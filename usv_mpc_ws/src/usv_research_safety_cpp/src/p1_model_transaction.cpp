// SPDX-License-Identifier: MIT
//
// registered_model_transaction_v1.cpp — owner 事务的实现（I03 / N02 修正版）。
//
// 本版针对 E01—E06 的六项修正：
//   E01 同代路径也先过 stop/expiry，再决定 can_continue_this_job
//   E02 BoundPreparedJob 绑定原 Job，apply 消费它一次
//   E03 bootstrap 只能由受检构造回执采用
//   E04 setter → reset → **sync_cpp_state** 全部成功后才发布新身份
//   E05 调用事实分 attempt / entry / returned / reported_ok
//   E06 事务持注册表快照（值拷贝）；Registry 有 freeze() 与重叠拒绝
//
// 仍然刻意不做任何 solve、不产生 candidate、不计数 completed —— 那些属于原 Worker
// 路径（T02）。也不链接 SDK。

#include "p1_model_transaction.hpp"

#include <cstring>
#include <atomic>
#include <limits>
#include <stdexcept>
#include <thread>

namespace model_txn {

namespace {

std::uint64_t mint_instance_id() {
  static std::atomic<std::uint64_t> next{1};
  auto current = next.load(std::memory_order_relaxed);
  for (;;) {
    if (!current) throw std::overflow_error("model_transaction_instance_ids_exhausted");
    const auto following = current == std::numeric_limits<std::uint64_t>::max()
                               ? 0 : current + 1;
    if (next.compare_exchange_weak(current, following, std::memory_order_relaxed))
      return current;
  }
}

// Release only after every use of this record and every callback has finished.
struct RecordLease {
  BoundRecord &record;
  bool &applying;
  ~RecordLease() { record.used = false; applying = false; }
};

bool bits_equal(double a, double b) {
  return std::memcmp(&a, &b, sizeof(double)) == 0;
}

// E05：一个回调调用的四层事实。只在实际进入回调时记录 entry/returned，
// 这样"回调不存在"不会冒称"调用成功"。
struct CallOutcome {
  bool entered = false;
  bool returned = false;
  ApiResult result{};
};

// 三个操作各自一个显式包装，避免模板推导出错，也让计数点一目了然。
CallOutcome call_setter(const std::function<ApiResult(const Content &)> &fn,
                        const Content &c, TouchFacts &f) {
  CallOutcome co;
  ++f.setter_attempts;
  if (!fn) return co;
  co.entered = true;
  ++f.setter_entries;
  try {
    co.result = fn(c);
    if (co.result.native_called) ++f.native_mutations;
    co.returned = true;
    ++f.setter_returned;
    if (co.result.ok) ++f.setter_reported_ok;
  } catch (...) {
    ++f.setter_native_outcome_unknown;
  }
  return co;
}

CallOutcome call_reset(const std::function<ApiResult(int)> &fn, int arg, TouchFacts &f) {
  CallOutcome co;
  ++f.reset_attempts;
  if (!fn) return co;
  co.entered = true;
  ++f.reset_entries;
  try {
    co.result = fn(arg);
    if (co.result.native_called) ++f.reset_calls;
    co.returned = true;
    ++f.reset_returned;
    if (co.result.ok) ++f.reset_reported_ok;
  } catch (...) {
    ++f.reset_native_outcome_unknown;
  }
  return co;
}

CallOutcome call_sync(const std::function<ApiResult(const Content &)> &fn,
                      const Content &c, TouchFacts &f) {
  CallOutcome co;
  ++f.sync_attempts;
  if (!fn) return co;
  co.entered = true;
  ++f.sync_entries;
  ++f.sync_calls;
  try {
    co.result = fn(c);
    co.returned = true;
    ++f.sync_returned;
    if (co.result.ok) ++f.sync_reported_ok;
  } catch (...) {
  }
  return co;
}

}  // namespace

const char *to_string(Disposition d) {
  switch (d) {
    case Disposition::ModelConsistentReady: return "ModelConsistentReady";
    case Disposition::RefusedBeforeApply: return "RefusedBeforeApply";
    case Disposition::AppliedButJobExpired: return "AppliedButJobExpired";
    case Disposition::AppliedThenStopped: return "AppliedThenStopped";
    case Disposition::FaultedAfterTouch: return "FaultedAfterTouch";
  }
  return "unknown";
}

bool FrozenBaseline::bit_equal(const FrozenBaseline &o) const {
  return bits_equal(N, o.N) && bits_equal(dt, o.dt) && bits_equal(T_min, o.T_min) &&
         bits_equal(T_max, o.T_max) && bits_equal(dT_max, o.dT_max);
}

RegisteredModelTransaction::RegisteredModelTransaction(
    const model_reference::Registry &registry, const model_reference::Grid &grid,
    TransactionApi api, FrozenBaseline baseline, Options opts)
    : RegisteredModelTransaction(registry, grid, std::move(api), baseline, opts,
                                 ConstructorSource{}) {}

RegisteredModelTransaction::RegisteredModelTransaction(
    const model_reference::Registry &registry, const model_reference::Grid &grid,
    TransactionApi api, FrozenBaseline baseline, Options opts,
    const ConstructorSource &expected_source)
    : registry_(registry.snapshot()), grid_(grid), api_(std::move(api)),
      baseline_(baseline), opts_(opts), owner_id_(std::this_thread::get_id()),
      instance_id_(mint_instance_id()), expected_source_issuer_(expected_source.issuer_),
      expected_source_lifetime_(expected_source.lifetime_) {
  registry_.freeze();
  // E03：构造**不**宣称任何模型已应用。applied_generation_ 保持 0，
  // model_consistent_ 保持 false。必须由 adopt_constructor_fact() 显式采用。
}

bool RegisteredModelTransaction::owner_thread() const { return on_owner(); }

bool RegisteredModelTransaction::on_owner() const { return std::this_thread::get_id() == owner_id_; }

void RegisteredModelTransaction::fault(const std::string &why) {
  faulted_ = true;
  model_consistent_ = false;
  start_closing(why);
}

void RegisteredModelTransaction::start_closing(const std::string &why) {
  closing_ = true;
  if (closing_reason_.empty()) closing_reason_ = why;
  for (auto &record : records_) record.used = false;
}

// ---- E03：bootstrap 来自受检构造回执 ----------------------------------
bool RegisteredModelTransaction::adopt_constructor_fact(
    std::uint64_t generation, const ConstructorSource &source,
    std::uint64_t first_job_target_tick, std::string *reason) {
  const auto fail = [&](const char *why) {
    if (reason) *reason = why;
    return false;
  };
  if (!on_owner()) return fail("wrong_owner_thread");
  if (faulted_) return fail("transaction_faulted");
  if (closing_) return fail("transaction_closing");
  if (applying_) return fail("transaction_apply_in_progress");
  // E03f：默认关闭时不得采用任何模型事实。
  // 否则默认关闭的角色仅凭构造回执就获得"模型一致"的能力，
  // 绕过 Options::model_switch_enabled 这道门。
  if (!opts_.model_switch_enabled) return fail("model_switch_disabled");

  // E03a：构造失败必须让事务**中毒**，而不只是"这次不采用"。
  // 否则后继 apply 会继续对一个可能根本不存在的 capsule 调 setter。
  // R02：来源必须可信 —— 签发者非零、构造线程与本事务同为 owner、
  // 且那次 apply 真的成功并真的进入了 native setter。
  if (source.issuer_ == 0 || expected_source_issuer_ == 0)
    return fail("constructor_source_missing_issuer");
  if (source.owner_ != std::this_thread::get_id()) return fail("constructor_source_wrong_owner_thread");
  if (source.issuer_ != expected_source_issuer_ || source.lifetime_.owner_before(expected_source_lifetime_) ||
      expected_source_lifetime_.owner_before(source.lifetime_)) return fail("constructor_source_wrong_raw");
  if (source.lifetime_.expired() || expected_source_lifetime_.expired())
    return fail("constructor_source_expired");
  if (!source.native_called_) return fail("constructor_source_setter_not_entered");
  if (!source.applied_ok_) {
    fault("constructor_apply_failed");
    return fail("constructor_apply_not_ok");
  }
  // E03b：bootstrap 是一次性事实，不得重复采用
  if (adopted_) return fail("constructor_fact_already_adopted");
  // E03c：任何 runtime 应用之后都不得再声称构造事实（否则会把
  //        applied_generation_ 从 2 回滚到 1，而 native 实际还是新模型）
  if (runtime_applications_ > 0) return fail("constructor_fact_after_runtime_apply");
  // E03d：构造采用的代必须覆盖首个 Job 的 target，否则它永远服务不了第一拍
  if (generation == 0) return fail("zero_generation");

  const model_reference::Entry *reg = registry_.find(generation);
  if (!reg) return fail("generation_not_in_registry");
  if (generation != 1) return fail("constructor_generation_not_g1");
  if (model_reference::Registry::content_digest(reg->content) !=
      model_reference::Registry::content_digest(model_reference::m0_content()))
    return fail("constructor_registered_g1_not_M0");

  // 内容必须与登记表那一代逐位一致
  if (model_reference::Registry::content_digest(reg->content) !=
      model_reference::Registry::content_digest(source.content_))
    return fail("constructor_content_differs_from_registry");

  // E03e：被采用的代必须能覆盖首个 Job 的 target（默认 1）。
  // 两种不覆盖都要拒绝：
  //   * target 早于该代的 first_target_tick（例如 g2 从 6 开始、首个 Job 是 1）；
  //   * target 晚于该代的 last_target_tick（有界代）。
  // 开放式代只受"不早于 first"约束。
  if (first_job_target_tick < reg->first_target_tick)
    return fail("constructor_generation_does_not_cover_first_job");
  if (!reg->open_ended() && first_job_target_tick > reg->last_target_tick)
    return fail("constructor_generation_does_not_cover_first_job");

  // 摘要外字段必须与冻结基线逐位一致
  if (!baseline_.bit_equal(source.baseline_)) return fail("frozen_baseline_mismatch");

  // 通过：采用构造事实。**不调用 setter** —— 那会变成用 setter 证明 setter。
  applied_generation_ = generation;
  model_consistent_ = true;
  adopted_ = true;
  adopted_issuer_ = source.issuer_;
  ++bootstrap_applications_;
  if (reason) reason->clear();
  return true;
}

// ---- E02：prepare 绑定真实 Job ----------------------------------------
// ---- R01/R02：句柄记录管理 -------------------------------------------
BoundRecord *RegisteredModelTransaction::record_of(BoundHandle h) {
  if (h.issuer_ != instance_id_ || h.id == 0 || h.id > kMaxPending || !h.serial_)
    return nullptr;
  BoundRecord &r = records_[h.id - 1];
  return r.issue_serial == h.serial_ ? &r : nullptr;
}

const BoundRecord *RegisteredModelTransaction::record_of(BoundHandle h) const {
  if (h.issuer_ != instance_id_ || h.id == 0 || h.id > kMaxPending || !h.serial_)
    return nullptr;
  const BoundRecord &r = records_[h.id - 1];
  return r.issue_serial == h.serial_ ? &r : nullptr;
}

// 提交新一代之后，所有更低代的未消费记录一律退休：不允许回滚到旧代。
void RegisteredModelTransaction::retire_below(std::uint64_t generation) {
  for (BoundRecord &r : records_)
    if (r.used && !r.consumed && r.generation < generation) {
      r.retired = true;
      r.used = false;
    }
}

Selection RegisteredModelTransaction::select_job_model_(const Axes &job_axes,
                                                         const Grid &query_grid,
                                                         std::uint64_t target_tick) const {
  Selection sel = registry_.resolve(grid_, query_grid, target_tick, {true});
  if (!sel) {
    sel.reason = "resolve:" + sel.reason;
    return sel;
  }
  if (job_axes.schedule != query_grid.schedule_generation || job_axes.epoch != query_grid.clock_epoch)
    return {false, 0, "job_axes_do_not_match_query_grid"};
  if (job_axes.model != sel.generation)
    return {false, 0, "job_model_not_equal_expected"};
  if (sel.generation < applied_generation_)
    return {false, 0, "generation_retired"};
  return sel;
}

// ---- R01：prepare 写入内部记录，只返回句柄 ----------------------------
PreparedOutcome RegisteredModelTransaction::prepare(
    const JobIdentity &identity, const Axes &job_axes, const Grid &query_grid,
    std::uint64_t job_id, std::uint64_t target_tick, std::int64_t now_ns,
    std::int64_t original_deadline_ns, const std::array<double, 126> &reference,
    double initial_yaw) {
  PreparedOutcome out;
  const auto fail = [&](const std::string &why) {
    out.accepted = false;
    out.reason = why;
    return out;
  };

  if (!opts_.model_switch_enabled) return fail("model_switch_disabled");
  if (!on_owner()) return fail("wrong_owner_thread");
  if (faulted_) return fail("transaction_faulted");
  if (closing_) return fail("transaction_closing");
  if (applying_) return fail("transaction_apply_in_progress");
  if (!job_id) return fail("zero_job_id");
  // R01：完整 Job 身份必须齐全（134 收了字段却没有入口，探针里全空仍 Ready）
  if (identity.run_id.empty() || identity.boot_id.empty() ||
      identity.contract_hash.empty() || identity.nominal_hash.empty() ||
      identity.worker_instance.empty())
    return fail("incomplete_job_identity");
  if (context_bound_ &&
      (identity.run_id != context_.run_id || identity.boot_id != context_.boot_id ||
       identity.contract_hash != context_.contract_hash ||
       identity.nominal_hash != context_.nominal_hash ||
       identity.worker_instance != context_.worker_instance))
    return fail("job_identity_changed");

  if (now_ns > original_deadline_ns) return fail("deadline_expired_before_prepare");

  // 用 Job 自己的 query grid 解析
  const Selection sel = select_job_model_(job_axes, query_grid, target_tick);
  if (!sel) return fail(sel.reason);
  // The single-owner Source issues monotonically increasing Job ids. Rejected
  // prepares do not advance this mark; accepted Jobs cannot be issued twice.
  if (job_id <= issued_job_high_water_) return fail("job_already_issued_or_older");
  if (!next_handle_id_) return fail("handle_serials_exhausted");

  const model_reference::Entry *reg = registry_.find(sel.generation);
  if (!reg) return fail("generation_not_in_registry");

  // R02：有界槽位。满了显式拒绝，不静默淘汰（淘汰对调用方不可见）。
  std::size_t slot = kMaxPending;
  for (std::size_t i = 0; i < kMaxPending; ++i)
    if (!records_[i].used) { slot = i; break; }
  if (slot == kMaxPending) return fail("pending_slots_full");

  BoundRecord &r = records_[slot];
  r = BoundRecord{};            // 清空槽位
  r.used = true;
  r.run_id = identity.run_id;
  r.boot_id = identity.boot_id;
  r.contract_hash = identity.contract_hash;
  r.nominal_hash = identity.nominal_hash;
  r.worker_instance = identity.worker_instance;
  r.job_id = job_id;
  r.target_tick = target_tick;
  r.job_axes = job_axes;
  r.query_grid = query_grid;
  r.original_deadline_ns = original_deadline_ns;
  r.reference = reference;
  r.initial_yaw = initial_yaw;
  r.generation = sel.generation;
  r.content = reg->content;
  r.content_digest = model_reference::Registry::content_digest(reg->content);
  r.table_digest = registry_.table_digest();
  r.plan_digest = registry_.runtime_plan_digest_json_v1(grid_);
  r.plan_fingerprint = registry_.plan_fingerprint_be64_v1(grid_);

  r.issue_serial = next_handle_id_;
  next_handle_id_ = next_handle_id_ == std::numeric_limits<std::uint64_t>::max()
                        ? 0 : next_handle_id_ + 1;
  out.handle = BoundHandle(instance_id_, slot + 1, r.issue_serial);
  issued_job_high_water_ = job_id;
  if (!context_bound_) { context_ = identity; context_bound_ = true; }
  out.accepted = true;
  return out;
}

// ---- apply：消费 BoundPreparedJob（E01/E02/E04/E05） -------------------
// ---- R01/R02/R03：apply 只消费内部记录 --------------------------------
Outcome RegisteredModelTransaction::consume_entry_refusal(
    const JobIdentity &identity, const Axes &job_axes, const Grid &query_grid,
    std::uint64_t job_id, std::uint64_t target_tick, std::int64_t now_ns,
    std::int64_t original_deadline_ns) {
  Outcome out;
  const auto refuse = [&](const std::string &why) {
    out.disposition = Disposition::RefusedBeforeApply;
    out.reason = why;
    out.model_consistent = model_consistent_;
    out.applied_generation = applied_generation_;
    out.can_continue_this_job = false;
    return out;
  };
  // 1. model-off 必须完全不变：不改任何状态。
  if (!opts_.model_switch_enabled) return refuse("model_switch_disabled");
  // 2. 线程与状态门。
  if (!on_owner()) return refuse("wrong_owner_thread");
  if (faulted_) {
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "transaction_already_faulted";
    out.closing = true;
    return out;
  }
  if (closing_) { out = refuse("transaction_closing"); out.closing = true; return out; }
  if (applying_) return refuse("transaction_apply_in_progress");
  // 3. 身份必须齐全（无效输入不前移高水位）。
  if (!job_id) return refuse("zero_job_id");
  if (identity.run_id.empty() || identity.boot_id.empty() ||
      identity.contract_hash.empty() || identity.nominal_hash.empty() ||
      identity.worker_instance.empty())
    return refuse("incomplete_job_identity");
  if (context_bound_ &&
      (identity.run_id != context_.run_id || identity.boot_id != context_.boot_id ||
       identity.contract_hash != context_.contract_hash ||
       identity.nominal_hash != context_.nominal_hash ||
       identity.worker_instance != context_.worker_instance))
    return refuse("job_identity_changed");
  // 4. 过期是该方法的前置条件：未过期不得消费。
  if (now_ns <= original_deadline_ns) return refuse("not_expired");
  // Resolve the same registered model as prepare() before any id or context is
  // consumed. An invalid grid, axis, target or retired generation is not an
  // eligible expired Job.
  const Selection sel = select_job_model_(job_axes, query_grid, target_tick);
  if (!sel) return refuse(sel.reason);
  if (!registry_.find(sel.generation)) return refuse("generation_not_in_registry");
  // 5. 重复/更旧的 Job ID：拒绝且不前移。
  if (job_id <= issued_job_high_water_) return refuse("job_already_issued_or_older");
  // 6. 至此才消费。
  issued_job_high_water_ = job_id;
  if (!context_bound_) { context_ = identity; context_bound_ = true; }
  out.disposition = Disposition::RefusedBeforeApply;
  out.reason = "expired_before_entry";
  out.model_consistent = model_consistent_;
  out.applied_generation = applied_generation_;
  out.can_continue_this_job = false;
  out.closing = false;
  out.facts = facts_;
  out.refusal.origin = RefusalOrigin::OwnedInitialDeadline;
  out.refusal.fault = RefusalFault::Expiry;
  out.refusal.job_id = job_id;
  out.refusal.original_deadline_ns = original_deadline_ns;
  out.refusal.checked_ns = now_ns;
  out.refusal.applied_generation = applied_generation_;
  out.refusal.model_consistent = model_consistent_;
  out.refusal.closing = false;
  // R07: this Job never entered preparation, so "preparation is fully
  // accounted for" is vacuously TRUE. Leaving the default false would block
  // every recoverable entry refusal at the recoverability gate.
  out.refusal.preparation_known_complete = true;
  out.refusal.c_solve_entries_this_job = 0;
  out.refusal.c_graph_mutated = false;
  out.refusal.reset_applied = false;
  out.refusal.once_consumed = false;
  return out;
}

Outcome RegisteredModelTransaction::apply(BoundHandle handle, StopPredicate local_stop,
                                         ExpiryPredicate expired,
                                         std::int64_t now_ns) {
  Outcome out;
  BoundRecord *rec = nullptr;   // R01：内部记录，后面的谓词与提交都用它

  // R03(b)：谓词异常不能留下"旧模型仍一致"的假状态。
  // 用 current_phase 记录"已经走到哪一步"，异常时据此选终局。
  enum class Phase { BeforeTouch, Touching, Committed };
  Phase phase = Phase::BeforeTouch;

  const auto stop_now = [&]() -> bool {
    if (!local_stop) return false;
    return local_stop();          // 抛出由外层统一处理
  };
  const auto deadline_passed = [&]() {
    return rec && now_ns > rec->original_deadline_ns;
  };
  const auto expired_now = [&]() -> bool {
    if (deadline_passed()) return true;
    if (!expired) return false;
    return expired();             // 抛出由外层统一处理
  };

  // 统一的"谓词异常"终局
  const auto predicate_exception = [&]() -> Outcome {
    Outcome o;
    o.facts = facts_;
    // 谓词抛出是本事务唯一可归因的 PredicateFault：它必须在事实里，
    // 而不是靠事后匹配 reason 文本。
    o.refusal.origin = RefusalOrigin::PredicateFault;
    o.refusal.fault = RefusalFault::Unknown;
    o.refusal.job_id = rec ? rec->job_id : 0;
    o.refusal.original_deadline_ns = rec ? rec->original_deadline_ns : 0;
    o.refusal.checked_ns = now_ns;
    o.refusal.applied_generation = applied_generation_;
    o.refusal.model_consistent = (phase == Phase::Committed);
    o.refusal.model_terminal = true;
    o.refusal.c_solve_entries_this_job = 0;
    if (phase == Phase::Committed) {
      // 已一致提交：保留真实新模型事实，但本 Job 不许继续
      o.disposition = Disposition::FaultedAfterTouch;
      o.reason = "predicate_threw_after_consistent_commit";
      o.model_consistent = true;
      o.applied_generation = applied_generation_;
      o.identity_published = true;
      o.cpp_state_synced = true;
      o.can_continue_this_job = false;
      o.closing = true;
      start_closing(o.reason);
    } else if (phase == Phase::Touching) {
      // 已开始修改但未一致提交：状态不确定
      fault("predicate_threw_during_touch");
      o.disposition = Disposition::FaultedAfterTouch;
      o.reason = "predicate_threw_during_touch";
      o.applied_generation = applied_generation_;
      o.closing = true;
    } else {
      // 触碰前：原模型不变
      o.disposition = Disposition::RefusedBeforeApply;
      o.reason = "predicate_threw_before_touch";
      o.model_consistent = model_consistent_;
      o.applied_generation = applied_generation_;
      o.can_continue_this_job = false;
      o.closing = true;
      start_closing(o.reason);
    }
    return o;
  };

  const auto refuse = [&](const std::string &why) {
    out.disposition = Disposition::RefusedBeforeApply;
    out.reason = why;
    out.model_consistent = model_consistent_;
    out.applied_generation = applied_generation_;
    out.facts = facts_;
    return out;
  };

  // ---- 前置（不读任何外部可写内容） -----------------------------------
  if (!on_owner()) return refuse("wrong_owner_thread");
  if (faulted_) {
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "transaction_already_faulted";
    out.closing = true;
    out.facts = facts_;
    return out;
  }
  if (closing_) {
    out = refuse("transaction_closing:" + closing_reason_);
    out.closing = true;
    return out;
  }
  if (applying_) return refuse("transaction_apply_in_progress");
  if (!opts_.model_switch_enabled) {
    out = refuse("model_switch_disabled");
    out.can_continue_this_job = true;   // 关闭模式下由原路径继续
    return out;
  }
  if (adopted_ && expected_source_lifetime_.expired()) {
    model_consistent_ = false;
    start_closing("constructor_source_expired_before_apply");
    out = refuse("constructor_source_expired_before_apply");
    out.closing = true;
    return out;
  }

  // R01/R02：句柄必须是本事务发放的、未消费、未退休的记录
  rec = record_of(handle);
  if (!rec) return refuse("unknown_handle");
  if (rec->consumed) return refuse("handle_already_consumed");
  if (rec->retired) return refuse("generation_retired");
  if (!rec->used) return refuse("inactive_handle");
  if (rec->generation < applied_generation_) {
    rec->retired = true;
    rec->used = false;
    return refuse("generation_retired");
  }
  rec->consumed = true;
  applying_ = true;
  RecordLease lease{*rec, applying_};
  if (!adopted_) return refuse("bootstrap_not_adopted");

  // 身份必须与当前表一致（防 prepare 之后换表）
  if (rec->table_digest != registry_.table_digest())
    return refuse("table_digest_changed_since_prepare");
  if (rec->plan_digest != registry_.runtime_plan_digest_json_v1(grid_))
    return refuse("plan_digest_changed_since_prepare");

  // R01：**重算**内容摘要与登记表比对 —— 不读任何外部自报字段
  const model_reference::Entry *reg = registry_.find(rec->generation);
  if (!reg) return refuse("generation_not_in_registry");
  if (model_reference::Registry::content_digest(rec->content) !=
      model_reference::Registry::content_digest(reg->content))
    return refuse("record_content_differs_from_registry");
  if (rec->content_digest != model_reference::Registry::content_digest(reg->content))
    return refuse("record_digest_inconsistent");

  // 消费：无论后续成功与否都不能再用第二次
  // Consumption was committed before validation and is released by RecordLease.

  // ---- E01：同代也要先过 stop / expiry -------------------------------
  const bool same_generation =
      (rec->generation == applied_generation_ && model_consistent_);

  try {
    if (stop_now()) {
      out.disposition = Disposition::RefusedBeforeApply;
      out.reason = same_generation ? "same_generation_stop_refused"
                                   : "stop_before_capsule_touch";
      out.model_consistent = model_consistent_;
      out.applied_generation = applied_generation_;
      out.can_continue_this_job = false;
      out.closing = true;
      start_closing(out.reason);
      out.bootstrap = same_generation && (runtime_applications_ == 0);
      out.facts = facts_;
      return out;
    }
    if (expired_now()) {
      out.disposition = Disposition::RefusedBeforeApply;
      out.reason = same_generation ? "same_generation_expired_refused"
                                   : "expired_before_capsule_touch";
      // R07/K05: expiry before the capsule is touched.
      out.refusal.origin = RefusalOrigin::TransactionPreExpiry;
      out.refusal.fault = RefusalFault::Expiry;
      out.refusal.job_id = rec->job_id;
      out.refusal.original_deadline_ns = rec->original_deadline_ns;
      out.refusal.checked_ns = now_ns;
      out.refusal.model_consistent = model_consistent_;
      out.refusal.applied_generation = applied_generation_;
      out.refusal.preparation_known_complete = true;
      out.refusal.c_solve_entries_this_job = 0;
      out.model_consistent = model_consistent_;
      out.applied_generation = applied_generation_;
      out.can_continue_this_job = false;
      out.bootstrap = same_generation && (runtime_applications_ == 0);
      out.facts = facts_;
      return out;
    }
  } catch (...) {
    return predicate_exception();
  }

  if (same_generation) {
    out.disposition = Disposition::ModelConsistentReady;
    out.model_consistent = true;
    out.applied_generation = applied_generation_;
    out.bootstrap = (runtime_applications_ == 0);
    out.can_continue_this_job = true;
    out.reason = "same_generation_no_reapply";
    out.facts = facts_;
    return out;
  }

  // ---- E04/E05：setter → reset → sync ---------------------------------
  phase = Phase::Touching;
  const Content &content = rec->content;   // R01：内容取自内部记录

  const CallOutcome setter = call_setter(api_.set_global, content, facts_);
  if (!setter.entered) {
    fault("no_setter");
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "setter_not_bound";
    out.applied_generation = applied_generation_;
    out.closing = true;
    out.facts = facts_;
    return out;
  }
  if (!setter.returned) {
    fault("setter_threw");
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "setter_threw";
    out.applied_generation = applied_generation_;
    out.closing = true;
    out.facts = facts_;
    return out;
  }
  if (!setter.result.ok) {
    fault("setter_rejected");
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "setter_rejected:code=" + std::to_string(setter.result.code);
    out.applied_generation = applied_generation_;
    out.closing = true;
    out.facts = facts_;
    return out;
  }
  if (!setter.result.native_called) {
    fault("setter_reported_ok_without_native_entry");
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "setter_reported_ok_without_native_entry";
    out.applied_generation = applied_generation_;
    out.closing = true;
    out.facts = facts_;
    return out;
  }

  try {
    if (stop_now()) {
      fault("stop_after_setter_before_reset");
      out.disposition = Disposition::FaultedAfterTouch;
      out.reason = "stop_after_setter_before_reset";
      out.applied_generation = applied_generation_;
      out.closing = true;
      start_closing(out.reason);
      out.facts = facts_;
      return out;
    }
  } catch (...) {
    return predicate_exception();
  }

  const CallOutcome reset = call_reset(api_.reset, 1, facts_);
  if (!reset.entered) {
    fault("no_reset");
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "reset_not_bound";
    out.applied_generation = applied_generation_;
    out.closing = true;
    out.facts = facts_;
    return out;
  }
  if (!reset.returned) {
    fault("reset_threw");
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "reset_threw";
    out.applied_generation = applied_generation_;
    out.closing = true;
    out.facts = facts_;
    return out;
  }
  if (!reset.result.ok) {
    fault("reset_failed");
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "reset_failed:code=" + std::to_string(reset.result.code);
    out.applied_generation = applied_generation_;
    out.closing = true;
    out.facts = facts_;
    return out;
  }
  if (!reset.result.native_called) {
    fault("reset_reported_ok_without_native_entry");
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "reset_reported_ok_without_native_entry";
    out.applied_generation = applied_generation_;
    out.closing = true;
    out.facts = facts_;
    return out;
  }

  try {
    if (stop_now()) {
      fault("stop_after_reset_before_sync");
      out.disposition = Disposition::FaultedAfterTouch;
      out.reason = "stop_after_reset_before_sync";
      out.applied_generation = applied_generation_;
      out.closing = true;
      out.facts = facts_;
      return out;
    }
  } catch (...) {
    return predicate_exception();
  }

  const CallOutcome sync = call_sync(api_.sync_cpp_state, content, facts_);
  if (!sync.entered) {
    fault("no_sync_cpp_state");
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "sync_not_bound";
    out.applied_generation = applied_generation_;
    out.closing = true;
    out.facts = facts_;
    return out;
  }
  if (!sync.returned) {
    fault("sync_threw");
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "sync_threw";
    out.applied_generation = applied_generation_;
    out.closing = true;
    out.facts = facts_;
    return out;
  }
  if (!sync.result.ok) {
    fault("sync_failed");
    out.disposition = Disposition::FaultedAfterTouch;
    out.reason = "sync_failed:code=" + std::to_string(sync.result.code);
    out.applied_generation = applied_generation_;
    out.closing = true;
    out.facts = facts_;
    return out;
  }

  // The touching phase must consult BOTH predicates. The expiry predicate was
  // read only before the capsule was touched and again after a consistent
  // commit, so an expiry armed inside the setter surfaced at the post-commit
  // site and was reported as a different phase than the one it really crossed.
  // The phase is part of the refusal contract (F13/F14/F15), so the consultation
  // sits here: after the three real entries, before the identity is published.
  // The evaluation result is deliberately DISCARDED. A predicate that merely
  // reports "expired" must still let the frozen policy complete the consistent
  // commit and be refused afterwards at TransactionCommittedExpiry (F11/F12);
  // only a predicate that THROWS has crossed the touching phase, and that is the
  // fact F14 requires. Treating a plain `true` as a mid-touch fault would move
  // F11/F12 into the wrong phase and lose the committed generation.
  try {
    (void)expired_now();
  } catch (...) {
    return predicate_exception();
  }

  // ---- 三步全成功：提交新身份，并让更低代的未消费记录退休 -------------
  applied_generation_ = rec->generation;
  model_consistent_ = true;
  ++runtime_applications_;
  phase = Phase::Committed;
  retire_below(applied_generation_);

  out.identity_published = true;
  out.cpp_state_synced = true;
  out.model_consistent = true;
  out.applied_generation = applied_generation_;
  out.facts = facts_;

  try {
    if (stop_now()) {
      out.disposition = Disposition::AppliedThenStopped;
      out.reason = "stop_after_consistent_commit";
      out.can_continue_this_job = false;
      out.closing = true;
      start_closing(out.reason);
      return out;
    }
    if (expired_now()) {
      out.disposition = Disposition::AppliedButJobExpired;
      out.reason = "expired_after_consistent_commit";
      // R07/K05: committed, then the Job expired. A DIFFERENT phase from the
      // pre-touch one; collapsing the two was the K05 defect.
      out.refusal.origin = RefusalOrigin::TransactionCommittedExpiry;
      out.refusal.fault = RefusalFault::Expiry;
      out.refusal.job_id = rec->job_id;
      out.refusal.original_deadline_ns = rec->original_deadline_ns;
      out.refusal.checked_ns = now_ns;
      out.refusal.model_consistent = true;
      out.refusal.applied_generation = applied_generation_;
      out.refusal.preparation_known_complete = true;
      out.refusal.c_solve_entries_this_job = 0;
      out.can_continue_this_job = false;
      out.closing = false;
      return out;
    }
  } catch (...) {
    return predicate_exception();
  }

  out.disposition = Disposition::ModelConsistentReady;
  out.reason = "applied";
  out.can_continue_this_job = true;
  return out;
}

}  // namespace model_txn
