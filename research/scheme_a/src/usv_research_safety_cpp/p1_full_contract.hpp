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
inline constexpr const char * contract_parameter_profile = "F5_P1_candidate_20261007_01";
inline constexpr const char * full_contract_spec_sha256 = "33fb4a5eef93aa6abce5a61e7549dd7217f90c9572e5097791731fbb89661ffd";
inline const nlohmann::json & candidate_baseline() {
  static const auto value = nlohmann::json::parse(R"P1BASE({"schema":"p1-execution-contract-v2","qualification":"temporary_shadow_diagnostic","execute_qualified":false,"clock":"CLOCK_MONOTONIC","N":20,"dt":0.2,"T_ns":200000000,"deadline_ns":150000000,"baseline_input":"F5_20261005_atomic_freeze_01","nominal_hash":"78d7133fd4f11d47bd534d820b02489e440bd8664bef254893e830fe4bc7dc84","Q":[20,20,50,8,1,8],"R":[0.05,0.05],"Rd":[0.2,0.2],"Qf_scale":8,"hydro":{"mass":14.2,"Iz":2.13,"xg":0.12,"d_thruster":0.25,"Xu_dot":-2,"Yv_dot":-8,"Yr_dot":-0.1817725,"Nv_dot":-0.1817725,"Nr_dot":-3.41,"Xu":-2.272063,"Yv":-2.629019,"Yr":0,"Nv":0,"Nr":-3.105,"Xuu":-11.571784,"Yvv":-0.05,"Yrr":0,"Nvv":0,"Nrr":-0.71},"command_min_n":-25,"command_max_n":25,"map_scale":1,"publisher_max_n":100,"backend_rate_n_s":80,"rho_n_s":80,"hold_ns":600000000,"activation_tolerance":[0.25,0.25,0.15,0.3,0.2,0.15],"odom_age_ns":100000000,"imu_age_ns":100000000,"mixed_skew_ns":100000000,"clock_age_ns":100000000,"rtf_low":0.95,"rtf_high":1.05,"clock_pause_confirm_ns":400000000,"target_sim_slack_ns":20000000,"tick_jitter_ns":20000000,"publish_gap_ns":240000000,"publish_budget_ns":5000000,"active_watchdog_ns":1000000000,"worker_grace_ns":500000000,"term_grace_ns":1000000000,"kill_postcheck_ns":1000000000,"shutdown_grace_ns":2500000000,"max_path_points":2048,"max_profile_rows":2048,"max_job_bytes":8192,"max_candidate_bytes":16384,"history_capacity":256,"log_capacity":512,"dds_depth":1,"fault_injection_enabled":true,"reference_start_offset":2,"cruise_speed":0.6,"input_topics":{"odom":"/wamv/sensors/position/ground_truth_odometry","imu":"/wamv/sensors/imu/imu/data","path":"/path/reference","profile":"/path/reference_profile"},"output_topics":{"left":"/wamv/thrusters/left/thrust","right":"/wamv/thrusters/right/thrust"},"expected_pose_frame":"map","expected_child_frame":"wamv/base_link","propagation_semantics":"publisher-side piecewise held history from accepted odom stamp, mixed r retained with separate IMU stamp; future held current command; RK4 nominal point prediction","pending_final_calibration":["rho_n_s","hold_ns","activation_tolerance","source ages","RTF and pause","jitter/gap/publish","watchdog and cleanup","worker capability validated callback receipt lease; no source packet sequence/send time"],"parameters_are_diagnostic_only":true,"diagnostic_contract_revision":5,"odom_sim_lag_ns":100000000,"imu_sim_lag_ns":100000000,"source_future_slack_ns":20000000,"recording_ready_timeout_ns":10000000000,"expected_imu_frame":"wamv/wamv/base_link/imu_sensor","source_age_semantics":"receipt age uses CLOCK_MONOTONIC; physical source lag/future uses clock sim plus 1:1 monotonic elapsed; IMU only when mixed","worker_failure_policy":"terminal_on_failed_or_invalid_native_result","worker_capability_lease_policy":"valid_identity_capability_callback_receipt_lease_terminal_until_new_run","worker_capability_receipt_timeout_ns":600000000,"worker_capability_source_freshness_available":false,"resource_policy":"typed_domain_bounds_before_copy_v1","resource_budget_scope":"application_typed_domain_cdr1_with_4_byte_encapsulation","job_cdr_max_bytes":7361,"candidate_cdr_max_bytes":9708,"max_profile_dims":4,"max_profile_label_bytes":64,"max_path_frame_bytes":128})P1BASE");
  return value;
}
inline const std::set<std::string> & integer_contract_fields() {
  static const std::set<std::string> fields = {"N","T_ns","active_watchdog_ns","candidate_cdr_max_bytes","clock_age_ns","clock_pause_confirm_ns","dds_depth","deadline_ns","diagnostic_contract_revision","history_capacity","hold_ns","imu_age_ns","imu_sim_lag_ns","job_cdr_max_bytes","kill_postcheck_ns","log_capacity","max_candidate_bytes","max_job_bytes","max_path_frame_bytes","max_path_points","max_profile_dims","max_profile_label_bytes","max_profile_rows","mixed_skew_ns","odom_age_ns","odom_sim_lag_ns","publish_budget_ns","publish_gap_ns","recording_ready_timeout_ns","reference_start_offset","shutdown_grace_ns","source_future_slack_ns","state_age_ns","target_sim_slack_ns","term_grace_ns","tick_jitter_ns","worker_capability_receipt_timeout_ns","worker_grace_ns"};return fields;
}
inline const std::set<std::string> & resource_contract_fields() {
  static const std::set<std::string> fields = {"resource_policy","resource_budget_scope","max_path_points","max_profile_rows","max_job_bytes","max_candidate_bytes","history_capacity","log_capacity","dds_depth","max_profile_dims","max_profile_label_bytes","max_path_frame_bytes","job_cdr_max_bytes","candidate_cdr_max_bytes"};return fields;
}
inline const std::set<std::string> & special_contract_fields() {
  static const std::set<std::string> fields = {"schema","qualification","execute_qualified","parameters_are_diagnostic_only","fault_injection_enabled","diagnostic_contract_revision","pending_final_calibration"};return fields;
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
enum class ContractProfile { Diagnostic,PreFreeze,Frozen,ControlledSim,ShipboardCommissioning,ShipboardDryRun };
// 实船调试服务接管的合同字段集合（不含资源字段）。旧 profile 一律不认这个 schema。
inline const std::set<std::string> & shipboard_commissioning_fields() {
  static const std::set<std::string> fields = {"schema","qualification","execute_qualified","parameters_are_diagnostic_only","fault_injection_enabled","diagnostic_contract_revision","clock","input_topics","N","dt","T_ns","deadline_ns","nominal_hash","Q","R","Rd","Qf_scale","hydro","command_min_n","command_max_n","backend_rate_n_s","worker_failure_policy","recording_ready_timeout_ns","worker_capability_receipt_timeout_ns"};
  return fields;
}
inline constexpr const char * shipboard_commissioning_schema = "p1-shipboard-commissioning-v1";
inline constexpr const char * shipboard_commissioning_qualification = "shipboard_commissioning";
inline constexpr const char * shipboard_commissioning_mode = "commissioning";
// 实船干跑求解（真传感 + 真 acados 求解 + 零物理输出）合同字段集合（不含资源字段）。
inline const std::set<std::string> & shipboard_dry_run_fields() {
  static const std::set<std::string> fields = []() {
    auto f = shipboard_commissioning_fields();
    for (const char * k : {"expected_pose_frame","expected_child_frame","expected_imu_frame","reference_start_offset","cruise_speed","rho_n_s","odom_age_ns","imu_age_ns","state_age_ns","map_scale","publisher_max_n"}) f.insert(k);
    return f;
  }();
  return fields;
}
inline constexpr const char * shipboard_dry_run_schema = "p1-shipboard-dry-run-v1";
inline constexpr const char * shipboard_dry_run_qualification = "shipboard_dry_run";
inline constexpr const char * shipboard_dry_run_mode = "shipboard_dry_run";
inline const nlohmann::json & shipboard_input_topics() {
  static const auto value = nlohmann::json::parse(R"P1TOPICS({"state":"/mavros/state","odom":"/mavros/local_position/odom","imu":"/mavros/imu/data","path":"/path/reference","profile":"/path/reference_profile"})P1TOPICS");
  return value;
}
inline void validate_shipboard_common(const nlohmann::json & c,const std::set<std::string> & core_fields,const std::set<std::string> & dry_run_calibrated_fields,const std::string & expected_qualification) {
  contract_require(c.at("qualification")==expected_qualification,
                   "shipboard schema requires matching qualification: "+expected_qualification);
  std::set<std::string> expected=core_fields;
  for(const auto & key:resource_contract_fields())expected.insert(key);
  contract_require(c.size()==expected.size(),"missing or unknown top-level fields");
  for(const auto & key:expected)contract_require(c.contains(key),"missing field: "+key);
  const auto & base=candidate_baseline();
  for(auto it=base.begin();it!=base.end();++it) {
    const auto key=it.key();
    if(!expected.count(key)||key=="input_topics")continue;
    contract_value_type(c.at(key),it.value(),key);
    if(!special_contract_fields().count(key)&&!resource_contract_fields().count(key)&&!dry_run_calibrated_fields.count(key))
      contract_require(c.at(key)==it.value(),"unsupported fixed shipboard parameter: "+key);
  }
  contract_require(c.at("execute_qualified")==false,"shipboard execute_qualified must be false");
  contract_require(c.at("parameters_are_diagnostic_only")==true,
                   "shipboard parameters_are_diagnostic_only must be true");
  contract_require(c.at("fault_injection_enabled")==false,"shipboard fault injection prohibited");
  contract_require(c.at("worker_failure_policy")==base.at("worker_failure_policy"),
                   "shipboard worker failure policy is fixed");
  contract_require(c.at("input_topics").is_object()&&c.at("input_topics")==shipboard_input_topics(),
                   "shipboard input topics are fixed");
  resource_limits_from_contract(c);
}
inline ContractProfile validate_contract_fields(const nlohmann::json & c) {
  contract_require(c.is_object() && c.contains("schema") && c.at("schema").is_string(),"schema object required");
  // 受控仿真不是物理执行：它从不发布到 physical 主题，也不需要 B5/M4 放行。
  // 这个 profile 必须是**显式**的合同声明，不能被 v2 默认值意外获得。
  if(c.at("schema").is_string() && c.at("schema").get<std::string>()=="p1-execution-contract-v2-sim") {
    contract_require(c.contains("qualification") && c.at("qualification")=="controlled_sim",
                     "sim schema requires controlled_sim qualification");
    contract_require(c.contains("fault_injection_enabled"),"sim schema requires the fault flag");
    // 闭环故障注入（迟到/重复/hold 到期/求解阻塞）编入普通二进制，但**必须**
    // 由这份合同显式启用的开关门控。声明缺失即拒绝，不允许"默认开"。
    contract_require(c.contains("controlled_sim_faults_enabled") &&
                     c.at("controlled_sim_faults_enabled").is_boolean(),
                     "sim schema requires the controlled_sim faults flag");
    resource_limits_from_contract(c);
    return ContractProfile::ControlledSim;
  }
  const auto schema=c.at("schema").get<std::string>();
  // 实船调试服务接管：无执行资格，只允许 commissioning 模式。字段集合是
  // "列名字面集合 ∪ 资源字段"，任何缺失/未知/重复键都在这里拒绝。
  if(schema==shipboard_commissioning_schema) {
    static const std::set<std::string> no_extra_calibrated{};
    validate_shipboard_common(c,shipboard_commissioning_fields(),no_extra_calibrated,shipboard_commissioning_qualification);
    return ContractProfile::ShipboardCommissioning;
  }
  if(schema==shipboard_dry_run_schema) {
    static const std::set<std::string> dry_run_calibrated = {"expected_child_frame","expected_imu_frame","odom_age_ns","imu_age_ns","recording_ready_timeout_ns","worker_capability_receipt_timeout_ns"};
    validate_shipboard_common(c,shipboard_dry_run_fields(),dry_run_calibrated,shipboard_dry_run_qualification);
    contract_require(c.at("expected_pose_frame")=="map","dry_run expected_pose_frame must be map");
    contract_require(c.at("expected_child_frame")=="base_link","dry_run expected_child_frame must be base_link");
    contract_require(c.at("expected_imu_frame")=="base_link","dry_run expected_imu_frame must be base_link");
    const auto check_ns_bound=[&](const char * key,int64_t lo,int64_t hi){
      contract_require(strict_i64(c.at(key)),std::string("int64 required: ")+key);
      const auto v=c.at(key).get<int64_t>();
      contract_require(v>=lo&&v<=hi,std::string("dry_run bound out of range: ")+key);
    };
    check_ns_bound("odom_age_ns",100000000LL,5000000000LL);
    check_ns_bound("imu_age_ns",100000000LL,5000000000LL);
    check_ns_bound("state_age_ns",500000000LL,10000000000LL);
    check_ns_bound("worker_capability_receipt_timeout_ns",200000000LL,5000000000LL);
    check_ns_bound("recording_ready_timeout_ns",1000000000LL,60000000000LL);
    return ContractProfile::ShipboardDryRun;
  }
  const bool formal=schema=="p1-execution-contract-v3";
  contract_require(formal||schema=="p1-execution-contract-v2","unknown schema");
  const auto & base=candidate_baseline();std::set<std::string> expected;
  for(auto it=base.begin();it!=base.end();++it)if(!formal||it.key()!="diagnostic_contract_revision")expected.insert(it.key());
  if(formal)for(const auto & key:{"execution_contract_revision","resource_contract_revision","supported_parameter_profile","freeze_evidence_sha256"})expected.insert(key);
  contract_require(c.size()==expected.size(),"missing or unknown top-level fields");
  for(const auto & key:expected)contract_require(c.contains(key),"missing field: "+key);
  for(auto it=base.begin();it!=base.end();++it) {
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
  contract_require(c.at("supported_parameter_profile").is_string() && c.at("supported_parameter_profile")==contract_parameter_profile,"unsupported parameter profile");
  contract_require(c.at("freeze_evidence_sha256").is_string(),"freeze evidence marker type");
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
  bool okay;
  if(profile==ContractProfile::ControlledSim)okay=mode=="controlled_sim";
  else if(profile==ContractProfile::ShipboardCommissioning)okay=mode==shipboard_commissioning_mode;
  else if(profile==ContractProfile::ShipboardDryRun)okay=mode==shipboard_dry_run_mode;
  else if(profile==ContractProfile::Diagnostic)okay=(mode=="no_output"||mode=="shadow");
  else if(profile==ContractProfile::PreFreeze)okay=mode=="no_output";
  else okay=(mode=="no_output"||mode=="execute");
  contract_require(okay,"profile/mode mismatch");
}
inline void require_runtime_contract_mode(const nlohmann::json & c,const std::string & mode) {
  validate_contract_mode(c,mode);
  if(mode=="execute"&&!physical_execute_release_enabled)
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
