// generated from rosidl_typesupport_fastrtps_c/resource/idl__rosidl_typesupport_fastrtps_c.h.em
// with input from usv_research_interfaces:msg/SolveJob.idl
// generated code does not contain a copyright notice
#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__ROSIDL_TYPESUPPORT_FASTRTPS_C_H_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__ROSIDL_TYPESUPPORT_FASTRTPS_C_H_


#include <stddef.h>
#include "rosidl_runtime_c/message_type_support_struct.h"
#include "rosidl_typesupport_interface/macros.h"
#include "usv_research_interfaces/msg/rosidl_typesupport_fastrtps_c__visibility_control.h"
#include "usv_research_interfaces/msg/detail/solve_job__struct.h"
#include "fastcdr/Cdr.h"

#ifdef __cplusplus
extern "C"
{
#endif

ROSIDL_TYPESUPPORT_FASTRTPS_C_PUBLIC_usv_research_interfaces
bool cdr_serialize_usv_research_interfaces__msg__SolveJob(
  const usv_research_interfaces__msg__SolveJob * ros_message,
  eprosima::fastcdr::Cdr & cdr);

ROSIDL_TYPESUPPORT_FASTRTPS_C_PUBLIC_usv_research_interfaces
bool cdr_deserialize_usv_research_interfaces__msg__SolveJob(
  eprosima::fastcdr::Cdr &,
  usv_research_interfaces__msg__SolveJob * ros_message);

ROSIDL_TYPESUPPORT_FASTRTPS_C_PUBLIC_usv_research_interfaces
size_t get_serialized_size_usv_research_interfaces__msg__SolveJob(
  const void * untyped_ros_message,
  size_t current_alignment);

ROSIDL_TYPESUPPORT_FASTRTPS_C_PUBLIC_usv_research_interfaces
size_t max_serialized_size_usv_research_interfaces__msg__SolveJob(
  bool & full_bounded,
  bool & is_plain,
  size_t current_alignment);

ROSIDL_TYPESUPPORT_FASTRTPS_C_PUBLIC_usv_research_interfaces
bool cdr_serialize_key_usv_research_interfaces__msg__SolveJob(
  const usv_research_interfaces__msg__SolveJob * ros_message,
  eprosima::fastcdr::Cdr & cdr);

ROSIDL_TYPESUPPORT_FASTRTPS_C_PUBLIC_usv_research_interfaces
size_t get_serialized_size_key_usv_research_interfaces__msg__SolveJob(
  const void * untyped_ros_message,
  size_t current_alignment);

ROSIDL_TYPESUPPORT_FASTRTPS_C_PUBLIC_usv_research_interfaces
size_t max_serialized_size_key_usv_research_interfaces__msg__SolveJob(
  bool & full_bounded,
  bool & is_plain,
  size_t current_alignment);

ROSIDL_TYPESUPPORT_FASTRTPS_C_PUBLIC_usv_research_interfaces
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_fastrtps_c, usv_research_interfaces, msg, SolveJob)();

#ifdef __cplusplus
}
#endif

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__ROSIDL_TYPESUPPORT_FASTRTPS_C_H_
