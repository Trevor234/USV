// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include "p1_job_wire.hpp"

#include <limits>

#include "p1_contract.hpp"
#include "p1_sys_utils.hpp"

namespace p1 {
namespace {

const char * check_job_identity(const Job & job, const JobContractContext & context) {
  if (job.schema_version != "p1-solve-job-v1" || job.run_id != context.run_id ||
      job.boot_id != context.boot_id || job.contract_hash != context.contract_hash ||
      job.nominal_hash != context.nominal_hash || job.worker_instance != context.worker_instance) {
    return "foreign";
  }
  return nullptr;
}

const char * check_job_timing(const Job & job, const JobContractContext & context) {
  const auto origin = job.tick_origin_steady_ns;
  const auto max_ns = std::numeric_limits<std::int64_t>::max();
  const auto now = context.now_ns != 0 ? context.now_ns : monotonic_ns();
  if (context.T_ns <= 0 || context.deadline_ns <= 0 || context.deadline_ns > context.T_ns ||
      origin < 0 || origin > max_ns - context.T_ns ||
      job.freeze_steady_ns < origin || job.freeze_steady_ns > now ||
      job.target_sim_ns < job.odom_stamp_ns || job.odom_receive_ns > job.freeze_steady_ns ||
      job.imu_receive_ns > job.freeze_steady_ns) {
    return "invalid_time_order";
  }
  if (job.deadline_steady_ns != origin + context.deadline_ns ||
      job.target_steady_ns != origin + context.T_ns || job.freeze_steady_ns > job.deadline_steady_ns) {
    return "shape_or_time_contract";
  }
  return nullptr;
}

const char * check_job_shape_finite(const Job & job, const JobContractContext & context) {
  if (job.horizon_steps != context.N || job.prediction_dt != context.dt || job.job_id == 0) {
    return "shape_or_time_contract";
  }
  if (!finite_array(job.target_state) || !finite_array(job.frozen_state) ||
      !finite_array(job.reference) || !finite_array(job.anchor_n)) {
    return "nonfinite";
  }
  return nullptr;
}

const char * check_job_anchors(const Job & job, const JobContractContext & context) {
  for (std::size_t i = 0; i < job.anchor_n.size(); ++i) {
    if (!job.anchor_known[i] || job.anchor_n[i] < context.command_min_n ||
        job.anchor_n[i] > context.command_max_n || job.anchor_publish_ns[i] <= 0 ||
        job.anchor_publish_ns[i] > job.freeze_steady_ns) {
      return "unknown_or_invalid_anchor";
    }
  }
  return nullptr;
}

const char * check_job_history(const Job & job, const JobContractContext & context) {
  const auto size = job.history_sim_ns.size();
  if (size > context.history_capacity || job.history_channel.size() != size ||
      job.history_n.size() != size || !finite_array(job.history_n) ||
      job.assumed_rtf != 1.0 || job.frozen_clock_receive_ns > job.freeze_steady_ns) {
    return "history_shape_or_time";
  }
  for (std::size_t i = 0; i < size; ++i) {
    if (job.history_channel[i] >= job.anchor_n.size() ||
        (i > 0 && job.history_sim_ns[i] < job.history_sim_ns[i - 1]) ||
        job.history_n[i] < context.command_min_n || job.history_n[i] > context.command_max_n) {
      return "invalid_history";
    }
  }
  return nullptr;
}

}  // namespace

JobContractContext make_job_context(const ContractSpec & spec, std::string_view run_id,
  std::string_view boot_id, std::string_view contract_hash, std::string_view worker_instance,
  std::int64_t now_ns) {
  return {run_id, boot_id, contract_hash, spec.identity.nominal_hash, worker_instance,
    static_cast<std::uint32_t>(spec.mpc.N), spec.mpc.dt, spec.timing.T_ns,
    spec.timing.deadline_ns, spec.actuator.command_min_n, spec.actuator.command_max_n,
    spec.resources.history_capacity, now_ns};
}

std::string valid_job(const Job & job, const JobContractContext & context) {
  if (const auto * reason = check_job_identity(job, context)) return reason;
  if (const auto * reason = check_job_timing(job, context)) return reason;
  if (const auto * reason = check_job_shape_finite(job, context)) return reason;
  if (const auto * reason = check_job_anchors(job, context)) return reason;
  if (const auto * reason = check_job_history(job, context)) return reason;
  return {};
}

bool job_echo_equals(const Job & lhs, const Job & rhs) noexcept {
  // The generated ROS comparator visits every SolveJob member by reference.
  // Its scalar and sequence comparisons match those of the JSON values.
  return lhs == rhs;
}

nlohmann::json job_to_json(const Job & j) {
  return {
    {"schema", j.schema_version},
    {"run_id", j.run_id},
    {"boot_id", j.boot_id},
    {"contract_hash", j.contract_hash},
    {"nominal_hash", j.nominal_hash},
    {"worker_instance", j.worker_instance},
    {"job_id", j.job_id},
    {"target_tick", j.target_tick},
    {"task_generation", j.task_generation},
    {"model_generation", j.model_generation},
    {"config_generation", j.config_generation},
    {"schedule_generation", j.schedule_generation},
    {"clock_epoch", j.clock_epoch},
    {"tick_origin_ns", j.tick_origin_steady_ns},
    {"freeze_ns", j.freeze_steady_ns},
    {"deadline_ns", j.deadline_steady_ns},
    {"target_ns", j.target_steady_ns},
    {"target_sim_ns", j.target_sim_ns},
    {"odom_stamp_ns", j.odom_stamp_ns},
    {"imu_stamp_ns", j.imu_stamp_ns},
    {"odom_receive_ns", j.odom_receive_ns},
    {"imu_receive_ns", j.imu_receive_ns},
    {"odom_sequence", j.odom_sequence},
    {"imu_sequence", j.imu_sequence},
    {"r_from_imu", j.r_from_imu},
    {"N", j.horizon_steps},
    {"dt", j.prediction_dt},
    {"frozen_state", j.frozen_state},
    {"target_state", j.target_state},
    {"reference", j.reference},
    {"anchor_n", j.anchor_n},
    {"anchor_sequence", j.anchor_sequence},
    {"anchor_publish_ns", j.anchor_publish_ns},
    {"anchor_known", j.anchor_known},
    {"reset_warmstart", j.reset_warmstart},
    {"frozen_clock_sim_ns", j.frozen_clock_sim_ns},
    {"frozen_clock_receive_ns", j.frozen_clock_receive_ns},
    {"assumed_rtf", j.assumed_rtf},
    {"anchor_source", j.anchor_source},
    {"anchor_producer", j.anchor_producer},
    {"anchor_run_id", j.anchor_run_id},
    {"history_sim_ns", j.history_sim_ns},
    {"history_channel", j.history_channel},
    {"history_n", j.history_n},
  };
}

nlohmann::json decision_to_json(const Decision & decision) {
  return {
    {"type", "decision"},
    {"schema", decision.schema_version},
    {"run_id", decision.run_id},
    {"boot_id", decision.boot_id},
    {"contract_hash", decision.contract_hash},
    {"worker_instance", decision.worker_instance},
    {"plant_execution_index", decision.anchor_sequence[0]},
    {"model_generation", decision.model_generation},
    {"config_generation", decision.config_generation},
    {"mode", decision.mode},
    {"sequence", decision.sequence},
    {"tick", decision.tick},
    {"job_id", decision.job_id},
    {"task_generation", decision.task_generation},
    {"schedule_generation", decision.schedule_generation},
    {"epoch", decision.clock_epoch},
    {"clock_epoch", decision.clock_epoch},
    {"anchor_publish_ns", decision.anchor_publish_ns},
    {"planned_ns", decision.tick_planned_ns},
    {"start_ns", decision.tick_start_ns},
    {"cutoff_commit_ns", decision.cutoff_commit_ns},
    {"ready_commit_ns", decision.candidate_ready_commit_ns},
    {"activation_commit_ns", decision.activation_commit_ns},
    {"end_ns", decision.tick_end_ns},
    {"skipped_ticks", decision.skipped_ticks},
    {"candidate_accepted", decision.candidate_accepted},
    {"accepted", decision.candidate_accepted},
    {"diagnostic_only", decision.diagnostic_only},
    {"reason", decision.reason},
    {"control_source", decision.control_source},
    {"target_state", decision.target_state},
    {"activation_state", decision.activation_state},
    {"state_error", decision.state_error},
    {"requested_n", decision.requested_n},
    {"final_n", decision.final_n},
    {"publish_success", decision.publish_success},
    {"publish_start_ns", decision.publish_start_ns},
    {"publish_end_ns", decision.publish_end_ns},
    {"previous_anchor_known", decision.previous_anchor_known},
    {"publish_sim_ns", decision.publish_sim_ns},
    {"publish_epoch", decision.publish_epoch},
    {"publish_clock_age_ns", decision.publish_clock_age_ns},
    {"activation_clock_sim_ns", decision.activation_clock_sim_ns},
    {"activation_clock_receive_ns", decision.activation_clock_receive_ns},
    {"activation_rtf", decision.activation_rtf},
    {"activation_odom_stamp_ns", decision.activation_odom_stamp_ns},
    {"activation_odom_receive_ns", decision.activation_odom_receive_ns},
    {"activation_odom_sequence", decision.activation_odom_sequence},
    {"activation_imu_stamp_ns", decision.activation_imu_stamp_ns},
    {"activation_imu_receive_ns", decision.activation_imu_receive_ns},
    {"activation_imu_sequence", decision.activation_imu_sequence},
    {"activation_r_from_imu", decision.activation_r_from_imu},
    {"previous_n", decision.previous_n},
    {"previous_publish_ns", decision.previous_publish_ns},
    {"anchor_known", decision.anchor_known},
    {"anchor_sequence", decision.anchor_sequence},
    {"odom_age_ns", decision.odom_age_ns},
    {"imu_age_ns", decision.imu_age_ns},
    {"clock_age_ns", decision.clock_age_ns},
    {"normal_contract_complete", decision.normal_contract_complete},
    {"rho_available", decision.rho_available},
    // Acceptance evidence comes from the plant receipt, independently of this decision.
    {"plant_acceptance_observed", false},
  };
}

}  // namespace p1
