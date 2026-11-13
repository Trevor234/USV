#!/usr/bin/env python3
"""树莓派发布身份取证 (只读)。

两个子命令:
  static  --release-root <R> --variant noopt|release --output <JSON>
      采集冻结源码清单内容哈希、构建配置/编译命令、安装 ELF/launch/config/
      ament marker 与外部依赖解析路径及哈希、测试结果引用。只描述“这份构建是
      什么”, 不声称它已在线生效。
  runtime --expected-install <路径> --output <JSON> [--record-only]
          [--baseline <先前 JSON>]
      采集实际在线身份: 三个服务状态、受管 cgroup 内进程的 ELF(含已删除文件)
      哈希、自定义节点是否落在预期 install、MAVROS/串口独占、控制器 --params-file
      与实时参数、启动日志后端、五包解析前缀。默认在缺失/不匹配时非零退出;
      --record-only 仅用于给旧运行态留证, 不能用于候选验收。

只读: 不写服务配置、不重启服务、不打开串口、不调用 ROS 服务。
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ElementTree

import yaml

PKG_KINEMATIC = "usv_mpc"
PKG_DYNAMIC = "usv_nmpc"
PACKAGES = ("usv_acados", "usv_mpc", "usv_nmpc", "usv_safety", "usv_planning",
            "usv_bringup")
# 各方案的控制节点可执行文件与预期后端 (方案 A/B 均为 acados, 共用后端库)。
SCHEME_PROFILE = {
  "A": {"package": PKG_KINEMATIC, "executable": "mpc_node", "backend": "acados",
        "control_mode": "kinematic", "param_prefix": "kinematic.",
        "params_yaml": "mpc_params_A.yaml", "vehicle_yaml": "usv_params_A.yaml"},
  "B": {"package": PKG_DYNAMIC, "executable": "mpc_node", "backend": "acados",
        "control_mode": "dynamic", "param_prefix": "dynamic.",
        "params_yaml": "mpc_params_B.yaml", "vehicle_yaml": "usv_params_B.yaml"},
}
# 参数核对必须存在的关键字段 (与节点 declare_parameter 一一对应)。
CRITICAL_KINEMATIC_KEYS = (
  "control_mode", "mpc_dt", "horizon", "max_solve_time_ms",
  "kinematic.dt", "kinematic.Q", "kinematic.R", "kinematic.u_max",
  "kinematic.u_min", "kinematic.r_max", "kinematic.du_max",
  "kinematic.dr_max", "kinematic.tau_u", "kinematic.tau_r",
  "kinematic.Qf_scale", "kinematic.backend",
  "kinematic.solution_constraint_tol",
)
CRITICAL_DYNAMIC_KEYS = (
  "control_mode", "mpc_dt", "horizon", "max_solve_time_ms",
  "dynamic.dt", "dynamic.Q", "dynamic.R", "dynamic.Rd", "dynamic.Qf_scale",
  "dynamic.T_max", "dynamic.T_min", "dynamic.dT_max",
  "vehicle.mass", "vehicle.Iz", "vehicle.xg", "vehicle.d_thruster",
  "vehicle.Xu_dot", "vehicle.Yv_dot", "vehicle.Yr_dot", "vehicle.Nv_dot",
  "vehicle.Nr_dot", "vehicle.Xu", "vehicle.Yv", "vehicle.Yr", "vehicle.Nv",
  "vehicle.Nr", "vehicle.Xuu", "vehicle.Yvv", "vehicle.Yrr", "vehicle.Nvv",
  "vehicle.Nrr",
)
SERVICES = ("usv-system", "usv-record", "usv-rtk")
SERIAL_PREFIX = "/dev/tty"
# 解释器可执行文件不作为“自定义节点”判定对象 (ros2 launch / python 节点)。
INTERPRETER_PATTERN = re.compile(r"^(python[0-9.]*|bash|sh|dash)$")
ROS_PREFIX = "/opt/ros/"
EXTERNAL_LIBRARY_MARKERS = ("libacados", "libblasfeo", "libhpipm", "libcasadi")
# 共用后端库: 候选自建, 必须由两个控制器共同加载。
SHARED_BACKEND_MARKER = "libusv_acados_backend"
SOURCE_EXCLUDES = (".git", "build", "install", "log", "__pycache__")


class IdentityError(Exception):
  pass


def sha256_bytes(payload):
  return hashlib.sha256(payload).hexdigest()


def sha256_text(text):
  return sha256_bytes(text.encode("utf-8"))


# ── 只读执行器 (测试中可替换为假实现) ───────────────────────────────
class CommandRunner:
  """只读执行器。输出按 UTF-8 容错解码: systemd 单元里的中文注释在
  部分文件编码下会被 cat 原样吐出, 不能让一个非 UTF-8 字节葬送整次取证。
  """

  def run(self, argv, timeout=60, env=None):
    completed = subprocess.run(argv, capture_output=True,
                               timeout=timeout, check=False, env=env)
    return (completed.returncode,
            completed.stdout.decode("utf-8", "replace"),
            completed.stderr.decode("utf-8", "replace"))

  def read_bytes(self, path):
    with open(path, "rb") as handle:
      return handle.read()

  def read_text(self, path):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
      return handle.read()

  def readlink(self, path):
    return os.readlink(path)

  def exists(self, path):
    return os.path.exists(path)

  def isdir(self, path):
    return os.path.isdir(path)

  def listdir(self, path):
    return sorted(os.listdir(path))

  def realpath(self, path):
    return os.path.realpath(path)


def hash_file(runner, path):
  return sha256_bytes(runner.read_bytes(path))


# ── static: 冻结源码清单 ────────────────────────────────────────────
def manifest_tree(runner, root, excludes=SOURCE_EXCLUDES):
  entries = []

  def walk(directory, prefix):
    for name in runner.listdir(directory):
      if name in excludes:
        continue
      path = os.path.join(directory, name)
      relative = os.path.join(prefix, name) if prefix else name
      if runner.isdir(path):
        walk(path, relative)
        continue
      entries.append({
        "path": relative,
        "size": len(runner.read_bytes(path)),
        "sha256": hash_file(runner, path),
      })

  walk(root, "")
  entries.sort(key=lambda item: item["path"])
  return entries


def manifest_digest(entries):
  lines = [f"{item['path']}\0{item['size']}\0{item['sha256']}" for item in entries]
  return sha256_text("\n".join(lines))


def audit_all_compile_commands(runner, compile_dirs, variant):
  """逐包审计编译命令。

  只有 usv_acados 带 vendored acados codegen (C99), 且必须同时存在
  kinematic 与 dynamic 两套生成 .c 的编译记录 —— 仅凭任意一个 C 文件通过
  无法证明两个模型都真的被编进了共用库。
  """
  combined = {"compile_commands": [], "records": [], "failures": []}
  for directory in compile_dirs:
    package = os.path.basename(directory)
    single = audit_compile_commands(
      runner, directory, variant, expect_codegen=(package == "usv_acados"))
    combined["compile_commands"].append({
      "package_dir": package,
      "sha256": single["compile_commands_sha256"],
    })
    combined["records"].extend(single["records"])
    combined["failures"].extend(single["failures"])
    if package == "usv_acados":
      generated = [item for item in single["records"]
                   if "/acados_generated/" in item["file"]]
      models = {item["file"].split("/acados_generated/", 1)[1].split("/")[0]
                for item in generated}
      for model in ("kinematic", "dynamic"):
        if model not in models:
          combined["failures"].append(
            f"usv_acados 缺少 {model} 生成码的 C 编译记录 "
            "(两个模型都必须编进共用库)")
  if not compile_dirs:
    combined["failures"].append("未找到 compile_commands.json")
  return combined


def audit_compile_commands(runner, build_dir, variant, expect_codegen=False):
  """按实际编译命令校验优化级别, 并返回逐文件记录。"""
  path = os.path.join(build_dir, "compile_commands.json")
  if not runner.exists(path):
    raise IdentityError(f"缺少 compile_commands.json: {path}")
  payload = json.loads(runner.read_text(path))
  expect_release = (variant == "release")
  interesting = ("mpc_node.cpp", "acados_backend.cpp",
                 "acados_kinematic_backend.cpp", "kinematic_solution_audit.cpp",
                 "kinematic_mpc_solver.cpp", "model_api.cpp", "mpc_solver.cpp")
  records = []
  failures = []
  for entry in payload:
    source = entry.get("file", "")
    command = entry.get("command") or " ".join(entry.get("arguments", []))
    tokens = shlex.split(command)
    optimization = [token for token in tokens if token.startswith("-O")]
    defines = [token for token in tokens if token.startswith("-DNDEBUG")]
    is_generated_c = ("/acados_generated/" in source and source.endswith(".c"))
    is_c = source.endswith(".c")
    if not (os.path.basename(source) in interesting or is_generated_c):
      continue
    records.append({
      "file": source,
      "language": "C" if is_c else "CXX",
      "optimization": optimization,
      "ndebug": bool(defines),
    })
    if expect_release:
      if "-O3" not in optimization or not defines:
        failures.append(f"{source} 缺少有效 Release 优化 (-O3 -DNDEBUG): {optimization}")
      if any(flag in ("-O0", "-Og", "-O1") for flag in optimization):
        failures.append(f"{source} 存在覆盖优化级别: {optimization}")
    elif optimization != ["-O0"]:
      failures.append(f"{source} 非 -O0 编译: {optimization}")
  if expect_codegen and not any(item["language"] == "C" for item in records):
    failures.append(
      f"{build_dir} 未找到 codegen 的 C 编译记录 (vendored 生成码未被编译)")
  records.sort(key=lambda item: item["file"])
  return {
    "compile_commands_sha256": hash_file(runner, path),
    "records": records,
    "failures": failures,
  }


def read_cmake_cache(runner, build_dir):
  path = os.path.join(build_dir, "CMakeCache.txt")
  if not runner.exists(path):
    raise IdentityError(f"缺少 CMakeCache.txt: {path}")
  wanted = {}
  for line in runner.read_text(path).splitlines():
    if not line or line.startswith("//") or line.startswith("#"):
      continue
    if "=" not in line or ":" not in line.split("=", 1)[0]:
      continue
    key, value = line.split("=", 1)
    name = key.split(":", 1)[0]
    if name.startswith(("CMAKE_BUILD_TYPE", "CMAKE_C_FLAGS", "CMAKE_CXX_FLAGS",
                        "CMAKE_C_COMPILER", "CMAKE_CXX_COMPILER",
                        "CMAKE_EXPORT_COMPILE_COMMANDS")):
      wanted[name] = value
  return wanted


def elf_machine(runner, path):
  head = runner.read_bytes(path)[:20]
  if len(head) < 20 or head[:4] != b"\x7fELF":
    return None
  little = head[5] == 1
  machine = int.from_bytes(head[18:20], "little" if little else "big")
  return {"class": head[4], "machine": machine}


def runtime_library_paths(runner, install_root):
  """控制器运行时必须显式可见的两个目录。

  1. 本候选的共用后端库 (install_<variant>/usv_acados/lib): 由 workspace
     overlay 提供, 这里显式列出以便在没有 overlay 的取证进程里也能解析。
  2. acados 运行时库 (libacados/libhpipm/libblasfeo): 间接依赖
     (libacados -> libhpipm) 不享受可执行文件的 RUNPATH。
  方案 A 不再链接/import CasADi, 因此这里不做 CasADi 探测。
  """
  shared_dir = os.path.join(install_root, "usv_acados", "lib")
  acados_dir = os.path.expanduser("~/acados/lib")
  return [path for path in (shared_dir, acados_dir) if path]


def ros_ldd_environment(runner, library_paths=()):
  """构造与生产启动一致的 ldd 环境: ROS 基础 overlay + acados/casadi 目录。

  直接 `ldd` 一个未 source 过 ROS 的节点会报一堆 librclcpp.so not found ——
  那不是构建缺陷, 而是环境缺失, 不能当成依赖未解析。
  """
  command = ("source /opt/ros/jazzy/setup.bash >/dev/null 2>&1 && "
             "env -0")
  code, out, err = runner.run(["/bin/bash", "-c", command])
  env = {}
  if code == 0:
    for entry in out.split("\0"):
      if "=" in entry:
        key, value = entry.split("=", 1)
        env[key] = value
  extra = ":".join(library_paths)
  existing = env.get("LD_LIBRARY_PATH", "")
  env["LD_LIBRARY_PATH"] = ":".join(
    [item for item in (extra, existing) if item])
  # source 步骤失败时至少保证 acados/casadi 目录可见
  env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
  return env


def ldd_resolution(runner, path, library_paths=(), env=None):
  if env is None:
    env = ros_ldd_environment(runner, library_paths)
  code, out, err = runner.run(["ldd", path], env=env)
  libraries = []
  missing = []
  for line in out.splitlines():
    line = line.strip()
    if not line:
      continue
    if "=>" in line:
      name, rest = line.split("=>", 1)
      target = rest.strip().split(" (")[0].strip()
      if target == "not found":
        missing.append(name.strip())
        continue
      libraries.append({"name": name.strip(), "path": target})
    else:
      target = line.split(" (")[0].strip()
      if target.startswith("/"):
        libraries.append({"name": os.path.basename(target), "path": target})
  return {"libraries": libraries, "missing": missing, "returncode": code,
          "stderr": err.strip()}


def collect_test_results(runner, build_dir):
  totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
  files = []

  def walk(directory):
    for name in runner.listdir(directory):
      path = os.path.join(directory, name)
      if runner.isdir(path):
        walk(path)
      elif name.endswith(".xml") and "/test_results/" in path + "/":
        files.append({
          "path": os.path.relpath(path, build_dir),
          "sha256": hash_file(runner, path),
        })

  walk(build_dir)
  for item in files:
    try:
      root = ElementTree.fromstring(
        runner.read_text(os.path.join(build_dir, item["path"])))
    except ElementTree.ParseError:
      item["parse_error"] = True
      continue
    suites = [root] if root.tag == "testsuite" else list(root)
    for suite in suites:
      if suite.tag != "testsuite":
        continue
      for key in totals:
        try:
          totals[key] += int(suite.attrib.get(key, 0))
        except ValueError:
          pass
  return {"totals": totals, "files": files}


def collect_static(root, variant, runner):
  root = runner.realpath(root)
  source_dir = os.path.join(root, "src")
  if not runner.isdir(source_dir):
    raise IdentityError(f"冻结源码目录缺失: {source_dir}")
  build_dir = os.path.join(root, f"build_{variant}")
  install_dir = os.path.join(root, f"install_{variant}")

  source_entries = manifest_tree(runner, source_dir)
  manifest = {
    "root": source_dir,
    "file_count": len(source_entries),
    "total_bytes": sum(item["size"] for item in source_entries),
    "content_sha256": manifest_digest(source_entries),
    "files": source_entries,
  }

  git_identity = {"present": False}
  git_path = os.path.join(root, "source_git.txt")
  if runner.exists(git_path):
    git_identity = {"present": True, "sha256": hash_file(runner, git_path),
                    "text": runner.read_text(git_path).strip()}

  # colcon 把每个包建在自己的 build/<pkg> 子目录里, CMakeCache 与
  # compile_commands.json 都在包级目录下。
  cache_paths = []
  compile_dirs = []
  if runner.exists(os.path.join(build_dir, "CMakeCache.txt")):
    cache_paths.append(build_dir)
  for package in PACKAGES:
    package_dir = os.path.join(build_dir, package)
    if runner.exists(os.path.join(package_dir, "CMakeCache.txt")):
      cache_paths.append(package_dir)
    if runner.exists(os.path.join(package_dir, "compile_commands.json")):
      compile_dirs.append(package_dir)
  if not cache_paths:
    raise IdentityError(f"未找到任何 CMakeCache.txt: {build_dir}")
  cmake_cache = {}
  for directory in cache_paths:
    for key, value in read_cmake_cache(runner, directory).items():
      cmake_cache.setdefault(key, value)
  compile_audit = audit_all_compile_commands(runner, compile_dirs, variant)
  test_results = collect_test_results(runner, build_dir)

  install = {"packages": {}, "failures": [],
             "external_libraries": {}}
  library_paths = runtime_library_paths(runner, install_dir)
  install["runtime_library_paths"] = library_paths
  link_env = ros_ldd_environment(runner, library_paths)
  for package in PACKAGES:
    prefix = os.path.join(install_dir, package)
    marker_candidates = [
      os.path.join(install_dir, package, "share", "ament_index",
                   "resource_index", "packages", package),
      os.path.join(install_dir, "share", "ament_index",
                   "resource_index", "packages", package),
    ]
    marker = next((item for item in marker_candidates
                   if runner.exists(item)), marker_candidates[0])
    entry = {"prefix": prefix, "present": runner.isdir(prefix),
             "ament_marker": None}
    if runner.exists(marker):
      entry["ament_marker"] = {"path": marker, "sha256": hash_file(runner, marker)}
    else:
      install["failures"].append(f"{package} 缺少 ament marker: {marker}")
    install["packages"][package] = entry

  binaries = {}
  for package in PACKAGES:
    lib_dir = os.path.join(install_dir, package, "lib", package)
    if not runner.isdir(lib_dir):
      continue
    for name in runner.listdir(lib_dir):
      path = os.path.join(lib_dir, name)
      if runner.isdir(path):
        continue
      info = {"path": path, "sha256": hash_file(runner, path),
              "elf": elf_machine(runner, path)}
      if info["elf"] is None:
        continue
      if info["elf"]["machine"] != 183:
        install["failures"].append(f"{path} 不是 AArch64 ELF (machine={info['elf']['machine']})")
      binaries[os.path.relpath(path, install_dir)] = info
      if name == "mpc_node":
        resolution = ldd_resolution(runner, path, library_paths, link_env)
        if resolution["missing"]:
          install["failures"].append(f"{path} 存在未解析依赖: {resolution['missing']}")
        external = []
        for library in resolution["libraries"]:
          if any(marker in os.path.basename(library["path"])
                 for marker in EXTERNAL_LIBRARY_MARKERS):
            external.append({
              "path": library["path"],
              "sha256": hash_file(runner, library["path"]),
            })
        install["external_libraries"][package] = external

  # 共用后端库: 必须存在、是 AArch64 ELF、无未解析依赖, 且 ldd 里出现
  # acados/hpipm/blasfeo; 不用 libcasadi。
  shared = {"path": None, "sha256": None, "elf": None, "libraries": [],
            "missing": [], "failures": []}
  shared_candidates = [
    os.path.join(install_dir, "usv_acados", "lib", name)
    for name in runner.listdir(os.path.join(install_dir, "usv_acados", "lib"))
  ] if runner.isdir(os.path.join(install_dir, "usv_acados", "lib")) else []
  shared_real = [path for path in shared_candidates
                 if SHARED_BACKEND_MARKER in os.path.basename(path)
                 and not os.path.islink(path)]
  if not shared_real:
    shared["failures"].append("缺少共用后端库 libusv_acados_backend.so")
  else:
    shared_path = sorted(shared_real)[0]
    shared["path"] = shared_path
    shared["sha256"] = hash_file(runner, shared_path)
    shared["elf"] = elf_machine(runner, shared_path)
    if shared["elf"] is None or shared["elf"]["machine"] != 183:
      shared["failures"].append(
        f"共用后端库不是 AArch64 ELF: {shared['elf']}")
    resolution = ldd_resolution(runner, shared_path, library_paths, link_env)
    shared["libraries"] = resolution["libraries"]
    shared["missing"] = resolution["missing"]
    if resolution["missing"]:
      shared["failures"].append(
        f"共用后端库存在未解析依赖: {resolution['missing']}")
    names = [os.path.basename(item["path"]) for item in resolution["libraries"]]
    for marker in ("libacados", "libhpipm", "libblasfeo"):
      if not any(marker in name for name in names):
        shared["failures"].append(f"共用后端库未链接 {marker} (ldd 缺项)")
    if any("libcasadi" in name for name in names):
      shared["failures"].append("共用后端库仍链接 libcasadi")
  install["shared_backend"] = shared

  # 安装的生成码元数据必须与冻结源码逐字节一致 (OCP JSON + 生成清单)。
  generated = {"models": {}, "failures": []}
  for model in ("kinematic", "dynamic"):
    frozen_dir = os.path.join(source_dir, "usv_acados", "acados_generated", model)
    install_side = os.path.join(install_dir, "usv_acados", "share", "usv_acados",
                                "acados_generated", model)
    entry = {"source_dir": frozen_dir, "install_dir": install_side, "files": {}}
    if not runner.isdir(install_side):
      generated["failures"].append(f"{model}: install 缺少生成码元数据 {install_side}")
      generated["models"][model] = entry
      continue
    # generated_manifest_<model>.json 是构建期产物 (冻结源码里没有同名文件):
    # 只核对它列出的文件与 install 实际内容一致, 以及 manifest 自身哈希。
    manifest_name = f"generated_manifest_{model}.json"
    for name in runner.listdir(install_side):
      install_path = os.path.join(install_side, name)
      if runner.isdir(install_path):
        continue
      install_hash = hash_file(runner, install_path)
      if name == manifest_name:
        entry["manifest"] = {"path": install_path, "sha256": install_hash}
        try:
          listed = json.loads(runner.read_text(install_path)).get("files", [])
        except (json.JSONDecodeError, AttributeError):
          generated["failures"].append(f"{model}: {name} 不是有效 JSON")
          continue
        # install 只带 JSON + 清单 (生成 .c/.h 只在冻结源码与构建目录里),
        # 因此清单逐项对冻结源码核对: 证明这份清单描述的确实是本候选源码。
        names = {item.get("path", "").split("/", 1)[-1] for item in listed}
        for item in listed:
          relative = item.get("path", "").split("/", 1)[-1]
          target = os.path.join(frozen_dir, relative)
          if not runner.exists(target):
            generated["failures"].append(
              f"{model}: 生成清单列出但冻结源码缺失: {relative}")
          elif item.get("sha256") != hash_file(runner, target):
            generated["failures"].append(
              f"{model}: 生成清单哈希与冻结源码不符: {relative}")
        entry["manifest_file_count"] = len(names)
        continue
      source_path = os.path.join(frozen_dir, name)
      if not runner.exists(source_path):
        generated["failures"].append(
          f"{model}/{name}: 冻结源码中不存在对应文件")
        continue
      source_hash = hash_file(runner, source_path)
      entry["files"][name] = {"install_sha256": install_hash,
                              "source_sha256": source_hash}
      if install_hash != source_hash:
        generated["failures"].append(
          f"{model}/{name}: install 与冻结源码哈希不一致")
    if not entry["files"]:
      generated["failures"].append(f"{model}: install 生成码元数据为空")
    if entry.get("manifest") is None:
      generated["failures"].append(f"{model}: install 缺少 {manifest_name}")
    generated["models"][model] = entry
  install["generated_metadata"] = generated

  copied = {"mismatches": [], "files": []}
  for package in PACKAGES:
    source_share = os.path.join(source_dir, package)
    install_share = os.path.join(install_dir, package, "share", package)
    if not runner.isdir(install_share):
      continue
    for name in ("config", "launch"):
      source_side = os.path.join(source_share, name)
      install_side = os.path.join(install_share, name)
      if not runner.isdir(source_side) or not runner.isdir(install_side):
        continue
      for filename in runner.listdir(install_side):
        install_path = os.path.join(install_side, filename)
        if runner.isdir(install_path):
          continue
        source_path = os.path.join(source_side, filename)
        entry = {"path": os.path.relpath(install_path, install_dir)}
        if not runner.exists(source_path):
          copied["mismatches"].append(f"{entry['path']} 在冻结源码中不存在")
          continue
        install_hash = hash_file(runner, install_path)
        source_hash = hash_file(runner, source_path)
        entry["install_sha256"] = install_hash
        entry["source_sha256"] = source_hash
        if install_hash != source_hash:
          copied["mismatches"].append(f"{entry['path']} 与冻结源码哈希不一致")
        copied["files"].append(entry)

  failures = []
  failures.extend(compile_audit["failures"])
  failures.extend(install["failures"])
  failures.extend(install["shared_backend"]["failures"])
  failures.extend(install["generated_metadata"]["failures"])
  failures.extend(copied["mismatches"])
  if not cmake_cache.get("CMAKE_BUILD_TYPE"):
    failures.append("CMakeCache 中 CMAKE_BUILD_TYPE 为空")

  return {
    "identity_kind": "static_build",
    "release_id": os.path.basename(root),
    "variant": variant,
    "release_root": root,
    "online_effective": False,
    "note": "静态身份只描述本次构建, 不代表该构建已在线运行",
    "source_manifest": manifest,
    "git_identity": git_identity,
    "cmake_cache": cmake_cache,
    "compile_audit": compile_audit,
    "test_results": test_results,
    "install": install,
    "installed_binaries": binaries,
    "installed_copies": copied,
    "failures": failures,
    "identity_ok": not failures,
  }


# ── runtime: 实际在线身份 ───────────────────────────────────────────
def read_text_or_none(runner, path):
  try:
    return runner.read_text(path)
  except OSError:
    return None


def collect_service(runner, unit):
  fields = ("ActiveState", "UnitFileState", "MainPID", "NRestarts",
            "ExecStart", "FragmentPath", "DropInPaths", "ActiveEnterTimestamp",
            "ControlGroup")
  code, out, err = runner.run(
    ["systemctl", "show", unit, "--no-pager",
     f"--property={','.join(fields)}"])
  info = {"unit": unit, "returncode": code, "stderr": err.strip()}
  if code == 0:
    for line in out.splitlines():
      if "=" in line:
        key, value = line.split("=", 1)
        info[key] = value
  cat_code, cat_out, cat_err = runner.run(["systemctl", "cat", unit, "--no-pager"])
  info["unit_fingerprint_sha256"] = (
    sha256_text(cat_out) if cat_code == 0 else None)
  if cat_code != 0:
    info["cat_error"] = cat_err.strip()
  drop_ins = info.get("DropInPaths", "").strip()
  info["drop_ins"] = [item for item in drop_ins.split() if item] if drop_ins else []
  return info


def collect_processes(runner, control_group, expected_install):
  """control_group 取 systemctl show 的 ControlGroup (如 /system.slice/usv-system.service)。"""
  pids = []
  procs_path = os.path.join("/sys/fs/cgroup", control_group.lstrip("/"),
                            "cgroup.procs")
  if runner.exists(procs_path):
    pids = [int(item) for item in runner.read_text(procs_path).split()]
  processes = []
  for pid in pids:
    record = {"pid": pid}
    try:
      raw = runner.read_bytes(f"/proc/{pid}/cmdline")
      record["cmdline"] = [item for item in raw.decode(
        "utf-8", "replace").split("\0") if item]
    except OSError:
      continue
    try:
      link = runner.readlink(f"/proc/{pid}/exe")
    except OSError:
      link = ""
    record["exe_link"] = link
    record["exe_deleted"] = link.endswith(" (deleted)")
    record["exe_target"] = link[:-len(" (deleted)")] if record["exe_deleted"] else link
    try:
      stat = runner.read_text(f"/proc/{pid}/stat")
      record["starttime"] = stat.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
      record["starttime"] = None
    try:
      record["exe_sha256"] = sha256_bytes(runner.read_bytes(f"/proc/{pid}/exe"))
    except OSError:
      record["exe_sha256"] = None
    # 同路径文件的哈希: 用于核对“运行的确实是磁盘上这份”, 以及发现 deleted ELF。
    record["disk_sha256"] = None
    if record["exe_target"] and not record["exe_deleted"]:
      try:
        record["disk_sha256"] = hash_file(runner, record["exe_target"])
      except OSError:
        record["disk_sha256"] = None
    maps = []
    try:
      for line in runner.read_text(f"/proc/{pid}/maps").splitlines():
        parts = line.split()
        if len(parts) < 6:
          continue
        path = parts[5]
        if not path.startswith("/"):
          continue
        if any(marker in os.path.basename(path)
               for marker in EXTERNAL_LIBRARY_MARKERS + (SHARED_BACKEND_MARKER,)):
          if path not in [item["path"] for item in maps]:
            maps.append({"path": path, "sha256": hash_file(runner, path)})
    except OSError:
      pass
    record["external_libraries"] = maps
    params_files = []
    cmdline = record.get("cmdline", [])
    for index, token in enumerate(cmdline):
      if token == "--params-file" and index + 1 < len(cmdline):
        path = cmdline[index + 1]
        entry = {"path": path}
        try:
          entry["sha256"] = hash_file(runner, path)
        except OSError:
          entry["sha256"] = None
        params_files.append(entry)
    record["params_files"] = params_files
    record["under_expected_install"] = record["exe_target"].startswith(
      expected_install + os.sep)
    record["under_ros"] = record["exe_target"].startswith(ROS_PREFIX)
    # 解释器 (python3/bash) 只是外层 shell 或 Python 节点, 归属由 they 的
    # 脚本路径决定; 这里只把 ELF 可执行文件算作需要落位 install 的自定义节点。
    record["is_elf"] = record["exe_target"].startswith("/")
    record["interpreter"] = bool(INTERPRETER_PATTERN.search(
      os.path.basename(record["exe_target"])))
    record["custom"] = (not (record["under_expected_install"] or record["under_ros"])
                        and record["is_elf"] and not record["interpreter"])
    processes.append(record)
  return processes


def collect_serial_holders(runner):
  holders = {}
  for name in runner.listdir("/proc"):
    if not name.isdigit():
      continue
    fd_dir = f"/proc/{name}/fd"
    if not runner.exists(fd_dir):
      continue
    try:
      entries = runner.listdir(fd_dir)
    except OSError:
      continue
    for entry in entries:
      try:
        target = runner.readlink(os.path.join(fd_dir, entry))
      except OSError:
        continue
      if target.startswith(SERIAL_PREFIX) and " (" not in target:
        holders.setdefault(target, []).append(int(name))
  return {device: sorted(set(pids)) for device, pids in holders.items()}


def flatten_mapping(mapping, prefix=""):
  flat = {}
  for key, value in mapping.items():
    name = f"{prefix}{key}"
    if isinstance(value, dict):
      flat.update(flatten_mapping(value, name + "."))
    else:
      flat[name] = value
  return flat


def load_expected_parameters(runner, install, scheme):
  profile = SCHEME_PROFILE[scheme]
  share = os.path.join(install, "usv_bringup", "share", "usv_bringup", "config")
  expected = {}
  sources = []
  for filename in (profile["params_yaml"], profile["vehicle_yaml"]):
    path = os.path.join(share, filename)
    if not runner.exists(path):
      raise IdentityError(f"安装目录缺少参数文件: {path}")
    payload = yaml.safe_load(runner.read_text(path)) or {}
    for _, scope in payload.items():
      parameters = (scope or {}).get("ros__parameters") or {}
      expected.update(flatten_mapping(parameters))
    sources.append({"path": path, "sha256": hash_file(runner, path)})
  return expected, sources


def normalize_parameters(values):
  return json.dumps(values, sort_keys=True, ensure_ascii=False,
                    separators=(",", ":"))


def collect_parameter_dump(runner, install, scheme):
  overlay = os.path.join(install, "setup.bash")
  ros_setup = "/opt/ros/jazzy/setup.bash"
  script = f"source {ros_setup}"
  if runner.exists(overlay):
    script += f" && source {overlay}"
    overlay_present = True
  else:
    overlay_present = False
  script += " && ros2 param dump --timeout 10 /mpc_controller_node"
  code, out, err = runner.run(["/bin/bash", "-lc", script], timeout=60)
  result = {"returncode": code, "overlay_present": overlay_present,
            "stderr": err.strip()[-400:], "parameters": {}, "sha256": None}
  if code != 0:
    return result
  payload = yaml.safe_load(out) or {}
  for _, scope in payload.items():
    parameters = (scope or {}).get("ros__parameters") or {}
    result["parameters"].update(flatten_mapping(parameters))
  result["sha256"] = sha256_text(normalize_parameters(result["parameters"]))
  return result


def collect_package_prefixes(runner, install, scheme):
  overlay = os.path.join(install, "setup.bash")
  script = "source /opt/ros/jazzy/setup.bash"
  if runner.exists(overlay):
    script += f" && source {overlay}"
  prefixes = {}
  for package in PACKAGES:
    code, out, _ = runner.run(
      ["/bin/bash", "-lc", f"{script} && ros2 pkg prefix {package}"], timeout=60)
    value = out.strip() if code == 0 else None
    prefixes[package] = {
      "prefix": value,
      "resolved": bool(value),
      "inside_expected": bool(value) and runner.realpath(value).startswith(
        runner.realpath(install) + os.sep),
    }
  return prefixes


def journal_since(active_enter_timestamp):
  """把 systemd 的 ActiveEnterTimestamp 规范成 journalctl --since 可解析的形式。"""
  tokens = (active_enter_timestamp or "").split()
  if len(tokens) >= 3 and tokens[0].isalpha():
    tokens = tokens[1:]
  return " ".join(tokens[:3]) if len(tokens) >= 2 else ""


def collect_backend_log(runner, unit, active_enter_timestamp):
  """取本次服务启动后的第一条 backend= 日志 (只认本次 invocation)。"""
  since = journal_since(active_enter_timestamp)
  result = {"returncode": None, "stderr": "", "backend": None, "line": None,
            "since": since}
  if not since:
    result["stderr"] = "缺少 ActiveEnterTimestamp, 无法限定日志窗口"
    return result
  # grep -m1 命中即退出, journalctl 收到 SIGPIPE 提前结束, 不整段载入内存。
  command = ("journalctl -u %s --no-pager -o cat --since '%s' "
             "| grep -m1 -o 'backend=[A-Za-z0-9_]*'") % (unit, since)
  code, out, err = runner.run(["/bin/bash", "-lc", command], timeout=90)
  result["returncode"] = code
  result["stderr"] = err.strip()[-200:]
  line = out.strip()
  if line.startswith("backend="):
    result["backend"] = line.split("=", 1)[1]
    result["line"] = line
  return result


def collect_runtime(expected_install, runner):
  install = runner.realpath(expected_install)
  scheme_text = read_text_or_none(runner, "/etc/default/usv-system") or ""
  scheme = ""
  for line in scheme_text.splitlines():
    if line.startswith("SCHEME="):
      scheme = line.split("=", 1)[1].strip()
  profile = SCHEME_PROFILE.get(scheme)
  expected_executable = {"path": None, "sha256": None}
  if profile is not None:
    expected_path = os.path.join(install, profile["package"], "lib",
                                profile["package"], profile["executable"])
    expected_executable["path"] = expected_path
    if runner.exists(expected_path):
      expected_executable["sha256"] = hash_file(runner, expected_path)
  services = {unit: collect_service(runner, unit) for unit in SERVICES}
  control_group = (services["usv-system"].get("ControlGroup")
                   or "/system.slice/usv-system.service")
  processes = collect_processes(runner, control_group, install)
  serial_holders = collect_serial_holders(runner)

  parameters = {"returncode": None, "parameters": {}, "sha256": None}
  expected_parameters = {}
  expected_sources = []
  prefixes = {}
  backend_log = {"backend": None, "line": None, "since": None}
  if scheme in SCHEME_PROFILE:
    expected_parameters, expected_sources = load_expected_parameters(
      runner, install, scheme)
    parameters = collect_parameter_dump(runner, install, scheme)
    prefixes = collect_package_prefixes(runner, install, scheme)
    backend_log = collect_backend_log(
      runner, "usv-system", services["usv-system"].get("ActiveEnterTimestamp", ""))

  return {
    "identity_kind": "runtime",
    "utc": runner.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"])[1].strip(),
    "hostname": (read_text_or_none(runner, "/proc/sys/kernel/hostname") or "").strip(),
    "boot_id": (read_text_or_none(runner, "/proc/sys/kernel/random/boot_id") or "").strip(),
    "scheme": scheme,
    "expected_install": install,
    "services": services,
    "processes": processes,
    "serial_holders": serial_holders,
    "parameter_dump": parameters,
    "expected_parameters": expected_parameters,
    "expected_parameter_sources": expected_sources,
    "package_prefixes": prefixes,
    "expected_executable": expected_executable,
    "backend_log": backend_log,
    "failures": [],
    "identity_ok": None,
  }


# ── 在线身份判定 (纯函数, 便于用假快照做行为测试) ───────────────────
def critical_keys(scheme):
  return CRITICAL_KINEMATIC_KEYS if scheme == "A" else CRITICAL_DYNAMIC_KEYS


def evaluate_runtime(snapshot, baseline=None):
  failures = []
  scheme = snapshot.get("scheme")
  if scheme not in SCHEME_PROFILE:
    return [f"/etc/default/usv-system 的 SCHEME 非法或缺失: {scheme!r}"]
  profile = SCHEME_PROFILE[scheme]
  install = snapshot["expected_install"]
  if not install.startswith("/"):
    failures.append(f"预期 install 不是绝对路径: {install}")

  system = snapshot["services"].get("usv-system", {})
  if system.get("ActiveState") != "active":
    failures.append(f"usv-system 不是 active: {system.get('ActiveState')!r}")

  controllers = [item for item in snapshot["processes"]
                 if os.path.basename(item.get("exe_target", "")) == "mpc_node"]
  if len(controllers) != 1:
    failures.append(
      f"控制器进程数量不为 1: {[(item.get('pid'), item.get('exe_target')) for item in controllers]}")
    return failures
  controller = controllers[0]
  if controller.get("exe_deleted"):
    failures.append(f"控制器 ELF 已被删除 (deleted): {controller.get('exe_link')}")
  if not controller.get("exe_target", "").startswith(install + os.sep):
    failures.append(
      f"控制器不在预期 install 内: {controller.get('exe_target')} (期望 {install})")
  expected_exe = (snapshot.get("expected_executable") or {}).get("path")
  if controller.get("exe_target") != expected_exe:
    failures.append(
      f"控制器路径不是预期方案可执行文件: {controller.get('exe_target')} (期望 {expected_exe})")
  on_disk = (snapshot.get("expected_executable") or {}).get("sha256")
  if on_disk is None:
    failures.append(f"无法读取预期可执行文件: {expected_exe}")
  elif controller.get("exe_sha256") != on_disk:
    failures.append(
      f"运行中 ELF 与安装文件哈希不一致: 运行={controller.get('exe_sha256')} 磁盘={on_disk}")

  # 控制器必须实际加载本候选共用后端库与外部 acados 依赖; 不得残留 libcasadi。
  install_real = snapshot["expected_install"]
  shared_libraries = [lib for lib in controller.get("external_libraries", [])
                      if SHARED_BACKEND_MARKER in os.path.basename(lib.get("path", ""))]
  if not shared_libraries:
    failures.append("控制器未加载共用后端库 libusv_acados_backend")
  for library in shared_libraries:
    path = library.get("path", "")
    if not os.path.realpath(path).startswith(
        os.path.realpath(install_real) + os.sep):
      failures.append(f"共用后端库不在预期 install 内: {path}")
    if library.get("sha256") is None:
      failures.append(f"无法核对共用后端库哈希: {path}")
  external_names = [os.path.basename(item.get("path", ""))
                    for item in controller.get("external_libraries", [])]
  for marker in ("libacados", "libhpipm", "libblasfeo"):
    if not any(marker in name for name in external_names):
      failures.append(f"控制器未加载 {marker}")
  if any("libcasadi" in name for name in external_names):
    failures.append(
      f"控制器仍加载 libcasadi: {[n for n in external_names if 'libcasadi' in n]}")

  for item in snapshot["processes"]:
    if item.get("custom"):
      failures.append(
        f"自定义进程不在预期 install 内: pid={item.get('pid')} exe={item.get('exe_target')}")
      continue
    if not item.get("under_expected_install"):
      continue
    if item.get("exe_deleted"):
      failures.append(
        f"预期 install 内进程的 ELF 已被删除: pid={item.get('pid')} exe={item.get('exe_link')}")
    elif item.get("disk_sha256") is None:
      failures.append(
        f"无法核对 ELF 哈希: pid={item.get('pid')} exe={item.get('exe_target')}")
    elif item.get("exe_sha256") != item.get("disk_sha256"):
      failures.append(
        f"运行中 ELF 与磁盘文件哈希不一致: pid={item.get('pid')} exe={item.get('exe_target')}")

  mavros = [item for item in snapshot["processes"]
            if item.get("exe_target", "").endswith("/lib/mavros/mavros_node")]
  if len(mavros) != 1:
    failures.append(f"MAVROS 进程数量不为 1: {[item.get('pid') for item in mavros]}")

  for device, pids in snapshot["serial_holders"].items():
    holders = [pid for pid in pids if pid in [item["pid"] for item in snapshot["processes"]]]
    if len(holders) > 1:
      failures.append(f"串口 {device} 被多个进程持有: {sorted(pids)}")
    elif holders and not any(pid in holders for pid in [item["pid"] for item in mavros]):
      failures.append(f"串口 {device} 由非 MAVROS 进程持有: {sorted(pids)}")

  dump = snapshot["parameter_dump"]
  live = dump.get("parameters") or {}
  if dump.get("returncode") != 0:
    failures.append(f"无法 dump 控制器参数: rc={dump.get('returncode')} {dump.get('stderr')}")
  else:
    if live.get("control_mode") != profile["control_mode"]:
      failures.append(
        f"在线 control_mode={live.get('control_mode')!r} 与方案 {scheme} 不符")
    expected = snapshot.get("expected_parameters") or {}
    for key in critical_keys(scheme):
      if key not in live:
        failures.append(f"在线参数缺少关键字段: {key}")
      elif key not in expected:
        failures.append(f"安装参数文件缺少关键字段: {key}")
      elif live[key] != expected[key]:
        failures.append(
          f"在线参数与安装配置不一致: {key} 在线={live[key]!r} 安装={expected[key]!r}")

  backend = (snapshot.get("backend_log") or {}).get("backend")
  if backend != profile["backend"]:
    failures.append(
      f"启动日志后端={backend!r} 与方案 {scheme} 预期 {profile['backend']!r} 不符")

  for package, info in (snapshot.get("package_prefixes") or {}).items():
    if package not in PACKAGES:
      continue
    if not info.get("resolved"):
      failures.append(f"未解析到包前缀: {package}")
    elif not info.get("inside_expected"):
      failures.append(
        f"包 {package} 解析到预期 install 之外: {info.get('prefix')}")

  if baseline is not None:
    base_system = baseline.get("services", {}).get("usv-system", {})
    try:
      before = int(base_system.get("NRestarts", 0))
      after = int(system.get("NRestarts", 0))
      if after > before:
        failures.append(f"usv-system 重启次数增加: {before} -> {after}")
    except (TypeError, ValueError):
      failures.append("无法比较 usv-system 重启次数")
    for unit in ("usv-record", "usv-rtk"):
      before = baseline.get("services", {}).get(unit, {}).get("ActiveState")
      after = snapshot["services"].get(unit, {}).get("ActiveState")
      if before != "active" and after == "active":
        failures.append(f"{unit} 原本未运行却被启动: {before!r} -> {after!r}")
  return failures


def write_document(document, output):
  if os.path.exists(output):
    raise IdentityError(f"输出文件已存在, 拒绝覆盖: {output}")
  directory = os.path.dirname(os.path.abspath(output))
  os.makedirs(directory, exist_ok=True)
  with open(output, "w", encoding="utf-8") as handle:
    json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=False)
    handle.write("\n")


def main(argv):
  parser = argparse.ArgumentParser(description="发布身份取证 (只读)")
  subparsers = parser.add_subparsers(dest="command", required=True)

  static_parser = subparsers.add_parser("static", help="采集静态构建身份")
  static_parser.add_argument("--release-root", required=True)
  static_parser.add_argument("--variant", required=True,
                             choices=("noopt", "release"))
  static_parser.add_argument("--output", required=True)

  runtime_parser = subparsers.add_parser("runtime", help="采集实际在线身份")
  runtime_parser.add_argument("--expected-install", required=True)
  runtime_parser.add_argument("--output", required=True)
  runtime_parser.add_argument("--record-only", action="store_true",
                              help="仅留证, 不因不匹配返回非零 (不能用于候选验收)")
  runtime_parser.add_argument("--baseline", default=None,
                              help="先前 runtime JSON, 用于比较重启次数与服务状态")
  args = parser.parse_args(argv)
  runner = CommandRunner()
  try:
    if args.command == "static":
      document = collect_static(args.release_root, args.variant, runner)
      write_document(document, args.output)
      for failure in document["failures"]:
        print(f"静态身份未通过: {failure}", file=sys.stderr)
      print(f"静态身份已写入: {args.output} identity_ok={document['identity_ok']}")
      return 0 if document["identity_ok"] else 1

    document = collect_runtime(args.expected_install, runner)
    baseline = None
    if args.baseline:
      with open(args.baseline, "r", encoding="utf-8") as handle:
        baseline = json.load(handle)
    document["failures"] = evaluate_runtime(document, baseline)
    document["identity_ok"] = not document["failures"]
    write_document(document, args.output)
    for failure in document["failures"]:
      print(f"在线身份未通过: {failure}", file=sys.stderr)
    print(f"在线身份已写入: {args.output} identity_ok={document['identity_ok']}")
    if args.record_only:
      return 0
    return 0 if document["identity_ok"] else 1
  except IdentityError as error:
    print(f"取证失败: {error}", file=sys.stderr)
    return 2


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
