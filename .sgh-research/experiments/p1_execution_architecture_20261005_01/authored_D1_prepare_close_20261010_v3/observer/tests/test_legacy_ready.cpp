// SPDX-License-Identifier: MIT
// Source-including tests call production callbacks and the actual readiness
// issue/deadline/invalidation paths. No copied readiness business model exists.
#include <gtest/gtest.h>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#define P1_SHADOW_ENTRY_TEST
#define P1_LEGACY_READY_TEST
#define main p1_shadow_ready_program_main
#include P1_REGULATOR_SOURCE
#undef main

using Applied=usv_research_interfaces::msg::AppliedControl;
class LegacyReadyAccess {
 public:
  static std::unique_ptr<Regulator> make(const std::string &path,const p1::shadow::LegacyIdentity &id){stop_requested=false;return std::unique_ptr<Regulator>(new Regulator(Regulator::LegacyReadyTestTag{},path,id));}
  static void apply(Regulator &r,const Applied &m){r.legacy_applied(m);}
  static void odom(Regulator &r,const nav_msgs::msg::Odometry &m){r.odom(m);}
  static void imu(Regulator &r,const sensor_msgs::msg::Imu &m){r.imu(m);}
  static void path(Regulator &r,const nav_msgs::msg::Path &m){r.path(m);}
  static void profile(Regulator &r,const std_msgs::msg::Float64MultiArray &m){r.profile(m);}
  static void clock(Regulator &r,const rosgraph_msgs::msg::Clock &m){r.clock(m);}
  static void capability(Regulator &r,const p1::Capability &m){r.capability(m);}
  static p1::Json state(Regulator &r){std::lock_guard<std::mutex> l(r.mutex_);return {{"issued",r.legacy_ready_issued_},{"eligible",r.legacy_measurement_eligible_.load()},{"terminal",r.legacy_readiness_terminal_},{"worker_terminal",r.worker_unusable_.load()},{"pending_reason",r.legacy_ready_pending_reason_},{"admitted",r.legacy_admitted_}};}
  static p1::Capability valid_capability(Regulator &r){p1::Capability m;m.schema_version="p1-worker-capability-v1";m.run_id=r.run_;m.boot_id=r.boot_;m.contract_hash=r.hash_;m.nominal_hash=r.nominal_;m.worker_instance=std::string(64,'e');m.clock_name="CLOCK_MONOTONIC";m.backend="acados";m.matrix_layout="column_major";m.horizon_steps=20;m.prediction_dt=.2;m.pid=getpid();m.startup_ns=p1::monotonic_ns()-1000;m.fault_injection_enabled=true;return m;}
  static void expire_prepare(Regulator &r){std::lock_guard<std::mutex> l(r.mutex_);r.check_legacy_prepare_timeout_locked(r.legacy_prepare_deadline_ns_+1);}
  static void one_sided_history(Regulator &r){std::lock_guard<std::mutex> l(r.mutex_);r.history_.pop_back();r.ready_history_.pop_back();}
  static void expire_capability(Regulator &r){std::lock_guard<std::mutex> l(r.mutex_);r.check_worker_locked(r.capability_lease_->last_valid_ns()+r.capability_lease_->timeout_ns()+1);}
  static bool enqueue(Regulator &r){p1::Decision d;const auto now=p1::monotonic_ns();d.sequence=1;d.tick_end_ns=now;int64_t stop=0;r.finish_tick(d,now,now,0,stop);std::lock_guard<std::mutex> q(r.prep_mutex_);return bool(r.pending_);}
  static std::vector<p1::Json> rows(Regulator &r,const std::filesystem::path &file){r.sink_->close();std::ifstream f(file);std::vector<p1::Json> out;std::string line;while(std::getline(f,line))out.push_back(p1::Json::parse(line));return out;}
};

class LegacyReady:public ::testing::Test {
 protected:
  static void SetUpTestSuite(){int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);}
  static void TearDownTestSuite(){rclcpp::shutdown();}
  void SetUp()override{const auto *base=std::getenv("P1_BRANCH_TEST_OUTPUT");ASSERT_NE(base,nullptr);folder=std::filesystem::path(base)/::testing::UnitTest::GetInstance()->current_test_info()->name();ASSERT_FALSE(std::filesystem::exists(folder));std::filesystem::create_directories(folder);source=folder/"source.jsonl";id={"p0-contract-v1","legacy-ready-test","legacy-ready-test:12345","F5_20261005_atomic_freeze_01",std::string(64,'a'),p1::boot_id()+":steady_clock"};r=LegacyReadyAccess::make(source.string(),id);}
  static builtin_interfaces::msg::Time stamp(int64_t ns){builtin_interfaces::msg::Time t;t.sec=ns/1000000000;t.nanosec=ns%1000000000;return t;}
  rosgraph_msgs::msg::Clock clock_msg(int64_t ns)const{rosgraph_msgs::msg::Clock m;m.clock=stamp(ns);return m;}
  nav_msgs::msg::Path path_msg(int sec=1)const{nav_msgs::msg::Path m;m.header.frame_id="map";m.header.stamp=stamp(int64_t(sec)*1000000000);m.poses.resize(2);m.poses[0].pose.orientation.w=1;m.poses[1].pose.orientation.w=1;m.poses[1].pose.position.x=1;return m;}
  std_msgs::msg::Float64MultiArray profile_msg(int sec=1)const{std_msgs::msg::Float64MultiArray m;m.layout.dim.resize(2);m.layout.dim[0].label="stamp_sec:"+std::to_string(sec);m.layout.dim[1].label="stamp_nanosec:0";m.data={0,0.6,0,0,1,0.6,0,1};return m;}
  nav_msgs::msg::Odometry odom_msg(int64_t ns)const{nav_msgs::msg::Odometry m;m.header.frame_id="map";m.child_frame_id="wamv/base_link";m.header.stamp=stamp(ns);m.pose.pose.orientation.w=1;return m;}
  sensor_msgs::msg::Imu imu_msg(int64_t ns)const{sensor_msgs::msg::Imu m;m.header.frame_id="wamv/wamv/base_link/imu_sensor";m.header.stamp=stamp(ns);m.angular_velocity.z=0;return m;}
  Applied pair(uint64_t seq=1)const{Applied m;m.schema_version=id.schema;m.run_id=id.run;m.producer_instance_id=id.producer;m.baseline_id=id.baseline;m.config_hash=id.config;m.steady_clock_domain=id.domain;m.sequence=seq;m.event_semantics="publisher_command";m.map_scale=1;m.lower_n=-25;m.upper_n=25;m.final_n={1,2};m.requested_known=true;m.requested_n=m.final_n;m.clock_epoch=0;m.left_clock_epoch=0;m.right_clock_epoch=0;m.sim_time_ns=current_sim;m.left_sim_time_ns=current_sim;m.right_sim_time_ns=current_sim;m.clock_status="valid";m.control_source="nmpc";m.left_publish_success=true;m.right_publish_success=true;m.left_publish_start_steady_ns=p1::monotonic_ns()-1000;m.left_publish_end_steady_ns=m.left_publish_start_steady_ns+10;m.right_publish_start_steady_ns=m.left_publish_end_steady_ns+10;m.right_publish_end_steady_ns=m.right_publish_start_steady_ns+10;m.clock_receive_steady_ns=m.left_publish_start_steady_ns-100;m.clock_age_ns=100;m.left_clock_age_ns=100;m.right_clock_age_ns=100;return m;}
  void inputs(bool with_imu=true,bool with_capability=true,bool with_profile=true){
    // Two real clock callbacks separated by a finite wall interval exercise the
    // immutable ClockWindow. No test override sets an RTF-valid business flag.
    const auto start=p1::monotonic_ns();LegacyReadyAccess::clock(*r,clock_msg(1000000000));
    std::this_thread::sleep_for(std::chrono::milliseconds(420));current_sim=1000000000+p1::monotonic_ns()-start;LegacyReadyAccess::clock(*r,clock_msg(current_sim));
    LegacyReadyAccess::path(*r,path_msg());if(with_profile)LegacyReadyAccess::profile(*r,profile_msg());if(with_capability)LegacyReadyAccess::capability(*r,LegacyReadyAccess::valid_capability(*r));if(with_imu)LegacyReadyAccess::imu(*r,imu_msg(current_sim));
  }
  void ready(){inputs();LegacyReadyAccess::apply(*r,pair());LegacyReadyAccess::odom(*r,odom_msg(current_sim));ASSERT_EQ(LegacyReadyAccess::state(*r)["issued"],true);}
  std::vector<p1::Json> rows(){return LegacyReadyAccess::rows(*r,source);}
  static size_t count(const std::vector<p1::Json> &v,const std::string &type){size_t n=0;for(const auto &e:v)if(e.value("type","")==type)++n;return n;}
  std::filesystem::path folder,source;p1::shadow::LegacyIdentity id;std::unique_ptr<Regulator> r;int64_t current_sim=1000000000;
};

TEST_F(LegacyReady,GraphArmedAloneIsNotLegacyReadiness){EXPECT_FALSE(LegacyReadyAccess::state(*r)["issued"].get<bool>());const auto v=rows();EXPECT_EQ(count(v,"recording_ready"),1);EXPECT_EQ(count(v,"legacy_ready"),0);}
TEST_F(LegacyReady,WholePairAndPostPairOdomIssueExactOnceReady){ready();LegacyReadyAccess::odom(*r,odom_msg(current_sim));LegacyReadyAccess::imu(*r,imu_msg(current_sim));const auto v=rows();ASSERT_EQ(count(v,"legacy_ready"),1);for(const auto &e:v)if(e.value("type","")=="legacy_ready"){const auto &a=e.at("readiness");EXPECT_EQ(a["legacy_identity"],id.json());EXPECT_EQ(a["anchor_sequence"],(std::array<uint64_t,2>{1,1}));EXPECT_EQ(a["anchor_sim_ns"],(std::array<int64_t,2>{current_sim,current_sim}));EXPECT_GT(a["odom_receive_ns"].get<int64_t>(),a["pair_processed_ns"].get<int64_t>());EXPECT_EQ(a["held_history"].size(),2);EXPECT_EQ(a["preodom_held"].size(),2);EXPECT_EQ(a["worker_capability"]["pid"],getpid());EXPECT_TRUE(a["measurement_eligible"].get<bool>());}}
TEST_F(LegacyReady,ActualEnqueueBoundaryAllowsOnlyAfterReady){ready();EXPECT_TRUE(LegacyReadyAccess::enqueue(*r));}
TEST_F(LegacyReady,OdomBeforePairCannotIssueOrEnqueue){inputs();LegacyReadyAccess::odom(*r,odom_msg(current_sim));LegacyReadyAccess::apply(*r,pair());EXPECT_FALSE(LegacyReadyAccess::state(*r)["issued"].get<bool>());EXPECT_FALSE(LegacyReadyAccess::enqueue(*r));}
TEST_F(LegacyReady,PrePairStampDespitePostPairReceiptCannotIssue){inputs();LegacyReadyAccess::apply(*r,pair());LegacyReadyAccess::odom(*r,odom_msg(current_sim-1));EXPECT_FALSE(LegacyReadyAccess::state(*r)["issued"].get<bool>());EXPECT_EQ(count(rows(),"legacy_ready"),0);}
TEST_F(LegacyReady,SameSimDualChannelIsLegalButOneSidedHistoryIsNot){inputs();LegacyReadyAccess::apply(*r,pair());LegacyReadyAccess::one_sided_history(*r);LegacyReadyAccess::odom(*r,odom_msg(current_sim));EXPECT_FALSE(LegacyReadyAccess::state(*r)["issued"].get<bool>());EXPECT_EQ(count(rows(),"legacy_ready"),0);}
TEST_F(LegacyReady,MissingImuCannotIssueEvenOdomRateIsActive){inputs(false);LegacyReadyAccess::apply(*r,pair());LegacyReadyAccess::odom(*r,odom_msg(current_sim));EXPECT_FALSE(LegacyReadyAccess::state(*r)["issued"].get<bool>());EXPECT_FALSE(LegacyReadyAccess::enqueue(*r));}
TEST_F(LegacyReady,MissingCapabilityAndForeignCapabilityCannotIssue){inputs(true,false);LegacyReadyAccess::apply(*r,pair());LegacyReadyAccess::odom(*r,odom_msg(current_sim));auto m=LegacyReadyAccess::valid_capability(*r);m.pid++;LegacyReadyAccess::capability(*r,m);EXPECT_FALSE(LegacyReadyAccess::state(*r)["issued"].get<bool>());EXPECT_EQ(count(rows(),"legacy_ready"),0);}
TEST_F(LegacyReady,ProfileStampMismatchCannotIssue){inputs(true,true,false);LegacyReadyAccess::profile(*r,profile_msg(2));LegacyReadyAccess::apply(*r,pair());LegacyReadyAccess::odom(*r,odom_msg(current_sim));EXPECT_FALSE(LegacyReadyAccess::state(*r)["issued"].get<bool>());EXPECT_EQ(count(rows(),"legacy_ready"),0);}
TEST_F(LegacyReady,FirstSequenceMustBeOneAndGapCannotRecoverPreparation){inputs();LegacyReadyAccess::apply(*r,pair(2));LegacyReadyAccess::odom(*r,odom_msg(current_sim));EXPECT_FALSE(LegacyReadyAccess::state(*r)["issued"].get<bool>());LegacyReadyAccess::apply(*r,pair(4));LegacyReadyAccess::odom(*r,odom_msg(current_sim));EXPECT_FALSE(LegacyReadyAccess::state(*r)["issued"].get<bool>());EXPECT_EQ(count(rows(),"legacy_ready"),0);}
TEST_F(LegacyReady,DuplicateBeforeReadyFailsCompleteReceiptConservation){inputs();auto m=pair();LegacyReadyAccess::apply(*r,m);LegacyReadyAccess::apply(*r,m);LegacyReadyAccess::odom(*r,odom_msg(current_sim));EXPECT_FALSE(LegacyReadyAccess::state(*r)["issued"].get<bool>());EXPECT_EQ(count(rows(),"legacy_ready"),0);}
TEST_F(LegacyReady,ProducerChangePermanentlyInvalidatesReady){ready();auto m=pair(2);m.producer_instance_id="changed";LegacyReadyAccess::apply(*r,m);LegacyReadyAccess::apply(*r,pair(3));const auto s=LegacyReadyAccess::state(*r);EXPECT_TRUE(s["terminal"].get<bool>());EXPECT_FALSE(s["eligible"].get<bool>());EXPECT_TRUE(s["worker_terminal"].get<bool>());const auto v=rows();EXPECT_EQ(count(v,"legacy_ready"),1);EXPECT_EQ(count(v,"legacy_ready_invalidated"),1);}
TEST_F(LegacyReady,DuplicateAfterReadyPermanentlyClosesGate){ready();LegacyReadyAccess::apply(*r,pair());LegacyReadyAccess::apply(*r,pair(2));EXPECT_FALSE(LegacyReadyAccess::state(*r)["eligible"].get<bool>());EXPECT_TRUE(LegacyReadyAccess::state(*r)["terminal"].get<bool>());EXPECT_FALSE(LegacyReadyAccess::enqueue(*r));const auto v=rows();EXPECT_EQ(count(v,"legacy_ready"),1);EXPECT_EQ(count(v,"legacy_ready_invalidated"),1);}
TEST_F(LegacyReady,ForeignReceiptAfterReadyPermanentlyClosesGate){ready();auto m=pair(2);m.run_id="foreign";LegacyReadyAccess::apply(*r,m);LegacyReadyAccess::apply(*r,pair(2));EXPECT_FALSE(LegacyReadyAccess::state(*r)["eligible"].get<bool>());EXPECT_TRUE(LegacyReadyAccess::state(*r)["terminal"].get<bool>());EXPECT_FALSE(LegacyReadyAccess::enqueue(*r));const auto v=rows();EXPECT_EQ(count(v,"legacy_ready"),1);EXPECT_EQ(count(v,"legacy_ready_invalidated"),1);}
TEST_F(LegacyReady,TruncatedProjectionAfterReadyPermanentlyClosesGate){ready();auto m=pair(2);m.control_source=std::string(129,'x');LegacyReadyAccess::apply(*r,m);LegacyReadyAccess::apply(*r,pair(3));EXPECT_FALSE(LegacyReadyAccess::state(*r)["eligible"].get<bool>());EXPECT_TRUE(LegacyReadyAccess::state(*r)["terminal"].get<bool>());EXPECT_FALSE(LegacyReadyAccess::enqueue(*r));const auto v=rows();EXPECT_EQ(count(v,"legacy_ready"),1);EXPECT_EQ(count(v,"legacy_ready_invalidated"),1);}
TEST_F(LegacyReady,SequenceGapPermanentlyInvalidatesReady){ready();LegacyReadyAccess::apply(*r,pair(3));LegacyReadyAccess::odom(*r,odom_msg(current_sim));EXPECT_FALSE(LegacyReadyAccess::state(*r)["eligible"].get<bool>());const auto v=rows();EXPECT_EQ(count(v,"legacy_ready"),1);EXPECT_EQ(count(v,"legacy_ready_invalidated"),1);}
TEST_F(LegacyReady,LossOfTrueHeldChannelAfterReadyIsTerminal){ready();LegacyReadyAccess::one_sided_history(*r);LegacyReadyAccess::odom(*r,odom_msg(current_sim));EXPECT_FALSE(LegacyReadyAccess::state(*r)["eligible"].get<bool>());EXPECT_EQ(count(rows(),"legacy_ready_invalidated"),1);}
TEST_F(LegacyReady,PartialPublishPermanentlyInvalidatesReady){ready();auto m=pair(2);m.right_publish_success=false;LegacyReadyAccess::apply(*r,m);LegacyReadyAccess::odom(*r,odom_msg(current_sim));EXPECT_FALSE(LegacyReadyAccess::state(*r)["eligible"].get<bool>());EXPECT_EQ(count(rows(),"legacy_ready_invalidated"),1);}
TEST_F(LegacyReady,ClockEpochChangePermanentlyInvalidatesReady){ready();LegacyReadyAccess::clock(*r,clock_msg(current_sim-1));LegacyReadyAccess::clock(*r,clock_msg(current_sim));EXPECT_FALSE(LegacyReadyAccess::state(*r)["eligible"].get<bool>());const auto v=rows();EXPECT_EQ(count(v,"legacy_ready"),1);EXPECT_EQ(count(v,"legacy_ready_invalidated"),1);}
TEST_F(LegacyReady,SameFingerprintReferenceRefreshKeepsOneReady){ready();LegacyReadyAccess::path(*r,path_msg(2));LegacyReadyAccess::profile(*r,profile_msg(2));LegacyReadyAccess::capability(*r,LegacyReadyAccess::valid_capability(*r));EXPECT_TRUE(LegacyReadyAccess::state(*r)["eligible"].get<bool>());const auto v=rows();EXPECT_EQ(count(v,"legacy_ready"),1);EXPECT_EQ(count(v,"legacy_ready_invalidated"),0);}
TEST_F(LegacyReady,ChangedReferenceDataInvalidatesReady){ready();auto m=path_msg();m.poses[1].pose.position.x=2;LegacyReadyAccess::path(*r,m);EXPECT_FALSE(LegacyReadyAccess::state(*r)["eligible"].get<bool>());EXPECT_EQ(count(rows(),"legacy_ready_invalidated"),1);}
TEST_F(LegacyReady,ExpiredCapabilityInvalidatesReady){ready();LegacyReadyAccess::expire_capability(*r);EXPECT_FALSE(LegacyReadyAccess::state(*r)["eligible"].get<bool>());EXPECT_EQ(count(rows(),"legacy_ready_invalidated"),1);}
TEST_F(LegacyReady,BoundedPrepareTimeoutIsSingleTerminalAndStops){LegacyReadyAccess::expire_prepare(*r);LegacyReadyAccess::expire_prepare(*r);EXPECT_TRUE(stop_requested.load());const auto s=LegacyReadyAccess::state(*r);EXPECT_TRUE(s["terminal"].get<bool>());EXPECT_TRUE(s["worker_terminal"].get<bool>());EXPECT_FALSE(s["issued"].get<bool>());const auto v=rows();EXPECT_EQ(count(v,"legacy_ready_failed"),1);EXPECT_EQ(count(v,"legacy_ready"),0);}
TEST_F(LegacyReady,ActualConstructorRejectsMissingAndUnboundedPrepareBudgetBeforeFiles){
  const auto contract=folder/"contract.json",identity=folder/"identity.cpp";const auto raw=p1::candidate_baseline().dump();{std::ofstream out(contract);out<<raw;}{std::ofstream out(identity);out<<"source-linked readiness identity fixture\n";}
  const auto out=folder/"runtime_source.jsonl",witness=folder/"runtime_witness.json";
  const std::vector<rclcpp::Parameter> base={{"run_id","shadow-ready-constructor-test"},{"mode","shadow"},{"contract_file",contract.string()},{"contract_hash",p1::digest(raw)},
    {"worker_pid",int64_t(getpid())},{"witness_enabled",true},{"source_file",out.string()},{"witness_file",witness.string()},{"diagnostic_source_file",identity.string()},
    {"diagnostic_source_sha256",file_sha(identity.string())},{"diagnostic_binary_sha256",file_sha("/proc/self/exe")},{"worker_binary_sha256",file_sha("/proc/self/exe")},{"witness_worker_instance",std::string(64,'e')},
    {"legacy_run_id",id.run},{"legacy_schema_version",id.schema},{"legacy_producer_instance_id",id.producer},{"legacy_config_hash",id.config},{"legacy_clock_domain",id.domain}};
  for(const auto value:{int64_t(0),int64_t(-1),int64_t(60001)}){auto values=base;if(value!=0)values.emplace_back("legacy_ready_timeout_ms",value);auto options=rclcpp::NodeOptions().parameter_overrides(values).enable_rosout(false).start_parameter_services(false).start_parameter_event_publisher(false);
    try{Regulator rejected(options);FAIL()<<"unbounded budget accepted";}catch(const std::exception &e){EXPECT_EQ(std::string(e.what()),"legacy_ready_timeout_ms must be explicitly within [1,60000]");}EXPECT_FALSE(std::filesystem::exists(out));EXPECT_FALSE(std::filesystem::exists(witness));}
}
