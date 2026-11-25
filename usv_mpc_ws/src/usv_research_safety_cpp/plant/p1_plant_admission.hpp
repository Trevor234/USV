// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// plant/p1_plant_admission.hpp —— plant 的执行准入（纯函数，无 ROS、无墙钟）。
//
// 3.4 的缺陷是：plant 只校验 run/schema/sequence/deadline/推力范围，于是
//   * 错误的五轴版本被原样回显并执行；
//   * 同一个 tick 可以被施加两次；
//   * 重叠窗口可以被接受（推力来源不唯一）。
//
// 这里的顺序是**固定**的 12 步，且每一步都返回可对账的 reason 词表值。
// `now` 由调用方传入：准入判据不接受内部时钟，否则测试只能靠睡等。
#pragma once

#include <cmath>
#include <cstdint>
#include <deque>
#include <string>
#include <unordered_map>

#include "p1_plant_core.hpp"

namespace p1_plant
{

/// 命令的最小视图：只包含准入真正需要的字段。
struct CommandView
{
  std::string schema_version;
  std::string run_id;
  std::string boot_id;
  std::string contract_hash;
  /// 命令的生产者（regulator 或刺激注入器）。序号是每个生产者各自的。
  std::string producer;
  std::uint64_t sequence = 0;
  std::uint64_t tick = 0;
  std::int64_t apply_begin_steady_ns = 0;
  std::int64_t apply_end_steady_ns = 0;
  std::int64_t deadline_steady_ns = 0;
  std::array<double, 2> thrust{0.0, 0.0};
  std::uint64_t task_generation = 0;
  std::uint64_t model_generation = 0;
  std::uint64_t config_generation = 0;
  std::uint64_t schedule_generation = 0;
  std::uint64_t clock_epoch = 0;
};

/// 处置与原因（词表固定；检查器按词表判定）。
struct Admission
{
  std::string disposition;   // ok / rejected / late / duplicate
  std::string reason;        // 词表值；ok 时为空
  bool executes = false;     // 只有 ok 才可真实施加
};

/// 有界、可回读的准入状态。
struct PlantGateState
{
  static constexpr std::size_t kCapacity = 64;

  /// 两类状态必须分开：
  ///   * sequence **全局唯一**（一个序号只对应一条命令，不管谁发的）——这是
  ///     "同序号只执行一次 / 重复必须被识别"的基础；
  ///   * **顺序** 是每个生产者各自的（注入器自己的序号空间不该把 regulator
  ///     的命令判成 reordered）；
  ///   * tick 是物理时间，全局唯一。
  std::deque<std::uint64_t> seen_sequences;
  std::deque<std::uint64_t> executed_ticks;
  std::unordered_map<std::string, std::uint64_t> highest_by_producer;
  bool pending_scheduled = false;
  /// 待执行命令的窗口起点（steady）。窗口一旦开始，这条申请就已"生效"，
  /// 不再占用 pending 槽位 —— pump 最多滞后一个轮询周期，不能因此把
  /// 已经合法的后继命令判成 command_pending。
  std::int64_t pending_begin_steady_ns = 0;
  std::int64_t open_hold_end_steady_ns = 0;

  bool seen(std::uint64_t sequence) const
  {
    for (auto value : seen_sequences)
      if (value == sequence) return true;
    return false;
  }
  bool tick_executed(std::uint64_t tick) const
  {
    for (auto value : executed_ticks)
      if (value == tick) return true;
    return false;
  }
  std::uint64_t highest_sequence(const std::string & producer) const
  {
    const auto it = highest_by_producer.find(producer);
    return it == highest_by_producer.end() ? 0 : it->second;
  }
  void note_sequence(std::uint64_t sequence, const std::string & producer = "")
  {
    seen_sequences.push_back(sequence);
    while (seen_sequences.size() > kCapacity) seen_sequences.pop_front();
    auto & highest = highest_by_producer[producer];
    if (sequence > highest) highest = sequence;
  }
  void note_executed_tick(std::uint64_t tick)
  {
    executed_ticks.push_back(tick);
    while (executed_ticks.size() > kCapacity) executed_ticks.pop_front();
  }
  void reset()
  {
    seen_sequences.clear();
    executed_ticks.clear();
    highest_by_producer.clear();
    pending_scheduled = false;
    pending_begin_steady_ns = 0;
    open_hold_end_steady_ns = 0;
  }
};

/// 准入的输入事实：身份、期望 schema、推力上下限、合同周期。
struct GateContext
{
  std::string run_id;
  std::string boot_id;
  std::string contract_hash;
  std::string schema_version = "p1-plant-command-v2";
  std::string producer;
  double command_min_n = -25.0;
  double command_max_n = 25.0;
};

/// 固定 12 步准入。`now` 是**调用方**采样的 CLOCK_MONOTONIC 纳秒。
/// 顺序: schema → foreign_run → duplicate → reordered → invalid_window →
///       late(deadline) → late(window_closed) → thrust_range →
///       tick_already_executed → command_pending → window_overlap → ok
inline Admission classify(const CommandView & command, const GateContext & context,
                          PlantGateState & state, std::int64_t now_steady_ns)
{
  Admission out;
  const auto reject = [&out](const char * reason) {
    out.disposition = "rejected";
    out.reason = reason;
    out.executes = false;
    return out;
  };
  const auto late = [&out](const char * reason) {
    out.disposition = "late";
    out.reason = reason;
    out.executes = false;
    return out;
  };
  // duplicate 是**独立处置**，不是 rejected 的一个理由：重复命令没有执行、
  // 也没有迟到，把它折叠成 rejected 会让"同序号只执行一次"无法被逐条核对。
  const auto duplicate = [&out](const char * reason) {
    out.disposition = "duplicate";
    out.reason = reason;
    out.executes = false;
    return out;
  };

  // 1) schema：版本不足直接拒绝，不降级解析。
  if (command.schema_version != context.schema_version) return reject("schema");
  // 2) 运行身份：外来运行的命令绝不执行。
  if (command.run_id != context.run_id || command.boot_id != context.boot_id ||
      command.contract_hash != context.contract_hash)
    return reject("foreign_run");
  // 3) 重复：同一 sequence 已受理过（不论当时处置如何）。
  if (state.seen(command.sequence)) return duplicate("same_sequence");
  // 4) 重排：比已受理的最大 sequence 更旧。
  if (command.sequence < state.highest_sequence(command.producer))
    return reject("reordered");
  // 5) 申请窗口必须正好一个合同周期，且起点非负。
  if (command.apply_begin_steady_ns < 0 ||
      command.apply_end_steady_ns - command.apply_begin_steady_ns != kTickNs)
    return reject("invalid_window");
  // 6) 迟到：接收时刻已过 deadline（等于 deadline 不算迟到）。
  if (now_steady_ns > command.deadline_steady_ns)
    return late("deadline_passed_before_execution");
  // 7) 窗口已关闭：申请窗口末端已过。
  if (now_steady_ns >= command.apply_end_steady_ns) return late("window_closed");
  // 8) 推力范围与有限性。
  for (double value : command.thrust)
    if (!std::isfinite(value) || value < context.command_min_n ||
        value > context.command_max_n)
      return reject("thrust_range");
  // 9) 同一 tick 只施加一次（与 sequence 无关的第二道闸）。
  if (state.tick_executed(command.tick)) return reject("tick_already_executed");
  // 10) 已有待执行命令：一次只允许一个未完成的申请。
  // 槽位里有未生效的窗口就拒绝：允许"窗口已到点"的后继命令通过，会让它
  // 覆盖掉尚未执行的那条申请（实测会把注入命令整条吞掉）。
  // pump 的滞后由调用方在准入前推进 due 窗口解决，不靠放宽这一条。
  if (state.pending_scheduled) return reject("command_pending");
  // 11) 窗口重叠：新窗口起点早于已有 hold 末端。
  if (state.open_hold_end_steady_ns > 0 &&
      command.apply_begin_steady_ns < state.open_hold_end_steady_ns)
    return reject("window_overlap");

  // 12) ok
  out.disposition = "ok";
  out.reason = "";
  out.executes = true;
  return out;
}

}  // namespace p1_plant
