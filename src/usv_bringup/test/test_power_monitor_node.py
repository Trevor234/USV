"""power_monitor_node 协议与换算单元测试。

CRC 期望值取自厂商参考实现
WeActStudio.PowerMonitorV1/Communication protocol/com_PowerMonitorMiniV1.py
的 calculate_crc8 输出 (设备固件的校验标准), 不是对本实现的自回归。
"""
import math
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from usv_bringup.power_monitor_node import (  # noqa: E402
    LIPO_CELL_SOC_TABLE,
    ProtocolError,
    PowerMonitorMini,
    compute_battery_percentage,
    crc8,
    decode_realtime,
    lipo_cell_fraction,
)


class FakeSerial:
    """内存串口: 预置应答字节流, 记录写出的请求帧。"""

    def __init__(self, responses, **kwargs):
        self.responses = bytearray(responses)
        self.written = []
        self.is_open = True

    def write(self, data):
        self.written.append(bytes(data))

    def read(self, n):
        out = bytes(self.responses[:n])
        del self.responses[:n]
        return out

    def reset_input_buffer(self):
        pass

    def close(self):
        self.is_open = False


def make_device(responses):
    factory = lambda **kwargs: FakeSerial(responses, **kwargs)  # noqa: E731
    return PowerMonitorMini("FAKE", 9600, min_query_interval=0.0,
                            serial_factory=factory)


def frame82(voltage_mv, current_01ma, power_mw):
    payload = struct.pack("<IiI", voltage_mv, current_01ma, power_mw)
    head = bytes([0x82]) + payload
    return head + bytes([crc8(head)])


# ―─ CRC8: 厂商实现给出的参考向量 ──────────────────────────────
@pytest.mark.parametrize("cmd,expected", [
    (0x82, 0xB4), (0x84, 0x12), (0x87, 0x41),
    (0x81, 0xE7), (0xC2, 0x89), (0xC3, 0xB8),
])
def test_crc8_request_vectors(cmd, expected):
    assert crc8(bytes([cmd])) == expected


def test_crc8_response_vectors():
    payload = struct.pack("<IiI", 11850, -1234, 5600)
    assert crc8(bytes([0x82]) + payload) == 0xF0
    assert crc8(bytes([0x84]) + struct.pack("<II", 12345, 67890)) == 0x56
    ident = b"WeAct Studio Power Monitor Mini V1"
    assert crc8(bytes([0x81, len(ident)]) + ident) == 0xEA


# ―─ 实时数据解码: 单位与电流符号 ──────────────────────────────
def test_decode_realtime_units_and_discharge_sign():
    # 设备电流正方向 = 输入→输出 (电池放电); BatteryState 约定放电为负。
    assert decode_realtime(
        struct.pack("<IiI", 11850, 1234, 5600)) == pytest.approx(
        (11.85, -0.1234, 5.6))
    _, charging, _ = decode_realtime(
        struct.pack("<IiI", 11850, -1234, 5600))
    assert charging == pytest.approx(0.1234)


# ―─ 请求-应答回路 (含帧格式) ──────────────────────────────────
def test_read_realtime_roundtrip_and_request_frame():
    dev = make_device(frame82(11850, 1234, 5600))
    assert dev.read_realtime() == pytest.approx((11.85, -0.1234, 5.6))
    assert dev.ser.written == [bytes([0x82, crc8(bytes([0x82]))])]


def test_variable_length_roundtrip():
    ident = b"WeAct Studio Power Monitor Mini V1"
    head = bytes([0x81, len(ident)]) + ident
    dev = make_device(head + bytes([crc8(head)]))
    assert dev.who_am_i() == "WeAct Studio Power Monitor Mini V1"


def test_corrupted_crc_raises():
    good = bytearray(frame82(11850, 1234, 5600))
    good[-1] ^= 0xFF
    with pytest.raises(ProtocolError):
        make_device(bytes(good)).read_realtime()


def test_wrong_response_cmd_raises():
    # 请求 0x82 却收到 0x84 的应答 → 必须报错, 不能错位解析。
    payload = struct.pack("<II", 12345, 67890)
    head = bytes([0x84]) + payload
    with pytest.raises(ProtocolError):
        make_device(head + bytes([crc8(head)])).read_realtime()


def test_short_response_times_out():
    with pytest.raises(ProtocolError):
        make_device(b"\x82\x2e").read_realtime()


def test_empty_response_times_out():
    with pytest.raises(ProtocolError):
        make_device(b"").read_realtime()


# ―─ LiPo SOC 估算 ────────────────────────────────────────────
def test_soc_table_is_monotonic_and_bounded():
    volts = [v for v, _ in LIPO_CELL_SOC_TABLE]
    fracs = [f for _, f in LIPO_CELL_SOC_TABLE]
    assert volts == sorted(set(volts))
    assert fracs == sorted(fracs)
    assert fracs[0] == 0.0 and fracs[-1] == 1.0


@pytest.mark.parametrize("per_cell,expected", [
    (4.5, 1.0), (4.2, 1.0), (3.3, 0.0), (3.0, 0.0),
])
def test_lipo_fraction_clamps(per_cell, expected):
    assert lipo_cell_fraction(per_cell) == expected


def test_lipo_fraction_interpolates():
    # 3.80→0.50 与 3.83→0.55 的中点。
    assert lipo_cell_fraction(3.815) == pytest.approx(0.525)
    # 3S 满电 12.6V → 单芯 4.2V。
    assert lipo_cell_fraction(12.6 / 3) == 1.0


# ―─ 总压区间与 SOC 综合换算 (6S 动力电池) ───────────────────────
@pytest.mark.parametrize("voltage,expected", [
    (29.0, 1.0),
    (25.0, 0.0),
    (27.0, 0.5),
    (28.0, 0.75),
    (30.0, 1.0),   # 高于满电截止压截断到 1.0
    (24.0, 0.0),   # 低于保护截止压截断到 0.0
])
def test_compute_battery_percentage_total_voltage_linear(voltage, expected):
    res = compute_battery_percentage(voltage, v_min=25.0, v_max=29.0, cell_count=6)
    assert res == pytest.approx(expected)


def test_compute_battery_percentage_fallback_to_cell_fraction():
    # 未配置总压区间时回退至单芯 SOC 表
    res = compute_battery_percentage(12.6, v_min=0.0, v_max=0.0, cell_count=3)
    assert res == pytest.approx(1.0)
    res_half = compute_battery_percentage(3.815 * 3, v_min=0.0, v_max=0.0, cell_count=3)
    assert res_half == pytest.approx(0.525)


def test_compute_battery_percentage_nan():
    # 电压为零或负数返回 NaN
    assert math.isnan(compute_battery_percentage(-1.0, v_min=25.0, v_max=29.0))
    assert math.isnan(compute_battery_percentage(0.0, v_min=25.0, v_max=29.0))
    # 未配置总压区间且 cell_count <= 0 返回 NaN
    assert math.isnan(compute_battery_percentage(27.0, v_min=0.0, v_max=0.0, cell_count=0))

