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
 * @file acados_kinematic_backend.cpp
 * @brief 运动学 MPC acados 适配器实现 (方案 A)。
 *
 * 求解循环/热启动/候选管理在 usv_acados::AcadosBackend (与方案 B 共用);
 * 本文件保留 A 的 p_global 组装、参数校验、四残差硬门禁与 anchor clamp。
 */

#include "usv_mpc/acados_kinematic_backend.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <stdexcept>
#include <string>

#include "usv_mpc/kinematic_solution_audit.hpp"

namespace usv_mpc
{

namespace
{
// p_global 布局 (与 usv_acados/scripts/regenerate_acados_codegen.py 一致)
constexpr int PG_TOTAL = 8;

bool valid_bound(double lower, double upper)
{
  return std::isfinite(lower) && std::isfinite(upper) && lower <= upper;
}
}  // namespace

AcadosKinematicBackend::AcadosKinematicBackend(const KinematicMpcParams & params)
: params_(params)
{
  // tau 进入生成模型的 ODE 分母: 必须是有限正数。
  if (!(std::isfinite(params_.tau_u) && params_.tau_u > 0.0) ||
    !(std::isfinite(params_.tau_r) && params_.tau_r > 0.0))
  {
    throw std::invalid_argument("kinematic tau_u/tau_r must be finite and positive");
  }
  // 权重必须是有限非负数 (sqrt(2*w) 进入生成残差)。
  if (!params_.Q_diag.allFinite() || !params_.R_diag.allFinite() ||
    !std::isfinite(params_.Qf_scale) ||
    (params_.Q_diag.array() < 0.0).any() ||
    (params_.R_diag.array() < 0.0).any() || params_.Qf_scale < 0.0)
  {
    throw std::invalid_argument(
      "kinematic cost weights must be finite and nonnegative");
  }
  if (!(std::isfinite(params_.dt) && params_.dt > 0.0) || params_.N <= 0) {
    throw std::invalid_argument("kinematic dt must be finite/positive and N positive");
  }
  if (!valid_bound(params_.u_min, params_.u_max)) {
    throw std::invalid_argument("kinematic u_min/u_max must be finite and ordered");
  }
  if (!(std::isfinite(params_.r_max) && params_.r_max > 0.0)) {
    throw std::invalid_argument("kinematic r_max must be finite and positive");
  }
  if (!(std::isfinite(params_.du_max) && params_.du_max > 0.0) ||
    !(std::isfinite(params_.dr_max) && params_.dr_max > 0.0))
  {
    throw std::invalid_argument("kinematic du_max/dr_max must be finite and positive");
  }
  if (!(std::isfinite(params_.solution_constraint_tol) &&
    params_.solution_constraint_tol > 0.0))
  {
    throw std::invalid_argument("kinematic solution_constraint_tol must be positive");
  }

  // 共用引擎: 构造时核对生成码的 N/dt/维度并写入 p_global。
  engine_ = std::make_unique<usv_acados::AcadosBackend>(
    usv_acados::Model::Kinematic, build_problem_());
}

AcadosKinematicBackend::~AcadosKinematicBackend() = default;

Eigen::VectorXd AcadosKinematicBackend::build_p_global_() const
{
  Eigen::VectorXd pg(PG_TOTAL);
  pg << params_.tau_u, params_.tau_r,
    params_.Q_diag(0), params_.Q_diag(1), params_.Q_diag(2),
    params_.R_diag(0), params_.R_diag(1),
    params_.Qf_scale;
  return pg;
}

usv_acados::Problem AcadosKinematicBackend::build_problem_() const
{
  usv_acados::Problem problem;
  problem.N = params_.N;
  problem.dt = params_.dt;
  problem.p_global = build_p_global_();
  // 两通道边界不同: u 非对称 [u_min,u_max], r 对称 [-r_max,r_max]。
  problem.lower << params_.u_min, -params_.r_max;
  problem.upper << params_.u_max, params_.r_max;
  problem.max_delta << params_.du_max * params_.dt, params_.dr_max * params_.dt;
  return problem;
}

std::pair<Eigen::Vector2d, SolveInfo>
AcadosKinematicBackend::solve(
  const Eigen::Matrix<double, 5, 1> & current_state,
  const Eigen::MatrixXd & reference)
{
  SolveInfo info;
  snprintf(info.backend, sizeof(info.backend), "acados");

  // A 的 solve_time_ms 覆盖适配器完整 solve (设参+求解+提取+残差核查):
  // 节点用它和外部墙钟一起做 200 ms 拒绝, 两者语义必须一致。
  const auto begin = std::chrono::steady_clock::now();
  auto finish = [&info, begin]() {
      info.solve_time_ms = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - begin).count();
      return info.solve_time_ms;
    };

  try {
    const usv_acados::Candidate & candidate =
      engine_->solve(current_state, reference);

    // 只对可提取状态 (0/2/7) 做残差门禁; 其他状态直接失败, 不回收。
    const bool extractable = (candidate.status == 0 || candidate.status == 2 ||
      candidate.status == 7);
    if (!extractable || !candidate.finite) {
      info.success = false;
      info.X_pred.resize(0, 0);
      info.U_pred.resize(0, 0);
      finish();
      const Eigen::Vector2d anchor = engine_->anchor();
      if (!extractable) {
        snprintf(info.error, sizeof(info.error), "acados_status=%d",
                 candidate.status);
        return {anchor, info};
      }
      snprintf(info.error, sizeof(info.error), "non_finite_solution");
      return {anchor, info};
    }

    info.X_pred = candidate.X_aug.topRows(5);
    info.U_pred = candidate.U;

    const bool constraints_ok = audit_kinematic_solution(
      params_, current_state, engine_->anchor(), info.X_pred, info.U_pred, info);

    if (!accept_kinematic_candidate(candidate.status, candidate.finite,
        constraints_ok))
    {
      // status 0 也必须复核: 违反原门禁时按 constraint_violation 拒绝,
      // 并且不提交热启动 (诊断字段保留实际残差)。
      info.success = false;
      const Eigen::Vector2d anchor = engine_->anchor();
      const char * stage = (candidate.status == 0) ? "converged" : "early_stop";
      if (constraints_ok) {
        // 理论上不可达 (accept 需要 constraints_ok), 保留防御分支。
        snprintf(info.error, sizeof(info.error), "acados_%s_rejected", stage);
      } else if (candidate.status == 0) {
        char detail[sizeof(info.error)];
        snprintf(detail, sizeof(detail), "%s", info.error);
        snprintf(info.error, sizeof(info.error),
                 "status=0 constraint_violation: %.180s", detail);
      } else {
        char detail[sizeof(info.error)];
        snprintf(detail, sizeof(detail), "%s", info.error);
        snprintf(info.error, sizeof(info.error),
                 "acados_early_stop_infeasible: %.180s", detail);
      }
      info.X_pred.resize(0, 0);
      info.U_pred.resize(0, 0);
      finish();
      return {anchor, info};
    }

    // 通过门禁: 提交热启动, 首拍控制生效。
    engine_->accept_candidate();
    info.success = true;
    if (candidate.status != 0) {
      snprintf(info.error, sizeof(info.error), "acados_early_stop_feasible");
    }
    finish();
    return {info.U_pred.col(0), info};
  } catch (const std::exception & error) {
    // 维度/参数/数值异常一律降级为“本拍失败”, 不发布可疑解。
    info.success = false;
    info.X_pred.resize(0, 0);
    info.U_pred.resize(0, 0);
    info.initial_state_residual = 0.0;
    info.max_dynamics_residual = 0.0;
    info.max_control_bound_violation = 0.0;
    info.max_control_rate_violation = 0.0;
    snprintf(info.error, sizeof(info.error), "%.200s", error.what());
    finish();
    return {engine_->anchor(), info};
  }
}

void AcadosKinematicBackend::reset_warmstart()
{
  engine_->reset_warmstart();
}

void AcadosKinematicBackend::set_applied_command(const Eigen::Vector2d & applied)
{
  // 与 B 同理: 异常测量值 (GPS 重定位等) 若超出边界, 首步速率约束 ∩ 控制
  // 边界会变成空集 → NLP 不可行。A 按两通道各自 clamp。
  // 非有限输入不能靠 clamp “修好”, 直接拒绝。
  if (!applied.allFinite()) {
    throw std::invalid_argument("applied command must be finite");
  }
  Eigen::Vector2d clamped;
  clamped(0) = std::clamp(applied(0), params_.u_min, params_.u_max);
  clamped(1) = std::clamp(applied(1), -params_.r_max, params_.r_max);
  engine_->set_anchor(clamped);
}

Eigen::MatrixXd AcadosKinematicBackend::get_predicted_trajectory() const
{
  if (!engine_->has_warmstart()) {return Eigen::MatrixXd();}
  return engine_->warm_states().topRows(5);
}

double AcadosKinematicBackend::diagnostic_cost() const
{
  return engine_->candidate_cost();
}

}  // namespace usv_mpc
