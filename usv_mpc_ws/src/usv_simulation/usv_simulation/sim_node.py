"""USV Dynamics Simulator Node.

Simulates the 6-DOF dynamics of the USV in real time.
Publishes:
  /mavros/mavros/odom   — simulated odometry (with noise)
  /mavros/mavros/data              — simulated IMU
  /mavros/state                 — simulated MAVROS state

Subscribes to:
  /mavros/mavros/cmd_vel  — velocity commands (Scheme A)
  /mavros/mavros/override               — RC override (Scheme B)

Use this for testing MPC without hardware or SITL.
"""

import math
import time

import numpy as np
import rclpy
from geometry_msgs.msg import Quaternion, TwistStamped, Vector3
from mavros_msgs.msg import OverrideRCIn, State as MavrosState
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import Imu


class USVSimulator(Node):
    """Simple USV dynamics simulator for offline MPC testing."""

    def __init__(self):
        super().__init__("usv_sim_node")

        self._declare_parameters()
        self._init_state()
        self._init_pubsub()

        self._timer = self.create_timer(self._dt, self._simulation_step)
        self.get_logger().info(
            f"USV Simulator started | dt={self._dt}s | "
            f"initial=({self._x},{self._y},{math.degrees(self._psi):.0f}°)"
        )

    def _declare_parameters(self):
        # Simulation params
        self.declare_parameter("dt", 0.05)
        self.declare_parameter("publish_rate", 20.0)
        self.declare_parameter("add_noise", True)
        self.declare_parameter("noise_scale_pos", 0.05)
        self.declare_parameter("noise_scale_vel", 0.02)

        # Initial conditions
        self.declare_parameter("x_init", 0.0)
        self.declare_parameter("y_init", 0.0)
        self.declare_parameter("psi_init", 0.0)
        self.declare_parameter("u_init", 0.0)
        self.declare_parameter("v_init", 0.0)
        self.declare_parameter("r_init", 0.0)

        # Hull parameters (same as dynamic model)
        self.declare_parameter("mass", 30.0)
        self.declare_parameter("Iz", 8.0)
        self.declare_parameter("xg", 0.0)
        self.declare_parameter("d_thruster", 0.3)
        self.declare_parameter("Xu_dot", -3.0)
        self.declare_parameter("Yv_dot", -20.0)
        self.declare_parameter("Yr_dot", -0.5)
        self.declare_parameter("Nv_dot", -0.5)
        self.declare_parameter("Nr_dot", -2.0)
        self.declare_parameter("Xu", -8.0)
        self.declare_parameter("Yv", -30.0)
        self.declare_parameter("Yr", -1.0)
        self.declare_parameter("Nv", -1.0)
        self.declare_parameter("Nr", -5.0)
        self.declare_parameter("Xuu", -15.0)
        self.declare_parameter("Yvv", -60.0)
        self.declare_parameter("Yrr", -1.0)
        self.declare_parameter("Nvv", -1.0)
        self.declare_parameter("Nrr", -3.0)

    def _init_state(self):
        self._dt = self.get_parameter("dt").value
        self._add_noise = self.get_parameter("add_noise").value
        self._noise_pos = self.get_parameter("noise_scale_pos").value
        self._noise_vel = self.get_parameter("noise_scale_vel").value

        self._x = self.get_parameter("x_init").value
        self._y = self.get_parameter("y_init").value
        self._psi = self.get_parameter("psi_init").value
        self._u = self.get_parameter("u_init").value
        self._v = self.get_parameter("v_init").value
        self._r = self.get_parameter("r_init").value

        # Control inputs
        self._cmd_u = 0.0   # commanded surge velocity
        self._cmd_r = 0.0   # commanded yaw rate
        self._TL = 0.0      # left thrust
        self._TR = 0.0      # right thrust

        # Hull params
        self._m = self.get_parameter("mass").value
        self._Iz = self.get_parameter("Iz").value
        self._xg = self.get_parameter("xg").value
        self._d = self.get_parameter("d_thruster").value
        self._Xu_dot = self.get_parameter("Xu_dot").value
        self._Yv_dot = self.get_parameter("Yv_dot").value
        self._Yr_dot = self.get_parameter("Yr_dot").value
        self._Nv_dot = self.get_parameter("Nv_dot").value
        self._Nr_dot = self.get_parameter("Nr_dot").value
        self._Xu = self.get_parameter("Xu").value
        self._Yv = self.get_parameter("Yv").value
        self._Yr = self.get_parameter("Yr").value
        self._Nv = self.get_parameter("Nv").value
        self._Nr = self.get_parameter("Nr").value
        self._Xuu = self.get_parameter("Xuu").value
        self._Yvv = self.get_parameter("Yvv").value
        self._Yrr = self.get_parameter("Yrr").value
        self._Nvv = self.get_parameter("Nvv").value
        self._Nrr = self.get_parameter("Nrr").value

        self._sim_time = 0.0

    def _init_pubsub(self):
        # Subscribers for commands
        self._vel_sub = self.create_subscription(
            TwistStamped, "/mavros/mavros/cmd_vel", self._vel_callback, 10
        )
        self._rc_sub = self.create_subscription(
            OverrideRCIn, "/mavros/mavros/override", self._rc_callback, 10
        )

        # Publishers for simulated sensor data
        self._odom_pub = self.create_publisher(Odometry, "/mavros/mavros/odom", 10)
        self._imu_pub = self.create_publisher(Imu, "/mavros/mavros/data", 10)
        self._state_pub = self.create_publisher(MavrosState, "/mavros/state", 10)

    def _vel_callback(self, msg: TwistStamped):
        self._cmd_u = msg.twist.linear.x
        self._cmd_r = msg.twist.angular.z

        # Convert velocity command to approximate thrust (Scheme A simulation)
        # Simple P-controller emulating Pixhawk PID
        ku = 50.0  # N per m/s error
        kr = 30.0  # Nm per rad/s error
        thrust_x = ku * (self._cmd_u - self._u)
        thrust_n = kr * (self._cmd_r - self._r)
        # Distribute to left/right thrusters
        self._TL = 0.5 * thrust_x - 0.5 * thrust_n / max(self._d, 0.01)
        self._TR = 0.5 * thrust_x + 0.5 * thrust_n / max(self._d, 0.01)
        # Clamp (Relaxed limits for better tracking at high speeds)
        self._TL = max(-50.0, min(100.0, self._TL))
        self._TR = max(-50.0, min(100.0, self._TR))

    def _rc_callback(self, msg: OverrideRCIn):
        # PWM to thrust (Scheme B direct control)
        pwm_l = msg.channels[0]
        pwm_r = msg.channels[2]
        self._TL = self._pwm_to_thrust(pwm_l)
        self._TR = self._pwm_to_thrust(pwm_r)

    @staticmethod
    def _pwm_to_thrust(pwm: int) -> float:
        if pwm == 0:
            return 0.0
        if pwm >= 1500:
            return (pwm - 1500) / 500.0 * 100.0
        else:
            return (pwm - 1500) / 500.0 * 50.0

    def _simulation_step(self):
        """Integrate 6-DOF dynamics forward by dt using RK4."""
        state = np.array([self._x, self._y, self._psi, self._u, self._v, self._r])
        control = np.array([self._TL, self._TR])

        # --- RK4 integration ---
        def dynamics(s, ctrl):
            x_s, y_s, psi_s, u_s, v_s, r_s = s
            TL, TR = ctrl

            # Inertia matrix
            m11 = self._m - self._Xu_dot
            m22 = self._m - self._Yv_dot
            m23 = self._m * self._xg - self._Yr_dot
            m32 = self._m * self._xg - self._Nv_dot
            m33 = self._Iz - self._Nr_dot

            # C(nu)*nu
            c13 = -m22 * v_s - m23 * r_s
            c23 = m11 * u_s
            Cnu = np.array([c13 * r_s, c23 * r_s, -c13 * u_s - c23 * v_s])

            # D(nu)*nu
            d11 = -self._Xu - self._Xuu * abs(u_s)
            d22 = -self._Yv - self._Yvv * abs(v_s)
            d23 = -self._Yr - self._Yrr * abs(r_s)
            d32 = -self._Nv - self._Nvv * abs(v_s)
            d33 = -self._Nr - self._Nrr * abs(r_s)
            Dnu = np.array([
                d11 * u_s,
                d22 * v_s + d23 * r_s,
                d32 * v_s + d33 * r_s,
            ])

            # Thrust
            tau = np.array([TL + TR, 0.0, self._d * (TR - TL)])

            # dot_nu = M_inv * (tau - Cnu - Dnu)
            M = np.array([[m11, 0, 0], [0, m22, m23], [0, m32, m33]])
            M_inv = np.linalg.inv(M)
            nu_dot = M_inv @ (tau - Cnu - Dnu)

            # Kinematics
            cos_psi = math.cos(psi_s)
            sin_psi = math.sin(psi_s)
            eta_dot = np.array([
                u_s * cos_psi - v_s * sin_psi,
                u_s * sin_psi + v_s * cos_psi,
                r_s,
            ])

            return np.concatenate([eta_dot, nu_dot])

        # RK4
        h = self._dt
        k1 = dynamics(state, control)
        k2 = dynamics(state + h / 2 * k1, control)
        k3 = dynamics(state + h / 2 * k2, control)
        k4 = dynamics(state + h * k3, control)
        next_state = state + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)

        self._x, self._y, self._psi, self._u, self._v, self._r = next_state
        self._psi = math.atan2(math.sin(self._psi), math.cos(self._psi))
        self._sim_time += self._dt

        # Publish simulated data
        self._publish_odom()
        self._publish_imu()
        self._publish_state()

    def _publish_odom(self):
        msg = Odometry()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "map"
        msg.child_frame_id = "base_link"

        # Position with optional noise
        noise_pos = np.random.randn(3) * self._noise_pos if self._add_noise else np.zeros(3)
        msg.pose.pose.position.x = self._x + noise_pos[0]
        msg.pose.pose.position.y = self._y + noise_pos[1]
        msg.pose.pose.position.z = 0.0

        # Orientation as quaternion from yaw
        half_psi = self._psi / 2.0
        msg.pose.pose.orientation.z = math.sin(half_psi)
        msg.pose.pose.orientation.w = math.cos(half_psi)

        # Velocity with optional noise
        noise_vel = np.random.randn(3) * self._noise_vel if self._add_noise else np.zeros(3)
        msg.twist.twist.linear.x = self._u + noise_vel[0]
        msg.twist.twist.linear.y = self._v + noise_vel[1]
        msg.twist.twist.angular.z = self._r + noise_vel[2]

        # Covariance (simplified)
        for i in range(6):
            msg.twist.covariance[i * 7] = 0.01
            msg.pose.covariance[i * 7] = 0.01

        self._odom_pub.publish(msg)

    def _publish_imu(self):
        msg = Imu()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "base_link"

        noise = np.random.randn(3) * 0.001 if self._add_noise else np.zeros(3)
        msg.angular_velocity.z = self._r + noise[2]
        msg.linear_acceleration.x = 0.0 + noise[0]

        # Identity quaternion (orientation handled in odom)
        msg.orientation.w = 1.0

        for i in range(3):
            msg.angular_velocity_covariance[i * 4] = 0.001
            msg.linear_acceleration_covariance[i * 4] = 0.01

        self._imu_pub.publish(msg)

    def _publish_state(self):
        msg = MavrosState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.connected = True
        msg.armed = True
        msg.guided = True
        msg.mode = "GUIDED"
        msg.system_status = 4  # ACTIVE
        self._state_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = USVSimulator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
