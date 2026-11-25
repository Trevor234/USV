// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// plant 执行准入：12 步固定顺序、词表原因、同 tick 唯一执行、窗口不重叠。
// 纯函数，`now` 由调用方给，所以没有任何睡等或墙钟依赖。
#include <gtest/gtest.h>

#include "plant/p1_plant_admission.hpp"

namespace {

constexpr std::int64_t kBegin = 10'000'000'000LL;

p1_plant::GateContext context()
{
  p1_plant::GateContext c;
  c.run_id = "run";
  c.boot_id = "boot";
  c.contract_hash = "contract";
  return c;
}

p1_plant::CommandView command(std::uint64_t sequence, std::uint64_t tick,
                              std::int64_t begin = kBegin)
{
  p1_plant::CommandView v;
  v.schema_version = "p1-plant-command-v2";
  v.run_id = "run";
  v.boot_id = "boot";
  v.contract_hash = "contract";
  v.sequence = sequence;
  v.tick = tick;
  v.apply_begin_steady_ns = begin;
  v.apply_end_steady_ns = begin + p1_plant::kTickNs;
  v.deadline_steady_ns = begin + p1_plant::kDeadlineNs;
  v.thrust = {6.0, -3.0};
  v.task_generation = 1;
  v.model_generation = 1;
  v.config_generation = 1;
  v.schedule_generation = 1;
  v.clock_epoch = 0;
  return v;
}

}  // namespace

TEST(PlantAdmission, FreshCommandIsOk)
{
  auto state = p1_plant::PlantGateState{};
  const auto result = p1_plant::classify(command(1, 1), context(), state, kBegin);
  EXPECT_EQ(result.disposition, "ok");
  EXPECT_TRUE(result.executes);
  EXPECT_TRUE(result.reason.empty());
}

TEST(PlantAdmission, SchemaAndForeignRunAreRejectedFirst)
{
  auto state = p1_plant::PlantGateState{};
  auto bad_schema = command(1, 1);
  bad_schema.schema_version = "p1-plant-command-v1";
  auto result = p1_plant::classify(bad_schema, context(), state, kBegin);
  EXPECT_EQ(result.disposition, "rejected");
  EXPECT_EQ(result.reason, "schema");

  auto foreign = command(1, 1);
  foreign.run_id = "other";
  result = p1_plant::classify(foreign, context(), state, kBegin);
  EXPECT_EQ(result.reason, "foreign_run");
}

TEST(PlantAdmission, DuplicateAndReorderedAreDistinct)
{
  auto state = p1_plant::PlantGateState{};
  ASSERT_TRUE(p1_plant::classify(command(1, 1), context(), state, kBegin).executes);
  state.note_sequence(1);

  // 同一 sequence 再发一次：duplicate（不是 reordered）
  const auto dup = p1_plant::classify(command(1, 1), context(), state, kBegin);
  EXPECT_EQ(dup.disposition, "duplicate");
  EXPECT_EQ(dup.reason, "same_sequence");
  // 更旧的 sequence：reordered
  EXPECT_EQ(p1_plant::classify(command(0, 1), context(), state, kBegin).reason,
            "reordered");
}

TEST(PlantAdmission, InvalidWindowLengthAndNegativeBegin)
{
  auto state = p1_plant::PlantGateState{};
  auto short_window = command(1, 1);
  short_window.apply_end_steady_ns = short_window.apply_begin_steady_ns + 1000;
  EXPECT_EQ(p1_plant::classify(short_window, context(), state, kBegin).reason,
            "invalid_window");

  auto negative = command(1, 1, -1);
  EXPECT_EQ(p1_plant::classify(negative, context(), state, kBegin).reason,
            "invalid_window");
}

TEST(PlantAdmission, LateByDeadlineAndLateByClosedWindowAreDifferentReasons)
{
  auto state = p1_plant::PlantGateState{};
  auto v = command(1, 1);
  // 恰好等于 deadline 不算迟到。
  EXPECT_TRUE(p1_plant::classify(v, context(), state, v.deadline_steady_ns).executes);
  // 超过 deadline：deadline_passed_before_execution
  auto late_deadline =
      p1_plant::classify(v, context(), state, v.deadline_steady_ns + 1);
  EXPECT_EQ(late_deadline.disposition, "late");
  EXPECT_EQ(late_deadline.reason, "deadline_passed_before_execution");

  // 窗口已关闭：window_closed（deadline 放宽到窗口之外）
  auto wide = command(2, 2);
  wide.deadline_steady_ns = wide.apply_end_steady_ns + 1'000'000'000LL;
  auto late_window = p1_plant::classify(wide, context(), state,
                                        wide.apply_end_steady_ns);
  EXPECT_EQ(late_window.disposition, "late");
  EXPECT_EQ(late_window.reason, "window_closed");
}

TEST(PlantAdmission, ThrustRangeAndNonFinite)
{
  auto state = p1_plant::PlantGateState{};
  auto over = command(1, 1);
  over.thrust = {25.5, 0.0};
  EXPECT_EQ(p1_plant::classify(over, context(), state, kBegin).reason, "thrust_range");

  auto nan_command = command(2, 2);
  nan_command.thrust = {std::nan(""), 0.0};
  EXPECT_EQ(p1_plant::classify(nan_command, context(), state, kBegin).reason,
            "thrust_range");

  auto low = command(3, 3);
  low.thrust = {-25.0, 25.0};
  EXPECT_TRUE(p1_plant::classify(low, context(), state, kBegin).executes);
}

TEST(PlantAdmission, SameTickCannotExecuteTwice)
{
  auto state = p1_plant::PlantGateState{};
  state.note_executed_tick(7);
  EXPECT_EQ(p1_plant::classify(command(2, 7), context(), state, kBegin).reason,
            "tick_already_executed");
}

// 只要槽位里有未执行的窗口就拒绝：占用方可能是别的生产者（注入器），
// 允许通过会把它覆盖掉，等于静默丢命令。
TEST(PlantAdmission, PendingCommandBlocksSecondSchedule)
{
  auto state = p1_plant::PlantGateState{};
  state.pending_scheduled = true;
  EXPECT_EQ(p1_plant::classify(command(1, 1), context(), state, kBegin).reason,
            "command_pending");
}

TEST(PlantAdmission, OverlappingWindowIsRejected)
{
  auto state = p1_plant::PlantGateState{};
  state.open_hold_end_steady_ns = kBegin + p1_plant::kTickNs;
  // 起点早于已有 hold 末端 → window_overlap
  EXPECT_EQ(p1_plant::classify(command(1, 1, kBegin + 1000), context(), state,
                               kBegin + 1000)
                .reason,
            "window_overlap");
  // 起点正好落在 hold 末端 → 合法接续
  EXPECT_TRUE(p1_plant::classify(command(2, 2, kBegin + p1_plant::kTickNs), context(),
                                 state, kBegin + p1_plant::kTickNs)
                  .executes);
}

TEST(PlantAdmission, ReasonVocabularyIsClosed)
{
  const char * allowed[] = {"", "schema", "foreign_run", "same_sequence", "reordered",
                            "invalid_window", "deadline_passed_before_execution",
                            "window_closed", "thrust_range", "tick_already_executed",
                            "command_pending", "window_overlap"};
  auto state = p1_plant::PlantGateState{};
  const auto result = p1_plant::classify(command(1, 1), context(), state, kBegin);
  bool found = false;
  for (const char * reason : allowed)
    if (result.reason == reason) found = true;
  EXPECT_TRUE(found);

  const char * dispositions[] = {"ok", "rejected", "late", "duplicate"};
  found = false;
  for (const char * disposition : dispositions)
    if (result.disposition == disposition) found = true;
  EXPECT_TRUE(found);
}
