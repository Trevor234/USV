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
#include "usv_mpc_cpp/acados_backend.hpp"
namespace {std::atomic<bool> stopping{false};void stop_signal(int){stopping=true;}}
class Worker final:public rclcpp::Node {
 public:
  Worker():Node("p1_solver_worker") {
    run_=declare_parameter<std::string>("run_id","");hash_=declare_parameter<std::string>("contract_hash","");
    auto file=declare_parameter<std::string>("contract_file","");c_=p1::load_contract(file,hash_);
    boot_=p1::boot_id();nominal_=c_.at("nominal_hash");instance_=p1::digest(run_+boot_+std::to_string(getpid())+std::to_string(p1::monotonic_ns()));
    if(run_.empty()||run_.size()>128)throw std::runtime_error("run identity invalid");
    delay_=declare_parameter<int>("test_delay_ms",0);block_=declare_parameter<int>("test_native_block_ms",0);
    if(delay_<0||block_<0||delay_>10000||block_>60000||((delay_||block_)&&!c_.at("fault_injection_enabled").get<bool>()))throw std::runtime_error("unqualified fault injection");
    auto log=declare_parameter<std::string>("source_file","");file_.open(log,std::ios::out|std::ios::app);if(!file_)throw std::runtime_error("worker source log unavailable");
    solver_=std::make_unique<usv_mpc::AcadosBackend>(p1::solver_params(c_));
    out_=create_publisher<p1::Candidate>("/p1/solve_candidate",rclcpp::QoS(1).reliable());
    caps_=create_publisher<p1::Capability>("/p1/worker_capability",rclcpp::QoS(1).reliable().transient_local());
    sub_=create_subscription<p1::Job>("/p1/solve_job",rclcpp::QoS(1).reliable(),[this](p1::Job::SharedPtr j){receive(*j);});
    startup_=p1::monotonic_ns();publish_capability();timer_=create_wall_timer(std::chrono::milliseconds(200),[this]{publish_capability();});
    thread_=std::thread([this]{work();});
  }
  ~Worker(){close_source();}
  bool close_source(){if(closed_)return !fatal_;closed_=true;stopping=true;cv_.notify_all();if(thread_.joinable())thread_.join();event({{"type","worker_summary"},{"generated_candidates",generated_candidates_.load()},{"published_candidates",published_candidates_.load()},{"completed_jobs",completed_.load()},{"fatal",fatal_.load()},{"normal_source_complete",!fatal_.load()&&generated_candidates_==published_candidates_},{"finished_ns",p1::monotonic_ns()}});file_.flush();if(!file_)fatal_=true;fprintf(stdout,"WORKER_CLOSE_FLUSH_SUCCESS=%s\n",fatal_?"false":"true");return !fatal_;}
 private:
  void event(const p1::Json & d){std::lock_guard<std::mutex> l(log_mutex_);file_<<d.dump()<<'\n';if(!file_)fatal_=true;}
  void publish_capability(){p1::Capability m;m.schema_version="p1-worker-capability-v1";m.run_id=run_;m.boot_id=boot_;m.contract_hash=hash_;m.nominal_hash=nominal_;m.worker_instance=instance_;m.clock_name="CLOCK_MONOTONIC";m.backend=solver_->backend();m.matrix_layout="column_major";m.horizon_steps=solver_->N();m.prediction_dt=solver_->dt();m.pid=getpid();m.startup_ns=startup_;m.completed_jobs=completed_;m.active_job=active_;{std::lock_guard<std::mutex> l(mutex_);m.pending_count=pending_?1:0;}m.fatal=fatal_;m.fault_injection_enabled=c_.at("fault_injection_enabled");m.reason=fatal_?"worker_log_or_exception":"";caps_->publish(m);}
  void receive(const p1::Job & j){auto now=p1::monotonic_ns();if(fatal_||stopping){event({{"type","job_rejected"},{"job_id",j.job_id},{"reason","worker_terminal"}});return;}auto reason=p1::valid_job(j,run_,boot_,hash_,nominal_,instance_);if(reason.empty()&&now>j.deadline_steady_ns)reason="late_before_native";
    if(!reason.empty()){event({{"type","job_rejected"},{"job_id",j.job_id},{"reason",reason},{"receive_ns",now}});return;}
    std::lock_guard<std::mutex> l(mutex_);
    if(j.job_id<=last_received_){event({{"type","job_rejected"},{"job_id",j.job_id},{"reason","duplicate_or_reordered"}});return;}
    last_received_=j.job_id;
    if(pending_)event({{"type","pending_replaced"},{"job_id",pending_->job.job_id},{"replacement_job_id",j.job_id}});
    pending_=Pending{j,now};cv_.notify_one();
  }
  struct Pending{p1::Job job;int64_t receive;};
  void work(){while(!stopping&&!fatal_){Pending p;{std::unique_lock<std::mutex> l(mutex_);cv_.wait_for(l,std::chrono::milliseconds(100),[this]{return stopping||pending_.has_value();});if(stopping||fatal_){pending_.reset();break;}if(!pending_)continue;p=*pending_;pending_.reset();active_=p.job.job_id;}
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
      if(block_){event({{"type","controlled_pre_native_barrier"},{"job_id",p.job.job_id},{"start_ns",p1::monotonic_ns()},{"duration_ms",block_},{"actual_native_invoked",false}});std::this_thread::sleep_for(std::chrono::milliseconds(block_));}
      result.solve_start_ns=p1::monotonic_ns();if(stopping||fatal_||result.solve_start_ns>p.job.deadline_steady_ns){event({{"type","pending_expired_before_native"},{"job_id",p.job.job_id},{"solver_invoked",false},{"now_ns",result.solve_start_ns}});active_=0;continue;}result.solver_invoked=true;
      auto answer=solver_->solve(x,ref);result.solve_end_ns=p1::monotonic_ns();
      result.success=answer.second.success;result.backend_ms=answer.second.solve_time_ms;result.reason=answer.second.error;
      result.prediction_available=result.success&&answer.second.X_pred.rows()==6&&answer.second.X_pred.cols()==21&&answer.second.U_pred.rows()==2&&answer.second.U_pred.cols()==20&&answer.second.X_pred.allFinite()&&answer.second.U_pred.allFinite()&&answer.first.allFinite();
      if(result.prediction_available){std::copy(answer.first.data(),answer.first.data()+2,result.first_control.begin());std::copy(answer.second.X_pred.data(),answer.second.X_pred.data()+126,result.x_prediction.begin());std::copy(answer.second.U_pred.data(),answer.second.U_pred.data()+40,result.u_prediction.begin());}
      if(delay_)std::this_thread::sleep_for(std::chrono::milliseconds(delay_));
      generated_candidates_++;event({{"type","candidate"},{"job",p1::job_json(p.job)},{"worker_instance",instance_},{"receive_ns",p.receive},{"solver_invoked",result.solver_invoked},{"backend",result.backend},{"backend_ms",result.backend_ms},{"solve_start_ns",result.solve_start_ns},{"solve_end_ns",result.solve_end_ns},{"success",result.success},{"prediction_available",result.prediction_available},{"first_control",result.first_control},{"X",result.x_prediction},{"U",result.u_prediction},{"reason",result.reason},{"publish_start_ns",p1::monotonic_ns()}});
      if(fatal_)break;
      out_->publish(result);published_candidates_++;
    }catch(const std::exception & e){fatal_=true;result.reason=std::string(e.what()).substr(0,256);result.success=false;result.prediction_available=false;event({{"type","terminal_exception"},{"job_id",p.job.job_id},{"reason",result.reason}});{std::lock_guard<std::mutex> l(mutex_);pending_.reset();}break;}
    completed_++;active_=0;
  }}
  p1::Json c_;std::string run_,hash_,boot_,nominal_,instance_;int delay_=0,block_=0;int64_t startup_=0;bool closed_=false;
  std::atomic<uint64_t> active_{0},completed_{0},generated_candidates_{0},published_candidates_{0};std::atomic<bool> fatal_{false};uint64_t last_received_=0;
  std::unique_ptr<usv_mpc::AcadosBackend> solver_;std::optional<Pending> pending_;std::mutex mutex_,log_mutex_;std::condition_variable cv_;std::thread thread_;std::ofstream file_;
  rclcpp::Publisher<p1::Candidate>::SharedPtr out_;rclcpp::Publisher<p1::Capability>::SharedPtr caps_;rclcpp::Subscription<p1::Job>::SharedPtr sub_;rclcpp::TimerBase::SharedPtr timer_;
};
int main(int argc,char **argv){rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,stop_signal);std::signal(SIGTERM,stop_signal);
try{auto node=std::make_shared<Worker>();rclcpp::executors::SingleThreadedExecutor exec;exec.add_node(node);while(!stopping&&rclcpp::ok()){exec.spin_some(std::chrono::milliseconds(10));std::this_thread::sleep_for(std::chrono::milliseconds(1));}exec.remove_node(node);bool closed=node->close_source();node.reset();rclcpp::shutdown();return closed?0:2;}catch(const std::exception & e){fprintf(stderr,"worker fatal: %s\n",e.what());rclcpp::shutdown();return 1;}}
