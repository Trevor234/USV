// generated from rosidl_typesupport_fastrtps_cpp/resource/idl__rosidl_typesupport_fastrtps_cpp.hpp.em
// with input from usv_research_interfaces:msg/SolveJob.idl
// generated code does not contain a copyright notice

#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__ROSIDL_TYPESUPPORT_FASTRTPS_CPP_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__ROSIDL_TYPESUPPORT_FASTRTPS_CPP_HPP_

#include <cstddef>
#include "rosidl_runtime_c/message_type_support_struct.h"
#include "rosidl_typesupport_interface/macros.h"
#include "usv_research_interfaces/msg/rosidl_typesupport_fastrtps_cpp__visibility_control.h"
#include "usv_research_interfaces/msg/detail/solve_job__struct.hpp"

#ifndef _WIN32
# pragma GCC diagnostic push
# pragma GCC diagnostic ignored "-Wunused-parameter"
# ifdef __clang__
#  pragma clang diagnostic ignored "-Wdeprecated-register"
#  pragma clang diagnostic ignored "-Wreturn-type-c-linkage"
# endif
#endif
#ifndef _WIN32
# pragma GCC diagnostic pop
#endif

#include "fastcdr/Cdr.h"

namespace usv_research_interfaces
{

namespace msg
{

namespace typesupport_fastrtps_cpp
{

bool
ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_usv_research_interfaces
cdr_serialize(
  const usv_research_interfaces::msg::SolveJob & ros_message,
  eprosima::fastcdr::Cdr & cdr);

bool
ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_usv_research_interfaces
cdr_deserialize(
  eprosima::fastcdr::Cdr & cdr,
  usv_research_interfaces::msg::SolveJob & ros_message);

size_t
ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_usv_research_interfaces
get_serialized_size(
  const usv_research_interfaces::msg::SolveJob & ros_message,
  size_t current_alignment);

size_t
ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_usv_research_interfaces
max_serialized_size_SolveJob(
  bool & full_bounded,
  bool & is_plain,
  size_t current_alignment);

bool
ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_usv_research_interfaces
cdr_serialize_key(
  const usv_research_interfaces::msg::SolveJob & ros_message,
  eprosima::fastcdr::Cdr &);

size_t
ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_usv_research_interfaces
get_serialized_size_key(
  const usv_research_interfaces::msg::SolveJob & ros_message,
  size_t current_alignment);

size_t
ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_usv_research_interfaces
max_serialized_size_key_SolveJob(
  bool & full_bounded,
  bool & is_plain,
  size_t current_alignment);

}  // namespace typesupport_fastrtps_cpp

}  // namespace msg

}  // namespace usv_research_interfaces

#ifdef __cplusplus
extern "C"
{
#endif

ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_usv_research_interfaces
const rosidl_message_type_support_t *
  ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_fastrtps_cpp, usv_research_interfaces, msg, SolveJob)();

#ifdef __cplusplus
}
#endif

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__ROSIDL_TYPESUPPORT_FASTRTPS_CPP_HPP_
