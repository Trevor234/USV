"""USV 三自由度运动学模型（方案 A）。

状态量: [x, y, psi] — ROS local map 坐标系下的位置和航向角
控制量: [u_surge, r_yaw] — 纵向速度和艏摇角速度

使用 CasADi 进行符号微分和 RK4 数值积分。
"""

import math
from typing import Optional

import casadi as ca
import numpy as np


class USVKinematicModel:
    """USV 运动学模型: dot_x = u*cos(psi), dot_y = u*sin(psi), dot_psi = r。"""

    def __init__(self, dt: float = 0.2, rk4_substeps: int = 4):
        self.dt = dt
        self.rk4_substeps = rk4_substeps
        self._setup_casadi()

    def _setup_casadi(self):
        """构建运动学模型的 CasADi 符号函数。"""
        x = ca.SX.sym("x")
        y = ca.SX.sym("y")
        psi = ca.SX.sym("psi")
        states = ca.vertcat(x, y, psi)

        u_surge = ca.SX.sym("u_surge")
        r_yaw = ca.SX.sym("r_yaw")
        controls = ca.vertcat(u_surge, r_yaw)

        rhs = ca.vertcat(
            u_surge * ca.cos(psi),
            u_surge * ca.sin(psi),
            r_yaw,
        )
        self._f_continuous = ca.Function("f", [states, controls], [rhs])

        # RK4 离散化动力学
        X0 = ca.SX.sym("X0", 3)
        U = ca.SX.sym("U", 2)
        X = X0
        h = self.dt / self.rk4_substeps
        for _ in range(self.rk4_substeps):
            k1 = self._f_continuous(X, U)
            k2 = self._f_continuous(X + h / 2 * k1, U)
            k3 = self._f_continuous(X + h / 2 * k2, U)
            k4 = self._f_continuous(X + h * k3, U)
            X = X + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        self._f_rk4 = ca.Function("f_rk4", [X0, U], [X])

    def forward(self, state: np.ndarray, control: np.ndarray) -> np.ndarray:
        """使用 RK4 将状态向前推进 dt 时间步。
        参数:
            state: [x, y, psi]
            control: [u_surge, r_yaw]
        返回:
            next_state: [x, y, psi]
        """
        result = self._f_rk4(state, control)
        """CasADi 算出来的 result 是它自己特有的数据类型
        （CasADi DM 矩阵）
        转回普通的Python 1 维一维数组 [x, y, psi]"""
        x_next = np.array(result).flatten()
        # 角度归一化，避免漂移
        x_next[2] = math.atan2(math.sin(x_next[2]), math.cos(x_next[2]))
        return x_next

    def casadi_function(self) -> ca.Function:
        """返回 CasADi 离散动力学函数。"""
        return self._f_rk4

    @property
    def n_states(self) -> int:
        return 3

    @property
    def n_controls(self) -> int:
        return 2
