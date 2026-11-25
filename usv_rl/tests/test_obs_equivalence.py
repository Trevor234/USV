"""锁定 compose_observation 与 UsvTrackingEnv._get_obs 的等价性。

ROS 部署节点与 `research/scheme_a/learning/ppo_proposal_node.py` 都按
`usv_rl.observation` 的语义组装观测；本测试保证训练环境**不重新内联实现**
（否则规则一改就分叉），并锁定进度搜索的两道门（窗口 + 距离）。
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from usv_rl.envs import UsvTrackingEnv
from usv_rl.observation import (
    PROGRESS_GATE_M,
    PROGRESS_WINDOW,
    advance_progress,
    apply_thrust_limits,
    compose_observation,
)


def _reference_arrays(env: UsvTrackingEnv):
    ref = env.reference
    return (ref.xs, ref.ys, ref.psis, ref.kappas, ref.v_ref, ref.r_ref, ref.s)


@pytest.mark.parametrize("path_type", ["arc", "zigzag", "random"])
def test_compose_observation_matches_env(path_type: str):
    env = UsvTrackingEnv(path_type=path_type)
    env.reset(seed=42)
    rng = np.random.default_rng(0)
    for step in range(30):
        env.step(env.action_space.sample()) if step else None
        # env._get_obs 必须就是按同一规则调用 compose_observation 的结果
        obs_env = env._get_obs()
        xs, ys, psis, kappas, vs, rs, ss = _reference_arrays(env)
        obs_compose = compose_observation(
            env.state, xs, ys, psis, kappas, vs, rs, ss,
            prog_idx=env.prog_idx,
            prev_thrust=env.prev_thrust,
            lookahead=env.lookahead,
        )
        np.testing.assert_array_equal(obs_env, obs_compose)
        # 推进进度搜索也必须一致（同窗口、同门限）
        env.prog_idx = advance_progress(
            xs, ys, env.state[0], env.state[1], env.prog_idx, gate_m=env.progress_gate_m
        )
        env.step(rng.uniform(-5, 5, 2))


def test_advance_progress_monotonic():
    env = UsvTrackingEnv(path_type="straight")
    env.reset(seed=1)
    xs, ys = env.reference.xs, env.reference.ys
    idx = 0
    last = -1
    for _ in range(100):
        env.step(np.array([15.0, 15.0]))
        idx = advance_progress(xs, ys, env.state[0], env.state[1], idx)
        assert idx >= last
        last = idx


def test_progress_window_blocks_jump():
    """瞬移到窗口外的路径点上（距离 0）也不能跳进度——否则近道直接记满进度。"""
    n = 200
    xs = np.arange(n, dtype=np.float64) * 0.5
    ys = np.zeros(n)
    prev_idx = 5
    far = prev_idx + 30
    assert far - prev_idx > PROGRESS_WINDOW
    got = advance_progress(xs, ys, float(xs[far]), float(ys[far]), prev_idx)
    assert got == prev_idx


def test_progress_gate_blocks_offpath():
    """窗口内的最近点仍远于门限时，进度保持不变（远离航线不算前进）。"""
    n = 200
    xs = np.arange(n, dtype=np.float64) * 0.5
    ys = np.zeros(n)
    prev_idx = 5
    x = float(xs[prev_idx + 2])
    y = PROGRESS_GATE_M + 0.5
    assert abs(y) > PROGRESS_GATE_M
    got = advance_progress(xs, ys, x, y, prev_idx)
    assert got == prev_idx


def test_schedule_channels_use_progress_index():
    """e_psi / v_ref / r_ref 必须取 prog_idx，不是时间索引。"""
    n = 30
    xs = np.arange(n, dtype=np.float64) * 0.5
    ys = np.zeros(n)
    psis = np.full(n, 0.0)
    kappas = np.zeros(n)
    vs = np.full(n, 0.7)
    rs = np.zeros(n)
    ss = xs.copy()
    prog_idx = 4
    # 进度索引的参考航向与大/小角度都不同：时间索引会给出另一套值
    psis[prog_idx] = 0.4
    vs[prog_idx] = 0.61
    rs[prog_idx] = 0.13
    state = np.array([0.0, 0.0, 0.1, 0.5, 0.0, 0.0])
    obs = compose_observation(
        state, xs, ys, psis, kappas, vs, rs, ss,
        prog_idx=prog_idx, prev_thrust=np.zeros(2), lookahead=(0.5,) * 8,
    )
    e_psi = math.atan2(math.sin(0.1 - psis[prog_idx]), math.cos(0.1 - psis[prog_idx]))
    assert obs[5] == pytest.approx(math.sin(e_psi), abs=1e-6)
    assert obs[6] == pytest.approx(math.cos(e_psi), abs=1e-6)
    assert obs[7] == pytest.approx(vs[prog_idx], abs=1e-6)
    assert obs[8] == pytest.approx(rs[prog_idx], abs=1e-6)


def test_thrust_limits_match_env_step():
    t_max, d_t_max, dt = 25.0, 80.0, 0.2
    prev = np.array([10.0, -10.0])
    applied, _ = apply_thrust_limits(prev, np.array([100.0, -100.0]), t_max, d_t_max, dt)
    np.testing.assert_allclose(applied, [25.0, -25.0], atol=1e-12)
    applied2, _ = apply_thrust_limits(np.zeros(2), np.array([3.0, -4.0]), t_max, d_t_max, dt)
    np.testing.assert_allclose(applied2, [3.0, -4.0], atol=1e-12)


def test_step_returned_obs_matches_compose_observation_under_post_update():
    env_pre = UsvTrackingEnv(
        path_type="zigzag",
        init_pos_noise=0.0, init_psi_noise=0.0, init_vel_noise=0.0,
        obs_prev_thrust_timing="pre_update",
    )
    env_post = UsvTrackingEnv(
        path_type="zigzag",
        init_pos_noise=0.0, init_psi_noise=0.0, init_vel_noise=0.0,
        obs_prev_thrust_timing="post_update",
    )
    env_pre.reset(seed=42)
    env_post.reset(seed=42)
    rng = np.random.default_rng(7)
    for k in range(15):
        action = rng.uniform(-0.8, 0.8, 2).astype(np.float32)
        obs_pre, rew_pre, term_pre, _, info_pre = env_pre.step(action)
        obs_post, rew_post, term_post, _, info_post = env_post.step(action)
        assert np.isclose(rew_pre, rew_post, atol=1e-12)
        assert term_pre == term_post
        xs, ys, psis, kappas, vs, rs, ss = _reference_arrays(env_post)
        expected_post = compose_observation(
            env_post.state, xs, ys, psis, kappas, vs, rs, ss,
            prog_idx=env_post.prog_idx,
            prev_thrust=info_post["applied_thrust"],
            lookahead=env_post.lookahead,
        )
        np.testing.assert_allclose(obs_post, expected_post, atol=1e-6)
        np.testing.assert_allclose(obs_post[-2:], info_post["applied_thrust"], atol=1e-5)
        if np.max(np.abs(info_pre["applied_thrust"])) > 1e-3 and k == 0:
            assert np.max(np.abs(obs_pre[-2:] - obs_post[-2:])) > 1e-3
        if term_post:
            break
