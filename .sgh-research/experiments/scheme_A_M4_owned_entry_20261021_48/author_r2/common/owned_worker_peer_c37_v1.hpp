// SPDX-License-Identifier: MIT
// Worker-role binding to two distinct DataWriters; no Publisher identity reuse.
#pragma once
#include "owned_peer_c36_v1.hpp"
#include "p1_full_contract.hpp"

namespace c37_owned {
using Json = p1_owned::Json;
namespace detail = c36_owned::detail;
enum class Interface { Capability, Candidate };

struct WorkerPins {
  std::string manifest_path, manifest_sha256;
  std::string run_id, boot_id, contract_sha256, worker_instance, nominal_hash;
  std::string exe, binary_sha256, source_bundle_sha256, effective_parameters_sha256;
  int64_t pid = 0;
  uint64_t process_start_ticks = 0;
  std::string capability_topic = "/p1/worker_capability";
  std::string capability_type = "usv_research_interfaces/msg/WorkerCapability";
  std::string candidate_topic = "/p1/solve_candidate";
  std::string candidate_type = "usv_research_interfaces/msg/SolveCandidate";
  static WorkerPins from_json(const Json &j);
};

inline WorkerPins from_json(const Json &j) {
  const std::set<std::string> expected = {"manifest_path","manifest_sha256","run_id","boot_id",
    "contract_sha256","worker_instance","nominal_hash","exe","binary_sha256",
    "source_bundle_sha256","effective_parameters_sha256","pid","process_start_ticks",
    "capability_topic","capability_type","candidate_topic","candidate_type"};
  detail::require(j.is_object() && j.size() == expected.size(), "worker_pins_population");
  for (auto it = j.begin(); it != j.end(); ++it)
    detail::require(expected.count(it.key()) == 1, "unknown_worker_pin_field");
  WorkerPins p;
  p.manifest_path = detail::string_field(j,"manifest_path",4096);
  p.manifest_sha256 = detail::string_field(j,"manifest_sha256",64);
  p.run_id = detail::string_field(j,"run_id",128);
  p.boot_id = detail::string_field(j,"boot_id",64);
  p.contract_sha256 = detail::string_field(j,"contract_sha256",64);
  p.worker_instance = detail::string_field(j,"worker_instance",64);
  p.nominal_hash = detail::string_field(j,"nominal_hash",64);
  p.exe = detail::string_field(j,"exe",4096);
  p.binary_sha256 = detail::string_field(j,"binary_sha256",64);
  p.source_bundle_sha256 = detail::string_field(j,"source_bundle_sha256",64);
  p.effective_parameters_sha256 = detail::string_field(j,"effective_parameters_sha256",64);
  p.pid = static_cast<int64_t>(detail::uint_field(j,"pid",INT_MAX));
  p.process_start_ticks = detail::uint_field(j,"process_start_ticks",UINT64_MAX);
  p.capability_topic = detail::string_field(j,"capability_topic",256);
  p.capability_type = detail::string_field(j,"capability_type",256);
  p.candidate_topic = detail::string_field(j,"candidate_topic",256);
  p.candidate_type = detail::string_field(j,"candidate_type",256);
  return p;
}
inline WorkerPins WorkerPins::from_json(const Json &j) { return c37_owned::from_json(j); }

class OwnedWorkerPeer {
 public:
  explicit OwnedWorkerPeer(WorkerPins pins) : pins_(std::move(pins)) {
    using detail::require;
    static_assert(RMW_GID_STORAGE_SIZE == 16, "registered FastDDS GID domain changed");
    require(pins_.pid > 0 && pins_.pid <= INT_MAX && pins_.process_start_ticks > 0,
            "worker_pin_process_domain");
    require(detail::visible_ascii(pins_.run_id,128) && detail::visible_ascii(pins_.boot_id,64) &&
      detail::visible_ascii(pins_.worker_instance,64) && detail::visible_ascii(pins_.exe,4096) &&
      pins_.exe[0] == '/' && detail::visible_ascii(pins_.capability_topic,256) &&
      detail::visible_ascii(pins_.candidate_topic,256) && pins_.capability_topic[0] == '/' &&
      pins_.candidate_topic[0] == '/' && pins_.capability_topic != pins_.candidate_topic,
      "worker_pin_identity_domain");
    require(pins_.capability_type == "usv_research_interfaces/msg/WorkerCapability" &&
      pins_.candidate_type == "usv_research_interfaces/msg/SolveCandidate", "worker_interface_type");
    for (const auto *sha : {&pins_.manifest_sha256,&pins_.contract_sha256,&pins_.nominal_hash,
      &pins_.binary_sha256,&pins_.source_bundle_sha256,&pins_.effective_parameters_sha256})
      require(p1_owned::sha256_shape(*sha), "worker_pin_sha_shape");
    const auto raw = detail::read_manifest(pins_.manifest_path);
    require(p1_owned::sha256_bytes(raw) == pins_.manifest_sha256, "worker_manifest_sha");
    manifest_ = detail::strict_json(raw);
    for (const auto &binding : std::vector<std::pair<const char *,std::string>>{
      {"schema_version","p1-owned-role-v1"},{"role","worker"},{"run_id",pins_.run_id},
      {"boot_id",pins_.boot_id},{"contract_sha256",pins_.contract_sha256},
      {"worker_instance",pins_.worker_instance},{"nominal_hash",pins_.nominal_hash},
      {"exe",pins_.exe},{"binary_sha256",pins_.binary_sha256},
      {"source_bundle_sha256",pins_.source_bundle_sha256},
      {"effective_parameters_sha256",pins_.effective_parameters_sha256},
      {"rmw_implementation","rmw_fastrtps_cpp"},
      {"effective_parameters_digest_encoding","p1-typed-ieee754-v1"}}) {
      const size_t limit = std::string(binding.first) == "exe" ? 4096 : 256;
      require(detail::string_field(manifest_,binding.first,limit) == binding.second,
              std::string("worker_manifest_binding_") + binding.first);
    }
    require(!manifest_.contains("producer_instance_id") && !manifest_.contains("config_hash"),
            "worker_manifest_borrowed_publisher_identity");
    require(detail::uint_field(manifest_,"pid",INT_MAX) == static_cast<uint64_t>(pins_.pid) &&
      detail::uint_field(manifest_,"process_start_ticks",UINT64_MAX) == pins_.process_start_ticks,
      "worker_manifest_process");
    const auto created = detail::uint_field(manifest_,"created_steady_ns",INT64_MAX);
    require(created > 0 && created <= static_cast<uint64_t>(p1_owned::steady_ns()), "worker_manifest_time");
    detail::bool_field(manifest_,"effective_parameters_immutable",true);
    detail::bool_field(manifest_,"execute_qualified",false);
    detail::bool_field(manifest_,"physical_release_qualified",false);
    detail::parameter_rows(manifest_.at("effective_parameters"));
    detail::parameter_rows(manifest_.at("parameter_overrides"));
    require(p1_owned::sha256_bytes(p1_owned::canonical_parameters(manifest_.at("effective_parameters")).dump()) ==
      pins_.effective_parameters_sha256, "worker_parameter_digest");
    // These values are independently pinned by the supervisor; the manifest
    // digest alone would not detect internally coherent copies with wrong roles.
    const auto &effective = manifest_.at("effective_parameters");
    for (const auto &binding : std::vector<std::pair<const char *,std::string>>{
      {"run_id",pins_.run_id},{"contract_hash",pins_.contract_sha256},
      {"owned_manifest_file",pins_.manifest_path}}) {
      require(effective.contains(binding.first) &&
        detail::uint_field(effective.at(binding.first),"type",9) == 4 &&
        effective.at(binding.first).at("value").is_string() &&
        effective.at(binding.first).at("value").get<std::string>() == binding.second,
        std::string("worker_parameter_binding_") + binding.first);
    }
    const auto &configuration = manifest_.at("contract_configuration");
    require(configuration.is_object() &&
      detail::string_field(configuration,"nominal_hash",64) == pins_.nominal_hash,
      "worker_contract_nominal_binding");
    require(p1::validate_contract_fields(configuration)==p1::ContractProfile::Frozen && configuration.at("supported_parameter_profile")==p1::target_parameter_profile,"M4 worker exact owned frozen contract");
    require(manifest_.at("argv").is_array() && !manifest_.at("argv").empty() &&
      manifest_.at("argv").size() <= 512, "worker_manifest_argv");
    for (const auto &arg : manifest_.at("argv"))
      require(arg.is_string() && arg.get_ref<const std::string &>().size() <= 65536 &&
        arg.get_ref<const std::string &>().find('\0') == std::string::npos, "worker_manifest_argv_element");
    node_ = detail::string_field(manifest_,"node",256);
    require(node_[0] == '/' && detail::uint_field(manifest_,"gid_storage_size",16) == 16,
            "worker_endpoint_domain");
    const auto &endpoints = manifest_.at("endpoints");
    require(endpoints.is_array() && endpoints.size() >= 2 && endpoints.size() <= 128,
            "worker_endpoint_population");
    std::set<std::string> unique;
    size_t capability_matches = 0, candidate_matches = 0;
    for (const auto &ep : endpoints) {
      require(ep.is_object() && ep.size() == 4 && ep.contains("gid"), "worker_endpoint_shape");
      const auto kind = detail::string_field(ep,"kind",16);
      const auto topic = detail::string_field(ep,"topic",256);
      const auto type = detail::string_field(ep,"type",256);
      require((kind == "publisher" || kind == "subscription") && topic[0] == '/' &&
        type.find("/msg/") != std::string::npos, "worker_endpoint_shape");
      const auto &gid = ep.at("gid");
      require(gid.is_array() && gid.size() == RMW_GID_STORAGE_SIZE, "worker_endpoint_gid_shape");
      std::array<uint8_t,RMW_GID_STORAGE_SIZE> parsed{}; bool nonzero = false;
      for (size_t i = 0; i < parsed.size(); ++i) {
        const auto &byte = gid[i];
        require(byte.is_number_integer() && !byte.is_boolean() &&
          (byte.is_number_unsigned() || byte.get<int64_t>() >= 0) && byte.get<uint64_t>() <= 255,
          "worker_endpoint_gid_byte");
        parsed[i] = static_cast<uint8_t>(byte.get<uint64_t>()); nonzero |= parsed[i] != 0;
      }
      require(nonzero && unique.insert(gid.dump()).second, "worker_endpoint_gid_duplicate_or_zero");
      if (kind == "publisher" && topic == pins_.capability_topic) {
        require(type == pins_.capability_type, "worker_capability_endpoint_type");
        ++capability_matches; capability_gid_ = parsed; capability_endpoint_ = ep;
      }
      if (kind == "publisher" && topic == pins_.candidate_topic) {
        require(type == pins_.candidate_type, "worker_candidate_endpoint_type");
        ++candidate_matches; candidate_gid_ = parsed; candidate_endpoint_ = ep;
      }
    }
    require(capability_matches == 1 && candidate_matches == 1 && capability_gid_ != candidate_gid_,
            "worker_endpoint_missing_or_ambiguous");
    // Shared process verifier does not use Publisher identity fields.
    process_pins_.pid = pins_.pid; process_pins_.process_start_ticks = pins_.process_start_ticks;
    process_pins_.boot_id = pins_.boot_id; process_pins_.exe = pins_.exe;
    process_pins_.binary_sha256 = pins_.binary_sha256;
    process_ = detail::authenticate_process(process_pins_,manifest_);
    pidfd_.reset(static_cast<int>(::syscall(SYS_pidfd_open,static_cast<pid_t>(pins_.pid),0)));
    require(pidfd_.get() >= 0, "worker_pidfd_open");
    const auto after = detail::authenticate_process(process_pins_,manifest_);
    require(after.start == process_.start && after.pgid == process_.pgid && after.sid == process_.sid &&
      after.exe == process_.exe && after.sha == process_.sha && after.argv == process_.argv && alive(),
      "worker_process_changed_during_pin");
    require(detail::read_manifest(pins_.manifest_path) == raw, "worker_manifest_changed_during_pin");
    authenticated_ns_ = p1_owned::steady_ns();
  }
  OwnedWorkerPeer(const OwnedWorkerPeer &) = delete;
  OwnedWorkerPeer &operator=(const OwnedWorkerPeer &) = delete;
  bool alive() const { return liveness_reason().empty(); }
  bool gid_matches(const rclcpp::MessageInfo &info, Interface interface) const {
    return metadata_reason(info,interface).empty();
  }
  std::string callback_reason(const rclcpp::MessageInfo &info, Interface interface) const {
    const auto reason = metadata_reason(info,interface);
    return reason.empty() ? liveness_reason() : reason;
  }
  Json expected_gid(Interface interface) const {
    return endpoint(interface).at("gid");
  }
  bool graph_matches_snapshot(rclcpp::Node &node) const {
    return alive() && graph_endpoint(node,pins_.capability_topic,pins_.capability_type,capability_gid_) &&
      graph_endpoint(node,pins_.candidate_topic,pins_.candidate_type,candidate_gid_);
  }
  Json evidence() const {
    return {{"schema","p1-owned-worker-peer-C3_7-v1"},{"manifest_path",pins_.manifest_path},
      {"manifest_sha256",pins_.manifest_sha256},{"run_id",pins_.run_id},{"boot_id",pins_.boot_id},
      {"contract_sha256",pins_.contract_sha256},{"worker_instance",pins_.worker_instance},
      {"nominal_hash",pins_.nominal_hash},{"source_bundle_sha256",pins_.source_bundle_sha256},
      {"binary_sha256",pins_.binary_sha256},{"effective_parameters_sha256",pins_.effective_parameters_sha256},
      {"pid",pins_.pid},{"process_start_ticks",pins_.process_start_ticks},{"pgid",process_.pgid},
      {"sid",process_.sid},{"exe",process_.exe},{"node",node_},
      {"endpoints",{{"capability",capability_endpoint_},{"candidate",candidate_endpoint_}}},
      {"authenticated_steady_ns",authenticated_ns_},{"pidfd_alive_at_evidence_call",alive()},
      {"callback_policy","interface_specific_exact_DataWriter_GID_and_zero_wait_pidfd"},
      {"manifest_authorship_policy","pins supplied by independently authenticated external supervisor"},
      {"post_pin_exec_continuity","unknown"},{"continuous_DDS_uniqueness","unknown"},
      {"worker_close_intent","unknown"},{"worker_endpoints_exited","unknown"},
      {"plant_acceptance","unknown"},{"stage_qualified",false},{"execute_qualified",false},
      {"physical_release_qualified",false}};
  }
 private:
  const Json &endpoint(Interface interface) const {
    if (interface == Interface::Capability) return capability_endpoint_;
    if (interface == Interface::Candidate) return candidate_endpoint_;
    throw std::runtime_error("owned_worker_peer:interface_domain");
  }
  std::string metadata_reason(const rclcpp::MessageInfo &info, Interface interface) const {
    if (interface != Interface::Capability && interface != Interface::Candidate)
      return "callback_interface_domain";
    const auto &message = info.get_rmw_message_info();
    if (message.from_intra_process) return "callback_intra_process_outside_registered_domain";
    if (!message.publisher_gid.implementation_identifier ||
      std::strcmp(message.publisher_gid.implementation_identifier,"rmw_fastrtps_cpp") != 0)
      return "callback_rmw_implementation";
    const auto &gid = interface == Interface::Capability ? capability_gid_ : candidate_gid_;
    for (size_t i = 0; i < gid.size(); ++i)
      if (message.publisher_gid.data[i] != gid[i]) return "callback_foreign_gid";
    return "";
  }
  bool graph_endpoint(rclcpp::Node &node, const std::string &topic,const std::string &type,
    const std::array<uint8_t,RMW_GID_STORAGE_SIZE> &gid) const {
    const auto rows = node.get_publishers_info_by_topic(topic);
    if (rows.size() != 1 || rows[0].topic_type() != type || rows[0].endpoint_gid() != gid) return false;
    const auto name_space = rows[0].node_namespace();
    return (name_space == "/" ? "/" : name_space + "/") + rows[0].node_name() == node_;
  }
  std::string liveness_reason() const {
    pollfd fd{pidfd_.get(),POLLIN,0}; const auto result = ::poll(&fd,1,0);
    if (result == 0) return "";
    if (result < 0 || (fd.revents & (POLLERR | POLLNVAL))) return "worker_liveness_check_failed";
    return (fd.revents & (POLLIN | POLLHUP)) ? "worker_process_exited" : "worker_liveness_check_failed";
  }
  WorkerPins pins_;
  c36_owned::PeerPins process_pins_;
  Json manifest_, capability_endpoint_, candidate_endpoint_;
  std::string node_;
  std::array<uint8_t,RMW_GID_STORAGE_SIZE> capability_gid_{}, candidate_gid_{};
  detail::Process process_;
  detail::Fd pidfd_;
  int64_t authenticated_ns_ = 0;
};
}  // namespace c37_owned
