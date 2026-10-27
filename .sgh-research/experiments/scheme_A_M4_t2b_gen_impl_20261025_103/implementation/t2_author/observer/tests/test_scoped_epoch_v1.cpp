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
  auto pa1 = w.propose(A, TS1, target(), input);
  check(pa1.valid && pa1.first, "gen1_first_proposal_valid");
  check(w.commit(pa1, JOB_A1, 123456789LL), "gen1_first_commit");
  auto pa2 = w.propose(A, TS2, target(), input);
  check(pa2.valid && !pa2.first, "gen1_second_proposal_successive");
  check(w.commit(pa2, JOB_A2, 123500000LL), "gen1_second_commit");
  check(w.generation() == 1 && w.ledger().empty() && events.empty(),
        "gen1_no_generation_events");
  // Binding change -> terminal, quiesce completed in the same section.
  w.invalidate_if_changed(B);
  check(w.terminal() && w.invalid_reason() == "epoch_binding_changed" && !w.quiesced(),
        "terminal_after_binding_change_quiesce_cleared", w.invalid_reason());
  w.mark_quiesced();
  auto pb = w.propose(B, TS3, target(), input);
  check(pb.valid && pb.first, "gen2_first_proposal_valid_after_scoped_open");
  check(w.generation() == 2 && w.ledger().size() == 1 && events.size() == 1,
        "gen2_opened_single_event");
  check(pb.anchor.binding == B, "gen2_proposal_anchor_binding_B", pb.anchor.binding.path.substr(0, 8));
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
  w.commit(w.propose(A, TS1, target(), input), JOB_A1, 1LL);
  w.invalidate_if_changed(B); w.mark_quiesced();
  w.commit(w.propose(B, TS3, target(), input), JOB_B1, 2LL);
  const auto ledger_before = w.ledger().size();
  const auto gen_before = w.generation();
  auto revived = w.propose(A, TS3 + 1000000000LL, target(), input);
  check(revived.valid == false && revived.reason == "epoch_binding_changed",
        "retired_binding_proposal_rejected", revived.reason);
  check(w.ledger().size() == ledger_before && w.generation() == gen_before && events.size() == 1,
        "no_extra_generation_or_ledger_growth");
  check(w.anchor() && w.anchor()->binding == B, "anchor_never_rolled_back");
  check(w.commit(w.propose(B, TS3 + 2000000000LL, target(), input), 6, 3LL),
        "current_generation_still_advances");
}
// E3: same-content republish of the ACTIVE binding is a normal successive
// proposal and never opens a generation.
void run_e3() {
  ScopedEpoch w(sink);
  const Binding A = make_binding('A');
  const auto input = make_input();
  w.commit(w.propose(A, TS1, target(), input), JOB_A1, 1LL);
  auto again = w.propose(A, TS2, target(), input);
  check(again.valid && !again.first, "same_binding_republish_is_successive");
  check(w.generation() == 1 && w.ledger().empty() && events.empty(),
        "same_binding_never_opens_generation");
  check(w.commit(again, JOB_A2, 2LL), "successive_commit_normal");
}
// E4: a new binding outside the frozen static domain is rejected with the
// frozen reason and completes no open (G4).
void run_e4() {
  ScopedEpoch w(sink);
  const Binding A = make_binding('A'), C = make_binding('C');
  w.commit(w.propose(A, TS1, target(), make_input()), JOB_A1, 1LL);
  w.invalidate_if_changed(C); w.mark_quiesced();
  auto bad = w.propose(C, TS1, target(), make_input(101));  // outside 201-point domain
  check(bad.valid == false && bad.reason == "static_reference_population",
        "domain_rejected_with_frozen_reason", bad.reason);
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
  w.commit(w.propose(A, TS1, target(), make_input()), JOB_A1, 1LL);
  w.invalidate_if_changed(B); w.mark_quiesced();
  auto same = w.propose(A, TS2, target(), make_input());
  check(same.valid == false && same.reason == "scoped_open_binding_not_new",
        "own_binding_reblocked_by_g3", same.reason);
  check(w.generation() == 1 && w.ledger().empty() && events.empty(), "no_open_for_own_binding");
  check(w.anchor() && w.anchor()->binding == A && w.terminal(), "old_anchor_kept_terminal");
}
// E6: terminal without the quiesce marker keeps today's no-submission
// behavior; the marker alone then authorizes the open.
void run_e6() {
  ScopedEpoch w(sink);
  const Binding A = make_binding('A'), B = make_binding('B');
  w.commit(w.propose(A, TS1, target(), make_input()), JOB_A1, 1LL);
  w.invalidate_if_changed(B);
  auto blocked = w.propose(B, TS3, target(), make_input());
  check(blocked.valid == false && blocked.reason == "scoped_open_requires_quiesce",
        "g2_blocks_without_quiesce", blocked.reason);
  check(w.generation() == 1 && events.empty(), "no_open_before_quiesce");
  w.mark_quiesced();
  auto opened = w.propose(B, TS3, target(), make_input());
  check(opened.valid && opened.first && w.generation() == 2 && events.size() == 1,
        "quiesce_marker_authorizes_open");
  check(w.commit(opened, JOB_B1, 2LL), "gen2_commit_after_g2_satisfied");
}
int main(int argc, char **argv) {
  try {
    require(argc == 3, "usage: test_scoped_epoch_v1 <case_id> <fresh_out_dir>");
    const std::string casename = argv[1];
    const std::filesystem::path out(argv[2]);
    require(!std::filesystem::exists(out), "fresh output directory required (single finite execution)");
    std::filesystem::create_directories(out);
    if (casename == "T2B-GEN-E1") run_e1();
    else if (casename == "T2B-GEN-E2") run_e2();
    else if (casename == "T2B-GEN-E3") run_e3();
    else if (casename == "T2B-GEN-E4") run_e4();
    else if (casename == "T2B-GEN-E5") run_e5();
    else if (casename == "T2B-GEN-E6") run_e6();
    else require(false, "unknown case");
    Json fixed;
    fixed["speed"] = SPEED;
    fixed["points"] = POINTS;
    fixed["ts_ns"] = {TS1, TS2, TS3};
    fixed["jobs"] = {JOB_A1, JOB_A2, JOB_B1};
    Json result = {{"schema", "T2B-GEN-component/v1"}, {"case", casename}, {"passed", all_ok},
                   {"assertions", asserts}, {"assertion_count", asserts.size()}, {"checks", checks},
                   {"generation_events", events},
                   {"policy", task_time_reference::scoped_policy},
                   {"frozen_epoch_policy", task_time_reference::epoch_policy},
                   {"fixed_parameters", fixed},
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
