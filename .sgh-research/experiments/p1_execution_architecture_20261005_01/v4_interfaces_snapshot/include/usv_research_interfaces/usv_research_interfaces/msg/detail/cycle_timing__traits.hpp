// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from usv_research_interfaces:msg/CycleTiming.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/cycle_timing.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__CYCLE_TIMING__TRAITS_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__CYCLE_TIMING__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "usv_research_interfaces/msg/detail/cycle_timing__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace usv_research_interfaces
{

namespace msg
{

inline void to_flow_style_yaml(
  const CycleTiming & msg,
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

  // member: producer_instance_id
  {
    out << "producer_instance_id: ";
    rosidl_generator_traits::value_to_yaml(msg.producer_instance_id, out);
    out << ", ";
  }

  // member: baseline_id
  {
    out << "baseline_id: ";
    rosidl_generator_traits::value_to_yaml(msg.baseline_id, out);
    out << ", ";
  }

  // member: config_hash
  {
    out << "config_hash: ";
    rosidl_generator_traits::value_to_yaml(msg.config_hash, out);
    out << ", ";
  }

  // member: sequence
  {
    out << "sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.sequence, out);
    out << ", ";
  }

  // member: clock_epoch
  {
    out << "clock_epoch: ";
    rosidl_generator_traits::value_to_yaml(msg.clock_epoch, out);
    out << ", ";
  }

  // member: sim_time_ns
  {
    out << "sim_time_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.sim_time_ns, out);
    out << ", ";
  }

  // member: clock_receive_steady_ns
  {
    out << "clock_receive_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.clock_receive_steady_ns, out);
    out << ", ";
  }

  // member: clock_age_ns
  {
    out << "clock_age_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.clock_age_ns, out);
    out << ", ";
  }

  // member: clock_status
  {
    out << "clock_status: ";
    rosidl_generator_traits::value_to_yaml(msg.clock_status, out);
    out << ", ";
  }

  // member: steady_clock_domain
  {
    out << "steady_clock_domain: ";
    rosidl_generator_traits::value_to_yaml(msg.steady_clock_domain, out);
    out << ", ";
  }

  // member: timer_entry_steady_ns
  {
    out << "timer_entry_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.timer_entry_steady_ns, out);
    out << ", ";
  }

  // member: state_copy_steady_ns
  {
    out << "state_copy_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.state_copy_steady_ns, out);
    out << ", ";
  }

  // member: reference_ready_steady_ns
  {
    out << "reference_ready_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.reference_ready_steady_ns, out);
    out << ", ";
  }

  // member: solve_start_steady_ns
  {
    out << "solve_start_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.solve_start_steady_ns, out);
    out << ", ";
  }

  // member: solve_end_steady_ns
  {
    out << "solve_end_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.solve_end_steady_ns, out);
    out << ", ";
  }

  // member: publish_end_steady_ns
  {
    out << "publish_end_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.publish_end_steady_ns, out);
    out << ", ";
  }

  // member: controller_state_6
  {
    if (msg.controller_state_6.size() == 0) {
      out << "controller_state_6: []";
    } else {
      out << "controller_state_6: [";
      size_t pending_items = msg.controller_state_6.size();
      for (auto item : msg.controller_state_6) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: state_kind
  {
    out << "state_kind: ";
    rosidl_generator_traits::value_to_yaml(msg.state_kind, out);
    out << ", ";
  }

  // member: received_odom_sequence
  {
    out << "received_odom_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.received_odom_sequence, out);
    out << ", ";
  }

  // member: received_imu_sequence
  {
    out << "received_imu_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.received_imu_sequence, out);
    out << ", ";
  }

  // member: odom_stamp_ns
  {
    out << "odom_stamp_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.odom_stamp_ns, out);
    out << ", ";
  }

  // member: imu_stamp_ns
  {
    out << "imu_stamp_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.imu_stamp_ns, out);
    out << ", ";
  }

  // member: backend_time_ms
  {
    out << "backend_time_ms: ";
    rosidl_generator_traits::value_to_yaml(msg.backend_time_ms, out);
    out << ", ";
  }

  // member: budget_ms
  {
    out << "budget_ms: ";
    rosidl_generator_traits::value_to_yaml(msg.budget_ms, out);
    out << ", ";
  }

  // member: success
  {
    out << "success: ";
    rosidl_generator_traits::value_to_yaml(msg.success, out);
    out << ", ";
  }

  // member: deadline_miss
  {
    out << "deadline_miss: ";
    rosidl_generator_traits::value_to_yaml(msg.deadline_miss, out);
    out << ", ";
  }

  // member: rejection_reason
  {
    out << "rejection_reason: ";
    rosidl_generator_traits::value_to_yaml(msg.rejection_reason, out);
    out << ", ";
  }

  // member: applied_sequence
  {
    out << "applied_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.applied_sequence, out);
    out << ", ";
  }

  // member: solve_invoked
  {
    out << "solve_invoked: ";
    rosidl_generator_traits::value_to_yaml(msg.solve_invoked, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const CycleTiming & msg,
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

  // member: producer_instance_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "producer_instance_id: ";
    rosidl_generator_traits::value_to_yaml(msg.producer_instance_id, out);
    out << "\n";
  }

  // member: baseline_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "baseline_id: ";
    rosidl_generator_traits::value_to_yaml(msg.baseline_id, out);
    out << "\n";
  }

  // member: config_hash
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "config_hash: ";
    rosidl_generator_traits::value_to_yaml(msg.config_hash, out);
    out << "\n";
  }

  // member: sequence
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.sequence, out);
    out << "\n";
  }

  // member: clock_epoch
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "clock_epoch: ";
    rosidl_generator_traits::value_to_yaml(msg.clock_epoch, out);
    out << "\n";
  }

  // member: sim_time_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "sim_time_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.sim_time_ns, out);
    out << "\n";
  }

  // member: clock_receive_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "clock_receive_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.clock_receive_steady_ns, out);
    out << "\n";
  }

  // member: clock_age_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "clock_age_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.clock_age_ns, out);
    out << "\n";
  }

  // member: clock_status
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "clock_status: ";
    rosidl_generator_traits::value_to_yaml(msg.clock_status, out);
    out << "\n";
  }

  // member: steady_clock_domain
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "steady_clock_domain: ";
    rosidl_generator_traits::value_to_yaml(msg.steady_clock_domain, out);
    out << "\n";
  }

  // member: timer_entry_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "timer_entry_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.timer_entry_steady_ns, out);
    out << "\n";
  }

  // member: state_copy_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "state_copy_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.state_copy_steady_ns, out);
    out << "\n";
  }

  // member: reference_ready_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "reference_ready_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.reference_ready_steady_ns, out);
    out << "\n";
  }

  // member: solve_start_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "solve_start_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.solve_start_steady_ns, out);
    out << "\n";
  }

  // member: solve_end_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "solve_end_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.solve_end_steady_ns, out);
    out << "\n";
  }

  // member: publish_end_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "publish_end_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.publish_end_steady_ns, out);
    out << "\n";
  }

  // member: controller_state_6
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.controller_state_6.size() == 0) {
      out << "controller_state_6: []\n";
    } else {
      out << "controller_state_6:\n";
      for (auto item : msg.controller_state_6) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: state_kind
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "state_kind: ";
    rosidl_generator_traits::value_to_yaml(msg.state_kind, out);
    out << "\n";
  }

  // member: received_odom_sequence
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "received_odom_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.received_odom_sequence, out);
    out << "\n";
  }

  // member: received_imu_sequence
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "received_imu_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.received_imu_sequence, out);
    out << "\n";
  }

  // member: odom_stamp_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "odom_stamp_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.odom_stamp_ns, out);
    out << "\n";
  }

  // member: imu_stamp_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "imu_stamp_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.imu_stamp_ns, out);
    out << "\n";
  }

  // member: backend_time_ms
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "backend_time_ms: ";
    rosidl_generator_traits::value_to_yaml(msg.backend_time_ms, out);
    out << "\n";
  }

  // member: budget_ms
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "budget_ms: ";
    rosidl_generator_traits::value_to_yaml(msg.budget_ms, out);
    out << "\n";
  }

  // member: success
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "success: ";
    rosidl_generator_traits::value_to_yaml(msg.success, out);
    out << "\n";
  }

  // member: deadline_miss
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "deadline_miss: ";
    rosidl_generator_traits::value_to_yaml(msg.deadline_miss, out);
    out << "\n";
  }

  // member: rejection_reason
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "rejection_reason: ";
    rosidl_generator_traits::value_to_yaml(msg.rejection_reason, out);
    out << "\n";
  }

  // member: applied_sequence
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "applied_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.applied_sequence, out);
    out << "\n";
  }

  // member: solve_invoked
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "solve_invoked: ";
    rosidl_generator_traits::value_to_yaml(msg.solve_invoked, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const CycleTiming & msg, bool use_flow_style = false)
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
  const usv_research_interfaces::msg::CycleTiming & msg,
  std::ostream & out, size_t indentation = 0)
{
  usv_research_interfaces::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use usv_research_interfaces::msg::to_yaml() instead")]]
inline std::string to_yaml(const usv_research_interfaces::msg::CycleTiming & msg)
{
  return usv_research_interfaces::msg::to_yaml(msg);
}

template<>
inline const char * data_type<usv_research_interfaces::msg::CycleTiming>()
{
  return "usv_research_interfaces::msg::CycleTiming";
}

template<>
inline const char * name<usv_research_interfaces::msg::CycleTiming>()
{
  return "usv_research_interfaces/msg/CycleTiming";
}

template<>
struct has_fixed_size<usv_research_interfaces::msg::CycleTiming>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<usv_research_interfaces::msg::CycleTiming>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<usv_research_interfaces::msg::CycleTiming>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__CYCLE_TIMING__TRAITS_HPP_
