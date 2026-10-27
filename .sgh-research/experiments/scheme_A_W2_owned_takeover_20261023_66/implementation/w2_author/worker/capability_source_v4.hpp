// SPDX-License-Identifier: MIT
#pragma once
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
#include "p1_owned_identity.hpp"
namespace p1_cap_source_v4 {
inline p1::Json payload(const p1::Capability & m) {
  return {{"schema_version",m.schema_version},{"run_id",m.run_id},{"boot_id",m.boot_id},
    {"contract_hash",m.contract_hash},{"nominal_hash",m.nominal_hash},{"worker_instance",m.worker_instance},
    {"clock_name",m.clock_name},{"backend",m.backend},{"matrix_layout",m.matrix_layout},
    {"horizon_steps",m.horizon_steps},{"prediction_dt",m.prediction_dt},{"pid",m.pid},
    {"startup_ns",m.startup_ns},{"completed_jobs",m.completed_jobs},{"active_job",m.active_job},
    {"pending_count",m.pending_count},{"fault_injection_enabled",m.fault_injection_enabled},
    {"fatal",m.fatal},{"reason",m.reason}};
}
inline std::string typed_sha(p1::Json value) {
  value["prediction_dt"]={{"ieee754_binary64_be",p1_owned::double_canonical(value.at("prediction_dt").get<double>())}};
  return p1_owned::sha256_bytes(value.dump());
}
inline p1::Json cdr(const p1::Capability & m) {
  rclcpp::Serialization<p1::Capability> serializer;
  rclcpp::SerializedMessage serialized;
  serializer.serialize_message(&m,&serialized);
  const auto & raw=serialized.get_rcl_serialized_message();
  p1_owned::require(raw.buffer_length>0&&raw.buffer_length<=1048576,"capability CDR exceeds observation bound");
  return {{"representation","typed_reserialization_cdr"},{"bytes",raw.buffer_length},
    {"sha256",p1_owned::sha256_bytes(std::string(reinterpret_cast<const char *>(raw.buffer),raw.buffer_length))},
    {"hex",p1_owned::hex(raw.buffer,raw.buffer_length)}};
}
}  // namespace p1_cap_source_v4
