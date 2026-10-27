// SPDX-License-Identifier: MIT
// Finite owner binding. The caller supplies independently authenticated pins.
#pragma once
#include "p1_owned_identity.hpp"
#include <rclcpp/message_info.hpp>
#include <array>
#include <climits>
#include <poll.h>
#include <sys/syscall.h>

namespace c36_owned {
using Json = p1_owned::Json;

struct PeerPins {
  std::string manifest_path, manifest_sha256;
  std::string run_id, boot_id, contract_sha256, producer_instance_id, config_hash;
  std::string exe, binary_sha256, source_bundle_sha256, effective_parameters_sha256;
  int64_t pid = 0;
  uint64_t process_start_ticks = 0;
  std::string topic = "/research/control/applied";
  std::string type = "usv_research_interfaces/msg/AppliedControl";
};

namespace detail {
inline void require(bool ok, const std::string &why) {
  if (!ok) throw std::runtime_error("owned_peer:" + why);
}
class Fd {
 public:
  explicit Fd(int fd = -1) : fd_(fd) {}
  ~Fd() { if (fd_ >= 0) ::close(fd_); }
  Fd(const Fd &) = delete;
  Fd &operator=(const Fd &) = delete;
  void reset(int fd) { if (fd_ >= 0) ::close(fd_); fd_ = fd; }
  int get() const { return fd_; }
 private:
  int fd_;
};
inline bool visible_ascii(const std::string &s, size_t limit) {
  if (s.empty() || s.size() > limit) return false;
  for (unsigned char c : s) if (c < 33 || c > 126) return false;
  return true;
}
inline std::string string_field(const Json &j, const char *key, size_t limit) {
  require(j.contains(key) && j.at(key).is_string(), std::string(key) + "_type");
  auto value = j.at(key).get<std::string>();
  require(visible_ascii(value, limit), std::string(key) + "_domain");
  return value;
}
inline uint64_t uint_field(const Json &j, const char *key, uint64_t maximum) {
  require(j.contains(key), std::string(key) + "_missing");
  const auto &v = j.at(key);
  require(v.is_number_integer() && !v.is_boolean(), std::string(key) + "_type");
  if (!v.is_number_unsigned()) require(v.get<int64_t>() >= 0, std::string(key) + "_negative");
  const auto n = v.get<uint64_t>();
  require(n <= maximum, std::string(key) + "_domain");
  return n;
}
inline void bool_field(const Json &j, const char *key, bool expected) {
  require(j.contains(key) && j.at(key).is_boolean() && j.at(key).get<bool>() == expected,
          std::string(key) + "_boolean");
}
inline bool same_stat(const struct stat &a, const struct stat &b) {
  return a.st_dev == b.st_dev && a.st_ino == b.st_ino && a.st_mode == b.st_mode &&
    a.st_size == b.st_size && a.st_mtim.tv_sec == b.st_mtim.tv_sec &&
    a.st_mtim.tv_nsec == b.st_mtim.tv_nsec && a.st_ctim.tv_sec == b.st_ctim.tv_sec &&
    a.st_ctim.tv_nsec == b.st_ctim.tv_nsec;
}
inline std::string read_manifest(const std::string &path) {
  constexpr size_t bound = 262144;
  const std::filesystem::path p(path);
  require(p.is_absolute() && !p.filename().empty() && p.filename() != "." && p.filename() != "..",
          "manifest_path");
  const auto parent = p1_owned::open_directory(p.parent_path());
  const auto name = p.filename().string();
  Fd fd(::openat(parent.get(), name.c_str(), O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC));
  require(fd.get() >= 0, "manifest_open");
  struct stat before{}, after{}, named{};
  require(::fstat(fd.get(), &before) == 0 && S_ISREG(before.st_mode) && before.st_size > 0 &&
          static_cast<uint64_t>(before.st_size) <= bound, "manifest_regular_bound");
  std::string raw(static_cast<size_t>(before.st_size), '\0');
  size_t done = 0;
  while (done < raw.size()) {
    const auto count = ::read(fd.get(), raw.data() + done, raw.size() - done);
    if (count < 0 && errno == EINTR) continue;
    require(count > 0, "manifest_short_read");
    done += static_cast<size_t>(count);
  }
  char extra;
  require(::read(fd.get(), &extra, 1) == 0 && ::fstat(fd.get(), &after) == 0 &&
          ::fstatat(parent.get(), name.c_str(), &named, AT_SYMLINK_NOFOLLOW) == 0 &&
          same_stat(before, after) && same_stat(before, named), "manifest_changed");
  return raw;
}
inline Json strict_json(const std::string &raw) {
  std::vector<std::set<std::string>> keys;
  auto callback = [&keys](int depth, Json::parse_event_t event, Json &parsed) {
    require(depth <= 32, "json_depth");
    if (event == Json::parse_event_t::object_start) keys.emplace_back();
    else if (event == Json::parse_event_t::key) {
      require(!keys.empty() && keys.back().insert(parsed.get<std::string>()).second,
              "duplicate_json_key");
    } else if (event == Json::parse_event_t::object_end) {
      require(!keys.empty(), "json_object_stack"); keys.pop_back();
    } else if (event == Json::parse_event_t::value && parsed.is_number_float()) {
      require(std::isfinite(parsed.get<double>()), "nonfinite_json");
    }
    return true;
  };
  auto j = Json::parse(raw, callback);
  require(j.is_object() && keys.empty(), "manifest_object");
  return j;
}
inline bool exact_json(const Json &a, const Json &b) {
  if (a.type() != b.type()) return false;
  if (a.is_array()) {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i) if (!exact_json(a[i], b[i])) return false;
    return true;
  }
  if (a.is_object()) {
    if (a.size() != b.size()) return false;
    for (auto it = a.begin(); it != a.end(); ++it)
      if (!b.contains(it.key()) || !exact_json(it.value(), b.at(it.key()))) return false;
    return true;
  }
  return a == b;
}
inline void parameter_rows(const Json &rows) {
  require(rows.is_object() && rows.size() <= 512, "parameter_population");
  for (auto it = rows.begin(); it != rows.end(); ++it) {
    require(!it.key().empty() && it.key().size() <= 256 && it.key().find('\0') == std::string::npos,
            "parameter_name");
    const auto &r = it.value();
    require(r.is_object() && r.size() == 3 && r.contains("value") && r.contains("canonical_value"),
            "parameter_row");
    const auto type = uint_field(r, "type", 9);
    const auto &v = r.at("value");
    const auto scalar = [](const Json &x, unsigned t) {
      if (t == 0) return x.is_null();
      if (t == 1) return x.is_boolean();
      if (t == 2) return x.is_number_integer() && (!x.is_number_unsigned() || x.get<uint64_t>() <= INT64_MAX);
      if (t == 3) return x.is_number() && !x.is_boolean() && std::isfinite(x.get<double>());
      return x.is_string() && x.get_ref<const std::string &>().size() <= 65536;
    };
    if (type <= 4) require(scalar(v, type), "parameter_value_type");
    else {
      require(v.is_array() && v.size() <= 8192, "parameter_array_bound");
      for (const auto &x : v) {
        if (type == 5) require(x.is_number_integer() && !x.is_boolean() &&
          (x.is_number_unsigned() || x.get<int64_t>() >= 0) && x.get<uint64_t>() <= 255,
          "parameter_byte");
        else require(scalar(x, static_cast<unsigned>(type - 5)), "parameter_element_type");
      }
    }
    Json canonical = v;
    if (type == 3) canonical = p1_owned::double_canonical(v.get<double>());
    if (type == 8) {
      canonical = Json::array();
      for (const auto &x : v) canonical.push_back(p1_owned::double_canonical(x.get<double>()));
    }
    require(exact_json(r.at("canonical_value"), canonical),
            "parameter_canonical");
  }
}
struct Process {
  uint64_t start = 0;
  int64_t pgid = 0, sid = 0;
  std::string exe, sha;
  Json argv;
};
inline std::string process_binary_sha(const std::string &path) {
  // /proc/PID/exe is a kernel link. Every ordinary manifest component rejects links.
  Fd fd(::open(path.c_str(), O_RDONLY | O_CLOEXEC));
  struct stat before{}, after{};
  require(fd.get() >= 0 && ::fstat(fd.get(), &before) == 0 && S_ISREG(before.st_mode) &&
          before.st_size > 0 && before.st_size <= 512LL * 1024 * 1024, "process_binary_bound");
  EVP_MD_CTX *ctx = EVP_MD_CTX_new();
  require(ctx != nullptr, "digest_allocation");
  std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> guard(ctx, EVP_MD_CTX_free);
  require(EVP_DigestInit_ex(ctx, EVP_sha256(), nullptr) == 1, "digest_init");
  char buffer[16384]; uint64_t total = 0;
  while (true) {
    auto count = ::read(fd.get(), buffer, sizeof(buffer));
    if (count < 0 && errno == EINTR) continue;
    require(count >= 0, "binary_read");
    if (count == 0) break;
    total += static_cast<uint64_t>(count);
    require(total <= static_cast<uint64_t>(before.st_size) &&
            EVP_DigestUpdate(ctx, buffer, static_cast<size_t>(count)) == 1, "binary_changed");
  }
  unsigned char digest[EVP_MAX_MD_SIZE]; unsigned size = 0;
  require(total == static_cast<uint64_t>(before.st_size) && ::fstat(fd.get(), &after) == 0 &&
          same_stat(before, after) && EVP_DigestFinal_ex(ctx, digest, &size) == 1 && size == 32,
          "binary_changed");
  return p1_owned::hex(digest, size);
}
inline Process authenticate_process(const PeerPins &pins, const Json &manifest) {
  require(p1_owned::boot_id() == pins.boot_id, "process_boot");
  const auto root = "/proc/" + std::to_string(pins.pid);
  const auto stat = p1_owned::read_bounded(root + "/stat", 4096);
  const auto close = stat.rfind(')');
  require(close != std::string::npos && stat.substr(0, stat.find(' ')) == std::to_string(pins.pid),
          "process_stat");
  std::istringstream input(stat.substr(close + 1)); std::vector<std::string> fields; std::string field;
  while (input >> field) fields.push_back(field);
  require(fields.size() >= 20 && fields[0] != "Z" && fields[0] != "X", "process_not_live");
  Process p;
  size_t used = 0; p.start = std::stoull(fields[19], &used);
  require(used == fields[19].size() && p.start == pins.process_start_ticks, "process_start_ticks");
  p.pgid = std::stoll(fields[2]); p.sid = std::stoll(fields[3]);
  require(p.pgid == static_cast<int64_t>(uint_field(manifest, "pgid", INT_MAX)) &&
          p.sid == static_cast<int64_t>(uint_field(manifest, "sid", INT_MAX)), "process_group");
  std::array<char,4097> exe{};
  auto n = ::readlink((root + "/exe").c_str(), exe.data(), exe.size() - 1);
  require(n > 0 && static_cast<size_t>(n) < exe.size() - 1, "process_exe");
  p.exe.assign(exe.data(), static_cast<size_t>(n));
  require(p.exe == pins.exe, "process_exe");
  p.sha = process_binary_sha(root + "/exe");
  require(p.sha == pins.binary_sha256, "process_binary_sha");
  const auto cmdline = p1_owned::read_bounded(root + "/cmdline", 65536);
  p.argv = Json::array(); size_t begin = 0;
  for (size_t i = 0; i < cmdline.size(); ++i) if (cmdline[i] == '\0') {
    p.argv.push_back(cmdline.substr(begin, i - begin)); begin = i + 1;
  }
  require(begin == cmdline.size() && !p.argv.empty() && p.argv.size() <= 512 &&
          manifest.at("argv") == p.argv, "process_argv");
  return p;
}
}  // namespace detail

// Parse only the peer subobject of a separately authenticated supervisor pins
// file. Driver request/cleanup fields belong to a different enclosing object.
inline PeerPins from_json(const Json &j) {
  const std::set<std::string> expected = {"manifest_path","manifest_sha256","run_id","boot_id",
    "contract_sha256","producer_instance_id","config_hash","exe","binary_sha256",
    "source_bundle_sha256","effective_parameters_sha256","pid","process_start_ticks","topic","type"};
  detail::require(j.is_object() && j.size() == expected.size(), "pins_population");
  for (auto it = j.begin(); it != j.end(); ++it)
    detail::require(expected.count(it.key()) == 1, "unknown_pin_field");
  PeerPins p;
  p.manifest_path = detail::string_field(j,"manifest_path",4096);
  p.manifest_sha256 = detail::string_field(j,"manifest_sha256",64);
  p.run_id = detail::string_field(j,"run_id",128);
  p.boot_id = detail::string_field(j,"boot_id",64);
  p.contract_sha256 = detail::string_field(j,"contract_sha256",64);
  p.producer_instance_id = detail::string_field(j,"producer_instance_id",64);
  p.config_hash = detail::string_field(j,"config_hash",64);
  p.exe = detail::string_field(j,"exe",4096);
  p.binary_sha256 = detail::string_field(j,"binary_sha256",64);
  p.source_bundle_sha256 = detail::string_field(j,"source_bundle_sha256",64);
  p.effective_parameters_sha256 = detail::string_field(j,"effective_parameters_sha256",64);
  p.pid = static_cast<int64_t>(detail::uint_field(j,"pid",INT_MAX));
  p.process_start_ticks = detail::uint_field(j,"process_start_ticks",UINT64_MAX);
  p.topic = detail::string_field(j,"topic",256);
  p.type = detail::string_field(j,"type",256);
  return p;
}

// Source/bin/config and manifest authorship are independently supplied by the
// caller's supervisor. This class checks those pins, the initialized process,
// and each callback's actual DataWriter GID. It does not authenticate the plant,
// prove a continuous unique graph, or infer owner intent from process death.
class OwnedPeer {
 public:
  explicit OwnedPeer(PeerPins pins) : pins_(std::move(pins)) {
    using detail::require;
    static_assert(RMW_GID_STORAGE_SIZE == 16, "registered FastDDS GID domain changed");
    require(pins_.pid > 0 && pins_.pid <= INT_MAX && pins_.process_start_ticks > 0,
            "pin_process_domain");
    require(detail::visible_ascii(pins_.run_id,128) && detail::visible_ascii(pins_.boot_id,64) &&
            detail::visible_ascii(pins_.producer_instance_id,64) &&
            detail::visible_ascii(pins_.topic,256) && pins_.topic[0] == '/' &&
            detail::visible_ascii(pins_.type,256) && pins_.type.find("/msg/") != std::string::npos &&
            !pins_.exe.empty() && pins_.exe.size() <= 4096 && pins_.exe[0] == '/', "pin_identity_domain");
    for (const auto *sha : {&pins_.manifest_sha256,&pins_.contract_sha256,&pins_.config_hash,
         &pins_.binary_sha256,&pins_.source_bundle_sha256,&pins_.effective_parameters_sha256})
      require(p1_owned::sha256_shape(*sha), "pin_sha_shape");
    const auto raw = detail::read_manifest(pins_.manifest_path);
    require(p1_owned::sha256_bytes(raw) == pins_.manifest_sha256, "manifest_sha");
    manifest_ = detail::strict_json(raw);
    for (const auto &binding : std::vector<std::pair<const char *,std::string>>{
        {"schema_version","p1-owned-role-v1"},{"role","publisher"},{"run_id",pins_.run_id},
        {"boot_id",pins_.boot_id},{"contract_sha256",pins_.contract_sha256},
        {"producer_instance_id",pins_.producer_instance_id},{"config_hash",pins_.config_hash},
        {"exe",pins_.exe},{"binary_sha256",pins_.binary_sha256},
        {"source_bundle_sha256",pins_.source_bundle_sha256},
        {"effective_parameters_sha256",pins_.effective_parameters_sha256},
        {"rmw_implementation","rmw_fastrtps_cpp"},
        {"effective_parameters_digest_encoding","p1-typed-ieee754-v1"}}) {
      const size_t limit = std::string(binding.first) == "exe" ? 4096 : 256;
      require(detail::string_field(manifest_,binding.first,limit) == binding.second,
              std::string("manifest_binding_") + binding.first);
    }
    require(detail::uint_field(manifest_,"pid",INT_MAX) == static_cast<uint64_t>(pins_.pid) &&
            detail::uint_field(manifest_,"process_start_ticks",UINT64_MAX) == pins_.process_start_ticks,
            "manifest_process");
    const auto created = detail::uint_field(manifest_,"created_steady_ns",INT64_MAX);
    require(created > 0 && created <= static_cast<uint64_t>(p1_owned::steady_ns()), "manifest_time");
    detail::bool_field(manifest_,"effective_parameters_immutable",true);
    detail::bool_field(manifest_,"execute_qualified",false);
    detail::bool_field(manifest_,"physical_release_qualified",false);
    detail::parameter_rows(manifest_.at("effective_parameters"));
    detail::parameter_rows(manifest_.at("parameter_overrides"));
    require(p1_owned::sha256_bytes(p1_owned::canonical_parameters(manifest_.at("effective_parameters")).dump()) ==
            pins_.effective_parameters_sha256, "parameter_digest");
    require(manifest_.at("argv").is_array() && !manifest_.at("argv").empty() &&
            manifest_.at("argv").size() <= 512, "manifest_argv");
    for (const auto &arg : manifest_.at("argv"))
      require(arg.is_string() && arg.get_ref<const std::string &>().size() <= 65536 &&
              arg.get_ref<const std::string &>().find('\0') == std::string::npos, "manifest_argv_element");
    node_ = detail::string_field(manifest_,"node",256);
    require(node_[0] == '/' && detail::uint_field(manifest_,"gid_storage_size",16) == 16,
            "endpoint_domain");
    const auto &endpoints = manifest_.at("endpoints");
    require(endpoints.is_array() && !endpoints.empty() && endpoints.size() <= 128, "endpoint_population");
    std::set<std::string> unique; size_t matches = 0;
    for (const auto &ep : endpoints) {
      require(ep.is_object() && ep.size() == 4 && ep.contains("gid"), "endpoint_shape");
      const auto kind = detail::string_field(ep,"kind",16);
      const auto topic = detail::string_field(ep,"topic",256);
      const auto type = detail::string_field(ep,"type",256);
      require((kind == "publisher" || kind == "subscription") && topic[0] == '/' &&
              type.find("/msg/") != std::string::npos, "endpoint_shape");
      const auto &gid = ep.at("gid");
      require(gid.is_array() && gid.size() == gid_.size(), "endpoint_gid_shape");
      std::array<uint8_t,RMW_GID_STORAGE_SIZE> parsed{}; bool nonzero = false;
      for (size_t i = 0; i < parsed.size(); ++i) {
        const auto &byte = gid[i];
        require(byte.is_number_integer() && !byte.is_boolean() &&
          (byte.is_number_unsigned() || byte.get<int64_t>() >= 0) && byte.get<uint64_t>() <= 255,
          "endpoint_gid_byte");
        parsed[i] = static_cast<uint8_t>(byte.get<uint64_t>()); nonzero |= parsed[i] != 0;
      }
      require(nonzero && unique.insert(kind + ":" + topic + ":" + gid.dump()).second,
              "endpoint_gid_duplicate_or_zero");
      if (kind == "publisher" && topic == pins_.topic) {
        require(type == pins_.type, "endpoint_type"); ++matches; gid_ = parsed; endpoint_ = ep;
      }
    }
    require(matches == 1, "endpoint_missing_or_ambiguous");
    process_ = detail::authenticate_process(pins_,manifest_);
    pidfd_.reset(static_cast<int>(::syscall(SYS_pidfd_open,static_cast<pid_t>(pins_.pid),0)));
    require(pidfd_.get() >= 0, "pidfd_open");
    const auto after = detail::authenticate_process(pins_,manifest_);
    require(after.start == process_.start && after.pgid == process_.pgid && after.sid == process_.sid &&
            after.exe == process_.exe && after.sha == process_.sha && after.argv == process_.argv && alive(),
            "process_changed_during_pin");
    // Recheck the immutable manifest after process pinning; callback paths do no I/O.
    require(detail::read_manifest(pins_.manifest_path) == raw, "manifest_changed_during_pin");
    authenticated_ns_ = p1_owned::steady_ns();
  }
  OwnedPeer(const OwnedPeer &) = delete;
  OwnedPeer &operator=(const OwnedPeer &) = delete;
  bool alive() const { return liveness_reason().empty(); }
  bool gid_matches(const rclcpp::MessageInfo &info) const {
    const auto &message = info.get_rmw_message_info();
    if (message.from_intra_process || !message.publisher_gid.implementation_identifier ||
        std::strcmp(message.publisher_gid.implementation_identifier,"rmw_fastrtps_cpp") != 0) return false;
    for (size_t i = 0; i < gid_.size(); ++i)
      if (message.publisher_gid.data[i] != gid_[i]) return false;
    return true;
  }
  Json expected_gid() const { return endpoint_.at("gid"); }
  std::string callback_reason(const rclcpp::MessageInfo &info) const {
    const auto &message = info.get_rmw_message_info();
    if (message.from_intra_process) return "callback_intra_process_outside_registered_domain";
    if (!message.publisher_gid.implementation_identifier ||
        std::strcmp(message.publisher_gid.implementation_identifier,"rmw_fastrtps_cpp") != 0)
      return "callback_rmw_implementation";
    for (size_t i = 0; i < gid_.size(); ++i)
      if (message.publisher_gid.data[i] != gid_[i]) return "callback_foreign_gid";
    // A queued valid-GID tail after exit may be retained as raw evidence. This
    // result forbids admitting it as live-owner feedback or starting a new Job.
    return liveness_reason();
  }
  bool graph_matches_snapshot(rclcpp::Node &node) const {
    if (!alive()) return false;
    const auto rows = node.get_publishers_info_by_topic(pins_.topic);
    if (rows.size() != 1 || rows[0].topic_type() != pins_.type || rows[0].endpoint_gid() != gid_) return false;
    auto name_space = rows[0].node_namespace();
    const auto full = (name_space == "/" ? "/" : name_space + "/") + rows[0].node_name();
    return full == node_;
  }
  Json evidence() const {
    return {{"schema","p1-owned-peer-C3_6-v1"},{"manifest_path",pins_.manifest_path},
      {"manifest_sha256",pins_.manifest_sha256},{"run_id",pins_.run_id},{"boot_id",pins_.boot_id},
      {"contract_sha256",pins_.contract_sha256},{"producer_instance_id",pins_.producer_instance_id},
      {"config_hash",pins_.config_hash},{"source_bundle_sha256",pins_.source_bundle_sha256},
      {"binary_sha256",pins_.binary_sha256},{"effective_parameters_sha256",pins_.effective_parameters_sha256},
      {"pid",pins_.pid},{"process_start_ticks",pins_.process_start_ticks},{"pgid",process_.pgid},
      {"sid",process_.sid},{"exe",process_.exe},{"node",node_},{"endpoint",endpoint_},{"gid",expected_gid()},
      {"authenticated_steady_ns",authenticated_ns_},{"pidfd_alive_at_evidence_call",alive()},
      {"callback_policy","exact_DataWriter_GID_and_zero_wait_pidfd"},
      {"manifest_authorship_policy","pins supplied by independently authenticated external supervisor"},
      {"post_pin_exec_continuity","unknown"},{"continuous_DDS_uniqueness","unknown"},
      {"owner_close_intent","unknown"},{"owner_endpoints_exited","unknown"},
      {"plant_acceptance","unknown"},{"stage_qualified",false},{"execute_qualified",false}};
  }
 private:
  std::string liveness_reason() const {
    pollfd fd{pidfd_.get(),POLLIN,0}; const auto result = ::poll(&fd,1,0);
    if (result == 0) return "";
    if (result < 0 || (fd.revents & (POLLERR | POLLNVAL))) return "owner_liveness_check_failed";
    return (fd.revents & (POLLIN | POLLHUP)) ? "owner_process_exited" : "owner_liveness_check_failed";
  }
  PeerPins pins_;
  Json manifest_, endpoint_;
  std::string node_;
  std::array<uint8_t,RMW_GID_STORAGE_SIZE> gid_{};
  detail::Process process_;
  detail::Fd pidfd_;
  int64_t authenticated_ns_ = 0;
};
}  // namespace c36_owned
