// Copyright 2026 USV Developer
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
// THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.


/**
 * @file safety_monitor.hpp
 * @brief USV 自主运行的安全监控器（纯 C++ 逻辑，无 ROS 依赖）。
 *
 * 监控通信健康状态、求解器状态、地理围栏和系统状态。
 * 在检测到异常时触发故障保护（failsafe）动作。
 *
 * 对应 Python 版本: usv_safety/safety_monitor.py
 *
 * 设计要点：每个 update 方法只负责一个监控域（odom/geofence/battery、
 * solver、path、odom 看门狗）。更新一个域不得清除另一个域的活跃标志，
 * 否则一条新的 odom 样本会掩盖 solver/path 的 failsafe。replace_flags_()
 * 强制执行这种域隔离。
 */

#pragma once

#include <string>
#include <vector>

namespace usv_safety
{

// ── 安全级别枚举 ─────────────────────────────────────────
// 对应 Python: class SafetyLevel(IntEnum)
enum class SafetyLevel : int
{
  NOMINAL  = 0,  // 所有系统正常
  WARNING  = 1,  // 性能下降但可恢复
  CAUTION  = 2,  // 需要采取行动 — 减速、保持位置
  FAILSAFE = 3,  // 立即触发 RTL（返航）或 HOLD（保持）
};

// ── 可配置的安全阈值 ─────────────────────────────────────
// 对应 Python: @dataclass class SafetyConfig
struct SafetyConfig
{
  int    max_solver_failures = 5;
  double max_odom_timeout_s = 1.0;
  double max_path_timeout_s = 5.0;
  double max_solve_time_ms = 500.0;
  double geofence_radius_m = 200.0;
  double geofence_center_x = 0.0;
  double geofence_center_y = 0.0;
  double max_crosstrack_error_m = 10.0;
  double low_battery_v = 10.5;
  double critical_battery_v = 10.0;
  double max_speed_mps = 3.0;
  double mpc_status_timeout_s = 1.0;
};

// ── 当前的安全评估状态 ───────────────────────────────────
// 对应 Python: @dataclass class SafetyState
struct SafetyState
{
  SafetyLevel              level = SafetyLevel::NOMINAL;
  std::vector<std::string> active_flags;
  std::string              recommended_action;
  double                   timestamp = 0.0;
};

// ── 安全监控器 ───────────────────────────────────────────
// 对应 Python: class SafetyMonitor
class SafetyMonitor {
public:
  /**
   * @brief 构造函数。
   * @param config 可配置的安全阈值，使用默认值即可满足大多数场景。
   */
  explicit SafetyMonitor(const SafetyConfig & config = SafetyConfig{});

  // ── 域更新方法 ──────────────────────────────────────

  /// 根据最新的里程计数据更新地理围栏和速度限制检查。
  /// 只能从真实 odom 回调调用:timestamp 是 odom 看门狗的时间种子。
  /// 电池电压走独立的 update_battery() 域;若从这里喂电压,电池话题会
  /// 持续刷新 odom 看门狗,导致 odom 断流 failsafe 永不触发。
  /// timestamp 为 0 时自动取系统单调时钟。
  void update_odom(
    double x, double y, double psi, double speed,
    double timestamp = 0.0);

  /// 更新电池检查。独立拥有 Low/CRITICAL battery 标志域。
  void update_battery(double voltage, double timestamp = 0.0);

  /// 根据求解器状态更新。
  void update_solver(
    bool success, double solve_time_ms,
    double timestamp = 0.0);

  /// 根据路径规划器状态更新。
  void update_path(bool received, double timestamp = 0.0);

  /// 设置或清除里程计看门狗标志。flag 为空字符串时表示清除。
  void set_odom_watchdog(const std::string & flag, double timestamp = 0.0);

  /// 记录 /mpc/status 到达时间(新鲜度看门狗的时间种子)。
  void mark_mpc_status(double timestamp = 0.0);

  /// 设置或清除 /mpc/status 新鲜度看门狗标志。flag 为空字符串时表示清除。
  void set_mpc_status_watchdog(const std::string & flag, double timestamp = 0.0);

  /// 设置或清除电池遥测看门狗标志 (WARNING 级: 断流仅提醒, 不触发 RTL)。
  void set_battery_watchdog(const std::string & flag, double timestamp = 0.0);

  /// 同步求解器失败计数器，且不增加新的失败次数。
  void set_solver_fail_count(int fail_count);

  /// 清除过期的求解器警告/故障保护标志。
  void clear_solver_flags(double timestamp = 0.0);

  /// 如果里程计数据已超时，则返回 true。
  bool check_odom_timeout(double timestamp = 0.0) const;

  /// 如果 /mpc/status 已过期，则返回 true。
  bool check_mpc_status_timeout(double timestamp = 0.0) const;

  /// 重置所有状态。
  void reset();

  // ── 只读属性访问器（防御性拷贝） ────────────────────

  /// 返回当前安全状态的防御性快照。
  SafetyState state() const;

  /// 返回当前安全级别。
  SafetyLevel level() const;

  /// 返回当前活跃的警告标志列表。
  std::vector<std::string> active_flags() const;

  /// 返回推荐动作。
  std::string recommended_action() const;

  /// 返回求解器连续失败计数。
  int solver_fail_count() const;

  /// 安全级别低于 FAILSAFE 时返回 true。
  bool ok() const;

  /// 当前是否处于 WARNING 级别。
  bool warning_active() const;

  /// 当前是否触发了 FAILSAFE。
  bool failsafe_active() const;

private:
  // ── 内部工具方法 ──────────────────────────────────────

  /// 替换某一个监控域的警告标志，而不清除其他域的标志。
  /// prefixes 为该域所有标志的前缀集合；new_flags 为该域的新标志（可为空）。
  void replace_flags_(
    const std::vector<std::string> & prefixes,
    const std::vector<std::string> & new_flags,
    double timestamp);

  /// 根据当前活跃的警告标志消息，推导出总体的严重程度级别。
  static SafetyLevel level_from_flags_(const std::vector<std::string> & flags);

  /// 根据安全级别返回推荐动作字符串。
  static std::string get_action_(SafetyLevel level);

  /// 获取当前时间戳（秒），当传入值为 0 时自动获取系统单调时钟。
  static double now_or_(double ts);

  /// 辅助函数：检查字符串是否以指定前缀开头。
  static bool starts_with_(const std::string & str, const std::string & prefix);

  // ── 内部状态 ──────────────────────────────────────────
  SafetyConfig config_;
  double       last_odom_time_ = 0.0;
  double       last_path_time_ = 0.0;
  double       last_mpc_status_time_ = 0.0;
  int          solver_fail_count_ = 0;
  double       last_solve_time_ms_ = 0.0;
  SafetyState  current_state_;
};

}  // namespace usv_safety
