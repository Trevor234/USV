// SPDX-License-Identifier: MIT
// T3-Q family (batch 126 derivation of the batch-99 harness).
//
// F124-01 fix. The batch-99 harness captured the loop-local `base` by reference
// ([&]) in the racing producer threads; the capture died at the end of each loop
// iteration while four threads still read it, which is undefined behaviour and
// produced 350 duplicated accepted identities in runs/T3-Q2_r2. This file:
//   * captures every producer's base BY VALUE,
//   * gives each event an explicit {producer_id, local_seq} identity,
//   * opens a finite start gate so no thread runs before capture scope is fixed,
//   * reconciles offered = accepted U+ rejected as an exclusive complete
//     partition, and compares accepted / publisher-delivered / on-disk as
//     MULTISETS of identity, never as counts.
// The summary row stays outside the business-event population.
//
// DiagSink business behaviour is NOT changed: this file only changes the test
// load generator and the observations it makes.
#include "p1_diag_sink.hpp"
#include <algorithm>
#include <atomic>
#include <condition_variable>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <thread>
#include <utility>
#include <vector>

// Registration-fixed parameters (identical to batch 99: no pressure, capacity or
// thread-count changes are permitted to make a case pass).
constexpr size_t CAPACITY=512;                 // contract log_capacity
constexpr uint64_t K=2048;                     // pressure tail beyond capacity
constexpr uint64_t ATTEMPTS=CAPACITY+K;        // 2560 single-producer attempts
constexpr unsigned Q2_THREADS=4,Q2_M=768;      // 3072 concurrent attempts
constexpr int DELAY_PUBLISH_MS=2;
constexpr int64_t DRAIN_WAIT_NS=15000000000LL; // bounded drain-out wait

using Json=nlohmann::json;

// Identity = the registered sequence. producer_id/local_seq make the multiset
// argument auditable: a duplicate sequence originating from two producers is a
// different failure than one producer issuing the same sequence twice.
struct Decision {uint64_t sequence;};

// Publishers record every delivered identity inside their own lock so the
// delivered multiset can be compared with the accepted multiset.
struct ImmediatePublisher {
  std::mutex m; std::vector<uint64_t> delivered;
  void publish(const Decision &d){std::lock_guard<std::mutex> l(m);delivered.push_back(d.sequence);}
  std::vector<uint64_t> snapshot(){std::lock_guard<std::mutex> l(m);return delivered;}
  size_t calls(){return snapshot().size();}
};
struct DelayPublisher {
  std::mutex m; std::vector<uint64_t> delivered;
  void publish(const Decision &d){std::this_thread::sleep_for(std::chrono::milliseconds(DELAY_PUBLISH_MS));
    std::lock_guard<std::mutex> l(m);delivered.push_back(d.sequence);}
  std::vector<uint64_t> snapshot(){std::lock_guard<std::mutex> l(m);return delivered;}
  size_t calls(){return snapshot().size();}
};
struct BlockingPublisher {
  std::atomic<unsigned> picked{0};std::mutex m;std::condition_variable cv;bool released=false;
  std::vector<uint64_t> delivered;
  void publish(const Decision &d){++picked;std::unique_lock<std::mutex> l(m);cv.wait(l,[this]{return released;});
    delivered.push_back(d.sequence);}
  void release(){{std::lock_guard<std::mutex> l(m);released=true;}cv.notify_all();}
  std::vector<uint64_t> snapshot(){std::lock_guard<std::mutex> l(m);return delivered;}
  size_t calls(){return snapshot().size();}
};

using SinkB=p1::DiagSink<Decision,std::shared_ptr<BlockingPublisher>>;
using SinkD=p1::DiagSink<Decision,std::shared_ptr<DelayPublisher>>;
using SinkI=p1::DiagSink<Decision,std::shared_ptr<ImmediatePublisher>>;

int checks=0;Json asserts=Json::array();bool all_ok=true;
void check(bool v,const std::string &name,const Json &observed=Json(nullptr)){
  ++checks;if(!v)all_ok=false;asserts.push_back({{"name",name},{"passed",v},{"observed",observed}});}
void require(bool v,const char *why){++checks;if(!v)throw std::runtime_error(why);}

// ---------------------------------------------------------------- identity
struct Identity {uint64_t producer=0,local_seq=0,sequence=0;};
struct Offer {Identity id;bool accepted=false;};

// Explicit finite start gate: threads are constructed, each waits, and only the
// release() turns them loose. No sleep is used to paper over a lifetime problem.
class StartGate {
 public:
  void wait(){std::unique_lock<std::mutex> l(m_);cv_.wait(l,[this]{return open_;});}
  void release(){std::lock_guard<std::mutex> l(m_);open_=true;cv_.notify_all();}
  void arrive(){++arrived_;}
  unsigned arrived(){return arrived_.load();}
 private:
  std::mutex m_;std::condition_variable cv_;bool open_=false;std::atomic<unsigned> arrived_{0};
};

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

// Business events only: the summary row is never mixed into the event population.
std::vector<Json> business_events(const std::vector<Json> &data){
  std::vector<Json> out;
  for(const auto &r:data)if(r.value("type",std::string{})!="source_summary")out.push_back(r);
  return out;}

// Multiset helpers. Comparing sorted vectors keeps duplicates visible, which a
// set comparison would silently erase (the exact batch-99 blind spot).
std::multiset<uint64_t> multiset_of(const std::vector<uint64_t> &v){return std::multiset<uint64_t>(v.begin(),v.end());}
Json multiset_digest(const std::multiset<uint64_t> &ms){
  std::map<uint64_t,unsigned> dup;for(auto v:ms)++dup[v];
  unsigned duplicated_entries=0;for(const auto &kv:dup)if(kv.second>1)duplicated_entries+=kv.second-1;
  return {{"entries",ms.size()},{"unique",dup.size()},{"duplicated_entries",duplicated_entries}};}

void balance_checks(const Json &summary,uint64_t attempts){
  check(summary.at("generated").get<uint64_t>()==attempts,"generated_equals_attempts",
        {{"generated",summary.at("generated")},{"attempts",attempts}});
  check(summary.at("generated").get<uint64_t>()==summary.at("emitted").get<uint64_t>()+summary.at("dropped").get<uint64_t>(),
        "balance_generated_equals_emitted_plus_dropped",
        {{"generated",summary.at("generated")},{"emitted",summary.at("emitted")},{"dropped",summary.at("dropped")}});
  check(summary.at("normal_source_complete").get<bool>()==false,"normal_source_complete_false",summary);}

struct Counters {uint64_t accepted=0,rejected=0;};

// ------------------------------------------------------- T3-Q1d (regression)
// Blocked drain makes natural overflow deterministic. One event is drained first
// and provably blocks publishing outside the queue lock (picked==1 observed);
// the single producer then refills to capacity and every later add fails at the
// real bounded queue. Unchanged from batch 99 except identity bookkeeping.
void run_q1d(const std::filesystem::path &out){
  auto pub=std::make_shared<BlockingPublisher>();p1::Witness w(true);
  SinkB s((out/"q1d.jsonl").string(),CAPACITY,pub,&w);
  std::vector<Offer> offers;
  auto add=[&](uint64_t seq)->bool{const bool ok=s.add({{"type","t3_event"},{"sequence",seq},
      {"producer_id",0},{"local_seq",seq}},Decision{seq});offers.push_back({{0,seq,seq},ok});return ok;};
  require(add(0),"seed enqueue");
  require(wait_until([&]{return pub->picked.load()>=1;},DRAIN_WAIT_NS),"drain provably blocked at first publish");
  Counters c;for(uint64_t seq=1;seq<ATTEMPTS;++seq){if(add(seq))++c.accepted;else ++c.rejected;}
  ++c.accepted;                                    // account the seed event
  const uint64_t attempts=ATTEMPTS+1;              // +1 terminal probe stays accounted
  const bool terminal_reject=!s.add({{"type","t3_terminal_check"},{"sequence",UINT64_MAX},
      {"producer_id",0},{"local_seq",UINT64_MAX}},Decision{UINT64_MAX});
  check(terminal_reject,"terminal_add_rejects_while_full",{{"terminal_reject",terminal_reject}});
  ++c.rejected;
  auto snap=s.v1_snapshot();
  check(pub->calls()==0,"blocked_publisher_delivered_nothing_yet",{{"calls",pub->calls()}});
  pub->release();s.close();w.close_after_join();
  check(c.accepted==CAPACITY+1,"accepted_capacity_plus_one",{{"accepted",c.accepted},{"expected",CAPACITY+1}});
  check(c.rejected==K,"rejected_equals_K",{{"rejected",c.rejected},{"K",K}});
  const auto [ov,sf]=phase_counts(w);
  check(ov==1&&sf==1,"overflow_and_failure_each_once",{{"overflow",ov},{"source_failure",sf}});
  check(pub->calls()==c.accepted,"publisher_delivered_exactly_accepted",
        {{"calls",pub->calls()},{"accepted",c.accepted}});
  const auto data=rows(out/"q1d.jsonl");
  const auto events=business_events(data);
  check(data.size()==c.accepted+1,"file_rows_accepted_plus_summary",
        {{"rows",data.size()},{"expected",c.accepted+1}});
  balance_checks(data.back(),attempts);
  check(s.failed()==true,"failed_terminal_after_close",{{"failed",s.failed()}});
  check(s.peak_depth()==CAPACITY,"peak_equals_capacity",{{"peak",s.peak_depth()}});
  check(snap.at("dropped").get<uint64_t>()==c.rejected,"snapshot_dropped_matches",snap.at("dropped"));
  check(snap.at("generated").get<uint64_t>()==attempts,"snapshot_generated_matches",snap.at("generated"));
  // identity: every offered identity is unique and the accepted multiset matches
  // the delivered multiset and the on-disk multiset.
  std::vector<uint64_t> accepted_ids,offered_ids;
  for(const auto &o:offers){offered_ids.push_back(o.id.sequence);if(o.accepted)accepted_ids.push_back(o.id.sequence);}
  std::vector<uint64_t> disk_ids;for(const auto &r:events)disk_ids.push_back(r.at("sequence").get<uint64_t>());
  check(multiset_of(offered_ids).size()==std::set<uint64_t>(offered_ids.begin(),offered_ids.end()).size(),
        "q1d_offered_identities_unique",multiset_digest(multiset_of(offered_ids)));
  check(multiset_of(accepted_ids)==multiset_of(pub->snapshot()),"q1d_published_multiset_equals_accepted",
        {{"accepted",multiset_digest(multiset_of(accepted_ids))},{"published",multiset_digest(multiset_of(pub->snapshot()))}});
  check(multiset_of(accepted_ids)==multiset_of(disk_ids),"q1d_disk_multiset_equals_accepted",
        {{"accepted",multiset_digest(multiset_of(accepted_ids))},{"disk",multiset_digest(multiset_of(disk_ids))}});}

// ------------------------------------------------- T3-Q1r / Q3 (identity)
void run_racing_sequential(const std::string &name,const std::filesystem::path &out,bool identity){
  auto pub=std::make_shared<DelayPublisher>();p1::Witness w(true);
  SinkD s((out/(name+".jsonl")).string(),CAPACITY,pub,&w);
  std::vector<uint64_t> accepted_ids,offered_ids;
  for(uint64_t seq=1;seq<=ATTEMPTS;++seq){
    const bool ok=s.add({{"type","t3_event"},{"sequence",seq},{"producer_id",0},{"local_seq",seq}},Decision{seq});
    offered_ids.push_back(seq);if(ok)accepted_ids.push_back(seq);}
  const uint64_t attempts=ATTEMPTS;
  auto snap=s.v1_snapshot();
  const bool drained=wait_until([&]{return pub->calls()==accepted_ids.size();},DRAIN_WAIT_NS);
  check(drained,"bounded_drain_out_completed",{{"publisher_calls",pub->calls()},{"accepted",accepted_ids.size()}});
  s.close();w.close_after_join();
  const uint64_t rejected=attempts-accepted_ids.size();
  check(accepted_ids.size()+rejected==attempts,"attempts_all_accounted",
        {{"accepted",accepted_ids.size()},{"rejected",rejected},{"attempts",attempts}});
  check(snap.at("generated").get<uint64_t>()==attempts,"generated_equals_attempts",snap.at("generated"));
  check(snap.at("dropped").get<uint64_t>()==rejected,"dropped_equals_rejected",
        {{"dropped",snap.at("dropped")},{"rejected",rejected}});
  check(rejected>0,"pressure_actually_applied",{{"rejected",rejected}});
  check(snap.at("failed").get<bool>()==true&&s.failed()==true,"failed_flag_true",{{"failed",s.failed()}});
  check(static_cast<uint64_t>(s.peak_depth())<=CAPACITY,"peak_within_capacity",{{"peak",s.peak_depth()}});
  const auto [ov,sf]=phase_counts(w);
  check(ov==1,"queue_overflow_phase_exactly_once",{{"observed",ov}});
  check(sf==1,"source_failure_phase_exactly_once",{{"observed",sf}});
  check(pub->calls()==accepted_ids.size(),"publisher_delivered_exactly_accepted",
        {{"calls",pub->calls()},{"accepted",accepted_ids.size()}});
  const auto data=rows(out/(name+".jsonl"));
  const auto events=business_events(data);
  check(data.size()==accepted_ids.size()+1,"file_rows_accepted_plus_summary",{{"rows",data.size()}});
  balance_checks(data.back(),attempts);
  std::vector<uint64_t> disk_ids;for(const auto &r:events)disk_ids.push_back(r.at("sequence").get<uint64_t>());
  if(identity){
    check(multiset_of(disk_ids)==multiset_of(accepted_ids),"each_accepted_event_exactly_once",
          {{"disk",multiset_digest(multiset_of(disk_ids))},{"accepted",multiset_digest(multiset_of(accepted_ids))}});
    check(multiset_of(pub->snapshot())==multiset_of(accepted_ids),"published_multiset_equals_accepted",
          {{"published",multiset_digest(multiset_of(pub->snapshot()))}});
    bool all_in_range=std::all_of(disk_ids.begin(),disk_ids.end(),
        [](uint64_t v){return v>=1&&v<1+ATTEMPTS;});
    check(all_in_range,"sequences_within_registered_ranges");}}

// ------------------------------------------------------------ T3-Q2 (fix)
// Four concurrent producers. The batch-99 defect was a by-reference capture of
// the loop-local base; here the capture is by value, each event carries an
// explicit producer identity, and the start gate guarantees no thread begins
// before the captured values are fixed.
void run_q2(const std::filesystem::path &out){
  auto pub=std::make_shared<DelayPublisher>();p1::Witness w(true);
  SinkD s((out/"q2.jsonl").string(),CAPACITY,pub,&w);
  const uint64_t attempts=uint64_t(Q2_THREADS)*Q2_M;
  std::vector<std::thread> ts;StartGate gate;
  std::mutex acc_m,off_m;
  std::vector<uint64_t> accepted_ids,offered_ids;
  std::atomic<uint64_t> accepted{0},rejected{0};
  for(unsigned t=0;t<Q2_THREADS;++t){
    const uint64_t base=1+uint64_t(t)*Q2_M;      // captured BY VALUE below
    const uint64_t producer=t;
    ts.emplace_back([&,base,producer]{
      gate.arrive();
      gate.wait();                               // finite start barrier
      std::vector<uint64_t> local_acc,local_off;
      for(unsigned i=0;i<Q2_M;++i){
        const uint64_t seq=base+i;
        const bool ok=s.add({{"type","t3_event"},{"sequence",seq},
                             {"producer_id",producer},{"local_seq",i}},Decision{seq});
        local_off.push_back(seq);
        if(ok){local_acc.push_back(seq);++accepted;}else ++rejected;}
      {std::lock_guard<std::mutex> l(acc_m);accepted_ids.insert(accepted_ids.end(),local_acc.begin(),local_acc.end());}
      {std::lock_guard<std::mutex> l(off_m);offered_ids.insert(offered_ids.end(),local_off.begin(),local_off.end());}});}
  const auto deadline=p1::diag_now()+DRAIN_WAIT_NS;
  while(gate.arrived()<Q2_THREADS&&p1::diag_now()<deadline)std::this_thread::sleep_for(std::chrono::milliseconds(1));
  require(gate.arrived()==Q2_THREADS,"all producers reached the start gate");
  gate.release();
  for(auto &t:ts)t.join();
  auto snap=s.v1_snapshot();
  const bool drained=wait_until([&]{return pub->calls()==accepted_ids.size();},DRAIN_WAIT_NS);
  check(drained,"bounded_drain_out_completed",{{"publisher_calls",pub->calls()},{"accepted",accepted_ids.size()}});
  s.close();w.close_after_join();
  check(accepted.load()+rejected.load()==attempts,"attempts_all_accounted",
        {{"accepted",accepted.load()},{"rejected",rejected.load()},{"attempts",attempts}});
  check(snap.at("generated").get<uint64_t>()==attempts,"generated_equals_attempts",snap.at("generated"));
  check(snap.at("dropped").get<uint64_t>()==rejected.load(),"dropped_equals_rejected",
        {{"dropped",snap.at("dropped")},{"rejected",rejected.load()}});
  check(rejected.load()>0,"pressure_actually_applied",{{"rejected",rejected.load()}});
  check(snap.at("failed").get<bool>()==true&&s.failed()==true,"failed_flag_true",{{"failed",s.failed()}});
  check(static_cast<uint64_t>(s.peak_depth())<=CAPACITY,"peak_within_capacity",{{"peak",s.peak_depth()}});
  const auto [ov,sf]=phase_counts(w);
  check(ov==1,"queue_overflow_phase_exactly_once",{{"observed",ov}});
  check(sf==1,"source_failure_phase_exactly_once",{{"observed",sf}});
  check(pub->calls()==accepted_ids.size(),"publisher_delivered_exactly_accepted",
        {{"calls",pub->calls()},{"accepted",accepted_ids.size()}});
  const auto data=rows(out/"q2.jsonl");
  const auto events=business_events(data);
  check(data.size()==accepted_ids.size()+1,"file_rows_accepted_plus_summary",{{"rows",data.size()}});
  balance_checks(data.back(),attempts);

  // ---- identity and multiset reconciliation (the F124-01 core)
  const auto offered_ms=multiset_of(offered_ids);
  const auto accepted_ms=multiset_of(accepted_ids);
  std::vector<uint64_t> pub_ids=pub->snapshot();
  std::vector<uint64_t> disk_ids;std::vector<std::pair<uint64_t,uint64_t>> disk_pairs;
  for(const auto &r:events){
    disk_ids.push_back(r.at("sequence").get<uint64_t>());
    disk_pairs.push_back({r.at("producer_id").get<uint64_t>(),r.at("local_seq").get<uint64_t>()});}
  const auto disk_ms=multiset_of(disk_ids);
  // offered identities unique: 4 producers x 768 disjoint sequences
  check(offered_ms.size()==std::set<uint64_t>(offered_ids.begin(),offered_ids.end()).size(),
        "q2_offered_identities_unique",multiset_digest(offered_ms));
  // accepted has no unexpected duplicate
  check(accepted_ms.size()==std::set<uint64_t>(accepted_ids.begin(),accepted_ids.end()).size(),
        "q2_accepted_identities_unique",multiset_digest(accepted_ms));
  // exclusive complete partition
  check(offered_ms.size()==accepted_ms.size()+(attempts-accepted_ms.size()),
        "q2_offered_eq_accepted_plus_rejected",
        {{"offered",offered_ms.size()},{"accepted",accepted_ms.size()},{"rejected",attempts-accepted_ms.size()}});
  // published multiset == accepted multiset
  check(multiset_of(pub_ids)==accepted_ms,"q2_published_multiset_equals_accepted",
        {{"published",multiset_digest(multiset_of(pub_ids))},{"accepted",multiset_digest(accepted_ms)}});
  // on-disk multiset == accepted multiset
  check(disk_ms==accepted_ms,"q2_disk_multiset_equals_accepted",
        {{"disk",multiset_digest(disk_ms)},{"accepted",multiset_digest(accepted_ms)}});
  // every producer's local sequence is monotonic and covers exactly its own range
  bool per_producer_ok=true;
  for(unsigned t=0;t<Q2_THREADS;++t){
    const uint64_t base=1+uint64_t(t)*Q2_M;
    unsigned seen=0;
    for(size_t k=0;k<disk_pairs.size();++k){
      if(disk_pairs[k].first==t){++seen;
        if(disk_pairs[k].second!=disk_ids[k]-base){per_producer_ok=false;}}}
    if(seen>Q2_M)per_producer_ok=false;}
  check(per_producer_ok,"q2_producer_local_sequence_consistent");}

// ------------------------------------------------------------ T3-Q4 (clean)
void run_q4(const std::filesystem::path &out){
  auto pub=std::make_shared<ImmediatePublisher>();p1::Witness w(true);
  SinkI s((out/"q4.jsonl").string(),CAPACITY,pub,&w);
  std::vector<uint64_t> accepted_ids;
  for(uint64_t seq=1;seq<=100;++seq)
    if(s.add({{"type","t3_event"},{"sequence",seq},{"producer_id",0},{"local_seq",seq}},Decision{seq}))
      accepted_ids.push_back(seq);
  auto snap=s.v1_snapshot();
  const bool drained=wait_until([&]{return pub->calls()==accepted_ids.size();},DRAIN_WAIT_NS);
  check(drained,"bounded_drain_completed",{{"calls",pub->calls()},{"accepted",accepted_ids.size()}});
  s.close();w.close_after_join();
  const uint64_t rejected=100-accepted_ids.size();
  check(accepted_ids.size()==100&&rejected==0,"no_pressure_no_rejection",
        {{"accepted",accepted_ids.size()},{"rejected",rejected}});
  check(s.failed()==false,"failed_flag_false",{{"failed",s.failed()}});
  const auto [ov,sf]=phase_counts(w);
  check(ov==0&&sf==0,"no_overflow_no_failure_phases",{{"overflow",ov},{"source_failure",sf}});
  const auto data=rows(out/"q4.jsonl");
  const auto &summary=data.back();
  check(summary.at("normal_source_complete").get<bool>()==true,"normal_source_complete_true",summary);
  check(summary.at("dropped").get<uint64_t>()==0,"dropped_zero",summary.at("dropped"));
  check(pub->calls()==100&&summary.at("emitted").get<uint64_t>()==100,"all_emitted",
        {{"publisher_calls",pub->calls()},{"emitted",summary.at("emitted")}});
  check(summary.at("generated").get<uint64_t>()==100,"generated_equals_attempts",summary.at("generated"));
  const auto events=business_events(data);
  std::vector<uint64_t> disk_ids;for(const auto &r:events)disk_ids.push_back(r.at("sequence").get<uint64_t>());
  check(multiset_of(disk_ids)==multiset_of(accepted_ids),"q4_disk_multiset_equals_accepted",
        {{"disk",multiset_digest(multiset_of(disk_ids))}});}

int main(int argc,char **argv){try{
  require(argc==3,"usage: test_t3_queue_pressure_v2 <case_id> <fresh_out_dir>");
  const std::string casename=argv[1];const std::filesystem::path out(argv[2]);
  require(!std::filesystem::exists(out),"fresh output directory required (single finite execution)");
  std::filesystem::create_directories(out);
  if(casename=="Q2V-Q1d")run_q1d(out);
  else if(casename=="Q2V-Q1r")run_racing_sequential("q1r",out,false);
  else if(casename=="Q2V-Q2")run_q2(out);
  else if(casename=="Q2V-Q3")run_racing_sequential("q3",out,true);
  else if(casename=="Q2V-Q4")run_q4(out);
  else require(false,"unknown case");
  Json result={{"schema","T3-queue-pressure/v2"},{"case",casename},{"passed",all_ok},
    {"assertions",asserts},{"assertion_count",asserts.size()},{"checks",checks},
    {"capacity",CAPACITY},{"K",K},
    {"attempts",casename=="Q2V-Q2"?uint64_t(Q2_THREADS)*Q2_M:(casename=="Q2V-Q4"?uint64_t{100}:ATTEMPTS)},
    {"producer_identity_recorded",true},{"start_gate","finite"},
    {"ROS_context_created",false},{"actuator_endpoints_created",false},{"stage_qualified",false},
    {"execute_qualified",false},{"research_conclusion",false}};
  std::ofstream f(out/"result.json");f<<result.dump(2)<<'\n';require(bool(f),"evidence stream");
  std::cout<<"case="<<casename<<" passed="<<(all_ok?"true":"false")<<" assertions="<<asserts.size()<<'\n';
  return all_ok?0:2;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
