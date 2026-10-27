// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from usv_research_interfaces:msg/SolveJob.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/solve_job.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__STRUCT_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


#ifndef _WIN32
# define DEPRECATED__usv_research_interfaces__msg__SolveJob __attribute__((deprecated))
#else
# define DEPRECATED__usv_research_interfaces__msg__SolveJob __declspec(deprecated)
#endif

namespace usv_research_interfaces
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct SolveJob_
{
  using Type = SolveJob_<ContainerAllocator>;

  explicit SolveJob_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
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
      this->job_id = 0ull;
      this->target_tick = 0ull;
      this->task_generation = 0ull;
      this->model_generation = 0ull;
      this->config_generation = 0ull;
      this->schedule_generation = 0ull;
      this->clock_epoch = 0ull;
      this->tick_origin_steady_ns = 0ll;
      this->freeze_steady_ns = 0ll;
      this->deadline_steady_ns = 0ll;
      this->target_steady_ns = 0ll;
      this->target_sim_ns = 0ll;
      this->odom_stamp_ns = 0ll;
      this->imu_stamp_ns = 0ll;
      this->odom_receive_ns = 0ll;
      this->imu_receive_ns = 0ll;
      this->odom_sequence = 0ull;
      this->imu_sequence = 0ull;
      this->r_from_imu = false;
      this->horizon_steps = 0ul;
      this->prediction_dt = 0.0;
      std::fill<typename std::array<double, 6>::iterator, double>(this->frozen_state.begin(), this->frozen_state.end(), 0.0);
      std::fill<typename std::array<double, 6>::iterator, double>(this->target_state.begin(), this->target_state.end(), 0.0);
      std::fill<typename std::array<double, 126>::iterator, double>(this->reference.begin(), this->reference.end(), 0.0);
      std::fill<typename std::array<double, 2>::iterator, double>(this->anchor_n.begin(), this->anchor_n.end(), 0.0);
      std::fill<typename std::array<uint64_t, 2>::iterator, uint64_t>(this->anchor_sequence.begin(), this->anchor_sequence.end(), 0ull);
      std::fill<typename std::array<int64_t, 2>::iterator, int64_t>(this->anchor_publish_ns.begin(), this->anchor_publish_ns.end(), 0ll);
      std::fill<typename std::array<bool, 2>::iterator, bool>(this->anchor_known.begin(), this->anchor_known.end(), false);
      this->reset_warmstart = false;
      this->frozen_clock_sim_ns = 0ll;
      this->frozen_clock_receive_ns = 0ll;
      this->assumed_rtf = 0.0;
      this->anchor_source = "";
      this->anchor_producer = "";
      this->anchor_run_id = "";
    }
  }

  explicit SolveJob_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : schema_version(_alloc),
    run_id(_alloc),
    boot_id(_alloc),
    contract_hash(_alloc),
    nominal_hash(_alloc),
    worker_instance(_alloc),
    frozen_state(_alloc),
    target_state(_alloc),
    reference(_alloc),
    anchor_n(_alloc),
    anchor_sequence(_alloc),
    anchor_publish_ns(_alloc),
    anchor_known(_alloc),
    anchor_source(_alloc),
    anchor_producer(_alloc),
    anchor_run_id(_alloc)
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
      this->job_id = 0ull;
      this->target_tick = 0ull;
      this->task_generation = 0ull;
      this->model_generation = 0ull;
      this->config_generation = 0ull;
      this->schedule_generation = 0ull;
      this->clock_epoch = 0ull;
      this->tick_origin_steady_ns = 0ll;
      this->freeze_steady_ns = 0ll;
      this->deadline_steady_ns = 0ll;
      this->target_steady_ns = 0ll;
      this->target_sim_ns = 0ll;
      this->odom_stamp_ns = 0ll;
      this->imu_stamp_ns = 0ll;
      this->odom_receive_ns = 0ll;
      this->imu_receive_ns = 0ll;
      this->odom_sequence = 0ull;
      this->imu_sequence = 0ull;
      this->r_from_imu = false;
      this->horizon_steps = 0ul;
      this->prediction_dt = 0.0;
      std::fill<typename std::array<double, 6>::iterator, double>(this->frozen_state.begin(), this->frozen_state.end(), 0.0);
      std::fill<typename std::array<double, 6>::iterator, double>(this->target_state.begin(), this->target_state.end(), 0.0);
      std::fill<typename std::array<double, 126>::iterator, double>(this->reference.begin(), this->reference.end(), 0.0);
      std::fill<typename std::array<double, 2>::iterator, double>(this->anchor_n.begin(), this->anchor_n.end(), 0.0);
      std::fill<typename std::array<uint64_t, 2>::iterator, uint64_t>(this->anchor_sequence.begin(), this->anchor_sequence.end(), 0ull);
      std::fill<typename std::array<int64_t, 2>::iterator, int64_t>(this->anchor_publish_ns.begin(), this->anchor_publish_ns.end(), 0ll);
      std::fill<typename std::array<bool, 2>::iterator, bool>(this->anchor_known.begin(), this->anchor_known.end(), false);
      this->reset_warmstart = false;
      this->frozen_clock_sim_ns = 0ll;
      this->frozen_clock_receive_ns = 0ll;
      this->assumed_rtf = 0.0;
      this->anchor_source = "";
      this->anchor_producer = "";
      this->anchor_run_id = "";
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
  using _job_id_type =
    uint64_t;
  _job_id_type job_id;
  using _target_tick_type =
    uint64_t;
  _target_tick_type target_tick;
  using _task_generation_type =
    uint64_t;
  _task_generation_type task_generation;
  using _model_generation_type =
    uint64_t;
  _model_generation_type model_generation;
  using _config_generation_type =
    uint64_t;
  _config_generation_type config_generation;
  using _schedule_generation_type =
    uint64_t;
  _schedule_generation_type schedule_generation;
  using _clock_epoch_type =
    uint64_t;
  _clock_epoch_type clock_epoch;
  using _tick_origin_steady_ns_type =
    int64_t;
  _tick_origin_steady_ns_type tick_origin_steady_ns;
  using _freeze_steady_ns_type =
    int64_t;
  _freeze_steady_ns_type freeze_steady_ns;
  using _deadline_steady_ns_type =
    int64_t;
  _deadline_steady_ns_type deadline_steady_ns;
  using _target_steady_ns_type =
    int64_t;
  _target_steady_ns_type target_steady_ns;
  using _target_sim_ns_type =
    int64_t;
  _target_sim_ns_type target_sim_ns;
  using _odom_stamp_ns_type =
    int64_t;
  _odom_stamp_ns_type odom_stamp_ns;
  using _imu_stamp_ns_type =
    int64_t;
  _imu_stamp_ns_type imu_stamp_ns;
  using _odom_receive_ns_type =
    int64_t;
  _odom_receive_ns_type odom_receive_ns;
  using _imu_receive_ns_type =
    int64_t;
  _imu_receive_ns_type imu_receive_ns;
  using _odom_sequence_type =
    uint64_t;
  _odom_sequence_type odom_sequence;
  using _imu_sequence_type =
    uint64_t;
  _imu_sequence_type imu_sequence;
  using _r_from_imu_type =
    bool;
  _r_from_imu_type r_from_imu;
  using _horizon_steps_type =
    uint32_t;
  _horizon_steps_type horizon_steps;
  using _prediction_dt_type =
    double;
  _prediction_dt_type prediction_dt;
  using _frozen_state_type =
    std::array<double, 6>;
  _frozen_state_type frozen_state;
  using _target_state_type =
    std::array<double, 6>;
  _target_state_type target_state;
  using _reference_type =
    std::array<double, 126>;
  _reference_type reference;
  using _anchor_n_type =
    std::array<double, 2>;
  _anchor_n_type anchor_n;
  using _anchor_sequence_type =
    std::array<uint64_t, 2>;
  _anchor_sequence_type anchor_sequence;
  using _anchor_publish_ns_type =
    std::array<int64_t, 2>;
  _anchor_publish_ns_type anchor_publish_ns;
  using _anchor_known_type =
    std::array<bool, 2>;
  _anchor_known_type anchor_known;
  using _reset_warmstart_type =
    bool;
  _reset_warmstart_type reset_warmstart;
  using _frozen_clock_sim_ns_type =
    int64_t;
  _frozen_clock_sim_ns_type frozen_clock_sim_ns;
  using _frozen_clock_receive_ns_type =
    int64_t;
  _frozen_clock_receive_ns_type frozen_clock_receive_ns;
  using _assumed_rtf_type =
    double;
  _assumed_rtf_type assumed_rtf;
  using _anchor_source_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _anchor_source_type anchor_source;
  using _anchor_producer_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _anchor_producer_type anchor_producer;
  using _anchor_run_id_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _anchor_run_id_type anchor_run_id;
  using _history_sim_ns_type =
    rosidl_runtime_cpp::BoundedVector<int64_t, 256, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<int64_t>>;
  _history_sim_ns_type history_sim_ns;
  using _history_channel_type =
    rosidl_runtime_cpp::BoundedVector<uint8_t, 256, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<uint8_t>>;
  _history_channel_type history_channel;
  using _history_n_type =
    rosidl_runtime_cpp::BoundedVector<double, 256, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<double>>;
  _history_n_type history_n;

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
  Type & set__job_id(
    const uint64_t & _arg)
  {
    this->job_id = _arg;
    return *this;
  }
  Type & set__target_tick(
    const uint64_t & _arg)
  {
    this->target_tick = _arg;
    return *this;
  }
  Type & set__task_generation(
    const uint64_t & _arg)
  {
    this->task_generation = _arg;
    return *this;
  }
  Type & set__model_generation(
    const uint64_t & _arg)
  {
    this->model_generation = _arg;
    return *this;
  }
  Type & set__config_generation(
    const uint64_t & _arg)
  {
    this->config_generation = _arg;
    return *this;
  }
  Type & set__schedule_generation(
    const uint64_t & _arg)
  {
    this->schedule_generation = _arg;
    return *this;
  }
  Type & set__clock_epoch(
    const uint64_t & _arg)
  {
    this->clock_epoch = _arg;
    return *this;
  }
  Type & set__tick_origin_steady_ns(
    const int64_t & _arg)
  {
    this->tick_origin_steady_ns = _arg;
    return *this;
  }
  Type & set__freeze_steady_ns(
    const int64_t & _arg)
  {
    this->freeze_steady_ns = _arg;
    return *this;
  }
  Type & set__deadline_steady_ns(
    const int64_t & _arg)
  {
    this->deadline_steady_ns = _arg;
    return *this;
  }
  Type & set__target_steady_ns(
    const int64_t & _arg)
  {
    this->target_steady_ns = _arg;
    return *this;
  }
  Type & set__target_sim_ns(
    const int64_t & _arg)
  {
    this->target_sim_ns = _arg;
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
  Type & set__odom_receive_ns(
    const int64_t & _arg)
  {
    this->odom_receive_ns = _arg;
    return *this;
  }
  Type & set__imu_receive_ns(
    const int64_t & _arg)
  {
    this->imu_receive_ns = _arg;
    return *this;
  }
  Type & set__odom_sequence(
    const uint64_t & _arg)
  {
    this->odom_sequence = _arg;
    return *this;
  }
  Type & set__imu_sequence(
    const uint64_t & _arg)
  {
    this->imu_sequence = _arg;
    return *this;
  }
  Type & set__r_from_imu(
    const bool & _arg)
  {
    this->r_from_imu = _arg;
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
  Type & set__frozen_state(
    const std::array<double, 6> & _arg)
  {
    this->frozen_state = _arg;
    return *this;
  }
  Type & set__target_state(
    const std::array<double, 6> & _arg)
  {
    this->target_state = _arg;
    return *this;
  }
  Type & set__reference(
    const std::array<double, 126> & _arg)
  {
    this->reference = _arg;
    return *this;
  }
  Type & set__anchor_n(
    const std::array<double, 2> & _arg)
  {
    this->anchor_n = _arg;
    return *this;
  }
  Type & set__anchor_sequence(
    const std::array<uint64_t, 2> & _arg)
  {
    this->anchor_sequence = _arg;
    return *this;
  }
  Type & set__anchor_publish_ns(
    const std::array<int64_t, 2> & _arg)
  {
    this->anchor_publish_ns = _arg;
    return *this;
  }
  Type & set__anchor_known(
    const std::array<bool, 2> & _arg)
  {
    this->anchor_known = _arg;
    return *this;
  }
  Type & set__reset_warmstart(
    const bool & _arg)
  {
    this->reset_warmstart = _arg;
    return *this;
  }
  Type & set__frozen_clock_sim_ns(
    const int64_t & _arg)
  {
    this->frozen_clock_sim_ns = _arg;
    return *this;
  }
  Type & set__frozen_clock_receive_ns(
    const int64_t & _arg)
  {
    this->frozen_clock_receive_ns = _arg;
    return *this;
  }
  Type & set__assumed_rtf(
    const double & _arg)
  {
    this->assumed_rtf = _arg;
    return *this;
  }
  Type & set__anchor_source(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->anchor_source = _arg;
    return *this;
  }
  Type & set__anchor_producer(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->anchor_producer = _arg;
    return *this;
  }
  Type & set__anchor_run_id(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->anchor_run_id = _arg;
    return *this;
  }
  Type & set__history_sim_ns(
    const rosidl_runtime_cpp::BoundedVector<int64_t, 256, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<int64_t>> & _arg)
  {
    this->history_sim_ns = _arg;
    return *this;
  }
  Type & set__history_channel(
    const rosidl_runtime_cpp::BoundedVector<uint8_t, 256, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<uint8_t>> & _arg)
  {
    this->history_channel = _arg;
    return *this;
  }
  Type & set__history_n(
    const rosidl_runtime_cpp::BoundedVector<double, 256, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<double>> & _arg)
  {
    this->history_n = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    usv_research_interfaces::msg::SolveJob_<ContainerAllocator> *;
  using ConstRawPtr =
    const usv_research_interfaces::msg::SolveJob_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::SolveJob_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::SolveJob_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::SolveJob_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::SolveJob_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::SolveJob_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::SolveJob_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::SolveJob_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::SolveJob_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__usv_research_interfaces__msg__SolveJob
    std::shared_ptr<usv_research_interfaces::msg::SolveJob_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__usv_research_interfaces__msg__SolveJob
    std::shared_ptr<usv_research_interfaces::msg::SolveJob_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const SolveJob_ & other) const
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
    if (this->job_id != other.job_id) {
      return false;
    }
    if (this->target_tick != other.target_tick) {
      return false;
    }
    if (this->task_generation != other.task_generation) {
      return false;
    }
    if (this->model_generation != other.model_generation) {
      return false;
    }
    if (this->config_generation != other.config_generation) {
      return false;
    }
    if (this->schedule_generation != other.schedule_generation) {
      return false;
    }
    if (this->clock_epoch != other.clock_epoch) {
      return false;
    }
    if (this->tick_origin_steady_ns != other.tick_origin_steady_ns) {
      return false;
    }
    if (this->freeze_steady_ns != other.freeze_steady_ns) {
      return false;
    }
    if (this->deadline_steady_ns != other.deadline_steady_ns) {
      return false;
    }
    if (this->target_steady_ns != other.target_steady_ns) {
      return false;
    }
    if (this->target_sim_ns != other.target_sim_ns) {
      return false;
    }
    if (this->odom_stamp_ns != other.odom_stamp_ns) {
      return false;
    }
    if (this->imu_stamp_ns != other.imu_stamp_ns) {
      return false;
    }
    if (this->odom_receive_ns != other.odom_receive_ns) {
      return false;
    }
    if (this->imu_receive_ns != other.imu_receive_ns) {
      return false;
    }
    if (this->odom_sequence != other.odom_sequence) {
      return false;
    }
    if (this->imu_sequence != other.imu_sequence) {
      return false;
    }
    if (this->r_from_imu != other.r_from_imu) {
      return false;
    }
    if (this->horizon_steps != other.horizon_steps) {
      return false;
    }
    if (this->prediction_dt != other.prediction_dt) {
      return false;
    }
    if (this->frozen_state != other.frozen_state) {
      return false;
    }
    if (this->target_state != other.target_state) {
      return false;
    }
    if (this->reference != other.reference) {
      return false;
    }
    if (this->anchor_n != other.anchor_n) {
      return false;
    }
    if (this->anchor_sequence != other.anchor_sequence) {
      return false;
    }
    if (this->anchor_publish_ns != other.anchor_publish_ns) {
      return false;
    }
    if (this->anchor_known != other.anchor_known) {
      return false;
    }
    if (this->reset_warmstart != other.reset_warmstart) {
      return false;
    }
    if (this->frozen_clock_sim_ns != other.frozen_clock_sim_ns) {
      return false;
    }
    if (this->frozen_clock_receive_ns != other.frozen_clock_receive_ns) {
      return false;
    }
    if (this->assumed_rtf != other.assumed_rtf) {
      return false;
    }
    if (this->anchor_source != other.anchor_source) {
      return false;
    }
    if (this->anchor_producer != other.anchor_producer) {
      return false;
    }
    if (this->anchor_run_id != other.anchor_run_id) {
      return false;
    }
    if (this->history_sim_ns != other.history_sim_ns) {
      return false;
    }
    if (this->history_channel != other.history_channel) {
      return false;
    }
    if (this->history_n != other.history_n) {
      return false;
    }
    return true;
  }
  bool operator!=(const SolveJob_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct SolveJob_

// alias to use template instance with default allocator
using SolveJob =
  usv_research_interfaces::msg::SolveJob_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__STRUCT_HPP_
