// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from usv_research_interfaces:msg/AppliedControl.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/applied_control.h"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__APPLIED_CONTROL__STRUCT_H_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__APPLIED_CONTROL__STRUCT_H_

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
// Member 'control_source'
// Member 'event_semantics'
// Member 'publish_error'
#include "rosidl_runtime_c/string.h"

/// Struct defined in msg/AppliedControl in the package usv_research_interfaces.
/**
  * Publisher-side observation contract; no plant execution acknowledgement.
 */
typedef struct usv_research_interfaces__msg__AppliedControl
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
  uint64_t cycle_sequence;
  rosidl_runtime_c__String control_source;
  rosidl_runtime_c__String event_semantics;
  bool requested_known;
  double requested_n[2];
  double final_n[2];
  bool left_publish_success;
  bool right_publish_success;
  int64_t left_publish_start_steady_ns;
  int64_t left_publish_end_steady_ns;
  int64_t right_publish_start_steady_ns;
  int64_t right_publish_end_steady_ns;
  int64_t left_sim_time_ns;
  int64_t right_sim_time_ns;
  uint64_t left_clock_epoch;
  uint64_t right_clock_epoch;
  int64_t left_clock_age_ns;
  int64_t right_clock_age_ns;
  double map_scale;
  double lower_n;
  double upper_n;
  bool previous_anchor_known;
  double previous_final_n[2];
  bool plant_acceptance_observed;
  bool force_measured;
  bool execution_atomicity_proven;
  rosidl_runtime_c__String publish_error;
} usv_research_interfaces__msg__AppliedControl;

// Struct for a sequence of usv_research_interfaces__msg__AppliedControl.
typedef struct usv_research_interfaces__msg__AppliedControl__Sequence
{
  usv_research_interfaces__msg__AppliedControl * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} usv_research_interfaces__msg__AppliedControl__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__APPLIED_CONTROL__STRUCT_H_
