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
 * @brief USV MPC 控制器 ROS 2 节点实现 (C++ 版本, 方案 A 运动学)。
 *
 * 对应 Python 版本: usv_mpc/mpc_node.py (方案 A, MultiThreadedExecutor 版)
 *
 * 结构与方案 B 的 mpc_node.cpp 同构, 逐方法对照移植 (见注释)。差异:
 *   - 输出 TwistStamped (linear.x=u, angular.z=r) 而非 OverrideRCIn
 *   - 参数 kinematic. (无 dynamic. / vehicle. / rc_ 系列)
 *   - 状态 3 维 [x,y,psi] (B 是 6 维 [x,y,psi,u,v,r])
 *   - 参考 [3, N+1] (B 是 [6, N+1])
 *   - status JSON: u_cmd/r_cmd (B 是 tl_n/tr_n + RC 诊断)
 */

#include "usv_mpc_cpp/mpc_node.hpp"

#include <chrono>
#include <cmath>
#include <functional>
#include <nlohmann/json.hpp>

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
              "运动学 MPC 控制器已启动 | 模式=kinematic | dt=%.1fs | N=%d | 方案=A | backend=%s",
              mpc_dt_, horizon_, mpc_ ? mpc_->backend().c_str() : "none");

  timer_ = this->create_wall_timer(
      std::chrono::duration<double>(mpc_dt_),
      std::bind(&MpcControllerNode::control_loop_, this),
      control_cb_group_);
}

MpcControllerNode::~MpcControllerNode() {
  // safe_shutdown 由 main 在 rclcpp::shutdown 前显式调用
}

// ── 参数声明 (默认值与 mpc_params.yaml 对齐; kinematic.* 命名空间) ──
void MpcControllerNode::declare_parameters_() {
  this->declare_parameter("scheme", std::string("A"));
  this->declare_parameter("control_mode", std::string("kinematic"));
  this->declare_parameter("mpc_dt", 0.2);
  this->declare_parameter("horizon", 20);
  this->declare_parameter("odom_topic", std::string("/mavros/local_position/odom"));
  this->declare_parameter("imu_topic", std::string("/mavros/imu/data"));
  this->declare_parameter("path_topic", std::string("/path/reference"));
  this->declare_parameter("profile_topic", std::string("/path/reference_profile"));
  this->declare_parameter("state_topic", std::string("/mavros/state"));
  this->declare_parameter("velocity_topic", std::string("/mavros/setpoint_velocity/cmd_vel"));
  this->declare_parameter("status_topic", std::string("/mpc/status"));
  this->declare_parameter("predicted_trajectory_topic", std::string("/mpc/predicted_trajectory"));
  this->declare_parameter("path_frame", std::string("map"));
  this->declare_parameter("body_frame", std::string("base_link"));
  this->declare_parameter("require_fcu_state", true);
  this->declare_parameter("publish_predicted", true);
  this->declare_parameter("max_solve_time_ms", 200.0);
  this->declare_parameter("solver_hold_threshold", 5);
  this->declare_parameter("allowed_fcu_modes", std::vector<std::string>{"GUIDED"});
  this->declare_parameter("state_timeout_s", 2.0);   // A 用 2.0 (B 用 5.0)
  this->declare_parameter("odom_timeout_s", 1.0);
  this->declare_parameter("reference_start_offset", 1);  // A 用 1 (B 用 3)
  this->declare_parameter("cruise_speed", 1.0);

  // 运动学 MPC 参数 (kinematic.*)
  this->declare_parameter("kinematic.Q", std::vector<double>{10.0, 10.0, 50.0});
  this->declare_parameter("kinematic.R", std::vector<double>{1.0, 1.0});
  this->declare_parameter("kinematic.Qf_scale", 10.0);
  this->declare_parameter("kinematic.u_max", 2.0);
  this->declare_parameter("kinematic.u_min", 0.0);
  this->declare_parameter("kinematic.r_max", 0.5);
  this->declare_parameter("kinematic.du_max", 0.8);
  this->declare_parameter("kinematic.dr_max", 0.5);
  this->declare_parameter("kinematic.dt", 0.2);
  // backend 参数 (C++ 只实现 casadi; 保留参数对齐 Python, 非 ipopt 时 WARN)
  this->declare_parameter("kinematic.backend", std::string("ipopt"));
}

void MpcControllerNode::load_config_() {
  // 此工作目录仅方案 A; scheme 强制 A, control_mode 仅 kinematic/idle
  scheme_ = "A";
  std::string mode_str = this->get_parameter("control_mode").as_string();
  if (mode_str != "kinematic" && mode_str != "idle") {
    RCLCPP_ERROR(this->get_logger(),
                 "control_mode='%s' 不支持 (仅 kinematic/idle), fallback IDLE",
                 mode_str.c_str());
  }

  mpc_dt_ = this->get_parameter("mpc_dt").as_double();
  horizon_ = this->get_parameter("horizon").as_int();
  max_solve_time_ms_ = this->get_parameter("max_solve_time_ms").as_double();
  require_fcu_state_ = this->get_parameter("require_fcu_state").as_bool();
  path_frame_ = this->get_parameter("path_frame").as_string();
  body_frame_ = this->get_parameter("body_frame").as_string();
  publish_predicted_ = this->get_parameter("publish_predicted").as_bool();
  solver_hold_threshold_ = this->get_parameter("solver_hold_threshold").as_int();
  allowed_fcu_modes_ = this->get_parameter("allowed_fcu_modes").as_string_array();
  state_timeout_s_ = this->get_parameter("state_timeout_s").as_double();
  odom_timeout_s_ = this->get_parameter("odom_timeout_s").as_double();
  reference_start_offset_ = this->get_parameter("reference_start_offset").as_int();
  cruise_speed_ = this->get_parameter("cruise_speed").as_double();
  backend_param_ = this->get_parameter("kinematic.backend").as_string();

  // C++ 版只实现 casadi 后端; 若配置要求 acados, 警告并仍用 casadi
  if (backend_param_ == "acados") {
    RCLCPP_WARN(this->get_logger(),
                "kinematic.backend=acados: C++ 版暂未实现运动学 acados codegen, "
                "回退到 casadi (ipopt) 后端");
  }
  // ★ 无 vehicle.* 加载 (运动学无水动力)
  // ★ 无 RC 参数加载
}

void MpcControllerNode::init_mpc_solver_() {
  KinematicMpcParams p;
  p.dt = this->get_parameter("kinematic.dt").as_double();
  double prediction_time = static_cast<double>(horizon_) * mpc_dt_;
  p.N = std::max(1, static_cast<int>(std::round(prediction_time / p.dt)));
  kin_dt_ = p.dt;
  kin_N_ = p.N;
  kin_prediction_time_ = prediction_time;

  auto Qv = this->get_parameter("kinematic.Q").as_double_array();  // 3 维
  for (int i = 0; i < 3; ++i) p.Q_diag(i) = Qv[i];
  auto Rv = this->get_parameter("kinematic.R").as_double_array();  // 2 维
  p.R_diag << Rv[0], Rv[1];
  p.Qf_scale = this->get_parameter("kinematic.Qf_scale").as_double();
  p.u_max = this->get_parameter("kinematic.u_max").as_double();
  p.u_min = this->get_parameter("kinematic.u_min").as_double();
  p.r_max = this->get_parameter("kinematic.r_max").as_double();
  p.du_max = this->get_parameter("kinematic.du_max").as_double();
  p.dr_max = this->get_parameter("kinematic.dr_max").as_double();
  // ★ 无 HydroParams 加载
  // ★ 无 acados cache_dir
  mpc_ = make_kinematic_mpc(p);  // 直接 CasadiKinematicBackend
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
      rclcpp::CallbackGroupType::Reentrant);
  control_cb_group_ = this->create_callback_group(
      rclcpp::CallbackGroupType::MutuallyExclusive);

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

  // ★ vel_pub_ (TwistStamped) 替代 B 的 rc_pub_ (OverrideRCIn)
  vel_pub_ = this->create_publisher<geometry_msgs::msg::TwistStamped>(
      this->get_parameter("velocity_topic").as_string(), 10);
  traj_pub_ = this->create_publisher<nav_msgs::msg::Path>(
      this->get_parameter("predicted_trajectory_topic").as_string(), 10);
  status_pub_ = this->create_publisher<std_msgs::msg::String>(
      this->get_parameter("status_topic").as_string(), 10);
}

// ── 回调 (与 B 几乎逐行相同, 仅 reference_path_ 类型对齐 utils) ──
void MpcControllerNode::odom_callback_(const nav_msgs::msg::Odometry::SharedPtr msg) {
  std::lock_guard<std::mutex> lk(state_lock_);
  x_ = msg->pose.pose.position.x;
  y_ = msg->pose.pose.position.y;
  auto& q = msg->pose.pose.orientation;
  psi_ = quaternion_to_yaw(q.x, q.y, q.z, q.w);
  u_ = msg->twist.twist.linear.x;
  v_ = msg->twist.twist.linear.y;
  r_ = msg->twist.twist.angular.z;
  odom_received_ = true;
  last_odom_time_ = steady_now();
}

void MpcControllerNode::imu_callback_(const sensor_msgs::msg::Imu::SharedPtr msg) {
  std::lock_guard<std::mutex> lk(state_lock_);
  r_ = msg->angular_velocity.z;  // 直接陀螺仪角速度, 更灵敏
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
  // 从 layout.dim 提取标签, 解析 stamp (utils 保持纯逻辑, 不依赖 ROS 消息)
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
    ref_profile_.push_back({data[4 * i], data[4 * i + 1], data[4 * i + 2], data[4 * i + 3]});
  }
}

void MpcControllerNode::state_callback_(const mavros_msgs::msg::State::SharedPtr msg) {
  std::lock_guard<std::mutex> lk(state_lock_);
  armed_ = msg->armed;
  mode_ = msg->mode;
  last_state_time_ = steady_now();
}

// ── 控制循环 (与 B 逐行相同, 状态机逻辑方案无关) ──────────
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
    publish_zero_velocity_();  // ★ 零速度 (B 是 release_rc_override_)
    RCLCPP_INFO(this->get_logger(), "MPC → STANDBY: %s", reason.c_str());
  }
  prev_state_ = "STANDBY";
  publish_standby_status_(reason);
  RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                       "MPC 等待飞控就绪: %s", reason.c_str());
}

void MpcControllerNode::control_loop_() {
  std::pair<bool, std::string> cs;
  bool armed;
  std::string mode;
  {
    std::lock_guard<std::mutex> lk(state_lock_);
    cs = can_solve_();
    armed = armed_;
    mode = mode_;
  }
  if (!cs.first) {
    enter_standby_(cs.second);
    return;
  }

  if (prev_state_ != "ACTIVE") {
    RCLCPP_INFO(this->get_logger(), "MPC → ACTIVE: armed=%d, mode=%s", armed, mode.c_str());
    solver_fail_count_ = 0;
  }
  prev_state_ = "ACTIVE";
  run_kinematic_mpc_();
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

void MpcControllerNode::run_kinematic_mpc_() {
  Eigen::Vector3d current_state;  // ★ 3 维 (B 是 6 维 Vector6d)
  Eigen::MatrixXd reference;
  {
    std::lock_guard<std::mutex> lk(state_lock_);
    current_state << x_, y_, normalize_angle(psi_);
    reference = build_reference_(current_state);
  }

  auto [u_opt, info] = mpc_->solve(current_state, reference);
  bool deadline_miss = enforce_solve_deadline_(info);
  if (deadline_miss) u_opt.setZero();

  bool in_hold = false;
  if (info.success) {
    solver_fail_count_ = 0;
    publish_velocity_cmd_(u_opt);  // ★ Twist (B 是 publish_dynamic_output_)
    if (control_count_ % 5 == 0) publish_predicted_trajectory_(info.X_pred);
  } else {
    solver_fail_count_++;
    if (solver_fail_count_ <= 3) {
      RCLCPP_WARN(this->get_logger(), "MPC 求解失败: %s  失败计数=%d",
                  info.error.c_str(), solver_fail_count_);
    }
    if (solver_fail_count_ >= solver_hold_threshold_) {
      in_hold = true;
      u_opt.setZero();
      publish_velocity_cmd_(u_opt);
      mpc_->reset_warmstart();
      if (solver_fail_count_ == solver_hold_threshold_) {
        RCLCPP_ERROR(this->get_logger(),
                     "MPC HOLD 挂起：连续失败 %d 次，正在发布零速度并重置热启动",
                     solver_fail_count_);
      }
    } else {
      publish_velocity_cmd_(u_opt);
    }
  }

  // 暴露 u_opt / 航向参考给 status (对齐 Python A 的 status 字段)
  publish_status_(info, in_hold, u_opt, current_state, reference);

  control_count_++;
  if (control_count_ % 25 == 0) {  // 约每 5 秒 (对齐 Python A)
    RCLCPP_INFO(this->get_logger(),
                "t=%.1fs  位置=(%.1f,%.1f)  航向=%.0f°  指令=(u=%.2f, r=%.1f°/s)  求解时间=%.0fms",
                control_count_ * mpc_dt_, x_, y_, psi_ * 180.0 / M_PI,
                u_opt(0), u_opt(1) * 180.0 / M_PI, info.solve_time_ms);
  }
}

// ── 输出: TwistStamped (★ 与 B 的 thrust→RC PWM 完全不同, 无映射) ──
void MpcControllerNode::publish_velocity_cmd_(const Eigen::Vector2d& u_opt) {
  geometry_msgs::msg::TwistStamped msg;
  msg.header.stamp = this->get_clock()->now();
  msg.header.frame_id = body_frame_;
  msg.twist.linear.x = u_opt(0);   // u_surge
  msg.twist.linear.y = 0.0;
  msg.twist.angular.z = u_opt(1);  // r_yaw
  vel_pub_->publish(msg);
}

void MpcControllerNode::publish_zero_velocity_() {
  publish_velocity_cmd_(Eigen::Vector2d::Zero());
}

void MpcControllerNode::publish_status_(const SolveInfo& info, bool in_hold,
                                        const Eigen::Vector2d& u_opt,
                                        const Eigen::Vector3d& current_state,
                                        const Eigen::MatrixXd& reference) {
  nlohmann::json j;
  j["state"] = in_hold ? "HOLD" : "ACTIVE";
  j["success"] = info.success;
  j["fail_count"] = solver_fail_count_;
  j["solve_time_ms"] = info.solve_time_ms;
  j["max_solve_time_ms"] = max_solve_time_ms_;
  j["deadline_miss"] = (info.error.rfind("solve_timeout", 0) == 0);
  j["hold"] = in_hold;
  j["scheme"] = scheme_;
  j["control_mode"] = "kinematic";
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
    j["x"] = x_;
    j["y"] = y_;
    j["psi"] = normalize_angle(psi_);
    j["u"] = u_;
    j["v"] = v_;
    j["r"] = r_;
  }
  // ★ 运动学诊断字段 (对齐 Python A 的 status; B 用 tl_n/tr_n + RC 诊断)
  j["kinematic_dt"] = kin_dt_;
  j["kinematic_N"] = kin_N_;
  j["prediction_time_s"] = kin_prediction_time_;
  j["u_cmd"] = u_opt(0);
  j["r_cmd"] = u_opt(1);
  if (reference.cols() > 0) {
    j["psi_ref"] = reference(2, 0);
    j["e_psi"] = normalize_angle(current_state(2) - reference(2, 0));
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
  j["scheme"] = scheme_;
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

// ── 参考构建 (对应 Python _build_reference; ★ 3 维, start_offset=1) ──
Eigen::MatrixXd MpcControllerNode::build_reference_(const Eigen::Vector3d& current_state) {
  const int N = mpc_->N();
  double dt = mpc_->dt();
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(3, N + 1);  // ★ 3 维 (B 是 6)
  const auto& path = reference_path_;
  if (path.empty()) return ref;

  // 最近点 + start_offset
  double best_d = 1e18;
  int nearest = 0;
  for (size_t i = 0; i < path.size(); ++i) {
    double d = std::hypot(path[i][0] - current_state(0), path[i][1] - current_state(1));
    if (d < best_d) {
      best_d = d;
      nearest = static_cast<int>(i);
    }
  }
  int idx = std::min(nearest + std::max(1, reference_start_offset_),
                     static_cast<int>(path.size()) - 1);

  // profile 同步判定
  int profile_len = ref_profile_.empty() ? -1 : static_cast<int>(ref_profile_.size());
  const std::pair<int, int>* p_stamp =
      (ref_profile_stamp_.first >= 0) ? &ref_profile_stamp_ : nullptr;
  const std::pair<int, int>* path_stamp =
      (reference_path_stamp_.first >= 0) ? &reference_path_stamp_ : nullptr;
  auto [synced, sync_reason] = profile_sync_state(
      static_cast<int>(path.size()), profile_len, path_stamp, p_stamp);

  if (synced) {
    std::vector<double> times(ref_profile_.size()), vs(ref_profile_.size()),
        rs(ref_profile_.size());
    for (size_t i = 0; i < ref_profile_.size(); ++i) {
      times[i] = ref_profile_[i][3];
      vs[i] = ref_profile_[i][0];
      rs[i] = ref_profile_[i][2];
    }
    double t0 = times[idx];
    int j = idx;
    for (int k = 0; k <= N; ++k) {
      double tk = t0 + k * dt;
      RefSample s = sample_path_profile_at_time(path, times, vs, rs, tk, j);
      ref(0, k) = s.x;
      ref(1, k) = s.y;
      ref(2, k) = s.psi;
      // ★ 不填 ref(3..5) (运动学参考无 v/v_ref/r_ref; B 填 6 维)
      j = s.j;
    }
    profile_synced_ = true;
    profile_sync_reason_ = sync_reason;
  } else {
    // 回退: 匀速弧长采样 (r_ref=0)
    profile_synced_ = false;
    profile_sync_reason_ = sync_reason;
    std::vector<double> arc;
    arc.push_back(0.0);
    for (int i = idx; i < static_cast<int>(path.size()) - 1; ++i) {
      arc.push_back(arc.back() +
                    std::hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]));
    }
    for (int k = 0; k <= N; ++k) {
      double s_des = cruise_speed_ * dt * k;
      int j = 0;
      while (j < static_cast<int>(arc.size()) - 1 && arc[j + 1] < s_des) ++j;
      int ii = std::min(idx + j, static_cast<int>(path.size()) - 1);
      if (ii < static_cast<int>(path.size()) - 1 && j < static_cast<int>(arc.size()) - 1) {
        double seg_len = arc[j + 1] - arc[j];
        if (seg_len > 1e-6) {
          double t = std::clamp((s_des - arc[j]) / seg_len, 0.0, 1.0);
          ref(0, k) = path[ii][0] + t * (path[ii + 1][0] - path[ii][0]);
          ref(1, k) = path[ii][1] + t * (path[ii + 1][1] - path[ii][1]);
          double dpsi = normalize_angle(path[ii + 1][2] - path[ii][2]);
          ref(2, k) = normalize_angle(path[ii][2] + t * dpsi);
        } else {
          ref(0, k) = path[ii][0];
          ref(1, k) = path[ii][1];
          ref(2, k) = path[ii][2];
        }
      } else {
        ref(0, k) = path[ii][0];
        ref(1, k) = path[ii][1];
        ref(2, k) = path[ii][2];
      }
      // ★ 不填 ref(3..5) (B 填 ref(3,k)=cruise_speed 等)
    }
  }
  return ref;
}

void MpcControllerNode::safe_shutdown() {
  publish_zero_velocity_();
  publish_standby_status_("node_shutdown");
  RCLCPP_INFO(this->get_logger(), "MPC 节点退出: 已发送安全停车指令");
}

}  // namespace usv_mpc
