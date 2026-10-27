// SPDX-License-Identifier: MIT
#pragma once
#include "raw_backend_v1.hpp"
namespace fixed_first {
using Json=bias_replay::Json;
inline Json seeded_free_baseline(const Json &input){
 auto p=bias_replay::parameters(input.at("contract"));auto &job=input.at("actual_job");startup_replay::RawBackend solver(p);auto seed=solver.seed_feasible(job,input.at("refined_U").get<std::vector<double>>());auto answer=solver.step(job,false,false);auto r=startup_replay::answer_json(answer,job,p);const auto &expected=input.at("refined_answer");
 double xe=bias_replay::maximum_error(r["X"].get<std::vector<double>>(),expected.at("X")),ue=bias_replay::maximum_error(r["U"].get<std::vector<double>>(),expected.at("U")),ce=std::abs(r["feasible_rollout_objective_self_computed"]["total"].get<double>()-expected.at("feasible_rollout_objective_self_computed").at("total").get<double>());
 bias_replay::require(xe<=input.at("baseline_max_U_X_abs_error").get<double>()&&ue<=input.at("baseline_max_U_X_abs_error").get<double>()&&ce<=input.at("baseline_max_feasible_cost_abs_error").get<double>(),"free seeded baseline must reproduce before constrained OCP");
 return {{"X_max_abs_error",xe},{"U_max_abs_error",ue},{"feasible_cost_abs_error",ce},{"seed",seed},{"answer",r}};
}
} // namespace fixed_first
