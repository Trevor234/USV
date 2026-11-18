// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// Finite, bounded GP snapshot schedule & horizon evaluator for Scheme A (WP6/WP7).
// Enforces cryptographic binding between controller nominal hydrodynamics,
// loaded gp-snapshot-v1 artifacts, activation generations, and 3x21 stage residuals.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>

#include <Eigen/Dense>

#include "gp_predictor.hpp"
#include "usv_nmpc/usv_model_dynamic.hpp"

namespace p1_gp_snap
{

inline constexpr std::size_t kMaxGpEntries = 8;
inline constexpr int kHorizonSteps = 20;
inline constexpr int kResidualDims = 3;
inline constexpr std::size_t kStageResidualFloats = 63;  // 3 * (20 + 1), column-major

/// Exact cross-language SHA-256 matching Python `HydroParams.canonical_sha256`.
std::string canonical_nominal_hydro_sha256(
    const usv_mpc::HydroParams & hydro,
    double dt_s = 0.2,
    int rk4_substeps = 4);

/// Canonical little-endian IEEE-754 SHA-256 over the 63 stage residual doubles.
std::string compute_stage_residuals_digest(const std::array<double, kStageResidualFloats> & flat);

struct GpScheduleEntry
{
  std::uint64_t generation = 0;
  std::uint64_t first_target_tick = 1;
  std::uint64_t last_target_tick = 0;  // 0 means open-ended tail
  bool is_zero = true;
  std::string file_path;
  p1_gp::GpResidualModel model;
};

struct GpSelection
{
  bool valid = false;
  std::uint64_t generation = 0;
  const GpScheduleEntry * entry = nullptr;
  std::string reason;

  explicit operator bool() const noexcept { return valid && entry != nullptr; }
};

class GpSnapshotRegistry
{
public:
  static GpSnapshotRegistry create_zero_only(const std::string & nominal_hydro_hash);

  static GpSnapshotRegistry create_single_file(
      const std::string & path,
      const std::string & expected_sha256,
      const std::string & nominal_hydro_hash);

  static GpSnapshotRegistry create_from_schedule_json(
      const std::string & schedule_path,
      const std::string & expected_schedule_sha256,
      const std::string & nominal_hydro_hash);

  static GpSnapshotRegistry initialize_from_params(
      const std::string & snapshot_file,
      const std::string & snapshot_sha256,
      const std::string & schedule_file,
      const std::string & schedule_sha256,
      const std::string & nominal_hydro_hash);

  GpSelection resolve(std::uint64_t target_tick) const noexcept;
  const GpScheduleEntry * find(std::uint64_t generation) const noexcept;
  std::size_t size() const noexcept { return count_; }
  const std::string & nominal_hydro_hash() const noexcept { return nominal_hydro_hash_; }

private:
  std::string nominal_hydro_hash_;
  std::array<GpScheduleEntry, kMaxGpEntries> entries_{};
  std::size_t count_ = 0;

  void add_entry(GpScheduleEntry entry);
};

struct StageResidualEvalResult
{
  std::array<double, kStageResidualFloats> residuals{};  // column-major 3x21, k=20 strictly 0
  std::string digest;
  bool ood_detected = false;
  std::uint32_t ood_stage_count = 0;
};

/// Evaluate GP model along k=0..19 for trajectory (traj_x: 6x21, traj_u: 2x20).
/// Terminal slot k=20 (indices 60..62) is always zeroed as specified by WP6.
StageResidualEvalResult evaluate_gp_horizon(
    const p1_gp::GpResidualModel & model,
    const Eigen::MatrixXd & traj_x,
    const Eigen::MatrixXd & traj_u,
    bool ood_fallback_zero = true);

/// Build a physically consistent 6x21 / 2x20 trajectory guess for GP evaluation,
/// either by shifting a nearby previous accepted MPC trajectory or rolling out
/// nominal Fossen RK4 + GP under a slew-clamped feedback guess.
void build_gp_rollout_guess(
    const usv_mpc::Vector6d & x0,
    const Eigen::MatrixXd & ref,
    const Eigen::Vector2d & anchor,
    const usv_mpc::HydroParams & hydro,
    double dt,
    double t_min,
    double t_max,
    double dt_max,
    const p1_gp::GpResidualModel & model,
    bool ood_fallback_zero,
    const Eigen::MatrixXd * prev_x,
    const Eigen::MatrixXd * prev_u,
    int tick_shift,
    Eigen::MatrixXd & out_x,
    Eigen::MatrixXd & out_u);

}  // namespace p1_gp_snap
