"""Energy metrics, contract wiring, and candidate gates."""
from __future__ import annotations

import importlib.util
import inspect
import json
import math
import queue
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

import closed_loop_metrics as metrics
import eval_fusion_arms as fusion
import eval_r2_calib as r2
import fusion_env
import ppo_proposal_node
import select_ppo_candidate as selector
from fusion_controller import FusionController, build_frozen_reference
from verify_fusion_clone import _generation_contents, _reference_options, gate_reference


def test_active_energy_policy_matches_runner_defaults_and_artifacts() -> None:
    model_dir = fusion.RUNNER.parent.parent / "model"
    profile = json.loads((model_dir / "scheme_a_active_energy_policy.json").read_text(encoding="utf-8"))
    assert profile["schema"] == "scheme-a-active-energy-policy-v1"
    assert profile["selected_arm"] == "gp_v7_v6_s4dr_l005_curv"
    assert profile["contract_file"] == "contract_controlled_sim_energy.json"
    contract_path = model_dir / profile["contract_file"]
    assert metrics.sha256_file(contract_path) == profile["contract_sha256"]
    for key in ("gp_snapshot", "ppo_model", "ppo_manifest"):
        assert metrics.sha256_file(Path(profile[key])) == profile[f"{key}_sha256"]

    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    for key in ("reference_projection_mode", "reference_lead_s", "Q", "Qf_scale", "R", "Rd"):
        assert profile[key] == contract[key]
    assert profile["obs_contract_version"] == ppo_proposal_node.OBS_CONTRACT_VERSION
    assert tuple(profile["lookahead_m"]) == ppo_proposal_node.DEFAULT_LOOKAHEAD
    assert profile["lambda_pi"] == 0.005
    assert profile["equivariant_z2_se2"] is True
    assert profile["gate"] == {
        "gate_mode": "curv_err",
        "gate_min_kappa": 0.05,
        "gate_min_cte": 0.02,
        "gate_min_psi": 0.04,
        "gate_near_points": 4,
    }
    for factory in (fusion_env.FusionTrackingEnv, fusion_env.make_fusion_env):
        assert inspect.signature(factory).parameters["lambda_pi"].default == profile["lambda_pi"]

    spec = importlib.util.spec_from_file_location("run_scheme_a_closed_loop", fusion.RUNNER)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    args = runner.build_parser().parse_args([
        "--scenario", "pre_switch",
        "--out", "run",
        "--install-root", str(fusion.INSTALL_ROOT),
        "--contract", str(contract_path),
        "--contract-hash", profile["contract_sha256"],
        "--plan", str(fusion.PLAN),
        "--plan-sha256", metrics.sha256_file(fusion.PLAN),
        "--source-hashes", "source_hashes.json",
    ])
    assert args.ppo_model == profile["ppo_model"] == str(ppo_proposal_node.DEFAULT_MODEL_PATH)
    assert args.ppo_manifest == profile["ppo_manifest"] == str(ppo_proposal_node.DEFAULT_MANIFEST_PATH)
    assert args.lambda_pi == 0.0
    assert args.ppo_gate_mode == "none"
    assert args.ppo_lookahead == ""
    assert not args.ppo_proposal


@pytest.mark.parametrize("lead, effective", [(0.0, 0.0), (0.1, 0.1), (None, 0.4), (-1.0, 0.4)])
def test_polyline_time_interpolates_nearest_segment_and_time_lead(lead, effective):
    state = np.array([2.25, 0.5, 0, 0, 0, 0])
    path = np.array([[0, 0, 0], [2, 0, 0], [2, 2, 0]])
    profile = np.array([[1, 0, 0, 0], [2, 0, 0, 2], [4, 0, 2, 3]])
    ref = build_frozen_reference(
        state, path, profile, N=1, projection_mode="polyline_time", lead_s=lead,
    )
    y = np.array([0.5, 0.9]) + 2.0 * effective
    np.testing.assert_allclose(ref, [[2, 2], y, [0, 0], 2 + y, [0, 0], y],
                               rtol=0, atol=1e-14)
    discrete = build_frozen_reference(state, path, profile, N=1)
    np.testing.assert_array_equal(discrete, [[2, 2], [2, 2], [0, 0], [4, 4], [0, 0], [2, 2]])


def test_polyline_time_clamps_endpoints_and_keeps_earlier_ties():
    path = np.array([[0, 0, 0], [0, 0, 0], [2, 0, 0]])
    profile = np.array([[1, 0, 0, 0], [2, 0, 0, 1], [4, 0, 0, 3]])
    state = np.array([-1.0, 0, 0, 0, 0, 0])
    start = build_frozen_reference(state, path, profile, N=0,
                                   projection_mode="polyline_time", lead_s=0.1)
    np.testing.assert_array_equal(start[:, 0], [0, 0, 0, 1.1, 0, 0])
    state[0] = 4.0
    end = build_frozen_reference(state, path, profile, N=1,
                                 projection_mode="polyline_time", lead_s=0.1)
    np.testing.assert_array_equal(end[[0, 3], :], [[2, 2], [4, 4]])

    # Both segments project exactly onto x=1.5, with different profile times.
    path = np.array([[0, 0, 0], [2, 0, 0], [0, 0, 0]])
    state[0] = 1.5
    tied = build_frozen_reference(state, path, profile, N=0,
                                  projection_mode="polyline_time", lead_s=0.0)
    np.testing.assert_array_equal(tied[[0, 3], 0], [1.5, 1.75])


def test_polyline_time_unwraps_heading_and_falls_back_without_profile():
    path = np.array([[0, 0, math.pi - 0.2], [2, 0, -math.pi + 0.2]])
    profile = np.array([[1, 0, 0, 0], [2, 0, 0, 1]])
    state = np.array([0.8, 0, math.pi - 0.3, 0, 0, 0])
    ref = build_frozen_reference(state, path, profile, N=2, dt=0.25,
                                 projection_mode="polyline_time", lead_s=0.1)
    np.testing.assert_allclose(ref[2], [math.pi, math.pi + 0.1, math.pi + 0.2],
                               rtol=0, atol=1e-14)
    fallback = build_frozen_reference(state, path, profile[:1], N=1,
                                      projection_mode="polyline_time", lead_s=0.1)
    np.testing.assert_array_equal(fallback[[0, 3], :], [[2, 2], [0.6, 0.6]])
    np.testing.assert_allclose(fallback[2], [math.pi + 0.2] * 2, rtol=0, atol=1e-14)
    single = build_frozen_reference(state, path[:1], profile[:1], N=0,
                                    projection_mode="polyline_time", lead_s=0.1)
    assert single[3, 0] == 0.6


@pytest.mark.parametrize("mode, lead", [("unknown", 0.0), ("polyline_time", -0.1),
                                       ("polyline_time", math.nan), ("discrete_offset", math.inf)])
def test_polyline_time_rejects_invalid_options(mode, lead):
    with pytest.raises(ValueError):
        build_frozen_reference(np.zeros(6), np.empty((0, 3)), None,
                               projection_mode=mode, lead_s=lead)


def test_clone_gate_checks_logged_projection_and_uses_controlled_sim_weights(tmp_path):
    contract = {
        "schema": "p1-execution-contract-v2-sim", "qualification": "controlled_sim",
        "reference_projection_mode": "polyline_time", "reference_lead_s": 0.1,
        "Q": [35, 35, 60, 25, 1, 8], "R": [0.07, 0.08], "Rd": [0.6, 0.6], "Qf_scale": 9,
    }
    _write_json(tmp_path / "plan.json", {"activation_plan": [
        {"generation": 1, "content": "M0"}, {"generation": 2, "content": "M1"},
        {"generation": 3, "content": "M0"},
    ]})
    contents = _generation_contents(contract, tmp_path)
    assert contents[1] == contents[3]
    assert contents[2][19:] == contents[1][19:] == [35, 35, 60, 25, 1, 8, 0.07, 0.08, 0.6, 0.6, 9]
    assert [i for i, (a, b) in enumerate(zip(contents[1], contents[2])) if a != b] == [0, 9, 13]
    assert [contents[2][i] for i in (0, 9, 13)] == [15.0, -2.4, -4.4]
    diagnostic = {**contract, "schema": "p1-execution-contract-v2"}
    assert _generation_contents(diagnostic, tmp_path)[1][19:] == [
        20, 20, 50, 8, 1, 8, 0.05, 0.05, 0.2, 0.2, 8,
    ]
    assert _reference_options(diagnostic) == ("discrete_offset", None)

    state = np.array([0.8, 0, 0, 0, 0, 0])
    path = np.array([[0, 0, 0], [2, 0, 0]])
    profile = np.array([[1, 0, 0, 0], [2, 0, 0, 1]])
    mode, lead = _reference_options(contract)
    ref = build_frozen_reference(state, path, profile, projection_mode=mode, lead_s=lead)
    job = {"job_id": 7, "target_tick": 12, "reference": ref.T.flatten(), "target_state": state}
    logged = {"reference_mode": "profile_time", "job": {
        "reference_projection_mode": mode, "reference_lead_s": lead,
    }}
    assert gate_reference([{"job": job}], path, profile, 2, 0.6, mode, lead, {7: logged})["passed"]
    logged["job"]["reference_projection_mode"] = "discrete_offset"
    result = gate_reference([{"job": job}], path, profile, 2, 0.6, mode, lead, {7: logged})
    assert not result["passed"]
    assert result["first_metadata_mismatch_tick"] == 12


def _write_json(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


@pytest.mark.parametrize(("options", "mode", "lead"), [
    ({}, "discrete_offset", None),
    ({"reference_projection_mode": "polyline_time", "reference_lead_s": 0.1}, "polyline_time", 0.1),
])
def test_fusion_env_uses_contract_reference_and_nominal_hydro(tmp_path, monkeypatch, options, mode, lead):
    contract = tmp_path / "contract.json"
    _write_json(contract, {"hydro": {"Xu": -3.0, "Xuu": -13.0}, **options})
    solver = Mock()
    gp_snapshot = tmp_path / "gp.json"
    gp_loader = Mock()
    monkeypatch.setattr(fusion_env, "_FUSION_IMPORTS", {
        "FusionController": FusionController, "FusionSolver": solver, "load_pooled_gp": gp_loader,
    })

    env = fusion_env.FusionTrackingEnv(
        contract_path=contract, gp_snapshot=gp_snapshot, use_mode_energy=True,
        drag_ff_gain=1.0, hydro_dr_frac=0.2,
    )
    solver.from_contract.assert_called_once_with(contract, lib_path=None)
    gp_loader.assert_called_once_with(gp_snapshot)
    assert env.lambda_pi == 0.005
    assert env.controller.projection_mode == mode
    assert env.controller.lead_s == lead
    assert env.controller.hydro is env._base.base_hydro is env.model.params is env.base_hydro
    assert (env.cost_params.ff_xu, env.cost_params.ff_xuu) == (-3.0, -13.0)

    env.reset(seed=42)
    assert (env.model.params.Xu, env.model.params.Xuu) != (-3.0, -13.0)
    assert (env.cost_params.ff_xu, env.cost_params.ff_xuu) == (-3.0, -13.0)


@pytest.mark.parametrize(("field", "value"), [
    ("reference_projection_mode", "unknown"),
    ("reference_lead_s", -0.1),
    ("reference_lead_s", 2.1),
    ("reference_lead_s", math.nan),
    ("reference_lead_s", None),
])
def test_fusion_env_rejects_invalid_contract_reference(tmp_path, monkeypatch, field, value):
    contract = tmp_path / "contract.json"
    _write_json(contract, {"hydro": {}, field: value})
    fusion_modules = Mock()
    monkeypatch.setattr(fusion_env, "_fusion_modules", fusion_modules)
    with pytest.raises(ValueError, match=field):
        fusion_env.FusionTrackingEnv(contract_path=contract, gp_snapshot=tmp_path / "gp.json")
    fusion_modules.assert_not_called()


@pytest.fixture
def synthetic_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, list[dict]]:
    _write_json(tmp_path / "run.json", {"run_id": "synthetic"})
    _write_json(tmp_path / "check.json", {"run_id": "synthetic", "verdict": "PASS"})
    (tmp_path / "scenario_path.txt").write_text("0 0 0 0\n4 0 0 1\n", encoding="utf-8")
    (tmp_path / "scenario_profile.txt").write_text("0 0 0 0\n0 0 0 1\n", encoding="utf-8")
    admitted: list[dict] = []
    monkeypatch.setattr(metrics, "extract_run", lambda *args, **kwargs: SimpleNamespace(admitted=admitted))
    return tmp_path, admitted


@pytest.mark.parametrize("progress_m", [4.0, 0.0])
def test_energy_metrics(synthetic_run: tuple[Path, list[dict]], progress_m: float) -> None:
    run_dir, admitted = synthetic_run
    for tick, thrust in enumerate(([4.0, 4.0], [2.0, -2.0], [0.0, 2.0]), start=1):
        x = [progress_m * tick / 3, 0.0, 0.0, 0.0, 0.0, 0.0]
        admitted.append({"tick": tick, "q_exec": thrust, "x_start": x, "x_end": x,
                         "y_k": [0.0] * 3, "z_k": [0.0] * 5})

    run = metrics.evaluate_closed_loop_run(run_dir, reuse_verified_check_json=True)
    effort = run["control_effort"]
    assert run["geometric_tracking"]["along_track_progress_m"] == progress_m
    assert effort["tv_per_step"] == 7.0
    assert effort["tv_total"] == 14.0
    assert effort["thrust_l2_dt"] == pytest.approx(44 * metrics.DT_S)
    assert effort["common_mode_l2_dt"] == pytest.approx(34 * metrics.DT_S)
    assert effort["diff_mode_l2_dt"] == pytest.approx(10 * metrics.DT_S)
    assert effort["common_mode_l2_dt"] + effort["diff_mode_l2_dt"] == pytest.approx(effort["thrust_l2_dt"])
    assert effort["energy_per_meter"] == pytest.approx(44 * metrics.DT_S / max(progress_m, 1e-6))
    assert effort["diff_mode_fraction"] == pytest.approx(10 / 44)
    assert effort["opposing_thrust_fraction"] == pytest.approx(1 / 3)

    legacy = {**run, "control_effort": {key: effort[key] for key in ("tv_per_step", "tv_total", "thrust_l2_dt")}}
    mixed_summary = fusion._aggregate_arm([run, legacy])
    legacy_summary = fusion._aggregate_arm([legacy])
    for key in ("energy_per_meter", "common_mode_l2_dt", "diff_mode_l2_dt", "diff_mode_fraction"):
        assert mixed_summary[key] == {"mean": effort[key]}
        assert legacy_summary[key] == {"mean": None}


def test_empty_run_has_zero_control_effort(synthetic_run: tuple[Path, list[dict]]) -> None:
    run_dir, _ = synthetic_run
    result = metrics.evaluate_closed_loop_run(run_dir, reuse_verified_check_json=True)
    assert result["control_effort"] == dict.fromkeys([
        "tv_per_step", "tv_total", "thrust_l2_dt", "energy_per_meter", "common_mode_l2_dt",
        "diff_mode_l2_dt", "diff_mode_fraction", "opposing_thrust_fraction",
    ], 0.0)


@pytest.fixture
def cached_episode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    contract = tmp_path / "first_contract.json"
    source_hashes = tmp_path / "source_hashes.json"
    plan = tmp_path / "plan.json"
    _write_json(contract, {"revision": 1})
    _write_json(source_hashes, {})
    _write_json(plan, {})
    monkeypatch.setattr(fusion, "PLAN", plan)
    run_dir = tmp_path / "episode"
    run_dir.mkdir()
    (run_dir / "contract.json").write_bytes(contract.read_bytes())
    _write_json(run_dir / "run.json", {"run_id": "cached"})
    _write_json(run_dir / "check.json", {"run_id": "cached", "verdict": "PASS"})
    cache = {
        "source_hashes_sha256": metrics.sha256_file(source_hashes),
        "run_json_sha256": metrics.sha256_file(run_dir / "run.json"),
        "contract_sha256": metrics.sha256_file(contract),
        "gp_keys": [],
        "metrics": {"checker_passed": True, "decisions_total": 3, "control_effort": {"energy_per_meter": 1.0}},
    }
    cache_path = run_dir / "eval_cache_v2.json"
    _write_json(cache_path, cache)
    domains: queue.Queue[int] = queue.Queue()
    domains.put(91)
    kwargs = dict(run_dir=run_dir, ep={"episode_name": "test", "maneuver": "straight", "seed": 0,
                                      "plant_model_file": tmp_path / "plant.json"},
                  stop_decisions=3, domain_queue=domains, gp_models={}, source_hashes=source_hashes,
                  max_attempts=1)
    return SimpleNamespace(contract=contract, cache=cache, cache_path=cache_path, kwargs=kwargs)


@pytest.mark.parametrize("same_path", [False, True])
def test_run_episode_invalidates_changed_contract(
    cached_episode: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, same_path: bool,
) -> None:
    episode = cached_episode
    runner = Mock()
    evaluate = Mock(return_value={**episode.cache["metrics"], "control_effort": {"energy_per_meter": 2.0}})
    monkeypatch.setattr(fusion.subprocess, "run", runner)
    monkeypatch.setattr(fusion, "evaluate_closed_loop_run", evaluate)
    assert fusion._run_episode(**episode.kwargs, contract_path=episode.contract)["reused"]
    runner.assert_not_called()
    evaluate.assert_not_called()

    changed_contract = episode.contract if same_path else episode.contract.with_name("second_contract.json")
    _write_json(changed_contract, {"revision": 2})
    expected_sha = metrics.sha256_file(changed_contract)

    def fake_runner(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        assert cmd[cmd.index("--contract") + 1] == str(changed_contract)
        assert cmd[cmd.index("--contract-hash") + 1] == expected_sha
        run_dir = Path(cmd[cmd.index("--out") + 1])
        run_dir.mkdir()
        (run_dir / "contract.json").write_bytes(changed_contract.read_bytes())
        _write_json(run_dir / "run.json", {"run_id": "fresh"})
        _write_json(run_dir / "check.json", {"run_id": "fresh", "verdict": "PASS"})
        return SimpleNamespace(returncode=0)

    runner.side_effect = fake_runner
    fresh = fusion._run_episode(**episode.kwargs, contract_path=changed_contract)
    assert fresh["reused"] is False
    assert fresh["control_effort"]["energy_per_meter"] == 2.0
    assert json.loads(episode.cache_path.read_text())["contract_sha256"] == expected_sha
    assert evaluate.call_args.kwargs["contract_path"] == changed_contract
    assert fusion._run_episode(**episode.kwargs, contract_path=changed_contract)["reused"]
    runner.assert_called_once()
    evaluate.assert_called_once()


@pytest.mark.parametrize(("old_options", "new_options"), [
    ({}, {"gate_mode": "curv_err"}),
    ({"gate_mode": "curv_err"}, {}),
    ({"gate_mode": "curv_err"}, {"gate_mode": "curv_err_cmcap"}),
    *[({"gate_mode": "curv_err_cmcap"}, {"gate_mode": "curv_err_cmcap", field: value})
      for field, value in {
          "gate_min_kappa": 0.08, "gate_min_cte": 0.03, "gate_min_psi": 0.05,
          "gate_near_points": 3, "gate_cm_cap_margin": 0.6, "gate_u_lag_allow": 0.04,
      }.items()],
])
def test_run_episode_invalidates_changed_gate(cached_episode, monkeypatch, old_options, new_options):
    episode = cached_episode
    run_dir = episode.kwargs["run_dir"]

    def write_run(options: dict) -> None:
        ppo = {"enabled": True, "lambda_pi": 0.001}
        if options:
            ppo["gate"] = {**ppo_proposal_node.GATE_DEFAULTS, **options}
        _write_json(run_dir / "run.json", {"run_id": "gate-test", "ppo_proposal": ppo})
        _write_json(run_dir / "check.json", {"run_id": "gate-test", "verdict": "PASS"})

    write_run(old_options)
    episode.cache["run_json_sha256"] = metrics.sha256_file(run_dir / "run.json")
    _write_json(episode.cache_path, episode.cache)

    def fake_runner(cmd, **kwargs):
        expected_gate = {**ppo_proposal_node.GATE_DEFAULTS, **new_options} if new_options else {}
        for field in ppo_proposal_node.GATE_DEFAULTS:
            flag = "--ppo-" + field.replace("_", "-")
            if field in expected_gate:
                assert cmd[cmd.index(flag) + 1] == str(expected_gate[field])
            else:
                assert flag not in cmd
        run_dir.mkdir()
        (run_dir / "contract.json").write_bytes(episode.contract.read_bytes())
        write_run(new_options)
        return SimpleNamespace(returncode=0)

    runner = Mock(side_effect=fake_runner)
    evaluate = Mock(return_value={**episode.cache["metrics"]})
    monkeypatch.setattr(fusion.subprocess, "run", runner)
    monkeypatch.setattr(fusion, "evaluate_closed_loop_run", evaluate)
    kwargs = dict(episode.kwargs, contract_path=episode.contract, ppo_proposal=True, lambda_pi=0.001)
    assert fusion._run_episode(**kwargs, **old_options)["reused"] is True
    runner.assert_not_called()
    evaluate.assert_not_called()
    assert fusion._run_episode(**kwargs, **new_options)["reused"] is False
    assert fusion._run_episode(**kwargs, **new_options)["reused"] is True
    runner.assert_called_once()
    evaluate.assert_called_once()


@pytest.mark.parametrize("missing_field", ["contract_sha256", "energy_per_meter"])
def test_run_episode_refreshes_legacy_cache_without_runner(
    cached_episode: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, missing_field: str,
) -> None:
    episode = cached_episode
    current_metrics = {**episode.cache["metrics"], "control_effort": {"energy_per_meter": 3.0}}
    if missing_field == "contract_sha256":
        del episode.cache[missing_field]
    else:
        del episode.cache["metrics"]["control_effort"][missing_field]
    _write_json(episode.cache_path, episode.cache)
    runner = Mock(side_effect=AssertionError("should reuse the checked run"))
    evaluate = Mock(return_value=current_metrics)
    monkeypatch.setattr(fusion.subprocess, "run", runner)
    monkeypatch.setattr(fusion, "evaluate_closed_loop_run", evaluate)

    refreshed = fusion._run_episode(**episode.kwargs, contract_path=episode.contract)
    assert refreshed["reused"] is True
    evaluate.assert_called_once_with(
        episode.kwargs["run_dir"], source_hashes=episode.kwargs["source_hashes"],
        gp_models_by_sha={}, reuse_verified_check_json=True, contract_path=episode.contract,
    )
    cache = json.loads(episode.cache_path.read_text())
    assert cache["contract_sha256"] == metrics.sha256_file(episode.contract)
    assert cache["metrics"]["control_effort"]["energy_per_meter"] == 3.0
    runner.assert_not_called()


def test_run_batch_accepts_contract_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    default_contract = tmp_path / "default.json"
    override_contract = tmp_path / "override.json"
    run_episode = Mock(return_value={"geometric_tracking": {"cross_track_rmse_m": 0.25},
                                     "latency_ms": {"freeze_to_publish_e2e": {"p95": 1.0}}})
    monkeypatch.setattr(r2, "_run_episode", run_episode)
    monkeypatch.setattr(r2, "_extract_run_telemetry", lambda path: {})
    ep = {"episode_name": "straight"}
    r2._run_batch(
        out_dir=tmp_path, tasks=[("default", ep, {"gp": None}),
                                ("override", ep, {"gp": None, "contract": str(override_contract)})],
        arm_names=["default", "override"], gp_models={}, source_hashes=tmp_path / "source_hashes.json",
        workers=1, base_domain_id=91, stop_decisions=3, resume=True, contract_path=default_contract,
    )
    assert [call.kwargs["contract_path"] for call in run_episode.call_args_list] == [
        default_contract, override_contract,
    ]


@pytest.mark.parametrize("override", [False, True])
def test_select_ppo_candidate_forwards_and_records_contract(tmp_path, monkeypatch, override):
    candidates = tmp_path / "candidates.json"
    manifest = tmp_path / "split_manifest.json"
    _write_json(candidates, {"candidates": [{"name": "candidate"}]})
    _write_json(manifest, {"episodes": [{"episode_name": "a", "split": "calibration", "seed": 0}]})
    monkeypatch.setattr(selector, "SPLIT_MANIFEST", manifest)
    monkeypatch.setattr(selector, "_load_r2_gps", lambda: (tmp_path / "pooled.json", {}))
    monkeypatch.setattr(selector.MultiChannelSparseGP, "load", Mock(return_value=SimpleNamespace(snapshot_sha256="gp")))
    ref = {"ep_tag": "s0_a", "checker_passed": True, "control_effort": {"tv_per_step": 1.0}}
    batch = Mock(return_value=({
        selector.REF_ARM: [{**ref, "geometric_tracking": {"cross_track_rmse_m": 0.5}}],
        "gp_candidate": [{**ref, "geometric_tracking": {"cross_track_rmse_m": 0.49}}],
    }, {}))
    monkeypatch.setattr(selector, "_run_batch", batch)

    out = tmp_path / "selection"
    args = ["--candidates", str(candidates), "--out", str(out), "--seeds", "0"]
    expected_contract = fusion.CONTRACT.resolve()
    if override:
        expected_contract = tmp_path / "override.json"
        _write_json(expected_contract, {"test": "override"})
        monkeypatch.chdir(tmp_path)
        args += ["--contract", expected_contract.name]

    assert selector.main(args) == 0
    batch.assert_called_once()
    assert batch.call_args.kwargs["contract_path"] == expected_contract
    doc = json.loads((out / "selection.json").read_text(encoding="utf-8"))
    assert doc["contract"] == str(expected_contract)
    assert doc["contract_sha256"] == metrics.sha256_file(expected_contract)
    assert f"`{expected_contract.name}`" in (out / "selection.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(("flags", "selected"), [
    ([], "expensive"),
    (["--max-delta-e-per-m", "0"], "short"),
    (["--min-progress-ratio", "0.9"], "expensive"),
    (["--max-delta-e-per-m", "0", "--min-progress-ratio", "0.9"], "balanced"),
    (["--max-delta-e-per-m", "-2", "--min-progress-ratio", "0.9"], None),
])
def test_select_ppo_candidate_energy_and_progress_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flags: list[str], selected: str | None,
) -> None:
    candidates_path = tmp_path / "candidates.json"
    manifest_path = tmp_path / "split_manifest.json"
    _write_json(candidates_path, {"candidates": [{"name": name} for name in ("expensive", "short", "balanced")]})
    _write_json(manifest_path, {"episodes": [
        {"episode_name": tag, "split": "calibration", "seed": i} for i, tag in enumerate(("a", "b"))
    ]})

    def runs(cte: float, tv: float, progress: tuple[float, float], energy: tuple[float, float]) -> list[dict]:
        return [
            {"ep_tag": tag, "checker_passed": True,
             "geometric_tracking": {"cross_track_rmse_m": cte, "along_track_progress_m": p},
             "control_effort": {"tv_per_step": tv, "thrust_l2_dt": p * e, "energy_per_meter": e}}
            for tag, p, e in zip(("s0_a", "s0_b"), progress, energy)
        ]

    by_arm = {
        selector.REF_ARM: runs(0.50, 4.0, (8.0, 12.0), (2.0, 4.0)),
        "gp_expensive": runs(0.49, 1.0, (7.5, 12.5), (4.0, 6.0)),
        "gp_short": runs(0.49, 2.0, (5.0, 10.0), (1.0, 3.0)),
        "gp_balanced": runs(0.49, 3.0, (8.0, 10.0), (2.0, 4.0)),
    }
    monkeypatch.setattr(selector, "SPLIT_MANIFEST", manifest_path)
    monkeypatch.setattr(selector, "_load_r2_gps", lambda: (tmp_path / "pooled.json", {}))
    monkeypatch.setattr(selector, "MultiChannelSparseGP",
                        SimpleNamespace(load=lambda path: SimpleNamespace(snapshot_sha256="gp")))
    monkeypatch.setattr(selector, "_run_batch", lambda **kwargs: (by_arm, {}))

    out = tmp_path / "selection"
    assert selector.main(["--candidates", str(candidates_path), "--out", str(out), "--seeds", "0", *flags]) == 0
    doc = json.loads((out / "selection.json").read_text())
    assert doc["selected"] == selected
    optional_gates = {flag[2:].replace("-", "_"): float(value) for flag, value in zip(flags[::2], flags[1::2])}
    assert doc["gates"] == {"delta_cte_mean_max": selector.DELTA_GATE, "ci95_upper_max": selector.CI_UPPER_GATE,
                            **optional_gates}
    balanced = next(record for record in doc["ranking"] if record["name"] == "balanced")
    assert balanced["energy_mean"] == 28.0
    assert balanced["energy_per_meter_mean"] == 3.0
    assert balanced["delta_e_per_m_mean"] == 0.0
    assert balanced["progress_m_mean"] == 9.0
    assert balanced["progress_ratio"] == 0.9
    report = (out / "selection.md").read_text(encoding="utf-8")
    assert "| 28 | 3 | 0 | 9 | 0.9 |" in report
    if selected is None:
        assert "进度门槛" in doc["reason"]
    else:
        assert json.loads((out / "selected" / "selection.json").read_text()) == doc
