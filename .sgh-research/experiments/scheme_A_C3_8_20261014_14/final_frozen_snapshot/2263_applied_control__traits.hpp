// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from usv_research_interfaces:msg/AppliedControl.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/applied_control.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__APPLIED_CONTROL__TRAITS_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__APPLIED_CONTROL__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "usv_research_interfaces/msg/detail/applied_control__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace usv_research_interfaces
{

namespace msg
{

inline void to_flow_style_yaml(
  const AppliedControl & msg,
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

  // member: cycle_sequence
  {
    out << "cycle_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.cycle_sequence, out);
    out << ", ";
  }

  // member: control_source
  {
    out << "control_source: ";
    rosidl_generator_traits::value_to_yaml(msg.control_source, out);
    out << ", ";
  }

  // member: event_semantics
  {
    out << "event_semantics: ";
    rosidl_generator_traits::value_to_yaml(msg.event_semantics, out);
    out << ", ";
  }

  // member: requested_known
  {
    out << "requested_known: ";
    rosidl_generator_traits::value_to_yaml(msg.requested_known, out);
    out << ", ";
  }

  // member: requested_n
  {
    if (msg.requested_n.size() == 0) {
      out << "requested_n: []";
    } else {
      out << "requested_n: [";
      size_t pending_items = msg.requested_n.size();
      for (auto item : msg.requested_n) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: final_n
  {
    if (msg.final_n.size() == 0) {
      out << "final_n: []";
    } else {
      out << "final_n: [";
      size_t pending_items = msg.final_n.size();
      for (auto item : msg.final_n) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: left_publish_success
  {
    out << "left_publish_success: ";
    rosidl_generator_traits::value_to_yaml(msg.left_publish_success, out);
    out << ", ";
  }

  // member: right_publish_success
  {
    out << "right_publish_success: ";
    rosidl_generator_traits::value_to_yaml(msg.right_publish_success, out);
    out << ", ";
  }

  // member: left_publish_start_steady_ns
  {
    out << "left_publish_start_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.left_publish_start_steady_ns, out);
    out << ", ";
  }

  // member: left_publish_end_steady_ns
  {
    out << "left_publish_end_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.left_publish_end_steady_ns, out);
    out << ", ";
  }

  // member: right_publish_start_steady_ns
  {
    out << "right_publish_start_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.right_publish_start_steady_ns, out);
    out << ", ";
  }

  // member: right_publish_end_steady_ns
  {
    out << "right_publish_end_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.right_publish_end_steady_ns, out);
    out << ", ";
  }

  // member: left_sim_time_ns
  {
    out << "left_sim_time_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.left_sim_time_ns, out);
    out << ", ";
  }

  // member: right_sim_time_ns
  {
    out << "right_sim_time_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.right_sim_time_ns, out);
    out << ", ";
  }

  // member: left_clock_epoch
  {
    out << "left_clock_epoch: ";
    rosidl_generator_traits::value_to_yaml(msg.left_clock_epoch, out);
    out << ", ";
  }

  // member: right_clock_epoch
  {
    out << "right_clock_epoch: ";
    rosidl_generator_traits::value_to_yaml(msg.right_clock_epoch, out);
    out << ", ";
  }

  // member: left_clock_age_ns
  {
    out << "left_clock_age_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.left_clock_age_ns, out);
    out << ", ";
  }

  // member: right_clock_age_ns
  {
    out << "right_clock_age_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.right_clock_age_ns, out);
    out << ", ";
  }

  // member: map_scale
  {
    out << "map_scale: ";
    rosidl_generator_traits::value_to_yaml(msg.map_scale, out);
    out << ", ";
  }

  // member: lower_n
  {
    out << "lower_n: ";
    rosidl_generator_traits::value_to_yaml(msg.lower_n, out);
    out << ", ";
  }

  // member: upper_n
  {
    out << "upper_n: ";
    rosidl_generator_traits::value_to_yaml(msg.upper_n, out);
    out << ", ";
  }

  // member: previous_anchor_known
  {
    out << "previous_anchor_known: ";
    rosidl_generator_traits::value_to_yaml(msg.previous_anchor_known, out);
    out << ", ";
  }

  // member: previous_final_n
  {
    if (msg.previous_final_n.size() == 0) {
      out << "previous_final_n: []";
    } else {
      out << "previous_final_n: [";
      size_t pending_items = msg.previous_final_n.size();
      for (auto item : msg.previous_final_n) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: plant_acceptance_observed
  {
    out << "plant_acceptance_observed: ";
    rosidl_generator_traits::value_to_yaml(msg.plant_acceptance_observed, out);
    out << ", ";
  }

  // member: force_measured
  {
    out << "force_measured: ";
    rosidl_generator_traits::value_to_yaml(msg.force_measured, out);
    out << ", ";
  }

  // member: execution_atomicity_proven
  {
    out << "execution_atomicity_proven: ";
    rosidl_generator_traits::value_to_yaml(msg.execution_atomicity_proven, out);
    out << ", ";
  }

  // member: publish_error
  {
    out << "publish_error: ";
    rosidl_generator_traits::value_to_yaml(msg.publish_error, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const AppliedControl & msg,
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

  // member: cycle_sequence
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "cycle_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.cycle_sequence, out);
    out << "\n";
  }

  // member: control_source
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "control_source: ";
    rosidl_generator_traits::value_to_yaml(msg.control_source, out);
    out << "\n";
  }

  // member: event_semantics
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "event_semantics: ";
    rosidl_generator_traits::value_to_yaml(msg.event_semantics, out);
    out << "\n";
  }

  // member: requested_known
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "requested_known: ";
    rosidl_generator_traits::value_to_yaml(msg.requested_known, out);
    out << "\n";
  }

  // member: requested_n
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.requested_n.size() == 0) {
      out << "requested_n: []\n";
    } else {
      out << "requested_n:\n";
      for (auto item : msg.requested_n) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: final_n
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.final_n.size() == 0) {
      out << "final_n: []\n";
    } else {
      out << "final_n:\n";
      for (auto item : msg.final_n) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: left_publish_success
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "left_publish_success: ";
    rosidl_generator_traits::value_to_yaml(msg.left_publish_success, out);
    out << "\n";
  }

  // member: right_publish_success
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "right_publish_success: ";
    rosidl_generator_traits::value_to_yaml(msg.right_publish_success, out);
    out << "\n";
  }

  // member: left_publish_start_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "left_publish_start_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.left_publish_start_steady_ns, out);
    out << "\n";
  }

  // member: left_publish_end_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "left_publish_end_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.left_publish_end_steady_ns, out);
    out << "\n";
  }

  // member: right_publish_start_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "right_publish_start_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.right_publish_start_steady_ns, out);
    out << "\n";
  }

  // member: right_publish_end_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "right_publish_end_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.right_publish_end_steady_ns, out);
    out << "\n";
  }

  // member: left_sim_time_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "left_sim_time_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.left_sim_time_ns, out);
    out << "\n";
  }

  // member: right_sim_time_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "right_sim_time_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.right_sim_time_ns, out);
    out << "\n";
  }

  // member: left_clock_epoch
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "left_clock_epoch: ";
    rosidl_generator_traits::value_to_yaml(msg.left_clock_epoch, out);
    out << "\n";
  }

  // member: right_clock_epoch
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "right_clock_epoch: ";
    rosidl_generator_traits::value_to_yaml(msg.right_clock_epoch, out);
    out << "\n";
  }

  // member: left_clock_age_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "left_clock_age_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.left_clock_age_ns, out);
    out << "\n";
  }

  // member: right_clock_age_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "right_clock_age_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.right_clock_age_ns, out);
    out << "\n";
  }

  // member: map_scale
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "map_scale: ";
    rosidl_generator_traits::value_to_yaml(msg.map_scale, out);
    out << "\n";
  }

  // member: lower_n
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "lower_n: ";
    rosidl_generator_traits::value_to_yaml(msg.lower_n, out);
    out << "\n";
  }

  // member: upper_n
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "upper_n: ";
    rosidl_generator_traits::value_to_yaml(msg.upper_n, out);
    out << "\n";
  }

  // member: previous_anchor_known
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "previous_anchor_known: ";
    rosidl_generator_traits::value_to_yaml(msg.previous_anchor_known, out);
    out << "\n";
  }

  // member: previous_final_n
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.previous_final_n.size() == 0) {
      out << "previous_final_n: []\n";
    } else {
      out << "previous_final_n:\n";
      for (auto item : msg.previous_final_n) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: plant_acceptance_observed
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "plant_acceptance_observed: ";
    rosidl_generator_traits::value_to_yaml(msg.plant_acceptance_observed, out);
    out << "\n";
  }

  // member: force_measured
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "force_measured: ";
    rosidl_generator_traits::value_to_yaml(msg.force_measured, out);
    out << "\n";
  }

  // member: execution_atomicity_proven
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "execution_atomicity_proven: ";
    rosidl_generator_traits::value_to_yaml(msg.execution_atomicity_proven, out);
    out << "\n";
  }

  // member: publish_error
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "publish_error: ";
    rosidl_generator_traits::value_to_yaml(msg.publish_error, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const AppliedControl & msg, bool use_flow_style = false)
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
  const usv_research_interfaces::msg::AppliedControl & msg,
  std::ostream & out, size_t indentation = 0)
{
  usv_research_interfaces::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use usv_research_interfaces::msg::to_yaml() instead")]]
inline std::string to_yaml(const usv_research_interfaces::msg::AppliedControl & msg)
{
  return usv_research_interfaces::msg::to_yaml(msg);
}

template<>
inline const char * data_type<usv_research_interfaces::msg::AppliedControl>()
{
  return "usv_research_interfaces::msg::AppliedControl";
}

template<>
inline const char * name<usv_research_interfaces::msg::AppliedControl>()
{
  return "usv_research_interfaces/msg/AppliedControl";
}

template<>
struct has_fixed_size<usv_research_interfaces::msg::AppliedControl>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<usv_research_interfaces::msg::AppliedControl>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<usv_research_interfaces::msg::AppliedControl>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__APPLIED_CONTROL__TRAITS_HPP_
