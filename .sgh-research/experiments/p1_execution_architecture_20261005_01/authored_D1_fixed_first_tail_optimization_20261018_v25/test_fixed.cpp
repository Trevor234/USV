// SPDX-License-Identifier: MIT
#include "fixed_first.hpp"
#include <gtest/gtest.h>
#include <limits>
#ifndef P1_REPLAY_INPUT_FILE
#error pinned input required
#endif
auto input(){return bias_replay::read(P1_REPLAY_INPUT_FILE);}
TEST(FixedFirst,UnmodifiedModeReproducesAll102ActualJobs){
 auto d=input();auto r=startup_replay::actual_baseline(bias_replay::read(d["actual_baseline_input_path"]));
 EXPECT_EQ(r["jobs"],102);
 for(auto kind:{"public_vs_actual","raw_shift_vs_actual","public_vs_raw_shift"}){
  EXPECT_LE(r[kind]["control"].get<double>(),1e-10);
  EXPECT_LE(r[kind]["X"].get<double>(),1e-9);
  EXPECT_LE(r[kind]["U"].get<double>(),1e-9);
 }
}
TEST(FixedFirst,FeasibleSeedFreeSolveReproducesRefinedBaseline){
 auto d=input();auto r=fixed_first::seeded_free_baseline(d);
 EXPECT_LE(r["X_max_abs_error"].get<double>(),1e-9);
 EXPECT_LE(r["U_max_abs_error"].get<double>(),1e-9);
 EXPECT_LE(r["feasible_cost_abs_error"].get<double>(),1e-11);
}
TEST(FixedFirst,InvalidSeedsRejectedBeforeAnySolve){
 auto d=input();auto p=bias_replay::parameters(d["contract"]);startup_replay::RawBackend s(p);auto u=d["refined_U"].get<std::vector<double>>();u[0]=17.;
 EXPECT_THROW(s.seed_feasible(d["actual_job"],u),std::runtime_error);
 u=d["refined_U"].get<std::vector<double>>();u[4]=std::numeric_limits<double>::quiet_NaN();
 EXPECT_THROW(s.seed_feasible(d["actual_job"],u),std::runtime_error);
}
