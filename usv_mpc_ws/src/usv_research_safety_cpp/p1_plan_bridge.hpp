// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#pragma once

#include "p1_contract.hpp"
#include "p1_job_wire.hpp"
#include "p1_model_reference.hpp"
#include "p1_model_transaction.hpp"

namespace p1 {

inline model_reference::Axes axes_of(const Job & job) {
  return {job.task_generation, job.model_generation, job.config_generation,
    job.schedule_generation, job.clock_epoch};
}

// Schedule and epoch come from the plan. The contract supplies the time bounds
// against which both processes verify the same grid.
inline model_reference::Grid grid_of_plan(const std::string & plan_text, const ContractSpec & spec) {
  const auto plan = Json::parse(plan_text);
  const auto & grid = plan.at("grid");
  model_reference::Grid out;
  out.schedule_generation = grid.at("schedule_generation_at_table_start").get<std::uint64_t>();
  out.clock_epoch = grid.at("clock_epoch_at_table_start").get<std::uint64_t>();
  out.tick_period_ns = grid.at("tick_period_ns").get<std::int64_t>();
  out.deadline_ns = grid.at("deadline_ns").get<std::int64_t>();
  contract_require(out.tick_period_ns == spec.timing.T_ns, "plan grid tick differs from the contract");
  contract_require(out.deadline_ns == spec.timing.deadline_ns,
    "plan grid deadline differs from the contract");
  return out;
}

inline model_txn::RegisteredModelTransaction::JobIdentity identity_of(const Job & job) {
  return {job.run_id, job.boot_id, job.contract_hash, job.nominal_hash, job.worker_instance};
}

}  // namespace p1
