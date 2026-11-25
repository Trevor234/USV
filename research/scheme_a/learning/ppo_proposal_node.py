#!/usr/bin/env python3
"""Read-only PPO preference proposal node & pure-Python inference engine (WP5).

Runs in system Python 3 with ROS 2 Jazzy (`rclpy`) + `onnxruntime`.
Never touches hardware commands directly; publishes bounded `ControlProposal`
messages on `/p1/control_proposal` with model SHA-256, `stamp_sim_ns`,
`target_tick`, confirmed-execution `prev_thrust`, and explicit `valid` status.
Missing, stale, or exiting proposal nodes never block the NMPC regulator.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np

DEFAULT_MODEL_PATH = Path("/home/trevor/USV/artifacts/rl_models/v7_fusion_v6/s4_dr/policy_physical_n.onnx")
DEFAULT_MANIFEST_PATH = Path("/home/trevor/USV/artifacts/rl_models/v7_fusion_v6/s4_dr/policy_physical_n.manifest.json")
OBS_CONTRACT_VERSION = "ppo-obs-v2"
PROPOSAL_SCHEMA = "p1-control-proposal-v1"
# 方案 A 闭环运行器生成的前瞻弧长偏移（部署侧历史契约）
SCHEME_A_LOOKAHEAD = (0.4, 0.8, 1.4, 2.2, 3.2, 4.4, 5.8, 7.5)
# usv_rl 训练环境使用的领先元组（v5 训练口径）
TRAINING_LOOKAHEAD = (0.4, 0.8, 1.2, 1.6, 2.0, 2.5, 3.0, 4.0)
DEFAULT_LOOKAHEAD = SCHEME_A_LOOKAHEAD
LOOKAHEAD_DIM = 8
LOOKAHEAD_MAX_M = 20.0
# 进度搜索窗口/距离门（与 usv_rl.observation.PROGRESS_WINDOW/PROGRESS_GATE_M 同值）
PROGRESS_WINDOW = 8
PROGRESS_GATE_M = 1.0
TICK_NS = 200_000_000
GATE_MODES = ("none", "curv_err", "curv_err_cmcap")
GATE_DEFAULTS = {
    "gate_mode": "none",
    "gate_min_kappa": 0.05,
    "gate_min_cte": 0.02,
    "gate_min_psi": 0.04,
    "gate_near_points": 4,
    "gate_cm_cap_margin": 0.5,
    "gate_u_lag_allow": 0.03,
}


def add_gate_arguments(parser: argparse.ArgumentParser, prefix: str = "") -> None:
    for name, default in GATE_DEFAULTS.items():
        choices = {"choices": GATE_MODES} if name == "gate_mode" else {}
        parser.add_argument(f"--{prefix}{name.replace('_', '-')}",
                            default=default, type=type(default), **choices)


def gate_cli_args(gate: dict[str, Any], prefix: str = "") -> list[str]:
    args = []
    for name, value in gate.items():
        args.extend((f"--{prefix}{name.replace('_', '-')}", str(value)))
    return args


def wrap_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def parse_lookahead(text: str) -> tuple[float, ...]:
    """解析逗号分隔的前瞻元组：必须 8 个、有限、严格递增、首值>0、末值<=20 m。"""
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) != LOOKAHEAD_DIM or any(p == "" for p in parts):
        raise ValueError(f"lookahead 必须是 {LOOKAHEAD_DIM} 个逗号分隔值，收到 {text!r}")
    try:
        vals = tuple(float(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"lookahead 含非数值项: {text!r}") from exc
    if not all(math.isfinite(v) for v in vals):
        raise ValueError(f"lookahead 含非有限值: {text!r}")
    if vals[0] <= 0.0:
        raise ValueError(f"lookahead 首值必须 > 0 m，收到 {vals[0]}")
    if vals[-1] > LOOKAHEAD_MAX_M:
        raise ValueError(f"lookahead 末值必须 <= {LOOKAHEAD_MAX_M} m，收到 {vals[-1]}")
    for a, b in zip(vals, vals[1:]):
        if b <= a:
            raise ValueError(f"lookahead 必须严格递增，违反处 {a} -> {b}")
    return vals


def advance_progress(
    ref_xs: np.ndarray,
    ref_ys: np.ndarray,
    x: float,
    y: float,
    prev_idx: int,
    window: int = PROGRESS_WINDOW,
    gate_m: float = PROGRESS_GATE_M,
) -> int:
    """最近点单调推进（窗口 + 距离门），与 usv_rl.observation.advance_progress 同语义。"""
    n = len(ref_xs)
    if n == 0:
        return 0
    prev_idx = int(min(max(int(prev_idx), 0), n - 1))
    hi = min(prev_idx + window, n - 1)
    idxs = np.arange(prev_idx, hi + 1)
    d2 = (ref_xs[idxs] - x) ** 2 + (ref_ys[idxs] - y) ** 2
    k = int(np.argmin(d2))
    if gate_m > 0.0 and float(d2[k]) > gate_m * gate_m:
        return prev_idx
    return int(idxs[k])


def compose_observation_scheme_a(
    state6: np.ndarray,
    ref_xs: np.ndarray,
    ref_ys: np.ndarray,
    ref_psis: np.ndarray,
    ref_kappas: np.ndarray,
    ref_v: np.ndarray,
    ref_r: np.ndarray,
    ref_s: np.ndarray,
    prog_idx: int,
    prev_thrust: np.ndarray,
    lookahead: tuple[float, ...] = DEFAULT_LOOKAHEAD,
) -> np.ndarray:
    """Assemble 43-D raw observation matching `usv_rl.observation.compose_observation`.

    契约 `ppo-obs-v2`：e_psi / v_ref / r_ref 三个通道一律取 `prog_idx`（单调推进的
    最近路径点），不再取时间轴索引 —— 时间索引在落后/超前时会给出与船实际状态
    错位的参考，且 rebase 平移量本身是未进入观测的隐藏状态。
    """
    x_s, y_s, psi, u, v, r = (float(v_) for v_ in state6)
    i_p = int(np.clip(prog_idx, 0, len(ref_psis) - 1))
    e_psi = wrap_angle(psi - float(ref_psis[i_p]))
    cos_p, sin_p = math.cos(psi), math.sin(psi)

    obs: list[float] = [
        u, v, r, sin_p, cos_p,
        math.sin(e_psi), math.cos(e_psi), float(ref_v[i_p]), float(ref_r[i_p]),
    ]

    s0 = float(ref_s[i_p])
    for off in lookahead:
        arc = s0 + float(off)
        i_k = int(np.clip(np.searchsorted(ref_s, arc, side="right") - 1, 0, len(ref_s) - 1))
        dx_w = float(ref_xs[i_k]) - x_s
        dy_w = float(ref_ys[i_k]) - y_s
        obs.extend([
            cos_p * dx_w + sin_p * dy_w,
            -sin_p * dx_w + cos_p * dy_w,
            float(ref_kappas[i_k]),
            float(ref_v[i_k]),
        ])

    obs.extend([float(prev_thrust[0]), float(prev_thrust[1])])
    return np.asarray(obs, dtype=np.float32)


@dataclass(frozen=True)
class ProposalOutput:
    schema_version: str
    run_id: str
    boot_id: str
    obs_contract_version: str
    ppo_model_sha256: str
    sequence: int
    target_tick: int
    stamp_sim_ns: int
    stamp_steady_ns: int
    valid_until_sim_ns: int
    q_pi: tuple[float, float]
    inference_ms: float
    valid: bool
    reason: str
    lookahead: tuple[float, ...] = DEFAULT_LOOKAHEAD


class ProposalEngine:
    """Stateful, ROS-free PPO proposal engine driven by confirmed plant execution feedback."""

    def __init__(
        self,
        *,
        onnx_path: Path = DEFAULT_MODEL_PATH,
        manifest_path: Path = DEFAULT_MANIFEST_PATH,
        run_id: str = "",
        boot_id: str = "",
        max_odom_age_ns: int = 200_000_000,
        validity_horizon_ns: int = 450_000_000,
        history_capacity: int = 256,
        thrust_bounds_n: tuple[float, float] = (-25.0, 25.0),
        lookahead: tuple[float, ...] = DEFAULT_LOOKAHEAD,
        gate_mode: str = GATE_DEFAULTS["gate_mode"],
        gate_min_kappa: float = GATE_DEFAULTS["gate_min_kappa"],
        gate_min_cte: float = GATE_DEFAULTS["gate_min_cte"],
        gate_min_psi: float = GATE_DEFAULTS["gate_min_psi"],
        gate_near_points: int = GATE_DEFAULTS["gate_near_points"],
        gate_cm_cap_margin: float = GATE_DEFAULTS["gate_cm_cap_margin"],
        gate_u_lag_allow: float = GATE_DEFAULTS["gate_u_lag_allow"],
        gate_ff_xu: float = -2.272063,
        gate_ff_xuu: float = -11.571784,
    ) -> None:
        import onnxruntime as ort

        self.run_id = run_id
        self.boot_id = boot_id
        self.max_odom_age_ns = int(max_odom_age_ns)
        self.validity_horizon_ns = int(validity_horizon_ns)
        self.thrust_bounds_n = (float(thrust_bounds_n[0]), float(thrust_bounds_n[1]))
        self.lookahead = parse_lookahead(",".join(str(v) for v in lookahead))
        if gate_mode not in GATE_MODES:
            raise ValueError(f"unsupported gate_mode: {gate_mode!r}")
        self.gate_mode = gate_mode
        self.gate_min_kappa = float(gate_min_kappa)
        self.gate_min_cte = float(gate_min_cte)
        self.gate_min_psi = float(gate_min_psi)
        self.gate_near_points = int(gate_near_points)
        self.gate_cm_cap_margin = float(gate_cm_cap_margin)
        self.gate_u_lag_allow = float(gate_u_lag_allow)
        self.gate_ff_xu = float(gate_ff_xu)
        self.gate_ff_xuu = float(gate_ff_xuu)
        if self.gate_near_points < 0:
            raise ValueError("gate_near_points must be nonnegative")
        if not all(math.isfinite(value) for value in (
            self.gate_min_kappa, self.gate_min_cte, self.gate_min_psi, self.gate_cm_cap_margin,
            self.gate_u_lag_allow, self.gate_ff_xu, self.gate_ff_xuu,
        )):
            raise ValueError("PPO gate parameters must be finite")

        onnx_path = Path(onnx_path)
        manifest_path = Path(manifest_path)
        if not onnx_path.is_file() or not manifest_path.is_file():
            raise FileNotFoundError(f"PPO model or manifest missing: {onnx_path}, {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        onnx_sha = hashlib.sha256(onnx_path.read_bytes()).hexdigest()
        if manifest.get("onnx_sha256") != onnx_sha:
            raise ValueError(f"PPO ONNX sha256 mismatch: actual={onnx_sha} manifest={manifest.get('onnx_sha256')}")
        self.ppo_model_sha256 = onnx_sha
        self.thrust_scale_n = float(manifest.get("thrust_scale_n", 25.0))

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        self._session = ort.InferenceSession(str(onnx_path), sess_options=opts, providers=["CPUExecutionProvider"])

        self._seq = 0
        self._clock_sim_ns: int | None = None
        self._odom_sim_ns: int | None = None
        self._odom_state: np.ndarray | None = None
        self._clock_epoch: int = 0
        self._prog_idx = 0

        self._ref_xs: np.ndarray | None = None
        self._ref_ys: np.ndarray | None = None
        self._ref_psis: np.ndarray | None = None
        self._ref_kappas: np.ndarray | None = None
        self._ref_vs: np.ndarray | None = None
        self._ref_rs: np.ndarray | None = None
        self._ref_ss: np.ndarray | None = None
        self._ref_ts: np.ndarray | None = None  # 仅取证/长度校验，观测不再使用

        # Bounded confirmed execution feedback queue: (execution_index, begin_sim_ns, end_sim_ns, thrust_n)
        self._confirmed_holds: deque[tuple[int, int, int, np.ndarray]] = deque(maxlen=max(8, int(history_capacity)))
        self._closed_exec_end: dict[int, int] = {}

    def on_clock(self, sim_ns: int) -> None:
        self._clock_sim_ns = int(sim_ns)

    def on_odom(self, stamp_sim_ns: int, state6: list[float] | np.ndarray) -> None:
        arr = np.asarray(state6, dtype=np.float64)
        if arr.shape != (6,) or not np.all(np.isfinite(arr)):
            return
        self._odom_sim_ns = int(stamp_sim_ns)
        self._odom_state = arr.copy()

    def on_reference(
        self,
        path_xypsi: np.ndarray,
        profile_rows: np.ndarray | None = None,
    ) -> None:
        p = np.asarray(path_xypsi, dtype=np.float64)
        if p.ndim != 2 or p.shape[0] < 2 or p.shape[1] < 3 or not np.all(np.isfinite(p)):
            return
        xs, ys, psis = p[:, 0], p[:, 1], p[:, 2]
        same_path = (
            self._ref_xs is not None
            and len(xs) == len(self._ref_xs)
            and np.array_equal(xs, self._ref_xs)
            and np.array_equal(ys, self._ref_ys)
            and np.array_equal(psis, self._ref_psis)
        )
        if profile_rows is not None and len(profile_rows) == len(xs):
            pr = np.asarray(profile_rows, dtype=np.float64)
            vs = pr[:, 0]
            rs = pr[:, 2]
            # ppo-obs-v2 不再用时间索引；ts 只保留作长度/一致性校验证据
            ts = pr[:, 3]
        else:
            ts = np.arange(len(xs), dtype=np.float64) * 0.2
            vs = np.full(len(xs), 0.6, dtype=np.float64)
            rs = np.zeros(len(xs), dtype=np.float64)
        same_profile = (
            same_path
            and self._ref_vs is not None
            and np.array_equal(vs, self._ref_vs)
            and np.array_equal(rs, self._ref_rs)
        )
        if same_profile:
            return

        ds = np.hypot(np.diff(xs), np.diff(ys))
        ss = np.concatenate([[0.0], np.cumsum(ds)])
        kappas = np.divide(rs, np.maximum(np.abs(vs), 0.1))
        self._ref_xs, self._ref_ys, self._ref_psis = xs, ys, psis
        self._ref_kappas, self._ref_vs, self._ref_rs = kappas, vs, rs
        self._ref_ss, self._ref_ts = ss, ts
        if not same_path:
            self._prog_idx = 0
        else:
            self._prog_idx = min(max(self._prog_idx, 0), len(xs) - 1)

    def on_plant_receipt(
        self,
        *,
        schema_version: str,
        disposition: str,
        execution_index: int,
        state_sample_sim_ns: int,
        planned_window_end_sim_ns: int,
        thrust_n: list[float] | np.ndarray,
        clock_epoch: int,
    ) -> None:
        if schema_version != "p1-plant-receipt-v3" or disposition != "ok" or execution_index <= 0:
            return
        q = np.asarray(thrust_n, dtype=np.float64)
        if q.shape != (2,) or not np.all(np.isfinite(q)):
            return
        self._clock_epoch = int(clock_epoch)
        self._confirmed_holds.append((int(execution_index), int(state_sample_sim_ns), int(planned_window_end_sim_ns), q.copy()))

    def on_hold_close(
        self,
        *,
        schema_version: str,
        execution_index: int,
        close_sim_ns: int,
        clock_epoch: int,
    ) -> None:
        if schema_version != "p1-plant-hold-close-v2" or execution_index <= 0:
            return
        if len(self._closed_exec_end) >= 512:
            # Drop oldest key deterministically to keep memory strictly bounded.
            oldest = next(iter(self._closed_exec_end))
            del self._closed_exec_end[oldest]
        self._closed_exec_end[int(execution_index)] = int(close_sim_ns)

    def confirmed_prev_thrust(self, at_sim_ns: int) -> np.ndarray:
        """Determine last confirmed executed thrust as of `at_sim_ns` under hold-window semantics."""
        for exec_idx, begin_ns, end_ns, q in reversed(self._confirmed_holds):
            effective_end = min(end_ns, self._closed_exec_end.get(exec_idx, end_ns))
            # Check confirmed hold active or most recently completed interval right at boundary.
            if begin_ns < at_sim_ns <= effective_end:
                return q.copy()
            if begin_ns <= at_sim_ns <= effective_end and effective_end > begin_ns:
                return q.copy()
        return np.zeros(2, dtype=np.float64)

    def _gate_low_demand(self) -> bool:
        idx = self._prog_idx
        x, y, psi = self._odom_state[:3]
        e_psi = abs(wrap_angle(float(psi - self._ref_psis[idx])))
        near_arcs = self._ref_ss[idx] + np.asarray(self.lookahead[:self.gate_near_points])
        near_indices = np.searchsorted(self._ref_ss, near_arcs, side="right") - 1
        kappa_near = max(abs(self._ref_kappas[idx]), np.max(np.abs(self._ref_kappas[near_indices]), initial=0.0))

        window = slice(max(0, idx - 2), min(len(self._ref_xs), idx + 5))
        points = np.column_stack((self._ref_xs[window], self._ref_ys[window]))
        segments = np.diff(points, axis=0)
        offsets = np.array([x, y]) - points[:-1]
        lengths_sq = np.sum(segments ** 2, axis=1)
        fractions = np.divide(np.sum(offsets * segments, axis=1), lengths_sq,
                              out=np.zeros_like(lengths_sq), where=lengths_sq > 0.0)
        errors = offsets - np.clip(fractions, 0.0, 1.0)[:, None] * segments
        e_ct = float(np.min(np.hypot(errors[:, 0], errors[:, 1])))
        return kappa_near < self.gate_min_kappa and e_ct < self.gate_min_cte and e_psi < self.gate_min_psi

    def evaluate(self, steady_now_ns: int | None = None) -> ProposalOutput:
        self._seq += 1
        st_ns = int(steady_now_ns if steady_now_ns is not None else time.monotonic_ns())
        now_sim = self._clock_sim_ns

        def invalid(reason: str) -> ProposalOutput:
            sim_v = int(now_sim if now_sim is not None else -1)
            return ProposalOutput(
                schema_version=PROPOSAL_SCHEMA,
                run_id=self.run_id,
                boot_id=self.boot_id,
                obs_contract_version=OBS_CONTRACT_VERSION,
                ppo_model_sha256=self.ppo_model_sha256,
                sequence=self._seq,
                target_tick=max(1, (max(0, sim_v) // TICK_NS) + 1),
                stamp_sim_ns=sim_v,
                stamp_steady_ns=st_ns,
                valid_until_sim_ns=sim_v,
                q_pi=(0.0, 0.0),
                inference_ms=0.0,
                valid=False,
                reason=reason[:64],
                lookahead=self.lookahead,
            )

        if now_sim is None:
            return invalid("clock_missing")
        if self._odom_state is None or self._odom_sim_ns is None:
            return invalid("odom_missing")
        age = abs(now_sim - self._odom_sim_ns)
        if age > self.max_odom_age_ns:
            return invalid("odom_stale")
        if self._ref_xs is None or self._ref_ss is None:
            return invalid("reference_missing")

        self._prog_idx = advance_progress(
            self._ref_xs, self._ref_ys, float(self._odom_state[0]), float(self._odom_state[1]),
            self._prog_idx, window=PROGRESS_WINDOW, gate_m=PROGRESS_GATE_M,
        )
        prev_q = self.confirmed_prev_thrust(self._odom_sim_ns)
        obs = compose_observation_scheme_a(
            self._odom_state,
            self._ref_xs,
            self._ref_ys,
            self._ref_psis,
            self._ref_kappas,
            self._ref_vs,
            self._ref_rs,
            self._ref_ss,
            prog_idx=self._prog_idx,
            prev_thrust=prev_q,
            lookahead=self.lookahead,
        )
        if not np.all(np.isfinite(obs)):
            return invalid("nonfinite_obs")
        if self.gate_mode != "none" and self._gate_low_demand():
            return invalid("gate_low_demand")

        t0 = time.perf_counter()
        raw = self._session.run(["thrust"], {"obs": obs[None, :]})[0][0]
        t1 = time.perf_counter()
        infer_ms = (t1 - t0) * 1e3

        if not np.all(np.isfinite(raw)):
            return invalid("nonfinite_onnx_output")

        lo, hi = self.thrust_bounds_n
        q0, q1 = float(raw[0]), float(raw[1])
        if self.gate_mode == "curv_err_cmcap":
            v_pos = max(0.0, float(self._ref_vs[self._prog_idx]))
            u_cur = float(self._odom_state[3])
            if u_cur >= v_pos - self.gate_u_lag_allow:
                u_ff_single = 0.5 * (-self.gate_ff_xu * v_pos - self.gate_ff_xuu * v_pos ** 2)
                cm, dm = 0.5 * (q0 + q1), 0.5 * (q1 - q0)
                cap = u_ff_single + self.gate_cm_cap_margin
                if cm > cap:
                    q0, q1 = cap - dm, cap + dm
        q0 = float(np.clip(q0, lo, hi))
        q1 = float(np.clip(q1, lo, hi))
        target_tick = int((now_sim // TICK_NS) + 1)
        return ProposalOutput(
            schema_version=PROPOSAL_SCHEMA,
            run_id=self.run_id,
            boot_id=self.boot_id,
            obs_contract_version=OBS_CONTRACT_VERSION,
            ppo_model_sha256=self.ppo_model_sha256,
            sequence=self._seq,
            target_tick=target_tick,
            stamp_sim_ns=now_sim,
            stamp_steady_ns=st_ns,
            valid_until_sim_ns=now_sim + self.validity_horizon_ns,
            q_pi=(q0, q1),
            inference_ms=infer_ms,
            valid=True,
            reason="ok",
            lookahead=self.lookahead,
        )


def run_ros_node(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--boot-id", default="")
    parser.add_argument("--model", default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--rate-hz", type=float, default=20.0)
    parser.add_argument("--topic-out", default="/p1/control_proposal")
    parser.add_argument("--log-file", default="")
    parser.add_argument("--lookahead", default="",
                        help="8 个逗号分隔的前瞻弧长偏移（m）；空 = DEFAULT_LOOKAHEAD")
    parser.add_argument("--allow-lookahead-mismatch", action="store_true",
                        help="允许请求的前瞻元组与模型 manifest 的 observation_contract 不一致")
    add_gate_arguments(parser)
    parser.add_argument("--gate-ff-xu", type=float, default=-2.272063)
    parser.add_argument("--gate-ff-xuu", type=float, default=-11.571784)
    args, ros_args = parser.parse_known_args(argv)

    try:
        requested_lookahead = parse_lookahead(args.lookahead) if args.lookahead else DEFAULT_LOOKAHEAD
    except ValueError as exc:
        parser.error(str(exc))
    manifest_doc = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    contract_la = (manifest_doc.get("observation_contract") or {}).get("lookahead_m")
    if contract_la is not None:
        bound = tuple(float(v) for v in contract_la)
        if bound != requested_lookahead and not args.allow_lookahead_mismatch:
            parser.error(
                f"请求的 lookahead {requested_lookahead} 与 manifest 绑定的 {bound} 不一致；"
                "确认要跨契约运行请加 --allow-lookahead-mismatch"
            )

    import rclpy
    from rclpy.executors import ExternalShutdownException
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from nav_msgs.msg import Odometry, Path as NavPath
    from rosgraph_msgs.msg import Clock
    from std_msgs.msg import Float64MultiArray
    from usv_research_interfaces.msg import ControlProposal, PlantHoldClose, PlantReceipt

    class PpoProposalRosNode(Node):
        def __init__(self) -> None:
            super().__init__("p1_ppo_proposal_node")
            self.declare_parameter("run_id", args.run_id)
            self.declare_parameter("boot_id", args.boot_id)
            run_id = self.get_parameter("run_id").get_parameter_value().string_value
            boot_id = self.get_parameter("boot_id").get_parameter_value().string_value
            self.engine = ProposalEngine(
                onnx_path=Path(args.model),
                manifest_path=Path(args.manifest),
                run_id=run_id,
                boot_id=boot_id,
                lookahead=requested_lookahead,
                gate_ff_xu=args.gate_ff_xu,
                gate_ff_xuu=args.gate_ff_xuu,
                **{name: getattr(args, name) for name in GATE_DEFAULTS},
            )
            self._path_xypsi: np.ndarray | None = None
            self._profile_rows: np.ndarray | None = None

            latched_qos = QoSProfile(
                depth=16,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            sensor_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)

            self.pub = self.create_publisher(ControlProposal, args.topic_out, 4)
            self.sub_clock = self.create_subscription(Clock, "/clock", self._on_clock, sensor_qos)
            self.sub_odom = self.create_subscription(
                Odometry, "/wamv/sensors/position/ground_truth_odometry", self._on_odom, sensor_qos
            )
            self.sub_path = self.create_subscription(NavPath, "/path/reference", self._on_path, 4)
            self.sub_prof = self.create_subscription(Float64MultiArray, "/path/reference_profile", self._on_profile, 4)
            self.sub_rec = self.create_subscription(PlantReceipt, "/p1/plant_receipt", self._on_receipt, latched_qos)
            self.sub_hc = self.create_subscription(PlantHoldClose, "/p1/plant_hold_close", self._on_hold_close, latched_qos)
            self.timer = self.create_timer(1.0 / max(1.0, args.rate_hz), self._on_timer)
            self._log_handle = open(args.log_file, "a", encoding="utf-8") if args.log_file else None

        def _on_clock(self, msg: Clock) -> None:
            self.engine.on_clock(int(msg.clock.sec) * 1_000_000_000 + int(msg.clock.nanosec))

        def _on_odom(self, msg: Odometry) -> None:
            stamp_ns = int(msg.header.stamp.sec) * 1_000_000_000 + int(msg.header.stamp.nanosec)
            qz = float(msg.pose.pose.orientation.z)
            qw = float(msg.pose.pose.orientation.w)
            psi = 2.0 * math.atan2(qz, qw)
            st = [
                float(msg.pose.pose.position.x),
                float(msg.pose.pose.position.y),
                psi,
                float(msg.twist.twist.linear.x),
                float(msg.twist.twist.linear.y),
                float(msg.twist.twist.angular.z),
            ]
            self.engine.on_odom(stamp_ns, st)

        def _on_path(self, msg: NavPath) -> None:
            rows = []
            for ps in msg.poses:
                psi = 2.0 * math.atan2(float(ps.pose.orientation.z), float(ps.pose.orientation.w))
                rows.append([float(ps.pose.position.x), float(ps.pose.position.y), psi])
            if len(rows) >= 2:
                self._path_xypsi = np.asarray(rows, dtype=np.float64)
                self.engine.on_reference(self._path_xypsi, self._profile_rows)

        def _on_profile(self, msg: Float64MultiArray) -> None:
            if len(msg.data) >= 8 and len(msg.data) % 4 == 0:
                self._profile_rows = np.asarray(msg.data, dtype=np.float64).reshape(-1, 4)
                if self._path_xypsi is not None:
                    self.engine.on_reference(self._path_xypsi, self._profile_rows)

        def _on_receipt(self, msg: PlantReceipt) -> None:
            self.engine.on_plant_receipt(
                schema_version=str(msg.schema_version),
                disposition=str(msg.disposition),
                execution_index=int(msg.execution_index),
                state_sample_sim_ns=int(msg.state_sample_sim_ns),
                planned_window_end_sim_ns=int(msg.planned_window_end_sim_ns),
                thrust_n=[float(msg.thrust_n[0]), float(msg.thrust_n[1])],
                clock_epoch=int(msg.clock_epoch),
            )

        def _on_hold_close(self, msg: PlantHoldClose) -> None:
            self.engine.on_hold_close(
                schema_version=str(msg.schema_version),
                execution_index=int(msg.execution_index),
                close_sim_ns=int(msg.close_sim_ns),
                clock_epoch=int(msg.clock_epoch),
            )

        def _on_timer(self) -> None:
            prop = self.engine.evaluate()
            msg = ControlProposal()
            msg.schema_version = prop.schema_version
            msg.run_id = prop.run_id
            msg.boot_id = prop.boot_id
            msg.obs_contract_version = prop.obs_contract_version
            msg.ppo_model_sha256 = prop.ppo_model_sha256
            msg.sequence = prop.sequence
            msg.target_tick = prop.target_tick
            msg.stamp_sim_ns = prop.stamp_sim_ns
            msg.stamp_steady_ns = prop.stamp_steady_ns
            msg.valid_until_sim_ns = prop.valid_until_sim_ns
            msg.q_pi = [prop.q_pi[0], prop.q_pi[1]]
            msg.inference_ms = prop.inference_ms
            msg.valid = prop.valid
            msg.reason = prop.reason
            self.pub.publish(msg)
            if self._log_handle is not None:
                self._log_handle.write(json.dumps(prop.__dict__, sort_keys=True) + "\n")
                self._log_handle.flush()

        def close(self) -> None:
            if self._log_handle is not None:
                self._log_handle.close()
                self._log_handle = None

    rclpy.init(args=ros_args)
    node = PpoProposalRosNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_ros_node())
