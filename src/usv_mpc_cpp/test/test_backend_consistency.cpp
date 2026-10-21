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
 * @file test_backend_consistency.cpp
 * @brief acados 与 CasADi 动力学 NMPC 后端一致性回归。
 */

#include <gtest/gtest.h>

#include <memory>
#include <stdexcept>

#include "usv_mpc_cpp/acados_backend.hpp"
#include "usv_mpc_cpp/mpc_solver.hpp"

namespace
{

Eigen::MatrixXd TerminalStepReference(const usv_mpc::MpcParams & params)
{
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(6, params.N + 1);
  // 运行阶段保持原点，终端才给位移目标。该工况对运行/终端代价的相对
  // 缩放敏感，能捕获 CasADi 漏乘 dt 导致的后端目标不一致。
  ref(0, params.N) = 0.5;
  return ref;
}

}  // namespace

TEST(BackendConsistency, TerminalStepFirstControlAgrees) {
  usv_mpc::MpcParams params;
  // 避免首拍被推力变化率或推力硬边界钳住，让比较反映目标函数本身。
  params.T_min = -100.0;
  params.T_max = 100.0;
  params.dT_max = 500.0;

  usv_mpc::AcadosBackend acados(params);
  std::unique_ptr<usv_mpc::DynamicMpc> casadi =
    usv_mpc::make_casadi_dynamic_mpc(params);

  usv_mpc::Vector6d x0 = usv_mpc::Vector6d::Zero();
  const Eigen::MatrixXd ref = TerminalStepReference(params);
  const auto [u_acados, info_acados] = acados.solve(x0, ref);
  const auto [u_casadi, info_casadi] = casadi->solve(x0, ref);

  ASSERT_TRUE(info_acados.success) << info_acados.error;
  ASSERT_TRUE(info_casadi.success) << info_casadi.error;
  ASSERT_TRUE(u_acados.allFinite());
  ASSERT_TRUE(u_casadi.allFinite());

  EXPECT_NEAR(u_acados(0), u_acados(1), 1e-5);
  EXPECT_NEAR(u_casadi(0), u_casadi(1), 1e-5);
  EXPECT_NEAR(u_casadi(0), u_acados(0), 0.03)
      << "相同 Q/R/Rd/Qf_scale 下两个后端的运行/终端代价缩放可能不一致";
}

TEST(BackendConsistency, PeriodicHeadingCostKeepsItsWeight) {
  usv_mpc::MpcParams params;
  params.T_min = -100.0;
  params.T_max = 100.0;
  params.dT_max = 500.0;

  usv_mpc::AcadosBackend acados(params);
  std::unique_ptr<usv_mpc::DynamicMpc> casadi =
    usv_mpc::make_casadi_dynamic_mpc(params);

  usv_mpc::Vector6d x0 = usv_mpc::Vector6d::Zero();
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(6, params.N + 1);
  ref(2, params.N) = 0.5;

  const auto [u_acados, info_acados] = acados.solve(x0, ref);
  const auto [u_casadi, info_casadi] = casadi->solve(x0, ref);

  ASSERT_TRUE(info_acados.success) << info_acados.error;
  ASSERT_TRUE(info_casadi.success) << info_casadi.error;
  ASSERT_TRUE(u_acados.allFinite());
  ASSERT_TRUE(u_casadi.allFinite());

  EXPECT_NEAR(u_acados.sum(), 0.0, 1e-5);
  EXPECT_NEAR(u_casadi.sum(), 0.0, 3e-3);
  EXPECT_NEAR(u_casadi(0), u_acados(0), 0.02)
      << "NONLINEAR_LS 的 0.5*y^T*W*y 约定可能改变了航向权重";
  EXPECT_NEAR(u_casadi(1), u_acados(1), 0.02)
      << "NONLINEAR_LS 的 0.5*y^T*W*y 约定可能改变了航向权重";
}

TEST(BackendConsistency, AppliedControlAnchorsBothRateConstraints) {
  usv_mpc::MpcParams params;
  params.dT_max = 1.0;

  usv_mpc::AcadosBackend acados(params);
  std::unique_ptr<usv_mpc::DynamicMpc> casadi =
    usv_mpc::make_casadi_dynamic_mpc(params);
  const Eigen::Vector2d applied_control(5.0, -5.0);
  acados.set_applied_control(applied_control);
  casadi->set_applied_control(applied_control);

  const usv_mpc::Vector6d x0 = usv_mpc::Vector6d::Zero();
  const Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(6, params.N + 1);
  const auto [u_acados, info_acados] = acados.solve(x0, ref);
  const auto [u_casadi, info_casadi] = casadi->solve(x0, ref);

  ASSERT_TRUE(info_acados.success) << info_acados.error;
  ASSERT_TRUE(info_casadi.success) << info_casadi.error;
  const double dT_step = params.dT_max * params.dt;
  EXPECT_LE((u_acados - applied_control).cwiseAbs().maxCoeff(),
            dT_step + 1e-6);
  EXPECT_LE((u_casadi - applied_control).cwiseAbs().maxCoeff(),
            dT_step + 1e-6);
  EXPECT_NEAR(u_casadi(0), u_acados(0), 0.03);
  EXPECT_NEAR(u_casadi(1), u_acados(1), 0.03);
}

TEST(BackendConsistency, CasadiRejectsNegativeCostWeight) {
  usv_mpc::MpcParams params;
  params.R_diag(0) = -1.0;
  EXPECT_THROW(usv_mpc::make_casadi_dynamic_mpc(params), std::invalid_argument);
}
