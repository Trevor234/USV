"""Gymnasium API 与环境行为测试。"""
from __future__ import annotations

import math

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from usv_rl.baselines import LosController
from usv_rl.envs import _ENV_ID, UsvTrackingEnv
from usv_rl.envs.geometry import cte_penalty
from usv_rl.envs.reward import tracking_cost
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


def test_beeline_policy_scores_zero_success():
    """反例：不看参考、全推力直冲的策略必须一次都不算成功。

    旧的"到终点即成功"判据会奖励"蒙到终点但全程偏离航线 5 m+"的策略，
    这正是评审里发现的失败模式。这里用不受早期终止打断的训练口径
    （early_termination=False，与 env.yaml 一致），让横向误差充分暴露。
    """
    env = UsvTrackingEnv(path_type="arc", early_termination=False)
    successes, max_cts = 0, []
    for ep in range(20):
        env.reset(seed=2000 + ep)
        done = False
        while not done:
            # 恒定航向 + 全推力：既不对参考航向做任何跟踪，也不做速度控制
            _, _, terminated, truncated, info = env.step(np.array([1.0, 1.0], dtype=np.float32))
            done = terminated or truncated
        successes += int(info["is_success"])
        max_cts.append(float(info.get("max_e_ct", 0.0)))
    assert successes == 0, f"直线策略不应成功，实际 {successes}/20"
    assert float(np.median(max_cts)) > 5.0, f"max_e_ct 中位数应 > 5 m，实际 {np.median(max_cts):.3f}"


def test_reward_matches_polyline_cte():
    """奖励的第一项必须等于按折线投影算出的横向误差惩罚。"""
    env = UsvTrackingEnv(path_type="random")
    env.reset(seed=5)
    applied = np.array([3.0, 2.5])
    env.step(np.array([0.2, 0.15], dtype=np.float32))
    ds_prog = 0.0
    reward = env._reward(applied, ds_prog)
    p = env.cost_params
    e_ct, psi_seg = env._ct_geometry()
    e_psi = math.atan2(
        math.sin(float(env.state[2]) - psi_seg), math.cos(float(env.state[2]) - psi_seg)
    )
    expected = tracking_cost(
        env.state, applied, env.prev_thrust,
        float(env.reference.v_ref[env.prog_idx]), float(env.reference.r_ref[env.prog_idx]),
        e_ct, e_psi, ds_prog, p,
    )
    assert reward == pytest.approx(expected, abs=1e-9)
    penalty_term = -p.reward_scale * p.q_ct * cte_penalty(e_ct, p.ct_linear_m)
    rest = expected + p.reward_scale * p.q_ct * cte_penalty(e_ct, p.ct_linear_m)
    assert rest + penalty_term == pytest.approx(expected, abs=1e-9)
    assert np.isfinite(e_ct)


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


def test_obs_prev_thrust_timing_reward_invariant_and_validation():
    import pytest

    with pytest.raises(ValueError, match="obs_prev_thrust_timing"):
        UsvTrackingEnv(obs_prev_thrust_timing="invalid")

    e_pre = UsvTrackingEnv(path_type="arc", init_pos_noise=0.0, init_psi_noise=0.0, init_vel_noise=0.0, obs_prev_thrust_timing="pre_update")
    e_post = UsvTrackingEnv(path_type="arc", init_pos_noise=0.0, init_psi_noise=0.0, init_vel_noise=0.0, obs_prev_thrust_timing="post_update")
    e_pre.reset(seed=11)
    e_post.reset(seed=11)
    for k in range(10):
        act = np.array([0.4 + 0.03 * k, 0.25 - 0.02 * k], dtype=np.float32)
        obs_pre, r_pre, t_pre, tr_pre, _ = e_pre.step(act)
        obs_post, r_post, t_post, tr_post, info_post = e_post.step(act)
        assert r_pre == pytest.approx(r_post, abs=1e-12)
        assert t_pre == t_post and tr_pre == tr_post
        np.testing.assert_allclose(obs_post[-2:], info_post["applied_thrust"], atol=1e-5)
        if np.max(np.abs(obs_pre[-2:] - obs_post[-2:])) == 0.0:
            raise AssertionError("Expected pre_update and post_update prev_thrust slices to differ when action changes")
