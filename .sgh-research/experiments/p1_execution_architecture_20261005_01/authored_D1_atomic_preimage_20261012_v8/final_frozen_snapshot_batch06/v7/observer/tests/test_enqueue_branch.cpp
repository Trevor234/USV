// Source-linked regression: the included runtime class owns the tested tick tail.
#include <gtest/gtest.h>
#include <filesystem>
#include <future>
#include <chrono>
#include <cstdlib>
#define P1_ENQUEUE_BRANCH_TEST
#define main p1_original_program_main
#include P1_REGULATOR_SOURCE
#undef main

class EnqueueBranchAccess {
 public:
  static std::unique_ptr<Regulator> make(const std::string &path,size_t capacity=512){
    stop_requested=false;return std::unique_ptr<Regulator>(new Regulator(Regulator::EnqueueTestTag{},path,capacity));
  }
  static void populate(Regulator &r,int slots=1,bool pending=true){
    std::lock_guard<std::mutex> l(r.mutex_);
    r.admission_.invalidate();
    const int64_t origin=1000000000;
    p1::Ticket t{};t.id=++r.job_id_;t.target=1;t.origin=origin;t.deadline=origin+p1::DEADLINE;t.target_ns=origin+p1::T;t.version=r.version_;
    if(slots>0){if(!r.admission_.register_ready(t,0,origin,r.version_).empty())throw std::runtime_error("fixture admission");}
    if(slots==2){r.admission_.cutoff(t.deadline+1);t.id=++r.job_id_;t.target=2;if(!r.admission_.register_ready(t,1,origin,r.version_).empty())throw std::runtime_error("fixture second admission");}
    auto c=std::make_shared<p1::Candidate>();c->job.job_id=t.id;r.candidate_=c;
    std::lock_guard<std::mutex> q(r.prep_mutex_);
    if(pending)r.pending_=Regulator::Preparation{Regulator::Snapshot{},0,origin};else r.pending_.reset();
  }
  static void commit_slot(Regulator &r){std::lock_guard<std::mutex> l(r.mutex_);r.admission_.cutoff(1000000000+p1::DEADLINE+1);}
  static p1::Json state(Regulator &r){std::lock_guard<std::mutex> l(r.mutex_);std::lock_guard<std::mutex> q(r.prep_mutex_);return {{"slots",r.admission_.slots()},{"candidate",bool(r.candidate_)},{"pending",bool(r.pending_)},{"stopping",r.stopping_.load()},{"normal",r.normal_complete_.load()},{"sink_failed",r.sink_->failed()}};}
  static void close_sink(Regulator &r){r.sink_->close();}
  static bool failed(Regulator &r){return r.sink_->failed();}
  static bool stopping(Regulator &r){return r.stopping_;}
  static bool finish(Regulator &r,p1::Decision d,int64_t now,int64_t &stop_start){return r.finish_tick(d,now,now,0,stop_start);}
  static void already_invalidated(Regulator &r){std::lock_guard<std::mutex> l(r.mutex_);r.stopping_=true;r.normal_complete_=false;
#ifdef P1_DIAGNOSTIC_TEST
    r.phase_locked(p1::WitnessPhaseKind::StoppingObserved,p1::WitnessObservation::TickStart,p1::monotonic_ns());r.stop_phase_recorded_=true;
#endif
    r.invalidate_locked();
#ifdef P1_DIAGNOSTIC_TEST
    r.phase_locked(p1::WitnessPhaseKind::InvalidationObserved,p1::WitnessObservation::TickStart,p1::monotonic_ns());r.invalidate_phase_recorded_=true;
#endif
  }
  static std::mutex &prep_mutex(Regulator &r){return r.prep_mutex_;}
  static bool business_try(Regulator &r){if(!r.mutex_.try_lock())return false;r.mutex_.unlock();return true;}
#ifdef P1_DIAGNOSTIC_TEST
  static bool pause_fill(Regulator &r){if(!r.sink_->arm_pause())return false;auto until=std::chrono::steady_clock::now()+std::chrono::seconds(1);while(!r.sink_->pause_active()&&std::chrono::steady_clock::now()<until)std::this_thread::yield();return r.sink_->pause_active()&&r.sink_->add({{"type","test_fill"}});}
  static p1::Json witness(Regulator &r,const std::string &path){r.sink_->close();r.witness_->close_after_join();if(!r.witness_->write_terminal(path.c_str()))throw std::runtime_error("test witness write");std::ifstream f(path);p1::Json j;f>>j;return j;}
#endif
};

class EnqueueBranch:public ::testing::Test {
 protected:
  static void SetUpTestSuite(){int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);}
  static void TearDownTestSuite(){rclcpp::shutdown();}
  void SetUp() override {const auto *root=std::getenv("P1_BRANCH_TEST_OUTPUT");ASSERT_NE(root,nullptr);folder=std::filesystem::path(root)/::testing::UnitTest::GetInstance()->current_test_info()->name();ASSERT_FALSE(std::filesystem::exists(folder));std::filesystem::create_directories(folder);r=EnqueueBranchAccess::make((folder/"source.jsonl").string());}
  void clean(){auto s=EnqueueBranchAccess::state(*r);EXPECT_EQ(s["slots"],0);EXPECT_EQ(s["candidate"],false);EXPECT_EQ(s["pending"],false);EXPECT_EQ(s["stopping"],true);EXPECT_EQ(s["normal"],false);EXPECT_EQ(s["sink_failed"],true);}
  void dirty(int n){auto s=EnqueueBranchAccess::state(*r);ASSERT_EQ(s["slots"],n);ASSERT_EQ(s["candidate"],true);ASSERT_EQ(s["pending"],true);ASSERT_EQ(s["stopping"],false);ASSERT_EQ(s["sink_failed"],false);}
  std::filesystem::path folder;std::unique_ptr<Regulator> r;p1::Decision d{};int64_t start=0;const int64_t now=2000000000;
};
TEST_F(EnqueueBranch,FirstFailureZeroExitCleansAllSlots){EnqueueBranchAccess::populate(*r,2);dirty(2);EnqueueBranchAccess::close_sink(*r);ASSERT_FALSE(EnqueueBranchAccess::failed(*r));ASSERT_TRUE(EnqueueBranchAccess::finish(*r,d,now,start));EXPECT_EQ(start,now);clean();}
TEST_F(EnqueueBranch,ReadySlotCleared){EnqueueBranchAccess::populate(*r);dirty(1);EnqueueBranchAccess::close_sink(*r);ASSERT_TRUE(EnqueueBranchAccess::finish(*r,d,now,start));clean();}
TEST_F(EnqueueBranch,CommittedSlotCleared){EnqueueBranchAccess::populate(*r);EnqueueBranchAccess::commit_slot(*r);dirty(1);EnqueueBranchAccess::close_sink(*r);ASSERT_TRUE(EnqueueBranchAccess::finish(*r,d,now,start));clean();}
TEST_F(EnqueueBranch,NonzeroContinuesOnlyUntilExistingGrace){EnqueueBranchAccess::populate(*r);EnqueueBranchAccess::close_sink(*r);d.final_n={1,1};EXPECT_FALSE(EnqueueBranchAccess::finish(*r,d,now,start));clean();EXPECT_TRUE(EnqueueBranchAccess::finish(*r,d,now+1000000000,start));EXPECT_EQ(start,now);clean();}
TEST_F(EnqueueBranch,PriorInvalidationIsIdempotent){EnqueueBranchAccess::populate(*r);EnqueueBranchAccess::already_invalidated(*r);start=now-1;EnqueueBranchAccess::close_sink(*r);ASSERT_TRUE(EnqueueBranchAccess::finish(*r,d,now,start));EXPECT_EQ(start,now-1);clean();}
TEST_F(EnqueueBranch,RepeatedFailureAlwaysClearsNewlySeededSlots){EnqueueBranchAccess::populate(*r);EnqueueBranchAccess::close_sink(*r);ASSERT_TRUE(EnqueueBranchAccess::finish(*r,d,now,start));clean();EnqueueBranchAccess::populate(*r,2);ASSERT_TRUE(EnqueueBranchAccess::finish(*r,d,now+1,start));clean();EXPECT_EQ(start,now);}
TEST_F(EnqueueBranch,SuccessDoesNotStopOrClearSlots){EnqueueBranchAccess::populate(*r,2);dirty(2);EXPECT_FALSE(EnqueueBranchAccess::finish(*r,d,now,start));EXPECT_EQ(start,0);dirty(2);EnqueueBranchAccess::close_sink(*r);EXPECT_FALSE(EnqueueBranchAccess::failed(*r));}
TEST_F(EnqueueBranch,PendingAlreadyPoppedStillClearsOtherSlots){EnqueueBranchAccess::populate(*r,2,false);EnqueueBranchAccess::close_sink(*r);ASSERT_TRUE(EnqueueBranchAccess::finish(*r,d,now,start));clean();}
TEST_F(EnqueueBranch,BusinessGateWaitsForPrepSlotClear){EnqueueBranchAccess::populate(*r);EnqueueBranchAccess::close_sink(*r);std::unique_lock<std::mutex> held(EnqueueBranchAccess::prep_mutex(*r));auto done=std::async(std::launch::async,[&]{return EnqueueBranchAccess::finish(*r,d,now,start);});auto until=std::chrono::steady_clock::now()+std::chrono::seconds(1);while(!EnqueueBranchAccess::stopping(*r)&&std::chrono::steady_clock::now()<until)std::this_thread::yield();EXPECT_TRUE(EnqueueBranchAccess::stopping(*r));EXPECT_FALSE(EnqueueBranchAccess::business_try(*r));held.unlock();ASSERT_EQ(done.wait_for(std::chrono::seconds(1)),std::future_status::ready);EXPECT_TRUE(done.get());clean();}
#ifdef P1_DIAGNOSTIC_TEST
TEST_F(EnqueueBranch,BoundedQueueFirstFailureTakesDecisionEnqueue){r.reset();r=EnqueueBranchAccess::make((folder/"bounded_source.jsonl").string(),1);EnqueueBranchAccess::populate(*r,2);dirty(2);ASSERT_TRUE(EnqueueBranchAccess::pause_fill(*r));ASSERT_FALSE(EnqueueBranchAccess::failed(*r));ASSERT_TRUE(EnqueueBranchAccess::finish(*r,d,now,start));clean();auto w=EnqueueBranchAccess::witness(*r,(folder/"witness.json").string());auto phases=w.at("phase");bool saw_stop=false,saw_invalid=false;for(auto &p:phases){if(p.at("event_code")==5){EXPECT_EQ(p.at("observation_code"),3);EXPECT_EQ(p.at("admission_slots"),2);EXPECT_EQ(p.at("candidate_present"),true);EXPECT_EQ(p.at("pending_present"),true);saw_stop=true;}if(p.at("event_code")==8){EXPECT_TRUE(saw_stop);EXPECT_EQ(p.at("observation_code"),3);EXPECT_EQ(p.at("admission_slots"),0);EXPECT_EQ(p.at("candidate_present"),false);EXPECT_EQ(p.at("pending_present"),false);saw_invalid=true;}}EXPECT_TRUE(saw_stop);EXPECT_TRUE(saw_invalid);}
#else
TEST_F(EnqueueBranch,CapacityRejectFirstFailureCleansBeforeExit){r.reset();r=EnqueueBranchAccess::make((folder/"capacity_source.jsonl").string(),0);EnqueueBranchAccess::populate(*r,2);dirty(2);ASSERT_TRUE(EnqueueBranchAccess::finish(*r,d,now,start));clean();}
#endif
