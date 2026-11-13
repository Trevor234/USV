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
 * @file safety_monitor.cpp
 * @brief USV 安全监控器实现（纯逻辑，无 ROS 依赖）。
 */

#include "usv_safety/safety_monitor.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>

namespace usv_safety {

// ── 构造函数 ─────────────────────────────────────────────
SafetyMonitor::SafetyMonitor(const SafetyConfig& config)
    : config_(config) {}

// ── 域更新 ───────────────────────────────────────────────

void SafetyMonitor::update_odom(double x, double y, double /*psi*/,
                                double speed, double timestamp) {
  double ts = now_or_(timestamp);
  last_odom_time_ = ts;

  std::vector<std::string> flags;

  // 地理围栏
  double dx = x - config_.geofence_center_x;
  double dy = y - config_.geofence_center_y;
  double dist = std::hypot(dx, dy);
  if (dist > config_.geofence_radius_m) {
    flags.push_back("GEOFENCE VIOLATION: " + std::to_string(dist).substr(0, 4) +
                    "m");
  } else if (dist > config_.geofence_radius_m * 0.9) {
    flags.push_back("Approaching geofence boundary: " +
                    std::to_string(dist).substr(0, 4) + "m");
  }

  // 速度限制
  if (speed > config_.max_speed_mps) {
    flags.push_back("Speed limit exceeded: " +
                    std::to_string(speed).substr(0, 4) + " m/s");
  }

  replace_flags_(
      {
          "Approaching geofence boundary",
          "GEOFENCE VIOLATION",
          "Speed limit exceeded",
      },
      flags, ts);
}

void SafetyMonitor::update_battery(double voltage, double timestamp) {
  double ts = now_or_(timestamp);

  std::vector<std::string> flags;
  if (voltage < config_.critical_battery_v) {
    flags.push_back("CRITICAL battery: " + std::to_string(voltage).substr(0, 4) +
                    "V");
  } else if (voltage < config_.low_battery_v) {
    flags.push_back("Low battery: " + std::to_string(voltage).substr(0, 4) +
                    "V");
  }

  replace_flags_({"Low battery", "CRITICAL battery"}, flags, ts);
}

void SafetyMonitor::update_solver(bool success, double solve_time_ms,
                                  double timestamp) {
  double ts = now_or_(timestamp);
  last_solve_time_ms_ = solve_time_ms;

  if (success) {
    solver_fail_count_ = 0;
  } else {
    solver_fail_count_ += 1;
  }

  std::vector<std::string> flags;
  if (solver_fail_count_ >= config_.max_solver_failures) {
    flags.push_back("Solver failed " + std::to_string(solver_fail_count_) +
                    " consecutive times");
  } else if (solver_fail_count_ >= 3) {
    flags.push_back("Solver failures: " + std::to_string(solver_fail_count_));
  }

  if (solve_time_ms > config_.max_solve_time_ms) {
    flags.push_back("Slow solve: " + std::to_string(static_cast<int>(solve_time_ms)) +
                    "ms");
  }

  replace_flags_(
      {"Solver failed", "Solver failures", "Slow solve"}, flags, ts);
}

void SafetyMonitor::update_path(bool received, double timestamp) {
  double ts = now_or_(timestamp);

  if (received) {
    last_path_time_ = ts;
    replace_flags_({"No path update"}, {}, ts);
  } else if (last_path_time_ > 0.0) {
    // 只有在确实收到过路径之后才监视超时；
    // 任务开始前路径缺失不得触发 failsafe。
    double dt = ts - last_path_time_;
    if (dt > config_.max_path_timeout_s) {
      std::string flag = "No path update for " +
                         std::to_string(static_cast<int>(dt)) + "s";
      replace_flags_({"No path update"}, {flag}, ts);
    } else {
      replace_flags_({"No path update"}, {}, ts);
    }
  }
}

void SafetyMonitor::set_odom_watchdog(const std::string& flag,
                                      double timestamp) {
  double ts = now_or_(timestamp);
  std::vector<std::string> new_flags;
  if (!flag.empty()) {
    new_flags.push_back(flag);
  }
  // "FCU link lost" 也必须列入被替换集合, 否则断链期间每 0.5s 追加一条,
  // 恢复后也不会被清除, flags 会无限累积同一条告警。
  replace_flags_({"No odometry received", "Odometry timeout", "FCU link lost"},
                 new_flags, ts);
}

void SafetyMonitor::mark_mpc_status(double timestamp) {
  last_mpc_status_time_ = now_or_(timestamp);
}

void SafetyMonitor::set_mpc_status_watchdog(const std::string& flag,
                                            double timestamp) {
  double ts = now_or_(timestamp);
  std::vector<std::string> new_flags;
  if (!flag.empty()) {
    new_flags.push_back(flag);
  }
  replace_flags_({"No MPC status", "MPC status timeout"}, new_flags, ts);
}

void SafetyMonitor::set_battery_watchdog(const std::string& flag,
                                         double timestamp) {
  double ts = now_or_(timestamp);
  std::vector<std::string> new_flags;
  if (!flag.empty()) {
    new_flags.push_back(flag);
  }
  replace_flags_({"No battery telemetry"}, new_flags, ts);
}

void SafetyMonitor::set_solver_fail_count(int fail_count) {
  solver_fail_count_ = std::max(0, fail_count);
}

void SafetyMonitor::clear_solver_flags(double timestamp) {
  double ts = now_or_(timestamp);
  replace_flags_({"Solver failed", "Solver failures", "Slow solve"}, {}, ts);
}

bool SafetyMonitor::check_odom_timeout(double timestamp) const {
  double ts = now_or_(timestamp);
  return (ts - last_odom_time_) > config_.max_odom_timeout_s;
}

bool SafetyMonitor::check_mpc_status_timeout(double timestamp) const {
  double ts = now_or_(timestamp);
  return (ts - last_mpc_status_time_) > config_.mpc_status_timeout_s;
}

void SafetyMonitor::reset() {
  solver_fail_count_ = 0;
  current_state_ = SafetyState{};
}

// ── 只读访问器 ───────────────────────────────────────────

SafetyState SafetyMonitor::state() const {
  SafetyState snapshot;
  snapshot.level = current_state_.level;
  snapshot.active_flags = current_state_.active_flags;  // 防御性拷贝
  snapshot.recommended_action = current_state_.recommended_action;
  snapshot.timestamp = current_state_.timestamp;
  return snapshot;
}

SafetyLevel SafetyMonitor::level() const { return current_state_.level; }

std::vector<std::string> SafetyMonitor::active_flags() const {
  return current_state_.active_flags;
}

std::string SafetyMonitor::recommended_action() const {
  return current_state_.recommended_action;
}

int SafetyMonitor::solver_fail_count() const { return solver_fail_count_; }

bool SafetyMonitor::ok() const {
  return static_cast<int>(current_state_.level) <
         static_cast<int>(SafetyLevel::FAILSAFE);
}

bool SafetyMonitor::warning_active() const {
  return current_state_.level == SafetyLevel::WARNING;
}

bool SafetyMonitor::failsafe_active() const {
  return current_state_.level == SafetyLevel::FAILSAFE;
}

// ── 内部工具方法 ─────────────────────────────────────────

void SafetyMonitor::replace_flags_(const std::vector<std::string>& prefixes,
                                   const std::vector<std::string>& new_flags,
                                   double timestamp) {
  std::vector<std::string> flags;
  for (const auto& flag : current_state_.active_flags) {
    bool belongs = false;
    for (const auto& prefix : prefixes) {
      if (starts_with_(flag, prefix)) {
        belongs = true;
        break;
      }
    }
    if (!belongs) {
      flags.push_back(flag);
    }
  }
  for (const auto& nf : new_flags) {
    flags.push_back(nf);
  }

  SafetyLevel level = level_from_flags_(flags);
  current_state_.level = level;
  current_state_.active_flags = flags;
  current_state_.recommended_action = get_action_(level);
  current_state_.timestamp = timestamp;
}

SafetyLevel SafetyMonitor::level_from_flags_(
    const std::vector<std::string>& flags) {
  // FAILSAFE 触发前缀（按前缀匹配触发）
  static const std::vector<std::string> kFailsafePrefixes = {
      "GEOFENCE VIOLATION", "CRITICAL battery", "Solver failed",
      "No path update", "No odometry received", "Odometry timeout",
      "No MPC status", "MPC status timeout",
      // 与飞控链路断开: MAVROS 会把 armed 置 false, 而 FCU 侧会锁存最后
      // 一条速度指令。断链必须与"里程计超时"同级, 不能被 armed 门禁吞掉。
      "FCU link lost",
  };
  static const std::vector<std::string> kWarningPrefixes = {
      "Approaching geofence boundary", "Speed limit exceeded",
      "Low battery", "Solver failures", "Slow solve",
      "No battery telemetry",
  };

  SafetyLevel level = SafetyLevel::NOMINAL;
  for (const auto& flag : flags) {
    for (const auto& p : kFailsafePrefixes) {
      if (starts_with_(flag, p)) {
        return SafetyLevel::FAILSAFE;
      }
    }
    for (const auto& p : kWarningPrefixes) {
      if (starts_with_(flag, p)) {
        level = std::max(level, SafetyLevel::WARNING);
        break;
      }
    }
  }
  return level;
}

std::string SafetyMonitor::get_action_(SafetyLevel level) {
  switch (level) {
    case SafetyLevel::FAILSAFE: return "RTL";
    case SafetyLevel::CAUTION:  return "HOLD";
    case SafetyLevel::WARNING:  return "REDUCE_SPEED";
    default:                     return "NONE";
  }
}

double SafetyMonitor::now_or_(double ts) {
  if (ts != 0.0) {
    return ts;
  }
  auto now = std::chrono::steady_clock::now();
  return std::chrono::duration<double>(now.time_since_epoch()).count();
}

bool SafetyMonitor::starts_with_(const std::string& str,
                                 const std::string& prefix) {
  return str.rfind(prefix, 0) == 0;
}

}  // namespace usv_safety
