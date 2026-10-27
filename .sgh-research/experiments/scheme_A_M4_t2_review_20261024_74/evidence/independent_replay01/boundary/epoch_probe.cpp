// Offline counterexamples using the actual preserved rev8 Epoch header.
// No ROS, DDS, owned roles, worker or native solver is linked or launched.
#include <iostream>
#include <nlohmann/json.hpp>
#include "task_time_profile_v1.hpp"

static usv_mpc::ReferenceInput reference(int points, double speed=.05) {
  usv_mpc::ReferenceInput x;
  x.path_stamp={100,0}; x.profile_stamp=x.path_stamp;
  for(int k=0;k<points;++k) {
    x.path.push_back({speed*(.2*k),0,0});
    x.profile.push_back({speed,0,0,.2*k});
  }
  return x;
}
static task_time_reference::Binding binding(uint64_t task) {
  return {{task,1,1,1,0},"run","boot",std::string(64,'a'),std::string(64,'b'),
          std::string(64,'c'),std::string(64,'d')};
}
static nlohmann::json facts(const task_time_reference::Epoch &e,
                            const task_time_reference::Proposal &p) {
  return {{"valid",p.valid},{"reason",p.reason},{"epoch_active",e.active()},
          {"epoch_terminal",e.terminal()},{"invalid_reason",e.invalid_reason()}};
}
int main() {
  const auto target=usv_mpc::Vector6d::Zero().eval();
  auto before=binding(2), after=binding(3);
  const auto full=reference(201), short_ref=reference(101);
  task_time_reference::Epoch fresh101;
  const auto p101=fresh101.propose(before,1000000000LL,target,short_ref);
  task_time_reference::Epoch e;
  const auto first=e.propose(before,1000000000LL,target,full);
  const bool committed=e.commit(first,1,1000);
  const auto changed_without_invalidation=e.propose(after,1200000000LL,target,full);
  // This is the exact invalidation call regulator_owned_execute.cpp:578 makes.
  e.invalidate_if_changed(after);
  const auto changed_full=e.propose(after,1200000000LL,target,full);
  const auto changed_short=e.propose(after,1200000000LL,target,short_ref);
  std::cout << nlohmann::json{
    {"first_201_proposal_valid",first.valid},{"first_commit",committed},
    {"fresh_101",facts(fresh101,p101)},
    {"active_epoch_changed_201_without_invalidation",{
       {"valid",changed_without_invalidation.valid},{"reason",changed_without_invalidation.reason}}},
    {"changed_201_after_regulator_invalidation",facts(e,changed_full)},
    {"changed_101_after_regulator_invalidation",facts(e,changed_short)}
  }.dump(2) << '\n';
}
