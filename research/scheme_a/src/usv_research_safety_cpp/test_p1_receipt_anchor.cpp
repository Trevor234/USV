// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// regulator 侧回执锚点：无回执不种子、bootstrap 必需、双通道原子、
// 断档失效、非 ok 不改 anchor、stop 截断幂等。
#include <gtest/gtest.h>

#include "p1_receipt_anchor.hpp"

namespace {

constexpr std::int64_t kOrigin = 5'000'000'000LL;

p1_receipt::ReceiptFacts bootstrap()
{
  p1_receipt::ReceiptFacts f;
  f.schema_version = "p1-plant-receipt-v3";
  f.run_id = "run";
  f.contract_hash = "contract";
  f.producer_instance_id = "plant-1";
  f.sequence = 0;
  f.tick = 0;
  f.disposition = "bootstrap";
  f.execution_index = 0;
  f.plant_steady_origin_ns = kOrigin;
  f.executed_begin_steady_ns = kOrigin;
  f.executed_end_steady_ns = kOrigin;
  f.hold_end_steady_ns = kOrigin;
  f.sim_ns = 0;
  f.state_sample_sim_ns = 0;
  f.planned_window_end_sim_ns = 0;
  f.clock_identity = p1_plant::kClockIdentity;
  f.clock_epoch = 0;
  return f;
}

p1_receipt::ReceiptFacts ok(std::uint64_t sequence, std::uint64_t index,
                           std::int64_t begin, std::array<double, 2> thrust)
{
  p1_receipt::ReceiptFacts f;
  f.schema_version = "p1-plant-receipt-v3";
  f.run_id = "run";
  f.contract_hash = "contract";
  f.producer_instance_id = "plant-1";
  f.sequence = sequence;
  f.tick = sequence;
  f.disposition = "ok";
  f.execution_index = index;
  f.thrust = thrust;
  f.executed_begin_steady_ns = begin;
  f.executed_end_steady_ns = begin + p1_plant::kTickNs;
  f.hold_end_steady_ns = begin + p1_plant::kTickNs;
  f.plant_steady_origin_ns = kOrigin;
  f.sim_ns = begin + p1_plant::kTickNs - kOrigin;
  f.state_sample_sim_ns = begin - kOrigin;
  f.planned_window_end_sim_ns = begin + p1_plant::kTickNs - kOrigin;
  f.clock_identity = p1_plant::kClockIdentity;
  f.clock_epoch = 0;
  return f;
}

p1_receipt::ReceiptAnchor started()
{
  p1_receipt::ReceiptAnchor anchor("p1-plant-receipt-v3", "run", "contract");
  const auto result = anchor.accept(bootstrap());
  EXPECT_TRUE(result.accepted);
  return anchor;
}

}  // namespace

// 没有回执时 anchor 必须是 unknown：空人口不能"通过"。
TEST(ReceiptAnchor, UnknownUntilFirstReceipt)
{
  p1_receipt::ReceiptAnchor anchor("p1-plant-receipt-v3", "run", "contract");
  EXPECT_FALSE(anchor.known());
  EXPECT_FALSE(anchor.normal_complete());
  EXPECT_TRUE(anchor.holds().empty());
  EXPECT_TRUE(anchor.publications().empty());
}

// 首条必须是 bootstrap：ok 先行说明没有可证明的零执行起点。
TEST(ReceiptAnchor, FirstReceiptMustBeBootstrap)
{
  p1_receipt::ReceiptAnchor anchor("p1-plant-receipt-v3", "run", "contract");
  const auto result = anchor.accept(ok(1, 1, kOrigin, {6.0, -3.0}));
  EXPECT_FALSE(result.accepted);
  EXPECT_EQ(result.reason, "bootstrap_required");
  EXPECT_FALSE(anchor.known());
}

TEST(ReceiptAnchor, SchemaAndForeignRunFailExplicitly)
{
  p1_receipt::ReceiptAnchor anchor("p1-plant-receipt-v3", "run", "contract");
  auto wrong_schema = bootstrap();
  wrong_schema.schema_version = "p1-plant-receipt-v2";
  EXPECT_EQ(anchor.accept(wrong_schema).reason, "schema");

  auto foreign = bootstrap();
  foreign.run_id = "other";
  EXPECT_EQ(anchor.accept(foreign).reason, "foreign_run");

  auto wrong_contract = bootstrap();
  wrong_contract.contract_hash = "other";
  EXPECT_EQ(anchor.accept(wrong_contract).reason, "foreign_contract");
}

// ok 回执一次性设置双通道 anchor（不存在"只更新一个通道"的中间态）。
TEST(ReceiptAnchor, OkSetsBothChannelsAtomically)
{
  auto anchor = started();
  const auto result = anchor.accept(ok(1, 1, kOrigin, {8.0, 12.0}));
  ASSERT_TRUE(result.accepted);
  EXPECT_TRUE(anchor.known());
  EXPECT_EQ(anchor.thrust()[0], 8.0);
  EXPECT_EQ(anchor.thrust()[1], 12.0);
  EXPECT_EQ(anchor.execution_index(), 1u);
  EXPECT_EQ(anchor.anchor_steady_ns(), kOrigin);
  EXPECT_EQ(anchor.hold_end_steady_ns(), kOrigin + p1_plant::kTickNs);
  EXPECT_EQ(anchor.publications().size(), 2u);  // 两个通道各一条
}

// 派生 hold 事件按真实执行区间闭合；相邻窗口不产生臆造的非零保持。
TEST(ReceiptAnchor, HeldEventsCloseAtRealIntervalEnd)
{
  auto anchor = started();
  ASSERT_TRUE(anchor.accept(ok(1, 1, kOrigin, {8.0, 12.0})).accepted);
  ASSERT_TRUE(anchor
                  .accept(ok(2, 2, kOrigin + p1_plant::kTickNs, {1.0, 2.0}))
                  .accepted);

  const auto events = anchor.held_events();
  // 两个窗口 × 2 通道 × (起点 + 零点) = 8 条；同一窗口内按通道成对出现。
  ASSERT_EQ(events.size(), 8u);
  EXPECT_EQ(events[0].steady_ns, kOrigin);
  EXPECT_EQ(events[0].channel, 0);
  EXPECT_DOUBLE_EQ(events[0].n, 8.0);
  EXPECT_EQ(events[1].steady_ns, kOrigin + p1_plant::kTickNs);
  EXPECT_EQ(events[1].channel, 0);
  EXPECT_DOUBLE_EQ(events[1].n, 0.0);
  EXPECT_EQ(events[2].steady_ns, kOrigin);
  EXPECT_EQ(events[2].channel, 1);
  EXPECT_DOUBLE_EQ(events[2].n, 12.0);
  EXPECT_EQ(events[3].steady_ns, kOrigin + p1_plant::kTickNs);
  EXPECT_DOUBLE_EQ(events[3].n, 0.0);
  // 第二个窗口从上一 hold 末端接续，零点被截断到该接续点。
  EXPECT_EQ(events[4].steady_ns, kOrigin + p1_plant::kTickNs);
  EXPECT_DOUBLE_EQ(events[4].n, 1.0);
  EXPECT_EQ(events[5].steady_ns, kOrigin + 2 * p1_plant::kTickNs);
  EXPECT_DOUBLE_EQ(events[5].n, 0.0);
}

// 重复与重排只计数，不推进 anchor。
TEST(ReceiptAnchor, DuplicateAndReorderedDoNotAdvance)
{
  auto anchor = started();
  ASSERT_TRUE(anchor.accept(ok(1, 1, kOrigin, {8.0, 12.0})).accepted);
  const auto before = anchor.anchor_steady_ns();

  const auto duplicate = anchor.accept(ok(1, 1, kOrigin, {99.0, 99.0}));
  EXPECT_EQ(duplicate.reason, "duplicate");
  EXPECT_EQ(anchor.duplicate_count(), 1u);
  const auto reordered = anchor.accept(ok(1, 1, kOrigin, {99.0, 99.0}));
  EXPECT_EQ(reordered.reason, "duplicate");
  EXPECT_EQ(anchor.thrust()[0], 8.0);
  EXPECT_EQ(anchor.anchor_steady_ns(), before);
}

// sequence 断档：锚点与历史必须失效，而不是静默续用旧值。
TEST(ReceiptAnchor, SequenceGapInvalidatesAnchorAndCompleteness)
{
  auto anchor = started();
  ASSERT_TRUE(anchor.accept(ok(1, 1, kOrigin, {8.0, 12.0})).accepted);
  const auto gap = anchor.accept(ok(4, 2, kOrigin + p1_plant::kTickNs, {1.0, 1.0}));
  EXPECT_FALSE(gap.accepted);
  EXPECT_EQ(gap.reason, "sequence_gap");
  EXPECT_FALSE(anchor.known());
  EXPECT_FALSE(anchor.normal_complete());
  EXPECT_TRUE(anchor.holds().empty());
}

// 非 ok 只推进 sequence，不动 anchor、不产生 hold。
TEST(ReceiptAnchor, NonOkAdvancesSequenceOnly)
{
  auto anchor = started();
  ASSERT_TRUE(anchor.accept(ok(1, 1, kOrigin, {8.0, 12.0})).accepted);
  auto late = ok(2, 2, kOrigin + p1_plant::kTickNs, {0.0, 0.0});
  late.disposition = "late";
  late.reason = "deadline_passed_before_execution";
  late.execution_index = 0;
  const auto result = anchor.accept(late);
  EXPECT_TRUE(result.accepted);
  EXPECT_TRUE(anchor.known());
  EXPECT_EQ(anchor.execution_index(), 1u);
  EXPECT_EQ(anchor.holds().size(), 1u);

  // 后续 ok 继续用连续的执行序号（2），而不是因为 late 而跳号。
  EXPECT_TRUE(anchor.accept(ok(3, 2, kOrigin + p1_plant::kTickNs, {1.0, 1.0})).accepted);
}

// ok 的结构性要求：执行序号必须连续、hold 末端必须在网格上、
// sim 必须由唯一原点派生。
TEST(ReceiptAnchor, StructuralMismatchInvalidates)
{
  auto anchor = started();
  auto skipped_index = ok(1, 5, kOrigin, {8.0, 12.0});
  EXPECT_EQ(anchor.accept(skipped_index).reason, "execution_index_gap");

  anchor = started();
  auto off_grid = ok(1, 1, kOrigin, {8.0, 12.0});
  off_grid.hold_end_steady_ns += 1;
  EXPECT_EQ(anchor.accept(off_grid).reason, "hold_end_off_grid");

  anchor = started();
  auto wrong_sim = ok(1, 1, kOrigin, {8.0, 12.0});
  wrong_sim.sim_ns += 1;
  EXPECT_EQ(anchor.accept(wrong_sim).reason, "sim_not_derived_from_origin");

  anchor = started();
  auto empty_window = ok(1, 1, kOrigin, {8.0, 12.0});
  empty_window.executed_end_steady_ns = empty_window.executed_begin_steady_ns;
  EXPECT_EQ(anchor.accept(empty_window).reason, "execution_window_invalid");

  anchor = started();
  auto wrong_sample = ok(1, 1, kOrigin, {8.0, 12.0});
  wrong_sample.state_sample_sim_ns += 1000;
  EXPECT_EQ(anchor.accept(wrong_sample).reason, "state_sample_sim_mismatch");

  anchor = started();
  auto wrong_planned = ok(1, 1, kOrigin, {8.0, 12.0});
  wrong_planned.planned_window_end_sim_ns += 1000;
  EXPECT_EQ(anchor.accept(wrong_planned).reason, "planned_end_sim_mismatch");

  anchor = started();
  auto changed_clock = ok(1, 1, kOrigin, {8.0, 12.0});
  changed_clock.clock_identity = "foreign_clock";
  EXPECT_EQ(anchor.accept(changed_clock).reason, "clock_identity_changed");
}

// producer 变化 = 新的 plant 实例：清空并置 unknown。
TEST(ReceiptAnchor, ProducerChangeClearsAnchor)
{
  auto anchor = started();
  ASSERT_TRUE(anchor.accept(ok(1, 1, kOrigin, {8.0, 12.0})).accepted);
  auto other = ok(2, 2, kOrigin + p1_plant::kTickNs, {1.0, 1.0});
  other.producer_instance_id = "plant-2";
  const auto result = anchor.accept(other);
  EXPECT_EQ(result.reason, "producer_changed");
  EXPECT_FALSE(anchor.known());
  EXPECT_FALSE(anchor.normal_complete());
}

// stop 截断：把最后一个 hold 截到 close；重复调用幂等。
TEST(ReceiptAnchor, StopTruncationIsIdempotent)
{
  auto anchor = started();
  ASSERT_TRUE(anchor.accept(ok(1, 1, kOrigin, {8.0, 12.0})).accepted);
  const auto original_end = anchor.holds().back().end_ns;
  const auto close = original_end - 50'000'000;

  EXPECT_TRUE(anchor.close_at(close));
  EXPECT_EQ(anchor.holds().back().end_ns, close);
  EXPECT_EQ(anchor.hold_end_steady_ns(), close);
  // 幂等：同样的 close 不再改动，更晚的 close 被忽略。
  EXPECT_FALSE(anchor.close_at(close));
  EXPECT_FALSE(anchor.close_at(original_end));
  EXPECT_EQ(anchor.holds().back().end_ns, close);
}

// 发布历史与 anchor 必须一致（检查器 guard_on_source 的判据来源）。
TEST(ReceiptAnchor, PublicationsMatchAnchorHistory)
{
  auto anchor = started();
  ASSERT_TRUE(anchor.accept(ok(1, 1, kOrigin, {8.0, 12.0})).accepted);
  ASSERT_TRUE(anchor
                  .accept(ok(2, 2, kOrigin + p1_plant::kTickNs, {2.0, 3.0}))
                  .accepted);
  ASSERT_EQ(anchor.publications().size(), 4u);
  for (const auto & publication : anchor.publications())
  {
    EXPECT_TRUE(publication.known);
    EXPECT_GT(publication.sequence, 0u);
  }
  EXPECT_EQ(anchor.publications().back().sequence, anchor.execution_index());
  EXPECT_EQ(anchor.publications().back().publish_ns, anchor.anchor_steady_ns());
}
