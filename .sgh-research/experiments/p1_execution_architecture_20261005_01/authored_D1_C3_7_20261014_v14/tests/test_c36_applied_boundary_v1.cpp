// SPDX-License-Identifier: MIT
// Source-linked callback/resource/readiness tests and the production tail
// predicate. Seeded predicate authentication inputs are not live owner-exit or
// continuous DDS evidence; the separately supervised runtime supplies those.
#include <gtest/gtest.h>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#define P1_SHADOW_ENTRY_TEST
#define P1_LEGACY_READY_TEST
#define P1_C36_APPLIED_BOUNDARY_TEST
#define main p1_c36_applied_boundary_program_main
#include P1_REGULATOR_SOURCE
#undef main

using Applied = usv_research_interfaces::msg::AppliedControl;
class C36AppliedBoundaryAccess {
 public:
  static std::unique_ptr<Regulator> make(const std::string &path,const p1::shadow::LegacyIdentity &id) {
    stop_requested=false;
    return std::unique_ptr<Regulator>(new Regulator(Regulator::LegacyReadyTestTag{},path,id));
  }
  static void receive(Regulator &r,const Applied &m,const rclcpp::MessageInfo &info) { r.receive_applied(m,info); }
  static void odom(Regulator &r,const nav_msgs::msg::Odometry &m) { r.odom(m); }
  static void imu(Regulator &r,const sensor_msgs::msg::Imu &m) { r.imu(m); }
  static void path(Regulator &r,const nav_msgs::msg::Path &m) { r.path(m); }
  static void profile(Regulator &r,const std_msgs::msg::Float64MultiArray &m) { r.profile(m); }
  static void clock(Regulator &r,const rosgraph_msgs::msg::Clock &m) { r.clock(m); }
  static void capability(Regulator &r,const p1::Capability &m) { r.capability(m); }
  static p1::Capability valid_capability(Regulator &r) {
    p1::Capability m; m.schema_version="p1-worker-capability-v1";m.run_id=r.run_;m.boot_id=r.boot_;
    m.contract_hash=r.hash_;m.nominal_hash=r.nominal_;m.worker_instance=std::string(64,'e');
    m.clock_name="CLOCK_MONOTONIC";m.backend="acados";m.matrix_layout="column_major";
    m.horizon_steps=20;m.prediction_dt=.2;m.pid=getpid();m.startup_ns=p1::monotonic_ns()-1000;
    m.fault_injection_enabled=true;return m;
  }
  static p1::Json state(Regulator &r) {
    std::lock_guard<std::mutex> lock(r.mutex_);
    return {{"received",r.legacy_received_},{"admitted",r.legacy_admitted_},
      {"ordinal",r.input_commit_ordinal_},{"raw_sequence",r.raw_callback_sequences_["/research/control/applied"]},
      {"lifecycle_complete",r.legacy_sequence_complete_},{"projection_complete",r.legacy_ready_projection_complete_},
      {"issued",r.legacy_ready_issued_},{"eligible",r.legacy_measurement_eligible_.load()},
      {"terminal",r.legacy_readiness_terminal_},{"worker_terminal",r.worker_unusable_.load()}};
  }
  static std::vector<p1::Json> rows(Regulator &r,const std::filesystem::path &file) {
    r.sink_->close();std::ifstream f(file);std::vector<p1::Json> out;std::string line;
    while(std::getline(f,line))out.push_back(p1::Json::parse(line));return out;
  }
  static bool tail(const Applied &m,const std::string &authentication="owner_process_exited",
      bool gid=true,bool driver_closed=true,bool business_closed=true,
      int64_t request=1000,int64_t observed=1100,int64_t receipt=2000) {
    return Regulator::queued_terminal_zero_predicate(m,authentication,gid,driver_closed,business_closed,
      request,observed,receipt);
  }
};

class C36AppliedBoundary : public ::testing::Test {
 protected:
  static void SetUpTestSuite() {
    int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);
  }
  static void TearDownTestSuite() { rclcpp::shutdown(); }
  void SetUp() override {
    const auto *base=std::getenv("P1_BRANCH_TEST_OUTPUT");ASSERT_NE(base,nullptr);
    folder_=std::filesystem::path(base)/::testing::UnitTest::GetInstance()->current_test_info()->name();
    ASSERT_FALSE(std::filesystem::exists(folder_));std::filesystem::create_directories(folder_);
    source_=folder_/"source.jsonl";
    id_={"p0-contract-v1","c36-boundary-legacy","c36-boundary-producer",
      "F5_20261005_atomic_freeze_01",std::string(64,'a'),p1::boot_id()+":steady_clock"};
    node_=C36AppliedBoundaryAccess::make(source_.string(),id_);
    pub_=node_->create_publisher<Applied>("/p1_test/c36_applied_metadata",rclcpp::QoS(10).reliable());
  }
  static builtin_interfaces::msg::Time stamp(int64_t ns) {
    builtin_interfaces::msg::Time out;out.sec=ns/1000000000;out.nanosec=ns%1000000000;return out;
  }
  rclcpp::MessageInfo info() const {
    rmw_message_info_t rmw{};rmw.publisher_gid=pub_->get_gid();return rclcpp::MessageInfo(rmw);
  }
  Applied pair(uint64_t sequence=1) const {
    Applied m;m.schema_version=id_.schema;m.run_id=id_.run;m.producer_instance_id=id_.producer;
    m.baseline_id=id_.baseline;m.config_hash=id_.config;m.steady_clock_domain=id_.domain;
    m.sequence=sequence;m.event_semantics="publisher_command";m.map_scale=1;m.lower_n=-25;m.upper_n=25;
    m.final_n={1,2};m.requested_known=true;m.requested_n=m.final_n;m.clock_epoch=0;
    m.left_clock_epoch=0;m.right_clock_epoch=0;m.sim_time_ns=sim_;m.left_sim_time_ns=sim_;m.right_sim_time_ns=sim_;
    m.clock_status="valid";m.control_source="nmpc";m.left_publish_success=true;m.right_publish_success=true;
    m.left_publish_start_steady_ns=p1::monotonic_ns()-1000;
    m.left_publish_end_steady_ns=m.left_publish_start_steady_ns+10;
    m.right_publish_start_steady_ns=m.left_publish_end_steady_ns+10;
    m.right_publish_end_steady_ns=m.right_publish_start_steady_ns+10;
    m.clock_receive_steady_ns=m.left_publish_start_steady_ns-100;m.clock_age_ns=100;
    m.left_clock_age_ns=100;m.right_clock_age_ns=100;return m;
  }
  static Applied zero_tail() {
    Applied m;m.control_source="shutdown_zero";m.final_n={0,0};m.left_publish_success=true;m.right_publish_success=true;
    m.left_publish_start_steady_ns=1200;m.left_publish_end_steady_ns=1300;
    m.right_publish_start_steady_ns=1400;m.right_publish_end_steady_ns=1500;return m;
  }
  void inputs() {
    const auto start=p1::monotonic_ns();rosgraph_msgs::msg::Clock c;c.clock=stamp(1000000000);
    C36AppliedBoundaryAccess::clock(*node_,c);
    std::this_thread::sleep_for(std::chrono::milliseconds(420));sim_=1000000000+p1::monotonic_ns()-start;
    c.clock=stamp(sim_);C36AppliedBoundaryAccess::clock(*node_,c);
    nav_msgs::msg::Path path;path.header.frame_id="map";path.header.stamp=stamp(1000000000);
    path.poses.resize(2);path.poses[0].pose.orientation.w=1;path.poses[1].pose.orientation.w=1;path.poses[1].pose.position.x=1;
    C36AppliedBoundaryAccess::path(*node_,path);
    std_msgs::msg::Float64MultiArray profile;profile.layout.dim.resize(2);
    profile.layout.dim[0].label="stamp_sec:1";profile.layout.dim[1].label="stamp_nanosec:0";
    profile.data={0,0.6,0,0,1,0.6,0,1};C36AppliedBoundaryAccess::profile(*node_,profile);
    C36AppliedBoundaryAccess::capability(*node_,C36AppliedBoundaryAccess::valid_capability(*node_));
    sensor_msgs::msg::Imu imu;imu.header.frame_id="wamv/wamv/base_link/imu_sensor";imu.header.stamp=stamp(sim_);
    C36AppliedBoundaryAccess::imu(*node_,imu);
  }
  void odom() {
    nav_msgs::msg::Odometry m;m.header.frame_id="map";m.child_frame_id="wamv/base_link";
    m.header.stamp=stamp(sim_);m.pose.pose.orientation.w=1;C36AppliedBoundaryAccess::odom(*node_,m);
  }
  static size_t count(const std::vector<p1::Json> &rows,const std::string &type) {
    size_t result=0;for(const auto &row:rows)if(row.value("type","")==type)++result;return result;
  }
  std::filesystem::path folder_,source_;
  p1::shadow::LegacyIdentity id_;std::unique_ptr<Regulator> node_;
  rclcpp::Publisher<Applied>::SharedPtr pub_;int64_t sim_=1000000000;
};

TEST_F(C36AppliedBoundary, StartupOversizeCountsExactlyOnceAndLegalSequenceCannotRecoverReady) {
  const auto before=C36AppliedBoundaryAccess::state(*node_);
  auto bad=pair();bad.control_source=std::string(1048577,'x');
  C36AppliedBoundaryAccess::receive(*node_,bad,info());
  auto rejected=C36AppliedBoundaryAccess::state(*node_);
  EXPECT_EQ(rejected.at("received"),1);EXPECT_EQ(rejected.at("admitted"),0);
  EXPECT_EQ(rejected.at("raw_sequence"),1);
  EXPECT_EQ(rejected.at("ordinal").get<uint64_t>(),before.at("ordinal").get<uint64_t>()+1);
  EXPECT_FALSE(rejected.at("lifecycle_complete").get<bool>());
  EXPECT_FALSE(rejected.at("projection_complete").get<bool>());
  inputs();C36AppliedBoundaryAccess::receive(*node_,pair(1),info());odom();
  C36AppliedBoundaryAccess::receive(*node_,pair(2),info());odom();
  const auto after=C36AppliedBoundaryAccess::state(*node_);
  EXPECT_EQ(after.at("received"),3);EXPECT_EQ(after.at("admitted"),2);EXPECT_EQ(after.at("raw_sequence"),3);
  EXPECT_FALSE(after.at("issued").get<bool>());EXPECT_FALSE(after.at("eligible").get<bool>());
  EXPECT_FALSE(after.at("lifecycle_complete").get<bool>());
  auto rows=C36AppliedBoundaryAccess::rows(*node_,source_);
  ASSERT_EQ(count(rows,"adapter_applied_resource_rejected"),1U);EXPECT_EQ(count(rows,"legacy_ready"),0U);
  for(const auto &row:rows)if(row.value("type","")=="adapter_applied_resource_rejected") {
    EXPECT_EQ(row.at("sequence"),1);EXPECT_EQ(row.at("callback_sequence"),1);
    EXPECT_EQ(row.at("received_count"),1);EXPECT_EQ(row.at("admitted_count"),0);
    EXPECT_EQ(row.at("publisher_gid"),p1_owned::gid_json(pub_->get_gid()));
    EXPECT_FALSE(row.at("full_cdr_serialized").get<bool>());
    EXPECT_FALSE(row.contains("raw_input"));EXPECT_LT(row.dump().size(),2048U);
  }
}

TEST_F(C36AppliedBoundary, ValidActualCallbackStillIssuesReadyAndPostReadyOversizeIsTerminal) {
  inputs();C36AppliedBoundaryAccess::receive(*node_,pair(),info());odom();
  ASSERT_TRUE(C36AppliedBoundaryAccess::state(*node_).at("issued").get<bool>());
  auto bad=pair(2);bad.publish_error=std::string(129,'x');
  C36AppliedBoundaryAccess::receive(*node_,bad,info());
  C36AppliedBoundaryAccess::receive(*node_,pair(2),info());odom();
  const auto after=C36AppliedBoundaryAccess::state(*node_);
  EXPECT_EQ(after.at("received"),3);EXPECT_EQ(after.at("admitted"),1);EXPECT_EQ(after.at("raw_sequence"),3);
  EXPECT_TRUE(after.at("terminal").get<bool>());EXPECT_TRUE(after.at("worker_terminal").get<bool>());
  EXPECT_FALSE(after.at("eligible").get<bool>());
  const auto rows=C36AppliedBoundaryAccess::rows(*node_,source_);
  EXPECT_EQ(count(rows,"legacy_ready"),1U);EXPECT_EQ(count(rows,"legacy_ready_invalidated"),1U);
}

TEST_F(C36AppliedBoundary, ActualNodePredicateAcceptsOnlyCompleteFiniteZeroTail) {
  EXPECT_TRUE(C36AppliedBoundaryAccess::tail(zero_tail()));
  auto m=zero_tail();m.final_n[0]=-0.0;EXPECT_TRUE(C36AppliedBoundaryAccess::tail(m));
}
TEST_F(C36AppliedBoundary, ZeroLabelWithNonzeroCommandsOrNonfiniteCommandsRejected) {
  auto m=zero_tail();m.final_n[0]=1;EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
  m=zero_tail();m.final_n[1]=-.1;EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
  m=zero_tail();m.final_n[0]=std::numeric_limits<double>::quiet_NaN();EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
  m=zero_tail();m.final_n[1]=std::numeric_limits<double>::infinity();EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
}
TEST_F(C36AppliedBoundary, PublishStartedBeforeAuthenticatedRequestCannotBeTail) {
  auto m=zero_tail();m.left_publish_start_steady_ns=999;EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
  m=zero_tail();m.right_publish_start_steady_ns=999;EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
  m=zero_tail();m.left_publish_end_steady_ns=999;EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
  m=zero_tail();m.right_publish_end_steady_ns=999;EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
}
TEST_F(C36AppliedBoundary, PublishEndAfterReceiptOrCrossChannelOrderCannotBeTail) {
  auto m=zero_tail();m.right_publish_end_steady_ns=2001;EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
  m=zero_tail();m.left_publish_end_steady_ns=2001;EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
  m=zero_tail();m.right_publish_start_steady_ns=1299;EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
  m=zero_tail();m.right_publish_end_steady_ns=1399;EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
}
TEST_F(C36AppliedBoundary, OriginalGidAndExitedPidfdAreDistinctRequiredInputs) {
  EXPECT_FALSE(C36AppliedBoundaryAccess::tail(zero_tail(),"owner_process_exited",false));
  EXPECT_FALSE(C36AppliedBoundaryAccess::tail(zero_tail(),"callback_foreign_gid",true));
  EXPECT_FALSE(C36AppliedBoundaryAccess::tail(zero_tail(),"",true));
  EXPECT_FALSE(C36AppliedBoundaryAccess::tail(zero_tail(),"owner_liveness_check_failed",true));
}
TEST_F(C36AppliedBoundary, AuthenticatedRequestAndClosedBusinessAreBothRequired) {
  EXPECT_FALSE(C36AppliedBoundaryAccess::tail(zero_tail(),"owner_process_exited",true,false,true));
  EXPECT_FALSE(C36AppliedBoundaryAccess::tail(zero_tail(),"owner_process_exited",true,true,false));
  EXPECT_FALSE(C36AppliedBoundaryAccess::tail(zero_tail(),"owner_process_exited",true,true,true,0));
  EXPECT_FALSE(C36AppliedBoundaryAccess::tail(zero_tail(),"owner_process_exited",true,true,true,1000,999));
}
TEST_F(C36AppliedBoundary, WindowUsesOriginalAuthenticatedRequestAndIncludesExactTwoSecondBoundary) {
  EXPECT_TRUE(C36AppliedBoundaryAccess::tail(zero_tail(),"owner_process_exited",true,true,true,1000,1100,2000001000LL));
  EXPECT_FALSE(C36AppliedBoundaryAccess::tail(zero_tail(),"owner_process_exited",true,true,true,1000,1100,2000001001LL));
  EXPECT_FALSE(C36AppliedBoundaryAccess::tail(zero_tail(),"owner_process_exited",true,true,true,1000,2001,2000));
}
TEST_F(C36AppliedBoundary, FailedChannelAndWrongControlSourceCannotBeTail) {
  auto m=zero_tail();m.left_publish_success=false;EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
  m=zero_tail();m.right_publish_success=false;EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
  m=zero_tail();m.control_source="nmpc";EXPECT_FALSE(C36AppliedBoundaryAccess::tail(m));
}
