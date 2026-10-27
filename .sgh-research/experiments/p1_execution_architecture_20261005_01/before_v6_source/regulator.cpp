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
#include <rosgraph_msgs/msg/clock.hpp>
#include "usv_research_interfaces/msg/applied_control.hpp"
#include "usv_mpc_cpp/p1_input_core.hpp"
#include "protocol.hpp"
#include "p1_admission.hpp"
namespace {std::atomic<bool> stop_requested{false};void stop_signal(int){stop_requested=true;}}
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
    c_=p1::load_contract(declare_parameter<std::string>("contract_file",""),hash_);boot_=p1::boot_id();nominal_=c_.at("nominal_hash");
    legacy_run_=declare_parameter<std::string>("legacy_run_id","");expected_worker_pid_=declare_parameter<int64_t>("worker_pid",0);
    recording_observer_=declare_parameter<std::string>("recording_observer_node","p1_calibration_driver");
    if(recording_observer_.empty()||recording_observer_.size()>128)throw std::runtime_error("invalid bounded recording observer node");
    if(run_.empty()||run_.size()>128||(mode_!="shadow"&&mode_!="execute"&&mode_!="no_output"))throw std::runtime_error("identity/mode invalid");
    if(mode_=="execute"&&(!c_.at("execute_qualified").get<bool>()||c_.at("parameters_are_diagnostic_only").get<bool>()))throw std::runtime_error("execute contract is unqualified");
    limits_.tolerance=c_.at("activation_tolerance").get<p1::State>();limits_.rho=c_.at("rho_n_s");limits_.hold_ns=c_.at("hold_ns");limits_.low=c_.at("command_min_n");limits_.high=c_.at("command_max_n");if(!limits_.valid())throw std::runtime_error("invalid finite limits");
    const std::array<std::string,21> positive={"odom_age_ns","imu_age_ns","mixed_skew_ns","clock_age_ns","clock_pause_confirm_ns","target_sim_slack_ns","tick_jitter_ns","publish_gap_ns","publish_budget_ns","active_watchdog_ns","worker_grace_ns","term_grace_ns","kill_postcheck_ns","shutdown_grace_ns","max_path_points","history_capacity","log_capacity","odom_sim_lag_ns","imu_sim_lag_ns","source_future_slack_ns","recording_ready_timeout_ns"};for(auto & k:positive)if(c_.at(k).get<int64_t>()<=0)throw std::runtime_error("missing/invalid bound: "+k);if(c_.at("recording_ready_timeout_ns").get<int64_t>()>60000000000LL)throw std::runtime_error("invalid finite recording timeout");
    for(const auto & key:{"expected_pose_frame","expected_child_frame","expected_imu_frame"}){const auto frame=c_.at(key).get<std::string>();if(frame.empty()||frame.size()>128)throw std::runtime_error("invalid bounded expected frame");}
    params_=p1::solver_params(c_);ref_=std::make_shared<const usv_mpc::ReferenceInput>();
    job_pub_=create_publisher<p1::Job>("/p1/solve_job",rclcpp::QoS(1).reliable());decision_pub_=create_publisher<p1::Decision>("/p1/execution_decision",rclcpp::QoS(1).reliable());
    sink_=std::make_unique<Sink>(declare_parameter<std::string>("source_file",""),c_.at("log_capacity"),decision_pub_);
    if(mode_=="execute") {left_=create_publisher<std_msgs::msg::Float64>(c_.at("output_topics").at("left").get<std::string>(),rclcpp::QoS(1).reliable());right_=create_publisher<std_msgs::msg::Float64>(c_.at("output_topics").at("right").get<std::string>(),rclcpp::QoS(1).reliable());}
    odom_=create_subscription<nav_msgs::msg::Odometry>(c_.at("input_topics").at("odom").get<std::string>(),rclcpp::SensorDataQoS(),[this](nav_msgs::msg::Odometry::SharedPtr m){odom(*m);});
    imu_=create_subscription<sensor_msgs::msg::Imu>(c_.at("input_topics").at("imu").get<std::string>(),rclcpp::SensorDataQoS(),[this](sensor_msgs::msg::Imu::SharedPtr m){imu(*m);});
    path_=create_subscription<nav_msgs::msg::Path>(c_.at("input_topics").at("path").get<std::string>(),rclcpp::QoS(1).reliable(),[this](nav_msgs::msg::Path::SharedPtr m){path(*m);});
    profile_=create_subscription<std_msgs::msg::Float64MultiArray>(c_.at("input_topics").at("profile").get<std::string>(),rclcpp::QoS(1).reliable(),[this](std_msgs::msg::Float64MultiArray::SharedPtr m){profile(*m);});
    clock_=create_subscription<rosgraph_msgs::msg::Clock>("/clock",rclcpp::ClockQoS(),[this](rosgraph_msgs::msg::Clock::SharedPtr m){clock(*m);});
    candidates_=create_subscription<p1::Candidate>("/p1/solve_candidate",rclcpp::QoS(1).reliable(),[this](p1::Candidate::SharedPtr m){candidate(*m);});
    capabilities_=create_subscription<p1::Capability>("/p1/worker_capability",rclcpp::QoS(1).reliable().transient_local(),[this](p1::Capability::SharedPtr m){capability(*m);});
    stop_=create_subscription<std_msgs::msg::Bool>("/p1/stop",rclcpp::QoS(1).reliable(),[](std_msgs::msg::Bool::SharedPtr m){if(m->data)stop_requested=true;});
    if(mode_=="shadow")applied_=create_subscription<usv_research_interfaces::msg::AppliedControl>("/research/control/applied",rclcpp::QoS(10).reliable(),[this](usv_research_interfaces::msg::AppliedControl::SharedPtr m){legacy_applied(*m);});
    if(mode_=="no_output") {auto now=p1::monotonic_ns();anchor_.known={true,true};anchor_.seq={1,1};anchor_.time={now,now};}
    wait_recording_ready();prep_=std::thread([this]{prepare_loop();});tick_=std::thread([this]{tick_loop();});
    sink_->add({{"type","startup"},{"schema","p1-regulator-v1"},{"run_id",run_},{"mode",mode_},{"pid",getpid()},{"boot",boot_},{"clock","CLOCK_MONOTONIC"},{"contract_hash",hash_},{"physical_publisher_endpoints",mode_=="execute"?2:0},{"input_anchor_source",mode_=="shadow"?"legacy_publisher":mode_=="execute"?"regulator_publisher":"synthetic_static_fixture"},{"diagnostic_only",mode_!="execute"}});
  }
  ~Regulator(){stop_requested=true;prep_stop_=true;prep_cv_.notify_all();if(tick_.joinable())tick_.join();if(prep_.joinable())prep_.join();sink_->close();}
  bool finished()const{return finished_;}
  bool close_source(){if(tick_.joinable())tick_.join();prep_stop_=true;prep_cv_.notify_all();if(prep_.joinable())prep_.join();sink_->close();fprintf(stdout,"REGULATOR_CLOSE_FLUSH_SUCCESS=%s\n",sink_->failed()?"false":"true");return !sink_->failed();}
 private:
  static int64_t stamp(const builtin_interfaces::msg::Time & t){return int64_t(t.sec)*1000000000+t.nanosec;}
  struct Snapshot {usv_mpc::Vector6d state=usv_mpc::Vector6d::Zero();std::shared_ptr<const usv_mpc::ReferenceInput> ref;std::vector<usv_mpc::HeldInputEvent> history;p1::Anchor anchor;p1::Version version;uint64_t odom_seq=0,imu_seq=0;int64_t odom_stamp=0,imu_stamp=0,odom_receive=0,imu_receive=0,clock_receive=0,sim=0,freeze=0;bool mixed=false,paused=false,rtf_valid=false;double rtf=0;std::string anchor_producer,anchor_run,anchor_source;};
  struct Preparation {Snapshot s;uint64_t tick;int64_t origin;};
  Snapshot snapshot_locked(int64_t now){Snapshot s;s.state=state_;s.ref=ref_;s.history.assign(history_.begin(),history_.end());s.anchor=anchor_;s.version=version_;s.odom_seq=odom_seq_;s.imu_seq=imu_seq_;s.odom_stamp=odom_stamp_;s.imu_stamp=imu_stamp_;s.odom_receive=odom_receive_;s.imu_receive=imu_receive_;s.clock_receive=clock_receive_;s.sim=sim_;s.freeze=now;s.mixed=mixed_;s.paused=paused_;s.rtf_valid=rtf_valid_;s.rtf=rtf_;s.anchor_source=mode_=="shadow"?"legacy_publisher":mode_=="execute"?"regulator_publisher":"synthetic_static_fixture";s.anchor_producer=mode_=="shadow"?legacy_producer_:p1::digest(run_+boot_+std::to_string(getpid()));s.anchor_run=mode_=="shadow"?legacy_run_:run_;return s;}
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
      const bool ready=job_pub_->get_subscription_count()>=2&&decision_pub_->get_subscription_count()>=2&&
        named_subscription("/p1/solve_job","p1_solver_worker")&&named_subscription("/p1/solve_job","",true)&&
        named_subscription("/p1/execution_decision",recording_observer_)&&named_subscription("/p1/execution_decision","",true)&&
        named_subscription("/p1/solve_candidate","p1_regulator")&&named_subscription("/p1/solve_candidate","",true);
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

  void invalidate_locked(){admission_.invalidate();candidate_.reset();{std::lock_guard<std::mutex> l(prep_mutex_);pending_.reset();}}
  void odom(const nav_msgs::msg::Odometry & m){auto now=p1::monotonic_ns();auto & p=m.pose.pose.position;auto & q=m.pose.pose.orientation;auto & t=m.twist.twist;std::array<double,5> a={p.x,p.y,t.linear.x,t.linear.y,t.angular.z};std::array<double,4> quat={q.x,q.y,q.z,q.w};bool valid=usv_mpc::admit_odom(a,quat)&&m.header.frame_id==c_.at("expected_pose_frame")&&m.child_frame_id==c_.at("expected_child_frame");std::lock_guard<std::mutex> l(mutex_);++odom_received_;
    if(valid){state_=usv_mpc::compose_odom(a,quat);odom_seq_=odom_received_;odom_stamp_=stamp(m.header.stamp);odom_receive_=now;mixed_=false;}
    sink_->add({{"type","odom_admission"},{"sequence",odom_received_},{"valid",valid},{"pose_frame",m.header.frame_id.substr(0,128)},{"pose_frame_truncated",m.header.frame_id.size()>128},{"child_frame",m.child_frame_id.substr(0,128)},{"child_frame_truncated",m.child_frame_id.size()>128},{"accepted_sequence",odom_seq_},{"stamp_ns",stamp(m.header.stamp)},{"receive_ns",now},{"state",std::array<double,6>{state_[0],state_[1],state_[2],state_[3],state_[4],state_[5]}}});
  }
  void imu(const sensor_msgs::msg::Imu & m){auto now=p1::monotonic_ns();std::lock_guard<std::mutex> l(mutex_);++imu_received_;const bool valid=usv_mpc::admit_imu(m.angular_velocity.z)&&m.header.frame_id==c_.at("expected_imu_frame");if(valid){usv_mpc::compose_imu(state_,m.angular_velocity.z);imu_seq_=imu_received_;imu_stamp_=stamp(m.header.stamp);imu_receive_=now;mixed_=true;}sink_->add({{"type","imu_admission"},{"sequence",imu_received_},{"valid",valid},{"frame_id",m.header.frame_id.substr(0,128)},{"frame_truncated",m.header.frame_id.size()>128},{"r_value",m.angular_velocity.z},{"accepted_sequence",imu_seq_},{"stamp_ns",stamp(m.header.stamp)},{"receive_ns",now}});}
  void path(const nav_msgs::msg::Path & m){auto next=std::make_shared<usv_mpc::ReferenceInput>();std::string fingerprint;
    bool valid=m.poses.size()<=c_.at("max_path_points").get<size_t>()&&m.header.frame_id==c_.at("expected_pose_frame");
    if(valid)for(auto & p:m.poses){auto & q=p.pose.orientation;double yaw=usv_mpc::quaternion_to_yaw(q.x,q.y,q.z,q.w);if(!std::isfinite(p.pose.position.x)||!std::isfinite(p.pose.position.y)||!std::isfinite(yaw)){valid=false;break;}next->path.push_back({p.pose.position.x,p.pose.position.y,yaw});}
    if(!valid)next->path.clear();fingerprint=p1::digest(p1::Json{{"frame",m.header.frame_id},{"path",next->path}}.dump());
    std::lock_guard<std::mutex> l(mutex_);next->profile=ref_->profile;next->profile_stamp=ref_->profile_stamp;next->profile_sequence=ref_->profile_sequence;next->path_sequence=++path_seq_;next->path_stamp={m.header.stamp.sec,int(m.header.stamp.nanosec)};
    if(fingerprint!=path_fingerprint_||next->path.size()<2){version_.task++;path_fingerprint_=fingerprint;invalidate_locked();}
    ref_=next;sink_->add({{"type","path_version"},{"received_sequence",path_seq_},{"task_generation",version_.task},{"fingerprint",fingerprint},{"points",next->path.size()},{"valid",valid},{"processed_ns",p1::monotonic_ns()}});
  }
  void profile(const std_msgs::msg::Float64MultiArray & m){auto next=std::make_shared<usv_mpc::ReferenceInput>();bool valid=!m.data.empty()&&m.data.size()%4==0&&m.data.size()/4<=c_.at("max_profile_rows").get<size_t>();std::vector<std::string> labels;for(auto & d:m.layout.dim)labels.push_back(d.label);bool stamp_ok=false;next->profile_stamp=usv_mpc::parse_profile_stamp(labels,stamp_ok);if(!stamp_ok)next->profile_stamp={-1,-1};
    if(valid){for(size_t i=0;i<m.data.size()/4;++i){std::array<double,4> r={m.data[4*i],m.data[4*i+1],m.data[4*i+2],m.data[4*i+3]};if(!p1::finite_array(r)||(i&&r[3]<=m.data[4*(i-1)+3])){valid=false;break;}next->profile.push_back(r);}}if(!valid)next->profile.clear();auto fp=p1::digest(p1::Json(next->profile).dump());
    std::lock_guard<std::mutex> l(mutex_);next->path=ref_->path;next->path_stamp=ref_->path_stamp;next->path_sequence=ref_->path_sequence;next->profile_sequence=++profile_seq_;if(fp!=profile_fingerprint_){version_.task++;profile_fingerprint_=fp;invalidate_locked();}ref_=next;sink_->add({{"type","profile_version"},{"received_sequence",profile_seq_},{"task_generation",version_.task},{"fingerprint",fp},{"rows",next->profile.size()},{"valid",valid},{"processed_ns",p1::monotonic_ns()}});
  }
  void clock(const rosgraph_msgs::msg::Clock & m){auto now=p1::monotonic_ns(),s=stamp(m.clock);std::lock_guard<std::mutex> l(mutex_);if(clock_receive_&&(s<sim_||s-sim_>5000000000LL)){version_.epoch++;version_.schedule++;clock_samples_.clear();rtf_valid_=false;invalidate_locked();}
    if(s!=sim_){last_clock_advance_=now;if(paused_){paused_=false;version_.schedule++;invalidate_locked();}}
    sim_=s;clock_receive_=now;clock_samples_.push_back({now,s});while(clock_samples_.size()>100||(!clock_samples_.empty()&&now-clock_samples_.front().first>600000000))clock_samples_.pop_front();
    if(clock_samples_.size()>1&&now-clock_samples_.front().first>=400000000){double rtf=double(s-clock_samples_.front().second)/double(now-clock_samples_.front().first);rtf_valid_=rtf>=c_.at("rtf_low").get<double>()&&rtf<=c_.at("rtf_high").get<double>();rtf_=rtf;}
    sink_->add({{"type","clock"},{"sim_ns",s},{"receive_ns",now},{"epoch",version_.epoch},{"schedule_generation",version_.schedule},{"paused",paused_.load()},{"rtf",rtf_},{"rtf_valid",rtf_valid_.load()}});
  }
  void capability(const p1::Capability & m){std::lock_guard<std::mutex> l(mutex_);bool identity=m.run_id==run_&&m.boot_id==boot_&&m.contract_hash==hash_&&m.nominal_hash==nominal_&&m.pid==expected_worker_pid_;if(!identity){sink_->add({{"type","foreign_capability_ignored"},{"pid",m.pid},{"run_id",m.run_id}});return;}bool valid=m.schema_version=="p1-worker-capability-v1"&&m.run_id==run_&&m.boot_id==boot_&&m.contract_hash==hash_&&m.nominal_hash==nominal_&&m.clock_name=="CLOCK_MONOTONIC"&&m.backend=="acados"&&m.matrix_layout=="column_major"&&m.horizon_steps==20&&m.prediction_dt==.2&&!m.fatal&&m.pid==expected_worker_pid_;
    if(!worker_instance_.empty()&&worker_instance_!=m.worker_instance){worker_unusable_=true;invalidate_locked();}
    if(valid&&!worker_unusable_){worker_instance_=m.worker_instance;worker_valid_=true;}
    if(m.fatal){worker_unusable_=true;worker_valid_=false;normal_complete_=false;invalidate_locked();}
    if(m.active_job!=worker_active_){worker_active_=m.active_job;worker_active_since_=p1::monotonic_ns();}
  }
  void legacy_applied(const usv_research_interfaces::msg::AppliedControl & m){std::lock_guard<std::mutex> l(mutex_);if(m.run_id!=legacy_run_||m.baseline_id!="F5_20261005_atomic_freeze_01"||m.event_semantics!="publisher_command"||m.steady_clock_domain.find(boot_)==std::string::npos||m.map_scale!=1||!p1::finite_array(m.final_n))return;
    if(!legacy_producer_.empty()&&legacy_producer_!=m.producer_instance_id){anchor_.known={false,false};worker_unusable_=true;invalidate_locked();return;}legacy_producer_=m.producer_instance_id;
    for(int i=0;i<2;++i){bool success=i?m.right_publish_success:m.left_publish_success;int64_t time=i?m.right_publish_start_steady_ns:m.left_publish_start_steady_ns;int64_t sim=i?m.right_sim_time_ns:m.left_sim_time_ns;
      if(!success){anchor_.known[i]=false;normal_complete_=false;invalidate_locked();continue;}anchor_.n[i]=m.final_n[i];anchor_.seq[i]=m.sequence;anchor_.time[i]=time;anchor_.known[i]=true;push_history_locked({sim,i,m.final_n[i]});}
    sink_->add({{"type","legacy_anchor"},{"producer",m.producer_instance_id},{"run_id",m.run_id},{"sequence",m.sequence},{"final_n",m.final_n},{"known",anchor_.known},{"publish_ns",anchor_.time},{"clock_epoch",m.clock_epoch}});
  }
  void push_history_locked(const usv_mpc::HeldInputEvent & e){if(!history_.empty()&&e.sim_ns<history_.back().sim_ns){history_.clear();anchor_.known={false,false};return;}history_.push_back(e);while(history_.size()>c_.at("history_capacity").get<size_t>())history_.pop_front();}
  bool predict(Snapshot & s,int64_t target_sim){Eigen::Vector2d initial(s.anchor.n[0],s.anchor.n[1]);std::array<bool,2> found{false,false};for(auto & e:s.history)if(e.sim_ns<=s.odom_stamp){initial[e.channel]=e.value;found[e.channel]=true;}
    if(mode_!="no_output"&&(!found[0]||!found[1]))return false;return usv_mpc::propagate_publisher_nominal(s.state,s.odom_stamp,target_sim,initial,s.history,params_.hydro);}
  void candidate(const p1::Candidate & m){auto immutable=std::make_shared<const p1::Candidate>(m);auto reason=p1::valid_job(m.job,run_,boot_,hash_,nominal_,worker_instance_);if(reason.empty()&&(m.worker_instance!=worker_instance_||m.backend!="acados"))reason="foreign_worker";
    if(reason.empty()&&(!m.success||!m.prediction_available||!m.solver_invoked))reason="solver_failed";
    if(reason.empty()&&(!p1::finite_array(m.x_prediction)||!p1::finite_array(m.u_prediction)||!p1::finite_array(m.first_control)||!std::isfinite(m.backend_ms)||m.backend_ms<0||m.solve_end_ns<m.solve_start_ns))reason="nonfinite_or_timing";
    if(reason.empty())for(int i=0;i<2;++i)if(std::abs(m.first_control[i]-m.u_prediction[i])>1e-8)reason="first_control_mismatch";
    if(reason.empty())for(int i=0;i<6;++i)if(std::abs(m.x_prediction[i]-m.job.target_state[i])>1e-7)reason="prediction_initial_mismatch";
    std::lock_guard<std::mutex> l(mutex_);auto expected=std::find_if(jobs_.begin(),jobs_.end(),[&](const p1::Job & j){return j.job_id==m.job.job_id;});
    if(reason.empty()&&(expected==jobs_.end()||p1::job_json(*expected)!=p1::job_json(m.job)))reason="job_echo_mismatch";
    auto now=p1::monotonic_ns();if(reason.empty()&&!(m.job.freeze_steady_ns<=m.worker_receive_ns&&m.worker_receive_ns<=m.solve_start_ns&&m.solve_start_ns<=m.solve_end_ns&&m.solve_end_ns<=now))reason="native_timing_order";p1::Ticket t;t.id=m.job.job_id;t.target=m.job.target_tick;t.origin=m.job.tick_origin_steady_ns;t.deadline=m.job.deadline_steady_ns;t.target_ns=m.job.target_steady_ns;t.version={m.job.task_generation,m.job.model_generation,m.job.config_generation,m.job.schedule_generation,m.job.clock_epoch};t.anchor={m.job.anchor_n,m.job.anchor_sequence,m.job.anchor_publish_ns,m.job.anchor_known};t.prediction=m.job.target_state;
    if(reason.empty()&&(worker_unusable_||stopping_||sink_->failed()))reason="run_unusable";
    if(reason.empty())reason=admission_.register_ready(t,current_tick_,now,version_);
    if(reason.empty()){candidate_=std::move(immutable);now=p1::monotonic_ns();if(!admission_.finalize_ready(t.id,now)){candidate_.reset();reason="late_registration_completion";}}
    sink_->add({{"type","candidate_registration"},{"job",p1::job_json(m.job)},{"ready_commit_ns",now},{"accepted_registration",reason.empty()},{"reason",reason},{"solve_start_ns",m.solve_start_ns},{"solve_end_ns",m.solve_end_ns},{"worker_instance",m.worker_instance},{"first_control",m.first_control}});
  }
  void prepare_loop(){while(!prep_stop_){Preparation p;{std::unique_lock<std::mutex> l(prep_mutex_);prep_cv_.wait_for(l,std::chrono::milliseconds(100),[this]{return prep_stop_||pending_.has_value();});if(prep_stop_)break;if(!pending_)continue;p=*pending_;pending_.reset();}
    auto & s=p.s;int64_t target_sim=s.sim+(p.origin+p1::T-s.clock_receive);auto x=s.state;if(!predict(s,target_sim)){sink_->add({{"type","job_not_submitted"},{"target_tick",p.tick+1},{"reason","history_or_propagation"}});continue;}
    usv_mpc::ReferenceMetadata meta;auto ref=usv_mpc::build_frozen_reference(s.state,*s.ref,20,.2,c_.at("reference_start_offset"),c_.at("cruise_speed"),&meta);if(!ref.allFinite())continue;
    p1::Job j;j.schema_version="p1-solve-job-v1";j.run_id=run_;j.boot_id=boot_;j.contract_hash=hash_;j.nominal_hash=nominal_;j.target_tick=p.tick+1;j.task_generation=s.version.task;j.model_generation=s.version.model;j.config_generation=s.version.config;j.schedule_generation=s.version.schedule;j.clock_epoch=s.version.epoch;j.tick_origin_steady_ns=p.origin;j.freeze_steady_ns=s.freeze;j.deadline_steady_ns=p.origin+p1::DEADLINE;j.target_steady_ns=p.origin+p1::T;j.target_sim_ns=target_sim;j.odom_stamp_ns=s.odom_stamp;j.imu_stamp_ns=s.mixed?s.imu_stamp:0;j.odom_receive_ns=s.odom_receive;j.imu_receive_ns=s.mixed?s.imu_receive:0;j.odom_sequence=s.odom_seq;j.imu_sequence=s.mixed?s.imu_seq:0;j.r_from_imu=s.mixed;j.horizon_steps=20;j.prediction_dt=.2;std::copy(x.data(),x.data()+6,j.frozen_state.begin());std::copy(s.state.data(),s.state.data()+6,j.target_state.begin());std::copy(ref.data(),ref.data()+126,j.reference.begin());j.frozen_clock_sim_ns=s.sim;j.frozen_clock_receive_ns=s.clock_receive;j.assumed_rtf=1.0;j.anchor_source=s.anchor_source;j.anchor_producer=s.anchor_producer;j.anchor_run_id=s.anchor_run;for(auto & e:s.history){j.history_sim_ns.push_back(e.sim_ns);j.history_channel.push_back(e.channel);j.history_n.push_back(e.value);}j.anchor_n=s.anchor.n;j.anchor_sequence=s.anchor.seq;j.anchor_publish_ns=s.anchor.time;j.anchor_known=s.anchor.known;j.reset_warmstart=std::abs(usv_mpc::normalize_angle(s.state[2]-ref(2,0)))>M_PI*.75;
    {std::lock_guard<std::mutex> l(mutex_);if(stopping_||worker_unusable_||!worker_valid_||sink_->failed()||!(s.version==version_)||current_tick_!=p.tick||p1::monotonic_ns()>j.deadline_steady_ns)continue;j.worker_instance=worker_instance_;j.job_id=++job_id_;jobs_.push_back(j);while(jobs_.size()>8)jobs_.pop_front();}
    if(!sink_->add({{"type","job"},{"job",p1::job_json(j)},{"reference_mode",meta.reference_mode},{"profile_t0",meta.profile_t0},{"nearest_index",meta.nearest_index},{"start_index",meta.start_index},{"publish_start_ns",p1::monotonic_ns()}}))continue;
    try{job_pub_->publish(j);}catch(...){normal_complete_=false;worker_unusable_=true;}
  }}
  void publish(p1::Decision & d){if(mode_!="execute")return;p1::Anchor old;{std::lock_guard<std::mutex> l(mutex_);old=anchor_;}d.rho_available=old.known[0]&&old.known[1];d.previous_anchor_known=old.known;d.previous_n=old.n;d.previous_publish_ns=old.time;
    for(int i=0;i<2;++i){d.publish_start_ns[i]=p1::monotonic_ns();{std::lock_guard<std::mutex> l(mutex_);d.publish_sim_ns[i]=sim_;d.publish_epoch[i]=version_.epoch;d.publish_clock_age_ns[i]=d.publish_start_ns[i]-clock_receive_;}std_msgs::msg::Float64 m;m.data=d.final_n[i];try{(i?right_:left_)->publish(m);d.publish_success[i]=true;}catch(...){d.publish_success[i]=false;}
      d.publish_end_ns[i]=p1::monotonic_ns();std::lock_guard<std::mutex> l(mutex_);if(d.publish_success[i]){anchor_.n[i]=d.final_n[i];anchor_.time[i]=d.publish_start_ns[i];anchor_.seq[i]++;anchor_.known[i]=true;push_history_locked({d.publish_sim_ns[i],i,d.final_n[i]});}else{anchor_.known[i]=false;normal_complete_=false;worker_unusable_=true;invalidate_locked();}}
    if(d.publish_end_ns[1]-d.publish_start_ns[0]>c_.at("publish_budget_ns").get<int64_t>()){normal_complete_=false;worker_unusable_=true;}
    for(int i=0;i<2;++i)if(!old.known[i]||!d.publish_success[i])d.rho_available=false;
    for(int i=0;i<2;++i)if(old.known[i]&&d.publish_success[i]&&(d.publish_start_ns[i]-old.time[i]>c_.at("publish_gap_ns").get<int64_t>()||std::abs(d.final_n[i]-old.n[i])>limits_.rho*(d.publish_start_ns[i]-old.time[i])/1e9+1e-9)){normal_complete_=false;worker_unusable_=true;d.rho_available=false;}
  }
  static p1::Json decision_json(const p1::Decision & d){return {{"type","decision"},{"schema",d.schema_version},{"run_id",d.run_id},{"boot_id",d.boot_id},{"contract_hash",d.contract_hash},{"worker_instance",d.worker_instance},{"model_generation",d.model_generation},{"config_generation",d.config_generation},{"mode",d.mode},{"sequence",d.sequence},{"tick",d.tick},{"job_id",d.job_id},{"task_generation",d.task_generation},{"schedule_generation",d.schedule_generation},{"epoch",d.clock_epoch},{"planned_ns",d.tick_planned_ns},{"start_ns",d.tick_start_ns},{"cutoff_commit_ns",d.cutoff_commit_ns},{"ready_commit_ns",d.candidate_ready_commit_ns},{"activation_commit_ns",d.activation_commit_ns},{"end_ns",d.tick_end_ns},{"skipped_ticks",d.skipped_ticks},{"accepted",d.candidate_accepted},{"diagnostic_only",d.diagnostic_only},{"reason",d.reason},{"control_source",d.control_source},{"target_state",d.target_state},{"activation_state",d.activation_state},{"state_error",d.state_error},{"requested_n",d.requested_n},{"final_n",d.final_n},{"publish_success",d.publish_success},{"publish_start_ns",d.publish_start_ns},{"publish_end_ns",d.publish_end_ns},{"previous_anchor_known",d.previous_anchor_known},{"publish_sim_ns",d.publish_sim_ns},{"publish_epoch",d.publish_epoch},{"publish_clock_age_ns",d.publish_clock_age_ns},{"activation_clock_sim_ns",d.activation_clock_sim_ns},{"activation_clock_receive_ns",d.activation_clock_receive_ns},{"activation_rtf",d.activation_rtf},{"activation_odom_stamp_ns",d.activation_odom_stamp_ns},{"activation_odom_receive_ns",d.activation_odom_receive_ns},{"activation_odom_sequence",d.activation_odom_sequence},{"activation_imu_stamp_ns",d.activation_imu_stamp_ns},{"activation_imu_receive_ns",d.activation_imu_receive_ns},{"activation_imu_sequence",d.activation_imu_sequence},{"activation_r_from_imu",d.activation_r_from_imu},{"previous_n",d.previous_n},{"previous_publish_ns",d.previous_publish_ns},{"anchor_known",d.anchor_known},{"anchor_sequence",d.anchor_sequence},{"odom_age_ns",d.odom_age_ns},{"imu_age_ns",d.imu_age_ns},{"clock_age_ns",d.clock_age_ns},{"normal_contract_complete",d.normal_contract_complete},{"rho_available",d.rho_available},{"plant_acceptance_observed",false}};}
  void tick_loop(){int64_t origin=p1::monotonic_ns()+1000000000,stop_start=0;uint64_t tick=0,last_schedule=0;
    while(true){auto planned=origin+tick*p1::T;p1::sleep_until_monotonic(planned);auto now=p1::monotonic_ns();p1::Decision d;Snapshot s;std::optional<p1::Ticket> t;std::shared_ptr<const p1::Candidate> cand;
      {std::lock_guard<std::mutex> l(mutex_);if(last_schedule&&version_.schedule!=last_schedule){origin=now;tick=0;planned=origin;invalidate_locked();}last_schedule=version_.schedule;
        auto due=p1::due_tick(origin,now);d.skipped_ticks=due>tick?due-tick:0;if(due>tick){tick=due;planned=origin+tick*p1::T;admission_.invalidate();candidate_.reset();normal_complete_=false;}
        current_tick_=tick;if(stop_requested||sink_->failed()){stopping_=true;if(!stop_start)stop_start=now;invalidate_locked();}
        if(clock_receive_&&last_clock_advance_&&now-last_clock_advance_>c_.at("clock_pause_confirm_ns").get<int64_t>()&&!paused_){paused_=true;version_.schedule++;invalidate_locked();}
        if(worker_active_&&now-worker_active_since_>c_.at("active_watchdog_ns").get<int64_t>()){worker_unusable_=true;worker_valid_=false;normal_complete_=false;invalidate_locked();sink_->add({{"type","active_watchdog"},{"active_job",worker_active_},{"observed_ns",now},{"policy","stop_submit; supervisor owns finite TERM/KILL"}});}
        s=snapshot_locked(now);t=admission_.take(tick,now);cand=candidate_;if(t)candidate_.reset();
        d.schema_version="p1-execution-decision-v2";d.run_id=run_;d.boot_id=boot_;d.contract_hash=hash_;d.worker_instance=worker_instance_;d.mode=mode_;d.sequence=++decision_seq_;d.tick=tick;d.task_generation=version_.task;d.model_generation=version_.model;d.config_generation=version_.config;d.schedule_generation=version_.schedule;d.clock_epoch=version_.epoch;d.tick_planned_ns=planned;d.tick_start_ns=now;d.cutoff_commit_ns=t?admission_.cutoff_ns():0;d.diagnostic_only=mode_!="execute";d.odom_age_ns=now-s.odom_receive;d.imu_age_ns=s.mixed?now-s.imu_receive:0;d.clock_age_ns=now-s.clock_receive;
      }
      auto reason=eligible(s,now);if(stopping_)reason="shutdown";if(worker_unusable_)reason="worker_unusable";
      if(now-planned>c_.at("tick_jitter_ns").get<int64_t>()){reason="tick_jitter";normal_complete_=false;}
      if(t&&cand){d.job_id=t->id;d.candidate_ready_commit_ns=t->ready_ns;d.target_state=t->prediction;
        if(reason.empty()&&!(t->version==s.version))reason="version_mismatch";
        if(reason.empty())reason=p1::anchor_check(t->anchor,s.anchor);
        auto aligned=s;if(!predict(aligned,cand->job.target_sim_ns)){if(reason.empty())reason="activation_history_or_time";}else{std::copy(aligned.state.data(),aligned.state.data()+6,d.activation_state.begin());auto state_reason=p1::state_check(t->prediction,d.activation_state,limits_,&d.state_error);if(reason.empty())reason=state_reason;}
        if(reason.empty()){Eigen::Vector2d request(cand->first_control[0],cand->first_control[1]);auto mapped=usv_mpc::map_vrx(request,c_.at("map_scale"),limits_.low,limits_.high,c_.at("publisher_max_n"));d.requested_n=cand->first_control;d.final_n={mapped[0],mapped[1]};reason=p1::command_check(d.final_n,s.anchor,now,limits_);if((mapped-request).norm()>1e-9)reason="candidate_mapping_changed";}
      }else if(reason.empty())reason="no_candidate";
      {std::lock_guard<std::mutex> l(mutex_);if(reason.empty()&&(!(s.version==version_)||s.odom_seq!=odom_seq_||s.imu_seq!=imu_seq_))reason="activation_input_changed_during_validation";
        if(reason.empty())reason=p1::anchor_check(s.anchor,anchor_);
        const int64_t commit_now=p1::monotonic_ns();
        if(reason.empty())reason=eligible(snapshot_locked(commit_now),commit_now);
        if(reason.empty()&&(worker_unusable_||!worker_valid_||sink_->failed()))reason="run_unusable_at_commit";
        if(reason.empty()&&commit_now-planned>c_.at("tick_jitter_ns").get<int64_t>()){reason="tick_jitter_at_commit";normal_complete_=false;}
        if(reason.empty()&&cand&&std::abs(sim_+(commit_now-clock_receive_)-cand->job.target_sim_ns)>c_.at("target_sim_slack_ns").get<int64_t>())reason="target_sim_mismatch";
        if(reason.empty())reason=p1::command_check(d.final_n,anchor_,commit_now,limits_);
        if(stopping_||stop_requested)reason="shutdown";
        d.candidate_accepted=reason.empty();d.reason=reason;d.activation_commit_ns=commit_now;d.activation_clock_sim_ns=sim_;d.activation_clock_receive_ns=clock_receive_;d.activation_rtf=rtf_;
        // Current source provenance at the actual final commit, not the job snapshot.
        d.activation_odom_stamp_ns=odom_stamp_;d.activation_odom_receive_ns=odom_receive_;d.activation_odom_sequence=odom_seq_;
        d.activation_r_from_imu=mixed_;d.activation_imu_stamp_ns=mixed_?imu_stamp_:0;
        d.activation_imu_receive_ns=mixed_?imu_receive_:0;d.activation_imu_sequence=mixed_?imu_seq_:0;
        d.odom_age_ns=commit_now-odom_receive_;d.imu_age_ns=mixed_?commit_now-imu_receive_:0;d.clock_age_ns=commit_now-clock_receive_;
        if(d.candidate_accepted){last_accepted_=d.activation_commit_ns;d.control_source="candidate";}else{d.final_n=p1::fallback(anchor_,d.activation_commit_ns,last_accepted_,limits_,stopping_||worker_unusable_||reason!="no_candidate");d.requested_n=d.final_n;d.control_source=last_accepted_>0&&!stopping_&&!worker_unusable_&&reason=="no_candidate"&&d.activation_commit_ns-last_accepted_<=limits_.hold_ns?"hold":"ramp_zero";}
      }
      // Only the tick thread reaches either physical publisher; no shared mutex
      // spans publish. Callback invalidation after this commit affects successor ticks.
      publish(d);
      {std::lock_guard<std::mutex> l(mutex_);d.anchor_known=anchor_.known;d.anchor_sequence=anchor_.seq;d.normal_contract_complete=normal_complete_&&!sink_->failed()&&mode_=="execute";d.tick_end_ns=p1::monotonic_ns();}
      if(!sink_->add(decision_json(d),d)){normal_complete_=false;stopping_=true;if(!stop_start)stop_start=now;}
      if(!stopping_&&!worker_unusable_&&worker_valid_&&!sink_->failed()){
        std::lock_guard<std::mutex> l(mutex_);auto next=snapshot_locked(p1::monotonic_ns());if(eligible(next,next.freeze).empty()){std::lock_guard<std::mutex> q(prep_mutex_);if(pending_)sink_->add({{"type","prepare_pending_replaced"},{"old_target_tick",pending_->tick+1},{"replacement_target_tick",tick+1}});pending_=Preparation{next,tick,planned};prep_cv_.notify_one();}}
      if(stopping_){bool zero=std::abs(d.final_n[0])<1e-9&&std::abs(d.final_n[1])<1e-9;if(zero||now-stop_start>=c_.at("shutdown_grace_ns").get<int64_t>()){sink_->add({{"type","regulator_shutdown"},{"zero_target_published",mode_=="execute"&&zero&&d.publish_success[0]&&d.publish_success[1]},{"shutdown_grace_exceeded",!zero},{"last_decision_sequence",d.sequence},{"normal_contract_complete",normal_complete_.load()&&!sink_->failed()},{"plant_hold_end_known",false},{"finished_ns",p1::monotonic_ns()}});break;}}
      p1::sleep_until_monotonic(planned+p1::DEADLINE+1);{std::lock_guard<std::mutex> l(mutex_);admission_.cutoff(p1::monotonic_ns());}
      ++tick;
    }
    prep_stop_=true;prep_cv_.notify_all();finished_=true;
  }
  p1::Json c_;usv_mpc::MpcParams params_;p1::Limits limits_;std::string run_,hash_,mode_,boot_,nominal_,legacy_run_,legacy_producer_,worker_instance_,path_fingerprint_,profile_fingerprint_,recording_observer_;int64_t expected_worker_pid_=0;
  std::mutex mutex_,prep_mutex_;std::condition_variable prep_cv_;std::optional<Preparation> pending_;std::thread prep_,tick_;std::atomic<bool> prep_stop_{false},finished_{false},stopping_{false},normal_complete_{true},worker_unusable_{false},worker_valid_{false};std::unique_ptr<Sink> sink_;
  p1::Version version_;p1::Anchor anchor_;p1::Admission admission_;std::shared_ptr<const p1::Candidate> candidate_;std::deque<p1::Job> jobs_;std::deque<usv_mpc::HeldInputEvent> history_;std::shared_ptr<const usv_mpc::ReferenceInput> ref_;usv_mpc::Vector6d state_=usv_mpc::Vector6d::Zero();
  uint64_t current_tick_=0,job_id_=0,decision_seq_=0,odom_received_=0,imu_received_=0,odom_seq_=0,imu_seq_=0,path_seq_=0,profile_seq_=0,worker_active_=0;int64_t worker_active_since_=0,odom_stamp_=0,imu_stamp_=0,odom_receive_=0,imu_receive_=0,clock_receive_=0,sim_=0,last_clock_advance_=0,last_accepted_=0;bool mixed_=false;std::atomic<bool> paused_{false},rtf_valid_{false};double rtf_=0;std::deque<std::pair<int64_t,int64_t>> clock_samples_;
  rclcpp::Publisher<p1::Job>::SharedPtr job_pub_;rclcpp::Publisher<p1::Decision>::SharedPtr decision_pub_;rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr left_,right_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_;rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_;rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr path_;rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr profile_;rclcpp::Subscription<rosgraph_msgs::msg::Clock>::SharedPtr clock_;rclcpp::Subscription<p1::Candidate>::SharedPtr candidates_;rclcpp::Subscription<p1::Capability>::SharedPtr capabilities_;rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr stop_;rclcpp::Subscription<usv_research_interfaces::msg::AppliedControl>::SharedPtr applied_;
};
int main(int argc,char **argv){rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,stop_signal);std::signal(SIGTERM,stop_signal);
try{auto node=std::make_shared<Regulator>();rclcpp::executors::SingleThreadedExecutor exec;exec.add_node(node);while(!node->finished()&&rclcpp::ok()){exec.spin_some(std::chrono::milliseconds(10));std::this_thread::sleep_for(std::chrono::milliseconds(1));}exec.remove_node(node);bool closed=node->close_source();node.reset();rclcpp::shutdown();return closed?0:2;}catch(const std::exception & e){fprintf(stderr,"regulator fatal: %s\n",e.what());rclcpp::shutdown();return 1;}}
