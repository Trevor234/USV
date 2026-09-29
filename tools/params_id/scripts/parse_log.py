#!/usr/bin/env python3
"""Parse ArduPilot DataFlash .bin logs into per-message npz arrays.

Usage: python3 parse_log.py <bin_file> <out_npz>
Identified-message extraction for USV parameter identification (2026-09-03 data).
"""
import sys
import numpy as np
from pymavlink.DFReader import DFReader_binary

# message type -> fields to extract (all prefixed TimeUS unless noted)
FIELDS = {
    "IMU":  ["TimeUS", "GyrX", "GyrY", "GyrZ", "AccX", "AccY", "AccZ"],
    "ESC":  ["TimeUS", "Instance", "RPM", "RawRPM", "Volt", "Curr", "Err"],
    "RCOU": ["TimeUS", "C1", "C3"],
    "RCIN": ["TimeUS", "C1", "C3"],
    "GPS":  ["TimeUS", "Status", "NSats", "HDop", "Lat", "Lng"],
    "POS":  ["TimeUS", "Lat", "Lng"],
    "ATT":  ["TimeUS", "DesYaw", "Yaw", "DesPitch", "Pitch"],
    "XKF1": ["TimeUS", "C", "Yaw", "VN", "VE", "VD"],
    "XKF2": ["TimeUS", "C", "AX", "AY", "AZ"],
    "STER": ["TimeUS", "DesTurnRate", "TurnRate", "DesLatAcc", "LatAcc"],
    "THR":  ["TimeUS", "ThrIn", "ThrOut", "DesSpeed", "Speed"],
    "VIBE": ["TimeUS", "Clip"],
    "NTUN": ["TimeUS", "WpDist", "XTrack"],
    "PIDS": ["TimeUS", "Tar", "Act", "Err"],
    "PIDA": ["TimeUS", "Tar", "Act", "Err"],
    "AHR2": ["TimeUS", "Roll", "Pitch", "Yaw", "Lat", "Lng"],
    "MAG":  ["TimeUS", "MagX", "MagY", "MagZ"],
    "BARO": ["TimeUS", "Alt", "Press", "Temp"],
    "DCM":  ["TimeUS", "Roll", "Pitch", "Yaw"],
}
STR_MSGS = {"MODE": ["TimeUS", "Mode"]}  # string-valued message


def parse(bin_path, out_path):
    reader = DFReader_binary(bin_path)
    cols = {t: {f: [] for f in fs} for t, fs in FIELDS.items()}
    scol = {t: {"TimeUS": [], "Mode": []} for t, fs in STR_MSGS.items()}
    types_want = set(FIELDS) | set(STR_MSGS)
    n_msg = 0
    while True:
        m = reader.recv_match()
        if m is None:
            break
        n_msg += 1
        t = m.get_type()
        if t not in types_want:
            continue
        if t in STR_MSGS:
            try:
                scol[t]["TimeUS"].append(float(getattr(m, "TimeUS")))
                scol[t]["Mode"].append(str(getattr(m, "Mode")))
            except Exception:
                pass
            continue
        if t not in FIELDS:
            continue
        for f in FIELDS[t]:
            try:
                cols[t][f].append(float(getattr(m, f)))
            except Exception:
                cols[t][f].append(np.nan)
    out = {}
    for t, fs in FIELDS.items():
        for f, v in fs and cols[t].items():
            out[f"{t}.{f}"] = np.asarray(v, dtype=np.float64)
    for t in STR_MSGS:
        out[f"{t}.TimeUS"] = np.asarray(scol[t]["TimeUS"], dtype=np.float64)
        out[f"{t}.Mode"] = np.asarray(scol[t]["Mode"])
    np.savez_compressed(out_path, **out)
    summary = {t: len(cols[t]["TimeUS"]) for t in FIELDS}
    summary.update({t: len(scol[t]["TimeUS"]) for t in STR_MSGS})
    return n_msg, summary


if __name__ == "__main__":
    bin_path, out_path = sys.argv[1], sys.argv[2]
    n_msg, summary = parse(bin_path, out_path)
    big = {k: v for k, v in summary.items() if v > 0}
    print(f"{bin_path}: {n_msg} msgs parsed -> {out_path}")
    for k, v in sorted(big.items(), key=lambda x: -x[1]):
        print(f"  {k:6s} {v}")
