"""Physical-unit checks independent of exporter buffers and manifest limits."""
from __future__ import annotations

import hashlib
import json
import pickle
from types import SimpleNamespace

import gymnasium as gym
import numpy as np
import onnxruntime as ort
import pytest
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from usv_rl import export_policy as exporter
from usv_rl.observation import LOOKAHEAD_M, OBS_CONTRACT_VERSION

_TRAIN_META: dict[str, Path] = {}


@pytest.fixture(autouse=True)
def train_meta_file(tmp_path):
    """每个用例一份 train_meta.json：导出必须绑定观测契约。"""
    path = tmp_path / "train_meta.json"
    path.write_text(json.dumps({
        "env": {
            "lookahead": list(LOOKAHEAD_M),
            "obs_prev_thrust_timing": "post_update",
            "progress_gate_m": 1.0,
        }
    }), encoding="utf-8")
    _TRAIN_META["path"] = path
    return path


def export(*args, **kwargs):
    kwargs.setdefault("train_meta_path", str(_TRAIN_META["path"]))
    return exporter.export(*args, **kwargs)


class ObservationEnv(gym.Env):
    observation_space = gym.spaces.Box(-100, 100, shape=(43,), dtype=np.float32)
    action_space = gym.spaces.Box(-1, 1, shape=(2,), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        return np.zeros(43, dtype=np.float32), {}

    def step(self, action):
        return np.zeros(43, dtype=np.float32), 0.0, False, False, {}


class SelectFirstTwoPolicy(torch.nn.Module):
    """Known normalized means; the reference below uses NumPy independently."""

    def __init__(self):
        super().__init__()
        self.mlp_extractor = SimpleNamespace(policy_net=torch.nn.Sequential())
        self.action_net = torch.nn.Linear(43, 2)
        with torch.no_grad():
            self.action_net.weight.zero_()
            self.action_net.bias.zero_()
            self.action_net.weight[0, 0] = 1
            self.action_net.weight[1, 1] = 1


class ReferenceModel:
    def __init__(self):
        self.observation_space = ObservationEnv.observation_space
        self.action_space = ObservationEnv.action_space
        self.policy = SelectFirstTwoPolicy()

    def predict(self, normalized, deterministic=False):
        assert deterministic is True
        # No actor call or exporter mapping is used to produce this oracle.
        return np.clip(np.asarray(normalized)[:, :2], -1, 1), None


@pytest.fixture
def paired_assets(tmp_path, monkeypatch):
    model_path = tmp_path / "model.zip"
    model_path.write_bytes(b"test checkpoint placeholder")
    vn_path = tmp_path / "vecnormalize.pkl"
    vn = VecNormalize(DummyVecEnv([ObservationEnv]), norm_obs=True, norm_reward=False,
                      epsilon=0.03, clip_obs=2.5)
    vn.obs_rms.mean = np.linspace(-0.4, 0.6, 43)
    vn.obs_rms.var = np.linspace(0.2, 1.2, 43)
    vn.save(str(vn_path))
    model = ReferenceModel()
    monkeypatch.setattr(PPO, "load", lambda *args, **kwargs: model)
    yield model_path, vn_path, vn, model
    vn.close()


def _save_vn(vn, path):
    with path.open("wb") as stream:
        pickle.dump(vn, stream)


def test_onnx_hardcoded_physical_golden(tmp_path):
    actor = exporter.DeterministicActor(
        SelectFirstTwoPolicy(), np.zeros(43), np.ones(43), thrust_scale_n=25.0,
    ).eval()
    raw = np.zeros((6, 43), dtype=np.float32)
    raw[:, :2] = [[-1, 1], [-0.5, 0.5], [0, 0], [0.5, -0.5], [1, -1], [-2, 2]]
    path = tmp_path / "golden.onnx"
    torch.onnx.export(actor, torch.from_numpy(raw[:1]), str(path),
                      input_names=["obs"], output_names=["thrust"],
                      dynamic_axes={"obs": {0: "batch"}, "thrust": {0: "batch"}},
                      opset_version=13, dynamo=False)
    actual = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"]).run(
        ["thrust"], {"obs": raw})[0]
    # Constants are deliberately independent of actor scale/manifest bounds.
    expected = [[-25, 25], [-12.5, 12.5], [0, 0], [12.5, -12.5], [25, -25], [-25, 25]]
    np.testing.assert_allclose(actual, expected, atol=1e-5, rtol=0)


def test_export_uses_saved_normalization_and_independent_reference(paired_assets, tmp_path):
    model_path, vn_path, vn, model = paired_assets
    source_hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (model_path, vn_path)]
    observations = np.tile(np.linspace(-1, 1, 43, dtype=np.float32), (3, 1))
    observations[1] *= 5
    raw_path = tmp_path / "observations.npy"
    np.save(raw_path, observations)
    count_before = vn.obs_rms.count
    out = export(str(model_path), str(vn_path), thrust_scale_n=25.0,
                          verification_obs_path=str(raw_path))
    assert out.name == "policy_physical_n.onnx"
    manifest = json.loads(out.with_suffix(".manifest.json").read_text())
    assert manifest["output_unit"] == "N"
    assert manifest["action_order"] == ["T_L", "T_R"]
    assert manifest["input_dim"] == 43 and manifest["output_dim"] == 2
    assert manifest["thrust_scale_n"] == 25.0
    assert manifest["physical_low_n"] == [-25.0, -25.0]
    assert manifest["physical_high_n"] == [25.0, 25.0]
    assert manifest["normalization_embedded"] is True
    assert manifest["normalization"]["epsilon"] == 0.03
    assert manifest["normalization"]["clip_obs"] == 2.5
    assert manifest["verification"]["observed_input_rows"] == 3
    contract = manifest["observation_contract"]
    assert contract["version"] == OBS_CONTRACT_VERSION == "ppo-obs-v2"
    assert contract["lookahead_m"] == list(LOOKAHEAD_M)
    assert contract["prev_thrust_timing"] == "post_update"
    assert contract["input_dim"] == 43
    assert manifest["train_meta_sha256"] == hashlib.sha256(
        _TRAIN_META["path"].read_bytes()).hexdigest()
    assert manifest["onnx_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert manifest["source_model_sha256"] == source_hashes[0]
    assert manifest["source_vecnormalize_sha256"] == source_hashes[1]
    session = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    metadata = session.get_modelmeta().custom_metadata_map
    assert metadata["usv.output_unit"] == "N"
    assert float(metadata["usv.thrust_scale_n"]) == 25.0
    actual = session.run(["thrust"], {"obs": observations})[0]
    expected = 25.0 * model.predict(vn.normalize_obs(observations), deterministic=True)[0]
    np.testing.assert_allclose(actual, expected, rtol=0, atol=0.001)
    assert vn.obs_rms.count == count_before
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in (model_path, vn_path)] == source_hashes


@pytest.mark.parametrize("scale", [0, -25, np.nan, np.inf, 20])
def test_illegal_scale_fails_without_publishing(paired_assets, tmp_path, scale):
    model_path, vn_path, _, _ = paired_assets
    with pytest.raises(ValueError):
        export(str(model_path), str(vn_path), thrust_scale_n=scale)
    assert not (tmp_path / "policy_physical_n.onnx").exists()
    assert not (tmp_path / "policy_physical_n.manifest.json").exists()


@pytest.mark.parametrize("invalid", ["norm_off", "mean_shape", "var_shape", "mean_nan",
                                     "var_inf", "var_negative", "epsilon_zero", "epsilon_nan",
                                     "clip_zero", "clip_inf"])
def test_invalid_normalization_fails_without_publishing(paired_assets, tmp_path, invalid):
    model_path, vn_path, vn, _ = paired_assets
    if invalid == "norm_off":
        vn.norm_obs = False
    elif invalid == "mean_shape":
        vn.obs_rms.mean = np.zeros(42)
    elif invalid == "var_shape":
        vn.obs_rms.var = np.ones(42)
    elif invalid == "mean_nan":
        vn.obs_rms.mean[0] = np.nan
    elif invalid == "var_inf":
        vn.obs_rms.var[0] = np.inf
    elif invalid == "var_negative":
        vn.obs_rms.var[0] = -1
    elif invalid == "epsilon_zero":
        vn.epsilon = 0
    elif invalid == "epsilon_nan":
        vn.epsilon = np.nan
    elif invalid == "clip_zero":
        vn.clip_obs = 0
    elif invalid == "clip_inf":
        vn.clip_obs = np.inf
    _save_vn(vn, vn_path)
    with pytest.raises(ValueError):
        export(str(model_path), str(vn_path), thrust_scale_n=25)
    assert not (tmp_path / "policy_physical_n.onnx").exists()
    assert not list(tmp_path.glob(".policy-export-*"))


def test_missing_train_meta_fails(paired_assets, tmp_path):
    """没有观测契约就不许导出（否则 43 维通道语义无法从产物反推）。"""
    model_path, vn_path, _, _ = paired_assets
    with pytest.raises(ValueError, match="train_meta"):
        exporter.export(str(model_path), str(vn_path), thrust_scale_n=25)
    assert not (tmp_path / "policy_physical_n.onnx").exists()


def test_malformed_train_meta_fails(paired_assets, tmp_path):
    model_path, vn_path, _, _ = paired_assets
    bad = tmp_path / "bad_train_meta.json"
    bad.write_text(json.dumps({"env": {"lookahead": [0.4, 0.8], "obs_prev_thrust_timing": "post_update"}}))
    with pytest.raises(ValueError, match="lookahead"):
        exporter.export(str(model_path), str(vn_path), thrust_scale_n=25, train_meta_path=str(bad))
    bad.write_text(json.dumps({"env": {"lookahead": list(LOOKAHEAD_M), "obs_prev_thrust_timing": "whenever"}}))
    with pytest.raises(ValueError, match="obs_prev_thrust_timing"):
        exporter.export(str(model_path), str(vn_path), thrust_scale_n=25, train_meta_path=str(bad))
    assert not (tmp_path / "policy_physical_n.onnx").exists()


def test_missing_normalization_fails(paired_assets, tmp_path):
    model_path, _, _, _ = paired_assets
    with pytest.raises(FileNotFoundError):
        export(str(model_path), str(tmp_path / "missing.pkl"), thrust_scale_n=25)
    assert not (tmp_path / "policy_physical_n.onnx").exists()


def test_loaded_reference_statistics_are_frozen(paired_assets):
    _, vn_path, _, _ = paired_assets
    loaded, _, _, eps, clip = exporter._load_vecnormalize(vn_path)
    assert loaded.training is False
    assert eps == 0.03 and clip == 2.5
    before = (loaded.obs_rms.mean.copy(), loaded.obs_rms.var.copy(), loaded.obs_rms.count)
    loaded.normalize_obs(np.full((4, 43), 5.0, dtype=np.float32))
    np.testing.assert_array_equal(loaded.obs_rms.mean, before[0])
    np.testing.assert_array_equal(loaded.obs_rms.var, before[1])
    assert loaded.obs_rms.count == before[2]


@pytest.mark.parametrize("raw", [np.zeros((0, 43)), np.zeros((2, 42)), np.zeros(43),
                                 np.full((2, 43), np.nan)])
def test_invalid_verification_observations_do_not_publish(paired_assets, tmp_path, raw):
    model_path, vn_path, _, _ = paired_assets
    raw_path = tmp_path / "invalid.npy"
    np.save(raw_path, raw)
    with pytest.raises(ValueError, match="verification observations"):
        export(str(model_path), str(vn_path), thrust_scale_n=25,
                        verification_obs_path=str(raw_path))
    assert not (tmp_path / "policy_physical_n.onnx").exists()


@pytest.mark.parametrize("invalid", ["physical_box", "one_action", "discrete", "42_obs"])
def test_wrong_checkpoint_spaces_fail(paired_assets, tmp_path, invalid):
    model_path, vn_path, _, model = paired_assets
    if invalid == "physical_box":
        model.action_space = gym.spaces.Box(-25, 25, (2,), dtype=np.float32)
    elif invalid == "one_action":
        model.action_space = gym.spaces.Box(-1, 1, (1,), dtype=np.float32)
    elif invalid == "discrete":
        model.action_space = gym.spaces.Discrete(2)
    else:
        model.observation_space = gym.spaces.Box(-100, 100, (42,), dtype=np.float32)
    with pytest.raises(ValueError):
        export(str(model_path), str(vn_path), thrust_scale_n=25)
    assert not (tmp_path / "policy_physical_n.onnx").exists()


@pytest.mark.parametrize("existing", ["graph", "manifest"])
def test_existing_outputs_are_not_overwritten(paired_assets, tmp_path, existing):
    model_path, vn_path, _, _ = paired_assets
    old_graph = tmp_path / "policy.onnx"
    old_graph.write_bytes(b"old normalized graph")
    target = tmp_path / "policy_physical_n.onnx"
    existing_path = target if existing == "graph" else target.with_suffix(".manifest.json")
    existing_path.write_bytes(b"existing asset")
    with pytest.raises(FileExistsError):
        export(str(model_path), str(vn_path), thrust_scale_n=25)
    assert existing_path.read_bytes() == b"existing asset"
    assert old_graph.read_bytes() == b"old normalized graph"
    # The original graph itself also cannot be overwritten through a custom --out.
    with pytest.raises(FileExistsError):
        export(str(model_path), str(vn_path), str(old_graph), thrust_scale_n=25)
    assert old_graph.read_bytes() == b"old normalized graph"


def test_reference_mismatch_leaves_no_formal_or_temporary_assets(paired_assets, tmp_path):
    model_path, vn_path, _, model = paired_assets
    model.predict = lambda obs, deterministic: (np.full((len(obs), 2), 0.75), None)
    with pytest.raises(ValueError, match="independent SB3 reference"):
        export(str(model_path), str(vn_path), thrust_scale_n=25)
    assert not (tmp_path / "policy_physical_n.onnx").exists()
    assert not (tmp_path / "policy_physical_n.manifest.json").exists()
    assert not list(tmp_path.glob(".policy-export-*"))


def test_publication_failure_removes_own_partial_graph(paired_assets, tmp_path, monkeypatch):
    model_path, vn_path, _, _ = paired_assets
    original_link = exporter.os.link

    def fail_manifest_link(source, destination):
        if str(destination).endswith(".manifest.json"):
            raise OSError("simulated manifest publication failure")
        return original_link(source, destination)

    monkeypatch.setattr(exporter.os, "link", fail_manifest_link)
    with pytest.raises(OSError, match="manifest publication"):
        export(str(model_path), str(vn_path), thrust_scale_n=25)
    assert not (tmp_path / "policy_physical_n.onnx").exists()
    assert not (tmp_path / "policy_physical_n.manifest.json").exists()
    assert not list(tmp_path.glob(".policy-export-*"))


def test_real_sb3_checkpoint_and_nondefault_statistics(tmp_path):
    """Exercise the actual SB3 policy and normalize_obs, without training."""
    env = DummyVecEnv([ObservationEnv])
    vn = VecNormalize(env, epsilon=0.03, clip_obs=2.5, norm_reward=False)
    vn.obs_rms.mean = np.linspace(-0.7, 0.8, 43)
    vn.obs_rms.var = np.linspace(0.3, 1.4, 43)
    model = PPO("MlpPolicy", vn, n_steps=8, batch_size=8, seed=42, device="cpu",
                policy_kwargs={"net_arch": {"pi": [8], "vf": [8]}})
    model_path, vn_path = tmp_path / "actual_model.zip", tmp_path / "actual_vecnormalize.pkl"
    model.save(str(model_path))
    vn.save(str(vn_path))
    out = export(str(model_path), str(vn_path), thrust_scale_n=25)
    raw = np.random.default_rng(19).normal(0, 2, (11, 43)).astype(np.float32)
    actual = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"]).run(
        ["thrust"], {"obs": raw})[0]
    expected = 25.0 * np.clip(model.predict(vn.normalize_obs(raw), deterministic=True)[0], -1, 1)
    np.testing.assert_allclose(actual, expected, rtol=0, atol=0.001)
    vn.close()
