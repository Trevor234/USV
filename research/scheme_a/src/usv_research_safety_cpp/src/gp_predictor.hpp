// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// C++ runtime evaluator for `gp-snapshot-v1` (Titsias Sparse ARD-RBF GP).
// Provides deterministic O(M) mean + variance prediction, OOD envelope guard,
// residual clip bounds, and zero-residual fallback without external ML libs.
#pragma once

#include <array>
#include <cstddef>
#include <string>
#include <vector>

namespace p1_gp
{

inline constexpr const char * kExpectedSnapshotSchema = "gp-snapshot-v1";
inline constexpr const char * kExpectedCodegenLayout = "usv_dyn_nmpc_np12_ny13_v1";

struct GpChannelModel
{
  std::size_t M = 0;
  double signal_std = 0.0;
  double noise_std = 0.0;
  double y_std_scale = 0.0;
  std::array<double, 5> lengthscales{1.0, 1.0, 1.0, 1.0, 1.0};
  std::vector<std::array<double, 5>> Z_m_std;
  std::vector<double> alpha_mu_phys;
  std::vector<double> L_m_inv;  // M x M row-major
  std::vector<double> L_B_inv;  // M x M row-major
};

struct GpPrediction
{
  std::array<double, 3> mean{0.0, 0.0, 0.0};
  std::array<double, 3> raw_mean{0.0, 0.0, 0.0};
  std::array<double, 3> std{0.0, 0.0, 0.0};
  std::array<double, 3> latent_std{0.0, 0.0, 0.0};
  double nearest_std_dist = 0.0;
  bool ood = false;
  bool clipped = false;
  bool fallback_zero = false;
};

class GpResidualModel
{
public:
  static GpResidualModel zero_fallback(const std::string & nominal_model_hash = "");

  static GpResidualModel from_json_string(
      const std::string & json_text,
      const std::string & expected_nominal_hash = "");

  static GpResidualModel from_json_file(
      const std::string & path,
      const std::string & expected_nominal_hash = "");

  GpPrediction predict(
      const std::array<double, 5> & z,
      bool apply_clip = true,
      bool ood_fallback_zero = true) const noexcept;

  bool is_zero_fallback() const noexcept { return zero_fallback_; }
  const std::string & snapshot_id() const noexcept { return snapshot_id_; }
  const std::string & snapshot_sha256() const noexcept { return snapshot_sha256_; }
  const std::string & file_sha256() const noexcept { return file_sha256_; }
  const std::string & nominal_model_hash() const noexcept { return nominal_model_hash_; }

  const std::array<double, 5> & x_mean() const noexcept { return x_mean_; }
  const std::array<double, 5> & x_std() const noexcept { return x_std_; }
  const std::array<std::array<double, 2>, 3> & clip_bounds() const noexcept { return clip_bounds_; }
  const std::array<GpChannelModel, 3> & channels() const noexcept { return channels_; }

private:
  bool zero_fallback_ = true;
  std::string snapshot_id_{"zero_fallback"};
  std::string snapshot_sha256_;
  std::string file_sha256_;
  std::string nominal_model_hash_;
  std::array<double, 5> x_mean_{0.0, 0.0, 0.0, 0.0, 0.0};
  std::array<double, 5> x_std_{1.0, 1.0, 1.0, 1.0, 1.0};
  std::array<double, 5> feature_min_{-1.0, -1.0, -1.0, -1.0, -1.0};
  std::array<double, 5> feature_max_{1.0, 1.0, 1.0, 1.0, 1.0};
  double ood_max_nearest_std_dist_ = 4.5;
  std::array<std::array<double, 2>, 3> clip_bounds_{
      std::array<double, 2>{-0.35, 0.35},
      std::array<double, 2>{-0.35, 0.35},
      std::array<double, 2>{-0.35, 0.35},
  };
  std::array<GpChannelModel, 3> channels_;
};

}  // namespace p1_gp
