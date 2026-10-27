// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#pragma once
#include <array>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <cerrno>
#include <fcntl.h>
#include <ostream>
#include <sstream>
#include <string>
#include <string_view>
#include <type_traits>
#include <unistd.h>

namespace p1 {
// Observation only: never consult recording success or this summary to authorize
// a business action. Identity must be pinned before producer threads start.
struct WitnessHeader {
  char run_id[129], boot_id[37], contract_sha256[65], source_sha256[65];
  char binary_sha256[65], worker_binary_sha256[65], worker_instance[65];
};
template<std::size_t N>
bool witness_text(char (&out)[N], std::string_view value) noexcept {
  std::memset(out, 0, N);
  if (value.empty() || value.size() >= N || value.find('\0') != value.npos) return false;
  std::memcpy(out, value.data(), value.size());
  return true;
}
enum class WitnessState : uint8_t { Unknown=0, False=1, True=2 };
enum class WitnessActivationReason : uint8_t {
  Accepted=0, Shutdown=1, RunUnusable=2, OtherRejected=3
};
enum class WitnessPhaseKind : uint8_t {
  PauseArmed=1, PauseBegin=2, QueueOverflow=3, SourceFailure=4,
  StoppingObserved=5, PauseEnd=6, Close=7, InvalidationObserved=8, BusinessReady=9
};
enum class WitnessObservation : uint8_t {
  None=0, TickStart=1, FinalActivation=2, DecisionEnqueue=3,
  Submit=4, SinkThread=5, Close=6
};
enum class WitnessStream : uint8_t { None=0, Tick=1, Submit=2, Activation=3, Phase=4 };
enum class WitnessFailure : uint8_t {
  None=0, Capacity=1, InvalidRecord=2, CloseWhileWriting=3,
  Unpublished=4, Write=5, AfterClose=6, Header=7
};
#define P1_WITNESS_IDENTITY_FIELDS \
  uint64_t job_id, tick, target_tick, task_generation, model_generation; \
  uint64_t config_generation, schedule_generation, clock_epoch
struct WitnessTick {
  P1_WITNESS_IDENTITY_FIELDS;
  int64_t planned_ns, start_ns, end_ns;
  uint64_t skipped_ticks;
  bool candidate_present, failed_start, stopping_start, failed_end, stopping_end;
};
struct WitnessSubmit {
  P1_WITNESS_IDENTITY_FIELDS;
  int64_t commit_ns;
  bool failed, stopping;
};
struct WitnessActivation {
  P1_WITNESS_IDENTITY_FIELDS;
  int64_t commit_ns, ready_commit_ns;
  bool accepted, failed, stopping;
  WitnessActivationReason reason_code;
};
#undef P1_WITNESS_IDENTITY_FIELDS
struct WitnessPhase {
  WitnessPhaseKind event_code;
  WitnessObservation observation_code;
  int64_t ns;
  uint64_t tick, job_id;
  int32_t admission_slots; // -1 explicitly means the observer cannot know.
  WitnessState candidate_present, pending_present, failed, stopping, pause_active;
};
struct WitnessFirstFailure {
  WitnessFailure code;
  WitnessStream stream;
  int64_t ns;
  uint64_t ticket; // One-based reservation; 0 when no reservation exists.
};
struct WitnessStreamStats { uint64_t attempts, reserved, published, overflow, rejected; };
struct WitnessSummary {
  bool enabled, closed, audit_complete, overflow, incomplete;
  // audit_complete retains only the old internal storage-completeness meaning. These are
  // diagnostic observations, never a control or stage-qualification gate.
  bool observation_complete, business_ready_observed, normal_contract_qualified;
  WitnessStreamStats tick, submit, activation, phase;
  uint64_t ticks_without_candidate, accepted_activations;
  WitnessFirstFailure first_failure;
};
struct WitnessLayout {
  std::size_t header_bytes,first_failure_payload_bytes;
  std::size_t tick_payload_bytes,submit_payload_bytes,activation_payload_bytes,phase_payload_bytes;
  std::size_t tick_slot_bytes,submit_slot_bytes,activation_slot_bytes,phase_slot_bytes;
  std::size_t tick_stream_bytes,submit_stream_bytes,activation_stream_bytes,phase_stream_bytes;
  std::size_t total_bytes;
};
#define P1_WITNESS_POD(Type) \
  static_assert(std::is_standard_layout<Type>::value && \
                std::is_trivially_copyable<Type>::value, "fixed POD witness payload required")
P1_WITNESS_POD(WitnessHeader);
P1_WITNESS_POD(WitnessTick);
P1_WITNESS_POD(WitnessSubmit);
P1_WITNESS_POD(WitnessActivation);
P1_WITNESS_POD(WitnessPhase);
P1_WITNESS_POD(WitnessFirstFailure);
P1_WITNESS_POD(WitnessLayout);
#undef P1_WITNESS_POD
static_assert(std::atomic<uint64_t>::is_always_lock_free &&
              std::atomic<uint8_t>::is_always_lock_free &&
              std::atomic<bool>::is_always_lock_free,
              "this diagnostic build requires lock-free scalar atomics");

namespace witness_detail {
// Bounded MPSC reservation, no mutex, allocation, I/O or wait for another
// producer. CAS contention is not a hard realtime or wait-free guarantee.
// A reservation is never recycled. Only Committed permits a payload read.
template<class Row, std::size_t Capacity>
class FixedStream {
 public:
  static constexpr std::size_t slot_bytes() noexcept { return sizeof(Slot); }
  struct Reservation { bool granted; uint64_t index; };
  Reservation reserve() noexcept {
    attempts_.fetch_add(1, std::memory_order_relaxed);
    auto index = next_.load(std::memory_order_relaxed);
    while (index < Capacity) {
      if (next_.compare_exchange_weak(index, index+1, std::memory_order_relaxed)) {
        slots_[index].state.store(1, std::memory_order_release);
        return {true,index};
      }
    }
    overflow_.fetch_add(1, std::memory_order_relaxed);
    return {false,index};
  }
  bool publish(Reservation reservation, const Row &row) noexcept {
    if (!reservation.granted || reservation.index >= Capacity) return false;
    auto &slot = slots_[reservation.index];
    uint8_t expected = 1;
    if (!slot.state.compare_exchange_strong(expected, 2, std::memory_order_acquire)) return false;
    slot.value = row;
    slot.state.store(3, std::memory_order_release);
    published_.fetch_add(1, std::memory_order_release);
    return true;
  }
  void reject() noexcept {
    attempts_.fetch_add(1, std::memory_order_relaxed);
    rejected_.fetch_add(1, std::memory_order_relaxed);
  }
  const Row *committed(uint64_t index) const noexcept {
    if (index >= Capacity || slots_[index].state.load(std::memory_order_acquire) != 3) return nullptr;
    return &slots_[index].value;
  }
  WitnessStreamStats stats() const noexcept {
    return {attempts_.load(std::memory_order_acquire),next_.load(std::memory_order_acquire),
            published_.load(std::memory_order_acquire),overflow_.load(std::memory_order_acquire),
            rejected_.load(std::memory_order_acquire)};
  }
  bool all_committed() const noexcept {
    const auto count = next_.load(std::memory_order_acquire);
    for (uint64_t i=0;i<count;++i) if (!committed(i)) return false;
    return count == published_.load(std::memory_order_acquire);
  }
 private:
  struct Slot { Row value{}; std::atomic<uint8_t> state{0}; };
  std::array<Slot,Capacity> slots_{};
  std::atomic<uint64_t> next_{0}, attempts_{0}, published_{0}, overflow_{0}, rejected_{0};
};
template<std::size_t N>
std::string_view text(const char (&value)[N]) noexcept {
  std::size_t length=0;
  while (length<N && value[length]) ++length;
  return {value,length};
}
template<std::size_t N>
bool hash(const char (&value)[N]) noexcept {
  const auto view=text(value);
  if (view.size()!=64) return false;
  for (const auto c:view) if (!((c>='0' && c<='9') || (c>='a' && c<='f'))) return false;
  return true;
}
inline bool state(WitnessState value) noexcept { return static_cast<uint8_t>(value)<=2; }
inline bool utf8_without_controls(std::string_view value) noexcept {
  for (std::size_t i=0;i<value.size();) {
    const auto c=static_cast<unsigned char>(value[i++]);
    if (c<32 || c==127) return false;
    if (c<128) continue;
    unsigned remaining=0;uint32_t code=0,minimum=0;
    if (c>=0xc2 && c<=0xdf) {remaining=1;code=c&0x1f;minimum=0x80;}
    else if (c>=0xe0 && c<=0xef) {remaining=2;code=c&0x0f;minimum=0x800;}
    else if (c>=0xf0 && c<=0xf4) {remaining=3;code=c&7;minimum=0x10000;}
    else return false;
    if (value.size()-i<remaining) return false;
    while (remaining--) {
      const auto next=static_cast<unsigned char>(value[i++]);
      if ((next&0xc0)!=0x80) return false;
      code=(code<<6)|(next&0x3f);
    }
    if (code<minimum || code>0x10ffff || (code>=0xd800 && code<=0xdfff)) return false;
  }
  return true;
}
inline bool uuid(std::string_view value) noexcept {
  if (value.size()!=36) return false;
  for (std::size_t i=0;i<value.size();++i) {
    const bool dash=i==8 || i==13 || i==18 || i==23;
    const auto c=value[i];
    if (dash ? c!='-' : !((c>='0' && c<='9') || (c>='a' && c<='f'))) return false;
  }
  return true;
}
inline void json_text(std::ostream &out,std::string_view value) {
  constexpr char hex[]="0123456789abcdef";
  out << '"';
  for (unsigned char c:value) {
    if (c=='"' || c=='\\') out << '\\' << static_cast<char>(c);
    else if (c<32) out << "\\u00" << hex[c>>4] << hex[c&15];
    else out << static_cast<char>(c);
  }
  out << '"';
}
inline void json_bool(std::ostream &out,bool value) { out << (value ? "true" : "false"); }
inline void json_state(std::ostream &out,WitnessState value) {
  if (value==WitnessState::Unknown) out << "null";
  else json_bool(out,value==WitnessState::True);
}
template<class Row>
void identity(std::ostream &out,const Row &r) {
  out << ",\"job_id\":" << r.job_id << ",\"tick\":" << r.tick
      << ",\"target_tick\":" << r.target_tick << ",\"task_generation\":" << r.task_generation
      << ",\"model_generation\":" << r.model_generation << ",\"config_generation\":" << r.config_generation
      << ",\"schedule_generation\":" << r.schedule_generation << ",\"clock_epoch\":" << r.clock_epoch;
}
inline void stats(std::ostream &out,const WitnessStreamStats &s) {
  out << "{\"attempts\":" << s.attempts << ",\"reserved\":" << s.reserved
      << ",\"published\":" << s.published << ",\"overflow\":" << s.overflow
      << ",\"rejected\":" << s.rejected << '}';
}
} // namespace witness_detail

class Witness {
 public:
  static constexpr std::size_t tick_capacity=256, submit_capacity=128;
  static constexpr std::size_t activation_capacity=128, phase_capacity=32;
  explicit Witness(bool enabled=false,WitnessHeader header={}) noexcept
      : enabled_(enabled),header_(header) {
    if (enabled_ && !valid_header()) failure(WitnessFailure::Header,WitnessStream::None,0,0);
  }
  Witness(const Witness&)=delete;
  Witness& operator=(const Witness&)=delete;
  bool enabled() const noexcept { return enabled_; }
  const WitnessHeader &header() const noexcept { return header_; }
  static constexpr WitnessLayout layout() noexcept;
  // A later external identity check can invalidate this observation without
  // changing a control flag, stopping a worker, or creating a business action.
  void mark_header_invalid() noexcept {
    if (enabled_) failure(WitnessFailure::Header,WitnessStream::None,0,0);
  }
  bool record_tick(const WitnessTick &r) noexcept {
    const bool valid=r.planned_ns>0 && r.start_ns>=r.planned_ns && r.end_ns>=r.start_ns &&
      (r.candidate_present ? r.job_id>0 && r.target_tick==r.tick : r.job_id==0 && r.target_tick==0);
    return record(tick_,r,WitnessStream::Tick,r.end_ns,valid,
                  r.candidate_present ? nullptr : &ticks_without_candidate_);
  }
  bool record_submit(const WitnessSubmit &r) noexcept {
    return record(submit_,r,WitnessStream::Submit,r.commit_ns,
                  r.job_id>0 && r.commit_ns>0 && r.tick!=UINT64_MAX && r.target_tick==r.tick+1);
  }
  bool record_activation(const WitnessActivation &r) noexcept {
    const auto reason=static_cast<uint8_t>(r.reason_code);
    const bool valid=r.job_id>0 && r.commit_ns>0 && r.ready_commit_ns>0 &&
      r.ready_commit_ns<=r.commit_ns && r.target_tick==r.tick && reason<=3 &&
      (r.accepted ? reason==0 : reason!=0);
    return record(activation_,r,WitnessStream::Activation,r.commit_ns,valid,
                  r.accepted ? &accepted_activations_ : nullptr);
  }
  bool record_phase(const WitnessPhase &r) noexcept {
    const auto event=static_cast<uint8_t>(r.event_code),observation=static_cast<uint8_t>(r.observation_code);
    const bool valid=r.ns>0 && event>=1 && event<=9 && observation<=6 &&
      r.admission_slots>=-1 && r.admission_slots<=2 &&
      witness_detail::state(r.candidate_present) && witness_detail::state(r.pending_present) &&
      witness_detail::state(r.failed) && witness_detail::state(r.stopping) && witness_detail::state(r.pause_active);
    return record(phase_,r,WitnessStream::Phase,r.ns,valid);
  }
  // Call only after every tick/preparation/Sink phase producer has been joined.
  // This cannot prove a caller performed join; a concurrent or later record
  // makes the in-memory audit incomplete. A written terminal file is a snapshot
  // and cannot prove no caller attempts a record after it was written.
  // No control lock is acquired here or in append.
  void close_after_join() noexcept {
    const auto previous=lifecycle_.fetch_or(closed_bit,std::memory_order_acq_rel);
    if (previous&active_mask) failure(WitnessFailure::CloseWhileWriting,WitnessStream::None,0,0);
    check_complete(tick_,WitnessStream::Tick);
    check_complete(submit_,WitnessStream::Submit);
    check_complete(activation_,WitnessStream::Activation);
    check_complete(phase_,WitnessStream::Phase);
  }
  WitnessSummary summary() const noexcept {
    WitnessSummary s{};
    const auto lifecycle=lifecycle_.load(std::memory_order_acquire);
    s.enabled=enabled_;s.closed=(lifecycle&closed_bit)!=0;
    s.tick=tick_.stats();s.submit=submit_.stats();s.activation=activation_.stats();s.phase=phase_.stats();
    s.ticks_without_candidate=ticks_without_candidate_.load(std::memory_order_acquire);
    s.accepted_activations=accepted_activations_.load(std::memory_order_acquire);
    const auto first=first_state_.load(std::memory_order_acquire);
    if (first==2) s.first_failure=first_failure_;
    else if (first) s.first_failure={WitnessFailure::Unpublished,WitnessStream::None,0,0};
    s.overflow=s.tick.overflow || s.submit.overflow || s.activation.overflow || s.phase.overflow;
    const bool slots=tick_.all_committed() && submit_.all_committed() && activation_.all_committed() && phase_.all_committed();
    s.incomplete=failed_.load(std::memory_order_acquire) || (s.closed && (!slots || (lifecycle&active_mask)));
    s.audit_complete=enabled_ && s.closed && !s.incomplete && !s.overflow && slots;
    s.business_ready_observed=business_ready_binding();
    s.observation_complete=s.audit_complete && records_consistent(false) && ready_records_consistent();
    s.normal_contract_qualified=s.observation_complete && s.business_ready_observed && normal_records_complete();
    return s;
  }
  template<class F> void for_each_tick_after_join(F &&f) const { each(tick_,f); }
  template<class F> void for_each_submit_after_join(F &&f) const { each(submit_,f); }
  template<class F> void for_each_activation_after_join(F &&f) const { each(activation_,f); }
  template<class F> void for_each_phase_after_join(F &&f) const { each(phase_,f); }
  // Terminal serialization only, outside every business thread and Sink.
  // Caller supplies a fresh path in its create-only owned run directory.
  // Disabled never creates a file. Failed/partial output is preserved and is
  // never retried or silently rewritten as a normal proof.
  bool write_terminal(const char *path) noexcept {
    if (!enabled_) return false;
    const auto lifecycle=lifecycle_.load(std::memory_order_acquire);
    if (written_.exchange(true) || !(lifecycle&closed_bit) || (lifecycle&active_mask) || !path || !*path) {
      failure(WitnessFailure::Write,WitnessStream::None,0,0);return false;
    }
    int descriptor=-1;
    try {
      // The exclusive creation is atomic with respect to another writer or a
      // pre-existing symlink. Terminal-only formatting may allocate; append
      // producers never do. Failed/partial files remain available for audit.
      descriptor=::open(path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
      if (descriptor<0) { failure(WitnessFailure::Write,WitnessStream::None,0,0);return false; }
      std::ostringstream out;serialize(out);
      if (!out.good()) throw 0;
      const auto bytes=out.str();std::size_t offset=0;
      while (offset<bytes.size()) {
        const auto count=::write(descriptor,bytes.data()+offset,bytes.size()-offset);
        if (count<0 && errno==EINTR) continue;
        if (count<=0) throw 0;
        offset+=static_cast<std::size_t>(count);
      }
      const auto result=::close(descriptor);descriptor=-1;
      if (result!=0) { failure(WitnessFailure::Write,WitnessStream::None,0,0);return false; }
      return true;
    } catch (...) {
      if (descriptor>=0) ::close(descriptor);
      failure(WitnessFailure::Write,WitnessStream::None,0,0);return false;
    }
  }
 private:
  // Fixed-capacity, observation-only scans. No allocation, I/O, mutex, or
  // authorization is introduced into any append path. Full Source/DDS joins
  // and phase qualifications remain the independent checker's responsibility.
  bool business_ready_binding() const noexcept {
    const WitnessActivation *first=nullptr;
    for(uint64_t i=0;i<activation_capacity;++i) if(const auto r=activation_.committed(i)) {
      if(r->accepted && (!first || r->commit_ns<first->commit_ns)) first=r;
    }
    const WitnessPhase *ready=nullptr;unsigned count=0;
    for(uint64_t i=0;i<phase_capacity;++i) if(const auto r=phase_.committed(i)) {
      if(r->event_code==WitnessPhaseKind::BusinessReady){ready=r;++count;}
    }
    return first && count==1 && ready && ready->observation_code==WitnessObservation::FinalActivation &&
      ready->job_id==first->job_id && ready->tick==first->tick && ready->ns==first->commit_ns;
  }
  bool ready_records_consistent() const noexcept {
    unsigned count=0;
    for(uint64_t i=0;i<phase_capacity;++i)if(const auto r=phase_.committed(i))
      if(r->event_code==WitnessPhaseKind::BusinessReady)++count;
    return count==0 || (count==1 && business_ready_binding());
  }
  template<class A,class B>static bool same_business_identity(const A&a,const B&b) noexcept {
    return a.job_id==b.job_id && a.target_tick==b.target_tick && a.task_generation==b.task_generation &&
      a.model_generation==b.model_generation && a.config_generation==b.config_generation &&
      a.schedule_generation==b.schedule_generation && a.clock_epoch==b.clock_epoch;
  }
  bool normal_records_complete() const noexcept {
    return records_consistent(true);
  }
  bool records_consistent(bool require_normal) const noexcept {
    const auto ts=tick_.stats(),ss=submit_.stats(),as=activation_.stats(),ps=phase_.stats();
    if(!ts.published)return false;
    const WitnessPhase *close=nullptr;uint64_t close_index=0;unsigned close_count=0;int64_t latest=0;
    for(uint64_t i=0;i<ps.reserved;++i)if(const auto r=phase_.committed(i)) {
      if(r->ns>latest)latest=r->ns;
      if(require_normal && (r->event_code==WitnessPhaseKind::QueueOverflow || r->event_code==WitnessPhaseKind::SourceFailure ||
         r->failed==WitnessState::True))return false;
      if(r->event_code==WitnessPhaseKind::Close){close=r;close_index=i;++close_count;}
    }
    if(close_count!=1 || !close || close_index+1!=ps.reserved || close->observation_code!=WitnessObservation::Close)return false;
    const WitnessTick *previous_tick=nullptr;
    for(uint64_t i=0;i<ts.reserved;++i)if(const auto t=tick_.committed(i)) {
      if(require_normal && (t->failed_start || t->failed_end))return false;
      if(t->end_ns>latest)latest=t->end_ns;
      if(previous_tick) {
        if(t->start_ns<previous_tick->end_ns || t->planned_ns<=previous_tick->planned_ns)return false;
        if(t->schedule_generation==previous_tick->schedule_generation) {
          if(previous_tick->tick==UINT64_MAX || t->skipped_ticks>UINT64_MAX-previous_tick->tick-1 ||
             t->tick!=previous_tick->tick+1+t->skipped_ticks)return false;
        } else if(t->schedule_generation<=previous_tick->schedule_generation)return false;
      }
      previous_tick=t;
      if(t->candidate_present) {
        unsigned count=0;
        for(uint64_t j=0;j<as.reserved;++j)if(const auto a=activation_.committed(j))if(a->job_id==t->job_id)++count;
        if(count!=1)return false;
        for(uint64_t j=0;j<i;++j)if(const auto p=tick_.committed(j))if(p->candidate_present&&p->job_id==t->job_id)return false;
      }
    }
    int64_t previous_submit=0;
    for(uint64_t i=0;i<ss.reserved;++i)if(const auto s=submit_.committed(i)) {
      if(require_normal && s->failed)return false;
      if(s->commit_ns<previous_submit)return false;previous_submit=s->commit_ns;
      if(s->commit_ns>latest)latest=s->commit_ns;
      for(uint64_t j=0;j<i;++j)if(const auto p=submit_.committed(j))if(p->job_id==s->job_id)return false;
    }
    int64_t previous_activation=0;
    for(uint64_t i=0;i<as.reserved;++i)if(const auto a=activation_.committed(i)) {
      if(require_normal && a->failed)return false;
      if(a->commit_ns<previous_activation)return false;previous_activation=a->commit_ns;
      if(a->commit_ns>latest)latest=a->commit_ns;
      for(uint64_t j=0;j<i;++j)if(const auto p=activation_.committed(j))if(p->job_id==a->job_id)return false;
      const WitnessSubmit *submit=nullptr;const WitnessTick *tick=nullptr;unsigned sc=0,tc=0;
      for(uint64_t j=0;j<ss.reserved;++j)if(const auto s=submit_.committed(j))if(s->job_id==a->job_id){submit=s;++sc;}
      for(uint64_t j=0;j<ts.reserved;++j)if(const auto t=tick_.committed(j))if(t->candidate_present&&t->job_id==a->job_id){tick=t;++tc;}
      if(sc!=1||tc!=1||!submit||!tick||tick->tick!=a->tick||a->commit_ns<tick->start_ns||a->commit_ns>tick->end_ns||
         a->ready_commit_ns<submit->commit_ns||a->commit_ns<submit->commit_ns)return false;
      if(a->accepted && (!same_business_identity(*a,*submit)||!same_business_identity(*a,*tick)))return false;
    }
    return close->ns>=latest;
  }
  bool valid_header() const noexcept {
    return !witness_detail::text(header_.run_id).empty() && witness_detail::text(header_.run_id).size()<sizeof(header_.run_id) &&
      witness_detail::utf8_without_controls(witness_detail::text(header_.run_id)) &&
      witness_detail::uuid(witness_detail::text(header_.boot_id)) && witness_detail::hash(header_.contract_sha256) &&
      witness_detail::hash(header_.source_sha256) && witness_detail::hash(header_.binary_sha256) &&
      witness_detail::hash(header_.worker_binary_sha256) && witness_detail::hash(header_.worker_instance);
  }
  void failure(WitnessFailure code,WitnessStream stream,int64_t ns,uint64_t ticket) noexcept {
    failed_.store(true,std::memory_order_release);
    uint8_t empty=0;
    if (first_state_.compare_exchange_strong(empty,1,std::memory_order_acquire)) {
      first_failure_={code,stream,ns<0?0:ns,ticket};
      first_state_.store(2,std::memory_order_release);
    }
  }
  template<class Row,std::size_t N>
  bool record(witness_detail::FixedStream<Row,N> &stream,const Row &row,WitnessStream which,int64_t ns,bool valid,
              std::atomic<uint64_t> *published_counter=nullptr) noexcept {
    if (!enabled_) return false;
    // A single atomic modification order makes entry versus close unambiguous:
    // either close sees this active producer, or it enters after the closed bit.
    const auto lifecycle=lifecycle_.fetch_add(1,std::memory_order_acq_rel);
    bool result=false;
    if (lifecycle&closed_bit) {
      stream.reject();failure(WitnessFailure::AfterClose,which,ns,0);
    } else if (!valid) {
      stream.reject();failure(WitnessFailure::InvalidRecord,which,ns,0);
    } else {
      const auto reservation=stream.reserve();
      if (!reservation.granted) failure(WitnessFailure::Capacity,which,ns,reservation.index+1);
      else if (!(result=stream.publish(reservation,row))) failure(WitnessFailure::Unpublished,which,ns,reservation.index+1);
    }
    if (result && published_counter) published_counter->fetch_add(1,std::memory_order_relaxed);
    lifecycle_.fetch_sub(1,std::memory_order_release);
    return result;
  }
  template<class Row,std::size_t N>
  void check_complete(const witness_detail::FixedStream<Row,N> &stream,WitnessStream which) noexcept {
    if (enabled_ && !stream.all_committed()) failure(WitnessFailure::Unpublished,which,0,0);
  }
  template<class Row,std::size_t N,class F>
  static void each(const witness_detail::FixedStream<Row,N> &stream,F &&f) {
    const auto count=stream.stats().reserved;
    for (uint64_t i=0;i<count;++i) if (const auto row=stream.committed(i)) f(i+1,*row);
  }
  template<class Row,std::size_t N,class F>
  static void array(std::ostream &out,const witness_detail::FixedStream<Row,N> &stream,F f) {
    bool comma=false;out << '[';
    each(stream,[&](uint64_t sequence,const Row &row){
      if (comma) out << ',';comma=true;out << "{\"sequence\":" << sequence;f(out,row);out << '}';
    });
    out << ']';
  }
  void serialize(std::ostream &out) const {
    using namespace witness_detail;
    const auto s=summary();
    out << "{\"schema\":\"p1-fixed-witness-v2\",\"profile\":\"closed_shadow_observation\",\"normal_contract_scope\":\"Witness records and first real accepted activation/BusinessReady consistency only; no control or phase qualification\",\"enabled\":";json_bool(out,s.enabled);
    out << ",\"closed\":";json_bool(out,s.closed);out << ",\"observation_complete\":";json_bool(out,s.observation_complete);
    out << ",\"business_ready_observed\":";json_bool(out,s.business_ready_observed);
    out << ",\"normal_contract_qualified\":";json_bool(out,s.normal_contract_qualified);
    out << ",\"overflow\":";json_bool(out,s.overflow);out << ",\"incomplete\":";json_bool(out,s.incomplete);
    out << ",\"clock_name\":\"CLOCK_MONOTONIC\",\"header\":{\"run_id\":";json_text(out,text(header_.run_id));
    out << ",\"boot_id\":";json_text(out,text(header_.boot_id));out << ",\"contract_sha256\":";json_text(out,text(header_.contract_sha256));
    out << ",\"source_sha256\":";json_text(out,text(header_.source_sha256));out << ",\"binary_sha256\":";json_text(out,text(header_.binary_sha256));
    out << ",\"worker_binary_sha256\":";json_text(out,text(header_.worker_binary_sha256));out << ",\"worker_instance\":";json_text(out,text(header_.worker_instance));
    out << "},\"capacities\":{\"tick\":256,\"submit\":128,\"activation\":128,\"phase\":32},\"counters\":{\"tick\":";stats(out,s.tick);
    out << ",\"submit\":";stats(out,s.submit);out << ",\"activation\":";stats(out,s.activation);out << ",\"phase\":";stats(out,s.phase);
    out << ",\"ticks_without_candidate\":" << s.ticks_without_candidate << ",\"accepted_activations\":" << s.accepted_activations << "},\"tick\":";
    array(out,tick_,[](std::ostream &o,const WitnessTick &r){identity(o,r);o << ",\"planned_ns\":" << r.planned_ns << ",\"start_ns\":" << r.start_ns << ",\"end_ns\":" << r.end_ns << ",\"skipped_ticks\":" << r.skipped_ticks << ",\"candidate_present\":";json_bool(o,r.candidate_present);o << ",\"failed_start\":";json_bool(o,r.failed_start);o << ",\"stopping_start\":";json_bool(o,r.stopping_start);o << ",\"failed_end\":";json_bool(o,r.failed_end);o << ",\"stopping_end\":";json_bool(o,r.stopping_end);});
    out << ",\"submit\":";array(out,submit_,[](std::ostream &o,const WitnessSubmit &r){identity(o,r);o << ",\"commit_ns\":" << r.commit_ns << ",\"failed\":";json_bool(o,r.failed);o << ",\"stopping\":";json_bool(o,r.stopping);});
    out << ",\"activation\":";array(out,activation_,[](std::ostream &o,const WitnessActivation &r){identity(o,r);o << ",\"commit_ns\":" << r.commit_ns << ",\"ready_commit_ns\":" << r.ready_commit_ns << ",\"accepted\":";json_bool(o,r.accepted);o << ",\"failed\":";json_bool(o,r.failed);o << ",\"stopping\":";json_bool(o,r.stopping);o << ",\"reason_code\":" << static_cast<unsigned>(r.reason_code);});
    out << ",\"phase\":";array(out,phase_,[](std::ostream &o,const WitnessPhase &r){o << ",\"event_code\":" << static_cast<unsigned>(r.event_code) << ",\"observation_code\":" << static_cast<unsigned>(r.observation_code) << ",\"ns\":" << r.ns << ",\"tick\":" << r.tick << ",\"job_id\":" << r.job_id << ",\"admission_slots\":" << r.admission_slots << ",\"candidate_present\":";json_state(o,r.candidate_present);o << ",\"pending_present\":";json_state(o,r.pending_present);o << ",\"failed\":";json_state(o,r.failed);o << ",\"stopping\":";json_state(o,r.stopping);o << ",\"pause_active\":";json_state(o,r.pause_active);});
    out << ",\"first_failure\":{\"code\":" << static_cast<unsigned>(s.first_failure.code)
        << ",\"stream\":" << static_cast<unsigned>(s.first_failure.stream)
        << ",\"ns\":" << s.first_failure.ns << ",\"ticket\":" << s.first_failure.ticket << "}}\n";
  }
  const bool enabled_;
  const WitnessHeader header_;
  witness_detail::FixedStream<WitnessTick,tick_capacity> tick_;
  witness_detail::FixedStream<WitnessSubmit,submit_capacity> submit_;
  witness_detail::FixedStream<WitnessActivation,activation_capacity> activation_;
  witness_detail::FixedStream<WitnessPhase,phase_capacity> phase_;
  static constexpr uint64_t closed_bit=uint64_t{1}<<63, active_mask=closed_bit-1;
  std::atomic<uint64_t> lifecycle_{0},ticks_without_candidate_{0},accepted_activations_{0};
  std::atomic<bool> failed_{false},written_{false};
  std::atomic<uint8_t> first_state_{0};
  WitnessFirstFailure first_failure_{};
};
constexpr WitnessLayout Witness::layout() noexcept {
  using TickStream=witness_detail::FixedStream<WitnessTick,tick_capacity>;
  using SubmitStream=witness_detail::FixedStream<WitnessSubmit,submit_capacity>;
  using ActivationStream=witness_detail::FixedStream<WitnessActivation,activation_capacity>;
  using PhaseStream=witness_detail::FixedStream<WitnessPhase,phase_capacity>;
  return {sizeof(WitnessHeader),sizeof(WitnessFirstFailure),
          sizeof(WitnessTick),sizeof(WitnessSubmit),sizeof(WitnessActivation),sizeof(WitnessPhase),
          TickStream::slot_bytes(),SubmitStream::slot_bytes(),ActivationStream::slot_bytes(),PhaseStream::slot_bytes(),
          sizeof(TickStream),sizeof(SubmitStream),sizeof(ActivationStream),sizeof(PhaseStream),sizeof(Witness)};
}
} // namespace p1
