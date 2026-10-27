// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from usv_research_interfaces:msg/CycleTiming.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/cycle_timing.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__CYCLE_TIMING__BUILDER_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__CYCLE_TIMING__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "usv_research_interfaces/msg/detail/cycle_timing__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace usv_research_interfaces
{

namespace msg
{

namespace builder
{

class Init_CycleTiming_solve_invoked
{
public:
  explicit Init_CycleTiming_solve_invoked(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  ::usv_research_interfaces::msg::CycleTiming solve_invoked(::usv_research_interfaces::msg::CycleTiming::_solve_invoked_type arg)
  {
    msg_.solve_invoked = std::move(arg);
    return std::move(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_applied_sequence
{
public:
  explicit Init_CycleTiming_applied_sequence(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_solve_invoked applied_sequence(::usv_research_interfaces::msg::CycleTiming::_applied_sequence_type arg)
  {
    msg_.applied_sequence = std::move(arg);
    return Init_CycleTiming_solve_invoked(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_rejection_reason
{
public:
  explicit Init_CycleTiming_rejection_reason(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_applied_sequence rejection_reason(::usv_research_interfaces::msg::CycleTiming::_rejection_reason_type arg)
  {
    msg_.rejection_reason = std::move(arg);
    return Init_CycleTiming_applied_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_deadline_miss
{
public:
  explicit Init_CycleTiming_deadline_miss(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_rejection_reason deadline_miss(::usv_research_interfaces::msg::CycleTiming::_deadline_miss_type arg)
  {
    msg_.deadline_miss = std::move(arg);
    return Init_CycleTiming_rejection_reason(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_success
{
public:
  explicit Init_CycleTiming_success(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_deadline_miss success(::usv_research_interfaces::msg::CycleTiming::_success_type arg)
  {
    msg_.success = std::move(arg);
    return Init_CycleTiming_deadline_miss(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_budget_ms
{
public:
  explicit Init_CycleTiming_budget_ms(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_success budget_ms(::usv_research_interfaces::msg::CycleTiming::_budget_ms_type arg)
  {
    msg_.budget_ms = std::move(arg);
    return Init_CycleTiming_success(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_backend_time_ms
{
public:
  explicit Init_CycleTiming_backend_time_ms(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_budget_ms backend_time_ms(::usv_research_interfaces::msg::CycleTiming::_backend_time_ms_type arg)
  {
    msg_.backend_time_ms = std::move(arg);
    return Init_CycleTiming_budget_ms(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_imu_stamp_ns
{
public:
  explicit Init_CycleTiming_imu_stamp_ns(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_backend_time_ms imu_stamp_ns(::usv_research_interfaces::msg::CycleTiming::_imu_stamp_ns_type arg)
  {
    msg_.imu_stamp_ns = std::move(arg);
    return Init_CycleTiming_backend_time_ms(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_odom_stamp_ns
{
public:
  explicit Init_CycleTiming_odom_stamp_ns(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_imu_stamp_ns odom_stamp_ns(::usv_research_interfaces::msg::CycleTiming::_odom_stamp_ns_type arg)
  {
    msg_.odom_stamp_ns = std::move(arg);
    return Init_CycleTiming_imu_stamp_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_received_imu_sequence
{
public:
  explicit Init_CycleTiming_received_imu_sequence(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_odom_stamp_ns received_imu_sequence(::usv_research_interfaces::msg::CycleTiming::_received_imu_sequence_type arg)
  {
    msg_.received_imu_sequence = std::move(arg);
    return Init_CycleTiming_odom_stamp_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_received_odom_sequence
{
public:
  explicit Init_CycleTiming_received_odom_sequence(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_received_imu_sequence received_odom_sequence(::usv_research_interfaces::msg::CycleTiming::_received_odom_sequence_type arg)
  {
    msg_.received_odom_sequence = std::move(arg);
    return Init_CycleTiming_received_imu_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_state_kind
{
public:
  explicit Init_CycleTiming_state_kind(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_received_odom_sequence state_kind(::usv_research_interfaces::msg::CycleTiming::_state_kind_type arg)
  {
    msg_.state_kind = std::move(arg);
    return Init_CycleTiming_received_odom_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_controller_state_6
{
public:
  explicit Init_CycleTiming_controller_state_6(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_state_kind controller_state_6(::usv_research_interfaces::msg::CycleTiming::_controller_state_6_type arg)
  {
    msg_.controller_state_6 = std::move(arg);
    return Init_CycleTiming_state_kind(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_publish_end_steady_ns
{
public:
  explicit Init_CycleTiming_publish_end_steady_ns(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_controller_state_6 publish_end_steady_ns(::usv_research_interfaces::msg::CycleTiming::_publish_end_steady_ns_type arg)
  {
    msg_.publish_end_steady_ns = std::move(arg);
    return Init_CycleTiming_controller_state_6(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_solve_end_steady_ns
{
public:
  explicit Init_CycleTiming_solve_end_steady_ns(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_publish_end_steady_ns solve_end_steady_ns(::usv_research_interfaces::msg::CycleTiming::_solve_end_steady_ns_type arg)
  {
    msg_.solve_end_steady_ns = std::move(arg);
    return Init_CycleTiming_publish_end_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_solve_start_steady_ns
{
public:
  explicit Init_CycleTiming_solve_start_steady_ns(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_solve_end_steady_ns solve_start_steady_ns(::usv_research_interfaces::msg::CycleTiming::_solve_start_steady_ns_type arg)
  {
    msg_.solve_start_steady_ns = std::move(arg);
    return Init_CycleTiming_solve_end_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_reference_ready_steady_ns
{
public:
  explicit Init_CycleTiming_reference_ready_steady_ns(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_solve_start_steady_ns reference_ready_steady_ns(::usv_research_interfaces::msg::CycleTiming::_reference_ready_steady_ns_type arg)
  {
    msg_.reference_ready_steady_ns = std::move(arg);
    return Init_CycleTiming_solve_start_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_state_copy_steady_ns
{
public:
  explicit Init_CycleTiming_state_copy_steady_ns(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_reference_ready_steady_ns state_copy_steady_ns(::usv_research_interfaces::msg::CycleTiming::_state_copy_steady_ns_type arg)
  {
    msg_.state_copy_steady_ns = std::move(arg);
    return Init_CycleTiming_reference_ready_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_timer_entry_steady_ns
{
public:
  explicit Init_CycleTiming_timer_entry_steady_ns(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_state_copy_steady_ns timer_entry_steady_ns(::usv_research_interfaces::msg::CycleTiming::_timer_entry_steady_ns_type arg)
  {
    msg_.timer_entry_steady_ns = std::move(arg);
    return Init_CycleTiming_state_copy_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_steady_clock_domain
{
public:
  explicit Init_CycleTiming_steady_clock_domain(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_timer_entry_steady_ns steady_clock_domain(::usv_research_interfaces::msg::CycleTiming::_steady_clock_domain_type arg)
  {
    msg_.steady_clock_domain = std::move(arg);
    return Init_CycleTiming_timer_entry_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_clock_status
{
public:
  explicit Init_CycleTiming_clock_status(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_steady_clock_domain clock_status(::usv_research_interfaces::msg::CycleTiming::_clock_status_type arg)
  {
    msg_.clock_status = std::move(arg);
    return Init_CycleTiming_steady_clock_domain(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_clock_age_ns
{
public:
  explicit Init_CycleTiming_clock_age_ns(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_clock_status clock_age_ns(::usv_research_interfaces::msg::CycleTiming::_clock_age_ns_type arg)
  {
    msg_.clock_age_ns = std::move(arg);
    return Init_CycleTiming_clock_status(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_clock_receive_steady_ns
{
public:
  explicit Init_CycleTiming_clock_receive_steady_ns(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_clock_age_ns clock_receive_steady_ns(::usv_research_interfaces::msg::CycleTiming::_clock_receive_steady_ns_type arg)
  {
    msg_.clock_receive_steady_ns = std::move(arg);
    return Init_CycleTiming_clock_age_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_sim_time_ns
{
public:
  explicit Init_CycleTiming_sim_time_ns(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_clock_receive_steady_ns sim_time_ns(::usv_research_interfaces::msg::CycleTiming::_sim_time_ns_type arg)
  {
    msg_.sim_time_ns = std::move(arg);
    return Init_CycleTiming_clock_receive_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_clock_epoch
{
public:
  explicit Init_CycleTiming_clock_epoch(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_sim_time_ns clock_epoch(::usv_research_interfaces::msg::CycleTiming::_clock_epoch_type arg)
  {
    msg_.clock_epoch = std::move(arg);
    return Init_CycleTiming_sim_time_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_sequence
{
public:
  explicit Init_CycleTiming_sequence(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_clock_epoch sequence(::usv_research_interfaces::msg::CycleTiming::_sequence_type arg)
  {
    msg_.sequence = std::move(arg);
    return Init_CycleTiming_clock_epoch(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_config_hash
{
public:
  explicit Init_CycleTiming_config_hash(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_sequence config_hash(::usv_research_interfaces::msg::CycleTiming::_config_hash_type arg)
  {
    msg_.config_hash = std::move(arg);
    return Init_CycleTiming_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_baseline_id
{
public:
  explicit Init_CycleTiming_baseline_id(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_config_hash baseline_id(::usv_research_interfaces::msg::CycleTiming::_baseline_id_type arg)
  {
    msg_.baseline_id = std::move(arg);
    return Init_CycleTiming_config_hash(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_producer_instance_id
{
public:
  explicit Init_CycleTiming_producer_instance_id(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_baseline_id producer_instance_id(::usv_research_interfaces::msg::CycleTiming::_producer_instance_id_type arg)
  {
    msg_.producer_instance_id = std::move(arg);
    return Init_CycleTiming_baseline_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_run_id
{
public:
  explicit Init_CycleTiming_run_id(::usv_research_interfaces::msg::CycleTiming & msg)
  : msg_(msg)
  {}
  Init_CycleTiming_producer_instance_id run_id(::usv_research_interfaces::msg::CycleTiming::_run_id_type arg)
  {
    msg_.run_id = std::move(arg);
    return Init_CycleTiming_producer_instance_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

class Init_CycleTiming_schema_version
{
public:
  Init_CycleTiming_schema_version()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_CycleTiming_run_id schema_version(::usv_research_interfaces::msg::CycleTiming::_schema_version_type arg)
  {
    msg_.schema_version = std::move(arg);
    return Init_CycleTiming_run_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::CycleTiming msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::usv_research_interfaces::msg::CycleTiming>()
{
  return usv_research_interfaces::msg::builder::Init_CycleTiming_schema_version();
}

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__CYCLE_TIMING__BUILDER_HPP_
