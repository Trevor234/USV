// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from usv_research_interfaces:msg/AppliedControl.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/applied_control.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__APPLIED_CONTROL__STRUCT_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__APPLIED_CONTROL__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


#ifndef _WIN32
# define DEPRECATED__usv_research_interfaces__msg__AppliedControl __attribute__((deprecated))
#else
# define DEPRECATED__usv_research_interfaces__msg__AppliedControl __declspec(deprecated)
#endif

namespace usv_research_interfaces
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct AppliedControl_
{
  using Type = AppliedControl_<ContainerAllocator>;

  explicit AppliedControl_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
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
      this->cycle_sequence = 0ull;
      this->control_source = "";
      this->event_semantics = "";
      this->requested_known = false;
      std::fill<typename std::array<double, 2>::iterator, double>(this->requested_n.begin(), this->requested_n.end(), 0.0);
      std::fill<typename std::array<double, 2>::iterator, double>(this->final_n.begin(), this->final_n.end(), 0.0);
      this->left_publish_success = false;
      this->right_publish_success = false;
      this->left_publish_start_steady_ns = 0ll;
      this->left_publish_end_steady_ns = 0ll;
      this->right_publish_start_steady_ns = 0ll;
      this->right_publish_end_steady_ns = 0ll;
      this->left_sim_time_ns = 0ll;
      this->right_sim_time_ns = 0ll;
      this->left_clock_epoch = 0ull;
      this->right_clock_epoch = 0ull;
      this->left_clock_age_ns = 0ll;
      this->right_clock_age_ns = 0ll;
      this->map_scale = 0.0;
      this->lower_n = 0.0;
      this->upper_n = 0.0;
      this->previous_anchor_known = false;
      std::fill<typename std::array<double, 2>::iterator, double>(this->previous_final_n.begin(), this->previous_final_n.end(), 0.0);
      this->plant_acceptance_observed = false;
      this->force_measured = false;
      this->execution_atomicity_proven = false;
      this->publish_error = "";
    }
  }

  explicit AppliedControl_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : schema_version(_alloc),
    run_id(_alloc),
    producer_instance_id(_alloc),
    baseline_id(_alloc),
    config_hash(_alloc),
    clock_status(_alloc),
    steady_clock_domain(_alloc),
    control_source(_alloc),
    event_semantics(_alloc),
    requested_n(_alloc),
    final_n(_alloc),
    previous_final_n(_alloc),
    publish_error(_alloc)
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
      this->cycle_sequence = 0ull;
      this->control_source = "";
      this->event_semantics = "";
      this->requested_known = false;
      std::fill<typename std::array<double, 2>::iterator, double>(this->requested_n.begin(), this->requested_n.end(), 0.0);
      std::fill<typename std::array<double, 2>::iterator, double>(this->final_n.begin(), this->final_n.end(), 0.0);
      this->left_publish_success = false;
      this->right_publish_success = false;
      this->left_publish_start_steady_ns = 0ll;
      this->left_publish_end_steady_ns = 0ll;
      this->right_publish_start_steady_ns = 0ll;
      this->right_publish_end_steady_ns = 0ll;
      this->left_sim_time_ns = 0ll;
      this->right_sim_time_ns = 0ll;
      this->left_clock_epoch = 0ull;
      this->right_clock_epoch = 0ull;
      this->left_clock_age_ns = 0ll;
      this->right_clock_age_ns = 0ll;
      this->map_scale = 0.0;
      this->lower_n = 0.0;
      this->upper_n = 0.0;
      this->previous_anchor_known = false;
      std::fill<typename std::array<double, 2>::iterator, double>(this->previous_final_n.begin(), this->previous_final_n.end(), 0.0);
      this->plant_acceptance_observed = false;
      this->force_measured = false;
      this->execution_atomicity_proven = false;
      this->publish_error = "";
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
  using _cycle_sequence_type =
    uint64_t;
  _cycle_sequence_type cycle_sequence;
  using _control_source_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _control_source_type control_source;
  using _event_semantics_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _event_semantics_type event_semantics;
  using _requested_known_type =
    bool;
  _requested_known_type requested_known;
  using _requested_n_type =
    std::array<double, 2>;
  _requested_n_type requested_n;
  using _final_n_type =
    std::array<double, 2>;
  _final_n_type final_n;
  using _left_publish_success_type =
    bool;
  _left_publish_success_type left_publish_success;
  using _right_publish_success_type =
    bool;
  _right_publish_success_type right_publish_success;
  using _left_publish_start_steady_ns_type =
    int64_t;
  _left_publish_start_steady_ns_type left_publish_start_steady_ns;
  using _left_publish_end_steady_ns_type =
    int64_t;
  _left_publish_end_steady_ns_type left_publish_end_steady_ns;
  using _right_publish_start_steady_ns_type =
    int64_t;
  _right_publish_start_steady_ns_type right_publish_start_steady_ns;
  using _right_publish_end_steady_ns_type =
    int64_t;
  _right_publish_end_steady_ns_type right_publish_end_steady_ns;
  using _left_sim_time_ns_type =
    int64_t;
  _left_sim_time_ns_type left_sim_time_ns;
  using _right_sim_time_ns_type =
    int64_t;
  _right_sim_time_ns_type right_sim_time_ns;
  using _left_clock_epoch_type =
    uint64_t;
  _left_clock_epoch_type left_clock_epoch;
  using _right_clock_epoch_type =
    uint64_t;
  _right_clock_epoch_type right_clock_epoch;
  using _left_clock_age_ns_type =
    int64_t;
  _left_clock_age_ns_type left_clock_age_ns;
  using _right_clock_age_ns_type =
    int64_t;
  _right_clock_age_ns_type right_clock_age_ns;
  using _map_scale_type =
    double;
  _map_scale_type map_scale;
  using _lower_n_type =
    double;
  _lower_n_type lower_n;
  using _upper_n_type =
    double;
  _upper_n_type upper_n;
  using _previous_anchor_known_type =
    bool;
  _previous_anchor_known_type previous_anchor_known;
  using _previous_final_n_type =
    std::array<double, 2>;
  _previous_final_n_type previous_final_n;
  using _plant_acceptance_observed_type =
    bool;
  _plant_acceptance_observed_type plant_acceptance_observed;
  using _force_measured_type =
    bool;
  _force_measured_type force_measured;
  using _execution_atomicity_proven_type =
    bool;
  _execution_atomicity_proven_type execution_atomicity_proven;
  using _publish_error_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _publish_error_type publish_error;

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
  Type & set__cycle_sequence(
    const uint64_t & _arg)
  {
    this->cycle_sequence = _arg;
    return *this;
  }
  Type & set__control_source(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->control_source = _arg;
    return *this;
  }
  Type & set__event_semantics(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->event_semantics = _arg;
    return *this;
  }
  Type & set__requested_known(
    const bool & _arg)
  {
    this->requested_known = _arg;
    return *this;
  }
  Type & set__requested_n(
    const std::array<double, 2> & _arg)
  {
    this->requested_n = _arg;
    return *this;
  }
  Type & set__final_n(
    const std::array<double, 2> & _arg)
  {
    this->final_n = _arg;
    return *this;
  }
  Type & set__left_publish_success(
    const bool & _arg)
  {
    this->left_publish_success = _arg;
    return *this;
  }
  Type & set__right_publish_success(
    const bool & _arg)
  {
    this->right_publish_success = _arg;
    return *this;
  }
  Type & set__left_publish_start_steady_ns(
    const int64_t & _arg)
  {
    this->left_publish_start_steady_ns = _arg;
    return *this;
  }
  Type & set__left_publish_end_steady_ns(
    const int64_t & _arg)
  {
    this->left_publish_end_steady_ns = _arg;
    return *this;
  }
  Type & set__right_publish_start_steady_ns(
    const int64_t & _arg)
  {
    this->right_publish_start_steady_ns = _arg;
    return *this;
  }
  Type & set__right_publish_end_steady_ns(
    const int64_t & _arg)
  {
    this->right_publish_end_steady_ns = _arg;
    return *this;
  }
  Type & set__left_sim_time_ns(
    const int64_t & _arg)
  {
    this->left_sim_time_ns = _arg;
    return *this;
  }
  Type & set__right_sim_time_ns(
    const int64_t & _arg)
  {
    this->right_sim_time_ns = _arg;
    return *this;
  }
  Type & set__left_clock_epoch(
    const uint64_t & _arg)
  {
    this->left_clock_epoch = _arg;
    return *this;
  }
  Type & set__right_clock_epoch(
    const uint64_t & _arg)
  {
    this->right_clock_epoch = _arg;
    return *this;
  }
  Type & set__left_clock_age_ns(
    const int64_t & _arg)
  {
    this->left_clock_age_ns = _arg;
    return *this;
  }
  Type & set__right_clock_age_ns(
    const int64_t & _arg)
  {
    this->right_clock_age_ns = _arg;
    return *this;
  }
  Type & set__map_scale(
    const double & _arg)
  {
    this->map_scale = _arg;
    return *this;
  }
  Type & set__lower_n(
    const double & _arg)
  {
    this->lower_n = _arg;
    return *this;
  }
  Type & set__upper_n(
    const double & _arg)
  {
    this->upper_n = _arg;
    return *this;
  }
  Type & set__previous_anchor_known(
    const bool & _arg)
  {
    this->previous_anchor_known = _arg;
    return *this;
  }
  Type & set__previous_final_n(
    const std::array<double, 2> & _arg)
  {
    this->previous_final_n = _arg;
    return *this;
  }
  Type & set__plant_acceptance_observed(
    const bool & _arg)
  {
    this->plant_acceptance_observed = _arg;
    return *this;
  }
  Type & set__force_measured(
    const bool & _arg)
  {
    this->force_measured = _arg;
    return *this;
  }
  Type & set__execution_atomicity_proven(
    const bool & _arg)
  {
    this->execution_atomicity_proven = _arg;
    return *this;
  }
  Type & set__publish_error(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->publish_error = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    usv_research_interfaces::msg::AppliedControl_<ContainerAllocator> *;
  using ConstRawPtr =
    const usv_research_interfaces::msg::AppliedControl_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::AppliedControl_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::AppliedControl_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::AppliedControl_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::AppliedControl_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::AppliedControl_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::AppliedControl_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::AppliedControl_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::AppliedControl_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__usv_research_interfaces__msg__AppliedControl
    std::shared_ptr<usv_research_interfaces::msg::AppliedControl_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__usv_research_interfaces__msg__AppliedControl
    std::shared_ptr<usv_research_interfaces::msg::AppliedControl_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const AppliedControl_ & other) const
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
    if (this->cycle_sequence != other.cycle_sequence) {
      return false;
    }
    if (this->control_source != other.control_source) {
      return false;
    }
    if (this->event_semantics != other.event_semantics) {
      return false;
    }
    if (this->requested_known != other.requested_known) {
      return false;
    }
    if (this->requested_n != other.requested_n) {
      return false;
    }
    if (this->final_n != other.final_n) {
      return false;
    }
    if (this->left_publish_success != other.left_publish_success) {
      return false;
    }
    if (this->right_publish_success != other.right_publish_success) {
      return false;
    }
    if (this->left_publish_start_steady_ns != other.left_publish_start_steady_ns) {
      return false;
    }
    if (this->left_publish_end_steady_ns != other.left_publish_end_steady_ns) {
      return false;
    }
    if (this->right_publish_start_steady_ns != other.right_publish_start_steady_ns) {
      return false;
    }
    if (this->right_publish_end_steady_ns != other.right_publish_end_steady_ns) {
      return false;
    }
    if (this->left_sim_time_ns != other.left_sim_time_ns) {
      return false;
    }
    if (this->right_sim_time_ns != other.right_sim_time_ns) {
      return false;
    }
    if (this->left_clock_epoch != other.left_clock_epoch) {
      return false;
    }
    if (this->right_clock_epoch != other.right_clock_epoch) {
      return false;
    }
    if (this->left_clock_age_ns != other.left_clock_age_ns) {
      return false;
    }
    if (this->right_clock_age_ns != other.right_clock_age_ns) {
      return false;
    }
    if (this->map_scale != other.map_scale) {
      return false;
    }
    if (this->lower_n != other.lower_n) {
      return false;
    }
    if (this->upper_n != other.upper_n) {
      return false;
    }
    if (this->previous_anchor_known != other.previous_anchor_known) {
      return false;
    }
    if (this->previous_final_n != other.previous_final_n) {
      return false;
    }
    if (this->plant_acceptance_observed != other.plant_acceptance_observed) {
      return false;
    }
    if (this->force_measured != other.force_measured) {
      return false;
    }
    if (this->execution_atomicity_proven != other.execution_atomicity_proven) {
      return false;
    }
    if (this->publish_error != other.publish_error) {
      return false;
    }
    return true;
  }
  bool operator!=(const AppliedControl_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct AppliedControl_

// alias to use template instance with default allocator
using AppliedControl =
  usv_research_interfaces::msg::AppliedControl_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__APPLIED_CONTROL__STRUCT_HPP_
