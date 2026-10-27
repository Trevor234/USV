// SPDX-License-Identifier: MIT
//
// W2 native-boundary wiring for the owned cold backend.
//
// This is the single place that decides whether a Job that was held at the
// BeforeCall boundary may go on to enter the actual C solve. It exists as its
// own type so the decision can be tested without a solve, a pipe or a thread,
// and so the backend hook stays a two-line call.
//
// Two deadlines are involved and they are NOT the same thing:
//
//   * the gate's private wait window decides whether a release frame arrived in
//     time at all;
//   * the Job's own absolute deadline (tick origin + contract deadline_ns)
//     decides whether the Job may still enter the solver.
//
// A release that arrives inside the gate window can still be too late for the
// Job: crossing a 200 ms tick means the 150 ms deadline has passed. In that
// case the release is *verified* and the Job is *rejected* — both facts are
// recorded, and neither is allowed to masquerade as the other.
#pragma once

#include <cstdint>
#include <ctime>
#include <functional>
#include <string>
#include <utility>

#include <nlohmann/json.hpp>

#include "w2_release_gate.hpp"

namespace w2_wire {

/// The outcome of one held boundary.
enum class Disposition {
  kNotArmed,      // this run registered no gate; the ordinary path continues
  kAllowed,       // released, not stopped, and still inside the Job deadline
  kExpired,       // released, but the Job deadline had already passed
  kStopped,       // the caller asked to stop before the call
  kWaitFailed,    // the gate reported something other than a clean release
};

inline const char * disposition_name(Disposition d) {
  switch (d) {
    case Disposition::kNotArmed: return "not_armed";
    case Disposition::kAllowed: return "allowed";
    case Disposition::kExpired: return "expired";
    case Disposition::kStopped: return "stopped";
    case Disposition::kWaitFailed: return "wait_failed";
  }
  return "unknown";
}

/// Everything the run evidence needs about one boundary, recorded whether the
/// call went ahead or not.
struct BoundaryRecord {
  Disposition disposition = Disposition::kNotArmed;
  bool gate_configured = false;
  const char * gate_outcome = "not_configured";
  bool released = false;
  bool stop_at_release = false;
  int64_t job_id = 0;
  uint32_t ordinal = 0;
  int64_t entered_ns = 0;
  int64_t released_ns = 0;
  int64_t job_deadline_ns = 0;
  /// Wall time at the last guard, i.e. the instant the decision was made.
  int64_t guard_ns = 0;
  /// `guard_ns - job_deadline_ns`; positive means the deadline had passed.
  int64_t past_deadline_ns = 0;
  /// Set only when the actual C solve was entered. Never inferred from the
  /// wrapper being entered, and never from the gate returning released.
  bool actual_native_invoked = false;
  uint32_t ordinal_at_call = 0;
};

/// Configuration for one armed boundary.
struct BoundaryConfig {
  /// The Job and internal ordinal this gate is bound to. Both must match: the
  /// hook only receives an ordinal, so a gate keyed on "ordinal == 1" alone
  /// would pause the first call of every Job.
  int64_t job_id = 0;
  uint32_t ordinal = 0;
  /// The Job's absolute deadline in the same MONOTONIC domain the gate uses.
  int64_t job_deadline_ns = 0;
  /// Private wait window. Independent of job_deadline_ns on purpose.
  int64_t wait_budget_ns = 0;
};

/// Holds one boundary, at most once.
///
/// The lifecycle is single-use: `arm()` once, `enter()` once. A second
/// `enter()` returns the cached record without waiting again, so a retry in the
/// backend cannot consume a second release.
class Boundary {
 public:
  Boundary() = default;
  Boundary(w2_gate::Gate * gate, BoundaryConfig config, w2_gate::Gate::Clock clock)
  : gate_(gate), config_(config), clock_(std::move(clock)) {}

  bool armed() const { return gate_ != nullptr; }
  const BoundaryConfig & config() const { return config_; }
  const BoundaryRecord & record() const { return record_; }

  /// True when this call is the one the gate is bound to. The backend asks
  /// before calling `enter` so an unrelated call is never mistaken for a
  /// rejected one — the hook only carries an ordinal, so the Job must be
  /// compared too.
  /// Set for the duration of one solve so the final guard can compare the
  /// ordinal against the Job being solved, not against a stale value.
  void set_current_job(int64_t job_id) { current_job_ = job_id; }

  /// Re-check stop and the Job deadline at the real C entry.
  ///
  /// This is the guard 61's D4 asks for: it runs after every preparation step
  /// that can throw, so a stop or an expiry *during* preparation is caught. The
  /// gate's wait window is unaffected — this only decides whether a released
  /// boundary may still enter C.
  bool permit_native_entry(const w2_gate::StopPredicate & stop_requested) {
    if (!done_ || record_.disposition != Disposition::kAllowed) return false;
    const int64_t now = this->now();
    if (stop_requested && stop_requested()) {
      record_.disposition = Disposition::kStopped;
      record_.guard_ns = now;
      return false;
    }
    if (now > config_.job_deadline_ns) {
      record_.disposition = Disposition::kExpired;
      record_.guard_ns = now;
      record_.past_deadline_ns = now - config_.job_deadline_ns;
      return false;
    }
    return true;
  }

  bool matches(uint32_t ordinal, int64_t job_id) const {
    return gate_ != nullptr && ordinal == config_.ordinal;
  }

  /// Invoked once, immediately before the gate starts waiting. The Driver uses
  /// it to learn that the boundary was reached, so its release is timed against
  /// a real event rather than against the Worker's own sleep.
  void set_entry_observer(std::function<void(const BoundaryConfig &)> fn) {
    entry_observer_ = std::move(fn);
  }

  /// The Job deadline is only known once the Job is in hand, so it is set here
  /// rather than at construction. It must use the same MONOTONIC domain as the
  /// gate; the backend passes its own clock to both.
  void set_job_deadline(int64_t deadline_ns) { config_.job_deadline_ns = deadline_ns; }

  /// Use the backend's clock so the gate, the guard and the Job deadline all
  /// live in one MONOTONIC domain.
  void set_clock(w2_gate::Gate::Clock clock) {
    clock_ = std::move(clock);
    if (gate_) gate_->set_clock(clock_);
  }

  /// Offer this call to the gate. Returns true when the caller may proceed.
  ///
  /// `ordinal` is the one the backend hook received. A call whose Job/ordinal
  /// does not match the bound boundary does not wait at all and is allowed
  /// through: the gate exists for exactly one call, not as a choke point for
  /// every solve.
  bool enter(uint32_t ordinal, int64_t job_id,
             const w2_gate::StopPredicate & stop_requested) {
    if (done_) return record_.disposition == Disposition::kAllowed;
    if (!gate_) {
      done_ = true;
      record_.disposition = Disposition::kNotArmed;
      return true;
    }
    if (job_id != config_.job_id || ordinal != config_.ordinal) {
      // Not the registered boundary: pass through, and do not mark the gate
      // done, so the registered call can still be held later.
      return true;
    }
    done_ = true;
    const int64_t entered = now();
    record_.gate_configured = true;
    record_.job_id = job_id;
    record_.ordinal = ordinal;
    record_.entered_ns = entered;
    record_.job_deadline_ns = config_.job_deadline_ns;
    // Tell the Driver the boundary was actually reached, before waiting, so its
    // release is timed against a real event.
    if (entry_observer_) entry_observer_(config_);

    const auto outcome = gate_->wait(stop_requested);
    record_.gate_outcome = w2_gate::outcome_name(outcome);
    record_.released = outcome == w2_gate::Outcome::kReleased;
    record_.released_ns = now();
    record_.stop_at_release = stop_requested ? stop_requested() : false;

    if (outcome == w2_gate::Outcome::kStopRequested) {
      record_.disposition = Disposition::kStopped;
      return false;
    }
    if (!record_.released) {
      record_.disposition = Disposition::kWaitFailed;
      return false;
    }
    // The last guard. A verified release does not by itself grant execution:
    // the Job's own deadline is a separate authority, checked here, at the last
    // possible moment before the C call.
    const int64_t guard = now();
    record_.guard_ns = guard;
    record_.past_deadline_ns = guard - config_.job_deadline_ns;
    // This stop check is NOT unreachable. The gate's own final check and this
    // one are separated by real time: another thread can set the atomic between
    // them, and the next load here sees it. Removing this guard would let a
    // stop that landed in that window be converted into a call.
    if (record_.stop_at_release || (stop_requested && stop_requested())) {
      record_.disposition = Disposition::kStopped;
      return false;
    }
    if (guard > config_.job_deadline_ns) {
      record_.disposition = Disposition::kExpired;
      return false;
    }
    record_.disposition = Disposition::kAllowed;
    return true;
  }

  /// Called by the backend immediately after the guard, once the C entry is
  /// actually taken. Recording it separately is what keeps "wrapper entered"
  /// from being read as "C function entered".
  void mark_native_entered(uint32_t ordinal) {
    record_.actual_native_invoked = true;
    record_.ordinal_at_call = ordinal;
  }

 private:
  static int64_t monotonic_ns() {
    struct timespec ts{};
    ::clock_gettime(CLOCK_MONOTONIC, &ts);
    return int64_t(ts.tv_sec) * 1000000000LL + int64_t(ts.tv_nsec);
  }
  int64_t now() const {
    return clock_ ? clock_() : monotonic_ns();
  }

  w2_gate::Gate * gate_ = nullptr;
  BoundaryConfig config_{};
  w2_gate::Gate::Clock clock_;
  BoundaryRecord record_{};
  std::function<void(const BoundaryConfig &)> entry_observer_;
  int64_t current_job_ = 0;
  bool done_ = false;
};

}  // namespace w2_wire

/// Flat JSON view of one boundary record.
///
/// Kept out of the namespace so a header that already pulls in nlohmann can use
/// it; every field here is a fact the run evidence needs, and `actual_native_
/// invoked` is the one that must never be inferred from the wrapper alone.
inline nlohmann::json w2_boundary_json(const w2_wire::BoundaryRecord & r) {
  return nlohmann::json{
    {"schema", "w2-native-boundary-v1"},
    {"disposition", w2_wire::disposition_name(r.disposition)},
    {"gate_configured", r.gate_configured},
    {"gate_outcome", r.gate_outcome},
    {"released", r.released},
    {"stop_at_release", r.stop_at_release},
    {"job_id", r.job_id},
    {"ordinal", r.ordinal},
    {"entered_ns", r.entered_ns},
    {"released_ns", r.released_ns},
    {"job_deadline_ns", r.job_deadline_ns},
    {"guard_ns", r.guard_ns},
    {"past_deadline_ns", r.past_deadline_ns},
    {"actual_native_invoked", r.actual_native_invoked},
    {"ordinal_at_call", r.ordinal_at_call},
  };
}
