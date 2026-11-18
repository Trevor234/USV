// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
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
constexpr void append_job(CdrSize & s, const std::array<size_t, 9> & strings,
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
  for (size_t i = 6; i < 9; ++i) s.string(strings[i]);
  s.sequence(8, histories[0]);
  s.sequence(1, histories[1]);
  s.sequence(8, histories[2]);
}

constexpr void append_candidate(CdrSize & s, size_t worker, size_t reason,
                                size_t backend) {
  s.string(worker);
  s.scalar(8, 3);  // worker_receive, solve_start, solve_end.
  s.scalar(1, 3);  // solver_invoked, success, prediction_available.
  s.string(reason);
  s.string(backend);
  s.scalar(8);     // backend_ms.
  s.scalar(8, 2);  // first_control.
  s.scalar(8, 126);
  s.scalar(8, 40);
}

inline ResourceCheck byte_bound(size_t observed, size_t limit, const char * field) {
  return observed <= limit ? ResourceCheck{} :
    ResourceCheck{"resource_string_oversize", field, observed, limit};
}
inline ResourceCheck sequence_bound(size_t observed, size_t limit, const char * field) {
  return observed <= limit ? ResourceCheck{} :
    ResourceCheck{"resource_history_oversize", field, observed, limit};
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
  resource_detail::append_job(s, {64, 128, 64, 64, 64, 64, 32, 64, 128},
    {history_capacity, history_capacity, history_capacity});
  return s.body + 4;
}
constexpr size_t max_candidate_cdr_bytes(size_t history_capacity = resource_history_hard_cap) {
  if (history_capacity > resource_history_hard_cap)
    throw std::out_of_range("unsupported CDR history capacity");
  resource_detail::CdrSize s;
  resource_detail::append_job(s, {64, 128, 64, 64, 64, 64, 32, 64, 128},
    {history_capacity, history_capacity, history_capacity});
  resource_detail::append_candidate(s, 64, 256, 16);
  return s.body + 4;
}
static_assert(max_job_cdr_bytes() == 6460, "SolveJob CDR layout changed");
static_assert(max_candidate_cdr_bytes() == 8204, "SolveCandidate CDR layout changed");

// Validate the full IDL type budget, even if this contract uses a smaller
// history cache. This prevents an implicit wire-schema change per run.
inline ResourceLimits resource_limits_from_contract(const nlohmann::json & c) {
  using resource_detail::integer_bound;
  if (c.value("schema", std::string{}) == "p1-execution-contract-v3" ||
      c.value("schema", std::string{}) == "p1-shipboard-execute-v1") {
    integer_bound(c, "resource_contract_revision", 1, 1);
  } else {
    integer_bound(c, "diagnostic_contract_revision", 5, 5);
  }
  for (const auto & expected : std::array<std::pair<const char *, const char *>, 2>{{
       {"resource_policy", resource_policy_v1},
       {"resource_budget_scope", resource_cdr_encoding_v1}}}) {
    const auto it = c.find(expected.first);
    if (it == c.end() || !it->is_string() || it->get_ref<const std::string &>() != expected.second)
      throw std::runtime_error(std::string("unsupported resource policy: ") + expected.first);
  }
  ResourceLimits r;
  r.max_job_bytes = integer_bound(c, "max_job_bytes", max_job_cdr_bytes(), resource_job_byte_hard_cap);
  r.max_candidate_bytes = integer_bound(c, "max_candidate_bytes", max_candidate_cdr_bytes(), resource_candidate_byte_hard_cap);
  r.history_capacity = integer_bound(c, "history_capacity", 1, resource_history_hard_cap);
  r.max_path_points = integer_bound(c, "max_path_points", 1, resource_path_hard_cap);
  r.max_profile_rows = integer_bound(c, "max_profile_rows", 1, resource_profile_hard_cap);
  r.log_capacity = integer_bound(c, "log_capacity", 1, resource_log_hard_cap);
  r.dds_depth = integer_bound(c, "dds_depth", 1, 1);
  integer_bound(c, "job_cdr_max_bytes", max_job_cdr_bytes(), max_job_cdr_bytes());
  integer_bound(c, "candidate_cdr_max_bytes", max_candidate_cdr_bytes(), max_candidate_cdr_bytes());
  r.max_profile_dims = integer_bound(c, "max_profile_dims", 4, 4);
  r.max_profile_label_bytes = integer_bound(c, "max_profile_label_bytes", 64, 64);
  r.max_path_frame_bytes = integer_bound(c, "max_path_frame_bytes", 128, 128);
  return r;
}

template<class Job>
inline size_t job_cdr_bytes(const Job & j) {
  resource_detail::CdrSize s;
  resource_detail::append_job(s, {j.schema_version.size(), j.run_id.size(), j.boot_id.size(),
    j.contract_hash.size(), j.nominal_hash.size(), j.worker_instance.size(),
    j.anchor_source.size(), j.anchor_producer.size(), j.anchor_run_id.size()},
    {j.history_sim_ns.size(), j.history_channel.size(), j.history_n.size()});
  return s.body + 4;
}

template<class Job>
inline ResourceCheck check_job_resources(const Job & j, const ResourceLimits & r) {
  const std::array<std::pair<const std::string *, size_t>, 9> strings{{
    {&j.schema_version, 64}, {&j.run_id, 128}, {&j.boot_id, 64},
    {&j.contract_hash, 64}, {&j.nominal_hash, 64}, {&j.worker_instance, 64},
    {&j.anchor_source, 32}, {&j.anchor_producer, 64}, {&j.anchor_run_id, 128}}};
  const std::array<const char *, 9> fields{{"job.schema_version", "job.run_id", "job.boot_id",
    "job.contract_hash", "job.nominal_hash", "job.worker_instance", "job.anchor_source",
    "job.anchor_producer", "job.anchor_run_id"}};
  for (size_t i = 0; i < strings.size(); ++i) {
    const auto check = resource_detail::byte_bound(strings[i].first->size(), strings[i].second, fields[i]);
    if (!check) return check;
  }
  const size_t history_limit = r.history_capacity <= resource_history_hard_cap ?
    r.history_capacity : resource_history_hard_cap;
  for (const auto & item : std::array<std::pair<size_t, const char *>, 3>{{
       {j.history_sim_ns.size(), "job.history_sim_ns"},
       {j.history_channel.size(), "job.history_channel"},
       {j.history_n.size(), "job.history_n"}}}) {
    const auto check = resource_detail::sequence_bound(item.first, history_limit, item.second);
    if (!check) return check;
  }
  const auto bytes = job_cdr_bytes(j);
  if (bytes > r.max_job_bytes)
    return {"resource_message_oversize", "job.cdr_bytes", bytes, r.max_job_bytes};
  return {};
}

template<class Candidate>
inline size_t candidate_cdr_bytes(const Candidate & m) {
  resource_detail::CdrSize s;
  resource_detail::append_job(s, {m.job.schema_version.size(), m.job.run_id.size(), m.job.boot_id.size(),
    m.job.contract_hash.size(), m.job.nominal_hash.size(), m.job.worker_instance.size(),
    m.job.anchor_source.size(), m.job.anchor_producer.size(), m.job.anchor_run_id.size()},
    {m.job.history_sim_ns.size(), m.job.history_channel.size(), m.job.history_n.size()});
  resource_detail::append_candidate(s, m.worker_instance.size(), m.reason.size(), m.backend.size());
  return s.body + 4;
}

template<class Candidate>
inline ResourceCheck check_candidate_resources(const Candidate & m, const ResourceLimits & r) {
  auto check = check_job_resources(m.job, r);
  if (!check) return check;
  check = resource_detail::byte_bound(m.worker_instance.size(), 64, "candidate.worker_instance");
  if (!check) return check;
  check = resource_detail::byte_bound(m.reason.size(), 256, "candidate.reason");
  if (!check) return check;
  check = resource_detail::byte_bound(m.backend.size(), 16, "candidate.backend");
  if (!check) return check;
  const auto bytes = candidate_cdr_bytes(m);
  if (bytes > r.max_candidate_bytes)
    return {"resource_message_oversize", "candidate.cdr_bytes", bytes, r.max_candidate_bytes};
  return {};
}

template<class Capability>
inline ResourceCheck check_capability_resources(const Capability & m) {
  const std::array<std::pair<const std::string *, size_t>, 10> strings{{
    {&m.schema_version, 64}, {&m.run_id, 128}, {&m.boot_id, 64}, {&m.contract_hash, 64},
    {&m.nominal_hash, 64}, {&m.worker_instance, 64}, {&m.clock_name, 32},
    {&m.backend, 16}, {&m.matrix_layout, 32}, {&m.reason, 256}}};
  const std::array<const char *, 10> fields{{"capability.schema_version", "capability.run_id",
    "capability.boot_id", "capability.contract_hash", "capability.nominal_hash",
    "capability.worker_instance", "capability.clock_name", "capability.backend",
    "capability.matrix_layout", "capability.reason"}};
  for (size_t i = 0; i < strings.size(); ++i) {
    const auto check = resource_detail::byte_bound(strings[i].first->size(), strings[i].second, fields[i]);
    if (!check) return check;
  }
  return {};
}
template<size_t N>
inline ResourceCheck copy_native_reason(const char (&text)[N],std::string & output) {
  size_t size=0;while(size<N&&text[size]!='\0')++size;
  if(size==N)return {"native_reason_unterminated","candidate.reason",size,N-1};
  if(size>256)return {"native_reason_oversize","candidate.reason",size,256};
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
