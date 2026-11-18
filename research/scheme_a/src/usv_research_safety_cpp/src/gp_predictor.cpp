// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT

#include "gp_predictor.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>

#include <openssl/evp.h>
#include <nlohmann/json.hpp>

namespace p1_gp
{
namespace
{

constexpr std::size_t kInputDim = 5;
constexpr std::size_t kOutputDim = 3;
constexpr std::size_t kMaxInducing = 256;

std::string to_hex(const unsigned char * hash, unsigned int len)
{
  static constexpr char kHex[] = "0123456789abcdef";
  std::string out(len * 2, '0');
  for (unsigned int i = 0; i < len; ++i)
  {
    out[2 * i] = kHex[(hash[i] >> 4) & 0x0F];
    out[2 * i + 1] = kHex[hash[i] & 0x0F];
  }
  return out;
}

std::string sha256_hex(const std::string & data)
{
  EVP_MD_CTX * ctx = EVP_MD_CTX_new();
  if (!ctx) throw std::runtime_error("EVP_MD_CTX_new failed");
  unsigned char hash[EVP_MAX_MD_SIZE];
  unsigned int hash_len = 0;
  const bool ok =
      EVP_DigestInit_ex(ctx, EVP_sha256(), nullptr) == 1 &&
      EVP_DigestUpdate(ctx, data.data(), data.size()) == 1 &&
      EVP_DigestFinal_ex(ctx, hash, &hash_len) == 1;
  EVP_MD_CTX_free(ctx);
  if (!ok) throw std::runtime_error("EVP SHA256 digest failed");
  return to_hex(hash, hash_len);
}

class CanonicalBinaryHasher
{
public:
  CanonicalBinaryHasher() : ctx_(EVP_MD_CTX_new())
  {
    if (!ctx_ || EVP_DigestInit_ex(ctx_, EVP_sha256(), nullptr) != 1)
    {
      if (ctx_) EVP_MD_CTX_free(ctx_);
      throw std::runtime_error("EVP_MD_CTX init failed");
    }
  }
  ~CanonicalBinaryHasher()
  {
    if (ctx_) EVP_MD_CTX_free(ctx_);
  }

  void str0(const std::string & s)
  {
    if (!s.empty()) update(s.data(), s.size());
    const char nul = '\0';
    update(&nul, 1);
  }

  void u32(std::uint32_t v)
  {
    const unsigned char b[4] = {
        static_cast<unsigned char>(v & 0xFFu),
        static_cast<unsigned char>((v >> 8) & 0xFFu),
        static_cast<unsigned char>((v >> 16) & 0xFFu),
        static_cast<unsigned char>((v >> 24) & 0xFFu),
    };
    update(b, 4);
  }

  void f64(double val)
  {
    const double clean = (val == 0.0) ? 0.0 : val;
    std::uint64_t bits = 0;
    static_assert(sizeof(clean) == sizeof(bits));
    std::memcpy(&bits, &clean, 8);
    unsigned char b[8];
    for (int i = 0; i < 8; ++i)
    {
      b[i] = static_cast<unsigned char>((bits >> (8 * i)) & 0xFFu);
    }
    update(b, 8);
  }

  std::string finalize()
  {
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_len = 0;
    if (EVP_DigestFinal_ex(ctx_, hash, &hash_len) != 1)
    {
      throw std::runtime_error("EVP_DigestFinal_ex failed");
    }
    return to_hex(hash, hash_len);
  }

private:
  void update(const void * data, std::size_t n)
  {
    if (EVP_DigestUpdate(ctx_, data, n) != 1)
    {
      throw std::runtime_error("EVP_DigestUpdate failed");
    }
  }
  EVP_MD_CTX * ctx_{nullptr};
};

void ensure_finite(double v, const char * ctx)
{
  if (!std::isfinite(v))
  {
    throw std::runtime_error(std::string("non-finite GP field: ") + ctx);
  }
}

std::array<double, kInputDim> parse_vec5(const nlohmann::json & arr, const char * ctx)
{
  if (!arr.is_array() || arr.size() != kInputDim)
  {
    throw std::runtime_error(std::string("expected 5-element array: ") + ctx);
  }
  std::array<double, kInputDim> out{};
  for (std::size_t i = 0; i < kInputDim; ++i)
  {
    if (!arr[i].is_number()) throw std::runtime_error(std::string("non-numeric entry in ") + ctx);
    out[i] = arr[i].get<double>();
    ensure_finite(out[i], ctx);
  }
  return out;
}

}  // namespace

GpResidualModel GpResidualModel::zero_fallback(const std::string & nominal_model_hash)
{
  GpResidualModel m;
  m.zero_fallback_ = true;
  m.snapshot_id_ = "zero_fallback";
  m.nominal_model_hash_ = nominal_model_hash;
  m.snapshot_sha256_ = sha256_hex(std::string("gp-snapshot-zero-v1:") + nominal_model_hash);
  return m;
}

GpResidualModel GpResidualModel::from_json_file(
    const std::string & path,
    const std::string & expected_nominal_hash)
{
  std::ifstream ifs(path);
  if (!ifs)
  {
    throw std::runtime_error("cannot open GP snapshot file: " + path);
  }
  std::ostringstream oss;
  oss << ifs.rdbuf();
  return from_json_string(oss.str(), expected_nominal_hash);
}

GpResidualModel GpResidualModel::from_json_string(
    const std::string & json_text,
    const std::string & expected_nominal_hash)
{
  nlohmann::json doc = nlohmann::json::parse(json_text);
  if (!doc.is_object())
  {
    throw std::runtime_error("GP snapshot root must be a JSON object");
  }
  if (doc.value("schema", std::string()) != kExpectedSnapshotSchema)
  {
    throw std::runtime_error("unsupported GP snapshot schema");
  }
  if (doc.value("codegen_layout_version", std::string()) != kExpectedCodegenLayout)
  {
    throw std::runtime_error("GP snapshot codegen_layout_version mismatch");
  }
  if (doc.value("input_dim", 0) != static_cast<int>(kInputDim) ||
      doc.value("output_dim", 0) != static_cast<int>(kOutputDim))
  {
    throw std::runtime_error("GP snapshot input/output dims must be 5 and 3");
  }

  const std::string declared_sha = doc.at("snapshot_sha256").get<std::string>();
  if (declared_sha.size() != 64)
  {
    throw std::runtime_error("GP snapshot missing valid 64-hex snapshot_sha256");
  }
  const int rk4_substeps = doc.value("rk4_substeps", 4);
  const double dt_s = doc.value("dt_s", 0.2);
  ensure_finite(dt_s, "dt_s");

  GpResidualModel model;
  model.zero_fallback_ = false;
  model.snapshot_id_ = doc.at("snapshot_id").get<std::string>();
  model.snapshot_sha256_ = declared_sha;
  model.file_sha256_ = sha256_hex(json_text);
  model.nominal_model_hash_ = doc.at("nominal_model_hash").get<std::string>();
  if (!expected_nominal_hash.empty() && model.nominal_model_hash_ != expected_nominal_hash)
  {
    throw std::runtime_error("GP snapshot nominal_model_hash mismatch");
  }

  model.x_mean_ = parse_vec5(doc.at("x_mean"), "x_mean");
  model.x_std_ = parse_vec5(doc.at("x_std"), "x_std");
  for (std::size_t d = 0; d < kInputDim; ++d)
  {
    if (model.x_std_[d] <= 0.0) throw std::runtime_error("GP x_std must be > 0");
  }

  const auto & env = doc.at("envelope");
  model.feature_min_ = parse_vec5(env.at("feature_min"), "feature_min");
  model.feature_max_ = parse_vec5(env.at("feature_max"), "feature_max");
  model.ood_max_nearest_std_dist_ = env.at("ood_max_nearest_std_dist").get<double>();
  ensure_finite(model.ood_max_nearest_std_dist_, "ood_max_nearest_std_dist");
  if (model.ood_max_nearest_std_dist_ <= 0.0)
  {
    throw std::runtime_error("ood_max_nearest_std_dist must be > 0");
  }

  const auto & clips = doc.at("residual_clip_bounds");
  if (!clips.is_array() || clips.size() != kOutputDim)
  {
    throw std::runtime_error("residual_clip_bounds must have 3 entries");
  }
  for (std::size_t c = 0; c < kOutputDim; ++c)
  {
    const double lo = clips[c].at(0).get<double>();
    const double hi = clips[c].at(1).get<double>();
    ensure_finite(lo, "clip_lo");
    ensure_finite(hi, "clip_hi");
    if (lo >= hi) throw std::runtime_error("invalid residual_clip_bounds lo >= hi");
    model.clip_bounds_[c] = {lo, hi};
  }

  const auto & chs = doc.at("channels");
  if (!chs.is_array() || chs.size() != kOutputDim)
  {
    throw std::runtime_error("GP channels must have 3 entries");
  }
  for (std::size_t c = 0; c < kOutputDim; ++c)
  {
    const auto & jc = chs[c];
    GpChannelModel ch;
    ch.M = jc.at("M").get<std::size_t>();
    if (ch.M == 0 || ch.M > kMaxInducing)
    {
      throw std::runtime_error("GP channel M out of bounds [1, 256]");
    }
    ch.signal_std = jc.at("signal_std").get<double>();
    ch.noise_std = jc.at("noise_std").get<double>();
    ch.y_std_scale = jc.at("y_std_scale").get<double>();
    ensure_finite(ch.signal_std, "signal_std");
    ensure_finite(ch.noise_std, "noise_std");
    ensure_finite(ch.y_std_scale, "y_std_scale");
    if (ch.signal_std < 0.0 || ch.noise_std < 0.0 || ch.y_std_scale < 0.0)
    {
      throw std::runtime_error("GP scales must be >= 0");
    }
    ch.lengthscales = parse_vec5(jc.at("lengthscales"), "lengthscales");
    for (double l : ch.lengthscales)
    {
      if (l <= 0.0) throw std::runtime_error("GP lengthscale must be > 0");
    }

    const auto & zm = jc.at("Z_m_std");
    const auto & am = jc.at("alpha_mu_phys");
    const auto & lm = jc.at("L_m_inv");
    const auto & lb = jc.at("L_B_inv");
    if (!zm.is_array() || zm.size() != ch.M ||
        !am.is_array() || am.size() != ch.M ||
        !lm.is_array() || lm.size() != ch.M ||
        !lb.is_array() || lb.size() != ch.M)
    {
      throw std::runtime_error("GP channel array dimension mismatch vs M");
    }
    ch.Z_m_std.resize(ch.M);
    ch.alpha_mu_phys.resize(ch.M);
    ch.L_m_inv.assign(ch.M * ch.M, 0.0);
    ch.L_B_inv.assign(ch.M * ch.M, 0.0);
    for (std::size_t m = 0; m < ch.M; ++m)
    {
      ch.Z_m_std[m] = parse_vec5(zm[m], "Z_m_std");
      ch.alpha_mu_phys[m] = am[m].get<double>();
      ensure_finite(ch.alpha_mu_phys[m], "alpha_mu_phys");
      if (!lm[m].is_array() || lm[m].size() != ch.M ||
          !lb[m].is_array() || lb[m].size() != ch.M)
      {
        throw std::runtime_error("GP Cholesky matrix row mismatch vs M");
      }
      for (std::size_t col = 0; col < ch.M; ++col)
      {
        const double v_m = lm[m][col].get<double>();
        const double v_b = lb[m][col].get<double>();
        ensure_finite(v_m, "L_m_inv");
        ensure_finite(v_b, "L_B_inv");
        ch.L_m_inv[m * ch.M + col] = v_m;
        ch.L_B_inv[m * ch.M + col] = v_b;
      }
    }
    model.channels_[c] = std::move(ch);
  }

  CanonicalBinaryHasher h;
  h.str0(kExpectedSnapshotSchema);
  h.str0(model.snapshot_id_);
  h.str0(model.nominal_model_hash_);
  h.str0(kExpectedCodegenLayout);
  h.u32(static_cast<std::uint32_t>(kInputDim));
  h.u32(static_cast<std::uint32_t>(kOutputDim));
  h.u32(static_cast<std::uint32_t>(rk4_substeps));
  h.f64(dt_s);
  for (double v : model.x_mean_) h.f64(v);
  for (double v : model.x_std_) h.f64(v);
  for (double v : model.feature_min_) h.f64(v);
  for (double v : model.feature_max_) h.f64(v);
  h.f64(model.ood_max_nearest_std_dist_);
  for (const auto & b : model.clip_bounds_)
  {
    h.f64(b[0]);
    h.f64(b[1]);
  }
  for (const auto & ch : model.channels_)
  {
    h.u32(static_cast<std::uint32_t>(ch.M));
    h.f64(ch.signal_std);
    h.f64(ch.noise_std);
    h.f64(ch.y_std_scale);
    for (double v : ch.lengthscales) h.f64(v);
    for (const auto & pt : ch.Z_m_std)
      for (double v : pt) h.f64(v);
    for (double v : ch.alpha_mu_phys) h.f64(v);
    for (double v : ch.L_m_inv) h.f64(v);
    for (double v : ch.L_B_inv) h.f64(v);
  }
  const std::string recomputed_sha = h.finalize();
  if (recomputed_sha != declared_sha)
  {
    throw std::runtime_error("GP snapshot canonical sha256 mismatch: declared=" +
                             declared_sha + " computed=" + recomputed_sha);
  }
  return model;
}

GpPrediction GpResidualModel::predict(
    const std::array<double, 5> & z,
    bool apply_clip,
    bool ood_fallback_zero) const noexcept
{
  GpPrediction out;
  if (zero_fallback_)
  {
    out.fallback_zero = true;
    return out;
  }

  for (double val : z)
  {
    if (!std::isfinite(val))
    {
      out.ood = true;
      out.fallback_zero = ood_fallback_zero;
      out.nearest_std_dist = std::numeric_limits<double>::infinity();
      return out;
    }
  }

  bool box_ood = false;
  std::array<double, kInputDim> z_std{};
  for (std::size_t d = 0; d < kInputDim; ++d)
  {
    const double margin = 0.25 * (feature_max_[d] - feature_min_[d]);
    if (z[d] < (feature_min_[d] - margin) || z[d] > (feature_max_[d] + margin))
    {
      box_ood = true;
    }
    z_std[d] = (z[d] - x_mean_[d]) / x_std_[d];
  }

  double min_std_dist = std::numeric_limits<double>::infinity();
  std::vector<double> k_star;
  std::vector<double> v_vec;
  for (std::size_t c = 0; c < kOutputDim; ++c)
  {
    const auto & ch = channels_[c];
    if (ch.y_std_scale <= 1e-11)
    {
      out.raw_mean[c] = 0.0;
      out.mean[c] = 0.0;
      out.latent_std[c] = 1e-12;
      out.std[c] = 1e-12;
      for (std::size_t m = 0; m < ch.M; ++m)
      {
        double d2 = 0.0;
        for (std::size_t d = 0; d < kInputDim; ++d)
        {
          const double dz = z_std[d] - ch.Z_m_std[m][d];
          d2 += dz * dz;
        }
        min_std_dist = std::min(min_std_dist, std::sqrt(d2));
      }
      continue;
    }

    const std::size_t M = ch.M;
    k_star.resize(M);
    v_vec.resize(M);
    const double sf2 = ch.signal_std * ch.signal_std;
    double mu_c = 0.0;

    for (std::size_t m = 0; m < M; ++m)
    {
      double ard_d2 = 0.0;
      double std_d2 = 0.0;
      for (std::size_t d = 0; d < kInputDim; ++d)
      {
        const double dz = z_std[d] - ch.Z_m_std[m][d];
        std_d2 += dz * dz;
        const double l = std::max(ch.lengthscales[d], 1e-6);
        ard_d2 += (dz * dz) / (l * l);
      }
      min_std_dist = std::min(min_std_dist, std::sqrt(std_d2));
      const double kv = sf2 * std::exp(-0.5 * ard_d2);
      k_star[m] = kv;
      mu_c += kv * ch.alpha_mu_phys[m];
    }

    double norm_v2 = 0.0;
    for (std::size_t i = 0; i < M; ++i)
    {
      double sum = 0.0;
      const double * row = &ch.L_m_inv[i * M];
      for (std::size_t j = 0; j < M; ++j)
      {
        sum += row[j] * k_star[j];
      }
      v_vec[i] = sum;
      norm_v2 += sum * sum;
    }

    double norm_w2 = 0.0;
    for (std::size_t i = 0; i < M; ++i)
    {
      double sum = 0.0;
      const double * row = &ch.L_B_inv[i * M];
      for (std::size_t j = 0; j < M; ++j)
      {
        sum += row[j] * v_vec[j];
      }
      norm_w2 += sum * sum;
    }

    const double var_lat_std = std::max(0.0, sf2 - norm_v2 + norm_w2);
    const double var_tot_std = var_lat_std + ch.noise_std * ch.noise_std;
    out.raw_mean[c] = mu_c;
    out.mean[c] = mu_c;
    out.latent_std[c] = ch.y_std_scale * std::sqrt(var_lat_std);
    out.std[c] = ch.y_std_scale * std::sqrt(var_tot_std);
  }

  out.nearest_std_dist = min_std_dist;
  out.ood = box_ood || (min_std_dist > ood_max_nearest_std_dist_);

  if (apply_clip)
  {
    for (std::size_t c = 0; c < kOutputDim; ++c)
    {
      const double lo = clip_bounds_[c][0];
      const double hi = clip_bounds_[c][1];
      if (out.mean[c] < lo || out.mean[c] > hi)
      {
        out.clipped = true;
        out.mean[c] = std::clamp(out.mean[c], lo, hi);
      }
    }
  }

  if (out.ood && ood_fallback_zero)
  {
    out.mean = {0.0, 0.0, 0.0};
    out.fallback_zero = true;
  }

  return out;
}

}  // namespace p1_gp
