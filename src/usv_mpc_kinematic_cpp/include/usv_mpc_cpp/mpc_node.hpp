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
 * @brief USV MPC 控制器 ROS 2 节点 (C++ 版本, 方案 A 运动学 MPC)。
 *
 * 对应 Python 版本: usv_mpc/mpc_node.py (方案 A, MultiThreadedExecutor 版)
 *
 * 订阅: /mavros/local_position/odom, /mavros/imu/data, /path/reference,
 *       /path/reference_profile, /mavros/state
 * 发布: /mavros/setpoint_velocity/cmd_vel (TwistStamped), /mpc/status,
 *       /mpc/predicted_trajectory
 *
 * 与方案 B 的 mpc_node.hpp 结构同构, 但:
 *   - 输出 TwistStamped (体坐标系速度) 而非 OverrideRCIn (RC PWM)
 *   - 参数 kinematic.* (无 dynamic.*, 无 vehicle.*, 无 rc_*)
 *   - 状态 3 维 [x,y,psi] (B 是 6 维)
 *   - 无 thrust_to_rc_pwm_ / RC 映射字段
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
#include <geometry_msgs/msg/twist_stamped.hpp>
#include <mavros_msgs/msg/state.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <nav_msgs/msg/path.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <std_msgs/msg/string.hpp>

#include "usv_mpc_cpp/kinematic_mpc_solver.hpp"
#include "usv_mpc_cpp/utils.hpp"

namespace usv_mpc
{

class MpcControllerNode : public rclcpp::Node {
public:
  MpcControllerNode();
  ~MpcControllerNode() override;

  /// 节点退出前发送安全停车指令 (零速度 TwistStamped)。
  void safe_shutdown();

private:
  // Tests inject a solver without exposing fault-injection ROS parameters.
  friend class MpcControllerNodeTestAccess;
  explicit MpcControllerNode(std::unique_ptr<KinematicMpc> solver);
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
  void run_kinematic_mpc_();
  // Returns true when timing rejects the result (timeout or invalid timing).
  bool enforce_solve_deadline_(SolveInfo & info, double solve_wall_time_ms);

  // ── 输出 (★ A 输出 TwistStamped, 无 RC 映射) ─────────
  void publish_velocity_cmd_(const Eigen::Vector2d & u_opt);
  void publish_zero_velocity_();
  void publish_status_(
    const SolveInfo & info, bool in_hold,
    const Eigen::Vector2d & u_opt,
    const Eigen::Vector3d & current_state,
    const Eigen::MatrixXd & reference);
  void publish_standby_status_(const std::string & reason);
  void publish_predicted_trajectory_(const Eigen::MatrixXd & X_pred);

  // ── 参考构建 (对齐 B: 作为 node 私有方法, 无独立类) ───
  Eigen::MatrixXd build_reference_(const Eigen::Vector3d & current_state);

  // ── 状态锁 (传感器回调与控制循环并发) ────────────────
  std::mutex state_lock_;

  // MPC 求解器
  std::unique_ptr<KinematicMpc> mpc_;
  double kin_dt_ = 0.0;
  int kin_N_ = 0;
  double kin_prediction_time_ = 0.0;
  // Deadline 拒绝后的重放指令 (repeat-last 语义, 对齐 B)。
  Eigen::Vector2d last_commanded_velocity_ = Eigen::Vector2d::Zero();
  bool has_last_command_ = false;
  // Shutdown can run outside the timer's callback group. Serialize output and
  // cache changes without holding this mutex across synchronous solve().
  std::mutex control_output_mutex_;
  std::atomic<bool> shutting_down_{false};

  // ── 当前状态 (运动学只用 x,y,psi; u/v/r 用于 status 上报) ──
  double x_ = 0, y_ = 0, psi_ = 0, u_ = 0, v_ = 0, r_ = 0;
  bool odom_received_ = false, imu_received_ = false, path_received_ = false;
  bool armed_ = false;
  std::string mode_ = "MANUAL";
  int solver_fail_count_ = 0;
  int control_count_ = 0;
  double last_state_time_ = 0.0;
  double last_odom_time_ = 0.0;
  std::string prev_state_;          // "" / "ACTIVE" / "STANDBY"

  // 参考路径 + profile (类型对齐 B + utils 签名)
  std::vector<std::array<double, 3>> reference_path_;  // [x,y,psi]
  std::pair<int, int> reference_path_stamp_{-1, -1};
  std::vector<std::array<double, 4>> ref_profile_;     // [v,kappa,r,t]
  std::pair<int, int> ref_profile_stamp_{-1, -1};
  bool profile_synced_ = false;
  std::string profile_sync_reason_ = "no_profile";

  // ── 配置 ────────────────────────────────────────────
  // 控制模式: "kinematic" 正常解算; "idle" 只发零速度不解算。
  // 原实现读入局部变量后丢弃, 导致 idle 是假开关 (2026-10-21 修复)。
  std::string control_mode_ = "kinematic";
  std::string scheme_ = "A";
  double mpc_dt_ = 0.2;
  int horizon_ = 20;
  double max_solve_time_ms_ = 200.0;
  bool require_fcu_state_ = true;
  std::string path_frame_ = "map";
  std::string body_frame_ = "base_link";   // ★ A 有 body_frame (B 无, 因 B 输出 RC)
  bool publish_predicted_ = true;
  int solver_hold_threshold_ = 5;
  std::vector<std::string> allowed_fcu_modes_ = {"GUIDED"};
  double state_timeout_s_ = 2.0;            // ★ A 用 2.0 (B 用 5.0)
  double odom_timeout_s_ = 1.0;
  int reference_start_offset_ = 1;          // ★ A 用 1 (B 用 3)
  double cruise_speed_ = 1.0;
  std::string backend_param_ = "ipopt";     // kinematic.backend 参数 (C++ 只实现 casadi)

  // ★ 无 RC 映射字段 (B 有 rc_steering_channel_ 等 8 个, A 不需要)

  // ── ROS 接口 ────────────────────────────────────────
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_sub_;
  rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr path_sub_;
  rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr profile_sub_;
  rclcpp::Subscription<mavros_msgs::msg::State>::SharedPtr state_sub_;
  // ★ Twist (B 是 rc_pub_)
  rclcpp::Publisher<geometry_msgs::msg::TwistStamped>::SharedPtr vel_pub_;
  rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr traj_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_pub_;
  rclcpp::TimerBase::SharedPtr timer_;

  // 多线程执行器 (控制循环与 IO 回调并发, 对齐 B)
  rclcpp::CallbackGroup::SharedPtr io_cb_group_;
  rclcpp::CallbackGroup::SharedPtr control_cb_group_;
};

}  // namespace usv_mpc
