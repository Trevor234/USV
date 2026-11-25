import json
import pickle
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import gymnasium as gym
import numpy as np
import onnx
import onnxruntime as ort
import pytest
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from usv_rl import envs, export_policy
from usv_rl.envs import UsvTrackingEnv
from usv_rl.equivariant_policy import (
    ACTION_SWAP_MATRIX,
    ODD_OBS_IDXS,
    SE2_MASK,
    Z2_PERM_MATRIX,
    EquivariantActorCriticPolicy,
    SymmetricVecNormalize,
    canonicalize_se2_np,
    mirror_obs_np,
)
from usv_rl.observation import LOOKAHEAD_M, compose_observation
from usv_rl.reference import path_from_curvature_profile
from usv_rl.train import ROOT, load_configs


def test_physical_reflection_of_curved_reference():
    state = np.array([2.6, -0.9, 0.37, 0.7, -0.14, 0.11])
    xs, ys, psis, kappas, s = path_from_curvature_profile(
        [0.16, -0.08], [6.0, 8.0], ds=0.25, start=(0.4, -1.7, -0.2),
    )
    v_ref = 0.5 + 0.02 * s
    r_ref = kappas * v_ref
    thrust = np.array([2.5, -6.0])
    obs = compose_observation(state, xs, ys, psis, kappas, v_ref, r_ref, s, 11, thrust)
    reflected = compose_observation(
        state * [1, -1, -1, 1, -1, -1],
        xs, -ys, -psis, -kappas, v_ref, -r_ref, s, 11, thrust[::-1],
    )

    # The physical reflection also flips absolute sin(psi). Z2 acts after masking it.
    np.testing.assert_allclose(reflected[3:5], obs[3:5] * [-1, 1], rtol=0, atol=1e-6)
    np.testing.assert_allclose(
        mirror_obs_np(canonicalize_se2_np(obs)), canonicalize_se2_np(reflected),
        rtol=0, atol=1e-6,
    )


def test_symmetry_matrices():
    for constant in (Z2_PERM_MATRIX, SE2_MASK, ACTION_SWAP_MATRIX):
        assert constant.dtype == np.float32
    np.testing.assert_array_equal(Z2_PERM_MATRIX @ Z2_PERM_MATRIX, np.eye(43))
    np.testing.assert_array_equal(Z2_PERM_MATRIX, Z2_PERM_MATRIX.T)
    np.testing.assert_array_equal(ACTION_SWAP_MATRIX, [[0, 1], [1, 0]])
    expected_mask = np.ones(43)
    expected_mask[[3, 4]] = 0
    np.testing.assert_array_equal(SE2_MASK, expected_mask)


class ObservationEnv(gym.Env):
    action_space = gym.spaces.Box(-1.0, 1.0, (2,), dtype=np.float32)

    def __init__(self, dict_obs):
        self.dict_obs = dict_obs
        obs_space = gym.spaces.Box(-100, 100, (43,), dtype=np.float32)
        self.observation_space = gym.spaces.Dict({
            "usv": obs_space, "other": gym.spaces.Box(-100, 100, (1,), dtype=np.float32),
        }) if dict_obs else obs_space

    def observation(self, offset):
        obs = np.linspace(-3.0, 8.0, 43, dtype=np.float32) + offset
        if self.dict_obs:
            return {"usv": obs, "other": np.array([offset], dtype=np.float32)}
        return obs

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        return self.observation(0.0), {}

    def step(self, action):
        return self.observation(2.0), 3.0, False, True, {}


@pytest.mark.parametrize("dict_obs", [False, True])
def test_normalization_commutes_with_reflection_after_reset_and_step(dict_obs):
    vn = SymmetricVecNormalize(DummyVecEnv([lambda: ObservationEnv(dict_obs)]), clip_obs=0.4)
    raw = np.random.default_rng(7).normal(0, 20, (7, 43)).astype(np.float32)
    try:
        vn.reset()
        rms = vn.obs_rms["usv"] if dict_obs else vn.obs_rms
        assert rms.count == pytest.approx(2.0001)

        def fields(obs):
            return obs["usv"] if dict_obs else obs

        def normalize(batch):
            obs = {"usv": batch, "other": np.zeros((len(batch), 1))} if dict_obs else batch
            return fields(vn.normalize_obs(obs))

        for step in (False, True):
            if step:
                _, _, dones, infos = vn.step(np.zeros((1, 2)))
                assert dones[0]
                assert vn.returns[0] == 0.0
                terminal_raw = vn.env_method("observation", 2.0)[0]
                np.testing.assert_array_equal(
                    fields(infos[0]["terminal_observation"]), fields(vn.normalize_obs(terminal_raw)),
                )
                assert rms.count == pytest.approx(4.0001)
            np.testing.assert_array_equal(rms.mean[list(ODD_OBS_IDXS)], 0)
            np.testing.assert_array_equal(rms.mean[3:5], 0)
            np.testing.assert_array_equal(rms.var[3:5], 1)
            assert rms.mean[41] == rms.mean[42]
            assert rms.var[41] == rms.var[42]

            assert abs(normalize(raw)).max() == np.float32(vn.clip_obs)
            np.testing.assert_array_equal(normalize(mirror_obs_np(raw)), mirror_obs_np(normalize(raw)))
        if dict_obs:
            assert vn.obs_rms["other"].count == pytest.approx(2.0001)
        vn.training = False
        vn.reset()
        vn.step(np.zeros((1, 2)))
        assert rms.count == pytest.approx(4.0001)
    finally:
        vn.close()


def _straight_obs():
    s = np.arange(0.0, 12.5, 0.5)
    zeros = np.zeros_like(s)
    speed = np.full_like(s, 0.7)
    return compose_observation(
        np.array([0.0, 0.0, 0.0, 0.7, 0.0, 0.0]),
        s, zeros, zeros, zeros, speed, zeros, s, 0, np.array([3.0, 3.0]),
    )


@pytest.fixture
def symmetry_inputs():
    raw = np.random.default_rng(17).normal(0, 2, (12, 43)).astype(np.float32)
    headings = np.array([-2.1, -1.55, 0.0, 0.7, 2.8])
    same_heading_free_obs = np.repeat(raw[:1], len(headings), axis=0)
    same_heading_free_obs[:, 3:5] = np.column_stack((np.sin(headings), np.cos(headings)))
    return raw, same_heading_free_obs, _straight_obs()[None, :]


@pytest.fixture(params=[True, False], ids=["shared", "separate"])
def trained_policy(request):
    vn = SymmetricVecNormalize(DummyVecEnv([lambda: UsvTrackingEnv(path_type="straight")]))
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        model = PPO(
            EquivariantActorCriticPolicy, vn, n_steps=32, batch_size=16, n_epochs=2,
            seed=42, device="cpu", policy_kwargs={
                "net_arch": [16, 16], "share_features_extractor": request.param,
            },
        )
        with torch.no_grad():
            model.policy.log_std.copy_(torch.tensor([-0.7, 0.2]))
        initial_weights = model.policy.action_net.weight.detach().clone()
        model.learn(total_timesteps=32)
        assert model.num_timesteps == 32
        assert not torch.equal(model.policy.action_net.weight, initial_weights)
        yield model, vn
    finally:
        vn.close()
        torch.set_num_threads(threads)


def test_policy_distribution_and_value_invariance(trained_policy, symmetry_inputs):
    model, vn = trained_policy
    raw, headings, straight = symmetry_inputs
    obs = torch.as_tensor(vn.normalize_obs(raw))
    mirrored = torch.as_tensor(vn.normalize_obs(mirror_obs_np(raw)))

    def predict(batch):
        return model.predict(vn.normalize_obs(batch), deterministic=True)[0]

    actions = predict(raw)
    heading_actions = predict(headings)
    np.testing.assert_allclose(heading_actions, np.repeat(heading_actions[:1], len(headings), axis=0), rtol=0, atol=1e-6)
    np.testing.assert_allclose(predict(mirror_obs_np(raw)), actions[:, ::-1], rtol=0, atol=1e-6)
    np.testing.assert_allclose(predict(straight)[0, 0], predict(straight)[0, 1], rtol=0, atol=1e-6)
    policy = model.policy
    with torch.no_grad():
        sampled, rollout_values, logp = policy(obs)
        values, evaluated_logp, entropy = policy.evaluate_actions(obs, sampled)
        mirrored_values, mirrored_logp, mirrored_entropy = policy.evaluate_actions(mirrored, sampled.flip(1))
        torch.testing.assert_close(logp, evaluated_logp, rtol=0, atol=1e-6)
        torch.testing.assert_close(logp, mirrored_logp, rtol=0, atol=1e-6)
        torch.testing.assert_close(entropy, mirrored_entropy, rtol=0, atol=1e-6)
        torch.testing.assert_close(rollout_values, values, rtol=0, atol=1e-6)
        torch.testing.assert_close(values, mirrored_values, rtol=0, atol=1e-6)
        torch.testing.assert_close(policy.predict_values(mirrored), values, rtol=0, atol=1e-6)
        heading_values = policy.predict_values(torch.as_tensor(vn.normalize_obs(headings)))
        torch.testing.assert_close(heading_values, heading_values[:1].expand_as(heading_values), rtol=0, atol=1e-6)
        dist = policy.get_distribution(obs).distribution
        torch.testing.assert_close(dist.stddev[:, 0], dist.stddev[:, 1], rtol=0, atol=0)
        torch.testing.assert_close(dist.stddev[0, 0], policy.log_std.mean().exp(), rtol=0, atol=0)


def test_checkpoint_roundtrip_and_onnx_symmetry(tmp_path, trained_policy, symmetry_inputs):
    model, vn = trained_policy
    model_path = tmp_path / "model.zip"
    vn_path = tmp_path / "vecnormalize.pkl"
    model.save(model_path)
    vn.save(vn_path)
    with vn_path.open("rb") as stream:
        assert isinstance(pickle.load(stream), SymmetricVecNormalize)

    raw, headings, straight = symmetry_inputs
    restored_vn = VecNormalize.load(vn_path, DummyVecEnv([lambda: UsvTrackingEnv(path_type="straight")]))
    try:
        assert isinstance(restored_vn, SymmetricVecNormalize)
        restored = PPO.load(model_path, env=restored_vn, device="cpu")
        assert type(restored.policy) is EquivariantActorCriticPolicy
        np.testing.assert_array_equal(restored_vn.normalize_obs(raw), vn.normalize_obs(raw))
        expected = model.predict(vn.normalize_obs(raw), deterministic=True)[0]
        np.testing.assert_array_equal(restored.predict(restored_vn.normalize_obs(raw), deterministic=True)[0], expected)
    finally:
        restored_vn.close()

    train_meta = tmp_path / "train_meta.json"
    train_meta.write_text(json.dumps({"env": {"lookahead": LOOKAHEAD_M, "obs_prev_thrust_timing": "post_update"}}))
    raw_path = tmp_path / "observations.npy"
    np.save(raw_path, np.concatenate((raw, mirror_obs_np(raw), headings, straight)))
    out = export_policy.export(
        str(model_path), str(vn_path), opset=13, thrust_scale_n=25.0,
        train_meta_path=str(train_meta), verification_obs_path=str(raw_path),
    )
    manifest = json.loads(out.with_suffix(".manifest.json").read_text())
    assert manifest["equivariant_z2_se2"] is True
    assert manifest["verification"]["max_abs_error_n"] <= 1e-4
    graph = onnx.load(out)
    assert graph.opset_import[0].version == 13
    assert all(not node.op_type.startswith(("Gather", "Scatter")) for node in graph.graph.node)
    session = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])

    def thrust(batch):
        return session.run(["thrust"], {"obs": batch})[0]

    np.testing.assert_allclose(thrust(raw), 25.0 * expected, rtol=0, atol=1e-4)
    np.testing.assert_allclose(thrust(mirror_obs_np(raw)), thrust(raw)[:, ::-1], rtol=0, atol=1e-6)
    np.testing.assert_array_equal(thrust(headings), np.repeat(thrust(headings)[:1], len(headings), axis=0))
    q_left, q_right = thrust(straight)[0]
    assert q_left == q_right


def test_v7_fusion_config_and_factory(monkeypatch):
    default_ppo, _ = load_configs(None)
    config, env_cfg = load_configs(str(ROOT / "configs" / "v7_fusion.yaml"))
    ppo = config["ppo"]
    assert ppo.keys() == default_ppo["ppo"].keys()
    assert config["eval"].keys() == default_ppo["eval"].keys()
    assert ppo["n_steps"] * config["n_envs"] % ppo["batch_size"] == 0
    assert ppo["learning_rate"] == 1.5e-4
    assert config["policy_kwargs"] == {
        "net_arch": [256, 256], "activation_fn": "tanh", "equivariant_z2_se2": True,
    }
    assert config["curriculum"][0]["name"] == "s4_dr"
    env = UsvTrackingEnv(**env_cfg)
    try:
        assert env.cost_params.use_mode_energy
        assert env.reset(seed=42)[0].shape == (43,)
    finally:
        env.close()

    make_fusion_env = Mock()
    monkeypatch.setitem(sys.modules, "fusion_env", SimpleNamespace(make_fusion_env=make_fusion_env))
    monkeypatch.syspath_prepend(str(envs.SCHEME_A_LEARNING_DIR))
    monkeypatch.setattr(envs, "FUSION_ENV", True)
    monkeypatch.setattr(envs, "FUSION_CONTRACT", "/contract.json")
    monkeypatch.setattr(envs, "FUSION_GP", "/gp.json")
    envs.make_env_factory(env_cfg, 42, fusion_cfg=config["fusion"])
    assert make_fusion_env.call_args.kwargs["lambda_pi"] == 0.01
    assert make_fusion_env.call_args.kwargs["r_qpi_u0"] == 0.002
    envs.make_env_factory(env_cfg, 42)
    assert make_fusion_env.call_args.kwargs["lambda_pi"] == envs.FUSION_LAMBDA_PI
    assert "r_qpi_u0" not in make_fusion_env.call_args.kwargs


def test_v7_fusion_stable_config_and_log_std_init():
    default_ppo, _ = load_configs(None)
    config, env_cfg = load_configs(str(ROOT / "configs" / "v7_fusion_stable.yaml"))
    ppo = config["ppo"]
    assert ppo.keys() == default_ppo["ppo"].keys()
    assert config["eval"].keys() == default_ppo["eval"].keys()
    assert ppo["n_steps"] * config["n_envs"] % ppo["batch_size"] == 0
    assert config["policy_kwargs"]["log_std_init"] == -1.6
    assert config["fusion"] == {"lambda_pi": 0.01, "r_qpi_u0": 0.004}
    vn = SymmetricVecNormalize(DummyVecEnv([lambda: UsvTrackingEnv(path_type="straight")]))
    try:
        model = PPO(
            EquivariantActorCriticPolicy, vn, device="cpu",
            policy_kwargs={"net_arch": [128, 128], "log_std_init": -1.6},
        )
        np.testing.assert_allclose(model.policy.log_std.detach().numpy(), [-1.6, -1.6], atol=1e-6)
    finally:
        vn.close()


def test_v7_fusion_v4_config_loads_and_matches_env():
    default_ppo, _ = load_configs(None)
    config, env_cfg = load_configs(str(ROOT / "configs" / "v7_fusion_v4.yaml"))
    ppo = config["ppo"]
    assert ppo.keys() == default_ppo["ppo"].keys()
    assert config["eval"].keys() == default_ppo["eval"].keys()
    assert ppo["n_steps"] * config["n_envs"] % ppo["batch_size"] == 0
    assert env_cfg["maneuver_seconds"] == 55.0
    assert config["policy_kwargs"]["log_std_init"] == -0.9
    env = UsvTrackingEnv(**env_cfg)
    try:
        assert env.reset(seed=42)[0].shape == (43,)
    finally:
        env.close()


def test_v7_fusion_v5_config_loads_and_matches_env():
    default_ppo, _ = load_configs(None)
    _, v4_env = load_configs(str(ROOT / "configs" / "v7_fusion_v4.yaml"))
    config, env_cfg = load_configs(str(ROOT / "configs" / "v7_fusion_v5.yaml"))
    ppo = config["ppo"]
    rollout_steps = ppo["n_steps"] * config["n_envs"]
    assert ppo.keys() == default_ppo["ppo"].keys()
    assert config["eval"].keys() == default_ppo["eval"].keys()
    assert rollout_steps % ppo["batch_size"] == 0
    assert config["eval"]["freq_steps"] % rollout_steps == 0
    assert config["policy_kwargs"] == {
        "net_arch": [128, 128], "activation_fn": "tanh", "equivariant_z2_se2": True, "log_std_init": -0.85,
    }
    assert config["fusion"] == {"lambda_pi": 0.005, "r_qpi_u0": 0.0005}
    stage, = config["curriculum"]
    assert stage["name"] == "s4_dr"
    assert stage["total_steps"] == 196608
    assert stage["total_steps"] % rollout_steps == 0
    for key in ("early_termination", "max_steps", "maneuver_seconds"):
        assert env_cfg[key] == v4_env[key]

    env = UsvTrackingEnv(**{**env_cfg, **stage["env_overrides"]})
    try:
        assert env.cost_params.use_mode_energy
        assert env.cost_params.r_dm == 0.03
        assert env.reset(seed=42)[0].shape == (43,)
    finally:
        env.close()


def test_v7_fusion_v6_config_loads_m6_and_s4_dr():
    _, v5_env = load_configs(str(ROOT / "configs" / "v7_fusion_v5.yaml"))
    config, env_cfg = load_configs(str(ROOT / "configs" / "v7_fusion_v6.yaml"))

    assert (config["n_envs"], config["seed"], config["device"]) == (16, 42, "cuda")
    assert config["policy_kwargs"] == {
        "net_arch": [128, 128], "activation_fn": "tanh", "equivariant_z2_se2": True, "log_std_init": -1.4,
    }
    assert config["fusion"] == {"lambda_pi": 0.005, "r_qpi_u0": 0.0005}
    assert config["ppo"] == {
        "learning_rate": 5.0e-5, "lr_schedule": "linear", "n_steps": 512, "batch_size": 1024,
        "n_epochs": 6, "gamma": 0.99, "gae_lambda": 0.95, "clip_range": 0.1,
        "ent_coef": 0.0001, "vf_coef": 0.5, "max_grad_norm": 0.5,
    }
    assert config["eval"] == {
        "n_episodes": 16, "freq_steps": 16384, "path_type": "scheme_a_mix", "deterministic": True,
    }
    stage, = config["curriculum"]
    assert stage == {
        "name": "s4_dr", "total_steps": 131072, "env_overrides": {
            "path_type": "scheme_a_mix", "hydro_dr_frac": 0.15, "thrust_delay_max_steps": 0,
            "obs_noise_vel": 0.0, "obs_noise_pos": 0.0,
        },
    }
    for key in ("early_termination", "max_steps", "maneuver_seconds",
                "init_pos_noise", "init_psi_noise", "init_vel_noise"):
        assert env_cfg[key] == v5_env[key]

    env = UsvTrackingEnv(**{**env_cfg, **stage["env_overrides"]})
    try:
        cost = env.cost_params
        assert cost.use_mode_energy
        assert (cost.q_ct, cost.q_psi, cost.q_u, cost.q_v, cost.q_r) == (380.0, 65.0, 26.0, 1.0, 8.0)
        assert (cost.r_thrust, cost.r_dthrust, cost.w_progress) == (0.05, 0.6, 0.0)
        assert (cost.r_cm, cost.r_dm, cost.drag_ff_gain) == (0.105, 0.015, 0.64)
        assert env.reset(seed=42)[0].shape == (43,)
    finally:
        env.close()


