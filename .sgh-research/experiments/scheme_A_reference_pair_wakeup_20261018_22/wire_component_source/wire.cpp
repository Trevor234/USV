// SPDX-License-Identifier: MIT
// Actual callback, enqueue and prepare_loop source; no copied eligibility rule.
// Changed reference, owner feedback/phase and Job use real DDS MessageInfo.
// Worker, odometry/clock/RTF/readiness are construction premises, not a five-role closure test.
#include <gtest/gtest.h>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#define P1_SHADOW_ENTRY_TEST
#define P1_C33_MATRIX_TEST
#define main original_pair_regulator_main
#include P1_REGULATOR_SOURCE
#undef main
using Applied=usv_research_interfaces::msg::AppliedControl;
class C33MatrixAccess {
 public:
 static std::unique_ptr<Regulator> make(const std::string &file,const p1::shadow::LegacyIdentity &id){
  stop_requested=false;auto r=std::unique_ptr<Regulator>(new Regulator(Regulator::ShadowTestTag{},file,id));
  r->hash_=std::string(64,'a');r->nominal_=r->c_.at("nominal_hash");r->ref_=std::make_shared<const usv_mpc::ReferenceInput>();r->resources_=p1::resource_limits_from_contract(r->c_);
  r->worker_instance_=std::string(64,'e');r->worker_valid_=true;r->expected_worker_pid_=getpid();r->worker_liveness_=std::make_unique<p1::WorkerLiveness>(getpid());r->capability_lease_->renew(p1::monotonic_ns());
  r->limits_.low=r->c_.at("command_min_n");r->limits_.high=r->c_.at("command_max_n");r->limits_.rho=r->c_.at("rho_n_s");r->limits_.hold_ns=r->c_.at("hold_ns");r->limits_.tolerance=r->c_.at("activation_tolerance").get<p1::State>();
  r->preparation_barrier_=std::make_unique<p1::PreparationBarrier>(0,r->mode_,false);
  r->job_pub_=r->create_publisher<p1::Job>("/p1_test/pair_jobs",rclcpp::QoS(1).reliable());return r;
 }
 static void peer(Regulator &r,const c36_owned::PeerPins &pins){
  r.owner_peer_=std::make_unique<c36_owned::OwnedPeer>(pins);auto pp=pins;pp.topic="/p1/controlled_owner_phase";pp.type="std_msgs/msg/String";r.controlled_owner_phase_peer_=std::make_unique<c36_owned::OwnedPeer>(pp);
  auto binding=[](const auto &p,const auto &peer){controlled_phase::PeerBinding b;b.gid=peer.expected_gid().template get<controlled_phase::Gid>();b.pid=p.pid;b.process_start_ticks=p.process_start_ticks;b.manifest_sha256=p.manifest_sha256;b.binary_sha256=p.binary_sha256;b.run_id=p.run_id;b.boot_id=p.boot_id;b.contract_sha256=p.contract_sha256;return b;};
  r.controlled_applied_binding_=binding(pins,*r.owner_peer_);r.controlled_phase_binding_=binding(pp,*r.controlled_owner_phase_peer_);r.controlled_owner_identity_={pins.run_id,pins.boot_id,pins.contract_sha256,pins.producer_instance_id,controlled_phase::baseline};
  r.controlled_phase_state_=std::make_unique<controlled_phase::ObserverPhase>(r.controlled_owner_identity_,r.controlled_applied_binding_,r.controlled_phase_binding_);
  r.adapter_=std::make_unique<c36_runtime::Adapter>(c36::Owner{pins.run_id,pins.boot_id,pins.producer_instance_id,pins.config_hash,0},r.run_,r.hash_,r.nominal_);
 }
 static bool healthy(Regulator &r){const auto now=p1::monotonic_ns();return r.eligible(r.snapshot_locked(now),now).empty()&&r.worker_valid_&&!r.worker_unusable_&&r.legacy_measurement_eligible_;}
 static void seed_ready(Regulator &r){r.capability_lease_->renew(p1::monotonic_ns());r.legacy_readiness_enabled_=true;r.legacy_ready_issued_=true;r.legacy_measurement_eligible_=true;refresh(r);}
 static void refresh(Regulator &r){auto now=p1::monotonic_ns();r.odom_seq_=1;r.odom_receive_=now;r.odom_stamp_=100000000000LL;r.sim_=100000000000LL;r.clock_receive_=now;r.last_clock_advance_=now;r.rtf_=1;r.rtf_valid_=true;r.paused_=false;r.state_=usv_mpc::Vector6d::Zero();}
 static int64_t begin(Regulator &r){refresh(r);controlled_phase::Decision d;d.sequence=1;d.tick=0;d.planned_ns=p1::monotonic_ns()-5000000;d.finished_ns=d.planned_ns+1;d.run_id=r.run_;d.boot_id=r.boot_;d.contract_sha256=r.hash_;auto why=r.controlled_phase_state_->begin(d,p1::monotonic_ns());if(!why.empty())throw std::runtime_error(why);return d.planned_ns;}
 static void path(Regulator &r,const nav_msgs::msg::Path &m,const p1::Json *raw=nullptr){r.path(m,raw);}
 static void profile(Regulator &r,const std_msgs::msg::Float64MultiArray &m,const p1::Json *raw=nullptr){r.profile(m,raw);}
 static void applied(Regulator &r,const Applied &m,const rclcpp::MessageInfo &i){r.receive_applied(m,i);}
 static void phase(Regulator &r,const std_msgs::msg::String &m,const rclcpp::MessageInfo &i){r.receive_controlled_phase(m,i);}
 static size_t job_readers(Regulator &r){return r.job_pub_->get_subscription_count();}
 static uint64_t profile_sequence(Regulator &r){return r.profile_seq_;}
 static uint64_t applied_sequence(Regulator &r){return r.legacy_sequence_;}
 static uint64_t phase_callbacks(Regulator &r){return r.raw_callback_sequences_["/p1/controlled_owner_phase"];}
 static void pending_health(Regulator &r){refresh(r);}
 static bool pending(Regulator &r){std::lock_guard<std::mutex> q(r.prep_mutex_);return bool(r.pending_);}
 static bool epoch(Regulator &r){std::lock_guard<std::mutex> q(r.mutex_);return r.reference_epoch_.active();}
 static size_t jobs(Regulator &r){std::lock_guard<std::mutex> q(r.mutex_);return r.jobs_.size();}
 static void prepare(Regulator &r){r.prep_=std::thread([&r]{r.prepare_loop();});}
 static void finish(Regulator &r){r.prep_stop_=true;r.prep_cv_.notify_all();if(r.prep_.joinable())r.prep_.join();r.sink_->close();}
 static void close(Regulator &r){r.adapter_->request_close(p1::monotonic_ns());}
 static void stale(Regulator &r){r.odom_receive_-=200000000;}
 static void worker_invalid(Regulator &r){r.worker_valid_=false;}
 static void clock_reset(Regulator &r){rosgraph_msgs::msg::Clock m;m.clock.sec=99;r.clock(m);}
 static void rtf_invalid(Regulator &r){r.rtf_valid_=false;}
};
class PairCallbacks:public ::testing::Test {
 protected:
 static void SetUpTestSuite(){int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);}
 static void TearDownTestSuite(){rclcpp::shutdown();}
 void SetUp()override{
  const char *base=std::getenv("P1_PAIR_TEST_OUTPUT");ASSERT_NE(base,nullptr);
#ifdef P1_PAIR_EXPECT_MISSING
  folder=std::filesystem::path(base)/"parent";
#else
  folder=std::filesystem::path(base)/"current";
#endif
  folder/=::testing::UnitTest::GetInstance()->current_test_info()->name();ASSERT_FALSE(std::filesystem::exists(folder));std::filesystem::create_directories(folder);
  id={"p0-contract-v1","pair-test-owner","pair-test-owner:unit",controlled_phase::baseline,std::string(64,'c'),p1::boot_id()+":steady_clock"};
  owner=std::make_shared<rclcpp::Node>("pair_native_owner",rclcpp::NodeOptions().enable_rosout(false).start_parameter_services(false).start_parameter_event_publisher(false));
  ap=owner->create_publisher<Applied>("/research/control/applied",rclcpp::QoS(10));pp=owner->create_publisher<std_msgs::msg::String>("/p1/controlled_owner_phase",rclcpp::QoS(10));
  auto endpoints=p1_owned::Json::array({p1_owned::publisher_endpoint(*ap,"usv_research_interfaces/msg/AppliedControl"),p1_owned::publisher_endpoint(*pp,"std_msgs/msg/String")});
  auto m=p1_owned::role_manifest(*owner,"publisher",id.run,std::string(64,'a'),P1_OWNED_SOURCE_BUNDLE_SHA256,endpoints,{{"producer_instance_id",id.producer},{"config_hash",id.config}});auto path=folder/"native_owner_manifest.json";p1_owned::write_create_only(path.string(),m);
  c36_owned::PeerPins pins;pins.manifest_path=path.string();pins.manifest_sha256=p1_owned::file_sha256(path.string());pins.run_id=id.run;pins.boot_id=p1::boot_id();pins.contract_sha256=std::string(64,'a');pins.producer_instance_id=id.producer;pins.config_hash=id.config;pins.exe=m["exe"];pins.binary_sha256=m["binary_sha256"];pins.source_bundle_sha256=m["source_bundle_sha256"];pins.effective_parameters_sha256=m["effective_parameters_sha256"];pins.pid=getpid();pins.process_start_ticks=m["process_start_ticks"];
  r=C33MatrixAccess::make((folder/"source.jsonl").string(),id);C33MatrixAccess::peer(*r,pins);C33MatrixAccess::path(*r,path_message(100));C33MatrixAccess::profile(*r,profile_message(100));
  path_writer=owner->create_publisher<nav_msgs::msg::Path>("/path/reference",rclcpp::QoS(10));profile_writer=owner->create_publisher<std_msgs::msg::Float64MultiArray>("/path/reference_profile",rclcpp::QoS(10));
  applied_reader=r->create_subscription<Applied>("/research/control/applied",rclcpp::QoS(10),[this](Applied::SharedPtr m,const rclcpp::MessageInfo &i){C33MatrixAccess::applied(*r,*m,i);});
  phase_reader=r->create_subscription<std_msgs::msg::String>("/p1/controlled_owner_phase",rclcpp::QoS(10),[this](std_msgs::msg::String::SharedPtr m,const rclcpp::MessageInfo &i){C33MatrixAccess::phase(*r,*m,i);});
  path_reader=r->create_subscription<nav_msgs::msg::Path>("/path/reference",rclcpp::QoS(10),[this](nav_msgs::msg::Path::SharedPtr m,const rclcpp::MessageInfo &i){auto raw=p1_observation_v4::raw_input(*m,i,"/path/reference","nav_msgs/msg/Path",++path_received);C33MatrixAccess::path(*r,*m,&raw);});
  profile_reader=r->create_subscription<std_msgs::msg::Float64MultiArray>("/path/reference_profile",rclcpp::QoS(10),[this](std_msgs::msg::Float64MultiArray::SharedPtr m,const rclcpp::MessageInfo &i){auto raw=p1_observation_v4::raw_input(*m,i,"/path/reference_profile","std_msgs/msg/Float64MultiArray",++profile_received);C33MatrixAccess::profile(*r,*m,&raw);});
  job_reader=owner->create_subscription<p1::Job>("/p1_test/pair_jobs",rclcpp::QoS(1).reliable(),[this](p1::Job::SharedPtr m,const rclcpp::MessageInfo &i){received_jobs.push_back(p1::job_json(*m));received_job_raw.push_back(p1_observation_v4::raw_input(*m,i,"/p1_test/pair_jobs","usv_research_interfaces/msg/SolveJob",received_jobs.size()));});
  executor.add_node(r->get_node_base_interface());executor.add_node(owner);
  ASSERT_TRUE(spin_until([this]{return ap->get_subscription_count()==1&&pp->get_subscription_count()==1&&path_writer->get_subscription_count()==1&&profile_writer->get_subscription_count()==1&&C33MatrixAccess::job_readers(*r)==1;},3000));
  auto bootstrap=pair();bootstrap.sequence=1;ap->publish(bootstrap);ASSERT_TRUE(spin_until([this]{return C33MatrixAccess::applied_sequence(*r)==1;},500));
  C33MatrixAccess::seed_ready(*r);origin=C33MatrixAccess::begin(*r);ASSERT_TRUE(C33MatrixAccess::healthy(*r));

  std::ofstream note(folder/"fixture_scope.json");note<<p1::Json{{"actual_Regulator_source_included",true},{"actual_path_profile_Applied_phase_enqueue_prepare_functions",true},{"MessageInfo_seeded_from_actual_DataWriter_GID",false},{"actual_DDS_delivery_claimed",true},{"worker_odom_clock_RTF_readiness_explicitly_seeded",true},{"actual_process_manifest_pidfd_checked",true},{"worker_RTF_readiness_explicitly_seeded",true},{"actuator_writers",0},{"stage_qualified",false},{"execute_qualified",false}}.dump(2)<<'\n';
 }
 void TearDown()override{if(r){executor.remove_node(r->get_node_base_interface());executor.remove_node(owner);C33MatrixAccess::finish(*r);}applied_reader.reset();phase_reader.reset();path_reader.reset();profile_reader.reset();job_reader.reset();r.reset();pp.reset();ap.reset();path_writer.reset();profile_writer.reset();owner.reset();}
 static nav_msgs::msg::Path path_message(int second){nav_msgs::msg::Path m;m.header.frame_id="map";m.header.stamp.sec=second;m.poses.resize(201);for(int k=0;k<=200;++k){m.poses[k].pose.position.x=.05*(.2*k);m.poses[k].pose.orientation.w=1;}return m;}
 static std_msgs::msg::Float64MultiArray profile_message(int second){std_msgs::msg::Float64MultiArray m;m.layout.dim.resize(2);m.layout.dim[0].label="stamp_sec:"+std::to_string(second);m.layout.dim[0].size=201;m.layout.dim[0].stride=804;m.layout.dim[1].label="stamp_nanosec:0";m.layout.dim[1].size=4;m.layout.dim[1].stride=4;for(int k=0;k<=200;++k)for(double v:{.05,0.,0.,.2*k})m.data.push_back(v);return m;}
 template<class P>static rclcpp::MessageInfo info(const P &p){rmw_message_info_t m{};m.publisher_gid=p->get_gid();return rclcpp::MessageInfo(m);}
 Applied pair(){Applied m;m.schema_version=id.schema;m.run_id=id.run;m.producer_instance_id=id.producer;m.baseline_id=id.baseline;m.config_hash=id.config;m.steady_clock_domain=id.domain;m.sequence=2;m.event_semantics="publisher_command";m.map_scale=1;m.lower_n=-25;m.upper_n=25;m.final_n={0,0};m.left_publish_success=m.right_publish_success=true;m.sim_time_ns=m.left_sim_time_ns=m.right_sim_time_ns=100000000000LL;m.clock_status="valid";m.control_source="native_callback_fixture";auto now=p1::monotonic_ns();m.left_publish_start_steady_ns=now-1000;m.left_publish_end_steady_ns=now-900;m.right_publish_start_steady_ns=now-800;m.right_publish_end_steady_ns=now-700;m.clock_receive_steady_ns=now-1100;m.clock_age_ns=m.left_clock_age_ns=m.right_clock_age_ns=100;return m;}
 std_msgs::msg::String commitment(const Applied &m){auto now=p1::monotonic_ns();p1::Json p={{"schema","p1-controlled-owner-phase-v1"},{"run_id",id.run},{"boot_id",p1::boot_id()},{"contract_sha256",std::string(64,'a')},{"baseline_id",controlled_phase::baseline},{"producer_instance_id",id.producer},{"decision_sequence",1},{"tick",0},{"planned_ns",origin},{"applied_sequence",m.sequence},{"command_n",m.final_n},{"start_ns",{m.left_publish_start_steady_ns,m.right_publish_start_steady_ns}},{"end_ns",{m.left_publish_end_steady_ns,m.right_publish_end_steady_ns}},{"held_until_ns",origin+200000000},{"emitted_ns",now},{"stage_qualified",false},{"execute_qualified",false}};std_msgs::msg::String out;out.data=p.dump();return out;}
 void applied_then_phase(){a=pair();C33MatrixAccess::applied(*r,a,info(ap));C33MatrixAccess::phase(*r,commitment(a),info(pp));}
 void mismatch(){C33MatrixAccess::profile(*r,profile_message(101));}
 void complete(){C33MatrixAccess::path(*r,path_message(101));}
 void submitted_once(){ASSERT_TRUE(C33MatrixAccess::pending(*r));EXPECT_FALSE(C33MatrixAccess::epoch(*r));C33MatrixAccess::prepare(*r);auto end=p1::monotonic_ns()+300000000;while(!C33MatrixAccess::jobs(*r)&&p1::monotonic_ns()<end)std::this_thread::sleep_for(std::chrono::milliseconds(1));EXPECT_EQ(C33MatrixAccess::jobs(*r),1u);EXPECT_TRUE(C33MatrixAccess::epoch(*r));}
 bool spin_until(std::function<bool()> predicate,int milliseconds){auto until=p1::monotonic_ns()+int64_t(milliseconds)*1000000;while(p1::monotonic_ns()<until){executor.spin_some();if(predicate())return true;std::this_thread::sleep_for(std::chrono::milliseconds(1));}return false;}
 rclcpp::executors::SingleThreadedExecutor executor;
 rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr path_writer;rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr profile_writer;
 rclcpp::Subscription<Applied>::SharedPtr applied_reader;rclcpp::Subscription<std_msgs::msg::String>::SharedPtr phase_reader;rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr path_reader;rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr profile_reader;rclcpp::Subscription<p1::Job>::SharedPtr job_reader;
 uint64_t path_received=0,profile_received=0;std::vector<p1::Json> received_jobs,received_job_raw;
 std::unique_ptr<Regulator> r;std::shared_ptr<rclcpp::Node> owner;rclcpp::Publisher<Applied>::SharedPtr ap;rclcpp::Publisher<std_msgs::msg::String>::SharedPtr pp;std::filesystem::path folder;p1::shadow::LegacyIdentity id;Applied a;int64_t origin=0;
};

TEST_F(PairCallbacks,ActualDDSProfilePhasePathSubmitsExactlyOneJob){
 profile_writer->publish(profile_message(101));ASSERT_TRUE(spin_until([this]{return C33MatrixAccess::profile_sequence(*r)==2;},80));
 a=pair();ap->publish(a);ASSERT_TRUE(spin_until([this]{return C33MatrixAccess::applied_sequence(*r)==2;},40));
 pp->publish(commitment(a));ASSERT_TRUE(spin_until([this]{return C33MatrixAccess::phase_callbacks(*r)==1;},40));
 ASSERT_FALSE(C33MatrixAccess::pending(*r));ASSERT_FALSE(C33MatrixAccess::epoch(*r));
 path_writer->publish(path_message(101));ASSERT_TRUE(spin_until([this]{return C33MatrixAccess::pending(*r);},40));
 submitted_once();ASSERT_TRUE(spin_until([this]{return received_jobs.size()==1;},500));
 EXPECT_EQ(received_jobs[0]["job_id"],1);EXPECT_EQ(received_jobs[0]["target_tick"],1);EXPECT_EQ(received_jobs[0]["reference"].size(),126u);
 p1::Json out={{"schema","p1-real-DDS-reference-pair-wakeup-component-v1"},{"received_Job",received_jobs[0]},{"received_Job_raw_input",received_job_raw[0]},{"actual_DDS_delivery",true},{"actual_path_writer",p1_owned::publisher_endpoint(*path_writer,"nav_msgs/msg/Path")},{"actual_profile_writer",p1_owned::publisher_endpoint(*profile_writer,"std_msgs/msg/Float64MultiArray")},{"positive_reference_completion_retry",true},{"fixture_worker_odom_clock_RTF_readiness_seeded",true},{"actuator_publishers",0},{"stage_qualified",false},{"execute_qualified",false}};
 p1_owned::write_create_only((folder/"actual_wire_result.json").string(),out);
}
