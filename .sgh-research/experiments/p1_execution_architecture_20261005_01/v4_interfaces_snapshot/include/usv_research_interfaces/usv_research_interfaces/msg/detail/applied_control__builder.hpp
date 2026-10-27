// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from usv_research_interfaces:msg/AppliedControl.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/applied_control.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__APPLIED_CONTROL__BUILDER_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__APPLIED_CONTROL__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "usv_research_interfaces/msg/detail/applied_control__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace usv_research_interfaces
{

namespace msg
{

namespace builder
{

class Init_AppliedControl_publish_error
{
public:
  explicit Init_AppliedControl_publish_error(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  ::usv_research_interfaces::msg::AppliedControl publish_error(::usv_research_interfaces::msg::AppliedControl::_publish_error_type arg)
  {
    msg_.publish_error = std::move(arg);
    return std::move(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_execution_atomicity_proven
{
public:
  explicit Init_AppliedControl_execution_atomicity_proven(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_publish_error execution_atomicity_proven(::usv_research_interfaces::msg::AppliedControl::_execution_atomicity_proven_type arg)
  {
    msg_.execution_atomicity_proven = std::move(arg);
    return Init_AppliedControl_publish_error(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_force_measured
{
public:
  explicit Init_AppliedControl_force_measured(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_execution_atomicity_proven force_measured(::usv_research_interfaces::msg::AppliedControl::_force_measured_type arg)
  {
    msg_.force_measured = std::move(arg);
    return Init_AppliedControl_execution_atomicity_proven(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_plant_acceptance_observed
{
public:
  explicit Init_AppliedControl_plant_acceptance_observed(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_force_measured plant_acceptance_observed(::usv_research_interfaces::msg::AppliedControl::_plant_acceptance_observed_type arg)
  {
    msg_.plant_acceptance_observed = std::move(arg);
    return Init_AppliedControl_force_measured(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_previous_final_n
{
public:
  explicit Init_AppliedControl_previous_final_n(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_plant_acceptance_observed previous_final_n(::usv_research_interfaces::msg::AppliedControl::_previous_final_n_type arg)
  {
    msg_.previous_final_n = std::move(arg);
    return Init_AppliedControl_plant_acceptance_observed(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_previous_anchor_known
{
public:
  explicit Init_AppliedControl_previous_anchor_known(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_previous_final_n previous_anchor_known(::usv_research_interfaces::msg::AppliedControl::_previous_anchor_known_type arg)
  {
    msg_.previous_anchor_known = std::move(arg);
    return Init_AppliedControl_previous_final_n(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_upper_n
{
public:
  explicit Init_AppliedControl_upper_n(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_previous_anchor_known upper_n(::usv_research_interfaces::msg::AppliedControl::_upper_n_type arg)
  {
    msg_.upper_n = std::move(arg);
    return Init_AppliedControl_previous_anchor_known(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_lower_n
{
public:
  explicit Init_AppliedControl_lower_n(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_upper_n lower_n(::usv_research_interfaces::msg::AppliedControl::_lower_n_type arg)
  {
    msg_.lower_n = std::move(arg);
    return Init_AppliedControl_upper_n(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_map_scale
{
public:
  explicit Init_AppliedControl_map_scale(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_lower_n map_scale(::usv_research_interfaces::msg::AppliedControl::_map_scale_type arg)
  {
    msg_.map_scale = std::move(arg);
    return Init_AppliedControl_lower_n(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_right_clock_age_ns
{
public:
  explicit Init_AppliedControl_right_clock_age_ns(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_map_scale right_clock_age_ns(::usv_research_interfaces::msg::AppliedControl::_right_clock_age_ns_type arg)
  {
    msg_.right_clock_age_ns = std::move(arg);
    return Init_AppliedControl_map_scale(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_left_clock_age_ns
{
public:
  explicit Init_AppliedControl_left_clock_age_ns(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_right_clock_age_ns left_clock_age_ns(::usv_research_interfaces::msg::AppliedControl::_left_clock_age_ns_type arg)
  {
    msg_.left_clock_age_ns = std::move(arg);
    return Init_AppliedControl_right_clock_age_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_right_clock_epoch
{
public:
  explicit Init_AppliedControl_right_clock_epoch(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_left_clock_age_ns right_clock_epoch(::usv_research_interfaces::msg::AppliedControl::_right_clock_epoch_type arg)
  {
    msg_.right_clock_epoch = std::move(arg);
    return Init_AppliedControl_left_clock_age_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_left_clock_epoch
{
public:
  explicit Init_AppliedControl_left_clock_epoch(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_right_clock_epoch left_clock_epoch(::usv_research_interfaces::msg::AppliedControl::_left_clock_epoch_type arg)
  {
    msg_.left_clock_epoch = std::move(arg);
    return Init_AppliedControl_right_clock_epoch(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_right_sim_time_ns
{
public:
  explicit Init_AppliedControl_right_sim_time_ns(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_left_clock_epoch right_sim_time_ns(::usv_research_interfaces::msg::AppliedControl::_right_sim_time_ns_type arg)
  {
    msg_.right_sim_time_ns = std::move(arg);
    return Init_AppliedControl_left_clock_epoch(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_left_sim_time_ns
{
public:
  explicit Init_AppliedControl_left_sim_time_ns(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_right_sim_time_ns left_sim_time_ns(::usv_research_interfaces::msg::AppliedControl::_left_sim_time_ns_type arg)
  {
    msg_.left_sim_time_ns = std::move(arg);
    return Init_AppliedControl_right_sim_time_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_right_publish_end_steady_ns
{
public:
  explicit Init_AppliedControl_right_publish_end_steady_ns(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_left_sim_time_ns right_publish_end_steady_ns(::usv_research_interfaces::msg::AppliedControl::_right_publish_end_steady_ns_type arg)
  {
    msg_.right_publish_end_steady_ns = std::move(arg);
    return Init_AppliedControl_left_sim_time_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_right_publish_start_steady_ns
{
public:
  explicit Init_AppliedControl_right_publish_start_steady_ns(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_right_publish_end_steady_ns right_publish_start_steady_ns(::usv_research_interfaces::msg::AppliedControl::_right_publish_start_steady_ns_type arg)
  {
    msg_.right_publish_start_steady_ns = std::move(arg);
    return Init_AppliedControl_right_publish_end_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_left_publish_end_steady_ns
{
public:
  explicit Init_AppliedControl_left_publish_end_steady_ns(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_right_publish_start_steady_ns left_publish_end_steady_ns(::usv_research_interfaces::msg::AppliedControl::_left_publish_end_steady_ns_type arg)
  {
    msg_.left_publish_end_steady_ns = std::move(arg);
    return Init_AppliedControl_right_publish_start_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_left_publish_start_steady_ns
{
public:
  explicit Init_AppliedControl_left_publish_start_steady_ns(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_left_publish_end_steady_ns left_publish_start_steady_ns(::usv_research_interfaces::msg::AppliedControl::_left_publish_start_steady_ns_type arg)
  {
    msg_.left_publish_start_steady_ns = std::move(arg);
    return Init_AppliedControl_left_publish_end_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_right_publish_success
{
public:
  explicit Init_AppliedControl_right_publish_success(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_left_publish_start_steady_ns right_publish_success(::usv_research_interfaces::msg::AppliedControl::_right_publish_success_type arg)
  {
    msg_.right_publish_success = std::move(arg);
    return Init_AppliedControl_left_publish_start_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_left_publish_success
{
public:
  explicit Init_AppliedControl_left_publish_success(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_right_publish_success left_publish_success(::usv_research_interfaces::msg::AppliedControl::_left_publish_success_type arg)
  {
    msg_.left_publish_success = std::move(arg);
    return Init_AppliedControl_right_publish_success(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_final_n
{
public:
  explicit Init_AppliedControl_final_n(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_left_publish_success final_n(::usv_research_interfaces::msg::AppliedControl::_final_n_type arg)
  {
    msg_.final_n = std::move(arg);
    return Init_AppliedControl_left_publish_success(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_requested_n
{
public:
  explicit Init_AppliedControl_requested_n(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_final_n requested_n(::usv_research_interfaces::msg::AppliedControl::_requested_n_type arg)
  {
    msg_.requested_n = std::move(arg);
    return Init_AppliedControl_final_n(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_requested_known
{
public:
  explicit Init_AppliedControl_requested_known(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_requested_n requested_known(::usv_research_interfaces::msg::AppliedControl::_requested_known_type arg)
  {
    msg_.requested_known = std::move(arg);
    return Init_AppliedControl_requested_n(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_event_semantics
{
public:
  explicit Init_AppliedControl_event_semantics(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_requested_known event_semantics(::usv_research_interfaces::msg::AppliedControl::_event_semantics_type arg)
  {
    msg_.event_semantics = std::move(arg);
    return Init_AppliedControl_requested_known(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_control_source
{
public:
  explicit Init_AppliedControl_control_source(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_event_semantics control_source(::usv_research_interfaces::msg::AppliedControl::_control_source_type arg)
  {
    msg_.control_source = std::move(arg);
    return Init_AppliedControl_event_semantics(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_cycle_sequence
{
public:
  explicit Init_AppliedControl_cycle_sequence(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_control_source cycle_sequence(::usv_research_interfaces::msg::AppliedControl::_cycle_sequence_type arg)
  {
    msg_.cycle_sequence = std::move(arg);
    return Init_AppliedControl_control_source(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_steady_clock_domain
{
public:
  explicit Init_AppliedControl_steady_clock_domain(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_cycle_sequence steady_clock_domain(::usv_research_interfaces::msg::AppliedControl::_steady_clock_domain_type arg)
  {
    msg_.steady_clock_domain = std::move(arg);
    return Init_AppliedControl_cycle_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_clock_status
{
public:
  explicit Init_AppliedControl_clock_status(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_steady_clock_domain clock_status(::usv_research_interfaces::msg::AppliedControl::_clock_status_type arg)
  {
    msg_.clock_status = std::move(arg);
    return Init_AppliedControl_steady_clock_domain(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_clock_age_ns
{
public:
  explicit Init_AppliedControl_clock_age_ns(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_clock_status clock_age_ns(::usv_research_interfaces::msg::AppliedControl::_clock_age_ns_type arg)
  {
    msg_.clock_age_ns = std::move(arg);
    return Init_AppliedControl_clock_status(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_clock_receive_steady_ns
{
public:
  explicit Init_AppliedControl_clock_receive_steady_ns(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_clock_age_ns clock_receive_steady_ns(::usv_research_interfaces::msg::AppliedControl::_clock_receive_steady_ns_type arg)
  {
    msg_.clock_receive_steady_ns = std::move(arg);
    return Init_AppliedControl_clock_age_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_sim_time_ns
{
public:
  explicit Init_AppliedControl_sim_time_ns(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_clock_receive_steady_ns sim_time_ns(::usv_research_interfaces::msg::AppliedControl::_sim_time_ns_type arg)
  {
    msg_.sim_time_ns = std::move(arg);
    return Init_AppliedControl_clock_receive_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_clock_epoch
{
public:
  explicit Init_AppliedControl_clock_epoch(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_sim_time_ns clock_epoch(::usv_research_interfaces::msg::AppliedControl::_clock_epoch_type arg)
  {
    msg_.clock_epoch = std::move(arg);
    return Init_AppliedControl_sim_time_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_sequence
{
public:
  explicit Init_AppliedControl_sequence(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_clock_epoch sequence(::usv_research_interfaces::msg::AppliedControl::_sequence_type arg)
  {
    msg_.sequence = std::move(arg);
    return Init_AppliedControl_clock_epoch(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_config_hash
{
public:
  explicit Init_AppliedControl_config_hash(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_sequence config_hash(::usv_research_interfaces::msg::AppliedControl::_config_hash_type arg)
  {
    msg_.config_hash = std::move(arg);
    return Init_AppliedControl_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_baseline_id
{
public:
  explicit Init_AppliedControl_baseline_id(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_config_hash baseline_id(::usv_research_interfaces::msg::AppliedControl::_baseline_id_type arg)
  {
    msg_.baseline_id = std::move(arg);
    return Init_AppliedControl_config_hash(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_producer_instance_id
{
public:
  explicit Init_AppliedControl_producer_instance_id(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_baseline_id producer_instance_id(::usv_research_interfaces::msg::AppliedControl::_producer_instance_id_type arg)
  {
    msg_.producer_instance_id = std::move(arg);
    return Init_AppliedControl_baseline_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_run_id
{
public:
  explicit Init_AppliedControl_run_id(::usv_research_interfaces::msg::AppliedControl & msg)
  : msg_(msg)
  {}
  Init_AppliedControl_producer_instance_id run_id(::usv_research_interfaces::msg::AppliedControl::_run_id_type arg)
  {
    msg_.run_id = std::move(arg);
    return Init_AppliedControl_producer_instance_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

class Init_AppliedControl_schema_version
{
public:
  Init_AppliedControl_schema_version()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_AppliedControl_run_id schema_version(::usv_research_interfaces::msg::AppliedControl::_schema_version_type arg)
  {
    msg_.schema_version = std::move(arg);
    return Init_AppliedControl_run_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::AppliedControl msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::usv_research_interfaces::msg::AppliedControl>()
{
  return usv_research_interfaces::msg::builder::Init_AppliedControl_schema_version();
}

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__APPLIED_CONTROL__BUILDER_HPP_
