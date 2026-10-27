// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from usv_research_interfaces:msg/SolveCandidate.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/solve_candidate.h"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_CANDIDATE__STRUCT_H_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_CANDIDATE__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Constants defined in the message

// Include directives for member types
// Member 'job'
#include "usv_research_interfaces/msg/detail/solve_job__struct.h"
// Member 'worker_instance'
// Member 'reason'
// Member 'backend'
#include "rosidl_runtime_c/string.h"

// constants for array fields with an upper bound
// worker_instance
enum
{
  usv_research_interfaces__msg__SolveCandidate__worker_instance__MAX_STRING_SIZE = 64
};
// reason
enum
{
  usv_research_interfaces__msg__SolveCandidate__reason__MAX_STRING_SIZE = 256
};
// backend
enum
{
  usv_research_interfaces__msg__SolveCandidate__backend__MAX_STRING_SIZE = 16
};

/// Struct defined in msg/SolveCandidate in the package usv_research_interfaces.
typedef struct usv_research_interfaces__msg__SolveCandidate
{
  usv_research_interfaces__msg__SolveJob job;
  rosidl_runtime_c__String worker_instance;
  int64_t worker_receive_ns;
  int64_t solve_start_ns;
  int64_t solve_end_ns;
  bool solver_invoked;
  bool success;
  bool prediction_available;
  rosidl_runtime_c__String reason;
  rosidl_runtime_c__String backend;
  double backend_ms;
  double first_control[2];
  double x_prediction[126];
  double u_prediction[40];
} usv_research_interfaces__msg__SolveCandidate;

// Struct for a sequence of usv_research_interfaces__msg__SolveCandidate.
typedef struct usv_research_interfaces__msg__SolveCandidate__Sequence
{
  usv_research_interfaces__msg__SolveCandidate * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} usv_research_interfaces__msg__SolveCandidate__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_CANDIDATE__STRUCT_H_
