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
 * @brief MPC 纯逻辑层 gtest 单测 (运动学模型 sanity + utils, 对拍 Python)。
 *
 * 结构对齐方案 B 的 test_mpc_core.cpp:
 *   - Utils 4 个测试: 与 B 逐字相同 (utils 是同一份纯逻辑代码)
 *   - KinematicModel 4 个测试: 替换 B 的 FossenModel, 测 3 维运动学 ODE
 */

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <vector>

#include "usv_mpc_cpp/usv_model_kinematic.hpp"
#include "usv_mpc_cpp/kinematic_mpc_solver.hpp"
#include "usv_mpc_cpp/utils.hpp"

using usv_mpc::USVKinematicModel;

// ===========================================================================
// Utils 测试 (与方案 B 逐字相同 — utils 是同一份纯逻辑代码)
// ===========================================================================

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
  for (int i = 0; i < 3; ++i) EXPECT_NEAR(rhs(i), 0.0, 1e-9);
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

#ifdef USV_MPC_HAS_CASADI
#include <Eigen/Dense>
#include <cstring>

// ABI 跨界回归测试: 测试单元(new ABI)调用 old-ABI 编译的 CasADi 后端,
// SolveInfo 以 POD(定长 char 数组)按值跨界 — 验证求解与字符串字段完好。
// (casadi pip wheel 为旧 ABI; 此测试仅在探针通过、后端编入时编译。)
TEST(KinematicCasadiBackend, SolveCrossesAbiBoundary) {
  usv_mpc::KinematicMpcParams p;
  p.N   = 5;
  p.dt  = 0.2;
  p.tau_u = 0.8;
  p.tau_r = 1.78;
  auto mpc = usv_mpc::make_kinematic_mpc(p);
  ASSERT_NE(mpc, nullptr);
  EXPECT_STREQ(mpc->backend(), "casadi");

  Eigen::Matrix<double, 5, 1> x0;
  x0 << 0.0, 0.0, 0.0, 0.0, 0.0;
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(3, p.N + 1);
  for (int k = 0; k <= p.N; ++k) ref(0, k) = 0.1 * k;  // 缓慢直线参考

  for (int tick = 0; tick < 3; ++tick) {  // 多拍: 覆盖 warm start 路径
    auto [u, info] = mpc->solve(x0, ref);
    EXPECT_TRUE(info.success) << "tick " << tick;
    EXPECT_STREQ(info.backend, "casadi");
    EXPECT_STREQ(info.error, "");
    EXPECT_LE(info.initial_state_residual, p.solution_constraint_tol);
    EXPECT_LE(info.max_dynamics_residual, p.solution_constraint_tol);
    EXPECT_LE(info.max_control_bound_violation, p.solution_constraint_tol);
    EXPECT_LE(info.max_control_rate_violation, p.solution_constraint_tol);
    x0(0) += u(0) * p.dt;
    x0(3) = u(0);
    x0(4) = u(1);
  }
}

// set_applied_command 写回的锚点必须约束首步控制: U(0,0) ∈ anchor ± du_step。
// (修复前 u_prev_ 与实际下发值脱节, 此测试无法满足 — 真回归覆盖。)
TEST(KinematicCasadiBackend, AppliedCommandAnchorsRateConstraint) {
  usv_mpc::KinematicMpcParams p;
  p.N  = 5;
  p.dt = 0.2;
  auto mpc = usv_mpc::make_kinematic_mpc(p);
  ASSERT_NE(mpc, nullptr);

  Eigen::Matrix<double, 5, 1> x0;
  x0 << 0.0, 0.0, 0.0, 0.0, 0.0;
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(3, p.N + 1);
  for (int k = 0; k <= p.N; ++k) ref(0, k) = 0.1 * k;

  const double du_step = p.du_max * p.dt;  // 0.8 * 0.2 = 0.16
  const double eps = 5e-3;                 // 收敛约束违反容差余量

  // 锚点 1.5 (界内): 首步指令必须落在 [1.5-du_step, 1.5+du_step]
  mpc->set_applied_command(Eigen::Vector2d(1.5, 0.0));
  {
    auto [u, info] = mpc->solve(x0, ref);
    ASSERT_TRUE(info.success) << info.error;
    (void)u;
    EXPECT_GE(info.U_pred(0, 0), 1.5 - du_step - eps);
    EXPECT_LE(info.U_pred(0, 0), 1.5 + du_step + eps);
  }

  // 锚点 99 (超界): 须 clamp 到 u_max=2.0, 否则首步速率约束 ∩ [u_min,u_max]
  // 为空集 → NLP 不可行。clamp 后窗口 [u_max-du_step, u_max]。
  mpc->set_applied_command(Eigen::Vector2d(99.0, 0.0));
  {
    auto [u, info] = mpc->solve(x0, ref);
    ASSERT_TRUE(info.success) << info.error;
    (void)u;
    EXPECT_GE(info.U_pred(0, 0), 2.0 - du_step - eps);
    EXPECT_LE(info.U_pred(0, 0), 2.0 + eps);
  }
}

// reset_warmstart 清空锚点: 重置后首步指令回到 0 ± du_step
// (u_min=0 时即 [0, du_step]) — 对应 STANDBY/HOLD 后重新激活的场景。
TEST(KinematicCasadiBackend, ResetClearsRateAnchor) {
  usv_mpc::KinematicMpcParams p;
  p.N  = 5;
  p.dt = 0.2;
  auto mpc = usv_mpc::make_kinematic_mpc(p);
  ASSERT_NE(mpc, nullptr);

  Eigen::Matrix<double, 5, 1> x0;
  x0 << 0.0, 0.0, 0.0, 0.0, 0.0;
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(3, p.N + 1);
  for (int k = 0; k <= p.N; ++k) ref(0, k) = 0.1 * k;

  const double du_step = p.du_max * p.dt;
  const double eps = 5e-3;

  mpc->set_applied_command(Eigen::Vector2d(1.5, 0.0));
  {
    auto [u, info] = mpc->solve(x0, ref);
    ASSERT_TRUE(info.success) << info.error;
    (void)u;
  }
  mpc->reset_warmstart();
  {
    auto [u, info] = mpc->solve(x0, ref);
    ASSERT_TRUE(info.success) << info.error;
    (void)u;
    EXPECT_GE(info.U_pred(0, 0), -eps);
    EXPECT_LE(info.U_pred(0, 0), du_step + eps);
  }
}

// IPOPT 早停回收: max_iter=1 强制早停。迭代点即使全部有限，只要违反
// 初值、动力学、控制边界或变化率约束，就必须拒绝并返回实际控制锚点。
TEST(KinematicCasadiBackend, InfeasibleEarlyStopIsRejected) {
  usv_mpc::KinematicMpcParams p;
  p.N  = 5;
  p.dt = 0.2;
  p.ipopt_max_iter = 1;  // 1 次迭代不可能满足 tol/acceptable(5) → 必早停
  auto mpc = usv_mpc::make_kinematic_mpc(p);
  ASSERT_NE(mpc, nullptr);

  Eigen::Matrix<double, 5, 1> x0;
  x0 << 0.0, 0.0, 0.0, 1.5, 0.0;
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(3, p.N + 1);
  for (int k = 0; k <= p.N; ++k) ref(0, k) = 0.3 * k;
  const Eigen::Vector2d applied(1.5, 0.0);
  mpc->set_applied_command(applied);

  auto [u, info] = mpc->solve(x0, ref);
  EXPECT_FALSE(info.success);
  EXPECT_EQ(std::strncmp(info.error, "ipopt_early_stop_infeasible", 27), 0)
      << info.error;
  EXPECT_TRUE(u.isApprox(applied));
  EXPECT_EQ(info.X_pred.size(), 0);
  EXPECT_EQ(info.U_pred.size(), 0);
  EXPECT_GT(std::max({info.initial_state_residual,
                      info.max_dynamics_residual,
                      info.max_control_bound_violation,
                      info.max_control_rate_violation}),
            p.solution_constraint_tol);
}
#endif

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
