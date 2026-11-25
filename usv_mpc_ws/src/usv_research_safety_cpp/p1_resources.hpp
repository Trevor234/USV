// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <nlohmann/json.hpp>

namespace p1 {

// These bounds protect application work after a typed callback begins. They do
// not constrain memory already allocated by the middleware/deserializer.
inline constexpr const char * resource_policy_v1 = "typed_domain_bounds_before_copy_v1";
inline constexpr const char * resource_cdr_encoding_v1 =
  "application_typed_domain_cdr1_with_4_byte_encapsulation";
inline constexpr size_t resource_history_hard_cap = 256;
inline constexpr size_t resource_path_hard_cap = 2048;
inline constexpr size_t resource_profile_hard_cap = 2048;
inline constexpr size_t resource_log_hard_cap = 512;
inline constexpr size_t resource_job_byte_hard_cap = 8192;
inline constexpr size_t resource_candidate_byte_hard_cap = 16384;

inline constexpr char grouped_contract_schema[] = "p1-contract-v4";

struct ResourceLimits {
  size_t max_job_bytes = resource_job_byte_hard_cap;
  size_t max_candidate_bytes = resource_candidate_byte_hard_cap;
  size_t history_capacity = resource_history_hard_cap;
  size_t max_path_points = resource_path_hard_cap;
  size_t max_profile_rows = resource_profile_hard_cap;
  size_t log_capacity = resource_log_hard_cap;
  size_t dds_depth = 1;
  size_t max_profile_dims = 4;
  size_t max_profile_label_bytes = 64;
  size_t max_path_frame_bytes = 128;
};

// Error metadata is fixed and contains no copy of the rejected payload.
struct ResourceCheck {
  const char * reason = "";
  const char * field = "";
  size_t observed = 0;
  size_t limit = 0;
  explicit operator bool() const noexcept { return reason[0] == '\0'; }
};

namespace resource_detail {
template<class Measure>
struct WireField {
  const char * name;
  size_t max_size;
  Measure measure;
  size_t element_bytes = 1;
};

template<class Measure>
WireField(const char *, size_t, Measure, size_t = 1) -> WireField<Measure>;

inline constexpr size_t kSchemaBytes = 64;
inline constexpr size_t kRunIdBytes = 128;
inline constexpr size_t kBootIdBytes = 64;
inline constexpr size_t kHashBytes = 64;
inline constexpr size_t kWorkerInstanceBytes = 64;
inline constexpr size_t kReasonBytes = 256;
inline constexpr size_t kBackendBytes = 16;

inline constexpr auto kJobStringFields = std::make_tuple(
  WireField{"job.schema_version", kSchemaBytes, [](const auto & m) { return m.schema_version.size(); }},
  WireField{"job.run_id", kRunIdBytes, [](const auto & m) { return m.run_id.size(); }},
  WireField{"job.boot_id", kBootIdBytes, [](const auto & m) { return m.boot_id.size(); }},
  WireField{"job.contract_hash", kHashBytes, [](const auto & m) { return m.contract_hash.size(); }},
  WireField{"job.nominal_hash", kHashBytes, [](const auto & m) { return m.nominal_hash.size(); }},
  WireField{"job.worker_instance", kWorkerInstanceBytes, [](const auto & m) { return m.worker_instance.size(); }},
  WireField{"job.anchor_source", 32, [](const auto & m) { return m.anchor_source.size(); }},
  WireField{"job.anchor_producer", 64, [](const auto & m) { return m.anchor_producer.size(); }},
  WireField{"job.anchor_run_id", kRunIdBytes, [](const auto & m) { return m.anchor_run_id.size(); }});

inline constexpr auto kJobHistoryFields = std::make_tuple(
  WireField{"job.history_sim_ns", resource_history_hard_cap,
    [](const auto & m) { return m.history_sim_ns.size(); }, 8},
  WireField{"job.history_channel", resource_history_hard_cap,
    [](const auto & m) { return m.history_channel.size(); }, 1},
  WireField{"job.history_n", resource_history_hard_cap,
    [](const auto & m) { return m.history_n.size(); }, 8});

inline constexpr auto kCandidateStringFields = std::make_tuple(
  WireField{"candidate.worker_instance", kWorkerInstanceBytes, [](const auto & m) { return m.worker_instance.size(); }},
  WireField{"candidate.reason", kReasonBytes, [](const auto & m) { return m.reason.size(); }},
  WireField{"candidate.backend", kBackendBytes, [](const auto & m) { return m.backend.size(); }});

inline constexpr auto kCapabilityStringFields = std::make_tuple(
  WireField{"capability.schema_version", kSchemaBytes, [](const auto & m) { return m.schema_version.size(); }},
  WireField{"capability.run_id", kRunIdBytes, [](const auto & m) { return m.run_id.size(); }},
  WireField{"capability.boot_id", kBootIdBytes, [](const auto & m) { return m.boot_id.size(); }},
  WireField{"capability.contract_hash", kHashBytes, [](const auto & m) { return m.contract_hash.size(); }},
  WireField{"capability.nominal_hash", kHashBytes, [](const auto & m) { return m.nominal_hash.size(); }},
  WireField{"capability.worker_instance", kWorkerInstanceBytes, [](const auto & m) { return m.worker_instance.size(); }},
  WireField{"capability.clock_name", 32, [](const auto & m) { return m.clock_name.size(); }},
  WireField{"capability.backend", kBackendBytes, [](const auto & m) { return m.backend.size(); }},
  WireField{"capability.matrix_layout", 32, [](const auto & m) { return m.matrix_layout.size(); }},
  WireField{"capability.reason", kReasonBytes, [](const auto & m) { return m.reason.size(); }});

template<class... Fields>
constexpr auto max_field_sizes(const std::tuple<Fields...> & fields) {
  return std::apply([](const auto & ... field) {
    return std::array<size_t, sizeof...(Fields)>{field.max_size...};
  }, fields);
}

inline constexpr auto kJobStringMaxBytes = max_field_sizes(kJobStringFields);
inline constexpr auto kCandidateStringMaxBytes = max_field_sizes(kCandidateStringFields);

template<class Message, class... Fields>
auto measure_fields(const Message & message, const std::tuple<Fields...> & fields) {
  return std::apply([&](const auto & ... field) {
    return std::array<size_t, sizeof...(Fields)>{field.measure(message)...};
  }, fields);
}

struct CdrSize {
  size_t body = 0;
  constexpr void align(size_t alignment) {
    body += (alignment - body % alignment) % alignment;
  }
  constexpr void scalar(size_t width, size_t count = 1) {
    align(width); body += width * count;
  }
  constexpr void string(size_t byte_count) {
    scalar(4); body += byte_count + 1;  // uint32 length includes the terminal NUL.
  }
  constexpr void sequence(size_t width, size_t count) {
    scalar(4);
    // Installed FastRTPS get_serialized_size aligns elements even when empty;
    // ROS serialized buffer_length includes this generated size accounting.
    scalar(width, count);
  }
};

// CDR1 body alignment starts at zero after the four-byte encapsulation. Keep
// this order tied to SolveJob.msg; tests compare independently to ROS serialization.
constexpr void append_job(CdrSize & s, const decltype(kJobStringMaxBytes) & strings,
                          const std::array<size_t, 3> & histories) {
  for (size_t i = 0; i < 6; ++i) s.string(strings[i]);
  s.scalar(8, 7);   // job_id, target_tick, five generation/epoch fields.
  s.scalar(8, 9);   // tick origin through IMU receive timestamps.
  s.scalar(8, 2);   // odom and IMU sequence.
  s.scalar(1);      // r_from_imu.
  s.scalar(4);      // horizon_steps.
  s.scalar(8);      // prediction_dt.
  s.scalar(8, 6);   // frozen_state.
  s.scalar(8, 6);   // target_state.
  s.scalar(8, 126); // reference.
  s.scalar(8, 2);   // anchor_n.
  s.scalar(8, 2);   // anchor_sequence.
  s.scalar(8, 2);   // anchor_publish_ns.
  s.scalar(1, 2);   // anchor_known.
  s.scalar(1);      // reset_warmstart.
  s.scalar(8, 3);   // clock sim, clock receive, assumed_rtf.
  for (size_t i = 6; i < strings.size(); ++i) s.string(strings[i]);
  std::apply([&](const auto & ... field) {
    size_t i = 0;
    (s.sequence(field.element_bytes, histories[i++]), ...);
  }, kJobHistoryFields);
}

constexpr void append_candidate(CdrSize & s, const decltype(kCandidateStringMaxBytes) & strings) {
  s.string(strings[0]);
  s.scalar(8, 3);  // worker_receive, solve_start, solve_end.
  s.scalar(1, 3);  // solver_invoked, success, prediction_available.
  s.string(strings[1]);
  s.string(strings[2]);
  s.scalar(8);     // backend_ms.
  s.scalar(8, 2);  // first_control.
  s.scalar(8, 126);
  s.scalar(8, 40);
}

inline ResourceCheck byte_bound(size_t observed, size_t limit, const char * field) {
  return observed <= limit ? ResourceCheck{} :
    ResourceCheck{"resource_string_oversize", field, observed, limit};
}
template<class Message, class... Fields>
ResourceCheck check_fields(const Message & message, const std::tuple<Fields...> & fields,
                           const char * reason, size_t capacity) {
  ResourceCheck result;
  const auto within_bound = [&](const auto & field) {
    const auto observed = field.measure(message);
    const auto limit = std::min(field.max_size, capacity);
    if (observed <= limit) return true;
    result = {reason, field.name, observed, limit};
    return false;
  };
  std::apply([&](const auto & ... field) { return (within_bound(field) && ...); }, fields);
  return result;
}

template<class Message, class... Fields>
ResourceCheck check_string_fields(const Message & message, const std::tuple<Fields...> & fields) {
  return check_fields(message, fields, "resource_string_oversize", std::numeric_limits<size_t>::max());
}

inline size_t integer_bound(const nlohmann::json & c, const char * key,
                            size_t low, size_t high) {
  const auto it = c.find(key);
  if (it == c.end() || !it->is_number_integer())
    throw std::runtime_error(std::string("resource integer required: ") + key);
  uint64_t value;
  if (it->is_number_unsigned()) value = it->get<uint64_t>();
  else {
    const int64_t signed_value = it->get<int64_t>();
    if (signed_value < 0)
      throw std::runtime_error(std::string("negative resource bound: ") + key);
    value = static_cast<uint64_t>(signed_value);
  }
  if (value < low || value > high)
    throw std::runtime_error(std::string("unsupported resource bound: ") + key);
  return static_cast<size_t>(value);
}
}  // namespace resource_detail

constexpr size_t max_job_cdr_bytes(size_t history_capacity = resource_history_hard_cap) {
  if (history_capacity > resource_history_hard_cap)
    throw std::out_of_range("unsupported CDR history capacity");
  resource_detail::CdrSize s;
  resource_detail::append_job(s, resource_detail::kJobStringMaxBytes,
    {history_capacity, history_capacity, history_capacity});
  return s.body + 4;
}
constexpr size_t max_candidate_cdr_bytes(size_t history_capacity = resource_history_hard_cap) {
  if (history_capacity > resource_history_hard_cap)
    throw std::out_of_range("unsupported CDR history capacity");
  resource_detail::CdrSize s;
  resource_detail::append_job(s, resource_detail::kJobStringMaxBytes,
    {history_capacity, history_capacity, history_capacity});
  resource_detail::append_candidate(s, resource_detail::kCandidateStringMaxBytes);
  return s.body + 4;
}
static_assert(max_job_cdr_bytes() == 6460, "SolveJob CDR layout changed");
static_assert(max_candidate_cdr_bytes() == 8204, "SolveCandidate CDR layout changed");

namespace resource_detail {

struct ResourceLimitField {
  const char * key;
  size_t ResourceLimits::*member;
  size_t min;
  size_t max;
};

inline constexpr ResourceLimits kDefaultLimits{};
inline constexpr ResourceLimitField kLimitFields[] = {
  {"max_job_bytes", &ResourceLimits::max_job_bytes, max_job_cdr_bytes(), resource_job_byte_hard_cap},
  {"max_candidate_bytes", &ResourceLimits::max_candidate_bytes, max_candidate_cdr_bytes(),
    resource_candidate_byte_hard_cap},
  {"history_capacity", &ResourceLimits::history_capacity, 1, resource_history_hard_cap},
  {"max_path_points", &ResourceLimits::max_path_points, 1, resource_path_hard_cap},
  {"max_profile_rows", &ResourceLimits::max_profile_rows, 1, resource_profile_hard_cap},
  {"log_capacity", &ResourceLimits::log_capacity, 1, resource_log_hard_cap},
  {"dds_depth", &ResourceLimits::dds_depth, kDefaultLimits.dds_depth, kDefaultLimits.dds_depth},
  {"job_cdr_max_bytes", nullptr, max_job_cdr_bytes(), max_job_cdr_bytes()},
  {"candidate_cdr_max_bytes", nullptr, max_candidate_cdr_bytes(), max_candidate_cdr_bytes()},
  {"max_profile_dims", &ResourceLimits::max_profile_dims,
    kDefaultLimits.max_profile_dims, kDefaultLimits.max_profile_dims},
  {"max_profile_label_bytes", &ResourceLimits::max_profile_label_bytes,
    kDefaultLimits.max_profile_label_bytes, kDefaultLimits.max_profile_label_bytes},
  {"max_path_frame_bytes", &ResourceLimits::max_path_frame_bytes,
    kDefaultLimits.max_path_frame_bytes, kDefaultLimits.max_path_frame_bytes},
};

inline constexpr std::pair<const char *, const char *> kPolicyFields[] = {
  {"resource_policy", resource_policy_v1},
  {"resource_budget_scope", resource_cdr_encoding_v1},
};

}  // namespace resource_detail

// Validate the full IDL type budget, even if this contract uses a smaller
// history cache. This prevents an implicit wire-schema change per run.
inline ResourceLimits resource_limits_from_contract(const nlohmann::json & c) {
  using namespace resource_detail;
  if (!c.is_object()) throw std::runtime_error("resource contract object required");
  const auto schema = c.find("schema");
  if (schema != c.end() && !schema->is_string()) throw std::runtime_error("resource schema string required");
  const bool grouped = schema != c.end() && *schema == grouped_contract_schema;
  if (!grouped) {
    if (schema != c.end() && *schema == "p1-execution-contract-v3") {
      integer_bound(c, "resource_contract_revision", 1, 1);
    } else {
      integer_bound(c, "diagnostic_contract_revision", 5, 5);
    }
  } else if (!c.contains("resources")) {
    return {};
  }

  const auto & values = grouped ? c.at("resources") : c;
  if (!values.is_object()) throw std::runtime_error("resources object required");
  size_t matched = 0;
  for (const auto & [key, expected] : kPolicyFields) {
    const auto it = values.find(key);
    if (grouped && it == values.end()) continue;
    if (it == values.end() || !it->is_string() || it->get_ref<const std::string &>() != expected)
      throw std::runtime_error(std::string("unsupported resource policy: ") + key);
    ++matched;
  }

  ResourceLimits limits;
  for (const auto & field : kLimitFields) {
    if (grouped && !values.contains(field.key)) continue;
    const auto size = integer_bound(values, field.key, field.min, field.max);
    if (field.member) limits.*(field.member) = size;
    ++matched;
  }
  if (grouped && matched != values.size()) throw std::runtime_error("unknown resources field");
  return limits;
}

namespace resource_detail {

template<class Job>
void append_job(CdrSize & s, const Job & job) {
  append_job(s, measure_fields(job, kJobStringFields), measure_fields(job, kJobHistoryFields));
}

}  // namespace resource_detail

template<class Job>
inline size_t job_cdr_bytes(const Job & job) {
  resource_detail::CdrSize s;
  resource_detail::append_job(s, job);
  return s.body + 4;
}

template<class Job>
inline ResourceCheck check_job_resources(const Job & job, const ResourceLimits & r) {
  using namespace resource_detail;
  const auto strings = check_string_fields(job, kJobStringFields);
  if (!strings) return strings;
  const auto history = check_fields(job, kJobHistoryFields, "resource_history_oversize",
    r.history_capacity);
  if (!history) return history;
  const auto bytes = job_cdr_bytes(job);
  if (bytes > r.max_job_bytes)
    return {"resource_message_oversize", "job.cdr_bytes", bytes, r.max_job_bytes};
  return {};
}

template<class Candidate>
inline size_t candidate_cdr_bytes(const Candidate & candidate) {
  using namespace resource_detail;
  CdrSize s;
  append_job(s, candidate.job);
  append_candidate(s, measure_fields(candidate, kCandidateStringFields));
  return s.body + 4;
}

template<class Candidate>
inline ResourceCheck check_candidate_resources(const Candidate & candidate, const ResourceLimits & r) {
  const auto job = check_job_resources(candidate.job, r);
  if (!job) return job;
  const auto strings = resource_detail::check_string_fields(candidate, resource_detail::kCandidateStringFields);
  if (!strings) return strings;
  const auto bytes = candidate_cdr_bytes(candidate);
  if (bytes > r.max_candidate_bytes)
    return {"resource_message_oversize", "candidate.cdr_bytes", bytes, r.max_candidate_bytes};
  return {};
}

template<class Capability>
inline ResourceCheck check_capability_resources(const Capability & capability) {
  return resource_detail::check_string_fields(capability, resource_detail::kCapabilityStringFields);
}
template<size_t N>
inline ResourceCheck copy_native_reason(const char (&text)[N],std::string & output) {
  size_t size=0;while(size<N&&text[size]!='\0')++size;
  const auto & reason = std::get<1>(resource_detail::kCandidateStringFields);
  if(size==N)return {"native_reason_unterminated",reason.name,size,N-1};
  if(size>reason.max_size)return {"native_reason_oversize",reason.name,size,reason.max_size};
  output.assign(text,size);return {};
}
template<class Path>
inline ResourceCheck check_path_resources(const Path & m, const ResourceLimits & r) {
  if(m.poses.size()>r.max_path_points)return {"resource_path_oversize","path.poses",m.poses.size(),r.max_path_points};
  return resource_detail::byte_bound(m.header.frame_id.size(),r.max_path_frame_bytes,"path.frame_id");
}
template<class Profile>
inline ResourceCheck check_profile_resources(const Profile & m, const ResourceLimits & r) {
  if(m.data.size()>r.max_profile_rows*4)return {"resource_profile_oversize","profile.data",m.data.size(),r.max_profile_rows*4};
  if(m.layout.dim.size()>r.max_profile_dims)return {"resource_metadata_oversize","profile.dim",m.layout.dim.size(),r.max_profile_dims};
  for(const auto & dim:m.layout.dim){auto c=resource_detail::byte_bound(dim.label.size(),r.max_profile_label_bytes,"profile.label");if(!c)return c;}
  return {};
}
}  // namespace p1
