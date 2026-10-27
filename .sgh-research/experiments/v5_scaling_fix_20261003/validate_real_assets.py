#!/usr/bin/env python3
"""Independent, read-only validation of the v5 physical-N ONNX asset.

Run with the existing training Python environment.  The reference calls the
saved VecNormalize.normalize_obs and PPO.predict; it never imports the new
exporter or reads the actor's scale buffers.  This validates numerical pairing,
not the historical provenance of the checkpoint/normalizer or training range.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import pickle
import sys
import time
import traceback

import numpy as np


ORIGINAL_SHA256 = {
    "model.zip": "85c6c573fa880695de1c6173c5e7e75c1702c5f1306415d91b39d2a9512c7220",
    "policy.onnx": "a4892ad56a3af6031d0721ca34dfadd4eeafc42bc8a38604119b25a7a0cd88b0",
    "vecnormalize.pkl": "2be84c0fcaf992a52f1d9a2a3d4b997d8586951c1b9c9caba1d67badce2d769e",
}
LOOKAHEAD = (0.4, 0.8, 1.2, 1.6, 2.0, 2.5, 3.0, 4.0)
PHYSICAL_SCALE_N = 25.0
TOLERANCE_N = 0.001


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_versions() -> dict:
    result = {"python": sys.version, "executable": sys.executable}
    for name in ("numpy", "torch", "gymnasium", "stable-baselines3", "onnx", "onnxruntime"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def composed_cases(compose_observation) -> list[dict]:
    """Raw 43-D fixtures from the shared real observation constructor.

    The state/profile pairs are deterministic representative inputs, not
    fabricated recorded telemetry.  Previous thrust values are physical N.
    """
    cases = []
    straight_s = np.arange(0.0, 80.0 + 0.5, 0.5)
    profiles = {
        "straight": {
            "x": straight_s, "y": np.zeros_like(straight_s),
            "psi": np.zeros_like(straight_s), "kappa": np.zeros_like(straight_s),
            "s": straight_s,
        }
    }
    arc_s = np.arange(0.0, 40.0 + 0.5, 0.5)
    radius = 25.0
    theta = arc_s / radius
    profiles["turn"] = {
        "x": radius * np.sin(theta), "y": radius * (1.0 - np.cos(theta)),
        "psi": theta, "kappa": np.full_like(arc_s, 1.0 / radius), "s": arc_s,
    }
    definitions = [
        ("straight_start", "straight", [0, 0, 0, 0, 0, 0], 0, [0, 0]),
        ("straight_cruise", "straight", [6, 0, 0, .6, 0, 0], 6, [12.5, 12.5]),
        ("straight_left_offset", "straight", [12, .4, .1, .55, .02, .03], 12, [16, -16]),
        ("straight_right_offset", "straight", [18, -.5, -.12, .7, -.03, -.02], 18, [25, 9]),
        ("turn_cruise", "turn", [radius * math.sin(.4), radius * (1 - math.cos(.4)), .4, .6, 0, .024], 10, [12.5, 16]),
        ("turn_offset", "turn", [radius * math.sin(.4), radius * (1 - math.cos(.4)) + .3, .3, .7, .02, .02], 10, [-12.5, 12.5]),
        ("turn_reverse_history", "turn", [radius * math.sin(.8), radius * (1 - math.cos(.8)), .8 + math.pi, -.2, 0, -.03], 20, [-25, 25]),
        ("straight_endpoint", "straight", [80, 0, 0, 0, 0, 0], 80, [-16, -16]),
    ]
    for name, profile_name, state, progress_s, prev in definitions:
        p = profiles[profile_name]
        v = np.full_like(p["s"], .6)
        # Explicit stopping reference at endpoint; this is a fixture definition.
        v[-1] = 0.0
        r = p["kappa"] * v
        ref_time = p["s"] / .6
        index = int(np.searchsorted(p["s"], progress_s, side="right") - 1)
        prev_n = np.asarray(prev, dtype=np.float64)
        raw = compose_observation(
            np.asarray(state, dtype=np.float64), p["x"], p["y"], p["psi"],
            p["kappa"], v, r, p["s"], ref_time,
            t_now=progress_s / .6, prog_idx=index, prev_thrust=prev_n,
            lookahead=LOOKAHEAD,
        )
        if raw.shape != (43,) or raw.dtype != np.float32:
            raise ValueError(f"Observation fixture {name} violates 43-D float32 input")
        if not np.array_equal(raw[-2:], prev_n.astype(np.float32)):
            raise AssertionError(f"Observation fixture {name} lost physical-N previous thrust")
        cases.append({
            "name": name, "kind": "shared_constructor_fixture", "profile": profile_name,
            "state6": state, "progress_s_m": progress_s,
            "prev_published_thrust_n": prev, "raw_obs": raw.tolist(),
        })
    rng = np.random.default_rng(20261003)
    for i in range(64):
        raw = rng.normal(0.0, 2.0, 43).astype(np.float32)
        raw[-2:] = rng.uniform(-25.0, 25.0, 2).astype(np.float32)
        cases.append({"name": f"random_{i:02d}", "kind": "random_raw_supplement",
                      "prev_published_thrust_n": raw[-2:].tolist(), "raw_obs": raw.tolist()})
    return cases


def load_cases(args, report: dict) -> tuple[list[dict], np.ndarray]:
    sys.path.insert(0, str(args.workspace / "usv_rl"))
    from usv_rl import observation
    report["observation_source"] = {
        "path": str(observation.__file__), "sha256": sha256(Path(observation.__file__)),
        "lookahead_m": list(LOOKAHEAD), "fixture_source": "Deterministic state/profile pairs composed through the production shared observation constructor; not recorded telemetry",
    }
    cases = composed_cases(observation.compose_observation)
    raw = np.asarray([c["raw_obs"] for c in cases], dtype=np.float32)
    if args.cases_file:
        saved = np.load(args.cases_file, allow_pickle=False)
        if saved.shape != raw.shape or saved.dtype != np.float32 or not np.array_equal(saved, raw):
            raise ValueError("Frozen raw cases differ from the recorded deterministic shared-constructor fixtures")
        raw = saved
        report["raw_cases_file"] = str(args.cases_file)
        report["raw_cases_sha256"] = sha256(args.cases_file)
    return cases, raw


def prepare(args, report: dict) -> None:
    asset_dir = args.asset_dir or args.workspace / "usv_rl/models/v5/s4_dr"
    hashes = {name: sha256(asset_dir / name) for name in ORIGINAL_SHA256}
    report["original_sha256_before"] = hashes
    if hashes != ORIGINAL_SHA256:
        raise AssertionError("Original assets differ from the independently recorded baseline")
    cases, raw = load_cases(args, report)
    out = args.cases_out or args.report.parent / "raw_obs_cases.npy"
    if out.suffix != ".npy":
        raise ValueError("--cases-out must end in .npy")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        existing = np.load(out, allow_pickle=False)
        if existing.dtype != np.float32 or not np.array_equal(existing, raw):
            raise FileExistsError("Refusing to overwrite a different frozen case asset")
    else:
        np.save(out, raw, allow_pickle=False)
    report.update({
        "phase": "raw_observation_preparation", "prepared": True, "passed": None,
        "raw_cases_file": str(out), "raw_cases_sha256": sha256(out),
        "cases": cases, "case_count": len(cases), "composed_case_count": 8,
        "random_case_count": 64, "versions": package_versions(),
        "note": "Preparation is not model acceptance. Use this same file with exporter --verification-obs and this script --cases-file after creating the new ONNX.",
    })


def validate(args, report: dict) -> None:
    import onnx
    import onnxruntime as ort
    from stable_baselines3 import PPO

    asset_dir = args.asset_dir or args.workspace / "usv_rl/models/v5/s4_dr"
    new_path = args.new_onnx or asset_dir / "policy_physical_n.onnx"
    manifest_path = new_path.with_suffix(".manifest.json")
    report.update({
        "workspace": str(args.workspace), "asset_dir": str(asset_dir),
        "new_onnx": str(new_path), "versions": package_versions(),
        "physical_scale_n": PHYSICAL_SCALE_N, "tolerance_n": TOLERANCE_N,
        "historical_training_range_proven": False,
        "historical_checkpoint_normalizer_pairing_proven": False,
        "scope": "Numerical consistency of the selected checkpoint, normalizer, old graph and new graph at the current symmetric +/-25 N deployment contract",
    })
    before = {name: sha256(asset_dir / name) for name in ORIGINAL_SHA256}
    report["original_sha256_before"] = before
    report["original_sha256_expected"] = ORIGINAL_SHA256
    if before != ORIGINAL_SHA256:
        raise AssertionError("Original assets differ from the independently recorded baseline")

    model = PPO.load(str(asset_dir / "model.zip"), device="cpu")
    model.policy.eval()
    if model.observation_space.shape != (43,) or model.action_space.shape != (2,):
        raise ValueError("Checkpoint dimensions must be 43 observations and 2 actions")
    if not (np.array_equal(model.action_space.low, [-1.0, -1.0]) and
            np.array_equal(model.action_space.high, [1.0, 1.0])):
        raise ValueError("Checkpoint action space must be normalized [-1,1]^2")
    with (asset_dir / "vecnormalize.pkl").open("rb") as handle:
        vn = pickle.load(handle)
    if not vn.norm_obs:
        raise ValueError("Selected normalizer disables norm_obs; diagnose legacy preprocessing before acceptance")
    vn.training = False
    vn.norm_reward = False
    mean_before = np.asarray(vn.obs_rms.mean).copy()
    var_before = np.asarray(vn.obs_rms.var).copy()
    count_before = np.asarray(vn.obs_rms.count).copy()
    if mean_before.shape != (43,) or var_before.shape != (43,):
        raise ValueError("Normalizer statistics must be 43-D")
    if not (np.isfinite(mean_before).all() and np.isfinite(var_before).all() and
            (var_before >= 0).all() and math.isfinite(float(vn.epsilon)) and
            float(vn.epsilon) > 0 and math.isfinite(float(vn.clip_obs)) and float(vn.clip_obs) > 0):
        raise ValueError("Invalid normalizer statistics, epsilon or clip")
    report["vecnormalize"] = {
        "norm_obs": bool(vn.norm_obs), "training": bool(vn.training),
        "norm_reward": bool(vn.norm_reward), "epsilon": float(vn.epsilon),
        "clip_obs": float(vn.clip_obs), "rms_count": float(vn.obs_rms.count),
        "rms_mean": mean_before.tolist(), "rms_var": var_before.tolist(),
    }

    # The only production source imported here is the common observation builder.
    cases, raw = load_cases(args, report)
    normalized = vn.normalize_obs(raw.copy())
    actions, _ = model.predict(normalized, deterministic=True)
    # Explicit independent physical reference; no exporter symbols/buffers.
    expected_n = np.clip(np.asarray(actions, dtype=np.float32), -1.0, 1.0) * 25.0
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    new_session = ort.InferenceSession(str(new_path), options, providers=["CPUExecutionProvider"])
    old_session = ort.InferenceSession(str(asset_dir / "policy.onnx"), options, providers=["CPUExecutionProvider"])
    inputs, outputs = new_session.get_inputs(), new_session.get_outputs()
    if len(inputs) != 1 or inputs[0].name != "obs" or len(inputs[0].shape) != 2 or inputs[0].shape[1] != 43 or inputs[0].type != "tensor(float)":
        raise ValueError("New ONNX input contract must be obs(batch,43), float32")
    if len(outputs) != 1 or outputs[0].name != "thrust" or len(outputs[0].shape) != 2 or outputs[0].shape[1] != 2 or outputs[0].type != "tensor(float)":
        raise ValueError("New ONNX output contract must be thrust(batch,2), float32")
    onnx.checker.check_model(str(new_path))
    start = time.perf_counter()
    actual_n = new_session.run(["thrust"], {"obs": raw})[0]
    report["batch_infer_ms"] = (time.perf_counter() - start) * 1000.0
    old_a = old_session.run(["thrust"], {"obs": raw})[0]
    if actual_n.shape != (len(cases), 2) or not np.isfinite(actual_n).all():
        raise ValueError("New graph returned invalid output shape or non-finite thrust")
    reference_err = np.abs(actual_n - expected_n)
    old_scaled_err = np.abs(actual_n - 25.0 * old_a)
    old_reference_err = np.abs(old_a - np.clip(actions, -1.0, 1.0))
    for i, case in enumerate(cases):
        case.update({
            "sb3_normalized_action": np.asarray(actions[i]).tolist(),
            "expected_thrust_n": expected_n[i].tolist(),
            "new_thrust_n": actual_n[i].tolist(), "old_output_normalized": old_a[i].tolist(),
            "reference_abs_error_n": reference_err[i].tolist(),
            "new_vs_25_old_abs_error_n": old_scaled_err[i].tolist(),
        })
    frozen = (np.array_equal(mean_before, vn.obs_rms.mean) and
              np.array_equal(var_before, vn.obs_rms.var) and
              np.array_equal(count_before, vn.obs_rms.count))
    report.update({
        "cases": cases, "case_count": len(cases), "composed_case_count": 8,
        "random_case_count": 64, "max_reference_abs_error_n": float(reference_err.max()),
        "max_new_vs_25_old_abs_error_n": float(old_scaled_err.max()),
        "max_old_vs_sb3_normalized_abs_error": float(old_reference_err.max()),
        "new_abs_thrust_max_n": float(np.abs(actual_n).max()),
        "old_abs_output_max": float(np.abs(old_a).max()), "vecnormalize_statistics_unchanged": frozen,
        "onnx_checker_passed": True,
        "onnx_contract": {"input": [{"name": v.name, "shape": v.shape, "type": v.type} for v in inputs],
                          "output": [{"name": v.name, "shape": v.shape, "type": v.type} for v in outputs]},
        "onnx_metadata": new_session.get_modelmeta().custom_metadata_map,
        "new_onnx_sha256": sha256(new_path),
    })
    after = {name: sha256(asset_dir / name) for name in ORIGINAL_SHA256}
    report["original_sha256_after"] = after
    report["original_assets_unchanged"] = before == after == ORIGINAL_SHA256
    if manifest_path.exists():
        report["manifest_path"] = str(manifest_path)
        report["manifest_sha256"] = sha256(manifest_path)
        report["manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))
    legacy_reference_error_n = float(old_reference_err.max()) * 25.0
    legacy_preprocessing_agrees = legacy_reference_error_n <= TOLERANCE_N
    report["legacy_preprocessing_agrees_with_independent_reference"] = legacy_preprocessing_agrees
    report["legacy_reference_error_at_current_scale_n"] = legacy_reference_error_n
    report["auxiliary_checks"] = {
        "legacy_preprocessing_agrees_with_independent_reference": legacy_preprocessing_agrees,
        "same_observation_25_times_legacy_within_tolerance":
            float(old_scaled_err.max()) <= TOLERANCE_N if legacy_preprocessing_agrees else None,
    }
    report["requires_scope_review"] = not legacy_preprocessing_agrees
    report["separate_issue"] = (None if legacy_preprocessing_agrees else
        "The legacy graph does not match the selected saved VecNormalize + deterministic SB3 reference. Its 25-times ratio cannot be used as the new graph acceptance oracle. Review preprocessing/checkpoint pairing scope before claiming a scale-only repair.")
    checks = {
        "reference_error_within_tolerance": float(reference_err.max()) <= TOLERANCE_N,
        "new_output_within_physical_bounds": float(np.abs(actual_n).max()) <= 25.0 + TOLERANCE_N,
        "normalizer_statistics_frozen": frozen,
        "original_assets_unchanged": report["original_assets_unchanged"],
    }
    report["checks"] = checks
    if not all(checks.values()):
        raise AssertionError(f"Real asset acceptance failed: {checks}")
    report["passed"] = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/home/trevor/USV"))
    parser.add_argument("--asset-dir", type=Path)
    parser.add_argument("--new-onnx", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--cases-out", type=Path, help="Frozen raw .npy destination for --prepare-only")
    parser.add_argument("--cases-file", type=Path, help="Reuse and verify the previously frozen raw .npy fixtures")
    args = parser.parse_args()
    report = {"passed": False, "started_unix": time.time(), "command": sys.argv}
    code = 0
    try:
        if args.prepare_only:
            prepare(args, report)
        else:
            validate(args, report)
            if report.get("requires_scope_review"):
                code = 2
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
        code = 1
    report["finished_unix"] = time.time()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    summary = {key: report.get(key) for key in ("phase", "prepared", "passed", "requires_scope_review", "auxiliary_checks", "raw_cases_file", "case_count", "max_reference_abs_error_n", "max_new_vs_25_old_abs_error_n", "original_assets_unchanged", "error")}
    print(json.dumps(summary, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
