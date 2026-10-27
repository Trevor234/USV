#include "c38_diagnostic_gate.hpp"
#include "task_time_profile_v1.hpp"
#include "task_time_entry_contract_v1.hpp"
#include "../../../phase_protocol.hpp"
#include <std_msgs/msg/string.hpp>
// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include <atomic>
#include <condition_variable>
#include <csignal>
#include <deque>
#include <map>
#include <mutex>
#include <optional>
#include <thread>
#if defined(P1_C33_MATRIX_TEST) || defined(P1_C36_COMPLETION_TEST)
#include <functional>
#endif
#include <rclcpp/rclcpp.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <nav_msgs/msg/path.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <std_msgs/msg/float64.hpp>
#include <std_msgs/msg/bool.hpp>
#include <rosgraph_msgs/msg/clock.hpp>
#include "usv_research_interfaces/msg/applied_control.hpp"
#include "usv_mpc_cpp/p1_input_core.hpp"
#include "protocol.hpp"
#include "p1_admission.hpp"
#include "publication_result_v1.hpp"
#include "activation_sensor_history_v1.hpp"
#include "activation_interleave_v1.hpp"
#include "p1_clock_window.hpp"
#include "p1_worker_liveness.hpp"
#include "p1_preparation_barrier.hpp"
#include "p1_capability_lease.hpp"
#include "p1_tick_barrier.hpp"
#include "p1_diag_sink.hpp"
#include "p1_d0_observation.hpp"
#include "p1_shadow_entry.hpp"
#include "projected_profile_time_v1.hpp"
#include "p1_owned_identity.hpp"
#include "callback_raw_v4.hpp"
#include "c36_runtime_adapter.hpp"
#include "owned_peer_c36_v1.hpp"
#include "owned_worker_peer_c37_v1.hpp"
#ifndef P1_OWNED_SOURCE_BUNDLE_SHA256
#error "owned observer requires source bundle identity"
#endif
#include <openssl/evp.h>
namespace {std::atomic<bool> stop_requested{false};void stop_signal(int){stop_requested=true;}}
// Derived startup-handshake shadow observation entry. D0, B0 and parent entry remain
// independently identified; this executable cannot create a physical publisher.
using Sink=p1::DiagSink<p1::Decision,rclcpp::Publisher<p1::Decision>::SharedPtr>;
static std::string file_sha(const std::string &path){
  std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("identity file unavailable");
  EVP_MD_CTX *ctx=EVP_MD_CTX_new();if(!ctx)throw std::runtime_error("digest allocation");
  unsigned char hash[EVP_MAX_MD_SIZE];unsigned length=0;char buffer[16384];
  bool ok=EVP_DigestInit_ex(ctx,EVP_sha256(),nullptr)==1;
  while(f&&ok){f.read(buffer,sizeof(buffer));if(f.gcount())ok=EVP_DigestUpdate(ctx,buffer,f.gcount())==1;}
  ok=ok&&f.eof()&&EVP_DigestFinal_ex(ctx,hash,&length)==1;EVP_MD_CTX_free(ctx);
  if(!ok||length!=32)throw std::runtime_error("identity digest failed");
  static const char hex[]="0123456789abcdef";std::string result(64,'0');
  for(unsigned i=0;i<32;++i){result[2*i]=hex[hash[i]>>4];result[2*i+1]=hex[hash[i]&15];}return result;
}
class Regulator final:public rclcpp::Node {
 public:
  explicit Regulator(const rclcpp::NodeOptions &options=rclcpp::NodeOptions()):Node("p1_regulator",options) {
    run_=declare_parameter<std::string>("run_id","");hash_=declare_parameter<std::string>("contract_hash","");mode_=declare_parameter<std::string>("mode","");
    p1::shadow::require_shadow_mode(mode_);
    c_=p1::load_contract(declare_parameter<std::string>("contract_file",""),hash_);p1::require_runtime_contract_mode(c_,mode_);resources_=p1::resource_limits_from_contract(c_);
    p1::shadow::validate_task_time_entry(c_,mode_);
    p1_owned::require(c_.at("activation_state_policy")==activation_alignment::policy&&c_.at("activation_sensor_history_capacity")==activation_alignment::capacity&&c_.at("activation_validation_attempts")==activation_alignment::attempts,"compiled activation policy/limits differ from authenticated contract");
    boot_=p1::boot_id();nominal_=c_.at("nominal_hash");
    legacy_run_=declare_parameter<std::string>("legacy_run_id","");expected_worker_pid_=declare_parameter<int64_t>("worker_pid",0);
    const bool audit=declare_parameter<bool>("witness_enabled",false);
    witness_file_=declare_parameter<std::string>("witness_file","");
    const auto source_file=declare_parameter<std::string>("source_file","");
    const auto source_path=declare_parameter<std::string>("diagnostic_source_file","");
    const auto expected_source=declare_parameter<std::string>("diagnostic_source_sha256","");
    const auto expected_binary=declare_parameter<std::string>("diagnostic_binary_sha256","");
    const auto expected_worker=declare_parameter<std::string>("worker_binary_sha256","");
    const auto instance=declare_parameter<std::string>("witness_worker_instance","");
    expected_legacy_identity_={declare_parameter<std::string>("legacy_schema_version",""),legacy_run_,
      declare_parameter<std::string>("legacy_producer_instance_id",""),c_.at("baseline_input").get<std::string>(),
      declare_parameter<std::string>("legacy_config_hash",""),declare_parameter<std::string>("legacy_clock_domain","")};
    const std::array<int64_t,5> hooks={declare_parameter<int64_t>("test_delay_ms",0),declare_parameter<int64_t>("test_native_block_ms",0),
      declare_parameter<int64_t>("test_prepare_block_ms",0),declare_parameter<int64_t>("test_tick_block_ms",0),declare_parameter<int64_t>("test_sink_pause_ms",0)};
    v1_policy_=declare_parameter<std::string>("diagnostic_v1_sink_policy","none");
    v1_fault_file_=declare_parameter<std::string>("diagnostic_v1_fault_file","");
    if(v1_policy_!="none"&&v1_policy_!="decision_queue_saturation_after_authenticated_phase_v2")throw std::runtime_error("unknown V1 sink policy");
    v1_enabled_=v1_policy_!="none";
    if(v1_enabled_){
      p1_owned::require(mode_=="shadow"&&audit&&c_.at("fault_injection_enabled").get<bool>(),"V1 requires explicit witnessed diagnostic shadow");
      const std::filesystem::path path(v1_fault_file_);
      p1_owned::require(path.is_absolute()&&std::filesystem::is_directory(path.parent_path())&&!std::filesystem::exists(path)&&!std::filesystem::is_symlink(std::filesystem::symlink_status(path)),"V1 fault evidence must be a fresh absolute path");
    }else p1_owned::require(v1_fault_file_.empty(),"disabled V1 cannot have evidence output");
    v3_policy_=declare_parameter<std::string>("diagnostic_v3_input_policy","none");
    const auto v3_budget=declare_parameter<int64_t>("diagnostic_v3_wait_ns",0);
    activation_interleave::validate(v3_policy_,v3_budget,mode_,audit,c_.at("fault_injection_enabled").get<bool>(),v1_enabled_);
    p1::shadow::EntryPolicy policy{mode_,run_,boot_,source_file,witness_file_,source_path,expected_source,expected_binary,expected_worker,instance,
      expected_worker_pid_,audit,hooks,expected_legacy_identity_};
    policy.validate(); // All application publisher/sink creation is below this gate.
    p1::DiagPausePolicy pause{0};
    pause.validate(mode_,true,c_.at("fault_injection_enabled").get<bool>(),audit);
    if(!audit&&!witness_file_.empty())throw std::runtime_error("disabled witness cannot have output path");
    p1::WitnessHeader h{};
    if(audit){
      if(witness_file_.empty())throw std::runtime_error("witness output path required");
      const auto source=file_sha(source_path),binary=file_sha("/proc/self/exe");
      if(expected_worker_pid_<=0)throw std::runtime_error("worker identity PID required");
      const auto worker=file_sha("/proc/"+std::to_string(expected_worker_pid_)+"/exe");
      if(source!=expected_source||binary!=expected_binary||worker!=expected_worker)throw std::runtime_error("witness identity digest mismatch");
      if(!(p1::witness_text(h.run_id,run_)&&p1::witness_text(h.boot_id,boot_)&&p1::witness_text(h.contract_sha256,hash_)&&
           p1::witness_text(h.source_sha256,source)&&p1::witness_text(h.binary_sha256,binary)&&p1::witness_text(h.worker_binary_sha256,worker)&&p1::witness_text(h.worker_instance,instance)))
        throw std::runtime_error("bounded witness identity invalid");
    }
    witness_=std::make_unique<p1::Witness>(audit,h);
    if(audit&&witness_->summary().incomplete)throw std::runtime_error("witness header invalid");
    pause_policy_=pause;
    worker_liveness_=std::make_unique<p1::WorkerLiveness>(expected_worker_pid_);
    recording_observer_=declare_parameter<std::string>("recording_observer_node","p1_calibration_driver");
    if(recording_observer_.empty()||recording_observer_.size()>128)throw std::runtime_error("invalid bounded recording observer node");
    if(run_.empty()||run_.size()>128||(mode_!="shadow"&&mode_!="execute"&&mode_!="no_output"))throw std::runtime_error("identity/mode invalid");
    preparation_barrier_=std::make_unique<p1::PreparationBarrier>(0,mode_,c_.at("fault_injection_enabled").get<bool>());
    tick_barrier_=std::make_unique<p1::TickBarrier>(0,mode_,c_.at("fault_injection_enabled").get<bool>());
    capability_lease_=std::make_unique<p1::CapabilityLease>(c_.at("worker_capability_receipt_timeout_ns").get<int64_t>());
    limits_.tolerance=c_.at("activation_tolerance").get<p1::State>();limits_.rho=c_.at("rho_n_s");limits_.hold_ns=c_.at("hold_ns");limits_.low=c_.at("command_min_n");limits_.high=c_.at("command_max_n");if(!limits_.valid())throw std::runtime_error("invalid finite limits");
    const std::array<std::string,21> positive={"odom_age_ns","imu_age_ns","mixed_skew_ns","clock_age_ns","clock_pause_confirm_ns","target_sim_slack_ns","tick_jitter_ns","publish_gap_ns","publish_budget_ns","active_watchdog_ns","worker_grace_ns","term_grace_ns","kill_postcheck_ns","shutdown_grace_ns","max_path_points","history_capacity","log_capacity","odom_sim_lag_ns","imu_sim_lag_ns","source_future_slack_ns","recording_ready_timeout_ns"};for(auto & k:positive)if(c_.at(k).get<int64_t>()<=0)throw std::runtime_error("missing/invalid bound: "+k);if(c_.at("recording_ready_timeout_ns").get<int64_t>()>60000000000LL)throw std::runtime_error("invalid finite recording timeout");
    for(const auto & key:{"expected_pose_frame","expected_child_frame","expected_imu_frame"}){const auto frame=c_.at(key).get<std::string>();if(frame.empty()||frame.size()>128)throw std::runtime_error("invalid bounded expected frame");}
    const auto ready_timeout_ms=declare_parameter<int64_t>("legacy_ready_timeout_ms",0);
    if(ready_timeout_ms<=0||ready_timeout_ms>60000)throw std::runtime_error("legacy_ready_timeout_ms must be explicitly within [1,60000]");
    legacy_ready_timeout_ns_=ready_timeout_ms*1000000;legacy_readiness_enabled_=true;
    const auto peer_file=declare_parameter<std::string>("adapter_peer_pins_file","");
    const auto peer_sha=declare_parameter<std::string>("adapter_peer_pins_sha256","");
    const auto peer_raw=c36_owned::detail::read_manifest(peer_file);
    p1_owned::require(p1_owned::sha256_shape(peer_sha)&&p1_owned::sha256_bytes(peer_raw)==peer_sha,"adapter peer pins SHA");
    adapter_pins_=c36_owned::detail::strict_json(peer_raw);
    auto peer_pins=c36_owned::from_json(adapter_pins_.at("publisher_peer"));
    p1_owned::require(peer_pins.run_id==legacy_run_&&peer_pins.boot_id==boot_&&peer_pins.contract_sha256==hash_&&peer_pins.producer_instance_id==expected_legacy_identity_.producer&&peer_pins.config_hash==expected_legacy_identity_.config,"adapter peer/payload identity differs");
    owner_peer_=std::make_unique<c36_owned::OwnedPeer>(peer_pins);
    controlled_phase_enabled_=declare_parameter<bool>("controlled_phase_enabled",false);
    p1_owned::require(controlled_phase_enabled_,"controlled diagnostic phase must be explicitly true");
    auto phase_pins=peer_pins;phase_pins.topic="/p1/controlled_owner_phase";phase_pins.type="std_msgs/msg/String";
    controlled_owner_phase_peer_=std::make_unique<c36_owned::OwnedPeer>(phase_pins);
    controlled_owner_identity_={legacy_run_,boot_,hash_,peer_pins.producer_instance_id,controlled_phase::baseline};
    auto binding=[](const c36_owned::PeerPins &pins,const c36_owned::OwnedPeer &peer){
      controlled_phase::PeerBinding b;b.gid=peer.expected_gid().get<controlled_phase::Gid>();b.pid=pins.pid;b.process_start_ticks=pins.process_start_ticks;
      b.manifest_sha256=pins.manifest_sha256;b.binary_sha256=pins.binary_sha256;b.run_id=pins.run_id;b.boot_id=pins.boot_id;b.contract_sha256=pins.contract_sha256;return b;
    };
    controlled_applied_binding_=binding(peer_pins,*owner_peer_);controlled_phase_binding_=binding(phase_pins,*controlled_owner_phase_peer_);
    controlled_phase_state_=std::make_unique<controlled_phase::ObserverPhase>(controlled_owner_identity_,controlled_applied_binding_,controlled_phase_binding_);
    auto worker_pins=c37_owned::from_json(adapter_pins_.at("worker_peer"));
    p1_owned::require(worker_pins.run_id==run_&&worker_pins.boot_id==boot_&&worker_pins.contract_sha256==hash_&&worker_pins.nominal_hash==nominal_&&worker_pins.worker_instance==instance&&worker_pins.pid==expected_worker_pid_&&worker_pins.binary_sha256==expected_worker&&worker_pins.capability_topic=="/p1/worker_capability"&&worker_pins.candidate_topic=="/p1/solve_candidate","worker peer/payload identity differs");
    worker_peer_=std::make_unique<c37_owned::OwnedWorkerPeer>(worker_pins);
    adapter_=std::make_unique<c36_runtime::Adapter>(c36::Owner{peer_pins.run_id,boot_,peer_pins.producer_instance_id,peer_pins.config_hash,0},run_,hash_,nominal_);
    adapter_close_file_=declare_parameter<std::string>("adapter_driver_close_file","");
    p1_owned::require(!adapter_close_file_.empty(),"adapter close path required");
    diagnostic_c38_mode_=declare_parameter<std::string>("diagnostic_c38_mode","none");
    diagnostic_c38_pause_file_=declare_parameter<std::string>("diagnostic_c38_pause_file","");
    diagnostic_c38_resume_file_=declare_parameter<std::string>("diagnostic_c38_resume_file","");
    c38::validate_mode_paths(diagnostic_c38_mode_,diagnostic_c38_pause_file_,diagnostic_c38_resume_file_);
    if(diagnostic_c38_mode_=="applied-gate"||diagnostic_c38_mode_=="worker-gate"){
      c38_gate_=std::make_unique<c38::DiagnosticGate>(c38::Identity{run_,boot_,adapter_pins_.at("driver").at("pid").get<int64_t>(),adapter_pins_.at("driver").at("start_ticks").get<uint64_t>(),adapter_pins_.at("driver_tool_sha256").get<std::string>(),peer_pins.manifest_sha256});
      c38_gate_interface_=diagnostic_c38_mode_=="worker-gate"?"worker":"applied";
      c38_diagnostic_group_=create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive,false);
    }
    params_=p1::solver_params(c_);ref_=std::make_shared<const usv_mpc::ReferenceInput>();
    job_pub_=create_publisher<p1::Job>("/p1/solve_job",rclcpp::QoS(1).reliable());decision_pub_=create_publisher<p1::Decision>("/p1/execution_decision",rclcpp::QoS(1).reliable());
    sink_=std::make_unique<Sink>(source_file,c_.at("log_capacity"),decision_pub_,witness_.get(),pause_policy_,v1_enabled_);
    odom_=create_subscription<nav_msgs::msg::Odometry>(c_.at("input_topics").at("odom").get<std::string>(),rclcpp::SensorDataQoS(),[this](nav_msgs::msg::Odometry::SharedPtr m,const rclcpp::MessageInfo &info){const auto topic=c_.at("input_topics").at("odom").get<std::string>();auto raw=p1_observation_v4::raw_input(*m,info,topic,"nav_msgs/msg/Odometry",++raw_callback_sequences_[topic]);odom(*m,&raw);});
    imu_=create_subscription<sensor_msgs::msg::Imu>(c_.at("input_topics").at("imu").get<std::string>(),rclcpp::SensorDataQoS(),[this](sensor_msgs::msg::Imu::SharedPtr m,const rclcpp::MessageInfo &info){const auto topic=c_.at("input_topics").at("imu").get<std::string>();auto raw=p1_observation_v4::raw_input(*m,info,topic,"sensor_msgs/msg/Imu",++raw_callback_sequences_[topic]);imu(*m,&raw);});
    path_=create_subscription<nav_msgs::msg::Path>(c_.at("input_topics").at("path").get<std::string>(),rclcpp::QoS(1).reliable(),[this](nav_msgs::msg::Path::SharedPtr m,const rclcpp::MessageInfo &info){const auto topic=c_.at("input_topics").at("path").get<std::string>();auto raw=p1_observation_v4::raw_input(*m,info,topic,"nav_msgs/msg/Path",++raw_callback_sequences_[topic]);path(*m,&raw);});
    profile_=create_subscription<std_msgs::msg::Float64MultiArray>(c_.at("input_topics").at("profile").get<std::string>(),rclcpp::QoS(1).reliable(),[this](std_msgs::msg::Float64MultiArray::SharedPtr m,const rclcpp::MessageInfo &info){const auto topic=c_.at("input_topics").at("profile").get<std::string>();auto raw=p1_observation_v4::raw_input(*m,info,topic,"std_msgs/msg/Float64MultiArray",++raw_callback_sequences_[topic]);profile(*m,&raw);});
    clock_=create_subscription<rosgraph_msgs::msg::Clock>("/clock",rclcpp::ClockQoS(),[this](rosgraph_msgs::msg::Clock::SharedPtr m,const rclcpp::MessageInfo &info){const auto topic=std::string("/clock");auto raw=p1_observation_v4::raw_input(*m,info,topic,"rosgraph_msgs/msg/Clock",++raw_callback_sequences_[topic]);clock(*m,&raw);});
    // This diagnostic changes executor scheduling only. DataReaders stay alive,
    // and every resumed receipt still traverses the original resource/GID/pidfd guard.
    rclcpp::SubscriptionOptions worker_options;if(c38_gate_interface_=="worker")worker_options.callback_group=c38_diagnostic_group_;
    candidates_=create_subscription<p1::Candidate>("/p1/solve_candidate",rclcpp::QoS(1).reliable(),[this](p1::Candidate::SharedPtr m,const rclcpp::MessageInfo &info){receive_worker(*m,info,c37_owned::Interface::Candidate);},worker_options);
    capabilities_=create_subscription<p1::Capability>("/p1/worker_capability",rclcpp::QoS(1).reliable().transient_local(),[this](p1::Capability::SharedPtr m,const rclcpp::MessageInfo &info){receive_worker(*m,info,c37_owned::Interface::Capability);},worker_options);
    stop_=create_subscription<std_msgs::msg::Bool>("/p1/stop",rclcpp::QoS(1).reliable(),[](std_msgs::msg::Bool::SharedPtr m){if(m->data)stop_requested=true;});
    rclcpp::SubscriptionOptions applied_options;if(c38_gate_interface_=="applied")applied_options.callback_group=c38_diagnostic_group_;
    applied_=create_subscription<usv_research_interfaces::msg::AppliedControl>("/research/control/applied",rclcpp::QoS(10).reliable(),[this](usv_research_interfaces::msg::AppliedControl::SharedPtr m,const rclcpp::MessageInfo& info){
      receive_applied(*m,info);
    },applied_options);
    controlled_phase_subscription_=create_subscription<std_msgs::msg::String>("/p1/controlled_owner_phase",rclcpp::QoS(10).reliable(),[this](std_msgs::msg::String::SharedPtr m,const rclcpp::MessageInfo &info){receive_controlled_phase(*m,info);});
    adapter_close_timer_=create_wall_timer(std::chrono::milliseconds(20),[this]{poll_adapter_close();});
    const auto owned_file=declare_parameter<std::string>("owned_manifest_file","");
    parameters_frozen_=p1_owned::freeze_parameters(*this);
    const auto endpoints=p1_owned::Json::array({
      p1_owned::publisher_endpoint(*job_pub_,"usv_research_interfaces/msg/SolveJob"),
      p1_owned::publisher_endpoint(*decision_pub_,"usv_research_interfaces/msg/ExecutionDecision"),
      p1_owned::subscription_endpoint(*odom_,"nav_msgs/msg/Odometry"),
      p1_owned::subscription_endpoint(*imu_,"sensor_msgs/msg/Imu"),
      p1_owned::subscription_endpoint(*path_,"nav_msgs/msg/Path"),
      p1_owned::subscription_endpoint(*profile_,"std_msgs/msg/Float64MultiArray"),
      p1_owned::subscription_endpoint(*clock_,"rosgraph_msgs/msg/Clock"),
      p1_owned::subscription_endpoint(*candidates_,"usv_research_interfaces/msg/SolveCandidate"),
      p1_owned::subscription_endpoint(*capabilities_,"usv_research_interfaces/msg/WorkerCapability"),
      p1_owned::subscription_endpoint(*stop_,"std_msgs/msg/Bool"),
      p1_owned::subscription_endpoint(*applied_,"usv_research_interfaces/msg/AppliedControl"),
      p1_owned::subscription_endpoint(*controlled_phase_subscription_,"std_msgs/msg/String")});
    p1_owned::write_create_only(owned_file,p1_owned::role_manifest(*this,"observer",run_,hash_,P1_OWNED_SOURCE_BUNDLE_SHA256,endpoints,
      {{"source_fd",p1_owned::source_fd_identity(source_file)},{"contract_configuration",c_},{"diagnostic_v1_sink_policy",v1_policy_},{"diagnostic_v1_fault_file",v1_fault_file_},{"diagnostic_v3_input_policy",v3_policy_},{"diagnostic_v3_wait_ns",v3_budget},
       {"worker_instance",instance},{"runtime_hook_values",hooks},{"expected_legacy_identity",expected_legacy_identity_.json()},
       {"physical_publisher_endpoints",0},{"adapter_peer_binding",owner_peer_->evidence()},{"worker_peer_binding",worker_peer_->evidence()},{"adapter_pins_sha256",peer_sha},{"controlled_phase_peer_binding",controlled_owner_phase_peer_->evidence()},{"controlled_phase_enabled",true},{"controlled_phase_baseline",controlled_phase::baseline}}));
    wait_recording_ready();
    p1_owned::write_create_only(owned_file+".reader_ready.json",{{"schema","p1-owned-native-reader-ready-v1"},{"role","observer"},{"run_id",run_},{"contract_sha256",hash_},{"boot_id",boot_},{"pid",getpid()},{"process_start_ticks",p1_owned::process_start_ticks()},{"owned_manifest_sha256",p1_owned::file_sha256(owned_file)},{"checked_steady_ns",p1_owned::steady_ns()},{"applied_matched_publishers",applied_->get_publisher_count()},{"applied_endpoint",p1_owned::subscription_endpoint(*applied_,"usv_research_interfaces/msg/AppliedControl")},{"fixture_only",true},{"execute_qualified",false}});
    legacy_prepare_start_ns_=p1::monotonic_ns();legacy_prepare_deadline_ns_=legacy_prepare_start_ns_+legacy_ready_timeout_ns_;
    prep_=std::thread([this]{prepare_loop();});tick_=std::thread([this]{tick_loop();});
    sink_->add({{"type","startup"},{"schema","p1-regulator-v1"},{"run_id",run_},{"mode",mode_},{"pid",getpid()},{"boot",boot_},{"clock","CLOCK_MONOTONIC"},{"contract_hash",hash_},{"physical_publisher_endpoints",0},{"worker_liveness_policy","linux_pidfd_no_wait"},{"publication_history_policy","full_consecutive_publisher_history"},{"input_anchor_source","legacy_publisher"},{"diagnostic_only",true},{"entry_policy",p1::shadow::entry_policy},{"fault_hook_values",hooks},{"fault_capability_flag",c_.at("fault_injection_enabled")},{"legacy_expected_identity",expected_legacy_identity_.json()},{"external_worker_zero_hook_argv_verified",false},{"reference_sampling_policy",c_.at("reference_sampling_policy")},{"readiness_policy","p1-D1-legacy-ready-v1"},{"legacy_ready_timeout_ns",legacy_ready_timeout_ns_},{"legacy_prepare_start_ns",legacy_prepare_start_ns_},{"legacy_prepare_deadline_ns",legacy_prepare_deadline_ns_}});
  }
  ~Regulator(){stop_requested=true;prep_stop_=true;prep_cv_.notify_all();if(tick_.joinable())tick_.join();if(prep_.joinable())prep_.join();sink_->close();}
  bool finished()const{return finished_;}
  bool audit_closed()const{return audit_closed_;}
  void register_diagnostic_group(rclcpp::Executor &exec){if(c38_diagnostic_group_){exec.add_callback_group(c38_diagnostic_group_,get_node_base_interface());c38_group_registered_=true;}}
  void remove_diagnostic_group(rclcpp::Executor &exec){if(c38_diagnostic_group_&&c38_group_registered_){exec.remove_callback_group(c38_diagnostic_group_);c38_group_registered_=false;}}
  void poll_diagnostic_gate(rclcpp::Executor &exec){
    if(!c38_gate_)return;
    auto emit=[&](const char* type,const c38::Command* command=nullptr,const std::string &reason=""){
      std::lock_guard<std::mutex> lock(mutex_);
      p1::Json event={{"type",type},{"checked_ns",p1::monotonic_ns()},{"gate",c38_gate_->evidence()},{"gate_interface",c38_gate_interface_},{"group_registered",c38_group_registered_},{"legacy_received",legacy_received_},{"raw_callback_sequence",raw_callback_sequences_["/research/control/applied"]},{"capability_received",worker_capability_received_},{"candidate_received",worker_candidate_received_},{"capability_callback_sequence",raw_callback_sequences_["/p1/worker_capability"]},{"candidate_callback_sequence",raw_callback_sequences_["/p1/solve_candidate"]},{"business",worker_callback_snapshot_locked()},{"anchor",anchor_.n},{"reason",reason},{"diagnostic_only",true},{"stage_qualified",false}};
      if(command){event["request_sha256"]=command->sha256;event["issued_ns"]=command->issued_ns;event["seq"]=command->seq;}
      sink_->add(std::move(event));
    };
    try{
      auto now=p1::monotonic_ns();
      if(c38_gate_->expired(now)){
        if(!c38_group_registered_){exec.add_callback_group(c38_diagnostic_group_,get_node_base_interface());c38_group_registered_=true;}
        c38_gate_->timeout_applied(p1::monotonic_ns());emit("diagnostic_c38_gate_timeout");return;
      }
      if(!c38_pause_attempted_&&std::filesystem::exists(diagnostic_c38_pause_file_)){
        c38_pause_attempted_=true;auto command=c38_gate_->validate_pause(c36_owned::detail::read_manifest(diagnostic_c38_pause_file_),now);
        exec.remove_callback_group(c38_diagnostic_group_);c38_group_registered_=false;c38_gate_->pause_applied(p1::monotonic_ns());emit("diagnostic_c38_gate_paused",&command);
      }
      now=p1::monotonic_ns();
      if(c38_gate_->state()==c38::State::paused&&!c38_resume_attempted_&&std::filesystem::exists(diagnostic_c38_resume_file_)){
        c38_resume_attempted_=true;auto command=c38_gate_->validate_resume(c36_owned::detail::read_manifest(diagnostic_c38_resume_file_),now);
        exec.add_callback_group(c38_diagnostic_group_,get_node_base_interface());c38_group_registered_=true;c38_gate_->resume_applied(p1::monotonic_ns());emit("diagnostic_c38_gate_resumed",&command);
      }
    }catch(const std::exception &e){
      const auto state=c38_gate_->state();
      if(state==c38::State::pause_validated&&!c38_group_registered_){exec.add_callback_group(c38_diagnostic_group_,get_node_base_interface());c38_group_registered_=true;}
      c38_gate_->abandon_validation();emit("diagnostic_c38_gate_rejected",nullptr,e.what());
    }
  }
  void mark_executor_detached(){executor_detached_=true;}
  bool close_source(){if(tick_.joinable())tick_.join();prep_stop_=true;prep_cv_.notify_all();if(prep_.joinable())prep_.join();
    {std::lock_guard<std::mutex> lock(mutex_);if(adapter_){auto r=adapter_->close_after_join(p1::monotonic_ns());sink_->add({{"type","adapter_closed_after_join"},{"reason",r.reason},{"evidence",adapter_->evidence()},{"owner_process_alive",owner_peer_->alive()},{"owner_endpoints_exited","unknown"}});}
      sink_->add({{"type","adapter_applied_reception_closed"},{"closed_ns",p1::monotonic_ns()},{"executor_detached",executor_detached_},{"legacy_received",legacy_received_},{"legacy_admitted",legacy_admitted_},{"raw_callback_sequence",raw_callback_sequences_["/research/control/applied"]}});
      sink_->add({{"type","controlled_phase_reception_closed"},{"closed_ns",p1::monotonic_ns()},{"executor_detached",executor_detached_},{"received",raw_callback_sequences_["/p1/controlled_owner_phase"]},{"raw_callback_sequence",raw_callback_sequences_["/p1/controlled_owner_phase"]},{"phase_expired",controlled_phase_state_->expired_phases()},{"phase_still_awaiting",controlled_phase_state_->awaiting()},{"all_DDS_publications_received",nullptr},{"owner_endpoints_exited","unknown"}});
      if(worker_peer_)sink_->add({{"type","adapter_worker_reception_closed"},{"schema","p1-C3.7-worker-reception-close-v1"},{"closed_ns",p1::monotonic_ns()},{"executor_detached",executor_detached_},{"tick_joined",!tick_.joinable()},{"prep_joined",!prep_.joinable()},{"capability_received",worker_capability_received_},{"candidate_received",worker_candidate_received_},{"capability_callback_sequence",raw_callback_sequences_["/p1/worker_capability"]},{"candidate_callback_sequence",raw_callback_sequences_["/p1/solve_candidate"]},{"business",worker_callback_snapshot_locked()},{"worker_process_alive",worker_peer_->alive()},{"all_Worker_publications_received",nullptr},{"worker_endpoints_exited","unknown"}});}
    sink_->close();
    {std::lock_guard<std::mutex> l(mutex_);phase_locked(p1::WitnessPhaseKind::Close,p1::WitnessObservation::Close,p1::monotonic_ns());}
    if(witness_->enabled()&&!audit_identity_ok_)witness_->mark_header_invalid();
    witness_->close_after_join();const bool audit_written=!witness_->enabled()||witness_->write_terminal(witness_file_.c_str());
    audit_closed_=audit_written&&(!witness_->enabled()||witness_->summary().observation_complete);
    fprintf(stdout,"REGULATOR_CLOSE_FLUSH_SUCCESS=%s\n",sink_->failed()?"false":"true");
    fprintf(stdout,"WITNESS_OBSERVATION_COMPLETE=%s\n",audit_closed_&&witness_->summary().observation_complete?"true":"false");
    fprintf(stdout,"WITNESS_BUSINESS_READY_OBSERVED=%s\n",witness_->summary().business_ready_observed?"true":"false");return !sink_->failed();}
 private:
#ifdef P1_C37_WORKER_CALLBACK_TEST
  friend class C37WorkerCallbackAccess;
#endif
#ifdef P1_C34_LEASE_COMPONENT
  // Only source-linked finite native/wire evidence producer; no runtime hook.
  friend class C34LeaseAccess;
#endif
#ifdef P1_C36_APPLIED_BOUNDARY_TEST
  // Source-including tests exercise the actual resource branch and queued-tail
  // predicate. The owned runtime has no test constructor or callback hook.
  friend class C36AppliedBoundaryAccess;
#endif
  rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr parameters_frozen_;
#ifdef P1_C36_COMPLETION_TEST
  friend class C36CompletionAccess;
  std::function<void()> c36_before_ready_completion_;
#endif
#ifdef P1_C33_MATRIX_TEST
  // Source-including bounded GTest only. No hook, friend, or callable is compiled
  // into the owned runtime executable. Hooks establish an explicitly seeded
  // finite fixture or release a callback thread at original tick phase edges;
  // the tested gates and fallback remain the actual code below.
  friend class C33MatrixAccess;
  std::function<void(uint64_t,int64_t)> c33_before_snapshot_;
  std::function<void(uint64_t)> c33_before_commit_;
  std::function<void(uint64_t)> c33_after_tick_;
#endif
#ifdef P1_ENQUEUE_BRANCH_TEST
  // Compiled only into the linked test executable, never into a runtime binary.
  friend class EnqueueBranchAccess;
  struct EnqueueTestTag {};
  Regulator(EnqueueTestTag,const std::string &path,size_t capacity):Node("p1_enqueue_branch_test",rclcpp::NodeOptions().enable_rosout(false).start_parameter_services(false).start_parameter_event_publisher(false)){
    mode_="no_output";c_={{"shutdown_grace_ns",1000000000LL}};
    decision_pub_=create_publisher<p1::Decision>("/p1_test/decision",rclcpp::QoS(1).reliable());
    p1::WitnessHeader h{};p1::witness_text(h.run_id,"enqueue-branch-linked-test");p1::witness_text(h.boot_id,p1::boot_id());
    p1::witness_text(h.contract_sha256,std::string(64,'a'));p1::witness_text(h.source_sha256,std::string(64,'b'));p1::witness_text(h.binary_sha256,std::string(64,'c'));
    p1::witness_text(h.worker_binary_sha256,std::string(64,'d'));p1::witness_text(h.worker_instance,std::string(64,'e'));
    witness_=std::make_unique<p1::Witness>(true,h);
    sink_=std::make_unique<Sink>(path,capacity,decision_pub_,witness_.get(),p1::DiagPausePolicy{5000});
  }
#endif
#ifdef P1_LEGACY_READY_TEST
  // Additional seam only in the source-including test target. All callback,
  // history, capability, readiness and invalidation code is the runtime code.
  friend class LegacyReadyAccess;
  struct LegacyReadyTestTag {};
  Regulator(LegacyReadyTestTag,const std::string &path,const p1::shadow::LegacyIdentity &legacy):Regulator(ShadowTestTag{},path,legacy){
    ref_=std::make_shared<const usv_mpc::ReferenceInput>();resources_=p1::resource_limits_from_contract(c_);
    hash_="0e3eb70e74e922059ff17014ab1971b8a9fe20be0171964fc26410b7d769a933";nominal_=c_.at("nominal_hash");expected_worker_pid_=getpid();
    worker_liveness_=std::make_unique<p1::WorkerLiveness>(expected_worker_pid_);
    limits_.low=c_.at("command_min_n");limits_.high=c_.at("command_max_n");
    legacy_readiness_enabled_=true;legacy_ready_timeout_ns_=5000000000LL;
    graph_arm_ns_=p1::monotonic_ns();legacy_prepare_start_ns_=graph_arm_ns_+1;legacy_prepare_deadline_ns_=legacy_prepare_start_ns_+legacy_ready_timeout_ns_;
    sink_->add({{"type","recording_ready"},{"run_id",run_},{"ready_ns",graph_arm_ns_},{"job_matched",0},{"decision_matched",0},{"observer_node","source_linked_test"},{"test_fixture",true}});
  }
#endif
#ifdef P1_SHADOW_ENTRY_TEST
  // Source-linked tests only; the runtime target never defines this macro.
  friend class ShadowEntryAccess;
  struct ShadowTestTag {};
  Regulator(ShadowTestTag,const std::string &path,const p1::shadow::LegacyIdentity &legacy):Node("p1_shadow_entry_test",rclcpp::NodeOptions().enable_rosout(false).start_parameter_services(false).start_parameter_event_publisher(false)){
    mode_="shadow";run_="shadow-source-linked-test";boot_=p1::boot_id();c_=p1::candidate_baseline();legacy_run_=legacy.run;expected_legacy_identity_=legacy;
    params_=p1::solver_params(c_);capability_lease_=std::make_unique<p1::CapabilityLease>(600000000);
    decision_pub_=create_publisher<p1::Decision>("/p1_test/shadow_decision",rclcpp::QoS(1).reliable());
    p1::WitnessHeader h{};p1::witness_text(h.run_id,run_);p1::witness_text(h.boot_id,boot_);
    #ifdef P1_LEGACY_READY_TEST
    // Bind the actual frozen contract at construction, before any source row.
    p1::witness_text(h.contract_sha256,"0e3eb70e74e922059ff17014ab1971b8a9fe20be0171964fc26410b7d769a933");
    #else
    p1::witness_text(h.contract_sha256,std::string(64,'a'));
    #endif
    p1::witness_text(h.source_sha256,std::string(64,'b'));p1::witness_text(h.binary_sha256,std::string(64,'c'));
    p1::witness_text(h.worker_binary_sha256,std::string(64,'d'));p1::witness_text(h.worker_instance,std::string(64,'e'));
    witness_=std::make_unique<p1::Witness>(true,h);sink_=std::make_unique<Sink>(path,512,decision_pub_,witness_.get(),p1::DiagPausePolicy{});
  }
#endif
  static p1::WitnessState ws(bool value){return value?p1::WitnessState::True:p1::WitnessState::False;}
  void phase_locked(p1::WitnessPhaseKind event,p1::WitnessObservation observation,int64_t ns,uint64_t job=0){
    if(!witness_->enabled())return;
    p1::WitnessPhase r{};r.event_code=event;r.observation_code=observation;r.ns=ns;r.tick=current_tick_;r.job_id=job;
    r.admission_slots=int32_t(admission_.slots());r.candidate_present=ws(bool(candidate_));
    {std::lock_guard<std::mutex> q(prep_mutex_);r.pending_present=ws(bool(pending_));}
    r.failed=ws(sink_->failed());r.stopping=ws(stopping_);r.pause_active=ws(sink_->pause_active());witness_->record_phase(r);
  }
  template<class Row>void identity(Row &r,const p1::Decision &d){r.job_id=d.job_id;r.tick=d.tick;r.target_tick=d.job_id?d.tick:0;r.task_generation=d.task_generation;r.model_generation=d.model_generation;r.config_generation=d.config_generation;r.schedule_generation=d.schedule_generation;r.clock_epoch=d.clock_epoch;}
  void audit_tick(const p1::Decision &d,bool present,bool failed_start,bool stopping_start){
    if(!witness_->enabled())return;
    p1::WitnessTick r{};identity(r,d);r.planned_ns=d.tick_planned_ns;r.start_ns=d.tick_start_ns;r.end_ns=p1::monotonic_ns();r.skipped_ticks=d.skipped_ticks;
    r.candidate_present=present;r.failed_start=failed_start;r.stopping_start=stopping_start;r.failed_end=sink_->failed();r.stopping_end=stopping_;witness_->record_tick(r);
  }
  static int64_t stamp(const builtin_interfaces::msg::Time & t){return int64_t(t.sec)*1000000000+t.nanosec;}
  struct Snapshot {std::vector<activation_alignment::Frame> activation_frames;uint64_t activation_history_generation=0;usv_mpc::Vector6d state=usv_mpc::Vector6d::Zero();std::shared_ptr<const usv_mpc::ReferenceInput> ref;std::vector<usv_mpc::HeldInputEvent> history;std::deque<p1::PublicationEvent> publication_history;p1::Anchor anchor;p1::Version version;uint64_t odom_seq=0,imu_seq=0,input_commit_ordinal=0;int64_t odom_stamp=0,imu_stamp=0,odom_receive=0,imu_receive=0,clock_receive=0,sim=0,freeze=0;bool mixed=false,paused=false,rtf_valid=false;double rtf=0;std::string anchor_producer,anchor_run,anchor_source,path_fingerprint,profile_fingerprint;};
  struct Preparation {Snapshot s;uint64_t tick;int64_t origin;};
  Snapshot snapshot_source_locked(int64_t now){Snapshot s;s.activation_history_generation=activation_sensor_history_.generation();s.state=state_;s.ref=ref_;s.input_commit_ordinal=input_commit_ordinal_;s.path_fingerprint=path_fingerprint_;s.profile_fingerprint=profile_fingerprint_;s.anchor=anchor_;s.version=version_;s.odom_seq=odom_seq_;s.imu_seq=imu_seq_;s.odom_stamp=odom_stamp_;s.imu_stamp=imu_stamp_;s.odom_receive=odom_receive_;s.imu_receive=imu_receive_;s.clock_receive=clock_receive_;s.sim=sim_;s.freeze=now;s.mixed=mixed_;s.paused=paused_;s.rtf_valid=rtf_valid_;s.rtf=rtf_;s.anchor_source=mode_=="shadow"?"legacy_publisher":mode_=="execute"?"regulator_publisher":"synthetic_static_fixture";s.anchor_producer=mode_=="shadow"?legacy_producer_:p1::digest(run_+boot_+std::to_string(getpid()));s.anchor_run=mode_=="shadow"?legacy_run_:run_;return s;}
  Snapshot snapshot_locked(int64_t now){auto s=snapshot_source_locked(now);s.activation_frames=activation_sensor_history_.copy();s.history.assign(history_.begin(),history_.end());s.publication_history=publication_history_;return s;}
  struct ActivationAttemptRecord {
    Snapshot raw,guard;activation_interleave::Record interleave;activation_alignment::Selection selection;p1::d0::Observation gate_observation;
    int64_t copied_ns=0,commit_check_ns=0,final_commit_ns=0;bool retry=false,predicted_available=false;
    p1::State predicted{};std::string reason;
  };
  struct ActivationCapture {std::array<ActivationAttemptRecord,activation_alignment::attempts> attempts;size_t count=0;int64_t decision_commit_ns=0;};
  static p1::Json materialize_activation_trace(const ActivationCapture &capture,int64_t observer_publish_return_ns){
    const auto begin=p1::monotonic_ns();
    p1_owned::require(capture.count>0&&capture.count<=activation_alignment::attempts&&capture.decision_commit_ns>0&&observer_publish_return_ns>=capture.decision_commit_ns,"deferred trace boundary");
    p1::Json trace={{"policy",activation_alignment::policy},{"capacity",activation_alignment::capacity},{"maximum_attempts",activation_alignment::attempts},
      {"observation_policy","bounded_values_then_JSON_after_observer_publish_return_v1"},{"decision_commit_ns",capture.decision_commit_ns},
      {"observer_publish_return_ns",observer_publish_return_ns},{"materialized_start_ns",begin},{"attempts",p1::Json::array()}};
    for(size_t index=0;index<capture.count;++index){const auto &r=capture.attempts[index];
      auto a=p1::Json{{"attempt",index+1},{"raw_snapshot",p1::d0::full_snapshot_json(r.raw)},
        {"sample_ns",r.raw.freeze},{"copy_capture_ns",r.copied_ns},{"history_generation",r.raw.activation_history_generation},
        {"frame_count",r.raw.activation_frames.size()},{"frames_scanned",r.selection.scanned},
        {"selected_frame",r.selection.frame?activation_alignment::json(*r.selection.frame):p1::Json(nullptr)},
        {"input_change_gate_ran",r.gate_observation.input_change_gate_ran},
        {"input_change_gate_unchanged",p1::d0::nullable_bool(r.gate_observation.input_change_gate_unchanged)},
        {"input_gate_reads",p1::d0::gate_reads_json(r.gate_observation)},{"guard_snapshot",p1::d0::source_json(r.guard)},
        {"commit_check_ns",r.commit_check_ns},{"retry",r.retry},{"reason",r.reason}};
      if(r.interleave.used){const auto &w=r.interleave;a["diagnostic_interleave"]={{"policy",activation_interleave::policy},{"begin_ns",w.begin_ns},{"deadline_ns",w.deadline_ns},{"end_ns",w.end_ns},{"wait_budget_ns",activation_interleave::wait_budget_ns},{"captured_odom_sequence",w.captured_sequence},{"observed_before",w.observed_before},{"observed_after",w.observed_after},{"changed",w.changed},{"cancelled",w.cancelled},{"business_mutex_held_during_wait",false},{"original_jitter_budget_unchanged",true}};}
      if(!r.retry){a["final_commit_ns"]=r.final_commit_ns;a["predicted_state"]=r.predicted_available?p1::Json(r.predicted):p1::Json(nullptr);}
      trace["attempts"].push_back(std::move(a));
    }
    trace["materialized_end_ns"]=p1::monotonic_ns();return trace;
  }

  std::string eligible(const Snapshot & s,int64_t now) {
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
    if(!sync.first)return "profile_pair_incomplete";
    for(auto & point:s.ref->path)for(double v:point)if(!std::isfinite(v))return "invalid_path";
    if(!s.anchor.known[0]||!s.anchor.known[1])return "unknown_anchor";
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
    const int64_t start=p1::monotonic_ns(),timeout=c_.at("recording_ready_timeout_ns").get<int64_t>();
    while(rclcpp::ok()&&!stop_requested&&p1::monotonic_ns()-start<=timeout){
      const bool ready=controlled_phase_subscription_->get_publisher_count()==1&&controlled_owner_phase_peer_->graph_matches_snapshot(*this)&&applied_->get_publisher_count()==1&&(!owner_peer_||owner_peer_->graph_matches_snapshot(*this))&&(!worker_peer_||worker_peer_->graph_matches_snapshot(*this))&&job_pub_->get_subscription_count()>=2&&decision_pub_->get_subscription_count()>=2&&
        named_subscription("/p1/solve_job","p1_solver_worker")&&named_subscription("/p1/solve_job","",true)&&
        named_subscription("/p1/execution_decision",recording_observer_)&&named_subscription("/p1/execution_decision","",true)&&
        named_subscription("/p1/solve_candidate","p1_regulator")&&named_subscription("/p1/solve_candidate","",true);
      if(ready){
        graph_arm_ns_=p1::monotonic_ns();
        if(!sink_->add({{"type","recording_ready"},{"run_id",run_},{"ready_ns",graph_arm_ns_},
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

  struct ReadyHeld {
    int64_t sim_ns=0;int channel=0;double n=0;uint64_t sequence=0;int64_t publish_ns=0;
    p1::Json json()const{return {{"sim_ns",sim_ns},{"channel",channel},{"n",n},{"sequence",sequence},{"publish_ns",publish_ns}};}
  };
  void invalidate_legacy_ready_locked(const std::string &reason,int64_t now){
    if(!legacy_readiness_enabled_||!legacy_ready_issued_||legacy_readiness_terminal_)return;
    legacy_readiness_terminal_=true;legacy_measurement_eligible_=false;
    sink_->add({{"type","legacy_ready_invalidated"},{"schema","p1-D1-legacy-ready-invalidation-v1"},{"run_id",run_},
      {"check_ns",now},{"legacy_ready_ns",legacy_ready_ns_},{"reason",reason},{"measurement_eligible",false},{"terminal",true},
      {"clock_epoch",version_.epoch},{"sequence",legacy_sequence_}});
    // The existing uniform terminal transition clears all uncommitted work.
    unusable_locked("legacy_ready_invalidated:"+reason,now);
  }
  void check_legacy_prepare_timeout_locked(int64_t now){
    if(!legacy_readiness_enabled_||legacy_ready_issued_||legacy_readiness_terminal_||now<=legacy_prepare_deadline_ns_)return;
    legacy_readiness_terminal_=true;legacy_measurement_eligible_=false;
    sink_->add({{"type","legacy_ready_failed"},{"schema","p1-D1-legacy-ready-failure-v1"},{"run_id",run_},
      {"check_ns",now},{"prepare_start_ns",legacy_prepare_start_ns_},{"prepare_deadline_ns",legacy_prepare_deadline_ns_},
      {"reason","prepare_timeout"},{"last_pending_reason",legacy_ready_pending_reason_},{"measurement_eligible",false},{"terminal",true}});
    unusable_locked("legacy_ready_timeout",now);stop_requested=true;
  }
  // Only actual executor callbacks invoke the issue path. The periodic tick
  // checks the finite deadline but cannot fabricate callback readiness.
  void try_legacy_ready_locked(int64_t now){
    if(!legacy_readiness_enabled_||legacy_readiness_terminal_)return;
    if(legacy_ready_issued_){
      if(!legacy_sequence_complete_||!legacy_ready_projection_complete_||legacy_received_!=legacy_sequence_||legacy_admitted_!=legacy_sequence_){invalidate_legacy_ready_locked("legacy_lifecycle_or_projection_incomplete",now);return;}
      std::array<bool,2> covered{false,false};for(const auto &entry:history_)if(entry.sim_ns<=odom_stamp_&&entry.channel>=0&&entry.channel<2)covered[entry.channel]=true;
      if(ready_history_.size()!=history_.size()||!covered[0]||!covered[1]||!anchor_.known[0]||!anchor_.known[1])invalidate_legacy_ready_locked("held_history_coverage_lost",now);
      return;
    }
    check_legacy_prepare_timeout_locked(now);if(legacy_readiness_terminal_)return;
    const auto pending=[this](const char *reason){legacy_ready_pending_reason_=reason;};
    if(!graph_arm_ns_||graph_arm_ns_>=now){pending("graph_not_armed");return;}
    if(worker_unusable_||!worker_valid_||sink_->failed()||!audit_identity_ok_){pending("worker_or_source_unusable");return;}
    check_worker_locked(now);if(worker_unusable_)return;
    if(last_capability_.is_null()||capability_lease_->last_valid_ns()<=0||worker_instance_!=witness_->header().worker_instance){pending("exact_worker_capability_missing");return;}
    if(!legacy_sequence_||legacy_first_sequence_!=1||!legacy_sequence_complete_||!legacy_ready_projection_complete_||legacy_received_!=legacy_sequence_||legacy_admitted_!=legacy_sequence_||legacy_producer_!=expected_legacy_identity_.producer||
       !anchor_.known[0]||!anchor_.known[1]||anchor_.seq[0]!=legacy_sequence_||anchor_.seq[1]!=legacy_sequence_){pending("whole_pair_lifecycle_incomplete");return;}
    if(!odom_seq_||odom_receive_<=legacy_pair_processed_ns_||odom_stamp_<std::max(legacy_anchor_sim_ns_[0],legacy_anchor_sim_ns_[1])){pending("post_pair_odom_missing");return;}
    if(!imu_seq_||!path_seq_||!profile_seq_||!ready_path_valid_||!ready_profile_valid_){pending("valid_input_versions_missing");return;}
    const auto current=snapshot_locked(now);const auto source_reason=eligible(current,now);
    if(!source_reason.empty()){legacy_ready_pending_reason_=source_reason;return;}
    // Readiness always authenticates the received IMU, even when the current
    // control snapshot uses the most recent odometry yaw rate.
    const p1::SourceAgeLimits source_limits{c_.at("odom_age_ns").get<int64_t>(),c_.at("imu_age_ns").get<int64_t>(),
      c_.at("odom_sim_lag_ns").get<int64_t>(),c_.at("imu_sim_lag_ns").get<int64_t>(),c_.at("source_future_slack_ns").get<int64_t>()};
    const auto all_sources=p1::state_source_check(now,sim_,clock_receive_,{odom_stamp_,odom_receive_},{imu_stamp_,imu_receive_},true,source_limits);
    if(!all_sources.empty()||std::abs(imu_stamp_-odom_stamp_)>c_.at("mixed_skew_ns").get<int64_t>()){pending("imu_source_age_or_skew");return;}
    if(ready_history_.size()!=history_.size()||ready_history_.empty()){pending("held_history_provenance_incomplete");return;}
    std::array<std::optional<ReadyHeld>,2> held;size_t index=0;p1::Json history=p1::Json::array();
    for(const auto &entry:ready_history_){const auto &raw=history_[index++];
      if(entry.channel<0||entry.channel>1||entry.sim_ns!=raw.sim_ns||entry.channel!=raw.channel||entry.n!=raw.value){pending("held_history_provenance_mismatch");return;}
      history.push_back(entry.json());if(entry.sim_ns<=odom_stamp_)held[entry.channel]=entry;
    }
    if(!held[0]||!held[1]){pending("dual_preodom_history_missing");return;}
    p1::Json ready={{"schema","p1-D1-legacy-ready-v1"},{"graph_arm_ns",graph_arm_ns_},{"legacy_ready_ns",now},
      {"executor_spinning",true},{"evidence_source","executor_callback_join"},{"measurement_eligible",true},
      {"legacy_identity",expected_legacy_identity_.json()},{"clock_epoch",version_.epoch},{"anchor_sequence",anchor_.seq},
      {"legacy_received_count",legacy_received_},{"legacy_admitted_count",legacy_admitted_},
      {"anchor_n",anchor_.n},{"anchor_known",anchor_.known},{"anchor_publish_ns",anchor_.time},{"anchor_sim_ns",legacy_anchor_sim_ns_},
      {"pair_processed_ns",legacy_pair_processed_ns_},{"pair_publish_end_ns",legacy_pair_publish_end_ns_},
      {"odom_stamp_ns",odom_stamp_},{"odom_receive_ns",odom_receive_},{"odom_sequence",odom_seq_},
      {"imu_stamp_ns",imu_stamp_},{"imu_receive_ns",imu_receive_},{"imu_sequence",imu_seq_},{"r_from_imu",mixed_},
      {"clock_sim_ns",sim_},{"clock_receive_ns",clock_receive_},{"rtf",rtf_},{"rtf_valid",rtf_valid_.load()},{"paused",paused_.load()},
      {"path_sequence",path_seq_},{"profile_sequence",profile_seq_},{"path_stamp",std::array<int,2>{ref_->path_stamp.first,ref_->path_stamp.second}},
      {"profile_stamp",std::array<int,2>{ref_->profile_stamp.first,ref_->profile_stamp.second}},{"path_fingerprint",path_fingerprint_},{"profile_fingerprint",profile_fingerprint_},
      {"version",{{"task",version_.task},{"model",version_.model},{"config",version_.config},{"schedule",version_.schedule},{"epoch",version_.epoch}}},
      {"held_history",history},{"preodom_held",p1::Json::array({held[0]->json(),held[1]->json()})},{"worker_capability",last_capability_},
      {"capability_validation_commit_ns",last_capability_commit_ns_},{"capability_lease_last_valid_ns",capability_lease_->last_valid_ns()},
      {"capability_timeout_ns",capability_lease_->timeout_ns()},{"prepare_start_ns",legacy_prepare_start_ns_},{"prepare_deadline_ns",legacy_prepare_deadline_ns_}};
    if(!sink_->add({{"type","legacy_ready"},{"schema","p1-D1-legacy-ready-source-v1"},{"run_id",run_},{"readiness",ready}})){
      legacy_readiness_terminal_=true;unusable_locked("legacy_ready_source_failed",now);stop_requested=true;return;
    }
    legacy_ready_ns_=now;legacy_ready_issued_=true;legacy_measurement_eligible_=true;legacy_ready_pending_reason_.clear();
  }

  std::optional<uint64_t> invalidate_locked(){activation_sensor_history_.clear();activation_odom_generation_=0;if(sink_)sink_->add({{"type","activation_sensor_history_reset"},{"input_commit_ordinal",input_commit_ordinal_},{"history_generation",activation_sensor_history_.generation()},{"version",p1::d0::version_json(version_)},{"reset_ns",p1::monotonic_ns()}});reference_epoch_.invalidate_if_changed(task_time_reference::Binding{{version_.task,version_.model,version_.config,version_.schedule,version_.epoch},run_,boot_,hash_,nominal_,path_fingerprint_,profile_fingerprint_});if(adapter_)adapter_->cancel(0,p1::monotonic_ns());admission_.invalidate();candidate_.reset();std::lock_guard<std::mutex> l(prep_mutex_);std::optional<uint64_t> target;if(pending_)target=pending_->tick+1;pending_.reset();return target;}
  void unusable_locked(const std::string & reason,int64_t now){
    if(worker_unusable_)return;
    // Mark terminal before recursion into the uniform unusable transition.
    invalidate_legacy_ready_locked("worker_unusable:"+reason,now);if(worker_unusable_)return;
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
  std::map<std::string,uint64_t> raw_callback_sequences_;
  p1::Json remember_activation_sensor_locked(const std::string &kind,uint64_t sequence){
    if(!odom_seq_||activation_odom_generation_!=activation_sensor_history_.generation())return nullptr;
    activation_alignment::Frame f;std::copy(state_.data(),state_.data()+6,f.state.begin());f.version=version_;
    f.input_commit_ordinal=input_commit_ordinal_;f.origin_kind=kind;f.origin_sequence=sequence;
    f.odom_sequence=odom_seq_;f.imu_sequence=imu_seq_;f.odom_stamp_ns=odom_stamp_;f.imu_stamp_ns=imu_stamp_;
    f.odom_receive_ns=odom_receive_;f.imu_receive_ns=imu_receive_;f.r_from_imu=mixed_;
    activation_sensor_history_.append(f);f.history_generation=activation_sensor_history_.generation();return activation_alignment::json(f);
  }
  void odom(const nav_msgs::msg::Odometry & m,const p1::Json *raw=nullptr){auto now=p1::monotonic_ns();auto & p=m.pose.pose.position;auto & q=m.pose.pose.orientation;auto & t=m.twist.twist;std::array<double,5> a={p.x,p.y,t.linear.x,t.linear.y,t.angular.z};std::array<double,4> quat={q.x,q.y,q.z,q.w};bool valid=usv_mpc::admit_odom(a,quat)&&m.header.frame_id==c_.at("expected_pose_frame")&&m.child_frame_id==c_.at("expected_child_frame");std::lock_guard<std::mutex> l(mutex_);++input_commit_ordinal_;++odom_received_;
    if(valid){state_=usv_mpc::compose_odom(a,quat);odom_seq_=odom_received_;odom_stamp_=stamp(m.header.stamp);odom_receive_=now;mixed_=false;activation_odom_generation_=activation_sensor_history_.generation();}
    const auto activation_frame=valid?remember_activation_sensor_locked("odom",odom_received_):p1::Json(nullptr);
    const auto v3_commit_ns=v3_policy_==activation_interleave::policy&&valid?p1::monotonic_ns():0;
    sink_->add({{"type","odom_admission"},{"diagnostic_v3_commit_ns",v3_commit_ns},{"activation_sensor_frame",activation_frame},{"input_commit_ordinal",input_commit_ordinal_},{"raw_input",raw?*raw:p1::Json(nullptr)},{"sequence",odom_received_},{"valid",valid},{"pose_frame",m.header.frame_id.substr(0,128)},{"pose_frame_truncated",m.header.frame_id.size()>128},{"child_frame",m.child_frame_id.substr(0,128)},{"child_frame_truncated",m.child_frame_id.size()>128},{"accepted_sequence",odom_seq_},{"stamp_ns",stamp(m.header.stamp)},{"receive_ns",now},{"state",std::array<double,6>{state_[0],state_[1],state_[2],state_[3],state_[4],state_[5]}}});
    try_legacy_ready_locked(p1::monotonic_ns());
    if(v3_commit_ns)v3_interleave_.observe_odom(odom_seq_);
  }
  void imu(const sensor_msgs::msg::Imu & m,const p1::Json *raw=nullptr){auto now=p1::monotonic_ns();std::lock_guard<std::mutex> l(mutex_);++input_commit_ordinal_;++imu_received_;const bool valid=usv_mpc::admit_imu(m.angular_velocity.z)&&m.header.frame_id==c_.at("expected_imu_frame");if(valid){usv_mpc::compose_imu(state_,m.angular_velocity.z);imu_seq_=imu_received_;imu_stamp_=stamp(m.header.stamp);imu_receive_=now;mixed_=true;}const auto activation_frame=valid?remember_activation_sensor_locked("imu",imu_received_):p1::Json(nullptr);sink_->add({{"type","imu_admission"},{"activation_sensor_frame",activation_frame},{"input_commit_ordinal",input_commit_ordinal_},{"raw_input",raw?*raw:p1::Json(nullptr)},{"sequence",imu_received_},{"valid",valid},{"frame_id",m.header.frame_id.substr(0,128)},{"frame_truncated",m.header.frame_id.size()>128},{"r_value",m.angular_velocity.z},{"accepted_sequence",imu_seq_},{"stamp_ns",stamp(m.header.stamp)},{"receive_ns",now}});try_legacy_ready_locked(p1::monotonic_ns());}
  void path(const nav_msgs::msg::Path & m,const p1::Json *raw=nullptr){auto next=std::make_shared<usv_mpc::ReferenceInput>();std::string fingerprint;
    const auto resource=p1::check_path_resources(m,resources_);const bool resource_ok=bool(resource);
    bool valid=resource_ok&&m.header.frame_id==c_.at("expected_pose_frame");
    if(valid)for(auto & p:m.poses){auto & q=p.pose.orientation;double yaw=usv_mpc::quaternion_to_yaw(q.x,q.y,q.z,q.w);if(!std::isfinite(p.pose.position.x)||!std::isfinite(p.pose.position.y)||!std::isfinite(yaw)){valid=false;break;}next->path.push_back({p.pose.position.x,p.pose.position.y,yaw});}
    if(!valid)next->path.clear();fingerprint=p1::digest(p1::Json{{"frame",resource_ok?m.header.frame_id:std::string("resource_rejected")},{"path",next->path}}.dump());
    std::lock_guard<std::mutex> l(mutex_);++input_commit_ordinal_;next->profile=ref_->profile;next->profile_stamp=ref_->profile_stamp;next->profile_sequence=ref_->profile_sequence;next->path_sequence=++path_seq_;next->path_stamp={m.header.stamp.sec,int(m.header.stamp.nanosec)};
    if(fingerprint!=path_fingerprint_||next->path.size()<2){invalidate_legacy_ready_locked("path_fingerprint_changed",p1::monotonic_ns());version_.task++;path_fingerprint_=fingerprint;invalidate_locked();}
    ready_path_valid_=valid;
    ref_=next;sink_->add({{"type","path_version"},{"input_commit_ordinal",input_commit_ordinal_},{"raw_input",raw?*raw:p1::Json(nullptr)},{"received_sequence",path_seq_},{"task_generation",version_.task},{"fingerprint",fingerprint},{"points",next->path.size()},{"valid",valid},{"resource_valid",resource_ok},{"received_points",m.poses.size()},{"frame_bytes",m.header.frame_id.size()},{"processed_ns",p1::monotonic_ns()}});
    try_legacy_ready_locked(p1::monotonic_ns());
    retry_reference_pair_locked("path",valid&&resource_ok);
  }
  void profile(const std_msgs::msg::Float64MultiArray & m,const p1::Json *raw=nullptr){auto next=std::make_shared<usv_mpc::ReferenceInput>();const auto resource=p1::check_profile_resources(m,resources_);const bool metadata_ok=bool(resource);
    bool valid=metadata_ok&&!m.data.empty()&&m.data.size()%4==0&&m.data.size()/4<=resources_.max_profile_rows;std::vector<std::string> labels;if(metadata_ok)for(auto & d:m.layout.dim)labels.push_back(d.label);bool stamp_ok=false;if(metadata_ok)next->profile_stamp=usv_mpc::parse_profile_stamp(labels,stamp_ok);if(!stamp_ok)next->profile_stamp={-1,-1};
    if(valid){for(size_t i=0;i<m.data.size()/4;++i){std::array<double,4> r={m.data[4*i],m.data[4*i+1],m.data[4*i+2],m.data[4*i+3]};if(!p1::finite_array(r)||(i&&r[3]<=m.data[4*(i-1)+3])){valid=false;break;}next->profile.push_back(r);}}if(!valid)next->profile.clear();auto fp=p1::digest(p1::Json(next->profile).dump());
    std::lock_guard<std::mutex> l(mutex_);++input_commit_ordinal_;next->path=ref_->path;next->path_stamp=ref_->path_stamp;next->path_sequence=ref_->path_sequence;next->profile_sequence=++profile_seq_;if(fp!=profile_fingerprint_){invalidate_legacy_ready_locked("profile_fingerprint_changed",p1::monotonic_ns());version_.task++;profile_fingerprint_=fp;invalidate_locked();}ready_profile_valid_=valid&&stamp_ok;ref_=next;sink_->add({{"type","profile_version"},{"input_commit_ordinal",input_commit_ordinal_},{"raw_input",raw?*raw:p1::Json(nullptr)},{"received_sequence",profile_seq_},{"task_generation",version_.task},{"fingerprint",fp},{"rows",next->profile.size()},{"valid",valid},{"resource_valid",metadata_ok&&m.data.size()<=resources_.max_profile_rows*4},{"received_data_elements",m.data.size()},{"received_dims",m.layout.dim.size()},{"processed_ns",p1::monotonic_ns()}});try_legacy_ready_locked(p1::monotonic_ns());
    retry_reference_pair_locked("profile",valid&&metadata_ok&&stamp_ok);
  }
  void clock(const rosgraph_msgs::msg::Clock & m,const p1::Json *raw=nullptr){auto now=p1::monotonic_ns(),s=stamp(m.clock);std::lock_guard<std::mutex> l(mutex_);++input_commit_ordinal_;if(clock_receive_&&(s<sim_||s-sim_>5000000000LL)){invalidate_legacy_ready_locked("clock_epoch_changed",now);version_.epoch++;version_.schedule++;clock_window_.reset();rtf_valid_=false;rtf_=0;history_.clear();ready_history_.clear();publication_history_.clear();anchor_.known={false,false};invalidate_locked();}
    if(s!=sim_){last_clock_advance_=now;if(paused_){paused_=false;version_.schedule++;invalidate_locked();}}
    sim_=s;clock_receive_=now;
    const auto estimate=clock_window_.observe(now,s,c_.at("rtf_low").get<double>(),c_.at("rtf_high").get<double>());
    rtf_=estimate.value;rtf_valid_=estimate.valid;
    sink_->add({{"type","clock"},{"input_commit_ordinal",input_commit_ordinal_},{"raw_input",raw?*raw:p1::Json(nullptr)},{"sim_ns",s},{"receive_ns",now},{"epoch",version_.epoch},{"schedule_generation",version_.schedule},{"paused",paused_.load()},{"rtf",rtf_},{"rtf_valid",rtf_valid_.load()},{"rtf_window_span_ns",estimate.span_ns},{"rtf_stored_samples",estimate.stored_samples}});
    try_legacy_ready_locked(p1::monotonic_ns());
  }
  p1::Json worker_callback_snapshot_locked() const {
    return {{"worker_instance",worker_instance_},{"worker_valid",worker_valid_.load()},{"worker_unusable",worker_unusable_.load()},{"lease_last_valid_ns",capability_lease_->last_valid_ns()},{"candidate_present",bool(candidate_)},{"admission_slots",admission_.slots()}};
  }
  template<class Message>void receive_worker(const Message &m,const rclcpp::MessageInfo &info,c37_owned::Interface interface){
    constexpr bool is_capability=std::is_same<Message,p1::Capability>::value;
    static_assert(is_capability||std::is_same<Message,p1::Candidate>::value,"bounded registered Worker interfaces only");
    const auto entered=p1::monotonic_ns();
    const std::string label=is_capability?"capability":"candidate";
    const std::string topic=is_capability?"/p1/worker_capability":"/p1/solve_candidate";
    const std::string type=is_capability?"usv_research_interfaces/msg/WorkerCapability":"usv_research_interfaces/msg/SolveCandidate";
    auto resource=[&](){if constexpr(is_capability)return p1::check_capability_resources(m);else return p1::check_candidate_resources(m,resources_);}();
    p1::Json event;uint64_t received=0,sequence=0;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      sequence=++raw_callback_sequences_[topic];received=is_capability?++worker_capability_received_:++worker_candidate_received_;++input_commit_ordinal_;
      const auto before=worker_callback_snapshot_locked();
      const auto authentication=worker_peer_?worker_peer_->callback_reason(info,interface):std::string("worker_peer_missing");
      const auto checked=p1::monotonic_ns();const auto &meta=info.get_rmw_message_info();
      // Evidence copies fixed metadata bytes; authentication above remains authoritative.
      // Malformed metadata must still yield a bounded rejection record.
      std::array<uint8_t,RMW_GID_STORAGE_SIZE> actual_gid{};
      std::copy(std::begin(meta.publisher_gid.data),std::end(meta.publisher_gid.data),actual_gid.begin());
      p1::Json guard_alive=nullptr;if(authentication.empty())guard_alive=true;else if(authentication=="worker_process_exited")guard_alive=false;
      event={{"type","adapter_worker_callback"},{"interface",label},{"topic",topic},{"message_type",type},{"callback_sequence",sequence},{"received_count",received},{"input_commit_ordinal",input_commit_ordinal_},{"entry_ns",entered},{"authentication_checked_ns",checked},{"resource_valid",bool(resource)},{"resource_reason",resource.reason},{"resource_field",resource.field},{"resource_observed",resource.observed},{"resource_limit",resource.limit},{"authentication_reason",authentication},{"worker_process_alive_at_guard",guard_alive},{"expected_gid",worker_peer_?worker_peer_->expected_gid(interface):p1::Json(nullptr)},{"actual_gid",actual_gid},{"rmw_implementation_matches_registered",meta.publisher_gid.implementation_identifier&&std::strcmp(meta.publisher_gid.implementation_identifier,"rmw_fastrtps_cpp")==0},{"source_timestamp",meta.source_timestamp},{"received_timestamp",meta.received_timestamp},{"from_intra_process",meta.from_intra_process},{"full_cdr_serialized",false},{"raw_input",nullptr},{"before",before}};
      if(!resource||!authentication.empty()){
        event["after"]=worker_callback_snapshot_locked();event["callback_completed_ns"]=p1::monotonic_ns();event["processed_ns"]=event["callback_completed_ns"];event["later_worker_process_alive"]=worker_peer_?p1::Json(worker_peer_->alive()):p1::Json(nullptr);event["semantic_callback_invoked"]=false;
        sink_->add(std::move(event));return;
      }
    }
    // Resource shape and actual interface GID/pidfd precede bounded full CDR.
    // Typed payload/lease/echo checks remain the original semantic callbacks.
    auto raw=p1_observation_v4::raw_input(m,info,topic,type,sequence);
    if constexpr(is_capability)capability(m,&raw,received);else candidate(m,&raw,received);
    {
      std::lock_guard<std::mutex> lock(mutex_);event["raw_input"]=raw;event["full_cdr_serialized"]=true;event["semantic_callback_invoked"]=true;event["after"]=worker_callback_snapshot_locked();event["callback_completed_ns"]=p1::monotonic_ns();event["processed_ns"]=event["callback_completed_ns"];event["later_worker_process_alive"]=worker_peer_->alive();sink_->add(std::move(event));
    }
  }
  void capability(const p1::Capability & m,const p1::Json *raw=nullptr,uint64_t received_count=0){const auto received=p1::monotonic_ns();auto resource=p1::check_capability_resources(m);if(!resource){sink_->add({{"type","resource_rejected"},{"raw_input",raw?*raw:p1::Json(nullptr)},{"interface","capability"},{"reason",resource.reason},{"field",resource.field},{"observed",resource.observed},{"limit",resource.limit},{"receive_ns",received},{"renewed",false}});return;}std::lock_guard<std::mutex> l(mutex_);const auto now=p1::monotonic_ns();const p1::Json observation_before={{"worker_instance",worker_instance_},{"worker_valid",worker_valid_.load()},{"worker_unusable",worker_unusable_.load()}};check_worker_locked(now);const auto before=capability_lease_->last_valid_ns();
    const bool identity=m.run_id==run_&&m.boot_id==boot_&&m.contract_hash==hash_&&m.nominal_hash==nominal_&&m.pid==expected_worker_pid_;
    const bool valid=identity&&m.schema_version=="p1-worker-capability-v1"&&m.clock_name=="CLOCK_MONOTONIC"&&m.backend=="acados"&&m.matrix_layout=="column_major"&&m.horizon_steps==20&&m.prediction_dt==.2&&!m.fatal&&!m.worker_instance.empty()&&m.startup_ns>0&&m.fault_injection_enabled==c_.at("fault_injection_enabled").get<bool>();
    bool renewed=false;
    if(witness_->enabled()&&valid&&identity&&m.worker_instance!=witness_->header().worker_instance)audit_identity_ok_=false;
    if(identity){
      if(!worker_instance_.empty()&&worker_instance_!=m.worker_instance)unusable_locked("worker_instance_changed",now);
      if(m.fatal)unusable_locked("fatal_capability",now);
      if(valid&&!worker_unusable_){renewed=capability_lease_->renew(now);if(renewed){worker_instance_=m.worker_instance;worker_valid_=true;if(m.active_job!=worker_active_){worker_active_=m.active_job;worker_active_since_=now;}}else unusable_locked(capability_lease_->check(now),now);}
    }
    const p1::Json admission={{"type","capability_admission"},{"raw_input",raw?*raw:p1::Json(nullptr)},{"callback_sequence",raw?raw->at("callback_sequence"):p1::Json(0)},{"received_count",received_count},{"lease_observation",{{"before",observation_before},{"after",{{"worker_instance",worker_instance_},{"worker_valid",worker_valid_.load()},{"worker_unusable",worker_unusable_.load()}}}}},{"receive_ns",received},{"validation_commit_ns",now},{"identity_valid",identity},{"valid",valid},{"renewed",renewed},{"terminal_run",worker_unusable_.load()},
      {"lease_last_before_ns",before},{"lease_last_after_ns",capability_lease_->last_valid_ns()},{"lease_timeout_ns",capability_lease_->timeout_ns()},{"source_freshness_available",false},
      {"capability",{{"schema_version",m.schema_version},{"run_id",m.run_id},{"boot_id",m.boot_id},{"contract_hash",m.contract_hash},{"nominal_hash",m.nominal_hash},{"worker_instance",m.worker_instance},{"clock_name",m.clock_name},{"backend",m.backend},{"matrix_layout",m.matrix_layout},{"horizon_steps",m.horizon_steps},{"prediction_dt",m.prediction_dt},{"pid",m.pid},{"startup_ns",m.startup_ns},{"completed_jobs",m.completed_jobs},{"active_job",m.active_job},{"pending_count",m.pending_count},{"fault_injection_enabled",m.fault_injection_enabled},{"fatal",m.fatal},{"reason",m.reason}}}};
    sink_->add(admission);if(renewed){last_capability_=admission.at("capability");last_capability_commit_ns_=now;}try_legacy_ready_locked(p1::monotonic_ns());
  }
  void poll_adapter_close(){
    if(!adapter_||adapter_close_observed_.load())return;
    if(diagnostic_c38_mode_=="suppress-close-poll"){if(!c38_suppression_logged_){c38_suppression_logged_=true;sink_->add({{"type","diagnostic_c38_close_poll_suppressed"},{"checked_ns",p1::monotonic_ns()},{"diagnostic_only",true},{"stage_qualified",false}});}return;}
    try{
      if(!std::filesystem::exists(adapter_close_file_))return;
      const auto bytes=c36_owned::detail::read_manifest(adapter_close_file_);const auto request=c36_owned::detail::strict_json(bytes);
      p1_owned::require(request.at("schema")=="p1-C3.6-driver-close-request-v1"&&request.at("run_id")==run_&&request.at("boot_id")==boot_&&request.at("owner_manifest_sha256")==adapter_pins_.at("publisher_peer").at("manifest_sha256"),"adapter close identity");
      p1_owned::require(c36_owned::detail::uint_field(request,"driver_pid",INT_MAX)==adapter_pins_.at("driver").at("pid").get<uint64_t>()&&c36_owned::detail::uint_field(request,"driver_start_ticks",UINT64_MAX)==adapter_pins_.at("driver").at("start_ticks").get<uint64_t>()&&request.at("driver_tool_sha256")==adapter_pins_.at("driver_tool_sha256"),"adapter close driver identity");
      const auto requested=c36_owned::detail::uint_field(request,"request_ns",INT64_MAX);const auto read_completed=p1::monotonic_ns();p1_owned::require(requested>0&&requested<=uint64_t(read_completed),"adapter close time");
      std::lock_guard<std::mutex> lock(mutex_);adapter_close_request_ns_=static_cast<int64_t>(requested);adapter_close_observed_=true;adapter_close_ns_=p1::monotonic_ns();auto r=adapter_->request_close(adapter_close_ns_);invalidate_locked();
      sink_->add({{"type","adapter_driver_close_observed"},{"requested_ns",requested},{"observed_ns",adapter_close_ns_},{"read_completed_ns",read_completed},{"request_sha256",p1_owned::sha256_bytes(bytes)},{"cancel_reason",r.reason},{"driver_close_request",true},{"owner_close_intent","unknown"},{"owner_process_alive",owner_peer_->alive()},{"owner_endpoints_exited","unknown"},{"evidence",adapter_->evidence()}});
    }catch(const std::exception& e){std::lock_guard<std::mutex> lock(mutex_);adapter_close_observed_=true;adapter_close_ns_=p1::monotonic_ns();adapter_->request_close(adapter_close_ns_);unusable_locked("adapter_close_evidence_invalid",adapter_close_ns_);sink_->add({{"type","adapter_close_evidence_failed"},{"reason",e.what()},{"observed_ns",adapter_close_ns_}});}
  }
  void receive_applied(const usv_research_interfaces::msg::AppliedControl &m,const rclcpp::MessageInfo &info){
    const std::array<size_t,10> text={m.schema_version.size(),m.run_id.size(),m.producer_instance_id.size(),m.baseline_id.size(),m.config_hash.size(),m.clock_status.size(),m.steady_clock_domain.size(),m.control_source.size(),m.event_semantics.size(),m.publish_error.size()};
    if(std::any_of(text.begin(),text.end(),[](size_t n){return n>128;})){
      // Count every received packet before rejecting it. Do not copy or
      // serialize unbounded strings, and never erase this lifecycle hole by
      // subsequently admitting a legal sequence-one packet.
      std::lock_guard<std::mutex> lock(mutex_);const auto now=p1::monotonic_ns();
      ++input_commit_ordinal_;++legacy_received_;const auto callback=++raw_callback_sequences_["/research/control/applied"];
      legacy_sequence_complete_=false;legacy_ready_projection_complete_=false;normal_complete_=false;legacy_measurement_eligible_=false;
      invalidate_locked();invalidate_legacy_ready_locked("applied_resource_domain",now);
      std::array<uint8_t,RMW_GID_STORAGE_SIZE> actual_gid{};const auto &rmw=info.get_rmw_message_info();
      std::copy(std::begin(rmw.publisher_gid.data),std::end(rmw.publisher_gid.data),actual_gid.begin());
      sink_->add({{"type","adapter_applied_resource_rejected"},{"field_bytes",text},{"processed_ns",now},{"sequence",m.sequence},
        {"input_commit_ordinal",input_commit_ordinal_},{"callback_sequence",callback},{"received_count",legacy_received_},{"admitted_count",legacy_admitted_},
        {"publisher_gid",actual_gid},{"rmw_implementation_matches_registered",rmw.publisher_gid.implementation_identifier&&std::strcmp(rmw.publisher_gid.implementation_identifier,"rmw_fastrtps_cpp")==0},
        {"full_cdr_serialized",false},{"lifecycle_complete",false},{"projection_complete",false},{"measurement_eligible",false}});
      return;
    }
    auto raw=p1_observation_v4::raw_input(m,info,"/research/control/applied","usv_research_interfaces/msg/AppliedControl",++raw_callback_sequences_["/research/control/applied"]);
    legacy_applied(m,&raw,&info);
  }
  static bool queued_terminal_zero_predicate(const usv_research_interfaces::msg::AppliedControl &m,
      const std::string &authentication,bool original_gid,bool driver_closed,bool business_closed,
      int64_t request_ns,int64_t observed_ns,int64_t receipt_ns){
    if(authentication!="owner_process_exited"||!original_gid||!driver_closed||!business_closed||
       request_ns<=0||observed_ns<request_ns||receipt_ns<observed_ns||receipt_ns-request_ns>2000000000LL||
       m.control_source!="shutdown_zero"||!std::isfinite(m.final_n[0])||!std::isfinite(m.final_n[1])||
       m.final_n[0]!=0.0||m.final_n[1]!=0.0||!m.left_publish_success||!m.right_publish_success)return false;
    return m.left_publish_start_steady_ns>=request_ns&&m.left_publish_end_steady_ns>=m.left_publish_start_steady_ns&&
      m.right_publish_start_steady_ns>=request_ns&&m.right_publish_start_steady_ns>=m.left_publish_end_steady_ns&&
      m.right_publish_end_steady_ns>=m.right_publish_start_steady_ns&&m.left_publish_end_steady_ns<=receipt_ns&&m.right_publish_end_steady_ns<=receipt_ns;
  }
  void legacy_applied(const usv_research_interfaces::msg::AppliedControl & m,const p1::Json* raw=nullptr,const rclcpp::MessageInfo* info=nullptr){
    std::lock_guard<std::mutex> l(mutex_);++input_commit_ordinal_;const auto now=p1::monotonic_ns();
    ++legacy_received_;
    if(owner_peer_){
      auto authentication=info?owner_peer_->callback_reason(*info):std::string("callback_info_missing");
      const bool queued_tail=queued_terminal_zero_predicate(m,authentication,info&&owner_peer_->gid_matches(*info),adapter_close_observed_.load(),adapter_&&adapter_->closing(),adapter_close_request_ns_,adapter_close_ns_,now);
      sink_->add({{"type","adapter_applied_callback"},{"raw_input",raw?*raw:p1::Json(nullptr)},{"sequence",m.sequence},{"processed_ns",now},{"authentication_reason",authentication},{"queued_terminal_tail",queued_tail},{"owner_process_alive",owner_peer_->alive()},{"expected_gid",owner_peer_->expected_gid()}});
      if(!authentication.empty()&&!queued_tail){invalidate_legacy_ready_locked("adapter_applied_authentication:"+authentication,now);sink_->add({{"type","adapter_applied_auth_rejected"},{"reason",authentication},{"processed_ns",now},{"sequence",m.sequence},{"anchor_after",anchor_.n},{"component",adapter_->evidence()}});return;}
    }
    const auto assessment=p1::shadow::assess(m,expected_legacy_identity_,legacy_producer_,version_.epoch,legacy_sequence_,anchor_,
      !history_.empty(),history_.empty()?0:history_.back().sim_ns,now,limits_.low,limits_.high);
    if(!assessment){
      // Every received packet remains in the complete lifecycle population.
      // A nonadmitted receipt after ready breaks qualification even if it is
      // foreign/duplicate and cannot mutate an authenticated command anchor.
      invalidate_legacy_ready_locked(std::string("legacy_receipt_not_admitted:")+assessment.reason,now);
      if(assessment.invalidate||assessment.terminal){legacy_sequence_complete_=false;invalidate_legacy_ready_locked(assessment.reason,now);anchor_.known={false,false};history_.clear();ready_history_.clear();publication_history_.clear();normal_complete_=false;}
      if(assessment.terminal)unusable_locked("legacy_producer_changed",now);
      else if(assessment.invalidate)invalidate_locked();
      sink_->add({{"type","legacy_admission_rejected"},{"input_commit_ordinal",input_commit_ordinal_},{"schema","p1-shadow-legacy-admission-v1"},{"reason",assessment.reason},{"processed_ns",now},{"sequence",m.sequence},
        {"received_count",legacy_received_},{"admitted_count",legacy_admitted_},{"expected_identity",expected_legacy_identity_.json()},
        {"observed_identity",p1::shadow::observed_identity(m)},{"history_invalidated",assessment.invalidate||assessment.terminal},{"terminal",assessment.terminal}});
      return;
    }
    if(worker_unusable_){sink_->add({{"type","legacy_admission_rejected"},{"input_commit_ordinal",input_commit_ordinal_},{"schema","p1-shadow-legacy-admission-v1"},{"reason","run_terminal"},{"processed_ns",now},{"sequence",m.sequence},
      {"received_count",legacy_received_},{"admitted_count",legacy_admitted_},{"expected_identity",expected_legacy_identity_.json()},{"observed_identity",p1::shadow::observed_identity(m)},{"history_invalidated",false},{"terminal",true}});return;}
    if(adapter_){auto r=adapter_->observe(m,now);sink_->add({{"type","adapter_applied_observed"},{"sequence",m.sequence},{"processed_ns",now},{"reason",r.reason},{"evidence",adapter_->evidence()}});if(!r){unusable_locked("adapter_applied:"+r.reason,now);return;}}
    legacy_producer_=m.producer_instance_id;++legacy_admitted_;if(!legacy_first_sequence_)legacy_first_sequence_=m.sequence;
    if(legacy_sequence_&&m.sequence!=legacy_sequence_+1){legacy_sequence_complete_=false;invalidate_legacy_ready_locked("sequence_gap",now);history_.clear();ready_history_.clear();publication_history_.clear();anchor_.known={false,false};invalidate_locked();sink_->add({{"type","legacy_history_reset"},{"input_commit_ordinal",input_commit_ordinal_},{"reason","sequence_gap"},{"processed_ns",now},{"expected_sequence",legacy_sequence_+1},{"sequence",m.sequence}});}
    legacy_sequence_=m.sequence;
    for(int i=0;i<2;++i){const bool success=i?m.right_publish_success:m.left_publish_success;const int64_t time=i?m.right_publish_start_steady_ns:m.left_publish_start_steady_ns;const int64_t sim=i?m.right_sim_time_ns:m.left_sim_time_ns;
      if(!success||time<=0||time>now||(anchor_.known[i]&&time<=anchor_.time[i])){anchor_.known[i]=false;normal_complete_=false;invalidate_locked();continue;}
      anchor_.n[i]=m.final_n[i];anchor_.seq[i]=m.sequence;anchor_.time[i]=time;anchor_.known[i]=true;push_history_locked({sim,i,m.final_n[i]});push_publication_locked({i,m.sequence,time,m.final_n[i],anchor_.known[i]});
      ready_history_.push_back({sim,i,m.final_n[i],m.sequence,time});while(ready_history_.size()>c_.at("history_capacity").get<size_t>())ready_history_.pop_front();
    }
    legacy_anchor_sim_ns_={m.left_sim_time_ns,m.right_sim_time_ns};legacy_pair_publish_end_ns_={m.left_publish_end_steady_ns,m.right_publish_end_steady_ns};legacy_pair_processed_ns_=now;
    legacy_ready_projection_complete_=legacy_ready_projection_complete_&&m.clock_status.size()<=128&&m.control_source.size()<=128&&m.publish_error.size()<=128;
    const p1::Json admitted={{"schema_version",m.schema_version},{"run_id",m.run_id},{"producer_instance_id",m.producer_instance_id},{"baseline_id",m.baseline_id},{"config_hash",m.config_hash},
      {"sequence",m.sequence},{"clock_epoch",m.clock_epoch},{"sim_time_ns",m.sim_time_ns},{"clock_receive_steady_ns",m.clock_receive_steady_ns},{"clock_age_ns",m.clock_age_ns},
      {"clock_status",m.clock_status.substr(0,128)},{"steady_clock_domain",m.steady_clock_domain},{"cycle_sequence",m.cycle_sequence},{"control_source",m.control_source.substr(0,128)},
      {"event_semantics",m.event_semantics},{"requested_known",m.requested_known},{"requested_n",m.requested_n},{"final_n",m.final_n},{"left_publish_success",m.left_publish_success},{"right_publish_success",m.right_publish_success},
      {"left_publish_start_steady_ns",m.left_publish_start_steady_ns},{"left_publish_end_steady_ns",m.left_publish_end_steady_ns},{"right_publish_start_steady_ns",m.right_publish_start_steady_ns},{"right_publish_end_steady_ns",m.right_publish_end_steady_ns},
      {"left_sim_time_ns",m.left_sim_time_ns},{"right_sim_time_ns",m.right_sim_time_ns},{"left_clock_epoch",m.left_clock_epoch},{"right_clock_epoch",m.right_clock_epoch},{"left_clock_age_ns",m.left_clock_age_ns},{"right_clock_age_ns",m.right_clock_age_ns},
      {"map_scale",m.map_scale},{"lower_n",m.lower_n},{"upper_n",m.upper_n},{"previous_anchor_known",m.previous_anchor_known},{"previous_final_n",m.previous_final_n},
      {"plant_acceptance_observed",m.plant_acceptance_observed},{"force_measured",m.force_measured},{"execution_atomicity_proven",m.execution_atomicity_proven},{"publish_error",m.publish_error.substr(0,128)}};
    sink_->add({{"type","legacy_anchor"},{"input_commit_ordinal",input_commit_ordinal_},{"producer",m.producer_instance_id},{"run_id",m.run_id},{"sequence",m.sequence},{"final_n",m.final_n},{"known",anchor_.known},{"publish_ns",anchor_.time},{"clock_epoch",m.clock_epoch},{"processed_ns",now},{"received_count",legacy_received_},{"admitted_count",legacy_admitted_},
      {"applied",admitted},{"applied_text_truncated",m.clock_status.size()>128||m.control_source.size()>128||m.publish_error.size()>128}});
    try_legacy_ready_locked(p1::monotonic_ns());
    if(info&&controlled_phase_state_&&!adapter_->closing()&&owner_peer_->alive()){
      controlled_phase::Pair pair;pair.identity=controlled_owner_identity_;pair.sequence=m.sequence;pair.command=m.final_n;
      pair.start={m.left_publish_start_steady_ns,m.right_publish_start_steady_ns};pair.end={m.left_publish_end_steady_ns,m.right_publish_end_steady_ns};pair.succeeded={m.left_publish_success,m.right_publish_success};
      const auto phase_reason=controlled_phase_state_->observe_applied(pair,controlled_transport(*info,controlled_applied_binding_,*owner_peer_),now);
      sink_->add({{"type","controlled_phase_applied"},{"sequence",m.sequence},{"observed_ns",now},{"reason",phase_reason},{"hold_input_changed",controlled_phase_state_->hold_input_changed()},{"command_n",m.final_n}});
      if(!phase_reason.empty())unusable_locked("controlled_phase_applied:"+phase_reason,now);
      else maybe_enqueue_controlled_locked(p1::monotonic_ns());
    }
  }
  controlled_phase::TransportObservation controlled_transport(const rclcpp::MessageInfo &info,const controlled_phase::PeerBinding &binding,const c36_owned::OwnedPeer &peer) const {
    controlled_phase::TransportObservation out;const auto &m=info.get_rmw_message_info();std::copy(std::begin(m.publisher_gid.data),std::end(m.publisher_gid.data),out.actual_gid.begin());
    out.pinned_pid=binding.pid;out.pinned_process_start_ticks=binding.process_start_ticks;out.registered_fastrtps=m.publisher_gid.implementation_identifier&&std::strcmp(m.publisher_gid.implementation_identifier,"rmw_fastrtps_cpp")==0;out.from_intra_process=m.from_intra_process;out.pidfd_alive=peer.alive();return out;
  }
  // Notification after the reference dependency commit; it grants no new
  // authorization. All original peer/eligible/phase/Applied/deadline checks
  // remain in the existing enqueue path and the final preparation completion.
  void retry_reference_pair_locked(const char *trigger,bool input_valid){
    if(!input_valid||!controlled_phase_state_||!controlled_phase_state_->awaiting())return;
    const auto start=p1::monotonic_ns();
    maybe_enqueue_controlled_locked(start);
    sink_->add({{"type","reference_pair_retry"},{"policy","authenticated_phase_reference_pair_completion_v1"},{"trigger",trigger},{"input_commit_ordinal",input_commit_ordinal_},{"path_sequence",ref_->path_sequence},{"profile_sequence",ref_->profile_sequence},{"path_stamp_ns",int64_t(ref_->path_stamp.first)*1000000000LL+ref_->path_stamp.second},{"profile_stamp_ns",int64_t(ref_->profile_stamp.first)*1000000000LL+ref_->profile_stamp.second},{"started_ns",start},{"completed_ns",p1::monotonic_ns()},{"phase_still_awaiting",controlled_phase_state_->awaiting()},{"froze",!controlled_phase_state_->awaiting()},{"stage_qualified",false}});
  }
  void maybe_enqueue_controlled_locked(int64_t now){
    if(!controlled_phase_state_||stopping_||worker_unusable_||!worker_valid_||sink_->failed()||!legacy_measurement_eligible_||adapter_->closing()||!owner_peer_->alive())return;
    auto next=snapshot_locked(now);if(!eligible(next,next.freeze).empty())return;
    auto grant=controlled_phase_state_->freeze(job_id_+1,now);if(!grant)return;
    if(grant->job.target_tick!=current_tick_+1||grant->applied.sequence!=legacy_sequence_||grant->applied.command!=anchor_.n){unusable_locked("controlled_phase_native_anchor_or_tick_differs",now);return;}
    bool busy=false;{std::lock_guard<std::mutex> q(prep_mutex_);busy=bool(pending_);if(!busy){pending_=Preparation{next,current_tick_,grant->job.origin_ns};prep_cv_.notify_one();}}
    if(busy){unusable_locked("controlled_phase_pending_slot_busy",now);return;}
    sink_->add({{"type","controlled_phase_freeze"},{"freeze_ns",now},{"tick",current_tick_},{"target_tick",grant->job.target_tick},{"planned_ns",grant->job.origin_ns},{"deadline_ns",grant->job.deadline_ns},{"target_ns",grant->job.target_ns},{"applied_sequence",grant->applied.sequence},{"command_n",grant->applied.command},{"decision_sequence",grant->commitment.decision_sequence},{"phase_applied_sequence",grant->commitment.applied_sequence},{"phase_emitted_ns",grant->commitment.emitted_ns},{"held_until_ns",grant->commitment.held_until_ns},{"phase_command_n",grant->commitment.command},{"phase_start_ns",grant->commitment.start},{"phase_end_ns",grant->commitment.end},{"phase_contract","unchanged_150ms_ready_200ms_target"},{"stage_qualified",false}});
    if(v1_enabled_&&!v1_armed_&&v1_await_sequence_&&grant->commitment.decision_sequence==v1_await_sequence_){
      v1_armed_=sink_->arm_v1_saturation();
      sink_->add({{"type","diagnostic_v1_armed_after_ack"},{"decision_sequence",v1_await_sequence_},{"applied_sequence",grant->applied.sequence},{"phase_emitted_ns",grant->commitment.emitted_ns},{"armed",v1_armed_},{"observed_ns",p1::monotonic_ns()}});
    }
  }
  void receive_controlled_phase(const std_msgs::msg::String &m,const rclcpp::MessageInfo &info){
    const auto entered=p1::monotonic_ns();std::lock_guard<std::mutex> lock(mutex_);const auto sequence=++raw_callback_sequences_["/p1/controlled_owner_phase"];
    p1::Json event={{"type","controlled_phase_callback"},{"callback_sequence",sequence},{"entry_ns",entered},{"actual_bytes",m.data.size()},{"raw_input",nullptr},{"expected_gid",controlled_owner_phase_peer_->expected_gid()},{"reason",""},{"accepted",false}};
    const auto authentication=controlled_owner_phase_peer_->callback_reason(info);event["authentication_reason"]=authentication;
    if(!authentication.empty()||m.data.empty()||m.data.size()>4096){event["reason"]=authentication.empty()?"phase_resource_domain":authentication;sink_->add(std::move(event));return;}
    event["raw_input"]=p1_observation_v4::raw_input(m,info,"/p1/controlled_owner_phase","std_msgs/msg/String",sequence);
    try{
      const auto j=c36_owned::detail::strict_json(m.data);const std::set<std::string> keys={"schema","run_id","boot_id","contract_sha256","baseline_id","producer_instance_id","decision_sequence","tick","planned_ns","applied_sequence","command_n","start_ns","end_ns","held_until_ns","emitted_ns","stage_qualified","execute_qualified"};
      p1_owned::require(j.size()==keys.size(),"phase exact field population");for(auto it=j.begin();it!=j.end();++it)p1_owned::require(keys.count(it.key())==1,"phase unknown field");
      p1_owned::require(j.at("schema")=="p1-controlled-owner-phase-v1","phase schema");
      c36_owned::detail::bool_field(j,"stage_qualified",false);c36_owned::detail::bool_field(j,"execute_qualified",false);
      controlled_phase::Commitment c;c.identity={c36_owned::detail::string_field(j,"run_id",128),c36_owned::detail::string_field(j,"boot_id",64),c36_owned::detail::string_field(j,"contract_sha256",64),c36_owned::detail::string_field(j,"producer_instance_id",64),c36_owned::detail::string_field(j,"baseline_id",64)};
      c.decision_sequence=c36_owned::detail::uint_field(j,"decision_sequence",UINT64_MAX-1);c.tick=c36_owned::detail::uint_field(j,"tick",UINT64_MAX-1);c.applied_sequence=c36_owned::detail::uint_field(j,"applied_sequence",UINT64_MAX-1);
      c.planned_ns=c36_owned::detail::uint_field(j,"planned_ns",INT64_MAX);c.held_until_ns=c36_owned::detail::uint_field(j,"held_until_ns",INT64_MAX);c.emitted_ns=c36_owned::detail::uint_field(j,"emitted_ns",INT64_MAX);
      for(const auto &key:{"command_n","start_ns","end_ns"})p1_owned::require(j.at(key).is_array()&&j.at(key).size()==2,"phase pair array");
      for(size_t ch=0;ch<2;++ch){p1_owned::require(j.at("command_n")[ch].is_number()&&!j.at("command_n")[ch].is_boolean()&&std::isfinite(j.at("command_n")[ch].get<double>()),"phase command finite");c.command[ch]=j.at("command_n")[ch].get<double>();
        for(const auto &key:{"start_ns","end_ns"})p1_owned::require(j.at(key)[ch].is_number_integer()&&!j.at(key)[ch].is_boolean()&&(!j.at(key)[ch].is_number_unsigned()||j.at(key)[ch].get<uint64_t>()<=INT64_MAX)&&j.at(key)[ch].get<int64_t>()>0,"phase integer call timestamp");c.start[ch]=j.at("start_ns")[ch].get<int64_t>();c.end[ch]=j.at("end_ns")[ch].get<int64_t>();}
      const auto now=p1::monotonic_ns();const auto reason=controlled_phase_state_->observe_commitment(c,controlled_transport(info,controlled_phase_binding_,*controlled_owner_phase_peer_),now);
      event["reason"]=reason;event["accepted"]=reason.empty();event["observed_ns"]=now;event["phase"]=j;
      if(reason.empty())maybe_enqueue_controlled_locked(p1::monotonic_ns());
    }catch(const std::exception &e){event["reason"]=e.what();}
    event["processed_ns"]=p1::monotonic_ns();sink_->add(std::move(event));
  }
  void push_publication_locked(const p1::PublicationEvent & e){publication_history_.push_back(e);while(publication_history_.size()>c_.at("history_capacity").get<size_t>())publication_history_.pop_front();}
  void anchor_evidence_locked(const p1::Ticket & t,const p1::Decision & d){
    p1::Json entries=p1::Json::array();
    for(const auto & e:publication_history_)if(e.sequence>=t.anchor.seq[e.channel]&&e.sequence<=anchor_.seq[e.channel])entries.push_back({{"channel",e.channel},{"sequence",e.sequence},{"publish_ns",e.publish_ns},{"n",e.n},{"known",e.known}});
    sink_->add({{"type","anchor_validation"},{"sequence",d.sequence},{"job_id",t.id},{"mode",mode_},{"producer",legacy_producer_},{"run_id",legacy_run_},{"clock_epoch",version_.epoch},{"check_ns",d.activation_commit_ns},{"expected_n",t.anchor.n},{"expected_sequence",t.anchor.seq},{"expected_publish_ns",t.anchor.time},{"expected_known",t.anchor.known},{"actual_n",anchor_.n},{"actual_sequence",anchor_.seq},{"actual_publish_ns",anchor_.time},{"actual_known",anchor_.known},{"entries",entries},{"history_reason",p1::publication_history_check(t.anchor,anchor_,publication_history_)},{"decision_reason",d.reason},{"accepted",d.candidate_accepted}});
  }
  void push_history_locked(const usv_mpc::HeldInputEvent & e){if(!history_.empty()&&e.sim_ns<history_.back().sim_ns){invalidate_legacy_ready_locked("held_history_time_regression",p1::monotonic_ns());history_.clear();ready_history_.clear();publication_history_.clear();anchor_.known={false,false};invalidate_locked();return;}history_.push_back(e);while(history_.size()>c_.at("history_capacity").get<size_t>())history_.pop_front();}
  // Observation only: copy raw final provenance under the existing commit lock.
  // Inactive IMU values remain raw here because the original input-change gate
  // still compares its sequence; the canonical Decision keeps its zero mask.
  void capture_final_source_locked(Snapshot &s,int64_t commit_ns){
    // Full immutable observation from the original final commit mutex scope.
    // Only observation fields are added; no gate or policy reads are reused.
    s=snapshot_locked(commit_ns);
  }
  static p1::Json captured_candidate_json(const std::shared_ptr<const p1::Candidate> &cand,bool ticket_present){
    p1::Json out={{"ticket_present",ticket_present},{"candidate_present",bool(cand)},{"pair",ticket_present&&bool(cand)},
      {"digest_semantics","actual immutable Candidate reserialized CDR integrity; decoded full fields establish payload identity; not network bytes or pointer address"}};
    if(!cand){out["cdr_hex"]=nullptr;out["cdr_bytes"]=nullptr;out["cdr_sha256"]=nullptr;out["job_id"]=nullptr;out["worker_instance"]=nullptr;out["first_control"]=nullptr;return out;}
    // The actual captured immutable object is read here after all business gates.
    rclcpp::Serialization<p1::Candidate> serializer;rclcpp::SerializedMessage serialized;
    serializer.serialize_message(cand.get(),&serialized);const auto &cdr=serialized.get_rcl_serialized_message();
    p1_owned::require(cdr.buffer_length>0&&cdr.buffer_length<=1048576,"captured Candidate CDR outside observation bound");
    const std::string bytes(reinterpret_cast<const char *>(cdr.buffer),cdr.buffer_length);
    out["cdr_bytes"]=cdr.buffer_length;out["cdr_sha256"]=p1_owned::sha256_bytes(bytes);out["cdr_hex"]=p1_owned::hex(cdr.buffer,cdr.buffer_length);
    out["job_id"]=cand->job.job_id;out["worker_instance"]=cand->worker_instance;out["first_control"]=cand->first_control;
    return out;
  }
  bool predict(Snapshot & s,int64_t target_sim){Eigen::Vector2d initial(s.anchor.n[0],s.anchor.n[1]);std::array<bool,2> found{false,false};for(auto & e:s.history)if(e.sim_ns<=s.odom_stamp){initial[e.channel]=e.value;found[e.channel]=true;}
    if(mode_!="no_output"&&(!found[0]||!found[1]))return false;return usv_mpc::propagate_publisher_nominal(s.state,s.odom_stamp,target_sim,initial,s.history,params_.hydro);}
  void candidate(const p1::Candidate & m,const p1::Json *raw=nullptr,uint64_t received_count=0){auto resource=p1::check_candidate_resources(m,resources_);if(!resource){sink_->add({{"type","resource_rejected"},{"interface","candidate"},{"job_id",m.job.job_id},{"reason",resource.reason},{"field",resource.field},{"observed",resource.observed},{"limit",resource.limit},{"receive_ns",p1::monotonic_ns()},{"accepted_registration",false}});return;}auto immutable=std::make_shared<const p1::Candidate>(m);auto reason=p1::valid_job(m.job,run_,boot_,hash_,nominal_,worker_instance_);if(reason.empty()&&(m.worker_instance!=worker_instance_||m.backend!="acados"))reason="foreign_worker";
    if(reason.empty()&&(!m.success||!m.prediction_available||!m.solver_invoked))reason="solver_failed";
    if(reason.empty()&&(!p1::finite_array(m.x_prediction)||!p1::finite_array(m.u_prediction)||!p1::finite_array(m.first_control)||!std::isfinite(m.backend_ms)||m.backend_ms<0||m.solve_end_ns<m.solve_start_ns))reason="nonfinite_or_timing";
    if(reason.empty())for(int i=0;i<2;++i)if(std::abs(m.first_control[i]-m.u_prediction[i])>1e-8)reason="first_control_mismatch";
    if(reason.empty())for(int i=0;i<6;++i)if(std::abs(m.x_prediction[i]-m.job.target_state[i])>1e-7)reason="prediction_initial_mismatch";
    std::lock_guard<std::mutex> l(mutex_);auto expected=std::find_if(jobs_.begin(),jobs_.end(),[&](const p1::Job & j){return j.job_id==m.job.job_id;});
    if(reason.empty()&&(expected==jobs_.end()||p1::job_json(*expected)!=p1::job_json(m.job)))reason="job_echo_mismatch";
    auto now=p1::monotonic_ns();if(reason.empty()&&!(m.job.freeze_steady_ns<=m.worker_receive_ns&&m.worker_receive_ns<=m.solve_start_ns&&m.solve_start_ns<=m.solve_end_ns&&m.solve_end_ns<=now))reason="native_timing_order";p1::Ticket t;t.id=m.job.job_id;t.target=m.job.target_tick;t.origin=m.job.tick_origin_steady_ns;t.deadline=m.job.deadline_steady_ns;t.target_ns=m.job.target_steady_ns;t.version={m.job.task_generation,m.job.model_generation,m.job.config_generation,m.job.schedule_generation,m.job.clock_epoch};t.anchor={m.job.anchor_n,m.job.anchor_sequence,m.job.anchor_publish_ns,m.job.anchor_known};t.prediction=m.job.target_state;
    check_worker_locked(now);if(reason.empty()&&(worker_unusable_||stopping_||sink_->failed()))reason="run_unusable";
    if(reason.empty()&&adapter_&&(!owner_peer_->alive()||adapter_->closing()))reason="adapter_owner_not_open";
    if(reason.empty())reason=admission_.register_ready(t,current_tick_,now,version_);
    if(reason.empty()){candidate_=std::move(immutable);now=p1::monotonic_ns();if(adapter_){auto r=adapter_->ready(m.job,m.first_control,now);sink_->add({{"type","adapter_candidate_ready"},{"job_id",m.job.job_id},{"commit_ns",now},{"preliminary_ready_ns",now},{"reason",r.reason},{"evidence",adapter_->evidence()}});if(!r)reason="adapter_ready:"+r.reason;}
#ifdef P1_C36_COMPLETION_TEST
      if(c36_before_ready_completion_)c36_before_ready_completion_();
#endif
      // Re-read after bridge and diagnostic work. Both slots use the same final
      // completion point; neither inherits the preliminary adapter ready time.
      now=p1::monotonic_ns();check_worker_locked(now);
      if(reason.empty()&&(stopping_||stop_requested||worker_unusable_||!worker_valid_||sink_->failed()))reason="run_unusable_at_ready_completion";
      if(reason.empty()&&adapter_&&(!owner_peer_->alive()||adapter_->closing()))reason="adapter_owner_not_open_at_ready_completion";
      if(reason.empty()&&!admission_.finalize_ready(t.id,now))reason="late_registration_completion";
      if(reason.empty()&&adapter_){auto r=adapter_->finalize_ready_completion(t.id,now);if(!r)reason="adapter_ready_completion:"+r.reason;}
      if(!reason.empty()){admission_.invalidate();candidate_.reset();if(adapter_)adapter_->cancel(m.job.target_tick,p1::monotonic_ns());}}
    sink_->add({{"type","candidate_registration"},{"raw_input",raw?*raw:p1::Json(nullptr)},{"callback_sequence",raw?raw->at("callback_sequence"):p1::Json(0)},{"received_count",received_count},{"job",p1::job_json(m.job)},{"ready_commit_ns",now},{"accepted_registration",reason.empty()},{"reason",reason},{"solve_start_ns",m.solve_start_ns},{"solve_end_ns",m.solve_end_ns},{"worker_instance",m.worker_instance},{"first_control",m.first_control}});
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
    // Preparation is tentative. The fixed epoch is committed only below,
    // after the existing final submission completion guards have succeeded.
    task_time_reference::Epoch epoch_snapshot;
    {std::lock_guard<std::mutex> lock(mutex_);epoch_snapshot=reference_epoch_;}
    const task_time_reference::Binding reference_binding{{s.version.task,s.version.model,s.version.config,s.version.schedule,s.version.epoch},run_,boot_,hash_,nominal_,s.path_fingerprint,s.profile_fingerprint};
    auto task_reference=epoch_snapshot.propose(reference_binding,target_sim,s.state,*s.ref);
    if(!task_reference.valid){std::lock_guard<std::mutex> lock(mutex_);sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"reason","task_time_reference_policy_rejected"},{"policy_reason",task_reference.reason},{"reference_mode",task_time_reference::policy},{"processed_ns",p1::monotonic_ns()}});if(reference_epoch_.active()){reference_epoch_.invalidate(task_reference.reason);unusable_locked("task_time_reference:"+task_reference.reason,p1::monotonic_ns());}continue;}
    const auto &projected=task_reference.geometric;
    auto ref=task_reference.reference;usv_mpc::ReferenceMetadata meta;
    meta.horizon_steps=20;meta.prediction_dt=.2;meta.path_received_sequence=s.ref->path_sequence;meta.profile_received_sequence=s.ref->profile_sequence;
    meta.path_stamp_ns=int64_t(s.ref->path_stamp.first)*1000000000LL+s.ref->path_stamp.second;meta.profile_stamp_known=true;meta.profile_stamp_ns=int64_t(s.ref->profile_stamp.first)*1000000000LL+s.ref->profile_stamp.second;
    meta.path_size=s.ref->path.size();meta.profile_size=s.ref->profile.size();meta.configured_start_offset=0;meta.effective_start_offset=0;
    meta.profile_synced=true;meta.profile_sync_reason="exact_pair_stamps_and_complete_valid_profile";meta.reference_mode=task_time_reference::policy;meta.profile_t0_known=true;meta.profile_t0=task_reference.profile_t0;meta.start_index=task_reference.start_index;
    // Preserve the historical nearest_index field's meaning as an observation;
    // actual sampling uses the separately reported continuous segment/fraction.
    double closest=std::numeric_limits<double>::infinity();for(size_t k=0;k<s.ref->path.size();++k){const auto &point=s.ref->path[k];const double distance=std::hypot(point[0]-s.state[0],point[1]-s.state[1]);if(distance<closest){closest=distance;meta.nearest_index=int(k);}}
    const p1::Json projection={{"segment",projected.segment},{"fraction",projected.fraction},{"profile_t0",projected.profile_t0},{"projection_x",projected.projection_x},{"projection_y",projected.projection_y},{"squared_distance",projected.squared_distance},{"stationary",projected.stationary}};
    p1::Job j;j.schema_version="p1-solve-job-v1";j.run_id=run_;j.boot_id=boot_;j.contract_hash=hash_;j.nominal_hash=nominal_;j.target_tick=p.tick+1;j.task_generation=s.version.task;j.model_generation=s.version.model;j.config_generation=s.version.config;j.schedule_generation=s.version.schedule;j.clock_epoch=s.version.epoch;j.tick_origin_steady_ns=p.origin;j.freeze_steady_ns=s.freeze;j.deadline_steady_ns=p.origin+p1::DEADLINE;j.target_steady_ns=p.origin+p1::T;j.target_sim_ns=target_sim;j.odom_stamp_ns=s.odom_stamp;j.imu_stamp_ns=s.mixed?s.imu_stamp:0;j.odom_receive_ns=s.odom_receive;j.imu_receive_ns=s.mixed?s.imu_receive:0;j.odom_sequence=s.odom_seq;j.imu_sequence=s.mixed?s.imu_seq:0;j.r_from_imu=s.mixed;j.horizon_steps=20;j.prediction_dt=.2;std::copy(x.data(),x.data()+6,j.frozen_state.begin());std::copy(s.state.data(),s.state.data()+6,j.target_state.begin());std::copy(ref.data(),ref.data()+126,j.reference.begin());j.frozen_clock_sim_ns=s.sim;j.frozen_clock_receive_ns=s.clock_receive;j.assumed_rtf=1.0;j.anchor_source=s.anchor_source;j.anchor_producer=s.anchor_producer;j.anchor_run_id=s.anchor_run;for(auto & e:s.history){j.history_sim_ns.push_back(e.sim_ns);j.history_channel.push_back(e.channel);j.history_n.push_back(e.value);}j.anchor_n=s.anchor.n;j.anchor_sequence=s.anchor.seq;j.anchor_publish_ns=s.anchor.time;j.anchor_known=s.anchor.known;j.reset_warmstart=std::abs(usv_mpc::normalize_angle(s.state[2]-ref(2,0)))>M_PI*.75;
    int64_t submit_commit_ns;p1::Json reference_epoch_source;
    {std::lock_guard<std::mutex> l(mutex_);check_worker_locked(p1::monotonic_ns());submit_commit_ns=p1::monotonic_ns();std::string rejected;
      if(stopping_)rejected="shutdown_before_submit";else if(worker_unusable_)rejected="worker_unusable_before_submit";else if(!worker_valid_)rejected="worker_unvalidated_before_submit";else if(sink_->failed())rejected="source_failed_before_submit";else if(adapter_&&adapter_->closing())rejected="driver_close_requested_before_submit";else if(!(s.version==version_))rejected="version_changed_before_submit";else if(current_tick_!=p.tick)rejected="tick_changed_before_submit";else if(submit_commit_ns>j.deadline_steady_ns)rejected="deadline_expired_before_submit";
      if(!rejected.empty()){sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"preparation_tick",p.tick},{"current_tick",current_tick_},{"deadline_ns",j.deadline_steady_ns},{"processed_ns",submit_commit_ns},{"reason",rejected}});continue;}j.worker_instance=worker_instance_;auto resource=p1::check_job_resources(j,resources_);if(!resource){sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"reason",resource.reason},{"field",resource.field},{"observed",resource.observed},{"limit",resource.limit}});continue;}j.job_id=++job_id_;
      if(adapter_){if(!owner_peer_->alive()){sink_->add({{"type","job_not_submitted"},{"job_id",j.job_id},{"reason","adapter_owner_process_not_live"}});continue;}auto r=adapter_->submit(j,submit_commit_ns);sink_->add({{"type","adapter_job_import"},{"job_id",j.job_id},{"freeze_ns",j.freeze_steady_ns},{"submit_ns",submit_commit_ns},{"import_linearization_ns",submit_commit_ns},{"reason",r.reason},{"evidence",adapter_->evidence()}});if(!r){sink_->add({{"type","job_not_submitted"},{"job_id",j.job_id},{"reason","adapter_submit:"+r.reason}});continue;}}
      // Imported component slots and diagnostics do not authorize DDS submit.
      // Only this fresh completion point, inside the invalidation lock, does.
      submit_commit_ns=p1::monotonic_ns();check_worker_locked(submit_commit_ns);
      if(stopping_||stop_requested)rejected="shutdown_at_submit_completion";else if(worker_unusable_||!worker_valid_)rejected="worker_unusable_at_submit_completion";else if(sink_->failed())rejected="source_failed_at_submit_completion";else if(adapter_&&(adapter_->closing()||!owner_peer_->alive()))rejected="adapter_owner_not_open_at_submit_completion";else if(!(s.version==version_))rejected="version_changed_at_submit_completion";else if(current_tick_!=p.tick)rejected="tick_changed_at_submit_completion";else if(submit_commit_ns>j.deadline_steady_ns)rejected="deadline_expired_at_submit_completion";
      if(!rejected.empty()){if(adapter_)adapter_->cancel(j.target_tick,p1::monotonic_ns());sink_->add({{"type","job_not_submitted"},{"job_id",j.job_id},{"target_tick",j.target_tick},{"deadline_ns",j.deadline_steady_ns},{"processed_ns",submit_commit_ns},{"reason",rejected}});continue;}
      if(!reference_epoch_.commit(task_reference,j.job_id,submit_commit_ns)){if(adapter_)adapter_->cancel(j.target_tick,p1::monotonic_ns());unusable_locked("reference_epoch_commit_failed",p1::monotonic_ns());sink_->add({{"type","job_not_submitted"},{"job_id",j.job_id},{"reason","reference_epoch_commit_failed"}});continue;}
      const auto &epoch=*reference_epoch_.anchor();
      reference_epoch_source={{"policy",task_time_reference::policy},{"epoch_policy",task_time_reference::epoch_policy},{"first_job_id",epoch.first_job_id},{"first_target_sim_ns",epoch.first_target_sim_ns},{"initial_profile_t0",epoch.initial_profile_t0},{"epoch_submit_commit_ns",epoch.commit_ns},{"current_target_sim_ns",target_sim},{"profile_t0",task_reference.profile_t0},{"task_generation",s.version.task},{"model_generation",s.version.model},{"config_generation",s.version.config},{"schedule_generation",s.version.schedule},{"clock_epoch",s.version.epoch},{"run_id",run_},{"boot_id",boot_},{"contract_hash",hash_},{"nominal_hash",nominal_},{"path_fingerprint",s.path_fingerprint},{"profile_fingerprint",s.profile_fingerprint}};
      if(task_reference.first)sink_->add({{"type","reference_epoch_committed"},{"job_id",j.job_id},{"submit_commit_ns",submit_commit_ns},{"reference_epoch",reference_epoch_source},{"first_job_G_T_reference_bit_identical",ref==projected.reference}});
      jobs_.push_back(j);while(jobs_.size()>8)jobs_.pop_front();
      p1::WitnessSubmit row{};row.job_id=j.job_id;row.tick=p.tick;row.target_tick=j.target_tick;row.task_generation=j.task_generation;row.model_generation=j.model_generation;row.config_generation=j.config_generation;row.schedule_generation=j.schedule_generation;row.clock_epoch=j.clock_epoch;row.commit_ns=submit_commit_ns;row.failed=sink_->failed();row.stopping=stopping_;witness_->record_submit(row);
    }
    // Submission commits share the invalidation mutex; DDS remains outside it.
    // A previously committed publication may finish after a terminal observation.
    if(!sink_->add({{"type","job"},{"job",p1::job_json(j)},{"input_provenance",{{"schema","p1-job-input-selection-v2"},{"input_commit_ordinal",s.input_commit_ordinal},{"ref_selection",p1::d0::source_json(s).at("ref_selection")},{"odom_sequence",s.odom_seq},{"imu_sequence_raw",s.imu_seq},{"r_from_imu",s.mixed},{"path_sequence",s.ref->path_sequence},{"profile_sequence",s.ref->profile_sequence},{"path_stamp_ns",int64_t(s.ref->path_stamp.first)*1000000000LL+s.ref->path_stamp.second},{"profile_stamp_ns",int64_t(s.ref->profile_stamp.first)*1000000000LL+s.ref->profile_stamp.second},{"clock_sim_ns",s.sim},{"clock_receive_ns",s.clock_receive},{"rtf",s.rtf},{"rtf_valid",s.rtf_valid},{"paused",s.paused},{"freeze_ns",s.freeze}}},{"reference_mode",meta.reference_mode},{"reference_projection",projection},{"reference_epoch",reference_epoch_source},{"configured_start_offset",meta.configured_start_offset},{"effective_start_offset",meta.effective_start_offset},{"profile_t0",meta.profile_t0},{"nearest_index",meta.nearest_index},{"start_index",meta.start_index},{"submit_commit_ns",submit_commit_ns},{"publish_start_ns",p1::monotonic_ns()}}))continue;
    const auto publish_start=p1::monotonic_ns();try{job_pub_->publish(j);sink_->add({{"type","job_publish_result"},{"job_id",j.job_id},{"publish_start_ns",publish_start},{"publish_end_ns",p1::monotonic_ns()},{"success",true}});}catch(...){sink_->add({{"type","job_publish_result"},{"job_id",j.job_id},{"publish_start_ns",publish_start},{"publish_end_ns",p1::monotonic_ns()},{"success",false}});std::lock_guard<std::mutex> l(mutex_);unusable_locked("job_publication_failed",p1::monotonic_ns());}
  }}
  void publish(p1::Decision & d){
    if(mode_!="execute")return;
    p1::Anchor old;{std::lock_guard<std::mutex> l(mutex_);old=anchor_;}
    d.previous_anchor_known=old.known;d.previous_n=old.n;d.previous_publish_ns=old.time;
    const p1::publication::Policy policy{c_.at("publish_budget_ns").get<int64_t>(),c_.at("publish_gap_ns").get<int64_t>(),limits_.rho};
    const auto result=p1::publication::publish_pair(d.final_n,old,policy,
      []{return p1::monotonic_ns();},
      [&](int i,int64_t start){d.publish_start_ns[i]=start;std::lock_guard<std::mutex> l(mutex_);d.publish_sim_ns[i]=sim_;d.publish_epoch[i]=version_.epoch;d.publish_clock_age_ns[i]=start-clock_receive_;},
      [&](int i,double n){std_msgs::msg::Float64 message;message.data=n;(i?right_:left_)->publish(message);},
      [&](int i,const p1::publication::CallResult &call){
        d.publish_end_ns[i]=call.end_ns;d.publish_success[i]=call.returned;
        std::lock_guard<std::mutex> l(mutex_);
        p1::publication::apply_channel_result(anchor_,i,d.final_n[i],call);
        if(call.returned){push_history_locked({d.publish_sim_ns[i],i,d.final_n[i]});push_publication_locked({i,anchor_.seq[i],call.start_ns,d.final_n[i],anchor_.known[i]});}
        else{normal_complete_=false;worker_unusable_=true;invalidate_locked();}
      });
    d.rho_available=result.rho_available;
    if(result.timing_failed()){normal_complete_=false;worker_unusable_=true;}
  }
  static p1::Json decision_json(const p1::Decision & d){return {{"type","decision"},{"schema",d.schema_version},{"run_id",d.run_id},{"boot_id",d.boot_id},{"contract_hash",d.contract_hash},{"worker_instance",d.worker_instance},{"model_generation",d.model_generation},{"config_generation",d.config_generation},{"mode",d.mode},{"sequence",d.sequence},{"tick",d.tick},{"job_id",d.job_id},{"task_generation",d.task_generation},{"schedule_generation",d.schedule_generation},{"epoch",d.clock_epoch},{"planned_ns",d.tick_planned_ns},{"start_ns",d.tick_start_ns},{"cutoff_commit_ns",d.cutoff_commit_ns},{"ready_commit_ns",d.candidate_ready_commit_ns},{"activation_commit_ns",d.activation_commit_ns},{"end_ns",d.tick_end_ns},{"skipped_ticks",d.skipped_ticks},{"accepted",d.candidate_accepted},{"diagnostic_only",d.diagnostic_only},{"reason",d.reason},{"control_source",d.control_source},{"target_state",d.target_state},{"activation_state",d.activation_state},{"state_error",d.state_error},{"requested_n",d.requested_n},{"final_n",d.final_n},{"publish_success",d.publish_success},{"publish_start_ns",d.publish_start_ns},{"publish_end_ns",d.publish_end_ns},{"previous_anchor_known",d.previous_anchor_known},{"publish_sim_ns",d.publish_sim_ns},{"publish_epoch",d.publish_epoch},{"publish_clock_age_ns",d.publish_clock_age_ns},{"activation_clock_sim_ns",d.activation_clock_sim_ns},{"activation_clock_receive_ns",d.activation_clock_receive_ns},{"activation_rtf",d.activation_rtf},{"activation_odom_stamp_ns",d.activation_odom_stamp_ns},{"activation_odom_receive_ns",d.activation_odom_receive_ns},{"activation_odom_sequence",d.activation_odom_sequence},{"activation_imu_stamp_ns",d.activation_imu_stamp_ns},{"activation_imu_receive_ns",d.activation_imu_receive_ns},{"activation_imu_sequence",d.activation_imu_sequence},{"activation_r_from_imu",d.activation_r_from_imu},{"previous_n",d.previous_n},{"previous_publish_ns",d.previous_publish_ns},{"anchor_known",d.anchor_known},{"anchor_sequence",d.anchor_sequence},{"odom_age_ns",d.odom_age_ns},{"imu_age_ns",d.imu_age_ns},{"clock_age_ns",d.clock_age_ns},{"normal_contract_complete",d.normal_contract_complete},{"rho_available",d.rho_available},{"plant_acceptance_observed",false}};}
  // Actual tick tail, shared by the runtime loop and source-linked branch tests.
  // A true result means this same tick exits; no successor TickStart is required.
  bool finish_tick(const p1::Decision &d,int64_t now,int64_t planned,uint64_t tick,int64_t &stop_start,const p1::Json *observation=nullptr){
      auto source_row=decision_json(d);
      if(observation)source_row["d0_observation"]=*observation;
      {
        std::lock_guard<std::mutex> lock(mutex_);
        if(!stopping_&&!worker_unusable_&&worker_valid_&&!sink_->failed()&&(!adapter_||!adapter_->closing())){
          if(v1_enabled_&&!v1_armed_&&v1_await_sequence_==0&&d.candidate_accepted)v1_await_sequence_=d.sequence;
          controlled_previous_hold_changed_=controlled_phase_state_->hold_input_changed();
          const auto old_expired=controlled_phase_state_->expired_phases();
          controlled_phase::Decision phase;phase.sequence=d.sequence;phase.tick=d.tick;phase.job_id=d.job_id;phase.planned_ns=planned;phase.finished_ns=d.tick_end_ns;phase.accepted=d.candidate_accepted;phase.command=d.final_n;phase.run_id=run_;phase.boot_id=boot_;phase.contract_sha256=hash_;
          const auto reason=controlled_phase_state_->begin(phase,p1::monotonic_ns());
          sink_->add({{"type","controlled_phase_begin"},{"decision_sequence",d.sequence},{"tick",tick},{"planned_ns",planned},{"finished_ns",d.tick_end_ns},{"reason",reason},{"expired_phases",controlled_phase_state_->expired_phases()},{"expired_previous",controlled_phase_state_->expired_phases()!=old_expired},{"legacy_measurement_eligible",legacy_measurement_eligible_.load()},{"previous_hold_input_changed",controlled_previous_hold_changed_}});
          controlled_previous_hold_changed_=false;
          if(!reason.empty())unusable_locked("controlled_phase_begin:"+reason,p1::monotonic_ns());
        }
      }
      if(!sink_->add(std::move(source_row),d)){
        // Sink has released its queue lock. Stop and invalidate at the same
        // business boundary as preparation authorization, before any direct exit.
        std::lock_guard<std::mutex> l(mutex_);
        normal_complete_=false;stopping_=true;if(!stop_start)stop_start=now;
        if(!enqueue_failed_recorded_){phase_locked(p1::WitnessPhaseKind::StoppingObserved,p1::WitnessObservation::DecisionEnqueue,p1::monotonic_ns(),d.job_id);enqueue_failed_recorded_=true;stop_phase_recorded_=true;}
        invalidate_locked();
        if(!invalidate_phase_recorded_){phase_locked(p1::WitnessPhaseKind::InvalidationObserved,p1::WitnessObservation::DecisionEnqueue,p1::monotonic_ns(),d.job_id);invalidate_phase_recorded_=true;}
      }
      if(v1_enabled_&&!v1_report_written_&&sink_->v1_triggered()){
        auto diagnostic=sink_->v1_snapshot();p1::Json report;
        {std::lock_guard<std::mutex> lock(mutex_);std::lock_guard<std::mutex> prepare_lock(prep_mutex_);
          report={{"schema","V1-actual-queue-failure-observation/v1"},{"run_id",run_},{"boot_id",boot_},{"contract_hash",hash_},
            {"binary_sha256",get_parameter("diagnostic_binary_sha256").as_string()},{"source_sha256",get_parameter("diagnostic_source_sha256").as_string()},
            {"sink",diagnostic},{"arm_policy",v1_policy_},{"decision_sequence",d.sequence},{"job_id",d.job_id},{"tick",d.tick},
            {"stopping",stopping_.load()},{"normal_complete",normal_complete_.load()},{"admission_slots",admission_.slots()},
            {"candidate_present",bool(candidate_)},{"pending_present",pending_.has_value()},{"observation_ns",p1::monotonic_ns()},
            {"observer_physical_publishers",0},{"stage_qualified",false},{"execute_qualified",false}};
        }
        p1_owned::write_create_only(v1_fault_file_,report);v1_report_written_=true;
      }
      // The next Preparation is authorized only by an authenticated phase ack
      // plus its actual already-admitted Applied pair. No snapshot occurs here.
      const auto close=p1::publication::shutdown_result(stopping_.load(),mode_=="execute",d.final_n,d.publish_success,now,stop_start,c_.at("shutdown_grace_ns").get<int64_t>());
      if(close.exit_tick){sink_->add({{"type","regulator_shutdown"},{"zero_target_published",close.zero_target_published},{"shutdown_grace_exceeded",close.grace_exceeded},{"last_decision_sequence",d.sequence},{"normal_contract_complete",normal_complete_.load()&&!sink_->failed()},{"plant_hold_end_known",false},{"finished_ns",p1::monotonic_ns()}});return true;}
    return false;
  }
  void activate_candidate(p1::Decision &d,Snapshot &s,Snapshot &final_source,int64_t &copy_capture_ns,
       p1::d0::Observation &observation,const std::optional<p1::Ticket> &t,const std::shared_ptr<const p1::Candidate> &cand,
       int64_t planned,uint64_t tick,ActivationCapture &capture){
    capture.count=0;capture.decision_commit_ns=0;
    for(size_t attempt=0;attempt<activation_alignment::attempts;++attempt){
      const auto now=s.freeze;observation=p1::d0::Observation{};d.activation_state={};d.state_error={};d.requested_n={};d.final_n={};
      activation_alignment::Selection selection;
      auto &saved=capture.attempts[attempt];capture.count=attempt+1;saved.copied_ns=copy_capture_ns;
      auto reason=eligible(s,now);if(p1::d0::tap(observation.early_legacy_enabled,legacy_readiness_enabled_)&&!p1::d0::tap(observation.early_legacy_measurement,legacy_measurement_eligible_.load()))reason="legacy_not_ready";if(p1::d0::tap(observation.early_stopping,stopping_.load()))reason="shutdown";if(p1::d0::tap(observation.early_worker_unusable,worker_unusable_.load()))reason="worker_unusable";
      if(now-planned>c_.at("tick_jitter_ns").get<int64_t>()){reason="tick_jitter";normal_complete_=false;}
      if(t&&cand){d.job_id=t->id;d.candidate_ready_commit_ns=t->ready_ns;d.target_state=t->prediction;
        if(reason.empty()&&!(t->version==s.version))reason="version_mismatch";
        if(reason.empty())reason=p1::publication_history_check(t->anchor,s.anchor,s.publication_history);
        auto aligned=s;selection=activation_alignment::select(s,cand->job.target_sim_ns,
          p1::SourceAgeLimits{c_.at("odom_age_ns"),c_.at("imu_age_ns"),c_.at("odom_sim_lag_ns"),c_.at("imu_sim_lag_ns"),c_.at("source_future_slack_ns")},c_.at("mixed_skew_ns"));
        saved.selection=selection;
        if(selection.frame)activation_alignment::apply(aligned,*selection.frame);
        if(reason.empty()&&!selection.frame)reason="activation_no_causal_state";
        if(reason.empty())reason=eligible(aligned,now);
        const bool predicted=selection.frame&&predict(aligned,cand->job.target_sim_ns);if(!predicted){if(reason.empty())reason="activation_history_or_time";}else{std::copy(aligned.state.data(),aligned.state.data()+6,d.activation_state.begin());auto state_reason=p1::state_check(t->prediction,d.activation_state,limits_,&d.state_error);if(reason.empty())reason=state_reason;}
        p1::d0::observe_prediction(observation,predicted,d.activation_state,t->prediction);
        if(reason.empty()){Eigen::Vector2d request(cand->first_control[0],cand->first_control[1]);auto mapped=usv_mpc::map_vrx(request,c_.at("map_scale"),limits_.low,limits_.high,c_.at("publisher_max_n"));d.requested_n=cand->first_control;d.final_n={mapped[0],mapped[1]};reason=p1::command_check(d.final_n,s.anchor,now,limits_);if((mapped-request).norm()>1e-9)reason="candidate_mapping_changed";}
      }else if(reason.empty())reason="no_candidate";
      // Deliberately outside mutex_: the actual executor must be able to finish
      // a source admission. The original planned tick/jitter/deadline is retained.
      saved.interleave=v3_interleave_.wait(v3_policy_==activation_interleave::policy,
        reason.empty()&&attempt==0&&t&&cand&&last_accepted_>0,s.odom_seq,
        []{return p1::monotonic_ns();},[this]{return stopping_.load()||stop_requested.load()||worker_unusable_.load();});
#ifdef P1_C33_MATRIX_TEST
      if(c33_before_commit_)c33_before_commit_(tick);
#endif
      {std::lock_guard<std::mutex> l(mutex_);observation.input_change_gate_ran=reason.empty();
        if(observation.input_change_gate_ran){observation.input_change_gate_unchanged=(p1::d0::tap(observation.input_version_equal,s.version==version_)&&p1::d0::tap(observation.input_odom_equal,s.odom_seq==odom_seq_)&&p1::d0::tap(observation.input_imu_equal,s.imu_seq==imu_seq_));if(!*observation.input_change_gate_unchanged)reason="activation_input_changed_during_validation";}
        saved.gate_observation=observation;saved.guard=snapshot_source_locked(p1::monotonic_ns());saved.commit_check_ns=p1::monotonic_ns();
        if(reason=="activation_input_changed_during_validation"&&attempt+1<activation_alignment::attempts&&t&&cand&&
           s.version==version_&&s.activation_history_generation==activation_sensor_history_.generation()&&
           !stopping_&&!stop_requested&&!worker_unusable_&&!sink_->failed()&&
           p1::monotonic_ns()-planned<=c_.at("tick_jitter_ns").get<int64_t>()){
          saved.reason=reason;saved.retry=true;saved.raw=std::move(s);
          s=snapshot_locked(p1::monotonic_ns());copy_capture_ns=p1::monotonic_ns();continue;
        }
        if(reason.empty()&&s.activation_history_generation!=activation_sensor_history_.generation())reason="activation_sensor_history_changed";

        if(reason.empty()&&t)reason=p1::publication_history_check(t->anchor,anchor_,publication_history_);
        check_worker_locked(p1::monotonic_ns());
        int64_t commit_now=p1::monotonic_ns();
        if(reason.empty())reason=eligible(snapshot_locked(commit_now),commit_now);
        if(reason.empty()&&p1::d0::tap(observation.commit_legacy_enabled,legacy_readiness_enabled_)&&!p1::d0::tap(observation.commit_legacy_measurement,legacy_measurement_eligible_.load()))reason="legacy_not_ready_at_commit";
        if(reason.empty()&&(p1::d0::tap(observation.commit_worker_unusable,worker_unusable_.load())||!p1::d0::tap(observation.commit_worker_valid,worker_valid_.load())||p1::d0::tap(observation.commit_sink_failed,sink_->failed())))reason="run_unusable_at_commit";
        if(reason.empty()&&commit_now-planned>c_.at("tick_jitter_ns").get<int64_t>()){reason="tick_jitter_at_commit";normal_complete_=false;}
        if(reason.empty()&&cand&&std::abs(sim_+(commit_now-clock_receive_)-cand->job.target_sim_ns)>c_.at("target_sim_slack_ns").get<int64_t>())reason="target_sim_mismatch";
        if(reason.empty()&&selection.frame){auto selected_now=snapshot_locked(commit_now);activation_alignment::apply(selected_now,*selection.frame);reason=eligible(selected_now,commit_now);}
        if(reason.empty())reason=p1::command_check(d.final_n,anchor_,commit_now,limits_);
        if(adapter_){
          if(reason.empty()&&(!owner_peer_->alive()||adapter_->closing()))reason="adapter_owner_not_open";
          if(reason.empty()&&t&&cand){auto r=adapter_->inspect(t->id,tick,commit_now);if(!r)reason="adapter_activation:"+r.reason;}
          else adapter_->cancel(tick,commit_now);
          sink_->add({{"type","adapter_final_commit"},{"job_id",t?t->id:0},{"tick",tick},{"commit_ns",commit_now},{"inspection_linearization_ns",commit_now},{"reason",reason},{"owner_process_alive",owner_peer_->alive()},{"evidence",adapter_->evidence()}});
          // Recheck time-dependent guards after the observation-only consume and
          // its evidence work. A later rejection remains a consumed shadow slot.
          commit_now=p1::monotonic_ns();check_worker_locked(commit_now);
          if(reason.empty())reason=eligible(snapshot_locked(commit_now),commit_now);
          if(reason.empty()&&(worker_unusable_||!worker_valid_||sink_->failed()))reason="run_unusable_at_commit";
          if(reason.empty()&&(!owner_peer_->alive()||adapter_->closing()))reason="adapter_owner_not_open";
          if(reason.empty()&&commit_now-planned>c_.at("tick_jitter_ns").get<int64_t>()){reason="tick_jitter_at_commit";normal_complete_=false;}
          if(reason.empty()&&cand&&std::abs(sim_+(commit_now-clock_receive_)-cand->job.target_sim_ns)>c_.at("target_sim_slack_ns").get<int64_t>())reason="target_sim_mismatch";
          if(reason.empty()&&selection.frame){auto selected_now=snapshot_locked(commit_now);activation_alignment::apply(selected_now,*selection.frame);reason=eligible(selected_now,commit_now);}
          if(reason.empty())reason=p1::command_check(d.final_n,anchor_,commit_now,limits_);
        }
        if(p1::d0::tap(observation.final_stopping,stopping_.load())||p1::d0::tap(observation.final_stop_requested,stop_requested.load()))reason="shutdown";
        d.candidate_accepted=reason.empty();d.reason=reason;d.activation_commit_ns=commit_now;
        if(t&&cand){p1::WitnessActivation row{};identity(row,d);row.commit_ns=commit_now;row.ready_commit_ns=d.candidate_ready_commit_ns;row.accepted=d.candidate_accepted;row.failed=sink_->failed();row.stopping=stopping_;
          row.reason_code=row.accepted?p1::WitnessActivationReason::Accepted:reason=="shutdown"?p1::WitnessActivationReason::Shutdown:reason=="run_unusable_at_commit"?p1::WitnessActivationReason::RunUnusable:p1::WitnessActivationReason::OtherRejected;
          witness_->record_activation(row);
          if(row.accepted&&!business_ready_recorded_){phase_locked(p1::WitnessPhaseKind::BusinessReady,p1::WitnessObservation::FinalActivation,commit_now,d.job_id);business_ready_recorded_=true;}
          if(row.failed&&!activation_failed_recorded_){phase_locked(p1::WitnessPhaseKind::SourceFailure,p1::WitnessObservation::FinalActivation,p1::monotonic_ns(),d.job_id);activation_failed_recorded_=true;}
        }
        capture_final_source_locked(final_source,commit_now);
        d.activation_clock_sim_ns=sim_;d.activation_clock_receive_ns=clock_receive_;d.activation_rtf=rtf_;
        // Current source provenance at the actual final commit, not the job snapshot.
        d.activation_odom_stamp_ns=odom_stamp_;d.activation_odom_receive_ns=odom_receive_;d.activation_odom_sequence=odom_seq_;
        d.activation_r_from_imu=mixed_;d.activation_imu_stamp_ns=mixed_?imu_stamp_:0;
        d.activation_imu_receive_ns=mixed_?imu_receive_:0;d.activation_imu_sequence=mixed_?imu_seq_:0;
        d.odom_age_ns=commit_now-odom_receive_;d.imu_age_ns=mixed_?commit_now-imu_receive_:0;d.clock_age_ns=commit_now-clock_receive_;
        if(t&&cand&&mode_=="shadow")anchor_evidence_locked(*t,d);
        if(d.candidate_accepted){last_accepted_=d.activation_commit_ns;d.control_source="candidate";}else{d.final_n=p1::fallback(anchor_,d.activation_commit_ns,last_accepted_,limits_,p1::d0::tap(observation.fallback_invalid_stopping,stopping_.load())||p1::d0::tap(observation.fallback_invalid_worker_unusable,worker_unusable_.load())||reason!="no_candidate");d.requested_n=d.final_n;d.control_source=last_accepted_>0&&!p1::d0::tap(observation.fallback_source_stopping,stopping_.load())&&!p1::d0::tap(observation.fallback_source_worker_unusable,worker_unusable_.load())&&reason=="no_candidate"&&d.activation_commit_ns-last_accepted_<=limits_.hold_ns?"hold":"ramp_zero";}
      }
      saved.reason=d.reason;saved.final_commit_ns=d.activation_commit_ns;saved.predicted_available=observation.predicted_state_available;saved.predicted=observation.predicted_state;
      saved.raw=std::move(s);capture.decision_commit_ns=d.activation_commit_ns;break;
    }
  }
  void tick_loop(){int64_t origin=p1::monotonic_ns()+1000000000,stop_start=0;uint64_t tick=0,last_schedule=0;
    while(true){auto planned=origin+tick*p1::T;p1::sleep_until_monotonic(planned);
      if(tick_barrier_->take()){
        const auto start=p1::monotonic_ns();sink_->add({{"type","diagnostic_tick_barrier_enter"},{"expected_tick",tick},{"planned_ns",planned},{"start_ns",start},{"maximum_ms",tick_barrier_->milliseconds()},{"physical_output",false}});
        const auto until=start+tick_barrier_->milliseconds()*1000000;
        while(!stop_requested&&!prep_stop_&&p1::monotonic_ns()<until)p1::sleep_until_monotonic(std::min(until,p1::monotonic_ns()+20000000));
        sink_->add({{"type","diagnostic_tick_barrier_release"},{"expected_tick",tick},{"released_ns",p1::monotonic_ns()},{"cancelled",stop_requested.load()||prep_stop_.load()}});
      }
      auto now=p1::monotonic_ns();p1::Decision d;Snapshot s,final_source;int64_t copy_capture_ns=0;p1::d0::Observation observation;ActivationCapture activation_capture;std::optional<p1::Ticket> t;std::shared_ptr<const p1::Candidate> cand;
#ifdef P1_C33_MATRIX_TEST
      if(c33_before_snapshot_){c33_before_snapshot_(tick,planned);now=p1::monotonic_ns();}
#endif
      {std::lock_guard<std::mutex> l(mutex_);if(last_schedule&&version_.schedule!=last_schedule){origin=now;tick=0;planned=origin;invalidate_locked();}last_schedule=version_.schedule;
        auto due=p1::due_tick(origin,now);d.skipped_ticks=due>tick?due-tick:0;if(due>tick){const auto old_tick=tick;const auto old_candidate=candidate_?candidate_->job.job_id:0;const auto old_target=candidate_?candidate_->job.target_tick:0;tick=due;planned=origin+tick*p1::T;admission_.invalidate();candidate_.reset();normal_complete_=false;sink_->add({{"type","scheduler_skipped_ticks"},{"expected_tick",old_tick},{"due_tick",due},{"skipped_ticks",d.skipped_ticks},{"origin_ns",origin},{"observed_ns",now},{"planned_ns",planned},{"schedule_generation",version_.schedule},{"invalidated_candidate_job_id",old_candidate},{"invalidated_candidate_target_tick",old_target},{"candidate_after",false},{"admission_slots_after",admission_.slots()}});}
        current_tick_=tick;check_worker_locked(now);check_legacy_prepare_timeout_locked(now);if(stop_requested||sink_->failed()){
          stopping_=true;if(!stop_phase_recorded_){phase_locked(p1::WitnessPhaseKind::StoppingObserved,p1::WitnessObservation::TickStart,p1::monotonic_ns());stop_phase_recorded_=true;}
          if(!stop_start)stop_start=now;invalidate_locked();
          if(!invalidate_phase_recorded_){phase_locked(p1::WitnessPhaseKind::InvalidationObserved,p1::WitnessObservation::TickStart,p1::monotonic_ns());invalidate_phase_recorded_=true;}
        }
        if(clock_receive_&&last_clock_advance_&&now-last_clock_advance_>c_.at("clock_pause_confirm_ns").get<int64_t>()&&!paused_){invalidate_legacy_ready_locked("clock_paused",now);paused_=true;version_.schedule++;invalidate_locked();}
        if(worker_active_&&now-worker_active_since_>c_.at("active_watchdog_ns").get<int64_t>()){unusable_locked("active_watchdog",now);sink_->add({{"type","active_watchdog"},{"active_job",worker_active_},{"observed_ns",now},{"policy","stop_submit; supervisor owns finite TERM/KILL"}});}
        s=snapshot_locked(p1::monotonic_ns());copy_capture_ns=p1::monotonic_ns();t=admission_.take(tick,now);cand=candidate_;if(t)candidate_.reset();
        d.schema_version="p1-execution-decision-v2";d.run_id=run_;d.boot_id=boot_;d.contract_hash=hash_;d.worker_instance=worker_instance_;d.mode=mode_;d.sequence=++decision_seq_;d.tick=tick;d.task_generation=version_.task;d.model_generation=version_.model;d.config_generation=version_.config;d.schedule_generation=version_.schedule;d.clock_epoch=version_.epoch;d.tick_planned_ns=planned;d.tick_start_ns=now;d.cutoff_commit_ns=t?admission_.cutoff_ns():0;d.diagnostic_only=mode_!="execute";d.odom_age_ns=now-s.odom_receive;d.imu_age_ns=s.mixed?now-s.imu_receive:0;d.clock_age_ns=now-s.clock_receive;
      }
      const bool audit_failed_start=sink_->failed(),audit_stopping_start=stopping_;
      activate_candidate(d,s,final_source,copy_capture_ns,observation,t,cand,planned,tick,activation_capture);
      // Only the tick thread reaches either physical publisher; no shared mutex
      // spans publish. Callback invalidation after this commit affects successor ticks.
      publish(d);const auto observer_publish_return_ns=p1::monotonic_ns();
      {std::lock_guard<std::mutex> l(mutex_);d.anchor_known=anchor_.known;d.anchor_sequence=anchor_.seq;d.normal_contract_complete=normal_complete_&&!sink_->failed()&&mode_=="execute";d.tick_end_ns=p1::monotonic_ns();}
      auto activation_trace=materialize_activation_trace(activation_capture,observer_publish_return_ns);
      const auto &validation=activation_capture.attempts[activation_capture.count-1].raw;
      auto observed=p1::d0::json(validation,final_source,copy_capture_ns,observation,bool(t&&cand),t?t->id:0,cand?cand->job.target_tick:0,cand?cand->job.target_sim_ns:0);
      observed["activation_alignment"]=std::move(activation_trace);
      observed["candidate_capture"]=captured_candidate_json(cand,bool(t));observed["audit_reads_start"]={{"sink_failed",audit_failed_start},{"stopping",audit_stopping_start}};
      if(finish_tick(d,now,planned,tick,stop_start,&observed)){audit_tick(d,bool(t&&cand),audit_failed_start,audit_stopping_start);break;}
#ifdef P1_C33_MATRIX_TEST
      if(c33_after_tick_)c33_after_tick_(tick);
#endif
      p1::sleep_until_monotonic(planned+p1::DEADLINE+1);{std::lock_guard<std::mutex> l(mutex_);const auto cutoff_now=p1::monotonic_ns();admission_.cutoff(cutoff_now);if(adapter_){auto r=adapter_->cutoff(cutoff_now);sink_->add({{"type","adapter_cutoff"},{"tick",tick},{"commit_ns",cutoff_now},{"reason",r.reason}});}}
      audit_tick(d,bool(t&&cand),audit_failed_start,audit_stopping_start);
      ++tick;
    }
    prep_stop_=true;prep_cv_.notify_all();finished_=true;
  }
  std::string v3_policy_="none";activation_interleave::Once v3_interleave_;
  std::string v1_policy_,v1_fault_file_;uint64_t v1_await_sequence_=0;bool v1_enabled_=false,v1_armed_=false,v1_report_written_=false;
  bool controlled_phase_enabled_=false,controlled_previous_hold_changed_=false;
  controlled_phase::Identity controlled_owner_identity_;controlled_phase::PeerBinding controlled_applied_binding_,controlled_phase_binding_;
  std::unique_ptr<controlled_phase::ObserverPhase> controlled_phase_state_;
  std::unique_ptr<c36_owned::OwnedPeer> controlled_owner_phase_peer_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr controlled_phase_subscription_;
  std::unique_ptr<c36_owned::OwnedPeer> owner_peer_;std::unique_ptr<c36_runtime::Adapter> adapter_;p1::Json adapter_pins_;std::string adapter_close_file_;std::atomic<bool> adapter_close_observed_{false};int64_t adapter_close_ns_=0,adapter_close_request_ns_=0;rclcpp::TimerBase::SharedPtr adapter_close_timer_;
  std::unique_ptr<p1::Witness> witness_;p1::DiagPausePolicy pause_policy_;std::string witness_file_;
  std::atomic<bool> audit_identity_ok_{true};bool audit_closed_=false,business_ready_recorded_=false,stop_phase_recorded_=false,invalidate_phase_recorded_=false,activation_failed_recorded_=false,enqueue_failed_recorded_=false;
  p1::shadow::LegacyIdentity expected_legacy_identity_;uint64_t legacy_received_=0,legacy_admitted_=0;
  bool legacy_readiness_enabled_=false,legacy_ready_issued_=false,legacy_readiness_terminal_=false;std::atomic<bool> legacy_measurement_eligible_{false};
  bool legacy_sequence_complete_=true,legacy_ready_projection_complete_=true,ready_path_valid_=false,ready_profile_valid_=false;uint64_t legacy_first_sequence_=0;
  int64_t graph_arm_ns_=0,legacy_prepare_start_ns_=0,legacy_prepare_deadline_ns_=0,legacy_ready_timeout_ns_=0,legacy_ready_ns_=0,legacy_pair_processed_ns_=0,last_capability_commit_ns_=0;
  std::array<int64_t,2> legacy_anchor_sim_ns_{},legacy_pair_publish_end_ns_{};std::deque<ReadyHeld> ready_history_;
  p1::Json last_capability_=nullptr;std::string legacy_ready_pending_reason_="no_executor_callbacks";
  task_time_reference::Epoch reference_epoch_;
  p1::Json c_;usv_mpc::MpcParams params_;p1::Limits limits_;std::string run_,hash_,mode_,boot_,nominal_,legacy_run_,legacy_producer_,worker_instance_,path_fingerprint_,profile_fingerprint_,recording_observer_;int64_t expected_worker_pid_=0;
  std::unique_ptr<p1::WorkerLiveness> worker_liveness_;
  std::unique_ptr<c37_owned::OwnedWorkerPeer> worker_peer_;
  uint64_t worker_capability_received_=0,worker_candidate_received_=0;
  bool executor_detached_=false;
  std::string diagnostic_c38_mode_="none",diagnostic_c38_pause_file_,diagnostic_c38_resume_file_,c38_gate_interface_="none";std::unique_ptr<c38::DiagnosticGate> c38_gate_;rclcpp::CallbackGroup::SharedPtr c38_diagnostic_group_;bool c38_group_registered_=false,c38_pause_attempted_=false,c38_resume_attempted_=false,c38_suppression_logged_=false;
  std::unique_ptr<p1::PreparationBarrier> preparation_barrier_;std::atomic<bool> preparation_barrier_active_{false};
  std::unique_ptr<p1::TickBarrier> tick_barrier_;
  std::unique_ptr<p1::CapabilityLease> capability_lease_;
  std::mutex mutex_,prep_mutex_;std::condition_variable prep_cv_;std::optional<Preparation> pending_;std::thread prep_,tick_;std::atomic<bool> prep_stop_{false},finished_{false},stopping_{false},normal_complete_{true},worker_unusable_{false},worker_valid_{false};std::unique_ptr<Sink> sink_;
  p1::ResourceLimits resources_;p1::Version version_;p1::Anchor anchor_;p1::Admission admission_;std::shared_ptr<const p1::Candidate> candidate_;std::deque<p1::Job> jobs_;std::deque<usv_mpc::HeldInputEvent> history_;std::deque<p1::PublicationEvent> publication_history_;uint64_t legacy_sequence_=0;std::shared_ptr<const usv_mpc::ReferenceInput> ref_;usv_mpc::Vector6d state_=usv_mpc::Vector6d::Zero();
  activation_alignment::History activation_sensor_history_;uint64_t activation_odom_generation_=0;
  uint64_t input_commit_ordinal_=0,current_tick_=0,job_id_=0,decision_seq_=0,odom_received_=0,imu_received_=0,odom_seq_=0,imu_seq_=0,path_seq_=0,profile_seq_=0,worker_active_=0;int64_t worker_active_since_=0,odom_stamp_=0,imu_stamp_=0,odom_receive_=0,imu_receive_=0,clock_receive_=0,sim_=0,last_clock_advance_=0,last_accepted_=0;bool mixed_=false;std::atomic<bool> paused_{false},rtf_valid_{false};double rtf_=0;p1::ClockWindow clock_window_;
  rclcpp::Publisher<p1::Job>::SharedPtr job_pub_;rclcpp::Publisher<p1::Decision>::SharedPtr decision_pub_;rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr left_,right_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_;rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_;rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr path_;rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr profile_;rclcpp::Subscription<rosgraph_msgs::msg::Clock>::SharedPtr clock_;rclcpp::Subscription<p1::Candidate>::SharedPtr candidates_;rclcpp::Subscription<p1::Capability>::SharedPtr capabilities_;rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr stop_;rclcpp::Subscription<usv_research_interfaces::msg::AppliedControl>::SharedPtr applied_;
};
int main(int argc,char **argv){rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,stop_signal);std::signal(SIGTERM,stop_signal);
try{auto node=std::make_shared<Regulator>();rclcpp::executors::SingleThreadedExecutor exec;exec.add_node(node);node->register_diagnostic_group(exec);while(!node->finished()&&rclcpp::ok()){node->poll_diagnostic_gate(exec);exec.spin_some(std::chrono::milliseconds(10));node->poll_diagnostic_gate(exec);std::this_thread::sleep_for(std::chrono::milliseconds(1));}node->remove_diagnostic_group(exec);exec.remove_node(node);node->mark_executor_detached();bool closed=node->close_source();bool audit=node->audit_closed();node.reset();rclcpp::shutdown();return closed?(audit?0:3):2;}catch(const std::exception & e){fprintf(stderr,"regulator fatal: %s\n",e.what());rclcpp::shutdown();return 1;}}
