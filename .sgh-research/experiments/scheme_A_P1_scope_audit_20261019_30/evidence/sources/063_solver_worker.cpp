// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include <atomic>
#include <condition_variable>
#include <mutex>
#include <optional>
#include <thread>
#include <csignal>
#include <rclcpp/rclcpp.hpp>
#include "protocol.hpp"
#include "owned_cold_backend.hpp"
#include "p1_owned_identity.hpp"
#include "capability_source_v4.hpp"
#ifndef P1_OWNED_SOURCE_BUNDLE_SHA256
#error "owned Worker requires source bundle identity"
#endif
namespace {std::atomic<bool> stopping{false};void stop_signal(int){stopping=true;}}
class Worker final:public rclcpp::Node {
 public:
  Worker():Node("p1_solver_worker") {
    run_=declare_parameter<std::string>("run_id","");hash_=declare_parameter<std::string>("contract_hash","");
    auto file=declare_parameter<std::string>("contract_file","");c_=p1::load_contract(file,hash_);resources_=p1::resource_limits_from_contract(c_);
    boot_=p1::boot_id();nominal_=c_.at("nominal_hash");instance_=p1::digest(run_+boot_+std::to_string(getpid())+std::to_string(p1::monotonic_ns()));
    if(run_.empty()||run_.size()>128)throw std::runtime_error("run identity invalid");
    delay_=declare_parameter<int>("test_delay_ms",0);block_=declare_parameter<int>("test_native_block_ms",0);
    if(delay_<0||block_<0||delay_>10000||block_>60000||((delay_||block_)&&!c_.at("fault_injection_enabled").get<bool>()))throw std::runtime_error("unqualified fault injection");
    if(c_.value("worker_failure_policy",std::string{})!="terminal_on_failed_or_invalid_native_result")throw std::runtime_error("undeclared worker failure policy");
    auto log=declare_parameter<std::string>("source_file","");file_.open(log,std::ios::out|std::ios::app);if(!file_)throw std::runtime_error("worker source log unavailable");
    if(c_.at("recording_ready_timeout_ns").get<int64_t>()<=0||c_.at("recording_ready_timeout_ns").get<int64_t>()>60000000000LL)throw std::runtime_error("invalid finite recording timeout");
    solver_=std::make_unique<owned_cold::Backend>(p1::solver_params(c_),p1::Json{{"run_id",run_},{"boot_id",boot_},{"contract_hash",hash_},{"nominal_hash",nominal_},{"worker_instance",instance_}},true);
    out_=create_publisher<p1::Candidate>("/p1/solve_candidate",rclcpp::QoS(1).reliable());
    caps_=create_publisher<p1::Capability>("/p1/worker_capability",rclcpp::QoS(1).reliable().transient_local());
    sub_=create_subscription<p1::Job>("/p1/solve_job",rclcpp::QoS(1).reliable(),[this](p1::Job::SharedPtr j){receive(*j);});
    const auto owned_file=declare_parameter<std::string>("owned_manifest_file","");owned_file_=owned_file;
    parameters_frozen_=p1_owned::freeze_parameters(*this);
    const auto endpoints=p1_owned::Json::array({
      p1_owned::publisher_endpoint(*out_,"usv_research_interfaces/msg/SolveCandidate"),
      p1_owned::publisher_endpoint(*caps_,"usv_research_interfaces/msg/WorkerCapability"),
      p1_owned::subscription_endpoint(*sub_,"usv_research_interfaces/msg/SolveJob")});
    p1_owned::write_create_only(owned_file,p1_owned::role_manifest(*this,"worker",run_,hash_,P1_OWNED_SOURCE_BUNDLE_SHA256,endpoints,
      {{"worker_instance",instance_},{"nominal_hash",nominal_},{"source_fd",p1_owned::source_fd_identity(log)},
       {"runtime_hook_values",{{"test_delay_ms",delay_},{"test_native_block_ms",block_}}},
       {"fault_injection_permission",c_.at("fault_injection_enabled")},{"contract_configuration",c_}}));
    startup_=p1::monotonic_ns();
    event({{"type","capability_source_header"},{"schema","p1-capability-source-header-v1"},
      {"run_id",run_},{"boot_id",boot_},{"pid",getpid()},{"process_start_ticks",p1_owned::process_start_ticks()},
      {"worker_instance",instance_},{"startup_ns",startup_},{"contract_hash",hash_},{"nominal_hash",nominal_},
      {"source_bundle_sha256",P1_OWNED_SOURCE_BUNDLE_SHA256},{"binary_sha256",p1_owned::file_sha256("/proc/self/exe")},
      {"owned_manifest_sha256",p1_owned::file_sha256(owned_file_)},{"endpoint",p1_owned::publisher_endpoint(*caps_,"usv_research_interfaces/msg/WorkerCapability")},
      {"clock","CLOCK_MONOTONIC"},{"wire_contract_unchanged",true}},true);
    if(fatal_)throw std::runtime_error("capability source header failed");publish_capability();timer_=create_wall_timer(std::chrono::milliseconds(200),[this]{publish_capability();});
    thread_=std::thread([this]{work();});
  }
  ~Worker(){close_source();}
  bool close_source(){if(closed_)return !fatal_;closed_=true;stopping=true;cv_.notify_all();if(thread_.joinable())thread_.join();{std::lock_guard<std::mutex> l(mutex_);if(pending_){event({{"type","pending_discarded"},{"job_id",pending_->job.job_id},{"reason","worker_close"}});pending_.reset();}}event({{"type","worker_summary"},{"generated_candidates",generated_candidates_.load()},{"published_candidates",published_candidates_.load()},{"completed_jobs",completed_.load()},{"fatal",fatal_.load()},{"terminal_numerical_failure",terminal_numerical_.load()},{"normal_source_complete",!fatal_.load()&&generated_candidates_==published_candidates_},{"capability_source",capability_terminal()},{"source_rows_before_terminal",source_rows_generated_.load()},{"source_rows_emitted_before_terminal",source_rows_emitted_.load()},{"source_io_failed",source_io_failed_.load()},{"finished_ns",p1::monotonic_ns()}});file_.flush();const bool flush_ok=bool(file_);if(!flush_ok)fatal_=true;fprintf(stdout,"WORKER_CLOSE_FLUSH_SUCCESS=%s\n",flush_ok?"true":"false");return !fatal_;}
 private:
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
    try {
      if(p.job.reset_warmstart)solver_->reset_warmstart();
      solver_->set_applied_control({p.job.anchor_n[0],p.job.anchor_n[1]});
      usv_mpc::Vector6d x;std::copy(p.job.target_state.begin(),p.job.target_state.end(),x.data());
      Eigen::MatrixXd ref(6,21);std::copy(p.job.reference.begin(),p.job.reference.end(),ref.data());
      result.solve_start_ns=p1::monotonic_ns();if(result.solve_start_ns>p.job.deadline_steady_ns){event({{"type","pending_expired_before_native"},{"job_id",p.job.job_id},{"solver_invoked",false},{"now_ns",result.solve_start_ns}});active_=0;continue;}
      // Controlled barrier is deliberately in the native-owned path; an owned
      // supervisor must TERM/KILL this process if its active watchdog expires.
      if(block_){event({{"type","controlled_pre_native_barrier"},{"job_id",p.job.job_id},{"start_ns",p1::monotonic_ns()},{"duration_ms",block_},{"actual_native_invoked",false},{"flush_requested",true}},true);if(fatal_){active_=0;{std::lock_guard<std::mutex> l(mutex_);pending_.reset();}break;}std::this_thread::sleep_for(std::chrono::milliseconds(block_));}
      result.solve_start_ns=p1::monotonic_ns();if(stopping||fatal_||result.solve_start_ns>p.job.deadline_steady_ns){event({{"type","pending_expired_before_native"},{"job_id",p.job.job_id},{"solver_invoked",false},{"now_ns",result.solve_start_ns}});active_=0;continue;}result.solver_invoked=true;
      std::pair<Eigen::Vector2d,usv_mpc::SolveInfo> answer;
      try{answer=solver_->solve_owned(p1::job_json(p.job));}catch(...){event({{"type","cold_start_policy_failure"},{"job_id",p.job.job_id},{"worker_instance",instance_},{"metadata",solver_->last_policy_event()}},true);throw;}
      result.solve_end_ns=p1::monotonic_ns();
      event({{"type","cold_start_policy_result"},{"job_id",p.job.job_id},{"worker_instance",instance_},{"metadata",solver_->last_policy_event()},{"solve_start_ns",result.solve_start_ns},{"solve_end_ns",result.solve_end_ns}});
      result.success=answer.second.success;result.backend_ms=answer.second.solve_time_ms;
      const auto native_reason=p1::copy_native_reason(answer.second.error,result.reason);if(!native_reason){event({{"type","native_result_resource_oversize"},{"job_id",p.job.job_id},{"field",native_reason.field},{"reason",native_reason.reason},{"observed",native_reason.observed},{"limit",native_reason.limit}});result.reason="native_result_resource_oversize";result.success=false;}
      result.prediction_available=result.success&&answer.second.X_pred.rows()==6&&answer.second.X_pred.cols()==21&&answer.second.U_pred.rows()==2&&answer.second.U_pred.cols()==20&&answer.second.X_pred.allFinite()&&answer.second.U_pred.allFinite()&&answer.first.allFinite();
      if(result.prediction_available){std::copy(answer.first.data(),answer.first.data()+2,result.first_control.begin());std::copy(answer.second.X_pred.data(),answer.second.X_pred.data()+126,result.x_prediction.begin());std::copy(answer.second.U_pred.data(),answer.second.U_pred.data()+40,result.u_prediction.begin());}
      if(delay_)std::this_thread::sleep_for(std::chrono::milliseconds(delay_));
      auto output_resource=p1::check_candidate_resources(result,resources_);if(!output_resource){event({{"type","native_result_resource_oversize"},{"job_id",p.job.job_id},{"field",output_resource.field},{"observed",output_resource.observed},{"limit",output_resource.limit}});throw std::runtime_error("native_result_resource_oversize");}
      generated_candidates_++;event({{"type","candidate"},{"job",p1::job_json(p.job)},{"worker_instance",instance_},{"receive_ns",p.receive},{"solver_invoked",result.solver_invoked},{"backend",result.backend},{"backend_ms",result.backend_ms},{"solve_start_ns",result.solve_start_ns},{"solve_end_ns",result.solve_end_ns},{"success",result.success},{"prediction_available",result.prediction_available},{"first_control",result.first_control},{"X",result.x_prediction},{"U",result.u_prediction},{"reason",result.reason},{"publish_start_ns",p1::monotonic_ns()}});
      if(fatal_)break;
      const auto publish_start=p1::monotonic_ns();
      try{out_->publish(result);published_candidates_++;event({{"type","candidate_publish_result"},{"job_id",p.job.job_id},{"worker_instance",instance_},{"solve_start_ns",result.solve_start_ns},{"solve_end_ns",result.solve_end_ns},{"publish_start_ns",publish_start},{"publish_end_ns",p1::monotonic_ns()},{"success",true}});}catch(...){event({{"type","candidate_publish_result"},{"job_id",p.job.job_id},{"worker_instance",instance_},{"solve_start_ns",result.solve_start_ns},{"solve_end_ns",result.solve_end_ns},{"publish_start_ns",publish_start},{"publish_end_ns",p1::monotonic_ns()},{"success",false}});throw;}
    }catch(const std::exception & e){fatal_=true;result.reason=std::string(e.what()).substr(0,256);result.success=false;result.prediction_available=false;event({{"type","terminal_exception"},{"job_id",p.job.job_id},{"reason",result.reason}});{std::lock_guard<std::mutex> l(mutex_);if(pending_)event({{"type","pending_discarded"},{"job_id",pending_->job.job_id},{"reason","worker_terminal_exception"}});pending_.reset();}break;}
    completed_++;active_=0;
    if(!result.success||!result.prediction_available){
      std::optional<uint64_t> discarded;
      {std::lock_guard<std::mutex> l(mutex_);fatal_=true;terminal_numerical_=true;if(pending_){discarded=pending_->job.job_id;pending_.reset();}}
      event({{"type","terminal_numerical_failure"},{"job_id",p.job.job_id},{"solver_invoked",result.solver_invoked},{"success",result.success},{"prediction_available",result.prediction_available},{"result_published",true},{"reason",result.reason},{"policy","quarantine_this_run_no_restart"},{"terminal_ns",p1::monotonic_ns()}},true);
      if(discarded)event({{"type","terminal_pending_discarded"},{"job_id",*discarded},{"reason","native_failure_quarantine"}},true);
      break;
    }
  }}
  uint64_t cap_generated_=0,cap_attempt_records_=0,cap_calls_=0,cap_returned_=0,cap_threw_=0,cap_result_records_=0,cap_aborted_=0;
  int64_t cap_last_end_=0;std::string cap_last_sha_;std::atomic<uint64_t> source_rows_generated_{0},source_rows_emitted_{0};std::atomic<bool> source_io_failed_{false};
  p1::Json c_;p1::ResourceLimits resources_;std::string run_,hash_,boot_,nominal_,instance_,owned_file_;bool capability_recording_ready_=false;int delay_=0,block_=0;int64_t startup_=0;bool closed_=false;
  std::atomic<uint64_t> active_{0},completed_{0},generated_candidates_{0},published_candidates_{0};std::atomic<bool> fatal_{false},terminal_numerical_{false};uint64_t last_received_=0;
  std::unique_ptr<owned_cold::Backend> solver_;std::optional<Pending> pending_;std::mutex mutex_,log_mutex_;std::condition_variable cv_;std::thread thread_;std::ofstream file_;
  rclcpp::Publisher<p1::Candidate>::SharedPtr out_;rclcpp::Publisher<p1::Capability>::SharedPtr caps_;rclcpp::Subscription<p1::Job>::SharedPtr sub_;rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr parameters_frozen_;
};
int main(int argc,char **argv){rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,stop_signal);std::signal(SIGTERM,stop_signal);
try{auto node=std::make_shared<Worker>();rclcpp::executors::SingleThreadedExecutor exec;exec.add_node(node);while(!stopping&&rclcpp::ok()){exec.spin_some(std::chrono::milliseconds(10));std::this_thread::sleep_for(std::chrono::milliseconds(1));}exec.remove_node(node);bool closed=node->close_source();node.reset();rclcpp::shutdown();return closed?0:2;}catch(const std::exception & e){fprintf(stderr,"worker fatal: %s\n",e.what());rclcpp::shutdown();return 1;}}
