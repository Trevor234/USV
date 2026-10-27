// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from usv_research_interfaces:msg/ReferencePrediction.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/reference_prediction.h"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__REFERENCE_PREDICTION__STRUCT_H_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__REFERENCE_PREDICTION__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Constants defined in the message

// Include directives for member types
// Member 'schema_version'
// Member 'run_id'
// Member 'producer_instance_id'
// Member 'baseline_id'
// Member 'config_hash'
// Member 'steady_clock_domain'
// Member 'clock_status'
// Member 'state_kind'
// Member 'profile_sync_reason'
// Member 'reference_mode'
// Member 'nominal_config_hash'
// Member 'backend'
// Member 'matrix_layout'
// Member 'rejection_reason'
// Member 'prediction_reason'
#include "rosidl_runtime_c/string.h"
// Member 'reference_data'
// Member 'x_pred_data'
// Member 'u_pred_data'
#include "rosidl_runtime_c/primitives_sequence.h"

/// Struct defined in msg/ReferencePrediction in the package usv_research_interfaces.
/**
  * Actual solve inputs and accepted prediction; publisher-side observation only.
  * Independent extension. StateSnapshot/AppliedControl/CycleTiming stay v1.
 */
typedef struct usv_research_interfaces__msg__ReferencePrediction
{
  rosidl_runtime_c__String schema_version;
  rosidl_runtime_c__String run_id;
  rosidl_runtime_c__String producer_instance_id;
  rosidl_runtime_c__String baseline_id;
  rosidl_runtime_c__String config_hash;
  rosidl_runtime_c__String steady_clock_domain;
  uint64_t sequence;
  uint64_t clock_epoch;
  int64_t sim_time_ns;
  int64_t clock_receive_steady_ns;
  int64_t clock_age_ns;
  rosidl_runtime_c__String clock_status;
  uint64_t cycle_sequence;
  uint64_t applied_sequence;
  int64_t state_copy_steady_ns;
  int64_t reference_ready_steady_ns;
  int64_t solve_start_steady_ns;
  int64_t solve_end_steady_ns;
  int64_t freeze_steady_ns;
  double controller_state_6[6];
  rosidl_runtime_c__String state_kind;
  uint64_t received_odom_sequence;
  uint64_t received_imu_sequence;
  int64_t odom_stamp_ns;
  int64_t imu_stamp_ns;
  /// Versions count every callback, including callbacks clearing empty/malformed data.
  /// They identify received container versions, not valid or accepted messages.
  uint64_t path_received_sequence;
  uint64_t profile_received_sequence;
  int64_t path_stamp_ns;
  int64_t profile_stamp_ns;
  bool profile_stamp_known;
  uint64_t path_size;
  uint64_t profile_size;
  int32_t nearest_index;
  int32_t start_index;
  int32_t configured_start_offset;
  int32_t effective_start_offset;
  bool profile_synced;
  rosidl_runtime_c__String profile_sync_reason;
  rosidl_runtime_c__String reference_mode;
  bool profile_t0_known;
  double profile_t0;
  /// config_hash binds all run config; this hash binds effective nominal model only.
  rosidl_runtime_c__String nominal_config_hash;
  rosidl_runtime_c__String backend;
  uint32_t horizon_steps;
  double prediction_dt;
  /// k_major = k=0 column first, each column in state/control component order.
  /// Reference is the exact already-built matrix supplied to solve(), 6*(N+1).
  rosidl_runtime_c__String matrix_layout;
  uint32_t reference_rows;
  uint32_t reference_cols;
  rosidl_runtime_c__double__Sequence reference_data;
  bool solve_success;
  bool deadline_miss;
  rosidl_runtime_c__String rejection_reason;
  /// Only successful post-deadline-gate finite, correctly sized info.X_pred/U_pred.
  /// False => all prediction shapes are zero and arrays empty; no candidate copy.
  bool prediction_available;
  rosidl_runtime_c__String prediction_reason;
  uint32_t x_pred_rows;
  uint32_t x_pred_cols;
  rosidl_runtime_c__double__Sequence x_pred_data;
  uint32_t u_pred_rows;
  uint32_t u_pred_cols;
  rosidl_runtime_c__double__Sequence u_pred_data;
} usv_research_interfaces__msg__ReferencePrediction;

// Struct for a sequence of usv_research_interfaces__msg__ReferencePrediction.
typedef struct usv_research_interfaces__msg__ReferencePrediction__Sequence
{
  usv_research_interfaces__msg__ReferencePrediction * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} usv_research_interfaces__msg__ReferencePrediction__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__REFERENCE_PREDICTION__STRUCT_H_
