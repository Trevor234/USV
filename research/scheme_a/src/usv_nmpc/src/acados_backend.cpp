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
 * @file acados_backend.cpp
 * @brief acados 后端实现 (动力学 NMPC): 共用引擎 + 方案 B 语义。
 *
 * 求解循环/热启动/候选管理在 usv_acados::AcadosBackend (与方案 A 共用);
 * 本文件保留 p_global 组装、权重校验、连续失败计数与分级安全回退。
 * codegen 逻辑见 usv_acados/scripts/regenerate_acados_codegen.py --model dynamic。
 */

#include "usv_nmpc/acados_backend.hpp"

#include <array>
#include <cmath>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <string>

namespace usv_mpc
{

namespace
{
// p_global 布局索引 (与 usv_acados/scripts/regenerate_acados_codegen.py 一致)
constexpr int N_HYDRO = 19;
constexpr int PG_N_Q = 6, PG_N_R = 2, PG_N_RD = 2, PG_N_QF = 1;
constexpr int PG_OFF_Q = N_HYDRO;
constexpr int PG_OFF_R = N_HYDRO + PG_N_Q;
constexpr int PG_OFF_RD = N_HYDRO + PG_N_Q + PG_N_R;
constexpr int PG_OFF_QF = N_HYDRO + PG_N_Q + PG_N_R + PG_N_RD;
constexpr int PG_TOTAL = N_HYDRO + PG_N_Q + PG_N_R + PG_N_RD + PG_N_QF;

// 残差维度的编译期契约在 usv_acados/src/model_api.cpp 统一核对 (含 nx/np 等)。

// hydro 参数 -> p_global 前 19 维 (顺序与 usv_model_dynamic.hydro_dict_to_p_global 一致)
void fill_hydro(double * pg, const HydroParams & h)
{
  pg[0] = h.mass;       pg[1] = h.Iz;        pg[2] = h.xg;     pg[3] = h.d_thruster;
  pg[4] = h.Xu_dot;     pg[5] = h.Yv_dot;    pg[6] = h.Yr_dot; pg[7] = h.Nv_dot;
  pg[8] = h.Nr_dot;     pg[9] = h.Xu;        pg[10] = h.Yv;     pg[11] = h.Yr;
  pg[12] = h.Nv;         pg[13] = h.Nr;        pg[14] = h.Xuu;    pg[15] = h.Yvv;
  pg[16] = h.Yrr;        pg[17] = h.Nvv;       pg[18] = h.Nrr;
}
}  // namespace

AcadosBackend::AcadosBackend(const MpcParams & params)
: params_(params)
{
  if (!params_.Q_diag.allFinite() || !params_.R_diag.allFinite() ||
    !params_.Rd_diag.allFinite() || !std::isfinite(params_.Qf_scale) ||
    (params_.Q_diag.array() < 0.0).any() ||
    (params_.R_diag.array() < 0.0).any() ||
    (params_.Rd_diag.array() < 0.0).any() || params_.Qf_scale < 0.0)
  {
    throw std::invalid_argument("MPC cost weights must be finite and nonnegative");
  }

  // 共用引擎: 构造时核对 codegen 烘焙的 N/dt/维度, 失败即抛 (不静默回退)。
  engine_ = std::make_unique<usv_acados::AcadosBackend>(
      usv_acados::Model::Dynamic, build_problem_());
}

AcadosBackend::~AcadosBackend() = default;

std::array<double, 30> AcadosBackend::build_p_global_() const
{
  std::array<double, PG_TOTAL> pg{};
  fill_hydro(pg.data(), params_.hydro);
  for (int i = 0; i < PG_N_Q; ++i) {
    pg[PG_OFF_Q + i] = params_.Q_diag(i);
  }
  for (int i = 0; i < PG_N_R; ++i) {
    pg[PG_OFF_R + i] = params_.R_diag(i);
  }
  for (int i = 0; i < PG_N_RD; ++i) {
    pg[PG_OFF_RD + i] = params_.Rd_diag(i);
  }
  pg[PG_OFF_QF] = params_.Qf_scale;
  return pg;
}

usv_acados::Problem AcadosBackend::build_problem_() const
{
  usv_acados::Problem problem;
  problem.N = params_.N;
  problem.dt = params_.dt;
  const std::array<double, PG_TOTAL> pg = build_p_global_();
  problem.p_global = Eigen::Map<const Eigen::VectorXd>(pg.data(), PG_TOTAL);
  problem.lower << params_.T_min, params_.T_min;
  problem.upper << params_.T_max, params_.T_max;
  const double dT_step = params_.dT_max * params_.dt;
  problem.max_delta << dT_step, dT_step;
  return problem;
}

std::pair<Eigen::Vector2d, SolveInfo>
AcadosBackend::solve(
  const Vector6d & current_state,
  const Eigen::MatrixXd & reference)
{
  SolveInfo info;
  snprintf(info.backend, sizeof(info.backend), "acados");

  try {
    const usv_acados::Candidate & candidate =
      engine_->solve(current_state, reference);
    info.solve_time_ms = candidate.solver_time_ms;

    // K4: 非零状态码或非有限解都走分级回退, 绝不把不可用候选写进热启动。
    if (candidate.status != 0) {
      ++fail_count_;
      info.success = false;
      std::string note = "acados_status=" + std::to_string(candidate.status);
      const Eigen::Vector2d fb = safe_fallback_(note);
      snprintf(info.error, sizeof(info.error), "%s", note.c_str());
      return {fb, info};
    }
    if (!candidate.finite) {
      ++fail_count_;
      info.success = false;
      std::string note = "non_finite_solution";
      const Eigen::Vector2d fb = safe_fallback_(note);
      snprintf(info.error, sizeof(info.error), "%s", note.c_str());
      return {fb, info};
    }

    // X_sol = X_aug 前 6 维 (切回给调用方)
    info.X_pred = candidate.X_aug.topRows(6);
    info.U_pred = candidate.U;

    // 提交热启动 (左移/末列复制/anchor=首控制), 与历史行为一致。
    engine_->accept_candidate();
    fail_count_ = 0;

    info.success = true;
    return {candidate.U.col(0), info};
  } catch (const std::exception & e) {
    ++fail_count_;
    info.success = false;
    std::string note = std::string("acados_exception: ") + e.what();
    const Eigen::Vector2d fb = safe_fallback_(note);
    snprintf(info.error, sizeof(info.error), "%s", note.c_str());
    info.solve_time_ms = 0.0;
    return {fb, info};
  }
}

Eigen::Vector2d AcadosBackend::safe_fallback_(std::string & note)
{
  // K4 分级回退:
  //   ① 连续失败 < N 步且有历史最优轨迹 → 沿轨迹继续(取 shift 后首控制,
  //      每次失败轨迹前移一格,末端补零使推力自然衰减趋向停船);
  //   ② 连续失败 >= N 步(轨迹耗尽) → 双桨归零(Fossen 阻尼使船自然减速)。
  // 恢复求解成功后 fail_count_ 清零,自动回到正常控制。
  if (engine_->has_warmstart() && fail_count_ < params_.N) {
    const Eigen::Vector2d u_fb = engine_->shift_fallback();
    note += " fallback=shift_traj(fail=" + std::to_string(fail_count_) + ")";
    return u_fb;
  }
  engine_->set_anchor(Eigen::Vector2d::Zero());
  note += " fallback=zero_thrust(fail=" + std::to_string(fail_count_) + ")";
  return Eigen::Vector2d::Zero();
}

void AcadosBackend::set_applied_control(
  const Eigen::Vector2d & applied_control)
{
  constexpr double kBoundTolerance = 1e-9;
  if (!applied_control.allFinite()) {
    throw std::invalid_argument("applied control must be finite");
  }
  if ((applied_control.array() < params_.T_min - kBoundTolerance).any() ||
    (applied_control.array() > params_.T_max + kBoundTolerance).any())
  {
    throw std::out_of_range("applied control exceeds MPC thrust bounds");
  }
  engine_->set_anchor(applied_control);
}

void AcadosBackend::reset_warmstart()
{
  fail_count_ = 0;
  engine_->reset_warmstart();
}

Eigen::MatrixXd AcadosBackend::get_predicted_trajectory() const
{
  if (!engine_->has_warmstart()) {return Eigen::MatrixXd();}
  return engine_->warm_states().topRows(6);
}

}  // namespace usv_mpc
