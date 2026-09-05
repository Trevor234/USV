"""适用于无人船 (USV) 的运动学 MPC 求解器（方案 A）。

求解如下最优控制问题：
  min  sum_k ||x_k - x_k^ref||_Q^2 + ||u_k||_R^2  +  ||x_N - x_N^ref||_Qf^2
  (注意: R 项是控制量正则化到 0, 参考速度剖面不直接进入代价;
   稳态跟踪偏差由位置项间接驱动)
  s.t. x_{k+1} = f(x_k, u_k),  x_0 = 当前状态
       u_min <= u <= u_max,  delta_u_min <= delta_u <= delta_u_max

使用 CasADi Opti 与 IPOPT 后端（嵌入式部署时可替换为 acados）。
"""

import time
from typing import Optional, Tuple

import casadi as ca
import numpy as np

from .usv_model_kinematic import USVKinematicModel


class KinematicMPC:
    """用于无人船路径跟踪的运动学 MPC 控制器。"""

    def __init__(
        self,
        dt: float = 0.2,
        N: int = 20,
        Q_diag: Tuple[float, float, float] = (10.0, 10.0, 50.0),
        R_diag: Tuple[float, float] = (1.0, 1.0),
        Qf_scale: float = 10.0,
        u_max: float = 2.0,
        u_min: float = 0.0,
        r_max: float = 0.5,
        du_max: float = 0.8,
        dr_max: float = 0.5,
        solver_opts: Optional[dict] = None,
        use_acados: bool = False,
    ):
        self.dt = dt
        self.N = N
        self.u_max = u_max
        self.u_min = u_min
        self.r_max = r_max
        self.du_max = du_max
        self.dr_max = dr_max

        self.model = USVKinematicModel(dt=dt)
        self._f_rk4 = self.model.casadi_function()

        self.Q = np.diag(Q_diag)
        self.R = np.diag(R_diag)
        self.Qf = Qf_scale * self.Q

        self._use_acados = use_acados
        self._build_solver(solver_opts)

        # 热启动缓存
        self._X_warm: Optional[np.ndarray] = None
        self._U_warm: Optional[np.ndarray] = None
        self._u_prev = np.zeros(2)

    def _build_solver(self, solver_opts: Optional[dict] = None):
        """构建 CasADi Opti MPC 优化问题。"""
        opti = ca.Opti()

        # 决策变量
        self._X = opti.variable(3, self.N + 1)
        self._U = opti.variable(2, self.N)

        # 参数
        self._p_x0 = opti.parameter(3, 1)
        self._p_ref = opti.parameter(3, self.N + 1)
        self._p_u_prev = opti.parameter(2, 1)

        # 代价函数
        # 航向角误差使用 2*(1 - cos(Δψ))，而不是 atan2 包角后的 Δψ²：
        # 两者在小角度下都近似为 Δψ²，但 1-cos 全局平滑且具有 2π 周期性，
        # 可避免 ±π 处的 C1 不连续在急转弯时拖慢 IPOPT。
        # Q[2,2] 仍保持原来的角度权重含义。
        cost = 0
        Qxy = self.Q[:2, :2]
        Q_psi = self.Q[2, 2]
        Qf_xy = self.Qf[:2, :2]
        Qf_psi = self.Qf[2, 2]
        for k in range(self.N):
            e_xy = self._X[:2, k] - self._p_ref[:2, k]
            e_psi = self._X[2, k] - self._p_ref[2, k]
            cost += ca.mtimes([e_xy.T, Qxy, e_xy])
            cost += 2 * Q_psi * (1 - ca.cos(e_psi))
            cost += ca.mtimes([self._U[:, k].T, self.R, self._U[:, k]])

        e_xy_f = self._X[:2, self.N] - self._p_ref[:2, self.N]
        e_psi_f = self._X[2, self.N] - self._p_ref[2, self.N]
        cost += ca.mtimes([e_xy_f.T, Qf_xy, e_xy_f])
        cost += 2 * Qf_psi * (1 - ca.cos(e_psi_f))
        opti.minimize(cost)

        # 动力学约束
        opti.subject_to(self._X[:, 0] == self._p_x0)
        for k in range(self.N):
            x_next = self._f_rk4(self._X[:, k], self._U[:, k])
            opti.subject_to(self._X[:, k + 1] == x_next)

        # 控制量边界约束
        for k in range(self.N):
            opti.subject_to(opti.bounded(self.u_min, self._U[0, k], self.u_max))
            opti.subject_to(opti.bounded(-self.r_max, self._U[1, k], self.r_max))

        # 控制量变化率约束
        du_step = self.du_max * self.dt
        dr_step = self.dr_max * self.dt
        opti.subject_to(opti.bounded(-du_step, self._U[0, 0] - self._p_u_prev[0], du_step))
        opti.subject_to(opti.bounded(-dr_step, self._U[1, 0] - self._p_u_prev[1], dr_step))
        for k in range(1, self.N):
            opti.subject_to(opti.bounded(-du_step, self._U[0, k] - self._U[0, k - 1], du_step))
            opti.subject_to(opti.bounded(-dr_step, self._U[1, k] - self._U[1, k - 1], dr_step))

        # 求解器选项
        opts = solver_opts or {}
        ipopt_opts = {
            "print_level": 0,
            "max_iter": 200,
            "warm_start_init_point": "yes",
            "tol": 1e-4,
            "acceptable_tol": 1e-3,
            "acceptable_iter": 5,
        }
        ipopt_opts.update(opts)
        opti.solver("ipopt", {"print_time": 0, "ipopt": ipopt_opts})

        self._opti = opti

    def solve(
        self, current_state: np.ndarray, reference_traj: np.ndarray
    ) -> Tuple[np.ndarray, dict]:
        """求解 MPC 优化问题。

        参数：
            current_state: NED 坐标系下的 [x, y, psi]
            reference_traj: 形状为 [3, N+1] 的参考状态数组

        返回：
            optimal_control: [u_surge, r_yaw]
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
            # 显式钳位: IPOPT 只以求解器精度满足约束, 与 acados 后端
            # (发布前 clip) 对称, 避免后端间输出保证不一致
            u_opt = np.clip(u_opt, [self.u_min, -self.r_max],
                            [self.u_max, self.r_max])

            # 保存平移后的热启动解
            X_sol = sol.value(self._X)
            U_sol = sol.value(self._U)
            self._X_warm = np.hstack([X_sol[:, 1:], X_sol[:, -1:]])
            self._U_warm = np.hstack([U_sol[:, 1:], U_sol[:, -1:]])
            self._u_prev = u_opt

            solve_time = time.time() - t_start
            return u_opt, {
                "success": True,
                "solve_time_ms": solve_time * 1000,
                "X_pred": X_sol,
                "U_pred": U_sol,
            }
        except Exception as e:
            t_elapsed = time.time() - t_start
            return self._u_prev, {
                "success": False,
                "solve_time_ms": t_elapsed * 1000,
                "error": str(e),
            }

    def get_predicted_trajectory(self) -> Optional[np.ndarray]:
        """返回上一次预测的状态轨迹，用于可视化。"""
        return self._X_warm

    def reset_warmstart(self):
        """重置热启动缓存。"""
        self._X_warm = None
        self._U_warm = None
        self._u_prev = np.zeros(2)
