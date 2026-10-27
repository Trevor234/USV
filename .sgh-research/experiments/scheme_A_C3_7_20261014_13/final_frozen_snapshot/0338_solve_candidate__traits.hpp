// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from usv_research_interfaces:msg/SolveCandidate.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/solve_candidate.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_CANDIDATE__TRAITS_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_CANDIDATE__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "usv_research_interfaces/msg/detail/solve_candidate__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

// Include directives for member types
// Member 'job'
#include "usv_research_interfaces/msg/detail/solve_job__traits.hpp"

namespace usv_research_interfaces
{

namespace msg
{

inline void to_flow_style_yaml(
  const SolveCandidate & msg,
  std::ostream & out)
{
  out << "{";
  // member: job
  {
    out << "job: ";
    to_flow_style_yaml(msg.job, out);
    out << ", ";
  }

  // member: worker_instance
  {
    out << "worker_instance: ";
    rosidl_generator_traits::value_to_yaml(msg.worker_instance, out);
    out << ", ";
  }

  // member: worker_receive_ns
  {
    out << "worker_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.worker_receive_ns, out);
    out << ", ";
  }

  // member: solve_start_ns
  {
    out << "solve_start_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.solve_start_ns, out);
    out << ", ";
  }

  // member: solve_end_ns
  {
    out << "solve_end_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.solve_end_ns, out);
    out << ", ";
  }

  // member: solver_invoked
  {
    out << "solver_invoked: ";
    rosidl_generator_traits::value_to_yaml(msg.solver_invoked, out);
    out << ", ";
  }

  // member: success
  {
    out << "success: ";
    rosidl_generator_traits::value_to_yaml(msg.success, out);
    out << ", ";
  }

  // member: prediction_available
  {
    out << "prediction_available: ";
    rosidl_generator_traits::value_to_yaml(msg.prediction_available, out);
    out << ", ";
  }

  // member: reason
  {
    out << "reason: ";
    rosidl_generator_traits::value_to_yaml(msg.reason, out);
    out << ", ";
  }

  // member: backend
  {
    out << "backend: ";
    rosidl_generator_traits::value_to_yaml(msg.backend, out);
    out << ", ";
  }

  // member: backend_ms
  {
    out << "backend_ms: ";
    rosidl_generator_traits::value_to_yaml(msg.backend_ms, out);
    out << ", ";
  }

  // member: first_control
  {
    if (msg.first_control.size() == 0) {
      out << "first_control: []";
    } else {
      out << "first_control: [";
      size_t pending_items = msg.first_control.size();
      for (auto item : msg.first_control) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: x_prediction
  {
    if (msg.x_prediction.size() == 0) {
      out << "x_prediction: []";
    } else {
      out << "x_prediction: [";
      size_t pending_items = msg.x_prediction.size();
      for (auto item : msg.x_prediction) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: u_prediction
  {
    if (msg.u_prediction.size() == 0) {
      out << "u_prediction: []";
    } else {
      out << "u_prediction: [";
      size_t pending_items = msg.u_prediction.size();
      for (auto item : msg.u_prediction) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const SolveCandidate & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: job
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "job:\n";
    to_block_style_yaml(msg.job, out, indentation + 2);
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

  // member: worker_receive_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "worker_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.worker_receive_ns, out);
    out << "\n";
  }

  // member: solve_start_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "solve_start_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.solve_start_ns, out);
    out << "\n";
  }

  // member: solve_end_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "solve_end_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.solve_end_ns, out);
    out << "\n";
  }

  // member: solver_invoked
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "solver_invoked: ";
    rosidl_generator_traits::value_to_yaml(msg.solver_invoked, out);
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

  // member: prediction_available
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "prediction_available: ";
    rosidl_generator_traits::value_to_yaml(msg.prediction_available, out);
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

  // member: backend
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "backend: ";
    rosidl_generator_traits::value_to_yaml(msg.backend, out);
    out << "\n";
  }

  // member: backend_ms
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "backend_ms: ";
    rosidl_generator_traits::value_to_yaml(msg.backend_ms, out);
    out << "\n";
  }

  // member: first_control
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.first_control.size() == 0) {
      out << "first_control: []\n";
    } else {
      out << "first_control:\n";
      for (auto item : msg.first_control) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: x_prediction
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.x_prediction.size() == 0) {
      out << "x_prediction: []\n";
    } else {
      out << "x_prediction:\n";
      for (auto item : msg.x_prediction) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: u_prediction
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.u_prediction.size() == 0) {
      out << "u_prediction: []\n";
    } else {
      out << "u_prediction:\n";
      for (auto item : msg.u_prediction) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const SolveCandidate & msg, bool use_flow_style = false)
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
  const usv_research_interfaces::msg::SolveCandidate & msg,
  std::ostream & out, size_t indentation = 0)
{
  usv_research_interfaces::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use usv_research_interfaces::msg::to_yaml() instead")]]
inline std::string to_yaml(const usv_research_interfaces::msg::SolveCandidate & msg)
{
  return usv_research_interfaces::msg::to_yaml(msg);
}

template<>
inline const char * data_type<usv_research_interfaces::msg::SolveCandidate>()
{
  return "usv_research_interfaces::msg::SolveCandidate";
}

template<>
inline const char * name<usv_research_interfaces::msg::SolveCandidate>()
{
  return "usv_research_interfaces/msg/SolveCandidate";
}

template<>
struct has_fixed_size<usv_research_interfaces::msg::SolveCandidate>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<usv_research_interfaces::msg::SolveCandidate>
  : std::integral_constant<bool, has_bounded_size<usv_research_interfaces::msg::SolveJob>::value> {};

template<>
struct is_message<usv_research_interfaces::msg::SolveCandidate>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_CANDIDATE__TRAITS_HPP_
