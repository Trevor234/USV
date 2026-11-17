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

    # 2. 已被覆盖的研究/bringup 包不允许通过 egg-link 绕过
    bringup_src = ws / "build" / "usv_bringup" / "src"
    bringup_sp = underlay / "usv_bringup" / "lib" / "python3.12" / "site-packages"
    bringup_src.mkdir(parents=True)
    bringup_sp.mkdir(parents=True)
    (bringup_sp / "usv-bringup.egg-link").write_text(f"{bringup_src}\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", f"{rel_sp}:{bringup_src}")
    with pytest.raises(SystemExit):
        sup.clean_environment(str(release), str(underlay), identity)

    # 3. 合法 ntrip_client build 路径若出现在非 PYTHONPATH 变量中仍必须拒绝
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
