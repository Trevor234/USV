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
 * @file mission_bridge_node.cpp
 * @brief Mission Planner 桥接节点实现。
 */

#include "usv_planning/mission_bridge_node.hpp"

#include <cmath>
#include <functional>
#include <set>
#include <sstream>

using namespace std::chrono_literals;

namespace usv_planning {

static const std::set<uint16_t> NAV_WAYPOINT_COMMANDS = {
    MAV_CMD_NAV_WAYPOINT, MAV_CMD_NAV_SPLINE_WAYPOINT};

MissionBridgeNode::MissionBridgeNode()
    : Node("mission_bridge_node") {
  // ── 参数声明与读取 ──
  this->declare_parameter("waypoints_topic",
                          std::string("/mavros/mission/waypoints"));//订阅的任务航点列表话题。
  this->declare_parameter("origin_topic",
                          std::string("/mavros/global_position/gp_origin"));//订阅的局部坐标原点
  this->declare_parameter("output_topic",
                          std::string("/usv/mission/waypoints_local"));//发布的局部坐标系下的航点列表
  this->declare_parameter("pull_service",
                          std::string("/mavros/mission/pull"));//主动从飞控拉取任务的服务名
  this->declare_parameter("auto_pull", true);
  this->declare_parameter("pull_interval", 2.0);
  this->declare_parameter("skip_home", true);
  this->declare_parameter("output_frame", std::string("map"));

  waypoints_topic_ = this->get_parameter("waypoints_topic").as_string();
  origin_topic_    = this->get_parameter("origin_topic").as_string();
  output_topic_    = this->get_parameter("output_topic").as_string();
  pull_service_    = this->get_parameter("pull_service").as_string();
  auto_pull_       = this->get_parameter("auto_pull").as_bool();
  pull_interval_   = std::max(0.5, this->get_parameter("pull_interval").as_double());
  skip_home_       = this->get_parameter("skip_home").as_bool();
  output_frame_    = this->get_parameter("output_frame").as_string();

  // ── QoS 配置（双订阅防兼容性问题） ──
  auto latched_qos = rclcpp::QoS(rclcpp::KeepLast(1))
      .reliable()
      .transient_local();
  auto volatile_qos = rclcpp::QoS(rclcpp::KeepLast(10))
      .reliable();

  // 航点订阅（latched + volatile 双保险）
  wp_sub_latched_ =
      this->create_subscription<mavros_msgs::msg::WaypointList>(
          waypoints_topic_,
          latched_qos,
          std::bind(&MissionBridgeNode::waypoints_callback_, this,
                    std::placeholders::_1));
  wp_sub_volatile_ =
      this->create_subscription<mavros_msgs::msg::WaypointList>(
          waypoints_topic_,
          volatile_qos,
          std::bind(&MissionBridgeNode::waypoints_callback_, this,
                    std::placeholders::_1));

  // 坐标原点订阅（latched + volatile 双保险）
  origin_sub_latched_ =
      this->create_subscription<geographic_msgs::msg::GeoPointStamped>(
          origin_topic_,
          latched_qos,
          std::bind(&MissionBridgeNode::origin_callback_, this,
                    std::placeholders::_1));
  origin_sub_volatile_ =
      this->create_subscription<geographic_msgs::msg::GeoPointStamped>(
          origin_topic_,
          volatile_qos,
          std::bind(&MissionBridgeNode::origin_callback_, this,
                    std::placeholders::_1));

  // 发布者
  path_pub_ = this->create_publisher<nav_msgs::msg::Path>(output_topic_, 10);

  // 主动拉取定时器
  if (auto_pull_) {
    pull_client_ =
        this->create_client<mavros_msgs::srv::WaypointPull>(pull_service_);
    pull_timer_ = this->create_wall_timer(
        std::chrono::duration<double>(pull_interval_),
        std::bind(&MissionBridgeNode::pull_mission_, this));
  }

  RCLCPP_INFO(this->get_logger(),
              "Mission bridge started | waypoints=%s | origin=%s | "
              "output=%s | auto_pull=%s",
              waypoints_topic_.c_str(), origin_topic_.c_str(),
              output_topic_.c_str(), auto_pull_ ? "true" : "false");
}

// ── 原点回调 ─────────────────────────────────────────────
void MissionBridgeNode::origin_callback_(
    const geographic_msgs::msg::GeoPointStamped::SharedPtr msg) {
  std::pair<double, double> new_origin{msg->position.latitude,
                                        msg->position.longitude};
  if (!origin_.has_value() || origin_.value() != new_origin) {
    origin_ = new_origin;
    RCLCPP_INFO(this->get_logger(), "GP origin set: lat=%.7f, lon=%.7f",
                new_origin.first, new_origin.second);
    if (last_waypoints_) {
      republish_();
    }
  }
}

// ── 航点回调（去重） ─────────────────────────────────────
void MissionBridgeNode::waypoints_callback_(
    const mavros_msgs::msg::WaypointList::SharedPtr msg) {
  auto sig = waypoint_signature_(*msg);
  if (last_signature_.has_value() && last_signature_.value() == sig) {
    return;
  }
  last_signature_ = sig;
  last_waypoints_ = msg;
  RCLCPP_INFO(this->get_logger(),
              "收到 MAVROS mission 航点列表: %zu 项", msg->waypoints.size());
  republish_();
}

// ── 航点签名 ─────────────────────────────────────────────
std::pair<uint16_t, MissionBridgeNode::WaypointSignature>
MissionBridgeNode::waypoint_signature_(
    const mavros_msgs::msg::WaypointList& msg) const {
  WaypointSignature sig;
  for (const auto& wp : msg.waypoints) {
    sig.emplace_back(
        wp.frame, wp.command, wp.is_current, wp.autocontinue,
        wp.param1, wp.param2, wp.param3, wp.param4,
        wp.x_lat, wp.y_long, wp.z_alt);
  }
  return {msg.current_seq, std::move(sig)};
}

// ── 主动拉取任务 ─────────────────────────────────────────
void MissionBridgeNode::pull_mission_() {
  if (!pull_client_ || pull_in_progress_) return;
  if (!pull_client_->service_is_ready()) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "等待 MAVROS mission pull 服务: %s",
                         pull_service_.c_str());
    return;
  }
  pull_in_progress_ = true;
  auto req = std::make_shared<mavros_msgs::srv::WaypointPull::Request>();
  auto future = pull_client_->async_send_request(
      req,
      std::bind(&MissionBridgeNode::pull_done_callback_, this,
                std::placeholders::_1));
}

void MissionBridgeNode::pull_done_callback_(
    rclcpp::Client<mavros_msgs::srv::WaypointPull>::SharedFuture future) {
  pull_in_progress_ = false;
  try {
    auto response = future.get();
    if (!response->success) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "MAVROS mission pull 返回失败");
      return;
    }
    int received = static_cast<int>(response->wp_received);
    if (!last_pull_count_.has_value() || last_pull_count_.value() != received) {
      last_pull_count_ = received;
      RCLCPP_INFO(this->get_logger(),
                  "MAVROS mission pull 成功: %d 项", received);
    }
  } catch (const std::exception& e) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "拉取 MAVROS mission 航点失败: %s", e.what());
  }
}

// ── 坐标转换并发布 ───────────────────────────────────────
void MissionBridgeNode::republish_() {
  if (!last_waypoints_) return;

  if (!origin_.has_value()) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "收到 %zu 个航点,但 gp_origin 尚未发布,跳过转换",
                         last_waypoints_->waypoints.size());
    return;
  }

  auto path = nav_msgs::msg::Path();
  path.header.stamp = this->get_clock()->now();
  path.header.frame_id = output_frame_;

  auto [lat0, lon0] = origin_.value();
  double cos_lat0 = std::cos(lat0 * M_PI / 180.0);

  int skipped = 0;
  for (size_t i = 0; i < last_waypoints_->waypoints.size(); ++i) {
    const auto& wp = last_waypoints_->waypoints[i];
    if (NAV_WAYPOINT_COMMANDS.find(wp.command) == NAV_WAYPOINT_COMMANDS.end()) {
      skipped++;
      continue;
    }
    if (skip_home_ && i == 0) {
      skipped++;
      continue;
    }

    // 经纬度有效性门禁: NaN/Inf 或未初始化的 (0,0) 航点会被转换成
    // ~10^7 m 外的 ENU 点, MPC 就近投影后参考指向错误方向、全速开船。
    if (!std::isfinite(wp.x_lat) || !std::isfinite(wp.y_long) ||
        (std::fabs(wp.x_lat) < 1e-6 && std::fabs(wp.y_long) < 1e-6)) {
      skipped++;
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "航点 #%zu 经纬度无效 (lat=%f, lon=%f)，已跳过",
                           i, wp.x_lat, wp.y_long);
      continue;
    }

    // 经纬度 -> ENU 平面坐标 (m)
    double dE = (wp.y_long - lon0) * (M_PI / 180.0) * EARTH_RADIUS_M * cos_lat0;
    double dN = (wp.x_lat - lat0)  * (M_PI / 180.0) * EARTH_RADIUS_M;

    geometry_msgs::msg::PoseStamped pose;
    pose.header = path.header;
    pose.pose.position.x = dE;
    pose.pose.position.y = dN;
    pose.pose.position.z = 0.0;
    pose.pose.orientation.w = 1.0;
    path.poses.push_back(pose);
  }

  path_pub_->publish(path);

  if (!path.poses.empty()) {
    RCLCPP_INFO(this->get_logger(),
                "已发布 %zu 个本地航点(跳过 %d 个非导航/HOME 项)",
                path.poses.size(), skipped);
  } else {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "Mission Planner 无有效导航航点，已发布空航点列表（控制器将进入 STANDBY）"
                         "(跳过 %d 项)", skipped);
  }
}

}  // 命名空间 usv_planning
