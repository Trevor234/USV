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
 * @file mode_manager_node.hpp
 * @brief 模式管理 ROS 2 节点（C++ 版本）。
 *
 * 负责管理飞行模式切换 (MANUAL ↔ GUIDED ↔ HOLD ↔ RTL)、
 * 解锁/上锁，以及集成安全监控功能。
 *
 * 对应 Python 版本: usv_safety/mode_manager_node.py
 */

#pragma once

#include <cstdint>
#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>
#include <mavros_msgs/msg/state.hpp>
#include <mavros_msgs/srv/command_bool.hpp>
#include <mavros_msgs/srv/set_mode.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <nav_msgs/msg/path.hpp>
#include <sensor_msgs/msg/battery_state.hpp>
#include <std_msgs/msg/string.hpp>

#include "usv_safety_cpp/safety_monitor.hpp"

namespace usv_safety {

class ModeManagerNode : public rclcpp::Node {
 public:
  ModeManagerNode();

  /// 请求解锁/上锁。
  bool request_arm(bool arm = true);

  /// 切换到 GUIDED 模式。
  bool switch_to_guided();
  /// 切换到 MANUAL 模式。
  bool switch_to_manual();
  /// 切换到 RTL 模式。
  bool switch_to_rtl();
  /// 切换到 HOLD 模式。
  bool switch_to_hold();

 private:
  // ── 初始化辅助 ──────────────────────────────────────
  void declare_parameters_();
  void load_config_();

  // ── 回调函数 ────────────────────────────────────────
  void state_callback_(const mavros_msgs::msg::State::SharedPtr msg);
  void mpc_status_callback_(const std_msgs::msg::String::SharedPtr msg);

  // 安全状态发布辅助
  static const char* safety_level_name_(SafetyLevel level);
  void publish_safety_status_(const char* level, const std::string& flags);
  void odom_callback_(const nav_msgs::msg::Odometry::SharedPtr msg);
  void battery_callback_(const sensor_msgs::msg::BatteryState::SharedPtr msg);
  void path_callback_(const nav_msgs::msg::Path::SharedPtr msg);

  // ── 定时器回调 ──────────────────────────────────────
  void monitor_loop_();

  // ── 模式切换 ────────────────────────────────────────
  bool switch_mode_(const std::string& mode);

  // ── 安全监控器（纯逻辑） ────────────────────────────
  SafetyConfig  safety_config_;
  SafetyMonitor safety_;

  // ── 内部状态 ────────────────────────────────────────
  std::string current_mavros_mode_   = "MANUAL";
  bool        armed_                 = false;
  // MAVROS 链路连接状态 (来自 /mavros/state.connected)。
  // 看门狗武装条件必须用 connected 而非 armed: 断链时 /mavros/state 会把
  // armed 置 false, 若用它作武装条件, 所有保护会在最需要时静默。
  bool        fcu_connected_         = false;
  bool        mpc_ok_                = true;   // 默认 True,直到收到真正的错误
  int         mpc_fail_count_        = 0;
  double      mpc_solve_time_ms_     = 0.0;
  bool        mpc_hold_              = false;
  std::string mpc_state_             = "UNKNOWN";  // ACTIVE/HOLD/STANDBY/UNKNOWN
  std::string mpc_standby_reason_;
  double      last_mpc_status_time_  = 0.0;
  // 每条 /mpc/status 递增; 监控循环据此只消费"新"状态 (避免按 2Hz 监控
  // 节拍重复喂同一份失败, 把失败计数膨胀)
  uint64_t    mpc_status_seq_        = 0;
  uint64_t    last_status_seq_used_  = 0;
  double      x_                     = 0.0;
  double      y_                     = 0.0;
  double      speed_                 = 0.0;
  // 安全哨兵值:缺失电池遥测不得触发低/临界电池 failsafe
  // (任务中途意外 RTL 本身就是一种危险)。
  double      voltage_               = 99.0;
  bool        battery_received_      = false;
  bool        odom_received_         = false;
  double      last_odom_rx_          = 0.0;
  bool        path_ever_received_    = false;
  double      last_battery_rx_       = 0.0;
  // 人工接管冷却: FCU 模式变化时刻起, 该时长内 auto_mode_switch 不拉回
  double      last_mode_change_      = 0.0;
  double      battery_timeout_s_     = 10.0;
  double      takeover_cooldown_s_   = 10.0;
  // FAILSAFE 模式切换重发上限 (达到后停止指令洪水, 保持 failsafe 等待人工介入)
  int         max_rtl_retries_       = 10;
  int         rtl_attempts_          = 0;
  // 兜底: set_mode 重试耗尽后 disarm, 让飞控切断动力。
  bool        failsafe_disarm_sent_  = false;
  // FAILSAFE 触发时的动作: "report"(只报错) / "HOLD" / "RTL"
  std::string failsafe_mode_        = "report";

  // ── ROS 通信接口 ────────────────────────────────────
  // 订阅者
  rclcpp::Subscription<mavros_msgs::msg::State>::SharedPtr        state_sub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr          mpc_status_sub_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr        odom_sub_;
  rclcpp::Subscription<sensor_msgs::msg::BatteryState>::SharedPtr battery_sub_;
  rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr            path_sub_;

  // 服务客户端
  // 安全状态对外发布 (JSON)。此前安全节点没有任何 publisher,
  // 围栏/电池/求解器告警与 failsafe 事件对地面站完全不可见, 也不进 bag。
  // (2026-10-21)
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr      safety_status_pub_;
  rclcpp::Client<mavros_msgs::srv::SetMode>::SharedPtr      set_mode_cli_;
  rclcpp::Client<mavros_msgs::srv::CommandBool>::SharedPtr  cmd_arming_cli_;

  // 定时器
  rclcpp::TimerBase::SharedPtr timer_;
};

}  // namespace usv_safety
