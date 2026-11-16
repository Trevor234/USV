#!/usr/bin/env python3
"""WeAct PowerMonitorMini V1 电池驱动: Pi GPIO UART 直读 → /usv/battery。

硬件接线 (Pi 5, 40-pin 排针):
  /boot/firmware/config.txt 增加一行 `dtoverlay=uart4-pi5` 后重启
  (启用 GPIO12/13 上的 RP1 UART4 → /dev/ttyAMA4):
    Pi GPIO12 (pin 32, TXD4) → 功率计 4 针口 RX
    Pi GPIO13 (pin 33, RXD4) → 功率计 4 针口 TX   (交叉接线, 3.3V TTL)
    Pi GND    (pin 34)       → 功率计 GND         (必须共地)
  GPIO14/15 (/dev/ttyAMA10) 已被 MAVROS/飞控独占, 不可复用。
  设备 UART 波特率由其设置菜单 Baudrate 决定 (出厂默认 9600), USB CDC 口
  不适用本驱动。

协议 (Communication protocol v1.3, UART 通道):
  读命令 [cmd|0x80, CRC8]; 定长应答 [cmd|0x80, data..., CRC8];
  变长应答 [cmd|0x80, len, data..., CRC8]。CRC8 多项式 0x31、初值 0xFF、
  逐位计算, 覆盖除末字节外全部字节; 多字节数字小端。
    0x82 实时: 电压 mV (u32) / 电流 0.1mA (i32) / 功率 mW (u32)
    0x84 电量: mAh (u32) / mWh (u32) — 自设备上次清零起累计
    0x87 输入类型: 1B (0/4 初始化, 1 PD, 2 QC, 3 DC)
  固件 50ms 刷新一轮, 相邻查询间隔不得小于 50ms (本驱动强制 ≥55ms)。

发布 (sensor-data QoS, 供 mode_manager 低电量 failsafe 消费):
  voltage = 功率计实测电压; current 放电为负 (BatteryState 约定,
  设备电流正方向是输入→输出, 即放电); percentage 优先按配置的 [v_min, v_max]
  总压区间线性映射 (如 6S 动力电池 25.0V~29.0V), 或回退由 LiPo 单芯开路电压表插值估算;
  低电量判据仍以 usv_safety 的绝对电压阈值为准;
  功率 = voltage × current, 消费方可自行计算; 驱动只轮询 0x82 实时数据,
  mAh/mWh 累计与输入类型需深度分析时用厂商 GUI (USB 口可与 UART 并用)。
"""
import struct
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import BatteryState

try:
    import serial
except ImportError as _exc:  # pragma: no cover - 缺依赖时给出可操作提示
    raise SystemExit(
        "power_monitor_node 需要 pyserial: sudo apt install python3-serial"
    ) from _exc


class ProtocolError(Exception):
    """串口应答超时 / 命令字节不符 / CRC 校验失败。"""


# LiPo 单芯开路电压 → SOC 表 (电压 V, 分数 0-1), 两列均单调递增。
LIPO_CELL_SOC_TABLE = (
    (3.30, 0.00), (3.58, 0.05), (3.62, 0.10), (3.65, 0.15), (3.68, 0.20),
    (3.70, 0.25), (3.72, 0.30), (3.74, 0.35), (3.76, 0.40), (3.78, 0.45),
    (3.80, 0.50), (3.83, 0.55), (3.86, 0.60), (3.89, 0.65), (3.92, 0.70),
    (3.96, 0.75), (4.00, 0.80), (4.05, 0.85), (4.10, 0.90), (4.15, 0.95),
    (4.20, 1.00),
)


def crc8(data):
    """CRC-8: 多项式 0x31, 初值 0xFF, 逐位计算 (UART 通道帧尾校验)。"""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) if (crc & 0x80) else (crc << 1)
            crc &= 0xFF
    return crc


def lipo_cell_fraction(v_per_cell):
    """单芯电压 → SOC 分数; 表内线性插值, 表外截断到 [0, 1]。"""
    table = LIPO_CELL_SOC_TABLE
    if v_per_cell <= table[0][0]:
        return 0.0
    if v_per_cell >= table[-1][0]:
        return 1.0
    for (v0, f0), (v1, f1) in zip(table, table[1:]):
        if v_per_cell <= v1:
            return f0 + (f1 - f0) * (v_per_cell - v0) / (v1 - v0)
    return 1.0  # pragma: no cover — 表单调递增, 上面的分支必然命中


def compute_battery_percentage(voltage_v, v_min=0.0, v_max=0.0, cell_count=0):
    """计算电池百分比 (0.0~1.0 或 NaN)。

    优先使用 [v_min, v_max] 总压区间线性映射 (如 6S 动力电池 25.0V~29.0V);
    若未显式配置总压区间 (v_max <= v_min 或 <= 0) 且 cell_count > 0,
    则回退至 LiPo 单芯开路电压表插值。
    """
    if voltage_v <= 0.0:
        return float("nan")
    if v_max > v_min > 0.0:
        frac = (voltage_v - v_min) / (v_max - v_min)
        return min(max(frac, 0.0), 1.0)
    if cell_count > 0:
        return lipo_cell_fraction(voltage_v / cell_count)
    return float("nan")


def decode_realtime(payload):
    """0x82 应答 12B → (电压 V, 电流 A [放电为负], 功率 W)。

    设备电流单位 0.1mA, 正方向为输入→输出 (对电池即放电);
    BatteryState 约定放电为负, 故取反。
    """
    voltage_mv, current_01ma, power_mw = struct.unpack("<IiI", payload)
    return voltage_mv / 1000.0, -current_01ma / 10000.0, power_mw / 1000.0


class PowerMonitorMini:
    """WeAct PowerMonitorMini V1 同步请求-应答协议客户端 (UART 通道)。

    与厂商 com_PowerMonitorMiniV1.py 的差异: 无后台线程/队列, 一问一答,
    供 ROS 定时器低频轮询; 每次请求前清空输入缓冲并强制查询间隔 ≥50ms。
    """

    def __init__(self, port, baudrate, timeout=0.3, min_query_interval=0.055,
                 serial_factory=None):
        self._min_query_interval = min_query_interval
        self._last_cmd_time = 0.0
        self._serial_factory = serial_factory or serial.Serial
        self.ser = self._serial_factory(port=port, baudrate=baudrate,
                                        timeout=timeout)

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    def _throttle(self):
        """相邻查询间隔 ≥ min_query_interval (固件 50ms 刷新一轮)。"""
        wait = self._min_query_interval - (time.monotonic() - self._last_cmd_time)
        if wait > 0:
            time.sleep(wait)
        self._last_cmd_time = time.monotonic()

    def _read_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.ser.read(n - len(buf))
            if not chunk:
                raise ProtocolError(
                    f"读串口超时: 需要 {n} B, 只收到 {len(buf)} B")
            buf += chunk
        return bytes(buf)

    @staticmethod
    def _check_frame(raw, cmd):
        """校验 [cmd|0x80, ..., CRC8] 帧头与帧尾, 返回除 cmd/CRC 外的数据。"""
        if raw[0] != (cmd | 0x80) & 0xFF:
            raise ProtocolError(
                f"应答命令字节不符: 0x{raw[0]:02X} (期望 0x{cmd | 0x80:02X})")
        if crc8(raw[:-1]) != raw[-1]:
            raise ProtocolError(
                f"CRC 校验失败: 收到 0x{raw[-1]:02X}, 计算 0x{crc8(raw[:-1]):02X}")
        return raw[1:-1]

    def _request_fixed(self, cmd, data_len):
        """定长应答: [cmd|0x80, data(data_len), CRC8]。"""
        self._throttle()
        self.ser.reset_input_buffer()
        frame = bytes((cmd | 0x80,))
        self.ser.write(frame + bytes((crc8(frame),)))
        return self._check_frame(self._read_exact(2 + data_len), cmd)

    def _request_variable(self, cmd):
        """变长应答: [cmd|0x80, len, data(len), CRC8]。"""
        self._throttle()
        self.ser.reset_input_buffer()
        frame = bytes((cmd | 0x80,))
        self.ser.write(frame + bytes((crc8(frame),)))
        head = self._read_exact(2)
        raw = head + self._read_exact(head[1] + 1)
        return self._check_frame(raw, cmd)[1:]  # 再去掉 len 字节

    def read_realtime(self):
        """0x82: (电压 V, 电流 A [放电为负], 功率 W)。"""
        return decode_realtime(self._request_fixed(0x02, 12))

    def who_am_i(self):
        return self._request_variable(0x01).decode("utf-8", "replace")

    def system_version(self):
        return self._request_variable(0x42).decode("utf-8", "replace")

    def serial_number(self):
        return self._request_variable(0x43).decode("ascii", "replace")


class PowerMonitorNode(Node):
    """轮询功率计并发布 BatteryState; 串口断开/失败自动重连。"""

    def __init__(self):
        super().__init__("power_monitor_node")
        self.declare_parameter("port", "/dev/ttyAMA4")
        self.declare_parameter("baudrate", 9600)
        self.declare_parameter("poll_rate", 2.0)
        self.declare_parameter("battery_topic", "/usv/battery")
        self.declare_parameter("frame_id", "base_link")
        self.declare_parameter("cell_count", 3)
        self.declare_parameter("v_min", 0.0)
        self.declare_parameter("v_max", 0.0)
        self.declare_parameter("design_capacity_ah", 0.0)
        self.declare_parameter("reconnect_interval_s", 5.0)

        self._port = self.get_parameter("port").value
        self._baudrate = int(self.get_parameter("baudrate").value)
        rate = float(self.get_parameter("poll_rate").value)
        if not 0.0 < rate <= 20.0:  # 固件 50ms 刷新 → 上限 20Hz
            rate = min(max(rate, 0.1), 20.0)
            self.get_logger().warn(f"poll_rate 越界, 截断为 {rate} Hz")
        self._cell_count = int(self.get_parameter("cell_count").value)
        self._v_min = float(self.get_parameter("v_min").value)
        self._v_max = float(self.get_parameter("v_max").value)
        self._capacity_ah = float(self.get_parameter("design_capacity_ah").value)
        self._reconnect_interval = float(
            self.get_parameter("reconnect_interval_s").value)
        self._frame_id = self.get_parameter("frame_id").value

        topic = self.get_parameter("battery_topic").value
        self._pub = self.create_publisher(BatteryState, topic,
                                          qos_profile_sensor_data)

        self._dev = None
        self._last_connect_attempt = 0.0
        self._error_count = 0
        self._serial_number = ""

        self._timer = self.create_timer(1.0 / rate, self._poll)
        self.get_logger().info(
            f"功率计驱动就绪: {self._port}@{self._baudrate}, "
            f"{rate:g}Hz 轮询 → {topic}")

    def close(self):
        if self._dev is not None:
            self._dev.close()
            self._dev = None

    # ―─ 轮询主循环 ───────────────────────────────────────────
    def _poll(self):
        try:
            if self._dev is None:
                self._try_connect()
            else:
                self._poll_once()
        except serial.SerialException as exc:
            self._on_link_failure(f"串口异常: {exc}")
        except ProtocolError as exc:
            self._error_count += 1
            if self._error_count == 1 or self._error_count % 25 == 0:
                self.get_logger().warn(
                    f"协议错误 (连续第 {self._error_count} 次): {exc}")
            if self._error_count >= 10:
                self._on_link_failure(
                    f"连续 {self._error_count} 次协议错误, 重开串口")
        except Exception as exc:  # 防御: 定时器回调异常不得杀死 spin
            self.get_logger().error(f"轮询意外异常: {exc!r}")

    def _try_connect(self):
        now = time.monotonic()
        if now - self._last_connect_attempt < self._reconnect_interval:
            return
        self._last_connect_attempt = now
        try:
            dev = PowerMonitorMini(self._port, self._baudrate)
        except (serial.SerialException, OSError) as exc:
            self.get_logger().warn(f"打开 {self._port} 失败: {exc}")
            return
        self._dev = dev
        self._error_count = 0
        identity = []
        for label, reader, store in (
                ("who_am_i", dev.who_am_i, False),
                ("固件版本", dev.system_version, False),
                ("S/N", dev.serial_number, True)):
            try:
                value = reader()
                identity.append(f"{label}={value}")
                if store:
                    self._serial_number = value
            except Exception as exc:
                identity.append(f"{label}=读取失败({exc})")
        self.get_logger().info("已连接 WeAct 功率计: " + ", ".join(identity))

    def _on_link_failure(self, reason):
        self.get_logger().warn(
            f"{reason}; 每 {self._reconnect_interval:g}s 重试")
        self.close()
        self._error_count = 0

    def _poll_once(self):
        voltage_v, current_a, _power_w = self._dev.read_realtime()
        self._publish(voltage_v, current_a)
        self._error_count = 0

    def _publish(self, voltage_v, current_a):
        msg = BatteryState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self._frame_id
        msg.voltage = voltage_v
        msg.current = current_a
        msg.power_supply_technology = BatteryState.POWER_SUPPLY_TECHNOLOGY_LIPO
        msg.power_supply_health = BatteryState.POWER_SUPPLY_HEALTH_UNKNOWN
        msg.present = True
        msg.location = "weact_power_monitor"
        msg.serial_number = self._serial_number
        # Jazzy 的 float 字段默认 0.0, 未知量必须显式置 NaN,
        # 否则消费方无法区分 "未知" 与 "恰好为 0"。
        msg.temperature = float("nan")
        msg.charge = float("nan")  # mAh 计数是自清零起累计值, 非绝对剩电量
        if self._capacity_ah > 0.0:
            msg.capacity = self._capacity_ah
            msg.design_capacity = self._capacity_ah
        else:
            msg.capacity = float("nan")
            msg.design_capacity = float("nan")
        msg.percentage = compute_battery_percentage(
            voltage_v, self._v_min, self._v_max, self._cell_count
        )

        # 电流状态: BatteryState 约定放电为负; |I| < 50mA 视为静置。
        if current_a < -0.05:
            msg.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
        elif current_a > 0.05:
            msg.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_CHARGING
        else:
            msg.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_NOT_CHARGING
        self._pub.publish(msg)


def main():
    rclpy.init()
    node = PowerMonitorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
