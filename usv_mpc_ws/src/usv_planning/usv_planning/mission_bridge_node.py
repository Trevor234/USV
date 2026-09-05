"""Mission Planner 桥接节点。

订阅 MAVROS 的任务航点 (lat/lon) 与本地坐标原点 (gp_origin),将航点
转换为本地 ENU 坐标后以 nav_msgs/Path 形式重新发布,供 path_planner_node
作为动态航点源使用。

数据流:
  Mission Planner --UDP--> MAVROS (waypoint plugin)
        -> /mavros/mission/pull (mavros_msgs/WaypointPull)
        -> /mavros/mission/waypoints (mavros_msgs/WaypointList, lat/lon)
        -> /mavros/global_position/gp_origin (geographic_msgs/GeoPointStamped)
        -> mission_bridge_node (本节点)
        -> /usv/mission/waypoints_local (nav_msgs/Path, frame_id="map")
"""

import math
from typing import Optional, Tuple

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

from geographic_msgs.msg import GeoPointStamped
from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import WaypointList
from mavros_msgs.srv import WaypointPull
from nav_msgs.msg import Path as NavPath


EARTH_RADIUS_M = 6378137.0

MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_SPLINE_WAYPOINT = 82
NAV_WAYPOINT_COMMANDS = {MAV_CMD_NAV_WAYPOINT, MAV_CMD_NAV_SPLINE_WAYPOINT}


class MissionBridgeNode(Node):
    """将 MAVROS 任务航点 (GPS) 桥接为本地 ENU NavPath。"""

    def __init__(self):
        super().__init__("mission_bridge_node")

        self.declare_parameter("waypoints_topic", "/mavros/mission/waypoints")
        self.declare_parameter("origin_topic", "/mavros/global_position/gp_origin")
        self.declare_parameter("output_topic", "/usv/mission/waypoints_local")
        self.declare_parameter("pull_service", "/mavros/mission/pull")
        self.declare_parameter("auto_pull", True)
        self.declare_parameter("pull_interval", 2.0)
        self.declare_parameter("skip_home", True)
        self.declare_parameter("output_frame", "map")

        self._waypoints_topic = self.get_parameter("waypoints_topic").value
        self._origin_topic = self.get_parameter("origin_topic").value
        self._output_topic = self.get_parameter("output_topic").value
        self._pull_service = self.get_parameter("pull_service").value
        self._auto_pull = bool(self.get_parameter("auto_pull").value)
        self._pull_interval = max(0.5, float(self.get_parameter("pull_interval").value))
        self._skip_home = bool(self.get_parameter("skip_home").value)
        self._output_frame = self.get_parameter("output_frame").value

        self._origin: Optional[Tuple[float, float]] = None
        self._last_waypoints: Optional[WaypointList] = None
        self._last_waypoint_signature: Optional[Tuple] = None
        self._pull_in_progress = False
        self._last_pull_count: Optional[int] = None

        latched_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
        )
        volatile_qos = QoSProfile(
            depth=10,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE,
            history=QoSHistoryPolicy.KEEP_LAST,
        )

        self._wp_sub_latched = self.create_subscription(
            WaypointList, self._waypoints_topic, self._waypoints_callback, latched_qos
        )
        self._wp_sub_volatile = self.create_subscription(
            WaypointList, self._waypoints_topic, self._waypoints_callback, volatile_qos
        )
        self._origin_sub_latched = self.create_subscription(
            GeoPointStamped, self._origin_topic, self._origin_callback, latched_qos
        )
        self._origin_sub_volatile = self.create_subscription(
            GeoPointStamped, self._origin_topic, self._origin_callback, volatile_qos
        )
        self._path_pub = self.create_publisher(NavPath, self._output_topic, 10)

        self._pull_client = None
        self._pull_timer = None
        if self._auto_pull:
            self._pull_client = self.create_client(WaypointPull, self._pull_service)
            self._pull_timer = self.create_timer(self._pull_interval, self._pull_mission)

        self.get_logger().info(
            f"Mission bridge started | waypoints={self._waypoints_topic} | "
            f"origin={self._origin_topic} | output={self._output_topic} | "
            f"auto_pull={self._auto_pull}"
        )

    def _origin_callback(self, msg: GeoPointStamped):
        new_origin = (msg.position.latitude, msg.position.longitude)
        if self._origin is None or self._origin != new_origin:
            self._origin = new_origin
            self.get_logger().info(
                f"GP origin set: lat={new_origin[0]:.7f}, lon={new_origin[1]:.7f}"
            )
            if self._last_waypoints is not None:
                self._republish()

    def _waypoints_callback(self, msg: WaypointList):
        signature = self._waypoint_signature(msg)
        if signature == self._last_waypoint_signature:
            return
        self._last_waypoint_signature = signature
        self._last_waypoints = msg
        self.get_logger().info(f"收到 MAVROS mission 航点列表: {len(msg.waypoints)} 项")
        self._republish()

    def _waypoint_signature(self, msg: WaypointList) -> Tuple:
        return (
            msg.current_seq,
            tuple(
                (
                    wp.frame,
                    wp.command,
                    wp.is_current,
                    wp.autocontinue,
                    wp.param1,
                    wp.param2,
                    wp.param3,
                    wp.param4,
                    wp.x_lat,
                    wp.y_long,
                    wp.z_alt,
                )
                for wp in msg.waypoints
            ),
        )

    def _pull_mission(self):
        if self._pull_client is None or self._pull_in_progress:
            return
        if not self._pull_client.service_is_ready():
            self.get_logger().warning(
                f"等待 MAVROS mission pull 服务: {self._pull_service}",
                throttle_duration_sec=5.0,
            )
            return

        self._pull_in_progress = True
        future = self._pull_client.call_async(WaypointPull.Request())
        future.add_done_callback(self._pull_done_callback)

    def _pull_done_callback(self, future):
        self._pull_in_progress = False
        try:
            response = future.result()
        except Exception as exc:
            self.get_logger().warning(
                f"拉取 MAVROS mission 航点失败: {exc}",
                throttle_duration_sec=5.0,
            )
            return

        success = bool(getattr(response, "success", False))
        received = int(getattr(response, "wp_received", 0))
        if not success:
            self.get_logger().warning(
                "MAVROS mission pull 返回失败",
                throttle_duration_sec=5.0,
            )
            return

        if self._last_pull_count != received:
            self._last_pull_count = received
            self.get_logger().info(f"MAVROS mission pull 成功: {received} 项")

    def _republish(self):
        if self._last_waypoints is None:
            return

        if self._origin is None:
            self.get_logger().warning(
                f"收到 {len(self._last_waypoints.waypoints)} 个航点,但 gp_origin 尚未发布,跳过转换",
                throttle_duration_sec=5.0,
            )
            return

        path = NavPath()
        path.header.stamp = self.get_clock().now().to_msg()
        path.header.frame_id = self._output_frame

        lat0, lon0 = self._origin
        cos_lat0 = math.cos(math.radians(lat0))

        skipped = 0
        for i, wp in enumerate(self._last_waypoints.waypoints):
            if wp.command not in NAV_WAYPOINT_COMMANDS:
                skipped += 1
                continue
            if self._skip_home and i == 0:
                skipped += 1
                continue

            # 经纬度有效性门禁: NaN/Inf 或未初始化的 (0,0) 航点会被转换成
            # ~10^7 m 外的 ENU 点, MPC 就近投影后参考指向错误方向、全速开船。
            lat, lon = wp.x_lat, wp.y_long
            if not (math.isfinite(lat) and math.isfinite(lon)) or (
                abs(lat) < 1e-6 and abs(lon) < 1e-6
            ):
                skipped += 1
                self.get_logger().warning(
                    f"航点 #{i} 经纬度无效 (lat={lat}, lon={lon})，已跳过",
                    throttle_duration_sec=5.0,
                )
                continue

            dE = math.radians(lon - lon0) * EARTH_RADIUS_M * cos_lat0
            dN = math.radians(lat - lat0) * EARTH_RADIUS_M

            pose = PoseStamped()
            pose.header = path.header
            pose.pose.position.x = dE
            pose.pose.position.y = dN
            pose.pose.position.z = 0.0
            pose.pose.orientation.w = 1.0
            path.poses.append(pose)

        self._path_pub.publish(path)
        if path.poses:
            self.get_logger().info(
                f"已发布 {len(path.poses)} 个本地航点(跳过 {skipped} 个非导航/HOME 项)"
            )
        else:
            self.get_logger().warning(
                f"Mission Planner 无有效导航航点，已发布空航点列表以触发 HOLD(跳过 {skipped} 项)",
                throttle_duration_sec=5.0,
            )


def main(args=None):
    rclpy.init(args=args)
    node = MissionBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
