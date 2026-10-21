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
 * @file mode_manager_node.cpp
 * @brief 模式管理 ROS 2 节点实现（C++ 版本）。
 *
 * 对应 Python 版本: usv_safety/mode_manager_node.py
 */

#include "usv_safety_cpp/mode_manager_node.hpp"

#include <chrono>
#include <cmath>
#include <functional>
#include <iomanip>
#include <sstream>

#include <nlohmann/json.hpp>
#include <rclcpp/qos.hpp>

using namespace std::chrono_literals;

namespace usv_safety {

namespace {
double steady_now() {
  auto now = std::chrono::steady_clock::now();
  return std::chrono::duration<double>(now.time_since_epoch()).count();
}
}  // namespace

// ── 构造函数 ─────────────────────────────────────────────
ModeManagerNode::ModeManagerNode()
    : Node("mode_manager_node") {
  declare_parameters_();
  load_config_();

  safety_ = SafetyMonitor(safety_config_);

  // ── 订阅者 ──────────────────────────────────────────

  // 飞控状态
  auto state_topic = this->get_parameter("state_topic").as_string();
  state_sub_ = this->create_subscription<mavros_msgs::msg::State>(
      state_topic, 10,
      std::bind(&ModeManagerNode::state_callback_, this, std::placeholders::_1));

  // MPC 状态（JSON）
  auto mpc_status_topic = this->get_parameter("mpc_status_topic").as_string();
  mpc_status_sub_ = this->create_subscription<std_msgs::msg::String>(
      mpc_status_topic, 10,
      std::bind(&ModeManagerNode::mpc_status_callback_, this, std::placeholders::_1));

  // 位姿+速度（传感器数据 QoS）
  auto odom_topic = this->get_parameter("odom_topic").as_string();
  odom_sub_ = this->create_subscription<nav_msgs::msg::Odometry>(
      odom_topic, rclcpp::SensorDataQoS(),
      std::bind(&ModeManagerNode::odom_callback_, this, std::placeholders::_1));

  // 参考路径
  auto path_topic = this->get_parameter("path_topic").as_string();
  path_sub_ = this->create_subscription<nav_msgs::msg::Path>(
      path_topic, 10,
      std::bind(&ModeManagerNode::path_callback_, this, std::placeholders::_1));

  // 电池状态（可选）
  auto battery_topic = this->get_parameter("battery_topic").as_string();
  if (!battery_topic.empty()) {
    battery_sub_ = this->create_subscription<sensor_msgs::msg::BatteryState>(
        battery_topic, rclcpp::SensorDataQoS(),
        std::bind(&ModeManagerNode::battery_callback_, this, std::placeholders::_1));
  }

  // ── 服务客户端 ──────────────────────────────────────
  auto set_mode_service = this->get_parameter("set_mode_service").as_string();
  auto arming_service = this->get_parameter("arming_service").as_string();
  set_mode_cli_ = this->create_client<mavros_msgs::srv::SetMode>(set_mode_service);
  cmd_arming_cli_ = this->create_client<mavros_msgs::srv::CommandBool>(arming_service);

  // ── 定时器（0.5 秒周期） ───────────────────────────
  timer_ = this->create_wall_timer(
      500ms, std::bind(&ModeManagerNode::monitor_loop_, this));

  RCLCPP_INFO(this->get_logger(), "Mode Manager started | safety monitoring active");
}

// ── 声明参数 ─────────────────────────────────────────────
void ModeManagerNode::declare_parameters_() {
  this->declare_parameter("auto_arm", false);
  this->declare_parameter("auto_mode_switch", true);
  this->declare_parameter("geofence_radius", 200.0);
  this->declare_parameter("geofence_center_x", 0.0);
  this->declare_parameter("geofence_center_y", 0.0);
  this->declare_parameter("low_battery_v", 10.5);
  this->declare_parameter("critical_battery_v", 10.0);
  this->declare_parameter("max_solver_failures", 5);
  this->declare_parameter("odom_timeout_s", 1.0);
  this->declare_parameter("max_path_timeout_s", 5.0);
  this->declare_parameter("max_speed_mps", 3.0);
  this->declare_parameter("mpc_status_timeout_s", 1.0);
  // 电池遥测看门狗: 话题断流仅 WARNING (低电量检测失效需人工知晓),
  // 不触发 RTL —— 缺失遥测导致的意外 RTL 本身就是危险。
  this->declare_parameter("battery_timeout_s", 10.0);
  // 人工接管冷却: 检测到 FCU 模式被外部改变后, 该时长内 auto_mode_switch
  // 不拉回 GUIDED。failsafe RTL 不受此限制。
  this->declare_parameter("manual_takeover_cooldown_s", 10.0);
  // FAILSAFE RTL 重发上限: 达到后停止指令洪水 (链路断/飞控拒绝时无限
  // 重发毫无意义), 保持 failsafe 状态并节流告警, 等待人工介入。
  // FAILSAFE 触发时的动作: "report"(只报错不切模式, 测试期默认) /
  // "HOLD"(原地保持) / "RTL"(返航)
  this->declare_parameter("failsafe_mode", "report");
  this->declare_parameter("max_rtl_retries", 10);
  this->declare_parameter("state_topic", std::string("/mavros/state"));
  this->declare_parameter("mpc_status_topic", std::string("/mpc/status"));
  this->declare_parameter("path_topic", std::string("/path/reference"));
  this->declare_parameter("odom_topic", std::string("/mavros/local_position/odom"));
  this->declare_parameter("battery_topic", std::string("/mavros/battery"));
  this->declare_parameter("set_mode_service", std::string("/mavros/set_mode"));
  this->declare_parameter("arming_service", std::string("/mavros/cmd/arming"));
}

// ── 加载配置 ─────────────────────────────────────────────
void ModeManagerNode::load_config_() {
  safety_config_.geofence_radius_m    = this->get_parameter("geofence_radius").as_double();
  safety_config_.geofence_center_x    = this->get_parameter("geofence_center_x").as_double();
  safety_config_.geofence_center_y    = this->get_parameter("geofence_center_y").as_double();
  safety_config_.low_battery_v        = this->get_parameter("low_battery_v").as_double();
  safety_config_.critical_battery_v   = this->get_parameter("critical_battery_v").as_double();
  safety_config_.max_solver_failures  = this->get_parameter("max_solver_failures").as_int();
  safety_config_.max_odom_timeout_s   = this->get_parameter("odom_timeout_s").as_double();
  safety_config_.max_path_timeout_s   = this->get_parameter("max_path_timeout_s").as_double();
  safety_config_.max_speed_mps        = this->get_parameter("max_speed_mps").as_double();
  safety_config_.mpc_status_timeout_s = this->get_parameter("mpc_status_timeout_s").as_double();
  battery_timeout_s_   = this->get_parameter("battery_timeout_s").as_double();
  takeover_cooldown_s_ = this->get_parameter("manual_takeover_cooldown_s").as_double();
  max_rtl_retries_     = static_cast<int>(this->get_parameter("max_rtl_retries").as_int());
  failsafe_mode_       = this->get_parameter("failsafe_mode").as_string();
  if (failsafe_mode_ != "report" && failsafe_mode_ != "HOLD" && failsafe_mode_ != "RTL") {
    RCLCPP_ERROR(this->get_logger(),
                 "failsafe_mode='%s' 无效 (可选 report/HOLD/RTL), 回退 report",
                 failsafe_mode_.c_str());
    failsafe_mode_ = "report";
  }
}

// ── 飞控状态回调 ─────────────────────────────────────────
void ModeManagerNode::state_callback_(const mavros_msgs::msg::State::SharedPtr msg) {
  if (msg->mode != current_mavros_mode_) {
    // 记录外部/我方模式切换时刻 (人工接管冷却的起点)
    last_mode_change_ = steady_now();
  }
  current_mavros_mode_ = msg->mode;
  armed_ = msg->armed;
}

// ── MPC 状态回调（JSON 解析） ────────────────────────────
// 期望 JSON 载荷: {"state": str, "success": bool, "fail_count": int,
//                  "solve_time_ms": float, "hold": bool,
//                  "error": str (可选), "standby_reason": str (可选)}。
// JSON 解析失败时回退到子串匹配(向后兼容)。
void ModeManagerNode::mpc_status_callback_(const std_msgs::msg::String::SharedPtr msg) {
  try {
    auto payload = nlohmann::json::parse(msg->data);
    mpc_ok_             = payload.value("success", false);
    mpc_fail_count_     = payload.value("fail_count", 0);
    mpc_solve_time_ms_  = payload.value("solve_time_ms", 0.0);
    mpc_hold_           = payload.value("hold", false);
    mpc_state_          = payload.value("state", "UNKNOWN");
    mpc_standby_reason_ = payload.value("standby_reason", "");
  } catch (const nlohmann::json::exception& e) {
    // Legacy: 任何 "error" 子串标记为失败
    std::string lower = msg->data;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    mpc_ok_ = lower.find("error") == std::string::npos;
    mpc_hold_ = false;
    mpc_state_ = "UNKNOWN";
    mpc_standby_reason_.clear();
  }
  last_mpc_status_time_ = steady_now();
  safety_.mark_mpc_status(last_mpc_status_time_);
  ++mpc_status_seq_;
}

// ── 里程计回调 ───────────────────────────────────────────
void ModeManagerNode::odom_callback_(const nav_msgs::msg::Odometry::SharedPtr msg) {
  x_ = msg->pose.pose.position.x;
  y_ = msg->pose.pose.position.y;
  speed_ = std::hypot(msg->twist.twist.linear.x, msg->twist.twist.linear.y);
  odom_received_ = true;
  last_odom_rx_ = steady_now();
  safety_.update_odom(x_, y_, 0.0, speed_, last_odom_rx_);
}

// ── 电池回调 ─────────────────────────────────────────────
// 电压走 update_battery() 独立域,而非 update_odom():用电池话题刷新
// odom 看门狗会让 GPS/EKF 断流后 odom failsafe 永远不触发 (P0)。
void ModeManagerNode::battery_callback_(const sensor_msgs::msg::BatteryState::SharedPtr msg) {
  double v = msg->voltage;
  if (!std::isnan(v) && v > 0.0) {
    voltage_ = v;
    battery_received_ = true;
    last_battery_rx_ = steady_now();
    safety_.update_battery(voltage_, last_battery_rx_);
  }
}

// ── 路径回调 ─────────────────────────────────────────────
void ModeManagerNode::path_callback_(const nav_msgs::msg::Path::SharedPtr /*msg*/) {
  path_ever_received_ = true;
  safety_.update_path(true, steady_now());
}

// ── 周期性安全监控与模式管理 ─────────────────────────────
void ModeManagerNode::monitor_loop_() {
  double now = steady_now();

  // ── 里程计看门狗 ──
  // update_odom() 仅从真实 odom 回调调用,故 check_odom_timeout() 反映传感器新鲜度。
  // 不要在此处刷新它,否则该看门狗会自复位。
  if (!armed_) {
    // 解锁前 MAVROS/EKF 可能仍在启动。不要因尚无里程计就切换模式;
    // 车辆解锁后才开始执行看门狗。
    safety_.set_odom_watchdog("", now);
  } else if (!odom_received_) {
    safety_.set_odom_watchdog("No odometry received", now);
  } else if (safety_.check_odom_timeout(now)) {
    double dt = now - last_odom_rx_;
    std::ostringstream oss;
    oss << "Odometry timeout: " << std::fixed << std::setprecision(1) << dt << "s";
    safety_.set_odom_watchdog(oss.str(), now);
  } else {
    safety_.set_odom_watchdog("", now);
  }

  // ── MPC 求解器健康状况 ──
  // 仅在 MPC 处于 ACTIVE 或 HOLD 时才有意义。
  // STANDBY/UNKNOWN 表示 MPC 根本没在尝试解算(如错误 FCU 模式、未解锁、无路径)
  // ——把这些计为"求解失败"会在约 2Hz 误触 failsafe。这些状态下镜像 MPC 上报的
  // fail_count(STANDBY 时恒为 0)并跳过增量更新。
  if (mpc_state_ == "ACTIVE" || mpc_state_ == "HOLD") {
    // 仅当自上轮监控以来收到过新 status 才喂 update_solver: 用 2Hz 监控节拍
    // 重复消费同一份陈旧失败会把 fail_count 膨胀, 提前触发 RTL,
    // MPC 自身 HOLD 缓冲形同虚设。
    if (mpc_status_seq_ != last_status_seq_used_) {
      last_status_seq_used_ = mpc_status_seq_;
      if (mpc_fail_count_ > safety_.solver_fail_count()) {
        safety_.set_solver_fail_count(mpc_fail_count_);
      }
      safety_.update_solver(mpc_ok_, mpc_solve_time_ms_, now);
    }
  } else {
    // STANDBY / UNKNOWN: 保持同步但不累积求解失败
    last_status_seq_used_ = mpc_status_seq_;
    safety_.set_solver_fail_count(mpc_fail_count_);
    safety_.clear_solver_flags(now);
  }

  // ── /mpc/status 新鲜度看门狗 ──
  // MPC 节点在 ACTIVE/HOLD 期间死亡时,mpc_state_ 冻结在最后值,而 FCU 会
  // 锁存最后一条速度指令(GUIDED 无 setpoint 超时)——这正是必须触发
  // failsafe 的场景。未解锁时不武装(码头调试),与 odom 看门狗同一策略。
  if (armed_ && (mpc_state_ == "ACTIVE" || mpc_state_ == "HOLD")) {
    if (safety_.check_mpc_status_timeout(now)) {
      double dt = now - last_mpc_status_time_;
      std::ostringstream oss;
      oss << "MPC status timeout: " << std::fixed << std::setprecision(1)
          << dt << "s";
      safety_.set_mpc_status_watchdog(oss.str(), now);
    } else {
      safety_.set_mpc_status_watchdog("", now);
    }
  } else {
    safety_.set_mpc_status_watchdog("", now);
  }

  // ── 路径更新看门狗 ──
  // 仅在已解锁时监视 (与 odom 看门狗同一策略): 2026-09-03 实测中 mavros 未
  // 连接、armed=false, 但空路径流让看门狗武装, 规划器一次停发即 FAILSAFE
  // → RTL 0.5s 无限重发。未解锁时规划器停发不应拉响 failsafe。
  if (armed_ && path_ever_received_) {
    safety_.update_path(false, now);
  }

  // ── 电池遥测看门狗 (WARNING 级) ──
  // 曾收到过电池话题但已断流, 低电量 failsafe 变盲; 只提醒不 RTL。
  if (battery_received_ && (now - last_battery_rx_) > battery_timeout_s_) {
    std::ostringstream oss;
    oss << "No battery telemetry for " << std::fixed << std::setprecision(1)
        << (now - last_battery_rx_) << "s";
    safety_.set_battery_watchdog(oss.str(), now);
  } else {
    safety_.set_battery_watchdog("", now);
  }

  // ── 故障保护检查 ──
  if (safety_.failsafe_active()) {
    auto flags = safety_.active_flags();
    std::string flag_str;
    for (size_t i = 0; i < flags.size(); ++i) {
      if (i > 0) flag_str += ", ";
      flag_str += flags[i];
    }
    if (failsafe_mode_ == "report") {
      // 测试期模式: 只报错不切模式, 控制权完全留给人工。
      // 自动恢复 (auto_switch) 也被下方 return 抑制。
      RCLCPP_ERROR_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                            "FAILSAFE 持续! Flags: [%s] "
                            "(report 模式: 不切换模式, 请人工接管)",
                            flag_str.c_str());
    } else if (current_mavros_mode_ != failsafe_mode_) {
      if (rtl_attempts_ < max_rtl_retries_) {
        RCLCPP_ERROR(this->get_logger(), "FAILSAFE triggered! Flags: [%s]",
                     flag_str.c_str());
        switch_mode_(failsafe_mode_);
        ++rtl_attempts_;
      } else {
        // 2026-09-03 实测教训: FCU 链路断时 set_mode 永远无效、mode 永远
        // 变不成目标模式, 无限重发只是指令洪水。达到上限后停止重发。
        RCLCPP_ERROR_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                              "FAILSAFE 持续, 但 %s 已连发 %d 次仍未生效 — "
                              "检查 FCU 链路, 已停止重发",
                              failsafe_mode_.c_str(), rtl_attempts_);
      }
    }
    return;
  }
  // failsafe 解除后重置重试计数, 下次 failsafe 仍能正常发起
  rtl_attempts_ = 0;

  // ── 自动模式切换 ──
  // 触发条件: armed 且不在 GUIDED,且 MPC 有意愿解算 ——
  //   (1) 当前正在成功解算(legacy 行为),或
  //   (2) MPC 因 wrong_mode 进入 STANDBY(没切到 GUIDED 之前永远不会
  //       success,需要由 mode_manager 主动切过去打破死锁)
  // 人工接管冷却: 模式刚被改变(如操作手切 MANUAL)后的冷却期内不拉回;
  // failsafe RTL 在上方已 return, 不受冷却影响。
  bool auto_switch = this->get_parameter("auto_mode_switch").as_bool();
  bool in_takeover_cooldown =
      (now - last_mode_change_) < takeover_cooldown_s_;
  if (in_takeover_cooldown && current_mavros_mode_ != "GUIDED") {
    RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "人工接管冷却期内, 暂停自动切回 GUIDED");
  }
  if (!in_takeover_cooldown && auto_switch && armed_ &&
      current_mavros_mode_ != "GUIDED") {
    bool needs_guided =
        mpc_ok_ ||
        (mpc_state_ == "STANDBY" &&
         mpc_standby_reason_.rfind("wrong_mode", 0) == 0);
    if (needs_guided) {
      switch_mode_("GUIDED");
    }
  }

  // ── 记录警告日志 ──
  auto flags = safety_.active_flags();
  if (safety_.warning_active() && !flags.empty()) {
    for (const auto& flag : flags) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "Safety: %s", flag.c_str());
    }
  }
}

// ── 模式切换 ─────────────────────────────────────────────
bool ModeManagerNode::switch_mode_(const std::string& mode) {
  if (current_mavros_mode_ == mode) return true;

  if (!set_mode_cli_->service_is_ready()) {
    RCLCPP_ERROR(this->get_logger(), "SetMode service not ready");
    return false;
  }

  auto req = std::make_shared<mavros_msgs::srv::SetMode::Request>();
  req->custom_mode = mode;
  // 结果确认: 发后不管会让 failsafe 静默失效, 这里至少把拒绝暴露到日志
  set_mode_cli_->async_send_request(
      req, [this](rclcpp::Client<mavros_msgs::srv::SetMode>::SharedFuture f) {
        try {
          auto resp = f.get();
          if (!resp->mode_sent) {
            RCLCPP_ERROR(this->get_logger(),
                         "SetMode 请求被拒绝 (mode_sent=false): failsafe 重试"
                         "由监控循环继续发起, 请检查 FCU 模式表");
          }
        } catch (const std::exception& e) {
          RCLCPP_ERROR(this->get_logger(), "SetMode 结果获取失败: %s", e.what());
        }
      });
  RCLCPP_INFO(this->get_logger(), "Switching mode: %s → %s",
              current_mavros_mode_.c_str(), mode.c_str());
  return true;
}

// ── 解锁/上锁 ───────────────────────────────────────────
bool ModeManagerNode::request_arm(bool arm) {
  if (!cmd_arming_cli_->service_is_ready()) {
    RCLCPP_ERROR(this->get_logger(), "Arming service not ready");
    return false;
  }
  auto req = std::make_shared<mavros_msgs::srv::CommandBool::Request>();
  req->value = arm;
  cmd_arming_cli_->async_send_request(
      req, [this](rclcpp::Client<mavros_msgs::srv::CommandBool>::SharedFuture f) {
        try {
          auto resp = f.get();
          if (!resp->success) {
            RCLCPP_ERROR(this->get_logger(), "Arming 请求被飞控拒绝");
          }
        } catch (const std::exception& e) {
          RCLCPP_ERROR(this->get_logger(), "Arming 结果获取失败: %s", e.what());
        }
      });
  return true;
}

// ── 便捷模式切换方法 ─────────────────────────────────────
bool ModeManagerNode::switch_to_guided() { return switch_mode_("GUIDED"); }
bool ModeManagerNode::switch_to_manual() { return switch_mode_("MANUAL"); }
bool ModeManagerNode::switch_to_rtl()    { return switch_mode_("RTL"); }
bool ModeManagerNode::switch_to_hold()   { return switch_mode_("HOLD"); }

}  // namespace usv_safety
