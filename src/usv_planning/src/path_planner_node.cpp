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
 * @file path_planner_node.cpp
 * @brief 路径规划 ROS 2 节点实现。
 */

#include "usv_planning/path_planner_node.hpp"

#include <algorithm>
#include <cmath>
#include <functional>
#include <optional>

#include <Eigen/Dense>
#include <rclcpp/qos.hpp>
#include <std_msgs/msg/multi_array_dimension.hpp>

#include "usv_planning/speed_profile.hpp"
#include "usv_planning/trajectory_optimizer.hpp"

using namespace std::chrono_literals;

namespace usv_planning {

PathPlannerNode::PathPlannerNode()
    : Node("path_planner_node") {
  declare_parameters_();
  load_config_();

  // ── 订阅者 ──
  odom_sub_ = this->create_subscription<nav_msgs::msg::Odometry>(
      odom_topic_, rclcpp::SensorDataQoS(),
      std::bind(&PathPlannerNode::odom_callback_, this,
                std::placeholders::_1));//

  dynamic_wp_sub_ = this->create_subscription<nav_msgs::msg::Path>(
      dynamic_wp_topic_, 10,
      std::bind(&PathPlannerNode::dynamic_waypoints_callback_, this,
                std::placeholders::_1));

  // ── 发布者 ──
  path_pub_    = this->create_publisher<nav_msgs::msg::Path>(path_topic_, 10);
  profile_pub_ = this->create_publisher<std_msgs::msg::Float64MultiArray>(
      profile_topic_, 10);

  // ── 定时器 ──
  timer_ = this->create_wall_timer(
      std::chrono::duration<double>(update_rate_),
      std::bind(&PathPlannerNode::publish_path_, this));

  RCLCPP_INFO(this->get_logger(),
              "Path Planner started | %zu waypoints | update_rate=%.1fs",
              wp_manager_.waypoints().size(), update_rate_);
}

void PathPlannerNode::declare_parameters_() {
  this->declare_parameter("update_rate", 1.0);
  this->declare_parameter("waypoints_file", std::string(""));
  this->declare_parameter("path_resolution", 0.5);
  this->declare_parameter("turn_radius", 4.0);
  this->declare_parameter("odom_topic",
                          std::string("/mavros/local_position/odom"));
  this->declare_parameter("path_topic", std::string("/path/reference"));
  this->declare_parameter("profile_topic",
                          std::string("/path/reference_profile"));
  this->declare_parameter("dynamic_waypoints_topic",
                          std::string("/usv/mission/waypoints_local"));
  this->declare_parameter("default_waypoint_radius", 2.0);
  this->declare_parameter("prepend_current_pose", true);

  // TOPP 速度剖面约束
  this->declare_parameter("u_max", 2.0);
  this->declare_parameter("r_max", 0.5);
  this->declare_parameter("lat_accel_max", 1.0);
  this->declare_parameter("accel_max", 0.5);
  this->declare_parameter("decel_max", 0.5);
  this->declare_parameter("v_end", 0.0);
  this->declare_parameter("v_min", 0.2);
  this->declare_parameter("v_start_min", 0.4);

  // 可选最小曲率精修
  this->declare_parameter("enable_curvature_opt", false);
  this->declare_parameter("curvature_opt_max_iter", 40);
  this->declare_parameter("curvature_opt_corridor", 1.0);
}

void PathPlannerNode::load_config_() {
  update_rate_       = this->get_parameter("update_rate").as_double();
  path_resolution_   = this->get_parameter("path_resolution").as_double();
  turn_radius_       = this->get_parameter("turn_radius").as_double();
  odom_topic_        = this->get_parameter("odom_topic").as_string();
  path_topic_        = this->get_parameter("path_topic").as_string();
  profile_topic_     = this->get_parameter("profile_topic").as_string();
  dynamic_wp_topic_     = this->get_parameter("dynamic_waypoints_topic").as_string();
  default_wp_radius_    = this->get_parameter("default_waypoint_radius").as_double();
  prepend_current_pose_ = this->get_parameter("prepend_current_pose").as_bool();

  u_max_         = this->get_parameter("u_max").as_double();
  r_max_         = this->get_parameter("r_max").as_double();
  lat_accel_max_ = this->get_parameter("lat_accel_max").as_double();
  accel_max_     = this->get_parameter("accel_max").as_double();
  decel_max_     = this->get_parameter("decel_max").as_double();
  v_end_         = this->get_parameter("v_end").as_double();
  v_min_         = this->get_parameter("v_min").as_double();
  v_start_min_   = this->get_parameter("v_start_min").as_double();
  if (u_max_ >= v_min_) {
    const double clamped = std::clamp(v_start_min_, v_min_, u_max_);
    if (clamped != v_start_min_) {
      RCLCPP_WARN(this->get_logger(),
                  "v_start_min=%.2f 超出 [v_min=%.2f, u_max=%.2f], 已钳位为 %.2f",
                  v_start_min_, v_min_, u_max_, clamped);
      v_start_min_ = clamped;
    }
  }
  enable_curv_opt_   = this->get_parameter("enable_curvature_opt").as_bool();
  curv_opt_max_iter_ = this->get_parameter("curvature_opt_max_iter").as_int();
  curv_opt_corridor_ = this->get_parameter("curvature_opt_corridor").as_double();
  wp_manager_.set_turn_radius(turn_radius_);
}

// ── 里程计回调 ───────────────────────────────────────────
void PathPlannerNode::odom_callback_(
    const nav_msgs::msg::Odometry::SharedPtr msg) {
  // NaN/Inf 门禁: GPS 未收敛/EKF 发散时里程计携带 NaN, 会卡死
  // update_progress (hypot(NaN,NaN)<radius 恒 false) 并污染路径
  const auto& p = msg->pose.pose.position;
  const auto& t = msg->twist.twist;
  if (!std::isfinite(p.x) || !std::isfinite(p.y) ||
      !std::isfinite(t.linear.x)) {
    return;
  }
  x_ = p.x;
  y_ = p.y;
  // 四元数 -> 偏航角
  auto& q = msg->pose.pose.orientation;
  double siny = 2.0 * (q.w * q.z + q.x * q.y);
  double cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z);
  psi_ = std::atan2(siny, cosy);
  u_ = t.linear.x;
  odom_received_ = true;
}

// ── 动态航点回调 ─────────────────────────────────────────
void PathPlannerNode::dynamic_waypoints_callback_(
    const nav_msgs::msg::Path::SharedPtr msg) {
  wp_manager_.clear();

  if (msg->poses.empty()) {
    publish_empty_path_();
    RCLCPP_INFO(this->get_logger(), "收到空航点列表，已发布空参考路径（控制器将进入 STANDBY）");
    return;
  }

  // NaN/Inf 门禁: 一个污染点会让 fillet/采样产生垃圾路径或 UB
  std::vector<Waypoint> valid_wps;
  valid_wps.reserve(msg->poses.size());
  size_t skipped = 0;
  for (const auto& pose : msg->poses) {
    const double x = pose.pose.position.x;
    const double y = pose.pose.position.y;
    if (!std::isfinite(x) || !std::isfinite(y)) {
      skipped++;
      continue;
    }
    Waypoint wp;
    wp.x = x;
    wp.y = y;
    wp.radius = default_wp_radius_;
    wp.heading = 0.0;
    valid_wps.push_back(wp);
  }
  if (skipped > 0) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "动态航点含 %zu 个 NaN/Inf 点，已丢弃", skipped);
  }
  if (valid_wps.empty()) {
    publish_empty_path_();
    return;
  }

  bool prepended = false;
  if (prepend_current_pose_ && odom_received_) {
    const double dist_to_first = std::hypot(valid_wps.front().x - x_,
                                            valid_wps.front().y - y_);
    if (dist_to_first > default_wp_radius_) {
      Waypoint anchor;
      anchor.x = x_;
      anchor.y = y_;
      anchor.radius = default_wp_radius_;
      anchor.heading = psi_;
      wp_manager_.add_waypoint(anchor);
      prepended = true;
    }
  }
  for (const auto& wp : valid_wps) {
    wp_manager_.add_waypoint(wp);
  }

  RCLCPP_INFO(this->get_logger(),
              "Loaded %zu waypoints from mission bridge%s",
              valid_wps.size(), prepended ? " (已插入当前船位起始引导点)" : "");
}

// ── 发布空路径 ───────────────────────────────────────────
void PathPlannerNode::publish_empty_path_() {
  auto stamp = this->get_clock()->now();
  nav_msgs::msg::Path path_msg;
  path_msg.header.stamp = stamp;
  path_msg.header.frame_id = "map";
  path_pub_->publish(path_msg);
  profile_pub_->publish(std_msgs::msg::Float64MultiArray());
}

// ── 周期性路径发布 ───────────────────────────────────────
void PathPlannerNode::publish_path_() {
  wp_manager_.update_progress(x_, y_);

  if (wp_manager_.mission_complete()) {
    publish_empty_path_();
    return;
  }

  if (wp_manager_.waypoints().size() < 2) {
    publish_empty_path_();
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "等待 Mission Planner 提供至少 2 个有效航点");
    return;
  }

  auto result = generate_smooth_path_();
  if (!result.has_value()) {
    publish_empty_path_();
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "未能生成有效参考路径，已发布空参考路径");
    return;
  }

  auto& [xs, ys, psis, kappas, vs, rs, ts] = result.value();
  auto stamp = this->get_clock()->now();

  // 1) 参考路径 (NavPath)
  nav_msgs::msg::Path path_msg;
  path_msg.header.stamp = stamp;
  path_msg.header.frame_id = "map";
  const int n = static_cast<int>(xs.size());
  path_msg.poses.reserve(n);
  for (int i = 0; i < n; ++i) {
    geometry_msgs::msg::PoseStamped pose;
    pose.header = path_msg.header;
    pose.pose.position.x = xs(i);
    pose.pose.position.y = ys(i);
    pose.pose.position.z = 0.0;
    double psi = psis(i);
    pose.pose.orientation.z = std::sin(psi / 2.0);
    pose.pose.orientation.w = std::cos(psi / 2.0);
    path_msg.poses.push_back(pose);
  }
  path_pub_->publish(path_msg);

  // 2) 速度剖面 (Profile)
  profile_pub_->publish(build_profile_msg_(vs, kappas, rs, ts, stamp));
}

// ── 速度/曲率剖面消息构建 ────────────────────────────────
std_msgs::msg::Float64MultiArray PathPlannerNode::build_profile_msg_(
    const Eigen::VectorXd& vs,
    const Eigen::VectorXd& kappas,
    const Eigen::VectorXd& rs,
    const Eigen::VectorXd& ts,
    const builtin_interfaces::msg::Time& stamp) {
  const int m = static_cast<int>(vs.size());
  std_msgs::msg::Float64MultiArray msg;

  // 数组布局维度 layout dim
  std_msgs::msg::MultiArrayDimension d0, d1, d2, d3;
  d0.label = "points";          d0.size = m; d0.stride = m * 4;
  d1.label = "v_kappa_r_t";    d1.size = 4; d1.stride = 4;
  d2.label = "stamp_sec:" + std::to_string(stamp.sec);
  d2.size = 0; d2.stride = 0;
  d3.label = "stamp_nanosec:" + std::to_string(stamp.nanosec);
  d3.size = 0; d3.stride = 0;
  msg.layout.dim = {d0, d1, d2, d3};

  msg.data.reserve(m * 4);
  for (int i = 0; i < m; ++i) {
    msg.data.push_back(vs(i));
    msg.data.push_back(kappas(i));
    msg.data.push_back(rs(i));
    msg.data.push_back(ts(i));
  }
  return msg;
}

// ── 平滑路径生成（几何 + 速度剖面） ─────────────────────
std::optional<PathPlannerNode::SmoothPathResult>
PathPlannerNode::generate_smooth_path_() {
  const auto& wps = wp_manager_.waypoints();
  if (wps.size() < 2) return std::nullopt;

  // 提取航点坐标
  std::vector<std::pair<double, double>> waypoints_xy;
  waypoints_xy.reserve(wps.size());
  for (const auto& w : wps) {
    waypoints_xy.emplace_back(w.x, w.y);
  }

  // 几何层：圆弧倒角
  auto fillet = fillet_path(waypoints_xy, turn_radius_, path_resolution_);
  for (const auto& w : fillet.warnings) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "%s", w.c_str());
  }
  if (fillet.xs.size() < 2) return std::nullopt;

  auto xs     = fillet.xs;
  auto ys     = fillet.ys;
  auto psis   = fillet.psis;
  auto kappas = fillet.kappas;
  auto s      = fillet.s;

  // 可选：最小曲率精修（暂不实现 CasADi NLP，保留回退逻辑）
  if (enable_curv_opt_) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "最小曲率精修尚未实现，回退 fillet 结果");
  }

  // 速度层：TOPP 时间最优速度剖面 (v_start_min 破除零初速与死区之间的 1Hz 重规划死锁)
  const double v_start_eff = std::min(
      u_max_, std::max({v_start_min_, v_min_, std::max(0.0, u_)}));
  auto profile = compute_profile(
      kappas, s, u_max_, r_max_, lat_accel_max_,
      accel_max_, decel_max_,
      v_start_eff, v_end_, v_min_);

  return SmoothPathResult{
      std::move(xs), std::move(ys), std::move(psis), std::move(kappas),
      std::move(profile.vs), std::move(profile.rs), std::move(profile.ts)};
}

}  // 命名空间 usv_planning
