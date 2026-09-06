"""路径规划 ROS 2 节点。

根据航点生成平滑参考路径，并以 NavPath 消息形式发布给 MPC 控制器。
"""

import math
from typing import List, Tuple

import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.qos import qos_profile_sensor_data
import yaml
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry, Path as NavPath
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray, MultiArrayDimension

from . import trajectory_optimizer, speed_profile
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
        self._u = 0.0  # 当前纵向速度（用作 TOPP 起点速度 v_start）

        # 订阅者
        self._odom_sub = self.create_subscription(
            Odometry, self._odom_topic, self._odom_callback, qos_profile_sensor_data
        )
        self._dynamic_wp_sub = self.create_subscription(
            NavPath, self._dynamic_wp_topic, self._dynamic_waypoints_callback, 10
        )

        # 发布者
        self._path_pub = self.create_publisher(NavPath, self._path_topic, 10)
        # 速度/曲率/时间剖面，与 /path/reference 逐点对应，供 MPC 构建动力学一致参考
        self._profile_pub = self.create_publisher(Float64MultiArray, self._profile_topic, 10)

        # 定时器用于周期性更新路径
        self._timer = self.create_timer(self._update_rate, self._publish_path)

        self.get_logger().info(
            f"Path Planner started | {len(self._wp_manager.waypoints)} waypoints | "
            f"update_rate={self._update_rate}s"
        )

    def _declare_parameters(self):
        self.declare_parameter("update_rate", 1.0)
        self.declare_parameter("waypoints_file", "")
        self.declare_parameter("path_resolution", 0.5)  # 路径点间距，单位 m
        self.declare_parameter("turn_radius", 5.0)  # 最小转弯半径（圆弧倒角半径）
        self.declare_parameter("odom_topic", "/mavros/local_position/odom")
        self.declare_parameter("path_topic", "/path/reference")
        self.declare_parameter("profile_topic", "/path/reference_profile")
        self.declare_parameter("dynamic_waypoints_topic", "/usv/mission/waypoints_local")
        self.declare_parameter("default_waypoint_radius", 2.0)

        # --- 速度剖面 (TOPP) 约束 ---
        # 注意：规划可行域 ⊆ 控制可行域。本工作目录 MPC 为动力学 NMPC (推力域约束
        # dynamic.T_max)，规划侧 u_max 是 TOPP 巡航速度上限，需保证该速度下所需
        # 推力不超过 T_max，否则参考会超出控制器能跟踪的范围。
        self.declare_parameter("u_max", 2.0)         # 最大巡航速度 (m/s)
        self.declare_parameter("r_max", 0.5)         # 最大转艏角速度 (rad/s)
        self.declare_parameter("lat_accel_max", 1.0)  # 最大侧向加速度 (m/s^2)
        self.declare_parameter("accel_max", 0.5)     # 最大纵向加速 (m/s^2)
        self.declare_parameter("decel_max", 0.5)     # 最大纵向减速 (m/s^2)
        self.declare_parameter("v_end", 0.0)         # 末端目标速度 (m/s)
        self.declare_parameter("v_min", 0.2)         # 最小速度下限，保证时间推进 (m/s)

        # --- 可选：最小曲率精修 NLP（默认关闭，保 1Hz 实时性）---
        self.declare_parameter("enable_curvature_opt", False)
        self.declare_parameter("curvature_opt_max_iter", 40)
        self.declare_parameter("curvature_opt_corridor", 1.0)  # 走廊半宽 (m)

    def _load_config(self):
        self._update_rate = self.get_parameter("update_rate").value
        self._path_resolution = self.get_parameter("path_resolution").value
        self._turn_radius = self.get_parameter("turn_radius").value
        self._odom_topic = self.get_parameter("odom_topic").value
        self._path_topic = self.get_parameter("path_topic").value
        self._profile_topic = self.get_parameter("profile_topic").value
        self._dynamic_wp_topic = self.get_parameter("dynamic_waypoints_topic").value
        self._default_wp_radius = self.get_parameter("default_waypoint_radius").value

        self._u_max = self.get_parameter("u_max").value
        self._r_max = self.get_parameter("r_max").value
        self._lat_accel_max = self.get_parameter("lat_accel_max").value
        self._accel_max = self.get_parameter("accel_max").value
        self._decel_max = self.get_parameter("decel_max").value
        self._v_end = self.get_parameter("v_end").value
        self._v_min = self.get_parameter("v_min").value
        self._enable_curv_opt = bool(self.get_parameter("enable_curvature_opt").value)
        self._curv_opt_max_iter = int(self.get_parameter("curvature_opt_max_iter").value)
        self._curv_opt_corridor = float(self.get_parameter("curvature_opt_corridor").value)

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
        self._u = msg.twist.twist.linear.x  # 机体纵向速度，供 TOPP 作 v_start

    def _publish_empty_path(self):
        stamp = self.get_clock().now().to_msg()
        msg = NavPath()
        msg.header.stamp = stamp
        msg.header.frame_id = "map"
        self._path_pub.publish(msg)
        # 同步发空剖面，避免 MPC 端残留过期 profile
        self._profile_pub.publish(Float64MultiArray())

    def _dynamic_waypoints_callback(self, msg: NavPath):
        """使用动态 Path 消息替换 WaypointManager 中的航点。

        动态航点只表达位置。航向由 fillet 圆弧倒角从相邻航段方向自动推导，
        因此不再需要像旧版那样强制 heading=0 来规避 Dubins 短航段绕圈。
        空 Path 会清空航点管理器。
        """
        self._wp_manager.clear()

        # NaN/Inf 门禁: 一个污染点会让 fillet/TOPP 产生垃圾路径或抛异常
        pts = []
        skipped = 0
        for p in msg.poses:
            x, y = p.pose.position.x, p.pose.position.y
            if math.isfinite(x) and math.isfinite(y):
                pts.append((x, y))
            else:
                skipped += 1
        if skipped:
            self.get_logger().warning(
                f"动态航点含 {skipped} 个 NaN/Inf 点，已丢弃",
                throttle_duration_sec=5.0,
            )
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
        """周期性发布参考路径。

        本回调在 rclpy 定时器里运行, 任何未捕获异常都会传播出 spin() 杀死
        节点——规划器死亡意味着 /path/reference 停发, 只剩安全包的 path
        watchdog 兜底。这里统一兜底: 记日志并发布空路径 (MPC 侧触发 HOLD),
        节点存活等待下一拍恢复。
        """
        try:
            self._publish_path_impl()
        except Exception as e:  # noqa: BLE001 - 兜底防止节点死亡
            self.get_logger().error(
                f"路径生成异常, 已发布空参考路径: {e}",
                throttle_duration_sec=5.0,
            )
            try:
                self._publish_empty_path()
            except Exception:
                pass

    def _publish_path_impl(self):
        wps = self._wp_manager.waypoints

        # 更新航点进度
        self._wp_manager.update_progress(self._x, self._y)

        if self._wp_manager.mission_complete:
            self._publish_empty_path()
            self.get_logger().info(
                "任务完成，已发布空参考路径", throttle_duration_sec=60.0
            )
            return

        if len(wps) < 2:
            self._publish_empty_path()
            self.get_logger().warning(
                "等待 Mission Planner 提供至少 2 个有效航点",
                throttle_duration_sec=5.0,
            )
            return

        # 生成平滑轨迹（几何 + 速度剖面）
        result = self._generate_smooth_path()
        if result is None:
            self._publish_empty_path()
            self.get_logger().warning(
                "未能生成有效参考路径，已发布空参考路径",
                throttle_duration_sec=5.0,
            )
            return

        xs, ys, psis, kappas, vs, rs, ts = result
        stamp = self.get_clock().now().to_msg()

        # 1) NavPath：位置 + 航向（航向 normalize 后写入四元数；MPC 代价对包角免疫）
        path_msg = NavPath()
        path_msg.header.stamp = stamp
        path_msg.header.frame_id = "map"
        for i in range(len(xs)):
            pose = PoseStamped()
            pose.header = path_msg.header
            pose.pose.position.x = float(xs[i])
            pose.pose.position.y = float(ys[i])
            pose.pose.position.z = 0.0
            psi = float(psis[i])
            pose.pose.orientation.z = math.sin(psi / 2.0)
            pose.pose.orientation.w = math.cos(psi / 2.0)
            path_msg.poses.append(pose)
        self._path_pub.publish(path_msg)

        # 2) Profile：[M,4] = (v, kappa, r, t)，逐点与 NavPath 对应（同周期发布）
        self._profile_pub.publish(self._build_profile_msg(vs, kappas, rs, ts, stamp))

    def _build_profile_msg(self, vs, kappas, rs, ts, stamp) -> Float64MultiArray:
        """构建逐点速度/曲率/转艏角速度/时间剖面消息（行主序 [M,4]）。

        Float64MultiArray 没有 header；为了把 profile 与同周期 NavPath
        可靠配对，在 layout.dim 末尾写入 path.header.stamp 的元数据。
        """
        m = len(vs)
        msg = Float64MultiArray()
        msg.layout.dim = [
            MultiArrayDimension(label="points", size=m, stride=m * 4),
            MultiArrayDimension(label="v_kappa_r_t", size=4, stride=4),
            MultiArrayDimension(label=f"stamp_sec:{stamp.sec}", size=0, stride=0),
            MultiArrayDimension(label=f"stamp_nanosec:{stamp.nanosec}", size=0, stride=0),
        ]
        data: List[float] = []
        for i in range(m):
            data.extend([float(vs[i]), float(kappas[i]), float(rs[i]), float(ts[i])])
        msg.data = data
        return msg

    def _generate_smooth_path(self):
        """生成通过所有航点的曲率可行平滑轨迹 + 时间最优速度剖面。

        Returns:
            (xs, ys, psis, kappas, vs, rs, ts) 七元组 numpy 数组；无效时返回 None。
        """
        wps = self._wp_manager.waypoints
        if len(wps) < 2:
            return None

        waypoints_xy = [(w.x, w.y) for w in wps]

        # 几何层：圆弧倒角，解析输出航向与曲率
        xs, ys, psis, kappas, s, warnings = trajectory_optimizer.fillet_path(
            waypoints_xy, self._turn_radius, self._path_resolution
        )
        for w in warnings:
            self.get_logger().warning(w, throttle_duration_sec=5.0)
        if len(xs) < 2:
            return None

        # 可选：最小曲率精修（默认关闭，失败/不可用回退 fillet）
        if self._enable_curv_opt:
            refined = trajectory_optimizer.refine_min_curvature(
                xs, ys, self._curv_opt_corridor, self._turn_radius,
                max_iter=self._curv_opt_max_iter,
            )
            if refined is not None:
                xs, ys = refined
                psis, kappas, s = trajectory_optimizer.recompute_geometry(xs, ys)
            else:
                self.get_logger().warning(
                    "最小曲率精修失败/不可用，回退 fillet 结果",
                    throttle_duration_sec=5.0,
                )

        # 速度层：TOPP 时间最优速度剖面。起点速度取当前实测纵向速度。
        vs, rs, ts = speed_profile.compute_profile(
            kappas, s,
            u_max=self._u_max, r_max=self._r_max, a_lat_max=self._lat_accel_max,
            a_acc=self._accel_max, a_dec=self._decel_max,
            v_start=max(0.0, self._u), v_end=self._v_end, v_min=self._v_min,
        )
        return xs, ys, psis, kappas, vs, rs, ts


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
