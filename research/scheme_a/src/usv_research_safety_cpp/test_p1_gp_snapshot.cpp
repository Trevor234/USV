// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>

#include <openssl/evp.h>
#include <nlohmann/json.hpp>

#include "p1_gp_snapshot.hpp"

namespace
{

class TestBinaryHasher
{
public:
  TestBinaryHasher() : ctx_(EVP_MD_CTX_new()) { EVP_DigestInit_ex(ctx_, EVP_sha256(), nullptr); }
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

std::string write_signed_snapshot_file(
    const std::string & path,
    const std::string & id,
    const std::string & nom_sha,
    double am0)
{
  const nlohmann::json zm = {{-0.5, 0.0, 0.0, -0.5, -0.5}, {0.5, 0.1, -0.1, 0.5, 0.5}};
  const nlohmann::json ls = {1.2, 1.5, 1.0, 2.0, 2.0};
  const nlohmann::json am = {am0, -0.01};
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
  const nlohmann::json fmin = {-0.5, -0.5, -0.5, -10.0, -10.0};
  const nlohmann::json fmax = {1.5, 0.5, 0.5, 20.0, 20.0};
  const nlohmann::json clips = {{-0.35, 0.35}, {-0.35, 0.35}, {-0.35, 0.35}};

  nlohmann::json body = {
      {"schema", p1_gp::kExpectedSnapshotSchema},
      {"snapshot_id", id},
      {"nominal_model_hash", nom_sha},
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
          {"feature_q01", fmin},
          {"feature_q99", fmax},
          {"ood_max_nearest_std_dist", 4.5},
      }},
      {"residual_clip_bounds", clips},
      {"channels", {ch, ch2, ch3}},
      {"offline_metrics", nlohmann::json::object()},
  };
  TestBinaryHasher h;
  h.str0(p1_gp::kExpectedSnapshotSchema);
  h.str0(id);
  h.str0(nom_sha);
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
  const std::string sha = h.finalize();
  body["snapshot_sha256"] = sha;
  std::ofstream ofs(path);
  ofs << body.dump();
  return sha;
}

usv_mpc::HydroParams contract_hydro()
{
  usv_mpc::HydroParams h;
  h.mass = 14.2;
  h.Iz = 2.13;
  h.xg = 0.12;
  h.d_thruster = 0.25;
  h.Xu_dot = -2.0;
  h.Yv_dot = -8.0;
  h.Yr_dot = -0.1817725;
  h.Nv_dot = -0.1817725;
  h.Nr_dot = -3.41;
  h.Xu = -2.272063;
  h.Yv = -2.629019;
  h.Yr = 0.0;
  h.Nv = 0.0;
  h.Nr = -3.105;
  h.Xuu = -11.571784;
  h.Yvv = -0.05;
  h.Yrr = 0.0;
  h.Nvv = 0.0;
  h.Nrr = -0.71;
  return h;
}

TEST(GpSnapshotTest, NominalHydroShaMatchesDatasetBuilder)
{
  const std::string sha = p1_gp_snap::canonical_nominal_hydro_sha256(contract_hydro(), 0.2, 4);
  EXPECT_EQ(sha, "d35a427ae62e643940e04d055e6a1e9f21dbb6d8dace0fe13cd5ffbf366da84c");
}

TEST(GpSnapshotTest, FiniteScheduleSwitchZeroGp1Gp2Zero)
{
  const std::string nom_sha = p1_gp_snap::canonical_nominal_hydro_sha256(contract_hydro(), 0.2, 4);
  const std::string gp1_path = "/tmp/test_p1_gp1.json";
  const std::string gp2_path = "/tmp/test_p1_gp2.json";
  const std::string sched_path = "/tmp/test_p1_gp_schedule.json";
  const std::string sha1 = write_signed_snapshot_file(gp1_path, "gp_1", nom_sha, 0.05);
  const std::string sha2 = write_signed_snapshot_file(gp2_path, "gp_2", nom_sha, -0.04);

  {
    std::ofstream ofs(sched_path);
    ofs << R"JSON({
      "schema": "scheme-a-gp-schedule-v1",
      "entries": [
        {"generation": 1, "first_target_tick": 1, "last_target_tick": 10, "kind": "zero"},
        {"generation": 2, "first_target_tick": 11, "last_target_tick": 20, "kind": "file", "path": ")JSON"
        << gp1_path << R"JSON(", "sha256": ")JSON" << sha1 << R"JSON("},
        {"generation": 3, "first_target_tick": 21, "last_target_tick": 30, "kind": "file", "path": ")JSON"
        << gp2_path << R"JSON(", "sha256": ")JSON" << sha2 << R"JSON("},
        {"generation": 4, "first_target_tick": 31, "last_target_tick": null, "kind": "zero"}
      ]
    })JSON";
  }

  const auto reg = p1_gp_snap::GpSnapshotRegistry::create_from_schedule_json(sched_path, "", nom_sha);
  EXPECT_EQ(reg.size(), 4u);

  const auto s1 = reg.resolve(5);
  ASSERT_TRUE(bool(s1));
  EXPECT_EQ(s1.generation, 1u);
  EXPECT_TRUE(s1.entry->is_zero);

  const auto s2 = reg.resolve(15);
  ASSERT_TRUE(bool(s2));
  EXPECT_EQ(s2.generation, 2u);
  EXPECT_EQ(s2.entry->model.snapshot_sha256(), sha1);

  const auto s3 = reg.resolve(25);
  ASSERT_TRUE(bool(s3));
  EXPECT_EQ(s3.generation, 3u);
  EXPECT_EQ(s3.entry->model.snapshot_sha256(), sha2);

  // Returning to zero yields sequential generation 4 (distinct from generation 1).
  const auto s4 = reg.resolve(35);
  ASSERT_TRUE(bool(s4));
  EXPECT_EQ(s4.generation, 4u);
  EXPECT_TRUE(s4.entry->is_zero);
  EXPECT_EQ(s4.entry->model.snapshot_sha256(), s1.entry->model.snapshot_sha256());

  Eigen::MatrixXd x(6, 21), u(2, 20);
  x.setZero();
  x.row(3).setConstant(0.6);
  u.setConstant(6.0);
  const auto eval_zero = p1_gp_snap::evaluate_gp_horizon(s1.entry->model, x, u);
  for (double v : eval_zero.residuals) EXPECT_DOUBLE_EQ(v, 0.0);

  const auto eval_gp = p1_gp_snap::evaluate_gp_horizon(s2.entry->model, x, u);
  EXPECT_GT(std::abs(eval_gp.residuals[0]), 1e-6);
  EXPECT_DOUBLE_EQ(eval_gp.residuals[60], 0.0);
  EXPECT_DOUBLE_EQ(eval_gp.residuals[61], 0.0);
  EXPECT_DOUBLE_EQ(eval_gp.residuals[62], 0.0);
  EXPECT_EQ(eval_gp.digest, p1_gp_snap::compute_stage_residuals_digest(eval_gp.residuals));
}

TEST(GpSnapshotTest, RejectsMismatchedNominalHashExpectedShaAndOverlap)
{
  const std::string nom_sha = p1_gp_snap::canonical_nominal_hydro_sha256(contract_hydro(), 0.2, 4);
  const std::string gp_path = "/tmp/test_p1_gp_bad.json";
  const std::string sha = write_signed_snapshot_file(gp_path, "gp_bad", nom_sha, 0.03);
  (void)sha;

  EXPECT_THROW(
      p1_gp_snap::GpSnapshotRegistry::create_single_file(gp_path, "", std::string(64, 'a')),
      std::runtime_error);
  EXPECT_THROW(
      p1_gp_snap::GpSnapshotRegistry::create_single_file(gp_path, std::string(64, 'b'), nom_sha),
      std::runtime_error);

  const std::string bad_sched = "/tmp/test_p1_gp_overlap.json";
  {
    std::ofstream ofs(bad_sched);
    ofs << R"JSON({
      "schema": "scheme-a-gp-schedule-v1",
      "entries": [
        {"generation": 1, "first_target_tick": 1, "last_target_tick": 12, "kind": "zero"},
        {"generation": 2, "first_target_tick": 10, "last_target_tick": null, "kind": "zero"}
      ]
    })JSON";
  }
  EXPECT_THROW(
      p1_gp_snap::GpSnapshotRegistry::create_from_schedule_json(bad_sched, "", nom_sha),
      std::runtime_error);
}

}  // namespace
