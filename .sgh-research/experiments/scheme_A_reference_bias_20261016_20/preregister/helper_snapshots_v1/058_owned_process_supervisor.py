"""Finite cleanup of Linux process groups created by this supervisor only."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import BinaryIO


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def proc_identity(pid: int, hash_exe: bool = True) -> dict | None:
    try:
        root = Path("/proc") / str(pid)
        raw = (root / "stat").read_text()
        fields = raw[raw.rindex(")") + 2:].split()
        result = {"pid": pid, "state": fields[0], "ppid": int(fields[1]),
                  "pgid": int(fields[2]), "sid": int(fields[3]),
                  "start_ticks": int(fields[19])}
        try:
            result["exe"] = os.readlink(root / "exe")
            result["exe_sha256"] = sha256_file(root / "exe") if hash_exe else None
        except (FileNotFoundError, PermissionError, OSError):
            result["exe"] = None
            result["exe_sha256"] = None
        return result
    except (FileNotFoundError, ProcessLookupError):
        return None


def proc_table() -> list[dict]:
    result = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdecimal():
            item = proc_identity(int(entry.name), hash_exe=False)
            if item:
                result.append(item)
    return result


def finite_seconds(value: float) -> float:
    if not math.isfinite(value) or value < 0 or value > 60:
        raise ValueError("each cleanup wait must be finite, in [0, 60] seconds")
    return value


@dataclass
class Owned:
    name: str
    process: subprocess.Popen
    identity: dict
    output: BinaryIO
    members: dict[int, int] = field(default_factory=dict)
    cleanup: dict | None = None


class Supervisor:
    def __init__(self, directory: Path):
        if os.name != "posix" or not Path("/proc/self/stat").exists():
            raise RuntimeError("Linux /proc and POSIX process groups required")
        self.directory = directory
        self.boot = boot_id()
        self.owned: dict[str, Owned] = {}
        self.unverified_children: list[dict] = []
        self.unexpected_descendants: list[dict] = []
        self.cleanup_failed = False
        self.evidence_failed = False
        self.memory_tail: list[dict] = []
        self.ledger = (directory / "owned_process_ledger.jsonl").open("x")

    def event(self, kind: str, **details) -> None:
        item = {"type": kind, "monotonic_ns": time.monotonic_ns(),
                "boot_id": self.boot, **details}
        self.memory_tail.append(item)
        self.memory_tail = self.memory_tail[-256:]
        try:
            self.ledger.write(json.dumps(item, sort_keys=True) + "\n")
            self.ledger.flush()
        except (OSError, ValueError):
            # Observation IO failure never skips the remaining owned cleanup.
            # New launches stop; resource and evidence outcomes remain separate.
            self.evidence_failed = True

    def spawn(self, name: str, argv: list[str], env: dict[str, str],
              expected_exe: Path, expected_sha: str, cwd: Path | None = None) -> Owned:
        if self.cleanup_failed:
            raise RuntimeError("cleanup_failed: spawning further children is forbidden")
        if self.evidence_failed:
            raise RuntimeError("supervision ledger failed: spawning further children is forbidden")
        if name in self.owned:
            raise ValueError("duplicate child name")
        expected_exe = expected_exe.resolve(strict=True)
        if sha256_file(expected_exe) != expected_sha:
            raise RuntimeError("prelaunch executable hash changed: " + name)
        out = (self.directory / (name + ".console.log")).open("xb")
        try:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=subprocess.STDOUT,
                                       start_new_session=True, close_fds=True)
        except BaseException:
            out.close()
            raise
        identity = proc_identity(process.pid)
        if identity is None:
            # Never signal an unidentified group, even on an exceptional launch.
            self.cleanup_failed = True
            self.unverified_children.append({"name": name, "pid": process.pid,
                                             "reason": "launch_identity_missing"})
            out.close()
            self.event("launch_identity_missing", name=name, pid=process.pid)
            raise RuntimeError("child identity unavailable; retained for manual inspection")
        if identity["pgid"] != process.pid or identity["sid"] != process.pid:
            self.cleanup_failed = True
            self.unverified_children.append({"name": name, "identity": identity,
                                             "reason": "launch_group_invalid"})
            out.close()
            self.event("launch_group_invalid", name=name, identity=identity)
            raise RuntimeError("child did not acquire its own process group/session")
        item = Owned(name, process, identity, out, {process.pid: identity["start_ticks"]})
        self.owned[name] = item
        valid_exe = (identity["exe"] is not None
                     and Path(identity["exe"]).resolve() == expected_exe
                     and identity["exe_sha256"] == expected_sha)
        self.event("spawn", name=name, identity=identity, argv=argv,
                   expected_exe=str(expected_exe), expected_sha256=expected_sha,
                   executable_verified=valid_exe)
        if not valid_exe:
            self.evidence_failed = True
            raise RuntimeError("actual executable identity mismatch: " + name)
        return item

    def members(self, item: Owned) -> list[dict]:
        if boot_id() != self.boot:
            raise RuntimeError("boot identity changed")
        leader = proc_identity(item.process.pid, hash_exe=False)
        if leader and leader["start_ticks"] != item.identity["start_ticks"]:
            raise RuntimeError("owned leader PID was reused; refusing signals")
        result = []
        for entry in proc_table():
            if entry["pgid"] == item.process.pid:
                if entry["sid"] != item.process.pid:
                    raise RuntimeError("foreign session found in owned group")
                previous = item.members.get(entry["pid"])
                if previous is not None and previous != entry["start_ticks"]:
                    raise RuntimeError("owned descendant PID was reused")
                if previous is None:
                    observed = proc_identity(entry["pid"])
                    self.unexpected_descendants.append({"name": item.name, "identity": observed or entry})
                    self.event("owned_descendant_observed", name=item.name,
                               identity=observed or entry, qualification_clean=False)
                item.members[entry["pid"]] = entry["start_ticks"]
                result.append(entry)
        return result

    def wait_empty(self, item: Owned, timeout: float) -> bool:
        deadline = time.monotonic() + finite_seconds(timeout)
        while True:
            item.process.poll()  # Nonblocking waitpid reaps the owned direct child.
            if not self.members(item):
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(.05, remaining))

    def send(self, item: Owned, sig: int) -> None:
        members = self.members(item)
        if members:
            # PGID was minted by start_new_session; its session and leader start
            # identity are checked on every signal. No discovery-based kill.
            self.event("signal", name=item.name, signal=int(sig), members=members)
            try:
                os.killpg(item.process.pid, sig)
            except ProcessLookupError:
                pass

    def stop(self, item: Owned, grace: float, term_grace: float,
             kill_postcheck: float, first_signal: int = signal.SIGINT,
             natural_grace: float = 0) -> dict:
        if item.cleanup is not None:
            return item.cleanup
        for value in (grace, term_grace, kill_postcheck, natural_grace):
            finite_seconds(value)
        try:
            empty = self.wait_empty(item, natural_grace)
            if not empty:
                self.send(item, first_signal)
                empty = self.wait_empty(item, grace)
            if not empty:
                self.send(item, signal.SIGTERM)
                empty = self.wait_empty(item, term_grace)
            if not empty:
                self.send(item, signal.SIGKILL)
                empty = self.wait_empty(item, kill_postcheck)
            result = {"name": item.name, "cleanup_complete": empty,
                      "returncode": item.process.poll(),
                      "remaining_members": self.members(item)}
        except BaseException as error:
            result = {"name": item.name, "cleanup_complete": False,
                      "returncode": item.process.poll(), "error": repr(error)}
        result["resource_cleanup_complete"] = result["cleanup_complete"]
        result["unexpected_descendants"] = [r for r in self.unexpected_descendants if r["name"] == item.name]
        result["qualification_clean"] = bool(result["cleanup_complete"] and result["returncode"] == 0 and not result["unexpected_descendants"] and not self.evidence_failed and not self.unverified_children)
        item.cleanup = result
        self.cleanup_failed |= not result["cleanup_complete"]
        self.event("cleanup_result", **result)
        item.output.close()
        return result

    def close(self) -> None:
        self.event("supervisor_summary", cleanup_failed=self.cleanup_failed,
                   children={name: child.cleanup for name, child in self.owned.items()},
                   unverified_children=self.unverified_children,
                   unexpected_descendants=self.unexpected_descendants,
                   qualification_clean=not (self.cleanup_failed or self.evidence_failed or self.unverified_children or self.unexpected_descendants),
                   source_completeness_proven=False)
        try:
            self.ledger.close()
        except OSError:
            self.evidence_failed = True
