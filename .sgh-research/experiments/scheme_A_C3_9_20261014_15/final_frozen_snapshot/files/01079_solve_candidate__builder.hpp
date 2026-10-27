// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from usv_research_interfaces:msg/SolveCandidate.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/solve_candidate.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_CANDIDATE__BUILDER_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_CANDIDATE__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "usv_research_interfaces/msg/detail/solve_candidate__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace usv_research_interfaces
{

namespace msg
{

namespace builder
{

class Init_SolveCandidate_u_prediction
{
public:
  explicit Init_SolveCandidate_u_prediction(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  ::usv_research_interfaces::msg::SolveCandidate u_prediction(::usv_research_interfaces::msg::SolveCandidate::_u_prediction_type arg)
  {
    msg_.u_prediction = std::move(arg);
    return std::move(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_x_prediction
{
public:
  explicit Init_SolveCandidate_x_prediction(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  Init_SolveCandidate_u_prediction x_prediction(::usv_research_interfaces::msg::SolveCandidate::_x_prediction_type arg)
  {
    msg_.x_prediction = std::move(arg);
    return Init_SolveCandidate_u_prediction(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_first_control
{
public:
  explicit Init_SolveCandidate_first_control(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  Init_SolveCandidate_x_prediction first_control(::usv_research_interfaces::msg::SolveCandidate::_first_control_type arg)
  {
    msg_.first_control = std::move(arg);
    return Init_SolveCandidate_x_prediction(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_backend_ms
{
public:
  explicit Init_SolveCandidate_backend_ms(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  Init_SolveCandidate_first_control backend_ms(::usv_research_interfaces::msg::SolveCandidate::_backend_ms_type arg)
  {
    msg_.backend_ms = std::move(arg);
    return Init_SolveCandidate_first_control(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_backend
{
public:
  explicit Init_SolveCandidate_backend(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  Init_SolveCandidate_backend_ms backend(::usv_research_interfaces::msg::SolveCandidate::_backend_type arg)
  {
    msg_.backend = std::move(arg);
    return Init_SolveCandidate_backend_ms(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_reason
{
public:
  explicit Init_SolveCandidate_reason(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  Init_SolveCandidate_backend reason(::usv_research_interfaces::msg::SolveCandidate::_reason_type arg)
  {
    msg_.reason = std::move(arg);
    return Init_SolveCandidate_backend(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_prediction_available
{
public:
  explicit Init_SolveCandidate_prediction_available(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  Init_SolveCandidate_reason prediction_available(::usv_research_interfaces::msg::SolveCandidate::_prediction_available_type arg)
  {
    msg_.prediction_available = std::move(arg);
    return Init_SolveCandidate_reason(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_success
{
public:
  explicit Init_SolveCandidate_success(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  Init_SolveCandidate_prediction_available success(::usv_research_interfaces::msg::SolveCandidate::_success_type arg)
  {
    msg_.success = std::move(arg);
    return Init_SolveCandidate_prediction_available(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_solver_invoked
{
public:
  explicit Init_SolveCandidate_solver_invoked(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  Init_SolveCandidate_success solver_invoked(::usv_research_interfaces::msg::SolveCandidate::_solver_invoked_type arg)
  {
    msg_.solver_invoked = std::move(arg);
    return Init_SolveCandidate_success(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_solve_end_ns
{
public:
  explicit Init_SolveCandidate_solve_end_ns(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  Init_SolveCandidate_solver_invoked solve_end_ns(::usv_research_interfaces::msg::SolveCandidate::_solve_end_ns_type arg)
  {
    msg_.solve_end_ns = std::move(arg);
    return Init_SolveCandidate_solver_invoked(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_solve_start_ns
{
public:
  explicit Init_SolveCandidate_solve_start_ns(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  Init_SolveCandidate_solve_end_ns solve_start_ns(::usv_research_interfaces::msg::SolveCandidate::_solve_start_ns_type arg)
  {
    msg_.solve_start_ns = std::move(arg);
    return Init_SolveCandidate_solve_end_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_worker_receive_ns
{
public:
  explicit Init_SolveCandidate_worker_receive_ns(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  Init_SolveCandidate_solve_start_ns worker_receive_ns(::usv_research_interfaces::msg::SolveCandidate::_worker_receive_ns_type arg)
  {
    msg_.worker_receive_ns = std::move(arg);
    return Init_SolveCandidate_solve_start_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_worker_instance
{
public:
  explicit Init_SolveCandidate_worker_instance(::usv_research_interfaces::msg::SolveCandidate & msg)
  : msg_(msg)
  {}
  Init_SolveCandidate_worker_receive_ns worker_instance(::usv_research_interfaces::msg::SolveCandidate::_worker_instance_type arg)
  {
    msg_.worker_instance = std::move(arg);
    return Init_SolveCandidate_worker_receive_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

class Init_SolveCandidate_job
{
public:
  Init_SolveCandidate_job()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_SolveCandidate_worker_instance job(::usv_research_interfaces::msg::SolveCandidate::_job_type arg)
  {
    msg_.job = std::move(arg);
    return Init_SolveCandidate_worker_instance(msg_);
  }

private:
  ::usv_research_interfaces::msg::SolveCandidate msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::usv_research_interfaces::msg::SolveCandidate>()
{
  return usv_research_interfaces::msg::builder::Init_SolveCandidate_job();
}

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_CANDIDATE__BUILDER_HPP_
