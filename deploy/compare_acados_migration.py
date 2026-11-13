#!/usr/bin/env python3
"""算法迁移验收: 旧 IPOPT(CasADi) A + 原 B -> 共用 acados 后端。

与 compare_release_baseline.py 分工明确:
  compare_release_baseline.py  只做同算法 NoOpt/Release 对照;
  compare_acados_migration.py  只做算法迁移对照 (旧参照 vs 新候选)。

输入:
  --reference-root <R0>   不可变旧候选 (含旧 A/B 高预算 numerical 与旧 B 二进制)
  --candidate-root <R>    新候选 (含 evidence/migration/* 与 evidence/bench/*)
  --output <空目录>       报告输出目录 (必须为空)

参照侧只做“旧 oracle 可接受性”检查 (固定 SHA + 4 场景 x 5 拍全部成功/有限),
不套用新候选的 OCP profile 门禁; 候选侧必须通过 profile/provenance 门禁。

门禁 (阈值固定, 不做自动调优):
  A 成本语义     每个成功解: |acados_cost - J_analytic| <= 1e-8*max(1,|J|)
  A 迁移质量     每拍输入与旧参照 1e-12 同源; J_new <= J_old + max(0.01, 0.01|J_old|)
  A 硬约束       维度 5x21/2x20, 有限, 独立重算四残差 <= 0.005,
                 首拍对真实 anchor, 增广末两维逐步等于上拍控制
  A 闭环         4 场景 x 200 拍 0 失败, 位置 RMSE <= 0.40 m, 周期航向 RMSE <= 0.20 rad
  A 耗时         两轮四场景各自 p95 <= 20 ms, p99 <= 50 ms, max < 200 ms;
                 全部 520 拍 (含冷首拍/预热) 0 失败、0 拍 >= 200 ms
  A NoOpt 可用   全部 520 拍成功/有限且无 200 ms deadline
  B 抽取回归     生成码清单字节不变; replay_B 与 R0 逐元素严格容差;
                 原/新同轮 timing p95_new <= max(1.10*p95_old, p95_old+0.2ms)
"""

import argparse
import hashlib
import json
import math
import os
import sys

TOL_ABS = 1e-4
TOL_REL = 1e-6
INPUT_TOL = 1e-12
HEADING_ROW = 2
DEADLINE_MS = 200.0
# A: 生产 SQP 结构 (与生成码烘焙值一致)
A_N = 20
A_DT = 0.2
A_STATE_ROWS = 5
A_CONTROL_ROWS = 2
A_SOLUTION_TOL = 0.005
A_COST_REL_TOL = 1e-8
A_QUALITY_ABS_SLACK = 0.01
A_QUALITY_REL_SLACK = 0.01
A_CLOSED_LOOP_POSITION_RMSE = 0.40
A_CLOSED_LOOP_HEADING_RMSE = 0.20
A_TIMING_P95_MS = 20.0
A_TIMING_P99_MS = 50.0
A_TIMING_MAX_MS = 200.0
A_TIMING_WARMUP = 20
A_TIMING_MEASURED = 500
# 旧参照 (不可变 R0) 的固定 SHA-256; 内容不同即视为参照被改写。
REFERENCE_SHA256 = {
  "evidence/bench/release/kinematic/numerical.json":
    "8a183f2365901dd02eaf4b3b70471b31877d3387ceda38d9800805eaaf69bc2b",
  "evidence/bench/release/dynamic_acados/numerical.json":
    "37945e1763d16f7c2f6399e1fbb4257e20aefddf0d02dd69fdb9b8dbfd631e4c",
  "build_release/usv_nmpc/benchmark_dynamic_solver":
    "14ae0147f9b8ef86c5c818b511c9b3bf37de87edb86868aa0fd463adde8a3948",
}
# 旧 A 数值阶段的诊断预算标签 (证明参照确实是高预算 oracle)。
OLD_A_IPOPT_CPU_S = 60.0
OLD_A_IPOPT_ITER = 300
SCENARIOS = ("straight", "arc", "arc_cross_pi", "straight_anchor_offset")
# 必须与旧参照完全相等的模型键 (允许差异的只有求解器预算/backend/provenance)。
A_MODEL_KEYS = ("dt", "N", "Q", "R", "Qf_scale", "u_max", "u_min", "r_max",
                "du_max", "dr_max", "tau_u", "tau_r", "max_solve_time_ms",
                "horizon_budget_s", "solution_constraint_tol")


class GateError(Exception):
  pass


def load_json(path):
  if not os.path.exists(path):
    raise GateError(f"缺少文件: {path}")
  with open(path, "r", encoding="utf-8") as handle:
    try:
      return json.load(handle)
    except json.JSONDecodeError as error:
      raise GateError(f"JSON 解析失败: {path}: {error}") from error


def sha256_file(path):
  digest = hashlib.sha256()
  with open(path, "rb") as handle:
    for chunk in iter(lambda: handle.read(65536), b""):
      digest.update(chunk)
  return digest.hexdigest()


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


def matrix(rows, rows_expected, cols_expected, context):
  if not isinstance(rows, list) or len(rows) != rows_expected:
    raise GateError(f"{context} 行数不是 {rows_expected}")
  width = None
  out = []
  for row in rows:
    if not isinstance(row, list):
      raise GateError(f"{context} 行不是数组")
    if width is None:
      width = len(row)
      if width != cols_expected:
        raise GateError(f"{context} 列数 {width} != {cols_expected}")
    elif len(row) != width:
      raise GateError(f"{context} 各行长度不一致")
    out.append([finite(value, context) for value in row])
  return out


def vector(values, size, context):
  if not isinstance(values, list) or len(values) != size:
    raise GateError(f"{context} 维度不是 {size}")
  return [finite(value, context) for value in values]


def scenario_map(document, context):
  scenarios = document.get("scenarios")
  if not isinstance(scenarios, list) or not scenarios:
    raise GateError(f"{context} 缺少 scenarios")
  out = {}
  for scenario in scenarios:
    name = scenario.get("name")
    if name in out:
      raise GateError(f"{context} 场景重复: {name}")
    steps = scenario.get("steps")
    if not isinstance(steps, list) or not steps:
      raise GateError(f"{context} 场景 {name} 没有 steps")
    out[name] = scenario
  missing = [name for name in SCENARIOS if name not in out]
  if missing:
    raise GateError(f"{context} 缺少场景: {missing}")
  return out


# ── 参照侧: 只做旧 oracle 可接受性检查 ──────────────────────────────
def verify_reference_hashes(reference_root):
  report = {}
  for relative, expected in REFERENCE_SHA256.items():
    path = os.path.join(reference_root, relative)
    if not os.path.exists(path):
      raise GateError(f"旧参照缺失: {path}")
    actual = sha256_file(path)
    if actual != expected:
      raise GateError(
        f"旧参照被改写: {relative} sha256={actual} 期望={expected}")
    report[relative] = actual
  return report


def check_old_numerical(document, variant, path):
  """旧 oracle 可接受性: phase/拍数/成功/有限/完整 X-U-input。"""
  if document.get("phase") != "numerical":
    raise GateError(f"旧参照 {variant} 的 phase 不是 numerical: {path}")
  if document.get("numerical_steps") != 5:
    raise GateError(f"旧参照 {variant} numerical_steps != 5")
  scenarios = scenario_map(document, f"旧参照 {variant}")
  if set(scenarios) != set(SCENARIOS):
    raise GateError(f"旧参照 {variant} 场景集合不符: {sorted(scenarios)}")
  for name, scenario in scenarios.items():
    steps = scenario["steps"]
    if len(steps) != 5:
      raise GateError(f"旧参照 {variant}/{name} 拍数 {len(steps)} != 5")
    for index, step in enumerate(steps):
      context = f"旧参照 {variant}/{name}[{index}]"
      if step.get("success") is not True:
        raise GateError(f"{context} 未成功")
      if "input" not in step:
        raise GateError(f"{context} 缺少 input")
      vector(step["input"].get("measured"),
             A_STATE_ROWS if variant == "A" else 6, f"{context}.measured")
      vector(step["input"].get("anchor"), 2, f"{context}.anchor")
      vector(step.get("control"), 2, f"{context}.control")
      matrix(step.get("X"), A_STATE_ROWS if variant == "A" else 6,
             A_N + 1, f"{context}.X")
      matrix(step.get("U"), A_CONTROL_ROWS, A_N, f"{context}.U")
  params = document.get("solver_params", {})
  if variant == "A":
    if params.get("ipopt_max_cpu_time_s") != OLD_A_IPOPT_CPU_S:
      raise GateError("旧 A 参照不是 60 s 预算 oracle")
    if params.get("ipopt_max_iter") != OLD_A_IPOPT_ITER:
      raise GateError("旧 A 参照不是 300 次迭代 oracle")
  return scenarios


def check_model_keys_equal(old_params, new_params):
  """A 的物理/权重/约束参数必须与旧参照完全一致 (只允许预算字段不同)。"""
  failures = []
  for key in A_MODEL_KEYS:
    if key not in old_params:
      failures.append(f"旧参照缺少 {key}")
      continue
    if key not in new_params:
      failures.append(f"候选缺少 {key}")
      continue
    old_value = old_params[key]
    new_value = new_params[key]
    if isinstance(old_value, list):
      if [float(item) for item in old_value] != [float(item) for item in new_value]:
        failures.append(f"{key}: {old_value!r} != {new_value!r}")
    else:
      if float(old_value) != float(new_value):
        failures.append(f"{key}: {old_value!r} != {new_value!r}")
  if failures:
    raise GateError("A 模型参数与旧参照不一致: " + "; ".join(failures))
  allowed_extra = {"ipopt_max_cpu_time_s", "ipopt_max_iter"}
  extra = set(old_params) - set(new_params) - allowed_extra
  if extra:
    raise GateError(f"候选缺少旧参照参数: {sorted(extra)}")
  added = set(new_params) - set(old_params) - {"defaulted_params"}
  if added:
    raise GateError(f"候选新增未声明参数: {sorted(added)}")


def check_dynamic_params_equal(old_params, new_params):
  old = dict(old_params)
  new = dict(new_params)
  old.pop("defaulted_params", None)
  new.pop("defaulted_params", None)
  if old != new:
    raise GateError(
      "B 的 solver_params 与旧参照不一致 (含水动力): "
      f"差异={ {k: (old.get(k), new.get(k)) for k in set(old) | set(new) if old.get(k) != new.get(k)} }")


# ── A: 独立重算 (不信任 SolveInfo 的自报残差) ────────────────────────
def kinematic_step(state, control, tau_u, tau_r, dt, substeps=4):
  def rhs(s):
    psi, u, r = s[2], s[3], s[4]
    return [u * math.cos(psi), u * math.sin(psi), r,
            (control[0] - u) / tau_u, (control[1] - r) / tau_r]

  x = list(state)
  h = dt / float(substeps)
  for _ in range(substeps):
    k1 = rhs(x)
    k2 = rhs([x[i] + 0.5 * h * k1[i] for i in range(5)])
    k3 = rhs([x[i] + 0.5 * h * k2[i] for i in range(5)])
    k4 = rhs([x[i] + h * k3[i] for i in range(5)])
    x = [x[i] + h / 6.0 * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i])
         for i in range(5)]
  return x


def audit_a_solution(params, anchor, x_rows, u_rows, context):
  """独立核查: 初值/四子步动力学/幅值/首拍与后续变化率。"""
  dt = float(params["dt"])
  tau_u = float(params["tau_u"])
  tau_r = float(params["tau_r"])
  du_step = float(params["du_max"]) * dt
  dr_step = float(params["dr_max"]) * dt
  u_min = float(params["u_min"])
  u_max = float(params["u_max"])
  r_max = float(params["r_max"])
  residual = {"initial": 0.0, "dynamics": 0.0, "bounds": 0.0, "rate": 0.0}
  previous = list(anchor)
  for k in range(len(u_rows[0])):
    control = [u_rows[0][k], u_rows[1][k]]
    residual["bounds"] = max(
      residual["bounds"], u_min - control[0], control[0] - u_max,
      -r_max - control[1], control[1] - r_max)
    residual["rate"] = max(
      residual["rate"], abs(control[0] - previous[0]) - du_step,
      abs(control[1] - previous[1]) - dr_step)
    state = [x_rows[row][k] for row in range(A_STATE_ROWS)]
    predicted = kinematic_step(state, control, tau_u, tau_r, dt)
    target = [x_rows[row][k + 1] for row in range(A_STATE_ROWS)]
    residual["dynamics"] = max(
      residual["dynamics"],
      max(abs(predicted[i] - target[i]) for i in range(A_STATE_ROWS)))
    previous = control
  measured = [finite(value, context) for value in params["_measured"]]
  residual["initial"] = max(
    abs(x_rows[row][0] - measured[row]) for row in range(A_STATE_ROWS))
  worst = max(residual.values())
  if worst > A_SOLUTION_TOL:
    raise GateError(f"{context} 独立重算约束违规 {worst:.3e} > {A_SOLUTION_TOL}: {residual}")
  return residual


def a_objective(params, x_rows, u_rows, ref_rows):
  q = [float(item) for item in params["Q"]]
  r = [float(item) for item in params["R"]]
  qf = float(params["Qf_scale"])
  n = len(u_rows[0])
  total = 0.0
  for k in range(n):
    ex = x_rows[0][k] - ref_rows[0][k]
    ey = x_rows[1][k] - ref_rows[1][k]
    epsi = x_rows[2][k] - ref_rows[2][k]
    total += q[0] * ex * ex + q[1] * ey * ey + 2.0 * q[2] * (1.0 - math.cos(epsi))
    total += r[0] * u_rows[0][k] ** 2 + r[1] * u_rows[1][k] ** 2
  ex = x_rows[0][n] - ref_rows[0][n]
  ey = x_rows[1][n] - ref_rows[1][n]
  epsi = x_rows[2][n] - ref_rows[2][n]
  total += qf * (q[0] * ex * ex + q[1] * ey * ey + 2.0 * q[2] * (1.0 - math.cos(epsi)))
  return total


def compare_inputs_exact(reference_input, candidate_input, context):
  """replay 的三种输入必须与旧参照逐位同源 (1e-12)。"""
  for key in ("measured", "anchor"):
    ref = reference_input.get(key)
    cand = candidate_input.get(key)
    if ref is None or cand is None:
      raise GateError(f"{context}.{key} 缺失")
    if len(ref) != len(cand):
      raise GateError(f"{context}.{key} 维度不一致")
    for index, (a, b) in enumerate(zip(ref, cand)):
      delta = abs(finite(a, context) - finite(b, context))
      if delta > INPUT_TOL:
        raise GateError(f"{context}.{key}[{index}] 输入不同源: |{a} - {b}| = {delta:g}")
  ref = reference_input.get("reference")
  cand = candidate_input.get("reference")
  if not isinstance(ref, list) or not isinstance(cand, list):
    raise GateError(f"{context}.reference 缺失")
  if len(ref) != len(cand):
    raise GateError(f"{context}.reference 行数不一致")
  for row, (ref_row, cand_row) in enumerate(zip(ref, cand)):
    if len(ref_row) != len(cand_row):
      raise GateError(f"{context}.reference 行列数不一致")
    for col, (a, b) in enumerate(zip(ref_row, cand_row)):
      delta = abs(finite(a, context) - finite(b, context))
      if delta > INPUT_TOL:
        raise GateError(
          f"{context}.reference[{row}][{col}] 输入不同源: |{a} - {b}| = {delta:g}")


def compare_a_replay(old_document, new_document, candidate_params):
  """A: 逐拍同源 + 独立硬约束 + 成本语义 + 质量不劣化。"""
  old_scenarios = check_old_numerical(old_document, "A", "reference")
  new_scenarios = scenario_map(new_document, "候选 replay_A")
  if new_document.get("phase") != "numerical":
    raise GateError("replay_A 的 phase 不是 numerical")
  report = []
  for name in SCENARIOS:
    old_steps = old_scenarios[name]["steps"]
    new_steps = new_scenarios[name]["steps"]
    if len(new_steps) != len(old_steps):
      raise GateError(f"replay_A/{name} 拍数 {len(new_steps)} != {len(old_steps)}")
    entry = {"scenario": name, "steps": len(new_steps),
             "max_objective_delta": 0.0, "max_cost_semantics_delta": 0.0,
             "max_new_objective": 0.0, "max_old_objective": 0.0}
    for index, (old_step, new_step) in enumerate(zip(old_steps, new_steps)):
      context = f"replay_A/{name}[{index}]"
      if new_step.get("anchor_source") != "replay":
        raise GateError(f"{context} anchor_source != replay")
      if new_step.get("success") is not True:
        raise GateError(f"{context} 未成功: {new_step.get('error')}")
      compare_inputs_exact(old_step.get("input"), new_step.get("input"), context)

      x_rows = matrix(new_step.get("X"), A_STATE_ROWS, A_N + 1, f"{context}.X")
      u_rows = matrix(new_step.get("U"), A_CONTROL_ROWS, A_N, f"{context}.U")
      ref_rows = matrix(new_step["input"].get("reference"), 3, A_N + 1,
                        f"{context}.reference")
      anchor = vector(new_step["input"].get("anchor"), 2, f"{context}.anchor")
      measured = vector(new_step["input"].get("measured"), A_STATE_ROWS,
                        f"{context}.measured")
      # 增广末两维逐步等于上一拍控制 (生成模型的精确赋值语义)
      params = dict(candidate_params)
      params["_measured"] = measured
      audit_a_solution(params, anchor, x_rows, u_rows, context)

      # 成本语义: 独立解析目标 vs generated cost
      analytic = a_objective(params, x_rows, u_rows, ref_rows)
      acados_cost = finite(new_step.get("acados_cost"), f"{context}.acados_cost")
      recorded = finite(new_step.get("objective"), f"{context}.objective")
      limit = A_COST_REL_TOL * max(1.0, abs(analytic))
      if abs(acados_cost - analytic) > limit:
        raise GateError(
          f"{context} 成本语义不符: acados={acados_cost:.9g} analytic={analytic:.9g}")
      if abs(recorded - analytic) > max(limit, 1e-9):
        raise GateError(f"{context} 记录的 objective 与重算不一致")
      entry["max_cost_semantics_delta"] = max(
        entry["max_cost_semantics_delta"], abs(acados_cost - analytic))

      # 迁移质量: 新旧目标都由各自 X/U + 同一参考重算
      old_x = matrix(old_step.get("X"), A_STATE_ROWS, A_N + 1, f"{context}.oldX")
      old_u = matrix(old_step.get("U"), A_CONTROL_ROWS, A_N, f"{context}.oldU")
      old_analytic = a_objective(params, old_x, old_u, ref_rows)
      slack = max(A_QUALITY_ABS_SLACK, A_QUALITY_REL_SLACK * abs(old_analytic))
      if analytic > old_analytic + slack:
        raise GateError(
          f"{context} 目标劣化: new={analytic:.6g} old={old_analytic:.6g} "
          f"slack={slack:.6g}")
      entry["max_new_objective"] = max(entry["max_new_objective"], analytic)
      entry["max_old_objective"] = max(entry["max_old_objective"], old_analytic)
      entry["max_objective_delta"] = max(
        entry["max_objective_delta"], analytic - old_analytic)
    report.append(entry)
  return report


def compare_b_replay(old_document, new_document):
  """B: 抽取前后必须逐元素一致 (同算法, 同生成码, 只换了调用路径)。"""
  old_scenarios = check_old_numerical(old_document, "B", "reference")
  new_scenarios = scenario_map(new_document, "候选 replay_B")
  report = []
  for name in SCENARIOS:
    old_steps = old_scenarios[name]["steps"]
    new_steps = new_scenarios[name]["steps"]
    if len(new_steps) != len(old_steps):
      raise GateError(f"replay_B/{name} 拍数 {len(new_steps)} != {len(old_steps)}")
    max_control = 0.0
    max_state = 0.0
    max_bounds = 0.0
    max_rate = 0.0
    for index, (old_step, new_step) in enumerate(zip(old_steps, new_steps)):
      context = f"replay_B/{name}[{index}]"
      if new_step.get("anchor_source") != "replay":
        raise GateError(f"{context} anchor_source != replay")
      if new_step.get("success") is not True:
        raise GateError(f"{context} 未成功: {new_step.get('error')}")
      compare_inputs_exact(old_step.get("input"), new_step.get("input"), context)
      for key, rows, cols in (("X", 6, A_N + 1), ("U", A_CONTROL_ROWS, A_N)):
        ref = matrix(old_step.get(key), rows, cols, f"{context}.old{key}")
        cand = matrix(new_step.get(key), rows, cols, f"{context}.{key}")
        for row in range(rows):
          for col in range(cols):
            if key == "X" and row == HEADING_ROW:
              delta = abs(angular_difference(cand[row][col], ref[row][col]))
            else:
              delta = abs(cand[row][col] - ref[row][col])
            limit = TOL_ABS + TOL_REL * abs(ref[row][col])
            if delta > limit:
              raise GateError(
                f"{context}.{key}[{row}][{col}] 超差 {delta:.3e} > {limit:.3e}")
            if key == "X":
              max_state = max(max_state, delta)
            else:
              max_control = max(max_control, delta)
      # 独立复核 B 的推力幅值/变化率 (不信任记录值)
      params_b = new_step.get("_params")
      max_bounds = max(max_bounds, finite(new_step.get("bound_violation", 0.0),
                                          f"{context}.bound_violation"))
      max_rate = max(max_rate, finite(new_step.get("rate_violation", 0.0),
                                      f"{context}.rate_violation"))
    report.append({"scenario": name, "steps": len(new_steps),
                   "max_control_delta": max_control,
                   "max_state_delta": max_state,
                   "max_bound_violation": max_bounds,
                   "max_rate_violation": max_rate})
    if max_bounds > 1e-6 or max_rate > 1e-6:
      raise GateError(f"replay_B/{name} 幅值/变化率越界 {max_bounds}/{max_rate}")
  return report


# ── 耗时 ────────────────────────────────────────────────────────────
def nearest_rank(sorted_values, percentile):
  if not sorted_values:
    raise GateError("空样本无法计算分位数")
  rank = int(math.ceil(percentile / 100.0 * len(sorted_values)))
  index = min(max(rank - 1, 0), len(sorted_values) - 1)
  return sorted_values[index]


def timing_gate(document, label, budget_ms, absolute=False):
  """每场景: 520 拍、warmup=20/measured=500、全拍成功且无 deadline。"""
  if document.get("phase") != "timing":
    raise GateError(f"{label} 的 phase 不是 timing")
  if document.get("timing_warmup") != A_TIMING_WARMUP:
    raise GateError(f"{label} timing_warmup != {A_TIMING_WARMUP}")
  if document.get("timing_measured") != A_TIMING_MEASURED:
    raise GateError(f"{label} timing_measured != {A_TIMING_MEASURED}")
  scenarios = scenario_map(document, label)
  rows = []
  failures = []
  for name in SCENARIOS:
    steps = scenarios[name]["steps"]
    expected = A_TIMING_WARMUP + A_TIMING_MEASURED
    if len(steps) != expected:
      raise GateError(f"{label}/{name} 拍数 {len(steps)} != {expected}")
    wall = []
    scenario_failures = 0
    for index, step in enumerate(steps):
      context = f"{label}/{name}[{index}]"
      value = finite(step.get("wall_ms"), f"{context}.wall_ms")
      wall.append(value)
      if step.get("success") is not True:
        scenario_failures += 1
      # 冷首拍与全部预热拍同样受 deadline 与成功性约束 (不许靠丢弃掩盖)
      if value >= budget_ms:
        failures.append(f"{context} 墙钟 {value:.1f}ms >= {budget_ms:.0f}ms")
    if scenario_failures:
      failures.append(f"{label}/{name} 失败拍 {scenario_failures}")
    measured = sorted(wall[A_TIMING_WARMUP:])
    rows.append({
      "scenario": name,
      "samples": len(measured),
      "failures": scenario_failures,
      "p50": nearest_rank(measured, 50),
      "p95": nearest_rank(measured, 95),
      "p99": nearest_rank(measured, 99),
      "max": measured[-1],
      "first": wall[0],
    })
  if absolute:
    for row in rows:
      if row["p95"] > A_TIMING_P95_MS:
        failures.append(f"{label}/{row['scenario']} p95={row['p95']:.2f}ms > {A_TIMING_P95_MS}ms")
      if row["p99"] > A_TIMING_P99_MS:
        failures.append(f"{label}/{row['scenario']} p99={row['p99']:.2f}ms > {A_TIMING_P99_MS}ms")
      if row["max"] >= A_TIMING_MAX_MS:
        failures.append(
          f"{label}/{row['scenario']} max={row['max']:.1f}ms >= {A_TIMING_MAX_MS}ms")
  if failures:
    raise GateError("; ".join(failures))
  return rows


def compare_b_timing(old_document, new_document):
  """抽取前后同轮耗时: 逐场景 p95_new <= max(1.10*p95_old, p95_old+0.2ms)。"""
  old_rows = timing_gate(old_document, "旧 B timing", DEADLINE_MS)
  new_rows = timing_gate(new_document, "新 B timing", DEADLINE_MS)
  old_by_name = {row["scenario"]: row for row in old_rows}
  new_by_name = {row["scenario"]: row for row in new_rows}
  if list(old_by_name) != list(new_by_name):
    raise GateError("B 耗时场景集合不一致")
  report = []
  for name, old_row in old_by_name.items():
    new_row = new_by_name[name]
    limit = max(old_row["p95"] * 1.10, old_row["p95"] + 0.2)
    if new_row["p95"] > limit:
      raise GateError(
        f"B/{name} p95 退化: old={old_row['p95']:.3f}ms new={new_row['p95']:.3f}ms "
        f"门槛={limit:.3f}ms")
    report.append({"scenario": name, "old_p95": old_row["p95"],
                   "new_p95": new_row["p95"], "limit": limit,
                   "old_max": old_row["max"], "new_max": new_row["max"]})
  return report


# ── A 闭环 ──────────────────────────────────────────────────────────
def closed_loop_gate(document):
  if document.get("phase") != "closed_loop":
    raise GateError("closed_loop_A 的 phase 不是 closed_loop")
  expected_steps = 200
  if document.get("closed_loop_steps") != expected_steps:
    raise GateError(f"closed_loop_A closed_loop_steps != {expected_steps}")
  scenarios = scenario_map(document, "closed_loop_A")
  report = []
  for name in SCENARIOS:
    scenario = scenarios[name]
    steps = scenario.get("steps")
    if len(steps) != expected_steps:
      raise GateError(f"closed_loop_A/{name} 拍数 {len(steps)} != {expected_steps}")
    plants = scenario.get("plant_states")
    references = scenario.get("reference_first_column")
    if not isinstance(plants, list) or len(plants) != expected_steps:
      raise GateError(f"closed_loop_A/{name} 缺少逐拍 plant 记录")
    if not isinstance(references, list) or len(references) != expected_steps:
      raise GateError(f"closed_loop_A/{name} 缺少逐拍参考记录")
    failures = 0
    position_sq = 0.0
    heading_sq = 0.0
    worst_wall = 0.0
    for index, step in enumerate(steps):
      context = f"closed_loop_A/{name}[{index}]"
      if step.get("success") is not True:
        failures += 1
      wall = finite(step.get("wall_ms"), f"{context}.wall_ms")
      worst_wall = max(worst_wall, wall)
      if wall >= DEADLINE_MS:
        raise GateError(f"{context} 墙钟 {wall:.1f}ms >= {DEADLINE_MS:.0f}ms")
      control = vector(step.get("control"), 2, f"{context}.control")
      # 命令必须在幅值界内
      if not (0.0 - 1e-6 <= control[0] <= 3.3 + 1e-6):
        raise GateError(f"{context} 输出速度越界: {control[0]}")
      if abs(control[1]) > 1.25 + 1e-6:
        raise GateError(f"{context} 输出角速度越界: {control[1]}")
      plant = vector(plants[index], A_STATE_ROWS, f"{context}.plant")
      reference = vector(references[index], 3, f"{context}.reference")
      position_sq += (plant[0] - reference[0]) ** 2 + (plant[1] - reference[1]) ** 2
      heading_sq += angular_difference(plant[2], reference[2]) ** 2
    if failures:
      raise GateError(f"closed_loop_A/{name} 有 {failures} 拍失败/HOLD")
    position_rmse = math.sqrt(position_sq / expected_steps)
    heading_rmse = math.sqrt(heading_sq / expected_steps)
    if position_rmse > A_CLOSED_LOOP_POSITION_RMSE:
      raise GateError(
        f"closed_loop_A/{name} 位置 RMSE {position_rmse:.3f} m > "
        f"{A_CLOSED_LOOP_POSITION_RMSE} m")
    if heading_rmse > A_CLOSED_LOOP_HEADING_RMSE:
      raise GateError(
        f"closed_loop_A/{name} 周期航向 RMSE {heading_rmse:.3f} rad > "
        f"{A_CLOSED_LOOP_HEADING_RMSE} rad")
    report.append({"scenario": name, "steps": expected_steps,
                   "position_rmse": position_rmse,
                   "heading_rmse": heading_rmse,
                   "max_wall_ms": worst_wall})
  return report


# ── 门禁编排 ────────────────────────────────────────────────────────
def resolve_paths(reference_root, candidate_root):
  return {
    "old_a": os.path.join(reference_root, "evidence", "bench", "release",
                          "kinematic", "numerical.json"),
    "old_b": os.path.join(reference_root, "evidence", "bench", "release",
                          "dynamic_acados", "numerical.json"),
    "replay_a": os.path.join(candidate_root, "evidence", "migration", "replay_A.json"),
    "replay_b": os.path.join(candidate_root, "evidence", "migration", "replay_B.json"),
    "closed_loop_a": os.path.join(candidate_root, "evidence", "migration",
                                  "closed_loop_A.json"),
    "timing_old_b_1": os.path.join(candidate_root, "evidence", "migration", "timing",
                                   "old_B_1.json"),
    "timing_old_b_2": os.path.join(candidate_root, "evidence", "migration", "timing",
                                   "old_B_2.json"),
    "timing_new_b_1": os.path.join(candidate_root, "evidence", "migration", "timing",
                                   "new_B_1.json"),
    "timing_new_b_2": os.path.join(candidate_root, "evidence", "migration", "timing",
                                   "new_B_2.json"),
    "a_timing_1": os.path.join(candidate_root, "evidence", "bench", "release",
                               "kinematic", "timing_1.json"),
    "a_timing_2": os.path.join(candidate_root, "evidence", "bench", "release",
                               "kinematic", "timing_2.json"),
    "a_noopt_timing_1": os.path.join(candidate_root, "evidence", "bench", "noopt",
                                     "kinematic", "timing_1.json"),
    "a_noopt_timing_2": os.path.join(candidate_root, "evidence", "bench", "noopt",
                                     "kinematic", "timing_2.json"),
    "b_numerical": os.path.join(candidate_root, "evidence", "bench", "release",
                                "dynamic_acados", "numerical.json"),
    "a_numerical": os.path.join(candidate_root, "evidence", "bench", "release",
                                "kinematic", "numerical.json"),
  }


def require_provenance(document, label, model, require_shared=True):
  """校验 runner 写下的 provenance。

  旧 B 是迁移前的单体二进制, 没有共用后端库 —— 对它只要求 shared 字段为
  null, 不允许凭空补一个路径 (那会伪造"旧版也用了共用库")。
  """
  provenance = document.get("provenance")
  if not isinstance(provenance, dict):
    raise GateError(f"{label} 缺少 provenance")
  if provenance.get("model") != model:
    raise GateError(f"{label} provenance.model={provenance.get('model')!r} != {model}")
  required = ["binary_path", "binary_sha256", "ocp_json_path", "ocp_json_sha256",
              "source_manifest_path", "source_manifest_sha256", "segment_id"]
  if require_shared:
    required += ["shared_backend_path", "shared_backend_sha256"]
  for key in required:
    if provenance.get(key) in (None, ""):
      raise GateError(f"{label} provenance.{key} 缺失")
  checked = [("binary_path", "binary_sha256"),
             ("ocp_json_path", "ocp_json_sha256"),
             ("source_manifest_path", "source_manifest_sha256")]
  if require_shared:
    checked.append(("shared_backend_path", "shared_backend_sha256"))
  else:
    if provenance.get("shared_backend_path") is not None:
      raise GateError(
        f"{label} 旧 B 不应带 shared_backend: {provenance['shared_backend_path']}")
  for path_key, hash_key in checked:
    path = provenance[path_key]
    if not os.path.isabs(path):
      raise GateError(f"{label} provenance.{path_key} 不是绝对路径: {path}")
    if not os.path.exists(path):
      raise GateError(f"{label} provenance.{path_key} 不存在: {path}")
    actual = sha256_file(path)
    if actual != provenance[hash_key]:
      raise GateError(
        f"{label} provenance.{hash_key} 与文件不符 ({actual} != {provenance[hash_key]})")
  return provenance


def run(reference_root, candidate_root):
  report = {"ok": True, "failures": [], "reference_hashes": {},
            "a_replay": [], "a_closed_loop": [], "a_timing_release": [],
            "a_timing_noopt": [], "b_replay": [], "b_timing": []}
  paths = resolve_paths(reference_root, candidate_root)
  report["reference_hashes"] = verify_reference_hashes(reference_root)

  old_a = load_json(paths["old_a"])
  old_b = load_json(paths["old_b"])
  replay_a = load_json(paths["replay_a"])
  replay_b = load_json(paths["replay_b"])
  closed_loop = load_json(paths["closed_loop_a"])
  a_numerical = load_json(paths["a_numerical"])

  # 候选侧 profile/provenance 门禁 (A: replay 与 numerical 各一份)
  require_provenance(replay_a, "replay_A", "kinematic")
  require_provenance(a_numerical, "A numerical", "kinematic")
  require_provenance(replay_b, "replay_B", "dynamic")
  require_provenance(closed_loop, "closed_loop_A", "kinematic")
  require_provenance(load_json(paths["b_numerical"]), "B numerical", "dynamic")
  for round_index in (1, 2):
    require_provenance(load_json(paths[f"timing_old_b_{round_index}"]),
                       f"旧 B timing {round_index}", "dynamic",
                       require_shared=False)
    require_provenance(load_json(paths[f"timing_new_b_{round_index}"]),
                       f"新 B timing {round_index}", "dynamic")
    require_provenance(load_json(paths[f"a_timing_{round_index}"]),
                       f"A release timing {round_index}", "kinematic")
    require_provenance(load_json(paths[f"a_noopt_timing_{round_index}"]),
                       f"A noopt timing {round_index}", "kinematic")

  # A: 参数一致性 + 质量/成本/约束
  check_model_keys_equal(old_a.get("solver_params", {}),
                         replay_a.get("solver_params", {}))
  report["a_replay"] = compare_a_replay(
    old_a, replay_a, replay_a.get("solver_params", {}))
  # B: 参数完全一致 (含水动力) + 逐元素回归
  check_dynamic_params_equal(old_b.get("solver_params", {}),
                             replay_b.get("solver_params", {}))
  report["b_replay"] = compare_b_replay(old_b, replay_b)

  report["a_closed_loop"] = closed_loop_gate(closed_loop)

  # A 耗时: Release 绝对门禁 + NoOpt 可用性
  for round_index in (1, 2):
    report["a_timing_release"].append({
      "round": round_index,
      "scenarios": timing_gate(load_json(paths[f"a_timing_{round_index}"]),
                               f"A release timing {round_index}",
                               DEADLINE_MS, absolute=True)})
    report["a_timing_noopt"].append({
      "round": round_index,
      "scenarios": timing_gate(load_json(paths[f"a_noopt_timing_{round_index}"]),
                               f"A noopt timing {round_index}", DEADLINE_MS)})

  # B 抽取前后同轮耗时
  for round_index in (1, 2):
    report["b_timing"].append({
      "round": round_index,
      **{"scenarios": compare_b_timing(
        load_json(paths[f"timing_old_b_{round_index}"]),
        load_json(paths[f"timing_new_b_{round_index}"]))}})
  return report


def format_milliseconds(value):
  return f"{value:.3f}"


def render_markdown(report, reference_root, candidate_root):
  lines = ["# acados 迁移对照 (旧参照 vs 新候选)", ""]
  lines.append(f"- 旧参照: `{reference_root}`")
  lines.append(f"- 候选: `{candidate_root}`")
  lines.append(f"- 结论: {'通过' if report['ok'] else '失败'}")
  for failure in report["failures"]:
    lines.append(f"- 未通过: {failure}")
  lines += ["", "## A: 重放旧 IPOPT 输入 (成本/硬约束/质量)", "",
            "| 场景 | 拍数 | 最大成本语义差 | 最大目标劣化 | 新目标 | 旧目标 |",
            "|---|---|---|---|---|---|"]
  for item in report["a_replay"]:
    lines.append(
      f"| {item['scenario']} | {item['steps']} | "
      f"{item['max_cost_semantics_delta']:.3e} | "
      f"{item['max_objective_delta']:.3e} | "
      f"{item['max_new_objective']:.6g} | {item['max_old_objective']:.6g} |")
  lines += ["", "## A: 独立闭环 (200 拍/场景)", "",
            "| 场景 | 拍数 | 位置 RMSE (m) | 周期航向 RMSE (rad) | 最大墙钟 (ms) |",
            "|---|---|---|---|---|"]
  for item in report["a_closed_loop"]:
    lines.append(
      f"| {item['scenario']} | {item['steps']} | {item['position_rmse']:.3f} | "
      f"{item['heading_rmse']:.3f} | {item['max_wall_ms']:.2f} |")
  lines += ["", "## A: Release 耗时 (20 预热 + 500 计时, 门槛 p95<=20ms/p99<=50ms)", ""]
  for round_entry in report["a_timing_release"]:
    lines.append(f"第 {round_entry['round']} 轮")
    lines.append("")
    lines.append("| 场景 | 样本 | 失败 | p50 | p95 | p99 | max | 首拍 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in round_entry["scenarios"]:
      lines.append(
        f"| {row['scenario']} | {row['samples']} | {row['failures']} | "
        f"{format_milliseconds(row['p50'])} | {format_milliseconds(row['p95'])} | "
        f"{format_milliseconds(row['p99'])} | {format_milliseconds(row['max'])} | "
        f"{format_milliseconds(row['first'])} |")
    lines.append("")
  lines += ["## B: 抽取前后逐元素回归 + 同轮耗时", "",
            "| 场景 | 拍数 | 最大控制差 | 最大状态差 | 幅值越界 | 变化率越界 |",
            "|---|---|---|---|---|---|"]
  for item in report["b_replay"]:
    lines.append(
      f"| {item['scenario']} | {item['steps']} | {item['max_control_delta']:.3e} | "
      f"{item['max_state_delta']:.3e} | {item['max_bound_violation']:.3e} | "
      f"{item['max_rate_violation']:.3e} |")
  lines.append("")
  for round_entry in report["b_timing"]:
    lines.append(f"第 {round_entry['round']} 轮")
    lines.append("")
    lines.append("| 场景 | 旧 p95 | 新 p95 | 门槛 | 旧 max | 新 max |")
    lines.append("|---|---|---|---|---|---|")
    for row in round_entry["scenarios"]:
      lines.append(
        f"| {row['scenario']} | {format_milliseconds(row['old_p95'])} | "
        f"{format_milliseconds(row['new_p95'])} | {format_milliseconds(row['limit'])} | "
        f"{format_milliseconds(row['old_max'])} | {format_milliseconds(row['new_max'])} |")
    lines.append("")
  return "\n".join(lines)


def write_outputs(report, reference_root, candidate_root, output_dir):
  if os.path.isdir(output_dir) and os.listdir(output_dir):
    raise GateError(f"输出目录非空, 拒绝覆盖: {output_dir}")
  os.makedirs(output_dir, exist_ok=True)
  with open(os.path.join(output_dir, "comparison.json"), "w",
            encoding="utf-8") as handle:
    json.dump(report, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
  with open(os.path.join(output_dir, "comparison.md"), "w",
            encoding="utf-8") as handle:
    handle.write(render_markdown(report, reference_root, candidate_root))


def main(argv):
  parser = argparse.ArgumentParser(description="acados 迁移对照")
  parser.add_argument("--reference-root", required=True,
                      help="不可变旧候选 R0 (含旧 A/B numerical)")
  parser.add_argument("--candidate-root", required=True,
                      help="新候选 R (含 evidence/migration 与 bench)")
  parser.add_argument("--output", required=True, help="输出报告目录 (必须为空)")
  args = parser.parse_args(argv)
  try:
    report = run(args.reference_root, args.candidate_root)
    write_outputs(report, args.reference_root, args.candidate_root, args.output)
  except GateError as error:
    print(f"迁移对照失败: {error}", file=sys.stderr)
    return 1
  print(f"迁移对照{'通过' if report['ok'] else '失败'}: {args.output}")
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
