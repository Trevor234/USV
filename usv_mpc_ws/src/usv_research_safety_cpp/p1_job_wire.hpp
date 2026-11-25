// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#pragma once

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

#include <nlohmann/json.hpp>

#include "usv_research_interfaces/msg/execution_decision.hpp"
#include "usv_research_interfaces/msg/solve_candidate.hpp"
#include "usv_research_interfaces/msg/solve_job.hpp"
#include "usv_research_interfaces/msg/worker_capability.hpp"

namespace p1 {

using Job = usv_research_interfaces::msg::SolveJob;
using Candidate = usv_research_interfaces::msg::SolveCandidate;
using Capability = usv_research_interfaces::msg::WorkerCapability;
using Decision = usv_research_interfaces::msg::ExecutionDecision;

struct ContractSpec;

struct JobContractContext {
  // Identity views refer to the contract and caller's run identifiers.
  std::string_view run_id;
  std::string_view boot_id;
  std::string_view contract_hash;
  std::string_view nominal_hash;
  std::string_view worker_instance;
  std::uint32_t N;
  double dt;
  std::int64_t T_ns;
  std::int64_t deadline_ns;
  double command_min_n;
  double command_max_n;
  std::size_t history_capacity;
  std::int64_t now_ns = 0;  // Read CLOCK_MONOTONIC at validation if zero.
};

JobContractContext make_job_context(const ContractSpec & spec, std::string_view run_id,
  std::string_view boot_id, std::string_view contract_hash, std::string_view worker_instance,
  std::int64_t now_ns = 0);

template<class Range>
bool finite_array(const Range & values) {
  for (double value : values) {
    if (!std::isfinite(value)) return false;
  }
  return true;
}

std::string valid_job(const Job & job, const JobContractContext & context);
bool job_echo_equals(const Job & lhs, const Job & rhs) noexcept;

nlohmann::json job_to_json(const Job & job);
inline nlohmann::json job_json(const Job & job) { return job_to_json(job); }

nlohmann::json decision_to_json(const Decision & decision);
inline nlohmann::json decision_json(const Decision & decision) { return decision_to_json(decision); }

}  // namespace p1
