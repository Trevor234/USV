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
 * @file mission_bridge_node.hpp
 * @brief Mission Planner 桥接 ROS 2 节点（C++ 版本）。
 *
 * 订阅 MAVROS 的任务航点 (lat/lon) 与本地坐标原点 (gp_origin)，将航点
 * 转换为本地 ENU 坐标后以 nav_msgs/Path 形式重新发布。
 *
 * 对应 Python 版本: usv_planning/mission_bridge_node.py
 */

#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <geographic_msgs/msg/geo_point_stamped.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <mavros_msgs/msg/waypoint_list.hpp>
#include <mavros_msgs/srv/waypoint_pull.hpp>
#include <nav_msgs/msg/path.hpp>

namespace usv_planning
{

/// 地球半径 (m)
constexpr double EARTH_RADIUS_M = 6378137.0;

/// MAVLink 导航命令 ID
constexpr uint16_t MAV_CMD_NAV_WAYPOINT = 16;
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
    const mavros_msgs::msg::WaypointList & msg) const;

  // ── 参数 ────────────────────────────────────────────
  std::string waypoints_topic_;
  std::string origin_topic_;
  std::string output_topic_;
  std::string pull_service_;
  bool        auto_pull_ = true;
  double      pull_interval_ = 2.0;
  bool        skip_home_ = true;
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

}  // namespace usv_planning
