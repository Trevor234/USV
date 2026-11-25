// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#pragma once

#include <array>
#include <cstdint>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "p1_resources.hpp"
#include "usv_nmpc/usv_model_dynamic.hpp"

namespace usv_mpc {
struct MpcParams;
}

namespace p1 {

using Json = nlohmann::json;

inline constexpr bool physical_execute_release_enabled = false;
inline constexpr const char * contract_parameter_profile = "F5_P1_candidate_20261007_01";
inline constexpr const char * full_contract_spec_sha256 =
  "33fb4a5eef93aa6abce5a61e7549dd7217f90c9572e5097791731fbb89661ffd";

enum class ContractProfile { Diagnostic, PreFreeze, Frozen, ControlledSim };

struct ContractIdentity {
  std::string schema;  // Normalized profile schema. LoadedContract::raw retains the input schema.
  std::string qualification;
  std::string clock;
  std::string baseline_input;
  std::string nominal_hash;
  std::int64_t diagnostic_contract_revision = 0;
  std::int64_t execution_contract_revision = 0;
  std::int64_t resource_contract_revision = 0;
  std::string supported_parameter_profile;
  std::string freeze_evidence_sha256;
};

struct MpcSpec {
  int N = 0;
  double dt = 0;
  std::array<double, 6> Q{};
  std::array<double, 2> R{};
  std::array<double, 2> Rd{};
  double Qf_scale = 0;
  usv_mpc::HydroParams hydro;
  int reference_start_offset = 0;
  double cruise_speed = 0;
};

struct ActuatorLimits {
  double command_min_n = 0;
  double command_max_n = 0;
  double map_scale = 0;
  double publisher_max_n = 0;
  double backend_rate_n_s = 0;
  double rho_n_s = 0;
  std::int64_t hold_ns = 0;
  std::array<double, 6> activation_tolerance{};
};

struct TimingSpec {
  std::int64_t T_ns = 0;
  std::int64_t deadline_ns = 0;
  std::int64_t odom_age_ns = 0;
  std::int64_t imu_age_ns = 0;
  std::int64_t mixed_skew_ns = 0;
  std::int64_t clock_age_ns = 0;
  double rtf_low = 0;
  double rtf_high = 0;
  std::int64_t clock_pause_confirm_ns = 0;
  std::int64_t target_sim_slack_ns = 0;
  std::int64_t tick_jitter_ns = 0;
  std::int64_t publish_gap_ns = 0;
  std::int64_t publish_budget_ns = 0;
  std::int64_t active_watchdog_ns = 0;
  std::int64_t worker_grace_ns = 0;
  std::int64_t term_grace_ns = 0;
  std::int64_t kill_postcheck_ns = 0;
  std::int64_t shutdown_grace_ns = 0;
  std::int64_t odom_sim_lag_ns = 0;
  std::int64_t imu_sim_lag_ns = 0;
  std::int64_t source_future_slack_ns = 0;
  std::int64_t recording_ready_timeout_ns = 0;
  std::int64_t worker_capability_receipt_timeout_ns = 0;
};

struct TopicFrameSpec {
  struct InputTopics {
    std::string odom;
    std::string imu;
    std::string path;
    std::string profile;
  } input_topics;
  struct OutputTopics {
    std::string left;
    std::string right;
  } output_topics;
  std::string expected_pose_frame;
  std::string expected_child_frame;
  std::string expected_imu_frame;
};

struct FaultAndReleaseSpec {
  bool execute_qualified = false;
  bool fault_injection_enabled = false;
  bool controlled_sim_faults_enabled = false;
  bool parameters_are_diagnostic_only = false;
  bool worker_capability_source_freshness_available = false;
  std::vector<std::string> pending_final_calibration;
  std::string worker_failure_policy;
  std::string worker_capability_lease_policy;

  bool faults_enabled(ContractProfile profile) const noexcept {
    return profile == ContractProfile::ControlledSim
      ? controlled_sim_faults_enabled : fault_injection_enabled;
  }
};

struct ContractSpec {
  ContractIdentity identity;
  MpcSpec mpc;
  ActuatorLimits actuator;
  TimingSpec timing;
  TopicFrameSpec topics;
  FaultAndReleaseSpec faults;
  ResourceLimits resources;
};

struct LoadedContract {
  ContractProfile profile;
  ContractSpec spec;
  nlohmann::json raw;
};

LoadedContract load_verified_contract(const std::string & file, const std::string & hash);
LoadedContract load_verified_contract(
  const std::string & file, const std::string & hash, const std::string & mode);
Json load_contract(const std::string & file, const std::string & hash);

usv_mpc::MpcParams solver_params(const ContractSpec & spec);
usv_mpc::MpcParams solver_params(const Json & contract);

Json parse_unique_contract(const std::string & text);
// Emit the profile and overrides. Full form also includes the compiled defaults.
Json to_v4_contract_json(const ContractSpec & spec, ContractProfile profile, bool minimal = true);
ContractProfile validate_contract_fields(const Json & contract);
void validate_contract_mode(ContractProfile profile, const std::string & mode);
void validate_contract_mode(const Json & contract, const std::string & mode);
void require_runtime_contract_mode(ContractProfile profile, const std::string & mode);
void require_runtime_contract_mode(const Json & contract, const std::string & mode);

// Compatibility helpers used by the diagnostic contract and its callers.
const Json & candidate_baseline();
const std::set<std::string> & integer_contract_fields();
const std::set<std::string> & resource_contract_fields();
const std::set<std::string> & special_contract_fields();
void contract_require(bool okay, const std::string & reason);
bool strict_i64(const Json & value);
void contract_value_type(const Json & actual, const Json & expected, const std::string & key);

}  // namespace p1
