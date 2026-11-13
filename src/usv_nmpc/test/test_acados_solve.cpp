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
 * @file test_acados_solve.cpp
 * @brief acados 后端冒烟与回归测试。
 *
 * 覆盖:
 *   - 冒烟:标称求解成功、推力在界内、求解时间在预算内、预测维度正确;
 *   - 滚动:20 步 receding-horizon 热启动链全部成功;
 *   - K1 回归:运行时 T_max/T_min 覆盖 codegen 烘焙值 (±25) 后真正生效;
 *   - K2 回归:运行时 dT_max 覆盖烘焙值 (80 N/s) 后首步推力增量受限。
 */

#include <cmath>
#include <stdexcept>
#include <utility>

#include <gtest/gtest.h>

#include "usv_nmpc/acados_backend.hpp"
#include "usv_nmpc/mpc_solver.hpp"
#include "usv_nmpc/utils.hpp"

namespace {

// MpcParams 默认值即 2026-07-23 真船辨识参数 (见 mpc_solver.hpp)。
usv_mpc::MpcParams RealBoatParams() { return usv_mpc::MpcParams(); }

// 直线前推参考: 1 m/s, dt=0.2 s。
Eigen::MatrixXd StraightRef(int n) {
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(6, n + 1);
  for (int k = 0; k <= n; ++k) {
    ref(0, k) = 0.2 * k;
    ref(3, k) = 1.0;
  }
  return ref;
}

}  // namespace

TEST(AcadosSolve, NominalSolveSucceedsWithinBounds) {
  const usv_mpc::MpcParams p = RealBoatParams();
  usv_mpc::AcadosBackend backend(p);
  usv_mpc::Vector6d x0;
  x0.setZero();

  const auto [u, info] = backend.solve(x0, StraightRef(p.N));
  ASSERT_TRUE(info.success) << info.error;
  EXPECT_LE(std::abs(u(0)), p.T_max + 1e-6);
  EXPECT_LE(std::abs(u(1)), p.T_max + 1e-6);
  EXPECT_LT(info.solve_time_ms, 200.0);  // 对应 mpc_params_B.yaml 中的 max_solve_time_ms
  EXPECT_EQ(info.X_pred.rows(), 6);
  EXPECT_EQ(info.X_pred.cols(), p.N + 1);
  EXPECT_EQ(info.U_pred.cols(), p.N);
}

TEST(AcadosSolve, RecedingHorizonWarmStartChainStaysStable) {
  const usv_mpc::MpcParams p = RealBoatParams();
  usv_mpc::AcadosBackend backend(p);
  usv_mpc::Vector6d x;
  x.setZero();

  for (int step = 0; step < 20; ++step) {
    const auto [u, info] = backend.solve(x, StraightRef(p.N));
    ASSERT_TRUE(info.success) << "step=" << step << " err=" << info.error;
    // 用预测下一状态近似前推 (开链热启动验证)
    x = info.X_pred.col(1);
  }
}

TEST(AcadosSolve, RuntimeThrustBoundsTakeEffect) {  // K1
  usv_mpc::MpcParams p = RealBoatParams();
  p.T_max = 10.0;   // 与 codegen 烘焙值 ±25 N 不同
  p.T_min = -10.0;
  usv_mpc::AcadosBackend backend(p);
  usv_mpc::Vector6d x0;
  x0.setZero();

  const auto [u, info] = backend.solve(x0, StraightRef(p.N));
  ASSERT_TRUE(info.success) << info.error;
  EXPECT_LE(std::abs(u(0)), 10.0 + 1e-6)
      << "运行时 T_max 未生效 (仍按烘焙 ±25 N 求解?)";
  EXPECT_LE(std::abs(u(1)), 10.0 + 1e-6);
  // 强化:整条预测序列的所有阶段都必须满足运行时边界
  // (只查 u0 不够——标称解本身可能就小于 10 N)
  ASSERT_EQ(info.U_pred.cols(), p.N);
  for (int k = 0; k < p.N; ++k) {
    EXPECT_LE(info.U_pred.col(k).cwiseAbs().maxCoeff(), 10.0 + 1e-6)
        << "stage " << k << " 越界";
  }
}

TEST(AcadosSolve, RuntimeRateBoundTakesEffect) {  // K2
  usv_mpc::MpcParams p = RealBoatParams();
  p.dT_max = 5.0;   // 烘焙值为 80 N/s;每步 |Δu| <= 5*0.2 = 1 N
  usv_mpc::AcadosBackend backend(p);
  usv_mpc::Vector6d x0;
  x0.setZero();

  const auto [u, info] = backend.solve(x0, StraightRef(p.N));
  ASSERT_TRUE(info.success) << info.error;
  const double dT_step = 5.0 * p.dt;
  EXPECT_LE(std::abs(u(0)), dT_step + 1e-6)
      << "首步变化率约束未生效 (con_h_expr_0 缺失?)";
  EXPECT_LE(std::abs(u(1)), dT_step + 1e-6);
  // 强化:预测序列相邻阶段之差也必须满足
  ASSERT_EQ(info.U_pred.cols(), p.N);
  for (int k = 1; k < p.N; ++k) {
    const double du =
        (info.U_pred.col(k) - info.U_pred.col(k - 1)).cwiseAbs().maxCoeff();
    EXPECT_LE(du, dT_step + 1e-6) << "stage " << k << " 变化率越界";
  }
}

TEST(AcadosSolve, AppliedControlAnchorsNextRateConstraint) {
  usv_mpc::MpcParams p = RealBoatParams();
  p.dT_max = 1.0;
  usv_mpc::AcadosBackend backend(p);
  usv_mpc::Vector6d x0 = usv_mpc::Vector6d::Zero();
  const auto [planned_control, first_info] = backend.solve(x0, StraightRef(p.N));
  ASSERT_TRUE(first_info.success) << first_info.error;
  EXPECT_TRUE(planned_control.allFinite());

  const Eigen::Vector2d applied_control(5.0, -5.0);
  backend.set_applied_control(applied_control);
  EXPECT_THROW(backend.set_applied_control(Eigen::Vector2d(26.0, 0.0)),
               std::out_of_range);

  const Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(6, p.N + 1);
  const auto [u, info] = backend.solve(x0, ref);

  ASSERT_TRUE(info.success) << info.error;
  const double dT_step = p.dT_max * p.dt;
  EXPECT_LE((u - applied_control).cwiseAbs().maxCoeff(), dT_step + 1e-6)
      << "首拍变化率约束没有锚定执行层回写推力";
}

TEST(AcadosSolve, YawWrapAroundPiIsSmooth) {
  const usv_mpc::MpcParams p = RealBoatParams();
  usv_mpc::AcadosBackend backend(p);

  // 第 1 步：USV 艏向接近 +pi（+3.12 rad，u=0.8，r=0.05）
  usv_mpc::Vector6d x1;
  x1 << 0.0, 0.0, 3.12, 0.8, 0.0, 0.05;
  Eigen::MatrixXd ref1 = Eigen::MatrixXd::Zero(6, p.N + 1);
  for (int k = 0; k <= p.N; ++k) {
    ref1(0, k) = 0.8 * p.dt * k;
    ref1(2, k) = usv_mpc::normalize_angle(3.12 + 0.05 * p.dt * k);
    ref1(3, k) = 0.8;
  }
  const auto [u1, info1] = backend.solve(x1, ref1);
  ASSERT_TRUE(info1.success) << info1.error;

  // 第 2 步：USV 艏向越过 +pi，归一化至 -3.14 rad
  usv_mpc::Vector6d x2;
  x2 << 0.8 * p.dt, 0.0, -3.14, 0.8, 0.0, 0.05;
  Eigen::MatrixXd ref2 = Eigen::MatrixXd::Zero(6, p.N + 1);
  for (int k = 0; k <= p.N; ++k) {
    ref2(0, k) = 0.8 * p.dt * (k + 1);
    ref2(2, k) = usv_mpc::normalize_angle(-3.14 + 0.05 * p.dt * k);
    ref2(3, k) = 0.8;
  }
  const auto [u2, info2] = backend.solve(x2, ref2);
  ASSERT_TRUE(info2.success) << info2.error;

  // 验证: 跨越 ±pi 边界时不应发生暴力差动推力饱和 (修复前差动跳变 26.5N, 左推打满 -25N)
  EXPECT_LT(std::abs(u2(0) - u1(0)), 10.0) << "u2(0)=" << u2(0) << " u1(0)=" << u1(0);
  EXPECT_LT(std::abs(u2(1) - u1(1)), 10.0) << "u2(1)=" << u2(1) << " u1(1)=" << u1(1);
  EXPECT_LT(std::abs(u2(1) - u2(0)), 10.0) << "diff=" << u2(1) - u2(0);
}

TEST(AcadosSolve, LargeHeadingErrorsRemainSolvable) {
  const usv_mpc::MpcParams p = RealBoatParams();
  const double heading_errors[] = {M_PI / 2.0, 3.0 * M_PI / 4.0,
                                   M_PI - 1e-3};

  for (const double heading_error : heading_errors) {
    SCOPED_TRACE("heading_error=" + std::to_string(heading_error));
    usv_mpc::AcadosBackend backend(p);
    usv_mpc::Vector6d x0 = usv_mpc::Vector6d::Zero();
    Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(6, p.N + 1);
    ref.row(2).setConstant(heading_error);

    const auto [u, info] = backend.solve(x0, ref);
    ASSERT_TRUE(info.success) << info.error;
    EXPECT_TRUE(u.allFinite());
    EXPECT_TRUE(info.X_pred.allFinite());
    EXPECT_TRUE(info.U_pred.allFinite());
    EXPECT_LE(u.cwiseAbs().maxCoeff(), p.T_max + 1e-6);
  }
}

TEST(AcadosSolve, NegativeCostWeightIsRejected) {
  usv_mpc::MpcParams p = RealBoatParams();
  p.Q_diag(2) = -1.0;
  EXPECT_THROW(usv_mpc::AcadosBackend backend(p), std::invalid_argument);
  EXPECT_THROW(usv_mpc::make_dynamic_mpc(p), std::invalid_argument);
}

TEST(AcadosSolve, FactoryUsesAcadosOnlyAndFailsFastOnCodegenMismatch) {
  const usv_mpc::MpcParams p = RealBoatParams();
  auto solver = usv_mpc::make_dynamic_mpc(p);
  ASSERT_NE(solver, nullptr);
  EXPECT_STREQ(solver->backend(), "acados");

  usv_mpc::MpcParams bad_n = p;
  bad_n.N = p.N + 1;
  EXPECT_THROW(usv_mpc::make_dynamic_mpc(bad_n), std::runtime_error);

  usv_mpc::MpcParams bad_dt = p;
  bad_dt.dt = p.dt + 0.05;
  EXPECT_THROW(usv_mpc::make_dynamic_mpc(bad_dt), std::runtime_error);
}
