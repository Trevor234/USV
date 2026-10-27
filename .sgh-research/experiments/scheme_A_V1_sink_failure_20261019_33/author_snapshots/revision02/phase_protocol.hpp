// SPDX-License-Identifier: MIT
// Diagnostic component only. No ROS, I/O, actuator calls, or stage permission.
// Call under the owner's/observer's business mutex. TransportObservation fields
// must come from actual MessageInfo plus an independently pinned pidfd; callers
// must never construct them from message payload claims. These pure comparisons
// are not a substitute for the runtime authentication adapter.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <deque>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>

namespace controlled_phase {
constexpr int64_t period_ns = 200000000;
constexpr int64_t ready_ns = 150000000;
constexpr const char *baseline = "CONTROLLED_PHASE_20261015_DIAGNOSTIC_01";
using Command = std::array<double, 2>;
using Gid = std::array<uint8_t, 16>;
inline bool finite(const Command &n) {
  return std::isfinite(n[0]) && std::isfinite(n[1]) &&
    n[0] >= -25 && n[0] <= 25 && n[1] >= -25 && n[1] <= 25;
}
inline bool hash(const std::string &s) {
  if (s.size() != 64) return false;
  for (char c : s) if (!((c >= 'a' && c <= 'f') || (c >= '0' && c <= '9'))) return false;
  return true;
}
inline bool text(const std::string &s, size_t bound) {
  if (s.empty() || s.size() > bound) return false;
  for (unsigned char c : s) if (c < 33 || c > 126) return false;
  return true;
}
struct Identity {
  std::string run, boot, contract_sha256, producer, baseline_id;
  bool valid() const {
    return text(run,128) && text(boot,64) && hash(contract_sha256) &&
      text(producer,64) && baseline_id == baseline;
  }
  bool operator==(const Identity &o) const {
    return run == o.run && boot == o.boot && contract_sha256 == o.contract_sha256 &&
      producer == o.producer && baseline_id == o.baseline_id;
  }
};
struct PeerBinding {
  Gid gid{};
  int64_t pid=0;
  uint64_t process_start_ticks=0;
  std::string manifest_sha256, binary_sha256;
  std::string run_id, boot_id, contract_sha256;
  bool valid() const {
    bool nonzero=false; for (auto b : gid) nonzero |= b != 0;
    return nonzero && pid > 0 && process_start_ticks > 0 &&
      hash(manifest_sha256) && hash(binary_sha256) && text(run_id,128) &&
      text(boot_id,64) && hash(contract_sha256);
  }
};
struct TransportObservation {
  Gid actual_gid{};
  int64_t pinned_pid=0;
  uint64_t pinned_process_start_ticks=0;
  bool registered_fastrtps=false, from_intra_process=false, pidfd_alive=false;
};
inline bool authenticated(const PeerBinding &p,const TransportObservation &o) {
  return p.valid() && o.actual_gid == p.gid && o.pinned_pid == p.pid &&
    o.pinned_process_start_ticks == p.process_start_ticks && o.registered_fastrtps &&
    !o.from_intra_process && o.pidfd_alive;
}
struct Decision {
  uint64_t sequence=0, tick=0, job_id=0;
  int64_t planned_ns=0, finished_ns=0;
  bool accepted=false, diagnostic_only=true;
  Command command{};
  std::string run_id, boot_id, contract_sha256;
};
inline bool valid_decision(const Decision &d,int64_t now) {
  return d.sequence > 0 && d.sequence < UINT64_MAX && d.tick < UINT64_MAX && d.planned_ns > 0 &&
    d.planned_ns <= std::numeric_limits<int64_t>::max()-period_ns &&
    d.finished_ns >= d.planned_ns && d.finished_ns <= now &&
    now <= d.planned_ns+ready_ns && d.diagnostic_only && finite(d.command) &&
    text(d.run_id,128) && text(d.boot_id,64) && hash(d.contract_sha256);
}
struct Pair {
  Identity identity;
  uint64_t sequence=0;
  Command command{};
  std::array<int64_t,2> start{}, end{};
  std::array<bool,2> succeeded{};
};
inline bool valid_pair(const Pair &p,int64_t now) {
  return p.identity.valid() && p.sequence > 0 && finite(p.command) &&
    p.succeeded[0] && p.succeeded[1] && p.start[0] > 0 && p.end[0] >= p.start[0] &&
    p.start[1] >= p.end[0] && p.end[1] >= p.start[1] && p.end[1] <= now;
}
struct Commitment {
  Identity identity;
  uint64_t decision_sequence=0, tick=0, applied_sequence=0;
  int64_t planned_ns=0, held_until_ns=0, emitted_ns=0;
  Command command{};
  std::array<int64_t,2> start{}, end{};
};
struct Job {
  uint64_t id=0,target_tick=0,applied_sequence=0;
  int64_t origin_ns=0,freeze_ns=0,deadline_ns=0,target_ns=0;
  Command anchor{};
};
struct Grant {Job job; Pair applied; Commitment commitment;};

// Observer side: a local completed Decision opens exactly one next phase.
// Cross-topic callbacks may arrive in either order. All Applied feedback must
// still traverse the original admission/history path; this component never
// hides a changed feedback message. Hold violations are separately observable.
class ObserverPhase {
 public:
  ObserverPhase(Identity identity,PeerBinding applied,PeerBinding phase)
    : identity_(std::move(identity)), applied_peer_(std::move(applied)), phase_peer_(std::move(phase)) {
    if (!identity_.valid() || !applied_peer_.valid() || !phase_peer_.valid() ||
        applied_peer_.pid != phase_peer_.pid ||
        applied_peer_.process_start_ticks != phase_peer_.process_start_ticks ||
        applied_peer_.manifest_sha256 != phase_peer_.manifest_sha256 ||
        applied_peer_.binary_sha256 != phase_peer_.binary_sha256 ||
        applied_peer_.gid == phase_peer_.gid) throw std::invalid_argument("owner_binding");
  }
  std::string begin(const Decision &d,int64_t now) {
    if (!valid_decision(d,now) || d.boot_id!=identity_.boot || d.contract_sha256!=identity_.contract_sha256)
      return "decision_shape_or_time";
    if (awaiting_) {
      if (!last_ || now<=last_->planned_ns+ready_ns) return "previous_phase_unfinished";
      // Expiration grants no Job and changes no time budget. The runtime records
      // this count; premeasurement startup can await the next local tick.
      ++expired_; awaiting_=false; commitment_.reset();
    }
    if (last_ && (d.sequence != last_->sequence+1 || d.tick != last_->tick+1)) return "decision_sequence";
    if (held_ && (d.tick != held_->job.target_tick || now < held_->job.target_ns)) return "decision_before_target";
    last_=d; awaiting_=true; held_.reset(); commitment_.reset(); hold_changed_=false; return {};
  }
  std::string observe_applied(const Pair &p,const TransportObservation &o,int64_t now) {
    if (!authenticated(applied_peer_,o)) return "applied_transport_authentication";
    if (!(p.identity == identity_) || !valid_pair(p,now)) return "applied_identity_or_shape";
    if (!pairs_.empty() && (p.sequence != pairs_.back().sequence+1 || p.start[0] <= pairs_.back().start[1])) return "applied_sequence_or_time";
    if (held_ && p.command != held_->applied.command) hold_changed_=true;
    pairs_.push_back(p); if (pairs_.size()>8) pairs_.pop_front(); return {};
  }
  std::string observe_commitment(const Commitment &c,const TransportObservation &o,int64_t now) {
    if (!authenticated(phase_peer_,o)) return "phase_transport_authentication";
    if (!awaiting_ || !last_) return "no_open_phase";
    if (commitment_) return "duplicate_phase";
    if (!(c.identity == identity_) || !finite(c.command) || c.applied_sequence == 0 ||
        c.decision_sequence != last_->sequence || c.tick != last_->tick || c.planned_ns != last_->planned_ns ||
        c.held_until_ns != last_->planned_ns+period_ns || c.emitted_ns < last_->finished_ns ||
        c.emitted_ns > now || now > last_->planned_ns+ready_ns || c.start[0] < last_->finished_ns ||
        c.end[0] < c.start[0] || c.start[1] < c.end[0] || c.end[1] < c.start[1] || c.end[1] > c.emitted_ns)
      return "phase_identity_shape_or_time";
    commitment_=c; return {};
  }
  std::optional<Grant> freeze(uint64_t job_id,int64_t now) {
    if (!awaiting_ || !last_ || !commitment_ || !job_id || pairs_.empty() ||
        now < commitment_->emitted_ns || now > last_->planned_ns+ready_ns) return {};
    const auto &c=*commitment_;
    auto it=std::find_if(pairs_.begin(),pairs_.end(),[&](const Pair &p){return p.sequence==c.applied_sequence;});
    if (it==pairs_.end() || it->command!=c.command || it->start!=c.start || it->end!=c.end ||
        pairs_.back().command!=c.command || pairs_.back().end[1]>now) return {};
    Job j{job_id,last_->tick+1,pairs_.back().sequence,last_->planned_ns,now,
      last_->planned_ns+ready_ns,last_->planned_ns+period_ns,pairs_.back().command};
    held_=Grant{j,pairs_.back(),c}; awaiting_=false; return held_;
  }
  bool hold_input_changed() const {return hold_changed_;}
  bool awaiting() const {return awaiting_;}
  uint64_t expired_phases() const {return expired_;}
 private:
  Identity identity_; PeerBinding applied_peer_,phase_peer_;
  std::deque<Pair> pairs_; std::optional<Decision> last_;
  std::optional<Commitment> commitment_; std::optional<Grant> held_;
  bool awaiting_=false,hold_changed_=false;
  uint64_t expired_=0;
};

// Owner side: no next value is authorized until a real, authenticated Decision
// for the current frozen target arrives. A missing Decision cannot time-release
// an actuator call. Real runtime shutdown has its own independently logged path.
class OwnerPhase {
 public:
  OwnerPhase(Identity identity,PeerBinding observer_decision,PeerBinding observer_job,bool negative_enabled=false)
    : identity_(std::move(identity)),decision_peer_(std::move(observer_decision)),job_peer_(std::move(observer_job)),negative_enabled_(negative_enabled) {
    if (!identity_.valid() || !decision_peer_.valid() || !job_peer_.valid() ||
        decision_peer_.pid!=job_peer_.pid || decision_peer_.process_start_ticks!=job_peer_.process_start_ticks ||
        decision_peer_.manifest_sha256!=job_peer_.manifest_sha256 || decision_peer_.binary_sha256!=job_peer_.binary_sha256 ||
        decision_peer_.gid==job_peer_.gid || decision_peer_.run_id!=job_peer_.run_id ||
        decision_peer_.boot_id!=job_peer_.boot_id || decision_peer_.contract_sha256!=job_peer_.contract_sha256 ||
        decision_peer_.boot_id!=identity_.boot || decision_peer_.contract_sha256!=identity_.contract_sha256)
      throw std::invalid_argument("observer_binding");
  }
  bool bootstrap_completed(const Pair &p,int64_t now) {
    if (last_ || last_pair_ || p.sequence!=1 || p.command!=Command{} ||
        !(p.identity==identity_) || !valid_pair(p,now)) return false;
    last_pair_=p; return true;
  }
  std::string observe_decision(const Decision &d,const TransportObservation &o,int64_t now) {
    if (!authenticated(decision_peer_,o)) return "decision_transport_authentication";
    if (!valid_decision(d,now) || d.run_id!=decision_peer_.run_id || d.boot_id!=decision_peer_.boot_id ||
        d.contract_sha256!=decision_peer_.contract_sha256) return "decision_shape_or_time";
    if (!last_pair_) return "bootstrap_not_completed";
    if (may_publish_) return "previous_publication_unfinished";
    if (last_ && (d.sequence!=last_->sequence+1 || d.tick!=last_->tick+1)) return "decision_sequence";
    if (job_ && (d.tick!=job_->target_tick || d.job_id!=job_->id || now<job_->target_ns)) return "decision_job_or_target";
    if (last_ && !job_) return "previous_job_unobserved";
    last_=d; may_publish_=true; job_.reset(); return {};
  }
  Command next_command() const {
    if (!may_publish_ || !last_) throw std::logic_error("no_decision_authorization");
    return last_->accepted ? last_->command : current_;
  }
  std::optional<Commitment> publication_completed(const Pair &p,int64_t now) {
    if (!may_publish_ || !last_ || !(p.identity==identity_) || !valid_pair(p,now) ||
        p.command!=next_command() || p.start[0]<last_->finished_ns || now>last_->planned_ns+ready_ns ||
        (last_pair_ && (p.sequence!=last_pair_->sequence+1 || p.start[0]<=last_pair_->start[1]))) return {};
    current_=p.command; last_pair_=p; may_publish_=false;
    return Commitment{identity_,last_->sequence,last_->tick,p.sequence,last_->planned_ns,
      last_->planned_ns+period_ns,now,p.command,p.start,p.end};
  }
  std::string observe_job(const Job &j,const TransportObservation &o,int64_t now) {
    if (!authenticated(job_peer_,o)) return "job_transport_authentication";
    if (!last_ || may_publish_ || !last_pair_ || job_) return "job_phase";
    if (!j.id || j.target_tick!=last_->tick+1 || j.origin_ns!=last_->planned_ns ||
        j.deadline_ns!=j.origin_ns+ready_ns || j.target_ns!=j.origin_ns+period_ns ||
        j.freeze_ns<last_pair_->end[1] || j.freeze_ns>now || now>j.deadline_ns ||
        j.applied_sequence!=last_pair_->sequence || j.anchor!=current_) return "job_binding_or_time";
    job_=j; return {};
  }
  bool may_publish() const {return may_publish_;}
  // Negative B has a separate explicit, logged actuator-call path. This helper
  // checks only the preregistered pulse window/rate; it grants no normal publish.
  bool claim_negative_pulse(int64_t now,const Command &pulse) {
    if (!negative_enabled_ || pulse_claimed_ || !job_ || may_publish_ || !last_pair_ || now<job_->origin_ns+100000000 ||
        now>=job_->deadline_ns || !finite(pulse)) return false;
    for (size_t ch=0;ch<2;++ch) if (pulse[ch]!=current_[ch]+0.1 || now<=last_pair_->start[ch] ||
        std::abs(pulse[ch]-current_[ch])>80.0*(now-last_pair_->start[ch])/1e9) return false;
    pulse_claimed_=true; pulse_=pulse;
    return true;
  }
  bool negative_publication_completed(const Pair &p,int64_t now) {
    if (!pulse_claimed_ || pulse_completed_ || !job_ || !last_pair_ ||
        !(p.identity==identity_) || !valid_pair(p,now) || p.command!=pulse_ ||
        p.sequence!=last_pair_->sequence+1 || p.start[0]<job_->origin_ns+100000000 ||
        p.end[1]>=job_->deadline_ns) return false;
    for(size_t ch=0;ch<2;++ch) if(p.start[ch]<=last_pair_->start[ch] ||
      std::abs(p.command[ch]-current_[ch])>80.0*(p.start[ch]-last_pair_->start[ch])/1e9) return false;
    current_=p.command; last_pair_=p; pulse_completed_=true; return true;
  }
 private:
  Identity identity_; PeerBinding decision_peer_,job_peer_;
  std::optional<Decision> last_; std::optional<Pair> last_pair_; std::optional<Job> job_;
  Command current_{},pulse_{};
  bool may_publish_=false,negative_enabled_=false,pulse_claimed_=false,pulse_completed_=false;
};
} // namespace controlled_phase
