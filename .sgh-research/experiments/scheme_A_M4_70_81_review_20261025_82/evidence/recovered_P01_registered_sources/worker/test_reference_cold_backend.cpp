// SPDX-License-Identifier: MIT
#include "owned_cold_backend.hpp"
#include <gtest/gtest.h>
#ifndef OWNED_COLD_TEST_INPUT_FILE
#error isolated component fixture required
#endif
namespace {
using Json=nlohmann::json;
Json fixture(){return bias_replay::read(OWNED_COLD_TEST_INPUT_FILE);}
Json data(){return bias_replay::read(fixture().at("legacy_input_path"));}
Json job(const Json &d,size_t k=0){return d.at("ordered_native_jobs").at(k).at("job");}
Json binding(const Json &j){Json b;for(auto k:{"run_id","boot_id","contract_hash","nominal_hash","worker_instance"})b[k]=j.at(k);return b;}
void anchor(owned_cold::Backend &s,const Json &j){s.set_applied_control(startup_replay::anchor_of(j));if(j.at("reset_warmstart").get<bool>())s.reset_warmstart();}
}
TEST(OwnedCold,DefaultAdapterReplaysAll102ActualJobs){
 auto d=data();int64_t now=0;owned_cold::Backend s(bias_replay::parameters(d["contract"]),binding(job(d)),false,[&](){return now;});size_t count=0;
 for(const auto &row:d["ordered_native_jobs"]){auto j=row["job"];now=j["freeze_ns"].get<int64_t>()+1;anchor(s,j);auto a=s.solve_owned(j);auto expected=row["expected"];
  EXPECT_LE(bias_replay::maximum_error({a.first[0],a.first[1]},expected["first_control"]),1e-10);
  EXPECT_LE(bias_replay::maximum_error(bias_replay::matrix_data(a.second.X_pred),expected["X"]),1e-9);
  EXPECT_LE(bias_replay::maximum_error(bias_replay::matrix_data(a.second.U_pred),expected["U"]),1e-9);
  EXPECT_EQ(s.last_policy_event()["backend_entries_completed"],1);++count;
 }
 EXPECT_EQ(count,102u);
}
TEST(OwnedCold,CurrentJobOnlyFourCallsMatchSealedCausalCandidate){
 auto d=data();auto j=job(d);int64_t now=j["freeze_ns"].get<int64_t>()+1;owned_cold::Backend s(bias_replay::parameters(d["contract"]),binding(j),true,[&](){return now;});anchor(s,j);auto a=s.solve_owned(j);auto v=bias_replay::read(fixture()["candidate_result_path"])["candidate"]["candidate_final"];
 EXPECT_EQ(s.last_policy_event()["candidate_applied"],true);
 EXPECT_EQ(s.last_policy_event()["backend_entries_completed"],4);
 EXPECT_LE(bias_replay::maximum_error(bias_replay::matrix_data(a.second.X_pred),v["X"]),1e-8);
 EXPECT_LE(bias_replay::maximum_error(bias_replay::matrix_data(a.second.U_pred),v["U"]),1e-8);
}
TEST(OwnedCold,InvalidIdentityDoesNotConsumeColdOpportunity){
 auto d=data();auto j=job(d);int64_t now=j["freeze_ns"].get<int64_t>()+1;owned_cold::Backend s(bias_replay::parameters(d["contract"]),binding(j),true,[&](){return now;});auto bad=j;bad["run_id"]="foreign";anchor(s,bad);
 EXPECT_THROW(s.solve_owned(bad),std::runtime_error);
 anchor(s,j);s.solve_owned(j);
 EXPECT_EQ(s.last_policy_event()["candidate_applied"],true);
}
TEST(OwnedCold,LateJobDoesNotConsumeColdOpportunity){
 auto d=data();auto j=job(d);int64_t now=j["deadline_ns"].get<int64_t>()+1;owned_cold::Backend s(bias_replay::parameters(d["contract"]),binding(j),true,[&](){return now;});anchor(s,j);
 EXPECT_THROW(s.solve_owned(j),std::runtime_error);
 now=j["freeze_ns"].get<int64_t>()+1;anchor(s,j);s.solve_owned(j);
 EXPECT_EQ(s.last_policy_event()["candidate_applied"],true);
}
TEST(OwnedCold,DuplicateRejectedAndNextJobRemainsOneFreeCall){
 auto d=data();auto j=job(d);int64_t now=j["freeze_ns"].get<int64_t>()+1;owned_cold::Backend s(bias_replay::parameters(d["contract"]),binding(j),true,[&](){return now;});anchor(s,j);s.solve_owned(j);anchor(s,j);
 EXPECT_THROW(s.solve_owned(j),std::runtime_error);
 auto next=job(d,1);now=next["freeze_ns"].get<int64_t>()+1;anchor(s,next);s.solve_owned(next);
 EXPECT_EQ(s.last_policy_event()["candidate_applied"],false);
 EXPECT_EQ(s.last_policy_event()["backend_entries_completed"],1);
 EXPECT_EQ(s.actual_first_bounds()["lbu"],Json::array({-25.,-25.}));
}
TEST(OwnedCold,ResetAndGenerationChangeDoNotRearmPolicy){
 auto d=data();auto j=job(d);int64_t now=j["freeze_ns"].get<int64_t>()+1;owned_cold::Backend s(bias_replay::parameters(d["contract"]),binding(j),true,[&](){return now;});anchor(s,j);s.solve_owned(j);auto next=job(d,1);next["task_generation"]=2;next["reset_warmstart"]=true;now=next["freeze_ns"].get<int64_t>()+1;anchor(s,next);s.solve_owned(next);
 EXPECT_EQ(s.last_policy_event()["candidate_applied"],false);
 EXPECT_EQ(s.last_policy_event()["policy_consumed_for_run"],true);
 EXPECT_EQ(s.last_policy_event()["backend_entries_completed"],1);
}
TEST(OwnedCold,ActualWithdrawalPreservesOneShiftedWarmCache){
 auto d=data();auto j=job(d);int64_t now=j["freeze_ns"].get<int64_t>()+1;owned_cold::Backend s(bias_replay::parameters(d["contract"]),binding(j),true,[&](){return now;});anchor(s,j);s.solve_owned(j);auto m=s.last_policy_event();
 EXPECT_EQ(m["warm_after_last_shift"],m["warm_after_withdrawal"]);
 EXPECT_EQ(s.debug_warm(),m["warm_after_withdrawal"]);
 EXPECT_EQ(s.actual_first_bounds()["lbu"],Json::array({-25.,-25.}));
 EXPECT_EQ(s.actual_first_bounds()["ubu"],Json::array({25.,25.}));
 EXPECT_EQ(m["subcalls"][0]["warm_shift_after"],false);
 EXPECT_EQ(m["subcalls"][1]["warm_shift_after"],false);
 EXPECT_EQ(m["subcalls"][2]["warm_shift_after"],false);
 EXPECT_EQ(m["subcalls"][3]["warm_shift_after"],true);
}
TEST(OwnedCold,EveryInternalFailureIsTerminalWithoutFallback){
 auto d=data();auto j=job(d);int64_t now=j["freeze_ns"].get<int64_t>()+1;
 for(unsigned fail=1;fail<=4;++fail){owned_cold::Backend s(bias_replay::parameters(d["contract"]),binding(j),true,[&](){return now;},[&](unsigned n){if(n==fail)throw std::runtime_error("component injected internal failure");});anchor(s,j);
  EXPECT_THROW(s.solve_owned(j),std::runtime_error);
  EXPECT_TRUE(s.terminal());
  EXPECT_EQ(s.last_policy_event()["successful"],false);
  EXPECT_EQ(s.last_policy_event()["backend_entries_completed"],fail-1);
  EXPECT_EQ(s.actual_first_bounds()["lbu"],Json::array({-25.,-25.}));
  auto next=job(d,1);anchor(s,next);
  EXPECT_THROW(s.solve_owned(next),std::runtime_error);
 }
}
TEST(OwnedCold,OutsideRegisteredDomainKeepsOriginalFreeBehavior){
 auto d=data();auto j=job(d);j["reference"][3]=.1;int64_t now=j["freeze_ns"].get<int64_t>()+1;owned_cold::Backend s(bias_replay::parameters(d["contract"]),binding(j),true,[&](){return now;});anchor(s,j);s.solve_owned(j);
 EXPECT_EQ(s.last_policy_event()["candidate_applied"],false);
 EXPECT_EQ(s.last_policy_event()["reason"],"outside_registered_cold_domain");
 EXPECT_EQ(s.last_policy_event()["backend_entries_completed"],1);
}
