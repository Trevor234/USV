// SPDX-License-Identifier: MIT
#pragma once
#include "p1_full_contract.hpp"
#include "p1_shadow_entry.hpp"
#include "task_time_profile_v1.hpp"
namespace p1::shadow {
// This exact function is used by the actual Regulator constructor and the
// native test. Full fixed numeric/type validation remains mandatory.
inline void validate_task_time_entry(const nlohmann::json &c,const std::string &mode){
 require_shadow_mode(mode);
 p1::require_runtime_contract_mode(c,mode);
 require(c.at("schema")=="p1-execution-contract-v2"&&
         p1::strict_i64(c.at("diagnostic_contract_revision"))&&c.at("diagnostic_contract_revision")==10&&
         c.at("activation_state_policy")=="latest_causal_sensor_frame_then_one_revalidation_v1"&&
         c.at("activation_sensor_history_capacity")==32&&c.at("activation_validation_attempts")==2&&
         c.at("cold_start_policy")=="current_job_free_once_then_fixed050_three_rti_v1"&&
         c.at("preparation_retry_policy")=="authenticated_phase_reference_pair_completion_v1"&&
         c.at("reference_sampling_policy")==task_time_reference::policy&&
         c.at("reference_epoch_policy")==task_time_reference::epoch_policy&&
         p1::strict_i64(c.at("reference_start_offset"))&&c.at("reference_start_offset")==0,
         "exact diag10 task-time and submit epoch policies with integer zero offset required");
}
}
