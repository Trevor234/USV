"""Unit and native integration tests for the paired robustness evaluator."""
from __future__ import annotations

from dataclasses import asdict, replace
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import eval_robustness_ablation as robustness
from eval_robustness_ablation import (
    ARMS, CONTRACT, DEFAULT_LIB_PATH, DT, GP_POOLED, REGIMES, SPLIT_MANIFEST, TICK_NS,
    ExternalWrenchProfile, FusionSolver, FusionSolverError, HydroParams, NavigationNoiseModel,
    USVDynamicModel, forward_with_wrench,
)

V7_ARM = "gp_v7_v6_s4dr_l005_none"
STATE_REFLECTION = np.array([1, -1, -1, 1, -1, -1])


def test_forward_with_wrench_zero_matches_usv_dynamic_model():
    rng = np.random.default_rng(705)
    zero = ExternalWrenchProfile.from_preset("W0", 705)
    for _ in range(100):
        dyn = USVDynamicModel(params=HydroParams().perturbed(rng, 0.25))
        state = rng.uniform(-2.0, 2.0, size=6)
        state[2] = rng.uniform(-math.tau, math.tau)
        thrust = rng.uniform(-25.0, 25.0, size=2)
        expected = dyn.forward(state, thrust)
        np.testing.assert_array_equal(forward_with_wrench(dyn, state, thrust, None, 1.3), expected)
        actual = forward_with_wrench(dyn, state, thrust, zero, 1.3)
        assert np.max(np.abs(actual - expected)) < 1e-14


def test_forward_with_wrench_samples_every_rk4_stage():
    dyn = USVDynamicModel()
    calls = []

    class StageWrench:
        def body_wrench(self, t_s, psi):
            calls.append((t_s, psi))
            return np.array([t_s, 0.0, 0.0])

    state = np.array([0.0, 0.0, 0.2, 0.0, 0.0, 0.5])
    forward_with_wrench(dyn, state, np.zeros(2), StageWrench(), 1.5)
    h = dyn.dt / dyn.rk4_substeps
    expected_times = [
        1.5 + (step + stage) * h for step in range(dyn.rk4_substeps) for stage in (0, 0.5, 0.5, 1)
    ]
    times, headings = np.asarray(calls).T
    np.testing.assert_allclose(times, expected_times, atol=1e-15, rtol=0)
    assert headings[0] == state[2]
    assert headings[1] == pytest.approx(state[2] + h * 0.5 * state[5])
    assert headings[-1] > headings[0]


@pytest.mark.parametrize(
    ("psi", "expected"),
    [(0, (3, 4)), (math.pi / 2, (4, -3)), (math.pi, (-3, -4)), (-math.pi / 2, (-4, 3))],
)
def test_external_wrench_world_to_body_rotation(psi, expected):
    zero = ExternalWrenchProfile.from_preset("W0", 7)
    wrench = replace(zero, theta0=math.atan2(4, 3), F0=5, b_r=0.125)
    fx, fy = wrench.world_force(3.1)
    np.testing.assert_allclose([fx, fy], [3, 4], atol=1e-15, rtol=0)
    actual = wrench.body_wrench(3.1, psi)
    np.testing.assert_allclose(actual, [*expected, 0.125], atol=1e-15, rtol=0)
    assert actual.dtype == np.float64
    assert np.dot(actual[:2], actual[:2]) == pytest.approx(fx * fx + fy * fy, abs=1e-14)


def test_deterministic_pairing_and_orthogonality():
    seed, ticks = 3010, 37
    times = np.arange(ticks) * DT
    headings = np.linspace(-math.pi, math.pi, ticks)

    def realizations(regime, episode_seed):
        wrench_level, noise_level = REGIMES[regime]
        wrench = ExternalWrenchProfile.from_preset(wrench_level, episode_seed)
        noise = NavigationNoiseModel.from_preset(noise_level, episode_seed, ticks)
        wrench_rows = np.stack([wrench.body_wrench(t, psi) for t, psi in zip(times, headings)])
        return wrench_rows, noise.eta_sequence

    combined_wrench, combined_noise = realizations("R4_combined_nominal", seed)
    assert combined_noise.shape == (ticks, 6)
    for _ in ARMS:
        repeated_wrench, repeated_noise = realizations("R4_combined_nominal", seed)
        np.testing.assert_array_equal(combined_wrench, repeated_wrench)
        np.testing.assert_array_equal(combined_noise, repeated_noise)
    wrench_only, no_noise = realizations("R1_wrench_mod", seed)
    no_wrench, noise_only = realizations("R3_noise_rtk", seed)
    np.testing.assert_array_equal(combined_wrench, wrench_only)
    np.testing.assert_array_equal(combined_noise, noise_only)
    np.testing.assert_array_equal(no_noise, np.zeros((ticks, 6)))
    np.testing.assert_array_equal(no_wrench, np.zeros((ticks, 3)))
    different_wrench, different_noise = realizations("R4_combined_nominal", seed + 1)
    assert not np.array_equal(combined_wrench, different_wrench)
    assert not np.array_equal(combined_noise, different_noise)
    harsh_wrench, harsh_noise = realizations("R5_combined_harsh", seed)
    assert not np.array_equal(harsh_wrench, combined_wrench)
    assert not np.array_equal(harsh_noise, combined_noise)

    wrench = ExternalWrenchProfile.from_preset("W1", seed)
    mirrored = wrench.mirrored()
    for time, heading in zip(times, headings):
        np.testing.assert_array_equal(mirrored.body_wrench(time, -heading),
                                      wrench.body_wrench(time, heading) * [1, -1, -1])

    noise = NavigationNoiseModel.from_preset("N1", seed, ticks)
    state = np.array([0.3, 0.5, math.pi + 0.2, 0.3, -0.2, 0.1])
    original = state.copy()
    actual = noise.corrupt(state, 3)
    np.testing.assert_array_equal(state, original)
    assert not np.shares_memory(actual, state)
    expected = original + combined_noise[3]
    expected[2] -= math.tau
    assert -math.pi < actual[2] <= math.pi
    np.testing.assert_allclose(actual, expected, atol=1e-15, rtol=0)
    state[2] = -math.pi
    assert NavigationNoiseModel.from_preset("N0", seed).corrupt(state, 0)[2] == math.pi


def test_controller_cannot_see_ground_truth_state(monkeypatch):
    ep = {
        "episode_name": "spy", "seed": 3010, "maneuver": "straight",
        "cruise_speed": 0.7, "plant_model_file": "spy-actual-plant.json",
    }
    nominal = HydroParams()
    plant = replace(nominal, mass=nominal.mass * 1.2)
    read_json = robustness._read_json

    def read_trial_input(path):
        if path == Path(ep["plant_model_file"]):
            return {"plant_actual": asdict(plant)}
        return {**read_json(path), "hydro": asdict(nominal)}

    monkeypatch.setattr(robustness, "_read_json", read_trial_input)
    monkeypatch.setattr(robustness, "_pooled_gp", lambda _: object())
    odometry, targets, receipts, metric_inputs, solver_updates = [], [], [], [], []
    metric_function = robustness.path_polyline_metrics
    raw = np.array([[40, -40], [40, -40], [0, 0], [0, 0]])
    command_sequence = np.array([[0, 0], [16, -16], [25, -25], [9, -9], [0, 0]])

    class SpyEngine:
        def __init__(self, **_):
            self.sim_ns = None

        def on_reference(self, path, profile):
            assert path.shape[0] == profile.shape[0]

        def on_clock(self, sim_ns):
            self.sim_ns = sim_ns

        def on_odom(self, sim_ns, state):
            assert sim_ns == self.sim_ns
            odometry.append(state.copy())

        def on_plant_receipt(self, **receipt):
            receipts.append({**receipt, "thrust_n": receipt["thrust_n"].copy()})

        def evaluate(self, steady_now_ns):
            assert steady_now_ns == self.sim_ns
            return SimpleNamespace(valid=self.sim_ns != TICK_NS, q_pi=(3.0, 5.0))

    class SpySolver:
        @classmethod
        def from_contract(cls, path):
            assert path == CONTRACT
            return cls()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def set_anchor(self, anchor):
            solver_updates.append(("set_anchor", tuple(anchor)))

    rollout_x, rollout_u = np.zeros((6, 21)), np.zeros((2, 20))

    class SpyController:
        def __init__(self, solver, *, hydro, **_):
            assert hydro == nominal

        def step(self, state, path, profile, *, anchors, q_pi, lambda_pi, prev_x, prev_u, tick_shift):
            tick = len(targets)
            targets.append(state.copy())
            np.testing.assert_array_equal(anchors, command_sequence[tick])
            assert prev_x is None and prev_u is None and tick_shift == 0
            if tick == 1:
                assert q_pi == (0.0, 0.0) and lambda_pi == 0.0
            else:
                assert q_pi == (3.0, 5.0) and lambda_pi == ARMS[V7_ARM].lambda_pi
            if tick == 2:
                # The fallback can only bring the held thrusts 16 N closer to zero.
                raise FusionSolverError("injected solve failure")
            return raw[tick], {"rollout_x": rollout_x, "rollout_u": rollout_u, "solver_ms": 1.0}

        def commit(self, applied):
            solver_updates.append(("commit", tuple(applied)))

        def reset_warmstart(self):
            solver_updates.append(("reset_warmstart",))

    def spy_metrics(states, path, profile_uvr):
        metric_inputs.append(states.copy())
        return metric_function(states, path, profile_uvr)

    monkeypatch.setattr(robustness, "ProposalEngine", SpyEngine)
    monkeypatch.setattr(robustness, "FusionSolver", SpySolver)
    monkeypatch.setattr(robustness, "FusionController", SpyController)
    monkeypatch.setattr(robustness, "path_polyline_metrics", spy_metrics)

    outputs, first_inputs = [], []
    for regime in ("R0_clean", "R3_noise_rtk"):
        for records in (odometry, targets, receipts, metric_inputs, solver_updates):
            records.clear()
        run = robustness.run_robustness_episode(ep, V7_ARM, regime, ticks=4, keep_trajectory=True)
        outputs.append(run)
        first_inputs.append((odometry[0].copy(), targets[0].copy()))
        assert run["solver_failures"] == 1
        assert run["first_solver_error"] == "injected solve failure"
        assert run["ppo_active_pct"] == 75.0
        assert not run["success"]
        np.testing.assert_array_equal(run["u_exec"], command_sequence[:-1])
        assert solver_updates == [
            ("commit", tuple(command_sequence[1])),
            ("commit", tuple(command_sequence[2])),
            ("reset_warmstart",),
            ("set_anchor", tuple(command_sequence[3])),
            ("commit", tuple(command_sequence[4])),
        ]

        starts = np.vstack([np.zeros(6), run["states_end"][:-1]])
        noise_model = NavigationNoiseModel.from_preset(REGIMES[regime][1], ep["seed"], 4)
        for tick, (start, held) in enumerate(zip(starts, run["u_exec"])):
            obs = noise_model.corrupt(start, tick)
            np.testing.assert_array_equal(odometry[tick], obs)
            nominal_dyn = USVDynamicModel(dt=DT, params=nominal)
            np.testing.assert_array_equal(targets[tick], nominal_dyn.forward(obs, held))
            actual_dyn = USVDynamicModel(dt=DT, params=plant)
            np.testing.assert_array_equal(run["states_end"][tick], actual_dyn.forward(start, held))
        for tick, receipt in enumerate(receipts, 1):
            assert {k: v for k, v in receipt.items() if k != "thrust_n"} == {
                "schema_version": "p1-plant-receipt-v3", "disposition": "ok", "execution_index": tick,
                "state_sample_sim_ns": (tick - 1) * TICK_NS, "planned_window_end_sim_ns": tick * TICK_NS,
                "clock_epoch": 0,
            }
            np.testing.assert_array_equal(receipt["thrust_n"], run["u_exec"][tick - 1])
        assert len(receipts) == 3 and len(metric_inputs) == 1
        np.testing.assert_array_equal(metric_inputs[0], run["states_end"])

    for clean_input, noisy_input in zip(*first_inputs):
        np.testing.assert_array_equal(clean_input, np.zeros(6))
        assert not np.array_equal(clean_input, noisy_input)
    np.testing.assert_array_equal(outputs[0]["states_end"], outputs[1]["states_end"])
    assert outputs[0]["cross_track_rmse_m"] == outputs[1]["cross_track_rmse_m"]


class _ProjectedGP:
    def __init__(self, gp):
        self.gp = gp

    def predict(self, features):
        reflected = features[:, [0, 1, 2, 4, 3]] * [1, -1, -1, 1, 1]
        prediction = self.gp.predict(np.concatenate((features, reflected), axis=0))
        mean, mirror_mean = np.split(prediction["mean"], 2)
        ood, mirror_ood = np.split(prediction["ood"], 2)
        return {"mean": 0.5 * (mean + mirror_mean * [1, -1, -1]), "ood": ood | mirror_ood}


class _MirrorToleranceError(AssertionError):
    """Only a measured reflection mismatch qualifies as the expected failure."""


@pytest.fixture
def native_v7():
    pytest.importorskip("onnxruntime")
    arm = ARMS[V7_ARM]
    for path in (Path(DEFAULT_LIB_PATH), arm.onnx, arm.manifest, GP_POOLED, CONTRACT, SPLIT_MANIFEST):
        if not path.is_file():
            pytest.skip(f"Native v7 replay needs {path}")
    try:
        with FusionSolver.from_contract(CONTRACT):
            pass
    except FusionSolverError as exc:
        if isinstance(exc.__cause__, OSError):
            pytest.skip(f"Native solver unavailable. Add /home/trevor/acados/lib to LD_LIBRARY_PATH: {exc}")
        raise


@pytest.mark.parametrize("project_gp", [
    pytest.param(False, id="frozen-pooled-gp", marks=pytest.mark.xfail(
        strict=True, raises=_MirrorToleranceError,
        reason="The frozen pooled GP is measurably asymmetric under port/starboard reflection",
    )),
    pytest.param(True, id="reflection-projected-gp"),
])
def test_z2_mirror_symmetry_under_wrench(project_gp, native_v7, monkeypatch):
    if project_gp:
        # Isolate the wrench, v7 proposal and native solver while retaining GP residuals.
        projected = _ProjectedGP(robustness._pooled_gp(GP_POOLED))
        monkeypatch.setattr(robustness, "_pooled_gp", lambda _: projected)

    episode = next(ep for ep in robustness._read_json(SPLIT_MANIFEST)["episodes"]
                   if ep["split"] == "final_test" and ep["maneuver"] == "left_turn" and ep["seed"] == 3010)
    wrench = ExternalWrenchProfile.from_preset("W1", episode["seed"])
    left = robustness.run_robustness_episode(
        episode, V7_ARM, "R1_wrench_mod", ticks=25, wrench=wrench, keep_trajectory=True,
    )
    right = robustness.run_robustness_episode(
        {**episode, "maneuver": "right_turn"}, V7_ARM, "R1_wrench_mod", ticks=25,
        wrench=wrench.mirrored(), keep_trajectory=True,
    )
    for run in (left, right):
        assert run["solver_failures"] == 0
        assert run["ticks_executed"] == 25
        assert run["ppo_active_pct"] == 100.0
        assert run["success"]

    thrust_error = float(np.max(np.abs(left["u_exec"] - right["u_exec"][:, ::-1])))
    state_errors = np.max(np.abs(left["states_end"] - right["states_end"] * STATE_REFLECTION), axis=0)
    if thrust_error >= 1e-4 or np.max(state_errors) >= 1e-6:
        raise _MirrorToleranceError(
            f"max swapped thrust error = {thrust_error:.9g} N; "
            f"max reflected state errors [x,y,psi,u,v,r] = {state_errors}"
        )
