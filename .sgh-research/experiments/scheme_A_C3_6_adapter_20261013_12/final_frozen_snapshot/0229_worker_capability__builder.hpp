// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from usv_research_interfaces:msg/WorkerCapability.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/worker_capability.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__WORKER_CAPABILITY__BUILDER_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__WORKER_CAPABILITY__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "usv_research_interfaces/msg/detail/worker_capability__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace usv_research_interfaces
{

namespace msg
{

namespace builder
{

class Init_WorkerCapability_reason
{
public:
  explicit Init_WorkerCapability_reason(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  ::usv_research_interfaces::msg::WorkerCapability reason(::usv_research_interfaces::msg::WorkerCapability::_reason_type arg)
  {
    msg_.reason = std::move(arg);
    return std::move(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_fatal
{
public:
  explicit Init_WorkerCapability_fatal(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_reason fatal(::usv_research_interfaces::msg::WorkerCapability::_fatal_type arg)
  {
    msg_.fatal = std::move(arg);
    return Init_WorkerCapability_reason(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_fault_injection_enabled
{
public:
  explicit Init_WorkerCapability_fault_injection_enabled(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_fatal fault_injection_enabled(::usv_research_interfaces::msg::WorkerCapability::_fault_injection_enabled_type arg)
  {
    msg_.fault_injection_enabled = std::move(arg);
    return Init_WorkerCapability_fatal(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_pending_count
{
public:
  explicit Init_WorkerCapability_pending_count(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_fault_injection_enabled pending_count(::usv_research_interfaces::msg::WorkerCapability::_pending_count_type arg)
  {
    msg_.pending_count = std::move(arg);
    return Init_WorkerCapability_fault_injection_enabled(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_active_job
{
public:
  explicit Init_WorkerCapability_active_job(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_pending_count active_job(::usv_research_interfaces::msg::WorkerCapability::_active_job_type arg)
  {
    msg_.active_job = std::move(arg);
    return Init_WorkerCapability_pending_count(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_completed_jobs
{
public:
  explicit Init_WorkerCapability_completed_jobs(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_active_job completed_jobs(::usv_research_interfaces::msg::WorkerCapability::_completed_jobs_type arg)
  {
    msg_.completed_jobs = std::move(arg);
    return Init_WorkerCapability_active_job(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_startup_ns
{
public:
  explicit Init_WorkerCapability_startup_ns(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_completed_jobs startup_ns(::usv_research_interfaces::msg::WorkerCapability::_startup_ns_type arg)
  {
    msg_.startup_ns = std::move(arg);
    return Init_WorkerCapability_completed_jobs(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_pid
{
public:
  explicit Init_WorkerCapability_pid(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_startup_ns pid(::usv_research_interfaces::msg::WorkerCapability::_pid_type arg)
  {
    msg_.pid = std::move(arg);
    return Init_WorkerCapability_startup_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_prediction_dt
{
public:
  explicit Init_WorkerCapability_prediction_dt(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_pid prediction_dt(::usv_research_interfaces::msg::WorkerCapability::_prediction_dt_type arg)
  {
    msg_.prediction_dt = std::move(arg);
    return Init_WorkerCapability_pid(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_horizon_steps
{
public:
  explicit Init_WorkerCapability_horizon_steps(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_prediction_dt horizon_steps(::usv_research_interfaces::msg::WorkerCapability::_horizon_steps_type arg)
  {
    msg_.horizon_steps = std::move(arg);
    return Init_WorkerCapability_prediction_dt(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_matrix_layout
{
public:
  explicit Init_WorkerCapability_matrix_layout(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_horizon_steps matrix_layout(::usv_research_interfaces::msg::WorkerCapability::_matrix_layout_type arg)
  {
    msg_.matrix_layout = std::move(arg);
    return Init_WorkerCapability_horizon_steps(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_backend
{
public:
  explicit Init_WorkerCapability_backend(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_matrix_layout backend(::usv_research_interfaces::msg::WorkerCapability::_backend_type arg)
  {
    msg_.backend = std::move(arg);
    return Init_WorkerCapability_matrix_layout(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_clock_name
{
public:
  explicit Init_WorkerCapability_clock_name(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_backend clock_name(::usv_research_interfaces::msg::WorkerCapability::_clock_name_type arg)
  {
    msg_.clock_name = std::move(arg);
    return Init_WorkerCapability_backend(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_worker_instance
{
public:
  explicit Init_WorkerCapability_worker_instance(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_clock_name worker_instance(::usv_research_interfaces::msg::WorkerCapability::_worker_instance_type arg)
  {
    msg_.worker_instance = std::move(arg);
    return Init_WorkerCapability_clock_name(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_nominal_hash
{
public:
  explicit Init_WorkerCapability_nominal_hash(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_worker_instance nominal_hash(::usv_research_interfaces::msg::WorkerCapability::_nominal_hash_type arg)
  {
    msg_.nominal_hash = std::move(arg);
    return Init_WorkerCapability_worker_instance(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_contract_hash
{
public:
  explicit Init_WorkerCapability_contract_hash(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_nominal_hash contract_hash(::usv_research_interfaces::msg::WorkerCapability::_contract_hash_type arg)
  {
    msg_.contract_hash = std::move(arg);
    return Init_WorkerCapability_nominal_hash(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_boot_id
{
public:
  explicit Init_WorkerCapability_boot_id(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_contract_hash boot_id(::usv_research_interfaces::msg::WorkerCapability::_boot_id_type arg)
  {
    msg_.boot_id = std::move(arg);
    return Init_WorkerCapability_contract_hash(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_run_id
{
public:
  explicit Init_WorkerCapability_run_id(::usv_research_interfaces::msg::WorkerCapability & msg)
  : msg_(msg)
  {}
  Init_WorkerCapability_boot_id run_id(::usv_research_interfaces::msg::WorkerCapability::_run_id_type arg)
  {
    msg_.run_id = std::move(arg);
    return Init_WorkerCapability_boot_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

class Init_WorkerCapability_schema_version
{
public:
  Init_WorkerCapability_schema_version()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_WorkerCapability_run_id schema_version(::usv_research_interfaces::msg::WorkerCapability::_schema_version_type arg)
  {
    msg_.schema_version = std::move(arg);
    return Init_WorkerCapability_run_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::WorkerCapability msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::usv_research_interfaces::msg::WorkerCapability>()
{
  return usv_research_interfaces::msg::builder::Init_WorkerCapability_schema_version();
}

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__WORKER_CAPABILITY__BUILDER_HPP_
