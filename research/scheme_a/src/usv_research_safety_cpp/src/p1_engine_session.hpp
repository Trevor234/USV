// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// p1::EngineSession —— Worker 的唯一模型会话。
//
// 设计约束（方案 A §4）：
//   * 一个 AcadosBackend（一个 capsule）+ 一个 RegisteredModelTransaction；
//   * 事务是唯一能改 capsule 参数的角色，EngineSession 只转发；
//   * 构造函数事实来自本类私有派生（ConstructorSource 只对事务与本类开放）；
//   * 三个事务回调严格分离：set_global -> update_p_global，
//     reset -> reset_native(1)，sync_cpp_state -> clear_cpp_state。合并任意
//     两个都会让"reset 成功但 C++ 未同步"这类故障无法表达（E04）。
#pragma once

#include <array>
#include <cstdint>
#include <memory>
#include <string>

#include <Eigen/Dense>
#include <nlohmann/json_fwd.hpp>

#include "usv_acados/acados_backend.hpp"
#include "p1_model_reference.hpp"
#include "p1_model_transaction.hpp"

namespace p1
{

/// 事务层的可观察账目（写进 worker source，不写进 Candidate 消息）。
struct TransactionResult
{
  bool applied = false;
  std::string disposition;
  std::string reason;
  std::uint64_t applied_generation = 0;
  bool model_consistent = false;
  bool cpp_state_synced = false;
  bool can_continue = false;
  bool closing = false;
  /// 事务是否判定本 Job 为终端（FaultedAfterTouch）。由事务的处置值决定，
  /// 不由上层按 reason 文本重判。
  bool terminal = false;
  /// 类型化拒绝事实：origin/fault 由事务给出，不在上层按文本重判。
  model_txn::RefusalFacts refusal{};
  /// 事务在准备阶段用掉的 native 调用（Test/报告用）。
  unsigned setter_entries = 0;
  unsigned reset_entries = 0;
  unsigned sync_entries = 0;
};

/// 事务三个回调唯一的 native 入口（构造时一次绑定，此后不可变）。
struct ApiRoute
{
  usv_acados::AcadosBackend * backend = nullptr;
};

class EngineSession {
public:
  /// 以登记表与网格构造：事务立即快照注册表并冻结。
  EngineSession(std::unique_ptr<usv_acados::AcadosBackend> backend,
                const model_reference::Registry &registry,
                const model_reference::Grid &grid,
                std::uint64_t bootstrap_generation);

  ~EngineSession();
  EngineSession(const EngineSession &) = delete;
  EngineSession &operator=(const EngineSession &) = delete;

  usv_acados::AcadosBackend & backend() { return *backend_; }
  const usv_acados::AcadosBackend & backend() const { return *backend_; }

  /// 事务决定要应用一次模型切换时，把 Job 的完整身份交给它。
  /// 返回 false 表示该 Job 在进入 native 之前已被拒绝（reason 已填）。
  bool prepare(const model_txn::RegisteredModelTransaction::JobIdentity & identity,
               const model_reference::Axes & axes,
               const model_reference::Grid & query_grid,
               std::uint64_t job_id,
               std::uint64_t target_tick,
               std::int64_t now_ns,
               std::int64_t original_deadline_ns,
               const std::array<double, 126> & reference,
               double initial_yaw,
               std::string * reason);

  /// 消费上一次 prepare 的句柄。stop/expiry 谓词在检查点重新求值。
  TransactionResult apply(std::int64_t now_ns,
                          const model_txn::RegisteredModelTransaction::StopPredicate & stop,
                          const model_txn::RegisteredModelTransaction::ExpiryPredicate & expired);

  /// 本 Job 在入口就过期：纯值拒绝，零 native，零 pending 占用。
  TransactionResult entry_refusal(const model_txn::RegisteredModelTransaction::JobIdentity & identity,
                                  const model_reference::Axes & axes,
                                  const model_reference::Grid & query_grid,
                                  std::uint64_t job_id,
                                  std::uint64_t target_tick,
                                  std::int64_t now_ns,
                                  std::int64_t original_deadline_ns);

  const model_txn::RegisteredModelTransaction & transaction() const { return *txn_; }
  std::uint64_t applied_generation() const { return txn_->applied_generation(); }
  bool model_consistent() const { return txn_->model_consistent(); }
  bool faulted() const { return txn_->faulted(); }
  bool closing() const { return txn_->closing(); }
  const model_txn::TouchFacts & touch_facts() const { return txn_->facts(); }
  std::size_t registry_size() const { return txn_->registry_size(); }

  /// 构造事实：只能由本类签发（ConstructorSource 的私有构造者）。
  struct BootstrapFacts
  {
    model_reference::Content content{};
    model_txn::FrozenBaseline baseline{};
  };
  const BootstrapFacts & bootstrap_facts() const { return boot_; }

private:
  std::unique_ptr<usv_acados::AcadosBackend> backend_;
  std::unique_ptr<model_txn::RegisteredModelTransaction> txn_;
  BootstrapFacts boot_{};
  model_txn::PreparedOutcome prepared_{};
  bool prepared_valid_ = false;
  /// 与 ConstructorSource 共享的 capsule 生命周期令牌。
  std::shared_ptr<const std::uint64_t> lifetime_token_;
  std::unique_ptr<ApiRoute> route_;
  void * api_route_ = nullptr;
};

/// 从一份 132 语义计划文本构造 registry：任何不一致都抛 std::runtime_error。
/// 这是 Regulator 与 Worker 共用的唯一计划入口。
model_reference::Registry registry_from_plan(const std::string & preimage,
                                             const model_reference::Grid & grid);

bool content_from_controlled_sim_contract(const nlohmann::json & contract,
    model_reference::Content * out, std::string * err);

bool registry_from_plan_and_contract(const std::string & preimage,
    const model_reference::Grid & grid, const std::string & contract_json_text,
    model_reference::Registry * out, std::string * err);

/// 默认登记表（g1=M0 1..5, g2=M1 6..11, g3=M0 12..）。
model_reference::Registry default_registry(const model_reference::Grid & grid);

}  // namespace p1
