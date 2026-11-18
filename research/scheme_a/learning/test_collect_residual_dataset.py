#!/usr/bin/env python3
"""Unit tests for WP3 scenarios, splits, and plant profile validation."""
from __future__ import annotations

import json
from pathlib import Path

from collect_residual_dataset import (
    SCENARIOS_PATH,
    build_episode_plan,
    build_plant_profile_files,
)


def test_full_split_disjoint_and_heldout_isolated() -> None:
    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    plan = build_episode_plan(scenarios, "full")
    eps = plan["episodes"]
    nom = plan["nominal_gate"]
    assert len(eps) == 60
    assert len(nom) == 6

    names = [e["episode_name"] for e in eps]
    assert len(names) == len(set(names))

    counts = {}
    for e in eps:
        counts[e["split"]] = counts.get(e["split"], 0) + 1
    assert counts == {"train": 36, "calibration": 12, "final_test": 12}

    # Zero leakage: heldout_combination ONLY in final_test; unseen maneuvers NOT in train.
    for e in eps:
        if e["profile"] == "heldout_combination":
            assert e["split"] == "final_test"
        if e["maneuver"] in ("right_turn", "rate_limited_thrust_step"):
            assert e["split"] != "train"
        assert e["profile"] != "nominal"


def test_pilot_covers_all_6_maneuvers_and_profiles(tmp_path: Path) -> None:
    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    models = build_plant_profile_files(scenarios, tmp_path / "models")
    assert set(models.keys()) == {
        "nominal",
        "mass_plus_10pct",
        "surge_damping_plus_15pct",
        "yaw_damping_plus_15pct",
        "heldout_combination",
    }
    comb = json.loads(models["heldout_combination"].read_text(encoding="utf-8"))
    assert abs(comb["plant_actual"]["mass"] - 14.91) < 1e-12
    assert abs(comb["plant_actual"]["Xu"] - (-2.4992693)) < 1e-12

    pilot = build_episode_plan(scenarios, "pilot")
    all_pilot = pilot["episodes"] + pilot["nominal_gate"]
    assert len(all_pilot) == 12
    assert {e["maneuver"] for e in all_pilot} == set(scenarios["maneuvers"])
