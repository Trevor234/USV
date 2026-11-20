"""F1/F2 回归测试：服务级验收 checker 的 --proc-snapshot 与活动/已结束判定。

全部构造临时 run 目录并实际调用 check_shipboard_commissioning.py 子进程，
不依赖 run_state.json / status_latest.json，也不允许无 snapshot 静默跳过。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys

import pytest

CHECKER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "scripts",
    "check_shipboard_commissioning.py",
)
SUPERVISOR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "scripts",
    "run_shipboard_commissioning.py",
)


def _load_supervisor():
    spec = importlib.util.spec_from_file_location("run_shipboard_commissioning", SUPERVISOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

SUPERVISOR_SCHEMA = "p1-shipboard-supervisor-v1"
STATUS_SCHEMA = "p1-shipboard-commissioning-status-v1"


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_status() -> dict:
    empty_input = {
        "seen": False,
        "count": 0,
        "receipt_age_ns": None,
        "source_stamp_ns": None,
        "frame": None,
        "child_frame": None,
        "truncated": False,
        "finite": None,
        "resource_valid": False,
    }
    imu_input = {
        "seen": True,
        "count": 5,
        "receipt_age_ns": 100_000_000,
        "source_stamp_ns": 123456789,
        "frame": "base_link",
        "child_frame": None,
        "truncated": False,
        "finite": True,
        "resource_valid": True,
    }
    state_input = {
        "seen": True,
        "count": 5,
        "receipt_age_ns": 100_000_000,
        "source_stamp_ns": None,
        "frame": None,
        "child_frame": None,
        "truncated": False,
        "finite": None,
        "resource_valid": None,
    }
    return {
        "schema": STATUS_SCHEMA,
        "run_id": "run-1",
        "boot_id": "boot-1",
        "host_boot_id": "host-1",
        "contract_hash": "c" * 64,
        "plan_sha256": "p" * 64,
        "mode": "commissioning",
        "seq": 3,
        "at_ns": 3_000_000_000,
        "phase": "ready",
        "failure_reason": "",
        "physical_output_enabled": False,
        "jobs_submitted": 0,
        "anchor_known": False,
        "control_inputs_verified": False,
        "closed_loop_verified": False,
        "worker": {
            "pid": 1002,
            "instance": "worker-1",
            "model_runtime_ready": True,
            "capability_age_ns": 50_000_000,
            "completed_jobs": 0,
            "active_job": 0,
            "pending_count": 0,
        },
        "fcu": {"seen": True, "connected": True, "armed": False, "mode": "HOLD"},
        "inputs": {
            "state": state_input,
            "odom": dict(empty_input),
            "imu": imu_input,
            "path": dict(empty_input),
            "profile": dict(empty_input),
        },
        "source": {"generated": 4, "emitted": 4, "dropped": 0, "failed": False},
    }


def _build_fixture(tmp_path, include_shutdown: bool = False, include_summaries: bool = False):
    release = tmp_path / "release"
    underlay = tmp_path / "underlay"
    run_dir = release / "runs" / "inv-fixture-1"
    tx_dir = tmp_path / "tx"
    bin_dir = release / "install" / "usv_research_safety_cpp" / "lib" / "usv_research_safety_cpp"
    lib_dir = release / "install" / "usv_acados" / "lib"
    (release / "deploy").mkdir(parents=True)
    (release / "evidence").mkdir(parents=True)
    bin_dir.mkdir(parents=True)
    lib_dir.mkdir(parents=True)
    underlay.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    tx_dir.mkdir(parents=True)

    (release / "deploy" / "capture_release_identity.py").write_text(
        "import hashlib\n"
        "def sha256_bytes(data: bytes) -> str:\n"
        "    return hashlib.sha256(data).hexdigest()\n",
        encoding="utf-8",
    )

    regulator_bin = bin_dir / "p1_regulator"
    worker_bin = bin_dir / "p1_solver_worker"
    supervisor_py = bin_dir / "run_shipboard_commissioning.py"
    acados_so = lib_dir / "libusv_acados_backend.so"
    regulator_bin.write_bytes(b"\x7fELF-reg")
    worker_bin.write_bytes(b"\x7fELF-wrk")
    supervisor_py.write_text("# supervisor\n", encoding="utf-8")
    acados_so.write_bytes(b"\x7fELF-so")

    install_root = release / "install"
    manifest_records = []
    for item in (regulator_bin, worker_bin, supervisor_py, acados_so):
        rel = os.path.relpath(item, install_root)
        manifest_records.append({
            "path": rel,
            "resolved_path": str(item),
            "sha256": _sha256_file(str(item)),
        })
    (release / "evidence" / "install_manifest.json").write_text(
        json.dumps({"records": manifest_records}),
        encoding="utf-8",
    )

    reg_sha = _sha256_file(str(regulator_bin))
    wrk_sha = _sha256_file(str(worker_bin))
    snapshot = {
        "schema": "p1-shipboard-proc-snapshot-v1",
        "processes": [
            {
                "pid": 1001,
                "cmdline": [str(regulator_bin)],
                "exe_deleted": False,
                "exe_target": str(regulator_bin),
                "exe_sha256": reg_sha,
                "disk_sha256": reg_sha,
                "external_libraries": [{"path": str(acados_so), "sha256": "a" * 64}],
                "interpreter": False,
            },
            {
                "pid": 1002,
                "cmdline": [str(worker_bin)],
                "exe_deleted": False,
                "exe_target": str(worker_bin),
                "exe_sha256": wrk_sha,
                "disk_sha256": wrk_sha,
                "external_libraries": [{"path": str(acados_so), "sha256": "a" * 64}],
                "interpreter": False,
            },
            {
                "pid": 1000,
                "cmdline": ["/usr/bin/python3", "-B", str(supervisor_py)],
                "exe_deleted": False,
                "exe_target": "/usr/bin/python3",
                "interpreter": True,
            },
            {
                "pid": 1003,
                "cmdline": ["/opt/ros/jazzy/lib/mavros/mavros_node"],
                "exe_deleted": False,
                "exe_target": "/opt/ros/jazzy/lib/mavros/mavros_node",
                "interpreter": False,
            },
        ],
        "serial_holders": {"/dev/ttyAMA10": [1003], "/dev/ttyAMA4": [1004]},
    }
    snap_path = tx_dir / "commissioning-t60.json"
    snap_path.write_text(json.dumps(snapshot), encoding="utf-8")

    status = _valid_status()
    base = {
        "schema": SUPERVISOR_SCHEMA,
        "invocation_id": "inv-fixture-1",
        "run_id": "run-1",
        "boot_id": "boot-1",
        "host_boot_id": "host-1",
    }
    sup_lines = [
        {**base, "event": "startup", "at_ns": 1_000_000_000},
        {
            **base,
            "event": "sample",
            "at_ns": 2_000_000_000,
            "status_received_ns": 1_900_000_000,
            "worker_capability_received_ns": 1_800_000_000,
            "processes": {},
            "regulator_status": status,
        },
        {
            **base,
            "event": "sample",
            "at_ns": 3_000_000_000,
            "status_received_ns": 2_900_000_000,
            "worker_capability_received_ns": 2_800_000_000,
            "processes": {},
            "regulator_status": status,
        },
    ]
    if include_shutdown:
        sup_lines.append({
            **base,
            "event": "shutdown",
            "at_ns": 4_000_000_000,
            "reason": "clean_stop",
            "exit_code": 0,
        })
    (run_dir / "supervisor.jsonl").write_text(
        "\n".join(json.dumps(row) for row in sup_lines) + "\n",
        encoding="utf-8",
    )

    if include_summaries:
        (run_dir / "worker.source.jsonl").write_text(
            json.dumps({"type": "worker_summary", "fatal": False, "completed_jobs": 0}) + "\n",
            encoding="utf-8",
        )
        (run_dir / "regulator.source.jsonl").write_text(
            json.dumps({"type": "source_summary", "generated": 5, "emitted": 5, "dropped": 0}) + "\n",
            encoding="utf-8",
        )

    return release, underlay, run_dir, snap_path


def _run_checker(release, underlay, run_dir, snap_path, out_path, extra_args=()):
    cmd = [
        sys.executable,
        "-B",
        CHECKER,
        "--release-root",
        str(release),
        "--underlay",
        str(underlay),
        "--run",
        str(run_dir),
        "--proc-snapshot",
        str(snap_path),
        "--out",
        str(out_path),
        *extra_args,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    doc = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {}
    return res.returncode, doc, res


def test_active_run_passes_with_external_proc_snapshot(tmp_path):
    release, underlay, run_dir, snap_path = _build_fixture(tmp_path)
    out = tmp_path / "check-active.json"
    rc, doc, res = _run_checker(
        release, underlay, run_dir, snap_path, out, extra_args=("--expect-active",)
    )
    assert rc == 0, res.stdout + res.stderr
    assert doc["verdict"] == "PASS"
    assert doc["commissioning_service_takeover_passed"] is True
    assert doc["physical_control_authorised"] is False
    assert doc["closed_loop_verified"] is False
    assert doc["run_facts"]["finished"] is False


def test_active_run_missing_proc_snapshot_exits_2(tmp_path):
    release, underlay, run_dir, _ = _build_fixture(tmp_path)
    missing = tmp_path / "nonexistent-t60.json"
    out = tmp_path / "check-missing-snap.json"
    rc, doc, _ = _run_checker(release, underlay, run_dir, missing, out)
    assert rc == 2
    assert doc["verdict"] == "FAIL"
    assert any("proc_snapshot_present" in err for err in doc["errors"])


def test_closed_run_missing_summary_exits_2(tmp_path):
    release, underlay, run_dir, snap_path = _build_fixture(
        tmp_path, include_shutdown=True, include_summaries=False
    )
    out = tmp_path / "check-closed-no-sum.json"
    rc, doc, _ = _run_checker(release, underlay, run_dir, snap_path, out)
    assert rc == 2
    assert doc["verdict"] == "FAIL"
    assert any("closed_summary_missing" in err for err in doc["errors"])


def test_closed_run_with_summaries_passes(tmp_path):
    release, underlay, run_dir, snap_path = _build_fixture(
        tmp_path, include_shutdown=True, include_summaries=True
    )
    out = tmp_path / "check-closed-pass.json"
    rc, doc, res = _run_checker(release, underlay, run_dir, snap_path, out)
    assert rc == 0, res.stdout + res.stderr
    assert doc["verdict"] == "PASS"
    assert doc["run_facts"]["finished"] is True


def test_active_run_with_shutdown_event_exits_2(tmp_path):
    # 即使有 summary，只要声明期望活动 (--expect-active) 却带 shutdown 事件，必须 exit 2
    release, underlay, run_dir, snap_path = _build_fixture(
        tmp_path, include_shutdown=True, include_summaries=True
    )
    out = tmp_path / "check-active-shutdown.json"
    rc, doc, _ = _run_checker(
        release, underlay, run_dir, snap_path, out, extra_args=("--expect-active",)
    )
    assert rc == 2
    assert doc["verdict"] == "FAIL"
    assert any("supervisor_active_no_shutdown" in err for err in doc["errors"])


def _setup_env_fixture(tmp_path):
    ws = tmp_path / "ws"
    underlay = ws / "install"
    release = tmp_path / "release"
    ntrip_src = ws / "build" / "ntrip_client" / "src"
    ntrip_sp = underlay / "ntrip_client" / "lib" / "python3.12" / "site-packages"
    rel_sp = release / "install" / "usv_bringup" / "lib" / "python3.12" / "site-packages"
    dds = tmp_path / "fastdds_lan.xml"
    dds.write_text("<dds/>", encoding="utf-8")
    for p in (ntrip_src, ntrip_sp, rel_sp):
        p.mkdir(parents=True, exist_ok=True)
    (ntrip_sp / "ntrip-client.egg-link").write_text(f"{ntrip_src}\n../\n", encoding="utf-8")
    identity = {
        "ros_domain_id": 0,
        "dds_profile_path": str(dds),
        "dds_profile_sha256": _sha256_file(str(dds)),
    }
    return ws, underlay, release, ntrip_src, rel_sp, identity


def test_clean_environment_strips_verified_underlay_egg_link_and_ensures_acados_lib(tmp_path, monkeypatch):
    sup = _load_supervisor()
    ws, underlay, release, ntrip_src, rel_sp, identity = _setup_env_fixture(tmp_path)
    monkeypatch.setenv("PYTHONPATH", f"{rel_sp}:{ntrip_src}:{underlay}")
    monkeypatch.setenv("LD_LIBRARY_PATH", f"{release}/install/usv_nmpc/lib")
    monkeypatch.setenv("AMENT_PREFIX_PATH", f"{release}/install:{underlay}")
    monkeypatch.setenv("CMAKE_PREFIX_PATH", f"{release}/install:{underlay}")

    cleaned = sup.clean_environment(str(release), str(underlay), identity)
    py_entries = cleaned["PYTHONPATH"].split(":")
    assert str(ntrip_src) not in py_entries
    assert str(rel_sp) in py_entries
    assert str(underlay) in py_entries

    acados_lib = os.path.join(os.path.realpath("/home/trevor/acados"), "lib")
    if os.path.isdir(acados_lib):
        ld_entries = [os.path.realpath(p) for p in cleaned["LD_LIBRARY_PATH"].split(":")]
        assert ld_entries.count(acados_lib) == 1
        monkeypatch.setenv("LD_LIBRARY_PATH", f"{release}/install/usv_nmpc/lib:{acados_lib}/")
        cleaned2 = sup.clean_environment(str(release), str(underlay), identity)
        assert [os.path.realpath(p) for p in cleaned2["LD_LIBRARY_PATH"].split(":")].count(acados_lib) == 1


def test_clean_environment_still_rejects_unverified_build_or_overridden_pkg(tmp_path, monkeypatch):
    sup = _load_supervisor()
    ws, underlay, release, ntrip_src, rel_sp, identity = _setup_env_fixture(tmp_path)

    # 1. 未在 underlay egg-link 中声明的 build 目录仍必须拒绝
    evil_src = ws / "build" / "unregistered_pkg" / "src"
    evil_src.mkdir(parents=True)
    monkeypatch.setenv("PYTHONPATH", f"{rel_sp}:{evil_src}")
    monkeypatch.setenv("LD_LIBRARY_PATH", "")
    monkeypatch.setenv("AMENT_PREFIX_PATH", "")
    monkeypatch.setenv("CMAKE_PREFIX_PATH", "")
    with pytest.raises(SystemExit):
        sup.clean_environment(str(release), str(underlay), identity)

    # 2. 纯研究包不允许通过 underlay egg-link 注入
    research_src = ws / "build" / "usv_research_safety_cpp" / "src"
    research_sp = underlay / "usv_research_safety_cpp" / "lib" / "python3.12" / "site-packages"
    research_src.mkdir(parents=True)
    research_sp.mkdir(parents=True)
    (research_sp / "usv-research-safety-cpp.egg-link").write_text(f"{research_src}\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", f"{rel_sp}:{research_src}")
    with pytest.raises(SystemExit):
        sup.clean_environment(str(release), str(underlay), identity)

    # 3. 宿主工作空间 --symlink-install 产生的 usv_bringup egg-link 必须被安全剥离，不得泄漏进子进程或阻塞启动
    bringup_build = ws / "build" / "usv_bringup"
    bringup_sp = underlay / "usv_bringup" / "lib" / "python3.12" / "site-packages"
    bringup_build.mkdir(parents=True)
    bringup_sp.mkdir(parents=True)
    (bringup_sp / "usv-bringup.egg-link").write_text(f"{bringup_build}\n.\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", f"{rel_sp}:{bringup_build}/.:{underlay}")
    cleaned_bringup = sup.clean_environment(str(release), str(underlay), identity)
    cleaned_py = [os.path.realpath(p) for p in cleaned_bringup["PYTHONPATH"].split(":") if p]
    assert os.path.realpath(str(bringup_build)) not in cleaned_py
    assert os.path.realpath(str(rel_sp)) in cleaned_py

    # 4. 合法 ntrip_client build 路径若出现在非 PYTHONPATH 变量中仍必须拒绝
    monkeypatch.setenv("PYTHONPATH", f"{rel_sp}:{ntrip_src}")
    monkeypatch.setenv("LD_LIBRARY_PATH", str(ntrip_src))
    with pytest.raises(SystemExit):
        sup.clean_environment(str(release), str(underlay), identity)


def _write_dry_run_contract(run_dir):
    doc = json.loads(open(os.path.join(os.path.dirname(SUPERVISOR), "..", "model", "contract_shipboard_dry_run.json"), encoding="utf-8").read())
    (run_dir / "contract.json").write_text(json.dumps(doc), encoding="utf-8")


def test_checker_accepts_dry_run_with_solves_and_rejects_physical_output(tmp_path):
    release, underlay, run_dir, snap_path = _build_fixture(
        tmp_path, include_shutdown=True, include_summaries=True
    )
    _write_dry_run_contract(run_dir)

    # 重写 supervisor.jsonl + regulator.source.jsonl 为 shipboard_dry_run
    status = _valid_status()
    status["mode"] = "shipboard_dry_run"
    status["jobs_submitted"] = 5
    status["worker"]["completed_jobs"] = 5
    status["dry_run"] = {
        "nav_gate": "ready",
        "nav_ready": True,
        "jobs_submitted": 5,
        "candidates_received": 5,
        "candidates_accepted": 5,
        "candidates_rejected": 0,
        "last_rejection_reason": "",
        "last_backend_ms": 1.1,
        "last_solve_latency_ms": 1.2,
        "last_first_control": [2.0, 2.0],
        "nominal_continuity_n": [2.0, 2.0],
        "physical_output_enabled": False,
        "closed_loop_verified": False,
        "control_inputs_verified": False,
        "anchor_known": False,
    }
    sup_lines = [
        {"schema": SUPERVISOR_SCHEMA, "event": "startup", "invocation_id": "inv-fixture-1",
         "run_id": "run-1", "boot_id": "boot-1", "host_boot_id": "host-1", "at_ns": 1_000_000_000},
        {"schema": SUPERVISOR_SCHEMA, "event": "sample", "invocation_id": "inv-fixture-1",
         "run_id": "run-1", "boot_id": "boot-1", "host_boot_id": "host-1", "at_ns": 2_000_000_000,
         "phase": "ready", "status_received_ns": 2_000_000_000, "worker_capability_received_ns": 2_000_000_000,
         "regulator_status": status, "processes": {}},
        {"schema": SUPERVISOR_SCHEMA, "event": "sample", "invocation_id": "inv-fixture-1",
         "run_id": "run-1", "boot_id": "boot-1", "host_boot_id": "host-1", "at_ns": 3_000_000_000,
         "phase": "ready", "status_received_ns": 3_000_000_000, "worker_capability_received_ns": 3_000_000_000,
         "regulator_status": status, "processes": {}},
        {"schema": SUPERVISOR_SCHEMA, "event": "shutdown", "invocation_id": "inv-fixture-1",
         "run_id": "run-1", "boot_id": "boot-1", "host_boot_id": "host-1", "at_ns": 4_000_000_000,
         "mode": "shipboard_dry_run", "physical_output_enabled": False, "jobs_submitted": 5},
    ]
    (run_dir / "supervisor.jsonl").write_text(
        "\n".join(json.dumps(row) for row in sup_lines) + "\n", encoding="utf-8"
    )
    reg_lines = [
        {"type": "startup", "mode": "shipboard_dry_run", "physical_output_enabled": False,
         "anchor_known": False, "execution_publisher_endpoints": 0,
         "publications": ["/p1/commissioning_status", "/p1/solve_job"]},
        {"type": "dry_run_job", "job_id": 1, "physical_output_enabled": False, "anchor_known": False},
        {"type": "dry_run_decision", "schema": "p1-dry-run-decision-v1", "job_id": 1,
         "accepted": True, "physical_output_enabled": False, "closed_loop_verified": False,
         "anchor_known": False},
        {"type": "source_summary", "generated": 4, "emitted": 4, "dropped": 0, "normal_source_complete": True},
    ]
    (run_dir / "regulator.source.jsonl").write_text(
        "\n".join(json.dumps(row) for row in reg_lines) + "\n", encoding="utf-8"
    )
    wrk_lines = [
        {"type": "candidate", "job": {"job_id": 1}},
        {"type": "worker_summary", "fatal": False, "dry_run_mode": True, "completed_jobs": 5},
    ]
    (run_dir / "worker.source.jsonl").write_text(
        "\n".join(json.dumps(row) for row in wrk_lines) + "\n", encoding="utf-8"
    )

    out_ok = tmp_path / "check-dry-ok.json"
    rc, doc, _ = _run_checker(
        release, underlay, run_dir, snap_path, out_ok, extra_args=("--require-solves",)
    )
    assert rc == 0, doc
    assert doc["verdict"] == "PASS"
    assert doc["mode"] == "shipboard_dry_run"
    assert doc["physical_output_enabled"] is False
    assert doc["closed_loop_verified"] is False

    # 若 startup 出现真实执行话题或 physical_output_enabled=True，checker 必须判 FAIL
    bad_reg = list(reg_lines)
    bad_reg[0] = {**reg_lines[0], "publications": ["/p1/commissioning_status", "/mavros/rc/override"]}
    (run_dir / "regulator.source.jsonl").write_text(
        "\n".join(json.dumps(row) for row in bad_reg) + "\n", encoding="utf-8"
    )
    out_bad = tmp_path / "check-dry-bad.json"
    rc_bad, doc_bad, _ = _run_checker(
        release, underlay, run_dir, snap_path, out_bad, extra_args=("--require-solves",)
    )
    assert rc_bad == 2
    assert any("startup_no_actuator_publishers" in err for err in doc_bad["errors"])


def _write_execute_contract(run_dir):
    doc = json.loads(open(os.path.join(os.path.dirname(SUPERVISOR), "..", "model", "contract_shipboard_execute.json"), encoding="utf-8").read())
    (run_dir / "contract.json").write_text(json.dumps(doc), encoding="utf-8")


def test_checker_accepts_shipboard_execute_and_rejects_bad_execute_logs(tmp_path):
    release, underlay, run_dir, snap_path = _build_fixture(
        tmp_path, include_shutdown=True, include_summaries=True
    )
    _write_execute_contract(run_dir)

    status = _valid_status()
    status["mode"] = "shipboard_execute"
    status["jobs_submitted"] = 4
    status["execution_endpoint_enabled"] = True
    status["water_execution_allowed"] = False
    status["physical_output_enabled"] = True
    status["worker"]["completed_jobs"] = 4
    status["execute"] = {
        "exec_state": "active",
        "control_epoch": 2,
        "jobs_submitted": 4,
        "candidates_received": 4,
        "candidates_accepted": 4,
        "candidates_rejected": 0,
        "continuity_anchor_n": [2.0, 2.0],
        "steering_pwm": 1500,
        "throttle_pwm": 1560,
        "anchor_source": "rc_override_quantized_eff",
        "anchor_modeled": True,
        "hardware_receipt_verified": False,
        "physical_output_enabled": True,
        "water_execution_allowed": False,
    }
    sup_lines = [
        {"schema": SUPERVISOR_SCHEMA, "event": "startup", "invocation_id": "inv-fixture-1",
         "run_id": "run-1", "boot_id": "boot-1", "host_boot_id": "host-1", "at_ns": 1_000_000_000},
        {"schema": SUPERVISOR_SCHEMA, "event": "sample", "invocation_id": "inv-fixture-1",
         "run_id": "run-1", "boot_id": "boot-1", "host_boot_id": "host-1", "at_ns": 2_000_000_000,
         "phase": "ready", "status_received_ns": 2_000_000_000, "worker_capability_received_ns": 2_000_000_000,
         "regulator_status": status, "processes": {}},
        {"schema": SUPERVISOR_SCHEMA, "event": "sample", "invocation_id": "inv-fixture-1",
         "run_id": "run-1", "boot_id": "boot-1", "host_boot_id": "host-1", "at_ns": 3_000_000_000,
         "phase": "ready", "status_received_ns": 3_000_000_000, "worker_capability_received_ns": 3_000_000_000,
         "regulator_status": status, "processes": {}},
        {"schema": SUPERVISOR_SCHEMA, "event": "shutdown", "invocation_id": "inv-fixture-1",
         "run_id": "run-1", "boot_id": "boot-1", "host_boot_id": "host-1", "at_ns": 4_000_000_000,
         "mode": "shipboard_execute", "execution_endpoint_enabled": True, "jobs_submitted": 4},
    ]
    (run_dir / "supervisor.jsonl").write_text(
        "\n".join(json.dumps(row) for row in sup_lines) + "\n", encoding="utf-8"
    )
    reg_lines = [
        {"type": "startup", "mode": "shipboard_execute", "physical_output_enabled": False,
         "execution_endpoint_enabled": True, "anchor_known": False,
         "execution_publisher_endpoints": 2,
         "publications": ["/p1/commissioning_status", "/p1/solve_job", "/mavros/rc/override", "/mpc/status"]},
        {"type": "execute_job", "job_id": 1, "physical_output_enabled": True, "anchor_known": True},
        {"type": "execute_decision", "schema": "p1-execute-decision-v1", "job_id": 1,
         "accepted": True, "anchor_modeled": True, "hardware_receipt_verified": False},
        {"type": "execute_actuation", "schema": "p1-execute-actuation-v1", "directive": "thrust_pwm",
         "steering_pwm": 1500, "throttle_pwm": 1560},
        {"type": "execute_actuation", "schema": "p1-execute-actuation-v1", "directive": "release",
         "steering_pwm": 0, "throttle_pwm": 0},
        {"type": "source_summary", "generated": 5, "emitted": 5, "dropped": 0, "normal_source_complete": True},
    ]
    (run_dir / "regulator.source.jsonl").write_text(
        "\n".join(json.dumps(row) for row in reg_lines) + "\n", encoding="utf-8"
    )
    wrk_lines = [
        {"type": "candidate", "job": {"job_id": 1}},
        {"type": "worker_summary", "fatal": False, "shipboard_execute_mode": True, "completed_jobs": 4},
    ]
    (run_dir / "worker.source.jsonl").write_text(
        "\n".join(json.dumps(row) for row in wrk_lines) + "\n", encoding="utf-8"
    )

    out_ok = tmp_path / "check-exec-ok.json"
    rc, doc, _ = _run_checker(
        release, underlay, run_dir, snap_path, out_ok, extra_args=("--require-solves",)
    )
    assert rc == 0, doc
    assert doc["verdict"] == "PASS"
    assert doc["mode"] == "shipboard_execute"
    assert doc["execution_endpoint_enabled"] is True
    assert doc["closed_loop_verified"] is False

    bad_pwm = list(reg_lines)
    bad_pwm[3] = {**reg_lines[3], "throttle_pwm": 2050}
    (run_dir / "regulator.source.jsonl").write_text(
        "\n".join(json.dumps(row) for row in bad_pwm) + "\n", encoding="utf-8"
    )
    rc_pwm, doc_pwm, _ = _run_checker(release, underlay, run_dir, snap_path, tmp_path / "check-bad-pwm.json")
    assert rc_pwm == 2 and any("execute_pwm_in_bounds" in err for err in doc_pwm["errors"])

    bad_pub = list(reg_lines)
    bad_pub[0] = {**reg_lines[0], "publications": ["/p1/commissioning_status", "/mavros/rc/override", "/mpc/status", "/mavros/setpoint_velocity/cmd_vel"]}
    (run_dir / "regulator.source.jsonl").write_text(
        "\n".join(json.dumps(row) for row in bad_pub) + "\n", encoding="utf-8"
    )
    rc_pub, doc_pub, _ = _run_checker(release, underlay, run_dir, snap_path, tmp_path / "check-bad-pub.json")
    assert rc_pub == 2 and any("startup_no_forbidden_actuator_pubs" in err for err in doc_pub["errors"])

    bad_anchor = list(reg_lines)
    bad_anchor[2] = {**reg_lines[2], "hardware_receipt_verified": True}
    (run_dir / "regulator.source.jsonl").write_text(
        "\n".join(json.dumps(row) for row in bad_anchor) + "\n", encoding="utf-8"
    )
    rc_anc, doc_anc, _ = _run_checker(release, underlay, run_dir, snap_path, tmp_path / "check-bad-anc.json")
    assert rc_anc == 2 and any("execute_decision_honest_anchor" in err for err in doc_anc["errors"])


def test_supervisor_defueled_powered_bench_contract_and_attestation_rules(tmp_path):
    sup = _load_supervisor()
    contract_path = os.path.join(os.path.dirname(SUPERVISOR), "..", "model", "contract_shipboard_execute.json")
    contract_sha = _sha256_file(contract_path)
    doc, mode = sup.verify_contract(contract_path, contract_sha, expected_mode="shipboard_execute")
    assert mode == "shipboard_execute" and doc["qualification"] == "shipboard_defueled_bench_execute"

    # 水下冻结合同必须在 runtime 阶段继续被拒，直到 C3 解锁。
    water_contract = json.loads(open(contract_path, encoding="utf-8").read())
    water_contract["qualification"] = "shipboard_execution_frozen"
    water_contract["execute_qualified"] = True
    water_contract["bench_execution_allowed"] = False
    water_contract["water_execution_allowed"] = True
    water_contract["propellers_removed_required"] = False
    water_path = tmp_path / "water.json"
    water_path.write_text(json.dumps(water_contract), encoding="utf-8")
    with pytest.raises(SystemExit):
        sup.verify_contract(str(water_path), _sha256_file(str(water_path)), expected_mode="shipboard_execute")

    class _DummyArgs:
        mode = "shipboard_execute"

    release = tmp_path / "rel"
    (release / "evidence").mkdir(parents=True)
    att_file = release / "evidence" / "operator-attestation.json"
    valid_att = {
        "attestation_profile": "defueled_powered_bench",
        "vessel_secured": True,
        "no_mission": True,
        "propellers_removed": True,
        "propulsion_power_isolated": False,
        "local_emergency_stop_available": True,
        "valid_until_utc": int((__import__("time").time() + 3600) * 1_000_000_000),
    }

    s = sup.Supervisor.__new__(sup.Supervisor)
    s.release_root = str(release)
    s.runtime_mode = "shipboard_execute"
    s.args = _DummyArgs()
    att_file.write_text(json.dumps(valid_att), encoding="utf-8")
    s._verify_attestation()

    for bad_patch in (
        {"attestation_profile": "commissioning"},
        {"propellers_removed": False},
        {"propulsion_power_isolated": True},
        {"vessel_secured": False},
    ):
        att_file.write_text(json.dumps({**valid_att, **bad_patch}), encoding="utf-8")
        with pytest.raises(SystemExit):
            s._verify_attestation()


def test_supervisor_preflight_rejects_m4_competing_controller_or_publisher(tmp_path, monkeypatch, capsys):
    sup = _load_supervisor()
    env = dict(os.environ)
    env.update({
        "ROS_DOMAIN_ID": "225",
        "ROS_LOCALHOST_ONLY": "1",
        "ROS_AUTOMATIC_DISCOVERY_RANGE": "LOCALHOST",
        "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    monkeypatch.setenv("ROS_DOMAIN_ID", "225")
    monkeypatch.setenv("ROS_LOCALHOST_ONLY", "1")
    monkeypatch.setenv("ROS_AUTOMATIC_DISCOVERY_RANGE", "LOCALHOST")

    ready_flag = tmp_path / "competing.ready"
    competing = subprocess.Popen(
        [sys.executable, "-B", "-c", """
import sys, time, rclpy
from rclpy.node import Node
from mavros_msgs.msg import OverrideRCIn
rclpy.init()
node = Node("mpc_controller_node")
pub = node.create_publisher(OverrideRCIn, "/mavros/rc/override", 10)
with open(sys.argv[1], "w") as fh:
    fh.write("ready")
try:
    end = time.monotonic() + 8.0
    while time.monotonic() < end and rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.05)
        time.sleep(0.05)
except Exception:
    pass
finally:
    if rclpy.ok():
        rclpy.shutdown()
""", str(ready_flag)],
        env=env,
    )
    try:
        deadline = __import__("time").monotonic() + 10.0
        while __import__("time").monotonic() < deadline and not ready_flag.exists():
            __import__("time").sleep(0.05)
        assert ready_flag.exists(), "competing publisher never started"
        s = sup.Supervisor.__new__(sup.Supervisor)
        s.runtime_mode = "shipboard_execute"
        with pytest.raises(SystemExit) as exc:
            s.preflight_graph()
        assert exc.value.code == 1
        assert "M4 violation" in capsys.readouterr().err
    finally:
        competing.terminate()
        competing.wait(timeout=5)


def test_supervisor_run_drains_callbacks_and_supports_soak_limits(tmp_path):
    """回归：run() 必须在采样窗内持续排空多条回调，避免被高频 worker_capability 饿死 status。"""
    sup = _load_supervisor()
    assert sup.STATUS_STALE_NS >= 5_000_000_000
    assert sup.EVIDENCE_LIMIT_BYTES >= 512 * 1024 * 1024

    s = sup.Supervisor.__new__(sup.Supervisor)
    s.failure = ""
    spin_calls = 0
    sample_calls = 0

    class _FakeExecutor:
        def spin_once(self, timeout_sec=0.0):
            nonlocal spin_calls
            spin_calls += 1

    s.executor = _FakeExecutor()
    s.prepare = lambda: None
    s.preflight_graph = lambda: None
    s.make_node = lambda: None
    s.spawn = lambda: None
    s.children = []
    s.record = lambda *a, **kw: None
    s.latest_status = {"phase": "ready"}
    s.ready = True
    s.last_seq = 1

    def _fake_sample():
        nonlocal sample_calls
        sample_calls += 1
        if sample_calls >= 1:
            s.failure = "done_for_test"

    s.sample = _fake_sample
    rc = s.run()
    assert rc == sup.EXIT_FAIL
    assert sample_calls == 1
    assert spin_calls > 5, f"expected continuous draining across 0.8s window, got spin_calls={spin_calls}"

