// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// 实船干跑求解（shipboard_dry_run）的 ROS-free 核心门控、候选验收与名义延续状态机。
//
// 本头严格维持三把物理锁恒为 false：
//   * physical_output_enabled = false
//   * closed_loop_verified    = false
//   * anchor_known            = false
// 内部维护的 nominal_continuity_n_ 仅用于 SolverJob 递推边界连续性（在 Job 内按
// protocol.hpp 约束填入 anchor_source="dry_run_nominal_command"），绝不在状态或
// 决策日志中伪称为真实硬件执行锚点。
#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <string>
#include <nlohmann/json.hpp>

namespace p1_dry_run {

using Json = nlohmann::json;

struct DryRunLimits {
  std::int64_t odom_age_ns = 1000000000LL;
  std::int64_t imu_age_ns = 500000000LL;
  std::int64_t tick_period_ns = 200000000LL;
  std::int64_t deadline_ns = 150000000LL;
  double command_min_n = -25.0;
  double command_max_n = 25.0;
  double rho_n_s = 80.0;
  double map_scale = 1.0;
  double publisher_max_n = 100.0;
  std::string expected_pose_frame = "map";
  std::string expected_child_frame = "base_link";
  std::string expected_imu_frame = "base_link";
};

inline DryRunLimits limits_from_contract(const Json & c) {
  DryRunLimits out;
  out.odom_age_ns = c.at("odom_age_ns").get<std::int64_t>();
  out.imu_age_ns = c.at("imu_age_ns").get<std::int64_t>();
  out.tick_period_ns = c.at("T_ns").get<std::int64_t>();
  out.deadline_ns = c.at("deadline_ns").get<std::int64_t>();
  out.command_min_n = c.at("command_min_n").get<double>();
  out.command_max_n = c.at("command_max_n").get<double>();
  out.rho_n_s = c.at("rho_n_s").get<double>();
  out.map_scale = c.at("map_scale").get<double>();
  out.publisher_max_n = c.at("publisher_max_n").get<double>();
  out.expected_pose_frame = c.at("expected_pose_frame").get<std::string>();
  out.expected_child_frame = c.at("expected_child_frame").get<std::string>();
  out.expected_imu_frame = c.at("expected_imu_frame").get<std::string>();
  return out;
}

struct OdomFacts {
  bool seen = false;
  bool valid = false;
  bool finite = false;
  std::string pose_frame;
  std::string child_frame;
  std::uint64_t seq = 0;
  std::int64_t receipt_ns = 0;
  std::int64_t stamp_ns = 0;
  std::array<double, 6> state{0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
};

struct ImuFacts {
  bool seen = false;
  bool valid = false;
  bool finite = false;
  std::string frame;
  std::uint64_t seq = 0;
  std::int64_t receipt_ns = 0;
  std::int64_t stamp_ns = 0;
  double r = 0.0;
};

struct PathFacts {
  bool seen = false;
  bool resource_valid = false;
  std::string frame;
  std::uint64_t seq = 0;
  std::int64_t receipt_ns = 0;
  std::int64_t stamp_ns = 0;
  std::size_t points = 0;
};

struct ProfileFacts {
  bool seen = false;
  bool resource_valid = false;
  std::uint64_t seq = 0;
  std::int64_t receipt_ns = 0;
  std::int64_t stamp_ns = 0;
  std::size_t rows = 0;
  bool stamp_ok = false;
  bool path_profile_sync_ok = false;
  std::string sync_reason;
};

struct CandidateFacts {
  std::uint64_t job_id = 0;
  std::uint64_t tick = 0;
  std::string worker_instance;
  std::string expected_worker_instance;
  std::string backend;
  bool echo_matched = false;
  bool success = false;
  bool prediction_available = false;
  bool solver_invoked = false;
  bool finite = false;
  double backend_ms = 0.0;
  std::array<double, 2> first_control{0.0, 0.0};
  bool initial_control_matches = false;
  bool initial_state_matches = false;
  std::int64_t freeze_steady_ns = 0;
  std::int64_t worker_receive_ns = 0;
  std::int64_t solve_start_ns = 0;
  std::int64_t solve_end_ns = 0;
  std::int64_t deadline_steady_ns = 0;
  std::int64_t receive_ns = 0;
};

struct CandidateOutcome {
  bool accepted = false;
  std::string reason;
  std::array<double, 2> clamped_control{0.0, 0.0};
  std::int64_t solve_latency_ns = 0;
};

class DryRunCoordinator {
 public:
  static constexpr bool kPhysicalOutputEnabled = false;
  static constexpr bool kClosedLoopVerified = false;
  static constexpr bool kControlInputsVerified = false;
  static constexpr bool kAnchorKnown = false;

  DryRunCoordinator() = default;
  explicit DryRunCoordinator(const DryRunLimits & limits) : limits_(limits) {}

  void arm(std::int64_t start_ns) {
    nominal_anchor_time_ns_ = start_ns > 0 ? start_ns : 1LL;
  }

  void on_odom(const OdomFacts & f) { odom_ = f; }
  void on_imu(const ImuFacts & f) { imu_ = f; }
  void on_path(const PathFacts & f) { path_ = f; }
  void on_profile(const ProfileFacts & f) { profile_ = f; }
  void set_profile_sync(bool ok, const std::string & reason) {
    profile_.path_profile_sync_ok = ok;
    profile_.sync_reason = reason;
  }

  void record_job_submitted() { ++jobs_submitted_; }

  std::string nav_gate(std::int64_t now_ns) const {
    if (!odom_.seen) return "waiting_odom";
    if (odom_.pose_frame != limits_.expected_pose_frame ||
        odom_.child_frame != limits_.expected_child_frame) {
      return "bad_odom_frame";
    }
    if (!odom_.finite || !odom_.valid) return "invalid_odom";
    if (now_ns - odom_.receipt_ns > limits_.odom_age_ns) return "odom_stale";

    if (!imu_.seen) return "waiting_imu";
    if (imu_.frame != limits_.expected_imu_frame) return "bad_imu_frame";
    if (!imu_.finite || !imu_.valid) return "invalid_imu";
    if (now_ns - imu_.receipt_ns > limits_.imu_age_ns) return "imu_stale";

    if (!path_.seen) return "waiting_path";
    if (path_.frame != limits_.expected_pose_frame) return "bad_path_frame";
    if (!path_.resource_valid || path_.points < 2U) return "invalid_path";

    if (!profile_.seen) return "waiting_profile";
    if (!profile_.resource_valid || profile_.rows < 2U || !profile_.stamp_ok) {
      return "invalid_profile";
    }
    if (!profile_.path_profile_sync_ok) return "profile_sync_mismatch";
    return "ready";
  }

  bool nav_ready(std::int64_t now_ns) const { return nav_gate(now_ns) == "ready"; }

  std::array<double, 6> composed_state() const {
    auto s = odom_.state;
    if (imu_.seen && imu_.valid && imu_.finite) s[5] = imu_.r;
    return s;
  }

  CandidateOutcome evaluate_candidate(const CandidateFacts & cand) {
    ++candidates_received_;
    CandidateOutcome out;
    out.solve_latency_ns =
        cand.solve_end_ns >= cand.solve_start_ns ? (cand.solve_end_ns - cand.solve_start_ns) : -1;

    std::string reason;
    if (cand.expected_worker_instance.empty() ||
        cand.worker_instance != cand.expected_worker_instance ||
        cand.backend != "acados") {
      reason = "foreign_worker";
    } else if (!cand.echo_matched) {
      reason = "job_echo_mismatch";
    } else if (!cand.solver_invoked || !cand.success || !cand.prediction_available) {
      reason = "solver_failed";
    } else if (!cand.finite || !std::isfinite(cand.backend_ms) || cand.backend_ms < 0.0 ||
               !std::isfinite(cand.first_control[0]) || !std::isfinite(cand.first_control[1])) {
      reason = "nonfinite_or_timing";
    } else if (!cand.initial_control_matches) {
      reason = "first_control_mismatch";
    } else if (!cand.initial_state_matches) {
      reason = "prediction_initial_mismatch";
    } else if (!(cand.freeze_steady_ns > 0 &&
                 cand.freeze_steady_ns <= cand.worker_receive_ns &&
                 cand.worker_receive_ns <= cand.solve_start_ns &&
                 cand.solve_start_ns <= cand.solve_end_ns &&
                 cand.solve_end_ns <= cand.receive_ns)) {
      reason = "native_timing_order";
    } else if (cand.solve_end_ns > cand.deadline_steady_ns ||
               cand.receive_ns > cand.deadline_steady_ns) {
      reason = "deadline_exceeded";
    }

    if (reason.empty()) {
      const double lo = std::max(limits_.command_min_n, -limits_.publisher_max_n);
      const double hi = std::min(limits_.command_max_n, limits_.publisher_max_n);
      for (int i = 0; i < 2; ++i) {
        const double raw = cand.first_control[i];
        const double scaled = raw * limits_.map_scale;
        if (scaled < limits_.command_min_n || scaled > limits_.command_max_n ||
            std::abs(scaled) > limits_.publisher_max_n ||
            std::abs(scaled - raw) > 1e-9) {
          reason = "command_bounds";
          break;
        }
        out.clamped_control[i] = std::clamp(scaled, lo, hi);
      }
    }

    if (reason.empty()) {
      const double max_delta = limits_.rho_n_s * (limits_.tick_period_ns / 1e9) + 1e-6;
      for (int i = 0; i < 2; ++i) {
        if (std::abs(out.clamped_control[i] - nominal_continuity_n_[i]) > max_delta) {
          reason = "rate_limit_exceeded";
          break;
        }
      }
    }

    out.accepted = reason.empty();
    out.reason = reason;
    last_backend_ms_ = cand.backend_ms;
    last_solve_latency_ns_ = out.solve_latency_ns;
    last_first_control_ = cand.first_control;

    if (out.accepted) {
      ++candidates_accepted_;
      nominal_continuity_n_ = out.clamped_control;
      nominal_anchor_time_ns_ = cand.freeze_steady_ns;
      ++nominal_anchor_seq_;
      last_rejection_reason_.clear();
    } else {
      ++candidates_rejected_;
      last_rejection_reason_ = reason;
    }
    return out;
  }

  Json status_json(std::int64_t now_ns) const {
    Json out = Json::object();
    out["nav_gate"] = nav_gate(now_ns);
    out["nav_ready"] = out["nav_gate"] == "ready";
    out["jobs_submitted"] = jobs_submitted_;
    out["candidates_received"] = candidates_received_;
    out["candidates_accepted"] = candidates_accepted_;
    out["candidates_rejected"] = candidates_rejected_;
    out["last_rejection_reason"] = last_rejection_reason_;
    out["last_backend_ms"] = last_backend_ms_;
    out["last_solve_latency_ms"] = last_solve_latency_ns_ >= 0 ? last_solve_latency_ns_ / 1e6 : -1.0;
    out["last_first_control"] = last_first_control_;
    out["nominal_continuity_n"] = nominal_continuity_n_;
    out["physical_output_enabled"] = kPhysicalOutputEnabled;
    out["closed_loop_verified"] = kClosedLoopVerified;
    out["control_inputs_verified"] = kControlInputsVerified;
    out["anchor_known"] = kAnchorKnown;
    return out;
  }

  const DryRunLimits & limits() const { return limits_; }
  const OdomFacts & odom() const { return odom_; }
  const ImuFacts & imu() const { return imu_; }
  const PathFacts & path() const { return path_; }
  const ProfileFacts & profile() const { return profile_; }
  std::array<double, 2> nominal_continuity_n() const { return nominal_continuity_n_; }
  std::uint64_t nominal_anchor_seq() const { return nominal_anchor_seq_; }
  std::int64_t nominal_anchor_time_ns() const { return nominal_anchor_time_ns_; }
  std::uint64_t jobs_submitted() const { return jobs_submitted_; }
  std::uint64_t candidates_received() const { return candidates_received_; }
  std::uint64_t candidates_accepted() const { return candidates_accepted_; }
  std::uint64_t candidates_rejected() const { return candidates_rejected_; }

 private:
  DryRunLimits limits_{};
  OdomFacts odom_{};
  ImuFacts imu_{};
  PathFacts path_{};
  ProfileFacts profile_{};
  std::array<double, 2> nominal_continuity_n_{0.0, 0.0};
  std::int64_t nominal_anchor_time_ns_ = 1;
  std::uint64_t nominal_anchor_seq_ = 1;
  std::uint64_t jobs_submitted_ = 0;
  std::uint64_t candidates_received_ = 0;
  std::uint64_t candidates_accepted_ = 0;
  std::uint64_t candidates_rejected_ = 0;
  std::string last_rejection_reason_;
  double last_backend_ms_ = 0.0;
  std::int64_t last_solve_latency_ns_ = -1;
  std::array<double, 2> last_first_control_{0.0, 0.0};
};

}  // namespace p1_dry_run
