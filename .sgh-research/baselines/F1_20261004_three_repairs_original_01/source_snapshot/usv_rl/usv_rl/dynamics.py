"""USV Fossen 3-DOF 动力学模型 — 从 usv_mpc_cpp/src/usv_model_dynamic.cpp 逐行移植。

约定与 C++ 版完全一致：
- 状态 [x, y, psi, u, v, r]（psi 单位 rad，x/y 单位 m，u/v/r 单位 m/s、m/s、rad/s）
- 控制 [T_L, T_R] 左右推进器推力（N）
- tau = [TL+TR, 0, d*(TR-TL)]
- M 含附加质量，sway-yaw 通道非对角耦合（M 不对称，与 C++ 保持一致）
- RK4 离散化，rk4_substeps 子步，末端航向归一化到 (-pi, pi]
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, fields

import numpy as np
import yaml

# usv_params.yaml / usv_params_sim.yaml `vehicle:` 段中属于水动力参数的键
_VEHICLE_KEYS = (
    "mass", "Iz", "xg", "d_thruster",
    "Xu_dot", "Yv_dot", "Yr_dot", "Nv_dot", "Nr_dot",
    "Xu", "Yv", "Yr", "Nv", "Nr",
    "Xuu", "Yvv", "Yrr", "Nvv", "Nrr",
)


@dataclass
class HydroParams:
    """19 维水动力参数（默认值 = usv_params_sim.yaml 2026-09 快照）。"""

    mass: float = 14.2
    Iz: float = 2.13
    xg: float = 0.12
    d_thruster: float = 0.25

    Xu_dot: float = -2.0
    Yv_dot: float = -8.0
    Yr_dot: float = 0.0
    Nv_dot: float = -0.363545
    Nr_dot: float = -3.41

    Xu: float = -2.272063
    Yv: float = -2.629019
    Yr: float = 0.0
    Nv: float = 0.0
    Nr: float = -3.105

    Xuu: float = -11.571784
    Yvv: float = -0.05
    Yrr: float = 0.0
    Nvv: float = 0.0
    Nrr: float = -0.71

    @classmethod
    def from_usv_params_yaml(cls, path: str) -> "HydroParams":
        """从 usv_bringup/config/usv_params*.yaml 的 /**: ros__parameters: vehicle: 段加载。"""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        vehicle = data["/**"]["ros__parameters"]["vehicle"]
        kwargs = {k: float(v) for k, v in vehicle.items() if k in _VEHICLE_KEYS}
        missing = [k for k in _VEHICLE_KEYS if k not in kwargs]
        if missing:
            raise KeyError(f"{path} vehicle 段缺少参数: {missing}")
        return cls(**kwargs)

    def perturbed(self, rng: np.random.Generator, frac: float) -> "HydroParams":
        """Domain randomization：每个水动力参数独立乘 (1 + U(-frac, frac))。"""
        out = copy.deepcopy(self)
        for f in fields(HydroParams):
            scale = 1.0 + rng.uniform(-frac, frac)
            setattr(out, f.name, getattr(self, f.name) * scale)
        return out


def wrap_angle(psi: float) -> float:
    """归一化到 (-pi, pi]，与 C++ atan2(sin, cos) 一致。"""
    return math.atan2(math.sin(psi), math.cos(psi))


class USVDynamicModel:
    """单步推进器：forward(state, control) = RK4(dt/rk4_substeps) 积分一步。"""

    def __init__(
        self,
        dt: float = 0.2,
        rk4_substeps: int = 4,
        params: HydroParams | None = None,
    ) -> None:
        self.dt = dt
        self.rk4_substeps = rk4_substeps
        self.params = params if params is not None else HydroParams()

    # ------------------------------------------------------------------
    def continuous_ode(
        self, state: np.ndarray, control: np.ndarray, p: HydroParams
    ) -> np.ndarray:
        """连续动力学右端项，与 C++ USVDynamicModel::continuous_ode 一致。"""
        psi_s = state[2]
        u_s, v_s, r_s = state[3], state[4], state[5]
        TL, TR = control[0], control[1]

        # 惯性矩阵 M（含附加质量；m23/m32 不对称，照搬 C++）
        m11 = p.mass - p.Xu_dot
        m22 = p.mass - p.Yv_dot
        m23 = p.mass * p.xg - p.Yr_dot
        m32 = p.mass * p.xg - p.Nv_dot
        m33 = p.Iz - p.Nr_dot

        # 科里奥利 C(nu)
        c13 = -m22 * v_s - m23 * r_s
        c23 = m11 * u_s

        # 阻尼 D(nu)：线性 + 二次
        d00 = -p.Xu - p.Xuu * abs(u_s)
        d11 = -p.Yv - p.Yvv * abs(v_s)
        d12 = -p.Yr - p.Yrr * abs(r_s)
        d21 = -p.Nv - p.Nvv * abs(v_s)
        d22 = -p.Nr - p.Nrr * abs(r_s)

        # 推力映射 tau = [TL+TR, 0, d*(TR-TL)]
        tau_x = TL + TR
        tau_n = p.d_thruster * (TR - TL)

        cos_psi = math.cos(psi_s)
        sin_psi = math.sin(psi_s)

        # nu_dot = M^{-1} (tau - C nu - D nu)
        # C*nu = [c13*r, c23*r, -c13*u - c23*v]
        rhs_x = tau_x - c13 * r_s - d00 * u_s
        rhs_y = -c23 * r_s - (d11 * v_s + d12 * r_s)
        rhs_n = tau_n + c13 * u_s + c23 * v_s - (d21 * v_s + d22 * r_s)

        # M 的 2x2 sway-yaw 子块解析求逆（det = m22*m33 - m23*m32）
        det2 = m22 * m33 - m23 * m32
        nu_dot_u = rhs_x / m11
        nu_dot_v = (m33 * rhs_y - m23 * rhs_n) / det2
        nu_dot_r = (-m32 * rhs_y + m22 * rhs_n) / det2

        return np.array(
            [
                cos_psi * u_s - sin_psi * v_s,
                sin_psi * u_s + cos_psi * v_s,
                r_s,
                nu_dot_u,
                nu_dot_v,
                nu_dot_r,
            ],
            dtype=np.float64,
        )

    # ------------------------------------------------------------------
    def forward(self, state: np.ndarray, control: np.ndarray) -> np.ndarray:
        """RK4 积分一个 dt，末端航向归一化。与 C++ forward 一致。"""
        x = np.asarray(state, dtype=np.float64).copy()
        h = self.dt / self.rk4_substeps
        for _ in range(self.rk4_substeps):
            k1 = self.continuous_ode(x, control, self.params)
            k2 = self.continuous_ode(x + 0.5 * h * k1, control, self.params)
            k3 = self.continuous_ode(x + 0.5 * h * k2, control, self.params)
            k4 = self.continuous_ode(x + h * k3, control, self.params)
            x = x + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        x[2] = wrap_angle(x[2])
        return x
