// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from usv_research_interfaces:msg/CycleTiming.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/cycle_timing.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__CYCLE_TIMING__STRUCT_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__CYCLE_TIMING__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


#ifndef _WIN32
# define DEPRECATED__usv_research_interfaces__msg__CycleTiming __attribute__((deprecated))
#else
# define DEPRECATED__usv_research_interfaces__msg__CycleTiming __declspec(deprecated)
#endif

namespace usv_research_interfaces
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct CycleTiming_
{
  using Type = CycleTiming_<ContainerAllocator>;

  explicit CycleTiming_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->schema_version = "";
      this->run_id = "";
      this->producer_instance_id = "";
      this->baseline_id = "";
      this->config_hash = "";
      this->sequence = 0ull;
      this->clock_epoch = 0ull;
      this->sim_time_ns = 0ll;
      this->clock_receive_steady_ns = 0ll;
      this->clock_age_ns = 0ll;
      this->clock_status = "";
      this->steady_clock_domain = "";
      this->timer_entry_steady_ns = 0ll;
      this->state_copy_steady_ns = 0ll;
      this->reference_ready_steady_ns = 0ll;
      this->solve_start_steady_ns = 0ll;
      this->solve_end_steady_ns = 0ll;
      this->publish_end_steady_ns = 0ll;
      std::fill<typename std::array<double, 6>::iterator, double>(this->controller_state_6.begin(), this->controller_state_6.end(), 0.0);
      this->state_kind = "";
      this->received_odom_sequence = 0ull;
      this->received_imu_sequence = 0ull;
      this->odom_stamp_ns = 0ll;
      this->imu_stamp_ns = 0ll;
      this->backend_time_ms = 0.0;
      this->budget_ms = 0.0;
      this->success = false;
      this->deadline_miss = false;
      this->rejection_reason = "";
      this->applied_sequence = 0ull;
      this->solve_invoked = false;
    }
  }

  explicit CycleTiming_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : schema_version(_alloc),
    run_id(_alloc),
    producer_instance_id(_alloc),
    baseline_id(_alloc),
    config_hash(_alloc),
    clock_status(_alloc),
    steady_clock_domain(_alloc),
    controller_state_6(_alloc),
    state_kind(_alloc),
    rejection_reason(_alloc)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->schema_version = "";
      this->run_id = "";
      this->producer_instance_id = "";
      this->baseline_id = "";
      this->config_hash = "";
      this->sequence = 0ull;
      this->clock_epoch = 0ull;
      this->sim_time_ns = 0ll;
      this->clock_receive_steady_ns = 0ll;
      this->clock_age_ns = 0ll;
      this->clock_status = "";
      this->steady_clock_domain = "";
      this->timer_entry_steady_ns = 0ll;
      this->state_copy_steady_ns = 0ll;
      this->reference_ready_steady_ns = 0ll;
      this->solve_start_steady_ns = 0ll;
      this->solve_end_steady_ns = 0ll;
      this->publish_end_steady_ns = 0ll;
      std::fill<typename std::array<double, 6>::iterator, double>(this->controller_state_6.begin(), this->controller_state_6.end(), 0.0);
      this->state_kind = "";
      this->received_odom_sequence = 0ull;
      this->received_imu_sequence = 0ull;
      this->odom_stamp_ns = 0ll;
      this->imu_stamp_ns = 0ll;
      this->backend_time_ms = 0.0;
      this->budget_ms = 0.0;
      this->success = false;
      this->deadline_miss = false;
      this->rejection_reason = "";
      this->applied_sequence = 0ull;
      this->solve_invoked = false;
    }
  }

  // field types and members
  using _schema_version_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _schema_version_type schema_version;
  using _run_id_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _run_id_type run_id;
  using _producer_instance_id_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _producer_instance_id_type producer_instance_id;
  using _baseline_id_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _baseline_id_type baseline_id;
  using _config_hash_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _config_hash_type config_hash;
  using _sequence_type =
    uint64_t;
  _sequence_type sequence;
  using _clock_epoch_type =
    uint64_t;
  _clock_epoch_type clock_epoch;
  using _sim_time_ns_type =
    int64_t;
  _sim_time_ns_type sim_time_ns;
  using _clock_receive_steady_ns_type =
    int64_t;
  _clock_receive_steady_ns_type clock_receive_steady_ns;
  using _clock_age_ns_type =
    int64_t;
  _clock_age_ns_type clock_age_ns;
  using _clock_status_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _clock_status_type clock_status;
  using _steady_clock_domain_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _steady_clock_domain_type steady_clock_domain;
  using _timer_entry_steady_ns_type =
    int64_t;
  _timer_entry_steady_ns_type timer_entry_steady_ns;
  using _state_copy_steady_ns_type =
    int64_t;
  _state_copy_steady_ns_type state_copy_steady_ns;
  using _reference_ready_steady_ns_type =
    int64_t;
  _reference_ready_steady_ns_type reference_ready_steady_ns;
  using _solve_start_steady_ns_type =
    int64_t;
  _solve_start_steady_ns_type solve_start_steady_ns;
  using _solve_end_steady_ns_type =
    int64_t;
  _solve_end_steady_ns_type solve_end_steady_ns;
  using _publish_end_steady_ns_type =
    int64_t;
  _publish_end_steady_ns_type publish_end_steady_ns;
  using _controller_state_6_type =
    std::array<double, 6>;
  _controller_state_6_type controller_state_6;
  using _state_kind_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _state_kind_type state_kind;
  using _received_odom_sequence_type =
    uint64_t;
  _received_odom_sequence_type received_odom_sequence;
  using _received_imu_sequence_type =
    uint64_t;
  _received_imu_sequence_type received_imu_sequence;
  using _odom_stamp_ns_type =
    int64_t;
  _odom_stamp_ns_type odom_stamp_ns;
  using _imu_stamp_ns_type =
    int64_t;
  _imu_stamp_ns_type imu_stamp_ns;
  using _backend_time_ms_type =
    double;
  _backend_time_ms_type backend_time_ms;
  using _budget_ms_type =
    double;
  _budget_ms_type budget_ms;
  using _success_type =
    bool;
  _success_type success;
  using _deadline_miss_type =
    bool;
  _deadline_miss_type deadline_miss;
  using _rejection_reason_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _rejection_reason_type rejection_reason;
  using _applied_sequence_type =
    uint64_t;
  _applied_sequence_type applied_sequence;
  using _solve_invoked_type =
    bool;
  _solve_invoked_type solve_invoked;

  // setters for named parameter idiom
  Type & set__schema_version(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->schema_version = _arg;
    return *this;
  }
  Type & set__run_id(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->run_id = _arg;
    return *this;
  }
  Type & set__producer_instance_id(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->producer_instance_id = _arg;
    return *this;
  }
  Type & set__baseline_id(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->baseline_id = _arg;
    return *this;
  }
  Type & set__config_hash(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->config_hash = _arg;
    return *this;
  }
  Type & set__sequence(
    const uint64_t & _arg)
  {
    this->sequence = _arg;
    return *this;
  }
  Type & set__clock_epoch(
    const uint64_t & _arg)
  {
    this->clock_epoch = _arg;
    return *this;
  }
  Type & set__sim_time_ns(
    const int64_t & _arg)
  {
    this->sim_time_ns = _arg;
    return *this;
  }
  Type & set__clock_receive_steady_ns(
    const int64_t & _arg)
  {
    this->clock_receive_steady_ns = _arg;
    return *this;
  }
  Type & set__clock_age_ns(
    const int64_t & _arg)
  {
    this->clock_age_ns = _arg;
    return *this;
  }
  Type & set__clock_status(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->clock_status = _arg;
    return *this;
  }
  Type & set__steady_clock_domain(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->steady_clock_domain = _arg;
    return *this;
  }
  Type & set__timer_entry_steady_ns(
    const int64_t & _arg)
  {
    this->timer_entry_steady_ns = _arg;
    return *this;
  }
  Type & set__state_copy_steady_ns(
    const int64_t & _arg)
  {
    this->state_copy_steady_ns = _arg;
    return *this;
  }
  Type & set__reference_ready_steady_ns(
    const int64_t & _arg)
  {
    this->reference_ready_steady_ns = _arg;
    return *this;
  }
  Type & set__solve_start_steady_ns(
    const int64_t & _arg)
  {
    this->solve_start_steady_ns = _arg;
    return *this;
  }
  Type & set__solve_end_steady_ns(
    const int64_t & _arg)
  {
    this->solve_end_steady_ns = _arg;
    return *this;
  }
  Type & set__publish_end_steady_ns(
    const int64_t & _arg)
  {
    this->publish_end_steady_ns = _arg;
    return *this;
  }
  Type & set__controller_state_6(
    const std::array<double, 6> & _arg)
  {
    this->controller_state_6 = _arg;
    return *this;
  }
  Type & set__state_kind(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->state_kind = _arg;
    return *this;
  }
  Type & set__received_odom_sequence(
    const uint64_t & _arg)
  {
    this->received_odom_sequence = _arg;
    return *this;
  }
  Type & set__received_imu_sequence(
    const uint64_t & _arg)
  {
    this->received_imu_sequence = _arg;
    return *this;
  }
  Type & set__odom_stamp_ns(
    const int64_t & _arg)
  {
    this->odom_stamp_ns = _arg;
    return *this;
  }
  Type & set__imu_stamp_ns(
    const int64_t & _arg)
  {
    this->imu_stamp_ns = _arg;
    return *this;
  }
  Type & set__backend_time_ms(
    const double & _arg)
  {
    this->backend_time_ms = _arg;
    return *this;
  }
  Type & set__budget_ms(
    const double & _arg)
  {
    this->budget_ms = _arg;
    return *this;
  }
  Type & set__success(
    const bool & _arg)
  {
    this->success = _arg;
    return *this;
  }
  Type & set__deadline_miss(
    const bool & _arg)
  {
    this->deadline_miss = _arg;
    return *this;
  }
  Type & set__rejection_reason(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->rejection_reason = _arg;
    return *this;
  }
  Type & set__applied_sequence(
    const uint64_t & _arg)
  {
    this->applied_sequence = _arg;
    return *this;
  }
  Type & set__solve_invoked(
    const bool & _arg)
  {
    this->solve_invoked = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    usv_research_interfaces::msg::CycleTiming_<ContainerAllocator> *;
  using ConstRawPtr =
    const usv_research_interfaces::msg::CycleTiming_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::CycleTiming_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::CycleTiming_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::CycleTiming_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::CycleTiming_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::CycleTiming_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::CycleTiming_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::CycleTiming_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::CycleTiming_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__usv_research_interfaces__msg__CycleTiming
    std::shared_ptr<usv_research_interfaces::msg::CycleTiming_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__usv_research_interfaces__msg__CycleTiming
    std::shared_ptr<usv_research_interfaces::msg::CycleTiming_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const CycleTiming_ & other) const
  {
    if (this->schema_version != other.schema_version) {
      return false;
    }
    if (this->run_id != other.run_id) {
      return false;
    }
    if (this->producer_instance_id != other.producer_instance_id) {
      return false;
    }
    if (this->baseline_id != other.baseline_id) {
      return false;
    }
    if (this->config_hash != other.config_hash) {
      return false;
    }
    if (this->sequence != other.sequence) {
      return false;
    }
    if (this->clock_epoch != other.clock_epoch) {
      return false;
    }
    if (this->sim_time_ns != other.sim_time_ns) {
      return false;
    }
    if (this->clock_receive_steady_ns != other.clock_receive_steady_ns) {
      return false;
    }
    if (this->clock_age_ns != other.clock_age_ns) {
      return false;
    }
    if (this->clock_status != other.clock_status) {
      return false;
    }
    if (this->steady_clock_domain != other.steady_clock_domain) {
      return false;
    }
    if (this->timer_entry_steady_ns != other.timer_entry_steady_ns) {
      return false;
    }
    if (this->state_copy_steady_ns != other.state_copy_steady_ns) {
      return false;
    }
    if (this->reference_ready_steady_ns != other.reference_ready_steady_ns) {
      return false;
    }
    if (this->solve_start_steady_ns != other.solve_start_steady_ns) {
      return false;
    }
    if (this->solve_end_steady_ns != other.solve_end_steady_ns) {
      return false;
    }
    if (this->publish_end_steady_ns != other.publish_end_steady_ns) {
      return false;
    }
    if (this->controller_state_6 != other.controller_state_6) {
      return false;
    }
    if (this->state_kind != other.state_kind) {
      return false;
    }
    if (this->received_odom_sequence != other.received_odom_sequence) {
      return false;
    }
    if (this->received_imu_sequence != other.received_imu_sequence) {
      return false;
    }
    if (this->odom_stamp_ns != other.odom_stamp_ns) {
      return false;
    }
    if (this->imu_stamp_ns != other.imu_stamp_ns) {
      return false;
    }
    if (this->backend_time_ms != other.backend_time_ms) {
      return false;
    }
    if (this->budget_ms != other.budget_ms) {
      return false;
    }
    if (this->success != other.success) {
      return false;
    }
    if (this->deadline_miss != other.deadline_miss) {
      return false;
    }
    if (this->rejection_reason != other.rejection_reason) {
      return false;
    }
    if (this->applied_sequence != other.applied_sequence) {
      return false;
    }
    if (this->solve_invoked != other.solve_invoked) {
      return false;
    }
    return true;
  }
  bool operator!=(const CycleTiming_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct CycleTiming_

// alias to use template instance with default allocator
using CycleTiming =
  usv_research_interfaces::msg::CycleTiming_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__CYCLE_TIMING__STRUCT_HPP_
