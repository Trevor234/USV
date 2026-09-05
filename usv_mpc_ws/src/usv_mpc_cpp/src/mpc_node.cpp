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
 * @brief USV MPC 控制器 ROS 2 节点实现 (C++ 版本)。
 *
 * 对应 Python 版本: usv_mpc/mpc_node.py (清理后, 仅 NMPC)
 */

#include "usv_mpc_cpp/mpc_node.hpp"

#include <chrono>
#include <cmath>
#include <functional>
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
              "MPC 控制器已启动 | 模式=dynamic | dt=%.1fs | N=%d | 类型=NMPC (动力学) | backend=%s | output=%s",
              mpc_dt_, horizon_, mpc_ ? mpc_->backend().c_str() : "none",
              output_mode_.c_str());

  timer_ = this->create_wall_timer(
      std::chrono::duration<double>(mpc_dt_),
      std::bind(&MpcControllerNode::control_loop_, this),
      control_cb_group_);
}

MpcControllerNode::~MpcControllerNode() {
  // safe_shutdown 由 main 在 rclpy::shutdown 前显式调用
}

// ── 参数声明 (默认值与清理后的 mpc_params.yaml/usv_params.yaml 对齐) ──
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
  this->declare_parameter("allowed_fcu_modes", std::vector<std::string>{"GUIDED"});
  this->declare_parameter("state_timeout_s", 5.0);
  this->declare_parameter("odom_timeout_s", 1.0);
  this->declare_parameter("reference_start_offset", 3);
  this->declare_parameter("cruise_speed", 1.0);

  // 输出后端: "rc_override" (实机 ArduRover) 或 "vrx_thrust" (VRX Gazebo 直接推力)
  this->declare_parameter("output_mode", std::string("rc_override"));
  this->declare_parameter("vrx_left_thrust_topic", std::string("/wamv/thrusters/left/thrust"));
  this->declare_parameter("vrx_right_thrust_topic", std::string("/wamv/thrusters/right/thrust"));
  this->declare_parameter("vrx_thrust_scale", 25.0);
  this->declare_parameter("vrx_thrust_cmd_max", 1000.0);

  // NMPC参数
  this->declare_parameter("dynamic.Q", std::vector<double>{10.0, 10.0, 50.0, 5.0, 1.0, 5.0});
  this->declare_parameter("dynamic.R", std::vector<double>{0.01, 0.01});
  this->declare_parameter("dynamic.Rd", std::vector<double>{0.1, 0.1});
  this->declare_parameter("dynamic.Qf_scale", 10.0);
  this->declare_parameter("dynamic.T_max", 40.0);
  this->declare_parameter("dynamic.T_min", -20.0);
  this->declare_parameter("dynamic.dT_max", 30.0);
  this->declare_parameter("dynamic.dt", 0.2);

  // RC 映射
  this->declare_parameter("rc_steering_channel", 0);
  this->declare_parameter("rc_throttle_channel", 2);
  this->declare_parameter("rc_pwm_min", 1100);
  this->declare_parameter("rc_pwm_center", 1500);
  this->declare_parameter("rc_pwm_max", 1900);
  // ArduRover RC1 舵向符号与 NMPC (TR-TL) 相反 (2026-07 实船标定,
  // 与 mpc_params_B.yaml 一致)。默认必须为 -1, 避免配置缺失时闭环正反馈画圈。
  this->declare_parameter("steering_sign", -1.0);
  this->declare_parameter("throttle_sign", 1.0);
  this->declare_parameter("steering_gain", 0.25);
  this->declare_parameter("throttle_gain", 0.5);

  // 船体参数 (vehicle.*)
  this->declare_parameter("vehicle.mass", 30.0);
  this->declare_parameter("vehicle.Iz", 8.0);
  this->declare_parameter("vehicle.xg", 0.0);
  this->declare_parameter("vehicle.d_thruster", 0.3);
  this->declare_parameter("vehicle.Xu_dot", -3.0);
  this->declare_parameter("vehicle.Yv_dot", -20.0);
  this->declare_parameter("vehicle.Yr_dot", -0.5);
  this->declare_parameter("vehicle.Nv_dot", -0.5);
  this->declare_parameter("vehicle.Nr_dot", -2.0);
  this->declare_parameter("vehicle.Xu", -8.0);
  this->declare_parameter("vehicle.Yv", -30.0);
  this->declare_parameter("vehicle.Yr", -1.0);
  this->declare_parameter("vehicle.Nv", -1.0);
  this->declare_parameter("vehicle.Nr", -5.0);
  this->declare_parameter("vehicle.Xuu", -15.0);
  this->declare_parameter("vehicle.Yvv", -60.0);
  this->declare_parameter("vehicle.Yrr", -1.0);
  this->declare_parameter("vehicle.Nvv", -1.0);
  this->declare_parameter("vehicle.Nrr", -3.0);
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

  output_mode_ = this->get_parameter("output_mode").as_string();
  if (output_mode_ != "rc_override" && output_mode_ != "vrx_thrust") {
    RCLCPP_ERROR(this->get_logger(),
                 "output_mode='%s' 不支持 (仅 rc_override/vrx_thrust), fallback rc_override",
                 output_mode_.c_str());
    output_mode_ = "rc_override";
  }
  vrx_thrust_scale_ = this->get_parameter("vrx_thrust_scale").as_double();
  vrx_thrust_cmd_max_ = this->get_parameter("vrx_thrust_cmd_max").as_double();

  // 输出后端 × FCU 模式契约自检: rc_override 组合 (ArduRover GUIDED 接受
  // RC override, 2026-07 实船验证) 依赖 allowed_fcu_modes 与部署的模式切换
  // 逻辑一致。若列表不含 GUIDED, MPC 将永远 wrong_mode STANDBY —— 启动时
  // 显式告警, 避免配置漂移静默生效。
  if (output_mode_ == "rc_override" && !allowed_fcu_modes_.empty()) {
    bool has_guided = false;
    for (const auto& m : allowed_fcu_modes_) {
      if (m == "GUIDED") { has_guided = true; break; }
    }
    if (!has_guided) {
      std::string modes;
      for (const auto& m : allowed_fcu_modes_) {
        modes += (modes.empty() ? "" : ",") + m;
      }
      RCLCPP_WARN(this->get_logger(),
                  "output_mode=rc_override 但 allowed_fcu_modes=[%s] 不含 "
                  "GUIDED: 确认该组合与模式管理器的切换逻辑一致",
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
  vrx_left_pub_ = this->create_publisher<std_msgs::msg::Float64>(
      this->get_parameter("vrx_left_thrust_topic").as_string(), 10);
  vrx_right_pub_ = this->create_publisher<std_msgs::msg::Float64>(
      this->get_parameter("vrx_right_thrust_topic").as_string(), 10);
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
  std::lock_guard<std::mutex> lk(state_lock_);
  reference_path_.clear();
  for (const auto& pose : msg->poses) {
    auto& q = pose.pose.orientation;
    reference_path_.push_back({pose.pose.position.x, pose.pose.position.y,
                               quaternion_to_yaw(q.x, q.y, q.z, q.w)});
  }
  reference_path_stamp_ = {static_cast<int>(msg->header.stamp.sec),
                           static_cast<int>(msg->header.stamp.nanosec)};
  path_received_ = !reference_path_.empty();
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
std::pair<bool, std::string> MpcControllerNode::can_solve_() const {
  double now = steady_now();
  if (!odom_received_) return {false, "no_odom"};
  if (odom_timeout_s_ > 0.0 && (now - last_odom_time_) > odom_timeout_s_)
    return {false, "odom_timeout"};
  if (!path_received_ || reference_path_.size() < 2) return {false, "no_path"};
  if (require_fcu_state_) {
    if (last_state_time_ == 0.0) return {false, "no_state"};
    if (state_timeout_s_ > 0.0 && (now - last_state_time_) > state_timeout_s_)
      return {false, "state_timeout"};
    if (!armed_) return {false, "disarmed"};
    if (!allowed_fcu_modes_.empty()) {
      bool allowed = false;
      for (const auto& m : allowed_fcu_modes_) if (m == mode_) { allowed = true; break; }
      if (!allowed) return {false, "wrong_mode(" + mode_ + ")"};
    }
  }
  return {true, ""};
}

void MpcControllerNode::enter_standby_(const std::string& reason) {
  bool transition = (prev_state_ != "STANDBY");
  if (transition) {
    solver_fail_count_ = 0;
    if (mpc_) mpc_->reset_warmstart();
    publish_zero_dynamic_output_();
    RCLCPP_INFO(this->get_logger(), "MPC → STANDBY: %s", reason.c_str());
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
  }
  prev_state_ = "ACTIVE";
  run_dynamic_mpc_();
}

bool MpcControllerNode::enforce_solve_deadline_(SolveInfo& info) {
  bool deadline_miss = max_solve_time_ms_ > 0.0 && info.solve_time_ms > max_solve_time_ms_;
  if (deadline_miss) {
    info.success = false;
    info.error = "solve_timeout: " + std::to_string(info.solve_time_ms) + "ms > " +
                 std::to_string(max_solve_time_ms_) + "ms";
  }
  return deadline_miss;
}

void MpcControllerNode::run_dynamic_mpc_() {
  Vector6d current_state;
  Eigen::MatrixXd reference;
  {
    std::lock_guard<std::mutex> lk(state_lock_);
    current_state << x_, y_, normalize_angle(psi_), u_, v_, r_;
    reference = build_reference_(current_state);
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
  enforce_solve_deadline_(info);

  bool in_hold = false;
  if (info.success) {
    solver_fail_count_ = 0;
    publish_dynamic_output_(u_opt);
    if (control_count_ % 5 == 0) publish_predicted_trajectory_(info.X_pred);
  } else {
    solver_fail_count_++;
    if (solver_fail_count_ <= 3) {
      RCLCPP_WARN(this->get_logger(), "NMPC 求解失败: %s  失败计数=%d",
                  info.error.c_str(), solver_fail_count_);
    }
    if (solver_fail_count_ >= solver_hold_threshold_) {
      in_hold = true;
      u_opt.setZero();
      publish_dynamic_output_(u_opt);
      mpc_->reset_warmstart();
      if (solver_fail_count_ == solver_hold_threshold_) {
        RCLCPP_ERROR(this->get_logger(),
                     "NMPC HOLD 挂起：连续失败 %d 次，正在发布零推力并重置热启动",
                     solver_fail_count_);
      }
    } else {
      publish_dynamic_output_(u_opt);
    }
  }

  publish_status_(info, in_hold, u_opt);

  control_count_++;
  if (control_count_ % 10 == 0) {
    int steer = rc_pwm_center_, thr = rc_pwm_center_;
    // 取最近 RC debug (从 thrust_to_rc 缓存, 简化: 重算当前 u_opt)
    thrust_to_rc_pwm_(u_opt, steer, thr);
    RCLCPP_INFO(this->get_logger(),
                "t=%.1fs  位置=(%.1f,%.1f)  左推力=%.1fN  右推力=%.1fN  RC(steer=%d, throttle=%d)  求解时间=%.0fms",
                control_count_ * mpc_dt_, x_, y_, u_opt(0), u_opt(1), steer, thr,
                info.solve_time_ms);
  }
}

// ── 推力 → RC PWM (对应 Python _thrust_to_rc_pwm, 用缓存 T_max/T_min) ──
void MpcControllerNode::thrust_to_rc_pwm_(const Eigen::Vector2d& thrust,
                                          int& steering_pwm, int& throttle_pwm) {
  double t_max = std::max(dyn_T_max_, 1.0);
  double t_min = std::fabs(std::min(dyn_T_min_, -1.0));
  double left = thrust(0), right = thrust(1);

  double throttle_n = 0.5 * (left + right);
  double throttle_scale = (throttle_n >= 0.0) ? t_max : t_min;
  throttle_n = throttle_sign_ * throttle_gain_ *
               std::clamp(throttle_n / throttle_scale, -1.0, 1.0);

  double steering_span = std::max(t_max, t_min);
  double steering_n = steering_sign_ * steering_gain_ *
                      std::clamp((right - left) / (2.0 * steering_span), -1.0, 1.0);

  auto to_pwm = [&](double val) -> int {
    val = std::clamp(val, -1.0, 1.0);
    double pwm;
    if (val >= 0.0) pwm = rc_pwm_center_ + val * (rc_pwm_max_ - rc_pwm_center_);
    else            pwm = rc_pwm_center_ + val * (rc_pwm_center_ - rc_pwm_min_);
    return static_cast<int>(std::clamp(std::round(pwm),
                                       static_cast<double>(rc_pwm_min_),
                                       static_cast<double>(rc_pwm_max_)));
  };
  steering_pwm = to_pwm(steering_n);
  throttle_pwm = to_pwm(throttle_n);
}

void MpcControllerNode::publish_rc_override_(const Eigen::Vector2d& thrust) {
  int steer, thr;
  thrust_to_rc_pwm_(thrust, steer, thr);
  mavros_msgs::msg::OverrideRCIn msg;
  if (rc_steering_channel_ >= 0 && rc_steering_channel_ < static_cast<int>(msg.channels.size()))
    msg.channels[rc_steering_channel_] = steer;
  if (rc_throttle_channel_ >= 0 && rc_throttle_channel_ < static_cast<int>(msg.channels.size()))
    msg.channels[rc_throttle_channel_] = thr;
  rc_pub_->publish(msg);
}

void MpcControllerNode::publish_dynamic_output_(const Eigen::Vector2d& thrust) {
  if (output_mode_ == "vrx_thrust") {
    publish_vrx_thrust_(thrust);
  } else {
    publish_rc_override_(thrust);
  }
}

void MpcControllerNode::publish_zero_dynamic_output_() {
  if (output_mode_ == "vrx_thrust") {
    release_vrx_thrust_();
  } else {
    release_rc_override_();
  }
}

void MpcControllerNode::release_rc_override_() {
  // 全零 OverrideRCIn = 释放所有通道
  rc_pub_->publish(mavros_msgs::msg::OverrideRCIn());
}

// 对应 Python _publish_vrx_thrust: NMPC [TL,TR] (N) 经 scale/cmd_max 限幅后
// 直接发布到 VRX thruster topic (std_msgs/Float64, 单位 N)。
void MpcControllerNode::publish_vrx_thrust_(const Eigen::Vector2d& thrust) {
  std_msgs::msg::Float64 left, right;
  left.data = std::clamp(thrust(0) * vrx_thrust_scale_,
                         -vrx_thrust_cmd_max_, vrx_thrust_cmd_max_);
  right.data = std::clamp(thrust(1) * vrx_thrust_scale_,
                          -vrx_thrust_cmd_max_, vrx_thrust_cmd_max_);
  vrx_left_pub_->publish(left);
  vrx_right_pub_->publish(right);
}

void MpcControllerNode::release_vrx_thrust_() {
  // VRX thruster 无"释放通道"概念, 零推力即停船
  std_msgs::msg::Float64 left, right;
  left.data = 0.0;
  right.data = 0.0;
  vrx_left_pub_->publish(left);
  vrx_right_pub_->publish(right);
}

void MpcControllerNode::publish_status_(const SolveInfo& info, bool in_hold,
                                        const Eigen::Vector2d& thrust) {
  nlohmann::json j;
  j["state"] = in_hold ? "HOLD" : "ACTIVE";
  j["success"] = info.success;
  j["fail_count"] = solver_fail_count_;
  j["solve_time_ms"] = info.solve_time_ms;
  j["max_solve_time_ms"] = max_solve_time_ms_;
  j["deadline_miss"] = (info.error.rfind("solve_timeout", 0) == 0);
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
    j["profile_synced"] = profile_synced_;
    j["profile_sync_reason"] = profile_sync_reason_;
    j["x"] = x_; j["y"] = y_; j["psi"] = normalize_angle(psi_);
    j["u"] = u_; j["v"] = v_; j["r"] = r_;
  }
  j["dynamic_dt"] = dyn_dt_;
  j["dynamic_N"] = dyn_N_;
  j["prediction_time_s"] = dyn_prediction_time_;
  // 实际推力 (N),供地面站/可视化直接从 /mpc/status 解析。
  j["tl_n"] = thrust(0);
  j["tr_n"] = thrust(1);
  // 对应 RC PWM (与 Python _last_rc_debug 字段对齐)。
  {
    int steering_pwm = rc_pwm_center_, throttle_pwm = rc_pwm_center_;
    thrust_to_rc_pwm_(thrust, steering_pwm, throttle_pwm);
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
    j["profile_synced"] = profile_synced_;
    j["profile_sync_reason"] = profile_sync_reason_;
  }
  j["standby_reason"] = reason;
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

// ── 参考构建 (对应 Python _build_reference) ───────────────
Eigen::MatrixXd MpcControllerNode::build_reference_(const Vector6d& current_state) {
  const int N = mpc_->N();
  double dt = mpc_->dt();
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(6, N + 1);
  const auto& path = reference_path_;
  if (path.empty()) return ref;

  // 最近点 + start_offset
  double best_d = 1e18; int nearest = 0;
  for (size_t i = 0; i < path.size(); ++i) {
    double d = std::hypot(path[i][0] - current_state(0), path[i][1] - current_state(1));
    if (d < best_d) { best_d = d; nearest = static_cast<int>(i); }
  }
  int idx = std::min(nearest + std::max(1, reference_start_offset_),
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
  return ref;
}

void MpcControllerNode::safe_shutdown() {
  publish_zero_dynamic_output_();
  publish_standby_status_("node_shutdown");
  RCLCPP_INFO(this->get_logger(), "MPC 节点退出: 已发送安全停车指令");
}

}  // namespace usv_mpc
