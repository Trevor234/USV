"""Finite recovery of this C0 runner's independently minted child groups.

Only a stable, complete-line snapshot of this run's owned ledger authorizes
signals.  Missing roles remain unknown.  This helper has no launch/ROS/R5 API.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import time

ROLES = ("regulator", "worker", "fixture", "recorder")
HEX = re.compile(r"[0-9a-f]{64}\Z")
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
MAX_LEDGER_BYTES = 4 * 1024 * 1024
MAX_LEDGER_ROWS = 10000
# The recovery target is Linux.  Numeric POSIX signals also let pure mocked
# tests run on the Windows authoring host without creating any OS processes.
SIGINT, SIGTERM, SIGKILL = 2, 15, 9


class AuthorizationError(ValueError):
    pass


class LinuxBackend:
    def __init__(self):
        from owned_process_supervisor import boot_id, proc_identity, proc_table
        self.boot_id = boot_id
        self.proc_identity = proc_identity
        self.proc_table = proc_table
        self.monotonic = time.monotonic
        self.sleep = time.sleep
        import os
        self.killpg = os.killpg


def _int(value, name):
    if type(value) is not int or not 0 < value <= (1 << 63) - 1:
        raise AuthorizationError("invalid positive integer: " + name)
    return value


def _exe(value):
    if (type(value) is not str or not value or not PurePosixPath(value).is_absolute()
            or PurePosixPath(value).as_posix() != value or ".." in PurePosixPath(value).parts
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise AuthorizationError("expected canonical absolute POSIX executable path")
    return value


def _digest(value):
    if type(value) is not str or not HEX.fullmatch(value):
        raise AuthorizationError("expected lowercase SHA256")
    return value


def _identity(row, *, leader=False):
    if type(row) is not dict:
        raise AuthorizationError("missing process identity")
    result = {k: _int(row.get(k), k) for k in ("pid", "ppid", "pgid", "sid", "start_ticks")}
    if result["pid"] > (1 << 31) - 1:
        raise AuthorizationError("PID outside Linux pid_t domain")
    result["exe"] = _exe(row.get("exe"))
    result["exe_sha256"] = _digest(row.get("exe_sha256"))
    result["state"] = row.get("state")
    if type(result["state"]) is not str or len(result["state"]) != 1:
        raise AuthorizationError("unknown process state")
    if leader and not result["pid"] == result["pgid"] == result["sid"]:
        raise AuthorizationError("role did not mint its own PGID/SID")
    return result


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuthorizationError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value):
    raise AuthorizationError("nonfinite JSON number: " + value)


def _finite_shape(row):
    pending = [(row, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > 100000 or depth > 12:
            raise AuthorizationError("ledger JSON shape bound")
        if type(value) is float and not math.isfinite(value):
            raise AuthorizationError("nonfinite ledger JSON number")
        if type(value) is dict:
            pending.extend((v, depth + 1) for v in value.values())
        elif type(value) is list:
            pending.extend((v, depth + 1) for v in value)


def _snapshot(path):
    path = Path(path)
    before = path.stat()
    if not path.is_file() or not 0 < before.st_size <= MAX_LEDGER_BYTES:
        raise AuthorizationError("ledger absent/empty/oversize")
    raw = path.read_bytes()
    after = path.stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(before, k) != getattr(after, k) for k in fields) or len(raw) != after.st_size:
        raise AuthorizationError("ledger changed during snapshot")
    if not raw.endswith(b"\n"):
        raise AuthorizationError("concurrent or unclosed ledger tail")
    lines = raw.decode("utf-8", errors="strict").splitlines()
    if len(lines) > MAX_LEDGER_ROWS or any(not line for line in lines):
        raise AuthorizationError("ledger row bound/blank row")
    rows = [json.loads(line, object_pairs_hook=_pairs, parse_constant=_nonfinite) for line in lines]
    for row in rows:
        _finite_shape(row)
    return rows, hashlib.sha256(raw).hexdigest(), len(raw)


def load_pins(ledger_path, expected_roles, expected_boot_id, *, runner_pid, backend=None):
    """Return validated ledger authorizations; missing roles are explicit unknown.

    expected_roles has exactly ROLES, each {'exe': resolved absolute POSIX path,
    'sha256': independently read digest}.  runner_pid is the outer-owned runner
    PID.  ledger_path must be that run directory's owned_process_ledger.jsonl.
    No process is signalled by this function.
    """
    backend = backend or LinuxBackend()
    if type(expected_boot_id) is not str or not UUID.fullmatch(expected_boot_id):
        raise AuthorizationError("invalid independently expected boot")
    _int(runner_pid, "runner_pid")
    if type(expected_roles) is not dict or set(expected_roles) != set(ROLES):
        raise AuthorizationError("expected role map must have exactly four roles")
    expected = {}
    for role, value in expected_roles.items():
        if type(value) is not dict or set(value) != {"exe", "sha256"}:
            raise AuthorizationError("invalid expected role pin: " + role)
        expected[role] = {"exe": _exe(value["exe"]), "sha256": _digest(value["sha256"])}
    path = Path(ledger_path)
    if path.name != "owned_process_ledger.jsonl" or not path.is_absolute():
        raise AuthorizationError("expected absolute owned ledger path within this run")
    if backend.boot_id() != expected_boot_id:
        raise AuthorizationError("current boot differs from independent expected boot")
    rows, digest, size = _snapshot(path)
    pins = {}
    descendants = []
    for row in rows:
        if type(row) is not dict or type(row.get("type")) is not str:
            raise AuthorizationError("invalid ledger event")
        _int(row.get("monotonic_ns"), "ledger.monotonic_ns")
        if row.get("boot_id") != expected_boot_id:
            raise AuthorizationError("ledger boot mismatch")
        if row["type"] == "spawn":
            role = row.get("name")
            if role not in ROLES or role in pins:
                raise AuthorizationError("unknown/duplicate owned role")
            identity = _identity(row.get("identity"), leader=True)
            if identity["ppid"] != runner_pid:
                raise AuthorizationError("spawn parent is not the outer-owned runner")
            pin = expected[role]
            if (row.get("executable_verified") is not True or row.get("expected_exe") != pin["exe"]
                    or row.get("expected_sha256") != pin["sha256"]
                    or identity["exe"] != pin["exe"] or identity["exe_sha256"] != pin["sha256"]):
                raise AuthorizationError("spawn executable pin mismatch: " + role)
            pins[role] = {"identity": identity, "members": {identity["pid"]: identity["start_ticks"]}}
        elif row["type"] == "owned_descendant_observed":
            descendants.append(row)
        elif row["type"] in {"launch_identity_missing", "launch_group_invalid"}:
            raise AuthorizationError("ledger explicitly contains unidentified owned launch")
    for row in descendants:
        role = row.get("name")
        if role not in pins:
            raise AuthorizationError("descendant has no owned spawn")
        identity = row.get("identity")
        if type(identity) is not dict:
            raise AuthorizationError("missing observed descendant identity")
        values = {k: _int(identity.get(k), k) for k in ("pid", "pgid", "sid", "start_ticks")}
        owner = pins[role]["identity"]
        if (values["pgid"] != owner["pid"] or values["sid"] != owner["pid"]
                or values["start_ticks"] < owner["start_ticks"]):
            raise AuthorizationError("foreign observed group/session")
        previous = pins[role]["members"].get(values["pid"])
        if previous is not None and previous != values["start_ticks"]:
            raise AuthorizationError("observed descendant PID reused")
        pins[role]["members"][values["pid"]] = values["start_ticks"]
    if len({p["identity"]["pid"] for p in pins.values()}) != len(pins):
        raise AuthorizationError("roles reuse a leader PID")
    if backend.boot_id() != expected_boot_id:
        raise AuthorizationError("boot changed during authorization snapshot")
    return {"schema": "p1-C0-inner-owned-pins-v1", "ledger_path": str(path),
            "ledger_sha256": digest, "ledger_bytes": size, "expected_boot_id": expected_boot_id,
            "runner_pid": runner_pid, "pins": pins, "missing_roles": [r for r in ROLES if r not in pins],
            "evidence_complete": set(pins) == set(ROLES)}


def _persist(event, kind, **details):
    if event(kind, **details) is not True:
        raise AuthorizationError("recovery evidence write not confirmed")


def _members(role, pin, boot, backend, event):
    if backend.boot_id() != boot:
        raise AuthorizationError("boot changed before owned operation")
    owner = pin["identity"]
    _check_known_members(role, pin, backend)
    live = backend.proc_identity(owner["pid"], hash_exe=True)
    if live is not None:
        # PPID may legitimately change after the runner exits; creation PPID
        # was already independently bound in load_pins.
        current = _identity(live, leader=True)
        for key in ("pid", "pgid", "sid", "start_ticks", "exe", "exe_sha256"):
            if current[key] != owner[key]:
                raise AuthorizationError("live leader identity changed: " + role + ":" + key)
    result = []
    for row in backend.proc_table():
        if type(row) is not dict:
            raise AuthorizationError("unknown proc-table row")
        if row.get("pgid") != owner["pid"]:
            continue
        for key in ("pid", "pgid", "sid", "start_ticks"):
            _int(row.get(key), "member." + key)
        if row["sid"] != owner["pid"] or row["start_ticks"] < owner["start_ticks"]:
            raise AuthorizationError("foreign group/session: " + role)
        old = pin["members"].get(row["pid"])
        if old is not None and old != row["start_ticks"]:
            raise AuthorizationError("known member PID reused: " + role)
        observed = backend.proc_identity(row["pid"], hash_exe=True)
        if observed is None:
            raise AuthorizationError("member identity disappeared during validation")
        observed = _identity(observed)
        if any(observed[key] != row[key] for key in ("pid", "pgid", "sid", "start_ticks")):
            raise AuthorizationError("member snapshot identity raced")
        if observed["pid"] == owner["pid"] and any(observed[key] != owner[key] for key in ("exe", "exe_sha256")):
            raise AuthorizationError("leader executable changed during group snapshot")
        if old is None:
            _persist(event, "C0_recovery_member_observed", role=role, identity=observed)
            pin["members"][row["pid"]] = row["start_ticks"]
        result.append(observed)
    if backend.boot_id() != boot:
        raise AuthorizationError("boot changed during member validation")
    _check_known_members(role, pin, backend)
    # New-member evidence callbacks can take time.  Recheck the leader after
    # persistence as well, before returning a group eligible for signalling.
    final = backend.proc_identity(owner["pid"], hash_exe=True)
    if final is not None:
        final = _identity(final, leader=True)
        if any(final[k] != owner[k] for k in ("pid", "pgid", "sid", "start_ticks", "exe", "exe_sha256")):
            raise AuthorizationError("leader changed after group validation")
    return result


def _check_known_members(role, pin, backend):
    # Query recorded PIDs before filtering a proc table by PGID.  An authorized
    # descendant can still exist outside the original group; an empty original
    # PGID then does not prove its cleanup, nor authorize chasing its new group.
    owner = pin["identity"]
    for pid, start_ticks in pin["members"].items():
        row = backend.proc_identity(pid, hash_exe=True)
        if row is None:
            continue
        row = _identity(row, leader=pid == owner["pid"])
        if (row["pid"] != pid or row["start_ticks"] != start_ticks
                or row["pgid"] != owner["pid"] or row["sid"] != owner["pid"]):
            raise AuthorizationError("known PID reused or escaped owned group/session: " + role)
        if pid == owner["pid"] and any(row[k] != owner[k] for k in ("exe", "exe_sha256")):
            raise AuthorizationError("known leader executable changed: " + role)


def _wait(role, pin, boot, backend, event, seconds):
    deadline = backend.monotonic() + seconds
    while True:
        rows = _members(role, pin, boot, backend, event)
        if not rows:
            return []
        remaining = deadline - backend.monotonic()
        if remaining <= 0:
            return rows
        backend.sleep(min(.05, remaining))


def recover(ledger_path, expected_roles, expected_boot_id, *, runner_pid, event,
            grace=.5, term_grace=1., kill_postcheck=1., backend=None):
    """Recover validated subset; full complete requires all four role pins.

    event(kind, **details) must synchronously persist and return True; a wrapper
    around outer Supervisor.event should return not supervisor.evidence_failed.
    No waitpid is used: these leaders need not be direct children of the caller.
    """
    backend = backend or LinuxBackend()
    result = {"schema": "p1-C0-inner-owned-recovery-v1", "ledger_path": str(ledger_path),
              "evidence_complete": False, "group_cleanup_complete": False,
              "cleanup_complete": False, "missing_roles": list(ROLES), "roles": {},
              "signals": [], "issues": [], "R5_complete": False, "execute_qualified": False}
    try:
        for value in (grace, term_grace, kill_postcheck):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 60:
                raise AuthorizationError("finite cleanup waits in [0,60] required")
        if not callable(event):
            raise AuthorizationError("persistent recovery event callback required")
        auth = load_pins(ledger_path, expected_roles, expected_boot_id, runner_pid=runner_pid, backend=backend)
        result.update({k: auth[k] for k in ("ledger_sha256", "ledger_bytes", "missing_roles", "evidence_complete")})
        _persist(event, "C0_recovery_authorized", ledger_path=str(ledger_path),
                 ledger_sha256=auth["ledger_sha256"], runner_pid=runner_pid,
                 missing_roles=auth["missing_roles"], identities={r:p["identity"] for r,p in auth["pins"].items()})
        # Any unknown/reused/foreign live authorization aborts globally before
        # the first signal; missing roles alone allow cleanup of known subset.
        for role, pin in auth["pins"].items():
            _members(role, pin, expected_boot_id, backend, event)
        for role in ROLES:
            if role not in auth["pins"]:
                continue
            pin = auth["pins"][role]
            rows = _wait(role, pin, expected_boot_id, backend, event, 0.)
            for sig, wait in ((SIGINT, grace), (SIGTERM, term_grace), (SIGKILL, kill_postcheck)):
                if not rows:
                    break
                # Revalidate immediately before EVERY signal; no name-based
                # discovery and no PID-only authority is used.
                rows = _members(role, pin, expected_boot_id, backend, event)
                if any(row["state"] != "Z" for row in rows):
                    _persist(event, "C0_recovery_signal", role=role, pgid=pin["identity"]["pid"],
                             signal=int(sig), members=rows)
                    # Evidence persistence can take time; verify again before
                    # touching the authorized group.
                    rows = _members(role, pin, expected_boot_id, backend, event)
                    if any(row["state"] != "Z" for row in rows):
                        try:
                            backend.killpg(pin["identity"]["pid"], sig)
                        except ProcessLookupError:
                            pass
                        result["signals"].append({"role": role, "pgid": pin["identity"]["pid"], "signal": int(sig)})
                rows = _wait(role, pin, expected_boot_id, backend, event, wait)
            leader = backend.proc_identity(pin["identity"]["pid"], hash_exe=False)
            report = {"cleanup_complete": not rows, "remaining_members": rows,
                      "leader_status": "absent" if leader is None else "exited_zombie" if leader.get("state") == "Z" else "present"}
            _persist(event, "C0_recovery_role_result", role=role, **report)
            result["roles"][role] = report
        _, after, _ = _snapshot(ledger_path)
        result["ledger_sha256_after"] = after
        result["ledger_snapshot_unchanged"] = after == auth["ledger_sha256"]
        if after != auth["ledger_sha256"]:
            result["evidence_complete"] = False
            result["issues"].append("inner_ledger_changed_during_recovery")
        result["group_cleanup_complete"] = bool(auth["pins"]) and all(r["cleanup_complete"] for r in result["roles"].values()) and set(result["roles"]) == set(auth["pins"])
        result["cleanup_complete"] = result["evidence_complete"] and result["group_cleanup_complete"]
        if result["missing_roles"]:
            result["issues"].append("unrecorded_roles_remain_unknown")
        if not result["group_cleanup_complete"]:
            result["issues"].append("known_owned_groups_not_empty")
        _persist(event, "C0_recovery_summary", **result)
    except Exception as error:
        result["evidence_complete"] = False
        result["cleanup_complete"] = False
        result["group_cleanup_complete"] = False
        result["issues"].append(type(error).__name__ + ": " + str(error))
    return result
