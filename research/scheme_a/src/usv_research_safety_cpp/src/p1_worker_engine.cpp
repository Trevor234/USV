// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include "p1_worker_engine.hpp"

#include <cstdint>
#include <ctime>
#include <stdexcept>
#include <string>
#include <chrono>
#include <thread>

#include "usv_nmpc/model_constants.hpp"

namespace p1
{
namespace
{

/// CLOCK_MONOTONIC，与 worker 的 p1::monotonic_ns 同一时基（不得用 system_clock：
/// 事务的过期判定与 Job 的 deadline 是同一把尺子）。
std::int64_t monotonic_now_ns()
{
  timespec ts{};
  if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0)
    throw std::runtime_error("CLOCK_MONOTONIC failed");
  return static_cast<std::int64_t>(ts.tv_sec) * 1000000000 + ts.tv_nsec;
}

/// 30 维内容与 acados 生成码的参数顺序一致：19 水动力 + 6 Q + 2 R + 2 Rd + 1 Qf。
/// 这里复用 usv_nmpc 的权威打包函数，不重写偏移量。
model_reference::Content content_of(const usv_mpc::MpcParams & params)
{
  model_reference::Content content{};
  usv_nmpc::fill_hydro_p_global(content.data(), params.hydro);
  for (int i = 0; i < usv_nmpc::kPGN_Q; ++i)
    content[usv_nmpc::kPGOFF_Q + i] = params.Q_diag(i);
  for (int i = 0; i < usv_nmpc::kPGN_R; ++i)
    content[usv_nmpc::kPGOFF_R + i] = params.R_diag(i);
  for (int i = 0; i < usv_nmpc::kPGN_Rd; ++i)
    content[usv_nmpc::kPGOFF_Rd + i] = params.Rd_diag(i);
  content[usv_nmpc::kPGOFF_Qf] = params.Qf_scale;
  return content;
}

usv_acados::Problem problem_of(const usv_mpc::MpcParams & params,
                               const model_reference::Content & content)
{
  usv_acados::Problem problem;
  problem.N = usv_nmpc::kDynamicN;
  problem.dt = usv_nmpc::kDynamicDt;
  problem.p_global.resize(static_cast<int>(content.size()));
  for (std::size_t i = 0; i < content.size(); ++i)
    problem.p_global[static_cast<int>(i)] = content[i];
  problem.lower << params.T_min, params.T_min;
  problem.upper << params.T_max, params.T_max;
  const double dT_step = params.dT_max * params.dt;
  problem.max_delta << dT_step, dT_step;
  return problem;
}

/// 最终 native guard 的上下文：**栈上**、本 Job 独占、固定函数指针。
/// 它在真实 solve 紧前求值，所以用的必须是原始 deadline（不得改写或延长），
/// 且 stop 优先于 expiry —— stop 决定此后的 owner 归属。
struct GuardContext
{
  std::uint64_t job_id = 0;
  std::thread::id owner{};
  std::int64_t original_deadline_ns = 0;
  std::uint64_t expected_generation = 0;
  std::uint32_t horizon_steps = 0;
  const model_txn::RegisteredModelTransaction::StopPredicate * stop = nullptr;
  const model_txn::RegisteredModelTransaction::ExpiryPredicate * expired = nullptr;
  EngineOutcome * outcome = nullptr;
  // 结果（由 hook 写回，供调用方判定）
  bool refused = false;
  bool stopped = false;
  std::int64_t checked_ns = 0;
  model_txn::RefusalFacts refusal{};
};

void final_guard(void * context, const usv_acados::PreparationLedger & ledger)
{
  auto * guard = static_cast<GuardContext *>(context);
  if (guard == nullptr) throw std::runtime_error("final_guard_without_context");
  EngineOutcome * out = guard->outcome;

  // 1) 本轮准备账本必须完整：ordinals=1、complete、82/21/41、失败计数全 0。
  //    准备事实错是终端故障（PrepareFailure），不是"本拍过期"。
  const bool preparation_ok =
      ledger.ordinals == 1 && ledger.complete &&
      ledger.constraint_set_failed == 0 && ledger.update_params_failed == 0;
  if (!preparation_ok)
  {
    model_txn::RefusalFacts facts;
    facts.origin = model_txn::RefusalOrigin::PrepareFailure;
    facts.fault = model_txn::RefusalFault::Unknown;
    facts.job_id = guard->job_id;
    facts.original_deadline_ns = guard->original_deadline_ns;
    facts.checked_ns = monotonic_now_ns();
    facts.model_terminal = true;
    throw model_txn::Refusal(facts, "final_guard_preparation_incomplete");
  }
  if (guard->expected_generation == 0)
  {
    model_txn::RefusalFacts facts;
    facts.origin = model_txn::RefusalOrigin::InvalidInput;
    facts.fault = model_txn::RefusalFault::Unknown;
    facts.job_id = guard->job_id;
    facts.original_deadline_ns = guard->original_deadline_ns;
    facts.checked_ns = monotonic_now_ns();
    facts.model_terminal = true;
    throw model_txn::Refusal(facts, "final_guard_without_expected_generation");
  }

  // 2) 谓词抛异常 = PredicateFault（终端隔离），必须与"谓词返回 true"分开。
  bool stop_now = false;
  bool expired_now = false;
  try
  {
    stop_now = guard->stop != nullptr && (*guard->stop)();
    if (!stop_now) expired_now = guard->expired != nullptr && (*guard->expired)();
  }
  catch (...)
  {
    model_txn::RefusalFacts facts;
    facts.origin = model_txn::RefusalOrigin::PredicateFault;
    facts.fault = model_txn::RefusalFault::Unknown;
    facts.job_id = guard->job_id;
    facts.original_deadline_ns = guard->original_deadline_ns;
    facts.checked_ns = monotonic_now_ns();
    facts.model_terminal = true;
    if (out != nullptr) out->reason = "final_guard_predicate_threw";
    throw model_txn::Refusal(facts, "final_guard_predicate_threw");
  }

  // 3) 重新采样时钟，再判定：等于 deadline 不算过期（严格大于）。
  const std::int64_t checked = monotonic_now_ns();
  guard->checked_ns = checked;
  const bool past_deadline = checked > guard->original_deadline_ns;

  if (!stop_now && !expired_now && !past_deadline) return;

  model_txn::RefusalFacts facts;
  facts.job_id = guard->job_id;
  facts.original_deadline_ns = guard->original_deadline_ns;
  facts.checked_ns = checked;
  if (stop_now)
  {
    facts.origin = model_txn::RefusalOrigin::Stop;
    facts.fault = model_txn::RefusalFault::Stop;
    facts.closing = true;
  }
  else
  {
    facts.origin = model_txn::RefusalOrigin::RawFinalGuard;
    facts.fault = model_txn::RefusalFault::Expiry;
  }
  guard->refused = true;
  guard->stopped = stop_now;
  guard->refusal = facts;
  if (out != nullptr)
    out->reason = stop_now ? "final_guard_stop" : "final_guard_expired";
  throw model_txn::Refusal(facts, stop_now ? "final_guard_stop" : "final_guard_expired");
}

}  // namespace

const char *to_string(EngineDisposition d)
{
  switch (d)
  {
    case EngineDisposition::CandidateReady: return "candidate_ready";
    case EngineDisposition::JobRefused: return "job_refused";
    case EngineDisposition::Closing: return "closing";
    case EngineDisposition::TerminalFault: return "terminal_fault";
  }
  return "unknown";
}

WorkerEngine::WorkerEngine(const usv_mpc::MpcParams & params,
                           model_reference::Registry registry,
                           model_reference::Grid grid,
                           std::uint64_t bootstrap_generation)
{
  // 生成码烘焙的时域/步长/边界必须与合同逐项一致，否则一次静默覆盖就会
  // 让所有后续"数值一致"的断言失去意义。
  if (params.N != usv_nmpc::kDynamicN)
    throw std::runtime_error("contract N differs from the generated horizon");
  if (params.dt != usv_nmpc::kDynamicDt)
    throw std::runtime_error("contract dt differs from the generated step");
  if (params.T_min != usv_nmpc::kDynamicTMin || params.T_max != usv_nmpc::kDynamicTMax)
    throw std::runtime_error("contract command bounds differ from the generated bounds");
  if (params.dT_max != usv_nmpc::kDynamicDTMax)
    throw std::runtime_error("contract rate bound differs from the generated bound");

  const model_reference::Content content = content_of(params);
  auto backend = std::make_unique<usv_acados::AcadosBackend>(
      usv_acados::Model::Dynamic, problem_of(params, content));
  session_ = std::make_unique<EngineSession>(std::move(backend), registry, grid,
                                             bootstrap_generation);
  frozen_anchor_ = Eigen::Vector2d::Zero();

  // 构造事实里的内容必须就是本合同的参数：EngineSession 采用的是 m0_content()，
  // 若合同与 M0 不一致，这里的比较会立即失败而不是留到第一拍才发现。
  const auto & boot = session_->bootstrap_facts();
  for (std::size_t i = 0; i < content.size(); ++i)
  {
    if (boot.content[i] != content[i])
      throw std::runtime_error("contract parameters differ from the registered M0");
  }
}

std::pair<Eigen::Vector2d, usv_mpc::SolveInfo> WorkerEngine::solve(
    const model_reference::Axes & axes,
    const model_reference::Grid & grid,
    std::uint64_t job_id,
    std::uint64_t target_tick,
    std::int64_t original_deadline_ns,
    const Eigen::VectorXd & state,
    const Eigen::MatrixXd & reference,
    const Eigen::Vector2d & anchor,
    const model_txn::RegisteredModelTransaction::JobIdentity & identity,
    const model_txn::RegisteredModelTransaction::StopPredicate & stop,
    const model_txn::RegisteredModelTransaction::ExpiryPredicate & expired,
    EngineOutcome * outcome)
{
  const Eigen::MatrixXd zero_res = Eigen::MatrixXd::Zero(3, usv_nmpc::kDynamicN + 1);
  return solve(axes, grid, job_id, target_tick, original_deadline_ns, state,
               reference, anchor, zero_res, Eigen::Vector2d::Zero(), 0.0,
               identity, stop, expired, outcome);
}

std::pair<Eigen::Vector2d, usv_mpc::SolveInfo> WorkerEngine::solve(
    const model_reference::Axes & axes,
    const model_reference::Grid & grid,
    std::uint64_t job_id,
    std::uint64_t target_tick,
    std::int64_t original_deadline_ns,
    const Eigen::VectorXd & state,
    const Eigen::MatrixXd & reference,
    const Eigen::Vector2d & anchor,
    const Eigen::MatrixXd & stage_residuals,
    const Eigen::Vector2d & q_pi,
    double lambda_pi,
    const model_txn::RegisteredModelTransaction::JobIdentity & identity,
    const model_txn::RegisteredModelTransaction::StopPredicate & stop,
    const model_txn::RegisteredModelTransaction::ExpiryPredicate & expired,
    EngineOutcome * outcome)
{
  usv_mpc::SolveInfo info;
  info.success = false;
  ::snprintf(info.backend, sizeof(info.backend), "acados");
  std::pair<Eigen::Vector2d, usv_mpc::SolveInfo> answer{Eigen::Vector2d::Zero(), info};
  EngineOutcome local;
  EngineOutcome * out = outcome ? outcome : &local;
  *out = EngineOutcome{};
  out->original_deadline_ns = original_deadline_ns;

  if (reference.rows() != 6 || reference.cols() != 21 ||
      stage_residuals.rows() != 3 || stage_residuals.cols() != 21 ||
      !stage_residuals.allFinite() || !q_pi.allFinite() ||
      !std::isfinite(lambda_pi) || lambda_pi < 0.0)
  {
    std::snprintf(answer.second.error, sizeof(answer.second.error),
                  "reference_or_gp_shape:%ldx%ld/%ldx%ld",
                  static_cast<long>(reference.rows()), static_cast<long>(reference.cols()),
                  static_cast<long>(stage_residuals.rows()), static_cast<long>(stage_residuals.cols()));
    out->reason = answer.second.error;
    out->execution = EngineDisposition::TerminalFault;
    out->terminal = true;
    return answer;
  }

  // 实执行锚点先冻结：事务的 sync 会清 C++ 侧 anchor，切换后若直接用
  // 清零值，本拍的变化率约束就从 0 起算。冻结值在事务之后**重新**写回。
  frozen_anchor_ = anchor;
  const std::uint64_t native_before = session_->backend().native_solve_entries();
  out->native_solve_entries_before = native_before;

  const std::int64_t now = monotonic_now_ns();
  std::array<double, 126> flat{};
  std::copy(reference.data(), reference.data() + 126, flat.begin());

  std::string reason;
  if (!session_->prepare(identity, axes, grid, job_id, target_tick, now,
                         original_deadline_ns, flat, 0.0, &reason))
  {
    out->model_switch_considered = true;
    out->reason = reason;
    out->disposition = "PrepareRefused";
    out->execution = EngineDisposition::JobRefused;
    out->refusal.origin = model_txn::RefusalOrigin::InvalidInput;
    out->refusal.job_id = job_id;
    out->refusal.original_deadline_ns = original_deadline_ns;
    out->refusal.checked_ns = now;
    std::snprintf(answer.second.error, sizeof(answer.second.error), "%s", reason.c_str());
    return answer;
  }
  out->model_switch_considered = true;

  const auto applied = session_->apply(now, stop, expired);
  out->disposition = applied.disposition;
  out->reason = applied.reason;
  out->applied_generation = applied.applied_generation;
  out->model_consistent = applied.model_consistent;
  out->model_switched = applied.applied && applied.model_consistent;
  out->refusal = applied.refusal;

  if (!applied.can_continue)
  {
    // 事务拒绝本 Job（停止/过期/故障）。此时**零 C solve**，且不产生候选。
    out->guard_refused = true;
    // 终端故障优先于 closing：谓词异常既会关闭 owner，也必须被记为终局隔离。
    if (applied.terminal || applied.refusal.model_terminal)
      out->execution = EngineDisposition::TerminalFault;
    else if (applied.refusal.origin == model_txn::RefusalOrigin::Stop || applied.closing)
      out->execution = EngineDisposition::Closing;
    else
      out->execution = EngineDisposition::JobRefused;
    out->terminal = out->execution == EngineDisposition::TerminalFault;
    std::snprintf(answer.second.error, sizeof(answer.second.error), "%s",
                  applied.reason.empty() ? applied.disposition.c_str()
                                         : applied.reason.c_str());
    return answer;
  }

  // 事务的 apply/sync/clear 已经跑完：此时才把本 Job 冻结的实执行锚点写回，
  // 再进入准备与真实 solve。clear_cpp_state() 的清零语义保持不变。
  session_->backend().set_anchor(frozen_anchor_);

#ifdef USV_RESEARCH_TEST_SEAMS
  if (test_preparation_delay_ns_ > 0)
    std::this_thread::sleep_for(std::chrono::nanoseconds(test_preparation_delay_ns_));
#endif

  // 最终 native guard：栈上上下文，固定函数指针，紧邻真实 solve 求值。
  GuardContext guard;
  guard.job_id = job_id;
  guard.owner = std::this_thread::get_id();
  guard.original_deadline_ns = original_deadline_ns;
  guard.expected_generation = axes.model;
  guard.horizon_steps = static_cast<std::uint32_t>(usv_nmpc::kDynamicN);
  guard.stop = &stop;
  guard.expired = &expired;
  guard.outcome = out;

  usv_acados::SolveHooks hooks;
  hooks.context = &guard;
  hooks.before_native = &final_guard;

  const usv_acados::Candidate * candidate = nullptr;
  try
  {
    candidate = &session_->backend().solve(state, reference, stage_residuals, q_pi, lambda_pi, hooks);
  }
  catch (const model_txn::Refusal & refusal)
  {
    // guard 在真实 solve 紧前拒绝：backend 保证本轮零 C solve。
    out->preparation = session_->backend().preparation();
    out->native_solve_entries_after = session_->backend().native_solve_entries();
    out->native_solve_entries = out->native_solve_entries_after;
    out->native_solve_entries_this_job =
        out->native_solve_entries_after - native_before;
    out->guard_refused = true;
    out->refusal = refusal.facts();
    out->guard_checked_ns = guard.checked_ns;
    out->execution = guard.stopped ? EngineDisposition::Closing
                                   : (refusal.facts().model_terminal
                                          ? EngineDisposition::TerminalFault
                                          : EngineDisposition::JobRefused);
    out->terminal = out->execution == EngineDisposition::TerminalFault;
    if (out->reason.empty()) out->reason = refusal.what();
    std::snprintf(answer.second.error, sizeof(answer.second.error), "%s",
                  out->reason.c_str());
    return answer;
  }
  catch (const usv_acados::NativePreparationError & error)
  {
    // native 准备本身失败：终端故障，且本轮零 C solve。
    out->preparation = session_->backend().preparation();
    out->native_solve_entries_after = session_->backend().native_solve_entries();
    out->native_solve_entries = out->native_solve_entries_after;
    out->native_solve_entries_this_job =
        out->native_solve_entries_after - native_before;
    out->execution = EngineDisposition::TerminalFault;
    out->terminal = true;
    out->refusal.origin = model_txn::RefusalOrigin::PrepareFailure;
    out->refusal.fault = model_txn::RefusalFault::Unknown;
    out->refusal.job_id = job_id;
    out->refusal.original_deadline_ns = original_deadline_ns;
    out->refusal.checked_ns = monotonic_now_ns();
    out->refusal.model_terminal = true;
    out->reason = std::string("native_preparation_failed:") + error.operation;
    std::snprintf(answer.second.error, sizeof(answer.second.error), "%s",
                  out->reason.c_str());
    return answer;
  }

  out->preparation = session_->backend().preparation();
  out->native_solve_entries_after = session_->backend().native_solve_entries();
  out->native_solve_entries = out->native_solve_entries_after;
  out->native_solve_entries_this_job =
      out->native_solve_entries_after - native_before;
  out->guard_checked_ns = guard.checked_ns;

  if (candidate == nullptr)
  {
    out->execution = EngineDisposition::TerminalFault;
    out->terminal = true;
    out->reason = "native_candidate_missing";
    return answer;
  }
  answer.second.success = candidate->finite;
  answer.second.solve_time_ms = candidate->solver_time_ms;
  if (!candidate->finite)
  {
    std::snprintf(answer.second.error, sizeof(answer.second.error), "native_infeasible");
    out->execution = EngineDisposition::TerminalFault;
    out->terminal = true;
    out->refusal.origin = model_txn::RefusalOrigin::InvalidInput;
    out->refusal.fault = model_txn::RefusalFault::Unknown;
    out->refusal.model_terminal = true;
    out->refusal.job_id = job_id;
    out->refusal.c_solve_entries_this_job = 1;
    return answer;
  }
  out->execution = EngineDisposition::CandidateReady;
  out->terminal = false;
  answer.first = candidate->U.col(0);
  // 增广状态的前 6 维就是物理状态 (生成模型把 nu 维控制附在尾部)。
  answer.second.X_pred = candidate->X_aug.topRows(6);
  answer.second.U_pred = candidate->U;
  return answer;
}

void WorkerEngine::set_applied_control(const Eigen::Vector2d & applied)
{
  frozen_anchor_ = applied;
  session_->backend().set_anchor(applied);
}

void WorkerEngine::accept_candidate() { session_->backend().accept_candidate(); }

void WorkerEngine::reset_warmstart() { session_->backend().reset_warmstart(); }

bool WorkerEngine::has_warmstart() const { return session_->backend().has_warmstart(); }

}  // namespace p1
