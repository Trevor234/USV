"""Bridge body-frame USV force commands to Gazebo Sim EntityWrench."""

import math
from typing import Optional

import rclpy
from geometry_msgs.msg import Wrench
from nav_msgs.msg import Odometry
from rclpy.node import Node
from ros_gz_interfaces.msg import Entity, EntityWrench


class CmdForceToEntityWrench(Node):
    """Convert /usv/cmd_force into /world/<world>/wrench for ApplyLinkWrench."""

    def __init__(self) -> None:
        super().__init__("cmd_force_to_entity_wrench")
        self.declare_parameter("cmd_force_topic", "/usv/cmd_force")
        self.declare_parameter("entity_wrench_topic", "/world/lake_gz/wrench")
        self.declare_parameter("entity_name", "usv_2m::base_link")
        self.declare_parameter("entity_type", int(Entity.LINK))
        self.declare_parameter("odom_topic", "/model/usv_2m/odometry")
        self.declare_parameter("use_body_frame", True)

        self._yaw: Optional[float] = None
        self._use_body_frame = bool(self.get_parameter("use_body_frame").value)
        self._entity_name = str(self.get_parameter("entity_name").value)
        self._entity_type = int(self.get_parameter("entity_type").value)

        self._pub = self.create_publisher(
            EntityWrench, self.get_parameter("entity_wrench_topic").value, 10
        )
        self._force_sub = self.create_subscription(
            Wrench,
            self.get_parameter("cmd_force_topic").value,
            self._force_callback,
            10,
        )
        self._odom_sub = self.create_subscription(
            Odometry,
            self.get_parameter("odom_topic").value,
            self._odom_callback,
            10,
        )
        self.get_logger().info(
            "cmd_force_to_entity_wrench ready: "
            f"{self.get_parameter('cmd_force_topic').value} -> "
            f"{self.get_parameter('entity_wrench_topic').value} "
            f"entity={self._entity_name}"
        )

    def _odom_callback(self, msg: Odometry) -> None:
        q = msg.pose.pose.orientation
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        self._yaw = math.atan2(siny_cosp, cosy_cosp)

    def _force_callback(self, msg: Wrench) -> None:
        out = EntityWrench()
        out.header.stamp = self.get_clock().now().to_msg()
        out.entity.name = self._entity_name
        out.entity.type = self._entity_type

        if self._use_body_frame and self._yaw is not None:
            c = math.cos(self._yaw)
            s = math.sin(self._yaw)
            out.wrench.force.x = c * msg.force.x - s * msg.force.y
            out.wrench.force.y = s * msg.force.x + c * msg.force.y
        else:
            out.wrench.force.x = msg.force.x
            out.wrench.force.y = msg.force.y
        out.wrench.force.z = msg.force.z

        out.wrench.torque.x = msg.torque.x
        out.wrench.torque.y = msg.torque.y
        out.wrench.torque.z = msg.torque.z
        self._pub.publish(out)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CmdForceToEntityWrench()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
