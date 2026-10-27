// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from usv_research_interfaces:msg/SolveCandidate.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/solve_candidate.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_CANDIDATE__STRUCT_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_CANDIDATE__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


// Include directives for member types
// Member 'job'
#include "usv_research_interfaces/msg/detail/solve_job__struct.hpp"

#ifndef _WIN32
# define DEPRECATED__usv_research_interfaces__msg__SolveCandidate __attribute__((deprecated))
#else
# define DEPRECATED__usv_research_interfaces__msg__SolveCandidate __declspec(deprecated)
#endif

namespace usv_research_interfaces
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct SolveCandidate_
{
  using Type = SolveCandidate_<ContainerAllocator>;

  explicit SolveCandidate_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : job(_init)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->worker_instance = "";
      this->worker_receive_ns = 0ll;
      this->solve_start_ns = 0ll;
      this->solve_end_ns = 0ll;
      this->solver_invoked = false;
      this->success = false;
      this->prediction_available = false;
      this->reason = "";
      this->backend = "";
      this->backend_ms = 0.0;
      std::fill<typename std::array<double, 2>::iterator, double>(this->first_control.begin(), this->first_control.end(), 0.0);
      std::fill<typename std::array<double, 126>::iterator, double>(this->x_prediction.begin(), this->x_prediction.end(), 0.0);
      std::fill<typename std::array<double, 40>::iterator, double>(this->u_prediction.begin(), this->u_prediction.end(), 0.0);
    }
  }

  explicit SolveCandidate_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : job(_alloc, _init),
    worker_instance(_alloc),
    reason(_alloc),
    backend(_alloc),
    first_control(_alloc),
    x_prediction(_alloc),
    u_prediction(_alloc)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->worker_instance = "";
      this->worker_receive_ns = 0ll;
      this->solve_start_ns = 0ll;
      this->solve_end_ns = 0ll;
      this->solver_invoked = false;
      this->success = false;
      this->prediction_available = false;
      this->reason = "";
      this->backend = "";
      this->backend_ms = 0.0;
      std::fill<typename std::array<double, 2>::iterator, double>(this->first_control.begin(), this->first_control.end(), 0.0);
      std::fill<typename std::array<double, 126>::iterator, double>(this->x_prediction.begin(), this->x_prediction.end(), 0.0);
      std::fill<typename std::array<double, 40>::iterator, double>(this->u_prediction.begin(), this->u_prediction.end(), 0.0);
    }
  }

  // field types and members
  using _job_type =
    usv_research_interfaces::msg::SolveJob_<ContainerAllocator>;
  _job_type job;
  using _worker_instance_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _worker_instance_type worker_instance;
  using _worker_receive_ns_type =
    int64_t;
  _worker_receive_ns_type worker_receive_ns;
  using _solve_start_ns_type =
    int64_t;
  _solve_start_ns_type solve_start_ns;
  using _solve_end_ns_type =
    int64_t;
  _solve_end_ns_type solve_end_ns;
  using _solver_invoked_type =
    bool;
  _solver_invoked_type solver_invoked;
  using _success_type =
    bool;
  _success_type success;
  using _prediction_available_type =
    bool;
  _prediction_available_type prediction_available;
  using _reason_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _reason_type reason;
  using _backend_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _backend_type backend;
  using _backend_ms_type =
    double;
  _backend_ms_type backend_ms;
  using _first_control_type =
    std::array<double, 2>;
  _first_control_type first_control;
  using _x_prediction_type =
    std::array<double, 126>;
  _x_prediction_type x_prediction;
  using _u_prediction_type =
    std::array<double, 40>;
  _u_prediction_type u_prediction;

  // setters for named parameter idiom
  Type & set__job(
    const usv_research_interfaces::msg::SolveJob_<ContainerAllocator> & _arg)
  {
    this->job = _arg;
    return *this;
  }
  Type & set__worker_instance(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->worker_instance = _arg;
    return *this;
  }
  Type & set__worker_receive_ns(
    const int64_t & _arg)
  {
    this->worker_receive_ns = _arg;
    return *this;
  }
  Type & set__solve_start_ns(
    const int64_t & _arg)
  {
    this->solve_start_ns = _arg;
    return *this;
  }
  Type & set__solve_end_ns(
    const int64_t & _arg)
  {
    this->solve_end_ns = _arg;
    return *this;
  }
  Type & set__solver_invoked(
    const bool & _arg)
  {
    this->solver_invoked = _arg;
    return *this;
  }
  Type & set__success(
    const bool & _arg)
  {
    this->success = _arg;
    return *this;
  }
  Type & set__prediction_available(
    const bool & _arg)
  {
    this->prediction_available = _arg;
    return *this;
  }
  Type & set__reason(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->reason = _arg;
    return *this;
  }
  Type & set__backend(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->backend = _arg;
    return *this;
  }
  Type & set__backend_ms(
    const double & _arg)
  {
    this->backend_ms = _arg;
    return *this;
  }
  Type & set__first_control(
    const std::array<double, 2> & _arg)
  {
    this->first_control = _arg;
    return *this;
  }
  Type & set__x_prediction(
    const std::array<double, 126> & _arg)
  {
    this->x_prediction = _arg;
    return *this;
  }
  Type & set__u_prediction(
    const std::array<double, 40> & _arg)
  {
    this->u_prediction = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    usv_research_interfaces::msg::SolveCandidate_<ContainerAllocator> *;
  using ConstRawPtr =
    const usv_research_interfaces::msg::SolveCandidate_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::SolveCandidate_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::SolveCandidate_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::SolveCandidate_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::SolveCandidate_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::SolveCandidate_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::SolveCandidate_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::SolveCandidate_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::SolveCandidate_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__usv_research_interfaces__msg__SolveCandidate
    std::shared_ptr<usv_research_interfaces::msg::SolveCandidate_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__usv_research_interfaces__msg__SolveCandidate
    std::shared_ptr<usv_research_interfaces::msg::SolveCandidate_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const SolveCandidate_ & other) const
  {
    if (this->job != other.job) {
      return false;
    }
    if (this->worker_instance != other.worker_instance) {
      return false;
    }
    if (this->worker_receive_ns != other.worker_receive_ns) {
      return false;
    }
    if (this->solve_start_ns != other.solve_start_ns) {
      return false;
    }
    if (this->solve_end_ns != other.solve_end_ns) {
      return false;
    }
    if (this->solver_invoked != other.solver_invoked) {
      return false;
    }
    if (this->success != other.success) {
      return false;
    }
    if (this->prediction_available != other.prediction_available) {
      return false;
    }
    if (this->reason != other.reason) {
      return false;
    }
    if (this->backend != other.backend) {
      return false;
    }
    if (this->backend_ms != other.backend_ms) {
      return false;
    }
    if (this->first_control != other.first_control) {
      return false;
    }
    if (this->x_prediction != other.x_prediction) {
      return false;
    }
    if (this->u_prediction != other.u_prediction) {
      return false;
    }
    return true;
  }
  bool operator!=(const SolveCandidate_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct SolveCandidate_

// alias to use template instance with default allocator
using SolveCandidate =
  usv_research_interfaces::msg::SolveCandidate_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_CANDIDATE__STRUCT_HPP_
