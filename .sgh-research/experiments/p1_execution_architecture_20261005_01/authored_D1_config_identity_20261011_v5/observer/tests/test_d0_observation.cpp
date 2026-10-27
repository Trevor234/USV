#include <gtest/gtest.h>
#include <filesystem>
#include <fstream>
#include <limits>
#include <cstdlib>
#define P1_ENQUEUE_BRANCH_TEST
#define main p1_original_program_main
#include P1_REGULATOR_SOURCE
#undef main

class EnqueueBranchAccess {
 public:
  static std::unique_ptr<Regulator> make(const std::string &path){stop_requested=false;return std::unique_ptr<Regulator>(new Regulator(Regulator::EnqueueTestTag{},path,512));}
  static auto snapshot(Regulator &r,int64_t now){std::lock_guard<std::mutex> l(r.mutex_);return r.snapshot_locked(now);}
  static auto final(Regulator &r,int64_t now){std::lock_guard<std::mutex> l(r.mutex_);Regulator::Snapshot s;r.capture_final_source_locked(s,now);return s;}
  static void input(Regulator &r,bool changed){std::lock_guard<std::mutex> l(r.mutex_);r.state_[0]=changed?9:1;r.odom_seq_=changed?12:11;r.odom_stamp_=21;r.odom_receive_=31;r.imu_seq_=changed?42:41;r.imu_stamp_=51;r.imu_receive_=61;r.mixed_=false;r.version_.task=71;r.sim_=81;r.clock_receive_=91;r.rtf_=1;r.rtf_valid_=true;r.anchor_.known={true,true};r.anchor_.n={2,3};r.history_.push_back({20,0,2});}
  template<class S> static bool predict(Regulator &r,S &s,int64_t target){return r.predict(s,target);}
  static auto canonical(const p1::Decision &d){return Regulator::decision_json(d);}
  static bool finish(Regulator &r,const p1::Decision &d,const p1::Json &o){int64_t start=0;return r.finish_tick(d,100,100,0,start,&o);}
  static void close(Regulator &r){r.sink_->close();}
};
class D0Observation:public ::testing::Test {
 protected:
  static void SetUpTestSuite(){int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);}
  static void TearDownTestSuite(){rclcpp::shutdown();}
  void SetUp() override {const char *p=std::getenv("P1_BRANCH_TEST_OUTPUT");ASSERT_NE(p,nullptr);folder=std::filesystem::path(p)/::testing::UnitTest::GetInstance()->current_test_info()->name();ASSERT_FALSE(std::filesystem::exists(folder));std::filesystem::create_directories(folder);r=EnqueueBranchAccess::make((folder/"source.jsonl").string());}
  std::filesystem::path folder;std::unique_ptr<Regulator> r;
};
TEST_F(D0Observation,ValidationSnapshotCannotBeBackfilledFromFinalMembers){
  EnqueueBranchAccess::input(*r,false);auto s=EnqueueBranchAccess::snapshot(*r,100);EnqueueBranchAccess::input(*r,true);auto f=EnqueueBranchAccess::final(*r,200);
  p1::d0::Observation o;auto j=p1::d0::json(s,f,110,o,false,0,0,0);
  EXPECT_EQ(j["validation_snapshot"]["state"][0],1);EXPECT_EQ(j["validation_snapshot"]["odom_sequence"],11);EXPECT_EQ(j["final_snapshot"]["odom_sequence"],12);
  EXPECT_EQ(j["validation_snapshot"]["history_count"],1);EXPECT_EQ(j["validation_snapshot"]["held_history"][0]["value"],2);
  EXPECT_EQ(j["validation_snapshot"]["sample_ns"],100);EXPECT_EQ(j["validation_snapshot"]["copy_capture_ns"],110);EXPECT_EQ(j["final_snapshot"]["commit_ns"],200);
}
TEST_F(D0Observation,InactiveImuIsRawInObservationAndMaskedInCanonical){
  EnqueueBranchAccess::input(*r,false);auto s=EnqueueBranchAccess::snapshot(*r,100);auto f=EnqueueBranchAccess::final(*r,200);p1::d0::Observation o;auto j=p1::d0::json(s,f,110,o,false,0,0,0);p1::Decision d;
  EXPECT_EQ(j["final_snapshot"]["r_from_imu"],false);EXPECT_EQ(j["final_snapshot"]["imu_sequence"],41);EXPECT_EQ(EnqueueBranchAccess::canonical(d)["activation_imu_sequence"],0);
}
TEST_F(D0Observation,MissingCandidateIsExplicitNullRatherThanZeroSample){auto s=EnqueueBranchAccess::snapshot(*r,100);p1::d0::Observation o;auto j=p1::d0::json(s,s,110,o,false,0,0,0);EXPECT_TRUE(j["predicted_state"].is_null());EXPECT_TRUE(j["full_error"].is_null());EXPECT_TRUE(j["prediction_target_sim_ns"].is_null());EXPECT_EQ(j["predict_invoked"],false);EXPECT_EQ(j["predict_status"],"not_attempted");EXPECT_TRUE(j["input_change_gate_unchanged"].is_null());}
TEST_F(D0Observation,ActualBackwardPropagationFailureCannotProduceZeroSample){EnqueueBranchAccess::input(*r,false);auto s=EnqueueBranchAccess::snapshot(*r,100);auto a=s;p1::d0::Observation o;std::array<double,6> z{};bool ok=EnqueueBranchAccess::predict(*r,a,s.odom_stamp-1);ASSERT_FALSE(ok);p1::d0::observe_prediction(o,ok,z,z);auto j=p1::d0::json(s,s,110,o,true,1,2,20);EXPECT_EQ(j["predict_status"],"history_or_time_failed");EXPECT_TRUE(j["predicted_state"].is_null());EXPECT_TRUE(j["full_error"].is_null());}
TEST_F(D0Observation,CompleteObservationSurvivesOriginalFirstDimensionEarlyExit){std::array<double,6> actual{1,2,.3,4,5,6},target{},partial{};p1::Limits l;l.tolerance={.25,.25,.15,.3,.2,.15};ASSERT_FALSE(p1::state_check(target,actual,l,&partial).empty());EXPECT_EQ(partial[5],0);p1::d0::Observation o;p1::d0::observe_prediction(o,true,actual,target);ASSERT_TRUE(o.full_error_available);EXPECT_EQ(o.full_error[5],6);EXPECT_EQ(o.full_error[1],2);EXPECT_NEAR(o.full_error[2],.3,1e-12);}
TEST_F(D0Observation,HeadingCrossingPiUsesWrappedFullDifference){std::array<double,6> actual{},target{};actual[2]=-3.13;target[2]=3.13;p1::d0::Observation o;p1::d0::observe_prediction(o,true,actual,target);ASSERT_TRUE(o.full_error_available);EXPECT_NEAR(o.full_error[2],2*std::acos(-1)-6.26,1e-12);}
TEST_F(D0Observation,NonfiniteAndSubtractionOverflowHaveExplicitAvailability){std::array<double,6> a{},b{};a[0]=std::numeric_limits<double>::quiet_NaN();p1::d0::Observation o;p1::d0::observe_prediction(o,true,a,b);EXPECT_TRUE(o.predict_success);EXPECT_FALSE(o.predicted_state_available);EXPECT_FALSE(o.full_error_available);a[0]=std::numeric_limits<double>::max();b[0]=-a[0];p1::d0::observe_prediction(o,true,a,b);EXPECT_TRUE(o.predicted_state_available);EXPECT_FALSE(o.full_error_available);}
TEST_F(D0Observation,DecoratedDecisionSharesOneEventAndKeepsCanonicalProjection){auto s=EnqueueBranchAccess::snapshot(*r,100);p1::d0::Observation o;o.input_change_gate_ran=true;o.input_change_gate_unchanged=false;auto j=p1::d0::json(s,s,110,o,false,0,0,0);p1::Decision d;d.reason="activation_input_changed_during_validation";d.final_n={0,0};auto plain=EnqueueBranchAccess::canonical(d);EXPECT_FALSE(EnqueueBranchAccess::finish(*r,d,j));EnqueueBranchAccess::close(*r);std::ifstream in(folder/"source.jsonl");std::string line;size_t decisions=0;while(std::getline(in,line)){auto row=p1::Json::parse(line);if(row.value("type","")=="decision"){++decisions;EXPECT_EQ(row["d0_observation"]["input_change_gate_unchanged"],false);row.erase("d0_observation");EXPECT_EQ(row,plain);}}EXPECT_EQ(decisions,1);}
