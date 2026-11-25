"""方案 A 机动生成器接入 usv_rl 的参考轨迹契约。

生成器本体在 `research/scheme_a/learning/maneuver_reference.py`（受控仿真场景
权威副本）。这里只验证解析与契约，不重复实现生成逻辑。
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from usv_rl.reference import (
    DEFAULT_SCHEME_A_LEARNING_DIR,
    MANEUVER_TYPES,
    SCHEME_A_LEARNING_DIR_ENV,
    make_maneuver_reference,
)

_LEARNING_DIR = Path(os.environ.get(SCHEME_A_LEARNING_DIR_ENV, DEFAULT_SCHEME_A_LEARNING_DIR))

pytestmark = pytest.mark.skipif(
    not (_LEARNING_DIR / "maneuver_reference.py").is_file(),
    reason=f"缺少方案 A 学习脚本目录: {_LEARNING_DIR}",
)


@pytest.mark.parametrize("maneuver", MANEUVER_TYPES)
def test_maneuver_reference_contract(maneuver: str):
    ref = make_maneuver_reference(maneuver, seconds=30.0, seed=3, cruise_speed=0.7)
    n = len(ref.xs)
    assert n >= 5
    assert ref.ys.shape == (n,) and ref.psis.shape == (n,)
    assert ref.kappas.shape == (n,) and ref.s.shape == (n,)
    assert ref.v_ref.shape == (n,) and ref.r_ref.shape == (n,) and ref.t.shape == (n,)
    assert np.all(np.isfinite(ref.xs)) and np.all(np.isfinite(ref.ys))
    assert float(np.min(ref.v_ref)) > 0.0, "参考速度必须为正（kappas = r/v 才有限）"
    assert np.all(np.diff(ref.s) >= 0.0), "弧长必须单调不减"
    assert np.all(np.diff(ref.t) > 0.0), "时间戳必须严格递增"
    assert np.all(np.isfinite(ref.kappas))


def test_maneuver_reference_is_deterministic():
    a = make_maneuver_reference("s_turn", seconds=20.0, seed=11, cruise_speed=0.66)
    b = make_maneuver_reference("s_turn", seconds=20.0, seed=11, cruise_speed=0.66)
    np.testing.assert_array_equal(a.xs, b.xs)
    np.testing.assert_array_equal(a.v_ref, b.v_ref)


def test_env_samples_scheme_a_mix():
    from usv_rl.envs import UsvTrackingEnv

    env = UsvTrackingEnv(path_type="scheme_a_mix", maneuver_seconds=20.0)
    env.reset(seed=17)
    assert len(env.reference.xs) > 5
    assert env.observation_space.shape == (43,)
