#!/usr/bin/env python3
"""Freeze a local, allowlisted USV baseline; never alter source or old baselines.

Run after sourcing the intended ROS overlays. Snapshots remain on this host.
An immutable static baseline does not establish effective runtime parameters.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys


SCHEMA = "usv-repair-baseline-v1"
PACKAGES = ("usv_mpc_cpp", "usv_rl_ros", "usv_bringup", "usv_simulation",
            "usv_planning_cpp")
SOURCE_PACKAGES = PACKAGES + ("usv_research_interfaces",)
SAFE_SUFFIXES = {".cpp", ".hpp", ".h", ".c", ".py", ".xml", ".msg",
                 ".yaml", ".json", ".md", ".txt", ".in", ".cmake"}
EXCLUDED_PARTS = {".git", "__pycache__", ".venv", "venv", "build", "log",
                  "install", "node_modules", ".sgh-research", "data"}
EXCLUDED_NAMES = {"ntrip_params.yaml", "mavros_config.yaml", "ntrip.launch.py",
                  "mavros.launch.py", "real.launch.py", "sitl.launch.py",
                  "sitl_square.yaml"}
EXACT_SOURCE = (
    "usv_mpc_ws/scripts/collect_repair_baseline.py",
    "usv_mpc_ws/scripts/check_ppo_bag.py",
    "usv_mpc_ws/scripts/check_p0_contract.py",
    "usv_mpc_ws/scripts/tests/test_collect_repair_baseline.py",
    "usv_mpc_ws/scripts/tests/test_check_ppo_bag.py",
    "usv_mpc_ws/scripts/tests/test_check_p0_contract.py",
    "usv_mpc_ws/docs/bag_recording.md", "usv_mpc_ws/docs/topic_contract.md",
    "usv_mpc_ws/docs/research/p0_data_contract.md",
    "usv_rl/usv_rl/export_policy.py", "usv_rl/usv_rl/dynamics.py",
    "usv_rl/usv_rl/env.py", "usv_rl/configs/env.yaml",
    "usv_rl/tests/test_export_scaling.py",
)
REQUIRED_SOURCE = (
    "usv_mpc_ws/scripts/collect_repair_baseline.py",
    "usv_mpc_ws/scripts/check_ppo_bag.py",
    "usv_mpc_ws/scripts/tests/test_check_ppo_bag.py",
    "usv_mpc_ws/docs/bag_recording.md",
    "usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp",
    "usv_mpc_ws/src/usv_mpc_cpp/include/usv_mpc_cpp/mpc_node.hpp",
    "usv_mpc_ws/src/usv_mpc_cpp/CMakeLists.txt",
    "usv_mpc_ws/src/usv_mpc_cpp/package.xml",
    "usv_mpc_ws/src/usv_mpc_cpp/test/test_deadline_control.cpp",
    "usv_mpc_ws/src/usv_bringup/launch/vrx.launch.py",
    "usv_mpc_ws/src/usv_bringup/config/mpc_params_vrx.yaml",
    "usv_mpc_ws/src/usv_bringup/config/usv_params_sim.yaml",
    "usv_mpc_ws/src/usv_simulation/config/vrx_model.yaml",
    "usv_mpc_ws/src/usv_rl_ros/usv_rl_ros/rl_policy_node.py",
    "usv_mpc_ws/src/usv_rl_ros/test/test_policy_units.py",
    "usv_rl/usv_rl/export_policy.py", "usv_rl/usv_rl/dynamics.py",
    "usv_rl/configs/env.yaml", "usv_rl/tests/test_export_scaling.py",
)
MODEL_ROOT = "usv_rl/models/v5/s4_dr"
MODEL_FILES = ("model.zip", "policy.onnx", "vecnormalize.pkl",
               "policy_physical_n.onnx", "policy_physical_n.manifest.json")
GENERATED_FILES = ("effective_vehicle.yaml", "model_report.json", "model.sdf")


def command(argv, cwd=None):
    """No shell, no complete environment/history capture, bounded command time."""
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=20)
        return {"argv": list(map(str, argv)), "returncode": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": list(map(str, argv)), "returncode": None,
                "stdout": "", "stderr": str(exc)}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inside(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_source_file(path, root):
    relative = path.relative_to(root)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if path.name in EXCLUDED_NAMES or path.name.startswith("."):
        return False
    if re.search(r"(secret|credential|password|private[_-]?key|token)", path.name,
                 re.IGNORECASE):
        return False
    return path.name == "CMakeLists.txt" or path.suffix in SAFE_SUFFIXES


def select_source(workspace, effective_config_dir=None):
    result = set()
    for package in SOURCE_PACKAGES:
        root = workspace / "usv_mpc_ws/src" / package
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file() and safe_source_file(path, root):
                    result.add(path)
    for relative in EXACT_SOURCE:
        path = workspace / relative
        if path.is_file():
            result.add(path)
    # Only named generated configuration; do not recurse through experiments.
    root = workspace / "usv_mpc_ws/artifacts/vrx_model"
    for name in GENERATED_FILES:
        path = root / name
        if path.is_file():
            result.add(path)
    if effective_config_dir is not None:
        if not inside(effective_config_dir, workspace):
            raise ValueError("effective_config_dir must remain inside workspace")
        for name in GENERATED_FILES:
            path = effective_config_dir / name
            if path.is_file():
                result.add(path)
    return sorted(result, key=lambda p: p.as_posix())


def file_inventory(paths, root):
    records = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        resolved = path.resolve()
        if not inside(resolved, root):
            records.append({"path": relative, "valid": False,
                            "reason": "symlink_target_outside_workspace",
                            "resolved_path": str(resolved)})
            continue
        try:
            records.append({"path": relative, "resolved_path": str(resolved),
                            "symlink": path.is_symlink(), "bytes": path.stat().st_size,
                            "sha256": digest(path), "valid": True})
        except OSError as exc:
            records.append({"path": relative, "valid": False, "reason": str(exc)})
    return records


def package_prefixes(workspace, runner=command):
    values = {}
    for package in PACKAGES:
        result = runner(["ros2", "pkg", "prefix", package], cwd=workspace)
        raw = result["stdout"].strip()
        prefix = Path(raw) if raw and "\n" not in raw else None
        expected = workspace / "usv_mpc_ws/install"
        valid = (result["returncode"] == 0 and prefix is not None and
                 prefix.is_dir() and inside(prefix, expected))
        marker = prefix / "share/ament_index/resource_index/packages" / package if prefix else None
        valid = valid and marker.is_file()
        values[package] = {"prefix": str(prefix) if prefix else None,
                           "valid": bool(valid), "lookup": result,
                           "reason": None if valid else "missing_or_wrong_active_overlay"}
    return values


def select_installed(workspace, prefixes):
    paths = set()
    for package, info in prefixes.items():
        if not info["valid"]:
            continue
        prefix = Path(info["prefix"])
        for directory in (prefix / "lib" / package, prefix / "include" / package):
            if directory.is_dir():
                for path in directory.rglob("*"):
                    if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                        paths.add(path)
        share = prefix / "share" / package
        if share.is_dir():
            for path in share.rglob("*"):
                if path.is_file() and safe_source_file(path, share):
                    paths.add(path)
        # Python installed package can be a directory symlink (rglob won't descend it).
        for site in prefix.glob("lib/python*/site-packages"):
            source = site / package
            if source.is_dir():
                for path in source.rglob("*.py"):
                    if "__pycache__" not in path.parts:
                        paths.add(path)
        for path in prefix.glob("lib/*.so*"):
            if path.is_file():
                paths.add(path)
    return sorted(paths, key=lambda p: p.as_posix())


def model_contract(workspace, records):
    manifest_path = workspace / MODEL_ROOT / "policy_physical_n.manifest.json"
    result = {"valid": False, "manifest": None, "problems": []}
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        result["manifest"] = document
    except (OSError, ValueError) as exc:
        result["problems"].append("manifest_missing_or_invalid: " + str(exc))
        return result
    expected = {"contract_version": 1, "output_unit": "N", "input_dim": 43,
                "output_dim": 2, "action_order": ["T_L", "T_R"],
                "thrust_scale_n": 25.0, "physical_low_n": [-25.0, -25.0],
                "physical_high_n": [25.0, 25.0], "normalization_embedded": True}
    for key, value in expected.items():
        if document.get(key) != value:
            result["problems"].append("contract_mismatch:" + key)
    by_name = {Path(item["path"]).name: item for item in records}
    for key, name in (("onnx_sha256", "policy_physical_n.onnx"),
                      ("source_model_sha256", "model.zip"),
                      ("source_vecnormalize_sha256", "vecnormalize.pkl")):
        if document.get(key) != by_name.get(name, {}).get("sha256"):
            result["problems"].append("asset_hash_mismatch:" + key)
    result["valid"] = not result["problems"]
    return result


def python_versions(interpreter, runner):
    script = ("import sys,json,importlib.metadata as m; "
              "names=['numpy','torch','stable-baselines3','onnx','onnxruntime','casadi','rclpy']; "
              "v={}; "
              "exec('for n in names:\\n try: v[n]=m.version(n)\\n except m.PackageNotFoundError: v[n]=None'); "
              "print(json.dumps({'executable':sys.executable,'version':sys.version,'packages':v}))")
    return runner([str(interpreter), "-c", script])


def dependencies(workspace, runner):
    pythons = []
    candidates = [Path("/usr/bin/python3"), Path(sys.executable),
                  workspace / "usv_rl/.venv/bin/python", workspace / "usv_rl/venv/bin/python",
                  workspace / ".venv/bin/python", Path.home() / "venv-ardupilot/bin/python"]
    seen = set()
    for interpreter in candidates:
        if interpreter.exists() and str(interpreter) not in seen:
            seen.add(str(interpreter))
            pythons.append({"requested_path": str(interpreter),
                            "version_probe": python_versions(interpreter, runner),
                            "runtime_interpreter_verified": False})
    acados = Path(os.environ.get("ACADOS_SOURCE_DIR", str(Path.home() / "acados")))
    acados_info = {"source_dir": str(acados), "head": runner(["git", "-C", str(acados),
                  "rev-parse", "HEAD"]), "libraries": []}
    for name in ("libacados.so", "libblasfeo.so", "libhpipm.so"):
        path = acados / "lib" / name
        if path.is_file():
            acados_info["libraries"].append({"path": str(path), "resolved_path": str(path.resolve()),
                                             "sha256": digest(path)})
    return {"python_interpreters": pythons, "acados": acados_info,
            "os_release": Path("/etc/os-release").read_text(encoding="utf-8") if Path("/etc/os-release").exists() else None,
            "ros_gazebo_packages": runner(["dpkg-query", "-W", "-f=${Package}\t${Version}\n",
                                            "ros-jazzy-ros-base", "ros-jazzy-rclcpp",
                                            "ros-jazzy-rclpy", "gz-sim8", "libgz-sim8"]),
            "gz_version": runner(["gz", "sim", "--versions"]),
            "kernel": platform.release(), "collection_python": sys.version,
            "runtime_interpreter_verified": False}


def collect(workspace, baseline_id, output_root, runner=command, after_copy=None,
            effective_config_dir=None):
    workspace = Path(workspace).resolve()
    output_root = Path(output_root).resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", baseline_id):
        raise ValueError("baseline_id must be a safe unique identifier")
    if not workspace.is_dir() or not inside(output_root, workspace):
        raise ValueError("output_root must stay within the named workspace")
    target = output_root / baseline_id
    target.mkdir(parents=True, exist_ok=False)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    problems = []
    source_paths = select_source(workspace, effective_config_dir)
    sources = file_inventory(source_paths, workspace)
    prefixes = package_prefixes(workspace, runner)
    installed_paths = select_installed(workspace, prefixes)
    installed = file_inventory(installed_paths, workspace)
    model_paths = [workspace / MODEL_ROOT / name for name in MODEL_FILES]
    models = file_inventory([p for p in model_paths if p.is_file()], workspace)
    for relative in REQUIRED_SOURCE:
        if relative not in {item["path"] for item in sources}:
            problems.append("missing_required_source:" + relative)
    for path in model_paths:
        if not path.is_file():
            problems.append("missing_required_model:" + path.relative_to(workspace).as_posix())
    for package, info in prefixes.items():
        if not info["valid"]:
            problems.append("invalid_active_package_prefix:" + package)
    mpc_prefix = prefixes["usv_mpc_cpp"]["prefix"]
    if not mpc_prefix or not (Path(mpc_prefix) / "lib/usv_mpc_cpp/mpc_node").is_file():
        problems.append("missing_installed_mpc_node")
    bringup_prefix = prefixes["usv_bringup"]["prefix"]
    if not bringup_prefix or not (Path(bringup_prefix) / "share/usv_bringup/launch/vrx.launch.py").is_file():
        problems.append("missing_installed_vrx_launch")
    rl_prefix = prefixes["usv_rl_ros"]["prefix"]
    if not rl_prefix or not (Path(rl_prefix) / "lib/usv_rl_ros/rl_policy_node").is_file():
        problems.append("missing_installed_rl_node")
    contract = model_contract(workspace, models)
    problems += contract["problems"]
    git = {}
    for label, argv in (("head", ["git", "rev-parse", "HEAD"]),
                        ("branch", ["git", "branch", "--show-current"]),
                        ("status", ["git", "status", "--short", "--untracked-files=all"]),
                        ("untracked", ["git", "ls-files", "--others", "--exclude-standard", "-z"])):
        git[label] = runner(argv, cwd=workspace)
        if git[label]["returncode"] != 0:
            problems.append("git_probe_failed:" + label)
    whitelist = [item["path"] for item in sources]
    tracked_diff = runner(["git", "diff", "--binary", "HEAD", "--", *whitelist], cwd=workspace)
    if tracked_diff["returncode"] != 0:
        problems.append("git_diff_failed")
    (target / "git_status.txt").write_text(git["status"]["stdout"], encoding="utf-8")
    (target / "tracked_changes.patch").write_text(tracked_diff["stdout"], encoding="utf-8")
    untracked = set(git["untracked"]["stdout"].split("\0"))
    selected_untracked = [item for item in sources if item["path"] in untracked]
    write_json(target / "selected_untracked_files.json", selected_untracked)
    all_records = ((sources, "source_snapshot"), (installed, "installed_snapshot"),
                   (models, "model_snapshot"))
    for records, destination_name in all_records:
        for item in records:
            if not item["valid"]:
                problems.append("invalid_file:" + item["path"])
                continue
            source = workspace / item["path"]
            destination = target / destination_name / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(source, destination)
                if digest(destination) != item["sha256"]:
                    problems.append("snapshot_hash_mismatch:" + item["path"])
            except OSError as exc:
                problems.append("snapshot_failed:" + item["path"] + ":" + str(exc))
    # Test seam exercises a real mid-collection mutation without mocking hashes.
    if after_copy is not None:
        after_copy()
    sources_after = file_inventory(select_source(workspace, effective_config_dir), workspace)
    installed_after = file_inventory(select_installed(workspace, prefixes), workspace)
    models_after = file_inventory([p for p in model_paths if p.is_file()], workspace)
    for label, before, after in (("source", sources, sources_after),
                                 ("installed", installed, installed_after),
                                 ("models", models, models_after)):
        if before != after:
            problems.append(label + "_changed_during_collection")
    git_after = {label: runner(info["argv"], cwd=workspace)
                 for label, info in git.items() if label != "untracked"}
    # Output files are intentionally excluded from the status stability comparison.
    def filtered_status(value):
        return [line for line in value.splitlines() if line[3:] in whitelist]
    for label in ("head", "branch"):
        if git[label]["stdout"] != git_after[label]["stdout"]:
            problems.append("git_" + label + "_changed_during_collection")
    if filtered_status(git["status"]["stdout"]) != filtered_status(git_after["status"]["stdout"]):
        problems.append("selected_git_status_changed_during_collection")
    diff_after = runner(tracked_diff["argv"], cwd=workspace)
    if tracked_diff["stdout"] != diff_after["stdout"] or diff_after["returncode"] != 0:
        problems.append("tracked_diff_changed_during_collection")
    # Resolve installed headers/launch back to matching source bytes where possible.
    correspondence = []
    source_by_path = {item["path"]: item for item in sources}
    for item in installed:
        for package in PACKAGES:
            prefix = prefixes[package]["prefix"]
            if not prefix:
                continue
            try:
                rel = (workspace / item["path"]).relative_to(Path(prefix))
            except ValueError:
                continue
            if rel.parts[:2] == ("share", package):
                source_rel = "usv_mpc_ws/src/" + package + "/" + Path(*rel.parts[2:]).as_posix()
            elif rel.parts[:2] == ("include", package):
                source_rel = "usv_mpc_ws/src/" + package + "/include/" + rel.as_posix()[8:]
            else:
                continue
            original = source_by_path.get(source_rel)
            if original:
                match = item.get("sha256") == original.get("sha256")
                correspondence.append({"source": source_rel, "installed": item["path"], "hash_equal": match})
                if not match:
                    problems.append("source_installed_mismatch:" + source_rel)
    effective = [item for item in sources if Path(item["path"]).name in GENERATED_FILES]
    config_dir = target / "effective_config"
    config_dir.mkdir()
    write_json(config_dir / "configuration_sources.json", {
        "static_configuration_files": [item for item in sources if item["path"].endswith(".yaml")],
        "generated_configuration": effective,
        "explicit_effective_config_dir": str(effective_config_dir) if effective_config_dir else None,
        "generated_configuration_evidence_kind": "static/prior-run source; current runtime loading unverified",
        "controller_nominal_plant_actual_relation": "shared effective_vehicle launch source; runtime loading unverified",
        "runtime_effective_verified": False,
        "runtime_parameters": None,
        "launch_arguments": None,
        "time_contract": {"compute_clock": "steady", "physical_clock": "explicit /clock observations",
                          "runtime_use_sim_time_verified": False}})
    versions_dir = target / "dependency_versions"
    versions_dir.mkdir()
    write_json(versions_dir / "versions.json", dependencies(workspace, runner))
    write_json(target / "source_hashes.json", sources)
    write_json(target / "installed_hashes.json", {"packages": prefixes, "files": installed,
                                                    "source_correspondence": correspondence})
    write_json(target / "model_assets.json", {"files": models, "contract": contract,
                                              "restore_strategy": "local model_snapshot; no assets exported"})
    integrity = {"frozen_baseline_verified": not problems,
                 "source_and_installed_stable": sources == sources_after and installed == installed_after,
                 "models_stable": models == models_after,
                 "runtime_effective_verified": False, "problems": problems,
                 "snapshots_recoverable": not any("snapshot" in p or "invalid_file" in p for p in problems)}
    write_json(target / "integrity_check.json", integrity)
    boot = Path("/proc/sys/kernel/random/boot_id")
    manifest = {"schema_version": SCHEMA, "baseline_id": baseline_id,
                "created_utc": started, "completed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "workspace": str(workspace), "host": platform.node(),
                "boot_id": boot.read_text().strip() if boot.exists() else None,
                "steady_clock_domain": "same host and boot only", "git": git,
                "dirty": bool(git["status"]["stdout"].strip()),
                "tracked_patch_scope": "only source allowlist; unrelated dirty files are not copied",
                "allowlist": {"source_packages": SOURCE_PACKAGES, "exact_source_files": EXACT_SOURCE,
                              "source_suffixes": sorted(SAFE_SUFFIXES), "model_files": MODEL_FILES,
                              "excluded_names": sorted(EXCLUDED_NAMES),
                              "excluded_categories": ["credentials/private keys/environment/history", "bags",
                                                      "existing baselines/experiments/backups", "build/log trees"]},
                "source_count": len(sources), "installed_count": len(installed),
                "model_count": len(models), "runtime_effective_verified": False,
                "missing_generated_config_is_unknown": not bool(effective),
                "runtime_evidence_location": "first run_context; frozen manifest is not amended",
                "integrity": integrity}
    write_json(target / "baseline_manifest.json", manifest)
    return target, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--effective-config-dir", type=Path,
                        help="Only named generated files; recorded as static/prior-run evidence")
    args = parser.parse_args(argv)
    try:
        target, manifest = collect(args.workspace, args.baseline_id,
                                   args.output_root or args.workspace / ".sgh-research/baselines",
                                   effective_config_dir=args.effective_config_dir)
    except (ValueError, OSError) as exc:
        print(json.dumps({"frozen_baseline_verified": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"baseline_directory": str(target), "baseline_id": args.baseline_id,
                      **manifest["integrity"]}, ensure_ascii=False))
    return 0 if manifest["integrity"]["frozen_baseline_verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
