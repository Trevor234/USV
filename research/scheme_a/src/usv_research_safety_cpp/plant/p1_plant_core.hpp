// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// plant/p1_plant_core.hpp —— 受控仿真 plant 的物理内核（无 ROS、无 DDS、无墙钟）。
//
// 唯一的推进源是 `step_once`：时钟、动力学、传感器、参考发布都从同一个
// 仿真时刻派生。命令回调**只做准入**，绝不改状态 —— 否则"命令到达"和
// "物理推进"就成了两个可以互相矛盾的时钟（3.5 的缺陷）。
//
// 时间轴（全部整数纳秒，半开区间）：
//   steady_origin_ns —— CLOCK_MONOTONIC 原点，sim = steady - origin；
//   substep_ns       —— T/4 = 50 ms，与生成模型的 rk4_substeps 一致；
//   next_boundary()  —— 下一个 tick 网格边界（origin + k*T）。
#pragma once

#include <array>
#include <cstdint>
#include <limits>
#include <stdexcept>

#include <Eigen/Dense>

#include "usv_nmpc/usv_model_dynamic.hpp"

namespace p1_plant
{

constexpr std::int64_t kTickNs = 200000000;   // T
constexpr std::int64_t kDeadlineNs = 150000000;
constexpr std::int64_t kSubstepNs = kTickNs / 4;  // 50 ms，与 rk4_substeps = 4 对齐

using Vector6d = usv_mpc::Vector6d;

/// CLOCK_MONOTONIC ↔ 仿真时间 的双射，只允许通过它换算。
struct SimClock
{
  std::int64_t steady_origin_ns = 0;
  std::int64_t sim_ns = 0;

  std::int64_t steady_of(std::int64_t sim) const { return steady_origin_ns + sim; }
  std::int64_t sim_of(std::int64_t steady) const { return steady - steady_origin_ns; }

  /// 向上对齐到下一个 tick 网格边界（严格大于 sim）。
  std::int64_t next_boundary() const
  {
    const std::int64_t index = sim_ns / kTickNs;
    return (index + 1) * kTickNs;
  }

  /// 把"声明起点"向上对齐到网格：只发生在首步，之后沿同一网格推进。
  std::int64_t align_up(std::int64_t sim) const
  {
    if (sim <= 0) return 0;
    if (sim % kTickNs == 0) return sim;
    return ((sim / kTickNs) + 1) * kTickNs;
  }

  /// 追赶超限时的重设：不回退、不跳子步，只把 origin 移到"现在 - sim"。
  void resync(std::int64_t now_steady)
  {
    steady_origin_ns = now_steady - sim_ns;
  }

  bool catch_up_exceeded(std::int64_t now_steady, std::int64_t limit_ns) const
  {
    return now_steady - steady_of(sim_ns) > limit_ns;
  }
};

/// 一个已接纳命令的 hold 窗口：半开 [begin, end)，未覆盖即零推力。
struct HoldWindow
{
  bool active = false;
  std::int64_t begin_ns = 0;
  std::int64_t end_ns = 0;
  std::array<double, 2> thrust{0.0, 0.0};
  std::uint64_t sequence = 0;
  std::uint64_t tick = 0;
  std::uint64_t execution_index = 0;

  bool covers(std::int64_t sim) const
  {
    return active && sim >= begin_ns && sim < end_ns;
  }
  bool expired_at(std::int64_t sim) const { return active && sim >= end_ns; }
};

/// 半开区间语义的唯一实现：窗口外一律零推力，不做"大概保持"。
inline std::array<double, 2> held_thrust(const HoldWindow & hold, std::int64_t sim)
{
  if (!hold.covers(sim)) return {0.0, 0.0};
  return hold.thrust;
}

/// 物理推进：复用既有 USVDynamicModel，不复制 RK4、不新增积分器。
struct PlantCore
{
  explicit PlantCore(usv_mpc::HydroParams hydro)
      : model(kTickNs * 1e-9, 4, hydro) {}

  /// 推进一个子步（50 ms）。返回 false 表示输入不可用（非有限）。
  bool step_once(Vector6d & state, const std::array<double, 2> & thrust)
  {
    for (double value : thrust)
      if (!std::isfinite(value)) return false;
    for (double value : state)
      if (!std::isfinite(value)) return false;
    const Eigen::Vector2d u(thrust[0], thrust[1]);
    state = model.forward_for_duration(state, u, kSubstepNs * 1e-9);
    return true;
  }

  /// 整 tick 的参考：4 个子步与一次 200 ms 积分在位级上一致。
  /// 这是测试用来证明"子步不改变动力学"的唯一入口。
  Vector6d forward_tick(const Vector6d & state, const std::array<double, 2> & thrust) const
  {
    const Eigen::Vector2d u(thrust[0], thrust[1]);
    return model.forward_for_duration(state, u, kTickNs * 1e-9);
  }

  usv_mpc::USVDynamicModel model;
};

/// 状态数组与 Eigen 向量之间的唯一转换，避免各处自己 reinterpret。
inline Vector6d to_vector(const double (&state)[6])
{
  Vector6d out;
  for (int i = 0; i < 6; ++i) out[i] = state[i];
  return out;
}

inline void from_vector(const Vector6d & value, double (&state)[6])
{
  for (int i = 0; i < 6; ++i) state[i] = value[i];
}

}  // namespace p1_plant
