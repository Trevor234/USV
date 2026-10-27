"""Synthetic read-only comparison fixtures; no actual F4 pilot pass is claimed."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from compare_f4_runs import compare_runs, load_run, main, normalized_sdf_and_meshes
from research_config_sources import prepare_config_sources, verify_runtime_sources


HERE = Path(__file__).resolve().parent


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


class ActualConfigurationComparison(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.baseline, self.plant, self.nominal = [self.make_run(kind) for kind in ("baseline", "plant", "nominal")]

    def make_run(self, kind):
        run = self.root / kind
        run.mkdir()
        nominal = json.loads((HERE / "p0_nominal_f3.yaml").read_text(encoding="utf-8"))
        plant = copy.deepcopy(nominal)
        plant["/**"]["ros__parameters"]["vehicle"].update({"Yr_dot": 0.0, "Nv_dot": -0.363545})
        if kind == "plant":
            plant["/**"]["ros__parameters"]["vehicle"]["mass"] = 17.04
        if kind == "nominal":
            nominal["/**"]["ros__parameters"]["vehicle"]["mass"] = 17.04
        for label, data in (("nominal", nominal), ("plant", plant),
                            ("simulation", {"added_mass_cross_policy": "symmetric_mean"})):
            write_json(run / (label + ".yaml"), data)
        source = prepare_config_sources(run / "nominal.yaml", run / "plant.yaml", run / "simulation.yaml", run / "config")
        model = run / "model"
        model.mkdir()
        mass = source["expected_plant_effective_vehicle"]["mass"]
        beam = 0.3121789448404427 * mass / 14.2
        (model / "hull.dae").write_text("synthetic hull beam=" + str(beam), encoding="utf-8")
        sdf = '<sdf><model name="wamv"><link name="hull"><visual><geometry><mesh><uri>'
        sdf += (model / "hull.dae").as_uri() + '</uri></mesh></geometry></visual></link>'
        sdf += ''.join('<plugin name="gz::sim::systems::Thruster"><max_thrust_cmd>25</max_thrust_cmd>'
                       '<min_thrust_cmd>-25</min_thrust_cmd></plugin>' for _ in range(2))
        sdf += '<custom>retained</custom></model></sdf>'
        (model / "model.sdf").write_text(sdf, encoding="utf-8")
        write_json(model / "model_report.json", {
            "effective_vehicle": source["expected_plant_effective_vehicle"],
            "mass_kg": mass, "waterline_beam_m": beam, "displacement_m3": mass / 1000,
            "yaw_inertia_at_com": 2.13 - mass * 0.12 ** 2, "com_m": [0.12, 0, 0],
        })
        write_json(model / "effective_vehicle.yaml", {"/**": {"ros__parameters": {
            "vehicle": source["expected_plant_effective_vehicle"], "thruster": source["plant"]["thruster"]}}})
        params = {"vehicle": source["nominal"]["vehicle"], "dynamic": {"T_max": 25.0, "T_min": -25.0, "Q": [20, 20, 50, 8, 1, 8]},
                  "research_run_id": kind, "research_baseline_id": "F4_synthetic_fixture",
                  "research_config_hash": hashlib.sha256(kind.encode()).hexdigest(),
                  "research_output_dir": str(run / "source"),
                  "research_nominal_config_hash": source["nominal_effective_sha256"],
                  "enable_research_logging": True, "enable_reference_prediction_logging": True}
        raw = json.dumps({"/mpc_controller_node": {"ros__parameters": params}})
        write_json(run / "topic_graph.json", {"run_id": kind, "baseline_id": "F4_synthetic_fixture",
            "effective_parameter_dump": {"returncode": 0, "stdout": raw, "stdout_sha256": hashlib.sha256(raw.encode()).hexdigest()}})
        write_json(run / "config_runtime.json", verify_runtime_sources(run / "config", model, params))
        return run

    def loaded(self):
        return [load_run(p) for p in (self.baseline, self.plant, self.nominal)]

    def test_intended_synthetic_invariants_pass_without_claiming_physics(self):
        report = compare_runs(*self.loaded())
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(report["scope"], "configuration isolation only")
        self.assertTrue(report["plant_probe_interpretation"]["not_a_pure_payload_step_performance_experiment"])
        self.assertFalse(report["plant_equivalence_proven"])
        self.assertFalse(report["gp_labels_ready"])

    def test_unrelated_actual_controller_change_is_not_hidden_by_exclusions(self):
        b, p, n = self.loaded()
        p["flat_parameters"]["dynamic.Q"][0] = 21
        report = compare_runs(b, p, n)
        self.assertFalse(report["passed"])
        self.assertIn("plant_mass_all_other_actual_controller_parameters_unchanged", report["failures"])

    def test_sdf_normalization_retains_every_non_uri_field_and_mesh_hash(self):
        b, _, n = self.loaded()
        self.assertEqual(b["model_identity"]["normalized_sdf_sha256"], n["model_identity"]["normalized_sdf_sha256"])
        sdf = self.nominal / "model/model.sdf"
        sdf.write_text(sdf.read_text().replace('retained', 'changed'), encoding="utf-8")
        changed = normalized_sdf_and_meshes(self.nominal / "model")
        self.assertNotEqual(b["model_identity"]["normalized_sdf_sha256"], changed["normalized_sdf_sha256"])
        self.assertEqual(b["model_identity"]["mesh_sha256_by_relative_path"], changed["mesh_sha256_by_relative_path"])

    def test_external_mesh_uri_and_bad_dump_hash_rejected(self):
        sdf = self.nominal / "model/model.sdf"
        sdf.write_text(sdf.read_text().replace((self.nominal / "model/hull.dae").as_uri(), (self.baseline / "model/hull.dae").as_uri()), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "contained"):
            normalized_sdf_and_meshes(self.nominal / "model")
        graph_path = self.baseline / "topic_graph.json"
        graph = json.loads(graph_path.read_text())
        graph["effective_parameter_dump"]["stdout_sha256"] = '0' * 64
        write_json(graph_path, graph)
        with self.assertRaisesRegex(ValueError, "stdout hash"):
            load_run(self.baseline)

    def test_same_run_reuse_and_missing_actual_files_do_not_pass(self):
        b, p, n = self.loaded()
        self.assertFalse(compare_runs(b, p, b)["passed"])
        (self.nominal / "config_runtime.json").unlink()
        output = self.root / "comparison.json"
        code = main(['--baseline-run', str(self.baseline), '--plant-run', str(self.plant),
                     '--nominal-run', str(self.nominal), '--output', str(output)])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output.read_text())["passed"])
        with self.assertRaises(SystemExit):
            main(['--baseline-run', str(self.baseline), '--plant-run', str(self.plant),
                  '--nominal-run', str(self.nominal), '--output', str(output)])


if __name__ == '__main__':
    unittest.main()
