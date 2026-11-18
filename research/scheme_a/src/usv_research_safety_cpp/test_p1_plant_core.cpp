// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// plant 物理内核：无命令也推进、hold 半开区间、四子步与整 tick 位级一致、
// 网格对齐只发生在首步。全部 ROS-free、无墙钟、无 DDS。
#include <gtest/gtest.h>

#include <cmath>
#include <cstdio>
#include <fstream>
#include <stdexcept>

#include "plant/p1_plant_core.hpp"
#include "plant/p1_plant_model_loader.hpp"

namespace {

usv_mpc::HydroParams hydro()
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

p1_plant::Vector6d moving_state()
{
  p1_plant::Vector6d x = p1_plant::Vector6d::Zero();
  x[3] = 1.0;  // u = 1 m/s
  return x;
}

}  // namespace

// 四个 50 ms 子步必须与一次 200 ms 积分在数值上一致（1e-12）。
TEST(PlantCore, FourSubstepsEqualOneTickIntegration)
{
  p1_plant::PlantCore core(hydro());
  const std::array<double, 2> thrust{6.0, -3.0};
  const auto one_shot = core.forward_tick(moving_state(), thrust);

  auto stepped = moving_state();
  for (int i = 0; i < 4; ++i) ASSERT_TRUE(core.step_once(stepped, thrust));

  for (int i = 0; i < 6; ++i)
    EXPECT_NEAR(stepped[i], one_shot[i], 1e-12) << "component " << i;
}

// 无命令也必须连续推进动力学：状态不等于冻结。
TEST(PlantCore, ZeroThrustStillAdvancesPhysics)
{
  p1_plant::PlantCore core(hydro());
  auto state = moving_state();
  const double before = state[0];
  for (int i = 0; i < 4; ++i) ASSERT_TRUE(core.step_once(state, {0.0, 0.0}));
  EXPECT_GT(state[0], before);
  EXPECT_GT(state[3], 0.0);  // 有阻力但仍有速度
}

// hold 是半开区间：未覆盖与右端点都是零推力。
TEST(HoldWindow, HalfOpenIntervalZeroOutside)
{
  p1_plant::HoldWindow hold;
  hold.active = true;
  hold.begin_ns = 1000;
  hold.end_ns = 1000 + p1_plant::kTickNs;
  hold.thrust = {8.0, 12.0};

  EXPECT_TRUE(hold.covers(hold.begin_ns));
  EXPECT_TRUE(hold.covers(hold.end_ns - 1));
  EXPECT_FALSE(hold.covers(hold.end_ns));         // 右端点开
  EXPECT_FALSE(hold.covers(hold.begin_ns - 1));   // 左端点外
  EXPECT_DOUBLE_EQ(p1_plant::held_thrust(hold, hold.end_ns)[0], 0.0);
  EXPECT_DOUBLE_EQ(p1_plant::held_thrust(hold, hold.begin_ns)[0], 8.0);
  EXPECT_TRUE(hold.expired_at(hold.end_ns));
  EXPECT_FALSE(hold.expired_at(hold.end_ns - 1));
}

// 未被任何命令覆盖的时间段一律零推力，而不是"保持上一个值"。
TEST(HoldWindow, UncoveredTimeIsZeroNotLastValue)
{
  p1_plant::HoldWindow hold;
  EXPECT_DOUBLE_EQ(p1_plant::held_thrust(hold, 0)[1], 0.0);
  hold.active = true;
  hold.begin_ns = 1000;
  hold.end_ns = 1000 + p1_plant::kTickNs;
  hold.thrust = {5.0, 5.0};
  EXPECT_DOUBLE_EQ(p1_plant::held_thrust(hold, hold.end_ns + 1)[1], 0.0);
}

// 网格对齐：整点不动，非整点向上取整；next_boundary 严格向前。
TEST(SimClock, AlignUpOnlyMovesForwardToGridBoundary)
{
  p1_plant::SimClock clock;
  clock.steady_origin_ns = 5000;
  EXPECT_EQ(clock.align_up(0), 0);
  EXPECT_EQ(clock.align_up(p1_plant::kTickNs), p1_plant::kTickNs);
  EXPECT_EQ(clock.align_up(1), p1_plant::kTickNs);
  EXPECT_EQ(clock.align_up(p1_plant::kTickNs + 1), 2 * p1_plant::kTickNs);

  clock.sim_ns = 0;
  EXPECT_EQ(clock.next_boundary(), p1_plant::kTickNs);
  clock.sim_ns = p1_plant::kTickNs;
  EXPECT_EQ(clock.next_boundary(), 2 * p1_plant::kTickNs);

  EXPECT_EQ(clock.steady_of(1234), 5000 + 1234);
  EXPECT_EQ(clock.sim_of(6234), 1234);
}

// 零散推进共享同一网格：连续 12 次 50 ms 恰好等于 3 个 tick。
TEST(SimClock, SubstepsStayOnOneGrid)
{
  p1_plant::SimClock clock;
  clock.steady_origin_ns = 0;
  for (int i = 0; i < 12; ++i) clock.sim_ns += p1_plant::kSubstepNs;
  EXPECT_EQ(clock.sim_ns, 3 * p1_plant::kTickNs);
  EXPECT_EQ(clock.sim_ns % p1_plant::kTickNs, 0);
}

// 追赶超限必须重新对齐原点，但不得回退或跳子步。
TEST(SimClock, CatchUpResyncKeepsSimMonotone)
{
  p1_plant::SimClock clock;
  clock.steady_origin_ns = 1000;
  clock.sim_ns = 400000000;
  const std::int64_t now = clock.steady_of(clock.sim_ns) + 3'000'000'000LL;
  EXPECT_TRUE(clock.catch_up_exceeded(now, 2'000'000'000LL));
  const std::int64_t before_sim = clock.sim_ns;
  clock.resync(now);
  EXPECT_EQ(clock.sim_ns, before_sim);
  EXPECT_EQ(clock.steady_of(clock.sim_ns), now);
}

// 非有限输入必须被拒绝，而不是把 NaN 推进状态。
TEST(PlantCore, RejectsNonFiniteInput)
{
  p1_plant::PlantCore core(hydro());
  auto state = moving_state();
  EXPECT_FALSE(core.step_once(state, {std::nan(""), 0.0}));
  auto bad = moving_state();
  bad[3] = std::nan("");
  EXPECT_FALSE(core.step_once(bad, {0.0, 0.0}));
}

TEST(PlantModelLoader, ValidatesSPDAndPhysicalBounds)
{
  const auto nom = hydro();
  EXPECT_NO_THROW(p1_plant::validate_hydro_params(nom, "nominal"));

  auto bad_spd = nom;
  bad_spd.Yv_dot = 20.0;  // m22 = 14.2 - 20 < 0
  EXPECT_THROW(p1_plant::validate_hydro_params(bad_spd, "bad_spd"), std::runtime_error);

  auto bad_det = nom;
  bad_det.Yr_dot = -15.0;  // induces off-diagonal blowup making det_sym <= 0
  bad_det.Nv_dot = -15.0;
  EXPECT_THROW(p1_plant::validate_hydro_params(bad_det, "bad_det"), std::runtime_error);

  auto bad_damp = nom;
  bad_damp.Xu = 0.5;  // positive linear damping breaks passivity
  EXPECT_THROW(p1_plant::validate_hydro_params(bad_damp, "bad_damp"), std::runtime_error);

  auto bad_nan = nom;
  bad_nan.mass = std::nan("");
  EXPECT_THROW(p1_plant::validate_hydro_params(bad_nan, "bad_nan"), std::runtime_error);
}

TEST(PlantModelLoader, LoadsOverrideFileAndRejectsInvalidFile)
{
  const std::string ok_path = "/tmp/test_p1_plant_model_ok.json";
  {
    std::ofstream ofs(ok_path);
    ofs << R"({"plant_actual":{"mass":15.62,"Xu":-2.61287245}})";
  }
  const auto loaded = p1_plant::load_plant_hydro(hydro(), ok_path);
  EXPECT_TRUE(loaded.overridden);
  EXPECT_DOUBLE_EQ(loaded.controller_nominal.mass, 14.2);
  EXPECT_DOUBLE_EQ(loaded.plant_actual.mass, 15.62);
  EXPECT_DOUBLE_EQ(loaded.plant_actual.Xu, -2.61287245);
  std::remove(ok_path.c_str());

  const std::string bad_path = "/tmp/test_p1_plant_model_bad.json";
  {
    std::ofstream ofs(bad_path);
    ofs << R"({"plant_actual":{"mass":-5.0}})";
  }
  EXPECT_THROW(p1_plant::load_plant_hydro(hydro(), bad_path), std::runtime_error);
  std::remove(bad_path.c_str());
}
