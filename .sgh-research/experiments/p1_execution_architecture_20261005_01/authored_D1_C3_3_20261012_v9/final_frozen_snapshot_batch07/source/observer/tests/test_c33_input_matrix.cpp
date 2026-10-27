// SPDX-License-Identifier: MIT
// Calls the original production callbacks, snapshot functions and tick_loop.
// Source-including fixture prerequisites are explicit, never stage qualification.
#include <gtest/gtest.h>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#include <functional>
#define P1_SHADOW_ENTRY_TEST
#define P1_LEGACY_READY_TEST
#define P1_C33_MATRIX_TEST
#define main p1_c33_original_program_main
#include P1_REGULATOR_SOURCE
#undef main

using Applied=usv_research_interfaces::msg::AppliedControl;
class C33MatrixAccess {
 public:
  static std::unique_ptr<Regulator> make(const std::string &path,const p1::shadow::LegacyIdentity &id){
    stop_requested=false;
    auto out=std::unique_ptr<Regulator>(new Regulator(Regulator::LegacyReadyTestTag{},path,id));
    // Existing callback-only constructor does not start the tick machinery.
    // This actual-tick fixture supplies its original zero/disabled barrier.
    out->tick_barrier_=std::make_unique<p1::TickBarrier>(0,out->mode_,false);
    // Only isolated source-linked callback/tick semantics are under test. The
    // startup-ready business phase is already a separate native test target.
    out->legacy_readiness_enabled_=false;
    return out;
  }
  static void odom(Regulator &r,const nav_msgs::msg::Odometry &m){r.odom(m);}
  static void imu(Regulator &r,const sensor_msgs::msg::Imu &m){r.imu(m);}
  static void path(Regulator &r,const nav_msgs::msg::Path &m){r.path(m);}
  static void profile(Regulator &r,const std_msgs::msg::Float64MultiArray &m){r.profile(m);}
  static void clock(Regulator &r,const rosgraph_msgs::msg::Clock &m){r.clock(m);}
  static void capability(Regulator &r,const p1::Capability &m){r.capability(m);}
  static auto snapshot(Regulator &r){std::lock_guard<std::mutex> lock(r.mutex_);return r.snapshot_locked(p1::monotonic_ns());}
  static auto final(Regulator &r){std::lock_guard<std::mutex> lock(r.mutex_);Regulator::Snapshot out;r.capture_final_source_locked(out,p1::monotonic_ns());return out;}
  static auto source(Regulator &r){return p1::d0::source_json(snapshot(r));}
  static p1::Json state(Regulator &r){std::lock_guard<std::mutex> lock(r.mutex_);return {
    {"ordinal",r.input_commit_ordinal_},{"odom_received",r.odom_received_},{"imu_received",r.imu_received_},
    {"ready_path_valid",r.ready_path_valid_},{"ready_profile_valid",r.ready_profile_valid_},
    {"candidate_present",bool(r.candidate_)},{"admission_slots",r.admission_.slots()},
    {"worker_unusable",r.worker_unusable_.load()},{"worker_valid",r.worker_valid_.load()},
    {"worker_instance",r.worker_instance_},{"last_valid_ns",r.capability_lease_->last_valid_ns()},
    {"last_capability",r.last_capability_},{"last_capability_commit_ns",r.last_capability_commit_ns_},
    {"timeout_ns",r.capability_lease_->timeout_ns()},{"paused",r.paused_.load()}};}
  static std::string eligible(Regulator &r){std::lock_guard<std::mutex> lock(r.mutex_);auto now=p1::monotonic_ns();return r.eligible(r.snapshot_locked(now),now);}
  static p1::Capability valid_capability(Regulator &r){p1::Capability m;
    m.schema_version="p1-worker-capability-v1";m.run_id=r.run_;m.boot_id=r.boot_;m.contract_hash=r.hash_;
    m.nominal_hash=r.nominal_;m.worker_instance=std::string(64,'e');m.clock_name="CLOCK_MONOTONIC";
    m.backend="acados";m.matrix_layout="column_major";m.horizon_steps=20;m.prediction_dt=.2;
    m.pid=getpid();m.startup_ns=p1::monotonic_ns()-1000;m.fault_injection_enabled=true;return m;
  }
  static void expire(Regulator &r){std::lock_guard<std::mutex> lock(r.mutex_);r.check_worker_locked(r.capability_lease_->last_valid_ns()+r.capability_lease_->timeout_ns()+1);}
  static void seed_history(Regulator &r){std::lock_guard<std::mutex> lock(r.mutex_);
    r.anchor_.n={0,0};r.anchor_.known={true,true};r.anchor_.seq={1,1};r.anchor_.time={p1::monotonic_ns()-100000000,p1::monotonic_ns()-100000000};
    r.history_={{1000000000,0,0},{1000000000,1,0}};
    r.publication_history_={{0,1,r.anchor_.time[0],0,true},{1,1,r.anchor_.time[1],0,true}};
  }
  static void seed_live_candidate(Regulator &r){std::lock_guard<std::mutex> lock(r.mutex_);
    const auto now=p1::monotonic_ns();p1::Ticket t;t.id=41;t.target=1;t.origin=now;t.deadline=now+p1::DEADLINE;t.target_ns=now+p1::T;t.version=r.version_;
    if(!r.admission_.register_ready(t,0,now,r.version_).empty())throw std::runtime_error("fixture registration failed");
    if(!r.admission_.finalize_ready(t.id,now))throw std::runtime_error("fixture registration completion failed");
    p1::Candidate c;c.job.job_id=t.id;r.candidate_=std::make_shared<const p1::Candidate>(c);
  }
  static void install_hooks(Regulator &r,std::function<void(uint64_t,int64_t)> before,std::function<void(uint64_t)> commit,std::function<void(uint64_t)> after){
    r.c33_before_snapshot_=std::move(before);r.c33_before_commit_=std::move(commit);r.c33_after_tick_=std::move(after);
  }
  static void run_tick(Regulator &r){r.tick_loop();}
  static void seed_tick_preconditions(Regulator &r,uint64_t tick,int64_t planned){
    std::lock_guard<std::mutex> lock(r.mutex_);
    // Prerequisites isolate original final-gate interleavings. They do NOT
    // qualify RTF estimation, nominal trajectory solving, startup-ready, or
    // transport. Source callbacks still determine all accepted input counters.
    r.rtf_=1;r.rtf_valid_=true;r.paused_=false;
    if(tick==0){
      r.anchor_.n={0,0};r.anchor_.known={true,true};r.anchor_.seq={1,1};r.anchor_.time={planned-100000000,planned-100000000};
      r.history_={{999000000,0,0},{999000000,1,0}};
      r.publication_history_={{0,1,r.anchor_.time[0],0,true},{1,1,r.anchor_.time[1],0,true}};
      p1::Ticket t;t.id=71;t.target=1;t.origin=planned;t.deadline=planned+p1::DEADLINE;t.target_ns=planned+p1::T;t.version=r.version_;t.anchor=r.anchor_;
      const auto now=p1::monotonic_ns();auto reason=r.admission_.register_ready(t,0,now,r.version_);
      if(!reason.empty()||!r.admission_.finalize_ready(t.id,p1::monotonic_ns()))throw std::runtime_error("bounded tick fixture ticket failed: "+reason);
      p1::Candidate c;c.job.job_id=t.id;c.job.target_tick=1;c.job.target_sim_ns=1200000000;c.worker_instance=r.worker_instance_;
      c.job.run_id=r.run_;c.job.boot_id=r.boot_;c.job.contract_hash=r.hash_;c.job.nominal_hash=r.nominal_;c.job.worker_instance=r.worker_instance_;
      c.job.task_generation=t.version.task;c.job.model_generation=t.version.model;c.job.config_generation=t.version.config;c.job.schedule_generation=t.version.schedule;c.job.clock_epoch=t.version.epoch;
      c.job.freeze_steady_ns=now;c.job.tick_origin_steady_ns=t.origin;c.job.deadline_steady_ns=t.deadline;c.job.target_steady_ns=t.target_ns;c.job.horizon_steps=20;c.job.prediction_dt=.2;
      c.first_control={0,0};r.candidate_=std::make_shared<const p1::Candidate>(c);
    }
  }
  static void seed_pause_clock(Regulator &r){std::lock_guard<std::mutex> lock(r.mutex_);r.clock_receive_=p1::monotonic_ns();r.last_clock_advance_=r.clock_receive_-r.c_.at("clock_pause_confirm_ns").get<int64_t>()-1;}
  static void close(Regulator &r){r.sink_->close();}
};

class C33InputMatrix:public ::testing::Test {
 protected:
  static void SetUpTestSuite(){int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);}
  static void TearDownTestSuite(){rclcpp::shutdown();}
  void SetUp()override{
    const char *output=std::getenv("P1_BRANCH_TEST_OUTPUT");ASSERT_NE(output,nullptr);
    folder=std::filesystem::path(output)/::testing::UnitTest::GetInstance()->current_test_info()->name();ASSERT_FALSE(std::filesystem::exists(folder));std::filesystem::create_directories(folder);
    source_file=folder/"source.jsonl";
    id={"p0-contract-v1","c33-source-test","c33-source-test:12345","F5_20261005_atomic_freeze_01",std::string(64,'a'),p1::boot_id()+":steady_clock"};
    r=C33MatrixAccess::make(source_file.string(),id);
    std::ofstream note(folder/"test_scope.json");note<<p1::Json{{"schema","p1-C3.3-native-scope-v1"},{"runtime_source_included",true},
      {"raw_network_authenticated",false},{"fixture_prerequisites_seeded",true},{"physical_publishers",0},{"phase_qualified",false},
      {"limitations",{"direct callback raw_input=null","RTF/anchor/immutable ticket prerequisites may be seeded in isolated gates","no global total order or real Master Clock","component test only"}}}.dump(2)<<'\n';
  }
  void TearDown()override{if(r)C33MatrixAccess::close(*r);}
  static builtin_interfaces::msg::Time stamp(int sec,int nsec){builtin_interfaces::msg::Time t;t.sec=sec;t.nanosec=nsec;return t;}
  static builtin_interfaces::msg::Time stamp_ns(int64_t ns){return stamp(ns/1000000000,ns%1000000000);}
  static nav_msgs::msg::Odometry odom_msg(int64_t ns=1000000000){nav_msgs::msg::Odometry m;m.header.frame_id="map";m.child_frame_id="wamv/base_link";m.header.stamp=stamp_ns(ns);m.pose.pose.orientation.w=1;m.pose.pose.position.x=2;m.pose.pose.position.y=3;m.twist.twist.linear.x=4;m.twist.twist.linear.y=5;m.twist.twist.angular.z=6;return m;}
  static sensor_msgs::msg::Imu imu_msg(int64_t ns=1000000000){sensor_msgs::msg::Imu m;m.header.frame_id="wamv/wamv/base_link/imu_sensor";m.header.stamp=stamp_ns(ns);m.angular_velocity.z=7;return m;}
  static nav_msgs::msg::Path path_msg(int sec=1,int nsec=0){nav_msgs::msg::Path m;m.header.frame_id="map";m.header.stamp=stamp(sec,nsec);m.poses.resize(2);m.poses[0].pose.orientation.w=1;m.poses[1].pose.orientation.w=1;m.poses[1].pose.position.x=1;return m;}
  static std_msgs::msg::Float64MultiArray profile_msg(int sec=1,int nsec=0){std_msgs::msg::Float64MultiArray m;m.layout.dim.resize(2);m.layout.dim[0].label="stamp_sec:"+std::to_string(sec);m.layout.dim[1].label="stamp_nanosec:"+std::to_string(nsec);m.data={0,.6,0,0,1,.6,0,1};return m;}
  static rosgraph_msgs::msg::Clock clock_msg(int64_t ns){rosgraph_msgs::msg::Clock m;m.clock=stamp_ns(ns);return m;}
  void reference(){C33MatrixAccess::path(*r,path_msg());C33MatrixAccess::profile(*r,profile_msg());}
  std::vector<p1::Json> rows(){C33MatrixAccess::close(*r);std::ifstream f(source_file);std::string line;std::vector<p1::Json> out;while(std::getline(f,line))out.push_back(p1::Json::parse(line));return out;}
  static std::vector<p1::Json> of_type(const std::vector<p1::Json> &v,const std::string &name){std::vector<p1::Json> out;for(const auto &e:v)if(e.value("type","")==name)out.push_back(e);return out;}
  void assert_odom_rejected(nav_msgs::msg::Odometry invalid){
    C33MatrixAccess::odom(*r,odom_msg());const auto before=C33MatrixAccess::snapshot(*r);const auto b=C33MatrixAccess::state(*r);
    C33MatrixAccess::odom(*r,invalid);const auto after=C33MatrixAccess::final(*r);const auto a=C33MatrixAccess::state(*r);
    EXPECT_EQ(after.state,before.state);EXPECT_EQ(after.odom_seq,before.odom_seq);EXPECT_EQ(after.odom_stamp,before.odom_stamp);EXPECT_EQ(after.odom_receive,before.odom_receive);EXPECT_EQ(after.mixed,before.mixed);
    EXPECT_EQ(a["ordinal"].get<uint64_t>(),b["ordinal"].get<uint64_t>()+1);EXPECT_EQ(a["odom_received"].get<uint64_t>(),b["odom_received"].get<uint64_t>()+1);
    auto log=of_type(rows(),"odom_admission");ASSERT_EQ(log.size(),2);EXPECT_EQ(log.back()["valid"],false);EXPECT_EQ(log.back()["accepted_sequence"],1);EXPECT_TRUE(log.back()["raw_input"].is_null());
  }
  void assert_imu_rejected(sensor_msgs::msg::Imu invalid){
    C33MatrixAccess::odom(*r,odom_msg());C33MatrixAccess::imu(*r,imu_msg());const auto before=C33MatrixAccess::snapshot(*r);
    C33MatrixAccess::imu(*r,invalid);const auto after=C33MatrixAccess::final(*r);
    EXPECT_EQ(after.state,before.state);EXPECT_EQ(after.imu_seq,before.imu_seq);EXPECT_EQ(after.imu_stamp,before.imu_stamp);EXPECT_EQ(after.imu_receive,before.imu_receive);EXPECT_EQ(after.mixed,true);EXPECT_EQ(after.input_commit_ordinal,before.input_commit_ordinal+1);
    auto log=of_type(rows(),"imu_admission");ASSERT_EQ(log.size(),2);EXPECT_EQ(log.back()["valid"],false);EXPECT_EQ(log.back()["accepted_sequence"],1);
  }
  void assert_invalid_path(nav_msgs::msg::Path invalid){
    reference();C33MatrixAccess::seed_live_candidate(*r);const auto before=C33MatrixAccess::snapshot(*r);
    C33MatrixAccess::path(*r,invalid);const auto after=C33MatrixAccess::snapshot(*r);
    EXPECT_TRUE(after.ref->path.empty());EXPECT_EQ(after.ref->profile,before.ref->profile);EXPECT_EQ(after.ref->profile_sequence,before.ref->profile_sequence);
    EXPECT_EQ(after.ref->path_sequence,before.ref->path_sequence+1);EXPECT_GT(after.version.task,before.version.task);EXPECT_EQ(after.input_commit_ordinal,before.input_commit_ordinal+1);
    EXPECT_EQ(C33MatrixAccess::state(*r)["admission_slots"],0);EXPECT_EQ(C33MatrixAccess::state(*r)["candidate_present"],false);EXPECT_EQ(before.ref->path.size(),2);
    auto log=of_type(rows(),"path_version");ASSERT_EQ(log.size(),2);EXPECT_EQ(log.back()["valid"],false);EXPECT_EQ(log.back()["points"],0);
  }
  void assert_invalid_profile(std_msgs::msg::Float64MultiArray invalid){
    reference();C33MatrixAccess::seed_live_candidate(*r);const auto before=C33MatrixAccess::snapshot(*r);
    C33MatrixAccess::profile(*r,invalid);const auto after=C33MatrixAccess::snapshot(*r);
    EXPECT_TRUE(after.ref->profile.empty());EXPECT_EQ(after.ref->path,before.ref->path);EXPECT_EQ(after.ref->path_sequence,before.ref->path_sequence);EXPECT_EQ(after.ref->profile_sequence,before.ref->profile_sequence+1);
    EXPECT_GT(after.version.task,before.version.task);EXPECT_EQ(after.input_commit_ordinal,before.input_commit_ordinal+1);EXPECT_EQ(C33MatrixAccess::state(*r)["admission_slots"],0);EXPECT_EQ(before.ref->profile.size(),2);
    auto log=of_type(rows(),"profile_version");ASSERT_EQ(log.size(),2);EXPECT_EQ(log.back()["valid"],false);EXPECT_EQ(log.back()["rows"],0);
  }
  void assert_clock_reset(int64_t next){
    C33MatrixAccess::clock(*r,clock_msg(1000000000));C33MatrixAccess::seed_history(*r);C33MatrixAccess::seed_live_candidate(*r);const auto before=C33MatrixAccess::snapshot(*r);
    C33MatrixAccess::clock(*r,clock_msg(next));const auto after=C33MatrixAccess::snapshot(*r);
    EXPECT_EQ(after.version.epoch,before.version.epoch+1);EXPECT_EQ(after.version.schedule,before.version.schedule+1);EXPECT_TRUE(after.history.empty());EXPECT_TRUE(after.publication_history.empty());EXPECT_EQ(after.anchor.known,(std::array<bool,2>{false,false}));EXPECT_FALSE(after.rtf_valid);EXPECT_EQ(after.input_commit_ordinal,before.input_commit_ordinal+1);EXPECT_EQ(C33MatrixAccess::state(*r)["candidate_present"],false);
  }
  void assert_capability_preserved(const p1::Json &before){const auto after=C33MatrixAccess::state(*r);
    for(const auto *field:{"ordinal","last_valid_ns","last_capability","last_capability_commit_ns","worker_instance","worker_valid"})EXPECT_EQ(after[field],before[field])<<field;
    EXPECT_FALSE(after["worker_unusable"].get<bool>());
  }
  // Executes the real two-phase tick loop with a real callback thread released
  // between original validation and final mutex. Tick0 establishes a committed
  // candidate for tick1; tick2 follows the original bounded shutdown path.
  p1::Json gate_race(const std::function<void()> &mutate){
    C33MatrixAccess::install_hooks(*r,[&](uint64_t tick,int64_t planned){
      if(tick>1)return;
      auto o=odom_msg(1000000000+int64_t(tick)*p1::T-1000000);o.pose.pose.position.x=0;o.pose.pose.position.y=0;o.twist.twist.linear.x=0;o.twist.twist.linear.y=0;o.twist.twist.angular.z=0;
      C33MatrixAccess::clock(*r,clock_msg(1000000000+int64_t(tick)*p1::T));C33MatrixAccess::path(*r,path_msg());C33MatrixAccess::profile(*r,profile_msg());C33MatrixAccess::odom(*r,o);C33MatrixAccess::capability(*r,C33MatrixAccess::valid_capability(*r));C33MatrixAccess::seed_tick_preconditions(*r,tick,planned);
    },[&](uint64_t tick){if(tick==1){std::thread callback([&]{mutate();});callback.join();}},[&](uint64_t tick){if(tick==1)stop_requested=true;});
    C33MatrixAccess::run_tick(*r);const auto log=of_type(rows(),"decision");
    for(const auto &e:log)if(e.at("tick")==1)return e;
    ADD_FAILURE()<<"original tick1 Decision not observed";return p1::Json::object();
  }
  std::filesystem::path folder,source_file;p1::shadow::LegacyIdentity id;std::unique_ptr<Regulator> r;
};

TEST_F(C33InputMatrix,OdomInvalidNumericRetainsAcceptedPrefix){auto m=odom_msg(2000000000);m.pose.pose.position.x=std::numeric_limits<double>::quiet_NaN();assert_odom_rejected(m);}
TEST_F(C33InputMatrix,OdomZeroQuaternionRetainsAcceptedPrefix){auto m=odom_msg(2000000000);m.pose.pose.orientation.w=0;assert_odom_rejected(m);}
TEST_F(C33InputMatrix,OdomWrongFrameRetainsAcceptedPrefix){auto m=odom_msg(2000000000);m.header.frame_id="foreign";m.child_frame_id="foreign-child";assert_odom_rejected(m);}
TEST_F(C33InputMatrix,ImuInvalidNumericRetainsAcceptedPrefix){auto m=imu_msg(2000000000);m.angular_velocity.z=std::numeric_limits<double>::quiet_NaN();assert_imu_rejected(m);}
TEST_F(C33InputMatrix,ImuWrongFrameRetainsAcceptedPrefix){auto m=imu_msg(2000000000);m.header.frame_id="foreign";assert_imu_rejected(m);}
TEST_F(C33InputMatrix,ValidOdomResetsMixedButKeepsRawImuPrefix){C33MatrixAccess::imu(*r,imu_msg());auto before=C33MatrixAccess::snapshot(*r);C33MatrixAccess::odom(*r,odom_msg());auto after=C33MatrixAccess::snapshot(*r);EXPECT_FALSE(after.mixed);EXPECT_EQ(after.state[5],6);EXPECT_EQ(after.imu_seq,before.imu_seq);EXPECT_EQ(after.imu_stamp,before.imu_stamp);EXPECT_EQ(after.imu_receive,before.imu_receive);EXPECT_EQ(after.input_commit_ordinal,before.input_commit_ordinal+1);EXPECT_EQ(p1::d0::source_json(after)["imu_sequence"],1);}
TEST_F(C33InputMatrix,PathInvalidNumericClearsAndInvalidates){auto m=path_msg();m.poses[1].pose.position.x=std::numeric_limits<double>::quiet_NaN();assert_invalid_path(m);}
TEST_F(C33InputMatrix,PathWrongFrameClearsAndInvalidates){auto m=path_msg();m.header.frame_id="foreign";assert_invalid_path(m);}
TEST_F(C33InputMatrix,PathSinglePointIsNotEligible){reference();C33MatrixAccess::seed_live_candidate(*r);const auto before=C33MatrixAccess::snapshot(*r);auto m=path_msg();m.poses.resize(1);C33MatrixAccess::path(*r,m);auto after=C33MatrixAccess::snapshot(*r);EXPECT_EQ(after.ref->path.size(),1);EXPECT_GT(after.version.task,before.version.task);EXPECT_EQ(C33MatrixAccess::state(*r)["candidate_present"],false);C33MatrixAccess::odom(*r,odom_msg());EXPECT_EQ(C33MatrixAccess::eligible(*r),"no_path");auto log=of_type(rows(),"path_version");ASSERT_EQ(log.size(),2);EXPECT_EQ(log.back()["valid"],true);}
TEST_F(C33InputMatrix,ProfileMalformedRowsClearAndInvalidate){auto m=profile_msg();m.data.pop_back();assert_invalid_profile(m);}
TEST_F(C33InputMatrix,ProfileNonmonotoneTimeClearsAndInvalidate){auto m=profile_msg();m.data[7]=0;assert_invalid_profile(m);}
TEST_F(C33InputMatrix,ProfileNonfiniteClearsAndInvalidate){auto m=profile_msg();m.data[5]=std::numeric_limits<double>::quiet_NaN();assert_invalid_profile(m);}
TEST_F(C33InputMatrix,ProfileBadStampKeepsNumericRowsButNotReady){reference();auto before=C33MatrixAccess::snapshot(*r);auto m=profile_msg();m.layout.dim[0].label="stamp_sec:invalid";C33MatrixAccess::profile(*r,m);auto after=C33MatrixAccess::snapshot(*r);EXPECT_EQ(after.ref->profile,before.ref->profile);EXPECT_EQ(after.ref->profile_stamp,(std::pair<int,int>{-1,-1}));EXPECT_EQ(after.version.task,before.version.task);EXPECT_EQ(C33MatrixAccess::state(*r)["ready_profile_valid"],false);auto log=of_type(rows(),"profile_version");ASSERT_EQ(log.size(),2);EXPECT_EQ(log.back()["valid"],true);EXPECT_EQ(log.back()["resource_valid"],true);}
TEST_F(C33InputMatrix,ReferenceSameContentNewIdentityPreservesTaskButChangesSelection){reference();const auto before=C33MatrixAccess::snapshot(*r);C33MatrixAccess::path(*r,path_msg(2,123));C33MatrixAccess::profile(*r,profile_msg(2,123));const auto after=C33MatrixAccess::final(*r);EXPECT_EQ(after.version.task,before.version.task);EXPECT_EQ(after.path_fingerprint,before.path_fingerprint);EXPECT_EQ(after.profile_fingerprint,before.profile_fingerprint);EXPECT_EQ(after.ref->path_sequence,before.ref->path_sequence+1);EXPECT_EQ(after.ref->profile_sequence,before.ref->profile_sequence+1);EXPECT_EQ(after.ref->path_stamp,(std::pair<int,int>{2,123}));EXPECT_EQ(before.ref->path_stamp,(std::pair<int,int>{1,0}));EXPECT_EQ(after.input_commit_ordinal,before.input_commit_ordinal+2);EXPECT_NE(p1::d0::source_json(after)["ref_selection"],p1::d0::source_json(before)["ref_selection"]);}
TEST_F(C33InputMatrix,ScalarEquivalentStampPairsRemainDistinctSelections){C33MatrixAccess::path(*r,path_msg(1,1000000001));C33MatrixAccess::profile(*r,profile_msg(1,1000000001));const auto before=C33MatrixAccess::snapshot(*r);C33MatrixAccess::path(*r,path_msg(2,1));C33MatrixAccess::profile(*r,profile_msg(2,1));const auto after=C33MatrixAccess::snapshot(*r);EXPECT_EQ(int64_t(before.ref->path_stamp.first)*1000000000+before.ref->path_stamp.second,int64_t(after.ref->path_stamp.first)*1000000000+after.ref->path_stamp.second);EXPECT_NE(before.ref->path_stamp,after.ref->path_stamp);EXPECT_EQ(before.version.task,after.version.task);const auto b=p1::d0::source_json(before)["ref_selection"],a=p1::d0::source_json(after)["ref_selection"];EXPECT_EQ(b["path_stamp"]["sec"],1);EXPECT_EQ(b["path_stamp"]["nanosec"],1000000001);EXPECT_EQ(a["profile_stamp"]["sec"],2);EXPECT_EQ(a["profile_stamp"]["nanosec"],1);}
TEST_F(C33InputMatrix,ClockRegressionClearsHistoryAndEpoch){assert_clock_reset(999999999);}
TEST_F(C33InputMatrix,ClockLargeJumpClearsHistoryAndEpoch){assert_clock_reset(6000000001);}
TEST_F(C33InputMatrix,ActualTickPauseAndCallbackResume){
  C33MatrixAccess::clock(*r,clock_msg(1000000000));C33MatrixAccess::seed_history(*r);C33MatrixAccess::seed_pause_clock(*r);const auto before=C33MatrixAccess::snapshot(*r);
  C33MatrixAccess::install_hooks(*r,{}, {},[&](uint64_t tick){if(tick==0)stop_requested=true;});C33MatrixAccess::run_tick(*r);
  const auto paused=C33MatrixAccess::snapshot(*r);EXPECT_TRUE(paused.paused);EXPECT_GT(paused.version.schedule,before.version.schedule);
  C33MatrixAccess::clock(*r,clock_msg(1000000001));const auto resumed=C33MatrixAccess::snapshot(*r);EXPECT_FALSE(resumed.paused);EXPECT_EQ(resumed.version.schedule,paused.version.schedule+1);EXPECT_EQ(resumed.version.epoch,paused.version.epoch);EXPECT_EQ(resumed.input_commit_ordinal,paused.input_commit_ordinal+1);
  const auto log=of_type(rows(),"decision");ASSERT_GE(log.size(),2);EXPECT_EQ(log[0]["d0_observation"]["validation_snapshot"]["paused"],true);
}
TEST_F(C33InputMatrix,CapabilityForeignAfterValidKeepsLease){auto good=C33MatrixAccess::valid_capability(*r);C33MatrixAccess::capability(*r,good);const auto before=C33MatrixAccess::state(*r);ASSERT_GT(before["last_valid_ns"].get<int64_t>(),0);auto foreign=good;foreign.run_id="foreign";foreign.fatal=true;C33MatrixAccess::capability(*r,foreign);assert_capability_preserved(before);foreign=good;foreign.pid++;C33MatrixAccess::capability(*r,foreign);assert_capability_preserved(before);const auto log=of_type(rows(),"capability_admission");ASSERT_EQ(log.size(),3);for(size_t i=1;i<log.size();++i){EXPECT_EQ(log[i]["identity_valid"],false);EXPECT_EQ(log[i]["renewed"],false);EXPECT_EQ(log[i]["terminal_run"],false);}}
TEST_F(C33InputMatrix,CapabilityInvalidAfterValidKeepsLease){auto good=C33MatrixAccess::valid_capability(*r);C33MatrixAccess::capability(*r,good);const auto before=C33MatrixAccess::state(*r);for(int i=0;i<3;++i){auto bad=good;if(i==0)bad.backend="other";else if(i==1)bad.horizon_steps=19;else bad.prediction_dt=.25;C33MatrixAccess::capability(*r,bad);assert_capability_preserved(before);}const auto log=of_type(rows(),"capability_admission");ASSERT_EQ(log.size(),4);for(size_t i=1;i<log.size();++i){EXPECT_EQ(log[i]["identity_valid"],true);EXPECT_EQ(log[i]["valid"],false);EXPECT_EQ(log[i]["lease_last_after_ns"],before["last_valid_ns"]);}}
TEST_F(C33InputMatrix,CapabilityResourceRejectedAfterValidKeepsLease){auto good=C33MatrixAccess::valid_capability(*r);C33MatrixAccess::capability(*r,good);const auto before=C33MatrixAccess::state(*r);auto bad=good;bad.reason=std::string(257,'x');C33MatrixAccess::capability(*r,bad);assert_capability_preserved(before);auto rejected=of_type(rows(),"resource_rejected");ASSERT_EQ(rejected.size(),1);EXPECT_EQ(rejected[0]["interface"],"capability");EXPECT_EQ(rejected[0]["renewed"],false);}
TEST_F(C33InputMatrix,CapabilityExpiredLeaseIsIrreversible){auto good=C33MatrixAccess::valid_capability(*r);C33MatrixAccess::capability(*r,good);auto before=C33MatrixAccess::state(*r);C33MatrixAccess::expire(*r);EXPECT_TRUE(C33MatrixAccess::state(*r)["worker_unusable"].get<bool>());C33MatrixAccess::capability(*r,good);auto after=C33MatrixAccess::state(*r);EXPECT_EQ(after["last_valid_ns"],before["last_valid_ns"]);EXPECT_EQ(after["worker_valid"],false);auto terminal=of_type(rows(),"worker_unusable_transition");ASSERT_EQ(terminal.size(),1);EXPECT_EQ(terminal[0]["reason"],"worker_capability_expired");}
TEST_F(C33InputMatrix,CapabilityChangedInstanceIsTerminal){auto good=C33MatrixAccess::valid_capability(*r);C33MatrixAccess::capability(*r,good);const auto before=C33MatrixAccess::state(*r);auto bad=good;bad.worker_instance=std::string(64,'f');bad.backend="other";C33MatrixAccess::capability(*r,bad);C33MatrixAccess::capability(*r,good);auto after=C33MatrixAccess::state(*r);EXPECT_TRUE(after["worker_unusable"].get<bool>());EXPECT_EQ(after["last_valid_ns"],before["last_valid_ns"]);auto terminal=of_type(rows(),"worker_unusable_transition");ASSERT_EQ(terminal.size(),1);EXPECT_EQ(terminal[0]["reason"],"worker_instance_changed");}
TEST_F(C33InputMatrix,CapabilityMatchingFatalIsTerminal){auto good=C33MatrixAccess::valid_capability(*r);C33MatrixAccess::capability(*r,good);auto before=C33MatrixAccess::state(*r);auto bad=good;bad.fatal=true;C33MatrixAccess::capability(*r,bad);C33MatrixAccess::capability(*r,good);auto after=C33MatrixAccess::state(*r);EXPECT_TRUE(after["worker_unusable"].get<bool>());EXPECT_EQ(after["last_valid_ns"],before["last_valid_ns"]);auto terminal=of_type(rows(),"worker_unusable_transition");ASSERT_EQ(terminal.size(),1);EXPECT_EQ(terminal[0]["reason"],"fatal_capability");}
TEST_F(C33InputMatrix,ActualGateRaceValidOdomRejectsChangedSequence){auto d=gate_race([&]{auto m=odom_msg(1199000000);m.pose.pose.position.x=0;m.pose.pose.position.y=0;m.twist.twist.linear.x=0;m.twist.twist.linear.y=0;m.twist.twist.angular.z=0;C33MatrixAccess::odom(*r,m);});ASSERT_FALSE(d.empty());EXPECT_EQ(d["reason"],"activation_input_changed_during_validation");EXPECT_EQ(d["accepted"],false);auto g=d["d0_observation"]["gate_reads"];EXPECT_EQ(g["input_version_equal"],true);EXPECT_EQ(g["input_odom_equal"],false);EXPECT_TRUE(g["input_imu_equal"].is_null());}
TEST_F(C33InputMatrix,ActualGateRaceValidImuRejectsChangedSequence){auto d=gate_race([&]{auto m=imu_msg(1199000000);m.angular_velocity.z=0;C33MatrixAccess::imu(*r,m);});ASSERT_FALSE(d.empty());EXPECT_EQ(d["reason"],"activation_input_changed_during_validation");auto g=d["d0_observation"]["gate_reads"];EXPECT_EQ(g["input_version_equal"],true);EXPECT_EQ(g["input_odom_equal"],true);EXPECT_EQ(g["input_imu_equal"],false);}
TEST_F(C33InputMatrix,ActualGateRaceChangedReferenceStopsAtVersion){auto d=gate_race([&]{auto m=path_msg();m.poses[1].pose.position.x=2;C33MatrixAccess::path(*r,m);});ASSERT_FALSE(d.empty());EXPECT_EQ(d["reason"],"activation_input_changed_during_validation");auto g=d["d0_observation"]["gate_reads"];EXPECT_EQ(g["input_version_equal"],false);EXPECT_TRUE(g["input_odom_equal"].is_null());EXPECT_TRUE(g["input_imu_equal"].is_null());EXPECT_EQ(d["d0_observation"]["candidate_capture"]["candidate_present"],true);EXPECT_FALSE(C33MatrixAccess::state(*r)["candidate_present"].get<bool>());}
TEST_F(C33InputMatrix,ActualGateRaceInvalidOdomKeepsAcceptedPrefix){auto d=gate_race([&]{auto m=odom_msg(1199000000);m.pose.pose.position.x=std::numeric_limits<double>::quiet_NaN();C33MatrixAccess::odom(*r,m);});ASSERT_FALSE(d.empty());EXPECT_EQ(d["reason"],"");EXPECT_EQ(d["accepted"],true);auto o=d["d0_observation"];EXPECT_EQ(o["gate_reads"]["input_version_equal"],true);EXPECT_EQ(o["gate_reads"]["input_odom_equal"],true);EXPECT_EQ(o["gate_reads"]["input_imu_equal"],true);EXPECT_EQ(o["final_snapshot"]["input_commit_ordinal"].get<uint64_t>(),o["validation_snapshot"]["input_commit_ordinal"].get<uint64_t>()+1);EXPECT_EQ(o["final_snapshot"]["odom_sequence"],o["validation_snapshot"]["odom_sequence"]);}
TEST_F(C33InputMatrix,ActualGateRaceStopRequestedFinalOverride){auto d=gate_race([&]{stop_requested=true;});ASSERT_FALSE(d.empty());EXPECT_EQ(d["reason"],"shutdown");EXPECT_EQ(d["accepted"],false);auto g=d["d0_observation"]["gate_reads"];EXPECT_EQ(g["final_stopping"],false);EXPECT_EQ(g["final_stop_requested"],true);EXPECT_EQ(d["control_source"],"ramp_zero");}
TEST_F(C33InputMatrix,ActualGateRaceLeaseLossFailsClosed){auto d=gate_race([&]{C33MatrixAccess::expire(*r);});ASSERT_FALSE(d.empty());EXPECT_EQ(d["reason"],"run_unusable_at_commit");EXPECT_EQ(d["accepted"],false);auto g=d["d0_observation"]["gate_reads"];EXPECT_EQ(g["commit_worker_unusable"],true);EXPECT_TRUE(g["commit_worker_valid"].is_null());EXPECT_TRUE(g["commit_sink_failed"].is_null());EXPECT_EQ(g["fallback_invalid_worker_unusable"],true);EXPECT_TRUE(C33MatrixAccess::state(*r)["worker_unusable"].get<bool>());}
