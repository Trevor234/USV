// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from usv_research_interfaces:msg/WorkerCapability.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/worker_capability.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__WORKER_CAPABILITY__TRAITS_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__WORKER_CAPABILITY__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "usv_research_interfaces/msg/detail/worker_capability__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace usv_research_interfaces
{

namespace msg
{

inline void to_flow_style_yaml(
  const WorkerCapability & msg,
  std::ostream & out)
{
  out << "{";
  // member: schema_version
  {
    out << "schema_version: ";
    rosidl_generator_traits::value_to_yaml(msg.schema_version, out);
    out << ", ";
  }

  // member: run_id
  {
    out << "run_id: ";
    rosidl_generator_traits::value_to_yaml(msg.run_id, out);
    out << ", ";
  }

  // member: boot_id
  {
    out << "boot_id: ";
    rosidl_generator_traits::value_to_yaml(msg.boot_id, out);
    out << ", ";
  }

  // member: contract_hash
  {
    out << "contract_hash: ";
    rosidl_generator_traits::value_to_yaml(msg.contract_hash, out);
    out << ", ";
  }

  // member: nominal_hash
  {
    out << "nominal_hash: ";
    rosidl_generator_traits::value_to_yaml(msg.nominal_hash, out);
    out << ", ";
  }

  // member: worker_instance
  {
    out << "worker_instance: ";
    rosidl_generator_traits::value_to_yaml(msg.worker_instance, out);
    out << ", ";
  }

  // member: clock_name
  {
    out << "clock_name: ";
    rosidl_generator_traits::value_to_yaml(msg.clock_name, out);
    out << ", ";
  }

  // member: backend
  {
    out << "backend: ";
    rosidl_generator_traits::value_to_yaml(msg.backend, out);
    out << ", ";
  }

  // member: matrix_layout
  {
    out << "matrix_layout: ";
    rosidl_generator_traits::value_to_yaml(msg.matrix_layout, out);
    out << ", ";
  }

  // member: horizon_steps
  {
    out << "horizon_steps: ";
    rosidl_generator_traits::value_to_yaml(msg.horizon_steps, out);
    out << ", ";
  }

  // member: prediction_dt
  {
    out << "prediction_dt: ";
    rosidl_generator_traits::value_to_yaml(msg.prediction_dt, out);
    out << ", ";
  }

  // member: pid
  {
    out << "pid: ";
    rosidl_generator_traits::value_to_yaml(msg.pid, out);
    out << ", ";
  }

  // member: startup_ns
  {
    out << "startup_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.startup_ns, out);
    out << ", ";
  }

  // member: completed_jobs
  {
    out << "completed_jobs: ";
    rosidl_generator_traits::value_to_yaml(msg.completed_jobs, out);
    out << ", ";
  }

  // member: active_job
  {
    out << "active_job: ";
    rosidl_generator_traits::value_to_yaml(msg.active_job, out);
    out << ", ";
  }

  // member: pending_count
  {
    out << "pending_count: ";
    rosidl_generator_traits::value_to_yaml(msg.pending_count, out);
    out << ", ";
  }

  // member: fault_injection_enabled
  {
    out << "fault_injection_enabled: ";
    rosidl_generator_traits::value_to_yaml(msg.fault_injection_enabled, out);
    out << ", ";
  }

  // member: fatal
  {
    out << "fatal: ";
    rosidl_generator_traits::value_to_yaml(msg.fatal, out);
    out << ", ";
  }

  // member: reason
  {
    out << "reason: ";
    rosidl_generator_traits::value_to_yaml(msg.reason, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const WorkerCapability & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: schema_version
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "schema_version: ";
    rosidl_generator_traits::value_to_yaml(msg.schema_version, out);
    out << "\n";
  }

  // member: run_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "run_id: ";
    rosidl_generator_traits::value_to_yaml(msg.run_id, out);
    out << "\n";
  }

  // member: boot_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "boot_id: ";
    rosidl_generator_traits::value_to_yaml(msg.boot_id, out);
    out << "\n";
  }

  // member: contract_hash
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "contract_hash: ";
    rosidl_generator_traits::value_to_yaml(msg.contract_hash, out);
    out << "\n";
  }

  // member: nominal_hash
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "nominal_hash: ";
    rosidl_generator_traits::value_to_yaml(msg.nominal_hash, out);
    out << "\n";
  }

  // member: worker_instance
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "worker_instance: ";
    rosidl_generator_traits::value_to_yaml(msg.worker_instance, out);
    out << "\n";
  }

  // member: clock_name
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "clock_name: ";
    rosidl_generator_traits::value_to_yaml(msg.clock_name, out);
    out << "\n";
  }

  // member: backend
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "backend: ";
    rosidl_generator_traits::value_to_yaml(msg.backend, out);
    out << "\n";
  }

  // member: matrix_layout
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "matrix_layout: ";
    rosidl_generator_traits::value_to_yaml(msg.matrix_layout, out);
    out << "\n";
  }

  // member: horizon_steps
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "horizon_steps: ";
    rosidl_generator_traits::value_to_yaml(msg.horizon_steps, out);
    out << "\n";
  }

  // member: prediction_dt
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "prediction_dt: ";
    rosidl_generator_traits::value_to_yaml(msg.prediction_dt, out);
    out << "\n";
  }

  // member: pid
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "pid: ";
    rosidl_generator_traits::value_to_yaml(msg.pid, out);
    out << "\n";
  }

  // member: startup_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "startup_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.startup_ns, out);
    out << "\n";
  }

  // member: completed_jobs
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "completed_jobs: ";
    rosidl_generator_traits::value_to_yaml(msg.completed_jobs, out);
    out << "\n";
  }

  // member: active_job
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "active_job: ";
    rosidl_generator_traits::value_to_yaml(msg.active_job, out);
    out << "\n";
  }

  // member: pending_count
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "pending_count: ";
    rosidl_generator_traits::value_to_yaml(msg.pending_count, out);
    out << "\n";
  }

  // member: fault_injection_enabled
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "fault_injection_enabled: ";
    rosidl_generator_traits::value_to_yaml(msg.fault_injection_enabled, out);
    out << "\n";
  }

  // member: fatal
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "fatal: ";
    rosidl_generator_traits::value_to_yaml(msg.fatal, out);
    out << "\n";
  }

  // member: reason
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "reason: ";
    rosidl_generator_traits::value_to_yaml(msg.reason, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const WorkerCapability & msg, bool use_flow_style = false)
{
  std::ostringstream out;
  if (use_flow_style) {
    to_flow_style_yaml(msg, out);
  } else {
    to_block_style_yaml(msg, out);
  }
  return out.str();
}

}  // namespace msg

}  // namespace usv_research_interfaces

namespace rosidl_generator_traits
{

[[deprecated("use usv_research_interfaces::msg::to_block_style_yaml() instead")]]
inline void to_yaml(
  const usv_research_interfaces::msg::WorkerCapability & msg,
  std::ostream & out, size_t indentation = 0)
{
  usv_research_interfaces::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use usv_research_interfaces::msg::to_yaml() instead")]]
inline std::string to_yaml(const usv_research_interfaces::msg::WorkerCapability & msg)
{
  return usv_research_interfaces::msg::to_yaml(msg);
}

template<>
inline const char * data_type<usv_research_interfaces::msg::WorkerCapability>()
{
  return "usv_research_interfaces::msg::WorkerCapability";
}

template<>
inline const char * name<usv_research_interfaces::msg::WorkerCapability>()
{
  return "usv_research_interfaces/msg/WorkerCapability";
}

template<>
struct has_fixed_size<usv_research_interfaces::msg::WorkerCapability>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<usv_research_interfaces::msg::WorkerCapability>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<usv_research_interfaces::msg::WorkerCapability>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__WORKER_CAPABILITY__TRAITS_HPP_
