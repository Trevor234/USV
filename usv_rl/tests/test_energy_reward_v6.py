from dataclasses import replace
from unittest.mock import Mock

import numpy as np
import pytest

from usv_rl.dynamics import HydroParams
from usv_rl.envs.reward import TrackingCostParams, tracking_cost
from usv_rl.envs.usv_tracking_env import UsvTrackingEnv
from usv_rl.evaluate import run_episodes
from usv_rl.train import ROOT, load_configs


def _reward_at_reference(thrust, speed, params):
    applied = np.array(thrust, dtype=np.float64)
    state = np.array([0.0, 0.0, 0.0, speed, 0.0, 0.0])
    return tracking_cost(state, applied, applied, speed, 0.0, 0.0, 0.0, 0.0, params)


@pytest.mark.parametrize("thrust", [(3.0, -5.0), (4.0, 4.0), (-1.5, 1.5)])
def test_equal_mode_weights_without_feedforward_match_legacy_reward(thrust):
    # Binary-exact inputs keep the comparison exact despite the reordered arithmetic.
    legacy = TrackingCostParams(r_thrust=0.125)
    mode = replace(legacy, use_mode_energy=True, drag_ff_gain=0.0, r_cm=0.125, r_dm=0.125)
    legacy_reward = _reward_at_reference(thrust, 0.7, legacy)
    assert legacy_reward == -legacy.reward_scale * legacy.r_thrust * sum(t ** 2 for t in thrust)
    assert _reward_at_reference(thrust, 0.7, mode) == legacy_reward


@pytest.mark.parametrize("speed", [0.7, -0.7])
def test_common_mode_penalty_is_zero_at_drag_feedforward(speed):
    params = TrackingCostParams(use_mode_energy=True, drag_ff_gain=1.0)
    hydro = HydroParams()
    equilibrium = 0.5 * (-hydro.Xu - hydro.Xuu * abs(speed)) * speed
    assert _reward_at_reference([equilibrium, equilibrium], speed, params) == 0.0
    assert _reward_at_reference([equilibrium + 1, equilibrium + 1], speed, params) < 0.0


def test_opposing_thrust_costs_more_than_equal_l2_common_thrust():
    params = TrackingCostParams(use_mode_energy=True, r_cm=0.08, r_dm=0.14)
    common = _reward_at_reference([4.0, 4.0], 0.7, params)
    opposing = _reward_at_reference([-4.0, 4.0], 0.7, params)
    assert opposing < common < 0.0


def test_feedforward_uses_nominal_hydro_under_domain_randomization():
    hydro = HydroParams(Xu=-3.0, Xuu=-13.0)
    env = UsvTrackingEnv(hydro_params=hydro, hydro_dr_frac=0.2,
                         use_mode_energy=True, drag_ff_gain=1.0)
    env.reset(seed=42)

    assert env.base_hydro is hydro
    assert env.model.params.Xu != hydro.Xu
    assert env.model.params.Xuu != hydro.Xuu
    assert env.cost_params.ff_xu == hydro.Xu
    assert env.cost_params.ff_xuu == hydro.Xuu


@pytest.mark.parametrize(("name", "value"), [
    ("r_cm", -1.0), ("r_cm", float("inf")), ("r_dm", -1.0), ("r_dm", float("nan")),
    ("drag_ff_gain", -0.1), ("drag_ff_gain", 2.1), ("drag_ff_gain", float("inf")),
])
def test_invalid_energy_params_are_rejected(name, value):
    with pytest.raises(ValueError, match=name):
        UsvTrackingEnv(**{name: value})


@pytest.mark.parametrize("config", ["v6_energy.yaml", "v6_fusion.yaml"])
def test_energy_configs_load_complete_blocks_with_divisible_batches(config):
    default_ppo, _ = load_configs(None)
    ppo_cfg, env_cfg = load_configs(str(ROOT / "configs" / config))
    ppo = ppo_cfg["ppo"]
    assert ppo.keys() == default_ppo["ppo"].keys()
    assert ppo_cfg["eval"].keys() == default_ppo["eval"].keys()
    assert ppo["n_steps"] * ppo_cfg["n_envs"] % ppo["batch_size"] == 0
    assert ppo_cfg["curriculum"][-1]["name"] == "s4_dr"
    assert UsvTrackingEnv(**env_cfg).cost_params.use_mode_energy


def test_evaluation_metrics_use_applied_thrust_and_episode_progress():
    def transition(thrust, surge_error, progress, done):
        return None, None, [done], [{
            "applied_thrust": thrust, "signed_surge_error": surge_error,
            "progress_s": progress, "total_s": 4.0,
        }]

    venv = Mock()
    venv.get_attr.return_value = [0.25]
    venv.step.side_effect = [
        transition([4.0, 4.0], -0.2, 1.0, False),
        transition([2.0, -2.0], 0.1, 4.0, True),
        transition([0.0, 2.0], 0.4, 0.0, True),
    ]
    result = run_episodes(venv, lambda _venv, _obs: np.zeros(2), episodes=2)
    assert result["energy_mean"] == 5.5
    assert result["cm_energy_mean"] == 4.25
    assert result["dm_energy_mean"] == 1.25
    assert result["opposing_thrust_fraction"] == pytest.approx(1 / 3)
    assert result["progress_m_mean"] == 2.0
    assert result["progress_frac_mean"] == 0.5
    assert result["energy_per_meter_mean"] == pytest.approx((10 / 4 + 1 / 1e-6) / 2)
    assert result["signed_surge_error_mean"] == pytest.approx(0.1)
