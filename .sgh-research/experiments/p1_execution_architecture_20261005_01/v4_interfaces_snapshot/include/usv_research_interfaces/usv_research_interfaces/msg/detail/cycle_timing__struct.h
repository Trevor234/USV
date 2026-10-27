// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from usv_research_interfaces:msg/CycleTiming.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/cycle_timing.h"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__CYCLE_TIMING__STRUCT_H_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__CYCLE_TIMING__STRUCT_H_

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
// Member 'clock_status'
// Member 'steady_clock_domain'
// Member 'state_kind'
// Member 'rejection_reason'
#include "rosidl_runtime_c/string.h"

/// Struct defined in msg/CycleTiming in the package usv_research_interfaces.
/**
  * Publisher-side observation contract; no plant execution acknowledgement.
 */
typedef struct usv_research_interfaces__msg__CycleTiming
{
  rosidl_runtime_c__String schema_version;
  rosidl_runtime_c__String run_id;
  rosidl_runtime_c__String producer_instance_id;
  rosidl_runtime_c__String baseline_id;
  rosidl_runtime_c__String config_hash;
  uint64_t sequence;
  uint64_t clock_epoch;
  int64_t sim_time_ns;
  int64_t clock_receive_steady_ns;
  int64_t clock_age_ns;
  rosidl_runtime_c__String clock_status;
  rosidl_runtime_c__String steady_clock_domain;
  int64_t timer_entry_steady_ns;
  int64_t state_copy_steady_ns;
  int64_t reference_ready_steady_ns;
  int64_t solve_start_steady_ns;
  int64_t solve_end_steady_ns;
  int64_t publish_end_steady_ns;
  double controller_state_6[6];
  rosidl_runtime_c__String state_kind;
  uint64_t received_odom_sequence;
  uint64_t received_imu_sequence;
  int64_t odom_stamp_ns;
  int64_t imu_stamp_ns;
  double backend_time_ms;
  double budget_ms;
  bool success;
  bool deadline_miss;
  rosidl_runtime_c__String rejection_reason;
  uint64_t applied_sequence;
  bool solve_invoked;
} usv_research_interfaces__msg__CycleTiming;

// Struct for a sequence of usv_research_interfaces__msg__CycleTiming.
typedef struct usv_research_interfaces__msg__CycleTiming__Sequence
{
  usv_research_interfaces__msg__CycleTiming * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} usv_research_interfaces__msg__CycleTiming__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__CYCLE_TIMING__STRUCT_H_
