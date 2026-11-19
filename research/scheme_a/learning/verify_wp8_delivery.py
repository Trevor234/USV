#!/usr/bin/env python3
"""WP8 ARM64 reachability probe, B2 shipboard dry-run + GP regression,
full verification runner, and final deliverable bundle packager (`r1`)."""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from closed_loop_metrics import sha256_file
from dataset_builder import extract_run


WORKTREE = Path("/home/trevor/usv_scheme_a_wt")
INSTALL_BASE = WORKTREE / "install/scheme_a"
BUILD_BASE = WORKTREE / "build/scheme_a"
SAFETY_CPP_DIR = WORKTREE / "research/scheme_a/src/usv_research_safety_cpp"
SAFETY_BIN_DIR = INSTALL_BASE / "usv_research_safety_cpp/lib/usv_research_safety_cpp"
DRY_RUN_CONTRACT = SAFETY_CPP_DIR / "model/contract_shipboard_dry_run.json"
CONTROLLED_CONTRACT = SAFETY_CPP_DIR / "model/contract_controlled_sim.json"
PLAN_FILE = SAFETY_CPP_DIR / "model/research_model_plan.json"
ARM64_CAL_EVIDENCE = SAFETY_CPP_DIR / "model/arm64_calibration_evidence.json"

BATCH_ROOT = Path("/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物")
BASELINE_DIR = BATCH_ROOT / "scheme_A_gp_ppo_20261117_baseline"
WORK_ROOT = BATCH_ROOT / "scheme_A_gp_ppo_20261117_work"
GP_MODELS_DIR = WORK_ROOT / "gp_models"
GP_EVAL_DIR = WORK_ROOT / "gp_eval"
PPO_SHADOW_DIR = WORK_ROOT / "ppo_shadow"
WP6_META_DIR = WORK_ROOT / "wp6_baseline_meta"
WP6_REG_DIR = WORK_ROOT / "gp_nmpc_regression"
WP7_EVAL_DIR = WORK_ROOT / "fusion_eval"
DEFAULT_ARCHIVE_DIR = BATCH_ROOT / "scheme_A_gp_ppo_20261117_r1"

PPO_MODEL = Path("/home/trevor/USV/artifacts/rl_models/v5/s4_dr/policy_physical_n.onnx")
PPO_MANIFEST = Path("/home/trevor/USV/artifacts/rl_models/v5/s4_dr/policy_physical_n.manifest.json")


def probe_arm64_target(host: str = "trevor@10.0.0.3") -> dict[str, Any]:
    """Probe Pi 5 reachability and document pre-existing Nov-16/17 hardware receipts."""
    ip = host.split("@", 1)[-1]
    ping = subprocess.run(
        ["ping", "-c", "1", "-W", "2", ip],
        capture_output=True, text=True, check=False,
    )
    ssh = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host,
         "uname -a && systemctl is-active usv_mpc || true"],
        capture_output=True, text=True, check=False,
    )
    reachable_ssh = (ssh.returncode == 0)
    hist_bench = BATCH_ROOT / "scheme-a-bench-20261117T030458Z-results/RESULTS.json"
    hist_dry = BATCH_ROOT / "scheme-a-b2-dryrun-20261117T1010Z-results/RESULTS.json"
    return {
        "schema": "scheme-a-wp8-arm64-reachability-v1",
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "target_host": host,
        "icmp_ping_rc": ping.returncode,
        "icmp_ping_ok": (ping.returncode == 0),
        "ssh_batchmode_rc": ssh.returncode,
        "ssh_batchmode_reachable": reachable_ssh,
        "ssh_stdout": ssh.stdout.strip(),
        "ssh_stderr": ssh.stderr.strip(),
        "arm64_wp8_live_execution_status": (
            "executed" if reachable_ssh
            else "blocked_ssh_auth_required_no_key_or_noninteractive_auth"
        ),
        "historical_arm64_pre_wp6_receipts": {
            "scheme_a_bench_results": str(hist_bench) if hist_bench.is_file() else None,
            "scheme_a_b2_dryrun_results": str(hist_dry) if hist_dry.is_file() else None,
        },
        "production_scheme_b_touched": False,
    }


def _isolated_env(work_dir: Path) -> dict[str, str]:
    def _prepend(name: str, entries: list[str]) -> str:
        cur = [x for x in os.environ.get(name, "").split(":") if x]
        out: list[str] = []
        for item in entries + cur:
            if item and item not in out:
                out.append(item)
        return ":".join(out)

    env = dict(os.environ)
    env.update({
        "ROS_DOMAIN_ID": "224",
        "ROS_LOCALHOST_ONLY": "1",
        "ROS_AUTOMATIC_DISCOVERY_RANGE": "LOCALHOST",
        "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
        "PYTHONDONTWRITEBYTECODE": "1",
        "ACADOS_SOURCE_DIR": "/home/trevor/acados",
        "LD_LIBRARY_PATH": _prepend("LD_LIBRARY_PATH", [
            str(INSTALL_BASE / "usv_acados/lib"),
            str(INSTALL_BASE / "usv_nmpc/lib"),
            str(INSTALL_BASE / "usv_research_interfaces/lib"),
            "/home/trevor/acados/lib",
        ]),
        "AMENT_PREFIX_PATH": _prepend("AMENT_PREFIX_PATH", [
            str(INSTALL_BASE / "usv_research_safety_cpp"),
            str(INSTALL_BASE / "usv_research_interfaces"),
            str(INSTALL_BASE / "usv_nmpc"),
            str(INSTALL_BASE / "usv_acados"),
            str(INSTALL_BASE),
        ]),
        "PYTHONPATH": _prepend("PYTHONPATH", [
            str(INSTALL_BASE / "usv_research_safety_cpp/lib/python3.12/site-packages"),
            str(INSTALL_BASE / "usv_research_interfaces/lib/python3.12/site-packages"),
        ]),
    })
    return env


def run_b2_dry_run_gp_regression(
    out_dir: Path,
    *,
    gp_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    """Run pytest test_shipboard_commissioning.py + live GP-enabled shipboard_dry_run + dataset rejection."""
    # 1. Existing B2 suite.
    pytest_env = _isolated_env(out_dir)
    pytest_env["USV_COMMISSIONING_INSTALL_BASE"] = str(INSTALL_BASE)
    p_test = subprocess.run(
        ["/usr/bin/python3", "-m", "pytest", "-v",
         str(SAFETY_CPP_DIR / "test_shipboard_commissioning.py")],
        cwd=str(WORKTREE), env=pytest_env, capture_output=True, text=True, check=False,
    )

    # 2. Live GP-configured shipboard_dry_run on isolated domain 224.
    dry_dir = out_dir / "dry_run_gp_probe"
    if dry_dir.exists():
        shutil.rmtree(dry_dir)
    dry_dir.mkdir(parents=True, exist_ok=True)
    gp_snap = gp_snapshot_path or (GP_MODELS_DIR / "gp_snapshot.json")
    gp_sha = sha256_file(gp_snap)
    gp_internal_sha = json.loads(gp_snap.read_text(encoding="utf-8"))["snapshot_sha256"]

    run_id = str(uuid.uuid4())
    boot_id = str(uuid.uuid4())
    c_sha = sha256_file(DRY_RUN_CONTRACT)
    p_sha = sha256_file(PLAN_FILE)
    shutil.copy2(DRY_RUN_CONTRACT, dry_dir / "contract.json")
    shutil.copy2(PLAN_FILE, dry_dir / "plan.json")
    (dry_dir / "run.json").write_text(
        json.dumps({"run_id": run_id, "scenario": "shipboard_dry_run", "dataset_source": "dry_run_nominal"}, indent=2) + "\n",
        encoding="utf-8",
    )

    env = _isolated_env(dry_dir)
    w_log = (dry_dir / "worker.stdout.txt").open("wb")
    r_log = (dry_dir / "regulator.stdout.txt").open("wb")
    worker = subprocess.Popen(
        [
            str(SAFETY_BIN_DIR / "p1_solver_worker"), "--ros-args",
            "-p", f"run_id:={run_id}", "-p", f"boot_id:={boot_id}",
            "-p", f"contract_file:={DRY_RUN_CONTRACT}", "-p", f"contract_hash:={c_sha}",
            "-p", f"model_plan_file:={PLAN_FILE}", "-p", f"model_plan_sha256:={p_sha}",
            "-p", "mode:=shipboard_dry_run",
            "-p", f"source_file:={dry_dir / 'worker.source.jsonl'}",
            "-p", f"gp_snapshot_file:={gp_snap}",
            "-p", f"gp_snapshot_sha256:={gp_sha}",
        ],
        env=env, stdout=w_log, stderr=w_log,
    )
    regulator = subprocess.Popen(
        [
            str(SAFETY_BIN_DIR / "p1_regulator"), "--ros-args",
            "-p", f"run_id:={run_id}", "-p", f"boot_id:={boot_id}",
            "-p", f"contract_file:={DRY_RUN_CONTRACT}", "-p", f"contract_hash:={c_sha}",
            "-p", f"model_plan_file:={PLAN_FILE}", "-p", f"model_plan_sha256:={p_sha}",
            "-p", "mode:=shipboard_dry_run",
            "-p", f"source_file:={dry_dir / 'regulator.source.jsonl'}",
            "-p", f"worker_pid:={worker.pid}",
            "-p", f"gp_snapshot_file:={gp_snap}",
            "-p", f"gp_snapshot_sha256:={gp_sha}",
        ],
        env=env, stdout=r_log, stderr=r_log,
    )
    driver_payload: dict[str, Any] = {}
    try:
        driver_code = """
import json, time, rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from mavros_msgs.msg import State
from nav_msgs.msg import Odometry, Path
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import Imu
from std_msgs.msg import Float64MultiArray, MultiArrayDimension, String

rclpy.init()
node = Node("wp8_dry_run_gp_feeder")
sqos = rclpy.qos.qos_profile_sensor_data
p_state = node.create_publisher(State, "/mavros/state", sqos)
p_odom = node.create_publisher(Odometry, "/mavros/local_position/odom", sqos)
p_imu = node.create_publisher(Imu, "/mavros/imu/data", sqos)
p_path = node.create_publisher(Path, "/path/reference", 10)
p_prof = node.create_publisher(Float64MultiArray, "/path/reference_profile", 10)
statuses = []
sub_qos = QoSProfile(depth=1, history=HistoryPolicy.KEEP_LAST, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
node.create_subscription(String, "/p1/commissioning_status", lambda m: statuses.append(json.loads(m.data)), sub_qos)
start = time.monotonic()
ready_seen = False
while time.monotonic() - start < 25.0:
    now_t = node.get_clock().now().to_msg()
    st = State(); st.connected = True; st.armed = False; st.mode = "HOLD"; p_state.publish(st)
    od = Odometry(); od.header.stamp = now_t; od.header.frame_id = "map"; od.child_frame_id = "base_link"
    od.pose.pose.orientation.w = 1.0; od.twist.twist.linear.x = 0.25; p_odom.publish(od)
    im = Imu(); im.header.stamp = now_t; im.header.frame_id = "base_link"; im.orientation.w = 1.0; im.angular_velocity.z = 0.01; p_imu.publish(im)
    path = Path(); path.header.stamp = now_t; path.header.frame_id = "map"; prof = Float64MultiArray()
    for i in range(12):
        ps = PoseStamped(); ps.header.stamp = now_t; ps.header.frame_id = "map"; ps.pose.position.x = float(i)*0.5; ps.pose.orientation.w = 1.0
        path.poses.append(ps); prof.data.extend([0.65, 0.0, 0.0, float(i)*0.8])
    prof.layout.dim = [MultiArrayDimension(label=f"stamp_sec:{now_t.sec}", size=12, stride=48), MultiArrayDimension(label=f"stamp_nanosec:{now_t.nanosec}", size=4, stride=4)]
    p_path.publish(path); p_prof.publish(prof)
    rclpy.spin_once(node, timeout_sec=0.05)
    if statuses:
        last = statuses[-1]
        if last.get("phase") == "ready" and last.get("jobs_submitted", 0) >= 4 and last.get("dry_run", {}).get("candidates_accepted", 0) >= 4:
            ready_seen = True
            break
    time.sleep(0.05)
pubs = {t: [info.node_name for info in node.get_publishers_info_by_topic(t)] for t in ("/p1/commissioning_status","/p1/solve_job","/mavros/setpoint_velocity/cmd_vel","/mavros/rc/override","/wamv/thrusters/left/thrust","/wamv/thrusters/right/thrust","/p1/plant_command","/p1/execution_decision")}
print(json.dumps({"ready_seen": ready_seen, "last": statuses[-1] if statuses else None, "pubs": pubs}))
node.destroy_node(); rclpy.shutdown()
"""
        drv = subprocess.run(["/usr/bin/python3", "-c", driver_code], env=env, capture_output=True, text=True, timeout=45, check=False)
        if drv.returncode != 0:
            raise RuntimeError(f"Dry run driver failed rc={drv.returncode}: {drv.stderr}")
        driver_payload = json.loads(drv.stdout.strip().splitlines()[-1])
    finally:
        for proc in (regulator, worker):
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
        w_log.close()
        r_log.close()

    w_rows = [json.loads(l) for l in (dry_dir / "worker.source.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    r_rows = [json.loads(l) for l in (dry_dir / "regulator.source.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    w_sum = [r for r in w_rows if r.get("type") == "worker_summary"]
    cands = [r for r in w_rows if r.get("type") == "candidate"]
    gp_applied_shas = sorted({str((c.get("job") or {}).get("gp_snapshot_sha256") or "") for c in cands})

    # Write minimal empty plant log to test dataset_builder explicit dry_run rejection.
    (dry_dir / "plant.source.jsonl").write_text("", encoding="utf-8")
    ds_extract = extract_run(dry_dir, split="shipboard_dry_run_probe")

    last_status = driver_payload.get("last") or {}
    forbidden_empty = all(driver_payload["pubs"][t] == [] for t in (
        "/mavros/setpoint_velocity/cmd_vel", "/mavros/rc/override",
        "/wamv/thrusters/left/thrust", "/wamv/thrusters/right/thrust",
        "/p1/plant_command", "/p1/execution_decision",
    ))
    live_ok = bool(
        driver_payload.get("ready_seen")
        and last_status.get("mode") == "shipboard_dry_run"
        and last_status.get("physical_output_enabled") is False
        and last_status.get("closed_loop_verified") is False
        and last_status.get("anchor_known") is False
        and last_status.get("jobs_submitted", 0) >= 4
        and (last_status.get("dry_run") or {}).get("candidates_accepted", 0) >= 4
        and forbidden_empty
        and len(w_sum) == 1
        and w_sum[0].get("dry_run_mode") is True
        and w_sum[0].get("fatal") is False
        and gp_internal_sha in gp_applied_shas
        and ds_extract.stats.get("run_rejected_reason") == "dry_run_not_executable_truth"
        and ds_extract.stats.get("admitted_windows") == 0
    )
    assert p_test.returncode == 0, p_test.stdout + p_test.stderr
    assert live_ok, f"Live GP dry_run check failed: status={last_status}, pubs={driver_payload.get('pubs')}, gp_shas={gp_applied_shas}, ds={ds_extract.stats}"
    return {
        "schema": "scheme-a-wp8-b2-dry-run-regression-v1",
        "pytest_shipboard_commissioning_rc": p_test.returncode,
        "pytest_shipboard_commissioning_passed": (p_test.returncode == 0),
        "live_gp_dry_run": {
            "passed": live_ok,
            "mode": last_status.get("mode"),
            "anchor_known": last_status.get("anchor_known"),
            "closed_loop_verified": last_status.get("closed_loop_verified"),
            "physical_output_enabled": last_status.get("physical_output_enabled"),
            "jobs_submitted": last_status.get("jobs_submitted"),
            "worker_completed_jobs": (last_status.get("worker") or {}).get("completed_jobs"),
            "candidates_accepted": (last_status.get("dry_run") or {}).get("candidates_accepted"),
            "gp_snapshot_shas_seen": gp_applied_shas,
            "expected_gp_snapshot_internal_sha256": gp_internal_sha,
            "forbidden_publishers": {k: driver_payload["pubs"][k] for k in driver_payload["pubs"] if k not in ("/p1/commissioning_status", "/p1/solve_job")},
            "dataset_builder_rejection": {
                "run_rejected_reason": ds_extract.stats.get("run_rejected_reason"),
                "admitted_windows": ds_extract.stats.get("admitted_windows"),
            },
        },
    }


def run_final_test_suites() -> dict[str, Any]:
    """Run pytest across all learning/baseline suites and colcon test across Scheme A packages."""
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        f"{WORKTREE}/research/scheme_a/learning:{WORKTREE}/research/scheme_a/scripts:"
        + env.get("PYTHONPATH", "")
    )
    # Source install/scheme_a/setup.bash via bash -lc so all ROS env vars are accurate.
    py_tests = [
        "research/scheme_a/learning/test_dataset_builder.py",
        "research/scheme_a/learning/test_collect_residual_dataset.py",
        "research/scheme_a/learning/test_gp_offline.py",
        "research/scheme_a/learning/test_ppo_proposal.py",
        "research/scheme_a/scripts/test_capture_research_baseline.py",
    ]
    py_proc = subprocess.run(
        ["bash", "-lc", f"cd {WORKTREE} && source install/scheme_a/setup.bash && PYTHONPATH=research/scheme_a/learning:research/scheme_a/scripts:$PYTHONPATH /usr/bin/python3 -m pytest -v {' '.join(py_tests)}"],
        capture_output=True, text=True, check=False,
    )
    colcon_proc = subprocess.run(
        ["bash", "-lc", f"cd {WORKTREE} && source install/scheme_a/setup.bash && PATH=/usr/local/bin:/usr/bin:/bin colcon --log-base log/scheme_a test --base-paths research/scheme_a/src src/usv_bringup --build-base build/scheme_a --install-base install/scheme_a --packages-select usv_acados usv_nmpc usv_research_safety_cpp && colcon --log-base log/scheme_a test-result --test-result-base build/scheme_a --all"],
        capture_output=True, text=True, check=False,
    )

    xml_records: list[dict[str, Any]] = []
    for pkg in ("usv_acados", "usv_nmpc", "usv_research_safety_cpp"):
        for xfile in sorted((BUILD_BASE / pkg / "test_results" / pkg).glob("*.xml")):
            root = ET.parse(xfile).getroot()
            tests = int(root.attrib.get("tests", 0))
            failures = int(root.attrib.get("failures", 0))
            errors = int(root.attrib.get("errors", 0))
            skipped = int(root.attrib.get("skipped", 0)) + int(root.attrib.get("disabled", 0))
            stem = xfile.name.replace(".gtest.xml", "").replace(".xunit.xml", "")
            is_linter = any(tag in stem for tag in ("cpplint", "uncrustify", "xmllint", "cppcheck", "copyright", "lint_cmake"))
            xml_records.append({
                "package": pkg,
                "suite": stem,
                "file": str(xfile),
                "is_linter": is_linter,
                "tests": tests,
                "failures": failures,
                "errors": errors,
                "skipped": skipped,
            })

    functional_failures = [r for r in xml_records if not r["is_linter"] and (r["failures"] > 0 or r["errors"] > 0)]
    functional_total = sum(r["tests"] for r in xml_records if not r["is_linter"])
    assert py_proc.returncode == 0, py_proc.stdout + py_proc.stderr
    assert not functional_failures, f"Functional test failures: {functional_failures}"
    return {
        "schema": "scheme-a-wp8-verification-suites-v1",
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "learning_pytest_rc": py_proc.returncode,
        "learning_pytest_summary": py_proc.stdout.splitlines()[-3:] if py_proc.stdout else [],
        "colcon_test_rc": colcon_proc.returncode,
        "functional_test_suites": [r for r in xml_records if not r["is_linter"]],
        "functional_tests_total": functional_total,
        "functional_failures": functional_failures,
        "linter_test_suites": [r for r in xml_records if r["is_linter"]],
    }


def _copy_with_record(src: Path, dst: Path, bundle_root: Path, role: str) -> dict[str, Any]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {
        "bundle_relpath": str(dst.relative_to(bundle_root)),
        "source_path": str(src),
        "role": role,
        "bytes": dst.stat().st_size,
        "sha256": sha256_file(dst),
    }


def build_delivery_bundle(
    bundle_root: Path,
    arm64_info: dict[str, Any],
    b2_info: dict[str, Any],
    suites_info: dict[str, Any],
    *,
    work_root: Path = WORK_ROOT,
    baseline_dir: Path = BASELINE_DIR,
    gp_models_dir: Path = GP_MODELS_DIR,
    gp_eval_dir: Path = GP_EVAL_DIR,
    wp6_meta_dir: Path = WP6_META_DIR,
    wp6_reg_dir: Path = WP6_REG_DIR,
    wp7_eval_dir: Path = WP7_EVAL_DIR,
    wp8_work_dir: Path | None = None,
    r2_work_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)

    wp8_work = wp8_work_dir or (work_root / "wp8_dry_run_regression")
    records: list[dict[str, Any]] = []

    # WP1 baseline.
    for fname in ("baseline.json", "asset_manifest.json", "source_hashes.json"):
        records.append(_copy_with_record(baseline_dir / fname, bundle_root / "wp1_baseline" / fname, bundle_root, "wp1_baseline"))

    # WP3 dataset metadata + quality report.
    for fname in ("data_quality_report.md", "split_manifest.json", "episode_manifest.json"):
        records.append(_copy_with_record(work_root / "full" / fname, bundle_root / "wp3_dataset" / fname, bundle_root, "wp3_dataset_meta"))
    for sub in ("dataset_mismatch", "dataset_nominal"):
        for fname in ("dataset_contract.json", "data_quality.json"):
            records.append(_copy_with_record(work_root / "full" / sub / fname, bundle_root / "wp3_dataset" / sub / fname, bundle_root, f"wp3_{sub}"))

    # WP4 GP models + holdout evaluation (supports both flat and per-profile subdirectories).
    for p in sorted(gp_models_dir.rglob("*.json")):
        rel = p.relative_to(gp_models_dir)
        records.append(_copy_with_record(p, bundle_root / "wp4_gp/gp_models" / rel, bundle_root, "wp4_gp_model"))
    for p in sorted(gp_eval_dir.iterdir()):
        if p.is_file():
            records.append(_copy_with_record(p, bundle_root / "wp4_gp/gp_eval" / p.name, bundle_root, "wp4_gp_eval"))

    # WP5 PPO shadow + frozen manifest copy.
    ppo_shadow_dir = work_root / "ppo_shadow"
    for p in sorted(ppo_shadow_dir.iterdir()):
        if p.is_file():
            records.append(_copy_with_record(p, bundle_root / "wp5_ppo_shadow" / p.name, bundle_root, "wp5_ppo_shadow"))
    records.append(_copy_with_record(PPO_MANIFEST, bundle_root / "wp5_ppo_shadow" / PPO_MANIFEST.name, bundle_root, "wp5_frozen_ppo_manifest"))

    # WP6 codegen + contracts + refreshed baseline + closed-loop regression.
    for fname in ("baseline.json", "asset_manifest.json", "source_hashes.json"):
        records.append(_copy_with_record(wp6_meta_dir / fname, bundle_root / "wp6_gp_nmpc/wp6_baseline_meta" / fname, bundle_root, "wp6_meta"))
    records.append(_copy_with_record(work_root / "gp_nmpc_codegen_manifest.json", bundle_root / "wp6_gp_nmpc/gp_nmpc_codegen_manifest.json", bundle_root, "wp6_codegen_manifest"))
    for fname in ("wp6_regression_report.json", "schedule_explicit_zero.json", "schedule_hotswap.json"):
        records.append(_copy_with_record(wp6_reg_dir / fname, bundle_root / "wp6_gp_nmpc" / fname, bundle_root, "wp6_regression"))
    for fname in ("contract_controlled_sim.json", "contract_shipboard_dry_run.json", "research_model_plan.json", "arm64_calibration_evidence.json"):
        records.append(_copy_with_record(SAFETY_CPP_DIR / "model" / fname, bundle_root / "wp6_gp_nmpc/contracts" / fname, bundle_root, "wp6_contract"))

    # WP7 fusion evaluation reports/configs.
    for fname in ("selected_configuration.json", "calibration_summary.json", "conflict_probe_summary.json", "four_arm_evaluation.json", "fusion_report.md"):
        records.append(_copy_with_record(wp7_eval_dir / fname, bundle_root / "wp7_fusion" / fname, bundle_root, "wp7_fusion"))

    # Optional r2 diagnosis/calibration reports.
    if r2_work_root is not None:
        for rel in (
            "diagnosis/gp_regression_diagnosis.md",
            "diagnosis/gp_regression_diagnosis.json",
            "calib_eval/r2_calibration_report.md",
            "calib_eval/r4_calibration_report.md",
            "calib_eval/conflict_probe_report.json",
        ):
            src_r2 = r2_work_root / rel
            if src_r2.is_file():
                records.append(_copy_with_record(src_r2, bundle_root / "r2_research" / rel, bundle_root, "r2_research"))

    # WP8 reports.
    wp8_dir = bundle_root / "wp8_delivery"
    wp8_dir.mkdir(parents=True, exist_ok=True)
    for fname, obj in (
        ("arm64_reachability.json", arm64_info),
        ("b2_dry_run_regression.json", b2_info),
        ("colcon_and_pytest_verification.json", suites_info),
    ):
        fpath = wp8_dir / fname
        fpath.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        records.append({
            "bundle_relpath": str(fpath.relative_to(bundle_root)),
            "source_path": str(fpath),
            "role": "wp8_verification",
            "bytes": fpath.stat().st_size,
            "sha256": sha256_file(fpath),
        })

    # Copy compact dry_run_gp_probe logs into wp8_delivery.
    for p in sorted((wp8_work / "dry_run_gp_probe").iterdir()):
        if p.is_file():
            records.append(_copy_with_record(p, wp8_dir / "dry_run_gp_probe" / p.name, bundle_root, "wp8_dry_run_probe"))

    # External large artifact / built binary digests.
    external_assets = []
    for label, path in (
        ("ppo_onnx_v5_s4_dr", PPO_MODEL),
        ("dataset_mismatch_npz", work_root / "full/dataset_mismatch/dataset.npz"),
        ("dataset_nominal_npz", work_root / "full/dataset_nominal/dataset.npz"),
        ("bin_p1_x86_plant", SAFETY_BIN_DIR / "p1_x86_plant"),
        ("bin_p1_solver_worker", SAFETY_BIN_DIR / "p1_solver_worker"),
        ("bin_p1_regulator", SAFETY_BIN_DIR / "p1_regulator"),
        ("bin_p1_gp_eval_cli", SAFETY_BIN_DIR / "p1_gp_eval_cli"),
        ("bin_p1_contract_validate", SAFETY_BIN_DIR / "p1_contract_validate"),
        ("lib_usv_acados_backend", INSTALL_BASE / "usv_acados/lib/libusv_acados_backend.so.0.1.0"),
        ("raw_full_dataset_root", work_root / "full"),
        ("raw_wp7_eval_root", wp7_eval_dir),
    ):
        if path.is_file():
            external_assets.append({"label": label, "path": str(path), "kind": "file", "bytes": path.stat().st_size, "sha256": sha256_file(path)})
        elif path.is_dir():
            external_assets.append({"label": label, "path": str(path), "kind": "directory"})

    sel_cfg = json.loads((wp7_eval_dir / "selected_configuration.json").read_text(encoding="utf-8"))
    eval_doc = json.loads((wp7_eval_dir / "four_arm_evaluation.json").read_text(encoding="utf-8"))
    wp6_rep = json.loads((wp6_reg_dir / "wp6_regression_report.json").read_text(encoding="utf-8"))
    gp_par = json.loads((gp_eval_dir / "gp_numeric_parity.json").read_text(encoding="utf-8"))

    replay_commands = {
        "build_scheme_a": "cd /home/trevor/usv_scheme_a_wt && PATH=/usr/local/bin:/usr/bin:/bin colcon --log-base log/scheme_a build --base-paths research/scheme_a/src src/usv_bringup --build-base build/scheme_a --install-base install/scheme_a --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3 -DCMAKE_BUILD_TYPE=Release -DUSV_RESEARCH_TEST_SEAMS=OFF -DBUILD_TESTING=ON",
        "wp6_closed_loop_regression": f"cd /home/trevor/usv_scheme_a_wt && source install/scheme_a/setup.bash && PYTHONPATH=research/scheme_a/learning:$PYTHONPATH /usr/bin/python3 research/scheme_a/learning/verify_wp6_gp_nmpc.py --out {wp6_reg_dir} --source-hashes {wp6_meta_dir / 'source_hashes.json'} --align-tick-phase --base-domain-id 31",
        "wp7_fusion_evaluation": (
            f"cd /home/trevor/usv_scheme_a_wt && source install/scheme_a/setup.bash && PYTHONPATH=research/scheme_a/learning:$PYTHONPATH /usr/bin/python3 research/scheme_a/learning/eval_r5_fusion.py --out {wp7_eval_dir} --source-hashes {wp6_meta_dir / 'source_hashes.json'}"
            if r2_work_root is not None
            else "cd /home/trevor/usv_scheme_a_wt && source install/scheme_a/setup.bash && PYTHONPATH=research/scheme_a/learning:$PYTHONPATH /usr/bin/python3 research/scheme_a/learning/eval_fusion_arms.py --stage all --workers 1 --base-domain-id 30"
        ),
        "wp8_delivery_and_b2_dry_run": "cd /home/trevor/usv_scheme_a_wt && source install/scheme_a/setup.bash && PYTHONPATH=research/scheme_a/learning:$PYTHONPATH /usr/bin/python3 research/scheme_a/learning/verify_wp8_delivery.py" + (" --skip-arm64-probe" if arm64_info.get("skipped_by_policy") else ""),
    }

    # Write CURRENT.md first so its digest is also included in delivery_manifest.json + readback.json.
    all12 = eval_doc["final_test_aggregates_all12"]
    held6 = eval_doc["final_test_aggregates_heldout6"]
    arm_order = [
        a for a in ("nominal_nmpc", "oracle_nmpc", "gp_nmpc_r2b", "gp_nmpc", "ppo_guided_nmpc", "gp_ppo_nmpc_r2b", "gp_ppo_nmpc")
        if a in all12
        and not (a == "gp_nmpc" and "gp_nmpc_r2b" in all12)
        and not (a == "gp_ppo_nmpc" and "gp_ppo_nmpc_r2b" in all12)
    ]
    linter_fails = sum(r["failures"] + r["errors"] for r in suites_info["linter_test_suites"])
    linter_skips = sum(r["skipped"] for r in suites_info["linter_test_suites"])
    eps_label = eval_doc.get("episodes_per_full_arm", 12)
    current_md = "\n".join([
        f"# Scheme A GP-NMPC + PPO Delivery Bundle (`{bundle_root.name}`)",
        "",
        f"- Created UTC: `{datetime.datetime.now(datetime.timezone.utc).isoformat()}`",
        f"- Worktree: `{WORKTREE}` (`USV_RESEARCH_TEST_SEAMS=OFF`)",
        f"- Selected Pooled GP Snapshot: `{sel_cfg['gp_snapshot_pooled']}` (`sha256={sel_cfg['gp_snapshot_pooled_sha256']}`)",
        f"- Frozen PPO ONNX (`v5/s4_dr`): `{sel_cfg['ppo_model_onnx']}` (`sha256={sel_cfg['ppo_model_sha256']}`)",
        f"- Calibrated `lambda_pi`: `{sel_cfg['selected_positive_lambda_pi']}` (overall best on calibration split: `{sel_cfg['calibration_overall_best_lambda_pi']}`)",
        f"- GP Python vs C++ Parity (`gp_numeric_parity.json`): `sha256_match={gp_par['sha256_match']}`, `max_abs_mean_diff={gp_par['max_abs_mean_diff']:.3e}`, `ood_flags_exact_match={gp_par['ood_flags_exact_match']}`",
        f"- WP6 Closed-Loop Regression (`wp6_regression_report.json`): `all_passed={wp6_rep['all_passed']}` ({list(wp6_rep['results'].keys())})",
        "",
        f"## Held-Out `final_test` Summary ({eps_label} Episodes/Arm x 301 Ticks)",
        "| Arm | Pass/Succ | CTE RMSE (m) | Heading RMSE | Speed RMSE | TV/step | Vel Res RMSE | E2E P95 (ms) | E2E Max (ms) |",
        "|---|:---:|---:|---:|---:|---:|---:|---:|---:|",
        *[
            f"| `{arm}` | {all12[arm]['checker_pass_count']}/{all12[arm]['episodes']} ({all12[arm]['success_count']}) | "
            f"{all12[arm]['cross_track_rmse_m']['mean']:.4f} | {all12[arm]['heading_rmse_rad']['mean']:.4f} | "
            f"{all12[arm]['speed_rmse_mps']['mean']:.4f} | {all12[arm]['control_tv_per_step']['mean']:.3f} | "
            f"{(all12[arm]['gp_model_vel_rmse']['mean'] if all12[arm]['gp_model_vel_rmse']['mean'] is not None else all12[arm]['zero_model_vel_rmse']['mean']):.5f} | "
            f"{all12[arm]['latency_ms']['e2e_p95_mean']:.3f} | {all12[arm]['latency_ms']['e2e_max']:.3f} |"
            for arm in arm_order
        ],
        "",
        f"- Unseen `heldout_combination` mean CTE RMSE: " + ", ".join(
            f"`{arm}={held6[arm]['cross_track_rmse_m']['mean']:.4f}m`" for arm in arm_order if arm in held6
        ) + ".",
        "",
        "## WP8 Verification & Target Hardware Status",
        f"- x86 Learning Pytest (`5` files): rc=`{suites_info['learning_pytest_rc']}`; B2 `test_shipboard_commissioning.py` rc=`{b2_info['pytest_shipboard_commissioning_rc']}`",
        f"- x86 Functional C++/ROS Suites (`usv_acados`, `usv_nmpc`, `usv_research_safety_cpp`): `{suites_info['functional_tests_total']}` functional tests, `{len(suites_info['functional_failures'])}` failures; Linter suites: `{linter_fails}` failures, `{linter_skips}` skipped",
        f"- Live GP `shipboard_dry_run` Safety & Data Guard: `passed={b2_info['live_gp_dry_run']['passed']}`, `anchor_known={b2_info['live_gp_dry_run']['anchor_known']}`, `closed_loop_verified={b2_info['live_gp_dry_run']['closed_loop_verified']}`, `physical_output_enabled={b2_info['live_gp_dry_run']['physical_output_enabled']}`, `dataset_builder={b2_info['live_gp_dry_run']['dataset_builder_rejection']['run_rejected_reason']}`",
        f"- ARM64 Target (`{arm64_info['target_host']}`): status=`{arm64_info['arm64_wp8_live_execution_status']}`, ping=`{arm64_info['icmp_ping_ok']}`, ssh=`{arm64_info['ssh_batchmode_reachable']}`. Production `SCHEME=B` untouched.",
        "",
    ])
    current_path = bundle_root / "CURRENT.md"
    current_path.write_text(current_md, encoding="utf-8")
    records.append({
        "bundle_relpath": "CURRENT.md",
        "source_path": str(current_path),
        "role": "bundle_index_markdown",
        "bytes": current_path.stat().st_size,
        "sha256": sha256_file(current_path),
    })

    manifest = {
        "schema": "scheme-a-gp-ppo-delivery-manifest-v1",
        "bundle_id": bundle_root.name,
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "worktree": str(WORKTREE),
        "replay_commands": replay_commands,
        "bundled_files": records,
        "external_artifacts": external_assets,
        "arm64_status": arm64_info,
    }
    manifest_path = bundle_root / "delivery_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    # Independent readback verification of every bundled and external file hash.
    readback_checks = []
    missing = 0
    mismatched = 0
    for rec in records:
        p = bundle_root / rec["bundle_relpath"]
        exists = p.is_file()
        actual_sha = sha256_file(p) if exists else None
        match = (exists and actual_sha == rec["sha256"])
        if not exists:
            missing += 1
        elif not match:
            mismatched += 1
        readback_checks.append({
            "bundle_relpath": rec["bundle_relpath"],
            "exists": exists,
            "sha256_match": match,
            "expected_sha256": rec["sha256"],
            "actual_sha256": actual_sha,
        })
    ext_checks = []
    for ext in external_assets:
        p = Path(ext["path"])
        exists = p.exists()
        actual_sha = sha256_file(p) if (ext["kind"] == "file" and p.is_file()) else None
        match = (exists and (ext["kind"] != "file" or actual_sha == ext["sha256"]))
        if not exists:
            missing += 1
        elif not match:
            mismatched += 1
        ext_checks.append({"label": ext["label"], "path": ext["path"], "exists": exists, "match": match})

    readback = {
        "schema": "scheme-a-gp-ppo-readback-v1",
        "verified_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "delivery_manifest_sha256": sha256_file(manifest_path),
        "all_verified": (missing == 0 and mismatched == 0),
        "bundled_count": len(readback_checks),
        "external_count": len(ext_checks),
        "missing_count": missing,
        "mismatched_count": mismatched,
        "bundled_checks": readback_checks,
        "external_checks": ext_checks,
    }
    readback_path = bundle_root / "readback.json"
    readback_path.write_text(json.dumps(readback, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    assert readback["all_verified"], f"Readback verification failed: missing={missing}, mismatched={mismatched}"
    return manifest, readback


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-out", default=str(DEFAULT_ARCHIVE_DIR))
    parser.add_argument("--arm64-host", default="trevor@10.0.0.3")
    parser.add_argument("--skip-arm64-probe", action="store_true", help="Skip ARM64 ping/ssh probe (x86-only research runs).")
    parser.add_argument("--work-root", default=str(WORK_ROOT))
    parser.add_argument("--baseline-dir", default=str(BASELINE_DIR))
    parser.add_argument("--gp-models-dir", default=None)
    parser.add_argument("--gp-eval-dir", default=None)
    parser.add_argument("--wp6-meta-dir", default=None)
    parser.add_argument("--wp6-reg-dir", default=None)
    parser.add_argument("--wp7-eval-dir", default=None)
    parser.add_argument("--r2-work-root", default=None, help="Optional r2 work root to also bundle r2 diagnosis/calibration reports.")
    parser.add_argument("--dry-run-gp-snapshot", default=None)
    args = parser.parse_args(argv)

    work_root = Path(args.work_root)
    r2_root = Path(args.r2_work_root) if args.r2_work_root else None
    baseline_dir = Path(args.baseline_dir)
    gp_models_dir = Path(args.gp_models_dir) if args.gp_models_dir else ((r2_root / "gp_models") if r2_root else work_root / "gp_models")
    gp_eval_dir = Path(args.gp_eval_dir) if args.gp_eval_dir else ((r2_root / "gp_eval") if r2_root else work_root / "gp_eval")
    wp6_meta_dir = Path(args.wp6_meta_dir) if args.wp6_meta_dir else ((r2_root / "meta") if r2_root else work_root / "wp6_baseline_meta")
    wp6_reg_dir = Path(args.wp6_reg_dir) if args.wp6_reg_dir else ((r2_root / "gp_nmpc_regression_r6") if r2_root else work_root / "gp_nmpc_regression")
    wp7_eval_dir = Path(args.wp7_eval_dir) if args.wp7_eval_dir else ((r2_root / "fusion_eval") if r2_root else work_root / "fusion_eval")
    wp8_work = (r2_root or work_root) / "wp8_dry_run_regression"
    wp8_work.mkdir(parents=True, exist_ok=True)
    dry_gp = Path(args.dry_run_gp_snapshot) if args.dry_run_gp_snapshot else (
        gp_models_dir / "pooled/gp_snapshot.json"
        if (gp_models_dir / "pooled/gp_snapshot.json").is_file()
        else gp_models_dir / "gp_snapshot.json"
    )

    if args.skip_arm64_probe:
        hist_bench = BATCH_ROOT / "scheme-a-bench-20261117T030458Z-results/RESULTS.json"
        hist_dry = BATCH_ROOT / "scheme-a-b2-dryrun-20261117T1010Z-results/RESULTS.json"
        arm64_info = {
            "schema": "scheme-a-wp8-arm64-reachability-v1",
            "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "target_host": args.arm64_host,
            "icmp_ping_rc": None,
            "icmp_ping_ok": None,
            "ssh_batchmode_rc": None,
            "ssh_batchmode_reachable": False,
            "ssh_stdout": "",
            "ssh_stderr": "",
            "skipped_by_policy": "x86-only-r2",
            "arm64_wp8_live_execution_status": "skipped_x86_only_policy",
            "historical_arm64_pre_wp6_receipts": {
                "scheme_a_bench_results": str(hist_bench) if hist_bench.is_file() else None,
                "scheme_a_b2_dryrun_results": str(hist_dry) if hist_dry.is_file() else None,
            },
            "production_scheme_b_touched": False,
        }
        print(f"[WP8] ARM64 probe skipped ({arm64_info['arm64_wp8_live_execution_status']})", flush=True)
    else:
        print("[WP8] Probing ARM64 target reachability...", flush=True)
        arm64_info = probe_arm64_target(args.arm64_host)
        print(f"[WP8] ARM64 probe: ping={arm64_info['icmp_ping_ok']} ssh={arm64_info['ssh_batchmode_reachable']} status={arm64_info['arm64_wp8_live_execution_status']}", flush=True)

    print("[WP8] Running B2 shipboard_dry_run + GP + dataset_builder rejection regression...", flush=True)
    b2_info = run_b2_dry_run_gp_regression(wp8_work, gp_snapshot_path=dry_gp)
    print(f"[WP8] B2 dry-run regression passed={b2_info['live_gp_dry_run']['passed']}", flush=True)

    print("[WP8] Running full pytest and colcon test verification suites...", flush=True)
    suites_info = run_final_test_suites()
    print(f"[WP8] Verification suites complete: learning_rc={suites_info['learning_pytest_rc']}, functional_total={suites_info['functional_tests_total']}, functional_failures={len(suites_info['functional_failures'])}", flush=True)

    bundle_root = Path(args.bundle_out)
    print(f"[WP8] Packaging final delivery bundle -> {bundle_root}...", flush=True)
    manifest, readback = build_delivery_bundle(
        bundle_root,
        arm64_info,
        b2_info,
        suites_info,
        work_root=work_root,
        baseline_dir=baseline_dir,
        gp_models_dir=gp_models_dir,
        gp_eval_dir=gp_eval_dir,
        wp6_meta_dir=wp6_meta_dir,
        wp6_reg_dir=wp6_reg_dir,
        wp7_eval_dir=wp7_eval_dir,
        wp8_work_dir=wp8_work,
        r2_work_root=r2_root,
    )
    print(json.dumps({
        "bundle_root": str(bundle_root),
        "all_verified": readback["all_verified"],
        "bundled_count": readback["bundled_count"],
        "external_count": readback["external_count"],
        "arm64_status": arm64_info["arm64_wp8_live_execution_status"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
