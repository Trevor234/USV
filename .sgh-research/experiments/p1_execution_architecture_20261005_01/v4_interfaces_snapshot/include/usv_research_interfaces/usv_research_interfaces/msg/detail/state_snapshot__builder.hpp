// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from usv_research_interfaces:msg/StateSnapshot.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/state_snapshot.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__STATE_SNAPSHOT__BUILDER_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__STATE_SNAPSHOT__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "usv_research_interfaces/msg/detail/state_snapshot__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace usv_research_interfaces
{

namespace msg
{

namespace builder
{

class Init_StateSnapshot_source_topic
{
public:
  explicit Init_StateSnapshot_source_topic(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  ::usv_research_interfaces::msg::StateSnapshot source_topic(::usv_research_interfaces::msg::StateSnapshot::_source_topic_type arg)
  {
    msg_.source_topic = std::move(arg);
    return std::move(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_quality_reason
{
public:
  explicit Init_StateSnapshot_quality_reason(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_source_topic quality_reason(::usv_research_interfaces::msg::StateSnapshot::_quality_reason_type arg)
  {
    msg_.quality_reason = std::move(arg);
    return Init_StateSnapshot_source_topic(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_valid
{
public:
  explicit Init_StateSnapshot_valid(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_quality_reason valid(::usv_research_interfaces::msg::StateSnapshot::_valid_type arg)
  {
    msg_.valid = std::move(arg);
    return Init_StateSnapshot_quality_reason(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_state_6
{
public:
  explicit Init_StateSnapshot_state_6(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_valid state_6(::usv_research_interfaces::msg::StateSnapshot::_state_6_type arg)
  {
    msg_.state_6 = std::move(arg);
    return Init_StateSnapshot_valid(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_child_frame_id
{
public:
  explicit Init_StateSnapshot_child_frame_id(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_state_6 child_frame_id(::usv_research_interfaces::msg::StateSnapshot::_child_frame_id_type arg)
  {
    msg_.child_frame_id = std::move(arg);
    return Init_StateSnapshot_state_6(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_frame_id
{
public:
  explicit Init_StateSnapshot_frame_id(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_child_frame_id frame_id(::usv_research_interfaces::msg::StateSnapshot::_frame_id_type arg)
  {
    msg_.frame_id = std::move(arg);
    return Init_StateSnapshot_child_frame_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_freeze_steady_ns
{
public:
  explicit Init_StateSnapshot_freeze_steady_ns(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_frame_id freeze_steady_ns(::usv_research_interfaces::msg::StateSnapshot::_freeze_steady_ns_type arg)
  {
    msg_.freeze_steady_ns = std::move(arg);
    return Init_StateSnapshot_frame_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_receive_steady_ns
{
public:
  explicit Init_StateSnapshot_receive_steady_ns(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_freeze_steady_ns receive_steady_ns(::usv_research_interfaces::msg::StateSnapshot::_receive_steady_ns_type arg)
  {
    msg_.receive_steady_ns = std::move(arg);
    return Init_StateSnapshot_freeze_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_odom_stamp_ns
{
public:
  explicit Init_StateSnapshot_odom_stamp_ns(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_receive_steady_ns odom_stamp_ns(::usv_research_interfaces::msg::StateSnapshot::_odom_stamp_ns_type arg)
  {
    msg_.odom_stamp_ns = std::move(arg);
    return Init_StateSnapshot_receive_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_received_odom_sequence
{
public:
  explicit Init_StateSnapshot_received_odom_sequence(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_odom_stamp_ns received_odom_sequence(::usv_research_interfaces::msg::StateSnapshot::_received_odom_sequence_type arg)
  {
    msg_.received_odom_sequence = std::move(arg);
    return Init_StateSnapshot_odom_stamp_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_steady_clock_domain
{
public:
  explicit Init_StateSnapshot_steady_clock_domain(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_received_odom_sequence steady_clock_domain(::usv_research_interfaces::msg::StateSnapshot::_steady_clock_domain_type arg)
  {
    msg_.steady_clock_domain = std::move(arg);
    return Init_StateSnapshot_received_odom_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_clock_status
{
public:
  explicit Init_StateSnapshot_clock_status(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_steady_clock_domain clock_status(::usv_research_interfaces::msg::StateSnapshot::_clock_status_type arg)
  {
    msg_.clock_status = std::move(arg);
    return Init_StateSnapshot_steady_clock_domain(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_clock_age_ns
{
public:
  explicit Init_StateSnapshot_clock_age_ns(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_clock_status clock_age_ns(::usv_research_interfaces::msg::StateSnapshot::_clock_age_ns_type arg)
  {
    msg_.clock_age_ns = std::move(arg);
    return Init_StateSnapshot_clock_status(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_clock_receive_steady_ns
{
public:
  explicit Init_StateSnapshot_clock_receive_steady_ns(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_clock_age_ns clock_receive_steady_ns(::usv_research_interfaces::msg::StateSnapshot::_clock_receive_steady_ns_type arg)
  {
    msg_.clock_receive_steady_ns = std::move(arg);
    return Init_StateSnapshot_clock_age_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_sim_time_ns
{
public:
  explicit Init_StateSnapshot_sim_time_ns(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_clock_receive_steady_ns sim_time_ns(::usv_research_interfaces::msg::StateSnapshot::_sim_time_ns_type arg)
  {
    msg_.sim_time_ns = std::move(arg);
    return Init_StateSnapshot_clock_receive_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_clock_epoch
{
public:
  explicit Init_StateSnapshot_clock_epoch(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_sim_time_ns clock_epoch(::usv_research_interfaces::msg::StateSnapshot::_clock_epoch_type arg)
  {
    msg_.clock_epoch = std::move(arg);
    return Init_StateSnapshot_sim_time_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_sequence
{
public:
  explicit Init_StateSnapshot_sequence(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_clock_epoch sequence(::usv_research_interfaces::msg::StateSnapshot::_sequence_type arg)
  {
    msg_.sequence = std::move(arg);
    return Init_StateSnapshot_clock_epoch(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_config_hash
{
public:
  explicit Init_StateSnapshot_config_hash(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_sequence config_hash(::usv_research_interfaces::msg::StateSnapshot::_config_hash_type arg)
  {
    msg_.config_hash = std::move(arg);
    return Init_StateSnapshot_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_baseline_id
{
public:
  explicit Init_StateSnapshot_baseline_id(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_config_hash baseline_id(::usv_research_interfaces::msg::StateSnapshot::_baseline_id_type arg)
  {
    msg_.baseline_id = std::move(arg);
    return Init_StateSnapshot_config_hash(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_producer_instance_id
{
public:
  explicit Init_StateSnapshot_producer_instance_id(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_baseline_id producer_instance_id(::usv_research_interfaces::msg::StateSnapshot::_producer_instance_id_type arg)
  {
    msg_.producer_instance_id = std::move(arg);
    return Init_StateSnapshot_baseline_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_run_id
{
public:
  explicit Init_StateSnapshot_run_id(::usv_research_interfaces::msg::StateSnapshot & msg)
  : msg_(msg)
  {}
  Init_StateSnapshot_producer_instance_id run_id(::usv_research_interfaces::msg::StateSnapshot::_run_id_type arg)
  {
    msg_.run_id = std::move(arg);
    return Init_StateSnapshot_producer_instance_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

class Init_StateSnapshot_schema_version
{
public:
  Init_StateSnapshot_schema_version()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_StateSnapshot_run_id schema_version(::usv_research_interfaces::msg::StateSnapshot::_schema_version_type arg)
  {
    msg_.schema_version = std::move(arg);
    return Init_StateSnapshot_run_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::StateSnapshot msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::usv_research_interfaces::msg::StateSnapshot>()
{
  return usv_research_interfaces::msg::builder::Init_StateSnapshot_schema_version();
}

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__STATE_SNAPSHOT__BUILDER_HPP_
