#include <gtest/gtest.h>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>
#define P1_ENQUEUE_BRANCH_TEST
#define main p1_original_program_main
#include P1_REGULATOR_SOURCE
#undef main

// The snapshot and Candidate identity operations are the actual source methods.
// This seam supplies input state without starting control/preparation threads.
class EnqueueBranchAccess {
 public:
  static std::unique_ptr<Regulator> make(const std::string &path){
    stop_requested=false;
    return std::unique_ptr<Regulator>(new Regulator(Regulator::EnqueueTestTag{},path,512));
  }
  static void input(Regulator &r,uint64_t ordinal,double value){
    std::lock_guard<std::mutex> lock(r.mutex_);
    r.mode_="shadow";r.input_commit_ordinal_=ordinal;
    r.state_ << value,value+1,value+2,value+3,value+4,value+5;
    r.odom_seq_=ordinal;r.imu_seq_=ordinal+1;r.mixed_=false;
    auto ref=std::make_shared<usv_mpc::ReferenceInput>();
    ref->path={{{value,0.,0.}},{{value+1,0.,0.}}};
    ref->profile={{{.6,0.,0.,0.}},{{.6,0.,0.,.2}}};
    ref->path_sequence=ordinal*2;ref->profile_sequence=ordinal*2+1;
    ref->path_stamp={7,int(ordinal)};ref->profile_stamp={8,int(ordinal+1)};
    r.ref_=ref;r.path_fingerprint_="path-"+std::to_string(ordinal);
    r.profile_fingerprint_="profile-"+std::to_string(ordinal);
    r.legacy_producer_="producer-"+std::to_string(ordinal);
    r.legacy_run_="run-"+std::to_string(ordinal);
    r.anchor_.n={value+10,value+20};r.anchor_.seq={ordinal,ordinal};
    r.anchor_.time={int64_t(100+ordinal),int64_t(200+ordinal)};
    r.anchor_.known={true,true};
    r.history_.clear();r.history_.push_back({int64_t(ordinal),0,value+10});
    r.history_.push_back({int64_t(ordinal+1),1,value+20});
    r.publication_history_.clear();
    r.publication_history_.push_back({0,ordinal,int64_t(100+ordinal),value+10,true});
    r.publication_history_.push_back({1,ordinal,int64_t(200+ordinal),value+20,true});
  }
  static auto snapshot(Regulator &r,int64_t now){
    std::lock_guard<std::mutex> lock(r.mutex_);return r.snapshot_locked(now);
  }
  static auto final(Regulator &r,int64_t now){
    std::lock_guard<std::mutex> lock(r.mutex_);Regulator::Snapshot out;
    r.capture_final_source_locked(out,now);return out;
  }
  static uint64_t ordinal(Regulator &r){
    std::lock_guard<std::mutex> lock(r.mutex_);return r.input_commit_ordinal_;
  }
  static p1::Json captured(const std::shared_ptr<const p1::Candidate> &candidate,bool ticket){
    return Regulator::captured_candidate_json(candidate,ticket);
  }
  static void close(Regulator &r){r.sink_->close();}
};

class AtomicObservation:public ::testing::Test {
 protected:
  static void SetUpTestSuite(){
    int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);
  }
  static void TearDownTestSuite(){rclcpp::shutdown();}
  void SetUp() override {
    const char *output=std::getenv("P1_BRANCH_TEST_OUTPUT");ASSERT_NE(output,nullptr);
    auto folder=std::filesystem::path(output)/::testing::UnitTest::GetInstance()->current_test_info()->name();
    ASSERT_FALSE(std::filesystem::exists(folder));std::filesystem::create_directories(folder);
    regulator=EnqueueBranchAccess::make((folder/"source.jsonl").string());
  }
  void TearDown() override {if(regulator)EnqueueBranchAccess::close(*regulator);}
  std::unique_ptr<Regulator> regulator;
};

TEST_F(AtomicObservation,ValidationAndFinalCannotBeBackfilledFromLaterMembers){
  EnqueueBranchAccess::input(*regulator,4,1.);
  auto validation=EnqueueBranchAccess::snapshot(*regulator,100);
  EnqueueBranchAccess::input(*regulator,8,9.);
  auto final=EnqueueBranchAccess::final(*regulator,200);
  EnqueueBranchAccess::input(*regulator,12,17.);
  auto observed=p1::d0::json(validation,final,110,p1::d0::Observation{},false,0,0,0);
  EXPECT_EQ(observed["schema"],"p1-d0-observation-v2");
  const auto &v=observed["validation_snapshot"],&f=observed["final_snapshot"];
  EXPECT_EQ(v["state"][0],1.);EXPECT_EQ(f["state"][0],9.);
  EXPECT_EQ(v["ref_selection"]["path_sequence"],8);EXPECT_EQ(f["ref_selection"]["path_sequence"],16);
  EXPECT_EQ(v["ref_selection"]["profile_sequence"],9);EXPECT_EQ(f["ref_selection"]["profile_sequence"],17);
  EXPECT_EQ(v["ref_selection"]["path_fingerprint"],"path-4");
  EXPECT_EQ(f["ref_selection"]["profile_fingerprint"],"profile-8");
  EXPECT_EQ(v["ref_selection"]["path_stamp"]["sec"],7);
  EXPECT_EQ(f["ref_selection"]["profile_stamp"]["nanosec"],9);
  EXPECT_EQ(v["anchor"]["sequence"][0],4);EXPECT_EQ(f["anchor"]["sequence"][0],8);
  EXPECT_EQ(v["anchor_producer"],"producer-4");EXPECT_EQ(f["anchor_run_id"],"run-8");
  EXPECT_EQ(f["anchor_source"],"legacy_publisher");
  EXPECT_EQ(v["held_history"][0]["value"],11.);EXPECT_EQ(f["held_history"][0]["value"],19.);
  EXPECT_EQ(v["publication_history"][1]["sequence"],4);
  EXPECT_EQ(f["publication_history"][1]["n"],29.);
  EXPECT_EQ(v["history_count"],2);EXPECT_EQ(f["publication_history_count"],2);
  EXPECT_EQ(v["input_commit_ordinal"],4);EXPECT_EQ(f["input_commit_ordinal"],8);
  EXPECT_EQ(v["sample_ns"],100);EXPECT_EQ(v["copy_capture_ns"],110);EXPECT_EQ(f["commit_ns"],200);
}

TEST_F(AtomicObservation,SnapshotCopiesCurrentInputOrdinalWithoutIncrement){
  EnqueueBranchAccess::input(*regulator,37,1.);
  auto first=EnqueueBranchAccess::snapshot(*regulator,100);
  auto second=EnqueueBranchAccess::snapshot(*regulator,110);
  auto final=EnqueueBranchAccess::final(*regulator,120);
  EXPECT_EQ(first.input_commit_ordinal,37);EXPECT_EQ(second.input_commit_ordinal,37);
  EXPECT_EQ(final.input_commit_ordinal,37);EXPECT_EQ(EnqueueBranchAccess::ordinal(*regulator),37);
}

TEST_F(AtomicObservation,MissingReferenceAndUnreceivedFingerprintsRemainExplicitUnknown){
  auto snapshot=EnqueueBranchAccess::snapshot(*regulator,100);
  snapshot.ref=std::make_shared<const usv_mpc::ReferenceInput>();
  snapshot.path_fingerprint="later-path";snapshot.profile_fingerprint="later-profile";
  auto selection=p1::d0::source_json(snapshot)["ref_selection"];
  EXPECT_EQ(selection["ref_present"],true);EXPECT_EQ(selection["path_sequence"],0);
  EXPECT_TRUE(selection["path_fingerprint"].is_null());EXPECT_TRUE(selection["profile_fingerprint"].is_null());
  EXPECT_EQ(selection["path_stamp"]["sec"],-1);EXPECT_EQ(selection["profile_stamp"]["nanosec"],-1);
  EXPECT_EQ(selection["path_size"],0);EXPECT_EQ(selection["profile_size"],0);
  snapshot.ref.reset();selection=p1::d0::source_json(snapshot)["ref_selection"];
  EXPECT_EQ(selection["ref_present"],false);
  for(const auto &entry:selection.items())if(entry.key()!="ref_present")EXPECT_TRUE(entry.value().is_null());
}

TEST(AtomicReadTap,UnreadFieldsAreNullAndReadFalseIsBoolean){
  p1::d0::Observation observation;
  auto fields=p1::d0::gate_reads_json(observation);ASSERT_EQ(fields.size(),18);
  for(const auto &entry:fields.items())EXPECT_TRUE(entry.value().is_null());
  int reads=0;auto measurement=[&](){++reads;return true;};
  const bool invalid=p1::d0::tap(observation.early_legacy_enabled,false)&&
    !p1::d0::tap(observation.early_legacy_measurement,measurement());
  EXPECT_FALSE(invalid);EXPECT_EQ(reads,0);fields=p1::d0::gate_reads_json(observation);
  EXPECT_TRUE(fields["early_legacy_enabled"].is_boolean());EXPECT_EQ(fields["early_legacy_enabled"],false);
  EXPECT_TRUE(fields["early_legacy_measurement"].is_null());
}

TEST(AtomicReadTap,RunUsableOperandsKeepOriginalOrderAndShortCircuit){
  struct Case {bool unusable,valid,failed;std::vector<std::string> expected;};
  const std::vector<Case> cases={{true,true,true,{"worker_unusable"}},
    {false,false,true,{"worker_unusable","worker_valid"}},
    {false,true,true,{"worker_unusable","worker_valid","sink_failed"}},
    {false,true,false,{"worker_unusable","worker_valid","sink_failed"}}};
  for(const auto &test:cases){
    p1::d0::Observation observation;std::vector<std::string> reads;
    auto read=[&](const char *name,bool value){reads.emplace_back(name);return value;};
    const bool unusable=p1::d0::tap(observation.commit_worker_unusable,read("worker_unusable",test.unusable))||
      !p1::d0::tap(observation.commit_worker_valid,read("worker_valid",test.valid))||
      p1::d0::tap(observation.commit_sink_failed,read("sink_failed",test.failed));
    EXPECT_EQ(unusable,test.unusable||!test.valid||test.failed);EXPECT_EQ(reads,test.expected);
    EXPECT_EQ(observation.commit_worker_valid.has_value(),!test.unusable);
    EXPECT_EQ(observation.commit_sink_failed.has_value(),!test.unusable&&test.valid);
  }
}

TEST(AtomicReadTap,FinalShutdownSkipsStopRequestedWhenStoppingIsTrue){
  p1::d0::Observation observation;int stop_reads=0;
  auto stop=[&](){++stop_reads;return false;};
  EXPECT_TRUE(p1::d0::tap(observation.final_stopping,true)||
    p1::d0::tap(observation.final_stop_requested,stop()));
  EXPECT_EQ(stop_reads,0);EXPECT_FALSE(observation.final_stop_requested.has_value());
  observation=p1::d0::Observation{};
  EXPECT_FALSE(p1::d0::tap(observation.final_stopping,false)||
    p1::d0::tap(observation.final_stop_requested,stop()));
  EXPECT_EQ(stop_reads,1);EXPECT_EQ(p1::d0::gate_reads_json(observation)["final_stop_requested"],false);
}

TEST(AtomicReadTap,InputComparisonSkipsLaterOperandsAndPreservesFalse){
  for(int mismatch=0;mismatch<4;++mismatch){
    p1::d0::Observation observation;int reads=0;
    auto compare=[&](int position){++reads;return position!=mismatch;};
    const bool same=p1::d0::tap(observation.input_version_equal,compare(0))&&
      p1::d0::tap(observation.input_odom_equal,compare(1))&&
      p1::d0::tap(observation.input_imu_equal,compare(2));
    EXPECT_EQ(same,mismatch==3);EXPECT_EQ(reads,std::min(mismatch+1,3));
    EXPECT_EQ(observation.input_odom_equal.has_value(),mismatch!=0);
    EXPECT_EQ(observation.input_imu_equal.has_value(),mismatch>1);
  }
}

TEST(AtomicReadTap,FallbackAndFinalAreSeparateActualOccurrences){
  p1::d0::Observation observation;int reads=0;
  auto read=[&](bool value){++reads;return value;};
  EXPECT_FALSE(p1::d0::tap(observation.final_stopping,read(false)));
  const bool invalid=p1::d0::tap(observation.fallback_invalid_stopping,read(true))||
    p1::d0::tap(observation.fallback_invalid_worker_unusable,read(false));
  EXPECT_TRUE(invalid);EXPECT_EQ(reads,2);
  EXPECT_EQ(p1::d0::gate_reads_json(observation)["final_stopping"],false);
  EXPECT_EQ(p1::d0::gate_reads_json(observation)["fallback_invalid_stopping"],true);
  EXPECT_FALSE(observation.fallback_invalid_worker_unusable.has_value());
  const int64_t last_accepted=0;
  const bool hold=last_accepted>0&&!p1::d0::tap(observation.fallback_source_stopping,read(false))&&
    !p1::d0::tap(observation.fallback_source_worker_unusable,read(false));
  EXPECT_FALSE(hold);EXPECT_EQ(reads,2);
  EXPECT_FALSE(observation.fallback_source_stopping.has_value());EXPECT_FALSE(observation.fallback_source_worker_unusable.has_value());
}

TEST(AtomicCapturedCandidate,IdentityComesFromFullCapturedImmutablePayload){
  p1::Candidate source;source.job.job_id=17;source.worker_instance="worker-original";
  source.first_control={1.,2.};source.job.reference[125]=.125;
  source.x_prediction[125]=.25;source.u_prediction[39]=.5;
  auto captured=std::make_shared<const p1::Candidate>(source);
  const auto original=EnqueueBranchAccess::captured(captured,true);
  EXPECT_EQ(original["job_id"],17);EXPECT_EQ(original["worker_instance"],"worker-original");
  EXPECT_EQ(original["first_control"][0],1.);EXPECT_TRUE(original["pair"].get<bool>());
  EXPECT_GT(original["cdr_bytes"].get<size_t>(),0);EXPECT_EQ(original["cdr_sha256"].get<std::string>().size(),64);
  auto assert_changed=[&](const p1::Candidate &changed){
    auto value=EnqueueBranchAccess::captured(std::make_shared<const p1::Candidate>(changed),true);
    EXPECT_NE(value["cdr_sha256"],original["cdr_sha256"]);
    EXPECT_EQ(EnqueueBranchAccess::captured(captured,true),original);
  };
  auto changed=source;changed.first_control[0]=3.;assert_changed(changed);
  changed=source;changed.job.reference[125]=.75;assert_changed(changed);
  changed=source;changed.x_prediction[125]=.75;assert_changed(changed);
  changed=source;changed.u_prediction[39]=.75;assert_changed(changed);
  changed=source;changed.job.frozen_state[5]=-0.0;assert_changed(changed);
}

TEST(AtomicCapturedCandidate,TicketCandidateAndPairPresenceAreIndependent){
  const auto missing=EnqueueBranchAccess::captured({},true);
  EXPECT_EQ(missing["ticket_present"],true);EXPECT_EQ(missing["candidate_present"],false);EXPECT_EQ(missing["pair"],false);
  for(const char *key:{"cdr_bytes","cdr_sha256","job_id","worker_instance","first_control"})EXPECT_TRUE(missing[key].is_null());
  p1::Candidate candidate;candidate.job.job_id=23;
  const auto unpaired=EnqueueBranchAccess::captured(std::make_shared<const p1::Candidate>(candidate),false);
  EXPECT_EQ(unpaired["ticket_present"],false);EXPECT_EQ(unpaired["candidate_present"],true);EXPECT_EQ(unpaired["pair"],false);
  EXPECT_EQ(unpaired["job_id"],23);EXPECT_FALSE(unpaired["cdr_sha256"].is_null());
}
