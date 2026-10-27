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
// Batch 126 (F124-05): a Proposal must carry the identity of the wrapper state it
// was produced from, because the frozen Proposal struct has no such field and
// Epoch::commit cannot check provenance. `wrapper_generation` is the generation the
// proposal was formed against; `expected_binding` is the binding it set out to
// anchor; `serial` distinguishes two proposals with otherwise equal stamps.
//
// Consumption rule (important): the token is consumed ONLY on a successful commit.
// A proposal rejected by an existing guard (G5 job monotonicity, same-target
// ordering, terminal state) stays un-consumed and may be retried by the caller,
// exactly as the pre-126 behaviour allowed; but a proposal that was already
// committed can never be committed again, and a proposal formed against a
// superseded generation can never be committed at all.
struct ProposalToken {
  uint64_t wrapper_generation = 0;
  uint64_t serial = 0;
  Binding expected_binding;
  bool consumed = false;
};
struct ScopedProposal {
  Proposal proposal;
  ProposalToken token;
};
// Result of forming a proposal from a snapshot. `proposed_generation` records which
// wrapper generation the snapshot was taken at, so the token minted later carries
// the snapshot's identity rather than the (possibly advanced) live identity.
struct ProbeResult {
  Proposal proposal;
  uint64_t proposed_generation = 0;
};
class ScopedEpoch {
 public:
  using EventSink = std::function<void(const OpenInfo &)>;
  // Rejection counters are diagnostics; they never change the guards' behaviour.
  struct Counters {
    uint64_t proposals_minted = 0, reject_stale_generation = 0, reject_binding_mismatch = 0,
        reject_consumed = 0, reject_foreign_token = 0, commits = 0;
  };
  explicit ScopedEpoch(EventSink sink = {}, uint64_t max_generations = 8)
      : sink_(std::move(sink)), max_generations_(max_generations) {}
  bool active() const { return current_.active(); }
  bool terminal() const { return current_.terminal(); }
  const std::string &invalid_reason() const { return current_.invalid_reason(); }
  const std::optional<Anchor> &anchor() const { return current_.anchor(); }
  // Pure-snapshot accessor: callers propose on a copy of the frozen Epoch
  // exactly as before; only an epoch_terminal result re-enters the wrapper
  // under the invalidation mutex for scoped evaluation.
  const Epoch &current() const { return current_; }
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
  ProbeResult probe(const Binding &binding, int64_t target_sim,
                    const usv_mpc::Vector6d &target, const usv_mpc::ReferenceInput &input) {
    ProbeResult r;
    if (current_.terminal()) {
      const OpenInfo info = try_open(binding, target_sim, target, input);
      if (!info.opened) {
        r.proposal.binding = binding;
        r.proposal.target_sim_ns = target_sim;
        r.proposal.valid = false;
        r.proposal.reason = info.blocked_reason;
        r.proposed_generation = generation_;
        return r;
      }
    }
    r.proposal = current_.propose(binding, target_sim, target, input);
    // Recorded AFTER the propose: try_open may have advanced generation_, and the
    // proposal is only valid against the generation that exists once it returns.
    r.proposed_generation = generation_;
    return r;
  }
  // Legacy/side-effect path, unchanged in behaviour: proposes against the live
  // object. The Regulator's hot path deliberately does NOT use this (it probes a
  // copy outside the mutex), which is why both must mint a token.
  Proposal propose(const Binding &binding, int64_t target_sim,
                   const usv_mpc::Vector6d &target, const usv_mpc::ReferenceInput &input) {
    return probe(binding, target_sim, target, input).proposal;
  }
  // Mint the identity of a proposal produced from a snapshot taken while the
  // wrapper was at `proposed_generation`. Pure field work: no solver, no capsule,
  // no allocation, so it is safe to call inside the submission critical section.
  ScopedProposal mint(const Proposal &p, uint64_t proposed_generation) {
    ScopedProposal s;
    s.proposal = p;
    s.token.wrapper_generation = proposed_generation;
    s.token.serial = ++serial_;
    s.token.expected_binding = p.binding;
    s.token.consumed = false;
    ++counters_.proposals_minted;
    return s;
  }
  ScopedProposal mint(const ProbeResult &r) { return mint(r.proposal, r.proposed_generation); }
  // Token gate. Returns an empty string when the token authorizes the commit,
  // otherwise the named reason. Never mutates state.
  std::string token_rejection(const ScopedProposal &s) const {
    // MUTANT: identity gate removed
    return {};
  }
  bool commit(ScopedProposal &s, uint64_t job_id, int64_t submit_commit_ns) {
    const std::string why = token_rejection(s);
    if (!why.empty()) {
      if (why == "proposal_stale_generation") ++counters_.reject_stale_generation;
      else if (why == "proposal_consumed") ++counters_.reject_consumed;
      else ++counters_.reject_binding_mismatch;
      return false;
    }
    if (!commit(s.proposal, job_id, submit_commit_ns)) return false;
    s.token.consumed = true;          // consumed ONLY on success
    ++counters_.commits;
    return true;
  }
  // Untokened commit, kept for the existing 6 component cases and for callers that
  // never leave a single critical section. It cannot see staleness, so anything
  // crossing a lock boundary must use the ScopedProposal overload.
  bool commit(const Proposal &p, uint64_t job_id, int64_t submit_commit_ns) {
    if (p.valid && job_id <= max_job_id_) return false;  // G5, cross-generation
    if (!current_.commit(p, job_id, submit_commit_ns)) return false;
    max_job_id_ = std::max(max_job_id_, job_id);
    last_job_of_generation_ = job_id;
    last_target_of_generation_ = p.target_sim_ns;
    return true;
  }
  uint64_t max_job_id() const { return max_job_id_; }
  const Counters &counters() const { return counters_; }

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
    // The retired-ledger loop reports its own reason. Batch 126 (F124-05): sharing
    // "scoped_open_binding_not_new" with the active-generation check made the ledger
    // guard impossible to observe on its own -- deleting it still left the same
    // reason, so no test could prove it was load-bearing. Distinct reasons make each
    // guard independently falsifiable.
    for (const auto &record : ledger_)
      if (record.anchor && record.anchor->binding == binding) {
        info.blocked_reason = "scoped_open_binding_retired"; return info;
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
  uint64_t serial_ = 0;              // monotonic proposal serial, per instance
  Counters counters_;
  int64_t last_target_of_generation_ = 0;
  uint64_t max_generations_;
  bool quiesced_ = true;  // nothing to quiesce before the first generation
  EventSink sink_;
};
}  // namespace task_time_reference
