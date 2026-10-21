#!/usr/bin/env python3
"""QoS 中继: MAVROS raw/fix (BEST_EFFORT) -> /fix_for_ntrip (RELIABLE)。
ntrip_client 的 fix 订阅无法通过参数覆盖 QoS (rclpy 需代码侧启用
qos_overriding_options), 故经此中继桥接。2026-10-09 RTK 修复引入。
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import NavSatFix


class FixQosRelay(Node):
    def __init__(self):
        super().__init__("fix_qos_relay")
        self.sub = self.create_subscription(
            NavSatFix, "/mavros/global_position/raw/fix",
            self.cb, qos_profile_sensor_data)
        self.pub = self.create_publisher(
            NavSatFix, "/fix_for_ntrip", 10)

    def cb(self, msg):
        self.pub.publish(msg)


def main():
    rclpy.init()
    node = FixQosRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
