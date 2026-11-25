// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include "p1_contract.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iterator>
#include <string_view>
#include <limits>
#include <map>
#include <type_traits>
#include <utility>

#include "p1_sys_utils.hpp"
#include "usv_nmpc/mpc_solver.hpp"

namespace p1 {
namespace {

constexpr char kDiagnosticSchema[] = "p1-execution-contract-v2";
constexpr char kSimSchema[] = "p1-execution-contract-v2-sim";
constexpr char kFormalSchema[] = "p1-execution-contract-v3";
constexpr char kControlledSim[] = "controlled_sim";
constexpr std::size_t kMaxContractBytes = 65'536;

struct HydroField {
  const char * key;
  double usv_mpc::HydroParams::*member;
  Json baseline;
};

const HydroField kHydroFields[] = {
  {"mass", &usv_mpc::HydroParams::mass, 14.2},
  {"Iz", &usv_mpc::HydroParams::Iz, 2.13},
  {"xg", &usv_mpc::HydroParams::xg, 0.12},
  {"d_thruster", &usv_mpc::HydroParams::d_thruster, 0.25},
  {"Xu_dot", &usv_mpc::HydroParams::Xu_dot, -2},
  {"Yv_dot", &usv_mpc::HydroParams::Yv_dot, -8},
  {"Yr_dot", &usv_mpc::HydroParams::Yr_dot, -0.1817725},
  {"Nv_dot", &usv_mpc::HydroParams::Nv_dot, -0.1817725},
  {"Nr_dot", &usv_mpc::HydroParams::Nr_dot, -3.41},
  {"Xu", &usv_mpc::HydroParams::Xu, -2.272063},
  {"Yv", &usv_mpc::HydroParams::Yv, -2.629019},
  {"Yr", &usv_mpc::HydroParams::Yr, 0},
  {"Nv", &usv_mpc::HydroParams::Nv, 0},
  {"Nr", &usv_mpc::HydroParams::Nr, -3.105},
  {"Xuu", &usv_mpc::HydroParams::Xuu, -11.571784},
  {"Yvv", &usv_mpc::HydroParams::Yvv, -0.05},
  {"Yrr", &usv_mpc::HydroParams::Yrr, 0},
  {"Nvv", &usv_mpc::HydroParams::Nvv, 0},
  {"Nrr", &usv_mpc::HydroParams::Nrr, -0.71},
};

Json hydro_baseline() {
  auto result = Json::object();
  for (const auto & field : kHydroFields) result[field.key] = field.baseline;
  return result;
}

void read_hydro(ContractSpec & spec, const Json & value) {
  for (const auto & field : kHydroFields) {
    spec.mpc.hydro.*(field.member) = value.at(field.key).get<double>();
  }
}

Json write_hydro(const ContractSpec & spec) {
  auto result = Json::object();
  for (const auto & field : kHydroFields) result[field.key] = spec.mpc.hydro.*(field.member);
  return result;
}

void read_input_topics(ContractSpec & spec, const Json & value) {
  spec.topics.input_topics = {value.at("odom"), value.at("imu"), value.at("path"), value.at("profile")};
}

void read_output_topics(ContractSpec & spec, const Json & value) {
  spec.topics.output_topics = {value.at("left"), value.at("right")};
}

Json write_input_topics(const ContractSpec & spec) {
  const auto & topics = spec.topics.input_topics;
  return {{"odom", topics.odom}, {"imu", topics.imu}, {"path", topics.path}, {"profile", topics.profile}};
}

Json write_output_topics(const ContractSpec & spec) {
  const auto & topics = spec.topics.output_topics;
  return {{"left", topics.left}, {"right", topics.right}};
}

enum class Presence { Common, DiagnosticAndSim, Formal, Sim };
enum class Policy { Fixed, Profile, Resource };
enum class SimRule { Tunable, Fixed, Optional, Positive, Nonnegative };

struct FieldRule {
  const char * key;
  Json baseline;
  void (*read)(ContractSpec &, const Json &) = nullptr;
  Policy policy = Policy::Fixed;
  SimRule sim = SimRule::Tunable;
  Presence presence = Presence::Common;
  bool integer = false;
  bool solver_parameter = false;
  const char * section = nullptr;
  Json (*write)(const ContractSpec &) = nullptr;
};

// Setter and integer type are inferred from the member, independently of the
// baseline JSON's numeric representation (e.g. command_max_n is a double).
template<auto group, auto member>
void read_member(ContractSpec & spec, const Json & value) {
  using Value = std::decay_t<decltype((spec.*group).*member)>;
  (spec.*group).*member = value.get<Value>();
}

template<auto group, auto member>
Json write_member(const ContractSpec & spec) {
  return (spec.*group).*member;
}

template<class Group>
constexpr const char * section_name() {
  if constexpr (std::is_same_v<Group, ContractIdentity>) return "identity";
  if constexpr (std::is_same_v<Group, MpcSpec>) return "mpc";
  if constexpr (std::is_same_v<Group, ActuatorLimits>) return "actuator";
  if constexpr (std::is_same_v<Group, TimingSpec>) return "timing";
  if constexpr (std::is_same_v<Group, TopicFrameSpec>) return "topics";
  // Fault flags are derived from the profile, except for faults.enabled.
  return nullptr;
}

template<auto group, auto member>
FieldRule field(const char * key, Json baseline, SimRule sim = SimRule::Tunable,
                Policy policy = Policy::Fixed, Presence presence = Presence::Common,
                bool solver_parameter = false,
                const char * section = section_name<std::decay_t<decltype(std::declval<ContractSpec>().*group)>>()) {
  using Value = std::decay_t<decltype((std::declval<ContractSpec>().*group).*member)>;
  return {key, std::move(baseline), read_member<group, member>, policy, sim, presence,
          std::is_integral_v<Value> && !std::is_same_v<Value, bool>, solver_parameter,
          section, write_member<group, member>};
}

FieldRule resource_field(const char * key, Json baseline) {
  const bool integer = baseline.is_number_integer();
  return {key, std::move(baseline), nullptr, Policy::Resource, SimRule::Tunable,
          Presence::Common, integer};
}

constexpr auto identity = &ContractSpec::identity;
constexpr auto mpc = &ContractSpec::mpc;
constexpr auto actuator = &ContractSpec::actuator;
constexpr auto timing = &ContractSpec::timing;
constexpr auto topics = &ContractSpec::topics;
constexpr auto faults = &ContractSpec::faults;

std::vector<FieldRule> contract_field_rules() {
  std::vector<FieldRule> rules = {
    field<identity, &ContractIdentity::schema>(
      "schema", kDiagnosticSchema, SimRule::Tunable, Policy::Profile),
    field<identity, &ContractIdentity::qualification>(
      "qualification", "temporary_shadow_diagnostic", SimRule::Tunable, Policy::Profile),
    field<identity, &ContractIdentity::clock>("clock", "CLOCK_MONOTONIC", SimRule::Fixed),
    field<identity, &ContractIdentity::baseline_input>("baseline_input", "F5_20261005_atomic_freeze_01"),
    field<identity, &ContractIdentity::nominal_hash>(
      "nominal_hash", "78d7133fd4f11d47bd534d820b02489e440bd8664bef254893e830fe4bc7dc84"),
    field<identity, &ContractIdentity::diagnostic_contract_revision>(
      "diagnostic_contract_revision", 5, SimRule::Tunable, Policy::Profile, Presence::DiagnosticAndSim),
    field<identity, &ContractIdentity::execution_contract_revision>(
      "execution_contract_revision", 1, SimRule::Tunable, Policy::Profile, Presence::Formal),
    field<identity, &ContractIdentity::resource_contract_revision>(
      "resource_contract_revision", 1, SimRule::Tunable, Policy::Profile, Presence::Formal),
    field<identity, &ContractIdentity::supported_parameter_profile>(
      "supported_parameter_profile", contract_parameter_profile,
      SimRule::Tunable, Policy::Profile, Presence::Formal),
    field<identity, &ContractIdentity::freeze_evidence_sha256>(
      "freeze_evidence_sha256", "", SimRule::Tunable, Policy::Profile, Presence::Formal),

    // The generated solver, fixed-size ROS messages and plant execution grid
    // share these dimensions and time constants across all profiles.
    field<mpc, &MpcSpec::N>("N", 20, SimRule::Fixed, Policy::Fixed, Presence::Common, true),
    field<mpc, &MpcSpec::dt>("dt", 0.2, SimRule::Fixed, Policy::Fixed, Presence::Common, true),
    field<mpc, &MpcSpec::Q>("Q", {20, 20, 50, 8, 1, 8},
      SimRule::Nonnegative, Policy::Fixed, Presence::Common, true),
    field<mpc, &MpcSpec::R>("R", {0.05, 0.05},
      SimRule::Nonnegative, Policy::Fixed, Presence::Common, true),
    field<mpc, &MpcSpec::Rd>("Rd", {0.2, 0.2},
      SimRule::Nonnegative, Policy::Fixed, Presence::Common, true),
    field<mpc, &MpcSpec::Qf_scale>("Qf_scale", 8,
      SimRule::Nonnegative, Policy::Fixed, Presence::Common, true),
    {"hydro", hydro_baseline(), read_hydro, Policy::Fixed, SimRule::Tunable, Presence::Common,
      false, true, "mpc", write_hydro},
    field<mpc, &MpcSpec::reference_start_offset>("reference_start_offset", 2, SimRule::Nonnegative),
    field<mpc, &MpcSpec::cruise_speed>("cruise_speed", 0.6, SimRule::Nonnegative),

    field<actuator, &ActuatorLimits::command_min_n>("command_min_n", -25,
      SimRule::Tunable, Policy::Fixed, Presence::Common, true),
    field<actuator, &ActuatorLimits::command_max_n>("command_max_n", 25,
      SimRule::Tunable, Policy::Fixed, Presence::Common, true),
    field<actuator, &ActuatorLimits::map_scale>("map_scale", 1, SimRule::Positive),
    field<actuator, &ActuatorLimits::publisher_max_n>("publisher_max_n", 100, SimRule::Positive),
    field<actuator, &ActuatorLimits::backend_rate_n_s>("backend_rate_n_s", 80,
      SimRule::Positive, Policy::Fixed, Presence::Common, true),
    field<actuator, &ActuatorLimits::rho_n_s>("rho_n_s", 80, SimRule::Positive),
    field<actuator, &ActuatorLimits::hold_ns>("hold_ns", 600'000'000, SimRule::Positive),
    field<actuator, &ActuatorLimits::activation_tolerance>(
      "activation_tolerance", {0.25, 0.25, 0.15, 0.3, 0.2, 0.15}, SimRule::Positive),

    field<timing, &TimingSpec::T_ns>("T_ns", 200'000'000, SimRule::Fixed),
    field<timing, &TimingSpec::deadline_ns>("deadline_ns", 150'000'000, SimRule::Fixed),
    field<timing, &TimingSpec::odom_age_ns>("odom_age_ns", 100'000'000, SimRule::Positive),
    field<timing, &TimingSpec::imu_age_ns>("imu_age_ns", 100'000'000, SimRule::Positive),
    field<timing, &TimingSpec::mixed_skew_ns>("mixed_skew_ns", 100'000'000, SimRule::Positive),
    field<timing, &TimingSpec::clock_age_ns>("clock_age_ns", 100'000'000, SimRule::Positive),
    field<timing, &TimingSpec::rtf_low>("rtf_low", 0.95, SimRule::Positive),
    field<timing, &TimingSpec::rtf_high>("rtf_high", 1.05, SimRule::Positive),
    field<timing, &TimingSpec::clock_pause_confirm_ns>(
      "clock_pause_confirm_ns", 400'000'000, SimRule::Positive),
    field<timing, &TimingSpec::target_sim_slack_ns>("target_sim_slack_ns", 20'000'000, SimRule::Positive),
    field<timing, &TimingSpec::tick_jitter_ns>("tick_jitter_ns", 20'000'000, SimRule::Positive),
    field<timing, &TimingSpec::publish_gap_ns>("publish_gap_ns", 240'000'000, SimRule::Positive),
    field<timing, &TimingSpec::publish_budget_ns>("publish_budget_ns", 5'000'000, SimRule::Positive),
    field<timing, &TimingSpec::active_watchdog_ns>("active_watchdog_ns", 1'000'000'000, SimRule::Positive),
    field<timing, &TimingSpec::worker_grace_ns>("worker_grace_ns", 500'000'000, SimRule::Positive),
    field<timing, &TimingSpec::term_grace_ns>("term_grace_ns", 1'000'000'000, SimRule::Positive),
    field<timing, &TimingSpec::kill_postcheck_ns>("kill_postcheck_ns", 1'000'000'000, SimRule::Positive),
    field<timing, &TimingSpec::shutdown_grace_ns>("shutdown_grace_ns", 2'500'000'000LL, SimRule::Positive),
    field<timing, &TimingSpec::odom_sim_lag_ns>("odom_sim_lag_ns", 100'000'000, SimRule::Positive),
    field<timing, &TimingSpec::imu_sim_lag_ns>("imu_sim_lag_ns", 100'000'000, SimRule::Positive),
    field<timing, &TimingSpec::source_future_slack_ns>(
      "source_future_slack_ns", 20'000'000, SimRule::Positive),
    field<timing, &TimingSpec::recording_ready_timeout_ns>(
      "recording_ready_timeout_ns", 10'000'000'000LL, SimRule::Positive),
    field<timing, &TimingSpec::worker_capability_receipt_timeout_ns>(
      "worker_capability_receipt_timeout_ns", 600'000'000, SimRule::Positive),

    {"input_topics", {
      {"odom", "/wamv/sensors/position/ground_truth_odometry"},
      {"imu", "/wamv/sensors/imu/imu/data"},
      {"path", "/path/reference"},
      {"profile", "/path/reference_profile"},
    }, read_input_topics, Policy::Fixed, SimRule::Tunable, Presence::Common,
      false, false, "topics", write_input_topics},
    {"output_topics", {
      {"left", "/wamv/thrusters/left/thrust"},
      {"right", "/wamv/thrusters/right/thrust"},
    }, read_output_topics, Policy::Fixed, SimRule::Tunable, Presence::Common,
      false, false, "topics", write_output_topics},
    field<topics, &TopicFrameSpec::expected_pose_frame>("expected_pose_frame", "map"),
    field<topics, &TopicFrameSpec::expected_child_frame>("expected_child_frame", "wamv/base_link"),
    field<topics, &TopicFrameSpec::expected_imu_frame>(
      "expected_imu_frame", "wamv/wamv/base_link/imu_sensor"),

    field<faults, &FaultAndReleaseSpec::execute_qualified>(
      "execute_qualified", false, SimRule::Fixed, Policy::Profile),
    field<faults, &FaultAndReleaseSpec::fault_injection_enabled>(
      "fault_injection_enabled", true, SimRule::Tunable, Policy::Profile),
    field<faults, &FaultAndReleaseSpec::controlled_sim_faults_enabled>(
      "controlled_sim_faults_enabled", false, SimRule::Tunable, Policy::Profile, Presence::Sim),
    field<faults, &FaultAndReleaseSpec::parameters_are_diagnostic_only>(
      "parameters_are_diagnostic_only", true, SimRule::Fixed, Policy::Profile),
    field<faults, &FaultAndReleaseSpec::pending_final_calibration>("pending_final_calibration", {
      "rho_n_s", "hold_ns", "activation_tolerance", "source ages", "RTF and pause",
      "jitter/gap/publish", "watchdog and cleanup",
      "worker capability validated callback receipt lease; no source packet sequence/send time",
    }, SimRule::Tunable, Policy::Profile, Presence::Common, false, "identity"),
    field<faults, &FaultAndReleaseSpec::worker_failure_policy>(
      "worker_failure_policy", "terminal_on_failed_or_invalid_native_result", SimRule::Fixed,
      Policy::Fixed, Presence::Common, false, "identity"),
    field<faults, &FaultAndReleaseSpec::worker_capability_lease_policy>(
      "worker_capability_lease_policy",
      "valid_identity_capability_callback_receipt_lease_terminal_until_new_run", SimRule::Fixed,
      Policy::Fixed, Presence::Common, false, "identity"),
    field<faults, &FaultAndReleaseSpec::worker_capability_source_freshness_available>(
      "worker_capability_source_freshness_available", false, SimRule::Fixed,
      Policy::Fixed, Presence::Common, false, "identity"),

    {"propagation_semantics",
      "publisher-side piecewise held history from accepted odom stamp, mixed r retained with "
      "separate IMU stamp; future held current command; RK4 nominal point prediction",
      nullptr, Policy::Fixed, SimRule::Optional, Presence::Common, false, false, "mpc"},
    {"source_age_semantics",
      "receipt age uses CLOCK_MONOTONIC; physical source lag/future uses clock sim plus 1:1 "
      "monotonic elapsed; IMU only when mixed", nullptr, Policy::Fixed, SimRule::Optional, Presence::Common, false, false, "timing"},
  };
  for (const auto & [key, value] : resource_detail::kPolicyFields) {
    rules.push_back(resource_field(key, value));
  }
  for (const auto & field : resource_detail::kLimitFields) {
    const auto value = field.member ? resource_detail::kDefaultLimits.*(field.member) : field.max;
    rules.push_back(resource_field(field.key, value));
  }
  return rules;
}

const auto kContractFieldRules = contract_field_rules();

bool in_baseline(const FieldRule & rule) {
  return rule.presence == Presence::Common || rule.presence == Presence::DiagnosticAndSim;
}

const auto & rules_by_key() {
  // Retain the validation order of the existing sorted JSON object.
  static const auto rules = [] {
    std::map<std::string, const FieldRule *> result;
    for (const auto & rule : kContractFieldRules) result.emplace(rule.key, &rule);
    return result;
  }();
  return rules;
}

template<class Predicate>
std::set<std::string> select_baseline_keys(Predicate predicate) {
  std::set<std::string> keys;
  for (const auto & rule : kContractFieldRules) {
    if (in_baseline(rule) && predicate(rule)) keys.emplace(rule.key);
  }
  return keys;
}

bool is_sha256(const std::string & value) {
  return value.size() == 64 && std::all_of(value.begin(), value.end(), [](char ch) {
    return (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f');
  });
}

bool applies(const FieldRule & rule, bool formal, bool sim) {
  switch (rule.presence) {
    case Presence::Common: return true;
    case Presence::DiagnosticAndSim: return !formal;
    case Presence::Formal: return formal;
    case Presence::Sim: return sim;
  }
  return false;
}

void check_sim_value(const FieldRule & rule, const Json & value) {
  const std::string key(rule.key);
  if (rule.sim == SimRule::Fixed) {
    contract_require(value == rule.baseline, "unsupported fixed candidate parameter: " + key);
  }
  if (rule.sim == SimRule::Positive || rule.sim == SimRule::Nonnegative) {
    const bool positive = rule.sim == SimRule::Positive;
    const auto in_range = [positive](const Json & item) {
      return positive ? item.get<double>() > 0 : item.get<double>() >= 0;
    };
    const bool valid = value.is_array()
      ? std::all_of(value.begin(), value.end(), in_range) : in_range(value);
    contract_require(valid, "numeric bound: " + key);
  }
}

void validate_sim_spec(const ContractSpec & spec) {
  contract_require(is_sha256(spec.identity.nominal_hash), "nominal SHA256 identity required");
  contract_require(!spec.identity.baseline_input.empty(), "baseline input identity required");
  const auto & hydro = spec.mpc.hydro;
  contract_require(hydro.mass > 0 && hydro.Iz > 0 && hydro.d_thruster > 0,
    "positive hydro mass, Iz and d_thruster required");
  const auto & act = spec.actuator;
  contract_require(act.command_min_n <= 0 && act.command_max_n >= 0 &&
    act.command_min_n < act.command_max_n, "invalid command bounds");
  const auto & time = spec.timing;
  contract_require(time.rtf_low <= time.rtf_high, "invalid RTF bounds");
  contract_require(time.recording_ready_timeout_ns <= 60'000'000'000LL,
    "invalid finite recording timeout");
  contract_require(time.worker_capability_receipt_timeout_ns >= time.T_ns &&
    time.worker_capability_receipt_timeout_ns <= 5'000'000'000LL,
    "capability receipt lease outside finite diagnostic bounds");
  const auto & names = spec.topics;
  for (const auto * frame :
       {&names.expected_pose_frame, &names.expected_child_frame, &names.expected_imu_frame}) {
    contract_require(!frame->empty() && frame->size() <= 128, "invalid bounded expected frame");
  }
  for (const auto * topic :
       {&names.input_topics.odom, &names.input_topics.imu, &names.input_topics.path, &names.input_topics.profile,
        &names.output_topics.left, &names.output_topics.right}) {
    contract_require(!topic->empty(), "nonempty contract topic required");
  }
}

ContractProfile decode_legacy_contract(
  const Json & c, ContractSpec & spec, const ResourceLimits * grouped_limits = nullptr) {
  const auto & schema = c.at("schema").get_ref<const std::string &>();
  const bool formal = schema == kFormalSchema;
  const bool sim = schema == kSimSchema;
  contract_require(formal || sim || schema == kDiagnosticSchema, "unknown schema");

  if (sim) {
    contract_require(c.contains("qualification") && c.at("qualification") == kControlledSim,
      "sim schema requires controlled_sim qualification");
    contract_require(c.contains("fault_injection_enabled"), "sim schema requires the fault flag");
    contract_require(c.contains("controlled_sim_faults_enabled") &&
      c.at("controlled_sim_faults_enabled").is_boolean(),
      "sim schema requires the controlled_sim faults flag");
    spec.resources = grouped_limits ? *grouped_limits : resource_limits_from_contract(c);
  } else {
    const auto expected_size = std::count_if(std::begin(kContractFieldRules),
      std::end(kContractFieldRules), [formal](const auto & rule) { return applies(rule, formal, false); });
    contract_require(c.size() == static_cast<std::size_t>(expected_size),
      "missing or unknown top-level fields");
  }

  for (const auto & [key, rule] : rules_by_key()) {
    if (!applies(*rule, formal, sim) || (sim && rule->sim == SimRule::Optional)) continue;
    contract_require(c.contains(key), "missing field: " + key);
  }

  for (const auto & [key, rule] : rules_by_key()) {
    if (!applies(*rule, formal, sim) || (sim && !c.contains(key))) continue;
    // Formal-only markers retain the existing checks and error messages below.
    if (rule->presence == Presence::Formal) continue;
    if (sim && rule->policy == Policy::Resource) continue;
    const auto & value = c.at(key);
    contract_value_type(value, rule->baseline, key);
    if (sim) {
      check_sim_value(*rule, value);
      if (key == "reference_start_offset") {
        // The reference builder adds this offset to the nearest path index.
        const auto max_path_index = static_cast<std::int64_t>(spec.resources.max_path_points - 1);
        contract_require(value.get<std::int64_t>() <=
          std::numeric_limits<int>::max() - max_path_index, "reference_start_offset exceeds int range");
      }
    } else if (rule->policy == Policy::Fixed) {
      contract_require(value == rule->baseline, "unsupported fixed candidate parameter: " + key);
    }
    if (rule->read) rule->read(spec, value);
  }

  if (sim) {
    validate_sim_spec(spec);
    return ContractProfile::ControlledSim;
  }

  spec.resources = grouped_limits ? *grouped_limits : resource_limits_from_contract(c);
  if (!formal) {
    for (const auto & key : special_contract_fields()) {
      contract_require(c.at(key) == candidate_baseline().at(key),
        "diagnostic flag or policy mismatch: " + key);
    }
    return ContractProfile::Diagnostic;
  }

  for (const auto & [key, rule] : rules_by_key()) {
    if (rule->presence != Presence::Formal) continue;
    const auto & value = c.at(key);
    if (rule->integer) {
      contract_require(strict_i64(value) && value == rule->baseline, "unsupported formal revision: " + key);
    } else if (key == "supported_parameter_profile") {
      contract_require(value.is_string() && value == rule->baseline, "unsupported parameter profile");
    } else {
      contract_require(value.is_string(), "freeze evidence marker type");
    }
    rule->read(spec, value);
  }

  const auto & flags = spec.faults;
  const auto & evidence = spec.identity.freeze_evidence_sha256;
  contract_require(!flags.fault_injection_enabled, "formal fault injection prohibited");
  if (spec.identity.qualification == "execution_pre_freeze") {
    contract_require(!flags.execute_qualified && flags.parameters_are_diagnostic_only,
      "pre-freeze qualification flags");
    contract_require(c.at("pending_final_calibration") ==
      candidate_baseline().at("pending_final_calibration") && evidence.empty(),
      "pre-freeze pending evidence");
    return ContractProfile::PreFreeze;
  }
  contract_require(spec.identity.qualification == "execution_frozen", "unknown formal qualification");
  contract_require(flags.execute_qualified && !flags.parameters_are_diagnostic_only,
    "frozen qualification flags");
  contract_require(flags.pending_final_calibration.empty(), "frozen pending calibration remains");
  contract_require(is_sha256(evidence), "frozen evidence hash marker");
  return ContractProfile::Frozen;
}

constexpr std::pair<std::string_view, ContractProfile> kV4Profiles[] = {
  {"diagnostic", ContractProfile::Diagnostic},
  {"controlled_sim", ContractProfile::ControlledSim},
  {"pre_freeze", ContractProfile::PreFreeze},
  {"frozen", ContractProfile::Frozen},
};

Json v4_profile_baseline(ContractProfile profile) {
  auto baseline = candidate_baseline();
  if (profile == ContractProfile::ControlledSim) {
    baseline["schema"] = kSimSchema;
    baseline["qualification"] = kControlledSim;
    baseline["controlled_sim_faults_enabled"] = false;
  } else if (profile == ContractProfile::PreFreeze || profile == ContractProfile::Frozen) {
    const bool frozen = profile == ContractProfile::Frozen;
    baseline.erase("diagnostic_contract_revision");
    for (const auto & rule : kContractFieldRules) {
      if (rule.presence == Presence::Formal) baseline[rule.key] = rule.baseline;
    }
    baseline["schema"] = kFormalSchema;
    baseline["qualification"] = frozen ? "execution_frozen" : "execution_pre_freeze";
    baseline["fault_injection_enabled"] = false;
    baseline["execute_qualified"] = frozen;
    baseline["parameters_are_diagnostic_only"] = !frozen;
    if (frozen) baseline["pending_final_calibration"] = Json::array();
  }
  return baseline;
}

bool v4_has_field(const FieldRule & rule, const Json & baseline) {
  const std::string_view key = rule.key;
  return rule.section && key != "schema" && key != "qualification" && baseline.contains(rule.key);
}

void apply_v4_override(Json & value, const Json & override_value, const std::string & path) {
  if (!value.is_object()) {
    value = override_value;
    return;
  }
  contract_require(override_value.is_object(), "object required: " + path);
  for (auto it = override_value.begin(); it != override_value.end(); ++it) {
    const auto child_path = path + "." + it.key();
    contract_require(value.contains(it.key()), "unknown field: " + child_path);
    apply_v4_override(value.at(it.key()), it.value(), child_path);
  }
}

ContractProfile decode_v4_contract(const Json & contract, ContractSpec & spec) {
  const auto profile_key = contract.find("profile");
  contract_require(profile_key != contract.end() && profile_key->is_string(), "v4 profile required");
  const auto & name = profile_key->get_ref<const std::string &>();
  const auto entry = std::find_if(std::begin(kV4Profiles), std::end(kV4Profiles),
    [&name](const auto & item) { return item.first == name; });
  contract_require(entry != std::end(kV4Profiles), "unknown v4 profile");
  const auto profile = entry->second;
  auto expanded = v4_profile_baseline(profile);
  const bool sim = profile == ContractProfile::ControlledSim;
  const bool diagnostic = profile == ContractProfile::Diagnostic;
  bool faults_enabled = diagnostic;
  bool has_faults_enabled = false;

  for (auto section = contract.begin(); section != contract.end(); ++section) {
    const auto & key = section.key();
    if (key == "schema" || key == "profile" || key == "resources") continue;
    contract_require(key == "identity" || key == "mpc" || key == "actuator" ||
      key == "timing" || key == "topics" || key == "faults", "unknown v4 section: " + key);
    contract_require(section->is_object(), "object required: " + key);
    for (auto it = section->begin(); it != section->end(); ++it) {
      const auto path = key + "." + it.key();
      if (key == "faults") {
        contract_require(it.key() == "enabled", "unknown field: " + path);
        contract_require(it->is_boolean(), "bool required: " + path);
        faults_enabled = it->get<bool>();
        has_faults_enabled = true;
        continue;
      }
      const auto rule = rules_by_key().find(it.key());
      contract_require(rule != rules_by_key().end() && v4_has_field(*rule->second, expanded) &&
        key == rule->second->section, "unknown field: " + path);
      if (rule->second->sim == SimRule::Optional ||
          (rule->second->integer && rule->second->policy == Policy::Profile)) {
        contract_require(*it == rule->second->baseline, "unsupported fixed candidate parameter: " + path);
      }
      apply_v4_override(expanded.at(it.key()), *it, path);
    }
  }

  contract_require(!sim || has_faults_enabled, "controlled_sim requires faults.enabled");
  contract_require(sim || diagnostic || !faults_enabled, "formal fault injection prohibited");
  if (sim) expanded["controlled_sim_faults_enabled"] = faults_enabled;

  const auto resources = resource_limits_from_contract(contract);
  decode_legacy_contract(expanded, spec, &resources);
  if (diagnostic) spec.faults.fault_injection_enabled = faults_enabled;
  return profile;
}

ContractProfile decode_contract(const Json & contract, ContractSpec & spec) {
  contract_require(contract.is_object() && contract.contains("schema") && contract.at("schema").is_string(),
    "schema object required");
  if (contract.at("schema") == grouped_contract_schema) return decode_v4_contract(contract, spec);
  return decode_legacy_contract(contract, spec);
}

void emit_v4_field(Json & section, const std::string & key, const Json & value,
                   const Json & baseline, bool minimal) {
  // JSON equality treats finite numeric representations equivalently, as do the
  // fixed-value checks. Reject a nonfinite override during validation below.
  if (!minimal) {
    section[key] = value;
  } else if (value.is_object()) {
    auto overrides = Json::object();
    for (auto item = value.begin(); item != value.end(); ++item) {
      emit_v4_field(overrides, item.key(), item.value(), baseline.at(item.key()), true);
    }
    if (!overrides.empty()) section[key] = std::move(overrides);
  } else if (value != baseline) {
    section[key] = value;
  }
}

}  // namespace

const Json & candidate_baseline() {
  static const auto baseline = [] {
    auto value = Json::object();
    for (const auto & rule : kContractFieldRules) {
      if (in_baseline(rule)) value[rule.key] = rule.baseline;
    }
    return value;
  }();
  return baseline;
}

Json to_v4_contract_json(const ContractSpec & spec, ContractProfile profile, bool minimal) {
  const auto entry = std::find_if(std::begin(kV4Profiles), std::end(kV4Profiles),
    [profile](const auto & item) { return item.second == profile; });
  contract_require(entry != std::end(kV4Profiles), "unknown v4 profile");
  const auto baseline = v4_profile_baseline(profile);
  Json contract = {{"schema", grouped_contract_schema}, {"profile", entry->first}};
  for (const auto & rule : kContractFieldRules) {
    if (!v4_has_field(rule, baseline)) continue;
    const auto & default_value = baseline.at(rule.key);
    auto section = contract.find(rule.section);
    if (section == contract.end()) section = contract.emplace(rule.section, Json::object()).first;
    emit_v4_field(*section, rule.key, rule.write ? rule.write(spec) : default_value,
      default_value, minimal);
  }

  auto resources = Json::object();
  for (const auto & field : resource_detail::kLimitFields) {
    const auto value = field.member ? spec.resources.*(field.member) : field.max;
    emit_v4_field(resources, field.key, value, baseline.at(field.key), minimal);
  }
  if (!minimal) {
    for (const auto & [key, value] : resource_detail::kPolicyFields) resources[key] = value;
  }
  if (!resources.empty()) contract["resources"] = std::move(resources);

  const bool enabled = spec.faults.faults_enabled(profile);
  if (!minimal || profile == ContractProfile::ControlledSim ||
      enabled != (profile == ContractProfile::Diagnostic)) {
    contract["faults"] = {{"enabled", enabled}};
  }
  for (auto it = contract.begin(); it != contract.end();) {
    if (it->is_object() && it->empty()) it = contract.erase(it);
    else ++it;
  }
  validate_contract_fields(contract);
  return contract;
}

const std::set<std::string> & integer_contract_fields() {
  static const auto keys = select_baseline_keys([](const auto & rule) { return rule.integer; });
  return keys;
}

const std::set<std::string> & resource_contract_fields() {
  static const auto keys = select_baseline_keys([](const auto & rule) {
    return rule.policy == Policy::Resource;
  });
  return keys;
}

const std::set<std::string> & special_contract_fields() {
  static const auto keys = select_baseline_keys([](const auto & rule) {
    return rule.policy == Policy::Profile;
  });
  return keys;
}

void contract_require(bool okay, const std::string & reason) {
  if (!okay) throw std::runtime_error("contract validation: " + reason);
}

bool strict_i64(const Json & value) {
  return value.is_number_integer() && (!value.is_number_unsigned() ||
    value.get<std::uint64_t>() <= std::uint64_t(std::numeric_limits<std::int64_t>::max()));
}

void contract_value_type(const Json & actual, const Json & expected, const std::string & key) {
  if (expected.is_boolean()) {
    contract_require(actual.is_boolean(), "bool required: " + key);
  } else if (expected.is_number()) {
    contract_require(actual.is_number() && std::isfinite(actual.get<double>()),
      "finite number required: " + key);
    if (integer_contract_fields().count(key)) {
      contract_require(strict_i64(actual), "int64 JSON integer required: " + key);
    }
  } else if (expected.is_string()) {
    contract_require(actual.is_string(), "string required: " + key);
  } else if (expected.is_array()) {
    contract_require(actual.is_array(), "array required: " + key);
    if (key == "pending_final_calibration") {
      contract_require(actual.size() <= 32, "pending list bound");
      for (const auto & item : actual) {
        contract_require(item.is_string() && !item.get_ref<const std::string &>().empty() &&
          item.get_ref<const std::string &>().size() <= 256, "pending string bound");
      }
    } else {
      contract_require(actual.size() == expected.size(), "array shape: " + key);
      for (std::size_t i = 0; i < actual.size(); ++i) {
        contract_value_type(actual[i], expected[i], key);
      }
    }
  } else if (expected.is_object()) {
    contract_require(actual.is_object() && actual.size() == expected.size(), "object shape: " + key);
    for (auto it = expected.begin(); it != expected.end(); ++it) {
      contract_require(actual.contains(it.key()), "nested field missing: " + key + "." + it.key());
      contract_value_type(actual.at(it.key()), it.value(), it.key());
    }
  } else {
    contract_require(false, "unsupported normative value type");
  }
}

Json parse_unique_contract(const std::string & text) {
  contract_require(!text.empty() && text.size() <= kMaxContractBytes, "bounded contract file required");
  std::vector<std::set<std::string>> objects;
  auto callback = [&objects](int, Json::parse_event_t event, Json & value) {
    switch (event) {
      case Json::parse_event_t::object_start: objects.emplace_back(); break;
      case Json::parse_event_t::key:
        if (objects.empty() || !objects.back().insert(value.get<std::string>()).second) {
          throw std::runtime_error("duplicate contract JSON key");
        }
        break;
      case Json::parse_event_t::object_end: objects.pop_back(); break;
      default: break;
    }
    return true;
  };
  return Json::parse(text, callback);
}

ContractProfile validate_contract_fields(const Json & contract) {
  ContractSpec spec;
  return decode_contract(contract, spec);
}

void validate_contract_mode(ContractProfile profile, const std::string & mode) {
  bool okay = false;
  switch (profile) {
    case ContractProfile::ControlledSim: okay = mode == kControlledSim; break;
    case ContractProfile::Diagnostic: okay = mode == "no_output" || mode == "shadow"; break;
    case ContractProfile::PreFreeze: okay = mode == "no_output"; break;
    case ContractProfile::Frozen: okay = mode == "no_output" || mode == "execute"; break;
  }
  contract_require(okay, "profile/mode mismatch");
}

void validate_contract_mode(const Json & contract, const std::string & mode) {
  validate_contract_mode(validate_contract_fields(contract), mode);
}

void require_runtime_contract_mode(ContractProfile profile, const std::string & mode) {
  validate_contract_mode(profile, mode);
  if (mode == "execute" && !physical_execute_release_enabled) {
    throw std::runtime_error("physical execute release is disabled until B5/M4");
  }
}

void require_runtime_contract_mode(const Json & contract, const std::string & mode) {
  require_runtime_contract_mode(validate_contract_fields(contract), mode);
}

LoadedContract load_verified_contract(const std::string & file, const std::string & hash) {
  contract_require(is_sha256(hash), "SHA256 identity required");
  std::ifstream input(file, std::ios::binary);
  if (!input) throw std::runtime_error("contract read failed");
  std::string text(kMaxContractBytes + 1, '\0');
  input.read(text.data(), text.size());
  text.resize(static_cast<std::size_t>(input.gcount()));
  contract_require(!text.empty() && text.size() <= kMaxContractBytes, "bounded contract file required");
  if (digest(text) != hash) throw std::runtime_error("contract hash mismatch");

  auto raw = parse_unique_contract(text);
  ContractSpec spec;
  const auto profile = decode_contract(raw, spec);
  return {profile, std::move(spec), std::move(raw)};
}

LoadedContract load_verified_contract(
  const std::string & file, const std::string & hash, const std::string & mode) {
  auto loaded = load_verified_contract(file, hash);
  validate_contract_mode(loaded.profile, mode);
  return loaded;
}

Json load_contract(const std::string & file, const std::string & hash) {
  return load_verified_contract(file, hash).raw;
}

usv_mpc::MpcParams solver_params(const ContractSpec & spec) {
  usv_mpc::MpcParams params;
  params.N = spec.mpc.N;
  params.dt = spec.mpc.dt;
  params.Q_diag = Eigen::Map<const usv_mpc::Vector6d>(spec.mpc.Q.data());
  params.R_diag = Eigen::Map<const Eigen::Vector2d>(spec.mpc.R.data());
  params.Rd_diag = Eigen::Map<const Eigen::Vector2d>(spec.mpc.Rd.data());
  params.Qf_scale = spec.mpc.Qf_scale;
  params.T_min = spec.actuator.command_min_n;
  params.T_max = spec.actuator.command_max_n;
  params.dT_max = spec.actuator.backend_rate_n_s;
  params.hydro = spec.mpc.hydro;
  return params;
}

usv_mpc::MpcParams solver_params(const Json & contract) {
  ContractSpec spec;
  if (contract.is_object() && contract.contains("schema") && contract.at("schema") == grouped_contract_schema) {
    decode_v4_contract(contract, spec);
    return solver_params(spec);
  }
  for (const auto & rule : kContractFieldRules) {
    if (rule.solver_parameter) rule.read(spec, contract.at(rule.key));
  }
  return solver_params(spec);
}

}  // namespace p1
