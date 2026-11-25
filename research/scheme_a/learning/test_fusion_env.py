import json
from unittest.mock import Mock

import numpy as np
import pytest

import fusion_env


@pytest.fixture
def fusion_factory(tmp_path, monkeypatch):
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"hydro": {}}), encoding="utf-8")
    controller = Mock()
    controller.step.return_value = (
        np.array([22.0, -21.0]), {"rollout_x": np.zeros((2, 6)), "rollout_u": np.zeros((1, 2))},
    )
    monkeypatch.setattr(fusion_env, "_FUSION_IMPORTS", {
        "FusionController": Mock(return_value=controller),
        "FusionSolver": Mock(),
        "load_pooled_gp": Mock(),
    })

    def make(**kwargs):
        return fusion_env.make_fusion_env(
            {"path_type": "straight", "dt": 0.2, "d_t_max": 80.0, "reward_scale": 0.2},
            42, contract_path=contract, gp_snapshot=tmp_path / "gp.json", **kwargs,
        )()

    return make


@pytest.mark.parametrize("penalty", [-0.0004, np.nan, np.inf, -np.inf])
def test_invalid_proposal_penalty(penalty, tmp_path):
    with pytest.raises(ValueError, match="r_qpi_u0"):
        fusion_env.FusionTrackingEnv(
            r_qpi_u0=penalty, contract_path=tmp_path / "contract.json", gp_snapshot=tmp_path / "gp.json",
        )


def test_zero_penalty_matches_default_reward_and_transition(fusion_factory):
    default = fusion_factory()
    zero = fusion_factory(r_qpi_u0=0.0)
    try:
        for env in (default, zero):
            env.reset(seed=42)
        action = np.array([0.4, -0.2])
        baseline = default.step(action)
        actual = zero.step(action)
        np.testing.assert_array_equal(actual[0], baseline[0])
        assert actual[1:4] == baseline[1:4]
        assert actual[4]["q_pi_penalty"] == baseline[4]["q_pi_penalty"] == 0.0
    finally:
        default.close()
        zero.close()


@pytest.mark.parametrize("action", [np.array([0.4, -0.2]), np.array([0.0, 0.0])])
def test_quadratic_penalty_uses_rate_limited_applied_thrust(fusion_factory, action):
    weight = 0.0004
    baseline = fusion_factory()
    penalized = fusion_factory(r_qpi_u0=weight)
    try:
        for env in (baseline, penalized):
            env.reset(seed=42)
        baseline_obs, baseline_reward, baseline_terminated, baseline_truncated, _ = baseline.step(action)
        obs, reward, terminated, truncated, info = penalized.step(action)
        applied = np.array([16.0, -16.0])
        proposal = 25.0 * action
        expected_penalty = 0.2 * weight * np.sum((proposal - applied) ** 2)
        np.testing.assert_array_equal(info["applied_thrust"], applied)
        np.testing.assert_array_equal(info["q_pi"], proposal)
        np.testing.assert_array_equal(info["u0"], [22.0, -21.0])
        assert info["q_pi_penalty"] == pytest.approx(expected_penalty)
        assert reward == pytest.approx(baseline_reward - expected_penalty)
        np.testing.assert_array_equal(obs, baseline_obs)
        assert (terminated, truncated) == (baseline_terminated, baseline_truncated)
    finally:
        baseline.close()
        penalized.close()
