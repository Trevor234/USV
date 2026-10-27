// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from usv_research_interfaces:msg/ExecutionDecision.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/execution_decision.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__EXECUTION_DECISION__TRAITS_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__EXECUTION_DECISION__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "usv_research_interfaces/msg/detail/execution_decision__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace usv_research_interfaces
{

namespace msg
{

inline void to_flow_style_yaml(
  const ExecutionDecision & msg,
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

  // member: worker_instance
  {
    out << "worker_instance: ";
    rosidl_generator_traits::value_to_yaml(msg.worker_instance, out);
    out << ", ";
  }

  // member: mode
  {
    out << "mode: ";
    rosidl_generator_traits::value_to_yaml(msg.mode, out);
    out << ", ";
  }

  // member: sequence
  {
    out << "sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.sequence, out);
    out << ", ";
  }

  // member: tick
  {
    out << "tick: ";
    rosidl_generator_traits::value_to_yaml(msg.tick, out);
    out << ", ";
  }

  // member: job_id
  {
    out << "job_id: ";
    rosidl_generator_traits::value_to_yaml(msg.job_id, out);
    out << ", ";
  }

  // member: task_generation
  {
    out << "task_generation: ";
    rosidl_generator_traits::value_to_yaml(msg.task_generation, out);
    out << ", ";
  }

  // member: model_generation
  {
    out << "model_generation: ";
    rosidl_generator_traits::value_to_yaml(msg.model_generation, out);
    out << ", ";
  }

  // member: config_generation
  {
    out << "config_generation: ";
    rosidl_generator_traits::value_to_yaml(msg.config_generation, out);
    out << ", ";
  }

  // member: schedule_generation
  {
    out << "schedule_generation: ";
    rosidl_generator_traits::value_to_yaml(msg.schedule_generation, out);
    out << ", ";
  }

  // member: clock_epoch
  {
    out << "clock_epoch: ";
    rosidl_generator_traits::value_to_yaml(msg.clock_epoch, out);
    out << ", ";
  }

  // member: tick_planned_ns
  {
    out << "tick_planned_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.tick_planned_ns, out);
    out << ", ";
  }

  // member: tick_start_ns
  {
    out << "tick_start_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.tick_start_ns, out);
    out << ", ";
  }

  // member: cutoff_commit_ns
  {
    out << "cutoff_commit_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.cutoff_commit_ns, out);
    out << ", ";
  }

  // member: candidate_ready_commit_ns
  {
    out << "candidate_ready_commit_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.candidate_ready_commit_ns, out);
    out << ", ";
  }

  // member: activation_commit_ns
  {
    out << "activation_commit_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_commit_ns, out);
    out << ", ";
  }

  // member: tick_end_ns
  {
    out << "tick_end_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.tick_end_ns, out);
    out << ", ";
  }

  // member: skipped_ticks
  {
    out << "skipped_ticks: ";
    rosidl_generator_traits::value_to_yaml(msg.skipped_ticks, out);
    out << ", ";
  }

  // member: candidate_accepted
  {
    out << "candidate_accepted: ";
    rosidl_generator_traits::value_to_yaml(msg.candidate_accepted, out);
    out << ", ";
  }

  // member: diagnostic_only
  {
    out << "diagnostic_only: ";
    rosidl_generator_traits::value_to_yaml(msg.diagnostic_only, out);
    out << ", ";
  }

  // member: reason
  {
    out << "reason: ";
    rosidl_generator_traits::value_to_yaml(msg.reason, out);
    out << ", ";
  }

  // member: control_source
  {
    out << "control_source: ";
    rosidl_generator_traits::value_to_yaml(msg.control_source, out);
    out << ", ";
  }

  // member: target_state
  {
    if (msg.target_state.size() == 0) {
      out << "target_state: []";
    } else {
      out << "target_state: [";
      size_t pending_items = msg.target_state.size();
      for (auto item : msg.target_state) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: activation_state
  {
    if (msg.activation_state.size() == 0) {
      out << "activation_state: []";
    } else {
      out << "activation_state: [";
      size_t pending_items = msg.activation_state.size();
      for (auto item : msg.activation_state) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: state_error
  {
    if (msg.state_error.size() == 0) {
      out << "state_error: []";
    } else {
      out << "state_error: [";
      size_t pending_items = msg.state_error.size();
      for (auto item : msg.state_error) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
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

  // member: publish_success
  {
    if (msg.publish_success.size() == 0) {
      out << "publish_success: []";
    } else {
      out << "publish_success: [";
      size_t pending_items = msg.publish_success.size();
      for (auto item : msg.publish_success) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: publish_start_ns
  {
    if (msg.publish_start_ns.size() == 0) {
      out << "publish_start_ns: []";
    } else {
      out << "publish_start_ns: [";
      size_t pending_items = msg.publish_start_ns.size();
      for (auto item : msg.publish_start_ns) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: publish_end_ns
  {
    if (msg.publish_end_ns.size() == 0) {
      out << "publish_end_ns: []";
    } else {
      out << "publish_end_ns: [";
      size_t pending_items = msg.publish_end_ns.size();
      for (auto item : msg.publish_end_ns) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: anchor_known
  {
    if (msg.anchor_known.size() == 0) {
      out << "anchor_known: []";
    } else {
      out << "anchor_known: [";
      size_t pending_items = msg.anchor_known.size();
      for (auto item : msg.anchor_known) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: anchor_sequence
  {
    if (msg.anchor_sequence.size() == 0) {
      out << "anchor_sequence: []";
    } else {
      out << "anchor_sequence: [";
      size_t pending_items = msg.anchor_sequence.size();
      for (auto item : msg.anchor_sequence) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: previous_n
  {
    if (msg.previous_n.size() == 0) {
      out << "previous_n: []";
    } else {
      out << "previous_n: [";
      size_t pending_items = msg.previous_n.size();
      for (auto item : msg.previous_n) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: previous_publish_ns
  {
    if (msg.previous_publish_ns.size() == 0) {
      out << "previous_publish_ns: []";
    } else {
      out << "previous_publish_ns: [";
      size_t pending_items = msg.previous_publish_ns.size();
      for (auto item : msg.previous_publish_ns) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: odom_age_ns
  {
    out << "odom_age_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.odom_age_ns, out);
    out << ", ";
  }

  // member: imu_age_ns
  {
    out << "imu_age_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.imu_age_ns, out);
    out << ", ";
  }

  // member: clock_age_ns
  {
    out << "clock_age_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.clock_age_ns, out);
    out << ", ";
  }

  // member: normal_contract_complete
  {
    out << "normal_contract_complete: ";
    rosidl_generator_traits::value_to_yaml(msg.normal_contract_complete, out);
    out << ", ";
  }

  // member: rho_available
  {
    out << "rho_available: ";
    rosidl_generator_traits::value_to_yaml(msg.rho_available, out);
    out << ", ";
  }

  // member: plant_acceptance_observed
  {
    out << "plant_acceptance_observed: ";
    rosidl_generator_traits::value_to_yaml(msg.plant_acceptance_observed, out);
    out << ", ";
  }

  // member: previous_anchor_known
  {
    if (msg.previous_anchor_known.size() == 0) {
      out << "previous_anchor_known: []";
    } else {
      out << "previous_anchor_known: [";
      size_t pending_items = msg.previous_anchor_known.size();
      for (auto item : msg.previous_anchor_known) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: publish_sim_ns
  {
    if (msg.publish_sim_ns.size() == 0) {
      out << "publish_sim_ns: []";
    } else {
      out << "publish_sim_ns: [";
      size_t pending_items = msg.publish_sim_ns.size();
      for (auto item : msg.publish_sim_ns) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: publish_epoch
  {
    if (msg.publish_epoch.size() == 0) {
      out << "publish_epoch: []";
    } else {
      out << "publish_epoch: [";
      size_t pending_items = msg.publish_epoch.size();
      for (auto item : msg.publish_epoch) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: publish_clock_age_ns
  {
    if (msg.publish_clock_age_ns.size() == 0) {
      out << "publish_clock_age_ns: []";
    } else {
      out << "publish_clock_age_ns: [";
      size_t pending_items = msg.publish_clock_age_ns.size();
      for (auto item : msg.publish_clock_age_ns) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: activation_clock_sim_ns
  {
    out << "activation_clock_sim_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_clock_sim_ns, out);
    out << ", ";
  }

  // member: activation_clock_receive_ns
  {
    out << "activation_clock_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_clock_receive_ns, out);
    out << ", ";
  }

  // member: activation_rtf
  {
    out << "activation_rtf: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_rtf, out);
    out << ", ";
  }

  // member: activation_odom_stamp_ns
  {
    out << "activation_odom_stamp_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_odom_stamp_ns, out);
    out << ", ";
  }

  // member: activation_odom_receive_ns
  {
    out << "activation_odom_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_odom_receive_ns, out);
    out << ", ";
  }

  // member: activation_odom_sequence
  {
    out << "activation_odom_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_odom_sequence, out);
    out << ", ";
  }

  // member: activation_imu_stamp_ns
  {
    out << "activation_imu_stamp_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_imu_stamp_ns, out);
    out << ", ";
  }

  // member: activation_imu_receive_ns
  {
    out << "activation_imu_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_imu_receive_ns, out);
    out << ", ";
  }

  // member: activation_imu_sequence
  {
    out << "activation_imu_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_imu_sequence, out);
    out << ", ";
  }

  // member: activation_r_from_imu
  {
    out << "activation_r_from_imu: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_r_from_imu, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const ExecutionDecision & msg,
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

  // member: worker_instance
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "worker_instance: ";
    rosidl_generator_traits::value_to_yaml(msg.worker_instance, out);
    out << "\n";
  }

  // member: mode
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "mode: ";
    rosidl_generator_traits::value_to_yaml(msg.mode, out);
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

  // member: tick
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "tick: ";
    rosidl_generator_traits::value_to_yaml(msg.tick, out);
    out << "\n";
  }

  // member: job_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "job_id: ";
    rosidl_generator_traits::value_to_yaml(msg.job_id, out);
    out << "\n";
  }

  // member: task_generation
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "task_generation: ";
    rosidl_generator_traits::value_to_yaml(msg.task_generation, out);
    out << "\n";
  }

  // member: model_generation
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "model_generation: ";
    rosidl_generator_traits::value_to_yaml(msg.model_generation, out);
    out << "\n";
  }

  // member: config_generation
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "config_generation: ";
    rosidl_generator_traits::value_to_yaml(msg.config_generation, out);
    out << "\n";
  }

  // member: schedule_generation
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "schedule_generation: ";
    rosidl_generator_traits::value_to_yaml(msg.schedule_generation, out);
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

  // member: tick_planned_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "tick_planned_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.tick_planned_ns, out);
    out << "\n";
  }

  // member: tick_start_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "tick_start_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.tick_start_ns, out);
    out << "\n";
  }

  // member: cutoff_commit_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "cutoff_commit_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.cutoff_commit_ns, out);
    out << "\n";
  }

  // member: candidate_ready_commit_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "candidate_ready_commit_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.candidate_ready_commit_ns, out);
    out << "\n";
  }

  // member: activation_commit_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "activation_commit_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_commit_ns, out);
    out << "\n";
  }

  // member: tick_end_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "tick_end_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.tick_end_ns, out);
    out << "\n";
  }

  // member: skipped_ticks
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "skipped_ticks: ";
    rosidl_generator_traits::value_to_yaml(msg.skipped_ticks, out);
    out << "\n";
  }

  // member: candidate_accepted
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "candidate_accepted: ";
    rosidl_generator_traits::value_to_yaml(msg.candidate_accepted, out);
    out << "\n";
  }

  // member: diagnostic_only
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "diagnostic_only: ";
    rosidl_generator_traits::value_to_yaml(msg.diagnostic_only, out);
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

  // member: control_source
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "control_source: ";
    rosidl_generator_traits::value_to_yaml(msg.control_source, out);
    out << "\n";
  }

  // member: target_state
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.target_state.size() == 0) {
      out << "target_state: []\n";
    } else {
      out << "target_state:\n";
      for (auto item : msg.target_state) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: activation_state
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.activation_state.size() == 0) {
      out << "activation_state: []\n";
    } else {
      out << "activation_state:\n";
      for (auto item : msg.activation_state) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: state_error
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.state_error.size() == 0) {
      out << "state_error: []\n";
    } else {
      out << "state_error:\n";
      for (auto item : msg.state_error) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
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

  // member: publish_success
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.publish_success.size() == 0) {
      out << "publish_success: []\n";
    } else {
      out << "publish_success:\n";
      for (auto item : msg.publish_success) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: publish_start_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.publish_start_ns.size() == 0) {
      out << "publish_start_ns: []\n";
    } else {
      out << "publish_start_ns:\n";
      for (auto item : msg.publish_start_ns) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: publish_end_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.publish_end_ns.size() == 0) {
      out << "publish_end_ns: []\n";
    } else {
      out << "publish_end_ns:\n";
      for (auto item : msg.publish_end_ns) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: anchor_known
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.anchor_known.size() == 0) {
      out << "anchor_known: []\n";
    } else {
      out << "anchor_known:\n";
      for (auto item : msg.anchor_known) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: anchor_sequence
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.anchor_sequence.size() == 0) {
      out << "anchor_sequence: []\n";
    } else {
      out << "anchor_sequence:\n";
      for (auto item : msg.anchor_sequence) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: previous_n
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.previous_n.size() == 0) {
      out << "previous_n: []\n";
    } else {
      out << "previous_n:\n";
      for (auto item : msg.previous_n) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: previous_publish_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.previous_publish_ns.size() == 0) {
      out << "previous_publish_ns: []\n";
    } else {
      out << "previous_publish_ns:\n";
      for (auto item : msg.previous_publish_ns) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: odom_age_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "odom_age_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.odom_age_ns, out);
    out << "\n";
  }

  // member: imu_age_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "imu_age_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.imu_age_ns, out);
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

  // member: normal_contract_complete
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "normal_contract_complete: ";
    rosidl_generator_traits::value_to_yaml(msg.normal_contract_complete, out);
    out << "\n";
  }

  // member: rho_available
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "rho_available: ";
    rosidl_generator_traits::value_to_yaml(msg.rho_available, out);
    out << "\n";
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

  // member: previous_anchor_known
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.previous_anchor_known.size() == 0) {
      out << "previous_anchor_known: []\n";
    } else {
      out << "previous_anchor_known:\n";
      for (auto item : msg.previous_anchor_known) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: publish_sim_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.publish_sim_ns.size() == 0) {
      out << "publish_sim_ns: []\n";
    } else {
      out << "publish_sim_ns:\n";
      for (auto item : msg.publish_sim_ns) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: publish_epoch
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.publish_epoch.size() == 0) {
      out << "publish_epoch: []\n";
    } else {
      out << "publish_epoch:\n";
      for (auto item : msg.publish_epoch) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: publish_clock_age_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.publish_clock_age_ns.size() == 0) {
      out << "publish_clock_age_ns: []\n";
    } else {
      out << "publish_clock_age_ns:\n";
      for (auto item : msg.publish_clock_age_ns) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: activation_clock_sim_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "activation_clock_sim_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_clock_sim_ns, out);
    out << "\n";
  }

  // member: activation_clock_receive_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "activation_clock_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_clock_receive_ns, out);
    out << "\n";
  }

  // member: activation_rtf
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "activation_rtf: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_rtf, out);
    out << "\n";
  }

  // member: activation_odom_stamp_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "activation_odom_stamp_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_odom_stamp_ns, out);
    out << "\n";
  }

  // member: activation_odom_receive_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "activation_odom_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_odom_receive_ns, out);
    out << "\n";
  }

  // member: activation_odom_sequence
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "activation_odom_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_odom_sequence, out);
    out << "\n";
  }

  // member: activation_imu_stamp_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "activation_imu_stamp_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_imu_stamp_ns, out);
    out << "\n";
  }

  // member: activation_imu_receive_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "activation_imu_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_imu_receive_ns, out);
    out << "\n";
  }

  // member: activation_imu_sequence
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "activation_imu_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_imu_sequence, out);
    out << "\n";
  }

  // member: activation_r_from_imu
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "activation_r_from_imu: ";
    rosidl_generator_traits::value_to_yaml(msg.activation_r_from_imu, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const ExecutionDecision & msg, bool use_flow_style = false)
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
  const usv_research_interfaces::msg::ExecutionDecision & msg,
  std::ostream & out, size_t indentation = 0)
{
  usv_research_interfaces::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use usv_research_interfaces::msg::to_yaml() instead")]]
inline std::string to_yaml(const usv_research_interfaces::msg::ExecutionDecision & msg)
{
  return usv_research_interfaces::msg::to_yaml(msg);
}

template<>
inline const char * data_type<usv_research_interfaces::msg::ExecutionDecision>()
{
  return "usv_research_interfaces::msg::ExecutionDecision";
}

template<>
inline const char * name<usv_research_interfaces::msg::ExecutionDecision>()
{
  return "usv_research_interfaces/msg/ExecutionDecision";
}

template<>
struct has_fixed_size<usv_research_interfaces::msg::ExecutionDecision>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<usv_research_interfaces::msg::ExecutionDecision>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<usv_research_interfaces::msg::ExecutionDecision>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__EXECUTION_DECISION__TRAITS_HPP_
