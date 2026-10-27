// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from usv_research_interfaces:msg/WorkerCapability.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/worker_capability.h"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__WORKER_CAPABILITY__STRUCT_H_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__WORKER_CAPABILITY__STRUCT_H_

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
// Member 'clock_name'
// Member 'backend'
// Member 'matrix_layout'
// Member 'reason'
#include "rosidl_runtime_c/string.h"

// constants for array fields with an upper bound
// schema_version
enum
{
  usv_research_interfaces__msg__WorkerCapability__schema_version__MAX_STRING_SIZE = 64
};
// run_id
enum
{
  usv_research_interfaces__msg__WorkerCapability__run_id__MAX_STRING_SIZE = 128
};
// boot_id
enum
{
  usv_research_interfaces__msg__WorkerCapability__boot_id__MAX_STRING_SIZE = 64
};
// contract_hash
enum
{
  usv_research_interfaces__msg__WorkerCapability__contract_hash__MAX_STRING_SIZE = 64
};
// nominal_hash
enum
{
  usv_research_interfaces__msg__WorkerCapability__nominal_hash__MAX_STRING_SIZE = 64
};
// worker_instance
enum
{
  usv_research_interfaces__msg__WorkerCapability__worker_instance__MAX_STRING_SIZE = 64
};
// clock_name
enum
{
  usv_research_interfaces__msg__WorkerCapability__clock_name__MAX_STRING_SIZE = 32
};
// backend
enum
{
  usv_research_interfaces__msg__WorkerCapability__backend__MAX_STRING_SIZE = 16
};
// matrix_layout
enum
{
  usv_research_interfaces__msg__WorkerCapability__matrix_layout__MAX_STRING_SIZE = 32
};
// reason
enum
{
  usv_research_interfaces__msg__WorkerCapability__reason__MAX_STRING_SIZE = 256
};

/// Struct defined in msg/WorkerCapability in the package usv_research_interfaces.
typedef struct usv_research_interfaces__msg__WorkerCapability
{
  rosidl_runtime_c__String schema_version;
  rosidl_runtime_c__String run_id;
  rosidl_runtime_c__String boot_id;
  rosidl_runtime_c__String contract_hash;
  rosidl_runtime_c__String nominal_hash;
  rosidl_runtime_c__String worker_instance;
  rosidl_runtime_c__String clock_name;
  rosidl_runtime_c__String backend;
  rosidl_runtime_c__String matrix_layout;
  uint32_t horizon_steps;
  double prediction_dt;
  int64_t pid;
  int64_t startup_ns;
  uint64_t completed_jobs;
  uint64_t active_job;
  uint32_t pending_count;
  bool fault_injection_enabled;
  bool fatal;
  rosidl_runtime_c__String reason;
} usv_research_interfaces__msg__WorkerCapability;

// Struct for a sequence of usv_research_interfaces__msg__WorkerCapability.
typedef struct usv_research_interfaces__msg__WorkerCapability__Sequence
{
  usv_research_interfaces__msg__WorkerCapability * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} usv_research_interfaces__msg__WorkerCapability__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__WORKER_CAPABILITY__STRUCT_H_
