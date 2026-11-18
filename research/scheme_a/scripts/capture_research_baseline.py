#!/usr/bin/env python3
"""Capture the Scheme-A GP + PPO research baseline without altering sources.

Outputs into a brand-new `--out` directory:
  - `source_hashes.json` (with `schema` and `records`, compatible with
    `run_scheme_a_closed_loop.py` / `check_scheme_a_closed_loop.py`)
  - `asset_manifest.json` (external `acados` libs, `acados_generated` codegen,
    frozen `v5/s4_dr` PPO artifacts, cross-worktree RL files, parent evidence)
  - `baseline.json` (git provenance, Python toolchains, optional build/install
    overlay binding & `USV_RESEARCH_TEST_SEAMS=OFF` verification, integrity check)
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

SOURCE_HASHES_SCHEMA = "scheme-a-execution-closure-baseline-v1"
BASELINE_SCHEMA = "scheme-a-gp-ppo-baseline-v1"
ASSET_MANIFEST_SCHEMA = "scheme-a-gp-ppo-asset-manifest-v1"

EXPECTED_WORKTREE_PACKAGES = (
    "usv_acados",
    "usv_bringup",
    "usv_nmpc",
    "usv_research_interfaces",
    "usv_research_safety_cpp",
)
GENERATED_MODELS = ("kinematic", "dynamic")
SAFE_SUFFIXES = {
    ".cpp", ".hpp", ".h", ".c", ".py", ".xml", ".msg",
    ".idl", ".yaml", ".json", ".md", ".txt", ".in", ".cmake", ".sh",
}
EXCLUDED_PARTS = {
    ".git", "__pycache__", ".venv", "venv", "build", "log",
    "install", "node_modules", ".pytest_cache",
}
EXCLUDED_NAMES = {"ntrip_params.yaml"}

FROZEN_RL_FILES = (
    "policy_physical_n.onnx",
    "policy_physical_n.manifest.json",
    "model.zip",
    "vecnormalize.pkl",
    "policy.onnx",
)
EXPECTED_V5_DIGESTS = {
    "policy_physical_n.onnx":
        "ff60e0f70a142dc0c76ac0e1b8e1d113bcff892d7999fad9ef41cf5a83147278",
    "model.zip":
        "85c6c573fa880695de1c6173c5e7e75c1702c5f1306415d91b39d2a9512c7220",
    "vecnormalize.pkl":
        "2be84c0fcaf992a52f1d9a2a3d4b997d8586951c1b9c9caba1d67badce2d769e",
}
RL_SOURCE_REFS = (
    "usv_rl/usv_rl/envs/usv_tracking_env.py",
    "usv_rl/usv_rl/observation.py",
    "usv_rl/usv_rl/dynamics.py",
    "usv_rl/usv_rl/export_policy.py",
    "usv_rl/tests/test_obs_equivalence.py",
    "usv_rl/tests/test_env_api.py",
    "usv_rl/tests/test_dynamics_vs_cpp.py",
    "usv_mpc_ws/src/usv_rl_ros/usv_rl_ros/rl_policy_node.py",
    "usv_mpc_ws/src/usv_rl_ros/test/test_policy_units.py",
)
PARENT_EVIDENCES = (
    (
        "/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物/"
        "scheme-a-b2-dryrun-20261117T1010Z-results/RESULTS.json",
        "21e0758040ee404fd2afe7a4184e61a03e50e179ecfa0acb19fb4237e8736566",
    ),
    (
        "/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物/"
        "scheme-a-b2-dryrun-20261117T1010Z-results.readback.json",
        "461c2d4518df05773865853f7a14fc2dfdeeb068255f8a4c8279c4a1fa6fdca1",
    ),
    (
        "/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物/"
        "scheme-a-bench-20261117T030458Z-results/RESULTS.json",
        "7263f610cce1a23a9ba9fdce54e54a707a61a487848f79067e97372597634ea6",
    ),
    (
        "/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物/"
        "scheme-a-b1-seams-off-20261117T071005Z-results.readback.json",
        "6cc75c65531c69ba18474c8cbc88bf4b2eff57cfdd3684cb48418fd45377197d",
    ),
    (
        "/home/trevor/Documents/Codex/2026-11-14/home-trevor-usv-home-trevor-mpc/"
        "outputs/方案A_GP与PPO可行性核查回执_2026-11-16.json",
        "c5dd3ed11ad72b0fdc4d9704b53de599dd5393b221445678e2f89922e7dbf550",
    ),
)
CMAKE_CACHE_KEYS = (
    "CMAKE_BUILD_TYPE",
    "CMAKE_CXX_COMPILER",
    "CMAKE_C_COMPILER",
    "Python3_EXECUTABLE",
    "USV_RESEARCH_TEST_SEAMS",
    "BUILD_TESTING",
)
EXPECTED_INSTALL_BINARIES = (
    ("usv_research_safety_cpp", "lib/usv_research_safety_cpp/p1_solver_worker"),
    ("usv_research_safety_cpp", "lib/usv_research_safety_cpp/p1_regulator"),
    ("usv_research_safety_cpp", "lib/usv_research_safety_cpp/p1_contract_validate"),
    ("usv_research_safety_cpp", "lib/usv_research_safety_cpp/p1_x86_plant"),
    ("usv_research_interfaces", "lib/libusv_research_interfaces__rosidl_typesupport_cpp.so"),
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run_cmd(argv: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> dict:
    try:
        res = subprocess.run(
            argv, cwd=cwd, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
        )
        return {
            "argv": list(map(str, argv)),
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": list(map(str, argv)), "returncode": None, "stdout": "", "stderr": str(exc)}


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_source_file(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return False
    if path.name in EXCLUDED_NAMES or path.name.startswith("."):
        return False
    if re.search(r"(secret|credential|password|private[_-]?key|token)", path.name, re.IGNORECASE):
        return False
    return path.name == "CMakeLists.txt" or path.suffix in SAFE_SUFFIXES


def collect_worktree_sources(workspace: Path) -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    scan_roots = (
        workspace / "research/scheme_a/src",
        workspace / "research/scheme_a/scripts",
        workspace / "research/scheme_a/learning",
        workspace / "src/usv_bringup",
        workspace / "deploy/scheme_a_commissioning",
    )
    selected: set[Path] = set()
    for root in scan_roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and safe_source_file(path, root):
                selected.add(path)
    records = []
    for path in sorted(selected, key=lambda p: p.as_posix()):
        rel = path.relative_to(workspace).as_posix()
        resolved = path.resolve()
        if not inside(resolved, workspace):
            records.append({"path": rel, "valid": False, "reason": "symlink_outside_workspace",
                            "resolved_path": str(resolved)})
            problems.append("invalid_source_symlink:" + rel)
            continue
        records.append({
            "path": rel,
            "resolved_path": str(resolved),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "symlink": path.is_symlink(),
            "valid": True,
        })
    for pkg in ("usv_acados", "usv_nmpc", "usv_research_interfaces", "usv_research_safety_cpp"):
        rel = f"research/scheme_a/src/{pkg}/package.xml"
        if not (workspace / rel).is_file():
            problems.append("missing_package:" + rel)
    if not (workspace / "src/usv_bringup/package.xml").is_file():
        problems.append("missing_package:src/usv_bringup/package.xml")
    return records, problems


def git_info(repo: Path) -> dict:
    if not repo.exists():
        return {"exists": False}
    return {
        "exists": True,
        "head": run_cmd(["git", "rev-parse", "HEAD"], cwd=repo),
        "branch": run_cmd(["git", "branch", "--show-current"], cwd=repo),
        "status": run_cmd(["git", "status", "--short"], cwd=repo),
    }


def probe_python(interpreter: Path, extra_pythonpath: str | None = None) -> dict:
    if not interpreter.exists():
        return {"path": str(interpreter), "exists": False}
    env = dict(os.environ)
    if extra_pythonpath:
        cur = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{extra_pythonpath}:{cur}" if cur else extra_pythonpath
    script = (
        "import importlib, importlib.metadata as m, json, sys; "
        "names=['numpy','scipy','casadi','onnx','onnxruntime','torch','stable-baselines3','pytest','rclpy']; "
        "pkgs={}; "
        "\nfor n in names:\n"
        "  try: pkgs[n]=m.version(n)\n"
        "  except Exception: pkgs[n]=None\n"
        "try:\n"
        "  importlib.import_module('acados_template')\n"
        "  ac_ok=True\n"
        "except Exception as exc:\n"
        "  ac_ok=str(exc)\n"
        "print(json.dumps({'executable':sys.executable,'version':sys.version.split()[0],'packages':pkgs,'acados_template':ac_ok}))"
    )
    res = run_cmd([str(interpreter), "-c", script], env=env)
    parsed = None
    if res["returncode"] == 0 and res["stdout"].strip():
        try:
            parsed = json.loads(res["stdout"].strip().splitlines()[-1])
        except json.JSONDecodeError:
            parsed = None
    return {"path": str(interpreter), "exists": True, "probe": parsed, "raw": res}


def read_cmake_cache(path: Path) -> dict | None:
    if not path.is_file():
        return None
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith(("//", "#")):
            continue
        lhs, sep, val = line.partition("=")
        if not sep:
            continue
        key = lhs.partition(":")[0]
        if key in CMAKE_CACHE_KEYS:
            out[key] = val
    return out


def collect_acados_assets(workspace: Path, acados_dir: Path) -> tuple[dict, list[str]]:
    problems: list[str] = []
    info = {
        "source_dir": str(acados_dir),
        "head": run_cmd(["git", "-C", str(acados_dir), "rev-parse", "HEAD"]),
        "libraries": [],
        "generated_models": {},
    }
    for name in ("libacados.so", "libblasfeo.so", "libhpipm.so"):
        path = acados_dir / "lib" / name
        if path.is_file():
            resolved = path.resolve()
            info["libraries"].append({
                "name": name,
                "path": str(path),
                "resolved_path": str(resolved),
                "bytes": resolved.stat().st_size,
                "sha256": sha256_file(resolved),
            })
        else:
            info["libraries"].append({"name": name, "path": str(path), "missing": True})
            problems.append("missing_acados_lib:" + name)

    gen_root = workspace / "research/scheme_a/src/usv_acados/acados_generated"
    for model in GENERATED_MODELS:
        mdir = gen_root / model
        files = []
        if mdir.is_dir():
            for p in sorted(mdir.rglob("*")):
                if p.is_file():
                    files.append({
                        "path": p.relative_to(workspace).as_posix(),
                        "bytes": p.stat().st_size,
                        "sha256": sha256_file(p),
                    })
        if not files:
            problems.append("missing_generated_model:" + model)
        info["generated_models"][model] = {"count": len(files), "files": files}
    return info, problems


def collect_rl_assets(rl_root: Path, rl_artifact_root: Path) -> tuple[dict, list[str]]:
    problems: list[str] = []
    frozen = {}
    for name in FROZEN_RL_FILES:
        path = rl_artifact_root / name
        if not path.is_file():
            frozen[name] = {"path": str(path), "missing": True}
            problems.append("missing_frozen_rl_asset:" + name)
            continue
        digest = sha256_file(path)
        entry = {"path": str(path), "bytes": path.stat().st_size, "sha256": digest}
        expected = EXPECTED_V5_DIGESTS.get(name)
        if expected and expected != digest:
            entry["expected_sha256"] = expected
            problems.append("frozen_rl_asset_hash_mismatch:" + name)
        frozen[name] = entry

    manifest_path = rl_artifact_root / "policy_physical_n.manifest.json"
    manifest_doc = None
    if manifest_path.is_file():
        try:
            manifest_doc = json.loads(manifest_path.read_text(encoding="utf-8"))
            for k, fname in (
                ("onnx_sha256", "policy_physical_n.onnx"),
                ("source_model_sha256", "model.zip"),
                ("source_vecnormalize_sha256", "vecnormalize.pkl"),
            ):
                if manifest_doc.get(k) != frozen.get(fname, {}).get("sha256"):
                    problems.append("manifest_hash_mismatch:" + k)
        except (OSError, ValueError) as exc:
            problems.append("manifest_unparsable:" + str(exc))

    rl_sources = []
    for rel in RL_SOURCE_REFS:
        path = rl_root / rel
        if not path.is_file():
            rl_sources.append({"path": rel, "abs_path": str(path), "missing": True})
            problems.append("missing_rl_source:" + rel)
            continue
        rl_sources.append({
            "path": rel,
            "abs_path": str(path.resolve()),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })

    return {
        "rl_workspace_git": git_info(rl_root),
        "frozen_v5_dir": str(rl_artifact_root),
        "frozen_files": frozen,
        "manifest": manifest_doc,
        "reused_sources": rl_sources,
    }, problems


def collect_parent_evidences(skip_external: bool) -> tuple[list[dict], list[str]]:
    out = []
    problems: list[str] = []
    if skip_external:
        return out, problems
    for path_str, expected_sha in PARENT_EVIDENCES:
        path = Path(path_str)
        if not path.is_file():
            out.append({"path": path_str, "missing": True, "expected_sha256": expected_sha})
            problems.append("missing_parent_evidence:" + path.name)
            continue
        actual = sha256_file(path)
        matches = actual == expected_sha
        if not matches:
            problems.append("parent_evidence_hash_mismatch:" + path.name)
        out.append({
            "path": path_str,
            "bytes": path.stat().st_size,
            "sha256": actual,
            "expected_sha256": expected_sha,
            "matches": matches,
        })
    return out, problems


def inspect_build_install(
    build_base: Path | None,
    install_base: Path | None,
) -> tuple[dict, list[str]]:
    problems: list[str] = []
    if build_base is None and install_base is None:
        return {"mode": "source-only", "claims_install_consistency": False, "build_verified": False}, problems
    if build_base is None or install_base is None:
        return {"mode": "invalid", "claims_install_consistency": False, "build_verified": False}, [
            "build_base_and_install_base_must_both_be_set",
        ]

    build_abs = build_base.resolve()
    install_abs = install_base.resolve()
    per_pkg = {}
    for pkg in EXPECTED_WORKTREE_PACKAGES:
        cache = build_abs / pkg / "CMakeCache.txt"
        cache_vals = read_cmake_cache(cache)
        prefix = install_abs / pkg
        entry = {
            "build_dir_exists": (build_abs / pkg).is_dir(),
            "cmake_cache_exists": cache.is_file(),
            "cmake_cache": cache_vals,
            "install_prefix_exists": prefix.is_dir(),
        }
        if pkg != "usv_bringup" and cache_vals is None:
            problems.append("missing_cmake_cache:" + pkg)
        if pkg == "usv_research_safety_cpp" and cache_vals is not None:
            if cache_vals.get("USV_RESEARCH_TEST_SEAMS") != "OFF":
                problems.append("unexpected_test_seams_flag:" + str(cache_vals.get("USV_RESEARCH_TEST_SEAMS")))
        per_pkg[pkg] = entry

    installed_bins = []
    ldd_records = []
    for pkg, rel in EXPECTED_INSTALL_BINARIES:
        target = install_abs / pkg / rel
        if not target.is_file():
            installed_bins.append({"package": pkg, "rel": rel, "missing": True})
            problems.append("missing_installed_binary:" + rel)
            continue
        installed_bins.append({
            "package": pkg,
            "path": str(target),
            "bytes": target.stat().st_size,
            "sha256": sha256_file(target),
        })
        if target.suffix != ".so":
            ldd_res = run_cmd(["ldd", str(target)])
            matched = [
                ln.strip() for ln in ldd_res["stdout"].splitlines()
                if re.search(r"(acados|blasfeo|hpipm|usv_)", ln)
            ]
            ldd_records.append({"binary": target.name, "returncode": ldd_res["returncode"], "deps": matched})

    return {
        "mode": "built",
        "build_base": str(build_abs),
        "install_base": str(install_abs),
        "claims_install_consistency": not problems,
        "build_verified": not problems,
        "packages": per_pkg,
        "installed_binaries": installed_bins,
        "ldd_bindings": ldd_records,
    }, problems


def write_json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def capture(args: argparse.Namespace) -> tuple[Path, dict]:
    workspace = Path(args.workspace).resolve()
    out = Path(args.out).resolve()
    if not workspace.is_dir():
        raise ValueError(f"workspace directory missing: {workspace}")
    if out.exists():
        raise ValueError(f"output directory already exists, refusing to overwrite: {out}")

    rl_root = Path(args.rl_root).resolve()
    rl_artifact_root = Path(args.rl_artifact_root).resolve()
    acados_dir = Path(args.acados_dir).resolve()

    out.mkdir(parents=True, exist_ok=False)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    problems: list[str] = []

    records, src_probs = collect_worktree_sources(workspace)
    problems.extend(src_probs)

    acados_info, ac_probs = collect_acados_assets(workspace, acados_dir)
    problems.extend(ac_probs)

    rl_info, rl_probs = collect_rl_assets(rl_root, rl_artifact_root)
    if args.require_external_rl:
        problems.extend(rl_probs)
    elif rl_probs:
        # Still verify V5 hashes if directory exists; record issues cleanly.
        problems.extend(rl_probs)

    parent_evidences, parent_probs = collect_parent_evidences(args.skip_parent_evidence)
    problems.extend(parent_probs)

    build_base = Path(args.build_base) if args.build_base else None
    install_base = Path(args.install_base) if args.install_base else None
    build_info, build_probs = inspect_build_install(build_base, install_base)
    problems.extend(build_probs)

    source_hashes_doc = {
        "schema": SOURCE_HASHES_SCHEMA,
        "mode": build_info["mode"],
        "captured_utc": started,
        "workspace": str(workspace),
        "packages": list(EXPECTED_WORKTREE_PACKAGES),
        "records": records,
    }
    write_json(out / "source_hashes.json", source_hashes_doc)

    asset_manifest_doc = {
        "schema": ASSET_MANIFEST_SCHEMA,
        "captured_utc": started,
        "acados": acados_info,
        "rl_assets": rl_info,
        "parent_evidence": parent_evidences,
    }
    write_json(out / "asset_manifest.json", asset_manifest_doc)

    acados_python = str(acados_dir / "interfaces" / "acados_template")
    toolchains = {
        "system_python3": probe_python(Path("/usr/bin/python3"), extra_pythonpath=acados_python),
        "rl_venv_python": probe_python(rl_root / "usv_rl/.venv/bin/python"),
        "os_release": (Path("/etc/os-release").read_text(encoding="utf-8")
                       if Path("/etc/os-release").is_file() else None),
        "machine": platform.machine(),
        "node": platform.node(),
        "kernel": platform.release(),
        "ros_distro": os.environ.get("ROS_DISTRO"),
        "ament_prefix_path": os.environ.get("AMENT_PREFIX_PATH"),
    }

    integrity = {
        "verified": not problems,
        "claims_install_consistency": build_info["claims_install_consistency"],
        "problems": problems,
        "source_count": len(records),
    }

    baseline_doc = {
        "schema": BASELINE_SCHEMA,
        "captured_utc": started,
        "completed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "workspace": str(workspace),
        "git": git_info(workspace),
        "build": build_info,
        "toolchains": toolchains,
        "source_hashes_sha256": sha256_file(out / "source_hashes.json"),
        "asset_manifest_sha256": sha256_file(out / "asset_manifest.json"),
        "integrity": integrity,
    }
    write_json(out / "baseline.json", baseline_doc)
    return out, baseline_doc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", default="/home/trevor/usv_scheme_a_wt")
    p.add_argument("--out", required=True)
    p.add_argument("--source-only", action="store_true")
    p.add_argument("--build-base", default=None)
    p.add_argument("--install-base", default=None)
    p.add_argument("--acados-dir", default=os.environ.get("ACADOS_SOURCE_DIR", "/home/trevor/acados"))
    p.add_argument("--rl-root", default="/home/trevor/USV")
    p.add_argument("--rl-artifact-root", default="/home/trevor/USV/artifacts/rl_models/v5/s4_dr")
    p.add_argument("--skip-parent-evidence", action="store_true")
    p.add_argument("--require-external-rl", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if bool(args.source_only) and (args.build_base or args.install_base):
        print(json.dumps({"verified": False, "error": "cannot combine --source-only with --build-base/--install-base"}),
              file=sys.stderr)
        return 2
    try:
        out, baseline_doc = capture(args)
    except (ValueError, OSError) as exc:
        print(json.dumps({"verified": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"out": str(out), **baseline_doc["integrity"]}, ensure_ascii=False))
    return 0 if baseline_doc["integrity"]["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
