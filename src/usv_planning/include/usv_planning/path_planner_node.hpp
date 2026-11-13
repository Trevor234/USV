// 版权所有 2026 USV Developer
//
// 特此免费授予任何获得本软件及相关文档文件（下称“软件”）副本的人不受限制地处置该软件的权利，
// 包括但不限于使用、复制、修改、合并、发布、分发、再许可和/或出售软件副本的权利，
// 以及允许获得本软件的人这样做，但须满足以下条件：
//
// 上述版权声明和本许可声明应包含在软件的所有副本或主要部分中。
//
// 本软件按“原样”提供，不附带任何明示或暗示的担保，包括但不限于对适销性、
// 特定用途适用性和非侵权性的担保。在任何情况下，作者或版权持有人均不对因软件、
// 软件的使用或与软件相关的其他交易而产生的任何索赔、损害赔偿或其他责任承担责任，
// 无论该等责任是基于合同诉讼、侵权行为还是其他原因。


/**
 * @file path_planner_node.hpp
 * @brief 路径规划 ROS 2 节点。
 *
 * 根据航点生成平滑参考路径（圆弧倒角 + TOPP 速度剖面），
 * 并以 NavPath + Float64MultiArray 形式发布给 MPC 控制器。
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

namespace usv_planning {

class PathPlannerNode : public rclcpp::Node {
 public:
  PathPlannerNode();

 private:
  void declare_parameters_();
  void load_config_();

  // ── 回调 ────────────────────────────────────────────
  void odom_callback_(const nav_msgs::msg::Odometry::SharedPtr msg);
  void dynamic_waypoints_callback_(const nav_msgs::msg::Path::SharedPtr msg);
  void publish_path_();
  void publish_empty_path_();

  // ── 路径生成 ────────────────────────────────────────
  struct SmoothPathResult {
    Eigen::VectorXd xs, ys, psis, kappas, vs, rs, ts;
  };
  std::optional<SmoothPathResult> generate_smooth_path_();

  std_msgs::msg::Float64MultiArray build_profile_msg_(
      const Eigen::VectorXd& vs,
      const Eigen::VectorXd& kappas,
      const Eigen::VectorXd& rs,
      const Eigen::VectorXd& ts,
      const builtin_interfaces::msg::Time& stamp);

  // ── 航点管理 ────────────────────────────────────────
  WaypointManager wp_manager_;

  // ── 当前位姿 ────────────────────────────────────────
  double x_   = 0.0;
  double y_   = 0.0;
  double psi_ = 0.0;
  double u_   = 0.0;  // 当前纵向速度

  // ── 配置参数 ────────────────────────────────────────
  double      update_rate_       = 1.0;
  double      path_resolution_   = 0.5;
  double      turn_radius_       = 5.0;
  std::string odom_topic_;
  std::string path_topic_;
  std::string profile_topic_;
  std::string dynamic_wp_topic_;
  double      default_wp_radius_ = 2.0;

  // TOPP 速度剖面约束
  double u_max_         = 2.0;
  double r_max_         = 0.5;
  double lat_accel_max_ = 1.0;
  double accel_max_     = 0.5;
  double decel_max_     = 0.5;
  double v_end_         = 0.0;
  double v_min_         = 0.2;

  // 可选最小曲率精修
  bool   enable_curv_opt_       = false;
  int    curv_opt_max_iter_     = 40;
  double curv_opt_corridor_     = 1.0;

  // ── ROS 通信 ────────────────────────────────────────
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr     dynamic_wp_sub_;
  rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr        path_pub_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr profile_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

}  // 命名空间 usv_planning
