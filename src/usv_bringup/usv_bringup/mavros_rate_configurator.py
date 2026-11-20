#!/usr/bin/env python3
"""MAVROS 动态消息流频配置节点 (MAVLink Message Interval Configurator)

通过 ROS 2 服务 /mavros/set_message_interval (底层基于 MAV_CMD_SET_MESSAGE_INTERVAL)
动态配置飞控 MAVLink 遥测消息的发送频率，确保实船 MPC 与状态估计获得满足要求的 IMU 与里程计流频。

特性：
- 自动侦测飞控连接状态 (监听 /mavros/state)；
- 飞控上线/重连自动触发流频配置，解决断电重启后流频复位问题；
- 异步非阻塞调用，支持独立超时与重试预算；
- 容错保护：单条消息配置失败绝不阻塞系统运行与 MPC 启动。
"""

import time
from typing import Dict, List, Optional, Set

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from mavros_msgs.msg import State
from mavros_msgs.srv import MessageInterval

# 常用 MAVLink 消息 ID 可读名称映射
KNOWN_MSG_NAMES: Dict[int, str] = {
    27: "RAW_IMU",
    30: "ATTITUDE",
    32: "LOCAL_POSITION_NED",
    33: "GLOBAL_POSITION_INT",
    36: "SERVO_OUTPUT_RAW",
    65: "RC_CHANNELS",
    102: "SCALED_IMU",
    105: "HIGHRES_IMU",
    147: "BATTERY_STATUS",
}


class MavrosRateConfigurator(Node):
    """动态配置 MAVLink 遥测流频的 ROS 2 节点。"""

    def __init__(self) -> None:
        super().__init__("mavros_rate_configurator")

        # 声明参数
        self.declare_parameter("message_ids", [30, 27, 105, 32, 33, 36, 65])
        self.declare_parameter("message_rates", [20.0, 20.0, 20.0, 10.0, 10.0, 20.0, 10.0])
        self.declare_parameter("max_retries", 5)
        self.declare_parameter("retry_interval_sec", 1.0)
        self.declare_parameter("service_timeout_sec", 3.0)
        self.declare_parameter("auto_reconfigure_on_reconnect", True)

        # 获取参数
        raw_ids: List[int] = self.get_parameter("message_ids").value
        raw_rates: List[float] = [
            float(r) for r in self.get_parameter("message_rates").value
        ]
        self.max_retries: int = int(self.get_parameter("max_retries").value)
        self.retry_interval_sec: float = float(
            self.get_parameter("retry_interval_sec").value
        )
        self.service_timeout_sec: float = float(
            self.get_parameter("service_timeout_sec").value
        )
        self.auto_reconfigure_on_reconnect: bool = bool(
            self.get_parameter("auto_reconfigure_on_reconnect").value
        )

        if len(raw_ids) != len(raw_rates):
            self.get_logger().error(
                f"message_ids count ({len(raw_ids)}) does not match "
                f"message_rates count ({len(raw_rates)})! Using pairwise zip."
            )

        # 目标配置字典: msg_id -> target_rate (Hz)
        self.target_rates: Dict[int, float] = dict(zip(raw_ids, raw_rates))
        self.get_logger().info(
            f"Configured target message rates: {self._format_targets(self.target_rates)}"
        )

        # 状态机成员变量
        self.fcu_connected: bool = False
        self.is_configured: bool = False
        self.pending_msgs: Set[int] = set()
        self.retry_counts: Dict[int, int] = {}
        self.active_futures: Dict[int, tuple] = {}  # msg_id -> (future, start_time)

        # 服务客户端: /mavros/set_message_interval
        self.srv_client = self.create_client(
            MessageInterval, "/mavros/set_message_interval"
        )

        # 订阅 /mavros/state (TRANSIENT_LOCAL 确保可接收最新状态)
        state_qos = QoSProfile(
            depth=10,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.state_sub = self.create_subscription(
            State, "/mavros/state", self._on_state, state_qos
        )

        # 周期管理定时器 (0.5s 周期，处理服务调用与重试状态机)
        self.timer = self.create_timer(0.5, self._timer_callback)
        self.get_logger().info("MavrosRateConfigurator initialized and waiting for FCU...")

    def _format_targets(self, targets: Dict[int, float]) -> str:
        items = []
        for mid, rate in targets.items():
            name = KNOWN_MSG_NAMES.get(mid, f"MSG_{mid}")
            items.append(f"{name}(#{mid})={rate}Hz")
        return ", ".join(items)

    def _on_state(self, msg: State) -> None:
        """飞控连接状态回调。"""
        new_connected = bool(msg.connected)

        if new_connected and not self.fcu_connected:
            self.get_logger().info(
                f"FCU connected (mode: {msg.mode}, armed: {msg.armed})! "
                "Triggering message rate configuration..."
            )
            self._trigger_configuration()
        elif not new_connected and self.fcu_connected:
            self.get_logger().warn("FCU connection lost!")
            if self.auto_reconfigure_on_reconnect:
                self.is_configured = False
                self.active_futures.clear()

        self.fcu_connected = new_connected

    def _trigger_configuration(self) -> None:
        """重置待配置集合与重试计数，启动配置流程。"""
        self.pending_msgs = set(self.target_rates.keys())
        self.retry_counts = {mid: 0 for mid in self.target_rates.keys()}
        self.active_futures.clear()
        self.is_configured = False

    def _timer_callback(self) -> None:
        """状态机定时轮询：服务就绪检查、异步调用发起、超时与重试维护。"""
        if not self.fcu_connected:
            return

        if self.is_configured:
            return

        if not self.srv_client.service_is_ready():
            self.get_logger().debug(
                "Waiting for /mavros/set_message_interval service to become available..."
            )
            return

        now = time.time()

        # 1. 检查已发出的请求是否超时
        timed_out_ids = []
        for mid, (future, start_time) in list(self.active_futures.items()):
            if not future.done():
                if now - start_time > self.service_timeout_sec:
                    name = KNOWN_MSG_NAMES.get(mid, f"MSG_{mid}")
                    self.get_logger().warn(
                        f"Request for {name} (#{mid}) timed out after {self.service_timeout_sec}s."
                    )
                    timed_out_ids.append(mid)

        for mid in timed_out_ids:
            self.active_futures.pop(mid, None)
            self.retry_counts[mid] = self.retry_counts.get(mid, 0) + 1
            if self.retry_counts[mid] <= self.max_retries:
                self.pending_msgs.add(mid)
            else:
                name = KNOWN_MSG_NAMES.get(mid, f"MSG_{mid}")
                self.get_logger().error(
                    f"Exceeded max retries ({self.max_retries}) for {name} (#{mid}). Skipping."
                )

        # 2. 对尚在 pending 且无活跃异步调用的消息发起请求
        for mid in list(self.pending_msgs):
            if mid in self.active_futures:
                continue

            rate = self.target_rates[mid]
            name = KNOWN_MSG_NAMES.get(mid, f"MSG_{mid}")

            req = MessageInterval.Request()
            req.message_id = mid
            req.message_rate = rate

            self.get_logger().info(
                f"Sending request: set {name} (#{mid}) to {rate} Hz "
                f"(attempt {self.retry_counts.get(mid, 0) + 1}/{self.max_retries + 1})..."
            )
            future = self.srv_client.call_async(req)
            self.active_futures[mid] = (future, now)
            self.pending_msgs.remove(mid)

            # 绑定完成回调
            future.add_done_callback(
                lambda fut, m=mid, r=rate: self._on_service_result(m, r, fut)
            )

        # 3. 检查是否全部已完成
        if not self.pending_msgs and not self.active_futures:
            self.is_configured = True
            success_count = sum(
                1 for mid, cnt in self.retry_counts.items() if cnt <= self.max_retries
            )
            total_count = len(self.target_rates)
            self.get_logger().info(
                f"MAVLink message rate configuration finished: "
                f"{success_count}/{total_count} streams configured successfully."
            )

    def _on_service_result(self, mid: int, rate: float, future) -> None:
        """异步服务响应回调。"""
        self.active_futures.pop(mid, None)
        name = KNOWN_MSG_NAMES.get(mid, f"MSG_{mid}")

        try:
            res = future.result()
            if res.success:
                self.get_logger().info(
                    f"Set {name} (#{mid}) to {rate} Hz: SUCCESS"
                )
            else:
                self.get_logger().warn(
                    f"FCU rejected interval setting for {name} (#{mid}) (success=False)."
                )
                self._handle_failure(mid)
        except Exception as e:
            self.get_logger().error(
                f"Exception calling /mavros/set_message_interval for {name} (#{mid}): {e}"
            )
            self._handle_failure(mid)

    def _handle_failure(self, mid: int) -> None:
        """处理调用失败与重试预算。"""
        self.retry_counts[mid] = self.retry_counts.get(mid, 0) + 1
        name = KNOWN_MSG_NAMES.get(mid, f"MSG_{mid}")
        if self.retry_counts[mid] <= self.max_retries:
            self.get_logger().info(
                f"Scheduling retry for {name} (#{mid}) in {self.retry_interval_sec}s "
                f"({self.retry_counts[mid]}/{self.max_retries})..."
            )
            self.pending_msgs.add(mid)
        else:
            self.get_logger().error(
                f"Exceeded max retries ({self.max_retries}) for {name} (#{mid}). Giving up."
            )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MavrosRateConfigurator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
