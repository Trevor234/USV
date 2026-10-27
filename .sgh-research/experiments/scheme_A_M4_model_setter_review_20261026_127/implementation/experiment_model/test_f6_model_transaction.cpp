// SPDX-License-Identifier: MIT
// F6 limited model transaction harness (batch 107 design, batch 108 run).
// Native, no ROS context, no codegen, no GP/PPO. Drives the real vendored
// acados C API through model_transaction_v1.hpp and compares against the freshly compiled
// checked_init AcadosBackend source candidate. One registered
// case per invocation; result.json carries per-assertion evidence.
#include "model_transaction_v1.hpp"
#include "usv_mpc_cpp/acados_backend.hpp"
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
#include <string>
using usv_mpc::AcadosBackend;
using usv_mpc::MpcParams;
using usv_mpc::Vector6d;
using Json = nlohmann::json;
// Registration-fixed parameters.
constexpr double TOL = 1e-8;
constexpr int K1_TICKS = 4, K2_TICKS = 4;
MpcParams params_m0() { return MpcParams{}; }
MpcParams params_m1() {           // limited perturbed finite model version
  MpcParams p{};
  p.hydro.mass = 15.0;            // 14.2 -> 15.0
  p.hydro.Xu = -2.4;              // -2.272063 -> -2.4
  p.hydro.Nr = -4.4;              // -4.286144 -> -4.4
  return p;
}
std::array<double, 30> make_p_global(const MpcParams & p) {
  return usv_mpc::p_global::pack(p);
}
Eigen::MatrixXd ref_tick(int k) {          // .05 straight, 6 x 21
  Eigen::MatrixXd R(6, 21);
  for (int j = 0; j < 21; ++j) {
    R(0, j) = 0.05 * 0.2 * (k + j); R(1, j) = 0.0; R(2, j) = 0.0;
    R(3, j) = 0.05; R(4, j) = 0.0; R(5, j) = 0.0;
  }
  return R;
}
Vector6d state_tick(int k) {               // on-line state with a heading offset
  Vector6d s; s << 0.05 * 0.2 * k + 0.02, 0.0, 0.03, 0.045, 0.0, 0.0; return s;
}
int checks = 0; Json asserts = Json::array(); bool all_ok = true;
void check(bool v, const std::string & name, const Json & observed = Json(nullptr)) {
  ++checks; if (!v) all_ok = false;
  asserts.push_back({{"name", name}, {"passed", v}, {"observed", observed}});
}
void require(bool v, const char * why) { ++checks; if (!v) throw std::runtime_error(why); }
double max_abs_diff(const Eigen::MatrixXd & a, const Eigen::MatrixXd & b) {
  return (a - b).cwiseAbs().maxCoeff();
}
Json stats_json(const f6::Stats & s) {
  return {{"offered", s.offered}, {"executed", s.executed},
          {"rejected_stale_stamp", s.rejected_stale_stamp},
          {"rejected_preparing", s.rejected_preparing},
          {"rejected_unknown_generation", s.rejected_unknown_generation},
          {"rejected_immutable", s.rejected_immutable},
          {"prepares_staged", s.prepares_staged}, {"commits", s.commits}};
}
void init_m0(f6::ModelTransactionSolver & w) {
  require(w.register_version(1, make_p_global(params_m0())), "register m0");
  require(w.prepare(1) && w.commit(), "initial commit m0");
}
// F6-6: no transaction, whole run on M0 — the wrapper must reproduce the
// production AcadosBackend tick for tick (wrapper fidelity + inertness).
void run_f6_6() {
  f6::ModelTransactionSolver w(f6::Bounds{}); init_m0(w);
  AcadosBackend backend(params_m0());
  double worst = 0.0;
  for (int k = 0; k < 8; ++k) {
    auto out = w.solve(1, state_tick(k), ref_tick(k));
    auto [u, info] = backend.solve(state_tick(k), ref_tick(k));
    require(out.executed && out.finite && info.success, "f6_6 solve ok");
    worst = std::max(worst, (out.u - u).cwiseAbs().maxCoeff());
    worst = std::max(worst, max_abs_diff(out.X.topRows(6), info.X_pred));
  }
  check(worst < TOL, "f6_6_wrapper_matches_production_backend_tick_for_tick", worst);
  check(w.stats().offered == 8 && w.stats().executed == 8 && w.stats().commits == 1,
        "f6_6_no_transaction_accounting", stats_json(w.stats()));
}
// F6-1: runtime p_global setter-path switch equals a freshly constructed M1
// instance (the F6 gap closure premise: the setter path really works).
void run_f6_1() {
  f6::ModelTransactionSolver w(f6::Bounds{}); init_m0(w);
  for (int k = 0; k < 8; ++k) require(w.solve(1, state_tick(k), ref_tick(k)).finite, "m0 tick");
  require(w.register_version(2, make_p_global(params_m1())), "register m1");
  require(w.prepare(2) && w.commit(), "commit m1");
  const bool m1_book_empty_before_solve = !w.warm_of(2).has;  // cold == fresh instance premise
  const int k = 8;
  auto out = w.solve(2, state_tick(k), ref_tick(k));
  AcadosBackend fresh_m1(params_m1());
  auto [u, info] = fresh_m1.solve(state_tick(k), ref_tick(k));
  require(out.executed && out.finite && info.success, "f6_1 solves ok");
  const double du = (out.u - u).cwiseAbs().maxCoeff();
  const double dx = max_abs_diff(out.X.topRows(6), info.X_pred);
  check(du < TOL && dx < TOL, "f6_1_setter_switch_equals_fresh_m1_instance",
        {{"u_diff", du}, {"X_diff", dx}});
  check(w.current_generation() == 2 && w.warm_of(1).has && m1_book_empty_before_solve
        && w.warm_of(2).has, "f6_1_warm_books_per_version",
        {{"m0_book", true}, {"m1_empty_before_solve", m1_book_empty_before_solve},
         {"m1_book_after_solve", w.warm_of(2).has}});
}
// F6-3: fixed-tick activation — every tick matches the corresponding pure
// version instance; the switch happens only at the tick boundary.
void run_f6_3() {
  f6::ModelTransactionSolver w(f6::Bounds{}); init_m0(w);
  AcadosBackend pure_m0(params_m0());
  double worst = 0.0;
  for (int k = 0; k < K1_TICKS; ++k) {
    auto out = w.solve(1, state_tick(k), ref_tick(k));
    auto [u, info] = pure_m0.solve(state_tick(k), ref_tick(k));
    worst = std::max({worst, (out.u - u).cwiseAbs().maxCoeff(),
                      max_abs_diff(out.X.topRows(6), info.X_pred)});
  }
  check(worst < TOL, "f6_3_m0_phase_matches_pure_m0", worst);
  require(w.register_version(2, make_p_global(params_m1())) && w.prepare(2) && w.commit(), "switch");
  AcadosBackend pure_m1(params_m1());
  double worst2 = 0.0;
  for (int k = K1_TICKS; k < K1_TICKS + K2_TICKS; ++k) {
    auto out = w.solve(2, state_tick(k), ref_tick(k));
    auto [u, info] = pure_m1.solve(state_tick(k), ref_tick(k));
    worst2 = std::max({worst2, (out.u - u).cwiseAbs().maxCoeff(),
                       max_abs_diff(out.X.topRows(6), info.X_pred)});
  }
  check(worst2 < TOL, "f6_3_m1_phase_matches_pure_m1", worst2);
  check(w.stats().commits == 2 && w.stats().rejected_stale_stamp == 0,
        "f6_3_clean_boundary_accounting", stats_json(w.stats()));
}
// F6-2: prepare/commit two-phase — solve is rejected while preparing and the
// solver call count proves no half-applied solve ever ran.
void run_f6_2() {
  f6::ModelTransactionSolver w(f6::Bounds{}); init_m0(w);
  require(w.solve(1, state_tick(0), ref_tick(0)).executed, "first tick");
  const uint64_t executed_before = w.stats().executed;
  require(w.register_version(2, make_p_global(params_m1())), "register m1");
  require(w.prepare(2), "prepare");
  auto blocked = w.solve(1, state_tick(1), ref_tick(1));
  check(!blocked.executed && blocked.reject == "solve_during_prepare",
        "f6_2_solve_rejected_during_prepare", blocked.reject);
  check(w.stats().executed == executed_before, "f6_2_no_half_applied_solve",
        {{"executed", w.stats().executed}});
  require(w.commit(), "commit");
  auto out = w.solve(2, state_tick(1), ref_tick(1));
  check(out.executed && out.finite && w.stats().executed == executed_before + 1,
        "f6_2_solve_after_commit_executes_exactly_once");
  check(w.stats().rejected_preparing == 1 && w.stats().commits == 2, "f6_2_accounting",
        stats_json(w.stats()));
}
// F6-4: stale/mixed rejection — old stamps never touch the solver; version
// content is immutable.
void run_f6_4() {
  f6::ModelTransactionSolver w(f6::Bounds{}); init_m0(w);
  require(w.solve(1, state_tick(0), ref_tick(0)).executed, "tick");
  require(w.register_version(2, make_p_global(params_m1())) && w.prepare(2) && w.commit(), "switch");
  const uint64_t executed_before = w.stats().executed;
  auto stale = w.solve(1, state_tick(1), ref_tick(1));
  check(!stale.executed && stale.reject == "stale_stamp", "f6_4_stale_stamp_rejected", stale.reject);
  auto unknown = w.solve(99, state_tick(1), ref_tick(1));
  check(!unknown.executed && unknown.reject == "unknown_generation",
        "f6_4_unknown_generation_rejected", unknown.reject);
  auto redefined = w.register_version(2, make_p_global(params_m0()));
  check(!redefined && w.stats().rejected_immutable == 1, "f6_4_version_content_immutable");
  check(w.stats().executed == executed_before, "f6_4_rejections_never_touch_solver",
        {{"executed", w.stats().executed}});
  check(w.warm_of(1).has && w.current_generation() == 2, "f6_4_state_unchanged_by_rejections");
}
// F6-5: warm-start independence — switching back restores M0's own warm book
// and the next solve matches the paused pure M0 instance exactly.
void run_f6_5() {
  f6::ModelTransactionSolver w(f6::Bounds{}); init_m0(w);
  AcadosBackend paused_m0(params_m0());
  double worst = 0.0;
  for (int k = 0; k < 5; ++k) {
    auto out = w.solve(1, state_tick(k), ref_tick(k));
    auto [u, info] = paused_m0.solve(state_tick(k), ref_tick(k));
    worst = std::max(worst, (out.u - u).cwiseAbs().maxCoeff());
  }
  check(worst < TOL, "f6_5_phase1_lockstep", worst);
  require(w.register_version(2, make_p_global(params_m1())) && w.prepare(2) && w.commit(), "to m1");
  require(w.solve(2, state_tick(5), ref_tick(5)).executed, "m1 tick");
  const bool m1_has_warm = w.warm_of(2).has;
  require(w.prepare(1) && w.commit(), "back to m0");
  check(!w.preparing() && w.current_generation() == 1, "f6_5_back_on_m0");
  auto out = w.solve(1, state_tick(5), ref_tick(5));
  auto [u, info] = paused_m0.solve(state_tick(5), ref_tick(5));
  require(out.executed && out.finite && info.success, "f6_5 solve ok");
  const double du = (out.u - u).cwiseAbs().maxCoeff();
  check(du < TOL, "f6_5_m0_warm_restored_matches_paused_instance", du);
  check(m1_has_warm && w.warm_of(1).has, "f6_5_both_versions_keep_warm_books");
}
int main(int argc, char ** argv) {
  try {
    require(argc == 3, "usage: test_f6_model_transaction <case_id> <fresh_out_dir>");
    const std::string casename = argv[1];
    const std::filesystem::path out(argv[2]);
    require(!std::filesystem::exists(out), "fresh output directory required (single finite execution)");
    std::filesystem::create_directories(out);
    if (casename == "F6-1") run_f6_1();
    else if (casename == "F6-2") run_f6_2();
    else if (casename == "F6-3") run_f6_3();
    else if (casename == "F6-4") run_f6_4();
    else if (casename == "F6-5") run_f6_5();
    else if (casename == "F6-6") run_f6_6();
    else require(false, "unknown case");
    Json result = {{"schema", "F6-model-transaction/v1"}, {"case", casename}, {"passed", all_ok},
                   {"assertions", asserts}, {"assertion_count", asserts.size()}, {"checks", checks},
                   {"tolerance", TOL},
                   {"comparison_scope", "fresh checked_init source snapshot, not an installed solver archive"},
                   {"m1_perturbations", {{"mass", {14.2, 15.0}}, {"Xu", {-2.272063, -2.4}},
                                          {"Nr", {-4.286144, -4.4}}}},
                   {"ROS_context_created", false}, {"actuator_endpoints_created", false},
                   {"stage_qualified", false}, {"execute_qualified", false}, {"research_conclusion", false}};
    std::ofstream f(out / "result.json");
    f << result.dump(2) << '\n';
    require(bool(f), "evidence stream");
    std::cout << "case=" << casename << " passed=" << (all_ok ? "true" : "false")
              << " assertions=" << asserts.size() << '\n';
    return all_ok ? 0 : 2;
  } catch (const std::exception & e) { std::cerr << e.what() << '\n'; return 2; }
}
