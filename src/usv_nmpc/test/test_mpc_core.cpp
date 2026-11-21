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
 * @brief MPC 纯逻辑层 gtest 单测 (utils + 动力学模型 sanity)。
 */

#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "usv_nmpc/usv_model_dynamic.hpp"
#include "usv_nmpc/utils.hpp"

using usv_mpc::Vector6d;
using usv_mpc::HydroParams;
using usv_mpc::USVDynamicModel;

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

// 死区跳过与二次标定反解自洽性测试
TEST(Utils, RcActuationDeadbandCompensationAndInverseConsistency) {
  usv_mpc::RcActuationConfig config;
  config.thrust_max = 30.0;
  config.thrust_min = -30.0;
  config.steering_gain = 0.75;
  config.throttle_gain = 1.0;
  config.deadband_compensation = true;
  config.use_quadratic_model = true;

  // 1) 微小正推力 (2.0 N > 0.5 N): throttle_pwm 必须越过 1500~1600 us 死区
  const auto micro_fwd = usv_mpc::thrust_to_rc_actuation(Eigen::Vector2d(2.0, 2.0), config);
  EXPECT_GE(micro_fwd.throttle_pwm, 1600);
  EXPECT_EQ(micro_fwd.steering_pwm, 1500);
  EXPECT_GT(micro_fwd.effective_thrust(0), 1.0);
  EXPECT_NEAR(micro_fwd.effective_thrust(0), micro_fwd.effective_thrust(1), 1e-9);

  // 2) 再将反算出的 effective_thrust 喂回前向映射, PWM 应与首次下发严格一致 (自洽无漂移)
  const auto recheck = usv_mpc::thrust_to_rc_actuation(
      micro_fwd.effective_thrust, config);
  EXPECT_EQ(recheck.throttle_pwm, micro_fwd.throttle_pwm);

  // 3) 极小抖动 (0.3 N <= 0.5 N) 回中 1500 us 防抖
  const auto jitter = usv_mpc::thrust_to_rc_actuation(Eigen::Vector2d(0.3, 0.3), config);
  EXPECT_EQ(jitter.throttle_pwm, 1500);
  EXPECT_EQ(jitter.steering_pwm, 1500);
  EXPECT_DOUBLE_EQ(jitter.effective_thrust(0), 0.0);

  // 4) 微小负推力 (-2.0 N): throttle_pwm 跳过反向死区 <= 1400 us
  const auto micro_rev = usv_mpc::thrust_to_rc_actuation(Eigen::Vector2d(-2.0, -2.0), config);
  EXPECT_LE(micro_rev.throttle_pwm, 1400);
  EXPECT_LT(micro_rev.effective_thrust(0), -1.0);

  // 5) 典型工况与边界定量核验 (throttle_gain=1.0, 1100~1900 us 安全区间)
  const auto t15 = usv_mpc::thrust_to_rc_actuation(Eigen::Vector2d(15.0, 15.0), config);
  EXPECT_EQ(t15.throttle_pwm, 1711);
  EXPECT_NEAR(t15.effective_thrust(0), 15.0, 0.15);

  const auto t30 = usv_mpc::thrust_to_rc_actuation(Eigen::Vector2d(30.0, 30.0), config);
  EXPECT_EQ(t30.throttle_pwm, 1812);
  EXPECT_LE(t30.throttle_pwm, 1900);
  EXPECT_NEAR(t30.effective_thrust(0), 30.0, 0.15);

  const auto t_rev30 = usv_mpc::thrust_to_rc_actuation(Eigen::Vector2d(-30.0, -30.0), config);
  EXPECT_EQ(t_rev30.throttle_pwm, 1188);
  EXPECT_GE(t_rev30.throttle_pwm, 1100);
  EXPECT_NEAR(t_rev30.effective_thrust(0), -30.0, 0.15);
}

// 复现 11.18 Episode #4 起点防终点倒吸 + U 型折返横漂不跨航段跳变
TEST(Utils, MonotonicProgressPreventsEndpointCollapse) {
  const std::vector<std::array<double, 2>> wps = {
    {127.66, -92.95}, {126.64, -76.43}, {136.63, -77.08},
    {144.07, -83.99}, {150.35, -94.49}
  };
  std::vector<std::array<double, 3>> ep4_path;
  for (size_t seg = 0; seg + 1 < wps.size(); ++seg) {
    const double dx = wps[seg + 1][0] - wps[seg][0];
    const double dy = wps[seg + 1][1] - wps[seg][1];
    const double len = std::hypot(dx, dy);
    const double psi = std::atan2(dy, dx);
    const int steps = std::max(1, static_cast<int>(std::round(len / 0.5)));
    for (int k = 0; k < steps; ++k) {
      const double t = static_cast<double>(k) / steps;
      ep4_path.push_back({wps[seg][0] + t * dx, wps[seg][1] + t * dy, psi});
    }
  }
  ep4_path.push_back({wps.back()[0], wps.back()[1], -1.0});
  ASSERT_GE(ep4_path.size(), 90u);

  usv_mpc::MonotonicProgressConfig cfg;
  cfg.is_initial = true;
  const auto res_ep4 = usv_mpc::select_monotonic_nearest_index(
      ep4_path, 153.0, -95.1, 0, cfg);
  EXPECT_LT(res_ep4.nearest_index, 15);
  EXPECT_LT(res_ep4.progress_index, 15);
  EXPECT_FALSE(usv_mpc::is_goal_reached(ep4_path, 153.0, -95.1, res_ep4.progress_index, 8, 2.0));

  std::vector<std::array<double, 3>> uturn_path;
  for (int i = 0; i <= 60; ++i) {
    uturn_path.push_back({0.5 * i, 0.0, 0.0});
  }
  for (int i = 1; i <= 18; ++i) {
    const double th = -M_PI / 2.0 + M_PI * i / 19.0;
    uturn_path.push_back({30.0 + 3.0 * std::cos(th), 3.0 + 3.0 * std::sin(th), th + M_PI / 2.0});
  }
  for (int i = 0; i <= 60; ++i) {
    uturn_path.push_back({30.0 - 0.5 * i, 6.0, M_PI});
  }

  usv_mpc::MonotonicProgressConfig track_cfg;
  track_cfg.is_initial = false;
  const auto res_uturn = usv_mpc::select_monotonic_nearest_index(
      uturn_path, 15.0, 3.5, 30, track_cfg);
  EXPECT_LE(res_uturn.nearest_index, 45);
  EXPECT_GE(res_uturn.progress_index, 30);
  EXPECT_LE(res_uturn.progress_index, 45);
}

// 大航向偏差起步前向推力辅助验证 (根治 Episode #3 原地反推打转)
TEST(Utils, LargeHeadingForwardAssistPreventsReverseSpin) {
  usv_mpc::LargeHeadingAssistConfig cfg;
  cfg.enabled = true;
  cfg.heading_threshold_rad = M_PI / 3.0;
  cfg.speed_threshold_mps = 0.3;
  cfg.min_net_thrust_n = 8.0;
  cfg.reverse_thrust_floor_n = -5.0;
  cfg.thrust_min = -30.0;
  cfg.thrust_max = 30.0;

  // 100° 航向误差且低速: (22, -25) 应被钳位至 (22, -5), 保持转向差动且净推力为正
  const auto assisted = usv_mpc::apply_large_heading_forward_assist(
      Eigen::Vector2d(22.0, -25.0), 1.75, 0.0, cfg);
  EXPECT_GE(assisted(0), -5.0);
  EXPECT_GE(assisted(1), -5.0);
  EXPECT_GE(assisted(0) + assisted(1), 8.0 - 1e-9);
  EXPECT_GT(assisted(0), assisted(1));

  // 小偏角或高速时不干预
  const Eigen::Vector2d raw(10.0, -15.0);
  EXPECT_TRUE(usv_mpc::apply_large_heading_forward_assist(raw, 0.2, 0.0, cfg).isApprox(raw));
  EXPECT_TRUE(usv_mpc::apply_large_heading_forward_assist(raw, 1.75, 0.8, cfg).isApprox(raw));
}

// profile 时间戳解析与同步状态判定
TEST(Utils, ProfileStampParsingAndSyncState) {
  std::vector<std::string> labels = {"points", "v_kappa_r_t", "stamp_sec:12", "stamp_nanosec:34"};
  bool ok = false;
  auto stamp = usv_mpc::parse_profile_stamp(labels, ok);
  ASSERT_TRUE(ok);
  EXPECT_EQ(stamp.first, 12);
  EXPECT_EQ(stamp.second, 34);

  std::pair<int,int> ps{12, 34};
  auto r1 = usv_mpc::profile_sync_state(3, 3, &ps, &ps);
  EXPECT_TRUE(r1.first); EXPECT_EQ(r1.second, "stamp_match");

  std::pair<int,int> ps2{12, 35};
  auto r2 = usv_mpc::profile_sync_state(3, 3, &ps2, &ps);
  EXPECT_FALSE(r2.first); EXPECT_EQ(r2.second, "stamp_mismatch");

  auto r3 = usv_mpc::profile_sync_state(3, 2, &ps, &ps);
  EXPECT_FALSE(r3.first); EXPECT_EQ(r3.second, "length_mismatch");

  auto r4 = usv_mpc::profile_sync_state(3, 3, &ps, nullptr);
  EXPECT_TRUE(r4.first); EXPECT_EQ(r4.second, "legacy_no_profile_stamp");
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

// Fossen 模型 sanity: 零控零速下状态应保持不变 (稳态)
TEST(FossenModel, ZeroControlZeroSpeedSteadyState) {
  HydroParams p;  // 默认真船参数
  Vector6d state; state << 0.0, 0.0, 0.0, 0.0, 0.0, 0.0;
  Eigen::Vector2d control; control << 0.0, 0.0;
  auto rhs = USVDynamicModel::continuous_ode(state, control, p);
  // 零速零控下所有导数应为 0 (eta_dot=J*0=0; nu_dot=M^-1*(0-0-0)=0)
  for (int i = 0; i < 6; ++i) EXPECT_NEAR(rhs(i), 0.0, 1e-9);
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

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
