"""Regression tests for the Scheme A VRX velocity inner loop."""

import math

from nav_msgs.msg import Odometry

from usv_simulation.cmdvel_to_thrust import CmdvelToThrust


def test_odometry_twist_is_consumed_in_child_frame():
    """A 90-degree pose must not rotate the already body-frame twist again."""
    controller = object.__new__(CmdvelToThrust)
    msg = Odometry()
    msg.header.frame_id = "map"
    msg.child_frame_id = "wamv/base_link"
    msg.pose.pose.orientation.z = math.sin(math.pi / 4.0)
    msg.pose.pose.orientation.w = math.cos(math.pi / 4.0)
    msg.twist.twist.linear.x = 1.25
    msg.twist.twist.linear.y = -0.30
    msg.twist.twist.angular.z = 0.18

    controller._odom_callback(msg)

    assert controller._u_meas == 1.25
    assert controller._r_meas == 0.18
