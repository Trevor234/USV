// SPDX-License-Identifier: MIT
// Shared pure contract tests. No rclcpp initialization or middleware call.
#ifdef REFERENCE_WORKER_CONTRACT
#include "worker/p1_full_contract.hpp"
#else
#include "observer/src/shadow/p1_full_contract.hpp"
#endif
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
using Json=nlohmann::json;
Json read(const std::filesystem::path &path) {
  std::ifstream input(path);
  if(!input)throw std::runtime_error("missing contract test input: "+path.string());
  std::string raw((std::istreambuf_iterator<char>(input)),{});
  return p1::parse_unique_contract(raw);
}
bool rejected(const Json &value) {
  try {p1::validate_contract_fields(value);return false;}
  catch(const std::exception &) {return true;}
}
bool runtime_rejected(const Json &value,const std::string &mode) {
  try {p1::require_runtime_contract_mode(value,mode);return false;}
  catch(const std::exception &) {return true;}
}
}

int main() {
  unsigned checks=0;
  const auto check=[&](bool good,const std::string &label) {
    ++checks;
    if(!good)throw std::runtime_error("reference contract check "+std::to_string(checks)+": "+label);
  };
  const auto directory=std::filesystem::path(__FILE__).parent_path();
  const auto old=read(directory.parent_path()/"authored_D1_positive_chain_20261015_v18/controlled_phase/controlled_contract_v1.json");
  const auto configured=read(directory/"pair_wakeup_contract_v1.json");
  auto expected=old;
  expected["reference_start_offset"]=0;
  expected["reference_sampling_policy"]="first_target_task_time_profile_v1";
  expected["diagnostic_contract_revision"]=9;
  expected["cold_start_policy"]="current_job_free_once_then_fixed050_three_rti_v1";
  expected["preparation_retry_policy"]="authenticated_phase_reference_pair_completion_v1";
  expected["reference_epoch_policy"]="first_successful_job_submit_completion_target_sim_v1";
  const auto base=p1::candidate_baseline();
  check(base==expected,"all baseline fields except the six declared deltas are unchanged");
  check(base==configured,"baked contract equals the actual projected JSON input");
  check(p1::validate_contract_fields(base)==p1::ContractProfile::Diagnostic,"new contract is valid diagnostic");
  check(std::string(p1::full_contract_spec_sha256)=="ad15bcbb6e86fbd4b2127387663923e9ef0e7c46b7e66ac43ee66cc7e60bdeb4","new specification identity");
  check(std::string(p1::contract_parameter_profile)=="P1_causal_cold_diagnostic_20261018_01","new profile is explicitly diagnostic");
  check(!p1::physical_execute_release_enabled,"physical execute remains disabled");
  check(rejected(old),"old contract lacking sampling policy is rejected");
  {auto value=base;value.erase("reference_sampling_policy");check(rejected(value),"sampling policy required");}
  for(const auto &policy:{"","nearest_point_index","foreign","projected_profile_time_v2"}) {
    auto value=base;value["reference_sampling_policy"]=policy;check(rejected(value),"foreign policy rejected");
  }
  {auto v=base;v.erase("reference_epoch_policy");check(rejected(v),"epoch policy required");}
  for(const auto &value:{Json(""),Json("ready_time"),Json("per_tick_projection"),Json(false),Json(1)}){auto v=base;v["reference_epoch_policy"]=value;check(rejected(v),"foreign epoch policy rejected");}
  {auto v=base;v.erase("preparation_retry_policy");check(rejected(v),"retry policy required");}
  for(const auto &v0:{Json(""),Json("timer_retry"),Json("ignore_deadline"),Json(false)}){auto v=base;v["preparation_retry_policy"]=v0;check(rejected(v),"foreign retry policy rejected");}
  for(const auto &offset:{Json(2),Json(1),Json(-1),Json(false),Json(0.0)}) {
    auto value=base;value["reference_start_offset"]=offset;check(rejected(value),"offset exact integer zero required");
  }
  for(const auto &revision:{Json(7),Json(8),Json(false),Json(9.0)}) {
    auto value=base;value["diagnostic_contract_revision"]=revision;check(rejected(value),"diagnostic revision exact integer nine required");
  }
  for(const auto &key:{"Q","R","Rd"}) {
    for(size_t index=0;index<base[key].size();++index) {
      auto value=base;value[key][index]=value[key][index].get<double>()+.001;
      check(rejected(value),std::string(key)+" component must remain unchanged");
    }
  }
  for(const auto &key:{"Qf_scale","N","dt","hold_ns","rho_n_s","backend_rate_n_s","command_min_n","command_max_n","deadline_ns","T_ns","publish_budget_ns","clock_age_ns"}) {
    auto value=base;value[key]=value[key].get<double>()+.001;
    check(rejected(value),std::string(key)+" remains fixed");
  }
  for(auto it=base["hydro"].begin();it!=base["hydro"].end();++it) {
    auto value=base;value["hydro"][it.key()]=it.value().get<double>()+.001;
    check(rejected(value),"hydrodynamic model component "+it.key()+" unchanged");
  }
  for(size_t index=0;index<base["activation_tolerance"].size();++index) {
    auto value=base;value["activation_tolerance"][index]=value["activation_tolerance"][index].get<double>()+.001;
    check(rejected(value),"state tolerance component unchanged");
  }
  {auto value=base;value["execute_qualified"]=true;check(rejected(value),"no execute qualification inferred");}
  {auto value=base;value["parameters_are_diagnostic_only"]=false;check(rejected(value),"diagnostic scope remains mandatory");}
  {auto value=base;value["qualification"]="execution_frozen";check(rejected(value),"qualification relabel rejected");}
  {auto value=base;value["unknown_policy"]=true;check(rejected(value),"unknown field rejected");}
  {auto value=base;value["reference_sampling_policy"]=false;check(rejected(value),"policy type cannot be boolean");}
  {auto value=base;value["R"][0]=std::numeric_limits<double>::quiet_NaN();check(rejected(value),"nonfinite cost rejected");}
  {auto v=base;v.erase("cold_start_policy");check(rejected(v),"cold policy required");}
  for(const auto &value:{Json(""),Json("free_only"),Json(false),Json(1)}){auto v=base;v["cold_start_policy"]=value;check(rejected(v),"exact cold policy required");}
  check(!runtime_rejected(base,"shadow"),"shadow diagnostic remains valid");
  check(!runtime_rejected(base,"no_output"),"no-output diagnostic remains valid");
  check(runtime_rejected(base,"execute"),"diagnostic execute denied by actual runtime entry");
  check(runtime_rejected(base,"foreign_mode"),"unknown runtime mode denied");
  std::cout<<"reference contract checks="<<checks<<" passed; six declared sampling deltas only; no ROS calls\n";
}
