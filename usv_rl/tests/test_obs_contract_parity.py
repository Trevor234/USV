"""部署侧观测副本与 `usv_rl.observation` 的逐位等价性。

`ppo_proposal_node.py` 跑在 `/usr/bin/python3`（ROS 侧），不能 import `usv_rl`，
因此保留了一份 `compose_observation_scheme_a`/`advance_progress` 副本。本测试
按路径加载该脚本并逐位比较，防止两侧在通道语义/前瞻/进度门上分叉。
"""
from __future__ import annotations

import importlib.util
import math
import os
from pathlib import Path

import numpy as np
import pytest

from usv_rl.observation import (
    OBS_CONTRACT_VERSION as TRAIN_OBS_CONTRACT_VERSION,
    advance_progress,
    compose_observation,
)

SCHEME_A_LEARNING_DIR = Path(
    os.environ.get(
        "USV_SCHEME_A_LEARNING_DIR",
        "/home/trevor/usv_scheme_a_wt/research/scheme_a/learning",
    )
)

pytestmark = pytest.mark.skipif(
    not (SCHEME_A_LEARNING_DIR / "ppo_proposal_node.py").is_file(),
    reason=f"缺少方案 A 学习脚本目录: {SCHEME_A_LEARNING_DIR}",
)


def _load_node_module():
    import sys

    name = "scheme_a_ppo_proposal_node"
    path = SCHEME_A_LEARNING_DIR / "ppo_proposal_node.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass 解析字符串注解时要能从 sys.modules 找到模块，必须先注册
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


@pytest.fixture(scope="module")
def node():
    return _load_node_module()


def test_obs_contract_version_matches(node):
    assert node.OBS_CONTRACT_VERSION == TRAIN_OBS_CONTRACT_VERSION == "ppo-obs-v2"


def test_lookahead_tuple_matches_training_contract(node):
    from usv_rl.observation import LOOKAHEAD_M

    assert tuple(float(v) for v in node.DEFAULT_LOOKAHEAD) == tuple(float(v) for v in LOOKAHEAD_M)


def test_compose_observation_is_bitwise_identical(node):
    rng = np.random.default_rng(2024)
    n = 240
    xs = np.cumsum(rng.uniform(0.3, 0.7, n))
    ys = np.cumsum(rng.uniform(-0.2, 0.2, n))
    psis = np.arctan2(np.gradient(ys), np.gradient(xs))
    ss = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(xs), np.diff(ys)))])
    vs = rng.uniform(0.4, 0.9, n)
    rs = rng.uniform(-0.2, 0.2, n)
    kappas = np.divide(rs, np.maximum(np.abs(vs), 0.1))
    prev = np.array([5.0, -3.5])

    for k in range(50):
        prog_idx = int(rng.integers(1, n - 20))
        state = np.array([
            xs[prog_idx] + rng.uniform(-0.4, 0.4),
            ys[prog_idx] + rng.uniform(-0.4, 0.4),
            rng.uniform(-math.pi, math.pi),
            rng.uniform(0.2, 1.0),
            rng.uniform(-0.1, 0.1),
            rng.uniform(-0.2, 0.2),
        ])
        ref = compose_observation(
            state, xs, ys, psis, kappas, vs, rs, ss,
            prog_idx=prog_idx, prev_thrust=prev, lookahead=tuple(float(v) for v in node.DEFAULT_LOOKAHEAD),
        )
        local = node.compose_observation_scheme_a(
            state, xs, ys, psis, kappas, vs, rs, ss,
            prog_idx=prog_idx, prev_thrust=prev, lookahead=node.DEFAULT_LOOKAHEAD,
        )
        assert ref.dtype == local.dtype == np.float32
        assert local.shape == (43,)
        np.testing.assert_array_equal(local, ref)


def test_advance_progress_matches_including_gate(node):
    rng = np.random.default_rng(7)
    n = 200
    xs = np.arange(n, dtype=np.float64) * 0.5
    ys = np.zeros(n)
    for _ in range(40):
        prev_idx = int(rng.integers(0, n - 40))
        x = xs[prev_idx] + rng.uniform(-1.5, 6.0)
        y = rng.uniform(-1.5, 1.5)
        assert (
            node.advance_progress(xs, ys, x, y, prev_idx, window=8, gate_m=1.0)
            == advance_progress(xs, ys, x, y, prev_idx, window=8, gate_m=1.0)
        )
