// SPDX-License-Identifier: MIT
#pragma once
#include "p1_owned_identity.hpp"
#include <usv_research_interfaces/msg/execution_decision.hpp>
#include <usv_research_interfaces/msg/solve_job.hpp>
#include <usv_research_interfaces/msg/applied_control.hpp>
namespace controlled {
constexpr int64_t period_ns=200000000;
constexpr int64_t pulse_offset_ns=100000000;
constexpr double pulse_n=0.1;
constexpr const char *baseline="CONTROLLED_PHASE_20261015_DIAGNOSTIC_01";
inline bool mode_valid(const std::string &mode){return mode=="A2"||mode=="B"||mode=="C";}
inline bool decision_domain(const usv_research_interfaces::msg::ExecutionDecision &d,const std::string &run,const std::string &contract,int64_t now) {
 return d.schema_version=="p1-execution-decision-v2"&&d.run_id==run&&d.contract_hash==contract&&d.boot_id==p1_owned::boot_id()
  &&d.mode=="shadow"&&d.diagnostic_only&&d.sequence>0&&d.tick_planned_ns>0&&d.tick_planned_ns<=d.activation_commit_ns
  &&d.activation_commit_ns<=d.tick_end_ns&&d.tick_end_ns<=now&&now<d.tick_planned_ns+period_ns
  &&std::all_of(d.final_n.begin(),d.final_n.end(),[](double n){return std::isfinite(n)&&n>=-25&&n<=25;});
}
inline bool job_domain(const usv_research_interfaces::msg::SolveJob &j,const std::string &run,const std::string &contract,int64_t now) {
 return j.schema_version=="p1-solve-job-v1"&&j.run_id==run&&j.boot_id==p1_owned::boot_id()&&j.contract_hash==contract&&j.job_id>0
  &&j.tick_origin_steady_ns>0&&j.tick_origin_steady_ns<=j.freeze_steady_ns&&j.freeze_steady_ns<=now
  &&j.target_steady_ns==j.tick_origin_steady_ns+period_ns&&now<j.tick_origin_steady_ns+pulse_offset_ns;
}
inline p1_owned::Json phase(const p1_owned::Json &identity,const std::string &contract,
 const usv_research_interfaces::msg::ExecutionDecision &d,const usv_research_interfaces::msg::AppliedControl &a,int64_t emitted) {
 p1_owned::require(identity.at("baseline_id")==baseline&&a.baseline_id==baseline&&a.run_id==identity.at("run_id")&&a.producer_instance_id==identity.at("producer_instance_id")
 &&a.sequence>0&&d.sequence>0&&a.cycle_sequence==d.sequence&&p1_owned::sha256_shape(contract)
 &&std::all_of(a.final_n.begin(),a.final_n.end(),[](double n){return std::isfinite(n)&&n>=-25&&n<=25;}),"controlled_phase_actual_identity_domain");
 p1_owned::require(a.left_publish_success&&a.right_publish_success&&a.left_publish_start_steady_ns>0&&a.left_publish_start_steady_ns<=a.left_publish_end_steady_ns
 &&a.left_publish_end_steady_ns<=a.right_publish_start_steady_ns&&a.right_publish_start_steady_ns<=a.right_publish_end_steady_ns&&a.right_publish_end_steady_ns<=emitted&&emitted<d.tick_planned_ns+150000000,"controlled_phase_actual_order_or_late_for_freeze");
 return {{"schema","p1-controlled-owner-phase-v1"},{"run_id",identity.at("run_id")},{"boot_id",p1_owned::boot_id()},
  {"contract_sha256",contract},{"baseline_id",baseline},{"producer_instance_id",identity.at("producer_instance_id")},
  {"decision_sequence",d.sequence},{"tick",d.tick},{"planned_ns",d.tick_planned_ns},{"applied_sequence",a.sequence},
  {"command_n",a.final_n},{"start_ns",{a.left_publish_start_steady_ns,a.right_publish_start_steady_ns}},
  {"end_ns",{a.left_publish_end_steady_ns,a.right_publish_end_steady_ns}},{"held_until_ns",d.tick_planned_ns+period_ns},
  {"emitted_ns",emitted},{"stage_qualified",false},{"execute_qualified",false}};
}
} // namespace controlled
