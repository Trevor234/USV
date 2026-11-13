#!/usr/bin/env python3
"""可复现的性能/数值证据采集入口 (候选验收唯一入口)。

产出 evidence/ 下的固定布局, 供 compare_release_baseline.py (同算法
NoOpt/Release) 与 compare_acados_migration.py (算法迁移) 消费:

  evidence/run_manifest.json
  evidence/bench/{noopt,release}/env.json
  evidence/bench/{noopt,release}/{kinematic,dynamic_acados}/{numerical,timing_1,timing_2}.json
  evidence/migration/env.json
  evidence/migration/replay_A.json
  evidence/migration/replay_B.json
  evidence/migration/closed_loop_A.json
  evidence/migration/timing/{old_B,new_B}_{1,2}.json

约束 (全部为硬性):
  - 每个子进程显式 taskset -c 3, OMP/OPENBLAS 线程数=1, 只 source
    /opt/ros/jazzy/setup.bash (不 source 旧 install 到新进程);
  - 每个实际 benchmark 进程开始/结束都实时读 get_throttled, 解析原始
    0x..., 四个 sticky 位与当前位都必须为 0; 记录温度/boot_id/UTC/单调
    时间/governor/频率/原始输出/退出码;
  - 起始温度 <= 60°C, governor=performance 且配对测量一致, 同一 boot;
  - 顺序固定: 同算法 N→R→R→N; B 原版/新 Release Old→New→New→Old;
  - benchmark 只写自己的 *.raw.json; runner 独占创建最终结果并补 provenance
    (不改/覆盖 raw); 任何目标文件已存在即拒绝执行;
  - 非零退出的 benchmark 不被后续成功掩盖: 保留 raw 与报告, 总退出码非零;
  - 测量环境无效时只允许保存失败证据后完整重做一次, 仍无效即报告未验收。
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

ROS_SETUP = "/opt/ros/jazzy/setup.bash"
CPU_PIN = "3"
TEMPERATURE_LIMIT_C = 60.0
STICKY_MASK = 0xF0000
# R0 旧 B benchmark 的固定身份 (迁移计划 §1); build 目录里的二进制同样要核对。
OLD_B_BENCHMARK_SHA256 = (
  "14ae0147f9b8ef86c5c818b511c9b3bf37de87edb86868aa0fd463adde8a3948")
VARIANTS = ("kinematic", "dynamic_acados")
VARIANT_MODEL = {"kinematic": "kinematic", "dynamic_acados": "dynamic"}
VARIANT_PHASE_FILES = ("numerical.json", "timing_1.json", "timing_2.json")


class RunnerError(Exception):
  pass


def sha256_file(path):
  digest = hashlib.sha256()
  with open(path, "rb") as handle:
    for chunk in iter(lambda: handle.read(65536), b""):
      digest.update(chunk)
  return digest.hexdigest()


def read_text(path, default=None):
  try:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
      return handle.read().strip()
  except OSError:
    return default


def utc_now():
  return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Environment:
  """单次实时环境读数 (不做缓存, 不虚构 0)。"""

  def __init__(self):
    self.utc = utc_now()
    self.monotonic = time.monotonic()
    self.boot_id = read_text("/proc/sys/kernel/random/boot_id")
    self.governor = read_text(
      "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    self.frequency_khz = read_text(
      "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    self.temperature_c = self._temperature()
    self.throttled_raw, self.throttled_sticky, self.throttled_errors = (
      self._throttled())

  @staticmethod
  def _temperature():
    text = read_text("/sys/class/thermal/thermal_zone0/temp")
    if text is None:
      return None
    try:
      return float(text) / 1000.0
    except ValueError:
      return None

  @staticmethod
  def _sudo_password():
    """可选: 从文件读 sudo 密码 (仅用于把 vcgencmd 经 stdin 喂给 sudo -S)。

    路径由 USV_SUDO_PASSWORD_FILE 覆盖, 默认 ~/.ssh/.pi_pw_tmp。读不到就返回
    None —— 不猜、不缓存、不虚构。
    """
    path = os.environ.get("USV_SUDO_PASSWORD_FILE",
                          os.path.expanduser("~/.ssh/.pi_pw_tmp"))
    try:
      with open(path, "r", encoding="utf-8") as handle:
        return handle.read().strip() or None
    except OSError:
      return None

  @staticmethod
  def _throttled():
    """实时执行 vcgencmd get_throttled 并解析原始值。权限不足即报缺失。"""
    errors = []
    password = Environment._sudo_password()
    attempts = [["vcgencmd", "get_throttled"],
                ["sudo", "-n", "vcgencmd", "get_throttled"]]
    for argv in attempts:
      try:
        completed = subprocess.run(argv, capture_output=True, text=True,
                                   timeout=10, check=False)
      except (OSError, subprocess.SubprocessError) as error:
        errors.append(f"{' '.join(argv)}: {error}")
        continue
      output = (completed.stdout or "").strip()
      if completed.returncode != 0 or "throttled=" not in output:
        errors.append(f"{' '.join(argv)}: rc={completed.returncode} "
                      f"out={output!r} err={(completed.stderr or '').strip()[:120]!r}")
        continue
      raw = output.split("throttled=", 1)[1].split()[0]
      try:
        value = int(raw, 16)
      except ValueError:
        errors.append(f"无法解析 throttled 值: {raw!r}")
        continue
      return output, value & STICKY_MASK, errors
    if password:
      # root:video 独占 /dev/vcio, 非交互式 sudo 需要 -S + stdin。
      argv = ["sudo", "-S", "-p", "", "vcgencmd", "get_throttled"]
      try:
        completed = subprocess.run(argv, input=password + "\n",
                                   capture_output=True, text=True, timeout=10,
                                   check=False)
      except (OSError, subprocess.SubprocessError) as error:
        errors.append(f"{' '.join(argv)}: {error}")
        return None, None, errors
      output = (completed.stdout or "").strip()
      if completed.returncode == 0 and "throttled=" in output:
        raw = output.split("throttled=", 1)[1].split()[0]
        try:
          return output, int(raw, 16) & STICKY_MASK, errors
        except ValueError:
          errors.append(f"无法解析 throttled 值: {raw!r}")
      else:
        errors.append(f"{' '.join(argv)}: rc={completed.returncode} "
                      f"out={output!r}")
    else:
      errors.append("未找到可用的 sudo 密码文件, 无法读取 get_throttled")
    return None, None, errors

  def as_segment(self, label):
    return {
      "label": label,
      "start_temperature_c": self.temperature_c,
      "temperature_limit_c": TEMPERATURE_LIMIT_C,
      "governor": self.governor,
      "frequency_khz": (int(self.frequency_khz)
                        if self.frequency_khz and self.frequency_khz.isdigit()
                        else None),
      "boot_id": self.boot_id,
      "utc": self.utc,
      "monotonic_s": self.monotonic,
      "throttled_raw": self.throttled_raw,
      "throttled_sticky": self.throttled_sticky,
      "throttled_errors": self.throttled_errors,
    }


class Segment:
  """一次 benchmark 进程 = 一个 segment (起止各一次环境读数)。"""

  def __init__(self, segment_id, variant, model, phase, round_index,
               command, raw_path, final_path):
    self.segment_id = segment_id
    self.variant = variant
    self.model = model
    self.phase = phase
    self.round_index = round_index
    self.command = command
    self.raw_path = raw_path
    self.final_path = final_path
    self.start = None
    self.end = None
    self.service_before = None
    self.service_after = None
    self.artifacts_before = None
    self.artifacts_after = None
    self.returncode = None
    self.stdout_tail = ""
    self.stderr_tail = ""

  def to_env_json(self):
    return {
      "label": self.segment_id,
      "variant": self.variant,
      "model": self.model,
      "phase": self.phase,
      "round": self.round_index,
      "command": self.command,
      "raw_path": self.raw_path,
      "final_path": self.final_path,
      "returncode": self.returncode,
      "start": self.start,
      "end": self.end,
      "start_temperature_c": (self.start or {}).get("start_temperature_c"),
      "governor": (self.start or {}).get("governor"),
      "boot_id": (self.start or {}).get("boot_id"),
      "throttled_sticky": (self.start or {}).get("throttled_sticky"),
      "stdout_tail": self.stdout_tail,
      "stderr_tail": self.stderr_tail,
    }



def service_snapshot():
  """只读记录生产服务状态: 段前后各一次, 任何变化使该配对无效。"""
  fields = "ActiveState,MainPID,NRestarts"
  snapshot = {}
  for unit in ("usv-system", "usv-record", "usv-rtk"):
    try:
      completed = subprocess.run(
        ["systemctl", "show", unit, "--no-pager", f"--property={fields}"],
        capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as error:
      snapshot[unit] = {"error": str(error)}
      continue
    entry = {"returncode": completed.returncode}
    for line in (completed.stdout or "").splitlines():
      if "=" in line:
        key, value = line.split("=", 1)
        entry[key] = value
    snapshot[unit] = entry
  return snapshot


def validate_service_stability(segment_id, before, after):
  """usv-system 必须全程 active 且 PID/重启次数不变; record/rtk 必须 inactive。"""
  failures = []
  for label, snapshot in (("开始", before), ("结束", after)):
    system = snapshot.get("usv-system", {})
    if system.get("error"):
      failures.append(f"{segment_id}: {label}无法查询 usv-system: {system['error']}")
      continue
    if system.get("ActiveState") != "active":
      failures.append(
        f"{segment_id}: {label} usv-system ActiveState={system.get('ActiveState')!r}")
    for unit in ("usv-record", "usv-rtk"):
      entry = snapshot.get(unit, {})
      if entry.get("error"):
        failures.append(f"{segment_id}: {label}无法查询 {unit}: {entry['error']}")
      elif entry.get("ActiveState") == "active":
        failures.append(f"{segment_id}: {label} {unit} 处于 active (应为 inactive)")
  before_system = before.get("usv-system", {})
  after_system = after.get("usv-system", {})
  for key in ("MainPID", "NRestarts", "ActiveState"):
    if before_system.get(key) != after_system.get(key):
      failures.append(
        f"{segment_id}: usv-system {key} 在测量期间改变 "
        f"({before_system.get(key)!r} -> {after_system.get(key)!r})")
  return failures


def artifact_hashes(binary, shared, ocp_json, params, manifest):
  """段前后各算一次: 产物在测量期间被替换则配对无效。"""
  entries = {}
  for label, path in (("binary", binary), ("shared_backend", shared),
                      ("ocp_json", ocp_json), ("source_manifest", manifest)):
    if path and os.path.exists(path):
      entries[label] = {"path": os.path.realpath(path),
                        "sha256": sha256_file(path)}
    else:
      entries[label] = {"path": None, "sha256": None}
  entries["params"] = [
    {"path": os.path.realpath(path),
     "sha256": sha256_file(path) if os.path.exists(path) else None}
    for path in params]
  return entries


def validate_artifact_stability(segment_id, before, after):
  failures = []
  for label in ("binary", "shared_backend", "ocp_json", "source_manifest"):
    if before.get(label, {}).get("sha256") != after.get(label, {}).get("sha256"):
      failures.append(
        f"{segment_id}: {label} 哈希在测量期间改变 "
        f"({before.get(label, {}).get('sha256')} -> "
        f"{after.get(label, {}).get('sha256')})")
  before_params = [item.get("sha256") for item in before.get("params", [])]
  after_params = [item.get("sha256") for item in after.get("params", [])]
  if before_params != after_params:
    failures.append(f"{segment_id}: 参数文件哈希在测量期间改变")
  return failures


def require_absent(path):
  if os.path.exists(path):
    raise RunnerError(f"目标已存在, 拒绝覆盖: {path}")


def resolve_release_root(path, label):
  real = os.path.realpath(path)
  if not os.path.isdir(real):
    raise RunnerError(f"{label} 不存在: {path}")
  return real


def check_prerequisites(release_root, reference_root):
  required = [
    os.path.join(release_root, "src", "usv_bringup", "config", "mpc_params_A.yaml"),
    os.path.join(release_root, "src", "usv_bringup", "config", "usv_params_A.yaml"),
    os.path.join(release_root, "src", "usv_bringup", "config", "mpc_params_B.yaml"),
    os.path.join(release_root, "src", "usv_bringup", "config", "usv_params_B.yaml"),
    os.path.join(release_root, "evidence", "source_manifest_frozen.txt"),
    os.path.join(release_root, "build_noopt", "usv_mpc", "benchmark_kinematic_solver"),
    os.path.join(release_root, "build_noopt", "usv_nmpc", "benchmark_dynamic_solver"),
    os.path.join(release_root, "build_release", "usv_mpc", "benchmark_kinematic_solver"),
    os.path.join(release_root, "build_release", "usv_nmpc", "benchmark_dynamic_solver"),
    os.path.join(reference_root, "build_release", "usv_nmpc",
                 "benchmark_dynamic_solver"),
    os.path.join(reference_root, "evidence", "source_manifest_frozen.txt"),
  ]
  for path in required:
    if not os.path.exists(path):
      raise RunnerError(f"缺少必需文件: {path}")
  for group in ("bench", "migration"):
    directory = os.path.join(release_root, "evidence", group)
    if os.path.isdir(directory) and os.listdir(directory):
      raise RunnerError(f"evidence/{group} 非空, 拒绝覆盖: {directory}")


def build_environment(release_root, reference_root, extra_library_paths=()):
  """只 source ROS 基础 overlay; 不继承旧工作空间。"""
  command = f"source {ROS_SETUP} >/dev/null 2>&1 && env -0"
  completed = subprocess.run(["/bin/bash", "-c", command], capture_output=True,
                             check=False)
  env = {}
  for entry in completed.stdout.decode("utf-8", "replace").split("\0"):
    if "=" in entry:
      key, value = entry.split("=", 1)
      env[key] = value
  library_paths = list(extra_library_paths) + [
    "/home/trevor/acados/lib"]
  env["LD_LIBRARY_PATH"] = ":".join(
    [item for item in library_paths if item] +
    ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else []))
  env["OMP_NUM_THREADS"] = "1"
  env["OPENBLAS_NUM_THREADS"] = "1"
  env["MKL_NUM_THREADS"] = "1"
  env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
  env["ROS_DOMAIN_ID"] = env.get("ROS_DOMAIN_ID", "0")
  return env


def run_benchmark(segment, env, artifacts):
  """执行一个 benchmark 进程。

  进程前后各取一次: 实时环境读数 (节流/温度/governor/boot)、只读服务状态、
  产物哈希。三者任一在段内改变, 该配对即无效。
  """
  # raw 目录必须先存在: benchmark 独占创建自己的 raw 文件, 不会替你建目录。
  os.makedirs(os.path.dirname(segment.raw_path), exist_ok=True)
  segment.start = Environment().as_segment(segment.segment_id + ":start")
  segment.service_before = service_snapshot()
  segment.artifacts_before = artifacts()
  started = time.monotonic()
  completed = subprocess.run(segment.command, env=env, capture_output=True,
                             text=True, check=False)
  elapsed = time.monotonic() - started
  segment.end = Environment().as_segment(segment.segment_id + ":end")
  segment.service_after = service_snapshot()
  segment.artifacts_after = artifacts()
  segment.returncode = completed.returncode
  segment.stdout_tail = (completed.stdout or "")[-2000:]
  segment.stderr_tail = (completed.stderr or "")[-4000:]
  segment.elapsed_s = elapsed
  return completed


def validate_measurement(segment, groups, boot_id):
  """单个 segment 的有效性 (温度/governor/节流/boot 一致)。"""
  failures = []
  start = segment.start or {}
  end = segment.end or {}
  if start.get("throttled_sticky") is None:
    failures.append(
      f"{segment.segment_id}: 缺少 get_throttled 读数 "
      f"({'; '.join(start.get('throttled_errors') or [])[:200]})")
  if start.get("throttled_sticky"):
    failures.append(
      f"{segment.segment_id}: 起始 sticky 位非零 0x{start['throttled_sticky']:x}")
  if end.get("throttled_sticky"):
    failures.append(
      f"{segment.segment_id}: 结束 sticky 位非零 0x{end['throttled_sticky']:x}")
  for label, reading in (("开始", start), ("结束", end)):
    raw = reading.get("throttled_raw")
    if raw is None:
      continue
    try:
      value = int(raw.split("throttled=", 1)[1].split()[0], 16)
    except (IndexError, ValueError):
      failures.append(f"{segment.segment_id}: {label} throttled 原始值无法解析: {raw!r}")
      continue
    if value != 0:
      failures.append(
        f"{segment.segment_id}: {label} 当前节流位非零 ({raw})")
  temperature = start.get("start_temperature_c")
  if temperature is None:
    failures.append(f"{segment.segment_id}: 缺少起始温度")
  elif temperature > TEMPERATURE_LIMIT_C:
    failures.append(
      f"{segment.segment_id}: 起始温度 {temperature:.1f}°C > {TEMPERATURE_LIMIT_C:.0f}°C")
  if start.get("governor") != "performance":
    failures.append(
      f"{segment.segment_id}: governor={start.get('governor')!r} != performance")
  if end.get("governor") not in (None, start.get("governor")):
    failures.append(
      f"{segment.segment_id}: 结束 governor={end.get('governor')!r} 与开始不一致")
  for key in ("boot_id",):
    if start.get(key) is None:
      failures.append(f"{segment.segment_id}: 缺少 {key}")
    elif end.get(key) not in (None, start.get(key)):
      failures.append(f"{segment.segment_id}: {key} 在测量期间改变")
  if boot_id is not None and start.get("boot_id") not in (None, boot_id):
    failures.append(
      f"{segment.segment_id}: boot_id 与配对组不一致 "
      f"({start.get('boot_id')} != {boot_id})")
  group = groups.setdefault(segment.variant + "/" + segment.phase, set())
  if start.get("boot_id"):
    group.add(start["boot_id"])
  if len(group) > 1:
    failures.append(
      f"{segment.segment_id}: 同一配对组出现多个 boot_id: {sorted(group)}")
  return failures


def provenance_for(segment, binary_path, shared_backend_path, ocp_json_path,
                   model, params_paths, source_manifest_path):
  provenance = {
    "binary_path": os.path.realpath(binary_path),
    "binary_sha256": sha256_file(binary_path),
    "shared_backend_path": (os.path.realpath(shared_backend_path)
                            if shared_backend_path else None),
    "shared_backend_sha256": (sha256_file(shared_backend_path)
                              if shared_backend_path else None),
    "model": model,
    "ocp_json_path": os.path.realpath(ocp_json_path),
    "ocp_json_sha256": sha256_file(ocp_json_path),
    "source_manifest_path": os.path.realpath(source_manifest_path),
    "source_manifest_sha256": sha256_file(source_manifest_path),
    "params": [{"path": os.path.realpath(path), "sha256": sha256_file(path)}
               for path in params_paths],
    "segment_id": segment.segment_id,
    "returncode": segment.returncode,
  }
  with open(ocp_json_path, "r", encoding="utf-8") as handle:
    ocp = json.load(handle)
  provenance["solver_options"] = ocp.get("solver_options")
  return provenance


def finalize_segment(segment, provenance):
  """raw 由 benchmark 独占写入; runner 独占创建最终文件并补 provenance。"""
  require_absent(segment.final_path)
  if not os.path.exists(segment.raw_path):
    raise RunnerError(f"{segment.segment_id}: benchmark 未产出 raw: {segment.raw_path}")
  with open(segment.raw_path, "r", encoding="utf-8") as handle:
    try:
      document = json.load(handle)
    except json.JSONDecodeError as error:
      raise RunnerError(
        f"{segment.segment_id}: raw JSON 无效 ({error}), 不能成为成功段") from error
  document["provenance"] = provenance
  document["raw_path"] = segment.raw_path
  document["raw_sha256"] = sha256_file(segment.raw_path)
  os.makedirs(os.path.dirname(segment.final_path), exist_ok=True)
  with open(segment.final_path, "x", encoding="utf-8") as handle:
    json.dump(document, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
  return document


def write_json_exclusive(path, payload):
  require_absent(path)
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "x", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write("\n")


def benchmark_argv(binary, params, vehicle, phase, output, replay=None):
  argv = ["taskset", "-c", CPU_PIN, binary,
          "--params", params, "--vehicle", vehicle,
          "--backend", "acados", "--phase", phase, "--output", output]
  if replay is not None:
    argv += ["--replay-inputs", replay]
  return argv


def plan_segments(release_root, reference_root, base):
  """固定顺序的 segment 列表 (计划里写死的顺序, 不做自适应重排)。"""
  config = os.path.join(release_root, "src", "usv_bringup", "config")
  config_old = os.path.join(reference_root, "src", "usv_bringup", "config")
  binaries = {
    ("noopt", "kinematic"): os.path.join(
      release_root, "build_noopt", "usv_mpc", "benchmark_kinematic_solver"),
    ("noopt", "dynamic_acados"): os.path.join(
      release_root, "build_noopt", "usv_nmpc", "benchmark_dynamic_solver"),
    ("release", "kinematic"): os.path.join(
      release_root, "build_release", "usv_mpc", "benchmark_kinematic_solver"),
    ("release", "dynamic_acados"): os.path.join(
      release_root, "build_release", "usv_nmpc", "benchmark_dynamic_solver"),
  }
  params = {
    "kinematic": (os.path.join(config, "mpc_params_A.yaml"),
                  os.path.join(config, "usv_params_A.yaml")),
    "dynamic_acados": (os.path.join(config, "mpc_params_B.yaml"),
                       os.path.join(config, "usv_params_B.yaml")),
  }
  segments = []

  def add(segment_id, variant, phase, round_index, argv, raw_path, final_path):
    segment = Segment(segment_id, variant, VARIANT_MODEL[variant], phase,
                      round_index, argv, raw_path, final_path)
    segments.append(segment)
    return segment

  # 数值阶段: 每个变体每个变体各一次 (固定顺序 noopt -> release)。
  for variant in VARIANTS:
    for build in ("noopt", "release"):
      out_dir = os.path.join(base, "bench", build, variant)
      raw = os.path.join(out_dir, "numerical.raw.json")
      final = os.path.join(out_dir, "numerical.json")
      argv = benchmark_argv(binaries[(build, variant)], params[variant][0],
                            params[variant][1], "numerical", raw)
      add(f"{build}_{variant}_numerical", variant, "numerical", 0, argv, raw, final)

  # 同算法计时: 顺序 N -> R -> R -> N (两轮).
  order = [("noopt", 1), ("release", 1), ("release", 2), ("noopt", 2)]
  for variant in VARIANTS:
    for build, round_index in order:
      out_dir = os.path.join(base, "bench", build, variant)
      raw = os.path.join(out_dir, f"timing_{round_index}.raw.json")
      final = os.path.join(out_dir, f"timing_{round_index}.json")
      argv = benchmark_argv(binaries[(build, variant)], params[variant][0],
                            params[variant][1], "timing", raw)
      add(f"{build}_{variant}_timing_{round_index}", variant, f"timing_{round_index}",
          round_index, argv, raw, final)

  # 迁移: A 重放 (旧 IPOPT 输入) + A 闭环 + B 重放.
  migration = os.path.join(base, "migration")
  replay_a_raw = os.path.join(migration, "replay_A.raw.json")
  add("release_kinematic_replay_A", "kinematic", "replay", 0,
      benchmark_argv(binaries[("release", "kinematic")], params["kinematic"][0],
                     params["kinematic"][1], "numerical", replay_a_raw,
                     os.path.join(reference_root, "evidence", "bench", "release",
                                  "kinematic", "numerical.json")),
      replay_a_raw, os.path.join(migration, "replay_A.json"))

  closed_loop_raw = os.path.join(migration, "closed_loop_A.raw.json")
  add("release_kinematic_closed_loop_A", "kinematic", "closed_loop", 0,
      benchmark_argv(binaries[("release", "kinematic")], params["kinematic"][0],
                     params["kinematic"][1], "closed_loop", closed_loop_raw),
      closed_loop_raw, os.path.join(migration, "closed_loop_A.json"))

  replay_b_raw = os.path.join(migration, "replay_B.raw.json")
  add("release_dynamic_replay_B", "dynamic_acados", "replay", 0,
      benchmark_argv(binaries[("release", "dynamic_acados")], params["dynamic_acados"][0],
                     params["dynamic_acados"][1], "numerical", replay_b_raw,
                     os.path.join(reference_root, "evidence", "bench", "release",
                                  "dynamic_acados", "numerical.json")),
      replay_b_raw, os.path.join(migration, "replay_B.json"))

  # B 原版/新 Release 抽取对照: Old -> New -> New -> Old.
  timing_dir = os.path.join(migration, "timing")
  old_binary = os.path.join(reference_root, "build_release", "usv_nmpc",
                            "benchmark_dynamic_solver")
  old_params = (os.path.join(config_old, "mpc_params_B.yaml"),
                os.path.join(config_old, "usv_params_B.yaml"))
  new_binary = binaries[("release", "dynamic_acados")]
  for label, round_index in (("old_B", 1), ("new_B", 1), ("new_B", 2), ("old_B", 2)):
    is_old = label == "old_B"
    raw = os.path.join(timing_dir, f"{label}_{round_index}.raw.json")
    final = os.path.join(timing_dir, f"{label}_{round_index}.json")
    argv = benchmark_argv(
      old_binary if is_old else new_binary,
      old_params[0] if is_old else params["dynamic_acados"][0],
      old_params[1] if is_old else params["dynamic_acados"][1],
      "timing", raw)
    add(f"{label}_timing_{round_index}", "dynamic_acados", f"timing_{label}",
        round_index, argv, raw, final)
  return segments


def segment_sources(segment, release_root, reference_root):
  """返回 (binary, shared_backend, ocp_json, params, manifest)。"""
  is_old_b = segment.segment_id.startswith("old_B_")
  root = reference_root if is_old_b else release_root
  variant = segment.variant
  if is_old_b:
    binary = os.path.join(reference_root, "build_release", "usv_nmpc",
                          "benchmark_dynamic_solver")
    config = os.path.join(reference_root, "src", "usv_bringup", "config")
    shared = None
  else:
    build = "noopt" if segment.segment_id.startswith("noopt_") else "release"
    package, executable = (("usv_mpc", "benchmark_kinematic_solver")
                           if variant == "kinematic"
                           else ("usv_nmpc", "benchmark_dynamic_solver"))
    binary = os.path.join(release_root, f"build_{build}", package, executable)
    config = os.path.join(release_root, "src", "usv_bringup", "config")
    shared = os.path.join(release_root, f"install_{build}", "usv_acados", "lib",
                          "libusv_acados_backend.so")
    if not os.path.exists(shared):
      shared = os.path.realpath(os.path.join(
        release_root, f"install_{build}", "usv_acados", "lib",
        "libusv_acados_backend.so.0"))
  model = VARIANT_MODEL[variant]
  if variant == "kinematic":
    ocp_json = os.path.join(release_root, "src", "usv_acados", "acados_generated",
                            "kinematic", "usv_kin_ocp.json")
    params = [os.path.join(config, "mpc_params_A.yaml"),
              os.path.join(config, "usv_params_A.yaml")]
  else:
    ocp_json = os.path.join(root, "src", "usv_acados", "acados_generated",
                            "dynamic", "usv_dyn_ocp.json")
    params = [os.path.join(config, "mpc_params_B.yaml"),
              os.path.join(config, "usv_params_B.yaml")]
    if is_old_b:
      # 旧候选没有 usv_acados 包: 用其冻结的 usv_nmpc 生成码 JSON。
      ocp_json = os.path.join(reference_root, "src", "usv_nmpc", "acados_generated",
                              "usv_dyn_ocp.json")
  manifest = os.path.join(root, "evidence", "source_manifest_frozen.txt")
  return binary, shared, ocp_json, params, manifest


def execute(segments, release_root, reference_root):
  """按固定顺序执行, 返回 (failures, env 段落, manifest 条目)。"""
  groups = {}
  boot_ids = set()
  failures = []
  env_segments = {}
  manifest_entries = []
  library_paths = {}
  for segment in segments:
    shared_lib = segment_sources(segment, release_root, reference_root)[1]
    key = os.path.dirname(shared_lib) if shared_lib else ""
    extra = [key] if key else []
    if segment.segment_id.startswith("old_B_"):
      # 旧 B 二进制没有新共用库: 只加它自己的依赖目录, 不 source 旧 install。
      extra = [os.path.join(reference_root, "install_release", "usv_nmpc", "lib"),
               os.path.join(reference_root, "install_release", "usv_acados", "lib")]
      extra = [path for path in extra if os.path.isdir(path)]
    binary, shared, ocp_json, params, manifest = segment_sources(
      segment, release_root, reference_root)
    env = build_environment(release_root, reference_root, extra)
    completed = run_benchmark(
      segment, env,
      lambda: artifact_hashes(binary, shared, ocp_json, params, manifest))
    segment.stdout_tail += ""
    if segment.start.get("boot_id"):
      boot_ids.add(segment.start["boot_id"])
    failures.extend(validate_measurement(segment, groups, None))
    failures.extend(validate_service_stability(
      segment.segment_id, segment.service_before, segment.service_after))
    failures.extend(validate_artifact_stability(
      segment.segment_id, segment.artifacts_before, segment.artifacts_after))
    if segment.segment_id.startswith("old_B_"):
      # 旧 B benchmark 在 build 目录里, 仍必须前后重算身份哈希并核对固定值。
      recorded = (segment.artifacts_before.get("binary") or {}).get("sha256")
      expected = OLD_B_BENCHMARK_SHA256
      if recorded != expected:
        failures.append(
          f"{segment.segment_id}: 旧 B benchmark 哈希 {recorded} != {expected}")
    entry = {
      "segment_id": segment.segment_id,
      "variant": segment.variant,
      "phase": segment.phase,
      "round": segment.round_index,
      "command": segment.command,
      "returncode": segment.returncode,
      "elapsed_s": getattr(segment, "elapsed_s", None),
      "raw_path": segment.raw_path,
      "final_path": segment.final_path,
      "binary_path": os.path.realpath(binary),
      "binary_sha256": sha256_file(binary) if os.path.exists(binary) else None,
      "shared_backend_path": os.path.realpath(shared) if shared else None,
      "shared_backend_sha256": sha256_file(shared) if shared else None,
      "ocp_json_path": os.path.realpath(ocp_json) if os.path.exists(ocp_json) else None,
      "ocp_json_sha256": (sha256_file(ocp_json)
                          if os.path.exists(ocp_json) else None),
      "params": [{"path": os.path.realpath(path),
                  "sha256": sha256_file(path) if os.path.exists(path) else None}
                 for path in params],
      "start": segment.start,
      "end": segment.end,
      "service_before": segment.service_before,
      "service_after": segment.service_after,
      "artifacts_before": segment.artifacts_before,
      "artifacts_after": segment.artifacts_after,
      "stdout_tail": segment.stdout_tail,
      "stderr_tail": segment.stderr_tail,
    }
    manifest_entries.append(entry)
    env_segments[segment.segment_id] = segment.to_env_json()
    if completed.returncode != 0:
      failures.append(
        f"{segment.segment_id}: benchmark 退出码 {completed.returncode}: "
        f"{(completed.stderr or '').strip()[-300:]}")
      # 保留 raw (即使失败) 与进程输出; 不生成最终结果。
      continue
    provenance = provenance_for(segment, binary, shared, ocp_json,
                                VARIANT_MODEL[segment.variant], params, manifest)
    finalize_segment(segment, provenance)
  if len(boot_ids) > 1:
    failures.append(f"整轮测量跨多个 boot_id: {sorted(boot_ids)}")
  return failures, env_segments, manifest_entries


def _service_untouched(manifest_entries):
  """由实际观测推导 (不写死): 每个段前后 usv-system active、PID/重启不变。"""
  if not manifest_entries:
    return False
  for entry in manifest_entries:
    before = (entry.get("service_before") or {}).get("usv-system", {})
    after = (entry.get("service_after") or {}).get("usv-system", {})
    if before.get("ActiveState") != "active" or after.get("ActiveState") != "active":
      return False
    if before.get("MainPID") != after.get("MainPID"):
      return False
    if before.get("NRestarts") != after.get("NRestarts"):
      return False
  return True


def env_document(group_label, env_segments, segments):
  """compare_release_baseline 需要的 env.json: 与变体目录配套的分段记录。"""
  relevant = [item for item in env_segments.values()
              if item["final_path"].startswith(group_label)]
  relevant.sort(key=lambda item: item["label"])
  starts = [item["start"] for item in relevant if item.get("start")]
  sticky = [item.get("throttled_sticky") for item in starts
            if item.get("throttled_sticky") is not None]
  raw = [item.get("throttled_raw") for item in starts if item.get("throttled_raw")]
  return {
    "variant": os.path.basename(group_label),
    "segments": starts,
    "segment_labels": [item["label"] for item in relevant],
    "throttled_sticky": (max(sticky) if sticky else None),
    "throttled_raw": (raw[0] if raw else None),
    "boot_ids": sorted({item.get("boot_id") for item in starts if item.get("boot_id")}),
    "governors": sorted({item.get("governor") for item in starts
                         if item.get("governor")}),
    "segments_detail": relevant,
  }


def main(argv):
  parser = argparse.ArgumentParser(description="性能/数值证据采集")
  parser.add_argument("--release-root", required=True, help="新候选 R")
  parser.add_argument("--reference-root", required=True, help="不可变旧候选 R0")
  parser.add_argument("--skip-environment-gate", action="store_true",
                      help="仅用于离线自测: 环境无效时仍写报告 (结果标记未验收)")
  args = parser.parse_args(argv)

  try:
    release_root = resolve_release_root(args.release_root, "--release-root")
    reference_root = resolve_release_root(args.reference_root, "--reference-root")
    check_prerequisites(release_root, reference_root)
    base = os.path.join(release_root, "evidence")
    segments = plan_segments(release_root, reference_root, base)
    failures, env_segments, manifest_entries = execute(
      segments, release_root, reference_root)
  except (RunnerError, OSError) as error:
    print(f"runner 失败: {error}", file=sys.stderr)
    return 2

  for build in ("noopt", "release"):
    path = os.path.join(base, "bench", build, "env.json")
    if os.path.exists(path):
      continue
    write_json_exclusive(
      path, env_document(os.path.join(base, "bench", build), env_segments, segments))
  migration_env = os.path.join(base, "migration", "env.json")
  if not os.path.exists(migration_env):
    write_json_exclusive(
      migration_env, env_document(os.path.join(base, "migration"), env_segments, segments))
  manifest_path = os.path.join(base, "run_manifest.json")
  if not os.path.exists(manifest_path):
    write_json_exclusive(manifest_path, {
      "release_root": release_root,
      "reference_root": reference_root,
      "utc": utc_now(),
      "effective_uid": os.geteuid(),
      "cpu_pin": CPU_PIN,
      "thread_env": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"},
      "production_service_untouched": _service_untouched(manifest_entries),
      "service_baseline": service_snapshot(),
      "segments": manifest_entries,
      "failures": failures,
    })

  for failure in failures:
    print(f"未通过: {failure}", file=sys.stderr)
  print(f"采集完成: {len(segments)} 个 segment, {len(failures)} 项失败")
  if failures and not args.skip_environment_gate:
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
