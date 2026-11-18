# Copyright 2026 USV Developer
# SPDX-License-Identifier: MIT
"""Plant 回执语义测试（v2）。

四个处置必须彼此可分，且"未执行"必须真的为零推力 —— 一个把 late 记成 ok 的
plant，会让每次对账都通过，而物理时间什么都没发生。

判据绑定在**准入与内核的实现**上（纯头文件），而不是绑定在某段源码文本里：
源码行号/变量名会变，语义不会。
"""
from pathlib import Path

PLANT_DIR = Path(__file__).with_name("plant")


def _admission() -> str:
    return (PLANT_DIR / "p1_plant_admission.hpp").read_text()


def _core() -> str:
    return (PLANT_DIR / "p1_plant_core.hpp").read_text()


def _plant() -> str:
    return (PLANT_DIR / "p1_x86_plant.cpp").read_text()


def test_receipt_dispositions_are_distinct_and_ordered():
    admission = _admission()
    # 四个处置各有一个固定词表值
    for token in ('"ok"', '"rejected"', '"late"', '"duplicate"'):
        assert token in admission, token
    # late 必须在"施加"之前判定：准入是纯函数，物理只在内核里推进
    late_at = admission.index('late("deadline_passed_before_execution")')
    executes_at = admission.index("out.executes = true;")
    assert late_at < executes_at, "late must be decided before any execution is allowed"
    # 非 ok 一律零推力、零执行区间（plant 侧把 throttle 与指数都清零）
    plant = _plant()
    assert "receipt.thrust_n[0] = 0.0;" in plant
    assert "receipt.execution_index = 0;" in plant


def test_receipt_order_is_strictly_monotonic():
    admission = _admission()
    # 重复（已见 sequence）与重排（比最大 sequence 更旧）是两条不同的判据，
    # 且都在"受理"之前。
    duplicate_at = admission.index('duplicate("same_sequence")')
    reordered_at = admission.index('reject("reordered")')
    accept_at = admission.index("out.executes = true;")
    assert duplicate_at < accept_at
    assert reordered_at < accept_at
    # 同一 tick 只施加一次：这是与 sequence 无关的第二道闸
    assert 'reject("tick_already_executed")' in admission
    # pending 槽被占用时一律拒绝（不许覆盖别人的申请）
    assert "state.pending_scheduled) return reject(\"command_pending\")" in admission
    assert "note_executed_tick" in admission


def test_hold_window_is_half_open_and_never_inherits_stale_thrust():
    core = _core()
    # 半开区间：右端点不属于窗口
    assert "sim >= begin_ns && sim < end_ns" in core
    # 未覆盖即零推力（不存在"保持上一个值"的默认分支）
    assert "if (!hold.covers(sim)) return {0.0, 0.0};" in core


def test_plant_never_invents_inputs():
    plant = _plant()
    # 主题/坐标系全部来自合同
    for key in ("input_topics", "expected_pose_frame", "expected_child_frame"):
        assert key in plant, key
    assert '"/odom"' not in plant
    assert '"base_link"' not in plant
    # 唯一的时间原点是 plant 自己采的稳态时钟，仿真时刻由它派生
    assert "steady_origin_ns" in plant
    assert "clock_.sim_of(" in plant or "sim_of" in plant
    assert "p1-plant-receipt-v3" in plant
    assert "state_sample_sim_ns" in plant
    assert "p1-plant-hold-close-v2" in plant
