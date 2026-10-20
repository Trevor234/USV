#!/usr/bin/env python3
"""方案C: RL 策略推理节点（与 usv_mpc_cpp mpc_node 接口对齐）。

订阅（与 mpc_node 相同契约）:
    odom_topic     nav_msgs/Odometry        [x,y,psi,u,v,r]
    imu_topic      sensor_msgs/Imu          angular_velocity.z 覆盖 r
    path_topic     nav_msgs/Path            /path/reference
    profile_topic  std_msgs/Float64MultiArray  M×4 [v,kappa,r,t]（stamp 在 layout.dim）

发布:
    left/right thrust  std_msgs/Float64     推力 N（vrx_thrust 模式，1:1）
    status_topic       std_msgs/String      与 /mpc/status 同构 JSON（safety 看门狗兼容）

推理: ONNX（训练侧 usv_rl.export_policy 导出，内含 VecNormalize 归一化）。
执行约束与 MPC 一致: ±T_max clamp + dT_max 速率限制（usv_rl.observation.apply_thrust_limits）。

依赖（部署机 pip）: onnxruntime、numpy、pyyaml、usv_rl（观测单一真源，pip install ../usv_rl）。
"""
from __future__ import annotations

import json
import hashlib
import math
import time
from pathlib import Path

import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Quaternion
from nav_msgs.msg import Odometry
from nav_msgs.msg import Path as PathMsg
from sensor_msgs.msg import Imu
from std_msgs.msg import Float64, String
from std_msgs.msg import Float64MultiArray

from usv_rl.observation import advance_progress, apply_thrust_limits, compose_observation

try:  # 观测单一真源里的默认前瞻配置
    from usv_rl.envs.usv_tracking_env import DEFAULT_LOOKAHEAD
except ImportError:  # usv_rl 未装完整依赖时兜底
    DEFAULT_LOOKAHEAD = (0.4, 0.8, 1.2, 1.6, 2.0, 2.5, 3.0, 4.0)


def yaw_from_quaternion(q: Quaternion) -> float:
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


def load_policy_contract(model_path: str | Path, t_max: float) -> dict:
    """Validate the hash-bound physical-N deployment contract before inference."""
    model_path = Path(model_path)
    manifest_path = model_path.with_suffix(".manifest.json")
    try:
        contract = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read policy manifest: {manifest_path}") from exc
    if not isinstance(contract, dict):
        raise ValueError("policy manifest must be a JSON object")
    expected = {
        "contract_version": 1, "output_unit": "N",
        "action_order": ["T_L", "T_R"],
        "input_name": "obs", "input_dim": 43,
        "output_name": "thrust", "output_dim": 2,
        "normalization_embedded": True,
    }
    for name, value in expected.items():
        actual = contract.get(name)
        # bool is an int in Python; reject it for dimensions/version.
        if type(actual) is not type(value) or actual != value:
            raise ValueError(f"invalid policy contract {name}: {actual!r}")
    if not math.isfinite(t_max) or not math.isclose(t_max, 25.0, abs_tol=1e-6):
        raise ValueError("this physical-N contract requires current t_max=25 N")
    scale = contract.get("thrust_scale_n")
    if (isinstance(scale, bool) or not isinstance(scale, (int, float))
            or not math.isfinite(scale)
            or not math.isclose(scale, 25.0, abs_tol=1e-6)):
        raise ValueError("policy thrust_scale_n must be 25 N")
    for name, value in (("physical_low_n", [-25.0, -25.0]),
                        ("physical_high_n", [25.0, 25.0])):
        actual = contract.get(name)
        if (not isinstance(actual, list) or len(actual) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v)
                       or not math.isclose(v, ref, abs_tol=1e-6)
                       for v, ref in zip(actual, value))):
            raise ValueError(f"invalid policy contract {name}: {actual!r}")
    actual_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if contract.get("onnx_sha256") != actual_hash:
        raise ValueError("policy ONNX SHA256 does not match manifest")
    return contract


def validate_policy_session(session, contract: dict) -> None:
    """Check the real ORT interface and any declared graph unit metadata."""
    for args, name, dim in ((session.get_inputs(), "obs", 43),
                            (session.get_outputs(), "thrust", 2)):
        if len(args) != 1:
            raise ValueError(f"policy must have exactly one {name} tensor")
        arg = args[0]
        shape = arg.shape
        if (arg.name != name or arg.type != "tensor(float)"
                or not isinstance(shape, (tuple, list)) or len(shape) != 2
                or shape[1] != dim
                or not (shape[0] is None or isinstance(shape[0], str)
                        or (type(shape[0]) is int and shape[0] == 1))):
            raise ValueError(f"invalid policy tensor {name}: {arg.name}, {arg.type}, {shape}")
    metadata = session.get_modelmeta().custom_metadata_map or {}
    expected = {
        "usv.contract_version": str(contract["contract_version"]),
        "usv.output_unit": contract["output_unit"],
        "usv.action_order": ",".join(contract["action_order"]),
        "usv.input_dim": str(contract["input_dim"]),
        "usv.output_dim": str(contract["output_dim"]),
    }
    for name, value in expected.items():
        if name in metadata and metadata[name] != value:
            raise ValueError(f"ONNX metadata disagrees with manifest: {name}")
    if "usv.thrust_scale_n" in metadata:
        try:
            scale = float(metadata["usv.thrust_scale_n"])
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid ONNX thrust scale metadata") from exc
        if not math.isfinite(scale) or not math.isclose(
                scale, contract["thrust_scale_n"], abs_tol=1e-6):
            raise ValueError("ONNX thrust scale metadata disagrees with manifest")


class RlPolicyNode(Node):
    def __init__(self, *, parameter_overrides=None) -> None:
        super().__init__("rl_policy_node", parameter_overrides=parameter_overrides)

        self.declare_parameter("model_path", "")
        self.declare_parameter("odom_topic", "/wamv/sensors/position/ground_truth_odometry")
        self.declare_parameter("imu_topic", "/wamv/sensors/imu/imu/data")
        self.declare_parameter("path_topic", "/path/reference")
        self.declare_parameter("profile_topic", "/path/reference_profile")
        self.declare_parameter("left_thrust_topic", "/wamv/thrusters/left/thrust")
        self.declare_parameter("right_thrust_topic", "/wamv/thrusters/right/thrust")
        self.declare_parameter("status_topic", "/mpc/status")
        self.declare_parameter("control_rate_hz", 5.0)
        self.declare_parameter("t_max", 25.0)
        self.declare_parameter("d_t_max", 80.0)
        self.declare_parameter("cruise_speed", 0.6)
        self.declare_parameter("schedule_rebase_m", 2.0)
        self.declare_parameter(
            "lookahead", [float(v) for v in DEFAULT_LOOKAHEAD])

        self.model_path = self.get_parameter("model_path").value
        odom_topic = self.get_parameter("odom_topic").value
        imu_topic = self.get_parameter("imu_topic").value
        path_topic = self.get_parameter("path_topic").value
        profile_topic = self.get_parameter("profile_topic").value
        left_topic = self.get_parameter("left_thrust_topic").value
        right_topic = self.get_parameter("right_thrust_topic").value
        status_topic = self.get_parameter("status_topic").value
        self.rate_hz = float(self.get_parameter("control_rate_hz").value)
        self.t_max = float(self.get_parameter("t_max").value)
        self.d_t_max = float(self.get_parameter("d_t_max").value)
        self.cruise_speed = float(self.get_parameter("cruise_speed").value)
        self.schedule_rebase_m = float(self.get_parameter("schedule_rebase_m").value)
        self.lookahead = tuple(
            float(v) for v in self.get_parameter("lookahead").value)
        self.dt = 1.0 / self.rate_hz

        # ── 推理会话 ──
        self.session = None
        self.model_contract_invalid = False
        if self.model_path and Path(self.model_path).exists():
            try:
                contract = load_policy_contract(self.model_path, self.t_max)
                import onnxruntime as ort
                candidate = ort.InferenceSession(
                    self.model_path, providers=["CPUExecutionProvider"])
                validate_policy_session(candidate, contract)
                self.session = candidate
                self.get_logger().info(f"加载物理N策略: {self.model_path}")
            except Exception as exc:
                self.model_contract_invalid = True
                self.get_logger().error(
                    f"策略合同无效: {exc} — 节点将保持 STANDBY 零推力")
        else:
            self.get_logger().error(
                f"模型不存在: '{self.model_path}' — 节点将保持 STANDBY 零推力")

        # ── 状态 ──
        self.state = np.zeros(6)             # [x,y,psi,u,v,r]
        self.have_odom = False
        self.r_from_imu: float | None = None
        self.ref_xs = self.ref_ys = None     # 路径数组
        self.ref_psis = None
        self.ref_s = None
        self.prof_v = self.prof_kappa = self.prof_r = self.prof_t = None
        self.profile_synced = False
        self.path_stamp = None
        self.path_received = False
        self.prog_idx = 0
        self._path_fp = None                 # 路径几何指纹（防每秒重发重置任务时钟）
        self._mission_t0 = None              # 任务时钟起点：新路径首次出现的时刻
        self._t_lag = 0.0                    # 调度滞后（与训练环境 rebase 语义一致）
        self.prev_thrust = np.zeros(2)
        self.standby_reason = "init"

        self.thrust_pub_l = self.create_publisher(Float64, left_topic, 10)
        self.thrust_pub_r = self.create_publisher(Float64, right_topic, 10)
        self.status_pub = self.create_publisher(String, status_topic, 10)

        self.create_subscription(Odometry, odom_topic, self._odom_cb, qos_profile_sensor_data)
        self.create_subscription(Imu, imu_topic, self._imu_cb, qos_profile_sensor_data)
        self.create_subscription(PathMsg, path_topic, self._path_cb, 10)
        self.create_subscription(Float64MultiArray, profile_topic, self._profile_cb, 10)

        self.create_timer(self.dt, self._control_loop)
        self.get_logger().info(
            f"rl_policy_node 就绪 rate={self.rate_hz}Hz t_max={self.t_max} dT_max={self.d_t_max}")

    # ────────────────────────── 回调 ──────────────────────────
    def _odom_cb(self, msg: Odometry) -> None:
        p, t = msg.pose.pose.position, msg.pose.pose.orientation
        lin = msg.twist.twist.linear
        ang = msg.twist.twist.angular
        # NaN/Inf 与四元数退化门禁 (对齐 MPC 节点): 单个污染样本 (EKF 发散/
        # GPS 重定位) 进观测 → NaN 推力直发执行器 (clip 拦不住 NaN)。
        qn = t.x * t.x + t.y * t.y + t.z * t.z + t.w * t.w
        if not (math.isfinite(qn) and qn >= 1e-12 and
                all(math.isfinite(v) for v in (p.x, p.y, lin.x, lin.y, ang.z))):
            self.get_logger().warning(
                "odom 含 NaN/Inf 或四元数退化, 丢弃该样本",
                throttle_duration_sec=5.0)
            return
        self.state = np.array([
            p.x, p.y, yaw_from_quaternion(t), lin.x, lin.y, ang.z,
        ])
        self.have_odom = True

    def _imu_cb(self, msg: Imu) -> None:
        r = msg.angular_velocity.z
        if math.isfinite(r):
            self.r_from_imu = r

    @staticmethod
    def _path_fingerprint(xs, ys) -> tuple:
        """路径几何指纹：规划器每秒重发同一路径（戳会变），据此区分真·新路径。"""
        return (
            len(xs),
            round(float(xs[0]), 3), round(float(ys[0]), 3),
            round(float(xs[-1]), 3), round(float(ys[-1]), 3),
        )

    def _path_cb(self, msg: PathMsg) -> None:
        n = len(msg.poses)
        if n < 2:
            return
        xs = np.array([p.pose.position.x for p in msg.poses])
        ys = np.array([p.pose.position.y for p in msg.poses])
        yaws = np.array([yaw_from_quaternion(p.pose.orientation) for p in msg.poses])
        # 规划器发布连续累积航向；防御性 unwrap 保证曲率差分有效
        psis = np.unwrap(yaws)
        seg = np.hypot(np.diff(xs), np.diff(ys))
        s = np.concatenate([[0.0], np.cumsum(seg)])
        self.ref_xs, self.ref_ys, self.ref_psis, self.ref_s = xs, ys, psis, s
        self.path_received = True

        fp = self._path_fingerprint(xs, ys)
        now_sec = self.get_clock().now().nanoseconds * 1e-9
        if fp != self._path_fp:
            # 真·新路径：任务时钟归零、进度归零
            self._path_fp = fp
            self._mission_t0 = now_sec
            self.prog_idx = 0
        self.path_stamp = msg.header.stamp
        self.profile_synced = (
            self.prof_v is not None and len(self.prof_v) == len(xs)
        )
        if not self.profile_synced:
            self._derive_fallback_profile()

    def _profile_cb(self, msg: Float64MultiArray) -> None:
        data = np.asarray(msg.data, dtype=np.float64)
        if data.size % 4 != 0:
            return
        rows = data.reshape(-1, 4)
        self.prof_v, self.prof_kappa, self.prof_r, self.prof_t = (
            rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3])
        if self.ref_xs is not None:
            self.profile_synced = len(self.prof_v) == len(self.ref_xs)

    def _derive_fallback_profile(self) -> None:
        """无同步剖面时按弧长匀速 + 航向差分曲率兜底（MPC cruise_speed 回退同语义）。"""
        n = len(self.ref_xs)
        ds = np.diff(self.ref_s, prepend=self.ref_s[0])
        dpsi = np.diff(self.ref_psis, prepend=self.ref_psis[0])
        with np.errstate(divide="ignore", invalid="ignore"):
            kappa = np.where(ds > 1e-6, dpsi / np.maximum(ds, 1e-9), 0.0)
        v = np.full(n, self.cruise_speed)
        self.prof_kappa = kappa
        self.prof_v = v
        self.prof_r = kappa * v
        self.prof_t = np.concatenate([[0.0], np.cumsum(ds[1:] / v[1:])])
        self.profile_synced = False

    # ────────────────────────── 控制循环 ──────────────────────────
    def _control_loop(self) -> None:
        if not self.have_odom or self.ref_xs is None or self.session is None:
            reason = ("model_contract_invalid" if self.model_contract_invalid else
                      "no_odom" if not self.have_odom else
                      "no_path" if self.ref_xs is None else "model_missing")
            self._publish_thrust(np.zeros(2))
            self._publish_status(active=False, reason=reason, raw=np.zeros(2),
                                 applied=np.zeros(2), infer_ms=0.0)
            return

        # 2026-10-09 审查修复: 推理/观测异常曾直接打崩节点 (rclpy.spin 逃逸),
        # VRX 下无 mode_manager 兜底 → 推力锁存 = 失控船。任何异常都降级为
        # 零推力 STANDBY 并保持定时器存活。
        try:
            self._control_step()
        except Exception as exc:  # noqa: BLE001 — 定时器回调必须永不逃逸
            self.get_logger().error(
                f"控制循环异常, 本拍零推力: {exc}", throttle_duration_sec=5.0)
            self._publish_thrust(np.zeros(2))
            self._publish_status(active=False, reason="control_loop_error",
                                 raw=np.zeros(2), applied=np.zeros(2), infer_ms=0.0)

    def _control_step(self) -> None:
        # 观测有限性门禁: NaN/Inf 状态 (上游残留路径) 不进推理。
        if not np.isfinite(self.state).all():
            self.get_logger().warning(
                "状态含 NaN/Inf, 本拍零推力", throttle_duration_sec=5.0)
            self._publish_thrust(np.zeros(2))
            self._publish_status(active=False, reason="nonfinite_state",
                                 raw=np.zeros(2), applied=np.zeros(2), infer_ms=0.0)
            return

        # IMU r 覆盖（比 odom 灵敏，与 mpc_node 同）
        if self.r_from_imu is not None and abs(self.r_from_imu) < 10.0:
            self.state[5] = self.r_from_imu

        now = self.get_clock().now()
        if self._mission_t0 is not None:
            # 任务时钟：从新路径首次出现起累计（不受规划器每秒重发影响）
            mission_time = max(now.nanoseconds * 1e-9 - self._mission_t0, 0.0)
        else:
            mission_time = 0.0

        # 调度 rebase（与训练环境 _rebase_schedule 语义一致）：沿迹偏差超阈
        # 时平移时间参考。缺了这步，任务时钟一旦超过剖面总时长，参考就钳在
        # 路径终点 v_ref≈0，策略会以阻力平衡速度滑行（VRX 实测 0.3 m/s 的根因）
        i_t = int(np.clip(
            np.searchsorted(self.prof_t, max(mission_time - self._t_lag, 0.0),
                            side="right") - 1,
            0, len(self.prof_t) - 1))
        hd = self.ref_psis[i_t]
        e_along = ((self.state[0] - self.ref_xs[i_t]) * math.cos(hd)
                   + (self.state[1] - self.ref_ys[i_t]) * math.sin(hd))
        vr = max(float(self.prof_v[i_t]), 0.1)
        if e_along < -self.schedule_rebase_m:
            self._t_lag += (-e_along - self.schedule_rebase_m) / vr
        elif e_along > self.schedule_rebase_m:
            self._t_lag = max(
                self._t_lag - (e_along - self.schedule_rebase_m) / vr, 0.0)
        path_time = max(mission_time - self._t_lag, 0.0)

        self.prog_idx = advance_progress(
            self.ref_xs, self.ref_ys, self.state[0], self.state[1], self.prog_idx)

        obs = compose_observation(
            self.state, self.ref_xs, self.ref_ys, self.ref_psis,
            self.prof_kappa, self.prof_v, self.prof_r, self.ref_s,
            self.prof_t, t_now=max(path_time, 0.0),
            prog_idx=self.prog_idx, prev_thrust=self.prev_thrust,
            lookahead=self.lookahead,
        )
        if not np.isfinite(obs).all():
            self.get_logger().warning(
                "观测向量含 NaN/Inf, 本拍零推力", throttle_duration_sec=5.0)
            self._publish_thrust(np.zeros(2))
            self._publish_status(active=False, reason="nonfinite_obs",
                                 raw=np.zeros(2), applied=np.zeros(2), infer_ms=0.0)
            return

        t0 = time.monotonic()
        raw = self.session.run(["thrust"], {"obs": obs[None].astype(np.float32)})[0][0]
        infer_ms = (time.monotonic() - t0) * 1e3
        # 推理输出有限性门禁: NaN 经 apply_thrust_limits 的 clip 仍是 NaN。
        if not np.isfinite(raw).all():
            self.get_logger().error(
                "策略输出含 NaN/Inf, 本拍零推力", throttle_duration_sec=5.0)
            self._publish_thrust(np.zeros(2))
            self._publish_status(active=False, reason="nonfinite_action",
                                 raw=np.zeros(2), applied=np.zeros(2),
                                 infer_ms=infer_ms)
            return

        applied, _target = apply_thrust_limits(
            self.prev_thrust, raw, self.t_max, self.d_t_max, self.dt)
        self._publish_thrust(applied)
        self.prev_thrust = applied
        self.standby_reason = ""
        self._publish_status(active=True, reason="", raw=raw,
                             applied=applied, infer_ms=infer_ms)

    # ────────────────────────── 发布 ──────────────────────────
    def _publish_thrust(self, applied: np.ndarray) -> None:
        ml, mr = Float64(), Float64()
        ml.data, mr.data = float(applied[0]), float(applied[1])
        self.thrust_pub_l.publish(ml)
        self.thrust_pub_r.publish(mr)

    def _publish_status(self, active: bool, reason: str, raw: np.ndarray,
                        applied: np.ndarray, infer_ms: float) -> None:
        x, y, psi, u, v, r = self.state

        def _fin(value: float) -> float:
            """NaN/Inf 清洗: 非有限值以 0.0 呈现, 防 JSON 里出现 NaN 字面量
            (严格解析器会崩, mode_manager 的容错路径也会每拍告警)。"""
            return float(value) if math.isfinite(value) else 0.0

        j = {
            "state": "ACTIVE" if active else "STANDBY",
            "success": active,
            "fail_count": 0,
            "solve_time_ms": round(infer_ms, 3),
            "max_solve_time_ms": round(self.dt * 1e3, 1),
            "deadline_miss": infer_ms > self.dt * 1e3,
            "hold": False,
            "control_mode": "rl",
            "backend": "onnx_ppo",
            "require_fcu_state": False,
            "path_received": self.path_received,
            "path_len": 0 if self.ref_xs is None else int(len(self.ref_xs)),
            "profile_synced": bool(self.profile_synced),
            "profile_sync_reason": "synced" if self.profile_synced else "fallback_cruise",
            "t_lag": round(_fin(self._t_lag), 2),
            "x": _fin(x), "y": _fin(y), "psi": _fin(psi),
            "u": _fin(u), "v": _fin(v), "r": _fin(r),
            "dynamic_dt": self.dt,
            "dynamic_N": 1,
            "prediction_time_s": self.dt,
            "tl_n": _fin(applied[0]),
            "tr_n": _fin(applied[1]),
            "tl_cmd_n": _fin(raw[0]),
            "tr_cmd_n": _fin(raw[1]),
            "actuation_anchor_source": "vrx_published",
        }
        if not active:
            j["standby_reason"] = reason
        msg = String()
        msg.data = json.dumps(j)
        self.status_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RlPolicyNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
