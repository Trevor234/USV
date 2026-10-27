// SPDX-License-Identifier: MIT
// Runtime candidate accepts current-Job data only. Oracles live in another process.
#pragma once
#include "raw_backend_v1.hpp"
#include <functional>
namespace causal_start {
using Json=bias_replay::Json;
inline Json answer(const startup_replay::Answer &a,const Json &job,const usv_mpc::MpcParams &p,bool fixed,bool shifted){
 auto r=startup_replay::answer_json(a,job,p);r["actual_OCP_input_changed"]=fixed;r["additional_first_control_equality"]=fixed;r["warm_shift_after_this_call"]=shifted;r["native_status"]=0;r["augmented_X"]=bias_replay::matrix_data(a.augmented);r["first_control_equality_error_n"]=fixed?std::max(std::abs(a.control[0]-.5),std::abs(a.control[1]-.5)):0.;return r;
}
class Pipeline {
 public:
 explicit Pipeline(const usv_mpc::MpcParams &p):p_(p),solver_(p){}
 Json run(const Json &runtime,const std::function<void(const Json&)> &emit){
  bias_replay::require(!done_,"candidate may run once per cold pipeline");const auto &job=runtime.at("actual_job");
  bias_replay::require(job.at("job_id")==1&&startup_replay::state_of(job).isZero(0.)&&startup_replay::anchor_of(job).isZero(0.),"registered cold Job1 zero state and anchor only");
  const auto &policy=runtime.at("policy");bias_replay::require(policy.at("free_RTI_calls")==1&&policy.at("restricted_RTI_calls")==3&&policy.at("fixed_first_control_n")==Json::array({.5,.5}),"exact fixed candidate design");
  auto cold=solver_.step(job,job.at("reset_warmstart"),false);++calls_;auto cold_record=answer(cold,job,p_,false,false);emit({{"phase","preliminary_free"},{"answer",cold_record}});
  solver_.set_first_control_mode(true);auto on=solver_.first_control_bounds();emit({{"phase","fixed_mode_enabled"},{"bounds",on}});
  // The sole tail source is the just-computed U; no validation/benchmark object is accepted.
  auto u=bias_replay::matrix_data(cold.info.U_pred);u[0]=.5;u[1]=.5;auto seed=solver_.seed_feasible(job,u);seed["source"]="current_job_preliminary_free_U_only";emit({{"phase","causal_seed"},{"seed",seed}});
  Json rows=Json::array();
  for(int k=1;k<=3;++k){bool shift=k==3;auto a=solver_.step(job,false,shift);++calls_;auto r=answer(a,job,p_,true,shift);rows.push_back({{"iteration",k},{"answer",r}});emit({{"phase","restricted_iteration"},{"iteration",k},{"answer",r}});}
  auto before=solver_.warm_state();solver_.set_first_control_mode(false);auto bounds=solver_.first_control_bounds();auto after=solver_.warm_state();bias_replay::require(before==after,"withdrawal must preserve shifted warm cache");
  bias_replay::require(bounds["lbu"]==Json::array({p_.T_min,p_.T_min})&&bounds["ubu"]==Json::array({p_.T_max,p_.T_max})&&!bounds["additional_first_equality"].get<bool>(),"actual first bounds restored");done_=true;
  Json r={{"actual_job",job},{"preliminary_free",cold_record},{"enabled_first_bounds",on},{"causal_seed",seed},{"restricted_iterations",rows},{"candidate_final",rows.back()["answer"]},{"warm_after_last_shift",before},{"restored_first_bounds",bounds},{"warm_after_withdrawal",after},{"candidate_RTI_calls",calls_},{"oracle_data_accepted_by_candidate",false},{"mode_withdrawn_before_return",true}};emit({{"phase","candidate_complete"},{"candidate",r}});return r;
 }
 Json restoration_probe_same_job(const Json &job){
  bias_replay::require(done_&&!probed_,"one separate probe after candidate completion only");probed_=true;auto before=solver_.first_control_bounds();auto a=solver_.step(job,false,true);
  return {{"scope","separate same-Job offline restoration check; not a future physical Job"},{"RTI_calls",1},{"first_bounds_before",before},{"first_bounds_after",solver_.first_control_bounds()},{"answer",answer(a,job,p_,false,true)},{"fed_back_into_candidate",false}};
 }
 private:usv_mpc::MpcParams p_;startup_replay::RawBackend solver_;bool done_=false,probed_=false;int calls_=0;
};
} // namespace causal_start
