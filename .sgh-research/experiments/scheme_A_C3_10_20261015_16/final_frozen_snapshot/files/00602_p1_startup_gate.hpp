// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
// Isolated D1 preparation gate. It validates a driver's attestation; it does
// not independently prove the driver's graph, process, or Worker observations.
#pragma once

#include <openssl/evp.h>
#include "p1_create_only_atomic.hpp"
#include <algorithm>
#include <array>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <cerrno>
#include <chrono>
#include <filesystem>
#include <functional>
#include <fstream>
#include <iomanip>
#include <memory>
#include <limits>
#include <mutex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>

#ifndef P1_D1_SOURCE_BUNDLE_SHA256
#error "The isolated publisher requires an immutable build-time source bundle SHA256"
#endif
#ifndef P1_D1_F5_PARENT_MANIFEST_SHA256
#error "The isolated publisher requires its frozen F5 parent manifest SHA256"
#endif

namespace usv_mpc {
namespace p1_startup {
using Json = nlohmann::json;
inline int64_t steady_ns()
{
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
}
inline bool sha256_shape(const std::string & s)
{
  return s.size() == 64 && s.find_first_not_of("0123456789abcdef") == std::string::npos;
}
inline std::string sha256_bytes(const std::string & bytes)
{
  unsigned char digest[EVP_MAX_MD_SIZE]; unsigned int length = 0;
  if (EVP_Digest(bytes.data(), bytes.size(), digest, &length, EVP_sha256(), nullptr) != 1 ||
    length != 32) {throw std::runtime_error("SHA256 failed");}
  std::ostringstream out; out << std::hex << std::setfill('0');
  for (unsigned int i = 0; i < length; ++i) {out << std::setw(2) << int(digest[i]);}
  return out.str();
}
class Fd {
public:
  explicit Fd(int fd = -1) : value_(fd) {}
  ~Fd() {if (value_ >= 0) {::close(value_);}}
  Fd(const Fd &) = delete;
  Fd & operator=(const Fd &) = delete;
  Fd(Fd && other) noexcept : value_(other.value_) {other.value_ = -1;}
  int get() const {return value_;}
private:
  int value_;
};
// Walk from / using openat and O_NOFOLLOW. No resolve()/symlink traversal.
inline Fd open_directory(const std::filesystem::path & path)
{
  if (!path.is_absolute()) {throw std::runtime_error("gate path must be absolute");}
  int current = ::open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
  if (current < 0) {throw std::runtime_error("cannot open filesystem root");}
  for (const auto & component : path.relative_path()) {
    const std::string name = component.string();
    if (name.empty() || name == "." || name == "..") {
      ::close(current); throw std::runtime_error("gate path contains unsafe component");
    }
    const int next = ::openat(current, name.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    ::close(current);
    if (next < 0) {throw std::runtime_error("gate directory missing or symlink");}
    current = next;
  }
  return Fd(current);
}
inline void write_create_only(const std::filesystem::path & path, const std::string & bytes)
{
  const auto directory = open_directory(path.parent_path());
  const std::string name = path.filename().string();
  if (name.empty() || name == "." || name == "..") {throw std::runtime_error("unsafe output filename");}
  const std::string temporary = name + ".tmp." + std::to_string(::getpid()) + "." + std::to_string(steady_ns());
  p1_create_only::write_create_only_at(directory.get(), name, temporary, bytes, path.string());
}
inline bool read_regular_bounded(const std::filesystem::path & path, std::string & bytes,
  size_t max_bytes = 16384)
{
  const auto directory = open_directory(path.parent_path());
  Fd file(::openat(directory.get(), path.filename().c_str(), O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK));
  if (file.get() < 0) {
    if (errno == ENOENT) {return false;}
    throw std::runtime_error("gate input cannot be opened safely");
  }
  struct stat before{}, after{};
  if (::fstat(file.get(), &before) != 0 || !S_ISREG(before.st_mode) ||
    before.st_size <= 0 || static_cast<uint64_t>(before.st_size) > max_bytes || before.st_nlink != 1) {
    throw std::runtime_error("gate input is not a bounded, single-link regular file");
  }
  bytes.assign(static_cast<size_t>(before.st_size), '\0');
  size_t received = 0;
  while (received < bytes.size()) {
    const ssize_t count = ::read(file.get(), bytes.data() + received, bytes.size() - received);
    if (count < 0 && errno == EINTR) {continue;}
    if (count <= 0) {throw std::runtime_error("gate input changed or read failed");}
    received += static_cast<size_t>(count);
  }
  char extra = 0;
  if (::read(file.get(), &extra, 1) != 0 || ::fstat(file.get(), &after) != 0 ||
    before.st_dev != after.st_dev || before.st_ino != after.st_ino || before.st_size != after.st_size ||
    before.st_mtim.tv_sec != after.st_mtim.tv_sec || before.st_mtim.tv_nsec != after.st_mtim.tv_nsec ||
    before.st_ctim.tv_sec != after.st_ctim.tv_sec || before.st_ctim.tv_nsec != after.st_ctim.tv_nsec) {
    throw std::runtime_error("gate input changed during read");
  }
  return true;
}
inline Json strict_json(const std::string & bytes)
{
  std::vector<std::set<std::string>> object_keys;
  auto callback = [&object_keys](int, Json::parse_event_t event, Json & parsed) {
    if (event == Json::parse_event_t::object_start) {object_keys.emplace_back();}
    if (event == Json::parse_event_t::key &&
      !object_keys.back().insert(parsed.get<std::string>()).second) {
      throw std::runtime_error("duplicate gate JSON key");
    }
    if (event == Json::parse_event_t::object_end) {object_keys.pop_back();}
    return true;
  };
  return Json::parse(bytes, callback);
}
inline void exact_keys(const Json & object, const std::set<std::string> & expected)
{
  if (!object.is_object()) {throw std::runtime_error("gate JSON object required");}
  std::set<std::string> actual;
  for (auto it = object.begin(); it != object.end(); ++it) {actual.insert(it.key());}
  if (actual != expected) {throw std::runtime_error("gate JSON keys differ from protocol");}
}
inline std::string binary_sha256()
{
  // /proc/self/exe is a kernel-owned executable identity, intentionally not a
  // caller-owned filesystem path. Opening its fd pins the currently executing inode.
  Fd fd(::open("/proc/self/exe", O_RDONLY | O_CLOEXEC));
  struct stat stat{};
  if (fd.get() < 0 || ::fstat(fd.get(), &stat) != 0 || !S_ISREG(stat.st_mode) ||
    stat.st_size <= 0 || stat.st_size > 134217728) {throw std::runtime_error("executable identity read failed");}
  std::string bytes(static_cast<size_t>(stat.st_size), '\0'); size_t size = 0;
  while (size < bytes.size()) {
    const ssize_t count = ::read(fd.get(), bytes.data() + size, bytes.size() - size);
    if (count < 0 && errno == EINTR) {continue;}
    if (count <= 0) {throw std::runtime_error("executable identity truncated");}
    size += static_cast<size_t>(count);
  }
  return sha256_bytes(bytes);
}
inline uint64_t process_start_ticks()
{
  std::ifstream input("/proc/self/stat"); std::string row; std::getline(input, row);
  const auto close = row.rfind(')');
  if (close == std::string::npos) {throw std::runtime_error("process start identity missing");}
  std::istringstream fields(row.substr(close + 2)); std::string value;
  for (int index = 0; index <= 19; ++index) {
    if (!(fields >> value)) {throw std::runtime_error("process stat truncated");}
  }
  size_t consumed = 0; const uint64_t ticks = std::stoull(value, &consumed);
  if (consumed != value.size() || ticks == 0) {throw std::runtime_error("process start identity invalid");}
  return ticks;
}
}  // namespace p1_startup

class PublisherStartupGate {
public:
  PublisherStartupGate(const std::filesystem::path & output,
    const std::filesystem::path & release_file, p1_startup::Json identity)
  : release_file_(release_file), receipt_file_(output / "release_receipt.json"),
    manifest_file_(output / "startup_manifest.json")
  {
    if (!release_file.is_absolute()) {throw std::runtime_error("p1_release_file must be absolute");}
    (void)p1_startup::open_directory(release_file.parent_path());
    for (const auto key : {"run_id", "producer_instance_id", "steady_clock_domain", "baseline_id"}) {
      if (!identity.at(key).is_string() || identity.at(key).get<std::string>().empty()) {
        throw std::runtime_error("startup identity missing");
      }
    }
    if (identity.at("baseline_id") != "F5_20261005_atomic_freeze_01") {
      throw std::runtime_error("startup must bind frozen F5 baseline lineage");
    }
    for (const auto key : {"config_hash", "nominal_config_hash"}) {
      if (!identity.at(key).is_string() || !p1_startup::sha256_shape(identity.at(key))) {
        throw std::runtime_error("startup identity SHA256 missing");
      }
    }
    const std::string source = P1_D1_SOURCE_BUNDLE_SHA256;
    const std::string parent = P1_D1_F5_PARENT_MANIFEST_SHA256;
    if (!p1_startup::sha256_shape(source) || !p1_startup::sha256_shape(parent) ||
      parent != "77737a5924f1bcd97996dee3c08e204a4a4c8fbf2f3716ff65d41fbc4bad6762") {
      throw std::runtime_error("startup compiled lineage invalid");
    }
    std::ifstream boot("/proc/sys/kernel/random/boot_id"); std::string boot_id; std::getline(boot, boot_id);
    if (boot_id.size() != 36 || identity.at("steady_clock_domain") != boot_id + ":steady_clock") {
      throw std::runtime_error("startup boot/domain mismatch");
    }
    identity["schema_version"] = "p1-D1-publisher-startup-v1";
    identity["derived_publisher"] = true;
    identity["physical_output_state"] = "held";
    identity["boot_id"] = boot_id;
    identity["pid"] = ::getpid();
    identity["process_start_ticks"] = p1_startup::process_start_ticks();
    identity["created_steady_ns"] = p1_startup::steady_ns();
    identity["source_bundle_sha256"] = source;
    identity["binary_sha256"] = p1_startup::binary_sha256();
    identity["parent_baseline_manifest_sha256"] = parent;
    identity["parent_mpc_node_source_sha256"] = "2f1b457ce9644d6ceff722e4ce328fa6a5de23a2cb94f8470c022e0bd70f2dd8";
    identity["driver_process_graph_worker_evidence_verified_by_publisher"] = false;
    identity_ = std::move(identity);
    const std::string bytes = identity_.dump(2) + "\n";
    if (bytes.size() > 16384) {throw std::runtime_error("startup manifest exceeds fixed 16 KiB budget");}
    if (identity_.contains("owned_manifest_file")) {
      if (identity_.at("owned_manifest_file") != "owned_manifest.json" ||
        !identity_.at("owned_manifest_sha256").is_string() ||
        !p1_startup::sha256_shape(identity_.at("owned_manifest_sha256")) ||
        !identity_.at("effective_parameters_sha256").is_string() ||
        !p1_startup::sha256_shape(identity_.at("effective_parameters_sha256"))) {
        throw std::runtime_error("startup owned manifest binding invalid");
      }
      owned_manifest_file_ = output / "owned_manifest.json";
      verify_owned_manifest_locked_();
    }
    p1_startup::write_create_only(manifest_file_, bytes);
    manifest_sha256_ = p1_startup::sha256_bytes(bytes);
  }

  // Only the controller's preparation/timer path may accept a release. Output
  // helpers and shutdown can verify an already accepted release, never accept one.
  bool poll_release(const std::function<bool()> & arm_and_verify)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    increment_counter_(observation_.poll_count);
    if (state_ == State::Fault) {return false;}
    if (state_ == State::Released) {return verify_locked_();}
    try {
      observation_.phase = Phase::ManifestVerification;
      verify_manifest_locked_();
      std::string bytes;
      observation_.phase = Phase::ReleaseRead;
      observation_.release_read_completed = false;
      observation_.release_present = false; observation_.release_bytes_count = 0;
      observation_.release_read_end_ns = 0;
      observation_.release_read_start_ns = p1_startup::steady_ns();
      const bool release_present = p1_startup::read_regular_bounded(release_file_, bytes);
      observation_.release_read_end_ns = p1_startup::steady_ns();
      observation_.release_read_completed = true;
      observation_.release_present = release_present;
      observation_.release_bytes_count = bytes.size();
      if (!release_present) {increment_counter_(observation_.missing_release_count); return false;}
      observation_.phase = Phase::ReleaseValidation;
      const auto release = p1_startup::strict_json(bytes);
      p1_startup::exact_keys(release, {"schema_version", "run_id", "producer_instance_id",
        "startup_manifest_sha256", "release_nonce", "driver_evidence_sha256", "valid_until_steady_ns", "gates"});
      if (release.at("schema_version") != "p1-D1-publisher-release-v1" ||
        release.at("run_id") != identity_.at("run_id") ||
        release.at("producer_instance_id") != identity_.at("producer_instance_id") ||
        release.at("startup_manifest_sha256") != manifest_sha256_) {
        throw std::runtime_error("release identity/manifest mismatch");
      }
      if (!release.at("release_nonce").is_string()) {throw std::runtime_error("release nonce type invalid");}
      const std::string nonce = release.at("release_nonce");
      if (nonce.size() != 32 || nonce.find_first_not_of("0123456789abcdef") != std::string::npos ||
        !release.at("driver_evidence_sha256").is_string() ||
        !p1_startup::sha256_shape(release.at("driver_evidence_sha256"))) {
        throw std::runtime_error("release nonce/evidence SHA256 invalid");
      }
      const auto & gates = release.at("gates");
      p1_startup::exact_keys(gates, {"external_worker_zero_hooks", "subscriptions_verified", "unique_dual_channel_owner"});
      for (auto it = gates.begin(); it != gates.end(); ++it) {
        if (!it.value().is_boolean() || !it.value().get<bool>()) {
          throw std::runtime_error("release preparation gate unready");
        }
      }
      const auto & deadline_json = release.at("valid_until_steady_ns");
      if (!deadline_json.is_number_integer() ||
        (deadline_json.is_number_unsigned() && deadline_json.get<uint64_t>() >
        static_cast<uint64_t>(std::numeric_limits<int64_t>::max()))) {
        throw std::runtime_error("release expiry must be an exact positive int64");
      }
      const int64_t valid_until = deadline_json.get<int64_t>();
      observation_.valid_until_read = true; observation_.valid_until_ns = valid_until;
      const int64_t validate_ns = now_();
      observation_.validate_now_read = true; observation_.validate_now_ns = validate_ns;
      if (validate_ns <= 0 || valid_until <= validate_ns || valid_until - validate_ns > 60000000000LL) {
        throw std::runtime_error("release expired or validity exceeds 60 seconds");
      }
      observation_.phase = Phase::TelemetryArm;
      observation_.arm_start_ns = p1_startup::steady_ns();
      const bool armed = arm_and_verify();
      observation_.arm_end_ns = p1_startup::steady_ns();
      if (!armed) {throw std::runtime_error("research telemetry could not be armed");}
      const int64_t attempt_ns = now_();
      observation_.attempt_now_read = true; observation_.attempt_now_ns = attempt_ns;
      if (attempt_ns >= valid_until) {throw std::runtime_error("release expired while telemetry armed");}
      const std::string release_sha = p1_startup::sha256_bytes(bytes);
      observation_.release_sha_read = true;
      std::copy(release_sha.begin(), release_sha.end(), observation_.release_sha.begin());
      auto receipt = identity_;
      receipt["schema_version"] = "p1-D1-publisher-release-receipt-v1";
      // This create-only receipt records prepared acceptance. It precedes the
      // final in-memory commit and cannot qualify physical release by itself.
      receipt["physical_output_state"] = "held_pending_in_memory_commit";
      receipt["status"] = "prepared_acceptance";
      receipt["receipt_qualifies_physical_release"] = false;
      receipt["startup_manifest_sha256"] = manifest_sha256_;
      receipt["release_file_sha256"] = release_sha;
      receipt["driver_evidence_sha256"] = release.at("driver_evidence_sha256");
      receipt["release_nonce"] = nonce;
      receipt["attempted_acceptance_steady_ns"] = attempt_ns;
      receipt["valid_until_steady_ns"] = valid_until;
      receipt["research_armed_before_release"] = true;
      observation_.phase = Phase::ReceiptIo;
      observation_.receipt_io_start_ns = p1_startup::steady_ns();
      p1_startup::write_create_only(receipt_file_, receipt.dump(2) + "\n");
      observation_.receipt_io_end_ns = p1_startup::steady_ns();
      receipt_io_completed_ = true;
      observation_.phase = Phase::FinalFreshness;
      const int64_t final_freshness_ns = now_();
      observation_.final_now_read = true; observation_.final_now_ns = final_freshness_ns;
      if (final_freshness_ns >= valid_until) {throw std::runtime_error("release expired after receipt IO; output remains held");}
      observation_.phase = Phase::InMemoryCommit;
      accepted_release_sha256_ = release_sha; state_ = State::Released;
      observation_.commit_ns = p1_startup::steady_ns();
      return true;
    } catch (const std::exception & error) {
      fail_locked_(error.what()); return false;
    }
  }
  bool released_and_unchanged()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    return state_ == State::Released && verify_locked_();
  }
  bool failed() const {std::lock_guard<std::mutex> lock(mutex_); return state_ == State::Fault;}
  std::string failure_reason() const {std::lock_guard<std::mutex> lock(mutex_); return failure_reason_;}
  bool receipt_io_completed() const {std::lock_guard<std::mutex> lock(mutex_); return receipt_io_completed_;}
  // Diagnostic copy only: it never polls, arms, verifies, or changes a gate.
  // All fields are copied under the original gate mutex. Filesystem IO belongs
  // to the post-shutdown controller writer, outside release acceptance.
  p1_startup::Json observation() const
  {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto nullable = [](bool read, int64_t value) -> p1_startup::Json {
        return read ? p1_startup::Json(value) : p1_startup::Json(nullptr);
      };
    const auto time_or_null = [&nullable](int64_t value) {return nullable(value != 0, value);};
    return {{"gate_state", state_ == State::Held ? "Held" : state_ == State::Released ? "Released" : "Fault"},
      {"failure_reason", failure_reason_}, {"failure_phase", phase_name_(observation_.failure_phase)},
      {"last_phase", phase_name_(observation_.phase)},
      {"poll_count", observation_.poll_count}, {"missing_release_count", observation_.missing_release_count},
      {"released_integrity_verify_count", observation_.verify_count},
      {"release_read_completed", observation_.release_read_completed},
      {"release_present_at_last_completed_read", observation_.release_read_completed ?
        p1_startup::Json(observation_.release_present) : p1_startup::Json(nullptr)},
      {"release_bytes_count", observation_.release_read_completed ?
        p1_startup::Json(observation_.release_bytes_count) : p1_startup::Json(nullptr)},
      {"release_file_sha256", observation_.release_sha_read ?
        p1_startup::Json(std::string(observation_.release_sha.begin(), observation_.release_sha.end())) : p1_startup::Json(nullptr)},
      {"accepted_release_sha256", accepted_release_sha256_.empty() ? p1_startup::Json(nullptr) : p1_startup::Json(accepted_release_sha256_)},
      {"valid_until_steady_ns", nullable(observation_.valid_until_read, observation_.valid_until_ns)},
      {"validate_now_ns", nullable(observation_.validate_now_read, observation_.validate_now_ns)},
      {"attempt_now_ns", nullable(observation_.attempt_now_read, observation_.attempt_now_ns)},
      {"final_freshness_now_ns", nullable(observation_.final_now_read, observation_.final_now_ns)},
      {"original_freshness_read_count", int(observation_.validate_now_read) +
        int(observation_.attempt_now_read) + int(observation_.final_now_read)},
      {"release_read_start_steady_ns", time_or_null(observation_.release_read_start_ns)},
      {"release_read_end_steady_ns", time_or_null(observation_.release_read_end_ns)},
      {"arm_start_steady_ns", time_or_null(observation_.arm_start_ns)},
      {"arm_end_steady_ns", time_or_null(observation_.arm_end_ns)},
      {"receipt_io_start_steady_ns", time_or_null(observation_.receipt_io_start_ns)},
      {"receipt_io_end_steady_ns", time_or_null(observation_.receipt_io_end_ns)},
      {"receipt_io_completed", receipt_io_completed_}, {"commit_steady_ns", time_or_null(observation_.commit_ns)},
      {"failure_steady_ns", time_or_null(observation_.failure_ns)},
      {"observation_qualifies_physical_release", false}, {"business_policy_changed", false}};
  }
  const p1_startup::Json & identity() const {return identity_;}
  const std::string & manifest_sha256() const {return manifest_sha256_;}
private:
#ifdef P1_PUBLISHER_TEST
  friend class MpcControllerNodeTestAccess;
  std::function<int64_t()> p1_test_now_;
#endif
  int64_t now_() const
  {
#ifdef P1_PUBLISHER_TEST
    if (p1_test_now_) {return p1_test_now_();}
#endif
    return p1_startup::steady_ns();
  }
  enum class State {Held, Released, Fault};
  enum class Phase {None, ManifestVerification, ReleaseRead, ReleaseValidation,
    TelemetryArm, ReceiptIo, FinalFreshness, InMemoryCommit, ReleasedIntegrity};
  static const char * phase_name_(Phase phase)
  {
    switch (phase) {
      case Phase::None: return "none";
      case Phase::ManifestVerification: return "manifest_verification";
      case Phase::ReleaseRead: return "release_read";
      case Phase::ReleaseValidation: return "release_parse_and_validation";
      case Phase::TelemetryArm: return "telemetry_arm";
      case Phase::ReceiptIo: return "receipt_io";
      case Phase::FinalFreshness: return "final_freshness_check";
      case Phase::InMemoryCommit: return "in_memory_commit";
      case Phase::ReleasedIntegrity: return "released_integrity_verification";
    }
    return "none";
  }
  struct Observation {
    uint64_t poll_count = 0, missing_release_count = 0, verify_count = 0, release_bytes_count = 0;
    Phase phase = Phase::None, failure_phase = Phase::None;
    bool release_read_completed = false, release_present = false, release_sha_read = false;
    bool valid_until_read = false, validate_now_read = false, attempt_now_read = false, final_now_read = false;
    int64_t valid_until_ns = 0, validate_now_ns = 0, attempt_now_ns = 0, final_now_ns = 0;
    int64_t release_read_start_ns = 0, release_read_end_ns = 0, arm_start_ns = 0, arm_end_ns = 0;
    int64_t receipt_io_start_ns = 0, receipt_io_end_ns = 0, commit_ns = 0, failure_ns = 0;
    std::array<char, 64> release_sha{};
  };
  static void increment_counter_(uint64_t & value)
  {
    if (value != std::numeric_limits<uint64_t>::max()) {++value;}
  }
  bool verify_locked_()
  {
    increment_counter_(observation_.verify_count); observation_.phase = Phase::ReleasedIntegrity;
    try {
      verify_manifest_locked_();
      std::string bytes;
      if (!p1_startup::read_regular_bounded(release_file_, bytes) ||
        p1_startup::sha256_bytes(bytes) != accepted_release_sha256_) {
        throw std::runtime_error("accepted release removed or replaced");
      }
      return true;
    } catch (const std::exception & error) {fail_locked_(error.what()); return false;}
  }
  void verify_manifest_locked_() const
  {
    std::string bytes;
    if (!p1_startup::read_regular_bounded(manifest_file_, bytes) ||
      p1_startup::sha256_bytes(bytes) != manifest_sha256_) {
      throw std::runtime_error("startup manifest removed or replaced");
    }
    verify_owned_manifest_locked_();
  }
  void verify_owned_manifest_locked_() const
  {
    if (owned_manifest_file_.empty()) {return;}
    std::string bytes;
    if (!p1_startup::read_regular_bounded(owned_manifest_file_, bytes, 262144) ||
      p1_startup::sha256_bytes(bytes) != identity_.at("owned_manifest_sha256")) {
      throw std::runtime_error("owned manifest removed or replaced");
    }
  }
  void fail_locked_(const std::string & reason)
  {
    observation_.failure_phase = observation_.phase;
    observation_.failure_ns = p1_startup::steady_ns();
    state_ = State::Fault; failure_reason_ = reason.substr(0, 160);
  }
  std::filesystem::path release_file_, receipt_file_, manifest_file_, owned_manifest_file_;
  p1_startup::Json identity_;
  std::string manifest_sha256_, accepted_release_sha256_, failure_reason_;
  mutable std::mutex mutex_;
  State state_ = State::Held;
  bool receipt_io_completed_ = false;
  Observation observation_;
};
}  // namespace usv_mpc
