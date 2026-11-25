#include <gtest/gtest.h>
#include "p1_tick_barrier.hpp"
#include "p1_admission.hpp"
TEST(TickBarrier, DisabledInEveryMode) {
  for(const auto & mode:{"no_output","shadow","execute"}) {
    p1::TickBarrier b(0,mode,false);
    for(int i=0;i<10;++i)EXPECT_FALSE(b.take());
  }
}
TEST(TickBarrier, DiagnosticModeAndFaultPermissionRequired) {
  EXPECT_THROW(p1::TickBarrier(610,"shadow",true),std::runtime_error);
  EXPECT_THROW(p1::TickBarrier(610,"execute",true),std::runtime_error);
  // 新矩阵：no_output 是诊断模式，不需要故障开关；受控仿真则必须带。
  EXPECT_NO_THROW(p1::TickBarrier(610,"no_output",false));
  EXPECT_THROW(p1::TickBarrier(610,"controlled_sim",false),std::runtime_error);
}
TEST(TickBarrier, FiniteInclusiveBounds) {
  EXPECT_THROW(p1::TickBarrier(-1,"no_output",true),std::runtime_error);
  EXPECT_THROW(p1::TickBarrier(3001,"no_output",true),std::runtime_error);
  for(int64_t ms:{1,610,3000}) {
    p1::TickBarrier b(ms,"no_output",true);
    EXPECT_EQ(b.milliseconds(),ms);
  }
}
TEST(TickBarrier, OneShotOnThirdAttempt) {
  p1::TickBarrier b(610,"no_output",true);
  EXPECT_FALSE(b.take());
  EXPECT_FALSE(b.take());
  EXPECT_TRUE(b.take());
  for(int i=0;i<20;++i)EXPECT_FALSE(b.take());
}
TEST(SchedulerBoundary, ExactAndAdjacentDueTicks) {
  const int64_t origin=1000000000;
  EXPECT_EQ(p1::due_tick(origin,origin-1),0u);
  EXPECT_EQ(p1::due_tick(origin,origin),0u);
  for(uint64_t i:{1,2,5}) {
    auto due=origin+i*p1::T;
    EXPECT_EQ(p1::due_tick(origin,due-1),i-1);
    EXPECT_EQ(p1::due_tick(origin,due),i);
    EXPECT_EQ(p1::due_tick(origin,due+1),i);
  }
}

// 受控仿真 + 合同故障开关：允许；缺任一：拒绝。
TEST(TickBarrier, ControlledSimAdmissionMatrix) {
  EXPECT_THROW(p1::TickBarrier(610,"controlled_sim",false),std::runtime_error);
  EXPECT_THROW(p1::TickBarrier(610,"shadow",true),std::runtime_error);
  EXPECT_THROW(p1::TickBarrier(610,"execute",true),std::runtime_error);
  EXPECT_NO_THROW(p1::TickBarrier(610,"controlled_sim",true));
}
TEST(TickBarrier, OrdinalIsAConstructorParameter) {
  p1::TickBarrier b(610,"no_output",true,2);
  EXPECT_FALSE(b.take());
  EXPECT_TRUE(b.take());
  EXPECT_FALSE(b.take());
}
