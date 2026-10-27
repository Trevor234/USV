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
 * @file mpc_node.hpp
 * @brief USV MPC 控制器 ROS 2 节点 (C++ 版本, 动力学 NMPC)。
 *
 * 对应 Python 版本: usv_mpc/mpc_node.py (清理后版本: 仅 NMPC)
 *
 * 订阅: /mavros/local_position/odom, /mavros/imu/data, /path/reference,
 *       /path/reference_profile, /mavros/state
 * 发布: /mavros/rc/override (output_mode=rc_override, 实机) 或
 *       /wamv/thrusters/{left,right}/thrust (output_mode=vrx_thrust, VRX 仿真),
 *       /mpc/status, /mpc/predicted_trajectory
 */

#pragma once

#include <array>
#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <utility>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <mavros_msgs/msg/override_rc_in.hpp>
#include <mavros_msgs/msg/state.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <nav_msgs/msg/path.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <std_msgs/msg/float64.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <std_msgs/msg/string.hpp>

#include <rosgraph_msgs/msg/clock.hpp>
#include "usv_mpc_cpp/research_logger.hpp"
#include "usv_mpc_cpp/mpc_solver.hpp"
#include "usv_mpc_cpp/utils.hpp"

namespace usv_mpc
{

class MpcControllerNode : public rclcpp::Node {
public:
  MpcControllerNode();
  ~MpcControllerNode() override;

  /// 节点退出前发送安全停车指令。
  void safe_shutdown();

private:
  // Tests inject a solver without exposing fault-injection ROS parameters.
  friend class MpcControllerNodeTestAccess;
  explicit MpcControllerNode(std::unique_ptr<DynamicMpc> solver);

  // ── 初始化 ──────────────────────────────────────────
  void declare_parameters_();
  void load_config_();
  void init_mpc_solver_();
  void init_state_();
  void init_pubsub_();

  // ── 回调 ────────────────────────────────────────────
  void odom_callback_(const nav_msgs::msg::Odometry::SharedPtr msg);
  void imu_callback_(const sensor_msgs::msg::Imu::SharedPtr msg);
  void path_callback_(const nav_msgs::msg::Path::SharedPtr msg);
  void profile_callback_(const std_msgs::msg::Float64MultiArray::SharedPtr msg);
  void state_callback_(const mavros_msgs::msg::State::SharedPtr msg);

  // ── 控制循环 ────────────────────────────────────────
  void control_loop_();
  std::pair<bool, std::string> can_solve_() const;
  void enter_standby_(const std::string & reason);
  void run_dynamic_mpc_();
  // Returns true when timing rejects the result (timeout or invalid timing).
  bool enforce_solve_deadline_(SolveInfo & info, double solve_wall_time_ms);

  // ── 输出 ────────────────────────────────────────────
  Eigen::Vector2d thrust_to_rc_pwm_(
    const Eigen::Vector2d & thrust,
    int & steering_pwm, int & throttle_pwm);
  Eigen::Vector2d publish_rc_override_(const Eigen::Vector2d & thrust);
  Eigen::Vector2d publish_vrx_thrust_(const Eigen::Vector2d & thrust);
  void release_vrx_thrust_();
  Eigen::Vector2d publish_dynamic_output_(const Eigen::Vector2d & thrust);
  void publish_zero_dynamic_output_();
  void release_rc_override_();
  void publish_status_(
    const SolveInfo & info, bool in_hold,
    const Eigen::Vector2d & commanded_thrust,
    const Eigen::Vector2d & applied_thrust,
    double solve_wall_time_ms, const char * control_source);
  void publish_standby_status_(const std::string & reason);
  void publish_predicted_trajectory_(const Eigen::MatrixXd & X_pred);

  // ── 参考构建 ────────────────────────────────────────
  Eigen::MatrixXd build_reference_(const Vector6d & current_state);

  void research_clock_(const rosgraph_msgs::msg::Clock::SharedPtr msg);
  template<class T> void research_time_(T & msg)
  {
    std::lock_guard<std::mutex> lock(research_clock_mutex_);
    msg.sim_time_ns = observed_sim_ns_;
    msg.clock_epoch = observed_epoch_;
    msg.clock_receive_steady_ns = observed_clock_receive_ns_;
    msg.clock_age_ns = observed_clock_receive_ns_ == 0 ? -1 :
      research_steady_ns() - observed_clock_receive_ns_;
    msg.clock_status = observed_clock_status_;
  }
  void research_state_(
    const nav_msgs::msg::Odometry & msg, uint64_t received,
    int64_t receive_ns, double yaw);
  Eigen::Vector2d research_publish_(
    const Eigen::Vector2d & requested,
    const std_msgs::msg::Float64 & left, const std_msgs::msg::Float64 & right);
  std::unique_ptr<ResearchLogger> research_;
  rclcpp::Subscription<rosgraph_msgs::msg::Clock>::SharedPtr research_clock_sub_;
  rclcpp::CallbackGroup::SharedPtr research_clock_group_;
  std::mutex research_clock_mutex_;
  int64_t observed_sim_ns_ = -1, observed_clock_receive_ns_ = 0;
  uint64_t observed_epoch_ = 0;
  std::string observed_clock_status_ = "not_received";
  uint64_t received_odom_count_ = 0, received_imu_count_ = 0;
  uint64_t accepted_odom_sequence_ = 0, accepted_imu_sequence_ = 0;
  int64_t accepted_odom_stamp_ns_ = 0, accepted_imu_stamp_ns_ = 0;
  bool r_from_imu_ = false;
  uint64_t research_cycle_sequence_ = 0;
  std::atomic<uint64_t> active_research_cycle_{0}, latest_applied_sequence_{0};
  bool observed_previous_known_ = false;
  std::array<double, 2> observed_previous_final_{};
  ResearchCycle research_cycle_;
  const char * research_control_source_ = "direct_call";

  // ── 状态锁 (传感器回调与控制循环并发) ────────────────
  std::mutex state_lock_;

  // MPC 求解器
  std::unique_ptr<DynamicMpc> mpc_;
  double dyn_dt_ = 0.0;
  int dyn_N_ = 0;
  double dyn_prediction_time_ = 0.0;
  double dyn_T_max_ = 25.0;   // 缓存,热路径用
  double dyn_T_min_ = -25.0;
  // Cache the publication input separately from the mapped output: replaying
  // applied thrust through the mapper would scale/map it a second time.
  Eigen::Vector2d last_commanded_thrust_ = Eigen::Vector2d::Zero();
  Eigen::Vector2d last_applied_thrust_ = Eigen::Vector2d::Zero();
  bool has_last_command_ = false;
  // Shutdown can run outside the timer's callback group. Serialize output and
  // cache changes without holding this mutex across synchronous solve().
  std::mutex control_output_mutex_;
  std::atomic<bool> shutting_down_{false};

  // ── 当前状态 ────────────────────────────────────────
  double x_ = 0, y_ = 0, psi_ = 0, u_ = 0, v_ = 0, r_ = 0;
  bool odom_received_ = false, imu_received_ = false, path_received_ = false;
  bool armed_ = false;
  std::string mode_ = "MANUAL";
  int solver_fail_count_ = 0;
  int control_count_ = 0;
  double last_state_time_ = 0.0;
  double last_odom_time_ = 0.0;
  std::string prev_state_;          // "" / "ACTIVE" / "STANDBY"

  // 参考路径 + profile
  std::vector<std::array<double, 3>> reference_path_;  // [x,y,psi]
  std::pair<int, int> reference_path_stamp_{-1, -1};
  std::vector<std::array<double, 4>> ref_profile_;     // [v,kappa,r,t]
  std::pair<int, int> ref_profile_stamp_{-1, -1};
  bool profile_synced_ = false;
  std::string profile_sync_reason_ = "no_profile";

  // ── 配置 ────────────────────────────────────────────
  double mpc_dt_ = 0.2;
  int horizon_ = 20;
  double max_solve_time_ms_ = 200.0;
  bool require_fcu_state_ = true;
  std::string path_frame_ = "map";
  bool publish_predicted_ = true;
  int solver_hold_threshold_ = 5;
  std::vector<std::string> allowed_fcu_modes_ = {"GUIDED"};
  double state_timeout_s_ = 5.0;
  double odom_timeout_s_ = 1.0;
  int reference_start_offset_ = 3;
  double cruise_speed_ = 1.0;

  // RC 映射
  int rc_steering_channel_ = 0;
  int rc_throttle_channel_ = 2;
  int rc_pwm_min_ = 1100, rc_pwm_center_ = 1500, rc_pwm_max_ = 1900;
  double steering_sign_ = 1.0, throttle_sign_ = 1.0;
  double steering_gain_ = 0.25, throttle_gain_ = 0.5;

  // 输出后端: "rc_override" (实机 ArduRover) 或 "vrx_thrust" (VRX Gazebo 直接推力)
  std::string output_mode_ = "rc_override";
  double vrx_thrust_scale_ = 25.0;
  double vrx_thrust_cmd_max_ = 1000.0;

  // ── ROS 接口 ────────────────────────────────────────
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_sub_;
  rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr path_sub_;
  rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr profile_sub_;
  rclcpp::Subscription<mavros_msgs::msg::State>::SharedPtr state_sub_;
  rclcpp::Publisher<mavros_msgs::msg::OverrideRCIn>::SharedPtr rc_pub_;
  rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr vrx_left_pub_;
  rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr vrx_right_pub_;
  rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr traj_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_pub_;
  rclcpp::TimerBase::SharedPtr timer_;

  // 多线程执行器 (控制循环与 IO 回调并发)
  rclcpp::CallbackGroup::SharedPtr io_cb_group_;
  rclcpp::CallbackGroup::SharedPtr control_cb_group_;
};

}  // namespace usv_mpc
