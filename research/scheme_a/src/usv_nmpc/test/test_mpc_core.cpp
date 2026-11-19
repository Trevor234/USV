// Copyright 2026 USV Developer
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
// THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.

/**
 * @file test_mpc_core.cpp
 * @brief MPC 纯逻辑层 gtest 单测 (对拍 Python test_utils_and_sync.py + model sanity)。
 */

#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "usv_nmpc/usv_model_dynamic.hpp"
#include "usv_nmpc/utils.hpp"

using usv_mpc::Vector6d;
using usv_mpc::HydroParams;
using usv_mpc::USVDynamicModel;

// 对应 Python: test_local_map_body_rotation_semantics
TEST(Utils, LocalMapBodyRotationSemantics) {
  auto [vx, vy] = usv_mpc::body_to_ned(1.0, 0.0, M_PI / 2.0);
  EXPECT_NEAR(vx, 0.0, 1e-9);
  EXPECT_NEAR(vy, 1.0, 1e-9);
  auto [u, v] = usv_mpc::ned_to_body(vx, vy, M_PI / 2.0);
  EXPECT_NEAR(u, 1.0, 1e-9);
  EXPECT_NEAR(v, 0.0, 1e-9);
}

// 对应 Python: test_quaternion_to_yaw_ros_semantics
TEST(Utils, QuaternionToYawAndNormalize) {
  double yaw = M_PI / 2.0;
  EXPECT_NEAR(usv_mpc::quaternion_to_yaw(0.0, 0.0, std::sin(yaw / 2), std::cos(yaw / 2)),
              yaw, 1e-9);
  EXPECT_NEAR(usv_mpc::normalize_angle(3.0 * M_PI), M_PI, 1e-9);
}

TEST(Utils, RcActuationReportsEquivalentAppliedThrust) {
  const usv_mpc::RcActuationConfig config;

  Eigen::Vector2d surge_command;
  surge_command << 20.0, 20.0;
  const auto surge = usv_mpc::thrust_to_rc_actuation(surge_command, config);
  EXPECT_EQ(surge.steering_pwm, 1500);
  EXPECT_EQ(surge.throttle_pwm, 1740);
  EXPECT_NEAR(surge.effective_thrust(0), 15.0, 1e-9);
  EXPECT_NEAR(surge.effective_thrust(1), 15.0, 1e-9);

  Eigen::Vector2d yaw_command;
  yaw_command << -20.0, 20.0;
  const auto yaw = usv_mpc::thrust_to_rc_actuation(yaw_command, config);
  EXPECT_EQ(yaw.steering_pwm, 1372);
  EXPECT_EQ(yaw.throttle_pwm, 1500);
  EXPECT_NEAR(yaw.effective_thrust(0), -8.0, 1e-9);
  EXPECT_NEAR(yaw.effective_thrust(1), 8.0, 1e-9);
}

// 对应 Python: test_profile_stamp_parsing_and_sync_state
TEST(Utils, ProfileStampParsingAndSyncState) {
  std::vector<std::string> labels = {"points", "v_kappa_r_t", "stamp_sec:12", "stamp_nanosec:34"};
  bool ok = false;
  auto stamp = usv_mpc::parse_profile_stamp(labels, ok);
  ASSERT_TRUE(ok);
  EXPECT_EQ(stamp.first, 12);
  EXPECT_EQ(stamp.second, 34);

  std::pair<int, int> ps{12, 34};
  auto r1 = usv_mpc::profile_sync_state(3, 3, &ps, &ps);
  EXPECT_TRUE(r1.first); EXPECT_EQ(r1.second, "stamp_match");

  std::pair<int, int> ps2{12, 35};
  auto r2 = usv_mpc::profile_sync_state(3, 3, &ps2, &ps);
  EXPECT_FALSE(r2.first); EXPECT_EQ(r2.second, "stamp_mismatch");

  auto r3 = usv_mpc::profile_sync_state(3, 2, &ps, &ps);
  EXPECT_FALSE(r3.first); EXPECT_EQ(r3.second, "length_mismatch");

  auto r4 = usv_mpc::profile_sync_state(3, 3, &ps, nullptr);
  EXPECT_TRUE(r4.first); EXPECT_EQ(r4.second, "legacy_no_profile_stamp");
}

// 对应 Python: test_sample_at_time_interpolates_heading_and_speed
TEST(Utils, SampleAtTimeInterpolation) {
  std::vector<std::array<double, 3>> path = {{0, 0, 0}, {10, 0, M_PI / 2.0}};
  std::vector<double> times = {0.0, 10.0};
  std::vector<double> vs = {1.0, 3.0};
  std::vector<double> rs = {0.0, 0.2};
  auto s = usv_mpc::sample_path_profile_at_time(path, times, vs, rs, 5.0, 0);
  EXPECT_NEAR(s.x, 5.0, 1e-9);
  EXPECT_NEAR(s.y, 0.0, 1e-9);
  EXPECT_NEAR(s.psi, M_PI / 4.0, 1e-9);
  EXPECT_NEAR(s.v, 2.0, 1e-9);
  EXPECT_NEAR(s.r, 0.1, 1e-9);
  EXPECT_EQ(s.j, 0);
}

// Fossen 模型 sanity: 零控零速下状态应保持不变 (稳态)
TEST(FossenModel, ZeroControlZeroSpeedSteadyState) {
  HydroParams p;  // 默认真船参数
  Vector6d state; state << 0.0, 0.0, 0.0, 0.0, 0.0, 0.0;
  Eigen::Vector2d control; control << 0.0, 0.0;
  auto rhs = USVDynamicModel::continuous_ode(state, control, p);
  // 零速零控下所有导数应为 0 (eta_dot=J*0=0; nu_dot=M^-1*(0-0-0)=0)
  for (int i = 0; i < 6; ++i) {
    EXPECT_NEAR(rhs(i), 0.0, 1e-9);
}
}

// Fossen 模型: 纯前向推力应产生正纵向加速度 (u_dot > 0)
TEST(FossenModel, ForwardThrustProducesSurgeAccel) {
  HydroParams p;
  Vector6d state; state << 0.0, 0.0, 0.0, 0.0, 0.0, 0.0;
  Eigen::Vector2d control; control << 10.0, 10.0;  // 等推力 → 纯前向
  auto rhs = USVDynamicModel::continuous_ode(state, control, p);
  // tau = [TL+TR, 0, d*(TR-TL)] = [20, 0, 0]; u_dot = rhs(3) > 0
  EXPECT_GT(rhs(3), 0.0);
  // 等推力无偏航力矩 → r_dot = rhs(5) 应为 0
  EXPECT_NEAR(rhs(5), 0.0, 1e-9);
}

// Fossen 模型: 差动推力应产生偏航加速度 (r_dot != 0)
TEST(FossenModel, DifferentialThrustProducesYawAccel) {
  HydroParams p;
  Vector6d state; state << 0.0, 0.0, 0.0, 0.0, 0.0, 0.0;
  Eigen::Vector2d control; control << 10.0, -10.0;  // 差动 → 偏航
  auto rhs = USVDynamicModel::continuous_ode(state, control, p);
  // tau_z = d*(TR-TL) = 0.25*(-20) = -5 != 0 → r_dot != 0
  EXPECT_NE(rhs(5), 0.0);
}

// RK4 forward: 时间步进后航向应归一化到 [-pi, pi]
TEST(FossenModel, ForwardNormalizesHeading) {
  HydroParams p;
  USVDynamicModel model(0.2, 4, p);
  Vector6d state; state << 0.0, 0.0, 3.5, 0.0, 0.0, 0.0;  // psi=3.5 (>pi)
  Eigen::Vector2d control; control << 0.0, 0.0;
  auto next = model.forward(state, control);
  EXPECT_GE(next(2), -M_PI - 1e-9);
  EXPECT_LE(next(2), M_PI + 1e-9);
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
