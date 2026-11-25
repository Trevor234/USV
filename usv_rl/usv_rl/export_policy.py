"""Export the v5 PPO policy with raw observations and physical thrust in N.

The checkpoint's action Box describes normalized actions, not physical limits.
This export path requires the explicit deployment scale and paired, fixed
VecNormalize statistics. Existing ONNX files are never overwritten.

Example::

    python -m usv_rl.export_policy --model ../artifacts/rl_models/v5/s4_dr/model.zip \
        --vecnorm ../artifacts/rl_models/v5/s4_dr/vecnormalize.pkl --thrust-scale-n 25.0 \
        --verification-obs experiments/observations.npy
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import pickle
import platform
import shlex
import tempfile
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from usv_rl.observation import LOOKAHEAD_M, OBS_CONTRACT_VERSION, PROGRESS_GATE_M, PROGRESS_WINDOW


OBS_DIM = 43
ACTION_DIM = 2
VERIFY_TOLERANCE_N = 1e-3


def _positive_finite(value: float, name: str) -> float:
    value = float(value)
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _validate_spaces(model) -> None:
    from gymnasium.spaces import Box

    if not isinstance(model.observation_space, Box) or model.observation_space.shape != (OBS_DIM,):
        raise ValueError("v5 export requires a 43-dimensional Box observation space")
    space = model.action_space
    if (not isinstance(space, Box) or space.shape != (ACTION_DIM,)
            or not np.array_equal(space.low, [-1.0, -1.0])
            or not np.array_equal(space.high, [1.0, 1.0])):
        raise ValueError("v5 export requires a 2-dimensional normalized action Box [-1, 1]")
    if getattr(model.policy, "squash_output", False):
        raise ValueError("v5 export requires an unsquashed PPO mean policy")


def _load_vecnormalize(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"paired VecNormalize statistics are required: {path}")
    with path.open("rb") as stream:
        vn = pickle.load(stream)
    if getattr(vn, "norm_obs", None) is not True:
        raise ValueError("this export path requires VecNormalize norm_obs=True")
    if not callable(getattr(vn, "normalize_obs", None)):
        raise ValueError("statistics must provide VecNormalize.normalize_obs")
    rms = getattr(vn, "obs_rms", None)
    mean = np.asarray(getattr(rms, "mean", None), dtype=np.float64)
    var = np.asarray(getattr(rms, "var", None), dtype=np.float64)
    if mean.shape != (OBS_DIM,) or var.shape != (OBS_DIM,):
        raise ValueError("VecNormalize mean and variance must each have 43 entries")
    if not np.isfinite(mean).all() or not np.isfinite(var).all() or (var < 0).any():
        raise ValueError("VecNormalize statistics must be finite with nonnegative variance")
    with np.errstate(over="ignore"):
        if not np.isfinite(mean.astype(np.float32)).all() or not np.isfinite(var.astype(np.float32)).all():
            raise ValueError("VecNormalize statistics must be representable as float32")
    eps = _positive_finite(vn.epsilon, "VecNormalize epsilon")
    clip_obs = _positive_finite(vn.clip_obs, "VecNormalize clip_obs")
    if not np.isfinite(np.float32(eps)) or np.float32(eps) <= 0 or not np.isfinite(np.float32(clip_obs)):
        raise ValueError("VecNormalize epsilon and clip_obs must be representable as float32")
    vn.training = False
    return vn, mean, var, eps, clip_obs


class DeterministicActor(nn.Module):
    """Raw observation -> frozen normalization -> clipped mean -> physical N."""

    def __init__(self, policy, obs_mean, obs_var, *, thrust_scale_n: float,
                 clip_obs: float = 10.0, eps: float = 1e-8) -> None:
        super().__init__()
        layers = list(policy.mlp_extractor.policy_net.children()) + [policy.action_net]
        self.net = nn.Sequential(*layers)
        self._equivariant = all(hasattr(policy, name) for name in ("se2_mask", "z2_perm_mat", "action_swap_mat"))
        if self._equivariant:
            self.register_buffer("se2_mask", policy.se2_mask.detach().float())
            self.register_buffer("z2_perm_mat", policy.z2_perm_mat.detach().float())
            self.register_buffer("action_swap_mat", policy.action_swap_mat.detach().float())
        self.register_buffer("obs_mean", torch.as_tensor(obs_mean, dtype=torch.float32))
        self.register_buffer("obs_var", torch.as_tensor(obs_var, dtype=torch.float32))
        self.thrust_scale_n = _positive_finite(thrust_scale_n, "thrust_scale_n")
        self.clip_obs = clip_obs
        self.eps = eps

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        norm = (obs - self.obs_mean) / torch.sqrt(self.obs_var + self.eps)
        norm = torch.clamp(norm, -self.clip_obs, self.clip_obs)
        if self._equivariant:
            norm_c = norm * self.se2_mask
            norm_m = norm_c @ self.z2_perm_mat
            mean = 0.5 * (self.net(norm_c) + self.net(norm_m) @ self.action_swap_mat)
        else:
            mean = self.net(norm)
        return torch.clamp(mean, -1.0, 1.0) * self.thrust_scale_n


def _load_observation_contract(train_meta_path: str | Path | None) -> dict:
    """从 train_meta.json 读出本次训练的观测契约；缺参数一律报错。

    没有契约的清单等于没有 provenance：部署侧的 43 维通道含义只能靠猜，
    而 lookahead / prev_thrust 时序每变一次，同一份权重就是另一套语义。
    """
    if not train_meta_path:
        raise ValueError(
            "train_meta.json is required: 用 --train-meta <run>/train_meta.json 绑定观测契约"
        )
    path = Path(train_meta_path)
    if not path.is_file():
        raise FileNotFoundError(f"train_meta.json 不存在: {path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    env = doc.get("env")
    if not isinstance(env, dict):
        raise ValueError(f"{path} 缺少 env 段，无法确定观测契约")
    lookahead = env.get("lookahead")
    if not isinstance(lookahead, (list, tuple)) or len(lookahead) != len(LOOKAHEAD_M):
        raise ValueError(
            f"{path} 的 env.lookahead 必须是 {len(LOOKAHEAD_M)} 项，实际 {lookahead!r}"
        )
    try:
        lookahead_f = [float(v) for v in lookahead]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} 的 env.lookahead 含非数值项: {lookahead!r}") from exc
    if not all(np.isfinite(v) for v in lookahead_f):
        raise ValueError(f"{path} 的 env.lookahead 含非有限值: {lookahead_f!r}")
    timing = env.get("obs_prev_thrust_timing")
    if timing not in ("pre_update", "post_update"):
        raise ValueError(
            f"{path} 的 env.obs_prev_thrust_timing 必须是 pre_update/post_update，实际 {timing!r}"
        )
    return {
        "version": OBS_CONTRACT_VERSION,
        "lookahead_m": lookahead_f,
        "prev_thrust_timing": timing,
        "reference_index": f"monotone_progress_window{PROGRESS_WINDOW}_gate{PROGRESS_GATE_M}",
        "input_dim": OBS_DIM,
        "_train_meta_path": str(path),
        "_train_meta_sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verification_observations(path: Path | None) -> np.ndarray:
    if path is None:
        return np.empty((0, OBS_DIM), dtype=np.float32)
    observations = np.asarray(np.load(path, allow_pickle=False), dtype=np.float32)
    if (observations.ndim != 2 or observations.shape[1] != OBS_DIM
            or observations.shape[0] < 1 or not np.isfinite(observations).all()):
        raise ValueError("verification observations must be finite with shape (N, 43), N >= 1")
    return observations


def _verify(sb3_model, vn, out: Path, thrust_scale_n: float,
            observed_inputs: np.ndarray) -> dict:
    """Independent reference: saved VecNormalize API + SB3 deterministic predict.

    Neither actor buffers nor its mapping function are used as the oracle.
    Physical golden values are separately checked by test_export_scaling.py.
    """
    import onnxruntime as ort

    session = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    synthetic = np.random.default_rng(0).normal(0, 2.0, (64, OBS_DIM)).astype(np.float32)
    raw = np.concatenate((synthetic, observed_inputs), axis=0)
    actual = session.run(["thrust"], {"obs": raw})[0]
    normalized = vn.normalize_obs(raw.copy())
    actions = np.asarray(sb3_model.predict(normalized, deterministic=True)[0])
    expected_n = np.clip(actions, -1.0, 1.0) * thrust_scale_n
    if (actual.shape != (len(raw), ACTION_DIM) or expected_n.shape != actual.shape
            or not np.isfinite(actual).all() or not np.isfinite(expected_n).all()):
        raise ValueError("ONNX/reference outputs must be finite with shape (N, 2)")
    max_diff_n = float(np.max(np.abs(actual - expected_n)))
    if max_diff_n > VERIFY_TOLERANCE_N:
        raise ValueError(f"ONNX and independent SB3 reference differ by {max_diff_n:.6g} N")
    return {"reference": "VecNormalize.normalize_obs + SB3.predict(deterministic=True)",
            "synthetic_input_rows": 64, "observed_input_rows": len(observed_inputs),
            "max_abs_error_n": max_diff_n, "tolerance_n": VERIFY_TOLERANCE_N}


def _temporary_path(directory: Path, suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".policy-export-", suffix=suffix, dir=directory)
    os.close(descriptor)
    return Path(name)


def export(model_path: str, vecnorm_path: str, out_path: str | None = None,
           opset: int = 13, *, thrust_scale_n: float,
           train_meta_path: str | None = None,
           verification_obs_path: str | None = None) -> Path:
    """Publish a new graph plus manifest after independent verification.

    Exclusive same-directory links prevent replacement by concurrent exports.
    Failure removes this call's temporary files and any partial publication.
    """
    scale = _positive_finite(thrust_scale_n, "thrust_scale_n")
    obs_contract = _load_observation_contract(train_meta_path)
    if scale != 25.0:
        raise ValueError("this v5 deployment contract requires thrust_scale_n=25.0")
    model_source, vn_source = Path(model_path), Path(vecnorm_path)
    out = Path(out_path) if out_path else model_source.parent / "policy_physical_n.onnx"
    manifest_path = out.with_suffix(".manifest.json")
    if out.exists() or manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite an existing output: {out} / {manifest_path}")
    if not model_source.is_file():
        raise FileNotFoundError(model_source)
    # Hash before deserializing, then check again before publishing.
    model_source_hash, vn_source_hash = _sha256(model_source), _sha256(vn_source)
    vn, mean, var, eps, clip_obs = _load_vecnormalize(vn_source)
    observations_path = Path(verification_obs_path) if verification_obs_path else None
    observations_hash = _sha256(observations_path) if observations_path else None
    observed_inputs = _verification_observations(observations_path)

    from stable_baselines3 import PPO
    import onnx

    model = PPO.load(str(model_source), device="cpu")
    _validate_spaces(model)
    model.policy.eval()
    actor = DeterministicActor(model.policy, mean, var, thrust_scale_n=scale,
                               clip_obs=clip_obs, eps=eps).eval()
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary_onnx = _temporary_path(out.parent, ".onnx")
    temporary_manifest = None
    published_onnx = False
    published_manifest = False
    try:
        torch.onnx.export(
            actor, torch.zeros(1, OBS_DIM, dtype=torch.float32), str(temporary_onnx),
            input_names=["obs"], output_names=["thrust"],
            dynamic_axes={"obs": {0: "batch"}, "thrust": {0: "batch"}},
            opset_version=opset, do_constant_folding=True, dynamo=False,
        )
        graph = onnx.load(str(temporary_onnx))
        onnx.helper.set_model_props(graph, {
            "usv.contract_version": "1", "usv.output_unit": "N",
            "usv.action_order": "T_L,T_R", "usv.input_dim": str(OBS_DIM),
            "usv.output_dim": str(ACTION_DIM), "usv.thrust_scale_n": str(scale),
        })
        onnx.checker.check_model(graph, full_check=True)
        onnx.save(graph, str(temporary_onnx))
        verification = _verify(model, vn, temporary_onnx, scale, observed_inputs)
        if _sha256(model_source) != model_source_hash or _sha256(vn_source) != vn_source_hash:
            raise ValueError("source checkpoint/statistics changed during export")
        if observations_path and _sha256(observations_path) != observations_hash:
            raise ValueError("verification observations changed during export")
        command = ["python", "-m", "usv_rl.export_policy", "--model", str(model_source),
                   "--vecnorm", str(vn_source), "--thrust-scale-n", str(scale), "--out", str(out),
                   "--train-meta", obs_contract["_train_meta_path"]]
        if observations_path:
            command += ["--verification-obs", str(observations_path)]
        manifest = {
            "contract_version": 1, "output_unit": "N", "action_order": ["T_L", "T_R"],
            "input_name": "obs", "input_dim": OBS_DIM, "output_name": "thrust",
            "output_dim": ACTION_DIM, "thrust_scale_n": scale,
            "physical_low_n": [-scale, -scale], "physical_high_n": [scale, scale],
            "normalization_embedded": True, "onnx_sha256": _sha256(temporary_onnx),
            "source_model_path": str(model_source), "source_model_sha256": model_source_hash,
            "source_vecnormalize_path": str(vn_source), "source_vecnormalize_sha256": vn_source_hash,
            "normalization": {"norm_obs": True, "epsilon": eps, "clip_obs": clip_obs,
                              "reference_training": False},
            "observation_contract": {k: v for k, v in obs_contract.items() if not k.startswith("_")},
            "train_meta_path": obs_contract["_train_meta_path"],
            "train_meta_sha256": obs_contract["_train_meta_sha256"],
            "verification": verification, "export_command": shlex.join(command),
            "opset": opset, "versions": {"python": platform.python_version(), **{
                name: importlib.metadata.version(name) for name in
                ("numpy", "torch", "stable-baselines3", "onnx", "onnxruntime")}},
        }
        if actor._equivariant:
            manifest["equivariant_z2_se2"] = True
        if observations_path:
            manifest["verification_observations_sha256"] = observations_hash
        temporary_manifest = _temporary_path(out.parent, ".manifest.json")
        temporary_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                      encoding="utf-8")
        os.link(temporary_onnx, out)
        published_onnx = True
        os.link(temporary_manifest, manifest_path)
        published_manifest = True
    except BaseException:
        if published_manifest:
            manifest_path.unlink(missing_ok=True)
        if published_onnx:
            out.unlink(missing_ok=True)
        raise
    finally:
        temporary_onnx.unlink(missing_ok=True)
        if temporary_manifest:
            temporary_manifest.unlink(missing_ok=True)
    print(f"ONNX exported: {out} (independent reference error {verification['max_abs_error_n']:.2e} N)")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Export v5 PPO ONNX with physical thrust in N")
    parser.add_argument("--model", required=True)
    parser.add_argument("--vecnorm", help="paired VecNormalize pickle, defaults beside model")
    parser.add_argument("--thrust-scale-n", required=True, type=float,
                        help="explicit physical thrust scale in N (this contract: 25.0)")
    parser.add_argument("--out", help="new output path, defaults to policy_physical_n.onnx")
    parser.add_argument("--verification-obs", help="fixed real raw observations, NumPy (N, 43)")
    parser.add_argument("--train-meta", required=True,
                        help="<run>/train_meta.json：导出必须绑定观测契约（lookahead / prev_thrust 时序）")
    args = parser.parse_args()
    model_path = Path(args.model)
    vecnorm = args.vecnorm or str(model_path.parent / "vecnormalize.pkl")
    export(str(model_path), vecnorm, args.out, thrust_scale_n=args.thrust_scale_n,
           train_meta_path=args.train_meta,
           verification_obs_path=args.verification_obs)


if __name__ == "__main__":
    main()
