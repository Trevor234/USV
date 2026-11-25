#!/usr/bin/env python3
"""Parse ArduPilot DataFlash .bin logs into per-message npz arrays.

Usage: python3 parse_log.py <bin_file> <out_npz>

Keys are dotted ``<TYPE>.<FIELD>``; missing messages yield empty arrays and
missing fields yield NaN (never a fabricated "normal" value).  String-valued
fields (PARM.Name, MODE.Mode, MSG.Message) are stored as object arrays.
"""
import sys

import numpy as np
from pymavlink.DFReader import DFReader_binary

# message type -> numeric fields to extract (TimeUS included explicitly)
NUM_FIELDS = {
    "IMU": ["TimeUS", "I", "GyrX", "GyrY", "GyrZ", "AccX", "AccY", "AccZ"],
    "ESC": ["TimeUS", "Instance", "RPM", "RawRPM", "Volt", "Curr", "Temp", "Err"],
    "RCOU": ["TimeUS"] + [f"C{i}" for i in range(1, 17)],
    "RCIN": ["TimeUS"] + [f"C{i}" for i in range(1, 17)],
    "GPS": ["TimeUS", "I", "Status", "NSats", "HDop", "Lat", "Lng", "Alt", "Spd", "GCrs", "Yaw"],
    "POS": ["TimeUS", "Lat", "Lng", "Alt"],
    "ATT": ["TimeUS", "DesYaw", "Yaw", "DesPitch", "Pitch", "DesRoll", "Roll"],
    "XKF1": ["TimeUS", "C", "Yaw", "Roll", "Pitch", "VN", "VE", "VD", "PN", "PE", "PD"],
    "XKF2": ["TimeUS", "C", "AX", "AY", "AZ", "VWN", "VWE"],
    "XKF4": ["TimeUS", "C", "PI", "FS", "TS", "SS", "GPS"],
    "STER": ["TimeUS", "DesTurnRate", "TurnRate", "DesLatAcc", "LatAcc"],
    "THR": ["TimeUS", "ThrIn", "ThrOut", "DesSpeed", "Speed"],
    # Clip0/1/2 exist on older firmware; newer firmware logs a single Clip.
    "VIBE": ["TimeUS", "IMU", "VibeX", "VibeY", "VibeZ", "Clip", "Clip0", "Clip1", "Clip2"],
    "NTUN": ["TimeUS", "WpDist", "XTrack"],
    "PIDS": ["TimeUS", "Tar", "Act", "Err"],
    "PIDA": ["TimeUS", "Tar", "Act", "Err"],
    "AHR2": ["TimeUS", "Roll", "Pitch", "Yaw", "Lat", "Lng"],
    "MAG": ["TimeUS", "MagX", "MagY", "MagZ"],
    "BARO": ["TimeUS", "Alt", "Press", "Temp"],
    "DCM": ["TimeUS", "Roll", "Pitch", "Yaw"],
    "ARM": ["TimeUS", "ArmState", "ArmChecks", "Forced", "Method"],
    "EV": ["TimeUS", "Id"],
    "ERR": ["TimeUS", "Subsys", "ECode"],
    "BAT": ["TimeUS", "Inst", "Volt", "Curr", "CurrTot", "RemPct", "Temp"],
    "MODE": ["TimeUS", "ModeNum", "Rsn"],
    "PARM": ["TimeUS", "Value", "Default"],
}

# message type -> string-valued fields
STR_FIELDS = {
    "MODE": ["Mode"],
    "MSG": ["Message"],
    "PARM": ["Name"],
}

STR_MSGS = set(STR_FIELDS) | {t for t, fs in STR_FIELDS.items()}


def parse(bin_path, out_path):
    """Parse one DataFlash log.

    Returns ``(n_msg, summary, field_report)`` where ``summary`` maps message
    type to record count and ``field_report`` maps message type to the subset of
    requested fields actually present in that log's FMT definitions.
    """
    reader = DFReader_binary(bin_path)
    want = set(NUM_FIELDS) | set(STR_MSGS)
    num_cols = {t: {f: [] for f in fs} for t, fs in NUM_FIELDS.items()}
    str_cols = {t: {f: [] for f in fs} for t, fs in STR_FIELDS.items()}
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
        names = m.get_fieldnames()
        if t not in present:
            present[t] = set(names)
        for f in NUM_FIELDS.get(t, ()):
            try:
                num_cols[t][f].append(float(getattr(m, f)))
            except Exception:
                num_cols[t][f].append(np.nan)
        for f in STR_FIELDS.get(t, ()):
            try:
                str_cols[t][f].append(str(getattr(m, f)))
            except Exception:
                str_cols[t][f].append("")

    out = {}
    for t, fs in NUM_FIELDS.items():
        for f in fs:
            out[f"{t}.{f}"] = np.asarray(num_cols[t][f], dtype=np.float64)
    for t, fs in STR_FIELDS.items():
        for f in fs:
            out[f"{t}.{f}"] = np.asarray(str_cols[t][f], dtype=object)
    np.savez_compressed(out_path, **out)

    summary = {t: len(num_cols[t]["TimeUS"]) for t in NUM_FIELDS}
    for t, fs in STR_FIELDS.items():
        summary[t] = len(str_cols[t][fs[0]])
    field_report = {
        t: {f: (f in present.get(t, set())) for f in (NUM_FIELDS.get(t, []) + STR_FIELDS.get(t, []))}
        for t in NUM_FIELDS
    }
    return n_msg, summary, field_report


if __name__ == "__main__":
    bin_path, out_path = sys.argv[1], sys.argv[2]
    n_msg, summary, _ = parse(bin_path, out_path)
    big = {k: v for k, v in summary.items() if v > 0}
    print(f"{bin_path}: {n_msg} msgs parsed -> {out_path}")
    for k, v in sorted(big.items(), key=lambda x: -x[1]):
        print(f"  {k:6s} {v}")
