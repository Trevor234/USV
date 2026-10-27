// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from usv_research_interfaces:msg/StateSnapshot.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/state_snapshot.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__STATE_SNAPSHOT__STRUCT_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__STATE_SNAPSHOT__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


#ifndef _WIN32
# define DEPRECATED__usv_research_interfaces__msg__StateSnapshot __attribute__((deprecated))
#else
# define DEPRECATED__usv_research_interfaces__msg__StateSnapshot __declspec(deprecated)
#endif

namespace usv_research_interfaces
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct StateSnapshot_
{
  using Type = StateSnapshot_<ContainerAllocator>;

  explicit StateSnapshot_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
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
      this->received_odom_sequence = 0ull;
      this->odom_stamp_ns = 0ll;
      this->receive_steady_ns = 0ll;
      this->freeze_steady_ns = 0ll;
      this->frame_id = "";
      this->child_frame_id = "";
      std::fill<typename std::array<double, 6>::iterator, double>(this->state_6.begin(), this->state_6.end(), 0.0);
      this->valid = false;
      this->quality_reason = "";
      this->source_topic = "";
    }
  }

  explicit StateSnapshot_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : schema_version(_alloc),
    run_id(_alloc),
    producer_instance_id(_alloc),
    baseline_id(_alloc),
    config_hash(_alloc),
    clock_status(_alloc),
    steady_clock_domain(_alloc),
    frame_id(_alloc),
    child_frame_id(_alloc),
    state_6(_alloc),
    quality_reason(_alloc),
    source_topic(_alloc)
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
      this->received_odom_sequence = 0ull;
      this->odom_stamp_ns = 0ll;
      this->receive_steady_ns = 0ll;
      this->freeze_steady_ns = 0ll;
      this->frame_id = "";
      this->child_frame_id = "";
      std::fill<typename std::array<double, 6>::iterator, double>(this->state_6.begin(), this->state_6.end(), 0.0);
      this->valid = false;
      this->quality_reason = "";
      this->source_topic = "";
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
  using _received_odom_sequence_type =
    uint64_t;
  _received_odom_sequence_type received_odom_sequence;
  using _odom_stamp_ns_type =
    int64_t;
  _odom_stamp_ns_type odom_stamp_ns;
  using _receive_steady_ns_type =
    int64_t;
  _receive_steady_ns_type receive_steady_ns;
  using _freeze_steady_ns_type =
    int64_t;
  _freeze_steady_ns_type freeze_steady_ns;
  using _frame_id_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _frame_id_type frame_id;
  using _child_frame_id_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _child_frame_id_type child_frame_id;
  using _state_6_type =
    std::array<double, 6>;
  _state_6_type state_6;
  using _valid_type =
    bool;
  _valid_type valid;
  using _quality_reason_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _quality_reason_type quality_reason;
  using _source_topic_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _source_topic_type source_topic;

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
  Type & set__received_odom_sequence(
    const uint64_t & _arg)
  {
    this->received_odom_sequence = _arg;
    return *this;
  }
  Type & set__odom_stamp_ns(
    const int64_t & _arg)
  {
    this->odom_stamp_ns = _arg;
    return *this;
  }
  Type & set__receive_steady_ns(
    const int64_t & _arg)
  {
    this->receive_steady_ns = _arg;
    return *this;
  }
  Type & set__freeze_steady_ns(
    const int64_t & _arg)
  {
    this->freeze_steady_ns = _arg;
    return *this;
  }
  Type & set__frame_id(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->frame_id = _arg;
    return *this;
  }
  Type & set__child_frame_id(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->child_frame_id = _arg;
    return *this;
  }
  Type & set__state_6(
    const std::array<double, 6> & _arg)
  {
    this->state_6 = _arg;
    return *this;
  }
  Type & set__valid(
    const bool & _arg)
  {
    this->valid = _arg;
    return *this;
  }
  Type & set__quality_reason(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->quality_reason = _arg;
    return *this;
  }
  Type & set__source_topic(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->source_topic = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    usv_research_interfaces::msg::StateSnapshot_<ContainerAllocator> *;
  using ConstRawPtr =
    const usv_research_interfaces::msg::StateSnapshot_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::StateSnapshot_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::StateSnapshot_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::StateSnapshot_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::StateSnapshot_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::StateSnapshot_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::StateSnapshot_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::StateSnapshot_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::StateSnapshot_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__usv_research_interfaces__msg__StateSnapshot
    std::shared_ptr<usv_research_interfaces::msg::StateSnapshot_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__usv_research_interfaces__msg__StateSnapshot
    std::shared_ptr<usv_research_interfaces::msg::StateSnapshot_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const StateSnapshot_ & other) const
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
    if (this->received_odom_sequence != other.received_odom_sequence) {
      return false;
    }
    if (this->odom_stamp_ns != other.odom_stamp_ns) {
      return false;
    }
    if (this->receive_steady_ns != other.receive_steady_ns) {
      return false;
    }
    if (this->freeze_steady_ns != other.freeze_steady_ns) {
      return false;
    }
    if (this->frame_id != other.frame_id) {
      return false;
    }
    if (this->child_frame_id != other.child_frame_id) {
      return false;
    }
    if (this->state_6 != other.state_6) {
      return false;
    }
    if (this->valid != other.valid) {
      return false;
    }
    if (this->quality_reason != other.quality_reason) {
      return false;
    }
    if (this->source_topic != other.source_topic) {
      return false;
    }
    return true;
  }
  bool operator!=(const StateSnapshot_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct StateSnapshot_

// alias to use template instance with default allocator
using StateSnapshot =
  usv_research_interfaces::msg::StateSnapshot_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__STATE_SNAPSHOT__STRUCT_HPP_
