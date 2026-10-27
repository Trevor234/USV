// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from usv_research_interfaces:msg/ReferencePrediction.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/reference_prediction.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__REFERENCE_PREDICTION__BUILDER_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__REFERENCE_PREDICTION__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "usv_research_interfaces/msg/detail/reference_prediction__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace usv_research_interfaces
{

namespace msg
{

namespace builder
{

class Init_ReferencePrediction_u_pred_data
{
public:
  explicit Init_ReferencePrediction_u_pred_data(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  ::usv_research_interfaces::msg::ReferencePrediction u_pred_data(::usv_research_interfaces::msg::ReferencePrediction::_u_pred_data_type arg)
  {
    msg_.u_pred_data = std::move(arg);
    return std::move(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_u_pred_cols
{
public:
  explicit Init_ReferencePrediction_u_pred_cols(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_u_pred_data u_pred_cols(::usv_research_interfaces::msg::ReferencePrediction::_u_pred_cols_type arg)
  {
    msg_.u_pred_cols = std::move(arg);
    return Init_ReferencePrediction_u_pred_data(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_u_pred_rows
{
public:
  explicit Init_ReferencePrediction_u_pred_rows(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_u_pred_cols u_pred_rows(::usv_research_interfaces::msg::ReferencePrediction::_u_pred_rows_type arg)
  {
    msg_.u_pred_rows = std::move(arg);
    return Init_ReferencePrediction_u_pred_cols(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_x_pred_data
{
public:
  explicit Init_ReferencePrediction_x_pred_data(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_u_pred_rows x_pred_data(::usv_research_interfaces::msg::ReferencePrediction::_x_pred_data_type arg)
  {
    msg_.x_pred_data = std::move(arg);
    return Init_ReferencePrediction_u_pred_rows(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_x_pred_cols
{
public:
  explicit Init_ReferencePrediction_x_pred_cols(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_x_pred_data x_pred_cols(::usv_research_interfaces::msg::ReferencePrediction::_x_pred_cols_type arg)
  {
    msg_.x_pred_cols = std::move(arg);
    return Init_ReferencePrediction_x_pred_data(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_x_pred_rows
{
public:
  explicit Init_ReferencePrediction_x_pred_rows(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_x_pred_cols x_pred_rows(::usv_research_interfaces::msg::ReferencePrediction::_x_pred_rows_type arg)
  {
    msg_.x_pred_rows = std::move(arg);
    return Init_ReferencePrediction_x_pred_cols(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_prediction_reason
{
public:
  explicit Init_ReferencePrediction_prediction_reason(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_x_pred_rows prediction_reason(::usv_research_interfaces::msg::ReferencePrediction::_prediction_reason_type arg)
  {
    msg_.prediction_reason = std::move(arg);
    return Init_ReferencePrediction_x_pred_rows(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_prediction_available
{
public:
  explicit Init_ReferencePrediction_prediction_available(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_prediction_reason prediction_available(::usv_research_interfaces::msg::ReferencePrediction::_prediction_available_type arg)
  {
    msg_.prediction_available = std::move(arg);
    return Init_ReferencePrediction_prediction_reason(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_rejection_reason
{
public:
  explicit Init_ReferencePrediction_rejection_reason(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_prediction_available rejection_reason(::usv_research_interfaces::msg::ReferencePrediction::_rejection_reason_type arg)
  {
    msg_.rejection_reason = std::move(arg);
    return Init_ReferencePrediction_prediction_available(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_deadline_miss
{
public:
  explicit Init_ReferencePrediction_deadline_miss(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_rejection_reason deadline_miss(::usv_research_interfaces::msg::ReferencePrediction::_deadline_miss_type arg)
  {
    msg_.deadline_miss = std::move(arg);
    return Init_ReferencePrediction_rejection_reason(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_solve_success
{
public:
  explicit Init_ReferencePrediction_solve_success(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_deadline_miss solve_success(::usv_research_interfaces::msg::ReferencePrediction::_solve_success_type arg)
  {
    msg_.solve_success = std::move(arg);
    return Init_ReferencePrediction_deadline_miss(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_reference_data
{
public:
  explicit Init_ReferencePrediction_reference_data(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_solve_success reference_data(::usv_research_interfaces::msg::ReferencePrediction::_reference_data_type arg)
  {
    msg_.reference_data = std::move(arg);
    return Init_ReferencePrediction_solve_success(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_reference_cols
{
public:
  explicit Init_ReferencePrediction_reference_cols(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_reference_data reference_cols(::usv_research_interfaces::msg::ReferencePrediction::_reference_cols_type arg)
  {
    msg_.reference_cols = std::move(arg);
    return Init_ReferencePrediction_reference_data(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_reference_rows
{
public:
  explicit Init_ReferencePrediction_reference_rows(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_reference_cols reference_rows(::usv_research_interfaces::msg::ReferencePrediction::_reference_rows_type arg)
  {
    msg_.reference_rows = std::move(arg);
    return Init_ReferencePrediction_reference_cols(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_matrix_layout
{
public:
  explicit Init_ReferencePrediction_matrix_layout(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_reference_rows matrix_layout(::usv_research_interfaces::msg::ReferencePrediction::_matrix_layout_type arg)
  {
    msg_.matrix_layout = std::move(arg);
    return Init_ReferencePrediction_reference_rows(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_prediction_dt
{
public:
  explicit Init_ReferencePrediction_prediction_dt(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_matrix_layout prediction_dt(::usv_research_interfaces::msg::ReferencePrediction::_prediction_dt_type arg)
  {
    msg_.prediction_dt = std::move(arg);
    return Init_ReferencePrediction_matrix_layout(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_horizon_steps
{
public:
  explicit Init_ReferencePrediction_horizon_steps(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_prediction_dt horizon_steps(::usv_research_interfaces::msg::ReferencePrediction::_horizon_steps_type arg)
  {
    msg_.horizon_steps = std::move(arg);
    return Init_ReferencePrediction_prediction_dt(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_backend
{
public:
  explicit Init_ReferencePrediction_backend(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_horizon_steps backend(::usv_research_interfaces::msg::ReferencePrediction::_backend_type arg)
  {
    msg_.backend = std::move(arg);
    return Init_ReferencePrediction_horizon_steps(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_nominal_config_hash
{
public:
  explicit Init_ReferencePrediction_nominal_config_hash(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_backend nominal_config_hash(::usv_research_interfaces::msg::ReferencePrediction::_nominal_config_hash_type arg)
  {
    msg_.nominal_config_hash = std::move(arg);
    return Init_ReferencePrediction_backend(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_profile_t0
{
public:
  explicit Init_ReferencePrediction_profile_t0(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_nominal_config_hash profile_t0(::usv_research_interfaces::msg::ReferencePrediction::_profile_t0_type arg)
  {
    msg_.profile_t0 = std::move(arg);
    return Init_ReferencePrediction_nominal_config_hash(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_profile_t0_known
{
public:
  explicit Init_ReferencePrediction_profile_t0_known(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_profile_t0 profile_t0_known(::usv_research_interfaces::msg::ReferencePrediction::_profile_t0_known_type arg)
  {
    msg_.profile_t0_known = std::move(arg);
    return Init_ReferencePrediction_profile_t0(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_reference_mode
{
public:
  explicit Init_ReferencePrediction_reference_mode(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_profile_t0_known reference_mode(::usv_research_interfaces::msg::ReferencePrediction::_reference_mode_type arg)
  {
    msg_.reference_mode = std::move(arg);
    return Init_ReferencePrediction_profile_t0_known(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_profile_sync_reason
{
public:
  explicit Init_ReferencePrediction_profile_sync_reason(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_reference_mode profile_sync_reason(::usv_research_interfaces::msg::ReferencePrediction::_profile_sync_reason_type arg)
  {
    msg_.profile_sync_reason = std::move(arg);
    return Init_ReferencePrediction_reference_mode(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_profile_synced
{
public:
  explicit Init_ReferencePrediction_profile_synced(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_profile_sync_reason profile_synced(::usv_research_interfaces::msg::ReferencePrediction::_profile_synced_type arg)
  {
    msg_.profile_synced = std::move(arg);
    return Init_ReferencePrediction_profile_sync_reason(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_effective_start_offset
{
public:
  explicit Init_ReferencePrediction_effective_start_offset(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_profile_synced effective_start_offset(::usv_research_interfaces::msg::ReferencePrediction::_effective_start_offset_type arg)
  {
    msg_.effective_start_offset = std::move(arg);
    return Init_ReferencePrediction_profile_synced(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_configured_start_offset
{
public:
  explicit Init_ReferencePrediction_configured_start_offset(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_effective_start_offset configured_start_offset(::usv_research_interfaces::msg::ReferencePrediction::_configured_start_offset_type arg)
  {
    msg_.configured_start_offset = std::move(arg);
    return Init_ReferencePrediction_effective_start_offset(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_start_index
{
public:
  explicit Init_ReferencePrediction_start_index(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_configured_start_offset start_index(::usv_research_interfaces::msg::ReferencePrediction::_start_index_type arg)
  {
    msg_.start_index = std::move(arg);
    return Init_ReferencePrediction_configured_start_offset(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_nearest_index
{
public:
  explicit Init_ReferencePrediction_nearest_index(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_start_index nearest_index(::usv_research_interfaces::msg::ReferencePrediction::_nearest_index_type arg)
  {
    msg_.nearest_index = std::move(arg);
    return Init_ReferencePrediction_start_index(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_profile_size
{
public:
  explicit Init_ReferencePrediction_profile_size(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_nearest_index profile_size(::usv_research_interfaces::msg::ReferencePrediction::_profile_size_type arg)
  {
    msg_.profile_size = std::move(arg);
    return Init_ReferencePrediction_nearest_index(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_path_size
{
public:
  explicit Init_ReferencePrediction_path_size(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_profile_size path_size(::usv_research_interfaces::msg::ReferencePrediction::_path_size_type arg)
  {
    msg_.path_size = std::move(arg);
    return Init_ReferencePrediction_profile_size(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_profile_stamp_known
{
public:
  explicit Init_ReferencePrediction_profile_stamp_known(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_path_size profile_stamp_known(::usv_research_interfaces::msg::ReferencePrediction::_profile_stamp_known_type arg)
  {
    msg_.profile_stamp_known = std::move(arg);
    return Init_ReferencePrediction_path_size(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_profile_stamp_ns
{
public:
  explicit Init_ReferencePrediction_profile_stamp_ns(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_profile_stamp_known profile_stamp_ns(::usv_research_interfaces::msg::ReferencePrediction::_profile_stamp_ns_type arg)
  {
    msg_.profile_stamp_ns = std::move(arg);
    return Init_ReferencePrediction_profile_stamp_known(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_path_stamp_ns
{
public:
  explicit Init_ReferencePrediction_path_stamp_ns(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_profile_stamp_ns path_stamp_ns(::usv_research_interfaces::msg::ReferencePrediction::_path_stamp_ns_type arg)
  {
    msg_.path_stamp_ns = std::move(arg);
    return Init_ReferencePrediction_profile_stamp_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_profile_received_sequence
{
public:
  explicit Init_ReferencePrediction_profile_received_sequence(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_path_stamp_ns profile_received_sequence(::usv_research_interfaces::msg::ReferencePrediction::_profile_received_sequence_type arg)
  {
    msg_.profile_received_sequence = std::move(arg);
    return Init_ReferencePrediction_path_stamp_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_path_received_sequence
{
public:
  explicit Init_ReferencePrediction_path_received_sequence(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_profile_received_sequence path_received_sequence(::usv_research_interfaces::msg::ReferencePrediction::_path_received_sequence_type arg)
  {
    msg_.path_received_sequence = std::move(arg);
    return Init_ReferencePrediction_profile_received_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_imu_stamp_ns
{
public:
  explicit Init_ReferencePrediction_imu_stamp_ns(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_path_received_sequence imu_stamp_ns(::usv_research_interfaces::msg::ReferencePrediction::_imu_stamp_ns_type arg)
  {
    msg_.imu_stamp_ns = std::move(arg);
    return Init_ReferencePrediction_path_received_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_odom_stamp_ns
{
public:
  explicit Init_ReferencePrediction_odom_stamp_ns(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_imu_stamp_ns odom_stamp_ns(::usv_research_interfaces::msg::ReferencePrediction::_odom_stamp_ns_type arg)
  {
    msg_.odom_stamp_ns = std::move(arg);
    return Init_ReferencePrediction_imu_stamp_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_received_imu_sequence
{
public:
  explicit Init_ReferencePrediction_received_imu_sequence(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_odom_stamp_ns received_imu_sequence(::usv_research_interfaces::msg::ReferencePrediction::_received_imu_sequence_type arg)
  {
    msg_.received_imu_sequence = std::move(arg);
    return Init_ReferencePrediction_odom_stamp_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_received_odom_sequence
{
public:
  explicit Init_ReferencePrediction_received_odom_sequence(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_received_imu_sequence received_odom_sequence(::usv_research_interfaces::msg::ReferencePrediction::_received_odom_sequence_type arg)
  {
    msg_.received_odom_sequence = std::move(arg);
    return Init_ReferencePrediction_received_imu_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_state_kind
{
public:
  explicit Init_ReferencePrediction_state_kind(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_received_odom_sequence state_kind(::usv_research_interfaces::msg::ReferencePrediction::_state_kind_type arg)
  {
    msg_.state_kind = std::move(arg);
    return Init_ReferencePrediction_received_odom_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_controller_state_6
{
public:
  explicit Init_ReferencePrediction_controller_state_6(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_state_kind controller_state_6(::usv_research_interfaces::msg::ReferencePrediction::_controller_state_6_type arg)
  {
    msg_.controller_state_6 = std::move(arg);
    return Init_ReferencePrediction_state_kind(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_freeze_steady_ns
{
public:
  explicit Init_ReferencePrediction_freeze_steady_ns(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_controller_state_6 freeze_steady_ns(::usv_research_interfaces::msg::ReferencePrediction::_freeze_steady_ns_type arg)
  {
    msg_.freeze_steady_ns = std::move(arg);
    return Init_ReferencePrediction_controller_state_6(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_solve_end_steady_ns
{
public:
  explicit Init_ReferencePrediction_solve_end_steady_ns(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_freeze_steady_ns solve_end_steady_ns(::usv_research_interfaces::msg::ReferencePrediction::_solve_end_steady_ns_type arg)
  {
    msg_.solve_end_steady_ns = std::move(arg);
    return Init_ReferencePrediction_freeze_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_solve_start_steady_ns
{
public:
  explicit Init_ReferencePrediction_solve_start_steady_ns(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_solve_end_steady_ns solve_start_steady_ns(::usv_research_interfaces::msg::ReferencePrediction::_solve_start_steady_ns_type arg)
  {
    msg_.solve_start_steady_ns = std::move(arg);
    return Init_ReferencePrediction_solve_end_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_reference_ready_steady_ns
{
public:
  explicit Init_ReferencePrediction_reference_ready_steady_ns(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_solve_start_steady_ns reference_ready_steady_ns(::usv_research_interfaces::msg::ReferencePrediction::_reference_ready_steady_ns_type arg)
  {
    msg_.reference_ready_steady_ns = std::move(arg);
    return Init_ReferencePrediction_solve_start_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_state_copy_steady_ns
{
public:
  explicit Init_ReferencePrediction_state_copy_steady_ns(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_reference_ready_steady_ns state_copy_steady_ns(::usv_research_interfaces::msg::ReferencePrediction::_state_copy_steady_ns_type arg)
  {
    msg_.state_copy_steady_ns = std::move(arg);
    return Init_ReferencePrediction_reference_ready_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_applied_sequence
{
public:
  explicit Init_ReferencePrediction_applied_sequence(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_state_copy_steady_ns applied_sequence(::usv_research_interfaces::msg::ReferencePrediction::_applied_sequence_type arg)
  {
    msg_.applied_sequence = std::move(arg);
    return Init_ReferencePrediction_state_copy_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_cycle_sequence
{
public:
  explicit Init_ReferencePrediction_cycle_sequence(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_applied_sequence cycle_sequence(::usv_research_interfaces::msg::ReferencePrediction::_cycle_sequence_type arg)
  {
    msg_.cycle_sequence = std::move(arg);
    return Init_ReferencePrediction_applied_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_clock_status
{
public:
  explicit Init_ReferencePrediction_clock_status(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_cycle_sequence clock_status(::usv_research_interfaces::msg::ReferencePrediction::_clock_status_type arg)
  {
    msg_.clock_status = std::move(arg);
    return Init_ReferencePrediction_cycle_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_clock_age_ns
{
public:
  explicit Init_ReferencePrediction_clock_age_ns(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_clock_status clock_age_ns(::usv_research_interfaces::msg::ReferencePrediction::_clock_age_ns_type arg)
  {
    msg_.clock_age_ns = std::move(arg);
    return Init_ReferencePrediction_clock_status(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_clock_receive_steady_ns
{
public:
  explicit Init_ReferencePrediction_clock_receive_steady_ns(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_clock_age_ns clock_receive_steady_ns(::usv_research_interfaces::msg::ReferencePrediction::_clock_receive_steady_ns_type arg)
  {
    msg_.clock_receive_steady_ns = std::move(arg);
    return Init_ReferencePrediction_clock_age_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_sim_time_ns
{
public:
  explicit Init_ReferencePrediction_sim_time_ns(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_clock_receive_steady_ns sim_time_ns(::usv_research_interfaces::msg::ReferencePrediction::_sim_time_ns_type arg)
  {
    msg_.sim_time_ns = std::move(arg);
    return Init_ReferencePrediction_clock_receive_steady_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_clock_epoch
{
public:
  explicit Init_ReferencePrediction_clock_epoch(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_sim_time_ns clock_epoch(::usv_research_interfaces::msg::ReferencePrediction::_clock_epoch_type arg)
  {
    msg_.clock_epoch = std::move(arg);
    return Init_ReferencePrediction_sim_time_ns(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_sequence
{
public:
  explicit Init_ReferencePrediction_sequence(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_clock_epoch sequence(::usv_research_interfaces::msg::ReferencePrediction::_sequence_type arg)
  {
    msg_.sequence = std::move(arg);
    return Init_ReferencePrediction_clock_epoch(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_steady_clock_domain
{
public:
  explicit Init_ReferencePrediction_steady_clock_domain(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_sequence steady_clock_domain(::usv_research_interfaces::msg::ReferencePrediction::_steady_clock_domain_type arg)
  {
    msg_.steady_clock_domain = std::move(arg);
    return Init_ReferencePrediction_sequence(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_config_hash
{
public:
  explicit Init_ReferencePrediction_config_hash(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_steady_clock_domain config_hash(::usv_research_interfaces::msg::ReferencePrediction::_config_hash_type arg)
  {
    msg_.config_hash = std::move(arg);
    return Init_ReferencePrediction_steady_clock_domain(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_baseline_id
{
public:
  explicit Init_ReferencePrediction_baseline_id(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_config_hash baseline_id(::usv_research_interfaces::msg::ReferencePrediction::_baseline_id_type arg)
  {
    msg_.baseline_id = std::move(arg);
    return Init_ReferencePrediction_config_hash(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_producer_instance_id
{
public:
  explicit Init_ReferencePrediction_producer_instance_id(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_baseline_id producer_instance_id(::usv_research_interfaces::msg::ReferencePrediction::_producer_instance_id_type arg)
  {
    msg_.producer_instance_id = std::move(arg);
    return Init_ReferencePrediction_baseline_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_run_id
{
public:
  explicit Init_ReferencePrediction_run_id(::usv_research_interfaces::msg::ReferencePrediction & msg)
  : msg_(msg)
  {}
  Init_ReferencePrediction_producer_instance_id run_id(::usv_research_interfaces::msg::ReferencePrediction::_run_id_type arg)
  {
    msg_.run_id = std::move(arg);
    return Init_ReferencePrediction_producer_instance_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

class Init_ReferencePrediction_schema_version
{
public:
  Init_ReferencePrediction_schema_version()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_ReferencePrediction_run_id schema_version(::usv_research_interfaces::msg::ReferencePrediction::_schema_version_type arg)
  {
    msg_.schema_version = std::move(arg);
    return Init_ReferencePrediction_run_id(msg_);
  }

private:
  ::usv_research_interfaces::msg::ReferencePrediction msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::usv_research_interfaces::msg::ReferencePrediction>()
{
  return usv_research_interfaces::msg::builder::Init_ReferencePrediction_schema_version();
}

}  // namespace usv_research_interfaces

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__REFERENCE_PREDICTION__BUILDER_HPP_
