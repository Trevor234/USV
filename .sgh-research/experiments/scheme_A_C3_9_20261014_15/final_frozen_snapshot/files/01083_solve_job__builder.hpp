// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from usv_research_interfaces:msg/SolveJob.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/solve_job.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__BUILDER_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "usv_research_interfaces/msg/detail/solve_job__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace usv_research_interfaces
{

namespace msg
{

namespace builder
{

class Init_SolveJob_history_n
{
public:
  explicit Init_SolveJob_history_n(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  ::usv_research_interfaces::msg::SolveJob history_n(::usv_research_interfaces::msg::SolveJob::_history_n_type arg)
  {
    msg_.history_n = std::move(arg);
    return std::move(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_history_channel
{
public:
  explicit Init_SolveJob_history_channel(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_history_n history_channel(::usv_research_interfaces::msg::SolveJob::_history_channel_type arg)
  {
    msg_.history_channel = std::move(arg);
    return Init_SolveJob_history_n(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_history_sim_ns
{
public:
  explicit Init_SolveJob_history_sim_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_history_channel history_sim_ns(::usv_research_interfaces::msg::SolveJob::_history_sim_ns_type arg)
  {
    msg_.history_sim_ns = std::move(arg);
    return Init_SolveJob_history_channel(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_anchor_run_id
{
public:
  explicit Init_SolveJob_anchor_run_id(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_history_sim_ns anchor_run_id(::usv_research_interfaces::msg::SolveJob::_anchor_run_id_type arg)
  {
    msg_.anchor_run_id = std::move(arg);
    return Init_SolveJob_history_sim_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_anchor_producer
{
public:
  explicit Init_SolveJob_anchor_producer(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_anchor_run_id anchor_producer(::usv_research_interfaces::msg::SolveJob::_anchor_producer_type arg)
  {
    msg_.anchor_producer = std::move(arg);
    return Init_SolveJob_anchor_run_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_anchor_source
{
public:
  explicit Init_SolveJob_anchor_source(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_anchor_producer anchor_source(::usv_research_interfaces::msg::SolveJob::_anchor_source_type arg)
  {
    msg_.anchor_source = std::move(arg);
    return Init_SolveJob_anchor_producer(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_assumed_rtf
{
public:
  explicit Init_SolveJob_assumed_rtf(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_anchor_source assumed_rtf(::usv_research_interfaces::msg::SolveJob::_assumed_rtf_type arg)
  {
    msg_.assumed_rtf = std::move(arg);
    return Init_SolveJob_anchor_source(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_frozen_clock_receive_ns
{
public:
  explicit Init_SolveJob_frozen_clock_receive_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_assumed_rtf frozen_clock_receive_ns(::usv_research_interfaces::msg::SolveJob::_frozen_clock_receive_ns_type arg)
  {
    msg_.frozen_clock_receive_ns = std::move(arg);
    return Init_SolveJob_assumed_rtf(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_frozen_clock_sim_ns
{
public:
  explicit Init_SolveJob_frozen_clock_sim_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_frozen_clock_receive_ns frozen_clock_sim_ns(::usv_research_interfaces::msg::SolveJob::_frozen_clock_sim_ns_type arg)
  {
    msg_.frozen_clock_sim_ns = std::move(arg);
    return Init_SolveJob_frozen_clock_receive_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_reset_warmstart
{
public:
  explicit Init_SolveJob_reset_warmstart(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_frozen_clock_sim_ns reset_warmstart(::usv_research_interfaces::msg::SolveJob::_reset_warmstart_type arg)
  {
    msg_.reset_warmstart = std::move(arg);
    return Init_SolveJob_frozen_clock_sim_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_anchor_known
{
public:
  explicit Init_SolveJob_anchor_known(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_reset_warmstart anchor_known(::usv_research_interfaces::msg::SolveJob::_anchor_known_type arg)
  {
    msg_.anchor_known = std::move(arg);
    return Init_SolveJob_reset_warmstart(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_anchor_publish_ns
{
public:
  explicit Init_SolveJob_anchor_publish_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_anchor_known anchor_publish_ns(::usv_research_interfaces::msg::SolveJob::_anchor_publish_ns_type arg)
  {
    msg_.anchor_publish_ns = std::move(arg);
    return Init_SolveJob_anchor_known(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_anchor_sequence
{
public:
  explicit Init_SolveJob_anchor_sequence(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_anchor_publish_ns anchor_sequence(::usv_research_interfaces::msg::SolveJob::_anchor_sequence_type arg)
  {
    msg_.anchor_sequence = std::move(arg);
    return Init_SolveJob_anchor_publish_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_anchor_n
{
public:
  explicit Init_SolveJob_anchor_n(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_anchor_sequence anchor_n(::usv_research_interfaces::msg::SolveJob::_anchor_n_type arg)
  {
    msg_.anchor_n = std::move(arg);
    return Init_SolveJob_anchor_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_reference
{
public:
  explicit Init_SolveJob_reference(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_anchor_n reference(::usv_research_interfaces::msg::SolveJob::_reference_type arg)
  {
    msg_.reference = std::move(arg);
    return Init_SolveJob_anchor_n(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_target_state
{
public:
  explicit Init_SolveJob_target_state(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_reference target_state(::usv_research_interfaces::msg::SolveJob::_target_state_type arg)
  {
    msg_.target_state = std::move(arg);
    return Init_SolveJob_reference(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_frozen_state
{
public:
  explicit Init_SolveJob_frozen_state(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_target_state frozen_state(::usv_research_interfaces::msg::SolveJob::_frozen_state_type arg)
  {
    msg_.frozen_state = std::move(arg);
    return Init_SolveJob_target_state(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_prediction_dt
{
public:
  explicit Init_SolveJob_prediction_dt(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_frozen_state prediction_dt(::usv_research_interfaces::msg::SolveJob::_prediction_dt_type arg)
  {
    msg_.prediction_dt = std::move(arg);
    return Init_SolveJob_frozen_state(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_horizon_steps
{
public:
  explicit Init_SolveJob_horizon_steps(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_prediction_dt horizon_steps(::usv_research_interfaces::msg::SolveJob::_horizon_steps_type arg)
  {
    msg_.horizon_steps = std::move(arg);
    return Init_SolveJob_prediction_dt(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_r_from_imu
{
public:
  explicit Init_SolveJob_r_from_imu(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_horizon_steps r_from_imu(::usv_research_interfaces::msg::SolveJob::_r_from_imu_type arg)
  {
    msg_.r_from_imu = std::move(arg);
    return Init_SolveJob_horizon_steps(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_imu_sequence
{
public:
  explicit Init_SolveJob_imu_sequence(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_r_from_imu imu_sequence(::usv_research_interfaces::msg::SolveJob::_imu_sequence_type arg)
  {
    msg_.imu_sequence = std::move(arg);
    return Init_SolveJob_r_from_imu(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_odom_sequence
{
public:
  explicit Init_SolveJob_odom_sequence(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_imu_sequence odom_sequence(::usv_research_interfaces::msg::SolveJob::_odom_sequence_type arg)
  {
    msg_.odom_sequence = std::move(arg);
    return Init_SolveJob_imu_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_imu_receive_ns
{
public:
  explicit Init_SolveJob_imu_receive_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_odom_sequence imu_receive_ns(::usv_research_interfaces::msg::SolveJob::_imu_receive_ns_type arg)
  {
    msg_.imu_receive_ns = std::move(arg);
    return Init_SolveJob_odom_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_odom_receive_ns
{
public:
  explicit Init_SolveJob_odom_receive_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_imu_receive_ns odom_receive_ns(::usv_research_interfaces::msg::SolveJob::_odom_receive_ns_type arg)
  {
    msg_.odom_receive_ns = std::move(arg);
    return Init_SolveJob_imu_receive_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_imu_stamp_ns
{
public:
  explicit Init_SolveJob_imu_stamp_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_odom_receive_ns imu_stamp_ns(::usv_research_interfaces::msg::SolveJob::_imu_stamp_ns_type arg)
  {
    msg_.imu_stamp_ns = std::move(arg);
    return Init_SolveJob_odom_receive_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_odom_stamp_ns
{
public:
  explicit Init_SolveJob_odom_stamp_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_imu_stamp_ns odom_stamp_ns(::usv_research_interfaces::msg::SolveJob::_odom_stamp_ns_type arg)
  {
    msg_.odom_stamp_ns = std::move(arg);
    return Init_SolveJob_imu_stamp_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_target_sim_ns
{
public:
  explicit Init_SolveJob_target_sim_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_odom_stamp_ns target_sim_ns(::usv_research_interfaces::msg::SolveJob::_target_sim_ns_type arg)
  {
    msg_.target_sim_ns = std::move(arg);
    return Init_SolveJob_odom_stamp_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_target_steady_ns
{
public:
  explicit Init_SolveJob_target_steady_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_target_sim_ns target_steady_ns(::usv_research_interfaces::msg::SolveJob::_target_steady_ns_type arg)
  {
    msg_.target_steady_ns = std::move(arg);
    return Init_SolveJob_target_sim_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_deadline_steady_ns
{
public:
  explicit Init_SolveJob_deadline_steady_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_target_steady_ns deadline_steady_ns(::usv_research_interfaces::msg::SolveJob::_deadline_steady_ns_type arg)
  {
    msg_.deadline_steady_ns = std::move(arg);
    return Init_SolveJob_target_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_freeze_steady_ns
{
public:
  explicit Init_SolveJob_freeze_steady_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_deadline_steady_ns freeze_steady_ns(::usv_research_interfaces::msg::SolveJob::_freeze_steady_ns_type arg)
  {
    msg_.freeze_steady_ns = std::move(arg);
    return Init_SolveJob_deadline_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_tick_origin_steady_ns
{
public:
  explicit Init_SolveJob_tick_origin_steady_ns(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_freeze_steady_ns tick_origin_steady_ns(::usv_research_interfaces::msg::SolveJob::_tick_origin_steady_ns_type arg)
  {
    msg_.tick_origin_steady_ns = std::move(arg);
    return Init_SolveJob_freeze_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_clock_epoch
{
public:
  explicit Init_SolveJob_clock_epoch(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_tick_origin_steady_ns clock_epoch(::usv_research_interfaces::msg::SolveJob::_clock_epoch_type arg)
  {
    msg_.clock_epoch = std::move(arg);
    return Init_SolveJob_tick_origin_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_schedule_generation
{
public:
  explicit Init_SolveJob_schedule_generation(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_clock_epoch schedule_generation(::usv_research_interfaces::msg::SolveJob::_schedule_generation_type arg)
  {
    msg_.schedule_generation = std::move(arg);
    return Init_SolveJob_clock_epoch(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_config_generation
{
public:
  explicit Init_SolveJob_config_generation(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_schedule_generation config_generation(::usv_research_interfaces::msg::SolveJob::_config_generation_type arg)
  {
    msg_.config_generation = std::move(arg);
    return Init_SolveJob_schedule_generation(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_model_generation
{
public:
  explicit Init_SolveJob_model_generation(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_config_generation model_generation(::usv_research_interfaces::msg::SolveJob::_model_generation_type arg)
  {
    msg_.model_generation = std::move(arg);
    return Init_SolveJob_config_generation(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_task_generation
{
public:
  explicit Init_SolveJob_task_generation(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_model_generation task_generation(::usv_research_interfaces::msg::SolveJob::_task_generation_type arg)
  {
    msg_.task_generation = std::move(arg);
    return Init_SolveJob_model_generation(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_target_tick
{
public:
  explicit Init_SolveJob_target_tick(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_task_generation target_tick(::usv_research_interfaces::msg::SolveJob::_target_tick_type arg)
  {
    msg_.target_tick = std::move(arg);
    return Init_SolveJob_task_generation(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_job_id
{
public:
  explicit Init_SolveJob_job_id(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_target_tick job_id(::usv_research_interfaces::msg::SolveJob::_job_id_type arg)
  {
    msg_.job_id = std::move(arg);
    return Init_SolveJob_target_tick(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_worker_instance
{
public:
  explicit Init_SolveJob_worker_instance(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_job_id worker_instance(::usv_research_interfaces::msg::SolveJob::_worker_instance_type arg)
  {
    msg_.worker_instance = std::move(arg);
    return Init_SolveJob_job_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_nominal_hash
{
public:
  explicit Init_SolveJob_nominal_hash(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_worker_instance nominal_hash(::usv_research_interfaces::msg::SolveJob::_nominal_hash_type arg)
  {
    msg_.nominal_hash = std::move(arg);
    return Init_SolveJob_worker_instance(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_contract_hash
{
public:
  explicit Init_SolveJob_contract_hash(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_nominal_hash contract_hash(::usv_research_interfaces::msg::SolveJob::_contract_hash_type arg)
  {
    msg_.contract_hash = std::move(arg);
    return Init_SolveJob_nominal_hash(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_boot_id
{
public:
  explicit Init_SolveJob_boot_id(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_contract_hash boot_id(::usv_research_interfaces::msg::SolveJob::_boot_id_type arg)
  {
    msg_.boot_id = std::move(arg);
    return Init_SolveJob_contract_hash(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_run_id
{
public:
  explicit Init_SolveJob_run_id(::usv_research_interfaces::msg::SolveJob & msg)
  : msg_(msg)
  {}
  Init_SolveJob_boot_id run_id(::usv_research_interfaces::msg::SolveJob::_run_id_type arg)
  {
    msg_.run_id = std::move(arg);
    return Init_SolveJob_boot_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

class Init_SolveJob_schema_version
{
public:
  Init_SolveJob_schema_version()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_SolveJob_run_id schema_version(::usv_research_interfaces::msg::SolveJob::_schema_version_type arg)
  {
    msg_.schema_version = std::move(arg);
    return Init_SolveJob_run_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveJob msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::usv_research_interfaces::msg::SolveJob>()
{
  return usv_research_interfaces::msg::builder::Init_SolveJob_schema_version();
}

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__BUILDER_HPP_
