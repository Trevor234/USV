// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#pragma once
#include "p1_resources.hpp"
#include <cmath>
#include <set>
#include <limits>
#include <regex>
#include <vector>
namespace p1 {
inline constexpr bool physical_execute_release_enabled = false;
inline constexpr const char * contract_parameter_profile = "P1_activation_alignment_diagnostic_20261019_01";
inline constexpr const char * full_contract_spec_sha256 = "dca89c6559110290ece07e6102ee4f0bd28f38031f5dfe1702aaab81be45846f";
inline constexpr const char * target_parameter_profile = "P1_owned_nominal_execution_20261020_01";
inline constexpr const char * target_policy_sha256 = "475d093f034165b94a09dde577a4462dc3c575752e25a99364d4ac699955918b";
inline const nlohmann::json & formal_profile_overrides() {
  static const auto value=nlohmann::json::parse(R"P1PROFILES({"P1_activation_alignment_diagnostic_20261019_01":{},"P1_owned_nominal_execution_20261020_01":{"baseline_input":"F5_NOMINAL_SOURCE_OWNED_REGULATOR_20261020_01","preparation_retry_policy":"owned_reference_pair_completion_before_business_v1","propagation_semantics":"owned-regulator per-side successful API publish-start history from accepted odom stamp, mixed r retained with separate IMU stamp; future held current command; RK4 nominal point prediction"},"P1_owned_diagnostic_worker_20261021_01":{"baseline_input":"F5_NOMINAL_SOURCE_OWNED_REGULATOR_20261020_01","preparation_retry_policy":"owned_reference_pair_completion_before_business_v1","propagation_semantics":"owned-regulator per-side successful API publish-start history from accepted odom stamp, mixed r retained with separate IMU stamp; future held current command; RK4 nominal point prediction"}})P1PROFILES");return value;
}
inline const nlohmann::json & candidate_baseline() {
  static const auto value = nlohmann::json::parse(R"P1BASE({"N":20,"Q":[20,20,50,8,1,8],"Qf_scale":8,"R":[0.05,0.05],"Rd":[0.2,0.2],"T_ns":200000000,"activation_sensor_history_capacity":32,"activation_state_policy":"latest_causal_sensor_frame_then_one_revalidation_v1","activation_tolerance":[0.25,0.25,0.15,0.3,0.2,0.15],"activation_validation_attempts":2,"active_watchdog_ns":1000000000,"backend_rate_n_s":80,"baseline_input":"CONTROLLED_PHASE_20261015_DIAGNOSTIC_01","candidate_cdr_max_bytes":8204,"clock":"CLOCK_MONOTONIC","clock_age_ns":100000000,"clock_pause_confirm_ns":400000000,"cold_start_policy":"current_job_free_once_then_fixed050_three_rti_v1","command_max_n":25,"command_min_n":-25,"cruise_speed":0.6,"dds_depth":1,"deadline_ns":150000000,"diagnostic_contract_revision":10,"dt":0.2,"execute_qualified":false,"expected_child_frame":"wamv/base_link","expected_imu_frame":"wamv/wamv/base_link/imu_sensor","expected_pose_frame":"map","fault_injection_enabled":true,"history_capacity":256,"hold_ns":600000000,"hydro":{"Iz":2.13,"Nr":-3.105,"Nr_dot":-3.41,"Nrr":-0.71,"Nv":0,"Nv_dot":-0.1817725,"Nvv":0,"Xu":-2.272063,"Xu_dot":-2,"Xuu":-11.571784,"Yr":0,"Yr_dot":-0.1817725,"Yrr":0,"Yv":-2.629019,"Yv_dot":-8,"Yvv":-0.05,"d_thruster":0.25,"mass":14.2,"xg":0.12},"imu_age_ns":100000000,"imu_sim_lag_ns":100000000,"input_topics":{"imu":"/wamv/sensors/imu/imu/data","odom":"/wamv/sensors/position/ground_truth_odometry","path":"/path/reference","profile":"/path/reference_profile"},"job_cdr_max_bytes":6460,"kill_postcheck_ns":1000000000,"log_capacity":512,"map_scale":1,"max_candidate_bytes":16384,"max_job_bytes":8192,"max_path_frame_bytes":128,"max_path_points":2048,"max_profile_dims":4,"max_profile_label_bytes":64,"max_profile_rows":2048,"mixed_skew_ns":100000000,"nominal_hash":"78d7133fd4f11d47bd534d820b02489e440bd8664bef254893e830fe4bc7dc84","odom_age_ns":100000000,"odom_sim_lag_ns":100000000,"output_topics":{"left":"/wamv/thrusters/left/thrust","right":"/wamv/thrusters/right/thrust"},"parameters_are_diagnostic_only":true,"pending_final_calibration":["rho_n_s","hold_ns","activation_tolerance","source ages","RTF and pause","jitter/gap/publish","watchdog and cleanup","worker capability validated callback receipt lease; no source packet sequence/send time"],"preparation_retry_policy":"authenticated_phase_reference_pair_completion_v1","propagation_semantics":"publisher-side piecewise held history from accepted odom stamp, mixed r retained with separate IMU stamp; future held current command; RK4 nominal point prediction","publish_budget_ns":5000000,"publish_gap_ns":240000000,"publisher_max_n":100,"qualification":"temporary_shadow_diagnostic","recording_ready_timeout_ns":10000000000,"reference_epoch_policy":"first_successful_job_submit_completion_target_sim_v1","reference_sampling_policy":"first_target_task_time_profile_v1","reference_start_offset":0,"resource_budget_scope":"application_typed_domain_cdr1_with_4_byte_encapsulation","resource_policy":"typed_domain_bounds_before_copy_v1","rho_n_s":80,"rtf_high":1.05,"rtf_low":0.95,"schema":"p1-execution-contract-v2","shutdown_grace_ns":2500000000,"source_age_semantics":"receipt age uses CLOCK_MONOTONIC; physical source lag/future uses clock sim plus 1:1 monotonic elapsed; IMU only when mixed","source_future_slack_ns":20000000,"target_sim_slack_ns":20000000,"term_grace_ns":1000000000,"tick_jitter_ns":20000000,"worker_capability_lease_policy":"valid_identity_capability_callback_receipt_lease_terminal_until_new_run","worker_capability_receipt_timeout_ns":600000000,"worker_capability_source_freshness_available":false,"worker_failure_policy":"terminal_on_failed_or_invalid_native_result","worker_grace_ns":500000000})P1BASE");
  return value;
}
inline const std::set<std::string> & integer_contract_fields() {
  static const std::set<std::string> fields = {"N","T_ns","activation_sensor_history_capacity","activation_validation_attempts","active_watchdog_ns","candidate_cdr_max_bytes","clock_age_ns","clock_pause_confirm_ns","dds_depth","deadline_ns","diagnostic_contract_revision","history_capacity","hold_ns","imu_age_ns","imu_sim_lag_ns","job_cdr_max_bytes","kill_postcheck_ns","log_capacity","max_candidate_bytes","max_job_bytes","max_path_frame_bytes","max_path_points","max_profile_dims","max_profile_label_bytes","max_profile_rows","mixed_skew_ns","odom_age_ns","odom_sim_lag_ns","publish_budget_ns","publish_gap_ns","recording_ready_timeout_ns","reference_start_offset","shutdown_grace_ns","source_future_slack_ns","target_sim_slack_ns","term_grace_ns","tick_jitter_ns","worker_capability_receipt_timeout_ns","worker_grace_ns"};return fields;
}
inline const std::set<std::string> & resource_contract_fields() {
  static const std::set<std::string> fields = {"candidate_cdr_max_bytes","dds_depth","history_capacity","job_cdr_max_bytes","log_capacity","max_candidate_bytes","max_job_bytes","max_path_frame_bytes","max_path_points","max_profile_dims","max_profile_label_bytes","max_profile_rows","resource_budget_scope","resource_policy"};return fields;
}
inline const std::set<std::string> & special_contract_fields() {
  static const std::set<std::string> fields = {"diagnostic_contract_revision","execute_qualified","fault_injection_enabled","parameters_are_diagnostic_only","pending_final_calibration","qualification","schema"};return fields;
}
inline void contract_require(bool okay,const std::string & reason) {
  if(!okay)throw std::runtime_error("contract validation: "+reason);
}
inline bool strict_i64(const nlohmann::json & value) {
  if(!value.is_number_integer())return false;
  return !value.is_number_unsigned() || value.get<uint64_t>()<=uint64_t(std::numeric_limits<int64_t>::max());
}
inline void contract_value_type(const nlohmann::json & actual,const nlohmann::json & expected,const std::string & key) {
  if(expected.is_boolean())contract_require(actual.is_boolean(),"bool required: "+key);
  else if(expected.is_number()) {
    contract_require(actual.is_number() && std::isfinite(actual.get<double>()),"finite number required: "+key);
    if(integer_contract_fields().count(key))contract_require(strict_i64(actual),"int64 JSON integer required: "+key);
  } else if(expected.is_string())contract_require(actual.is_string(),"string required: "+key);
  else if(expected.is_array()) {
    contract_require(actual.is_array(),"array required: "+key);
    if(key=="pending_final_calibration") {
      contract_require(actual.size()<=32,"pending list bound");
      for(const auto & item:actual)contract_require(item.is_string() && !item.get_ref<const std::string &>().empty() && item.get_ref<const std::string &>().size()<=256,"pending string bound");
    } else {
      contract_require(actual.size()==expected.size(),"array shape: "+key);
      for(size_t i=0;i<actual.size();++i)contract_value_type(actual[i],expected[i],key);
    }
  } else if(expected.is_object()) {
    contract_require(actual.is_object() && actual.size()==expected.size(),"object shape: "+key);
    for(auto it=expected.begin();it!=expected.end();++it) {
      contract_require(actual.contains(it.key()),"nested field missing: "+key+"."+it.key());
      contract_value_type(actual.at(it.key()),it.value(),it.key());
    }
  } else contract_require(false,"unsupported normative value type");
}
// DiagnosticExecute is a fourth profile, introduced for W1. It carries the same
// field set as the frozen formal contract but admits a fault-capable Worker and
// permits mode=="execute" so the Regulator's tick loop (and therefore the active
// watchdog) actually runs. It is deliberately NOT reachable from v2/v3: those
// keep their exact previous acceptance and rejection rules.
enum class ContractProfile { Diagnostic,PreFreeze,Frozen,DiagnosticExecute };
inline ContractProfile validate_contract_fields(const nlohmann::json & c) {
  contract_require(c.is_object() && c.contains("schema") && c.at("schema").is_string(),"schema object required");
  const auto schema=c.at("schema").get<std::string>();
  const bool diagnostic_execute=schema=="p1-execution-contract-v4";
  const bool formal=schema=="p1-execution-contract-v3"||diagnostic_execute;
  contract_require(formal||schema=="p1-execution-contract-v2","unknown schema");
  const auto & base=candidate_baseline();std::set<std::string> expected;
  for(auto it=base.begin();it!=base.end();++it)if(!formal||it.key()!="diagnostic_contract_revision")expected.insert(it.key());
  if(formal)for(const auto & key:{"execution_contract_revision","resource_contract_revision","supported_parameter_profile","freeze_evidence_sha256"})expected.insert(key);
  contract_require(c.size()==expected.size(),"missing or unknown top-level fields");
  for(const auto & key:expected)contract_require(c.contains(key),"missing field: "+key);
  auto selected=base;
  if(formal){
    contract_require(c.at("supported_parameter_profile").is_string(),"profile string required");
    const auto profile=c.at("supported_parameter_profile").get<std::string>();
    const auto & profiles=formal_profile_overrides();
    contract_require(profiles.contains(profile),"unsupported parameter profile");
    selected.update(profiles.at(profile));
  }
  for(auto it=selected.begin();it!=selected.end();++it) {
    const auto key=it.key();if(formal&&key=="diagnostic_contract_revision")continue;
    contract_value_type(c.at(key),it.value(),key);
    if(!special_contract_fields().count(key) && !resource_contract_fields().count(key))
      contract_require(c.at(key)==it.value(),"unsupported fixed candidate parameter: "+key);
  }
  resource_limits_from_contract(c);
  if(!formal) {
    for(const auto & key:special_contract_fields())contract_require(c.at(key)==base.at(key),"diagnostic flag or policy mismatch: "+key);
    return ContractProfile::Diagnostic;
  }
  for(const auto & key:{"execution_contract_revision","resource_contract_revision"})
    contract_require(strict_i64(c.at(key)) && c.at(key).get<int64_t>()==1,"unsupported formal revision: "+std::string(key));
  contract_require(c.at("freeze_evidence_sha256").is_string(),"freeze evidence marker type");
  if(diagnostic_execute) {
    // W1 diagnostic execute profile. The flags are the opposite of Frozen on the
    // two fields v2_diagnostic::Block requires, while execute stays permitted so
    // the Regulator tick loop runs and the active watchdog can be observed.
    const auto qualification=c.at("qualification").get<std::string>();
    contract_require(qualification=="execution_diagnostic_only","v4 qualification must be execution_diagnostic_only");
    contract_require(c.at("fault_injection_enabled")==true,"v4 requires fault injection enabled");
    contract_require(c.at("execute_qualified")==false,"v4 must not claim execute qualification");
    contract_require(c.at("parameters_are_diagnostic_only")==true,"v4 parameters are diagnostic only");
    contract_require(std::regex_match(c.at("freeze_evidence_sha256").get<std::string>(),std::regex("[0-9a-f]{64}")),"v4 evidence hash marker");
    return ContractProfile::DiagnosticExecute;
  }
  contract_require(c.at("fault_injection_enabled")==false,"formal fault injection prohibited");
  const auto qualification=c.at("qualification").get<std::string>();
  if(qualification=="execution_pre_freeze") {
    contract_require(c.at("execute_qualified")==false && c.at("parameters_are_diagnostic_only")==true,"pre-freeze qualification flags");
    contract_require(c.at("pending_final_calibration")==base.at("pending_final_calibration") && c.at("freeze_evidence_sha256")=="","pre-freeze pending evidence");
    return ContractProfile::PreFreeze;
  }
  contract_require(qualification=="execution_frozen","unknown formal qualification");
  contract_require(c.at("execute_qualified")==true && c.at("parameters_are_diagnostic_only")==false,"frozen qualification flags");
  contract_require(c.at("pending_final_calibration").empty(),"frozen pending calibration remains");
  contract_require(std::regex_match(c.at("freeze_evidence_sha256").get<std::string>(),std::regex("[0-9a-f]{64}")),"frozen evidence hash marker");
  return ContractProfile::Frozen;
}
inline void validate_contract_mode(const nlohmann::json & c,const std::string & mode) {
  const auto profile=validate_contract_fields(c);
  const bool okay=profile==ContractProfile::Diagnostic?(mode=="no_output"||mode=="shadow"):
    profile==ContractProfile::PreFreeze?mode=="no_output":
    profile==ContractProfile::DiagnosticExecute?(mode=="no_output"||mode=="execute"):
    (mode=="no_output"||mode=="execute");
  contract_require(okay,"profile/mode mismatch");
}
inline void require_runtime_contract_mode(const nlohmann::json & c,const std::string & mode) {
  validate_contract_mode(c,mode);
  // The v4 diagnostic profile is the only execute-capable path that does not
  // require the ordinary production release, because it is explicitly scoped to
  // an isolated diagnostic run and its contract carries execute_qualified=false.
  if(mode=="execute"&&!physical_execute_release_enabled&&
     validate_contract_fields(c)!=ContractProfile::DiagnosticExecute)
    throw std::runtime_error("physical execute release is disabled until B5/M4");
}
inline nlohmann::json parse_unique_contract(const std::string & text) {
  contract_require(!text.empty() && text.size()<=65536,"bounded contract file required");
  std::vector<std::set<std::string>> objects;
  auto callback=[&objects](int,nlohmann::json::parse_event_t event,nlohmann::json & value) {
    if(event==nlohmann::json::parse_event_t::object_start)objects.emplace_back();
    else if(event==nlohmann::json::parse_event_t::key) {
      if(objects.empty()||!objects.back().insert(value.get<std::string>()).second)throw std::runtime_error("duplicate contract JSON key");
    }else if(event==nlohmann::json::parse_event_t::object_end)objects.pop_back();
    return true;
  };
  return nlohmann::json::parse(text,callback);
}
}  // namespace p1
