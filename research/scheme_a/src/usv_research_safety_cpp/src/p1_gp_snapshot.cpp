// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT

#include "p1_gp_snapshot.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <regex>
#include <sstream>
#include <stdexcept>

#include <openssl/evp.h>
#include <nlohmann/json.hpp>

namespace p1_gp_snap
{
namespace
{

std::string sha256_bytes(const void * data, std::size_t size)
{
  EVP_MD_CTX * ctx = EVP_MD_CTX_new();
  if (!ctx) throw std::runtime_error("EVP_MD_CTX_new failed");
  unsigned char hash[EVP_MAX_MD_SIZE];
  unsigned int hash_len = 0;
  const bool ok =
      EVP_DigestInit_ex(ctx, EVP_sha256(), nullptr) == 1 &&
      EVP_DigestUpdate(ctx, data, size) == 1 &&
      EVP_DigestFinal_ex(ctx, hash, &hash_len) == 1;
  EVP_MD_CTX_free(ctx);
  if (!ok) throw std::runtime_error("EVP SHA256 digest failed");

  static constexpr char kHex[] = "0123456789abcdef";
  std::string out(hash_len * 2, '0');
  for (unsigned int i = 0; i < hash_len; ++i)
  {
    out[2 * i] = kHex[(hash[i] >> 4) & 0x0F];
    out[2 * i + 1] = kHex[hash[i] & 0x0F];
  }
  return out;
}

std::string read_file_bytes(const std::string & path)
{
  std::ifstream ifs(path, std::ios::binary);
  if (!ifs) throw std::runtime_error("cannot read file: " + path);
  std::ostringstream oss;
  oss << ifs.rdbuf();
  return oss.str();
}

void verify_hex64_if_present(
    const std::string & actual_sha,
    const std::string & expected_sha,
    const std::string & label)
{
  if (expected_sha.empty()) return;
  if (!std::regex_match(expected_sha, std::regex("[0-9a-f]{64}")))
  {
    throw std::runtime_error(label + ": expected sha256 must be 64 lowercase hex chars");
  }
  if (actual_sha != expected_sha)
  {
    throw std::runtime_error(
        label + ": sha256 mismatch expected=" + expected_sha + " actual=" + actual_sha);
  }
}

bool ranges_overlap(
    std::uint64_t a_first,
    std::uint64_t a_last,
    std::uint64_t b_first,
    std::uint64_t b_last) noexcept
{
  const bool a_open = (a_last == 0);
  const bool b_open = (b_last == 0);
  if (!a_open && a_last < b_first) return false;
  if (!b_open && b_last < a_first) return false;
  return true;
}

double wrap_angle(double a) noexcept
{
  while (a > M_PI) a -= 2.0 * M_PI;
  while (a < -M_PI) a += 2.0 * M_PI;
  return a;
}

}  // namespace

std::string canonical_nominal_hydro_sha256(
    const usv_mpc::HydroParams & hydro,
    double dt_s,
    int rk4_substeps)
{
  nlohmann::json h = {
      {"mass", hydro.mass},
      {"Iz", hydro.Iz},
      {"xg", hydro.xg},
      {"d_thruster", hydro.d_thruster},
      {"Xu_dot", hydro.Xu_dot},
      {"Yv_dot", hydro.Yv_dot},
      {"Yr_dot", hydro.Yr_dot},
      {"Nv_dot", hydro.Nv_dot},
      {"Nr_dot", hydro.Nr_dot},
      {"Xu", hydro.Xu},
      {"Yv", hydro.Yv},
      {"Yr", hydro.Yr},
      {"Nv", hydro.Nv},
      {"Nr", hydro.Nr},
      {"Xuu", hydro.Xuu},
      {"Yvv", hydro.Yvv},
      {"Yrr", hydro.Yrr},
      {"Nvv", hydro.Nvv},
      {"Nrr", hydro.Nrr},
  };
  nlohmann::json payload = {
      {"dt_s", dt_s},
      {"hydro", h},
      {"rk4_substeps", rk4_substeps},
  };
  const std::string raw = payload.dump();
  return sha256_bytes(raw.data(), raw.size());
}

std::string compute_stage_residuals_digest(const std::array<double, kStageResidualFloats> & flat)
{
  unsigned char buf[kStageResidualFloats * 8];
  for (std::size_t idx = 0; idx < kStageResidualFloats; ++idx)
  {
    const double clean = (flat[idx] == 0.0) ? 0.0 : flat[idx];
    std::uint64_t bits = 0;
    std::memcpy(&bits, &clean, 8);
    for (int b = 0; b < 8; ++b)
    {
      buf[idx * 8 + b] = static_cast<unsigned char>((bits >> (8 * b)) & 0xFFu);
    }
  }
  return sha256_bytes(buf, sizeof(buf));
}

void GpSnapshotRegistry::add_entry(GpScheduleEntry entry)
{
  if (count_ >= kMaxGpEntries)
  {
    throw std::runtime_error("GP schedule exceeds bounded capacity (8)");
  }
  if (entry.generation == 0)
  {
    throw std::runtime_error("GP generation must be >= 1");
  }
  if (entry.first_target_tick == 0)
  {
    throw std::runtime_error("GP first_target_tick must be >= 1");
  }
  if (entry.last_target_tick != 0 && entry.last_target_tick < entry.first_target_tick)
  {
    throw std::runtime_error("GP last_target_tick < first_target_tick");
  }
  for (std::size_t i = 0; i < count_; ++i)
  {
    if (entries_[i].generation == entry.generation)
    {
      throw std::runtime_error("duplicate GP generation in schedule");
    }
    if (ranges_overlap(
            entry.first_target_tick, entry.last_target_tick,
            entries_[i].first_target_tick, entries_[i].last_target_tick))
    {
      throw std::runtime_error("overlapping GP schedule tick range");
    }
  }
  entries_[count_++] = std::move(entry);
}

GpSnapshotRegistry GpSnapshotRegistry::create_zero_only(const std::string & nominal_hydro_hash)
{
  GpSnapshotRegistry reg;
  reg.nominal_hydro_hash_ = nominal_hydro_hash;
  GpScheduleEntry entry;
  entry.generation = 1;
  entry.first_target_tick = 1;
  entry.last_target_tick = 0;
  entry.is_zero = true;
  entry.model = p1_gp::GpResidualModel::zero_fallback(nominal_hydro_hash);
  reg.add_entry(std::move(entry));
  return reg;
}

GpSnapshotRegistry GpSnapshotRegistry::create_single_file(
    const std::string & path,
    const std::string & expected_sha256,
    const std::string & nominal_hydro_hash)
{
  const std::string raw = read_file_bytes(path);
  auto model = p1_gp::GpResidualModel::from_json_string(raw, nominal_hydro_hash);
  // Check either canonical snapshot_sha256 OR raw file bytes SHA-256 against expected_sha256.
  if (!expected_sha256.empty())
  {
    if (!std::regex_match(expected_sha256, std::regex("[0-9a-f]{64}")))
    {
      throw std::runtime_error("gp_snapshot_sha256 must be 64 lowercase hex chars");
    }
    const std::string file_sha = sha256_bytes(raw.data(), raw.size());
    if (model.snapshot_sha256() != expected_sha256 && file_sha != expected_sha256)
    {
      throw std::runtime_error(
          "GP snapshot sha256 mismatch expected=" + expected_sha256 +
          " model=" + model.snapshot_sha256() + " file=" + file_sha);
    }
  }
  GpSnapshotRegistry reg;
  reg.nominal_hydro_hash_ = nominal_hydro_hash;
  GpScheduleEntry entry;
  entry.generation = 1;
  entry.first_target_tick = 1;
  entry.last_target_tick = 0;
  entry.is_zero = false;
  entry.file_path = path;
  entry.model = std::move(model);
  reg.add_entry(std::move(entry));
  return reg;
}

GpSnapshotRegistry GpSnapshotRegistry::create_from_schedule_json(
    const std::string & schedule_path,
    const std::string & expected_schedule_sha256,
    const std::string & nominal_hydro_hash)
{
  const std::string sched_text = read_file_bytes(schedule_path);
  verify_hex64_if_present(
      sha256_bytes(sched_text.data(), sched_text.size()),
      expected_schedule_sha256,
      "gp_schedule");
  const auto doc = nlohmann::json::parse(sched_text);
  if (!doc.is_object() || doc.value("schema", std::string()) != "scheme-a-gp-schedule-v1")
  {
    throw std::runtime_error("gp_schedule must have schema scheme-a-gp-schedule-v1");
  }
  const auto & items = doc.at("entries");
  if (!items.is_array() || items.empty() || items.size() > kMaxGpEntries)
  {
    throw std::runtime_error("gp_schedule entries must be 1..8 items");
  }

  GpSnapshotRegistry reg;
  reg.nominal_hydro_hash_ = nominal_hydro_hash;
  for (const auto & item : items)
  {
    GpScheduleEntry entry;
    entry.generation = item.at("generation").get<std::uint64_t>();
    entry.first_target_tick = item.at("first_target_tick").get<std::uint64_t>();
    if (item.at("last_target_tick").is_null())
    {
      entry.last_target_tick = 0;
    }
    else
    {
      entry.last_target_tick = item.at("last_target_tick").get<std::uint64_t>();
      if (entry.last_target_tick == 0)
      {
        throw std::runtime_error("gp_schedule numeric last_target_tick must be >= 1 or null");
      }
    }
    const std::string kind = item.at("kind").get<std::string>();
    if (kind == "zero")
    {
      entry.is_zero = true;
      entry.model = p1_gp::GpResidualModel::zero_fallback(nominal_hydro_hash);
    }
    else if (kind == "file")
    {
      entry.is_zero = false;
      entry.file_path = item.at("path").get<std::string>();
      const std::string expected = item.value("sha256", std::string());
      const std::string raw = read_file_bytes(entry.file_path);
      entry.model = p1_gp::GpResidualModel::from_json_string(raw, nominal_hydro_hash);
      if (!expected.empty())
      {
        const std::string file_sha = sha256_bytes(raw.data(), raw.size());
        if (entry.model.snapshot_sha256() != expected && file_sha != expected)
        {
          throw std::runtime_error("gp_schedule entry sha256 mismatch for " + entry.file_path);
        }
      }
    }
    else
    {
      throw std::runtime_error("unsupported gp_schedule entry kind: " + kind);
    }
    reg.add_entry(std::move(entry));
  }
  return reg;
}

GpSnapshotRegistry GpSnapshotRegistry::initialize_from_params(
    const std::string & snapshot_file,
    const std::string & snapshot_sha256,
    const std::string & schedule_file,
    const std::string & schedule_sha256,
    const std::string & nominal_hydro_hash)
{
  if (!schedule_file.empty() && !snapshot_file.empty())
  {
    throw std::runtime_error("specify at most one of gp_snapshot_file or gp_schedule_file");
  }
  if (!schedule_file.empty())
  {
    return create_from_schedule_json(schedule_file, schedule_sha256, nominal_hydro_hash);
  }
  if (!snapshot_file.empty())
  {
    return create_single_file(snapshot_file, snapshot_sha256, nominal_hydro_hash);
  }
  return create_zero_only(nominal_hydro_hash);
}

GpSelection GpSnapshotRegistry::resolve(std::uint64_t target_tick) const noexcept
{
  GpSelection sel;
  if (target_tick == 0)
  {
    sel.reason = "target_tick_zero";
    return sel;
  }
  for (std::size_t i = 0; i < count_; ++i)
  {
    const auto & e = entries_[i];
    const bool in_range =
        (e.last_target_tick == 0)
            ? (target_tick >= e.first_target_tick)
            : (target_tick >= e.first_target_tick && target_tick <= e.last_target_tick);
    if (in_range)
    {
      sel.valid = true;
      sel.generation = e.generation;
      sel.entry = &e;
      return sel;
    }
  }
  sel.reason = "target_tick_outside_gp_schedule";
  return sel;
}

const GpScheduleEntry * GpSnapshotRegistry::find(std::uint64_t generation) const noexcept
{
  if (generation == 0) return nullptr;
  for (std::size_t i = 0; i < count_; ++i)
  {
    if (entries_[i].generation == generation) return &entries_[i];
  }
  return nullptr;
}

StageResidualEvalResult evaluate_gp_horizon(
    const p1_gp::GpResidualModel & model,
    const Eigen::MatrixXd & traj_x,
    const Eigen::MatrixXd & traj_u,
    bool ood_fallback_zero)
{
  StageResidualEvalResult out;
  out.residuals.fill(0.0);
  if (traj_x.rows() != 6 || traj_x.cols() != kHorizonSteps + 1 ||
      traj_u.rows() != 2 || traj_u.cols() != kHorizonSteps)
  {
    throw std::invalid_argument("evaluate_gp_horizon trajectory shape must be 6x21 and 2x20");
  }
  if (!model.is_zero_fallback())
  {
    for (int k = 0; k < kHorizonSteps; ++k)
    {
      const std::array<double, 5> z{
          traj_x(3, k), traj_x(4, k), traj_x(5, k), traj_u(0, k), traj_u(1, k)};
      const auto pred = model.predict(z, /*apply_clip=*/true, ood_fallback_zero);
      for (int c = 0; c < kResidualDims; ++c)
      {
        out.residuals[static_cast<std::size_t>(3 * k + c)] = pred.mean[static_cast<std::size_t>(c)];
      }
      if (pred.ood)
      {
        out.ood_detected = true;
        out.ood_stage_count += 1;
      }
    }
  }
  // Explicitly clear terminal slot k=20 (never consumed by dynamics).
  out.residuals[60] = 0.0;
  out.residuals[61] = 0.0;
  out.residuals[62] = 0.0;
  out.digest = compute_stage_residuals_digest(out.residuals);
  return out;
}

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
    Eigen::MatrixXd & out_u)
{
  out_x.resize(6, kHorizonSteps + 1);
  out_u.resize(2, kHorizonSteps);

  if (model.is_zero_fallback())
  {
    out_x.setZero();
    out_x.col(0) = x0;
    out_u.setZero();
    return;
  }

  bool use_shifted_u = false;
  if (prev_x != nullptr && prev_u != nullptr &&
      prev_x->rows() == 6 && prev_x->cols() == kHorizonSteps + 1 &&
      prev_u->rows() == 2 && prev_u->cols() == kHorizonSteps &&
      tick_shift >= 1 && tick_shift <= 4)
  {
    const double pos_diff = (x0.head<2>() - prev_x->block<2, 1>(0, tick_shift)).norm();
    const double yaw_diff = std::abs(wrap_angle(x0(2) - (*prev_x)(2, tick_shift)));
    use_shifted_u = (pos_diff < 0.75 && yaw_diff < 0.5);
  }

  const double dT_step = dt_max * dt;
  usv_mpc::USVDynamicModel dyn(dt, 4, hydro);
  usv_mpc::Vector6d x = x0;
  Eigen::Vector2d u_prev = anchor;
  out_x.col(0) = x;

  for (int k = 0; k < kHorizonSteps; ++k)
  {
    Eigen::Vector2d u_cand;
    if (use_shifted_u)
    {
      const int src_k = std::min(k + tick_shift, kHorizonSteps - 1);
      u_cand = prev_u->col(src_k);
    }
    else
    {
      // Lightweight stabilizing heuristic rollout for cold start when warm plan is unavailable.
      const double u_ref = (ref.rows() >= 4) ? ref(3, k) : 0.6;
      const double r_ref = (ref.rows() >= 6) ? ref(5, k) : 0.0;
      const double psi_err = wrap_angle(ref(2, k) - x(2));
      const double f_cmd = std::clamp(12.0 * (u_ref - x(3)) + 6.0 * u_ref, -40.0, 40.0);
      const double tau_cmd = std::clamp(2.5 * psi_err + 1.2 * (r_ref - x(5)), -12.0, 12.0);
      u_cand(0) = 0.5 * (f_cmd - tau_cmd / std::max(hydro.d_thruster, 0.05));
      u_cand(1) = 0.5 * (f_cmd + tau_cmd / std::max(hydro.d_thruster, 0.05));
    }
    for (int ch = 0; ch < 2; ++ch)
    {
      u_cand(ch) = std::clamp(u_cand(ch), u_prev(ch) - dT_step, u_prev(ch) + dT_step);
      u_cand(ch) = std::clamp(u_cand(ch), t_min, t_max);
    }
    out_u.col(k) = u_cand;
    usv_mpc::Vector6d x_next = dyn.forward(x, u_cand);
    const auto pred = model.predict({x(3), x(4), x(5), u_cand(0), u_cand(1)}, true, ood_fallback_zero);
    x_next(3) += pred.mean[0];
    x_next(4) += pred.mean[1];
    x_next(5) += pred.mean[2];
    x = x_next;
    out_x.col(k + 1) = x;
    u_prev = u_cand;
  }
}

}  // namespace p1_gp_snap
