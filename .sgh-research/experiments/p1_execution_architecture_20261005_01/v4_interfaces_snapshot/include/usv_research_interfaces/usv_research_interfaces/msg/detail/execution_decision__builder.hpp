// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from usv_research_interfaces:msg/ExecutionDecision.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/execution_decision.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__EXECUTION_DECISION__BUILDER_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__EXECUTION_DECISION__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "usv_research_interfaces/msg/detail/execution_decision__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace usv_research_interfaces
{

namespace msg
{

namespace builder
{

class Init_ExecutionDecision_activation_rtf
{
public:
  explicit Init_ExecutionDecision_activation_rtf(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  ::usv_research_interfaces::msg::ExecutionDecision activation_rtf(::usv_research_interfaces::msg::ExecutionDecision::_activation_rtf_type arg)
  {
    msg_.activation_rtf = std::move(arg);
    return std::move(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_activation_clock_receive_ns
{
public:
  explicit Init_ExecutionDecision_activation_clock_receive_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_activation_rtf activation_clock_receive_ns(::usv_research_interfaces::msg::ExecutionDecision::_activation_clock_receive_ns_type arg)
  {
    msg_.activation_clock_receive_ns = std::move(arg);
    return Init_ExecutionDecision_activation_rtf(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_activation_clock_sim_ns
{
public:
  explicit Init_ExecutionDecision_activation_clock_sim_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_activation_clock_receive_ns activation_clock_sim_ns(::usv_research_interfaces::msg::ExecutionDecision::_activation_clock_sim_ns_type arg)
  {
    msg_.activation_clock_sim_ns = std::move(arg);
    return Init_ExecutionDecision_activation_clock_receive_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_publish_clock_age_ns
{
public:
  explicit Init_ExecutionDecision_publish_clock_age_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_activation_clock_sim_ns publish_clock_age_ns(::usv_research_interfaces::msg::ExecutionDecision::_publish_clock_age_ns_type arg)
  {
    msg_.publish_clock_age_ns = std::move(arg);
    return Init_ExecutionDecision_activation_clock_sim_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_publish_epoch
{
public:
  explicit Init_ExecutionDecision_publish_epoch(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_publish_clock_age_ns publish_epoch(::usv_research_interfaces::msg::ExecutionDecision::_publish_epoch_type arg)
  {
    msg_.publish_epoch = std::move(arg);
    return Init_ExecutionDecision_publish_clock_age_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_publish_sim_ns
{
public:
  explicit Init_ExecutionDecision_publish_sim_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_publish_epoch publish_sim_ns(::usv_research_interfaces::msg::ExecutionDecision::_publish_sim_ns_type arg)
  {
    msg_.publish_sim_ns = std::move(arg);
    return Init_ExecutionDecision_publish_epoch(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_previous_anchor_known
{
public:
  explicit Init_ExecutionDecision_previous_anchor_known(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_publish_sim_ns previous_anchor_known(::usv_research_interfaces::msg::ExecutionDecision::_previous_anchor_known_type arg)
  {
    msg_.previous_anchor_known = std::move(arg);
    return Init_ExecutionDecision_publish_sim_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_plant_acceptance_observed
{
public:
  explicit Init_ExecutionDecision_plant_acceptance_observed(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_previous_anchor_known plant_acceptance_observed(::usv_research_interfaces::msg::ExecutionDecision::_plant_acceptance_observed_type arg)
  {
    msg_.plant_acceptance_observed = std::move(arg);
    return Init_ExecutionDecision_previous_anchor_known(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_rho_available
{
public:
  explicit Init_ExecutionDecision_rho_available(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_plant_acceptance_observed rho_available(::usv_research_interfaces::msg::ExecutionDecision::_rho_available_type arg)
  {
    msg_.rho_available = std::move(arg);
    return Init_ExecutionDecision_plant_acceptance_observed(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_normal_contract_complete
{
public:
  explicit Init_ExecutionDecision_normal_contract_complete(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_rho_available normal_contract_complete(::usv_research_interfaces::msg::ExecutionDecision::_normal_contract_complete_type arg)
  {
    msg_.normal_contract_complete = std::move(arg);
    return Init_ExecutionDecision_rho_available(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_clock_age_ns
{
public:
  explicit Init_ExecutionDecision_clock_age_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_normal_contract_complete clock_age_ns(::usv_research_interfaces::msg::ExecutionDecision::_clock_age_ns_type arg)
  {
    msg_.clock_age_ns = std::move(arg);
    return Init_ExecutionDecision_normal_contract_complete(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_imu_age_ns
{
public:
  explicit Init_ExecutionDecision_imu_age_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_clock_age_ns imu_age_ns(::usv_research_interfaces::msg::ExecutionDecision::_imu_age_ns_type arg)
  {
    msg_.imu_age_ns = std::move(arg);
    return Init_ExecutionDecision_clock_age_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_odom_age_ns
{
public:
  explicit Init_ExecutionDecision_odom_age_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_imu_age_ns odom_age_ns(::usv_research_interfaces::msg::ExecutionDecision::_odom_age_ns_type arg)
  {
    msg_.odom_age_ns = std::move(arg);
    return Init_ExecutionDecision_imu_age_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_previous_publish_ns
{
public:
  explicit Init_ExecutionDecision_previous_publish_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_odom_age_ns previous_publish_ns(::usv_research_interfaces::msg::ExecutionDecision::_previous_publish_ns_type arg)
  {
    msg_.previous_publish_ns = std::move(arg);
    return Init_ExecutionDecision_odom_age_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_previous_n
{
public:
  explicit Init_ExecutionDecision_previous_n(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_previous_publish_ns previous_n(::usv_research_interfaces::msg::ExecutionDecision::_previous_n_type arg)
  {
    msg_.previous_n = std::move(arg);
    return Init_ExecutionDecision_previous_publish_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_anchor_sequence
{
public:
  explicit Init_ExecutionDecision_anchor_sequence(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_previous_n anchor_sequence(::usv_research_interfaces::msg::ExecutionDecision::_anchor_sequence_type arg)
  {
    msg_.anchor_sequence = std::move(arg);
    return Init_ExecutionDecision_previous_n(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_anchor_known
{
public:
  explicit Init_ExecutionDecision_anchor_known(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_anchor_sequence anchor_known(::usv_research_interfaces::msg::ExecutionDecision::_anchor_known_type arg)
  {
    msg_.anchor_known = std::move(arg);
    return Init_ExecutionDecision_anchor_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_publish_end_ns
{
public:
  explicit Init_ExecutionDecision_publish_end_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_anchor_known publish_end_ns(::usv_research_interfaces::msg::ExecutionDecision::_publish_end_ns_type arg)
  {
    msg_.publish_end_ns = std::move(arg);
    return Init_ExecutionDecision_anchor_known(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_publish_start_ns
{
public:
  explicit Init_ExecutionDecision_publish_start_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_publish_end_ns publish_start_ns(::usv_research_interfaces::msg::ExecutionDecision::_publish_start_ns_type arg)
  {
    msg_.publish_start_ns = std::move(arg);
    return Init_ExecutionDecision_publish_end_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_publish_success
{
public:
  explicit Init_ExecutionDecision_publish_success(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_publish_start_ns publish_success(::usv_research_interfaces::msg::ExecutionDecision::_publish_success_type arg)
  {
    msg_.publish_success = std::move(arg);
    return Init_ExecutionDecision_publish_start_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_final_n
{
public:
  explicit Init_ExecutionDecision_final_n(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_publish_success final_n(::usv_research_interfaces::msg::ExecutionDecision::_final_n_type arg)
  {
    msg_.final_n = std::move(arg);
    return Init_ExecutionDecision_publish_success(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_requested_n
{
public:
  explicit Init_ExecutionDecision_requested_n(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_final_n requested_n(::usv_research_interfaces::msg::ExecutionDecision::_requested_n_type arg)
  {
    msg_.requested_n = std::move(arg);
    return Init_ExecutionDecision_final_n(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_state_error
{
public:
  explicit Init_ExecutionDecision_state_error(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_requested_n state_error(::usv_research_interfaces::msg::ExecutionDecision::_state_error_type arg)
  {
    msg_.state_error = std::move(arg);
    return Init_ExecutionDecision_requested_n(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_activation_state
{
public:
  explicit Init_ExecutionDecision_activation_state(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_state_error activation_state(::usv_research_interfaces::msg::ExecutionDecision::_activation_state_type arg)
  {
    msg_.activation_state = std::move(arg);
    return Init_ExecutionDecision_state_error(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_target_state
{
public:
  explicit Init_ExecutionDecision_target_state(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_activation_state target_state(::usv_research_interfaces::msg::ExecutionDecision::_target_state_type arg)
  {
    msg_.target_state = std::move(arg);
    return Init_ExecutionDecision_activation_state(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_control_source
{
public:
  explicit Init_ExecutionDecision_control_source(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_target_state control_source(::usv_research_interfaces::msg::ExecutionDecision::_control_source_type arg)
  {
    msg_.control_source = std::move(arg);
    return Init_ExecutionDecision_target_state(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_reason
{
public:
  explicit Init_ExecutionDecision_reason(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_control_source reason(::usv_research_interfaces::msg::ExecutionDecision::_reason_type arg)
  {
    msg_.reason = std::move(arg);
    return Init_ExecutionDecision_control_source(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_diagnostic_only
{
public:
  explicit Init_ExecutionDecision_diagnostic_only(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_reason diagnostic_only(::usv_research_interfaces::msg::ExecutionDecision::_diagnostic_only_type arg)
  {
    msg_.diagnostic_only = std::move(arg);
    return Init_ExecutionDecision_reason(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_candidate_accepted
{
public:
  explicit Init_ExecutionDecision_candidate_accepted(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_diagnostic_only candidate_accepted(::usv_research_interfaces::msg::ExecutionDecision::_candidate_accepted_type arg)
  {
    msg_.candidate_accepted = std::move(arg);
    return Init_ExecutionDecision_diagnostic_only(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_skipped_ticks
{
public:
  explicit Init_ExecutionDecision_skipped_ticks(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_candidate_accepted skipped_ticks(::usv_research_interfaces::msg::ExecutionDecision::_skipped_ticks_type arg)
  {
    msg_.skipped_ticks = std::move(arg);
    return Init_ExecutionDecision_candidate_accepted(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_tick_end_ns
{
public:
  explicit Init_ExecutionDecision_tick_end_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_skipped_ticks tick_end_ns(::usv_research_interfaces::msg::ExecutionDecision::_tick_end_ns_type arg)
  {
    msg_.tick_end_ns = std::move(arg);
    return Init_ExecutionDecision_skipped_ticks(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_activation_commit_ns
{
public:
  explicit Init_ExecutionDecision_activation_commit_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_tick_end_ns activation_commit_ns(::usv_research_interfaces::msg::ExecutionDecision::_activation_commit_ns_type arg)
  {
    msg_.activation_commit_ns = std::move(arg);
    return Init_ExecutionDecision_tick_end_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_candidate_ready_commit_ns
{
public:
  explicit Init_ExecutionDecision_candidate_ready_commit_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_activation_commit_ns candidate_ready_commit_ns(::usv_research_interfaces::msg::ExecutionDecision::_candidate_ready_commit_ns_type arg)
  {
    msg_.candidate_ready_commit_ns = std::move(arg);
    return Init_ExecutionDecision_activation_commit_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_cutoff_commit_ns
{
public:
  explicit Init_ExecutionDecision_cutoff_commit_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_candidate_ready_commit_ns cutoff_commit_ns(::usv_research_interfaces::msg::ExecutionDecision::_cutoff_commit_ns_type arg)
  {
    msg_.cutoff_commit_ns = std::move(arg);
    return Init_ExecutionDecision_candidate_ready_commit_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_tick_start_ns
{
public:
  explicit Init_ExecutionDecision_tick_start_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_cutoff_commit_ns tick_start_ns(::usv_research_interfaces::msg::ExecutionDecision::_tick_start_ns_type arg)
  {
    msg_.tick_start_ns = std::move(arg);
    return Init_ExecutionDecision_cutoff_commit_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_tick_planned_ns
{
public:
  explicit Init_ExecutionDecision_tick_planned_ns(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_tick_start_ns tick_planned_ns(::usv_research_interfaces::msg::ExecutionDecision::_tick_planned_ns_type arg)
  {
    msg_.tick_planned_ns = std::move(arg);
    return Init_ExecutionDecision_tick_start_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_clock_epoch
{
public:
  explicit Init_ExecutionDecision_clock_epoch(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_tick_planned_ns clock_epoch(::usv_research_interfaces::msg::ExecutionDecision::_clock_epoch_type arg)
  {
    msg_.clock_epoch = std::move(arg);
    return Init_ExecutionDecision_tick_planned_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_schedule_generation
{
public:
  explicit Init_ExecutionDecision_schedule_generation(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_clock_epoch schedule_generation(::usv_research_interfaces::msg::ExecutionDecision::_schedule_generation_type arg)
  {
    msg_.schedule_generation = std::move(arg);
    return Init_ExecutionDecision_clock_epoch(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_config_generation
{
public:
  explicit Init_ExecutionDecision_config_generation(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_schedule_generation config_generation(::usv_research_interfaces::msg::ExecutionDecision::_config_generation_type arg)
  {
    msg_.config_generation = std::move(arg);
    return Init_ExecutionDecision_schedule_generation(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_model_generation
{
public:
  explicit Init_ExecutionDecision_model_generation(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_config_generation model_generation(::usv_research_interfaces::msg::ExecutionDecision::_model_generation_type arg)
  {
    msg_.model_generation = std::move(arg);
    return Init_ExecutionDecision_config_generation(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_task_generation
{
public:
  explicit Init_ExecutionDecision_task_generation(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_model_generation task_generation(::usv_research_interfaces::msg::ExecutionDecision::_task_generation_type arg)
  {
    msg_.task_generation = std::move(arg);
    return Init_ExecutionDecision_model_generation(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_job_id
{
public:
  explicit Init_ExecutionDecision_job_id(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_task_generation job_id(::usv_research_interfaces::msg::ExecutionDecision::_job_id_type arg)
  {
    msg_.job_id = std::move(arg);
    return Init_ExecutionDecision_task_generation(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_tick
{
public:
  explicit Init_ExecutionDecision_tick(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_job_id tick(::usv_research_interfaces::msg::ExecutionDecision::_tick_type arg)
  {
    msg_.tick = std::move(arg);
    return Init_ExecutionDecision_job_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_sequence
{
public:
  explicit Init_ExecutionDecision_sequence(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_tick sequence(::usv_research_interfaces::msg::ExecutionDecision::_sequence_type arg)
  {
    msg_.sequence = std::move(arg);
    return Init_ExecutionDecision_tick(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_mode
{
public:
  explicit Init_ExecutionDecision_mode(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_sequence mode(::usv_research_interfaces::msg::ExecutionDecision::_mode_type arg)
  {
    msg_.mode = std::move(arg);
    return Init_ExecutionDecision_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_worker_instance
{
public:
  explicit Init_ExecutionDecision_worker_instance(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_mode worker_instance(::usv_research_interfaces::msg::ExecutionDecision::_worker_instance_type arg)
  {
    msg_.worker_instance = std::move(arg);
    return Init_ExecutionDecision_mode(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_contract_hash
{
public:
  explicit Init_ExecutionDecision_contract_hash(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_worker_instance contract_hash(::usv_research_interfaces::msg::ExecutionDecision::_contract_hash_type arg)
  {
    msg_.contract_hash = std::move(arg);
    return Init_ExecutionDecision_worker_instance(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_boot_id
{
public:
  explicit Init_ExecutionDecision_boot_id(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_contract_hash boot_id(::usv_research_interfaces::msg::ExecutionDecision::_boot_id_type arg)
  {
    msg_.boot_id = std::move(arg);
    return Init_ExecutionDecision_contract_hash(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_run_id
{
public:
  explicit Init_ExecutionDecision_run_id(::usv_research_interfaces::msg::ExecutionDecision & msg)
  : msg_(msg)
  {}
  Init_ExecutionDecision_boot_id run_id(::usv_research_interfaces::msg::ExecutionDecision::_run_id_type arg)
  {
    msg_.run_id = std::move(arg);
    return Init_ExecutionDecision_boot_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

class Init_ExecutionDecision_schema_version
{
public:
  Init_ExecutionDecision_schema_version()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_ExecutionDecision_run_id schema_version(::usv_research_interfaces::msg::ExecutionDecision::_schema_version_type arg)
  {
    msg_.schema_version = std::move(arg);
    return Init_ExecutionDecision_run_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::ExecutionDecision msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::usv_research_interfaces::msg::ExecutionDecision>()
{
  return usv_research_interfaces::msg::builder::Init_ExecutionDecision_schema_version();
}

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__EXECUTION_DECISION__BUILDER_HPP_
