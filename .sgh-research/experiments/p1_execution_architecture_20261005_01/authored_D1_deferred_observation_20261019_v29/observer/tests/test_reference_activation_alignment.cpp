// SPDX-License-Identifier: MIT
// Real selector/callback/activation code. Ticket, RTF, lease and readiness are
// explicit in-process premises, not a standalone owned/physical qualification.
#include <gtest/gtest.h>
#include <filesystem>
#include <fstream>
#define P1_SHADOW_ENTRY_TEST
#define P1_C33_MATRIX_TEST
#define main original_activation_regulator_main
#include P1_REGULATOR_SOURCE
#undef main
constexpr int64_t SIM=100000000000LL;
class C33MatrixAccess {
 public:
 using Snapshot=Regulator::Snapshot;
 static std::unique_ptr<Regulator> make(const std::string &file){
  stop_requested=false;p1::shadow::LegacyIdentity id{"p0-contract-v1","activation-test-owner","activation-test-owner:unit",controlled_phase::baseline,std::string(64,'c'),p1::boot_id()+":steady_clock"};
  auto r=std::unique_ptr<Regulator>(new Regulator(Regulator::ShadowTestTag{},file,id));
  r->ref_=std::make_shared<usv_mpc::ReferenceInput>();auto ref=std::make_shared<usv_mpc::ReferenceInput>();
  for(int k=0;k<3;++k){ref->path.push_back({.01*k,0,0});ref->profile.push_back({.05,0,0,.2*k});}ref->path_stamp=ref->profile_stamp={100,0};r->ref_=ref;
  r->legacy_readiness_enabled_=true;r->legacy_ready_issued_=true;r->legacy_measurement_eligible_=true;
  r->worker_valid_=true;r->expected_worker_pid_=getpid();r->worker_liveness_=std::make_unique<p1::WorkerLiveness>(getpid());r->capability_lease_->renew(p1::monotonic_ns());
  r->limits_.low=-25;r->limits_.high=25;r->limits_.rho=80;r->limits_.hold_ns=600000000;r->limits_.tolerance=r->c_.at("activation_tolerance").get<p1::State>();
  auto now=p1::monotonic_ns();r->clock_receive_=r->last_clock_advance_=now;r->sim_=SIM;r->rtf_=1;r->rtf_valid_=true;
  r->anchor_.known={true,true};r->anchor_.seq={1,1};r->anchor_.time={now-100000000,now-100000000};r->anchor_.n={0,0};
  for(int i=0;i<2;++i){r->history_.push_back({SIM-40000000,i,0});r->ready_history_.push_back({SIM-40000000,i,0,1,now-100000000});r->publication_history_.push_back({i,1,now-100000000,0,true});}
  odom(*r,SIM-20000000);odom(*r,SIM+100000);return r;
 }
 static void odom(Regulator&r,int64_t ns,double velocity=0){nav_msgs::msg::Odometry m;m.header.stamp.sec=ns/1000000000;m.header.stamp.nanosec=ns%1000000000;m.header.frame_id="map";m.child_frame_id="wamv/base_link";m.pose.pose.orientation.w=1;m.twist.twist.linear.x=velocity;r.odom(m);}
 static void imu(Regulator&r,int64_t ns,double value=0){sensor_msgs::msg::Imu m;m.header.stamp.sec=ns/1000000000;m.header.stamp.nanosec=ns%1000000000;m.header.frame_id="wamv/wamv/base_link/imu_sensor";m.angular_velocity.z=value;r.imu(m);}
 static Snapshot snapshot(Regulator&r){return r.snapshot_locked(p1::monotonic_ns());}
 static activation_alignment::Selection select(Regulator&r,const Snapshot&s){return activation_alignment::select(s,SIM,{100000000,100000000,100000000,100000000,20000000},100000000);}
 static void clear(Regulator&r){r.invalidate_locked();}
 static void change_version(Regulator&r){++r.version_.task;r.invalidate_locked();}
 static void one_channel(Regulator&r){r.history_.erase(r.history_.begin());}
 static void stop(Regulator&r){r.stopping_=true;}
 static void clock_future(Regulator&r){r.sim_=SIM+30000000;}
 struct Result{p1::Decision decision;p1::Json trace;};
 static Result activate(Regulator&r,const std::function<void(int)> &hook={},const std::function<void()> &after_publish={}){
  Regulator::ActivationCapture capture;auto s=snapshot(r);auto now=s.freeze;int64_t copied=p1::monotonic_ns();Regulator::Snapshot final;p1::d0::Observation observation;
  p1::Ticket t;t.id=1;t.target=1;t.target_ns=now;t.deadline=now-50000000;t.ready_ns=now-100000000;t.version=s.version;t.anchor=s.anchor;t.prediction={};
  auto candidate=std::make_shared<p1::Candidate>();candidate->job.target_sim_ns=SIM;candidate->job.job_id=1;candidate->first_control={.5,.5};
  std::shared_ptr<const p1::Candidate> cand=candidate;p1::Decision d;d.sequence=1;d.tick=1;d.tick_start_ns=d.tick_planned_ns=now;
  d.task_generation=s.version.task;d.model_generation=s.version.model;d.config_generation=s.version.config;d.schedule_generation=s.version.schedule;d.clock_epoch=s.version.epoch;
  int calls=0;r.c33_before_commit_=[&](uint64_t){if(hook)hook(++calls);};
  r.activate_candidate(d,s,final,copied,observation,t,cand,now,1,capture);
  r.publish(d);const auto returned=p1::monotonic_ns();if(after_publish)after_publish();
  auto trace=Regulator::materialize_activation_trace(capture,returned);return {d,trace};
 }
 static bool lite_equals_full(Regulator&r){auto now=p1::monotonic_ns();return p1::d0::source_json(r.snapshot_source_locked(now))==p1::d0::source_json(r.snapshot_locked(now));}
 static bool predict(Regulator&r,Snapshot&s,int64_t target){return r.predict(s,target);}
 static void finish(Regulator&r){r.sink_->close();}
 static activation_alignment::Frame frame(const p1::Json&j){
  activation_alignment::Frame f;f.state=j.at("state").get<p1::State>();auto v=j.at("version");f.version={v.at("task"),v.at("model"),v.at("config"),v.at("schedule"),v.at("epoch")};
  f.history_generation=j.at("history_generation");f.input_commit_ordinal=j.at("input_commit_ordinal");f.origin_kind=j.at("origin_kind");f.origin_sequence=j.at("origin_sequence");
  f.odom_sequence=j.at("odom_sequence");f.imu_sequence=j.at("imu_sequence");f.odom_stamp_ns=j.at("odom_stamp_ns");f.imu_stamp_ns=j.at("imu_stamp_ns");f.odom_receive_ns=j.at("odom_receive_ns");f.imu_receive_ns=j.at("imu_receive_ns");f.r_from_imu=j.at("r_from_imu");return f;
 }
 static Snapshot historical(const p1::Json&r){
  Snapshot s;const auto &j=r.at("snapshot");auto x=j.at("state").get<p1::State>();std::copy(x.begin(),x.end(),s.state.data());auto v=j.at("version");s.version={v.at("task"),v.at("model"),v.at("config"),v.at("schedule"),v.at("epoch")};
  s.freeze=j.at("sample_ns");s.sim=j.at("clock_sim_ns");s.clock_receive=j.at("clock_receive_ns");s.input_commit_ordinal=j.at("input_commit_ordinal");s.activation_history_generation=r.at("history_generation");
  for(const auto &f:r.at("frames"))s.activation_frames.push_back(frame(f));
  for(const auto&e:j.at("held_history"))s.history.push_back({e.at("sim_ns"),e.at("channel"),e.at("value")});return s;
 }
};
class Activation:public ::testing::Test {
 protected:
 static void SetUpTestSuite(){int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);}
 static void TearDownTestSuite(){rclcpp::shutdown();}
 void SetUp()override{
  const char*base=std::getenv("P1_PAIR_TEST_OUTPUT");ASSERT_NE(base,nullptr);folder=std::filesystem::path(base)/"activation"/::testing::UnitTest::GetInstance()->current_test_info()->name();ASSERT_FALSE(std::filesystem::exists(folder));std::filesystem::create_directories(folder);r=C33MatrixAccess::make((folder/"source.jsonl").string());
  std::ofstream out(folder/"scope.json");out<<p1::Json{{"production_selector_callbacks_and_activation_helper",true},{"ticket_RTF_lease_readiness_seeded",true},{"no_Actuator_DataWriter",true},{"native_timing_or_closed_loop_qualification",false},{"maximum_validation_attempts",2},{"history_capacity",32}}.dump(2)<<'\n';
 }
 void TearDown()override{if(r)C33MatrixAccess::finish(*r);r.reset();}
 void outcome(const C33MatrixAccess::Result&v){std::ofstream f(folder/"outcome.json");f<<p1::Json{{"accepted",v.decision.candidate_accepted},{"reason",v.decision.reason},{"trace",v.trace},{"physical_publish_success",v.decision.publish_success}}.dump(2)<<'\n';}
 std::unique_ptr<Regulator>r;std::filesystem::path folder;
};
TEST_F(Activation,All100HistoricalPrefixesAndIndependentPrediction){
 ASSERT_EQ(file_sha(P1_ACTIVATION_REPLAY_FILE),"1665863947727d618bbba0c41bd10f63bc62efb785e1d5b1a593b441758a7568");std::ifstream in(P1_ACTIVATION_REPLAY_FILE);p1::Json data;in>>data;ASSERT_EQ(data.at("rows").size(),100u);
 for(const auto &row:data.at("rows")){auto s=C33MatrixAccess::historical(row);auto selected=activation_alignment::select(s,row.at("target_sim_ns"),{100000000,100000000,100000000,100000000,20000000},100000000);ASSERT_TRUE(selected.frame);EXPECT_EQ(activation_alignment::json(*selected.frame),row.at("expected_selected_frame"));EXPECT_LE(selected.scanned,32u);activation_alignment::apply(s,*selected.frame);ASSERT_TRUE(C33MatrixAccess::predict(*r,s,row.at("target_sim_ns")));auto expected=row.at("expected_forward_state").get<p1::State>();for(int i=0;i<6;++i)EXPECT_NEAR(s.state[i],expected[i],1e-10);}
}
TEST_F(Activation,FutureLatestUsesOlderCausalOdom){auto selected=C33MatrixAccess::select(*r,C33MatrixAccess::snapshot(*r));ASSERT_TRUE(selected.frame);EXPECT_EQ(selected.frame->odom_sequence,1u);EXPECT_LE(selected.scanned,32u);}
TEST_F(Activation,LatestCausalCommitPreferred){C33MatrixAccess::odom(*r,SIM);auto selected=C33MatrixAccess::select(*r,C33MatrixAccess::snapshot(*r));ASSERT_TRUE(selected.frame);EXPECT_EQ(selected.frame->odom_sequence,3u);}
TEST_F(Activation,FutureImuCannotEnterSelectedState){C33MatrixAccess::imu(*r,SIM+1000000,.02);auto selected=C33MatrixAccess::select(*r,C33MatrixAccess::snapshot(*r));ASSERT_TRUE(selected.frame);EXPECT_FALSE(selected.frame->r_from_imu);EXPECT_EQ(selected.frame->state[5],0);}
TEST_F(Activation,CausalMixedImuRetainsProvenance){C33MatrixAccess::odom(*r,SIM-1000000);C33MatrixAccess::imu(*r,SIM-1000000,.02);auto selected=C33MatrixAccess::select(*r,C33MatrixAccess::snapshot(*r));ASSERT_TRUE(selected.frame);EXPECT_TRUE(selected.frame->r_from_imu);EXPECT_EQ(selected.frame->imu_sequence,1u);EXPECT_EQ(selected.frame->state[5],.02);}
TEST_F(Activation,MissingDualHistoryRejects){C33MatrixAccess::one_channel(*r);auto result=C33MatrixAccess::activate(*r);EXPECT_FALSE(result.decision.candidate_accepted);EXPECT_EQ(result.decision.reason,"activation_no_causal_state");outcome(result);}
TEST_F(Activation,StaleOrFutureReceiptRejects){for(auto delta:{-100000001LL,1LL}){auto s=C33MatrixAccess::snapshot(*r);for(auto&f:s.activation_frames)f.odom_receive_ns=s.freeze+delta;EXPECT_FALSE(C33MatrixAccess::select(*r,s).frame);}}
TEST_F(Activation,ForeignVersionRejects){auto s=C33MatrixAccess::snapshot(*r);++s.version.epoch;EXPECT_FALSE(C33MatrixAccess::select(*r,s).frame);}
TEST_F(Activation,InvalidationClearsAndImuAloneCannotReintroduceOldOdom){auto old=C33MatrixAccess::snapshot(*r).activation_history_generation;C33MatrixAccess::change_version(*r);C33MatrixAccess::imu(*r,SIM);auto s=C33MatrixAccess::snapshot(*r);EXPECT_GT(s.activation_history_generation,old);EXPECT_TRUE(s.activation_frames.empty());C33MatrixAccess::odom(*r,SIM);EXPECT_TRUE(C33MatrixAccess::select(*r,C33MatrixAccess::snapshot(*r)).frame);}
TEST_F(Activation,InvalidOdomDoesNotAppendOrAdvanceAcceptedSequence){auto before=C33MatrixAccess::snapshot(*r);C33MatrixAccess::odom(*r,SIM,NAN);auto after=C33MatrixAccess::snapshot(*r);EXPECT_EQ(after.activation_frames.size(),before.activation_frames.size());EXPECT_EQ(after.odom_seq,before.odom_seq);}
TEST_F(Activation,StorageCapacityIsBounded){for(int i=0;i<80;++i)C33MatrixAccess::odom(*r,SIM-30000000+i*300000);auto s=C33MatrixAccess::snapshot(*r);EXPECT_EQ(s.activation_frames.size(),32u);EXPECT_LE(C33MatrixAccess::select(*r,s).scanned,32u);}
TEST_F(Activation,StableFirstCandidateAcceptedWithoutPhysicalPublish){auto result=C33MatrixAccess::activate(*r);EXPECT_TRUE(result.decision.candidate_accepted)<<result.decision.reason;EXPECT_EQ(result.trace.at("attempts").size(),1u);EXPECT_EQ(result.decision.final_n,(p1::Command{.5,.5}));EXPECT_FALSE(result.decision.publish_success[0]);outcome(result);}
TEST_F(Activation,OneOdomRaceRevalidatesExactlyOnce){auto result=C33MatrixAccess::activate(*r,[&](int n){if(n==1)C33MatrixAccess::odom(*r,SIM+100000);});EXPECT_TRUE(result.decision.candidate_accepted)<<result.decision.reason;EXPECT_EQ(result.trace.at("attempts").size(),2u);EXPECT_EQ(result.trace["attempts"][0]["input_gate_reads"]["input_odom_equal"],false);outcome(result);}
TEST_F(Activation,OneImuRacePreservesOriginalImuSequenceCheck){auto result=C33MatrixAccess::activate(*r,[&](int n){if(n==1)C33MatrixAccess::imu(*r,SIM);});EXPECT_TRUE(result.decision.candidate_accepted)<<result.decision.reason;EXPECT_EQ(result.trace.at("attempts").size(),2u);EXPECT_EQ(result.trace["attempts"][0]["input_gate_reads"]["input_imu_equal"],false);outcome(result);}
TEST_F(Activation,RepeatedRaceRejectsAfterTwoAttempts){auto result=C33MatrixAccess::activate(*r,[&](int){C33MatrixAccess::odom(*r,SIM+100000);});EXPECT_FALSE(result.decision.candidate_accepted);EXPECT_EQ(result.decision.reason,"activation_input_changed_during_validation");EXPECT_EQ(result.trace.at("attempts").size(),2u);outcome(result);}
TEST_F(Activation,VersionRaceDoesNotRetryOrAccept){auto result=C33MatrixAccess::activate(*r,[&](int){C33MatrixAccess::change_version(*r);});EXPECT_FALSE(result.decision.candidate_accepted);EXPECT_EQ(result.trace.at("attempts").size(),1u);outcome(result);}
TEST_F(Activation,ShutdownDuringValidationDoesNotRetryOrAccept){auto result=C33MatrixAccess::activate(*r,[&](int){C33MatrixAccess::stop(*r);});EXPECT_FALSE(result.decision.candidate_accepted);EXPECT_EQ(result.decision.reason,"shutdown");EXPECT_EQ(result.trace.at("attempts").size(),1u);outcome(result);}
TEST_F(Activation,OriginalJitterBudgetCannotBeExtendedForRetry){auto result=C33MatrixAccess::activate(*r,[&](int){C33MatrixAccess::odom(*r,SIM);std::this_thread::sleep_for(std::chrono::milliseconds(22));});EXPECT_FALSE(result.decision.candidate_accepted);EXPECT_EQ(result.trace.at("attempts").size(),1u);outcome(result);}
TEST_F(Activation,CommitRechecksOriginalSourceAge){auto result=C33MatrixAccess::activate(*r,[&](int){std::this_thread::sleep_for(std::chrono::milliseconds(105));});EXPECT_FALSE(result.decision.candidate_accepted);outcome(result);}
TEST_F(Activation,RetryCannotBypassTargetSimSlack){auto result=C33MatrixAccess::activate(*r,[&](int n){if(n==1){C33MatrixAccess::odom(*r,SIM);C33MatrixAccess::clock_future(*r);}});EXPECT_FALSE(result.decision.candidate_accepted);EXPECT_EQ(result.decision.reason,"target_sim_mismatch");EXPECT_EQ(result.trace.at("attempts").size(),2u);outcome(result);}
TEST_F(Activation,LightweightGuardSnapshotPreservesSourceFields){EXPECT_TRUE(C33MatrixAccess::lite_equals_full(*r));}
TEST_F(Activation,ImuOdomBurstBeforeGuardUsesOneCompleteRetry){auto result=C33MatrixAccess::activate(*r,[&](int n){if(n==1){C33MatrixAccess::imu(*r,SIM);C33MatrixAccess::odom(*r,SIM);}});EXPECT_TRUE(result.decision.candidate_accepted)<<result.decision.reason;ASSERT_EQ(result.trace["attempts"].size(),2u);EXPECT_EQ(result.trace["attempts"][0]["input_gate_reads"]["input_odom_equal"],false);outcome(result);}
TEST_F(Activation,ImuThenOdomAcrossAttemptsRetainsOriginalRefusal){auto result=C33MatrixAccess::activate(*r,[&](int n){if(n==1)C33MatrixAccess::imu(*r,SIM);else C33MatrixAccess::odom(*r,SIM);});EXPECT_FALSE(result.decision.candidate_accepted);ASSERT_EQ(result.trace["attempts"].size(),2u);EXPECT_EQ(result.trace["attempts"][0]["input_gate_reads"]["input_imu_equal"],false);EXPECT_EQ(result.trace["attempts"][1]["input_gate_reads"]["input_odom_equal"],false);outcome(result);}
TEST_F(Activation,CapturedTraceSurvivesCallbacksAfterCommitAndPublishReturn){auto result=C33MatrixAccess::activate(*r,{},[&]{C33MatrixAccess::odom(*r,SIM,.01);C33MatrixAccess::imu(*r,SIM,.02);});ASSERT_TRUE(result.decision.candidate_accepted);const auto &a=result.trace["attempts"][0];EXPECT_EQ(a["raw_snapshot"]["odom_sequence"],2);EXPECT_EQ(a["guard_snapshot"]["odom_sequence"],2);EXPECT_EQ(a["selected_frame"]["odom_sequence"],1);EXPECT_EQ(a["raw_snapshot"]["state"][3],0);EXPECT_EQ(C33MatrixAccess::snapshot(*r).odom_seq,3u);EXPECT_GE(result.trace["materialized_start_ns"].get<int64_t>(),result.trace["observer_publish_return_ns"].get<int64_t>());EXPECT_GE(result.trace["observer_publish_return_ns"].get<int64_t>(),result.decision.activation_commit_ns);outcome(result);}
TEST_F(Activation,PostCommitFormattingDelayCannotRewriteOriginalVerdict){auto result=C33MatrixAccess::activate(*r,{},[&]{C33MatrixAccess::odom(*r,SIM,.02);std::this_thread::sleep_for(std::chrono::milliseconds(22));});ASSERT_TRUE(result.decision.candidate_accepted);EXPECT_EQ(result.trace["attempts"][0]["reason"],"");EXPECT_GE(result.trace["materialized_start_ns"].get<int64_t>()-result.decision.activation_commit_ns,22000000);EXPECT_FALSE(result.decision.publish_success[0]);outcome(result);}
