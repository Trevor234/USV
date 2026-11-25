"""UsvTrackingEnv — USV 轨迹跟踪 Gymnasium 环境（方案C 训练用）。

对齐点（与 usv_mpc_cpp MPC 公平对比的前提）：
- 决策周期 dt=0.2s（5Hz），与 MPC N=20/dt=0.2 相同
- 动作 = 双桨推力 [T_L, T_R]（N），±25N clamp + 80 N/s 速率限制（与 MPC 一致）
- 奖励 = 负 MPC 代价（`usv_rl.envs.reward`，Q/R/Rd 与 mpc_params.yaml 同量纲）
         + 弧长进度项；位置项用**路径几何横向误差** e_ct（平方-线性过渡）
- 参考轨迹：方案 A 闭环运行器的机动生成器（`scheme_a_mix` 等），保证训练与
  受控仿真运行同一分布；非机动类型仍走曲率段采样

观测（43 维 float32）：见 `usv_rl.observation`（唯一真源）。
  [u, v, r, sin(psi), cos(psi),
   sin(e_psi_p), cos(e_psi_p), v_ref_p, r_ref_p,   # 进度索引参考（非时间索引）
   K × (dx_b, dy_b, kappa_k, v_ref_k),             # K 个前瞻弧长点的机体系相对量
   T_L_prev, T_R_prev]
不含绝对 x, y（平移不变；世界朝向通过随机旋转路径打破）。

成功判据（三条同时满足）：到达路径末端邻域、终点距离 <= finish_radius_m、
全程 |e_ct| 最大值 <= success_cte_limit_m。只判"到终点"会奖励沿直线蒙到目标、
全程偏离航线 5 m+ 的"直线策略"（见 tests/test_env_api.py 的反例测试）。
"""
from __future__ import annotations

import math
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from usv_rl.dynamics import HydroParams, USVDynamicModel, wrap_angle
from usv_rl.envs.geometry import project_to_polyline
from usv_rl.envs.reward import TrackingCostParams, tracking_cost
from usv_rl.observation import LOOKAHEAD_M, advance_progress, compose_observation
from usv_rl.reference import (
    MANEUVER_TYPES,
    make_maneuver_reference,
    make_reference,
    sample_kappa_segments,
)

# 训练默认前瞻 = 观测契约（与部署节点同值）
DEFAULT_LOOKAHEAD = LOOKAHEAD_M

# 奖励里路径投影的段窗口：向后 2 段（滞后容差）+ 向前 8 段（4 m 前瞻）
_CT_BACK_SEG = 2
_CT_FWD_SEG = 8


class UsvTrackingEnv(gym.Env):
    """单桨 USV 轨迹跟踪。动作连续推力，参考轨迹逐 episode 随机生成。"""

    metadata = {"render_modes": []}

    def __init__(
        self,
        dt: float = 0.2,
        rk4_substeps: int = 4,
        max_steps: int = 450,
        t_max_thrust: float = 25.0,
        d_t_max: float = 80.0,
        lookahead: tuple[float, ...] = DEFAULT_LOOKAHEAD,
        path_resolution: float = 0.5,
        # 奖励权重（MPC mpc_params.yaml 对标；见 envs/reward.py）
        q_ct: float = 100.0,
        q_psi: float = 50.0,
        q_u: float = 8.0,
        q_v: float = 1.0,
        q_r: float = 8.0,
        r_thrust: float = 0.05,
        r_dthrust: float = 0.2,
        reward_scale: float = 0.2,
        w_progress: float = 15.0,
        ct_linear_m: float = 1.0,
        success_bonus: float = 10.0,
        failure_penalty: float = 10.0,
        # 终止条件
        pos_err_limit: float = 3.0,
        psi_err_limit: float = math.pi / 2,
        # 进度门限：窗口内最近路径点远于该值时进度不变
        progress_gate_m: float = 1.0,
        # 成功判据
        finish_radius_m: float = 1.0,
        success_cte_limit_m: float = 0.75,
        # 训练期关闭提前终止：违规只持续计罚不判死——
        # 只要"早死"比"带伤活着"省，PPO 就会先学死（v3 教训：ep_len 303→27.7）
        early_termination: bool = True,
        # 课程：路径类型（maneuver 名 / "scheme_a_mix" / 曲率段类型）
        path_type: str = "random",
        # 方案 A 机动参考的时长与巡航速度采样区间
        maneuver_seconds: float = 30.0,
        maneuver_cruise_speed: tuple[float, float] = (0.55, 0.85),
        # Domain randomization（训练末段开启）
        hydro_dr_frac: float = 0.0,          # 0 = 关闭
        thrust_delay_max_steps: int = 0,     # 0 = 关闭
        obs_noise_vel: float = 0.0,          # u/v/r 观测噪声 sigma
        obs_noise_pos: float = 0.0,          # 位置观测噪声 sigma（影响相对量）
        # 初始扰动
        init_pos_noise: float = 0.3,
        init_psi_noise: float = 0.3,
        init_vel_noise: float = 0.05,
        hydro_params: HydroParams | None = None,
        obs_prev_thrust_timing: str = "post_update",
        *,
        use_mode_energy: bool = False,
        r_cm: float = 0.05,
        r_dm: float = 0.05,
        drag_ff_gain: float = 0.0,
    ) -> None:
        super().__init__()
        if obs_prev_thrust_timing not in ("pre_update", "post_update"):
            raise ValueError(
                f"obs_prev_thrust_timing must be 'pre_update' or 'post_update', got {obs_prev_thrust_timing!r}"
            )
        if not math.isfinite(r_cm) or r_cm < 0.0:
            raise ValueError("r_cm must be finite and non-negative")
        if not math.isfinite(r_dm) or r_dm < 0.0:
            raise ValueError("r_dm must be finite and non-negative")
        if not 0.0 <= drag_ff_gain <= 2.0:
            raise ValueError("drag_ff_gain must be finite and in [0, 2]")
        self.obs_prev_thrust_timing = obs_prev_thrust_timing
        self.dt = dt
        self.max_steps = max_steps
        self.t_max_thrust = t_max_thrust
        self.d_t_max = d_t_max
        self.lookahead = tuple(lookahead)
        self.path_resolution = path_resolution
        self.base_hydro = hydro_params if hydro_params is not None else HydroParams()
        self.cost_params = TrackingCostParams(
            q_ct=q_ct, q_psi=q_psi, q_u=q_u, q_v=q_v, q_r=q_r,
            r_thrust=r_thrust, r_dthrust=r_dthrust, reward_scale=reward_scale,
            w_progress=w_progress, ct_linear_m=ct_linear_m,
            use_mode_energy=use_mode_energy, r_cm=r_cm, r_dm=r_dm, drag_ff_gain=drag_ff_gain,
            ff_xu=float(self.base_hydro.Xu), ff_xuu=float(self.base_hydro.Xuu),
        )
        self.success_bonus = success_bonus
        self.failure_penalty = failure_penalty
        self.pos_err_limit = pos_err_limit
        self.psi_err_limit = psi_err_limit
        self.progress_gate_m = progress_gate_m
        self.finish_radius_m = finish_radius_m
        self.success_cte_limit_m = success_cte_limit_m
        self.early_termination = early_termination
        self.path_type = path_type
        self.maneuver_seconds = maneuver_seconds
        self.maneuver_cruise_speed = (float(maneuver_cruise_speed[0]), float(maneuver_cruise_speed[1]))
        self.hydro_dr_frac = hydro_dr_frac
        self.thrust_delay_max_steps = thrust_delay_max_steps
        self.obs_noise_vel = obs_noise_vel
        self.obs_noise_pos = obs_noise_pos
        self.init_pos_noise = init_pos_noise
        self.init_psi_noise = init_psi_noise
        self.init_vel_noise = init_vel_noise

        self.model = USVDynamicModel(dt=dt, rk4_substeps=rk4_substeps)

        n_obs = 3 + 2 + 2 + 2 + 4 * len(self.lookahead) + 2
        self.observation_space = spaces.Box(-np.inf, np.inf, (n_obs,), np.float32)
        # 动作归一化到 [-1,1]：PPO 初始 std=1 即覆盖全推力量程（±25N 量纲下
        # std=1 只能探索 4% 满量程，策略永远摸不到巡航推力）
        self.action_space = spaces.Box(-1.0, 1.0, (2,), np.float32)

        self._rng = np.random.default_rng()
        self._reset_state()

    # ------------------------------------------------------------------
    def _reset_state(self) -> None:
        self.state = np.zeros(6)
        self.reference = None
        self.step_count = 0
        self.prog_idx = 0
        self.prev_thrust = np.zeros(2)
        self.thrust_queue: list[np.ndarray] = []
        self.traveled_s = 0.0
        self._episode_step_limit = self.max_steps
        self._episode_max_ct = 0.0
        self._last_e_ct = 0.0

    def _sample_reference(self) -> None:
        ptype = self.path_type
        if ptype == "scheme_a_mix":
            ptype = str(MANEUVER_TYPES[int(self._rng.integers(0, len(MANEUVER_TYPES)))])
        if ptype in MANEUVER_TYPES:
            seed = int(self._rng.integers(0, 2 ** 31 - 1))
            cruise = float(self._rng.uniform(*self.maneuver_cruise_speed))
            self.reference = make_maneuver_reference(
                ptype, seconds=self.maneuver_seconds, seed=seed, cruise_speed=cruise
            )
            # 随机世界朝向，打破绝对航向偏置（生成器固定从 (0,0,0) 起）
            psi0 = float(self._rng.uniform(-math.pi, math.pi))
            c, s = math.cos(psi0), math.sin(psi0)
            ref = self.reference
            xr = ref.xs * c - ref.ys * s
            yr = ref.xs * s + ref.ys * c
            ref.xs, ref.ys = xr, yr
            ref.psis = ref.psis + psi0
            return
        kappas, lengths = sample_kappa_segments(self._rng, ptype, n_segments=None)
        psi0 = float(self._rng.uniform(-math.pi, math.pi))
        self.reference = make_reference(
            kappas, lengths, ds=self.path_resolution, start=(0.0, 0.0, psi0)
        )

    # ------------------------------------------------------------------
    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        if options and "path_type" in options:
            self.path_type = options["path_type"]

        self._sample_reference()
        ref = self.reference

        # Domain randomization：水动力逐 episode 扰动
        if self.hydro_dr_frac > 0.0:
            self.model.params = self.base_hydro.perturbed(self._rng, self.hydro_dr_frac)
        else:
            self.model.params = self.base_hydro

        # 初始状态 = 路径起点 + 扰动
        x0 = ref.xs[0] + self._rng.uniform(-self.init_pos_noise, self.init_pos_noise)
        y0 = ref.ys[0] + self._rng.uniform(-self.init_pos_noise, self.init_pos_noise)
        psi0 = wrap_angle(ref.psis[0] + self._rng.uniform(-self.init_psi_noise, self.init_psi_noise))
        u0 = ref.v_ref[0] + self._rng.uniform(-self.init_vel_noise, self.init_vel_noise)
        self.state = np.array(
            [x0, y0, psi0, u0,
             self._rng.uniform(-self.init_vel_noise, self.init_vel_noise),
             self._rng.uniform(-self.init_vel_noise, self.init_vel_noise)]
        )

        self.step_count = 0
        self.prog_idx = 0
        self.traveled_s = 0.0
        self._episode_max_ct = 0.0
        self._last_e_ct = 0.0
        self.prev_thrust = np.zeros(2)
        # episode 步数上限随参考轨迹时长自适应（剖面时间 + 5 s 追赶余量），
        # 不超过配置的 max_steps 绝对上限
        self._episode_step_limit = min(
            self.max_steps,
            int(math.ceil(self.reference.total_time / self.dt)) + 25,
        )
        # 推力执行延迟：队列初值填零，长度逐 episode 采样
        n_delay = int(self._rng.integers(0, self.thrust_delay_max_steps + 1)) \
            if self.thrust_delay_max_steps > 0 else 0
        self.thrust_queue = [np.zeros(2) for _ in range(n_delay)]

        return self._get_obs(), self._info(0.0)

    # ------------------------------------------------------------------
    def step(self, action: np.ndarray):
        # [-1,1] → 物理推力 N，再施加速率限制
        action = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
        raw_thrust = action * self.t_max_thrust
        max_delta = self.d_t_max * self.dt
        target = np.clip(
            self.prev_thrust + np.clip(raw_thrust - self.prev_thrust, -max_delta, max_delta),
            -self.t_max_thrust, self.t_max_thrust,
        )
        applied = target
        if self.thrust_queue:
            self.thrust_queue.append(target)
            applied = self.thrust_queue.pop(0)

        self.state = self.model.forward(self.state, applied)
        self.step_count += 1

        prev_s = self.traveled_s
        self._update_progress()
        ds_prog = self.traveled_s - prev_s

        if self.obs_prev_thrust_timing == "pre_update":
            obs = self._get_obs()
        reward = self._reward(applied, ds_prog)
        self._episode_max_ct = max(self._episode_max_ct, abs(self._last_e_ct))
        terminated, truncated, reason = self._check_done()
        if terminated:
            reward += self.success_bonus if reason == "success" else -self.failure_penalty
        self.prev_thrust = applied
        if self.obs_prev_thrust_timing == "post_update":
            obs = self._get_obs()

        info = self._info(ds_prog, reason=reason)
        info["applied_thrust"] = applied.copy()
        return obs, reward, terminated, truncated, info

    # ------------------------------------------------------------------
    def _ct_geometry(self) -> tuple[float, float]:
        """当前状态的路径几何量：(带符号 e_ct, 投影段航向 psi_seg)。"""
        ref = self.reference
        n = len(ref.xs)
        lo = max(0, self.prog_idx - _CT_BACK_SEG)
        hi = min(n - 2, self.prog_idx + _CT_FWD_SEG)
        e_ct, psi_seg, _ = project_to_polyline(
            float(self.state[0]), float(self.state[1]), ref.xs, ref.ys, lo, hi
        )
        return e_ct, psi_seg

    def _update_progress(self) -> None:
        """最近点单调推进：窗口 PROGRESS_WINDOW + 距离门 progress_gate_m。"""
        ref = self.reference
        self.prog_idx = advance_progress(
            ref.xs, ref.ys, float(self.state[0]), float(self.state[1]),
            self.prog_idx, gate_m=self.progress_gate_m,
        )
        self.traveled_s = ref.s[self.prog_idx]

    def _get_obs(self) -> np.ndarray:
        ref = self.reference
        return compose_observation(
            self.state,
            ref.xs, ref.ys, ref.psis, ref.kappas, ref.v_ref, ref.r_ref, ref.s,
            prog_idx=self.prog_idx,
            prev_thrust=self.prev_thrust,
            lookahead=self.lookahead,
            obs_noise_vel=self.obs_noise_vel,
            obs_noise_pos=self.obs_noise_pos,
            rng=self._rng,
        )

    def _reward(self, applied: np.ndarray, ds_prog: float) -> float:
        ref = self.reference
        e_ct, psi_seg = self._ct_geometry()
        self._last_e_ct = e_ct
        i_p = self.prog_idx
        e_psi = wrap_angle(float(self.state[2]) - psi_seg)
        return tracking_cost(
            self.state, applied, self.prev_thrust,
            float(ref.v_ref[i_p]), float(ref.r_ref[i_p]),
            e_ct, e_psi, ds_prog, self.cost_params,
        )

    def _check_done(self) -> tuple[bool, bool, str]:
        """成功终止；超时截断；违规默认不判死（early_termination=False 时
        仅在超时那一刻用违规原因标记，供指标统计）。"""
        ref = self.reference
        i_p = self.prog_idx
        e_pos = math.hypot(self.state[0] - ref.xs[i_p], self.state[1] - ref.ys[i_p])
        e_psi = abs(wrap_angle(self.state[2] - ref.psis[i_p]))

        reason = ""
        if e_pos > self.pos_err_limit:
            reason = "pos_err"
        elif e_psi > self.psi_err_limit:
            reason = "psi_err"

        near_end = i_p >= len(ref.xs) - 2
        final_gap = math.hypot(self.state[0] - ref.xs[-1], self.state[1] - ref.ys[-1])
        if near_end and final_gap <= self.finish_radius_m \
                and self._episode_max_ct <= self.success_cte_limit_m:
            return True, False, "success"

        if self.step_count >= self._episode_step_limit:
            return False, True, reason or "timeout"
        if reason and self.early_termination:
            return True, False, reason
        return False, False, ""

    def _info(self, ds_prog: float, reason: str = "") -> dict[str, Any]:
        ref = self.reference
        if ref is None:
            return {}
        # 空间参考指标（最近路径点）：衡量路径跟随质量
        i_p = self.prog_idx
        e_pos = math.hypot(self.state[0] - ref.xs[i_p], self.state[1] - ref.ys[i_p])
        e_psi = wrap_angle(self.state[2] - ref.psis[i_p])
        e_ct, _ = self._ct_geometry()
        return {
            "e_pos": e_pos,
            "e_psi": e_psi,
            "e_ct": e_ct,
            "signed_surge_error": float(self.state[3] - ref.v_ref[i_p]),
            "max_e_ct": self._episode_max_ct,
            "progress_s": self.traveled_s,
            "total_s": ref.total_length,
            "ds_prog": ds_prog,
            "done_reason": reason,
            "is_success": reason == "success",
        }

    # ------------------------------------------------------------------
    def render(self) -> None:  # pragma: no cover
        pass

    def close(self) -> None:
        pass
