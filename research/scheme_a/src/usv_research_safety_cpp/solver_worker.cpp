// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// p1_solver_worker —— 唯一的求解进程。
//
// 线程归属（这是本文件的全部难点）：
//   * 事务与唯一 capsule 属于**求解线程**，构造、调用、销毁都在该线程内；
//     ROS 线程从不持有它们的引用；
//   * ROS 线程只读一个互斥保护的 POD 快照（EngineSnapshot），心跳/能力发布
//     只用快照，不访问任何 backend/txn getter，也不把心跳锁带进 solve；
//   * 初始化失败必须写 worker_engine_init_failed 并确定退出 2，不能 std::terminate。
//
// 结局分类：一个 Job 要么产生候选（CandidateReady），要么被**类型化拒绝**
// （JobRefused/Closing，零本 Job native，不进入数值故障隔离），要么终端故障。
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <csignal>
#include <deque>
#include <fstream>
#include <mutex>
#include <optional>
#include <thread>

#include <rclcpp/rclcpp.hpp>

#include "protocol.hpp"
#include "p1_worker_engine.hpp"
#include "p1_engine_session.hpp"

namespace
{

std::atomic<bool> g_stop{false};
void on_signal(int) { g_stop = true; }

/// ROS 线程唯一可见的运行事实。纯 POD，无指针，无 backend 访问。
struct EngineSnapshot
{
  bool ready = false;
  bool fatal = false;
  bool model_consistent = false;
  std::uint64_t applied_generation = 0;
  std::uint32_t horizon_steps = 0;
  double prediction_dt = 0.0;
  const char * failure_reason = "";
};

}  // namespace

class Worker final : public rclcpp::Node
{
public:
  Worker() : Node("p1_solver_worker")
  {
    run_ = declare_parameter<std::string>("run_id", "");
    mode_ = declare_parameter<std::string>("mode", "production");
    hash_ = declare_parameter<std::string>("contract_hash", "");
    const auto contract_file = declare_parameter<std::string>("contract_file", "");
    contract_ = p1::load_contract(contract_file, hash_);
    resources_ = p1::resource_limits_from_contract(contract_);
    boot_ = declare_parameter<std::string>("boot_id", "");
    if (boot_.empty()) boot_ = p1::boot_id();
    nominal_ = contract_.at("nominal_hash");
    instance_ = p1::digest(run_ + boot_ + std::to_string(getpid()) +
                           std::to_string(p1::monotonic_ns()));
    if (run_.empty() || run_.size() > 128) throw std::runtime_error("run identity invalid");

    // 进程内测试接缝只在 USV_RESEARCH_TEST_SEAMS 构建中存在；普通构建不声明参数。
#ifdef USV_RESEARCH_TEST_SEAMS
    block_ = declare_parameter<int>("test_native_block_ms", 0);
    delay_ = declare_parameter<int>("test_delay_ms", 0);
    if (block_ < 0 || delay_ < 0 || block_ > 60000 || delay_ > 10000)
      throw std::runtime_error("unqualified fault injection");
    // 受控仿真里故障许可的唯一来源是合同开关；用工程级的
    // fault_injection_enabled 会让"没有许可"的合同也能注入。
    const bool faults_allowed = mode_ == "controlled_sim"
      ? (contract_.contains("controlled_sim_faults_enabled") &&
         contract_.at("controlled_sim_faults_enabled").get<bool>())
      : contract_.at("fault_injection_enabled").get<bool>();
    if ((block_ || delay_) && !faults_allowed)
      throw std::runtime_error("unqualified fault injection");
#endif

    if (contract_.value("worker_failure_policy", std::string{}) !=
        "terminal_on_failed_or_invalid_native_result")
      throw std::runtime_error("undeclared worker failure policy");

    // 实船调试服务接管：模式或合同任一命中就走 require 版验证匹配，
    // 不匹配即抛（例如 commissioning 合同配 production 模式）。
    commissioning_ = mode_ == p1::shipboard_commissioning_mode ||
                     contract_.value("schema", std::string{}) ==
                         p1::shipboard_commissioning_schema;
    dry_run_ = mode_ == p1::shipboard_dry_run_mode ||
               contract_.value("schema", std::string{}) ==
                   p1::shipboard_dry_run_schema;
    execute_shipboard_ = mode_ == p1::shipboard_execute_mode ||
                         contract_.value("schema", std::string{}) ==
                             p1::shipboard_execute_schema;
    if (commissioning_ || dry_run_ || execute_shipboard_) p1::require_runtime_contract_mode(contract_, mode_);

    const auto log = declare_parameter<std::string>("source_file", "");
    file_.open(log, std::ios::out | std::ios::app);
    if (!file_) throw std::runtime_error("worker source log unavailable");
    const auto ready_timeout = contract_.at("recording_ready_timeout_ns").get<std::int64_t>();
    if (ready_timeout <= 0 || ready_timeout > 60000000000LL)
      throw std::runtime_error("invalid finite recording timeout");
    ready_timeout_ = ready_timeout;

    plan_file_ = declare_parameter<std::string>("model_plan_file", "");
    plan_sha_ = declare_parameter<std::string>("model_plan_sha256", "");
    if (plan_file_.empty() || !std::regex_match(plan_sha_, std::regex("[0-9a-f]{64}")))
      throw std::runtime_error("model plan identity required");
    const auto plan_text = p1::read_text(plan_file_);
    if (p1::digest(plan_text) != plan_sha_) throw std::runtime_error("model plan hash mismatch");
    grid_ = p1::grid_of_plan(plan_text, contract_);
    params_ = p1::solver_params(contract_);
    registry_ = p1::registry_from_plan(plan_text, grid_);

    out_ = create_publisher<p1::Candidate>("/p1/solve_candidate",
                                           rclcpp::QoS(1).reliable());
    caps_ = create_publisher<p1::Capability>(
        "/p1/worker_capability", rclcpp::QoS(1).reliable().transient_local());
    sub_ = create_subscription<p1::Job>(
        "/p1/solve_job", rclcpp::QoS(1).reliable(),
        [this](p1::Job::SharedPtr job) { receive(*job); });

    startup_ = p1::monotonic_ns();
    // 启动异步日志写线程，防止 SD 卡 flush 阻塞心跳发布或求解线程。
    log_thread_ = std::thread([this] { log_loop(); });
    publish_capability();  // 初始化未完成时 ready=false，但身份/时域常量已可读
    timer_ = create_wall_timer(std::chrono::milliseconds(200),
                               [this] { publish_capability(); });

    thread_ = std::thread([this] { solve_thread(); });
  }

  ~Worker() override { close_source(); }

  /// 终局判定：一旦本进程不可用（初始化失败、终端数值故障、就绪超时），
  /// main 循环必须**自行**退出，而不是等外部信号 —— 否则排空门会等到超时。
  bool failed() const { return fatal_.load(); }

  bool close_source()
  {
    if (closed_) return !fatal_;
    closed_ = true;
    stopping_ = true;
    if (timer_) timer_->cancel();
    cv_.notify_all();
    if (thread_.joinable()) thread_.join();
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (pending_)
      {
        event({{"type", "job_refused"}, {"job_id", pending_->job.job_id},
               {"reason", "worker_close"}, {"terminal", false},
               {"origin", "shutdown"}, {"native_solve_entries_this_job", 0}});
        pending_.reset();
      }
    }
    event({{"type", "worker_summary"},
           {"generated_candidates", generated_.load()},
           {"published_candidates", published_.load()},
           {"completed_jobs", completed_.load()},
           {"refused_jobs", refused_.load()},
           {"commissioning_mode", commissioning_},
           {"dry_run_mode", dry_run_},
           {"shipboard_execute_mode", execute_shipboard_},
           {"commissioning_refused_total", refused_total_.load()},
           {"commissioning_resource_invalid_total", resource_invalid_total_.load()},
           {"cancelled_jobs", cancelled_.load()},
           {"terminal_numerical_failure", terminal_numerical_.load()},
           {"fatal", fatal_.load()},
           {"normal_source_complete", !fatal_.load() &&
                                       generated_.load() == published_.load()},
           {"finished_ns", p1::monotonic_ns()}}, true);
    {
      std::lock_guard<std::mutex> lock(log_mutex_);
      log_closing_ = true;
    }
    log_cv_.notify_all();
    if (log_thread_.joinable()) log_thread_.join();
    if (!file_) fatal_ = true;
    fprintf(stdout, "WORKER_CLOSE_FLUSH_SUCCESS=%s\n", fatal_ ? "false" : "true");
    return !fatal_;
  }

private:
  struct Pending
  {
    p1::Job job;
    std::int64_t receive_ns = 0;
  };

  struct LogItem
  {
    p1::Json doc;
    bool flush = false;
  };

  static constexpr std::size_t kLogQueueCapacity = 4096;

  void event(p1::Json doc, bool flush = false)
  {
    std::lock_guard<std::mutex> lock(log_mutex_);
    if (log_closing_ || log_q_.size() >= kLogQueueCapacity)
    {
      fatal_ = true;
      return;
    }
    log_q_.push_back(LogItem{std::move(doc), flush});
    log_cv_.notify_one();
  }

  void log_loop()
  {
    for (;;)
    {
      std::deque<LogItem> batch;
      {
        std::unique_lock<std::mutex> lock(log_mutex_);
        log_cv_.wait(lock, [this] { return log_closing_ || !log_q_.empty(); });
        if (log_q_.empty() && log_closing_) break;
        batch.swap(log_q_);
      }
      try
      {
        bool need_flush = false;
        for (const auto & item : batch)
        {
          file_ << item.doc.dump() << '\n';
          need_flush = need_flush || item.flush;
        }
        if (need_flush) file_.flush();
        if (!file_) fatal_ = true;
      }
      catch (...)
      {
        fatal_ = true;
      }
    }
    file_.flush();
    if (!file_) fatal_ = true;
  }

  void set_snapshot(const EngineSnapshot & value)
  {
    std::lock_guard<std::mutex> lock(snapshot_mutex_);
    snapshot_ = value;
  }

  EngineSnapshot snapshot() const
  {
    std::lock_guard<std::mutex> lock(snapshot_mutex_);
    return snapshot_;
  }

  void publish_capability()
  {
    const EngineSnapshot snap = snapshot();
    p1::Capability message;
    message.schema_version = "p1-worker-capability-v2";
    message.run_id = run_;
    message.boot_id = boot_;
    message.contract_hash = hash_;
    message.nominal_hash = nominal_;
    message.worker_instance = instance_;
    message.clock_name = "CLOCK_MONOTONIC";
    message.backend = "acados";
    message.matrix_layout = "column_major";
    // 时域/步长是**合同常量**：初始化未完成也能正确报告，但 ready 仍为 false。
    message.horizon_steps = static_cast<std::uint32_t>(params_.N);
    message.prediction_dt = params_.dt;
    message.pid = getpid();
    message.startup_ns = startup_;
    message.completed_jobs = completed_.load();
    message.active_job = active_.load();
    {
      std::lock_guard<std::mutex> lock(mutex_);
      message.pending_count = pending_ ? 1 : 0;
    }
    message.fatal = fatal_.load();
    // 受控仿真：对外通告的故障能力以**合同开关**为准。基础合同的
    // fault_injection_enabled 是工程级开关，不是这次运行被授予的许可。
    const bool sim_faults = contract_.contains("controlled_sim_faults_enabled") &&
                            contract_.at("controlled_sim_faults_enabled").get<bool>();
    message.fault_injection_enabled = mode_ == "controlled_sim"
        ? sim_faults : contract_.at("fault_injection_enabled").get<bool>();
    message.reason = snap.fatal ? std::string(snap.failure_reason) : std::string{};
    // 三者都是实测值：就绪状态只来自求解线程的快照，不由接收方自报推导。
    message.model_runtime_ready = snap.ready && !snap.fatal && snap.model_consistent;
    message.model_plan_sha256 = plan_sha_;
    message.applied_generation = snap.applied_generation;
    // 契约证据：能力心跳必须落在 worker source 里，检查器只认原文。
    event({{"type", "worker_capability"},
           {"schema", message.schema_version},
           {"run_id", message.run_id},
           {"boot_id", message.boot_id},
           {"contract_hash", message.contract_hash},
           {"nominal_hash", message.nominal_hash},
           {"worker_instance", message.worker_instance},
           {"clock_name", message.clock_name},
           {"backend", message.backend},
           {"matrix_layout", message.matrix_layout},
           {"horizon_steps", message.horizon_steps},
           {"prediction_dt", message.prediction_dt},
           {"pid", message.pid},
           {"startup_ns", message.startup_ns},
           {"completed_jobs", message.completed_jobs},
           {"active_job", message.active_job},
           {"pending_count", message.pending_count},
           {"fault_injection_enabled", message.fault_injection_enabled},
           {"fatal", message.fatal},
           {"reason", message.reason},
           {"model_runtime_ready", message.model_runtime_ready},
           {"model_plan_sha256", message.model_plan_sha256},
           {"applied_generation", message.applied_generation},
           {"publish_ns", p1::monotonic_ns()}});
    caps_->publish(message);
  }

  bool wait_recording_ready()
  {
    try
    {
      const std::int64_t start = p1::monotonic_ns();
      while (rclcpp::ok() && !stopping_ && !fatal_ &&
             p1::monotonic_ns() - start <= ready_timeout_)
      {
        bool recorder = false;
        bool regulator = false;
        for (const auto & endpoint : get_subscriptions_info_by_topic("/p1/solve_candidate"))
        {
          recorder = recorder ||
                     endpoint.node_name().find("recorder") != std::string::npos;
          regulator = regulator || endpoint.node_name() == "p1_regulator";
        }
        // 受控仿真的启动门在 runner 那边：plant → worker → regulator。也就是说
        // worker 必须先就绪，regulator 之后才启动 —— 因此这里**不能**等
        // regulator 的订阅出现，否则两边互等直到超时。
        // 生产采集仍要求 recorder 与 regulator 都在位。
        const bool sim_ready = mode_ == "controlled_sim" || dry_run_ || execute_shipboard_;
        const bool production_ready = out_->get_subscription_count() >= 2 && recorder &&
                                      regulator;
        if (sim_ready ? sim_ready : production_ready)
        {
          event({{"type", "worker_recording_ready"},
                 {"worker_instance", instance_},
                 {"ready_ns", p1::monotonic_ns()},
                 {"candidate_matched", out_->get_subscription_count()},
                 {"active_job", 0}}, true);
          if (!fatal_) return true;
          break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
      }
      fatal_ = true;
      event({{"type", "worker_recording_ready_failed"},
             {"worker_instance", instance_},
             {"finished_ns", p1::monotonic_ns()}}, true);
    }
    catch (const std::exception & error)
    {
      fatal_ = true;
      event({{"type", "worker_recording_ready_failed"},
             {"reason", std::string(error.what()).substr(0, 256)}}, true);
    }
    {
      std::lock_guard<std::mutex> lock(mutex_);
      pending_.reset();
    }
    active_ = 0;
    return false;
  }

  void receive(const p1::Job & job)
  {
    const auto now = p1::monotonic_ns();
    const auto resource = p1::check_job_resources(job, resources_);
    // commissioning：先算资源检查结果，然后在任何普通 resource 日志、有效身份
    // 判定、排队、native 入口之前一律拒绝，且**不保存 Job payload**。
    if (commissioning_)
    {
      refuse_commissioning_job(job.job_id, static_cast<bool>(resource), now);
      return;
    }
    if (!resource)
    {
      event({{"type", "resource_rejected"}, {"interface", "job"},
             {"job_id", job.job_id}, {"reason", resource.reason},
             {"field", resource.field}, {"observed", resource.observed},
             {"limit", resource.limit}, {"receive_ns", now}});
      return;
    }
    if (fatal_ || stopping_)
    {
      event({{"type", "job_refused"}, {"job_id", job.job_id},
             {"reason", "worker_terminal"}, {"terminal", true},
             {"origin", "worker_terminal"}, {"native_solve_entries_this_job", 0}});
      return;
    }
    auto reason = p1::valid_job(job, run_, boot_, hash_, nominal_, instance_);
    if (reason.empty() && now > job.deadline_steady_ns) reason = "late_before_native";
    if (!reason.empty())
    {
      event({{"type", "job_refused"}, {"job_id", job.job_id}, {"reason", reason},
             {"terminal", false}, {"origin", "receive"},
             {"check_ns", now}, {"native_solve_entries_this_job", 0}});
      return;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    if (fatal_ || stopping_)
    {
      event({{"type", "job_refused"}, {"job_id", job.job_id},
             {"reason", "worker_terminal"}, {"terminal", true},
             {"origin", "worker_terminal"}, {"receive_ns", now}});
      return;
    }
    if (job.job_id <= last_received_)
    {
      event({{"type", "job_refused"}, {"job_id", job.job_id},
             {"reason", "duplicate_or_reordered"}, {"terminal", false},
             {"origin", "receive"}, {"receive_ns", now}});
      return;
    }
    last_received_ = job.job_id;
    event({{"type", "job_received"}, {"job", p1::job_json(job)},
           {"worker_instance", instance_}, {"receive_ns", now},
           {"commit_ns", p1::monotonic_ns()}});
    if (pending_)
      event({{"type", "pending_replaced"}, {"job_id", pending_->job.job_id},
             {"replacement_job_id", job.job_id}});
    pending_ = Pending{job, now};
    cv_.notify_one();
  }

  /// 求解线程入口：本线程内构造、调用、销毁引擎。构造失败必须确定退出。
  void solve_thread()
  {
    try
    {
      engine_ = std::make_unique<p1::WorkerEngine>(params_, registry_, grid_, 1);
    }
    catch (const std::exception & error)
    {
      const std::string reason = std::string("worker_engine_init_failed:") +
                                 std::string(error.what()).substr(0, 200);
      EngineSnapshot snap;
      snap.ready = false;
      snap.fatal = true;
      snap.failure_reason = "worker_engine_init_failed";
      set_snapshot(snap);
      fatal_ = true;
      event({{"type", "worker_engine_init_failed"}, {"reason", reason},
             {"worker_instance", instance_}, {"finished_ns", p1::monotonic_ns()}}, true);
      return;
    }
    {
      EngineSnapshot snap;
      snap.ready = true;
      snap.fatal = false;
      snap.model_consistent = engine_->model_consistent();
      snap.applied_generation = engine_->applied_generation();
      snap.horizon_steps = static_cast<std::uint32_t>(engine_->N());
      snap.prediction_dt = engine_->dt();
      snap.failure_reason = "";
      set_snapshot(snap);
    }
    try
    {
      work(*engine_);
    }
    catch (const std::exception & error)
    {
      const std::string reason = std::string("worker_work_exception:") +
                                 std::string(error.what()).substr(0, 200);
      EngineSnapshot snap = snapshot();
      snap.ready = false;
      snap.fatal = true;
      snap.failure_reason = "worker_unusable";
      set_snapshot(snap);
      fatal_ = true;
      event({{"type", "worker_engine_init_failed"}, {"reason", reason},
             {"worker_instance", instance_}, {"finished_ns", p1::monotonic_ns()}}, true);
    }
    engine_.reset();  // 只在本线程销毁
  }

  void work(p1::WorkerEngine & engine)
  {
    // commissioning：真实引擎已在求解线程内初始化并实测 ready；这里不做
    // recorder / regulator candidate 订阅 / job peer 的任何等待，也不读它们的
    // 计数或名称 —— 本模式根本不发布候选。
    if (commissioning_)
    {
      event({{"type", "worker_commissioning_ready"},
             {"worker_instance", instance_},
             {"mode", mode_},
             {"engine_ready", snapshot().ready},
             {"model_consistent", snapshot().model_consistent},
             {"candidate_publishers", 0},
             {"jobs_accepted", 0},
             {"ready_ns", p1::monotonic_ns()}}, true);
      work_commissioning();
      return;
    }
    if (!wait_recording_ready()) return;
    while (!stopping_ && !fatal_)
    {
      Pending item;
      {
        std::unique_lock<std::mutex> lock(mutex_);
        cv_.wait_for(lock, std::chrono::milliseconds(100),
                     [this] { return stopping_ || fatal_ || pending_.has_value(); });
        if (stopping_ || fatal_)
        {
          if (pending_)
          {
            event({{"type", "job_refused"},
                   {"job_id", pending_->job.job_id},
                   {"reason", "worker_stopping_before_native"},
                   {"terminal", false}, {"origin", "shutdown"},
                   {"native_solve_entries_this_job", 0}});
            ++cancelled_;
            pending_.reset();
          }
          break;
        }
        if (!pending_) continue;
        item = *pending_;
        pending_.reset();
        active_ = item.job.job_id;
      }

      // 入口到期：消费 Job 身份、记录 OwnedInitialDeadline、零 native，
      // 且**不**进入数值故障隔离 —— 后继合法 Job 必须能继续求解。
      p1::EngineOutcome entry;
      const auto use_entry_refusal = [&]() -> bool {
        const std::int64_t now = p1::monotonic_ns();
        if (now <= item.job.deadline_steady_ns) return false;
        const auto refusal = engine.entry_refusal(
            p1::identity_of(item.job), p1::axes_of(item.job), grid_,
            item.job.job_id, item.job.target_tick, now,
            item.job.deadline_steady_ns);
        event({{"type", "job_refused"}, {"job_id", item.job.job_id},
               {"origin", model_txn::to_string(refusal.refusal.origin)},
               {"fault", model_txn::to_string(refusal.refusal.fault)},
               {"reason", refusal.reason.empty() ? "entry_expired" : refusal.reason},
               {"terminal", false}, {"closing", refusal.closing},
               {"original_deadline_ns", item.job.deadline_steady_ns},
               {"check_ns", now},
               {"applied_generation", refusal.applied_generation},
               {"native_solve_entries_this_job", 0}});
        ++refused_;
        active_ = 0;
        return true;
      };
      if (use_entry_refusal()) continue;

      p1::Candidate result;
      result.job = item.job;
      result.worker_instance = instance_;
      result.backend = "acados";
      result.worker_receive_ns = item.receive_ns;
      try
      {
        if (item.job.reset_warmstart) engine.reset_warmstart();
        engine.set_applied_control({item.job.anchor_n[0], item.job.anchor_n[1]});
        usv_mpc::Vector6d x;
        std::copy(item.job.target_state.begin(), item.job.target_state.end(), x.data());
        Eigen::MatrixXd reference(6, 21);
        std::copy(item.job.reference.begin(), item.job.reference.end(), reference.data());

#ifdef USV_RESEARCH_TEST_SEAMS
        // 阻塞只施加**一次**：反证要证明"这一拍超时被拒、下一拍仍能正常求解"，
        // 每拍都阻塞会让整条链永远没有候选，什么也证明不了。
        if (block_ && !block_used_)
        {
          event({{"type", "controlled_pre_native_barrier"},
                 {"job_id", item.job.job_id},
                 {"start_ns", p1::monotonic_ns()},
                 {"duration_ms", block_},
                 {"actual_native_invoked", false},
                 {"flush_requested", true}}, true);
          block_used_ = true;
          std::this_thread::sleep_for(std::chrono::milliseconds(block_));
        }
#endif
        result.solve_start_ns = p1::monotonic_ns();
        if (stopping_ || fatal_ || result.solve_start_ns > item.job.deadline_steady_ns)
        {
          if (use_entry_refusal()) continue;
          ++refused_;
          active_ = 0;
          continue;
        }
        result.solver_invoked = true;
        p1::EngineOutcome outcome;
        const auto answer = engine.solve(
            p1::axes_of(item.job), grid_, item.job.job_id, item.job.target_tick,
            item.job.deadline_steady_ns, x, reference,
            {item.job.anchor_n[0], item.job.anchor_n[1]}, p1::identity_of(item.job),
            [this] { return stopping_.load() || fatal_.load(); },
            [this, &item] { return p1::monotonic_ns() > item.job.deadline_steady_ns; },
            &outcome);
        result.solve_end_ns = p1::monotonic_ns();
        result.success = answer.second.success;
        result.backend_ms = answer.second.solve_time_ms;
        // 原生原因必须按消息字段上界截断，不能让一个过长的字符串把 CDR 撑爆。
        result.reason = std::string(answer.second.error).substr(0, 256);

        const auto ledger = outcome.preparation;
        const p1::Json preparation = {
            {"ordinals", ledger.ordinals},
            {"complete", ledger.complete},
            {"constraint_set_calls", ledger.constraint_set_calls},
            {"constraint_set_failed", ledger.constraint_set_failed},
            {"update_params_calls", ledger.update_params_calls},
            {"update_params_failed", ledger.update_params_failed},
            {"out_set_calls", ledger.out_set_calls}};
        const p1::Json refusal = {
            {"origin", model_txn::to_string(outcome.refusal.origin)},
            {"fault", model_txn::to_string(outcome.refusal.fault)},
            {"job_id", outcome.refusal.job_id},
            {"original_deadline_ns", outcome.refusal.original_deadline_ns},
            {"checked_ns", outcome.refusal.checked_ns},
            {"applied_generation", outcome.refusal.applied_generation},
            {"model_consistent", outcome.refusal.model_consistent},
            {"closing", outcome.refusal.closing},
            {"model_terminal", outcome.refusal.model_terminal},
            {"c_solve_entries_this_job", outcome.refusal.c_solve_entries_this_job}};

        if (outcome.execution != p1::EngineDisposition::CandidateReady)
        {
          event({{"type", "job_refused"}, {"job_id", item.job.job_id},
                 {"origin", model_txn::to_string(outcome.refusal.origin)},
                 {"fault", model_txn::to_string(outcome.refusal.fault)},
                 {"reason", outcome.reason},
                 {"terminal", outcome.terminal},
                 {"closing", outcome.execution == p1::EngineDisposition::Closing},
                 {"execution", p1::to_string(outcome.execution)},
                 {"original_deadline_ns", item.job.deadline_steady_ns},
                 {"guard_checked_ns", outcome.guard_checked_ns},
                 {"native_solve_entries_before", outcome.native_solve_entries_before},
                 {"native_solve_entries_after", outcome.native_solve_entries_after},
                 {"native_solve_entries_this_job",
                  outcome.native_solve_entries_this_job},
                 {"applied_generation", outcome.applied_generation},
                 {"model_generation_applied", outcome.applied_generation},
                 {"preparation", preparation}, {"refusal_facts", refusal}}, true);
          active_ = 0;
          if (outcome.execution == p1::EngineDisposition::TerminalFault)
          {
            ++terminal_numerical_;
            mark_terminal(outcome.reason, item.job.job_id, "terminal_engine_fault");
            break;
          }
          if (outcome.execution == p1::EngineDisposition::Closing)
          {
            // stop 关闭：逐条取消 pending，不当数值故障。
            std::optional<std::uint64_t> discarded;
            {
              std::lock_guard<std::mutex> lock(mutex_);
              if (pending_)
              {
                discarded = pending_->job.job_id;
                pending_.reset();
              }
            }
            if (discarded)
            {
              event({{"type", "job_refused"}, {"job_id", *discarded},
                     {"reason", "worker_closing"}, {"terminal", false},
                     {"origin", "stop"}, {"native_solve_entries_this_job", 0}});
              ++cancelled_;
            }
            ++refused_;
            break;
          }
          ++refused_;
          continue;
        }

        result.prediction_available =
            result.success && answer.second.X_pred.rows() == 6 &&
            answer.second.X_pred.cols() == 21 && answer.second.U_pred.rows() == 2 &&
            answer.second.U_pred.cols() == 20 && answer.second.X_pred.allFinite() &&
            answer.second.U_pred.allFinite() && answer.first.allFinite();
        if (result.prediction_available)
        {
          std::copy(answer.first.data(), answer.first.data() + 2,
                    result.first_control.begin());
          std::copy(answer.second.X_pred.data(), answer.second.X_pred.data() + 126,
                    result.x_prediction.begin());
          std::copy(answer.second.U_pred.data(), answer.second.U_pred.data() + 40,
                    result.u_prediction.begin());
        }
        const auto output_resource = p1::check_candidate_resources(result, resources_);
        if (!output_resource)
        {
          event({{"type", "native_result_resource_oversize"},
                 {"job_id", item.job.job_id},
                 {"field", output_resource.field},
                 {"observed", output_resource.observed},
                 {"limit", output_resource.limit}});
          throw std::runtime_error("native_result_resource_oversize");
        }
        if (delay_ > 0) std::this_thread::sleep_for(std::chrono::milliseconds(delay_));

        ++generated_;
        event({{"type", "candidate"}, {"job", p1::job_json(item.job)},
               {"worker_instance", instance_},
               {"receive_ns", item.receive_ns},
               {"solver_invoked", result.solver_invoked},
               {"backend", result.backend},
               {"backend_ms", result.backend_ms},
               {"solve_start_ns", result.solve_start_ns},
               {"solve_end_ns", result.solve_end_ns},
               {"success", result.success},
               {"prediction_available", result.prediction_available},
               {"first_control", result.first_control},
               {"X", result.x_prediction}, {"U", result.u_prediction},
               {"reason", result.reason},
               {"txn_disposition", outcome.disposition},
               {"txn_reason", outcome.reason},
               {"execution", p1::to_string(outcome.execution)},
               {"model_generation_applied", outcome.applied_generation},
               {"applied_generation", outcome.applied_generation},
               {"model_consistent", outcome.model_consistent},
               {"native_solve_entries", outcome.native_solve_entries},
               {"native_solve_entries_before", outcome.native_solve_entries_before},
               {"native_solve_entries_after", outcome.native_solve_entries_after},
               {"native_solve_entries_this_job", outcome.native_solve_entries_this_job},
               {"guard_checked_ns", outcome.guard_checked_ns},
               {"original_deadline_ns", item.job.deadline_steady_ns},
               {"preparation", preparation}, {"refusal_facts", refusal},
               {"publish_start_ns", p1::monotonic_ns()}}, true);
        if (fatal_) break;

        const auto publish_start = p1::monotonic_ns();
        try
        {
          out_->publish(result);
          ++published_;
          event({{"type", "candidate_publish_result"},
                 {"job_id", item.job.job_id},
                 {"worker_instance", instance_},
                 {"solve_start_ns", result.solve_start_ns},
                 {"solve_end_ns", result.solve_end_ns},
                 {"publish_start_ns", publish_start},
                 {"publish_end_ns", p1::monotonic_ns()},
                 {"success", true}});
        }
        catch (...)
        {
          event({{"type", "candidate_publish_result"},
                 {"job_id", item.job.job_id},
                 {"worker_instance", instance_},
                 {"solve_start_ns", result.solve_start_ns},
                 {"solve_end_ns", result.solve_end_ns},
                 {"publish_start_ns", publish_start},
                 {"publish_end_ns", p1::monotonic_ns()},
                 {"success", false}});
          throw;
        }
      }
      catch (const std::exception & error)
      {
        fatal_ = true;
        ++terminal_numerical_;
        event({{"type", "terminal_exception"}, {"job_id", item.job.job_id},
               {"reason", std::string(error.what()).substr(0, 256)}}, true);
        mark_terminal(error.what(), item.job.job_id, "terminal_exception");
        break;
      }

      ++completed_;
      active_ = 0;
      if (!result.success || !result.prediction_available)
      {
        ++terminal_numerical_;
        event({{"type", "terminal_numerical_failure"},
               {"job_id", item.job.job_id},
               {"solver_invoked", result.solver_invoked},
               {"success", result.success},
               {"prediction_available", result.prediction_available},
               {"result_published", true},
               {"reason", result.reason},
               {"policy", "quarantine_this_run_no_restart"},
               {"terminal_ns", p1::monotonic_ns()}}, true);
        mark_terminal(result.reason, item.job.job_id, "native_failure_quarantine");
        break;
      }
      EngineSnapshot snap = snapshot();
      snap.applied_generation =
          engine.applied_generation();  // 只在本线程调用后写入快照
      snap.model_consistent = engine.model_consistent();
      set_snapshot(snap);
    }
  }

  /// commissioning 的拒绝聚合：首条逐条记，此后最多每 1s 一条同类聚合，
  /// 关闭时补记剩余窗口。绝不每 job 写盘。
  void refuse_commissioning_job(std::uint64_t job_id, bool resource_ok,
                                std::int64_t now)
  {
    ++refused_total_;
    if (!resource_ok) ++resource_invalid_total_;
    ++refused_window_;
    if (!commissioning_refusal_logged_)
    {
      commissioning_refusal_logged_ = true;
      refused_window_ = 0;
      commissioning_window_ns_ = now;
      event({{"type", "job_refused"}, {"job_id", job_id},
             {"reason", "commissioning_no_jobs"}, {"terminal", false},
             {"origin", "commissioning"}, {"check_ns", now},
             {"refused_total", refused_total_.load()},
             {"resource_invalid_total", resource_invalid_total_.load()},
             {"native_solve_entries_this_job", 0}});
      return;
    }
    if (now - commissioning_window_ns_ >= 1000000000LL)
    {
      const std::uint64_t window = refused_window_.exchange(0);
      commissioning_window_ns_ = now;
      event({{"type", "job_refused"}, {"job_id", job_id},
             {"reason", "commissioning_no_jobs"}, {"terminal", false},
             {"origin", "commissioning"}, {"check_ns", now},
             {"refused_total", refused_total_.load()},
             {"refused_in_window", window},
             {"resource_invalid_total", resource_invalid_total_.load()},
             {"aggregated", true}, {"native_solve_entries_this_job", 0}});
    }
  }

  /// commissioning 求解线程：引擎保持初始化状态，只等停止；不接受任何 Job。
  void work_commissioning()
  {
    while (!stopping_ && !fatal_)
    {
      std::unique_lock<std::mutex> lock(mutex_);
      cv_.wait_for(lock, std::chrono::milliseconds(100),
                   [this] { return stopping_ || fatal_; });
      // 任何排到队列里的 Job 都是外部误投：在没有 native 调用的情况下丢弃。
      if (pending_)
      {
        const auto discarded = pending_->job.job_id;
        pending_.reset();
        refuse_commissioning_job(discarded, true, p1::monotonic_ns());
      }
      active_ = 0;
    }
    {
      // 关闭时补记本窗口剩余计数，保证总数不丢。
      const std::uint64_t window = refused_window_.exchange(0);
      if (window)
        event({{"type", "job_refused"}, {"job_id", 0},
               {"reason", "commissioning_no_jobs"}, {"terminal", false},
               {"origin", "commissioning_close"}, {"refused_total", refused_total_.load()},
               {"refused_in_window", window},
               {"resource_invalid_total", resource_invalid_total_.load()},
               {"aggregated", true}, {"native_solve_entries_this_job", 0}});
    }
  }

  void mark_terminal(const std::string & reason, std::uint64_t job_id,
                     const char * policy)
  {
    fatal_ = true;
    std::optional<std::uint64_t> discarded;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (pending_)
      {
        discarded = pending_->job.job_id;
        pending_.reset();
      }
    }
    if (discarded)
      event({{"type", "job_refused"}, {"job_id", *discarded},
             {"reason", "terminal_pending_discarded"}, {"terminal", true},
             {"origin", policy}, {"native_solve_entries_this_job", 0}});
    EngineSnapshot snap = snapshot();
    snap.fatal = true;
    snap.ready = false;
    snap.failure_reason = "worker_unusable";
    set_snapshot(snap);
  }

  p1::Json contract_;
  p1::ResourceLimits resources_;
  std::string run_, hash_, boot_, nominal_, instance_, mode_;
  std::string plan_file_, plan_sha_;
  model_reference::Grid grid_;
  model_reference::Registry registry_{};
  usv_mpc::MpcParams params_{};
  std::int64_t startup_ = 0;
  std::int64_t ready_timeout_ = 0;
  bool closed_ = false;
#ifdef USV_RESEARCH_TEST_SEAMS
  int delay_ = 0;
  int block_ = 0;
  bool block_used_ = false;
#else
  static constexpr int delay_ = 0;
#endif

  std::atomic<std::uint64_t> active_{0}, completed_{0}, generated_{0}, published_{0},
      refused_{0}, cancelled_{0}, terminal_numerical_{0};
  bool commissioning_ = false;
  bool dry_run_ = false;
  bool execute_shipboard_ = false;
  std::atomic<std::uint64_t> refused_total_{0}, resource_invalid_total_{0}, refused_window_{0};
  bool commissioning_refusal_logged_ = false;
  std::int64_t commissioning_window_ns_ = 0;
  std::atomic<bool> fatal_{false}, stopping_{false};
  std::uint64_t last_received_ = 0;

  std::optional<Pending> pending_;
  std::mutex mutex_;
  mutable std::mutex snapshot_mutex_;
  std::condition_variable cv_;
  EngineSnapshot snapshot_{};
  std::ofstream file_;
  std::mutex log_mutex_;
  std::condition_variable log_cv_;
  std::deque<LogItem> log_q_;
  bool log_closing_ = false;
  std::thread log_thread_;
  std::thread thread_;
  std::unique_ptr<p1::WorkerEngine> engine_;  // 仅求解线程访问

  rclcpp::Publisher<p1::Candidate>::SharedPtr out_;
  rclcpp::Publisher<p1::Capability>::SharedPtr caps_;
  rclcpp::Subscription<p1::Job>::SharedPtr sub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv, rclcpp::InitOptions(),
               rclcpp::SignalHandlerOptions::None);
  std::signal(SIGINT, on_signal);
  std::signal(SIGTERM, on_signal);
  try
  {
    auto node = std::make_shared<Worker>();
    rclcpp::executors::SingleThreadedExecutor exec;
    exec.add_node(node);
    while (!g_stop && rclcpp::ok() && !node->failed())
    {
      exec.spin_some(std::chrono::milliseconds(10));
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    exec.remove_node(node);
    const bool closed = node->close_source();
    node.reset();
    rclcpp::shutdown();
    return closed ? 0 : 2;
  }
  catch (const std::exception & error)
  {
    fprintf(stderr, "worker fatal: %s\n", error.what());
    rclcpp::shutdown();
    return 1;
  }
}
