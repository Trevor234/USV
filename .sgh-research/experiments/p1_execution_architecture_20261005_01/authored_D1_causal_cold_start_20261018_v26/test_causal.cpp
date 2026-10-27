// SPDX-License-Identifier: MIT
#include "causal_start.hpp"
#include <gtest/gtest.h>
#include <limits>
#ifndef P1_REPLAY_INPUT_FILE
#error validation fixture required only for this test executable
#endif
auto validation(){return bias_replay::read(P1_REPLAY_INPUT_FILE);}
TEST(CausalCold,DefaultModeReproducesAll102ActualJobs){
 auto v=validation();auto r=startup_replay::actual_baseline(bias_replay::read(v["actual_baseline_input_path"]));
 EXPECT_EQ(r["jobs"],102);
 for(auto kind:{"public_vs_actual","raw_shift_vs_actual","public_vs_raw_shift"}){
  EXPECT_LE(r[kind]["control"].get<double>(),1e-10);
  EXPECT_LE(r[kind]["X"].get<double>(),1e-9);
  EXPECT_LE(r[kind]["U"].get<double>(),1e-9);
 }
}
TEST(CausalCold,ModeWithdrawalReadsActualBoundsAndPreservesWarmCache){
 auto v=validation();auto d=bias_replay::read(v["runtime_input_path"]);auto p=bias_replay::parameters(d["contract"]);startup_replay::RawBackend s(p);s.seed_feasible(d["actual_job"],std::vector<double>(40,0.));auto before=s.warm_state();
 s.set_first_control_mode(true);auto on=s.first_control_bounds();
 EXPECT_EQ(on["lbu"],causal_start::Json::array({.5,.5}));
 EXPECT_EQ(on["ubu"],causal_start::Json::array({.5,.5}));
 s.set_first_control_mode(false);auto off=s.first_control_bounds();
 EXPECT_EQ(off["lbu"],causal_start::Json::array({-25.,-25.}));
 EXPECT_EQ(off["ubu"],causal_start::Json::array({25.,25.}));
 EXPECT_EQ(before,s.warm_state());
}
TEST(CausalCold,InvalidCausalSeedsRejectedBeforeSolve){
 auto v=validation();auto d=bias_replay::read(v["runtime_input_path"]);auto p=bias_replay::parameters(d["contract"]);startup_replay::RawBackend s(p);std::vector<double> u(40,0.);u[0]=17.;
 EXPECT_THROW(s.seed_feasible(d["actual_job"],u),std::runtime_error);
 u[0]=std::numeric_limits<double>::quiet_NaN();
 EXPECT_THROW(s.seed_feasible(d["actual_job"],u),std::runtime_error);
}
