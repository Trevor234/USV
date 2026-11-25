// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include "p1_engine_session.hpp"

#include <cstring>
#include <stdexcept>
#include <string>

#include <nlohmann/json.hpp>

#include "usv_nmpc/model_constants.hpp"

namespace p1
{
namespace
{

model_txn::FrozenBaseline frozen_baseline_from_backend()
{
  model_txn::FrozenBaseline b;
  b.N = static_cast<double>(usv_nmpc::kDynamicN);
  b.dt = usv_nmpc::kDynamicDt;
  b.T_min = usv_nmpc::kDynamicTMin;
  b.T_max = usv_nmpc::kDynamicTMax;
  b.dT_max = usv_nmpc::kDynamicDTMax;
  return b;
}

/// 事务层看到的"真实 native 是否被调用"必须来自引擎，而不是事务自己推断。
/// 三个回调分别对应一个真实入口；各自的非零状态码就是事务的拒绝原因。

model_txn::ApiResult set_global(void * ctx, const model_reference::Content & content)
{
  auto * route = static_cast<ApiRoute *>(ctx);
  Eigen::VectorXd values(static_cast<int>(content.size()));
  for (std::size_t i = 0; i < content.size(); ++i) values[static_cast<int>(i)] = content[i];
  model_txn::ApiResult r;
  r.native_called = true;
  r.code = route->backend->update_p_global(values);
  r.ok = (r.code == 0);
  return r;
}

model_txn::ApiResult reset_native(void * ctx, int reset_qp_memory)
{
  auto * route = static_cast<ApiRoute *>(ctx);
  model_txn::ApiResult r;
  r.native_called = true;
  r.code = route->backend->reset_native(reset_qp_memory);
  r.ok = (r.code == 0);
  return r;
}

/// 只清 C++ 侧：零 native 调用。与 reset 分开，否则"reset 成功 ≠ C++ 已同步"
/// 这条事实永远无法区分（E04）。
model_txn::ApiResult sync_cpp(void * ctx, const model_reference::Content &)
{
  auto * route = static_cast<ApiRoute *>(ctx);
  route->backend->clear_cpp_state();
  model_txn::ApiResult r;
  r.ok = true;
  r.native_called = false;
  r.code = 0;
  return r;
}

std::string disposition_name(model_txn::Disposition d) { return model_txn::to_string(d); }

TransactionResult to_result(const model_txn::Outcome & out)
{
  TransactionResult r;
  r.applied = out.applied_generation != 0;
  r.disposition = disposition_name(out.disposition);
  r.reason = out.reason;
  r.applied_generation = out.applied_generation;
  r.model_consistent = out.model_consistent;
  r.cpp_state_synced = out.cpp_state_synced;
  r.can_continue = out.can_continue_this_job;
  r.closing = out.closing;
  r.terminal = out.terminal();
  r.setter_entries = out.facts.setter_entries;
  r.reset_entries = out.facts.reset_entries;
  r.sync_entries = out.facts.sync_entries;
  r.refusal = out.refusal;
  // 事务只在两个地方显式写 refusal（入口/提交后过期、谓词异常）。其余终端
  // 分支都是"准备事实错"（setter/reset/sync 的入口、返回值、原生进入），
  // 按**处置值**归一，而不是按 reason 文本分支。
  if (r.refusal.origin == model_txn::RefusalOrigin::None)
  {
    switch (out.disposition)
    {
      case model_txn::Disposition::FaultedAfterTouch:
        r.refusal.origin = model_txn::RefusalOrigin::PrepareFailure;
        r.refusal.fault = model_txn::RefusalFault::Unknown;
        r.refusal.model_terminal = true;
        break;
      case model_txn::Disposition::AppliedThenStopped:
        r.refusal.origin = model_txn::RefusalOrigin::Stop;
        r.refusal.fault = model_txn::RefusalFault::Stop;
        r.refusal.model_terminal = false;
        break;
      case model_txn::Disposition::AppliedButJobExpired:
        r.refusal.origin = model_txn::RefusalOrigin::TransactionCommittedExpiry;
        r.refusal.fault = model_txn::RefusalFault::Expiry;
        r.refusal.model_terminal = false;
        break;
      default:
        if (out.closing)
        {
          // 触碰前的 stop 拒绝：原模型不变，owner 关闭，但不是数值故障。
          r.refusal.origin = model_txn::RefusalOrigin::Stop;
          r.refusal.fault = model_txn::RefusalFault::Stop;
        }
        break;
    }
  }
  if (r.refusal.origin != model_txn::RefusalOrigin::None)
  {
    r.refusal.applied_generation = out.applied_generation;
    r.refusal.model_consistent = out.model_consistent;
    r.refusal.closing = out.closing;
    r.refusal.c_solve_entries_this_job = 0;
  }
  return r;
}

}  // namespace

EngineSession::EngineSession(std::unique_ptr<usv_acados::AcadosBackend> backend,
                             const model_reference::Registry & registry,
                             const model_reference::Grid & grid,
                             std::uint64_t bootstrap_generation)
    : backend_(std::move(backend))
{
  if (!backend_) throw std::invalid_argument("engine session needs a backend");
  if (backend_->model() != usv_acados::Model::Dynamic)
    throw std::runtime_error("engine session requires the dynamic model");

  boot_.content = model_reference::m0_content();
  boot_.baseline = frozen_baseline_from_backend();

  // 唯一的 capsule 生命周期令牌：构造源与事务共享它，源在会话销毁后立即过期。
  auto lifetime = std::make_shared<const std::uint64_t>(reinterpret_cast<std::uintptr_t>(this));

  model_txn::RegisteredModelTransaction::ConstructorSource source;
  source.issuer_ = reinterpret_cast<std::uintptr_t>(this);
  source.owner_ = std::this_thread::get_id();
  source.lifetime_ = lifetime;
  source.content_ = boot_.content;
  source.baseline_ = boot_.baseline;
  // 后端构造函数已经把这份 30 维参数烘焙进 capsule；这就是"真的调用了 native"
  // 的事实来源，而不是事务自报。
  source.native_called_ = true;
  source.applied_ok_ = true;
  lifetime_token_ = lifetime;

  route_ = std::make_unique<ApiRoute>();
  route_->backend = backend_.get();
  api_route_ = route_.get();

  model_txn::TransactionApi api;
  api.set_global = [this](const model_reference::Content & c) {
    return set_global(api_route_, c);
  };
  api.reset = [this](int qp) { return reset_native(api_route_, qp); };
  api.sync_cpp_state = [this](const model_reference::Content & c) {
    return sync_cpp(api_route_, c);
  };

  model_txn::Options opts;
  opts.model_switch_enabled = true;

  txn_ = std::make_unique<model_txn::RegisteredModelTransaction>(
      registry, grid, api, boot_.baseline, opts, source);

  std::string reason;
  if (!txn_->adopt_constructor_fact(bootstrap_generation, source, 1, &reason))
  {
    throw std::runtime_error("engine session bootstrap rejected: " + reason);
  }
}

EngineSession::~EngineSession() = default;

bool EngineSession::prepare(const model_txn::RegisteredModelTransaction::JobIdentity & identity,
                            const model_reference::Axes & axes,
                            const model_reference::Grid & query_grid,
                            std::uint64_t job_id,
                            std::uint64_t target_tick,
                            std::int64_t now_ns,
                            std::int64_t original_deadline_ns,
                            const std::array<double, 126> & reference,
                            double initial_yaw,
                            std::string * reason)
{
  prepared_ = txn_->prepare(identity, axes, query_grid, job_id, target_tick, now_ns,
                            original_deadline_ns, reference, initial_yaw);
  prepared_valid_ = prepared_.accepted;
  if (!prepared_) {
    if (reason) *reason = prepared_.reason;
    return false;
  }
  if (reason) reason->clear();
  return true;
}

TransactionResult EngineSession::apply(
    std::int64_t now_ns,
    const model_txn::RegisteredModelTransaction::StopPredicate & stop,
    const model_txn::RegisteredModelTransaction::ExpiryPredicate & expired)
{
  if (!prepared_valid_) {
    TransactionResult r;
    r.reason = "apply_without_prepare";
    r.disposition = "RefusedBeforeApply";
    return r;
  }
  prepared_valid_ = false;
  return to_result(txn_->apply(prepared_.handle, stop, expired, now_ns));
}

TransactionResult EngineSession::entry_refusal(
    const model_txn::RegisteredModelTransaction::JobIdentity & identity,
    const model_reference::Axes & axes,
    const model_reference::Grid & query_grid,
    std::uint64_t job_id,
    std::uint64_t target_tick,
    std::int64_t now_ns,
    std::int64_t original_deadline_ns)
{
  return to_result(txn_->consume_entry_refusal(identity, axes, query_grid, job_id,
                                               target_tick, now_ns,
                                               original_deadline_ns));
}

model_reference::Registry registry_from_plan(const std::string & preimage,
                                             const model_reference::Grid & grid)
{
  model_reference::Registry registry = model_reference::default_registry();
  const auto checked = registry.verify_plan_132_json(preimage, grid);
  if (!checked.ok)
  {
    throw std::runtime_error("plan rejected: " + checked.reason);
  }
  return registry;
}

model_reference::Registry default_registry(const model_reference::Grid &)
{
  return model_reference::default_registry();
}

}  // namespace p1
