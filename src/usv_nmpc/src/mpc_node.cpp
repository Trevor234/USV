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
 * @file mpc_node.cpp
 * @brief USV MPC 控制器 ROS 2 节点实现。
 */

#include "usv_nmpc/mpc_node.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <cstring>
#include <nlohmann/json.hpp>

using namespace std::chrono_literals;//引用所有字面量“10s” “10ms”等

namespace usv_mpc {

namespace {
double steady_now() {
  auto now = std::chrono::steady_clock::now();
  return std::chrono::duration<double>(now.time_since_epoch()).count();
}
}  // namespace

MpcControllerNode::MpcControllerNode()
    : Node("mpc_controller_node") {
  declare_parameters_();
  load_config_();
  init_mpc_solver_();
  init_state_();
  init_pubsub_();

  RCLCPP_INFO(this->get_logger(),
              "MPC 控制器已启动 | 模式=dynamic | dt=%.1fs | N=%d | 类型=NMPC (动力学) | backend=%s | output=rc_override",
              mpc_dt_, horizon_, mpc_ ? mpc_->backend() : "none");

  timer_ = this->create_wall_timer(
      std::chrono::duration<double>(mpc_dt_),
      std::bind(&MpcControllerNode::control_loop_, this),
      control_cb_group_);
}

MpcControllerNode::MpcControllerNode(std::unique_ptr<DynamicMpc> solver)
    : Node("mpc_controller_node"), mpc_(std::move(solver)) {
  declare_parameters_();
  load_config_();
  init_state_();
  init_pubsub_();
  timer_ = this->create_wall_timer(
      std::chrono::duration<double>(mpc_dt_),
      std::bind(&MpcControllerNode::control_loop_, this),
      control_cb_group_);
  timer_->cancel();
}

MpcControllerNode::~MpcControllerNode() {
  // safe_shutdown 由 main 在 rclpy::shutdown 前显式调用
}

// ── 参数声明 ──
// 默认值 = 实船部署值 (mpc_params_B.yaml + usv_params_B.yaml 2026-09-03
// 阶段3 辨识): yaml 缺失/漏传时落在实船模型上, 而不是静默换成 30kg 仿真船。
// 改动 yaml 后须同步此处 (此前默认值是仿真船参数, 与注释声称的"对齐"不符)。
void MpcControllerNode::declare_parameters_() {
  this->declare_parameter("control_mode", std::string("dynamic"));
  this->declare_parameter("mpc_dt", 0.2);
  this->declare_parameter("horizon", 20);
  this->declare_parameter("odom_topic", std::string("/mavros/local_position/odom"));
  this->declare_parameter("imu_topic", std::string("/mavros/imu/data"));
  this->declare_parameter("path_topic", std::string("/path/reference"));
  this->declare_parameter("profile_topic", std::string("/path/reference_profile"));
  this->declare_parameter("state_topic", std::string("/mavros/state"));
  this->declare_parameter("rc_override_topic", std::string("/mavros/rc/override"));
  this->declare_parameter("status_topic", std::string("/mpc/status"));
  this->declare_parameter("predicted_trajectory_topic", std::string("/mpc/predicted_trajectory"));
  this->declare_parameter("path_frame", std::string("map"));
  this->declare_parameter("require_fcu_state", true);
  this->declare_parameter("publish_predicted", true);
  this->declare_parameter("max_solve_time_ms", 200.0);
  this->declare_parameter("solver_hold_threshold", 5);
  // FCU 模式门禁默认值 = 本节点的输出语义: rc_override 只在 MANUAL 下经
  // ArduRover pilot 输入链生效。曾默认为 GUIDED (方案 A 的语义), 而
  // real.launch 不传该参数, 方案 B 实船因此永远 wrong_mode STANDBY。
  // 现在两份 mpc_params_*.yaml 各自声明, 此默认值只兜底裸启动。
  this->declare_parameter("allowed_fcu_modes", std::vector<std::string>{"MANUAL"});
  this->declare_parameter("state_timeout_s", 5.0);
  // MAVROS local odom 在 EKF/GPS 更新期间可能短暂停流 (与 mpc_params_B.yaml 对齐)
  this->declare_parameter("odom_timeout_s", 3.0);
  this->declare_parameter("reference_start_offset", 8);
  this->declare_parameter("cruise_speed", 1.0);
  this->declare_parameter("progress_window_forward_m", 6.0);
  this->declare_parameter("progress_window_back_m", 1.0);
  this->declare_parameter("progress_end_guard_m", 5.0);
  this->declare_parameter("goal_tolerance_m", 2.0);
  this->declare_parameter("max_initial_heading_step_rad", 0.7854);
  this->declare_parameter("align_turn_rate_rad_s", 0.5);
  this->declare_parameter("align_min_speed_mps", 0.4);
  this->declare_parameter("enable_large_heading_forward_assist", true);
  this->declare_parameter("align_heading_threshold_deg", 60.0);
  this->declare_parameter("align_speed_threshold_mps", 0.3);
  this->declare_parameter("align_min_net_thrust_n", 8.0);
  this->declare_parameter("align_reverse_thrust_floor_n", -5.0);

  // NMPC参数 (mpc_params_B.yaml: 针对 14.2 kg / 30 N 实船整定)
  this->declare_parameter("dynamic.Q", std::vector<double>{20.0, 20.0, 50.0, 8.0, 1.0, 8.0});
  this->declare_parameter("dynamic.R", std::vector<double>{0.05, 0.05});
  this->declare_parameter("dynamic.Rd", std::vector<double>{0.2, 0.2});
  this->declare_parameter("dynamic.Qf_scale", 8.0);
  this->declare_parameter("dynamic.T_max", 30.0);
  this->declare_parameter("dynamic.T_min", -30.0);
  this->declare_parameter("dynamic.dT_max", 80.0);
  this->declare_parameter("dynamic.dt", 0.2);

  // RC 映射与标定死区补偿
  this->declare_parameter("rc_steering_channel", 0);
  this->declare_parameter("rc_throttle_channel", 2);
  this->declare_parameter("rc_pwm_min", 1100);
  this->declare_parameter("rc_pwm_center", 1500);
  this->declare_parameter("rc_pwm_max", 1900);
  // ArduRover RC1 舵向符号与 NMPC (TR-TL) 相反 (2026-07 实船标定,
  // 与 mpc_params_B.yaml 一致)。默认必须为 -1, 避免配置缺失时闭环正反馈画圈。
  this->declare_parameter("steering_sign", -1.0);
  this->declare_parameter("throttle_sign", 1.0);
  this->declare_parameter("steering_gain", 0.75);
  this->declare_parameter("throttle_gain", 1.0);
  this->declare_parameter("deadband_compensation", true);
  this->declare_parameter("pwm_deadband_forward", 1600);
  this->declare_parameter("pwm_deadband_reverse", 1400);
  this->declare_parameter("deadband_min_thrust_n", 0.5);
  this->declare_parameter("use_quadratic_model", true);
  this->declare_parameter("quad_coeff_a", 6.378451e-5);
  this->declare_parameter("quad_coeff_b", 0.1280703);

  // 船体参数 (vehicle.* = usv_params_B.yaml 实船 14.2kg / 2026-09-03 阶段3)
  this->declare_parameter("vehicle.mass", 14.2);
  this->declare_parameter("vehicle.Iz", 2.13);
  this->declare_parameter("vehicle.xg", 0.12);
  this->declare_parameter("vehicle.d_thruster", 0.25);
  this->declare_parameter("vehicle.Xu_dot", -2.0);
  this->declare_parameter("vehicle.Yv_dot", -8.0);
  this->declare_parameter("vehicle.Yr_dot", 0.0);
  this->declare_parameter("vehicle.Nv_dot", -0.363545);
  this->declare_parameter("vehicle.Nr_dot", -3.41);   // 阶段3: was -1.621220
  this->declare_parameter("vehicle.Xu", -2.272063);
  this->declare_parameter("vehicle.Yv", -2.629019);
  this->declare_parameter("vehicle.Yr", 0.0);          // 置零
  this->declare_parameter("vehicle.Nv", 0.0);          // 置零
  this->declare_parameter("vehicle.Nr", -3.105);      // 阶段3: was -4.286144
  this->declare_parameter("vehicle.Xuu", -11.571784);
  this->declare_parameter("vehicle.Yvv", -0.05);
  this->declare_parameter("vehicle.Yrr", 0.0);         // 置零
  this->declare_parameter("vehicle.Nvv", 0.0);         // 置零
  this->declare_parameter("vehicle.Nrr", -0.71);       // 阶段3: was -0.001
}

void MpcControllerNode::load_config_() {
  // 此工作目录仅 NMPC (动力学);control_mode 仅 dynamic/idle
  std::string mode_str = this->get_parameter("control_mode").as_string();
  if (mode_str != "dynamic" && mode_str != "idle") {
    RCLCPP_ERROR(this->get_logger(),
                 "control_mode='%s' 不支持 (仅 dynamic/idle), fallback IDLE", mode_str.c_str());
  }

  mpc_dt_ = this->get_parameter("mpc_dt").as_double();
  horizon_ = this->get_parameter("horizon").as_int();
  max_solve_time_ms_ = this->get_parameter("max_solve_time_ms").as_double();
  require_fcu_state_ = this->get_parameter("require_fcu_state").as_bool();
  path_frame_ = this->get_parameter("path_frame").as_string();
  publish_predicted_ = this->get_parameter("publish_predicted").as_bool();
  solver_hold_threshold_ = this->get_parameter("solver_hold_threshold").as_int();
  allowed_fcu_modes_ = this->get_parameter("allowed_fcu_modes").as_string_array();
  state_timeout_s_ = this->get_parameter("state_timeout_s").as_double();
  odom_timeout_s_ = this->get_parameter("odom_timeout_s").as_double();
  reference_start_offset_ = this->get_parameter("reference_start_offset").as_int();
  cruise_speed_ = this->get_parameter("cruise_speed").as_double();
  progress_window_forward_m_ = this->get_parameter("progress_window_forward_m").as_double();
  progress_window_back_m_ = this->get_parameter("progress_window_back_m").as_double();
  progress_end_guard_m_ = this->get_parameter("progress_end_guard_m").as_double();
  goal_tolerance_m_ = this->get_parameter("goal_tolerance_m").as_double();
  max_initial_heading_step_rad_ = this->get_parameter("max_initial_heading_step_rad").as_double();
  align_turn_rate_rad_s_ = this->get_parameter("align_turn_rate_rad_s").as_double();
  align_min_speed_mps_ = this->get_parameter("align_min_speed_mps").as_double();
  enable_large_heading_forward_assist_ =
      this->get_parameter("enable_large_heading_forward_assist").as_bool();
  align_heading_threshold_deg_ =
      this->get_parameter("align_heading_threshold_deg").as_double();
  align_speed_threshold_mps_ =
      this->get_parameter("align_speed_threshold_mps").as_double();
  align_min_net_thrust_n_ =
      this->get_parameter("align_min_net_thrust_n").as_double();
  align_reverse_thrust_floor_n_ =
      this->get_parameter("align_reverse_thrust_floor_n").as_double();

  // 输出后端 × FCU 模式契约自检: rc_override 只在 ArduRover MANUAL 模式下
  // 经 pilot 输入链 (channel_steer/channel_throttle) 成为舵/油主控制。
  // GUIDED 由自身 submode 驱动: CH1 转向被忽略, CH3 仅作 speed nudge
  // (且限 WP/Heading/TurnRate 子模式), 无 target 时 Stop/Loiter 停车。
  // allowed_fcu_modes 不含 MANUAL 时 MPC 会永远 wrong_mode STANDBY 或
  // (更糟) 在 GUIDED 下解算但船无响应, 启动时显式告警。
  if (!allowed_fcu_modes_.empty()) {
    bool has_manual = false;
    for (const auto& m : allowed_fcu_modes_) {
      if (m == "MANUAL") { has_manual = true; break; }
    }
    if (!has_manual) {
      std::string modes;
      for (const auto& m : allowed_fcu_modes_) {
        modes += (modes.empty() ? "" : ",") + m;
      }
      RCLCPP_WARN(this->get_logger(),
                  "allowed_fcu_modes=[%s] 不含 MANUAL: RC 覆写在非 MANUAL "
                  "模式下不是舵/油主控制, 确认方案 B 的 FCU 模式配置",
                  modes.c_str());
    }
  }
  if (!require_fcu_state_) {
    RCLCPP_WARN(this->get_logger(),
                "require_fcu_state=false: armed/mode 检查全部跳过, MPC 会在"
                "任意 FCU 模式下抢占 RC 控制权, 仅限台架调试使用");
  }

  rc_steering_channel_ = this->get_parameter("rc_steering_channel").as_int();
  rc_throttle_channel_ = this->get_parameter("rc_throttle_channel").as_int();
  rc_pwm_min_ = this->get_parameter("rc_pwm_min").as_int();
  rc_pwm_center_ = this->get_parameter("rc_pwm_center").as_int();
  rc_pwm_max_ = this->get_parameter("rc_pwm_max").as_int();
  steering_sign_ = this->get_parameter("steering_sign").as_double();
  throttle_sign_ = this->get_parameter("throttle_sign").as_double();
  steering_gain_ = this->get_parameter("steering_gain").as_double();
  throttle_gain_ = this->get_parameter("throttle_gain").as_double();
  deadband_compensation_ = this->get_parameter("deadband_compensation").as_bool();
  pwm_deadband_forward_ = this->get_parameter("pwm_deadband_forward").as_int();
  pwm_deadband_reverse_ = this->get_parameter("pwm_deadband_reverse").as_int();
  deadband_min_thrust_n_ = this->get_parameter("deadband_min_thrust_n").as_double();
  use_quadratic_model_ = this->get_parameter("use_quadratic_model").as_bool();
  quad_coeff_a_ = this->get_parameter("quad_coeff_a").as_double();
  quad_coeff_b_ = this->get_parameter("quad_coeff_b").as_double();

  const std::size_t rc_channel_count =
      mavros_msgs::msg::OverrideRCIn().channels.size();
  if (rc_steering_channel_ < 0 || rc_throttle_channel_ < 0 ||
      static_cast<std::size_t>(rc_steering_channel_) >= rc_channel_count ||
      static_cast<std::size_t>(rc_throttle_channel_) >= rc_channel_count ||
      rc_steering_channel_ == rc_throttle_channel_ ||
      rc_pwm_min_ >= rc_pwm_center_ || rc_pwm_center_ >= rc_pwm_max_ ||
      pwm_deadband_reverse_ < rc_pwm_min_ ||
      pwm_deadband_reverse_ > rc_pwm_center_ ||
      pwm_deadband_forward_ < rc_pwm_center_ ||
      pwm_deadband_forward_ >= rc_pwm_max_ ||
      !std::isfinite(deadband_min_thrust_n_) || deadband_min_thrust_n_ < 0.0 ||
      !std::isfinite(quad_coeff_a_) || quad_coeff_a_ < 0.0 ||
      !std::isfinite(quad_coeff_b_) || quad_coeff_b_ <= 0.0 ||
      !std::isfinite(steering_sign_) || !std::isfinite(throttle_sign_) ||
      !std::isfinite(steering_gain_) || !std::isfinite(throttle_gain_) ||
      std::abs(std::abs(steering_sign_) - 1.0) > 1e-9 ||
      std::abs(std::abs(throttle_sign_) - 1.0) > 1e-9 ||
      steering_gain_ < 0.0 || throttle_gain_ < 0.0) {
    throw std::runtime_error(
        "RC 映射参数非法: 通道须有效且不同，并满足 pwm_min < pwm_deadband_reverse "
        "<= pwm_center <= pwm_deadband_forward < pwm_max、sign=+-1、gain>=0");
  }
}

void MpcControllerNode::init_mpc_solver_() {
  MpcParams p;
  p.dt = this->get_parameter("dynamic.dt").as_double();
  double prediction_time = static_cast<double>(horizon_) * mpc_dt_;
  p.N = std::max(1, static_cast<int>(std::round(prediction_time / p.dt)));
  dyn_dt_ = p.dt;
  dyn_N_ = p.N;
  dyn_prediction_time_ = prediction_time;

  auto Qv = this->get_parameter("dynamic.Q").as_double_array();
  auto Rv = this->get_parameter("dynamic.R").as_double_array();
  auto Rdv = this->get_parameter("dynamic.Rd").as_double_array();
  // 长度校验: 短数组会让 operator[] 越界 (UB), 启动即失败优于运行段错误
  if (Qv.size() < 6 || Rv.size() < 2 || Rdv.size() < 2) {
    throw std::runtime_error(
        "dynamic.Q/R/Rd 数组长度不足 (需要 >=6/>=2/>=2, 实际 " +
        std::to_string(Qv.size()) + "/" + std::to_string(Rv.size()) + "/" +
        std::to_string(Rdv.size()) + "), 请检查 mpc_params yaml");
  }
  for (int i = 0; i < 6; ++i) p.Q_diag(i) = Qv[i];
  p.R_diag << Rv[0], Rv[1];
  p.Rd_diag << Rdv[0], Rdv[1];
  p.Qf_scale = this->get_parameter("dynamic.Qf_scale").as_double();
  p.T_max = this->get_parameter("dynamic.T_max").as_double();
  p.T_min = this->get_parameter("dynamic.T_min").as_double();
  p.dT_max = this->get_parameter("dynamic.dT_max").as_double();
  // 缓存推力边界 (热路径用)
  dyn_T_max_ = p.T_max;
  dyn_T_min_ = p.T_min;

  // 船体水动力学
  p.hydro.mass = this->get_parameter("vehicle.mass").as_double();
  p.hydro.Iz = this->get_parameter("vehicle.Iz").as_double();
  p.hydro.xg = this->get_parameter("vehicle.xg").as_double();
  p.hydro.d_thruster = this->get_parameter("vehicle.d_thruster").as_double();
  p.hydro.Xu_dot = this->get_parameter("vehicle.Xu_dot").as_double();
  p.hydro.Yv_dot = this->get_parameter("vehicle.Yv_dot").as_double();
  p.hydro.Yr_dot = this->get_parameter("vehicle.Yr_dot").as_double();
  p.hydro.Nv_dot = this->get_parameter("vehicle.Nv_dot").as_double();
  p.hydro.Nr_dot = this->get_parameter("vehicle.Nr_dot").as_double();
  p.hydro.Xu = this->get_parameter("vehicle.Xu").as_double();
  p.hydro.Yv = this->get_parameter("vehicle.Yv").as_double();
  p.hydro.Yr = this->get_parameter("vehicle.Yr").as_double();
  p.hydro.Nv = this->get_parameter("vehicle.Nv").as_double();
  p.hydro.Nr = this->get_parameter("vehicle.Nr").as_double();
  p.hydro.Xuu = this->get_parameter("vehicle.Xuu").as_double();
  p.hydro.Yvv = this->get_parameter("vehicle.Yvv").as_double();
  p.hydro.Yrr = this->get_parameter("vehicle.Yrr").as_double();
  p.hydro.Nvv = this->get_parameter("vehicle.Nvv").as_double();
  p.hydro.Nrr = this->get_parameter("vehicle.Nrr").as_double();

  mpc_ = make_dynamic_mpc(p);
}

void MpcControllerNode::init_state_() {
  x_ = y_ = psi_ = u_ = v_ = r_ = 0.0;
  odom_received_ = imu_received_ = path_received_ = false;
  armed_ = false;
  mode_ = "MANUAL";
  solver_fail_count_ = 0;
  control_count_ = 0;
  last_state_time_ = 0.0;
  last_odom_time_ = 0.0;
  standby_holding_neutral_ = false;
  progress_index_ = 0;
  mission_completed_ = false;
  last_raw_heading_error_rad_ = 0.0;
}

void MpcControllerNode::init_pubsub_() {
  io_cb_group_ = this->create_callback_group(
      rclcpp::CallbackGroupType::Reentrant);//传感器订阅
  control_cb_group_ = this->create_callback_group(
      rclcpp::CallbackGroupType::MutuallyExclusive);//控制定时器

  rclcpp::SubscriptionOptions opts;
  opts.callback_group = io_cb_group_;

  odom_sub_ = this->create_subscription<nav_msgs::msg::Odometry>(
      this->get_parameter("odom_topic").as_string(), rclcpp::SensorDataQoS(),
      std::bind(&MpcControllerNode::odom_callback_, this, std::placeholders::_1), opts);
  imu_sub_ = this->create_subscription<sensor_msgs::msg::Imu>(
      this->get_parameter("imu_topic").as_string(), rclcpp::SensorDataQoS(),
      std::bind(&MpcControllerNode::imu_callback_, this, std::placeholders::_1), opts);
  path_sub_ = this->create_subscription<nav_msgs::msg::Path>(
      this->get_parameter("path_topic").as_string(), 10,
      std::bind(&MpcControllerNode::path_callback_, this, std::placeholders::_1), opts);
  profile_sub_ = this->create_subscription<std_msgs::msg::Float64MultiArray>(
      this->get_parameter("profile_topic").as_string(), 10,
      std::bind(&MpcControllerNode::profile_callback_, this, std::placeholders::_1), opts);
  state_sub_ = this->create_subscription<mavros_msgs::msg::State>(
      this->get_parameter("state_topic").as_string(), 10,
      std::bind(&MpcControllerNode::state_callback_, this, std::placeholders::_1), opts);

  rc_pub_ = this->create_publisher<mavros_msgs::msg::OverrideRCIn>(
      this->get_parameter("rc_override_topic").as_string(), 10);
  traj_pub_ = this->create_publisher<nav_msgs::msg::Path>(
      this->get_parameter("predicted_trajectory_topic").as_string(), 10);
  status_pub_ = this->create_publisher<std_msgs::msg::String>(
      this->get_parameter("status_topic").as_string(), 10);
}

// ── 回调 ─────────────────────────────────────────────────
void MpcControllerNode::odom_callback_(const nav_msgs::msg::Odometry::SharedPtr msg) {
  const auto& p = msg->pose.pose.position;
  const auto& q = msg->pose.pose.orientation;
  const auto& t = msg->twist.twist;
  // NaN/Inf 门禁: 一个污染样本 (GPS 重定位/EKF 发散) 若进入状态,求解器可能
  // 仍返回 status=0 的"成功"解,经 clamp/cast 变成任意 PWM 下发。直接丢弃。
  if (!std::isfinite(p.x) || !std::isfinite(p.y) ||
      !std::isfinite(q.x) || !std::isfinite(q.y) ||
      !std::isfinite(q.z) || !std::isfinite(q.w) ||
      !std::isfinite(t.linear.x) || !std::isfinite(t.linear.y) ||
      !std::isfinite(t.angular.z)) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "odom 含 NaN/Inf, 丢弃该样本");
    return;
  }
  double psi = quaternion_to_yaw(q.x, q.y, q.z, q.w);
  if (!std::isfinite(psi)) {  // 全零四元数等退化输入
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "odom 四元数退化, 丢弃该样本");
    return;
  }
  std::lock_guard<std::mutex> lk(state_lock_);
  x_ = p.x;
  y_ = p.y;
  psi_ = psi;
  u_ = t.linear.x;
  v_ = t.linear.y;
  r_ = t.angular.z;
  odom_received_ = true;
  last_odom_time_ = steady_now();
}

void MpcControllerNode::imu_callback_(const sensor_msgs::msg::Imu::SharedPtr msg) {
  double r = msg->angular_velocity.z;  // 直接陀螺仪角速度, 更灵敏
  if (!std::isfinite(r)) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "IMU 角速度含 NaN/Inf, 丢弃该样本");
    return;
  }
  std::lock_guard<std::mutex> lk(state_lock_);
  r_ = r;
  imu_received_ = true;
}

void MpcControllerNode::path_callback_(const nav_msgs::msg::Path::SharedPtr msg) {
  std::vector<std::array<double, 3>> new_path;
  new_path.reserve(msg->poses.size());
  for (const auto& pose : msg->poses) {
    auto& q = pose.pose.orientation;
    new_path.push_back({pose.pose.position.x, pose.pose.position.y,
                        quaternion_to_yaw(q.x, q.y, q.z, q.w)});
  }

  std::lock_guard<std::mutex> lk(state_lock_);
  const bool changed = !path_received_ ||
      is_substantive_path_change(reference_path_, new_path, 0.5);
  reference_path_ = std::move(new_path);
  reference_path_stamp_ = {static_cast<int>(msg->header.stamp.sec),
                           static_cast<int>(msg->header.stamp.nanosec)};
  path_received_ = !reference_path_.empty();
  if (!path_received_ || reference_path_.size() < 2 || changed) {
    progress_index_ = 0;
    mission_completed_ = false;
  }
}

void MpcControllerNode::profile_callback_(const std_msgs::msg::Float64MultiArray::SharedPtr msg) {
  std::lock_guard<std::mutex> lk(state_lock_);
  // 从 layout.dim 提取标签,解析 stamp (utils 保持纯逻辑,不依赖 ROS 消息)
  std::vector<std::string> labels;
  labels.reserve(msg->layout.dim.size());
  for (const auto& d : msg->layout.dim) labels.push_back(d.label);
  bool ok = false;
  ref_profile_stamp_ = parse_profile_stamp(labels, ok);
  if (!ok) ref_profile_stamp_ = {-1, -1};

  const auto& data = msg->data;
  if (data.size() < 4 || data.size() % 4 != 0) {
    ref_profile_.clear();
    profile_sync_reason_ = "empty_or_malformed_profile";
    return;
  }
  size_t m = data.size() / 4;
  ref_profile_.clear();
  ref_profile_.reserve(m);
  for (size_t i = 0; i < m; ++i) {
    ref_profile_.push_back({data[4*i], data[4*i+1], data[4*i+2], data[4*i+3]});
  }
}

void MpcControllerNode::state_callback_(const mavros_msgs::msg::State::SharedPtr msg) {
  std::lock_guard<std::mutex> lk(state_lock_);
  armed_ = msg->armed;
  mode_ = msg->mode;
  last_state_time_ = steady_now();
}

// ── 控制循环 ─────────────────────────────────────────────
bool MpcControllerNode::is_fcu_mode_allowed_() const {
  if (allowed_fcu_modes_.empty()) return true;
  for (const auto& m : allowed_fcu_modes_) {
    if (m == mode_) return true;
  }
  return false;
}

std::pair<bool, std::string> MpcControllerNode::can_solve_() const {
  double now = steady_now();
  if (!odom_received_) return {false, "no_odom"};
  if (odom_timeout_s_ > 0.0 && (now - last_odom_time_) > odom_timeout_s_)
    return {false, "odom_timeout"};
  if (!path_received_ || reference_path_.size() < 2) return {false, "no_path"};
  if (mission_completed_) return {false, "mission_complete"};
  if (require_fcu_state_) {
    if (last_state_time_ == 0.0) return {false, "no_state"};
    if (state_timeout_s_ > 0.0 && (now - last_state_time_) > state_timeout_s_)
      return {false, "state_timeout"};
    if (!armed_) return {false, "disarmed"};
    if (!is_fcu_mode_allowed_()) return {false, "wrong_mode(" + mode_ + ")"};
  }
  return {true, ""};
}

void MpcControllerNode::enter_standby_(const std::string& reason) {
  bool hold_neutral = false;
  {
    std::lock_guard<std::mutex> lk(state_lock_);
    if (!require_fcu_state_) {
      hold_neutral = true;
    } else {
      const double now = steady_now();
      const bool state_fresh = last_state_time_ > 0.0 &&
          (state_timeout_s_ <= 0.0 || (now - last_state_time_) <= state_timeout_s_);
      hold_neutral = state_fresh && armed_ && is_fcu_mode_allowed_();
    }
  }

  bool transition = (prev_state_ != "STANDBY");
  if (transition) {
    solver_fail_count_ = 0;
    last_commanded_thrust_.setZero();
    has_last_thrust_ = false;
    if (mpc_) mpc_->reset_warmstart();
    RCLCPP_INFO(this->get_logger(), "MPC → STANDBY: %s", reason.c_str());
  }

  if (hold_neutral) {
    // 飞控已解锁且处于允许模式 (如 MANUAL) 时持续发送中立 PWM 停船，不依赖遥控器回中
    publish_rc_override_(Eigen::Vector2d::Zero());
    standby_holding_neutral_ = true;
  } else if (transition || standby_holding_neutral_) {
    // 未解锁/切离允许模式/状态失联时释放 RC 覆写，避免抢占遥控器或其他模式控制权
    release_rc_override_();
    standby_holding_neutral_ = false;
  }

  prev_state_ = "STANDBY";
  publish_standby_status_(reason);
  RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                       "MPC 等待飞控就绪: %s", reason.c_str());
}

void MpcControllerNode::control_loop_() {
  std::pair<bool, std::string> cs;
  bool armed; std::string mode;
  {
    std::lock_guard<std::mutex> lk(state_lock_);
    cs = can_solve_();
    armed = armed_;
    mode = mode_;
  }
  if (!cs.first) { enter_standby_(cs.second); return; }

  if (prev_state_ != "ACTIVE") {
    RCLCPP_INFO(this->get_logger(), "MPC → ACTIVE: armed=%d, mode=%s", armed, mode.c_str());
    solver_fail_count_ = 0;
    standby_holding_neutral_ = false;
    std::lock_guard<std::mutex> lk(state_lock_);
    if (progress_index_ > 0 && reference_path_.size() >= 2) {
      const double d_prog = std::hypot(
          x_ - reference_path_[progress_index_][0],
          y_ - reference_path_[progress_index_][1]);
      const double d_start = std::hypot(
          x_ - reference_path_.front()[0],
          y_ - reference_path_.front()[1]);
      if (d_prog > std::max(progress_window_forward_m_, 8.0) &&
          d_start < 0.5 * d_prog) {
        progress_index_ = 0;
      }
    }
  }
  prev_state_ = "ACTIVE";
  run_dynamic_mpc_();
}

bool MpcControllerNode::enforce_solve_deadline_(SolveInfo& info) {
  bool deadline_miss = max_solve_time_ms_ > 0.0 && info.solve_time_ms > max_solve_time_ms_;
  if (deadline_miss) {
    info.success = false;
    snprintf(info.error, sizeof(info.error), "solve_timeout: %.1fms > %.1fms",
             info.solve_time_ms, max_solve_time_ms_);
  }
  return deadline_miss;
}

void MpcControllerNode::run_dynamic_mpc_() {
  Vector6d current_state;
  Eigen::MatrixXd reference;
  double raw_heading_error_rad = 0.0;
  {
    // C1 修复 (对齐方案 A): can_solve_ 在锁释放后可能被 path_callback_ 抢先清空路径,
    // 不重查会让 build_reference_ 返回全零参考 → 船被命令驶向地图原点。
    std::unique_lock<std::mutex> lk(state_lock_);
    const auto rechecked = can_solve_();
    if (!rechecked.first) {
      // enter_standby_ -> publish_standby_status_ 会再次加 state_lock_, 先释放防死锁
      lk.unlock();
      enter_standby_(rechecked.second);
      return;
    }
    current_state << x_, y_, normalize_angle(psi_), u_, v_, r_;
    MonotonicProgressConfig pcfg;
    pcfg.forward_window_m = progress_window_forward_m_;
    pcfg.back_window_m = progress_window_back_m_;
    pcfg.end_guard_m = progress_end_guard_m_;
    pcfg.is_initial = (progress_index_ == 0);
    const auto prog = select_monotonic_nearest_index(
        reference_path_, x_, y_, progress_index_, pcfg);
    progress_index_ = prog.progress_index;
    if (is_goal_reached(reference_path_, x_, y_, progress_index_,
                        reference_start_offset_, goal_tolerance_m_)) {
      mission_completed_ = true;
      lk.unlock();
      enter_standby_("mission_complete");
      return;
    }
    reference = build_reference_(current_state, prog.nearest_index);
    raw_heading_error_rad = last_raw_heading_error_rad_;
    // 航向偏差若超过 135 度 (例如遭遇强扰动反向): 重置热启动初值, 破坏倒车局部解记忆
    if (reference.cols() > 0 &&
        std::abs(raw_heading_error_rad) > (M_PI * 0.75)) {
      mpc_->reset_warmstart();
    }
  }

  /*u_opt 是当前这一拍要执行的最优控制量,类型是 Eigen::Vector2d。
  在这个项目里它表示左右推进器推力:
  u_opt = [left_thrust, right_thrust]
  
  info 是求解诊断信息,定义在 mpc_solver.hpp:53-62,包含:
  success:求解是否成功
  solve_time_ms:求解耗时
  backend:求解后端
  error:失败信息
  X_pred:预测状态轨迹
  U_pred:预测控制序列
  */
  auto [u_opt, info] = mpc_->solve(current_state, reference);
  const bool time_rejected = enforce_solve_deadline_(info);

  // deadline 拒绝 ≠ 普通求解失败: 迟到解可能已经把候选移进热启动,
  // 且它的"第一拍"对应的是过去的状态。必须立即丢弃并重置热启动,
  // 而不是等连续失败 5 次才归零 —— 那 5 拍下发的全是已确认迟到的解。
  // (对齐方案 A 的 time_rejected 路径; 2026-10-21 修复)
  if (time_rejected) {
    mpc_->reset_warmstart();
    u_opt = has_last_thrust_ ? last_commanded_thrust_ : Eigen::Vector2d::Zero();
  }

  bool in_hold = false;
  if (info.success) {
    solver_fail_count_ = 0;
    if (!time_rejected && enable_large_heading_forward_assist_) {
      LargeHeadingAssistConfig acfg;
      acfg.enabled = enable_large_heading_forward_assist_;
      acfg.heading_threshold_rad = align_heading_threshold_deg_ * M_PI / 180.0;
      acfg.speed_threshold_mps = align_speed_threshold_mps_;
      acfg.min_net_thrust_n = align_min_net_thrust_n_;
      acfg.reverse_thrust_floor_n = align_reverse_thrust_floor_n_;
      acfg.thrust_min = dyn_T_min_;
      acfg.thrust_max = dyn_T_max_;
      u_opt = apply_large_heading_forward_assist(
          u_opt, std::abs(raw_heading_error_rad), current_state(3), acfg);
    }
    if (control_count_ % 5 == 0) publish_predicted_trajectory_(info.X_pred);
  } else {
    solver_fail_count_++;
    if (solver_fail_count_ <= 3) {
      RCLCPP_WARN(this->get_logger(), "NMPC 求解失败: %s  失败计数=%d",
                  info.error, solver_fail_count_);
    }
    if (solver_fail_count_ >= solver_hold_threshold_) {
      in_hold = true;
      u_opt.setZero();
      mpc_->reset_warmstart();
      if (solver_fail_count_ == solver_hold_threshold_) {
        RCLCPP_ERROR(this->get_logger(),
                     "NMPC HOLD 挂起：连续失败 %d 次，正在发布零推力并重置热启动",
                     solver_fail_count_);
      }
    }
  }

  const Eigen::Vector2d applied_thrust = publish_rc_override_(u_opt);
  last_commanded_thrust_ = applied_thrust;
  has_last_thrust_ = true;
  // 求解器 solve() 内部先保存了计划首拍；这里用经过 RC 映射后真正
  // 下发的等效推力覆盖，使下一拍 ΔT 代价和硬约束从执行输入出发。
  mpc_->set_applied_control(applied_thrust);
  publish_status_(info, in_hold, u_opt, applied_thrust);

  control_count_++;
  if (control_count_ % 10 == 0) {
    int steer = rc_pwm_center_, thr = rc_pwm_center_;
    // RC debug 与发布路径调用同一个纯映射函数，重算当前 u_opt。
    thrust_to_rc_pwm_(u_opt, steer, thr);
    RCLCPP_INFO(this->get_logger(),
                "t=%.1fs  位置=(%.1f,%.1f)  计划推力=(%.1f,%.1f)N  "
                "下发等效推力=(%.1f,%.1f)N  RC(steer=%d, throttle=%d)  求解时间=%.0fms",
                control_count_ * mpc_dt_, x_, y_, u_opt(0), u_opt(1),
                applied_thrust(0), applied_thrust(1), steer, thr, info.solve_time_ms);
  }
}

// ── 推力 → RC PWM (用缓存 T_max/T_min) ──
Eigen::Vector2d MpcControllerNode::thrust_to_rc_pwm_(
    const Eigen::Vector2d& thrust, int& steering_pwm, int& throttle_pwm) {
  RcActuationConfig config;
  config.thrust_max = dyn_T_max_;
  config.thrust_min = dyn_T_min_;
  config.pwm_min = rc_pwm_min_;
  config.pwm_center = rc_pwm_center_;
  config.pwm_max = rc_pwm_max_;
  config.steering_sign = steering_sign_;
  config.throttle_sign = throttle_sign_;
  config.steering_gain = steering_gain_;
  config.throttle_gain = throttle_gain_;
  config.deadband_compensation = deadband_compensation_;
  config.pwm_deadband_forward = pwm_deadband_forward_;
  config.pwm_deadband_reverse = pwm_deadband_reverse_;
  config.deadband_min_thrust_n = deadband_min_thrust_n_;
  config.use_quadratic_model = use_quadratic_model_;
  config.quad_coeff_a = quad_coeff_a_;
  config.quad_coeff_b = quad_coeff_b_;
  const RcActuationResult result = thrust_to_rc_actuation(thrust, config);
  steering_pwm = result.steering_pwm;
  throttle_pwm = result.throttle_pwm;
  return result.effective_thrust;
}

Eigen::Vector2d MpcControllerNode::publish_rc_override_(
    const Eigen::Vector2d& thrust) {
  int steer, thr;
  const Eigen::Vector2d applied_thrust =
      thrust_to_rc_pwm_(thrust, steer, thr);
  mavros_msgs::msg::OverrideRCIn msg;
  if (rc_steering_channel_ >= 0 && rc_steering_channel_ < static_cast<int>(msg.channels.size()))
    msg.channels[rc_steering_channel_] = steer;
  if (rc_throttle_channel_ >= 0 && rc_throttle_channel_ < static_cast<int>(msg.channels.size()))
    msg.channels[rc_throttle_channel_] = thr;
  rc_pub_->publish(msg);
  return applied_thrust;
}

void MpcControllerNode::release_rc_override_() {
  // 全零 OverrideRCIn = 释放所有通道
  rc_pub_->publish(mavros_msgs::msg::OverrideRCIn());
}

void MpcControllerNode::publish_status_(const SolveInfo& info, bool in_hold,
                                        const Eigen::Vector2d& commanded_thrust,
                                        const Eigen::Vector2d& applied_thrust) {
  nlohmann::json j;
  j["state"] = in_hold ? "HOLD" : "ACTIVE";
  j["success"] = info.success;
  j["fail_count"] = solver_fail_count_;
  j["solve_time_ms"] = info.solve_time_ms;
  j["max_solve_time_ms"] = max_solve_time_ms_;
  j["deadline_miss"] = (std::strncmp(info.error, "solve_timeout", 13) == 0);
  j["hold"] = in_hold;
  j["control_mode"] = "dynamic";
  j["backend"] = info.backend;
  j["require_fcu_state"] = require_fcu_state_;
  {
    std::lock_guard<std::mutex> lk(state_lock_);
    j["fcu_mode"] = mode_;
    j["allowed_fcu_modes"] = allowed_fcu_modes_;
    j["armed"] = armed_;
    j["path_received"] = path_received_;
    j["path_len"] = reference_path_.size();
    j["progress_index"] = progress_index_;
    j["mission_completed"] = mission_completed_;
    j["profile_synced"] = profile_synced_;
    j["profile_sync_reason"] = profile_sync_reason_;
    j["x"] = x_; j["y"] = y_; j["psi"] = normalize_angle(psi_);
    j["u"] = u_; j["v"] = v_; j["r"] = r_;
  }
  j["dynamic_dt"] = dyn_dt_;
  j["dynamic_N"] = dyn_N_;
  j["prediction_time_s"] = dyn_prediction_time_;
  // tl_n/tr_n 保持“实际/等效下发推力”语义；新增 cmd 字段保存求解器计划值。
  j["tl_n"] = applied_thrust(0);
  j["tr_n"] = applied_thrust(1);
  j["tl_cmd_n"] = commanded_thrust(0);
  j["tr_cmd_n"] = commanded_thrust(1);
  j["actuation_anchor_source"] = deadband_compensation_
      ? (use_quadratic_model_ ? "rc_calibrated_quadratic" : "rc_deadband_linear")
      : "rc_linearized";
  j["actuation_mapping_error_n"] =
      (commanded_thrust - applied_thrust).cwiseAbs().maxCoeff();
  // 对应 RC PWM 诊断字段。
  {
    int steering_pwm = rc_pwm_center_, throttle_pwm = rc_pwm_center_;
    thrust_to_rc_pwm_(commanded_thrust, steering_pwm, throttle_pwm);
    j["steering_pwm"] = steering_pwm;
    j["throttle_pwm"] = throttle_pwm;
  }
  if (!info.success) j["error"] = info.error;

  std_msgs::msg::String msg;
  msg.data = j.dump();
  status_pub_->publish(msg);
}

void MpcControllerNode::publish_standby_status_(const std::string& reason) {
  nlohmann::json j;
  j["state"] = "STANDBY";
  j["success"] = false;
  j["fail_count"] = 0;
  j["solve_time_ms"] = 0.0;
  j["max_solve_time_ms"] = max_solve_time_ms_;
  j["deadline_miss"] = false;
  j["hold"] = false;
  // 与 path/profile 回调 (Reentrant 组) 并发, 共享状态须持锁读取
  {
    std::lock_guard<std::mutex> lk(state_lock_);
    j["path_received"] = path_received_;
    j["path_len"] = reference_path_.size();
    j["progress_index"] = progress_index_;
    j["mission_completed"] = mission_completed_;
    j["profile_synced"] = profile_synced_;
    j["profile_sync_reason"] = profile_sync_reason_;
  }
  j["standby_reason"] = reason;
  // allowed_fcu_modes 在 STANDBY 期间也必须在 (尤其 wrong_mode 时):
  // mode_manager 用它决定自动切到哪个模式, 缺了就只能退回 GUIDED 猜方案。
  {
    std::lock_guard<std::mutex> lk(state_lock_);
    j["allowed_fcu_modes"] = allowed_fcu_modes_;
    j["fcu_mode"] = mode_;
    j["armed"] = armed_;
  }
  std_msgs::msg::String msg;
  msg.data = j.dump();
  status_pub_->publish(msg);
}

void MpcControllerNode::publish_predicted_trajectory_(const Eigen::MatrixXd& X_pred) {
  if (!publish_predicted_ || X_pred.size() == 0) return;
  nav_msgs::msg::Path msg;
  msg.header.stamp = this->get_clock()->now();
  msg.header.frame_id = path_frame_;
  for (int i = 0; i < X_pred.cols(); ++i) {
    geometry_msgs::msg::PoseStamped pose;
    pose.header = msg.header;
    pose.pose.position.x = X_pred(0, i);
    pose.pose.position.y = X_pred(1, i);
    double psi = X_pred(2, i);
    pose.pose.orientation.z = std::sin(psi / 2.0);
    pose.pose.orientation.w = std::cos(psi / 2.0);
    msg.poses.push_back(pose);
  }
  traj_pub_->publish(msg);
}

// ── 参考构建 ───────────────────────────────────────────
Eigen::MatrixXd MpcControllerNode::build_reference_(const Vector6d& current_state, int nearest) {
  const int N = mpc_->N();
  double dt = mpc_->dt();
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(6, N + 1);
  const auto& path = reference_path_;
  if (path.empty()) return ref;

  const int clamped_nearest = std::clamp(nearest, 0, static_cast<int>(path.size()) - 1);
  int idx = std::min(clamped_nearest + std::max(1, reference_start_offset_),
                     static_cast<int>(path.size()) - 1);

  // profile 同步判定
  int profile_len = ref_profile_.empty() ? -1 : static_cast<int>(ref_profile_.size());
  const std::pair<int,int>* p_stamp = (ref_profile_stamp_.first >= 0) ? &ref_profile_stamp_ : nullptr;
  const std::pair<int,int>* path_stamp = (reference_path_stamp_.first >= 0) ? &reference_path_stamp_ : nullptr;
  auto [synced, sync_reason] = profile_sync_state(
      static_cast<int>(path.size()), profile_len, path_stamp, p_stamp);

  if (synced) {
    std::vector<double> times(ref_profile_.size()), vs(ref_profile_.size()), rs(ref_profile_.size());
    for (size_t i = 0; i < ref_profile_.size(); ++i) {
      times[i] = ref_profile_[i][3]; vs[i] = ref_profile_[i][0]; rs[i] = ref_profile_[i][2];
    }
    double t0 = times[idx];
    int j = idx;
    for (int k = 0; k <= N; ++k) {
      double tk = t0 + k * dt;
      RefSample s = sample_path_profile_at_time(path, times, vs, rs, tk, j);
      ref(0, k) = s.x; ref(1, k) = s.y; ref(2, k) = s.psi;
      ref(3, k) = s.v; ref(4, k) = 0.0; ref(5, k) = s.r;
      j = s.j;
    }
    profile_synced_ = true;
    profile_sync_reason_ = sync_reason;
  } else {
    // 回退: 匀速弧长采样
    profile_synced_ = false;
    profile_sync_reason_ = sync_reason;
    std::vector<double> arc;
    arc.push_back(0.0);
    for (int i = idx; i < static_cast<int>(path.size()) - 1; ++i) {
      arc.push_back(arc.back() + std::hypot(path[i+1][0]-path[i][0], path[i+1][1]-path[i][1]));
    }
    for (int k = 0; k <= N; ++k) {
      double s_des = cruise_speed_ * dt * k;
      int j = 0;
      while (j < static_cast<int>(arc.size()) - 1 && arc[j+1] < s_des) ++j;
      int ii = std::min(idx + j, static_cast<int>(path.size()) - 1);
      if (ii < static_cast<int>(path.size()) - 1 && j < static_cast<int>(arc.size()) - 1) {
        double seg_len = arc[j+1] - arc[j];
        if (seg_len > 1e-6) {
          double t = std::clamp((s_des - arc[j]) / seg_len, 0.0, 1.0);
          ref(0, k) = path[ii][0] + t * (path[ii+1][0] - path[ii][0]);
          ref(1, k) = path[ii][1] + t * (path[ii+1][1] - path[ii][1]);
          double dpsi = normalize_angle(path[ii+1][2] - path[ii][2]);
          ref(2, k) = normalize_angle(path[ii][2] + t * dpsi);
        } else {
          ref(0, k) = path[ii][0]; ref(1, k) = path[ii][1]; ref(2, k) = path[ii][2];
        }
      } else {
        ref(0, k) = path[ii][0]; ref(1, k) = path[ii][1]; ref(2, k) = path[ii][2];
      }
      ref(3, k) = cruise_speed_; ref(4, k) = 0.0; ref(5, k) = 0.0;
    }
  }

  // 航向角连续化展开 (Phase Unwrapping) + 起步大航向偏差渐进引导:
  // 保证 ref(2, 0) 与 current_state(2) 无 ±2pi 阶跃, 且偏差 > max_initial_heading_step_rad 时
  // 渐进引导 ref(2, k) 并保持最小前向参考速度 align_min_speed_mps_。
  last_raw_heading_error_rad_ = smooth_reference_heading(
      ref, current_state(2), dt,
      max_initial_heading_step_rad_, align_turn_rate_rad_s_, align_min_speed_mps_);

  return ref;
}

void MpcControllerNode::safe_shutdown() {
  release_rc_override_();
  publish_standby_status_("node_shutdown");
  RCLCPP_INFO(this->get_logger(), "MPC 节点退出: 已发送安全停车指令");
}

}  // namespace usv_mpc
