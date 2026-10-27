// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from usv_research_interfaces:msg/ExecutionDecision.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/execution_decision.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__EXECUTION_DECISION__STRUCT_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__EXECUTION_DECISION__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


#ifndef _WIN32
# define DEPRECATED__usv_research_interfaces__msg__ExecutionDecision __attribute__((deprecated))
#else
# define DEPRECATED__usv_research_interfaces__msg__ExecutionDecision __declspec(deprecated)
#endif

namespace usv_research_interfaces
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct ExecutionDecision_
{
  using Type = ExecutionDecision_<ContainerAllocator>;

  explicit ExecutionDecision_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->schema_version = "";
      this->run_id = "";
      this->boot_id = "";
      this->contract_hash = "";
      this->worker_instance = "";
      this->mode = "";
      this->sequence = 0ull;
      this->tick = 0ull;
      this->job_id = 0ull;
      this->task_generation = 0ull;
      this->model_generation = 0ull;
      this->config_generation = 0ull;
      this->schedule_generation = 0ull;
      this->clock_epoch = 0ull;
      this->tick_planned_ns = 0ll;
      this->tick_start_ns = 0ll;
      this->cutoff_commit_ns = 0ll;
      this->candidate_ready_commit_ns = 0ll;
      this->activation_commit_ns = 0ll;
      this->tick_end_ns = 0ll;
      this->skipped_ticks = 0ull;
      this->candidate_accepted = false;
      this->diagnostic_only = false;
      this->reason = "";
      this->control_source = "";
      std::fill<typename std::array<double, 6>::iterator, double>(this->target_state.begin(), this->target_state.end(), 0.0);
      std::fill<typename std::array<double, 6>::iterator, double>(this->activation_state.begin(), this->activation_state.end(), 0.0);
      std::fill<typename std::array<double, 6>::iterator, double>(this->state_error.begin(), this->state_error.end(), 0.0);
      std::fill<typename std::array<double, 2>::iterator, double>(this->requested_n.begin(), this->requested_n.end(), 0.0);
      std::fill<typename std::array<double, 2>::iterator, double>(this->final_n.begin(), this->final_n.end(), 0.0);
      std::fill<typename std::array<bool, 2>::iterator, bool>(this->publish_success.begin(), this->publish_success.end(), false);
      std::fill<typename std::array<int64_t, 2>::iterator, int64_t>(this->publish_start_ns.begin(), this->publish_start_ns.end(), 0ll);
      std::fill<typename std::array<int64_t, 2>::iterator, int64_t>(this->publish_end_ns.begin(), this->publish_end_ns.end(), 0ll);
      std::fill<typename std::array<bool, 2>::iterator, bool>(this->anchor_known.begin(), this->anchor_known.end(), false);
      std::fill<typename std::array<uint64_t, 2>::iterator, uint64_t>(this->anchor_sequence.begin(), this->anchor_sequence.end(), 0ull);
      std::fill<typename std::array<double, 2>::iterator, double>(this->previous_n.begin(), this->previous_n.end(), 0.0);
      std::fill<typename std::array<int64_t, 2>::iterator, int64_t>(this->previous_publish_ns.begin(), this->previous_publish_ns.end(), 0ll);
      this->odom_age_ns = 0ll;
      this->imu_age_ns = 0ll;
      this->clock_age_ns = 0ll;
      this->normal_contract_complete = false;
      this->rho_available = false;
      this->plant_acceptance_observed = false;
      std::fill<typename std::array<bool, 2>::iterator, bool>(this->previous_anchor_known.begin(), this->previous_anchor_known.end(), false);
      std::fill<typename std::array<int64_t, 2>::iterator, int64_t>(this->publish_sim_ns.begin(), this->publish_sim_ns.end(), 0ll);
      std::fill<typename std::array<uint64_t, 2>::iterator, uint64_t>(this->publish_epoch.begin(), this->publish_epoch.end(), 0ull);
      std::fill<typename std::array<int64_t, 2>::iterator, int64_t>(this->publish_clock_age_ns.begin(), this->publish_clock_age_ns.end(), 0ll);
      this->activation_clock_sim_ns = 0ll;
      this->activation_clock_receive_ns = 0ll;
      this->activation_rtf = 0.0;
      this->activation_odom_stamp_ns = 0ll;
      this->activation_odom_receive_ns = 0ll;
      this->activation_odom_sequence = 0ull;
      this->activation_imu_stamp_ns = 0ll;
      this->activation_imu_receive_ns = 0ll;
      this->activation_imu_sequence = 0ull;
      this->activation_r_from_imu = false;
    }
  }

  explicit ExecutionDecision_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : schema_version(_alloc),
    run_id(_alloc),
    boot_id(_alloc),
    contract_hash(_alloc),
    worker_instance(_alloc),
    mode(_alloc),
    reason(_alloc),
    control_source(_alloc),
    target_state(_alloc),
    activation_state(_alloc),
    state_error(_alloc),
    requested_n(_alloc),
    final_n(_alloc),
    publish_success(_alloc),
    publish_start_ns(_alloc),
    publish_end_ns(_alloc),
    anchor_known(_alloc),
    anchor_sequence(_alloc),
    previous_n(_alloc),
    previous_publish_ns(_alloc),
    previous_anchor_known(_alloc),
    publish_sim_ns(_alloc),
    publish_epoch(_alloc),
    publish_clock_age_ns(_alloc)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->schema_version = "";
      this->run_id = "";
      this->boot_id = "";
      this->contract_hash = "";
      this->worker_instance = "";
      this->mode = "";
      this->sequence = 0ull;
      this->tick = 0ull;
      this->job_id = 0ull;
      this->task_generation = 0ull;
      this->model_generation = 0ull;
      this->config_generation = 0ull;
      this->schedule_generation = 0ull;
      this->clock_epoch = 0ull;
      this->tick_planned_ns = 0ll;
      this->tick_start_ns = 0ll;
      this->cutoff_commit_ns = 0ll;
      this->candidate_ready_commit_ns = 0ll;
      this->activation_commit_ns = 0ll;
      this->tick_end_ns = 0ll;
      this->skipped_ticks = 0ull;
      this->candidate_accepted = false;
      this->diagnostic_only = false;
      this->reason = "";
      this->control_source = "";
      std::fill<typename std::array<double, 6>::iterator, double>(this->target_state.begin(), this->target_state.end(), 0.0);
      std::fill<typename std::array<double, 6>::iterator, double>(this->activation_state.begin(), this->activation_state.end(), 0.0);
      std::fill<typename std::array<double, 6>::iterator, double>(this->state_error.begin(), this->state_error.end(), 0.0);
      std::fill<typename std::array<double, 2>::iterator, double>(this->requested_n.begin(), this->requested_n.end(), 0.0);
      std::fill<typename std::array<double, 2>::iterator, double>(this->final_n.begin(), this->final_n.end(), 0.0);
      std::fill<typename std::array<bool, 2>::iterator, bool>(this->publish_success.begin(), this->publish_success.end(), false);
      std::fill<typename std::array<int64_t, 2>::iterator, int64_t>(this->publish_start_ns.begin(), this->publish_start_ns.end(), 0ll);
      std::fill<typename std::array<int64_t, 2>::iterator, int64_t>(this->publish_end_ns.begin(), this->publish_end_ns.end(), 0ll);
      std::fill<typename std::array<bool, 2>::iterator, bool>(this->anchor_known.begin(), this->anchor_known.end(), false);
      std::fill<typename std::array<uint64_t, 2>::iterator, uint64_t>(this->anchor_sequence.begin(), this->anchor_sequence.end(), 0ull);
      std::fill<typename std::array<double, 2>::iterator, double>(this->previous_n.begin(), this->previous_n.end(), 0.0);
      std::fill<typename std::array<int64_t, 2>::iterator, int64_t>(this->previous_publish_ns.begin(), this->previous_publish_ns.end(), 0ll);
      this->odom_age_ns = 0ll;
      this->imu_age_ns = 0ll;
      this->clock_age_ns = 0ll;
      this->normal_contract_complete = false;
      this->rho_available = false;
      this->plant_acceptance_observed = false;
      std::fill<typename std::array<bool, 2>::iterator, bool>(this->previous_anchor_known.begin(), this->previous_anchor_known.end(), false);
      std::fill<typename std::array<int64_t, 2>::iterator, int64_t>(this->publish_sim_ns.begin(), this->publish_sim_ns.end(), 0ll);
      std::fill<typename std::array<uint64_t, 2>::iterator, uint64_t>(this->publish_epoch.begin(), this->publish_epoch.end(), 0ull);
      std::fill<typename std::array<int64_t, 2>::iterator, int64_t>(this->publish_clock_age_ns.begin(), this->publish_clock_age_ns.end(), 0ll);
      this->activation_clock_sim_ns = 0ll;
      this->activation_clock_receive_ns = 0ll;
      this->activation_rtf = 0.0;
      this->activation_odom_stamp_ns = 0ll;
      this->activation_odom_receive_ns = 0ll;
      this->activation_odom_sequence = 0ull;
      this->activation_imu_stamp_ns = 0ll;
      this->activation_imu_receive_ns = 0ll;
      this->activation_imu_sequence = 0ull;
      this->activation_r_from_imu = false;
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
  using _worker_instance_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _worker_instance_type worker_instance;
  using _mode_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _mode_type mode;
  using _sequence_type =
    uint64_t;
  _sequence_type sequence;
  using _tick_type =
    uint64_t;
  _tick_type tick;
  using _job_id_type =
    uint64_t;
  _job_id_type job_id;
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
  using _tick_planned_ns_type =
    int64_t;
  _tick_planned_ns_type tick_planned_ns;
  using _tick_start_ns_type =
    int64_t;
  _tick_start_ns_type tick_start_ns;
  using _cutoff_commit_ns_type =
    int64_t;
  _cutoff_commit_ns_type cutoff_commit_ns;
  using _candidate_ready_commit_ns_type =
    int64_t;
  _candidate_ready_commit_ns_type candidate_ready_commit_ns;
  using _activation_commit_ns_type =
    int64_t;
  _activation_commit_ns_type activation_commit_ns;
  using _tick_end_ns_type =
    int64_t;
  _tick_end_ns_type tick_end_ns;
  using _skipped_ticks_type =
    uint64_t;
  _skipped_ticks_type skipped_ticks;
  using _candidate_accepted_type =
    bool;
  _candidate_accepted_type candidate_accepted;
  using _diagnostic_only_type =
    bool;
  _diagnostic_only_type diagnostic_only;
  using _reason_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _reason_type reason;
  using _control_source_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _control_source_type control_source;
  using _target_state_type =
    std::array<double, 6>;
  _target_state_type target_state;
  using _activation_state_type =
    std::array<double, 6>;
  _activation_state_type activation_state;
  using _state_error_type =
    std::array<double, 6>;
  _state_error_type state_error;
  using _requested_n_type =
    std::array<double, 2>;
  _requested_n_type requested_n;
  using _final_n_type =
    std::array<double, 2>;
  _final_n_type final_n;
  using _publish_success_type =
    std::array<bool, 2>;
  _publish_success_type publish_success;
  using _publish_start_ns_type =
    std::array<int64_t, 2>;
  _publish_start_ns_type publish_start_ns;
  using _publish_end_ns_type =
    std::array<int64_t, 2>;
  _publish_end_ns_type publish_end_ns;
  using _anchor_known_type =
    std::array<bool, 2>;
  _anchor_known_type anchor_known;
  using _anchor_sequence_type =
    std::array<uint64_t, 2>;
  _anchor_sequence_type anchor_sequence;
  using _previous_n_type =
    std::array<double, 2>;
  _previous_n_type previous_n;
  using _previous_publish_ns_type =
    std::array<int64_t, 2>;
  _previous_publish_ns_type previous_publish_ns;
  using _odom_age_ns_type =
    int64_t;
  _odom_age_ns_type odom_age_ns;
  using _imu_age_ns_type =
    int64_t;
  _imu_age_ns_type imu_age_ns;
  using _clock_age_ns_type =
    int64_t;
  _clock_age_ns_type clock_age_ns;
  using _normal_contract_complete_type =
    bool;
  _normal_contract_complete_type normal_contract_complete;
  using _rho_available_type =
    bool;
  _rho_available_type rho_available;
  using _plant_acceptance_observed_type =
    bool;
  _plant_acceptance_observed_type plant_acceptance_observed;
  using _previous_anchor_known_type =
    std::array<bool, 2>;
  _previous_anchor_known_type previous_anchor_known;
  using _publish_sim_ns_type =
    std::array<int64_t, 2>;
  _publish_sim_ns_type publish_sim_ns;
  using _publish_epoch_type =
    std::array<uint64_t, 2>;
  _publish_epoch_type publish_epoch;
  using _publish_clock_age_ns_type =
    std::array<int64_t, 2>;
  _publish_clock_age_ns_type publish_clock_age_ns;
  using _activation_clock_sim_ns_type =
    int64_t;
  _activation_clock_sim_ns_type activation_clock_sim_ns;
  using _activation_clock_receive_ns_type =
    int64_t;
  _activation_clock_receive_ns_type activation_clock_receive_ns;
  using _activation_rtf_type =
    double;
  _activation_rtf_type activation_rtf;
  using _activation_odom_stamp_ns_type =
    int64_t;
  _activation_odom_stamp_ns_type activation_odom_stamp_ns;
  using _activation_odom_receive_ns_type =
    int64_t;
  _activation_odom_receive_ns_type activation_odom_receive_ns;
  using _activation_odom_sequence_type =
    uint64_t;
  _activation_odom_sequence_type activation_odom_sequence;
  using _activation_imu_stamp_ns_type =
    int64_t;
  _activation_imu_stamp_ns_type activation_imu_stamp_ns;
  using _activation_imu_receive_ns_type =
    int64_t;
  _activation_imu_receive_ns_type activation_imu_receive_ns;
  using _activation_imu_sequence_type =
    uint64_t;
  _activation_imu_sequence_type activation_imu_sequence;
  using _activation_r_from_imu_type =
    bool;
  _activation_r_from_imu_type activation_r_from_imu;

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
  Type & set__worker_instance(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->worker_instance = _arg;
    return *this;
  }
  Type & set__mode(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->mode = _arg;
    return *this;
  }
  Type & set__sequence(
    const uint64_t & _arg)
  {
    this->sequence = _arg;
    return *this;
  }
  Type & set__tick(
    const uint64_t & _arg)
  {
    this->tick = _arg;
    return *this;
  }
  Type & set__job_id(
    const uint64_t & _arg)
  {
    this->job_id = _arg;
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
  Type & set__tick_planned_ns(
    const int64_t & _arg)
  {
    this->tick_planned_ns = _arg;
    return *this;
  }
  Type & set__tick_start_ns(
    const int64_t & _arg)
  {
    this->tick_start_ns = _arg;
    return *this;
  }
  Type & set__cutoff_commit_ns(
    const int64_t & _arg)
  {
    this->cutoff_commit_ns = _arg;
    return *this;
  }
  Type & set__candidate_ready_commit_ns(
    const int64_t & _arg)
  {
    this->candidate_ready_commit_ns = _arg;
    return *this;
  }
  Type & set__activation_commit_ns(
    const int64_t & _arg)
  {
    this->activation_commit_ns = _arg;
    return *this;
  }
  Type & set__tick_end_ns(
    const int64_t & _arg)
  {
    this->tick_end_ns = _arg;
    return *this;
  }
  Type & set__skipped_ticks(
    const uint64_t & _arg)
  {
    this->skipped_ticks = _arg;
    return *this;
  }
  Type & set__candidate_accepted(
    const bool & _arg)
  {
    this->candidate_accepted = _arg;
    return *this;
  }
  Type & set__diagnostic_only(
    const bool & _arg)
  {
    this->diagnostic_only = _arg;
    return *this;
  }
  Type & set__reason(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->reason = _arg;
    return *this;
  }
  Type & set__control_source(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->control_source = _arg;
    return *this;
  }
  Type & set__target_state(
    const std::array<double, 6> & _arg)
  {
    this->target_state = _arg;
    return *this;
  }
  Type & set__activation_state(
    const std::array<double, 6> & _arg)
  {
    this->activation_state = _arg;
    return *this;
  }
  Type & set__state_error(
    const std::array<double, 6> & _arg)
  {
    this->state_error = _arg;
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
  Type & set__publish_success(
    const std::array<bool, 2> & _arg)
  {
    this->publish_success = _arg;
    return *this;
  }
  Type & set__publish_start_ns(
    const std::array<int64_t, 2> & _arg)
  {
    this->publish_start_ns = _arg;
    return *this;
  }
  Type & set__publish_end_ns(
    const std::array<int64_t, 2> & _arg)
  {
    this->publish_end_ns = _arg;
    return *this;
  }
  Type & set__anchor_known(
    const std::array<bool, 2> & _arg)
  {
    this->anchor_known = _arg;
    return *this;
  }
  Type & set__anchor_sequence(
    const std::array<uint64_t, 2> & _arg)
  {
    this->anchor_sequence = _arg;
    return *this;
  }
  Type & set__previous_n(
    const std::array<double, 2> & _arg)
  {
    this->previous_n = _arg;
    return *this;
  }
  Type & set__previous_publish_ns(
    const std::array<int64_t, 2> & _arg)
  {
    this->previous_publish_ns = _arg;
    return *this;
  }
  Type & set__odom_age_ns(
    const int64_t & _arg)
  {
    this->odom_age_ns = _arg;
    return *this;
  }
  Type & set__imu_age_ns(
    const int64_t & _arg)
  {
    this->imu_age_ns = _arg;
    return *this;
  }
  Type & set__clock_age_ns(
    const int64_t & _arg)
  {
    this->clock_age_ns = _arg;
    return *this;
  }
  Type & set__normal_contract_complete(
    const bool & _arg)
  {
    this->normal_contract_complete = _arg;
    return *this;
  }
  Type & set__rho_available(
    const bool & _arg)
  {
    this->rho_available = _arg;
    return *this;
  }
  Type & set__plant_acceptance_observed(
    const bool & _arg)
  {
    this->plant_acceptance_observed = _arg;
    return *this;
  }
  Type & set__previous_anchor_known(
    const std::array<bool, 2> & _arg)
  {
    this->previous_anchor_known = _arg;
    return *this;
  }
  Type & set__publish_sim_ns(
    const std::array<int64_t, 2> & _arg)
  {
    this->publish_sim_ns = _arg;
    return *this;
  }
  Type & set__publish_epoch(
    const std::array<uint64_t, 2> & _arg)
  {
    this->publish_epoch = _arg;
    return *this;
  }
  Type & set__publish_clock_age_ns(
    const std::array<int64_t, 2> & _arg)
  {
    this->publish_clock_age_ns = _arg;
    return *this;
  }
  Type & set__activation_clock_sim_ns(
    const int64_t & _arg)
  {
    this->activation_clock_sim_ns = _arg;
    return *this;
  }
  Type & set__activation_clock_receive_ns(
    const int64_t & _arg)
  {
    this->activation_clock_receive_ns = _arg;
    return *this;
  }
  Type & set__activation_rtf(
    const double & _arg)
  {
    this->activation_rtf = _arg;
    return *this;
  }
  Type & set__activation_odom_stamp_ns(
    const int64_t & _arg)
  {
    this->activation_odom_stamp_ns = _arg;
    return *this;
  }
  Type & set__activation_odom_receive_ns(
    const int64_t & _arg)
  {
    this->activation_odom_receive_ns = _arg;
    return *this;
  }
  Type & set__activation_odom_sequence(
    const uint64_t & _arg)
  {
    this->activation_odom_sequence = _arg;
    return *this;
  }
  Type & set__activation_imu_stamp_ns(
    const int64_t & _arg)
  {
    this->activation_imu_stamp_ns = _arg;
    return *this;
  }
  Type & set__activation_imu_receive_ns(
    const int64_t & _arg)
  {
    this->activation_imu_receive_ns = _arg;
    return *this;
  }
  Type & set__activation_imu_sequence(
    const uint64_t & _arg)
  {
    this->activation_imu_sequence = _arg;
    return *this;
  }
  Type & set__activation_r_from_imu(
    const bool & _arg)
  {
    this->activation_r_from_imu = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    usv_research_interfaces::msg::ExecutionDecision_<ContainerAllocator> *;
  using ConstRawPtr =
    const usv_research_interfaces::msg::ExecutionDecision_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::ExecutionDecision_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::ExecutionDecision_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::ExecutionDecision_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::ExecutionDecision_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::ExecutionDecision_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::ExecutionDecision_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::ExecutionDecision_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::ExecutionDecision_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__usv_research_interfaces__msg__ExecutionDecision
    std::shared_ptr<usv_research_interfaces::msg::ExecutionDecision_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__usv_research_interfaces__msg__ExecutionDecision
    std::shared_ptr<usv_research_interfaces::msg::ExecutionDecision_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const ExecutionDecision_ & other) const
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
    if (this->worker_instance != other.worker_instance) {
      return false;
    }
    if (this->mode != other.mode) {
      return false;
    }
    if (this->sequence != other.sequence) {
      return false;
    }
    if (this->tick != other.tick) {
      return false;
    }
    if (this->job_id != other.job_id) {
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
    if (this->tick_planned_ns != other.tick_planned_ns) {
      return false;
    }
    if (this->tick_start_ns != other.tick_start_ns) {
      return false;
    }
    if (this->cutoff_commit_ns != other.cutoff_commit_ns) {
      return false;
    }
    if (this->candidate_ready_commit_ns != other.candidate_ready_commit_ns) {
      return false;
    }
    if (this->activation_commit_ns != other.activation_commit_ns) {
      return false;
    }
    if (this->tick_end_ns != other.tick_end_ns) {
      return false;
    }
    if (this->skipped_ticks != other.skipped_ticks) {
      return false;
    }
    if (this->candidate_accepted != other.candidate_accepted) {
      return false;
    }
    if (this->diagnostic_only != other.diagnostic_only) {
      return false;
    }
    if (this->reason != other.reason) {
      return false;
    }
    if (this->control_source != other.control_source) {
      return false;
    }
    if (this->target_state != other.target_state) {
      return false;
    }
    if (this->activation_state != other.activation_state) {
      return false;
    }
    if (this->state_error != other.state_error) {
      return false;
    }
    if (this->requested_n != other.requested_n) {
      return false;
    }
    if (this->final_n != other.final_n) {
      return false;
    }
    if (this->publish_success != other.publish_success) {
      return false;
    }
    if (this->publish_start_ns != other.publish_start_ns) {
      return false;
    }
    if (this->publish_end_ns != other.publish_end_ns) {
      return false;
    }
    if (this->anchor_known != other.anchor_known) {
      return false;
    }
    if (this->anchor_sequence != other.anchor_sequence) {
      return false;
    }
    if (this->previous_n != other.previous_n) {
      return false;
    }
    if (this->previous_publish_ns != other.previous_publish_ns) {
      return false;
    }
    if (this->odom_age_ns != other.odom_age_ns) {
      return false;
    }
    if (this->imu_age_ns != other.imu_age_ns) {
      return false;
    }
    if (this->clock_age_ns != other.clock_age_ns) {
      return false;
    }
    if (this->normal_contract_complete != other.normal_contract_complete) {
      return false;
    }
    if (this->rho_available != other.rho_available) {
      return false;
    }
    if (this->plant_acceptance_observed != other.plant_acceptance_observed) {
      return false;
    }
    if (this->previous_anchor_known != other.previous_anchor_known) {
      return false;
    }
    if (this->publish_sim_ns != other.publish_sim_ns) {
      return false;
    }
    if (this->publish_epoch != other.publish_epoch) {
      return false;
    }
    if (this->publish_clock_age_ns != other.publish_clock_age_ns) {
      return false;
    }
    if (this->activation_clock_sim_ns != other.activation_clock_sim_ns) {
      return false;
    }
    if (this->activation_clock_receive_ns != other.activation_clock_receive_ns) {
      return false;
    }
    if (this->activation_rtf != other.activation_rtf) {
      return false;
    }
    if (this->activation_odom_stamp_ns != other.activation_odom_stamp_ns) {
      return false;
    }
    if (this->activation_odom_receive_ns != other.activation_odom_receive_ns) {
      return false;
    }
    if (this->activation_odom_sequence != other.activation_odom_sequence) {
      return false;
    }
    if (this->activation_imu_stamp_ns != other.activation_imu_stamp_ns) {
      return false;
    }
    if (this->activation_imu_receive_ns != other.activation_imu_receive_ns) {
      return false;
    }
    if (this->activation_imu_sequence != other.activation_imu_sequence) {
      return false;
    }
    if (this->activation_r_from_imu != other.activation_r_from_imu) {
      return false;
    }
    return true;
  }
  bool operator!=(const ExecutionDecision_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct ExecutionDecision_

// alias to use template instance with default allocator
using ExecutionDecision =
  usv_research_interfaces::msg::ExecutionDecision_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__EXECUTION_DECISION__STRUCT_HPP_
