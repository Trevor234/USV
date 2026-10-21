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

#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <cstring>
#include <utility>
#include <nlohmann/json.hpp>

namespace usv_mpc
{

namespace
{
double steady_now()
{
  auto now = std::chrono::steady_clock::now();
  return std::chrono::duration<double>(now.time_since_epoch()).count();
}
}  // namespace

MpcControllerNode::MpcControllerNode()
: Node("mpc_controller_node")
{
  declare_parameters_();
  load_config_();
  init_mpc_solver_();
  init_state_();
  init_pubsub_();

  RCLCPP_INFO(this->get_logger(),
              "运动学 MPC 控制器已启动 | 模式=kinematic | dt=%.1fs | N=%d | 方案=A | backend=%s",
              mpc_dt_, horizon_, mpc_ ? mpc_->backend() : "none");

  timer_ = this->create_wall_timer(
      std::chrono::duration<double>(mpc_dt_),
      std::bind(&MpcControllerNode::control_loop_, this),
      control_cb_group_);
}

// Tests inject a solver without exposing fault-injection ROS parameters.
MpcControllerNode::MpcControllerNode(std::unique_ptr<KinematicMpc> solver)
: Node("mpc_controller_node"), mpc_(std::move(solver))
{
  declare_parameters_();
  load_config_();
  init_state_();
  init_pubsub_();
  // 测试不跑控制循环, 但 timer_ 需真实存在 (取消而非缺省), 与 B 一致。
  timer_ = this->create_wall_timer(
      std::chrono::duration<double>(mpc_dt_),
      std::bind(&MpcControllerNode::control_loop_, this),
      control_cb_group_);
  timer_->cancel();
}

MpcControllerNode::~MpcControllerNode()
{
  // safe_shutdown 由 main 在 rclcpp::shutdown 前显式调用
}

// ── 参数声明 (默认值与 mpc_params.yaml 对齐; kinematic.* 命名空间) ──
void MpcControllerNode::declare_parameters_()
{
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
  this->declare_parameter("kinematic.tau_u", 0.8);
  this->declare_parameter("kinematic.tau_r", 1.78);
  // IPOPT 早停策略: 早停迭代点通过完整约束门禁后才允许降级执行。
  this->declare_parameter("kinematic.ipopt_max_iter", 50);
  this->declare_parameter("kinematic.ipopt_max_cpu_time_ms", 120.0);
  this->declare_parameter("kinematic.solution_constraint_tol", 5e-3);
  // backend 参数 (C++ 只实现 casadi; 保留参数对齐 Python, 非 ipopt 时 WARN)
  this->declare_parameter("kinematic.backend", std::string("ipopt"));
}

void MpcControllerNode::load_config_()
{
  // 此工作目录仅方案 A; scheme 强制 A, control_mode 仅 kinematic/idle
  scheme_ = "A";
  std::string mode_str = this->get_parameter("control_mode").as_string();
  if (mode_str != "kinematic" && mode_str != "idle") {
    // 非法值降级到 idle: 不解算、只发零速度。这是安全侧的选择,
    // 与日志声明一致 (原实现只打日志却继续正常控制)。
    RCLCPP_ERROR(this->get_logger(),
                 "control_mode='%s' 不支持 (仅 kinematic/idle), 已降级为 IDLE",
                 mode_str.c_str());
    mode_str = "idle";
  }
  control_mode_ = mode_str;
  if (control_mode_ == "idle") {
    RCLCPP_WARN(this->get_logger(),
                "control_mode=idle: 将持续发布零速度, 不进行 MPC 解算");
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

void MpcControllerNode::init_mpc_solver_()
{
  KinematicMpcParams p;
  p.dt = this->get_parameter("kinematic.dt").as_double();
  double prediction_time = static_cast<double>(horizon_) * mpc_dt_;
  p.N = std::max(1, static_cast<int>(std::round(prediction_time / p.dt)));
  kin_dt_ = p.dt;
  kin_N_ = p.N;
  kin_prediction_time_ = prediction_time;

  auto Qv = this->get_parameter("kinematic.Q").as_double_array();  // 3 维
  auto Rv = this->get_parameter("kinematic.R").as_double_array();  // 2 维
  // 长度校验: 短数组会让 operator[] 越界 (UB), 启动即失败优于运行段错误
  if (Qv.size() < 3 || Rv.size() < 2) {
    throw std::runtime_error(
        "kinematic.Q/R 数组长度不足 (需要 >=3/>=2, 实际 " +
        std::to_string(Qv.size()) + "/" + std::to_string(Rv.size()) +
        "), 请检查 mpc_params yaml");
  }
  for (int i = 0; i < 3; ++i) {
    p.Q_diag(i) = Qv[i];
  }
  p.R_diag << Rv[0], Rv[1];
  p.Qf_scale = this->get_parameter("kinematic.Qf_scale").as_double();
  p.u_max = this->get_parameter("kinematic.u_max").as_double();
  p.u_min = this->get_parameter("kinematic.u_min").as_double();
  p.r_max = this->get_parameter("kinematic.r_max").as_double();
  p.du_max = this->get_parameter("kinematic.du_max").as_double();
  p.dr_max = this->get_parameter("kinematic.dr_max").as_double();
  p.tau_u = this->get_parameter("kinematic.tau_u").as_double();
  p.tau_r = this->get_parameter("kinematic.tau_r").as_double();
  p.ipopt_max_iter = static_cast<int>(this->get_parameter("kinematic.ipopt_max_iter").as_int());
  p.ipopt_max_cpu_time_s =
    this->get_parameter("kinematic.ipopt_max_cpu_time_ms").as_double() / 1000.0;
  p.solution_constraint_tol =
    this->get_parameter("kinematic.solution_constraint_tol").as_double();
  // ★ 无 HydroParams 加载
  // ★ 无 acados cache_dir
  mpc_ = make_kinematic_mpc(p);  // 直接 CasadiKinematicBackend
}

void MpcControllerNode::init_state_()
{
  x_ = y_ = psi_ = u_ = v_ = r_ = 0.0;
  odom_received_ = imu_received_ = path_received_ = false;
  armed_ = false;
  mode_ = "MANUAL";
  solver_fail_count_ = 0;
  control_count_ = 0;
  last_state_time_ = 0.0;
  last_odom_time_ = 0.0;
}

void MpcControllerNode::init_pubsub_()
{
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
void MpcControllerNode::odom_callback_(const nav_msgs::msg::Odometry::SharedPtr msg)
{
  const auto & p = msg->pose.pose.position;
  const auto & q = msg->pose.pose.orientation;
  const auto & t = msg->twist.twist;
  // NaN/Inf 门禁: 一个污染样本 (GPS 重定位/EKF 发散) 若进入状态,求解器可能
  // 仍返回"成功"解并把 NaN 速度指令发给 GUIDED。直接丢弃。
  if (!std::isfinite(p.x) || !std::isfinite(p.y) ||
    !std::isfinite(q.x) || !std::isfinite(q.y) ||
    !std::isfinite(q.z) || !std::isfinite(q.w) ||
    !std::isfinite(t.linear.x) || !std::isfinite(t.linear.y) ||
    !std::isfinite(t.angular.z))
  {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "odom 含 NaN/Inf, 丢弃该样本");
    return;
  }
  double psi = quaternion_to_yaw(q.x, q.y, q.z, q.w);
  // 四元数范数门禁 (对齐 B 的 admit_odom): 全零四元数的 yaw 是有限值 0,
  // isfinite 拦不住; 未归一化四元数也会扭曲 yaw 公式 (1-2(y²+z²) 仅对
  // 单位范数成立)。范数非有限或接近零即丢弃。
  const double qnorm2 = q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w;
  if (!std::isfinite(psi) || !std::isfinite(qnorm2) || qnorm2 < 1e-12) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "odom 四元数退化 (|q|²=%.3e), 丢弃该样本", qnorm2);
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

void MpcControllerNode::imu_callback_(const sensor_msgs::msg::Imu::SharedPtr msg)
{
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

void MpcControllerNode::path_callback_(const nav_msgs::msg::Path::SharedPtr msg)
{
  std::lock_guard<std::mutex> lk(state_lock_);
  reference_path_.clear();
  for (const auto & pose : msg->poses) {
    auto & q = pose.pose.orientation;
    reference_path_.push_back({pose.pose.position.x, pose.pose.position.y,
        quaternion_to_yaw(q.x, q.y, q.z, q.w)});
  }
  reference_path_stamp_ = {static_cast<int>(msg->header.stamp.sec),
    static_cast<int>(msg->header.stamp.nanosec)};
  path_received_ = !reference_path_.empty();
}

void MpcControllerNode::profile_callback_(const std_msgs::msg::Float64MultiArray::SharedPtr msg)
{
  std::lock_guard<std::mutex> lk(state_lock_);
  // 从 layout.dim 提取标签, 解析 stamp (utils 保持纯逻辑, 不依赖 ROS 消息)
  std::vector<std::string> labels;
  labels.reserve(msg->layout.dim.size());
  for (const auto & d : msg->layout.dim) {
    labels.push_back(d.label);
  }
  bool ok = false;
  ref_profile_stamp_ = parse_profile_stamp(labels, ok);
  if (!ok) {ref_profile_stamp_ = {-1, -1};}

  const auto & data = msg->data;
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

void MpcControllerNode::state_callback_(const mavros_msgs::msg::State::SharedPtr msg)
{
  std::lock_guard<std::mutex> lk(state_lock_);
  armed_ = msg->armed;
  mode_ = msg->mode;
  last_state_time_ = steady_now();
}

// ── 控制循环 (与 B 逐行相同, 状态机逻辑方案无关) ──────────
std::pair<bool, std::string> MpcControllerNode::can_solve_() const
{
  double now = steady_now();
  if (!odom_received_) {return {false, "no_odom"};}
  if (odom_timeout_s_ > 0.0 && (now - last_odom_time_) > odom_timeout_s_) {
    return {false, "odom_timeout"};
  }
  if (!path_received_ || reference_path_.size() < 2) {return {false, "no_path"};}
  if (require_fcu_state_) {
    if (last_state_time_ == 0.0) {return {false, "no_state"};}
    if (state_timeout_s_ > 0.0 && (now - last_state_time_) > state_timeout_s_) {
      return {false, "state_timeout"};
    }
    if (!armed_) {return {false, "disarmed"};}
    if (!allowed_fcu_modes_.empty()) {
      bool allowed = false;
      for (const auto & m : allowed_fcu_modes_) {
        if (m == mode_) {
          allowed = true; break;
        }
      }
      if (!allowed) {return {false, "wrong_mode(" + mode_ + ")"};}
    }
  }
  return {true, ""};
}

void MpcControllerNode::enter_standby_(const std::string & reason)
{
  std::lock_guard<std::mutex> output_lock(control_output_mutex_);
  if (shutting_down_.load()) {return;}
  bool transition = (prev_state_ != "STANDBY");
  if (transition) {
    solver_fail_count_ = 0;
    if (mpc_) {mpc_->reset_warmstart();}
    RCLCPP_INFO(this->get_logger(), "MPC → STANDBY: %s", reason.c_str());
  }
  publish_zero_velocity_();  // ★ 零速度 (B 是 release_rc_override_)
  prev_state_ = "STANDBY";
  publish_standby_status_(reason);
  RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                       "MPC 等待飞控就绪: %s", reason.c_str());
}

void MpcControllerNode::control_loop_()
{
  // idle 模式: 不解算, 持续发布零速度。用于码头/台架调试,
  // 保证"停住控制输出"这个开关真实有效。
  if (control_mode_ == "idle") {
    enter_standby_("control_mode=idle");
    return;
  }

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
    // STANDBY→ACTIVE: 速率约束锚点对齐船当前实测速度。reset_warmstart 已把
    // 锚点归零, 若船仍在动, 首步 du/dr 约束会强制指令从 0 出发 (首拍突变);
    // 以测量值重锚后, 首拍指令可在测量值 ±du_step 内平滑衔接。
    Eigen::Vector2d measured;
    {
      std::lock_guard<std::mutex> lk(state_lock_);
      measured << u_, r_;
    }
    mpc_->set_applied_command(measured);
  }
  prev_state_ = "ACTIVE";
  run_kinematic_mpc_();
}

bool MpcControllerNode::enforce_solve_deadline_(
  SolveInfo & info, double solve_wall_time_ms)
{
  // 墙钟与后端计时双检 (对齐 B): Pi 调度抢占下 wall 可远超 IPOPT 内部
  // CPU 时间, 只查后端时间会发布基于旧状态的过期解。
  if (!std::isfinite(solve_wall_time_ms) || solve_wall_time_ms < 0.0 ||
    !std::isfinite(info.solve_time_ms) || info.solve_time_ms < 0.0 ||
    !std::isfinite(max_solve_time_ms_))
  {
    info.success = false;
    snprintf(info.error, sizeof(info.error),
             "solve_timing_invalid: wall=%.1fms backend=%.1fms limit=%.1fms",
             solve_wall_time_ms, info.solve_time_ms, max_solve_time_ms_);
    return true;
  }
  const bool deadline_miss = max_solve_time_ms_ > 0.0 &&
    (solve_wall_time_ms > max_solve_time_ms_ || info.solve_time_ms > max_solve_time_ms_);
  if (deadline_miss) {
    info.success = false;
    snprintf(info.error, sizeof(info.error),
             "solve_timeout: wall=%.1fms backend=%.1fms limit=%.1fms",
             solve_wall_time_ms, info.solve_time_ms, max_solve_time_ms_);
  }
  return deadline_miss;
}

void MpcControllerNode::run_kinematic_mpc_()
{
  if (shutting_down_.load()) {return;}
  Eigen::Matrix<double, 5, 1> current_state_5d;
  Eigen::Vector3d current_pose;
  Eigen::MatrixXd reference;
  {
    // C1 修复 (对齐 B): can_solve_ 在锁释放后可能被 path_callback_ 抢先清空
    // 路径, 不重查会让 build_reference_ 返回全零参考 → 船被命令驶向地图原点。
    // 该窗口在每次任务结束 (规划器发空路径) 时都会打开。
    std::unique_lock<std::mutex> lk(state_lock_);
    const auto rechecked = can_solve_();
    if (!rechecked.first) {
      // standby 会先取 output 锁再取 state 锁 (见 enter_standby_), 先释放本锁防死锁。
      lk.unlock();
      enter_standby_(rechecked.second);
      return;
    }
    current_pose << x_, y_, normalize_angle(psi_);
    current_state_5d << x_, y_, normalize_angle(psi_), u_, r_;
    reference = build_reference_(current_pose);
  }

  const auto solve_start = std::chrono::steady_clock::now();
  auto [u_opt, info] = mpc_->solve(current_state_5d, reference);
  const double solve_wall_time_ms = std::chrono::duration<double, std::milli>(
    std::chrono::steady_clock::now() - solve_start).count();

  std::lock_guard<std::mutex> output_lock(control_output_mutex_);
  if (shutting_down_.load()) {return;}
  const bool time_rejected = enforce_solve_deadline_(info, solve_wall_time_ms);
  Eigen::Vector2d selected_command = u_opt;
  if (time_rejected) {
    // solve() 可能已把迟到候选移入热启动, 连同状态一起拒绝 (对齐 B)。
    mpc_->reset_warmstart();
    selected_command = has_last_command_ ?
      last_commanded_velocity_ : Eigen::Vector2d::Zero();
  }

  bool in_hold = false;
  if (info.success) {
    solver_fail_count_ = 0;
    if (info.error[0] != '\0') {
      // 早停回收解已通过后端完整约束门禁，但尚未达到正常收敛条件。
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "IPOPT 早停回收 (%s), 已发布当前迭代点", info.error);
    }
    publish_velocity_cmd_(selected_command);
    if (control_count_ % 5 == 0) {publish_predicted_trajectory_(info.X_pred);}
  } else {
    solver_fail_count_++;
    if (solver_fail_count_ <= 3) {
      RCLCPP_WARN(this->get_logger(), "MPC 求解失败: %s  失败计数=%d",
                  info.error, solver_fail_count_);
    }
    if (solver_fail_count_ >= solver_hold_threshold_) {
      in_hold = true;
      selected_command.setZero();
      publish_velocity_cmd_(selected_command);
      if (!time_rejected) {mpc_->reset_warmstart();}
      if (solver_fail_count_ == solver_hold_threshold_) {
        RCLCPP_ERROR(this->get_logger(),
                     "MPC HOLD 挂起：连续失败 %d 次，正在发布零速度并重置热启动",
                     solver_fail_count_);
      }
    } else {
      publish_velocity_cmd_(selected_command);
    }
  }

  last_commanded_velocity_ = selected_command;
  has_last_command_ = true;

  // 暴露 u_opt / 航向参考给 status (对齐 Python A 的 status 字段)
  publish_status_(info, in_hold, selected_command, current_pose, reference);

  control_count_++;
  if (control_count_ % 25 == 0) {  // 约每 5 秒 (对齐 Python A)
    RCLCPP_INFO(this->get_logger(),
                "t=%.1fs  位置=(%.1f,%.1f)  航向=%.0f°  指令=(u=%.2f, r=%.1f°/s)  求解时间=%.0fms",
                control_count_ * mpc_dt_, current_pose(0), current_pose(1),
                current_pose(2) * 180.0 / M_PI,
                selected_command(0), selected_command(1) * 180.0 / M_PI,
                info.solve_time_ms);
  }
}

// ── 输出: TwistStamped (★ 与 B 的 thrust→RC PWM 完全不同, 无映射) ──
// 发布后把实际下发值写回求解器作为速率约束锚点, 使锚点与真实执行一致
// (覆盖成功/失败重放/deadline 置零/HOLD 置零全部分支, 不会与发布逻辑漂移)。
void MpcControllerNode::publish_velocity_cmd_(const Eigen::Vector2d & u_opt)
{
  geometry_msgs::msg::TwistStamped msg;
  msg.header.stamp = this->get_clock()->now();
  msg.header.frame_id = body_frame_;
  msg.twist.linear.x = u_opt(0);   // u_surge
  msg.twist.linear.y = 0.0;
  msg.twist.angular.z = u_opt(1);  // r_yaw
  vel_pub_->publish(msg);
  if (mpc_) {mpc_->set_applied_command(u_opt);}
}

void MpcControllerNode::publish_zero_velocity_()
{
  publish_velocity_cmd_(Eigen::Vector2d::Zero());
}

void MpcControllerNode::publish_status_(
  const SolveInfo & info, bool in_hold,
  const Eigen::Vector2d & u_opt,
  const Eigen::Vector3d & current_state,
  const Eigen::MatrixXd & reference)
{
  nlohmann::json j;
  j["state"] = in_hold ? "HOLD" : "ACTIVE";
  j["success"] = info.success;
  j["fail_count"] = solver_fail_count_;
  j["solve_time_ms"] = info.solve_time_ms;
  j["max_solve_time_ms"] = max_solve_time_ms_;
  j["deadline_miss"] = (std::strncmp(info.error, "solve_timeout", 13) == 0);
  j["hold"] = in_hold;
  j["scheme"] = scheme_;
  j["control_mode"] = control_mode_;
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
  j["initial_state_residual"] = info.initial_state_residual;
  j["max_dynamics_residual"] = info.max_dynamics_residual;
  j["max_control_bound_violation"] = info.max_control_bound_violation;
  j["max_control_rate_violation"] = info.max_control_rate_violation;
  j["u_cmd"] = u_opt(0);
  j["r_cmd"] = u_opt(1);
  if (reference.cols() > 0) {
    j["psi_ref"] = reference(2, 0);
    j["e_psi"] = normalize_angle(current_state(2) - reference(2, 0));
  }
  if (!info.success) {j["error"] = info.error;}

  std_msgs::msg::String msg;
  msg.data = j.dump();
  status_pub_->publish(msg);
}

void MpcControllerNode::publish_standby_status_(const std::string & reason)
{
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

void MpcControllerNode::publish_predicted_trajectory_(const Eigen::MatrixXd & X_pred)
{
  if (!publish_predicted_ || X_pred.size() == 0) {return;}
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
Eigen::MatrixXd MpcControllerNode::build_reference_(const Eigen::Vector3d & current_state)
{
  const int N = mpc_->N();
  double dt = mpc_->dt();
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(3, N + 1);  // ★ 3 维 (B 是 6)
  const auto & path = reference_path_;
  if (path.empty()) {return ref;}

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
  const std::pair<int, int> * p_stamp =
    (ref_profile_stamp_.first >= 0) ? &ref_profile_stamp_ : nullptr;
  const std::pair<int, int> * path_stamp =
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
      while (j < static_cast<int>(arc.size()) - 1 && arc[j + 1] < s_des) {++j;}
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

void MpcControllerNode::safe_shutdown()
{
  // 对齐 B: 先置关机标志, 让在途的控制循环在输出锁上让行; shutdown 可能
  // 在信号线程执行, 此处不再触碰求解器 (避免与在途 solve() 竞争 CasADi 后端)。
  shutting_down_.store(true);
  std::lock_guard<std::mutex> output_lock(control_output_mutex_);
  publish_zero_velocity_();
  publish_standby_status_("node_shutdown");
  RCLCPP_INFO(this->get_logger(), "MPC 节点退出: 已发送安全停车指令");
}

}  // namespace usv_mpc
