// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from usv_research_interfaces:msg/SolveJob.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/solve_job.h"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__STRUCT_H_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__STRUCT_H_

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
// Member 'nominal_hash'
// Member 'worker_instance'
// Member 'anchor_source'
// Member 'anchor_producer'
// Member 'anchor_run_id'
#include "rosidl_runtime_c/string.h"
// Member 'history_sim_ns'
// Member 'history_channel'
// Member 'history_n'
#include "rosidl_runtime_c/primitives_sequence.h"

// constants for array fields with an upper bound
// schema_version
enum
{
  usv_research_interfaces__msg__SolveJob__schema_version__MAX_STRING_SIZE = 64
};
// run_id
enum
{
  usv_research_interfaces__msg__SolveJob__run_id__MAX_STRING_SIZE = 128
};
// boot_id
enum
{
  usv_research_interfaces__msg__SolveJob__boot_id__MAX_STRING_SIZE = 64
};
// contract_hash
enum
{
  usv_research_interfaces__msg__SolveJob__contract_hash__MAX_STRING_SIZE = 64
};
// nominal_hash
enum
{
  usv_research_interfaces__msg__SolveJob__nominal_hash__MAX_STRING_SIZE = 64
};
// worker_instance
enum
{
  usv_research_interfaces__msg__SolveJob__worker_instance__MAX_STRING_SIZE = 64
};
// anchor_source
enum
{
  usv_research_interfaces__msg__SolveJob__anchor_source__MAX_STRING_SIZE = 32
};
// anchor_producer
enum
{
  usv_research_interfaces__msg__SolveJob__anchor_producer__MAX_STRING_SIZE = 64
};
// anchor_run_id
enum
{
  usv_research_interfaces__msg__SolveJob__anchor_run_id__MAX_STRING_SIZE = 128
};
// history_sim_ns
enum
{
  usv_research_interfaces__msg__SolveJob__history_sim_ns__MAX_SIZE = 256
};
// history_channel
enum
{
  usv_research_interfaces__msg__SolveJob__history_channel__MAX_SIZE = 256
};
// history_n
enum
{
  usv_research_interfaces__msg__SolveJob__history_n__MAX_SIZE = 256
};

/// Struct defined in msg/SolveJob in the package usv_research_interfaces.
/**
  * Fixed F5 dimensions; column-major.
 */
typedef struct usv_research_interfaces__msg__SolveJob
{
  rosidl_runtime_c__String schema_version;
  rosidl_runtime_c__String run_id;
  rosidl_runtime_c__String boot_id;
  rosidl_runtime_c__String contract_hash;
  rosidl_runtime_c__String nominal_hash;
  rosidl_runtime_c__String worker_instance;
  uint64_t job_id;
  uint64_t target_tick;
  uint64_t task_generation;
  uint64_t model_generation;
  uint64_t config_generation;
  uint64_t schedule_generation;
  uint64_t clock_epoch;
  int64_t tick_origin_steady_ns;
  int64_t freeze_steady_ns;
  int64_t deadline_steady_ns;
  int64_t target_steady_ns;
  int64_t target_sim_ns;
  int64_t odom_stamp_ns;
  int64_t imu_stamp_ns;
  int64_t odom_receive_ns;
  int64_t imu_receive_ns;
  uint64_t odom_sequence;
  uint64_t imu_sequence;
  bool r_from_imu;
  uint32_t horizon_steps;
  double prediction_dt;
  double frozen_state[6];
  double target_state[6];
  double reference[126];
  double anchor_n[2];
  uint64_t anchor_sequence[2];
  int64_t anchor_publish_ns[2];
  bool anchor_known[2];
  bool reset_warmstart;
  int64_t frozen_clock_sim_ns;
  int64_t frozen_clock_receive_ns;
  double assumed_rtf;
  rosidl_runtime_c__String anchor_source;
  rosidl_runtime_c__String anchor_producer;
  rosidl_runtime_c__String anchor_run_id;
  rosidl_runtime_c__int64__Sequence history_sim_ns;
  rosidl_runtime_c__uint8__Sequence history_channel;
  rosidl_runtime_c__double__Sequence history_n;
} usv_research_interfaces__msg__SolveJob;

// Struct for a sequence of usv_research_interfaces__msg__SolveJob.
typedef struct usv_research_interfaces__msg__SolveJob__Sequence
{
  usv_research_interfaces__msg__SolveJob * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} usv_research_interfaces__msg__SolveJob__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__STRUCT_H_
