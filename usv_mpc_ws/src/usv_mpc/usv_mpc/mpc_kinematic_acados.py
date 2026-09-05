"""适用于无人船 (USV) 的运动学 MPC 求解器 —— acados 后端（方案 A）。

与 [mpc_kinematic.KinematicMPC] 求解同一最优控制问题，但用 acados 的
SQP_RTI + HPIPM（生成 C 代码）替代 CasADi/IPOPT，面向实时/嵌入式部署。

对外契约与 KinematicMPC 完全一致（构造签名、solve、reset_warmstart、
get_predicted_trajectory），因此 mpc_node 可通过 `kinematic.backend` 参数
在两者间切换而无需改动控制逻辑。

实现要点（详见 docs/acados_migration.md）：
  * 状态增广 x_aug = [x, y, psi, u, r]，控制 = [du, dr]，DISCRETE 动力学复用
    现成的 RK4 符号函数，从而把跨阶段的 Δu 速率约束化为简单的控制上下界。
  * 航向代价用 NONLINEAR_LS 残差 2*sin(Δψ/2)（即 sqrt(2(1-cosΔψ))），配
    Gauss-Newton，平滑且 Hessian 友好。
  * 参考 (x_ref, y_ref, psi_ref) 作为 acados 参数 p 逐阶段下发。

注意：`acados_template` 仅在实例化本类时才导入（惰性导入），所以在未安装
acados 的环境里 import 本模块、跑 colcon test 都不受影响。
"""

import os
import tempfile
import time
from typing import Optional, Tuple

import numpy as np

from .usv_model_kinematic import USVKinematicModel


class AcadosKinematicMPC:
    """运动学 MPC 控制器（acados SQP_RTI 后端）。接口同 KinematicMPC。"""

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
        use_acados: bool = True,  # 占位，保持与 KinematicMPC 同签名
    ):
        self.dt = dt
        self.N = N
        self.u_max = u_max
        self.u_min = u_min
        self.r_max = r_max
        self.du_max = du_max
        self.dr_max = dr_max

        self.Q = np.diag(Q_diag).astype(float)
        self.R = np.diag(R_diag).astype(float)
        self.Qf = float(Qf_scale) * self.Q

        # 热启动缓存：上一周期实际下发的控制 [u, r]，作为增广状态的初值分量
        self._u_prev = np.zeros(2)

        self._build_solver(solver_opts or {})

    # ------------------------------------------------------------------ #
    # 构建
    # ------------------------------------------------------------------ #
    def _build_solver(self, solver_opts: dict):
        # 惰性导入：未装 acados 的环境仍可 import 本模块
        import casadi as ca
        from acados_template import AcadosModel, AcadosOcp, AcadosOcpSolver

        N, dt = self.N, self.dt

        # --- 符号变量：增广状态 [x,y,psi,u,r]，控制 [du,dr] ---
        x = ca.SX.sym("x")
        y = ca.SX.sym("y")
        psi = ca.SX.sym("psi")
        u = ca.SX.sym("u")
        r = ca.SX.sym("r")
        x_aug = ca.vertcat(x, y, psi, u, r)

        du = ca.SX.sym("du")
        dr = ca.SX.sym("dr")
        u_aug = ca.vertcat(du, dr)

        # 参考参数 p = [x_ref, y_ref, psi_ref]
        p = ca.SX.sym("p", 3)

        # --- DISCRETE 动力学：复用现成 RK4 符号函数 ---
        f_rk4 = USVKinematicModel(dt=dt).casadi_function()  # [X0(3),U(2)] -> X(3)
        pos_next = f_rk4(ca.vertcat(x, y, psi), ca.vertcat(u, r))
        x_next = ca.vertcat(pos_next, u + du, r + dr)

        model = AcadosModel()
        model.name = "usv_kinematic_acados"
        model.x = x_aug
        model.u = u_aug
        model.p = p
        model.disc_dyn_expr = x_next

        # --- NONLINEAR_LS 代价：残差 [ex, ey, 2 sin(Δψ/2), u, r] ---
        e_x = x - p[0]
        e_y = y - p[1]
        e_psi = 2.0 * ca.sin((psi - p[2]) / 2.0)  # sqrt(2(1-cosΔψ))
        model.cost_y_expr = ca.vertcat(e_x, e_y, e_psi, u, r)
        model.cost_y_expr_e = ca.vertcat(e_x, e_y, e_psi)

        ocp = AcadosOcp()
        ocp.model = model
        # 时域：新版用 solver_options.N_horizon；旧版回退 dims.N
        if hasattr(ocp.solver_options, "N_horizon"):
            ocp.solver_options.N_horizon = N
        else:  # pragma: no cover - 旧版本兼容
            ocp.dims.N = N
        ocp.solver_options.tf = N * dt

        # 权重：W=diag(Qx,Qy,Qpsi,Ru,Rr)，终端 W_e=diag(Qf_xy,Qf_psi)
        ocp.cost.cost_type = "NONLINEAR_LS"
        ocp.cost.cost_type_e = "NONLINEAR_LS"
        ocp.cost.W = np.diag(
            [self.Q[0, 0], self.Q[1, 1], self.Q[2, 2], self.R[0, 0], self.R[1, 1]]
        )
        ocp.cost.W_e = np.diag([self.Qf[0, 0], self.Qf[1, 1], self.Qf[2, 2]])
        ocp.cost.yref = np.zeros(5)
        ocp.cost.yref_e = np.zeros(3)

        # --- 约束 ---
        # 控制（Δu,Δr）上下界：等价于速率约束 |Δu|<=du_max*dt
        ocp.constraints.idxbu = np.array([0, 1])
        ocp.constraints.lbu = np.array([-self.du_max * dt, -self.dr_max * dt])
        ocp.constraints.ubu = np.array([self.du_max * dt, self.dr_max * dt])
        # 状态（u,r，增广分量 idx 3,4）上下界
        ocp.constraints.idxbx = np.array([3, 4])
        ocp.constraints.lbx = np.array([self.u_min, -self.r_max])
        ocp.constraints.ubx = np.array([self.u_max, self.r_max])
        # 初始状态（每周期用 set(0,"lbx"/"ubx") 覆盖）
        ocp.constraints.x0 = np.zeros(5)

        ocp.parameter_values = np.zeros(3)

        # --- 求解器选项：SQP_RTI + HPIPM + DISCRETE ---
        ocp.solver_options.qp_solver = "PARTIAL_CONDENSING_HPIPM"
        ocp.solver_options.hessian_approx = "GAUSS_NEWTON"
        ocp.solver_options.integrator_type = "DISCRETE"
        ocp.solver_options.nlp_solver_type = "SQP_RTI"
        ocp.solver_options.print_level = 0
        for k, v in solver_opts.items():
            setattr(ocp.solver_options, k, v)

        # 生成代码写到可写目录（install/share 可能只读）
        # 目录名带 N/dt: 同机多实例 (不同 N/dt 配置) 不再互相覆盖 codegen
        export_dir = os.path.join(
            tempfile.gettempdir(), "usv_acados",
            f"{model.name}_N{self.N}_dt{self.dt}",
        )
        os.makedirs(export_dir, exist_ok=True)
        json_path = os.path.join(export_dir, "acados_ocp.json")

        # 导出目录 / json 路径：新版(≥0.5.4)用 code_gen_opts，旧版用顶层属性。
        # 构造 AcadosOcpSolver 即触发 C 代码生成 + 编译（几秒，作为 __init__ 预热）。
        if hasattr(ocp, "code_gen_opts"):
            ocp.code_gen_opts.code_export_directory = export_dir
            ocp.code_gen_opts.json_file = json_path
            self._solver = AcadosOcpSolver(ocp)
        else:  # pragma: no cover - 旧版本兼容
            ocp.code_export_directory = export_dir
            self._solver = AcadosOcpSolver(ocp, json_file=json_path)

        # 再做一次空求解，预热 QP（避免首个控制周期超时）
        try:
            self._warm_once()
        except Exception:  # pragma: no cover
            pass

    def _warm_once(self):
        x0 = np.zeros(5)
        self._solver.set(0, "lbx", x0)
        self._solver.set(0, "ubx", x0)
        for k in range(self.N + 1):
            self._solver.set(k, "p", np.zeros(3))
        self._solver.solve()

    # ------------------------------------------------------------------ #
    # 求解
    # ------------------------------------------------------------------ #
    def solve(
        self, current_state: np.ndarray, reference_traj: np.ndarray
    ) -> Tuple[np.ndarray, dict]:
        """求解 MPC。参数/返回与 KinematicMPC.solve 一致。

        current_state: [x, y, psi]
        reference_traj: [3, N+1] 的参考状态
        返回: (optimal_control[u,r], info{success, solve_time_ms, X_pred, U_pred})
        """
        t_start = time.time()
        try:
            x0 = np.concatenate([np.asarray(current_state, float), self._u_prev])
            self._solver.set(0, "lbx", x0)
            self._solver.set(0, "ubx", x0)
            for k in range(self.N + 1):
                self._solver.set(k, "p", np.asarray(reference_traj[:, k], float))

            status = self._solver.solve()
            solve_time = time.time() - t_start

            du0 = np.asarray(self._solver.get(0, "u"), float)
            u_opt = self._u_prev + du0
            # 数值安全：钳到边界
            u_opt[0] = float(np.clip(u_opt[0], self.u_min, self.u_max))
            u_opt[1] = float(np.clip(u_opt[1], -self.r_max, self.r_max))

            X_full = np.array(
                [np.asarray(self._solver.get(k, "x"), float) for k in range(self.N + 1)]
            ).T  # [5, N+1]
            X_pred = X_full[:3, :]
            U_pred = X_full[3:5, 1:]  # 各阶段实际 [u,r]

            if status != 0:
                # RTI 单步：status!=0 视为本周期失败，交给节点的失败计数处理
                return self._u_prev, {
                    "success": False,
                    "solve_time_ms": solve_time * 1000,
                    "error": f"acados status {status}",
                    "X_pred": X_pred,
                }

            self._u_prev = u_opt
            return u_opt, {
                "success": True,
                "solve_time_ms": solve_time * 1000,
                "X_pred": X_pred,
                "U_pred": U_pred,
            }
        except Exception as e:  # pragma: no cover
            return self._u_prev, {
                "success": False,
                "solve_time_ms": (time.time() - t_start) * 1000,
                "error": str(e),
            }

    def get_predicted_trajectory(self) -> Optional[np.ndarray]:
        """返回上一次预测的状态轨迹 [3, N+1]，用于可视化。"""
        try:
            X_full = np.array(
                [np.asarray(self._solver.get(k, "x"), float) for k in range(self.N + 1)]
            ).T
            return X_full[:3, :]
        except Exception:  # pragma: no cover
            return None

    def reset_warmstart(self):
        """重置热启动缓存与求解器内部轨迹。"""
        self._u_prev = np.zeros(2)
        reset = getattr(self._solver, "reset", None)
        if callable(reset):
            try:
                reset()
            except Exception:  # pragma: no cover
                pass
