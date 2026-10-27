#pragma once
#include "../observer/src/shadow/p1_witness.hpp"
#include <string_view>

namespace c37_witness_fixture {
inline p1::WitnessHeader header() {
  p1::WitnessHeader h{};
  p1::witness_text(h.run_id,"C37_native_finite_witness");
  p1::witness_text(h.boot_id,"5a417cdc-1c7f-4c5c-8186-6d7e9a85ddcb");
  p1::witness_text(h.contract_sha256,std::string(64,'1'));
  p1::witness_text(h.source_sha256,std::string(64,'2'));
  p1::witness_text(h.binary_sha256,std::string(64,'3'));
  p1::witness_text(h.worker_binary_sha256,std::string(64,'4'));
  p1::witness_text(h.worker_instance,std::string(64,'5'));
  return h;
}
template<class Row>inline void identity(Row &r,uint64_t job,uint64_t tick,uint64_t target) {
  r.job_id=job;r.tick=tick;r.target_tick=target;r.task_generation=1;r.model_generation=1;
  r.config_generation=1;r.schedule_generation=1;r.clock_epoch=1;
}
inline p1::WitnessPhase phase(p1::WitnessPhaseKind kind,int64_t ns,uint64_t tick=0,uint64_t job=0) {
  p1::WitnessPhase p{};p.event_code=kind;p.ns=ns;p.tick=tick;p.job_id=job;p.admission_slots=0;
  p.observation_code=kind==p1::WitnessPhaseKind::Close?p1::WitnessObservation::Close:
    kind==p1::WitnessPhaseKind::BusinessReady?p1::WitnessObservation::FinalActivation:p1::WitnessObservation::None;
  p.candidate_present=p.pending_present=p.failed=p.stopping=p.pause_active=p1::WitnessState::False;
  return p;
}
inline p1::WitnessTick tick(uint64_t index,uint64_t job,int64_t planned) {
  p1::WitnessTick r{};identity(r,job,index,job?index:0);
  r.planned_ns=planned;r.start_ns=planned+1;r.end_ns=planned+40;r.candidate_present=job!=0;return r;
}
inline p1::WitnessSubmit submit(uint64_t job,uint64_t preceding_tick,int64_t ns) {
  p1::WitnessSubmit r{};identity(r,job,preceding_tick,preceding_tick+1);r.commit_ns=ns;return r;
}
inline p1::WitnessActivation activation(uint64_t job,uint64_t index,int64_t ns,bool accepted) {
  p1::WitnessActivation r{};identity(r,job,index,index);r.commit_ns=ns;r.ready_commit_ns=ns-40;
  r.accepted=accepted;r.reason_code=accepted?p1::WitnessActivationReason::Accepted:p1::WitnessActivationReason::OtherRejected;
  return r;
}
// These finite deterministic fixtures call the real producer API. They are not
// claimed to be solver, DDS, plant, or owned process runtime evidence.
inline bool populate(p1::Witness &w,std::string_view mode) {
  const bool accepted=mode!="all_rejected" && mode!="startup_ready";
  auto t0=tick(0,0,100),t1=tick(1,1,200);
  if(mode=="failed_tick")t1.failed_end=true;
  if(mode=="reversed_ticks"){w.record_tick(t1);w.record_tick(t0);}
  else {w.record_tick(t0);w.record_tick(t1);}
  const auto s=submit(1,0,150);w.record_submit(s);
  if(mode=="duplicate_submit")w.record_submit(s);
  const auto a=activation(1,1,220,accepted);w.record_activation(a);
  if(accepted && mode!="missing_ready") {
    auto ready=phase(p1::WitnessPhaseKind::BusinessReady,220,1,mode=="mismatched_ready"?2:1);
    if(mode=="wrong_ready_observation")ready.observation_code=p1::WitnessObservation::TickStart;
    w.record_phase(ready);
    if(mode=="duplicate_ready")w.record_phase(ready);
  }
  if(mode=="startup_ready") {
    // An actual phase append with no accepted activation still cannot be a BR.
    auto ready=phase(p1::WitnessPhaseKind::BusinessReady,180);ready.observation_code=p1::WitnessObservation::None;
    w.record_phase(ready);
  }
  if(mode=="source_failure")w.record_phase(phase(p1::WitnessPhaseKind::SourceFailure,245));
  if(mode=="append_rejected"){auto bad=s;bad.job_id=0;w.record_submit(bad);}
  if(mode=="header_invalid")w.mark_header_invalid();
  if(mode=="accepted_then_rejected") {
    w.record_tick(tick(2,2,300));w.record_submit(submit(2,1,250));w.record_activation(activation(2,2,320,false));
  }
  if(mode=="different_first_accepted") {
    w.record_tick(tick(2,2,300));w.record_submit(submit(2,1,250));w.record_activation(activation(2,2,320,true));
    w.record_phase(phase(p1::WitnessPhaseKind::BusinessReady,320,2,2));
  }
  if(mode=="overflow") {
    for(uint64_t i=2;i<=p1::Witness::tick_capacity;++i)w.record_tick(tick(i,0,100+100*i));
  }
  if(mode!="missing_close") {
    const auto close_ns=mode=="overflow"?26000:mode=="accepted_then_rejected"||mode=="different_first_accepted"?350:250;
    w.record_phase(phase(p1::WitnessPhaseKind::Close,close_ns));
  }
  w.close_after_join();
  if(mode=="after_close")w.record_submit(submit(2,1,260));
  return true;
}
}
