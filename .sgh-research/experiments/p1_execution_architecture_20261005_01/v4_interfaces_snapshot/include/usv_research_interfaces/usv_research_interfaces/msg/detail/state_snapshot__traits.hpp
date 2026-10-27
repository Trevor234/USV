// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from usv_research_interfaces:msg/StateSnapshot.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/state_snapshot.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__STATE_SNAPSHOT__TRAITS_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__STATE_SNAPSHOT__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "usv_research_interfaces/msg/detail/state_snapshot__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace usv_research_interfaces
{

namespace msg
{

inline void to_flow_style_yaml(
  const StateSnapshot & msg,
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

  // member: received_odom_sequence
  {
    out << "received_odom_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.received_odom_sequence, out);
    out << ", ";
  }

  // member: odom_stamp_ns
  {
    out << "odom_stamp_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.odom_stamp_ns, out);
    out << ", ";
  }

  // member: receive_steady_ns
  {
    out << "receive_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.receive_steady_ns, out);
    out << ", ";
  }

  // member: freeze_steady_ns
  {
    out << "freeze_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.freeze_steady_ns, out);
    out << ", ";
  }

  // member: frame_id
  {
    out << "frame_id: ";
    rosidl_generator_traits::value_to_yaml(msg.frame_id, out);
    out << ", ";
  }

  // member: child_frame_id
  {
    out << "child_frame_id: ";
    rosidl_generator_traits::value_to_yaml(msg.child_frame_id, out);
    out << ", ";
  }

  // member: state_6
  {
    if (msg.state_6.size() == 0) {
      out << "state_6: []";
    } else {
      out << "state_6: [";
      size_t pending_items = msg.state_6.size();
      for (auto item : msg.state_6) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: valid
  {
    out << "valid: ";
    rosidl_generator_traits::value_to_yaml(msg.valid, out);
    out << ", ";
  }

  // member: quality_reason
  {
    out << "quality_reason: ";
    rosidl_generator_traits::value_to_yaml(msg.quality_reason, out);
    out << ", ";
  }

  // member: source_topic
  {
    out << "source_topic: ";
    rosidl_generator_traits::value_to_yaml(msg.source_topic, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const StateSnapshot & msg,
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

  // member: received_odom_sequence
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "received_odom_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.received_odom_sequence, out);
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

  // member: receive_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "receive_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.receive_steady_ns, out);
    out << "\n";
  }

  // member: freeze_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "freeze_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.freeze_steady_ns, out);
    out << "\n";
  }

  // member: frame_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "frame_id: ";
    rosidl_generator_traits::value_to_yaml(msg.frame_id, out);
    out << "\n";
  }

  // member: child_frame_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "child_frame_id: ";
    rosidl_generator_traits::value_to_yaml(msg.child_frame_id, out);
    out << "\n";
  }

  // member: state_6
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.state_6.size() == 0) {
      out << "state_6: []\n";
    } else {
      out << "state_6:\n";
      for (auto item : msg.state_6) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: valid
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "valid: ";
    rosidl_generator_traits::value_to_yaml(msg.valid, out);
    out << "\n";
  }

  // member: quality_reason
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "quality_reason: ";
    rosidl_generator_traits::value_to_yaml(msg.quality_reason, out);
    out << "\n";
  }

  // member: source_topic
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "source_topic: ";
    rosidl_generator_traits::value_to_yaml(msg.source_topic, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const StateSnapshot & msg, bool use_flow_style = false)
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
  const usv_research_interfaces::msg::StateSnapshot & msg,
  std::ostream & out, size_t indentation = 0)
{
  usv_research_interfaces::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use usv_research_interfaces::msg::to_yaml() instead")]]
inline std::string to_yaml(const usv_research_interfaces::msg::StateSnapshot & msg)
{
  return usv_research_interfaces::msg::to_yaml(msg);
}

template<>
inline const char * data_type<usv_research_interfaces::msg::StateSnapshot>()
{
  return "usv_research_interfaces::msg::StateSnapshot";
}

template<>
inline const char * name<usv_research_interfaces::msg::StateSnapshot>()
{
  return "usv_research_interfaces/msg/StateSnapshot";
}

template<>
struct has_fixed_size<usv_research_interfaces::msg::StateSnapshot>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<usv_research_interfaces::msg::StateSnapshot>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<usv_research_interfaces::msg::StateSnapshot>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__STATE_SNAPSHOT__TRAITS_HPP_
