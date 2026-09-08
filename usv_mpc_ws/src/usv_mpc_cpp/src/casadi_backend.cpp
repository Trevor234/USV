// Copyright 2026 USV Developer
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
// THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.


/**
 * @file casadi_backend.cpp
 * @brief CasADi Opti+IPOPT fallback 后端实现。
 *
 * 对应 Python 版本: usv_mpc/mpc_dynamic_legacy.py
 *
 * 用 CasADi C++ MX 符号构建 Fossen ODE (与 Python continuous_ode_expr 等价),
 * RK4 离散化, Opti+IPOPT 求解 NMPC。
 */

#include "usv_mpc_cpp/casadi_backend.hpp"
#include "usv_mpc_cpp/utils.hpp"

#include <chrono>
#include <cstdio>
#include <cmath>

namespace usv_mpc {

namespace {

using namespace casadi;

/// 符号 Fossen ODE 右端 rhs=[eta_dot; nu_dot] (6 维)。
/// 与 Python continuous_ode_expr 等价 (数值参数固化)。
MX fossen_ode(const MX& s, const MX& u_in, const HydroParams& p) {
  MX psi_s = s(2), u_s = s(3), v_s = s(4), r_s = s(5);
  MX TL = u_in(0), TR = u_in(1);

  // M (3x3) 及其解析逆 (结构固定)
  double m11 = p.mass - p.Xu_dot;
  double m22 = p.mass - p.Yv_dot;
  double m23 = p.mass * p.xg - p.Yr_dot;
  double m32 = p.mass * p.xg - p.Nv_dot;
  double m33 = p.Iz - p.Nr_dot;
  double det = m11 * (m22 * m33 - m23 * m32);
  double i00 = (m22 * m33 - m23 * m32) / det;
  double i11 = (m11 * m33) / det;
  double i12 = (-m11 * m23) / det;
  double i21 = (-m11 * m32) / det;
  double i22 = (m11 * m22) / det;

  // C(nu): c13=-m22*v-m23*r, c23=m11*u
  MX c13 = -m22 * v_s - m23 * r_s;
  MX c23 = m11 * u_s;
  // C*nu = [c13*r ; c23*r ; -c13*u - c23*v]
  MX Cnu0 = c13 * r_s;
  MX Cnu1 = c23 * r_s;
  MX Cnu2 = -c13 * u_s - c23 * v_s;

  // D(nu): 线性 + 二次 (fabs)
  MX Dnu0 = (-p.Xu - p.Xuu * fabs(u_s)) * u_s;
  MX Dnu1 = (-p.Yv - p.Yvv * fabs(v_s)) * v_s + (-p.Yr - p.Yrr * fabs(r_s)) * r_s;
  MX Dnu2 = (-p.Nv - p.Nvv * fabs(v_s)) * v_s + (-p.Nr - p.Nrr * fabs(r_s)) * r_s;

  // tau = [TL+TR, 0, d*(TR-TL)]
  MX tau0 = TL + TR;
  MX tau2 = p.d_thruster * (TR - TL);

  // nu_dot = M^{-1} * (tau - C*nu - D*nu)
  MX rhs0 = (tau0 - Cnu0 - Dnu0) * i00;
  MX rhs1 = (0.0 - Cnu1 - Dnu1) * i11 + (tau2 - Cnu2 - Dnu2) * i12;
  MX rhs2 = (0.0 - Cnu1 - Dnu1) * i21 + (tau2 - Cnu2 - Dnu2) * i22;

  // eta_dot = J(psi) * nu
  MX cos_psi = cos(psi_s);
  MX sin_psi = sin(psi_s);
  MX etax = cos_psi * u_s - sin_psi * v_s;
  MX etay = sin_psi * u_s + cos_psi * v_s;
  MX etapsi = r_s;

  return MX::vertcat({etax, etay, etapsi, rhs0, rhs1, rhs2});
}

/// 取行子集 (idx_xy_uvr = [0,1,3,4,5]) 的代价和。
MX quad_cost_xy_uvr(const MX& Xk, const MX& ref_k,
                    double q0, double q1, double q3, double q4, double q5) {
  MX e0 = Xk(0) - ref_k(0);
  MX e1 = Xk(1) - ref_k(1);
  MX e3 = Xk(3) - ref_k(3);
  MX e4 = Xk(4) - ref_k(4);
  MX e5 = Xk(5) - ref_k(5);
  return q0 * e0 * e0 + q1 * e1 * e1 + q3 * e3 * e3 + q4 * e4 * e4 + q5 * e5 * e5;
}

}  // namespace

CasadiBackend::CasadiBackend(const MpcParams& params) : params_(params) {
  const int N = params_.N;

  // RK4 离散动力学函数 f_rk4(state[6], control[2]) -> next[6]
  MX state_sym = MX::sym("state", 6);
  MX control_sym = MX::sym("control", 2);
  MX rhs = fossen_ode(state_sym, control_sym, params_.hydro);
  Function f_cont("f_dyn", {state_sym, control_sym}, {rhs});

  MX X0 = MX::sym("X0", 6);
  MX U = MX::sym("U", 2);
  MX X = X0;
  double h = params_.dt / 4.0;
  for (int i = 0; i < 4; ++i) {
    MX k1 = f_cont(std::vector<MX>{X, U}).at(0);
    MX k2 = f_cont(std::vector<MX>{X + h / 2.0 * k1, U}).at(0);
    MX k3 = f_cont(std::vector{X + h / 2.0 * k2, U}).at(0);
    MX k4 = f_cont(std::vector{X + h * k3, U}).at(0);
    X = X + h / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4);
  }
  f_rk4_ = Function("f_rk4_dyn", {X0, U}, {X});

  // Opti 问题
  X_ = opti_.variable(6, N + 1);
  U_ = opti_.variable(2, N);
  p_x0_ = opti_.parameter(6, 1);
  p_ref_ = opti_.parameter(6, N + 1);
  p_u_prev_ = opti_.parameter(2, 1);

  double q0 = params_.Q_diag(0), q1 = params_.Q_diag(1), q_psi = params_.Q_diag(2);
  double q3 = params_.Q_diag(3), q4 = params_.Q_diag(4), q5 = params_.Q_diag(5);
  double r0 = params_.R_diag(0), r1 = params_.R_diag(1);
  double rd0 = params_.Rd_diag(0), rd1 = params_.Rd_diag(1);
  double qf = params_.Qf_scale;

  MX cost = 0;
  for (int k = 0; k < N; ++k) {
    MX ref_k = p_ref_(Slice(0, 6), k);
    cost += quad_cost_xy_uvr(X_(Slice(0, 6), k), ref_k, q0, q1, q3, q4, q5);
    MX e_psi = X_(2, k) - p_ref_(2, k);
    cost += 2.0 * q_psi * (1.0 - cos(e_psi));
    cost += r0 * U_(0, k) * U_(0, k) + r1 * U_(1, k) * U_(1, k);
    MX du0 = (k == 0) ? (U_(0, k) - p_u_prev_(0)) : (U_(0, k) - U_(0, k - 1));
    MX du1 = (k == 0) ? (U_(1, k) - p_u_prev_(1)) : (U_(1, k) - U_(1, k - 1));
    cost += rd0 * du0 * du0 + rd1 * du1 * du1;
  }
  // 终端代价
  MX ref_N = p_ref_(Slice(0, 6), N);
  cost += qf * quad_cost_xy_uvr(X_(Slice(0, 6), N), ref_N, q0, q1, q3, q4, q5);
  MX e_psi_f = X_(2, N) - p_ref_(2, N);
  cost += 2.0 * qf * q_psi * (1.0 - cos(e_psi_f));
  opti_.minimize(cost);

  // 动力学约束
  opti_.subject_to(X_(Slice(0, 6), 0) == p_x0_);
  for (int k = 0; k < N; ++k) {
    MX x_next = f_rk4_(std::vector<MX>{X_(Slice(0, 6), k), U_(Slice(0, 2), k)}).at(0);
    opti_.subject_to(X_(Slice(0, 6), k + 1) == x_next);
  }

  // 推力边界
  for (int k = 0; k < N; ++k) {
    opti_.subject_to(opti_.bounded(params_.T_min, U_(0, k), params_.T_max));
    opti_.subject_to(opti_.bounded(params_.T_min, U_(1, k), params_.T_max));
  }

  // 变化率约束
  double dT_step = params_.dT_max * params_.dt;
  opti_.subject_to(opti_.bounded(-dT_step, U_(0, 0) - p_u_prev_(0), dT_step));
  opti_.subject_to(opti_.bounded(-dT_step, U_(1, 0) - p_u_prev_(1), dT_step));
  for (int k = 1; k < N; ++k) {
    opti_.subject_to(opti_.bounded(-dT_step, U_(0, k) - U_(0, k - 1), dT_step));
    opti_.subject_to(opti_.bounded(-dT_step, U_(1, k) - U_(1, k - 1), dT_step));
  }

  opti_.solver("ipopt",
               {{"print_time", 0}},
               {{"print_level", 0}, {"max_iter", 300},
                {"warm_start_init_point", "yes"},
                {"tol", 1e-4}, {"acceptable_tol", 1e-3},
                {"acceptable_iter", 10}});

  X_warm_ = Eigen::MatrixXd::Zero(6, N + 1);
  U_warm_ = Eigen::MatrixXd::Zero(2, N);
}

std::pair<Eigen::Vector2d, SolveInfo>
CasadiBackend::solve(const Vector6d& current_state, const Eigen::MatrixXd& reference) {
  SolveInfo info;
  snprintf(info.backend, sizeof(info.backend), "casadi");
  const int N = params_.N;

  // 参数赋值 (列主序 vector -> DM, 用 Sparsity::dense 指定形状)
  std::vector<double> x0v(current_state.data(), current_state.data() + 6);
  opti_.set_value(p_x0_, DM(Sparsity::dense(6, 1), x0v));

  // 参考轨迹逐阶段解包使航向角连续展开
  std::vector<double> refv(6 * (N + 1));
  double ref_psi_prev = current_state(2);
  for (int c = 0; c <= N; ++c) {
    double r_psi = ref_psi_prev + normalize_angle(reference(2, c) - ref_psi_prev);
    ref_psi_prev = r_psi;
    for (int r = 0; r < 6; ++r) {
      refv[c * 6 + r] = (r == 2) ? r_psi : reference(r, c);
    }
  }
  opti_.set_value(p_ref_, DM(Sparsity::dense(6, N + 1), refv));

  std::vector<double> upv(u_prev_.data(), u_prev_.data() + 2);
  opti_.set_value(p_u_prev_, DM(Sparsity::dense(2, 1), upv));

  // 热启动航向角解卷绕：消除 ±pi 边界处的 2pi 相位阶跃撕裂
  if (has_warm_) {
    double shift = std::round((current_state(2) - X_warm_(2, 0)) / (2.0 * M_PI)) * (2.0 * M_PI);
    if (std::abs(shift) > 1e-3) {
      X_warm_.row(2).array() += shift;
    }
  }

  // 热启动初值
  std::vector<double> xw(6 * (N + 1));
  if (has_warm_) {
    for (int c = 0; c <= N; ++c)
      for (int r = 0; r < 6; ++r) xw[c * 6 + r] = X_warm_(r, c);
  } else {
    for (int c = 0; c <= N; ++c)
      for (int r = 0; r < 6; ++r) xw[c * 6 + r] = current_state(r);
  }
  opti_.set_initial(X_, DM(Sparsity::dense(6, N + 1), xw));
  opti_.set_initial(U_, DM(Sparsity::dense(2, N), std::vector<double>(2 * N, 0.0)));

  auto t0 = std::chrono::steady_clock::now();
  try {
    OptiSol sol = opti_.solve();
    auto t1 = std::chrono::steady_clock::now();
    info.solve_time_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

    DM X_dm = sol.value(X_);
    DM U_dm = sol.value(U_);
    std::vector<double> u0v = U_dm(Slice(0, 2), 0).nonzeros();
    Eigen::Vector2d u_opt(u0v[0], u0v[1]);

    std::vector<double> x_all = X_dm.nonzeros();
    std::vector<double> u_all = U_dm.nonzeros();
    info.X_pred = Eigen::MatrixXd::Zero(6, N + 1);
    info.U_pred = Eigen::MatrixXd::Zero(2, N);
    for (int c = 0; c <= N; ++c)
      for (int r = 0; r < 6; ++r) info.X_pred(r, c) = x_all[c * 6 + r];
    for (int c = 0; c < N; ++c)
      for (int r = 0; r < 2; ++r) info.U_pred(r, c) = u_all[c * 2 + r];

    // NaN/Inf 门禁: IPOPT 收敛判据不保证有限值,在写入热启动前拦截,
    // 避免 NaN 经 u_prev_/X_warm_/U_warm_ 扩散到后续拍。
    if (!u_opt.allFinite() || !info.X_pred.allFinite() ||
        !info.U_pred.allFinite()) {
      info.success = false;
      snprintf(info.error, sizeof(info.error), "non_finite_solution");
      return {u_prev_, info};
    }

    X_warm_.leftCols(N) = info.X_pred.rightCols(N);
    X_warm_.col(N) = info.X_pred.col(N);
    U_warm_.leftCols(N - 1) = info.U_pred.rightCols(N - 1);
    U_warm_.col(N - 1) = info.U_pred.col(N - 1);
    u_prev_ = u_opt;
    has_warm_ = true;

    info.success = true;
    return {u_opt, info};
  } catch (const std::exception& e) {
    auto t1 = std::chrono::steady_clock::now();
    info.solve_time_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    info.success = false;
    snprintf(info.error, sizeof(info.error), "%s", e.what());
    return {u_prev_, info};
  }
}

void CasadiBackend::reset_warmstart() {
  has_warm_ = false;
  X_warm_.setZero();
  U_warm_.setZero();
  u_prev_.setZero();
}

Eigen::MatrixXd CasadiBackend::get_predicted_trajectory() const {
  if (!has_warm_) return Eigen::MatrixXd();
  return X_warm_;
}

}  // namespace usv_mpc
