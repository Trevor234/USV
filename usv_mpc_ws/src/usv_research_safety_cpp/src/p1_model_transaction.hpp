// SPDX-License-Identifier: MIT
//
// registered_model_transaction_v1.hpp — owner 串行的模型事务（I02）。
//
// 来源：第132批 A04（四格 guard / 类型化处置 / 受检 reset / 摘要外字段）、
//       A02（两阶段提交）、第133批 I00 的 T02/T03/T04。
//
// 本头**不 include** 130 的 raw_backend_v1.hpp / owned_cold_backend.hpp，也不链接
// acados。I02 用**受控 Api 替身**（两个 std::function）证明状态机与线程归属，
// 真实 SDK 留到 I03。
//
// 关键约束（不得改）：
//   * 三个事实分开：只读访问 / 首次 native 修改 / 真 C solve。
//     **不得**用单个 native_touched 布尔同时表示它们。
//   * 模型事务**不承担** candidate 生成 / 发布 / completed 计数（T02）。
//     原 Worker 有 W4 生成后丢弃路径，事务无权承诺"已发布"。
//   * `Ok` 只表示"模型一致就绪"，不是"已发布"。
//   * 冻结终局：setter 成功后、reset/C++ 同步前 stop = Faulted；
//     一致提交后**仅**过期 = 非终端拒绝、保留新模型、无 solve；
//     一致提交后 stop = 保留事实、无 solve、owner 关闭；
//     stop 与 expiry 同时 = stop 优先（终局），因为 stop 决定后续是否还服务。
//   * reset 必须消费真实返回值，且**先 reset 成功再清** warm_/xw_/uw_。
//   * 默认关闭：`Options::model_switch_enabled` 默认 false。
//
#pragma once

#include "p1_model_reference.hpp"

#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>

namespace startup_replay { class RawBackend; }
namespace p1 { class EngineSession; }

namespace model_txn {

using model_reference::Axes;
using model_reference::Content;
using model_reference::Grid;
using model_reference::Selection;

// ---- 受控 Api 替身 ----------------------------------------------------
// 形状对齐 p_global_apply.hpp 的 apply 返回语义，但**不 link** 它。
struct ApiResult {
  bool ok = false;
  int code = 0;          // 非 0 表示拒绝/故障
  bool native_called = false;
};

struct TransactionApi {
  // 对应 usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies
  std::function<ApiResult(const Content &)> set_global;
  // 对应 usv_dyn_nmpc_acados_reset
  std::function<ApiResult(int)> reset;
  // E04：C++ 侧参数与 warm 缓存同步。**必须**是独立操作，
  // 不得藏进 reset lambda —— 否则"reset 成功 ≠ C++ 已同步"这条永远无法区分。
  // 由 Raw 内部实现；真实接线时它改 p_ 并清 warm_/xw_/uw_。
  std::function<ApiResult(const Content &)> sync_cpp_state;
};

// ---- 三个分开的事实（T03） -------------------------------------------
// E05：call facts 不能是自增标签。四层分开记录：
//   attempt      —— 事务决定要调
//   entry        —— 回调真的被调用（回调存在且进入）
//   returned     —— 回调正常返回（没抛）
//   reported_ok  —— 回调报告 ok（它自己说成功）
// 一个不存在的回调：attempt=1, entry=0, returned=0, reported_ok=0。
struct TouchFacts {
  unsigned capsule_reads = 0;        // 只读访问次数
  unsigned native_mutations = 0;     // 正常返回后，回调报告真实 setter 入口的次数
  unsigned setter_native_outcome_unknown = 0; // 回调抛出时不能推断 C 是否已进入
  unsigned reset_calls = 0;          // 正常返回后，回调报告真实 reset 入口的次数
  unsigned reset_native_outcome_unknown = 0;
  unsigned sync_calls = 0;           // **实际进入** sync_cpp_state 的次数
  unsigned c_solve_entries = 0;      // 真 C solve 进入次数（本批恒为 0）

  unsigned setter_attempts = 0;
  unsigned setter_entries = 0;
  unsigned setter_returned = 0;
  unsigned setter_reported_ok = 0;
  unsigned reset_attempts = 0;
  unsigned reset_entries = 0;
  unsigned reset_returned = 0;
  unsigned reset_reported_ok = 0;
  unsigned sync_attempts = 0;
  unsigned sync_entries = 0;
  unsigned sync_returned = 0;
  unsigned sync_reported_ok = 0;

  // 明确禁止用单布尔概括上面各项
  static constexpr bool single_boolean_forbidden = true;
};

// ---- R07：类型化拒绝 ---------------------------------------------------
// 这一层不 include raw_backend_v1.hpp / owned_cold_backend.hpp（见文件头），
// 而 raw_backend_v1.hpp include 本头，所以具名类型只能定义在这里。
//
// K09：原因用**枚举**；审计文字由异常对象自己拥有的 std::string 承载。
// 一律不保存外部指针 —— 调用方传 std::string::c_str() 时会悬空，
// 而 std::runtime_error 只复制自己的文本，不保护外面的字段。
enum class RefusalOrigin {
  None,
  // 三个期限入口
  OwnedInitialDeadline,      // owned_cold_backend.hpp 的 try 外入口
  InternalInvokeDeadline,    // invoke lambda 内
  RawFinalGuard,             // Raw 紧邻 acados_solve 的最终 guard
  // K03：W2 已验证释放后才过期 —— 与 wait_failed 必须是不同事实
  W2VerifiedReleaseExpired,
  // 恒终端
  W2DeadlineMismatch, W2Gate, PrepareFailure, PredicateFault, InvalidInput,
  // K05：事务自身的过期，必须与 stop 区分
  TransactionCommittedExpiry, TransactionPreExpiry,
  Stop
};
enum class RefusalFault { None, Stop, Expiry, WaitFailed, Unknown };

inline const char *to_string(RefusalOrigin o) {
  switch (o) {
    case RefusalOrigin::None: return "none";
    case RefusalOrigin::OwnedInitialDeadline: return "owned_initial_deadline";
    case RefusalOrigin::InternalInvokeDeadline: return "internal_invoke_deadline";
    case RefusalOrigin::RawFinalGuard: return "raw_final_guard";
    case RefusalOrigin::W2VerifiedReleaseExpired: return "w2_verified_release_expired";
    case RefusalOrigin::W2DeadlineMismatch: return "w2_deadline_mismatch";
    case RefusalOrigin::W2Gate: return "w2_gate";
    case RefusalOrigin::PrepareFailure: return "prepare_failure";
    case RefusalOrigin::PredicateFault: return "predicate_fault";
    case RefusalOrigin::InvalidInput: return "invalid_input";
    case RefusalOrigin::TransactionCommittedExpiry: return "transaction_committed_expiry";
    case RefusalOrigin::TransactionPreExpiry: return "transaction_pre_expiry";
    case RefusalOrigin::Stop: return "stop";
  }
  return "unknown";
}
inline const char *to_string(RefusalFault f) {
  switch (f) {
    case RefusalFault::None: return "none";
    case RefusalFault::Stop: return "stop";
    case RefusalFault::Expiry: return "expiry";
    case RefusalFault::WaitFailed: return "wait_failed";
    case RefusalFault::Unknown: return "unknown";
  }
  return "unknown";
}

struct RefusalFacts {
  RefusalOrigin origin = RefusalOrigin::None;
  RefusalFault fault = RefusalFault::None;
  std::uint64_t job_id = 0;
  std::int64_t original_deadline_ns = 0;
  std::int64_t checked_ns = 0;
  std::uint64_t applied_generation = 0;
  bool model_consistent = false;
  bool closing = false;
  bool model_terminal = false;
  // 由 Raw 侧按 Job 基线实测，不是推测值（§6.2）
  unsigned c_solve_entries_this_job = 0;
  bool c_graph_mutated = false;
  bool reset_applied = false;
  bool preparation_known_complete = false;
  bool once_consumed = false;
};

// 必须派生自 std::runtime_error：冻结的 test_w2_backend_wiring.cpp 有 10 处
// EXPECT_THROW(..., std::runtime_error)。派生关系与"禁止按 what() 分支"不冲突。
class Refusal : public std::runtime_error {
 public:
  explicit Refusal(RefusalFacts f, std::string audit_why)
      : std::runtime_error(std::move(audit_why)), facts_(std::move(f)) {}
  const RefusalFacts &facts() const { return facts_; }

 private:
  RefusalFacts facts_;
};

// ---- 处置（限定为模型一致性层面，T02） -------------------------------
enum class Disposition {
  // 模型一致就绪。**不**代表已发布 —— 生成/发布/丢弃归原 Worker 账目。
  ModelConsistentReady,
  // 未触碰 capsule 即拒绝（原始模型完好）
  RefusedBeforeApply,
  // 已应用真实新模型，但本 Job 在进入 C 之前已过期。**非终端**，保留新模型。
  AppliedButJobExpired,
  // 已应用真实新模型，但 stop 到达。保留模型事实，零后续 solve，owner 关闭。
  // 与 AppliedButJobExpired **必须是不同的值** —— 冻结终局要求这两条分别可对账。
  AppliedThenStopped,
  // 触碰 capsule 后的不确定故障。终端隔离。
  FaultedAfterTouch,
};

const char *to_string(Disposition d);

// ---- 结果 --------------------------------------------------------------
struct Outcome {
  Disposition disposition = Disposition::RefusedBeforeApply;
  bool model_consistent = false;      // 当前胶囊内容 == 登记内容
  std::uint64_t applied_generation = 0;  // 0 = 尚未成功应用任何代（或已完成 bootstrap）
  bool bootstrap = false;             // 本次是否走构造事实（未 setter/reset）
  bool can_continue_this_job = false; // 本 Job 是否仍可进入 solve
  bool closing = false;               // owner 是否必须关闭
  std::string reason;
  TouchFacts facts;

  // E04：新身份只有在 setter + reset + sync 全部完成之后才发布。
  // 这三个布尔让测试能断言"晚于全部同步"，而不是只看 generation 变了没有。
  bool identity_published = false;
  bool cpp_state_synced = false;

  // R07：类型化拒绝事实。默认 origin=None，对既有路径零影响。
  RefusalFacts refusal{};

  bool terminal() const {
    return disposition == Disposition::FaultedAfterTouch;
  }
};

// ---- 登记内容 ----------------------------------------------------------
// 只携带受检登记条目。**不接受完整 MpcParams** —— 那样 N/dt/T_min/T_max/dT_max
// 会绕过 30 维摘要被静默改写（R07）。
struct RegisteredEntry {
  std::uint64_t generation = 0;
  Content content{};
  std::string content_digest;   // 由 Registry::content_digest 得到
  bool valid = false;
};

// ---- 摘要外字段 --------------------------------------------------------
// 这五项**不在** 30 维内容摘要里，必须在任何 capsule 触碰前逐位断言。
struct FrozenBaseline {
  double N = 20;
  double dt = 0.2;
  double T_min = -25.0;
  double T_max = 25.0;
  double dT_max = 80.0;

  bool bit_equal(const FrozenBaseline &o) const;
};

// ---- 选项（默认关闭） --------------------------------------------------
struct Options {
  bool model_switch_enabled = false;
};

// ---- R01：外部只拿到不透明句柄 ---------------------------------------
// 134 的 `BoundPreparedJob` 把 content/deadline/target/reference/yaw/身份全部暴露给
// 调用方，`apply` 又直接消费它们。于是"绑定"只是调用方持有的数据，不是事务掌握的
// 事实 —— 复审的 10 个探针正是靠改写这些字段通过检查。
//
// Q01: payload stays private; a handle also binds its issuing instance and serial.
struct BoundHandle {
  std::uint64_t id = 0;  // Diagnostic slot number only; never an authority by itself.
  BoundHandle() = default;
  explicit operator bool() const { return id != 0 && issuer_ != 0 && serial_ != 0; }
  bool operator==(const BoundHandle &o) const {
    return id == o.id && issuer_ == o.issuer_ && serial_ == o.serial_;
  }
  bool operator!=(const BoundHandle &o) const { return !(*this == o); }

 private:
  friend class RegisteredModelTransaction;
  BoundHandle(std::uint64_t issuer, std::uint64_t slot, std::uint64_t serial)
      : id(slot), issuer_(issuer), serial_(serial) {}
  std::uint64_t issuer_ = 0;
  std::uint64_t serial_ = 0;
};

// prepare 的结果：要么给句柄，要么给原因。
struct PreparedOutcome {
  BoundHandle handle{};
  bool accepted = false;
  std::string reason;
  explicit operator bool() const { return accepted; }
};

// ---- 内部记录：只有事务能读写 ----------------------------------------
struct BoundRecord {
  bool used = false;      // 槽位已发放
  bool consumed = false;  // 已被 apply 消费（一次）
  bool retired = false;   // 已被更新的代取代
  std::uint64_t issue_serial = 0;

  std::string run_id, boot_id, contract_hash, nominal_hash, worker_instance;
  std::uint64_t job_id = 0;
  std::uint64_t target_tick = 0;
  Axes job_axes{};
  Grid query_grid{};
  std::int64_t original_deadline_ns = 0;
  std::array<double, 126> reference{};
  double initial_yaw = 0.0;

  std::uint64_t generation = 0;
  Content content{};
  std::string content_digest;

  std::string table_digest;
  std::string plan_digest;
  std::string plan_fingerprint;
};

// ---- 事务 --------------------------------------------------------------
//
// 线程归属：唯一构造线程（owner）。
class RegisteredModelTransaction {
 public:
  // Only a live RawBackend can mint a nonempty source. The issued value owns
  // neither capsule nor backend; expiration follows the Raw object's lifetime.
  class ConstructorSource {
   public:
    ConstructorSource() = default;
    std::uint64_t issuer() const { return issuer_; }
   private:
    // The online engine is the only OTHER role allowed to mint a source: it owns
    // the single capsule and the shared lifetime the source expires with.
    friend class p1::EngineSession;
    friend class startup_replay::RawBackend;
    friend class RegisteredModelTransaction;
    std::uint64_t issuer_ = 0;
    std::thread::id owner_{};
    std::weak_ptr<const std::uint64_t> lifetime_;
    Content content_{};
    FrozenBaseline baseline_{};
    bool applied_ok_ = false;
    bool native_called_ = false;
  };
  // E03：构造函数**不**宣称任何模型已应用。
  // 注册表在此被**快照**（深拷贝 + freeze），事务此后不受外部注册表变动影响（E06）。
  RegisteredModelTransaction(const model_reference::Registry &registry,
                             const model_reference::Grid &grid,
                             TransactionApi api,
                             FrozenBaseline baseline,
                             Options opts);
  RegisteredModelTransaction(const model_reference::Registry &registry,
                             const model_reference::Grid &grid,
                             TransactionApi api, FrozenBaseline baseline,
                             Options opts, const ConstructorSource &expected_source);
  RegisteredModelTransaction(const RegisteredModelTransaction &) = delete;
  RegisteredModelTransaction &operator=(const RegisteredModelTransaction &) = delete;
  RegisteredModelTransaction(RegisteredModelTransaction &&) = delete;
  RegisteredModelTransaction &operator=(RegisteredModelTransaction &&) = delete;

  // The private source contains the actual 30 values and baseline; no caller
  // supplies a self-reported digest or a separately mutable success flag.
  bool adopt_constructor_fact(std::uint64_t generation, const ConstructorSource &source,
                              std::uint64_t first_job_target_tick = 1,
                              std::string *reason = nullptr);

  // 某个 Raw 签发者是否就是本事务采用的那一个。
  bool adopted_from_issuer(std::uint64_t issuer) const {
    return adopted_ && adopted_issuer_ == issuer; }

  // 完整 Job 身份（R01：134 有这些字段却没有数据入口，探针里全空仍 Ready）
  struct JobIdentity {
    std::string run_id, boot_id, contract_hash, nominal_hash, worker_instance;
  };

  // 纯值准备：零 native 修改。R01：返回不透明句柄，内容写入内部记录。
  PreparedOutcome prepare(const JobIdentity &identity, const Axes &job_axes,
                          const Grid &query_grid, std::uint64_t job_id,
                          std::uint64_t target_tick, std::int64_t now_ns,
                          std::int64_t original_deadline_ns,
                          const std::array<double, 126> &reference,
                          double initial_yaw);

  // R07/K07：入口处过期（本 Job 从未进入 apply 语义）。
  //
  // 这是**纯值**操作：不触碰 capsule、不占 pending 槽位、不写 BoundRecord、
  // 不动 next_handle_id_、不调 api_、不 retire_below。唯一的状态副作用是
  // 前移 issued Job 高水位 —— 验收计划 §6.1 明确要求过期也要消费 Job ID。
  //
  // "先校验，后消费"的顺序不可换：无效身份/格式/未过期/重复 ID 都必须
  // 在消费之前返回，否则无效 Job 会烧掉一个 ID（M20 针对此）。
  Outcome consume_entry_refusal(const JobIdentity &identity, const Axes &job_axes,
                                const Grid &query_grid, std::uint64_t job_id,
                                std::uint64_t target_tick, std::int64_t now_ns,
                                std::int64_t original_deadline_ns);

  // 应用。遵守冻结终局。
  //
  // `local_stop` 与 `expired` 是**谓词**而不是布尔快照：真实实现要在
  // 每个检查点重新求值（stop 可能在 setter 成功之后、reset 之前到达）。
  // 传一个调用前算好的 bool 会让"setter 后 stop"这一条永远测不到。
  // 这也对应 130 的 `owned_cold_backend.hpp` 里 `stop_()` 与
  // `clock_() > current_deadline_ns_` 在每个检查点重新调用的做法。
  using StopPredicate = std::function<bool()>;
  using ExpiryPredicate = std::function<bool()>;

  // E02：只接受 prepare 返回的绑定结果，并**消费**它一次。
  // 传入未 accepted、已被消费、或与当前表身份不符的绑定都会被拒绝。
  Outcome apply(BoundHandle handle, StopPredicate local_stop,
                ExpiryPredicate expired, std::int64_t now_ns);

  // 只读：当前已应用代（0 = 尚未应用，除非 bootstrap）
  std::uint64_t applied_generation() const { return applied_generation_; }
  bool model_consistent() const { return model_consistent_; }
  bool faulted() const { return faulted_; }
  bool closing() const { return closing_; }
  bool owner_thread() const;
  const TouchFacts &facts() const { return facts_; }

  // 供测试观察：bootstrap 与 runtime 应用计数分开（T04）
  unsigned bootstrap_applications() const { return bootstrap_applications_; }
  unsigned runtime_applications() const { return runtime_applications_; }

  // R01/R02：有界内部账本容量（公开，供测试与外部容量规划读取）。
  static constexpr std::size_t kMaxPending = 4;

  // E06：本事务持有的是自己的快照。测试用它断言"外部注册表再改也影响不到我"。
  std::size_t registry_size() const { return registry_.size(); }
  std::string registry_table_digest() const { return registry_.table_digest(); }

 private:
  bool on_owner() const;
  void fault(const std::string &why);
  void start_closing(const std::string &why);
  // Both ordinary preparation and initial expiry validate the same registered
  // grid, target and model generation before issuing or consuming a Job id.
  Selection select_job_model_(const Axes &job_axes, const Grid &query_grid,
                              std::uint64_t target_tick) const;

  // E06：持**值快照**，不是 const&。外部注册表之后再改，也影响不到本事务。
  model_reference::Registry registry_;
  model_reference::Grid grid_;
  TransactionApi api_;
  FrozenBaseline baseline_;
  Options opts_;
  const std::thread::id owner_id_;
  const std::uint64_t instance_id_;
  const std::uint64_t expected_source_issuer_;
  const std::weak_ptr<const std::uint64_t> expected_source_lifetime_;

  std::uint64_t applied_generation_ = 0;
  bool model_consistent_ = false;
  std::array<BoundRecord, kMaxPending> records_{};
  std::uint64_t next_handle_id_ = 1;  // Monotonic issue serial, never a slot index.
  JobIdentity context_;
  bool context_bound_ = false;
  std::uint64_t issued_job_high_water_ = 0;
  bool applying_ = false;
  bool closing_ = false;
  std::string closing_reason_;
  bool adopted_ = false;                // E03：bootstrap 只能采用一次
  std::uint64_t adopted_issuer_ = 0;    // R02：采用事实的签发者

  BoundRecord *record_of(BoundHandle h);
  const BoundRecord *record_of(BoundHandle h) const;
  void retire_below(std::uint64_t generation);
  bool faulted_ = false;
  unsigned bootstrap_applications_ = 0;
  unsigned runtime_applications_ = 0;
  TouchFacts facts_;
};

}  // namespace model_txn
