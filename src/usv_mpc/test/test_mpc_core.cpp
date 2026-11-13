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
 * @brief MPC 纯逻辑层 gtest 单测 (运动学模型 sanity + utils)。
 *
 * 结构对齐方案 B 的 test_mpc_core.cpp:
 *   - Utils 4 个测试: 与 B 逐字相同 (utils 是同一份纯逻辑代码)
 *   - KinematicModel 4 个测试: 替换 B 的 FossenModel, 测 3 维运动学 ODE
 */

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <vector>

#include "usv_mpc/usv_model_kinematic.hpp"
#include "usv_mpc/utils.hpp"

using usv_mpc::USVKinematicModel;

// ===========================================================================
// Utils 测试 (与方案 B 逐字相同 — utils 是同一份纯逻辑代码)
// ===========================================================================

// 局部 map 与船体坐标系旋转语义
TEST(Utils, LocalMapBodyRotationSemantics) {
  auto [vx, vy] = usv_mpc::body_to_ned(1.0, 0.0, M_PI / 2.0);
  EXPECT_NEAR(vx, 0.0, 1e-9);
  EXPECT_NEAR(vy, 1.0, 1e-9);
  auto [u, v] = usv_mpc::ned_to_body(vx, vy, M_PI / 2.0);
  EXPECT_NEAR(u, 1.0, 1e-9);
  EXPECT_NEAR(v, 0.0, 1e-9);
}

// 四元数转 ROS yaw 与角度归一化
TEST(Utils, QuaternionToYawAndNormalize) {
  double yaw = M_PI / 2.0;
  EXPECT_NEAR(usv_mpc::quaternion_to_yaw(0.0, 0.0, std::sin(yaw / 2), std::cos(yaw / 2)),
              yaw, 1e-9);
  EXPECT_NEAR(usv_mpc::normalize_angle(3.0 * M_PI), M_PI, 1e-9);
}

// profile 时间戳解析与同步状态判定
TEST(Utils, ProfileStampParsingAndSyncState) {
  std::vector<std::string> labels = {"points", "v_kappa_r_t", "stamp_sec:12", "stamp_nanosec:34"};
  bool ok = false;
  auto stamp = usv_mpc::parse_profile_stamp(labels, ok);
  ASSERT_TRUE(ok);
  EXPECT_EQ(stamp.first, 12);
  EXPECT_EQ(stamp.second, 34);

  std::pair<int, int> ps{12, 34};
  auto r1 = usv_mpc::profile_sync_state(3, 3, &ps, &ps);
  EXPECT_TRUE(r1.first);
  EXPECT_EQ(r1.second, "stamp_match");

  std::pair<int, int> ps2{12, 35};
  auto r2 = usv_mpc::profile_sync_state(3, 3, &ps2, &ps);
  EXPECT_FALSE(r2.first);
  EXPECT_EQ(r2.second, "stamp_mismatch");

  auto r3 = usv_mpc::profile_sync_state(3, 2, &ps, &ps);
  EXPECT_FALSE(r3.first);
  EXPECT_EQ(r3.second, "length_mismatch");

  auto r4 = usv_mpc::profile_sync_state(3, 3, &ps, nullptr);
  EXPECT_TRUE(r4.first);
  EXPECT_EQ(r4.second, "legacy_no_profile_stamp");
}

// 按时间插值航向与参考速度
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

// ===========================================================================
// 运动学模型 sanity (替换 B 的 FossenModel 测试, 测 3 维 ODE)
// ===========================================================================

// 零控零速下所有导数应为 0 (运动学纯函数, 无阻尼项)
// 对照 B 的 ZeroControlZeroSpeedSteadyState (B 断言 6 维, A 断言 3 维)
TEST(KinematicModel, ZeroControlZeroSpeedSteadyState) {
  Eigen::Vector3d state;
  state << 0.0, 0.0, 0.0;
  Eigen::Vector2d control;
  control << 0.0, 0.0;
  auto rhs = USVKinematicModel::continuous_ode(state, control);
  // u=0 → dx=0*cos(ψ)=0, dy=0*sin(ψ)=0; r=0 → dψ=0
  for (int i = 0; i < 3; ++i) {
    EXPECT_NEAR(rhs(i), 0.0, 1e-9);
}
}

// ψ=0 时前向速度只产生 x 方向位移, 不改变航向
// 对照 B 的 ForwardThrustProducesSurgeAccel (B 测 u_dot>0 加速度, A 测 dx=u 速度)
TEST(KinematicModel, ForwardSurgeProducesPositionChange) {
  Eigen::Vector3d state;
  state << 0.0, 0.0, 0.0;  // ψ=0
  Eigen::Vector2d control;
  control << 1.0, 0.0;  // u=1, r=0
  auto rhs = USVKinematicModel::continuous_ode(state, control);
  // ψ=0: dx=u*cos(0)=1, dy=u*sin(0)=0, dψ=r=0
  EXPECT_NEAR(rhs(0), 1.0, 1e-9);  // x 方向前进
  EXPECT_NEAR(rhs(1), 0.0, 1e-9);  // y 不变
  EXPECT_NEAR(rhs(2), 0.0, 1e-9);  // 航向不变
}

// 纯艏摇角速度只改变航向, 不产生位移 (u=0)
// 对照 B 的 DifferentialThrustProducesYawAccel (B 测 r_dot≠0, A 测 dψ=r)
TEST(KinematicModel, YawRateProducesHeadingChange) {
  Eigen::Vector3d state;
  state << 0.0, 0.0, 0.0;
  Eigen::Vector2d control;
  control << 0.0, 0.5;  // u=0, r=0.5
  auto rhs = USVKinematicModel::continuous_ode(state, control);
  // u=0: dx=0, dy=0; r=0.5: dψ=0.5
  EXPECT_NEAR(rhs(0), 0.0, 1e-9);
  EXPECT_NEAR(rhs(1), 0.0, 1e-9);
  EXPECT_NEAR(rhs(2), 0.5, 1e-9);  // 航向变化率 = r
}

// RK4 forward: 时间步进后航向应归一化到 [-pi, pi] (与 B 逐字相同逻辑)
TEST(KinematicModel, ForwardNormalizesHeading) {
  USVKinematicModel model(0.2, 4);
  Eigen::Vector3d state;
  state << 0.0, 0.0, 3.5;  // psi=3.5 (>pi)
  Eigen::Vector2d control;
  control << 0.0, 0.0;
  auto next = model.forward(state, control);
  EXPECT_GE(next(2), -M_PI - 1e-9);
  EXPECT_LE(next(2), M_PI + 1e-9);
}


// 5 状态滞后模型测试: 一阶滞后动态逼近期望值
TEST(KinematicModel5D, FirstOrderActuatorLag) {
  USVKinematicModel model(0.2, 4);
  Eigen::Matrix<double, 5, 1> state;
  state << 0.0, 0.0, 0.0, 0.0, 0.0;
  Eigen::Vector2d control;
  control << 1.0, 0.5;  // u_cmd=1, r_cmd=0.5
  double tau_u = 0.8;
  double tau_r = 1.78;

  // continuous_ode 检查: du/dt = (1-0)/0.8 = 1.25, dr/dt = (0.5-0)/1.78
  auto rhs = USVKinematicModel::continuous_ode(state, control, tau_u, tau_r);
  EXPECT_NEAR(rhs(3), 1.25, 1e-6);
  EXPECT_NEAR(rhs(4), 0.5 / 1.78, 1e-6);

  // forward 步进一次 (dt=0.2): u 应该递增但小于 1.0
  auto next = model.forward(state, control, tau_u, tau_r);
  EXPECT_GT(next(3), 0.0);
  EXPECT_LT(next(3), 1.0);
  EXPECT_GT(next(4), 0.0);
  EXPECT_LT(next(4), 0.5);
}


// forward_unwrapped: 与 forward 的 x/y/u/r 逐位相同, psi 只差整数倍 2*pi。
// (acados 生成模型不做 atan2, audit 用 unwrapped 结果才不会被 ±2π 误判)
TEST(KinematicModel5D, ForwardUnwrappedKeepsHeadingContinuous) {
  USVKinematicModel model(0.2, 4);
  Eigen::Matrix<double, 5, 1> state;
  state << 0.0, 0.0, 3.5, 0.9, 0.1;
  const Eigen::Vector2d control(1.8, 0.6);
  const double tau_u = 0.8;
  const double tau_r = 1.78;

  const auto wrapped = model.forward(state, control, tau_u, tau_r);
  const auto unwrapped = model.forward_unwrapped(state, control, tau_u, tau_r);

  for (int row = 0; row < 5; ++row) {
    if (row == 2) {
      continue;
    }
    EXPECT_NEAR(unwrapped(row), wrapped(row), 1e-12) << "row " << row;
  }
  // psi 只差整数倍 2*pi
  const double delta_psi = unwrapped(2) - wrapped(2);
  EXPECT_NEAR(delta_psi / (2.0 * M_PI),
              std::round(delta_psi / (2.0 * M_PI)), 1e-12);
  EXPECT_GE(unwrapped(2), 3.5) << "unwrapped psi 不应被 atan2 折回";
}

// 同一组物理 ODE/四子步参考: unwrapped RK4 与解析四子步手算一致。
TEST(KinematicModel5D, ForwardUnwrappedMatchesSubstepReference) {
  USVKinematicModel model(0.2, 4);
  Eigen::Matrix<double, 5, 1> state;
  state << 1.0, -2.0, M_PI - 0.01, 0.7, 0.2;
  const Eigen::Vector2d control(1.2, -0.3);
  const double tau_u = 0.8;
  const double tau_r = 1.78;

  // 独立四子步 RK4 (与生成器 Python 参考同构)
  const double h = 0.2 / 4.0;
  Eigen::Matrix<double, 5, 1> x = state;
  auto rhs = [&](const Eigen::Matrix<double, 5, 1> & s) {
      Eigen::Matrix<double, 5, 1> d;
      d << s(3) * std::cos(s(2)), s(3) * std::sin(s(2)), s(4),
        (control(0) - s(3)) / tau_u, (control(1) - s(4)) / tau_r;
      return d;
    };
  for (int i = 0; i < 4; ++i) {
    const auto k1 = rhs(x);
    const auto k2 = rhs(x + 0.5 * h * k1);
    const auto k3 = rhs(x + 0.5 * h * k2);
    const auto k4 = rhs(x + h * k3);
    x = x + h / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4);
  }

  const auto stepped = model.forward_unwrapped(state, control, tau_u, tau_r);
  EXPECT_TRUE(stepped.isApprox(x, 1e-12)) << stepped.transpose() << " vs "
                                          << x.transpose();
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
