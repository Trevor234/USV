// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include <atomic>
#include <condition_variable>
#include <mutex>
#include <optional>
#include <thread>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <rclcpp/rclcpp.hpp>
#include "protocol.hpp"
#include "m4_owned_runtime.hpp"
#include "owned_cold_backend.hpp"
#include "w2_native_boundary.hpp"
#include "w2_pipe_reader.hpp"
#include "p1_owned_identity.hpp"
#include "capability_source_v4.hpp"
#include "v2_diagnostic_block.hpp"
#ifndef P1_OWNED_SOURCE_BUNDLE_SHA256
#error "owned Worker requires source bundle identity"
#endif
namespace {std::atomic<bool> stopping{false};void stop_signal(int){stopping=true;}}
class Worker final:public rclcpp::Node {
 public:
  Worker():Node("p1_solver_worker",formal_owned::node_options()) {
    formal_owned::entry_arguments(*this);
    run_=declare_parameter<std::string>("run_id","");hash_=declare_parameter<std::string>("contract_hash","");
    // W1: the scope selects the identity. The ordinary scope still demands the
    // frozen v3 contract; the diagnostic scope demands the v4 one. Both paths go
    // through m4_owned::contract(), so neither can borrow the other's allowance.
    auto file=declare_parameter<std::string>("contract_file","");
    scope_=declare_parameter<std::string>("m4_release_scope","");
    c_=m4_owned::contract(file,hash_,declare_parameter<std::string>("mode","execute"),scope_);
    resources_=p1::resource_limits_from_contract(c_);
    boot_=p1::boot_id();nominal_=c_.at("nominal_hash");instance_=p1::digest(run_+boot_+std::to_string(getpid())+std::to_string(p1::monotonic_ns()));
    if(run_.empty()||run_.size()>128)throw std::runtime_error("run identity invalid");
    delay_=declare_parameter<int>("test_delay_ms",0);block_=declare_parameter<int>("test_native_block_ms",0);
    if(delay_<0||block_<0||delay_>10000||block_>60000||((delay_||block_)&&!c_.at("fault_injection_enabled").get<bool>()))throw std::runtime_error("unqualified fault injection");
    v2_policy_=declare_parameter<std::string>("diagnostic_v2_policy","none");v2_ms_=declare_parameter<int>("diagnostic_v2_block_ms",0);
    // W4: drop exactly one generated candidate instead of publishing it. The
    // Candidate is still fully built and recorded in the Worker Source, so the
    // audit can show generation happened and delivery did not.
    drop_after_=declare_parameter<int>("diagnostic_drop_after_candidates",-1);
    if(drop_after_< -1||drop_after_>1000||(drop_after_>=0&&!c_.at("fault_injection_enabled").get<bool>()))throw std::runtime_error("unqualified diagnostic drop");
    v2_block_=std::make_unique<v2_diagnostic::Block>(v2_policy_,v2_ms_,c_.at("parameters_are_diagnostic_only").get<bool>(),c_.at("fault_injection_enabled").get<bool>(),c_.at("execute_qualified").get<bool>());
    if(c_.value("worker_failure_policy",std::string{})!="terminal_on_failed_or_invalid_native_result")throw std::runtime_error("undeclared worker failure policy");
    const auto dp=declare_parameter<std::string>("driver_pins_file","");const auto dh=declare_parameter<std::string>("driver_pins_sha256","");m4_driver_=formal_owned::driver_peer(formal_owned::read_pinned(dp,dh),run_,hash_);
    auto log=declare_parameter<std::string>("source_file","");file_.open(log,std::ios::out|std::ios::app);if(!file_)throw std::runtime_error("worker source log unavailable");
    if(c_.at("recording_ready_timeout_ns").get<int64_t>()<=0||c_.at("recording_ready_timeout_ns").get<int64_t>()>60000000000LL)throw std::runtime_error("invalid finite recording timeout");
    solver_=std::make_unique<owned_cold::Backend>(p1::solver_params(c_),p1::Json{{"run_id",run_},{"boot_id",boot_},{"contract_hash",hash_},{"nominal_hash",nominal_},{"worker_instance",instance_}},true);
    // W2: arm the private release channel only when this run registered one.
    // An unarmed run keeps the ordinary path exactly as it was.
    arm_w2_boundary_();
    out_=create_publisher<p1::Candidate>("/p1/solve_candidate",rclcpp::QoS(1).reliable());
    caps_=create_publisher<p1::Capability>("/p1/worker_capability",rclcpp::QoS(1).reliable().transient_local());
    sub_=create_subscription<p1::Job>("/p1/solve_job",rclcpp::QoS(1).reliable(),[this](p1::Job::SharedPtr j){receive(*j);});
    const auto owned_file=declare_parameter<std::string>("owned_manifest_file","");owned_file_=owned_file;
    formal_owned::overrides(*this,{"run_id","contract_hash","contract_file","m4_release_scope","mode","driver_pins_file","driver_pins_sha256","source_file","owned_manifest_file","test_delay_ms","test_native_block_ms","diagnostic_v2_policy","diagnostic_v2_block_ms","diagnostic_drop_after_candidates","use_sim_time"});
    parameters_frozen_=p1_owned::freeze_parameters(*this);
    const auto endpoints=p1_owned::Json::array({
      p1_owned::publisher_endpoint(*out_,"usv_research_interfaces/msg/SolveCandidate"),
      p1_owned::publisher_endpoint(*caps_,"usv_research_interfaces/msg/WorkerCapability"),
      p1_owned::subscription_endpoint(*sub_,"usv_research_interfaces/msg/SolveJob")});
    p1_owned::write_create_only(owned_file,p1_owned::role_manifest(*this,"worker",run_,hash_,P1_OWNED_SOURCE_BUNDLE_SHA256,endpoints,
      {{"worker_instance",instance_},{"nominal_hash",nominal_},{"source_fd",p1_owned::source_fd_identity(log)},
       {"runtime_hook_values",{{"test_delay_ms",delay_},{"test_native_block_ms",block_}}},
       {"diagnostic_v2",{{"policy",v2_policy_},{"milliseconds",v2_ms_},{"after_completed_jobs",1},{"native_C_hang_claimed",false}}},{"diagnostic_drop_after_candidates",drop_after_},{"fault_injection_permission",c_.at("fault_injection_enabled")},
       {"w2_release_channel",w2_channel_manifest_()},{"contract_configuration",c_}}));
    startup_=p1::monotonic_ns();
    event({{"type","capability_source_header"},{"schema","p1-capability-source-header-v1"},
      {"run_id",run_},{"boot_id",boot_},{"pid",getpid()},{"process_start_ticks",p1_owned::process_start_ticks()},
      {"worker_instance",instance_},{"startup_ns",startup_},{"contract_hash",hash_},{"nominal_hash",nominal_},
      {"source_bundle_sha256",P1_OWNED_SOURCE_BUNDLE_SHA256},{"binary_sha256",p1_owned::file_sha256("/proc/self/exe")},
      {"owned_manifest_sha256",p1_owned::file_sha256(owned_file_)},{"endpoint",p1_owned::publisher_endpoint(*caps_,"usv_research_interfaces/msg/WorkerCapability")},
      {"diagnostic_v2_policy",v2_policy_},{"diagnostic_v2_block_ms",v2_ms_},{"clock","CLOCK_MONOTONIC"},{"wire_contract_unchanged",true}},true);
    if(fatal_)throw std::runtime_error("capability source header failed");publish_capability();timer_=create_wall_timer(std::chrono::milliseconds(200),[this]{publish_capability();});
    thread_=std::thread([this]{work();});
  }
  ~Worker(){close_source();}
  bool close_source(){if(closed_)return !fatal_;closed_=true;stopping=true;cv_.notify_all();if(thread_.joinable())thread_.join();{std::lock_guard<std::mutex> l(mutex_);if(pending_){event({{"type","pending_discarded"},{"job_id",pending_->job.job_id},{"reason","worker_close"}});pending_.reset();}}event({{"type","worker_summary"},{"generated_candidates",generated_candidates_.load()},{"published_candidates",published_candidates_.load()},{"dropped_candidates",dropped_candidates_.load()},{"completed_jobs",completed_.load()},{"fatal",fatal_.load()},{"terminal_numerical_failure",terminal_numerical_.load()},{"normal_source_complete",!fatal_.load()&&generated_candidates_==published_candidates_+dropped_candidates_.load()},{"capability_source",capability_terminal()},{"source_rows_before_terminal",source_rows_generated_.load()},{"source_rows_emitted_before_terminal",source_rows_emitted_.load()},{"source_io_failed",source_io_failed_.load()},{"finished_ns",p1::monotonic_ns()}});file_.flush();const bool flush_ok=bool(file_);if(!flush_ok)fatal_=true;fprintf(stdout,"WORKER_CLOSE_FLUSH_SUCCESS=%s\n",flush_ok?"true":"false");return !fatal_;}
 private:
  // ── W2 private release chanel ────────────────────────────────────────────
  //
  // The read end is inherited from the Driver, never opened here. Verifying it
  // is a read-only pipe on the inherited number is all this can do: the fd
  // number is not an identity, so the registration also pins device/inode and
  // the run/Job/ordinal/nonce that the frame must carry.
  void arm_w2_boundary_(){
    w2_fd_=declare_parameter<int>("w2_release_fd",-1);
    const auto job=declare_parameter<int64_t>("w2_release_job_id",-1);
    const auto ordinal=declare_parameter<int>("w2_release_ordinal",0);
    const auto budget=declare_parameter<int64_t>("w2_release_wait_ns",0);
    w2_nonce=declare_parameter<int>("w2_release_nonce",0);
    if(w2_fd_<0){
      // Without an fd every other W2 parameter must stay at its disabled
      // default; a half-registered channel is a configuration error, not a
      // reason to silently continue.
      if(job>=0||ordinal!=0||budget!=0||w2_nonce!=0)
        throw std::runtime_error("w2 release parameters given without an fd");
      return;  // ordinary profile: no gate, no waiting
    }
    if(w2_nonce==0)throw std::runtime_error("w2 release nonce must be non-zero");
    if(!c_.at("fault_injection_enabled").get<bool>()||!c_.at("parameters_are_diagnostic_only").get<bool>())
      throw std::runtime_error("w2 release channel requires the diagnostic profile");
    if(job<0||ordinal<=0||budget<=0||budget>2000000000LL)
      throw std::runtime_error("w2 release binding incomplete or out of bounds");
    char path[64];std::snprintf(path,sizeof(path),"/proc/self/fd/%d",w2_fd_);
    char target[256]={};const auto n=::readlink(path,target,sizeof(target)-1);
    if(n<=0)throw std::runtime_error("w2 release fd does not resolve");
    target[n]=0;
    // S_ISFIFO identifies the object; st_mode says nothing about the fd's
    // access mode. Both ends of a pipe report the same st_mode.
    struct stat st{};
    if(::fstat(w2_fd_,&st)!=0||!S_ISFIFO(st.st_mode))
      throw std::runtime_error("w2 release fd is not a FIFO");
    // F_GETFL is the only correct way to learn the direction: the read end is
    // O_RDONLY, the write end O_WRONLY. Checking st_mode & O_ACCMODE accepts
    // both ends, which is exactly the wiring error this gate must catch.
    const int flags=::fcntl(w2_fd_,F_GETFL);
    if((st.st_mode&O_ACCMODE)!=O_RDONLY)
      throw std::runtime_error("w2 release fd is not read-only");
    w2_channel_.device=uint64_t(st.st_dev);w2_channel_.inode=uint64_t(st.st_ino);
    w2_pipe_=std::make_unique<w2_gate::PipeReader>(w2_fd_);
    w2_gate_=std::make_unique<w2_gate::Gate>(w2_pipe_.get(),
      w2_gate::Identity{1,uint64_t(job),uint32_t(ordinal),uint32_t(w2_nonce)},
      budget);
    w2_boundary_cfg_.job_id=job;w2_boundary_cfg_.ordinal=uint32_t(ordinal);
    w2_boundary_cfg_.wait_budget_ns=budget;
    // The Job deadline is fixed per Job at solve time, not here.
    w2_boundary_=std::make_unique<w2_wire::Boundary>(w2_gate_.get(),w2_boundary_cfg_,
      []{return p1::monotonic_ns();});
    // Announce the boundary the moment it is reached, before the wait. The
    // Driver times its release against this event, not against a sleep.
    w2_boundary_->set_entry_observer([this](const w2_wire::BoundaryConfig &cfg){
      event({{"type","w2_boundary_entered"},{"job_id",cfg.job_id},
        {"ordinal",cfg.ordinal},{"job_deadline_ns",cfg.job_deadline_ns},
        {"wait_budget_ns",cfg.wait_budget_ns},
        {"entered_ns",p1::monotonic_ns()},
        {"actual_native_invoked",false}},true);
    });
    event({{"type","w2_release_channel_armed"},{"fd",w2_fd_},{"fd_target",target},
      {"job_id",job},{"ordinal",ordinal},{"wait_budget_ns",budget},
      {"nonce",w2_nonce},{"device",w2_channel_.device},{"inode",w2_channel_.inode},
      {"read_only",true},{"gate_armed",true}},true);
    if(fatal_)throw std::runtime_error("w2 release arm event failed");
  }

  /// The channel facts the Regulator authenticates against. Recorded from the
  /// actual inherited fd (device/inode and F_GETFL direction), not from the
  /// numbers the Driver passed: an fd integer is not an identity.
  p1::Json w2_channel_manifest_()const{
    if(w2_fd_<0)return p1::Json(nullptr);
    return {{"fd",w2_fd_},{"device",w2_channel_.device},{"inode",w2_channel_.inode},
            {"read_only",true},{"gate_armed",true},
            {"job_id",w2_boundary_cfg_.job_id},{"ordinal",w2_boundary_cfg_.ordinal},
            {"nonce",w2_nonce},{"wait_budget_ns",w2_boundary_cfg_.wait_budget_ns}};
  }

  /// Emit the boundary result once, and only for the Job it is bound to.
  ///
  /// The boundary holds one decision for the whole run. Without the Job check
  /// and the once-flag, every later Job would re-publish the target Job's
  /// disposition and invocation fact under its own job_id.
  void emit_w2_result_if_target_(int64_t job_id){
    if(!w2_boundary_||w2_result_emitted_)return;
    if(job_id!=w2_boundary_cfg_.job_id)return;
    const auto &rec=w2_boundary_->record();
    if(!rec.gate_configured)return;
    w2_result_emitted_=true;
    event({{"type","w2_boundary_result"},{"job_id",job_id},
      {"ordinal",rec.ordinal},{"disposition",w2_wire::disposition_name(rec.disposition)},
      {"boundary",w2_boundary_json(rec)},
      {"actual_native_invoked",rec.actual_native_invoked}},true);
  }

  bool event(const p1::Json & d,bool flush=false){std::lock_guard<std::mutex> l(log_mutex_);source_rows_generated_++;file_<<d.dump()<<'\n';if(flush)file_.flush();if(!file_){fatal_=true;source_io_failed_=true;return false;}source_rows_emitted_++;return true;}
  p1::Json capability_terminal()const{return {{"schema","p1-capability-source-terminal-v1"},
    {"capability_generated",cap_generated_},{"capability_attempt_records",cap_attempt_records_},
    {"capability_publish_calls",cap_calls_},{"capability_publish_returned",cap_returned_},
    {"capability_publish_threw",cap_threw_},{"capability_result_records",cap_result_records_},
    {"capability_aborted_before_publish",cap_aborted_},{"capability_source_io_failed",source_io_failed_.load()},
    {"capability_last_publish_seq",cap_generated_},{"capability_last_payload_sha256",cap_last_sha_},
    {"capability_last_publish_end_ns",cap_last_end_},
    {"capability_source_complete",!source_io_failed_&&cap_generated_==cap_attempt_records_&&cap_generated_==cap_calls_&&cap_generated_==cap_returned_&&cap_threw_==0&&cap_aborted_==0&&cap_result_records_==cap_generated_}};}


  // Capability and work have separate finite recorder barriers.
  bool wait_recording_ready(){
    try{
      const int64_t start=p1::monotonic_ns(),timeout=c_.at("recording_ready_timeout_ns").get<int64_t>();
      while(rclcpp::ok()&&!stopping&&!fatal_&&p1::monotonic_ns()-start<=timeout){
        bool recorder=false,regulator=false;
        for(const auto & endpoint:get_subscriptions_info_by_topic("/p1/solve_candidate")){
          recorder=recorder||endpoint.node_name().find("recorder")!=std::string::npos;
          regulator=regulator||endpoint.node_name()=="p1_regulator";
        }
        if(out_->get_subscription_count()>=2&&recorder&&regulator){
          event({{"type","worker_recording_ready"},{"worker_instance",instance_},{"ready_ns",p1::monotonic_ns()},
            {"candidate_matched",out_->get_subscription_count()},{"active_job",0}},true);
          if(!fatal_)return true;
          break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
      }
      fatal_=true;event({{"type","worker_recording_ready_failed"},{"worker_instance",instance_},{"finished_ns",p1::monotonic_ns()}},true);
    }catch(const std::exception & e){
      fatal_=true;event({{"type","worker_recording_ready_failed"},{"reason",std::string(e.what()).substr(0,256)}},true);
    }
    {std::lock_guard<std::mutex> l(mutex_);pending_.reset();}active_=0;return false;
  }

  void publish_capability(){
    if(!m4_driver_->alive()){fatal_=true;stopping=true;return;}
    if(!capability_recording_ready_){
      if(caps_->get_subscription_count()!=3)return;
      bool source=false,recorder=false,observer=false;
      for(const auto &e:get_subscriptions_info_by_topic("/p1/worker_capability")){
        source=source||e.node_name()=="p1_synthetic_source";
        recorder=recorder||e.node_name()=="p1_owned_recorder";
        observer=observer||e.node_name()=="p1_regulator";
      }
      if(!source||!recorder||!observer)return;
      const auto checked=p1::monotonic_ns();
      p1_owned::write_create_only(owned_file_+".capability_ready.json",{{"schema","p1-owned-native-capability-ready-v1"},{"role","worker"},{"run_id",run_},{"contract_sha256",hash_},{"boot_id",boot_},{"pid",getpid()},{"process_start_ticks",p1_owned::process_start_ticks()},{"owned_manifest_sha256",p1_owned::file_sha256(owned_file_)},{"checked_steady_ns",checked},{"capability_matched_subscribers",caps_->get_subscription_count()},{"capability_endpoint",p1_owned::publisher_endpoint(*caps_,"usv_research_interfaces/msg/WorkerCapability")},{"fixture_only",true},{"execute_qualified",false}});
      event({{"type","worker_capability_recording_ready"},{"ready_ns",checked},{"capability_matched",caps_->get_subscription_count()}},true);
      capability_recording_ready_=true;
    }
    p1::Capability m;m.schema_version="p1-worker-capability-v1";m.run_id=run_;m.boot_id=boot_;m.contract_hash=hash_;m.nominal_hash=nominal_;m.worker_instance=instance_;m.clock_name="CLOCK_MONOTONIC";m.backend=solver_->backend();m.matrix_layout="column_major";m.horizon_steps=solver_->N();m.prediction_dt=solver_->dt();m.pid=getpid();m.startup_ns=startup_;m.completed_jobs=completed_;m.active_job=active_;{std::lock_guard<std::mutex> l(mutex_);m.pending_count=pending_?1:0;}m.fatal=fatal_;m.fault_injection_enabled=c_.at("fault_injection_enabled");m.reason=fatal_?"worker_unusable":"";
    const auto seq=++cap_generated_;const auto snapshot_ns=p1::monotonic_ns();const auto value=p1_cap_source_v4::payload(m);
    cap_last_sha_=p1_cap_source_v4::typed_sha(value);
    if(!event({{"type","capability_publish_attempt"},{"schema","p1-capability-publish-attempt-v1"},
      {"publish_seq",seq},{"snapshot_ns",snapshot_ns},{"attempt_record_ns",p1::monotonic_ns()},
      {"payload",value},{"payload_sha256",cap_last_sha_},{"typed_digest_encoding","p1-capability-typed-ieee754-v1"},
      {"cdr",p1_cap_source_v4::cdr(m)}},true)){cap_aborted_++;stopping=true;return;}
    cap_attempt_records_++;const auto start=p1::monotonic_ns();cap_calls_++;
    try{caps_->publish(m);cap_last_end_=p1::monotonic_ns();cap_returned_++;
      if(event({{"type","capability_publish_result"},{"schema","p1-capability-publish-result-v1"},
        {"publish_seq",seq},{"payload_sha256",cap_last_sha_},{"publish_start_ns",start},{"publish_end_ns",cap_last_end_},
        {"returned",true},{"threw",false}},true))cap_result_records_++;else stopping=true;
    }catch(...){cap_last_end_=p1::monotonic_ns();cap_threw_++;
      if(event({{"type","capability_publish_result"},{"schema","p1-capability-publish-result-v1"},
        {"publish_seq",seq},{"payload_sha256",cap_last_sha_},{"publish_start_ns",start},{"publish_end_ns",cap_last_end_},
        {"returned",false},{"threw",true}},true))cap_result_records_++;
      fatal_=true;stopping=true;throw;
    }
  }
  void receive(const p1::Job & j){auto now=p1::monotonic_ns();auto resource=p1::check_job_resources(j,resources_);if(!resource){event({{"type","resource_rejected"},{"interface","job"},{"job_id",j.job_id},{"reason",resource.reason},{"field",resource.field},{"observed",resource.observed},{"limit",resource.limit},{"receive_ns",now}});return;}if(fatal_||stopping){event({{"type","job_rejected"},{"job_id",j.job_id},{"reason","worker_terminal"}});return;}auto reason=p1::valid_job(j,run_,boot_,hash_,nominal_,instance_);if(reason.empty()&&now>j.deadline_steady_ns)reason="late_before_native";
    if(!reason.empty()){event({{"type","job_rejected"},{"job_id",j.job_id},{"reason",reason},{"receive_ns",now}});return;}
    std::lock_guard<std::mutex> l(mutex_);
    if(fatal_||stopping){event({{"type","job_rejected"},{"job_id",j.job_id},{"reason","worker_terminal"},{"receive_ns",now}});return;}
    if(j.job_id<=last_received_){event({{"type","job_rejected"},{"job_id",j.job_id},{"reason","duplicate_or_reordered"}});return;}
    last_received_=j.job_id;
    event({{"type","job_received"},{"job",p1::job_json(j)},{"worker_instance",instance_},{"receive_ns",now},{"commit_ns",p1::monotonic_ns()}});
    if(fatal_)return;
    if(pending_)event({{"type","pending_replaced"},{"job_id",pending_->job.job_id},{"replacement_job_id",j.job_id}});
    pending_=Pending{j,now};cv_.notify_one();
  }
  struct Pending{p1::Job job;int64_t receive;};
  void work(){if(!wait_recording_ready())return;while(!stopping&&!fatal_){Pending p;{std::unique_lock<std::mutex> l(mutex_);cv_.wait_for(l,std::chrono::milliseconds(100),[this]{return stopping||pending_.has_value();});if(stopping||fatal_){if(pending_)event({{"type","pending_discarded"},{"job_id",pending_->job.job_id},{"reason","worker_stopping_before_native"}});pending_.reset();break;}if(!pending_)continue;p=*pending_;pending_.reset();active_=p.job.job_id;}
    if(p1::monotonic_ns()>p.job.deadline_steady_ns){event({{"type","pending_expired_before_native"},{"job_id",p.job.job_id},{"solver_invoked",false},{"now_ns",p1::monotonic_ns()}});active_=0;continue;}
    p1::Candidate result;result.job=p.job;result.worker_instance=instance_;result.backend="acados";result.worker_receive_ns=p.receive;
    bool result_published=false,result_dropped=false;
    try {
      if(p.job.reset_warmstart)solver_->reset_warmstart();
      solver_->set_applied_control({p.job.anchor_n[0],p.job.anchor_n[1]});
      usv_mpc::Vector6d x;std::copy(p.job.target_state.begin(),p.job.target_state.end(),x.data());
      Eigen::MatrixXd ref(6,21);std::copy(p.job.reference.begin(),p.job.reference.end(),ref.data());
      result.solve_start_ns=p1::monotonic_ns();if(result.solve_start_ns>p.job.deadline_steady_ns){event({{"type","pending_expired_before_native"},{"job_id",p.job.job_id},{"solver_invoked",false},{"now_ns",result.solve_start_ns}});active_=0;continue;}
      // Controlled barrier is deliberately in the native-owned path; an owned
      // supervisor must TERM/KILL this process if its active watchdog expires.
      if(block_){event({{"type","controlled_pre_native_barrier"},{"job_id",p.job.job_id},{"start_ns",p1::monotonic_ns()},{"duration_ms",block_},{"actual_native_invoked",false},{"flush_requested",true}},true);if(fatal_){active_=0;{std::lock_guard<std::mutex> l(mutex_);pending_.reset();}break;}std::this_thread::sleep_for(std::chrono::milliseconds(block_));}
      if(v2_block_->take(completed_.load())){
        const auto start=p1::monotonic_ns();
        event({{"type","diagnostic_v2_pre_native_enter"},{"policy",v2_policy_},{"job_id",p.job.job_id},{"start_ns",start},{"duration_ms",v2_ms_},{"completed_jobs_before",completed_.load()},{"actual_native_invoked",false},{"stage_qualified",false}},true);
        if(fatal_){active_=0;break;}
        std::this_thread::sleep_for(std::chrono::milliseconds(v2_ms_));
        event({{"type","diagnostic_v2_pre_native_release"},{"policy",v2_policy_},{"job_id",p.job.job_id},{"start_ns",start},{"released_ns",p1::monotonic_ns()},{"actual_native_invoked",false},{"stopping",stopping.load()},{"stage_qualified",false}},true);
      }
      result.solve_start_ns=p1::monotonic_ns();if(stopping||fatal_||result.solve_start_ns>p.job.deadline_steady_ns){event({{"type","pending_expired_before_native"},{"job_id",p.job.job_id},{"solver_invoked",false},{"now_ns",result.solve_start_ns}});active_=0;continue;}result.solver_invoked=true;
      // W2: bind the boundary to THIS Job before the solve so the internal hook
      // can tell which call it is holding. The gate waits inside the backend's
      // BeforeCall seam, which is after the internal deadline check and
      // immediately before the actual C call.
      if(w2_boundary_){
        w2_boundary_->set_job_deadline(p.job.deadline_steady_ns);
        w2_boundary_->set_clock([]{return p1::monotonic_ns();});
        solver_->attach_boundary(w2_boundary_.get(),[this]{return stopping.load()||fatal_.load();});
      }
      std::pair<Eigen::Vector2d,usv_mpc::SolveInfo> answer;
      try{answer=solver_->solve_owned(p1::job_json(p.job));}catch(...){
        emit_w2_result_if_target_(p.job.job_id);
        event({{"type","cold_start_policy_failure"},{"job_id",p.job.job_id},{"worker_instance",instance_},{"metadata",solver_->last_policy_event()}},true);throw;}
      result.solve_end_ns=p1::monotonic_ns();
      // Record the boundary facts exactly once, for the Job the boundary is
      // bound to. A later Job must not inherit this record: the boundary keeps
      // the last decision, so re-emitting it under a new job_id would attribute
      // one call's facts to another Job.
      emit_w2_result_if_target_(p.job.job_id);
      event({{"type","cold_start_policy_result"},{"job_id",p.job.job_id},{"worker_instance",instance_},{"metadata",solver_->last_policy_event()},{"solve_start_ns",result.solve_start_ns},{"solve_end_ns",result.solve_end_ns}});
      result.success=answer.second.success;result.backend_ms=answer.second.solve_time_ms;
      const auto native_reason=p1::copy_native_reason(answer.second.error,result.reason);if(!native_reason){event({{"type","native_result_resource_oversize"},{"job_id",p.job.job_id},{"field",native_reason.field},{"reason",native_reason.reason},{"observed",native_reason.observed},{"limit",native_reason.limit}});result.reason="native_result_resource_oversize";result.success=false;}
      result.prediction_available=result.success&&answer.second.X_pred.rows()==6&&answer.second.X_pred.cols()==21&&answer.second.U_pred.rows()==2&&answer.second.U_pred.cols()==20&&answer.second.X_pred.allFinite()&&answer.second.U_pred.allFinite()&&answer.first.allFinite();
      if(result.prediction_available){std::copy(answer.first.data(),answer.first.data()+2,result.first_control.begin());std::copy(answer.second.X_pred.data(),answer.second.X_pred.data()+126,result.x_prediction.begin());std::copy(answer.second.U_pred.data(),answer.second.U_pred.data()+40,result.u_prediction.begin());}
      if(delay_)std::this_thread::sleep_for(std::chrono::milliseconds(delay_));
      auto output_resource=p1::check_candidate_resources(result,resources_);if(!output_resource){event({{"type","native_result_resource_oversize"},{"job_id",p.job.job_id},{"field",output_resource.field},{"observed",output_resource.observed},{"limit",output_resource.limit}});throw std::runtime_error("native_result_resource_oversize");}
      generated_candidates_++;event({{"type","candidate"},{"job",p1::job_json(p.job)},{"worker_instance",instance_},{"receive_ns",p.receive},{"solver_invoked",result.solver_invoked},{"backend",result.backend},{"backend_ms",result.backend_ms},{"solve_start_ns",result.solve_start_ns},{"solve_end_ns",result.solve_end_ns},{"success",result.success},{"prediction_available",result.prediction_available},{"first_control",result.first_control},{"X",result.x_prediction},{"U",result.u_prediction},{"reason",result.reason},{"publish_start_ns",p1::monotonic_ns()}});
      if(fatal_)break;
      // W4 drop is recorded here but does NOT short-circuit the tick: falling
      // through keeps the completion counter, the active_job clear and the
      // numerical-failure policy identical to the publish path. Only the
      // out_->publish() call is skipped.
      result_dropped = drop_after_>=0&&generated_candidates_==uint64_t(drop_after_)+1;
      if(result_dropped){
        dropped_candidates_++;
        event({{"type","diagnostic_candidate_dropped"},{"job_id",p.job.job_id},
          {"worker_instance",instance_},{"generated_candidates",generated_candidates_.load()},
          {"policy","generate_once_without_publish"},{"publish_attempted",false}},true);
      } else {
      const auto publish_start=p1::monotonic_ns();
      try{out_->publish(result);published_candidates_++;result_published=true;event({{"type","candidate_publish_result"},{"job_id",p.job.job_id},{"worker_instance",instance_},{"solve_start_ns",result.solve_start_ns},{"solve_end_ns",result.solve_end_ns},{"publish_start_ns",publish_start},{"publish_end_ns",p1::monotonic_ns()},{"success",true}});}catch(...){event({{"type","candidate_publish_result"},{"job_id",p.job.job_id},{"worker_instance",instance_},{"solve_start_ns",result.solve_start_ns},{"solve_end_ns",result.solve_end_ns},{"publish_start_ns",publish_start},{"publish_end_ns",p1::monotonic_ns()},{"success",false}});throw;}
      }
    }catch(const std::exception & e){fatal_=true;result.reason=std::string(e.what()).substr(0,256);result.success=false;result.prediction_available=false;event({{"type","terminal_exception"},{"job_id",p.job.job_id},{"reason",result.reason}});{std::lock_guard<std::mutex> l(mutex_);if(pending_)event({{"type","pending_discarded"},{"job_id",pending_->job.job_id},{"reason","worker_terminal_exception"}});pending_.reset();}break;}
    completed_++;active_=0;
    if(!result.success||!result.prediction_available){
      std::optional<uint64_t> discarded;
      {std::lock_guard<std::mutex> l(mutex_);fatal_=true;terminal_numerical_=true;if(pending_){discarded=pending_->job.job_id;pending_.reset();}}
      event({{"type","terminal_numerical_failure"},{"job_id",p.job.job_id},{"solver_invoked",result.solver_invoked},{"success",result.success},{"prediction_available",result.prediction_available},{"result_published",result_published},{"result_dropped",result_dropped},{"reason",result.reason},{"policy","quarantine_this_run_no_restart"},{"terminal_ns",p1::monotonic_ns()}},true);
      if(discarded)event({{"type","terminal_pending_discarded"},{"job_id",*discarded},{"reason","native_failure_quarantine"}},true);
      break;
    }
  }}
  uint64_t cap_generated_=0,cap_attempt_records_=0,cap_calls_=0,cap_returned_=0,cap_threw_=0,cap_result_records_=0,cap_aborted_=0;
  int64_t cap_last_end_=0;std::string cap_last_sha_;std::atomic<uint64_t> source_rows_generated_{0},source_rows_emitted_{0};std::atomic<bool> source_io_failed_{false};
  std::unique_ptr<formal_owned::Peer> m4_driver_;
  std::unique_ptr<w2_gate::PipeReader> w2_pipe_;std::unique_ptr<w2_gate::Gate> w2_gate_;
  std::unique_ptr<w2_wire::Boundary> w2_boundary_;w2_wire::BoundaryConfig w2_boundary_cfg_;int w2_fd_=-1;
  bool w2_result_emitted_=false;int w2_nonce=0;
  struct W2Channel{uint64_t device=0;uint64_t inode=0;} w2_channel_;
  p1::Json c_;p1::ResourceLimits resources_;std::string run_,hash_,boot_,nominal_,instance_,scope_,owned_file_;bool capability_recording_ready_=false;int delay_=0,block_=0,drop_after_=-1;int64_t startup_=0;bool closed_=false;
  std::string v2_policy_;int v2_ms_=0;std::unique_ptr<v2_diagnostic::Block> v2_block_;
  std::atomic<uint64_t> active_{0},completed_{0},generated_candidates_{0},published_candidates_{0},dropped_candidates_{0};std::atomic<bool> fatal_{false},terminal_numerical_{false};uint64_t last_received_=0;
  std::unique_ptr<owned_cold::Backend> solver_;std::optional<Pending> pending_;std::mutex mutex_,log_mutex_;std::condition_variable cv_;std::thread thread_;std::ofstream file_;
  rclcpp::Publisher<p1::Candidate>::SharedPtr out_;rclcpp::Publisher<p1::Capability>::SharedPtr caps_;rclcpp::Subscription<p1::Job>::SharedPtr sub_;rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr parameters_frozen_;
};
int main(int argc,char **argv){rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,stop_signal);std::signal(SIGTERM,stop_signal);
try{auto node=std::make_shared<Worker>();rclcpp::executors::SingleThreadedExecutor exec;exec.add_node(node);while(!stopping&&rclcpp::ok()){exec.spin_some(std::chrono::milliseconds(10));std::this_thread::sleep_for(std::chrono::milliseconds(1));}exec.remove_node(node);bool closed=node->close_source();node.reset();rclcpp::shutdown();return closed?0:2;}catch(const std::exception & e){fprintf(stderr,"worker fatal: %s\n",e.what());rclcpp::shutdown();return 1;}}
