"""路径规划 ROS 2 节点。

根据航点生成平滑参考路径，并以 NavPath 消息形式发布给 MPC 控制器。
"""

import math
import time
from typing import List, Tuple

import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.qos import qos_profile_sensor_data
import yaml
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry, Path as NavPath
from rclpy.node import Node

from .dubins_path import plan_dubins, DubinsPath
from .waypoint_manager import WaypointManager, Waypoint


class PathPlannerNode(Node):
    """根据航点生成供 MPC 跟踪的参考路径。"""

    def __init__(self):
        super().__init__("path_planner_node")

        self._declare_parameters()
        self._load_config()

        self._wp_manager = WaypointManager()
        self._load_waypoints()

        # 当前位姿跟踪
        self._x = 0.0
        self._y = 0.0
        self._psi = 0.0

        # 订阅者
        self._odom_sub = self.create_subscription(
            Odometry, self._odom_topic, self._odom_callback, qos_profile_sensor_data
        )
        self._dynamic_wp_sub = self.create_subscription(
            NavPath, self._dynamic_wp_topic, self._dynamic_waypoints_callback, 10
        )

        # 发布者
        self._path_pub = self.create_publisher(NavPath, self._path_topic, 10)

        # 定时器用于周期性更新路径
        self._timer = self.create_timer(self._update_rate, self._publish_path)

        self._last_update = 0.0
        self.get_logger().info(
            f"Path Planner started | {len(self._wp_manager.waypoints)} waypoints | "
            f"update_rate={self._update_rate}s"
        )

    def _declare_parameters(self):
        self.declare_parameter("update_rate", 1.0)
        self.declare_parameter("waypoints_file", "")
        self.declare_parameter("path_resolution", 0.5)  # 路径点间距，单位 m
        self.declare_parameter("lookahead_distance", 50.0)  # 向前发布的路径长度，单位 m
        self.declare_parameter("turn_radius", 5.0)  # Dubins 最小转弯半径
        self.declare_parameter("cruise_speed", 1.0)
        self.declare_parameter("odom_topic", "/mavros/mavros/odom")
        self.declare_parameter("path_topic", "/path/reference")
        self.declare_parameter("dynamic_waypoints_topic", "/usv/mission/waypoints_local")
        self.declare_parameter("default_waypoint_radius", 2.0)

    def _load_config(self):
        self._update_rate = self.get_parameter("update_rate").value
        self._path_resolution = self.get_parameter("path_resolution").value
        self._lookahead = self.get_parameter("lookahead_distance").value
        self._turn_radius = self.get_parameter("turn_radius").value
        self._cruise_speed = self.get_parameter("cruise_speed").value
        self._odom_topic = self.get_parameter("odom_topic").value
        self._path_topic = self.get_parameter("path_topic").value
        self._dynamic_wp_topic = self.get_parameter("dynamic_waypoints_topic").value
        self._default_wp_radius = self.get_parameter("default_waypoint_radius").value

    def _load_waypoints(self):
        wp_file = self.get_parameter("waypoints_file").value
        if wp_file and wp_file.strip():
            try:
                with open(wp_file, "r") as f:
                    config = yaml.safe_load(f)
                self._wp_manager.load_from_yaml(config)
                self.get_logger().info(f"Loaded {len(self._wp_manager.waypoints)} waypoints from {wp_file}")
            except Exception as e:
                self._wp_manager.clear()
                self.get_logger().error(f"Failed to load waypoints: {e}")
        else:
            self.get_logger().info("未配置本地航点文件，等待 Mission Planner 航点")

    def _odom_callback(self, msg: Odometry):
        self._x = msg.pose.pose.position.x
        self._y = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        # 将四元数 (x,y,z,w) 转换为偏航角 yaw
        siny = 2.0 * (q.w * q.z + q.x * q.y)
        cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        self._psi = math.atan2(siny, cosy)

    def _publish_empty_path(self):
        msg = NavPath()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "map"
        self._path_pub.publish(msg)

    def _dynamic_waypoints_callback(self, msg: NavPath):
        """使用动态 Path 消息替换 WaypointManager 中的航点。

        动态航点只表达位置，不强制每个航点处的航向角；这样首轮仿真
        使用线性插值路径，避免 Dubins 曲线在短航段/急转角处生成绕圈。
        空 Path 会清空航点管理器。
        """
        self._wp_manager.clear()

        pts = [(p.pose.position.x, p.pose.position.y) for p in msg.poses]
        if not pts:
            self._publish_empty_path()
            self.get_logger().info("收到空航点列表，已发布空参考路径以触发 HOLD")
            return

        for x, y in pts:
            self._wp_manager.add_waypoint(Waypoint(
                x=x, y=y, radius=self._default_wp_radius, heading=0.0
            ))

        self.get_logger().info(
            f"Loaded {len(pts)} waypoints from mission bridge"
        )

    def _publish_path(self):
        wps = self._wp_manager.waypoints

        # 更新航点进度
        self._wp_manager.update_progress(self._x, self._y)

        if self._wp_manager.mission_complete:
            self._publish_empty_path()
            self.get_logger().info_once("任务完成，已发布空参考路径")
            return

        if len(wps) < 2:
            self._publish_empty_path()
            self.get_logger().warning(
                "等待 Mission Planner 提供至少 2 个有效航点",
                throttle_duration_sec=5.0,
            )
            return

        # 生成平滑路径
        path_points = self._generate_smooth_path()

        if not path_points:
            self._publish_empty_path()
            self.get_logger().warning(
                "未能生成有效参考路径，已发布空参考路径",
                throttle_duration_sec=5.0,
            )
            return

        # 构建 NavPath 消息
        msg = NavPath()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "map"

        for pt in path_points:
            pose = PoseStamped()
            pose.header = msg.header
            pose.pose.position.x = pt[0]
            pose.pose.position.y = pt[1]
            pose.pose.position.z = 0.0
            psi = pt[2]
            pose.pose.orientation.z = math.sin(psi / 2)
            pose.pose.orientation.w = math.cos(psi / 2)
            msg.poses.append(pose)

        self._path_pub.publish(msg)

    def _generate_smooth_path(self) -> List[Tuple[float, float, float]]:
        """通过所有活动航点生成平滑路径。

        默认使用带航向角平滑的线性插值；相邻线段急转弯时使用 Dubins 曲线。
        """
        wps = self._wp_manager.waypoints
        if len(wps) < 2:
            return []

        all_points: List[Tuple[float, float, float]] = []

        for i in range(len(wps) - 1):
            start = (wps[i].x, wps[i].y, wps[i].heading)
            end = (wps[i + 1].x, wps[i + 1].y, wps[i + 1].heading)

            # 若存在航向角约束，则优先使用 Dubins 曲线
            if wps[i].heading != 0.0 or wps[i + 1].heading != 0.0:
                dubins_path = plan_dubins(start, end, self._turn_radius)
                if dubins_path is not None and dubins_path.total_length < 500:
                    sampled = dubins_path.sample(
                        start[0], start[1], start[2],
                        self._turn_radius, self._path_resolution
                    )
                    if i > 0:
                        sampled = sampled[1:]  # 避免重复点
                    all_points.extend(sampled)
                    continue

            # 退化方案：线性插值
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            seg_len = math.hypot(dx, dy)
            n_pts = max(2, int(seg_len / self._path_resolution))
            heading = math.atan2(dy, dx)
            for j in range(n_pts):
                if i == 0 or j > 0:
                    t = j / (n_pts - 1) if n_pts > 1 else 0
                    x = start[0] + t * dx
                    y = start[1] + t * dy
                    all_points.append((x, y, heading))

        return all_points


def main(args=None):
    rclpy.init(args=args)
    node = PathPlannerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
