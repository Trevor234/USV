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

MpcControllerNode::MpcControllerNode(std::unique_ptr<DynamicMpc> solver,
  const rclcpp::NodeOptions & options)
: Node("mpc_controller_node", options), mpc_(std::move(solver))
{
  declare_parameters_();
  load_config_();
  init_mpc_solver_();
  init_state_();
  init_pubsub_();
  controlled_init_();
  // This derived binary has no opt-out release bypass. Creating publishers
  // registers graph endpoints; physical output is still held at every method.
  if (!research_ || !reference_logging_enabled_ || output_mode_ != "vrx_thrust") {
    throw std::runtime_error("D1 held publisher requires VRX, research and reference telemetry");
  }
  p1_startup_gate_ = std::make_unique<PublisherStartupGate>(
    this->get_parameter("research_output_dir").as_string(),
    this->get_parameter("p1_release_file").as_string(), p1_owned_startup_identity_());

  RCLCPP_INFO(this->get_logger(),
              "MPC 控制器已启动 | 模式=dynamic | dt=%.1fs | N=%d | "
              "类型=NMPC (动力学) | backend=%s | output=%s",
              mpc_dt_, horizon_, mpc_ ? mpc_->backend() : "none",
              output_mode_.c_str());

  timer_ = this->create_wall_timer(
      std::chrono::milliseconds(2),
      std::bind(&MpcControllerNode::control_loop_, this),
      control_cb_group_);
}

MpcControllerNode::~MpcControllerNode()
{
  if (research_) {research_->stop(false);}
}

nlohmann::json MpcControllerNode::p1_owned_startup_identity_()
{
  const auto contract = this->get_parameter("p1_owned_contract_sha256").as_string();
  if (!p1_startup::sha256_shape(contract)) {
    throw std::runtime_error("owned publisher requires actual execution contract SHA256");
  }
  p1_parameter_freeze_ = p1_owned::freeze_parameters(*this);
  auto endpoints = research_->owned_publisher_endpoints();
  endpoints.push_back(p1_owned::publisher_endpoint(*rc_pub_, "mavros_msgs/msg/OverrideRCIn"));
  endpoints.push_back(p1_owned::publisher_endpoint(*vrx_left_pub_, "std_msgs/msg/Float64"));
  endpoints.push_back(p1_owned::publisher_endpoint(*vrx_right_pub_, "std_msgs/msg/Float64"));
  endpoints.push_back(p1_owned::publisher_endpoint(*traj_pub_, "nav_msgs/msg/Path"));
  endpoints.push_back(p1_owned::publisher_endpoint(*status_pub_, "std_msgs/msg/String"));
  endpoints.push_back(p1_owned::subscription_endpoint(*odom_sub_, "nav_msgs/msg/Odometry"));
  endpoints.push_back(p1_owned::subscription_endpoint(*imu_sub_, "sensor_msgs/msg/Imu"));
  endpoints.push_back(p1_owned::subscription_endpoint(*path_sub_, "nav_msgs/msg/Path"));
  endpoints.push_back(p1_owned::subscription_endpoint(*profile_sub_, "std_msgs/msg/Float64MultiArray"));
  endpoints.push_back(p1_owned::subscription_endpoint(*state_sub_, "mavros_msgs/msg/State"));
  endpoints.push_back(p1_owned::subscription_endpoint(*research_clock_sub_, "rosgraph_msgs/msg/Clock"));
  endpoints.push_back(p1_owned::publisher_endpoint(*controlled_phase_pub_,"std_msgs/msg/String"));
  endpoints.push_back(p1_owned::subscription_endpoint(*controlled_decision_sub_,"usv_research_interfaces/msg/ExecutionDecision"));
  endpoints.push_back(p1_owned::subscription_endpoint(*controlled_job_sub_,"usv_research_interfaces/msg/SolveJob"));
  // TimeSource owns an additional /clock reader when use_sim_time=true.
  // Enumerate actual SubscriptionBase handles through public callback-group APIs;
  // graph node names or participant prefixes never manufacture ownership.
  this->get_node_base_interface()->for_each_callback_group([&](rclcpp::CallbackGroup::SharedPtr group) {
    group->find_subscription_ptrs_if([&](rclcpp::SubscriptionBase::SharedPtr sub) {
      if (std::string(sub->get_topic_name()) == "/clock") {
        const auto endpoint = p1_owned::subscription_endpoint(*sub, "rosgraph_msgs/msg/Clock");
        bool present = false;
        for (const auto & existing : endpoints) {if (existing == endpoint) {present = true;}}
        if (!present) {endpoints.push_back(endpoint);}
      }
      return false; // Visit every live subscription in this callback group.
    });
  });
  const auto startup = research_->startup_identity();
  const auto owned = p1_owned::role_manifest(*this, "publisher", startup.at("run_id"),
    contract, P1_D1_SOURCE_BUNDLE_SHA256, endpoints,
    {{"producer_instance_id", startup.at("producer_instance_id")},
      {"config_hash", startup.at("config_hash")},
      {"nominal_config_hash", startup.at("nominal_config_hash")},
      {"parent_baseline_manifest_sha256", P1_D1_F5_PARENT_MANIFEST_SHA256},
      {"physical_output_state", "held"},
      {"baseline_id",controlled::baseline},{"controlled_phase_mode",controlled_mode_},
      {"controlled_source_fd",p1_owned::source_fd_identity(this->get_parameter("research_output_dir").as_string()+"/controlled_source.jsonl")},
      {"controlled_owner_profile","diagnostic_owner; not frozen F5 runtime qualification"},
      {"endpoint_scope", "all_explicit_application_publishers_and_subscriptions"},
      {"infrastructure_endpoints_in_scope", false}});
  const auto owned_path = std::filesystem::path(
    this->get_parameter("research_output_dir").as_string()) / "owned_manifest.json";
  p1_owned::write_create_only(owned_path.string(), owned);
  std::string owned_bytes;
  if (!p1_startup::read_regular_bounded(owned_path, owned_bytes, 262144)) {
    throw std::runtime_error("publisher owned manifest missing after create-only write");
  }
  auto identity = startup;
  identity["owned_manifest_file"] = "owned_manifest.json";
  identity["owned_manifest_sha256"] = p1_startup::sha256_bytes(owned_bytes);
  identity["contract_sha256"] = contract;
  identity["effective_parameters_sha256"] = owned.at("effective_parameters_sha256");
  identity["parameter_encoding"] = "p1-typed-ieee754-v1";
  identity["application_endpoints"] = endpoints;
  identity["effective_configuration_frozen"] = true;
  return identity;
}

bool MpcControllerNode::p1_poll_release_()
{
  // Release acceptance and shutdown share one linearization lock. Shutdown
  // cannot arm/commit a release indirectly by racing the preparation path.
  std::lock_guard<std::mutex> output_lock(control_output_mutex_);
  if (shutting_down_.load() || !p1_startup_gate_ || !research_) {return false;}
  return p1_startup_gate_->poll_release([this]() {
    research_->arm();
#ifdef P1_PUBLISHER_TEST
    if (p1_test_release_arm_latch_) {p1_test_release_arm_latch_();}
#endif
    return research_->armed();
  });
}

bool MpcControllerNode::p1_output_permitted_()
{
  return p1_startup_gate_ && research_ && research_->armed() &&
    p1_startup_gate_->released_and_unchanged();
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
  if (!p1_output_permitted_()) {return Eigen::Vector2d::Zero();}
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
  this->declare_parameter("p1_release_file", std::string(""));
  this->declare_parameter("p1_owned_contract_sha256", std::string(""));
  this->declare_parameter("controlled_phase_mode",std::string("A2"));
  this->declare_parameter("controlled_observer_manifest_file",std::string(""));
  this->declare_parameter("controlled_observer_binary_sha256",std::string(""));
  this->declare_parameter("controlled_observer_source_bundle_sha256",std::string(""));
  this->declare_parameter("controlled_observer_run_id",std::string(""));
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
  std::lock_guard<std::mutex> lk(state_lock_);
  x_ = p.x;
  y_ = p.y;
  psi_ = psi;
  u_ = t.linear.x;
  v_ = t.linear.y;
  r_ = t.angular.z;
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
  if (!std::isfinite(r)) {
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
  research_control_source_ = "standby_release";
  publish_zero_dynamic_output_();
  prev_state_ = "STANDBY";
  publish_standby_status_(reason);
  RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                       "MPC 等待飞控就绪: %s", reason.c_str());
}

void MpcControllerNode::control_loop_()
{
  controlled_cycle_();return; // New diagnostic owner: autonomous F5 solve path is not executed.

  if (!p1_poll_release_()) {return;}
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
  if (!p1_output_permitted_()) {return Eigen::Vector2d::Zero();}
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
  if (!p1_output_permitted_()) {return Eigen::Vector2d::Zero();}
  if (output_mode_ == "vrx_thrust") {
    return publish_vrx_thrust_(thrust);
  }
  return publish_rc_override_(thrust);
}

void MpcControllerNode::publish_zero_dynamic_output_()
{
  if (!p1_output_permitted_()) {return;}
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
  if (!p1_output_permitted_()) {return;}
  has_last_command_ = false;
  // 全零 OverrideRCIn = 释放所有通道
  rc_pub_->publish(mavros_msgs::msg::OverrideRCIn());
}

// 对应 Python _publish_vrx_thrust: NMPC [TL,TR] (N) 经 scale/cmd_max 限幅后
// 直接发布到 VRX thruster topic (std_msgs/Float64, 单位 N)。
Eigen::Vector2d MpcControllerNode::publish_vrx_thrust_(
  const Eigen::Vector2d & thrust)
{
  if (!p1_output_permitted_()) {return Eigen::Vector2d::Zero();}
  std_msgs::msg::Float64 left, right;
  const double lower = std::max(dyn_T_min_, -vrx_thrust_cmd_max_);
  const double upper = std::min(dyn_T_max_, vrx_thrust_cmd_max_);
  left.data = std::clamp(thrust(0) * vrx_thrust_scale_, lower, upper);
  right.data = std::clamp(thrust(1) * vrx_thrust_scale_, lower, upper);
  return research_publish_(thrust, left, right);
}

void MpcControllerNode::release_vrx_thrust_()
{
  if (!p1_output_permitted_()) {return;}
  has_last_command_ = false;
  // VRX thruster 无"释放通道"概念, 零推力即停船
  std_msgs::msg::Float64 left, right;
  left.data = 0.0;
  right.data = 0.0;
  research_publish_(Eigen::Vector2d::Zero(), left, right);
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
  const Vector6d & current_state,
  ResearchReference * evidence)
{
  const int N = mpc_->N();
  double dt = mpc_->dt();
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(6, N + 1);
  const auto & path = reference_path_;
  if (evidence) {
    evidence->horizon_steps = static_cast<uint32_t>(N);
    evidence->prediction_dt = dt;
    evidence->path_received_sequence = path_received_sequence_;
    evidence->profile_received_sequence = profile_received_sequence_;
    evidence->path_stamp_ns = reference_path_stamp_.first < 0 ? -1 :
      int64_t(reference_path_stamp_.first) * 1000000000LL + reference_path_stamp_.second;
    evidence->profile_stamp_known = ref_profile_stamp_.first >= 0;
    evidence->profile_stamp_ns = !evidence->profile_stamp_known ? -1 :
      int64_t(ref_profile_stamp_.first) * 1000000000LL + ref_profile_stamp_.second;
    evidence->path_size = path.size();
    evidence->profile_size = ref_profile_.size();
    evidence->nearest_index = -1;
    evidence->start_index = -1;
    evidence->configured_start_offset = reference_start_offset_;
    evidence->effective_start_offset = std::max(1, reference_start_offset_);
    evidence->reference_mode = "empty_path";
    evidence->profile_sync_reason = "empty_path";
  }

  if (path.empty()) {return ref;}

  // 最近点 + start_offset
  double best_d = 1e18; int nearest = 0;
  for (size_t i = 0; i < path.size(); ++i) {
    double d = std::hypot(path[i][0] - current_state(0), path[i][1] - current_state(1));
    if (d < best_d) {best_d = d; nearest = static_cast<int>(i);}
  }
  int idx = std::min(nearest + std::max(1, reference_start_offset_),
                     static_cast<int>(path.size()) - 1);
  if (evidence) {evidence->nearest_index = nearest; evidence->start_index = idx;}

  // profile 同步判定
  int profile_len = ref_profile_.empty() ? -1 : static_cast<int>(ref_profile_.size());
  const std::pair<int,
    int> * p_stamp = (ref_profile_stamp_.first >= 0) ? &ref_profile_stamp_ : nullptr;
  const std::pair<int,
    int> * path_stamp = (reference_path_stamp_.first >= 0) ? &reference_path_stamp_ : nullptr;
  auto [synced, sync_reason] = profile_sync_state(
      static_cast<int>(path.size()), profile_len, path_stamp, p_stamp);

  if (evidence) {
    evidence->profile_synced = synced; evidence->profile_sync_reason = sync_reason;
    evidence->reference_mode = synced ? "profile_time" : "cruise_arc_fallback";
  }
  if (synced) {
    std::vector<double> times(ref_profile_.size()), vs(ref_profile_.size()),
    rs(ref_profile_.size());
    for (size_t i = 0; i < ref_profile_.size(); ++i) {
      times[i] = ref_profile_[i][3]; vs[i] = ref_profile_[i][0]; rs[i] = ref_profile_[i][2];
    }
    double t0 = times[idx];
    if (evidence) {evidence->profile_t0_known = true; evidence->profile_t0 = t0;}
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
      arc.push_back(arc.back() + std::hypot(path[i + 1][0] - path[i][0],
          path[i + 1][1] - path[i][1]));
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
          ref(0, k) = path[ii][0]; ref(1, k) = path[ii][1]; ref(2, k) = path[ii][2];
        }
      } else {
        ref(0, k) = path[ii][0]; ref(1, k) = path[ii][1]; ref(2, k) = path[ii][2];
      }
      ref(3, k) = cruise_speed_; ref(4, k) = 0.0; ref(5, k) = 0.0;
    }
  }

  // 航向角连续化展开 (Phase Unwrapping):
  // 保证 ref(2, 0) 与 current_state(2) 无 ±2pi 阶跃,
  // 且 ref(2, k) 在时域内连续, 消除 ±pi 边界处的 360° 虚假跳跃
  ref(2, 0) = current_state(2) + normalize_angle(ref(2, 0) - current_state(2));
  for (int k = 1; k <= N; ++k) {
    ref(2, k) = ref(2, k - 1) + normalize_angle(ref(2, k) - ref(2, k - 1));
  }

  return ref;
}

void MpcControllerNode::p1_write_release_observation()
{
  std::lock_guard<std::mutex> output_lock(control_output_mutex_);
  if (!shutting_down_.load() || !p1_startup_gate_) {
    throw std::runtime_error("release observation requires completed shutdown path entry");
  }
  const auto & identity = p1_startup_gate_->identity();
  nlohmann::json binding = nlohmann::json::object();
  for (const auto key : {"run_id", "producer_instance_id", "steady_clock_domain", "boot_id", "pid",
      "process_start_ticks", "source_bundle_sha256", "binary_sha256", "baseline_id", "config_hash",
      "nominal_config_hash", "contract_sha256", "owned_manifest_sha256", "effective_parameters_sha256"}) {
    if (identity.contains(key)) {binding[key] = identity.at(key);}
  }
  const nlohmann::json report = {{"schema_version", "p1-D1-publisher-release-observation-v1"},
    {"identity", binding}, {"startup_manifest_sha256", p1_startup_gate_->manifest_sha256()},
    {"controller_shutdown_requested", shutting_down_.load()},
    {"snapshot_steady_ns", p1_startup::steady_ns()}, {"gate", p1_startup_gate_->observation()},
    {"terminal_observation_only", true}, {"receipt_qualifies_physical_release", false},
    {"physical_release_qualified", false}, {"execute_qualified", false}, {"research_conclusion", false}};
  const std::string bytes = report.dump(2) + "\n";
  if (bytes.size() > 32768) {throw std::runtime_error("release observation exceeds fixed32 KiB budget");}
  p1_startup::write_create_only(std::filesystem::path(
    this->get_parameter("research_output_dir").as_string()) / "release_observation.json", bytes);
  controlled_log_({{"type","controlled_owner_source_closed"},{"closed_ns",research_steady_ns()},{"executor_detached",true},
    {"decision_receipts",controlled_decision_receipts_},{"job_receipts",controlled_job_receipts_},
    {"Applied_emitted",controlled_applied_emitted_count_},{"phases_emitted",controlled_phase_emitted_count_},
    {"pending_phase_count",controlled_pending_.size()},{"queued_decisions",controlled_decisions_.size()},{"pulse_fired",controlled_pulse_fired_},{"pulse_restored",controlled_pulse_restored_}});
}

void MpcControllerNode::safe_shutdown()
{
  std::lock_guard<std::mutex> output_lock(control_output_mutex_);
  if(shutting_down_.exchange(true))return;
#ifdef P1_PUBLISHER_TEST
  if (p1_test_shutdown_latch_) {p1_test_shutdown_latch_();}
#endif
  research_control_source_ = "shutdown_zero";
  if (research_) {research_->interrupted_cycle(active_research_cycle_.load());}
  active_research_cycle_ = 0;
  publish_zero_dynamic_output_();
  publish_standby_status_("node_shutdown");
  if (research_) {research_->stop(true);}
  RCLCPP_INFO(this->get_logger(), "D1 publisher shutdown: output remained subject to accepted release gate");
}

}  // namespace usv_mpc
