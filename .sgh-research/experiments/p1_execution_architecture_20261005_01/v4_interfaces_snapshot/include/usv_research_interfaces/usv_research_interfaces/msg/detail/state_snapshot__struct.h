// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from usv_research_interfaces:msg/StateSnapshot.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/state_snapshot.h"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__STATE_SNAPSHOT__STRUCT_H_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__STATE_SNAPSHOT__STRUCT_H_

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
// Member 'frame_id'
// Member 'child_frame_id'
// Member 'quality_reason'
// Member 'source_topic'
#include "rosidl_runtime_c/string.h"

/// Struct defined in msg/StateSnapshot in the package usv_research_interfaces.
/**
  * Publisher-side observation contract; no plant execution acknowledgement.
 */
typedef struct usv_research_interfaces__msg__StateSnapshot
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
  uint64_t received_odom_sequence;
  int64_t odom_stamp_ns;
  int64_t receive_steady_ns;
  int64_t freeze_steady_ns;
  rosidl_runtime_c__String frame_id;
  rosidl_runtime_c__String child_frame_id;
  double state_6[6];
  bool valid;
  rosidl_runtime_c__String quality_reason;
  rosidl_runtime_c__String source_topic;
} usv_research_interfaces__msg__StateSnapshot;

// Struct for a sequence of usv_research_interfaces__msg__StateSnapshot.
typedef struct usv_research_interfaces__msg__StateSnapshot__Sequence
{
  usv_research_interfaces__msg__StateSnapshot * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} usv_research_interfaces__msg__StateSnapshot__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__STATE_SNAPSHOT__STRUCT_H_
