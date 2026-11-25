#!/usr/bin/env python3
"""Freeze the Scheme-A execution-closure run identity; sources are never altered.

Modes
-----
--source-only
    Snapshot the current Scheme-A research execution chain sources (package
    closure of usv_acados/usv_mpc/usv_nmpc/usv_research_safety_cpp/
    usv_research_interfaces/usv_bringup plus transitive workspace deps, both
    generated-code variants included).  No claim is made about any install
    tree.
--build-base/--install-base/--source-manifest
    Bind a real colcon build/install pair to a prior --source-only capture,
    item by item.  If any source changed after the build inputs were frozen
    the run refuses to claim build/source consistency and exits non-zero.

The historical R40 archive is only cross-checked (final index digest, signed
flag); it is never rewritten and this tool never claims the current tree is
the 2026-11-13 historical binary build.
"""

import argparse
import datetime
import json
import os
import platform
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_repair_baseline as repair  # noqa: E402  utilities only, never collect()

SCHEMA = "scheme-a-execution-closure-baseline-v1"
SEED_PACKAGES = ("usv_acados", "usv_mpc", "usv_nmpc", "usv_research_safety_cpp",
                 "usv_research_interfaces", "usv_bringup")
GENERATED_MODELS = ("kinematic", "dynamic")
ARCHIVE_MANIFEST_NAME = "S2G.rev08.delivery_manifest.json"
ARCHIVE_FINAL_INDEX_SHA256 = ("c2f3994febf74592f532332f7b551ea46cabaeb2e"
                              "433b6f7a346ac4733848be4")
# 运行时脚本的真实路径。闭环 runner/checker 在包内 scripts/ 下，不在这里；
# 路径写错会让基线"少绑定一个关键脚本"却不报错 —— 必须显式失败。
RUNTIME_SCRIPTS = (
    "usv_mpc_ws/scripts/capture_scheme_a_baseline.py",
    "usv_mpc_ws/src/usv_research_safety_cpp/scripts/run_scheme_a_closed_loop.py",
    "usv_mpc_ws/src/usv_research_safety_cpp/scripts/check_scheme_a_closed_loop.py",
    "usv_mpc_ws/src/usv_research_safety_cpp/test_capture_scheme_a_baseline.py",
)
# (package, path relative to that package's install prefix)
EXPECTED_INSTALL_NODES = (
    ("usv_research_safety_cpp", "lib/usv_research_safety_cpp/p1_solver_worker"),
    ("usv_research_safety_cpp", "lib/usv_research_safety_cpp/p1_regulator"),
    ("usv_research_safety_cpp", "lib/usv_research_safety_cpp/p1_contract_validate"),
    ("usv_research_safety_cpp", "lib/usv_research_safety_cpp/p1_x86_plant"),
    ("usv_mpc", "lib/usv_mpc/mpc_node"),
    ("usv_research_interfaces", "lib/libusv_research_interfaces__rosidl_typesupport_cpp.so"),
)
CMAKE_CACHE_KEYS = ("CMAKE_BUILD_TYPE", "CMAKE_GENERATOR", "CMAKE_INSTALL_PREFIX",
                    "CMAKE_CXX_COMPILER", "CMAKE_C_COMPILER",
                    "CMAKE_CXX_FLAGS", "CMAKE_CXX_FLAGS_RELEASE",
                    "CMAKE_C_FLAGS", "CMAKE_C_FLAGS_RELEASE",
                    "CMAKE_EXPORT_COMPILE_COMMANDS", "USV_RESEARCH_TEST_SEAMS")
DEPEND_TAGS = ("build_depend", "buildtool_depend", "build_export_depend",
               "exec_depend", "run_depend", "test_depend", "depend")


def build_type(package_dir):
    """ament_python 包没有 CMake 构建记录；把它们当作 CMake 包要求会凭空制造失败。"""
    manifest = package_dir / "package.xml"
    if not manifest.is_file():
        return None
    try:
        tree = ET.parse(str(manifest))
    except (OSError, ValueError):
        return None
    for element in tree.iter():
        if element.tag.endswith("build_type"):
            return (element.text or "").strip()
    return "ament_cmake"


def package_name(package_dir):
    manifest = package_dir / "package.xml"
    if not manifest.is_file():
        return None
    try:
        tree = ET.parse(str(manifest))
    except (OSError, ValueError):
        return None
    for element in tree.iter():
        if element.tag.rsplit("}", 1)[-1] == "name" and element.text:
            return element.text.strip()
    return None


def workspace_dependencies(workspace):
    """Map every workspace package to its intra-workspace dependencies."""
    source_root = workspace / "usv_mpc_ws/src"
    result = {}
    for directory in sorted(p for p in source_root.iterdir() if p.is_dir()):
        name = package_name(directory)
        if name:
            result[name] = directory
    dependencies = {}
    for name, directory in result.items():
        intra = set()
        try:
            tree = ET.parse(str(directory / "package.xml"))
        except (OSError, ValueError):
            dependencies[name] = intra
            continue
        for tag in DEPEND_TAGS:
            for element in tree.iter():
                if element.tag.rsplit("}", 1)[-1] == tag and element.text:
                    if element.text.strip() in result:
                        intra.add(element.text.strip())
        dependencies[name] = intra
    return dependencies


def closure_packages(workspace):
    dependencies = workspace_dependencies(workspace)
    missing = [p for p in SEED_PACKAGES if p not in dependencies]
    if missing:
        raise ValueError("missing seed packages in workspace: " + ", ".join(missing))
    closure, stack = set(SEED_PACKAGES), list(SEED_PACKAGES)
    while stack:
        current = stack.pop()
        for dep in dependencies.get(current, ()):
            if dep not in closure:
                closure.add(dep)
                stack.append(dep)
    return sorted(closure), dependencies


def select_scheme_a_sources(workspace, packages):
    result = set()
    for package in packages:
        root = workspace / "usv_mpc_ws/src" / package
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and repair.safe_source_file(path, root):
                result.add(path)
    missing = []
    for relative in RUNTIME_SCRIPTS:
        path = workspace / relative
        if path.is_file():
            result.add(path)
        else:
            missing.append(relative)
    if missing:
        raise ValueError(f"runtime scripts missing: {', '.join(missing)}")
    return sorted(result, key=lambda p: p.as_posix())


def archive_identity(archive_root):
    record = {"archive_root": str(archive_root), "problems": []}
    manifest_path = Path(archive_root) / ARCHIVE_MANIFEST_NAME
    record["manifest_path"] = str(manifest_path)
    if not manifest_path.is_file():
        record["problems"].append("archive_manifest_missing:" + str(manifest_path))
        return record
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        record["problems"].append("archive_manifest_invalid:" + str(exc))
        return record
    record["manifest_sha256"] = repair.digest(manifest_path)
    record["schema"] = document.get("schema")
    record["final_index_sha256"] = document.get("final_index_sha256")
    record["signed"] = document.get("signed")
    record["obligations"] = document.get("obligations")
    record["cases"] = document.get("cases")
    if document.get("final_index_sha256") != ARCHIVE_FINAL_INDEX_SHA256:
        record["problems"].append("archive_final_index_sha256_mismatch")
    if document.get("signed") is not False:
        record["problems"].append("archive_signed_flag_unexpected")
    record["note"] = ("historical R40 delivery identity, read-only cross-check; "
                      "this baseline is a new run identity and does not re-certify it")
    return record


def resolve_prefixes(packages, install_base=None):
    """ros2 pkg prefix for every closure package; flag foreign overlays."""
    prefixes = {}
    for package in packages:
        result = repair.command(["ros2", "pkg", "prefix", package])
        raw = result["stdout"].strip()
        prefix = Path(raw) if raw and "\n" not in raw else None
        info = {"prefix": str(prefix) if prefix else None, "lookup": result}
        if install_base is None:
            # source-only mode: no workspace overlay may be active at all
            if prefix is not None:
                info["valid"] = False
                info["reason"] = "external_overlay_active"
            elif result["returncode"] not in (0, 1):
                info["valid"] = False
                info["reason"] = "ros2_prefix_lookup_failed"
            else:
                info["valid"] = True
                info["reason"] = None
        else:
            marker = (prefix / "share/ament_index/resource_index/packages"
                      / package) if prefix else None
            valid = (result["returncode"] == 0 and prefix is not None and
                     prefix.is_dir() and repair.inside(prefix, install_base) and
                     marker is not None and marker.is_file())
            info["valid"] = bool(valid)
            info["reason"] = None if valid else "missing_or_wrong_active_overlay"
        prefixes[package] = info
    return prefixes


def external_library_identity(runner=repair.command):
    acados = Path(os.environ.get("ACADOS_SOURCE_DIR", str(Path.home() / "acados")))
    record = {"source_dir": str(acados),
              "head": runner(["git", "-C", str(acados), "rev-parse", "HEAD"]),
              "libraries": []}
    for name in ("libacados.so", "libblasfeo.so", "libhpipm.so"):
        path = acados / "lib" / name
        entry = {"requested_path": str(path)}
        if path.is_file():
            entry.update({"resolved_path": str(path.resolve()),
                          "sha256": repair.digest(path)})
        else:
            entry["missing"] = True
        record["libraries"].append(entry)
    return record


def _first_match(path, pattern):
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")[:200000]
    match = re.search(pattern, text, re.DOTALL)
    return match.group(0) if match else None


def toolchain_identity():
    return {
        "ros_distro": os.environ.get("ROS_DISTRO"),
        "os_release": (Path("/etc/os-release").read_text(encoding="utf-8")
                       if Path("/etc/os-release").exists() else None),
        "kernel": platform.release(),
        "host": platform.node(),
        "collection_python": sys.version,
        "colcon": repair.command(["colcon", "version-check"]),
        "rosbag2_py": repair.command(["python3", "-c", "import rosbag2_py"]),
        "eigen_version": _first_match(
            Path("/usr/include/eigen3/Eigen/src/Core/util/Macros.h"),
            r"#define EIGEN_WORLD_VERSION (\d+).*?#define EIGEN_MAJOR_VERSION (\d+)"),
        "nlohmann_json_version": _first_match(
            Path("/usr/include/nlohmann/json.hpp"), r"NLOHMANN_JSON_VERSION_MAJOR\s+(\d+)"),
    }


def copy_snapshot(records, workspace, destination_root, problems):
    for item in records:
        if not item["valid"]:
            problems.append("invalid_file:" + item["path"])
            continue
        source = workspace / item["path"]
        destination = destination_root / item["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source, destination)
            if repair.digest(destination) != item["sha256"]:
                problems.append("snapshot_hash_mismatch:" + item["path"])
        except OSError as exc:
            problems.append("snapshot_failed:" + item["path"] + ":" + str(exc))


def git_probes(workspace, whitelist, runner=repair.command):
    git = {}
    for label, argv in (("head", ["git", "rev-parse", "HEAD"]),
                        ("branch", ["git", "branch", "--show-current"]),
                        ("status", ["git", "status", "--short", "--untracked-files=all"]),
                        ("untracked", ["git", "ls-files", "--others",
                                       "--exclude-standard", "-z"])):
        git[label] = runner(argv, cwd=workspace)
    diff = runner(["git", "diff", "--binary", "HEAD", "--", *whitelist], cwd=workspace)
    return git, diff


def git_stability(workspace, git, diff, whitelist, runner=repair.command):
    problems = []
    for label in ("head", "branch"):
        after = runner(git[label]["argv"], cwd=workspace)
        if git[label]["stdout"] != after["stdout"]:
            problems.append("git_" + label + "_changed_during_collection")

    def filtered(value):
        return [line for line in value.splitlines() if line[3:] in whitelist]

    after_status = runner(git["status"]["argv"], cwd=workspace)
    if filtered(git["status"]["stdout"]) != filtered(after_status["stdout"]):
        problems.append("selected_git_status_changed_during_collection")
    diff_after = runner(diff["argv"], cwd=workspace)
    if diff["stdout"] != diff_after["stdout"] or diff_after["returncode"] != 0:
        problems.append("tracked_diff_changed_during_collection")
    return problems


def read_cmake_cache(path):
    values = {}
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("//") or not line.strip():
            continue
        key, sep, value = line.partition(":=")
        if sep and key in CMAKE_CACHE_KEYS:
            values[key] = value
    return values


def root_identity(path):
    path = Path(path).resolve()
    record = {"path": str(path), "exists": path.is_dir()}
    if record["exists"]:
        stat = path.stat()
        record.update({"resolved": str(path), "device": stat.st_dev, "inode": stat.st_ino})
    return record


def ldd_bindings(executables):
    bindings = []
    for executable in executables:
        result = repair.command(["ldd", str(executable)])
        lines = [line.strip() for line in result["stdout"].splitlines()
                 if re.search(r"(acados|blasfeo|hpipm)", line)]
        bindings.append({"executable": str(executable),
                         "returncode": result["returncode"],
                         "resolved_native_libraries": lines})
    return bindings


def source_manifest_check(sources, source_manifest_path):
    problems = []
    try:
        prior_document = json.loads(Path(source_manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return ["source_manifest_unreadable:" + str(exc)], None
    if prior_document.get("schema") != SCHEMA:
        return ["source_manifest_schema_mismatch"], None
    prior = {record["path"]: record for record in prior_document.get("records", [])}
    current = {record["path"]: record for record in sources}
    for path, record in prior.items():
        if path not in current:
            problems.append("source_removed_since_build_input:" + path)
            continue
        if (current[path].get("sha256") != record.get("sha256") or
                current[path].get("bytes") != record.get("bytes")):
            problems.append("source_changed_since_build_input:" + path)
    for path in current:
        if path not in prior:
            problems.append("source_added_since_build_input:" + path)
    return problems, prior_document


def installed_source_correspondence(installed, sources, prefixes):
    correspondence = []
    problems = []
    source_by_path = {item["path"]: item for item in sources}
    for item in installed:
        for package, info in prefixes.items():
            prefix = info.get("prefix")
            if not prefix:
                continue
            try:
                rel = Path(item["path"]).relative_to(Path(prefix))
            except ValueError:
                continue
            parts = rel.parts
            if parts[:2] == ("share", package):
                source_rel = "usv_mpc_ws/src/" + package + "/" + Path(*parts[2:]).as_posix()
            elif parts[:2] == ("include", package):
                source_rel = ("usv_mpc_ws/src/" + package + "/include/" +
                              Path(*parts[2:]).as_posix())
            else:
                continue
            original = source_by_path.get(source_rel)
            if original:
                match = item.get("sha256") == original.get("sha256")
                correspondence.append({"source": source_rel, "installed": item["path"],
                                      "hash_equal": match})
                if not match:
                    problems.append("source_installed_mismatch:" + source_rel)
    return correspondence, problems


def capture(args):
    workspace = Path(args.workspace).resolve()
    out = Path(args.out).resolve()
    archive_root = Path(args.archive_root).resolve()
    if not workspace.is_dir():
        raise ValueError("workspace is not a directory: " + str(workspace))
    if out.exists():
        raise ValueError("output directory must be brand new, refusing to touch: " + str(out))
    if not archive_root.is_dir():
        raise ValueError("archive root is not a directory: " + str(archive_root))
    if bool(args.source_only) == bool(args.build_base or args.install_base or
                                      args.source_manifest):
        raise ValueError("choose exactly one mode: --source-only or "
                         "--build-base/--install-base/--source-manifest")
    built_mode = not args.source_only
    if built_mode and not (args.build_base and args.install_base and args.source_manifest):
        raise ValueError("built mode requires --build-base, --install-base and "
                         "--source-manifest together")

    out.mkdir(parents=True, exist_ok=False)
    problems = []
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    packages, _dependencies = closure_packages(workspace)

    # --- archive cross-check (both modes) ---
    archive = archive_identity(archive_root)
    problems += ["archive:" + p for p in archive["problems"]]
    repair.write_json(out / "archive_identity.json", archive)

    # --- source selection and requirements ---
    source_paths = select_scheme_a_sources(workspace, packages)
    sources = repair.file_inventory(source_paths, workspace)
    source_by_path = {item["path"]: item for item in sources}
    for package in SEED_PACKAGES:
        prefix = "usv_mpc_ws/src/" + package + "/"
        if prefix + "package.xml" not in source_by_path:
            problems.append("missing_required_source:" + prefix + "package.xml")
        if (prefix + "CMakeLists.txt" not in source_by_path and
                prefix + "setup.py" not in source_by_path):
            problems.append("missing_required_source:" + prefix +
                            "CMakeLists.txt-or-setup.py")
    if "usv_mpc_ws/scripts/capture_scheme_a_baseline.py" not in source_by_path:
        problems.append("missing_required_source:usv_mpc_ws/scripts/capture_scheme_a_baseline.py")
    for model in GENERATED_MODELS:
        directory = workspace / "usv_mpc_ws/src/usv_acados/acados_generated" / model
        generated = [item for item in sources
                     if item["path"].startswith(
                         "usv_mpc_ws/src/usv_acados/acados_generated/" + model + "/")]
        if not directory.is_dir() or not generated:
            problems.append("missing_generated_code:" + model)

    # --- overlay / prefix resolution ---
    install_base = Path(args.install_base).resolve() if built_mode else None
    prefixes = resolve_prefixes(packages, install_base)
    for package, info in prefixes.items():
        if not info["valid"]:
            problems.append("invalid_active_package_prefix:" + package + ":" +
                            str(info.get("reason")))
    if built_mode:
        for package, node in EXPECTED_INSTALL_NODES:
            prefix = prefixes[package].get("prefix")
            if not prefix or not (Path(prefix) / node).is_file():
                problems.append("missing_expected_install_node:" + package + ":" + node)

    # --- git facts (read-only) ---
    whitelist = [item["path"] for item in sources]
    git, tracked_diff = git_probes(workspace, whitelist)
    if git["head"]["returncode"] != 0:
        problems.append("git_probe_failed:head")
    (out / "git_status.txt").write_text(git["status"]["stdout"], encoding="utf-8")
    (out / "tracked_changes.patch").write_text(tracked_diff["stdout"], encoding="utf-8")
    untracked = set(git["untracked"]["stdout"].split("\0"))
    repair.write_json(out / "selected_untracked_files.json",
                      [item for item in sources if item["path"] in untracked])

    # --- built mode: bind sources to the frozen build inputs ---
    prior_document = None
    if built_mode:
        manifest_problems, prior_document = source_manifest_check(sources,
                                                                  args.source_manifest)
        problems += manifest_problems

    # --- copy source snapshot, then verify stability ---
    copy_snapshot(sources, workspace, out / "source_snapshot", problems)
    sources_after = repair.file_inventory(select_scheme_a_sources(workspace, packages),
                                          workspace)
    if sources != sources_after:
        problems.append("source_changed_during_collection")

    installed = []
    correspondence = []
    build_binding = None
    if built_mode:
        build_base = Path(args.build_base).resolve()
        install_base = Path(args.install_base).resolve()
        installed_paths = repair.select_installed(workspace, prefixes)
        installed = repair.file_inventory(installed_paths, workspace)
        copy_snapshot(installed, workspace, out / "installed_snapshot", problems)
        correspondence, correspondence_problems = installed_source_correspondence(
            installed, sources, prefixes)
        problems += correspondence_problems
        build_binding = {
            "build_root": root_identity(build_base),
            "install_root": root_identity(install_base),
            "source_manifest": str(Path(args.source_manifest).resolve()),
            "source_manifest_sha256": repair.digest(Path(args.source_manifest)),
            "per_package": {},
            "native_library_bindings": [],
        }
        for package in packages:
            entry = {"prefix": prefixes[package].get("prefix")}
            cache_path = build_base / package / "CMakeCache.txt"
            entry["cmake_cache_exists"] = cache_path.is_file()
            entry["cmake_cache_values"] = read_cmake_cache(cache_path)
            if cache_path.is_file():
                destination = out / "build_records" / package / "CMakeCache.txt"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cache_path, destination)
                entry["cmake_cache_sha256"] = repair.digest(destination)
            commands_path = build_base / package / "compile_commands.json"
            entry["compile_commands_exists"] = commands_path.is_file()
            if commands_path.is_file():
                destination = out / "build_records" / package / "compile_commands.json"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(commands_path, destination)
                entry["compile_commands_sha256"] = repair.digest(destination)
            kind = build_type(workspace / "usv_mpc_ws/src" / package)
            entry["build_type"] = kind
            # 只有 CMake 包才有 CMakeCache；python 包的真实记录是 setup.py 的产物。
            if not entry["cmake_cache_exists"] and kind != "ament_python":
                problems.append("missing_build_record:" + package + ":CMakeCache.txt")
            build_binding["per_package"][package] = entry
        executables = []
        safety_lib = Path(prefixes["usv_research_safety_cpp"]["prefix"]) / \
            "lib/usv_research_safety_cpp"
        if safety_lib.is_dir():
            executables = sorted(p for p in safety_lib.iterdir() if p.is_file())
        mpc_node = Path(prefixes["usv_mpc"]["prefix"]) / "lib/usv_mpc/mpc_node"
        if mpc_node.is_file():
            executables.append(mpc_node)
        build_binding["native_library_bindings"] = ldd_bindings(executables)
        installed_after = repair.file_inventory(
            repair.select_installed(workspace, prefixes), workspace)
        if installed != installed_after:
            problems.append("installed_changed_during_collection")

    # --- environment / external library identity ---
    repair.write_json(out / "dependency_versions.json", {
        "acados": external_library_identity(),
        "toolchain": toolchain_identity(),
        "environment": {"ROS_DISTRO": os.environ.get("ROS_DISTRO"),
                        "ACADOS_SOURCE_DIR": os.environ.get("ACADOS_SOURCE_DIR"),
                        "ROS_LOCALHOST_ONLY": os.environ.get("ROS_LOCALHOST_ONLY"),
                        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS")},
    })

    # --- git stability after all copies ---
    problems += git_stability(workspace, git, tracked_diff, whitelist)

    # --- outputs ---
    repair.write_json(out / "source_hashes.json", {
        "schema": SCHEMA, "mode": "source-only" if not built_mode else "built",
        "captured_utc": started, "packages": packages, "records": sources})
    if built_mode:
        repair.write_json(out / "installed_hashes.json", {
            "packages": prefixes, "files": installed,
            "source_correspondence": correspondence,
            "binary_source_build_verified": not problems,
            "binary_source_build_evidence":
                "CMakeCache/compile_commands/install prefixes bound to a matched "
                "source manifest; install hashes alone are not treated as build proof"})
        repair.write_json(out / "build_binding.json", build_binding)
    integrity = {
        "frozen_baseline_verified": not problems,
        "mode": "source-only" if not built_mode else "built",
        "claims_install_consistency": bool(built_mode and not problems),
        "problems": problems,
        "sources_stable": sources == sources_after,
    }
    repair.write_json(out / "integrity_check.json", integrity)
    manifest = {
        "schema_version": SCHEMA,
        "created_utc": started,
        "completed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "workspace": str(workspace), "host": platform.node(),
        "mode": "source-only" if not built_mode else "built",
        "identity_scope": ("current tree snapshot for the Scheme-A execution-closure "
                           "run; NOT the 2026-11-13 historical binary build and not a "
                           "re-certification of the R40 archive"),
        "packages": packages, "seed_packages": list(SEED_PACKAGES),
        "source_count": len(sources),
        "archive": {"root": str(archive_root),
                    "final_index_sha256": archive.get("final_index_sha256"),
                    "signed": archive.get("signed"),
                    "manifest_sha256": archive.get("manifest_sha256")},
        "git": {label: {"returncode": git[label]["returncode"],
                        "stdout": git[label]["stdout"],
                        "stderr": git[label]["stderr"]}
                for label in ("head", "branch", "status")},
        "dirty": bool(git["status"]["stdout"].strip()),
        "uncommitted_files_captured_by_content": True,
        "runtime_scripts_expected": list(RUNTIME_SCRIPTS),
        "built_mode": ({"build_root": str(Path(args.build_base).resolve()),
                        "install_root": str(Path(args.install_base).resolve()),
                        "source_manifest": str(Path(args.source_manifest).resolve()),
                        "source_manifest_sha256": repair.digest(Path(args.source_manifest))}
                       if built_mode else None),
        "integrity": integrity,
    }
    repair.write_json(out / "baseline_manifest.json", manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--build-base")
    parser.add_argument("--install-base")
    parser.add_argument("--source-manifest")
    parser.add_argument("--archive-root", required=True)
    args = parser.parse_args(argv)
    try:
        manifest = capture(args)
    except (ValueError, OSError) as exc:
        print(json.dumps({"frozen_baseline_verified": False, "error": str(exc)}),
              file=sys.stderr)
        return 2
    print(json.dumps({"baseline_directory": str(Path(args.out).resolve()),
                      **manifest["integrity"]}, ensure_ascii=False))
    return 0 if manifest["integrity"]["frozen_baseline_verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
