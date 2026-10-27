// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from usv_research_interfaces:msg/SolveJob.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/solve_job.hpp"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__TRAITS_HPP_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "usv_research_interfaces/msg/detail/solve_job__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace usv_research_interfaces
{

namespace msg
{

inline void to_flow_style_yaml(
  const SolveJob & msg,
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

  // member: job_id
  {
    out << "job_id: ";
    rosidl_generator_traits::value_to_yaml(msg.job_id, out);
    out << ", ";
  }

  // member: target_tick
  {
    out << "target_tick: ";
    rosidl_generator_traits::value_to_yaml(msg.target_tick, out);
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

  // member: tick_origin_steady_ns
  {
    out << "tick_origin_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.tick_origin_steady_ns, out);
    out << ", ";
  }

  // member: freeze_steady_ns
  {
    out << "freeze_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.freeze_steady_ns, out);
    out << ", ";
  }

  // member: deadline_steady_ns
  {
    out << "deadline_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.deadline_steady_ns, out);
    out << ", ";
  }

  // member: target_steady_ns
  {
    out << "target_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.target_steady_ns, out);
    out << ", ";
  }

  // member: target_sim_ns
  {
    out << "target_sim_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.target_sim_ns, out);
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

  // member: odom_receive_ns
  {
    out << "odom_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.odom_receive_ns, out);
    out << ", ";
  }

  // member: imu_receive_ns
  {
    out << "imu_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.imu_receive_ns, out);
    out << ", ";
  }

  // member: odom_sequence
  {
    out << "odom_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.odom_sequence, out);
    out << ", ";
  }

  // member: imu_sequence
  {
    out << "imu_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.imu_sequence, out);
    out << ", ";
  }

  // member: r_from_imu
  {
    out << "r_from_imu: ";
    rosidl_generator_traits::value_to_yaml(msg.r_from_imu, out);
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

  // member: frozen_state
  {
    if (msg.frozen_state.size() == 0) {
      out << "frozen_state: []";
    } else {
      out << "frozen_state: [";
      size_t pending_items = msg.frozen_state.size();
      for (auto item : msg.frozen_state) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
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

  // member: reference
  {
    if (msg.reference.size() == 0) {
      out << "reference: []";
    } else {
      out << "reference: [";
      size_t pending_items = msg.reference.size();
      for (auto item : msg.reference) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: anchor_n
  {
    if (msg.anchor_n.size() == 0) {
      out << "anchor_n: []";
    } else {
      out << "anchor_n: [";
      size_t pending_items = msg.anchor_n.size();
      for (auto item : msg.anchor_n) {
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

  // member: anchor_publish_ns
  {
    if (msg.anchor_publish_ns.size() == 0) {
      out << "anchor_publish_ns: []";
    } else {
      out << "anchor_publish_ns: [";
      size_t pending_items = msg.anchor_publish_ns.size();
      for (auto item : msg.anchor_publish_ns) {
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

  // member: reset_warmstart
  {
    out << "reset_warmstart: ";
    rosidl_generator_traits::value_to_yaml(msg.reset_warmstart, out);
    out << ", ";
  }

  // member: frozen_clock_sim_ns
  {
    out << "frozen_clock_sim_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.frozen_clock_sim_ns, out);
    out << ", ";
  }

  // member: frozen_clock_receive_ns
  {
    out << "frozen_clock_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.frozen_clock_receive_ns, out);
    out << ", ";
  }

  // member: assumed_rtf
  {
    out << "assumed_rtf: ";
    rosidl_generator_traits::value_to_yaml(msg.assumed_rtf, out);
    out << ", ";
  }

  // member: anchor_source
  {
    out << "anchor_source: ";
    rosidl_generator_traits::value_to_yaml(msg.anchor_source, out);
    out << ", ";
  }

  // member: anchor_producer
  {
    out << "anchor_producer: ";
    rosidl_generator_traits::value_to_yaml(msg.anchor_producer, out);
    out << ", ";
  }

  // member: anchor_run_id
  {
    out << "anchor_run_id: ";
    rosidl_generator_traits::value_to_yaml(msg.anchor_run_id, out);
    out << ", ";
  }

  // member: history_sim_ns
  {
    if (msg.history_sim_ns.size() == 0) {
      out << "history_sim_ns: []";
    } else {
      out << "history_sim_ns: [";
      size_t pending_items = msg.history_sim_ns.size();
      for (auto item : msg.history_sim_ns) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: history_channel
  {
    if (msg.history_channel.size() == 0) {
      out << "history_channel: []";
    } else {
      out << "history_channel: [";
      size_t pending_items = msg.history_channel.size();
      for (auto item : msg.history_channel) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: history_n
  {
    if (msg.history_n.size() == 0) {
      out << "history_n: []";
    } else {
      out << "history_n: [";
      size_t pending_items = msg.history_n.size();
      for (auto item : msg.history_n) {
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
  const SolveJob & msg,
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

  // member: job_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "job_id: ";
    rosidl_generator_traits::value_to_yaml(msg.job_id, out);
    out << "\n";
  }

  // member: target_tick
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "target_tick: ";
    rosidl_generator_traits::value_to_yaml(msg.target_tick, out);
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

  // member: tick_origin_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "tick_origin_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.tick_origin_steady_ns, out);
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

  // member: deadline_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "deadline_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.deadline_steady_ns, out);
    out << "\n";
  }

  // member: target_steady_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "target_steady_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.target_steady_ns, out);
    out << "\n";
  }

  // member: target_sim_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "target_sim_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.target_sim_ns, out);
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

  // member: odom_receive_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "odom_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.odom_receive_ns, out);
    out << "\n";
  }

  // member: imu_receive_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "imu_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.imu_receive_ns, out);
    out << "\n";
  }

  // member: odom_sequence
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "odom_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.odom_sequence, out);
    out << "\n";
  }

  // member: imu_sequence
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "imu_sequence: ";
    rosidl_generator_traits::value_to_yaml(msg.imu_sequence, out);
    out << "\n";
  }

  // member: r_from_imu
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "r_from_imu: ";
    rosidl_generator_traits::value_to_yaml(msg.r_from_imu, out);
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

  // member: frozen_state
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.frozen_state.size() == 0) {
      out << "frozen_state: []\n";
    } else {
      out << "frozen_state:\n";
      for (auto item : msg.frozen_state) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
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

  // member: reference
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.reference.size() == 0) {
      out << "reference: []\n";
    } else {
      out << "reference:\n";
      for (auto item : msg.reference) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: anchor_n
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.anchor_n.size() == 0) {
      out << "anchor_n: []\n";
    } else {
      out << "anchor_n:\n";
      for (auto item : msg.anchor_n) {
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

  // member: anchor_publish_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.anchor_publish_ns.size() == 0) {
      out << "anchor_publish_ns: []\n";
    } else {
      out << "anchor_publish_ns:\n";
      for (auto item : msg.anchor_publish_ns) {
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

  // member: reset_warmstart
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "reset_warmstart: ";
    rosidl_generator_traits::value_to_yaml(msg.reset_warmstart, out);
    out << "\n";
  }

  // member: frozen_clock_sim_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "frozen_clock_sim_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.frozen_clock_sim_ns, out);
    out << "\n";
  }

  // member: frozen_clock_receive_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "frozen_clock_receive_ns: ";
    rosidl_generator_traits::value_to_yaml(msg.frozen_clock_receive_ns, out);
    out << "\n";
  }

  // member: assumed_rtf
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "assumed_rtf: ";
    rosidl_generator_traits::value_to_yaml(msg.assumed_rtf, out);
    out << "\n";
  }

  // member: anchor_source
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "anchor_source: ";
    rosidl_generator_traits::value_to_yaml(msg.anchor_source, out);
    out << "\n";
  }

  // member: anchor_producer
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "anchor_producer: ";
    rosidl_generator_traits::value_to_yaml(msg.anchor_producer, out);
    out << "\n";
  }

  // member: anchor_run_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "anchor_run_id: ";
    rosidl_generator_traits::value_to_yaml(msg.anchor_run_id, out);
    out << "\n";
  }

  // member: history_sim_ns
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.history_sim_ns.size() == 0) {
      out << "history_sim_ns: []\n";
    } else {
      out << "history_sim_ns:\n";
      for (auto item : msg.history_sim_ns) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: history_channel
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.history_channel.size() == 0) {
      out << "history_channel: []\n";
    } else {
      out << "history_channel:\n";
      for (auto item : msg.history_channel) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: history_n
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.history_n.size() == 0) {
      out << "history_n: []\n";
    } else {
      out << "history_n:\n";
      for (auto item : msg.history_n) {
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

inline std::string to_yaml(const SolveJob & msg, bool use_flow_style = false)
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
  const usv_research_interfaces::msg::SolveJob & msg,
  std::ostream & out, size_t indentation = 0)
{
  usv_research_interfaces::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use usv_research_interfaces::msg::to_yaml() instead")]]
inline std::string to_yaml(const usv_research_interfaces::msg::SolveJob & msg)
{
  return usv_research_interfaces::msg::to_yaml(msg);
}

template<>
inline const char * data_type<usv_research_interfaces::msg::SolveJob>()
{
  return "usv_research_interfaces::msg::SolveJob";
}

template<>
inline const char * name<usv_research_interfaces::msg::SolveJob>()
{
  return "usv_research_interfaces/msg/SolveJob";
}

template<>
struct has_fixed_size<usv_research_interfaces::msg::SolveJob>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<usv_research_interfaces::msg::SolveJob>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<usv_research_interfaces::msg::SolveJob>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__SOLVE_JOB__TRAITS_HPP_
