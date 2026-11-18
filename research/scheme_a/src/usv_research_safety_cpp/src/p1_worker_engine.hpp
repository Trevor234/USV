// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// WorkerEngine —— solver_worker 的唯一求解入口。
//
// 它把三个角色合成一条受检路径：
//   1) usv_acados::AcadosBackend —— 唯一 capsule；
//   2) p1::EngineSession        —— 唯一能改 capsule 参数的事务；
//   3) Worker 的 Job 语义        —— 入口过期、最终 guard、终端隔离。
//
// 与旧的 usv_mpc::AcadosBackend 的差别（这是方案 A §4 的要求，不是风格偏好）：
//   * 没有安全回退：回退会把"失败"变成"看起来成功"，而本路径要求失败是终端的；
//   * 每一拍都在最终 guard 上重新求值 stop/expiry 谓词，而不是用调用前的快照；
//   * 模型参数只能由事务写入，Worker 不得直接调 set_p_global。
#pragma once

#include <atomic>
#include <cstdint>
#include <memory>
#include <string>

#include <Eigen/Dense>

#include "usv_nmpc/model_constants.hpp"
#include "usv_nmpc/mpc_solver.hpp"
#include "p1_engine_session.hpp"

namespace p1
{

/// 本 Job 的执行结局。它只有四个值，且**不**存在"成功但没求解"的中间态：
/// 一个既没候选、也没被类型化拒绝的 Job 就是实现缺陷，不是第五种结局。
enum class EngineDisposition
{
  /// 真 native solve 完成并产生了有限候选。
  CandidateReady,
  /// 本 Job 被类型化拒绝（入口/最终 guard/事务）。非终端，零本 Job native。
  JobRefused,
  /// owner 必须关闭（stop）。零后续 solve。
  Closing,
  /// 终端故障：准备事实错、谓词异常、原生结果不可用。同 run 不重启。
  TerminalFault,
};

const char *to_string(EngineDisposition d);

/// 一次求解的事务与原生账目（写进 worker source，不进入 Candidate 消息）。
struct EngineOutcome
{
  EngineDisposition execution = EngineDisposition::TerminalFault;
  bool model_switch_considered = false;
  bool model_switched = false;
  std::string disposition;
  std::string reason;
  std::uint64_t applied_generation = 0;
  bool model_consistent = false;
  /// 累计 native solve 进入数（与 backend 的计数器同一来源）。
  std::uint64_t native_solve_entries = 0;
  /// 本 Job 的 native solve 差分：before/after/this_job。
  std::uint64_t native_solve_entries_before = 0;
  std::uint64_t native_solve_entries_after = 0;
  std::uint64_t native_solve_entries_this_job = 0;
  /// 最终 guard 实际求值的时刻与原始 deadline（不被改写）。
  std::int64_t guard_checked_ns = 0;
  std::int64_t original_deadline_ns = 0;
  /// 本轮准备账本与事务拒绝事实。
  usv_acados::PreparationLedger preparation{};
  model_txn::RefusalFacts refusal{};
  bool guard_refused = false;
  bool terminal = false;
};

class WorkerEngine
{
public:
  /// contract 里的 N/dt/边界与生成码逐项核对；registry 由计划文件构造。
  WorkerEngine(const usv_mpc::MpcParams & params,
               model_reference::Registry registry,
               model_reference::Grid grid,
               std::uint64_t bootstrap_generation);

  /// 求解一拍。anchor 是上一拍实际下发控制（调用方已 clamp/校验）。
  /// stop/expired 是谓词：本函数在最终 guard 处重新求值，不接受快照。
  std::pair<Eigen::Vector2d, usv_mpc::SolveInfo> solve(
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
      EngineOutcome * outcome);

  /// WP6/WP7 重载: 为当前 Job 注入冻结的逐阶段 GP 残差 (3x21) 与首拍 PPO 偏好。
  std::pair<Eigen::Vector2d, usv_mpc::SolveInfo> solve(
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
      EngineOutcome * outcome);

#ifdef USV_RESEARCH_TEST_SEAMS
  /// 进程内测试接缝：在事务提交之后、真实准备之前插入一段可数的等待，
  /// 用来证明"准备期间越过原始 deadline"这条事实。普通构建编译剔除。
  void set_test_preparation_delay_ns(std::int64_t delay_ns)
  {
    test_preparation_delay_ns_ = delay_ns;
  }
#endif

  void set_applied_control(const Eigen::Vector2d & applied);
  void reset_warmstart();

  /// 入口处过期：纯值拒绝，零 native，不占 pending。Worker 在取出 pending、
  /// 可选阻塞之后、solve 之前调用它，消费合法 Job 的身份并记录原始期限。
  TransactionResult entry_refusal(
      const model_txn::RegisteredModelTransaction::JobIdentity & identity,
      const model_reference::Axes & axes,
      const model_reference::Grid & grid,
      std::uint64_t job_id,
      std::uint64_t target_tick,
      std::int64_t now_ns,
      std::int64_t original_deadline_ns)
  {
    return session_->entry_refusal(identity, axes, grid, job_id, target_tick,
                                   now_ns, original_deadline_ns);
  }

  int N() const { return usv_nmpc::kDynamicN; }
  double dt() const { return usv_nmpc::kDynamicDt; }
  const char * backend() const { return "acados"; }

  std::uint64_t applied_generation() const { return session_->applied_generation(); }
  bool model_consistent() const { return session_->model_consistent(); }
  bool faulted() const { return session_->faulted(); }
  bool closing() const { return session_->closing(); }
  const usv_acados::PreparationLedger & preparation() const
  {
    return session_->backend().preparation();
  }
  const model_txn::TouchFacts & touch_facts() const { return session_->touch_facts(); }

private:
  std::unique_ptr<EngineSession> session_;
  /// 本 Job 冻结的实执行锚点：事务 sync 会清后端 anchor，必须在事务之后
  /// 用这个值恢复，才能让切换首拍的变化率约束从真实前值起算。
  Eigen::Vector2d frozen_anchor_ = Eigen::Vector2d::Zero();
#ifdef USV_RESEARCH_TEST_SEAMS
  std::int64_t test_preparation_delay_ns_ = 0;
#endif
};

}  // namespace p1
