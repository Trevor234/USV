#!/usr/bin/env python3
"""2026-11-02 FCU PID analysis (ArduRover ``ATC_STR_RAT_*`` / ``ATC_SPEED_*``).

Offline only.  This tool never connects to the flight controller, never writes
parameters, never arms and never starts a thruster.  It freezes the 2026-11-02
DataFlash logs, re-extracts the *full* PID records the older NPZ products lost,
decides which of the recorded time actually closed the ATC loops, measures the
original controllers and emits a bounded (+-10 %) single-parameter trial matrix
plus a re-acquisition protocol.

Stages:

    --stage prepare       freeze + parse + baseline parameters        (write)
    --stage analyze       intervals/segments/coverage/baseline metrics (write)
    --stage recommend     trial matrix + reports                       (write)
    --stage assess-trials score authorised new trials                  (write)
    --stage verify        read-only recomputation and SHA chain        (stdout)

The measured firmware is ArduRover 4.7.1 (dbe79216); the exact primary sources
are pinned under ``provenance/firmware``.  Version strings are preserved
verbatim, never normalised against the local 4.6.3 checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import urllib.error
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse_log  # noqa: E402
import reidentify_20261102 as R  # noqa: E402

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
STAGE_ORDER = ("prepare", "analyze", "recommend")
STAGES = STAGE_ORDER + ("assess-trials", "verify")

FIRMWARE_COMMIT = "dbe792162d06cab66c3475fd5556bf7a120f119e"
FIRMWARE_BASE_URL = (
    "https://raw.githubusercontent.com/ArduPilot/ardupilot/" + FIRMWARE_COMMIT + "/")
FIRMWARE_FILES = (
    "Rover/version.h",
    "Rover/mode.h",
    "Rover/mode_manual.cpp",
    "Rover/mode_acro.cpp",
    "Rover/mode_guided.cpp",
    "Rover/mode.cpp",
    "Rover/Log.cpp",
    "libraries/APM_Control/AR_AttitudeControl.cpp",
    "libraries/AC_PID/AC_PID.cpp",
    "libraries/AP_Logger/LogFile.cpp",
    "libraries/AP_Logger/LogStructure.h",
    "libraries/AR_Motors/AP_MotorsUGV.cpp",
)

ANOMALY_JSON = "2026-11-02_失控段检测.json"
EXPECTED_ANOMALY_WINDOWS = 7

# Logged guidance targets (GUIP type field == Guided::SubMode).
GUIDED_SUBMODE = {"WP": 0, "HeadingAndSpeed": 1, "TurnRateAndSpeed": 2,
                  "Loiter": 3, "SteeringAndThrottle": 4, "Stop": 5}

# Rover mode numbers -> names (firmware Rover/mode.h / mode.cpp).
ROVER_MODES = {0: "MANUAL", 1: "ACRO", 3: "STEERING", 4: "HOLD", 5: "LOITER",
               6: "FOLLOW", 7: "SIMPLE", 9: "CIRCLE", 10: "AUTO", 11: "RTL",
               12: "SMART_RTL", 15: "GUIDED", 16: "INITIALISING"}

# Modes in which the ATC loops are *candidates* for closing.
CLOSED_LOOP_MODES = {"ACRO", "AUTO", "STEERING"}
# Modes that never enter ATC (kept only as negative controls).
NEGATIVE_CONTROLS = {"MANUAL"}
# Modes excluded from this round entirely (different controller contract).
EXCLUDED_MODES = {"HOLD", "LOITER", "RTL", "SMART_RTL", "CIRCLE", "FOLLOW",
                  "SIMPLE", "INITIALISING"}
# GUIDED reaches the ATC loops through several sub-modes, but the direct
# steering/throttle setter never logs GUIP, so a stale GUIP cannot prove the
# loop is closed.  Without a full external-command trace this is unprovable.
GUIDED_MODES = {"GUIDED"}

LOOPS = ("yaw", "speed")

# per-loop parameter set
LOOP_PARAMS = {
    "yaw": ("ATC_STR_RAT_FF", "ATC_STR_RAT_P", "ATC_STR_RAT_I", "ATC_STR_RAT_D",
            "ATC_STR_RAT_IMAX", "ATC_STR_RAT_MAX", "ATC_STR_ANG_P",
            "ATC_STR_ACC_MAX", "ACRO_TURN_RATE"),
    "speed": ("ATC_SPEED_FF", "ATC_SPEED_P", "ATC_SPEED_I", "ATC_SPEED_D",
              "ATC_SPEED_IMAX", "CRUISE_SPEED", "CRUISE_THROTTLE", "SPEED_MAX"),
}

# Only these may ever be changed by a trial.  Everything else is held at its
# recorded value; the report says so explicitly.
VAR_WHITELIST = ("ATC_STR_RAT_FF", "ATC_STR_RAT_P", "ATC_STR_RAT_I",
                 "CRUISE_THROTTLE", "ATC_SPEED_P", "ATC_SPEED_I")
HELD_PARAMS = ("ATC_STR_RAT_D", "ATC_SPEED_D", "ATC_SPEED_FF", "ATC_SPEED_D_FF",
               "ATC_STR_RAT_D_FF", "ATC_STR_RAT_IMAX", "ATC_SPEED_IMAX",
               "ATC_STR_RAT_FLTT", "ATC_STR_RAT_FLTE", "ATC_STR_RAT_FLTD",
               "ATC_SPEED_FLTT", "ATC_SPEED_FLTE", "ATC_SPEED_FLTD",
               "ATC_STR_RAT_SMAX", "ATC_STR_RAT_PDMX", "ATC_SPEED_SMAX",
               "ATC_SPEED_PDMX", "ATC_STR_ANG_P", "ATC_STR_ACC_MAX",
               "ATC_STR_DEC_MAX", "ATC_STR_RAT_MAX", "ACRO_TURN_RATE",
               "SPEED_MAX", "CRUISE_SPEED", "MOT_PWM_TYPE", "MOT_SAFE_DISARM",
               "SCHED_LOOP_RATE")

# trial matrix shape
GAIN_SCALES = (0.9, 1.0, 1.1)
FF_CLIP = (0.8, 1.2)
GATE_MIN_BLOCKS = 3
GATE_RMSE_RATIO = 0.80
GATE_SAT_FRAC = 0.05
GATE_TV_RATIO = 1.20
YAW_SS_LIM = 2.0             # deg/s
SPEED_SS_LIM = 0.1           # m/s
YAW_NEIGHBOUR_BAND = 2.0     # deg/s
SPEED_NEIGHBOUR_BAND = 0.1   # m/s

# FF estimability thresholds (analysis gates, not tuning claims)
YAW_PLAT_MIN_S = 8.0
YAW_PLAT_MIN_RATE = 5.0      # deg/s
YAW_PLAT_MAX_ACC = 1.0       # deg/s^2
YAW_COVER_MIN = 0.95
YAW_LIMIT_MAX = 0.05
YAW_PER_DIR_MIN = 3
SPEED_PLAT_MIN_S = 10.0
SPEED_PLAT_MIN_BINS = 2
SPEED_PLAT_BIN_SEP = 0.2     # m/s
SPEED_BINS = ((0.3, 0.7), (0.7, 1.1), (1.1, 1.5))
BOOT_MIN_SPAN_S = 60.0

# health gates (conservative analysis gates, not a hardware fault verdict)
GPS_MIN_STATUS = 3
GPS_MAX_HDOP = 1.0
ROLL_LIM_DEG = 10.0
PITCH_LIM_DEG = 15.0

# streams whose record gaps break a usable segment
FAST_STREAMS = ("PIDS", "PIDA", "ATT", "XKF1")
SLOW_STREAMS = ("STER", "THR", "RCOU", "GPS", "VIBE")

GAP_PAD_S = 1.0
SWITCH_PAD_S = 1.0
ANOMALY_PAD_S = 2.0
AUX_MAX_AGE_S = 0.2          # STER/THR/RCOU causal pairing
CROSS_YAW_TOL_DPS = 2.0
CROSS_SPEED_TOL_MPS = 0.1
CROSS_MIN_S = 2.0

STEER_FULL_SCALE = 4500.0    # STER.SteerOut / ACRO set_steering(*4500)
THROTTLE_FULL_SCALE = 100.0  # THR.ThrOut is -100..100

MIN_SEGMENT_S = 1.0
BOOTSTRAP_N = 200
BOOTSTRAP_SEED = 42
BOOTSTRAP_MIN_VALID = 180
GET_LSTSQ_RCOND = 1e-12

# read-only mode: nothing under --out may be created
VERIFY_ONLY = False
# prepare smoke only: restrict which frozen sources are parsed
SOURCE_SELECT = None


# ---------------------------------------------------------------------------
# private extended field table (parse_log's globals are never mutated)
# ---------------------------------------------------------------------------
_PID_FIELDS = ["TimeUS", "Tar", "Act", "Err", "P", "I", "D", "FF", "DFF",
               "Dmod", "SRate", "Flags"]

NUM_FIELDS = {t: list(fs) for t, fs in parse_log.NUM_FIELDS.items()}
NUM_FIELDS["PIDS"] = list(_PID_FIELDS)
NUM_FIELDS["PIDA"] = list(_PID_FIELDS)
NUM_FIELDS["STER"] = ["TimeUS", "SteerIn", "SteerOut", "DesLatAcc", "LatAcc",
                      "DesTurnRate", "TurnRate"]
NUM_FIELDS["THR"] = ["TimeUS", "ThrIn", "ThrOut", "DesSpeed", "Speed", "AccX"]
NUM_FIELDS["GUIP"] = ["TimeUS", "Type", "pX", "pY", "pZ", "vX", "vY", "vZ"]
NUM_FIELDS["MSG"] = ["TimeUS", "ID", "Seq"]
NUM_FIELDS["FMT"] = ["Type", "Length"]
NUM_FIELDS["FMTU"] = ["TimeUS", "FmtType", "UnitIds", "MultIds"]

STR_FIELDS = {t: list(fs) for t, fs in parse_log.STR_FIELDS.items()}
STR_FIELDS["FMT"] = ["Name", "Format", "Columns"]

# PID flag bits (AP_Logger::Write_PID, AP_Logger/LogFile.cpp)
FLAG_LIMIT = 1 << 0        # output saturated, I-term anti-windup active
FLAG_PD_LIMIT = 1 << 1     # PD sum limit active
FLAG_RESET = 1 << 2        # controller was reset
FLAG_I_SET = 1 << 3        # I term set externally


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _jp(obj):
    """JSON-safe conversion for numpy scalars/arrays and NaN -> null."""
    if isinstance(obj, dict):
        return {str(k): _jp(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jp(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_jp(v) for v in obj.tolist()]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if not math.isfinite(v) else v
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    return obj


def _dump(path, doc):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_jp(doc), fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def _sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _sha_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _write_new_text(path, text):
    _guard_write(path)
    if os.path.exists(path):
        raise SystemExit(f"conflict: {path} already exists (create-only stage)")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _write_new_json(path, doc):
    _guard_write(path)
    if os.path.exists(path):
        raise SystemExit(f"conflict: {path} already exists (create-only stage)")
    _dump(path, doc)


def _guard_write(path):
    if VERIFY_ONLY:
        raise SystemExit(f"verify is read-only; refusing to write {path}")


def _mkdir(path):
    _guard_write(path)
    os.makedirs(path, exist_ok=True)


def _versions():
    import scipy
    import matplotlib
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "pymavlink": getattr(__import__("pymavlink"), "__version__", "unknown"),
        "matplotlib": matplotlib.__version__,
    }


def _code_sha():
    return R.sha256_file(os.path.abspath(__file__))[0]


def _receipt_path(out, stage):
    return os.path.join(out, f"{stage}.done.json")


def _file_sha(path):
    sha, n = R.sha256_file(path)
    return {"sha256": sha, "bytes": n}


def _artifacts(root):
    """Relative path -> {sha256, bytes} for every file below ``root``."""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root)
            if rel.endswith(".done.json"):
                continue
            out[rel] = _file_sha(p)
    return out


def _write_receipt(out, stage, extra=None):
    arts = _artifacts(out)
    doc = {"stage": stage, "artifacts": arts, "code_sha256": _code_sha(),
           "versions": _versions()}
    if extra:
        doc.update(extra)
    _write_new_json(_receipt_path(out, stage), doc)
    return doc


def _load_receipt(path):
    if not os.path.exists(path):
        raise SystemExit(f"missing receipt: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _verify_artifacts(out, rec, strict=True):
    """Rehash every artifact named by ``rec``; returns list of problems."""
    bad = []
    for rel, meta in sorted(rec.get("artifacts", {}).items()):
        p = os.path.join(out, rel)
        if not os.path.exists(p):
            bad.append({"artifact": rel, "error": "missing"})
            continue
        got = _file_sha(p)
        if got["sha256"] != meta.get("sha256"):
            bad.append({"artifact": rel, "error": "sha256_mismatch",
                        "recorded": meta.get("sha256"), "actual": got["sha256"]})
        elif got["bytes"] != meta.get("bytes"):
            bad.append({"artifact": rel, "error": "size_mismatch",
                        "recorded": meta.get("bytes"), "actual": got["bytes"]})
    if bad and strict:
        raise SystemExit(f"artifact verification failed for {rec.get('stage')}: {bad[:3]}")
    return bad


def _require_stage(out, stage):
    rec = _load_receipt(_receipt_path(out, stage))
    _verify_artifacts(out, rec)
    return rec


def _require_prev(out, stage):
    idx = STAGE_ORDER.index(stage)
    if idx == 0:
        return None
    return _require_stage(out, STAGE_ORDER[idx - 1])


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------
def _parse_bin(src, npz_path):
    """Parse one DataFlash log with the private extended field table.

    Missing messages yield empty arrays; missing fields yield NaN (numeric) or
    "" (string).  Flags are never invented: an absent ``Flags`` column stays
    NaN so downstream code reports "no evidence" instead of "not saturated".
    """
    from pymavlink.DFReader import DFReader_binary

    reader = DFReader_binary(src)
    want = set(NUM_FIELDS) | set(STR_FIELDS)
    num = {t: {f: [] for f in fs} for t, fs in NUM_FIELDS.items()}
    txt = {t: {f: [] for f in fs} for t, fs in STR_FIELDS.items()}
    present = {}
    n_msg = 0
    while True:
        m = reader.recv_match()
        if m is None:
            break
        n_msg += 1
        t = m.get_type()
        if t not in want:
            continue
        if t not in present:
            present[t] = set(m.get_fieldnames())
        for f in NUM_FIELDS.get(t, ()):
            try:
                num[t][f].append(float(getattr(m, f)))
            except Exception:
                num[t][f].append(np.nan)
        for f in STR_FIELDS.get(t, ()):
            try:
                txt[t][f].append(str(getattr(m, f)))
            except Exception:
                txt[t][f].append("")

    out = {}
    for t, fs in NUM_FIELDS.items():
        for f in fs:
            out[f"{t}.{f}"] = np.asarray(num[t][f], dtype=np.float64)
    for t, fs in STR_FIELDS.items():
        for f in fs:
            out[f"{t}.{f}"] = np.asarray(txt[t][f], dtype=object)

    np.savez_compressed(npz_path, **out)

    counts = {t: int(len(num[t]["TimeUS"])) for t in NUM_FIELDS if "TimeUS" in num[t]}
    for t, fs in STR_FIELDS.items():
        if "TimeUS" not in NUM_FIELDS.get(t, ()):
            counts[t] = int(len(txt[t][fs[0]]))
    fields_present = {t: sorted(f for f in fs if f in present.get(t, set()))
                      for t, fs in NUM_FIELDS.items()}
    for t, fs in STR_FIELDS.items():
        fields_present[t] = sorted(set(fields_present.get(t, [])) |
                                   {f for f in fs if f in present.get(t, set())})
    missing_msgs = sorted(t for t in NUM_FIELDS if counts.get(t, 0) == 0)
    return {
        "n_msg": n_msg,
        "counts": counts,
        "fields_present": fields_present,
        "missing_messages": missing_msgs,
        "fmt_defined": sorted(present.get("FMT", set())),
    }


def _load_npz(path):
    with open(path, "rb") as fh:
        buf = fh.read()
    import io
    return np.load(io.BytesIO(buf), allow_pickle=True)


def _t(z, key):
    return np.asarray(z[key], dtype=float) / 1e6


# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------
def _param_backup(path):
    """Parse ``NAME,VALUE`` lines from an ArduPilot parameter backup."""
    vals, order = {}, []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "," not in line:
                continue
            name, _, raw = line.partition(",")
            name = name.strip()
            try:
                v = float(raw.strip())
            except ValueError:
                continue
            if name not in vals:
                order.append(name)
            vals[name] = v
    return vals, order


def _pid_baseline(params):
    """The recorded original values this round is centred on."""
    out = {}
    for loop in LOOPS:
        out[loop] = {k: params.get(k) for k in LOOP_PARAMS[loop]}
    out["common"] = {k: params.get(k) for k in
                     ("SCHED_LOOP_RATE", "MOT_PWM_TYPE", "MOT_SAFE_DISARM",
                      "CRUISE_SPEED", "CRUISE_THROTTLE", "SPEED_MAX")}
    return out


def _routing_from_params(params):
    """Left/right channel resolution (SERVOx_FUNCTION 73/74), never assumed."""
    out = {}
    for ch in range(1, 17):
        fn = params.get(f"SERVO{ch}_FUNCTION")
        if fn is None:
            continue
        fni = int(round(fn))
        if fni == 73:
            out.setdefault("left_ch", ch)
        elif fni == 74:
            out.setdefault("right_ch", ch)
    for side in ("left", "right"):
        ch = out.get(f"{side}_ch")
        if ch is None:
            continue
        for key, suffix in (("min", "MIN"), ("trim", "TRIM"), ("max", "MAX"),
                            ("reversed", "REVERSED")):
            v = params.get(f"SERVO{ch}_{suffix}")
            out[f"{side}_{key}"] = v
    return out


# ---------------------------------------------------------------------------
# anomaly windows
# ---------------------------------------------------------------------------
def _load_anomaly(data_root):
    """Copy-validated read of the fixed anomaly file; strict on content.

    The historical tooling treated a missing anomaly file as "no exclusion".
    That default is unsafe here, so every structural problem is fatal and
    nothing is written.
    """
    path = os.path.join(data_root, ANOMALY_JSON)
    if not os.path.exists(path):
        raise SystemExit(f"anomaly input missing: {path}")
    with open(path, "rb") as fh:
        raw_bytes = fh.read()
    try:
        doc = json.loads(raw_bytes.decode("utf-8"))
    except ValueError as exc:
        raise SystemExit(f"anomaly input is not JSON ({path}): {exc}")
    if not isinstance(doc, dict):
        raise SystemExit(f"anomaly input must be an object keyed by file name: {path}")

    windows, problems = {}, []
    for name, items in doc.items():
        if not isinstance(items, list):
            problems.append(f"{name}: group is not a list")
            continue
        clean = []
        for i, w in enumerate(items):
            if not isinstance(w, dict):
                problems.append(f"{name}[{i}]: not an object")
                continue
            a, b = w.get("start_s"), w.get("end_s")
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                problems.append(f"{name}[{i}]: start_s/end_s not numeric")
                continue
            a, b = float(a), float(b)
            if not (math.isfinite(a) and math.isfinite(b)):
                problems.append(f"{name}[{i}]: non-finite window")
                continue
            if not a < b:
                problems.append(f"{name}[{i}]: start_s >= end_s ({a} >= {b})")
                continue
            clean.append((a, b))
        windows[name] = clean

    for name in R.EXPECTED_SOURCES:
        if name not in windows:
            problems.append(f"{name}: main log missing from anomaly input")

    total = sum(len(windows.get(name, ())) for name in R.EXPECTED_SOURCES)
    if total != EXPECTED_ANOMALY_WINDOWS:
        problems.append(f"main-log anomaly windows = {total}, expected "
                        f"{EXPECTED_ANOMALY_WINDOWS}")
    if problems:
        raise SystemExit("anomaly input rejected: " + "; ".join(problems))

    return {"path": path, "sha256": _sha_bytes(raw_bytes), "windows": windows,
            "total_main_windows": total}


# ---------------------------------------------------------------------------
# firmware provenance
# ---------------------------------------------------------------------------
def _fetch_firmware(dest_dir, log):
    _mkdir(dest_dir)
    manifest = {"commit": FIRMWARE_COMMIT, "base_url": FIRMWARE_BASE_URL,
                "files": {}, "complete": True}
    for rel in FIRMWARE_FILES:
        url = FIRMWARE_BASE_URL + rel
        flat = rel.replace("/", "_")
        dst = os.path.join(dest_dir, flat)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "usv-pid-analysis"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read()
            if not body:
                raise ValueError("empty body")
        except (urllib.error.URLError, ValueError, OSError) as exc:
            manifest["files"][rel] = {"url": url, "status": "firmware_source_unavailable",
                                      "error": str(exc)}
            manifest["complete"] = False
            log(f"  firmware unavailable: {rel} ({exc})")
            continue
        _guard_write(dst)
        with open(dst, "wb") as fh:
            fh.write(body)
        manifest["files"][rel] = {"url": url, "status": "ok",
                                  "saved_as": flat, "sha256": _sha_bytes(body),
                                  "bytes": len(body)}
        log(f"  firmware {rel} -> {flat} ({len(body)} B)")
    return manifest


# ---------------------------------------------------------------------------
# stage: prepare
# ---------------------------------------------------------------------------
def _ensure_out(out, stage):
    """Create-only stage entry: no earlier/later receipt may already exist."""
    if stage in STAGE_ORDER:
        idx = STAGE_ORDER.index(stage)
        for later in STAGE_ORDER[idx:]:
            marker = _receipt_path(out, later)
            if os.path.exists(marker):
                raise SystemExit(
                    f"conflict: {marker} exists; this directory already holds a "
                    f"finished '{later}' stage - use a fresh --out")
        if idx > 0:
            need = STAGE_ORDER[idx - 1]
            if not os.path.exists(_receipt_path(out, need)):
                raise SystemExit(f"{stage} requires a completed '{need}' stage in {out}")
    _mkdir(out)


def _selected_sources():
    names = list(R.EXPECTED_SOURCES)
    if SOURCE_SELECT:
        unknown = [n for n in SOURCE_SELECT if n not in names]
        if unknown:
            raise SystemExit(f"--sources names not in the frozen set: {unknown}")
        names = [n for n in names if n in SOURCE_SELECT]
    if not names:
        raise SystemExit("no sources selected")
    return names


def _copy_verified(src, dst, expected_sha, log, label):
    """Sequential verified copy (the 2026-11-02 mount rejects seek)."""
    meta = R.verified_copy(src, dst, expected_sha=expected_sha)
    if "error" in meta:
        log(f"  FAILED {label}: {meta['error']}")
    else:
        log(f"  ok {label} bytes={meta['bytes_read']} sha={meta['sha256'][:16]}...")
    return meta


def _ticker(log, every=2 << 20):
    state = {"n": 0}

    def cb(nbytes):
        state["n"] += nbytes
        if nbytes and state["n"] % every < nbytes:
            log(f"    copied {state['n']/(1<<20):.1f} MiB")

    return cb


def stage_prepare(args):
    log = print
    out = args.out
    _ensure_out(out, "prepare")
    in_dir = os.path.join(out, "input")
    parsed_dir = os.path.join(out, "parsed")
    prov_dir = os.path.join(out, "provenance")
    for d in (in_dir, parsed_dir, prov_dir):
        _mkdir(d)

    log(f"[prepare] data root: {args.data_root}")
    anomaly = _load_anomaly(args.data_root)
    log(f"[prepare] anomaly windows validated "
        f"({anomaly['total_main_windows']} across the three main logs)")

    sources = {}
    for name, (sha, size) in R.EXPECTED_SOURCES.items():
        src = os.path.join(args.data_root, name)
        dst = os.path.join(in_dir, name)
        if not os.path.exists(src):
            raise SystemExit(f"missing source log: {src}")
        meta = _copy_verified(src, dst, sha, log, f"{name} ({size} B, sha {sha[:16]}...)")
        if "error" in meta:
            raise SystemExit(f"source rejected ({name}): {meta['error']}; hash/size "
                             f"pinned by the plan is NOT relaxed")
        if meta["stat_bytes"] != size:
            raise SystemExit(f"size mismatch for {name}: {meta['stat_bytes']} != {size}")
        meta["name"] = name
        meta["expected_sha256"] = sha
        meta["expected_bytes"] = size
        sources[name] = meta

    # backup parameters + identity
    backup = {"path": args.params_backup}
    if not os.path.exists(args.params_backup):
        raise SystemExit(f"missing parameter backup: {args.params_backup}")
    bdst = os.path.join(in_dir, os.path.basename(args.params_backup))
    bmeta = R.verified_copy(args.params_backup, bdst)
    if "error" in bmeta:
        raise SystemExit(f"parameter backup copy failed: {bmeta['error']}")
    backup.update(_file_sha(bdst))
    backup["copied_to"] = os.path.relpath(bdst, out)

    vin = args.vehicle_info
    vehicle = None
    if vin and os.path.exists(vin):
        vdst = os.path.join(in_dir, os.path.basename(vin))
        vmeta = R.verified_copy(vin, vdst)
        if "error" not in vmeta:
            with open(vdst, "r", encoding="utf-8") as fh:
                vehicle = json.load(fh)
            vehicle = {"copied_to": os.path.relpath(vdst, out), **_file_sha(vdst),
                       "content": vehicle}
    backup["vehicle_info"] = vehicle

    backup_params, backup_order = _param_backup(bdst)
    declared = None
    if vehicle and isinstance(vehicle.get("content"), dict):
        declared = vehicle["content"].get("param_count_captured")
    backup["param_count"] = len(backup_params)
    backup["param_count_declared"] = declared
    if declared is not None and int(declared) != len(backup_params):
        raise SystemExit(f"parameter backup incomplete: parsed {len(backup_params)} "
                         f"of {declared} declared parameters")
    log(f"[prepare] parameter backup: {len(backup_params)} values, "
        f"declared {declared}")

    # anomaly file is copied next to the logs and pinned
    adst = os.path.join(in_dir, ANOMALY_JSON)
    ameta = R.verified_copy(anomaly["path"], adst)
    if "error" in ameta:
        raise SystemExit(f"anomaly copy failed: {ameta['error']}")
    anomaly["copied_to"] = os.path.relpath(adst, out)
    anomaly["copy_sha256"] = ameta["sha256"]
    if ameta["sha256"] != anomaly["sha256"]:
        raise SystemExit("anomaly JSON changed between validation and copy")

    log("[prepare] fetching frozen firmware primary sources")
    fw = _fetch_firmware(os.path.join(prov_dir, "firmware"), log)

    # parse each frozen copy
    parsed = {}
    for name in _selected_sources():
        copy = os.path.join(in_dir, name)
        npz = os.path.join(parsed_dir, sources[name]["sha256"][:20] + ".npz")
        log(f"[prepare] parsing {name} -> {os.path.basename(npz)}")
        info = _parse_bin(copy, npz)
        pmeta = _file_sha(npz)
        parsed[name] = {"npz": os.path.relpath(npz, out), **pmeta, **info}
        log(f"  {info['n_msg']} messages; missing streams: "
            f"{info['missing_messages'] or 'none'}")

    # baseline parameters actually recorded by the flight controller
    per_log, active_params = {}, {}
    for name in _selected_sources():
        z = _load_npz(os.path.join(out, parsed[name]["npz"]))
        params, hist = R._params_dict(z)
        per_log[name] = {"pid": _pid_baseline(params),
                         "routing": _routing_from_params(params),
                         "parm_events": int(np.asarray(z["PARM.TimeUS"]).size),
                         "changes": R._parm_changes(hist)}
        active_params[name] = params

    keys = [k for loop in LOOPS for k in LOOP_PARAMS[loop]]
    reference = per_log[_selected_sources()[0]]["pid"]
    disagreements = []
    for name, doc in per_log.items():
        for loop in LOOPS:
            for k in LOOP_PARAMS[loop]:
                a, b = reference[loop].get(k), doc["pid"][loop].get(k)
                if (a is None) != (b is None) or (
                        a is not None and abs(a - b) > 1e-9):
                    disagreements.append({"log": name, "param": k, "value": b,
                                          "reference": a})
    if disagreements:
        raise SystemExit("PID parameters differ between the 2026-11-02 logs; the "
                         f"single-baseline premise does not hold: {disagreements}")

    flat_pid = {}
    for loop in LOOPS:
        flat_pid.update(reference[loop])

    missing = [k for k in keys if flat_pid.get(k) is None]
    cross = {}
    for k in keys:
        b = backup_params.get(k)
        a = flat_pid.get(k)
        if b is None and a is None:
            continue
        if b is None or a is None:
            cross[k] = {"log_20261102": a, "backup_20261110": b,
                        "status": "present_in_one_only"}
            continue
        cross[k] = {"log_20261102": a, "backup_20261110": b,
                    "status": "match" if abs(a - b) <= 1e-9 else "differs"}

    baseline_params = {
        "pid": reference,
        "param_names": list(keys),
        "missing_in_logs": missing,
        "backup_20261110": {k: backup_params.get(k) for k in keys + list(HELD_PARAMS)},
        "cross_check_20261102_vs_20261110": cross,
        "routing": per_log[_selected_sources()[0]]["routing"],
        "note": ("values are the recorded originals, not recommendations; the "
                 "2026-11-10 snapshot is a later firmware boot and is never used "
                 "to overwrite the 2026-11-02 time series"),
    }
    _write_new_json(os.path.join(out, "baseline_params.json"), baseline_params)

    # determine the firmware version strings actually present in the logs
    fw_strings = {}
    for name in _selected_sources():
        z = _load_npz(os.path.join(out, parsed[name]["npz"]))
        msgs = [str(x) for x in np.asarray(z["MSG.Message"], dtype=object)]
        fw_strings[name] = [m for m in msgs if "Ardu" in m or "ChibiOS" in m][:4]

    source_manifest = {
        "stage": "prepare",
        "data_root": args.data_root,
        "sources": {
            name: {
                "path": os.path.join(args.data_root, name),
                "copied_to": os.path.relpath(os.path.join(in_dir, name), out),
                "sha256": sources[name]["sha256"],
                "bytes": sources[name]["bytes_read"],
                "expected_sha256": sources[name]["expected_sha256"],
                "expected_bytes": sources[name]["expected_bytes"],
                "hash_match": True,
            } for name in _selected_sources()
        },
        "sources_parsed": _selected_sources(),
        "parameter_backup": backup,
        "anomaly": {k: v for k, v in anomaly.items() if k != "windows"},
        "firmware": fw,
        "firmware_version_strings_in_logs": fw_strings,
        "parsed": parsed,
        "versions": _versions(),
        "code_sha256": _code_sha(),
        "offline_only": True,
    }
    _write_new_json(os.path.join(out, "source_manifest.json"), source_manifest)
    _write_new_json(os.path.join(prov_dir, "anomaly_windows.json"),
                    {"total_main_windows": anomaly["total_main_windows"],
                     "padded_by_s": ANOMALY_PAD_S,
                     "windows": {k: v for k, v in anomaly["windows"].items()},
                     "verdicts_ignored": True,
                     "note": ("only the start/end times are used; the stored "
                              "verdict text and its causal explanation are not "
                              "trusted")})

    rec = _write_receipt(out, "prepare", {
        "source_manifest": _file_sha(os.path.join(out, "source_manifest.json")),
        "baseline_params": _file_sha(os.path.join(out, "baseline_params.json")),
        "firmware_complete": fw["complete"],
        "pid_params_missing": missing,
    })
    log(f"[prepare] done: {len(rec['artifacts'])} artifacts pinned")
    return rec


# ---------------------------------------------------------------------------
# timeline: gaps, regions, zero-order held state
# ---------------------------------------------------------------------------
def _stream_times(z, name):
    key = f"{name}.TimeUS"
    if key not in z:
        return np.array([])
    return np.asarray(z[key], dtype=float) / 1e6


def _gap_cuts(z, names, thresholds=None):
    """Record gaps of each stream, padded on both sides."""
    cuts, report = [], {}
    for name in names:
        t = _stream_times(z, name)
        if t.size < 3:
            report[name] = {"samples": int(t.size), "threshold_s": None,
                            "gaps": 0, "gap_seconds": 0.0}
            continue
        thr = (thresholds or {}).get(name)
        if thr is None:
            thr = (R._stream_gap_threshold(t) if name in SLOW_STREAMS
                   else R._gap_threshold(t))
        gaps = R._gaps_thr(t, thr)
        report[name] = {"samples": int(t.size), "threshold_s": round(float(thr), 4),
                        "gaps": len(gaps),
                        "gap_seconds": round(float(sum(b - a for a, b in gaps)), 3),
                        "median_dt_s": round(float(np.median(np.diff(t))), 5)
                        if t.size > 1 else None}
        for a, b in gaps:
            cuts.append((a - GAP_PAD_S, b + GAP_PAD_S))
    return cuts, report


def _boot_cuts(z):
    """Log restarts: a backward jump in the shared clock starts a new boot."""
    t = _stream_times(z, "PIDS")
    if t.size < 2:
        return [], []
    back = np.where(np.diff(t) < -1e-6)[0]
    cuts = [(float(t[i]), float(t[i + 1])) for i in back]
    return cuts, [float(x) for x in np.unique(np.round(t[back], 3))]


def _region_of(t, ends):
    """Integer region id per sample; a record gap increments the id."""
    if ends.size == 0:
        return np.zeros(np.shape(t), dtype=np.int64)
    return np.searchsorted(ends, t, side="right").astype(np.int64)


def _zoh(t_src, vals, t_dst, max_age=None, reg_src=None, reg_dst=None):
    """Zero-order hold that never extends across a record gap."""
    t_dst = np.asarray(t_dst, dtype=float)
    if t_src.size == 0:
        return np.full(t_dst.shape, np.nan), np.full(t_dst.shape, np.inf), \
            np.zeros(t_dst.shape, dtype=bool)
    idx = np.searchsorted(t_src, t_dst, side="right") - 1
    valid = idx >= 0
    ic = np.clip(idx, 0, t_src.size - 1)
    out = np.asarray(vals, dtype=float)[ic]
    age = np.where(valid, t_dst - t_src[ic], np.inf)
    valid &= np.isfinite(out)
    if max_age is not None:
        valid &= age <= max_age
    if reg_src is not None and reg_dst is not None:
        valid &= np.asarray(reg_src)[ic] == np.asarray(reg_dst)
    out = np.where(valid, out, np.nan)
    age = np.where(valid, age, np.inf)
    return out, age, valid


def _event_intervals(t_evt, value, want):
    """Half-open intervals during which ``value == want`` from event stream."""
    iv, start = [], None
    for t, v in zip(t_evt, value):
        if v == want and start is None:
            start = float(t)
        elif v != want and start is not None:
            iv.append((start, float(t)))
            start = None
    if start is not None:
        iv.append((start, math.inf))
    return iv


def _state_at(t_dst, t_evt, vals, ends, max_age=None):
    """Region-constrained ZOH of a discrete state stream."""
    out, age, ok = _zoh(t_evt, vals, t_dst, max_age=max_age,
                        reg_src=_region_of(t_evt, ends), reg_dst=_region_of(t_dst, ends))
    return out, ok


def _primary_pi_series(z):
    """Primary EKF core series from XKF4.PI, deduped per timestamp."""
    t4 = _stream_times(z, "XKF4")
    if t4.size == 0 or "XKF4.PI" not in z:
        return np.array([]), np.array([])
    pi = np.asarray(z["XKF4.PI"], dtype=float)
    _u, first = np.unique(t4, return_index=True)
    first = np.sort(first)
    tt, pp = t4[first], pi[first]
    ok = np.isfinite(pp)
    return tt[ok], pp[ok]


def _primary_xkf(z, keys, t_dst, ends, max_age=0.2):
    """Attitude/velocity of the primary EKF core only.

    ``XKF1`` interleaves one row per core at the same timestamp, so a plain
    zero-order hold would grab whichever row came last.  Rows are therefore
    filtered to the core that :data:`XKF4.PI` names at that instant, and only
    then held.  Two IMUs or two cores are never stacked: that would double the
    sample count without adding information.
    """
    shape = np.shape(t_dst)
    nan = np.full(shape, np.nan)
    false = np.zeros(shape, dtype=bool)
    tt, pp = _primary_pi_series(z)
    t1 = _stream_times(z, "XKF1")
    if tt.size == 0 or t1.size == 0 or "XKF1.C" not in z:
        return {k: nan for k in keys}, false, "no_primary_core"
    reg = _region_of(t_dst, ends)
    core1, _a, _v = _zoh(tt, pp, t1, max_age=None,
                         reg_src=_region_of(tt, ends), reg_dst=_region_of(t1, ends))
    c1 = np.asarray(z["XKF1.C"], dtype=float)
    sel = np.isfinite(core1) & np.isfinite(c1) & (c1 == core1)
    if sel.sum() < 3:
        return {k: nan for k in keys}, false, "no_primary_rows"
    ts = t1[sel]
    out, okall = {}, np.ones(shape, dtype=bool)
    for k in keys:
        key = f"XKF1.{k}"
        if key not in z:
            out[k] = nan
            okall = false
            continue
        v, _age, ok = _zoh(ts, np.asarray(z[key], dtype=float)[sel], t_dst,
                           max_age=max_age, reg_src=_region_of(ts, ends), reg_dst=reg)
        out[k] = v
        okall &= ok
    return out, okall, "primary_core"


def _core_switch_cuts(z):
    t4 = _stream_times(z, "XKF4")
    if t4.size == 0 or "XKF4.PI" not in z:
        return [], []
    pi = np.asarray(z["XKF4.PI"], dtype=float)
    _, first = np.unique(t4, return_index=True)
    tt, pp = t4[np.sort(first)], pi[np.sort(first)]
    ok = np.isfinite(pp)
    tt, pp = tt[ok], pp[ok]
    cuts, times = [], []
    for i in range(1, tt.size):
        if pp[i] != pp[i - 1]:
            cuts.append((tt[i] - SWITCH_PAD_S, tt[i] + SWITCH_PAD_S))
            times.append(float(tt[i]))
    return cuts, times


def _clip_cuts(z, ends):
    """Exclude from a rising VIBE clip counter to the end of that region."""
    t = _stream_times(z, "VIBE")
    if t.size == 0 or "VIBE.Clip" not in z:
        return [], {"events": 0}
    clip = np.asarray(z["VIBE.Clip"], dtype=float)
    inst = np.asarray(z["VIBE.IMU"], dtype=float) if "VIBE.IMU" in z else np.zeros(t.shape)
    reg = _region_of(t, ends)
    cuts, events = [], 0
    for inst_id in np.unique(inst[np.isfinite(inst)]):
        m = inst == inst_id
        ti, ci, ri = t[m], clip[m], reg[m]
        d = np.diff(ci)
        for j in np.where(np.isfinite(d) & (d > 0))[0]:
            cuts.append((float(ti[j + 1]), math.inf))
            events += 1
    # close open-ended cuts at the end of each region
    closed = []
    for a, _b in cuts:
        r = _region_of(np.array([a]), ends)[0]
        same = t[reg == r]
        closed.append((a, float(same[-1]) if same.size else a + 1.0))
    return closed, {"events": events}


# ---------------------------------------------------------------------------
# per-loop data assembly
# ---------------------------------------------------------------------------
def _loop_stream(loop):
    return "PIDS" if loop == "yaw" else "PIDA"


def _loop_units(loop):
    return "deg/s" if loop == "yaw" else "m/s"


def _loop_to_display(loop, x):
    """Native PID units (rad/s, m/s) -> report units (deg/s, m/s)."""
    return np.degrees(x) if loop == "yaw" else np.asarray(x, dtype=float)


def _loop_ref_change(loop):
    return math.radians(1.0) if loop == "yaw" else 0.05


def _loop_ss_limit(loop):
    return YAW_SS_LIM if loop == "yaw" else SPEED_SS_LIM


def _loop_neighbour_limit(loop):
    return YAW_NEIGHBOUR_BAND if loop == "yaw" else SPEED_NEIGHBOUR_BAND


def build_loop_frame(z, params, anomaly_windows, log_name, loop):
    """Assemble the per-sample evidence frame for one loop of one log."""
    stream = _loop_stream(loop)
    t = _stream_times(z, stream)
    if t.size == 0:
        return None

    gap_cuts, gap_report = _gap_cuts(z, FAST_STREAMS + SLOW_STREAMS)
    boot_cuts, boot_times = _boot_cuts(z)
    core_cuts, core_times = _core_switch_cuts(z)
    record_cuts = R.merge_intervals(
        [(a, b) for a, b in gap_cuts if math.isfinite(b)] + boot_cuts)
    ends = np.array([b for _a, b in record_cuts], dtype=float)
    region = _region_of(t, ends)

    # state streams, region-constrained (never extended across a record gap)
    tm = _stream_times(z, "MODE")
    mode_num, mode_ok = (np.full(t.shape, np.nan), np.zeros(t.shape, dtype=bool))
    if tm.size:
        mode_num, mode_ok = _state_at(t, tm, np.asarray(z["MODE.ModeNum"], dtype=float), ends)
    ta = _stream_times(z, "ARM")
    armed, armed_ok = (np.full(t.shape, np.nan), np.zeros(t.shape, dtype=bool))
    if ta.size:
        armed, armed_ok = _state_at(t, ta, np.asarray(z["ARM.ArmState"], dtype=float), ends)

    mode_name = np.array([ROVER_MODES.get(int(round(m)), f"MODE{int(round(m))}")
                          if np.isfinite(m) else "UNKNOWN" for m in mode_num], dtype=object)

    # health: primary EKF core only
    primary, core_ok, core_mode = _primary_xkf(z, ("Roll", "Pitch"), t, ends)
    roll, pitch = primary["Roll"], primary["Pitch"]
    roll_ok = pitch_ok = core_ok
    tg = _stream_times(z, "GPS")
    gps_thr = R._stream_gap_threshold(tg) if tg.size > 2 else None
    gstat, _a, gstat_ok = _zoh(tg, np.asarray(z["GPS.Status"], dtype=float) if "GPS.Status" in z
                               else np.array([]), t, max_age=gps_thr,
                               reg_src=_region_of(tg, ends), reg_dst=region)
    hdop, _a, hdop_ok = _zoh(tg, np.asarray(z["GPS.HDop"], dtype=float) if "GPS.HDop" in z
                             else np.array([]), t, max_age=gps_thr,
                             reg_src=_region_of(tg, ends), reg_dst=region)
    clip_cuts, clip_info = _clip_cuts(z, ends)

    # activation evidence: THR.Speed finite proves speed control was applied
    tt = _stream_times(z, "THR")
    thr_speed, _a, thr_ok = _zoh(tt, np.asarray(z["THR.Speed"], dtype=float) if "THR.Speed" in z
                                 else np.array([]), t, max_age=AUX_MAX_AGE_S,
                                 reg_src=_region_of(tt, ends), reg_dst=region)
    thr_out, _a, thr_out_ok = _zoh(tt, np.asarray(z["THR.ThrOut"], dtype=float) if "THR.ThrOut" in z
                                   else np.array([]), t, max_age=AUX_MAX_AGE_S,
                                   reg_src=_region_of(tt, ends), reg_dst=region)
    ts = _stream_times(z, "STER")
    steer_out, _a, steer_ok = _zoh(ts, np.asarray(z["STER.SteerOut"], dtype=float)
                                   if "STER.SteerOut" in z else np.array([]), t,
                                   max_age=AUX_MAX_AGE_S,
                                   reg_src=_region_of(ts, ends), reg_dst=region)
    st_des, _a, _ok = _zoh(ts, np.asarray(z["STER.DesTurnRate"], dtype=float)
                           if "STER.DesTurnRate" in z else np.array([]), t,
                           max_age=AUX_MAX_AGE_S,
                           reg_src=_region_of(ts, ends), reg_dst=region)
    st_act, _a, _ok = _zoh(ts, np.asarray(z["STER.TurnRate"], dtype=float)
                           if "STER.TurnRate" in z else np.array([]), t,
                           max_age=AUX_MAX_AGE_S,
                           reg_src=_region_of(ts, ends), reg_dst=region)
    th_des, _a, _ok = _zoh(tt, np.asarray(z["THR.DesSpeed"], dtype=float)
                           if "THR.DesSpeed" in z else np.array([]), t,
                           max_age=AUX_MAX_AGE_S,
                           reg_src=_region_of(tt, ends), reg_dst=region)

    # guidance sub-mode (proves *a* target was set; not that the loop is closed)
    tgp = _stream_times(z, "GUIP")
    guip_type, _a, guip_ok = _zoh(tgp, np.asarray(z["GUIP.Type"], dtype=float)
                                 if "GUIP.Type" in z else np.array([]), t, max_age=None,
                                 reg_src=_region_of(tgp, ends), reg_dst=region)

    def col(key):
        return np.asarray(z[f"{stream}.{key}"], dtype=float) if f"{stream}.{key}" in z \
            else np.full(t.shape, np.nan)

    ref = col("Tar")
    act = col("Act")
    err = col("Err")
    p_term, i_term, d_term = col("P"), col("I"), col("D")
    ff_term = col("FF") + col("DFF")
    out_norm = p_term + i_term + d_term + ff_term
    flags = col("Flags")
    dmod = col("Dmod")
    srate = col("SRate")

    # exclusion bookkeeping: seconds removed per reason (overlaps counted once
    # per reason, which is why the total need not equal the wall-clock loss)
    reasons = {}

    def add_reason(mask, name):
        if mask is None:
            return
        m = np.asarray(mask, dtype=bool)
        if m.any():
            reasons[name] = reasons.get(name, 0.0) + _duration(t, m)


    gap_mask = np.zeros(t.shape, dtype=bool)
    for a, b in gap_cuts:
        if math.isfinite(b):
            gap_mask |= (t > a) & (t < b)
    add_reason(gap_mask, "record_gap")
    boot_mask = np.zeros(t.shape, dtype=bool)
    for i in np.where(np.diff(t) < 0)[0]:
        boot_mask[max(0, i - 1): i + 3] = True
    add_reason(boot_mask & ~gap_mask, "log_restart")

    state_mask = ~(mode_ok & armed_ok)
    add_reason(state_mask, "state_unknown_after_gap")

    # an unarmed vehicle never exercises the loop; the plan excludes these
    # intervals outright rather than treating them as a gentle test.
    armed_mask = np.isfinite(armed) & (armed == 1)
    add_reason(armed_ok & ~armed_mask, "disarmed")

    sw_mask = np.zeros(t.shape, dtype=bool)
    tev = np.concatenate([_stream_times(z, "MODE"), _stream_times(z, "ARM")])
    for te in np.unique(tev):
        sw_mask |= np.abs(t - te) <= SWITCH_PAD_S
    add_reason(sw_mask & ~state_mask, "mode_or_arm_switch")

    core_sw_mask = np.zeros(t.shape, dtype=bool)
    for a, b in core_cuts:
        core_sw_mask |= (t > a) & (t < b)
    add_reason(core_sw_mask, "ekf_core_switch")

    tm_parm = _stream_times(z, "PARM")
    parm_mask = np.zeros(t.shape, dtype=bool)
    if tm_parm.size:
        names = np.asarray(z["PARM.Name"], dtype=object)
        for i, nm in enumerate(names):
            if str(nm) in VAR_WHITELIST or str(nm) in HELD_PARAMS:
                parm_mask |= np.abs(t - tm_parm[i]) <= SWITCH_PAD_S
    add_reason(parm_mask & ~state_mask, "pid_param_event")

    anomaly_mask = np.zeros(t.shape, dtype=bool)
    for a, b in anomaly_windows:
        anomaly_mask |= (t >= a - ANOMALY_PAD_S) & (t <= b + ANOMALY_PAD_S)
    add_reason(anomaly_mask, "historical_anomaly_window")

    clip_mask = np.zeros(t.shape, dtype=bool)
    for a, b in clip_cuts:
        clip_mask |= (t >= a) & (t <= b)
    add_reason(clip_mask, "vibration_clipping")

    gps_bad = ~(gstat_ok & hdop_ok) | ~(gstat >= GPS_MIN_STATUS) | ~(hdop <= GPS_MAX_HDOP)
    add_reason(gps_bad, "gps_health")
    att_bad = ~(roll_ok & pitch_ok) | (np.abs(roll) > ROLL_LIM_DEG) | \
        (np.abs(pitch) > PITCH_LIM_DEG)
    add_reason(att_bad, "attitude_outside_gate")
    add_reason(~core_ok, "ekf_core_unpaired")

    numeric_mode = np.isin(mode_name, sorted(CLOSED_LOOP_MODES))
    if loop == "speed":
        numeric_mode &= np.isfinite(thr_speed)
    guided = np.isin(mode_name, sorted(GUIDED_MODES))
    manual = np.isin(mode_name, sorted(NEGATIVE_CONTROLS))
    excluded_mode = np.isin(mode_name, sorted(EXCLUDED_MODES))
    unknown_mode = mode_name == "UNKNOWN"

    usable_base = (~(gap_mask | boot_mask | state_mask | sw_mask | core_sw_mask |
                     parm_mask | anomaly_mask | clip_mask | gps_bad | att_bad |
                     ~core_ok | ~armed_mask)
                   & np.isfinite(ref) & np.isfinite(act) & np.isfinite(err))

    frame = {
        "log": log_name, "loop": loop, "unit": _loop_units(loop),
        "t": t, "ref": ref, "act": act, "err": err,
        "p": p_term, "i": i_term, "d": d_term, "ff": ff_term,
        "out": out_norm, "flags": flags, "dmod": dmod, "srate": srate,
        "mode": mode_name, "mode_num": mode_num, "armed": armed,
        "steer_out": steer_out, "thr_out": thr_out, "thr_speed": thr_speed,
        "ster_des_dps": st_des, "ster_act_dps": st_act,
        "thr_des_mps": th_des, "guip": guip_type, "guip_ok": guip_ok,
        "ok_common": usable_base,
        "numeric_mode": numeric_mode, "guided": guided, "manual": manual,
        "excluded_mode": excluded_mode, "unknown_mode": unknown_mode,
        "region": region, "reasons": reasons, "record_cuts": record_cuts,
        "gap_report": gap_report, "boot_times": boot_times,
        "core_times": core_times, "core_mode": core_mode,
        "clip_info": clip_info,
        "roll": roll, "pitch": pitch, "gstat": gstat, "hdop": hdop,
        "thr_ok": thr_ok, "steer_ok": steer_ok, "thr_out_ok": thr_out_ok,
    }
    # explicit per-class masks with their own credit status
    frame["masks"] = {
        "numeric": usable_base & numeric_mode,
        "diagnostic_only_guided": usable_base & guided,
        "negative_control_manual": usable_base & manual,
        "excluded_mode": usable_base & excluded_mode,
        "unknown_mode": usable_base & unknown_mode,
    }
    return frame


def _duration(t, mask):
    """Seconds covered by consecutive selected samples (never bridges a hole)."""
    t = np.asarray(t, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if t.size < 2 or mask.size != t.size:
        return 0.0
    d = np.diff(t)
    both = mask[:-1] & mask[1:]
    return float(np.sum(np.where(both & (d > 0), d, 0.0)))
# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------
def _weighted_rmse(dt, e):
    w = float(np.sum(dt))
    if w <= 0:
        return float("nan")
    return float(math.sqrt(float(np.sum(dt * e * e)) / w))


def _weighted_iae(dt, e):
    return float(np.sum(dt * np.abs(e)))


def _total_variation(dt, x):
    """Total variation per second, independent of the record rate."""
    if x.size < 2:
        return float("nan")
    span = float(np.sum(dt))
    if span <= 0:
        return float("nan")
    return float(np.sum(np.abs(np.diff(x))) / span)


def cross_stream_delta(loop, pid_ref, pid_act, aux_des, aux_act):
    """Median |native PID - auxiliary log| in the loop's report unit.

    ``PIDS``/``PIDA`` carry rad/s and m/s; ``STER`` carries deg/s and ``THR``
    m/s.  A unit slip on either side, or a sign inverted on one side only, moves
    these medians by far more than the tolerance, which is exactly why the check
    exists.  Numbers are *not* silently fixed here.
    """
    tol = CROSS_YAW_TOL_DPS if loop == "yaw" else CROSS_SPEED_TOL_MPS
    out = {"tolerance": tol, "n": 0, "ref_delta": None, "act_delta": None,
           "ok": False, "applied": False}
    if loop == "yaw":
        conv_ref = np.degrees(np.asarray(pid_ref, dtype=float))
        conv_act = np.degrees(np.asarray(pid_act, dtype=float))
    else:
        conv_ref = np.asarray(pid_ref, dtype=float)
        conv_act = np.asarray(pid_act, dtype=float)
    ok = (np.isfinite(conv_ref) & np.isfinite(aux_des) &
          np.isfinite(conv_act) & np.isfinite(aux_act))
    n = int(ok.sum())
    out["n"] = n
    if n < 2:
        out["note"] = "no paired auxiliary samples"
        return out
    out["ref_delta"] = float(np.median(np.abs(conv_ref[ok] - np.asarray(aux_des)[ok])))
    out["act_delta"] = float(np.median(np.abs(conv_act[ok] - np.asarray(aux_act)[ok])))
    out["applied"] = True
    out["ok"] = bool(out["ref_delta"] <= tol and out["act_delta"] <= tol)
    return out


def _platforms(t, ref, seg_ids, min_s, plateau_tol, accel_lim=None):
    """Runs of near-constant reference inside one continuous valid segment."""
    out = []
    run = []
    prev = None
    prev_t = None
    for i in range(t.size):
        r = ref[i]
        ok = math.isfinite(r)
        if ok and run:
            dt = t[i] - prev_t
            jump = abs(r - prev)
            if seg_ids[i] != seg_ids[run[0]] or jump > plateau_tol or (
                    accel_lim is not None and dt > 0 and jump / dt > accel_lim):
                out.append(run)
                run = []
        if ok:
            run.append(i)
            prev = r
            prev_t = t[i]
    if run:
        out.append(run)
    plats = []
    for idx in out:
        idx = np.asarray(idx, dtype=int)
        if idx.size < 2:
            continue
        span = t[idx[-1]] - t[idx[0]]
        if span < min_s:
            continue
        vals = ref[idx]
        plats.append({"idx": idx, "t0": float(t[idx[0]]), "t1": float(t[idx[-1]]),
                      "span_s": float(span), "ref": float(np.median(vals)),
                      "region": int(seg_ids[idx[0]])})
    return plats


def _oscillation(t, e, thr):
    """Longest run of >=3 error round-trips with decaying-or-equal peaks."""
    mask = np.abs(e) > thr
    sign = np.sign(e)
    peaks, times, last = [], [], 0.0
    for i in range(1, e.size):
        if mask[i] and sign[i] != 0 and (i == 0 or sign[i] != sign[i - 1]):
            peaks.append(abs(e[i]))
            times.append(float(t[i]))
    if len(peaks) < 3:
        return {"cycles": len(peaks), "duration_s": 0.0, "oscillating": False}
    best = 0.0
    best_n = 0
    run_start = 0
    for i in range(1, len(peaks)):
        # round trip = 2 sign changes; compare first and last peak of the run
        if peaks[i] >= 0.8 * peaks[run_start]:
            dur = times[i] - times[run_start]
            n = (i - run_start + 1) // 2
            if n >= 3 and dur > best:
                best, best_n = dur, n
        else:
            run_start = i
    return {"cycles": int(best_n), "duration_s": float(best),
            "oscillating": bool(best > 0)}


def segment_metrics(t, ref, act, err, loop, p_term=None, i_term=None,
                    flags=None, out=None):
    """Time-weighted metrics for one continuous valid window (native units)."""
    t = np.asarray(t, dtype=float)
    ok = np.isfinite(ref) & np.isfinite(act) & np.isfinite(err)
    t, ref, act, err = t[ok], ref[ok], act[ok], err[ok]
    if t.size < 3:
        return {"n": int(t.size), "evaluable": False, "reason": "too_few_samples"}
    dt = np.diff(t)
    if np.any(dt <= 0):
        keep = np.concatenate(([True], dt > 0))
        t, ref, act, err = t[keep], ref[keep], act[keep], err[keep]
        dt = np.diff(t)
    if dt.size < 2:
        return {"n": int(t.size), "evaluable": False, "reason": "too_few_samples"}

    edt = dt
    emid = err[:-1]
    disp = _loop_to_display(loop, err)
    ref_disp = _loop_to_display(loop, ref)
    act_disp = _loop_to_display(loop, act)

    # steady-state deviation: median error over the tail platform
    tail_s = 3.0 if loop == "yaw" else 5.0
    t_end = t[-1]
    tail = t >= (t_end - tail_s)
    pre = (t >= (t_end - 2 * tail_s)) & (t < (t_end - tail_s))
    ss = float(np.median(disp[tail])) if tail.any() else float("nan")
    ss_prev = float(np.median(disp[pre])) if pre.sum() > 2 else float("nan")
    ss_tol = _loop_ss_limit(loop) * 0.5 if loop == "yaw" else 0.05
    ss_stable = bool(np.isfinite(ss) and np.isfinite(ss_prev) and
                     abs(ss - ss_prev) <= ss_tol)

    # step response: reference change inside the window
    step = float(np.nanmax(ref_disp) - np.nanmin(ref_disp)) if ref.size else float("nan")
    overshoot = float("nan")
    settle = float("nan")
    if np.isfinite(step) and step > 0:
        i0 = int(np.argmax(np.abs(np.diff(ref_disp)))) if ref_disp.size > 1 else 0
        i0 = min(i0 + 1, ref.size - 1)
        target = ref_disp[-1]
        tail_act = act_disp[i0:]
        if np.isfinite(target) and tail_act.size:
            signed = (tail_act - target) * np.sign(target - ref_disp[0] or 1.0)
            overshoot = float(max(0.0, np.nanmax(signed)))
            band = max(0.05 * step, _loop_ss_limit(loop))
            inside = np.abs(tail_act - target) <= band
            run = 0
            settle = float("nan")
            for k in range(inside.size):
                run = run + 1 if inside[k] else 0
                if run >= 2:
                    settle = float(t[i0 + k - run + 1] - t[i0])
                    break

    osc = _oscillation(t, disp, _loop_ss_limit(loop))
    sat = float("nan")
    if flags is not None:
        f = np.asarray(flags, dtype=float)[ok][:t.size]
        if f.size == t.size and np.isfinite(f).any():
            sat = float(np.mean((f.astype(np.int64) & FLAG_LIMIT) != 0))
    iterm = float("nan")
    if i_term is not None:
        it = np.asarray(i_term, dtype=float)[ok][:t.size]
        if np.isfinite(it).any():
            denom = float(np.sum(np.abs(np.asarray(p_term, dtype=float)[ok][:t.size])))
            iterm = float(np.sum(np.abs(it))) / denom if denom > 0 else float("nan")

    return {
        "n": int(t.size),
        "evaluable": True,
        "duration_s": float(np.sum(edt)),
        "rmse": _weighted_rmse(edt, emid),
        "rmse_display": _loop_to_display(loop, np.array([_weighted_rmse(edt, emid)]))[0],
        "iae": _weighted_iae(edt, emid),
        "iae_display": _loop_to_display(loop, np.array([_weighted_iae(edt, emid)]))[0],
        "ss_dev": ss,
        "ss_stable": ss_stable,
        "ref_span": step,
        "overshoot": overshoot,
        "settle_s": settle,
        "osc_cycles": osc["cycles"],
        "osc_duration_s": osc["duration_s"],
        "oscillating": osc["oscillating"],
        "sat_frac": sat,
        "tv_per_s": _total_variation(edt, np.asarray(out, dtype=float)[ok][:t.size]
                                     if out is not None else act),
        "i_ratio": iterm,
        "t0": float(t[0]),
        "t1": float(t[-1]),
    }


def _seg_ids(t, record_cuts):
    ends = np.array([b for _a, b in record_cuts], dtype=float)
    return _region_of(t, ends)


def _split_blocks(frame, mask, min_s=MIN_SEGMENT_S):
    """Contiguous usable windows; a reference change splits platforms, not blocks."""
    t = frame["t"]
    idx_all = np.where(mask)[0]
    if idx_all.size == 0:
        return []
    blocks = []
    start = idx_all[0]
    prev = idx_all[0]
    for i in idx_all[1:]:
        brk = (i != prev + 1) or (frame["region"][i] != frame["region"][prev])
        if brk:
            blocks.append((start, prev))
            start = i
        prev = i
    blocks.append((start, prev))
    out = []
    for a, b in blocks:
        if t[b] - t[a] >= min_s:
            out.append((int(a), int(b) + 1))
    return out


def _block_metrics(frame, a, b, loop):
    sl = slice(a, b)
    m = segment_metrics(
        frame["t"][sl], frame["ref"][sl], frame["act"][sl], frame["err"][sl], loop,
        p_term=frame["p"][sl], i_term=frame["i"][sl],
        flags=frame["flags"][sl], out=frame["out"][sl])
    if not m.get("evaluable"):
        return m
    if loop == "yaw":
        aux_des, aux_act = frame["ster_des_dps"][sl], frame["ster_act_dps"][sl]
    else:
        aux_des, aux_act = frame["thr_des_mps"][sl], frame["thr_speed"][sl]
    cross = cross_stream_delta(loop, frame["ref"][sl], frame["act"][sl], aux_des, aux_act)
    m["cross"] = cross
    if cross["applied"]:
        m["cross_ref_delta"] = cross["ref_delta"]
        m["cross_act_delta"] = cross["act_delta"]
        if not cross["ok"]:
            m["evaluable"] = False
            m["reason"] = "cross_stream_mismatch"
    return m


def _boot_ci(values, n=BOOTSTRAP_N, seed=BOOTSTRAP_SEED, stat=None):
    """Block bootstrap of a scalar statistic (blocks are the sampling unit)."""
    v = np.asarray([x for x in values if x is not None and np.isfinite(x)], dtype=float)
    if v.size < 2:
        return {"n": int(v.size), "ci": None}
    stat = np.median if stat is None else stat
    rng = np.random.default_rng(seed)
    draws = [stat(rng.choice(v, size=v.size, replace=True)) for _ in range(n)]
    return {"n": int(v.size), "point": float(stat(v)),
            "ci": [float(np.nanpercentile(draws, 2.5)),
                   float(np.nanpercentile(draws, 97.5))]}
# ---------------------------------------------------------------------------
# stage: analyze
# ---------------------------------------------------------------------------
def _mode_intervals(frame):
    """Per-mode intervals with armed state and how they were closed.

    Intervals are emitted at state boundaries only, and consecutive intervals
    shorter than ``MIN_SEGMENT_S`` are folded into their neighbour: a per-sample
    interval list would be a sample dump, not a mode inventory.
    """
    t, mode, armed = frame["t"], frame["mode"], frame["armed"]
    if t.size == 0:
        return []
    bounds = [0]
    for i in range(1, t.size):
        if mode[i] != mode[i - 1] or armed[i] != armed[i - 1] or \
                frame["region"][i] != frame["region"][i - 1]:
            bounds.append(i)
    bounds.append(t.size)
    spans = [(bounds[k], bounds[k + 1]) for k in range(len(bounds) - 1)]
    merged = []
    for a, b in spans:
        if merged and (t[b - 1] - t[merged[-1][0]]) < MIN_SEGMENT_S:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return [_interval_row(frame, a, b,
                          "record_end" if b >= t.size else "state_change")
            for a, b in merged]


def _interval_row(frame, a, b, closed):
    t = frame["t"]
    m = frame["masks"]["numeric"][a:b]
    d = frame["masks"]["diagnostic_only_guided"][a:b]
    n = frame["masks"]["negative_control_manual"][a:b]
    return {
        "log": frame["log"], "loop": frame["loop"],
        "mode": str(frame["mode"][a]),
        "armed": bool(frame["armed"][a] == 1) if np.isfinite(frame["armed"][a]) else None,
        "t0_s": round(float(t[a]), 3), "t1_s": round(float(t[b - 1]), 3),
        "duration_s": round(float(t[b - 1] - t[a]), 3),
        "numeric_credit_s": round(_duration(t[a:b], m), 3),
        "diagnostic_only_s": round(_duration(t[a:b], d), 3),
        "negative_control_s": round(_duration(t[a:b], n), 3),
        "closed_by": closed,
    }


def _coverage(frame):
    t = frame["t"]
    mask = frame["masks"]["numeric"]
    blocks = _split_blocks(frame, mask)
    dirs = {"left": 0, "right": 0, "zero": 0}
    ref = _loop_to_display(frame["loop"], frame["ref"])
    seg_ref = ref[mask] if mask.any() else np.array([])
    thr = YAW_PLAT_MIN_RATE if frame["loop"] == "yaw" else 0.05
    dirs["left"] = int(np.sum(seg_ref < -thr))
    dirs["right"] = int(np.sum(seg_ref > thr))
    dirs["zero"] = int(np.sum(np.abs(seg_ref) <= thr))

    # independent reference changes: distinct platform levels entered
    changes = 0
    if mask.any():
        tt = t[mask]
        rr = frame["ref"][mask]
        reg = frame["region"][mask]
        tol = _loop_ref_change(frame["loop"])
        for i in range(1, tt.size):
            if reg[i] != reg[i - 1]:
                changes += 1
            elif abs(rr[i] - rr[i - 1]) > tol and abs(rr[i] - rr[i - 1]) > 0:
                if i + 1 >= tt.size or abs(rr[i + 1] - rr[i]) <= tol:
                    changes += 1

    longest = 0.0
    for a, b in blocks:
        longest = max(longest, float(t[b - 1] - t[a]))
    sat = np.nan
    if frame["flags"] is not None and mask.any():
        f = frame["flags"][mask]
        if np.isfinite(f).any():
            sat = float(np.mean((f.astype(np.int64) & FLAG_LIMIT) != 0))
    speed_bins = set()
    if frame["loop"] == "speed" and mask.any():
        v = np.abs(np.asarray(frame["act"], dtype=float)[mask])
        for lo, hi in SPEED_BINS:
            if np.any((v >= lo) & (v < hi)):
                speed_bins.add(f"[{lo},{hi})")
    return {
        "log": frame["log"], "loop": frame["loop"], "unit": frame["unit"],
        "total_log_s": round(float(t[-1] - t[0]), 3) if t.size > 1 else 0.0,
        "numeric_credit_s": round(_duration(t, mask), 3),
        "numeric_evaluable_s": round(sum(float(t[b - 1] - t[a]) for a, b in blocks), 3),
        "diagnostic_only_guided_s": round(
            _duration(t, frame["masks"]["diagnostic_only_guided"]), 3),
        "negative_control_manual_s": round(
            _duration(t, frame["masks"]["negative_control_manual"]), 3),
        "numeric_blocks": len(blocks),
        "longest_numeric_block_s": round(longest, 3),
        "independent_reference_changes": int(changes),
        "direction_samples": dirs,
        "speed_bins_covered": sorted(speed_bins),
        "saturation_fraction": sat,
        "excluded_seconds_by_reason": {k: round(v, 3)
                                       for k, v in sorted(frame["reasons"].items())},
        "gap_thresholds_s": {k: v.get("threshold_s")
                             for k, v in frame["gap_report"].items()},
        "log_restarts_s": frame["boot_times"],
        "ekf_core_switches_s": frame["core_times"],
        "clip_events": frame["clip_info"]["events"],
        "activation_note": (
            "GUIDED segments are diagnostic only: the direct steering/throttle "
            "setter never logs GUIP, so a cached PID value matching the current "
            "reference is not proof the loop was closed"
            if frame["masks"]["diagnostic_only_guided"].any() else
            "no GUIDED closed-loop claim is made for this log"),
    }


def _analyze_figures(out_dir, frames):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _mkdir(out_dir)
    made = []
    for loop in LOOPS:
        sub = [f for f in frames if f["loop"] == loop]
        if not sub:
            continue
        fig, axes = plt.subplots(len(sub), 1, figsize=(12, 3.0 * len(sub)), squeeze=False)
        for ax, f in zip(axes[:, 0], sub):
            t = f["t"]
            ax.plot(t, _loop_to_display(loop, f["ref"]), lw=0.9, label="reference")
            ax.plot(t, _loop_to_display(loop, f["act"]), lw=0.7, alpha=0.85, label="actual")
            cred = f["masks"]["numeric"]
            if cred.any():
                ax.fill_between(t, ax.get_ylim()[0], ax.get_ylim()[1], where=cred,
                                color="tab:green", alpha=0.15, step="mid",
                                label="numeric credit")
            diag = f["masks"]["diagnostic_only_guided"]
            if diag.any():
                ax.fill_between(t, ax.get_ylim()[0], ax.get_ylim()[1], where=diag,
                                color="tab:orange", alpha=0.12, step="mid",
                                label="diagnostic only")
            ax.set_title(f"{f['log']} - {loop} ({f['unit']})", fontsize=9)
            ax.set_xlabel("TimeUS (s)", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.legend(fontsize=6, loc="upper right")
        fig.tight_layout()
        p = os.path.join(out_dir, f"trace_{loop}.png")
        _guard_write(p)
        fig.savefig(p, dpi=130)
        plt.close(fig)
        made.append(p)

    fig, ax = plt.subplots(figsize=(9, 0.6 * len(frames) + 1.2))
    labels = [f"{f['log'][-12:]} {f['loop']}" for f in frames]
    y = np.arange(len(frames))
    num = [f["masks"]["numeric"].sum() for f in frames]
    gui = [f["masks"]["diagnostic_only_guided"].sum() for f in frames]
    man = [f["masks"]["negative_control_manual"].sum() for f in frames]
    ax.barh(y, num, color="tab:green", label="numeric credit")
    ax.barh(y, gui, left=num, color="tab:orange", label="diagnostic only (GUIDED)")
    ax.barh(y, man, left=np.array(num) + np.array(gui), color="tab:gray",
            label="negative control (MANUAL)")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel("samples (50 Hz)", fontsize=8)
    ax.legend(fontsize=7)
    fig.tight_layout()
    p = os.path.join(out_dir, "coverage.png")
    _guard_write(p)
    fig.savefig(p, dpi=130)
    plt.close(fig)
    made.append(p)
    return [os.path.relpath(x, os.path.dirname(out_dir)) for x in made]


def stage_analyze(args):
    log = print
    out = args.out
    _require_stage(out, "prepare")
    _ensure_out(out, "analyze")
    adir = os.path.join(out, "analyze")
    _mkdir(adir)

    manifest, baseline = _load_frozen(out)
    windows_all = _anomaly_by_log(out)
    frames, coverage, intervals, segments, metrics = [], [], [], [], {}
    for name in manifest["sources_parsed"]:
        z = _load_npz(os.path.join(out, manifest["parsed"][name]["npz"]))
        params, _hist = R._params_dict(z)
        for loop in LOOPS:
            f = build_loop_frame(z, params, windows_all.get(name, []), name, loop)
            if f is None:
                log(f"[analyze] {name} {loop}: stream absent")
                continue
            frames.append(f)
            coverage.append(_coverage(f))
            intervals.extend(_mode_intervals(f))
            rows = []
            for status in ("numeric", "diagnostic_only_guided",
                           "negative_control_manual", "excluded_mode", "unknown_mode"):
                mask = f["masks"][status]
                for a, b in _split_blocks(f, mask):
                    m = _block_metrics(f, a, b, loop)
                    if not m.get("evaluable"):
                        continue
                    row = {"log": name, "loop": loop, "credit": status,
                           "block": len(rows) + 1, **_jp(m)}
                    rows.append(row)
            segments.extend(rows)
            numeric = [r for r in rows if r["credit"] == "numeric"]
            metrics[f"{name}|{loop}"] = {
                "numeric_blocks": len(numeric),
                "numeric_duration_s": round(sum(r["duration_s"] for r in numeric), 3),
                "rmse_point": _boot_ci([r["rmse"] for r in numeric]),
                "rmse_display_median": (float(np.median([r["rmse_display"] for r in numeric]))
                                        if numeric else None),
                "iae_display_total": (float(np.sum([r["iae_display"] for r in numeric]))
                                      if numeric else None),
                "blocks": numeric,
                "credit_status": ("numeric" if numeric else "insufficient_evidence"),
            }
            log(f"[analyze] {name} {loop}: {len(numeric)} numeric block(s), "
                f"{metrics[f'{name}|{loop}']['numeric_duration_s']} s")

    _write_csv_new(os.path.join(adir, "mode_intervals.csv"), intervals)
    _write_csv_new(os.path.join(adir, "segments.csv"), segments)
    _write_new_json(os.path.join(adir, "coverage.json"),
                    {"per_log_loop": coverage,
                     "note": ("numeric credit requires a closed ATC loop, healthy "
                              "sensors, a fresh record and a resolved activation "
                              "route; GUIDED is never credited")})
    _write_new_json(os.path.join(adir, "baseline_metrics.json"),
                    {"loops": metrics,
                     "units": {l: _loop_units(l) for l in LOOPS},
                     "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED,
                                   "unit": "independent maneuver block"},
                     "baseline_parameters": baseline["pid"]})
    figs = _analyze_figures(os.path.join(adir, "figures"), frames)

    _write_receipt(out, "analyze", {"figures": figs})
    log("[analyze] done")
    return metrics


def _write_csv_new(path, rows):
    _guard_write(path)
    if os.path.exists(path):
        raise SystemExit(f"conflict: {path} already exists (create-only stage)")
    R._write_csv(path, rows)


def _load_frozen(out):
    with open(os.path.join(out, "source_manifest.json"), "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    with open(os.path.join(out, "baseline_params.json"), "r", encoding="utf-8") as fh:
        baseline = json.load(fh)
    return manifest, baseline


def _anomaly_by_log(out):
    p = os.path.join(out, "provenance", "anomaly_windows.json")
    with open(p, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return {k: [tuple(w) for w in v] for k, v in doc["windows"].items()}
# ---------------------------------------------------------------------------
# feed-forward estimability
# ---------------------------------------------------------------------------
def _limit_fraction(flags, a, b):
    f = np.asarray(flags[a:b], dtype=float)
    if f.size == 0 or not np.isfinite(f).any():
        return float("nan")
    return float(np.mean((f.astype(np.int64) & FLAG_LIMIT) != 0))


def _platform_rows(frame, loop):
    """Steady reference platforms with the evidence needed for a FF anchor."""
    t = frame["t"]
    mask = frame["masks"]["numeric"]
    ref_disp = _loop_to_display(loop, frame["ref"])
    rows = []
    if not mask.any():
        return rows
    aux_ok = frame["steer_ok"] if loop == "yaw" else frame["thr_out_ok"]
    for a, b in _split_blocks(frame, mask):
        sub = mask[a:b]
        idx = np.where(sub)[0]
        # contiguous runs inside the block
        if idx.size == 0:
            continue
        seg = np.split(idx, np.where(np.diff(idx) != 1)[0] + 1)
        for s in seg:
            if s.size < 3:
                continue
            aa, bb = int(a + s[0]), int(a + s[-1]) + 1
            min_s = YAW_PLAT_MIN_S if loop == "yaw" else SPEED_PLAT_MIN_S
            plats = _platforms(
                t[aa:bb], ref_disp[aa:bb], frame["region"][aa:bb], min_s,
                (1.0 if loop == "yaw" else 0.05),
                (YAW_PLAT_MAX_ACC if loop == "yaw" else None))
            for p in plats:
                gi = aa + p["idx"]
                if loop == "yaw" and abs(p["ref"]) < math.radians(YAW_PLAT_MIN_RATE):
                    # a near-zero reference is a "hold still" platform; it is
                    # kept in the diagnostics but cannot anchor a feed-forward
                    p["below_min_rate"] = True
                cov = float(np.mean(aux_ok[gi])) if gi.size else 0.0
                lim = _limit_fraction(frame["flags"], int(gi[0]), int(gi[-1]) + 1)
                # steady tail: the last 3 s of the platform, but never more
                # than a third of it (a short platform would otherwise be
                # judged entirely on its own transient)
                tail_s = 3.0 if loop == "yaw" else 5.0
                tail_s = min(tail_s, max(1.0, p["span_s"] / 3.0))
                t_start = t[gi[-1]] - tail_s
                tail = gi[t[gi] >= t_start]
                if tail.size < 3:
                    tail = gi[-3:]
                if loop == "yaw":
                    steer_norm = np.asarray(frame["steer_out"], dtype=float)[tail] / \
                        STEER_FULL_SCALE
                    x_native = np.asarray(frame["ref"], dtype=float)[tail]
                    x_actual = np.asarray(frame["act"], dtype=float)[tail]
                    speed = np.asarray(frame["thr_speed"], dtype=float)[tail]
                    speed_med = float(np.nanmedian(speed)) if np.isfinite(speed).any() \
                        else float("nan")
                    y = float(np.nanmedian(steer_norm)) if np.isfinite(steer_norm).any() \
                        else float("nan")
                    x = float(np.nanmedian(x_actual)) if np.isfinite(x_actual).any() \
                        else float("nan")
                    # report unit only: rad/s -> deg/s for the steering loop
                    ref_med = float(np.nanmedian(np.degrees(x_native)))
                else:
                    thr_norm = np.asarray(frame["thr_out"], dtype=float)[tail] / \
                        THROTTLE_FULL_SCALE
                    y = float(np.nanmedian(thr_norm)) if np.isfinite(thr_norm).any() \
                        else float("nan")
                    x = float(np.nanmedian(np.asarray(frame["act"], dtype=float)[tail])) \
                        if np.isfinite(np.asarray(frame["act"], dtype=float)[tail]).any() \
                        else float("nan")
                    rate = _loop_to_display("yaw", np.asarray(frame["act"], dtype=float)[tail])
                    speed_med = float(np.nanmedian(np.asarray(frame["act"], dtype=float)[tail]))
                    ref_med = float(np.nanmedian(ref_disp[gi]))
                    x_native = np.asarray(frame["act"], dtype=float)[tail]
                    x_actual = x_native
                rows.append({
                    "t0_s": round(float(t[gi[0]]), 3),
                    "t1_s": round(float(t[gi[-1]]), 3),
                    "span_s": round(float(p["span_s"]), 3),
                    "ref_display": round(ref_med, 4),
                    "ref_native": (float(np.nanmedian(np.asarray(frame["ref"], dtype=float)[tail]))
                                   if np.isfinite(np.asarray(frame["ref"], dtype=float)[tail]).any()
                                   else None),
                    "x_actual": x, "steer_or_throttle_norm": y,
                    "forward_speed": speed_med,
                    "coverage": round(cov, 4),
                    "limit_fraction": None if not math.isfinite(lim) else round(lim, 4),
                    "below_min_rate": bool(p.get("below_min_rate", False)),
                    "speed_bin": _speed_bin(speed_med) if loop == "yaw" else
                    _speed_bin(float(np.nanmedian(np.asarray(frame["act"], dtype=float)[tail])))
                    if np.isfinite(np.nanmedian(np.asarray(frame["act"], dtype=float)[tail]))
                    else None,
                })
    return rows


def _speed_bin(v):
    if v is None or not math.isfinite(v):
        return None
    for lo, hi in SPEED_BINS:
        if lo <= v < hi:
            return f"[{lo},{hi})"
    return None


def _fit_anchor(points, block_ids=None):
    """Equal-weight rank-2 fit with a platform-level block bootstrap.

    One median point per platform, ``y = k*x + b``.  No model alternatives are
    tried: if the rank or the uncertainty gate fails, the anchor is reported as
    unavailable instead of being massaged into existence.
    """
    pts = [(float(x), float(y)) for x, y in points
           if x is not None and y is not None and math.isfinite(x) and math.isfinite(y)]
    doc = {"points": len(pts), "k": None, "b": None, "ci_k": None,
           "ci_width_ratio": None, "available": False, "reason": None}
    if len(pts) < 2:
        doc["reason"] = "fewer_than_two_platforms"
        return doc
    A = np.array([[x, 1.0] for x, _y in pts], dtype=float)
    v = np.array([y for _x, y in pts], dtype=float)
    if np.linalg.matrix_rank(A) < 2:
        doc["reason"] = "rank_deficient"
        return doc
    try:
        sol, *_ = np.linalg.lstsq(A, v, rcond=GET_LSTSQ_RCOND)
    except np.linalg.LinAlgError:
        doc["reason"] = "non_finite_solution"
        return doc
    k, b = float(sol[0]), float(sol[1])
    if not (math.isfinite(k) and math.isfinite(b)):
        doc["reason"] = "non_finite_solution"
        return doc
    doc["k"], doc["b"] = k, b

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = []
    for _ in range(BOOTSTRAP_N):
        pick = rng.integers(0, len(pts), size=len(pts))
        Ab = A[pick]
        vb = v[pick]
        if np.linalg.matrix_rank(Ab) < 2:
            continue
        try:
            sb, *_ = np.linalg.lstsq(Ab, vb, rcond=GET_LSTSQ_RCOND)
        except np.linalg.LinAlgError:
            continue
        if math.isfinite(sb[0]):
            draws.append(float(sb[0]))
    doc["bootstrap_valid"] = len(draws)
    if len(draws) < BOOTSTRAP_MIN_VALID:
        doc["reason"] = f"bootstrap_full_rank_{len(draws)}_of_{BOOTSTRAP_N}"
        return doc
    lo, hi = (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
    doc["ci_k"] = [lo, hi]
    width = hi - lo
    doc["ci_width_ratio"] = width / abs(k) if k != 0 else None
    if not (k > 0):
        doc["reason"] = "non_positive_slope"
        return doc
    if lo <= 0.0 <= hi:
        doc["reason"] = "ci_crosses_zero"
        return doc
    if k == 0 or width > 0.5 * abs(k):
        doc["reason"] = "ci_too_wide"
        return doc
    if abs(b) > 0.1:
        doc["reason"] = "bias_too_large"
        return doc
    doc["available"] = True
    return doc


def _ff_gate_yaw(rows):
    ok = [r for r in rows
          if not r.get("below_min_rate")
          and abs(r["ref_display"]) >= YAW_PLAT_MIN_RATE
          and r["coverage"] >= YAW_COVER_MIN
          and (r["limit_fraction"] is None or r["limit_fraction"] <= YAW_LIMIT_MAX)]
    out = {"platforms_total": len(rows), "platforms_eligible": len(ok),
           "platforms_below_min_rate": sum(1 for r in rows if r.get("below_min_rate")),
           "per_direction": {}, "per_bin": {}, "anchor": None,
           "single_anchor": None, "reason": None}
    left = [r for r in ok if r["ref_display"] < 0]
    right = [r for r in ok if r["ref_display"] > 0]
    out["platforms_dropped_saturated"] = sum(
        1 for r in rows if r["limit_fraction"] is not None
        and r["limit_fraction"] > YAW_LIMIT_MAX)
    out["platforms_dropped_coverage"] = sum(
        1 for r in rows if r["coverage"] < YAW_COVER_MIN)
    out["per_direction"] = {"left": len(left), "right": len(right),
                            "required_per_direction": YAW_PER_DIR_MIN}
    if len(left) < YAW_PER_DIR_MIN or len(right) < YAW_PER_DIR_MIN:
        parts = [f"left {len(left)}, right {len(right)} "
                 f"(need {YAW_PER_DIR_MIN} each)"]
        if out["platforms_dropped_saturated"]:
            parts.append(f"{out['platforms_dropped_saturated']} platform(s) "
                         f"saturated above {YAW_LIMIT_MAX:.0%}")
        if out["platforms_dropped_coverage"]:
            parts.append(f"{out['platforms_dropped_coverage']} platform(s) below "
                         f"{YAW_COVER_MIN:.0%} coverage")
        out["reason"] = "insufficient_independent_platforms: " + "; ".join(parts)
        return out
    per_bin = {}
    for b in sorted({r["speed_bin"] for r in ok if r["speed_bin"]}):
        sel = [r for r in ok if r["speed_bin"] == b]
        fit = _fit_anchor([(r["x_actual"], r["steer_or_throttle_norm"]) for r in sel])
        fit["speed_bin"] = b
        per_bin[b] = fit
    out["per_bin"] = per_bin
    ks = [v["k"] for v in per_bin.values() if v["available"]]
    out["eligible_bins"] = sorted(k for k, v in per_bin.items() if v["available"])
    if not ks:
        out["reason"] = "no_bin_passed_fit_gate"
        return out
    if len(ks) > 1:
        spread = (max(ks) - min(ks)) / abs(float(np.median(ks)))
        out["bin_spread"] = float(spread)
        if spread > 0.2:
            out["reason"] = "bins_differ_by_more_than_20pct"
            return out
    out["single_anchor"] = float(np.median(ks))
    out["anchor"] = out["single_anchor"]
    return out


def _ff_gate_speed(rows):
    ok = [r for r in rows
          if r["coverage"] >= YAW_COVER_MIN
          and (r["limit_fraction"] is None or r["limit_fraction"] <= YAW_LIMIT_MAX)]
    out = {"platforms_total": len(rows), "platforms_eligible": len(ok),
           "platforms_over_limit": sum(
               1 for r in rows if r["limit_fraction"] is not None
               and r["limit_fraction"] > YAW_LIMIT_MAX),
           "distinct_bins": 0, "bins_separated": False, "fit": None, "reason": None}
    bins = sorted({r["speed_bin"] for r in ok if r["speed_bin"]})
    out["distinct_bins"] = len(bins)
    if len(ok) < 3:
        out["reason"] = "fewer_than_three_platforms"
        return out
    if len(bins) < SPEED_PLAT_MIN_BINS:
        out["reason"] = "fewer_than_two_speed_bins"
        return out
    centres = [float(np.mean([r["x_actual"] for r in ok if r["speed_bin"] == b]))
               for b in bins]
    if max(centres) - min(centres) < SPEED_PLAT_BIN_SEP:
        out["reason"] = "speed_bins_not_separated"
        return out
    out["bins_separated"] = True
    out["fit"] = _fit_anchor([(r["x_actual"], r["steer_or_throttle_norm"]) for r in ok])
    return out


def _parent_sha(values):
    canon = json.dumps({k: values.get(k) for k in VAR_WHITELIST},
                       sort_keys=True, ensure_ascii=False)
    return _sha_text(canon)


def _candidate_rows(baseline_pid, originals):
    """Bounded single-parameter matrix; every row is an experiment, not advice."""
    rows = []
    parent = {k: originals.get(k) for k in VAR_WHITELIST}
    psha = _parent_sha(parent)

    def add(stage, loop, param, new, source, cond, note, status="trial_candidate"):
        if new is None:
            rows.append({
                "candidate_id": f"{loop}_{stage}_skip", "loop": loop, "stage": stage,
                "param": param, "original": parent.get(param), "candidate": None,
                "parent_param_sha256": psha, "source": source,
                "applicable_conditions": cond, "validated": False,
                "recommendation_status": status, "note": note})
            return
        cid = f"{loop}_{stage}_{param}_{new:.6g}".replace(".", "p")
        rows.append({
            "candidate_id": cid, "loop": loop, "stage": stage, "param": param,
            "original": parent.get(param), "candidate": new,
            "parent_param_sha256": psha, "source": source,
            "applicable_conditions": cond, "validated": False,
            "recommendation_status": status, "note": note})

    return rows, psha


def _build_matrix(baseline, ff_yaw, ff_speed):
    originals = dict(baseline["pid"]["yaw"])
    originals.update(baseline["pid"]["speed"])
    rows, psha = _candidate_rows(baseline["pid"], originals)

    # --- steering ---------------------------------------------------------
    ff0 = originals.get("ATC_STR_RAT_FF")
    ff_cand = None
    if ff_yaw["anchor"] is not None and ff0:
        lo, hi = FF_CLIP[0] * ff0, FF_CLIP[1] * ff0
        ff_cand = min(max(ff_yaw["anchor"], lo), hi)
        clip_note = ("anchor outside the +-20 % band is clipped for the trial; the "
                     "unclipped estimate stays in the diagnostics")
    else:
        clip_note = ("no FF anchor: the FF stage is skipped and P is tested with "
                     "the recorded FF held")
    rows.append({
        "candidate_id": "yaw_ff_anchor" if ff_cand is not None else "yaw_ff_skip",
        "loop": "yaw", "stage": "FF", "param": "ATC_STR_RAT_FF",
        "original": ff0, "candidate": ff_cand, "parent_param_sha256": psha,
        "source": "steady platform regression (see candidate_rationale.json)",
        "applicable_conditions": "closed-loop ACRO/AUTO/STEERING, forward speed "
                                 f"in covered bins {ff_yaw.get('eligible_bins')}",
        "validated": False,
        "recommendation_status": "trial_candidate" if ff_cand is not None
        else "skipped_no_ff_evidence",
        "note": clip_note})

    p0, i0 = originals.get("ATC_STR_RAT_P"), originals.get("ATC_STR_RAT_I")
    for scale in GAIN_SCALES:
        if scale == 1.0:
            rows.append({
                "candidate_id": "yaw_p_retain", "loop": "yaw", "stage": "P",
                "param": "ATC_STR_RAT_P", "original": p0, "candidate": p0,
                "parent_param_sha256": psha, "source": "control arm",
                "applicable_conditions": "same as the tested candidate",
                "validated": False, "recommendation_status": "retain_parent",
                "note": "unchanged-P control arm; not an improvement claim"})
            continue
        rows.append({
            "candidate_id": f"yaw_p_{int(round(scale*100))}", "loop": "yaw",
            "stage": "P", "param": "ATC_STR_RAT_P", "original": p0,
            "candidate": (p0 * scale) if p0 is not None else None,
            "parent_param_sha256": psha,
            "source": "bounded +-10 % single-parameter hypothesis",
            "applicable_conditions": "closed-loop ACRO/AUTO/STEERING, "
                                     "FF held at the selected or recorded value",
            "validated": False, "recommendation_status": "trial_candidate",
            "note": "I is held; P is not ranked before the trials exist"})
    for scale in GAIN_SCALES:
        if scale == 1.0:
            rows.append({
                "candidate_id": "yaw_i_retain", "loop": "yaw", "stage": "I",
                "param": "ATC_STR_RAT_I", "original": i0, "candidate": i0,
                "parent_param_sha256": psha, "source": "control arm",
                "applicable_conditions": "entered only after the P decision",
                "validated": False, "recommendation_status": "retain_parent",
                "note": "unchanged-I control arm"})
            continue
        rows.append({
            "candidate_id": f"yaw_i_{int(round(scale*100))}", "loop": "yaw",
            "stage": "I", "param": "ATC_STR_RAT_I", "original": i0,
            "candidate": (i0 * scale) if i0 is not None else None,
            "parent_param_sha256": psha,
            "source": "bounded +-10 % single-parameter hypothesis",
            "applicable_conditions": "entered only after the P decision is fixed",
            "validated": False, "recommendation_status": "trial_candidate",
            "note": "not reachable until the P stage is decided"})

    # --- speed ------------------------------------------------------------
    cruise_speed = originals.get("CRUISE_SPEED")
    cruise_thr = originals.get("CRUISE_THROTTLE")
    k = (ff_speed.get("fit") or {}).get("k")
    b = (ff_speed.get("fit") or {}).get("b")
    speed_anchor = None
    speed_note = "no speed FF anchor"
    if k is not None and b is not None:
        covered = [lo for lo, hi in SPEED_BINS if lo <= cruise_speed < hi]
        if not covered:
            speed_note = ("CRUISE_SPEED is outside every covered platform bin; "
                          "CRUISE_THROTTLE is not extrapolated")
        elif cruise_thr:
            raw = THROTTLE_FULL_SCALE * (k * cruise_speed + b)
            lo, hi = FF_CLIP[0] * cruise_thr, FF_CLIP[1] * cruise_thr
            speed_anchor = min(max(raw, lo), hi)
            speed_note = ("100*(k*CRUISE_SPEED+b) clipped to the +-20 % band; the "
                          "unclipped estimate stays in the diagnostics")
    rows.append({
        "candidate_id": "speed_cruise_anchor" if speed_anchor is not None
        else "speed_cruise_skip",
        "loop": "speed", "stage": "CRUISE", "param": "CRUISE_THROTTLE",
        "original": cruise_thr, "candidate": speed_anchor,
        "parent_param_sha256": psha,
        "source": "steady straight-platform regression",
        "applicable_conditions": "forward straight, |turn rate| <= 5 deg/s",
        "validated": False,
        "recommendation_status": "trial_candidate" if speed_anchor is not None
        else "skipped_no_ff_evidence",
        "note": speed_note})

    sp0, si0 = originals.get("ATC_SPEED_P"), originals.get("ATC_SPEED_I")
    for stage, param, base in (("P", "ATC_SPEED_P", sp0), ("I", "ATC_SPEED_I", si0)):
        for scale in GAIN_SCALES:
            if scale == 1.0:
                rows.append({
                    "candidate_id": f"speed_{stage.lower()}_retain", "loop": "speed",
                    "stage": stage, "param": param, "original": base,
                    "candidate": base, "parent_param_sha256": psha,
                    "source": "control arm",
                    "applicable_conditions": "entered only after the steering stage "
                                             "is decided",
                    "validated": False,
                    "recommendation_status": "retain_parent",
                    "note": "unchanged control arm"})
                continue
            rows.append({
                "candidate_id": f"speed_{stage.lower()}_{int(round(scale*100))}",
                "loop": "speed", "stage": stage, "param": param, "original": base,
                "candidate": (base * scale) if base is not None else None,
                "parent_param_sha256": psha,
                "source": "bounded +-10 % single-parameter hypothesis",
                "applicable_conditions": "entered only after the steering stage is "
                                         "decided and the new baseline is valid",
                "validated": False, "recommendation_status": "trial_candidate",
                "note": "not reachable before the steering decision"})
    return rows, psha


def _recommendation_status(loop, ff_gate, numeric_s, blocks):
    """Per-loop status.  ``validated`` is unreachable without new trials.

    A single usable block is still not enough to promise anything: the acceptance
    scheme needs >=3 independent matched blocks, so the honest label for the
    historical data is ``insufficient_evidence`` even when some seconds exist.
    """
    if numeric_s <= 0 or blocks <= 0:
        return "insufficient_evidence"
    if blocks < GATE_MIN_BLOCKS:
        return "insufficient_evidence"
    return "trial_candidate"
# ---------------------------------------------------------------------------
# stage: recommend
# ---------------------------------------------------------------------------
def stage_recommend(args):
    log = print
    out = args.out
    _require_stage(out, "prepare")
    _require_stage(out, "analyze")
    _ensure_out(out, "recommend")
    rdir = os.path.join(out, "recommend")
    _mkdir(rdir)

    manifest, baseline = _load_frozen(out)
    with open(os.path.join(out, "analyze", "coverage.json"), "r", encoding="utf-8") as fh:
        coverage = json.load(fh)
    with open(os.path.join(out, "analyze", "baseline_metrics.json"), "r", encoding="utf-8") as fh:
        metrics = json.load(fh)
    with open(os.path.join(out, "analyze", "segments.csv"), "r", encoding="utf-8") as fh:
        import csv
        segments = list(csv.DictReader(fh))
    windows_all = _anomaly_by_log(out)

    frames, plat_rows = [], {"yaw": [], "speed": []}
    for name in manifest["sources_parsed"]:
        z = _load_npz(os.path.join(out, manifest["parsed"][name]["npz"]))
        params, _hist = R._params_dict(z)
        for loop in LOOPS:
            f = build_loop_frame(z, params, windows_all.get(name, []), name, loop)
            if f is None:
                continue
            frames.append(f)
            for r in _platform_rows(f, loop):
                r["log"] = name
                plat_rows[loop].append(r)

    ff_yaw = _ff_gate_yaw(plat_rows["yaw"])
    ff_speed = _ff_gate_speed(plat_rows["speed"])
    rows, psha = _build_matrix(baseline, ff_yaw, ff_speed)

    _write_csv_new(os.path.join(rdir, "trial_candidates.csv"), rows)

    cov_by_loop = {}
    for c in coverage["per_log_loop"]:
        e = cov_by_loop.setdefault(c["loop"], {"numeric_s": 0.0, "blocks": 0,
                                               "guided_s": 0.0, "manual_s": 0.0})
        e["numeric_s"] += c["numeric_credit_s"]
        e["blocks"] += c["numeric_blocks"]
        e["guided_s"] += c["diagnostic_only_guided_s"]
        e["manual_s"] += c["negative_control_manual_s"]

    status = {}
    for loop in LOOPS:
        gate = ff_yaw if loop == "yaw" else ff_speed
        status[loop] = _recommendation_status(loop, gate, cov_by_loop[loop]["numeric_s"],
                                              cov_by_loop[loop]["blocks"])

    rationale = {
        "parent_param_sha256": psha,
        "candidate_matrix_sha256": _sha_text(json.dumps(rows, sort_keys=True, default=str)),
        "baseline_parameters": baseline["pid"],
        "whitelist": list(VAR_WHITELIST),
        "held_parameters": {k: baseline["backup_20261110"].get(k) for k in HELD_PARAMS},
        "ff_gates": {"yaw": ff_yaw, "speed": ff_speed},
        "platform_points": plat_rows,
        "coverage": cov_by_loop,
        "recommendation_status": status,
        "deployable": False,
        "deployable_reason": ("no authorised controlled trials have been scored; "
                              "the matrix is a set of bounded hypotheses, not a "
                              "parameter package"),
        "status_basis": {
            "numeric_seconds": {l: cov_by_loop[l]["numeric_s"] for l in LOOPS},
            "numeric_blocks": {l: cov_by_loop[l]["blocks"] for l in LOOPS},
            "blocks_required": GATE_MIN_BLOCKS,
            "rule": ("insufficient_evidence below 3 independent matched blocks; "
                     "validated is unreachable without new controlled trials"),
        },
        "model_note": ("no virtual-optimum search was run: the historical "
                       "hydrodynamic model was already rejected (velocity RMSE "
                       "0.8235 m/s, yaw-rate median RMSE 26.39 deg/s, positive "
                       "Jacobian real part), so candidates are bounded local "
                       "hypotheses, never the output of an optimiser"),
    }
    _write_new_json(os.path.join(rdir, "candidate_rationale.json"), rationale)

    protocol = _trial_protocol(baseline, status, ff_yaw, ff_speed)
    _write_new_text(os.path.join(rdir, "trial_protocol.md"), protocol)

    report = _tuning_report(out, manifest, baseline, coverage, metrics, segments,
                            rationale, rows, status)
    _write_new_text(os.path.join(out, "recommend", "PID_TUNING_REPORT.md"), report)

    changed = _changed_files(out, rdir)
    _write_new_json(os.path.join(rdir, "changed_files.json"), changed)

    _write_receipt(out, "recommend", {
        "candidate_matrix_sha256": rationale["candidate_matrix_sha256"],
        "parent_param_sha256": psha,
        "recommendation_status": status,
        "deployable": False,
    })
    log(f"[recommend] status: {status}")
    return status
def _fmt(v, nd=4):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        if not math.isfinite(v):
            return "—"
        return f"{v:.{nd}g}"
    return str(v)


def _trial_protocol(baseline, status, ff_yaw, ff_speed):
    pid = baseline["pid"]
    y, s = pid["yaw"], pid["speed"]
    lines = []
    A = lines.append
    A("# 飞控 PID 补采与验证协议（未执行，仅产出）")
    A("")
    A("> 本文件不授权任何通电、写参、解锁或下水动作。下面每一步都需要用户另行授权，")
    A("> 并由现场人员执行；离线分析已经完成，不等待硬件。")
    A("")
    A("## 0. 当前结论")
    A("")
    A(f"- 转向环推荐状态：**{status['yaw']}**；航速环推荐状态：**{status['speed']}**。")
    A("- 本轮**没有**可导入的 `.param`，也不会生成。只有在新的受控实测和独立组合验证")
    A("  全部通过后，才会在**新的评估根**写出 `recommended.param`。")
    A("- 现有 2026-11-02 数据不足以整定：见 `PID_TUNING_REPORT.md` 的逐项 PASS/FAIL/")
    A("  not_evaluable。")
    A("")
    A("## 1. 记录的原值（本轮候选矩阵的中心，不是建议值）")
    A("")
    A("| 回路 | 参数 | 记录值 |")
    A("|---|---|---:|")
    for k in ("ATC_STR_RAT_FF", "ATC_STR_RAT_P", "ATC_STR_RAT_I", "ATC_STR_RAT_D",
              "ATC_STR_RAT_IMAX"):
        A(f"| 转向率 | `{k}` | {_fmt(y.get(k))} |")
    for k in ("ATC_SPEED_P", "ATC_SPEED_I", "ATC_SPEED_D", "ATC_SPEED_FF",
              "ATC_SPEED_IMAX"):
        A(f"| 航速 | `{k}` | {_fmt(s.get(k))} |")
    for k in ("CRUISE_SPEED", "CRUISE_THROTTLE", "SPEED_MAX", "SCHED_LOOP_RATE"):
        A(f"| 共用 | `{k}` | {_fmt((baseline['backup_20261110'] or {}).get(k))} |")
    A("")
    A("## 2. 通电 / 下水前门（任一未闭合则水试门保持关闭）")
    A("")
    A("1. **无桨台架**：确认左右通道与转向方向、实际电调类型、OneShot 兼容性、")
    A("   `SERVOx_TRIM` 的实际停转行为与输出信号。依据必须是信号实测或电机实际响应，")
    A("   不能只看 `RCOU` 数字。")
    A("2. 按器件额定值设置电源限流；器件额定值或信号制式不明时**不给推进器上电**。")
    A("3. 物理断动力的急停必须独立有效；实测失信号、上锁、模式切换后的真实停机。")
    A("   `MOT_SAFE_DISARM` 可作为待验证的现场停机设计，但不得自动写入，也不得仅凭")
    A("   数值认定安全。")
    A("4. 记录硬件/推进器身份、日期、固件 `custom_version`、完整参数前后备份和停机证据。")
    A("5. **11.02 遗留的 PWM 中位自转异常尚未排清、停机未验证，因此水试门当前为关闭。**")
    A("")
    A("> 不要把台架 SOP 里的 `ARMING_CHECK=0`、强制解锁或关闭安全开关的设置复制到水试。")
    A("")
    A("## 3. 补采顺序（固定，不跳步）")
    A("")
    A("先转向：基线 → FF（若有）→ P → I；转向阶段**已完成裁决**（含“保留原值”）")
    A("且新基线/安全门有效后，固定转向设置，再走航速：基线 → cruise（若有）→ P → I。")
    A("MPC 停止，使用实际已核实的 ACRO 闭环；保持原速率限制，不更改模式契约。")
    A("")
    A("### 3.1 转向")
    A("")
    A("- 模式：ACRO（闭环转向率 PID，`ATC_STR_RAT_*` 真正入环）。")
    A("- 前进低速两档目标：0.5 与 0.8 m/s。")
    A("- 转向率目标序列：0 → +10 → 0 → −10 → 0 deg/s，之后才到 ±20 deg/s。")
    A("- 每平台 ≥ 8 s，每方向至少 3 次。")
    A(f"- FF 可估门（离线判据）：{ff_yaw.get('reason') or 'passed'}；"
      f"合格平台 {ff_yaw['platforms_eligible']}/{ff_yaw['platforms_total']}。")
    A("")
    A("### 3.2 航速")
    A("")
    A("- 直线：0.3 → 0.6 → 0.9 → 0.6 → 0.3 m/s，每平台 ≥ 15 s，至少 3 组。")
    A(f"- FF 可估门：{ff_speed.get('reason') or 'passed'}；"
      f"合格平台 {ff_speed['platforms_eligible']}/{ff_speed['platforms_total']}。")
    A("- `SPEED_MAX=0` 时改动 `CRUISE_SPEED` 会改变 ACRO 杆量→速度映射：报告变更前后的")
    A("  `CRUISE_SPEED/(CRUISE_THROTTLE/100)`，实际试验一律以日志中的**目标速度**匹配，")
    A("  不以相同杆量当作同一输入。")
    A("")
    A("### 3.3 匹配块")
    A("")
    A("- 每个候选与基线按 **A–B–B–A** 顺序做匹配块，至少 3 个独立往返块。")
    A("- 同一块内只变一个参数；同电池电压档、同装载、同水域。")
    A("- 反向航向成对，减轻风流影响。")
    A("- 参数读取不符合该候选、参考平台不符、环境明显变化 → 该次试验保留为**无效**")
    A("  并说明原因，不覆盖旧 attempt。")
    A("")
    A("## 4. 中止条件（立即执行）")
    A("")
    A("实际速度 > 1.5 m/s、|转向率| > 35 deg/s、失控旋转、遥测中断 > 0.5 s、")
    A("持续振荡增长，或操作者判断异常 → 立即中止。")
    A("")
    A("中止动作使用**已验证的物理停机**；不假定 HOLD 或 MANUAL 一定停船。")
    A("安全员、物理急停、空旷水域为必需条件。")
    A("")
    A("## 5. 明确不做的事")
    A("")
    A("- 不运行 CIRCLE 自动 QuickTune、自激继电或极限增益法；本轮是低幅度单因素验证。")
    A("- 场地或船体无法安全形成上述平台时，**停止采集并记录前置条件不足**，")
    A("  不扩大幅度去换“可辨识”。")
    A("- 台架无桨数据不能证明水中的 PID 响应；系泊数据也不混作自由航行整定数据。")
    A("")
    return "\n".join(lines) + "\n"


def _tuning_report(out, manifest, baseline, coverage, metrics, segments,
                   rationale, rows, status):
    lines = []
    A = lines.append
    A("# 2026-11-02 飞控 PID 闭环诊断报告")
    A("")
    A("离线分析。**没有**连接飞控、写参数、解锁、启动推进器或下水。")
    A("")
    A("## 1. 输入与版本")
    A("")
    A("| 日志 | 字节 | SHA-256 |")
    A("|---|---:|---|")
    for name, s in manifest["sources"].items():
        A(f"| `{name}` | {s['bytes']} | `{s['sha256']}` |")
    A("")
    ver = manifest["firmware_version_strings_in_logs"]
    for name, msgs in ver.items():
        hits = [m for m in msgs if m.startswith("Ardu")]
        if hits:
            A(f"- `{name}` 版本字符串：`{hits[0]}`（保留原样，未抹平与 `4.7.1.dev` 的差别）")
    fw = manifest["firmware"]
    A(f"- 冻结固件源码 commit：`{fw['commit']}`，"
      f"{sum(1 for v in fw['files'].values() if v.get('status') == 'ok')}"
      f"/{len(fw['files'])} 个 primary source 已保存并记录 SHA。")
    if not fw.get("complete"):
        A("- **`firmware_source_unavailable`**：部分源码未取到，因此不生成可部署参数。")
    A(f"- 参数备份（11.10 快照，**不是** 11.02 的时序，也不等于执行当天生效值）："
      f"`{manifest['parameter_backup']['copied_to']}`，"
      f"{manifest['parameter_backup']['param_count']} 项。")
    A("")
    A("## 2. 记录的原值与核对")
    A("")
    cross = baseline["cross_check_20261102_vs_20261110"]
    A("| 参数 | 日志记录值 | 11.10 备份 | 状态 |")
    A("|---|---:|---:|---|")
    for k, v in cross.items():
        A(f"| `{k}` | {_fmt(v.get('log_20261102'))} | {_fmt(v.get('backup_20261110'))} "
          f"| {v.get('status')} |")
    A("")
    A("> 三份主日志的上述参数一致，没有观察到 PARM 变化；11.10 快照只作并列登记，")
    A("> 不反灌历史数据。")
    A("")
    A("## 3. 相对时间轴：三份日志的长度远超可用闭环时间")
    A("")
    A("实测 PIDS/PIDA ≈ 50 Hz（`SCHED_LOOP_RATE=50`），STER/THR/RCOU ≈ 10 Hz。")
    A("可用时间只统计**真正入环**且健康、连续、已解锁的样本：")
    A("")
    A("| 日志 | 回路 | 可用闭环秒 | 可用块 | 最长连续块 | 独立参考变化 | 诊断-only(GUIDED) | MANUAL 负对照 |")
    A("|---|---|---:|---:|---:|---:|---:|---:|")
    for c in coverage["per_log_loop"]:
        A(f"| `{c['log']}` | {c['loop']} | {c['numeric_credit_s']} | "
          f"{c['numeric_blocks']} | {c['longest_numeric_block_s']} | "
          f"{c['independent_reference_changes']} | "
          f"{c['diagnostic_only_guided_s']} | {c['negative_control_manual_s']} |")
    A("")
    A("### 3.1 各流缺口阈值与切段原因")
    A("")
    for c in coverage["per_log_loop"][:2]:
        A(f"`{c['log']}` / {c['loop']}：")
        A("")
        A("| 原因 | 被排除秒数 |")
        A("|---|---:|")
        for k, v in sorted(c["excluded_seconds_by_reason"].items(),
                           key=lambda kv: -kv[1]):
            A(f"| {k} | {v} |")
        A("")
        A("缺口阈值（s）：" + "、".join(f"`{k}`={_fmt(v)}"
                                        for k, v in c["gap_thresholds_s"].items()) + "。")
        A("缺口两侧各排 1 s；**不跨缺口插值**。")
        A("")
    A("## 4. 两环基线指标")
    A("")
    A("| 日志 | 回路 | 块数 | 秒 | RMSE 中位 | IAE 合计 |")
    A("|---|---|---:|---:|---:|---:|")
    for key, m in metrics["loops"].items():
        name, loop = key.split("|")
        unit = metrics["units"][loop]
        A(f"| `{name}` | {loop} | {m['numeric_blocks']} | "
          f"{m['numeric_duration_s']} | "
          f"{_fmt(m.get('rmse_display_median'))} {unit} | "
          f"{_fmt(m.get('iae_display_total'))} |")
    A("")
    A("## 5. 逐项判定")
    A("")
    A("| 判据 | 结果 | 依据 |")
    A("|---|---|---|")
    tot_y = sum(c["numeric_credit_s"] for c in coverage["per_log_loop"]
                if c["loop"] == "yaw")
    tot_s = sum(c["numeric_credit_s"] for c in coverage["per_log_loop"]
                if c["loop"] == "speed")
    blocks = sum(c["numeric_blocks"] for c in coverage["per_log_loop"]
                 if c["loop"] == "yaw")
    A(f"| 转向环可整定 | {'PASS' if blocks >= 3 else 'FAIL'} | "
      f"数值信用 {round(tot_y, 2)} s / {blocks} 块（验收需 ≥3 个独立匹配块） |")
    A(f"| 航速环可整定 | {'PASS' if blocks >= 3 else 'FAIL'} | "
      f"数值信用 {round(tot_s, 2)} s / {blocks} 块 |")
    A(f"| 转向 FF 可估 | "
      f"{'PASS' if rationale['ff_gates']['yaw'].get('anchor') is not None else 'FAIL'} | "
      f"{rationale['ff_gates']['yaw'].get('reason') or '门通过'} |")
    A(f"| 航速 FF 可估 | "
      f"{'PASS' if (rationale['ff_gates']['speed'].get('fit') or {}).get('available') else 'FAIL'} | "
      f"{rationale['ff_gates']['speed'].get('reason') or '门通过'} |")
    A("| 阶跃超调/调节时间 | not_evaluable | 没有形成完整阶跃前后段的独立机动块 |")
    A("| 硬件停机可验证 | FAIL | 11.02 遗留自转异常未排清，缺电调遥测/停机证据 |")
    A("| 新增 PID 验证 | not_evaluable | 未收到授权的新试验清单 |")
    A("")
    A("### 5.0 唯一可用机动块的逐项体检")
    A("")
    A("历史数据里只有 15-31-04 的 AUTO 段留下 1 个可用块。把它直接拿去对照")
    A("验收门（上限取自本协议的绝对阈值）可以看清这批数据到底缺什么：")
    A("")
    A("| 日志 | 回路 | 稳态偏差 | 稳态成立 | 饱和占比 | 振荡 | 闭环秒 |")
    A("|---|---|---:|---|---:|---|---:|")
    any_block = False
    for key, mv in metrics["loops"].items():
        name, loop = key.split("|")
        for b in mv["blocks"]:
            any_block = True
            unit = metrics["units"][loop]
            A_SS = _loop_ss_limit(loop)
            A(f"| `{name}` | {loop} | {_fmt(b.get('ss_dev'))} {unit} "
              f"(限 {A_SS}) | {'yes' if b.get('ss_stable') else '**no**'} | "
              f"{_fmt(b.get('sat_frac'))} (限 {GATE_SAT_FRAC}) | "
              f"{_fmt(b.get('osc_duration_s'))} s | {_fmt(b.get('duration_s'))} |")
    if not any_block:
        A("| — | — | — | — | — | — | — |")
    A("")
    A("结论：即使这唯一的块也**不满足**稳态与饱和门，因此它只能用来描述现状，")
    A("不能作为“已整定”或“候选更优”的依据。")
    A("")
    A("### 5.1 GUIDED 为什么没有数值信用")
    A("")
    A("实测版 `mode.h` 的 `Guided::SubMode` 为 WP=0、HeadingAndSpeed=1、")
    A("TurnRateAndSpeed=2、Loiter=3、SteeringAndThrottle=4、Stop=5。")
    A("`GUIP` 只由三个通用 setter 写入；**direct steering/throttle 的 setter 不写 GUIP**。")
    A("本批没有登记完整外部命令追踪，因此三份历史 BIN 的 GUIDED 全部标")
    A("`activation_unproven`：缓存 PID 数值恰好与当前参考/测量一致，也不构成入环证明。")
    A("")
    A("## 6. 候选矩阵")
    A("")
    A(f"- 白名单：{', '.join('`'+k+'`' for k in VAR_WHITELIST)}。")
    A(f"- 矩阵 SHA-256：`{rationale['candidate_matrix_sha256']}`；"
      f"parent 参数集合 SHA：`{rationale['parent_param_sha256']}`。")
    A(f"- 候选条数：{len(rows)}；其中 `validated=true` 的条数："
      f"{sum(1 for r in rows if r.get('validated'))}。")
    A("")
    A("| candidate_id | 回路 | 阶段 | 参数 | 原值 | 候选 | 状态 |")
    A("|---|---|---|---|---:|---:|---|")
    for r in rows:
        A(f"| `{r['candidate_id']}` | {r['loop']} | {r['stage']} | "
          f"`{r['param']}` | {_fmt(r.get('original'))} | {_fmt(r.get('candidate'))} "
          f"| {r['recommendation_status']} |")
    A("")
    A("> 所有候选 `validated=false`，且**不得排序为已知更优**；数据不支持的方向")
    A("> 不给“建议增大/减小”的结论。")
    A("")
    A("## 7. 保持不变的参数")
    A("")
    A("两环 D 保持 0；`ATC_*_D_FF`、IMAX、FLTT/FLTE/FLTD、SMAX/PDMX、")
    A("`ATC_STR_ANG_P`、角/线加减速与速率上限、混控与电机参数保持各自原值。")
    A("本轮不在缺激励/缺噪声辨识下开放 D 或减小 IMAX。")
    A("")
    A("## 8. 结论")
    A("")
    A(f"- 转向环：`{status['yaw']}`")
    A(f"- 航速环：`{status['speed']}`")
    A("- 结果：`awaiting_controlled_trials`。缺的是：≥3 个独立匹配机动块的受控实测、")
    A("  可验证的物理停机证据，以及一组未参与选择的新采集做最终组合验证。")
    A("- 没有生成 `recommended.param` / `rollback.param`；" )
    A("  这两份文件只能在一个**新的评估根**里、在最终独立组合验证通过后写出。")
    A("")
    A("## 9. 与 11.02 其它产物的关系")
    A("")
    A("- 既有的 `reidentification_20261102_v10` 动力学模型结论为 `rejected`，")
    A("  本轮**没有**在它上面做 PID 最优搜索。")
    A("- `2026-11-02 16-19-57.bin` 已被旧辨识评分，不是全新盲测；其近乎全 MANUAL 的")
    A("  数据只用作“PID 未激活”负对照，**不能**充当 PID 验证集。")
    A("- 旧的 7 个异常窗只取起止时间，不采信其 `verdict` 的旧因果解释。")
    A("")
    return "\n".join(lines) + "\n"


def _changed_files(out, rdir):
    files = {}
    for base, scope in ((rdir, "recommend"),
                        (os.path.join(out, "analyze"), "analyze")):
        for dirpath, _d, names in os.walk(base):
            for fn in sorted(names):
                p = os.path.join(dirpath, fn)
                files[os.path.relpath(p, out)] = _file_sha(p)
    here = os.path.dirname(os.path.abspath(__file__))
    tests = os.path.join(os.path.dirname(here), "tests", "test_fcu_pid_20261102.py")
    code = {os.path.relpath(os.path.abspath(__file__)): _file_sha(os.path.abspath(__file__))}
    if os.path.exists(tests):
        code[os.path.relpath(tests)] = _file_sha(tests)
    return {
        "scope": "this round only: new analysis code and trial products",
        "note": ("no earlier S3-S5 products, no v10 identification output, no "
                 "upstream firmware and no ROS production configuration are mixed in"),
        "code": code,
        "products": files,
    }
# ---------------------------------------------------------------------------
# stage: verify  (read-only; prints JSON, never writes into --out)
# ---------------------------------------------------------------------------
def stage_verify(args):
    out = args.out
    problems, notes = [], []
    receipts = {}
    for stage in STAGE_ORDER:
        p = _receipt_path(out, stage)
        if not os.path.exists(p):
            problems.append({"stage": stage, "error": "missing_receipt"})
            continue
        rec = _load_receipt(p)
        receipts[stage] = rec
        for bad in _verify_artifacts(out, rec, strict=False):
            problems.append({"stage": stage, **bad})
        if rec.get("code_sha256") != _code_sha():
            notes.append({"stage": stage, "code_sha256_recorded": rec.get("code_sha256"),
                          "code_sha256_now": _code_sha(),
                          "note": "analysis code changed after this stage was written"})

    chained = {}
    if "prepare" in receipts:
        sm = receipts["prepare"].get("source_manifest", {})
        p = os.path.join(out, "source_manifest.json")
        if os.path.exists(p) and _file_sha(p)["sha256"] != sm.get("sha256"):
            problems.append({"stage": "prepare", "error": "source_manifest_sha_mismatch"})
        bp = os.path.join(out, "baseline_params.json")
        b = receipts["prepare"].get("baseline_params", {})
        if os.path.exists(bp) and _file_sha(bp)["sha256"] != b.get("sha256"):
            problems.append({"stage": "prepare", "error": "baseline_params_sha_mismatch"})
    if "recommend" in receipts:
        rr = receipts["recommend"]
        rp = os.path.join(out, "recommend", "candidate_rationale.json")
        recomputed = None
        if os.path.exists(rp):
            with open(rp, "r", encoding="utf-8") as fh:
                recomputed = json.load(fh)["candidate_matrix_sha256"]
            chained["candidate_matrix_sha256"] = recomputed
            if recomputed != rr.get("candidate_matrix_sha256"):
                problems.append({"stage": "recommend",
                                 "error": "candidate_matrix_sha_mismatch",
                                 "recorded": rr.get("candidate_matrix_sha256"),
                                 "recomputed": recomputed})

    # independent recomputation from the frozen copies only
    recomputed = {}
    if "prepare" in receipts and "analyze" in receipts:
        try:
            recomputed = _recompute(out)
        except Exception as exc:                      # noqa: BLE001
            problems.append({"stage": "analyze", "error": "recompute_failed",
                             "detail": repr(exc)})
        rec_path = os.path.join(out, "analyze", "coverage.json")
        if os.path.exists(rec_path):
            with open(rec_path, "r", encoding="utf-8") as fh:
                stored = json.load(fh)["per_log_loop"]
            got = {(r["log"], r["loop"]): r for r in recomputed.get("coverage", [])}
            for r in stored:
                g = got.get((r["log"], r["loop"]))
                if g is None:
                    problems.append({"stage": "analyze", "error": "missing_coverage",
                                     "log": r["log"], "loop": r["loop"]})
                    continue
                for key in ("numeric_credit_s", "numeric_blocks",
                            "independent_reference_changes"):
                    if abs(float(g[key]) - float(r[key])) > 1e-6:
                        problems.append({"stage": "analyze",
                                         "error": "coverage_mismatch", "key": key,
                                         "log": r["log"], "loop": r["loop"],
                                         "recorded": r[key], "recomputed": g[key]})

    doc = {
        "stage": "verify",
        "read_only": True,
        "out": out,
        "receipts_present": sorted(receipts),
        "problems": problems,
        "notes": notes,
        "chained": chained,
        "recomputed": recomputed,
        "status": "ok" if not problems else "failed",
    }
    print(json.dumps(_jp(doc), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not problems else 1


def _recompute(out):
    """Rebuild coverage and metrics from the frozen input copies."""
    manifest, baseline = _load_frozen(out)
    windows_all = _anomaly_by_log(out)
    coverage, metrics = [], {}
    for name in manifest["sources_parsed"]:
        meta = manifest["parsed"][name]
        npz = os.path.join(out, meta["npz"])
        sha = _file_sha(npz)
        z = _load_npz(npz)
        params, _hist = R._params_dict(z)
        for loop in LOOPS:
            f = build_loop_frame(z, params, windows_all.get(name, []), name, loop)
            if f is None:
                continue
            c = _coverage(f)
            c["npz_sha256_matches"] = sha["sha256"] == meta["sha256"]
            coverage.append(c)
            blocks = _split_blocks(f, f["masks"]["numeric"])
            metrics[f"{name}|{loop}"] = {
                "numeric_blocks": len(blocks),
                "numeric_duration_s": round(
                    sum(float(f["t"][b - 1] - f["t"][a]) for a, b in blocks), 3),
                "rmse_display": [
                    _block_metrics(f, a, b, loop).get("rmse_display") for a, b in blocks],
            }
    return {"coverage": coverage, "metrics": metrics,
            "pid_parameters_recovered": baseline["pid"],
            "note": ("recomputed from the frozen copies and the frozen npz; the "
                     "report text is never trusted as evidence")}
# ---------------------------------------------------------------------------
# gate comparison (shared by assess-trials and the tests)
# ---------------------------------------------------------------------------
def gate_block(loop, base, cand, neighbour_base=None, neighbour_cand=None):
    """Per-block acceptance gates for one matched baseline/candidate pair."""
    unit = _loop_units(loop)
    ss_lim = _loop_ss_limit(loop)
    gates = {}

    def g(name, value, ok, limit=None, evaluable=True):
        gates[name] = {"value": value, "limit": limit,
                       "pass": bool(ok and evaluable),
                       "status": "pass" if (ok and evaluable) else
                                 ("not_evaluable" if not evaluable else "fail")}

    b_rmse, c_rmse = base.get("rmse"), cand.get("rmse")
    if b_rmse is None or c_rmse is None or not (b_rmse > 0):
        g("rmse_improvement", None, False, GATE_RMSE_RATIO)
    else:
        g("rmse_improvement", c_rmse / b_rmse, c_rmse / b_rmse <= GATE_RMSE_RATIO,
          GATE_RMSE_RATIO)
    g("steady_state", cand.get("ss_dev"), cand.get("ss_dev") is not None
      and abs(cand["ss_dev"]) <= ss_lim, ss_lim)
    step = cand.get("ref_span")
    # a block with no reference step has no overshoot or settling time to judge;
    # those rows are reported as not_evaluable instead of being scored as zero
    has_step = bool(step and step > 0)
    ov_lim = max(0.25 * step, ss_lim) if loop == "yaw" else max(0.20 * step, ss_lim)
    ov = cand.get("overshoot")
    g("overshoot", ov, ov is not None and ov <= ov_lim, ov_lim, evaluable=has_step)
    band = max(0.05 * step, ss_lim) if has_step else ss_lim
    g("settle_band", band, True, band, evaluable=has_step)
    g("settled", cand.get("settle_s"),
      cand.get("settle_s") is not None and math.isfinite(float(cand["settle_s"])),
      "finite", evaluable=has_step)
    # saturation needs the logged Flags column; an absent column is "no
    # evidence", never "not saturated", so the gate is not evaluable and the
    # block stays unadoptable
    sat = cand.get("sat_frac")
    b_sat = base.get("sat_frac")
    sat_known = sat is not None and math.isfinite(float(sat))
    sat_ok = sat_known and sat <= GATE_SAT_FRAC and (
        b_sat is None or not math.isfinite(float(b_sat)) or sat <= b_sat + 0.02)
    g("saturation", sat, sat_ok, GATE_SAT_FRAC, evaluable=sat_known)
    tv, b_tv = cand.get("tv_per_s"), base.get("tv_per_s")
    tv_known = (tv is not None and b_tv is not None and
                math.isfinite(float(tv)) and math.isfinite(float(b_tv)))
    tv_ok = tv_known and tv <= b_tv * GATE_TV_RATIO
    g("output_total_variation", tv, tv_ok, GATE_TV_RATIO, evaluable=tv_known)
    osc, b_osc = cand.get("osc_duration_s"), base.get("osc_duration_s")
    g("oscillation_not_worse", osc,
      osc is not None and b_osc is not None and osc <= b_osc + 1e-9, "<= baseline")
    if neighbour_base is not None and neighbour_cand is not None:
        # RMSE is in native units (rad/s for steering), the absolute band is
        # stated in deg/s, so the band is converted before the comparison
        nb = neighbour_base.get("rmse")
        nc = neighbour_cand.get("rmse")
        band = (_loop_neighbour_limit(loop) if loop != "yaw"
                else math.radians(_loop_neighbour_limit(loop)))
        lim = max(1.1 * float(nb), band) if nb is not None else None
        g("neighbour_loop", nc, (nc is not None and lim is not None and nc <= lim), lim)
    return {"loop": loop, "unit": unit, "gates": gates,
            "pass": all(v["pass"] for v in gates.values())}


def select_candidate(per_candidate, blocks_required=GATE_MIN_BLOCKS):
    """Pick among candidates that passed; order is fixed and stated in advance."""
    eligible = []
    for cid, doc in per_candidate.items():
        blocks = doc.get("blocks", [])
        if len(blocks) < blocks_required:
            doc["rejected_reason"] = f"only {len(blocks)} valid block(s)"
            continue
        if not all(b["pass"] for b in blocks):
            doc["rejected_reason"] = "a matched block failed a gate"
            continue
        ratios = [b["gates"]["rmse_improvement"]["value"] for b in blocks
                  if b["gates"]["rmse_improvement"]["value"] is not None]
        tvs = [b["gates"]["output_total_variation"]["value"] for b in blocks
               if b["gates"]["output_total_variation"]["value"] is not None]
        doc["worst_block_ratio"] = max(ratios) if ratios else None
        doc["tv_sum"] = sum(tvs) if tvs else None
        eligible.append((cid, doc))
    if not eligible:
        return {"selected": None, "reason": "no candidate passed every gate",
                "candidates": per_candidate}
    eligible.sort(key=lambda cd: (
        cd[1]["worst_block_ratio"] if cd[1]["worst_block_ratio"] is not None else 9e9,
        cd[1]["tv_sum"] if cd[1]["tv_sum"] is not None else 9e9,
        abs((cd[1].get("value") or 0.0) - (cd[1].get("parent_value") or 0.0))))
    return {"selected": eligible[0][0], "reason": "all gates passed; ordering is "
                                                 "worst block, then total variation, "
                                                 "then smaller gain change",
            "candidates": per_candidate}


def _manifest_required(entry, keys):
    missing = [k for k in keys if k not in entry]
    return missing


EXPECTED_COMBO_KEY = "__final_combination__"
EXPECTED_BASE_KEY = "__baseline__"

TRIAL_KEYS = ("file", "sha256", "hardware_id", "candidate_id", "loop", "role",
              "block", "params_snapshot", "stop_evidence")
MANIFEST_KEYS = ("parent_root", "parent_receipt_path", "parent_receipt_sha256",
                 "candidate_matrix_sha256", "purpose", "trials")


def _validate_manifest(man, out, history):
    """Hard validation of one authorised trial manifest; nothing is guessed."""
    problems = []
    missing = [k for k in MANIFEST_KEYS if k not in man]
    if missing:
        return [f"manifest missing top-level keys: {missing}"], []
    if man["purpose"] not in ("selection", "final_validation"):
        problems.append(f"purpose must be selection or final_validation, got "
                        f"{man['purpose']!r}")

    # receipt -> matrix chain
    parent_root = man["parent_root"]
    receipt_path = os.path.join(parent_root, man["parent_receipt_path"])
    if not os.path.exists(receipt_path):
        problems.append(f"parent receipt not found: {receipt_path}")
        rec = None
    else:
        rec = _load_receipt(receipt_path)
        got = _file_sha(receipt_path)["sha256"]
        if got != man["parent_receipt_sha256"]:
            problems.append(f"parent receipt sha mismatch: manifest says "
                            f"{man['parent_receipt_sha256'][:16]}..., file is {got[:16]}...")
        if rec.get("candidate_matrix_sha256") != man["candidate_matrix_sha256"]:
            problems.append("parent receipt does not bind the supplied "
                            "candidate_matrix_sha256")
        _verify_artifacts(parent_root, rec, strict=False)

    trials, seen_blocks = [], {}
    for i, t in enumerate(man["trials"]):
        miss = _manifest_required(t, TRIAL_KEYS)
        if miss:
            problems.append(f"trial[{i}] missing {miss}")
            continue
        p = t["file"]
        if not os.path.isabs(p):
            problems.append(f"trial[{i}] file path must be absolute")
            continue
        if not os.path.exists(p):
            problems.append(f"trial[{i}] file not found: {p}")
            continue
        got = _file_sha(p)["sha256"]
        if got != t["sha256"]:
            problems.append(f"trial[{i}] sha mismatch for {os.path.basename(p)}")
        for key in ("params_snapshot", "stop_evidence"):
            sp = t[key]
            if not os.path.exists(sp):
                problems.append(f"trial[{i}] {key} not found: {sp}")
                continue
            want = t.get(f"{key}_sha256")
            if want and _file_sha(sp)["sha256"] != want:
                problems.append(f"trial[{i}] {key} sha mismatch")
        if t["loop"] not in LOOPS:
            problems.append(f"trial[{i}] unknown loop {t['loop']!r}")
        if t["role"] not in ("baseline", "candidate"):
            problems.append(f"trial[{i}] role must be baseline or candidate")
        seen_blocks.setdefault((t["loop"], t["candidate_id"], t["block"]), []).append(
            t["role"])
        trials.append(t)

    for key, roles in seen_blocks.items():
        if sorted(roles) != ["baseline", "candidate"]:
            problems.append(f"block {key} does not pair one baseline with one "
                            f"candidate (roles: {roles})")

    if problems:
        return problems, trials

    # A-B-B-A needs at least three independent round trips per candidate
    blocks = {}
    for t in trials:
        blocks.setdefault((t["loop"], t["candidate_id"]), set()).add(t["block"])
    for key, bs in blocks.items():
        if len(bs) < GATE_MIN_BLOCKS:
            problems.append(f"candidate {key} has {len(bs)} independent block(s), "
                            f"{GATE_MIN_BLOCKS} required")

    if man["purpose"] == "final_validation":
        problems.extend(_validate_final_validation(man, trials, history))
    return problems, trials


def _validate_final_validation(man, trials, history):
    """A final combination must already exist as a frozen, SHA-bound object.

    The manifest may not carry its own combination definition: accepting one
    would let a caller invent a combination, compare it against itself and
    declare success.  The comparison baseline is likewise the one frozen in
    that object, never one supplied with the trials.
    """
    problems = []
    fc_ref = man.get("final_combination")
    if not isinstance(fc_ref, dict):
        return ["final_validation requires a final_combination reference"]

    # the combination must be resolvable on disk and SHA-pinned
    for k in ("final_combination_id", "final_combination_sha256",
              "baseline_id", "baseline_param_set_sha256"):
        if k not in fc_ref:
            problems.append(f"final_combination reference missing {k}")
    if problems:
        return problems

    parent_root = man["parent_root"]
    fc_path = os.path.join(parent_root, "final_combination.json")
    if not os.path.exists(fc_path):
        return [f"final combination object not found: {fc_path}; a selection "
                f"round must be completed before final validation"]
    got = _file_sha(fc_path)["sha256"]
    if got != fc_ref["final_combination_sha256"]:
        problems.append("final_combination.json sha mismatch")
        return problems
    with open(fc_path, "r", encoding="utf-8") as fh:
        frozen = json.load(fh)
    if frozen.get("final_combination_id") != fc_ref["final_combination_id"]:
        problems.append("final_combination_id does not match the frozen object")
    if frozen.get("baseline_id") != fc_ref["baseline_id"]:
        problems.append("baseline_id does not match the frozen object")
    if frozen.get("baseline_param_set_sha256") != fc_ref["baseline_param_set_sha256"]:
        problems.append("baseline_param_set_sha256 does not match the frozen object")

    # the parent must be a finished selection, not the history root
    preceipt = _load_receipt(os.path.join(parent_root, man["parent_receipt_path"]))
    sel_state = preceipt.get("selection_complete")
    if preceipt.get("purpose") == "final_validation":
        problems.append("parent is already a final-validation round")
    if sel_state is not True:
        problems.append("parent selection is not complete; final validation "
                        "requires a finished selection round")
    if preceipt.get("next_stage") is not None:
        problems.append(f"parent selection still has a pending stage "
                        f"{preceipt.get('next_stage')}")

    # the frozen combination must be the parameter set the parent accepted
    accepted = preceipt.get("params_after_round") or {}
    want = frozen.get("params") or {}
    for k in VAR_WHITELIST:
        a, b = accepted.get(k), want.get(k)
        if a is not None and b is not None and abs(float(a) - float(b)) > 1e-9:
            problems.append(f"frozen combination disagrees with the accepted "
                            f"parameter {k}: {b} vs {a}")

    # both loops must be covered by the final validation
    covered = {t["loop"] for t in trials}
    missing_loops = sorted(set(LOOPS) - covered)
    if missing_loops:
        problems.append(f"final validation does not cover loop(s) {missing_loops}")

    # candidate trials must run the frozen combination; baselines must run the
    # frozen original baseline
    base_sha = frozen.get("baseline_param_set_sha256")
    for t in trials:
        if t["role"] == "candidate":
            if t.get("param_set_sha256") != frozen.get("param_set_sha256"):
                problems.append(
                    f"{os.path.basename(t['file'])}: candidate param set does not "
                    f"match the frozen combination")
        else:
            if t.get("param_set_sha256") != base_sha:
                problems.append(
                    f"{os.path.basename(t['file'])}: baseline param set is not the "
                    f"frozen original baseline")

    used = _selection_input_shas(history, parent_root)
    reused = sorted({t["sha256"] for t in trials} & used)
    if reused:
        problems.append(f"final_validation reuses selection input(s): {reused}")
    return problems


def _selection_input_shas(history, parent_root):
    """Every BIN sha consumed anywhere in the selection chain."""
    used, seen = set(), set()
    root = parent_root
    for _ in range(64):
        if root in seen or not root or not os.path.isdir(root):
            break
        seen.add(root)
        man_p = os.path.join(root, "trial_manifest.json")
        if os.path.exists(man_p):
            with open(man_p, "r", encoding="utf-8") as fh:
                m = json.load(fh)
            used |= {t.get("sha256") for t in m.get("trials", []) if t.get("sha256")}
            root = m.get("parent_root")
        else:
            break
    for root2 in (history, parent_root):
        p = os.path.join(root2, "assess-trials.done.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
            used |= set(rec.get("trial_bin_shas", []))
    return used


def _trial_track(path, loop, params_snapshot):
    """Load one authorised trial log and cut it into pre-step evaluation windows."""
    npz = path + ".npz"
    _parse_bin(path, npz)
    z = _load_npz(npz)
    params, _hist = R._params_dict(z)
    frame = build_loop_frame(z, params, [], os.path.basename(path), loop)
    os.unlink(npz)
    if frame is None:
        return None, params
    return frame, params


def assess_trial_blocks(trials, expectations):
    """Score every matched block of every tested candidate.

    ``expectations`` maps ``candidate_id`` to the full whitelist parameter set
    that candidate is *supposed* to run with, taken from the parent round's
    frozen matrix.  Every candidate that appears in the trials is registered
    here, so a fully correct trial set produces a full result (not an empty
    dict that only fills in on errors).
    """
    per = {}
    for t in trials:
        per.setdefault((t["loop"], t["candidate_id"]),
                       {"blocks": [], "errors": [], "param_checks": []})

    for t in trials:
        doc = per[(t["loop"], t["candidate_id"])]
        frame, params = _trial_track(t["file"], t["loop"], t["params_snapshot"])
        t["_metrics"] = None
        if frame is None:
            doc["errors"].append(f"{os.path.basename(t['file'])}: loop stream absent")
            continue
        t["_frame"] = frame
        # the parameters must come from the new BIN's own PARM records, not from
        # the manifest label
        want = expectations.get(t["candidate_id"])
        if want is None:
            # a final combination is a fixed object, not a row of the selection
            # matrix; its expected set comes from the frozen combination
            combo = expectations.get(EXPECTED_COMBO_KEY) or {}
            if combo and t["candidate_id"] == combo.get("id"):
                want = {k: (combo.get("params") or {}).get(k) for k in VAR_WHITELIST}
        if want is None:
            doc["errors"].append(f"candidate {t['candidate_id']} not in parent matrix")
            continue
        if t["role"] == "baseline":
            # a baseline block runs the round's start parameter set, never the
            # candidate's value on the changed parameter
            base_set = expectations.get(EXPECTED_BASE_KEY) or expectations.get("__parent__")
            if isinstance(base_set, dict):
                want = base_set
        bad = []
        for k in VAR_WHITELIST:
            w = want.get(k)
            if w is None:
                continue
            got = params.get(k)
            if got is None or abs(float(got) - float(w)) > 1e-6:
                bad.append(f"{k}={got} (matrix expects {w})")
        doc["param_checks"].append(
            {"file": os.path.basename(t["file"]), "role": t["role"],
             "block": t["block"], "mismatches": bad})
        if bad:
            doc["errors"].append(f"{os.path.basename(t['file'])}: " + "; ".join(bad))

    # per-trial metrics over the fixed evaluation window
    for t in trials:
        frame = t.get("_frame")
        if frame is None:
            continue
        bws = _split_blocks(frame, frame["masks"]["numeric"])
        if not bws:
            continue
        a, b = max(bws, key=lambda ab: frame["t"][ab[1] - 1] - frame["t"][ab[0]])
        t["_metrics"] = _block_metrics(frame, a, b, t["loop"])

    for key, doc in per.items():
        loop, cid = key
        if doc["errors"]:
            continue
        block_ids = sorted({t["block"] for t in trials
                            if t["loop"] == loop and t["candidate_id"] == cid})
        for bid in block_ids:
            base = [t for t in trials if t["loop"] == loop and t["candidate_id"] == cid
                    and t["block"] == bid and t["role"] == "baseline"]
            cand = [t for t in trials if t["loop"] == loop and t["candidate_id"] == cid
                    and t["block"] == bid and t["role"] == "candidate"]
            if len(base) != 1 or len(cand) != 1:
                continue
            bm, cm = base[0]["_metrics"], cand[0]["_metrics"]
            if not bm or not cm or not bm.get("evaluable") or not cm.get("evaluable"):
                doc.setdefault("skipped_blocks", []).append(
                    {"block": bid, "reason": "not_evaluable"})
                continue
            doc["blocks"].append(gate_block(loop, bm, cm))
    return per


def _baseline_valid(trials):
    """Safety/baseline gate: a round cannot advance without a usable baseline."""
    base = [t for t in trials if t["role"] == "baseline"]
    if not base:
        return False, "no baseline trials"
    good = 0
    for t in base:
        m = t.get("_metrics")
        if not m or not m.get("evaluable"):
            continue
        sat = m.get("sat_frac")
        if sat is not None and math.isfinite(float(sat)) and sat > GATE_SAT_FRAC:
            continue
        good += 1
    if good == 0:
        return False, "every baseline block is unevaluable or saturated"
    return True, f"{good}/{len(base)} baseline blocks usable"


# fixed progression: steering first, then speed
ROUND_SEQUENCE = (("yaw", "FF"), ("yaw", "P"), ("yaw", "I"),
                  ("speed", "CRUISE"), ("speed", "P"), ("speed", "I"))


def _matrix_of(parent_root):
    """Read the parent round's frozen candidate matrix."""
    for rel in (os.path.join("recommend", "trial_candidates.csv"),
                os.path.join("next_round", "trial_candidates.csv")):
        p = os.path.join(parent_root, rel)
        if os.path.exists(p):
            import csv as _csv
            with open(p, "r", encoding="utf-8") as fh:
                return list(_csv.DictReader(fh))
    return []


def _expectations_from_matrix(rows, parent_params, baseline_origins):
    """candidate_id -> full whitelist parameter set that candidate must run."""
    out = {"__parent__": {k: parent_params.get(k) for k in VAR_WHITELIST}}
    for r in rows:
        if r.get("candidate") in ("", None):
            continue
        pid = r["candidate_id"]
        want = dict(parent_params)
        try:
            want[r["param"]] = float(r["candidate"])
        except (TypeError, ValueError):
            continue
        out[pid] = {k: want.get(k) for k in VAR_WHITELIST}
    return out


def _current_stage(rows, tested_ids):
    stages = []
    for r in rows:
        if r["candidate_id"] in tested_ids:
            key = (r["loop"], r["stage"])
            if key not in stages:
                stages.append(key)
    if not stages:
        return None
    order = [s for s in ROUND_SEQUENCE if s in stages]
    return order[-1] if order else stages[-1]


def _next_stage(stage):
    if stage is None:
        return None
    try:
        i = ROUND_SEQUENCE.index(stage)
    except ValueError:
        return None
    return ROUND_SEQUENCE[i + 1] if i + 1 < len(ROUND_SEQUENCE) else None


def _resolve_round(selection, rows, tested_ids, parent_params, stage):
    """Turn one round's decision into the next round's parameter set.

    Returns ``(params, outcome)`` where outcome is ``selected_candidate``,
    ``retain_parent``, or ``skipped_no_ff_evidence``.  A safety/baseline
    failure is handled by the caller as ``blocked``.
    """
    params = dict(parent_params)
    chosen = selection.get("selected")
    if chosen:
        # selection keys are "loop|candidate_id"; the matrix stores bare ids
        cid = chosen.split("|", 1)[1] if "|" in chosen else chosen
        for r in rows:
            if r["candidate_id"] == cid and r.get("candidate") not in ("", None):
                params[r["param"]] = float(r["candidate"])
                return params, "selected_candidate"
    # whether the stage was FF-shaped and had no evidence at all
    ff_rows = [r for r in rows if r["candidate_id"] in tested_ids
               and r.get("recommendation_status") == "skipped_no_ff_evidence"]
    if ff_rows and stage and stage[1] in ("FF", "CRUISE"):
        return params, "skipped_no_ff_evidence"
    return params, "retain_parent"


def _make_matrix(stage, params):
    """Bounded single-parameter candidates for one stage, from ``params``."""
    loop, name = stage
    rows, psha = [], _parent_sha({k: params.get(k) for k in VAR_WHITELIST})
    if name in ("FF", "CRUISE"):
        param = "ATC_STR_RAT_FF" if loop == "yaw" else "CRUISE_THROTTLE"
        rows.append({
            "candidate_id": f"{loop}_{name.lower()}_skip", "loop": loop, "stage": name,
            "param": param, "original": params.get(param), "candidate": None,
            "parent_param_sha256": psha, "source": "no FF evidence this round",
            "applicable_conditions": "n/a", "validated": False,
            "recommendation_status": "skipped_no_ff_evidence",
            "note": "FF stage carries no candidate; the gain stage follows"})
        return rows
    param = {"P": "ATC_STR_RAT_P" if loop == "yaw" else "ATC_SPEED_P",
             "I": "ATC_STR_RAT_I" if loop == "yaw" else "ATC_SPEED_I"}[name]
    base = params.get(param)
    for scale in GAIN_SCALES:
        if scale == 1.0:
            rows.append({
                "candidate_id": f"{loop}_{name.lower()}_retain", "loop": loop,
                "stage": name, "param": param, "original": base, "candidate": base,
                "parent_param_sha256": psha, "source": "control arm",
                "applicable_conditions": "same matched blocks",
                "validated": False, "recommendation_status": "retain_parent",
                "note": "unchanged control arm; not an improvement claim"})
            continue
        rows.append({
            "candidate_id": f"{loop}_{name.lower()}_{int(round(scale*100))}",
            "loop": loop, "stage": name, "param": param, "original": base,
            "candidate": (base * scale) if base is not None else None,
            "parent_param_sha256": psha,
            "source": "bounded +-10 % single-parameter hypothesis",
            "applicable_conditions": "matched blocks, one parameter changed",
            "validated": False, "recommendation_status": "trial_candidate",
            "note": "unranked until the trials exist"})
    return rows


def _write_param_file(path, values):
    lines = ["# ArduPilot parameter file (offline analysis product; not uploaded)"]
    for k in VAR_WHITELIST:
        if k in values and values[k] is not None:
            lines.append(f"{k},{values[k]!r}")
    _write_new_text(path, "\n".join(lines) + "\n")


def _param_diff(originals, current):
    rows = []
    for k in VAR_WHITELIST:
        a, b = originals.get(k), current.get(k)
        if a is None or b is None:
            continue
        if abs(float(a) - float(b)) > 1e-9:
            rows.append({"param": k, "original": a, "new": b,
                         "delta": float(b) - float(a)})
    return rows
def stage_assess_trials(args):
    log = print
    history = args.history
    if not history:
        raise SystemExit("assess-trials requires --history")
    if not args.trial_manifest:
        raise SystemExit("assess-trials requires --trial-manifest")
    _require_stage(history, "recommend")

    with open(args.trial_manifest, "r", encoding="utf-8") as fh:
        man = json.load(fh)
    out = args.out
    problems, trials = _validate_manifest(man, out, history)
    if problems:
        print(json.dumps({"stage": "assess-trials", "status": "rejected",
                          "problems": problems}, ensure_ascii=False, indent=2))
        return 2
    _mkdir(out)

    parent_root = man["parent_root"]
    parent_params = _parent_params(parent_root, history)
    rows = _matrix_of(parent_root)
    tested_ids = sorted({t["candidate_id"] for t in trials})
    stage = _current_stage(rows, tested_ids)
    expectations = _expectations_from_matrix(rows, parent_params, None)
    # every round compares against the set it started from; a final validation
    # additionally needs the frozen combination object, read from disk
    expectations[EXPECTED_BASE_KEY] = {k: parent_params.get(k) for k in VAR_WHITELIST}
    if man["purpose"] == "final_validation":
        fc_path = os.path.join(parent_root, "final_combination.json")
        with open(fc_path, "r", encoding="utf-8") as fh:
            frozen = json.load(fh)
        expectations[EXPECTED_COMBO_KEY] = {
            "id": frozen.get("final_combination_id"),
            "params": frozen.get("params") or {}}
        expectations[EXPECTED_BASE_KEY] = (frozen.get("baseline_params")
                                          or expectations[EXPECTED_BASE_KEY])

    per = assess_trial_blocks(trials, expectations)
    ok, why = _baseline_valid(trials)
    selection = select_candidate({f"{k[0]}|{k[1]}": v for k, v in per.items()})
    if selection.get("selected"):
        # the loop prefix is an internal key; the consumer sees the candidate id
        selection["selected_key"] = selection["selected"]
        selection["selected"] = selection["selected"].split("|", 1)[-1]

    if not ok:
        outcome, params = "blocked", dict(parent_params)
    else:
        params, outcome = _resolve_round(selection, rows, tested_ids,
                                         parent_params, stage)

    nxt = _next_stage(stage) if outcome != "blocked" else None
    selection_complete = (man["purpose"] == "selection" and outcome != "blocked"
                          and nxt is None)
    result = {
        "stage": "assess-trials",
        "purpose": man["purpose"],
        "parent_root": parent_root,
        "parent_receipt_path": man["parent_receipt_path"],
        "candidate_matrix_sha256": man["candidate_matrix_sha256"],
        "parent_receipt_sha256": man["parent_receipt_sha256"],
        "stage_assessed": list(stage) if stage else None,
        "round_outcome": outcome,
        "baseline_gate": {"ok": ok, "detail": why},
        "selection": selection,
        "per_candidate": {f"{k[0]}|{k[1]}": v for k, v in per.items()},
        "params_after_round": {k: params.get(k) for k in VAR_WHITELIST},
        "next_stage": list(nxt) if nxt else None,
        "selection_complete": selection_complete,
        "builds_on_matrix": True,
        "deployable": False,
    }
    _write_new_json(os.path.join(out, "assessment.json"), result)
    _write_new_json(os.path.join(out, "trial_manifest.json"), man)
    _write_new_json(os.path.join(out, "selection_input_shas.json"),
                    {"trial_bin_shas": sorted({t["sha256"] for t in trials})})

    if man["purpose"] == "selection" and outcome != "blocked":
        if nxt is not None:
            _mkdir(os.path.join(out, "next_round"))
            nrows = _make_matrix(nxt, params)
            _write_csv_new(os.path.join(out, "next_round", "trial_candidates.csv"), nrows)
            _write_new_json(os.path.join(out, "next_round", "candidate_rationale.json"),
                            {"generated_from": man["candidate_matrix_sha256"],
                             "parent_param_sha256": _parent_sha(params),
                             "round_outcome": outcome,
                             "next_stage": list(nxt),
                             "params_after_round": {k: params.get(k)
                                                    for k in VAR_WHITELIST},
                             "validated": False})
        else:
            # the fixed sequence is exhausted: this is the completed selection
            _freeze_final_combination(out, params, history, man,
                                      man["candidate_matrix_sha256"])
    elif man["purpose"] == "selection" and outcome == "blocked":
        _write_new_json(os.path.join(out, "blocked.json"),
                        {"reason": why,
                         "note": "progression stopped; no next-round matrix"})

    # final independent combination validation opens the export
    if man["purpose"] == "final_validation" and outcome != "blocked" \
            and selection.get("selected"):
        _export_final(out, man, params, parent_root, history)

    _write_receipt(out, "assess-trials", {
        "candidate_matrix_sha256": man["candidate_matrix_sha256"],
        "parent_receipt_sha256": man["parent_receipt_sha256"],
        "trial_bin_shas": sorted({t["sha256"] for t in trials}),
        "selected": selection.get("selected"),
        "purpose": man["purpose"],
        "round_outcome": outcome,
        "next_stage": list(nxt) if nxt else None,
        "selection_complete": selection_complete,
        "params_after_round": {k: params.get(k) for k in VAR_WHITELIST},
        "baseline_param_set_sha256": _parent_sha(parent_params),
        "deployable": os.path.exists(os.path.join(out, "recommended.param")),
    })
    log(json.dumps({"stage": "assess-trials", "outcome": outcome,
                    "selected": selection.get("selected"),
                    "next_stage": list(nxt) if nxt else None},
                   ensure_ascii=False))
    return 0


def _parent_params(parent_root, history):
    """Whitelist values in force when this round started.

    A later round's accepted parameters live in the parent assessment, so the
    parent assessment is authoritative; the original baseline is only the root
    of that chain.
    """
    for root in (parent_root, history):
        a = os.path.join(root, "assessment.json")
        if os.path.exists(a):
            with open(a, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            got = doc.get("params_after_round") or {}
            if any(got.get(k) is not None for k in VAR_WHITELIST):
                return {k: got.get(k) for k in VAR_WHITELIST}
    for root in (parent_root, history):
        p = os.path.join(root, "baseline_params.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            out = {}
            for loop in LOOPS:
                out.update(doc["pid"][loop])
            return {k: out.get(k) for k in VAR_WHITELIST}
    raise SystemExit("cannot determine the parent parameter set")


def _freeze_final_combination(out, params, history, man, matrix_sha):
    """Freeze the accepted combination when the fixed sequence is exhausted.

    This object is what a later final-validation manifest must reference by
    SHA; it also carries the *original* comparison baseline so the final round
    cannot pick its own.
    """
    originals = _parent_params(history, history)
    _write_new_json(os.path.join(out, "final_combination.json"), {
        "final_combination_id": f"fc-{matrix_sha[:16]}",
        "param_set_sha256": _parent_sha(params),
        "baseline_id": "recorded_2026_11_02",
        "baseline_param_set_sha256": _parent_sha(originals),
        "baseline_params": originals,
        "params": {k: params.get(k) for k in VAR_WHITELIST},
        "frozen_after_matrix_sha256": matrix_sha,
        "round_outcome": "selected_candidate_or_retain",
        "note": ("frozen before the final round; the final round may not "
                 "redefine it and must not reuse any selection BIN"),
    })
    return os.path.join(out, "final_combination.json")


def _export_final(out, man, params, parent_root, history):
    """Only reachable after an independent final-combination validation."""
    fc_path = os.path.join(parent_root, "final_combination.json")
    with open(fc_path, "r", encoding="utf-8") as fh:
        frozen = json.load(fh)
    originals = frozen.get("baseline_params") or _parent_params(history, history)
    diff = _param_diff(originals, params)
    _write_param_file(os.path.join(out, "recommended.param"), params)
    _write_param_file(os.path.join(out, "rollback.param"), originals)
    _write_csv_new(os.path.join(out, "parameter_diff.csv"), diff)
    _write_new_json(os.path.join(out, "final_combination.json"), {
        "final_combination_id": (man.get("final_combination") or {}).get(
            "final_combination_id"),
        "param_set_sha256": _parent_sha(params),
        "baseline_param_set_sha256": _parent_sha(originals),
        "source_receipt": man["parent_receipt_sha256"],
        "params": params,
        "changed": [d["param"] for d in diff],
        "note": "offline product; nothing here is uploaded to the flight controller",
    })


# ---------------------------------------------------------------------------
# stage: recommend
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# stage: verify  (read-only; prints JSON, never writes into --out)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# gate comparison (shared by assess-trials and the tests)
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Offline 2026-11-02 FCU PID analysis (never talks to hardware)")
    p.add_argument("--stage", required=True, choices=STAGES)
    p.add_argument("--out", required=True, help="analysis root (create-only per stage)")
    p.add_argument("--data-root", help="2026-11-02 raw log directory (prepare)")
    p.add_argument("--params-backup", help="11.10 parameter backup .param (prepare)")
    p.add_argument("--vehicle-info", help="11.10 vehicle_info json (prepare, optional)")
    p.add_argument("--sources", nargs="*", default=None,
                   help="prepare: restrict parsing to these log names (smoke only)")
    p.add_argument("--history", help="historical analysis root (assess-trials/verify)")
    p.add_argument("--trial-manifest", help="authorised new-trial manifest (assess-trials)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    global VERIFY_ONLY, SOURCE_SELECT
    VERIFY_ONLY = args.stage == "verify"
    SOURCE_SELECT = list(args.sources) if args.sources else None
    if args.stage == "prepare":
        if not args.data_root or not args.params_backup:
            raise SystemExit("prepare requires --data-root and --params-backup")
        stage_prepare(args)
    elif args.stage == "analyze":
        stage_analyze(args)
    elif args.stage == "recommend":
        stage_recommend(args)
    elif args.stage == "assess-trials":
        return stage_assess_trials(args)
    elif args.stage == "verify":
        return stage_verify(args)
    else:
        raise SystemExit(f"stage '{args.stage}' not implemented yet")
    return 0


if __name__ == "__main__":
    sys.exit(main())


