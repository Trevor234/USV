// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from usv_research_interfaces:msg/WorkerCapability.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/worker_capability.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__WORKER_CAPABILITY__STRUCT_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__WORKER_CAPABILITY__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


#ifndef _WIN32
# define DEPRECATED__usv_research_interfaces__msg__WorkerCapability __attribute__((deprecated))
#else
# define DEPRECATED__usv_research_interfaces__msg__WorkerCapability __declspec(deprecated)
#endif

namespace usv_research_interfaces
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct WorkerCapability_
{
  using Type = WorkerCapability_<ContainerAllocator>;

  explicit WorkerCapability_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->schema_version = "";
      this->run_id = "";
      this->boot_id = "";
      this->contract_hash = "";
      this->nominal_hash = "";
      this->worker_instance = "";
      this->clock_name = "";
      this->backend = "";
      this->matrix_layout = "";
      this->horizon_steps = 0ul;
      this->prediction_dt = 0.0;
      this->pid = 0ll;
      this->startup_ns = 0ll;
      this->completed_jobs = 0ull;
      this->active_job = 0ull;
      this->pending_count = 0ul;
      this->fault_injection_enabled = false;
      this->fatal = false;
      this->reason = "";
    }
  }

  explicit WorkerCapability_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : schema_version(_alloc),
    run_id(_alloc),
    boot_id(_alloc),
    contract_hash(_alloc),
    nominal_hash(_alloc),
    worker_instance(_alloc),
    clock_name(_alloc),
    backend(_alloc),
    matrix_layout(_alloc),
    reason(_alloc)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->schema_version = "";
      this->run_id = "";
      this->boot_id = "";
      this->contract_hash = "";
      this->nominal_hash = "";
      this->worker_instance = "";
      this->clock_name = "";
      this->backend = "";
      this->matrix_layout = "";
      this->horizon_steps = 0ul;
      this->prediction_dt = 0.0;
      this->pid = 0ll;
      this->startup_ns = 0ll;
      this->completed_jobs = 0ull;
      this->active_job = 0ull;
      this->pending_count = 0ul;
      this->fault_injection_enabled = false;
      this->fatal = false;
      this->reason = "";
    }
  }

  // field types and members
  using _schema_version_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _schema_version_type schema_version;
  using _run_id_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _run_id_type run_id;
  using _boot_id_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _boot_id_type boot_id;
  using _contract_hash_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _contract_hash_type contract_hash;
  using _nominal_hash_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _nominal_hash_type nominal_hash;
  using _worker_instance_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _worker_instance_type worker_instance;
  using _clock_name_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _clock_name_type clock_name;
  using _backend_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _backend_type backend;
  using _matrix_layout_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _matrix_layout_type matrix_layout;
  using _horizon_steps_type =
    uint32_t;
  _horizon_steps_type horizon_steps;
  using _prediction_dt_type =
    double;
  _prediction_dt_type prediction_dt;
  using _pid_type =
    int64_t;
  _pid_type pid;
  using _startup_ns_type =
    int64_t;
  _startup_ns_type startup_ns;
  using _completed_jobs_type =
    uint64_t;
  _completed_jobs_type completed_jobs;
  using _active_job_type =
    uint64_t;
  _active_job_type active_job;
  using _pending_count_type =
    uint32_t;
  _pending_count_type pending_count;
  using _fault_injection_enabled_type =
    bool;
  _fault_injection_enabled_type fault_injection_enabled;
  using _fatal_type =
    bool;
  _fatal_type fatal;
  using _reason_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _reason_type reason;

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
  Type & set__boot_id(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->boot_id = _arg;
    return *this;
  }
  Type & set__contract_hash(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->contract_hash = _arg;
    return *this;
  }
  Type & set__nominal_hash(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->nominal_hash = _arg;
    return *this;
  }
  Type & set__worker_instance(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->worker_instance = _arg;
    return *this;
  }
  Type & set__clock_name(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->clock_name = _arg;
    return *this;
  }
  Type & set__backend(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->backend = _arg;
    return *this;
  }
  Type & set__matrix_layout(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->matrix_layout = _arg;
    return *this;
  }
  Type & set__horizon_steps(
    const uint32_t & _arg)
  {
    this->horizon_steps = _arg;
    return *this;
  }
  Type & set__prediction_dt(
    const double & _arg)
  {
    this->prediction_dt = _arg;
    return *this;
  }
  Type & set__pid(
    const int64_t & _arg)
  {
    this->pid = _arg;
    return *this;
  }
  Type & set__startup_ns(
    const int64_t & _arg)
  {
    this->startup_ns = _arg;
    return *this;
  }
  Type & set__completed_jobs(
    const uint64_t & _arg)
  {
    this->completed_jobs = _arg;
    return *this;
  }
  Type & set__active_job(
    const uint64_t & _arg)
  {
    this->active_job = _arg;
    return *this;
  }
  Type & set__pending_count(
    const uint32_t & _arg)
  {
    this->pending_count = _arg;
    return *this;
  }
  Type & set__fault_injection_enabled(
    const bool & _arg)
  {
    this->fault_injection_enabled = _arg;
    return *this;
  }
  Type & set__fatal(
    const bool & _arg)
  {
    this->fatal = _arg;
    return *this;
  }
  Type & set__reason(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->reason = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    usv_research_interfaces::msg::WorkerCapability_<ContainerAllocator> *;
  using ConstRawPtr =
    const usv_research_interfaces::msg::WorkerCapability_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::WorkerCapability_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::WorkerCapability_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::WorkerCapability_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::WorkerCapability_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::WorkerCapability_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::WorkerCapability_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::WorkerCapability_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::WorkerCapability_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__usv_research_interfaces__msg__WorkerCapability
    std::shared_ptr<usv_research_interfaces::msg::WorkerCapability_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__usv_research_interfaces__msg__WorkerCapability
    std::shared_ptr<usv_research_interfaces::msg::WorkerCapability_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const WorkerCapability_ & other) const
  {
    if (this->schema_version != other.schema_version) {
      return false;
    }
    if (this->run_id != other.run_id) {
      return false;
    }
    if (this->boot_id != other.boot_id) {
      return false;
    }
    if (this->contract_hash != other.contract_hash) {
      return false;
    }
    if (this->nominal_hash != other.nominal_hash) {
      return false;
    }
    if (this->worker_instance != other.worker_instance) {
      return false;
    }
    if (this->clock_name != other.clock_name) {
      return false;
    }
    if (this->backend != other.backend) {
      return false;
    }
    if (this->matrix_layout != other.matrix_layout) {
      return false;
    }
    if (this->horizon_steps != other.horizon_steps) {
      return false;
    }
    if (this->prediction_dt != other.prediction_dt) {
      return false;
    }
    if (this->pid != other.pid) {
      return false;
    }
    if (this->startup_ns != other.startup_ns) {
      return false;
    }
    if (this->completed_jobs != other.completed_jobs) {
      return false;
    }
    if (this->active_job != other.active_job) {
      return false;
    }
    if (this->pending_count != other.pending_count) {
      return false;
    }
    if (this->fault_injection_enabled != other.fault_injection_enabled) {
      return false;
    }
    if (this->fatal != other.fatal) {
      return false;
    }
    if (this->reason != other.reason) {
      return false;
    }
    return true;
  }
  bool operator!=(const WorkerCapability_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct WorkerCapability_

// alias to use template instance with default allocator
using WorkerCapability =
  usv_research_interfaces::msg::WorkerCapability_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__WORKER_CAPABILITY__STRUCT_HPP_
