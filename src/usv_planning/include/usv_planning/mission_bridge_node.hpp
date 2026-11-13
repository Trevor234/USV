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
 * @file mission_bridge_node.hpp
 * @brief Mission Planner 桥接 ROS 2 节点。
 *
 * 订阅 MAVROS 的任务航点 (lat/lon) 与本地坐标原点 (gp_origin)，将航点
 * 转换为本地 ENU 坐标后以 nav_msgs/Path 形式重新发布。
 */

#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <tuple>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <geographic_msgs/msg/geo_point_stamped.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <mavros_msgs/msg/waypoint_list.hpp>
#include <mavros_msgs/srv/waypoint_pull.hpp>
#include <nav_msgs/msg/path.hpp>

namespace usv_planning {

/// 地球半径 (m)
constexpr double EARTH_RADIUS_M = 6378137.0;

/// MAVLink 导航命令 ID
constexpr uint16_t MAV_CMD_NAV_WAYPOINT        = 16;
constexpr uint16_t MAV_CMD_NAV_SPLINE_WAYPOINT = 82;

class MissionBridgeNode : public rclcpp::Node {
 public:
  MissionBridgeNode();

 private:
  // ── 回调 ────────────────────────────────────────────
  void origin_callback_(
      const geographic_msgs::msg::GeoPointStamped::SharedPtr msg);
  void waypoints_callback_(
      const mavros_msgs::msg::WaypointList::SharedPtr msg);
  void pull_mission_();
  void pull_done_callback_(
      rclcpp::Client<mavros_msgs::srv::WaypointPull>::SharedFuture future);
  void republish_();

  /// 航点签名（用于去重）。
  using WaypointSignature = std::vector<std::tuple<
      uint8_t, uint16_t, bool, bool,
      float, float, float, float,
      double, double, double>>;
  std::pair<uint16_t, WaypointSignature> waypoint_signature_(
      const mavros_msgs::msg::WaypointList& msg) const;

  // ── 参数 ────────────────────────────────────────────
  std::string waypoints_topic_;
  std::string origin_topic_;
  std::string output_topic_;
  std::string pull_service_;
  bool        auto_pull_    = true;
  double      pull_interval_ = 2.0;
  bool        skip_home_    = true;
  std::string output_frame_ = "map";

  // ── 内部状态 ────────────────────────────────────────
  std::optional<std::pair<double, double>> origin_;
  mavros_msgs::msg::WaypointList::SharedPtr last_waypoints_;
  std::optional<std::pair<uint16_t, WaypointSignature>> last_signature_;
  bool pull_in_progress_ = false;
  std::optional<int> last_pull_count_;

  // ── ROS 通信 ────────────────────────────────────────
  rclcpp::Subscription<mavros_msgs::msg::WaypointList>::SharedPtr wp_sub_latched_;
  rclcpp::Subscription<mavros_msgs::msg::WaypointList>::SharedPtr wp_sub_volatile_;
  rclcpp::Subscription<geographic_msgs::msg::GeoPointStamped>::SharedPtr origin_sub_latched_;
  rclcpp::Subscription<geographic_msgs::msg::GeoPointStamped>::SharedPtr origin_sub_volatile_;
  rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr path_pub_;
  rclcpp::Client<mavros_msgs::srv::WaypointPull>::SharedPtr pull_client_;
  rclcpp::TimerBase::SharedPtr pull_timer_;
};

}  // 命名空间 usv_planning
