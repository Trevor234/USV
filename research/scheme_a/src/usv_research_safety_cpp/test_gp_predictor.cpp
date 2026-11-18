// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT

#include <gtest/gtest.h>

#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>

#include <openssl/evp.h>
#include <nlohmann/json.hpp>
#include "gp_predictor.hpp"

namespace
{

class TestBinaryHasher
{
public:
  TestBinaryHasher() : ctx_(EVP_MD_CTX_new())
  {
    EVP_DigestInit_ex(ctx_, EVP_sha256(), nullptr);
  }
  ~TestBinaryHasher() { EVP_MD_CTX_free(ctx_); }

  void str0(const std::string & s)
  {
    if (!s.empty()) EVP_DigestUpdate(ctx_, s.data(), s.size());
    const char nul = '\0';
    EVP_DigestUpdate(ctx_, &nul, 1);
  }
  void u32(std::uint32_t v)
  {
    const unsigned char b[4] = {
        static_cast<unsigned char>(v & 0xFFu),
        static_cast<unsigned char>((v >> 8) & 0xFFu),
        static_cast<unsigned char>((v >> 16) & 0xFFu),
        static_cast<unsigned char>((v >> 24) & 0xFFu),
    };
    EVP_DigestUpdate(ctx_, b, 4);
  }
  void f64(double val)
  {
    const double clean = (val == 0.0) ? 0.0 : val;
    std::uint64_t bits = 0;
    std::memcpy(&bits, &clean, 8);
    unsigned char b[8];
    for (int i = 0; i < 8; ++i) b[i] = static_cast<unsigned char>((bits >> (8 * i)) & 0xFFu);
    EVP_DigestUpdate(ctx_, b, 8);
  }
  std::string finalize()
  {
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_len = 0;
    EVP_DigestFinal_ex(ctx_, hash, &hash_len);
    static constexpr char kHex[] = "0123456789abcdef";
    std::string out(hash_len * 2, '0');
    for (unsigned int i = 0; i < hash_len; ++i)
    {
      out[2 * i] = kHex[(hash[i] >> 4) & 0x0F];
      out[2 * i + 1] = kHex[hash[i] & 0x0F];
    }
    return out;
  }

private:
  EVP_MD_CTX * ctx_{nullptr};
};

std::string make_signed_snapshot_json(const std::string & id_override = "unit_test_gp")
{
  const nlohmann::json zm = {{-0.5, 0.0, 0.0, -0.5, -0.5}, {0.5, 0.1, -0.1, 0.5, 0.5}};
  const nlohmann::json ls = {1.2, 1.5, 1.0, 2.0, 2.0};
  const nlohmann::json am = {0.02, -0.015};
  const nlohmann::json lm = {{2.0, 0.0}, {-0.5, 2.1}};
  const nlohmann::json lb = {{0.8, 0.0}, {-0.2, 0.85}};
  nlohmann::json ch = {
      {"output_name", "delta_u_residual"},
      {"output_unit", "m/s"},
      {"M", 2},
      {"signal_std", 0.5},
      {"lengthscales", ls},
      {"noise_std", 0.05},
      {"y_std_scale", 0.04},
      {"elbo", 10.0},
      {"Z_m_std", zm},
      {"alpha_mu_phys", am},
      {"L_m_inv", lm},
      {"L_B_inv", lb},
  };
  nlohmann::json ch2 = ch;
  ch2["output_name"] = "delta_v_residual";
  nlohmann::json ch3 = ch;
  ch3["output_name"] = "delta_r_residual";
  ch3["output_unit"] = "rad/s";

  const nlohmann::json xm = {0.6, 0.0, 0.0, 6.0, 6.0};
  const nlohmann::json xs = {0.25, 0.1, 0.1, 3.0, 3.0};
  const nlohmann::json fmin = {0.0, -0.4, -0.4, -5.0, -5.0};
  const nlohmann::json fmax = {1.2, 0.4, 0.4, 18.0, 18.0};
  const nlohmann::json clips = {{-0.35, 0.35}, {-0.35, 0.35}, {-0.35, 0.35}};

  nlohmann::json body = {
      {"schema", p1_gp::kExpectedSnapshotSchema},
      {"snapshot_id", id_override},
      {"nominal_model_hash", "nom_hash_1"},
      {"codegen_layout_version", p1_gp::kExpectedCodegenLayout},
      {"dt_s", 0.2},
      {"rk4_substeps", 4},
      {"input_dim", 5},
      {"output_dim", 3},
      {"feature_names", {"u", "v", "r", "T_L_executed", "T_R_executed"}},
      {"feature_units", {"m/s", "m/s", "rad/s", "N", "N"}},
      {"output_names", {"delta_u_residual", "delta_v_residual", "delta_r_residual"}},
      {"output_units", {"m/s", "m/s", "rad/s"}},
      {"inducing_points_count", {2, 2, 2}},
      {"x_mean", xm},
      {"x_std", xs},
      {"envelope", {
          {"feature_min", fmin},
          {"feature_max", fmax},
          {"feature_q01", {0.05, -0.35, -0.35, -3.0, -3.0}},
          {"feature_q99", {1.1, 0.35, 0.35, 16.0, 16.0}},
          {"ood_max_nearest_std_dist", 4.5},
      }},
      {"residual_clip_bounds", clips},
      {"channels", {ch, ch2, ch3}},
      {"offline_metrics", nlohmann::json::object()},
  };
  TestBinaryHasher h;
  h.str0(p1_gp::kExpectedSnapshotSchema);
  h.str0(id_override);
  h.str0("nom_hash_1");
  h.str0(p1_gp::kExpectedCodegenLayout);
  h.u32(5);
  h.u32(3);
  h.u32(4);
  h.f64(0.2);
  for (const auto & v : xm) h.f64(v.get<double>());
  for (const auto & v : xs) h.f64(v.get<double>());
  for (const auto & v : fmin) h.f64(v.get<double>());
  for (const auto & v : fmax) h.f64(v.get<double>());
  h.f64(4.5);
  for (const auto & row : clips)
  {
    h.f64(row[0].get<double>());
    h.f64(row[1].get<double>());
  }
  for (int c = 0; c < 3; ++c)
  {
    h.u32(2);
    h.f64(0.5);
    h.f64(0.05);
    h.f64(0.04);
    for (const auto & v : ls) h.f64(v.get<double>());
    for (const auto & pt : zm)
      for (const auto & v : pt) h.f64(v.get<double>());
    for (const auto & v : am) h.f64(v.get<double>());
    for (const auto & r : lm)
      for (const auto & v : r) h.f64(v.get<double>());
    for (const auto & r : lb)
      for (const auto & v : r) h.f64(v.get<double>());
  }
  body["snapshot_sha256"] = h.finalize();
  return body.dump();
}

}  // namespace

TEST(GpPredictor, ParsesValidSnapshotPredictsAndEnforcesOodClip)
{
  const auto model = p1_gp::GpResidualModel::from_json_string(
      make_signed_snapshot_json(), "nom_hash_1");
  EXPECT_FALSE(model.is_zero_fallback());

  const auto p_in = model.predict({0.6, 0.0, 0.0, 6.0, 6.0});
  EXPECT_FALSE(p_in.ood);
  EXPECT_FALSE(p_in.fallback_zero);
  for (int c = 0; c < 3; ++c)
  {
    EXPECT_TRUE(std::isfinite(p_in.mean[c]));
    EXPECT_GT(p_in.std[c], 0.0);
  }

  // Far out-of-distribution input must set ood=true and zero-fallback mean.
  const auto p_ood = model.predict({5.0, 2.0, 2.0, 40.0, -40.0});
  EXPECT_TRUE(p_ood.ood);
  EXPECT_TRUE(p_ood.fallback_zero);
  EXPECT_DOUBLE_EQ(p_ood.mean[0], 0.0);
  EXPECT_DOUBLE_EQ(p_ood.mean[1], 0.0);
  EXPECT_DOUBLE_EQ(p_ood.mean[2], 0.0);
}

TEST(GpPredictor, RejectsTamperedDigestAndMismatchedNominalHash)
{
  const auto valid_str = make_signed_snapshot_json();
  EXPECT_THROW(
      p1_gp::GpResidualModel::from_json_string(valid_str, "wrong_nominal_hash"),
      std::runtime_error);

  auto doc = nlohmann::json::parse(valid_str);
  doc["snapshot_id"] = "tampered_id";
  EXPECT_THROW(
      p1_gp::GpResidualModel::from_json_string(doc.dump()),
      std::runtime_error);
}
