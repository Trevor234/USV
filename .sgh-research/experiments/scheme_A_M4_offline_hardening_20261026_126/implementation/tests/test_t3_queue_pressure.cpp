// SPDX-License-Identifier: MIT
// T3-Q family: organic producer pressure on the real DiagSink enqueue/drain path.
// No ROS context, no actuator endpoints, no armed V1 gate (test_v1_sink_queue.cpp
// already covers the armed saturation gate). Each invocation runs exactly one
// registered case and writes result.json with per-assertion evidence.
#include "p1_diag_sink.hpp"
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <set>
#include <thread>
#include <utility>
#include <vector>
// Registration-fixed parameters (T3Q_registration.json must carry the same values).
constexpr size_t CAPACITY=512;                 // contract log_capacity
constexpr uint64_t K=2048;                     // pressure tail beyond capacity
constexpr uint64_t ATTEMPTS=CAPACITY+K;        // 2560 single-producer attempts
constexpr unsigned Q2_THREADS=4,Q2_M=768;      // 3072 concurrent attempts
constexpr int DELAY_PUBLISH_MS=2;
constexpr int64_t DRAIN_WAIT_NS=15000000000LL; // bounded drain-out wait
struct Decision {uint64_t sequence;};
struct ImmediatePublisher {std::atomic<unsigned> calls{0};void publish(const Decision &){++calls;}};
struct DelayPublisher {std::atomic<unsigned> calls{0};void publish(const Decision &){std::this_thread::sleep_for(std::chrono::milliseconds(DELAY_PUBLISH_MS));++calls;}};
struct BlockingPublisher {
  std::atomic<unsigned> calls{0},picked{0};std::mutex m;std::condition_variable cv;bool released=false;
  void publish(const Decision &){++picked;std::unique_lock<std::mutex> l(m);cv.wait(l,[this]{return released;});++calls;}
  void release(){{std::lock_guard<std::mutex> l(m);released=true;}cv.notify_all();}
};
using Json=nlohmann::json;
using SinkB=p1::DiagSink<Decision,std::shared_ptr<BlockingPublisher>>;
using SinkD=p1::DiagSink<Decision,std::shared_ptr<DelayPublisher>>;
using SinkI=p1::DiagSink<Decision,std::shared_ptr<ImmediatePublisher>>;
int checks=0;Json asserts=Json::array();bool all_ok=true;
void check(bool v,const std::string &name,const Json &observed){
  ++checks;if(!v)all_ok=false;asserts.push_back({{"name",name},{"passed",v},{"observed",observed}});}
void require(bool v,const char *why){++checks;if(!v)throw std::runtime_error(why);}
struct Counters {uint64_t accepted=0,rejected=0;};
template<class S> Counters produce(S &s,uint64_t attempts,uint64_t base){
  Counters c;for(uint64_t i=0;i<attempts;++i)
    {if(s.add({{"type","t3_event"},{"sequence",base+i}},Decision{base+i}))++c.accepted;else++c.rejected;}
  return c;}
template<class P> bool wait_until(const P &pred,int64_t timeout_ns){
  const auto deadline=p1::diag_now()+timeout_ns;
  while(!pred()){if(p1::diag_now()>deadline)return false;std::this_thread::sleep_for(std::chrono::milliseconds(2));}
  return true;}
std::pair<unsigned,unsigned> phase_counts(const p1::Witness &w){
  unsigned ov=0,sf=0;w.for_each_phase_after_join([&](uint64_t,const p1::WitnessPhase &r){
    if(r.event_code==p1::WitnessPhaseKind::QueueOverflow)++ov;
    else if(r.event_code==p1::WitnessPhaseKind::SourceFailure)++sf;});
  return {ov,sf};}
std::vector<Json> rows(const std::filesystem::path &p){
  std::ifstream f(p);std::vector<Json> r;std::string line;
  while(std::getline(f,line))if(!line.empty())r.push_back(Json::parse(line));return r;}
void balance_checks(const Json &summary,uint64_t attempts){
  check(summary.at("generated").get<uint64_t>()==attempts,"generated_equals_attempts",
        {{"generated",summary.at("generated")},{"attempts",attempts}});
  check(summary.at("generated").get<uint64_t>()==summary.at("emitted").get<uint64_t>()+summary.at("dropped").get<uint64_t>(),
        "balance_generated_equals_emitted_plus_dropped",
        {{"generated",summary.at("generated")},{"emitted",summary.at("emitted")},{"dropped",summary.at("dropped")}});
  check(summary.at("normal_source_complete").get<bool>()==false,"normal_source_complete_false",summary);}
// T3-Q1d: blocked drain makes natural overflow deterministic. One event is
// drained first and provably blocks publishing outside the queue lock
// (picked==1 observed); the single producer then refills to capacity, and
// every later add fails at the real bounded queue.
void run_q1d(const std::filesystem::path &out){
  auto pub=std::make_shared<BlockingPublisher>();p1::Witness w(true);
  SinkB s((out/"q1d.jsonl").string(),CAPACITY,pub,&w);
  require(s.add({{"type","t3_event"},{"sequence",0}},Decision{0}),"seed enqueue");
  require(wait_until([&]{return pub->picked.load()>=1;},DRAIN_WAIT_NS),"drain provably blocked at first publish");
  Counters c=produce(s,ATTEMPTS-1,1);++c.accepted;  // account the seed event
  const uint64_t attempts=ATTEMPTS+1;               // +1 terminal probe stays accounted
  const bool terminal_reject=!s.add({{"type","t3_terminal_check"}},Decision{UINT64_MAX});
  check(terminal_reject,"terminal_add_rejects_while_full",{{"terminal_reject",terminal_reject}});
  ++c.rejected;
  auto snap=s.v1_snapshot();
  check(pub->calls.load()==0,"blocked_publisher_delivered_nothing_yet",{{"calls",pub->calls.load()}});
  pub->release();s.close();w.close_after_join();
  check(c.accepted==CAPACITY+1,"accepted_capacity_plus_one",{{"accepted",c.accepted},{"expected",CAPACITY+1}});
  check(c.rejected==K,"rejected_equals_K",{{"rejected",c.rejected},{"K",K}});
  const auto [ov,sf]=phase_counts(w);
  check(ov==1&&sf==1,"overflow_and_failure_each_once",{{"overflow",ov},{"source_failure",sf}});
  check(pub->calls.load()==c.accepted,"publisher_delivered_exactly_accepted",{{"calls",pub->calls.load()},{"accepted",c.accepted}});
  const auto data=rows(out/"q1d.jsonl");
  check(data.size()==c.accepted+1,"file_rows_accepted_plus_summary",{{"rows",data.size()},{"expected",c.accepted+1}});
  balance_checks(data.back(),attempts);
  check(s.failed()==true,"failed_terminal_after_close",{{"failed",s.failed()}});
  check(s.peak_depth()==CAPACITY,"peak_equals_capacity",{{"peak",s.peak_depth()}});
  check(snap.at("dropped").get<uint64_t>()==c.rejected,"snapshot_dropped_matches",snap.at("dropped"));
  check(snap.at("generated").get<uint64_t>()==attempts,"snapshot_generated_matches",snap.at("generated"));}
// Racing-pressure runner: slow drain, invariants only (no exact split claimed).
void run_racing(const std::string &name,const std::filesystem::path &out,bool concurrent,bool identity){
  auto pub=std::make_shared<DelayPublisher>();p1::Witness w(true);
  SinkD s((out/(name+".jsonl")).string(),CAPACITY,pub,&w);
  Counters total;std::vector<std::pair<uint64_t,uint64_t>> ranges;
  if(concurrent){
    std::atomic<uint64_t> acc{0},rej{0};std::vector<std::thread> ts;
    for(unsigned t=0;t<Q2_THREADS;++t){const uint64_t base=1+uint64_t(t)*Q2_M;
      ranges.push_back({base,base+Q2_M});ts.emplace_back([&]{for(unsigned i=0;i<Q2_M;++i)
        {if(s.add({{"type","t3_event"},{"sequence",base+i}},Decision{base+i}))++acc;else++rej;}});}
    for(auto &t:ts)t.join();
    total={acc.load(),rej.load()};
  }else{total=produce(s,ATTEMPTS,1);ranges.push_back({1,1+ATTEMPTS});}
  const uint64_t attempts=concurrent?uint64_t(Q2_THREADS)*Q2_M:ATTEMPTS;
  auto snap=s.v1_snapshot();
  const bool drained=wait_until([&]{return pub->calls.load()==total.accepted;},DRAIN_WAIT_NS);
  check(drained,"bounded_drain_out_completed",{{"publisher_calls",pub->calls.load()},{"accepted",total.accepted}});
  s.close();w.close_after_join();
  check(total.accepted+total.rejected==attempts,"attempts_all_accounted",
        {{"accepted",total.accepted},{"rejected",total.rejected},{"attempts",attempts}});
  check(snap.at("generated").get<uint64_t>()==attempts,"generated_equals_attempts",snap.at("generated"));
  check(snap.at("dropped").get<uint64_t>()==total.rejected,"dropped_equals_rejected",
        {{"dropped",snap.at("dropped")},{"rejected",total.rejected}});
  check(total.rejected>0,"pressure_actually_applied",{{"rejected",total.rejected}});
  check(snap.at("failed").get<bool>()==true&&s.failed()==true,"failed_flag_true",{{"failed",s.failed()}});
  check(static_cast<uint64_t>(s.peak_depth())<=CAPACITY,"peak_within_capacity",{{"peak",s.peak_depth()}});
  const auto [ov,sf]=phase_counts(w);
  check(ov==1,"queue_overflow_phase_exactly_once",{{"observed",ov}});
  check(sf==1,"source_failure_phase_exactly_once",{{"observed",sf}});
  check(pub->calls.load()==total.accepted,"publisher_delivered_exactly_accepted",
        {{"calls",pub->calls.load()},{"accepted",total.accepted}});
  const auto data=rows(out/(name+".jsonl"));
  check(data.size()==total.accepted+1,"file_rows_accepted_plus_summary",{{"rows",data.size()}});
  balance_checks(data.back(),attempts);
  if(identity){  // T3-Q3: per-event identity, no loss, no duplicate at event level
    std::set<uint64_t> seen;unsigned events=0;bool all_in_range=true;
    for(const auto &r:data)if(r.value("type",std::string{})=="t3_event"){
      ++events;const uint64_t seq=r.at("sequence").get<uint64_t>();
      seen.insert(seq);bool in=false;
      for(const auto &range:ranges)if(seq>=range.first&&seq<range.second)in=true;
      all_in_range=all_in_range&&in;}
    check(events==total.accepted&&seen.size()==total.accepted,"each_accepted_event_exactly_once",
          {{"events",events},{"unique",seen.size()},{"accepted",total.accepted}});
    check(all_in_range,"sequences_within_registered_ranges",{{"ranges",ranges.size()}});}}
void run_q4(const std::filesystem::path &out){
  auto pub=std::make_shared<ImmediatePublisher>();p1::Witness w(true);
  SinkI s((out/"q4.jsonl").string(),CAPACITY,pub,&w);
  const Counters c=produce(s,100,1);
  auto snap=s.v1_snapshot();
  const bool drained=wait_until([&]{return pub->calls.load()==c.accepted;},DRAIN_WAIT_NS);
  check(drained,"bounded_drain_completed",{{"calls",pub->calls.load()},{"accepted",c.accepted}});
  s.close();w.close_after_join();
  check(c.accepted==100&&c.rejected==0,"no_pressure_no_rejection",{{"accepted",c.accepted},{"rejected",c.rejected}});
  check(s.failed()==false,"failed_flag_false",{{"failed",s.failed()}});
  const auto [ov,sf]=phase_counts(w);
  check(ov==0&&sf==0,"no_overflow_no_failure_phases",{{"overflow",ov},{"source_failure",sf}});
  const auto data=rows(out/"q4.jsonl");
  const auto &summary=data.back();
  check(summary.at("normal_source_complete").get<bool>()==true,"normal_source_complete_true",summary);
  check(summary.at("dropped").get<uint64_t>()==0,"dropped_zero",summary.at("dropped"));
  check(pub->calls.load()==100&&summary.at("emitted").get<uint64_t>()==100,"all_emitted",
        {{"publisher_calls",pub->calls.load()},{"emitted",summary.at("emitted")}});
  check(summary.at("generated").get<uint64_t>()==100,"generated_equals_attempts",summary.at("generated"));}
int main(int argc,char **argv){try{
  require(argc==3,"usage: test_t3_queue_pressure <case_id> <fresh_out_dir>");
  const std::string casename=argv[1];const std::filesystem::path out(argv[2]);
  require(!std::filesystem::exists(out),"fresh output directory required (single finite execution)");
  std::filesystem::create_directories(out);
  if(casename=="T3-Q1d")run_q1d(out);
  else if(casename=="T3-Q1r")run_racing("q1r",out,false,false);
  else if(casename=="T3-Q2")run_racing("q2",out,true,false);
  else if(casename=="T3-Q3")run_racing("q3",out,false,true);
  else if(casename=="T3-Q4")run_q4(out);
  else require(false,"unknown case");
  Json result={{"schema","T3-queue-pressure/v1"},{"case",casename},{"passed",all_ok},
    {"assertions",asserts},{"assertion_count",asserts.size()},{"checks",checks},
    {"capacity",CAPACITY},{"K",K},
    {"attempts",casename=="T3-Q2"?uint64_t(Q2_THREADS)*Q2_M:(casename=="T3-Q4"?uint64_t{100}:ATTEMPTS)},
    {"ROS_context_created",false},{"actuator_endpoints_created",false},{"stage_qualified",false},
    {"execute_qualified",false},{"research_conclusion",false}};
  std::ofstream f(out/"result.json");f<<result.dump(2)<<'\n';require(bool(f),"evidence stream");
  std::cout<<"case="<<casename<<" passed="<<(all_ok?"true":"false")<<" assertions="<<asserts.size()<<'\n';
  return all_ok?0:2;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
