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
 * @brief 方案 A/B 共用 acados 求解引擎实现。
 *
 * 求解顺序与方案 B 原 acados_backend.cpp 完全一致 (抽取来源):
 *   拼接 x0 -> 热启动 psi 解卷绕 -> stage 0 lbx/ubx -> 逐阶段 lbu/ubu/lh/uh
 *   -> 逐阶段参考解卷绕 + update_params -> 写热启动/零初猜 -> solve
 *   -> 提取候选 + 有限性检查。
 * 提交热启动 (左移/末列复制/anchor) 只在 accept_candidate() 内发生。
 */

#include "usv_acados/acados_backend.hpp"

#include <chrono>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

#include <acados_c/ocp_nlp_interface.h>

#include "model_api.hpp"

namespace usv_acados
{

namespace
{

/// 与 usv_nmpc/usv_mpc 的 normalize_angle 同一实现, 保持解卷绕逐位一致。
double wrap_to_pi(double angle)
{
  return std::atan2(std::sin(angle), std::cos(angle));
}

/// 允许提取候选解的状态码 (acados: 0=success, 2=maxiter, 7=timeout)。
bool status_extractable(int status)
{
  return status == 0 || status == 2 || status == 7;
}

}  // namespace

NativePreparationError::NativePreparationError(
  std::string operation_in, int stage_in, int status_in)
: std::runtime_error("native 准备失败: " + operation_in +
    " (stage " + std::to_string(stage_in) + ", status " +
    std::to_string(status_in) + ")"),
  operation(std::move(operation_in)), stage(stage_in), status(status_in)
{}

struct AcadosBackend::Impl
{
  Impl(Model model_in, const Problem & problem)
  : model(model_in), descriptor(detail::descriptor_for(model_in)),
    ops(detail::ops_for(model_in))
  {
    validate_problem(problem);

    // capsule 的 RAII 守卫: create 失败时释放半初始化对象, 绝不泄漏。
    capsule = ops.create_capsule();
    if (capsule == nullptr) {
      throw std::runtime_error(std::string(descriptor.symbol) +
                               ": create_capsule 返回 null");
    }
    const int created = ops.create(capsule);
    if (created != 0) {
      ops.free_capsule(capsule);
      capsule = nullptr;
      throw std::runtime_error(std::string(descriptor.symbol) +
                               ": acados_create 失败 status=" +
                               std::to_string(created));
    }

    config = ops.get_config(capsule);
    dims = ops.get_dims(capsule);
    nlp_in = ops.get_in(capsule);
    nlp_out = ops.get_out(capsule);
    nlp_solver = ops.get_solver(capsule);
    if (config == nullptr || dims == nullptr || nlp_in == nullptr ||
      nlp_out == nullptr || nlp_solver == nullptr)
    {
      release_capsule();
      throw std::runtime_error(std::string(descriptor.symbol) +
                               ": 生成码返回空 nlp 句柄");
    }

    // 烘焙尺寸核对必须发生在任何逐阶段写入之前: 生成码对越界 stage 写入
    // 没有边界检查 (update_params / out_set 会直接写坏内存)。
    if (dims->N != descriptor.N || dims->N != problem.N) {
      const int baked = dims->N;
      release_capsule();
      throw std::runtime_error(
        std::string(descriptor.symbol) + ": codegen N=" +
        std::to_string(baked) + " 与配置 N=" + std::to_string(problem.N) +
        " 不一致, 需重新生成 codegen");
    }
    // nx/nu/np 在 ocp_nlp_dims 里是逐阶段数组 (首元即 stage 0 维度)。
    if (dims->nx == nullptr || dims->nu == nullptr || dims->np == nullptr ||
      dims->nx[0] != descriptor.n_aug || dims->nu[0] != descriptor.nu ||
      dims->np[0] != descriptor.np || dims->np_global != descriptor.np_global)
    {
      release_capsule();
      throw std::runtime_error(std::string(descriptor.symbol) +
                               ": 生成码维度与 C++ 契约不一致");
    }
    if (nlp_in->Ts == nullptr) {
      release_capsule();
      throw std::runtime_error(std::string(descriptor.symbol) +
                               ": 生成码缺少阶段时间 Ts");
    }
    // nlp_in->Ts 只有 N 个元素 (阶段 0..N-1); 终端阶段没有时间步。
    for (int k = 0; k < descriptor.N; ++k) {
      const double baked_ts = nlp_in->Ts[k];
      if (!(std::isfinite(baked_ts) && std::fabs(baked_ts - problem.dt) < 1e-9)) {
        release_capsule();
        throw std::runtime_error(
          std::string(descriptor.symbol) + ": codegen dt=" +
          std::to_string(baked_ts) + " (stage " + std::to_string(k) +
          ") 与配置 dt=" + std::to_string(problem.dt) +
          " 不一致, 需重新生成 codegen");
      }
    }

    // p_global 全量覆盖 (生成占位值不可用于生产)。
    int pglobal_status = ops.set_p_global(capsule, p_global_scratch.data(),
        static_cast<int>(p_global_scratch.size()));
    if (pglobal_status != 0) {
      release_capsule();
      throw std::runtime_error(
        std::string(descriptor.symbol) +
        ": set_p_global_and_precompute_dependencies 失败 status=" +
        std::to_string(pglobal_status));
    }

    // p_global 运行期事务暂存: 只为满足生成码非 const 形参;
    // p_global_scratch 镜像不由 update_p_global 改写。
    p_global_txn_buffer.resize(descriptor.np_global);

    X_warm.setZero(descriptor.n_aug, descriptor.N + 1);
    U_warm.setZero(descriptor.nu, descriptor.N);
    candidate.X_aug.resize(descriptor.n_aug, descriptor.N + 1);
    candidate.U.resize(descriptor.nu, descriptor.N);
    candidate.X_aug.setZero();
    candidate.U.setZero();
  }

  ~Impl() {release_capsule();}

  void release_capsule()
  {
    if (capsule == nullptr) {
      return;
    }
    ops.free(capsule);
    ops.free_capsule(capsule);
    capsule = nullptr;
    config = nullptr;
    dims = nullptr;
    nlp_in = nullptr;
    nlp_out = nullptr;
    nlp_solver = nullptr;
  }

  void validate_problem(const Problem & problem)
  {
    if (problem.N <= 0) {
      throw std::invalid_argument("acados problem N must be positive");
    }
    if (!(std::isfinite(problem.dt) && problem.dt > 0.0)) {
      throw std::invalid_argument("acados problem dt must be finite and positive");
    }
    if (problem.p_global.size() != descriptor.np_global) {
      throw std::invalid_argument(
        std::string(descriptor.symbol) + ": p_global 长度 " +
        std::to_string(problem.p_global.size()) + " != " +
        std::to_string(descriptor.np_global));
    }
    if (!problem.p_global.allFinite()) {
      throw std::invalid_argument("acados problem p_global contains non-finite values");
    }
    if (!problem.lower.allFinite() || !problem.upper.allFinite() ||
      !problem.max_delta.allFinite())
    {
      throw std::invalid_argument("acados problem bounds must be finite");
    }
    if ((problem.lower.array() > problem.upper.array()).any()) {
      throw std::invalid_argument("acados problem lower bound exceeds upper bound");
    }
    if ((problem.max_delta.array() <= 0.0).any()) {
      throw std::invalid_argument("acados problem max_delta must be strictly positive");
    }
    p_global_scratch = problem.p_global;
    problem_N = problem.N;
    problem_dt = problem.dt;
    lower = problem.lower;
    upper = problem.upper;
    max_delta = problem.max_delta;
  }

  void invalidate_candidate()
  {
    candidate_valid = false;
    candidate.status = -1;
    candidate.finite = false;
    candidate.solver_time_ms = 0.0;
    candidate.X_aug.setZero();
    candidate.U.setZero();
  }

  /// 记账并检查一次 constraints setter 的真实 int 返回。
  void count_constraint_set(const char * operation, int stage, int status)
  {
    ledger.constraint_set_calls += 1;
    if (status != 0) {
      ledger.constraint_set_failed += 1;
      throw NativePreparationError(operation, stage, status);
    }
  }

  /// 记账并检查一次 update_params 的真实 int 返回。
  void count_update_params(int stage, int status)
  {
    ledger.update_params_calls += 1;
    if (status != 0) {
      ledger.update_params_failed += 1;
      throw NativePreparationError("update_params", stage, status);
    }
  }

  Model model;
  const detail::ModelDescriptor & descriptor;
  const detail::CapsuleOps & ops;

  void * capsule = nullptr;
  ocp_nlp_config * config = nullptr;
  ocp_nlp_dims * dims = nullptr;
  ocp_nlp_in * nlp_in = nullptr;
  ocp_nlp_out * nlp_out = nullptr;
  ocp_nlp_solver * nlp_solver = nullptr;

  // 构造参数副本 (不再引用调用方的 Problem)
  int problem_N = 0;
  double problem_dt = 0.0;
  Eigen::VectorXd p_global_scratch;
  Eigen::Vector2d lower = Eigen::Vector2d::Zero();
  Eigen::Vector2d upper = Eigen::Vector2d::Zero();
  Eigen::Vector2d max_delta = Eigen::Vector2d::Zero();

  // 热启动缓存
  bool has_warm = false;
  Eigen::MatrixXd X_warm;   // n_aug x (N+1)
  Eigen::MatrixXd U_warm;   // nu x N
  Eigen::Vector2d anchor_ = Eigen::Vector2d::Zero();
  // 候选解 (有效至下一次 solve 或 reset)
  Candidate candidate;
  bool candidate_valid = false;

  // 研究路径记账: 每 solve 清零的准备账 + 累计 native 进入数。
  PreparationLedger ledger;
  uint64_t native_solves = 0;

  // 求解 scratch (构造时按 N/模型一次分配, 循环内不建临时容器)
  Eigen::VectorXd x0_aug;
  std::vector<double> state_buffer;
  std::vector<double> control_buffer;
  std::vector<double> reference_buffer;

  // 运行期参数事务暂存 (见构造函数)。
  Eigen::VectorXd p_global_txn_buffer;
};


AcadosBackend::AcadosBackend(Model model, const Problem & problem)
: impl_(new Impl(model, problem))
{
  impl_->x0_aug.setZero(impl_->descriptor.n_aug);
  impl_->state_buffer.assign(
    static_cast<size_t>(impl_->descriptor.n_aug), 0.0);
  impl_->control_buffer.assign(static_cast<size_t>(impl_->descriptor.nu), 0.0);
  impl_->reference_buffer.assign(
    static_cast<size_t>(impl_->descriptor.np), 0.0);
}

AcadosBackend::~AcadosBackend() = default;

const Candidate & AcadosBackend::solve(
  const Eigen::Ref<const Eigen::VectorXd> & physical_state,
  const Eigen::Ref<const Eigen::MatrixXd> & reference)
{
  return solve(physical_state, reference, SolveHooks{});
}

const Candidate & AcadosBackend::solve(
  const Eigen::Ref<const Eigen::VectorXd> & physical_state,
  const Eigen::Ref<const Eigen::MatrixXd> & reference,
  const SolveHooks & hooks)
{
  Impl & d = *impl_;
  const detail::ModelDescriptor & desc = d.descriptor;

  // 每 solve 开始清零: 本轮准备失败不得借用上一轮的 complete。
  d.ledger = PreparationLedger{};
  d.ledger.ordinals = 1;

  if (physical_state.size() != desc.n_phys) {
    throw std::invalid_argument(
      std::string(desc.symbol) + ": physical_state 维度 " +
      std::to_string(physical_state.size()) + " != " +
      std::to_string(desc.n_phys));
  }
  if (reference.rows() != desc.np || reference.cols() != desc.N + 1) {
    throw std::invalid_argument(
      std::string(desc.symbol) + ": reference 维度 " +
      std::to_string(reference.rows()) + "x" +
      std::to_string(reference.cols()) + " != " +
      std::to_string(desc.np) + "x" + std::to_string(desc.N + 1));
  }
  if (!physical_state.allFinite() || !reference.allFinite()) {
    throw std::invalid_argument(
      std::string(desc.symbol) + ": state/reference 含非有限值");
  }

  // 上一次的候选在下一次 solve 前失效 (getter 不能读到陈旧 cost)。
  d.invalidate_candidate();

  const int N = desc.N;

  // 1. x0 增广 [state; anchor]
  d.x0_aug.head(desc.n_phys) = physical_state;
  d.x0_aug.tail(desc.nu) = d.anchor_;

  // 1b. 热启动航向解卷绕: 消除 ±pi 边界处 2pi 相位阶跃撕裂。
  if (d.has_warm) {
    const double current_psi = physical_state(2);
    const double shift = std::round(
      (current_psi - d.X_warm(2, 0)) / (2.0 * M_PI)) * (2.0 * M_PI);
    if (std::abs(shift) > 1e-3) {
      d.X_warm.row(2).array() += shift;
    }
  }

  // 2. 钉住初始状态 (stage 0 lbx/ubx), 真实 int 返回逐次记账。
  d.count_constraint_set("lbx", 0,
    ocp_nlp_constraints_model_set(d.config, d.dims, d.nlp_in, d.nlp_out,
                                  0, "lbx", d.x0_aug.data()));
  d.count_constraint_set("ubx", 0,
    ocp_nlp_constraints_model_set(d.config, d.dims, d.nlp_in, d.nlp_out,
                                  0, "ubx", d.x0_aug.data()));

  // 2b. 幅值与变化率边界逐阶段下发 (消除 codegen 烘焙值与 YAML 的漂移)。
  double lbu_v[2] = {d.lower(0), d.lower(1)};
  double ubu_v[2] = {d.upper(0), d.upper(1)};
  double lh_v[2] = {-d.max_delta(0), -d.max_delta(1)};
  double uh_v[2] = {d.max_delta(0), d.max_delta(1)};
  for (int k = 0; k < N; ++k) {
    d.count_constraint_set("lbu", k,
      ocp_nlp_constraints_model_set(d.config, d.dims, d.nlp_in, d.nlp_out,
                                    k, "lbu", lbu_v));
    d.count_constraint_set("ubu", k,
      ocp_nlp_constraints_model_set(d.config, d.dims, d.nlp_in, d.nlp_out,
                                    k, "ubu", ubu_v));
    d.count_constraint_set("lh", k,
      ocp_nlp_constraints_model_set(d.config, d.dims, d.nlp_in, d.nlp_out,
                                    k, "lh", lh_v));
    d.count_constraint_set("uh", k,
      ocp_nlp_constraints_model_set(d.config, d.dims, d.nlp_in, d.nlp_out,
                                    k, "uh", uh_v));
  }

  // 3. 逐阶段参考解卷绕 (第 2 行为 psi), 再写入阶段参数。
  double ref_psi_prev = physical_state(2);
  for (int k = 0; k <= N; ++k) {
    for (int i = 0; i < desc.np; ++i) {
      d.reference_buffer[static_cast<size_t>(i)] = reference(i, k);
    }
    const double solved = ref_psi_prev +
      wrap_to_pi(d.reference_buffer[2] - ref_psi_prev);
    d.reference_buffer[2] = solved;
    ref_psi_prev = solved;
    d.count_update_params(k, d.ops.update_params(
      d.capsule, k, d.reference_buffer.data(), desc.np));
  }

  // 4. 初猜: 有热启动则整条轨迹, 否则 [x0 物理; 0] 的零控制猜测。
  // ocp_nlp_out_set 是 void, 只计进入数, 不编造返回状态。
  if (d.has_warm) {
    for (int k = 0; k <= N; ++k) {
      ocp_nlp_out_set(d.config, d.dims, d.nlp_out, d.nlp_in, k, "x",
                      d.X_warm.col(k).data());
      d.ledger.out_set_calls += 1;
    }
    for (int k = 0; k < N; ++k) {
      ocp_nlp_out_set(d.config, d.dims, d.nlp_out, d.nlp_in, k, "u",
                      d.U_warm.col(k).data());
      d.ledger.out_set_calls += 1;
    }
  } else {
    for (int k = 0; k <= N; ++k) {
      ocp_nlp_out_set(d.config, d.dims, d.nlp_out, d.nlp_in, k, "x",
                      d.x0_aug.data());
      d.ledger.out_set_calls += 1;
    }
    double u_zero[2] = {0.0, 0.0};
    for (int k = 0; k < N; ++k) {
      ocp_nlp_out_set(d.config, d.dims, d.nlp_out, d.nlp_in, k, "u", u_zero);
      d.ledger.out_set_calls += 1;
    }
  }

  // 准备全部完成: 任一非零 int 状态都在上面抛出, 不会走到这里。
  d.ledger.complete = true;

  // 5. 最后一道 native guard: hook 在真实 solve 紧前调用, 抛出的类型化
  //    拒绝原样上抛 (本轮零 C solve, 不触碰 accept/fallback/capsule)。
  if (hooks.before_native != nullptr) {
    hooks.before_native(hooks.context, d.ledger);
  }

  // 紧邻真实 ops.solve() 才增加累计计数; guard 拒绝不计入。
  d.native_solves += 1;
  const auto t0 = std::chrono::steady_clock::now();
  const int status = d.ops.solve(d.capsule);
  const auto t1 = std::chrono::steady_clock::now();
  d.candidate.solver_time_ms =
    std::chrono::duration<double, std::milli>(t1 - t0).count();
  d.candidate.status = status;

  if (!status_extractable(status)) {
    // 其他状态直接保留状态码, 不提取可能陈旧的 nlp_out。
    d.candidate.finite = false;
    return d.candidate;
  }

  // 6. 提取候选 (未通过调用方门禁, 不影响 warm/anchor)
  double u0[2] = {0.0, 0.0};
  ocp_nlp_out_get(d.config, d.dims, d.nlp_out, 0, "u", u0);
  for (int k = 0; k <= N; ++k) {
    ocp_nlp_out_get(d.config, d.dims, d.nlp_out, k, "x", d.state_buffer.data());
    for (int i = 0; i < desc.n_aug; ++i) {
      d.candidate.X_aug(i, k) = d.state_buffer[static_cast<size_t>(i)];
    }
  }
  for (int k = 0; k < N; ++k) {
    ocp_nlp_out_get(d.config, d.dims, d.nlp_out, k, "u", d.control_buffer.data());
    for (int i = 0; i < desc.nu; ++i) {
      d.candidate.U(i, k) = d.control_buffer[static_cast<size_t>(i)];
    }
  }
  const bool finite = std::isfinite(u0[0]) && std::isfinite(u0[1]) &&
    d.candidate.X_aug.allFinite() && d.candidate.U.allFinite();
  d.candidate.finite = finite;
  d.candidate_valid = finite;
  return d.candidate;
}

void AcadosBackend::set_anchor(const Eigen::Vector2d & anchor)
{
  Impl & d = *impl_;
  if (!anchor.allFinite()) {
    throw std::invalid_argument("anchor must be finite");
  }
  d.anchor_ = anchor;
  if (d.has_warm) {
    d.X_warm.block(d.descriptor.anchor_offset, 0, d.descriptor.nu, 1) = anchor;
  }
}

const Eigen::Vector2d & AcadosBackend::anchor() const
{
  return impl_->anchor_;
}

void AcadosBackend::accept_candidate()
{
  Impl & d = *impl_;
  if (!d.candidate_valid || !d.candidate.finite) {
    throw std::logic_error("accept_candidate: 没有可提交的有限候选");
  }
  const int N = d.descriptor.N;
  d.X_warm.leftCols(N) = d.candidate.X_aug.rightCols(N);
  d.X_warm.col(N) = d.candidate.X_aug.col(N);
  d.U_warm.leftCols(N - 1) = d.candidate.U.rightCols(N - 1);
  d.U_warm.col(N - 1) = d.candidate.U.col(N - 1);
  d.anchor_ = d.candidate.U.col(0);
  d.has_warm = true;
}

Eigen::Vector2d AcadosBackend::shift_fallback()
{
  Impl & d = *impl_;
  const int N = d.descriptor.N;
  if (!d.has_warm) {
    return Eigen::Vector2d::Zero();
  }
  const Eigen::Vector2d u_fb = d.U_warm.col(0).cwiseMax(d.lower).cwiseMin(d.upper);
  d.U_warm.leftCols(N - 1) = d.U_warm.rightCols(N - 1);
  d.U_warm.col(N - 1).setZero();
  d.X_warm.leftCols(N) = d.X_warm.rightCols(N);
  d.anchor_ = u_fb;
  return u_fb;
}

void AcadosBackend::reset_warmstart()
{
  Impl & d = *impl_;
  // 先受检原生重置; 非零必须显式失败, 不清 warm, 不静默忽略。
  const int status = reset_native(1);
  if (status != 0) {
    throw std::runtime_error(
      std::string(d.descriptor.symbol) + ": acados_reset 失败 status=" +
      std::to_string(status) + "; warm 未清除");
  }
  clear_cpp_state();
}

int AcadosBackend::update_p_global(
  const Eigen::Ref<const Eigen::VectorXd> & values)
{
  Impl & d = *impl_;
  if (values.size() != d.descriptor.np_global) {
    throw std::invalid_argument(
      std::string(d.descriptor.symbol) + ": update_p_global 长度 " +
      std::to_string(values.size()) + " != " +
      std::to_string(d.descriptor.np_global));
  }
  if (!values.allFinite()) {
    throw std::invalid_argument(
      std::string(d.descriptor.symbol) + ": update_p_global 含非有限值");
  }
  // 任何参数修改前使旧候选失效; 不清 warm, 不改 C++ 参数镜像。
  d.invalidate_candidate();
  d.p_global_txn_buffer = values;
  return d.ops.set_p_global(d.capsule, d.p_global_txn_buffer.data(),
    d.descriptor.np_global);
}

int AcadosBackend::reset_native(int reset_qp_memory)
{
  Impl & d = *impl_;
  d.invalidate_candidate();
  return d.ops.reset(d.capsule, reset_qp_memory);
}

void AcadosBackend::clear_cpp_state()
{
  Impl & d = *impl_;
  d.has_warm = false;
  d.X_warm.setZero();
  d.U_warm.setZero();
  d.anchor_.setZero();
  d.invalidate_candidate();
}

const PreparationLedger & AcadosBackend::preparation() const
{
  return impl_->ledger;
}

uint64_t AcadosBackend::native_solve_entries() const
{
  return impl_->native_solves;
}

bool AcadosBackend::has_warmstart() const
{
  return impl_->has_warm;
}

const Eigen::MatrixXd & AcadosBackend::warm_states() const
{
  return impl_->X_warm;
}

double AcadosBackend::candidate_cost() const
{
  Impl & d = *impl_;
  if (!d.candidate_valid || !d.candidate.finite) {
    throw std::logic_error("candidate_cost: 没有有效有限候选");
  }
  // 直接从 nlp_out 求当前候选的代价: nlp_solver 内部 cost_value 可能属于
  // line-search 的试验点, 不能直接读。
  ocp_nlp_eval_cost(d.nlp_solver, d.nlp_in, d.nlp_out);
  double cost = 0.0;
  ocp_nlp_get(d.nlp_solver, "cost_value", &cost);
  if (!std::isfinite(cost)) {
    throw std::runtime_error("candidate_cost: acados cost_value 非有限");
  }
  return cost;
}

Model AcadosBackend::model() const
{
  return impl_->model;
}

int AcadosBackend::n_phys() const
{
  return impl_->descriptor.n_phys;
}

int AcadosBackend::n_aug() const
{
  return impl_->descriptor.n_aug;
}

int AcadosBackend::nu() const
{
  return impl_->descriptor.nu;
}

}  // namespace usv_acados
