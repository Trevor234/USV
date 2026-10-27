#include "phase_protocol.hpp"
#include <iostream>
#include <stdexcept>
using namespace controlled_phase;
int main(){
  unsigned checks=0;
  auto check=[&](bool v){++checks;if(!v)throw std::runtime_error("check "+std::to_string(checks));};
  Identity id{"owner-run","boot",std::string(64,'a'),"producer",baseline};
  auto peer=[&](uint8_t gid,bool observer=false){PeerBinding p;p.gid[0]=gid;p.pid=observer?200:100;p.process_start_ticks=50;p.manifest_sha256=std::string(64,'b');p.binary_sha256=std::string(64,'c');p.run_id=observer?"observer-run":id.run;p.boot_id=id.boot;p.contract_sha256=id.contract_sha256;return p;};
  auto obs=[&](const PeerBinding &p){return TransportObservation{p.gid,p.pid,p.process_start_ticks,true,false,true};};
  auto ap=peer(1),pp=peer(2),dp=peer(3,true),jp=peer(4,true);
  int64_t origin=1000000000;
  Decision d;d.sequence=1;d.tick=0;d.planned_ns=origin;d.finished_ns=origin+100;d.run_id=dp.run_id;d.boot_id=id.boot;d.contract_sha256=id.contract_sha256;
  Pair bootstrap{id,1,{0,0},{origin-1000000,origin-999000},{origin-999100,origin-998900},{true,true}};
  Pair p{id,2,{0,0},{origin+1000,origin+2000},{origin+1500,origin+2500},{true,true}};
  Commitment c{id,1,0,2,origin,origin+period_ns,origin+3000,{0,0},p.start,p.end};
  ObserverPhase observer(id,ap,pp);
  check(observer.observe_applied(bootstrap,obs(ap),origin).empty());
  check(observer.begin(d,origin+500).empty());
  auto foreign=obs(pp);foreign.actual_gid[0]=88;
  check(observer.observe_commitment(c,foreign,origin+4000)=="phase_transport_authentication");
  auto dead=obs(pp);dead.pidfd_alive=false;
  check(observer.observe_commitment(c,dead,origin+4000)=="phase_transport_authentication");
  auto bad=c;bad.held_until_ns--;
  check(observer.observe_commitment(bad,obs(pp),origin+4000)=="phase_identity_shape_or_time");
  check(observer.observe_commitment(c,obs(pp),origin+4000).empty());
  check(!observer.freeze(10,origin+4500)); // phase may precede Applied transport
  check(observer.observe_applied(p,obs(ap),origin+5000).empty());
  auto grant=observer.freeze(10,origin+6000);
  check(grant.has_value());check(grant->job.deadline_ns==origin+ready_ns);check(grant->job.target_ns==origin+period_ns);
  check(!observer.freeze(11,origin+7000));
  check(observer.observe_commitment(c,obs(pp),origin+8000)=="no_open_phase");
  Pair changed=p;changed.sequence=3;changed.command={0.1,0.1};changed.start={origin+100000000,origin+100001000};changed.end={origin+100000500,origin+100001500};
  check(observer.observe_applied(changed,obs(ap),origin+100002000).empty());
  check(observer.hold_input_changed()); // actual changed feedback remains visible
  ObserverPhase opposite(id,ap,pp);check(opposite.begin(d,origin+500).empty());
  check(opposite.observe_applied(p,obs(ap),origin+5000).empty());
  check(!opposite.freeze(10,origin+6000));
  check(opposite.observe_commitment(c,obs(pp),origin+7000).empty());
  check(opposite.freeze(10,origin+8000).has_value());
  ObserverPhase late(id,ap,pp);check(late.begin(d,origin+500).empty());
  check(late.observe_applied(p,obs(ap),origin+5000).empty());check(late.observe_commitment(c,obs(pp),origin+6000).empty());
  check(!late.freeze(10,origin+ready_ns+1));
  OwnerPhase owner(id,dp,jp,true);
  check(owner.observe_decision(d,obs(dp),origin+500)=="bootstrap_not_completed");
  check(owner.bootstrap_completed(bootstrap,origin));
  auto wrong=obs(dp);wrong.actual_gid[1]=3;
  check(owner.observe_decision(d,wrong,origin+500)=="decision_transport_authentication");
  auto cross=d;cross.contract_sha256=std::string(64,'d');
  check(owner.observe_decision(cross,obs(dp),origin+500)=="decision_shape_or_time");
  check(owner.observe_decision(d,obs(dp),origin+500).empty());check(owner.may_publish());
  auto failed=p;failed.succeeded[1]=false;
  check(!owner.publication_completed(failed,origin+3000));
  check(owner.publication_completed(p,origin+3000).has_value());check(!owner.may_publish());
  check(owner.observe_job(grant->job,obs(jp),origin+7000).empty());
  check(!owner.claim_negative_pulse(origin+99999999,{.1,.1}));
  check(!owner.claim_negative_pulse(origin+100000000,{10,10}));
  check(owner.claim_negative_pulse(origin+100000000,{.1,.1}));
  check(!owner.claim_negative_pulse(origin+100000001,{.1,.1}));
  check(owner.negative_publication_completed(changed,origin+100002000));
  check(!owner.negative_publication_completed(changed,origin+100002001));
  check(!owner.may_publish());
  Decision next=d;next.sequence=2;next.tick=1;next.job_id=10;next.planned_ns+=period_ns;next.finished_ns=next.planned_ns+100;
  auto premature=next;premature.planned_ns--;premature.finished_ns--;
  check(owner.observe_decision(premature,obs(dp),next.planned_ns-1)=="decision_shape_or_time");
  check(owner.observe_decision(next,obs(dp),next.planned_ns+200).empty());
  check(owner.next_command()==Command({.1,.1})); // rejection holds real last input
  auto mismatch=id;mismatch.baseline_id="F5_20261005_atomic_freeze_01";
  check(!mismatch.valid());
  std::cout<<"phase native checks="<<checks<<" passed; no ROS or actuator calls\n";
}
