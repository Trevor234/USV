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
// 新准入矩阵：no_output 单独即可（诊断模式），受控仿真必须带合同故障开关，
// execute/shadow 一律拒绝。
TEST(PreparationBarrier, AdmissionMatrix) {
  EXPECT_NO_THROW(p1::PreparationBarrier(1, "no_output", false));
  EXPECT_THROW(p1::PreparationBarrier(1, "controlled_sim", false), std::runtime_error);
  EXPECT_NO_THROW(p1::PreparationBarrier(1, "controlled_sim", true));
  EXPECT_THROW(p1::PreparationBarrier(1, "execute", true), std::runtime_error);
  EXPECT_THROW(p1::PreparationBarrier(1, "shadow", true), std::runtime_error);
}

// 受控仿真在合同启用故障注入时被允许；未启用仍然拒绝。
TEST(PreparationBarrier, ControlledSimNeedsTheContractFaultFlag) {
  EXPECT_THROW(p1::PreparationBarrier(1, "controlled_sim", false), std::runtime_error);
  p1::PreparationBarrier b(3000, "controlled_sim", true);
  EXPECT_FALSE(b.take()); EXPECT_FALSE(b.take()); EXPECT_TRUE(b.take());
}
// ordinal 是构造参数（默认 3），不是写死的第三次。
TEST(PreparationBarrier, OrdinalIsAConstructorParameter) {
  p1::PreparationBarrier b(1, "no_output", true, 1);
  EXPECT_TRUE(b.take());
  EXPECT_FALSE(b.take());
}
