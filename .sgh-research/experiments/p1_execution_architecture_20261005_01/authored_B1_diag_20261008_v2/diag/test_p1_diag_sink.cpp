#include <gtest/gtest.h>
#include "p1_diag_sink.hpp"
#include <memory>
struct DummyDecision {int n;};
struct DummyPublisher {std::atomic<unsigned> count{0};void publish(const DummyDecision &){++count;}};
using TestSink=p1::DiagSink<DummyDecision,std::shared_ptr<DummyPublisher>>;
static p1::WitnessHeader header(){p1::WitnessHeader h{};p1::witness_text(h.run_id,"sink-test");p1::witness_text(h.boot_id,"5a417cdc-1c7f-4c5c-8186-6d7e9a85ddcb");
  std::string sha(64,'a');p1::witness_text(h.contract_sha256,sha);p1::witness_text(h.source_sha256,sha);p1::witness_text(h.binary_sha256,sha);p1::witness_text(h.worker_binary_sha256,sha);p1::witness_text(h.worker_instance,sha);return h;}
class SinkTest:public testing::Test {protected:
  void SetUp()override{char name[]="/tmp/p1-B1-sink-XXXXXX";const int fd=mkstemp(name);ASSERT_GE(fd,0);::close(fd);path=name;}
  void TearDown()override{unlink(path.c_str());}
  bool await_pause(TestSink &s){const auto end=p1::diag_now()+1000000000;while(p1::diag_now()<end){if(s.pause_active())return true;std::this_thread::sleep_for(std::chrono::milliseconds(1));}return false;}
  std::string path;std::shared_ptr<DummyPublisher> pub=std::make_shared<DummyPublisher>();
};
TEST_F(SinkTest,DefaultOffCannotArmAndRetainsSourceSemantics){p1::Witness w;TestSink s(path,512,pub,&w);
  EXPECT_FALSE(s.arm_pause());
  EXPECT_TRUE(s.add({{"event",1}},DummyDecision{1}));s.close();
  EXPECT_EQ(pub->count,1u);
  EXPECT_FALSE(s.failed());
  EXPECT_EQ(w.summary().phase.published,0u);std::ifstream f(path);std::string line;getline(f,line);
  EXPECT_EQ(nlohmann::json::parse(line).at("event"),1);getline(f,line);
  EXPECT_TRUE(nlohmann::json::parse(line).at("normal_source_complete"));}
TEST(DiagPolicy,ModeFaultAndFiniteBounds){for(auto ms:{-1,5001})EXPECT_THROW((p1::DiagPausePolicy{ms}.validate("no_output",true,true,true)),std::runtime_error);
  EXPECT_NO_THROW((p1::DiagPausePolicy{5000}.validate("no_output",true,true,true)));
  EXPECT_NO_THROW((p1::DiagPausePolicy{}.validate("shadow",false,false,false)));
  EXPECT_THROW((p1::DiagPausePolicy{1}.validate("execute",true,true,true)),std::runtime_error);
  EXPECT_THROW((p1::DiagPausePolicy{1}.validate("no_output",false,true,true)),std::runtime_error);
  EXPECT_THROW((p1::DiagPausePolicy{1}.validate("no_output",true,false,true)),std::runtime_error);
  EXPECT_THROW((p1::DiagPausePolicy{1}.validate("no_output",true,true,false)),std::runtime_error);}
TEST_F(SinkTest,ConstructorAlsoRejectsUnboundedPause){EXPECT_THROW((TestSink(path,512,pub,nullptr,{5001})),std::runtime_error);}
TEST_F(SinkTest,OnceArmAndConcurrentEnqueueDuringFinitePause){p1::Witness w(true,header());TestSink s(path,512,pub,&w,{100});ASSERT_TRUE(s.arm_pause());ASSERT_TRUE(await_pause(s));
  EXPECT_FALSE(s.arm_pause());
  const auto start=p1::diag_now();for(int i=0;i<50;++i)ASSERT_TRUE(s.add({{"i",i}}));
  EXPECT_LT(p1::diag_now()-start,80000000);
  EXPECT_EQ(s.peak_depth(),50u);s.close();w.close_after_join();
  EXPECT_TRUE(w.summary().audit_complete);
  EXPECT_EQ(w.summary().phase.published,3u);
  EXPECT_FALSE(s.failed());}
TEST_F(SinkTest,CloseCancelsLongPauseAndDoesNotWaitFiveSeconds){p1::Witness w(true,header());TestSink s(path,512,pub,&w,{5000});ASSERT_TRUE(s.arm_pause());ASSERT_TRUE(await_pause(s));const auto start=p1::diag_now();s.close();
  EXPECT_LT(p1::diag_now()-start,500000000);w.close_after_join();
  EXPECT_TRUE(w.summary().audit_complete);}
TEST_F(SinkTest,ActualOverflowIsIndependentOfLaterClose){p1::Witness w(true,header());TestSink s(path,2,pub,&w,{100});ASSERT_TRUE(s.arm_pause());ASSERT_TRUE(await_pause(s));
  EXPECT_TRUE(s.add({{"a",1}}));
  EXPECT_TRUE(s.add({{"b",2}}));
  EXPECT_FALSE(s.add({{"c",3}}));
  EXPECT_TRUE(s.failed());
  EXPECT_EQ(s.dropped(),1u);s.close();w.close_after_join();unsigned overflow=0,fail=0;w.for_each_phase_after_join([&](uint64_t,const p1::WitnessPhase&r){overflow+=r.event_code==p1::WitnessPhaseKind::QueueOverflow;fail+=r.event_code==p1::WitnessPhaseKind::SourceFailure;
  EXPECT_EQ(r.candidate_present,p1::WitnessState::Unknown);});
  EXPECT_EQ(overflow,1u);
  EXPECT_EQ(fail,1u);}
TEST_F(SinkTest,ClosingRejectionIsNotCapacityOverflow){p1::Witness w(true,header());TestSink s(path,512,pub,&w);s.close();
  EXPECT_FALSE(s.add({{"late",1}}));w.close_after_join();unsigned overflow=0;w.for_each_phase_after_join([&](uint64_t,const p1::WitnessPhase&r){overflow+=r.event_code==p1::WitnessPhaseKind::QueueOverflow;});
  EXPECT_EQ(overflow,0u);
  EXPECT_EQ(s.dropped(),1u);}
TEST_F(SinkTest,ExistingSourceBytesAreNotTruncated){std::ofstream(path)<<"existing\n";TestSink s(path,512,pub);s.close();std::ifstream f(path);std::string line;getline(f,line);
  EXPECT_EQ(line,"existing");}
