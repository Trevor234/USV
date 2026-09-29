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

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <vector>

#include "usv_mpc_cpp/casadi_kinematic_backend.hpp"

namespace usv_mpc
{

namespace
{

using casadi::DM;
using casadi::Function;
using casadi::MX;
using casadi::Opti;
using casadi::OptiAdvanced;
using casadi::OptiSol;
using casadi::SX;
using casadi::Slice;
using casadi::Sparsity;

/// 符号运动学 ODE (5 状态, 含执行器一阶滞后):
///   s = [x, y, psi, u, r],  u_in = [u_cmd, r_cmd]
///   dx = u*cos(psi); dy = u*sin(psi); dpsi = r
///   du = (u_cmd - u)/tau_u;  dr = (r_cmd - r)/tau_r
MX kinematic_ode(const MX & s, const MX & u_in, double tau_u, double tau_r)
{
  MX psi = s(2);
  MX u = s(3);
  MX r = s(4);
  MX uc = u_in(0);
  MX rc = u_in(1);
  return MX::vertcat({
        u * cos(psi),
        u * sin(psi),
        r,
        (uc - u) / tau_u,
        (rc - r) / tau_r
  });
}

}  // namespace

CasadiKinematicBackend::CasadiKinematicBackend(const KinematicMpcParams & params)
: params_(params)
{
  const int N = params_.N;
  // 维度常量 (便于核对, 避免魔法数字)
  constexpr int NX = 5;  // [x, y, psi, u, r]
  constexpr int NU = 2;  // [u_cmd, r_cmd]

  // ── RK4 离散动力学函数 f_rk4(state[5], control[2]) -> next[5] ──
  MX state_sym = MX::sym("state", NX);
  MX control_sym = MX::sym("control", NU);
  MX rhs = kinematic_ode(state_sym, control_sym,
                         params_.tau_u, params_.tau_r);
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
  p_x0_ = opti_.parameter(NX, 1);      // [x, y, psi, u, r]
  p_ref_ = opti_.parameter(3, N + 1);  // 参考只含 x,y,psi (代价引用)
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

  // ── 动力学约束 (5 状态) ──
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

  // ── IPOPT 求解器选项 ──
  // expand: MX→SX 展开, 函数求值更快 (Pi5 上收益明显)。
  // max_iter/max_cpu_time: 早停时 solve() 抛异常, 由 solve() 的回收逻辑取回
  // 当前迭代点 (RTI 风格), 而不是丢整拍。max_cpu_time 须 < 节点的
  // max_solve_time_ms (200ms), 为状态发布留余量。
  opti_.solver("ipopt",
    {{"print_time", 0}, {"expand", true}},
    {{"print_level", 0}, {"max_iter", params_.ipopt_max_iter},
      {"max_cpu_time", params_.ipopt_max_cpu_time_s},
      {"warm_start_init_point", "yes"},
      {"tol", 1e-4}, {"acceptable_tol", 1e-3},
      {"acceptable_iter", 5}});

  X_warm_ = Eigen::MatrixXd::Zero(NX, N + 1);  // 5 x (N+1) (B 是 6)
  U_warm_ = Eigen::MatrixXd::Zero(NU, N);      // 2 x N (同 B)
}

std::pair<Eigen::Vector2d, SolveInfo>
CasadiKinematicBackend::solve(
  const Eigen::Matrix<double, 5, 1> & current_state,
  const Eigen::MatrixXd & reference)
{
  SolveInfo info;
  snprintf(info.backend, sizeof(info.backend), "casadi");
  const int N = params_.N;
  constexpr int NX = 5;
  constexpr int NU = 2;
  constexpr int NREF = 3;

  // 参数赋值 (列主序 vector -> DM, 用 Sparsity::dense 指定形状)
  std::vector<double> x0v(current_state.data(), current_state.data() + NX);
  opti_.set_value(p_x0_, DM(Sparsity::dense(NX, 1), x0v));

  std::vector<double> refv(NREF * (N + 1));
  for (int c = 0; c <= N; ++c) {
    for (int r = 0; r < NREF; ++r) {
      refv[c * NREF + r] = reference(r, c);
    }
  }
  opti_.set_value(p_ref_, DM(Sparsity::dense(NREF, N + 1), refv));

  std::vector<double> upv(u_prev_.data(), u_prev_.data() + NU);
  opti_.set_value(p_u_prev_, DM(Sparsity::dense(NU, 1), upv));

  // 热启动初值: X 平移滚动 (丢弃首列, 末列复制), U 同样用上次解滚动。
  if (has_warm_) {
    std::vector<double> xw(NX * (N + 1));
    for (int c = 0; c <= N; ++c) {
      for (int r = 0; r < NX; ++r) {
        xw[c * NX + r] = X_warm_(r, c);
      }
    }
    opti_.set_initial(X_, DM(Sparsity::dense(NX, N + 1), xw));
    std::vector<double> uw(NU * N);
    for (int c = 0; c < N; ++c) {
      for (int r = 0; r < NU; ++r) {
        uw[c * NU + r] = U_warm_(r, c);
      }
    }
    opti_.set_initial(U_, DM(Sparsity::dense(NU, N), uw));
  } else {
    std::vector<double> xw(NX * (N + 1));
    for (int c = 0; c <= N; ++c) {
      for (int r = 0; r < NX; ++r) {
        xw[c * NX + r] = current_state(r);
      }
    }
    opti_.set_initial(X_, DM(Sparsity::dense(NX, N + 1), xw));
    opti_.set_initial(U_, DM(Sparsity::dense(NU, N), std::vector<double>(NU * N, 0.0)));
  }

  // 对偶热启动: 按 CasADi Opti 接口把上一拍约束乘子设为本拍初值。
  if (has_dual_) {
    try {
      opti_.set_initial(opti_.lam_g(), lam_g_warm_);
    } catch (const std::exception &) {
      has_dual_ = false;
    }
  }

  // 提取候选解并验证完整约束。正常收敛解和早停回收解必须经过同一门禁，
  // 防止把数值有限、但违反动力学或控制约束的 IPOPT 迭代点发布到实船。
  Eigen::Vector2d u_out = u_prev_;
  auto accept_solution = [&](const DM & X_dm, const DM & U_dm,
    const char * note, const DM & lam_dm) {
      std::vector<double> x_all = X_dm.nonzeros();
      std::vector<double> u_all = U_dm.nonzeros();
      if (x_all.size() != static_cast<size_t>(NX * (N + 1)) ||
        u_all.size() != static_cast<size_t>(NU * N))
      {
        snprintf(info.error, sizeof(info.error), "invalid_solution_dimensions");
        return false;
      }

      info.X_pred = Eigen::MatrixXd::Zero(NX, N + 1);
      info.U_pred = Eigen::MatrixXd::Zero(NU, N);
      for (int c = 0; c <= N; ++c) {
        for (int r = 0; r < NX; ++r) {
          info.X_pred(r, c) = x_all[c * NX + r];
        }
      }
      for (int c = 0; c < N; ++c) {
        for (int r = 0; r < NU; ++r) {
          info.U_pred(r, c) = u_all[c * NU + r];
        }
      }
      Eigen::Vector2d u_opt = info.U_pred.col(0);

      if (!u_opt.allFinite() || !info.X_pred.allFinite() ||
        !info.U_pred.allFinite())
      {
        snprintf(info.error, sizeof(info.error), "non_finite_solution");
        info.X_pred.resize(0, 0);
        info.U_pred.resize(0, 0);
        return false;
      }

      info.initial_state_residual =
        (info.X_pred.col(0) - current_state).cwiseAbs().maxCoeff();
      info.max_dynamics_residual = 0.0;
      info.max_control_bound_violation = 0.0;
      info.max_control_rate_violation = 0.0;

      const double du_step = params_.du_max * params_.dt;
      const double dr_step = params_.dr_max * params_.dt;
      Eigen::Vector2d previous_control = u_prev_;
      for (int k = 0; k < N; ++k) {
        Eigen::Vector2d uk = info.U_pred.col(k);

        info.max_control_bound_violation = std::max({
          info.max_control_bound_violation,
          params_.u_min - uk(0), uk(0) - params_.u_max,
          -params_.r_max - uk(1), uk(1) - params_.r_max});
        info.max_control_rate_violation = std::max({
          info.max_control_rate_violation,
          std::abs(uk(0) - previous_control(0)) - du_step,
          std::abs(uk(1) - previous_control(1)) - dr_step});

        std::vector<double> xk(info.X_pred.col(k).data(),
          info.X_pred.col(k).data() + NX);
        std::vector<double> uk_vec(uk.data(), uk.data() + NU);
        DM predicted_dm = f_rk4_(std::vector<DM>{
          DM(Sparsity::dense(NX, 1), xk),
          DM(Sparsity::dense(NU, 1), uk_vec)}).at(0);
        std::vector<double> predicted_values = predicted_dm.nonzeros();
        if (predicted_values.size() != NX) {
          snprintf(info.error, sizeof(info.error), "invalid_dynamics_output");
          info.X_pred.resize(0, 0);
          info.U_pred.resize(0, 0);
          return false;
        }
        Eigen::Map<const Eigen::Matrix<double, NX, 1>> predicted(
          predicted_values.data());
        info.max_dynamics_residual = std::max(
          info.max_dynamics_residual,
          (predicted - info.X_pred.col(k + 1)).cwiseAbs().maxCoeff());
        previous_control = uk;
      }

      const double max_violation = std::max({
        info.initial_state_residual, info.max_dynamics_residual,
        info.max_control_bound_violation, info.max_control_rate_violation});
      if (max_violation > params_.solution_constraint_tol) {
        snprintf(info.error, sizeof(info.error),
               "constraint_violation: initial=%.3g dynamics=%.3g "
               "bounds=%.3g rate=%.3g tol=%.3g",
               info.initial_state_residual, info.max_dynamics_residual,
               info.max_control_bound_violation,
               info.max_control_rate_violation,
               params_.solution_constraint_tol);
        info.X_pred.resize(0, 0);
        info.U_pred.resize(0, 0);
        return false;
      }

    // 热启动滚动 (平移: 丢弃首列, 末列复制; 与 B 完全相同逻辑)
      X_warm_.leftCols(N) = info.X_pred.rightCols(N);
      X_warm_.col(N) = info.X_pred.col(N);
      U_warm_.leftCols(N - 1) = info.U_pred.rightCols(N - 1);
      U_warm_.col(N - 1) = info.U_pred.col(N - 1);
      u_prev_ = u_opt;
      has_warm_ = true;
      lam_g_warm_ = lam_dm;
      has_dual_ = true;

      u_out = u_opt;
      info.success = true;
      if (note != nullptr) {snprintf(info.error, sizeof(info.error), "%s", note);}
      return true;
    };

  auto t0 = std::chrono::steady_clock::now();
  try {
    OptiSol sol = opti_.solve();
    auto t1 = std::chrono::steady_clock::now();
    info.solve_time_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

    if (accept_solution(sol.value(X_), sol.value(U_), nullptr,
                        sol.value(opti_.lam_g())))
    {
      return {u_out, info};
    }
    info.success = false;
    return {u_prev_, info};
  } catch (const std::exception & e) {
    auto t1 = std::chrono::steady_clock::now();
    info.solve_time_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

    // 早停回收: IPOPT 触发 max_iter/max_cpu_time 时, Opti 先把最后迭代点
    // 存入内部状态再抛 "Solver failed..." (CasADi 异常带位置前缀, 故用
    // 子串匹配) — 此时 debug() 可取回。其他异常 (数值失败等, 求解器直接
    // throw, 无存储) 不可回收, 走通用失败路径。回收解经与成功路径相同的
    // 门禁后按成功处理 (RTI 风格), 节点侧仍有 solve deadline 兜底。
    if (std::strstr(e.what(), "Solver failed") != nullptr) {
      try {
        OptiAdvanced dbg = opti_.debug();
        if (accept_solution(dbg.value(X_), dbg.value(U_),
                            "ipopt_early_stop_feasible",
                            dbg.value(opti_.lam_g())))
        {
          return {u_out, info};
        }
      } catch (const std::exception &) {
        // 回收失败, 落到通用失败路径
      }
      char candidate_error[sizeof(info.error)];
      snprintf(candidate_error, sizeof(candidate_error), "%s", info.error);
      info.success = false;
      snprintf(info.error, sizeof(info.error),
               "ipopt_early_stop_infeasible: %.180s", candidate_error);
      return {u_prev_, info};
    }

    // 失败: 返回上次控制, 不更新热启动 (对齐 B, 防止发散)
    info.success = false;
    snprintf(info.error, sizeof(info.error), "%s", e.what());
    return {u_prev_, info};
  }
}

void CasadiKinematicBackend::reset_warmstart()
{
  has_warm_ = false;
  X_warm_.setZero();
  U_warm_.setZero();
  u_prev_.setZero();
  has_dual_ = false;
  lam_g_warm_ = DM();
}

void CasadiKinematicBackend::set_applied_command(const Eigen::Vector2d & applied)
{
  // clamp 到控制边界: 异常测量值 (GPS 重定位等) 若超出边界, 首步速率约束
  // ∩ 控制边界会变成空集 → NLP 不可行。
  u_prev_(0) = std::clamp(applied(0), params_.u_min, params_.u_max);
  u_prev_(1) = std::clamp(applied(1), -params_.r_max, params_.r_max);
}

Eigen::MatrixXd CasadiKinematicBackend::get_predicted_trajectory() const
{
  if (!has_warm_) {return Eigen::MatrixXd();}
  return X_warm_;
}

}  // namespace usv_mpc
