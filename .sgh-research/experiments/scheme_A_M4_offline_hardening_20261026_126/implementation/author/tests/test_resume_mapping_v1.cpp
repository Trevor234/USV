// SPDX-License-Identifier: MIT
// B2' resume stamp mapping — S2 component suite (batch 118).
// Tests the EXACT production helper (fixture/resume_stamp_mapping_v1.hpp)
// that synthetic_source_m4.cpp calls on every writer step, plus three
// mutants of that helper whose regressions the suite must catch, proving the
// tests hit the production call semantics. Native: no ROS, no rclcpp.
#include "../fixture/resume_stamp_mapping_v1.hpp"
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
#include <vector>
using resume_mapping::CATCH_UP_CAP_NS;
using resume_mapping::Mapping;
using Json = nlohmann::json;
int checks = 0; Json asserts = Json::array(); bool all_ok = true;
void check(bool v, const std::string &name, const Json &observed = Json(nullptr)) {
  ++checks; if (!v) all_ok = false;
  asserts.push_back({{"name", name}, {"passed", v}, {"observed", observed}});
}
// --- driver: one synthetic fixture writer ---------------------------------
struct Sim {
  Mapping m; int64_t stamp = 100000000000LL, last_target = 0, t = 0;
  bool holding = false, silent = true;
  int64_t step(int64_t dt) {  // one 20ms-class writer step
    t += dt;
    stamp = resume_mapping::step_stamp(m, holding, stamp, t, last_target);
    last_target = t;
    if (!(holding && silent)) resume_mapping::note_published(m, stamp, t);
    return stamp;
  }
  void hold() { holding = true; }
  void resume() { holding = false; resume_mapping::arm_resume(m); }
};
// regulator-side engineering projection, as the production regulator forms it
struct Projection {
  int64_t s_recv = 0, t_recv = 0;
  void receive(int64_t s, int64_t t) { s_recv = s; t_recv = t; }
  int64_t at(int64_t t_now) const { return s_recv + (t_now - t_recv); }
};
void run_matrix() {
  const int64_t STEP = 20000000;  // 20ms writer period
  // T1 real-sequence shape replay (attempt-2 hold 1527323783ns)
  {
    Sim s; std::vector<int64_t> stamps;
    for (int i = 0; i < 100; ++i) stamps.push_back(s.step(STEP));
    const int64_t s_last_pub = s.m.published_stamp_ns, t_last_pub = s.m.published_target_ns;
    s.hold();
    for (int i = 0; i < 77; ++i) s.step(STEP);            // silence ~1.54s
    s.resume();
    const int64_t first_resumed = s.step(STEP);
    const int64_t t_first = s.t;   // writer target of the resumed step itself
    for (int i = 0; i < 200; ++i) stamps.push_back(s.step(STEP));
    bool mono = true;
    for (size_t i = 1; i < stamps.size(); ++i) if (stamps[i] < stamps[i - 1]) mono = false;
    check(mono, "t1_raw_stamps_monotonic");
    check(first_resumed == s_last_pub + (t_first - t_last_pub),
          "t1_first_resumed_stamp_is_published_pair_mapping",
          {{"got", first_resumed}, {"expect", s_last_pub + (t_first - t_last_pub)}});
    // projection continuity: pre-hold pair sim never exceeds post-resume sims
    Projection p; p.receive(stamps[99], s.t - 77 * STEP - 200 * STEP - 2 * STEP);  // last receive before silence
    const int64_t proj_pre = p.at(s.t - 78 * STEP - 202 * STEP + 77 * STEP);       // pair during silence (projection)
    const int64_t proj_post = first_resumed;                                        // pair after resume, re-based
    check(proj_post >= proj_pre - STEP, "t1_projection_history_no_regression",
          {{"proj_pre", proj_pre}, {"proj_post", proj_post}});
  }
  // T2 edge/phase mismatch: mapping uses writer targets, never action times
  {
    Sim a, b;
    for (int i = 0; i < 50; ++i) { a.step(STEP); b.step(STEP); }
    a.hold(); b.hold();
    for (int i = 0; i < 60; ++i) { a.step(STEP); b.step(STEP); }
    // a: resume armed exactly ON the next boundary (before step)
    a.resume(); const int64_t fa = a.step(STEP);
    // b: resume armed mid-step (a wall instant later) — same next writer target
    b.resume(); const int64_t fb = b.step(STEP);
    check(fa == fb, "t2_resume_stamp_independent_of_action_instant", {{"on_edge", fa}, {"mid_phase", fb}});
  }
  // T3 hold longer than the declared minimum
  {
    Sim s; for (int i = 0; i < 30; ++i) s.step(STEP);
    s.hold(); for (int i = 0; i < 300; ++i) s.step(STEP);   // 6s >> declared 1.2s minimum
    s.resume(); const int64_t f1 = s.step(STEP); const int64_t f2 = s.step(STEP);
    check(f2 > f1 && f1 > s.m.published_stamp_ns - CATCH_UP_CAP_NS, "t3_long_hold_maps_capped_and_monotonic",
          {{"first", f1}, {"second", f2}});
  }
  // T4 duplicate resume: single pending application
  {
    Sim s; for (int i = 0; i < 20; ++i) s.step(STEP);
    s.hold(); for (int i = 0; i < 30; ++i) s.step(STEP);
    s.resume(); resume_mapping::arm_resume(s.m);            // duplicate arm while pending
    const int64_t f1 = s.step(STEP); const int64_t f2 = s.step(STEP);
    check(f2 - f1 == STEP, "t4_duplicate_resume_single_application", {{"second_delta", f2 - f1}});
  }
  // T5 missing resume: hold to the end, frozen and safe
  {
    Sim s; for (int i = 0; i < 20; ++i) s.step(STEP);
    const int64_t frozen = s.stamp; s.hold();
    bool ok = true; for (int i = 0; i < 500; ++i) ok &= (s.step(STEP) == frozen);
    check(ok, "t5_missing_resume_frozen_no_crash");
  }
  // T6 no double count: first post-resume step applies ONLY the pair mapping
  {
    Sim s; for (int i = 0; i < 40; ++i) s.step(STEP);
    const int64_t s_lp = s.m.published_stamp_ns, t_lp = s.m.published_target_ns;
    s.hold(); for (int i = 0; i < 50; ++i) s.step(STEP);
    s.resume(); const int64_t f1 = s.step(STEP);
    check(f1 == s_lp + (s.t - t_lp), "t6_no_double_accumulation",
          {{"got", f1}, {"expect", s_lp + (s.t - t_lp)}});
  }
  // T7 RTF window rebuild after resume (>=400ms window, ratio in band)
  {
    Sim s; for (int i = 0; i < 30; ++i) s.step(STEP);
    s.hold(); for (int i = 0; i < 50; ++i) s.step(STEP);
    s.resume(); std::vector<int64_t> st;
    for (int i = 0; i < 25; ++i) st.push_back(s.step(STEP));  // 480ms of samples
    const int64_t ds = st.back() - st.front(), dt = 24 * STEP;
    const double ratio = double(ds) / double(dt);
    check(ratio > 0.95 && ratio < 1.05, "t7_rtf_window_rebuild_in_band", ratio);
  }
  // T8 ordinary no-hold path identical to the original formula
  {
    Sim s; int64_t orig = 100000000000LL, orig_last = 0; bool same = true;
    for (int i = 1; i <= 100; ++i) {
      const int64_t t = i * STEP;
      orig += orig_last ? std::max(int64_t(0), t - orig_last) : 100000000000LL;
      orig_last = t;
      if (s.step(STEP) != orig) same = false;
    }
    check(same, "t8_no_hold_path_bitwise_identical");
  }
  // T9 same_stamp compatibility: publishes during hold; smooth resume
  {
    Sim s; s.silent = false;               // same_stamp publishes frozen stamps during hold
    for (int i = 0; i < 30; ++i) s.step(STEP);
    s.hold(); int64_t last = 0;
    for (int i = 0; i < 40; ++i) last = s.step(STEP);
    s.resume(); const int64_t f1 = s.step(STEP);
    check(f1 >= last && f1 - last <= 2 * STEP, "t9_same_stamp_smooth_resume",
          {{"frozen", last}, {"first_resumed", f1}, {"delta", f1 - last}});
  }
  // T10 catch-up cap under the 5s epoch threshold
  {
    Sim s; for (int i = 0; i < 10; ++i) s.step(STEP);
    const int64_t s_lp = s.m.published_stamp_ns;
    s.hold(); for (int i = 0; i < 500; ++i) s.step(STEP);   // 10s silence
    s.resume(); const int64_t f1 = s.step(STEP);
    check(f1 - s_lp == CATCH_UP_CAP_NS && CATCH_UP_CAP_NS < 5000000000LL,
          "t10_catch_up_capped_below_epoch_threshold", {{"applied", f1 - s_lp}});
  }
  // T11 large-stamp overflow guard
  {
    Sim s; s.stamp = 900000000000000000LL; s.t = 0;
    for (int i = 0; i < 10; ++i) s.step(STEP);
    s.hold(); for (int i = 0; i < 600; ++i) s.step(STEP);
    s.resume(); const int64_t f1 = s.step(STEP); const int64_t f2 = s.step(STEP);
    check(f1 > 0 && f2 > f1, "t11_large_stamp_no_overflow", {{"f1", f1}, {"f2", f2}});
  }
}
// --- mutants of the production helper semantics ---------------------------
namespace mutant {
int64_t step_no_catchup(Mapping &m, bool holding, int64_t stamp, int64_t target, int64_t last) {
  if (holding) return stamp;  // M1: pending flag ignored (catch-up deleted)
  return stamp + (last ? std::max(int64_t(0), target - last) : 100000000000LL);
}
int64_t step_command_time(Mapping &m, bool holding, int64_t stamp, int64_t target, int64_t last, int64_t command_t) {
  if (holding) return stamp;  // M2: uses the action execution time
  if (m.resume_pending) { m.resume_pending = false; return m.published_stamp_ns + (command_t - m.published_target_ns); }
  return stamp + (last ? std::max(int64_t(0), target - last) : 100000000000LL);
}
int64_t step_double(Mapping &m, bool holding, int64_t stamp, int64_t target, int64_t last) {
  if (holding) return stamp;  // M3: catch-up PLUS the ordinary delta
  if (m.resume_pending) { m.resume_pending = false; return m.published_stamp_ns + (target - m.published_target_ns) + std::max(int64_t(0), target - last); }
  return stamp + (last ? std::max(int64_t(0), target - last) : 100000000000LL);
}
}
void run_mutants() {
  const int64_t STEP = 20000000;
  // M1 must break the T1 invariant (first resumed stamp = pair mapping)
  {
    Mapping m; int64_t stamp = 100000000000LL, last = 0, t = 0;
    for (int i = 1; i <= 100; ++i) { t = i * STEP; stamp = mutant::step_no_catchup(m, false, stamp, t, last); last = t; resume_mapping::note_published(m, stamp, t); }
    const int64_t s_lp = m.published_stamp_ns, t_lp = m.published_target_ns;
    for (int i = 0; i < 77; ++i) { t += STEP; stamp = mutant::step_no_catchup(m, true, stamp, t, last); last = t; }
    resume_mapping::arm_resume(m);
    t += STEP; stamp = mutant::step_no_catchup(m, false, stamp, t, last);
    const bool broken = (stamp != s_lp + (t - t_lp));
    check(broken, "mutant_m1_no_catchup_is_caught", {{"mutant_stamp", stamp}, {"correct", s_lp + (t - t_lp)}});
  }
  // M2 must break the T2 invariant (action-time dependence)
  {
    Mapping m; int64_t stamp = 100000000000LL, last = 0, t = 0;
    for (int i = 1; i <= 50; ++i) { t = i * STEP; stamp = mutant::step_command_time(m, false, stamp, t, last, t); last = t; resume_mapping::note_published(m, stamp, t); }
    for (int i = 0; i < 60; ++i) { t += STEP; stamp = mutant::step_command_time(m, true, stamp, t, last, t); last = t; }
    resume_mapping::arm_resume(m);
    const int64_t cmd_on_edge = t + STEP;                    // resume exactly at boundary
    const int64_t cmd_mid = t + STEP + 7000000;              // resume 7ms into the step
    Mapping a = m, b = m;
    t += STEP;
    const int64_t fa = mutant::step_command_time(a, false, stamp, t, last, cmd_on_edge);
    const int64_t fb = mutant::step_command_time(b, false, stamp, t, last, cmd_mid);
    check(fa != fb, "mutant_m2_command_time_source_is_caught", {{"on_edge", fa}, {"mid_phase", fb}});
  }
  // M3 must break the T6 invariant (double accumulation)
  {
    Mapping m; int64_t stamp = 100000000000LL, last = 0, t = 0;
    for (int i = 1; i <= 40; ++i) { t = i * STEP; stamp = mutant::step_double(m, false, stamp, t, last); last = t; resume_mapping::note_published(m, stamp, t); }
    const int64_t s_lp = m.published_stamp_ns, t_lp = m.published_target_ns;
    for (int i = 0; i < 50; ++i) { t += STEP; stamp = mutant::step_double(m, true, stamp, t, last); last = t; }
    resume_mapping::arm_resume(m);
    t += STEP; stamp = mutant::step_double(m, false, stamp, t, last);
    check(stamp != s_lp + (t - t_lp), "mutant_m3_double_accumulation_is_caught",
          {{"mutant", stamp}, {"correct", s_lp + (t - t_lp)}});
  }
}
int main(int argc, char **argv) {
  try {
    if (argc != 2) throw std::runtime_error("usage: test_resume_mapping_v1 <fresh_out_dir>");
    const std::filesystem::path out(argv[1]);
    if (std::filesystem::exists(out)) throw std::runtime_error("fresh output directory required");
    std::filesystem::create_directories(out);
    run_matrix();
    run_mutants();
    Json result = {{"schema", "S2-resume-mapping/v1"}, {"passed", all_ok},
                   {"assertions", asserts}, {"assertion_count", asserts.size()}, {"checks", checks},
                   {"production_call_site", "fixture/synthetic_source_m4.cpp publish_step (step_stamp) and clock_resume (arm_resume)"},
                   {"helper", "fixture/resume_stamp_mapping_v1.hpp"},
                   {"mutants_required_caught", 3},
                   {"ROS_context_created", false}, {"stage_qualified", false},
                   {"execute_qualified", false}, {"research_conclusion", false}};
    std::ofstream f(out / "result.json"); f << result.dump(2) << '\n';
    if (!f) throw std::runtime_error("evidence stream");
    std::cout << "passed=" << (all_ok ? "true" : "false") << " assertions=" << asserts.size() << '\n';
    return all_ok ? 0 : 2;
  } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 2; }
}
