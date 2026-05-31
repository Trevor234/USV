"""适用于无人船 (USV) 的 MPC 控制器 ROS 2 节点。

订阅话题（可通过 launch 参数覆盖）：
  /mavros/local_position/odom     — EKF 融合的位置与速度
  /mavros/imu/data                — IMU 数据（用于动力学模式）
  /path/reference                 — 规划器给出的参考路径

发布话题（可通过 launch 参数覆盖）：
  /mavros/setpoint_velocity/cmd_vel  — 速度设定值（方案 A）
  /mavros/rc/override                — RC 通道覆写控制（方案 B）
  /mpc/predicted_trajectory          — 用于可视化的 MPC 预测轨迹
  /mpc/status                        — 求解器诊断信息

支持方案 A（运动学 MPC）与方案 B（动力学 NMPC）。
"""

import json
import math
import time
from enum import Enum

import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Quaternion, TwistStamped, Vector3
from mavros_msgs.msg import OverrideRCIn, State as MavrosState
from nav_msgs.msg import Odometry, Path as NavPath
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import String

from .mpc_kinematic import KinematicMPC
from .mpc_dynamic import DynamicMPC
from .utils import normalize_angle, quaternion_to_yaw


class ControlMode(Enum):
    IDLE = "idle"
    KINEMATIC = "kinematic"
    DYNAMIC = "dynamic"


class MpcControllerNode(Node):
    """适用于双推进器无人船 (USV) 的 ROS 2 MPC 控制器节点。"""

    def __init__(self):
        super().__init__("mpc_controller_node")

        self._declare_parameters()
        self._load_config()

        self._init_mpc_solvers()
        self._init_state()
        self._init_pubsub()

        self.get_logger().info(
            f"MPC 控制器已启动 | 模式={self.control_mode.value} "
            f"| dt={self.mpc_dt}s | N={self.horizon} | "
            f"方案={'A (运动学)' if self.scheme == 'A' else 'B (动力学)'}"
        )

        self._timer = self.create_timer(self.mpc_dt, self._control_loop)

    def _declare_parameters(self):
        self.declare_parameter("scheme", "A")
        self.declare_parameter("control_mode", "kinematic")
        self.declare_parameter("mpc_dt", 0.2)
        self.declare_parameter("horizon", 20)
        self.declare_parameter("odom_topic", "/mavros/local_position/odom")
        self.declare_parameter("imu_topic", "/mavros/imu/data")
        self.declare_parameter("path_topic", "/path/reference")
        self.declare_parameter("state_topic", "/mavros/state")
        self.declare_parameter("velocity_topic", "/mavros/setpoint_velocity/cmd_vel")
        self.declare_parameter("rc_override_topic", "/mavros/rc/override")
        self.declare_parameter("publish_predicted", True)
        self.declare_parameter("max_solve_time_ms", 200.0)
        # 进入 HOLD（挂起）模式前允许的连续求解失败次数：停止发送过时的控制指令，
        # 并重置热启动，以便下一次尝试能够从头开始。应与
        # usv_safety/mode_manager_node.max_solver_failures 一致。
        self.declare_parameter("solver_hold_threshold", 5)
        # 飞控就绪判据：允许 MPC 输出指令的 FCU 模式白名单。
        # 方案 A 使用 cmd_vel,只在 GUIDED 下被 ArduPilot 接受;
        # 方案 B 使用 RC override,可改为 ["MANUAL"] 或留空允许所有模式。
        self.declare_parameter("allowed_fcu_modes", ["GUIDED"])
        # MAVROS 状态心跳超时(秒);超过则视为飞控失联,进入 STANDBY
        self.declare_parameter("state_timeout_s", 2.0)
        # 里程计超时(秒);0 关闭检查
        self.declare_parameter("odom_timeout_s", 1.0)
        self.declare_parameter("reference_start_offset", 3)

        # 方案 A 参数
        self.declare_parameter("kinematic.Q", [10.0, 10.0, 50.0])
        self.declare_parameter("kinematic.R", [1.0, 1.0])
        self.declare_parameter("kinematic.Qf_scale", 10.0)
        self.declare_parameter("kinematic.u_max", 2.0)
        self.declare_parameter("kinematic.u_min", 0.0)
        self.declare_parameter("kinematic.r_max", 0.5)
        self.declare_parameter("kinematic.du_max", 0.8)
        self.declare_parameter("kinematic.dr_max", 0.5)

        # 方案 B 参数
        self.declare_parameter("dynamic.Q", [10.0, 10.0, 50.0, 5.0, 1.0, 5.0])
        self.declare_parameter("dynamic.R", [0.01, 0.01])
        self.declare_parameter("dynamic.Rd", [0.1, 0.1])
        self.declare_parameter("dynamic.Qf_scale", 10.0)
        self.declare_parameter("dynamic.T_max", 40.0)
        self.declare_parameter("dynamic.T_min", -20.0)
        self.declare_parameter("dynamic.dT_max", 30.0)
        self.declare_parameter("dynamic.dt", 0.1)
        self.declare_parameter("rc_steering_channel", 0)
        self.declare_parameter("rc_throttle_channel", 2)
        self.declare_parameter("rc_pwm_min", 1100)
        self.declare_parameter("rc_pwm_center", 1500)
        self.declare_parameter("rc_pwm_max", 1900)
        self.declare_parameter("steering_sign", 1.0)
        self.declare_parameter("throttle_sign", 1.0)
        self.declare_parameter("steering_gain", 0.25)
        self.declare_parameter("throttle_gain", 0.5)

        # 船体参数（用于动力学模式）
        self.declare_parameter("vehicle.mass", 30.0)
        self.declare_parameter("vehicle.Iz", 8.0)
        self.declare_parameter("vehicle.xg", 0.0)
        self.declare_parameter("vehicle.d_thruster", 0.3)
        self.declare_parameter("vehicle.Xu_dot", -3.0)
        self.declare_parameter("vehicle.Yv_dot", -20.0)
        self.declare_parameter("vehicle.Yr_dot", -0.5)
        self.declare_parameter("vehicle.Nv_dot", -0.5)
        self.declare_parameter("vehicle.Nr_dot", -2.0)
        self.declare_parameter("vehicle.Xu", -8.0)
        self.declare_parameter("vehicle.Yv", -30.0)
        self.declare_parameter("vehicle.Yr", -1.0)
        self.declare_parameter("vehicle.Nv", -1.0)
        self.declare_parameter("vehicle.Nr", -5.0)
        self.declare_parameter("vehicle.Xuu", -15.0)
        self.declare_parameter("vehicle.Yvv", -60.0)
        self.declare_parameter("vehicle.Yrr", -1.0)
        self.declare_parameter("vehicle.Nvv", -1.0)
        self.declare_parameter("vehicle.Nrr", -3.0)

    def _load_config(self):
        self.scheme = self.get_parameter("scheme").value
        mode_str = self.get_parameter("control_mode").value
        try:
            self.control_mode = ControlMode(mode_str)
        except ValueError:
            self.control_mode = ControlMode.IDLE

        self.mpc_dt = self.get_parameter("mpc_dt").value
        self.horizon = self.get_parameter("horizon").value
        self.max_solve_time_ms = self.get_parameter("max_solve_time_ms").value
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
        self.reference_start_offset = int(self.get_parameter("reference_start_offset").value)
        self.rc_steering_channel = int(self.get_parameter("rc_steering_channel").value)
        self.rc_throttle_channel = int(self.get_parameter("rc_throttle_channel").value)
        self.rc_pwm_min = int(self.get_parameter("rc_pwm_min").value)
        self.rc_pwm_center = int(self.get_parameter("rc_pwm_center").value)
        self.rc_pwm_max = int(self.get_parameter("rc_pwm_max").value)
        self.steering_sign = float(self.get_parameter("steering_sign").value)
        self.throttle_sign = float(self.get_parameter("throttle_sign").value)
        self.steering_gain = float(self.get_parameter("steering_gain").value)
        self.throttle_gain = float(self.get_parameter("throttle_gain").value)

    def _init_mpc_solvers(self):
        self._mpc_kin = None
        self._mpc_dyn = None

        if self.scheme in ("A", "both"):
            self._mpc_kin = KinematicMPC(
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

        if self.scheme in ("B", "both"):
            dyn_dt = self.get_parameter("dynamic.dt").value
            dyn_N = int(self.horizon * dyn_dt / self.mpc_dt) + 1
            model_params = {
                "mass": self.get_parameter("vehicle.mass").value,
                "Iz": self.get_parameter("vehicle.Iz").value,
                "xg": self.get_parameter("vehicle.xg").value,
                "d_thruster": self.get_parameter("vehicle.d_thruster").value,
                "Xu_dot": self.get_parameter("vehicle.Xu_dot").value,
                "Yv_dot": self.get_parameter("vehicle.Yv_dot").value,
                "Yr_dot": self.get_parameter("vehicle.Yr_dot").value,
                "Nv_dot": self.get_parameter("vehicle.Nv_dot").value,
                "Nr_dot": self.get_parameter("vehicle.Nr_dot").value,
                "Xu": self.get_parameter("vehicle.Xu").value,
                "Yv": self.get_parameter("vehicle.Yv").value,
                "Yr": self.get_parameter("vehicle.Yr").value,
                "Nv": self.get_parameter("vehicle.Nv").value,
                "Nr": self.get_parameter("vehicle.Nr").value,
                "Xuu": self.get_parameter("vehicle.Xuu").value,
                "Yvv": self.get_parameter("vehicle.Yvv").value,
                "Yrr": self.get_parameter("vehicle.Yrr").value,
                "Nvv": self.get_parameter("vehicle.Nvv").value,
                "Nrr": self.get_parameter("vehicle.Nrr").value,
            }
            self._mpc_dyn = DynamicMPC(
                dt=dyn_dt,
                N=dyn_N,
                Q_diag=tuple(self.get_parameter("dynamic.Q").value),
                R_diag=tuple(self.get_parameter("dynamic.R").value),
                Rd_diag=tuple(self.get_parameter("dynamic.Rd").value),
                Qf_scale=self.get_parameter("dynamic.Qf_scale").value,
                T_max=self.get_parameter("dynamic.T_max").value,
                T_min=self.get_parameter("dynamic.T_min").value,
                dT_max=self.get_parameter("dynamic.dT_max").value,
                model_params=model_params,
            )

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
        self._reference_path = []  # 格式为 [x, y, psi, u_ref, v_ref, r_ref] 的列表
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

    def _init_pubsub(self):
        # 订阅者
        odom_topic = self.get_parameter("odom_topic").value
        imu_topic = self.get_parameter("imu_topic").value
        path_topic = self.get_parameter("path_topic").value
        state_topic = self.get_parameter("state_topic").value

        self._odom_sub = self.create_subscription(
            Odometry, odom_topic, self._odom_callback, qos_profile_sensor_data
        )
        self._imu_sub = self.create_subscription(
            Imu, imu_topic, self._imu_callback, qos_profile_sensor_data
        )
        self._path_sub = self.create_subscription(
            NavPath, path_topic, self._path_callback, 10
        )
        self._state_sub = self.create_subscription(
            MavrosState, state_topic, self._state_callback, 10
        )

        # 发布者
        vel_topic = self.get_parameter("velocity_topic").value
        self._vel_pub = self.create_publisher(TwistStamped, vel_topic, 10)

        rc_topic = self.get_parameter("rc_override_topic").value
        self._rc_pub = self.create_publisher(OverrideRCIn, rc_topic, 10)

        self._traj_pub = self.create_publisher(NavPath, "/mpc/predicted_trajectory", 10)
        self._status_pub = self.create_publisher(String, "/mpc/status", 10)

    # ---------- 回调函数 ----------

    def _odom_callback(self, msg: Odometry):
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
        # 使用直接陀螺仪角速度以获得更灵敏的 r 测量值
        self._r = msg.angular_velocity.z
        self._imu_received = True

    def _path_callback(self, msg: NavPath):
        self._reference_path = []
        for pose in msg.poses:
            x = pose.pose.position.x
            y = pose.pose.position.y
            q = pose.pose.orientation
            psi = quaternion_to_yaw(q.x, q.y, q.z, q.w)
            self._reference_path.append([x, y, psi, 1.0, 0.0, 0.0])
        self._path_received = len(self._reference_path) > 0

    def _state_callback(self, msg: MavrosState):
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
          - 发布一次"停止"指令(方案 A: 零速度;方案 B: 释放 RC override)
          - INFO 日志记录原因
        STANDBY 期间每 5 s 通过节流 WARN 日志重复原因。
        """
        transition = self._prev_state != "STANDBY"
        if transition:
            self._solver_fail_count = 0
            if self._mpc_kin is not None:
                self._mpc_kin.reset_warmstart()
            if self._mpc_dyn is not None:
                self._mpc_dyn.reset_warmstart()
            # 发布"停止"指令一次,清除 MAVROS/FCU 中可能残留的旧设定
            if self.scheme == "A":
                self._publish_velocity_cmd(np.zeros(2))
            elif self.scheme == "B":
                self._release_rc_override()
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

        ok, reason = self._can_solve()
        if not ok:
            self._enter_standby(reason)
            return

        # STANDBY → ACTIVE 切换沿:清失败计数,日志说明
        if self._prev_state != "ACTIVE":
            self.get_logger().info(
                f"MPC → ACTIVE: armed={self._armed}, mode={self._mode}"
            )
            self._solver_fail_count = 0
        self._prev_state = "ACTIVE"

        if self.scheme == "A":
            self._run_kinematic_mpc()
        elif self.scheme == "B":
            self._run_dynamic_mpc()

    def safe_shutdown(self):
        """节点退出前显式发送安全停车指令。"""
        if self.scheme == "A":
            self._publish_velocity_cmd(np.zeros(2))
        elif self.scheme == "B":
            self._release_rc_override()
        self._publish_standby_status("node_shutdown")
        self.get_logger().info("MPC 节点退出: 已发送安全停车指令")

    def _release_rc_override(self):
        """发布全零 OverrideRCIn 以释放所有通道,让 FCU 回到正常 RC 输入。"""
        rc_msg = OverrideRCIn()
        # OverrideRCIn 默认 18 通道全 0;在 MAVROS 中 0 表示释放通道(不覆写)
        self._rc_pub.publish(rc_msg)

    def _run_kinematic_mpc(self):
        """方案 A：运动学 MPC → 速度指令。"""
        current_state = np.array([self._x, self._y, normalize_angle(self._psi)])
        reference = self._build_kinematic_reference(current_state)

        u_opt, info = self._mpc_kin.solve(current_state, reference)
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
        """发布 TwistStamped 速度指令（方案 A）。"""
        twist = TwistStamped()
        twist.header.stamp = self.get_clock().now().to_msg()
        twist.header.frame_id = "base_link"
        twist.twist.linear.x = float(u_opt[0])
        twist.twist.linear.y = 0.0
        twist.twist.angular.z = float(u_opt[1])
        self._vel_pub.publish(twist)

    def _run_dynamic_mpc(self):
        """方案 B：动力学 NMPC → 推力 → RC 覆写。"""
        current_state = np.array([
            self._x, self._y, normalize_angle(self._psi),
            self._u, self._v, self._r,
        ])
        reference = self._build_dynamic_reference(current_state)

        u_opt, info = self._mpc_dyn.solve(current_state, reference)
        in_hold = False

        if info["success"]:
            self._solver_fail_count = 0
            self._publish_rc_override(u_opt)

            if self._control_count % 5 == 0:
                self._publish_predicted_trajectory(info.get("X_pred"))
        else:
            self._solver_fail_count += 1
            if self._solver_fail_count <= 3:
                self.get_logger().warn(
                    f"NMPC 求解失败: {info.get('error', '未知错误')}  "
                    f"失败计数={self._solver_fail_count}"
                )
            if self._solver_fail_count >= self.solver_hold_threshold:
                in_hold = True
                u_opt = np.zeros(2)  # 零推力 → 中位 throttle/steering RC 输入
                self._publish_rc_override(u_opt)
                self._mpc_dyn.reset_warmstart()
                if self._solver_fail_count == self.solver_hold_threshold:
                    self.get_logger().error(
                        f"NMPC HOLD 挂起：连续失败 {self._solver_fail_count} 次，"
                        "正在发布零推力并重置热启动"
                    )
            else:
                self._publish_rc_override(u_opt)

        self._publish_status(info, in_hold=in_hold)

        self._control_count += 1
        if self._control_count % 10 == 0:
            self.get_logger().info(
                f"t={self._control_count * self.mpc_dt:.1f}s  "
                f"位置=({self._x:.1f},{self._y:.1f})  "
                f"左推力={u_opt[0]:.1f}N  右推力={u_opt[1]:.1f}N  "
                f"求解时间={info['solve_time_ms']:.0f}ms"
            )

    def _thrust_to_rc_pwm(self, thrust: np.ndarray) -> tuple:
        """将左右推力转换为 ArduRover throttle/steering RC 输入 PWM。

        OverrideRCIn 是遥控输入而不是 SERVO 输出。这里先把 NMPC 的
        [T_L, T_R] 转成 throttle/steering，再交给 ArduRover mixer 生成
        /mavros/rc/out 上的左右推进器输出。
        """
        t_max = max(float(self.get_parameter("dynamic.T_max").value), 1.0)
        t_min = abs(min(float(self.get_parameter("dynamic.T_min").value), -1.0))
        left = float(thrust[0])
        right = float(thrust[1])

        throttle_n = 0.5 * (left + right)
        throttle_scale = t_max if throttle_n >= 0.0 else t_min
        throttle_n = self.throttle_sign * self.throttle_gain * np.clip(throttle_n / throttle_scale, -1.0, 1.0)

        steering_span = max(t_max, t_min)
        steering_n = self.steering_sign * self.steering_gain * np.clip((right - left) / (2.0 * steering_span), -1.0, 1.0)

        def to_pwm(value: float) -> int:
            value = float(np.clip(value, -1.0, 1.0))
            if value >= 0.0:
                pwm = self.rc_pwm_center + value * (self.rc_pwm_max - self.rc_pwm_center)
            else:
                pwm = self.rc_pwm_center + value * (self.rc_pwm_center - self.rc_pwm_min)
            return int(np.clip(round(pwm), self.rc_pwm_min, self.rc_pwm_max))

        return to_pwm(steering_n), to_pwm(throttle_n)

    def _publish_rc_override(self, thrust: np.ndarray):
        """通过 OverrideRCIn 发布 throttle/steering 遥控输入（方案 B）。"""
        steering_pwm, throttle_pwm = self._thrust_to_rc_pwm(thrust)
        rc_msg = OverrideRCIn()
        if 0 <= self.rc_steering_channel < len(rc_msg.channels):
            rc_msg.channels[self.rc_steering_channel] = steering_pwm
        if 0 <= self.rc_throttle_channel < len(rc_msg.channels):
            rc_msg.channels[self.rc_throttle_channel] = throttle_pwm
        self._rc_pub.publish(rc_msg)

    def _publish_status(self, info: dict, in_hold: bool):
        """在 /mpc/status 话题上发布结构化的求解器诊断信息。

        格式：JSON 编码的字符串，包含以下字段：
          状态 state："ACTIVE"、"HOLD" 或 "STANDBY"；
          是否成功 success、失败计数 fail_count、求解时间 solve_time_ms；
          是否挂起 hold、控制方案 scheme；
          失败时包含错误信息 error，待机时包含待机原因 standby_reason。

        接收方（如 usv_safety/mode_manager_node）应当解析 JSON，
        而不是进行子字符串匹配。
        """
        payload = {
            "state": "HOLD" if in_hold else "ACTIVE",
            "success": bool(info.get("success", False)),
            "fail_count": int(self._solver_fail_count),
            "solve_time_ms": float(info.get("solve_time_ms", 0.0)),
            "hold": bool(in_hold),
            "scheme": self.scheme,
        }
        if not payload["success"]:
            payload["error"] = str(info.get("error", "未知错误"))
        msg = String()
        msg.data = json.dumps(payload, separators=(",", ":"))
        self._status_pub.publish(msg)

    def _publish_standby_status(self, reason: str):
        """待机期间发布最小诊断载荷,供 mode_manager / 地面站显示。"""
        payload = {
            "state": "STANDBY",
            "success": False,
            "fail_count": 0,
            "solve_time_ms": 0.0,
            "hold": False,
            "scheme": self.scheme,
            "standby_reason": reason,
        }
        msg = String()
        msg.data = json.dumps(payload, separators=(",", ":"))
        self._status_pub.publish(msg)

    def _build_kinematic_reference(self, current_state: np.ndarray) -> np.ndarray:
        """从路径点构建用于运动学 MPC 的 N+1 步参考轨迹。

        使用弧长参数化方法，使得参考轨迹在每个 MPC 时间步长内正好以巡航速度（cruise_speed）
        前进，而与参考路径点的实际间距无关。
        """
        N = self.horizon
        ref = np.zeros((3, N + 1))
        path = self._reference_path
        # 使用最大速度 u_max 进行前瞻，为 MPC 在弯道处提供足够的预览距离
        lookahead_speed = self.get_parameter("kinematic.u_max").value

        # 寻找最近的路径点索引，然后向前跳 1 步以始终产生向前的吸引力
        dists = [math.hypot(p[0] - current_state[0], p[1] - current_state[1]) for p in path]
        idx = min(int(np.argmin(dists)) + 1, len(path) - 1)

        # 预先计算从 idx 开始的累计弧长
        arc = [0.0]
        for i in range(idx, len(path) - 1):
            seg = math.hypot(path[i + 1][0] - path[i][0],
                             path[i + 1][1] - path[i][1])
            arc.append(arc[-1] + seg)

        for k in range(N + 1):
            # 距离最近路径点沿路径的期望距离
            s_desired = lookahead_speed * self.mpc_dt * k

            # 寻找包围 s_desired 的两个路径点
            j = 0
            while j < len(arc) - 1 and arc[j + 1] < s_desired:
                j += 1

            ii = min(idx + j, len(path) - 1)

            # 在 path[ii] 和 path[ii+1] 之间进行线性插值
            if ii < len(path) - 1 and j < len(arc) - 1:
                seg_len = arc[j + 1] - arc[j]
                if seg_len > 1e-6:
                    t = (s_desired - arc[j]) / seg_len
                    t = max(0.0, min(1.0, t))
                    ref[0, k] = path[ii][0] + t * (path[ii + 1][0] - path[ii][0])
                    ref[1, k] = path[ii][1] + t * (path[ii + 1][1] - path[ii][1])
                    # 通过角度混合插值航向角
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

        return ref

    def _build_dynamic_reference(self, current_state: np.ndarray) -> np.ndarray:
        """从路径点构建用于动力学 NMPC 的 N+1 步参考轨迹。

        使用弧长采样（与运动学相同的方案），使参考轨迹每步前进 cruise_speed * dt，
        而与路径的分辨率无关。
        """
        N = self._mpc_dyn.N
        dt = self._mpc_dyn.dt
        ref = np.zeros((6, N + 1))
        path = self._reference_path
        cruise_speed = 1.0

        # 寻找最近点索引，并向前跳若干路径点以保持前视拉力。
        # 只跳 1 个点在有横向误差时容易追逐最近点，导致大弧线偏离路径。
        dists = [math.hypot(p[0] - current_state[0], p[1] - current_state[1]) for p in path]
        idx = min(int(np.argmin(dists)) + max(1, self.reference_start_offset), len(path) - 1)

        # 从 idx 开始的累计弧长
        arc = [0.0]
        for i in range(idx, len(path) - 1):
            seg = math.hypot(path[i + 1][0] - path[i][0],
                             path[i + 1][1] - path[i][1])
            arc.append(arc[-1] + seg)

        for k in range(N + 1):
            s_desired = cruise_speed * dt * k

            j = 0
            while j < len(arc) - 1 and arc[j + 1] < s_desired:
                j += 1

            ii = min(idx + j, len(path) - 1)

            if ii < len(path) - 1 and j < len(arc) - 1:
                seg_len = arc[j + 1] - arc[j]
                if seg_len > 1e-6:
                    t = (s_desired - arc[j]) / seg_len
                    t = max(0.0, min(1.0, t))
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

            ref[3, k] = cruise_speed
            ref[4, k] = 0.0
            ref[5, k] = 0.0
        return ref

    def _publish_predicted_trajectory(self, X_pred):
        """发布 MPC 预测轨迹（作为 NavPath），用于可视化。"""
        if not self.publish_predicted or X_pred is None:
            return

        msg = NavPath()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "map"

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
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.safe_shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
