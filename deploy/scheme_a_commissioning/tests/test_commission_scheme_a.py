"""维护 driver 的行为反证。

这些用例验证的是**外部效果**：命令次序、文件字节、systemd 状态转换，而不是源码
字符串。全部在临时 unit 目录 + 可替换命令执行器上跑，不触碰真实 systemd、不打开
串口、不重启任何服务。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER_PATH = os.path.join(os.path.dirname(HERE), "commission_scheme_a.py")


def load_driver():
    spec = importlib.util.spec_from_file_location("commission_scheme_a", DRIVER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["commission_scheme_a"] = module
    spec.loader.exec_module(module)
    return module


driver_module = load_driver()


class FakeRunner:
    """记录调用次序；systemctl 的结果由用例注入。"""

    def __init__(self, service_states=None, fail_verify=False, unit_dir=None,
                 runtime_unit_dir=None, unit_name="usv-system.service"):
        self.calls = []
        self.service_states = service_states or {}
        self.fail_verify = fail_verify
        self.unit_dir = unit_dir
        self.runtime_unit_dir = runtime_unit_dir
        self.unit_name = unit_name
        self._state_index = 0

    def _dropin_overrides(self):
        """按 systemd 语义：/run 与 /etc drop-in 按文件名合并，后者覆盖前者。"""
        overrides = {}
        entries = []
        for is_runtime, base in ((True, self.runtime_unit_dir), (False, self.unit_dir)):
            if not base:
                continue
            dropin_dir = os.path.join(base, f"{self.unit_name}.d")
            try:
                names = os.listdir(dropin_dir)
            except OSError:
                continue
            for name in names:
                if name.endswith(".conf"):
                    entries.append((name, 0 if is_runtime else 1, os.path.join(dropin_dir, name)))
        for _name, _prio, path in sorted(entries):
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("Restart="):
                        overrides["Restart"] = line.split("=", 1)[1].strip()
                    if line.startswith("ConditionPathExists="):
                        overrides["ConditionPathExists"] = line.split("=", 1)[1].strip()
                    if line.startswith("ExecCondition="):
                        overrides["ExecCondition"] = line.split("=", 1)[1].strip()
                    if line.startswith("ExecStart=") and \
                            not line.strip() == "ExecStart=":
                        overrides["ExecStart"] = line.split("=", 1)[1].strip()
        return overrides

    def run(self, argv, timeout=60, env=None, check=False):
        self.calls.append(list(argv))
        if argv[0] == "systemctl" and "show" in argv:
            unit = argv[2]
            state = dict(self.service_states.get(unit, {}))
            state.update(self._dropin_overrides())
            lines = [f"{key}={value}" for key, value in state.items()]
            return {"argv": list(argv), "rc": 0, "stdout": "\n".join(lines), "stderr": ""}
        if argv[0] == "systemctl" and "stop" in argv:
            unit = argv[2]
            self.service_states.setdefault(unit, {})["ActiveState"] = "inactive"
            self.service_states.setdefault(unit, {})["MainPID"] = "0"
            return {"argv": list(argv), "rc": 0, "stdout": "", "stderr": ""}
        if argv[0] == "systemctl" and "start" in argv:
            unit = argv[2]
            svc = self.service_states.setdefault(unit, {})
            svc["ActiveState"] = "active"
            svc.setdefault("InvocationID", "inv-default-1")
            return {"argv": list(argv), "rc": 0, "stdout": "", "stderr": ""}
        if argv[0] == "systemd-analyze":
            rc = 1 if self.fail_verify else 0
            return {"argv": list(argv), "rc": rc, "stdout": "",
                    "stderr": "bad unit" if self.fail_verify else ""}
        if argv[0] == "runuser":
            return {"argv": list(argv), "rc": 0, "stdout": json.dumps(
                {"ok": True, "samples": 12, "connected": True, "armed": False,
                 "mode": "HOLD", "modes": ["HOLD"], "safe_hold": True}), "stderr": ""}
        return {"argv": list(argv), "rc": 0, "stdout": "", "stderr": ""}

    def trail(self):
        return [" ".join(call) for call in self.calls]


@pytest.fixture(autouse=True)
def hermetic_host(monkeypatch):
    """driver 会读真实 /proc 与网卡设备；测试必须与宿主状态解耦。

    Pi 上生产 usv-system 正在运行并持有 /dev/ttyAMA10，若不隔离，driver 会(正确地)
    拒绝继续 —— 那是真实行为的正确表现，但不该让单测结果依赖宿主。
    """
    monkeypatch.setattr(driver_module.Driver, "cgroup_pids", lambda self, unit: [])
    monkeypatch.setattr(driver_module.Driver, "serial_holders", lambda self: {})
    return None


ATEST = {
    "operator": "现场操作者",
    "confirmed_at_utc": 1,
    "valid_until_utc": 1 << 62,
    "vessel_secured": True,
    "no_mission": True,
    "propulsion_power_isolated": True,
    "local_emergency_stop_available": True,
}


def build_release(tmp_path, monkeypatch, with_attestation=True):
    release = tmp_path / "release"
    evidence = release / "evidence"
    evidence.mkdir(parents=True)
    (release / "deploy").mkdir()
    (release / "install" / "usv_research_safety_cpp" / "lib"
     / "usv_research_safety_cpp").mkdir(parents=True)
    (release / "runs").mkdir()
    (release / "capsule").mkdir()
    if with_attestation:
        (evidence / "operator-attestation.json").write_text(json.dumps(ATEST))
    (release / "deploy" / "commission_scheme_a.py").write_text("# driver\n")
    (release / "deploy" / "30-scheme-a-commissioning.conf.in").write_text(
        "[Unit]\n"
        "ConditionPathExists=@TOKEN_PATH@\n"
        "\n"
        "[Service]\n"
        "Restart=no\n"
        "ExecCondition=+/usr/bin/python3 -B @RELEASE_ROOT@/deploy/commission_scheme_a.py\n"
        "ExecStart=\n"
        "ExecStart=/bin/bash -c 'ros2 launch usv_bringup real.launch.py "
        "controller_backend:=research_commissioning "
        "commissioning_release_root:=@RELEASE_ROOT@ "
        "commissioning_underlay:=@UNDERLAY@ scheme:=${SCHEME}'\n")
    artifacts = {"artifacts": [{"path": "deploy/commission_scheme_a.py",
                                "sha256": driver_module.sha256_file(
                                    str(release / "deploy" / "commission_scheme_a.py"))}]}
    (evidence / "release_artifacts.json").write_text(json.dumps(artifacts))
    (evidence / "source_hashes.json").write_text("{}")
    (evidence / "install_manifest.json").write_text("{}")
    identity = {
        "source_hashes_sha256": driver_module.sha256_file(
            str(evidence / "source_hashes.json")),
        "install_manifest_sha256": driver_module.sha256_file(
            str(evidence / "install_manifest.json")),
        "release_artifacts_sha256": driver_module.sha256_file(
            str(evidence / "release_artifacts.json")),
        "underlay_identity_sha256": "u" * 64,
        "ros_domain_id": 0,
        "dds_profile_path": str(tmp_path / "fastdds_lan.xml"),
        "dropin_template_sha256": driver_module.sha256_file(
            str(release / "deploy" / "30-scheme-a-commissioning.conf.in")),
    }
    (tmp_path / "fastdds_lan.xml").write_text("<dds/>")
    identity["dds_profile_sha256"] = driver_module.sha256_file(str(tmp_path / "fastdds_lan.xml"))
    (evidence / "release_identity.json").write_text(json.dumps(identity))
    underlay = tmp_path / "underlay"
    underlay.mkdir()
    (underlay / "local_setup.bash").write_text("#\n")
    (release / "deploy" / "probe_fcu_state.py").write_text("# probe\n")
    (release / "deploy" / "capture_release_identity.py").write_text("# capture\n")
    return str(release), str(underlay), str(evidence)


def make_args(monkeypatch, release, underlay, evidence, action, attestation=None):
    monkeypatch.setattr(driver_module, "host_boot_id", lambda: "boot-1")
    monkeypatch.setattr(driver_module, "now_utc_ns", lambda: 1000)
    args = driver_module.parse_args([
        "--release-root", release, "--underlay", underlay,
        "--operator-attestation", attestation or os.path.join(
            release, "evidence", "operator-attestation.json"),
        "--action", action, "--evidence-dir", evidence])
    return args


# ------------------------------------------------------------- check-start
def test_check_start_rejects_missing_token(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    token = tmp_path / "token"
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "check-start"),
                                  runner=FakeRunner(), unit_dir=str(tmp_path / "units"),
                                  token_path=str(token))
    assert driver.action_check_start() == driver_module.EXIT_REJECT


def test_check_start_rejects_wrong_owner_and_mode(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    token = tmp_path / "token"
    token.write_text("{}")
    os.chmod(token, 0o644)
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "check-start"),
                                  runner=FakeRunner(), unit_dir=str(tmp_path / "units"),
                                  token_path=str(token))
    assert driver.action_check_start() == driver_module.EXIT_REJECT


def test_check_start_rejects_wrong_boot_and_expiry(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    token = tmp_path / "token"
    body = {"release_id": os.path.basename(release), "host_boot_id": "other-boot",
            "attestation_sha256": driver_module.sha256_file(
                os.path.join(release, "evidence", "operator-attestation.json")),
            "release_artifacts_sha256": driver_module.sha256_file(
                os.path.join(release, "evidence", "release_artifacts.json")),
            "underlay_identity_sha256": "u" * 64, "valid_until_utc": 1 << 62}
    token.write_text(json.dumps(body))
    os.chmod(token, 0o600)
    if os.geteuid() == 0:
        os.chown(token, 0, 0)
    else:
        pytest.skip("token ownership check needs root; covered on the real host")
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "check-start"),
                                  runner=FakeRunner(), unit_dir=str(tmp_path / "units"),
                                  token_path=str(token))
    assert driver.action_check_start() == driver_module.EXIT_REJECT


def test_check_start_takes_no_lock_and_writes_nothing(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    token = tmp_path / "token"
    lock = tmp_path / "lock"
    body = {"release_id": os.path.basename(release), "host_boot_id": "boot-1",
            "attestation_sha256": driver_module.sha256_file(
                os.path.join(release, "evidence", "operator-attestation.json")),
            "release_artifacts_sha256": driver_module.sha256_file(
                os.path.join(release, "evidence", "release_artifacts.json")),
            "underlay_identity_sha256": "u" * 64, "valid_until_utc": 1 << 62}
    token.write_text(json.dumps(body))
    os.chmod(token, 0o600)
    if os.geteuid() != 0:
        pytest.skip("token ownership check needs root")
    os.chown(token, 0, 0)
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "check-start"),
                                  runner=FakeRunner(), unit_dir=str(tmp_path / "units"),
                                  token_path=str(token), lock_path=str(lock))
    assert driver.action_check_start() == driver_module.EXIT_OK
    assert not lock.exists()


# ---------------------------------------------------------------- 声明
def test_takeover_refuses_attestation_outside_release(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    other = tmp_path / "other.json"
    other.write_text(json.dumps(ATEST))
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "takeover", attestation=str(other)),
                                  runner=FakeRunner(), unit_dir=str(tmp_path / "units"))
    with pytest.raises(driver_module.DriverError):
        driver.action_takeover()


def test_takeover_refuses_missing_flags_and_expiry(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    path = os.path.join(release, "evidence", "operator-attestation.json")
    bad = dict(ATEST)
    bad["propulsion_power_isolated"] = False
    open(path, "w").write(json.dumps(bad))
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "takeover"),
                                  runner=FakeRunner(), unit_dir=str(tmp_path / "units"))
    with pytest.raises(driver_module.DriverError):
        driver.action_takeover()
    expired = dict(ATEST)
    expired["valid_until_utc"] = 1
    open(path, "w").write(json.dumps(expired))
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "takeover"),
                                  runner=FakeRunner(), unit_dir=str(tmp_path / "units"))
    with pytest.raises(driver_module.DriverError):
        driver.action_takeover()


# --------------------------------------------------------------- takeover
def test_takeover_refuses_when_state_gate_fails(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)

    class ArmedRunner(FakeRunner):
        def run(self, argv, timeout=60, env=None, check=False):
            if argv[0] == "runuser":
                self.calls.append(list(argv))
                return {"argv": list(argv), "rc": 0,
                        "stdout": json.dumps({"ok": True, "samples": 5, "connected": True,
                                              "armed": True, "mode": "HOLD",
                                              "modes": ["HOLD"], "safe_hold": False}),
                        "stderr": ""}
            return super().run(argv, timeout=timeout, env=env, check=check)

    runner = ArmedRunner()
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "takeover"),
                                  runner=runner, unit_dir=str(tmp_path / "units"),
                                  token_path=str(tmp_path / "token"),
                                  lock_path=str(tmp_path / "lock"))
    with pytest.raises(driver_module.DriverError):
        driver.action_takeover()
    # armed=true 时绝不允许停旧服务。
    assert not any(call.startswith("systemctl stop") for call in runner.trail())


def test_takeover_order_and_token_lifecycle(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    units = tmp_path / "units"
    units.mkdir()
    states = {"usv-system.service": {"ActiveState": "active", "SubState": "running",
                                     "MainPID": "1255", "NRestarts": "0",
                                     "ControlGroup": "/system.slice/usv-system.service",
                                     "UnitFileState": "enabled"}}
    runner = FakeRunner(service_states=states, unit_dir=str(units))
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "takeover"),
                                  runner=runner, unit_dir=str(units),
                                  token_path=str(tmp_path / "token"),
                                  lock_path=str(tmp_path / "lock"))
    # 验收需要 supervisor ready；这里只验证次序与 token 生命周期，故让验收失败。
    monkeypatch.setattr(driver, "_wait_for_ready",
                        lambda identity, deadline=None: (_ for _ in ()).throw(
                            driver_module.DriverError("no supervisor")))
    with pytest.raises(driver_module.DriverError):
        driver.action_takeover()
    trail = runner.trail()
    stop_index = next(i for i, call in enumerate(trail) if call.startswith("systemctl stop"))
    reload_index = next(i for i, call in enumerate(trail) if "daemon-reload" in call)
    start_index = next(i for i, call in enumerate(trail) if call.startswith("systemctl start"))
    assert stop_index < reload_index < start_index
    # 30 文件已按本批字节安装
    dropin = units / "usv-system.service.d" / "30-scheme-a-commissioning.conf"
    assert dropin.is_file()
    body = dropin.read_text()
    assert "research_commissioning" in body and "Restart=no" in body
    assert "ExecCondition=+" in body
    # 失败也撤 token：不留可被再次拉起的口子
    assert not (tmp_path / "token").exists()


def test_takeover_does_not_overwrite_existing_dropin(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    units = tmp_path / "units"
    (units / "usv-system.service.d").mkdir(parents=True)
    existing = units / "usv-system.service.d" / "30-scheme-a-commissioning.conf"
    existing.write_text("[Service]\nRestart=always\n")
    runner = FakeRunner(service_states={"usv-system.service": {
        "ActiveState": "active", "MainPID": "1", "NRestarts": "0",
        "ControlGroup": "/system.slice/usv-system.service"}},
        unit_dir=str(units))
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "takeover"),
                                  runner=runner, unit_dir=str(units),
                                  token_path=str(tmp_path / "token"),
                                  lock_path=str(tmp_path / "lock"))
    with pytest.raises(driver_module.DriverError):
        driver.action_takeover()
    assert existing.read_text() == "[Service]\nRestart=always\n"


def test_takeover_refuses_when_cgroup_not_empty(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    runner = FakeRunner(service_states={"usv-system.service": {
        "ActiveState": "active", "MainPID": "1", "NRestarts": "0",
        "ControlGroup": "/system.slice/usv-system.service"}},
        )
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "takeover"),
                                  runner=runner, unit_dir=str(tmp_path / "units"),
                                  token_path=str(tmp_path / "token"),
                                  lock_path=str(tmp_path / "lock"))
    monkeypatch.setattr(driver, "cgroup_pids", lambda unit: [4242])
    with pytest.raises(driver_module.DriverError):
        driver.action_takeover()


def test_takeover_refuses_when_serial_still_held(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    runner = FakeRunner(service_states={"usv-system.service": {
        "ActiveState": "active", "MainPID": "1", "NRestarts": "0",
        "ControlGroup": "/system.slice/usv-system.service"}},
        )
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "takeover"),
                                  runner=runner, unit_dir=str(tmp_path / "units"),
                                  token_path=str(tmp_path / "token"),
                                  lock_path=str(tmp_path / "lock"))
    monkeypatch.setattr(driver, "cgroup_pids", lambda unit: [])
    monkeypatch.setattr(driver, "serial_holders",
                        lambda: {"/dev/ttyAMA10": [4242]})
    with pytest.raises(driver_module.DriverError):
        driver.action_takeover()


def test_takeover_stops_after_verify_failure(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    runner = FakeRunner(service_states={"usv-system.service": {
        "ActiveState": "active", "MainPID": "1", "NRestarts": "0",
        "ControlGroup": "/system.slice/usv-system.service"}},
        fail_verify=True)
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "takeover"),
                                  runner=runner, unit_dir=str(tmp_path / "units"),
                                  token_path=str(tmp_path / "token"),
                                  lock_path=str(tmp_path / "lock"))
    with pytest.raises(driver_module.DriverError):
        driver.action_takeover()
    assert not any(call.startswith("systemctl start") for call in runner.trail())


# --------------------------------------------------------------- rollback
def test_rollback_keeps_31_protection_when_b_fails(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    units = tmp_path / "units"
    run_units = tmp_path / "run_units"
    (units / "usv-system.service.d").mkdir(parents=True)
    dropin = units / "usv-system.service.d" / "30-scheme-a-commissioning.conf"
    dropin.write_text("[Service]\nRestart=no\n")
    runner = FakeRunner(service_states={"usv-system.service": {
        "ActiveState": "active", "MainPID": "1", "NRestarts": "0",
        "ControlGroup": "/system.slice/usv-system.service"}},
        unit_dir=str(units), runtime_unit_dir=str(run_units))
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "rollback"),
                                  runner=runner, unit_dir=str(units),
                                  runtime_unit_dir=str(run_units),
                                  token_path=str(tmp_path / "token"),
                                  lock_path=str(tmp_path / "lock"))
    monkeypatch.setattr(driver, "cgroup_pids", lambda unit: [])
    monkeypatch.setattr(driver, "serial_holders", lambda: {})
    monkeypatch.setattr(driver, "_verify_original_b",
                        lambda identity: {"problems": ["b did not come up"]})
    assert driver.action_rollback() == driver_module.EXIT_FAIL
    # 31 保护必须落在 runtime_unit_dir (/run/systemd/system/...)，且不得落地 /etc/...
    protection = run_units / "usv-system.service.d" / "31-scheme-a-rollback-no-restart.conf"
    assert protection.is_file()
    assert "Restart=no" in protection.read_text()
    assert not (units / "usv-system.service.d" / "31-scheme-a-rollback-no-restart.conf").exists()
    assert not dropin.exists()


def test_rollback_removes_31_only_after_b_passes(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    units = tmp_path / "units"
    run_units = tmp_path / "run_units"
    (units / "usv-system.service.d").mkdir(parents=True)
    dropin = units / "usv-system.service.d" / "30-scheme-a-commissioning.conf"
    dropin.write_text("[Service]\nRestart=no\n")
    runner = FakeRunner(service_states={"usv-system.service": {
        "ActiveState": "active", "MainPID": "1", "NRestarts": "0",
        "ControlGroup": "/system.slice/usv-system.service"}},
        unit_dir=str(units), runtime_unit_dir=str(run_units))
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "rollback"),
                                  runner=runner, unit_dir=str(units),
                                  runtime_unit_dir=str(run_units),
                                  token_path=str(tmp_path / "token"),
                                  lock_path=str(tmp_path / "lock"))
    monkeypatch.setattr(driver, "cgroup_pids", lambda unit: [])
    monkeypatch.setattr(driver, "serial_holders", lambda: {})
    monkeypatch.setattr(driver, "_verify_original_b",
                        lambda identity: {"problems": []})
    # 撤掉 31 之后 Restart 必须回到原策略；假 runner 从现存 drop-in 推导，
    # 因此先把"原 unit 里的 Restart=always"补进基线状态。
    runner.service_states["usv-system.service"]["Restart"] = "always"
    assert driver.action_rollback() == driver_module.EXIT_OK
    protection = run_units / "usv-system.service.d" / "31-scheme-a-rollback-no-restart.conf"
    assert not protection.exists()


def test_rollback_refuses_foreign_dropin_bytes(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    units = tmp_path / "units"
    run_units = tmp_path / "run_units"
    (units / "usv-system.service.d").mkdir(parents=True)
    dropin = units / "usv-system.service.d" / "30-scheme-a-commissioning.conf"
    dropin.write_text("[Service]\nRestart=no\n")
    runner = FakeRunner(service_states={"usv-system.service": {
        "ActiveState": "active", "MainPID": "1", "NRestarts": "0",
        "ControlGroup": "/system.slice/usv-system.service"}},
        unit_dir=str(units), runtime_unit_dir=str(run_units))
    driver = driver_module.Driver(make_args(monkeypatch, release, underlay, evidence,
                                            "rollback"),
                                  runner=runner, unit_dir=str(units),
                                  runtime_unit_dir=str(run_units),
                                  token_path=str(tmp_path / "token"),
                                  lock_path=str(tmp_path / "lock"))
    monkeypatch.setattr(driver, "cgroup_pids", lambda unit: [])
    monkeypatch.setattr(driver, "serial_holders", lambda: {})
    monkeypatch.setattr(driver, "_verify_original_b", lambda identity: {"problems": []})
    # 在 driver 取完摘要后改写字节 → 必须拒绝删除
    original_sha = driver_module.sha256_file(str(dropin))

    def tamper(expected_sha, name=None, runtime=False):
        return driver_module.Driver.remove_dropin_if_ours(
            driver, "0" * 64, name or driver_module.DROPIN_NAME, runtime=runtime)

    monkeypatch.setattr(driver, "remove_dropin_if_ours",
                        lambda expected_sha, name=driver_module.DROPIN_NAME, runtime=False:
                        tamper(expected_sha, name, runtime=runtime))
    with pytest.raises(driver_module.DriverError):
        driver.action_rollback()
    assert dropin.exists()
    assert dropin.read_text() == "[Service]\nRestart=no\n"
    assert original_sha


def test_takeover_requires_evidence_dir():
    assert driver_module.main([
        "--release-root", "/tmp/x", "--underlay", "/tmp/y",
        "--operator-attestation", "/tmp/z", "--action", "takeover"]) == driver_module.EXIT_FAIL


# --------------------------------------------------- F1 / F3 / F4 回归验证
def test_acceptance_waits_for_ready_by_invocation_id_before_t0(tmp_path, monkeypatch):
    """F1+F3：先按 InvocationID 等 ready（无视其它排序更靠前的旧 run 目录），之后再采 t0→60s→t60。"""
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    checker_path = (
        tmp_path / "release" / "install" / "usv_research_safety_cpp" / "lib"
        / "usv_research_safety_cpp" / "check_shipboard_commissioning.py"
    )
    checker_path.write_text("# checker\n")
    # 构造一个字典序更大、且早已 ready 的陈旧 run 目录，验证 driver 不会误选它。
    stale_run = tmp_path / "release" / "runs" / "zzzz-stale-run"
    stale_run.mkdir()
    (stale_run / "supervisor.jsonl").write_text(
        json.dumps({"event": "sample", "phase": "ready"}) + "\n"
    )
    target_inv = "inv-target-001"
    target_run = tmp_path / "release" / "runs" / target_inv
    target_run.mkdir()
    sup_log = target_run / "supervisor.jsonl"
    sup_log.write_text(json.dumps({"event": "startup"}) + "\n")

    timeline = []

    class ReadySequenceRunner(FakeRunner):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._polls = 0

        def run(self, argv, timeout=60, env=None, check=False):
            if argv[0] == "systemctl" and "show" in argv:
                self._polls += 1
                timeline.append(("show", self._polls))
                # 第 2 次轮询才把 target_inv 的 supervisor.jsonl 推进到 ready
                if self._polls == 2:
                    with open(sup_log, "a", encoding="utf-8") as handle:
                        handle.write(json.dumps({"event": "sample", "phase": "ready"}) + "\n")
            return super().run(argv, timeout=timeout, env=env, check=check)

    units = tmp_path / "units"
    units.mkdir()
    runner = ReadySequenceRunner(
        service_states={"usv-system.service": {
            "ActiveState": "active", "NRestarts": "0",
            "InvocationID": target_inv,
            "ControlGroup": "/system.slice/usv-system.service",
        }},
        unit_dir=str(units),
    )
    driver = driver_module.Driver(
        make_args(monkeypatch, release, underlay, evidence, "takeover"),
        runner=runner, unit_dir=str(units),
        token_path=str(tmp_path / "token"), lock_path=str(tmp_path / "lock"),
    )
    driver.begin_transaction()
    monkeypatch.setattr(driver_module, "ACCEPTANCE_SECONDS", 0.01)

    def fake_capture(identity, path, with_maps):
        timeline.append(("capture", os.path.basename(path)))
        snap = {"processes": [{"pid": 2001, "starttime": "100"}]}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(snap, handle)
        return snap

    monkeypatch.setattr(driver, "capture_snapshot", fake_capture)
    outcome = driver.acceptance({"ros_domain_id": 0, "dds_profile_path": "/dev/null"}, "commissioning")
    assert outcome["problems"] == []
    assert os.path.realpath(outcome["run_dir"]) == os.path.realpath(str(target_run))
    t0_idx = timeline.index(("capture", "commissioning-t0.json"))
    t60_idx = timeline.index(("capture", "commissioning-t60.json"))
    # ready 在第 2 次 show 才写入，因此 t0 必然落在第 2 次 show 之后、且在 t60 之前
    second_show_idx = [i for i, item in enumerate(timeline) if item == ("show", 2)][0]
    assert second_show_idx < t0_idx < t60_idx
    # checker 调用必须携带 --proc-snapshot commissioning-t60.json 与 --expect-active
    checker_call = [c for c in runner.calls if "check_shipboard_commissioning.py" in " ".join(c)]
    assert len(checker_call) == 1
    assert "--proc-snapshot" in checker_call[0]
    assert outcome["t60"] in checker_call[0]
    assert "--expect-active" in checker_call[0]


def test_wait_for_ready_fails_immediately_on_supervisor_failure_event(tmp_path, monkeypatch):
    """F3：supervisor.jsonl 出现 failure 事件必须立即抛出 DriverError，绝不当成 ready。"""
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    inv_id = "inv-fail-999"
    run_dir = tmp_path / "release" / "runs" / inv_id
    run_dir.mkdir()
    (run_dir / "supervisor.jsonl").write_text(
        json.dumps({"event": "startup"}) + "\n"
        + json.dumps({"event": "failure", "reason": "commissioning_imu_timeout"}) + "\n"
    )
    runner = FakeRunner(service_states={"usv-system.service": {
        "ActiveState": "active", "InvocationID": inv_id}})
    driver = driver_module.Driver(
        make_args(monkeypatch, release, underlay, evidence, "takeover"),
        runner=runner, unit_dir=str(tmp_path / "units"),
    )
    with pytest.raises(driver_module.DriverError, match="commissioning_imu_timeout"):
        driver._wait_for_ready({})


def test_rollback_verifies_b_t0_sleep_t60_without_overwrite(tmp_path, monkeypatch):
    """F4：_verify_original_b 必须先写 t0、等待、再带 --baseline t0 写 t60（不触发禁止覆盖）。"""
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    units = tmp_path / "units"
    run_units = tmp_path / "run_units"
    (units / "usv-system.service.d").mkdir(parents=True)
    dropin = units / "usv-system.service.d" / "30-scheme-a-commissioning.conf"
    dropin.write_text("[Service]\nRestart=no\n")

    capture_calls = []

    class NoOverwriteCaptureRunner(FakeRunner):
        def run(self, argv, timeout=60, env=None, check=False):
            if argv[0] == "runuser" and "capture_release_identity.py" in " ".join(argv):
                self.calls.append(list(argv))
                out_path = argv[argv.index("--output") + 1]
                baseline_arg = argv[argv.index("--baseline") + 1] if "--baseline" in argv else None
                if os.path.exists(out_path):
                    return {"argv": list(argv), "rc": 2, "stdout": "", "stderr": "refuse overwrite"}
                with open(out_path, "w", encoding="utf-8") as handle:
                    json.dump({"identity_ok": True}, handle)
                capture_calls.append((os.path.basename(out_path), baseline_arg))
                return {"argv": list(argv), "rc": 0, "stdout": "", "stderr": ""}
            return super().run(argv, timeout=timeout, env=env, check=check)

    runner = NoOverwriteCaptureRunner(
        service_states={"usv-system.service": {
            "ActiveState": "active", "MainPID": "1255", "NRestarts": "0",
            "Restart": "always", "ControlGroup": "/system.slice/usv-system.service"}},
        unit_dir=str(units), runtime_unit_dir=str(run_units),
    )
    driver = driver_module.Driver(
        make_args(monkeypatch, release, underlay, evidence, "rollback"),
        runner=runner, unit_dir=str(units), runtime_unit_dir=str(run_units),
        token_path=str(tmp_path / "token"), lock_path=str(tmp_path / "lock"),
    )
    monkeypatch.setattr(driver, "cgroup_pids", lambda unit: [])
    monkeypatch.setattr(driver, "serial_holders", lambda: {})
    monkeypatch.setattr(driver_module, "B_STARTUP_SECONDS", 0.01)
    monkeypatch.setattr(driver_module, "B_SETTLE_SECONDS", 0.0)
    monkeypatch.setattr(driver_module, "ACCEPTANCE_SECONDS", 0.01)

    assert driver.action_rollback() == driver_module.EXIT_OK
    assert len(capture_calls) == 2
    assert capture_calls[0][0] == "rollback-t0.json" and capture_calls[0][1] is None
    assert capture_calls[1][0] == "rollback-t60.json"
    assert capture_calls[1][1] and capture_calls[1][1].endswith("rollback-t0.json")
    assert not (run_units / "usv-system.service.d" / "31-scheme-a-rollback-no-restart.conf").exists()


def test_runner_resolves_runuser_from_sbin_when_env_path_is_minimal():
    if not os.path.exists("/usr/sbin/runuser") and not os.path.exists("/sbin/runuser"):
        pytest.skip("runuser not installed on this host")
    runner = driver_module.Runner()
    res = runner.run(["runuser", "--version"], timeout=10, env={"PATH": "/usr/local/bin:/usr/bin:/bin"})
    assert res["rc"] == 0, res
    assert "runuser" in res["stdout"]


def test_ros_env_collects_package_python_and_lib_dirs(tmp_path):
    release = tmp_path / "rel"
    underlay = tmp_path / "underlay"
    (release / "install" / "usv_bringup" / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    (release / "install" / "usv_acados" / "lib").mkdir(parents=True)
    (underlay / "usv_nmpc" / "lib").mkdir(parents=True)
    args = driver_module.parse_args([
        "--release-root", str(release),
        "--underlay", str(underlay),
        "--operator-attestation", str(release / "evidence" / "operator-attestation.json"),
        "--action", "check-start",
    ])
    driver = driver_module.Driver(args, runner=FakeRunner())
    env = driver.ros_env({"ros_domain_id": 0, "dds_profile_path": "/dev/null"})
    assert str(release / "install" / "usv_bringup" / "lib" / "python3.12" / "site-packages") in env["PYTHONPATH"].split(":")
    assert str(release / "install" / "usv_acados" / "lib") in env["LD_LIBRARY_PATH"].split(":")
    assert str(underlay / "usv_nmpc" / "lib") in env["LD_LIBRARY_PATH"].split(":")
    assert str(underlay / "usv_nmpc") in env["AMENT_PREFIX_PATH"].split(":")
    if os.path.isdir("/opt/ros/jazzy/lib"):
        assert "/opt/ros/jazzy" in env["AMENT_PREFIX_PATH"].split(":")
        assert any(p.startswith("/opt/ros/jazzy/lib/python") for p in env["PYTHONPATH"].split(":"))


def test_rollback_waits_for_b_mpc_node_and_backend_log_before_t0(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    units = tmp_path / "units"
    run_units = tmp_path / "run_units"
    (units / "usv-system.service.d").mkdir(parents=True)
    (units / "usv-system.service.d" / "30-scheme-a-commissioning.conf").write_text("[Service]\nRestart=no\n")

    timeline = []
    polls = {"count": 0}

    class WaitBRunner(FakeRunner):
        def run(self, argv, timeout=60, env=None, check=False):
            if argv[0] == "journalctl":
                self.calls.append(list(argv))
                timeline.append(("journalctl", polls["count"]))
                out = "backend=acados\n" if polls["count"] >= 2 else "starting...\n"
                return {"argv": list(argv), "rc": 0, "stdout": out, "stderr": ""}
            if argv[0] == "runuser" and "capture_release_identity.py" in " ".join(argv):
                self.calls.append(list(argv))
                out_path = argv[argv.index("--output") + 1]
                timeline.append(("capture", os.path.basename(out_path), polls["count"]))
                with open(out_path, "w", encoding="utf-8") as handle:
                    json.dump({"identity_ok": True}, handle)
                return {"argv": list(argv), "rc": 0, "stdout": "", "stderr": ""}
            return super().run(argv, timeout=timeout, env=env, check=check)

    runner = WaitBRunner(
        service_states={"usv-system.service": {
            "ActiveState": "active", "MainPID": "2200", "NRestarts": "0",
            "InvocationID": "b-inv-42", "Restart": "always",
            "ControlGroup": "/system.slice/usv-system.service"}},
        unit_dir=str(units), runtime_unit_dir=str(run_units),
    )
    driver = driver_module.Driver(
        make_args(monkeypatch, release, underlay, evidence, "rollback"),
        runner=runner, unit_dir=str(units), runtime_unit_dir=str(run_units),
        token_path=str(tmp_path / "token"), lock_path=str(tmp_path / "lock"),
    )

    def fake_pids(unit):
        if runner.service_states["usv-system.service"].get("ActiveState") != "active":
            return []
        polls["count"] += 1
        return [] if polls["count"] == 1 else [9001]

    orig_readlink = os.readlink
    monkeypatch.setattr(driver, "cgroup_pids", fake_pids)
    monkeypatch.setattr(driver, "serial_holders", lambda: {})
    monkeypatch.setattr(os, "readlink", lambda p: "/opt/usv/lib/usv_nmpc/mpc_node" if p == "/proc/9001/exe" else orig_readlink(p))
    monkeypatch.setattr(driver_module, "B_STARTUP_SECONDS", 5.0)
    monkeypatch.setattr(driver_module, "B_SETTLE_SECONDS", 0.0)
    monkeypatch.setattr(driver_module, "ACCEPTANCE_SECONDS", 0.01)

    assert driver.action_rollback() == driver_module.EXIT_OK
    t0_event = [item for item in timeline if item[0] == "capture" and item[1] == "rollback-t0.json"][0]
    assert t0_event[2] >= 2


def test_effective_reads_condition_path_from_systemctl_cat_when_show_omits_it(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)

    class RealSystemdShowRunner(FakeRunner):
        def run(self, argv, timeout=60, env=None, check=False):
            if argv[0] == "systemctl" and "show" in argv:
                return {
                    "argv": list(argv),
                    "rc": 0,
                    "stdout": "Restart=no\nExecStart=research_commissioning\n",
                    "stderr": "",
                }
            if argv[0] == "systemctl" and "cat" in argv:
                return {
                    "argv": list(argv),
                    "rc": 0,
                    "stdout": (
                        "# /etc/systemd/system/usv-system.service.d/30-scheme-a-commissioning.conf\n"
                        "[Unit]\n"
                        "ConditionPathExists=/run/usv-scheme-a-commissioning-authorized\n"
                        "[Service]\n"
                        "Restart=no\n"
                    ),
                    "stderr": "",
                }
            return super().run(argv, timeout=timeout, env=env, check=check)

    driver = driver_module.Driver(
        make_args(monkeypatch, release, underlay, evidence, "check-start"),
        runner=RealSystemdShowRunner(),
    )
    eff = driver.effective()
    assert eff["Restart"] == "no"
    assert "/run/usv-scheme-a-commissioning-authorized" in eff["ConditionPathExists"]


def _make_legacy_rollback_docs(release, underlay, build_dir, t60_override=None):
    ctrl_bin = build_dir / "usv_nmpc" / "mpc_node"
    ctrl_bin.parent.mkdir(parents=True, exist_ok=True)
    ctrl_bin.write_bytes(b"legacy-mpc-elf")
    ctrl_link = underlay / "usv_nmpc" / "lib" / "usv_nmpc" / "mpc_node"
    ctrl_link.parent.mkdir(parents=True, exist_ok=True)
    if not ctrl_link.exists():
        ctrl_link.symlink_to(ctrl_bin)

    safety_bin = build_dir / "usv_safety" / "mode_manager_node"
    safety_bin.parent.mkdir(parents=True, exist_ok=True)
    safety_bin.write_bytes(b"legacy-safety-elf")
    safety_link = underlay / "usv_safety" / "lib" / "usv_safety" / "mode_manager_node"
    safety_link.parent.mkdir(parents=True, exist_ok=True)
    if not safety_link.exists():
        safety_link.symlink_to(safety_bin)

    ctrl_sha = driver_module.sha256_file(str(ctrl_bin))
    safety_sha = driver_module.sha256_file(str(safety_bin))
    pkgs = ("usv_acados", "usv_mpc", "usv_nmpc", "usv_safety", "usv_planning", "usv_bringup")

    def build_doc(baseline=False):
        doc = {
            "identity_ok": False,
            "scheme": "B",
            "expected_install": str(underlay),
            "expected_executable": {"path": str(ctrl_link), "sha256": ctrl_sha},
            "services": {
                "usv-system": {
                    "ActiveState": "active",
                    "MainPID": "1255",
                    "NRestarts": "0",
                    "ExecStart": "source /home/trevor/usv_runtime/setup.bash && exec ros2 launch usv_bringup real.launch.py scheme:=B",
                    "drop_ins": [
                        "/etc/systemd/system/usv-system.service.d/20-release.conf",
                        "/run/systemd/system/usv-system.service.d/31-scheme-a-rollback-no-restart.conf",
                    ],
                },
                "usv-record": {"ActiveState": "inactive"},
                "usv-rtk": {"ActiveState": "inactive"},
            },
            "processes": [
                {"pid": 1001, "starttime": 500, "exe_target": "/opt/ros/jazzy/lib/mavros/mavros_node", "custom": False, "exe_deleted": False},
                {"pid": 1002, "starttime": 501, "exe_target": "/usr/bin/python3.12", "custom": False, "exe_deleted": False},
                {"pid": 1003, "starttime": 502, "exe_target": str(safety_bin), "custom": True, "exe_deleted": False, "disk_sha256": safety_sha, "exe_sha256": safety_sha},
                {"pid": 1004, "starttime": 503, "exe_target": str(ctrl_bin), "custom": True, "exe_deleted": False, "disk_sha256": ctrl_sha, "exe_sha256": ctrl_sha},
            ],
            "serial_holders": {"/dev/ttyAMA10": [1001], "/dev/ttyAMA4": [1002]},
            "parameter_dump": {"returncode": 0, "sha256": "param-sha-b", "parameters": {"control_mode": "dynamic"}},
            "backend_log": {"backend": "acados"},
            "package_prefixes": {
                p: {"prefix": str(underlay / p), "resolved": True, "inside_expected": True}
                for p in pkgs
            },
            "failures": [
                f"控制器不在预期 install 内: {ctrl_bin} (期望 {underlay})",
                f"控制器路径不是预期方案可执行文件: {ctrl_bin} (期望 {ctrl_link})",
                "控制器未加载共用后端库 libusv_acados_backend",
                f"自定义进程不在预期 install 内: pid=1003 exe={safety_bin}",
                "串口 /dev/ttyAMA4 由非 MAVROS 进程持有: [1002]",
            ],
        }
        if baseline and t60_override:
            t60_override(doc)
        return doc

    return build_doc(False), build_doc(True)


def test_rollback_capture_excludes_release_paths_from_env(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    rel_p = driver_module.Path if False else None  # keep clean
    from pathlib import Path
    (Path(release) / "install" / "usv_bringup" / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    (Path(release) / "install" / "usv_acados" / "lib").mkdir(parents=True)
    (Path(underlay) / "usv_nmpc" / "lib").mkdir(parents=True)

    driver = driver_module.Driver(
        make_args(monkeypatch, release, underlay, evidence, "rollback"),
        runner=FakeRunner(), unit_dir=str(tmp_path / "units"),
    )
    b_env = driver.ros_env({"ros_domain_id": 0, "dds_profile_path": "/dev/null"}, include_release=False)
    for var in ("AMENT_PREFIX_PATH", "PYTHONPATH", "LD_LIBRARY_PATH"):
        assert str(release) not in b_env.get(var, ""), f"{var} leaked release_root: {b_env.get(var)}"


def test_rollback_rejects_failure_when_underlay_has_candidate_shared_backend(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    from pathlib import Path
    shared = Path(underlay) / "usv_acados" / "lib" / "libusv_acados_backend.so"
    shared.parent.mkdir(parents=True, exist_ok=True)
    shared.write_bytes(b"so")
    mpc = Path(underlay) / "usv_nmpc" / "lib" / "usv_nmpc" / "mpc_node"
    mpc.parent.mkdir(parents=True, exist_ok=True)
    mpc.write_bytes(b"candidate-mpc-elf")

    units = tmp_path / "units"
    run_units = tmp_path / "run_units"
    (units / "usv-system.service.d").mkdir(parents=True)
    (units / "usv-system.service.d" / "30-scheme-a-commissioning.conf").write_text("[Service]\nRestart=no\n")

    class FailingCandidateCaptureRunner(FakeRunner):
        def run(self, argv, timeout=60, env=None, check=False):
            if argv[0] == "runuser" and "capture_release_identity.py" in " ".join(argv):
                out_path = argv[argv.index("--output") + 1]
                Path(out_path).write_text(json.dumps({"identity_ok": False, "failures": ["broken"]}))
                return {"argv": list(argv), "rc": 1, "stdout": "", "stderr": ""}
            return super().run(argv, timeout=timeout, env=env, check=check)

    runner = FailingCandidateCaptureRunner(
        service_states={"usv-system.service": {
            "ActiveState": "active", "MainPID": "1255", "NRestarts": "0",
            "Restart": "always", "ControlGroup": "/system.slice/usv-system.service"}},
        unit_dir=str(units), runtime_unit_dir=str(run_units),
    )
    driver = driver_module.Driver(
        make_args(monkeypatch, release, underlay, evidence, "rollback"),
        runner=runner, unit_dir=str(units), runtime_unit_dir=str(run_units),
        token_path=str(tmp_path / "token"), lock_path=str(tmp_path / "lock"),
    )
    monkeypatch.setattr(driver, "cgroup_pids", lambda unit: [])
    monkeypatch.setattr(driver, "serial_holders", lambda: {})
    monkeypatch.setattr(driver_module, "B_STARTUP_SECONDS", 0.01)
    monkeypatch.setattr(driver_module, "B_SETTLE_SECONDS", 0.0)
    monkeypatch.setattr(driver_module, "ACCEPTANCE_SECONDS", 0.01)

    assert driver.action_rollback() == driver_module.EXIT_FAIL
    assert (run_units / "usv-system.service.d" / "31-scheme-a-rollback-no-restart.conf").exists()


def test_rollback_accepts_verified_legacy_symlink_underlay_when_invariants_hold(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    from pathlib import Path
    t0_doc, t60_doc = _make_legacy_rollback_docs(Path(release), Path(underlay), tmp_path / "build")

    units = tmp_path / "units"
    run_units = tmp_path / "run_units"
    (units / "usv-system.service.d").mkdir(parents=True)
    (units / "usv-system.service.d" / "30-scheme-a-commissioning.conf").write_text("[Service]\nRestart=no\n")

    seen_envs = []

    class LegacyCaptureRunner(FakeRunner):
        def run(self, argv, timeout=60, env=None, check=False):
            if argv[0] == "runuser" and "capture_release_identity.py" in " ".join(argv):
                seen_envs.append(dict(env or {}))
                out_path = argv[argv.index("--output") + 1]
                doc = t60_doc if "--baseline" in argv else t0_doc
                Path(out_path).write_text(json.dumps(doc))
                return {"argv": list(argv), "rc": 1, "stdout": "", "stderr": ""}
            return super().run(argv, timeout=timeout, env=env, check=check)

    runner = LegacyCaptureRunner(
        service_states={"usv-system.service": {
            "ActiveState": "active", "MainPID": "1255", "NRestarts": "0",
            "Restart": "always", "ControlGroup": "/system.slice/usv-system.service"}},
        unit_dir=str(units), runtime_unit_dir=str(run_units),
    )
    driver = driver_module.Driver(
        make_args(monkeypatch, release, underlay, evidence, "rollback"),
        runner=runner, unit_dir=str(units), runtime_unit_dir=str(run_units),
        token_path=str(tmp_path / "token"), lock_path=str(tmp_path / "lock"),
    )
    monkeypatch.setattr(driver, "cgroup_pids", lambda unit: [])
    monkeypatch.setattr(driver, "serial_holders", lambda: {})
    monkeypatch.setattr(driver_module, "B_STARTUP_SECONDS", 0.01)
    monkeypatch.setattr(driver_module, "B_SETTLE_SECONDS", 0.0)
    monkeypatch.setattr(driver_module, "ACCEPTANCE_SECONDS", 0.01)

    assert driver.action_rollback() == driver_module.EXIT_OK
    assert not (run_units / "usv-system.service.d" / "31-scheme-a-rollback-no-restart.conf").exists()
    assert len(seen_envs) == 2
    for env in seen_envs:
        assert str(release) not in env.get("AMENT_PREFIX_PATH", "")


def test_rollback_rejects_legacy_underlay_on_release_leak_or_drift(tmp_path, monkeypatch):
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    from pathlib import Path
    t0_doc, t60_doc = _make_legacy_rollback_docs(
        Path(release), Path(underlay), tmp_path / "build",
        t60_override=lambda d: d["parameter_dump"].update({"sha256": "drifted-sha"}),
    )
    t0_doc["package_prefixes"]["usv_nmpc"] = {
        "prefix": str(Path(release) / "install" / "usv_nmpc"),
        "resolved": True,
        "inside_expected": False,
    }

    driver = driver_module.Driver(
        make_args(monkeypatch, release, underlay, evidence, "rollback"),
        runner=FakeRunner(), unit_dir=str(tmp_path / "units"),
    )
    probs = driver._evaluate_legacy_underlay_rollback(t0_doc, t60_doc)
    assert any("leaked" in p or "inside underlay" in p for p in probs), probs
    assert any("parameter dump sha changed" in p for p in probs), probs


def test_render_dropin_substitutes_use_ntrip_and_backend(tmp_path, monkeypatch):
    import importlib.util
    release, underlay, evidence = build_release(tmp_path, monkeypatch)
    from pathlib import Path
    tpl = Path(release) / "deploy" / "30-scheme-a-commissioning.conf.in"
    tpl.write_text(
        "[Unit]\nConditionPathExists=@TOKEN_PATH@\n\n[Service]\nRestart=no\n"
        "ExecStart=/bin/bash -c 'ros2 launch usv_bringup real.launch.py "
        "controller_backend:=@CONTROLLER_BACKEND@ use_ntrip:=@USE_NTRIP@ "
        "commissioning_release_root:=@RELEASE_ROOT@ commissioning_underlay:=@UNDERLAY@'\n"
    )
    ident_path = Path(evidence) / "release_identity.json"
    ident = json.loads(ident_path.read_text())
    ident["dropin_template_sha256"] = driver_module.sha256_file(str(tpl))
    ident_path.write_text(json.dumps(ident))

    args = driver_module.parse_args([
        "--release-root", release,
        "--underlay", underlay,
        "--operator-attestation", str(Path(evidence) / "operator-attestation.json"),
        "--action", "takeover",
        "--evidence-dir", str(tmp_path / "ev"),
        "--use-ntrip", "false",
    ])
    drv = driver_module.Driver(args, runner=FakeRunner(), token_path=str(tmp_path / "tok"))
    rendered = drv.render_dropin(ident)
    assert "controller_backend:=research_commissioning" in rendered
    assert "use_ntrip:=false" in rendered
    assert "@" not in rendered

    probe_spec = importlib.util.spec_from_file_location(
        "probe_fcu_state",
        str(Path(__file__).resolve().parents[1] / "probe_fcu_state.py"),
    )
    probe_mod = importlib.util.module_from_spec(probe_spec)
    probe_spec.loader.exec_module(probe_mod)
    not_ready = probe_mod.summarize_nav({
        "imu_count": 10, "imu_finite": True,
        "odom_count": 0, "odom_finite": True,
        "gp_origin_seen": False,
        "path_count": 2, "profile_count": 2,
    })
    assert not_ready["nav_ready"] is False
    assert set(not_ready["missing"]) == {"odom", "gp_origin"}
    ready = probe_mod.summarize_nav({
        "imu_count": 10, "imu_finite": True,
        "odom_count": 5, "odom_finite": True,
        "gp_origin_seen": True,
        "path_count": 2, "profile_count": 2,
    })
    assert ready["nav_ready"] is True
    assert ready["missing"] == []
