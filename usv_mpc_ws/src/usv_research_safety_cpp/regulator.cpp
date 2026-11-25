// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include <atomic>
#include <condition_variable>
#include <csignal>
#include <deque>
#include <fstream>
#include <mutex>
#include <optional>
#include <regex>
#include <thread>
#include <unistd.h>
#include <rclcpp/rclcpp.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <nav_msgs/msg/path.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <std_msgs/msg/float64.hpp>
#include <std_msgs/msg/bool.hpp>
#include <rosgraph_msgs/msg/clock.hpp>
#include "usv_research_interfaces/msg/applied_control.hpp"
#include "usv_research_interfaces/msg/plant_command.hpp"
#include "usv_research_interfaces/msg/plant_receipt.hpp"
#include "usv_research_interfaces/msg/plant_hold_close.hpp"
#include "p1_receipt_anchor.hpp"
#include "usv_nmpc/p1_input_core.hpp"
#include "p1_contract.hpp"
#include "p1_job_wire.hpp"
#include "p1_plan_bridge.hpp"
#include "p1_sys_utils.hpp"
#include "p1_admission.hpp"
#include "p1_clock_window.hpp"
#include "p1_worker_liveness.hpp"
#include "p1_preparation_barrier.hpp"
#include "p1_capability_lease.hpp"
#include "p1_tick_barrier.hpp"
namespace {
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
    auto contract=p1::load_verified_contract(
      declare_parameter<std::string>("contract_file",""),hash_);
    p1::require_runtime_contract_mode(contract.profile,mode_);
    spec_=std::move(contract.spec);
    faults_enabled_=spec_.faults.faults_enabled(contract.profile);
    boot_=declare_parameter<std::string>("boot_id","");
    if(boot_.empty())boot_=p1::boot_id();
    legacy_run_=declare_parameter<std::string>("legacy_run_id","");
    // 方案 A：模型代由计划决定，不是由 regulator 自增。计划字节摘要必须与声明一致，
    // 且计划自身的 grid 必须与合同时基逐位一致（grid_of_plan 内已断言）。
    {const auto plan_file=declare_parameter<std::string>("model_plan_file","");
     const auto plan_sha=declare_parameter<std::string>("model_plan_sha256","");
     p1::contract_require(!plan_file.empty()&&std::regex_match(plan_sha,std::regex("[0-9a-f]{64}")),
                      "model plan identity required");
     const auto plan_text=p1::read_text(plan_file);
     p1::contract_require(p1::digest(plan_text)==plan_sha,"model plan hash mismatch");
     grid_=p1::grid_of_plan(plan_text,spec_);
     registry_=model_reference::default_registry();{const auto chk=registry_.verify_plan_132_json(plan_text,grid_);p1::contract_require(chk.ok,"plan rejected: "+chk.reason);}
     // 计划已通过校验，切换必须开启；默认值是 false，"忘了打开"会让整条链路
     // 静默地只用单代而不报错。
     model_options_.model_switch_enabled=true;}
expected_worker_pid_=declare_parameter<int64_t>("worker_pid",0);
    worker_liveness_=std::make_unique<p1::WorkerLiveness>(expected_worker_pid_);
    recording_observer_=declare_parameter<std::string>("recording_observer_node","p1_calibration_driver");
    if(recording_observer_.empty()||recording_observer_.size()>128)throw std::runtime_error("invalid bounded recording observer node");
    if(run_.empty()||run_.size()>128||(mode_!="shadow"&&mode_!="execute"&&mode_!="no_output"&&mode_!="controlled_sim"))throw std::runtime_error("identity/mode invalid");
    preparation_barrier_=std::make_unique<p1::PreparationBarrier>(declare_parameter<int64_t>("test_prepare_block_ms",0),mode_,faults_enabled_);
    tick_barrier_=std::make_unique<p1::TickBarrier>(declare_parameter<int64_t>("test_tick_block_ms",0),mode_,faults_enabled_);
    test_skip_tick_=declare_parameter<int64_t>("test_skip_tick",0);
    if(test_skip_tick_<0)throw std::runtime_error("invalid negative test_skip_tick");
    if(test_skip_tick_>0&&!faults_enabled_)
      throw std::runtime_error("unqualified skip_tick fault injection");
    capability_lease_=std::make_unique<p1::CapabilityLease>(spec_.timing.worker_capability_receipt_timeout_ns);
    limits_.tolerance=spec_.actuator.activation_tolerance;limits_.rho=spec_.actuator.rho_n_s;limits_.hold_ns=spec_.actuator.hold_ns;limits_.low=spec_.actuator.command_min_n;limits_.high=spec_.actuator.command_max_n;if(!limits_.valid())throw std::runtime_error("invalid finite limits");
    ref_=std::make_shared<const usv_mpc::ReferenceInput>();
    job_pub_=create_publisher<p1::Job>("/p1/solve_job",rclcpp::QoS(1).reliable());
    if(mode_=="controlled_sim"){
      plant_pub_=create_publisher<usv_research_interfaces::msg::PlantCommand>("/p1/plant_command",rclcpp::QoS(1).reliable());
    }
    decision_pub_=create_publisher<p1::Decision>("/p1/execution_decision",rclcpp::QoS(1).reliable());
    sink_=std::make_unique<Sink>(declare_parameter<std::string>("source_file",""),spec_.resources.log_capacity,decision_pub_);
    if(mode_=="execute") {left_=create_publisher<std_msgs::msg::Float64>(spec_.topics.output_topics.left,rclcpp::QoS(1).reliable());right_=create_publisher<std_msgs::msg::Float64>(spec_.topics.output_topics.right,rclcpp::QoS(1).reliable());}
    odom_=create_subscription<nav_msgs::msg::Odometry>(spec_.topics.input_topics.odom,rclcpp::SensorDataQoS(),[this](nav_msgs::msg::Odometry::SharedPtr m){odom(*m);});
    imu_=create_subscription<sensor_msgs::msg::Imu>(spec_.topics.input_topics.imu,rclcpp::SensorDataQoS(),[this](sensor_msgs::msg::Imu::SharedPtr m){imu(*m);});
    path_=create_subscription<nav_msgs::msg::Path>(spec_.topics.input_topics.path,rclcpp::QoS(1).reliable(),[this](nav_msgs::msg::Path::SharedPtr m){path(*m);});
    profile_=create_subscription<std_msgs::msg::Float64MultiArray>(spec_.topics.input_topics.profile,rclcpp::QoS(1).reliable(),[this](std_msgs::msg::Float64MultiArray::SharedPtr m){profile(*m);});
    clock_=create_subscription<rosgraph_msgs::msg::Clock>("/clock",rclcpp::ClockQoS(),[this](rosgraph_msgs::msg::Clock::SharedPtr m){clock(*m);});
    candidates_=create_subscription<p1::Candidate>("/p1/solve_candidate",rclcpp::QoS(1).reliable(),[this](p1::Candidate::SharedPtr m){candidate(*m);});
    capabilities_=create_subscription<p1::Capability>("/p1/worker_capability",rclcpp::QoS(1).reliable().transient_local(),[this](p1::Capability::SharedPtr m){capability(*m);});
    stop_=create_subscription<std_msgs::msg::Bool>("/p1/stop",rclcpp::QoS(1).reliable(),[](std_msgs::msg::Bool::SharedPtr m){if(m->data)stop_requested=true;});
    if(mode_=="shadow")applied_=create_subscription<usv_research_interfaces::msg::AppliedControl>("/research/control/applied",rclcpp::QoS(10).reliable(),[this](usv_research_interfaces::msg::AppliedControl::SharedPtr m){legacy_applied(*m);});
    if(mode_=="controlled_sim"){
      // 唯一执行事实通道：plant 回执与 hold 闭合事件。
      receipt_sub_=create_subscription<usv_research_interfaces::msg::PlantReceipt>("/p1/plant_receipt",rclcpp::QoS(16).reliable().transient_local(),[this](usv_research_interfaces::msg::PlantReceipt::SharedPtr m){receipt(*m);});
      hold_close_sub_=create_subscription<usv_research_interfaces::msg::PlantHoldClose>("/p1/plant_hold_close",rclcpp::QoS(16).reliable(),[this](usv_research_interfaces::msg::PlantHoldClose::SharedPtr m){hold_close(*m);});
      receipts_.restart(p1::digest(run_+boot_));
      plant_producer_=p1::digest(run_+boot_);
    }
    if(mode_=="no_output") {auto now=p1::monotonic_ns();anchor_.known={true,true};anchor_.seq={1,1};anchor_.time={now,now};}
    wait_recording_ready();prep_=std::thread([this]{prepare_loop();});tick_=std::thread([this]{tick_loop();});
    sink_->add({{"type","startup"},{"schema","p1-regulator-v1"},{"run_id",run_},{"mode",mode_},{"pid",getpid()},{"boot",boot_},{"clock","CLOCK_MONOTONIC"},{"contract_hash",hash_},{"physical_publisher_endpoints",mode_=="execute"?2:0},{"worker_liveness_policy","linux_pidfd_no_wait"},{"publication_history_policy","full_consecutive_publisher_history"},{"input_anchor_source",mode_=="shadow"?"legacy_publisher":mode_=="execute"?"regulator_publisher":"synthetic_static_fixture"},
      {"anchor_source",mode_=="controlled_sim"?"plant_receipt":"legacy_publisher"},
      {"boot_id",boot_},
      {"typed_command_topics",p1::Json::array({"/p1/plant_command"})},
      {"raw_command_topics",p1::Json::array()},
      {"diagnostic_only",mode_!="execute"}});
  }
  ~Regulator(){stop_requested=true;prep_stop_=true;prep_cv_.notify_all();if(tick_.joinable())tick_.join();if(prep_.joinable())prep_.join();sink_->close();}
  bool finished()const{return finished_;}
  bool close_source(){if(tick_.joinable())tick_.join();prep_stop_=true;prep_cv_.notify_all();if(prep_.joinable())prep_.join();sink_->close();fprintf(stdout,"REGULATOR_CLOSE_FLUSH_SUCCESS=%s\n",sink_->failed()?"false":"true");return !sink_->failed();}
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
    usv_mpc::InputEligibility e;e.odom_received=s.odom_seq>0;e.path_received=!s.ref->path.empty();e.path_size=s.ref->path.size();e.now_s=now/1e9;e.last_odom_s=s.odom_receive/1e9;e.odom_timeout_s=spec_.timing.odom_age_ns/1e9;
    auto check=usv_mpc::input_eligibility(e);if(!check.first)return check.second;
    if(!s.state.allFinite())return "nonfinite";
    if(s.mixed&&(now-s.imu_receive>spec_.timing.imu_age_ns||std::abs(s.imu_stamp-s.odom_stamp)>spec_.timing.mixed_skew_ns))return "mixed_source_age_or_skew";
    if(!s.clock_receive||now-s.clock_receive>spec_.timing.clock_age_ns||s.paused)return "clock_missing_stale_paused";
    if(!s.rtf_valid)return "rtf_unaligned";
    const p1::SourceAgeLimits source_limits{
      spec_.timing.odom_age_ns,spec_.timing.imu_age_ns,
      spec_.timing.odom_sim_lag_ns,spec_.timing.imu_sim_lag_ns,
      spec_.timing.source_future_slack_ns};
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
  bool named_subscription(const std::string & topic,const std::string & name,bool recorder=false){
    for(const auto & endpoint:get_subscriptions_info_by_topic(topic)){
      if(recorder?endpoint.node_name().find("recorder")!=std::string::npos:endpoint.node_name()==name)return true;
    }
    return false;
  }
  void wait_recording_ready(){
    const int64_t start=p1::monotonic_ns(),timeout=spec_.timing.recording_ready_timeout_ns;
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
  void odom(const nav_msgs::msg::Odometry & m){auto now=p1::monotonic_ns();auto & p=m.pose.pose.position;auto & q=m.pose.pose.orientation;auto & t=m.twist.twist;std::array<double,5> a={p.x,p.y,t.linear.x,t.linear.y,t.angular.z};std::array<double,4> quat={q.x,q.y,q.z,q.w};bool valid=usv_mpc::admit_odom(a,quat)&&m.header.frame_id==spec_.topics.expected_pose_frame&&m.child_frame_id==spec_.topics.expected_child_frame;std::lock_guard<std::mutex> l(mutex_);++odom_received_;
    if(valid){
      state_=usv_mpc::compose_odom(a,quat);odom_seq_=odom_received_;odom_stamp_=stamp(m.header.stamp);odom_receive_=now;mixed_=false;}
    sink_->add({{"type","odom_admission"},{"sequence",odom_received_},{"valid",valid},{"pose_frame",m.header.frame_id.substr(0,128)},{"pose_frame_truncated",m.header.frame_id.size()>128},{"child_frame",m.child_frame_id.substr(0,128)},{"child_frame_truncated",m.child_frame_id.size()>128},{"accepted_sequence",odom_seq_},{"stamp_ns",stamp(m.header.stamp)},{"receive_ns",now},{"state",std::array<double,6>{state_[0],state_[1],state_[2],state_[3],state_[4],state_[5]}}});
  }
  void imu(const sensor_msgs::msg::Imu & m){auto now=p1::monotonic_ns();std::lock_guard<std::mutex> l(mutex_);++imu_received_;const bool valid=usv_mpc::admit_imu(m.angular_velocity.z)&&m.header.frame_id==spec_.topics.expected_imu_frame;if(valid){usv_mpc::compose_imu(state_,m.angular_velocity.z);imu_seq_=imu_received_;imu_stamp_=stamp(m.header.stamp);imu_receive_=now;mixed_=true;}sink_->add({{"type","imu_admission"},{"sequence",imu_received_},{"valid",valid},{"frame_id",m.header.frame_id.substr(0,128)},{"frame_truncated",m.header.frame_id.size()>128},{"r_value",m.angular_velocity.z},{"accepted_sequence",imu_seq_},{"stamp_ns",stamp(m.header.stamp)},{"receive_ns",now}});}
  void path(const nav_msgs::msg::Path & m){auto next=std::make_shared<usv_mpc::ReferenceInput>();std::string fingerprint;
    const auto resource=p1::check_path_resources(m,spec_.resources);const bool resource_ok=bool(resource);
    bool valid=resource_ok&&m.header.frame_id==spec_.topics.expected_pose_frame;
    if(valid)for(auto & p:m.poses){auto & q=p.pose.orientation;double yaw=usv_mpc::quaternion_to_yaw(q.x,q.y,q.z,q.w);if(!std::isfinite(p.pose.position.x)||!std::isfinite(p.pose.position.y)||!std::isfinite(yaw)){valid=false;break;}next->path.push_back({p.pose.position.x,p.pose.position.y,yaw});}
    if(!valid)next->path.clear();
    fingerprint=p1::digest(p1::Json{{"frame",resource_ok?m.header.frame_id:std::string("resource_rejected")},{"path",next->path}}.dump());
    std::lock_guard<std::mutex> l(mutex_);next->profile=ref_->profile;next->profile_stamp=ref_->profile_stamp;next->profile_sequence=ref_->profile_sequence;next->path_sequence=++path_seq_;next->path_stamp={m.header.stamp.sec,int(m.header.stamp.nanosec)};
    if(fingerprint!=path_fingerprint_||next->path.size()<2){version_.task++;path_fingerprint_=fingerprint;invalidate_locked();}
    ref_=next;sink_->add({{"type","path_version"},{"received_sequence",path_seq_},{"task_generation",version_.task},{"fingerprint",fingerprint},{"points",next->path.size()},{"valid",valid},{"resource_valid",resource_ok},{"received_points",m.poses.size()},{"frame_bytes",m.header.frame_id.size()},{"processed_ns",p1::monotonic_ns()}});
  }
  void profile(const std_msgs::msg::Float64MultiArray & m){auto next=std::make_shared<usv_mpc::ReferenceInput>();const auto resource=p1::check_profile_resources(m,spec_.resources);const bool metadata_ok=bool(resource);
    bool valid=metadata_ok&&!m.data.empty()&&m.data.size()%4==0&&m.data.size()/4<=spec_.resources.max_profile_rows;std::vector<std::string> labels;if(metadata_ok)for(auto & d:m.layout.dim)labels.push_back(d.label);bool stamp_ok=false;if(metadata_ok)next->profile_stamp=usv_mpc::parse_profile_stamp(labels,stamp_ok);if(!stamp_ok)next->profile_stamp={-1,-1};
    if(valid){for(size_t i=0;i<m.data.size()/4;++i){std::array<double,4> r={m.data[4*i],m.data[4*i+1],m.data[4*i+2],m.data[4*i+3]};if(!p1::finite_array(r)||(i&&r[3]<=m.data[4*(i-1)+3])){valid=false;break;}next->profile.push_back(r);}}if(!valid)next->profile.clear();auto fp=p1::digest(p1::Json(next->profile).dump());
    std::lock_guard<std::mutex> l(mutex_);next->path=ref_->path;next->path_stamp=ref_->path_stamp;next->path_sequence=ref_->path_sequence;next->profile_sequence=++profile_seq_;if(fp!=profile_fingerprint_){version_.task++;profile_fingerprint_=fp;invalidate_locked();}ref_=next;sink_->add({{"type","profile_version"},{"received_sequence",profile_seq_},{"task_generation",version_.task},{"fingerprint",fp},{"rows",next->profile.size()},{"valid",valid},{"resource_valid",metadata_ok&&m.data.size()<=spec_.resources.max_profile_rows*4},{"received_data_elements",m.data.size()},{"received_dims",m.layout.dim.size()},{"processed_ns",p1::monotonic_ns()}});
  }
  void clock(const rosgraph_msgs::msg::Clock & m){auto now=p1::monotonic_ns(),s=stamp(m.clock);std::lock_guard<std::mutex> l(mutex_);if(clock_receive_&&(s<sim_||s-sim_>5000000000LL)){version_.epoch++;version_.schedule++;clock_window_.reset();rtf_valid_=false;rtf_=0;history_.clear();publication_history_.clear();anchor_.known={false,false};invalidate_locked();}
    if(s!=sim_){last_clock_advance_=now;if(paused_){paused_=false;version_.schedule++;invalidate_locked();}}
    sim_=s;clock_receive_=now;
    const auto estimate=clock_window_.observe(now,s,spec_.timing.rtf_low,spec_.timing.rtf_high);
    rtf_=estimate.value;rtf_valid_=estimate.valid;
    sink_->add({{"type","clock"},{"sim_ns",s},{"receive_ns",now},{"epoch",version_.epoch},{"schedule_generation",version_.schedule},{"paused",paused_.load()},{"rtf",rtf_},{"rtf_valid",rtf_valid_.load()},{"rtf_window_span_ns",estimate.span_ns},{"rtf_stored_samples",estimate.stored_samples}});
  }
  void capability(const p1::Capability & m){const auto received=p1::monotonic_ns();auto resource=p1::check_capability_resources(m);if(!resource){sink_->add({{"type","resource_rejected"},{"interface","capability"},{"reason",resource.reason},{"field",resource.field},{"observed",resource.observed},{"limit",resource.limit},{"receive_ns",received},{"renewed",false}});return;}std::lock_guard<std::mutex> l(mutex_);const auto now=p1::monotonic_ns();check_worker_locked(now);const auto before=capability_lease_->last_valid_ns();
    const bool identity=m.run_id==run_&&m.boot_id==boot_&&m.contract_hash==hash_&&m.nominal_hash==spec_.identity.nominal_hash&&m.pid==expected_worker_pid_;
    const bool valid=identity&&m.schema_version=="p1-worker-capability-v2"&&m.clock_name=="CLOCK_MONOTONIC"&&m.backend=="acados"&&m.matrix_layout=="column_major"&&m.horizon_steps==static_cast<uint32_t>(spec_.mpc.N)&&m.prediction_dt==spec_.mpc.dt&&!m.fatal&&!m.worker_instance.empty()&&m.startup_ns>0&&m.fault_injection_enabled==faults_enabled_;
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
    std::lock_guard<std::mutex> l(mutex_);const auto now=p1::monotonic_ns();
    // 只有本 regulator 发出的命令所产生的回执属于执行链。刺激注入的命令
    // 也会得到回执（late/duplicate/rejected），把它并进链会伪造出序号断档。
    // bootstrap 是链的根：它由 plant 独立发布，不带 regulator 的生产者身份。
    if(!plant_producer_.empty()&&m.disposition!="bootstrap"&&
       m.producer_instance_id!=plant_producer_){
      sink_->add({{"type","foreign_receipt"},{"sequence",m.sequence},
        {"producer_instance_id",m.producer_instance_id},{"disposition",m.disposition},
        {"reason",m.reason},{"processed_ns",now}});
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
      {"anchor_known",receipts_.known()},{"processed_ns",now}});
  }
  /// hold 闭合：窗口内的非零推力已经结束。缺口内推力为零，不做隐式保持。
  void hold_close(const usv_research_interfaces::msg::PlantHoldClose & m){
    std::lock_guard<std::mutex> l(mutex_);const auto now=p1::monotonic_ns();
    bool truncated=false;
    if(m.reason=="stop")truncated=receipts_.close_at(m.close_steady_ns);
    sink_->add({{"type","plant_hold_close_admission"},{"execution_index",m.execution_index},
      {"reason",m.reason},{"close_steady_ns",m.close_steady_ns},
      {"close_sim_ns",m.close_sim_ns},{"truncated",truncated},
      {"executed_end_steady_ns",m.executed_end_steady_ns},{"processed_ns",now}});
  }
  void legacy_applied(const usv_research_interfaces::msg::AppliedControl & m){
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
  void push_publication_locked(const p1::PublicationEvent & e){publication_history_.push_back(e);while(publication_history_.size()>spec_.resources.history_capacity)publication_history_.pop_front();}
  void anchor_evidence_locked(const p1::Ticket & t,const p1::Decision & d){
    p1::Json entries=p1::Json::array();
    for(const auto & e:publication_history_)if(e.sequence>=t.anchor.seq[e.channel]&&e.sequence<=anchor_.seq[e.channel])entries.push_back({{"channel",e.channel},{"sequence",e.sequence},{"publish_ns",e.publish_ns},{"n",e.n},{"known",e.known}});
    sink_->add({{"type","anchor_validation"},{"sequence",d.sequence},{"job_id",t.id},{"mode",mode_},{"producer",legacy_producer_},{"run_id",legacy_run_},{"clock_epoch",version_.epoch},{"check_ns",d.activation_commit_ns},{"expected_n",t.anchor.n},{"expected_sequence",t.anchor.seq},{"expected_publish_ns",t.anchor.time},{"expected_known",t.anchor.known},{"actual_n",anchor_.n},{"actual_sequence",anchor_.seq},{"actual_publish_ns",anchor_.time},{"actual_known",anchor_.known},{"entries",entries},{"history_reason",p1::publication_history_check(t.anchor,anchor_,publication_history_)},{"decision_reason",d.reason},{"candidate_accepted",d.candidate_accepted},{"accepted",d.candidate_accepted}});
  }
  void push_history_locked(const usv_mpc::HeldInputEvent & e){if(!history_.empty()&&e.sim_ns<history_.back().sim_ns){history_.clear();publication_history_.clear();anchor_.known={false,false};invalidate_locked();return;}history_.push_back(e);while(history_.size()>spec_.resources.history_capacity)history_.pop_front();}
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
    if(mode_!="no_output"&&(!found[0]||!found[1]))return false;
    return usv_mpc::propagate_publisher_nominal(s.state,s.odom_stamp,target_sim,initial,hist,spec_.mpc.hydro);}
  void candidate(const p1::Candidate & m){auto resource=p1::check_candidate_resources(m,spec_.resources);if(!resource){sink_->add({{"type","resource_rejected"},{"interface","candidate"},{"job_id",m.job.job_id},{"reason",resource.reason},{"field",resource.field},{"observed",resource.observed},{"limit",resource.limit},{"receive_ns",p1::monotonic_ns()},{"accepted_registration",false}});return;}auto immutable=std::make_shared<const p1::Candidate>(m);auto reason=p1::valid_job(m.job,p1::make_job_context(spec_,run_,boot_,hash_,worker_instance_));if(reason.empty()&&(m.worker_instance!=worker_instance_||m.backend!="acados"))reason="foreign_worker";
    if(reason.empty()&&(!m.success||!m.prediction_available||!m.solver_invoked))reason="solver_failed";
    if(reason.empty()&&(!p1::finite_array(m.x_prediction)||!p1::finite_array(m.u_prediction)||!p1::finite_array(m.first_control)||!std::isfinite(m.backend_ms)||m.backend_ms<0||m.solve_end_ns<m.solve_start_ns))reason="nonfinite_or_timing";
    if(reason.empty())for(int i=0;i<2;++i)if(std::abs(m.first_control[i]-m.u_prediction[i])>1e-8)reason="first_control_mismatch";
    if(reason.empty())for(int i=0;i<6;++i)if(std::abs(m.x_prediction[i]-m.job.target_state[i])>1e-7)reason="prediction_initial_mismatch";
    std::lock_guard<std::mutex> l(mutex_);auto expected=std::find_if(jobs_.begin(),jobs_.end(),[&](const p1::Job & j){return j.job_id==m.job.job_id;});
    if(reason.empty()&&(expected==jobs_.end()||!p1::job_echo_equals(*expected,m.job)))reason="job_echo_mismatch";
    auto now=p1::monotonic_ns();if(reason.empty()&&!(m.job.freeze_steady_ns<=m.worker_receive_ns&&m.worker_receive_ns<=m.solve_start_ns&&m.solve_start_ns<=m.solve_end_ns&&m.solve_end_ns<=now))reason="native_timing_order";p1::Ticket t;t.id=m.job.job_id;t.target=m.job.target_tick;t.origin=m.job.tick_origin_steady_ns;t.deadline=m.job.deadline_steady_ns;t.target_ns=m.job.target_steady_ns;// 票据的版本是**Job 的版本**（计划网格 + 运行代数），与运行快照的
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
    sink_->add({{"type","candidate_registration"},{"job",p1::job_json(m.job)},{"ready_commit_ns",now},{"accepted_registration",reason.empty()},{"reason",reason},{"solve_start_ns",m.solve_start_ns},{"solve_end_ns",m.solve_end_ns},{"worker_instance",m.worker_instance},{"first_control",m.first_control}});
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
    auto & s=p.s;int64_t target_sim=s.sim+(p.origin+spec_.timing.T_ns-s.clock_receive);auto x=s.state;if(!predict(s,target_sim)){sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"reason","history_or_propagation"}});continue;}
    usv_mpc::ReferenceMetadata meta;auto ref=usv_mpc::build_frozen_reference(s.state,*s.ref,spec_.mpc.N,spec_.mpc.dt,spec_.mpc.reference_start_offset,spec_.mpc.cruise_speed,&meta);if(!ref.allFinite())continue;
    p1::Job j;j.schema_version="p1-solve-job-v1";j.run_id=run_;j.boot_id=boot_;j.contract_hash=hash_;j.nominal_hash=spec_.identity.nominal_hash;const auto selection=registry_.resolve(grid_,grid_,p.tick+1,model_options_);
    if(!selection){sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"reason","model_plan_resolve:"+selection.reason},{"processed_ns",p1::monotonic_ns()}});continue;}
    {std::lock_guard<std::mutex> l(mutex_);
       if(version_.model!=selection.generation){version_.model=selection.generation;invalidate_locked();
         sink_->add({{"type","model_version"},{"target_tick",p.tick+1},{"model_generation",version_.model},{"processed_ns",p1::monotonic_ns()}});}}
    j.target_tick=p.tick+1;j.task_generation=s.version.task;j.model_generation=selection.generation;j.config_generation=s.version.config;j.schedule_generation=grid_.schedule_generation;j.clock_epoch=grid_.clock_epoch;j.tick_origin_steady_ns=p.origin;j.freeze_steady_ns=s.freeze;j.deadline_steady_ns=p.origin+spec_.timing.deadline_ns;j.target_steady_ns=p.origin+spec_.timing.T_ns;j.target_sim_ns=target_sim;j.odom_stamp_ns=s.odom_stamp;j.imu_stamp_ns=s.mixed?s.imu_stamp:0;j.odom_receive_ns=s.odom_receive;j.imu_receive_ns=s.mixed?s.imu_receive:0;j.odom_sequence=s.odom_seq;j.imu_sequence=s.mixed?s.imu_seq:0;j.r_from_imu=s.mixed;j.horizon_steps=spec_.mpc.N;j.prediction_dt=spec_.mpc.dt;std::copy(x.data(),x.data()+6,j.frozen_state.begin());std::copy(s.state.data(),s.state.data()+6,j.target_state.begin());std::copy(ref.data(),ref.data()+j.reference.size(),j.reference.begin());j.frozen_clock_sim_ns=s.sim;j.frozen_clock_receive_ns=s.clock_receive;j.assumed_rtf=1.0;j.anchor_source=s.anchor_source;j.anchor_producer=s.anchor_producer;j.anchor_run_id=s.anchor_run;for(auto & e:s.history){j.history_sim_ns.push_back(e.sim_ns);j.history_channel.push_back(e.channel);j.history_n.push_back(e.value);}j.anchor_n=s.anchor.n;j.anchor_sequence=s.anchor.seq;j.anchor_publish_ns=s.anchor.time;j.anchor_known=s.anchor.known;j.reset_warmstart=std::abs(usv_mpc::normalize_angle(s.state[2]-ref(2,0)))>M_PI*.75;
    int64_t submit_commit_ns;
    {std::lock_guard<std::mutex> l(mutex_);check_worker_locked(p1::monotonic_ns());submit_commit_ns=p1::monotonic_ns();std::string rejected;
      if(stopping_)rejected="shutdown_before_submit";else if(worker_unusable_)rejected="worker_unusable_before_submit";else if(!worker_valid_)rejected="worker_unvalidated_before_submit";else if(sink_->failed())rejected="source_failed_before_submit";else if(!(s.version==version_))rejected="version_changed_before_submit";else if(current_tick_!=p.tick)rejected="tick_changed_before_submit";else if(submit_commit_ns>j.deadline_steady_ns)rejected="deadline_expired_before_submit";
      if(!rejected.empty()){sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"preparation_tick",p.tick},{"current_tick",current_tick_},{"deadline_ns",j.deadline_steady_ns},{"processed_ns",submit_commit_ns},{"reason",rejected}});continue;}j.worker_instance=worker_instance_;auto resource=p1::check_job_resources(j,spec_.resources);if(!resource){sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"reason",resource.reason},{"field",resource.field},{"observed",resource.observed},{"limit",resource.limit}});continue;}j.job_id=++job_id_;jobs_.push_back(j);while(jobs_.size()>8)jobs_.pop_front();}
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
      begin=origin+((offset+spec_.timing.T_ns-1)/spec_.timing.T_ns)*spec_.timing.T_ns;}
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
    m.apply_begin_steady_ns=begin;m.apply_end_steady_ns=begin+spec_.timing.T_ns;
    m.deadline_steady_ns=begin+spec_.timing.deadline_ns;
    m.regulator_clock_sim_ns=sim_;
    m.task_generation=d.task_generation;m.model_generation=d.model_generation;
    m.config_generation=d.config_generation;m.schedule_generation=d.schedule_generation;
    m.clock_epoch=d.clock_epoch;
    m.thrust_n[0]=d.final_n[0];m.thrust_n[1]=d.final_n[1];
    {std::lock_guard<std::mutex> l(mutex_);
     declared_={true,m.apply_begin_steady_ns,m.apply_end_steady_ns,{m.thrust_n[0],m.thrust_n[1]}};}
    if(candidate_){m.candidate_job_id=candidate_->job.job_id;m.candidate_worker_instance=candidate_->worker_instance;m.candidate_solve_end_ns=candidate_->solve_end_ns;}
    d.publish_start_ns[0]=p1::monotonic_ns();
    try{plant_pub_->publish(m);d.publish_success[0]=true;d.publish_success[1]=true;}catch(...){d.publish_success[0]=false;d.publish_success[1]=false;}
    d.publish_end_ns[0]=d.publish_end_ns[1]=p1::monotonic_ns();
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
    if(d.publish_end_ns[1]-d.publish_start_ns[0]>spec_.timing.publish_budget_ns){normal_complete_=false;worker_unusable_=true;}
    for(int i=0;i<2;++i)if(!old.known[i]||!d.publish_success[i])d.rho_available=false;
    for(int i=0;i<2;++i)if(old.known[i]&&d.publish_success[i]&&(d.publish_start_ns[i]-old.time[i]>spec_.timing.publish_gap_ns||std::abs(d.final_n[i]-old.n[i])>limits_.rho*(d.publish_start_ns[i]-old.time[i])/1e9+1e-9)){normal_complete_=false;worker_unusable_=true;d.rho_available=false;}
  }
  void tick_loop(){int64_t origin=p1::monotonic_ns()+1000000000,stop_start=0;uint64_t tick=1,last_schedule=0;
    while(true){auto planned=origin+static_cast<int64_t>(tick)*spec_.timing.T_ns;p1::sleep_until_monotonic(planned);
      if(tick_barrier_->take()){
        const auto start=p1::monotonic_ns();sink_->add({{"type","diagnostic_tick_barrier_enter"},{"expected_tick",tick},{"planned_ns",planned},{"start_ns",start},{"maximum_ms",tick_barrier_->milliseconds()},{"physical_output",false}});
        const auto until=start+tick_barrier_->milliseconds()*1000000;
        while(!stop_requested&&!prep_stop_&&p1::monotonic_ns()<until)p1::sleep_until_monotonic(std::min(until,p1::monotonic_ns()+20000000));
        sink_->add({{"type","diagnostic_tick_barrier_release"},{"expected_tick",tick},{"released_ns",p1::monotonic_ns()},{"cancelled",stop_requested.load()||prep_stop_.load()}});
      }
      auto now=p1::monotonic_ns();p1::Decision d;Snapshot s;std::optional<p1::Ticket> t;std::shared_ptr<const p1::Candidate> cand;
      {std::lock_guard<std::mutex> l(mutex_);if(last_schedule&&version_.schedule!=last_schedule){origin=now;tick=1;planned=origin;invalidate_locked();}last_schedule=version_.schedule;
        auto due=p1::due_tick(origin,now);d.skipped_ticks=due>tick?due-tick:0;if(due>tick){const auto old_tick=tick;const auto old_candidate=candidate_?candidate_->job.job_id:0;const auto old_target=candidate_?candidate_->job.target_tick:0;tick=due;planned=origin+static_cast<int64_t>(tick)*spec_.timing.T_ns;admission_.invalidate();candidate_.reset();normal_complete_=false;sink_->add({{"type","scheduler_skipped_ticks"},{"expected_tick",old_tick},{"due_tick",due},{"skipped_ticks",d.skipped_ticks},{"origin_ns",origin},{"observed_ns",now},{"planned_ns",planned},{"schedule_generation",version_.schedule},{"invalidated_candidate_job_id",old_candidate},{"invalidated_candidate_target_tick",old_target},{"candidate_after",false},{"admission_slots_after",admission_.slots()}});}
        current_tick_=tick;check_worker_locked(now);if(stop_requested||sink_->failed()){stopping_=true;if(!stop_start)stop_start=now;invalidate_locked();}
        if(clock_receive_&&last_clock_advance_&&now-last_clock_advance_>spec_.timing.clock_pause_confirm_ns&&!paused_){paused_=true;version_.schedule++;invalidate_locked();}
        if(worker_active_&&now-worker_active_since_>spec_.timing.active_watchdog_ns){unusable_locked("active_watchdog",now);sink_->add({{"type","active_watchdog"},{"active_job",worker_active_},{"observed_ns",now},{"policy","stop_submit; supervisor owns finite TERM/KILL"}});}
        s=snapshot_locked(now);t=admission_.take(tick,now);cand=candidate_;if(t)candidate_.reset();
        d.schema_version="p1-execution-decision-v2";d.run_id=run_;d.boot_id=boot_;d.contract_hash=hash_;d.worker_instance=worker_instance_;d.mode=mode_;d.sequence=++decision_seq_;d.tick=tick;d.task_generation=version_.task;d.model_generation=version_.model;d.config_generation=version_.config;d.schedule_generation=grid_.schedule_generation;d.clock_epoch=grid_.clock_epoch;d.tick_planned_ns=planned;d.tick_start_ns=now;d.cutoff_commit_ns=t?admission_.cutoff_ns():0;d.diagnostic_only=mode_!="execute";d.odom_age_ns=now-s.odom_receive;d.imu_age_ns=s.mixed?now-s.imu_receive:0;d.clock_age_ns=now-s.clock_receive;
      }
      auto reason=eligible(s,now);if(stopping_)reason="shutdown";if(worker_unusable_)reason="worker_unusable";
      if(now-planned>spec_.timing.tick_jitter_ns){reason="tick_jitter";normal_complete_=false;}
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
        if(reason.empty()){Eigen::Vector2d request(cand->first_control[0],cand->first_control[1]);auto mapped=usv_mpc::map_vrx(request,spec_.actuator.map_scale,limits_.low,limits_.high,spec_.actuator.publisher_max_n);d.requested_n=cand->first_control;d.final_n={mapped[0],mapped[1]};reason=p1::command_bounds(d.final_n,limits_);if(reason.empty()&&(mapped-request).norm()>1e-9)reason="candidate_mapping_changed";}
      }else if(reason.empty())reason="no_candidate";
      {std::lock_guard<std::mutex> l(mutex_);if(reason.empty()&&(!(s.version==version_)||s.odom_seq!=odom_seq_||s.imu_seq!=imu_seq_))reason="activation_input_changed_during_validation";
        if(reason.empty()&&t)reason=mode_=="controlled_sim"
          ?p1::receipt_chain_check(t->anchor,anchor_,publication_history_)
          :p1::publication_history_check(t->anchor,anchor_,publication_history_);
        check_worker_locked(p1::monotonic_ns());
        const int64_t commit_now=p1::monotonic_ns();
        if(reason.empty())reason=eligible(snapshot_locked(commit_now),commit_now);
        if(reason.empty()&&(worker_unusable_||!worker_valid_||sink_->failed()))reason="run_unusable_at_commit";
        if(reason.empty()&&commit_now-planned>spec_.timing.tick_jitter_ns){reason="tick_jitter_at_commit";normal_complete_=false;}
        if(reason.empty()&&cand&&std::abs(sim_+(commit_now-clock_receive_)-cand->job.target_sim_ns)>spec_.timing.target_sim_slack_ns)reason="target_sim_mismatch";
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
                                        limits_,spec_.timing.T_ns);}
        if(stopping_||stop_requested)reason="shutdown";
        d.candidate_accepted=reason.empty();d.reason=reason;d.activation_commit_ns=commit_now;d.activation_clock_sim_ns=sim_;d.activation_clock_receive_ns=clock_receive_;d.activation_rtf=rtf_;
        // Current source provenance at the actual final commit, not the job snapshot.
        d.activation_odom_stamp_ns=odom_stamp_;d.activation_odom_receive_ns=odom_receive_;d.activation_odom_sequence=odom_seq_;
        d.activation_r_from_imu=mixed_;d.activation_imu_stamp_ns=mixed_?imu_stamp_:0;
        d.activation_imu_receive_ns=mixed_?imu_receive_:0;d.activation_imu_sequence=mixed_?imu_seq_:0;
        d.odom_age_ns=commit_now-odom_receive_;d.imu_age_ns=mixed_?commit_now-imu_receive_:0;d.clock_age_ns=commit_now-clock_receive_;
        if(t&&cand&&mode_=="shadow")anchor_evidence_locked(*t,d);
        if(d.candidate_accepted){last_accepted_=d.activation_commit_ns;d.control_source="candidate";}else{d.final_n=p1::fallback(anchor_,d.activation_commit_ns,last_accepted_,limits_,stopping_||worker_unusable_||reason!="no_candidate");d.requested_n=d.final_n;d.control_source=last_accepted_>0&&!stopping_&&!worker_unusable_&&reason=="no_candidate"&&d.activation_commit_ns-last_accepted_<=limits_.hold_ns?"hold":"ramp_zero";}
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
      if(!sink_->add(p1::decision_to_json(d),d)){normal_complete_=false;stopping_=true;if(!stop_start)stop_start=now;}
      if(!stopping_&&!worker_unusable_&&worker_valid_&&!sink_->failed()){
        std::lock_guard<std::mutex> l(mutex_);const auto enqueue_now=p1::monotonic_ns();check_worker_locked(enqueue_now);auto next=snapshot_locked(enqueue_now);const std::string enqueue_gate=eligible(next,next.freeze,false);if(!enqueue_gate.empty())sink_->add({{"type","prepare_enqueue_blocked"},{"tick",tick},{"reason",enqueue_gate},{"processed_ns",enqueue_now}});
        if(!stopping_&&!worker_unusable_&&worker_valid_&&!sink_->failed()&&enqueue_gate.empty()){std::lock_guard<std::mutex> q(prep_mutex_);if(pending_)sink_->add({{"type","prepare_pending_replaced"},{"old_target_tick",pending_->tick+1},{"replacement_target_tick",tick+1}});pending_=Preparation{next,tick,planned};if(preparation_barrier_active_)sink_->add({{"type","diagnostic_preparation_pending_enqueued"},{"target_tick",tick+1},{"enqueued_ns",enqueue_now},{"pending_count",1}});prep_cv_.notify_one();}}
      if(stopping_){bool zero=std::abs(d.final_n[0])<1e-9&&std::abs(d.final_n[1])<1e-9;if(zero||now-stop_start>=spec_.timing.shutdown_grace_ns){sink_->add({{"type","regulator_shutdown"},{"zero_target_published",mode_=="execute"&&zero&&d.publish_success[0]&&d.publish_success[1]},{"shutdown_grace_exceeded",!zero},{"last_decision_sequence",d.sequence},{"normal_contract_complete",normal_complete_.load()&&!sink_->failed()},{"plant_hold_end_known",receipts_.known()&&receipts_.normal_complete()},{"finished_ns",p1::monotonic_ns()}});break;}}
      p1::sleep_until_monotonic(planned+spec_.timing.deadline_ns+1);{std::lock_guard<std::mutex> l(mutex_);admission_.cutoff(p1::monotonic_ns());}
      ++tick;
    }
    prep_stop_=true;prep_cv_.notify_all();finished_=true;
  }
  p1::ContractSpec spec_;p1::Limits limits_;bool faults_enabled_=false;std::string run_,hash_,mode_,boot_,legacy_run_,legacy_producer_,worker_instance_,path_fingerprint_,profile_fingerprint_,recording_observer_;int64_t expected_worker_pid_=0;
  std::unique_ptr<p1::WorkerLiveness> worker_liveness_;
  std::unique_ptr<p1::PreparationBarrier> preparation_barrier_;std::atomic<bool> preparation_barrier_active_{false};
  std::unique_ptr<p1::TickBarrier> tick_barrier_;int64_t test_skip_tick_=0;
  std::unique_ptr<p1::CapabilityLease> capability_lease_;
  std::mutex mutex_,prep_mutex_;std::condition_variable prep_cv_;std::optional<Preparation> pending_;std::thread prep_,tick_;std::atomic<bool> prep_stop_{false},finished_{false},stopping_{false},normal_complete_{true},worker_unusable_{false},worker_valid_{false};std::unique_ptr<Sink> sink_;
  model_reference::Registry registry_;model_reference::Grid grid_;model_reference::Options model_options_{};RunVersion version_;p1::Anchor anchor_;p1::Admission admission_;std::shared_ptr<const p1::Candidate> candidate_;std::deque<p1::Job> jobs_;std::deque<usv_mpc::HeldInputEvent> history_;std::deque<p1::PublicationEvent> publication_history_;uint64_t legacy_sequence_=0;std::shared_ptr<const usv_mpc::ReferenceInput> ref_;usv_mpc::Vector6d state_=usv_mpc::Vector6d::Zero();
  uint64_t current_tick_=0,job_id_=0,decision_seq_=0,odom_received_=0,imu_received_=0,odom_seq_=0,imu_seq_=0,path_seq_=0,profile_seq_=0,worker_active_=0;int64_t worker_active_since_=0,odom_stamp_=0,imu_stamp_=0,odom_receive_=0,imu_receive_=0,clock_receive_=0,sim_=0,last_clock_advance_=0,last_accepted_=0;bool mixed_=false;std::atomic<bool> paused_{false},rtf_valid_{false};double rtf_=0;p1::ClockWindow clock_window_;Declared declared_{};
  rclcpp::Publisher<p1::Job>::SharedPtr job_pub_;rclcpp::Publisher<usv_research_interfaces::msg::PlantCommand>::SharedPtr plant_pub_;uint64_t plant_sequence_=0;rclcpp::Subscription<usv_research_interfaces::msg::PlantReceipt>::SharedPtr receipt_sub_;rclcpp::Subscription<usv_research_interfaces::msg::PlantHoldClose>::SharedPtr hold_close_sub_;p1_receipt::ReceiptAnchor receipts_{};std::string plant_producer_;bool command_pending_=false;uint64_t pending_execution_before_=0;uint64_t pending_sequence_=0;rclcpp::Publisher<p1::Decision>::SharedPtr decision_pub_;rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr left_,right_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_;rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_;rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr path_;rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr profile_;rclcpp::Subscription<rosgraph_msgs::msg::Clock>::SharedPtr clock_;rclcpp::Subscription<p1::Candidate>::SharedPtr candidates_;rclcpp::Subscription<p1::Capability>::SharedPtr capabilities_;rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr stop_;rclcpp::Subscription<usv_research_interfaces::msg::AppliedControl>::SharedPtr applied_;
};
int main(int argc,char **argv){rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,stop_signal);std::signal(SIGTERM,stop_signal);
try{auto node=std::make_shared<Regulator>();rclcpp::executors::SingleThreadedExecutor exec;exec.add_node(node);while(!node->finished()&&rclcpp::ok()){exec.spin_some(std::chrono::milliseconds(10));std::this_thread::sleep_for(std::chrono::milliseconds(1));}exec.remove_node(node);bool closed=node->close_source();node.reset();rclcpp::shutdown();return closed?0:2;}catch(const std::exception & e){fprintf(stderr,"regulator fatal: %s\n",e.what());rclcpp::shutdown();return 1;}}
