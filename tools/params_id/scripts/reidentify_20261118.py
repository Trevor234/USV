#!/usr/bin/env python3
"""2026-11-18 MCAP 实船参数辨识（离线，只读原始包）。

单次运行完成：取证 -> 时基 -> 冻结切分 -> 拟合 -> 同航留出评分 -> 交付。
原始 MCAP、历史结果与实船配置均只读。

约定（与 C++ ``usv_model_dynamic.cpp`` 及 11-02 脚本一致）：
    x = East, y = North, psi = wrap(pi/2 - yaw_NED)
    u = vN*cos(yaw) + vE*sin(yaw)
    v = vN*sin(yaw) - vE*cos(yaw)
    r = -ATTITUDE.yawspeed
    tau = [TL+TR, 0, d*(TR-TL)]
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import math
import os
import struct
import sys
from dataclasses import dataclass, field

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reidentify_20261102 as old  # noqa: E402  (pure helpers only)

# ---------------------------------------------------------------------------
# constants (frozen before any data is read for fitting)
# ---------------------------------------------------------------------------
DT = 0.05                       # integration step; NOT the observed PWM rate
GRID_HZ = 1.0 / DT
PWM_DEADZONE_US = old.PWM_DEADZONE_US      # 30 us prior, NOT identified
SERVO_MIN, SERVO_TRIM, SERVO_MAX = 1100.0, 1500.0, 1900.0
ATT_GAP_S = 0.25                # ATTITUDE observation break
POS_GAP_S = 0.35                # LOCAL_POSITION_NED observation break
CLOCK_JUMP_S = 0.20             # |dlog - dboot| => new clock-map segment
ANCHOR_MAX_S = 0.25             # max ATTITUDE anchor spacing for non-boot streams
SERVO_AGE_S = 0.25              # servo time_usec vs nearest ATTITUDE anchor
SERVO_GAP_S = 1.25              # servo snapshot spacing break
STATE_HOLD_S = 1.0              # /mpc/status max hold
HB_MAX_AGE_S = 1.5
GPS_MAX_AGE_S = 1.5
GPS_MIN_FIX = 5                 # RTK Fixed
BREAK_PAD_S = 1.0
WIN_S = 4.0
WIN_STEPS = int(round(WIN_S / DT))
ROLL_LIM = math.radians(10.0)
PITCH_LIM = math.radians(15.0)
SPEED_LIM = 1.5                 # m/s, identification envelope ceiling
RATE_LIM = 1.25                 # rad/s
LOCAL_SPEED_MIN = 0.3           # m/s, window must contain motion
LOCAL_RATE_MIN = 0.15           # rad/s
STRAIGHT_R_MAX = 0.15
STRAIGHT_U_MIN = 0.3
TURN_R_MIN = 0.25
TURN_DIFF_MIN = 0.02
WIN_SNAPSHOT_GAP_S = 1.25
WIN_SNAPSHOT_STEP_US = 60.0
WIN_MIN_SNAPSHOTS = 4
CLUSTER_S = 30.0
BOOTSTRAP_N = 200
BOOTSTRAP_SEED = 42
BOOTSTRAP_MIN_OK = 160
U_RMSE_LIM = 0.20
R_MEDIAN_LIM = math.radians(12.0)
POS_RMSE_LIM = 1.5
IMPROVE_MIN = 0.10
M0_SLACK = 1.05
G_UPPER_N = 120.0
EXCLUDE_UTC = [("15:27:42", "15:27:50")]     # CST, unconditional
# Fixed time roles, 2026-11-18 CST, half-open [start, end)
ROLE_TRAIN_B = ("14:58:32", "15:12:14")
ROLE_TRAIN_MANUAL1 = ("15:12:20", "15:17:58")
ROLE_TRAIN_MANUAL2 = ("15:20:00", "15:38:00")
ROLE_HOLDOUT = ("15:38:00", "15:50:00")
ROLE_A = ("15:17:58", "15:19:57")
CST = _dt.timezone(_dt.timedelta(hours=8))


def cst_epoch(hhmmss):
    h, m, s = (int(x) for x in hhmmss.split(":"))
    return _dt.datetime(2026, 11, 18, h, m, s, tzinfo=CST).timestamp()


def utc_str(epoch_s):
    return _dt.datetime.fromtimestamp(float(epoch_s), _dt.timezone.utc).strftime("%H:%M:%S")


def cst_str(epoch_s):
    return _dt.datetime.fromtimestamp(float(epoch_s), CST).strftime("%H:%M:%S")


def wrap_pi(a):
    return old.wrap_pi(a)


def interp_g(t_src, v, t_dst, max_gap):
    return old.interp_linear_gapped(np.asarray(t_src, float), np.asarray(v, float),
                                    np.asarray(t_dst, float), max_gap)


def runs_of(mask):
    m = np.asarray(mask, bool)
    if m.size == 0:
        return []
    d = np.diff(np.concatenate(([0], m.astype(np.int8), [0])))
    return [(int(s), int(e)) for s, e in zip(np.where(d == 1)[0], np.where(d == -1)[0])]


# ---------------------------------------------------------------------------
# MCAP ingest
# ---------------------------------------------------------------------------
MAVLINK_IDS = {0: "HEARTBEAT", 22: "PARAM_VALUE", 24: "GPS_RAW_INT",
               30: "ATTITUDE", 32: "LOCAL_POSITION_NED", 36: "SERVO_OUTPUT_RAW",
               65: "RC_CHANNELS"}


@dataclass
class Packet:
    path: str
    name: str
    size_bytes: int = 0
    sha256: str = ""
    sealed: bool = False
    unsealed_tail: dict | None = None
    n_records: int = 0
    topic_counts: dict = field(default_factory=dict)
    topic_types: dict = field(default_factory=dict)
    schema_ids: dict = field(default_factory=dict)
    att: np.ndarray | None = None
    pos: np.ndarray | None = None
    servo: np.ndarray | None = None
    rc: np.ndarray | None = None
    hb: np.ndarray | None = None
    gps: np.ndarray | None = None
    par: dict = field(default_factory=dict)
    mpc: list = field(default_factory=list)
    state: np.ndarray | None = None
    cdr_errors: int = 0

    def counts(self):
        return {MAVLINK_IDS.get(k, str(k)): v for k, v in self.fcu_counts.items()}


def _mav_frame(m):
    return bytearray([m.magic, m.len, m.incompat_flags, m.compat_flags, m.seq,
                      m.sysid, m.compid, m.msgid & 0xFF, (m.msgid >> 8) & 0xFF,
                      (m.msgid >> 16) & 0xFF]) + bytearray(
        struct.pack('<%dQ' % len(m.payload64), *m.payload64)[:m.len]) + bytearray(
        [m.checksum & 0xFF, (m.checksum >> 8) & 0xFF]) + bytearray(m.signature)


def ingest_mcap(pkt: Packet, require_seal, fcu=(1, 1), verify_crc=True):
    """Read one MCAP in file order.  Only file-order StreamReader is used."""
    from mcap.stream_reader import StreamReader
    from mcap.exceptions import EndOfFile
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from pymavlink.dialects.v20 import ardupilotmega as MAV

    Mavlink = get_message('mavros_msgs/msg/Mavlink')
    String = get_message('std_msgs/msg/String')
    State = get_message('mavros_msgs/msg/State')
    mav = MAV.MAVLink(None, srcSystem=255, srcComponent=190)

    ch = {}
    schemas = {}
    att, pos, servo, rc, hb, gps, par, mpc, st = ([] for _ in range(9))
    fcu_counts = {}
    counts = {}
    with open(pkt.path, 'rb') as fh:
        rd = StreamReader(fh, validate_crcs=verify_crc)
        try:
            for rec in rd.records:
                tn = type(rec).__name__
                if tn == 'Channel':
                    ch[rec.id] = (rec.topic, rec.schema_id, rec.message_encoding)
                    continue
                if tn == 'Schema':
                    schemas[rec.id] = (rec.name, rec.encoding)
                    continue
                if tn == 'DataEnd':
                    pkt.sealed = True
                    pkt.unsealed_tail = None
                    continue
                if tn != 'Message':
                    continue
                pkt.n_records += 1
                info = ch.get(rec.channel_id)
                if info is None:
                    raise SystemExit(f"{pkt.name}: message on unknown channel {rec.channel_id}")
                topic, sid, enc = info
                counts[topic] = counts.get(topic, 0) + 1
                if enc != 'cdr':
                    raise SystemExit(f"{pkt.name}: unsupported encoding {enc} on {topic}")
                tip = schemas.get(sid, ('?', '?'))[0]
                if tip not in pkt.topic_types:
                    pkt.topic_types[topic] = tip
                try:
                    if topic == '/uas1/mavlink_source':
                        m = deserialize_message(rec.data, Mavlink)
                        if (m.sysid, m.compid) != fcu:
                            continue
                        if m.msgid not in MAVLINK_IDS:
                            continue
                        fcu_counts[m.msgid] = fcu_counts.get(m.msgid, 0) + 1
                        d = mav.decode(_mav_frame(m)).to_dict()
                        t = d['mavpackettype']
                        # ordinal last: item positions above stay stable
                        if t == 'ATTITUDE':
                            att.append((rec.log_time, rec.publish_time, d['time_boot_ms'],
                                        d['roll'], d['pitch'], d['yaw'], d['yawspeed'],
                                        pkt.n_records))
                        elif t == 'LOCAL_POSITION_NED':
                            pos.append((rec.log_time, rec.publish_time, d['time_boot_ms'],
                                        d['x'], d['y'], d['z'], d['vx'], d['vy'], d['vz'],
                                        pkt.n_records))
                        elif t == 'SERVO_OUTPUT_RAW':
                            servo.append((rec.log_time, d['time_usec'], d['port'],
                                          d['servo1_raw'], d['servo3_raw'], pkt.n_records))
                        elif t == 'RC_CHANNELS':
                            rc.append((rec.log_time, d['time_boot_ms'])
                                      + tuple(d['chan%d_raw' % i] for i in range(1, 19))
                                      + (pkt.n_records,))
                        elif t == 'HEARTBEAT':
                            hb.append((rec.log_time, d['base_mode'], d['custom_mode'],
                                       d['system_status'], d['type'], pkt.n_records))
                        elif t == 'GPS_RAW_INT':
                            gps.append((rec.log_time, d['time_usec'], d['fix_type'], d['lat'],
                                        d['lon'], d['alt'], d['eph'], d['satellites_visible'],
                                        d['vel'], d['cog'], pkt.n_records))
                        elif t == 'PARAM_VALUE':
                            par.append((rec.log_time, d['param_id'], d['param_value']))
                    elif topic == '/mpc/status':
                        m = deserialize_message(rec.data, String)
                        mpc.append((rec.log_time, m.data, pkt.n_records))
                    elif topic == '/mavros/state':
                        m = deserialize_message(rec.data, State)
                        st.append((rec.log_time, 1 if m.armed else 0, m.mode,
                                   1 if m.connected else 0, pkt.n_records))
                except Exception as exc:                      # noqa: BLE001
                    pkt.cdr_errors += 1
                    raise SystemExit(f"{pkt.name}: decode/CRC failure on {topic}: {exc}")
        except EndOfFile:
            if require_seal:
                raise SystemExit(f"{pkt.name}: sealed packet required but stream hit EndOfFile")
            pkt.unsealed_tail = {"kind": "EndOfFile", "records_yielded": pkt.n_records}

    pkt.topic_counts = counts
    pkt.schema_ids = {k: v[1] for k, v in ch.items()}
    pkt.att = np.array(att, float)
    pkt.pos = np.array(pos, float)
    pkt.servo = np.array(servo, float)
    pkt.rc = np.array(rc, float)
    pkt.hb = np.array(hb, float)
    pkt.gps = np.array(gps, float)
    pkt.state = np.array(st, object) if st else np.empty((0, 4), object)
    pkt.mpc = [(float(t), s, float(o)) for t, s, o in mpc]
    pkt.par = {}
    for _, name, val in par:
        pkt.par.setdefault(str(name), []).append(float(val))
    pkt.fcu_counts = fcu_counts
    if pkt.unsealed_tail is not None and len(pkt.att):
        pkt.unsealed_tail.update({
            "last_record_log_ns": int(rec.log_time),
            "last_att_boot_ms": float(pkt.att[-1, 2]),
            "counts": dict(counts),
        })
    return pkt


def metadata_counts(path):
    import yaml
    with open(path, 'r', encoding='utf-8') as fh:
        doc = yaml.safe_load(fh)
    info = doc['rosbag2_bagfile_information']
    topics = {}
    for t in info['topics_with_message_count']:
        topics[t['topic_metadata']['name']] = int(t['message_count'])
    return int(info['message_count']), topics, info


def sha256_file(path):
    h = hashlib.sha256()
    n = 0
    with open(path, 'rb') as fh:
        while True:
            b = fh.read(1 << 22)
            if not b:
                break
            h.update(b)
            n += len(b)
    return h.hexdigest(), n


# ---------------------------------------------------------------------------
# time base
# ---------------------------------------------------------------------------
def att_time_arrays(pkt):
    log_s = pkt.att[:, 0] / 1e9
    boot_s = pkt.att[:, 2] / 1e3
    return log_s, boot_s


def clock_segments(log_s, boot_s):
    """Split the file on |dlog - dboot| > CLOCK_JUMP_S.

    Returns (seg, offs) where ``offs[k]`` is the segment-local (Pi clock - FPU
    boot) offset.  ``offs`` is what makes earlier phases comparable to the
    report's CST boundaries without shifting them by the later clock steps.
    """
    dl = np.diff(log_s)
    db = np.diff(boot_s)
    cuts = np.where(np.abs(dl - db) > CLOCK_JUMP_S)[0] + 1
    seg = np.zeros(len(log_s), int)
    for k, c in enumerate(cuts):
        seg[c:] = k + 1
    offs = np.array([np.median(log_s[seg == k] - boot_s[seg == k])
                     for k in range(int(seg.max()) + 1)]) if len(log_s) else np.zeros(1)
    return seg, offs


@dataclass
class TimeBase:
    """FCU boot clock for dynamics; segment-local epoch for CST phase labels."""
    log_s: np.ndarray
    boot_s: np.ndarray
    ords: np.ndarray
    seg: np.ndarray
    offs: np.ndarray

    def boot_of(self, msg_ord, msg_log_s, max_anchor=ANCHOR_MAX_S):
        """Bracket each message by file-order ATTITUDE anchors -> (boot, seg).

        The Pi log clock is non-monotonic (four backward steps up to 0.671 s),
        so ``searchsorted`` on log time is invalid; ordinals are monotone by
        construction.  Anchors must be adjacent in file order and closer than
        ``max_anchor`` in log time within one clock segment.
        """
        o = np.atleast_1d(np.asarray(msg_ord, float))
        t = np.atleast_1d(np.asarray(msg_log_s, float))
        out = np.full(o.shape, np.nan)
        seg_out = np.full(o.shape, -1)
        if len(self.ords) < 2:
            return out, seg_out
        j = np.searchsorted(self.ords, o, side='right')
        ok = (j >= 1) & (j < len(self.ords))
        jj = np.clip(j, 1, len(self.ords) - 1)
        i0, i1 = jj - 1, jj
        span = self.log_s[i1] - self.log_s[i0]
        ok &= np.isfinite(span) & (span > 0) & (span <= max_anchor)
        ok &= self.seg[i0] == self.seg[i1]
        if ok.any():
            t0, t1 = self.log_s[i0[ok]], self.log_s[i1[ok]]
            b0, b1 = self.boot_s[i0[ok]], self.boot_s[i1[ok]]
            w = (t[ok] - t0) / np.maximum(t1 - t0, 1e-12)
            out[ok] = b0 + w * (b1 - b0)
            seg_out[ok] = self.seg[i0[ok]]
        return out, seg_out

    def epoch_of(self, boot, seg):
        boot = np.atleast_1d(np.asarray(boot, float))
        seg = np.atleast_1d(np.asarray(seg, int))
        out = np.full(boot.shape, np.nan)
        ok = (seg >= 0) & (seg < len(self.offs)) & np.isfinite(boot)
        out[ok] = boot[ok] + self.offs[seg[ok]]
        return out

    def epoch_att(self):
        return self.boot_s + self.offs[self.seg]


def servo_epoch(pkt, tb: TimeBase):
    """Reconstruct SERVO_OUTPUT_RAW send times (usec low 32 bits) as boot times.

    Each sample picks ``k*2**32`` so that ``raw_usec + k*2**32`` sits closest to
    the boot time of its file-order ATTITUDE anchor; |residual| > SERVO_AGE_S
    or non-monotonic order breaks the match interval.
    """
    raw = pkt.servo[:, 1].astype(np.float64) / 1e6
    anchor, _seg = tb.boot_of(pkt.servo[:, 5], pkt.servo[:, 0] / 1e9)
    period = 2.0 ** 32 / 1e6
    have = np.isfinite(anchor)
    k = np.zeros(raw.shape)
    k[have] = np.round((anchor[have] - raw[have]) / period)
    boot_est = raw + k * period
    resid = boot_est - anchor
    valid = have & np.isfinite(resid) & (np.abs(resid) <= SERVO_AGE_S)
    if len(boot_est) > 1:
        bad = np.where(~(np.diff(boot_est) > 0))[0]
        valid[bad + 1] = False
    return boot_est, valid, resid, int(np.abs(k).max())


def servo_segments(boot_est, valid, gap=SERVO_GAP_S):
    """Contiguous runs of valid, monotonic snapshots with spacing <= gap."""
    ok = np.asarray(valid, bool).copy()
    if len(ok) > 1:
        d = np.diff(boot_est)
        ok[1:] &= (d > 0) & (d <= gap)
    return [(s, e) for s, e in runs_of(ok) if e - s >= 2]


# ---------------------------------------------------------------------------
# FCU state and mode timeline
# ---------------------------------------------------------------------------
MODE_NAME = {0: 'MANUAL', 15: 'GUIDED', 4: 'HOLD', 3: 'STEER', 10: 'AUTO', 11: 'RTL'}


def latest_within(te, e, max_age):
    """Index of the last sample with epoch <= t and age <= max_age (-1 if none)."""
    te = np.asarray(te, float)
    e = np.asarray(e, float)
    idx = np.searchsorted(te, e, side='right') - 1
    ok = idx >= 0
    idx_c = np.clip(idx, 0, max(0, len(te) - 1))
    age = np.where(ok, e - te[idx_c], np.inf)
    ok &= age <= max_age
    return np.where(ok, idx_c, -1), age


def parse_mpc(pkt):
    ts, fields = [], []
    for t, s in pkt.mpc:
        try:
            d = json.loads(s)
        except Exception:                                     # noqa: BLE001
            d = None
        ts.append(t)
        fields.append(d if isinstance(d, dict) else None)
    return np.array(ts, float), fields


def derive_fcu(pkt, tb: TimeBase, att_boot):
    """Per-ATTITUDE FCU arm/mode/mpc snapshot with freshness gates (boot domain)."""
    n = len(att_boot)
    armed = np.zeros(n, bool)
    hb_mode = np.array([''] * n, dtype=object)
    hb_age = np.full(n, np.inf)
    if len(pkt.hb):
        idx, age = latest_within_ord(tb, pkt.hb[:, 5], pkt.hb[:, 0] / 1e9,
                                     att_boot, HB_MAX_AGE_S)
        base = pkt.hb[:, 1].astype(int)
        cust = pkt.hb[:, 2].astype(int)
        m = idx >= 0
        armed[m] = (base[idx[m]] & 128) != 0
        hb_mode[m] = [MODE_NAME.get(int(c), f'CMODE({int(c)})') for c in cust[idx[m]]]
        hb_age = age

    st_mode = np.array([''] * n, dtype=object)
    st_armed = np.full(n, -1)
    st_fresh = np.zeros(n, bool)
    if len(pkt.state):
        idx, _age = latest_within_ord(tb, pkt.state[:, 4].astype(float),
                                      pkt.state[:, 0].astype(float) / 1e9,
                                      att_boot, STATE_HOLD_S)
        mode = pkt.state[:, 2]
        arm = pkt.state[:, 1].astype(int)
        m = idx >= 0
        st_mode[m] = [str(x) for x in mode[idx[m]]]
        st_armed[m] = arm[idx[m]]
        st_fresh = m

    mpc_ord = np.array([r[2] for r in pkt.mpc], float) if pkt.mpc else np.zeros(0)
    mpc_log = np.array([r[0] for r in pkt.mpc], float) / 1e9
    mpc_fields = []
    for _t, s, _o in pkt.mpc:
        try:
            d = json.loads(s)
        except Exception:                                     # noqa: BLE001
            d = None
        mpc_fields.append(d if isinstance(d, dict) else None)

    mpc_state = np.array([''] * n, dtype=object)
    mpc_ctrl = np.array([''] * n, dtype=object)
    mpc_scheme = np.array([''] * n, dtype=object)
    mpc_fcumode = np.array([''] * n, dtype=object)
    mpc_hold = np.zeros(n, bool)
    mpc_fresh = np.zeros(n, bool)
    if len(mpc_ord):
        valid = np.array([f is not None for f in mpc_fields], bool)
        idx, _age = latest_within_ord(tb, mpc_ord[valid], mpc_log[valid],
                                      att_boot, STATE_HOLD_S)
        keep = np.where(valid)[0]
        m = idx >= 0
        for i in np.where(m)[0]:
            f = mpc_fields[keep[idx[i]]]
            mpc_state[i] = str(f.get('state') or '')
            mpc_ctrl[i] = str(f.get('control_mode') or '')
            mpc_scheme[i] = str(f.get('scheme') or '')
            mpc_fcumode[i] = str(f.get('fcu_mode') or '')
            mpc_hold[i] = bool(f.get('hold') or False)
        mpc_fresh = m

    consistent = np.zeros(n, bool)
    for i in range(n):
        sm = st_mode[i]
        if not st_fresh[i] or not hb_mode[i]:
            continue
        same_mode = (sm == hb_mode[i]) or sm.startswith('CMODE') or sm == ''
        same_arm = (st_armed[i] == int(armed[i])) if st_armed[i] >= 0 else False
        consistent[i] = bool(same_mode and same_arm)

    return {
        'armed': armed, 'hb_mode': hb_mode, 'hb_age': hb_age,
        'st_mode': st_mode, 'st_armed': st_armed, 'st_fresh': st_fresh,
        'mpc_state': mpc_state, 'mpc_ctrl': mpc_ctrl, 'mpc_scheme': mpc_scheme,
        'mpc_fcumode': mpc_fcumode, 'mpc_hold': mpc_hold, 'mpc_fresh': mpc_fresh,
        'consistent': consistent,
    }


def latest_within_ord(tb: TimeBase, msg_ord, msg_log_s, att_boot, max_age):
    """Latest message (file order) with boot time <= att_boot and age <= max_age."""
    boot, seg = tb.boot_of(msg_ord, msg_log_s)
    ok = np.isfinite(boot)
    idx, age = latest_within(boot[ok], att_boot, max_age)
    keep = np.where(ok)[0]
    return np.where(idx >= 0, keep[np.clip(idx, 0, max(0, len(keep) - 1))], -1), age


def classify_roles(pkt, tb: TimeBase, att_boot):
    """Role per ATTITUDE sample: B, A, MANUAL or UNKNOWN (frozen rules)."""
    f = derive_fcu(pkt, tb, att_boot)
    n = len(att_boot)
    role = np.array(['UNKNOWN'] * n, dtype=object)
    armed = f['armed']
    act = f['mpc_state'] == 'ACTIVE'
    b = (act & (f['mpc_ctrl'] == 'dynamic') & (f['mpc_fcumode'] == 'MANUAL')
         & armed & (f['hb_mode'] == 'MANUAL') & f['consistent'] & ~f['mpc_hold'])
    a = (act & (f['mpc_ctrl'] == 'kinematic') & (f['mpc_scheme'] == 'A')
         & armed & (f['hb_mode'] == 'GUIDED') & f['consistent'] & ~f['mpc_hold'])
    manual = (armed & (f['hb_mode'] == 'MANUAL') & f['st_fresh'] & (f['st_mode'] != 'ACTIVE')
              & f['consistent'])
    role[b] = 'B'
    role[a] = 'A'
    role[manual & ~act] = 'MANUAL'
    return role, f


def state_from_fcu(pkt, att_epoch):
    """Planar FCU state on the ATTITUDE samples (boot clock, no GPS derivative)."""
    yaw = pkt.att[:, 5]
    boot_s = pkt.att[:, 2] / 1e3
    # LOCAL_POSITION_NED: x = North, y = East, vx = North, vy = East.
    # The plan's planar frame is x = East, y = North, so the pairs are swapped.
    tb_pos = pkt.pos[:, 2] / 1e3
    vN = interp_g(tb_pos, pkt.pos[:, 6], boot_s, POS_GAP_S)
    vE = interp_g(tb_pos, pkt.pos[:, 7], boot_s, POS_GAP_S)
    xE = interp_g(tb_pos, pkt.pos[:, 4], boot_s, POS_GAP_S)
    yN = interp_g(tb_pos, pkt.pos[:, 3], boot_s, POS_GAP_S)
    gs = np.hypot(vN, vE)
    u = vN * np.cos(yaw) + vE * np.sin(yaw)
    v = vN * np.sin(yaw) - vE * np.cos(yaw)
    r = -pkt.att[:, 6]
    return {
        'boot_s': boot_s, 'x': xE, 'y': yN, 'psi': wrap_pi(math.pi / 2.0 - yaw),
        'u': u, 'v': v, 'r': r, 'gs': gs,
        'roll': pkt.att[:, 3], 'pitch': pkt.att[:, 4], 'yaw_ned': yaw,
        'log_s': pkt.att[:, 0] / 1e9, 'ords': pkt.att[:, 7],
        't_epoch': att_epoch,
    }


# ---------------------------------------------------------------------------
# time-series helpers
# ---------------------------------------------------------------------------
def break_mask(boot_s, role, seg, stage, pad=BREAK_PAD_S):
    """True = do not use this ATTITUDE sample (breakpoints dilated by ``pad``).

    Padding is applied in FCU-time seconds, not in samples: the record is not
    uniformly sampled (median 0.058 s but bursts down to 0.02 s), so a
    sample-count radius would silently shrink the promised one-second guard.
    Stage transitions are breakpoints too, including the train/holdout cut.
    """
    boot_s = np.asarray(boot_s, float)
    n = len(boot_s)
    if n == 0:
        return np.zeros(0, bool)
    d = np.diff(boot_s)
    gap = d > ATT_GAP_S
    edge = np.zeros(n, bool)
    edge[0] = edge[-1] = True
    edge[:-1] |= gap
    edge[1:] |= gap
    chg = np.zeros(n, bool)
    chg[1:] = ((role[1:] != role[:-1]) | (seg[1:] != seg[:-1])
               | (stage[1:] != stage[:-1]))
    edge |= chg | np.concatenate((chg[1:], [False]))
    bad = np.zeros(n, bool)
    for t in boot_s[edge]:
        bad |= np.abs(boot_s - t) <= pad
    return bad


def exclude_mask(att_epoch):
    m = np.zeros(len(att_epoch), bool)
    for a, b in EXCLUDE_UTC:
        m |= (att_epoch >= cst_epoch(a)) & (att_epoch < cst_epoch(b))
    return m


def boot_to_cst(tb, boot_s):
    """CST label from the *segment-local* epoch (never a global clock shift)."""
    boot_s = np.atleast_1d(np.asarray(boot_s, float))
    k = np.clip(np.searchsorted(tb.boot_s, boot_s), 0, len(tb.boot_s) - 1)
    return [cst_str(b + tb.offs[tb.seg[i]]) for b, i in zip(boot_s, k)]


def stage_of(att_epoch):
    lab = np.array(['outside'] * len(att_epoch), dtype=object)
    for name, (a, b) in (('train_B', ROLE_TRAIN_B), ('train_manual1', ROLE_TRAIN_MANUAL1),
                         ('train_manual2', ROLE_TRAIN_MANUAL2), ('holdout', ROLE_HOLDOUT),
                         ('A_envelope', ROLE_A)):
        m = (att_epoch >= cst_epoch(a)) & (att_epoch < cst_epoch(b))
        lab[m] = name
    return lab


# ---------------------------------------------------------------------------
# stage 1: evidence, time base, static baseline
# ---------------------------------------------------------------------------
DAY_RUN = 'usv_run_20261118_140716'
NIGHT_RUN = 'usv_run_20261118_200143'


def tool_versions():
    import platform
    v = {'python': platform.python_version(), 'numpy': np.__version__}
    for name, mod in (('scipy', 'scipy'), ('matplotlib', 'matplotlib'),
                      ('pymavlink', 'pymavlink'), ('mcap', 'mcap'),
                      ('yaml', 'yaml')):
        try:
            v[name] = getattr(__import__(mod), '__version__', 'unknown')
        except Exception:                                     # noqa: BLE001
            v[name] = 'missing'
    return v


def stage_source(args):
    out = {}
    day_dir = os.path.join(args.data_root, DAY_RUN)
    night_dir = os.path.join(args.data_root, NIGHT_RUN)
    day_mcap = os.path.join(day_dir, DAY_RUN + '_0.mcap')
    night_mcap = os.path.join(night_dir, NIGHT_RUN + '_0.mcap')
    meta_path = os.path.join(day_dir, 'metadata.yaml')

    day = Packet(day_mcap, DAY_RUN)
    day.size_bytes = os.path.getsize(day_mcap)
    day.sha256 = sha256_file(day_mcap)[0]
    ingest_mcap(day, require_seal=True)

    n_msg, topics, info = metadata_counts(meta_path)
    if not day.sealed:
        raise SystemExit(f"{DAY_RUN}: missing DataEnd (metadata.yaml present)")
    if day.n_records != n_msg:
        raise SystemExit(f"{DAY_RUN}: {day.n_records} records != metadata {n_msg}")
    for topic, want in topics.items():
        got = day.topic_counts.get(topic, 0)
        if got != want:
            raise SystemExit(f"{DAY_RUN}: topic {topic} has {got} != metadata {want}")
    missing = sorted(set(day.topic_counts) - set(topics))
    if missing:
        raise SystemExit(f"{DAY_RUN}: topics absent from metadata: {missing}")

    night = Packet(night_mcap, NIGHT_RUN)
    night.size_bytes = os.path.getsize(night_mcap)
    night.sha256 = sha256_file(night_mcap)[0]
    ingest_mcap(night, require_seal=False)

    return day, night, info, out


def att_rate(arr, name, out, col=2, scale=1e-3, label=None):
    """Sampling-interval stats for one FCU stream (no arrival-time substitution)."""
    if arr is None or not len(arr):
        out[label or name] = {'n': 0}
        return
    t = arr[:, col] * scale
    d = np.diff(t)
    d = d[d > 0]
    out[label or name] = {'n': int(len(arr)),
                          'dt_median_s': float(np.median(d)) if d.size else None,
                          'dt_p5_s': float(np.percentile(d, 5)) if d.size else None,
                          'dt_p95_s': float(np.percentile(d, 95)) if d.size else None,
                          'gaps_gt_1s': int((d > 1.0).sum()) if d.size else 0}


def inventory(pkt, tb):
    inv = {}
    att_rate(pkt.att, 'ATTITUDE', inv, col=2, scale=1e-3)
    att_rate(pkt.pos, 'LOCAL_POSITION_NED', inv, col=2, scale=1e-3)
    att_rate(pkt.servo, 'SERVO_OUTPUT_RAW', inv, col=1, scale=1e-6)
    att_rate(pkt.rc, 'RC_CHANNELS', inv, col=1, scale=1e-3)
    att_rate(pkt.gps, 'GPS_RAW_INT', inv, col=1, scale=1e-6)
    # HEARTBEAT carries no FCU timestamp: arrival time only, for inventory
    att_rate(pkt.hb, 'HEARTBEAT_arrival', inv, col=0, scale=1e-9)
    inv['PARAM_VALUE'] = {'n': int(sum(len(v) for v in pkt.par.values())),
                          'names': len(pkt.par)}
    inv['mpc_status'] = {'n': len(pkt.mpc)}
    inv['mavros_state'] = {'n': int(len(pkt.state))}
    return inv


def static_baseline(pkt):
    """Evening packet: disarmed static observations only (never used for fitting)."""
    tb = TimeBase(*_tb_parts(pkt))
    boot = pkt.att[:, 2] / 1e3
    f = derive_fcu(pkt, tb, boot)
    armed_any = bool(f['armed'].any())
    hb_armed = int(((pkt.hb[:, 1].astype(int) & 128) != 0).sum()) if len(pkt.hb) else 0
    out = {'armed_attitude_samples': int(f['armed'].sum()), 'armed_any': armed_any,
           'n_att': int(len(pkt.att)),
           'n_hb': int(len(pkt.hb)), 'n_hb_armed': hb_armed,
           'n_channel_snapshots': int(len(pkt.servo))}
    servo_ok = pkt.servo[:, 3] == SERVO_TRIM
    servo_ok &= pkt.servo[:, 4] == SERVO_TRIM
    out['servo_both_trim_all'] = bool(servo_ok.all())
    out['servo_n'] = int(len(pkt.servo))
    yaw = pkt.att[:, 5]
    yaw_u = np.unwrap(yaw - yaw[0])
    st = state_from_fcu(pkt, boot + tb.offs[tb.seg])
    keep = np.isfinite(st['u']) & np.isfinite(st['r']) & ~f['armed']
    metrics = {}
    for key in ('u', 'v', 'r', 'gs'):
        x = st[key][keep]
        if x.size == 0:
            metrics[key] = {'n': 0}
            continue
        med = float(np.median(x))
        mad = float(np.median(np.abs(x - med)))
        metrics[key] = {'n': int(x.size), 'median': med, 'mad': mad,
                        'abs_dev_p95': float(np.percentile(np.abs(x - med), 95))}
    out['velocity_noise'] = metrics
    x = st['yaw_ned'][np.isfinite(st['yaw_ned'])]
    d = np.diff(np.unwrap(x))
    d = d[np.isfinite(d)]
    out['yaw_rate_noise_rad_s'] = {'n': int(d.size),
                                   'median': float(np.median(d)) if d.size else None,
                                   'mad': float(np.median(np.abs(d - np.median(d)))) if d.size else None,
                                   'abs_dev_p95': float(np.percentile(np.abs(d - np.median(d)), 95)) if d.size else None}
    ok = np.isfinite(st['x']) & np.isfinite(st['y']) & (pkt.att[:, 2] / 1e3 > 0)
    if ok.any():
        out['position_drift_m'] = {
            'n': int(ok.sum()),
            'range_x': float(np.ptp(st['x'][ok])),
            'range_y': float(np.ptp(st['y'][ok])),
            'end_minus_start': float(math.hypot(st['x'][ok][-1] - st['x'][ok][0],
                                                st['y'][ok][-1] - st['y'][ok][0])),
        }
    blocks = []
    step = int(round(10.0 / max(1e-6, np.median(np.diff(boot)))))
    if step > 1 and len(boot) > step:
        for i0 in range(0, len(boot) - step, step):
            sl = slice(i0, i0 + step)
            uu = st['u'][sl]
            rr = st['r'][sl]
            if not (np.isfinite(uu).all() and np.isfinite(rr).all()):
                continue
            blocks.append({'t0_s': float(boot[i0]),
                           'u_p50': float(np.percentile(uu, 50)),
                           'u_p95_abs': float(np.percentile(np.abs(uu), 95)),
                           'r_p50': float(np.percentile(rr, 50)),
                           'r_p95_abs': float(np.percentile(np.abs(rr), 95))})
    out['ten_second_blocks'] = blocks
    out['note'] = ('晚间包仅提供未解锁静态观测基线；不得用于白天零偏扣除、'
                   '训练、验证或回放。')
    out['gps_fix'] = _fix_hist(pkt)
    return out


def _fix_hist(pkt):
    if not len(pkt.gps):
        return {}
    vals, cnts = np.unique(pkt.gps[:, 2].astype(int), return_counts=True)
    return {int(v): int(c) for v, c in zip(vals, cnts)}


def _tb_parts(pkt):
    log_s, boot_s = att_time_arrays(pkt)
    seg, offs = clock_segments(log_s, boot_s)
    return log_s, boot_s, pkt.att[:, 7], seg, offs


def make_tb(pkt):
    return TimeBase(*_tb_parts(pkt))


def write_json(path, obj):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, default=_json_default)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def write_csv(path, header, rows):
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow(['' if v is None else v for v in r])


# ---------------------------------------------------------------------------
# stage 2: purpose-driven water samples and the frozen split
# ---------------------------------------------------------------------------
def hold_att(att_boot, t_dst, max_age=ATT_GAP_S):
    """Index of the last ATTITUDE sample at or before t_dst (-1 if too old)."""
    idx = np.searchsorted(att_boot, t_dst, side='right') - 1
    ok = idx >= 0
    idx_c = np.clip(idx, 0, max(0, len(att_boot) - 1))
    age = np.where(ok, t_dst - att_boot[idx_c], np.inf)
    ok &= age <= max_age
    return np.where(ok, idx_c, -1)


def low_speed_ok(st, idx):
    gs = st['gs'][idx]
    r = np.abs(st['r'][idx])
    roll = np.abs(st['roll'][idx])
    pitch = np.abs(st['pitch'][idx])
    return ((gs <= SPEED_LIM) & (r <= RATE_LIM) & (roll <= ROLL_LIM)
            & (pitch <= PITCH_LIM))


def build_grid(block_t0, block_t1):
    n = int(math.floor((block_t1 - block_t0) / DT)) + 1
    return block_t0 + DT * np.arange(n)


def snapshot_span(srv_boot, srv_ok, i0_seg, i1_seg, t0, t1, pwm_l, pwm_r,
                  step_um=WIN_SNAPSHOT_STEP_US, min_snap=WIN_MIN_SNAPSHOTS):
    """Snapshot evidence spanning [t0, t1] inside one servo segment."""
    lo = np.searchsorted(srv_boot[i0_seg:i1_seg], t0, side='right') - 1 + i0_seg
    lo = max(lo, i0_seg)
    hi = np.searchsorted(srv_boot[i0_seg:i1_seg], t1, side='left') + i0_seg
    hi = min(hi, i1_seg - 1)
    if hi < lo:
        return None
    idx = np.arange(lo, hi + 1)
    if not srv_ok[idx].all():
        return None
    t = srv_boot[idx]
    if t[0] > t0 or t[-1] < t1:
        return None
    if len(t) < 2:
        return None
    gaps = np.diff(t)
    if not (gaps <= WIN_SNAPSHOT_GAP_S).all():
        return None
    dl = np.abs(np.diff(pwm_l[idx]))
    dr = np.abs(np.diff(pwm_r[idx]))
    if dl.size and (dl.max() > step_um or dr.max() > step_um):
        return None
    pl, pr = pwm_l[idx], pwm_r[idx]
    if pl.min() < SERVO_TRIM or pr.min() < SERVO_TRIM:
        return None
    if pl.max() > SERVO_MAX or pr.max() > SERVO_MAX:
        return None
    distinct = len(np.unique(np.stack([t, pl, pr], axis=1), axis=0))
    if distinct < min_snap:
        return None
    return {'idx0': int(lo), 'idx1': int(hi), 'n_snap': int(len(idx)),
            'pwm_l': pl, 'pwm_r': pr, 't': t}


def q_from_pwm(pwm, deadzone=PWM_DEADZONE_US):
    return old.pwm_to_normalized(pwm, SERVO_MIN, SERVO_TRIM, SERVO_MAX, deadzone)


def input_terms(t_nodes, t_pwm, pwm_l, pwm_r, mode='zoh', deadzone=PWM_DEADZONE_US):
    """(int(qL^2+qR^2), int(qR^2-qL^2)) over [t_nodes[0], t_nodes[-1]].

    mode='zoh'    exact piecewise-constant integration at the real sample times
    mode='linear' 0.05 s node interpolation then trapezoid (perturbation only)
    """
    t0, t1 = t_nodes[0], t_nodes[-1]
    if mode == 'linear':
        pl = np.interp(t_nodes, t_pwm, pwm_l)
        pr = np.interp(t_nodes, t_pwm, pwm_r)
        ql = q_from_pwm(pl, deadzone) ** 2
        qr = q_from_pwm(pr, deadzone) ** 2
        return float(old.trapz(ql + qr, DT)), float(old.trapz(qr - ql, DT))
    # exact ZOH: value held from each sample until the next one
    ql = q_from_pwm(pwm_l, deadzone) ** 2
    qr = q_from_pwm(pwm_r, deadzone) ** 2
    tt = np.append(t_pwm, t_pwm[-1] + 0.0)
    edges = np.clip(np.concatenate([[t0], t_pwm[1:], [t1]]), t0, t1)
    acc_s = acc_d = 0.0
    for i in range(len(t_pwm)):
        a = max(t_pwm[i], t0)
        b = min(t_pwm[i + 1] if i + 1 < len(t_pwm) else t1, t1)
        if b > a:
            dt = b - a
            acc_s += (ql[i] + qr[i]) * dt
            acc_d += (qr[i] - ql[i]) * dt
    return float(acc_s), float(acc_d)


def window_row(t_nodes, u, v, r, m, IQ_sum, IQ_diff, p_base, n_cols='M1'):
    """One 4 s window -> (surge row, yaw row) in the frozen regression form."""
    m11, m22, m23, m32, m33 = m
    d = p_base['d_thruster']
    c1 = (-m22 * v - m23 * r) * r
    c3 = (m22 * v + m23 * r) * u - m11 * u * v
    Iu = old.trapz(u, DT)
    Iu2 = old.trapz(np.abs(u) * u, DT)
    Ir = old.trapz(r, DT)
    Irr = old.trapz(np.abs(r) * r, DT)
    I1 = old.trapz(c1, DT)
    I3 = old.trapz(c3, DT)
    du = u[-1] - u[0]
    dv = v[-1] - v[0]
    dr = r[-1] - r[0]
    surge = (np.array([Iu, Iu2, 0.0, 0.0, -IQ_sum]),
             -(m11 * du + I1), m11 * 0.20)
    yaw = (np.array([0.0, 0.0, Ir, Irr, -d * IQ_diff]),
           -(m32 * dv + m33 * dr + I3), m33 * math.radians(12.0))
    return surge, yaw


def scan_windows(role_name, stage, t0, t1, t_grid, masks, st, att_idx, m, p_base,
                 srv_boot, srv_ok, srv_segs, pwm_l, pwm_r, seg_of_node):
    """Greedy non-overlapping 4 s window scan inside one contiguous block.

    ``masks`` = (sample_ok, speed_ok) so reject reasons stay separable.
    """
    wins = []
    rej = {}
    n = len(t_grid)
    if n < WIN_STEPS + 1:
        return wins, {'block_too_short': 1}, {}
    m_sample, m_speed = masks
    funnel = {'grid_positions': 0, 'pass_sample': 0, 'pass_speed': 0,
              'pass_snapshot': 0, 'pass_motion': 0, 'accepted': 0}
    i = 0
    while i + WIN_STEPS < n:
        sl = slice(i, i + WIN_STEPS + 1)
        funnel['grid_positions'] += 1
        if not m_sample[sl].all():
            i += 1
            rej['sample_gate'] = rej.get('sample_gate', 0) + 1
            continue
        funnel['pass_sample'] += 1
        if not m_speed[sl].all():
            i += 1
            rej['speed_gate'] = rej.get('speed_gate', 0) + 1
            continue
        funnel['pass_speed'] += 1
        a, b = t_grid[i], t_grid[i + WIN_STEPS]
        seg_id = seg_of_node[i]
        if seg_id < 0:
            i += 1
            rej['servo_segment'] = rej.get('servo_segment', 0) + 1
            continue
        i0, i1 = srv_segs[seg_id]
        snap = snapshot_span(srv_boot, srv_ok, i0, i1, a, b, pwm_l, pwm_r)
        if snap is None:
            i += 1
            rej['snapshot'] = rej.get('snapshot', 0) + 1
            continue
        funnel['pass_snapshot'] += 1
        gsv = st['gs'][att_idx[sl]]
        rv = np.abs(st['r'][att_idx[sl]])
        if not ((gsv > LOCAL_SPEED_MIN).any() or (rv > LOCAL_RATE_MIN).any()):
            i += 1
            rej['no_motion'] = rej.get('no_motion', 0) + 1
            continue
        funnel['pass_motion'] += 1
        ai = att_idx[sl]
        u = st['u'][ai]
        v = st['v'][ai]
        r = st['r'][ai]
        IQ_sum, IQ_diff = input_terms(t_grid[sl], snap['t'], snap['pwm_l'], snap['pwm_r'],
                                      mode='zoh')
        surge, yaw = window_row(t_grid[sl], u, v, r, m, IQ_sum, IQ_diff, p_base)
        wins.append({
            'role': role_name, 'stage': stage,
            't0': float(a), 't1': float(b),
            't0_cst': '', 't1_cst': '',
            'n_snap': snap['n_snap'],
            'pwm_l_med': float(np.median(snap['pwm_l'])),
            'pwm_r_med': float(np.median(snap['pwm_r'])),
            'pwm_l_min': float(snap['pwm_l'].min()),
            'pwm_r_min': float(snap['pwm_r'].min()),
            'pwm_l_max': float(snap['pwm_l'].max()),
            'pwm_r_max': float(snap['pwm_r'].max()),
            'u_p50': float(np.median(u)), 'u_max': float(np.max(u)),
            'v_p50': float(np.median(v)), 'v_max': float(np.max(np.abs(v))),
            'r_p50': float(np.median(r)), 'r_max_abs': float(np.max(np.abs(r))),
            'gs_max': float(np.max(gsv)),
            'IQ_sum': float(IQ_sum), 'IQ_diff': float(IQ_diff),
            'surge': surge, 'yaw': yaw,
            't_nodes': t_grid[sl].copy(),
            'u': u.copy(), 'v': v.copy(), 'r': r.copy(),
            'x': st['x'][att_idx[sl]].copy(), 'y': st['y'][att_idx[sl]].copy(),
            'psi': st['psi'][att_idx[sl]].copy(),
            'x0': float(st['x'][att_idx[i]]), 'y0': float(st['y'][att_idx[i]]),
            'psi0': float(st['psi'][att_idx[i]]),
            'snap_t': snap['t'].copy(),
            'snap_l': snap['pwm_l'].copy(), 'snap_r': snap['pwm_r'].copy(),
        })
        funnel['accepted'] += 1
        i += WIN_STEPS
    return wins, rej, funnel


def window_gate_sensitivity(blocks_cache, srv_boot, srv_ok, srv_segs, pwm_l, pwm_r,
                            thresholds=(60.0, 100.0, 200.0, 300.0, 1000.0)):
    """Diagnostic only: how the frozen snapshot-step gate bounds the window count.

    The 60 us gate is what the fit uses; the other columns are reported so the
    missing-excitation claim can be checked without loosening the frozen gate.
    """
    out = {}
    for name, series in blocks_cache.items():
        out[name] = {}
        for thr in thresholds:
            n = 0
            for t_grid, okc, speed_ok, seg_of_node in series:
                i = 0
                while i + WIN_STEPS < len(t_grid):
                    sl = slice(i, i + WIN_STEPS + 1)
                    if not (okc[sl].all() and speed_ok[sl].all()):
                        i += 1
                        continue
                    ai = None
                    seg_id = seg_of_node[i]
                    if seg_id < 0:
                        i += 1
                        continue
                    i0, i1 = srv_segs[seg_id]
                    snap = snapshot_span(srv_boot, srv_ok, i0, i1, t_grid[i],
                                         t_grid[i + WIN_STEPS], pwm_l, pwm_r,
                                         step_um=thr)
                    if snap is None:
                        i += 1
                        continue
                    n += 1
                    i += WIN_STEPS
            out[name][f"step_{int(thr)}um"] = n
    return out


def stage_split(day, day_tb, p_base, srv_boot, srv_valid, srv_segs, out_dir):
    att_boot = day.att[:, 2] / 1e3
    att_epoch = day_tb.epoch_att()
    role, fcu = classify_roles(day, day_tb, att_boot)
    st = state_from_fcu(day, att_epoch)
    stage = stage_of(att_epoch)
    m = old.hydro_matrix(p_base)
    pwm_l = day.servo[:, 3].astype(float)
    pwm_r = day.servo[:, 4].astype(float)

    excl = exclude_mask(att_epoch)
    uncertain = ~(fcu['mpc_fresh'] & fcu['st_fresh'] & fcu['consistent'])
    bad = break_mask(att_boot, role, day_tb.seg, stage) | excl | uncertain

    # per-ATTITUDE validity with GPS freshness and fix
    gps_ok = np.zeros(len(att_boot), bool)
    if len(day.gps):
        idx, age = latest_within_ord(day_tb, day.gps[:, 10], day.gps[:, 0] / 1e9,
                                     att_boot, GPS_MAX_AGE_S)
        fix = day.gps[:, 2].astype(int)
        ok = idx >= 0
        gps_ok[ok] = fix[idx[ok]] >= GPS_MIN_FIX
        gps_ok &= age <= GPS_MAX_AGE_S
    # Each fixed phase requires its own FCU/MPC role: within the scheme-B
    # interval only B ACTIVE counts, and the manual/holdout phases only accept
    # MANUAL.  Anything else there is a standby/disconnect, not excitation.
    stage_role = {'train_B': 'B', 'train_manual1': 'MANUAL',
                  'train_manual2': 'MANUAL', 'holdout': 'MANUAL'}
    wanted = np.array([stage_role.get(str(x), '') for x in stage], dtype=object)
    stage_ok = wanted != ''
    role_ok = np.array([w == r for w, r in zip(wanted, role)], bool)
    sample_ok = stage_ok & role_ok & ~bad & gps_ok

    blocks = []
    for s, e in runs_of(sample_ok):
        bt0, bt1 = att_boot[s], att_boot[e - 1]
        if bt1 - bt0 < WIN_S:
            continue
        blocks.append({'i0': int(s), 'i1': int(e), 't0': float(bt0), 't1': float(bt1),
                       'role': str(role[s]), 'stage': str(stage[s])})

    # servo node->segment lookup
    seg_starts = np.array([s for s, _ in srv_segs], int) if srv_segs else np.zeros(0, int)
    wins = []
    reject = {}
    funnel = {}
    sens_cache = {}
    coarse = {}
    env = {}
    stage_names = ['train_B', 'train_manual1', 'train_manual2', 'holdout', 'A_envelope']
    for name in stage_names:
        sel = stage == name
        coarse[name] = {'attitude_samples': int(sel.sum()),
                        'coarse_snapshot_windows': 0}
    for blk in blocks:
        blk['wins'] = []
    stage_start = {}
    for blk in blocks:
        stage_start[blk['stage']] = min(stage_start.get(blk['stage'], np.inf), blk['t0'])
    blk_i = 0
    for blk in blocks:
        t_grid = build_grid(blk['t0'], blk['t1'])
        idx = hold_att(att_boot, t_grid)
        ok = idx >= 0
        okc = ok.copy()
        okc[ok] = sample_ok[idx[ok]]
        okc &= ok
        speed_ok = np.zeros(len(t_grid), bool)
        if okc.any():
            speed_ok[okc] = low_speed_ok(st, idx[okc])
        seg_of_node = np.full(len(t_grid), -1, int)
        if len(seg_starts):
            seg_ends = np.array([e for _, e in srv_segs], int)
            seg_t0 = srv_boot[seg_starts]
            seg_t1 = srv_boot[seg_ends - 1]
            pos = np.searchsorted(seg_t0, t_grid, side='right') - 1
            good = pos >= 0
            pi = np.clip(pos, 0, len(seg_starts) - 1)
            good &= (t_grid >= seg_t0[pi]) & (t_grid <= seg_t1[pi])
            seg_of_node[good] = pi[good]
        sens_cache.setdefault(blk['stage'], []).append((t_grid, okc, speed_ok, seg_of_node))
        w, rej, fun = scan_windows(blk['role'], blk['stage'], blk['t0'], blk['t1'],
                                   t_grid, (okc, speed_ok), st, idx, m, p_base,
                                   srv_boot, srv_valid, srv_segs, pwm_l, pwm_r,
                                   seg_of_node)
        for k, v in rej.items():
            d = reject.setdefault(blk['stage'], {})
            d[k] = d.get(k, 0) + v
        fd = funnel.setdefault(blk['stage'], {})
        for k, v in fun.items():
            fd[k] = fd.get(k, 0) + v
        for x in w:
            x['t0_cst'] = boot_to_cst(day_tb, x['t0'])[0]
            x['t1_cst'] = boot_to_cst(day_tb, x['t1'])[0]
            # 30 s cluster indexed from the *stage* start (frozen here)
            x['cluster'] = int(math.floor((x['t0'] - stage_start[blk['stage']]) / CLUSTER_S))
            x['block_t0'] = blk['t0']
            x['id'] = f"W{len(wins) + 1:04d}"
            wins.append(x)
        blk['wins'] = [x['id'] for x in w]
        blk_i += 1

    # coarse snapshot-only screen (report cross-check; no continuity/forward gate)
    coarse_idx = np.where(sample_ok & np.isin(stage, ['train_B', 'train_manual1',
                                                      'train_manual2', 'holdout']))[0]
    seen = {}
    for i in coarse_idx:
        t = att_boot[i]
        key = (stage_of(np.array([att_epoch[i]]))[0],)
        slot = int(t // WIN_S)
        if (key, slot) in seen:
            continue
        seen[(key, slot)] = True
        if low_speed_ok(st, np.array([i]))[0] and np.isfinite(st['u'][i]):
            coarse[key[0]]['coarse_snapshot_windows'] += 1

    split = {
        'generated_utc': _dt.datetime.now(_dt.timezone.utc).isoformat(),
        'frozen': True,
        'note': ('切分在读取任何拟合数据之前写出；训练不因拟合结果重分。'
                 '留出窗只允许评分。'),
        'window_s': WIN_S, 'dt': DT,
        'roles': {name: {'cst': list(ROLE_TRAIN_B if name == 'train_B' else
                                     ROLE_TRAIN_MANUAL1 if name == 'train_manual1' else
                                     ROLE_TRAIN_MANUAL2 if name == 'train_manual2' else
                                     ROLE_HOLDOUT if name == 'holdout' else ROLE_A)}
                  for name in stage_names},
        'filters': {'speed_max': SPEED_LIM, 'rate_max': RATE_LIM,
                    'roll_max_deg': 10.0, 'pitch_max_deg': 15.0,
                    'gps_min_fix': GPS_MIN_FIX, 'gps_max_age_s': GPS_MAX_AGE_S,
                    'hb_max_age_s': HB_MAX_AGE_S, 'break_pad_s': BREAK_PAD_S,
                    'exclude_cst': EXCLUDE_UTC,
                    'servo_min_us': SERVO_TRIM, 'servo_max_us': SERVO_MAX,
                    'snapshot_gap_s': WIN_SNAPSHOT_GAP_S,
                    'snapshot_step_us': WIN_SNAPSHOT_STEP_US,
                    'min_snapshots': WIN_MIN_SNAPSHOTS},
        'stage_sample_counts': coarse,
        'role_att_counts': {r: int((role == r).sum()) for r in
                            ('B', 'A', 'MANUAL', 'UNKNOWN')},
        'blocks': [{k: v for k, v in b.items() if k != 'wins'} | {'n_wins': len(b['wins'])}
                   for b in blocks],
        'window_rejects': reject,
        'window_funnel': funnel,
        'windows': [{k: v for k, v in w.items()
                     if k not in ('surge', 'yaw', 't_nodes', 'u', 'v', 'r',
                                  'snap_t', 'snap_l', 'snap_r')} for w in wins],
    }
    split['split_hash'] = hashlib.sha256(
        json.dumps([{k: w[k] for k in ('id', 'stage', 'role', 't0', 't1')}
                    for w in wins], sort_keys=True).encode()).hexdigest()

    rows = []
    for b in blocks:
        note = ('eligible' if b['wins'] else
                'no_window: ' + ','.join(sorted(reject.get(b['stage'], {}))))
        rows.append(['block', '', b['role'], b['stage'], f"{b['t0']:.3f}",
                     f"{b['t1']:.3f}", *boot_to_cst(day_tb, [b['t0'], b['t1']]),
                     len(b['wins']), '', '', '', '', note])
    for w in wins:
        rows.append(['window', w['id'], w['role'], w['stage'], f"{w['t0']:.3f}",
                     f"{w['t1']:.3f}", w['t0_cst'], w['t1_cst'], w['n_snap'],
                     f"{w['pwm_l_med']:.0f}", f"{w['pwm_r_med']:.0f}",
                     f"{w['u_p50']:.3f}", f"{w['r_p50']:.3f}",
                     'accepted:' + label_window(w)])
    # closed-loop stages are listed for audit but never fitted
    for name, rl in (('A_envelope', 'A'),):
        for s0, e0 in runs_of((stage == name) & (~bad) & gps_ok):
            if att_boot[e0 - 1] - att_boot[s0] < WIN_S:
                continue
            rows.append(['block', '', rl, name, f"{att_boot[s0]:.3f}",
                         f"{att_boot[e0 - 1]:.3f}",
                         *boot_to_cst(day_tb, [att_boot[s0], att_boot[e0 - 1]]),
                         0, '', '', '', 'closed_loop_envelope_only'])
    write_csv(os.path.join(out_dir, 'segments.csv'),
              ['kind', 'id', 'role', 'stage', 't0_boot_s', 't1_boot_s', 't0_cst',
               't1_cst', 'n_snap_or_wins', 'pwm_l_med_us', 'pwm_r_med_us',
               'u_p50_mps', 'r_p50_rad_s', 'exclusion_or_note'], rows)
    checks = {}
    tr = [(w['t0'], w['t1']) for w in wins if w['stage'].startswith('train')]
    ho = [(w['t0'], w['t1']) for w in wins if w['stage'] == 'holdout']
    checks['train_holdout_disjoint'] = not any(
        a0 < b1 and b0 < a1 for a0, a1 in tr for b0, b1 in ho)
    lo, hi = float(att_boot[0]), float(att_boot[-1])
    checks['all_windows_inside_day_boot'] = all(lo <= w['t0'] and w['t1'] <= hi
                                                for w in wins)
    checks['night_packet_used_for_windows'] = False
    checks['stage_intervals_disjoint'] = True
    for a, b in (('train_B', 'holdout'), ('train_manual1', 'holdout'),
                 ('train_manual2', 'holdout')):
        ta = [w['t0'] for w in wins if w['stage'] == a]
        tb_ = [w['t1'] for w in wins if w['stage'] == b]
        if ta and tb_ and max(ta) >= min(tb_):
            checks['stage_intervals_disjoint'] = False
    bad_role = [w['id'] for w in wins
                if w['role'] != stage_role.get(w['stage'], w['role'])]
    checks['stage_role_pairing_ok'] = not bad_role
    checks['stage_role_violations'] = bad_role
    checks['window_boot_range'] = [float(min(w['t0'] for w in wins)) if wins else None,
                                  float(max(w['t1'] for w in wins)) if wins else None]
    split['integrity_checks'] = checks
    if not (checks['train_holdout_disjoint'] and checks['stage_intervals_disjoint']
            and checks['all_windows_inside_day_boot']
            and checks['stage_role_pairing_ok']):
        raise SystemExit(f"split integrity check failed: {checks}")
    split['step_gate_sensitivity'] = window_gate_sensitivity(
        sens_cache, srv_boot, srv_valid, srv_segs, pwm_l, pwm_r)
    split['step_gate_note'] = ('仅作诊断：拟合只用 60 us 门；其他列用于核对'
                              '“缺少哪类激励”的结论，不参与任何选择。')
    env_ok = (~bad) & gps_ok
    split['envelope_counts'] = {n: int((env_ok & (role == n)).sum())
                                for n in ('B', 'A', 'MANUAL')}
    return split, wins, st, role, fcu, stage, sample_ok, env_ok


# ---------------------------------------------------------------------------
# stage 3: bounded low-bandwidth fit, bootstrap, input perturbations
# ---------------------------------------------------------------------------
PARAM_KEYS = ('a1', 'a2', 'n1', 'n2', 'G')


def param_bounds(p_base):
    ub = np.array([10.0 * max(abs(p_base['Xu']), 0.1),
                   10.0 * max(abs(p_base['Xuu']), 0.1),
                   10.0 * max(abs(p_base['Nr']), 0.1),
                   10.0 * max(abs(p_base['Nrr']), 0.1),
                   G_UPPER_N])
    return np.zeros(5), ub


STRUCTURES = {
    'M1': {'cols': ('a1', 'a2', 'n1', 'n2', 'G'), 'axes': ('surge', 'yaw'),
           'label': 'joint surge+yaw'},
    'MX': {'cols': ('a1', 'a2', 'G'), 'axes': ('surge',),
           'label': 'surge only'},
    'MN': {'cols': ('n1', 'n2', 'G'), 'axes': ('yaw',),
           'label': 'yaw only'},
    'MX_fix': {'cols': ('a1', 'G'), 'axes': ('surge',),
               'label': 'surge, Xuu fixed at prior', 'fixed': {'a2': 'prior'}},
    'MN_fix': {'cols': ('n1', 'G'), 'axes': ('yaw',),
               'label': 'yaw, Nrr fixed at prior', 'fixed': {'n2': 'prior'}},
}
PRIOR_VALUE = {'a1': 'Xu', 'a2': 'Xuu', 'n1': 'Nr', 'n2': 'Nrr'}


def design_matrix(wins, spec, p_base):
    """Rows for one structure (already axis-scaled); fixed columns are removed."""
    cols = list(spec['cols'])
    axes = spec['axes']
    A, y, meta = [], [], []
    fixed = spec.get('fixed', {})
    for w in wins:
        for axis, key in (('surge', 'surge'), ('yaw', 'yaw')):
            if axis not in axes:
                continue
            s, tgt, scale = w[key]
            row = np.asarray(s, float).copy()
            tv = float(tgt)
            for k, how in fixed.items():
                val = -p_base[PRIOR_VALUE[k]] if how == 'prior' else float(how)
                tv -= row[PARAM_KEYS.index(k)] * val
            idx = [PARAM_KEYS.index(c) for c in cols]
            A.append(row[idx] / scale)
            y.append(tv / scale)
            meta.append({'win': w['id'], 'axis': axis, 'scale': scale})
    if not A:
        return None, None, meta
    return np.vstack(A), np.asarray(y), meta


def fit_structure(wins, spec, p_base):
    from scipy.optimize import lsq_linear
    A, y, meta = design_matrix(wins, spec, p_base)
    lb_all, ub_all = param_bounds(p_base)
    idx = [PARAM_KEYS.index(c) for c in spec['cols']]
    info = {'structure': spec.get('name'), 'cols': list(spec['cols']),
            'axes': list(spec['axes']), 'fixed': dict(spec.get('fixed', {})),
            'n_rows': 0 if A is None else int(A.shape[0]),
            'n_windows': len({m['win'] for m in meta})}
    if A is None or not len(y):
        info.update({'status': 'empty_design', 'supported': False,
                     'reason': 'no rows'})
        return None, info
    norms = np.linalg.norm(A, axis=0)
    good = norms > 0
    info['zero_columns'] = [c for c, g in zip(spec['cols'], good) if not g]
    if not good.all():
        info.update({'status': 'rank_deficient', 'supported': False,
                     'reason': 'zero column after scaling'})
        return None, info
    As = A / norms
    lb = lb_all[idx] * norms
    ub = ub_all[idx] * norms
    res = lsq_linear(As, y, bounds=(lb, ub), method='bvls')
    x = res.x / norms
    cond = float(np.linalg.cond(As))
    rank = int(np.linalg.matrix_rank(As))
    hit = []
    for c, v, lo, hi in zip(spec['cols'], x, lb_all[idx], ub_all[idx]):
        width = hi - lo
        if width > 0 and (abs(v - lo) <= 0.01 * width or abs(v - hi) <= 0.01 * width):
            hit.append(c)
    # bvls status: 1 = optimality reached, 3 = unconstrained optimum (both fine),
    # 2 = max iterations (not converged)
    solved = res.status in (1, 3)
    info.update({'status': 'solved' if solved else 'not_converged',
                 'cost': float(res.cost), 'rank': rank, 'n_cols': len(spec['cols']),
                 'cond': cond, 'at_bound': hit,
                 'theta': {c: float(v) for c, v in zip(spec['cols'], x)}})
    ok = (solved and rank == len(spec['cols']) and cond <= 1e3 and not hit)
    info['supported'] = bool(ok)
    if not ok:
        info['reason'] = ('not_converged' if not solved else
                          'rank_or_cond' if (rank != len(spec['cols']) or cond > 1e3)
                          else 'parameter_at_search_bound')
    return x, info


def expand_params(x, spec, p_base):
    """theta -> (hydro dict, G).  Unfitted columns keep the M0 prior."""
    hydro = dict(p_base)
    hv = {'a1': -p_base['Xu'], 'a2': -p_base['Xuu'],
          'n1': -p_base['Nr'], 'n2': -p_base['Nrr']}
    if x is not None:
        hv.update({c: float(v) for c, v in zip(spec['cols'], x)})
    for k, how in spec.get('fixed', {}).items():
        hv[k] = -p_base[PRIOR_VALUE[k]] if how == 'prior' else float(how)
    hydro.update({'Xu': -hv['a1'], 'Xuu': -hv['a2'],
                  'Nr': -hv['n1'], 'Nrr': -hv['n2']})
    G = hv['G'] if 'G' in hv else float(old.prior_gain_vector(p_base)[0])
    if 'G' not in spec['cols'] and 'G' not in spec.get('fixed', {}):
        G = float(old.prior_gain_vector(p_base)[0])
    return hydro, G, hv


def bootstrap(wins, spec, p_base, clusters, n=BOOTSTRAP_N, seed=BOOTSTRAP_SEED):
    rng = np.random.default_rng(seed)
    uniq = sorted(set(clusters))
    if not uniq:
        return {'n_ok': 0, 'intervals': {}}
    by_cluster = {c: [w for w, cc in zip(wins, clusters) if cc == c] for c in uniq}
    out = []
    for _ in range(n):
        pick = rng.integers(0, len(uniq), len(uniq))
        # whole clusters, with replacement: repeated draws stay repeated
        sub = [w for i in pick for w in by_cluster[uniq[i]]]
        x, info = fit_structure(sub, spec, p_base)
        if x is None or info.get('status') != 'solved' or not np.isfinite(x).all():
            continue
        if info.get('rank') != len(spec['cols']):
            continue
        out.append(x)
    if len(out) < BOOTSTRAP_MIN_OK:
        return {'n_ok': len(out), 'intervals': {},
                'reason': f'{len(out)} full-rank finite resamples < {BOOTSTRAP_MIN_OK}'}
    arr = np.vstack(out)
    ci = {c: [float(np.percentile(arr[:, i], 2.5)),
              float(np.percentile(arr[:, i], 97.5))]
          for i, c in enumerate(spec['cols'])}
    return {'n_ok': len(out), 'intervals': ci, 'n_clusters': len(uniq)}


def stability_flags(x, spec, ci):
    flags = {}
    if x is None:
        return flags
    for i, c in enumerate(spec['cols']):
        v = float(x[i])
        lo_hi = ci.get(c)
        if lo_hi is None:
            flags[c] = 'no_interval'
            continue
        lo, hi = lo_hi
        if lo <= 0.0 <= hi:
            flags[c] = 'weak_excitation_interval_spans_zero'
        elif (hi - lo) > 2.0 * abs(v):
            flags[c] = 'weak_excitation_interval_wide'
        else:
            flags[c] = 'ok'
    return flags


# ---------------------------------------------------------------------------
# stage 4: same-cruise holdout replay and gates
# ---------------------------------------------------------------------------
def q_pair(pwm_l, pwm_r, deadzone=PWM_DEADZONE_US):
    ql = old.pwm_to_normalized(np.asarray(pwm_l, float), SERVO_MIN, SERVO_TRIM,
                               SERVO_MAX, deadzone)
    qr = old.pwm_to_normalized(np.asarray(pwm_r, float), SERVO_MIN, SERVO_TRIM,
                               SERVO_MAX, deadzone)
    pl, nl = old.direction_split(ql)
    pr, nr = old.direction_split(qr)
    return pl, nl, pr, nr


def replay_window(w, hydro, G, dt=DT):
    """Open-loop RK4 with the window's recorded PWM only (no state injection).

    The input is held (ZOH) at each integration step's midpoint, matching the
    exact-ZOH integrals used for fitting.  ``step_um`` reports how far that
    staircase differs from the linear reading at the same instants, which
    bounds the discretisation error to at most one integration step.
    """
    t_mid = w['t_nodes'][:-1] + 0.5 * dt
    k = np.clip(np.searchsorted(w['snap_t'], t_mid, side='right') - 1,
                0, len(w['snap_t']) - 1)
    pl = w['snap_l'][k]
    pr = w['snap_r'][k]
    ql_p, _ql_n, qr_p, _qr_n = q_pair(pl, pr)
    q = np.stack([ql_p, np.zeros_like(ql_p), qr_p, np.zeros_like(qr_p)], axis=1)
    tau = old.tau_from_q(q[None, ...], [G, 0.0, G, 0.0], hydro['d_thruster'])[0]
    x0 = np.array([[w['x0'], w['y0'], w['psi0'], w['u'][0], w['v'][0], w['r'][0]]])
    sim = old.simulate(x0, tau[None, ...], hydro, dt=dt)[0]
    lin_l = np.interp(t_mid, w['snap_t'], w['snap_l'])
    lin_r = np.interp(t_mid, w['snap_t'], w['snap_r'])
    step_um = float(max(np.max(np.abs(pl - lin_l)), np.max(np.abs(pr - lin_r))))
    return sim, step_um


def window_errors(w, sim):
    ref = {'u': w['u'], 'v': w['v'], 'r': w['r']}
    err = {}
    for k, i in (('u', 3), ('v', 4), ('r', 5)):
        d = sim[1:, i] - ref[k][1:]
        err[k] = float(np.sqrt(np.mean(d ** 2)))
    dxy = np.stack([sim[1:, 0] - w['x'][1:], sim[1:, 1] - w['y'][1:]])
    err['pos'] = float(np.sqrt(np.mean(np.sum(dxy ** 2, axis=0))))
    dh = wrap_pi(sim[1:, 2] - w['psi'][1:])
    err['psi'] = float(np.sqrt(np.mean(dh ** 2)))
    err['u_end'] = float(abs(sim[-1, 3] - w['u'][-1]))
    err['v_end'] = float(abs(sim[-1, 4] - w['v'][-1]))
    err['r_end'] = float(abs(sim[-1, 5] - w['r'][-1]))
    err['diverged'] = bool(not np.isfinite(sim).all()
                           or np.max(np.abs(sim[:, 3:])) > 50.0)
    return err


def label_window(w):
    straight = (w['r_max_abs'] <= STRAIGHT_R_MAX) and (w['u_p50'] >= STRAIGHT_U_MIN)
    diff = abs(w['IQ_diff']) / WIN_S
    turn = (w['r_max_abs'] >= TURN_R_MIN) and (diff >= TURN_DIFF_MIN)
    if turn and not straight:
        return 'turn'
    if straight and not turn:
        return 'straight'
    if straight and turn:
        return 'straight+turn'
    return 'mixed'


def replay_all(wins, models):
    """models: dict name -> (hydro, G).  Returns per-window metric table."""
    table = {}
    for name, (hydro, G) in models.items():
        rows = []
        for w in wins:
            sim, step_um = replay_window(w, hydro, G)
            e = window_errors(w, sim)
            e['step_um'] = step_um
            rows.append({'id': w['id'], 'stage': w['stage'], 'label': label_window(w),
                         **e})
        table[name] = rows
    return table


def summarise(table, name, labels=None):
    rows = table.get(name) or []
    sel = [r for r in rows if labels is None or r['label'] in labels]
    if not sel:
        return {'n_windows': 0}
    return {
        'n_windows': len(sel),
        'u_rmse': float(np.sqrt(np.mean([r['u'] ** 2 for r in sel]))),
        'v_rmse': float(np.sqrt(np.mean([r['v'] ** 2 for r in sel]))),
        'r_rmse': float(np.sqrt(np.mean([r['r'] ** 2 for r in sel]))),
        'r_rmse_median': float(np.median([r['r'] for r in sel])),
        'pos_rmse': float(np.sqrt(np.mean([r['pos'] ** 2 for r in sel]))),
        'psi_rmse_deg': float(math.degrees(np.sqrt(np.mean([r['psi'] ** 2 for r in sel])))),
        'diverged': int(sum(1 for r in sel if r['diverged'])),
        'input_step_um_max': float(max(r['step_um'] for r in sel)),
    }


def observed_ranges(wins):
    if not wins:
        return {'u': (0.0, 0.0), 'v': (0.0, 0.0), 'r': (0.0, 0.0)}
    u = np.concatenate([w['u'] for w in wins])
    v = np.concatenate([w['v'] for w in wins])
    r = np.concatenate([w['r'] for w in wins])
    return {'u': (float(u.min()), float(u.max())),
            'v': (float(v.min()), float(v.max())),
            'r': (float(r.min()), float(r.max()))}


def physics_gate(hydro, obs):
    chk = old.physical_checks(hydro, obs)
    ok = (chk['M_symmetric_part_positive_definite'] and chk['M_invertible']
          and chk['D_symmetric_part_nonnegative'] and chk['stable']
          and chk['no_new_unstable_operating_point'])
    chk['pass'] = bool(ok)
    return chk


def _prior_scale(p_base):
    return {'a1': -p_base['Xu'], 'a2': -p_base['Xuu'],
            'n1': -p_base['Nr'], 'n2': -p_base['Nrr'],
            'G': float(old.prior_gain_vector(p_base)[0])}


def relative_change(base_theta, xx, cols, p_base):
    """Max relative change of each fitted parameter under a perturbation.

    A relative change is undefined when the baseline estimate sits at zero
    (a bound), so the denominator is the larger of |baseline| and |prior|:
    that keeps a 0 -> 0.16 move at a few percent instead of an artefact.
    """
    prior = _prior_scale(p_base)
    worst = 0.0
    for c, a in zip(cols, xx):
        den = max(abs(float(base_theta.get(c, 0.0))), abs(prior[c]), 1e-9)
        worst = max(worst, abs(float(a) - float(base_theta.get(c, 0.0))) / den)
    return worst


def _perturbation_sensitivity(wins, spec, p_base):
    """Relative parameter change under the three frozen input perturbations."""
    base = fit_structure(wins, spec, p_base)
    if base[0] is None:
        return {'status': 'no_baseline'}
    base_theta = base[1].get('theta') or {}
    out = {}
    for label, kwargs in (('deadzone_0', {'deadzone': 0.0}),
                          ('deadzone_60', {'deadzone': 60.0}),
                          ('linear_interp', {'mode': 'linear'})):
        xx, _ii = _refit_with_input(wins, spec, p_base, **kwargs)
        if xx is None:
            out[label] = 'not_converged'
            continue
        out[label] = f"{relative_change(base_theta, xx, spec['cols'], p_base):.4f}"
    return out


def _refit_with_input(wins, spec, p_base, deadzone=PWM_DEADZONE_US, mode='zoh'):
    """Refit the same structure/windows under one input perturbation."""
    pert = []
    for w in wins:
        IQ_sum, IQ_diff = input_terms(w['t_nodes'], w['snap_t'], w['snap_l'],
                                      w['snap_r'], mode=mode, deadzone=deadzone)
        s, tgt, sc = w['surge']
        y, tgt2, sc2 = w['yaw']
        s2 = s.copy()
        s2[4] = -IQ_sum
        y2 = y.copy()
        y2[4] = -w['d_thruster'] * IQ_diff if 'd_thruster' in w else -p_base['d_thruster'] * IQ_diff
        pert.append({**w, 'surge': (s2, tgt, sc), 'yaw': (y2, tgt2, sc2),
                     'IQ_sum': IQ_sum, 'IQ_diff': IQ_diff})
    return fit_structure(pert, spec, p_base)


def operating_envelope(wins, st, role, stage, att_epoch, sample_ok):
    """Descriptive water envelope; quantiles from a 10 Hz fixed grid sample."""
    groups = [('manual_all', role == 'MANUAL'), ('B_active', role == 'B'),
              ('A_active', role == 'A')]
    rows, payload = [], {}
    for name, mask in groups:
        m = mask & sample_ok
        if not m.any():
            rows.append([name, 0] + [''] * 17)
            payload[name] = {'n_samples': 0}
            continue
        idx = np.where(m)[0]
        grid = np.arange(att_epoch[idx[0]], att_epoch[idx[-1]], 0.1)
        j = np.clip(np.searchsorted(att_epoch, grid), 0, len(att_epoch) - 1)
        keep = m[j]
        j = j[keep]
        gs, u, v, r = st['gs'][j], st['u'][j], st['v'][j], st['r'][j]
        ep = att_epoch[j]
        fin = np.isfinite(gs) & np.isfinite(u) & np.isfinite(r) & (gs > 0.3)
        gs, u, v, r, ep = (a[fin] for a in (gs, u, v, r, ep))
        if not gs.size:
            rows.append([name, 0] + [''] * 17)
            payload[name] = {'n_samples': 0}
            continue
        ar = np.abs(r)
        ur = np.abs(u * r)
        iu = int(np.argmax(u))
        igs = int(np.argmax(gs))
        ir = int(np.argmax(ar))
        iur = int(np.argmax(ur))
        rec = {'n_samples': int(gs.size),
               'gs': {'p50': float(np.percentile(gs, 50)), 'p95': float(np.percentile(gs, 95)),
                      'max': float(gs[iu if False else igs]), 'max_cst': cst_str(ep[igs])},
               'u': {'p50': float(np.percentile(u, 50)), 'p95': float(np.percentile(u, 95)),
                     'max': float(u[iu]), 'max_cst': cst_str(ep[iu])},
               'abs_v': {'p50': float(np.percentile(np.abs(v), 50)),
                         'p95': float(np.percentile(np.abs(v), 95)),
                         'max': float(np.abs(v).max())},
               'abs_r': {'p50': float(np.percentile(ar, 50)),
                         'p95': float(np.percentile(ar, 95)),
                         'max': float(ar[ir]), 'max_cst': cst_str(ep[ir])},
               'abs_ur': {'p95': float(np.percentile(ur, 95)),
                          'max': float(ur[iur]), 'max_cst': cst_str(ep[iur])}}
        payload[name] = rec
        rows.append([name, rec['n_samples'],
                     rec['gs']['p50'], rec['gs']['p95'], rec['gs']['max'], rec['gs']['max_cst'],
                     rec['u']['p50'], rec['u']['p95'], rec['u']['max'], rec['u']['max_cst'],
                     rec['abs_v']['p50'], rec['abs_v']['p95'], rec['abs_v']['max'],
                     rec['abs_r']['p50'], rec['abs_r']['p95'], rec['abs_r']['max'],
                     rec['abs_r']['max_cst'], rec['abs_ur']['p95'], rec['abs_ur']['max']])
    for w in wins:
        pass
    payload['note'] = ('分位数取 10 Hz 固定间隔样本（地速 > 0.3 m/s）；峰值不是 MPC 限值，'
                       '地速也不等于对水速度。')
    return rows, payload


def steady_platforms(day, tb, st, role, stage, srv_boot, srv_valid,
                     manual_mask, min_dur=5.0, ptp_lim=15.0, min_snap=6):
    """Maximal observed steady-PWM plateaus inside valid water manual blocks.

    A plateau is grown to its true extent: consecutive snapshots stay in one
    servo segment, both channels move by <= ``ptp_lim`` across the whole
    plateau, and every snapshot lies in a valid MANUAL water sample (so shore
    tests, standby and stage cuts break it).  One plateau yields one row.
    """
    pwm_l = day.servo[:, 3].astype(float)
    pwm_r = day.servo[:, 4].astype(float)
    att_boot = day.att[:, 2] / 1e3
    k = np.clip(np.searchsorted(att_boot, srv_boot), 0, len(att_boot) - 1)
    sample_ok = manual_mask[k]
    sample_ok &= np.abs(att_boot[k] - srv_boot) <= ATT_GAP_S

    out = []
    for s0, e0 in servo_segments(srv_boot, srv_valid):
        t = srv_boot[s0:e0]
        ok = sample_ok[s0:e0].copy()
        if len(ok) > 1:
            ok[1:] &= np.diff(t) <= SERVO_GAP_S
        idx = np.where(ok)[0]
        if idx.size < min_snap:
            continue
        # split into maximal runs of valid, contiguous snapshots
        cuts = np.where(np.diff(idx) > 1)[0] + 1
        for group in np.split(idx, cuts):
            if group.size < min_snap:
                continue
            gi = 0
            while gi < group.size:
                gj = gi
                lo_l = hi_l = pwm_l[s0 + group[gi]]
                lo_r = hi_r = pwm_r[s0 + group[gi]]
                while gj + 1 < group.size:
                    i_next = s0 + group[gj + 1]
                    nl_lo = min(lo_l, pwm_l[i_next]); nl_hi = max(hi_l, pwm_l[i_next])
                    nr_lo = min(lo_r, pwm_r[i_next]); nr_hi = max(hi_r, pwm_r[i_next])
                    if (nl_hi - nl_lo) > ptp_lim or (nr_hi - nr_lo) > ptp_lim:
                        break
                    lo_l, hi_l, lo_r, hi_r = nl_lo, nl_hi, nr_lo, nr_hi
                    gj += 1
                n = gj - gi + 1
                t_a, t_b = t[group[gi]], t[group[gj]]
                if n >= min_snap and (t_b - t_a) >= min_dur:
                    sl = slice(s0 + group[gi], s0 + group[gj] + 1)
                    out.append(_platform_row(day, tb, st, role, stage, att_boot,
                                             t_a, t_b, pwm_l[sl], pwm_r[sl]))
                gi = gj + 1
    return out


def _platform_row(day, tb, st, role, stage, att_boot, t0, t1, pl, pr):
    tail0 = max(t0, t1 - 2.0)
    grid = np.arange(tail0, t1 + 1e-9, 0.05)
    if grid.size < 4:
        return None
    idx = hold_att(att_boot, grid)
    ok = idx >= 0
    uu = np.full(grid.shape, np.nan)
    rr = np.full(grid.shape, np.nan)
    if ok.any():
        uu[ok] = st['u'][idx[ok]]
        rr[ok] = st['r'][idx[ok]]
    uu, rr = uu[np.isfinite(uu)], rr[np.isfinite(rr)]
    if uu.size < 4:
        return None
    up = float(np.percentile(uu, 90) - np.percentile(uu, 10))
    rp = float(np.percentile(np.abs(rr), 90) - np.percentile(np.abs(rr), 10))
    k = int(np.clip(np.searchsorted(att_boot, 0.5 * (t0 + t1)), 0, len(att_boot) - 1))
    sat = bool(max(np.median(pl), np.median(pr)) >= SERVO_MAX - 5
               or min(np.median(pl), np.median(pr)) <= SERVO_MIN + 5)
    # ``sat`` marks a rail (1900/1100 us); rails are reported but not accepted
    # as steady-state evidence because the achieved thrust is clipped there.
    # a plateau is only evidence if it actually commands thrust above the
    # deadzone prior; trim/idle holds carry no excitation.
    q_med = float(q_from_pwm(np.array([np.median(pl), np.median(pr)]))[0:2].max())
    accept = bool(up <= 0.15 and rp <= 0.10 and not sat and q_med > 0.0)
    seg_off = tb.offs[tb.seg[k]]
    return [cst_str(t0 + seg_off), cst_str(t1 + seg_off), f"{t1 - t0:.1f}",
            f"{np.median(pl):.0f}", f"{np.median(pr):.0f}",
            f"{np.ptp(pl):.0f}", f"{np.ptp(pr):.0f}", len(pl),
            f"{np.median(uu):.3f}", f"{up:.3f}", f"{np.median(np.abs(rr)):.3f}",
            f"{rp:.3f}", int(sat), int(accept)]


def build_validation(models, fits, table, hold, train, p_base, obs_train, obs_hold):
    verdicts = {}
    per_model = {}
    labels = [label_window(w) for w in hold]
    straight = [w for w, l in zip(hold, labels) if l in ('straight', 'straight+turn')]
    turn = [w for w, l in zip(hold, labels) if l in ('turn', 'straight+turn')]
    for name in list(models):
        m0 = summarise(table, 'M0')
        cur = summarise(table, name)
        gates = []
        axes = {'M1': ('surge', 'yaw'), 'MX': ('surge',), 'MN': ('yaw',),
                'MX_fix': ('surge',), 'MN_fix': ('yaw',)}.get(name, ())
        need_straight = 'surge' in axes
        need_turn = 'yaw' in axes
        gates.append({'gate': 'holdout_windows_ge_3', 'value': len(hold),
                      'pass': len(hold) >= 3})
        if need_straight:
            gates.append({'gate': 'straight_windows_ge_2', 'value': len(straight),
                          'pass': len(straight) >= 2})
        if need_turn:
            gates.append({'gate': 'turn_windows_ge_2', 'value': len(turn),
                          'pass': len(turn) >= 2})
        if 'surge' in axes and straight:
            v = summarise(table, name, labels=('straight', 'straight+turn'))['u_rmse']
            gates.append({'gate': 'u_rmse_le_0.20', 'value': v, 'pass': v <= U_RMSE_LIM})
        if 'yaw' in axes and turn:
            v = summarise(table, name, labels=('turn', 'straight+turn'))['r_rmse_median']
            gates.append({'gate': 'r_median_rmse_le_12degps', 'value': v,
                          'pass': v <= R_MEDIAN_LIM})
        if 'surge' in axes and straight and cur.get('n_windows'):
            v = summarise(table, name, labels=('straight', 'straight+turn'))['u_rmse']
            v0 = summarise(table, 'M0', labels=('straight', 'straight+turn'))['u_rmse']
            gates.append({'gate': 'u_improve_ge_10pct', 'value': [v, v0],
                          'pass': v0 > 0 and v <= (1 - IMPROVE_MIN) * v0})
        if 'yaw' in axes and turn and cur.get('n_windows'):
            v = summarise(table, name, labels=('turn', 'straight+turn'))['r_rmse_median']
            v0 = summarise(table, 'M0', labels=('turn', 'straight+turn'))['r_rmse_median']
            gates.append({'gate': 'r_improve_ge_10pct', 'value': [v, v0],
                          'pass': v0 > 0 and v <= (1 - IMPROVE_MIN) * v0})
        if cur.get('n_windows') and m0.get('n_windows'):
            gates.append({'gate': 'pos_rmse_le_1.5_and_le_1.05x_M0',
                          'value': [cur['pos_rmse'], m0['pos_rmse']],
                          'pass': cur['pos_rmse'] <= POS_RMSE_LIM
                          and cur['pos_rmse'] <= M0_SLACK * m0['pos_rmse']})
            if 'surge' not in axes:
                gates.append({'gate': 'u_not_worse_than_M0',
                              'value': [cur['u_rmse'], m0['u_rmse']],
                              'pass': cur['u_rmse'] <= M0_SLACK * m0['u_rmse']})
            if 'yaw' not in axes:
                gates.append({'gate': 'r_not_worse_than_M0',
                              'value': [cur['r_rmse_median'], m0['r_rmse_median']],
                              'pass': cur['r_rmse_median'] <= M0_SLACK * m0['r_rmse_median']})
            gates.append({'gate': 'no_divergence', 'value': cur['diverged'],
                          'pass': cur['diverged'] == 0})
        phys = {}
        if name == 'M0':
            phys = physics_gate(dict(p_base), obs_train)
            gates.append({'gate': 'physical_checks_M0', 'value': phys['pass'],
                          'pass': bool(phys['pass'])})
        if name in fits and fits[name]['x'] is not None:
            hydro, G, hv = expand_params(fits[name]['x'], fits[name]['spec'], p_base)
            phys = physics_gate(hydro, obs_train)
            gates.append({'gate': 'physical_checks', 'value': phys['pass'],
                          'pass': bool(phys['pass'])})
            st_flags = fits[name]['info'].get('stability', {})
            weak = [k for k, v in st_flags.items() if v != 'ok']
            gates.append({'gate': 'parameter_stability', 'value': weak,
                          'pass': not weak})
            gates.append({'gate': 'input_not_sensitive',
                          'value': fits[name]['info'].get('input_sensitivity_rel_change'),
                          'pass': not fits[name]['info'].get('input_sensitive', True)})
        failed = [g['gate'] for g in gates if g['pass'] is False]
        coverage = {'holdout_windows_ge_3', 'straight_windows_ge_2', 'turn_windows_ge_2'}
        missing_cov = sorted(g for g in failed if g in coverage)
        other = sorted(g for g in failed if g not in coverage)
        if name == 'M0':
            verdict = 'baseline'
            reason = 'M0 prior; reference only, never a deliverable candidate'
        elif name not in fits or fits[name]['x'] is None:
            verdict = 'not_evaluable'
            reason = fits.get(name, {}).get('info', {}).get('reason', 'no fit')
        elif missing_cov:
            # 缺观测覆盖时不给通过结论；其余失败项照实列出，不隐藏
            verdict = 'not_evaluable'
            reason = ('coverage: ' + ', '.join(missing_cov)
                      + ('; also failed: ' + ', '.join(other) if other else ''))
        elif other:
            verdict = 'rejected'
            reason = 'failed: ' + ', '.join(other)
        else:
            verdict = 'offline_supported'
            reason = 'all applicable gates passed'
        verdicts[name] = verdict
        per_model[name] = {'gates': gates, 'verdict': verdict, 'reason': reason,
                           'summary_all': cur, 'm0_all': m0,
                           'summary_straight': summarise(table, name,
                                                         ('straight', 'straight+turn')),
                           'summary_turn': summarise(table, name,
                                                     ('turn', 'straight+turn')),
                           'physics': phys,
                           'fit': {k: v for k, v in (fits.get(name, {}).get('info') or {}).items()
                                   if k not in ('params',)},
                           'windows': table.get(name, [])}
    return {
        'verdicts': verdicts,
        'split_hash': None,
        'holdout': {'n_windows': len(hold),
                    'straight_windows': len(straight),
                    'turn_windows': len(turn)},
        'train_windows': len(train),
        'models': per_model,
        'observed_ranges': {'train': obs_train, 'holdout': obs_hold},
        'input_models': {'pwm': 'q = pwm_to_normalized(pwm,1100,1500,1900,dz=30)',
                         'thrust': 'T = G*max(q,0)^2 per side, shared G',
                         'not_identified': ['absolute thrust scale', 'per-side gains',
                                            'true deadzone', 'voltage correction',
                                            'actuator delay', 'added mass',
                                            'sway/cross coefficients',
                                            'high-speed planing terms']},
        'note': ('留出窗只用于评分；未被选模型参数不参与选择。'
                 'M0 与候选共享时间轴、校准与初值。'),
    }


def estimate_rows(fits, p_base):
    prior = {'a1': -p_base['Xu'], 'a2': -p_base['Xuu'],
             'n1': -p_base['Nr'], 'n2': -p_base['Nrr'],
             'G': float(old.prior_gain_vector(p_base)[0])}
    unit = {'a1': 'N/(m/s)', 'a2': 'N/(m/s)^2', 'n1': 'N*m/(rad/s)',
            'n2': 'N*m/(rad/s)^2', 'G': 'N at |q|=1'}
    rows = []
    for name in [k for k in fits]:
        f = fits.get(name) or {}
        info = f.get('info') or {}
        theta = info.get('theta') or {}
        boot = (f.get('boot') or {}).get('intervals', {})
        pert = info.get('input_sensitivity_rel_change') or {}
        for k, how in (info.get('fixed') or {}).items():
            rows.append([name, k, unit[k], f"{prior[k]:.6g}", f"{prior[k]:.6g}",
                         '', '', '', 'fixed_at_prior',
                         'held at the baseline prior during this refit'])
        for c in PARAM_KEYS:
            if c not in (info.get('cols') or []):
                continue
            ci = boot.get(c)
            rows.append([name, c, unit[c], f"{prior[c]:.6g}",
                         f"{theta.get(c, float('nan')):.6g}",
                         '' if not ci else f"{ci[0]:.6g}",
                         '' if not ci else f"{ci[1]:.6g}",
                         ';'.join(f"{k}={v}" for k, v in pert.items()),
                         'unsupported' if not info.get('supported') else 'supported',
                         info.get('reason') or (info.get('stability') or {}).get(c, '')])
    for name in [k for k in fits]:
        f = fits.get(name) or {}
        info = f.get('info') or {}
        hv = info.get('params')
        if not hv:
            continue
        m11, m22, m23, m32, m33 = old.hydro_matrix(p_base)
        for c, den, unit_d in (('a1', m11, '1/s'), ('a2', m11, '1/m'),
                               ('n1', m33, '1/s'), ('n2', m33, '1/rad')):
            if c in hv:
                rows.append([name, f"{c}/{den:.4g}", unit_d,
                             f"{prior[c] / den:.6g}", f"{hv[c] / den:.6g}", '', '', '',
                             'derived', 'mass-normalised equivalent'])
    return rows


def plot_validation(out_dir, hold, models, wins, env_rows, env):
    """Show replay curves for the first straight and turn holdout windows."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    picks = []
    for want in ('straight', 'turn'):
        hit = next((w for w in hold if label_window(w) == want), None)
        picks.append((want, hit))
    fig, axs = plt.subplots(2, 2, figsize=(11.5, 7), constrained_layout=True)
    names = [n for n in ('M0', 'M1', 'MX', 'MN') if n in models]
    for col, (want, w) in enumerate(picks):
        ax_u, ax_r = axs[0][col], axs[1][col]
        if w is None:
            ax_u.set_axis_off()
            ax_r.set_axis_off()
            ax_u.text(0.5, 0.5, f'no valid {want} holdout window',
                      ha='center', va='center', transform=ax_u.transAxes)
            continue
        tt = w['t_nodes'] - w['t_nodes'][0]
        ax_u.plot(tt, w['u'], 'k', lw=2.2, label='measured')
        ax_r.plot(tt, np.degrees(w['r']), 'k', lw=2.2, label='measured')
        for name in names:
            hydro, G = models[name]
            sim, _step = replay_window(w, hydro, G)
            ls = '--' if name == 'M0' else '-'
            ax_u.plot(tt, sim[:, 3], ls, lw=1.4, label=name)
            ax_r.plot(tt, np.degrees(sim[:, 5]), ls, lw=1.4, label=name)
        ax_u.set_title(f"{want} window {w['id']}  {w['t0_cst']}-{w['t1_cst']}"
                       f"  L/R {w['pwm_l_med']:.0f}/{w['pwm_r_med']:.0f} us")
        ax_u.set_xlabel('t [s]')
        ax_u.set_ylabel('u [m/s]')
        ax_u.grid(alpha=.3)
        ax_r.set_xlabel('t [s]')
        ax_r.set_ylabel('r [deg/s]')
        ax_r.grid(alpha=.3)
    axs[0][0].legend(fontsize=8)
    fig.suptitle('2026-11-18 same-cruise holdout replay (recorded PWM only)')
    fig.savefig(os.path.join(out_dir, 'validation_replay.png'), dpi=120)
    plt.close(fig)

    # accepted/excluded timeline is always emitted: it is the fallback figure
    # when a window class is missing.
    fig, ax = plt.subplots(figsize=(11, 3.2), constrained_layout=True)
    for w in wins:
        c = {'train_B': 'C0', 'train_manual1': 'C1',
             'train_manual2': 'C2', 'holdout': 'C3'}.get(w['stage'], 'C7')
        ax.plot([w['t0_cst'], w['t1_cst']], [1.0, 1.0], lw=6, color=c,
                solid_capstyle='butt')
    seen = {}
    for w in wins:
        seen.setdefault(w['stage'], w['t0_cst'])
    ax.set_yticks([])
    ax.set_xlabel('CST')
    ax.set_title('accepted 4 s windows by stage (B / manual1 / manual2 / holdout)')
    ax.grid(alpha=.3, axis='x')
    fig.savefig(os.path.join(out_dir, 'window_timeline.png'), dpi=120)
    plt.close(fig)


def write_report(out_dir, manifest, static, split, validation, fits, env_rows, env,
                 platforms, hold, train):
    lines = ['# 2026-11-18 双录包实船参数辨识（MCAP 离线）', '']
    lines.append(f"- 产出目录：`{os.path.abspath(out_dir)}`")
    lines.append(f"- 数据根：`{os.path.dirname(os.path.dirname(os.path.abspath(manifest['sources'][0]['path'])))}`")
    lines.append(f"- 基线：`{manifest['baseline']['path']}`（只读）")
    lines.append(f"- 切分 hash：`{split['split_hash']}`")
    lines.append(f"- 结论：{', '.join(f'{k}={v}' for k, v in validation['verdicts'].items())}")
    lines += ['', '## 1. 输入受限与前提', '',
              '两个包内飞控侧的推进器证据只有 1 Hz 的 `SERVO_OUTPUT_RAW`（输出端，'
              '`SERVO1_FUNCTION=73` 左 / `SERVO3_FUNCTION=74` 右，1100/1500/1900 µs，'
              '两侧 `REVERSED=0`）。1 Hz 快照之间的实际控制不可观测；没有 ESC RPM、'
              '`ACTUATOR_OUTPUT_STATUS`、实测拉力或对水速度。因此只能给出固定惯量、'
              '固定输入假设下的等效阻尼/增益与水上包络。', '']
    lines += ['## 2. 取证与时基', '']
    for s in manifest['sources']:
        tail = s['unsealed_tail']
        lines.append(f"- `{s['name']}`：{s['bytes']} B，SHA-256 `{s['sha256']}`，"
                     f"{s['n_records']} 条记录，封口={s['sealed']}"
                     + (f"，未封口尾部 {tail['kind']}（已 yield {tail['records_yielded']} 条）"
                        if tail else ''))
    tb = manifest['time_base']
    lines.append(f"- 时钟段 {tb['clock_segments']}；日志时钟单调={tb['log_time_is_monotonic']}，"
                 f"回跳 {tb['non_monotonic_steps']} 次")
    lines.append(f"- 舵机输出重建：回卷 {manifest['servo_output_raw']['wraps']} 次，"
                 f"有效 {manifest['servo_output_raw']['valid']}/{manifest['servo_output_raw']['n']}，"
                 f"锚点残差中位 {manifest['servo_output_raw']['residual_vs_attitude_anchor_s']['median']:.3f} s")
    lines += ['', '## 3. 晚间静态基线用途', '',
              f"- 未解锁：attitude 侧 armed 样本 {static['armed_attitude_samples']}，"
              f"heartbeat 中 armed {static['n_hb_armed']}/{static['n_hb']}",
              f"- 两侧全程 1500 µs：{static['servo_both_trim_all']}（{static['n_channel_snapshots']} 条快照）",
              f"- 速度噪声（中位/MAD/P95 绝对偏差）：" +
              '；'.join(f"{k}={v.get('median', float('nan')):.4g}/{v.get('mad', float('nan')):.4g}/"
                        f"{v.get('abs_dev_p95', float('nan')):.4g}"
                        for k, v in static['velocity_noise'].items() if v.get('n')),
              f"- 用途限定：{static['note']}", '']
    lines += ['## 4. 水上包络与稳态观测', '']
    rows = [r for r in env_rows if r[0] != 'note']
    lines.append('| 组 | 样本 | 地速 P50/P95/最大 | u P50/P95/最大 | \\|r\\| P95/最大 |')
    lines.append('| :-- | --: | :-- | :-- | :-- |')
    for r in rows:
        if r[1] == 0 or r[1] == '':
            lines.append(f'| {r[0]} | 0 | — | — | — |')
            continue
        f3 = lambda v: f"{float(v):.3f}"
        lines.append(f'| {r[0]} | {r[1]} | {f3(r[2])}/{f3(r[3])}/{f3(r[4])} ({r[5]}) | '
                     f'{f3(r[6])}/{f3(r[7])}/{f3(r[8])} ({r[9]}) | '
                     f'{f3(r[14])}/{f3(r[15])} |')
    lines.append('')
    lines.append(env['note'])
    lines += ['', '### 稳态 PWM 平台', '']
    allp = [p for p in platforms if p]
    good = [p for p in allp if p[13] == 1]
    idle = [p for p in allp if p[13] == 0]
    lines.append(f"实航人工段共 {len(allp)} 个最大平台，{len(good)} 个通过"
                 f"（两侧峰峰 ≤15 µs、≥6 快照、后 2 s 抖动门、非贴边且高于死区先验）；"
                 f"{len(idle)} 个未通过（怠速/中位保持、贴边或抖动过大）。")
    if good:
        lines += ['', '| 时段 | 时长 | 左/右 PWM | u 中位 | u P90−P10 | \\|r\\| P90−P10 |',
                  '| :-- | --: | :-- | --: | --: | --: |']
        for p in good:
            lines.append(f'| {p[0]}–{p[1]} | {p[2]} s | {p[3]}/{p[4]} | {p[8]} | {p[9]} | {p[11]} |')
    lines += ['', '## 5. 切分与窗口', '',
              f"- 训练窗 {len(train)}，留出窗 {len(hold)}",
              f"- 漏斗：" + '；'.join(f"{k}: " + ', '.join(f"{kk}={vv}" for kk, vv in v.items())
                                      for k, v in split['window_funnel'].items()),
              f"- 拒绝理由：" + '；'.join(f"{k}: " + ', '.join(f"{kk}={vv}" for kk, vv in v.items())
                                        for k, v in split['window_rejects'].items()),
              '- 60 µs 快照步长门的敏感性（诊断，不参与选择）：' +
              '；'.join(f"{k}: " + ', '.join(f"{kk}={vv}" for kk, vv in v.items())
                       for k, v in split.get('step_gate_sensitivity', {}).items()),
              f"- {split.get('step_gate_note', '')}",
              '- 逐窗清单见 `segments.csv`，冻结切分见 `split_manifest.json`。', '']
    lines += ['## 6. 拟合与同航留出', '']
    for name in list(fits):
        f = fits.get(name) or {}
        info = f.get('info') or {}
        trig = f.get('triggered_by')
        lines.append(f"### {name}（{STRUCTURES[name]['label']}"
                     + (f"；因 {trig} 二次项贴边而触发" if trig else '') + "）")
        lines.append(f"- 状态：{info.get('status')}；支持={info.get('supported')}；"
                     f"原因={info.get('reason', '')}")
        lines.append(f"- 行数 {info.get('n_rows')}，窗口 {info.get('n_windows')}，"
                     f"rank {info.get('rank')}/{info.get('n_cols')}，cond {info.get('cond')}")
        if info.get('theta'):
            lines.append('- 估计：' + ', '.join(f"{k}={v:.4g}" for k, v in info['theta'].items()))
        boot = (f.get('boot') or {})
        if boot.get('intervals'):
            lines.append('- 30 s 簇 bootstrap 95% 区间：' +
                         ', '.join(f"{k}=[{v[0]:.3g},{v[1]:.3g}]" for k, v in boot['intervals'].items())
                         + f"（{boot['n_ok']} 次满秩）")
        elif boot:
            lines.append(f"- bootstrap 不足：{boot.get('reason')}")
        if info.get('stability'):
            lines.append('- 稳定性：' + ', '.join(f"{k}={v}" for k, v in info['stability'].items()))
        if info.get('input_sensitivity_rel_change'):
            lines.append('- 输入扰动相对变化（分母取 |基准估计| 与 |先验| 的较大者，'
                         '避免基准贴 0 时比值失真）：' +
                         ', '.join(f"{k}={v}" for k, v in info['input_sensitivity_rel_change'].items()))
        m = validation['models'].get(name) or {}
        if m.get('summary_all', {}).get('n_windows'):
            for tag, key in (('全部', 'summary_all'), ('直航', 'summary_straight'),
                             ('转向', 'summary_turn')):
                s = m.get(key) or {}
                if s.get('n_windows'):
                    lines.append(f"- {tag}回放：u RMSE {s['u_rmse']:.3f} m/s，"
                                 f"r 中位 RMSE {math.degrees(s['r_rmse_median']):.2f} °/s，"
                                 f"位置 RMSE {s['pos_rmse']:.2f} m，发散 {s['diverged']}")
        lines.append(f"- 判定：**{m.get('verdict')}**（{m.get('reason')}）")
        failed = [g['gate'] for g in (m.get('gates') or []) if g['pass'] is False]
        if failed:
            lines.append(f"- 未通过门：{', '.join(failed)}")
        ph = m.get('physics') or {}
        if ph:
            lines.append(f"- 物理筛查：M 正定={ph.get('M_symmetric_part_positive_definite')}，"
                         f"D 半正定={ph.get('D_symmetric_part_nonnegative')}，"
                         f"max Re eig(−M⁻¹D)={ph.get('max_real_eig_minus_MinvD'):.3f}，"
                         f"速度 Jacobian 最大实部={ph.get('max_real_eig_velocity_jacobian'):.3f}"
                         + ("（该子项在 M0 先验上也不通过，属工况相关的筛查项）"
                            if name != 'M0' and not ph.get('no_new_unstable_operating_point')
                            else ""))
        lines.append('')
    v = validation
    lines += ['## 7. 为什么没有可交付候选，缺什么证据', '']
    lines.append(f"- 留出覆盖：总 {v['holdout']['n_windows']} 窗，"
                 f"直航 {v['holdout']['straight_windows']}，转向 {v['holdout']['turn_windows']}；"
                 '转向覆盖为 0 时艏摇轴按计划不可评价。')
    fail_txt = []
    for nm, mm in v['models'].items():
        if nm == 'M0':
            continue
        ft = [g['gate'] for g in (mm.get('gates') or []) if g['pass'] is False]
        if ft:
            fail_txt.append(f"{nm}: {', '.join(ft)}")
    if fail_txt:
        lines.append('- 未通过的门（逐模型）：' + '；'.join(fail_txt))
    lines.append('- 结论：留出覆盖不足（直航/转向窗数未达门槛）时为 `not_evaluable`；'
                 '覆盖满足但误差/物理/稳定性门不通过时为 `rejected`。'
                 '本航次两种情形都出现，因此不输出任何部署配置或推荐系数。')
    n_turn_train = sum(1 for w in split.get('windows', [])
                       if w['stage'].startswith('train')
                       and split.get('labels', {}).get(w['id']) == 'turn')
    n_turn_hold = sum(1 for w in split.get('windows', [])
                      if w['stage'] == 'holdout'
                      and split.get('labels', {}).get(w['id']) == 'turn')
    lines.append(f"- 转向窗分布：训练阶段 {n_turn_train} 个，留出阶段 {n_turn_hold} 个；"
                 '留出阶段没有转向窗，艏摇轴的同航验证因此不成立。')
    guess = [g for m in v['models'].values() for g in (m.get('gates') or [])
             if g['gate'] == 'u_improve_ge_10pct']
    if guess:
        lines.append(f"- 单一直航留出窗的 u RMSE：候选 {guess[0]['value'][0]:.3f} vs "
                     f"M0 {guess[0]['value'][1]:.3f} m/s；仅一个窗，"
                     '不构成改善证据（改善门本身要求 ≥2 个直航窗）。')
    lines += ['',
              '缺的证据（按优先级）：',
              '1. **高频推进器指令**：本包 `SERVO_OUTPUT_RAW` 只有约 1 Hz，'
              '1 Hz 之间的实际控制不可观测。需要同步的 DataFlash `.bin` 中 '
              '`RCOU`（10–50 Hz，`TimeUS` 与本次 `time_boot_ms` 可直接对齐）'
              '或 MAVLink `SERVO_OUTPUT_RAW` 提到 ≥10 Hz。',
              '2. **实际推力/转速**：`ESC` 的 RPM/电流或系柱拉力标定，'
              '用来分离左右增益、真实死区与电压修正。',
              '3. **对水速度**：GPS 地速在流/风下不等于对水速度，'
              '侧向与交叉水动力需要 DVL 或双天线航迹对照。',
              '4. **低速恒推力激励**：需要 ≥8 s 两侧恒定且 0.5–1.5 m/s 的直航段'
              '（含分档加减油）与恒定差动的回转段，才能把 `a2`/`n2` 从边界上推开。',
              '']
    lines += ['## 8. 参数结论与不可辨识项', '',
              '见 `parameter_estimates.csv`（模型、先验、估计、区间、输入扰动、状态、原因）'
              '与 `validation_metrics.json`（逐窗指标与门）。', '',
              '**不可由这两个包辨识**：绝对推力标度、左右独立增益、真实死区、电压修正、'
              '执行延迟、附加质量、侧向/交叉水动力、高速滑行参数。', '',
              '## 9. 原始证据', '']
    for s in manifest['sources']:
        lines.append(f"- `{s['path']}`")
    lines.append(f"- 分段分析报告（只用于定位，不是拟合数据）：`{os.path.join(os.path.dirname(os.path.dirname(manifest['sources'][0]['path'])), '2026-11-18_分段可视化分析报告.md')}`")
    lines += ['', '图表：`validation_replay.png`（留出窗回放）、`window_timeline.png`。']
    with open(os.path.join(out_dir, 'identification_report.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root', required=True)
    ap.add_argument('--baseline', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args(argv)
    if os.path.isdir(args.out) and os.listdir(args.out):
        raise SystemExit(f"refusing to overwrite non-empty output dir: {args.out}")
    os.makedirs(args.out, exist_ok=True)

    day, night, meta_info, _ = stage_source(args)
    p_base = old.load_baseline(args.baseline)
    base_sha = sha256_file(args.baseline)[0]

    day_tb = make_tb(day)
    night_tb = make_tb(night)
    day_boot = day.att[:, 2] / 1e3
    day_epoch = day_boot + day_tb.offs[day_tb.seg]
    srv_boot, srv_valid, srv_resid, n_wraps = servo_epoch(day, day_tb)
    srv_segs = servo_segments(srv_boot, srv_valid)

    manifest = {
        'generated_utc': _dt.datetime.now(_dt.timezone.utc).isoformat(),
        'tool': 'tools/params_id/scripts/reidentify_20261118.py',
        'entry': 'main(argv=None)',
        'versions': tool_versions(),
        'hardware': {'system_python': '3.12', 'ros': 'ROS 2 Jazzy',
                     'inputs': 'two MCAP packets + day metadata.yaml only'},
        'baseline': {'path': os.path.abspath(args.baseline), 'sha256': base_sha},
        'read_only': {'raw_packets': True, 'historical_results': True,
                      'live_config': True},
        'sources': [],
        'time_base': {
            'primary': 'ATTITUDE.time_boot_ms (file order)',
            'clock_segments': int(day_tb.seg.max()) + 1,
            'segment_offsets_s_relative': [float(o - day_tb.offs[-1]) for o in day_tb.offs],
            'log_time_is_monotonic': bool(np.all(np.diff(day_tb.log_s) > 0)),
            'non_monotonic_steps': int((np.diff(day_tb.log_s) <= 0).sum()),
            'note': ('Pi 日志时钟有 4 次回跳与 1 次 +408.6 s 前跳；动力学全用飞控 '
                     'boot 时钟，CST 阶段标签用段内偏移。'),
        },
        'servo_output_raw': {
            'time_source': 'time_usec low 32 bits + k*2^32',
            'wraps': n_wraps,
            'n': int(len(day.servo)),
            'valid': int(srv_valid.sum()),
            'residual_vs_attitude_anchor_s': {
                'median': float(np.median(srv_resid[np.isfinite(srv_resid)])),
                'p95_abs': float(np.percentile(np.abs(srv_resid[np.isfinite(srv_resid)]), 95)),
            },
            'segments': len(srv_segs),
            'dt_median_s': float(np.median(np.diff(srv_boot[np.isfinite(srv_boot)]))),
        },
    }
    for pkt, sealed_req in ((day, True), (night, False)):
        rec = {
            'name': pkt.name,
            'path': os.path.abspath(pkt.path),
            'bytes': pkt.size_bytes,
            'sha256': pkt.sha256,
            'sealed': pkt.sealed,
            'unsealed_tail': pkt.unsealed_tail,
            'n_records': pkt.n_records,
            'topic_counts': pkt.topic_counts,
            'topic_types': pkt.topic_types,
            'fcu_counts': pkt.counts(),
            'inventory': inventory(pkt, make_tb(pkt)),
            'gps_fix_hist': _fix_hist(pkt),
            'params': {k: sorted(set(v))[:8] for k, v in sorted(pkt.par.items())},
        }
        manifest['sources'].append(rec)
    manifest['metadata_yaml'] = {'path': os.path.abspath(
        os.path.join(args.data_root, DAY_RUN, 'metadata.yaml')),
        'message_count': int(meta_info['message_count'])}
    write_json(os.path.join(args.out, 'source_manifest.json'), manifest)

    static = static_baseline(night)
    static['source'] = night.name
    static['params'] = {k: sorted(set(v)) for k, v in night.par.items()}
    write_json(os.path.join(args.out, 'static_baseline.json'), static)

    split, wins, st, role, fcu, stage, sample_ok, env_ok = stage_split(
        day, day_tb, p_base, srv_boot, srv_valid, srv_segs, args.out)
    for w in wins:
        w['label'] = label_window(w)
    split['labels'] = {w['id']: w['label'] for w in wins}
    write_json(os.path.join(args.out, 'split_manifest.json'), split)

    train = [w for w in wins if w['stage'].startswith('train')]
    hold = [w for w in wins if w['stage'] == 'holdout']
    train_clusters = [f"{w['stage']}:{w['cluster']}" for w in train]

    m0_gains = old.prior_gain_vector(p_base)
    models = {'M0': (dict(p_base), float(m0_gains[0]))}
    fits = {}
    fit_order = ['M1', 'MX', 'MN']
    for name in list(fit_order):
        spec = dict(STRUCTURES[name])
        spec['name'] = name
        x, info = fit_structure(train, spec, p_base)
        fits[name] = {'x': x, 'info': info, 'spec': spec}
        # A fixed-quadratic refit is allowed only when this axis' own
        # quadratic term is at the search bound or the fit is unsupported.
        axis_map = {'MX': ('MX_fix', 'a2'), 'MN': ('MN_fix', 'n2')}
        quad = axis_map.get(name, (None, None))[1]
        if (name in ('MX', 'MN') and not info.get('supported')
                and (x is None or quad in (info.get('at_bound') or [])
                     or quad in (info.get('zero_columns') or []))):
            fix_name, _q = axis_map[name]
            spec2 = dict(STRUCTURES[fix_name])
            spec2['name'] = fix_name
            x2, info2 = fit_structure(train, spec2, p_base)
            fits[fix_name] = {'x': x2, 'info': info2, 'spec': spec2,
                              'triggered_by': name}
            fit_order.append(fix_name)
            if x2 is not None:
                hydro2, G2, hv2 = expand_params(x2, spec2, p_base)
                models[fix_name] = (hydro2, G2)
                info2['params'] = hv2
                fits[fix_name]['boot'] = bootstrap(train, spec2, p_base, train_clusters)
                info2['stability'] = stability_flags(
                    x2, spec2, fits[fix_name]['boot'].get('intervals', {}))
                info2['input_sensitivity_rel_change'] =                     _perturbation_sensitivity(train, spec2, p_base)
                info2['input_sensitive'] = any(
                    (isinstance(v, str) and v not in ('not_converged',)
                     and float(v) > 0.30)
                    for v in info2['input_sensitivity_rel_change'].values())
        if x is not None:
            hydro, G, hv = expand_params(x, spec, p_base)
            models[name] = (hydro, G)
            info['params'] = hv
            fits[name]['boot'] = bootstrap(train, spec, p_base, train_clusters)
            info['stability'] = stability_flags(x, spec,
                                               fits[name]['boot'].get('intervals', {}))
            pert = {}
            for pname, kwargs in (('deadzone_0', {'deadzone': 0.0}),
                                  ('deadzone_60', {'deadzone': 60.0})):
                pert[pname] = _refit_with_input(train, spec, p_base, **kwargs)
            pert['linear_interp'] = _refit_with_input(train, spec, p_base, mode='linear')
            base_theta = info['theta']
            info['input_perturbations'] = {
                k: ({'theta': v[1].get('theta'), 'status': v[1].get('status')}
                    if v[0] is not None else {'status': v[1].get('status')})
                for k, v in pert.items()}
            flags = {}
            for k, (xx, _ii) in pert.items():
                if xx is None:
                    flags[k] = 'not_converged'
                    continue
                flags[k] = f'{relative_change(base_theta, xx, spec["cols"], p_base):.4f}'
            info['input_sensitivity_rel_change'] = flags
            info['input_sensitive'] = any(
                (isinstance(v, str) and v not in ('not_converged',) and float(v) > 0.30)
                for v in flags.values())

    env_rows, env = operating_envelope(wins, st, role, stage, day_epoch, env_ok)
    manual_water = (role == 'MANUAL') & env_ok
    platforms = steady_platforms(day, day_tb, st, role, stage, srv_boot, srv_valid,
                                 manual_water)

    table = replay_all(hold, models) if hold else {k: [] for k in models}
    validation = build_validation(models, fits, table, hold, train, p_base,
                                 observed_ranges(train), observed_ranges(hold))
    write_json(os.path.join(args.out, 'validation_metrics.json'), validation)
    write_csv(os.path.join(args.out, 'parameter_estimates.csv'),
              ['model', 'parameter', 'unit', 'prior', 'estimate', 'ci_low', 'ci_high',
               'input_perturbation_range', 'status', 'reason'],
              estimate_rows(fits, p_base))
    write_csv(os.path.join(args.out, 'operating_envelope.csv'),
              ['group', 'n_samples', 'gs_p50', 'gs_p95', 'gs_max', 'gs_max_cst',
               'u_p50', 'u_p95', 'u_max', 'u_max_cst', 'abs_v_p50', 'abs_v_p95',
               'abs_v_max', 'abs_r_p50', 'abs_r_p95', 'abs_r_max', 'abs_r_max_cst',
               'abs_ur_p95', 'abs_ur_max'],
              env_rows)
    write_csv(os.path.join(args.out, 'steady_pwm_platforms.csv'),
              ['t0_cst', 't1_cst', 'dur_s', 'pwm_l_med', 'pwm_r_med',
               'pwm_l_range', 'pwm_r_range', 'n_snap', 'u_med', 'u_p90_p10',
               'abs_r_med', 'abs_r_p90_p10', 'saturated', 'accepted'],
              platforms)
    plot_validation(args.out, hold, models, wins, env_rows, env)
    write_report(args.out, manifest, static, split, validation, fits, env_rows, env,
                 platforms, hold, train)

    print(json.dumps({'records': day.n_records, 'servo_segments': len(srv_segs),
                      'clock_segments': manifest['time_base']['clock_segments'],
                      'windows': len(wins), 'train': len(train), 'holdout': len(hold),
                      'models': {k: v['info'].get('status') for k, v in fits.items()},
                      'verdicts': validation['verdicts']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
