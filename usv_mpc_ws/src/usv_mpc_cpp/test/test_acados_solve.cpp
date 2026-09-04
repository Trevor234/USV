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
#include <utility>

#include <gtest/gtest.h>

#include "usv_mpc_cpp/acados_backend.hpp"

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
  EXPECT_LT(info.solve_time_ms, 200.0);  // mpc_params.yaml max_solve_time_ms
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
