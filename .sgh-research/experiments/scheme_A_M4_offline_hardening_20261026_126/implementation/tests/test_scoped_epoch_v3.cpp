// SPDX-License-Identifier: MIT
// T2B-GEN Stage 1 component harness (batch 102 design, batch 103 run).
// Compiles the frozen task_time_profile_v1.hpp Epoch plus the new
// scoped_epoch_v1.hpp wrapper. No ROS context, no actuator endpoints, no
// owned claim (R74-07: component verification only). One registered case per
// invocation; result.json carries per-assertion evidence.
#include "scoped_epoch_v1.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
#include <string>
#include <vector>
using task_time_reference::Binding;
using task_time_reference::ScopedEpoch;
using Json = nlohmann::json;
// Registration-fixed parameters (registration must carry identical values).
constexpr double SPEED = .05;
constexpr int POINTS = 201;
constexpr int64_t TS1 = 1000000000LL, TS2 = 2000000000LL, TS3 = 3000000000LL;
constexpr uint64_t JOB_A1 = 1, JOB_A2 = 2, JOB_B1 = 5;
int checks = 0; Json asserts = Json::array(); bool all_ok = true;
void check(bool v, const std::string &name, const Json &observed = Json(nullptr)) {
  ++checks; if (!v) all_ok = false;
  asserts.push_back({{"name", name}, {"passed", v}, {"observed", observed}});
}
void require(bool v, const char *why) { ++checks; if (!v) throw std::runtime_error(why); }
std::string fingerprint(char tag) { return std::string(64, tag); }
Binding make_binding(char tag) {
  Binding b;
  b.version = {1, 1, 1, 1, 1};
  b.run = "T2B-GEN-COMP"; b.boot = "boot-identity";
  b.contract = std::string(64, 'c'); b.nominal = std::string(64, 'n');
  b.path = fingerprint(tag); b.profile = fingerprint(tag);
  return b;
}
usv_mpc::ReferenceInput make_input(int points = POINTS) {
  usv_mpc::ReferenceInput input;
  input.path_stamp = {1, 1}; input.profile_stamp = {1, 1};
  for (int i = 0; i < points; ++i) {
    input.path.push_back({SPEED * (.2 * i), 0., 0.});
    input.profile.push_back({SPEED, 0., 0., .2 * i});
  }
  return input;
}
usv_mpc::Vector6d target() { return usv_mpc::Vector6d{1.0, 0., 0., 0., 0., 0.}; }
Json events = Json::array();  // generation_opened records from the sink
ScopedEpoch::EventSink sink = [](const task_time_reference::OpenInfo &info) {
  events.push_back({{"policy", task_time_reference::scoped_policy}, {"opened", info.opened},
                    {"generation", info.generation}, {"previous_generation", info.previous.generation},
                    {"previous_terminal_reason", info.previous.terminal_reason},
                    {"previous_first_job_id", info.previous.first_job_id},
                    {"previous_last_job_id", info.previous.last_job_id},
                    {"previous_last_target_sim_ns", info.previous.last_target_sim_ns},
                    {"new_binding_path_fingerprint_head", info.new_binding.path.substr(0, 8)},
                    {"ledger_size_after", 0}});
};
// E1: full positive control — gen1 anchored and committed, binding change to
// terminal, old-object epoch_terminal baseline, quiesced scoped open of gen2,
// cross-generation job monotonicity, complete ledger.
void run_e1() {
  // Batch-74 offline proof replicated inside this binary: a plain frozen
  // Epoch that went terminal rejects the new binding with epoch_terminal.
  task_time_reference::Epoch plain;
  const Binding A = make_binding('A'), B = make_binding('B');
  const auto input = make_input();
  auto pa0 = plain.propose(A, TS1, target(), input);
  require(plain.commit(pa0, JOB_A1, 123456789LL), "plain baseline commit");
  plain.invalidate_if_changed(B);
  auto plain_blocked = plain.propose(B, TS2, target(), input);
  check(plain_blocked.valid == false && plain_blocked.reason == "epoch_terminal",
        "frozen_epoch_terminal_after_binding_change", plain_blocked.reason);
  // Scoped wrapper, generation 1.
  ScopedEpoch w(sink);
  auto pa1 = w.mint(w.probe(A, TS1, target(), input));
  check(pa1.proposal.valid && pa1.proposal.first, "gen1_first_proposal_valid");
  check(w.commit(pa1, JOB_A1, 123456789LL), "gen1_first_commit");
  auto pa2 = w.mint(w.probe(A, TS2, target(), input));
  check(pa2.proposal.valid && !pa2.proposal.first, "gen1_second_proposal_successive");
  check(w.commit(pa2, JOB_A2, 123500000LL), "gen1_second_commit");
  check(w.generation() == 1 && w.ledger().empty() && events.empty(),
        "gen1_no_generation_events");
  // Binding change -> terminal, quiesce completed in the same section.
  w.invalidate_if_changed(B);
  check(w.terminal() && w.invalid_reason() == "epoch_binding_changed" && !w.quiesced(),
        "terminal_after_binding_change_quiesce_cleared", w.invalid_reason());
  w.mark_quiesced();
  auto pb = w.mint(w.probe(B, TS3, target(), input));
  check(pb.proposal.valid && pb.proposal.first, "gen2_first_proposal_valid_after_scoped_open");
  check(w.generation() == 2 && w.ledger().size() == 1 && events.size() == 1,
        "gen2_opened_single_event");
  check(pb.proposal.anchor.binding == B, "gen2_proposal_anchor_binding_B", pb.proposal.anchor.binding.path.substr(0, 8));
  check(w.commit(pb, JOB_A2, 123600000LL) == false,
        "g5_cross_generation_job_monotonicity_enforced",
        {{"rejected_job_id", JOB_A2}, {"max_job_id", w.max_job_id()}});
  check(w.commit(pb, JOB_B1, 123700000LL), "gen2_first_commit_job5");
  check(w.anchor() && w.anchor()->binding == B && w.anchor()->first_job_id == JOB_B1,
        "gen2_anchor_after_commit");
  const auto &rec = w.ledger().front();
  check(rec.generation == 1 && rec.terminal_reason == "epoch_binding_changed"
        && rec.first_job_id == JOB_A1 && rec.last_job_id == JOB_A2
        && rec.last_target_sim_ns == TS2 && rec.anchor && rec.anchor->binding == A,
        "ledger_generation1_record_complete",
        {{"generation", rec.generation}, {"first", rec.first_job_id}, {"last", rec.last_job_id},
         {"reason", rec.terminal_reason}, {"last_target_sim_ns", rec.last_target_sim_ns}});
  check(w.active() && !w.terminal(), "gen2_active_not_terminal");
}
// E2: revival negative — after gen2 opened, the retired gen1 binding can
// never anchor again and the ledger never shrinks or rewrites.
void run_e2() {
  ScopedEpoch w(sink);
  const Binding A = make_binding('A'), B = make_binding('B');
  const auto input = make_input();
  w.commit(w.mint(w.probe(A, TS1, target(), input)), JOB_A1, 1LL);
  w.invalidate_if_changed(B); w.mark_quiesced();
  w.commit(w.mint(w.probe(B, TS3, target(), input)), JOB_B1, 2LL);
  const auto ledger_before = w.ledger().size();
  const auto gen_before = w.generation();
  auto revived = w.mint(w.probe(A, TS3 + 1000000000LL, target(), input));
  check(revived.proposal.valid == false && revived.proposal.reason == "epoch_binding_changed",
        "retired_binding_proposal_rejected", revived.proposal.reason);
  check(w.ledger().size() == ledger_before && w.generation() == gen_before && events.size() == 1,
        "no_extra_generation_or_ledger_growth");
  check(w.anchor() && w.anchor()->binding == B, "anchor_never_rolled_back");
  check(w.commit(w.mint(w.probe(B, TS3 + 2000000000LL, target(), input)), 6, 3LL),
        "current_generation_still_advances");
}
// E3: same-content republish of the ACTIVE binding is a normal successive
// proposal and never opens a generation.
void run_e3() {
  ScopedEpoch w(sink);
  const Binding A = make_binding('A');
  const auto input = make_input();
  w.commit(w.mint(w.probe(A, TS1, target(), input)), JOB_A1, 1LL);
  auto again = w.mint(w.probe(A, TS2, target(), input));
  check(again.proposal.valid && !again.proposal.first, "same_binding_republish_is_successive");
  check(w.generation() == 1 && w.ledger().empty() && events.empty(),
        "same_binding_never_opens_generation");
  check(w.commit(again, JOB_A2, 2LL), "successive_commit_normal");
}
// E4: a new binding outside the frozen static domain is rejected with the
// frozen reason and completes no open (G4).
void run_e4() {
  ScopedEpoch w(sink);
  const Binding A = make_binding('A'), C = make_binding('C');
  w.commit(w.mint(w.probe(A, TS1, target(), make_input())), JOB_A1, 1LL);
  w.invalidate_if_changed(C); w.mark_quiesced();
  auto bad = w.mint(w.probe(C, TS1, target(), make_input(101)));  // outside 201-point domain
  check(bad.proposal.valid == false && bad.proposal.reason == "static_reference_population",
        "domain_rejected_with_frozen_reason", bad.proposal.reason);
  check(w.generation() == 1 && w.ledger().empty() && events.empty(),
        "no_open_completed_on_domain_failure");
  check(w.terminal() && w.invalid_reason() == "epoch_binding_changed",
        "terminal_generation_unchanged_after_domain_failure");
}
// E5: a terminal generation quiesced, proposed with its OWN binding again:
// blocked (G3), never a resurrection of the current anchor.
void run_e5() {
  ScopedEpoch w(sink);
  const Binding A = make_binding('A'), B = make_binding('B');
  w.commit(w.mint(w.probe(A, TS1, target(), make_input())), JOB_A1, 1LL);
  w.invalidate_if_changed(B); w.mark_quiesced();
  auto same = w.mint(w.probe(A, TS2, target(), make_input()));
  check(same.proposal.valid == false && same.proposal.reason == "scoped_open_binding_not_new",
        "own_binding_reblocked_by_g3", same.proposal.reason);
  check(w.generation() == 1 && w.ledger().empty() && events.empty(), "no_open_for_own_binding");
  check(w.anchor() && w.anchor()->binding == A && w.terminal(), "old_anchor_kept_terminal");
}
// E6: terminal without the quiesce marker keeps today's no-submission
// behavior; the marker alone then authorizes the open.
void run_e6() {
  ScopedEpoch w(sink);
  const Binding A = make_binding('A'), B = make_binding('B');
  w.commit(w.mint(w.probe(A, TS1, target(), make_input())), JOB_A1, 1LL);
  w.invalidate_if_changed(B);
  auto blocked = w.mint(w.probe(B, TS3, target(), make_input()));
  check(blocked.proposal.valid == false && blocked.proposal.reason == "scoped_open_requires_quiesce",
        "g2_blocks_without_quiesce", blocked.proposal.reason);
  check(w.generation() == 1 && events.empty(), "no_open_before_quiesce");
  w.mark_quiesced();
  auto opened = w.mint(w.probe(B, TS3, target(), make_input()));
  check(opened.proposal.valid && opened.proposal.first && w.generation() == 2 && events.size() == 1,
        "quiesce_marker_authorizes_open");
  check(w.commit(opened, JOB_B1, 2LL), "gen2_commit_after_g2_satisfied");
}
// ============================ batch 126 (F124-05) ============================
// The six cases above are the batch-103 semantics, unchanged. The cases below add
// the Proposal identity the wrapper never had: a proposal formed against a
// superseded generation, or already committed, can no longer take effect.
//
// E7: retired-A replay. A is committed, A is retired by B's open, B is proposed but
// NOT yet committed (generation 2). Replaying A's still-uncommitted proposal must be
// refused for generation staleness, and B must still commit normally.
void run_e7() {
  ScopedEpoch w(sink);
  const Binding A = make_binding('A'), B = make_binding('B');
  const auto input = make_input();
  auto a = w.mint(w.probe(A, TS1, target(), input));
  check(w.commit(a, JOB_A1, 1LL), "e7_gen1_commit_A");
  w.invalidate_if_changed(B); w.mark_quiesced();
  auto b = w.mint(w.probe(B, TS3, target(), input));
  check(w.generation() == 2 && b.token.wrapper_generation == 2, "e7_gen2_open_minted_at_generation_2",
        {{"wrapper_generation", b.token.wrapper_generation}});
  const uint64_t gen_before = w.generation(), maxjob_before = w.max_job_id();
  const size_t ledger_before = w.ledger().size();
  // A token minted against generation 1: simulate the stale replay by rewinding the
  // token's recorded generation (the only way a caller could still hold one).
  auto stale = a;
  stale.token.wrapper_generation = 1;
  const bool stale_ok = w.commit(stale, 100, 2LL);
  check(!stale_ok && w.token_rejection(stale) == "proposal_stale_generation",
        "e7_stale_generation_replay_rejected", w.token_rejection(stale));
  // A scoped open installs a FRESH epoch, so generation 2 is unanchored until its
  // first commit; generation 1's anchor survives only inside the ledger record.
  // The failed replay must not have anchored generation 2 or touched either.
  check(w.generation() == gen_before && w.max_job_id() == maxjob_before
        && w.ledger().size() == ledger_before && !w.anchor()
        && w.ledger().front().anchor && w.ledger().front().anchor->binding == A,
        "e7_rejected_replay_left_state_unchanged",
        {{"generation", w.generation()}, {"max_job_id", w.max_job_id()},
         {"ledger", w.ledger().size()}, {"generation_2_anchored", w.anchor() != std::nullopt},
         {"ledger_holds_A", w.ledger().front().anchor
                            && w.ledger().front().anchor->binding == A}});
  check(w.counters().reject_stale_generation == 1, "e7_stale_counter_recorded",
        w.counters().reject_stale_generation);
  check(w.commit(b, JOB_B1, 3LL), "e7_fresh_B_still_commits");
  check(w.anchor() && w.anchor()->binding == B, "e7_anchor_is_B");
}
// E8: the same proposal cannot commit twice, even with a larger job id.
void run_e8() {
  ScopedEpoch w(sink);
  const Binding A = make_binding('A');
  const auto input = make_input();
  auto a = w.mint(w.probe(A, TS1, target(), input));
  check(w.commit(a, JOB_A1, 1LL), "e8_first_commit");
  check(a.token.consumed, "e8_token_consumed_on_success");
  const uint64_t maxjob = w.max_job_id();
  const bool again = w.commit(a, 900, 2LL);
  check(!again && w.token_rejection(a) == "proposal_consumed",
        "e8_duplicate_commit_rejected", w.token_rejection(a));
  check(w.max_job_id() == maxjob && w.counters().reject_consumed == 1,
        "e8_state_unchanged_and_counter", {{"max_job_id", w.max_job_id()}});
}
// E9: a proposal that a pre-existing guard rejected stays retryable — consumption
// happens only on success. This is the batch-103 behaviour that must NOT regress.
void run_e9() {
  ScopedEpoch w(sink);
  const Binding A = make_binding('A'), B = make_binding('B');
  const auto input = make_input();
  auto p1 = w.mint(w.probe(A, TS1, target(), input));
  w.commit(p1, JOB_A1, 1LL);
  auto p2 = w.mint(w.probe(A, TS2, target(), input));
  w.commit(p2, JOB_A2, 2LL);
  w.invalidate_if_changed(B); w.mark_quiesced();
  auto b = w.mint(w.probe(B, TS3, target(), input));
  const bool g5_blocked = w.commit(b, JOB_A2, 3LL);      // G5: job id not increasing
  check(!g5_blocked && !b.token.consumed, "e9_g5_failure_does_not_consume_token");
  check(w.token_rejection(b).empty(), "e9_token_still_authorizes", w.token_rejection(b));
  check(w.commit(b, JOB_B1, 4LL), "e9_retry_with_valid_job_succeeds");
  check(b.token.consumed, "e9_consumed_after_success");
}
// E10: the full retired-binding attempt. After A -> B is committed, a token whose
// recorded generation and binding both point back at A must be refused.
void run_e10() {
  ScopedEpoch w(sink); const auto input=make_input();
  const auto A=make_binding('A'), B=make_binding('B');
  auto a=w.mint(w.probe(A,TS1,target(),input)); require(w.commit(a,1,1),"A commit");
  w.invalidate_if_changed(B);w.mark_quiesced();
  auto b=w.mint(w.probe(B,TS3,target(),input));require(w.commit(b,5,2),"B commit");
  check(!w.commit(a,500,3),"e10_retired_A_commit_refused");
  auto next=w.mint(w.probe(B,TS3+1000000000LL,target(),input));
  auto mismatched=next;mismatched.token.expected_binding=A;
  check(w.token_rejection(mismatched)=="proposal_token_binding_mismatch","e10_binding_mismatch_gate");
  auto copy=next;require(w.commit(next,6,4),"next commit");
  copy.token.consumed=false;copy.proposal.target_sim_ns+=1;
  check(w.token_rejection(copy)=="proposal_consumed","e10_copied_consumed_credential_rejected");
  check(!w.commit(copy,7,5)&&w.max_job_id()==6,"e10_copied_credential_cannot_advance_state");
  check(w.anchor()&&w.anchor()->binding==B&&w.generation()==2,"e10_state_unchanged_by_all_refusals");
}
// E11: legal new binding that differs only in schedule — the doc requires this to be
// allowed, so the identity gate must not demand a path/profile change.
void run_e11() {
  ScopedEpoch w(sink);
  Binding A = make_binding('A');
  Binding B = make_binding('A');          // same path/profile fingerprint
  B.version = {1, 1, 1, 2, 1};            // schedule_generation 1 -> 2 only
  check(!(A == B) && B.path == A.path && B.profile == A.profile,
        "e11_bindings_differ_only_by_schedule");
  const auto input = make_input();
  auto p0 = w.mint(w.probe(A, TS1, target(), input));
  w.commit(p0, JOB_A1, 1LL);
  w.invalidate_if_changed(B); w.mark_quiesced();
  auto b = w.mint(w.probe(B, TS3, target(), input));
  check(b.proposal.valid && w.generation() == 2, "e11_schedule_only_change_opens_generation",
        {{"generation", w.generation()}, {"reason", b.proposal.reason}});
  check(w.commit(b, JOB_B1, 2LL), "e11_new_schedule_commits");
  check(w.max_job_id() == JOB_B1, "e11_job_monotonic_kept");
}
// E12: the RETIRED-LEDGER guard on its own. After A -> B is committed, the live
// generation is B and anchored, so the active-anchor check cannot fire for A. Only
// the retired-ledger loop can refuse A. This is the case that makes deleting that
// loop observable (EPV-MUT-LEDGER); batch 105 had no such case, which is why the
// mutation survived 32/32.
void run_e12() {
  ScopedEpoch w(sink);
  const Binding A = make_binding('A'), B = make_binding('B');
  const auto input = make_input();
  auto a = w.mint(w.probe(A, TS1, target(), input));
  w.commit(a, JOB_A1, 1LL);
  w.invalidate_if_changed(B); w.mark_quiesced();
  auto b = w.mint(w.probe(B, TS3, target(), input));
  check(w.commit(b, JOB_B1, 2LL), "e12_gen2_commit_B");
  check(w.anchor() && w.anchor()->binding == B && w.ledger().size() == 1,
        "e12_live_generation_is_B_and_A_is_retired");
  // Force a terminal state on B so try_open is reachable, then ask for A again.
  w.invalidate_if_changed(A); w.mark_quiesced();
  check(w.terminal() && w.generation() == 2, "e12_generation_2_terminal_and_quiesced",
        {{"terminal", w.terminal()}, {"generation", w.generation()}});
  auto revived = w.probe(A, TS3 + 1000000000LL, target(), input);
  check(!revived.proposal.valid, "e12_retired_A_refused");
  check(revived.proposal.reason == "scoped_open_binding_retired",
        "e12_refusal_is_the_retired_ledger_reason", revived.proposal.reason);
  check(w.ledger().size() == 1 && w.generation() == 2 && w.anchor()->binding == B,
        "e12_no_state_change_from_the_ledger_refusal",
        {{"ledger", w.ledger().size()}, {"generation", w.generation()}});
}
// E13: two fresh wrappers have the same generation/serial but distinct owners.
void run_e13(){
  ScopedEpoch a,b;auto p=a.mint(a.probe(make_binding('A'),TS1,target(),make_input()));
  auto own=b.mint(b.probe(make_binding('A'),TS1,target(),make_input()));
  check(!b.commit(p,1,1),"foreign_instance_rejected");
  check(!b.active()&&b.max_job_id()==0&&b.ledger().empty(),"foreign_no_state_change");
  check(a.commit(p,1,1),"issuing_instance_still_accepts");
  check(b.commit(own,1,1),"recipient_own_credential_still_accepts");
}
void run_e14(){
  ScopedEpoch w;auto p=w.mint(w.probe(make_binding('A'),TS1,target(),make_input()));
  auto forged=p;++forged.token.serial;
  check(!w.commit(forged,1,1),"unissued_serial_rejected");
  auto changed=p;changed.proposal.target_sim_ns+=1;
  check(!w.commit(changed,1,1),"payload_not_the_issued_proposal");
  check(!w.active()&&w.max_job_id()==0,"forgeries_do_not_anchor");
  check(w.commit(p,1,1),"original_credential_survives_invalid_attempts");
}
// E15: mirrors the real Regulator's copy-out, compute, lock-in, mint, commit path.
void run_e15(){
  ScopedEpoch w;const auto A=make_binding('A'),B=make_binding('B');const auto input=make_input();
  const auto old_identity=w.snapshot_identity();auto snapshot=w.current();
  auto tentative=snapshot.propose(A,TS1,target(),input);
  auto a=w.mint(w.probe(A,TS1,target(),input));require(w.commit(a,1,1),"A anchor");
  w.invalidate_if_changed(B);w.mark_quiesced();auto b=w.mint(w.probe(B,TS3,target(),input));
  auto stale=w.mint(std::move(tentative),old_identity);
  check(!w.commit(stale,9,2),"cross_lock_snapshot_stale_rejected");
  check(w.generation()==2&&!w.anchor()&&w.max_job_id()==1,"stale_snapshot_cannot_anchor_new_generation");
  check(w.commit(b,5,3),"new_generation_credential_not_displaced_by_stale_mint");
}
int main(int argc, char **argv) {
  try {
    require(argc == 3, "usage: test_scoped_epoch_v2 <case_id> <fresh_out_dir>");
    const std::string casename = argv[1];
    const std::filesystem::path out(argv[2]);
    require(!std::filesystem::exists(out), "fresh output directory required (single finite execution)");
    std::filesystem::create_directories(out);
    if (casename == "EPV-E1") run_e1();
    else if (casename == "EPV-E2") run_e2();
    else if (casename == "EPV-E3") run_e3();
    else if (casename == "EPV-E4") run_e4();
    else if (casename == "EPV-E5") run_e5();
    else if (casename == "EPV-E6") run_e6();
    else if (casename == "EPV-REPLAY-A") run_e7();
    else if (casename == "EPV-DUP-COMMIT") run_e8();
    else if (casename == "EPV-G5-RETRY") run_e9();
    else if (casename == "EPV-RETIRED-BINDING-V3") run_e10();
    else if (casename == "EPV-LEGAL-NEW-SCHEDULE") run_e11();
    else if (casename == "EPV-RETIRED-LEDGER") run_e12();
    else if (casename == "EPV-FOREIGN") run_e13();
    else if (casename == "EPV-SERIAL") run_e14();
    else if (casename == "EPV-SNAPSHOT") run_e15();
    else require(false, "unknown case");
    Json fixed;
    fixed["speed"] = SPEED;
    fixed["points"] = POINTS;
    fixed["ts_ns"] = {TS1, TS2, TS3};
    fixed["jobs"] = {JOB_A1, JOB_A2, JOB_B1};
    Json result = {{"schema", "T2B-GEN-component/v2"}, {"case", casename}, {"passed", all_ok},
                   {"assertions", asserts}, {"assertion_count", asserts.size()}, {"checks", checks},
                   {"generation_events", events},
                   {"policy", task_time_reference::scoped_policy},
                   {"frozen_epoch_policy", task_time_reference::epoch_policy},
                   {"fixed_parameters", fixed},
                   {"proposal_identity", "wrapper_generation+serial+expected_binding, consumed on success only"},
                   {"ROS_context_created", false}, {"actuator_endpoints_created", false},
                   {"stage_qualified", false}, {"execute_qualified", false}, {"research_conclusion", false}};
    std::ofstream f(out / "result.json");
    f << result.dump(2) << '\n';
    require(bool(f), "evidence stream");
    std::cout << "case=" << casename << " passed=" << (all_ok ? "true" : "false")
              << " assertions=" << asserts.size() << '\n';
    return all_ok ? 0 : 2;
  } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 2; }
}
