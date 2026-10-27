#include "command_anchor_v1.hpp"
#include <nlohmann/json.hpp>
#include <functional>
#include <iostream>
#include <thread>
#include <atomic>
using namespace c36;
using Json=nlohmann::json;
void expect(bool x,const char* message) {if(!x)throw std::runtime_error(message);}
void ok(Result r) {if(!r)throw std::runtime_error(r.reason);}
void rejects(Result r,const char* reason) {expect(r.reason==reason, (std::string("expected ")+reason+", got "+r.reason).c_str());}
Owner owner() {return {"component-run","component-boot","component-owner",std::string(64,'a'),0};}
PairFeedback pair(uint64_t seq=1,double n=0,int64_t start=1000) {
  return {owner(),seq,{n,n},{Call::succeeded,Call::succeeded},{start,start+1000},{start+10,start+1010},start+2000};
}
struct Fixture {
  CommandAnchor book{owner()};FrozenJob job;uint64_t token=0;
  Fixture(){ok(book.observe(pair()));ok(book.open(4000));}
  void frozen(){ok(book.freeze(1,1,10000000,10000000,job));}
  void ready(p1::Command n={1,2},int64_t now=20000000){frozen();ok(book.ready(job,n,now));}
  void committed(){ready();ok(book.cutoff(161000000));}
  void active(){committed();ok(book.activate(job,1,210000000,token));expect(token==1,"token");}
  void start_left(){double n=0;ok(book.start(token,0,210000010,n));expect(n==1,"left command");}
  void done_left(){start_left();ok(book.complete(token,0,true,210000020));}
  void start_right(){double n=0;ok(book.start(token,1,210000030,n));expect(n==2,"right command");}
};
int main(int argc,char** argv) {
  if(argc==2 && std::string(argv[1])=="--history") {
    std::string raw;char buffer[4096];
    while(std::cin.read(buffer,sizeof(buffer)) || std::cin.gcount()) {
      raw.append(buffer,static_cast<size_t>(std::cin.gcount()));
      if(raw.size()>2*1024*1024) throw std::runtime_error("bounded_history_input");
    }
    auto input=Json::parse(raw);expect(input.is_array()&&input.size()<=64,"bounded history population");Json outputs=Json::array();
    for(const auto& item:input) {
      auto anchor=[](const Json& x){p1::Anchor a;a.n=x.at("n").get<p1::Command>();a.seq=x.at("sequence").get<std::array<uint64_t,2>>();a.time=x.at("publish_ns").get<std::array<int64_t,2>>();a.known=x.at("known").get<std::array<bool,2>>();return a;};
      std::deque<p1::PublicationEvent> history;
      expect(item.at("history").size()<=256,"bounded history entries");
      for(const auto& e:item.at("history"))history.push_back({e.at("channel").get<int>(),e.at("sequence").get<uint64_t>(),e.at("publish_ns").get<int64_t>(),e.at("n").get<double>(),e.at("known").get<bool>()});
      outputs.push_back({{"job_id",item.at("job_id")},{"reason",p1::publication_history_check(anchor(item.at("expected")),anchor(item.at("actual")),history)}});
    }
    std::cout<<outputs.dump()<<'\n';return 0;
  }
  Json cases=Json::array();
  auto test=[&](const char* name,std::function<void()> f){
    try{f();cases.push_back({{"id",name},{"passed",true}});}
    catch(const std::exception& e){cases.push_back({{"id",name},{"passed",false},{"error",e.what()}});}
  };
  test("nonzero_complete_pair_local_facts",[]{Fixture f;f.active();f.done_left();
    auto a=f.book.facts();expect(a.anchor.n==p1::Command{1,0},"per-channel left update");expect(!a.whole_pair_observed,"pair pending");
    f.start_right();ok(f.book.complete(f.token,1,true,210000040));ok(f.book.settle(f.token,210000050));
    a=f.book.facts();expect(a.anchor.n==p1::Command{1,2}&&a.anchor.known[0]&&a.anchor.known[1]&&a.whole_pair_observed,"complete facts");expect(!a.plant_acceptance_observed,"no plant");});
  test("same_value_consecutive_republish_is_equivalent",[]{Fixture f;f.ready();ok(f.book.observe(pair(2,0,50000000)));ok(f.book.cutoff(161000000));ok(f.book.activate(f.job,1,210000000,f.token));});
  test("changed_command_rejected_at_activation",[]{Fixture f;f.ready();ok(f.book.observe(pair(2,3,50000000)));ok(f.book.cutoff(161000000));rejects(f.book.activate(f.job,1,210000000,f.token),"anchor_mismatch");expect(f.token==0,"no permit");});
  test("change_then_return_is_not_equivalent",[]{Fixture f;f.ready();ok(f.book.observe(pair(2,3,50000000)));ok(f.book.observe(pair(3,0,60000000)));ok(f.book.cutoff(161000000));rejects(f.book.activate(f.job,1,210000000,f.token),"anchor_history_changed");});
  test("feedback_gap_faults_both_known",[]{Fixture f;rejects(f.book.observe(pair(3,0,50000000)),"feedback_gap");auto a=f.book.facts();expect(a.life==Life::faulted&&!a.anchor.known[0]&&!a.anchor.known[1],"gap uncertainty");});
  test("history_eviction_refuses_equivalence",[]{Fixture f;f.ready();for(uint64_t i=2;i<=131;++i)ok(f.book.observe(pair(i,0,50000000+int64_t(i)*10000)));ok(f.book.cutoff(161000000));rejects(f.book.activate(f.job,1,210000000,f.token),"anchor_history_incomplete");});
  test("ready_at_150ms_equality_allowed",[]{Fixture f;f.frozen();ok(f.book.ready(f.job,{1,2},160000000));});
  test("ready_after_150ms_rejected",[]{Fixture f;f.frozen();rejects(f.book.ready(f.job,{1,2},160000001),"ready_time");});
  test("cutoff_at_deadline_not_closed",[]{Fixture f;f.ready();rejects(f.book.cutoff(160000000),"cutoff_time");ok(f.book.cutoff(160000001));});
  test("activation_before_target_rejected",[]{Fixture f;f.committed();rejects(f.book.activate(f.job,1,209999999,f.token),"activation_time_or_tick");});
  test("activation_wrong_tick_rejected",[]{Fixture f;f.committed();rejects(f.book.activate(f.job,2,210000000,f.token),"activation_time_or_tick");});
  test("registration_does_not_activate_without_cutoff",[]{Fixture f;f.ready();rejects(f.book.activate(f.job,1,210000000,f.token),"not_committed");});
  test("duplicate_ready_rejected",[]{Fixture f;f.ready();rejects(f.book.ready(f.job,{1,2},30000000),"duplicate_or_cutoff");});
  test("old_job_id_cannot_be_reused",[]{Fixture f;f.frozen();ok(f.book.close(20000000));rejects(f.book.freeze(1,2,30000000,30000000,f.job),"owner_not_open");});
  test("frozen_anchor_value_forge_rejected",[]{Fixture f;f.frozen();auto j=f.job;j.ticket.anchor.n[0]=2;rejects(f.book.ready(j,{1,2},20000000),"frozen_job_mismatch");});
  test("frozen_owner_config_forge_rejected",[]{Fixture f;f.frozen();auto j=f.job;j.owner.config[0]='b';rejects(f.book.ready(j,{1,2},20000000),"frozen_job_mismatch");});
  test("version_change_invalidates_old_candidate",[]{Fixture f;f.ready();p1::Version v;v.model=2;ok(f.book.change_version(v,30000000));rejects(f.book.ready(f.job,{1,2},40000000),"frozen_job_mismatch");FrozenJob j;rejects(f.book.freeze(1,2,50000000,50000000,j),"old_job_or_tick");ok(f.book.freeze(2,2,50000000,50000000,j));});
  test("foreign_feedback_not_admitted",[]{Fixture f;auto p=pair(2,0,50000000);p.owner.producer="other";rejects(f.book.observe(p),"foreign_owner");expect(f.book.facts().anchor.seq[0]==1,"source not advanced");});
  test("invalid_owner_ascii_rejected",[]{auto o=owner();o.boot="bad\n";bool rejected=false;try{CommandAnchor b(o);}catch(const std::invalid_argument&){rejected=true;}expect(rejected,"owner bounds");});
  test("invalid_owner_config_sha_rejected",[]{auto o=owner();o.config[0]='G';bool rejected=false;try{CommandAnchor b(o);}catch(const std::invalid_argument&){rejected=true;}expect(rejected,"config SHA");});
  test("publish_sequence_overflow_failclosed",[]{CommandAnchor b(owner());ok(b.observe(pair(UINT64_MAX)));ok(b.open(4000));FrozenJob j;ok(b.freeze(1,1,10000000,10000000,j));ok(b.ready(j,{1,2},20000000));ok(b.cutoff(161000000));uint64_t token=99;rejects(b.activate(j,1,210000000,token),"sequence_overflow");expect(token==0,"no wrapped token");});
  test("origin_overflow_rejected",[]{Fixture f;rejects(f.book.freeze(1,1,INT64_MAX,INT64_MAX,f.job),"freeze_time");});
  test("feedback_time_reversal_faults",[]{Fixture f;auto p=pair(2,0,5000);p.receipt=3500;p.start={100,200};p.end={110,210};rejects(f.book.observe(p),"feedback_time_reversal");});
  test("left_failed_right_unattempted_retains_right_fact",[]{Fixture f;f.active();f.start_left();ok(f.book.complete(f.token,0,false,210000020));double n=0;rejects(f.book.start(f.token,1,210000030,n),"owner_not_open");rejects(f.book.settle(f.token,210000040),"incomplete_pair");auto a=f.book.facts();expect(!a.anchor.known[0]&&a.anchor.known[1]&&a.anchor.n[1]==0&&!a.whole_pair_observed,"local partial facts");});
  test("right_failed_left_success_keeps_left_only",[]{Fixture f;f.active();f.done_left();f.start_right();ok(f.book.complete(f.token,1,false,210000040));rejects(f.book.settle(f.token,210000050),"incomplete_pair");auto a=f.book.facts();expect(a.anchor.known[0]&&a.anchor.n[0]==1&&!a.anchor.known[1]&&a.life==Life::faulted,"right uncertainty");});
  test("missing_completion_keeps_active_and_cannot_settle",[]{Fixture f;f.active();f.start_left();rejects(f.book.settle(f.token,210000020),"completion_missing");expect(f.book.facts().active_transaction,"pending receipt");ok(f.book.close(210000030));expect(f.book.facts().life==Life::closing,"not falsely closed");});
  test("close_before_activation_retains_command_but_revokes",[]{Fixture f;f.committed();ok(f.book.close(200000000));rejects(f.book.activate(f.job,1,210000000,f.token),"owner_not_open");auto a=f.book.facts();expect(a.life==Life::closed&&a.anchor.known[0]&&a.anchor.known[1],"lifecycle distinct from facts");});
  test("close_before_any_start_blocks_both",[]{Fixture f;f.active();ok(f.book.close(210000001));double n=0;rejects(f.book.start(f.token,0,210000010,n),"owner_not_open");rejects(f.book.settle(f.token,210000020),"incomplete_pair");expect(f.book.facts().life==Life::closed,"settled no-call close");});
  test("close_between_calls_revokes_right_permit",[]{Fixture f;f.active();f.done_left();ok(f.book.close(210000025));double n=0;rejects(f.book.start(f.token,1,210000030,n),"owner_not_open");rejects(f.book.settle(f.token,210000040),"incomplete_pair");auto a=f.book.facts();expect(a.life==Life::closed&&a.anchor.n==p1::Command{1,0}&&a.anchor.known[1],"unattempted right retained");});
  test("close_during_right_inflight_preserves_actual_result",[]{Fixture f;f.active();f.done_left();f.start_right();ok(f.book.close(210000035));expect(f.book.facts().life==Life::closing,"inflight close");ok(f.book.complete(f.token,1,true,210000040));ok(f.book.settle(f.token,210000050));auto a=f.book.facts();expect(a.life==Life::closed&&a.whole_pair_observed&&a.anchor.n==p1::Command{1,2},"actual call facts retained without reopening");});
  test("closed_session_cannot_be_reopened_or_reseeded",[]{Fixture f;ok(f.book.close(5000));rejects(f.book.open(6000),"not_prepared");rejects(f.book.observe(pair(2,0,7000)),"owner_not_open");});
  test("stale_transaction_receipt_rejected",[]{Fixture f;f.active();f.start_left();rejects(f.book.complete(999,0,true,210000020),"transaction_identity");expect(f.book.facts().active_transaction,"receipt not consumed");});
  test("partial_external_feedback_faults_without_full_pair_claim",[]{Fixture f;auto p=pair(2,1,50000000);p.calls[1]=Call::failed;rejects(f.book.observe(p),"incomplete_pair");auto a=f.book.facts();expect(a.anchor.known[0]&&!a.anchor.known[1]&&!a.whole_pair_observed,"partial per-channel");});
  test("nonfinite_candidate_command_rejected",[]{Fixture f;f.frozen();rejects(f.book.ready(f.job,{NAN,1},20000000),"command_domain");});
  test("out_of_command_bounds_rejected",[]{Fixture f;f.frozen();rejects(f.book.ready(f.job,{25.0001,1},20000000),"command_domain");});
  test("activation_command_rate_guard_retained",[]{Fixture f;f.ready({25,25});ok(f.book.cutoff(161000000));rejects(f.book.activate(f.job,1,210000000,f.token),"command_rate");});
  test("unattempted_with_call_timestamp_is_invalid",[]{Fixture f;auto p=pair(2,0,50000000);p.calls[1]=Call::unattempted;rejects(f.book.observe(p),"unattempted_has_call_times");});
  test("right_start_requires_completed_left",[]{Fixture f;f.active();f.start_left();double n=0;rejects(f.book.start(f.token,1,210000020,n),"left_not_succeeded");});
  test("no_seed_no_open_no_job",[]{CommandAnchor b(owner());rejects(b.open(1000),"not_prepared");FrozenJob j;rejects(b.freeze(1,1,10000000,10000000,j),"owner_not_open");});
  test("duplicate_local_call_cannot_advance_anchor",[]{Fixture f;f.active();f.start_left();double n=0;rejects(f.book.start(f.token,0,210000011,n),"start_time_or_duplicate");ok(f.book.complete(f.token,0,true,210000020));rejects(f.book.complete(f.token,0,true,210000021),"completion_order");});
  test("frozen_epoch_or_time_forge_rejected",[]{Fixture f;f.frozen();auto j=f.job;j.owner.epoch=1;rejects(f.book.ready(j,{1,2},20000000),"frozen_job_mismatch");j=f.job;j.ticket.target_ns++;rejects(f.book.ready(j,{1,2},20000000),"frozen_job_mismatch");});
  test("old_echo_rejected_after_activation_consumption",[]{Fixture f;f.active();rejects(f.book.ready(f.job,{1,2},210000001),"frozen_job_mismatch");});
  test("unfinished_feedback_result_invalidates_knowledge",[]{Fixture f;auto p=pair(2,0,50000000);p.calls[0]=Call::started;rejects(f.book.observe(p),"unfinished_feedback_call");expect(!f.book.facts().anchor.known[0],"uncertainty retained");});
  test("concurrent_close_serializes_before_right_start",[]{Fixture f;f.active();f.done_left();std::atomic<bool> closed{false};Result right;
    std::thread a([&]{ok(f.book.close(210000025));closed.store(true,std::memory_order_release);});
    std::thread b([&]{while(!closed.load(std::memory_order_acquire))std::this_thread::yield();double n=0;right=f.book.start(f.token,1,210000030,n);});
    a.join();b.join();rejects(right,"owner_not_open");rejects(f.book.settle(f.token,210000040),"incomplete_pair");expect(f.book.facts().life==Life::closed,"concurrent close");});
  test("authenticated_unexpected_feedback_faults_active_transaction",[]{Fixture f;f.active();rejects(f.book.observe(pair(2,3,210000001)),"unexpected_feedback_during_transaction");double n=0;rejects(f.book.start(f.token,0,210000010,n),"owner_not_open");expect(!f.book.facts().anchor.known[0],"do not trust stale anchor");});
  test("version_regression_or_zero_rejected",[]{Fixture f;p1::Version v;v.model=2;ok(f.book.change_version(v,5000));v.model=1;rejects(f.book.change_version(v,6000),"version_regression_or_zero");v.model=2;v.config=0;rejects(f.book.change_version(v,6000),"version_regression_or_zero");});
  test("all_frozen_anchor_identity_fields_bound",[]{Fixture f;f.frozen();for(int i=0;i<9;++i){auto j=f.job;if(i==0)j.owner.run+="x";if(i==1)j.owner.boot+="x";if(i==2)j.owner.producer+="x";if(i==3)j.ticket.anchor.seq[0]++;if(i==4)j.ticket.anchor.time[1]++;if(i==5)j.ticket.anchor.known[0]=false;if(i==6)j.ticket.id++;if(i==7)j.freeze++;if(i==8)j.ticket.version.model++;rejects(f.book.ready(j,{1,2},20000000),"frozen_job_mismatch");}});
  test("unregistered_command_rate_limit_rejected",[]{auto l=p1::Limits{};l.rho=800;bool rejected=false;try{CommandAnchor b(owner(),l);}catch(const std::invalid_argument&){rejected=true;}expect(rejected,"registered diagnostic limits");});
  test("duplicate_feedback_never_advances_history",[]{Fixture f;rejects(f.book.observe(pair()),"replayed_feedback");expect(f.book.facts().anchor.seq[0]==1,"duplicate not appended");});
  test("local_completion_cannot_precede_call_start",[]{Fixture f;f.active();f.start_left();rejects(f.book.complete(f.token,0,true,210000009),"completion_order");expect(f.book.facts().anchor.n[0]==0,"invalid receipt cannot update facts");});
  bool passed=true;for(const auto& c:cases)passed=passed&&c.at("passed").get<bool>();
  std::cout<<Json{{"schema","p1-C3.6-A-native-command-anchor-tests/v1"},{"passed",passed},{"count",cases.size()},
    {"cases",cases},{"scope","native finite local command component; all call receipts simulated; no ROS publisher or plant"},
    {"new_ROS_nodes",false},{"actual_actuator_publish",false},{"stage_qualified",false},{"research_conclusion",false}}.dump(2)<<'\n';
  return passed?0:1;
}
