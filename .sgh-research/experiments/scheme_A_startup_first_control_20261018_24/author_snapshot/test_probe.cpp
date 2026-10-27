// SPDX-License-Identifier: MIT
#include "probe.hpp"
#include <gtest/gtest.h>
#ifndef P1_REPLAY_INPUT_FILE
#error pinned actual input required
#endif
auto input(){return bias_replay::read(P1_REPLAY_INPUT_FILE);}
TEST(FirstControl,ActualSingleRTIFullNonlinearBaseline){auto d=input();auto b=first_probe::baseline(d,"once");EXPECT_LE(b["max_X_abs_error"].get<double>(),1e-11);EXPECT_LE(b["max_cost_part_abs_error"].get<double>(),1e-11);}
TEST(FirstControl,ActualUnshiftedIteration12FullBaseline){auto d=input();auto b=first_probe::baseline(d,"refined");EXPECT_LE(b["max_X_abs_error"].get<double>(),1e-11);EXPECT_LE(b["max_cost_part_abs_error"].get<double>(),1e-11);}
TEST(FirstControl,RejectNonfiniteAndOutOfBoundsWithoutClamping){
 auto d=input();auto p=bias_replay::parameters(d["contract"]);
 auto u=first_probe::controls(d["tail_sequences"]["once"]["U"]);
 auto a=first_probe::anchor(d["actual_job"]);
 u(0,0)=25.001;
 EXPECT_THROW(first_probe::validate(u,a,p),std::runtime_error);
 u(0,0)=std::numeric_limits<double>::quiet_NaN();
 EXPECT_THROW(first_probe::validate(u,a,p),std::runtime_error);
}
TEST(FirstControl,RateBoundaryUsesActualAnchorAndAllLaterNodes){
 auto d=input();auto p=bias_replay::parameters(d["contract"]);
 auto u=first_probe::controls(d["tail_sequences"]["once"]["U"]);
 auto a=first_probe::anchor(d["actual_job"]);
 u.col(0).setConstant(16.);
 EXPECT_NO_THROW(first_probe::validate(u,a,p));
 u(0,0)=16.000001;
 EXPECT_THROW(first_probe::validate(u,a,p),std::runtime_error);
 u=first_probe::controls(d["tail_sequences"]["once"]["U"]);u(0,9)=17.;
 EXPECT_THROW(first_probe::validate(u,a,p),std::runtime_error);
}
