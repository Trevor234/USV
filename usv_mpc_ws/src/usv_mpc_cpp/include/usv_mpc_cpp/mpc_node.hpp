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
#include <memory>
#include <mutex>
#include <string>
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

#include "usv_mpc_cpp/mpc_solver.hpp"
#include "usv_mpc_cpp/utils.hpp"

namespace usv_mpc {

class MpcControllerNode : public rclcpp::Node {
 public:
  MpcControllerNode();
  ~MpcControllerNode() override;

  /// 节点退出前发送安全停车指令。
  void safe_shutdown();

 private:
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
  void enter_standby_(const std::string& reason);
  void run_dynamic_mpc_();
  bool enforce_solve_deadline_(SolveInfo& info);

  // ── 输出 ────────────────────────────────────────────
  void thrust_to_rc_pwm_(const Eigen::Vector2d& thrust, int& steering_pwm,
                         int& throttle_pwm);
  void publish_rc_override_(const Eigen::Vector2d& thrust);
  void publish_vrx_thrust_(const Eigen::Vector2d& thrust);
  void release_vrx_thrust_();
  void publish_dynamic_output_(const Eigen::Vector2d& thrust);
  void publish_zero_dynamic_output_();
  void release_rc_override_();
  void publish_status_(const SolveInfo& info, bool in_hold,
                       const Eigen::Vector2d& thrust);
  void publish_standby_status_(const std::string& reason);
  void publish_predicted_trajectory_(const Eigen::MatrixXd& X_pred);

  // ── 参考构建 ────────────────────────────────────────
  Eigen::MatrixXd build_reference_(const Vector6d& current_state);

  // ── 状态锁 (传感器回调与控制循环并发) ────────────────
  std::mutex state_lock_;

  // MPC 求解器
  std::unique_ptr<DynamicMpc> mpc_;
  double dyn_dt_ = 0.0;
  int dyn_N_ = 0;
  double dyn_prediction_time_ = 0.0;
  double dyn_T_max_ = 25.0;   // 缓存,热路径用
  double dyn_T_min_ = -25.0;

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
