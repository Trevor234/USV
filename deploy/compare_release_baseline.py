#!/usr/bin/env python3
"""NoOpt 与 Release 两套构建的真实求解器基线对照。

输入为两个变体目录, 每个变体目录下按后端分子目录 (kinematic / dynamic_acados /
dynamic_casadi), 每个子目录含:
  numerical.json   数值阶段 (诊断预算, 完整 X/U 与约束残差)
  timing_1.json    计时阶段第 1 轮 (生产预算)
  timing_2.json    计时阶段第 2 轮 (生产预算)

输出 comparison.json 与 comparison.md; 任一硬门禁失败则非零退出。

门禁 (逐变体、逐场景, 不做全局平均):
  - 生成配置: 两侧都必须带 runner provenance, 且 OCP JSON 的求解器类型/
    迭代/超时/cost_scaling 与契约一致 (check_acados_profile);
  - 输入身份一致: 场景名/拍数/采样输入/solver_params 必须一致;
  - 数值阶段: 全部求解成功、解有限, 控制与预测状态在
    abs(a-b) <= 1e-4 + 1e-6*abs(a) 内 (航向按周期差);
  - 计时阶段: Release 的失败拍数、超预算拍数不多于 NoOpt,
    且 p95 <= max(NoOpt_p95*1.10, NoOpt_p95+0.2ms)。
"""

import argparse
import hashlib
import json
import math
import os
import sys

TOL_ABS = 1e-4
TOL_REL = 1e-6
# 采样输入在 -O0/-O3 之间的差别只允许浮点末位噪声 (含潜在 FMA 收缩)。
# 锚点取自上一拍求解输出, 经 IPOPT/acados 内部运算放大后末位差可达 1e-12 量级;
# 测量/参考由公式直接算出, 只受 FMA 影响。故按"由求解输出派生"与否分两档。
INPUT_TOL = 1e-12
DERIVED_INPUT_TOL = 1e-9
# 航向所在行 (方案 A 与 B 的预测轨迹第 3 行都是 psi)。
HEADING_ROW = 2
# 两个变体都是 acados 后端; 求解器预算烘焙在生成码里, 由 check_acados_profile
# 从 runner 绑定的 OCP JSON 核查 (不再有 IPOPT 预算字段)。
KNOWN_VARIANTS = ("kinematic", "dynamic_acados")
REQUIRED_VARIANTS = ("kinematic", "dynamic_acados")
# 每个变体对应的生成模型名 (provenance.model) 与 OCP JSON。
VARIANT_MODELS = {
  "kinematic": "kinematic",
  "dynamic_acados": "dynamic",
}
# 期望的生成器求解器配置 (与 usv_acados/scripts/regenerate_acados_codegen.py 一致)。
# 只允许旧参照 solver 预算字段与新 generated options 不同; 这里核对的是候选
# 实际链接的生成码, 不接受任何缺失元数据。
EXPECTED_OCP_PROFILE = {
  "kinematic": {
    "dims": {"N": 20, "nx": 7, "nu": 2, "np": 3, "np_global": 8,
             "ny_0": 6, "ny": 6, "ny_e": 4, "nh": 2, "nh_0": 2, "nbx_0": 7},
    "solver_options": {
      "nlp_solver_type": "SQP",
      "globalization": "MERIT_BACKTRACKING",
      "integrator_type": "DISCRETE",
      "qp_solver": "FULL_CONDENSING_HPIPM",
      "hessian_approx": "GAUSS_NEWTON",
      "nlp_solver_max_iter": 50,
      "qp_solver_iter_max": 200,
      "nlp_solver_tol_stat": 1e-4,
      "nlp_solver_tol_eq": 1e-4,
      "nlp_solver_tol_ineq": 1e-4,
      "nlp_solver_tol_comp": 1e-4,
      "timeout_max_time": 0.12,
      "print_level": 0,
      "tf": 4.0,
    },
    # 阶段代价不乘 dt: 21 个阶段全部为 1。
    "cost_scaling": [1.0] * 21,
  },
  "dynamic": {
    "dims": {"N": 20, "nx": 8, "nu": 2, "np": 6, "np_global": 30,
             "ny_0": 11, "ny": 11, "ny_e": 7, "nh": 2, "nh_0": 2, "nbx_0": 8},
    "solver_options": {
      "nlp_solver_type": "SQP_RTI",
      "integrator_type": "DISCRETE",
      "qp_solver": "FULL_CONDENSING_HPIPM",
      "hessian_approx": "GAUSS_NEWTON",
      "nlp_solver_max_iter": 50,
      "qp_solver_iter_max": 200,
      "tf": 4.0,
    },
    # B 保持 acados 默认阶段 dt 缩放: [dt x N, 1]。
    "cost_scaling": [0.2] * 20 + [1.0],
  },
}


class GateError(Exception):
  pass


def load_json(path):
  with open(path, "r", encoding="utf-8") as handle:
    return json.load(handle)


def finite(value, context):
  if not isinstance(value, (int, float)) or isinstance(value, bool):
    raise GateError(f"{context} 不是数值: {value!r}")
  value = float(value)
  if not math.isfinite(value):
    raise GateError(f"{context} 非有限数: {value!r}")
  return value


def angular_difference(a, b):
  delta = math.fmod(a - b + math.pi, 2.0 * math.pi)
  if delta < 0.0:
    delta += 2.0 * math.pi
  return delta - math.pi


def flatten_matrix(rows, context):
  if not isinstance(rows, list) or not rows:
    raise GateError(f"{context} 不是非空二维数组")
  width = None
  flat = []
  for row in rows:
    if not isinstance(row, list):
      raise GateError(f"{context} 行不是数组")
    if width is None:
      width = len(row)
    elif len(row) != width:
      raise GateError(f"{context} 各行长度不一致")
    flat.append([finite(value, context) for value in row])
  return flat


def compare_matrices(reference, candidate, context, periodic_rows=()):
  ref = flatten_matrix(reference, context + ".noopt")
  cand = flatten_matrix(candidate, context + ".release")
  if len(ref) != len(cand) or len(ref[0]) != len(cand[0]):
    raise GateError(
      f"{context} 维度不一致: noopt={len(ref)}x{len(ref[0])} "
      f"release={len(cand)}x{len(cand[0])}")
  max_delta = 0.0
  worst = None
  for row, (ref_row, cand_row) in enumerate(zip(ref, cand)):
    for col, (ref_value, cand_value) in enumerate(zip(ref_row, cand_row)):
      if row in periodic_rows:
        delta = abs(angular_difference(cand_value, ref_value))
      else:
        delta = abs(cand_value - ref_value)
      if delta > max_delta:
        max_delta = delta
        worst = (row, col)
      limit = TOL_ABS + TOL_REL * abs(ref_value)
      if delta > limit:
        raise GateError(
          f"{context}[{row},{col}] 超差: noopt={ref_value!r} "
          f"release={cand_value!r} 差={delta:.3e} 容差={limit:.3e}")
  return max_delta, worst


def compare_vectors(reference, candidate, context, periodic=False):
  return compare_matrices([reference], [candidate], context,
                          periodic_rows=(0,) if periodic else ())


def _input_matrix(reference, candidate, context):
  ref = flatten_matrix(reference, context + ".noopt")
  cand = flatten_matrix(candidate, context + ".release")
  if len(ref) != len(cand) or len(ref[0]) != len(cand[0]):
    raise GateError(
      f"{context} 输入维度不一致: noopt={len(ref)}x{len(ref[0])} "
      f"release={len(cand)}x{len(cand[0])}")
  for row, (ref_row, cand_row) in enumerate(zip(ref, cand)):
    for col, (ref_value, cand_value) in enumerate(zip(ref_row, cand_row)):
      if abs(ref_value - cand_value) > INPUT_TOL:
        raise GateError(
          f"{context}[{row},{col}] 输入不一致: noopt={ref_value!r} "
          f"release={cand_value!r}")


def compare_inputs(reference, candidate, context, derived=False):
  """采样输入必须来自同一场景定义。

  derived=True 表示该输入由上一次求解输出派生 (锚点), 允许更大的末位噪声。
  """
  tolerance = DERIVED_INPUT_TOL if derived else INPUT_TOL
  if isinstance(reference, list):
    if not isinstance(candidate, list):
      raise GateError(f"{context} 输入结构不一致")
    if reference and isinstance(reference[0], list):
      _input_matrix(reference, candidate, context)
      return
    if len(reference) != len(candidate):
      raise GateError(f"{context} 输入长度不一致")
    for index, (ref_value, cand_value) in enumerate(zip(reference, candidate)):
      _input_scalar(ref_value, cand_value, f"{context}[{index}]", tolerance)
    return
  if isinstance(candidate, list):
    raise GateError(f"{context} 输入结构不一致")
  _input_scalar(reference, candidate, context, tolerance)


def _input_scalar(reference, candidate, context, tolerance=INPUT_TOL):
  ref_value = finite(reference, context + ".noopt")
  cand_value = finite(candidate, context + ".release")
  if abs(ref_value - cand_value) > tolerance:
    raise GateError(
      f"{context} 输入不一致: noopt={ref_value!r} release={cand_value!r} "
      f"(容差 {tolerance:g})")


def deep_equal(reference, candidate, context):
  if type(reference) is not type(candidate):
    # int 与 float 在 JSON 中含义相同, 只有 bool 需要区分
    if isinstance(reference, bool) or isinstance(candidate, bool):
      raise GateError(f"{context} 类型不一致")
    if not (isinstance(reference, (int, float)) and isinstance(candidate, (int, float))):
      raise GateError(f"{context} 类型不一致")
  if isinstance(reference, dict):
    if set(reference) != set(candidate):
      raise GateError(f"{context} 键集合不一致")
    for key in reference:
      deep_equal(reference[key], candidate[key], f"{context}.{key}")
    return
  if isinstance(reference, list):
    if len(reference) != len(candidate):
      raise GateError(f"{context} 长度不一致")
    for index, (ref_item, cand_item) in enumerate(zip(reference, candidate)):
      deep_equal(ref_item, cand_item, f"{context}[{index}]")
    return
  if isinstance(reference, float) or isinstance(candidate, float):
    if float(reference) != float(candidate):
      raise GateError(
        f"{context} 不一致: noopt={reference!r} release={candidate!r}")
    return
  if reference != candidate:
    raise GateError(f"{context} 不一致: noopt={reference!r} release={candidate!r}")


def check_identity(noopt, release):
  if noopt.get("program") != release.get("program"):
    raise GateError("两份结果来自不同诊断程序")
  if noopt.get("package") != release.get("package"):
    raise GateError("两份结果的包名不同")
  if noopt.get("backend") != release.get("backend"):
    raise GateError("两份结果的后端不同")
  if noopt.get("phase") != release.get("phase"):
    raise GateError("两份结果的阶段不同")
  deep_equal(noopt.get("solver_params"), release.get("solver_params"),
             "solver_params")
  noopt_scenarios = [item.get("name") for item in noopt.get("scenarios", [])]
  release_scenarios = [item.get("name") for item in release.get("scenarios", [])]
  if noopt_scenarios != release_scenarios:
    raise GateError(
      f"场景序列不一致: noopt={noopt_scenarios} release={release_scenarios}")


def _sha256_file(path):
  digest = hashlib.sha256()
  with open(path, "rb") as handle:
    for chunk in iter(lambda: handle.read(65536), b""):
      digest.update(chunk)
  return digest.hexdigest()


def check_acados_profile(document, variant):
  """核对候选整体确实是声明的 acados 生成配置。

  数据来源是 runner 写入的 provenance: 它把 benchmark 与 OCP JSON、二进制、
  共用库、YAML 一起绑定。这里重新读 OCP JSON 并逐项核对求解器类型/迭代/
  超时/cost_scaling。任何元数据缺失一律失败 —— 不允许"缺字段就放行"。
  """
  model = VARIANT_MODELS.get(variant)
  if model is None:
    raise GateError(f"未知变体: {variant}")
  provenance = document.get("provenance")
  if not isinstance(provenance, dict):
    raise GateError(f"{variant}: 缺少 provenance (未由 runner 生成, 对照无效)")
  ocp_json_path = provenance.get("ocp_json_path")
  if not ocp_json_path:
    raise GateError(f"{variant}: provenance 缺少 ocp_json_path")
  if provenance.get("model") != model:
    raise GateError(
      f"{variant}: provenance.model={provenance.get('model')!r} 与变体不符")
  if not os.path.isabs(ocp_json_path) or not os.path.exists(ocp_json_path):
    raise GateError(f"{variant}: OCP JSON 不存在: {ocp_json_path}")
  recorded = provenance.get("ocp_json_sha256")
  if not recorded:
    raise GateError(f"{variant}: provenance 缺少 ocp_json_sha256")
  actual = _sha256_file(ocp_json_path)
  if actual != recorded:
    raise GateError(
      f"{variant}: OCP JSON 哈希与 provenance 不符 ({actual} != {recorded})")
  source_root = provenance.get("source_manifest_path")
  if not source_root or not os.path.exists(source_root):
    raise GateError(f"{variant}: provenance 缺少可读的 source_manifest_path")

  with open(ocp_json_path, "r", encoding="utf-8") as handle:
    ocp = json.load(handle)
  expected = EXPECTED_OCP_PROFILE[model]
  failures = []
  dims = ocp.get("dims")
  if not isinstance(dims, dict):
    failures.append("OCP JSON 缺少 dims")
  else:
    for key, value in expected["dims"].items():
      if dims.get(key) != value:
        failures.append(f"dims.{key}={dims.get(key)!r} != {value!r}")
  options = ocp.get("solver_options")
  if not isinstance(options, dict):
    failures.append("OCP JSON 缺少 solver_options")
  else:
    for key, value in expected["solver_options"].items():
      if options.get(key) != value:
        failures.append(f"solver_options.{key}={options.get(key)!r} != {value!r}")
    scaling = options.get("cost_scaling")
    if [float(item) for item in (scaling or [])] != expected["cost_scaling"]:
      failures.append(
        f"solver_options.cost_scaling={scaling!r} != {expected['cost_scaling']!r}")
  # 二进制/共用库身份也必须存在 (缺失即无法证明测的是这份候选)。
  for key in ("binary_path", "binary_sha256", "shared_backend_path",
              "shared_backend_sha256", "segment_id", "returncode"):
    if provenance.get(key) in (None, ""):
      failures.append(f"provenance.{key} 缺失")
  if provenance.get("returncode") not in (0,):
    failures.append(f"provenance.returncode={provenance.get('returncode')!r} 非 0")
  if failures:
    raise GateError(f"{variant}: 生成器配置与契约不一致: " + "; ".join(failures))
  return {
    "model": model,
    "ocp_json": ocp_json_path,
    "ocp_json_sha256": actual,
    "segment_id": provenance.get("segment_id"),
  }


def scenario_steps(document):
  steps = {}
  for scenario in document.get("scenarios", []):
    name = scenario.get("name")
    if name in steps:
      raise GateError(f"场景重复: {name}")
    steps[name] = scenario.get("steps", [])
  return steps


def compare_numerical(noopt, release):
  check_identity(noopt, release)
  noopt_steps = scenario_steps(noopt)
  release_steps = scenario_steps(release)
  if not noopt_steps:
    raise GateError("数值结果缺少场景")
  report = []
  for name, ref_steps in noopt_steps.items():
    cand_steps = release_steps[name]
    if len(ref_steps) != len(cand_steps):
      raise GateError(f"{name} 拍数不一致")
    max_control = 0.0
    max_state = 0.0
    for index, (ref_step, cand_step) in enumerate(zip(ref_steps, cand_steps)):
      context = f"{name}[{index}]"
      if not ref_step.get("success") or not cand_step.get("success"):
        raise GateError(
          f"{context} 求解失败: noopt={ref_step.get('success')} "
          f"release={cand_step.get('success')}")
      if ref_step.get("backend") != cand_step.get("backend"):
        raise GateError(f"{context} 后端标识不一致")
      # 输入身份
      ref_input = ref_step.get("input", {})
      cand_input = cand_step.get("input", {})
      if set(ref_input) != set(cand_input):
        raise GateError(f"{context} 输入字段不一致")
      for key in ref_input:
        compare_inputs(ref_input[key], cand_input[key],
                       f"{context}.input.{key}", derived=(key == "anchor"))
      control_delta, _ = compare_vectors(
        ref_step.get("control"), cand_step.get("control"), f"{context}.control")
      max_control = max(max_control, control_delta)
      x_delta, _ = compare_matrices(
        ref_step.get("X"), cand_step.get("X"), f"{context}.X",
        periodic_rows=(HEADING_ROW,))
      u_delta, _ = compare_matrices(
        ref_step.get("U"), cand_step.get("U"), f"{context}.U")
      max_state = max(max_state, x_delta, u_delta)
    report.append({
      "scenario": name,
      "steps": len(ref_steps),
      "max_control_delta": max_control,
      "max_state_delta": max_state,
    })
  return report


def nearest_rank(sorted_values, percentile):
  if not sorted_values:
    raise GateError("空样本无法计算分位数")
  rank = int(math.ceil(percentile / 100.0 * len(sorted_values)))
  index = min(max(rank - 1, 0), len(sorted_values) - 1)
  return sorted_values[index]


def timing_statistics(document, budget_ms):
  samples = []
  failures = 0
  over_budget = 0
  report = []
  for scenario in document.get("scenarios", []):
    name = scenario.get("name")
    wall = []
    scenario_failures = 0
    for step in scenario.get("steps", []):
      value = finite(step.get("wall_ms"), f"{name}.wall_ms")
      wall.append(value)
      if not step.get("success"):
        scenario_failures += 1
    if not wall:
      raise GateError(f"{name} 无计时样本")
    failures += scenario_failures
    over = sum(1 for value in wall if value > budget_ms)
    over_budget += over
    ordered = sorted(wall)
    entry = {
      "scenario": name,
      "samples": len(ordered),
      "failures": scenario_failures,
      "p50": nearest_rank(ordered, 50),
      "p95": nearest_rank(ordered, 95),
      "p99": nearest_rank(ordered, 99),
      "max": ordered[-1],
      "over_budget": over,
    }
    report.append(entry)
    samples.extend(wall)
  ordered_all = sorted(samples)
  aggregate = {
    "samples": len(ordered_all),
    "failures": failures,
    "p50": nearest_rank(ordered_all, 50),
    "p95": nearest_rank(ordered_all, 95),
    "p99": nearest_rank(ordered_all, 99),
    "max": ordered_all[-1],
    "over_budget": over_budget,
  }
  return aggregate, report


def compare_timing(noopt, release, budget_ms):
  check_identity(noopt, release)
  noopt_steps = scenario_steps(noopt)
  release_steps = scenario_steps(release)
  if not noopt_steps:
    raise GateError("计时结果缺少场景")
  if [item.get("name") for item in noopt.get("scenarios", [])] != \
     [item.get("name") for item in release.get("scenarios", [])]:
    raise GateError("计时场景序列不一致")
  for name, ref_steps in noopt_steps.items():
    cand_steps = release_steps[name]
    if len(ref_steps) != len(cand_steps):
      raise GateError(f"{name} 计时拍数不一致")
    for index, (ref_step, cand_step) in enumerate(zip(ref_steps, cand_steps)):
      ref_input = ref_step.get("input")
      cand_input = cand_step.get("input")
      if (ref_input is None) != (cand_input is None):
        raise GateError(f"{name}[{index}] 采样输入记录不一致")
      if ref_input is not None:
        for key in ref_input:
          if key not in cand_input:
            raise GateError(f"{name}[{index}] 采样输入缺少字段 {key}")
          compare_inputs(ref_input[key], cand_input[key],
                         f"{name}[{index}].{key}", derived=(key == "anchor"))
  noopt_stats, noopt_scenarios = timing_statistics(noopt, budget_ms)
  release_stats, release_scenarios = timing_statistics(release, budget_ms)

  # 门禁逐场景判定: 聚合平均会掩盖单场景退化。
  failures = []
  scenario_gates = []
  noopt_by_name = {item["scenario"]: item for item in noopt_scenarios}
  release_by_name = {item["scenario"]: item for item in release_scenarios}
  if list(noopt_by_name) != list(release_by_name):
    raise GateError("逐场景统计的场景集合不一致")
  for name, ref in noopt_by_name.items():
    cand = release_by_name[name]
    limit = max(ref["p95"] * 1.10, ref["p95"] + 0.2)
    scenario_failures = []
    if cand["failures"] > ref["failures"]:
      scenario_failures.append(
        f"失败拍数增加: noopt={ref['failures']} release={cand['failures']}")
    if cand["over_budget"] > ref["over_budget"]:
      scenario_failures.append(
        f"超预算拍数增加: noopt={ref['over_budget']} "
        f"release={cand['over_budget']}")
    if cand["p95"] > limit:
      scenario_failures.append(
        f"p95 门槛未通过: noopt={ref['p95']:.3f}ms "
        f"release={cand['p95']:.3f}ms 门槛={limit:.3f}ms")
    scenario_gates.append({
      "scenario": name,
      "limit_p95": limit,
      "noopt": ref,
      "release": cand,
      "failures": scenario_failures,
    })
    failures.extend(f"{name}: {item}" for item in scenario_failures)
  return {
    "failures": failures,
    "scenarios": scenario_gates,
    "noopt": noopt_stats,
    "release": release_stats,
    "noopt_scenarios": noopt_scenarios,
    "release_scenarios": release_scenarios,
  }


MAX_SEGMENT_START_TEMPERATURE_C = 60.0


def load_environment(root, variant_name):
  """读取变体目录下的分段环境记录 (由 run_bench.sh 生成)。

  计划要求: 段前温度不高于 60 °C, 且欠压/限频/热节流标志为 0, 否则该段无效。
  缺失记录同样按无效处理 —— 没有环境证据的耗时结论不可审计。
  """
  path = os.path.join(root, "env.json")
  if not os.path.exists(path):
    raise GateError(f"{variant_name} 缺少环境记录: {path}")
  payload = load_json(path)
  failures = []
  if payload.get("throttled_sticky") is None:
    failures.append(f"{variant_name}: 缺少 get_throttled 粘连位读数")
  elif payload["throttled_sticky"] != 0:
    failures.append(
      f"{variant_name}: get_throttled 粘连位非零 0x{payload['throttled_sticky']:x}"
      " (本 boot 内发生过欠压/限频/热节流)")
  for segment in payload.get("segments", []):
    start = segment.get("start_temperature_c")
    if start is None:
      failures.append(f"{variant_name}/{segment.get('label')}: 缺少起始温度")
    elif start > MAX_SEGMENT_START_TEMPERATURE_C:
      failures.append(
        f"{variant_name}/{segment.get('label')}: 起始温度 {start:.1f}°C "
        f"高于 {MAX_SEGMENT_START_TEMPERATURE_C:.0f}°C")
  if not payload.get("segments"):
    failures.append(f"{variant_name}: 环境记录里没有分段")
  if failures:
    raise GateError("; ".join(failures))
  return payload


def variant_directories(root):
  if not os.path.isdir(root):
    raise GateError(f"目录不存在: {root}")
  present = {}
  for name in sorted(os.listdir(root)):
    path = os.path.join(root, name)
    if not os.path.isdir(path):
      continue
    if name not in KNOWN_VARIANTS:
      raise GateError(f"未知变体目录: {path}")
    present[name] = path
  return present


def resolve_variants(noopt_root, release_root):
  noopt = variant_directories(noopt_root)
  release = variant_directories(release_root)
  if set(noopt) != set(release):
    raise GateError(
      f"两侧变体集合不一致: noopt={sorted(noopt)} release={sorted(release)}")
  missing = [name for name in REQUIRED_VARIANTS if name not in noopt]
  if missing:
    raise GateError(f"缺少必需变体: {missing}")
  return noopt, release


def compare_variants(noopt_root, release_root):
  noopt_variants, release_variants = resolve_variants(noopt_root, release_root)
  report = {"ok": True, "failures": [], "variants": {}, "environment": {}}
  # 环境有效性先于任何耗时结论: 无效环境直接失败, 不进入统计比较。
  environment = {}
  for name in sorted(noopt_variants):
    environment[name] = {
      "noopt": load_environment(noopt_root, name),
      "release": load_environment(release_root, name),
    }
  report["environment"] = environment
  for name in sorted(noopt_variants):
    entry = {}
    profiles = {}
    timing_profiles = {}
    noopt_numerical = load_json(os.path.join(noopt_variants[name], "numerical.json"))
    release_numerical = load_json(os.path.join(release_variants[name], "numerical.json"))
    for document, side in ((noopt_numerical, "noopt"), (release_numerical, "release")):
      if document.get("phase") != "numerical":
        raise GateError(f"{name} {side} 的数值文件 phase 不是 numerical")
      profiles[side] = check_acados_profile(document, name)
    entry["numerical"] = compare_numerical(noopt_numerical, release_numerical)
    entry["profile"] = profiles
    params = noopt_numerical.get("solver_params", {})
    budget_ms = float(params.get("max_solve_time_ms", 200.0))
    entry["budget_ms"] = budget_ms
    entry["rounds"] = []
    for round_index in (1, 2):
      filename = f"timing_{round_index}.json"
      noopt_timing = load_json(os.path.join(noopt_variants[name], filename))
      release_timing = load_json(os.path.join(release_variants[name], filename))
      for document, side in ((noopt_timing, "noopt"), (release_timing, "release")):
        if document.get("phase") != "timing":
          raise GateError(f"{name} {side} 的 {filename} phase 不是 timing")
        timing_profiles[side] = check_acados_profile(document, name)
      result = compare_timing(noopt_timing, release_timing, budget_ms)
      entry["rounds"].append({"round": round_index, "profiles": timing_profiles,
                              **result})
      for failure in result["failures"]:
        report["failures"].append(f"{name} 第{round_index}轮: {failure}")
    report["variants"][name] = entry
  report["ok"] = not report["failures"]
  return report


def format_milliseconds(value):
  return f"{value:.3f}"


def render_markdown(report, noopt_root, release_root):
  lines = ["# Release 基线对照 (NoOpt vs Release)", ""]
  lines.append(f"- NoOpt: `{noopt_root}`")
  lines.append(f"- Release: `{release_root}`")
  lines.append(f"- 结论: {'通过' if report['ok'] else '失败'}")
  if report["failures"]:
    lines.append("")
    for failure in report["failures"]:
      lines.append(f"- 未通过: {failure}")
  for name, entry in report["variants"].items():
    lines.append("")
    lines.append(f"## 变体 {name}")
    lines.append("")
    lines.append("### 数值一致性 (诊断预算, 容差 1e-4 + 1e-6|a|)")
    lines.append("")
    lines.append("| 场景 | 拍数 | 最大控制差 | 最大状态/预测差 |")
    lines.append("|---|---|---|---|")
    for item in entry["numerical"]:
      lines.append(
        f"| {item['scenario']} | {item['steps']} | "
        f"{item['max_control_delta']:.3e} | {item['max_state_delta']:.3e} |")
    lines.append("")
    lines.append(f"### 完整 solve() 墙钟耗时 (预算 {entry['budget_ms']:.1f} ms, "
                 "门禁逐场景判定)")
    for round_entry in entry["rounds"]:
      lines.append("")
      lines.append(f"第 {round_entry['round']} 轮")
      lines.append("")
      lines.append("| 场景 | 构建 | 样本 | 失败 | 超预算 | p50 | p95 | p99 | "
                   "max | p95 门槛 | 结果 |")
      lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
      for gate in round_entry["scenarios"]:
        outcome = "通过" if not gate["failures"] else "未通过"
        for label, stats in (("NoOpt", gate["noopt"]),
                             ("Release", gate["release"])):
          lines.append(
            f"| {gate['scenario']} | {label} | {stats['samples']} | "
            f"{stats['failures']} | {stats['over_budget']} | "
            f"{format_milliseconds(stats['p50'])} | "
            f"{format_milliseconds(stats['p95'])} | "
            f"{format_milliseconds(stats['p99'])} | "
            f"{format_milliseconds(stats['max'])} | "
            f"{format_milliseconds(gate['limit_p95'])} | {outcome} |")
      aggregate = (f"合计 NoOpt {round_entry['noopt']['failures']} 失败 / "
                   f"{round_entry['noopt']['over_budget']} 超预算; "
                   f"Release {round_entry['release']['failures']} 失败 / "
                   f"{round_entry['release']['over_budget']} 超预算")
      lines.append("")
      lines.append(aggregate)
  lines.append("")
  return "\n".join(lines)


def write_outputs(report, noopt_root, release_root, output_dir):
  if os.path.isdir(output_dir) and os.listdir(output_dir):
    raise GateError(f"输出目录非空, 拒绝覆盖: {output_dir}")
  os.makedirs(output_dir, exist_ok=True)
  with open(os.path.join(output_dir, "comparison.json"), "w",
            encoding="utf-8") as handle:
    json.dump(report, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
  with open(os.path.join(output_dir, "comparison.md"), "w",
            encoding="utf-8") as handle:
    handle.write(render_markdown(report, noopt_root, release_root))


def main(argv):
  parser = argparse.ArgumentParser(description="NoOpt/Release 基线对照")
  parser.add_argument("--noopt", required=True, help="NoOpt 变体目录")
  parser.add_argument("--release", required=True, help="Release 变体目录")
  parser.add_argument("--output", required=True, help="输出报告目录 (必须为空)")
  args = parser.parse_args(argv)
  try:
    report = compare_variants(args.noopt, args.release)
    write_outputs(report, args.noopt, args.release, args.output)
  except GateError as error:
    print(f"对照失败: {error}", file=sys.stderr)
    return 1
  for failure in report["failures"]:
    print(f"未通过: {failure}", file=sys.stderr)
  print(f"对照{'通过' if report['ok'] else '失败'}: {args.output}")
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
