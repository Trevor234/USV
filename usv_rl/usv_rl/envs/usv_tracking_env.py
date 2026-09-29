"""UsvTrackingEnv — USV 轨迹跟踪 Gymnasium 环境（方案C 训练用）。

对齐点（与 usv_mpc_cpp MPC 公平对比的前提）：
- 决策周期 dt=0.2s（5Hz），与 MPC N=20/dt=0.2 相同
- 动作 = 双桨推力 [T_L, T_R]（N），±25N clamp + 80 N/s 速率限制（与 MPC 一致）
- 奖励 = 负 MPC 代价（Q/R/Rd 取自 mpc_params.yaml）+ 弧长进度项 + 终端奖惩
- 时间参数化参考（曲率限速剖面），与规划器 TOPP 输出同形式

观测（43 维 float32）：
  [u, v, r,
   sin(psi), cos(psi),
   sin(e_psi_ref), cos(e_psi_ref), v_ref_t, r_ref_t,
   K × (dx_b, dy_b, kappa_k, v_ref_k),      # K 个前瞻弧长点的机体系相对量
   T_L_prev, T_R_prev]
不含绝对 x, y（平移不变；世界朝向通过随机旋转路径打破）。
"""
from __future__ import annotations

import math
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from usv_rl.dynamics import HydroParams, USVDynamicModel, wrap_angle
from usv_rl.reference import make_reference, sample_kappa_segments

DEFAULT_LOOKAHEAD = (0.4, 0.8, 1.2, 1.6, 2.0, 2.5, 3.0, 4.0)


class UsvTrackingEnv(gym.Env):
    """单桨 USV 轨迹跟踪。动作连续推力，参考轨迹逐 episode 随机生成。"""

    metadata = {"render_modes": []}

    def __init__(
        self,
        dt: float = 0.2,
        rk4_substeps: int = 4,
        max_steps: int = 300,
        t_max_thrust: float = 25.0,
        d_t_max: float = 80.0,
        lookahead: tuple[float, ...] = DEFAULT_LOOKAHEAD,
        path_resolution: float = 0.5,
        # 奖励权重（MPC mpc_params.yaml 对标）
        q_x: float = 20.0,
        q_y: float = 20.0,
        q_psi: float = 50.0,
        q_u: float = 8.0,
        q_v: float = 1.0,
        q_r: float = 8.0,
        r_thrust: float = 0.05,
        r_dthrust: float = 0.2,
        reward_scale: float = 0.2,
        w_progress: float = 0.5,
        success_bonus: float = 10.0,
        failure_penalty: float = 10.0,
        # 终止条件
        pos_err_limit: float = 3.0,
        psi_err_limit: float = math.pi / 2,
        # 时间参考代价 cap（超出后误差不再增长，避免策略早期奖励爆炸）
        schedule_pos_cap: float = 3.0,
        schedule_psi_cap: float = math.pi / 2,
        # 课程：路径类型
        path_type: str = "random",
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
    ) -> None:
        super().__init__()
        self.dt = dt
        self.max_steps = max_steps
        self.t_max_thrust = t_max_thrust
        self.d_t_max = d_t_max
        self.lookahead = tuple(lookahead)
        self.path_resolution = path_resolution
        self.q_x, self.q_y = q_x, q_y
        self.q_psi, self.q_u, self.q_v, self.q_r = q_psi, q_u, q_v, q_r
        self.r_thrust, self.r_dthrust = r_thrust, r_dthrust
        self.reward_scale = reward_scale
        self.w_progress = w_progress
        self.success_bonus = success_bonus
        self.failure_penalty = failure_penalty
        self.pos_err_limit = pos_err_limit
        self.psi_err_limit = psi_err_limit
        self.schedule_pos_cap = schedule_pos_cap
        self.schedule_psi_cap = schedule_psi_cap
        self.path_type = path_type
        self.hydro_dr_frac = hydro_dr_frac
        self.thrust_delay_max_steps = thrust_delay_max_steps
        self.obs_noise_vel = obs_noise_vel
        self.obs_noise_pos = obs_noise_pos
        self.init_pos_noise = init_pos_noise
        self.init_psi_noise = init_psi_noise
        self.init_vel_noise = init_vel_noise

        self.base_hydro = hydro_params if hydro_params is not None else HydroParams()
        self.model = USVDynamicModel(dt=dt, rk4_substeps=rk4_substeps)

        n_obs = 3 + 2 + 2 + 2 + 4 * len(self.lookahead) + 2
        self.observation_space = spaces.Box(-np.inf, np.inf, (n_obs,), np.float32)
        self.action_space = spaces.Box(-t_max_thrust, t_max_thrust, (2,), np.float32)

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

    def _sample_reference(self) -> None:
        kappas, lengths = sample_kappa_segments(
            self._rng, self.path_type, n_segments=None
        )
        # 随机世界朝向，打破绝对航向偏置
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
        action = np.clip(np.asarray(action, dtype=np.float64), -self.t_max_thrust, self.t_max_thrust)

        # 推力速率限制（与 MPC dT_max 一致）+ 可选执行延迟
        max_delta = self.d_t_max * self.dt
        target = np.clip(
            self.prev_thrust + np.clip(action - self.prev_thrust, -max_delta, max_delta),
            -self.t_max_thrust, self.t_max_thrust,
        )
        if self.thrust_queue:
            self.thrust_queue.append(target)
            applied = self.thrust_queue.pop(0)
        else:
            applied = target

        prev_state = self.state
        self.state = self.model.forward(self.state, applied)
        self.step_count += 1

        prev_s = self.traveled_s
        self._update_progress()
        ds_prog = self.traveled_s - prev_s

        obs = self._get_obs()
        reward = self._reward(applied, target, ds_prog)
        terminated, truncated, reason = self._check_done()
        self.prev_thrust = applied

        info = self._info(ds_prog, reason=reason)
        info["applied_thrust"] = applied.copy()
        return obs, reward, terminated, truncated, info

    # ------------------------------------------------------------------
    def _update_progress(self) -> None:
        """最近点单调推进搜索（窗口 40 点 = 20 m，终止条件限制抄近道）。"""
        ref = self.reference
        lo = self.prog_idx
        hi = min(lo + 40, len(ref.xs) - 1)
        idxs = np.arange(lo, hi + 1)
        d2 = (ref.xs[idxs] - self.state[0]) ** 2 + (ref.ys[idxs] - self.state[1]) ** 2
        self.prog_idx = int(idxs[np.argmin(d2)])
        self.traveled_s = ref.s[self.prog_idx]

    def _ref_point_at_time(self) -> int:
        return self.reference.at_time(self.step_count * self.dt)

    def _get_obs(self) -> np.ndarray:
        ref = self.reference
        x, y, psi, u, v, r = self.state

        # 观测噪声（仅观测通道，不污染内部状态）
        u_o = u + self._rng.normal(0, self.obs_noise_vel) if self.obs_noise_vel > 0 else u
        v_o = v + self._rng.normal(0, self.obs_noise_vel) if self.obs_noise_vel > 0 else v
        r_o = r + self._rng.normal(0, self.obs_noise_vel) if self.obs_noise_vel > 0 else r
        if self.obs_noise_pos > 0:
            x_o = x + self._rng.normal(0, self.obs_noise_pos)
            y_o = y + self._rng.normal(0, self.obs_noise_pos)
        else:
            x_o, y_o = x, y

        i_t = self._ref_point_at_time()
        e_psi = wrap_angle(psi - ref.psis[i_t])
        cos_p, sin_p = math.cos(psi), math.sin(psi)

        obs = [u_o, v_o, r_o, sin_p, cos_p, math.sin(e_psi), math.cos(e_psi),
               ref.v_ref[i_t], ref.r_ref[i_t]]

        # 前瞻点：当前投影弧长 + 固定偏移
        s0 = ref.s[self.prog_idx]
        for off in self.lookahead:
            i_k = ref.at_arc(s0 + off)
            dx_w = ref.xs[i_k] - x_o
            dy_w = ref.ys[i_k] - y_o
            dx_b = cos_p * dx_w + sin_p * dy_w
            dy_b = -sin_p * dx_w + cos_p * dy_w
            obs += [dx_b, dy_b, ref.kappas[i_k], ref.v_ref[i_k]]

        obs += [self.prev_thrust[0], self.prev_thrust[1]]
        return np.asarray(obs, dtype=np.float32)

    def _reward(
        self, applied: np.ndarray, target: np.ndarray, ds_prog: float
    ) -> float:
        ref = self.reference
        x, y, psi, u, v, r = self.state
        i_t = self._ref_point_at_time()
        dx, dy = x - ref.xs[i_t], y - ref.ys[i_t]
        e_pos_t = math.hypot(dx, dy)
        # 调度误差 cap：船远远落后/超前时误差封顶，保留有限惩罚与追赶梯度
        if e_pos_t > self.schedule_pos_cap:
            scale = self.schedule_pos_cap / e_pos_t
            dx, dy = dx * scale, dy * scale
        e_psi_t = wrap_angle(psi - ref.psis[i_t])
        e_psi_t = math.copysign(
            min(abs(e_psi_t), self.schedule_psi_cap), e_psi_t
        )
        d_thrust = applied - self.prev_thrust

        cost = (
            self.q_x * dx ** 2
            + self.q_y * dy ** 2
            + self.q_psi * e_psi_t ** 2
            + self.q_u * (u - ref.v_ref[i_t]) ** 2
            + self.q_v * v ** 2
            + self.q_r * (r - ref.r_ref[i_t]) ** 2
            + self.r_thrust * float(np.sum(applied ** 2))
            + self.r_dthrust * float(np.sum(d_thrust ** 2))
        )
        reward = -self.reward_scale * cost + self.w_progress * ds_prog
        return float(reward)

    def _check_done(self) -> tuple[bool, bool, str]:
        """终止用空间参考（最近路径点）：超前/滞后调度只影响奖励，不判死。"""
        ref = self.reference
        i_p = self.prog_idx
        e_pos = math.hypot(self.state[0] - ref.xs[i_p], self.state[1] - ref.ys[i_p])
        e_psi = abs(wrap_angle(self.state[2] - ref.psis[i_p]))

        if e_pos > self.pos_err_limit:
            return True, False, "pos_err"
        if e_psi > self.psi_err_limit:
            return True, False, "psi_err"
        if self.traveled_s >= ref.total_length - self.path_resolution * 1.5:
            return True, False, "success"
        if self.step_count >= self._episode_step_limit:
            return False, True, "timeout"
        return False, False, ""

    def _info(self, ds_prog: float, reason: str = "") -> dict[str, Any]:
        ref = self.reference
        if ref is None:
            return {}
        # 空间参考指标（最近路径点）：衡量路径跟随质量
        i_p = self.prog_idx
        e_pos = math.hypot(self.state[0] - ref.xs[i_p], self.state[1] - ref.ys[i_p])
        e_psi = wrap_angle(self.state[2] - ref.psis[i_p])
        # 带符号横向误差（参考航向的左法线方向为正）
        nx, ny = -math.sin(ref.psis[i_p]), math.cos(ref.psis[i_p])
        e_ct = (self.state[0] - ref.xs[i_p]) * nx + (self.state[1] - ref.ys[i_p]) * ny
        # 时间参考误差（调度偏差，诊断用）
        i_t = self._ref_point_at_time()
        e_pos_t = math.hypot(self.state[0] - ref.xs[i_t], self.state[1] - ref.ys[i_t])
        return {
            "e_pos": e_pos,
            "e_psi": e_psi,
            "e_ct": e_ct,
            "e_pos_t": e_pos_t,
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
