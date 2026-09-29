"""锁定 compose_observation 与 UsvTrackingEnv._get_obs 的等价性。

ROS 部署节点用 observation.py 组装观测；本测试保证它与训练环境
逐位一致（DR 噪声关闭时），防止训练/部署观测漂移。
"""
from __future__ import annotations

import numpy as np
import pytest

from usv_rl.envs import UsvTrackingEnv
from usv_rl.observation import advance_progress, compose_observation
from usv_rl.observation import apply_thrust_limits


def _reference_arrays(env: UsvTrackingEnv):
    ref = env.reference
    return (ref.xs, ref.ys, ref.psis, ref.kappas, ref.v_ref, ref.r_ref, ref.s, ref.t)


@pytest.mark.parametrize("path_type", ["straight", "arc", "zigzag", "random"])
def test_compose_observation_matches_env(path_type: str):
    env = UsvTrackingEnv(path_type=path_type)
    env.reset(seed=42)
    rng = np.random.default_rng(0)
    for step in range(40):
        env.step(env.action_space.sample()) if step else None
        # env._get_obs 与独立 compose 在同一状态下必须逐位一致
        obs_env = env._get_obs()
        xs, ys, psis, kappas, vs, rs, ss, ts = _reference_arrays(env)
        obs_compose = compose_observation(
            env.state, xs, ys, psis, kappas, vs, rs, ss, ts,
            t_now=env.step_count * env.dt,
            prog_idx=env.prog_idx,
            prev_thrust=env.prev_thrust,
            lookahead=env.lookahead,
        )
        np.testing.assert_array_equal(obs_env, obs_compose)
        # 推进进度搜索也必须一致
        env.prog_idx = advance_progress(xs, ys, env.state[0], env.state[1], env.prog_idx)
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


def test_thrust_limits_match_env_step():
    t_max, d_t_max, dt = 25.0, 80.0, 0.2
    prev = np.array([10.0, -10.0])
    # prev + 16N 会被 ±25 clamp 截断
    applied, _ = apply_thrust_limits(prev, np.array([100.0, -100.0]), t_max, d_t_max, dt)
    np.testing.assert_allclose(applied, [25.0, -25.0], atol=1e-12)
    applied2, _ = apply_thrust_limits(np.zeros(2), np.array([3.0, -4.0]), t_max, d_t_max, dt)
    np.testing.assert_allclose(applied2, [3.0, -4.0], atol=1e-12)
