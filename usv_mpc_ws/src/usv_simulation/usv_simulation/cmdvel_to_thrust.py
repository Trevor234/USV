#!/usr/bin/env python3
"""cmd_vel → VRX 双桨推力 转换节点 (方案 A 运动学 MPC 的 VRX 执行层)。

级联控制内环: 方案 A 的运动学 MPC 发布期望前进速度 u_cmd 与转艏角速度
r_cmd (TwistStamped); 本节点用 2026-09-03 辨识的动力学逆模型 + 测量反馈,
把它们映射为双桨推力 (N):

  总推力   F  = drag(u_cmd) + kp_u · (u_cmd − u_meas)      [N]
  转艏力矩 τ  = yaw_ff(r_cmd) + kp_r · (r_cmd − r_meas)    [N·m]
  T_L, T_R    = (F ∓ τ/d) / 2

  drag(u)    = |Xu|·u + |Xuu|·u·|u|   (纵向阻力前馈, 7-23 先验)
  yaw_ff(r)  = |Nr|·r + |Nrr|·r·|r|   (阶段 3 艏摇阻尼前馈)
  d          = 半桨距 0.25 m

参数默认值与 usv_params_sim.yaml / usv_mono 植物模型一致 (数字孪生)。
cmd_vel 断流 >0.3 s → 推力归零 (MPC 死亡/STANDBY 即停船)。
"""
import math

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import Float64


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class CmdvelToThrust(Node):

    def __init__(self):
        super().__init__("cmdvel_to_thrust")
        self._declare_parameters()

        self._d = float(self.get_parameter("d_thruster").value)
        self._xu = abs(float(self.get_parameter("xu").value))
        self._xuu = abs(float(self.get_parameter("xuu").value))
        self._nr = abs(float(self.get_parameter("nr").value))
        self._nrr = abs(float(self.get_parameter("nrr").value))
        self._t_max = float(self.get_parameter("t_max").value)
        self._kp_u = float(self.get_parameter("kp_u").value)
        self._kp_r = float(self.get_parameter("kp_r").value)
        self._cmd_timeout = float(self.get_parameter("cmd_timeout_s").value)

        self._u_cmd = 0.0
        self._r_cmd = 0.0
        self._u_meas = 0.0
        self._r_meas = 0.0
        self._last_cmd_time = None

        cmd_topic = self.get_parameter("cmd_vel_topic").value
        odom_topic = self.get_parameter("odom_topic").value
        lt = self.get_parameter("left_thrust_topic").value
        rt = self.get_parameter("right_thrust_topic").value

        self.create_subscription(TwistStamped, cmd_topic,
                                 self._cmd_callback, 10)
        self.create_subscription(Odometry, odom_topic,
                                 self._odom_callback,
                                 qos_profile_sensor_data)
        self._tl_pub = self.create_publisher(Float64, lt, 10)
        self._tr_pub = self.create_publisher(Float64, rt, 10)
        self._timer = self.create_timer(0.02, self._tick)  # 50 Hz 内环

        self.get_logger().info(
            f"cmdvel_to_thrust 启动 | d={self._d}m T_max={self._t_max}N "
            f"kp_u={self._kp_u} kp_r={self._kp_r} | cmd={cmd_topic}")

    def _declare_parameters(self):
        self.declare_parameter("cmd_vel_topic", "/usv/cmd_vel")
        self.declare_parameter(
            "odom_topic", "/wamv/sensors/position/ground_truth_odometry")
        self.declare_parameter("left_thrust_topic",
                               "/wamv/thrusters/left/thrust")
        self.declare_parameter("right_thrust_topic",
                               "/wamv/thrusters/right/thrust")
        # 植物模型 (与 usv_params_sim.yaml 一致; 取绝对值做前馈)
        self.declare_parameter("d_thruster", 0.25)
        self.declare_parameter("xu", 2.272)       # |Xu|
        self.declare_parameter("xuu", 11.572)     # |Xuu|
        self.declare_parameter("nr", 3.105)       # |Nr| (阶段 3)
        self.declare_parameter("nrr", 0.71)       # |Nrr| (阶段 3)
        self.declare_parameter("t_max", 25.0)
        # 反馈增益
        self.declare_parameter("kp_u", 8.0)
        self.declare_parameter("kp_r", 2.0)
        self.declare_parameter("cmd_timeout_s", 0.3)

    def _cmd_callback(self, msg: TwistStamped):
        self._u_cmd = msg.twist.linear.x
        self._r_cmd = msg.twist.angular.z
        self._last_cmd_time = self.get_clock().now()

    def _odom_callback(self, msg: Odometry):
        self._u_meas = msg.twist.twist.linear.x
        self._r_meas = msg.twist.twist.angular.z

    def _tick(self):
        now = self.get_clock().now()
        if (self._last_cmd_time is None or
                (now - self._last_cmd_time).nanoseconds * 1e-9
                > self._cmd_timeout):
            u_cmd, r_cmd = 0.0, 0.0    # cmd_vel 断流 → 推力归零 (MPC 侧已死)
        else:
            u_cmd = clamp(self._u_cmd, 0.0, 5.0)
            r_cmd = clamp(self._r_cmd, -1.5, 1.5)

        # 纵向: 阻力前馈 + 速度误差 P
        f_total = (self._xu * u_cmd + self._xuu * u_cmd * abs(u_cmd)
                   + self._kp_u * (u_cmd - self._u_meas))
        f_total = clamp(f_total, 0.0, 2.0 * self._t_max)

        # 艏摇: 阻尼前馈 + 角速度误差 P
        tau = (self._nr * r_cmd + self._nrr * r_cmd * abs(r_cmd)
               + self._kp_r * (r_cmd - self._r_meas))
        tau = clamp(tau, -self._d * self._t_max, self._d * self._t_max)

        tl = clamp((f_total - tau / self._d) / 2.0,
                   -self._t_max, self._t_max)
        tr = clamp((f_total + tau / self._d) / 2.0,
                   -self._t_max, self._t_max)

        self.get_logger().info(
            f"u_cmd={u_cmd:.3f} r_cmd={r_cmd:.3f} u_meas={self._u_meas:.3f} "
            f"r_meas={self._r_meas:.3f} -> F={f_total:.2f} tau={tau:.2f} "
            f"TL={tl:.2f} TR={tr:.2f}", throttle_duration_sec=2.0)
        self._tl_pub.publish(Float64(data=tl))
        self._tr_pub.publish(Float64(data=tr))


def main(args=None):
    rclpy.init(args=args)
    node = CmdvelToThrust()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
