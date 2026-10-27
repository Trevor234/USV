// SPDX-License-Identifier: MIT
#include "replay.hpp"
#include <gtest/gtest.h>
#ifndef P1_REPLAY_INPUT_FILE
#error pinned actual input file required
#endif
using Json=bias_replay::Json;
Json data(){return bias_replay::read(P1_REPLAY_INPUT_FILE);}
TEST(TaskTimeReplay,CompleteActualWarmPrefixes){auto d=data();ASSERT_EQ(d["ordered_native_jobs"].size(),40u);for(size_t k=0;k<40;++k)EXPECT_EQ(d["ordered_native_jobs"][k]["job"]["job_id"],k+1);}
TEST(TaskTimeReplay,FirstTargetReferenceBitIdentical){auto d=data();auto j=d["ordered_native_jobs"][0]["job"];EXPECT_EQ(bias_replay::task_time_job(j,d),j);}
TEST(TaskTimeReplay,OnlyXReferenceChangesInActualStraightScope){auto d=data();for(int id:{2,5,10,40}){auto j=d["ordered_native_jobs"][id-1]["job"],t=bias_replay::task_time_job(j,d),restored=t;restored["reference"]=j["reference"];EXPECT_EQ(restored,j);for(int k=0;k<126;++k)if(k%6)EXPECT_EQ(t["reference"][k],j["reference"][k]);EXPECT_GT(t["reference"][0].get<double>(),j["reference"][0].get<double>());}}
TEST(TaskTimeReplay,EpochUsesFirstSubmittedTarget){auto d=data();EXPECT_EQ(d["epoch"]["first_target_sim_ns"],d["ordered_native_jobs"][0]["job"]["target_sim_ns"]);EXPECT_EQ(d["epoch"]["initial_profile_t0"],d["ordered_native_jobs"][0]["reference_metadata"]["profile_t0"]);}
TEST(TaskTimeReplay,ActualBackendGMatchesAllFrozenControlAndPredictions){auto d=data();d["selected_job_id"]=40;auto r=bias_replay::prefix_replay(d,false);EXPECT_EQ(r["maximum_absolute_baseline_first_control_error"],0.);EXPECT_EQ(r["maximum_absolute_baseline_X_error"],0.);EXPECT_EQ(r["maximum_absolute_baseline_U_error"],0.);}
TEST(TaskTimeReplay,TChangesSelectedJobAfterSamePrefix){auto d=data();d["selected_job_id"]=10;auto r=bias_replay::prefix_replay(d,true);EXPECT_EQ(r["maximum_absolute_baseline_first_control_error"],0.);EXPECT_EQ(r["maximum_absolute_baseline_X_error"],0.);EXPECT_EQ(r["maximum_absolute_baseline_U_error"],0.);EXPECT_GT(r["selected"]["selected_absolute_control_difference_from_actual"].get<double>(),.01);}
