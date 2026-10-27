// SPDX-License-Identifier: MIT
#include "raw_backend_v1.hpp"
#include <gtest/gtest.h>
#ifndef P1_REPLAY_INPUT_FILE
#error actual input required
#endif
auto data(){return bias_replay::read(P1_REPLAY_INPUT_FILE);}
TEST(StartupReplay,ActualCompleteNativeOrder){auto d=data();ASSERT_EQ(d["ordered_native_jobs"].size(),102u);for(size_t i=0;i<102;++i)EXPECT_EQ(d["ordered_native_jobs"][i]["job"]["job_id"],i+1);}
TEST(StartupReplay,ActualColdStartStateAndAnchorAreZero){auto j=data()["ordered_native_jobs"][0]["job"];EXPECT_EQ(j["target_state"],bias_replay::Json::array({0.,0.,0.,0.,0.,0.}));EXPECT_EQ(j["anchor_n"],bias_replay::Json::array({0.,0.}));EXPECT_EQ(j["reset_warmstart"],false);}
TEST(StartupReplay,ReferenceFirstTargetAndVelocityRemainActual){auto j=data()["ordered_native_jobs"][0]["job"];ASSERT_EQ(j["reference"].size(),126u);EXPECT_EQ(j["reference"][0],0.);for(int k=0;k<21;++k)EXPECT_EQ(j["reference"][6*k+3],.05);}
TEST(StartupReplay,NoNumericObjectiveModelOrHorizonTuning){auto p=bias_replay::parameters(data()["contract"]);EXPECT_EQ(p.N,20);EXPECT_EQ(p.dt,.2);EXPECT_EQ(p.Qf_scale,8);EXPECT_EQ(p.R_diag[0],.05);EXPECT_EQ(p.Rd_diag[0],.2);EXPECT_EQ(p.hydro.mass,14.2);EXPECT_EQ(p.dT_max,80);}
TEST(StartupReplay,ScopeIsFiniteAndPrimaryColdJobPredeclared){auto d=data();EXPECT_EQ(d["repeat_count"],12);EXPECT_EQ(d["selected_job_ids"],bias_replay::Json::array({1,2,5,10}));}
TEST(StartupReplay,ActualResetFlagsAndAllPredictionShapes){auto d=data();for(auto &r:d["ordered_native_jobs"]){EXPECT_TRUE(r["job"]["reset_warmstart"].is_boolean());EXPECT_EQ(r["expected"]["X"].size(),126u);EXPECT_EQ(r["expected"]["U"].size(),40u);EXPECT_EQ(r["expected"]["first_control"].size(),2u);}}
TEST(StartupReplay,AbsoluteAndIncrementCostsUseFrozenDt){auto p=bias_replay::parameters(data()["contract"]);usv_mpc::SolveInfo i;i.X_pred=Eigen::MatrixXd::Zero(6,21);i.U_pred=Eigen::MatrixXd::Ones(2,20);auto c=bias_replay::objective(i,Eigen::MatrixXd::Zero(6,21),Eigen::Vector2d::Zero(),p);EXPECT_NEAR(c["stage_absolute_control_dt_scaled"].get<double>(),.4,1e-12);EXPECT_NEAR(c["stage_control_increment_dt_scaled"].get<double>(),.08,1e-12);}
TEST(StartupReplay,TerminalCostNotMultipliedByDt){auto p=bias_replay::parameters(data()["contract"]);usv_mpc::SolveInfo i;i.X_pred=Eigen::MatrixXd::Zero(6,21);i.U_pred=Eigen::MatrixXd::Zero(2,20);i.X_pred(0,20)=1.;EXPECT_EQ(bias_replay::objective(i,Eigen::MatrixXd::Zero(6,21),Eigen::Vector2d::Zero(),p)["terminal_state_not_dt_scaled"],160.);}
TEST(StartupReplay,ZeroInputNominalRolloutStaysZero){auto p=bias_replay::parameters(data()["contract"]);usv_mpc::USVDynamicModel m(p.dt,4,p.hydro);EXPECT_EQ(m.forward(usv_mpc::Vector6d::Zero(),Eigen::Vector2d::Zero()),usv_mpc::Vector6d::Zero());}
TEST(StartupReplay,ActualPublicAndRawShiftReplayAll102Jobs){auto r=startup_replay::actual_baseline(data());EXPECT_EQ(r["jobs"],102);for(auto kind:{"public_vs_actual","raw_shift_vs_actual","public_vs_raw_shift"}){EXPECT_LE(r[kind]["control"].get<double>(),1e-10);for(auto key:{"X","U"})EXPECT_LE(r[kind][key].get<double>(),1e-9);}}
