#!/usr/bin/env python3
"""重新生成 usv_mpc_cpp 的 vendored acados codegen C 源码 (动力学 NMPC)。

本脚本是原 Python 包 usv_mpc/mpc_dynamic.py + usv_model_dynamic.py 中
**仅 codegen 相关部分** 的自足归档。usv_mpc_cpp 平时直接编译 acados_generated/
下已 vendored 的 C 源码,不需要本脚本;**只有在改动 OCP 结构** (状态/控制/参数维度、
horizon N、代价/约束形式、积分器、求解器类型) 时才需要重新生成。

数值参数 (水动力学系数、Q/R/Rd/Qf 权重) 通过运行时 p_global (30维) 下发,
**改这些不需要重新 codegen**,故本脚本用占位默认值即可。
推力边界 (T_max/T_min) 与变化率边界 (dT_max) 烘焙于 codegen,但自 2026-08-11
起由 acados_backend.cpp solve() 按 yaml 逐阶段运行时下发 (K1/K2,
lbu/ubu/lh/uh set 接口),改 yaml 即生效,同样无需重新 codegen。

用法:
    # 需先装 acados_template + casadi (见 docs/pi5_deploy.md)
    python3 regenerate_acados_codegen.py                 # 生成到 ../acados_generated
    python3 regenerate_acados_codegen.py --horizon 20    # 指定 horizon N
    python3 regenerate_acados_codegen.py -o /tmp/gen      # 生成到别处

生成后 acados_generated/ 的文件集会被裁剪成 usv_mpc_cpp CMake 需要的最小集
(排除 main_*.c / acados_sim_solver_* / Makefile / *.o),然后 colcon build 即可。

OCP 设计 (与历史 codegen 完全一致,勿随意改动,否则破坏 C++ 侧索引约定):
  - 增广状态 x_aug = [x,y,psi,u,v,r, T_L_prev,T_R_prev]  (nx=8)
  - 控制 u = [T_L, T_R]  (nu=2)
  - 每阶段参数 p = x_ref (6)
  - 全局参数 p_global (30) = 19 水动力学 + 6 Q + 2 R + 2 Rd + 1 Qf_scale
  - 变化率非线性约束 h = u - u_prev, |h| <= dT_max*dt (nh=2, 阶段 0..N-1;
    con_h_expr_0 显式补齐首步, 见 build_ocp 注释)
  - EXTERNAL 代价 (含 2*(1-cos(Δψ)) 航向项)
  - SQP_RTI, DISCRETE 动力学 (内嵌 RK4 4子步; 增广状态 T̄<-u 精确赋值),
    FULL_CONDENSING_HPIPM, GAUSS_NEWTON
"""

import argparse
import os
import shutil
import sys

import numpy as np

# ── 水动力学参数在 p_global 中的布局 (与 acados_backend.cpp fill_hydro 一致) ──
PG_INDICES = {
    "mass": 0, "Iz": 1, "xg": 2, "d_thruster": 3,
    "Xu_dot": 4, "Yv_dot": 5, "Yr_dot": 6, "Nv_dot": 7, "Nr_dot": 8,
    "Xu": 9, "Yv": 10, "Yr": 11, "Nv": 12, "Nr": 13,
    "Xuu": 14, "Yvv": 15, "Yrr": 16, "Nvv": 17, "Nrr": 18,
}
N_HYDRO_PARAMS = 19
PG_N_Q, PG_N_R, PG_N_RD, PG_N_QF = 6, 2, 2, 1
N_P_GLOBAL = N_HYDRO_PARAMS + PG_N_Q + PG_N_R + PG_N_RD + PG_N_QF  # = 30

# 占位默认水动力学 (仅结构用途;运行时由 usv_params.yaml 经 p_global 覆盖)
DEFAULT_HYDRO = {
    "mass": 30.0, "Iz": 8.0, "xg": 0.0, "d_thruster": 0.3,
    "Xu_dot": -3.0, "Yv_dot": -20.0, "Yr_dot": -0.5, "Nv_dot": -0.5, "Nr_dot": -2.0,
    "Xu": -8.0, "Yv": -30.0, "Yr": -1.0, "Nv": -1.0, "Nr": -5.0,
    "Xuu": -15.0, "Yvv": -60.0, "Yrr": -1.0, "Nvv": -1.0, "Nrr": -3.0,
}

# 生成后保留的文件/目录 (其余裁掉)。与 usv_mpc_cpp CMake 的 GLOB 一致。
KEEP_TOP_FILES = {
    "acados_solver_usv_dyn_nmpc.c",
    "acados_solver_usv_dyn_nmpc.h",
    "usv_dyn_nmpc_p_global_precompute_fun.c",
    "usv_dyn_nmpc_p_global_precompute_fun.h",
    "usv_dyn_ocp.json",
}
KEEP_SUBDIRS = {
    "usv_dyn_nmpc_model",
    "usv_dyn_nmpc_constraints",
    "usv_dyn_nmpc_cost",
}


def continuous_ode_expr(states, controls, p_global, ca):
    """连续 Fossen 三自由度 ODE 右端 [eta_dot; nu_dot] (6维)。

    与原 usv_model_dynamic.USVDynamicModel.continuous_ode_expr 完全一致。
    """
    x_s, y_s, psi_s = states[0], states[1], states[2]
    u_s, v_s, r_s = states[3], states[4], states[5]
    TL, TR = controls[0], controls[1]

    g = {name: p_global[idx] for name, idx in PG_INDICES.items()}

    m11 = g["mass"] - g["Xu_dot"]
    m22 = g["mass"] - g["Yv_dot"]
    m23 = g["mass"] * g["xg"] - g["Yr_dot"]
    m32 = g["mass"] * g["xg"] - g["Nv_dot"]
    m33 = g["Iz"] - g["Nr_dot"]

    M = ca.SX(3, 3)
    M[0, 0] = m11
    M[1, 1] = m22
    M[1, 2] = m23
    M[2, 1] = m32
    M[2, 2] = m33
    M_inv = ca.inv(M)

    c13 = -m22 * v_s - m23 * r_s
    c23 = m11 * u_s
    C = ca.SX(3, 3)
    C[0, 2] = c13
    C[1, 2] = c23
    C[2, 0] = -c13
    C[2, 1] = -c23

    D = ca.SX(3, 3)
    D[0, 0] = -g["Xu"] - g["Xuu"] * ca.fabs(u_s)
    D[1, 1] = -g["Yv"] - g["Yvv"] * ca.fabs(v_s)
    D[1, 2] = -g["Yr"] - g["Yrr"] * ca.fabs(r_s)
    D[2, 1] = -g["Nv"] - g["Nvv"] * ca.fabs(v_s)
    D[2, 2] = -g["Nr"] - g["Nrr"] * ca.fabs(r_s)

    tau = ca.vertcat(TL + TR, 0, g["d_thruster"] * (TR - TL))

    nu = ca.vertcat(u_s, v_s, r_s)
    cos_psi, sin_psi = ca.cos(psi_s), ca.sin(psi_s)
    J = ca.SX(3, 3)
    J[0, 0] = cos_psi
    J[0, 1] = -sin_psi
    J[1, 0] = sin_psi
    J[1, 1] = cos_psi
    J[2, 2] = 1
    eta_dot = ca.mtimes(J, nu)

    nu_dot = ca.mtimes(M_inv, tau - ca.mtimes(C, nu) - ca.mtimes(D, nu))
    return ca.vertcat(eta_dot, nu_dot)


def build_ocp(N, dt, T_max, T_min, dT_max):
    """构建 AcadosOcp (对应 mpc_dynamic._build_acados_solver 的结构部分)。"""
    from acados_template import AcadosOcp, AcadosModel
    import casadi as ca

    nx_phys, nu = 6, 2
    nx_aug = nx_phys + nu  # 8
    np_, npg = 6, N_P_GLOBAL

    x = ca.SX.sym("x", nx_aug)
    u = ca.SX.sym("u", nu)
    p = ca.SX.sym("p", np_)              # x_ref (6)
    p_global = ca.SX.sym("p_global", npg)

    x_phys = x[:nx_phys]
    u_prev = x[nx_phys:]

    # 离散动力学 (2026-08-11 修复增广状态语义 bug):
    # 原连续模型 f_expl = [fossen_ode; u] 使 T̄ 按 T̄ <- T̄ + dt*u 积分漂移,
    # 变化率约束/Rd 惩罚实际语义变成 |u_k - (u_prev + dt*Σu)|,随时域指数失真
    # (实测: dT_max=5 时 du 从第 12 步起按 ~1.2 倍/步越界)。
    # 改为 DISCRETE: 物理 6 维内嵌 RK4 (4 子步, 与 casadi_backend 一致),
    # 增广状态精确赋值 T̄ <- u, 恢复 |u_k - u_{k-1}| 语义,与 CasADi 后端统一。
    def rk4_phys(xp, uu, h):
        k1 = continuous_ode_expr(xp, uu, p_global, ca)
        k2 = continuous_ode_expr(xp + h / 2 * k1, uu, p_global, ca)
        k3 = continuous_ode_expr(xp + h / 2 * k2, uu, p_global, ca)
        k4 = continuous_ode_expr(xp + h * k3, uu, p_global, ca)
        return xp + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)

    xc = x_phys
    h_int = dt / 4.0
    for _ in range(4):
        xc = rk4_phys(xc, u, h_int)
    disc_phi = ca.vertcat(xc, u)  # [RK4(物理 6 维); T̄ <- u 精确赋值]

    base = N_HYDRO_PARAMS
    Q = p_global[base:base + PG_N_Q]
    R = p_global[base + PG_N_Q:base + PG_N_Q + PG_N_R]
    Rd = p_global[base + PG_N_Q + PG_N_R:base + PG_N_Q + PG_N_R + PG_N_RD]
    Qf_scale = p_global[base + PG_N_Q + PG_N_R + PG_N_RD]

    idx_xy_uvr = [0, 1, 3, 4, 5]
    x_ref = p

    def stage_cost(xk, uk, uprev_k):
        e = xk[idx_xy_uvr] - x_ref[idx_xy_uvr]
        e_psi = xk[2] - x_ref[2]
        Q_e = ca.diag(ca.vertcat(Q[0], Q[1], Q[3], Q[4], Q[5]))
        cost = ca.mtimes([e.T, Q_e, e])
        cost += 2 * Q[2] * (1 - ca.cos(e_psi))
        cost += ca.mtimes([uk.T, ca.diag(R), uk])
        du = uk - uprev_k
        cost += ca.mtimes([du.T, ca.diag(Rd), du])
        return cost

    def term_cost(xk):
        e = xk[idx_xy_uvr] - x_ref[idx_xy_uvr]
        e_psi = xk[2] - x_ref[2]
        Qf_e = Qf_scale * ca.diag(ca.vertcat(Q[0], Q[1], Q[3], Q[4], Q[5]))
        cost = ca.mtimes([e.T, Qf_e, e])
        cost += 2 * Qf_scale * Q[2] * (1 - ca.cos(e_psi))
        return cost

    con_h = u - u_prev

    model = AcadosModel()
    model.name = "usv_dyn_nmpc"
    model.x = x
    model.u = u
    model.p = p
    model.p_global = p_global
    model.disc_dyn_expr = disc_phi
    model.cost_expr_ext_cost = stage_cost(x, u, u_prev)
    model.cost_expr_ext_cost_e = term_cost(x)
    model.con_h_expr = con_h
    # K2 修复 (2026-08-11): con_h_expr 仅作用于阶段 1..N-1,首步 u_0 相对
    # 实测 u_prev 的变化率此前完全不受硬约束(真正执行的恰恰是 u_0!)。
    # 显式设置 con_h_expr_0 补齐首步约束。
    model.con_h_expr_0 = con_h

    ocp = AcadosOcp()
    ocp.model = model
    ocp.solver_options.N_horizon = N
    ocp.dims.nx = nx_aug
    ocp.dims.nu = nu
    ocp.dims.np = np_
    ocp.dims.np_global = npg
    ocp.dims.nh = nu
    ocp.solver_options.tf = N * dt

    ocp.cost.cost_type = "EXTERNAL"
    ocp.cost.cost_type_e = "EXTERNAL"

    ocp.parameter_values = np.zeros(np_)
    pg = np.zeros(npg)
    for name, idx in PG_INDICES.items():
        pg[idx] = DEFAULT_HYDRO[name]
    ocp.p_global_values = pg

    ocp.constraints.idxbx_0 = np.arange(nx_aug)
    ocp.constraints.lbx_0 = np.zeros(nx_aug)
    ocp.constraints.ubx_0 = np.zeros(nx_aug)

    ocp.constraints.idxbu = np.arange(nu)
    ocp.constraints.lbu = np.array([T_min, T_min])
    ocp.constraints.ubu = np.array([T_max, T_max])

    dT_step = dT_max * dt
    ocp.constraints.lh = np.array([-dT_step, -dT_step])
    ocp.constraints.uh = np.array([dT_step, dT_step])
    # K2: 首步变化率边界 (配合 con_h_expr_0)
    ocp.constraints.lh_0 = np.array([-dT_step, -dT_step])
    ocp.constraints.uh_0 = np.array([dT_step, dT_step])
    ocp.constraints.constr_type = "BGH"

    ocp.solver_options.nlp_solver_type = "SQP_RTI"
    ocp.solver_options.integrator_type = "DISCRETE"  # 见上文增广状态修复说明
    ocp.solver_options.qp_solver = "FULL_CONDENSING_HPIPM"
    ocp.solver_options.hessian_approx = "GAUSS_NEWTON"
    ocp.solver_options.nlp_solver_max_iter = 50
    # K2 修复后变化率约束在全部阶段生效,边界收紧场景(如 dT_max 远小于烘焙值)
    # 下 QP 需要更多迭代才能收敛到硬约束容差内;50 -> 200。
    # 该 QP 规模很小(全凝聚后 ~20 阶段),迭代代价微秒级,标称求解时间不变。
    ocp.solver_options.qp_solver_iter_max = 200
    return ocp


def prune(out_dir):
    """裁剪成 usv_mpc_cpp CMake 需要的最小文件集。"""
    for entry in os.listdir(out_dir):
        path = os.path.join(out_dir, entry)
        if os.path.isdir(path):
            if entry not in KEEP_SUBDIRS:
                shutil.rmtree(path)
            else:
                # 子目录内仅保留 .c/.h
                for f in os.listdir(path):
                    if not f.endswith((".c", ".h")):
                        os.remove(os.path.join(path, f))
        else:
            if entry not in KEEP_TOP_FILES:
                os.remove(path)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default_out = os.path.normpath(os.path.join(here, "..", "acados_generated"))

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output-dir", default=default_out,
                    help=f"生成目录 (默认 {default_out})")
    ap.add_argument("--horizon", type=int, default=20,
                    help="预测步数 N_horizon (默认 20; 改动须同步 C++ 侧配置)")
    ap.add_argument("--dt", type=float, default=0.1, help="步长 dt 秒 (默认 0.1)")
    ap.add_argument("--t-max", type=float, default=40.0)
    ap.add_argument("--t-min", type=float, default=-20.0)
    ap.add_argument("--dt-max", type=float, default=30.0, help="推力变化率上限 N/s")
    ap.add_argument("--keep-build-artifacts", action="store_true",
                    help="保留 main_*/sim/Makefile/.o (调试用, CMake 不需要)")
    args = ap.parse_args()

    try:
        from acados_template import AcadosOcpSolver  # noqa: F401
    except Exception as e:
        sys.exit(f"[错误] 需要 acados_template ({type(e).__name__}: {e})。"
                 " 见 docs/pi5_deploy.md 安装 acados。")

    from acados_template import AcadosOcpSolver

    out_dir = os.path.abspath(args.output_dir)
    os.makedirs(out_dir, exist_ok=True)
    print(f"[codegen] 生成到 {out_dir} (N={args.horizon}, dt={args.dt})")

    ocp = build_ocp(args.horizon, args.dt, args.t_max, args.t_min, args.dt_max)
    ocp.code_export_directory = out_dir
    json_file = os.path.join(out_dir, "usv_dyn_ocp.json")

    # generate=True 写 C 源码; build=False 不编译 .so (由 usv_mpc_cpp CMake 编译)
    AcadosOcpSolver(ocp, json_file=json_file, generate=True, build=False)

    if not args.keep_build_artifacts:
        prune(out_dir)
        print("[codegen] 已裁剪为 CMake 最小文件集")

    n_c = sum(len([f for f in files if f.endswith(".c")])
              for _, _, files in os.walk(out_dir))
    print(f"[codegen] 完成, {n_c} 个 .c 源文件。请 colcon build --packages-select usv_mpc_cpp")


if __name__ == "__main__":
    main()
