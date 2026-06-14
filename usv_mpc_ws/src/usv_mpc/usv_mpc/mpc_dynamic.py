"""适用于无人船 (USV) 的动力学 NMPC 求解器（方案 B）。

求解带直接推力控制的 6 自由度最优控制问题：
  min  sum_k ||x_k - x_k^ref||_Q^2 + ||u_k||_R^2 + ||Delta u_k||_S^2  +  终端代价
  s.t. x_{k+1} = f_dyn(x_k, u_k),  x_0 = 当前状态
       T_min <= T_L, T_R <= T_max,  |Delta T| <= dT_max
"""

import time
from typing import Optional, Tuple

import casadi as ca
import numpy as np

from .usv_model_dynamic import USVDynamicModel


class DynamicMPC:
    """带直接推力控制的动力学 NMPC 控制器。"""

    def __init__(
        self,
        dt: float = 0.1,
        N: int = 15,
        Q_diag: Tuple[float, ...] = (10.0, 10.0, 50.0, 5.0, 1.0, 5.0),
        R_diag: Tuple[float, float] = (0.01, 0.01),
        Rd_diag: Tuple[float, float] = (0.1, 0.1),
        Qf_scale: float = 10.0,
        T_max: float = 40.0,
        T_min: float = -20.0,
        dT_max: float = 30.0,
        model_params: Optional[dict] = None,
        solver_opts: Optional[dict] = None,
    ):
        self.dt = dt
        self.N = N
        self.T_max = T_max
        self.T_min = T_min
        self.dT_max = dT_max

        model_kwargs = model_params or {}
        self.model = USVDynamicModel(dt=dt, **model_kwargs)
        self._f_rk4 = self.model.casadi_function()

        self.Q = np.diag(Q_diag)
        self.R = np.diag(R_diag)
        self.Rd = np.diag(Rd_diag)
        self.Qf = Qf_scale * self.Q

        self._build_solver(solver_opts)

        self._X_warm: Optional[np.ndarray] = None
        self._U_warm: Optional[np.ndarray] = None
        self._u_prev = np.zeros(2)

    def _build_solver(self, solver_opts: Optional[dict] = None):
        """构建 CasADi Opti NMPC 优化问题。"""
        opti = ca.Opti()

        self._X = opti.variable(6, self.N + 1)
        self._U = opti.variable(2, self.N)

        self._p_x0 = opti.parameter(6, 1)
        self._p_ref = opti.parameter(6, self.N + 1)
        self._p_u_prev = opti.parameter(2, 1)

        # 航向角代价使用 2*(1 - cos(Δψ)) 的原因见 mpc_kinematic.py。
        # 它是 atan2 包角后 Δψ² 的平滑替代形式。
        cost = 0
        Q_xy_uvr = np.diag(np.concatenate([np.diag(self.Q)[:2],
                                           np.diag(self.Q)[3:]]))
        Q_psi = self.Q[2, 2]
        Qf_xy_uvr = np.diag(np.concatenate([np.diag(self.Qf)[:2],
                                            np.diag(self.Qf)[3:]]))
        Qf_psi = self.Qf[2, 2]
        idx_xy_uvr = [0, 1, 3, 4, 5]
        for k in range(self.N):
            e_xy_uvr = self._X[idx_xy_uvr, k] - self._p_ref[idx_xy_uvr, k]
            e_psi = self._X[2, k] - self._p_ref[2, k]
            cost += ca.mtimes([e_xy_uvr.T, Q_xy_uvr, e_xy_uvr])
            cost += 2 * Q_psi * (1 - ca.cos(e_psi))
            cost += ca.mtimes([self._U[:, k].T, self.R, self._U[:, k]])

            if k == 0:
                du = self._U[:, k] - self._p_u_prev
            else:
                du = self._U[:, k] - self._U[:, k - 1]
            cost += ca.mtimes([du.T, self.Rd, du])

        e_xy_uvr_f = self._X[idx_xy_uvr, self.N] - self._p_ref[idx_xy_uvr, self.N]
        e_psi_f = self._X[2, self.N] - self._p_ref[2, self.N]
        cost += ca.mtimes([e_xy_uvr_f.T, Qf_xy_uvr, e_xy_uvr_f])
        cost += 2 * Qf_psi * (1 - ca.cos(e_psi_f))
        opti.minimize(cost)

        # 动力学约束
        opti.subject_to(self._X[:, 0] == self._p_x0)
        for k in range(self.N):
            opti.subject_to(self._X[:, k + 1] == self._f_rk4(self._X[:, k], self._U[:, k]))

        # 推力边界约束
        for k in range(self.N):
            opti.subject_to(opti.bounded(self.T_min, self._U[0, k], self.T_max))
            opti.subject_to(opti.bounded(self.T_min, self._U[1, k], self.T_max))

        # 推力变化率约束
        dT_step = self.dT_max * self.dt
        opti.subject_to(opti.bounded(-dT_step, self._U[0, 0] - self._p_u_prev[0], dT_step))
        opti.subject_to(opti.bounded(-dT_step, self._U[1, 0] - self._p_u_prev[1], dT_step))
        for k in range(1, self.N):
            opti.subject_to(
                opti.bounded(-dT_step, self._U[0, k] - self._U[0, k - 1], dT_step)
            )
            opti.subject_to(
                opti.bounded(-dT_step, self._U[1, k] - self._U[1, k - 1], dT_step)
            )

        opts = solver_opts or {}
        ipopt_opts = {
            "print_level": 0,
            "max_iter": 300,
            "warm_start_init_point": "yes",
            "tol": 1e-4,
            "acceptable_tol": 1e-3,
            "acceptable_iter": 10,
        }
        ipopt_opts.update(opts)
        opti.solver("ipopt", {"print_time": 0, "ipopt": ipopt_opts})

        self._opti = opti

    def solve(
        self, current_state: np.ndarray, reference_traj: np.ndarray
    ) -> Tuple[np.ndarray, dict]:
        """求解 NMPC 优化问题。

        参数：
            current_state: ROS local map / base_link 坐标系下的 [x, y, psi, u, v, r]
            reference_traj: 形状为 [6, N+1] 的参考状态数组

        返回：
            optimal_control: 单位为牛顿的 [T_L, T_R]
            info: 包含求解器统计信息的字典
        """
        self._opti.set_value(self._p_x0, current_state)
        self._opti.set_value(self._p_ref, reference_traj)
        self._opti.set_value(self._p_u_prev, self._u_prev)

        if self._X_warm is not None and self._U_warm is not None:
            self._opti.set_initial(self._X, self._X_warm)
            self._opti.set_initial(self._U, self._U_warm)
        else:
            self._opti.set_initial(self._X, np.tile(current_state.reshape(-1, 1), self.N + 1))
            self._opti.set_initial(self._U, np.zeros((2, self.N)))

        t_start = time.time()
        try:
            sol = self._opti.solve()
            u_opt = sol.value(self._U[:, 0]).flatten()

            X_sol = sol.value(self._X)
            U_sol = sol.value(self._U)
            self._X_warm = np.hstack([X_sol[:, 1:], X_sol[:, -1:]])
            self._U_warm = np.hstack([U_sol[:, 1:], U_sol[:, -1:]])
            self._u_prev = u_opt

            return u_opt, {
                "success": True,
                "solve_time_ms": (time.time() - t_start) * 1000,
                "X_pred": X_sol,
                "U_pred": U_sol,
            }
        except Exception as e:
            return self._u_prev, {
                "success": False,
                "solve_time_ms": (time.time() - t_start) * 1000,
                "error": str(e),
            }

    def get_predicted_trajectory(self) -> Optional[np.ndarray]:
        return self._X_warm

    def reset_warmstart(self):
        self._X_warm = None
        self._U_warm = None
        self._u_prev = np.zeros(2)
