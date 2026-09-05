"""适用于无人船 (USV) 的运动学 MPC 控制器 ROS 2 节点（方案 A）。

订阅话题（可通过 launch 参数覆盖）：
  /mavros/local_position/odom     — EKF 融合的位置与速度
  /mavros/imu/data                — IMU 角速度 r 仅用于 /mpc/status 遥测 (方案 A 状态为 [x,y,psi], 不进控制)
  /path/reference                 — 规划器给出的参考路径（x, y, psi）
  /path/reference_profile         — 规划器给出的速度剖面（v, kappa, r, t）

发布话题（可通过 launch 参数覆盖）：
  /mavros/setpoint_velocity/cmd_vel  — 速度设定值
  /mpc/predicted_trajectory          — 用于可视化的 MPC 预测轨迹
  /mpc/status                        — 求解器诊断信息

实机精简版：仅保留方案 A（运动学 MPC），单线程执行。参考构建优先按规划器
速度剖面（profile）做时间重采样，profile 缺失/不同步时退化为匀速弧长采样。
"""

import json
import math
import threading
import time
from enum import Enum

import numpy as np
import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import TwistStamped
from mavros_msgs.msg import State as MavrosState
from nav_msgs.msg import Odometry, Path as NavPath
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import Float64MultiArray, String

from .mpc_kinematic import KinematicMPC
from .utils import (
    normalize_angle,
    parse_profile_stamp,
    profile_sync_state,
    quaternion_to_yaw,
    sample_path_profile_at_time,
)


class ControlMode(Enum):
    IDLE = "idle"
    KINEMATIC = "kinematic"


class MpcControllerNode(Node):
    """适用于双推进器无人船 (USV) 的 ROS 2 MPC 控制器节点（方案 A）。"""

    def __init__(self):
        super().__init__("mpc_controller_node")

        self._declare_parameters()
        self._load_config()

        # MPC 求解可能耗时数十~数百毫秒。MultiThreadedExecutor 配合此锁,让传感器
        # 回调在控制回调求解期间继续运行(只取短的状态/参考快照),避免 IMU/odom 堵塞。
        self._state_lock = threading.RLock()
        self._io_cb_group = ReentrantCallbackGroup()
        self._control_cb_group = MutuallyExclusiveCallbackGroup()

        self._init_mpc_solvers()
        self._init_state()
        self._init_pubsub()

        self.get_logger().info(
            f"运动学 MPC 控制器已启动 | 方案={self.scheme} | 模式={self.control_mode.value} "
            f"| dt={self.mpc_dt}s | N={self.horizon} | "
            f"后端={self.backend} (运动学)"
        )

        self._timer = self.create_timer(
            self.mpc_dt,
            self._control_loop,
            callback_group=self._control_cb_group,
        )

    def _declare_parameters(self):
        # 实机精简版固定方案 A；保留 scheme 参数仅用于状态上报与配置兼容。
        self.declare_parameter("scheme", "A")
        self.declare_parameter("control_mode", "kinematic")
        self.declare_parameter("mpc_dt", 0.2)
        self.declare_parameter("horizon", 20)
        self.declare_parameter("odom_topic", "/mavros/local_position/odom")
        self.declare_parameter("imu_topic", "/mavros/imu/data")
        self.declare_parameter("path_topic", "/path/reference")
        self.declare_parameter("profile_topic", "/path/reference_profile")
        self.declare_parameter("state_topic", "/mavros/state")
        self.declare_parameter("velocity_topic", "/mavros/setpoint_velocity/cmd_vel")
        self.declare_parameter("path_frame", "map")
        self.declare_parameter("body_frame", "base_link")
        self.declare_parameter("require_fcu_state", True)
        self.declare_parameter("publish_predicted", True)
        self.declare_parameter("max_solve_time_ms", 200.0)
        # 进入 HOLD（挂起）模式前允许的连续求解失败次数：停止发送过时的控制指令，
        # 并重置热启动，以便下一次尝试能够从头开始。应与
        # usv_safety/mode_manager_node.max_solver_failures 一致。
        self.declare_parameter("solver_hold_threshold", 5)
        # 飞控就绪判据：允许 MPC 输出指令的 FCU 模式白名单。
        # 运动学 MPC 通过 cmd_vel 控制,只在 GUIDED 下被 ArduPilot 接受。
        self.declare_parameter("allowed_fcu_modes", ["GUIDED"])
        # MAVROS 状态心跳超时(秒);超过则视为飞控失联,进入 STANDBY
        self.declare_parameter("state_timeout_s", 2.0)
        # 里程计超时(秒);0 关闭检查
        self.declare_parameter("odom_timeout_s", 1.0)

        # 运动学 MPC 参数
        self.declare_parameter("kinematic.Q", [10.0, 10.0, 50.0])
        self.declare_parameter("kinematic.R", [1.0, 1.0])
        self.declare_parameter("kinematic.Qf_scale", 10.0)
        self.declare_parameter("kinematic.u_max", 2.0)
        # profile 缺失/失同步时降级参考的前瞻速度 (m/s)。默认跟随 u_max
        # (历史行为); 弯道多的场景建议调低, 降级时参考推进更保守。
        self.declare_parameter("kinematic.fallback_speed", -1.0)
        self.declare_parameter("kinematic.u_min", 0.0)
        self.declare_parameter("kinematic.r_max", 0.5)
        self.declare_parameter("kinematic.du_max", 0.8)
        self.declare_parameter("kinematic.dr_max", 0.5)
        # 求解后端："ipopt"（CasADi/IPOPT，默认）或 "acados"（SQP_RTI，需先装 acados）。
        # 两后端共用同一 KinematicMPC 调用契约；见 docs/acados_migration.md。
        self.declare_parameter("kinematic.backend", "ipopt")

    def _load_config(self):
        self.scheme = self.get_parameter("scheme").value
        if self.scheme not in ("A",):
            # 精简版仅实现方案 A；忽略其它取值并按方案 A 运行。
            self.get_logger().warning(
                f"实机精简版仅支持方案 A，已忽略 scheme='{self.scheme}'，按方案 A 运行。"
            )
            self.scheme = "A"

        mode_str = self.get_parameter("control_mode").value
        try:
            self.control_mode = ControlMode(mode_str)
        except ValueError:
            self.control_mode = ControlMode.IDLE

        self.mpc_dt = self.get_parameter("mpc_dt").value
        self.horizon = self.get_parameter("horizon").value
        self.max_solve_time_ms = self.get_parameter("max_solve_time_ms").value
        self.require_fcu_state = bool(self.get_parameter("require_fcu_state").value)
        self.path_frame = str(self.get_parameter("path_frame").value)
        self.body_frame = str(self.get_parameter("body_frame").value)
        self.publish_predicted = self.get_parameter("publish_predicted").value
        self.solver_hold_threshold = int(self.get_parameter("solver_hold_threshold").value)
        allowed_modes = self.get_parameter("allowed_fcu_modes").value
        if isinstance(allowed_modes, str):
            allowed_modes = allowed_modes.strip().strip("[]")
            self.allowed_fcu_modes = [m.strip().strip("'\"") for m in allowed_modes.split(",") if m.strip()]
        else:
            self.allowed_fcu_modes = list(allowed_modes)
        self.state_timeout_s = float(self.get_parameter("state_timeout_s").value)
        self.odom_timeout_s = float(self.get_parameter("odom_timeout_s").value)

    def _init_mpc_solvers(self):
        backend = str(self.get_parameter("kinematic.backend").value).lower()
        mpc_kwargs = dict(
            dt=self.mpc_dt,
            N=self.horizon,
            Q_diag=tuple(self.get_parameter("kinematic.Q").value),
            R_diag=tuple(self.get_parameter("kinematic.R").value),
            Qf_scale=self.get_parameter("kinematic.Qf_scale").value,
            u_max=self.get_parameter("kinematic.u_max").value,
            u_min=self.get_parameter("kinematic.u_min").value,
            r_max=self.get_parameter("kinematic.r_max").value,
            du_max=self.get_parameter("kinematic.du_max").value,
            dr_max=self.get_parameter("kinematic.dr_max").value,
        )

        # backend 字段记录实际生效的求解后端,供启动日志与 /mpc/status 上报。
        # acados 不可用(import/codegen 失败)时自动回退 ipopt,与 B 的 fallback 语义一致。
        if backend == "acados":
            try:
                from .mpc_kinematic_acados import AcadosKinematicMPC
                self._mpc_kin = AcadosKinematicMPC(**mpc_kwargs)
                self.backend = "acados"
                self.get_logger().info("MPC 后端: acados (SQP_RTI)")
                return
            except Exception as exc:
                self.get_logger().error(
                    f"acados 后端初始化失败，回退到 IPOPT: {exc}"
                )

        self._mpc_kin = KinematicMPC(**mpc_kwargs)
        self.backend = "ipopt"
        self.get_logger().info("MPC 后端: CasADi/IPOPT")

    def _init_state(self):
        self._x = 0.0
        self._y = 0.0
        self._psi = 0.0
        self._u = 0.0
        self._v = 0.0
        self._r = 0.0
        self._odom_received = False
        self._imu_received = False
        self._path_received = False
        self._reference_path = []  # 每点 [x, y, psi]（位姿；速度/转艏角速度来自 profile）
        self._reference_path_stamp = None  # (sec, nanosec), 来自 NavPath.header.stamp
        self._ref_profile = None   # 每点 [v, kappa, r, t]，来自 /path/reference_profile
        self._ref_profile_stamp = None  # (sec, nanosec), 来自 Float64MultiArray.layout 元数据
        self._profile_synced = False
        self._profile_sync_reason = "no_profile"
        self._armed = False
        self._mode = "MANUAL"
        self._solver_fail_count = 0
        self._control_count = 0
        # 飞控就绪追踪：心跳/数据时间戳与上一周期的运行状态
        self._last_state_time = 0.0
        self._last_odom_time = 0.0
        # _prev_state: "" (启动)、"ACTIVE"、"STANDBY";用于检测状态切换沿
        self._prev_state = ""
        self._last_standby_reason = ""
        self._last_ref_debug = {}

    def _init_pubsub(self):
        # 订阅者
        odom_topic = self.get_parameter("odom_topic").value
        imu_topic = self.get_parameter("imu_topic").value
        path_topic = self.get_parameter("path_topic").value
        profile_topic = self.get_parameter("profile_topic").value
        state_topic = self.get_parameter("state_topic").value

        self._odom_sub = self.create_subscription(
            Odometry, odom_topic, self._odom_callback, qos_profile_sensor_data,
            callback_group=self._io_cb_group,
        )
        self._imu_sub = self.create_subscription(
            Imu, imu_topic, self._imu_callback, qos_profile_sensor_data,
            callback_group=self._io_cb_group,
        )
        self._path_sub = self.create_subscription(
            NavPath, path_topic, self._path_callback, 10,
            callback_group=self._io_cb_group,
        )
        self._profile_sub = self.create_subscription(
            Float64MultiArray, profile_topic, self._profile_callback, 10,
            callback_group=self._io_cb_group,
        )
        self._state_sub = self.create_subscription(
            MavrosState, state_topic, self._state_callback, 10,
            callback_group=self._io_cb_group,
        )

        # 发布者
        vel_topic = self.get_parameter("velocity_topic").value
        self._vel_pub = self.create_publisher(TwistStamped, vel_topic, 10)

        self._traj_pub = self.create_publisher(NavPath, "/mpc/predicted_trajectory", 10)
        self._status_pub = self.create_publisher(String, "/mpc/status", 10)

    # ---------- 回调函数 ----------

    @staticmethod
    def _stamp_tuple(stamp) -> tuple[int, int]:
        return int(stamp.sec), int(stamp.nanosec)

    @staticmethod
    def _parse_profile_stamp(layout) -> tuple[int, int] | None:
        return parse_profile_stamp(layout)

    @staticmethod
    def _profile_sync_state(path_len: int, profile_len, path_stamp, profile_stamp) -> tuple[bool, str]:
        return profile_sync_state(path_len, profile_len, path_stamp, profile_stamp)

    def _odom_callback(self, msg: Odometry):
        with self._state_lock:
            self._x = msg.pose.pose.position.x
            self._y = msg.pose.pose.position.y
            q = msg.pose.pose.orientation
            self._psi = quaternion_to_yaw(q.x, q.y, q.z, q.w)
            self._u = msg.twist.twist.linear.x
            self._v = msg.twist.twist.linear.y
            self._r = msg.twist.twist.angular.z
            self._odom_received = True
            self._last_odom_time = time.time()

    def _imu_callback(self, msg: Imu):
        # 直接陀螺仪角速度; 仅用于 status 遥测 (运动学 MPC 状态不含 r)
        with self._state_lock:
            self._r = msg.angular_velocity.z
            self._imu_received = True

    def _path_callback(self, msg: NavPath):
        reference_path = []
        for pose in msg.poses:
            x = pose.pose.position.x
            y = pose.pose.position.y
            q = pose.pose.orientation
            psi = quaternion_to_yaw(q.x, q.y, q.z, q.w)
            reference_path.append([x, y, psi])
        path_stamp = self._stamp_tuple(msg.header.stamp)
        with self._state_lock:
            self._reference_path = reference_path
            self._reference_path_stamp = path_stamp
            self._path_received = len(self._reference_path) > 0

    def _profile_callback(self, msg: Float64MultiArray):
        """接收逐点速度剖面 [M,4]=(v, kappa, r, t)，与 /path/reference 逐点对应。

        构建参考时按长度与 path 对齐（同周期同长度），不一致则回退匀速弧长采样
        （见 _build_reference）。空数组表示规划器清空了路径。
        """
        data = msg.data
        profile_stamp = self._parse_profile_stamp(msg.layout)
        if len(data) < 4 or (len(data) % 4) != 0:
            with self._state_lock:
                self._ref_profile = None
                self._ref_profile_stamp = profile_stamp
                self._profile_sync_reason = "empty_or_malformed_profile"
            return
        m = len(data) // 4
        ref_profile = [
            [data[4 * i], data[4 * i + 1], data[4 * i + 2], data[4 * i + 3]]
            for i in range(m)
        ]
        with self._state_lock:
            self._ref_profile = ref_profile
            self._ref_profile_stamp = profile_stamp

    def _state_callback(self, msg: MavrosState):
        with self._state_lock:
            self._armed = msg.armed
            self._mode = msg.mode
            self._last_state_time = time.time()

    # ---------- 控制循环 ----------

    def _can_solve(self) -> tuple:
        """检查 MPC 是否具备解算与下发指令的所有前置条件。

        返回 (ok, reason)。reason 为 STANDBY 状态机暴露给上层
        (mode_manager / GCS) 的具体原因码。
        """
        now = time.time()
        if not self._odom_received:
            return False, "no_odom"
        if self.odom_timeout_s > 0.0 and (now - self._last_odom_time) > self.odom_timeout_s:
            return False, "odom_timeout"
        if not self._path_received or len(self._reference_path) < 2:
            return False, "no_path"
        if self.require_fcu_state:
            if self._last_state_time == 0.0:
                return False, "no_state"
            if self.state_timeout_s > 0.0 and (now - self._last_state_time) > self.state_timeout_s:
                return False, "state_timeout"
            if not self._armed:
                return False, "disarmed"
            if self.allowed_fcu_modes and self._mode not in self.allowed_fcu_modes:
                return False, f"wrong_mode({self._mode})"
        return True, ""

    def _enter_standby(self, reason: str):
        """进入或保持 STANDBY:不发布控制指令,清求解状态,只发布状态。

        切换沿(ACTIVE → STANDBY 或首次进入)时:
          - 清零 _solver_fail_count
          - 重置 MPC 热启动,防止下次激活时使用过期解
          - 发布一次零速度"停止"指令,清除 MAVROS/FCU 中可能残留的旧设定
          - INFO 日志记录原因
        STANDBY 期间每 5 s 通过节流 WARN 日志重复原因。
        """
        transition = self._prev_state != "STANDBY"
        if transition:
            self._solver_fail_count = 0
            self._mpc_kin.reset_warmstart()
            # 发布零速度"停止"指令一次,清除 MAVROS/FCU 中可能残留的旧设定
            self._publish_velocity_cmd(np.zeros(2))
            self.get_logger().info(f"MPC → STANDBY: {reason}")

        self._prev_state = "STANDBY"
        self._last_standby_reason = reason
        self._publish_standby_status(reason)
        self.get_logger().warning(
            f"MPC 等待飞控就绪: {reason}",
            throttle_duration_sec=5.0,
        )

    def _control_loop(self):
        # 空闲模式:节点级关闭,不进入状态机
        if self.control_mode == ControlMode.IDLE:
            return

        with self._state_lock:
            ok, reason = self._can_solve()
            armed = self._armed
            mode = self._mode
        if not ok:
            self._enter_standby(reason)
            return

        # STANDBY → ACTIVE 切换沿:清失败计数,日志说明
        if self._prev_state != "ACTIVE":
            self.get_logger().info(
                f"MPC → ACTIVE: armed={armed}, mode={mode}"
            )
            self._solver_fail_count = 0
        self._prev_state = "ACTIVE"

        self._run_kinematic_mpc()

    def _enforce_solve_deadline(self, info: dict) -> dict:
        """把超时求解转化为受控失败。

        IPOPT/CasADi 在此处是同步求解，开始后无法抢占。但仍可避免迟到的结果
        被当作健康解：一次超时会累加正常失败计数，并在 /mpc/status 暴露，
        供 mode_manager / GCS 反应。
        """
        solve_time_ms = float(info.get("solve_time_ms", 0.0))
        deadline_miss = self.max_solve_time_ms > 0.0 and solve_time_ms > self.max_solve_time_ms
        info["max_solve_time_ms"] = float(self.max_solve_time_ms)
        info["deadline_miss"] = bool(deadline_miss)
        if deadline_miss:
            info["success"] = False
            info["error"] = (
                f"solve_timeout: {solve_time_ms:.1f}ms > "
                f"{self.max_solve_time_ms:.1f}ms"
            )
        return info

    def safe_shutdown(self):
        """节点退出前显式发送安全停车指令。"""
        self._publish_velocity_cmd(np.zeros(2))
        self._publish_standby_status("node_shutdown")
        self.get_logger().info("MPC 节点退出: 已发送安全停车指令")

    def _run_kinematic_mpc(self):
        """运动学 MPC → 速度指令。"""
        with self._state_lock:
            current_state = np.array([self._x, self._y, normalize_angle(self._psi)])
            reference = self._build_kinematic_reference(current_state)

        u_opt, info = self._mpc_kin.solve(current_state, reference)
        info = self._enforce_solve_deadline(info)
        if info.get("deadline_miss"):
            u_opt = np.zeros(2)
        in_hold = False

        if info["success"]:
            self._solver_fail_count = 0
            self._publish_velocity_cmd(u_opt)

            if self._control_count % 5 == 0:
                self._publish_predicted_trajectory(info.get("X_pred"))
        else:
            self._solver_fail_count += 1
            if self._solver_fail_count <= 3:
                self.get_logger().warn(
                    f"MPC 求解失败: {info.get('error', '未知错误')}  "
                    f"({info['solve_time_ms']:.1f}ms)  "
                    f"失败计数={self._solver_fail_count}"
                )
            if self._solver_fail_count >= self.solver_hold_threshold:
                in_hold = True
                u_opt = np.zeros(2)
                self._publish_velocity_cmd(u_opt)
                self._mpc_kin.reset_warmstart()
                if self._solver_fail_count == self.solver_hold_threshold:
                    self.get_logger().error(
                        f"MPC HOLD 挂起：连续失败 {self._solver_fail_count} 次，"
                        "正在发布零速度并重置热启动"
                    )
            else:
                self._publish_velocity_cmd(u_opt)

        info["u_opt"] = [float(u_opt[0]), float(u_opt[1])]
        info["psi_ref"] = float(reference[2, 0])
        info["e_psi"] = float(normalize_angle(current_state[2] - reference[2, 0]))
        self._publish_status(info, in_hold=in_hold)

        self._control_count += 1
        if self._control_count % 25 == 0:  # 大约每 5 秒输出一次
            self.get_logger().info(
                f"t={self._control_count * self.mpc_dt:.1f}s  "
                f"位置=({self._x:.1f},{self._y:.1f})  航向角={math.degrees(self._psi):.0f}°  "
                f"指令=(u={u_opt[0]:.2f}, r={math.degrees(u_opt[1]):.1f}°/s)  "
                f"求解时间={info['solve_time_ms']:.0f}ms"
            )

    def _publish_velocity_cmd(self, u_opt: np.ndarray):
        """发布 TwistStamped 速度指令。"""
        twist = TwistStamped()
        twist.header.stamp = self.get_clock().now().to_msg()
        twist.header.frame_id = self.body_frame
        twist.twist.linear.x = float(u_opt[0])
        twist.twist.linear.y = 0.0
        twist.twist.angular.z = float(u_opt[1])
        self._vel_pub.publish(twist)

    def _publish_status(self, info: dict, in_hold: bool):
        """在 /mpc/status 话题上发布结构化的求解器诊断信息。

        格式：JSON 编码的字符串。接收方（如 usv_safety/mode_manager_node）
        应当解析 JSON，而不是进行子字符串匹配。字段结构与方案 B 对齐
        (control_mode/backend/prediction_time_s 等),仅不含动力学特有的
        推力/RC 诊断字段 (tl_n/tr_n/steering_pwm/...)。
        """
        with self._state_lock:
            payload = {
                "state": "HOLD" if in_hold else "ACTIVE",
                "success": bool(info.get("success", False)),
                "fail_count": int(self._solver_fail_count),
                "solve_time_ms": float(info.get("solve_time_ms", 0.0)),
                "max_solve_time_ms": float(info.get("max_solve_time_ms", self.max_solve_time_ms)),
                "deadline_miss": bool(info.get("deadline_miss", False)),
                "hold": bool(in_hold),
                "scheme": self.scheme,
                "control_mode": self.control_mode.value,
                "require_fcu_state": bool(self.require_fcu_state),
                "fcu_mode": self._mode,
                "allowed_fcu_modes": self.allowed_fcu_modes,
                "armed": bool(self._armed),
                "path_received": bool(self._path_received),
                "path_len": len(self._reference_path),
                "profile_synced": bool(self._profile_synced),
                "profile_sync_reason": self._profile_sync_reason,
                "x": float(self._x),
                "y": float(self._y),
                "psi": float(normalize_angle(self._psi)),
                "u": float(self._u),
                "v": float(self._v),
                "r": float(self._r),
            }
            payload.update(self._last_ref_debug)
        # 框架诊断字段 (与方案 B status 对齐): 后端 + 预测时域 + 运动学控制量。
        payload.update({
            "prediction_time_s": float(self.horizon) * float(self.mpc_dt),
            # 求解器后端: "acados" 或 "ipopt"。便于实机诊断与 A/B 对比。
            "backend": str(self.backend),
        })
        if "u_opt" in info:
            payload["u_cmd"] = float(info["u_opt"][0])
            payload["r_cmd"] = float(info["u_opt"][1])
        if "psi_ref" in info:
            payload["psi_ref"] = float(info["psi_ref"])
        if "e_psi" in info:
            payload["e_psi"] = float(info["e_psi"])
        if not payload["success"]:
            payload["error"] = str(info.get("error", "未知错误"))
        msg = String()
        msg.data = json.dumps(payload, separators=(",", ":"))
        self._status_pub.publish(msg)

    def _publish_standby_status(self, reason: str):
        """待机期间发布最小诊断载荷,供 mode_manager / 地面站显示。"""
        with self._state_lock:
            payload = {
                "state": "STANDBY",
                "success": False,
                "fail_count": 0,
                "solve_time_ms": 0.0,
                "max_solve_time_ms": float(self.max_solve_time_ms),
                "deadline_miss": False,
                "hold": False,
                "scheme": self.scheme,
                "path_received": bool(self._path_received),
                "path_len": len(self._reference_path),
                "profile_synced": bool(self._profile_synced),
                "profile_sync_reason": self._profile_sync_reason,
                "standby_reason": reason,
            }
        msg = String()
        msg.data = json.dumps(payload, separators=(",", ":"))
        self._status_pub.publish(msg)

    def _build_kinematic_reference(self, current_state: np.ndarray) -> np.ndarray:
        """运动学 MPC 的 [3, N+1] 参考（仅 x, y, psi）。"""
        # profile 缺失时用 fallback_speed 做前瞻速度 (默认跟随 u_max)
        fallback_speed = float(self.get_parameter("kinematic.fallback_speed").value)
        if fallback_speed <= 0.0:
            fallback_speed = float(self.get_parameter("kinematic.u_max").value)
        # 保持原行为：运动学起点向前跳 1 个点
        return self._build_reference(current_state, 3, self.horizon, self.mpc_dt,
                                     fallback_speed, start_offset=1)

    def _build_reference(self, current_state, n_state, N, dt, fallback_speed, start_offset):
        """构建 N+1 步参考轨迹。

        优先用规划器给出的速度剖面按 **时间** 重采样（弯道/减速区参考自动放慢）；
        profile 缺失或与 path 不同步时，退化为旧的 **匀速弧长** 采样（r_ref=0），
        并通过 _last_ref_debug 暴露 profile_synced=False 供观测。
        """
        ref = np.zeros((n_state, N + 1))
        path = self._reference_path
        if len(path) == 0:
            return ref

        dists = [math.hypot(p[0] - current_state[0], p[1] - current_state[1]) for p in path]
        nearest_idx = int(np.argmin(dists))
        idx = min(nearest_idx + max(1, start_offset), len(path) - 1)

        prof = self._ref_profile
        path_stamp = self._reference_path_stamp
        profile_stamp = self._ref_profile_stamp
        synced, sync_reason = self._profile_sync_state(
            len(path), len(prof) if prof is not None else None, path_stamp, profile_stamp
        )

        if synced:
            times = [prof[i][3] for i in range(len(prof))]
            vs = [prof[i][0] for i in range(len(prof))]
            rs = [prof[i][2] for i in range(len(prof))]
            t0 = times[idx]
            j = idx
            for k in range(N + 1):
                tk = t0 + k * dt
                x, y, psi, v, r, j = self._sample_at_time(path, times, vs, rs, tk, j)
                ref[0, k] = x
                ref[1, k] = y
                ref[2, k] = psi
                if n_state == 6:
                    ref[3, k] = v
                    ref[4, k] = 0.0
                    ref[5, k] = r
            self._profile_synced = True
            self._profile_sync_reason = sync_reason
            self._last_ref_debug = {
                "profile_synced": True,
                "profile_sync_reason": sync_reason,
                "nearest_idx": nearest_idx,
                "ref_start_idx": idx,
                "nearest_dist": float(dists[nearest_idx]),
                "u_ref": float(vs[idx]),
                "r_ref": float(rs[idx]),
            }
            return ref

        # ---- 回退：匀速弧长采样（r_ref=0），profile 缺失/不同步 ----
        self._profile_synced = False
        arc = [0.0]
        for i in range(idx, len(path) - 1):
            seg = math.hypot(path[i + 1][0] - path[i][0],
                             path[i + 1][1] - path[i][1])
            arc.append(arc[-1] + seg)

        for k in range(N + 1):
            s_desired = fallback_speed * dt * k
            j = 0
            while j < len(arc) - 1 and arc[j + 1] < s_desired:
                j += 1
            ii = min(idx + j, len(path) - 1)
            if ii < len(path) - 1 and j < len(arc) - 1:
                seg_len = arc[j + 1] - arc[j]
                if seg_len > 1e-6:
                    t = max(0.0, min(1.0, (s_desired - arc[j]) / seg_len))
                    ref[0, k] = path[ii][0] + t * (path[ii + 1][0] - path[ii][0])
                    ref[1, k] = path[ii][1] + t * (path[ii + 1][1] - path[ii][1])
                    dpsi = normalize_angle(path[ii + 1][2] - path[ii][2])
                    ref[2, k] = normalize_angle(path[ii][2] + t * dpsi)
                else:
                    ref[0, k] = path[ii][0]
                    ref[1, k] = path[ii][1]
                    ref[2, k] = normalize_angle(path[ii][2])
            else:
                ref[0, k] = path[ii][0]
                ref[1, k] = path[ii][1]
                ref[2, k] = normalize_angle(path[ii][2])
            if n_state == 6:
                ref[3, k] = fallback_speed
                ref[4, k] = 0.0
                ref[5, k] = 0.0

        self._profile_sync_reason = sync_reason
        self._last_ref_debug = {
            "profile_synced": False,
            "profile_sync_reason": sync_reason,
            "nearest_idx": nearest_idx,
            "ref_start_idx": idx,
            "nearest_dist": float(dists[nearest_idx]),
            "u_ref": float(fallback_speed),
            "r_ref": 0.0,
        }
        return ref

    @staticmethod
    def _sample_at_time(path, times, vs, rs, tk, j_hint):
        """在时间 tk 处对 (path, profile) 插值，返回 (x, y, psi, v, r, j)。

        times 单调递增；j_hint 为搜索起点（参考逐步前进，避免每步从头扫）。
        tk 超出末点时夹取到末点（末端速度趋缓，配合任务完成 HOLD 停车）。
        """
        return sample_path_profile_at_time(path, times, vs, rs, tk, j_hint)

    def _publish_predicted_trajectory(self, X_pred):
        """发布 MPC 预测轨迹（作为 NavPath），用于可视化。"""
        if not self.publish_predicted or X_pred is None:
            return

        msg = NavPath()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.path_frame

        from geometry_msgs.msg import PoseStamped

        for i in range(X_pred.shape[1]):
            pose = PoseStamped()
            pose.header = msg.header
            pose.pose.position.x = float(X_pred[0, i])
            pose.pose.position.y = float(X_pred[1, i])
            pose.pose.position.z = 0.0
            # 将航向角转换为四元数
            psi = float(X_pred[2, i])
            pose.pose.orientation.z = math.sin(psi / 2)
            pose.pose.orientation.w = math.cos(psi / 2)
            msg.poses.append(pose)

        self._traj_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = MpcControllerNode()
    executor = MultiThreadedExecutor(num_threads=3)
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        if rclpy.ok():
            node.safe_shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
