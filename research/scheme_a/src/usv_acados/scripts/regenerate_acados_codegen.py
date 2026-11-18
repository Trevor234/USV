#!/usr/bin/env python3
"""重新生成 usv_acados 的 vendored acados codegen C 源码 (方案 A/B 两个 OCP)。

本脚本用于离线生成 usv_acados 的 acados OCP C 源码。usv_acados 平时直接编译
acados_generated/{kinematic,dynamic}/ 下已 vendored 的 C 源码, 不需要本脚本;
**只有在改动 OCP 结构** (状态/控制/参数维度、horizon N、代价/约束形式、积分器、
求解器类型) 时才需要重新生成。数值参数 (权重、边界、水动力、tau) 通过运行时
p_global / lbu-ubu-lh-uh 下发, 改这些不需要重新 codegen。

用法:
    # 需先装 acados_template + casadi (或把 acados 源码树的 interfaces/acados_template
    # 加入 PYTHONPATH, 并把 $ACADOS_SOURCE_DIR 指向该源码树)
    python3 regenerate_acados_codegen.py --model kinematic
    python3 regenerate_acados_codegen.py --model dynamic
    python3 regenerate_acados_codegen.py --model kinematic --horizon 20 --dt 0.2 \
        --output-dir ../acados_generated/kinematic

生成后输出目录会被裁剪成 usv_acados CMake 需要的最小文件集 (按生成 JSON 的
external_function_files_* 引用清单), 然后 colcon build 即可。

两个模型的 OCP 设计 (C++ 侧索引契约见 src/model_api.cpp 的 static_assert):

kinematic (usv_kin_mpc_*, 方案 A 运动学):
  - 物理状态 [x,y,psi,u,r] (5) + 增广尾部 [u_cmd_prev,r_cmd_prev] (2) => nx=7
  - 控制 u=[u_cmd,r_cmd] (nu=2), 每阶段参数 p=[x_ref,y_ref,psi_ref] (np=3)
  - p_global (8) = [tau_u,tau_r,Qx,Qy,Qpsi,Ru,Rr,Qf_scale]
  - 变化率非线性约束 h=u-x[5:7], |h| <= [du_max*dt, dr_max*dt] (nh=2,
    含 con_h_expr_0 首步)
  - NONLINEAR_LS (ny_0=ny=6: 3 线性 + 2 单位圆航向 + 2 控制; ny_e=4),
    cost_scaling=ones(N+1) —— 阶段代价不乘 dt, 与原 CasADi 目标逐点一致
  - SQP + MERIT_BACKTRACKING + GAUSS_NEWTON + FULL_CONDENSING_HPIPM,
    timeout_max_time=0.12s, tol=1e-4, print_level=0
  - DISCRETE 动力学 (内嵌 RK4 4 子步; 增广状态 u_prev <- u 精确赋值)

dynamic (usv_dyn_nmpc_*, 方案 B 动力学, 数学内容与历史 codegen 完全一致):
  - 增广状态 x_aug=[x,y,psi,u,v,r,T_L_prev,T_R_prev] (nx=8)
  - 控制 u=[T_L,T_R] (nu=2), 每阶段参数 p=x_ref (np=6)
  - p_global (30) = 19 水动力学 + 6 Q + 2 R + 2 Rd + 1 Qf_scale
  - 变化率非线性约束 h=u-x[6:8], |h| <= dT_max*dt (nh=2, 含 con_h_expr_0)
  - NONLINEAR_LS (ny_0=ny=11, ny_e=7), cost_scaling=[dt,...,dt,1] (acados 默认)
  - SQP_RTI + GAUSS_NEWTON + FULL_CONDENSING_HPIPM
  - DISCRETE 动力学 (内嵌 RK4 4 子步; 增广状态 T̄ <- u 精确赋值)
"""

import argparse
import json
import os
import shutil
import sys

import numpy as np

# ── 水动力学参数在 p_global 中的布局 (与 dynamic 适配器的 fill_hydro 一致) ──
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

# ── 运动学 p_global 布局 (与 kinematic 适配器一致) ──
PG_K_TAU_U, PG_K_TAU_R = 0, 1
PG_K_QX, PG_K_QY, PG_K_QPSI = 2, 3, 4
PG_K_RU, PG_K_RR = 5, 6
PG_K_QF = 7
N_P_GLOBAL_KIN = 8

# 占位默认值: tau 绝不能为 0 (生成码会做 /tau 与 precompute 除法)。
DEFAULT_KINEMATIC = {
    "tau_u": 0.8, "tau_r": 1.78,
    "Qx": 10.0, "Qy": 10.0, "Qpsi": 50.0,
    "Ru": 1.0, "Rr": 1.0, "Qf_scale": 10.0,
}

MODELS = {
    "kinematic": {
        "model_name": "usv_kin_mpc",
        "json_name": "usv_kin_ocp.json",
        "symbol": "usv_kin_mpc",
    },
    "dynamic": {
        "model_name": "usv_dyn_nmpc",
        "json_name": "usv_dyn_ocp.json",
        "symbol": "usv_dyn_nmpc",
    },
}


# ── 方案 B: 动力学 OCP (数学内容与历史 codegen 完全一致, 勿随意改动) ──
def continuous_ode_expr(states, controls, p_global, ca):
    """连续 Fossen 三自由度 ODE 右端 [eta_dot; nu_dot] (6维)。

    与 USVDynamicModel::continuous_ode 数值模型保持一致。
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


def build_dynamic_ocp(N, dt, T_max, T_min, dT_max):
    """构建方案 B 的 AcadosOcp (与 dynamic 适配器的 OCP 契约一致)。"""
    from acados_template import AcadosOcp, AcadosModel
    import casadi as ca

    nx_phys, nu = 6, 2
    nx_aug = nx_phys + nu  # 8
    np_, npg = 12, N_P_GLOBAL

    x = ca.SX.sym("x", nx_aug)
    u = ca.SX.sym("u", nu)
    p = ca.SX.sym("p", np_)              # [x_ref(6), res_nu(3), q_pi(2), beta_pi(1)]
    p_global = ca.SX.sym("p_global", npg)

    x_phys = x[:nx_phys]
    u_prev = x[nx_phys:]

    # 离散动力学: 物理 6 维内嵌 RK4 (4 子步) + GP 离散速度增量, 增广状态精确赋值 T̄ <- u。
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
    xc_corr = xc + ca.vertcat(0.0, 0.0, 0.0, p[6], p[7], p[8])
    disc_phi = ca.vertcat(xc_corr, u)  # [RK4(物理 6 维)+残差; T̄ <- u 精确赋值]

    base = N_HYDRO_PARAMS
    Q = p_global[base:base + PG_N_Q]
    R = p_global[base + PG_N_Q:base + PG_N_Q + PG_N_R]
    Rd = p_global[base + PG_N_Q + PG_N_R:base + PG_N_Q + PG_N_R + PG_N_RD]
    Qf_scale = p_global[base + PG_N_Q + PG_N_R + PG_N_RD]

    idx_xy_uvr = [0, 1, 3, 4, 5]
    x_ref = p[:6]
    q_pi = p[9:11]
    beta_pi = p[11]

    # acados NONLINEAR_LS 使用 0.5 * y.T * W * y。把 sqrt(2*w)
    # 吸收到残差并令 W=I, 可保持原 Q/R/Rd 代价值完全不变。航向的两个
    # 单位圆残差平方和等于 2*(1-cos(delta_psi)), 因此对应原来的
    # 2*Q_psi*(1-cos(delta_psi)), 同时得到半正定 Gauss-Newton Hessian。
    # WP7: beta_pi = sqrt(2*lambda_pi/dt) 在 cost_scaling=dt 下给出 lambda_pi*||u - q_pi||^2 (仅 stage 0 非零).
    def stage_residual(xk, uk, uprev_k):
        e = xk[idx_xy_uvr] - x_ref[idx_xy_uvr]
        state_res = ca.vertcat(*[
            ca.sqrt(2 * Q[idx]) * e[row]
            for row, idx in enumerate(idx_xy_uvr)
        ])
        heading_res = ca.sqrt(2 * Q[2]) * ca.vertcat(
            ca.sin(xk[2]) - ca.sin(x_ref[2]),
            ca.cos(xk[2]) - ca.cos(x_ref[2]),
        )
        control_res = ca.vertcat(
            ca.sqrt(2 * R[0]) * uk[0],
            ca.sqrt(2 * R[1]) * uk[1],
        )
        du = uk - uprev_k
        increment_res = ca.vertcat(
            ca.sqrt(2 * Rd[0]) * du[0],
            ca.sqrt(2 * Rd[1]) * du[1],
        )
        pref_res = beta_pi * (uk - q_pi)
        return ca.vertcat(state_res, heading_res, control_res, increment_res, pref_res)

    def terminal_residual(xk):
        e = xk[idx_xy_uvr] - x_ref[idx_xy_uvr]
        state_res = ca.vertcat(*[
            ca.sqrt(2 * Qf_scale * Q[idx]) * e[row]
            for row, idx in enumerate(idx_xy_uvr)
        ])
        heading_res = ca.sqrt(2 * Qf_scale * Q[2]) * ca.vertcat(
            ca.sin(xk[2]) - ca.sin(x_ref[2]),
            ca.cos(xk[2]) - ca.cos(x_ref[2]),
        )
        return ca.vertcat(state_res, heading_res)

    con_h = u - u_prev

    model = AcadosModel()
    model.name = MODELS["dynamic"]["model_name"]
    model.x = x
    model.u = u
    model.p = p
    model.p_global = p_global
    model.disc_dyn_expr = disc_phi
    model.cost_y_expr = stage_residual(x, u, u_prev)
    model.cost_y_expr_e = terminal_residual(x)
    model.con_h_expr = con_h
    # con_h_expr 仅作用于阶段 1..N-1; 首步 u_0 相对实测 u_prev 的变化率必须
    # 由 con_h_expr_0 补齐 (真正执行的恰恰是 u_0)。
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

    ny, ny_e = 13, 7
    ocp.cost.cost_type = "NONLINEAR_LS"
    ocp.cost.cost_type_e = "NONLINEAR_LS"
    ocp.cost.W = np.eye(ny)
    ocp.cost.W_e = np.eye(ny_e)
    ocp.cost.yref = np.zeros(ny)
    ocp.cost.yref_e = np.zeros(ny_e)

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
    ocp.constraints.lh_0 = np.array([-dT_step, -dT_step])
    ocp.constraints.uh_0 = np.array([dT_step, dT_step])
    ocp.constraints.constr_type = "BGH"

    ocp.solver_options.nlp_solver_type = "SQP_RTI"
    ocp.solver_options.integrator_type = "DISCRETE"  # 增广状态精确赋值语义
    ocp.solver_options.qp_solver = "FULL_CONDENSING_HPIPM"
    ocp.solver_options.hessian_approx = "GAUSS_NEWTON"
    ocp.solver_options.nlp_solver_max_iter = 50
    ocp.solver_options.qp_solver_iter_max = 200
    return ocp


# ── 方案 A: 运动学 OCP ──────────────────────────────────────────────
def kinematic_ode_expr(s, uc, rc, p_global, ca):
    """连续运动学 ODE (5 状态, 含执行器一阶滞后)。

    与 USVKinematicModel::continuous_ode(Vector5d, control, tau_u, tau_r)
    数值模型一致; 这里 tau 来自 p_global, 因此在 OCP 内是参数。
    """
    tau_u = p_global[PG_K_TAU_U]
    tau_r = p_global[PG_K_TAU_R]
    psi, u, r = s[2], s[3], s[4]
    return ca.vertcat(
        u * ca.cos(psi),
        u * ca.sin(psi),
        r,
        (uc - u) / tau_u,
        (rc - r) / tau_r,
    )


def num_rk4_kinematic(state, control, tau_u, tau_r, dt, substeps=4):
    """独立 NumPy 参考实现 (4 子步 RK4), 用于生成期语义比对。"""
    def rhs(s, c):
        psi, u, r = s[2], s[3], s[4]
        return np.array([
            u * np.cos(psi),
            u * np.sin(psi),
            r,
            (c[0] - u) / tau_u,
            (c[1] - r) / tau_r,
        ])

    x = np.array(state, dtype=float)
    h = dt / float(substeps)
    for _ in range(substeps):
        k1 = rhs(x, control)
        k2 = rhs(x + 0.5 * h * k1, control)
        k3 = rhs(x + 0.5 * h * k2, control)
        k4 = rhs(x + h * k3, control)
        x = x + h / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
    return x


def build_kinematic_ocp(N, dt, u_max, u_min, r_max, du_max, dr_max):
    """构建方案 A 的 AcadosOcp (运动学, 5 物理状态 + 2 增广)。"""
    from acados_template import AcadosOcp, AcadosModel
    import casadi as ca

    nx_phys, nu = 5, 2
    nx_aug = nx_phys + nu  # 7
    np_, npg = 3, N_P_GLOBAL_KIN

    x = ca.SX.sym("x", nx_aug)
    u = ca.SX.sym("u", nu)
    p = ca.SX.sym("p", np_)              # [x_ref, y_ref, psi_ref]
    p_global = ca.SX.sym("p_global", npg)

    s = x[:nx_phys]
    u_prev = x[nx_phys:]

    # DISCRETE 动力学: 物理 5 维内嵌 RK4 (4 子步), 增广尾部精确赋值 u。
    def rk4_phys(sp, uc, rc, h):
        k1 = kinematic_ode_expr(sp, uc, rc, p_global, ca)
        k2 = kinematic_ode_expr(sp + h / 2 * k1, uc, rc, p_global, ca)
        k3 = kinematic_ode_expr(sp + h / 2 * k2, uc, rc, p_global, ca)
        k4 = kinematic_ode_expr(sp + h * k3, uc, rc, p_global, ca)
        return sp + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)

    sc = s
    h_int = dt / 4.0
    for _ in range(4):
        sc = rk4_phys(sc, u[0], u[1], h_int)
    disc_phi = ca.vertcat(sc, u)  # [RK4(物理 5 维); u_prev <- u 精确赋值]

    Qx = p_global[PG_K_QX]
    Qy = p_global[PG_K_QY]
    Qpsi = p_global[PG_K_QPSI]
    Ru = p_global[PG_K_RU]
    Rr = p_global[PG_K_RR]
    Qf_scale = p_global[PG_K_QF]

    x_ref, y_ref, psi_ref = p[0], p[1], p[2]

    # 0.5*y'W*y with W=I 下, 残差乘 sqrt(2*weight) 还原原目标:
    #   Qx*ex^2 + Qy*ey^2 + 2*Qpsi*(1-cos(dpsi)) + Ru*uc^2 + Rr*rc^2
    # 航向用两个单位圆残差, 平方和恰为 2*(1-cos(dpsi))。
    def stage_residual(xk, uk):
        return ca.vertcat(
            ca.sqrt(2 * Qx) * (xk[0] - x_ref),
            ca.sqrt(2 * Qy) * (xk[1] - y_ref),
            ca.sqrt(2 * Qpsi) * (ca.sin(xk[2]) - ca.sin(psi_ref)),
            ca.sqrt(2 * Qpsi) * (ca.cos(xk[2]) - ca.cos(psi_ref)),
            ca.sqrt(2 * Ru) * uk[0],
            ca.sqrt(2 * Rr) * uk[1],
        )

    def terminal_residual(xk):
        return ca.vertcat(
            ca.sqrt(2 * Qf_scale * Qx) * (xk[0] - x_ref),
            ca.sqrt(2 * Qf_scale * Qy) * (xk[1] - y_ref),
            ca.sqrt(2 * Qf_scale * Qpsi) * (ca.sin(xk[2]) - ca.sin(psi_ref)),
            ca.sqrt(2 * Qf_scale * Qpsi) * (ca.cos(xk[2]) - ca.cos(psi_ref)),
        )

    con_h = u - u_prev

    model = AcadosModel()
    model.name = MODELS["kinematic"]["model_name"]
    model.x = x
    model.u = u
    model.p = p
    model.p_global = p_global
    model.disc_dyn_expr = disc_phi
    model.cost_y_expr = stage_residual(x, u)
    model.cost_y_expr_e = terminal_residual(x)
    model.con_h_expr = con_h
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

    ny, ny_e = 6, 4
    ocp.cost.cost_type = "NONLINEAR_LS"
    ocp.cost.cost_type_e = "NONLINEAR_LS"
    ocp.cost.W = np.eye(ny)
    ocp.cost.W_e = np.eye(ny_e)
    ocp.cost.yref = np.zeros(ny)
    ocp.cost.yref_e = np.zeros(ny_e)

    ocp.parameter_values = np.zeros(np_)
    pg = np.zeros(npg)
    pg[PG_K_TAU_U] = DEFAULT_KINEMATIC["tau_u"]
    pg[PG_K_TAU_R] = DEFAULT_KINEMATIC["tau_r"]
    pg[PG_K_QX] = DEFAULT_KINEMATIC["Qx"]
    pg[PG_K_QY] = DEFAULT_KINEMATIC["Qy"]
    pg[PG_K_QPSI] = DEFAULT_KINEMATIC["Qpsi"]
    pg[PG_K_RU] = DEFAULT_KINEMATIC["Ru"]
    pg[PG_K_RR] = DEFAULT_KINEMATIC["Rr"]
    pg[PG_K_QF] = DEFAULT_KINEMATIC["Qf_scale"]
    ocp.p_global_values = pg

    # stage 0 钉住全部 7 维 (运行时每拍写入 [measured; anchor])
    ocp.constraints.idxbx_0 = np.arange(nx_aug)
    ocp.constraints.lbx_0 = np.zeros(nx_aug)
    ocp.constraints.ubx_0 = np.zeros(nx_aug)

    # 两通道非对称幅值边界 (运行时按 YAML 逐阶段覆盖)
    ocp.constraints.idxbu = np.arange(nu)
    ocp.constraints.lbu = np.array([u_min, -r_max])
    ocp.constraints.ubu = np.array([u_max, r_max])

    du_step = du_max * dt
    dr_step = dr_max * dt
    ocp.constraints.lh = np.array([-du_step, -dr_step])
    ocp.constraints.uh = np.array([du_step, dr_step])
    ocp.constraints.lh_0 = np.array([-du_step, -dr_step])
    ocp.constraints.uh_0 = np.array([du_step, dr_step])
    ocp.constraints.constr_type = "BGH"

    ocp.solver_options.nlp_solver_type = "SQP"
    ocp.solver_options.globalization = "MERIT_BACKTRACKING"
    ocp.solver_options.integrator_type = "DISCRETE"
    ocp.solver_options.qp_solver = "FULL_CONDENSING_HPIPM"
    ocp.solver_options.hessian_approx = "GAUSS_NEWTON"
    ocp.solver_options.nlp_solver_max_iter = 50
    ocp.solver_options.qp_solver_iter_max = 200
    ocp.solver_options.nlp_solver_tol_stat = 1e-4
    ocp.solver_options.nlp_solver_tol_eq = 1e-4
    ocp.solver_options.nlp_solver_tol_ineq = 1e-4
    ocp.solver_options.nlp_solver_tol_comp = 1e-4
    ocp.solver_options.timeout_max_time = 0.12
    ocp.solver_options.print_level = 0
    # 取消 acados 默认的阶段 dt 缩放, 使 0.5*y'W*y 与原目标逐点一致。
    ocp.solver_options.cost_scaling = np.ones(N + 1)
    return ocp


def verify_kinematic_discretization(ocp, dt):
    """用实际 disc_dyn_expr 对独立 NumPy RK4 做一次生成语义验证。

    检查项:
      1. 物理 5 维与 NumPy 四子步 RK4 的绝对误差 <= 1e-10;
      2. 增广末两维 == 本阶段控制 (精确赋值, 不是积分结果);
      3. 两组不同 tau 都必须成立 (证明 tau 确实来自 p_global 而非烘焙常数)。
    """
    import casadi as ca

    model = ocp.model
    disc = ca.Function("disc_check", [model.x, model.u, model.p_global],
                       [model.disc_dyn_expr])

    x0 = np.array([1.0, -2.0, np.pi - 0.01, 0.7, 0.2])
    control = np.array([1.2, -0.3])
    cases = ((0.8, 1.78), (0.4, 1.0))
    worst = 0.0
    for tau_u, tau_r in cases:
        pg = np.zeros(N_P_GLOBAL_KIN)
        pg[PG_K_TAU_U] = tau_u
        pg[PG_K_TAU_R] = tau_r
        x_aug = np.concatenate([x0, [0.0, 0.0]])
        # 覆盖 p_global 的权重位为生成占位值, 与 OCP 一致 (不影响动力学)
        pg[PG_K_QX] = DEFAULT_KINEMATIC["Qx"]
        pg[PG_K_QY] = DEFAULT_KINEMATIC["Qy"]
        pg[PG_K_QPSI] = DEFAULT_KINEMATIC["Qpsi"]
        pg[PG_K_RU] = DEFAULT_KINEMATIC["Ru"]
        pg[PG_K_RR] = DEFAULT_KINEMATIC["Rr"]
        pg[PG_K_QF] = DEFAULT_KINEMATIC["Qf_scale"]
        evaluated = np.array(disc(x_aug, control, pg)).reshape(-1)
        reference = num_rk4_kinematic(x0, control, tau_u, tau_r, dt, 4)
        error = float(np.max(np.abs(evaluated[:5] - reference)))
        if error > 1e-10:
            sys.exit(f"[错误] 运动学离散动力学与 NumPy RK4 不一致 "
                     f"(tau=({tau_u},{tau_r}) 误差 {error:.3e} > 1e-10)")
        augment_error = float(np.max(np.abs(evaluated[5:] - control)))
        if augment_error > 0.0:
            sys.exit(f"[错误] 增广状态末两维未精确赋值为控制 "
                     f"(误差 {augment_error:.3e})")
        worst = max(worst, error)
    print(f"[codegen] 运动学离散动力学校验通过 (2 组 tau, 最大误差 {worst:.3e})")


def prune(out_dir, json_name):
    """按生成 JSON 的引用清单裁成 CMake 需要的最小文件集。"""
    json_path = os.path.join(out_dir, json_name)
    with open(json_path, "r", encoding="utf-8") as f:
        ocp_description = json.load(f)
    generated_sources = {
        path.removeprefix("./")
        for key in ("external_function_files_model", "external_function_files_ocp")
        for path in ocp_description[key]
    }
    top_files = {json_name}
    keep_subdirs = set()
    for relative in generated_sources:
        directory = os.path.dirname(relative)
        if directory:
            keep_subdirs.add(directory)
        else:
            top_files.add(relative)
    # 求解器 C/H 与 p_global precompute 由生成器直接写出, 未必出现在引用清单中。
    # main_* / acados_sim_solver_* / Makefile / *.o 一律不保留: CMake 只要
    # 求解器与外部函数, 带 main 的文件会与 executables 冲突。
    for entry in os.listdir(out_dir):
        path = os.path.join(out_dir, entry)
        if os.path.isdir(path):
            continue
        if entry.startswith("main_") or entry.startswith("acados_sim_solver"):
            continue
        if entry.endswith((".c", ".h")):
            top_files.add(entry)

    for entry in os.listdir(out_dir):
        path = os.path.join(out_dir, entry)
        if os.path.isdir(path):
            if entry not in keep_subdirs:
                shutil.rmtree(path)
            else:
                # 保留当前 JSON 实际引用的 C 源码和对应汇总头；旧 OCP 留下的
                # 同名目录文件必须删除，否则 CMake GLOB 会继续把它们编入库。
                for filename in os.listdir(path):
                    relative_path = os.path.relpath(
                        os.path.join(path, filename), out_dir)
                    if not (filename.endswith(".h") or
                            relative_path in generated_sources):
                        os.remove(os.path.join(path, filename))
        else:
            if entry not in top_files:
                os.remove(path)


def check_generated_dims(out_dir, json_name, expected):
    """核对生成 JSON 的维度与求解器配置, 防止模板默认值悄悄改变。"""
    with open(os.path.join(out_dir, json_name), "r", encoding="utf-8") as f:
        payload = json.load(f)
    dims = payload["dims"]
    failures = []
    for key, value in expected["dims"].items():
        if dims.get(key) != value:
            failures.append(f"dims.{key}={dims.get(key)!r} != {value!r}")
    options = payload["solver_options"]
    for key, value in expected["solver_options"].items():
        if key == "cost_scaling":
            if [float(item) for item in options.get(key, [])] != value:
                failures.append(f"solver_options.{key}={options.get(key)!r} != {value!r}")
            continue
        if options.get(key) != value:
            failures.append(f"solver_options.{key}={options.get(key)!r} != {value!r}")
    if failures:
        sys.exit("[错误] 生成码与契约不一致:\n  " + "\n  ".join(failures))
    print("[codegen] JSON 维度与求解器配置符合契约")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    generated_root = os.path.normpath(os.path.join(here, "..", "acados_generated"))

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, choices=sorted(MODELS),
                    help="kinematic (方案 A) 或 dynamic (方案 B)")
    ap.add_argument("-o", "--output-dir", default=None,
                    help="生成目录 (默认 ../acados_generated/<model>)")
    ap.add_argument("--horizon", type=int, default=20,
                    help="预测步数 N_horizon (默认 20; 改动须同步 C++ 侧配置)")
    ap.add_argument("--dt", type=float, default=0.2,
                    help="步长 dt 秒 (默认 0.2; 改动须重新 codegen 并同步 yaml)")
    # dynamic 专用 (方案 B 原默认值)
    ap.add_argument("--t-max", type=float, default=40.0,
                    help="[dynamic] 推力上界 (N)")
    ap.add_argument("--t-min", type=float, default=-20.0,
                    help="[dynamic] 推力下界 (N)")
    ap.add_argument("--dt-max", type=float, default=30.0,
                    help="[dynamic] 推力变化率上限 (N/s)")
    # kinematic 专用 (与 mpc_params_A.yaml 同值)
    ap.add_argument("--u-max", type=float, default=3.3,
                    help="[kinematic] 纵荡速度上界 (m/s)")
    ap.add_argument("--u-min", type=float, default=0.0,
                    help="[kinematic] 纵荡速度下界 (m/s)")
    ap.add_argument("--r-max", type=float, default=1.25,
                    help="[kinematic] 艏摇角速度上界 (rad/s)")
    ap.add_argument("--du-max", type=float, default=1.3,
                    help="[kinematic] 纵荡加速度上界 (m/s^2)")
    ap.add_argument("--dr-max", type=float, default=1.25,
                    help="[kinematic] 艏摇角加速度上界 (rad/s^2)")
    ap.add_argument("--keep-build-artifacts", action="store_true",
                    help="保留 main_*/sim/Makefile/.o (调试用, CMake 不需要)")
    args = ap.parse_args()

    model_key = args.model
    meta = MODELS[model_key]
    out_dir = os.path.abspath(
        args.output_dir if args.output_dir else os.path.join(generated_root, model_key))

    try:
        from acados_template import AcadosOcpSolver  # noqa: F401
    except Exception as e:  # pragma: no cover - 环境问题
        sys.exit(f"[错误] 需要 acados_template ({type(e).__name__}: {e})。"
                 " 设置 ACADOS_SOURCE_DIR 并把 $ACADOS_SOURCE_DIR/interfaces/"
                 "acados_template 加入 PYTHONPATH。")

    os.makedirs(out_dir, exist_ok=True)
    print(f"[codegen] model={model_key} 生成到 {out_dir} "
          f"(N={args.horizon}, dt={args.dt})")

    if model_key == "kinematic":
        ocp = build_kinematic_ocp(args.horizon, args.dt, args.u_max, args.u_min,
                                  args.r_max, args.du_max, args.dr_max)
        expected = {
            "dims": {
                "N": args.horizon, "nx": 7, "nu": 2, "np": 3, "np_global": 8,
                "ny_0": 6, "ny": 6, "ny_e": 4, "nh": 2, "nh_0": 2, "nbx_0": 7,
            },
            "solver_options": {
                "nlp_solver_type": "SQP",
                "globalization": "MERIT_BACKTRACKING",
                "integrator_type": "DISCRETE",
                "qp_solver": "FULL_CONDENSING_HPIPM",
                "hessian_approx": "GAUSS_NEWTON",
                "nlp_solver_max_iter": 50,
                "qp_solver_iter_max": 200,
                "nlp_solver_tol_stat": 1e-4,
                "nlp_solver_tol_eq": 1e-4,
                "nlp_solver_tol_ineq": 1e-4,
                "nlp_solver_tol_comp": 1e-4,
                "timeout_max_time": 0.12,
                "print_level": 0,
                "tf": args.horizon * args.dt,
                "cost_scaling": [1.0] * (args.horizon + 1),
            },
        }
    else:
        ocp = build_dynamic_ocp(args.horizon, args.dt, args.t_max, args.t_min,
                                args.dt_max)
        expected = {
            "dims": {
                "N": args.horizon, "nx": 8, "nu": 2, "np": 12, "np_global": 30,
                "ny_0": 13, "ny": 13, "ny_e": 7, "nh": 2, "nh_0": 2, "nbx_0": 8,
            },
            "solver_options": {
                "nlp_solver_type": "SQP_RTI",
                "integrator_type": "DISCRETE",
                "qp_solver": "FULL_CONDENSING_HPIPM",
                "hessian_approx": "GAUSS_NEWTON",
                "nlp_solver_max_iter": 50,
                "qp_solver_iter_max": 200,
                "tf": args.horizon * args.dt,
            },
        }

    ocp.code_gen_opts.code_export_directory = out_dir
    json_file = os.path.join(out_dir, meta["json_name"])

    if model_key == "kinematic":
        verify_kinematic_discretization(ocp, args.dt)

    # generate=True 写 C 源码; build=False 不编译 .so (由 usv_acados CMake 编译)
    AcadosOcpSolver(ocp, json_file=json_file, generate=True, build=False)

    if not args.keep_build_artifacts:
        prune(out_dir, meta["json_name"])
        print("[codegen] 已裁剪为 CMake 最小文件集")

    # 增广状态锚点偏移必须等于物理维 (C++ 契约)
    check_generated_dims(out_dir, meta["json_name"], expected)

    n_c = sum(len([f for f in files if f.endswith(".c")])
              for _, _, files in os.walk(out_dir))
    print(f"[codegen] 完成, {n_c} 个 .c 源文件。"
          " 请 colcon build --packages-select usv_acados")


if __name__ == "__main__":
    main()
