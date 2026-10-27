// SPDX-License-Identifier: MIT
#pragma once
// Scoped Epoch generation wrapper (batch 102 design, option B).
//
// The frozen Epoch class is untouched: every generation is one complete,
// immutable-terminal Epoch instance. Opening the next generation swaps in a
// fresh Epoch and retires the terminal one into an append-only ledger, and
// only under the registered guards:
//   G1 current generation terminal with a recorded reason (entry condition)
//   G2 quiesce completed and marked in the same critical section that
//      performed the invalidation cleanup (Regulator invalidate_locked)
//   G3 the proposed binding differs from every binding ever anchored
//      (same-content republish never opens a generation)
//   G4 the static reference domain checks are the frozen Epoch's own: a fresh
//      Epoch evaluates the proposal and a domain failure blocks the open
//      with the original reason, leaving the terminal generation in place
//   G5 job ids strictly increase across the whole run, ledger included
//   G6 the ledger is append-only and the generation count is bounded
// Ordinary single-generation behavior is bit-identical while no open fires.
#include "task_time_profile_v1.hpp"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <vector>
namespace task_time_reference {
constexpr const char *scoped_policy = "scoped_generation_first_target_task_time_profile_v2";
struct GenerationRecord {
  uint64_t generation = 0, first_job_id = 0, last_job_id = 0;
  int64_t last_target_sim_ns = 0, terminal_ns = 0;
  std::string terminal_reason;
  Binding binding;  // default (never anchored) when the generation had no anchor
  std::optional<Anchor> anchor;
};
struct OpenInfo {
  bool opened = false;
  uint64_t generation = 0;          // new generation number when opened
  GenerationRecord previous;        // complete retired-generation record
  Binding new_binding;
  int64_t opened_ns = 0;
  std::string blocked_reason;       // empty iff opened
};
class ScopedEpoch {
 public:
  using EventSink = std::function<void(const OpenInfo &)>;
  explicit ScopedEpoch(EventSink sink = {}, uint64_t max_generations = 8)
      : sink_(std::move(sink)), max_generations_(max_generations) {}
  bool active() const { return current_.active(); }
  bool terminal() const { return current_.terminal(); }
  const std::string &invalid_reason() const { return current_.invalid_reason(); }
  const std::optional<Anchor> &anchor() const { return current_.anchor(); }
  uint64_t generation() const { return generation_; }
  const std::vector<GenerationRecord> &ledger() const { return ledger_; }
  // G2 marker: the caller sets it inside the same locked section that ran the
  // quiesce; any transition into terminal clears it, so a stale marker can
  // never authorize a later open.
  void mark_quiesced() { quiesced_ = true; }
  bool quiesced() const { return quiesced_; }
  void invalidate(const std::string &reason) {
    const bool was = terminal();
    current_.invalidate(reason);
    if (terminal() && !was) quiesced_ = false;
  }
  void invalidate_if_changed(const Binding &binding) {
    const bool was = terminal();
    current_.invalidate_if_changed(binding);
    if (terminal() && !was) quiesced_ = false;
  }
  Proposal propose(const Binding &binding, int64_t target_sim,
                   const usv_mpc::Vector6d &target, const usv_mpc::ReferenceInput &input) {
    if (current_.terminal()) {
      const OpenInfo info = try_open(binding, target_sim, target, input);
      if (!info.opened) {
        Proposal blocked;
        blocked.binding = binding;
        blocked.target_sim_ns = target_sim;
        blocked.valid = false;
        blocked.reason = info.blocked_reason;
        return blocked;
      }
    }
    return current_.propose(binding, target_sim, target, input);
  }
  bool commit(const Proposal &p, uint64_t job_id, int64_t submit_commit_ns) {
    if (p.valid && job_id <= max_job_id_) return false;  // G5, cross-generation
    if (!current_.commit(p, job_id, submit_commit_ns)) return false;
    max_job_id_ = std::max(max_job_id_, job_id);
    last_job_of_generation_ = job_id;
    last_target_of_generation_ = p.target_sim_ns;
    return true;
  }
  uint64_t max_job_id() const { return max_job_id_; }

 private:
  static int64_t steady_now_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
               std::chrono::steady_clock::now().time_since_epoch()).count();
  }
  OpenInfo try_open(const Binding &binding, int64_t target_sim,
                    const usv_mpc::Vector6d &target, const usv_mpc::ReferenceInput &input) {
    OpenInfo info;
    info.new_binding = binding;
    // G2 first: a terminal generation without a completed, marked quiesce
    // must keep today's behavior (no submission, no recovery).
    if (!quiesced_) { info.blocked_reason = "scoped_open_requires_quiesce"; return info; }
    // G3: genuine new binding, checked against the terminal current
    // generation and every retired one.
    if (current_.anchor() && current_.anchor()->binding == binding) {
      info.blocked_reason = "scoped_open_binding_not_new"; return info;
    }
    for (const auto &record : ledger_)
      if (record.anchor && record.anchor->binding == binding) {
        info.blocked_reason = "scoped_open_binding_not_new"; return info;
      }
    // G6: bounded generation churn.
    if (generation_ >= max_generations_) { info.blocked_reason = "scoped_open_generation_cap"; return info; }
    // G4: a fresh Epoch applies the frozen static-domain checks unchanged; a
    // rejection reports the frozen reason and completes no open.
    Epoch fresh;
    const Proposal probe = fresh.propose(binding, target_sim, target, input);
    if (!probe.valid) { info.blocked_reason = probe.reason; return info; }
    // Complete the open: retire the terminal generation (G6 append-only).
    GenerationRecord previous;
    previous.generation = generation_;
    previous.terminal_reason = current_.invalid_reason();
    previous.terminal_ns = steady_now_ns();
    if (current_.anchor()) {
      previous.anchor = current_.anchor();
      previous.binding = current_.anchor()->binding;
      previous.first_job_id = current_.anchor()->first_job_id;
      previous.last_job_id = last_job_of_generation_;
      previous.last_target_sim_ns = last_target_of_generation_;
    }
    ledger_.push_back(previous);
    current_ = Epoch{};
    ++generation_;
    quiesced_ = false;
    last_job_of_generation_ = 0;
    last_target_of_generation_ = 0;
    info.opened = true;
    info.generation = generation_;
    info.previous = previous;
    info.opened_ns = steady_now_ns();
    if (sink_) sink_(info);
    return info;
  }
  Epoch current_;
  std::vector<GenerationRecord> ledger_;
  uint64_t generation_ = 1, max_job_id_ = 0, last_job_of_generation_ = 0;
  int64_t last_target_of_generation_ = 0;
  uint64_t max_generations_;
  bool quiesced_ = true;  // nothing to quiesce before the first generation
  EventSink sink_;
};
}  // namespace task_time_reference
