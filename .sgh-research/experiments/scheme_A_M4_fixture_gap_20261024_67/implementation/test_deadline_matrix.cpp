// Deterministic contract cases. No ROS init, solver, endpoint, or actuator API.
#include <gtest/gtest.h>
#include "p1_admission.hpp"

namespace {
p1::Ticket ticket() {
  p1::Ticket t;
  t.id=1;t.target=2;t.origin=1000000000;t.deadline=1150000000;
  t.target_ns=1200000000;t.version={1,1,1,1,0};
  return t;
}
void check_ready(int64_t offset, bool expected) {
  auto t=ticket();p1::Admission admission;
  const auto reason=admission.register_ready(t,1,t.origin+offset,t.version);
  EXPECT_EQ(reason,expected?"":"late");
  if(expected) {
    EXPECT_TRUE(admission.finalize_ready(t.id,t.origin+offset));
    EXPECT_FALSE(admission.take(2,1199999999));
    const auto accepted=admission.take(2,1200000000);
    ASSERT_TRUE(accepted);
    EXPECT_EQ(accepted->deadline,1150000000);
    EXPECT_EQ(accepted->target_ns,1200000000);
    EXPECT_FALSE(admission.take(2,1200000000));
  } else {
    EXPECT_EQ(admission.slots(),0u);
    EXPECT_FALSE(admission.take(2,1400000000));
  }
}
}
TEST(DeadlineMatrix, Ready50msKeepsOriginal200msTarget) {check_ready(50000000,true);}
TEST(DeadlineMatrix, Ready150msEqualityIsAllowed) {check_ready(150000000,true);}
TEST(DeadlineMatrix, Ready150msPlusOneNanosecondIsLate) {check_ready(150000001,false);}
TEST(DeadlineMatrix, Ready250msIsNotRescheduled) {check_ready(250000000,false);}
TEST(DeadlineMatrix, Ready400msIsNotRescheduled) {check_ready(400000000,false);}
TEST(DeadlineMatrix, ExtendingDeadlineIsAContractFailure) {
  auto t=ticket();t.deadline=1250000000;p1::Admission a;
  EXPECT_EQ(a.register_ready(t,1,1050000000,t.version),"time_contract");
  EXPECT_EQ(a.slots(),0u);
}
TEST(DeadlineMatrix, ExtendingTargetIsAContractFailure) {
  auto t=ticket();t.target_ns=1400000000;p1::Admission a;
  EXPECT_EQ(a.register_ready(t,1,1050000000,t.version),"time_contract");
  EXPECT_EQ(a.slots(),0u);
}
