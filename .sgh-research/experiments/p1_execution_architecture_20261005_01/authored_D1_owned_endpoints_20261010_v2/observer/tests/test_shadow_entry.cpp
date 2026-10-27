// These tests include the real isolated runtime class and call the same policy
// and legacy callback used by production. There is no separately copied model.
#include <gtest/gtest.h>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#define P1_SHADOW_ENTRY_TEST
#define main p1_shadow_program_main
#include P1_REGULATOR_SOURCE
#undef main

using Applied=usv_research_interfaces::msg::AppliedControl;
class ShadowEntryAccess {
 public:
  static std::unique_ptr<Regulator> make(const std::string &path,const p1::shadow::LegacyIdentity &id){stop_requested=false;return std::unique_ptr<Regulator>(new Regulator(Regulator::ShadowTestTag{},path,id));}
  static void apply(Regulator &r,const Applied &m){r.legacy_applied(m);}
  static p1::Json state(Regulator &r){std::lock_guard<std::mutex> l(r.mutex_);std::lock_guard<std::mutex> q(r.prep_mutex_);return {
    {"known",r.anchor_.known},{"n",r.anchor_.n},{"seq",r.anchor_.seq},{"time",r.anchor_.time},{"history",r.history_.size()},
    {"publication",r.publication_history_.size()},{"legacy_sequence",r.legacy_sequence_},{"received",r.legacy_received_},{"admitted",r.legacy_admitted_},
    {"producer",r.legacy_producer_},{"terminal",r.worker_unusable_.load()},{"worker_valid",r.worker_valid_.load()},
    {"normal",r.normal_complete_.load()},{"slots",r.admission_.slots()},{"candidate",bool(r.candidate_)},{"pending",bool(r.pending_)}};}
  static auto anchor(Regulator &r){std::lock_guard<std::mutex> l(r.mutex_);return r.anchor_;}
  static std::string history_reason(Regulator &r,const p1::Anchor &a){std::lock_guard<std::mutex> l(r.mutex_);return p1::publication_history_check(a,r.anchor_,r.publication_history_);}
  static bool predict(Regulator &r,int64_t odom,int64_t target){std::lock_guard<std::mutex> l(r.mutex_);auto s=r.snapshot_locked(p1::monotonic_ns());s.odom_stamp=odom;return r.predict(s,target);}
  static p1::Json failed_prediction_observation(Regulator &r,int64_t odom,int64_t target){std::lock_guard<std::mutex> l(r.mutex_);auto s=r.snapshot_locked(p1::monotonic_ns());s.odom_stamp=odom;auto aligned=s;p1::d0::Observation o;std::array<double,6> state{},goal{};const bool ok=r.predict(aligned,target);if(ok)std::copy(aligned.state.data(),aligned.state.data()+6,state.begin());p1::d0::observe_prediction(o,ok,state,goal);return p1::d0::json(s,s,s.freeze,o,true,1,1,target);}
  static void capacity(Regulator &r,size_t size){std::lock_guard<std::mutex> l(r.mutex_);r.c_["history_capacity"]=size;}
  static void epoch(Regulator &r,uint64_t epoch){std::lock_guard<std::mutex> l(r.mutex_);r.version_.epoch=epoch;}
  static bool arm_pause(Regulator &r){return r.sink_->arm_pause();}
  static void populate(Regulator &r){std::lock_guard<std::mutex> l(r.mutex_);r.worker_valid_=true;
    const int64_t origin=1000000000;p1::Ticket a{};a.id=1;a.target=1;a.origin=origin;a.deadline=origin+p1::DEADLINE;a.target_ns=origin+p1::T;a.version=r.version_;
    if(!r.admission_.register_ready(a,0,origin,r.version_).empty())throw std::runtime_error("fixture ready slot");r.admission_.cutoff(a.deadline+1);
    a.id=2;a.target=2;if(!r.admission_.register_ready(a,1,origin,r.version_).empty())throw std::runtime_error("fixture committed slot");
    r.candidate_=std::make_shared<p1::Candidate>();std::lock_guard<std::mutex> q(r.prep_mutex_);r.pending_=Regulator::Preparation{Regulator::Snapshot{},0,origin};
  }
  static std::vector<p1::Json> rows(Regulator &r,const std::filesystem::path &file){r.sink_->close();std::ifstream f(file);std::vector<p1::Json> rows;std::string line;while(std::getline(f,line))rows.push_back(p1::Json::parse(line));return rows;}
};

class ShadowEntry:public ::testing::Test {
 protected:
  static void SetUpTestSuite(){int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);}
  static void TearDownTestSuite(){rclcpp::shutdown();}
  void SetUp()override{
    const auto *base=std::getenv("P1_BRANCH_TEST_OUTPUT");ASSERT_NE(base,nullptr);
    folder=std::filesystem::path(base)/::testing::UnitTest::GetInstance()->current_test_info()->name();ASSERT_FALSE(std::filesystem::exists(folder));std::filesystem::create_directories(folder);
    id={"p0-contract-v1","legacy-test","legacy-test:1234567","F5_20261005_atomic_freeze_01",std::string(64,'a'),p1::boot_id()+":steady_clock"};
    source=folder/"source.jsonl";r=ShadowEntryAccess::make(source.string(),id);
    std::ofstream identity_file(folder/"identity.cpp");identity_file<<"source-linked identity fixture\n";identity_file.close();
    contract=folder/"contract.json";const auto raw=p1::candidate_baseline().dump();std::ofstream c(contract);c<<raw;c.close();contract_hash=p1::digest(raw);
    policy={"shadow","shadow-test",p1::boot_id(),(folder/"runtime_source.jsonl").string(),(folder/"runtime_witness.json").string(),
      (folder/"identity.cpp").string(),std::string(64,'b'),std::string(64,'c'),std::string(64,'d'),std::string(64,'e'),getpid(),true,{},id};
    first_ns=p1::monotonic_ns()-100000000;ASSERT_GT(first_ns,0);
  }
  Applied event(uint64_t sequence=1)const{
    Applied m;m.schema_version=id.schema;m.run_id=id.run;m.producer_instance_id=id.producer;m.baseline_id=id.baseline;m.config_hash=id.config;m.steady_clock_domain=id.domain;
    m.sequence=sequence;m.event_semantics="publisher_command";m.map_scale=1;m.lower_n=-25;m.upper_n=25;m.final_n={1,2};m.requested_known=true;m.requested_n=m.final_n;
    m.clock_epoch=0;m.left_clock_epoch=0;m.right_clock_epoch=0;m.sim_time_ns=static_cast<int64_t>(sequence)*1000000;m.left_sim_time_ns=m.sim_time_ns;m.right_sim_time_ns=m.sim_time_ns;
    m.left_publish_success=true;m.right_publish_success=true;m.left_publish_start_steady_ns=first_ns+static_cast<int64_t>(sequence)*1000;m.left_publish_end_steady_ns=m.left_publish_start_steady_ns+10;
    m.right_publish_start_steady_ns=m.left_publish_end_steady_ns+10;m.right_publish_end_steady_ns=m.right_publish_start_steady_ns+10;
    m.clock_receive_steady_ns=m.left_publish_start_steady_ns-100;m.clock_age_ns=100;m.left_clock_age_ns=100;m.right_clock_age_ns=100;return m;
  }
  rclcpp::NodeOptions options(const p1::shadow::EntryPolicy &p)const{
    std::vector<rclcpp::Parameter> values={
      {"run_id",p.run},{"mode",p.mode},{"contract_file",contract.string()},{"contract_hash",contract_hash},
      {"worker_pid",p.worker_pid},{"witness_enabled",p.witness_enabled},{"source_file",p.source_file},{"witness_file",p.witness_file},
      {"diagnostic_source_file",p.identity_source_file},{"diagnostic_source_sha256",p.source_sha},{"diagnostic_binary_sha256",p.binary_sha},
      {"worker_binary_sha256",p.worker_sha},{"witness_worker_instance",p.worker_instance},{"legacy_run_id",p.legacy.run},
      {"legacy_schema_version",p.legacy.schema},{"legacy_producer_instance_id",p.legacy.producer},{"legacy_config_hash",p.legacy.config},{"legacy_clock_domain",p.legacy.domain},
      {"test_delay_ms",p.hooks[0]},{"test_native_block_ms",p.hooks[1]},{"test_prepare_block_ms",p.hooks[2]},{"test_tick_block_ms",p.hooks[3]},{"test_sink_pause_ms",p.hooks[4]}};
    return rclcpp::NodeOptions().parameter_overrides(values).enable_rosout(false).start_parameter_services(false).start_parameter_event_publisher(false);
  }
  void untouched_outputs(const p1::shadow::EntryPolicy &p){EXPECT_FALSE(std::filesystem::exists(p.source_file));EXPECT_FALSE(std::filesystem::exists(p.witness_file));}
  template<class Operation>void rejects_as(Operation operation,const std::string &expected){try{operation();FAIL()<<"expected exact rejection: "<<expected;}catch(const std::exception &e){EXPECT_EQ(std::string(e.what()),expected);}catch(...){FAIL()<<"non-standard exception";}}
  void rejected_whole_pair(const Applied &m){const auto before=ShadowEntryAccess::state(*r);ShadowEntryAccess::apply(*r,m);const auto after=ShadowEntryAccess::state(*r);EXPECT_EQ(after["admitted"],before["admitted"]);EXPECT_EQ(after["known"],(std::array<bool,2>{false,false}));EXPECT_EQ(after["history"],0);EXPECT_EQ(after["publication"],0);EXPECT_EQ(after["slots"],0);}
  std::filesystem::path folder,source,contract;std::string contract_hash;p1::shadow::LegacyIdentity id;p1::shadow::EntryPolicy policy;std::unique_ptr<Regulator> r;int64_t first_ns=0;
};

TEST_F(ShadowEntry,ActualConstructorRejectsExecuteNoOutputAndUnknownBeforeFiles){const std::string reason="shadow entry: only explicitly declared shadow mode is supported";for(const auto *mode:{"execute","no_output","","unknown"}){auto p=policy;p.mode=mode;rejects_as([&]{Regulator rejected(options(p));},reason);untouched_outputs(p);}auto opts=options(policy);auto values=opts.parameter_overrides();values.erase(std::remove_if(values.begin(),values.end(),[](const auto &p){return p.get_name()=="mode";}),values.end());opts.parameter_overrides(values);rejects_as([&]{Regulator rejected(opts);},reason);untouched_outputs(policy);}
TEST_F(ShadowEntry,CompleteDiag5CapabilityFlagAndZeroPolicyRemainCompatible){
  EXPECT_NO_THROW(policy.validate());
  EXPECT_NO_THROW(p1::require_runtime_contract_mode(p1::candidate_baseline(),"shadow"));
  EXPECT_TRUE(p1::candidate_baseline()["fault_injection_enabled"].get<bool>());
}
TEST_F(ShadowEntry,EachOfFiveNonzeroHooksIsRejectedByActualConstructor){const std::array<std::string,5> names={"test_delay_ms","test_native_block_ms","test_prepare_block_ms","test_tick_block_ms","test_sink_pause_ms"};for(size_t i=0;i<5;++i){for(int64_t value:{int64_t(-1),int64_t(1)}){auto p=policy;p.hooks[i]=value;rejects_as([&]{Regulator rejected(options(p));},"shadow entry: every delay/native/prepare/tick/logger hook must be exactly zero");untouched_outputs(p);}auto opts=options(policy);auto values=opts.parameter_overrides();for(auto &value:values)if(value.get_name()==names[i])value=rclcpp::Parameter(names[i],std::string("0"));opts.parameter_overrides(values);try{Regulator rejected(opts);FAIL()<<"wrong parameter type accepted";}catch(const rclcpp::exceptions::InvalidParameterTypeException &e){const std::string reason=e.what();EXPECT_NE(reason.find(names[i]),std::string::npos);EXPECT_NE(reason.find("type"),std::string::npos);}catch(const std::exception &e){FAIL()<<"wrong rejection boundary: "<<e.what();}untouched_outputs(policy);}}
TEST_F(ShadowEntry,WitnessDisabledRejectedByActualConstructor){auto p=policy;p.witness_enabled=false;rejects_as([&]{Regulator rejected(options(p));},"shadow entry: Witness is mandatory");untouched_outputs(p);}
TEST_F(ShadowEntry,IncompleteWitnessIdentityCannotOpenSource){for(size_t i=0;i<5;++i){auto p=policy;if(i==0)p.source_sha.clear();if(i==1)p.binary_sha="bad";if(i==2)p.worker_sha=std::string(64,'g');if(i==3)p.worker_instance.clear();if(i==4)p.worker_pid=0;rejects_as([&]{Regulator rejected(options(p));},i==4?"shadow entry: worker PID required":"shadow entry: complete bounded source/binary/worker Witness identity required");untouched_outputs(p);}rejects_as([&]{Regulator rejected(options(policy));},"witness identity digest mismatch");untouched_outputs(policy);}
TEST_F(ShadowEntry,FreshPathsAreMandatoryAndMustNotAliasIdentity){auto p=policy;p.witness_file=p.source_file;rejects_as([&]{p.validate();},"shadow entry: source/Witness/identity paths must be distinct");p=policy;p.source_file=p.identity_source_file;rejects_as([&]{p.validate();},"shadow entry: source/Witness/identity paths must be distinct");p=policy;std::ofstream exists(p.source_file);exists<<"existing evidence\n";exists.close();rejects_as([&]{p.validate();},"shadow entry: source/Witness output must be fresh create-only paths");p=policy;p.source_file=(folder/"relative_missing"/"file").string();rejects_as([&]{p.validate();},"shadow entry: owned output parent must already exist");}
TEST_F(ShadowEntry,LegacyPinMustBeCompleteAndCanonicalForThisBoot){const std::array<std::string,6> reasons={"nonempty bounded legacy run/producer required","nonempty bounded legacy run/producer required","legacy config SHA256 required","unsupported legacy schema","frozen F5 legacy baseline required","legacy clock domain must equal this boot steady_clock domain"};for(size_t i=0;i<6;++i){auto p=policy;if(i==0)p.legacy.run.clear();if(i==1)p.legacy.producer.clear();if(i==2)p.legacy.config.clear();if(i==3)p.legacy.schema="unknown";if(i==4)p.legacy.baseline="old";if(i==5)p.legacy.domain="prefix"+p.boot+":steady_clock";if(i==4)rejects_as([&]{p.validate();},"shadow entry: "+reasons[i]);else rejects_as([&]{Regulator rejected(options(p));},"shadow entry: "+reasons[i]);untouched_outputs(p);}}
TEST_F(ShadowEntry,ZeroLoggerPolicyCannotBeArmed){EXPECT_FALSE(ShadowEntryAccess::arm_pause(*r));EXPECT_EQ(ShadowEntryAccess::state(*r)["known"],(std::array<bool,2>{false,false}));}

TEST_F(ShadowEntry,ExactLegacyPairAdmitsBothRealChannels){const auto m=event();ShadowEntryAccess::apply(*r,m);const auto s=ShadowEntryAccess::state(*r);EXPECT_EQ(s["known"],(std::array<bool,2>{true,true}));EXPECT_EQ(s["n"],m.final_n);EXPECT_EQ(s["seq"],(std::array<uint64_t,2>{1,1}));EXPECT_EQ(s["history"],2);EXPECT_EQ(s["publication"],2);EXPECT_EQ(s["producer"],id.producer);EXPECT_EQ(s["admitted"],1);}
TEST_F(ShadowEntry,ForeignRunAndEmptyProducerDoNotSelfLearn){auto m=event();m.run_id="foreign";ShadowEntryAccess::apply(*r,m);m=event();m.producer_instance_id.clear();ShadowEntryAccess::apply(*r,m);const auto s=ShadowEntryAccess::state(*r);EXPECT_EQ(s["admitted"],0);EXPECT_EQ(s["producer"],"");EXPECT_EQ(s["known"],(std::array<bool,2>{false,false}));EXPECT_EQ(s["history"],0);}
TEST_F(ShadowEntry,SchemaConfigAndDomainRequireExactIdentity){for(size_t i=0;i<3;++i){auto m=event();if(i==0)m.schema_version="wrong";if(i==1)m.config_hash=std::string(64,'b');if(i==2)m.steady_clock_domain="prefix"+id.domain;ShadowEntryAccess::apply(*r,m);}EXPECT_EQ(ShadowEntryAccess::state(*r)["admitted"],0);EXPECT_EQ(ShadowEntryAccess::state(*r)["history"],0);}
TEST_F(ShadowEntry,RejectionEvidenceTruncatesEveryUntrustedString){auto m=event();m.run_id=std::string(4096,'r');m.producer_instance_id=std::string(4096,'p');m.config_hash=std::string(4096,'c');m.schema_version=std::string(4096,'s');m.baseline_id=std::string(4096,'b');m.steady_clock_domain=std::string(4096,'d');m.event_semantics=std::string(4096,'e');ShadowEntryAccess::apply(*r,m);const auto rows=ShadowEntryAccess::rows(*r,source);ASSERT_GE(rows.size(),2);const auto &observed=rows[0]["observed_identity"];ASSERT_EQ(rows[0]["type"],"legacy_admission_rejected");for(auto it=observed.begin();it!=observed.end();++it){EXPECT_EQ(it.value()["value"].get<std::string>().size(),128);EXPECT_EQ(it.value()["observed_bytes"],4096);EXPECT_EQ(it.value()["truncated"],true);}}
TEST_F(ShadowEntry,ProducerSwitchUsesUniformTerminalAndPreservesBeforeEvidence){ShadowEntryAccess::apply(*r,event());ShadowEntryAccess::populate(*r);auto m=event(2);m.producer_instance_id="legacy-test:changed";ShadowEntryAccess::apply(*r,m);const auto s=ShadowEntryAccess::state(*r);EXPECT_EQ(s["terminal"],true);EXPECT_EQ(s["normal"],false);EXPECT_EQ(s["worker_valid"],false);EXPECT_EQ(s["slots"],0);EXPECT_EQ(s["candidate"],false);EXPECT_EQ(s["pending"],false);EXPECT_EQ(s["history"],0);ShadowEntryAccess::apply(*r,event(3));EXPECT_EQ(ShadowEntryAccess::state(*r)["admitted"],1);const auto rows=ShadowEntryAccess::rows(*r,source);bool transition=false;for(const auto &row:rows)if(row["type"]=="worker_unusable_transition"){transition=true;EXPECT_EQ(row["reason"],"legacy_producer_changed");EXPECT_EQ(row["candidate_before"],true);EXPECT_EQ(row["pending_before"],true);}EXPECT_TRUE(transition);}
TEST_F(ShadowEntry,MissingAndOneSidedHistoryNeverCreateSyntheticPrediction){EXPECT_FALSE(ShadowEntryAccess::predict(*r,1000000,2000000));auto m=event();m.right_publish_success=false;rejected_whole_pair(m);EXPECT_FALSE(ShadowEntryAccess::predict(*r,1000000,2000000));const auto o=ShadowEntryAccess::failed_prediction_observation(*r,1000000,2000000);EXPECT_EQ(o["schema"],"p1-d0-observation-v1");EXPECT_EQ(o["predict_status"],"history_or_time_failed");EXPECT_TRUE(o["predicted_state"].is_null());EXPECT_TRUE(o["full_error"].is_null());}
TEST_F(ShadowEntry,BothChannelsMustCoverAcceptedOdometryStamp){const auto m=event();ShadowEntryAccess::apply(*r,m);EXPECT_FALSE(ShadowEntryAccess::predict(*r,m.left_sim_time_ns-1,m.left_sim_time_ns+1000000));EXPECT_TRUE(ShadowEntryAccess::predict(*r,m.left_sim_time_ns,m.left_sim_time_ns+1000000));}
TEST_F(ShadowEntry,DuplicateAndOldSequenceCannotRewriteHistory){ShadowEntryAccess::apply(*r,event());const auto before=ShadowEntryAccess::state(*r);auto m=event();m.final_n={9,9};ShadowEntryAccess::apply(*r,m);m=event();m.sequence=0;ShadowEntryAccess::apply(*r,m);const auto after=ShadowEntryAccess::state(*r);EXPECT_EQ(after["n"],before["n"]);EXPECT_EQ(after["history"],before["history"]);EXPECT_EQ(after["admitted"],1);EXPECT_EQ(after["received"],3);}
TEST_F(ShadowEntry,SequenceGapInvalidatesSlotsAndStartsOnlyObservedPair){ShadowEntryAccess::apply(*r,event());ShadowEntryAccess::populate(*r);ShadowEntryAccess::apply(*r,event(3));const auto s=ShadowEntryAccess::state(*r);EXPECT_EQ(s["slots"],0);EXPECT_EQ(s["candidate"],false);EXPECT_EQ(s["pending"],false);EXPECT_EQ(s["history"],2);EXPECT_EQ(s["publication"],2);EXPECT_EQ(s["legacy_sequence"],3);}
TEST_F(ShadowEntry,TopAndBothChannelEpochsMustMatch){for(size_t i=0;i<3;++i){ShadowEntryAccess::apply(*r,event(static_cast<uint64_t>(i)*2+1));auto m=event(static_cast<uint64_t>(i)*2+2);if(i==0)m.clock_epoch=1;if(i==1)m.left_clock_epoch=1;if(i==2)m.right_clock_epoch=1;rejected_whole_pair(m);}EXPECT_EQ(ShadowEntryAccess::state(*r)["admitted"],3);}
TEST_F(ShadowEntry,PartialPublicationClearsBothChannelsAndPending){ShadowEntryAccess::apply(*r,event());ShadowEntryAccess::populate(*r);auto m=event(2);m.left_publish_success=false;rejected_whole_pair(m);const auto s=ShadowEntryAccess::state(*r);EXPECT_EQ(s["candidate"],false);EXPECT_EQ(s["pending"],false);EXPECT_EQ(s["normal"],false);}
TEST_F(ShadowEntry,FutureNonmonotonicAndCrossChannelPublishTimesAreRejected){for(size_t i=0;i<3;++i){ShadowEntryAccess::apply(*r,event(static_cast<uint64_t>(i)*2+1));auto m=event(static_cast<uint64_t>(i)*2+2);if(i==0)m.right_publish_end_steady_ns=p1::monotonic_ns()+1000000000;if(i==1)m.left_publish_start_steady_ns=first_ns;if(i==2)m.right_publish_start_steady_ns=m.left_publish_start_steady_ns;rejected_whole_pair(m);}}
TEST_F(ShadowEntry,GlobalAndWithinPairSimReversalCannotLeavePartialAnchor){ShadowEntryAccess::apply(*r,event());auto m=event(2);m.sim_time_ns=500000;m.left_sim_time_ns=500000;m.right_sim_time_ns=500000;rejected_whole_pair(m);m=event(3);m.right_sim_time_ns=m.left_sim_time_ns-1;rejected_whole_pair(m);}
TEST_F(ShadowEntry,ConsecutiveSameValueHistoryPassesButChangeThenReturnFails){ShadowEntryAccess::apply(*r,event());const auto frozen=ShadowEntryAccess::anchor(*r);ShadowEntryAccess::apply(*r,event(2));EXPECT_EQ(ShadowEntryAccess::history_reason(*r,frozen),"");auto m=event(3);m.final_n[0]=3;ShadowEntryAccess::apply(*r,m);ShadowEntryAccess::apply(*r,event(4));EXPECT_EQ(ShadowEntryAccess::history_reason(*r,frozen),"anchor_history_changed");}
TEST_F(ShadowEntry,CapacityEvictionCannotInventFrozenHistoryEndpoint){ShadowEntryAccess::capacity(*r,4);ShadowEntryAccess::apply(*r,event());const auto frozen=ShadowEntryAccess::anchor(*r);ShadowEntryAccess::apply(*r,event(2));ShadowEntryAccess::apply(*r,event(3));EXPECT_EQ(ShadowEntryAccess::history_reason(*r,frozen),"anchor_history_incomplete");EXPECT_FALSE(ShadowEntryAccess::predict(*r,1000000,2000000));EXPECT_EQ(ShadowEntryAccess::state(*r)["history"],4);}
