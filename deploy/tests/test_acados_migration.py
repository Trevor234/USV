#!/usr/bin/env python3
"""compare_acados_migration.py 的行为测试 (不访问真实候选/服务)。

覆盖的误判风险:
  - 输入不同源 (measured/reference/anchor 任一维度漂移) 必须拒绝, 不能只看首拍;
  - 成本语义越界、目标劣化、独立重算约束违规必须拒绝;
  - 闭环 RMSE 越界/存在失败拍必须拒绝;
  - 耗时: p95/p99/max 绝对门禁、冷首拍超时、失败拍、B 抽取前后退化;
  - 旧参照 SHA 变化必须拒绝 (不允许用被改写的 oracle);
  - 旧参照预算标签不是 60 s/300 次迭代时不得当作 oracle。

运行: python3 -m unittest discover -s deploy/tests -v
"""

import copy
import json
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import compare_acados_migration as migration  # noqa: E402

N = migration.A_N
DT = migration.A_DT
PARAMS_A = {
  "dt": DT, "N": N,
  "Q": [10.0, 10.0, 50.0], "R": [1.0, 1.0], "Qf_scale": 10.0,
  "u_max": 3.3, "u_min": 0.0, "r_max": 1.25, "du_max": 1.3, "dr_max": 1.25,
  "tau_u": 0.8, "tau_r": 1.78, "solution_constraint_tol": 0.005,
  "max_solve_time_ms": 200.0, "horizon_budget_s": 4.0,
  "ipopt_max_cpu_time_s": 60.0, "ipopt_max_iter": 300,
  "defaulted_params": [],
}


def rollout(params, measured, control, reference):
  """用独立四子步 RK4 生成一条与生成模型一致的可行轨迹。"""
  x_rows = [[measured[row]] for row in range(5)]
  u_rows = [[], []]
  for k in range(N):
    command = list(control)
    u_rows[0].append(command[0])
    u_rows[1].append(command[1])
    state = [x_rows[row][k] for row in range(5)]
    nxt = migration.kinematic_step(state, command, params["tau_u"],
                                   params["tau_r"], params["dt"])
    for row in range(5):
      x_rows[row].append(nxt[row])
  return x_rows, u_rows


def replay_step(params, measured, control, reference):
  x_rows, u_rows = rollout(params, measured, control, reference)
  analytic = migration.a_objective(params, x_rows, u_rows, reference)
  return {
    "anchor_source": "replay",
    "success": True,
    "input": {
      "measured": list(measured),
      "anchor": list(control),
      "reference": [list(row) for row in reference],
    },
    "control": list(control),
    "X": x_rows,
    "U": u_rows,
    "objective": analytic,
    "acados_cost": analytic,
  }


def reference_matrix(offset=0.0):
  return [[0.2 * k + offset for k in range(N + 1)],
          [0.0 for _ in range(N + 1)],
          [0.0 for _ in range(N + 1)]]


def a_replay_document(params=None):
  params = dict(params or PARAMS_A)
  scenarios = []
  for name in migration.SCENARIOS:
    measured = [0.0, 0.0, 0.0, 0.5, 0.0]
    reference = reference_matrix()
    step = replay_step(params, measured, [0.5, 0.0], reference)
    scenarios.append({"name": name, "cold_start_us": 1.0, "first_solve_ms": 1.0,
                      "steps": [copy.deepcopy(step) for _ in range(5)]})
  return {
    "program": "benchmark_kinematic_solver", "package": "usv_mpc",
    "phase": "numerical", "backend": "acados",
    "solver_params": params, "numerical_steps": 5,
    "scenarios": scenarios,
  }


def old_a_document(params=None):
  document = a_replay_document(params)
  for scenario in document["scenarios"]:
    for step in scenario["steps"]:
      step.pop("acados_cost")
      step.pop("objective")
      step.pop("anchor_source")
  return document


def b_replay_document():
  scenarios = []
  for name in migration.SCENARIOS:
    measured = [0.0, 0.0, 0.0, 0.5, 0.0, 0.0]
    reference = [[0.2 * k for k in range(N + 1)],
                 [0.0 for _ in range(N + 1)],
                 [0.0 for _ in range(N + 1)],
                 [0.5 for _ in range(N + 1)],
                 [0.0 for _ in range(N + 1)],
                 [0.0 for _ in range(N + 1)]]
    step = {
      "anchor_source": "replay", "success": True,
      "input": {"measured": measured, "anchor": [5.0, 5.0],
                "reference": reference},
      "control": [5.0, 5.0],
      "X": [[0.2 * k for k in range(N + 1)] for _ in range(6)],
      "U": [[5.0 for _ in range(N)] for _ in range(2)],
      "bound_violation": 0.0, "rate_violation": 0.0,
    }
    scenarios.append({"name": name, "cold_start_us": 1.0,
                      "first_solve_ms": 1.0, "steps": [copy.deepcopy(step)] * 5})
  return {
    "program": "benchmark_dynamic_solver", "package": "usv_nmpc",
    "phase": "numerical", "backend": "acados",
    "solver_params": {"dt": DT, "N": N}, "numerical_steps": 5,
    "scenarios": scenarios,
  }


def timing_document(wall_ms, successes=None, warmup=None, measured=None):
  warmup = migration.A_TIMING_WARMUP if warmup is None else warmup
  measured = migration.A_TIMING_MEASURED if measured is None else measured
  total = warmup + measured
  steps = []
  for index in range(total):
    steps.append({
      "success": True if successes is None else successes[index],
      "wall_ms": wall_ms if not isinstance(wall_ms, list) else wall_ms[index],
    })
  return {
    "phase": "timing", "timing_warmup": warmup, "timing_measured": measured,
    "scenarios": [{"name": name, "steps": copy.deepcopy(steps)}
                  for name in migration.SCENARIOS],
  }


def closed_loop_document(position_error=0.05, heading_error=0.02, failures=0):
  scenarios = []
  for name in migration.SCENARIOS:
    plants = [[0.2 * k, 0.0, 0.0, 0.5, 0.0] for k in range(200)]
    references = [[0.2 * k + position_error, 0.0, heading_error]
                  for k in range(200)]
    steps = [{"success": True, "wall_ms": 1.0, "control": [0.5, 0.0]}
             for _ in range(200)]
    for index in range(failures):
      steps[index]["success"] = False
    scenarios.append({"name": name, "steps": steps,
                      "plant_states": plants,
                      "reference_first_column": references,
                      "closed_loop_failures": failures})
  return {"phase": "closed_loop", "closed_loop_steps": 200,
          "scenarios": scenarios}


class AReplayTest(unittest.TestCase):
  def test_consistent_replay_passes(self):
    report = migration.compare_a_replay(old_a_document(), a_replay_document(),
                                        PARAMS_A)
    self.assertEqual(len(report), 4)
    self.assertLess(report[0]["max_objective_delta"], 1e-9)

  def test_measured_drift_is_rejected(self):
    new = a_replay_document()
    new["scenarios"][0]["steps"][2]["input"]["measured"][1] += 1e-6
    with self.assertRaises(migration.GateError):
      migration.compare_a_replay(old_a_document(), new, PARAMS_A)

  def test_reference_drift_is_rejected(self):
    new = a_replay_document()
    new["scenarios"][3]["steps"][4]["input"]["reference"][0][1] += 1e-5
    with self.assertRaises(migration.GateError):
      migration.compare_a_replay(old_a_document(), new, PARAMS_A)

  def test_anchor_drift_is_rejected(self):
    new = a_replay_document()
    new["scenarios"][0]["steps"][1]["input"]["anchor"][0] += 1e-6
    with self.assertRaises(migration.GateError):
      migration.compare_a_replay(old_a_document(), new, PARAMS_A)

  def test_cost_semantics_violation_is_rejected(self):
    new = a_replay_document()
    new["scenarios"][1]["steps"][2]["acados_cost"] *= 1.001
    with self.assertRaises(migration.GateError) as raised:
      migration.compare_a_replay(old_a_document(), new, PARAMS_A)
    self.assertIn("成本语义", str(raised.exception))

  def test_objective_degradation_is_rejected(self):
    old = old_a_document()
    # 旧解更好: 把旧 X 的位置误差压到 0, 新解不变 -> 新目标劣化。
    for scenario in old["scenarios"]:
      for step in scenario["steps"]:
        step["X"][0] = list(step["input"]["reference"][0])
    with self.assertRaises(migration.GateError) as raised:
      migration.compare_a_replay(old, a_replay_document(), PARAMS_A)
    self.assertIn("目标劣化", str(raised.exception))

  def test_independent_dynamics_violation_is_rejected(self):
    new = a_replay_document()
    new["scenarios"][2]["steps"][1]["X"][3][5] += 0.5
    with self.assertRaises(migration.GateError) as raised:
      migration.compare_a_replay(old_a_document(), new, PARAMS_A)
    self.assertIn("独立重算约束违规", str(raised.exception))

  def test_anchor_source_must_be_replay(self):
    new = a_replay_document()
    new["scenarios"][0]["steps"][1]["anchor_source"] = "solver_return"
    with self.assertRaises(migration.GateError):
      migration.compare_a_replay(old_a_document(), new, PARAMS_A)

  def test_failed_step_is_rejected(self):
    new = a_replay_document()
    new["scenarios"][0]["steps"][0]["success"] = False
    with self.assertRaises(migration.GateError):
      migration.compare_a_replay(old_a_document(), new, PARAMS_A)

  def test_model_parameter_mismatch_is_rejected(self):
    new = a_replay_document()
    new["solver_params"]["Q"] = [10.0, 10.0, 60.0]
    with self.assertRaises(migration.GateError) as raised:
      migration.check_model_keys_equal(PARAMS_A, new["solver_params"])
    self.assertIn("Q", str(raised.exception))

  def test_solver_budget_fields_may_differ(self):
    candidate = dict(PARAMS_A)
    candidate.pop("ipopt_max_cpu_time_s")
    candidate.pop("ipopt_max_iter")
    migration.check_model_keys_equal(PARAMS_A, candidate)

  def test_missing_model_key_is_rejected(self):
    candidate = dict(PARAMS_A)
    candidate.pop("tau_r")
    with self.assertRaises(migration.GateError):
      migration.check_model_keys_equal(PARAMS_A, candidate)

  def test_unknown_extra_parameter_is_rejected(self):
    candidate = dict(PARAMS_A)
    candidate["dynamic.T_max"] = 1.0
    with self.assertRaises(migration.GateError):
      migration.check_model_keys_equal(PARAMS_A, candidate)


class BReplayTest(unittest.TestCase):
  def test_identical_replay_passes(self):
    report = migration.compare_b_replay(b_replay_document(),
                                        b_replay_document())
    self.assertEqual(len(report), 4)

  def test_control_sequence_drift_is_rejected(self):
    new = b_replay_document()
    new["scenarios"][0]["steps"][3]["U"][0][7] += 1e-3
    with self.assertRaises(migration.GateError):
      migration.compare_b_replay(b_replay_document(), new)

  def test_input_drift_is_rejected(self):
    new = b_replay_document()
    new["scenarios"][1]["steps"][2]["input"]["anchor"][1] += 1e-3
    with self.assertRaises(migration.GateError):
      migration.compare_b_replay(b_replay_document(), new)

  def test_dynamic_params_must_match_exactly(self):
    old = {"dt": DT, "hydro": {"mass": 14.2}}
    new = {"dt": DT, "hydro": {"mass": 14.3}}
    with self.assertRaises(migration.GateError):
      migration.check_dynamic_params_equal(old, new)

  def test_dynamic_params_equal_passes(self):
    payload = {"dt": DT, "hydro": {"mass": 14.2}, "defaulted_params": []}
    migration.check_dynamic_params_equal(payload, dict(payload))


class ProvenanceTest(unittest.TestCase):
  """旧 B 是迁移前单体二进制: 允许 shared 为空, 但绝不能凭空带一个共用库。"""

  def _document(self, root, shared=True):
    binary = os.path.join(root, "bench")
    ocp = os.path.join(root, "ocp.json")
    manifest = os.path.join(root, "manifest.txt")
    for path, content in ((binary, "b"), (ocp, "{}"), (manifest, "m")):
      with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    provenance = {
      "binary_path": binary, "binary_sha256": migration.sha256_file(binary),
      "ocp_json_path": ocp, "ocp_json_sha256": migration.sha256_file(ocp),
      "source_manifest_path": manifest,
      "source_manifest_sha256": migration.sha256_file(manifest),
      "model": "dynamic", "segment_id": "old_B_timing_1",
      "shared_backend_path": None, "shared_backend_sha256": None,
    }
    if shared:
      shared_path = os.path.join(root, "libusv_acados_backend.so")
      with open(shared_path, "w", encoding="utf-8") as handle:
        handle.write("s")
      provenance["shared_backend_path"] = shared_path
      provenance["shared_backend_sha256"] = migration.sha256_file(shared_path)
    return {"provenance": provenance}

  def test_old_binary_without_shared_backend_passes(self):
    with tempfile.TemporaryDirectory() as root:
      document = self._document(root, shared=False)
      migration.require_provenance(document, "旧 B", "dynamic",
                                   require_shared=False)

  def test_new_binary_requires_shared_backend(self):
    with tempfile.TemporaryDirectory() as root:
      document = self._document(root, shared=False)
      with self.assertRaises(migration.GateError):
        migration.require_provenance(document, "新 B", "dynamic")

  def test_old_binary_must_not_claim_shared_backend(self):
    with tempfile.TemporaryDirectory() as root:
      document = self._document(root, shared=True)
      with self.assertRaises(migration.GateError):
        migration.require_provenance(document, "旧 B", "dynamic",
                                     require_shared=False)

  def test_hash_mismatch_is_rejected(self):
    with tempfile.TemporaryDirectory() as root:
      document = self._document(root, shared=False)
      with open(document["provenance"]["binary_path"], "w",
                encoding="utf-8") as handle:
        handle.write("changed")
      with self.assertRaises(migration.GateError):
        migration.require_provenance(document, "旧 B", "dynamic",
                                     require_shared=False)


class ReferenceOracleTest(unittest.TestCase):
  def test_old_oracle_requires_diagnostic_budget(self):
    document = old_a_document()
    document["solver_params"]["ipopt_max_cpu_time_s"] = 0.12
    with self.assertRaises(migration.GateError) as raised:
      migration.check_old_numerical(document, "A", "fixture")
    self.assertIn("60 s", str(raised.exception))

  def test_old_oracle_requires_all_steps_successful(self):
    document = old_a_document()
    document["scenarios"][0]["steps"][2]["success"] = False
    with self.assertRaises(migration.GateError):
      migration.check_old_numerical(document, "A", "fixture")

  def test_missing_scenario_is_gate_error_not_keyerror(self):
    document = old_a_document()
    document["scenarios"].pop()
    with self.assertRaises(migration.GateError):
      migration.check_old_numerical(document, "A", "fixture")

  def test_reference_hash_mismatch_is_rejected(self):
    with tempfile.TemporaryDirectory() as workspace:
      for relative in migration.REFERENCE_SHA256:
        path = os.path.join(workspace, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
          handle.write("tampered")
      with self.assertRaises(migration.GateError) as raised:
        migration.verify_reference_hashes(workspace)
      self.assertIn("被改写", str(raised.exception))


class ClosedLoopTest(unittest.TestCase):
  def test_clean_closed_loop_passes(self):
    report = migration.closed_loop_gate(closed_loop_document())
    self.assertEqual(len(report), 4)
    self.assertLess(report[0]["position_rmse"], 0.1)

  def test_position_rmse_limit(self):
    document = closed_loop_document(position_error=0.5)
    with self.assertRaises(migration.GateError) as raised:
      migration.closed_loop_gate(document)
    self.assertIn("位置 RMSE", str(raised.exception))

  def test_heading_rmse_limit(self):
    document = closed_loop_document(heading_error=0.3)
    with self.assertRaises(migration.GateError) as raised:
      migration.closed_loop_gate(document)
    self.assertIn("周期航向 RMSE", str(raised.exception))

  def test_failure_step_is_rejected(self):
    document = closed_loop_document(failures=1)
    with self.assertRaises(migration.GateError) as raised:
      migration.closed_loop_gate(document)
    self.assertIn("失败", str(raised.exception))

  def test_step_count_must_be_200(self):
    document = closed_loop_document()
    document["scenarios"][0]["steps"].pop()
    with self.assertRaises(migration.GateError):
      migration.closed_loop_gate(document)

  def test_out_of_bounds_command_is_rejected(self):
    document = closed_loop_document()
    document["scenarios"][0]["steps"][5]["control"] = [5.0, 0.0]
    with self.assertRaises(migration.GateError):
      migration.closed_loop_gate(document)


class ATimingTest(unittest.TestCase):
  def test_clean_timing_passes(self):
    rows = migration.timing_gate(timing_document(5.0), "release", 200.0,
                                 absolute=True)
    self.assertEqual(len(rows), 4)
    self.assertEqual(rows[0]["samples"], migration.A_TIMING_MEASURED)

  def test_p95_limit(self):
    with self.assertRaises(migration.GateError) as raised:
      migration.timing_gate(timing_document(25.0), "release", 200.0,
                            absolute=True)
    self.assertIn("p95", str(raised.exception))

  def test_p99_limit(self):
    # nearest-rank p99 = 第 495/500 个样本: 需要 6 个慢样本才会落在 p99 上,
    # 同时 p95 (第 475 个) 仍为 5ms, 因此只触发 p99 门禁。
    values = ([5.0] * (migration.A_TIMING_WARMUP + migration.A_TIMING_MEASURED - 6)
              + [60.0] * 6)
    with self.assertRaises(migration.GateError) as raised:
      migration.timing_gate(timing_document(values), "release", 200.0,
                            absolute=True)
    self.assertIn("p99", str(raised.exception))

  def test_cold_first_step_over_deadline_is_rejected(self):
    values = [250.0] + [5.0] * (migration.A_TIMING_WARMUP +
                               migration.A_TIMING_MEASURED - 1)
    with self.assertRaises(migration.GateError) as raised:
      migration.timing_gate(timing_document(values), "release", 200.0)
    self.assertIn("墙钟", str(raised.exception))

  def test_warmup_failure_is_not_hidden(self):
    successes = [True] * (migration.A_TIMING_WARMUP + migration.A_TIMING_MEASURED)
    successes[3] = False
    with self.assertRaises(migration.GateError) as raised:
      migration.timing_gate(timing_document(5.0, successes=successes),
                            "release", 200.0)
    self.assertIn("失败拍", str(raised.exception))

  def test_wrong_sample_count_is_rejected(self):
    with self.assertRaises(migration.GateError):
      migration.timing_gate(timing_document(5.0, measured=400), "release", 200.0)

  def test_wrong_warmup_label_is_rejected(self):
    with self.assertRaises(migration.GateError):
      migration.timing_gate(timing_document(5.0, warmup=10), "release", 200.0)


class BTimingTest(unittest.TestCase):
  def test_no_regression_passes(self):
    rows = migration.compare_b_timing(timing_document(5.0),
                                      timing_document(5.1))
    self.assertEqual(len(rows), 4)

  def test_regression_beyond_ten_percent_is_rejected(self):
    with self.assertRaises(migration.GateError) as raised:
      migration.compare_b_timing(timing_document(5.0), timing_document(7.0))
    self.assertIn("退化", str(raised.exception))

  def test_small_absolute_regression_is_allowed(self):
    migration.compare_b_timing(timing_document(0.1), timing_document(0.25))


class NearestRankTest(unittest.TestCase):
  def test_nearest_rank(self):
    values = [float(index) for index in range(1, 101)]
    self.assertEqual(migration.nearest_rank(values, 50), 50.0)
    self.assertEqual(migration.nearest_rank(values, 95), 95.0)
    self.assertEqual(migration.nearest_rank(values, 99), 99.0)


if __name__ == "__main__":
  unittest.main()
