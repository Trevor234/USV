// SPDX-License-Identifier: MIT
// T1 (batch 68): source-linked component wiring of the CURRENT Regulator's
// candidate / reference / clock / publication-exit paths against the 23 gap
// atoms of case_applicability_v1 (67th batch).
//   * The tested code is the unmodified 67th-batch current_author source,
//     compiled in via P1_REGULATOR_SOURCE with the existing ShadowTestTag /
//     C33MatrixAccess seams. No admission rule is copied into this file.
//   * Ticket / lease / liveness / readiness premises are explicitly seeded in
//     C33MatrixAccess::make. This is NOT an owned four-role qualification, no
//     control DataWriter is created, and no cross-process delivery is claimed.
//   * Registration outcomes are asserted from the actual DiagSink JSONL stream
//     ("candidate_registration" events) plus the real admission/candidate state.
#include <gtest/gtest.h>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <thread>
#include <chrono>
#define P1_SHADOW_ENTRY_TEST
#define P1_C33_MATRIX_TEST
#define main t1_original_regulator_main
#include P1_REGULATOR_SOURCE
#undef main

namespace {
constexpr int64_t SIM=100000000000LL;
// Poll the actual sink stream until at least min_count events of the requested
// type exist; return the last one. flush_pad() must be called first: the sink
// ofstream only reaches disk when its ~8 KB buffer fills or at close.
p1::Json wait_event(const std::string &file,const std::string &type,size_t min_count){
  for(int tries=0;tries<300;++tries){
    std::ifstream in(file);size_t n=0;p1::Json last;std::string line;
    while(std::getline(in,line)){
      try{auto row=p1::Json::parse(line);
        if(row.value("type",std::string{})==type){last=std::move(row);++n;}
      }catch(const p1::Json::parse_error&){}
    }
    if(n>=min_count&&!last.is_null())return last;
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  return {};
}
}

// Bind visibility to this invocation, full Job identity, and the actual event
// type. The pad is only an aid to visibility; it is never the acknowledgement.
static p1::Json wait_current_registration(const std::string &file,
    const p1::Json &expected_job,int64_t invocation_ns) {
  const auto deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(200);
  do {
    std::ifstream in(file);std::string line;
    while(std::getline(in,line)) {
      try {
        auto row=p1::Json::parse(line);
        if(row.value("type",std::string{})=="candidate_registration" &&
           row.contains("job") && row.at("job")==expected_job &&
           row.value("ready_commit_ns",int64_t(0))>=invocation_ns)
          return row;
      }catch(const p1::Json::parse_error&){}
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  } while(std::chrono::steady_clock::now()<deadline);
  return {};
}

class C33MatrixAccess {
 public:
 using Snapshot=Regulator::Snapshot;
 static const p1::shadow::LegacyIdentity &legacy(){
  static const p1::shadow::LegacyIdentity id{"p0-contract-v1","t1-candidate-owner","t1-candidate-owner:unit",
    controlled_phase::baseline,std::string(64,'c'),p1::boot_id()+":steady_clock"};
  return id;
 }
 static std::unique_ptr<Regulator> make(const std::string &file){
  stop_requested=false;
  auto r=std::unique_ptr<Regulator>(new Regulator(Regulator::ShadowTestTag{},file,legacy()));
  r->hash_=std::string(64,'a');r->nominal_=r->c_.at("nominal_hash");
  r->ref_=std::make_shared<const usv_mpc::ReferenceInput>();r->resources_=p1::resource_limits_from_contract(r->c_);
  r->worker_instance_="t1-worker-instance";r->worker_valid_=true;r->expected_worker_pid_=getpid();
  r->worker_liveness_=std::make_unique<p1::WorkerLiveness>(getpid());r->capability_lease_->renew(p1::monotonic_ns());
  r->limits_.low=r->c_.at("command_min_n");r->limits_.high=r->c_.at("command_max_n");r->limits_.rho=r->c_.at("rho_n_s");
  r->limits_.hold_ns=r->c_.at("hold_ns");r->limits_.tolerance=r->c_.at("activation_tolerance").get<p1::State>();
  r->tick_barrier_=std::make_unique<p1::TickBarrier>(0,r->mode_,false);
  r->preparation_barrier_=std::make_unique<p1::PreparationBarrier>(0,r->mode_,false);
  auto now=p1::monotonic_ns();
  r->clock_receive_=r->last_clock_advance_=now;r->sim_=SIM;r->rtf_=1;r->rtf_valid_=true;
  r->anchor_.known={true,true};r->anchor_.seq={1,1};r->anchor_.time={now-100000000,now-100000000};r->anchor_.n={0,0};
  for(int i=0;i<2;++i){r->history_.push_back({SIM-40000000,i,0});
    r->ready_history_.push_back({SIM-40000000,i,0,1,now-100000000});
    r->publication_history_.push_back({i,1,now-100000000,0,true});}
  auto ref=std::make_shared<usv_mpc::ReferenceInput>();
  for(int k=0;k<3;++k){ref->path.push_back({.01*k,0,0});ref->profile.push_back({.05,0,0,.2*k});}
  ref->path_stamp=ref->profile_stamp={100,0};r->ref_=ref;
  odom(*r,SIM-20000000);odom(*r,SIM+1000000);
  return r;
 }
 // ---- message builders (identity matches the seeded premises) ----
 static nav_msgs::msg::Odometry odom_msg(int64_t ns,double velocity=0){
  nav_msgs::msg::Odometry m;m.header.stamp.sec=ns/1000000000;m.header.stamp.nanosec=ns%1000000000;
  m.header.frame_id="map";m.child_frame_id="wamv/base_link";m.pose.pose.orientation.w=1;m.twist.twist.linear.x=velocity;return m;}
 static void odom(Regulator&r,int64_t ns,double v=0){r.odom(odom_msg(ns,v));}
 static nav_msgs::msg::Path path_msg(int points,int64_t stamp_ns=100000000000LL,const std::string &frame="map"){
  nav_msgs::msg::Path m;m.header.stamp.sec=stamp_ns/1000000000;m.header.stamp.nanosec=stamp_ns%1000000000;
  m.header.frame_id=frame;for(int k=0;k<points;++k){geometry_msgs::msg::PoseStamped p;p.pose.position.x=.01*k;
  p.pose.orientation.w=1;m.poses.push_back(p);}return m;}
 static void path(Regulator&r,const nav_msgs::msg::Path&m){r.path(m);}
 static std_msgs::msg::Float64MultiArray profile_msg(int rows,int64_t stamp_ns=100000000000LL){
  std_msgs::msg::Float64MultiArray m;
  std_msgs::msg::MultiArrayDimension d0,d1,d2,d3;d0.label="points";d0.size=rows;d0.stride=rows*4;
  d1.label="v_kappa_r_t";d1.size=4;d1.stride=4;d2.label="stamp_sec:"+std::to_string(stamp_ns/1000000000);
  d3.label="stamp_nanosec:"+std::to_string(stamp_ns%1000000000);m.layout.dim={d0,d1,d2,d3};
  for(int i=0;i<rows;++i){m.data.push_back(.05);m.data.push_back(0);m.data.push_back(0);m.data.push_back(.2*i);}return m;}
 static void profile(Regulator&r,const std_msgs::msg::Float64MultiArray&m){r.profile(m);}
 static void clock(Regulator&r,int64_t ns){rosgraph_msgs::msg::Clock c;c.clock.sec=ns/1000000000;c.clock.nanosec=ns%1000000000;r.clock(c);}
 static void clock_silent_for(Regulator&r,int64_t ns){r.last_clock_advance_=p1::monotonic_ns()-ns;r.clock_receive_=p1::monotonic_ns()-ns;}
 struct JobSeed {uint64_t id=1,target_tick=1,task=0,model=1,config=1,schedule=1,epoch=0;
  int64_t origin_delta_ns=-100000000;std::string boot,run,worker;int horizon=20;double dt=.2;};
 static p1::Job job_msg(const Regulator&r,const JobSeed &s){
  const auto now=p1::monotonic_ns();const int64_t origin=now+s.origin_delta_ns;
  p1::Job j;j.schema_version="p1-solve-job-v1";j.run_id=s.run.empty()?r.run_:s.run;j.boot_id=s.boot.empty()?r.boot_:s.boot;
  j.contract_hash=r.hash_;j.nominal_hash=r.nominal_;j.worker_instance=s.worker.empty()?r.worker_instance_:s.worker;
  j.job_id=s.id;j.target_tick=s.target_tick;j.task_generation=s.task;j.model_generation=s.model;
  j.config_generation=s.config;j.schedule_generation=s.schedule;j.clock_epoch=s.epoch;
  j.tick_origin_steady_ns=origin;j.freeze_steady_ns=origin+10000000;j.deadline_steady_ns=origin+150000000;
  j.target_steady_ns=origin+200000000;j.target_sim_ns=SIM+2000000;
  j.odom_stamp_ns=SIM+1000000;j.imu_stamp_ns=0;j.odom_receive_ns=origin+1000000;j.imu_receive_ns=0;
  j.odom_sequence=r.odom_seq_;j.imu_sequence=0;j.r_from_imu=false;j.horizon_steps=s.horizon;j.prediction_dt=s.dt;
  j.frozen_state.fill(0);j.target_state.fill(0);j.reference.fill(0);
  // The anchor block mirrors what prepare_loop actually stamps: the live
  // command anchor of the regulator at submit time.
  j.anchor_n=r.anchor_.n;j.anchor_sequence=r.anchor_.seq;j.anchor_publish_ns=r.anchor_.time;j.anchor_known=r.anchor_.known;
  j.history_sim_ns={SIM-40000000,SIM-40000000};j.history_channel={0,1};j.history_n={0,0};
  j.assumed_rtf=1.0;j.frozen_clock_sim_ns=SIM-20000000;j.frozen_clock_receive_ns=origin+1000000;
  j.anchor_source="regulator_publisher";j.anchor_producer="t1-owner";j.anchor_run_id=r.run_;j.reset_warmstart=false;return j;}
 static p1::Candidate candidate_msg(const p1::Job &j,double first=1.0,bool available=true,bool invoked=true,
  bool success=true,bool nonfinite=false,std::string worker="",std::string backend="acados"){
  p1::Candidate m;m.job=j;m.worker_instance=worker.empty()?j.worker_instance:worker;m.backend=backend;
  m.success=success;m.prediction_available=available;m.solver_invoked=invoked;
  m.x_prediction.fill(0);for(int i=0;i<6;++i)m.x_prediction[i]=j.target_state[i];
  if(nonfinite)m.x_prediction[3]=std::numeric_limits<double>::quiet_NaN();
  m.u_prediction.fill(0);m.u_prediction[0]=first;m.u_prediction[1]=first;
  m.first_control={first,first};m.backend_ms=5.0;
  m.worker_receive_ns=j.freeze_steady_ns+1000000;m.solve_start_ns=j.freeze_steady_ns+1000000;
  m.solve_end_ns=j.freeze_steady_ns+2000000;return m;}
 // ---- real-code entry points and state readers (friend routing) ----
 static void seed_echo(Regulator&r,const p1::Job &j){std::lock_guard<std::mutex> l(r.mutex_);r.jobs_.push_back(j);}
 static void submit(Regulator&r,const p1::Candidate &c){r.candidate(c);}
 // The sink ofstream flushes only when its ~8 KB buffer fills (or at close).
 // A single padded event pushes prior events to disk so the assertions can
 // read the actual stream instead of trusting in-process state alone.
 static void flush_pad(Regulator&r){
  const std::string filler(8200,'p');  // serialized payload pushes the ~8 KB ofstream buffer to disk
  r.sink_->add({{"type","t1_component_flush_pad"},{"filler",filler},
    {"note","forces ofstream buffer flush for test-side stream reads"}});
 }
 static void refresh_clock(Regulator&r){  // keep receipt fresh WITHOUT re-observing the RTF window
  auto now=p1::monotonic_ns();r.clock_receive_=now;r.last_clock_advance_=now;}
 static bool register_candidate(Regulator&r,const std::string &sink,const p1::Job &j,const p1::Candidate &c,std::string &reason){
  const auto invocation_ns=p1::monotonic_ns();
  seed_echo(r,j);r.candidate(c);flush_pad(r);
  auto ev=wait_current_registration(sink,p1::job_json(j),invocation_ns);
  if(ev.is_null()){reason="<no_current_registration>";return false;}
  reason=ev.at("reason").get<std::string>();return ev.at("accepted_registration").get<bool>();
 }
 static uint64_t current_task(const Regulator&r){return r.version_.task;}
 static uint64_t current_tick(const Regulator&r){return r.current_tick_;}
 static uint64_t current_schedule(const Regulator&r){return r.version_.schedule;}
 static uint64_t current_epoch(const Regulator&r){return r.version_.epoch;}
 static bool paused(const Regulator&r){return r.paused_.load();}
 static bool rtf_valid(const Regulator&r){return r.rtf_valid_.load();}
 static double rtf_value(const Regulator&r){return r.rtf_;}
 static bool anchor_known(const Regulator&r){return r.anchor_.known[0]&&r.anchor_.known[1];}
 static size_t ref_path_size(const Regulator&r){return r.ref_->path.size();}
 static bool ready_path_valid(const Regulator&r){return r.ready_path_valid_;}
 static std::string path_fingerprint(const Regulator&r){return r.path_fingerprint_;}
 static bool admission_slots(const Regulator&r,int expect){return r.admission_.slots()==size_t(expect);}
 static bool candidate_present(const Regulator&r){return bool(r.candidate_);}
 static std::optional<p1::Ticket> admission_take(Regulator&r,uint64_t tick){return r.admission_.take(tick,p1::monotonic_ns());}
 static std::string eligible_now(Regulator&r){auto now=p1::monotonic_ns();return r.eligible(r.snapshot_locked(now),now);}
 static void stop(Regulator&r){r.stopping_=true;}
 static void resume_from_stop(Regulator&r){r.stopping_=false;stop_requested=false;}
 static void stale_odom(Regulator&r){r.odom_receive_=p1::monotonic_ns()-500000000;}
 static void finish(Regulator&r){r.sink_->close();}
 // ---- tick-loop shell (frozen contract + synthesized OutputAuthority) ----
 static void install_owned_authority(Regulator&r){
  const auto text=p1::read_text(P1_FROZEN_CONTRACT);
  auto frozen=p1::parse_unique_contract(text);
  p1::Json ctx{{"run_id","t1-tick-wiring"},{"boot_id",p1::boot_id()},{"contract_sha256",p1::digest(text)},
   {"freeze_evidence_sha256",frozen.at("freeze_evidence_sha256")},{"policy_sha256",p1::target_policy_sha256},
   {"regulator_manifest_sha256",p1::digest("t1-manifest")},{"producer_id","t1-candidate-owner"},
   {"role","p1_owned_execute_regulator"},{"pid",int64_t(getpid())},{"start_ticks",p1_owned::process_start_ticks()},
   {"output_gids",p1::Json::array({std::string(31,'a')+"b",std::string(31,'b')+"c"})},
   {"old_outputs_absent",true},{"worker_output_count",0},{"fixture_output_count",0},{"recorder_output_count",0},
   {"worker_capability_live",true},{"recorder_ready",true},{"inputs_ready",true},{"source_graph_verified",true}};
  p1::owned_execution::context_gate(frozen,"no_output",ctx,ctx);
  r.c_=frozen;
  r.own_authority_=std::make_unique<p1::owned_execution::OutputAuthority>(frozen,ctx,ctx,p1::monotonic_ns());
 }
 static void drive_one_tick(Regulator&r,int64_t origin){
  r.own_origin_ns_=origin;r.stopping_=true;  // finish_tick exits the loop after this tick
  r.tick_loop();
 }
 // ---- activation through the real admission take (mirrors tick_loop wiring) ----
 struct ActivationResult{bool accepted;std::string reason;std::string control_source;};
 static ActivationResult activate_taken(Regulator&r){
   refresh_clock(r);odom(r,SIM+1000000);  // keep live sources fresh, as the running tick would observe
   const auto now=p1::monotonic_ns();
   auto t=r.admission_.take(1,now);
   std::shared_ptr<const p1::Candidate> cand=r.candidate_;if(t)r.candidate_.reset();
   if(!t)return {false,"<no_ticket>",""};
   p1::Decision d;d.sequence=1;d.tick=t->target;d.tick_start_ns=d.tick_planned_ns=p1::monotonic_ns();
   d.task_generation=r.version_.task;d.model_generation=r.version_.model;d.config_generation=r.version_.config;
   d.schedule_generation=r.version_.schedule;d.clock_epoch=r.version_.epoch;
   Regulator::ActivationCapture capture;auto s=r.snapshot_locked(p1::monotonic_ns());int64_t copied=p1::monotonic_ns();
   Regulator::Snapshot final;p1::d0::Observation obs;
   r.activate_candidate(d,s,final,copied,obs,t,cand,d.tick_planned_ns,t->target,capture);
   r.publish(d);
   return {d.candidate_accepted,d.reason,d.control_source};
 }
 // ---- batch 70 (S1): real prepare_loop driving; friend routing only ----
 static nav_msgs::msg::Path static_path_msg(int64_t stamp_ns=100000000000LL){
  // The exact static 201-point straight at .05 m/s that task_time_reference
  // propose() admits: point x must equal speed*(.2*k) bit-for-bit.
  nav_msgs::msg::Path m;m.header.stamp.sec=stamp_ns/1000000000;m.header.stamp.nanosec=stamp_ns%1000000000;
  m.header.frame_id="map";
  for(int k=0;k<201;++k){geometry_msgs::msg::PoseStamped p;
    p.pose.position.x=.05*(.2*k);p.pose.orientation.w=1;m.poses.push_back(p);}
  return m;
 }
 static void settle_static_reference(Regulator &r){
  // Established through the real path()/profile() callbacks so the
  // path/profile fingerprints are real 64-char digests, as propose() requires.
  path(r,static_path_msg());
  profile(r,profile_msg(201));
 }
 static Regulator::Preparation make_preparation(Regulator &r,uint64_t tick,int64_t origin_delta_ns=-100000000){
  const auto now=p1::monotonic_ns();
  r.capability_lease_->renew(now);  // keep the lease fresh across the real submit guards
  return Regulator::Preparation{r.snapshot_locked(now),tick,now+origin_delta_ns};
 }
 static void enqueue_preparation(Regulator &r,const Regulator::Preparation &p){
  std::lock_guard<std::mutex> l(r.prep_mutex_);
  r.pending_=p;r.prep_cv_.notify_one();
 }
 static void ensure_job_publisher(Regulator &r){
  // The ShadowTestTag constructor creates no job publisher; the real submit
  // tail publishes on it, so the component gets a test publisher here (same
  // disclosure as the test decision publisher; no control DataWriter).
  if(!r.job_pub_)r.job_pub_=r.create_publisher<p1::Job>("/p1_test/solve_job",rclcpp::QoS(1).reliable());
 }
 static void start_prepare_thread(Regulator &r){
  ensure_job_publisher(r);
  r.prep_=std::thread(&Regulator::prepare_loop,&r);
 }
 static bool jobs_submitted(Regulator &r){
  std::lock_guard<std::mutex> l(r.mutex_);return !r.jobs_.empty();
 }
 static p1::Job last_submitted_job(Regulator &r){
  std::lock_guard<std::mutex> l(r.mutex_);return r.jobs_.back();
 }
 static bool pending_empty(Regulator &r){
  std::lock_guard<std::mutex> l(r.prep_mutex_);return !r.pending_.has_value();
 }
 static void stop_prepare_thread(Regulator &r){
  {std::lock_guard<std::mutex> l(r.prep_mutex_);r.prep_stop_=true;}
  r.prep_cv_.notify_all();if(r.prep_.joinable())r.prep_.join();
 }
 static bool wait_jobs_submitted(Regulator &r,int timeout_ms=300){
  for(int i=0;i<timeout_ms;++i){if(jobs_submitted(r))return true;
   std::this_thread::sleep_for(std::chrono::milliseconds(1));}
  return false;
 }
 static bool wait_pending_consumed(Regulator &r,int timeout_ms=300){
  for(int i=0;i<timeout_ms;++i){if(pending_empty(r))return true;
   std::this_thread::sleep_for(std::chrono::milliseconds(1));}
  return false;
 }
 static p1::Json read_event_once(const std::string &file,const std::string &type){
  std::ifstream in(file);p1::Json last;std::string line;
  while(std::getline(in,line)){
   try{auto row=p1::Json::parse(line);
    if(row.value("type",std::string{})==type)last=std::move(row);
   }catch(const p1::Json::parse_error&){}}
  return last;
 }
 static bool register_real_result(Regulator&r,const std::string &sink,const p1::Job &j,std::string &reason){
  // Result submission against the REAL prepare_loop echo: no manual seed_echo.
  const auto invocation_ns=p1::monotonic_ns();
  r.candidate(candidate_msg(j));flush_pad(r);
  auto ev=wait_current_registration(sink,p1::job_json(j),invocation_ns);
  if(ev.is_null()){reason="<no_current_registration>";return false;}
  reason=ev.at("reason").get<std::string>();return ev.at("accepted_registration").get<bool>();
 }
};

class T1Wiring:public ::testing::Test {
 protected:
 static void SetUpTestSuite(){int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);}
 static void TearDownTestSuite(){rclcpp::shutdown();}
 void SetUp()override{
  const char*base=std::getenv("P1_T1_TEST_OUTPUT");ASSERT_NE(base,nullptr);
  folder=std::filesystem::path(base)/::testing::UnitTest::GetInstance()->current_test_info()->name();
  ASSERT_FALSE(std::filesystem::exists(folder));std::filesystem::create_directories(folder);
  sink_file=(folder/"source.jsonl").string();
  reg=C33MatrixAccess::make(sink_file);
  std::ofstream(folder/"scope.json")<<p1::Json{{"source_linked_component_wiring",true},
   {"seeds","readiness/lease/liveness/ticket premises"},{"owned_four_role_qualification",false},
   {"control_DataWriter_created",false},{"cross_process_or_physical_claim",false}}.dump(2)<<'\n';
 }
 void TearDown()override{if(reg){C33MatrixAccess::finish(*reg);reg.reset();}}
 std::filesystem::path folder;std::string sink_file;std::unique_ptr<Regulator>reg;
};

// == candidate_identity_shape.01-.08 =====================================
TEST_F(T1Wiring,CandidateValidRegistersAndActivates){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<"reason="<<reason;
  EXPECT_EQ(reason,"");
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
  std::this_thread::sleep_for(std::chrono::milliseconds(210));  // past target_steady_ns
  auto result=C33MatrixAccess::activate_taken(*reg);
  EXPECT_TRUE(result.accepted)<<"reason="<<result.reason;
  EXPECT_EQ(result.control_source,"candidate");
}
TEST_F(T1Wiring,CandidateFailedSolverNotInvoked){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  auto bad=C33MatrixAccess::candidate_msg(j,1.0,false,false,false);  // unavailable, not invoked, failed
  bad.job.job_id=2;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,bad.job,bad,reason));
  EXPECT_EQ(reason,"solver_failed");
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));  // rejected submit leaves the accepted one intact
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
}
TEST_F(T1Wiring,CandidateInvalidShapeAndUnavailable){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  auto shape=j;shape.job_id=2;shape.horizon_steps=10;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,shape,C33MatrixAccess::candidate_msg(shape),reason));
  EXPECT_EQ(reason,"shape_or_time_contract");
  auto dt=j;dt.job_id=3;dt.prediction_dt=.4;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,dt,C33MatrixAccess::candidate_msg(dt),reason));
  EXPECT_EQ(reason,"shape_or_time_contract");
  auto unavailable=j;unavailable.job_id=4;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,unavailable,
    C33MatrixAccess::candidate_msg(unavailable,1.0,false,true,true),reason));
  EXPECT_EQ(reason,"solver_failed");
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));
}
TEST_F(T1Wiring,CandidateNonFinitePrediction){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,j,
    C33MatrixAccess::candidate_msg(j,1.0,true,true,true,true),reason));
  EXPECT_EQ(reason,"nonfinite_or_timing");
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));
}
TEST_F(T1Wiring,CandidateDuplicateRejected){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  // A second identical submit must be rejected as a duplicate without
  // consuming another slot or replacing the held candidate.
  C33MatrixAccess::submit(*reg,C33MatrixAccess::candidate_msg(j));
  C33MatrixAccess::flush_pad(*reg);
  auto ev=wait_event(sink_file,"candidate_registration",2);
  ASSERT_FALSE(ev.is_null());
  EXPECT_FALSE(ev.at("accepted_registration").get<bool>());
  EXPECT_EQ(ev.at("reason").get<std::string>(),"duplicate");
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
}
TEST_F(T1Wiring,CandidateOldReorderedJob){
  std::string reason;
  auto fresh=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,fresh,C33MatrixAccess::candidate_msg(fresh),reason))<<reason;
  auto stale_tick=C33MatrixAccess::job_msg(*reg,{.id=2,.target_tick=1});  // another id for the already-held tick
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,stale_tick,C33MatrixAccess::candidate_msg(stale_tick),reason));
  EXPECT_EQ(reason,"ready_slot_full");
  auto old_tick=C33MatrixAccess::job_msg(*reg,{.id=3,.target_tick=0});   // reordered: target behind current tick
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,old_tick,C33MatrixAccess::candidate_msg(old_tick),reason));
  EXPECT_EQ(reason,"wrong_tick");
  auto echo=C33MatrixAccess::job_msg(*reg,{.id=4,.target_tick=1});
  p1::Candidate stale_c=C33MatrixAccess::candidate_msg(echo);
  echo.target_sim_ns=SIM+12000000;                                        // echo now differs from the submitted job
  C33MatrixAccess::seed_echo(*reg,echo);
  C33MatrixAccess::submit(*reg,stale_c);
  C33MatrixAccess::flush_pad(*reg);
  auto ev=wait_event(sink_file,"candidate_registration",4);
  ASSERT_FALSE(ev.is_null());
  EXPECT_FALSE(ev.at("accepted_registration").get<bool>());
  EXPECT_EQ(ev.at("reason").get<std::string>(),"job_echo_mismatch");
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
}
TEST_F(T1Wiring,CandidateForeignWorkerAndIdentity){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  auto foreign_worker=C33MatrixAccess::candidate_msg(j,1.0,true,true,true,false,"somebody-else");
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,j,foreign_worker,reason));
  EXPECT_EQ(reason,"foreign_worker");
  auto foreign_boot=C33MatrixAccess::job_msg(*reg,{.id=2,.boot="00000000-0000-0000-0000-000000000000"});
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,foreign_boot,C33MatrixAccess::candidate_msg(foreign_boot),reason));
  EXPECT_EQ(reason,"foreign");
  auto foreign_run=C33MatrixAccess::job_msg(*reg,{.id=3,.run="t1-other-run"});
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,foreign_run,C33MatrixAccess::candidate_msg(foreign_run),reason));
  EXPECT_EQ(reason,"foreign");
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));
}
TEST_F(T1Wiring,CandidateStaleVersionRejected){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  auto stale=C33MatrixAccess::job_msg(*reg,{.id=2,.model=0});  // model generation behind version_.model=1
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,stale,C33MatrixAccess::candidate_msg(stale),reason));
  EXPECT_EQ(reason,"version_mismatch");
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
}

// == task_reference.01-.07 ================================================
TEST_F(T1Wiring,ReferenceClearBeforeFreeze){
  const uint64_t task0=C33MatrixAccess::current_task(*reg);
  C33MatrixAccess::path(*reg,C33MatrixAccess::path_msg(0));              // clear
  EXPECT_EQ(C33MatrixAccess::current_task(*reg),task0+1);
  EXPECT_EQ(C33MatrixAccess::ref_path_size(*reg),size_t(0));             // cleared input is not a task
  EXPECT_EQ(C33MatrixAccess::eligible_now(*reg),"no_path");              // short path cannot reach eligibility
  C33MatrixAccess::path(*reg,C33MatrixAccess::path_msg(3));              // recovery: single valid path
  EXPECT_TRUE(C33MatrixAccess::ready_path_valid(*reg));
  EXPECT_EQ(C33MatrixAccess::current_task(*reg),task0+2);                // new content is a new task
  EXPECT_EQ(C33MatrixAccess::ref_path_size(*reg),size_t(3));
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{.task=C33MatrixAccess::current_task(*reg)});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
}
TEST_F(T1Wiring,ReferenceSinglePointBeforeFreeze){
  const uint64_t task0=C33MatrixAccess::current_task(*reg);
  C33MatrixAccess::path(*reg,C33MatrixAccess::path_msg(1));
  EXPECT_EQ(C33MatrixAccess::current_task(*reg),task0+1);                // a single point is still a task change
  EXPECT_EQ(C33MatrixAccess::ref_path_size(*reg),size_t(1));
  EXPECT_EQ(C33MatrixAccess::eligible_now(*reg),"no_path");              // but never reaches eligibility
}
TEST_F(T1Wiring,ReferenceClearDuringReadyInvalidates){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));
  C33MatrixAccess::path(*reg,C33MatrixAccess::path_msg(0));              // clear while a candidate is held
  EXPECT_FALSE(C33MatrixAccess::candidate_present(*reg));
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));
  auto stale=C33MatrixAccess::job_msg(*reg,{.id=2});                      // old version cannot revive
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,stale,C33MatrixAccess::candidate_msg(stale),reason));
  EXPECT_EQ(reason,"version_mismatch");
}
TEST_F(T1Wiring,ReferenceReplaceDuringSolve){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  C33MatrixAccess::path(*reg,C33MatrixAccess::path_msg(5));              // replacement content
  EXPECT_FALSE(C33MatrixAccess::candidate_present(*reg));
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));
  EXPECT_EQ(C33MatrixAccess::ref_path_size(*reg),size_t(5));
  auto next=C33MatrixAccess::job_msg(*reg,{.id=2,.task=C33MatrixAccess::current_task(*reg)});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,next,C33MatrixAccess::candidate_msg(next),reason))<<reason;
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
}
TEST_F(T1Wiring,ReferenceSameContentRepublishKeepsTask){
  // Let the fingerprints settle through one real path/profile pass first; the
  // initial reference is seeded directly and carries no fingerprint yet.
  C33MatrixAccess::path(*reg,C33MatrixAccess::path_msg(3));
  C33MatrixAccess::profile(*reg,C33MatrixAccess::profile_msg(3));
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{.task=C33MatrixAccess::current_task(*reg)});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  const uint64_t task0=C33MatrixAccess::current_task(*reg);
  const auto fingerprint0=C33MatrixAccess::path_fingerprint(*reg);
  C33MatrixAccess::path(*reg,C33MatrixAccess::path_msg(3,100000000500LL));  // same geometry, new stamp
  EXPECT_EQ(C33MatrixAccess::current_task(*reg),task0);
  EXPECT_EQ(C33MatrixAccess::path_fingerprint(*reg),fingerprint0);
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));                 // held candidate survives the republish
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
  C33MatrixAccess::profile(*reg,C33MatrixAccess::profile_msg(3,100000000500LL));
  EXPECT_EQ(C33MatrixAccess::current_task(*reg),task0);
}
TEST_F(T1Wiring,ReferenceProfilePairMismatch){
  C33MatrixAccess::path(*reg,C33MatrixAccess::path_msg(3));
  C33MatrixAccess::profile(*reg,C33MatrixAccess::profile_msg(2));        // row count mismatch
  EXPECT_EQ(C33MatrixAccess::eligible_now(*reg),"profile_pair_incomplete");
  C33MatrixAccess::profile(*reg,C33MatrixAccess::profile_msg(3,200000000000LL));  // stamp mismatch
  EXPECT_EQ(C33MatrixAccess::eligible_now(*reg),"profile_pair_incomplete");
  C33MatrixAccess::profile(*reg,C33MatrixAccess::profile_msg(3));        // exact pair recovers
  EXPECT_EQ(C33MatrixAccess::eligible_now(*reg),"");
}
TEST_F(T1Wiring,ReferenceOrdinaryNewOdomKeepsEligible){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  const uint64_t task0=C33MatrixAccess::current_task(*reg);
  C33MatrixAccess::odom(*reg,SIM+5000000);                               // ordinary fresh odom
  EXPECT_EQ(C33MatrixAccess::current_task(*reg),task0);
  EXPECT_EQ(C33MatrixAccess::eligible_now(*reg),"");
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));
  C33MatrixAccess::stale_odom(*reg);                                     // contrast: stale receipt is gated
  EXPECT_EQ(C33MatrixAccess::eligible_now(*reg),"odom_timeout");
}

// == state_clock.04-.09 ====================================================
TEST_F(T1Wiring,ClockPauseInvalidatesSchedule){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  C33MatrixAccess::install_owned_authority(*reg);
  const uint64_t schedule0=C33MatrixAccess::current_schedule(*reg);
  C33MatrixAccess::clock_silent_for(*reg,600000000);                     // > clock_pause_confirm_ns (400 ms)
  C33MatrixAccess::drive_one_tick(*reg,p1::monotonic_ns());
  EXPECT_TRUE(C33MatrixAccess::paused(*reg));
  EXPECT_GT(C33MatrixAccess::current_schedule(*reg),schedule0);
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));
  EXPECT_FALSE(C33MatrixAccess::candidate_present(*reg));
}
TEST_F(T1Wiring,ClockResumeReschedules){
  C33MatrixAccess::install_owned_authority(*reg);
  C33MatrixAccess::clock_silent_for(*reg,600000000);
  C33MatrixAccess::drive_one_tick(*reg,p1::monotonic_ns()-600000000);
  ASSERT_TRUE(C33MatrixAccess::paused(*reg));
  C33MatrixAccess::resume_from_stop(*reg);  // the shell tick exits via stopping_; reopen for registration
  const uint64_t schedule0=C33MatrixAccess::current_schedule(*reg);
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,
    {.target_tick=C33MatrixAccess::current_tick(*reg)+1,
     .task=C33MatrixAccess::current_task(*reg),.schedule=C33MatrixAccess::current_schedule(*reg)});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  C33MatrixAccess::clock(*reg,SIM+100000000);                            // advance: resume wiring in clock()
  EXPECT_FALSE(C33MatrixAccess::paused(*reg));
  EXPECT_GT(C33MatrixAccess::current_schedule(*reg),schedule0);
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));                 // resume invalidates pending work
  EXPECT_FALSE(C33MatrixAccess::candidate_present(*reg));
}
TEST_F(T1Wiring,ClockBackwardResetsEpoch){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  const uint64_t epoch0=C33MatrixAccess::current_epoch(*reg),schedule0=C33MatrixAccess::current_schedule(*reg);
  C33MatrixAccess::clock(*reg,SIM-1000000000);                           // backward
  EXPECT_EQ(C33MatrixAccess::current_epoch(*reg),epoch0+1);
  EXPECT_GT(C33MatrixAccess::current_schedule(*reg),schedule0);
  EXPECT_FALSE(C33MatrixAccess::rtf_valid(*reg));
  EXPECT_FALSE(C33MatrixAccess::anchor_known(*reg));
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));
  EXPECT_FALSE(C33MatrixAccess::candidate_present(*reg));
}
TEST_F(T1Wiring,ClockLargeJumpResetsEpoch){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  const uint64_t epoch0=C33MatrixAccess::current_epoch(*reg);
  C33MatrixAccess::clock(*reg,SIM+6000000000LL);                         // > 5 s forward jump
  EXPECT_EQ(C33MatrixAccess::current_epoch(*reg),epoch0+1);
  EXPECT_FALSE(C33MatrixAccess::rtf_valid(*reg));
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));
  EXPECT_FALSE(C33MatrixAccess::candidate_present(*reg));
}
namespace {
int64_t drive_rtf_samples(Regulator &r,double sim_step_ms){
  int64_t sim=SIM;
  for(int i=0;i<6;++i){
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    sim+=int64_t(sim_step_ms*1000000.0);
    C33MatrixAccess::clock(r,sim);
  }
  return sim;
}}
TEST_F(T1Wiring,ClockRtfLowBandInvalid){
  const auto final_sim=drive_rtf_samples(*reg,90.0);                     // ratio ~0.90 < rtf_low 0.95
  C33MatrixAccess::odom(*reg,final_sim+1000000);                         // keep the odom source aligned
  EXPECT_FALSE(C33MatrixAccess::rtf_valid(*reg));
  EXPECT_LT(C33MatrixAccess::rtf_value(*reg),0.95);
  EXPECT_EQ(C33MatrixAccess::eligible_now(*reg),"rtf_unaligned");
}
TEST_F(T1Wiring,ClockRtfHighBandInvalid){
  const auto final_sim=drive_rtf_samples(*reg,110.0);                    // ratio ~1.10 > rtf_high 1.05
  C33MatrixAccess::odom(*reg,final_sim+1000000);
  EXPECT_FALSE(C33MatrixAccess::rtf_valid(*reg));
  EXPECT_GT(C33MatrixAccess::rtf_value(*reg),1.05);
  EXPECT_EQ(C33MatrixAccess::eligible_now(*reg),"rtf_unaligned");
}

// == publication_exit.02-.03 ===============================================
TEST_F(T1Wiring,CommittedSubmitClearInvalidates){
  std::string reason;auto j1=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j1,C33MatrixAccess::candidate_msg(j1),reason))<<reason;
  std::this_thread::sleep_for(std::chrono::milliseconds(210));
  auto activated=C33MatrixAccess::activate_taken(*reg);                  // committed and consumed through real admission
  EXPECT_TRUE(activated.accepted)<<activated.reason;
  auto j2=C33MatrixAccess::job_msg(*reg,{.id=2});                        // next registration targets the same open tick
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j2,C33MatrixAccess::candidate_msg(j2),reason))<<reason;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,j2,C33MatrixAccess::candidate_msg(j2),reason));  // id memory
  EXPECT_EQ(reason,"duplicate");
  C33MatrixAccess::path(*reg,C33MatrixAccess::path_msg(0));              // clear after committed submit
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));
  EXPECT_FALSE(C33MatrixAccess::candidate_present(*reg));
  EXPECT_FALSE(C33MatrixAccess::admission_take(*reg,1).has_value());     // committed target cannot be revived
  auto old=C33MatrixAccess::job_msg(*reg,{.id=3});                        // old-version identity cannot re-register
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,old,C33MatrixAccess::candidate_msg(old),reason));
  EXPECT_EQ(reason,"version_mismatch");
}
TEST_F(T1Wiring,ShutdownDuringReadyActivation){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  C33MatrixAccess::stop(*reg);                                            // shutdown interleaved with ready/activation
  std::this_thread::sleep_for(std::chrono::milliseconds(210));
  auto result=C33MatrixAccess::activate_taken(*reg);
  EXPECT_FALSE(result.accepted);
  EXPECT_EQ(result.reason,"shutdown");
  EXPECT_NE(result.control_source,"candidate");
}

// == delayed tick shells (250/400 ms) ======================================
TEST_F(T1Wiring,DelayedTick250msSkipsOnce){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  C33MatrixAccess::install_owned_authority(*reg);
  C33MatrixAccess::drive_one_tick(*reg,p1::monotonic_ns()-250000000);
  C33MatrixAccess::flush_pad(*reg);
  auto ev=wait_event(sink_file,"scheduler_skipped_ticks",1);
  ASSERT_FALSE(ev.is_null());
  EXPECT_EQ(ev.at("skipped_ticks").get<uint64_t>(),uint64_t(1));
  EXPECT_EQ(ev.at("due_tick").get<uint64_t>(),uint64_t(1));
  EXPECT_FALSE(ev.at("candidate_after").get<bool>());
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));                  // skipped tick invalidated the registration
  EXPECT_FALSE(C33MatrixAccess::candidate_present(*reg));
}
TEST_F(T1Wiring,DelayedTick400msSkipsTwice){
  C33MatrixAccess::install_owned_authority(*reg);
  C33MatrixAccess::drive_one_tick(*reg,p1::monotonic_ns()-400000000);
  C33MatrixAccess::flush_pad(*reg);
  auto ev=wait_event(sink_file,"scheduler_skipped_ticks",1);
  ASSERT_FALSE(ev.is_null());
  EXPECT_EQ(ev.at("skipped_ticks").get<uint64_t>(),uint64_t(2));
  EXPECT_EQ(ev.at("due_tick").get<uint64_t>(),uint64_t(2));
}

// == S1 supplementary evidence (batch 70) ==================================
// Scope: isolated boolean rejection gates, native-shape constructive evidence,
// the REAL prepare_loop submission path with its shutdown/version guards, the
// in-flight reference-change window, and a real activation after ordinary new
// odom. The tested code remains the unmodified 67th-batch Regulator source
// compiled in through P1_REGULATOR_SOURCE; no admission rule is copied here.
TEST_F(T1Wiring,CandidateSuccessFalseAloneRejected){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  auto failed=C33MatrixAccess::candidate_msg(j,1.0,true,true,false);  // ONLY success=false
  failed.job.job_id=2;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,failed.job,failed,reason));
  EXPECT_EQ(reason,"solver_failed");
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));  // the accepted registration is untouched
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
}
TEST_F(T1Wiring,CandidateSolverNotInvokedAloneRejected){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  auto not_invoked=C33MatrixAccess::candidate_msg(j,1.0,true,false,true);  // ONLY solver_invoked=false
  not_invoked.job.job_id=2;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,not_invoked.job,not_invoked,reason));
  EXPECT_EQ(reason,"solver_failed");
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
}
TEST_F(T1Wiring,NativePredictionShapeFixedByConstruction){
  // Native result dimensions are fixed by the wire contract itself: 126 for
  // x_prediction (21 columns x 6 states), 40 for u_prediction (20 x 2), 2 for
  // first_control, 126 for the Job reference block. A wrong-dimension native
  // result cannot be represented on the wire; this is constructive evidence,
  // not a claim that a bad-shape native experiment ran. The Job horizon/dt
  // branch stays a separate metadata gate.
  static_assert(sizeof(p1::Candidate{}.x_prediction)==126*sizeof(double),"x_prediction fixed at 126");
  static_assert(sizeof(p1::Candidate{}.u_prediction)==40*sizeof(double),"u_prediction fixed at 40");
  static_assert(sizeof(p1::Candidate{}.first_control)==2*sizeof(double),"first_control fixed at 2");
  static_assert(sizeof(p1::Job{}.reference)==126*sizeof(double),"job reference fixed at 126");
  const auto j=C33MatrixAccess::job_msg(*reg,{});
  const auto c=C33MatrixAccess::candidate_msg(j);
  EXPECT_EQ(c.x_prediction.size(),size_t(126));
  EXPECT_EQ(c.u_prediction.size(),size_t(40));
  EXPECT_EQ(c.first_control.size(),size_t(2));
  auto meta=j;meta.job_id=2;meta.horizon_steps=10;  // Job metadata, NOT native result shape
  std::string reason;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,meta,C33MatrixAccess::candidate_msg(meta),reason));
  EXPECT_EQ(reason,"shape_or_time_contract");
}
TEST_F(T1Wiring,RealPrepareLoopSubmitsJob){
  C33MatrixAccess::settle_static_reference(*reg);
  const auto prep=C33MatrixAccess::make_preparation(*reg,C33MatrixAccess::current_tick(*reg));
  C33MatrixAccess::enqueue_preparation(*reg,prep);
  C33MatrixAccess::start_prepare_thread(*reg);
  const bool submitted=C33MatrixAccess::wait_jobs_submitted(*reg);
  C33MatrixAccess::stop_prepare_thread(*reg);
  EXPECT_TRUE(submitted);                                     // real jobs_ push through the submit commit
  C33MatrixAccess::flush_pad(*reg);
  const auto ev=wait_event(sink_file,"job",1);
  ASSERT_FALSE(ev.is_null());
  const auto &job=ev.at("job");
  EXPECT_GT(job.at("job_id").get<uint64_t>(),uint64_t(0));
  EXPECT_EQ(job.at("N").get<uint32_t>(),uint32_t(20));
  EXPECT_DOUBLE_EQ(job.at("dt").get<double>(),.2);
  EXPECT_GT(job.at("deadline_ns").get<int64_t>(),ev.at("submit_commit_ns").get<int64_t>());
  const auto pub=C33MatrixAccess::read_event_once(sink_file,"job_publish_result");
  ASSERT_FALSE(pub.is_null());
  EXPECT_TRUE(pub.at("success").get<bool>());
  const auto epoch=C33MatrixAccess::read_event_once(sink_file,"reference_epoch_committed");
  ASSERT_FALSE(epoch.is_null());
  // The REAL echo written by prepare_loop admits a result WITHOUT seed_echo.
  const p1::Job real=C33MatrixAccess::last_submitted_job(*reg);
  EXPECT_EQ(real.job_id,job.at("job_id").get<uint64_t>());
  std::string reason;
  EXPECT_TRUE(C33MatrixAccess::register_real_result(*reg,sink_file,real,reason))<<"reason="<<reason;
  EXPECT_EQ(reason,"");
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
}
TEST_F(T1Wiring,RealSubmitBlockedByShutdownBeforeSubmit){
  C33MatrixAccess::settle_static_reference(*reg);
  const auto prep=C33MatrixAccess::make_preparation(*reg,C33MatrixAccess::current_tick(*reg));
  C33MatrixAccess::enqueue_preparation(*reg,prep);
  C33MatrixAccess::stop(*reg);                                // shutdown lands before the real submit guards
  C33MatrixAccess::start_prepare_thread(*reg);
  const bool consumed=C33MatrixAccess::wait_pending_consumed(*reg);
  std::this_thread::sleep_for(std::chrono::milliseconds(30));
  C33MatrixAccess::stop_prepare_thread(*reg);
  EXPECT_TRUE(consumed);
  C33MatrixAccess::flush_pad(*reg);
  const auto ev=wait_event(sink_file,"job_not_submitted",1);
  ASSERT_FALSE(ev.is_null());
  EXPECT_EQ(ev.at("reason").get<std::string>(),"shutdown_before_submit");
  EXPECT_FALSE(C33MatrixAccess::jobs_submitted(*reg));        // no echo, no submit
  EXPECT_TRUE(C33MatrixAccess::read_event_once(sink_file,"job").is_null());
}
TEST_F(T1Wiring,RealSubmitBlockedByVersionChangeBeforeSubmit){
  C33MatrixAccess::settle_static_reference(*reg);
  const auto prep=C33MatrixAccess::make_preparation(*reg,C33MatrixAccess::current_tick(*reg));
  C33MatrixAccess::path(*reg,C33MatrixAccess::path_msg(5));   // reference change inside the in-flight window
  C33MatrixAccess::profile(*reg,C33MatrixAccess::profile_msg(5));  // complete the new pair for the positive control
  const uint64_t new_task=C33MatrixAccess::current_task(*reg);
  EXPECT_GT(new_task,prep.s.version.task);                    // the preparation is now stale
  C33MatrixAccess::enqueue_preparation(*reg,prep);
  C33MatrixAccess::start_prepare_thread(*reg);
  const bool consumed=C33MatrixAccess::wait_pending_consumed(*reg);
  std::this_thread::sleep_for(std::chrono::milliseconds(30));
  C33MatrixAccess::stop_prepare_thread(*reg);
  EXPECT_TRUE(consumed);
  C33MatrixAccess::flush_pad(*reg);
  const auto ev=wait_event(sink_file,"job_not_submitted",1);
  ASSERT_FALSE(ev.is_null());
  const auto blocked=ev.at("reason").get<std::string>();
  EXPECT_TRUE(blocked=="version_changed_before_submit"||
              blocked=="version_changed_at_submit_completion")<<"blocked="<<blocked;
  EXPECT_FALSE(C33MatrixAccess::jobs_submitted(*reg));
  // The stale in-flight result cannot register afterwards either (distinct
  // job_id: a rejected submit leaves its seeded echo in jobs_).
  auto stale=C33MatrixAccess::job_msg(*reg,{.id=2,.task=prep.s.version.task});
  std::string reason;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,stale,C33MatrixAccess::candidate_msg(stale),reason));
  EXPECT_EQ(reason,"version_mismatch");
  // Positive control: the new task generation registers and really activates.
  auto fresh=C33MatrixAccess::job_msg(*reg,{.id=3,.task=new_task});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,fresh,C33MatrixAccess::candidate_msg(fresh),reason))<<reason;
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
  std::this_thread::sleep_for(std::chrono::milliseconds(210));
  const auto result=C33MatrixAccess::activate_taken(*reg);
  EXPECT_TRUE(result.accepted)<<result.reason;
  EXPECT_EQ(result.control_source,"candidate");
}
TEST_F(T1Wiring,ReferenceOrdinaryNewOdomActivation){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  const uint64_t task0=C33MatrixAccess::current_task(*reg);
  C33MatrixAccess::odom(*reg,SIM+5000000);                    // ordinary fresh odom
  EXPECT_EQ(C33MatrixAccess::current_task(*reg),task0);       // no version change
  std::this_thread::sleep_for(std::chrono::milliseconds(210));
  const auto result=C33MatrixAccess::activate_taken(*reg);    // REAL activation attempt
  EXPECT_TRUE(result.accepted)<<result.reason;
  EXPECT_EQ(result.control_source,"candidate");
  // Version rejection dimensions per the frozen contract: model is isolated in
  // candidate_identity_shape.08, clock epoch in the state_clock cases; the
  // remaining task/config/schedule dimensions reject explicitly here.
  const std::array<C33MatrixAccess::JobSeed,3> dims{
    C33MatrixAccess::JobSeed{.id=2,.task=task0+1},
    C33MatrixAccess::JobSeed{.id=3,.config=2},
    C33MatrixAccess::JobSeed{.id=4,.schedule=2}};
  for(const auto &seed:dims){
    auto stale=C33MatrixAccess::job_msg(*reg,seed);
    EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,stale,C33MatrixAccess::candidate_msg(stale),reason));
    EXPECT_EQ(reason,"version_mismatch");
  }
}
