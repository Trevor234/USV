#include <cassert>
#include <iostream>
#include "/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/observer/src/shadow/p1_admission.hpp"
#include "/home/trevor/USV/usv_mpc_ws/src/usv_research_safety_cpp/p1_capability_lease.hpp"
int main(){
  p1::Version v;
  p1::Ticket t;t.id=1;t.target=2;t.origin=1000000000;t.deadline=t.origin+p1::DEADLINE;t.target_ns=t.origin+p1::T;t.version=v;
  p1::Admission a;
  assert(!a.cutoff(t.deadline));
  assert(a.register_ready(t,1,t.deadline,v).empty());
  assert(a.finalize_ready(1,t.deadline));
  assert(!a.take(2,t.target_ns-1));
  assert(a.take(2,t.target_ns));
  assert(!a.take(2,t.target_ns));
  std::cout<<"deadline equality, fixed target, one-time consumption: PASS\n";
  p1::Admission late;
  assert(late.register_ready(t,1,t.deadline,v).empty());
  assert(!late.finalize_ready(1,t.deadline+1));
  assert(!late.take(2,t.target_ns));
  std::cout<<"post-copy completion past deadline retracts ready: PASS\n";
  p1::Admission invalid;
  assert(invalid.register_ready(t,1,t.deadline,v).empty());
  invalid.cutoff(t.deadline+1);invalid.invalidate();
  assert(!invalid.take(2,t.target_ns));
  std::cout<<"invalidation clears committed candidate: PASS\n";
  p1::Anchor anchor;anchor.n={25,-25};anchor.known={true,true};anchor.time={1000000000,1000000000};
  p1::Limits limits;
  auto fallback=p1::fallback(anchor,1200000000,0,limits,true);
  assert(fallback[0]==9 && fallback[1]==-9);
  std::cout<<"P1 invalid fallback respects 80N/s over 200ms: PASS (9,-9 N)\n";
  p1::CapabilityLease lease(600000000);
  assert(lease.renew(1000000000));
  assert(lease.check(1600000000).empty());
  assert(lease.check(1600000001)=="worker_capability_expired");
  assert(!lease.renew(1600000002));
  std::cout<<"lease equality valid, expiry terminal, no same-run revival: PASS\n";
}
