#!/usr/bin/env python3
"""方案A 实船调试服务接管维护 driver。

三个 action，语义刻意做窄：
  check-start —— 只读、只校验 root token 与代码身份。不取部署锁、不创建证据、
                 不探测尚未启动的 MAVROS。供 systemd ExecCondition(+前缀) 以 root
                 调用；通过 0，拒绝 1。
  takeover    —— 停旧 usv-system、安装本批 30 drop-in、启动唯一目标服务，并在
                 30s 启动 + 60s 连续验收后给出结论。
  rollback    —— 先在临时 31 保护下停 commissioning、恢复原 B 一次并独立验收，
                 通过后才撤 31 并核对原策略已复原。

本驱动只操作 usv-system.service，不动 usv_runtime 软链、不动 /etc/default/usv-system、
不动 usv-record / usv-rtk 的 active/enable，也不发任何解锁/模式/任务/RC/速度指令。
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid

EXIT_OK = 0
EXIT_REJECT = 1
EXIT_FAIL = 2

UNIT = "usv-system.service"
UNIT_DIR = "/etc/systemd/system"
RUNTIME_UNIT_DIR = "/run/systemd/system"
DROPIN_DIR = os.path.join(UNIT_DIR, f"{UNIT}.d")
DROPIN_NAME = "30-scheme-a-commissioning.conf"
ROLLBACK_DROPIN_NAME = "31-scheme-a-rollback-no-restart.conf"
TOKEN_PATH = "/run/usv-scheme-a-commissioning-authorized"
LOCK_PATH = "/run/lock/usv-scheme-a-commissioning.lock"
STATE_GATE_SECONDS = 10.0
STARTUP_SECONDS = 30.0
B_STARTUP_SECONDS = STARTUP_SECONDS
B_SETTLE_SECONDS = 2.0
ACCEPTANCE_SECONDS = 60.0
STOP_TIMEOUT_SECONDS = 20.0
SAFE_SYSTEM_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ATTESTATION_REQUIRED_FLAGS = ("vessel_secured", "no_mission", "propulsion_power_isolated",
                              "local_emergency_stop_available")


class DriverError(RuntimeError):
    pass


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: str):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode())


def now_utc_ns() -> int:
    return time.time_ns()


def iso_utc(ns: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ns / 1e9))


def host_boot_id() -> str:
    with open("/proc/sys/kernel/random/boot_id", "rb") as handle:
        return handle.read().decode().strip()


def _collect_unique_dirs(patterns: tuple[str, ...] | list[str]) -> list[str]:
    seen: list[str] = []
    for pattern in patterns:
        for match in sorted(glob.glob(pattern)):
            base = os.path.basename(match)
            if base.startswith("."):
                continue
            if os.path.isdir(match) and match not in seen:
                seen.append(match)
    return seen


class Runner:
    """可替换的命令执行器：测试用它验证"外部效果"，而不是读源码字符串。"""

    def run(self, argv, timeout=60, env=None, check=False):
        cmd = list(argv)
        if env is not None and cmd and not os.path.isabs(cmd[0]):
            resolved = shutil.which(cmd[0]) or shutil.which(cmd[0], path=SAFE_SYSTEM_PATH)
            if resolved:
                cmd[0] = resolved
        completed = subprocess.run(cmd, capture_output=True, timeout=timeout,
                                   check=False, env=env)
        result = {
            "argv": list(argv),
            "rc": completed.returncode,
            "stdout": completed.stdout.decode("utf-8", "replace"),
            "stderr": completed.stderr.decode("utf-8", "replace"),
        }
        if check and completed.returncode != 0:
            raise DriverError(f"command failed: {argv} rc={completed.returncode} "
                              f"stderr={result['stderr'][:400]}")
        return result


class Driver:
    def __init__(self, args, runner: Runner | None = None,
                 unit_dir: str = UNIT_DIR, token_path: str = TOKEN_PATH,
                 lock_path: str = LOCK_PATH,
                 runtime_unit_dir: str | None = None) -> None:
        self.args = args
        self.runner = runner or Runner()
        self.unit_dir = unit_dir
        self.dropin_dir = os.path.join(unit_dir, f"{UNIT}.d")
        if runtime_unit_dir is not None:
            self.runtime_unit_dir = runtime_unit_dir
        elif unit_dir == UNIT_DIR:
            self.runtime_unit_dir = RUNTIME_UNIT_DIR
        else:
            self.runtime_unit_dir = os.path.join(unit_dir, "_runtime")
        self.runtime_dropin_dir = os.path.join(self.runtime_unit_dir, f"{UNIT}.d")
        self.token_path = token_path
        self.lock_path = lock_path
        self.release_root = os.path.realpath(args.release_root)
        self.underlay = os.path.realpath(args.underlay)
        self.attestation_path = os.path.realpath(args.operator_attestation)
        self.evidence_dir = os.path.realpath(args.evidence_dir) if args.evidence_dir else ""
        self.release_id = os.path.basename(self.release_root)
        self.records: list[dict] = []
        self.baseline_path = ""
        self.transaction_dir = ""
        self.probe_dir = ""

    # ------------------------------------------------------------------ 记录
    def record(self, step: str, **fields) -> None:
        entry = {"step": step, "at_utc": iso_utc(now_utc_ns()), **fields}
        self.records.append(entry)

    def persist(self) -> None:
        if not self.transaction_dir:
            return
        path = os.path.join(self.transaction_dir, "transactions.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"schema": "p1-shipboard-transactions-v1",
                       "release_id": self.release_id,
                       "action": self.args.action,
                       "records": self.records}, handle, indent=2)
        os.chmod(path, 0o640)

    # -------------------------------------------------------------- 声明校验
    def load_attestation(self) -> dict:
        expected = os.path.join(self.release_root, "evidence", "operator-attestation.json")
        if self.attestation_path != os.path.realpath(expected):
            raise DriverError(
                f"--operator-attestation must resolve to {expected}")
        if not os.path.isfile(self.attestation_path):
            raise DriverError("operator attestation missing: no on-site declaration")
        declaration = read_json(self.attestation_path)
        for field in ATTESTATION_REQUIRED_FLAGS:
            if declaration.get(field) is not True:
                raise DriverError(f"operator attestation does not confirm {field}")
        for field in ("operator", "confirmed_at_utc", "valid_until_utc"):
            if field not in declaration:
                raise DriverError(f"operator attestation missing {field}")
        if not str(declaration["operator"]).strip():
            raise DriverError("operator attestation names no operator")
        deadline = int(declaration["valid_until_utc"])
        if deadline <= now_utc_ns():
            raise DriverError("operator attestation already expired (no auto-renewal)")
        declaration["_sha256"] = sha256_file(self.attestation_path)
        return declaration

    # ------------------------------------------------------------ 身份与证据
    def load_release_identity(self) -> dict:
        path = os.path.join(self.release_root, "evidence", "release_identity.json")
        if not os.path.isfile(path):
            raise DriverError(f"release identity missing: {path}")
        identity = read_json(path)
        for key, relative in (("source_hashes_sha256", "evidence/source_hashes.json"),
                              ("install_manifest_sha256", "evidence/install_manifest.json"),
                              ("release_artifacts_sha256", "evidence/release_artifacts.json")):
            target = os.path.join(self.release_root, relative)
            if not os.path.isfile(target):
                raise DriverError(f"release evidence missing: {relative}")
            if sha256_file(target) != identity.get(key):
                raise DriverError(f"release identity drifted: {key}")
        self._verify_artifacts()
        return identity

    def _verify_artifacts(self) -> None:
        path = os.path.join(self.release_root, "evidence", "release_artifacts.json")
        manifest = read_json(path)
        records = manifest.get("artifacts") or []
        if not records:
            raise DriverError("release_artifacts.json has no artifacts")
        for record in records:
            target = os.path.join(self.release_root, record["path"])
            if not os.path.isfile(target):
                raise DriverError(f"declared artifact missing: {record['path']}")
            if sha256_file(target) != record["sha256"]:
                raise DriverError(f"declared artifact drifted: {record['path']}")

    # -------------------------------------------------------------- 事务目录
    def begin_transaction(self) -> None:
        if not self.evidence_dir:
            raise DriverError("--evidence-dir is required for takeover/rollback")
        if not os.path.isdir(self.evidence_dir):
            raise DriverError(f"evidence dir missing: {self.evidence_dir}")
        self.transaction_dir = os.path.join(self.evidence_dir, str(uuid.uuid4()))
        os.mkdir(self.transaction_dir, 0o750)
        # 事务目录归 root:trevor/0750，回执 0640，便于 trevor 事后读回。
        # 非 root 执行（例如可替换执行器的反证）时跳过 chown，权限仍收窄。
        if os.geteuid() == 0:
            try:
                trevor = pwd.getpwnam("trevor")
                os.chown(self.transaction_dir, 0, trevor.pw_gid)
            except KeyError:
                pass
        os.chmod(self.transaction_dir, 0o750)
        self.probe_dir = os.path.join(self.transaction_dir, "probes")
        os.mkdir(self.probe_dir, 0o750)
        if os.geteuid() == 0:
            try:
                trevor = pwd.getpwnam("trevor")
                os.chown(self.probe_dir, trevor.pw_uid, trevor.pw_gid)
            except KeyError:
                pass
        os.chmod(self.probe_dir, 0o750)
        baseline = os.path.join(self.evidence_dir, "baseline.json")
        if not os.path.isfile(baseline):
            self.capture_environment(baseline)
            os.chmod(baseline, 0o640)
        self.baseline_path = baseline

    def capture_environment(self, path: str) -> None:
        """固定 baseline：unit 字节、drop-in 集合、runtime 软链、服务状态。"""
        environment = {
            "schema": "p1-shipboard-baseline-v1",
            "captured_utc": iso_utc(now_utc_ns()),
            "host_boot_id": host_boot_id(),
            "release_id": self.release_id,
            "unit_sha256": self._maybe_sha(os.path.join(self.unit_dir, UNIT)),
            "drop_ins": self._drop_in_fingerprints(),
            "runtime_link": self._readlink("/home/trevor/usv_runtime"),
            "default_scheme": self._read_text(os.path.join("/etc/default", "usv-system")),
            "services": {unit: self.service_state(unit)
                         for unit in ("usv-system.service", "usv-record.service",
                                      "usv-rtk.service")},
            "underlay_realpath": os.path.realpath(self.underlay),
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(environment, handle, indent=2)

    def _maybe_sha(self, path: str):
        return sha256_file(path) if os.path.isfile(path) else None

    @staticmethod
    def _readlink(path: str):
        try:
            return os.readlink(path)
        except OSError:
            return None

    @staticmethod
    def _read_text(path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            return None

    def _drop_in_fingerprints(self) -> dict:
        out = {}
        try:
            names = sorted(os.listdir(self.dropin_dir))
        except OSError:
            return out
        for name in names:
            if name.endswith(".conf"):
                path = os.path.join(self.dropin_dir, name)
                out[name] = sha256_file(path)
        return out

    def service_state(self, unit: str) -> dict:
        result = self.runner.run(["systemctl", "show", unit, "--no-pager", "--property="
                                  "ActiveState,SubState,UnitFileState,MainPID,"
                                  "NRestarts,ControlGroup,ActiveEnterTimestampMonotonic,"
                                  "InvocationID"])
        info = {"unit": unit, "rc": result["rc"]}
        for line in result["stdout"].splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                info[key] = value
        info["exe_starttime"] = None
        pid = info.get("MainPID")
        if pid and pid.isdigit() and int(pid) > 0:
            try:
                with open(f"/proc/{pid}/stat", "rb") as handle:
                    fields = handle.read().decode("utf-8", "replace").rsplit(") ", 1)[-1].split()
                info["exe_starttime"] = fields[19]
                info["exe_path"] = os.path.realpath(f"/proc/{pid}/exe")
            except OSError:
                pass
        return info

    def cgroup_pids(self, unit: str) -> list[int]:
        state = self.service_state(unit)
        group = (state.get("ControlGroup") or f"/system.slice/{unit}").lstrip("/")
        procs = os.path.join("/sys/fs/cgroup", group, "cgroup.procs")
        try:
            with open(procs, "r", encoding="utf-8") as handle:
                return [int(item) for item in handle.read().split() if item.isdigit()]
        except OSError:
            return []

    def serial_holders(self) -> dict:
        holders: dict[str, list[int]] = {}
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            fd_dir = f"/proc/{name}/fd"
            try:
                entries = os.listdir(fd_dir)
            except OSError:
                continue
            for entry in entries:
                try:
                    target = os.readlink(os.path.join(fd_dir, entry))
                except OSError:
                    continue
                if target.startswith("/dev/tty") and " (" not in target:
                    holders.setdefault(target, [])
                    if int(name) not in holders[target]:
                        holders[target].append(int(name))
        return {device: sorted(pids) for device, pids in holders.items()}

    # --------------------------------------------------------------- token
    def token_body(self, identity: dict, declaration: dict) -> dict:
        return {
            "schema": "p1-shipboard-authorisation-v1",
            "release_id": self.release_id,
            "host_boot_id": host_boot_id(),
            "attestation_sha256": declaration["_sha256"],
            "release_artifacts_sha256": identity["release_artifacts_sha256"],
            "underlay_identity_sha256": identity["underlay_identity_sha256"],
            "valid_until_utc": int(declaration["valid_until_utc"]),
            "created_utc": iso_utc(now_utc_ns()),
        }

    def create_token(self, body: dict) -> None:
        payload = json.dumps(body, sort_keys=True).encode()
        try:
            fd = os.open(self.token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise DriverError(f"authorisation token already exists: {self.token_path}") from error
        try:
            os.write(fd, payload)
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)

    def remove_token(self) -> None:
        try:
            os.unlink(self.token_path)
        except FileNotFoundError:
            pass

    # ------------------------------------------------------ check-start (只读)
    def action_check_start(self) -> int:
        """只用 stdlib：核 token 所有者/权限/内容/同 boot/未过期/发布身份。"""
        problems: list[str] = []
        try:
            info = os.lstat(self.token_path)
        except OSError:
            print("check-start: authorisation token absent", file=sys.stderr)
            return EXIT_REJECT
        if not stat.S_ISREG(info.st_mode):
            problems.append("token is not a regular file")
        if info.st_uid != 0:
            problems.append(f"token owner uid {info.st_uid} != 0")
        if stat.S_IMODE(info.st_mode) != 0o600:
            problems.append(f"token mode {oct(stat.S_IMODE(info.st_mode))} != 0o600")
        try:
            body = json.loads(open(self.token_path, "rb").read().decode())
        except (OSError, ValueError) as error:
            return self._reject(f"token unreadable: {error}")
        if body.get("release_id") != self.release_id:
            problems.append("token release_id mismatch")
        if body.get("host_boot_id") != host_boot_id():
            problems.append("token belongs to a different kernel boot")
        if int(body.get("valid_until_utc") or 0) <= now_utc_ns():
            problems.append("token expired")
        expected_attestation = os.path.join(self.release_root, "evidence",
                                           "operator-attestation.json")
        if not os.path.isfile(expected_attestation):
            problems.append("operator attestation missing")
        elif sha256_file(expected_attestation) != body.get("attestation_sha256"):
            problems.append("attestation bytes changed since the token was issued")
        artifacts = os.path.join(self.release_root, "evidence", "release_artifacts.json")
        if not os.path.isfile(artifacts):
            problems.append("release_artifacts.json missing")
        elif sha256_file(artifacts) != body.get("release_artifacts_sha256"):
            problems.append("release artifacts changed since the token was issued")
        identity_path = os.path.join(self.release_root, "evidence", "release_identity.json")
        if not os.path.isfile(identity_path):
            problems.append("release_identity.json missing")
        else:
            identity = read_json(identity_path)
            if identity.get("underlay_identity_sha256") != body.get("underlay_identity_sha256"):
                problems.append("underlay identity changed since the token was issued")
        if problems:
            return self._reject("; ".join(problems))
        print("check-start: ok")
        return EXIT_OK

    @staticmethod
    def _reject(message: str) -> int:
        print(f"check-start: rejected: {message}", file=sys.stderr)
        return EXIT_REJECT

    # ------------------------------------------------------------ 部署锁
    def acquire_lock(self):
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        handle = open(self.lock_path, "a+")
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, OSError) as error:
            handle.close()
            raise DriverError(f"deployment lock busy: {error}") from error
        return handle

    # --------------------------------------------------------- drop-in 文件
    def render_dropin(self, identity: dict) -> str:
        """从冻结模板渲染：同一 R 的两次 takeaway 必须得到同一批字节。"""
        template_path = self.template_path()
        if not os.path.isfile(template_path):
            raise DriverError(f"frozen drop-in template missing: {template_path}")
        template_sha = sha256_file(template_path)
        declared = identity.get("dropin_template_sha256")
        if declared and declared != template_sha:
            raise DriverError("drop-in template bytes drifted from the frozen identity")
        with open(template_path, "r", encoding="utf-8") as handle:
            body = handle.read()
        use_ntrip = str(getattr(self.args, "use_ntrip", "true"))
        backend = str(getattr(self.args, "backend", "research_commissioning"))
        for token, value in (("@RELEASE_ROOT@", self.release_root),
                             ("@UNDERLAY@", self.underlay),
                             ("@TOKEN_PATH@", self.token_path),
                             ("@USE_NTRIP@", use_ntrip),
                             ("@CONTROLLER_BACKEND@", backend)):
            body = body.replace(token, value)
        if "@" in body.replace("${SCHEME}", ""):
            leftover = [line for line in body.splitlines() if "@" in line]
            raise DriverError(f"unrendered drop-in template tokens: {leftover}")
        return body

    def template_path(self) -> str:
        return os.path.join(self.release_root, "deploy", "30-scheme-a-commissioning.conf.in")

    def dropin_path(self, name: str = DROPIN_NAME, runtime: bool = False) -> str:
        base = self.runtime_dropin_dir if runtime else self.dropin_dir
        return os.path.join(base, name)

    def install_dropin(self, body: str, name: str = DROPIN_NAME, runtime: bool = False) -> str:
        path = self.dropin_path(name, runtime=runtime)
        if os.path.exists(path):
            raise DriverError(f"refusing to overwrite an existing drop-in: {path}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            os.write(fd, body.encode())
            os.fchmod(fd, 0o644)
            if os.geteuid() == 0:
                os.fchown(fd, 0, 0)
        finally:
            os.close(fd)
        self.record("install_dropin", path=path, sha256=sha256_file(path))
        return path

    def remove_dropin_if_ours(self, expected_sha: str, name: str = DROPIN_NAME,
                             runtime: bool = False) -> str:
        path = self.dropin_path(name, runtime=runtime)
        if not os.path.isfile(path):
            return "absent"
        actual = sha256_file(path)
        if actual != expected_sha:
            self.record("dropin_foreign_refused", path=path, actual=actual,
                        expected=expected_sha)
            return "foreign"
        os.unlink(path)
        self.record("remove_dropin", path=path, sha256=expected_sha)
        return "removed"

    # ------------------------------------------------------------ systemd
    def systemctl(self, *argv, check=False, timeout=60):
        result = self.runner.run(["systemctl", *argv], timeout=timeout, check=check)
        self.record("systemctl", argv=list(argv), rc=result["rc"],
                    stderr=result["stderr"][:400])
        return result

    def daemon_reload(self) -> None:
        self.systemctl("daemon-reload", check=True)

    def effective(self, unit: str = UNIT) -> dict:
        result = self.runner.run(["systemctl", "show", unit, "--no-pager",
                                  "--property=ExecStart,Restart,ConditionPathExists,"
                                  "ExecCondition,DropInPaths,ActiveState,MainPID,NRestarts"])
        info = {}
        for line in result["stdout"].splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                info[key] = value
        # Real systemd stores ConditionPathExists inside D-Bus Conditions ([unprintable] in show),
        # so fall back to merged unit output from `systemctl cat` when `show` omits it.
        if "ConditionPathExists" not in info:
            cat_res = self.runner.run(["systemctl", "cat", unit, "--no-pager"])
            conditions: list[str] = []
            for raw_line in (cat_res.get("stdout") or "").splitlines():
                stripped = raw_line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("ConditionPathExists="):
                    val = stripped.split("=", 1)[1].strip()
                    if val:
                        conditions.append(val)
                    else:
                        conditions.clear()
            if conditions:
                info["ConditionPathExists"] = " ".join(conditions)
        return info

    def verify_unit_syntax(self) -> None:
        result = self.runner.run(["systemd-analyze", "verify", UNIT])
        self.record("systemd_analyze_verify", rc=result["rc"],
                    stderr=result["stderr"][:400])
        if result["rc"] != 0:
            raise DriverError(f"systemd-analyze verify failed: {result['stderr'][:400]}")

    def stop_unit(self) -> None:
        self.systemctl("stop", UNIT)
        deadline = time.time() + STOP_TIMEOUT_SECONDS
        while time.time() < deadline:
            state = self.service_state(UNIT)
            if state.get("ActiveState") == "inactive" and not self.cgroup_pids(UNIT):
                break
            time.sleep(0.5)
        state = self.service_state(UNIT)
        if state.get("ActiveState") != "inactive":
            raise DriverError(f"{UNIT} did not reach inactive: {state.get('ActiveState')}")
        leftovers = self.cgroup_pids(UNIT)
        if leftovers:
            raise DriverError(f"control group not empty after stop: {leftovers}")
        holders = self.serial_holders()
        busy = {device: pids for device, pids in holders.items()
                if device in ("/dev/ttyAMA10", "/dev/ttyAMA4") and pids}
        if busy:
            raise DriverError(f"serial device still held after stop: {busy}")
        self.record("unit_stopped", pid=state.get("MainPID"))

    # ------------------------------------------------------------ ROS 探测
    def ros_env(self, identity: dict, include_release: bool = True) -> dict:
        rel_install = os.path.join(self.release_root, "install")
        ros_root = "/opt/ros/jazzy"
        ament_patterns = []
        python_patterns = []
        ld_patterns = []
        if include_release:
            ament_patterns.append(os.path.join(rel_install, "*"))
            python_patterns.extend([
                os.path.join(rel_install, "*", "lib", "python*", "site-packages"),
                os.path.join(rel_install, "lib", "python*", "site-packages"),
            ])
            ld_patterns.append(os.path.join(rel_install, "*", "lib"))
        ament_patterns.extend([os.path.join(self.underlay, "*"), ros_root])
        python_patterns.extend([
            os.path.join(self.underlay, "*", "lib", "python*", "site-packages"),
            os.path.join(self.underlay, "lib", "python*", "site-packages"),
            os.path.join(ros_root, "lib", "python*", "site-packages"),
        ])
        ld_patterns.extend([
            os.path.join(self.underlay, "*", "lib"),
            "/home/trevor/acados/lib",
            os.path.join(ros_root, "lib", "*-linux-gnu"),
            os.path.join(ros_root, "lib"),
        ])
        ament_prefixes = _collect_unique_dirs(ament_patterns) or (
            [self.underlay, rel_install] if include_release else [self.underlay]
        )
        python_paths = _collect_unique_dirs(python_patterns)
        ld_paths = _collect_unique_dirs(ld_patterns) or (
            [os.path.join(rel_install, "usv_acados", "lib"),
             os.path.join(self.underlay, "usv_acados", "lib")]
            if include_release
            else [os.path.join(self.underlay, "usv_acados", "lib")]
        )
        env = {
            "HOME": "/home/trevor",
            "USER": "trevor",
            "LANG": "C.UTF-8",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "ROS_DOMAIN_ID": str(int(identity["ros_domain_id"])),
            "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
            "ROS_AUTOMATIC_DISCOVERY_RANGE": "SUBNET",
            "FASTDDS_DEFAULT_PROFILES_FILE": identity["dds_profile_path"],
            "FASTRTPS_DEFAULT_PROFILES_FILE": identity["dds_profile_path"],
            "AMENT_PREFIX_PATH": ":".join(ament_prefixes),
            "LD_LIBRARY_PATH": ":".join(ld_paths),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if python_paths:
            env["PYTHONPATH"] = ":".join(python_paths)
        return env

    def probe_state(self, identity: dict, seconds: float) -> dict:
        script = os.path.join(self.release_root, "deploy", "probe_fcu_state.py")
        if not os.path.isfile(script):
            raise DriverError(f"state probe missing: {script}")
        result = self.runner.run(
            ["runuser", "-u", "trevor", "--", "/usr/bin/python3", "-B", script,
             "--seconds", str(seconds)],
            timeout=int(seconds) + 30, env=self.ros_env(identity))
        self.record("probe_state", seconds=seconds, rc=result["rc"])
        try:
            parsed = json.loads(result["stdout"].strip().splitlines()[-1])
        except (ValueError, IndexError):
            parsed = {"ok": False, "error": result["stderr"][:200]}
        return parsed

    def state_gate(self, identity: dict, seconds: float = STATE_GATE_SECONDS) -> dict:
        facts = self.probe_state(identity, seconds)
        if not facts.get("safe_hold"):
            raise DriverError(f"FCU not in the required safe state: {facts}")
        self.record("state_gate_passed", facts=facts)
        return facts

    # ------------------------------------------------------------- 验收
    def capture_snapshot(self, identity: dict, path: str, with_maps: bool) -> dict:
        state = self.service_state(UNIT)
        pids = self.cgroup_pids(UNIT)
        processes = []
        for pid in pids:
            record = {"pid": pid}
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as handle:
                    record["cmdline"] = [item for item in
                                         handle.read().decode("utf-8", "replace").split("\0")
                                         if item]
                link = os.readlink(f"/proc/{pid}/exe")
                record["exe_deleted"] = link.endswith(" (deleted)")
                record["exe_target"] = link[:-len(" (deleted)")] if record["exe_deleted"] else link
                with open(f"/proc/{pid}/stat", "rb") as handle:
                    fields = handle.read().decode("utf-8", "replace").rsplit(") ", 1)[-1].split()
                record["starttime"] = fields[19]
                record["exe_sha256"] = sha256_file(f"/proc/{pid}/exe")
                record["disk_sha256"] = (None if record["exe_deleted"]
                                         else sha256_file(record["exe_target"]))
                record["is_python"] = os.path.basename(record["exe_target"]).startswith("python")
                record["interpreter"] = bool(re.match(
                    r"^(python[0-9.]*|bash|sh|dash)$",
                    os.path.basename(record["exe_target"])))
                libraries = []
                if with_maps:
                    try:
                        with open(f"/proc/{pid}/maps", "r", encoding="utf-8",
                                  errors="replace") as handle:
                            for line in handle:
                                parts = line.split()
                                if len(parts) < 6 or not parts[5].startswith("/"):
                                    continue
                                base = os.path.basename(parts[5])
                                if any(marker in base for marker in
                                       ("libacados", "libblasfeo", "libhpipm",
                                        "libusv_acados_backend")):
                                    if parts[5] not in [item["path"] for item in libraries]:
                                        libraries.append({"path": parts[5],
                                                          "sha256": sha256_file(parts[5])})
                    except OSError:
                        pass
                record["external_libraries"] = libraries
            except OSError:
                continue
            processes.append(record)
        snapshot = {
            "schema": "p1-shipboard-proc-snapshot-v1",
            "captured_utc": iso_utc(now_utc_ns()),
            "unit": state,
            "processes": processes,
            "serial_holders": self.serial_holders(),
            "with_maps": with_maps,
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2)
        return snapshot

    def run_checker(self, run_dir: str, out_path: str, proc_snapshot: str,
                    expect_active: bool = True) -> int:
        checker = os.path.join(self.release_root, "install", "usv_research_safety_cpp",
                              "lib", "usv_research_safety_cpp",
                              "check_shipboard_commissioning.py")
        if not os.path.isfile(checker):
            raise DriverError(f"checker missing: {checker}")
        cmd = ["/usr/bin/python3", "-B", checker,
               "--release-root", self.release_root, "--underlay", self.underlay,
               "--run", run_dir, "--proc-snapshot", proc_snapshot, "--out", out_path]
        if expect_active:
            cmd.append("--expect-active")
        result = self.runner.run(cmd, timeout=600)
        self.record("checker", rc=result["rc"], stdout=result["stdout"][-2000:])
        return result["rc"]

    def acceptance(self, identity: dict, label: str) -> dict:
        """先等 30s 启动就绪，再采 t0，随后连续 60s 验收，再采 t60 并运行判据。"""
        t0 = os.path.join(self.transaction_dir, f"{label}-t0.json")
        t60 = os.path.join(self.transaction_dir, f"{label}-t60.json")
        run_dir = self._wait_for_ready(identity)
        snapshot_t0 = self.capture_snapshot(identity, t0, with_maps=True)
        before = {record["pid"]: record.get("starttime")
                  for record in snapshot_t0["processes"]}
        restarts_before = self.service_state(UNIT).get("NRestarts")
        deadline = time.time() + ACCEPTANCE_SECONDS
        while time.time() < deadline:
            time.sleep(1.0)
        snapshot_t60 = self.capture_snapshot(identity, t60, with_maps=True)
        after = {record["pid"]: record.get("starttime")
                 for record in snapshot_t60["processes"]}
        state = self.service_state(UNIT)
        problems = []
        if not before:
            problems.append("no processes captured at t0")
        if state.get("ActiveState") != "active":
            problems.append(f"unit not active: {state.get('ActiveState')}")
        if state.get("NRestarts") != restarts_before:
            problems.append(f"NRestarts changed: {restarts_before} -> {state.get('NRestarts')}")
        if before != after:
            problems.append("process set or starttime changed during acceptance")
        check_out = os.path.join(self.transaction_dir, f"{label}-check.json")
        checker_rc = self.run_checker(run_dir, check_out, t60, expect_active=True)
        if checker_rc != 0:
            problems.append(f"checker failed rc={checker_rc}")
        self.record("acceptance", label=label, problems=problems,
                    run_dir=run_dir, t0=t0, t60=t60)
        return {"problems": problems, "run_dir": run_dir, "t0": t0, "t60": t60,
                "check": check_out}

    def _wait_for_ready(self, identity: dict, deadline: float | None = None) -> str:
        """按 systemd InvocationID 精确定位 run；不猜目录顺序，遇到 failure 即失败。"""
        limit = deadline if deadline is not None else (time.time() + STARTUP_SECONDS)
        runs = os.path.join(self.release_root, "runs")
        while time.time() < limit:
            state = self.service_state(UNIT)
            active = state.get("ActiveState", "")
            if active in ("failed", "inactive", "deactivating"):
                raise DriverError(
                    f"{UNIT} exited before commissioning ready: ActiveState={active}")
            inv_id = (state.get("InvocationID") or "").strip()
            if inv_id and "/" not in inv_id and ".." not in inv_id:
                run_dir = os.path.join(runs, inv_id)
                log = os.path.join(run_dir, "supervisor.jsonl")
                if os.path.isfile(log):
                    try:
                        with open(log, "r", encoding="utf-8", errors="replace") as handle:
                            for line in handle:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    record = json.loads(line)
                                except ValueError:
                                    continue
                                event = record.get("event")
                                if event == "failure":
                                    raise DriverError(
                                        "commissioning supervisor failed during startup: "
                                        f"{record.get('reason')}")
                                if event == "shutdown":
                                    raise DriverError(
                                        "commissioning supervisor shut down before ready: "
                                        f"{record.get('reason')}")
                                if event == "sample" and record.get("phase") == "ready":
                                    return run_dir
                    except OSError:
                        pass
            time.sleep(0.5)
        raise DriverError("commissioning supervisor did not report within the startup window")

    # ------------------------------------------------------------- takeover
    def action_takeover(self) -> int:
        declaration = self.load_attestation()
        identity = self.load_release_identity()
        self.begin_transaction()
        self.record("takeover_begin", release_id=self.release_id,
                    attestation_sha256=declaration["_sha256"],
                    ros_domain_id=identity["ros_domain_id"])
        # 停旧之前必须先拿到真实安全 state；软件 armed=false 不等于物理隔离。
        self.state_gate(identity)
        body = self.token_body(identity, declaration)
        self.create_token(body)
        dropin_body = self.render_dropin(identity)
        dropin_sha = hashlib.sha256(dropin_body.encode()).hexdigest()
        installed = False
        try:
            self.stop_unit()
            self.install_dropin(dropin_body)
            installed = True
            self.verify_unit_syntax()
            self.daemon_reload()
            effective = self.effective()
            if "research_commissioning" not in effective.get("ExecStart", ""):
                raise DriverError("effective ExecStart does not select research_commissioning")
            if effective.get("Restart") != "no":
                raise DriverError(f"effective Restart is {effective.get('Restart')}, expected no")
            if self.token_path not in effective.get("ConditionPathExists", ""):
                raise DriverError("effective unit lost the authorisation condition")
            self.systemctl("start", UNIT, check=True)
            outcome = self.acceptance(identity, "commissioning")
            if outcome["problems"]:
                raise DriverError(f"commissioning acceptance failed: {outcome['problems']}")
            self.record("takeover_passed", run_dir=outcome["run_dir"])
            return EXIT_OK
        finally:
            # token 只在 30s 启动 + 60s 验收期间持有；最终 active 的服务不会因为
            # 删除 token 被停掉，但后续 restart/重启无法无授权再拉起。
            self.remove_token()
            if not installed:
                self.record("takeover_no_dropin", reason="stopped before install")
            self.persist()

    # ------------------------------------------------------------- rollback
    def action_rollback(self) -> int:
        declaration = self.load_attestation()
        identity = self.load_release_identity()
        self.begin_transaction()
        self.record("rollback_begin", release_id=self.release_id,
                    attestation_sha256=declaration["_sha256"])
        current = self.dropin_path()
        if not os.path.isfile(current):
            raise DriverError("this batch's 30 drop-in is absent: nothing to roll back")
        batch_sha = sha256_file(current)
        # 1) 先安装 Restart=no 保护到运行时 drop-in 目录 (/run/systemd/system/...)：
        #    否则 systemd 的 Restart=always 会在失败时自动循环，把"停机"变成"不断重启"。
        protection = "[Service]\nRestart=no\n"
        self.install_dropin(protection, ROLLBACK_DROPIN_NAME, runtime=True)
        protection_sha = sha256_file(self.dropin_path(ROLLBACK_DROPIN_NAME, runtime=True))
        try:
            self.stop_unit()
            self.remove_token()
            removal = self.remove_dropin_if_ours(batch_sha)
            if removal == "foreign":
                raise DriverError("30 drop-in bytes changed outside this batch; refusing")
            self.daemon_reload()
            effective = self.effective()
            if effective.get("Restart") != "no":
                raise DriverError(f"temporary protection not effective: {effective.get('Restart')}")
            self.systemctl("start", UNIT, check=True)
            restored = self._verify_original_b(identity)
            if restored["problems"]:
                # 原 B 没起来：保持停止，并保留 31 保护。
                self.stop_unit()
                self.record("rollback_b_failed", problems=restored["problems"],
                            kept_protection=True)
                self.persist()
                return EXIT_FAIL
            # 2) 只有 B 验收通过，才撤本批 31 并核对原策略复原。
            removal31 = self.remove_dropin_if_ours(protection_sha, ROLLBACK_DROPIN_NAME,
                                                   runtime=True)
            if removal31 == "foreign":
                raise DriverError("31 protection bytes changed outside this batch")
            self.daemon_reload()
            final = self.effective()
            if final.get("Restart") != "always":
                raise DriverError(f"original restart policy not restored: {final.get('Restart')}")
            self.record("rollback_passed")
            return EXIT_OK
        finally:
            self.persist()

    def _wait_for_original_b_ready(self) -> None:
        """等待原方案 B 恢复至 mpc_node 在位且后端日志就绪后，再采 rollback-t0（应对 3s TimerAction）。"""
        deadline = time.time() + B_STARTUP_SECONDS
        while time.time() < deadline:
            state = self.service_state(UNIT)
            active = state.get("ActiveState", "")
            if active in ("failed", "inactive", "deactivating"):
                return
            if active == "active":
                has_mpc = False
                for pid in self.cgroup_pids(UNIT):
                    try:
                        exe = os.readlink(f"/proc/{pid}/exe")
                    except OSError:
                        continue
                    if os.path.basename(exe.removesuffix(" (deleted)")) == "mpc_node":
                        has_mpc = True
                        break
                if has_mpc:
                    inv_id = (state.get("InvocationID") or "").strip()
                    if inv_id:
                        jres = self.runner.run(
                            ["journalctl", "-u", UNIT,
                             f"_SYSTEMD_INVOCATION_ID={inv_id}",
                             "--since", "-5min", "--no-pager", "-o", "cat"],
                            timeout=10,
                        )
                        if "backend=" in (jres.get("stdout") or ""):
                            time.sleep(B_SETTLE_SECONDS)
                            return
                    else:
                        time.sleep(B_SETTLE_SECONDS)
                        return
            time.sleep(0.5)

    def _legacy_underlay_allowed_targets(self) -> set[str]:
        targets = set()
        for entry in glob.glob(os.path.join(self.underlay, "*", "lib", "*", "*")):
            if os.path.exists(entry) or os.path.islink(entry):
                targets.add(os.path.realpath(entry))
        return targets

    def _evaluate_legacy_underlay_doc(
        self, tag: str, doc: dict, allowed_targets: set[str]
    ) -> list[str]:
        problems = []
        rel_real = os.path.realpath(self.release_root)
        allowed_legacy_prefixes = (
            "控制器不在预期 install 内:",
            "控制器路径不是预期方案可执行文件:",
            "控制器未加载共用后端库",
            "自定义进程不在预期 install 内:",
            "串口 /dev/ttyAMA4 由非 MAVROS 进程持有:",
        )
        for failure in doc.get("failures") or []:
            if not any(failure.startswith(p) for p in allowed_legacy_prefixes):
                problems.append(f"rollback {tag} unexpected capture failure: {failure}")

        if doc.get("scheme") != "B":
            problems.append(f"rollback {tag} scheme mismatch: {doc.get('scheme')!r}")

        sys_svc = (doc.get("services") or {}).get("usv-system") or {}
        if sys_svc.get("ActiveState") != "active":
            problems.append(f"rollback {tag} usv-system not active: {sys_svc.get('ActiveState')!r}")
        drop_ins = [os.path.basename(p) for p in (sys_svc.get("drop_ins") or [])]
        if DROPIN_NAME in drop_ins:
            problems.append(f"rollback {tag} commissioning drop-in still in service drop_ins")
        exec_start = sys_svc.get("ExecStart") or ""
        if self.release_root in exec_start or rel_real in exec_start or "research_commissioning" in exec_start:
            problems.append(f"rollback {tag} ExecStart references commissioning release")

        required_pkgs = (
            "usv_acados", "usv_mpc", "usv_nmpc",
            "usv_safety", "usv_planning", "usv_bringup",
        )
        prefixes = doc.get("package_prefixes") or {}
        for pkg in required_pkgs:
            info = prefixes.get(pkg) or {}
            prefix = str(info.get("prefix") or "")
            if not info.get("resolved") or not info.get("inside_expected"):
                problems.append(f"rollback {tag} package {pkg} not inside underlay: {info!r}")
            elif prefix.startswith(self.release_root + os.sep) or (
                prefix and os.path.realpath(prefix).startswith(rel_real + os.sep)
            ):
                problems.append(f"rollback {tag} package {pkg} leaked into release_root: {prefix}")

        backend = (doc.get("backend_log") or {}).get("backend")
        if backend != "acados":
            problems.append(f"rollback {tag} backend mismatch: {backend!r}")

        dump = doc.get("parameter_dump") or {}
        live_params = dump.get("parameters") or {}
        if dump.get("returncode") != 0 or not dump.get("sha256"):
            problems.append(f"rollback {tag} parameter dump failed: rc={dump.get('returncode')}")
        elif live_params.get("control_mode") != "dynamic":
            problems.append(f"rollback {tag} control_mode mismatch: {live_params.get('control_mode')!r}")

        procs = doc.get("processes") or []
        by_pid = {p.get("pid"): p for p in procs if p.get("pid") is not None}
        expected_exe = doc.get("expected_executable") or {}
        expected_path = expected_exe.get("path")
        expected_sha = expected_exe.get("sha256")
        controllers = [p for p in procs if os.path.basename(p.get("exe_target", "")) == "mpc_node"]
        if len(controllers) != 1:
            problems.append(f"rollback {tag} controller count != 1: {len(controllers)}")
        elif not expected_path or not expected_sha:
            problems.append(f"rollback {tag} missing expected_executable metadata")
        else:
            ctrl = controllers[0]
            if ctrl.get("exe_deleted"):
                problems.append(f"rollback {tag} controller ELF deleted")
            elif ctrl.get("exe_target") != os.path.realpath(expected_path):
                problems.append(
                    f"rollback {tag} controller exe mismatch: {ctrl.get('exe_target')} vs {os.path.realpath(expected_path)}"
                )
            elif not ctrl.get("exe_sha256") or ctrl.get("exe_sha256") != expected_sha or ctrl.get("disk_sha256") != expected_sha:
                problems.append(f"rollback {tag} controller sha mismatch")

        for proc in procs:
            exe_target = proc.get("exe_target") or ""
            if exe_target.startswith(self.release_root + os.sep) or (
                exe_target and os.path.realpath(exe_target).startswith(rel_real + os.sep)
            ):
                problems.append(f"rollback {tag} process leaked from release_root: {exe_target}")
                continue
            if proc.get("custom"):
                if proc.get("exe_deleted"):
                    problems.append(f"rollback {tag} custom process deleted: pid={proc.get('pid')}")
                elif not proc.get("disk_sha256") or proc.get("exe_sha256") != proc.get("disk_sha256"):
                    problems.append(f"rollback {tag} custom process sha mismatch: {exe_target}")
                elif exe_target not in allowed_targets:
                    problems.append(f"rollback {tag} custom process outside underlay targets: {exe_target}")

        mavros_pids = {
            p.get("pid") for p in procs
            if (p.get("exe_target") or "").endswith("/lib/mavros/mavros_node")
        }
        if len(mavros_pids) != 1:
            problems.append(f"rollback {tag} mavros count != 1: {sorted(mavros_pids)}")

        holders = doc.get("serial_holders") or {}
        for dev, pids in holders.items():
            active_pids = [pid for pid in pids if pid in by_pid]
            if dev == "/dev/ttyAMA10" and (len(active_pids) > 1 or any(pid not in mavros_pids for pid in active_pids)):
                problems.append(f"rollback {tag} {dev} unexpected holder: {active_pids}")
            elif dev == "/dev/ttyAMA4":
                if len(active_pids) > 1:
                    problems.append(f"rollback {tag} {dev} multiple holders: {active_pids}")
                elif active_pids:
                    holder_exe = by_pid[active_pids[0]].get("exe_target") or ""
                    if not (holder_exe.startswith("/usr/bin/python3") or active_pids[0] in mavros_pids):
                        problems.append(f"rollback {tag} {dev} unexpected holder exe: {holder_exe}")
        return problems

    def _evaluate_legacy_underlay_rollback(self, t0_doc: dict, t60_doc: dict) -> list[str]:
        allowed_targets = self._legacy_underlay_allowed_targets()
        problems = []
        problems.extend(self._evaluate_legacy_underlay_doc("t0", t0_doc, allowed_targets))
        problems.extend(self._evaluate_legacy_underlay_doc("t60", t60_doc, allowed_targets))

        svc0 = (t0_doc.get("services") or {}).get("usv-system") or {}
        svc60 = (t60_doc.get("services") or {}).get("usv-system") or {}
        if not svc0.get("MainPID") or svc0.get("MainPID") == "0" or svc60.get("MainPID") != svc0.get("MainPID"):
            problems.append(f"rollback MainPID changed or zero: {svc0.get('MainPID')} -> {svc60.get('MainPID')}")
        try:
            if int(svc60.get("NRestarts", -1)) != int(svc0.get("NRestarts", -2)):
                problems.append(f"rollback NRestarts changed: {svc0.get('NRestarts')} -> {svc60.get('NRestarts')}")
        except (TypeError, ValueError):
            problems.append("rollback unable to compare NRestarts")

        sha0 = (t0_doc.get("parameter_dump") or {}).get("sha256")
        sha60 = (t60_doc.get("parameter_dump") or {}).get("sha256")
        if not sha0 or sha60 != sha0:
            problems.append(f"rollback parameter dump sha changed between t0 and t60: {sha0} -> {sha60}")

        ctrl0 = [p for p in (t0_doc.get("processes") or []) if os.path.basename(p.get("exe_target", "")) == "mpc_node"]
        ctrl60 = [p for p in (t60_doc.get("processes") or []) if os.path.basename(p.get("exe_target", "")) == "mpc_node"]
        if len(ctrl0) == 1 and len(ctrl60) == 1:
            sig0 = (ctrl0[0].get("pid"), ctrl0[0].get("starttime"), ctrl0[0].get("exe_sha256"))
            sig60 = (ctrl60[0].get("pid"), ctrl60[0].get("starttime"), ctrl60[0].get("exe_sha256"))
            if sig0 != sig60:
                problems.append(f"rollback controller identity changed between t0 and t60: {sig0} -> {sig60}")
        return problems

    def _is_legacy_symlink_underlay(self) -> bool:
        mpc_path = os.path.join(self.underlay, "usv_nmpc", "lib", "usv_nmpc", "mpc_node")
        if not os.path.islink(mpc_path):
            return False
        resolved = os.path.realpath(mpc_path)
        underlay_real = os.path.realpath(self.underlay)
        return not resolved.startswith(underlay_real + os.sep)

    def _verify_original_b(self, identity: dict) -> dict:
        problems = []
        capture = os.path.join(self.release_root, "deploy", "capture_release_identity.py")
        out_dir = self.probe_dir or self.transaction_dir
        t0 = os.path.join(out_dir, "rollback-t0.json")
        t60 = os.path.join(out_dir, "rollback-t60.json")
        self._wait_for_original_b_ready()
        b_env = self.ros_env(identity, include_release=False)
        result_t0 = self.runner.run(
            ["runuser", "-u", "trevor", "--", "/usr/bin/python3", "-B", capture,
             "runtime", "--expected-install", self.underlay, "--output", t0],
            timeout=600, env=b_env)
        self.record("b_runtime_capture", output=t0, rc=result_t0["rc"])
        deadline = time.time() + ACCEPTANCE_SECONDS
        while time.time() < deadline:
            time.sleep(1.0)
        result_t60 = self.runner.run(
            ["runuser", "-u", "trevor", "--", "/usr/bin/python3", "-B", capture,
             "runtime", "--expected-install", self.underlay, "--output", t60,
             "--baseline", t0],
            timeout=600, env=b_env)
        self.record("b_runtime_capture_baseline", output=t60, rc=result_t60["rc"])

        if result_t0["rc"] != 0 or result_t60["rc"] != 0:
            if self._is_legacy_symlink_underlay() and os.path.isfile(t0) and os.path.isfile(t60):
                try:
                    with open(t0, "r", encoding="utf-8") as handle:
                        t0_doc = json.load(handle)
                    with open(t60, "r", encoding="utf-8") as handle:
                        t60_doc = json.load(handle)
                except (OSError, ValueError) as exc:
                    problems.append(f"unable to parse rollback captures: {exc}")
                else:
                    legacy_problems = self._evaluate_legacy_underlay_rollback(t0_doc, t60_doc)
                    self.record(
                        "b_legacy_underlay_evaluated",
                        problems=legacy_problems,
                        t0_failures=t0_doc.get("failures", []),
                        t60_failures=t60_doc.get("failures", []),
                    )
                    problems.extend(legacy_problems)
            else:
                if result_t0["rc"] != 0:
                    problems.append(f"original B runtime check failed: {t0}")
                if result_t60["rc"] != 0:
                    problems.append("original B 60s baseline check failed")
        state = self.service_state(UNIT)
        if state.get("ActiveState") != "active":
            problems.append(f"original B not active: {state.get('ActiveState')}")
        if self.dropin_path() == os.path.join(self.dropin_dir, DROPIN_NAME) and \
                os.path.isfile(self.dropin_path()):
            problems.append("commissioning drop-in still present")
        self.record("b_rollback_verified", problems=problems)
        return {"problems": problems, "t0": t0, "t60": t60}

    # ------------------------------------------------------------------ 入口
    def run(self) -> int:
        if self.args.action == "check-start":
            return self.action_check_start()
        lock = self.acquire_lock()
        try:
            if self.args.action == "takeover":
                return self.action_takeover()
            if self.args.action == "rollback":
                return self.action_rollback()
            raise DriverError(f"unknown action: {self.args.action}")
        finally:
            lock.close()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="方案A 实船调试服务接管维护 driver")
    parser.add_argument("--release-root", required=True)
    parser.add_argument("--underlay", required=True)
    parser.add_argument("--operator-attestation", required=True)
    parser.add_argument("--action", required=True,
                        choices=["takeover", "rollback", "check-start"])
    parser.add_argument("--evidence-dir", default="")
    parser.add_argument("--use-ntrip", choices=["true", "false"], default="true",
                        help="Launch-time use_ntrip argument for real.launch.py (false for indoor bench without RTK)")
    parser.add_argument("--backend", choices=["research_commissioning"],
                        default="research_commissioning",
                        help="Controller backend passed to real.launch.py in 30 drop-in")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.action != "check-start" and not args.evidence_dir:
        print("driver fatal: --evidence-dir is required for takeover/rollback",
              file=sys.stderr)
        return EXIT_FAIL
    driver = Driver(args)
    try:
        return driver.run()
    except DriverError as error:
        driver.record("driver_error", error=str(error)[:1000])
        driver.persist()
        print(f"driver error: {error}", file=sys.stderr)
        return EXIT_FAIL
    except Exception as error:  # noqa: BLE001 - 任何意外都必须留证并失败退出
        driver.record("driver_exception", error=repr(error)[:1000])
        driver.persist()
        print(f"driver exception: {error}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
