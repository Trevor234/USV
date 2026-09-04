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
 * @file casadi_kinematic_backend.cpp
 * @brief CasADi Opti+IPOPT 运动学 MPC 后端实现。
 *
 * 对应 Python 版本: usv_mpc/mpc_kinematic.py (KinematicMPC)
 *
 * 用 CasADi C++ MX 符号构建运动学 ODE (3 维), RK4 离散化, Opti+IPOPT 求解。
 * 结构与方案 B 的 casadi_backend.cpp 同构, 逐方法对照移植 (见实现注释)。
 */

#include "usv_mpc_cpp/casadi_kinematic_backend.hpp"

#include <chrono>
#include <cmath>
#include <vector>

namespace usv_mpc {

namespace {

using namespace casadi;

/// 符号运动学 ODE 右端 rhs = [u*cos(psi), u*sin(psi), r] (3 维)。
/// 纯函数 (无物理参数), 对应 Python usv_model_kinematic.py 的 rhs。
/// 对照 B 的 fossen_ode: 无 M/C/D 矩阵, 无 HydroParams 入参, 仅 3 行。
MX kinematic_ode(const MX& s, const MX& u_in) {
  MX psi = s(2);
  MX u = u_in(0);   // surge
  MX r = u_in(1);   // yaw rate
  return MX::vertcat({
    u * cos(psi),
    u * sin(psi),
    r
  });
}

}  // namespace

CasadiKinematicBackend::CasadiKinematicBackend(const KinematicMpcParams& params)
    : params_(params) {
  const int N = params_.N;
  // 维度常量 (便于核对, 避免魔法数字; 对照 B 的 6 维, 此处全 3 维)
  constexpr int NX = 3;  // [x, y, psi]
  constexpr int NU = 2;  // [u, r]

  // ── RK4 离散动力学函数 f_rk4(state[3], control[2]) -> next[3] ──
  // 对照 B: fossen_ode -> kinematic_ode; MX::sym("state",6) -> (state,3)
  MX state_sym = MX::sym("state", NX);
  MX control_sym = MX::sym("control", NU);
  MX rhs = kinematic_ode(state_sym, control_sym);
  Function f_cont("f_kin", {state_sym, control_sym}, {rhs});

  MX X0 = MX::sym("X0", NX);
  MX U = MX::sym("U", NU);
  MX X = X0;
  double h = params_.dt / 4.0;  // 4 子步 (对齐 Python rk4_substeps=4)
  for (int i = 0; i < 4; ++i) {
    MX k1 = f_cont(std::vector<MX>{X, U}).at(0);
    MX k2 = f_cont(std::vector<MX>{X + h / 2.0 * k1, U}).at(0);
    MX k3 = f_cont(std::vector<MX>{X + h / 2.0 * k2, U}).at(0);
    MX k4 = f_cont(std::vector<MX>{X + h * k3, U}).at(0);
    X = X + h / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4);
  }
  f_rk4_ = Function("f_rk4_kin", {X0, U}, {X});

  // ── Opti 问题 ──
  // 对照 B: variable(6,N+1) -> variable(3,N+1); parameter(6,*) -> parameter(3,*)
  X_ = opti_.variable(NX, N + 1);
  U_ = opti_.variable(NU, N);
  p_x0_ = opti_.parameter(NX, 1);
  p_ref_ = opti_.parameter(NX, N + 1);
  p_u_prev_ = opti_.parameter(NU, 1);

  // ── 代价函数 (对照 Python mpc_kinematic.py) ──
  // 位置误差二次 (2维子块 x,y) + 航向 2*Q_psi*(1-cos(dψ)) + 控制能量 ||u||_R^2
  // ★ 与 B 的关键差异: 无 Rd 控制率代价项 (B 有 rd0*du0*du0 + rd1*du1*du1)
  double qx = params_.Q_diag(0), qy = params_.Q_diag(1), q_psi = params_.Q_diag(2);
  double ru = params_.R_diag(0), rr = params_.R_diag(1);
  double qf = params_.Qf_scale;

  MX cost = 0;
  for (int k = 0; k < N; ++k) {
    MX ex = X_(0, k) - p_ref_(0, k);
    MX ey = X_(1, k) - p_ref_(1, k);
    cost += qx * ex * ex + qy * ey * ey;
    MX e_psi = X_(2, k) - p_ref_(2, k);
    cost += 2.0 * q_psi * (1.0 - cos(e_psi));
    cost += ru * U_(0, k) * U_(0, k) + rr * U_(1, k) * U_(1, k);
    // ★ 无 du/dr 的 Rd 二次项 (B 有)
  }
  // 终端代价
  MX ex_f = X_(0, N) - p_ref_(0, N);
  MX ey_f = X_(1, N) - p_ref_(1, N);
  cost += qf * (qx * ex_f * ex_f + qy * ey_f * ey_f);
  MX e_psi_f = X_(2, N) - p_ref_(2, N);
  cost += 2.0 * qf * q_psi * (1.0 - cos(e_psi_f));
  opti_.minimize(cost);

  // ── 动力学约束 (对照 B: Slice(0,6) -> Slice(0,3)) ──
  opti_.subject_to(X_(Slice(0, NX), 0) == p_x0_);
  for (int k = 0; k < N; ++k) {
    MX x_next = f_rk4_(std::vector<MX>{X_(Slice(0, NX), k), U_(Slice(0, NU), k)}).at(0);
    opti_.subject_to(X_(Slice(0, NX), k + 1) == x_next);
  }

  // ── 控制边界约束 (★ 与 B 关键差异: 两通道不同边界) ──
  // B: 两通道同边界 bounded(T_min, U_(i,k), T_max) (对称)
  // A: u 用 [u_min, u_max] (非对称, u_min 可为 0); r 用 [-r_max, r_max] (对称)
  for (int k = 0; k < N; ++k) {
    opti_.subject_to(opti_.bounded(params_.u_min, U_(0, k), params_.u_max));
    opti_.subject_to(opti_.bounded(-params_.r_max, U_(1, k), params_.r_max));
  }

  // ── 速率约束 (★ 与 B 关键差异: 两通道不同速率) ──
  // B: dT_step = dT_max*dt, 两通道同
  // A: du_step = du_max*dt (u 通道), dr_step = dr_max*dt (r 通道)
  double du_step = params_.du_max * params_.dt;
  double dr_step = params_.dr_max * params_.dt;
  opti_.subject_to(opti_.bounded(-du_step, U_(0, 0) - p_u_prev_(0), du_step));
  opti_.subject_to(opti_.bounded(-dr_step, U_(1, 0) - p_u_prev_(1), dr_step));
  for (int k = 1; k < N; ++k) {
    opti_.subject_to(opti_.bounded(-du_step, U_(0, k) - U_(0, k - 1), du_step));
    opti_.subject_to(opti_.bounded(-dr_step, U_(1, k) - U_(1, k - 1), dr_step));
  }

  // ── IPOPT 求解器选项 (对齐 Python mpc_kinematic.py: max_iter=200, acceptable_iter=5) ──
  // B 用 max_iter=300, acceptable_iter=10
  opti_.solver("ipopt",
               {{"print_time", 0}},
               {{"print_level", 0}, {"max_iter", 200},
                {"warm_start_init_point", "yes"},
                {"tol", 1e-4}, {"acceptable_tol", 1e-3},
                {"acceptable_iter", 5}});

  X_warm_ = Eigen::MatrixXd::Zero(NX, N + 1);  // 3 x (N+1) (B 是 6)
  U_warm_ = Eigen::MatrixXd::Zero(NU, N);      // 2 x N (同 B)
}

std::pair<Eigen::Vector2d, SolveInfo>
CasadiKinematicBackend::solve(const Eigen::Vector3d& current_state,
                              const Eigen::MatrixXd& reference) {
  SolveInfo info;
  info.backend = "casadi";
  const int N = params_.N;
  constexpr int NX = 3;
  constexpr int NU = 2;

  // 参数赋值 (列主序 vector -> DM, 用 Sparsity::dense 指定形状)
  // 对照 B: +6 -> +3; dense(6,1) -> dense(3,1)
  std::vector<double> x0v(current_state.data(), current_state.data() + NX);
  opti_.set_value(p_x0_, DM(Sparsity::dense(NX, 1), x0v));

  std::vector<double> refv(NX * (N + 1));
  for (int c = 0; c <= N; ++c)
    for (int r = 0; r < NX; ++r) refv[c * NX + r] = reference(r, c);
  opti_.set_value(p_ref_, DM(Sparsity::dense(NX, N + 1), refv));

  std::vector<double> upv(u_prev_.data(), u_prev_.data() + NU);
  opti_.set_value(p_u_prev_, DM(Sparsity::dense(NU, 1), upv));

  // 热启动初值
  std::vector<double> xw(NX * (N + 1));
  if (has_warm_) {
    for (int c = 0; c <= N; ++c)
      for (int r = 0; r < NX; ++r) xw[c * NX + r] = X_warm_(r, c);
  } else {
    for (int c = 0; c <= N; ++c)
      for (int r = 0; r < NX; ++r) xw[c * NX + r] = current_state(r);
  }
  opti_.set_initial(X_, DM(Sparsity::dense(NX, N + 1), xw));
  opti_.set_initial(U_, DM(Sparsity::dense(NU, N), std::vector<double>(NU * N, 0.0)));

  auto t0 = std::chrono::steady_clock::now();
  try {
    OptiSol sol = opti_.solve();
    auto t1 = std::chrono::steady_clock::now();
    info.solve_time_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

    DM X_dm = sol.value(X_);
    DM U_dm = sol.value(U_);
    std::vector<double> u0v = U_dm(Slice(0, NU), 0).nonzeros();
    Eigen::Vector2d u_opt(u0v[0], u0v[1]);

    std::vector<double> x_all = X_dm.nonzeros();
    std::vector<double> u_all = U_dm.nonzeros();
    info.X_pred = Eigen::MatrixXd::Zero(NX, N + 1);
    info.U_pred = Eigen::MatrixXd::Zero(NU, N);
    for (int c = 0; c <= N; ++c)
      for (int r = 0; r < NX; ++r) info.X_pred(r, c) = x_all[c * NX + r];
    for (int c = 0; c < N; ++c)
      for (int r = 0; r < NU; ++r) info.U_pred(r, c) = u_all[c * NU + r];

    // 热启动滚动 (平移: 丢弃首列, 末列复制; 与 B 完全相同逻辑)
    X_warm_.leftCols(N) = info.X_pred.rightCols(N);
    X_warm_.col(N) = info.X_pred.col(N);
    U_warm_.leftCols(N - 1) = info.U_pred.rightCols(N - 1);
    U_warm_.col(N - 1) = info.U_pred.col(N - 1);
    u_prev_ = u_opt;
    has_warm_ = true;

    info.success = true;
    return {u_opt, info};
  } catch (const std::exception& e) {
    // 失败: 返回上次控制, 不更新热启动 (对齐 B, 防止发散)
    auto t1 = std::chrono::steady_clock::now();
    info.solve_time_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    info.success = false;
    info.error = e.what();
    return {u_prev_, info};
  }
}

void CasadiKinematicBackend::reset_warmstart() {
  has_warm_ = false;
  X_warm_.setZero();
  U_warm_.setZero();
  u_prev_.setZero();
}

Eigen::MatrixXd CasadiKinematicBackend::get_predicted_trajectory() const {
  if (!has_warm_) return Eigen::MatrixXd();
  return X_warm_;
}

}  // namespace usv_mpc
