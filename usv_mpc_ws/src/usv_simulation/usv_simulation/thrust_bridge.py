"""USV thrust bridge — converts ArduPilot RC_OUT PWM to Gazebo force.

The ArduPilot SITL ↔ Gazebo integration uses two parallel paths:

  1. libArduPilotPlugin.so handles the JSON FDM exchange (sensors + propeller
     EFFORT for visual prop spin).
  2. This node listens to /mavros/rc/out (mavros_msgs/RCOut), reads the PWM
     of CH1 (ArduRover SERVO1 = ThrottleLeft) and CH2 (SERVO2 = ThrottleRight),
     normalizes them to [-1, 1], and publishes geometry_msgs/Wrench on
     /usv/cmd_force. The libgazebo_ros_force.so plugin in model.sdf consumes
     that Wrench and applies the actual surge force and yaw torque.

The split lets us use ArduPilot's Boat-mode mixing (throttle/steering →
left/right thrust) for free, while keeping the first Gazebo validation path
independent of optional VRX thrust plugins.

Topic params:
    rc_out_topic   default /mavros/rc/out
    force_topic    default /usv/cmd_force
    left_channel   default 0  (ArduRover SERVO1 → RCOut.channels[0])
    right_channel  default 1  (ArduRover SERVO2 → RCOut.channels[1])
    pwm_min        default 1100
    pwm_center     default 1500
    pwm_max        default 1900
    deadband_us    default 25  (ignore commands within ±25us of center)
"""

import rclpy
from geometry_msgs.msg import Wrench
from rclpy.node import Node

try:
    from mavros_msgs.msg import RCOut
except ImportError:  # pragma: no cover — only at lint time without mavros
    RCOut = None


def _normalize(pwm: int, pwm_min: int, pwm_center: int, pwm_max: int,
               deadband: int) -> float:
    """Map PWM (us) into [-1, 1] with a small deadband around center."""
    if pwm <= 0:
        return 0.0
    if abs(pwm - pwm_center) <= deadband:
        return 0.0
    if pwm >= pwm_center:
        denom = max(pwm_max - pwm_center, 1)
        return min((pwm - pwm_center) / denom, 1.0)
    denom = max(pwm_center - pwm_min, 1)
    return max((pwm - pwm_center) / denom, -1.0)


class UsvThrustBridge(Node):
    def __init__(self) -> None:
        super().__init__("usv_thrust_bridge")

        self.declare_parameter("rc_out_topic", "/mavros/rc/out")
        self.declare_parameter("force_topic", "/usv/cmd_force")
        self.declare_parameter("left_channel", 0)
        self.declare_parameter("right_channel", 1)
        self.declare_parameter("pwm_min", 1100)
        self.declare_parameter("pwm_center", 1500)
        self.declare_parameter("pwm_max", 1900)
        self.declare_parameter("deadband_us", 25)

        self._left_ch = int(self.get_parameter("left_channel").value)
        self._right_ch = int(self.get_parameter("right_channel").value)
        self._pwm_min = int(self.get_parameter("pwm_min").value)
        self._pwm_center = int(self.get_parameter("pwm_center").value)
        self._pwm_max = int(self.get_parameter("pwm_max").value)
        self._deadband = int(self.get_parameter("deadband_us").value)

        if RCOut is None:
            self.get_logger().error(
                "mavros_msgs.msg.RCOut import failed — install ros-humble-mavros-msgs."
            )
            raise SystemExit(1)

        self._force_pub = self.create_publisher(
            Wrench, self.get_parameter("force_topic").value, 10
        )
        self._sub = self.create_subscription(
            RCOut,
            self.get_parameter("rc_out_topic").value,
            self._rc_callback,
            10,
        )

        self._frames_seen = 0
        self.get_logger().info(
            f"usv_thrust_bridge ready (Fallback Mode): rc_out={self.get_parameter('rc_out_topic').value} "
            f"→ Wrench on {self.get_parameter('force_topic').value}"
        )

    def _rc_callback(self, msg) -> None:
        if msg.channels is None or len(msg.channels) == 0:
            return
        if self._left_ch >= len(msg.channels) or self._right_ch >= len(msg.channels):
            return

        left_pwm = msg.channels[self._left_ch]
        right_pwm = msg.channels[self._right_ch]

        left = _normalize(
            left_pwm, self._pwm_min, self._pwm_center, self._pwm_max, self._deadband
        )
        right = _normalize(
            right_pwm, self._pwm_min, self._pwm_center, self._pwm_max, self._deadband
        )

        # Calculate force and torque (max force 40 N per thruster, arm 0.3 m)
        max_force = 40.0
        arm_y = 0.3
        
        force_x = (left + right) * max_force
        torque_z = (right - left) * max_force * arm_y

        msg_wrench = Wrench()
        msg_wrench.force.x = float(force_x)
        msg_wrench.torque.z = float(torque_z)
        self._force_pub.publish(msg_wrench)

        self._frames_seen += 1
        if self._frames_seen % 100 == 0:
            self.get_logger().info(
                f"PWM L={left_pwm} R={right_pwm}  →  cmd L={left:+.3f} R={right:+.3f}"
            )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = UsvThrustBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
