"""MAVROS 动态流频配置节点单元测试"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest
import rclpy
from mavros_msgs.msg import State
from mavros_msgs.srv import MessageInterval

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from usv_bringup.mavros_rate_configurator import MavrosRateConfigurator, KNOWN_MSG_NAMES


@pytest.fixture(scope="module")
def rclpy_init():
    rclpy.init()
    yield
    rclpy.shutdown()


def test_mavros_rate_configurator_init(rclpy_init):
    node = MavrosRateConfigurator()
    assert node.target_rates == {
        30: 20.0, 27: 20.0, 105: 20.0, 32: 10.0, 33: 10.0, 36: 20.0, 65: 10.0,
    }
    assert node.max_retries == 5
    assert node.auto_reconfigure_on_reconnect is True
    assert node.fcu_connected is False
    assert node.is_configured is False
    node.destroy_node()


def test_fcu_connection_transition(rclpy_init):
    node = MavrosRateConfigurator()
    
    # 模拟飞控连接消息
    msg_connected = State()
    msg_connected.connected = True
    msg_connected.mode = "HOLD"
    msg_connected.armed = False

    node._on_state(msg_connected)
    assert node.fcu_connected is True
    assert node.pending_msgs == {30, 27, 105, 32, 33, 36, 65}
    assert node.is_configured is False

    # 模拟飞控断开
    msg_disconnected = State()
    msg_disconnected.connected = False
    node._on_state(msg_disconnected)
    assert node.fcu_connected is False
    assert node.is_configured is False

    node.destroy_node()


def test_retry_handling(rclpy_init):
    node = MavrosRateConfigurator()
    node.pending_msgs = {30}
    node.retry_counts = {30: 0}

    # 模拟一次失败
    node._handle_failure(30)
    assert node.retry_counts[30] == 1
    assert 30 in node.pending_msgs

    # 模拟达到最大重试次数
    node.retry_counts[30] = node.max_retries
    node.pending_msgs.clear()
    node._handle_failure(30)
    assert node.retry_counts[30] == node.max_retries + 1
    assert 30 not in node.pending_msgs  # 超出重试次数后不再重试

    node.destroy_node()


def test_known_msg_names():
    assert KNOWN_MSG_NAMES[30] == "ATTITUDE"
    assert KNOWN_MSG_NAMES[27] == "RAW_IMU"
    assert KNOWN_MSG_NAMES[105] == "HIGHRES_IMU"
    assert KNOWN_MSG_NAMES[32] == "LOCAL_POSITION_NED"
    assert KNOWN_MSG_NAMES[33] == "GLOBAL_POSITION_INT"
    assert KNOWN_MSG_NAMES[36] == "SERVO_OUTPUT_RAW"
    assert KNOWN_MSG_NAMES[65] == "RC_CHANNELS"
