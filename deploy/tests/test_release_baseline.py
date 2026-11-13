#!/usr/bin/env python3
"""release 基线工具的行为测试 (不访问真实服务/串口/构建目录)。

覆盖两类误判风险:
  - 在线身份: 错误 overlay、已删除 ELF、哈希不符、参数失配、多控制器、
    串口被非 MAVROS 持有、包前缀落在预期 install 之外;
  - 数值/耗时对照: 输入不一致、非有限结果、容差内外、失败与超预算拍数增加、
    p95 门槛、生成器配置 (acados profile) 缺失或与契约不符。

运行: python3 -m unittest discover -s deploy/tests -v
"""

import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capture_release_identity as capture  # noqa: E402
import compare_release_baseline as compare  # noqa: E402

INSTALL = "/home/trevor/usv_releases/pi5-test/install_release"
EXECUTABLE = os.path.join(INSTALL, "usv_nmpc", "lib", "usv_nmpc", "mpc_node")
MAVROS = "/opt/ros/jazzy/lib/mavros/mavros_node"
EXE_SHA = "a" * 64


SHARED_BACKEND = os.path.join(INSTALL, "usv_acados", "lib",
                               "libusv_acados_backend.so.0.1.0")


def shared_libraries_for(scheme):
  """控制器实际加载的库: 共用后端 + acados/hpipm/blasfeo (方案 A/B 相同)。"""
  del scheme
  return [
    {"path": SHARED_BACKEND, "sha256": "9" * 64},
    {"path": "/home/trevor/acados/lib/libacados.so", "sha256": "8" * 64},
    {"path": "/home/trevor/acados/lib/libhpipm.so", "sha256": "7" * 64},
    {"path": "/home/trevor/acados/lib/libblasfeo.so", "sha256": "6" * 64},
  ]


def runtime_snapshot(scheme="B"):
  """构造一份“完全正确”的在线快照, 测试按需破坏其中一项。"""
  parameters = {
    "control_mode": "dynamic",
    "mpc_dt": 0.2,
    "horizon": 20,
    "max_solve_time_ms": 200.0,
    "dynamic.dt": 0.2,
    "dynamic.Q": [20.0, 20.0, 50.0, 8.0, 1.0, 8.0],
    "dynamic.R": [0.05, 0.05],
    "dynamic.Rd": [0.2, 0.2],
    "dynamic.Qf_scale": 8.0,
    "dynamic.T_max": 25.0,
    "dynamic.T_min": -25.0,
    "dynamic.dT_max": 80.0,
    "vehicle.mass": 14.2,
    "vehicle.Nrr": -0.71,
  }
  for key in capture.CRITICAL_DYNAMIC_KEYS:
    parameters.setdefault(key, 1.0)
  if scheme == "A":
    parameters["control_mode"] = "kinematic"
    parameters["kinematic.backend"] = "acados"
    for key in capture.CRITICAL_KINEMATIC_KEYS:
      parameters.setdefault(key, 1.0)
  package = "usv_mpc" if scheme == "A" else "usv_nmpc"
  executable = os.path.join(INSTALL, package, "lib", package, "mpc_node")
  return {
    "identity_kind": "runtime",
    "scheme": scheme,
    "expected_install": INSTALL,
    "expected_executable": {"path": executable, "sha256": EXE_SHA},
    "services": {
      "usv-system": {"ActiveState": "active", "UnitFileState": "enabled",
                     "NRestarts": "0"},
      "usv-record": {"ActiveState": "inactive"},
      "usv-rtk": {"ActiveState": "inactive"},
    },
    "processes": [
      {"pid": 100, "exe_target": executable, "exe_link": executable,
       "exe_deleted": False, "exe_sha256": EXE_SHA, "disk_sha256": EXE_SHA,
       "custom": False, "under_expected_install": True, "under_ros": False,
       "external_libraries": shared_libraries_for(scheme)},
      {"pid": 101, "exe_target": MAVROS, "exe_link": MAVROS,
       "exe_deleted": False, "exe_sha256": "b" * 64, "disk_sha256": "b" * 64,
       "custom": False, "under_expected_install": False, "under_ros": True},
    ],
    "serial_holders": {"/dev/ttyAMA10": [101]},
    "parameter_dump": {"returncode": 0, "parameters": parameters,
                       "sha256": "c" * 64},
    "expected_parameters": dict(parameters),
    "package_prefixes": {
      package: {"prefix": os.path.join(INSTALL, package), "resolved": True,
                "inside_expected": True}
      for package in capture.PACKAGES
    },
    "backend_log": {"backend": "acados"},
  }


def write_profile_fixture(root, model):
  """按 compare.EXPECTED_OCP_PROFILE 写一份 OCP JSON + source manifest, 返回路径。"""
  expected = compare.EXPECTED_OCP_PROFILE[model]
  payload = {
    "dims": dict(expected["dims"]),
    "solver_options": dict(expected["solver_options"],
                           cost_scaling=expected["cost_scaling"]),
  }
  ocp_path = os.path.join(root, f"{model}_ocp.json")
  with open(ocp_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle)
  manifest_path = os.path.join(root, "source_manifest_frozen.txt")
  with open(manifest_path, "w", encoding="utf-8") as handle:
    handle.write("src/manifest\n")
  return ocp_path, manifest_path


def fake_provenance(root, ocp_path, manifest_path, model, binary_name="bench"):
  binary = os.path.join(root, binary_name)
  with open(binary, "w", encoding="utf-8") as handle:
    handle.write("elf")
  shared = os.path.join(root, "libusv_acados_backend.so")
  with open(shared, "w", encoding="utf-8") as handle:
    handle.write("so")
  def digest(path):
    with open(path, "rb") as handle:
      return capture.sha256_bytes(handle.read())

  return {
    "binary_path": binary,
    "binary_sha256": digest(binary),
    "shared_backend_path": shared,
    "shared_backend_sha256": digest(shared),
    "model": model,
    "ocp_json_path": ocp_path,
    "ocp_json_sha256": digest(ocp_path),
    "source_manifest_path": manifest_path,
    "source_manifest_sha256": digest(manifest_path),
    "segment_id": "release_kinematic_numerical",
    "returncode": 0,
  }


def numerical_document(control=(1.0, 0.5), x_value=0.1, u_value=2.0,
                       variant="dynamic_acados"):
  is_kinematic = variant == "kinematic"
  return {
    "program": ("benchmark_kinematic_solver" if is_kinematic
                else "benchmark_dynamic_solver"),
    "package": "usv_mpc" if is_kinematic else "usv_nmpc",
    "phase": "numerical",
    "backend": "acados",
    "solver_params": {"dt": 0.2, "N": 2, "max_solve_time_ms": 200.0},
    "scenarios": [{
      "name": "straight",
      "cold_start_us": 1.0,
      "first_solve_ms": 1.0,
      "steps": [{
        "input": {"measured": [0.0, 0.2, 0.0, 0.8, 0.0, 0.0],
                  "reference": [[0.0, 0.16], [0.0, 0.0], [0.0, 0.0],
                                [0.8, 0.8], [0.0, 0.0], [0.0, 0.0]],
                  "anchor": [5.0, 5.0]},
        "success": True,
        "backend": "acados",
        "wall_ms": 1.0,
        "reported_ms": 0.9,
        "control": list(control),
        "X": [[x_value, x_value], [0.0, 0.0], [0.0, 0.0], [0.8, 0.8],
              [0.0, 0.0], [0.0, 0.0]],
        "U": [[u_value, u_value], [u_value, u_value]],
        "bound_violation": 0.0,
        "rate_violation": 0.0,
      }],
    }],
  }


def multi_scenario_timing(scenarios):
  """scenarios: {name: [wall_ms...]} -> 含多场景的计时文档。"""
  document = timing_document([1.0])
  document["scenarios"] = []
  for name, samples in scenarios.items():
    steps = []
    for index, value in enumerate(samples):
      step = {"success": True, "backend": "acados", "wall_ms": value,
              "reported_ms": value * 0.9, "control": [1.0, 1.0]}
      if index == 0:
        step["input"] = {"measured": [0.0, 0.2, 0.0, 0.8, 0.0, 0.0],
                         "reference": [[0.0, 0.16], [0.0, 0.0], [0.0, 0.0],
                                       [0.8, 0.8], [0.0, 0.0], [0.0, 0.0]],
                         "anchor": [5.0, 5.0]}
      steps.append(step)
    document["scenarios"].append({"name": name, "cold_start_us": 1.0,
                                  "first_solve_ms": 1.0, "steps": steps})
  return document


def environment_document(segments=None, throttled_sticky=0):
  return {
    "throttled_sticky": throttled_sticky,
    "segments": segments if segments is not None else [
      {"label": "x_start", "start_temperature_c": 55.0},
      {"label": "x_end", "start_temperature_c": 58.0},
    ],
  }


def timing_document(wall_ms, successes=None, provenance=None):
  steps = []
  for index, value in enumerate(wall_ms):
    step = {"success": True if successes is None else successes[index],
            "backend": "acados", "wall_ms": value, "reported_ms": value * 0.9,
            "control": [1.0, 1.0]}
    if index == 0:
      step["input"] = {"measured": [0.0, 0.2, 0.0, 0.8, 0.0, 0.0],
                       "reference": [[0.0, 0.16], [0.0, 0.0], [0.0, 0.0],
                                     [0.8, 0.8], [0.0, 0.0], [0.0, 0.0]],
                       "anchor": [5.0, 5.0]}
    steps.append(step)
  document = {
    "program": "benchmark_dynamic_solver",
    "package": "usv_nmpc",
    "phase": "timing",
    "backend": "acados",
    "solver_params": {"dt": 0.2, "N": 2, "max_solve_time_ms": 200.0},
    "scenarios": [{"name": "straight", "cold_start_us": 1.0,
                   "first_solve_ms": 1.0, "steps": steps}],
  }
  if provenance is not None:
    document["provenance"] = provenance
  return document


class RuntimeIdentityTest(unittest.TestCase):
  def test_clean_snapshot_passes(self):
    self.assertEqual(capture.evaluate_runtime(runtime_snapshot()), [])

  def test_scheme_a_requires_kinematic_executable(self):
    self.assertEqual(capture.evaluate_runtime(runtime_snapshot("A")), [])

  def test_wrong_overlay_is_rejected(self):
    snapshot = runtime_snapshot()
    snapshot["processes"].append({
      "pid": 300, "exe_target": "/home/trevor/usv_mpc_ws/install/usv_mpc_cpp/"
                                 "lib/usv_mpc_cpp/mode_manager_node",
      "exe_link": "/home/trevor/usv_mpc_ws/install/usv_mpc_cpp/lib/"
                  "usv_mpc_cpp/mode_manager_node",
      "exe_deleted": False, "exe_sha256": "d" * 64, "disk_sha256": "d" * 64,
      "custom": True, "under_expected_install": False, "under_ros": False})
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("自定义进程" in item for item in failures), failures)

  def test_deleted_executable_is_rejected(self):
    snapshot = runtime_snapshot()
    controller = snapshot["processes"][0]
    controller["exe_link"] = controller["exe_target"] + " (deleted)"
    controller["exe_deleted"] = True
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("deleted" in item for item in failures), failures)

  def test_hash_mismatch_is_rejected(self):
    snapshot = runtime_snapshot()
    snapshot["processes"][0]["exe_sha256"] = "e" * 64
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("哈希不一致" in item for item in failures), failures)

  def test_installed_node_with_stale_disk_hash_is_rejected(self):
    snapshot = runtime_snapshot()
    planner = {"pid": 200,
               "exe_target": os.path.join(INSTALL, "usv_planning", "lib",
                                          "usv_planning", "path_planner_node"),
               "exe_link": "", "exe_deleted": False, "exe_sha256": "1" * 64,
               "disk_sha256": "2" * 64, "custom": False,
               "under_expected_install": True, "under_ros": False}
    planner["exe_link"] = planner["exe_target"]
    snapshot["processes"].append(planner)
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("哈希不一致" in item for item in failures), failures)

  def test_multiple_controllers_are_rejected(self):
    snapshot = runtime_snapshot()
    duplicate = copy.deepcopy(snapshot["processes"][0])
    duplicate["pid"] = 999
    snapshot["processes"].append(duplicate)
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("控制器进程数量" in item for item in failures), failures)

  def test_parameter_mismatch_is_rejected(self):
    snapshot = runtime_snapshot()
    snapshot["parameter_dump"]["parameters"]["dynamic.T_max"] = 30.0
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("dynamic.T_max" in item for item in failures), failures)

  def test_control_mode_mismatch_is_rejected(self):
    snapshot = runtime_snapshot()
    snapshot["parameter_dump"]["parameters"]["control_mode"] = "idle"
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("control_mode" in item for item in failures), failures)

  def test_backend_mismatch_is_rejected(self):
    snapshot = runtime_snapshot()
    snapshot["backend_log"]["backend"] = "casadi"
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("后端" in item for item in failures), failures)

  def test_missing_shared_backend_is_rejected(self):
    snapshot = runtime_snapshot()
    snapshot["processes"][0]["external_libraries"] = [
      item for item in snapshot["processes"][0]["external_libraries"]
      if "libusv_acados_backend" not in item["path"]]
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("共用后端库" in item for item in failures), failures)

  def test_shared_backend_outside_install_is_rejected(self):
    snapshot = runtime_snapshot()
    snapshot["processes"][0]["external_libraries"][0] = {
      "path": "/home/trevor/usv_mpc_ws/install/usv_acados/lib/"
              "libusv_acados_backend.so", "sha256": "9" * 64}
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("共用后端库不在预期 install" in item for item in failures),
                    failures)

  def test_leftover_casadi_mapping_is_rejected(self):
    snapshot = runtime_snapshot()
    snapshot["processes"][0]["external_libraries"].append(
      {"path": "/home/trevor/.local/lib/python3.12/site-packages/casadi/libcasadi.so",
       "sha256": "5" * 64})
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("libcasadi" in item for item in failures), failures)

  def test_missing_acados_dependency_is_rejected(self):
    snapshot = runtime_snapshot()
    snapshot["processes"][0]["external_libraries"] = [
      item for item in snapshot["processes"][0]["external_libraries"]
      if "libhpipm" not in item["path"]]
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("libhpipm" in item for item in failures), failures)

  def test_second_mavros_is_rejected(self):
    snapshot = runtime_snapshot()
    snapshot["processes"].append({
      "pid": 400, "exe_target": MAVROS, "exe_link": MAVROS,
      "exe_deleted": False, "exe_sha256": "f" * 64, "disk_sha256": "f" * 64,
      "custom": False, "under_expected_install": False, "under_ros": True})
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("MAVROS 进程数量" in item for item in failures), failures)

  def test_serial_held_by_non_mavros_is_rejected(self):
    snapshot = runtime_snapshot()
    snapshot["serial_holders"]["/dev/ttyAMA10"] = [100]
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("串口" in item for item in failures), failures)

  def test_package_prefix_outside_install_is_rejected(self):
    snapshot = runtime_snapshot()
    snapshot["package_prefixes"]["usv_bringup"] = {
      "prefix": "/home/trevor/usv_mpc_ws/install/usv_bringup",
      "resolved": True, "inside_expected": False}
    failures = capture.evaluate_runtime(snapshot)
    self.assertTrue(any("usv_bringup" in item for item in failures), failures)

  def test_restart_increase_and_service_activation_are_rejected(self):
    baseline = runtime_snapshot()
    snapshot = runtime_snapshot()
    snapshot["services"]["usv-system"]["NRestarts"] = "2"
    snapshot["services"]["usv-record"]["ActiveState"] = "active"
    failures = capture.evaluate_runtime(snapshot, baseline)
    self.assertTrue(any("重启次数" in item for item in failures), failures)
    self.assertTrue(any("usv-record" in item for item in failures), failures)

  def test_unchanged_baseline_passes(self):
    baseline = runtime_snapshot()
    self.assertEqual(capture.evaluate_runtime(runtime_snapshot(), baseline), [])


class NumericalComparisonTest(unittest.TestCase):
  def test_identical_documents_pass(self):
    noopt = numerical_document()
    release = numerical_document()
    report = compare.compare_numerical(noopt, release)
    self.assertEqual(report[0]["steps"], 1)
    self.assertLess(report[0]["max_control_delta"], 1e-12)

  def test_input_mismatch_fails(self):
    noopt = numerical_document()
    release = numerical_document()
    release["scenarios"][0]["steps"][0]["input"]["reference"][0][1] = 0.5
    with self.assertRaises(compare.GateError):
      compare.compare_numerical(noopt, release)

  def test_anchor_tolerates_solver_derived_drift(self):
    noopt = numerical_document()
    release = numerical_document()
    noopt["scenarios"][0]["steps"][0]["input"]["anchor"] = [5.0, 5.0]
    release["scenarios"][0]["steps"][0]["input"]["anchor"] = [5.0 + 1e-12, 5.0]
    compare.compare_numerical(noopt, release)

  def test_anchor_outside_derived_tolerance_fails(self):
    noopt = numerical_document()
    release = numerical_document()
    noopt["scenarios"][0]["steps"][0]["input"]["anchor"] = [5.0, 5.0]
    release["scenarios"][0]["steps"][0]["input"]["anchor"] = [5.0 + 1e-6, 5.0]
    with self.assertRaises(compare.GateError):
      compare.compare_numerical(noopt, release)

  def test_measured_state_drift_beyond_last_bit_fails(self):
    noopt = numerical_document()
    release = numerical_document()
    noopt["scenarios"][0]["steps"][0]["input"]["measured"][0] = 0.0
    release["scenarios"][0]["steps"][0]["input"]["measured"][0] = 1e-9
    with self.assertRaises(compare.GateError):
      compare.compare_numerical(noopt, release)

  def test_parameter_mismatch_fails(self):
    noopt = numerical_document()
    release = numerical_document()
    release["solver_params"]["dynamic.T_max"] = 30.0
    with self.assertRaises(compare.GateError):
      compare.compare_numerical(noopt, release)

  def test_tolerance_boundary(self):
    noopt = numerical_document(control=(1.0, 0.5))
    inside = numerical_document(control=(1.0 + 1e-4 + 1e-6 * 1.0, 0.5))
    outside = numerical_document(control=(1.0 + 5e-4, 0.5))
    compare.compare_numerical(noopt, inside)
    with self.assertRaises(compare.GateError):
      compare.compare_numerical(noopt, outside)

  def test_non_finite_result_fails(self):
    noopt = numerical_document()
    release = numerical_document()
    release["scenarios"][0]["steps"][0]["control"] = [float("nan"), 0.5]
    with self.assertRaises(compare.GateError):
      compare.compare_numerical(noopt, release)

  def test_failed_solve_fails(self):
    noopt = numerical_document()
    release = numerical_document()
    release["scenarios"][0]["steps"][0]["success"] = False
    with self.assertRaises(compare.GateError):
      compare.compare_numerical(noopt, release)

  def test_heading_is_compared_modulo_two_pi(self):
    noopt = numerical_document()
    release = numerical_document()
    noopt["scenarios"][0]["steps"][0]["X"][2] = [3.14159265358979, 3.14159265358979]
    release["scenarios"][0]["steps"][0]["X"][2] = [-3.14159265358979, -3.14159265358979]
    compare.compare_numerical(noopt, release)

  def test_missing_provenance_is_rejected(self):
    # 没有 runner provenance 就无法证明测的是这份候选的生成码。
    document = numerical_document()
    with self.assertRaises(compare.GateError):
      compare.check_acados_profile(document, "kinematic")

  def test_profile_rejects_wrong_solver_type(self):
    with tempfile.TemporaryDirectory() as workspace:
      ocp_path, manifest_path = write_profile_fixture(workspace, "kinematic")
      with open(ocp_path, encoding="utf-8") as handle:
        payload = json.load(handle)
      payload["solver_options"]["nlp_solver_type"] = "SQP_RTI"
      with open(ocp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
      provenance = fake_provenance(workspace, ocp_path, manifest_path, "kinematic")
      document = numerical_document()
      document["provenance"] = provenance
      with self.assertRaises(compare.GateError) as raised:
        compare.check_acados_profile(document, "kinematic")
      self.assertIn("nlp_solver_type", str(raised.exception))

  def test_profile_rejects_dt_scaled_cost_for_kinematic(self):
    # A 的阶段代价不乘 dt: cost_scaling 必须是 ones, 不能沿用 B 的默认缩放。
    with tempfile.TemporaryDirectory() as workspace:
      ocp_path, manifest_path = write_profile_fixture(workspace, "kinematic")
      with open(ocp_path, encoding="utf-8") as handle:
        payload = json.load(handle)
      payload["solver_options"]["cost_scaling"] = [0.2] * 20 + [1.0]
      with open(ocp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
      provenance = fake_provenance(workspace, ocp_path, manifest_path, "kinematic")
      document = numerical_document()
      document["provenance"] = provenance
      with self.assertRaises(compare.GateError) as raised:
        compare.check_acados_profile(document, "kinematic")
      self.assertIn("cost_scaling", str(raised.exception))

  def test_profile_rejects_ocp_hash_mismatch(self):
    with tempfile.TemporaryDirectory() as workspace:
      ocp_path, manifest_path = write_profile_fixture(workspace, "kinematic")
      provenance = fake_provenance(workspace, ocp_path, manifest_path, "kinematic")
      provenance["ocp_json_sha256"] = "0" * 64
      document = numerical_document()
      document["provenance"] = provenance
      with self.assertRaises(compare.GateError) as raised:
        compare.check_acados_profile(document, "kinematic")
      self.assertIn("哈希", str(raised.exception))

  def test_profile_requires_binary_and_segment_identity(self):
    with tempfile.TemporaryDirectory() as workspace:
      ocp_path, manifest_path = write_profile_fixture(workspace, "kinematic")
      provenance = fake_provenance(workspace, ocp_path, manifest_path, "kinematic")
      provenance["segment_id"] = None
      document = numerical_document()
      document["provenance"] = provenance
      with self.assertRaises(compare.GateError) as raised:
        compare.check_acados_profile(document, "kinematic")
      self.assertIn("segment_id", str(raised.exception))

  def test_dynamic_profile_keeps_dt_scaled_cost(self):
    with tempfile.TemporaryDirectory() as workspace:
      ocp_path, manifest_path = write_profile_fixture(workspace, "dynamic")
      provenance = fake_provenance(workspace, ocp_path, manifest_path, "dynamic")
      document = numerical_document()
      document["provenance"] = provenance
      profile = compare.check_acados_profile(document, "dynamic_acados")
      self.assertEqual(profile["model"], "dynamic")


class TimingComparisonTest(unittest.TestCase):
  def test_identical_timings_pass(self):
    samples = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = compare.compare_timing(timing_document(samples),
                                    timing_document(samples), 200.0)
    self.assertEqual(result["failures"], [])
    self.assertAlmostEqual(result["release"]["p95"], 5.0)

  def test_regression_beyond_ten_percent_fails(self):
    noopt = timing_document([1.0] * 50)
    release = timing_document([1.5] * 50)
    result = compare.compare_timing(noopt, release, 200.0)
    self.assertTrue(result["failures"])

  def test_small_absolute_regression_is_allowed(self):
    noopt = timing_document([0.1] * 50)
    release = timing_document([0.28] * 50)
    result = compare.compare_timing(noopt, release, 200.0)
    self.assertEqual(result["failures"], [], result["failures"])

  def test_failure_count_increase_fails(self):
    noopt = timing_document([1.0] * 4)
    release = timing_document([1.0] * 4, successes=[True, False, True, True])
    result = compare.compare_timing(noopt, release, 200.0)
    self.assertTrue(any("失败拍数" in item for item in result["failures"]))

  def test_over_budget_increase_fails(self):
    noopt = timing_document([1.0, 2.0, 3.0, 4.0])
    release = timing_document([1.0, 2.0, 3.0, 250.0])
    result = compare.compare_timing(noopt, release, 200.0)
    self.assertTrue(result["failures"])

  def test_nearest_rank_percentile(self):
    values = [float(index) for index in range(1, 101)]
    self.assertEqual(compare.nearest_rank(values, 50), 50.0)
    self.assertEqual(compare.nearest_rank(values, 95), 95.0)
    self.assertEqual(compare.nearest_rank(values, 99), 99.0)
    self.assertEqual(compare.nearest_rank([7.0], 99), 7.0)


class PerScenarioGateTest(unittest.TestCase):
  def test_single_scenario_regression_fails_despite_aggregate_gain(self):
    noopt = multi_scenario_timing({"fast": [1.0] * 40, "slow": [10.0] * 40})
    release = multi_scenario_timing({"fast": [0.1] * 40, "slow": [20.0] * 40})
    result = compare.compare_timing(noopt, release, 200.0)
    self.assertTrue(any("slow" in item for item in result["failures"]),
                    result["failures"])
    self.assertFalse(any("fast" in item for item in result["failures"]))
    aggregate_release = sum(item["p95"] for item in
                            result["release_scenarios"]) / 2
    self.assertLess(aggregate_release, 20.0)

  def test_failure_count_regression_is_per_scenario(self):
    noopt = multi_scenario_timing({"a": [1.0] * 4, "b": [1.0] * 4})
    release = multi_scenario_timing({"a": [1.0] * 4, "b": [1.0] * 4})
    release["scenarios"][1]["steps"][2]["success"] = False
    result = compare.compare_timing(noopt, release, 200.0)
    self.assertEqual(len(result["failures"]), 1)
    self.assertIn("b:", result["failures"][0])

  def test_over_budget_regression_is_per_scenario(self):
    noopt = multi_scenario_timing({"a": [1.0] * 4, "b": [1.0] * 4})
    release = multi_scenario_timing({"a": [1.0] * 4, "b": [1.0, 1.0, 1.0, 300.0]})
    result = compare.compare_timing(noopt, release, 200.0)
    self.assertTrue(any("超预算" in item for item in result["failures"]))

  def test_all_scenarios_pass(self):
    noopt = multi_scenario_timing({"a": [10.0] * 40, "b": [20.0] * 40})
    release = multi_scenario_timing({"a": [10.0] * 40, "b": [19.0] * 40})
    result = compare.compare_timing(noopt, release, 200.0)
    self.assertEqual(result["failures"], [])


class EnvironmentGateTest(unittest.TestCase):
  def _write(self, root, variant, payload):
    directory = os.path.join(root, variant)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(root, "env.json"), "w", encoding="utf-8") as handle:
      json.dump(payload, handle)

  def test_valid_environment_passes(self):
    with tempfile.TemporaryDirectory() as workspace:
      self._write(workspace, "kinematic", environment_document())
      loaded = compare.load_environment(workspace, "kinematic")
      self.assertEqual(loaded["throttled_sticky"], 0)

  def test_missing_environment_record_fails(self):
    with tempfile.TemporaryDirectory() as workspace:
      os.makedirs(os.path.join(workspace, "kinematic"))
      with self.assertRaises(compare.GateError):
        compare.load_environment(workspace, "kinematic")

  def test_nonzero_sticky_throttle_bits_fail(self):
    with tempfile.TemporaryDirectory() as workspace:
      self._write(workspace, "kinematic", environment_document(throttled_sticky=0x50000))
      with self.assertRaises(compare.GateError) as raised:
        compare.load_environment(workspace, "kinematic")
      self.assertIn("粘连位", str(raised.exception))

  def test_hot_segment_start_fails(self):
    with tempfile.TemporaryDirectory() as workspace:
      document = environment_document(
        [{"label": "hot_start", "start_temperature_c": 62.5}])
      self._write(workspace, "kinematic", document)
      with self.assertRaises(compare.GateError) as raised:
        compare.load_environment(workspace, "kinematic")
      self.assertIn("62.5", str(raised.exception))

  def test_missing_throttle_reading_fails(self):
    with tempfile.TemporaryDirectory() as workspace:
      payload = environment_document()
      payload["throttled_sticky"] = None
      self._write(workspace, "kinematic", payload)
      with self.assertRaises(compare.GateError):
        compare.load_environment(workspace, "kinematic")


class CompareCliTest(unittest.TestCase):
  def _write_variant(self, root, name, numerical, timing):
    path = os.path.join(root, name)
    os.makedirs(path)
    model = compare.VARIANT_MODELS[name]
    ocp_path, manifest_path = write_profile_fixture(path, model)
    provenance = fake_provenance(path, ocp_path, manifest_path, model)
    for document in (numerical, timing):
      document["provenance"] = dict(provenance)
    with open(os.path.join(path, "numerical.json"), "w", encoding="utf-8") as handle:
      json.dump(numerical, handle)
    for index in (1, 2):
      with open(os.path.join(path, f"timing_{index}.json"), "w",
                encoding="utf-8") as handle:
        json.dump(timing, handle)

  def test_missing_variant_fails(self):
    with tempfile.TemporaryDirectory() as workspace:
      noopt = os.path.join(workspace, "noopt")
      release = os.path.join(workspace, "release")
      self._write_variant(noopt, "kinematic", numerical_document(),
                          timing_document([1.0]))
      os.makedirs(release)
      with self.assertRaises(compare.GateError):
        compare.resolve_variants(noopt, release)

  def test_variant_without_environment_record_fails(self):
    with tempfile.TemporaryDirectory() as workspace:
      noopt = os.path.join(workspace, "noopt")
      release = os.path.join(workspace, "release")
      for root in (noopt, release):
        self._write_variant(root, "kinematic", numerical_document(),
                            timing_document([1.0]))
        self._write_variant(root, "dynamic_acados", numerical_document(),
                            timing_document([1.0]))
      payload = environment_document()
      for root in (noopt, release):
        with open(os.path.join(root, "env.json"), "w", encoding="utf-8") as handle:
          json.dump(payload, handle)
      report = compare.compare_variants(noopt, release)
      self.assertTrue(report["ok"], report["failures"])
      # 删掉一侧的环境记录后必须失败, 不能靠缺省值放行
      os.remove(os.path.join(release, "env.json"))
      with self.assertRaises(compare.GateError):
        compare.compare_variants(noopt, release)

  def test_asymmetric_variant_sets_fail(self):
    with tempfile.TemporaryDirectory() as workspace:
      noopt = os.path.join(workspace, "noopt")
      release = os.path.join(workspace, "release")
      self._write_variant(noopt, "kinematic", numerical_document(),
                          timing_document([1.0]))
      self._write_variant(noopt, "dynamic_acados", numerical_document(),
                          timing_document([1.0]))
      self._write_variant(release, "kinematic", numerical_document(),
                          timing_document([1.0]))
      with self.assertRaises(compare.GateError):
        compare.resolve_variants(noopt, release)

  def test_output_directory_is_not_overwritten(self):
    with tempfile.TemporaryDirectory() as workspace:
      output = os.path.join(workspace, "report")
      os.makedirs(output)
      with open(os.path.join(output, "existing.txt"), "w", encoding="utf-8") as handle:
        handle.write("x")
      with self.assertRaises(compare.GateError):
        compare.write_outputs({"ok": True, "failures": [], "variants": {}},
                              "a", "b", output)


class RunnerGuardTest(unittest.TestCase):
  def test_runner_refuses_existing_target(self):
    import run_release_baseline as runner
    with tempfile.TemporaryDirectory() as workspace:
      target = os.path.join(workspace, "numerical.json")
      with open(target, "w", encoding="utf-8") as handle:
        handle.write("x")
      with self.assertRaises(runner.RunnerError):
        runner.require_absent(target)

  def test_runner_prerequisites_reject_missing_benchmarks(self):
    import run_release_baseline as runner
    with tempfile.TemporaryDirectory() as workspace:
      with self.assertRaises(runner.RunnerError):
        runner.check_prerequisites(workspace, workspace)

  def test_segment_with_throttle_failure_is_invalid(self):
    import run_release_baseline as runner
    segment = runner.Segment("release_kinematic_timing_1", "kinematic",
                             "kinematic", "timing_1", 1, ["true"], "raw", "final")
    segment.start = {"start_temperature_c": 50.0, "governor": "performance",
                     "boot_id": "abc", "throttled_sticky": None,
                     "throttled_raw": None, "throttled_errors": ["perm denied"]}
    segment.end = dict(segment.start)
    failures = runner.validate_measurement(segment, {}, None)
    self.assertTrue(any("get_throttled" in item for item in failures), failures)

  def test_segment_with_nonzero_sticky_bits_is_invalid(self):
    import run_release_baseline as runner
    segment = runner.Segment("release_kinematic_timing_1", "kinematic",
                             "kinematic", "timing_1", 1, ["true"], "raw", "final")
    segment.start = {"start_temperature_c": 50.0, "governor": "performance",
                     "boot_id": "abc", "throttled_sticky": 0x50000,
                     "throttled_raw": "throttled=0x50000", "throttled_errors": []}
    segment.end = dict(segment.start)
    failures = runner.validate_measurement(segment, {}, None)
    self.assertTrue(any("sticky" in item for item in failures), failures)

  def test_segment_with_hot_start_is_invalid(self):
    import run_release_baseline as runner
    segment = runner.Segment("release_kinematic_timing_1", "kinematic",
                             "kinematic", "timing_1", 1, ["true"], "raw", "final")
    start = {"start_temperature_c": 65.0, "governor": "performance", "boot_id": "abc",
             "throttled_sticky": 0, "throttled_raw": "throttled=0x0",
             "throttled_errors": []}
    segment.start = start
    segment.end = dict(start, start_temperature_c=64.0)
    failures = runner.validate_measurement(segment, {}, None)
    self.assertTrue(any("起始温度" in item for item in failures), failures)

  def test_segment_with_wrong_governor_is_invalid(self):
    import run_release_baseline as runner
    segment = runner.Segment("release_kinematic_timing_1", "kinematic",
                             "kinematic", "timing_1", 1, ["true"], "raw", "final")
    start = {"start_temperature_c": 50.0, "governor": "ondemand", "boot_id": "abc",
             "throttled_sticky": 0, "throttled_raw": "throttled=0x0",
             "throttled_errors": []}
    segment.start = start
    segment.end = dict(start)
    failures = runner.validate_measurement(segment, {}, None)
    self.assertTrue(any("governor" in item for item in failures), failures)

  def test_segment_across_boots_is_invalid(self):
    import run_release_baseline as runner
    segment = runner.Segment("release_kinematic_timing_1", "kinematic",
                             "kinematic", "timing_1", 1, ["true"], "raw", "final")
    start = {"temperature_c": 50.0, "governor": "performance", "boot_id": "abc",
             "throttled_sticky": 0, "throttled_raw": "throttled=0x0",
             "throttled_errors": []}
    segment.start = start
    segment.end = dict(start, boot_id="def")
    failures = runner.validate_measurement(segment, {}, None)
    self.assertTrue(any("boot_id" in item for item in failures), failures)

  def test_clean_segment_passes(self):
    import run_release_baseline as runner
    segment = runner.Segment("release_kinematic_timing_1", "kinematic",
                             "kinematic", "timing_1", 1, ["true"], "raw", "final")
    start = {"start_temperature_c": 50.0, "governor": "performance",
             "boot_id": "abc", "throttled_sticky": 0,
             "throttled_raw": "throttled=0x0", "throttled_errors": []}
    segment.start = start
    segment.end = dict(start)
    self.assertEqual(runner.validate_measurement(segment, {}, None), [])


class ServiceStabilityTest(unittest.TestCase):
  def _snapshot(self, active="active", pid="100", restarts="0",
                record="inactive", rtk="inactive"):
    return {
      "usv-system": {"returncode": 0, "ActiveState": active,
                     "MainPID": pid, "NRestarts": restarts},
      "usv-record": {"returncode": 0, "ActiveState": record},
      "usv-rtk": {"returncode": 0, "ActiveState": rtk},
    }

  def test_unchanged_active_service_passes(self):
    import run_release_baseline as runner
    snapshot = self._snapshot()
    self.assertEqual(
      runner.validate_service_stability("seg", snapshot, copy.deepcopy(snapshot)),
      [])

  def test_restart_count_increase_is_rejected(self):
    import run_release_baseline as runner
    failures = runner.validate_service_stability(
      "seg", self._snapshot(), self._snapshot(restarts="1"))
    self.assertTrue(any("NRestarts" in item for item in failures), failures)

  def test_pid_change_is_rejected(self):
    import run_release_baseline as runner
    failures = runner.validate_service_stability(
      "seg", self._snapshot(), self._snapshot(pid="101"))
    self.assertTrue(any("MainPID" in item for item in failures), failures)

  def test_inactive_production_service_is_rejected(self):
    import run_release_baseline as runner
    failures = runner.validate_service_stability(
      "seg", self._snapshot(), self._snapshot(active="failed"))
    self.assertTrue(any("ActiveState" in item for item in failures), failures)

  def test_record_service_started_during_measurement_is_rejected(self):
    import run_release_baseline as runner
    failures = runner.validate_service_stability(
      "seg", self._snapshot(), self._snapshot(record="active"))
    self.assertTrue(any("usv-record" in item for item in failures), failures)

  def test_untouched_flag_is_derived_not_assumed(self):
    import run_release_baseline as runner
    clean = [{"service_before": self._snapshot(),
              "service_after": self._snapshot()}]
    self.assertTrue(runner._service_untouched(clean))
    dirty = [{"service_before": self._snapshot(),
              "service_after": self._snapshot(restarts="2")}]
    self.assertFalse(runner._service_untouched(dirty))
    self.assertFalse(runner._service_untouched([]))


class ArtifactStabilityTest(unittest.TestCase):
  def test_hash_change_is_rejected(self):
    import run_release_baseline as runner
    before = {"binary": {"path": "/b", "sha256": "a" * 64},
              "shared_backend": {"path": "/s", "sha256": "b" * 64},
              "ocp_json": {"path": "/o", "sha256": "c" * 64},
              "source_manifest": {"path": "/m", "sha256": "d" * 64},
              "params": [{"path": "/p", "sha256": "e" * 64}]}
    after = copy.deepcopy(before)
    after["binary"]["sha256"] = "f" * 64
    failures = runner.validate_artifact_stability("seg", before, after)
    self.assertTrue(any("binary" in item for item in failures), failures)

  def test_parameter_change_is_rejected(self):
    import run_release_baseline as runner
    before = {"binary": {"path": "/b", "sha256": "a" * 64},
              "shared_backend": {"path": None, "sha256": None},
              "ocp_json": {"path": "/o", "sha256": "c" * 64},
              "source_manifest": {"path": "/m", "sha256": "d" * 64},
              "params": [{"path": "/p", "sha256": "e" * 64}]}
    after = copy.deepcopy(before)
    after["params"][0]["sha256"] = "0" * 64
    failures = runner.validate_artifact_stability("seg", before, after)
    self.assertTrue(any("参数文件" in item for item in failures), failures)


class StaticIdentityTest(unittest.TestCase):
  def test_compile_audit_flags_missing_release_optimization(self):
    class FakeRunner:
      def __init__(self, payload):
        self.payload = payload

      def exists(self, path):
        return True

      def read_text(self, path):
        return json.dumps(self.payload)

      def read_bytes(self, path):
        return json.dumps(self.payload).encode()

    payload = [
      {"file": "/r/src/usv_mpc/src/mpc_node.cpp",
       "command": "c++ -O0 -g -c -o mpc_node.o mpc_node.cpp"},
      {"file": "/r/src/usv_acados/acados_generated/dynamic/acados_solver_usv_dyn_nmpc.c",
       "command": "cc -O0 -c -o codegen.o codegen.c"},
      {"file": "/r/src/usv_acados/acados_generated/kinematic/acados_solver_usv_kin_mpc.c",
       "command": "cc -O0 -c -o codegen_kin.o codegen_kin.c"},
    ]
    result = capture.audit_compile_commands(FakeRunner(payload), "/r/build", "release")
    self.assertTrue(result["failures"])
    result = capture.audit_compile_commands(FakeRunner(payload), "/r/build", "noopt")
    self.assertEqual(result["failures"], [])

  def test_release_audit_accepts_o3_with_ndebug_for_c_and_cxx(self):
    class FakeRunner:
      def __init__(self, payload):
        self.payload = payload

      def exists(self, path):
        return True

      def read_text(self, path):
        return json.dumps(self.payload)

      def read_bytes(self, path):
        return json.dumps(self.payload).encode()

    payload = [
      {"file": "/r/src/usv_nmpc/src/mpc_node.cpp",
       "command": "c++ -O3 -DNDEBUG -c -o mpc_node.o mpc_node.cpp"},
      {"file": "/r/src/usv_acados/acados_generated/dynamic/acados_solver_usv_dyn_nmpc.c",
       "command": "cc -O3 -DNDEBUG -c -o codegen.o codegen.c"},
    ]
    result = capture.audit_compile_commands(
      FakeRunner(payload), "/r/build/usv_acados", "release", expect_codegen=True)
    self.assertEqual(result["failures"], [])
    self.assertEqual(len(result["records"]), 2)

  def test_both_generated_models_are_required(self):
    class FakeRunner:
      def __init__(self, payload):
        self.payload = payload

      def exists(self, path):
        return True

      def read_text(self, path):
        return json.dumps(self.payload)

      def read_bytes(self, path):
        return json.dumps(self.payload).encode()

    payload = [
      {"file": "/r/src/usv_acados/src/acados_backend.cpp",
       "command": "c++ -O3 -DNDEBUG -c -o acados_backend.o acados_backend.cpp"},
      # 只有 dynamic: 必须失败, 因为 kinematic 生成码没被编译。
      {"file": "/r/src/usv_acados/acados_generated/dynamic/acados_solver_usv_dyn_nmpc.c",
       "command": "cc -O3 -DNDEBUG -c -o codegen.o codegen.c"},
    ]
    result = capture.audit_all_compile_commands(
      FakeRunner(payload), ["/r/build/usv_acados"], "release")
    self.assertTrue(any("kinematic" in item for item in result["failures"]),
                    result["failures"])
    payload.append(
      {"file": "/r/src/usv_acados/acados_generated/kinematic/acados_solver_usv_kin_mpc.c",
       "command": "cc -O3 -DNDEBUG -c -o codegen_kin.o codegen_kin.c"})
    result = capture.audit_all_compile_commands(
      FakeRunner(payload), ["/r/build/usv_acados"], "release")
    self.assertEqual(result["failures"], [], result["failures"])

  def test_manifest_digest_changes_with_content(self):
    first = [{"path": "a", "size": 1, "sha256": "1" * 64}]
    second = [{"path": "a", "size": 1, "sha256": "2" * 64}]
    self.assertNotEqual(capture.manifest_digest(first), capture.manifest_digest(second))


if __name__ == "__main__":
  unittest.main()
