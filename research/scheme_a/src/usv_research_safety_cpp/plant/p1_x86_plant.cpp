// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// p1_x86_plant —— 受控仿真的执行端（x86 无硬件）。
//
// 唯一的时间推进源是 5 ms 的 pump：
//   * 物理只在 pump 里推进，命令到达只做准入，绝不改状态（修复 3.5）；
//   * 时钟、传感器、参考发布都从同一个 SimClock 派生（sim = steady - origin）；
//   * hold 是半开窗口，窗口外零推力；到期/被接管/stop 都发 PlantHoldClose；
//   * 准入按固定 12 步（schema/身份/重复/重排/窗口/迟到/范围/tick 唯一/
//     待执行/重叠），错误的五轴版本与同 tick 二次施加都会被拒绝（修复 3.4）。
#include <algorithm>
#include <atomic>
#include <chrono>
#include <fstream>
#include <optional>
#include <csignal>
#include <deque>
#include <string>
#include <thread>

#include <rclcpp/rclcpp.hpp>

#include "usv_nmpc/usv_model_dynamic.hpp"
#include "protocol.hpp"
#include "p1_clock_diagnostics.hpp"
#include "plant/p1_plant_admission.hpp"
#include "plant/p1_plant_core.hpp"
#include "plant/p1_plant_model_loader.hpp"
#include "usv_research_interfaces/msg/plant_command.hpp"
#include "usv_research_interfaces/msg/plant_hold_close.hpp"
#include "usv_research_interfaces/msg/plant_receipt.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "sensor_msgs/msg/imu.hpp"
#include "nav_msgs/msg/path.hpp"
#include "std_msgs/msg/float64_multi_array.hpp"
#include "rosgraph_msgs/msg/clock.hpp"

namespace
{

std::atomic<bool> g_stop{false};
void on_signal(int) { g_stop = true; }

/// pump 的固定节拍。物理子步是 50 ms，pump 比它快一个数量级以便及时收尾。
constexpr std::int64_t kPumpNs = 5'000'000;
constexpr std::int64_t kCatchUpLimitNs = 2'000'000'000;
constexpr std::int64_t kReferencePeriodNs = 200'000'000;

/// 诊断缓冲上限：单一 plant executor 流。饱和即停，不循环覆盖。
constexpr std::size_t kPlantTraceCapacity = 262144;

}  // namespace

class Plant final : public rclcpp::Node
{
public:
  Plant() : Node("p1_x86_plant")
  {
    run_ = declare_parameter<std::string>("run_id", "");
    boot_ = declare_parameter<std::string>("boot_id", "");
    if (boot_.empty()) boot_ = p1::boot_id();
    hash_ = declare_parameter<std::string>("contract_hash", "");
    contract_file_ = declare_parameter<std::string>("contract_file", "");
    source_ = declare_parameter<std::string>("source_file", "");
    plant_model_file_ = declare_parameter<std::string>("plant_model_file", "");
    // 空串 = 完全禁用：不分配缓冲、不额外读时钟、不创建文件。
    diag_file_ = declare_parameter<std::string>("clock_diagnostics_file", "");
    contract_ = p1::load_contract(contract_file_, hash_);
    const auto profile = p1::validate_contract_fields(contract_);
    p1::validate_contract_mode(
        contract_, profile == p1::ContractProfile::ControlledSim ? "controlled_sim" : "execute");
    if (!diag_file_.empty() && profile != p1::ContractProfile::ControlledSim)
      throw std::runtime_error("clock diagnostics require controlled_sim");

    const auto params = p1::solver_params(contract_);
    usv_mpc::HydroParams hydro;
    hydro.mass = params.hydro.mass;
    hydro.Iz = params.hydro.Iz;
    hydro.xg = params.hydro.xg;
    hydro.d_thruster = params.hydro.d_thruster;
    hydro.Xu_dot = params.hydro.Xu_dot;
    hydro.Yv_dot = params.hydro.Yv_dot;
    hydro.Yr_dot = params.hydro.Yr_dot;
    hydro.Nv_dot = params.hydro.Nv_dot;
    hydro.Nr_dot = params.hydro.Nr_dot;
    hydro.Xu = params.hydro.Xu;
    hydro.Yv = params.hydro.Yv;
    hydro.Yr = params.hydro.Yr;
    hydro.Nv = params.hydro.Nv;
    hydro.Nr = params.hydro.Nr;
    hydro.Xuu = params.hydro.Xuu;
    hydro.Yvv = params.hydro.Yvv;
    hydro.Yrr = params.hydro.Yrr;
    hydro.Nvv = params.hydro.Nvv;
    hydro.Nrr = params.hydro.Nrr;
    hydro_info_ = p1_plant::load_plant_hydro(hydro, plant_model_file_);
    hydro_nominal_hash_ = p1::digest(p1_plant::hydro_to_json(hydro_info_.controller_nominal).dump());
    hydro_actual_hash_ = p1::digest(p1_plant::hydro_to_json(hydro_info_.plant_actual).dump());
    core_ = std::make_unique<p1_plant::PlantCore>(hydro_info_.plant_actual);

    gate_.run_id = run_;
    gate_.boot_id = boot_;
    gate_.contract_hash = hash_;
    gate_.command_min_n = contract_.at("command_min_n").get<double>();
    gate_.command_max_n = contract_.at("command_max_n").get<double>();

    log_.open(source_, std::ios::out | std::ios::app);
    if (!log_) throw std::runtime_error("plant source log unavailable");

    const auto initial = declare_parameter<std::vector<double>>(
        "initial_state", std::vector<double>(6, 0.0));
    if (initial.size() != 6) throw std::runtime_error("initial_state must be 6 values");
    for (int i = 0; i < 6; ++i) state_[i] = initial[static_cast<std::size_t>(i)];

    // 唯一的时间原点：此后 sim = steady - origin。
    clock_.steady_origin_ns = p1::monotonic_ns();
    clock_.sim_ns = 0;

    // 诊断文件在合同/mode 校验之后才排他创建；失败即启动失败，不静默禁用。
    if (!diag_file_.empty())
    {
      diag_trace_ = std::make_unique<p1_clock_diag::BoundedTrace<kPlantTraceCapacity>>();
      nlohmann::json header{{"producer", "p1_x86_plant"},
                            {"pid", getpid()},
                            {"run_id", run_},
                            {"boot_id", boot_},
                            {"host_boot_id", p1::boot_id()},
                            {"contract_hash", hash_},
                            {"stream_capacities", {{"plant_executor", kPlantTraceCapacity}}},
                            {"bootstrap_steady_origin_ns", clock_.steady_origin_ns}};
      diag_ = p1_clock_diag::Diagnostics::create(diag_file_, header);
      diag_->add_stream("plant_executor", *diag_trace_);
    }

    sub_ = create_subscription<usv_research_interfaces::msg::PlantCommand>(
        // depth 1 会让新命令挤掉尚未处理的那一条（实测整段 tick 直接消失）。
        // 保持可靠投递，但必须给出足够的队列深度。
        "/p1/plant_command", rclcpp::QoS(16).reliable(),
        [this](usv_research_interfaces::msg::PlantCommand::SharedPtr message) {
          receive(*message);
        });
    // bootstrap 回执在 regulator 启动之前就要发布（启动门顺序是 plant → worker →
    // regulator），所以这个通道必须是 latched：晚加入的订阅者也能看到"零执行
    // 起点"。否则第一条回执永久丢失，锚点链永远无法建立。
    receipt_pub_ = create_publisher<usv_research_interfaces::msg::PlantReceipt>(
        "/p1/plant_receipt", rclcpp::QoS(16).reliable().transient_local());
    hold_close_pub_ = create_publisher<usv_research_interfaces::msg::PlantHoldClose>(
        "/p1/plant_hold_close", rclcpp::QoS(16).reliable().transient_local());
    odom_pub_ = create_publisher<nav_msgs::msg::Odometry>(
        contract_.at("input_topics").at("odom").get<std::string>(),
        rclcpp::SensorDataQoS());
    imu_pub_ = create_publisher<sensor_msgs::msg::Imu>(
        contract_.at("input_topics").at("imu").get<std::string>(),
        rclcpp::SensorDataQoS());
    const auto path_file = declare_parameter<std::string>("scenario_path_file", "");
    if (path_file.empty()) throw std::runtime_error("scenario_path_file is required");
    path_rows_ = load_path(path_file);
    const auto profile_file = declare_parameter<std::string>("scenario_profile_file", "");
    if (!profile_file.empty()) profile_rows_ = load_path(profile_file);
    path_pub_ = create_publisher<nav_msgs::msg::Path>(
        contract_.at("input_topics").at("path").get<std::string>(),
        rclcpp::QoS(1).reliable());
    profile_pub_ = create_publisher<std_msgs::msg::Float64MultiArray>(
        contract_.at("input_topics").at("profile").get<std::string>(),
        rclcpp::QoS(1).reliable());
    clock_pub_ = create_publisher<rosgraph_msgs::msg::Clock>("/clock", rclcpp::ClockQoS());

    // bootstrap 回执：sequence 0、零执行、给出真实原点。
    publish_bootstrap();

    pump_timer_ = create_wall_timer(std::chrono::nanoseconds(kPumpNs),
                                    [this] { pump(); });
    event({{"type", "plant_ready"}, {"run_id", run_}, {"boot", boot_},
           {"contract_hash", hash_}, {"clock", "CLOCK_MONOTONIC"},
           {"clock_identity", p1_plant::kClockIdentity},
           {"steady_origin_ns", clock_.steady_origin_ns},
           {"substep_ns", p1_plant::kSubstepNs},
           {"plant_model_file", hydro_info_.source_path},
           {"plant_model_overridden", hydro_info_.overridden},
           {"controller_nominal_hash", hydro_nominal_hash_},
           {"plant_actual_hash", hydro_actual_hash_},
           {"controller_nominal", p1_plant::hydro_to_json(hydro_info_.controller_nominal)},
           {"plant_actual", p1_plant::hydro_to_json(hydro_info_.plant_actual)}},
          true);
  }

  ~Plant() override { flush_summary(); }

  /// 收尾：停止推进、写 plant_summary（source 末行）。
  /// 关机：把正在执行的 hold 截断到当前 sim 并声明 reason=stop，然后 flush。
  /// 计时器驱动的 pump() 在 SIGTERM 之后不会再被调度，所以这条路必须显式走。
  void stop_and_flush()
  {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (!stopped_)
      {
        stopped_ = true;
        if (hold_.active && clock_.sim_ns < hold_.end_ns)
        {
          publish_hold_close("stop", clock_.steady_of(clock_.sim_ns),
                             clock_.steady_of(hold_.end_ns));
          hold_.active = false;
        }
        flush_summary_locked();
      }
    }
  }

  /// 收尾：executor 移除、原 source 收尾、且已退出状态锁作用域之后调用。
  void close_diagnostics() noexcept;

  void flush_summary()
  {
    if (summary_written_) return;
    summary_written_ = true;
    log_.flush();
    const bool flushed = bool(log_);
    event({{"type", "plant_summary"},
           {"receipt_counts", {{"ok", ok_count_},
                               {"rejected", rejected_count_},
                               {"late", late_count_},
                               {"duplicate", duplicate_count_}}},
           {"free_evolution_substeps", free_substeps_},
           {"stopped_at_substep", clock_.sim_ns / p1_plant::kSubstepNs},
           {"flushed", flushed},
           {"sim_ns_end", clock_.sim_ns},
           {"final_state",
            {state_[0], state_[1], state_[2], state_[3], state_[4], state_[5]}}},
          true);
  }

private:
  // 日志锁必须与状态锁分开：pump() 持有状态锁时还要写日志，共用一把
  // 非递归互斥量会在第一个 tick 上自锁。
  void event(const p1::Json & doc, bool flush = false)
  {
    // 诊断只观测 source 写/flush 区间；不为诊断构造或解析 JSON。
    if (diag_trace_)
      diag_note(p1_clock_diag::Record(p1_clock_diag::kSourceIoBegin,
                                      p1_clock_diag::kPlantExecutor,
                                      p1_clock_diag::monotonic_ns())
                    .nums(flush ? 1 : 0, 0));
    std::lock_guard<std::mutex> lock(log_mutex_);
    if (diag_trace_)
      diag_note(p1_clock_diag::Record(p1_clock_diag::kSourceIOLocked,
                                      p1_clock_diag::kPlantExecutor,
                                      p1_clock_diag::monotonic_ns())
                    .nums(flush ? 1 : 0, 0));
    log_ << doc.dump() << '\n';
    if (flush) log_.flush();
    if (diag_trace_)
      diag_note(p1_clock_diag::Record(p1_clock_diag::kSourceIoEnd,
                                      p1_clock_diag::kPlantExecutor,
                                      p1_clock_diag::monotonic_ns())
                    .nums(flush ? 1 : 0, bool(log_) ? 1 : 0));
  }

  // -- 诊断（纯观测）-----------------------------------------------------
  std::uint32_t diag_call() noexcept { return diag_trace_ ? diag_trace_->next_call() : 0; }

  void diag_note(const p1_clock_diag::Record & record) noexcept
  {
    if (diag_trace_) diag_trace_->append(record.get());
  }

  static std::int64_t diag_at() noexcept { return p1_clock_diag::monotonic_ns(); }

  /// 物理子步跨度：只在真实 step_once 调用前后记录。
  void diag_step(p1_clock_diag::EventId event, std::uint32_t call,
                 p1_clock_diag::KindId kind, std::int64_t sim_before,
                 std::int64_t substeps) noexcept
  {
    if (!diag_trace_) return;
    diag_note(p1_clock_diag::Record(event, p1_clock_diag::kPlantExecutor, diag_at())
                  .call(call)
                  .kind(kind)
                  .sim(clock_.sim_ns)
                  .nums(sim_before, substeps));
  }

  void diag_receive_end(std::uint32_t call, const p1_plant::Admission & admission,
                        std::int64_t catch_up_substeps,
                        std::int64_t scheduled_substeps) noexcept
  {
    if (!diag_trace_) return;
    const p1_clock_diag::DispositionId disposition =
        admission.disposition == "ok"       ? p1_clock_diag::kDispOk
        : admission.disposition == "late"   ? p1_clock_diag::kDispLate
        : admission.disposition == "duplicate"
            ? p1_clock_diag::kDispDuplicate
            : p1_clock_diag::kDispRejected;
    diag_note(p1_clock_diag::Record(p1_clock_diag::kReceiveEnd,
                                    p1_clock_diag::kPlantExecutor, diag_at())
                  .call(call)
                  .disposition(disposition)
                  .text(admission.reason)
                  .sim(clock_.sim_ns)
                  .ident(scheduled_.has_value() ? scheduled_->sequence : 0,
                         execution_index_)
                  .nums(0, admission.executes ? 1 : 0, catch_up_substeps,
                        scheduled_substeps));
  }

  void diag_end_pump(std::uint32_t call, p1_clock_diag::ExitId exit) noexcept
  {
    if (!diag_trace_) return;
    diag_note(p1_clock_diag::Record(p1_clock_diag::kPumpEnd, p1_clock_diag::kPlantExecutor,
                                    diag_at())
                  .call(call)
                  .exit(exit)
                  .sim(clock_.sim_ns)
                  .mapped(clock_.steady_of(clock_.sim_ns), clock_.steady_origin_ns));
  }

  /// 发布跨度：begin/end 用同一 call_id，便于与 source_io 行分离归属。
  struct PublishSpan
  {
    Plant * self;
    std::uint32_t call;
    p1_clock_diag::KindId kind;
    std::uint64_t sequence;
    std::uint64_t execution_index;
    PublishSpan(Plant * owner, p1_clock_diag::KindId k, std::uint64_t seq = 0,
                std::uint64_t execution = 0)
        : self(owner), call(owner->diag_call()), kind(k), sequence(seq),
          execution_index(execution)
    {
      if (!self->diag_trace_) return;
      self->diag_note(p1_clock_diag::Record(p1_clock_diag::kPublishBegin,
                                            p1_clock_diag::kPlantExecutor, diag_at())
                          .call(call)
                          .kind(kind)
                          .ident(sequence, execution_index));
    }
    ~PublishSpan()
    {
      if (!self->diag_trace_) return;
      self->diag_note(p1_clock_diag::Record(p1_clock_diag::kPublishEnd,
                                            p1_clock_diag::kPlantExecutor, diag_at())
                          .call(call)
                          .kind(kind)
                          .ident(sequence, execution_index));
    }
  };

  /// clock 发布单独一对事件，带本行有效的 origin 供 mapped=origin+sim 逐段校验。
  void diag_clock_publish(p1_clock_diag::EventId event, std::uint32_t call) noexcept
  {
    if (!diag_trace_) return;
    diag_note(p1_clock_diag::Record(event, p1_clock_diag::kPlantExecutor, diag_at())
                  .call(call)
                  .kind(p1_clock_diag::kKindClock)
                  .sim(clock_.sim_ns)
                  .mapped(clock_.steady_of(clock_.sim_ns), clock_.steady_origin_ns));
  }

  void publish_bootstrap()
  {
    usv_research_interfaces::msg::PlantReceipt receipt;
    receipt.schema_version = "p1-plant-receipt-v3";
    receipt.run_id = run_;
    receipt.boot_id = boot_;
    receipt.contract_hash = hash_;
    receipt.sequence = 0;
    receipt.tick = 0;
    receipt.disposition = "bootstrap";
    receipt.reason = "";
    receipt.execution_index = 0;
    receipt.apply_begin_steady_ns = clock_.steady_origin_ns;
    receipt.apply_end_steady_ns = clock_.steady_origin_ns;
    receipt.executed_begin_steady_ns = clock_.steady_origin_ns;
    receipt.executed_end_steady_ns = clock_.steady_origin_ns;
    receipt.hold_end_steady_ns = clock_.steady_origin_ns;
    receipt.plant_steady_origin_ns = clock_.steady_origin_ns;
    receipt.receive_steady_ns = clock_.steady_origin_ns;
    receipt.executed_steady_ns = clock_.steady_origin_ns;
    receipt.thrust_n[0] = 0.0;
    receipt.thrust_n[1] = 0.0;
    copy_state(receipt.state);
    receipt.sim_ns = 0;
    receipt.state_sample_sim_ns = 0;
    receipt.planned_window_end_sim_ns = 0;
    receipt.clock_identity = p1_plant::kClockIdentity;
    receipt.clock_epoch = 0;
    {
      PublishSpan span(this, p1_clock_diag::kKindBootstrap, 0, 0);
      receipt_pub_->publish(receipt);
    }
    event({{"type", "bootstrap_receipt"},
           {"schema", receipt.schema_version},
           {"run_id", run_},
           {"boot_id", boot_},
           {"contract_hash", hash_},
           {"sequence", 0},
           {"tick", 0},
           {"disposition", "bootstrap"},
           {"reason", ""},
           {"execution_index", 0},
           {"thrust_n", {0.0, 0.0}},
           {"state", state_json()},
           {"plant_steady_origin_ns", clock_.steady_origin_ns},
           {"sim_ns", 0},
           {"state_sample_sim_ns", 0},
           {"planned_window_end_sim_ns", 0},
           {"clock_identity", p1_plant::kClockIdentity},
           {"clock_epoch", 0},
           {"apply_begin_steady_ns", clock_.steady_origin_ns},
           {"apply_end_steady_ns", clock_.steady_origin_ns},
           {"executed_begin_steady_ns", clock_.steady_origin_ns},
           {"executed_end_steady_ns", clock_.steady_origin_ns},
           {"hold_end_steady_ns", clock_.steady_origin_ns},
           {"receive_steady_ns", clock_.steady_origin_ns},
           {"executed_steady_ns", clock_.steady_origin_ns}}, true);
  }

  void copy_state(std::array<double, 6> & target) const
  {
    for (int i = 0; i < 6; ++i) target[i] = state_[i];
  }

  p1::Json state_json() const
  {
    return {state_[0], state_[1], state_[2], state_[3], state_[4], state_[5]};
  }

  /// 按真实时钟把仿真推进到"已到期"的位置。pump 与 receive 共用同一条路径，
  /// 保证任何时刻读到的执行事实都与时钟一致。
  void advance_clock_locked(std::int64_t now)
  {
    const std::uint32_t call = diag_call();
    while (!g_stop && clock_.sim_ns + p1_plant::kSubstepNs <=
                          clock_.sim_of(now))
    {
      const auto thrust = p1_plant::held_thrust(hold_, clock_.sim_ns);
      p1_plant::Vector6d state;
      for (int i = 0; i < 6; ++i) state[i] = state_[i];
      diag_step(p1_clock_diag::kStepBegin, call, p1_clock_diag::kKindReceiveCatchup,
                clock_.sim_ns, 0);
      const bool stepped = core_->step_once(state, thrust);
      diag_step(p1_clock_diag::kStepEnd, call, p1_clock_diag::kKindReceiveCatchup,
                clock_.sim_ns, stepped ? 1 : 0);
      if (!stepped)
      {
        event({{"type", "plant_step_rejected"}, {"sim_ns", clock_.sim_ns}}, true);
        g_stop = true;
        return;
      }
      for (int i = 0; i < 6; ++i) state_[i] = state[i];
      clock_.sim_ns += p1_plant::kSubstepNs;
      if (thrust[0] == 0.0 && thrust[1] == 0.0) ++free_substeps_;
      if (hold_.expired_at(clock_.sim_ns))
      {
        const bool abutting = scheduled_.has_value() &&
                              clock_.sim_ns == scheduled_->begin_sim_ns;
        publish_hold_close(abutting ? "superseded" : "expired",
                           clock_.steady_of(hold_.end_ns),
                           clock_.steady_of(hold_.end_ns));
        hold_.active = false;
        gate_state_.open_hold_end_steady_ns = hold_.end_ns;
        gate_state_.pending_scheduled = false;
      }
      start_due_scheduled_locked();
    }
  }

  /// 单次物理推进：未到期就返回，到期才推进一步。
  void pump()
  {
    const std::int64_t now = p1::monotonic_ns();
    const std::uint32_t call = diag_call();
    diag_note(p1_clock_diag::Record(p1_clock_diag::kPumpBegin,
                                    p1_clock_diag::kPlantExecutor, now)
                  .call(call)
                  .sim(clock_.sim_ns));
    std::lock_guard<std::mutex> lock(mutex_);
    diag_note(p1_clock_diag::Record(p1_clock_diag::kPumpLocked,
                                    p1_clock_diag::kPlantExecutor, diag_at())
                  .call(call)
                  .sim(clock_.sim_ns)
                  .mapped(clock_.steady_of(clock_.sim_ns), clock_.steady_origin_ns)
                  .nums(clock_.steady_origin_ns, now));
    if (g_stop)
    {
      if (!stopped_)
      {
        stopped_ = true;
        // stop：把当前 hold 截到"已推进到的位置"，并声明 reason=stop。
        if (hold_.active && clock_.sim_ns < hold_.end_ns)
        {
          publish_hold_close("stop", clock_.steady_of(clock_.sim_ns),
                             clock_.steady_of(hold_.end_ns));
          hold_.active = false;
        }
        flush_summary_locked();
      }
      diag_end_pump(call, p1_clock_diag::kExitStopping);
      return;
    }

    // 追赶超限：只重设 origin（写 plant_clock_resync），不跳子步、不回退。
    if (clock_.catch_up_exceeded(now, kCatchUpLimitNs))
    {
      const std::int64_t old_origin = clock_.steady_origin_ns;
      clock_.resync(now);
      event({{"type", "plant_clock_resync"},
             {"sim_ns", clock_.sim_ns},
             {"steady_origin_ns", clock_.steady_origin_ns},
             {"steady_ns", now}});
      diag_note(p1_clock_diag::Record(p1_clock_diag::kClockResync,
                                      p1_clock_diag::kPlantExecutor, diag_at())
                    .call(call)
                    .sim(clock_.sim_ns)
                    .nums(old_origin, clock_.steady_origin_ns,
                          clock_.steady_of(clock_.sim_ns), now));
    }

    // 受控仿真是**实时节奏**（RTF = 1）：仿真时间只在对应的稳态时间到达后
    // 才推进一个子步。5 ms 的 pump 只是轮询节拍，不是时间推进源。
    // 若不这样，sim 会以约 10 倍速前进，regulator 会（正确地）判 rtf_unaligned。
    const std::int64_t next_substep_sim = clock_.sim_ns + p1_plant::kSubstepNs;
    if (now < clock_.steady_of(next_substep_sim))
    {
      diag_end_pump(call, p1_clock_diag::kExitIdleNotDue);
      return;
    }

    // 1) 物理推进一个子步。
    const auto thrust = p1_plant::held_thrust(hold_, clock_.sim_ns);
    p1_plant::Vector6d state;
    for (int i = 0; i < 6; ++i) state[i] = state_[i];
    diag_step(p1_clock_diag::kStepBegin, call, p1_clock_diag::kKindPump,
              clock_.sim_ns, 0);
    const bool stepped = core_->step_once(state, thrust);
    diag_step(p1_clock_diag::kStepEnd, call, p1_clock_diag::kKindPump,
              clock_.sim_ns, stepped ? 1 : 0);
    if (!stepped)
    {
      event({{"type", "plant_step_rejected"}, {"sim_ns", clock_.sim_ns}}, true);
      g_stop = true;
      diag_end_pump(call, p1_clock_diag::kExitStepFailed);
      return;
    }
    for (int i = 0; i < 6; ++i) state_[i] = state[i];
    clock_.sim_ns += p1_plant::kSubstepNs;
    if (thrust[0] == 0.0 && thrust[1] == 0.0) ++free_substeps_;

    // 2) hold 到期 → 闭合。
    if (hold_.expired_at(clock_.sim_ns))
    {
      // 只有**紧邻**的后继窗口才算"被接替"（推力连续）。中间有空档、或者
      // 根本没有后继，都是真实的零推力缺口 → expired。
      const bool abutting = scheduled_.has_value() &&
                            clock_.sim_ns == scheduled_->begin_sim_ns;
      publish_hold_close(abutting ? "superseded" : "expired",
                         clock_.steady_of(hold_.end_ns),
                         clock_.steady_of(hold_.end_ns));
      hold_.active = false;
      gate_state_.open_hold_end_steady_ns = hold_.end_ns;
      gate_state_.pending_scheduled = false;
    }

    // 3) 待执行命令在网格边界开始生效：先闭合旧窗口（superseded）再发布 ok。
    start_due_scheduled_locked();

    // 4) 时钟与传感器：同一 sim 派生。
    publish_clock();
    publish_sensors();
    finish_pump_locked();
    diag_end_pump(call, p1_clock_diag::kExitStepped);
  }

  /// 窗口到点即生效。receive() 也必须先调用它：新命令到达时，上一条命令的
  /// 窗口可能已经开始了，而 pump 还没来得及推进（最多滞后一个轮询周期）。
  void start_due_scheduled_locked()
  {
    if (scheduled_.has_value() && clock_.sim_ns >= scheduled_->begin_sim_ns)
    {
      if (hold_.active && hold_.sequence != scheduled_->sequence)
        publish_hold_close("superseded", clock_.steady_of(hold_.end_ns),
                           clock_.steady_of(hold_.end_ns));
      hold_.active = true;
      hold_.begin_ns = clock_.sim_ns;
      hold_.end_ns = clock_.sim_ns + p1_plant::kTickNs;
      hold_.thrust = scheduled_->thrust;
      hold_.sequence = scheduled_->sequence;
      hold_.tick = scheduled_->tick;
      hold_.execution_index = scheduled_->execution_index;
      hold_.clock_epoch = scheduled_->generations[4];
      gate_state_.note_executed_tick(scheduled_->tick);
      gate_state_.open_hold_end_steady_ns = hold_.end_ns;
      gate_state_.pending_scheduled = false;
      gate_state_.pending_begin_steady_ns = 0;
      publish_ok_receipt(*scheduled_, clock_.steady_of(clock_.sim_ns),
                         clock_.steady_of(hold_.end_ns));
      scheduled_.reset();
    }
  }

  void finish_pump_locked()
  {

    // 5) 参考：每 200 ms 边界一次。
    if (clock_.sim_ns % kReferencePeriodNs == 0) publish_reference();
  }

  void receive(const usv_research_interfaces::msg::PlantCommand & message)
  {
    const std::int64_t now = p1::monotonic_ns();
    const std::uint32_t call = diag_call();
    diag_note(p1_clock_diag::Record(p1_clock_diag::kReceiveBegin,
                                    p1_clock_diag::kPlantExecutor, now)
                  .call(call)
                  .kind(p1_clock_diag::kKindReceiveScheduled)
                  .sim(clock_.sim_ns)
                  .ident(message.sequence, message.tick));
    p1_plant::CommandView view;
    std::string producer;
    view.schema_version = message.schema_version;
    producer = message.producer_instance_id;
    view.run_id = message.run_id;
    view.boot_id = message.boot_id;
    view.contract_hash = message.contract_hash;
    view.sequence = message.sequence;
    view.tick = message.tick;
    view.apply_begin_steady_ns = message.apply_begin_steady_ns;
    view.apply_end_steady_ns = message.apply_end_steady_ns;
    view.deadline_steady_ns = message.deadline_steady_ns;
    view.thrust = {message.thrust_n[0], message.thrust_n[1]};
    view.task_generation = message.task_generation;
    view.model_generation = message.model_generation;
    view.config_generation = message.config_generation;
    view.schedule_generation = message.schedule_generation;
    view.clock_epoch = message.clock_epoch;
    view.producer = message.producer_instance_id;

    std::lock_guard<std::mutex> lock(mutex_);
    diag_note(p1_clock_diag::Record(p1_clock_diag::kReceiveLocked,
                                    p1_clock_diag::kPlantExecutor, diag_at())
                  .call(call)
                  .span(1)
                  .sim(clock_.sim_ns)
                  .ident(message.sequence,
                         scheduled_.has_value() ? scheduled_->sequence : 0));
    const std::int64_t advance_before = clock_.sim_ns;
    // 先按**真实时钟**把已到点的窗口推进到位，再判新命令。否则一条在新窗口
    // 到达后才收到的命令会先被拒绝（command_pending），而它的前驱 ok 回执
    // 还在 pump 里排队 —— 回执顺序与执行事实对不上。
    advance_clock_locked(now);
    const std::int64_t advance_after = clock_.sim_ns;
    diag_note(p1_clock_diag::Record(p1_clock_diag::kReceiveLocked,
                                    p1_clock_diag::kPlantExecutor, diag_at())
                  .call(call)
                  .span(1)
                  .sim(clock_.sim_ns)
                  .nums(advance_before, scheduled_.has_value() ? scheduled_->sequence : 0,
                        (advance_after - advance_before) / p1_plant::kSubstepNs, 0));
    // pump 可能滞后一个轮询周期：如果待执行窗口在**墙钟**上已经开始，就把
    // 物理推进到那个边界并让它生效。否则这条命令会被误判 command_pending，
    // 而它的前驱 ok 回执还在 pump 里排队 —— 决策与执行会对不上。
    const std::int64_t scheduled_before = clock_.sim_ns;
    while (scheduled_.has_value() &&
           now >= clock_.steady_of(scheduled_->begin_sim_ns) &&
           clock_.sim_ns < scheduled_->begin_sim_ns)
    {
      const auto thrust = p1_plant::held_thrust(hold_, clock_.sim_ns);
      p1_plant::Vector6d state;
      for (int i = 0; i < 6; ++i) state[i] = state_[i];
      diag_step(p1_clock_diag::kStepBegin, call, p1_clock_diag::kKindReceiveScheduled,
                clock_.sim_ns, 0);
      const bool stepped = core_->step_once(state, thrust);
      diag_step(p1_clock_diag::kStepEnd, call, p1_clock_diag::kKindReceiveScheduled,
                clock_.sim_ns, stepped ? 1 : 0);
      if (!stepped)
      {
        event({{"type", "plant_step_rejected"}, {"sim_ns", clock_.sim_ns}}, true);
        g_stop = true;
        break;
      }
      for (int i = 0; i < 6; ++i) state_[i] = state[i];
      clock_.sim_ns += p1_plant::kSubstepNs;
      if (thrust[0] == 0.0 && thrust[1] == 0.0) ++free_substeps_;
    }
    const std::int64_t scheduled_after = clock_.sim_ns;
    diag_note(p1_clock_diag::Record(p1_clock_diag::kReceiveLocked,
                                    p1_clock_diag::kPlantExecutor, diag_at())
                  .call(call)
                  .span(2)
                  .sim(clock_.sim_ns)
                  .nums(scheduled_before,
                        scheduled_.has_value() ? scheduled_->sequence : 0,
                        (scheduled_after - scheduled_before) / p1_plant::kSubstepNs, 0));
    start_due_scheduled_locked();
    const auto admission = p1_plant::classify(view, gate_, gate_state_, now);
    if (!admission.executes)
    {
      // 迟到命令**不占用**序号：它从未进入执行链，把它记成"已见"会让随后
      // 真正的那条同序号命令被误判 duplicate，整个后续 tick 都无法执行。
      if (admission.disposition != "late")
        gate_state_.note_sequence(view.sequence, view.producer);
      diag_receive_end(call, admission, (advance_after - advance_before) /
                                            p1_plant::kSubstepNs,
                       (scheduled_after - scheduled_before) /
                           p1_plant::kSubstepNs);
      publish_rejection(message, admission, now);
      return;
    }

    // 只登记，不改状态：实际执行发生在网格边界上的 pump。
    gate_state_.note_sequence(view.sequence, view.producer);
    const std::int64_t declared_sim = clock_.sim_of(view.apply_begin_steady_ns);
    const std::int64_t begin_sim =
        clock_.align_up(std::max(clock_.sim_ns, declared_sim));
    Scheduled scheduled;
    scheduled.sequence = view.sequence;
    scheduled.tick = view.tick;
    scheduled.execution_index = execution_index_ + 1;
    scheduled.thrust = view.thrust;
    scheduled.begin_sim_ns = begin_sim;
    scheduled.declared_begin_steady_ns = view.apply_begin_steady_ns;
    scheduled.apply_end_steady_ns = view.apply_end_steady_ns;
    scheduled.deadline_steady_ns = view.deadline_steady_ns;
    scheduled.receive_steady_ns = now;
    scheduled.schema_version = view.schema_version;
    scheduled.producer_instance_id = producer;
    scheduled.generations = {view.task_generation, view.model_generation,
                             view.config_generation, view.schedule_generation,
                             view.clock_epoch};
    scheduled_ = scheduled;
    gate_state_.pending_scheduled = true;
    gate_state_.pending_begin_steady_ns =
        clock_.steady_of(scheduled.begin_sim_ns);
    diag_receive_end(call, admission, (advance_after - advance_before) /
                                          p1_plant::kSubstepNs,
                     (scheduled_after - scheduled_before) / p1_plant::kSubstepNs);
  }

  struct Scheduled
  {
    std::uint64_t sequence = 0;
    std::uint64_t tick = 0;
    std::uint64_t execution_index = 0;
    std::array<double, 2> thrust{0.0, 0.0};
    std::int64_t begin_sim_ns = 0;
    std::int64_t declared_begin_steady_ns = 0;
    std::int64_t apply_end_steady_ns = 0;
    std::int64_t deadline_steady_ns = 0;
    std::int64_t receive_steady_ns = 0;
    std::string schema_version;
    std::array<std::uint64_t, 5> generations{0, 0, 0, 0, 0};
    std::string producer_instance_id;
  };

  void publish_ok_receipt(const Scheduled & scheduled, std::int64_t executed_begin_steady,
                          std::int64_t hold_end_steady)
  {
    ++execution_index_;
    ++ok_count_;
    usv_research_interfaces::msg::PlantReceipt receipt;
    fill_identity(receipt);
    // 回执通告的是**回执**的 schema；命令的 schema 只影响准入，不写进回执。
    receipt.schema_version = "p1-plant-receipt-v3";
    receipt.sequence = scheduled.sequence;
    receipt.tick = scheduled.tick;
    receipt.disposition = "ok";
    receipt.reason = "";
    receipt.execution_index = execution_index_;
    receipt.apply_begin_steady_ns = scheduled.declared_begin_steady_ns;
    receipt.apply_end_steady_ns = scheduled.apply_end_steady_ns;
    receipt.deadline_steady_ns = scheduled.deadline_steady_ns;
    receipt.producer_instance_id = scheduled.producer_instance_id;
    receipt.executed_begin_steady_ns = executed_begin_steady;
    receipt.executed_end_steady_ns = hold_end_steady;
    receipt.hold_end_steady_ns = hold_end_steady;
    receipt.plant_steady_origin_ns = clock_.steady_origin_ns;
    receipt.receive_steady_ns = scheduled.receive_steady_ns;
    receipt.executed_steady_ns = p1::monotonic_ns();
    receipt.thrust_n[0] = scheduled.thrust[0];
    receipt.thrust_n[1] = scheduled.thrust[1];
    copy_state(receipt.state);
    // v3 显式区分状态采样时刻（窗口起点）与计划保持终点时刻。
    receipt.state_sample_sim_ns = executed_begin_steady - clock_.steady_origin_ns;
    receipt.planned_window_end_sim_ns = hold_end_steady - clock_.steady_origin_ns;
    receipt.sim_ns = receipt.planned_window_end_sim_ns;
    receipt.clock_identity = p1_plant::kClockIdentity;
    fill_generations(receipt, scheduled.generations);
    {
      PublishSpan span(this, p1_clock_diag::kKindOkReceipt, receipt.sequence,
                       receipt.execution_index);
      receipt_pub_->publish(receipt);
    }
    event({{"type", "plant_receipt"},
           {"schema", receipt.schema_version},
           {"run_id", run_},
           {"boot_id", boot_},
           {"contract_hash", hash_},
           {"sequence", receipt.sequence},
           {"tick", receipt.tick},
           {"disposition", "ok"},
           {"reason", ""},
           {"execution_index", receipt.execution_index},
           {"thrust_n", {scheduled.thrust[0], scheduled.thrust[1]}},
           {"state", state_json()},
           {"apply_begin_steady_ns", receipt.apply_begin_steady_ns},
           {"apply_end_steady_ns", receipt.apply_end_steady_ns},
           {"deadline_steady_ns", receipt.deadline_steady_ns},
           {"producer_instance_id", receipt.producer_instance_id},
           {"executed_begin_steady_ns", receipt.executed_begin_steady_ns},
           {"executed_end_steady_ns", receipt.executed_end_steady_ns},
           {"hold_end_steady_ns", receipt.hold_end_steady_ns},
           {"plant_steady_origin_ns", receipt.plant_steady_origin_ns},
           {"receive_steady_ns", receipt.receive_steady_ns},
           {"executed_steady_ns", receipt.executed_steady_ns},
           {"sim_ns", receipt.sim_ns},
           {"state_sample_sim_ns", receipt.state_sample_sim_ns},
           {"planned_window_end_sim_ns", receipt.planned_window_end_sim_ns},
           {"clock_identity", receipt.clock_identity},
           {"task_generation", scheduled.generations[0]},
           {"model_generation", scheduled.generations[1]},
           {"config_generation", scheduled.generations[2]},
           {"schedule_generation", scheduled.generations[3]},
           {"clock_epoch", scheduled.generations[4]}}, true);
  }

  void publish_rejection(const usv_research_interfaces::msg::PlantCommand & command,
                         const p1_plant::Admission & admission, std::int64_t now)
  {
    if (admission.disposition == "late") ++late_count_;
    else if (admission.disposition == "duplicate") ++duplicate_count_;
    else ++rejected_count_;
    usv_research_interfaces::msg::PlantReceipt receipt;
    fill_identity(receipt);
    receipt.schema_version = "p1-plant-receipt-v3";
    receipt.sequence = command.sequence;
    receipt.tick = command.tick;
    receipt.disposition = admission.disposition;
    receipt.reason = admission.reason;
    receipt.execution_index = 0;
    receipt.apply_begin_steady_ns = 0;
    receipt.apply_end_steady_ns = 0;
    receipt.deadline_steady_ns = command.deadline_steady_ns;
    receipt.producer_instance_id = command.producer_instance_id;
    receipt.executed_begin_steady_ns = 0;
    receipt.executed_end_steady_ns = 0;
    receipt.hold_end_steady_ns = 0;
    receipt.plant_steady_origin_ns = clock_.steady_origin_ns;
    receipt.receive_steady_ns = now;
    receipt.executed_steady_ns = now;
    receipt.thrust_n[0] = 0.0;
    receipt.thrust_n[1] = 0.0;
    copy_state(receipt.state);
    receipt.sim_ns = clock_.sim_ns;
    receipt.state_sample_sim_ns = clock_.sim_ns;
    receipt.planned_window_end_sim_ns = 0;
    receipt.clock_identity = p1_plant::kClockIdentity;
    receipt.task_generation = command.task_generation;
    receipt.model_generation = command.model_generation;
    receipt.config_generation = command.config_generation;
    receipt.schedule_generation = command.schedule_generation;
    receipt.clock_epoch = command.clock_epoch;
    {
      PublishSpan span(this, p1_clock_diag::kKindRejectionReceipt, receipt.sequence, 0);
      receipt_pub_->publish(receipt);
    }
    event({{"type", "plant_receipt"},
           {"schema", receipt.schema_version},
           {"run_id", run_},
           {"boot_id", boot_},
           {"contract_hash", hash_},
           {"sequence", receipt.sequence},
           {"tick", receipt.tick},
           {"disposition", admission.disposition},
           {"reason", admission.reason},
           {"execution_index", 0},
           {"thrust_n", {0.0, 0.0}},
           {"state", state_json()},
           {"apply_begin_steady_ns", command.apply_begin_steady_ns},
           {"apply_end_steady_ns", command.apply_end_steady_ns},
           {"deadline_steady_ns", command.deadline_steady_ns},
           {"producer_instance_id", command.producer_instance_id},
           {"executed_begin_steady_ns", 0},
           {"executed_end_steady_ns", 0},
           {"hold_end_steady_ns", 0},
           {"plant_steady_origin_ns", clock_.steady_origin_ns},
           {"receive_steady_ns", now},
           {"executed_steady_ns", now},
           {"sim_ns", receipt.sim_ns},
           {"state_sample_sim_ns", receipt.state_sample_sim_ns},
           {"planned_window_end_sim_ns", 0},
           {"clock_identity", receipt.clock_identity},
           {"task_generation", command.task_generation},
           {"model_generation", command.model_generation},
           {"config_generation", command.config_generation},
           {"schedule_generation", command.schedule_generation},
           {"clock_epoch", command.clock_epoch}}, true);
  }

  void publish_hold_close(const char * reason, std::int64_t close_steady,
                          std::int64_t executed_end_steady)
  {
    usv_research_interfaces::msg::PlantHoldClose close;
    close.schema_version = "p1-plant-hold-close-v2";
    close.run_id = run_;
    close.boot_id = boot_;
    close.contract_hash = hash_;
    close.execution_index = hold_.execution_index;
    close.plant_steady_origin_ns = clock_.steady_origin_ns;
    close.close_steady_ns = close_steady;
    close.close_sim_ns = clock_.sim_of(close_steady);
    close.state_sample_sim_ns = clock_.sim_ns;
    close.executed_end_steady_ns = executed_end_steady;
    close.clock_identity = p1_plant::kClockIdentity;
    close.clock_epoch = hold_.clock_epoch;
    close.reason = reason;
    for (int i = 0; i < 6; ++i) close.state[i] = state_[i];
    {
      PublishSpan span(this, p1_clock_diag::kKindHoldClose, close.execution_index, 0);
      hold_close_pub_->publish(close);
    }
    event({{"type", "plant_hold_close"},
           {"schema", close.schema_version},
           {"run_id", run_},
           {"boot_id", boot_},
           {"contract_hash", hash_},
           {"execution_index", close.execution_index},
           {"reason", reason},
           {"plant_steady_origin_ns", clock_.steady_origin_ns},
           {"close_steady_ns", close_steady},
           {"close_sim_ns", close.close_sim_ns},
           {"state_sample_sim_ns", close.state_sample_sim_ns},
           {"executed_end_steady_ns", executed_end_steady},
           {"clock_identity", close.clock_identity},
           {"clock_epoch", close.clock_epoch},
           {"state", state_json()}}, true);
  }

  void fill_identity(usv_research_interfaces::msg::PlantReceipt & receipt) const
  {
    receipt.run_id = run_;
    receipt.boot_id = boot_;
    receipt.contract_hash = hash_;
  }

  void fill_generations(usv_research_interfaces::msg::PlantReceipt & receipt,
                        const std::array<std::uint64_t, 5> & generations) const
  {
    receipt.task_generation = generations[0];
    receipt.model_generation = generations[1];
    receipt.config_generation = generations[2];
    receipt.schedule_generation = generations[3];
    receipt.clock_epoch = generations[4];
  }

  void publish_clock()
  {
    const std::uint32_t call = diag_call();
    diag_clock_publish(p1_clock_diag::kClockPublishBegin, call);
    rosgraph_msgs::msg::Clock message;
    message.clock = rclcpp::Time(clock_.sim_ns, RCL_ROS_TIME);
    clock_pub_->publish(message);
    diag_clock_publish(p1_clock_diag::kClockPublishEnd, call);
    event({{"type", "plant_clock"},
           {"sim_ns", clock_.sim_ns},
           {"steady_ns", clock_.steady_of(clock_.sim_ns)},
           {"steady_origin_ns", clock_.steady_origin_ns},
           {"clock_identity", p1_plant::kClockIdentity}});
  }

  void publish_sensors()
  {
    const auto stamp = rclcpp::Time(clock_.sim_ns, RCL_ROS_TIME);
    nav_msgs::msg::Odometry odom;
    odom.header.stamp = stamp;
    odom.header.frame_id = contract_.at("expected_pose_frame").get<std::string>();
    odom.child_frame_id = contract_.at("expected_child_frame").get<std::string>();
    odom.pose.pose.position.x = state_[0];
    odom.pose.pose.position.y = state_[1];
    odom.pose.pose.orientation.z = std::sin(state_[2] * 0.5);
    odom.pose.pose.orientation.w = std::cos(state_[2] * 0.5);
    odom.twist.twist.linear.x = state_[3];
    odom.twist.twist.linear.y = state_[4];
    odom.twist.twist.angular.z = state_[5];
    {
      PublishSpan span(this, p1_clock_diag::kKindOdom, 0, 0);
      odom_pub_->publish(odom);
    }

    sensor_msgs::msg::Imu imu;
    imu.header.stamp = stamp;
    imu.header.frame_id = contract_.at("expected_child_frame").get<std::string>();
    imu.orientation.z = std::sin(0.5 * state_[2]);
    imu.orientation.w = std::cos(0.5 * state_[2]);
    imu.angular_velocity.z = state_[5];
    {
      PublishSpan span(this, p1_clock_diag::kKindImu, 0, 0);
      imu_pub_->publish(imu);
    }

    event({{"type", "plant_sensors"},
           {"sim_ns", clock_.sim_ns},
           {"steady_ns", clock_.steady_of(clock_.sim_ns)},
           {"clock_identity", p1_plant::kClockIdentity},
           {"state", state_json()}});
  }

  void publish_reference()
  {
    if (path_rows_.empty()) return;
    const auto stamp = rclcpp::Time(clock_.sim_ns, RCL_ROS_TIME);
    nav_msgs::msg::Path path;
    path.header.stamp = stamp;
    path.header.frame_id = contract_.at("expected_pose_frame").get<std::string>();
    for (const auto & row : path_rows_)
    {
      geometry_msgs::msg::PoseStamped pose;
      pose.header = path.header;
      pose.pose.position.x = row[0];
      pose.pose.position.y = row[1];
      pose.pose.orientation.z = std::sin(row[2] * 0.5);
      pose.pose.orientation.w = std::cos(row[2] * 0.5);
      path.poses.push_back(pose);
    }
    {
      PublishSpan span(this, p1_clock_diag::kKindPath, 0, 0);
      path_pub_->publish(path);
    }

    const auto & prof = profile_rows_.empty() ? path_rows_ : profile_rows_;
    std_msgs::msg::Float64MultiArray profile;
    profile.layout.dim.resize(4);
    profile.layout.dim[0].label = "stamp_sec:" + std::to_string(stamp.seconds());
    profile.layout.dim[0].size = static_cast<int>(prof.size());
    profile.layout.dim[1].label =
        "stamp_nanosec:" + std::to_string(stamp.nanoseconds() % 1000000000LL);
    profile.layout.dim[1].size = static_cast<int>(prof.size());
    profile.layout.dim[2].label = "rows";
    profile.layout.dim[2].size = static_cast<int>(prof.size());
    profile.layout.dim[3].label = "cols";
    profile.layout.dim[3].size = 4;
    for (const auto & row : prof)
      for (double value : row) profile.data.push_back(value);
    {
      PublishSpan span(this, p1_clock_diag::kKindProfile, 0, 0);
      profile_pub_->publish(profile);
    }
  }

  static std::vector<std::array<double, 4>> load_path(const std::string & file)
  {
    std::ifstream input(file);
    if (!input) throw std::runtime_error("scenario path unreadable: " + file);
    std::vector<std::array<double, 4>> rows;
    double a, b, c, d;
    while (input >> a >> b >> c >> d) rows.push_back({a, b, c, d});
    if (rows.size() < 2) throw std::runtime_error("scenario path needs at least two rows");
    return rows;
  }

  void flush_summary_locked()
  {
    if (summary_written_) return;
    summary_written_ = true;
    const bool flushed = bool(log_);
    event({{"type", "plant_summary"},
           {"receipt_counts", {{"ok", ok_count_},
                               {"rejected", rejected_count_},
                               {"late", late_count_},
                               {"duplicate", duplicate_count_}}},
           {"free_evolution_substeps", free_substeps_},
           {"stopped_at_substep", clock_.sim_ns / p1_plant::kSubstepNs},
           {"flushed", flushed},
           {"sim_ns_end", clock_.sim_ns},
           {"plant_model_file", hydro_info_.source_path},
           {"plant_model_overridden", hydro_info_.overridden},
           {"controller_nominal_hash", hydro_nominal_hash_},
           {"plant_actual_hash", hydro_actual_hash_},
           {"final_state", state_json()}}, true);
  }

  std::string run_, boot_, hash_, contract_file_, source_, plant_model_file_;
  std::string hydro_nominal_hash_, hydro_actual_hash_;
  p1::Json contract_;
  p1_plant::HydroLoadResult hydro_info_;
  double state_[6]{};
  p1_plant::SimClock clock_;
  p1_plant::HoldWindow hold_;
  p1_plant::PlantGateState gate_state_;
  p1_plant::GateContext gate_;
  std::optional<Scheduled> scheduled_;
  std::unique_ptr<p1_plant::PlantCore> core_;
  std::vector<std::array<double, 4>> path_rows_;
  std::vector<std::array<double, 4>> profile_rows_;

  std::uint64_t execution_index_ = 0;
  std::uint64_t ok_count_ = 0, rejected_count_ = 0, late_count_ = 0,
                duplicate_count_ = 0, free_substeps_ = 0;
  bool stopped_ = false, summary_written_ = false;

  std::string diag_file_;
  std::unique_ptr<p1_clock_diag::BoundedTrace<kPlantTraceCapacity>> diag_trace_;
  std::unique_ptr<p1_clock_diag::Diagnostics> diag_;

  std::ofstream log_;
  std::mutex mutex_;        // 状态机（pump/receive）
  std::mutex log_mutex_;    // source 文件
  rclcpp::Subscription<usv_research_interfaces::msg::PlantCommand>::SharedPtr sub_;
  rclcpp::Publisher<usv_research_interfaces::msg::PlantReceipt>::SharedPtr receipt_pub_;
  rclcpp::Publisher<usv_research_interfaces::msg::PlantHoldClose>::SharedPtr hold_close_pub_;
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_pub_;
  rclcpp::Publisher<sensor_msgs::msg::Imu>::SharedPtr imu_pub_;
  rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr path_pub_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr profile_pub_;
  rclcpp::Publisher<rosgraph_msgs::msg::Clock>::SharedPtr clock_pub_;
  rclcpp::TimerBase::SharedPtr pump_timer_;
};

void Plant::close_diagnostics() noexcept
{
  if (!diag_) return;
  const bool ok = diag_->flush();
  fprintf(stdout, "CLOCK_DIAGNOSTICS_FLUSH_SUCCESS=%s\n", ok ? "true" : "false");
}

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv, rclcpp::InitOptions(),
               rclcpp::SignalHandlerOptions::None);
  std::signal(SIGINT, on_signal);
  std::signal(SIGTERM, on_signal);
  try
  {
    auto node = std::make_shared<Plant>();
    rclcpp::executors::SingleThreadedExecutor exec;
    exec.add_node(node);
    while (!g_stop && rclcpp::ok())
    {
      exec.spin_some(std::chrono::milliseconds(10));
    }
    exec.remove_node(node);
    node->stop_and_flush();
    // executor 已移除、原 source 已收尾、状态锁作用域已退出：此刻才不会与
    // 仍在写 trace 的 writer 并发。
    node->close_diagnostics();
    node.reset();
    rclcpp::shutdown();
    return 0;
  }
  catch (const std::exception & error)
  {
    fprintf(stderr, "plant fatal: %s\n", error.what());
    rclcpp::shutdown();
    return 1;
  }
}
