#include <gtest/gtest.h>
#include <limits>
#include "p1_capability_lease.hpp"
TEST(CapabilityLease, NoLeaseBeforeFirstValidReceipt) {
  p1::CapabilityLease l(600000000);EXPECT_TRUE(l.check(1000000000).empty());EXPECT_EQ(l.last_valid_ns(),0);
}
TEST(CapabilityLease, ExactDeadlineAllowed) {
  p1::CapabilityLease l(600000000);ASSERT_TRUE(l.renew(1000000000));EXPECT_TRUE(l.check(1600000000).empty());
}
TEST(CapabilityLease, BeyondDeadlineTerminal) {
  p1::CapabilityLease l(600000000);ASSERT_TRUE(l.renew(1000000000));EXPECT_EQ(l.check(1600000001),"worker_capability_expired");
}
TEST(CapabilityLease, LateReceiptCannotHideExpiration) {
  p1::CapabilityLease l(600000000);ASSERT_TRUE(l.renew(1000000000));EXPECT_FALSE(l.renew(1600000001));EXPECT_EQ(l.last_valid_ns(),1000000000);
}
TEST(CapabilityLease, ExactDeadlineCanRenew) {
  p1::CapabilityLease l(600000000);ASSERT_TRUE(l.renew(1000000000));EXPECT_TRUE(l.renew(1600000000));EXPECT_TRUE(l.check(2200000000).empty());
}
TEST(CapabilityLease, FreshReceiptExtends) {
  p1::CapabilityLease l(600000000);ASSERT_TRUE(l.renew(1000000000));ASSERT_TRUE(l.renew(1200000000));EXPECT_TRUE(l.check(1800000000).empty());
}
TEST(CapabilityLease, IgnoredReceiptDoesNotExtend) {
  p1::CapabilityLease l(600000000);ASSERT_TRUE(l.renew(1000000000));EXPECT_TRUE(l.check(1500000000).empty());EXPECT_EQ(l.check(1600000001),"worker_capability_expired");
}
TEST(CapabilityLease, TerminalCannotResume) {
  p1::CapabilityLease l(600000000);ASSERT_TRUE(l.renew(1000000000));ASSERT_FALSE(l.check(1600000001).empty());EXPECT_FALSE(l.renew(2000000000));EXPECT_EQ(l.last_valid_ns(),1000000000);
}
TEST(CapabilityLease, BackwardClockTerminal) {
  p1::CapabilityLease l(600000000);ASSERT_TRUE(l.renew(1000000000));EXPECT_EQ(l.check(999999999),"worker_capability_clock_invalid");EXPECT_FALSE(l.renew(1100000000));
}
TEST(CapabilityLease, ZeroClockRejected) {
  p1::CapabilityLease l(600000000);EXPECT_FALSE(l.renew(0));
}
TEST(CapabilityLease, NegativeClockRejected) {
  p1::CapabilityLease l(600000000);EXPECT_FALSE(l.renew(-1));
}
TEST(CapabilityLease, RejectTooShort) {
  EXPECT_THROW(p1::CapabilityLease(199999999),std::runtime_error);
}
TEST(CapabilityLease, RejectUnbounded) {
  EXPECT_THROW(p1::CapabilityLease(5000000001),std::runtime_error);
}
TEST(CapabilityLease, LongMonotonicUptimeSafe) {
  p1::CapabilityLease l(600000000);ASSERT_TRUE(l.renew(std::numeric_limits<int64_t>::max()-600000000));EXPECT_TRUE(l.check(std::numeric_limits<int64_t>::max()).empty());
}
