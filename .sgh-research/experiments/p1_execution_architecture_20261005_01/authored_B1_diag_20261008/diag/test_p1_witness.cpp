// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include <gtest/gtest.h>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <atomic>
#include <csignal>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <set>
#include <string>
#include <stdexcept>
#include <thread>
#include <vector>
#include <sys/resource.h>
#include <sys/stat.h>
#include "p1_witness.hpp"

namespace {
using Json=nlohmann::json;
p1::WitnessHeader header(std::string run="witness-test") {
  p1::WitnessHeader h{};
  p1::witness_text(h.run_id,run);
  p1::witness_text(h.boot_id,"5a417cdc-1c7f-4c5c-8186-6d7e9a85ddcb");
  p1::witness_text(h.contract_sha256,std::string(64,'a'));
  p1::witness_text(h.source_sha256,std::string(64,'b'));
  p1::witness_text(h.binary_sha256,std::string(64,'c'));
  p1::witness_text(h.worker_binary_sha256,std::string(64,'d'));
  p1::witness_text(h.worker_instance,std::string(64,'e'));
  return h;
}
p1::WitnessTick tick(uint64_t id=1,bool candidate=true) {
  p1::WitnessTick r{};
  r.job_id=candidate?id:0;r.tick=id;r.target_tick=candidate?id:0;
  r.task_generation=id+1;r.model_generation=id+2;r.config_generation=id+3;
  r.schedule_generation=id+4;r.clock_epoch=id+5;
  r.planned_ns=100+id;r.start_ns=110+id;r.end_ns=120+id;
  r.skipped_ticks=id%3;r.candidate_present=candidate;
  return r;
}
p1::WitnessSubmit submit(uint64_t id=1) {
  p1::WitnessSubmit r{};
  r.job_id=id;r.tick=id;r.target_tick=id+1;
  r.task_generation=id+1;r.model_generation=id+2;r.config_generation=id+3;
  r.schedule_generation=id+4;r.clock_epoch=id+5;r.commit_ns=200+id;
  return r;
}
p1::WitnessActivation activation(uint64_t id=1,bool accepted=true) {
  p1::WitnessActivation r{};
  r.job_id=id;r.tick=id;r.target_tick=id;
  r.task_generation=id+1;r.model_generation=id+2;r.config_generation=id+3;
  r.schedule_generation=id+4;r.clock_epoch=id+5;
  r.commit_ns=300+id;r.ready_commit_ns=250+id;r.accepted=accepted;
  r.reason_code=accepted?p1::WitnessActivationReason::Accepted:p1::WitnessActivationReason::OtherRejected;
  return r;
}
p1::WitnessPhase phase(uint64_t id=1) {
  p1::WitnessPhase r{};
  r.event_code=p1::WitnessPhaseKind::StoppingObserved;
  r.observation_code=p1::WitnessObservation::TickStart;
  r.ns=400+id;r.tick=id;r.job_id=id;r.admission_slots=-1;
  r.candidate_present=p1::WitnessState::Unknown;r.pending_present=p1::WitnessState::Unknown;
  r.failed=p1::WitnessState::False;r.stopping=p1::WitnessState::True;r.pause_active=p1::WitnessState::Unknown;
  return r;
}
class TempDirectory {
 public:
  TempDirectory() {
    char pattern[]="/tmp/p1-witness-test-XXXXXX";
    const auto made=::mkdtemp(pattern);
    if (!made) throw std::runtime_error("test temp directory unavailable");
    directory=made;
  }
  ~TempDirectory() {
    for (const auto &file:files) ::unlink(file.c_str());
    ::rmdir(directory.c_str());
  }
  std::string path(std::string name) {auto result=directory+"/"+name;files.push_back(result);return result;}
  std::string directory;
  std::vector<std::string> files;
};
bool exists(const std::string &path) {struct stat s{};return ::lstat(path.c_str(),&s)==0;}
std::string contents(const std::string &path) {
  std::ifstream in(path,std::ios::binary);
  return {std::istreambuf_iterator<char>(in),std::istreambuf_iterator<char>()};
}
void stats(const p1::WitnessStreamStats &s,uint64_t attempts,uint64_t reserved,uint64_t overflow=0,uint64_t rejected=0) {
  EXPECT_EQ(s.attempts,attempts);
  EXPECT_EQ(s.reserved,reserved);
  EXPECT_EQ(s.published,reserved);
  EXPECT_EQ(s.overflow,overflow);
  EXPECT_EQ(s.rejected,rejected);
}
} // namespace

TEST(P1Witness,TextHelperRejectsEmptyNulAndTruncationWithoutPartialIdentity) {
  char out[5]{};
  EXPECT_TRUE(p1::witness_text(out,"abcd"));
  EXPECT_EQ(std::string(out),"abcd");
  EXPECT_FALSE(p1::witness_text(out,"abcde"));
  EXPECT_EQ(out[0],0);
  EXPECT_FALSE(p1::witness_text(out,""));
  EXPECT_FALSE(p1::witness_text(out,std::string_view("a\0b",3)));
  EXPECT_EQ(out[0],0);
}

TEST(P1Witness,DefaultOffDoesNotReserveOrCreateTerminalOutput) {
  p1::Witness w;TempDirectory temporary;auto path=temporary.path("disabled.json");
  EXPECT_FALSE(w.enabled());
  EXPECT_FALSE(w.record_tick(tick()));
  EXPECT_FALSE(w.record_submit(submit()));
  EXPECT_FALSE(w.record_activation(activation()));
  EXPECT_FALSE(w.record_phase(phase()));
  w.close_after_join();
  EXPECT_FALSE(w.write_terminal(path.c_str()));
  EXPECT_FALSE(exists(path));
  auto s=w.summary();
  stats(s.tick,0,0);stats(s.submit,0,0);stats(s.activation,0,0);stats(s.phase,0,0);
  EXPECT_FALSE(s.audit_complete);
  EXPECT_FALSE(s.incomplete);
  EXPECT_EQ(s.first_failure.code,p1::WitnessFailure::None);
}

TEST(P1Witness,ValidEmptyObservationCompletesOnlyAfterClose) {
  p1::Witness w(true,header());
  EXPECT_FALSE(w.summary().audit_complete);
  EXPECT_FALSE(w.summary().closed);
  w.close_after_join();auto s=w.summary();
  EXPECT_TRUE(s.closed);
  EXPECT_TRUE(s.audit_complete);
  EXPECT_FALSE(s.incomplete);
  EXPECT_FALSE(s.overflow);
  w.close_after_join();
  EXPECT_TRUE(w.summary().audit_complete);
}

TEST(P1Witness,ExternalHeaderPinFailureOnlyInvalidatesEnabledObservation) {
  p1::Witness disabled;disabled.mark_header_invalid();disabled.close_after_join();
  EXPECT_FALSE(disabled.summary().incomplete);
  EXPECT_EQ(disabled.summary().first_failure.code,p1::WitnessFailure::None);
  p1::Witness enabled(true,header());enabled.mark_header_invalid();
  EXPECT_TRUE(enabled.record_tick(tick()));
  EXPECT_TRUE(enabled.record_submit(submit()));
  enabled.close_after_join();auto s=enabled.summary();
  stats(s.tick,1,1);stats(s.submit,1,1);
  EXPECT_TRUE(s.incomplete);
  EXPECT_FALSE(s.audit_complete);
  EXPECT_EQ(s.first_failure.code,p1::WitnessFailure::Header);
}

TEST(P1Witness,LayoutAccountsForPayloadSlotsStreamsAndWholeFixedObject) {
  constexpr auto layout=p1::Witness::layout();
  static_assert(layout.total_bytes==sizeof(p1::Witness),"whole object footprint is exact");
  static_assert(layout.header_bytes==sizeof(p1::WitnessHeader),"header footprint is exact");
  EXPECT_EQ(layout.tick_payload_bytes,sizeof(p1::WitnessTick));
  EXPECT_EQ(layout.submit_payload_bytes,sizeof(p1::WitnessSubmit));
  EXPECT_EQ(layout.activation_payload_bytes,sizeof(p1::WitnessActivation));
  EXPECT_EQ(layout.phase_payload_bytes,sizeof(p1::WitnessPhase));
  EXPECT_EQ(layout.first_failure_payload_bytes,sizeof(p1::WitnessFirstFailure));
  EXPECT_GT(layout.tick_slot_bytes,layout.tick_payload_bytes);
  EXPECT_GT(layout.submit_slot_bytes,layout.submit_payload_bytes);
  EXPECT_GT(layout.activation_slot_bytes,layout.activation_payload_bytes);
  EXPECT_GT(layout.phase_slot_bytes,layout.phase_payload_bytes);
  EXPECT_GE(layout.tick_stream_bytes,256*layout.tick_slot_bytes);
  EXPECT_GE(layout.submit_stream_bytes,128*layout.submit_slot_bytes);
  EXPECT_GE(layout.activation_stream_bytes,128*layout.activation_slot_bytes);
  EXPECT_GE(layout.phase_stream_bytes,32*layout.phase_slot_bytes);
  EXPECT_GE(layout.total_bytes,layout.header_bytes+layout.tick_stream_bytes+layout.submit_stream_bytes+layout.activation_stream_bytes+layout.phase_stream_bytes);
  EXPECT_LT(layout.total_bytes,96*1024);
}

TEST(P1Witness,InvalidHeaderIsFirstFailureAndCannotComplete) {
  std::vector<p1::WitnessHeader> invalid;
  invalid.push_back({});
  auto h=header();std::memset(h.run_id,'r',sizeof(h.run_id));invalid.push_back(h);
  h=header();p1::witness_text(h.run_id,"with\ncontrol");invalid.push_back(h);
  h=header();p1::witness_text(h.run_id,std::string("bad\x7f",4));invalid.push_back(h);
  h=header();p1::witness_text(h.run_id,std::string("\xc0\x80",2));invalid.push_back(h);
  h=header();p1::witness_text(h.run_id,std::string("\xed\xa0\x80",3));invalid.push_back(h);
  h=header();p1::witness_text(h.run_id,std::string("\xf4\x90\x80\x80",4));invalid.push_back(h);
  h=header();p1::witness_text(h.run_id,std::string("\xe4\xb8",2));invalid.push_back(h);
  h=header();h.boot_id[8]='x';invalid.push_back(h);
  h=header();h.boot_id[0]='A';invalid.push_back(h);
  h=header();h.contract_sha256[3]='A';invalid.push_back(h);
  h=header();h.worker_instance[63]='\0';invalid.push_back(h);
  for (const auto &bad:invalid) {
    p1::Witness w(true,bad);w.close_after_join();auto s=w.summary();
    EXPECT_FALSE(s.audit_complete);
    EXPECT_TRUE(s.incomplete);
    EXPECT_EQ(s.first_failure.code,p1::WitnessFailure::Header);
    EXPECT_EQ(s.first_failure.stream,p1::WitnessStream::None);
    EXPECT_EQ(s.first_failure.ns,0);
  }
}

TEST(P1Witness,ExactTickCapacityAndNextAttemptOverflowKeepPublishedRows) {
  p1::Witness w(true,header());
  for (uint64_t i=1;i<=256;++i) {
    EXPECT_TRUE(w.record_tick(tick(i,i%2==0)));
  }
  auto at_capacity=w.summary();stats(at_capacity.tick,256,256);
  EXPECT_FALSE(at_capacity.overflow);
  EXPECT_FALSE(w.record_tick(tick(257)));
  w.close_after_join();auto s=w.summary();stats(s.tick,257,256,1);
  EXPECT_EQ(s.ticks_without_candidate,128);
  EXPECT_TRUE(s.incomplete);
  EXPECT_TRUE(s.overflow);
  EXPECT_FALSE(s.audit_complete);
  EXPECT_EQ(s.first_failure.code,p1::WitnessFailure::Capacity);
  EXPECT_EQ(s.first_failure.stream,p1::WitnessStream::Tick);
  EXPECT_EQ(s.first_failure.ticket,257);
  uint64_t count=0;
  w.for_each_tick_after_join([&](uint64_t sequence,const auto &r){++count;EXPECT_EQ(sequence,r.tick);});
  EXPECT_EQ(count,256);
}

TEST(P1Witness,ExactSubmitCapacityAndNextAttemptOverflow) {
  p1::Witness w(true,header());
  for (uint64_t i=1;i<=128;++i) {
    EXPECT_TRUE(w.record_submit(submit(i)));
  }
  stats(w.summary().submit,128,128);
  EXPECT_FALSE(w.record_submit(submit(129)));
  w.close_after_join();auto s=w.summary();stats(s.submit,129,128,1);
  EXPECT_EQ(s.first_failure.stream,p1::WitnessStream::Submit);
  EXPECT_EQ(s.first_failure.ticket,129);
  EXPECT_FALSE(s.audit_complete);
}

TEST(P1Witness,ExactActivationCapacityCountsOnlyStoredAcceptedAttempts) {
  p1::Witness w(true,header());
  for (uint64_t i=1;i<=128;++i) {
    EXPECT_TRUE(w.record_activation(activation(i,i%2==0)));
  }
  EXPECT_EQ(w.summary().accepted_activations,64);
  EXPECT_FALSE(w.record_activation(activation(129,true)));
  w.close_after_join();auto s=w.summary();stats(s.activation,129,128,1);
  EXPECT_EQ(s.accepted_activations,64);
  EXPECT_EQ(s.first_failure.stream,p1::WitnessStream::Activation);
  EXPECT_EQ(s.first_failure.ticket,129);
}

TEST(P1Witness,ExactPhaseCapacityAndNextAttemptOverflow) {
  p1::Witness w(true,header());
  for (uint64_t i=1;i<=32;++i) {
    EXPECT_TRUE(w.record_phase(phase(i)));
  }
  EXPECT_FALSE(w.record_phase(phase(33)));
  w.close_after_join();auto s=w.summary();stats(s.phase,33,32,1);
  EXPECT_EQ(s.first_failure.stream,p1::WitnessStream::Phase);
  EXPECT_EQ(s.first_failure.ticket,33);
  EXPECT_EQ(s.first_failure.ns,433);
}

TEST(P1Witness,FirstFailureRetainsOriginalCauseAcrossLaterFailures) {
  p1::Witness w(true,header());auto bad=submit();bad.commit_ns=-3;
  EXPECT_FALSE(w.record_submit(bad));
  for (uint64_t i=1;i<=33;++i) w.record_phase(phase(i));
  w.close_after_join();
  EXPECT_FALSE(w.record_tick(tick()));
  auto s=w.summary();
  EXPECT_EQ(s.first_failure.code,p1::WitnessFailure::InvalidRecord);
  EXPECT_EQ(s.first_failure.stream,p1::WitnessStream::Submit);
  EXPECT_EQ(s.first_failure.ns,0);
  EXPECT_EQ(s.first_failure.ticket,0);
  EXPECT_TRUE(s.overflow);
}

TEST(P1Witness,InvalidTickTimesAndCandidateIdentityRejectBeforeReservation) {
  std::vector<p1::WitnessTick> invalid;auto r=tick();r.planned_ns=0;invalid.push_back(r);
  r=tick();r.start_ns=r.planned_ns-1;invalid.push_back(r);
  r=tick();r.end_ns=r.start_ns-1;invalid.push_back(r);
  r=tick();r.job_id=0;invalid.push_back(r);
  r=tick();r.target_tick=r.tick+1;invalid.push_back(r);
  r=tick(1,false);r.job_id=1;invalid.push_back(r);
  r=tick(1,false);r.target_tick=1;invalid.push_back(r);
  p1::Witness w(true,header());
  for (const auto &bad:invalid) {
    EXPECT_FALSE(w.record_tick(bad));
  }
  EXPECT_TRUE(w.record_tick(tick()));
  w.close_after_join();stats(w.summary().tick,8,1,0,7);
  EXPECT_FALSE(w.summary().audit_complete);
}

TEST(P1Witness,InvalidSubmitIncludesUnsignedTargetWraparound) {
  std::vector<p1::WitnessSubmit> invalid;auto r=submit();r.job_id=0;invalid.push_back(r);
  r=submit();r.commit_ns=0;invalid.push_back(r);
  r=submit();r.target_tick=r.tick;invalid.push_back(r);
  r=submit();r.tick=UINT64_MAX;r.target_tick=0;invalid.push_back(r);
  p1::Witness w(true,header());
  for (const auto &bad:invalid) {
    EXPECT_FALSE(w.record_submit(bad));
  }
  EXPECT_TRUE(w.record_submit(submit()));
  w.close_after_join();stats(w.summary().submit,5,1,0,4);
}

TEST(P1Witness,InvalidActivationCommitAndReasonRejectBeforeReservation) {
  std::vector<p1::WitnessActivation> invalid;auto r=activation();r.job_id=0;invalid.push_back(r);
  r=activation();r.commit_ns=0;invalid.push_back(r);
  r=activation();r.ready_commit_ns=0;invalid.push_back(r);
  r=activation();r.ready_commit_ns=r.commit_ns+1;invalid.push_back(r);
  r=activation();r.target_tick=r.tick+1;invalid.push_back(r);
  r=activation();r.reason_code=p1::WitnessActivationReason::Shutdown;invalid.push_back(r);
  r=activation(1,false);r.reason_code=p1::WitnessActivationReason::Accepted;invalid.push_back(r);
  r=activation();r.reason_code=static_cast<p1::WitnessActivationReason>(4);invalid.push_back(r);
  p1::Witness w(true,header());
  for (const auto &bad:invalid) {
    EXPECT_FALSE(w.record_activation(bad));
  }
  EXPECT_TRUE(w.record_activation(activation()));
  w.close_after_join();stats(w.summary().activation,9,1,0,8);
  EXPECT_EQ(w.summary().accepted_activations,1);
}

TEST(P1Witness,InvalidPhaseEnumsStatesAndAdmissionBoundsReject) {
  std::vector<p1::WitnessPhase> invalid;auto r=phase();r.ns=0;invalid.push_back(r);
  r=phase();r.event_code=static_cast<p1::WitnessPhaseKind>(0);invalid.push_back(r);
  r=phase();r.event_code=static_cast<p1::WitnessPhaseKind>(10);invalid.push_back(r);
  r=phase();r.observation_code=static_cast<p1::WitnessObservation>(7);invalid.push_back(r);
  r=phase();r.admission_slots=-2;invalid.push_back(r);
  r=phase();r.admission_slots=3;invalid.push_back(r);
  r=phase();r.failed=static_cast<p1::WitnessState>(3);invalid.push_back(r);
  p1::Witness w(true,header());
  for (const auto &bad:invalid) {
    EXPECT_FALSE(w.record_phase(bad));
  }
  EXPECT_TRUE(w.record_phase(phase()));
  w.close_after_join();stats(w.summary().phase,8,1,0,7);
}

TEST(P1Witness,UnknownPhaseObservationIsStoredWithoutInventingBusinessState) {
  p1::Witness w(true,header());auto r=phase();
  EXPECT_TRUE(w.record_phase(r));
  w.close_after_join();uint64_t count=0;
  w.for_each_phase_after_join([&](uint64_t sequence,const auto &stored){
    ++count;
    EXPECT_EQ(sequence,1);
    EXPECT_EQ(stored.admission_slots,-1);
    EXPECT_EQ(stored.candidate_present,p1::WitnessState::Unknown);
    EXPECT_EQ(stored.pending_present,p1::WitnessState::Unknown);
    EXPECT_EQ(stored.pause_active,p1::WitnessState::Unknown);
  });
  EXPECT_EQ(count,1);
  EXPECT_TRUE(w.summary().audit_complete);
}

TEST(P1Witness,ReservationDoesNotExposePayloadUntilReleasePublication) {
  p1::witness_detail::FixedStream<p1::WitnessSubmit,2> stream;auto reservation=stream.reserve();
  ASSERT_TRUE(reservation.granted);
  EXPECT_EQ(reservation.index,0);
  EXPECT_EQ(stream.committed(0),nullptr);
  EXPECT_FALSE(stream.all_committed());
  EXPECT_EQ(stream.stats().published,0);
  EXPECT_TRUE(stream.publish(reservation,submit(7)));
  ASSERT_NE(stream.committed(0),nullptr);
  EXPECT_EQ(stream.committed(0)->job_id,7);
  EXPECT_TRUE(stream.all_committed());
  EXPECT_FALSE(stream.publish(reservation,submit(8)));
  EXPECT_EQ(stream.committed(0)->job_id,7);
  EXPECT_EQ(stream.stats().published,1);
}

TEST(P1Witness,AbandonedReservationIsDetectablyUnpublishedAndNeverRecycled) {
  p1::witness_detail::FixedStream<p1::WitnessSubmit,2> stream;
  auto first=stream.reserve();auto second=stream.reserve();
  EXPECT_TRUE(stream.publish(second,submit(9)));
  EXPECT_FALSE(stream.all_committed());
  EXPECT_EQ(stream.committed(first.index),nullptr);
  EXPECT_FALSE(stream.reserve().granted);
  auto s=stream.stats();
  EXPECT_EQ(s.attempts,3);
  EXPECT_EQ(s.reserved,2);
  EXPECT_EQ(s.published,1);
  EXPECT_EQ(s.overflow,1);
  EXPECT_TRUE(stream.publish(first,submit(8)));
  EXPECT_TRUE(stream.all_committed());
}

TEST(P1Witness,ConcurrentWritersReachEveryExactCapacityWithoutTornPayloads) {
  p1::Witness w(true,header());std::atomic<bool> start{false};std::atomic<uint64_t> rejected{0};
  std::vector<std::thread> threads;
  for (uint64_t producer=0;producer<4;++producer) threads.emplace_back([&,producer]{
    while (!start.load(std::memory_order_acquire)) std::this_thread::yield();
    for (uint64_t i=1;i<=64;++i) {
      const auto id=producer*64+i;
      if (!w.record_tick(tick(id,id%2==0))) rejected.fetch_add(1);
    }
    for (uint64_t i=1;i<=32;++i) {
      const auto id=producer*32+i;
      if (!w.record_submit(submit(id))) rejected.fetch_add(1);
      if (!w.record_activation(activation(id,id%2==0))) rejected.fetch_add(1);
    }
    for (uint64_t i=1;i<=8;++i) if (!w.record_phase(phase(producer*8+i))) rejected.fetch_add(1);
  });
  start.store(true,std::memory_order_release);
  for (auto &thread:threads) thread.join();
  w.close_after_join();auto s=w.summary();
  EXPECT_EQ(rejected.load(),0);
  stats(s.tick,256,256);stats(s.submit,128,128);stats(s.activation,128,128);stats(s.phase,32,32);
  EXPECT_EQ(s.ticks_without_candidate,128);
  EXPECT_EQ(s.accepted_activations,64);
  EXPECT_TRUE(s.audit_complete);
  std::set<uint64_t> ticks,submissions,activations,phases;
  w.for_each_tick_after_join([&](uint64_t,const auto &r){
    ticks.insert(r.tick);
    EXPECT_EQ(r.task_generation,r.tick+1);
    EXPECT_EQ(r.model_generation,r.tick+2);
    EXPECT_EQ(r.clock_epoch,r.tick+5);
    EXPECT_EQ(r.start_ns,110+r.tick);
    EXPECT_EQ(r.end_ns,120+r.tick);
  });
  w.for_each_submit_after_join([&](uint64_t,const auto &r){
    submissions.insert(r.job_id);
    EXPECT_EQ(r.target_tick,r.tick+1);
    EXPECT_EQ(r.commit_ns,200+r.job_id);
    EXPECT_EQ(r.schedule_generation,r.job_id+4);
  });
  w.for_each_activation_after_join([&](uint64_t,const auto &r){
    activations.insert(r.job_id);
    EXPECT_EQ(r.ready_commit_ns,250+r.job_id);
    EXPECT_EQ(r.commit_ns,300+r.job_id);
    EXPECT_EQ(r.accepted,r.job_id%2==0);
  });
  w.for_each_phase_after_join([&](uint64_t,const auto &r){
    phases.insert(r.job_id);
    EXPECT_EQ(r.ns,400+r.job_id);
    EXPECT_EQ(r.pending_present,p1::WitnessState::Unknown);
  });
  EXPECT_EQ(ticks.size(),256);
  EXPECT_EQ(submissions.size(),128);
  EXPECT_EQ(activations.size(),128);
  EXPECT_EQ(phases.size(),32);
}

TEST(P1Witness,ConcurrentOverflowRetainsOneWholeFirstFailure) {
  p1::Witness w(true,header());std::atomic<bool> start{false};std::vector<std::thread> threads;
  for (uint64_t producer=0;producer<8;++producer) threads.emplace_back([&,producer]{
    while (!start.load(std::memory_order_acquire)) std::this_thread::yield();
    for (uint64_t i=1;i<=64;++i) w.record_phase(phase(producer*64+i));
  });
  start.store(true,std::memory_order_release);
  for (auto &thread:threads) thread.join();
  w.close_after_join();auto s=w.summary();stats(s.phase,512,32,480);
  EXPECT_EQ(s.first_failure.code,p1::WitnessFailure::Capacity);
  EXPECT_EQ(s.first_failure.stream,p1::WitnessStream::Phase);
  EXPECT_EQ(s.first_failure.ticket,33);
  EXPECT_GE(s.first_failure.ns,401);
  EXPECT_LE(s.first_failure.ns,912);
  EXPECT_TRUE(s.incomplete);
  EXPECT_FALSE(s.audit_complete);
}

TEST(P1Witness,CloseRacingProducersCannotLeaveACompleteAuditAfterLateAttempt) {
  p1::Witness w(true,header());std::atomic<bool> start{false};std::vector<std::thread> threads;
  for (uint64_t producer=0;producer<8;++producer) threads.emplace_back([&,producer]{
    while (!start.load(std::memory_order_acquire)) std::this_thread::yield();
    for (uint64_t i=1;i<=16;++i) w.record_tick(tick(producer*16+i));
  });
  start.store(true,std::memory_order_release);w.close_after_join();
  for (auto &thread:threads) thread.join();
  EXPECT_FALSE(w.record_tick(tick(129)));
  w.close_after_join();auto s=w.summary();
  EXPECT_TRUE(s.closed);
  EXPECT_TRUE(s.incomplete);
  EXPECT_FALSE(s.audit_complete);
  EXPECT_EQ(s.tick.attempts,129);
  EXPECT_EQ(s.tick.attempts,s.tick.reserved+s.tick.rejected);
  EXPECT_EQ(s.tick.published,s.tick.reserved);
  EXPECT_LE(s.tick.reserved,128);
  EXPECT_EQ(s.tick.overflow,0);
}

TEST(P1Witness,AfterCloseEachStreamRejectsWithoutChangingPublishedRows) {
  p1::Witness w(true,header());
  EXPECT_TRUE(w.record_tick(tick()));
  EXPECT_TRUE(w.record_submit(submit()));
  EXPECT_TRUE(w.record_activation(activation()));
  EXPECT_TRUE(w.record_phase(phase()));
  w.close_after_join();
  EXPECT_TRUE(w.summary().audit_complete);
  EXPECT_FALSE(w.record_tick(tick(2)));
  EXPECT_FALSE(w.record_submit(submit(2)));
  EXPECT_FALSE(w.record_activation(activation(2)));
  EXPECT_FALSE(w.record_phase(phase(2)));
  auto s=w.summary();stats(s.tick,2,1,0,1);stats(s.submit,2,1,0,1);stats(s.activation,2,1,0,1);stats(s.phase,2,1,0,1);
  EXPECT_EQ(s.first_failure.code,p1::WitnessFailure::AfterClose);
  EXPECT_EQ(s.first_failure.stream,p1::WitnessStream::Tick);
  EXPECT_TRUE(s.incomplete);
  EXPECT_FALSE(s.audit_complete);
}

TEST(P1Witness,TerminalBeforeCloseIsRejectedAndSingleAttemptIsConsumed) {
  TempDirectory temporary;auto path=temporary.path("too-early.json");p1::Witness w(true,header());
  EXPECT_FALSE(w.write_terminal(path.c_str()));
  EXPECT_FALSE(exists(path));
  w.close_after_join();
  EXPECT_FALSE(w.write_terminal(path.c_str()));
  EXPECT_FALSE(exists(path));
  EXPECT_EQ(w.summary().first_failure.code,p1::WitnessFailure::Write);
  EXPECT_FALSE(w.summary().audit_complete);
}

TEST(P1Witness,TerminalJsonPreservesPinnedHeaderRowsCountersAndUnknownStates) {
  TempDirectory temporary;auto path=temporary.path("terminal.json");
  const auto run=std::string("unicode-\xe4\xb8\xad\xe6\x96\x87-\"quote\\slash");
  p1::Witness w(true,header(run));
  ASSERT_TRUE(w.record_tick(tick(4,false)));
  ASSERT_TRUE(w.record_submit(submit(4)));
  ASSERT_TRUE(w.record_activation(activation(4)));
  ASSERT_TRUE(w.record_phase(phase(4)));
  w.close_after_join();
  ASSERT_TRUE(w.write_terminal(path.c_str()));
  auto j=Json::parse(contents(path));
  EXPECT_EQ(j.at("schema"),"p1-fixed-witness-v1");
  EXPECT_EQ(j.at("clock_name"),"CLOCK_MONOTONIC");
  EXPECT_EQ(j.at("header").at("run_id"),run);
  EXPECT_EQ(j.at("header").at("worker_instance"),std::string(64,'e'));
  EXPECT_EQ(j.at("audit_complete"),true);
  EXPECT_EQ(j.at("incomplete"),false);
  EXPECT_EQ(j.at("capacities"),Json({{"tick",256},{"submit",128},{"activation",128},{"phase",32}}));
  EXPECT_EQ(j.at("counters").at("ticks_without_candidate"),1);
  EXPECT_EQ(j.at("counters").at("accepted_activations"),1);
  EXPECT_EQ(j.at("tick")[0].at("sequence"),1);
  EXPECT_EQ(j.at("tick")[0].at("tick"),4);
  EXPECT_EQ(j.at("tick")[0].at("job_id"),0);
  EXPECT_EQ(j.at("submit")[0].at("target_tick"),5);
  EXPECT_EQ(j.at("activation")[0].at("ready_commit_ns"),254);
  EXPECT_TRUE(j.at("phase")[0].at("candidate_present").is_null());
  EXPECT_TRUE(j.at("phase")[0].at("pending_present").is_null());
  EXPECT_TRUE(j.at("phase")[0].at("pause_active").is_null());
  EXPECT_EQ(j.at("phase")[0].at("failed"),false);
  EXPECT_EQ(j.at("phase")[0].at("stopping"),true);
  EXPECT_EQ(j.at("phase")[0].at("admission_slots"),-1);
  EXPECT_EQ(j.at("first_failure"),Json({{"code",0},{"stream",0},{"ns",0},{"ticket",0}}));
  struct stat state{};ASSERT_EQ(::stat(path.c_str(),&state),0);
  EXPECT_EQ(state.st_mode&0777,0600);
}

TEST(P1Witness,TerminalPreservesExistingFileAndExistingSymlinkTarget) {
  TempDirectory temporary;auto path=temporary.path("existing.json");
  {std::ofstream out(path);out<<"preserve-existing";}
  p1::Witness first(true,header());first.close_after_join();
  EXPECT_FALSE(first.write_terminal(path.c_str()));
  EXPECT_EQ(contents(path),"preserve-existing");
  EXPECT_EQ(first.summary().first_failure.code,p1::WitnessFailure::Write);
  auto link=temporary.path("link.json");ASSERT_EQ(::symlink(path.c_str(),link.c_str()),0);
  p1::Witness second(true,header());second.close_after_join();
  EXPECT_FALSE(second.write_terminal(link.c_str()));
  EXPECT_EQ(contents(path),"preserve-existing");
  EXPECT_EQ(second.summary().first_failure.code,p1::WitnessFailure::Write);
}

TEST(P1Witness,TerminalOpenFailureIsRecordedAndCannotBeRetriedAtAnotherPath) {
  TempDirectory temporary;auto missing=temporary.directory+"/absent/terminal.json";
  auto retry=temporary.path("retry.json");p1::Witness w(true,header());w.close_after_join();
  EXPECT_FALSE(w.write_terminal(missing.c_str()));
  EXPECT_EQ(w.summary().first_failure.code,p1::WitnessFailure::Write);
  EXPECT_TRUE(w.summary().incomplete);
  EXPECT_FALSE(w.write_terminal(retry.c_str()));
  EXPECT_FALSE(exists(retry));
}

TEST(P1Witness,CompetingTerminalCreatorsCannotOverwriteTheWinner) {
  TempDirectory temporary;auto path=temporary.path("exclusive.json");
  p1::Witness first(true,header("first")),second(true,header("second"));
  first.close_after_join();second.close_after_join();std::atomic<bool> start{false};
  bool result_first=false,result_second=false;
  std::thread a([&]{while(!start.load())std::this_thread::yield();result_first=first.write_terminal(path.c_str());});
  std::thread b([&]{while(!start.load())std::this_thread::yield();result_second=second.write_terminal(path.c_str());});
  start=true;a.join();b.join();
  EXPECT_NE(result_first,result_second);
  auto j=Json::parse(contents(path));
  EXPECT_EQ(j.at("header").at("run_id"),result_first?"first":"second");
  EXPECT_TRUE(j.at("audit_complete").get<bool>());
  EXPECT_EQ((result_first?second:first).summary().first_failure.code,p1::WitnessFailure::Write);
}

TEST(P1Witness,RepeatedTerminalCallPreservesOriginalSnapshotAndMarksMisuse) {
  TempDirectory temporary;auto path=temporary.path("single.json");p1::Witness w(true,header());w.close_after_join();
  ASSERT_TRUE(w.write_terminal(path.c_str()));
  auto original=contents(path);
  EXPECT_FALSE(w.write_terminal(path.c_str()));
  EXPECT_EQ(contents(path),original);
  EXPECT_EQ(w.summary().first_failure.code,p1::WitnessFailure::Write);
  EXPECT_FALSE(w.summary().audit_complete);
}

TEST(P1Witness,OperatingSystemWriteFailurePreservesPartialFileAndIncompleteState) {
  TempDirectory temporary;auto path=temporary.path("partial.json");
  ASSERT_EXIT({
    struct rlimit limit{};
    if (::getrlimit(RLIMIT_FSIZE,&limit)!=0) ::_exit(10);
    limit.rlim_cur=128;
    if (::setrlimit(RLIMIT_FSIZE,&limit)!=0) ::_exit(11);
    ::signal(SIGXFSZ,SIG_IGN);
    p1::Witness w(true,header());w.close_after_join();
    if (w.write_terminal(path.c_str())) ::_exit(12);
    const auto s=w.summary();
    if (!s.incomplete || s.audit_complete || s.first_failure.code!=p1::WitnessFailure::Write) ::_exit(13);
    if (w.write_terminal(path.c_str())) ::_exit(14);
    ::_exit(0);
  },::testing::ExitedWithCode(0),"");
  ASSERT_TRUE(exists(path));
  auto partial=contents(path);
  EXPECT_GT(partial.size(),0);
  EXPECT_LE(partial.size(),128);
  EXPECT_ANY_THROW(Json::parse(partial));
}
