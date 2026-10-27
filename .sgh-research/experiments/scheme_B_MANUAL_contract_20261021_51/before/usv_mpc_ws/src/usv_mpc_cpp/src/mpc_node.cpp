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
#include <cstring>
#include <nlohmann/json.hpp>

#include "usv_mpc_cpp/p1_input_core.hpp"

using namespace std::chrono_literals;  // 引用所有字面量“10s”“10ms”等

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
: MpcControllerNode(nullptr)
{
}

MpcControllerNode::MpcControllerNode(std::unique_ptr<DynamicMpc> solver)
: Node("mpc_controller_node"), mpc_(std::move(solver))
{
  declare_parameters_();
  load_config_();
  init_mpc_solver_();
  init_state_();
  init_pubsub_();

  RCLCPP_INFO(this->get_logger(),
              "MPC 控制器已启动 | 模式=dynamic | dt=%.1fs | N=%d | "
              "类型=NMPC (动力学) | backend=%s | output=%s",
              mpc_dt_, horizon_, mpc_ ? mpc_->backend() : "none",
              output_mode_.c_str());

  timer_ = this->create_wall_timer(
      std::chrono::duration<double>(mpc_dt_),
      std::bind(&MpcControllerNode::control_loop_, this),
      control_cb_group_);
}

MpcControllerNode::~MpcControllerNode()
{
  if (research_) {research_->stop(false);}
}

void MpcControllerNode::research_clock_(const rosgraph_msgs::msg::Clock::SharedPtr msg)
{
  const int64_t value = int64_t(msg->clock.sec) * 1000000000LL + msg->clock.nanosec;
  std::lock_guard<std::mutex> lock(research_clock_mutex_);
  observed_clock_status_ = "observed";
  if (observed_clock_receive_ns_ != 0) {
    if (value < observed_sim_ns_) {
      ++observed_epoch_; observed_clock_status_ = "reset";
    } else if (value - observed_sim_ns_ > 5000000000LL) {
      ++observed_epoch_; observed_clock_status_ = "jump";
    } else if (value == observed_sim_ns_) {observed_clock_status_ = "paused";}
  }
  observed_sim_ns_ = value;
  observed_clock_receive_ns_ = research_steady_ns();
}

void MpcControllerNode::research_state_(
  const nav_msgs::msg::Odometry & msg,
  uint64_t received, int64_t receive_ns, double yaw)
{
  if (!research_->armed()) {return;}
  ResearchState s;
  s.received_odom_sequence = received;
  s.odom_stamp_ns = int64_t(msg.header.stamp.sec) * 1000000000LL + msg.header.stamp.nanosec;
  s.receive_steady_ns = receive_ns;
  s.freeze_steady_ns = research_steady_ns();
  s.frame_id = msg.header.frame_id; s.child_frame_id = msg.child_frame_id;
  s.source_topic = this->get_parameter("odom_topic").as_string();
  s.state_6 = {msg.pose.pose.position.x, msg.pose.pose.position.y, yaw,
    msg.twist.twist.linear.x, msg.twist.twist.linear.y, msg.twist.twist.angular.z};
  s.valid = true;
  for (double value : s.state_6) {
    if (!std::isfinite(value)) {
      s.valid = false;
    }
  }
  const auto & q = msg.pose.pose.orientation;
  const double norm2 = q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w;
  if (!std::isfinite(norm2) || norm2 < 1e-12) {s.valid = false;}
  s.quality_reason = s.valid ? "valid_numeric" : "invalid_numeric_or_quaternion";
  // Invalid raw values remain in original odom; flagged snapshots use finite
  // placeholders so they cannot silently become training observations.
  for (double & value : s.state_6) {
    if (!std::isfinite(value)) {
      value = 0.0;
    }
  }
  if (!this->get_parameter("research_frame_contract_verified").as_bool() ||
    s.frame_id != this->get_parameter("research_expected_pose_frame").as_string() ||
    s.child_frame_id != this->get_parameter("research_expected_child_frame").as_string())
  {
    s.valid = false; s.quality_reason += ":frame_unverified_or_mismatch";
  }
  research_time_(s);
  if (s.clock_status == "not_received") {s.valid = false; s.quality_reason += ":clock_missing";}
  research_->enqueue(s, "state");
}

Eigen::Vector2d MpcControllerNode::research_publish_(
  const Eigen::Vector2d & requested,
  const std_msgs::msg::Float64 & left, const std_msgs::msg::Float64 & right)
{
  ResearchApplied event;
  research_time_(event);
  event.event_semantics = "publisher_command";
  event.cycle_sequence = active_research_cycle_;
  event.control_source = research_control_source_;
  event.requested_known = true;
  event.requested_n = {requested(0), requested(1)};
  event.final_n = {left.data, right.data};
  event.map_scale = vrx_thrust_scale_;
  event.lower_n = std::max(dyn_T_min_, -vrx_thrust_cmd_max_);
  event.upper_n = std::min(dyn_T_max_, vrx_thrust_cmd_max_);
  event.previous_anchor_known = observed_previous_known_;
  event.previous_final_n = observed_previous_final_;
  event.left_publish_start_steady_ns = research_steady_ns();
  ResearchApplied clock_at_left; research_time_(clock_at_left);
  event.left_sim_time_ns = clock_at_left.sim_time_ns;
  event.left_clock_epoch = clock_at_left.clock_epoch;
  event.left_clock_age_ns = clock_at_left.clock_age_ns;
  try {
    vrx_left_pub_->publish(left);
    event.left_publish_success = true;
    event.left_publish_end_steady_ns = research_steady_ns();
    event.right_publish_start_steady_ns = research_steady_ns();
    ResearchApplied clock_at_right; research_time_(clock_at_right);
    event.right_sim_time_ns = clock_at_right.sim_time_ns;
    event.right_clock_epoch = clock_at_right.clock_epoch;
    event.right_clock_age_ns = clock_at_right.clock_age_ns;
    vrx_right_pub_->publish(right);
    event.right_publish_success = true;
    event.right_publish_end_steady_ns = research_steady_ns();
  } catch (const std::exception & error) {
    if (!event.left_publish_success) {
      event.left_publish_end_steady_ns = research_steady_ns();
    } else {
      event.right_publish_end_steady_ns = research_steady_ns();
    }
    event.publish_error = error.what();
    observed_previous_known_ = false;
    latest_applied_sequence_ = research_->enqueue(event, "applied");
    throw;
  }
  observed_previous_known_ = true;
  observed_previous_final_ = event.final_n;
  latest_applied_sequence_ = research_->enqueue(event, "applied");
  return Eigen::Vector2d(left.data, right.data);
}

// ── 参数声明 (默认值与清理后的 mpc_params.yaml/usv_params.yaml 对齐) ──
void MpcControllerNode::declare_parameters_()
{
  // P0_REFERENCE_PREDICTION_V1
  this->declare_parameter("enable_reference_prediction_logging", false);
  this->declare_parameter("research_nominal_config_hash", std::string(""));
  this->declare_parameter("enable_research_logging", false);
  this->declare_parameter("research_logging_armed", false);
  this->declare_parameter("research_run_id", std::string(""));
  this->declare_parameter("research_baseline_id", std::string(""));
  this->declare_parameter("research_output_dir", std::string(""));
  this->declare_parameter("research_config_hash", std::string(""));
  this->declare_parameter("research_expected_pose_frame", std::string(""));
  this->declare_parameter("research_expected_child_frame", std::string(""));
  this->declare_parameter("research_frame_contract_verified", false);
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

void MpcControllerNode::load_config_()
{
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
    for (const auto & m : allowed_fcu_modes_) {
      if (m == "GUIDED") {has_guided = true; break;}
    }
    if (!has_guided) {
      std::string modes;
      for (const auto & m : allowed_fcu_modes_) {
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

  const std::size_t rc_channel_count =
    mavros_msgs::msg::OverrideRCIn().channels.size();
  if (rc_steering_channel_ < 0 || rc_throttle_channel_ < 0 ||
    static_cast<std::size_t>(rc_steering_channel_) >= rc_channel_count ||
    static_cast<std::size_t>(rc_throttle_channel_) >= rc_channel_count ||
    rc_steering_channel_ == rc_throttle_channel_ ||
    rc_pwm_min_ >= rc_pwm_center_ || rc_pwm_center_ >= rc_pwm_max_ ||
    !std::isfinite(steering_sign_) || !std::isfinite(throttle_sign_) ||
    !std::isfinite(steering_gain_) || !std::isfinite(throttle_gain_) ||
    std::abs(std::abs(steering_sign_) - 1.0) > 1e-9 ||
    std::abs(std::abs(throttle_sign_) - 1.0) > 1e-9 ||
    steering_gain_ < 0.0 || throttle_gain_ < 0.0)
  {
    throw std::runtime_error(
        "RC 映射参数非法: 通道须有效且不同，并满足 pwm_min < pwm_center < "
        "pwm_max、sign=+-1、gain>=0");
  }
  if (!std::isfinite(vrx_thrust_scale_) || vrx_thrust_scale_ <= 0.0 ||
    !std::isfinite(vrx_thrust_cmd_max_) || vrx_thrust_cmd_max_ <= 0.0)
  {
    throw std::runtime_error("VRX 推力映射参数必须为有限正数");
  }
}

void MpcControllerNode::init_mpc_solver_()
{
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
  for (int i = 0; i < 6; ++i) {
    p.Q_diag(i) = Qv[i];
  }
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

  if (!mpc_) {mpc_ = make_dynamic_mpc(p);}
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
  last_commanded_thrust_.setZero();
  last_applied_thrust_.setZero();
  has_last_command_ = false;
}

void MpcControllerNode::init_pubsub_()
{
  io_cb_group_ = this->create_callback_group(
      rclcpp::CallbackGroupType::Reentrant);  // 传感器订阅
  control_cb_group_ = this->create_callback_group(
      rclcpp::CallbackGroupType::MutuallyExclusive);  // 控制定时器

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
  reference_logging_enabled_ = this->get_parameter("enable_reference_prediction_logging").as_bool();
  research_nominal_config_hash_ = this->get_parameter("research_nominal_config_hash").as_string();
  if (reference_logging_enabled_ && !this->get_parameter("enable_research_logging").as_bool()) {
    throw std::runtime_error("reference telemetry requires enable_research_logging");
  }
  if (this->get_parameter("enable_research_logging").as_bool()) {
    if (output_mode_ != "vrx_thrust") {
      throw std::runtime_error("P0 research observations require vrx_thrust mode");
    }
    research_ = std::make_unique<ResearchLogger>(*this,
      this->get_parameter("research_output_dir").as_string(),
      this->get_parameter("research_run_id").as_string(),
      this->get_parameter("research_baseline_id").as_string(),
      this->get_parameter("research_config_hash").as_string(),
      reference_logging_enabled_, research_nominal_config_hash_);
    research_clock_group_ =
      this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
    auto clock_options = opts; clock_options.callback_group = research_clock_group_;
    research_clock_sub_ = this->create_subscription<rosgraph_msgs::msg::Clock>(
      "/clock", rclcpp::ClockQoS(),
      std::bind(&MpcControllerNode::research_clock_, this, std::placeholders::_1), clock_options);
  }
}

// ── 回调 ─────────────────────────────────────────────────
void MpcControllerNode::odom_callback_(const nav_msgs::msg::Odometry::SharedPtr msg)
{
  const int64_t receive_ns = research_ ? research_steady_ns() : 0;
  uint64_t received = 0;
  if (research_) {
    std::lock_guard<std::mutex> lk(state_lock_); received = ++received_odom_count_;
  }
  const auto & p = msg->pose.pose.position;
  const auto & q = msg->pose.pose.orientation;
  const auto & t = msg->twist.twist;
  if (research_) {
    research_state_(*msg, received, receive_ns, quaternion_to_yaw(q.x, q.y, q.z, q.w));
  }
  // NaN/Inf 门禁: 一个污染样本 (GPS 重定位/EKF 发散) 若进入状态,求解器可能
  // 仍返回 status=0 的"成功"解,经 clamp/cast 变成任意 PWM 下发。直接丢弃。
  // P1_SHARED_ODOM_ADMISSION_V1: the common gate owns acceptance.
  if (!admit_odom({p.x, p.y, t.linear.x, t.linear.y, t.angular.z},
    {q.x, q.y, q.z, q.w}))
  {
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
    // Keep raw research records above, but never admit degenerate orientations.
    const double quaternion_norm2 = q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w;
    if (!std::isfinite(quaternion_norm2) || quaternion_norm2 < 1e-12) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                          "odom quaternion norm is invalid; dropping sample");
      return;
    }
    double psi = quaternion_to_yaw(q.x, q.y, q.z, q.w);
    if (!std::isfinite(psi)) {  // Final guard for the yaw calculation
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "odom 四元数退化, 丢弃该样本");
      return;
    }
    return;
  }
  std::lock_guard<std::mutex> lk(state_lock_);
  const auto composed = compose_odom({p.x, p.y, t.linear.x, t.linear.y, t.angular.z},
      {q.x, q.y, q.z, q.w});
  x_ = composed[0];y_ = composed[1];psi_ = composed[2];u_ = composed[3];v_ = composed[4];
  r_ = composed[5];
  odom_received_ = true;
  last_odom_time_ = steady_now();
  if (research_) {
    accepted_odom_sequence_ = received;
    accepted_odom_stamp_ns_ = int64_t(msg->header.stamp.sec) * 1000000000LL +
      msg->header.stamp.nanosec;
    r_from_imu_ = false;
  }
}

void MpcControllerNode::imu_callback_(const sensor_msgs::msg::Imu::SharedPtr msg)
{
  uint64_t received = 0;
  if (research_) {
    std::lock_guard<std::mutex> lk(state_lock_); received = ++received_imu_count_;
  }
  double r = msg->angular_velocity.z;  // 直接陀螺仪角速度, 更灵敏
  if (!admit_imu(r)) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "IMU 角速度含 NaN/Inf, 丢弃该样本");
    return;
  }
  std::lock_guard<std::mutex> lk(state_lock_);
  r_ = r;
  imu_received_ = true;
  if (research_) {
    accepted_imu_sequence_ = received;
    accepted_imu_stamp_ns_ = int64_t(msg->header.stamp.sec) * 1000000000LL +
      msg->header.stamp.nanosec;
    r_from_imu_ = true;
  }
}

void MpcControllerNode::path_callback_(const nav_msgs::msg::Path::SharedPtr msg)
{
  std::lock_guard<std::mutex> lk(state_lock_);
  if (reference_logging_enabled_) {++path_received_sequence_;}
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
  if (reference_logging_enabled_) {++profile_received_sequence_;}
  // 从 layout.dim 提取标签,解析 stamp (utils 保持纯逻辑,不依赖 ROS 消息)
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

// ── 控制循环 ─────────────────────────────────────────────
std::pair<bool, std::string> MpcControllerNode::can_solve_() const
{
  InputEligibility c;
  c.odom_received = odom_received_;c.path_received = path_received_;
  c.path_size = reference_path_.size();
  c.now_s = steady_now();c.last_odom_s = last_odom_time_;c.odom_timeout_s = odom_timeout_s_;
  c.require_fcu = require_fcu_state_;c.armed = armed_;c.last_state_s = last_state_time_;
  c.state_timeout_s = state_timeout_s_;c.mode = mode_;c.allowed_modes = allowed_fcu_modes_;
  return input_eligibility(c);
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
  research_control_source_ = "standby_release";
  publish_zero_dynamic_output_();
  prev_state_ = "STANDBY";
  publish_standby_status_(reason);
  RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                       "MPC 等待飞控就绪: %s", reason.c_str());
}

void MpcControllerNode::control_loop_()
{
  if (research_ && this->get_parameter("research_logging_armed").as_bool()) {research_->arm();}
  const bool observing = research_ && research_->armed();
  if (observing) {
    research_cycle_ = ResearchCycle();
    research_cycle_.timer_entry_steady_ns = research_steady_ns();
    research_cycle_.state_kind = "no_solve";
    active_research_cycle_ = ++research_cycle_sequence_;
    research_->cycle_started();
    research_time_(research_cycle_);
  }
  std::pair<bool, std::string> cs;
  bool armed; std::string mode;
  {
    std::lock_guard<std::mutex> lk(state_lock_);
    cs = can_solve_();
    armed = armed_;
    mode = mode_;
  }
  if (!cs.first) {
    enter_standby_(cs.second);
    if (observing) {
      research_cycle_.rejection_reason = cs.second;
      research_cycle_.publish_end_steady_ns = research_steady_ns();
      research_cycle_.applied_sequence = latest_applied_sequence_;
      research_->enqueue(research_cycle_, "cycle");
    }
    active_research_cycle_ = 0;
    return;
  }

  if (prev_state_ != "ACTIVE") {
    RCLCPP_INFO(this->get_logger(), "MPC → ACTIVE: armed=%d, mode=%s", armed, mode.c_str());
    solver_fail_count_ = 0;
  }
  prev_state_ = "ACTIVE";
  run_dynamic_mpc_();
  if (observing) {
    research_cycle_.publish_end_steady_ns = research_steady_ns();
    research_cycle_.applied_sequence = latest_applied_sequence_;
    research_->enqueue(research_cycle_, "cycle");
  }
  active_research_cycle_ = 0;
}

bool MpcControllerNode::enforce_solve_deadline_(
  SolveInfo & info, double solve_wall_time_ms)
{
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

void MpcControllerNode::run_dynamic_mpc_()
{
  if (shutting_down_.load()) {return;}
  Vector6d current_state;
  Eigen::MatrixXd reference;
  const bool observe_reference = reference_logging_enabled_ && research_ && research_->armed();
  ResearchReference reference_event;
  {
    // P1_ATOMIC_DYNAMIC_FREEZE_V1
    std::unique_lock<std::mutex> lk(state_lock_);
    const auto rechecked = can_solve_();
    if (!rechecked.first) {
      // Standby acquires the output lock and later the state lock; release first.
      lk.unlock();
      enter_standby_(rechecked.second);
      if (research_ && research_->armed()) {
        research_cycle_.rejection_reason = rechecked.second;
      }
      return;
    }
    current_state << x_, y_, normalize_angle(psi_), u_, v_, r_;
    if (research_ && research_->armed()) {
      research_cycle_.state_copy_steady_ns = research_steady_ns();
      std::copy(current_state.data(), current_state.data() + 6,
          research_cycle_.controller_state_6.begin());
      research_cycle_.received_odom_sequence = accepted_odom_sequence_;
      research_cycle_.received_imu_sequence = r_from_imu_ ? accepted_imu_sequence_ : 0;
      research_cycle_.odom_stamp_ns = accepted_odom_stamp_ns_;
      research_cycle_.imu_stamp_ns = r_from_imu_ ? accepted_imu_stamp_ns_ : 0;
      research_cycle_.state_kind = r_from_imu_ ? "controller_mixed" : "odom_atomic";
    }
    reference = build_reference_(current_state, observe_reference ? &reference_event : nullptr);
    if (research_ && research_->armed()) {
      research_cycle_.reference_ready_steady_ns = research_steady_ns();
    }
    // 航向偏差若超过 135 度 (例如遭遇强扰动反向): 重置热启动初值, 破坏倒车局部解记忆
    if (reference.cols() > 0 &&
      std::abs(normalize_angle(current_state(2) - reference(2, 0))) > (M_PI * 0.75))
    {
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
  // reset_warmstart() also clears the backend's previous-input anchor. Restore
  // the published equivalent thrust after any pre-solve reset above.
  {
    std::lock_guard<std::mutex> output_lock(control_output_mutex_);
    if (shutting_down_.load()) {return;}
    if (has_last_command_) {mpc_->set_applied_control(last_applied_thrust_);}
  }
  if (observe_reference) {
    // This is the already-built, local solve input. No second build or getter.
    reference_event.cycle_sequence = active_research_cycle_.load();
    reference_event.clock_epoch = research_cycle_.clock_epoch;
    reference_event.sim_time_ns = research_cycle_.sim_time_ns;
    reference_event.clock_receive_steady_ns = research_cycle_.clock_receive_steady_ns;
    reference_event.clock_age_ns = research_cycle_.clock_age_ns;
    reference_event.clock_status = research_cycle_.clock_status;
    reference_event.state_copy_steady_ns = research_cycle_.state_copy_steady_ns;
    reference_event.reference_ready_steady_ns = research_cycle_.reference_ready_steady_ns;
    reference_event.controller_state_6 = research_cycle_.controller_state_6;
    reference_event.state_kind = research_cycle_.state_kind;
    reference_event.received_odom_sequence = research_cycle_.received_odom_sequence;
    reference_event.received_imu_sequence = research_cycle_.received_imu_sequence;
    reference_event.odom_stamp_ns = research_cycle_.odom_stamp_ns;
    reference_event.imu_stamp_ns = research_cycle_.imu_stamp_ns;
    reference_event.nominal_config_hash = research_nominal_config_hash_;
    reference_event.matrix_layout = "k_major";
    reference_event.reference_rows = static_cast<uint32_t>(reference.rows());
    reference_event.reference_cols = static_cast<uint32_t>(reference.cols());
    reference_event.reference_data.assign(reference.data(), reference.data() + reference.size());
  }
  if (research_ && research_->armed()) {
    research_cycle_.solve_invoked = true;
    research_cycle_.solve_start_steady_ns = research_steady_ns();
  }
  const auto solve_start = std::chrono::steady_clock::now();
  auto [u_opt, info] = mpc_->solve(current_state, reference);
  const double solve_wall_time_ms = std::chrono::duration<double, std::milli>(
    std::chrono::steady_clock::now() - solve_start).count();
  if (research_ && research_->armed()) {research_cycle_.solve_end_steady_ns = research_steady_ns();}
  std::lock_guard<std::mutex> output_lock(control_output_mutex_);
  if (shutting_down_.load()) {return;}
  const bool time_rejected = enforce_solve_deadline_(info, solve_wall_time_ms);
  Eigen::Vector2d selected_command = u_opt;
  const char * control_source = info.success ? "solver" : "backend_fallback";
  if (time_rejected) {
    // solve() may already have shifted the late candidate into its warm start.
    // Reject that state as well as its first command; this is a post-return gate,
    // not a watchdog capable of publishing while synchronous solve() is blocked.
    mpc_->reset_warmstart();
    selected_command = has_last_command_ ?
      last_commanded_thrust_ : Eigen::Vector2d::Zero();
    control_source = has_last_command_ ? "repeat_last_command" : "zero_no_history";
  }

  bool in_hold = false;
  if (info.success) {
    solver_fail_count_ = 0;
    if (control_count_ % 5 == 0) {publish_predicted_trajectory_(info.X_pred);}
  } else {
    solver_fail_count_++;
    if (solver_fail_count_ <= 3) {
      RCLCPP_WARN(this->get_logger(), "NMPC 求解失败: %s  失败计数=%d",
                  info.error, solver_fail_count_);
    }
    if (solver_fail_count_ >= solver_hold_threshold_) {
      in_hold = true;
      selected_command.setZero();
      control_source = "hold_zero";
      if (!time_rejected) {mpc_->reset_warmstart();}
      if (solver_fail_count_ == solver_hold_threshold_) {
        RCLCPP_ERROR(this->get_logger(),
                     "NMPC HOLD 挂起：连续失败 %d 次，正在发布零推力并重置热启动",
                     solver_fail_count_);
      }
    }
  }

  research_control_source_ = control_source;
  if (research_ && research_->armed()) {
    research_cycle_.backend_time_ms = info.solve_time_ms;
    research_cycle_.budget_ms = max_solve_time_ms_;
    research_cycle_.success = info.success;
    research_cycle_.deadline_miss = std::strncmp(info.error, "solve_timeout", 13) == 0;
    research_cycle_.rejection_reason = info.success ? "" : info.error;
  }
  const Eigen::Vector2d applied_thrust = publish_dynamic_output_(selected_command);
  // 求解器 solve() 内部先保存了计划首拍；这里用经过 RC/VRX 映射后真正
  // 下发的等效推力覆盖，使下一拍 ΔT 代价和硬约束从执行输入出发。
  mpc_->set_applied_control(applied_thrust);
  last_commanded_thrust_ = selected_command;
  last_applied_thrust_ = applied_thrust;
  has_last_command_ = true;
  publish_status_(
    info, in_hold, selected_command, applied_thrust, solve_wall_time_ms, control_source);

  if (observe_reference) {
    reference_event.applied_sequence = latest_applied_sequence_.load();
    reference_event.solve_start_steady_ns = research_cycle_.solve_start_steady_ns;
    reference_event.solve_end_steady_ns = research_cycle_.solve_end_steady_ns;
    reference_event.backend = info.backend;
    reference_event.solve_success = info.success;
    reference_event.deadline_miss = research_cycle_.deadline_miss;
    reference_event.rejection_reason = research_cycle_.rejection_reason;
    const bool prediction_valid = info.success && !time_rejected &&
      info.X_pred.rows() == 6 && info.X_pred.cols() == reference.cols() &&
      info.U_pred.rows() == 2 && info.U_pred.cols() == reference.cols() - 1 &&
      info.X_pred.allFinite() && info.U_pred.allFinite();
    reference_event.prediction_available = prediction_valid;
    reference_event.prediction_reason = !info.success || time_rejected ?
      "solve_rejected" : (prediction_valid ? "accepted_solution" : "prediction_missing_or_invalid");
    if (prediction_valid) {
      reference_event.x_pred_rows = 6;
      reference_event.x_pred_cols = static_cast<uint32_t>(info.X_pred.cols());
      reference_event.x_pred_data.assign(info.X_pred.data(),
          info.X_pred.data() + info.X_pred.size());
      reference_event.u_pred_rows = 2;
      reference_event.u_pred_cols = static_cast<uint32_t>(info.U_pred.cols());
      reference_event.u_pred_data.assign(info.U_pred.data(),
          info.U_pred.data() + info.U_pred.size());
    }
    // Failed/rejected candidates are deliberately not copied or exposed as predictions.
    reference_event.freeze_steady_ns = research_steady_ns();
    research_->enqueue(std::move(reference_event), "reference_prediction");
  }
  control_count_++;
  if (control_count_ % 10 == 0) {
    int steer = rc_pwm_center_, thr = rc_pwm_center_;
    // RC debug uses the selected publication input, never the rejected candidate.
    thrust_to_rc_pwm_(selected_command, steer, thr);
    RCLCPP_INFO(this->get_logger(),
                "t=%.1fs  位置=(%.1f,%.1f)  计划推力=(%.1f,%.1f)N  "
                "下发等效推力=(%.1f,%.1f)N  RC(steer=%d, throttle=%d)  求解时间=%.0fms",
                control_count_ * mpc_dt_, current_state(0), current_state(1),
                selected_command(0), selected_command(1),
                applied_thrust(0), applied_thrust(1), steer, thr, info.solve_time_ms);
  }
}

// ── 推力 → RC PWM (对应 Python _thrust_to_rc_pwm, 用缓存 T_max/T_min) ──
Eigen::Vector2d MpcControllerNode::thrust_to_rc_pwm_(
  const Eigen::Vector2d & thrust, int & steering_pwm, int & throttle_pwm)
{
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
  const RcActuationResult result = thrust_to_rc_actuation(thrust, config);
  steering_pwm = result.steering_pwm;
  throttle_pwm = result.throttle_pwm;
  return result.effective_thrust;
}

Eigen::Vector2d MpcControllerNode::publish_rc_override_(
  const Eigen::Vector2d & thrust)
{
  int steer, thr;
  const Eigen::Vector2d applied_thrust =
    thrust_to_rc_pwm_(thrust, steer, thr);
  mavros_msgs::msg::OverrideRCIn msg;
  if (rc_steering_channel_ >= 0 && rc_steering_channel_ < static_cast<int>(msg.channels.size())) {
    msg.channels[rc_steering_channel_] = steer;
  }
  if (rc_throttle_channel_ >= 0 && rc_throttle_channel_ < static_cast<int>(msg.channels.size())) {
    msg.channels[rc_throttle_channel_] = thr;
  }
  rc_pub_->publish(msg);
  return applied_thrust;
}

Eigen::Vector2d MpcControllerNode::publish_dynamic_output_(
  const Eigen::Vector2d & thrust)
{
  if (output_mode_ == "vrx_thrust") {
    return publish_vrx_thrust_(thrust);
  }
  return publish_rc_override_(thrust);
}

void MpcControllerNode::publish_zero_dynamic_output_()
{
  has_last_command_ = false;
  last_commanded_thrust_.setZero();
  last_applied_thrust_.setZero();
  if (output_mode_ == "vrx_thrust") {
    release_vrx_thrust_();
  } else {
    release_rc_override_();
  }
}

void MpcControllerNode::release_rc_override_()
{
  has_last_command_ = false;
  // 全零 OverrideRCIn = 释放所有通道
  rc_pub_->publish(mavros_msgs::msg::OverrideRCIn());
}

// 对应 Python _publish_vrx_thrust: NMPC [TL,TR] (N) 经 scale/cmd_max 限幅后
// 直接发布到 VRX thruster topic (std_msgs/Float64, 单位 N)。
Eigen::Vector2d MpcControllerNode::publish_vrx_thrust_(
  const Eigen::Vector2d & thrust)
{
  std_msgs::msg::Float64 left, right;
  const double lower = std::max(dyn_T_min_, -vrx_thrust_cmd_max_);
  const double upper = std::min(dyn_T_max_, vrx_thrust_cmd_max_);
  const auto mapped = map_vrx(thrust, vrx_thrust_scale_, lower, upper, vrx_thrust_cmd_max_);
  left.data = mapped[0];right.data = mapped[1];
  if (research_ && research_->armed()) {return research_publish_(thrust, left, right);}
  vrx_left_pub_->publish(left);
  vrx_right_pub_->publish(right);
  return Eigen::Vector2d(left.data, right.data);
}

void MpcControllerNode::release_vrx_thrust_()
{
  has_last_command_ = false;
  // VRX thruster 无"释放通道"概念, 零推力即停船
  std_msgs::msg::Float64 left, right;
  left.data = 0.0;
  right.data = 0.0;
  if (research_ && research_->armed()) {
    research_publish_(Eigen::Vector2d::Zero(), left, right); return;
  }
  vrx_left_pub_->publish(left);
  vrx_right_pub_->publish(right);
}

void MpcControllerNode::publish_status_(
  const SolveInfo & info, bool in_hold,
  const Eigen::Vector2d & commanded_thrust,
  const Eigen::Vector2d & applied_thrust,
  double solve_wall_time_ms, const char * control_source)
{
  nlohmann::json j;
  j["state"] = in_hold ? "HOLD" : "ACTIVE";
  j["success"] = info.success;
  j["fail_count"] = solver_fail_count_;
  j["solve_time_ms"] = info.solve_time_ms;
  j["solve_wall_time_ms"] = solve_wall_time_ms;
  j["control_source"] = control_source;
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
  j["actuation_anchor_source"] =
    (output_mode_ == "vrx_thrust") ? "vrx_published" : "rc_linearized";
  j["actuation_mapping_error_n"] =
    (commanded_thrust - applied_thrust).cwiseAbs().maxCoeff();
  // 对应 RC PWM (与 Python _last_rc_debug 字段对齐)。
  {
    int steering_pwm = rc_pwm_center_, throttle_pwm = rc_pwm_center_;
    thrust_to_rc_pwm_(commanded_thrust, steering_pwm, throttle_pwm);
    j["steering_pwm"] = steering_pwm;
    j["throttle_pwm"] = throttle_pwm;
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
  j["solve_wall_time_ms"] = 0.0;
  j["control_source"] = "standby_release";
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

// ── 参考构建 (对应 Python _build_reference) ───────────────
Eigen::MatrixXd MpcControllerNode::build_reference_(
  const Vector6d & current_state, ResearchReference * evidence)
{
  ReferenceInput input;
  input.path = reference_path_;input.profile = ref_profile_;
  input.path_stamp = reference_path_stamp_;input.profile_stamp = ref_profile_stamp_;
  input.path_sequence = path_received_sequence_;input.profile_sequence = profile_received_sequence_;
  ReferenceMetadata metadata;
  auto ref = build_frozen_reference(current_state, input, mpc_->N(), mpc_->dt(),
    reference_start_offset_, cruise_speed_, &metadata);
  // Preserve F5 cached status, including its empty-path early return semantics.
  if (!input.path.empty()) {
    profile_synced_ = metadata.profile_synced;profile_sync_reason_ = metadata.profile_sync_reason;
  }
  if (evidence) {
    evidence->configured_start_offset = metadata.configured_start_offset;
    evidence->effective_start_offset = metadata.effective_start_offset;
    evidence->horizon_steps = metadata.horizon_steps;
    evidence->nearest_index = metadata.nearest_index;
    evidence->path_received_sequence = metadata.path_received_sequence;
    evidence->path_size = metadata.path_size;
    evidence->path_stamp_ns = metadata.path_stamp_ns;
    evidence->prediction_dt = metadata.prediction_dt;
    evidence->profile_received_sequence = metadata.profile_received_sequence;
    evidence->profile_size = metadata.profile_size;
    evidence->profile_stamp_known = metadata.profile_stamp_known;
    evidence->profile_stamp_ns = metadata.profile_stamp_ns;
    evidence->profile_sync_reason = metadata.profile_sync_reason;
    evidence->profile_synced = metadata.profile_synced;
    evidence->profile_t0 = metadata.profile_t0;
    evidence->profile_t0_known = metadata.profile_t0_known;
    evidence->reference_mode = metadata.reference_mode;
    evidence->start_index = metadata.start_index;
  }
  return ref;
}

void MpcControllerNode::safe_shutdown()
{
  shutting_down_.store(true);
  std::lock_guard<std::mutex> output_lock(control_output_mutex_);
  research_control_source_ = "shutdown_zero";
  if (research_) {research_->interrupted_cycle(active_research_cycle_.load());}
  active_research_cycle_ = 0;
  publish_zero_dynamic_output_();
  publish_standby_status_("node_shutdown");
  if (research_) {research_->stop(true);}
  RCLCPP_INFO(this->get_logger(), "MPC 节点退出: 已释放控制或发布零推力目标");
}

}  // namespace usv_mpc
