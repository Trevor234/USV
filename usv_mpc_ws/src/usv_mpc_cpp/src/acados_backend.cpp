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
 * @brief acados C 后端实现 (动力学 NMPC)。
 *
 * codegen 逻辑见 scripts/regenerate_acados_codegen.py
 * (原 usv_mpc/mpc_dynamic.py 的 _solve_acados / _build_acados_solver)。
 */

#include "usv_mpc_cpp/acados_backend.hpp"

#include <chrono>
#include <cmath>
#include <stdexcept>

#include <acados_c/ocp_nlp_interface.h>

namespace usv_mpc {

namespace {
// p_global 布局索引 (与 mpc_dynamic.py _pg_indices_weights 一致)
constexpr int N_HYDRO = 19;
constexpr int PG_N_Q = 6, PG_N_R = 2, PG_N_RD = 2, PG_N_QF = 1;
constexpr int PG_OFF_Q  = N_HYDRO;
constexpr int PG_OFF_R  = N_HYDRO + PG_N_Q;
constexpr int PG_OFF_RD = N_HYDRO + PG_N_Q + PG_N_R;
constexpr int PG_OFF_QF = N_HYDRO + PG_N_Q + PG_N_R + PG_N_RD;

// hydro 参数 -> p_global 前 19 维 (顺序与 usv_model_dynamic.hydro_dict_to_p_global 一致)
void fill_hydro(double* pg, const HydroParams& h) {
  pg[0]  = h.mass;       pg[1]  = h.Iz;        pg[2]  = h.xg;     pg[3]  = h.d_thruster;
  pg[4]  = h.Xu_dot;     pg[5]  = h.Yv_dot;    pg[6]  = h.Yr_dot; pg[7]  = h.Nv_dot;
  pg[8]  = h.Nr_dot;     pg[9]  = h.Xu;        pg[10] = h.Yv;     pg[11] = h.Yr;
  pg[12] = h.Nv;         pg[13] = h.Nr;        pg[14] = h.Xuu;    pg[15] = h.Yvv;
  pg[16] = h.Yrr;        pg[17] = h.Nvv;       pg[18] = h.Nrr;
}
}  // namespace

AcadosBackend::AcadosBackend(const MpcParams& params)
    : params_(params) {
  // codegen 已 vendored 并静态链接进本包 (codegen_lib),符号直接可用,
  // 无需运行时加载 .so。

  capsule_ = usv_dyn_nmpc_acados_create_capsule();
  if (capsule_ == nullptr) {
    throw std::runtime_error("usv_dyn_nmpc_acados_create_capsule 返回 null");
  }
  int status = usv_dyn_nmpc_acados_create(capsule_);
  if (status != 0) {
    usv_dyn_nmpc_acados_free_capsule(capsule_);
    capsule_ = nullptr;
    throw std::runtime_error("usv_dyn_nmpc_acados_create 失败 status=" +
                             std::to_string(status));
  }

  // 取 nlp 句柄 (用于 set/get x/u/lbx/ubx)
  nlp_config_ = usv_dyn_nmpc_acados_get_nlp_config(capsule_);
  nlp_dims_   = usv_dyn_nmpc_acados_get_nlp_dims(capsule_);
  nlp_in_     = usv_dyn_nmpc_acados_get_nlp_in(capsule_);
  nlp_out_    = usv_dyn_nmpc_acados_get_nlp_out(capsule_);

  // codegen 烘焙值校验: 运行时 N/dt 与 vendored 生成码不一致时,
  // update_params / ocp_nlp_out_set 会按错误的 stage 数越界写 (内存破坏),
  // 且生成码对这些调用无边界检查。启动即失败优于运行段错误;
  // 改 horizon/mpc_dt/dynamic.dt 后必须重新生成 codegen
  // (scripts/regenerate_acados_codegen.py, --horizon/--dt 与 yaml 一致)。
  const int baked_N = nlp_dims_->N;
  if (baked_N != params_.N) {
    usv_dyn_nmpc_acados_free(capsule_);
    usv_dyn_nmpc_acados_free_capsule(capsule_);
    capsule_ = nullptr;
    throw std::runtime_error(
        "acados codegen N=" + std::to_string(baked_N) + " 与配置 N=" +
        std::to_string(params_.N) +
        " 不一致: 请用 scripts/regenerate_acados_codegen.py 重新生成 codegen");
  }
  const double baked_dt = (nlp_in_->Ts != nullptr) ? nlp_in_->Ts[0] : 0.0;
  if (!(std::isfinite(baked_dt) &&
        std::fabs(baked_dt - params_.dt) < 1e-9)) {
    usv_dyn_nmpc_acados_free(capsule_);
    usv_dyn_nmpc_acados_free_capsule(capsule_);
    capsule_ = nullptr;
    throw std::runtime_error(
        "acados codegen dt=" + std::to_string(baked_dt) + " 与配置 dynamic.dt=" +
        std::to_string(params_.dt) +
        " 不一致: 请用 scripts/regenerate_acados_codegen.py 重新生成 codegen");
  }

  // 初始化 p_global 运行时值 (30 维)
  auto pg = build_p_global_();
  usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies(
      capsule_, const_cast<double*>(pg.data()), 30);

  X_warm_ = Eigen::MatrixXd::Zero(8, params_.N + 1);
  U_warm_ = Eigen::MatrixXd::Zero(2, params_.N);
}

AcadosBackend::~AcadosBackend() {
  if (capsule_ != nullptr) {
    usv_dyn_nmpc_acados_free(capsule_);
    usv_dyn_nmpc_acados_free_capsule(capsule_);
    capsule_ = nullptr;
  }
}

std::array<double, 30> AcadosBackend::build_p_global_() const {
  std::array<double, 30> pg{};
  fill_hydro(pg.data(), params_.hydro);
  for (int i = 0; i < PG_N_Q; ++i)  pg[PG_OFF_Q + i]  = params_.Q_diag(i);
  for (int i = 0; i < PG_N_R; ++i)  pg[PG_OFF_R + i]  = params_.R_diag(i);
  for (int i = 0; i < PG_N_RD; ++i) pg[PG_OFF_RD + i] = params_.Rd_diag(i);
  pg[PG_OFF_QF] = params_.Qf_scale;
  return pg;
}

std::pair<Eigen::Vector2d, SolveInfo>
AcadosBackend::solve(const Vector6d& current_state,
                     const Eigen::MatrixXd& reference) {
  SolveInfo info;
  info.backend = "acados";
  const int N = params_.N;

  try {
    // 1. x0 增广 [state(6); u_prev(2)]
    Eigen::Matrix<double, 8, 1> x0_aug;
    x0_aug << current_state, u_prev_;

    // 2. 钉住初始状态 (lbx/ubx at stage 0)
    ocp_nlp_constraints_model_set(nlp_config_, nlp_dims_, nlp_in_, nlp_out_,
                                  0, "lbx", x0_aug.data());
    ocp_nlp_constraints_model_set(nlp_config_, nlp_dims_, nlp_in_, nlp_out_,
                                  0, "ubx", x0_aug.data());

    // 2b. 约束边界运行时下发 (K1/K2: 消除 codegen 烘焙值与 yaml 配置的漂移风险;
    //     仅改数值、结构不变,无需 re-codegen。当前值与烘焙值一致时行为不变)
    double lbu_v[2] = {params_.T_min, params_.T_min};
    double ubu_v[2] = {params_.T_max, params_.T_max};
    const double dT_step = params_.dT_max * params_.dt;
    double lh_v[2] = {-dT_step, -dT_step};
    double uh_v[2] = {dT_step, dT_step};
    for (int k = 0; k < N; ++k) {
      ocp_nlp_constraints_model_set(nlp_config_, nlp_dims_, nlp_in_, nlp_out_,
                                    k, "lbu", lbu_v);
      ocp_nlp_constraints_model_set(nlp_config_, nlp_dims_, nlp_in_, nlp_out_,
                                    k, "ubu", ubu_v);
      ocp_nlp_constraints_model_set(nlp_config_, nlp_dims_, nlp_in_, nlp_out_,
                                    k, "lh", lh_v);
      ocp_nlp_constraints_model_set(nlp_config_, nlp_dims_, nlp_in_, nlp_out_,
                                    k, "uh", uh_v);
    }

    // 3. 每阶段参考 p = x_ref (6 维)
    for (int k = 0; k <= N; ++k) {
      double ref_k[6];
      for (int i = 0; i < 6; ++i) ref_k[i] = reference(i, k);
      usv_dyn_nmpc_acados_update_params(capsule_, k, ref_k, 6);
    }

    // 4. 热启动
    if (has_warm_) {
      for (int k = 0; k <= N; ++k) {
        ocp_nlp_out_set(nlp_config_, nlp_dims_, nlp_out_, nlp_in_, k, "x",
                        X_warm_.col(k).data());
      }
      for (int k = 0; k < N; ++k) {
        ocp_nlp_out_set(nlp_config_, nlp_dims_, nlp_out_, nlp_in_, k, "u",
                        U_warm_.col(k).data());
      }
    } else {
      Eigen::Matrix<double, 8, 1> guess;
      guess << x0_aug.head<6>(), Eigen::Vector2d::Zero();
      for (int k = 0; k <= N; ++k) {
        ocp_nlp_out_set(nlp_config_, nlp_dims_, nlp_out_, nlp_in_, k, "x",
                        guess.data());
      }
      Eigen::Vector2d u_zero = Eigen::Vector2d::Zero();
      for (int k = 0; k < N; ++k) {
        ocp_nlp_out_set(nlp_config_, nlp_dims_, nlp_out_, nlp_in_, k, "u",
                        u_zero.data());
      }
    }

    // 5. 求解 + 计时
    auto t0 = std::chrono::steady_clock::now();
    int status = usv_dyn_nmpc_acados_solve(capsule_);
    auto t1 = std::chrono::steady_clock::now();
    info.solve_time_ms =
        std::chrono::duration<double, std::milli>(t1 - t0).count();

    if (status != 0) {
      // K4: 分级安全回退,不再简单保持上一步推力
      ++fail_count_;
      info.success = false;
      info.error = "acados_status=" + std::to_string(status);
      return {safe_fallback_(info.error), info};
    }

    // 6. 提取解
    Eigen::Vector2d u_opt;
    double u0[2];
    ocp_nlp_out_get(nlp_config_, nlp_dims_, nlp_out_, 0, "u", u0);
    u_opt << u0[0], u0[1];

    Eigen::MatrixXd X_aug(8, N + 1);
    Eigen::MatrixXd U_sol(2, N);
    for (int k = 0; k <= N; ++k) {
      double xk[8];
      ocp_nlp_out_get(nlp_config_, nlp_dims_, nlp_out_, k, "x", xk);
      X_aug.col(k) = Eigen::Map<Eigen::Matrix<double, 8, 1>>(xk);
    }
    for (int k = 0; k < N; ++k) {
      double uk[2];
      ocp_nlp_out_get(nlp_config_, nlp_dims_, nlp_out_, k, "u", uk);
      U_sol.col(k) = Eigen::Map<Eigen::Vector2d>(uk);
    }

    // NaN/Inf 门禁: acados status=0 不保证解有限(参考/状态被污染时可能返回
    // NaN)。必须在写入热启动缓存之前拦截,否则 NaN 会经 u_prev_/X_warm_ 扩散。
    if (!u_opt.allFinite() || !X_aug.allFinite() || !U_sol.allFinite()) {
      ++fail_count_;
      info.success = false;
      info.error = "non_finite_solution";
      return {safe_fallback_(info.error), info};
    }

    // X_sol = X_aug 前 6 维 (切回给调用方)
    info.X_pred = X_aug.topRows(6);
    info.U_pred = U_sol;

    // 7. 移位热启动 (与 Python 一致: 左移一格, 末列复制)
    X_warm_.leftCols(N) = X_aug.rightCols(N);
    X_warm_.col(N) = X_aug.col(N);
    U_warm_.leftCols(N - 1) = U_sol.rightCols(N - 1);
    U_warm_.col(N - 1) = U_sol.col(N - 1);
    u_prev_ = u_opt;
    has_warm_ = true;
    fail_count_ = 0;

    info.success = true;
    return {u_opt, info};
  } catch (const std::exception& e) {
    ++fail_count_;
    info.success = false;
    info.error = std::string("acados_exception: ") + e.what();
    info.solve_time_ms = 0.0;
    return {safe_fallback_(info.error), info};
  }
}

Eigen::Vector2d AcadosBackend::safe_fallback_(std::string& note) {
  // K4 分级回退:
  //   ① 连续失败 < N 步且有历史最优轨迹 → 沿轨迹继续(取 shift 后首控制,
  //      每次失败轨迹前移一格,末端补零使推力自然衰减趋向停船);
  //   ② 连续失败 >= N 步(轨迹耗尽) → 双桨归零(Fossen 阻尼使船自然减速)。
  // 恢复求解成功后 fail_count_ 清零,自动回到正常控制。
  const int N = params_.N;
  if (has_warm_ && fail_count_ < N) {
    Eigen::Vector2d u_fb =
        U_warm_.col(0).cwiseMax(params_.T_min).cwiseMin(params_.T_max);
    U_warm_.leftCols(N - 1) = U_warm_.rightCols(N - 1);
    U_warm_.col(N - 1).setZero();
    X_warm_.leftCols(N) = X_warm_.rightCols(N);
    u_prev_ = u_fb;
    note += " fallback=shift_traj(fail=" + std::to_string(fail_count_) + ")";
    return u_fb;
  }
  u_prev_.setZero();
  note += " fallback=zero_thrust(fail=" + std::to_string(fail_count_) + ")";
  return Eigen::Vector2d::Zero();
}

void AcadosBackend::reset_warmstart() {
  has_warm_ = false;
  fail_count_ = 0;
  X_warm_.setZero();
  U_warm_.setZero();
  u_prev_.setZero();
  if (capsule_ != nullptr) {
    usv_dyn_nmpc_acados_reset(capsule_, 1);
  }
}

Eigen::MatrixXd AcadosBackend::get_predicted_trajectory() const {
  if (!has_warm_) return Eigen::MatrixXd();
  return X_warm_.topRows(6);
}

}  // namespace usv_mpc
