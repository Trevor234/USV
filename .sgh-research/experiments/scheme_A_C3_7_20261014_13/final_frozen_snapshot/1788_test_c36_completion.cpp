// SPDX-License-Identifier: MIT
// Source-including tests of the actual Candidate callback's final completion
// boundary. All preconditions are finite typed fixtures; no solver, publisher
// owner or plant claim follows from these seeded inputs. The completion seam
// exists only in this test translation unit, never in the runtime target.
#include <gtest/gtest.h>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#define P1_SHADOW_ENTRY_TEST
#define P1_LEGACY_READY_TEST
#define P1_C36_COMPLETION_TEST
#define main p1_c36_completion_program_main
#include P1_REGULATOR_SOURCE
#undef main

class C36CompletionAccess {
 public:
  static std::unique_ptr<Regulator> make(const std::string& file) {
    stop_requested=false;
    p1::shadow::LegacyIdentity legacy{"p0-contract-v1","completion-publisher",
      "completion-producer","F5_20261005_atomic_freeze_01",std::string(64,'a'),
      p1::boot_id()+":steady_clock"};
    return std::unique_ptr<Regulator>(new Regulator(Regulator::LegacyReadyTestTag{},file,legacy));
  }
  static p1::Candidate seed(Regulator& r) {
    std::lock_guard<std::mutex> lock(r.mutex_);
    const auto now=p1::monotonic_ns();
    r.version_={1,1,1,1,0};r.current_tick_=0;
    r.worker_instance_=std::string(64,'e');r.worker_valid_=true;
    r.worker_unusable_=false;r.stopping_=false;
    if(!r.capability_lease_->renew(now))throw std::runtime_error("fixture lease renewal");
    p1::Candidate m;auto& j=m.job;
    j.schema_version="p1-solve-job-v1";j.run_id=r.run_;j.boot_id=r.boot_;
    j.contract_hash=r.hash_;j.nominal_hash=r.nominal_;j.worker_instance=r.worker_instance_;
    j.job_id=1;j.target_tick=1;j.task_generation=1;j.model_generation=1;
    j.config_generation=1;j.schedule_generation=1;j.clock_epoch=0;
    j.tick_origin_steady_ns=now-10000000;j.freeze_steady_ns=now-5000000;
    j.deadline_steady_ns=j.tick_origin_steady_ns+p1::DEADLINE;
    j.target_steady_ns=j.tick_origin_steady_ns+p1::T;
    j.odom_stamp_ns=1000000000;j.target_sim_ns=1200000000;
    j.odom_receive_ns=j.freeze_steady_ns-1000;j.odom_sequence=1;
    j.horizon_steps=20;j.prediction_dt=.2;
    j.target_state={1,2,.1,.2,.3,.4};j.frozen_state=j.target_state;
    j.anchor_n={0,0};j.anchor_sequence={1,1};j.anchor_known={true,true};
    j.anchor_publish_ns={j.tick_origin_steady_ns-1000,j.tick_origin_steady_ns-500};
    j.frozen_clock_sim_ns=1000000000;
    j.frozen_clock_receive_ns=j.freeze_steady_ns-1000;j.assumed_rtf=1;
    j.anchor_source="legacy_publisher";j.anchor_producer="completion-producer";
    j.anchor_run_id="completion-publisher";
    j.history_sim_ns={1000000000,1000000000};j.history_channel={0,1};j.history_n={0,0};
    m.worker_instance=r.worker_instance_;m.worker_receive_ns=j.freeze_steady_ns;
    m.solve_start_ns=j.freeze_steady_ns;m.solve_end_ns=j.freeze_steady_ns;
    m.backend="acados";m.backend_ms=0;
    m.success=true;m.prediction_available=true;m.solver_invoked=true;
    m.first_control={1,2};m.u_prediction[0]=1;m.u_prediction[1]=2;
    std::copy(j.target_state.begin(),j.target_state.end(),m.x_prediction.begin());
    r.jobs_.push_back(j);
    return m;
  }
  static void hook(Regulator& r,std::function<void()> f){r.c36_before_ready_completion_=std::move(f);}
  static void receive(Regulator& r,const p1::Candidate& m){r.candidate(m);}
  static p1::Json state(Regulator& r){std::lock_guard<std::mutex> lock(r.mutex_);return {{"candidate_present",bool(r.candidate_)},{"admission_slots",r.admission_.slots()},{"adapter_present",bool(r.adapter_)}};}
  static p1::Json registration(Regulator& r,const std::filesystem::path& file){
    r.sink_->close();std::ifstream input(file);std::string line;p1::Json result;
    while(std::getline(input,line)){auto row=p1::Json::parse(line);if(row.value("type","")=="candidate_registration")result=std::move(row);}
    return result;
  }
};

class C36Completion:public ::testing::Test {
 protected:
  static void SetUpTestSuite(){int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);}
  static void TearDownTestSuite(){rclcpp::shutdown();}
  void SetUp()override{
    const auto* base=std::getenv("P1_BRANCH_TEST_OUTPUT");ASSERT_NE(base,nullptr);
    const auto folder=std::filesystem::path(base)/(std::string("C36Completion_")+::testing::UnitTest::GetInstance()->current_test_info()->name());
    ASSERT_FALSE(std::filesystem::exists(folder));std::filesystem::create_directories(folder);
    source=folder/"source.jsonl";r=C36CompletionAccess::make(source.string());
    m=C36CompletionAccess::seed(*r);
    ASSERT_EQ(p1::valid_job(m.job,m.job.run_id,m.job.boot_id,m.job.contract_hash,m.job.nominal_hash,m.worker_instance),"");
    ASSERT_FALSE(C36CompletionAccess::state(*r)["adapter_present"].get<bool>());
  }
  std::filesystem::path source;std::unique_ptr<Regulator> r;p1::Candidate m;
};

TEST_F(C36Completion,NoDelayBeforeFinalCompletionRegistersActualCallback){
  C36CompletionAccess::receive(*r,m);
  auto state=C36CompletionAccess::state(*r);EXPECT_TRUE(state["candidate_present"].get<bool>());EXPECT_EQ(state["admission_slots"],1);
  const auto row=C36CompletionAccess::registration(*r,source);ASSERT_TRUE(row.is_object());
  EXPECT_TRUE(row["accepted_registration"].get<bool>());EXPECT_EQ(row["reason"],"");
  EXPECT_LE(row["ready_commit_ns"].get<int64_t>(),m.job.deadline_steady_ns);
}
TEST_F(C36Completion,ActualCompletionAcrossDeadlineRejectsAndClearsBothSlots){
  C36CompletionAccess::hook(*r,[deadline=m.job.deadline_steady_ns]{p1::sleep_until_monotonic(deadline+1000000);});
  C36CompletionAccess::receive(*r,m);
  auto state=C36CompletionAccess::state(*r);EXPECT_FALSE(state["candidate_present"].get<bool>());EXPECT_EQ(state["admission_slots"],0);
  const auto row=C36CompletionAccess::registration(*r,source);ASSERT_TRUE(row.is_object());
  EXPECT_FALSE(row["accepted_registration"].get<bool>());EXPECT_EQ(row["reason"],"late_registration_completion");
  EXPECT_GT(row["ready_commit_ns"].get<int64_t>(),m.job.deadline_steady_ns);
}
TEST_F(C36Completion,StopAtFinalCompletionRejectsAndClearsBothSlots){
  C36CompletionAccess::hook(*r,[]{stop_requested=true;});
  C36CompletionAccess::receive(*r,m);
  auto state=C36CompletionAccess::state(*r);EXPECT_FALSE(state["candidate_present"].get<bool>());EXPECT_EQ(state["admission_slots"],0);
  const auto row=C36CompletionAccess::registration(*r,source);ASSERT_TRUE(row.is_object());
  EXPECT_FALSE(row["accepted_registration"].get<bool>());EXPECT_EQ(row["reason"],"run_unusable_at_ready_completion");
}
