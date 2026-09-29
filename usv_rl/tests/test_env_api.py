"""Gymnasium API 与环境行为测试。"""
from __future__ import annotations

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from usv_rl.baselines import LosController
from usv_rl.envs import _ENV_ID, UsvTrackingEnv
from usv_rl.envs.usv_tracking_env import DEFAULT_LOOKAHEAD


@pytest.fixture
def env() -> UsvTrackingEnv:
    return UsvTrackingEnv(path_type="straight")


def test_gymnasium_check_env(env):
    check_env(env, skip_render_check=True)


def test_spaces(env):
    n_look = len(DEFAULT_LOOKAHEAD)
    # [u,v,r] + [sin,cos psi] + [sin,cos e_psi] + [v_ref,r_ref] + K×4 + [TL,TR]_prev
    assert env.observation_space.shape == (3 + 2 + 2 + 2 + 4 * n_look + 2,)
    assert env.action_space.shape == (2,)
    assert env.action_space.low[0] == pytest.approx(-1.0)
    assert env.action_space.high[0] == pytest.approx(1.0)
    assert env.observation_space.dtype == np.float32


def test_reset_seeded_deterministic():
    e1, e2 = UsvTrackingEnv(), UsvTrackingEnv()
    o1, _ = e1.reset(seed=123)
    o2, _ = e2.reset(seed=123)
    np.testing.assert_array_equal(o1, o2)
    # 不同 seed 应给出不同观测
    o3, _ = e1.reset(seed=456)
    assert not np.allclose(o1, o3)


def test_step_contract(env):
    obs, info = env.reset(seed=7)
    for _ in range(50):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        assert obs.dtype == np.float32
        assert np.isfinite(obs).all()
        assert np.isfinite(reward)
        assert set(info) >= {"e_pos", "e_psi", "e_ct", "progress_s", "is_success"}
        if terminated or truncated:
            obs, info = env.reset()
    # 速率限制生效：上一拍推力差不超过 dT_max*dt + 数值容差
    assert abs(info["applied_thrust"][0]) <= 25.0 + 1e-9


def test_thrust_rate_limit(env):
    env.reset(seed=1)
    big = np.array([1.0, 1.0])  # 归一化动作 +1 → 请求 +25N
    _, _, _, _, info = env.step(big)
    # 第一步从 0 出发，最多允许 dT_max*dt = 16 N
    assert info["applied_thrust"][0] == pytest.approx(80.0 * 0.2)


def test_los_baseline_completes_straight():
    """M2 前置：LOS 基线在直航路径上应基本完成。"""
    env = UsvTrackingEnv(path_type="straight")
    los = LosController()
    successes, episodes = 0, 20
    for ep in range(episodes):
        obs, info = env.reset(seed=1000 + ep)
        done = False
        while not done:
            action = los.act(env)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
        successes += int(info["is_success"])
    rate = successes / episodes
    print(f"LOS 直航成功率: {rate:.0%}")
    assert rate >= 0.9, f"LOS 直航成功率 {rate:.0%} < 90%"


def test_domain_randomization_changes_params():
    env = UsvTrackingEnv(path_type="straight", hydro_dr_frac=0.2)
    params_seen = set()
    for ep in range(10):
        env.reset(seed=ep)
        params_seen.add(round(env.model.params.mass, 6))
    assert len(params_seen) > 1, "DR 开启时每 episode 水动力应不同"


def test_gym_make_registered():
    import gymnasium as gym
    env = gym.make(_ENV_ID, path_type="arc")
    obs, _ = env.reset(seed=0)
    assert obs.shape[0] == env.observation_space.shape[0]
    env.close()
