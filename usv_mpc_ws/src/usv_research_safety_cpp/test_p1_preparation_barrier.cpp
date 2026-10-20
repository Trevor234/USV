#include <gtest/gtest.h>
#include "p1_preparation_barrier.hpp"

TEST(PreparationBarrier, DisabledDefault) {
  p1::PreparationBarrier b(0, "execute", false);
  for (int i=0; i<20; ++i) EXPECT_FALSE(b.take());
}
TEST(PreparationBarrier, ThirdTakeOnly) {
  p1::PreparationBarrier b(3000, "no_output", true);
  EXPECT_EQ(b.milliseconds(), 3000); EXPECT_FALSE(b.take()); EXPECT_FALSE(b.take());
  EXPECT_TRUE(b.take()); for (int i=0; i<20; ++i) EXPECT_FALSE(b.take());
}
TEST(PreparationBarrier, RejectNegative) {
  EXPECT_THROW(p1::PreparationBarrier(-1, "no_output", true), std::runtime_error);
}
TEST(PreparationBarrier, RejectBeyondFiniteBound) {
  EXPECT_THROW(p1::PreparationBarrier(3001, "no_output", true), std::runtime_error);
}
TEST(PreparationBarrier, RejectExecute) {
  EXPECT_THROW(p1::PreparationBarrier(1, "execute", true), std::runtime_error);
}
TEST(PreparationBarrier, RejectShadow) {
  EXPECT_THROW(p1::PreparationBarrier(1, "shadow", true), std::runtime_error);
}
TEST(PreparationBarrier, RejectDisabledFaultContract) {
  EXPECT_THROW(p1::PreparationBarrier(1, "no_output", false), std::runtime_error);
}
