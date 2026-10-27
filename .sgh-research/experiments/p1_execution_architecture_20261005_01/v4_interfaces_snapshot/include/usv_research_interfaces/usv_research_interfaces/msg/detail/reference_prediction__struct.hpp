// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from usv_research_interfaces:msg/ReferencePrediction.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/reference_prediction.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__REFERENCE_PREDICTION__STRUCT_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__REFERENCE_PREDICTION__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


#ifndef _WIN32
# define DEPRECATED__usv_research_interfaces__msg__ReferencePrediction __attribute__((deprecated))
#else
# define DEPRECATED__usv_research_interfaces__msg__ReferencePrediction __declspec(deprecated)
#endif

namespace usv_research_interfaces
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct ReferencePrediction_
{
  using Type = ReferencePrediction_<ContainerAllocator>;

  explicit ReferencePrediction_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->schema_version = "";
      this->run_id = "";
      this->producer_instance_id = "";
      this->baseline_id = "";
      this->config_hash = "";
      this->steady_clock_domain = "";
      this->sequence = 0ull;
      this->clock_epoch = 0ull;
      this->sim_time_ns = 0ll;
      this->clock_receive_steady_ns = 0ll;
      this->clock_age_ns = 0ll;
      this->clock_status = "";
      this->cycle_sequence = 0ull;
      this->applied_sequence = 0ull;
      this->state_copy_steady_ns = 0ll;
      this->reference_ready_steady_ns = 0ll;
      this->solve_start_steady_ns = 0ll;
      this->solve_end_steady_ns = 0ll;
      this->freeze_steady_ns = 0ll;
      std::fill<typename std::array<double, 6>::iterator, double>(this->controller_state_6.begin(), this->controller_state_6.end(), 0.0);
      this->state_kind = "";
      this->received_odom_sequence = 0ull;
      this->received_imu_sequence = 0ull;
      this->odom_stamp_ns = 0ll;
      this->imu_stamp_ns = 0ll;
      this->path_received_sequence = 0ull;
      this->profile_received_sequence = 0ull;
      this->path_stamp_ns = 0ll;
      this->profile_stamp_ns = 0ll;
      this->profile_stamp_known = false;
      this->path_size = 0ull;
      this->profile_size = 0ull;
      this->nearest_index = 0l;
      this->start_index = 0l;
      this->configured_start_offset = 0l;
      this->effective_start_offset = 0l;
      this->profile_synced = false;
      this->profile_sync_reason = "";
      this->reference_mode = "";
      this->profile_t0_known = false;
      this->profile_t0 = 0.0;
      this->nominal_config_hash = "";
      this->backend = "";
      this->horizon_steps = 0ul;
      this->prediction_dt = 0.0;
      this->matrix_layout = "";
      this->reference_rows = 0ul;
      this->reference_cols = 0ul;
      this->solve_success = false;
      this->deadline_miss = false;
      this->rejection_reason = "";
      this->prediction_available = false;
      this->prediction_reason = "";
      this->x_pred_rows = 0ul;
      this->x_pred_cols = 0ul;
      this->u_pred_rows = 0ul;
      this->u_pred_cols = 0ul;
    }
  }

  explicit ReferencePrediction_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : schema_version(_alloc),
    run_id(_alloc),
    producer_instance_id(_alloc),
    baseline_id(_alloc),
    config_hash(_alloc),
    steady_clock_domain(_alloc),
    clock_status(_alloc),
    controller_state_6(_alloc),
    state_kind(_alloc),
    profile_sync_reason(_alloc),
    reference_mode(_alloc),
    nominal_config_hash(_alloc),
    backend(_alloc),
    matrix_layout(_alloc),
    rejection_reason(_alloc),
    prediction_reason(_alloc)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->schema_version = "";
      this->run_id = "";
      this->producer_instance_id = "";
      this->baseline_id = "";
      this->config_hash = "";
      this->steady_clock_domain = "";
      this->sequence = 0ull;
      this->clock_epoch = 0ull;
      this->sim_time_ns = 0ll;
      this->clock_receive_steady_ns = 0ll;
      this->clock_age_ns = 0ll;
      this->clock_status = "";
      this->cycle_sequence = 0ull;
      this->applied_sequence = 0ull;
      this->state_copy_steady_ns = 0ll;
      this->reference_ready_steady_ns = 0ll;
      this->solve_start_steady_ns = 0ll;
      this->solve_end_steady_ns = 0ll;
      this->freeze_steady_ns = 0ll;
      std::fill<typename std::array<double, 6>::iterator, double>(this->controller_state_6.begin(), this->controller_state_6.end(), 0.0);
      this->state_kind = "";
      this->received_odom_sequence = 0ull;
      this->received_imu_sequence = 0ull;
      this->odom_stamp_ns = 0ll;
      this->imu_stamp_ns = 0ll;
      this->path_received_sequence = 0ull;
      this->profile_received_sequence = 0ull;
      this->path_stamp_ns = 0ll;
      this->profile_stamp_ns = 0ll;
      this->profile_stamp_known = false;
      this->path_size = 0ull;
      this->profile_size = 0ull;
      this->nearest_index = 0l;
      this->start_index = 0l;
      this->configured_start_offset = 0l;
      this->effective_start_offset = 0l;
      this->profile_synced = false;
      this->profile_sync_reason = "";
      this->reference_mode = "";
      this->profile_t0_known = false;
      this->profile_t0 = 0.0;
      this->nominal_config_hash = "";
      this->backend = "";
      this->horizon_steps = 0ul;
      this->prediction_dt = 0.0;
      this->matrix_layout = "";
      this->reference_rows = 0ul;
      this->reference_cols = 0ul;
      this->solve_success = false;
      this->deadline_miss = false;
      this->rejection_reason = "";
      this->prediction_available = false;
      this->prediction_reason = "";
      this->x_pred_rows = 0ul;
      this->x_pred_cols = 0ul;
      this->u_pred_rows = 0ul;
      this->u_pred_cols = 0ul;
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
  using _steady_clock_domain_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _steady_clock_domain_type steady_clock_domain;
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
  using _cycle_sequence_type =
    uint64_t;
  _cycle_sequence_type cycle_sequence;
  using _applied_sequence_type =
    uint64_t;
  _applied_sequence_type applied_sequence;
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
  using _freeze_steady_ns_type =
    int64_t;
  _freeze_steady_ns_type freeze_steady_ns;
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
  using _path_received_sequence_type =
    uint64_t;
  _path_received_sequence_type path_received_sequence;
  using _profile_received_sequence_type =
    uint64_t;
  _profile_received_sequence_type profile_received_sequence;
  using _path_stamp_ns_type =
    int64_t;
  _path_stamp_ns_type path_stamp_ns;
  using _profile_stamp_ns_type =
    int64_t;
  _profile_stamp_ns_type profile_stamp_ns;
  using _profile_stamp_known_type =
    bool;
  _profile_stamp_known_type profile_stamp_known;
  using _path_size_type =
    uint64_t;
  _path_size_type path_size;
  using _profile_size_type =
    uint64_t;
  _profile_size_type profile_size;
  using _nearest_index_type =
    int32_t;
  _nearest_index_type nearest_index;
  using _start_index_type =
    int32_t;
  _start_index_type start_index;
  using _configured_start_offset_type =
    int32_t;
  _configured_start_offset_type configured_start_offset;
  using _effective_start_offset_type =
    int32_t;
  _effective_start_offset_type effective_start_offset;
  using _profile_synced_type =
    bool;
  _profile_synced_type profile_synced;
  using _profile_sync_reason_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _profile_sync_reason_type profile_sync_reason;
  using _reference_mode_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _reference_mode_type reference_mode;
  using _profile_t0_known_type =
    bool;
  _profile_t0_known_type profile_t0_known;
  using _profile_t0_type =
    double;
  _profile_t0_type profile_t0;
  using _nominal_config_hash_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _nominal_config_hash_type nominal_config_hash;
  using _backend_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _backend_type backend;
  using _horizon_steps_type =
    uint32_t;
  _horizon_steps_type horizon_steps;
  using _prediction_dt_type =
    double;
  _prediction_dt_type prediction_dt;
  using _matrix_layout_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _matrix_layout_type matrix_layout;
  using _reference_rows_type =
    uint32_t;
  _reference_rows_type reference_rows;
  using _reference_cols_type =
    uint32_t;
  _reference_cols_type reference_cols;
  using _reference_data_type =
    std::vector<double, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<double>>;
  _reference_data_type reference_data;
  using _solve_success_type =
    bool;
  _solve_success_type solve_success;
  using _deadline_miss_type =
    bool;
  _deadline_miss_type deadline_miss;
  using _rejection_reason_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _rejection_reason_type rejection_reason;
  using _prediction_available_type =
    bool;
  _prediction_available_type prediction_available;
  using _prediction_reason_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _prediction_reason_type prediction_reason;
  using _x_pred_rows_type =
    uint32_t;
  _x_pred_rows_type x_pred_rows;
  using _x_pred_cols_type =
    uint32_t;
  _x_pred_cols_type x_pred_cols;
  using _x_pred_data_type =
    std::vector<double, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<double>>;
  _x_pred_data_type x_pred_data;
  using _u_pred_rows_type =
    uint32_t;
  _u_pred_rows_type u_pred_rows;
  using _u_pred_cols_type =
    uint32_t;
  _u_pred_cols_type u_pred_cols;
  using _u_pred_data_type =
    std::vector<double, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<double>>;
  _u_pred_data_type u_pred_data;

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
  Type & set__steady_clock_domain(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->steady_clock_domain = _arg;
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
  Type & set__cycle_sequence(
    const uint64_t & _arg)
  {
    this->cycle_sequence = _arg;
    return *this;
  }
  Type & set__applied_sequence(
    const uint64_t & _arg)
  {
    this->applied_sequence = _arg;
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
  Type & set__freeze_steady_ns(
    const int64_t & _arg)
  {
    this->freeze_steady_ns = _arg;
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
  Type & set__path_received_sequence(
    const uint64_t & _arg)
  {
    this->path_received_sequence = _arg;
    return *this;
  }
  Type & set__profile_received_sequence(
    const uint64_t & _arg)
  {
    this->profile_received_sequence = _arg;
    return *this;
  }
  Type & set__path_stamp_ns(
    const int64_t & _arg)
  {
    this->path_stamp_ns = _arg;
    return *this;
  }
  Type & set__profile_stamp_ns(
    const int64_t & _arg)
  {
    this->profile_stamp_ns = _arg;
    return *this;
  }
  Type & set__profile_stamp_known(
    const bool & _arg)
  {
    this->profile_stamp_known = _arg;
    return *this;
  }
  Type & set__path_size(
    const uint64_t & _arg)
  {
    this->path_size = _arg;
    return *this;
  }
  Type & set__profile_size(
    const uint64_t & _arg)
  {
    this->profile_size = _arg;
    return *this;
  }
  Type & set__nearest_index(
    const int32_t & _arg)
  {
    this->nearest_index = _arg;
    return *this;
  }
  Type & set__start_index(
    const int32_t & _arg)
  {
    this->start_index = _arg;
    return *this;
  }
  Type & set__configured_start_offset(
    const int32_t & _arg)
  {
    this->configured_start_offset = _arg;
    return *this;
  }
  Type & set__effective_start_offset(
    const int32_t & _arg)
  {
    this->effective_start_offset = _arg;
    return *this;
  }
  Type & set__profile_synced(
    const bool & _arg)
  {
    this->profile_synced = _arg;
    return *this;
  }
  Type & set__profile_sync_reason(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->profile_sync_reason = _arg;
    return *this;
  }
  Type & set__reference_mode(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->reference_mode = _arg;
    return *this;
  }
  Type & set__profile_t0_known(
    const bool & _arg)
  {
    this->profile_t0_known = _arg;
    return *this;
  }
  Type & set__profile_t0(
    const double & _arg)
  {
    this->profile_t0 = _arg;
    return *this;
  }
  Type & set__nominal_config_hash(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->nominal_config_hash = _arg;
    return *this;
  }
  Type & set__backend(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->backend = _arg;
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
  Type & set__matrix_layout(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->matrix_layout = _arg;
    return *this;
  }
  Type & set__reference_rows(
    const uint32_t & _arg)
  {
    this->reference_rows = _arg;
    return *this;
  }
  Type & set__reference_cols(
    const uint32_t & _arg)
  {
    this->reference_cols = _arg;
    return *this;
  }
  Type & set__reference_data(
    const std::vector<double, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<double>> & _arg)
  {
    this->reference_data = _arg;
    return *this;
  }
  Type & set__solve_success(
    const bool & _arg)
  {
    this->solve_success = _arg;
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
  Type & set__prediction_available(
    const bool & _arg)
  {
    this->prediction_available = _arg;
    return *this;
  }
  Type & set__prediction_reason(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->prediction_reason = _arg;
    return *this;
  }
  Type & set__x_pred_rows(
    const uint32_t & _arg)
  {
    this->x_pred_rows = _arg;
    return *this;
  }
  Type & set__x_pred_cols(
    const uint32_t & _arg)
  {
    this->x_pred_cols = _arg;
    return *this;
  }
  Type & set__x_pred_data(
    const std::vector<double, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<double>> & _arg)
  {
    this->x_pred_data = _arg;
    return *this;
  }
  Type & set__u_pred_rows(
    const uint32_t & _arg)
  {
    this->u_pred_rows = _arg;
    return *this;
  }
  Type & set__u_pred_cols(
    const uint32_t & _arg)
  {
    this->u_pred_cols = _arg;
    return *this;
  }
  Type & set__u_pred_data(
    const std::vector<double, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<double>> & _arg)
  {
    this->u_pred_data = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    usv_research_interfaces::msg::ReferencePrediction_<ContainerAllocator> *;
  using ConstRawPtr =
    const usv_research_interfaces::msg::ReferencePrediction_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::ReferencePrediction_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<usv_research_interfaces::msg::ReferencePrediction_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::ReferencePrediction_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::ReferencePrediction_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      usv_research_interfaces::msg::ReferencePrediction_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<usv_research_interfaces::msg::ReferencePrediction_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::ReferencePrediction_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<usv_research_interfaces::msg::ReferencePrediction_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__usv_research_interfaces__msg__ReferencePrediction
    std::shared_ptr<usv_research_interfaces::msg::ReferencePrediction_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__usv_research_interfaces__msg__ReferencePrediction
    std::shared_ptr<usv_research_interfaces::msg::ReferencePrediction_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const ReferencePrediction_ & other) const
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
    if (this->steady_clock_domain != other.steady_clock_domain) {
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
    if (this->cycle_sequence != other.cycle_sequence) {
      return false;
    }
    if (this->applied_sequence != other.applied_sequence) {
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
    if (this->freeze_steady_ns != other.freeze_steady_ns) {
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
    if (this->path_received_sequence != other.path_received_sequence) {
      return false;
    }
    if (this->profile_received_sequence != other.profile_received_sequence) {
      return false;
    }
    if (this->path_stamp_ns != other.path_stamp_ns) {
      return false;
    }
    if (this->profile_stamp_ns != other.profile_stamp_ns) {
      return false;
    }
    if (this->profile_stamp_known != other.profile_stamp_known) {
      return false;
    }
    if (this->path_size != other.path_size) {
      return false;
    }
    if (this->profile_size != other.profile_size) {
      return false;
    }
    if (this->nearest_index != other.nearest_index) {
      return false;
    }
    if (this->start_index != other.start_index) {
      return false;
    }
    if (this->configured_start_offset != other.configured_start_offset) {
      return false;
    }
    if (this->effective_start_offset != other.effective_start_offset) {
      return false;
    }
    if (this->profile_synced != other.profile_synced) {
      return false;
    }
    if (this->profile_sync_reason != other.profile_sync_reason) {
      return false;
    }
    if (this->reference_mode != other.reference_mode) {
      return false;
    }
    if (this->profile_t0_known != other.profile_t0_known) {
      return false;
    }
    if (this->profile_t0 != other.profile_t0) {
      return false;
    }
    if (this->nominal_config_hash != other.nominal_config_hash) {
      return false;
    }
    if (this->backend != other.backend) {
      return false;
    }
    if (this->horizon_steps != other.horizon_steps) {
      return false;
    }
    if (this->prediction_dt != other.prediction_dt) {
      return false;
    }
    if (this->matrix_layout != other.matrix_layout) {
      return false;
    }
    if (this->reference_rows != other.reference_rows) {
      return false;
    }
    if (this->reference_cols != other.reference_cols) {
      return false;
    }
    if (this->reference_data != other.reference_data) {
      return false;
    }
    if (this->solve_success != other.solve_success) {
      return false;
    }
    if (this->deadline_miss != other.deadline_miss) {
      return false;
    }
    if (this->rejection_reason != other.rejection_reason) {
      return false;
    }
    if (this->prediction_available != other.prediction_available) {
      return false;
    }
    if (this->prediction_reason != other.prediction_reason) {
      return false;
    }
    if (this->x_pred_rows != other.x_pred_rows) {
      return false;
    }
    if (this->x_pred_cols != other.x_pred_cols) {
      return false;
    }
    if (this->x_pred_data != other.x_pred_data) {
      return false;
    }
    if (this->u_pred_rows != other.u_pred_rows) {
      return false;
    }
    if (this->u_pred_cols != other.u_pred_cols) {
      return false;
    }
    if (this->u_pred_data != other.u_pred_data) {
      return false;
    }
    return true;
  }
  bool operator!=(const ReferencePrediction_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct ReferencePrediction_

// alias to use template instance with default allocator
using ReferencePrediction =
  usv_research_interfaces::msg::ReferencePrediction_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__REFERENCE_PREDICTION__STRUCT_HPP_
