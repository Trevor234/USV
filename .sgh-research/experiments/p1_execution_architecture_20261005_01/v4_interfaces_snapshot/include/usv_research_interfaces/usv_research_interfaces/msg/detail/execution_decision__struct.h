// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from usv_research_interfaces:msg/ExecutionDecision.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/execution_decision.h"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__EXECUTION_DECISION__STRUCT_H_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__EXECUTION_DECISION__STRUCT_H_

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
// Member 'boot_id'
// Member 'contract_hash'
// Member 'worker_instance'
// Member 'mode'
// Member 'reason'
// Member 'control_source'
#include "rosidl_runtime_c/string.h"

// constants for array fields with an upper bound
// schema_version
enum
{
  usv_research_interfaces__msg__ExecutionDecision__schema_version__MAX_STRING_SIZE = 64
};
// run_id
enum
{
  usv_research_interfaces__msg__ExecutionDecision__run_id__MAX_STRING_SIZE = 128
};
// boot_id
enum
{
  usv_research_interfaces__msg__ExecutionDecision__boot_id__MAX_STRING_SIZE = 64
};
// contract_hash
enum
{
  usv_research_interfaces__msg__ExecutionDecision__contract_hash__MAX_STRING_SIZE = 64
};
// worker_instance
enum
{
  usv_research_interfaces__msg__ExecutionDecision__worker_instance__MAX_STRING_SIZE = 64
};
// mode
enum
{
  usv_research_interfaces__msg__ExecutionDecision__mode__MAX_STRING_SIZE = 16
};
// reason
enum
{
  usv_research_interfaces__msg__ExecutionDecision__reason__MAX_STRING_SIZE = 256
};
// control_source
enum
{
  usv_research_interfaces__msg__ExecutionDecision__control_source__MAX_STRING_SIZE = 32
};

/// Struct defined in msg/ExecutionDecision in the package usv_research_interfaces.
typedef struct usv_research_interfaces__msg__ExecutionDecision
{
  rosidl_runtime_c__String schema_version;
  rosidl_runtime_c__String run_id;
  rosidl_runtime_c__String boot_id;
  rosidl_runtime_c__String contract_hash;
  rosidl_runtime_c__String worker_instance;
  rosidl_runtime_c__String mode;
  uint64_t sequence;
  uint64_t tick;
  uint64_t job_id;
  uint64_t task_generation;
  uint64_t model_generation;
  uint64_t config_generation;
  uint64_t schedule_generation;
  uint64_t clock_epoch;
  int64_t tick_planned_ns;
  int64_t tick_start_ns;
  int64_t cutoff_commit_ns;
  int64_t candidate_ready_commit_ns;
  int64_t activation_commit_ns;
  int64_t tick_end_ns;
  uint64_t skipped_ticks;
  bool candidate_accepted;
  bool diagnostic_only;
  rosidl_runtime_c__String reason;
  rosidl_runtime_c__String control_source;
  double target_state[6];
  double activation_state[6];
  double state_error[6];
  double requested_n[2];
  double final_n[2];
  bool publish_success[2];
  int64_t publish_start_ns[2];
  int64_t publish_end_ns[2];
  bool anchor_known[2];
  uint64_t anchor_sequence[2];
  double previous_n[2];
  int64_t previous_publish_ns[2];
  int64_t odom_age_ns;
  int64_t imu_age_ns;
  int64_t clock_age_ns;
  bool normal_contract_complete;
  bool rho_available;
  bool plant_acceptance_observed;
  bool previous_anchor_known[2];
  int64_t publish_sim_ns[2];
  uint64_t publish_epoch[2];
  int64_t publish_clock_age_ns[2];
  int64_t activation_clock_sim_ns;
  int64_t activation_clock_receive_ns;
  double activation_rtf;
} usv_research_interfaces__msg__ExecutionDecision;

// Struct for a sequence of usv_research_interfaces__msg__ExecutionDecision.
typedef struct usv_research_interfaces__msg__ExecutionDecision__Sequence
{
  usv_research_interfaces__msg__ExecutionDecision * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} usv_research_interfaces__msg__ExecutionDecision__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__EXECUTION_DECISION__STRUCT_H_
