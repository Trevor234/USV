"""M1 门禁：Python dynamics.py 与 C++ usv_model_dynamic.cpp 轨迹对拍。

C++ 金标准由 tests/cpp_golden/dump_golden_trajectory.cpp 生成（确定性控制序列、
非零初值、200 步），CSV 首行记录所用 19 维水动力参数，Python 侧据此构造同参
模型，规避 C++ 头文件默认值与 YAML 辨识更新值不一致的问题。
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from usv_rl.dynamics import HydroParams, USVDynamicModel

GOLDEN_CSV = Path(__file__).parent / "cpp_golden" / "golden_trajectory.csv"

_PARAM_KEYS = [
    "mass", "Iz", "xg", "d_thruster",
    "Xu_dot", "Yv_dot", "Yr_dot", "Nv_dot", "Nr_dot",
    "Xu", "Yv", "Yr", "Nv", "Nr",
    "Xuu", "Yvv", "Yrr", "Nvv", "Nrr",
]


def _load_golden(path: Path):
    params_kwargs = {}
    rows = []
    for line in path.read_text().splitlines():
        if line.startswith("# params"):
            for tok in line[len("# params"):].split():
                k, v = tok.split("=")
                params_kwargs[k] = float(v)
        elif line.startswith("step,"):
            continue
        elif line.strip():
            parts = line.split(",")
            rows.append([float(v) for v in parts[1:]])
    assert set(params_kwargs) == set(_PARAM_KEYS), "CSV 参数头不完整"
    return params_kwargs, np.asarray(rows)


def test_golden_csv_exists():
    assert GOLDEN_CSV.exists(), "缺少金标准 CSV，先运行 tests/cpp_golden/build_golden.sh"


def test_dynamics_matches_cpp():
    params_kwargs, rows = _load_golden(GOLDEN_CSV)
    params = HydroParams(**params_kwargs)
    model = USVDynamicModel(dt=0.2, rk4_substeps=4, params=params)

    # 重建与 C++ 相同的确定性控制序列
    def control_at(k: int) -> np.ndarray:
        phase = k % 40
        if phase < 10:
            return np.array([10.0, 10.0])
        if phase < 20:
            return np.array([15.0, 5.0])
        if phase < 30:
            return np.array([-5.0, 8.0])
        if phase < 36:
            return np.array([0.0, 0.0])
        return np.array([22.0, -18.0])

    state = np.array([0.0, 0.0, 0.5, 0.3, 0.05, 0.1])
    for k, ref_row in enumerate(rows):
        # 对拍积分前状态（C++ 输出的是积分前状态）
        np.testing.assert_allclose(
            state, ref_row, atol=1e-8, rtol=1e-8,
            err_msg=f"step {k} 状态与 C++ 金标准不一致",
        )
        state = model.forward(state, control_at(k))


def test_sanity_zero_control_rest():
    """零控零速应保持静止（复刻 test_mpc_core.cpp sanity）。"""
    model = USVDynamicModel()
    state = np.zeros(6)
    for _ in range(50):
        state = model.forward(state, np.zeros(2))
    np.testing.assert_allclose(state, np.zeros(6), atol=1e-12)


def test_sanity_equal_thrust_no_yaw():
    """等推力直航：u_dot > 0 且 r_dot ≈ 0（复刻 test_mpc_core.cpp）。"""
    model = USVDynamicModel()
    state = np.zeros(6)
    nxt = model.forward(state, np.array([10.0, 10.0]))
    assert nxt[3] > 0.0
    # 左右对称 + xg 引起的弱耦合可忽略：r 增量应远小于 u 增量
    assert abs(nxt[5]) < 0.1 * nxt[3]


def test_sanity_differential_yaw():
    """差动推力应产生艏摇（复刻 test_mpc_core.cpp）。"""
    model = USVDynamicModel()
    nxt = model.forward(np.zeros(6), np.array([5.0, -5.0]))
    assert abs(nxt[5]) > 1e-3


def test_heading_normalization():
    """forward 后航向应归一化到 (-pi, pi]。"""
    model = USVDynamicModel()
    state = np.array([0.0, 0.0, 3.0, 0.5, 0.0, 1.5])
    for _ in range(20):
        state = model.forward(state, np.array([5.0, -5.0]))
        assert -math.pi < state[2] <= math.pi + 1e-12


def test_yaml_loader_matches_snapshot():
    """YAML 加载器应取到 usv_params_sim.yaml 的 2026-09-03 辨识值（而非 C++ 默认）。"""
    yaml_path = (
        Path(__file__).parents[2]
        / "usv_mpc_ws" / "src" / "usv_bringup" / "config" / "usv_params_sim.yaml"
    )
    if not yaml_path.exists():
        pytest.skip("usv_params_sim.yaml 不在仓库内")
    params = HydroParams.from_usv_params_yaml(str(yaml_path))
    assert params.Nr_dot == pytest.approx(-3.41)
    assert params.Nr == pytest.approx(-3.105)
    assert params.Nrr == pytest.approx(-0.71)
    assert params.mass == pytest.approx(14.2)
