// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include <atomic>
#include <condition_variable>
#include <csignal>
#include <deque>
#include <mutex>
#include <optional>
#include <thread>
#include <rclcpp/rclcpp.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <nav_msgs/msg/path.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <std_msgs/msg/float64.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/string.hpp>
#include <mavros_msgs/msg/state.hpp>
#include <rosgraph_msgs/msg/clock.hpp>
#include "usv_research_interfaces/msg/applied_control.hpp"
#include "usv_research_interfaces/msg/plant_command.hpp"
#include "usv_research_interfaces/msg/plant_receipt.hpp"
#include "usv_research_interfaces/msg/plant_hold_close.hpp"
#include "p1_receipt_anchor.hpp"
#include "usv_nmpc/p1_input_core.hpp"
#include "protocol.hpp"
#include "p1_model_reference.hpp"
#include "p1_admission.hpp"
#include "p1_clock_window.hpp"
#include "p1_worker_liveness.hpp"
#include "p1_preparation_barrier.hpp"
#include "p1_capability_lease.hpp"
#include "p1_tick_barrier.hpp"
#include "p1_clock_diagnostics.hpp"
#include "p1_shipboard_commissioning.hpp"
#include "p1_shipboard_dry_run.hpp"
namespace {
/// 诊断缓冲上限：订阅 executor 与 tick 线程各一条单生产者流。
constexpr std::size_t kCallbackTraceCapacity=65536;
constexpr std::size_t kTickTraceCapacity=16384;
std::atomic<bool> stop_requested{false};
void stop_signal(int){stop_requested=true;}
// 本进程的运行版本（**运行轴**）：task/config 是运行身份，model 是本拍使用的
// 计划目标代，schedule/epoch 是计划网格身份。准入把计划轴与运行轴分开比较，
// 所以这里保留一个便于决策行落盘的聚合值，但**不**用它做准入判定。
struct RunVersion {uint64_t task=1,model=1,config=1,schedule=1,epoch=0;
  bool operator==(const RunVersion & v)const{return task==v.task&&model==v.model&&config==v.config&&schedule==v.schedule&&epoch==v.epoch;}};
}
// One bounded logging queue. Tick never waits for disk or observation DDS.
class Sink {
 public:
  struct Item {p1::Json event;std::optional<p1::Decision> decision;};
  Sink(const std::string & path,size_t capacity,rclcpp::Publisher<p1::Decision>::SharedPtr publisher):capacity_(capacity),publisher_(publisher) {
    file_.open(path,std::ios::out|std::ios::app);if(!file_)throw std::runtime_error("source log unavailable");thread_=std::thread([this]{loop();});
  }
  ~Sink(){close();}
  bool add(p1::Json e,std::optional<p1::Decision> d=std::nullopt){std::lock_guard<std::mutex> l(mutex_);generated_++;if(closing_||q_.size()>=capacity_){dropped_++;failed_=true;return false;}q_.push_back({std::move(e),std::move(d)});cv_.notify_one();return true;}
  bool failed()const{return failed_;}
  // 无锁 POD 快照：只读既有原子计数，不加锁、不分配、不触碰队列。
  struct Counters {std::uint64_t generated,emitted,dropped;bool failed;};
  Counters counters()const noexcept{return {generated_.load(),emitted_.load(),dropped_.load(),failed_.load()};}
  void close(){if(!thread_.joinable())return;{std::lock_guard<std::mutex> l(mutex_);closing_=true;}cv_.notify_all();thread_.join();}
 private:
  void loop(){for(;;){Item i;{std::unique_lock<std::mutex> l(mutex_);cv_.wait(l,[this]{return closing_||!q_.empty();});if(q_.empty()&&closing_)break;i=std::move(q_.front());q_.pop_front();}
    try{if(i.decision)publisher_->publish(*i.decision);file_<<i.event.dump()<<'\n';if(!file_)failed_=true;else emitted_++;}catch(...){failed_=true;}}
    file_<<p1::Json{{"type","source_summary"},{"generated",generated_.load()},{"emitted",emitted_.load()},{"dropped",dropped_.load()},{"normal_source_complete",!failed_.load()&&generated_==emitted_},{"finished_ns",p1::monotonic_ns()}}.dump()<<'\n';file_.flush();if(!file_)failed_=true;
  }
  size_t capacity_;std::ofstream file_;std::mutex mutex_;std::condition_variable cv_;std::deque<Item> q_;bool closing_=false;std::thread thread_;std::atomic<uint64_t> generated_{0},emitted_{0},dropped_{0};std::atomic<bool> failed_{false};rclcpp::Publisher<p1::Decision>::SharedPtr publisher_;
};
class Regulator final:public rclcpp::Node {
 public:
  Regulator():Node("p1_regulator") {
    run_=declare_parameter<std::string>("run_id","");hash_=declare_parameter<std::string>("contract_hash","");mode_=declare_parameter<std::string>("mode","shadow");
    // 空串 = 完全禁用：不分配缓冲、不额外读时钟、不创建文件。
    diag_file_=declare_parameter<std::string>("clock_diagnostics_file","");
    // require 版而不是 validate 版：Frozen 合同 + execute 必须在这里就被 B5/M4 拒绝，
    // 而不是靠一个 false 常量"看起来被锁住"。此处早于任何 publisher 创建。
    c_=p1::load_contract(declare_parameter<std::string>("contract_file",""),hash_);p1::require_runtime_contract_mode(c_,mode_);resources_=p1::resource_limits_from_contract(c_);boot_=declare_parameter<std::string>("boot_id","");if(boot_.empty())boot_=p1::boot_id();nominal_=c_.at("nominal_hash");
    legacy_run_=declare_parameter<std::string>("legacy_run_id","");
    // 方案 A：模型代由计划决定，不是由 regulator 自增。计划字节摘要必须与声明一致，
    // 且计划自身的 grid 必须与合同时基逐位一致（grid_of_plan 内已断言）。
    {const auto plan_file=declare_parameter<std::string>("model_plan_file","");
     const auto plan_sha=declare_parameter<std::string>("model_plan_sha256","");
     p1::contract_require(!plan_file.empty()&&std::regex_match(plan_sha,std::regex("[0-9a-f]{64}")),
                      "model plan identity required");
     const auto plan_text=p1::read_text(plan_file);
     p1::contract_require(p1::digest(plan_text)==plan_sha,"model plan hash mismatch");
     plan_sha_=plan_sha;plan_file_text_=plan_file;
     grid_=p1::grid_of_plan(plan_text,c_);
     registry_=model_reference::default_registry();{const auto chk=registry_.verify_plan_132_json(plan_text,grid_);p1::contract_require(chk.ok,"plan rejected: "+chk.reason);}
     // 计划已通过校验，切换必须开启；默认值是 false，"忘了打开"会让整条链路
     // 静默地只用单代而不报错。
     model_options_.model_switch_enabled=true;}
    params_=p1::solver_params(c_);
    {const auto gp_snap_file=declare_parameter<std::string>("gp_snapshot_file","");
     const auto gp_snap_sha=declare_parameter<std::string>("gp_snapshot_sha256","");
     const auto gp_sched_file=declare_parameter<std::string>("gp_schedule_file","");
     const auto gp_sched_sha=declare_parameter<std::string>("gp_schedule_sha256","");
     gp_allow_ood_fallback_zero_=declare_parameter<bool>("gp_allow_ood_fallback_zero",true);
     nominal_hydro_sha_=p1_gp_snap::canonical_nominal_hydro_sha256(params_.hydro,params_.dt,4);
     gp_registry_=p1_gp_snap::GpSnapshotRegistry::initialize_from_params(
         gp_snap_file,gp_snap_sha,gp_sched_file,gp_sched_sha,nominal_hydro_sha_);
     ppo_enabled_=declare_parameter<bool>("ppo_enabled",false);
     ppo_lambda_pi_=declare_parameter<double>("ppo_lambda_pi",0.0);
     if(!std::isfinite(ppo_lambda_pi_)||ppo_lambda_pi_<0.0)
       throw std::runtime_error("ppo_lambda_pi must be finite and >= 0");
     ppo_expected_policy_sha_=declare_parameter<std::string>("ppo_expected_policy_sha256","");
     ppo_expected_obs_contract_=declare_parameter<std::string>("ppo_expected_obs_contract","scheme-a-ppo-obs-post-update-v1");
     ppo_max_age_ns_=declare_parameter<int64_t>("ppo_max_age_ns",450000000LL);
     if(ppo_max_age_ns_<=0)throw std::runtime_error("ppo_max_age_ns must be > 0");}
expected_worker_pid_=declare_parameter<int64_t>("worker_pid",0);
    worker_liveness_=std::make_unique<p1::WorkerLiveness>(expected_worker_pid_);
    // 实船调试服务接管：唯一插入点。这里提前 return，跳过旧 observer /
    // preparation_barrier / tick_barrier / capability_lease / limits / positive /
    // frame 整段构造 —— 那些字段属于控制链，本模式一个都不碰。
    if(mode_==p1::shipboard_commissioning_mode||
       c_.at("schema").get<std::string>()==p1::shipboard_commissioning_schema){
      start_shipboard_mode(false);
      return;
    }
    if(mode_==p1::shipboard_dry_run_mode||
       c_.at("schema").get<std::string>()==p1::shipboard_dry_run_schema){
      start_shipboard_mode(true);
      return;
    }
    recording_observer_=declare_parameter<std::string>("recording_observer_node","p1_calibration_driver");
    if(recording_observer_.empty()||recording_observer_.size()>128)throw std::runtime_error("invalid bounded recording observer node");
    if(run_.empty()||run_.size()>128||(mode_!="shadow"&&mode_!="execute"&&mode_!="no_output"&&mode_!="controlled_sim"))throw std::runtime_error("identity/mode invalid");
    if(!diag_file_.empty()&&mode_!="controlled_sim")throw std::runtime_error("clock diagnostics require controlled_sim");
    preparation_barrier_=std::make_unique<p1::PreparationBarrier>(declare_parameter<int64_t>("test_prepare_block_ms",0),mode_,c_.at("fault_injection_enabled").get<bool>());
    tick_barrier_=std::make_unique<p1::TickBarrier>(declare_parameter<int64_t>("test_tick_block_ms",0),mode_,c_.at("fault_injection_enabled").get<bool>());
    test_skip_tick_=declare_parameter<int64_t>("test_skip_tick",0);
    if(test_skip_tick_<0)throw std::runtime_error("invalid negative test_skip_tick");
    if(test_skip_tick_>0){
      const bool faults_ok = mode_ == "controlled_sim"
        ? (c_.contains("controlled_sim_faults_enabled") && c_.at("controlled_sim_faults_enabled").get<bool>())
        : c_.at("fault_injection_enabled").get<bool>();
      if(!faults_ok)throw std::runtime_error("unqualified skip_tick fault injection");
    }
    capability_lease_=std::make_unique<p1::CapabilityLease>(c_.at("worker_capability_receipt_timeout_ns").get<int64_t>());
    limits_.tolerance=c_.at("activation_tolerance").get<p1::State>();limits_.rho=c_.at("rho_n_s");limits_.hold_ns=c_.at("hold_ns");limits_.low=c_.at("command_min_n");limits_.high=c_.at("command_max_n");if(!limits_.valid())throw std::runtime_error("invalid finite limits");
    const std::array<std::string,21> positive={"odom_age_ns","imu_age_ns","mixed_skew_ns","clock_age_ns","clock_pause_confirm_ns","target_sim_slack_ns","tick_jitter_ns","publish_gap_ns","publish_budget_ns","active_watchdog_ns","worker_grace_ns","term_grace_ns","kill_postcheck_ns","shutdown_grace_ns","max_path_points","history_capacity","log_capacity","odom_sim_lag_ns","imu_sim_lag_ns","source_future_slack_ns","recording_ready_timeout_ns"};for(auto & k:positive)if(c_.at(k).get<int64_t>()<=0)throw std::runtime_error("missing/invalid bound: "+k);if(c_.at("recording_ready_timeout_ns").get<int64_t>()>60000000000LL)throw std::runtime_error("invalid finite recording timeout");
    for(const auto & key:{"expected_pose_frame","expected_child_frame","expected_imu_frame"}){const auto frame=c_.at(key).get<std::string>();if(frame.empty()||frame.size()>128)throw std::runtime_error("invalid bounded expected frame");}
    params_=p1::solver_params(c_);ref_=std::make_shared<const usv_mpc::ReferenceInput>();
    job_pub_=create_publisher<p1::Job>("/p1/solve_job",rclcpp::QoS(1).reliable());
    if(mode_=="controlled_sim")plant_pub_=create_publisher<usv_research_interfaces::msg::PlantCommand>("/p1/plant_command",rclcpp::QoS(16).reliable());decision_pub_=create_publisher<p1::Decision>("/p1/execution_decision",rclcpp::QoS(1).reliable());
    sink_=std::make_unique<Sink>(declare_parameter<std::string>("source_file",""),c_.at("log_capacity"),decision_pub_);
    if(mode_=="execute") {left_=create_publisher<std_msgs::msg::Float64>(c_.at("output_topics").at("left").get<std::string>(),rclcpp::QoS(1).reliable());right_=create_publisher<std_msgs::msg::Float64>(c_.at("output_topics").at("right").get<std::string>(),rclcpp::QoS(1).reliable());}
    odom_=create_subscription<nav_msgs::msg::Odometry>(c_.at("input_topics").at("odom").get<std::string>(),rclcpp::SensorDataQoS(),[this](nav_msgs::msg::Odometry::SharedPtr m){odom(*m);});
    imu_=create_subscription<sensor_msgs::msg::Imu>(c_.at("input_topics").at("imu").get<std::string>(),rclcpp::SensorDataQoS(),[this](sensor_msgs::msg::Imu::SharedPtr m){imu(*m);});
    path_=create_subscription<nav_msgs::msg::Path>(c_.at("input_topics").at("path").get<std::string>(),rclcpp::QoS(1).reliable(),[this](nav_msgs::msg::Path::SharedPtr m){path(*m);});
    profile_=create_subscription<std_msgs::msg::Float64MultiArray>(c_.at("input_topics").at("profile").get<std::string>(),rclcpp::QoS(1).reliable(),[this](std_msgs::msg::Float64MultiArray::SharedPtr m){profile(*m);});
    clock_=create_subscription<rosgraph_msgs::msg::Clock>("/clock",rclcpp::ClockQoS(),[this](rosgraph_msgs::msg::Clock::SharedPtr m){clock(*m);});
    candidates_=create_subscription<p1::Candidate>("/p1/solve_candidate",rclcpp::QoS(1).reliable(),[this](p1::Candidate::SharedPtr m){candidate(*m);});
    capabilities_=create_subscription<p1::Capability>("/p1/worker_capability",rclcpp::QoS(1).reliable().transient_local(),[this](p1::Capability::SharedPtr m){capability(*m);});
    if(ppo_enabled_)proposal_sub_=create_subscription<p1::Proposal>("/p1/control_proposal",rclcpp::QoS(4).reliable(),[this](p1::Proposal::SharedPtr m){control_proposal(*m);});
    stop_=create_subscription<std_msgs::msg::Bool>("/p1/stop",rclcpp::QoS(1).reliable(),[this](std_msgs::msg::Bool::SharedPtr m){DiagCallback dspan(diag_callbacks_.get(),p1_clock_diag::kKindStop);if(m->data)stop_requested=true;});
    if(mode_=="shadow")applied_=create_subscription<usv_research_interfaces::msg::AppliedControl>("/research/control/applied",rclcpp::QoS(10).reliable(),[this](usv_research_interfaces::msg::AppliedControl::SharedPtr m){legacy_applied(*m);});
    if(mode_=="controlled_sim"){
      // 唯一执行事实通道：plant 回执与 hold 闭合事件。
      receipt_sub_=create_subscription<usv_research_interfaces::msg::PlantReceipt>("/p1/plant_receipt",rclcpp::QoS(16).reliable().transient_local(),[this](usv_research_interfaces::msg::PlantReceipt::SharedPtr m){receipt(*m);});
      hold_close_sub_=create_subscription<usv_research_interfaces::msg::PlantHoldClose>("/p1/plant_hold_close",rclcpp::QoS(16).reliable(),[this](usv_research_interfaces::msg::PlantHoldClose::SharedPtr m){hold_close(*m);});
      receipts_.restart(p1::digest(run_+boot_));
      plant_producer_=p1::digest(run_+boot_);
    }
    if(mode_=="no_output") {auto now=p1::monotonic_ns();anchor_.known={true,true};anchor_.seq={1,1};anchor_.time={now,now};}
    if(!diag_file_.empty()){
      diag_callbacks_=std::make_unique<p1_clock_diag::BoundedTrace<kCallbackTraceCapacity>>();
      diag_tick_=std::make_unique<p1_clock_diag::BoundedTrace<kTickTraceCapacity>>();
      nlohmann::json header{{"producer","p1_regulator"},{"pid",getpid()},{"run_id",run_},
        {"boot_id",boot_},{"host_boot_id",p1::boot_id()},{"contract_hash",hash_},
        {"stream_capacities",{{"regulator_callbacks",kCallbackTraceCapacity},{"regulator_tick",kTickTraceCapacity}}},
        {"bootstrap_steady_origin_ns",nullptr}};
      diag_=p1_clock_diag::Diagnostics::create(diag_file_,header);
      diag_->add_stream("regulator_callbacks",*diag_callbacks_);
      diag_->add_stream("regulator_tick",*diag_tick_);
    }
    wait_recording_ready();prep_=std::thread([this]{prepare_loop();});tick_=std::thread([this]{tick_loop();});
    sink_->add({{"type","startup"},{"schema","p1-regulator-v1"},{"run_id",run_},{"mode",mode_},{"pid",getpid()},{"boot",boot_},{"clock","CLOCK_MONOTONIC"},{"contract_hash",hash_},{"physical_publisher_endpoints",mode_=="execute"?2:0},{"worker_liveness_policy","linux_pidfd_no_wait"},{"publication_history_policy","full_consecutive_publisher_history"},{"input_anchor_source",mode_=="shadow"?"legacy_publisher":mode_=="execute"?"regulator_publisher":"synthetic_static_fixture"},
      {"anchor_source",mode_=="controlled_sim"?"plant_receipt":"legacy_publisher"},
      {"boot_id",boot_},
      {"typed_command_topics",p1::Json::array({"/p1/plant_command"})},
      {"raw_command_topics",p1::Json::array()},
      {"diagnostic_only",mode_!="execute"}});
  }
  ~Regulator(){stop_requested=true;prep_stop_=true;commission_stop_=true;prep_cv_.notify_all();if(commission_thread_.joinable())commission_thread_.join();if(tick_.joinable())tick_.join();if(prep_.joinable())prep_.join();sink_->close();}
  bool finished()const{return finished_;}
  bool commissioning()const{return commission_active_;}
  int commissioning_exit_code()const{return commission_rc_;}
  bool close_source(){commission_stop_=true;if(commission_thread_.joinable())commission_thread_.join();if(tick_.joinable())tick_.join();prep_stop_=true;prep_cv_.notify_all();if(prep_.joinable())prep_.join();sink_->close();
    if(diag_){const bool diag_ok=diag_->flush();fprintf(stdout,"CLOCK_DIAGNOSTICS_FLUSH_SUCCESS=%s\n",diag_ok?"true":"false");}
    fprintf(stdout,"REGULATOR_CLOSE_FLUSH_SUCCESS=%s\n",sink_->failed()?"false":"true");return !sink_->failed();}
 private:
  static int64_t stamp(const builtin_interfaces::msg::Time & t){return int64_t(t.sec)*1000000000+t.nanosec;}
  struct Snapshot {usv_mpc::Vector6d state=usv_mpc::Vector6d::Zero();std::shared_ptr<const usv_mpc::ReferenceInput> ref;std::vector<usv_mpc::HeldInputEvent> history;std::deque<p1::PublicationEvent> publication_history;p1::Anchor anchor;RunVersion version;uint64_t odom_seq=0,imu_seq=0;int64_t odom_stamp=0,imu_stamp=0,odom_receive=0,imu_receive=0,clock_receive=0,sim=0,freeze=0;bool mixed=false,paused=false,rtf_valid=false;double rtf=0;std::string anchor_producer,anchor_run,anchor_source;};
  struct Preparation {Snapshot s;uint64_t tick;int64_t origin;};
  /// 回执锚点 → 决策行锚点。未 known 时显式返回 unknown，不给默认值。
  p1::Anchor receipt_anchor()const{
    p1::Anchor a;
    if(!receipts_.known())return a;
    a.n={receipts_.thrust()[0],receipts_.thrust()[1]};
    a.seq={receipts_.execution_index(),receipts_.execution_index()};
    a.time={receipts_.anchor_steady_ns(),receipts_.anchor_steady_ns()};
    a.known={true,true};
    return a;}
  Snapshot snapshot_locked(int64_t now){Snapshot s;s.state=state_;s.ref=ref_;s.history.assign(history_.begin(),history_.end());s.anchor=anchor_;if(mode_=="controlled_sim"){s.anchor=receipt_anchor();}s.publication_history=publication_history_;s.version=version_;s.odom_seq=odom_seq_;s.imu_seq=imu_seq_;s.odom_stamp=odom_stamp_;s.imu_stamp=imu_stamp_;s.odom_receive=odom_receive_;s.imu_receive=imu_receive_;s.clock_receive=clock_receive_;s.sim=sim_;s.freeze=now;s.mixed=mixed_;s.paused=paused_;s.rtf_valid=rtf_valid_;s.rtf=rtf_;s.anchor_source=mode_=="shadow"?"legacy_publisher":mode_=="execute"?"regulator_publisher":"synthetic_static_fixture";s.anchor_producer=mode_=="shadow"?legacy_producer_:p1::digest(run_+boot_+std::to_string(getpid()));s.anchor_run=mode_=="shadow"?legacy_run_:run_;return s;}
  // require_committed_execution：受控仿真里"锚点必须有真实执行窗口支撑"。
  // 这条只约束**接受候选**；准备下一拍的求解只需要感知/时钟/锚点链完整，
  // 否则刚发布完命令就永远把自己判成 plant_not_executing。
  std::string eligible(const Snapshot & s,int64_t now,bool require_committed_execution=true) {
    usv_mpc::InputEligibility e;e.odom_received=s.odom_seq>0;e.path_received=!s.ref->path.empty();e.path_size=s.ref->path.size();e.now_s=now/1e9;e.last_odom_s=s.odom_receive/1e9;e.odom_timeout_s=c_.at("odom_age_ns").get<int64_t>()/1e9;
    auto check=usv_mpc::input_eligibility(e);if(!check.first)return check.second;
    if(!s.state.allFinite())return "nonfinite";
    if(s.mixed&&(now-s.imu_receive>c_.at("imu_age_ns").get<int64_t>()||std::abs(s.imu_stamp-s.odom_stamp)>c_.at("mixed_skew_ns").get<int64_t>()))return "mixed_source_age_or_skew";
    if(!s.clock_receive||now-s.clock_receive>c_.at("clock_age_ns").get<int64_t>()||s.paused)return "clock_missing_stale_paused";
    if(!s.rtf_valid)return "rtf_unaligned";
    const p1::SourceAgeLimits source_limits{
      c_.at("odom_age_ns").get<int64_t>(),c_.at("imu_age_ns").get<int64_t>(),
      c_.at("odom_sim_lag_ns").get<int64_t>(),c_.at("imu_sim_lag_ns").get<int64_t>(),
      c_.at("source_future_slack_ns").get<int64_t>()};
    auto source_reason=p1::state_source_check(now,s.sim,s.clock_receive,
      {s.odom_stamp,s.odom_receive},{s.imu_stamp,s.imu_receive},s.mixed,source_limits);
    if(!source_reason.empty())return source_reason;
    auto sync=usv_mpc::profile_sync_state(s.ref->path.size(),s.ref->profile.empty()?-1:s.ref->profile.size(),&s.ref->path_stamp,&s.ref->profile_stamp);
    if(!sync.first){
      sink_->add({{"type","profile_sync_detail"},{"reason",sync.second},
        {"path_len",s.ref->path.size()},{"profile_len",s.ref->profile.size()},
        {"path_stamp_sec",s.ref->path_stamp.first},{"path_stamp_ns",s.ref->path_stamp.second},
        {"profile_stamp_sec",s.ref->profile_stamp.first},{"profile_stamp_ns",s.ref->profile_stamp.second},
        {"processed_ns",p1::monotonic_ns()}});
      return "profile_pair_incomplete:"+sync.second;}
    for(auto & point:s.ref->path)for(double v:point)if(!std::isfinite(v))return "invalid_path";
    // 受控仿真：锚点**只**来自 plant 的 ok 回执。没有 bootstrap 回执就是
    // unknown_anchor（直接失败），不再用 odom 派生一个"静止锚点"来开路。
    if(mode_=="controlled_sim"){
      if(!receipts_.known())return "unknown_anchor";
      if(!receipts_.normal_complete())return "receipt_chain_incomplete";
      if(require_committed_execution&&command_pending_&&
         receipts_.execution_index()<=pending_execution_before_)
        return "plant_not_executing";
      return "";
    }
    if(!(s.anchor.known[0]&&s.anchor.known[1]))return "unknown_anchor";
    return "";
  }

  // Startup-only recording arm; no control/preparation thread exists yet.
  // -- 诊断（纯观测）-----------------------------------------------------
  std::uint32_t diag_call(p1_clock_diag::BoundedTrace<kCallbackTraceCapacity> * t)noexcept{return t?t->next_call():0;}
  std::uint32_t diag_call_tick()noexcept{return diag_tick_?diag_tick_->next_call():0;}
  /// 订阅 executor 流的通用跨度：只记 kind，不复制 payload。
  struct DiagCallback{
    p1_clock_diag::BoundedTrace<kCallbackTraceCapacity> * trace;std::uint32_t call;p1_clock_diag::KindId kind;
    DiagCallback(p1_clock_diag::BoundedTrace<kCallbackTraceCapacity> * t,p1_clock_diag::KindId k)
      :trace(t),call(t?t->next_call():0),kind(k){
      if(trace)trace->append(p1_clock_diag::Record(p1_clock_diag::kCallbackBegin,p1_clock_diag::kRegulatorCallbacks,p1_clock_diag::monotonic_ns()).call(call).kind(kind).get());}
    ~DiagCallback(){
      if(trace)trace->append(p1_clock_diag::Record(p1_clock_diag::kCallbackEnd,p1_clock_diag::kRegulatorCallbacks,p1_clock_diag::monotonic_ns()).call(call).kind(kind).get());}
  };
  /// tick 线程流：同样的跨度语义，但写指针独立。
  struct DiagTick{
    p1_clock_diag::BoundedTrace<kTickTraceCapacity> * trace;std::uint32_t call;
    DiagTick(p1_clock_diag::BoundedTrace<kTickTraceCapacity> * t,p1_clock_diag::EventId event,std::uint64_t tick_id,std::uint64_t decision_sequence,std::int64_t planned,std::int64_t start,std::int64_t end,std::uint64_t runtime,std::uint64_t grid,std::uint64_t epoch)
      :trace(t),call(t?t->next_call():0){
      if(trace)trace->append(p1_clock_diag::Record(event,p1_clock_diag::kRegulatorTick,p1_clock_diag::monotonic_ns()).call(call).ident(tick_id,decision_sequence).nums(planned,start,end,0).schedule(runtime,grid,epoch).get());}
  };
  void diag_emit(p1_clock_diag::BoundedTrace<kCallbackTraceCapacity> * trace,p1_clock_diag::Record record)noexcept{
    if(trace)trace->append(record.get());}
  void diag_emit_tick(p1_clock_diag::Record record)noexcept{
    if(diag_tick_)diag_tick_->append(record.get());}

  bool named_subscription(const std::string & topic,const std::string & name,bool recorder=false){
    for(const auto & endpoint:get_subscriptions_info_by_topic(topic)){
      if(recorder?endpoint.node_name().find("recorder")!=std::string::npos:endpoint.node_name()==name)return true;
    }
    return false;
  }
  void wait_recording_ready(){
    const int64_t start=p1::monotonic_ns(),timeout=c_.at("recording_ready_timeout_ns").get<int64_t>();
    while(rclcpp::ok()&&!stop_requested&&p1::monotonic_ns()-start<=timeout){
      // 受控仿真：worker 与 plant 就位即可开跑；生产采集才要求 recorder 全程在位。
      const bool sim_ready=mode_=="controlled_sim"&&job_pub_->get_subscription_count()>=1&&
        named_subscription("/p1/solve_job","p1_solver_worker")&&
        named_subscription("/p1/plant_command","p1_x86_plant");
      const bool ready=sim_ready||(job_pub_->get_subscription_count()>=2&&decision_pub_->get_subscription_count()>=2&&
        named_subscription("/p1/solve_job","p1_solver_worker")&&named_subscription("/p1/solve_job","",true)&&
        named_subscription("/p1/execution_decision",recording_observer_)&&named_subscription("/p1/execution_decision","",true)&&
        named_subscription("/p1/solve_candidate","p1_regulator")&&named_subscription("/p1/solve_candidate","",true));
      if(ready){
        if(!sink_->add({{"type","recording_ready"},{"run_id",run_},{"ready_ns",p1::monotonic_ns()},
          {"job_matched",job_pub_->get_subscription_count()},{"decision_matched",decision_pub_->get_subscription_count()},{"observer_node",recording_observer_}}))
          throw std::runtime_error("recording readiness source unavailable");
        return;
      }
      if(sink_->failed())throw std::runtime_error("recording readiness source failed");
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    sink_->add({{"type","recording_ready_failed"},{"run_id",run_},{"observer_node",recording_observer_},{"timeout_ns",timeout},{"finished_ns",p1::monotonic_ns()}});
    throw std::runtime_error("recording readiness timeout or stop");
  }

  std::optional<uint64_t> invalidate_locked(){admission_.invalidate();candidate_.reset();std::lock_guard<std::mutex> l(prep_mutex_);std::optional<uint64_t> target;if(pending_)target=pending_->tick+1;pending_.reset();return target;}
  void unusable_locked(const std::string & reason,int64_t now){
    if(worker_unusable_)return;
    const bool candidate_before=bool(candidate_);
    worker_unusable_=true;worker_valid_=false;normal_complete_=false;auto cleared_pending=invalidate_locked();
    sink_->add({{"type","worker_unusable_transition"},{"reason",reason},{"check_ns",now},{"processed_ns",p1::monotonic_ns()},
      {"worker_pid",expected_worker_pid_},{"worker_instance",worker_instance_},{"active_job",worker_active_},
      {"capability_last_valid_commit_ns",capability_lease_->last_valid_ns()},{"capability_timeout_ns",capability_lease_->timeout_ns()},
      {"candidate_before",candidate_before},{"pending_before",cleared_pending.has_value()},{"cleared_pending_target_tick",cleared_pending.value_or(0)},{"candidate_after",false},{"pending_after",false},
      {"policy","stop_new_submit_commits_and_activation; already_committed_DDS_tail_may_finish"}});
    prep_cv_.notify_all();
  }
  void check_worker_locked(int64_t now){const auto reason=worker_liveness_->reason();if(!reason.empty())unusable_locked(reason,now);if(!worker_unusable_){const auto expired=capability_lease_->check(now);if(!expired.empty())unusable_locked(expired,now);}}
  void odom(const nav_msgs::msg::Odometry & m){DiagCallback dspan(diag_callbacks_.get(),p1_clock_diag::kKindOdom);auto now=p1::monotonic_ns();auto & p=m.pose.pose.position;auto & q=m.pose.pose.orientation;auto & t=m.twist.twist;std::array<double,5> a={p.x,p.y,t.linear.x,t.linear.y,t.angular.z};std::array<double,4> quat={q.x,q.y,q.z,q.w};bool valid=usv_mpc::admit_odom(a,quat)&&m.header.frame_id==c_.at("expected_pose_frame")&&m.child_frame_id==c_.at("expected_child_frame");std::lock_guard<std::mutex> l(mutex_);++odom_received_;
    if(valid){
      state_=usv_mpc::compose_odom(a,quat);odom_seq_=odom_received_;odom_stamp_=stamp(m.header.stamp);odom_receive_=now;mixed_=false;}
    sink_->add({{"type","odom_admission"},{"sequence",odom_received_},{"valid",valid},{"pose_frame",m.header.frame_id.substr(0,128)},{"pose_frame_truncated",m.header.frame_id.size()>128},{"child_frame",m.child_frame_id.substr(0,128)},{"child_frame_truncated",m.child_frame_id.size()>128},{"accepted_sequence",odom_seq_},{"stamp_ns",stamp(m.header.stamp)},{"receive_ns",now},{"state",std::array<double,6>{state_[0],state_[1],state_[2],state_[3],state_[4],state_[5]}}});
  }
  void imu(const sensor_msgs::msg::Imu & m){DiagCallback dspan(diag_callbacks_.get(),p1_clock_diag::kKindImu);auto now=p1::monotonic_ns();std::lock_guard<std::mutex> l(mutex_);++imu_received_;const bool valid=usv_mpc::admit_imu(m.angular_velocity.z)&&m.header.frame_id==c_.at("expected_imu_frame");if(valid){usv_mpc::compose_imu(state_,m.angular_velocity.z);imu_seq_=imu_received_;imu_stamp_=stamp(m.header.stamp);imu_receive_=now;mixed_=true;}sink_->add({{"type","imu_admission"},{"sequence",imu_received_},{"valid",valid},{"frame_id",m.header.frame_id.substr(0,128)},{"frame_truncated",m.header.frame_id.size()>128},{"r_value",m.angular_velocity.z},{"accepted_sequence",imu_seq_},{"stamp_ns",stamp(m.header.stamp)},{"receive_ns",now}});}
  void path(const nav_msgs::msg::Path & m){DiagCallback dspan(diag_callbacks_.get(),p1_clock_diag::kKindPath);auto next=std::make_shared<usv_mpc::ReferenceInput>();std::string fingerprint;
    const auto resource=p1::check_path_resources(m,resources_);const bool resource_ok=bool(resource);
    bool valid=resource_ok&&m.header.frame_id==c_.at("expected_pose_frame");
    if(valid)for(auto & p:m.poses){auto & q=p.pose.orientation;double yaw=usv_mpc::quaternion_to_yaw(q.x,q.y,q.z,q.w);if(!std::isfinite(p.pose.position.x)||!std::isfinite(p.pose.position.y)||!std::isfinite(yaw)){valid=false;break;}next->path.push_back({p.pose.position.x,p.pose.position.y,yaw});}
    if(!valid)next->path.clear();fingerprint=p1::digest(p1::Json{{"frame",resource_ok?m.header.frame_id:std::string("resource_rejected")},{"path",next->path}}.dump());
    std::lock_guard<std::mutex> l(mutex_);next->profile=ref_->profile;next->profile_stamp=ref_->profile_stamp;next->profile_sequence=ref_->profile_sequence;next->path_sequence=++path_seq_;next->path_stamp={m.header.stamp.sec,int(m.header.stamp.nanosec)};
    if(fingerprint!=path_fingerprint_||next->path.size()<2){version_.task++;path_fingerprint_=fingerprint;invalidate_locked();}
    ref_=next;sink_->add({{"type","path_version"},{"received_sequence",path_seq_},{"task_generation",version_.task},{"fingerprint",fingerprint},{"points",next->path.size()},{"valid",valid},{"resource_valid",resource_ok},{"received_points",m.poses.size()},{"frame_bytes",m.header.frame_id.size()},{"processed_ns",p1::monotonic_ns()}});
  }
  void profile(const std_msgs::msg::Float64MultiArray & m){DiagCallback dspan(diag_callbacks_.get(),p1_clock_diag::kKindProfile);auto next=std::make_shared<usv_mpc::ReferenceInput>();const auto resource=p1::check_profile_resources(m,resources_);const bool metadata_ok=bool(resource);
    bool valid=metadata_ok&&!m.data.empty()&&m.data.size()%4==0&&m.data.size()/4<=resources_.max_profile_rows;std::vector<std::string> labels;if(metadata_ok)for(auto & d:m.layout.dim)labels.push_back(d.label);bool stamp_ok=false;if(metadata_ok)next->profile_stamp=usv_mpc::parse_profile_stamp(labels,stamp_ok);if(!stamp_ok)next->profile_stamp={-1,-1};
    if(valid){for(size_t i=0;i<m.data.size()/4;++i){std::array<double,4> r={m.data[4*i],m.data[4*i+1],m.data[4*i+2],m.data[4*i+3]};if(!p1::finite_array(r)||(i&&r[3]<=m.data[4*(i-1)+3])){valid=false;break;}next->profile.push_back(r);}}if(!valid)next->profile.clear();auto fp=p1::digest(p1::Json(next->profile).dump());
    std::lock_guard<std::mutex> l(mutex_);next->path=ref_->path;next->path_stamp=ref_->path_stamp;next->path_sequence=ref_->path_sequence;next->profile_sequence=++profile_seq_;if(fp!=profile_fingerprint_){version_.task++;profile_fingerprint_=fp;invalidate_locked();}ref_=next;sink_->add({{"type","profile_version"},{"received_sequence",profile_seq_},{"task_generation",version_.task},{"fingerprint",fp},{"rows",next->profile.size()},{"valid",valid},{"resource_valid",metadata_ok&&m.data.size()<=resources_.max_profile_rows*4},{"received_data_elements",m.data.size()},{"received_dims",m.layout.dim.size()},{"processed_ns",p1::monotonic_ns()}});
  }
  void clock(const rosgraph_msgs::msg::Clock & m){auto now=p1::monotonic_ns(),s=stamp(m.clock);
    const std::uint32_t dcall=diag_call(diag_callbacks_.get());
    diag_emit(diag_callbacks_.get(),p1_clock_diag::Record(p1_clock_diag::kClockCallbackBegin,p1_clock_diag::kRegulatorCallbacks,now).call(dcall).kind(p1_clock_diag::kKindClock).sim(s).nums(sim_,clock_receive_).ident(static_cast<std::uint64_t>(last_clock_advance_),0).schedule(version_.schedule,grid_.schedule_generation,version_.epoch));
    std::lock_guard<std::mutex> l(mutex_);
    diag_emit(diag_callbacks_.get(),p1_clock_diag::Record(p1_clock_diag::kClockCallbackLocked,p1_clock_diag::kRegulatorCallbacks,p1_clock_diag::monotonic_ns()).call(dcall).kind(p1_clock_diag::kKindClock).sim(s).nums(sim_,clock_receive_).ident(static_cast<std::uint64_t>(last_clock_advance_),0).schedule(version_.schedule,grid_.schedule_generation,version_.epoch));
    if(clock_receive_&&(s<sim_||s-sim_>5000000000LL)){
      diag_emit(diag_callbacks_.get(),p1_clock_diag::Record(p1_clock_diag::kClockEpochChange,p1_clock_diag::kRegulatorCallbacks,p1_clock_diag::monotonic_ns()).call(dcall).kind(p1_clock_diag::kKindClock).sim(s).nums(sim_,clock_receive_).ident(static_cast<std::uint64_t>(last_clock_advance_),5000000000ULL).schedule(version_.schedule,grid_.schedule_generation,version_.epoch));
      version_.epoch++;version_.schedule++;clock_window_.reset();rtf_valid_=false;rtf_=0;history_.clear();publication_history_.clear();anchor_.known={false,false};invalidate_locked();}
    if(s!=sim_){const bool was_paused=paused_;const std::int64_t advance_before=last_clock_advance_;last_clock_advance_=now;if(paused_){paused_=false;version_.schedule++;invalidate_locked();}
      if(was_paused)diag_emit(diag_callbacks_.get(),p1_clock_diag::Record(p1_clock_diag::kResume,p1_clock_diag::kRegulatorCallbacks,p1_clock_diag::monotonic_ns()).call(dcall).kind(p1_clock_diag::kKindClock).sim(s).nums(sim_,advance_before).ident(static_cast<std::uint64_t>(last_clock_advance_),0).schedule(version_.schedule,grid_.schedule_generation,version_.epoch));}
    sim_=s;clock_receive_=now;
    const auto estimate=clock_window_.observe(now,s,c_.at("rtf_low").get<double>(),c_.at("rtf_high").get<double>());
    rtf_=estimate.value;rtf_valid_=estimate.valid;
    sink_->add({{"type","clock"},{"sim_ns",s},{"receive_ns",now},{"epoch",version_.epoch},{"schedule_generation",version_.schedule},{"paused",paused_.load()},{"rtf",rtf_},{"rtf_valid",rtf_valid_.load()},{"rtf_window_span_ns",estimate.span_ns},{"rtf_stored_samples",estimate.stored_samples}});
    diag_emit(diag_callbacks_.get(),p1_clock_diag::Record(p1_clock_diag::kClockCallbackEnd,p1_clock_diag::kRegulatorCallbacks,p1_clock_diag::monotonic_ns()).call(dcall).kind(p1_clock_diag::kKindClock).sim(sim_).nums(sim_,clock_receive_).ident(static_cast<std::uint64_t>(last_clock_advance_),0).schedule(version_.schedule,grid_.schedule_generation,version_.epoch));
  }
  void capability(const p1::Capability & m){DiagCallback dspan(diag_callbacks_.get(),p1_clock_diag::kKindCapability);const auto received=p1::monotonic_ns();auto resource=p1::check_capability_resources(m);if(!resource){sink_->add({{"type","resource_rejected"},{"interface","capability"},{"reason",resource.reason},{"field",resource.field},{"observed",resource.observed},{"limit",resource.limit},{"receive_ns",received},{"renewed",false}});return;}std::lock_guard<std::mutex> l(mutex_);const auto now=p1::monotonic_ns();check_worker_locked(now);const auto before=capability_lease_->last_valid_ns();
    const bool identity=m.run_id==run_&&m.boot_id==boot_&&m.contract_hash==hash_&&m.nominal_hash==nominal_&&m.pid==expected_worker_pid_;
    const bool valid=identity&&m.schema_version=="p1-worker-capability-v2"&&m.clock_name=="CLOCK_MONOTONIC"&&m.backend=="acados"&&m.matrix_layout=="column_major"&&m.horizon_steps==20&&m.prediction_dt==.2&&!m.fatal&&!m.worker_instance.empty()&&m.startup_ns>0&&m.fault_injection_enabled==(mode_=="controlled_sim"
        ?(c_.contains("controlled_sim_faults_enabled")&&c_.at("controlled_sim_faults_enabled").get<bool>())
        :c_.at("fault_injection_enabled").get<bool>());
    bool renewed=false;
    if(identity){
      if(!worker_instance_.empty()&&worker_instance_!=m.worker_instance)unusable_locked("worker_instance_changed",now);
      if(m.fatal)unusable_locked("fatal_capability",now);
      if(valid&&!worker_unusable_){renewed=capability_lease_->renew(now);if(renewed){worker_instance_=m.worker_instance;worker_valid_=true;if(m.active_job!=worker_active_){worker_active_=m.active_job;worker_active_since_=now;}}else unusable_locked(capability_lease_->check(now),now);}
    }
    sink_->add({{"type","capability_admission"},{"receive_ns",received},{"validation_commit_ns",now},{"identity_valid",identity},{"valid",valid},{"renewed",renewed},{"terminal_run",worker_unusable_.load()},
      {"lease_last_before_ns",before},{"lease_last_after_ns",capability_lease_->last_valid_ns()},{"lease_timeout_ns",capability_lease_->timeout_ns()},{"source_freshness_available",false},
      {"capability",{{"schema_version",m.schema_version},{"run_id",m.run_id},{"boot_id",m.boot_id},{"contract_hash",m.contract_hash},{"nominal_hash",m.nominal_hash},{"worker_instance",m.worker_instance},{"clock_name",m.clock_name},{"backend",m.backend},{"matrix_layout",m.matrix_layout},{"horizon_steps",m.horizon_steps},{"prediction_dt",m.prediction_dt},{"pid",m.pid},{"startup_ns",m.startup_ns},{"completed_jobs",m.completed_jobs},{"active_job",m.active_job},{"pending_count",m.pending_count},{"fault_injection_enabled",m.fault_injection_enabled},{"fatal",m.fatal},{"reason",m.reason}}}});
  }
  /// 受控仿真的锚点来源：plant 的 ok 回执。每条回执都写一行准入证据，
  /// 检查器据此逐项核对"锚点 = 实际执行起点"。
  void receipt(const usv_research_interfaces::msg::PlantReceipt & m){
    const std::uint32_t dcall=diag_call(diag_callbacks_.get());
    diag_emit(diag_callbacks_.get(),p1_clock_diag::Record(p1_clock_diag::kReceiptCallbackBegin,p1_clock_diag::kRegulatorCallbacks,p1_clock_diag::monotonic_ns()).call(dcall).kind(p1_clock_diag::kKindOkReceipt).ident(m.sequence,m.execution_index).text(m.disposition));
    std::lock_guard<std::mutex> l(mutex_);const auto now=p1::monotonic_ns();
    diag_emit(diag_callbacks_.get(),p1_clock_diag::Record(p1_clock_diag::kReceiptCallbackLocked,p1_clock_diag::kRegulatorCallbacks,now).call(dcall).kind(p1_clock_diag::kKindOkReceipt).ident(m.sequence,m.execution_index).text(m.disposition).nums(receipts_.execution_index(),0));
    // 只有本 regulator 发出的命令所产生的回执属于执行链。刺激注入的命令
    // 也会得到回执（late/duplicate/rejected），把它并进链会伪造出序号断档。
    // bootstrap 是链的根：它由 plant 独立发布，不带 regulator 的生产者身份。
    if(!plant_producer_.empty()&&m.disposition!="bootstrap"&&
       m.producer_instance_id!=plant_producer_){
      sink_->add({{"type","foreign_receipt"},{"sequence",m.sequence},
        {"producer_instance_id",m.producer_instance_id},{"disposition",m.disposition},
        {"reason",m.reason},{"processed_ns",now}});
      diag_emit(diag_callbacks_.get(),p1_clock_diag::Record(p1_clock_diag::kReceiptCallbackEnd,p1_clock_diag::kRegulatorCallbacks,p1_clock_diag::monotonic_ns()).call(dcall).kind(p1_clock_diag::kKindOkReceipt).disposition(p1_clock_diag::kDispForeign).ident(m.sequence,m.execution_index).text(m.disposition));
      return;}
    p1_receipt::ReceiptFacts facts;
    facts.schema_version=m.schema_version;facts.run_id=m.run_id;
    facts.contract_hash=m.contract_hash;facts.producer_instance_id=plant_producer_;
    facts.sequence=m.sequence;facts.tick=m.tick;facts.disposition=m.disposition;
    facts.reason=m.reason;facts.execution_index=m.execution_index;
    facts.thrust={m.thrust_n[0],m.thrust_n[1]};
    facts.executed_begin_steady_ns=m.executed_begin_steady_ns;
    facts.executed_end_steady_ns=m.executed_end_steady_ns;
    facts.hold_end_steady_ns=m.hold_end_steady_ns;
    facts.plant_steady_origin_ns=m.plant_steady_origin_ns;
    facts.sim_ns=m.sim_ns;
    facts.state_sample_sim_ns=m.state_sample_sim_ns;
    facts.planned_window_end_sim_ns=m.planned_window_end_sim_ns;
    facts.clock_identity=m.clock_identity;
    facts.clock_epoch=m.clock_epoch;
    const auto result=receipts_.accept(facts);
    // 任何处置都终结这一条命令的 pending 状态；否则一条 late 回执会把
    // command_pending_ 永久钉住，后续每一拍都判 plant_not_executing。
    if(m.sequence>=pending_sequence_&&pending_sequence_>0)command_pending_=false;
    if(m.disposition=="ok"&&result.accepted){
      // 执行事实由回执决定：anchor 与 held-history 都从真实区间派生。
      anchor_.n={m.thrust_n[0],m.thrust_n[1]};
      anchor_.seq={m.execution_index,m.execution_index};
      anchor_.time={m.executed_begin_steady_ns,m.executed_begin_steady_ns};
      anchor_.known={true,true};
      command_pending_=false;
      // 受控仿真里"发布历史"就是真实执行窗口的历史：候选票据携带的是
      // 出票那一刻的锚点，接受时必须能由这段连续历史证明它演化到了当前锚点。
      // 不记录，则每个候选都被判 anchor_history_incomplete。
      for(int ch=0;ch<2;++ch)
        push_publication_locked({ch,m.execution_index,m.executed_begin_steady_ns,
                                 m.thrust_n[ch],true});
    }
    sink_->add({{"type","plant_receipt_admission"},{"sequence",m.sequence},{"tick",m.tick},
      {"disposition",m.disposition},{"reason",m.reason},{"accepted",result.accepted},
      {"admission_reason",result.reason},{"chain_complete",result.complete},
      {"execution_index",m.execution_index},
      {"executed_begin_steady_ns",m.executed_begin_steady_ns},
      {"executed_end_steady_ns",m.executed_end_steady_ns},
      {"hold_end_steady_ns",m.hold_end_steady_ns},
      {"state_sample_sim_ns",m.state_sample_sim_ns},
      {"planned_window_end_sim_ns",m.planned_window_end_sim_ns},
      {"clock_identity",m.clock_identity},
      {"anchor_known",receipts_.known()},{"processed_ns",now}});
    const p1_clock_diag::DispositionId disposition =
        m.disposition=="ok"?p1_clock_diag::kDispOk
        :m.disposition=="late"?p1_clock_diag::kDispLate
        :m.disposition=="duplicate"?p1_clock_diag::kDispDuplicate
        :m.disposition=="bootstrap"?p1_clock_diag::kDispBootstrap
        :p1_clock_diag::kDispRejected;
    diag_emit(diag_callbacks_.get(),p1_clock_diag::Record(p1_clock_diag::kReceiptCallbackEnd,p1_clock_diag::kRegulatorCallbacks,p1_clock_diag::monotonic_ns()).call(dcall).kind(p1_clock_diag::kKindOkReceipt).disposition(disposition).ident(m.sequence,m.execution_index).nums(result.accepted?1:0,receipts_.execution_index()).text(result.reason));
  }
  /// hold 闭合：窗口内的非零推力已经结束。缺口内推力为零，不做隐式保持。
  void hold_close(const usv_research_interfaces::msg::PlantHoldClose & m){
    const std::uint32_t dcall=diag_call(diag_callbacks_.get());
    diag_emit(diag_callbacks_.get(),p1_clock_diag::Record(p1_clock_diag::kHoldCloseCallbackBegin,p1_clock_diag::kRegulatorCallbacks,p1_clock_diag::monotonic_ns()).call(dcall).kind(p1_clock_diag::kKindHoldClose).ident(m.execution_index,0).sim(m.close_sim_ns).text(m.reason));
    std::lock_guard<std::mutex> l(mutex_);const auto now=p1::monotonic_ns();
    diag_emit(diag_callbacks_.get(),p1_clock_diag::Record(p1_clock_diag::kHoldCloseCallbackLocked,p1_clock_diag::kRegulatorCallbacks,now).call(dcall).kind(p1_clock_diag::kKindHoldClose).ident(m.execution_index,0).sim(m.close_sim_ns).text(m.reason));
    bool truncated=false;
    if(m.reason=="stop")truncated=receipts_.close_at(m.close_steady_ns);
    sink_->add({{"type","plant_hold_close_admission"},{"execution_index",m.execution_index},
      {"schema",m.schema_version},{"boot_id",m.boot_id},
      {"reason",m.reason},{"close_steady_ns",m.close_steady_ns},
      {"close_sim_ns",m.close_sim_ns},{"state_sample_sim_ns",m.state_sample_sim_ns},
      {"clock_identity",m.clock_identity},{"clock_epoch",m.clock_epoch},
      {"truncated",truncated},
      {"executed_end_steady_ns",m.executed_end_steady_ns},{"processed_ns",now}});
    diag_emit(diag_callbacks_.get(),p1_clock_diag::Record(p1_clock_diag::kHoldCloseCallbackEnd,p1_clock_diag::kRegulatorCallbacks,p1_clock_diag::monotonic_ns()).call(dcall).kind(p1_clock_diag::kKindHoldClose).ident(m.execution_index,0).sim(m.close_sim_ns).nums(truncated?1:0,0).text(m.reason));
  }
  void legacy_applied(const usv_research_interfaces::msg::AppliedControl & m){DiagCallback dspan(diag_callbacks_.get(),p1_clock_diag::kKindApplied);
    std::lock_guard<std::mutex> l(mutex_);const auto now=p1::monotonic_ns();
    // 受控仿真不接受任何 publisher 意图通道：执行事实只来自 plant 回执。
    if(mode_=="controlled_sim")return;
    if(m.run_id!=legacy_run_||m.baseline_id!="F5_20261005_atomic_freeze_01"||m.event_semantics!="publisher_command"||m.steady_clock_domain.find(boot_)==std::string::npos||m.map_scale!=1||!p1::finite_array(m.final_n))return;
    if(!legacy_producer_.empty()&&legacy_producer_!=m.producer_instance_id){anchor_.known={false,false};worker_unusable_=true;invalidate_locked();return;}legacy_producer_=m.producer_instance_id;
    if(m.clock_epoch!=version_.epoch){anchor_.known={false,false};history_.clear();publication_history_.clear();invalidate_locked();sink_->add({{"type","legacy_history_reset"},{"reason","epoch_mismatch"},{"processed_ns",now},{"sequence",m.sequence}});return;}
    if(!m.sequence||m.sequence<=legacy_sequence_){sink_->add({{"type","legacy_anchor_ignored"},{"reason","duplicate_or_old_sequence"},{"processed_ns",now},{"sequence",m.sequence}});return;}
    if(legacy_sequence_&&m.sequence!=legacy_sequence_+1){history_.clear();publication_history_.clear();anchor_.known={false,false};invalidate_locked();sink_->add({{"type","legacy_history_reset"},{"reason","sequence_gap"},{"processed_ns",now},{"expected_sequence",legacy_sequence_+1},{"sequence",m.sequence}});}
    legacy_sequence_=m.sequence;
    for(int i=0;i<2;++i){const bool success=i?m.right_publish_success:m.left_publish_success;const int64_t time=i?m.right_publish_start_steady_ns:m.left_publish_start_steady_ns;const int64_t sim=i?m.right_sim_time_ns:m.left_sim_time_ns;
      if(!success||time<=0||time>now||(anchor_.known[i]&&time<=anchor_.time[i])){anchor_.known[i]=false;normal_complete_=false;invalidate_locked();continue;}
      anchor_.n[i]=m.final_n[i];anchor_.seq[i]=m.sequence;anchor_.time[i]=time;anchor_.known[i]=true;push_history_locked({sim,i,m.final_n[i]});push_publication_locked({i,m.sequence,time,m.final_n[i],anchor_.known[i]});
    }
    sink_->add({{"type","legacy_anchor"},{"producer",m.producer_instance_id},{"run_id",m.run_id},{"sequence",m.sequence},{"final_n",m.final_n},{"known",anchor_.known},{"publish_ns",anchor_.time},{"clock_epoch",m.clock_epoch},{"processed_ns",now}});
  }
  void push_publication_locked(const p1::PublicationEvent & e){publication_history_.push_back(e);while(publication_history_.size()>c_.at("history_capacity").get<size_t>())publication_history_.pop_front();}
  void anchor_evidence_locked(const p1::Ticket & t,const p1::Decision & d){
    p1::Json entries=p1::Json::array();
    for(const auto & e:publication_history_)if(e.sequence>=t.anchor.seq[e.channel]&&e.sequence<=anchor_.seq[e.channel])entries.push_back({{"channel",e.channel},{"sequence",e.sequence},{"publish_ns",e.publish_ns},{"n",e.n},{"known",e.known}});
    sink_->add({{"type","anchor_validation"},{"sequence",d.sequence},{"job_id",t.id},{"mode",mode_},{"producer",legacy_producer_},{"run_id",legacy_run_},{"clock_epoch",version_.epoch},{"check_ns",d.activation_commit_ns},{"expected_n",t.anchor.n},{"expected_sequence",t.anchor.seq},{"expected_publish_ns",t.anchor.time},{"expected_known",t.anchor.known},{"actual_n",anchor_.n},{"actual_sequence",anchor_.seq},{"actual_publish_ns",anchor_.time},{"actual_known",anchor_.known},{"entries",entries},{"history_reason",p1::publication_history_check(t.anchor,anchor_,publication_history_)},{"decision_reason",d.reason},{"candidate_accepted",d.candidate_accepted},{"accepted",d.candidate_accepted}});
  }
  void push_history_locked(const usv_mpc::HeldInputEvent & e){if(!history_.empty()&&e.sim_ns<history_.back().sim_ns){history_.clear();publication_history_.clear();anchor_.known={false,false};invalidate_locked();return;}history_.push_back(e);while(history_.size()>c_.at("history_capacity").get<size_t>())history_.pop_front();}
  struct Declared {bool valid=false;std::int64_t begin_ns=0,end_ns=0;double thrust[2]{0,0};};
  bool predict(Snapshot & s,int64_t target_sim){Eigen::Vector2d initial(s.anchor.n[0],s.anchor.n[1]);std::array<bool,2> found{false,false};std::vector<usv_mpc::HeldInputEvent> receipt_history;const std::vector<usv_mpc::HeldInputEvent> * history_source=&s.history;
    if(mode_=="controlled_sim"){const std::int64_t origin=receipts_.steady_origin_ns();
      // hold 事件是稳态时刻；传播历史要的是仿真时刻（odom/sim 同一原点）。
      for(const auto & e:receipts_.held_events())receipt_history.push_back({e.steady_ns-origin,e.channel,e.n});
      // 已声明、尚未走完的窗口是**已经在执行的输入**：不把它并入历史，
      // 候选就会按"窗口内为零推力"做预测，接受时与 plant 的实际回执不符。
      if(declared_.valid&&declared_.end_ns>declared_.begin_ns){
        for(int ch=0;ch<2;++ch){
          receipt_history.push_back({declared_.begin_ns-origin,ch,declared_.thrust[ch]});
          receipt_history.push_back({declared_.end_ns-origin,ch,0.0});}}
      history_source=&receipt_history;}
    const auto & hist = *history_source;
    for(auto & e:hist)if(e.sim_ns<=s.odom_stamp){initial[e.channel]=e.value;found[e.channel]=true;}
    if(mode_!="no_output"&&(!found[0]||!found[1]))return false;return usv_mpc::propagate_publisher_nominal(s.state,s.odom_stamp,target_sim,initial,hist,params_.hydro);}
  void candidate(const p1::Candidate & m){DiagCallback dspan(diag_callbacks_.get(),p1_clock_diag::kKindCandidate);auto resource=p1::check_candidate_resources(m,resources_);if(!resource){sink_->add({{"type","resource_rejected"},{"interface","candidate"},{"job_id",m.job.job_id},{"reason",resource.reason},{"field",resource.field},{"observed",resource.observed},{"limit",resource.limit},{"receive_ns",p1::monotonic_ns()},{"accepted_registration",false}});return;}auto immutable=std::make_shared<const p1::Candidate>(m);auto reason=p1::valid_job(m.job,run_,boot_,hash_,nominal_,worker_instance_);if(reason.empty()&&(m.worker_instance!=worker_instance_||m.backend!="acados"))reason="foreign_worker";
    if(reason.empty()&&(!m.success||!m.prediction_available||!m.solver_invoked))reason="solver_failed";
    if(reason.empty()&&(!p1::finite_array(m.x_prediction)||!p1::finite_array(m.u_prediction)||!p1::finite_array(m.first_control)||!std::isfinite(m.backend_ms)||m.backend_ms<0||m.solve_end_ns<m.solve_start_ns))reason="nonfinite_or_timing";
    if(reason.empty())for(int i=0;i<2;++i)if(std::abs(m.first_control[i]-m.u_prediction[i])>1e-8)reason="first_control_mismatch";
    if(reason.empty())for(int i=0;i<6;++i)if(std::abs(m.x_prediction[i]-m.job.target_state[i])>1e-7)reason="prediction_initial_mismatch";
    std::lock_guard<std::mutex> l(mutex_);auto expected=std::find_if(jobs_.begin(),jobs_.end(),[&](const p1::Job & j){return j.job_id==m.job.job_id;});
    if(reason.empty()&&(expected==jobs_.end()||p1::job_json(*expected)!=p1::job_json(m.job)))reason="job_echo_mismatch";
    auto now=p1::monotonic_ns();
    if(reason.empty()&&(m.applied_gp_generation!=m.job.gp_generation||m.applied_gp_snapshot_sha256!=m.job.gp_snapshot_sha256))reason="gp_echo_mismatch";
    if(reason.empty()&&(!p1::finite_array(m.gp_post_solve_residuals)||!std::isfinite(m.gp_local_approx_max_diff)||m.gp_local_approx_max_diff<0.0))reason="gp_post_solve_nonfinite";
    if(reason.empty()&&!(m.job.freeze_steady_ns<=m.worker_receive_ns&&m.worker_receive_ns<=m.solve_start_ns&&m.solve_start_ns<=m.solve_end_ns&&m.solve_end_ns<=now))reason="native_timing_order";p1::Ticket t;t.id=m.job.job_id;t.target=m.job.target_tick;t.origin=m.job.tick_origin_steady_ns;t.deadline=m.job.deadline_steady_ns;t.target_ns=m.job.target_steady_ns;// 票据的版本是**Job 的版本**（计划网格 + 运行代数），与运行快照的
    // schedule/epoch 不是同一概念；用一个去比另一个会让每个候选都被拒绝。
    t.plan={m.job.model_generation,grid_.schedule_generation,grid_.clock_epoch};
    t.run={m.job.task_generation,m.job.config_generation,grid_.schedule_generation,
           grid_.clock_epoch};t.anchor={m.job.anchor_n,m.job.anchor_sequence,m.job.anchor_publish_ns,m.job.anchor_known};t.prediction=m.job.target_state;
    check_worker_locked(now);if(reason.empty()&&(worker_unusable_||stopping_||sink_->failed()))reason="run_unusable";
    if(reason.empty()){
      // 票据携带 Job 的计划版本；准入的"当前版本"必须是同一坐标系，否则每个候选都被
      // 判为 version_mismatch（而运行代数并不等价于计划网格）。
      p1::PlanIdentity plan_identity{t.plan.model,grid_.schedule_generation,grid_.clock_epoch};
      p1::RunAxes run_axes{version_.task,version_.config,grid_.schedule_generation,grid_.clock_epoch};
      reason=admission_.register_ready(t,current_tick_,now,plan_identity,run_axes);}
    if(reason.empty()){candidate_=std::move(immutable);now=p1::monotonic_ns();if(!admission_.finalize_ready(t.id,now)){candidate_.reset();reason="late_registration_completion";}}
    sink_->add({{"type","candidate_registration"},{"job",p1::job_json(m.job)},{"ready_commit_ns",now},{"accepted_registration",reason.empty()},{"reason",reason},{"solve_start_ns",m.solve_start_ns},{"solve_end_ns",m.solve_end_ns},{"worker_instance",m.worker_instance},{"first_control",m.first_control},{"applied_gp_generation",m.applied_gp_generation},{"applied_gp_snapshot_sha256",m.applied_gp_snapshot_sha256},{"gp_local_approx_max_diff",m.gp_local_approx_max_diff},{"gp_ood_detected",m.gp_ood_detected},{"gp_ood_stage_count",m.gp_ood_stage_count},{"ppo_proposal_used",m.job.ppo_proposal_used},{"ppo_q_pi",m.job.ppo_q_pi},{"ppo_lambda_pi",m.job.ppo_lambda_pi},{"ppo_reject_reason",m.job.ppo_reject_reason}});
  }
  struct ProposalEntry { p1::Proposal msg; int64_t recv_steady_ns = 0; };
  void control_proposal(const p1::Proposal & m){
    std::lock_guard<std::mutex> l(mutex_);
    proposals_.push_back(ProposalEntry{m, p1::monotonic_ns()});
    while(proposals_.size()>8)proposals_.pop_front();
  }
  bool bind_gp_and_ppo(
      p1::Job & j, uint64_t target_tick, int64_t target_sim, int64_t now_ns,
      const usv_mpc::Vector6d & x0, const Eigen::MatrixXd & ref,
      const Eigen::Vector2d & anchor, bool allow_ppo,
      const std::optional<ProposalEntry> & latest_prop,
      const Eigen::MatrixXd * prev_x, const Eigen::MatrixXd * prev_u,
      int tick_shift, std::string * gp_block_reason){
    const auto gp_sel=gp_registry_.resolve(target_tick);
    if(!gp_sel){if(gp_block_reason)*gp_block_reason="gp_plan_resolve:"+gp_sel.reason;return false;}
    Eigen::MatrixXd traj_x,traj_u;
    p1_gp_snap::build_gp_rollout_guess(
        x0,ref,anchor,params_.hydro,params_.dt,params_.T_min,params_.T_max,
        params_.dT_max,gp_sel.entry->model,gp_allow_ood_fallback_zero_,
        prev_x,prev_u,tick_shift,traj_x,traj_u);
    const auto gp_eval=p1_gp_snap::evaluate_gp_horizon(
        gp_sel.entry->model,traj_x,traj_u,gp_allow_ood_fallback_zero_);
    j.gp_snapshot_id=gp_sel.entry->model.snapshot_id().substr(0,64);
    j.gp_snapshot_sha256=gp_sel.entry->model.snapshot_sha256();
    j.gp_generation=gp_sel.generation;
    j.stage_residuals=gp_eval.residuals;
    j.stage_residuals_digest=gp_eval.digest;
    j.ppo_proposal_used=false;
    j.ppo_policy_sha256="";
    j.ppo_obs_seq=0;
    j.ppo_q_pi={0.0,0.0};
    j.ppo_lambda_pi=0.0;
    if(!allow_ppo){j.ppo_reject_reason="dry_run_no_ppo";return true;}
    if(!ppo_enabled_){j.ppo_reject_reason="ppo_disabled";return true;}
    if(!latest_prop){j.ppo_reject_reason="ppo_missing";return true;}
    const auto & p=latest_prop->msg;
    std::string rej;
    if(p.schema_version!="p1-control-proposal-v1"||p.run_id!=run_||p.boot_id!=boot_||
       p.obs_contract_version!=ppo_expected_obs_contract_)rej="ppo_identity_mismatch";
    else if(!ppo_expected_policy_sha_.empty()&&p.ppo_model_sha256!=ppo_expected_policy_sha_)
      rej="ppo_policy_sha_mismatch";
    else if(!p.valid)
      rej=p.reason.empty()?std::string("ppo_node_invalid"):(std::string("ppo_node:")+p.reason);
    else if(!p1::finite_array(p.q_pi))rej="ppo_nonfinite";
    else if(now_ns-latest_prop->recv_steady_ns>ppo_max_age_ns_)rej="ppo_steady_stale";
    else if(target_sim>p.valid_until_sim_ns)rej="ppo_expired_for_target_sim";
    else if(p.stamp_sim_ns>target_sim+500000000LL)rej="ppo_clock_reset_or_future";
    j.ppo_policy_sha256=p.ppo_model_sha256.substr(0,64);
    j.ppo_obs_seq=p.sequence;
    if(rej.empty()){
      j.ppo_proposal_used=true;
      j.ppo_q_pi=p.q_pi;
      j.ppo_lambda_pi=ppo_lambda_pi_;
      j.ppo_reject_reason="ok";
    }else{
      j.ppo_reject_reason=rej.substr(0,64);
    }
    return true;
  }
  void prepare_loop(){while(!prep_stop_){Preparation p;{std::unique_lock<std::mutex> l(prep_mutex_);prep_cv_.wait_for(l,std::chrono::milliseconds(100),[this]{return prep_stop_||pending_.has_value();});if(prep_stop_)break;if(!pending_)continue;p=*pending_;pending_.reset();}
    if(preparation_barrier_->take()){
      auto start=p1::monotonic_ns();preparation_barrier_active_=true;
      sink_->add({{"type","diagnostic_preparation_barrier_enter"},{"target_tick",p.tick+1},{"start_ns",start},{"maximum_ms",preparation_barrier_->milliseconds()},{"physical_output",false}});
      {std::unique_lock<std::mutex> q(prep_mutex_);prep_cv_.wait_for(q,std::chrono::milliseconds(preparation_barrier_->milliseconds()),[this]{return prep_stop_||stop_requested||worker_unusable_;});}
      preparation_barrier_active_=false;
      std::lock_guard<std::mutex> l(mutex_);
      const bool cancelled=prep_stop_||stop_requested||worker_unusable_;
      bool pending_after;{std::lock_guard<std::mutex> q(prep_mutex_);pending_after=bool(pending_);}
      sink_->add({{"type","diagnostic_preparation_barrier_release"},{"target_tick",p.tick+1},{"released_ns",p1::monotonic_ns()},{"cancelled",cancelled},{"worker_unusable",worker_unusable_.load()},{"pending_after",pending_after}});
      if(cancelled){sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"reason",worker_unusable_?"worker_unusable_after_preparation_barrier":"shutdown_after_preparation_barrier"},{"processed_ns",p1::monotonic_ns()}});continue;}
    }
    auto & s=p.s;int64_t target_sim=s.sim+(p.origin+p1::T-s.clock_receive);auto x=s.state;if(!predict(s,target_sim)){sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"reason","history_or_propagation"}});continue;}
    usv_mpc::ReferenceMetadata meta;auto ref=usv_mpc::build_frozen_reference(s.state,*s.ref,20,.2,c_.at("reference_start_offset"),c_.at("cruise_speed"),&meta);if(!ref.allFinite())continue;
    p1::Job j;j.schema_version="p1-solve-job-v1";j.run_id=run_;j.boot_id=boot_;j.contract_hash=hash_;j.nominal_hash=nominal_;const auto selection=registry_.resolve(grid_,grid_,p.tick+1,model_options_);
    if(!selection){sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"reason","model_plan_resolve:"+selection.reason},{"processed_ns",p1::monotonic_ns()}});continue;}
    {std::lock_guard<std::mutex> l(mutex_);
       if(version_.model!=selection.generation){version_.model=selection.generation;invalidate_locked();
         sink_->add({{"type","model_version"},{"target_tick",p.tick+1},{"model_generation",version_.model},{"processed_ns",p1::monotonic_ns()}});}}
    j.target_tick=p.tick+1;j.task_generation=s.version.task;j.model_generation=selection.generation;j.config_generation=s.version.config;j.schedule_generation=grid_.schedule_generation;j.clock_epoch=grid_.clock_epoch;j.tick_origin_steady_ns=p.origin;j.freeze_steady_ns=s.freeze;j.deadline_steady_ns=p.origin+p1::DEADLINE;j.target_steady_ns=p.origin+p1::T;j.target_sim_ns=target_sim;j.odom_stamp_ns=s.odom_stamp;j.imu_stamp_ns=s.mixed?s.imu_stamp:0;j.odom_receive_ns=s.odom_receive;j.imu_receive_ns=s.mixed?s.imu_receive:0;j.odom_sequence=s.odom_seq;j.imu_sequence=s.mixed?s.imu_seq:0;j.r_from_imu=s.mixed;j.horizon_steps=20;j.prediction_dt=.2;std::copy(x.data(),x.data()+6,j.frozen_state.begin());std::copy(s.state.data(),s.state.data()+6,j.target_state.begin());std::copy(ref.data(),ref.data()+126,j.reference.begin());j.frozen_clock_sim_ns=s.sim;j.frozen_clock_receive_ns=s.clock_receive;j.assumed_rtf=1.0;j.anchor_source=s.anchor_source;j.anchor_producer=s.anchor_producer;j.anchor_run_id=s.anchor_run;    for(auto & e:s.history){j.history_sim_ns.push_back(e.sim_ns);j.history_channel.push_back(e.channel);j.history_n.push_back(e.value);}j.anchor_n=s.anchor.n;j.anchor_sequence=s.anchor.seq;j.anchor_publish_ns=s.anchor.time;j.anchor_known=s.anchor.known;j.reset_warmstart=std::abs(usv_mpc::normalize_angle(s.state[2]-ref(2,0)))>M_PI*.75;
    {std::optional<ProposalEntry> latest_prop;bool has_prev=false;Eigen::MatrixXd prev_x,prev_u;uint64_t prev_tick=0;
      {std::lock_guard<std::mutex> l(mutex_);
       if(!proposals_.empty())latest_prop=proposals_.back();
       if(last_cand_x_.rows()==6&&last_cand_u_.rows()==2){has_prev=true;prev_x=last_cand_x_;prev_u=last_cand_u_;prev_tick=last_cand_tick_;}}
      const int shift=has_prev&&j.target_tick>prev_tick?int(j.target_tick-prev_tick):0;
      std::string gp_block;
      if(!bind_gp_and_ppo(j,j.target_tick,target_sim,p1::monotonic_ns(),x,ref,
          {s.anchor.n[0],s.anchor.n[1]},true,latest_prop,
          has_prev?&prev_x:nullptr,has_prev?&prev_u:nullptr,shift,&gp_block)){
        sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"reason",gp_block},{"processed_ns",p1::monotonic_ns()}});continue;}}
    int64_t submit_commit_ns;
    {std::lock_guard<std::mutex> l(mutex_);check_worker_locked(p1::monotonic_ns());submit_commit_ns=p1::monotonic_ns();std::string rejected;
      if(stopping_)rejected="shutdown_before_submit";else if(worker_unusable_)rejected="worker_unusable_before_submit";else if(!worker_valid_)rejected="worker_unvalidated_before_submit";else if(sink_->failed())rejected="source_failed_before_submit";else if(!(s.version==version_))rejected="version_changed_before_submit";else if(current_tick_!=p.tick)rejected="tick_changed_before_submit";else if(submit_commit_ns>j.deadline_steady_ns)rejected="deadline_expired_before_submit";
      if(!rejected.empty()){sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"preparation_tick",p.tick},{"current_tick",current_tick_},{"deadline_ns",j.deadline_steady_ns},{"processed_ns",submit_commit_ns},{"reason",rejected}});continue;}j.worker_instance=worker_instance_;auto resource=p1::check_job_resources(j,resources_);if(!resource){sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"reason",resource.reason},{"field",resource.field},{"observed",resource.observed},{"limit",resource.limit}});continue;}j.job_id=++job_id_;jobs_.push_back(j);while(jobs_.size()>8)jobs_.pop_front();}
    // Submission commits share the invalidation mutex; DDS remains outside it.
    // A previously committed publication may finish after a terminal observation.
    if(!sink_->add({{"type","job"},{"job",p1::job_json(j)},{"reference_mode",meta.reference_mode},{"profile_t0",meta.profile_t0},{"nearest_index",meta.nearest_index},{"start_index",meta.start_index},{"submit_commit_ns",submit_commit_ns},{"publish_start_ns",p1::monotonic_ns()}}))continue;
    const auto publish_start=p1::monotonic_ns();try{job_pub_->publish(j);sink_->add({{"type","job_publish_result"},{"job_id",j.job_id},{"publish_start_ns",publish_start},{"publish_end_ns",p1::monotonic_ns()},{"success",true}});}catch(...){sink_->add({{"type","job_publish_result"},{"job_id",j.job_id},{"publish_start_ns",publish_start},{"publish_end_ns",p1::monotonic_ns()},{"success",false}});std::lock_guard<std::mutex> l(mutex_);unusable_locked("job_publication_failed",p1::monotonic_ns());}
  }}
  // 受控仿真：一拍一条类型化命令。sequence 严格递增，tick 与决策拍一致；
  // 命令里不携带"我觉得锚点是什么"—— plant 的回执才是下一拍的锚点来源。
  // 受控仿真：一拍一条类型化命令，窗口**只能**声明在 plant 已执行事实之后。
  //   apply_begin = 上一条 ok 回执的 hold_end（首条用 commit_now）
  //   apply_end   = apply_begin + T；deadline = apply_begin + DEADLINE
  // 无法合法声明窗口时不发布命令（写 plant_command_withheld），该 tick 无命令
  // 是合法结果，而不是伪造一个窗口。
  /// 下一条命令实际生效的窗口起点：不早于提交时刻，且对齐到 plant 的 tick 网格。
  /// 决策校验与发布必须用同一个值，否则速率约束会被按"提交时刻"误算。
  std::int64_t next_apply_begin_locked() const {
    const std::int64_t commit_now=p1::monotonic_ns();
    int64_t begin=receipts_.hold_end_steady_ns();
    if(begin<commit_now)begin=commit_now;
    const std::int64_t origin=receipts_.steady_origin_ns();
    if(origin>0&&begin>origin){
      const std::int64_t offset=begin-origin;
      begin=origin+((offset+p1::T-1)/p1::T)*p1::T;}
    return begin>0?begin:commit_now;
  }
  void publish_plant(p1::Decision & d){
    if(test_skip_tick_>0&&d.tick==static_cast<uint64_t>(test_skip_tick_)){
      d.publish_success[0]=false;d.publish_success[1]=false;
      sink_->add({{"type","plant_command_withheld"},{"tick",d.tick},{"reason","injected_skip_tick"},{"processed_ns",p1::monotonic_ns()}});
      return;
    }
    std::int64_t begin=0;
    {std::lock_guard<std::mutex> l(mutex_);
     if(!receipts_.known()){d.publish_success[0]=false;d.publish_success[1]=false;
       sink_->add({{"type","plant_command_withheld"},{"tick",d.tick},{"reason","receipt_pending"},{"processed_ns",p1::monotonic_ns()}});
       return;}
     // 起点必须落在"plant 已执行事实之后"且**不早于本拍提交时刻**：
     // 只有 bootstrap 时 hold_end 是 plant 的启动瞬间，早已过去 —— 用它声明
     // 一个已关闭的窗口会让每条命令都被 plant 判 late。
     begin=next_apply_begin_locked();
     plant_sequence_++;
     command_pending_=true;pending_sequence_=plant_sequence_;
     pending_execution_before_=receipts_.execution_index();}
    usv_research_interfaces::msg::PlantCommand m;
    m.schema_version="p1-plant-command-v2";m.run_id=run_;m.boot_id=boot_;m.contract_hash=hash_;
    m.producer_instance_id=plant_producer_;
    m.sequence=plant_sequence_;m.tick=d.tick;
    m.apply_begin_steady_ns=begin;m.apply_end_steady_ns=begin+p1::T;
    m.deadline_steady_ns=begin+p1::DEADLINE;
    m.regulator_clock_sim_ns=sim_;
    m.task_generation=d.task_generation;m.model_generation=d.model_generation;
    m.config_generation=d.config_generation;m.schedule_generation=d.schedule_generation;
    m.clock_epoch=d.clock_epoch;
    m.thrust_n[0]=d.final_n[0];m.thrust_n[1]=d.final_n[1];
    {std::lock_guard<std::mutex> l(mutex_);
     declared_={true,m.apply_begin_steady_ns,m.apply_end_steady_ns,{m.thrust_n[0],m.thrust_n[1]}};}
    if(candidate_){m.candidate_job_id=candidate_->job.job_id;m.candidate_worker_instance=candidate_->worker_instance;m.candidate_solve_end_ns=candidate_->solve_end_ns;}
    const std::uint32_t pcall=diag_call_tick();
    diag_emit_tick(p1_clock_diag::Record(p1_clock_diag::kPublishBegin,p1_clock_diag::kRegulatorTick,p1_clock_diag::monotonic_ns()).call(pcall).kind(p1_clock_diag::kKindPlantCommand).ident(m.sequence,d.tick));
    d.publish_start_ns[0]=p1::monotonic_ns();
    try{plant_pub_->publish(m);d.publish_success[0]=true;d.publish_success[1]=true;}catch(...){d.publish_success[0]=false;d.publish_success[1]=false;}
    d.publish_end_ns[0]=d.publish_end_ns[1]=p1::monotonic_ns();
    diag_emit_tick(p1_clock_diag::Record(p1_clock_diag::kPublishEnd,p1_clock_diag::kRegulatorTick,p1_clock_diag::monotonic_ns()).call(pcall).kind(p1_clock_diag::kKindPlantCommand).ident(m.sequence,d.tick).nums(d.publish_success[0]?1:0,0,0,0));
    sink_->add({{"type","plant_command"},{"schema",m.schema_version},{"run_id",run_},
      {"boot_id",boot_},{"contract_hash",hash_},{"producer_instance_id",plant_producer_},
      {"sequence",m.sequence},{"tick",m.tick},
      {"thrust_n",{d.final_n[0],d.final_n[1]}},
      {"apply_begin_steady_ns",m.apply_begin_steady_ns},
      {"apply_end_steady_ns",m.apply_end_steady_ns},
      {"deadline_steady_ns",m.deadline_steady_ns},
      {"regulator_clock_sim_ns",m.regulator_clock_sim_ns},
      {"task_generation",m.task_generation},{"model_generation",m.model_generation},
      {"config_generation",m.config_generation},{"schedule_generation",m.schedule_generation},
      {"clock_epoch",m.clock_epoch},{"candidate_job_id",m.candidate_job_id},
      {"publish_ns",d.publish_end_ns[0]}});
    if(!d.publish_success[0]){std::lock_guard<std::mutex> l(mutex_);normal_complete_=false;worker_unusable_=true;invalidate_locked();}
  }
  void publish(p1::Decision & d){if(mode_=="controlled_sim"){publish_plant(d);return;}if(mode_!="execute")return;p1::Anchor old;{std::lock_guard<std::mutex> l(mutex_);old=anchor_;}d.rho_available=old.known[0]&&old.known[1];d.previous_anchor_known=old.known;d.previous_n=old.n;d.previous_publish_ns=old.time;
    for(int i=0;i<2;++i){d.publish_start_ns[i]=p1::monotonic_ns();{std::lock_guard<std::mutex> l(mutex_);d.publish_sim_ns[i]=sim_;d.publish_epoch[i]=version_.epoch;d.publish_clock_age_ns[i]=d.publish_start_ns[i]-clock_receive_;}std_msgs::msg::Float64 m;m.data=d.final_n[i];try{(i?right_:left_)->publish(m);d.publish_success[i]=true;}catch(...){d.publish_success[i]=false;}
      d.publish_end_ns[i]=p1::monotonic_ns();std::lock_guard<std::mutex> l(mutex_);if(d.publish_success[i]){anchor_.n[i]=d.final_n[i];anchor_.time[i]=d.publish_start_ns[i];anchor_.seq[i]++;anchor_.known[i]=true;push_history_locked({d.publish_sim_ns[i],i,d.final_n[i]});push_publication_locked({i,anchor_.seq[i],d.publish_start_ns[i],d.final_n[i],anchor_.known[i]});}else{anchor_.known[i]=false;normal_complete_=false;worker_unusable_=true;invalidate_locked();}}
    if(d.publish_end_ns[1]-d.publish_start_ns[0]>c_.at("publish_budget_ns").get<int64_t>()){normal_complete_=false;worker_unusable_=true;}
    for(int i=0;i<2;++i)if(!old.known[i]||!d.publish_success[i])d.rho_available=false;
    for(int i=0;i<2;++i)if(old.known[i]&&d.publish_success[i]&&(d.publish_start_ns[i]-old.time[i]>c_.at("publish_gap_ns").get<int64_t>()||std::abs(d.final_n[i]-old.n[i])>limits_.rho*(d.publish_start_ns[i]-old.time[i])/1e9+1e-9)){normal_complete_=false;worker_unusable_=true;d.rho_available=false;}
  }
  static p1::Json decision_json(const p1::Decision & d){return {{"type","decision"},{"schema",d.schema_version},{"run_id",d.run_id},{"boot_id",d.boot_id},{"contract_hash",d.contract_hash},{"worker_instance",d.worker_instance},{"plant_execution_index",d.anchor_sequence[0]},{"model_generation",d.model_generation},{"config_generation",d.config_generation},{"mode",d.mode},{"sequence",d.sequence},{"tick",d.tick},{"job_id",d.job_id},{"task_generation",d.task_generation},{"schedule_generation",d.schedule_generation},{"epoch",d.clock_epoch},{"clock_epoch",d.clock_epoch},{"anchor_publish_ns",d.anchor_publish_ns},{"planned_ns",d.tick_planned_ns},{"start_ns",d.tick_start_ns},{"cutoff_commit_ns",d.cutoff_commit_ns},{"ready_commit_ns",d.candidate_ready_commit_ns},{"activation_commit_ns",d.activation_commit_ns},{"end_ns",d.tick_end_ns},{"skipped_ticks",d.skipped_ticks},{"candidate_accepted",d.candidate_accepted},{"accepted",d.candidate_accepted},{"diagnostic_only",d.diagnostic_only},{"reason",d.reason},{"control_source",d.control_source},{"target_state",d.target_state},{"activation_state",d.activation_state},{"state_error",d.state_error},{"requested_n",d.requested_n},{"final_n",d.final_n},{"publish_success",d.publish_success},{"publish_start_ns",d.publish_start_ns},{"publish_end_ns",d.publish_end_ns},{"previous_anchor_known",d.previous_anchor_known},{"publish_sim_ns",d.publish_sim_ns},{"publish_epoch",d.publish_epoch},{"publish_clock_age_ns",d.publish_clock_age_ns},{"activation_clock_sim_ns",d.activation_clock_sim_ns},{"activation_clock_receive_ns",d.activation_clock_receive_ns},{"activation_rtf",d.activation_rtf},{"activation_odom_stamp_ns",d.activation_odom_stamp_ns},{"activation_odom_receive_ns",d.activation_odom_receive_ns},{"activation_odom_sequence",d.activation_odom_sequence},{"activation_imu_stamp_ns",d.activation_imu_stamp_ns},{"activation_imu_receive_ns",d.activation_imu_receive_ns},{"activation_imu_sequence",d.activation_imu_sequence},{"activation_r_from_imu",d.activation_r_from_imu},{"previous_n",d.previous_n},{"previous_publish_ns",d.previous_publish_ns},{"anchor_known",d.anchor_known},{"anchor_sequence",d.anchor_sequence},{"odom_age_ns",d.odom_age_ns},{"imu_age_ns",d.imu_age_ns},{"clock_age_ns",d.clock_age_ns},{"normal_contract_complete",d.normal_contract_complete},{"rho_available",d.rho_available},{"plant_acceptance_observed",false},{"gp_snapshot_id",d.gp_snapshot_id},{"gp_snapshot_sha256",d.gp_snapshot_sha256},{"gp_generation",d.gp_generation},{"ppo_proposal_used",d.ppo_proposal_used},{"ppo_policy_sha256",d.ppo_policy_sha256},{"ppo_q_pi",d.ppo_q_pi},{"ppo_lambda_pi",d.ppo_lambda_pi},{"ppo_reject_reason",d.ppo_reject_reason},{"gp_local_approx_max_diff",d.gp_local_approx_max_diff},{"gp_ood_detected",d.gp_ood_detected},{"gp_ood_stage_count",d.gp_ood_stage_count}};}
  void tick_loop(){int64_t origin=p1::monotonic_ns()+1000000000,stop_start=0;uint64_t tick=1,last_schedule=0;
    while(true){auto planned=origin+tick*p1::T;p1::sleep_until_monotonic(planned);
      if(tick_barrier_->take()){
        const auto start=p1::monotonic_ns();sink_->add({{"type","diagnostic_tick_barrier_enter"},{"expected_tick",tick},{"planned_ns",planned},{"start_ns",start},{"maximum_ms",tick_barrier_->milliseconds()},{"physical_output",false}});
        const auto until=start+tick_barrier_->milliseconds()*1000000;
        while(!stop_requested&&!prep_stop_&&p1::monotonic_ns()<until)p1::sleep_until_monotonic(std::min(until,p1::monotonic_ns()+20000000));
        sink_->add({{"type","diagnostic_tick_barrier_release"},{"expected_tick",tick},{"released_ns",p1::monotonic_ns()},{"cancelled",stop_requested.load()||prep_stop_.load()}});
      }
      auto now=p1::monotonic_ns();p1::Decision d;Snapshot s;std::optional<p1::Ticket> t;std::shared_ptr<const p1::Candidate> cand;
      const std::uint32_t tcall=diag_call_tick();
      diag_emit_tick(p1_clock_diag::Record(p1_clock_diag::kTickBegin,p1_clock_diag::kRegulatorTick,now).call(tcall).ident(tick,decision_seq_).nums(planned,now,0,0).schedule(version_.schedule,grid_.schedule_generation,version_.epoch));
      {std::lock_guard<std::mutex> l(mutex_);
       diag_emit_tick(p1_clock_diag::Record(p1_clock_diag::kTickLocked,p1_clock_diag::kRegulatorTick,p1_clock_diag::monotonic_ns()).call(tcall).ident(tick,decision_seq_).nums(planned,now,0,0).schedule(version_.schedule,grid_.schedule_generation,version_.epoch));
       if(last_schedule&&version_.schedule!=last_schedule){
         const std::uint64_t tick_before=tick;const std::int64_t origin_before=origin;const std::int64_t planned_before=planned;
         origin=now;tick=1;planned=origin;invalidate_locked();
         diag_emit_tick(p1_clock_diag::Record(p1_clock_diag::kScheduleReset,p1_clock_diag::kRegulatorTick,p1_clock_diag::monotonic_ns()).call(tcall).ident(last_schedule,0).nums(tick_before,tick,origin_before,origin).schedule(version_.schedule,grid_.schedule_generation,version_.epoch));
         diag_emit_tick(p1_clock_diag::Record(p1_clock_diag::kScheduleReset,p1_clock_diag::kRegulatorTick,p1_clock_diag::monotonic_ns()).call(tcall).span(1).ident(last_schedule,0).nums(planned_before,planned,0,0).schedule(version_.schedule,grid_.schedule_generation,version_.epoch));}last_schedule=version_.schedule;
        auto due=p1::due_tick(origin,now);d.skipped_ticks=due>tick?due-tick:0;if(due>tick){const auto old_tick=tick;const auto old_candidate=candidate_?candidate_->job.job_id:0;const auto old_target=candidate_?candidate_->job.target_tick:0;tick=due;planned=origin+tick*p1::T;admission_.invalidate();candidate_.reset();normal_complete_=false;sink_->add({{"type","scheduler_skipped_ticks"},{"expected_tick",old_tick},{"due_tick",due},{"skipped_ticks",d.skipped_ticks},{"origin_ns",origin},{"observed_ns",now},{"planned_ns",planned},{"schedule_generation",version_.schedule},{"invalidated_candidate_job_id",old_candidate},{"invalidated_candidate_target_tick",old_target},{"candidate_after",false},{"admission_slots_after",admission_.slots()}});}
        current_tick_=tick;check_worker_locked(now);if(stop_requested||sink_->failed()){stopping_=true;if(!stop_start)stop_start=now;invalidate_locked();}
        if(clock_receive_&&last_clock_advance_&&now-last_clock_advance_>c_.at("clock_pause_confirm_ns").get<int64_t>()&&!paused_){paused_=true;version_.schedule++;invalidate_locked();
          diag_emit_tick(p1_clock_diag::Record(p1_clock_diag::kPause,p1_clock_diag::kRegulatorTick,p1_clock_diag::monotonic_ns()).call(tcall).ident(static_cast<std::uint64_t>(last_clock_advance_),static_cast<std::uint64_t>(c_.at("clock_pause_confirm_ns").get<int64_t>())).nums(sim_,now-last_clock_advance_,0,0).schedule(version_.schedule,grid_.schedule_generation,version_.epoch));}
        if(worker_active_&&now-worker_active_since_>c_.at("active_watchdog_ns").get<int64_t>()){unusable_locked("active_watchdog",now);sink_->add({{"type","active_watchdog"},{"active_job",worker_active_},{"observed_ns",now},{"policy","stop_submit; supervisor owns finite TERM/KILL"}});}
        s=snapshot_locked(now);t=admission_.take(tick,now);cand=candidate_;if(t)candidate_.reset();
        d.schema_version="p1-execution-decision-v2";d.run_id=run_;d.boot_id=boot_;d.contract_hash=hash_;d.worker_instance=worker_instance_;d.mode=mode_;d.sequence=++decision_seq_;d.tick=tick;d.task_generation=version_.task;d.model_generation=version_.model;d.config_generation=version_.config;d.schedule_generation=grid_.schedule_generation;d.clock_epoch=grid_.clock_epoch;d.tick_planned_ns=planned;d.tick_start_ns=now;d.cutoff_commit_ns=t?admission_.cutoff_ns():0;d.diagnostic_only=mode_!="execute";d.odom_age_ns=now-s.odom_receive;d.imu_age_ns=s.mixed?now-s.imu_receive:0;d.clock_age_ns=now-s.clock_receive;
      }
      auto reason=eligible(s,now);if(stopping_)reason="shutdown";if(worker_unusable_)reason="worker_unusable";
      if(now-planned>c_.at("tick_jitter_ns").get<int64_t>()){reason="tick_jitter";normal_complete_=false;}
      if(t&&cand){d.job_id=t->id;d.candidate_ready_commit_ns=t->ready_ns;d.target_state=t->prediction;
        // 计划轴与运行轴分别比较：两者不共用一个坐标系，混比会让每个候选都被拒绝。
      const p1::RunAxes activation_run{s.version.task,s.version.config,
                                       grid_.schedule_generation,grid_.clock_epoch};
      const p1::PlanIdentity activation_plan{t->plan.model,grid_.schedule_generation,
                                             grid_.clock_epoch};
      if(reason.empty()&&!(t->run==activation_run)){
        sink_->add({{"type","version_compare"},{"axes","run"},
          {"ticket_task",t->run.task},{"snapshot_task",s.version.task},
          {"ticket_config",t->run.config},{"snapshot_config",s.version.config},
          {"processed_ns",now}});
        reason="run_axes_changed";}
      if(reason.empty()&&!(t->plan==activation_plan)){
        sink_->add({{"type","version_compare"},{"axes","plan"},
          {"ticket_model",t->plan.model},{"plan_model",activation_plan.model},
          {"ticket_schedule",t->plan.schedule},{"plan_schedule",activation_plan.schedule},
          {"ticket_epoch",t->plan.epoch},{"plan_epoch",activation_plan.epoch},
          {"processed_ns",now}});
        reason="plan_axes_changed";}
        if(reason.empty())reason=mode_=="controlled_sim"
          ?p1::receipt_chain_check(t->anchor,s.anchor,s.publication_history)
          :p1::publication_history_check(t->anchor,s.anchor,s.publication_history);
        auto aligned=s;if(!predict(aligned,cand->job.target_sim_ns)){if(reason.empty())reason="activation_history_or_time";}else{std::copy(aligned.state.data(),aligned.state.data()+6,d.activation_state.begin());auto state_reason=p1::state_check(t->prediction,d.activation_state,limits_,&d.state_error);if(reason.empty())reason=state_reason;}
        if(reason.empty()){Eigen::Vector2d request(cand->first_control[0],cand->first_control[1]);auto mapped=usv_mpc::map_vrx(request,c_.at("map_scale"),limits_.low,limits_.high,c_.at("publisher_max_n"));d.requested_n=cand->first_control;d.final_n={mapped[0],mapped[1]};reason=p1::command_bounds(d.final_n,limits_);if(reason.empty()&&(mapped-request).norm()>1e-9)reason="candidate_mapping_changed";}
      }else if(reason.empty())reason="no_candidate";
      {std::lock_guard<std::mutex> l(mutex_);if(reason.empty()&&(!(s.version==version_)||s.odom_seq!=odom_seq_||s.imu_seq!=imu_seq_))reason="activation_input_changed_during_validation";
        if(reason.empty()&&t)reason=mode_=="controlled_sim"
          ?p1::receipt_chain_check(t->anchor,anchor_,publication_history_)
          :p1::publication_history_check(t->anchor,anchor_,publication_history_);
        check_worker_locked(p1::monotonic_ns());
        const int64_t commit_now=p1::monotonic_ns();
        if(reason.empty())reason=eligible(snapshot_locked(commit_now),commit_now);
        if(reason.empty()&&(worker_unusable_||!worker_valid_||sink_->failed()))reason="run_unusable_at_commit";
        if(reason.empty()&&commit_now-planned>c_.at("tick_jitter_ns").get<int64_t>()){reason="tick_jitter_at_commit";normal_complete_=false;}
        if(reason.empty()&&cand&&std::abs(sim_+(commit_now-clock_receive_)-cand->job.target_sim_ns)>c_.at("target_sim_slack_ns").get<int64_t>())reason="target_sim_mismatch";
        if(reason.empty()){
          // 命令要到下一个窗口起点才生效；按提交时刻算速率会每个 tick 都超限。
          // 此处已在 mutex_ 临界区内：不得再次加锁（非递归互斥量会自锁）。
          const std::int64_t apply_begin=next_apply_begin_locked();
          p1::Anchor baseline=anchor_;
          // 若上一条已声明的命令在 apply_begin 之前生效，速率基准就是它。
          // 速率是"值能变多快"：基准时间的语义是**该值从何时开始保持**，
          // 不是它何时结束。用结束时刻会把切换瞬间算成零间隔。
          if(declared_.valid&&declared_.end_ns<=apply_begin){
            baseline.n={declared_.thrust[0],declared_.thrust[1]};
            baseline.time={declared_.begin_ns,declared_.begin_ns};}
          reason=p1::command_check_held(d.final_n,baseline,apply_begin,commit_now,
                                        limits_,p1::T);}
        if(stopping_||stop_requested)reason="shutdown";
        d.candidate_accepted=reason.empty();d.reason=reason;d.activation_commit_ns=commit_now;d.activation_clock_sim_ns=sim_;d.activation_clock_receive_ns=clock_receive_;d.activation_rtf=rtf_;
        // Current source provenance at the actual final commit, not the job snapshot.
        d.activation_odom_stamp_ns=odom_stamp_;d.activation_odom_receive_ns=odom_receive_;d.activation_odom_sequence=odom_seq_;
        d.activation_r_from_imu=mixed_;d.activation_imu_stamp_ns=mixed_?imu_stamp_:0;
        d.activation_imu_receive_ns=mixed_?imu_receive_:0;d.activation_imu_sequence=mixed_?imu_seq_:0;
        d.odom_age_ns=commit_now-odom_receive_;d.imu_age_ns=mixed_?commit_now-imu_receive_:0;d.clock_age_ns=commit_now-clock_receive_;
        if(t&&cand&&mode_=="shadow")anchor_evidence_locked(*t,d);
        if(cand){d.gp_snapshot_id=cand->job.gp_snapshot_id;d.gp_snapshot_sha256=cand->job.gp_snapshot_sha256;d.gp_generation=cand->job.gp_generation;d.ppo_proposal_used=cand->job.ppo_proposal_used;d.ppo_policy_sha256=cand->job.ppo_policy_sha256;d.ppo_q_pi=cand->job.ppo_q_pi;d.ppo_lambda_pi=cand->job.ppo_lambda_pi;d.ppo_reject_reason=cand->job.ppo_reject_reason;d.gp_local_approx_max_diff=cand->gp_local_approx_max_diff;d.gp_ood_detected=cand->gp_ood_detected;d.gp_ood_stage_count=cand->gp_ood_stage_count;}else{const auto gsel=gp_registry_.resolve(tick);if(gsel){d.gp_snapshot_id=gsel.entry->model.snapshot_id().substr(0,64);d.gp_snapshot_sha256=gsel.entry->model.snapshot_sha256();d.gp_generation=gsel.generation;}d.ppo_reject_reason=ppo_enabled_?"no_candidate":"ppo_disabled";}
        if(d.candidate_accepted){last_accepted_=d.activation_commit_ns;d.control_source="candidate";if(cand){last_cand_tick_=tick;last_cand_x_.resize(6,21);std::copy(cand->x_prediction.begin(),cand->x_prediction.end(),last_cand_x_.data());last_cand_u_.resize(2,20);std::copy(cand->u_prediction.begin(),cand->u_prediction.end(),last_cand_u_.data());}}else{d.final_n=p1::fallback(anchor_,d.activation_commit_ns,last_accepted_,limits_,stopping_||worker_unusable_||reason!="no_candidate");d.requested_n=d.final_n;d.control_source=last_accepted_>0&&!stopping_&&!worker_unusable_&&reason=="no_candidate"&&d.activation_commit_ns-last_accepted_<=limits_.hold_ns?"hold":"ramp_zero";}
      }
      // Only the tick thread reaches either physical publisher; no shared mutex
      // spans publish. Callback invalidation after this commit affects successor ticks.
      publish(d);
      {std::lock_guard<std::mutex> l(mutex_);
       d.anchor_known=anchor_.known;d.anchor_sequence=anchor_.seq;
       // 锚点时刻就是它那条回执的执行起点；两通道同窗口，故取同一个值。
       for(int i=0;i<2;++i)d.anchor_publish_ns[i]=anchor_.time[i];
       d.normal_contract_complete=normal_complete_&&!sink_->failed()&&mode_=="execute";
       d.tick_end_ns=p1::monotonic_ns();}
      {
        const std::uint32_t dcall=diag_call_tick();
        diag_emit_tick(p1_clock_diag::Record(p1_clock_diag::kPublishBegin,p1_clock_diag::kRegulatorTick,p1_clock_diag::monotonic_ns()).call(dcall).kind(p1_clock_diag::kKindDecision).ident(d.sequence,d.tick));
        const bool added=sink_->add(decision_json(d),d);
        diag_emit_tick(p1_clock_diag::Record(p1_clock_diag::kPublishEnd,p1_clock_diag::kRegulatorTick,p1_clock_diag::monotonic_ns()).call(dcall).kind(p1_clock_diag::kKindDecision).ident(d.sequence,d.tick).nums(added?1:0,0,0,0));
        if(!added){normal_complete_=false;stopping_=true;if(!stop_start)stop_start=now;}}
      if(!stopping_&&!worker_unusable_&&worker_valid_&&!sink_->failed()){
        std::lock_guard<std::mutex> l(mutex_);const auto enqueue_now=p1::monotonic_ns();check_worker_locked(enqueue_now);auto next=snapshot_locked(enqueue_now);const std::string enqueue_gate=eligible(next,next.freeze,false);if(!enqueue_gate.empty())sink_->add({{"type","prepare_enqueue_blocked"},{"tick",tick},{"reason",enqueue_gate},{"processed_ns",enqueue_now}});
        if(!stopping_&&!worker_unusable_&&worker_valid_&&!sink_->failed()&&enqueue_gate.empty()){std::lock_guard<std::mutex> q(prep_mutex_);if(pending_)sink_->add({{"type","prepare_pending_replaced"},{"old_target_tick",pending_->tick+1},{"replacement_target_tick",tick+1}});pending_=Preparation{next,tick,planned};if(preparation_barrier_active_)sink_->add({{"type","diagnostic_preparation_pending_enqueued"},{"target_tick",tick+1},{"enqueued_ns",enqueue_now},{"pending_count",1}});prep_cv_.notify_one();}}
      if(stopping_){bool zero=std::abs(d.final_n[0])<1e-9&&std::abs(d.final_n[1])<1e-9;if(zero||now-stop_start>=c_.at("shutdown_grace_ns").get<int64_t>()){sink_->add({{"type","regulator_shutdown"},{"zero_target_published",mode_=="execute"&&zero&&d.publish_success[0]&&d.publish_success[1]},{"shutdown_grace_exceeded",!zero},{"last_decision_sequence",d.sequence},{"normal_contract_complete",normal_complete_.load()&&!sink_->failed()},{"plant_hold_end_known",receipts_.known()&&receipts_.normal_complete()},{"finished_ns",p1::monotonic_ns()}});break;}}
      diag_emit_tick(p1_clock_diag::Record(p1_clock_diag::kTickEnd,p1_clock_diag::kRegulatorTick,p1_clock_diag::monotonic_ns()).call(tcall).ident(tick,d.sequence).nums(d.tick_planned_ns,d.tick_start_ns,d.tick_end_ns,0).schedule(version_.schedule,grid_.schedule_generation,version_.epoch));
      p1::sleep_until_monotonic(planned+p1::DEADLINE+1);{std::lock_guard<std::mutex> l(mutex_);admission_.cutoff(p1::monotonic_ns());}
      ++tick;
    }
    prep_stop_=true;prep_cv_.notify_all();finished_=true;
  }
  // ================= 实船调试服务接管（零求解 / 零物理输出）=================
  // 实船调试模式入口：dry_run=false 时为纯观测 commissioning（zero jobs, zero solve），
  // dry_run=true 时开启真 MAVROS 输入 + 真 acados 求解，但严格保持零物理执行输出。
  void start_shipboard_mode(bool dry_run){
    p1::require_runtime_contract_mode(c_,mode_);
    if(run_.empty()||run_.size()>128)throw std::runtime_error("identity invalid");
    if(!diag_file_.empty())throw std::runtime_error("clock diagnostics require controlled_sim");
    {const auto plan_text=p1::read_text(plan_file_text_);
     p1::contract_require(p1::digest(plan_text)==plan_sha_,"model plan hash mismatch");
     grid_=p1::grid_of_plan(plan_text,c_);}
    capability_lease_=std::make_unique<p1::CapabilityLease>(c_.at("worker_capability_receipt_timeout_ns").get<int64_t>());
    p1_shipboard::Limits limits;
    limits.capability_age_ns=capability_lease_->timeout_ns();
    if(dry_run){
      limits.state_age_ns=c_.at("state_age_ns").get<int64_t>();
      limits.imu_age_ns=c_.at("imu_age_ns").get<int64_t>();
      dry_run_nav_=std::make_unique<p1_dry_run::DryRunCoordinator>(p1_dry_run::limits_from_contract(c_));
      dry_run_ref_=std::make_shared<usv_mpc::ReferenceInput>();
    }
    monitor_=std::make_unique<p1_shipboard::Monitor>(limits);
    commission_active_=true;
    dry_run_active_=dry_run;

    sink_=std::make_unique<Sink>(declare_parameter<std::string>("source_file",""),c_.at("log_capacity"),nullptr);
    const auto topics=p1::shipboard_input_topics();
    status_pub_=create_publisher<std_msgs::msg::String>("/p1/commissioning_status",rclcpp::QoS(1).reliable().transient_local());
    const int path_depth=dry_run?10:1;
    // 禁止创建任何物理执行端 publisher（无 Float64 推力、无 rc/override、无 cmd_vel）。
    if(dry_run){
      job_pub_=create_publisher<p1::Job>("/p1/solve_job",rclcpp::QoS(1).reliable());
      candidates_=create_subscription<p1::Candidate>("/p1/solve_candidate",rclcpp::QoS(1).reliable(),[this](p1::Candidate::SharedPtr m){dry_run_candidate(*m);});
    }
    c_state_=create_subscription<mavros_msgs::msg::State>(topics.at("state").get<std::string>(),rclcpp::SensorDataQoS(),[this](mavros_msgs::msg::State::SharedPtr m){commissioning_state(*m);});
    c_odom_=create_subscription<nav_msgs::msg::Odometry>(topics.at("odom").get<std::string>(),rclcpp::SensorDataQoS(),[this](nav_msgs::msg::Odometry::SharedPtr m){commissioning_odom(*m);});
    c_imu_=create_subscription<sensor_msgs::msg::Imu>(topics.at("imu").get<std::string>(),rclcpp::SensorDataQoS(),[this](sensor_msgs::msg::Imu::SharedPtr m){commissioning_imu(*m);});
    c_path_=create_subscription<nav_msgs::msg::Path>(topics.at("path").get<std::string>(),rclcpp::QoS(path_depth).reliable(),[this](nav_msgs::msg::Path::SharedPtr m){commissioning_path(*m);});
    c_profile_=create_subscription<std_msgs::msg::Float64MultiArray>(topics.at("profile").get<std::string>(),rclcpp::QoS(path_depth).reliable(),[this](std_msgs::msg::Float64MultiArray::SharedPtr m){commissioning_profile(*m);});
    capabilities_=create_subscription<p1::Capability>("/p1/worker_capability",rclcpp::QoS(1).reliable().transient_local(),[this](p1::Capability::SharedPtr m){commissioning_capability(*m);});
    c_stop_=create_subscription<std_msgs::msg::Bool>("/p1/stop",rclcpp::QoS(1).reliable(),[this](std_msgs::msg::Bool::SharedPtr m){if(m->data)stop_requested=true;});
    {const auto now=p1::monotonic_ns();std::lock_guard<std::mutex> l(c_mutex_);monitor_->arm_start(now);if(dry_run_nav_)dry_run_nav_->arm(now);}
    auto subs=p1::Json::array({"/mavros/state","/mavros/local_position/odom","/mavros/imu/data","/path/reference","/path/reference_profile","/p1/worker_capability","/p1/stop"});
    auto pubs=p1::Json::array({"/p1/commissioning_status"});
    if(dry_run){subs.push_back("/p1/solve_candidate");pubs.push_back("/p1/solve_job");}
    auto header=p1::Json{{"type","startup"},{"schema","p1-shipboard-regulator-v1"},{"run_id",run_},
      {"boot_id",boot_},{"host_boot_id",p1::boot_id()},{"contract_hash",hash_},
      {"plan_sha256",plan_sha_},{"mode",mode_},{"pid",getpid()},
      {"clock","CLOCK_MONOTONIC"},{"physical_output_enabled",false},{"jobs_submitted",0},
      {"anchor_known",false},{"execution_publisher_endpoints",0},
      {"subscriptions",subs},{"publications",pubs}};
    if(!sink_->add(header))throw std::runtime_error("commissioning source unavailable");
    commission_thread_=std::thread([this]{commission_loop();});
  }
  static std::string bounded(const std::string & s,bool & truncated){
    truncated=s.size()>128;return s.substr(0,128);
  }
  void recompute_dry_run_sync_locked(){
    if(!dry_run_nav_||!dry_run_ref_)return;
    const auto sync=usv_mpc::profile_sync_state(
      dry_run_ref_->path.size(),
      dry_run_ref_->profile.empty()?-1:static_cast<int>(dry_run_ref_->profile.size()),
      &dry_run_ref_->path_stamp,&dry_run_ref_->profile_stamp);
    dry_run_nav_->set_profile_sync(sync.first,sync.second);
  }
  void commissioning_state(const mavros_msgs::msg::State & m){
    const auto now=p1::monotonic_ns();
    p1_shipboard::StateFacts f;f.seen=true;f.receipt_ns=now;f.connected=m.connected;f.armed=m.armed;
    f.mode=m.mode;if(f.mode.size()>32)f.mode.resize(32);
    std::lock_guard<std::mutex> l(c_mutex_);f.count=monitor_->state().count+1;monitor_->on_state(f);
  }
  void commissioning_odom(const nav_msgs::msg::Odometry & m){
    const auto now=p1::monotonic_ns();
    std::lock_guard<std::mutex> l(c_mutex_);
    p1_shipboard::InputFacts f;f.seen=true;f.count=monitor_->input("odom").count+1;f.receipt_ns=now;
    f.source_stamp_ns=stamp(m.header.stamp);
    f.frame=bounded(m.header.frame_id,f.truncated);
    f.child_frame=bounded(m.child_frame_id,f.truncated);
    const auto & p=m.pose.pose.position;const auto & q=m.pose.pose.orientation;const auto & t=m.twist.twist;
    f.has_finite=true;
    f.finite=std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(q.x)&&std::isfinite(q.y)&&
      std::isfinite(q.z)&&std::isfinite(q.w)&&std::isfinite(t.linear.x)&&std::isfinite(t.linear.y)&&
      std::isfinite(t.angular.z);
    f.resource_valid=true;
    monitor_->on_input("odom",f);
    if(dry_run_nav_){
      std::array<double,5> a{p.x,p.y,t.linear.x,t.linear.y,t.angular.z};
      std::array<double,4> quat{q.x,q.y,q.z,q.w};
      p1_dry_run::OdomFacts df;
      df.seen=true;df.finite=f.finite;df.valid=f.finite&&usv_mpc::admit_odom(a,quat);
      df.pose_frame=f.frame;df.child_frame=f.child_frame;df.seq=f.count;
      df.receipt_ns=now;df.stamp_ns=f.source_stamp_ns;
      if(df.valid){
        const auto vec=usv_mpc::compose_odom(a,quat);
        for(int i=0;i<6;++i)df.state[static_cast<size_t>(i)]=vec[i];
      }
      dry_run_nav_->on_odom(df);
    }
  }
  void commissioning_imu(const sensor_msgs::msg::Imu & m){
    const auto now=p1::monotonic_ns();
    std::lock_guard<std::mutex> l(c_mutex_);
    p1_shipboard::InputFacts f;f.seen=true;f.count=monitor_->input("imu").count+1;f.receipt_ns=now;
    f.source_stamp_ns=stamp(m.header.stamp);
    f.frame=bounded(m.header.frame_id,f.truncated);
    f.has_finite=true;
    f.finite=std::isfinite(m.angular_velocity.x)&&std::isfinite(m.angular_velocity.y)&&
      std::isfinite(m.angular_velocity.z)&&std::isfinite(m.orientation.x)&&
      std::isfinite(m.orientation.y)&&std::isfinite(m.orientation.z)&&std::isfinite(m.orientation.w);
    f.resource_valid=true;
    monitor_->on_input("imu",f);
    if(dry_run_nav_){
      p1_dry_run::ImuFacts imf;
      imf.seen=true;imf.finite=std::isfinite(m.angular_velocity.z);
      imf.valid=imf.finite&&usv_mpc::admit_imu(m.angular_velocity.z);
      imf.frame=f.frame;imf.seq=f.count;imf.receipt_ns=now;imf.stamp_ns=f.source_stamp_ns;
      imf.r=imf.valid?m.angular_velocity.z:0.0;
      dry_run_nav_->on_imu(imf);
    }
  }
  // path/profile 先复用资源检查，再只记长度/布局摘要；dry_run 同步解析坐标给 ReferenceInput。
  void commissioning_path(const nav_msgs::msg::Path & m){
    const auto now=p1::monotonic_ns();
    const auto resource=p1::check_path_resources(m,resources_);
    std::shared_ptr<usv_mpc::ReferenceInput> next;
    bool dry_valid=false;
    if(dry_run_active_){
      next=std::make_shared<usv_mpc::ReferenceInput>();
      dry_valid=bool(resource);
      if(dry_valid){
        for(const auto & p:m.poses){
          const auto & q=p.pose.orientation;
          const double yaw=usv_mpc::quaternion_to_yaw(q.x,q.y,q.z,q.w);
          if(!std::isfinite(p.pose.position.x)||!std::isfinite(p.pose.position.y)||!std::isfinite(yaw)){
            dry_valid=false;break;
          }
          next->path.push_back({p.pose.position.x,p.pose.position.y,yaw});
        }
        if(!dry_valid)next->path.clear();
      }
      next->path_stamp={m.header.stamp.sec,int(m.header.stamp.nanosec)};
    }
    std::lock_guard<std::mutex> l(c_mutex_);
    p1_shipboard::InputFacts f;f.seen=true;f.count=monitor_->input("path").count+1;f.receipt_ns=now;
    f.source_stamp_ns=stamp(m.header.stamp);
    f.frame=bounded(m.header.frame_id,f.truncated);
    f.resource_valid=bool(resource);
    monitor_->on_input("path",f);
    if(dry_run_nav_){
      next->profile=dry_run_ref_->profile;next->profile_stamp=dry_run_ref_->profile_stamp;
      next->profile_sequence=dry_run_ref_->profile_sequence;next->path_sequence=f.count;
      dry_run_ref_=next;
      p1_dry_run::PathFacts pf;pf.seen=true;pf.resource_valid=f.resource_valid&&dry_valid;
      pf.frame=f.frame;pf.seq=f.count;pf.receipt_ns=now;pf.stamp_ns=f.source_stamp_ns;
      pf.points=next->path.size();
      dry_run_nav_->on_path(pf);
      recompute_dry_run_sync_locked();
    }
    sink_->add({{"type","commissioning_path_facts"},{"sequence",f.count},
      {"points",m.poses.size()},{"frame_bytes",m.header.frame_id.size()},
      {"resource_valid",f.resource_valid},{"resource_reason",resource.reason},
      {"resource_field",resource.field},{"resource_observed",resource.observed},
      {"resource_limit",resource.limit},{"stamp_ns",f.source_stamp_ns},{"receive_ns",now}});
  }
  void commissioning_profile(const std_msgs::msg::Float64MultiArray & m){
    const auto now=p1::monotonic_ns();
    const auto resource=p1::check_profile_resources(m,resources_);
    bool stamp_ok=false;
    std::pair<int,int> parsed_stamp{-1,-1};
    std::shared_ptr<usv_mpc::ReferenceInput> next;
    bool dry_valid=false;
    if(resource){
      std::vector<std::string> labels;for(const auto & d:m.layout.dim)labels.push_back(d.label);
      parsed_stamp=usv_mpc::parse_profile_stamp(labels,stamp_ok);
    }
    if(dry_run_active_){
      next=std::make_shared<usv_mpc::ReferenceInput>();
      dry_valid=bool(resource)&&!m.data.empty()&&m.data.size()%4==0&&
                m.data.size()/4<=resources_.max_profile_rows;
      next->profile_stamp=stamp_ok?parsed_stamp:std::pair<int,int>{-1,-1};
      if(dry_valid){
        for(size_t i=0;i<m.data.size()/4;++i){
          std::array<double,4> r={m.data[4*i],m.data[4*i+1],m.data[4*i+2],m.data[4*i+3]};
          if(!p1::finite_array(r)||(i&&r[3]<=m.data[4*(i-1)+3])){dry_valid=false;break;}
          next->profile.push_back(r);
        }
        if(!dry_valid)next->profile.clear();
      }
    }
    std::lock_guard<std::mutex> l(c_mutex_);
    p1_shipboard::InputFacts f;f.seen=true;f.count=monitor_->input("profile").count+1;f.receipt_ns=now;
    f.resource_valid=bool(resource);
    if(stamp_ok)f.source_stamp_ns=int64_t(parsed_stamp.first)*1000000000+parsed_stamp.second;
    monitor_->on_input("profile",f);
    if(dry_run_nav_){
      next->path=dry_run_ref_->path;next->path_stamp=dry_run_ref_->path_stamp;
      next->path_sequence=dry_run_ref_->path_sequence;next->profile_sequence=f.count;
      dry_run_ref_=next;
      p1_dry_run::ProfileFacts prf;prf.seen=true;prf.resource_valid=f.resource_valid&&dry_valid;
      prf.seq=f.count;prf.receipt_ns=now;prf.stamp_ns=f.source_stamp_ns;
      prf.rows=next->profile.size();prf.stamp_ok=stamp_ok;
      dry_run_nav_->on_profile(prf);
      recompute_dry_run_sync_locked();
    }
    sink_->add({{"type","commissioning_profile_facts"},{"sequence",f.count},
      {"rows",m.data.size()/4},{"elements",m.data.size()},{"dims",m.layout.dim.size()},
      {"resource_valid",f.resource_valid},{"resource_reason",resource.reason},
      {"stamp_ns",f.source_stamp_ns},{"receive_ns",now}});
  }
  void commissioning_capability(const p1::Capability & m){
    const auto received=p1::monotonic_ns();
    auto resource=p1::check_capability_resources(m);
    if(!resource){
      sink_->add({{"type","resource_rejected"},{"interface","capability"},{"reason",resource.reason},
        {"field",resource.field},{"observed",resource.observed},{"limit",resource.limit},
        {"receive_ns",received},{"renewed",false}});
      return;
    }
    std::lock_guard<std::mutex> l(c_mutex_);
    const auto now=p1::monotonic_ns();
    const bool identity=m.run_id==run_&&m.boot_id==boot_&&m.contract_hash==hash_&&
      m.nominal_hash==nominal_&&m.pid==expected_worker_pid_;
    const bool shape=m.schema_version=="p1-worker-capability-v2"&&m.clock_name=="CLOCK_MONOTONIC"&&
      m.backend=="acados"&&m.matrix_layout=="column_major"&&
      m.horizon_steps==static_cast<std::uint32_t>(c_.at("N").get<int>())&&m.prediction_dt==c_.at("dt").get<double>()&&
      m.model_plan_sha256==plan_sha_&&!m.fault_injection_enabled&&!m.fatal&&
      !m.worker_instance.empty()&&m.startup_ns>0;
    bool renewed=false;
    if(identity&&!worker_instance_.empty()&&worker_instance_!=m.worker_instance){
      commission_terminal(p1_shipboard::reason_worker_identity_changed);
    }
    if(identity&&shape&&commission_monitor_alive()){
      renewed=capability_lease_->renew(now);
      if(renewed)worker_instance_=m.worker_instance;
    }
    p1_shipboard::CapabilityFacts f;f.seen=true;f.receipt_ns=received;
    f.lease_last_ns=capability_lease_->last_valid_ns();
    f.model_runtime_ready=m.model_runtime_ready;
    f.fault_injection_enabled=m.fault_injection_enabled;
    f.fatal=m.fatal;f.completed_jobs=m.completed_jobs;f.active_job=m.active_job;
    f.pending_count=m.pending_count;f.worker_instance=m.worker_instance;
    monitor_->on_capability(f);
    monitor_->set_worker_capability_valid(identity&&shape);
    sink_->add({{"type","capability_admission"},{"receive_ns",received},{"validation_commit_ns",now},
      {"identity_valid",identity},{"shape_valid",shape},{"renewed",renewed},
      {"identity_fields",{{"run_id",m.run_id==run_},{"boot_id",m.boot_id==boot_},
        {"contract_hash",m.contract_hash==hash_},{"nominal_hash",m.nominal_hash==nominal_},
        {"pid",m.pid},{"expected_pid",expected_worker_pid_}}},
      {"lease_timeout_ns",capability_lease_->timeout_ns()},
      {"lease_last_after_ns",capability_lease_->last_valid_ns()},
      {"capability",{{"schema_version",m.schema_version},{"worker_instance",m.worker_instance},
        {"backend",m.backend},{"horizon_steps",m.horizon_steps},{"prediction_dt",m.prediction_dt},
        {"model_runtime_ready",m.model_runtime_ready},{"completed_jobs",m.completed_jobs},
        {"active_job",m.active_job},{"pending_count",m.pending_count},
        {"fault_injection_enabled",m.fault_injection_enabled},{"fatal",m.fatal},
        {"model_plan_sha256",m.model_plan_sha256},{"reason",m.reason}}}});
  }
  void dry_run_candidate(const p1::Candidate & m){
    if(!dry_run_active_||!dry_run_nav_)return;
    const auto now=p1::monotonic_ns();
    const auto resource=p1::check_candidate_resources(m,resources_);
    if(!resource){
      sink_->add({{"type","resource_rejected"},{"interface","candidate"},{"job_id",m.job.job_id},
        {"reason",resource.reason},{"field",resource.field},{"observed",resource.observed},
        {"limit",resource.limit},{"receive_ns",now},{"accepted_registration",false}});
      return;
    }
    p1_dry_run::CandidateOutcome outcome;
    std::string valid_job_reason;
    {
      std::lock_guard<std::mutex> l(c_mutex_);
      valid_job_reason=p1::valid_job(m.job,run_,boot_,hash_,nominal_,worker_instance_);
      auto expected=std::find_if(dry_run_jobs_.begin(),dry_run_jobs_.end(),
        [&](const p1::Job & j){return j.job_id==m.job.job_id;});
      p1_dry_run::CandidateFacts cf;
      cf.job_id=m.job.job_id;cf.tick=m.job.target_tick;
      cf.worker_instance=m.worker_instance;cf.expected_worker_instance=worker_instance_;
      cf.backend=m.backend;
      cf.echo_matched=valid_job_reason.empty()&&expected!=dry_run_jobs_.end()&&
        p1::job_json(*expected)==p1::job_json(m.job);
      cf.success=m.success;cf.prediction_available=m.prediction_available;cf.solver_invoked=m.solver_invoked;
      cf.finite=p1::finite_array(m.x_prediction)&&p1::finite_array(m.u_prediction)&&
        p1::finite_array(m.first_control);
      cf.backend_ms=m.backend_ms;cf.first_control=m.first_control;
      cf.initial_control_matches=cf.finite&&std::abs(m.first_control[0]-m.u_prediction[0])<=1e-8&&
        std::abs(m.first_control[1]-m.u_prediction[1])<=1e-8;
      cf.initial_state_matches=cf.finite;
      if(cf.initial_state_matches){
        for(int i=0;i<6;++i){
          if(std::abs(m.x_prediction[i]-m.job.target_state[i])>1e-7){cf.initial_state_matches=false;break;}
        }
      }
      cf.freeze_steady_ns=m.job.freeze_steady_ns;cf.worker_receive_ns=m.worker_receive_ns;
      cf.solve_start_ns=m.solve_start_ns;cf.solve_end_ns=m.solve_end_ns;
      cf.deadline_steady_ns=m.job.deadline_steady_ns;cf.receive_ns=now;
      outcome=dry_run_nav_->evaluate_candidate(cf);
    }
    sink_->add({{"type","dry_run_decision"},{"schema","p1-dry-run-decision-v1"},
      {"job_id",m.job.job_id},{"tick",m.job.target_tick},
      {"accepted",outcome.accepted},{"reason",outcome.reason},
      {"valid_job_reason",valid_job_reason},
      {"backend_ms",m.backend_ms},{"solve_latency_ns",outcome.solve_latency_ns},
      {"first_control",m.first_control},{"clamped_control",outcome.clamped_control},
      {"worker_instance",m.worker_instance},
      {"physical_output_enabled",false},{"closed_loop_verified",false},{"anchor_known",false},
      {"receive_ns",now}});
  }
  void step_dry_run_tick(int64_t now){
    if(!dry_run_active_||!dry_run_nav_)return;
    std::string block_reason;
    p1::Job j;
    bool submit=false;
    usv_mpc::ReferenceMetadata meta;
    bool model_changed=false;
    std::uint64_t target_tick=0;
    {
      std::lock_guard<std::mutex> l(c_mutex_);
      const auto gate_now=p1::monotonic_ns();
      block_reason=dry_run_nav_->nav_gate(gate_now);
      if(block_reason=="ready"&&worker_instance_.empty())block_reason="waiting_worker_instance";
      if(block_reason=="ready"){
        const auto x_arr=dry_run_nav_->composed_state();
        usv_mpc::Vector6d x;for(int i=0;i<6;++i)x[i]=x_arr[static_cast<size_t>(i)];
        const auto ref=dry_run_ref_;
        auto ref_mat=usv_mpc::build_frozen_reference(x,*ref,20,0.2,
          c_.at("reference_start_offset").get<int>(),c_.at("cruise_speed").get<double>(),&meta);
        if(!ref_mat.allFinite()){
          block_reason="reference_nonfinite";
        }else{
          target_tick=dry_run_tick_++;
          const auto selection=registry_.resolve(grid_,grid_,target_tick,model_options_);
          if(!selection){
            block_reason="model_plan_resolve:"+selection.reason;
          }else{
            if(dry_run_model_gen_!=selection.generation){
              dry_run_model_gen_=selection.generation;
              model_changed=true;
            }
            const auto & od=dry_run_nav_->odom();
            const auto & im=dry_run_nav_->imu();
            const int64_t freeze_now=p1::monotonic_ns();
            const int64_t base_sim=std::max<int64_t>(0,od.stamp_ns);
            j.schema_version="p1-solve-job-v1";j.run_id=run_;j.boot_id=boot_;
            j.contract_hash=hash_;j.nominal_hash=nominal_;j.worker_instance=worker_instance_;
            j.target_tick=target_tick;j.task_generation=od.seq;j.model_generation=selection.generation;
            j.config_generation=1;j.schedule_generation=grid_.schedule_generation;
            j.clock_epoch=grid_.clock_epoch;
            j.tick_origin_steady_ns=freeze_now;j.freeze_steady_ns=freeze_now;
            j.deadline_steady_ns=freeze_now+p1::DEADLINE;j.target_steady_ns=freeze_now+p1::T;
            j.frozen_clock_sim_ns=base_sim;j.target_sim_ns=base_sim+p1::T;
            j.frozen_clock_receive_ns=freeze_now;j.assumed_rtf=1.0;
            j.odom_stamp_ns=od.stamp_ns;j.odom_receive_ns=od.receipt_ns;j.odom_sequence=od.seq;
            j.imu_stamp_ns=im.stamp_ns;j.imu_receive_ns=im.receipt_ns;j.imu_sequence=im.seq;
            j.r_from_imu=true;j.horizon_steps=20;j.prediction_dt=0.2;
            for(int i=0;i<6;++i){j.frozen_state[i]=x[i];j.target_state[i]=x[i];}
            std::copy(ref_mat.data(),ref_mat.data()+126,j.reference.begin());
            j.anchor_source="dry_run_nominal_command";j.anchor_producer="";j.anchor_run_id=run_;
            j.anchor_n=dry_run_nav_->nominal_continuity_n();
            const auto a_seq=dry_run_nav_->nominal_anchor_seq();
            const auto a_time=std::min(dry_run_nav_->nominal_anchor_time_ns(),freeze_now);
            j.anchor_sequence={a_seq,a_seq};j.anchor_publish_ns={a_time,a_time};j.anchor_known={true,true};
            j.reset_warmstart=std::abs(usv_mpc::normalize_angle(x[2]-ref_mat(2,0)))>M_PI*0.75;
            j.job_id=dry_run_nav_->jobs_submitted()+1;
            std::string gp_block;
            if(!bind_gp_and_ppo(j,target_tick,j.target_sim_ns,freeze_now,x,ref_mat,
                {j.anchor_n[0],j.anchor_n[1]},false,std::nullopt,nullptr,nullptr,0,&gp_block)){
              block_reason=gp_block;
            }else{
              const auto res=p1::check_job_resources(j,resources_);
              if(!res){
                block_reason=std::string("job_resource_invalid:")+(res.reason?res.reason:"unknown");
              }else{
                dry_run_nav_->record_job_submitted();
                dry_run_jobs_.push_back(j);
                while(dry_run_jobs_.size()>16)dry_run_jobs_.pop_front();
                last_dry_run_block_.clear();
                submit=true;
              }
            }
          }
        }
      }
    }
    if(submit){
      if(model_changed){
        sink_->add({{"type","model_version"},{"target_tick",target_tick},
          {"model_generation",j.model_generation},{"processed_ns",j.freeze_steady_ns}});
      }
      const auto pub_start=p1::monotonic_ns();
      bool pub_ok=false;
      try{job_pub_->publish(j);pub_ok=true;}catch(...){pub_ok=false;}
      const auto pub_end=p1::monotonic_ns();
      sink_->add({{"type","dry_run_job"},{"job_id",j.job_id},{"target_tick",j.target_tick},
        {"model_generation",j.model_generation},{"odom_seq",j.odom_sequence},{"imu_seq",j.imu_sequence},
        {"reference_mode",meta.reference_mode},{"nearest_index",meta.nearest_index},
        {"start_index",meta.start_index},{"anchor_n",j.anchor_n},
        {"publish_start_ns",pub_start},{"publish_end_ns",pub_end},{"success",pub_ok},
        {"physical_output_enabled",false},{"anchor_known",false}});
      return;
    }
    if(block_reason!=last_dry_run_block_||now-last_dry_run_block_log_ns_>=1000000000LL){
      last_dry_run_block_=block_reason;
      last_dry_run_block_log_ns_=now;
      sink_->add({{"type","dry_run_nav_blocked"},{"reason",block_reason},{"at_ns",now}});
    }
  }
  bool commission_monitor_alive()const{return !commission_rc_;}
  void commission_terminal(const char * reason){
    if(!commission_failure_.empty())return;
    commission_failure_=reason;
    commission_rc_=2;finished_=true;
  }
  void commission_loop(){
    auto last_status=0LL;std::uint64_t seq=0;
    auto next_tick=p1::monotonic_ns();
    while(!commission_stop_&&!finished_){
      const auto now=p1::monotonic_ns();
      bool terminal=false;std::string reason;
      p1_shipboard::WorkerFacts wf;
      std::uint64_t jobs_count=0;
      {std::lock_guard<std::mutex> l(c_mutex_);
       wf.pid=expected_worker_pid_;
       wf.instance=worker_instance_;
       wf.model_runtime_ready=monitor_->capability().model_runtime_ready;
       const auto alive=worker_liveness_?worker_liveness_->reason():std::string();
       wf.exited=!alive.empty()&&alive.find("exited")!=std::string::npos;
       monitor_->on_worker(wf);
       monitor_->evaluate(now,0);
       if(dry_run_nav_)jobs_count=dry_run_nav_->jobs_submitted();
       if(monitor_->failed()){terminal=true;reason=monitor_->failure();}
       else if(sink_->failed()){terminal=true;reason=p1_shipboard::reason_log_failed;}
      }
      if(terminal){
        commission_failure_=reason;commission_rc_=2;finished_=true;
        std::lock_guard<std::mutex> l(c_mutex_);
        sink_->add({{"type","commissioning_failure"},{"reason",reason},{"failed_ns",p1::monotonic_ns()},
          {"phase",monitor_->phase()},{"finished",true},{"exit_code",2},
          {"physical_output_enabled",false},{"jobs_submitted",jobs_count}});
        break;
      }
      if(stop_requested){commission_rc_=0;finished_=true;
        std::lock_guard<std::mutex> l(c_mutex_);
        sink_->add({{"type","commissioning_stop"},{"reason","operator_stop"},
          {"stopped_ns",p1::monotonic_ns()},{"phase","stopping"},{"exit_code",0},
          {"jobs_submitted",jobs_count}});
        break;}
      if(dry_run_active_&&monitor_->ready()){
        step_dry_run_tick(now);
      }
      if(now-last_status>=1000000000LL){
        last_status=now;
        auto counters=sink_->counters();
        p1::Json status;
        {std::lock_guard<std::mutex> l(c_mutex_);
         status=monitor_->status_json(now,++seq,p1::Json{{"run_id",run_},{"boot_id",boot_},
           {"host_boot_id",p1::boot_id()},{"contract_hash",hash_},{"plan_sha256",plan_sha_}});
         if(dry_run_active_&&dry_run_nav_){
           status["mode"]=mode_;
           status["jobs_submitted"]=dry_run_nav_->jobs_submitted();
           status["dry_run"]=dry_run_nav_->status_json(now);
         }}
        status["source"]={{"generated",counters.generated},{"emitted",counters.emitted},
          {"dropped",counters.dropped},{"failed",counters.failed}};
        const auto text=status.dump();
        sink_->add({{"type","commissioning_status"},{"status",status},{"emitted_ns",p1::monotonic_ns()}});
        std_msgs::msg::String msg;msg.data=text;
        try{status_pub_->publish(msg);}catch(...){commission_failure_=p1_shipboard::reason_log_failed;commission_rc_=2;finished_=true;break;}
      }
      if(dry_run_active_){
        next_tick+=p1::T;
        const auto wake=p1::monotonic_ns();
        if(next_tick<wake)next_tick=wake+p1::T;
        p1::sleep_until_monotonic(next_tick);
      }else{
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
      }
    }
    if(commission_rc_==0)finished_=true;
  }

  std::unique_ptr<p1_shipboard::Monitor> monitor_;std::unique_ptr<p1_dry_run::DryRunCoordinator> dry_run_nav_;std::shared_ptr<usv_mpc::ReferenceInput> dry_run_ref_;std::deque<p1::Job> dry_run_jobs_;std::uint64_t dry_run_tick_=1,dry_run_model_gen_=0;std::string last_dry_run_block_;std::int64_t last_dry_run_block_log_ns_=0;std::thread commission_thread_;std::mutex c_mutex_;std::atomic<bool> commission_stop_{false},commission_active_{false},dry_run_active_{false};std::atomic<int> commission_rc_{0};std::string commission_failure_,plan_sha_,plan_file_text_;rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_pub_;rclcpp::Subscription<mavros_msgs::msg::State>::SharedPtr c_state_;rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr c_odom_;rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr c_imu_;rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr c_path_;rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr c_profile_;rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr c_stop_;
  p1::Json c_;usv_mpc::MpcParams params_;p1::Limits limits_;std::string run_,hash_,mode_,boot_,nominal_,legacy_run_,legacy_producer_,worker_instance_,path_fingerprint_,profile_fingerprint_,recording_observer_;int64_t expected_worker_pid_=0;
  std::unique_ptr<p1::WorkerLiveness> worker_liveness_;
  std::unique_ptr<p1::PreparationBarrier> preparation_barrier_;std::atomic<bool> preparation_barrier_active_{false};
  std::unique_ptr<p1::TickBarrier> tick_barrier_;int64_t test_skip_tick_=0;
  std::unique_ptr<p1::CapabilityLease> capability_lease_;
  std::mutex mutex_,prep_mutex_;std::condition_variable prep_cv_;std::optional<Preparation> pending_;std::thread prep_,tick_;std::atomic<bool> prep_stop_{false},finished_{false},stopping_{false},normal_complete_{true},worker_unusable_{false},worker_valid_{false};std::unique_ptr<Sink> sink_;
  std::string diag_file_;std::unique_ptr<p1_clock_diag::BoundedTrace<kCallbackTraceCapacity>> diag_callbacks_;std::unique_ptr<p1_clock_diag::BoundedTrace<kTickTraceCapacity>> diag_tick_;std::unique_ptr<p1_clock_diag::Diagnostics> diag_;
  p1::ResourceLimits resources_;model_reference::Registry registry_;model_reference::Grid grid_;model_reference::Options model_options_{};p1_gp_snap::GpSnapshotRegistry gp_registry_{};std::string nominal_hydro_sha_;bool gp_allow_ood_fallback_zero_=true;bool ppo_enabled_=false;double ppo_lambda_pi_=0.0;std::string ppo_expected_policy_sha_,ppo_expected_obs_contract_;int64_t ppo_max_age_ns_=450000000LL;std::deque<ProposalEntry> proposals_;Eigen::MatrixXd last_cand_x_,last_cand_u_;uint64_t last_cand_tick_=0;RunVersion version_;p1::Anchor anchor_;p1::Admission admission_;std::shared_ptr<const p1::Candidate> candidate_;std::deque<p1::Job> jobs_;std::deque<usv_mpc::HeldInputEvent> history_;std::deque<p1::PublicationEvent> publication_history_;uint64_t legacy_sequence_=0;std::shared_ptr<const usv_mpc::ReferenceInput> ref_;usv_mpc::Vector6d state_=usv_mpc::Vector6d::Zero();
  uint64_t current_tick_=0,job_id_=0,decision_seq_=0,odom_received_=0,imu_received_=0,odom_seq_=0,imu_seq_=0,path_seq_=0,profile_seq_=0,worker_active_=0;int64_t worker_active_since_=0,odom_stamp_=0,imu_stamp_=0,odom_receive_=0,imu_receive_=0,clock_receive_=0,sim_=0,last_clock_advance_=0,last_accepted_=0;bool mixed_=false;std::atomic<bool> paused_{false},rtf_valid_{false};double rtf_=0;p1::ClockWindow clock_window_;Declared declared_{};
  rclcpp::Publisher<p1::Job>::SharedPtr job_pub_;rclcpp::Publisher<usv_research_interfaces::msg::PlantCommand>::SharedPtr plant_pub_;uint64_t plant_sequence_=0;rclcpp::Subscription<usv_research_interfaces::msg::PlantReceipt>::SharedPtr receipt_sub_;rclcpp::Subscription<usv_research_interfaces::msg::PlantHoldClose>::SharedPtr hold_close_sub_;p1_receipt::ReceiptAnchor receipts_{};std::string plant_producer_;bool command_pending_=false;uint64_t pending_execution_before_=0;uint64_t pending_sequence_=0;rclcpp::Publisher<p1::Decision>::SharedPtr decision_pub_;rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr left_,right_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_;rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_;rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr path_;rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr profile_;rclcpp::Subscription<rosgraph_msgs::msg::Clock>::SharedPtr clock_;rclcpp::Subscription<p1::Candidate>::SharedPtr candidates_;rclcpp::Subscription<p1::Capability>::SharedPtr capabilities_;rclcpp::Subscription<p1::Proposal>::SharedPtr proposal_sub_;rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr stop_;rclcpp::Subscription<usv_research_interfaces::msg::AppliedControl>::SharedPtr applied_;
};
int main(int argc,char **argv){rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,stop_signal);std::signal(SIGTERM,stop_signal);
try{auto node=std::make_shared<Regulator>();rclcpp::executors::SingleThreadedExecutor exec;exec.add_node(node);while(!node->finished()&&rclcpp::ok()){exec.spin_some(std::chrono::milliseconds(10));std::this_thread::sleep_for(std::chrono::milliseconds(1));}exec.remove_node(node);
// 服务接管分支的终局由 monitor/停止请求决定，不由旧 tick 设置 finished_ 决定；
// 失败状态必须在 reset 之前捕获，否则只能报"正常退出"。
const bool was_commissioning=node->commissioning();const int commissioning_rc=node->commissioning_exit_code();
bool closed=node->close_source();node.reset();rclcpp::shutdown();
if(was_commissioning&&commissioning_rc!=0)return 2;
return closed?0:2;}catch(const std::exception & e){fprintf(stderr,"regulator fatal: %s\n",e.what());rclcpp::shutdown();return 1;}}
