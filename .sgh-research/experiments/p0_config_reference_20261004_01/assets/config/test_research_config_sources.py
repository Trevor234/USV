"""Focused stdlib tests; runtime launch/renderer checks remain an Ubuntu gate."""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from research_config_sources import (
    VEHICLE_KEYS, load_asset, prepare_config_sources, verify_runtime_sources,
)
from apply_config_launch_patch import F3_VRX_SHA256, patched_bytes


HERE = Path(__file__).resolve().parent
# Optional verified source root containing usv_bringup, e.g. the F3
# source_snapshot/usv_mpc_ws/src. Never read patched production for this fixture.
SOURCE_ROOT = Path(os.environ.get(
    "P0_TEST_SOURCE_ROOT",
    str(HERE.parents[1] / "p0_contract_impl_2026-10-03/source/usv_mpc_ws/src")))
MIRROR = SOURCE_ROOT / "usv_bringup/launch/vrx.launch.py"


def write(path, document):
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class IndependentSources(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.nominal = json.loads((HERE / "p0_nominal_f3.yaml").read_text(encoding="utf-8"))
        self.plant = copy.deepcopy(self.nominal)
        self.plant["/**"]["ros__parameters"]["vehicle"].update(
            {"Yr_dot": 0.0, "Nv_dot": -0.363545, "length": 1.2,
             "beam": 0.6, "draft": 0.1, "height": 0.3})
        self.nominal_path = write(self.root / "nominal.yaml", self.nominal)
        self.plant_path = write(self.root / "plant.yaml", self.plant)
        self.settings = write(self.root / "settings.yaml", {"added_mass_cross_policy": "symmetric_mean"})

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, suffix):
        return prepare_config_sources(self.nominal_path, self.plant_path, self.settings,
                                      self.root / suffix)

    def test_default_effective_parameters_equal_f3_without_nominal_projection(self):
        report = self.prepare("baseline")
        self.assertEqual(set(report["nominal"]["vehicle"]), set(VEHICLE_KEYS))
        self.assertEqual(report["nominal"]["vehicle"], report["expected_plant_effective_vehicle"])
        self.assertEqual(report["nominal_projection"], "none; exact nineteen explicit vehicle values")
        self.assertFalse(report["runtime_effective_verified"])
        self.assertFalse(report["plant_equivalence_proven"])
        self.assertFalse(report["gp_labels_ready"])

    def test_plant_only_mass_changes_neither_nominal_file_nor_solver_constraints(self):
        baseline = self.prepare("baseline")
        self.plant["/**"]["ros__parameters"]["vehicle"]["mass"] = 15.62
        write(self.plant_path, self.plant)
        changed = self.prepare("plant_mass")
        self.assertEqual(baseline["nominal_effective_sha256"], changed["nominal_effective_sha256"])
        self.assertEqual(baseline["solver_input_constraints"], changed["solver_input_constraints"])
        self.assertNotEqual(baseline["plant"]["source_sha256"], changed["plant"]["source_sha256"])

    def test_nominal_only_mass_changes_neither_plant_source_nor_expected_projection(self):
        baseline = self.prepare("baseline")
        self.nominal["/**"]["ros__parameters"]["vehicle"]["mass"] = 15.62
        write(self.nominal_path, self.nominal)
        changed = self.prepare("nominal_mass")
        self.assertNotEqual(baseline["nominal_effective_sha256"], changed["nominal_effective_sha256"])
        self.assertEqual(baseline["plant"], changed["plant"])
        self.assertEqual(baseline["expected_plant_effective_vehicle"], changed["expected_plant_effective_vehicle"])

    def test_plant_only_thruster_does_not_change_solver_constraints(self):
        baseline = self.prepare("baseline")
        self.plant["/**"]["ros__parameters"]["thruster"]["T_max_forward"] = 20.0
        write(self.plant_path, self.plant)
        changed = self.prepare("plant_thruster")
        self.assertEqual(baseline["solver_input_constraints"], changed["solver_input_constraints"])
        self.assertEqual(changed["plant_actuator_command_limits"]["max_N"], 20.0)

    def test_nominal_only_thruster_does_not_change_plant_limits(self):
        baseline = self.prepare("baseline")
        self.nominal["/**"]["ros__parameters"]["thruster"]["T_max_reverse"] = 20.0
        write(self.nominal_path, self.nominal)
        changed = self.prepare("nominal_thruster")
        self.assertEqual(baseline["plant_actuator_command_limits"], changed["plant_actuator_command_limits"])
        self.assertEqual(changed["solver_input_constraints"]["T_min"], -20.0)

    def test_nominal_asymmetric_cross_terms_are_not_projected(self):
        self.nominal["/**"]["ros__parameters"]["vehicle"].update({"Yr_dot": 0.0, "Nv_dot": -0.363545})
        write(self.nominal_path, self.nominal)
        report = self.prepare("asymmetric")
        self.assertEqual(report["nominal"]["vehicle"]["Yr_dot"], 0.0)
        self.assertEqual(report["nominal"]["vehicle"]["Nv_dot"], -0.363545)
        self.assertEqual(report["expected_plant_effective_vehicle"]["Yr_dot"], -0.1817725)

    def test_existing_output_and_same_source_are_rejected(self):
        self.prepare("once")
        with self.assertRaises(FileExistsError):
            self.prepare("once")
        with self.assertRaisesRegex(ValueError, "distinct"):
            prepare_config_sources(self.nominal_path, self.nominal_path, self.settings, self.root / "same")

    def test_missing_nonfinite_and_nonvehicle_override_rejected(self):
        for change in ("missing", "nonfinite", "override"):
            with self.subTest(change=change):
                document = copy.deepcopy(self.nominal)
                params = document["/**"]["ros__parameters"]
                if change == "missing":
                    del params["vehicle"]["Xu"]
                elif change == "nonfinite":
                    params["vehicle"]["mass"] = float("nan")
                else:
                    params["dynamic"] = {"Q": "0 0 0 0 0 0"}
                path = write(self.root / (change + ".yaml"), document)
                with self.assertRaises(ValueError):
                    load_asset(path, "nominal")

    def test_strict_plant_cross_policy_rejects_asymmetry(self):
        write(self.settings, {"added_mass_cross_policy": "strict"})
        with self.assertRaisesRegex(ValueError, "Strict"):
            self.prepare("strict")

    def make_generated_fixture(self, report):
        # A synthetic fixture validates the evidence checker, not the real renderer.
        model = self.root / "model"
        model.mkdir()
        write(model / "model_report.json", {"effective_vehicle": report["expected_plant_effective_vehicle"]})
        write(model / "effective_vehicle.yaml", {"/**": {"ros__parameters": {
            "vehicle": report["expected_plant_effective_vehicle"], "thruster": report["plant"]["thruster"]}}})
        plugins = "".join('<plugin name="gz::sim::systems::Thruster"><max_thrust_cmd>25</max_thrust_cmd>'
                          '<min_thrust_cmd>-25</min_thrust_cmd></plugin>' for _ in range(2))
        (model / "model.sdf").write_text('<sdf><model name="wamv">' + plugins + '</model></sdf>', encoding="utf-8")
        runtime = {"vehicle": report["nominal"]["vehicle"], "dynamic": {"T_max": 25.0, "T_min": -25.0}}
        return model, runtime

    def test_runtime_checker_requires_actual_nominal_and_generated_plant(self):
        report = self.prepare("baseline")
        model, runtime = self.make_generated_fixture(report)
        result = verify_runtime_sources(self.root / "baseline", model, runtime)
        self.assertTrue(result["runtime_effective_verified"])
        self.assertTrue(result["plant_generated_verified"])
        self.assertFalse(result["exact_execution_timing_available"])
        runtime["vehicle"] = dict(runtime["vehicle"], mass=15.62)
        with self.assertRaisesRegex(ValueError, "controller vehicle"):
            verify_runtime_sources(self.root / "baseline", model, runtime)

    def test_runtime_checker_rejects_modified_source_and_actuator_bounds(self):
        report = self.prepare("baseline")
        model, runtime = self.make_generated_fixture(report)
        sdf = model / "model.sdf"
        sdf.write_text(sdf.read_text().replace('25</max_', '20</max_'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "actuator bound"):
            verify_runtime_sources(self.root / "baseline", model, runtime)
        (self.root / "baseline/plant_input.yaml").write_text('{}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source snapshot"):
            verify_runtime_sources(self.root / "baseline", model, runtime)


class GuardedLaunchPatch(unittest.TestCase):
    def test_verified_f3_mirror_and_legacy_fallback(self):
        import hashlib
        raw = MIRROR.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), F3_VRX_SHA256)
        result = patched_bytes(raw).decode("utf-8")
        self.assertIn('"controller_vehicle", default=LaunchConfiguration("effective_vehicle")', result)
        self.assertIn('"dynamic.T_max": controller_parameter("tmax")', result)
        self.assertIn('"t_max": plant_parameter("tmax")', result)  # PPO retains original source.
        self.assertIn('"mass": plant_parameter("mass")', result)  # A retains original source.

    def test_changed_bytes_duplicate_anchor_and_reapply_rejected(self):
        import hashlib
        raw = MIRROR.read_bytes()
        with self.assertRaisesRegex(ValueError, "SHA256"):
            patched_bytes(raw + b"\n")
        newline = b'\r\n' if b'\r\n' in raw else b'\n'
        duplicate = raw + newline + b'    usv_params_sim = LaunchConfiguration("effective_vehicle")' + newline
        with self.assertRaisesRegex(ValueError, "exactly once"):
            patched_bytes(duplicate, hashlib.sha256(duplicate).hexdigest())
        applied = patched_bytes(raw)
        with self.assertRaisesRegex(ValueError, "Already patched"):
            patched_bytes(applied, hashlib.sha256(applied).hexdigest())


if __name__ == "__main__":
    unittest.main()
