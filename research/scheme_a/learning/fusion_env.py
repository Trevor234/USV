#!/usr/bin/env python3
"""融合闭环 Gymnasium 环境（P5.4）——PPO 在真实融合环里训练。

参考生成、观测、跟踪奖励和成功判据复用 `UsvTrackingEnv`。
可选的 r_qpi_u0 惩罚衡量策略提议与实际执行推力的差异。每步执行链路：

    action ∈ [-1,1]² → q_pi = 25·a
    → FusionController.step(state, path, profile, anchor=上一拍执行推力, q_pi, λπ)
      → [build_frozen_reference + GP rollout + GP residual]  → C ABI 求解器
    → 求解器给出的 u0 经速率限制/幅值限制后**实际执行**
    → 用执行推力推进动力学，再按父类口径算奖励/终止

`prev_thrust` 存的是**执行**推力（与部署侧的 confirmed executed thrust 同义），
因此 `obs_prev_thrust_timing="post_update"` 的语义成立。

求解器不可用时不静默降级：构造即失败（没有可信求解器就不该产生训练数据）。
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from usv_rl.dynamics import HydroParams

# usv_rl 不依赖 scheme A 目录；这里按需延迟导入，便于仅训练方案C时无该目录
_FUSION_IMPORTS: dict[str, Any] = {}


def _fusion_modules():
    if not _FUSION_IMPORTS:
        from fusion_controller import FusionController, load_pooled_gp
        from fusion_solver import FusionSolver

        _FUSION_IMPORTS.update(
            FusionController=FusionController,
            FusionSolver=FusionSolver,
            load_pooled_gp=load_pooled_gp,
        )
    return _FUSION_IMPORTS


class FusionTrackingEnv(gym.Env):
    """以生产融合求解器为执行器、以 `UsvTrackingEnv` 为语义基线的训练环境。"""

    metadata = {"render_modes": []}

    def __init__(
        self,
        *,
        contract_path: Path,
        gp_snapshot: Path,
        lambda_pi: float = 0.005,
        solver_lib: str | None = None,
        thrust_scale_n: float = 25.0,
        r_qpi_u0: float = 0.0,
        **env_kwargs: Any,
    ) -> None:
        super().__init__()
        self.r_qpi_u0 = float(r_qpi_u0)
        if not np.isfinite(self.r_qpi_u0) or self.r_qpi_u0 < 0.0:
            raise ValueError("r_qpi_u0 must be finite and nonnegative")
        from usv_rl.envs.usv_tracking_env import UsvTrackingEnv

        # 组合而非继承：父类的 step() 是"策略直接给推力"，语义不同，覆写整段更清晰；
        # reset/_get_obs/_ct_geometry/_info/_check_done/_sample_reference 直接复用。
        self._base = UsvTrackingEnv(**env_kwargs)
        self.dt = self._base.dt
        self.t_max_thrust = float(thrust_scale_n)
        self.d_t_max = self._base.d_t_max
        self.lambda_pi = float(lambda_pi)
        self.gp_snapshot = Path(gp_snapshot)
        self.contract_path = Path(contract_path)
        self.observation_space = self._base.observation_space
        self.action_space = spaces.Box(-1.0, 1.0, (2,), np.float32)

        contract_doc = json.loads(self.contract_path.read_text(encoding="utf-8"))
        projection_mode = contract_doc.get("reference_projection_mode", "discrete_offset")
        if projection_mode not in ("discrete_offset", "polyline_time"):
            raise ValueError(f"invalid contract reference_projection_mode: {projection_mode!r}")
        lead_s = None
        if "reference_lead_s" in contract_doc:
            lead = contract_doc["reference_lead_s"]
            if type(lead) not in (int, float) or not 0.0 <= lead <= 2.0:
                raise ValueError("contract reference_lead_s must be a finite number in [0, 2]")
            lead_s = float(lead)
        hydro_doc = contract_doc["hydro"]
        self.base_hydro = HydroParams(
            **{k: float(v) for k, v in hydro_doc.items() if k in _hydro_keys()}
        )
        self._base.base_hydro = self.base_hydro
        self._base.model.params = self.base_hydro
        self._base.cost_params = replace(
            self._base.cost_params, ff_xu=self.base_hydro.Xu, ff_xuu=self.base_hydro.Xuu,
        )
        mods = _fusion_modules()
        self.solver = mods["FusionSolver"].from_contract(self.contract_path, lib_path=solver_lib)
        self.gp = mods["load_pooled_gp"](self.gp_snapshot)
        self.controller = mods["FusionController"](
            self.solver,
            gp=self.gp,
            hydro=self.base_hydro,
            t_min=-self.t_max_thrust,
            t_max=self.t_max_thrust,
            dt_max=self.d_t_max,
            cruise=float(contract_doc.get("cruise_speed", 0.6)),
            reference_offset=int(contract_doc.get("reference_start_offset", 2)),
            projection_mode=projection_mode,
            lead_s=lead_s,
        )
        self._prev_x: np.ndarray | None = None
        self._prev_u: np.ndarray | None = None
        self._prev_cmd_tick: int | None = None
        self._last_solver_ms = 0.0
        self._last_q_pi = np.zeros(2)
        self._last_u0 = np.zeros(2)
        self._last_ood = 0

    # 代理父类属性/方法，保证外部（callbacks、测试）按 UsvTrackingEnv 用
    def __getattr__(self, name: str) -> Any:
        base = self.__dict__.get("_base")
        if base is None:
            raise AttributeError(name)
        return getattr(base, name)

    # ------------------------------------------------------------------
    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        obs, info = self._base.reset(seed=seed, options=options)
        self.controller.reset_warmstart()
        # 融合闭环的 anchor 从零开始（与受控仿真首拍一致）
        self._base.prev_thrust = np.zeros(2)
        self._prev_x = None
        self._prev_u = None
        self._prev_cmd_tick = None
        obs = self._base._get_obs()
        info = self._base._info(0.0)
        info["ds_prog"] = 0.0
        return obs, info

    # ------------------------------------------------------------------
    def step(self, action: np.ndarray):
        base = self._base
        a = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
        q_pi = a * self.t_max_thrust
        ref = base.reference
        path = np.column_stack([ref.xs, ref.ys, ref.psis])
        profile = np.column_stack([ref.v_ref, np.zeros_like(ref.v_ref), ref.r_ref, ref.t])

        tick = int(base.step_count)
        tick_shift = 0 if self._prev_cmd_tick is None else tick - self._prev_cmd_tick
        u0, diag = self.controller.step(
            base.state, path, profile, base.prev_thrust, q_pi, self.lambda_pi,
            prev_x=self._prev_x, prev_u=self._prev_u, tick_shift=tick_shift,
        )
        # 执行层：幅值 + 变化率限制（与部署/受控仿真一致）
        max_delta = self.d_t_max * self.dt
        applied = np.clip(
            base.prev_thrust + np.clip(u0 - base.prev_thrust, -max_delta, max_delta),
            -self.t_max_thrust, self.t_max_thrust,
        )

        base.state = base.model.forward(base.state, applied)
        base.step_count += 1
        prev_s = base.traveled_s
        base._update_progress()
        ds_prog = base.traveled_s - prev_s

        reward = base._reward(applied, ds_prog)
        base._episode_max_ct = max(base._episode_max_ct, abs(base._last_e_ct))
        terminated, truncated, reason = base._check_done()
        if terminated:
            reward += base.success_bonus if reason == "success" else -base.failure_penalty
        qpi_pen = 0.0
        if self.r_qpi_u0 > 0.0:
            qpi_pen = base.cost_params.reward_scale * self.r_qpi_u0 * float(np.sum(np.square(q_pi - applied)))
            reward -= qpi_pen
        base.prev_thrust = applied

        self._prev_x = np.asarray(diag["rollout_x"], dtype=np.float64).copy()
        self._prev_u = np.asarray(diag["rollout_u"], dtype=np.float64).copy()
        self._prev_cmd_tick = tick
        self._last_solver_ms = float(diag.get("solver_ms", 0.0))
        self._last_q_pi = np.asarray(q_pi, dtype=np.float64).copy()
        self._last_u0 = np.asarray(u0, dtype=np.float64).copy()
        self._last_ood = int(diag.get("gp_ood_stage_count", 0) or 0)

        # 求解成功后提交热启动链（失败时 controller.step 已抛，不会走到这里）
        try:
            self.controller.commit(applied)
        except Exception:
            self.controller.reset_warmstart()
            self._prev_x = None
            self._prev_u = None

        info = base._info(ds_prog, reason=reason)
        info["applied_thrust"] = applied.copy()
        info["q_pi"] = self._last_q_pi
        info["q_pi_penalty"] = qpi_pen
        info["u0"] = self._last_u0
        info["solver_ms"] = self._last_solver_ms
        info["gp_ood_stage_count"] = self._last_ood
        return base._get_obs(), reward, terminated, truncated, info

    # ------------------------------------------------------------------
    def close(self) -> None:
        try:
            self.solver.close()
        finally:
            self._base.close()


def _hydro_keys() -> tuple[str, ...]:
    return ("mass", "Iz", "xg", "d_thruster", "Xu_dot", "Yv_dot", "Yr_dot", "Nv_dot",
            "Nr_dot", "Xu", "Yv", "Yr", "Nv", "Nr", "Xuu", "Yvv", "Yrr", "Nvv", "Nrr")


def make_fusion_env(env_cfg: dict, seed: int, *, contract_path: Path, gp_snapshot: Path,
                    lambda_pi: float = 0.005, solver_lib: str | None = None,
                    r_qpi_u0: float = 0.0):
    """工厂：供 `usv_rl.train` 在 FUSION_ENV=1 时替换 `gym.make`。"""
    from stable_baselines3.common.monitor import Monitor

    def _init():
        env = FusionTrackingEnv(
            contract_path=contract_path, gp_snapshot=gp_snapshot,
            lambda_pi=lambda_pi, solver_lib=solver_lib, r_qpi_u0=r_qpi_u0, **env_cfg,
        )
        env.reset(seed=seed)
        return Monitor(env)

    return _init
