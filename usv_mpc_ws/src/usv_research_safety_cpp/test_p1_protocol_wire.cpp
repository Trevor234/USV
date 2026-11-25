// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include <gtest/gtest.h>

#include <initializer_list>
#include <limits>
#include <set>
#include <type_traits>

#include "p1_contract.hpp"
#include "p1_job_wire.hpp"

namespace {

using p1::Job;
using p1::Json;

p1::ContractSpec job_spec() {
  p1::ContractSpec spec;
  spec.identity.nominal_hash = "nominal";
  spec.mpc.N = 10;
  spec.mpc.dt = 0.125;
  spec.timing.T_ns = 125'000'000;
  spec.timing.deadline_ns = 90'000'000;
  spec.actuator.command_min_n = -30;
  spec.actuator.command_max_n = 12;
  spec.resources.history_capacity = 2;
  return spec;
}

Job valid_job_fixture(const p1::JobContractContext & context) {
  Job job;
  job.schema_version = "p1-solve-job-v1";
  job.run_id = context.run_id;
  job.boot_id = context.boot_id;
  job.contract_hash = context.contract_hash;
  job.nominal_hash = context.nominal_hash;
  job.worker_instance = context.worker_instance;
  job.job_id = 1;
  job.horizon_steps = context.N;
  job.prediction_dt = context.dt;
  job.tick_origin_steady_ns = 1'000'000'000;
  job.freeze_steady_ns = job.tick_origin_steady_ns + 20;
  job.deadline_steady_ns = job.tick_origin_steady_ns + context.deadline_ns;
  job.target_steady_ns = job.tick_origin_steady_ns + context.T_ns;
  job.target_sim_ns = 200;
  job.odom_stamp_ns = 100;
  job.odom_receive_ns = job.tick_origin_steady_ns;
  job.frozen_clock_receive_ns = job.freeze_steady_ns;
  job.assumed_rtf = 1;
  job.anchor_known = {true, true};
  job.anchor_publish_ns = {job.freeze_steady_ns, job.freeze_steady_ns};
  job.anchor_n = {context.command_min_n, context.command_max_n};
  job.history_sim_ns = {10, 20};
  job.history_channel = {0, 1};
  job.history_n = {context.command_min_n, context.command_max_n};
  return job;
}

TEST(P1ProtocolWire, ValidJobUsesContractDimensionsAndTimes) {
  const auto spec = job_spec();
  auto context = p1::make_job_context(spec, "run", "boot", "contract", "worker", 1'000'000'020);
  const auto job = valid_job_fixture(context);
  EXPECT_TRUE(p1::valid_job(job, context).empty());

  auto changed = context;
  ++changed.N;
  EXPECT_EQ(p1::valid_job(job, changed), "shape_or_time_contract");
  changed = context;
  changed.dt *= 2;
  EXPECT_EQ(p1::valid_job(job, changed), "shape_or_time_contract");
  changed = context;
  ++changed.T_ns;
  EXPECT_EQ(p1::valid_job(job, changed), "shape_or_time_contract");
  changed = context;
  --changed.deadline_ns;
  EXPECT_EQ(p1::valid_job(job, changed), "shape_or_time_contract");

  --context.now_ns;
  EXPECT_EQ(p1::valid_job(job, context), "invalid_time_order");
  ++context.now_ns;
  auto overflow = job;
  overflow.tick_origin_steady_ns = std::numeric_limits<std::int64_t>::max() - context.T_ns + 1;
  EXPECT_EQ(p1::valid_job(overflow, context), "invalid_time_order");
  auto foreign = job;
  foreign.nominal_hash += "x";
  EXPECT_EQ(p1::valid_job(foreign, context), "foreign");
}

TEST(P1ProtocolWire, ValidJobEnforcesAsymmetricActuatorAndHistoryLimits) {
  const auto spec = job_spec();
  const auto context = p1::make_job_context(spec, "run", "boot", "contract", "worker", 1'000'000'020);
  const auto job = valid_job_fixture(context);
  EXPECT_TRUE(p1::valid_job(job, context).empty());

  auto bounded = context;
  --bounded.history_capacity;
  EXPECT_EQ(p1::valid_job(job, bounded), "history_shape_or_time");
  for (std::size_t channel = 0; channel < job.anchor_n.size(); ++channel) {
    const double beyond_bound = job.anchor_n[channel] + (channel == 0 ? -0.01 : 0.01);
    auto changed = job;
    changed.anchor_n[channel] = beyond_bound;
    EXPECT_EQ(p1::valid_job(changed, context), "unknown_or_invalid_anchor");
    changed = job;
    changed.history_n[channel] = beyond_bound;
    EXPECT_EQ(p1::valid_job(changed, context), "invalid_history");
  }

  auto changed = job;
  changed.history_n.pop_back();
  EXPECT_EQ(p1::valid_job(changed, context), "history_shape_or_time");
  changed = job;
  changed.history_sim_ns[1] = 9;
  EXPECT_EQ(p1::valid_job(changed, context), "invalid_history");
  changed = job;
  changed.history_channel[0] = 2;
  EXPECT_EQ(p1::valid_job(changed, context), "invalid_history");
  changed = job;
  changed.reference.back() = std::numeric_limits<double>::infinity();
  EXPECT_EQ(p1::valid_job(changed, context), "nonfinite");
}

// Mutate one member independently from the production JSON mapping. Arrays and
// bounded sequences change at the last element to cover their full comparison.
template<class T>
void mutate(T & value) {
  if constexpr (std::is_same_v<T, bool>) {
    value = !value;
  } else if constexpr (std::is_arithmetic_v<T>) {
    ++value;
  } else if constexpr (std::is_same_v<T, std::string>) {
    value += 'x';
  } else {
    mutate(value.back());
  }
}

TEST(P1ProtocolWire, EchoAndJsonCoverEverySolveJobField) {
  const auto spec = job_spec();
  const auto context = p1::make_job_context(spec, "run", "boot", "contract", "worker", 1'000'000'020);
  const auto original = valid_job_fixture(context);
  const auto baseline = p1::job_to_json(original);
  EXPECT_TRUE(p1::job_echo_equals(original, Job(original)));
  EXPECT_EQ(p1::job_json(original), baseline);

  std::set<std::string> expected_keys;
  const auto expect_mutation = [&](const char * key, auto member) {
    SCOPED_TRACE(key);
    EXPECT_TRUE(expected_keys.emplace(key).second);
    auto changed = original;
    mutate(changed.*member);
    EXPECT_FALSE(p1::job_echo_equals(original, changed));
    EXPECT_FALSE(p1::job_echo_equals(changed, original));

    auto changed_json = p1::job_to_json(changed);
    ASSERT_TRUE(changed_json.contains(key));
    EXPECT_EQ(changed_json.at(key), Json(changed.*member));
    EXPECT_NE(changed_json.at(key), baseline.at(key));
    auto expected_other_fields = baseline;
    expected_other_fields.erase(key);
    changed_json.erase(key);
    EXPECT_EQ(changed_json, expected_other_fields);
  };

  expect_mutation("schema", &Job::schema_version);
  expect_mutation("run_id", &Job::run_id);
  expect_mutation("boot_id", &Job::boot_id);
  expect_mutation("contract_hash", &Job::contract_hash);
  expect_mutation("nominal_hash", &Job::nominal_hash);
  expect_mutation("worker_instance", &Job::worker_instance);
  expect_mutation("job_id", &Job::job_id);
  expect_mutation("target_tick", &Job::target_tick);
  expect_mutation("task_generation", &Job::task_generation);
  expect_mutation("model_generation", &Job::model_generation);
  expect_mutation("config_generation", &Job::config_generation);
  expect_mutation("schedule_generation", &Job::schedule_generation);
  expect_mutation("clock_epoch", &Job::clock_epoch);
  expect_mutation("tick_origin_ns", &Job::tick_origin_steady_ns);
  expect_mutation("freeze_ns", &Job::freeze_steady_ns);
  expect_mutation("deadline_ns", &Job::deadline_steady_ns);
  expect_mutation("target_ns", &Job::target_steady_ns);
  expect_mutation("target_sim_ns", &Job::target_sim_ns);
  expect_mutation("odom_stamp_ns", &Job::odom_stamp_ns);
  expect_mutation("imu_stamp_ns", &Job::imu_stamp_ns);
  expect_mutation("odom_receive_ns", &Job::odom_receive_ns);
  expect_mutation("imu_receive_ns", &Job::imu_receive_ns);
  expect_mutation("odom_sequence", &Job::odom_sequence);
  expect_mutation("imu_sequence", &Job::imu_sequence);
  expect_mutation("r_from_imu", &Job::r_from_imu);
  expect_mutation("N", &Job::horizon_steps);
  expect_mutation("dt", &Job::prediction_dt);
  expect_mutation("frozen_state", &Job::frozen_state);
  expect_mutation("target_state", &Job::target_state);
  expect_mutation("reference", &Job::reference);
  expect_mutation("anchor_n", &Job::anchor_n);
  expect_mutation("anchor_sequence", &Job::anchor_sequence);
  expect_mutation("anchor_publish_ns", &Job::anchor_publish_ns);
  expect_mutation("anchor_known", &Job::anchor_known);
  expect_mutation("reset_warmstart", &Job::reset_warmstart);
  expect_mutation("frozen_clock_sim_ns", &Job::frozen_clock_sim_ns);
  expect_mutation("frozen_clock_receive_ns", &Job::frozen_clock_receive_ns);
  expect_mutation("assumed_rtf", &Job::assumed_rtf);
  expect_mutation("anchor_source", &Job::anchor_source);
  expect_mutation("anchor_producer", &Job::anchor_producer);
  expect_mutation("anchor_run_id", &Job::anchor_run_id);
  expect_mutation("history_sim_ns", &Job::history_sim_ns);
  expect_mutation("history_channel", &Job::history_channel);
  expect_mutation("history_n", &Job::history_n);

  std::set<std::string> actual_keys;
  for (const auto & item : baseline.items()) actual_keys.insert(item.key());
  EXPECT_EQ(expected_keys.size(), 44u);
  EXPECT_EQ(actual_keys, expected_keys);
}

TEST(P1ProtocolWire, EchoMatchesJsonEqualityForFloatingPointEdgeCases) {
  Job lhs;
  Job rhs;
  lhs.prediction_dt = -0.0;
  rhs.prediction_dt = 0.0;
  lhs.frozen_state[0] = rhs.frozen_state[0] = std::numeric_limits<double>::infinity();
  EXPECT_TRUE(p1::job_echo_equals(lhs, rhs));
  EXPECT_EQ(p1::job_to_json(lhs), p1::job_to_json(rhs));

  rhs.frozen_state[0] = -rhs.frozen_state[0];
  EXPECT_FALSE(p1::job_echo_equals(lhs, rhs));
  EXPECT_NE(p1::job_to_json(lhs), p1::job_to_json(rhs));

  lhs.frozen_state[0] = rhs.frozen_state[0] = std::numeric_limits<double>::quiet_NaN();
  EXPECT_FALSE(p1::job_echo_equals(lhs, rhs));
  EXPECT_FALSE(p1::job_to_json(lhs) == p1::job_to_json(rhs));

  lhs.frozen_state[0] = rhs.frozen_state[0] = 0;
  lhs.history_n.push_back(std::numeric_limits<double>::quiet_NaN());
  rhs.history_n = lhs.history_n;
  EXPECT_FALSE(p1::job_echo_equals(lhs, rhs));
  EXPECT_FALSE(p1::job_to_json(lhs) == p1::job_to_json(rhs));
}

TEST(P1ProtocolWire, DecisionJsonCoversEveryExecutionDecisionFieldAndAuditAlias) {
  using p1::Decision;
  const Decision original;
  const auto baseline = p1::decision_to_json(original);
  EXPECT_EQ(p1::decision_json(original), baseline);
  EXPECT_EQ(baseline.at("type"), "decision");
  EXPECT_EQ(baseline.at("plant_acceptance_observed"), false);
  EXPECT_EQ(baseline.at("plant_execution_index"), original.anchor_sequence[0]);
  std::set<std::string> expected_keys{"type", "plant_acceptance_observed", "plant_execution_index"};
  const auto expect_member = [&](auto member, std::initializer_list<const char *> keys) {
    auto changed = original;
    mutate(changed.*member);
    auto changed_json = p1::decision_to_json(changed);
    auto expected_other_fields = baseline;
    for (const char * key : keys) {
      SCOPED_TRACE(key);
      EXPECT_TRUE(expected_keys.emplace(key).second);
      ASSERT_TRUE(changed_json.contains(key));
      EXPECT_EQ(baseline.at(key), Json(original.*member));
      EXPECT_EQ(changed_json.at(key), Json(changed.*member));
      EXPECT_NE(changed_json.at(key), baseline.at(key));
      changed_json.erase(key);
      expected_other_fields.erase(key);
    }
    EXPECT_EQ(changed_json, expected_other_fields);
  };

  expect_member(&Decision::schema_version, {"schema"});
  expect_member(&Decision::run_id, {"run_id"});
  expect_member(&Decision::boot_id, {"boot_id"});
  expect_member(&Decision::contract_hash, {"contract_hash"});
  expect_member(&Decision::worker_instance, {"worker_instance"});
  expect_member(&Decision::mode, {"mode"});
  expect_member(&Decision::sequence, {"sequence"});
  expect_member(&Decision::tick, {"tick"});
  expect_member(&Decision::job_id, {"job_id"});
  expect_member(&Decision::task_generation, {"task_generation"});
  expect_member(&Decision::model_generation, {"model_generation"});
  expect_member(&Decision::config_generation, {"config_generation"});
  expect_member(&Decision::schedule_generation, {"schedule_generation"});
  expect_member(&Decision::clock_epoch, {"clock_epoch", "epoch"});
  expect_member(&Decision::tick_planned_ns, {"planned_ns"});
  expect_member(&Decision::tick_start_ns, {"start_ns"});
  expect_member(&Decision::cutoff_commit_ns, {"cutoff_commit_ns"});
  expect_member(&Decision::candidate_ready_commit_ns, {"ready_commit_ns"});
  expect_member(&Decision::activation_commit_ns, {"activation_commit_ns"});
  expect_member(&Decision::tick_end_ns, {"end_ns"});
  expect_member(&Decision::skipped_ticks, {"skipped_ticks"});
  expect_member(&Decision::candidate_accepted, {"candidate_accepted", "accepted"});
  expect_member(&Decision::diagnostic_only, {"diagnostic_only"});
  expect_member(&Decision::reason, {"reason"});
  expect_member(&Decision::control_source, {"control_source"});
  expect_member(&Decision::target_state, {"target_state"});
  expect_member(&Decision::activation_state, {"activation_state"});
  expect_member(&Decision::state_error, {"state_error"});
  expect_member(&Decision::requested_n, {"requested_n"});
  expect_member(&Decision::final_n, {"final_n"});
  expect_member(&Decision::publish_success, {"publish_success"});
  expect_member(&Decision::publish_start_ns, {"publish_start_ns"});
  expect_member(&Decision::publish_end_ns, {"publish_end_ns"});
  expect_member(&Decision::anchor_known, {"anchor_known"});
  expect_member(&Decision::anchor_sequence, {"anchor_sequence"});
  expect_member(&Decision::anchor_publish_ns, {"anchor_publish_ns"});
  expect_member(&Decision::previous_n, {"previous_n"});
  expect_member(&Decision::previous_publish_ns, {"previous_publish_ns"});
  expect_member(&Decision::odom_age_ns, {"odom_age_ns"});
  expect_member(&Decision::imu_age_ns, {"imu_age_ns"});
  expect_member(&Decision::clock_age_ns, {"clock_age_ns"});
  expect_member(&Decision::normal_contract_complete, {"normal_contract_complete"});
  expect_member(&Decision::rho_available, {"rho_available"});
  expect_member(&Decision::previous_anchor_known, {"previous_anchor_known"});
  expect_member(&Decision::publish_sim_ns, {"publish_sim_ns"});
  expect_member(&Decision::publish_epoch, {"publish_epoch"});
  expect_member(&Decision::publish_clock_age_ns, {"publish_clock_age_ns"});
  expect_member(&Decision::activation_clock_sim_ns, {"activation_clock_sim_ns"});
  expect_member(&Decision::activation_clock_receive_ns, {"activation_clock_receive_ns"});
  expect_member(&Decision::activation_rtf, {"activation_rtf"});
  expect_member(&Decision::activation_odom_stamp_ns, {"activation_odom_stamp_ns"});
  expect_member(&Decision::activation_odom_receive_ns, {"activation_odom_receive_ns"});
  expect_member(&Decision::activation_odom_sequence, {"activation_odom_sequence"});
  expect_member(&Decision::activation_imu_stamp_ns, {"activation_imu_stamp_ns"});
  expect_member(&Decision::activation_imu_receive_ns, {"activation_imu_receive_ns"});
  expect_member(&Decision::activation_imu_sequence, {"activation_imu_sequence"});
  expect_member(&Decision::activation_r_from_imu, {"activation_r_from_imu"});


  auto changed = original;
  changed.anchor_sequence = {41, 42};
  auto expected = baseline;
  expected["anchor_sequence"] = {41, 42};
  expected["plant_execution_index"] = 41;
  EXPECT_EQ(p1::decision_to_json(changed), expected);

  changed.plant_acceptance_observed = true;
  EXPECT_EQ(p1::decision_to_json(changed), expected);

  std::set<std::string> actual_keys;
  for (const auto & item : baseline.items()) actual_keys.insert(item.key());
  EXPECT_EQ(expected_keys.size(), 62u);
  EXPECT_EQ(actual_keys, expected_keys);
}

}  // namespace
