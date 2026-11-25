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
 * @file path_planner_node.hpp
 * @brief 路径规划 ROS 2 节点（C++ 版本）。
 *
 * 根据航点生成平滑参考路径（圆弧倒角 + TOPP 速度剖面），
 * 并以 NavPath + Float64MultiArray 形式发布给 MPC 控制器。
 *
 * 对应 Python 版本: usv_planning/path_planner_node.py
 */

#pragma once

#include <memory>
#include <optional>
#include <string>

#include <Eigen/Dense>
#include <rclcpp/rclcpp.hpp>
#include <builtin_interfaces/msg/time.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <nav_msgs/msg/path.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>

#include "usv_planning/waypoint_manager.hpp"

namespace usv_planning
{

class PathPlannerNode : public rclcpp::Node {
public:
  PathPlannerNode();

private:
  void declare_parameters_();
  void load_config_();
  void load_waypoints_from_file_();

  // ── 回调 ────────────────────────────────────────────
  void odom_callback_(const nav_msgs::msg::Odometry::SharedPtr msg);
  void dynamic_waypoints_callback_(const nav_msgs::msg::Path::SharedPtr msg);
  void publish_path_();
  void publish_empty_path_();

  // ── 路径生成 ────────────────────────────────────────
  struct SmoothPathResult
  {
    Eigen::VectorXd xs, ys, psis, kappas, vs, rs, ts;
  };
  std::optional<SmoothPathResult> generate_smooth_path_();

  std_msgs::msg::Float64MultiArray build_profile_msg_(
    const Eigen::VectorXd & vs,
    const Eigen::VectorXd & kappas,
    const Eigen::VectorXd & rs,
    const Eigen::VectorXd & ts,
    const builtin_interfaces::msg::Time & stamp);

  // ── 航点管理 ────────────────────────────────────────
  WaypointManager wp_manager_;

  // ── 当前位姿 ────────────────────────────────────────
  double x_ = 0.0;
  double y_ = 0.0;
  double psi_ = 0.0;
  double u_ = 0.0;    // 当前纵向速度

  // ── 配置参数 ────────────────────────────────────────
  double      update_rate_ = 1.0;
  double      path_resolution_ = 0.5;
  double      turn_radius_ = 5.0;
  std::string odom_topic_;
  std::string path_topic_;
  std::string profile_topic_;
  std::string dynamic_wp_topic_;
  std::string waypoints_file_;
  double      default_wp_radius_ = 2.0;

  // TOPP 速度剖面约束
  double u_max_ = 2.0;
  double r_max_ = 0.5;
  double lat_accel_max_ = 1.0;
  double accel_max_ = 0.5;
  double decel_max_ = 0.5;
  double v_end_ = 0.0;
  double v_min_ = 0.2;

  // 可选最小曲率精修
  bool   enable_curv_opt_ = false;
  int    curv_opt_max_iter_ = 40;
  double curv_opt_corridor_ = 1.0;

  // ── ROS 通信 ────────────────────────────────────────
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr     dynamic_wp_sub_;
  rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr        path_pub_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr profile_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

}  // namespace usv_planning
