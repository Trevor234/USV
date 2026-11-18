// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// p1_receipt_anchor.hpp —— regulator 侧的回执锚点（纯值，无 ROS）。
//
// 3.2/3.5 的根因之一是 regulator 用**自己的意图**当下一拍的锚点，并用
// plant 的回显 sim_ns 造历史。这里把唯一合法来源固定为 plant 的 ok 回执：
//   * 首条必须是 bootstrap（否则没有任何"零执行"起点可证明）；
//   * sequence 必须连续，断档即清空并标记 normal_complete=false；
//   * 只有 ok 回执才推进 anchor，且双通道**一次性**设置（不得半更新）；
//   * hold 事件序列按真实执行区间闭合，缺口内为零推力。
#pragma once

#include <array>
#include <cstdint>
#include <deque>
#include <string>

#include "p1_plant_core.hpp"

namespace p1_receipt
{

/// 一条 ok 回执里锚点真正需要的事实。
struct ReceiptFacts
{
  std::string schema_version;
  std::string run_id;
  std::string contract_hash;
  std::string producer_instance_id;
  std::uint64_t sequence = 0;
  std::uint64_t tick = 0;
  std::string disposition;
  std::string reason;
  std::uint64_t execution_index = 0;
  std::array<double, 2> thrust{0.0, 0.0};
  std::int64_t executed_begin_steady_ns = 0;
  std::int64_t executed_end_steady_ns = 0;
  std::int64_t hold_end_steady_ns = 0;
  std::int64_t plant_steady_origin_ns = 0;
  std::int64_t sim_ns = 0;
  std::int64_t state_sample_sim_ns = 0;
  std::int64_t planned_window_end_sim_ns = 0;
  std::string clock_identity;
  std::uint64_t clock_epoch = 0;
  std::array<double, 6> state{};
};

/// 一个已闭合的 hold 区间（供 held-history 使用）。
struct HoldRecord
{
  std::int64_t begin_ns = 0;
  std::int64_t end_ns = 0;
  std::array<double, 2> thrust{0.0, 0.0};
  std::uint64_t execution_index = 0;
};

/// 一个双通道发布事件：anchor 的可审计历史。
struct PublicationEvent
{
  int channel = 0;
  std::uint64_t sequence = 0;
  std::int64_t publish_ns = 0;
  double n = 0.0;
  bool known = false;
};

/// 通道化的 held-input 事件（与 usv_mpc::HeldInputEvent 同形，避免耦合）。
/// steady_ns 是 **plant 的 CLOCK_MONOTONIC 稳态时刻**，与仿真时间差一个唯一原点；
/// 消费方必须减去 steady_origin_ns() 才得到仿真时刻（列名写清以免再混用）。
struct HeldEvent
{
  std::int64_t steady_ns = 0;
  std::uint8_t channel = 0;
  double n = 0.0;
};

/// 准入结论：显式成功/失败，不靠"没报错就算成功"。
struct AdmissionResult
{
  bool accepted = false;
  bool complete = false;      // 该 sequence 的对账链是否仍然连续
  std::string reason;
};

class ReceiptAnchor
{
public:
  static constexpr std::size_t kHistoryCapacity = 256;
  static constexpr std::int64_t kTickNs = p1_plant::kTickNs;

  explicit ReceiptAnchor(std::string schema_version = "p1-plant-receipt-v3",
                         std::string expected_run_id = "",
                         std::string expected_contract_hash = "")
      : schema_version_(std::move(schema_version)),
        expected_run_id_(std::move(expected_run_id)),
        expected_contract_hash_(std::move(expected_contract_hash)) {}

  /// 从未见过任何回执时必须是 unknown —— 空集上的 all() 不是证明。
  bool known() const { return known_; }
  const std::array<double, 2> & thrust() const { return anchor_thrust_; }
  std::uint64_t execution_index() const { return execution_index_; }
  std::int64_t anchor_steady_ns() const { return anchor_steady_ns_; }
  std::int64_t hold_end_steady_ns() const { return hold_end_steady_ns_; }
  std::int64_t sim_ns() const { return sim_ns_; }
  /// plant 的唯一时间原点（0 = 尚未 bootstrap）。
  std::int64_t steady_origin_ns() const { return bootstrap_origin_ns_; }
  bool normal_complete() const { return normal_complete_; }
  std::size_t duplicate_count() const { return duplicate_count_; }
  std::size_t reordered_count() const { return reordered_count_; }
  const std::deque<HoldRecord> & holds() const { return holds_; }
  const std::deque<PublicationEvent> & publications() const { return publications_; }
  const std::deque<std::uint64_t> & job_history() const { return job_history_; }

  /// 接受一条回执。规则：schema/foreign_run 显式失败；producer 变化清空；
  /// 首条必须 bootstrap；sequence 必须连续；非 ok 只推进 sequence。
  AdmissionResult accept(const ReceiptFacts & facts)
  {
    AdmissionResult result;
    if (facts.schema_version != schema_version_)
    {
      result.reason = "schema";
      return result;
    }
    if (facts.clock_identity.empty())
    {
      result.reason = "clock_identity_missing";
      return result;
    }
    if (!expected_run_id_.empty() && facts.run_id != expected_run_id_)
    {
      result.reason = "foreign_run";
      return result;
    }
    if (!expected_contract_hash_.empty() &&
        facts.contract_hash != expected_contract_hash_)
    {
      result.reason = "foreign_contract";
      return result;
    }
    if (!producer_instance_id_.empty() &&
        facts.producer_instance_id != producer_instance_id_)
    {
      reset();
      producer_instance_id_ = facts.producer_instance_id;
      result.reason = "producer_changed";
      return result;
    }
    producer_instance_id_ = facts.producer_instance_id;

    if (!started_)
    {
      if (facts.disposition != "bootstrap" || facts.sequence != 0)
      {
        result.reason = "bootstrap_required";
        return result;
      }
      started_ = true;
      last_sequence_ = 0;
      bootstrap_origin_ns_ = facts.plant_steady_origin_ns;
      if (bootstrap_origin_ns_ <= 0)
      {
        normal_complete_ = false;
        result.reason = "bootstrap_origin_missing";
        return result;
      }
      if (facts.state_sample_sim_ns != 0)
      {
        normal_complete_ = false;
        result.reason = "bootstrap_state_sample_sim_invalid";
        return result;
      }
      if (facts.planned_window_end_sim_ns != 0)
      {
        normal_complete_ = false;
        result.reason = "bootstrap_planned_end_invalid";
        return result;
      }
      bootstrap_clock_identity_ = facts.clock_identity;
      // bootstrap 本身就是"零执行起点"：双通道 anchor 一次性置到原点。
      anchor_thrust_ = {0.0, 0.0};
      anchor_steady_ns_ = facts.executed_begin_steady_ns > 0
                              ? facts.executed_begin_steady_ns
                              : bootstrap_origin_ns_;
      hold_end_steady_ns_ = anchor_steady_ns_;
      execution_index_ = 0;
      sim_ns_ = 0;
      known_ = true;
      normal_complete_ = true;
      result.accepted = true;
      result.complete = normal_complete_;
      return result;
    }

    if (facts.sequence == last_sequence_)
    {
      ++duplicate_count_;
      last_sequence_ = facts.sequence;
      result.reason = "duplicate";
      result.complete = normal_complete_;
      return result;
    }
    if (facts.sequence < last_sequence_)
    {
      ++reordered_count_;
      result.reason = "reordered";
      result.complete = normal_complete_;
      return result;
    }
    if (facts.sequence != last_sequence_ + 1)
    {
      // 断档：锚点与历史全部失效，且**不得**静默续用旧值。
      reset();
      normal_complete_ = false;
      result.reason = "sequence_gap";
      result.complete = false;
      return result;
    }
    last_sequence_ = facts.sequence;

    if (facts.disposition != "ok")
    {
      // 非 ok 只推进 sequence：不动 anchor、不产生 hold、不进执行历史。
      result.accepted = true;
      result.complete = normal_complete_;
      return result;
    }

    // ok 的结构要求：执行序号连续、区间非空、hold 末端正好一个周期、
    // sim 与唯一原点一致。任何一条不满足都是"不可用的执行事实"。
    if (facts.execution_index != execution_index_ + 1)
    {
      reset();
      normal_complete_ = false;
      result.reason = "execution_index_gap";
      return result;
    }
    if (facts.executed_end_steady_ns <= facts.executed_begin_steady_ns ||
        facts.executed_end_steady_ns - facts.executed_begin_steady_ns > kTickNs)
    {
      reset();
      normal_complete_ = false;
      result.reason = "execution_window_invalid";
      return result;
    }
    if (facts.hold_end_steady_ns != facts.executed_begin_steady_ns + kTickNs)
    {
      reset();
      normal_complete_ = false;
      result.reason = "hold_end_off_grid";
      return result;
    }
    if (facts.plant_steady_origin_ns != bootstrap_origin_ns_)
    {
      reset();
      normal_complete_ = false;
      result.reason = "steady_origin_changed";
      return result;
    }
    if (facts.clock_identity != bootstrap_clock_identity_)
    {
      reset();
      normal_complete_ = false;
      result.reason = "clock_identity_changed";
      return result;
    }
    if (facts.sim_ns != facts.executed_end_steady_ns - bootstrap_origin_ns_)
    {
      reset();
      normal_complete_ = false;
      result.reason = "sim_not_derived_from_origin";
      return result;
    }
    if (facts.state_sample_sim_ns != facts.executed_begin_steady_ns - bootstrap_origin_ns_)
    {
      reset();
      normal_complete_ = false;
      result.reason = "state_sample_sim_mismatch";
      return result;
    }
    if (facts.planned_window_end_sim_ns != facts.hold_end_steady_ns - bootstrap_origin_ns_)
    {
      reset();
      normal_complete_ = false;
      result.reason = "planned_end_sim_mismatch";
      return result;
    }

    // 双通道一次性设置（在同一个不可分割的提交里）。
    anchor_thrust_ = facts.thrust;
    anchor_steady_ns_ = facts.executed_begin_steady_ns;
    hold_end_steady_ns_ = facts.hold_end_steady_ns;
    execution_index_ = facts.execution_index;
    sim_ns_ = facts.sim_ns;
    known_ = true;

    holds_.push_back(HoldRecord{facts.executed_begin_steady_ns,
                                facts.hold_end_steady_ns, facts.thrust,
                                facts.execution_index});
    while (holds_.size() > kHistoryCapacity) holds_.pop_front();
    push_publication(facts.execution_index, facts.executed_begin_steady_ns,
                     facts.thrust[0], 0);
    push_publication(facts.execution_index, facts.executed_begin_steady_ns,
                     facts.thrust[1], 1);
    job_history_.push_back(facts.tick);
    while (job_history_.size() > kHistoryCapacity) job_history_.pop_front();

    result.accepted = true;
    result.complete = normal_complete_;
    return result;
  }

  /// hold 事件序列：每个窗口给 {begin, n}，并在窗口末端给 {end, 0}
  /// （若下一窗口紧接着开始，则把零推力事件截断到 next_begin）。
  std::deque<HeldEvent> held_events() const
  {
    std::deque<HeldEvent> events;
    for (std::size_t i = 0; i < holds_.size(); ++i)
    {
      const auto & hold = holds_[i];
      for (int channel = 0; channel < 2; ++channel)
      {
        events.push_back({hold.begin_ns, static_cast<std::uint8_t>(channel),
                          hold.thrust[static_cast<std::size_t>(channel)]});
        std::int64_t zero_at = hold.end_ns;
        if (i + 1 < holds_.size() && holds_[i + 1].begin_ns < zero_at)
          zero_at = holds_[i + 1].begin_ns;
        events.push_back({zero_at, static_cast<std::uint8_t>(channel), 0.0});
      }
    }
    return events;
  }

  /// 清空：任何不确定事实都回到 unknown，而不是保留半套锚点。
  void reset()
  {
    known_ = false;
    started_ = false;
    normal_complete_ = false;
    anchor_thrust_ = {0.0, 0.0};
    anchor_steady_ns_ = 0;
    hold_end_steady_ns_ = 0;
    execution_index_ = 0;
    sim_ns_ = 0;
    last_sequence_ = 0;
    bootstrap_origin_ns_ = 0;
    bootstrap_clock_identity_.clear();
    holds_.clear();
    publications_.clear();
    job_history_.clear();
  }

  /// 重新开始一条已经完整断掉的对账链（新的 producer 或新的运行）。
  void restart(const std::string & producer_instance_id)
  {
    reset();
    producer_instance_id_ = producer_instance_id;
    normal_complete_ = true;
  }

  /// stop 截断：把最后一个 hold 截到 close，且幂等（重复调用不再改）。
  bool close_at(std::int64_t close_steady_ns)
  {
    if (holds_.empty()) return false;
    auto & last = holds_.back();
    if (close_steady_ns >= last.end_ns) return false;
    if (close_steady_ns <= last.begin_ns) return false;
    last.end_ns = close_steady_ns;
    if (hold_end_steady_ns_ > close_steady_ns) hold_end_steady_ns_ = close_steady_ns;
    return true;
  }

private:
  void push_publication(std::uint64_t sequence, std::int64_t publish_ns, double n,
                        int channel)
  {
    publications_.push_back(PublicationEvent{channel, sequence, publish_ns, n, true});
    while (publications_.size() > kHistoryCapacity) publications_.pop_front();
  }

  std::string schema_version_;
  std::string expected_run_id_;
  std::string expected_contract_hash_;
  std::string producer_instance_id_;
  bool started_ = false;
  bool known_ = false;
  bool normal_complete_ = false;  // 只有 bootstrap 之后才算"链已开始且连续"
  std::array<double, 2> anchor_thrust_{0.0, 0.0};
  std::int64_t anchor_steady_ns_ = 0;
  std::int64_t hold_end_steady_ns_ = 0;
  std::uint64_t execution_index_ = 0;
  std::int64_t sim_ns_ = 0;
  std::uint64_t last_sequence_ = 0;
  std::int64_t bootstrap_origin_ns_ = 0;
  std::string bootstrap_clock_identity_;
  std::size_t duplicate_count_ = 0;
  std::size_t reordered_count_ = 0;
  std::deque<HoldRecord> holds_;
  std::deque<PublicationEvent> publications_;
  std::deque<std::uint64_t> job_history_;
};

}  // namespace p1_receipt
