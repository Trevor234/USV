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
 * @file test_instance_isolation.cpp
 * @brief 共用一个后端实现时, A/B 两个实例必须彼此独立。
 *
 * 只使用 usv_acados 公共 API (不同时包含两个方案 facade, 避免同名 SolveInfo):
 *   - 同一进程内构造 kinematic 与 dynamic 实例并交错求解;
 *   - 一个实例的 reset 不得改变另一个实例的 warm 成功链与首拍速率锚点;
 *   - 实例维度/参数长度错误必须在构造或 solve 时立即失败。
 *
 * 这里不做方案语义的残差门禁 (那属于各方案适配器), 只验证引擎边界。
 */

// 手写测试头按 ament_cpplint 顺序: 对应头 -> C system -> C++ system -> other。
#include <gtest/gtest.h>

#include <cmath>
#include <stdexcept>
#include <vector>

#include "usv_acados/acados_backend.hpp"

namespace
{

constexpr int kDynamicPGlobal = 30;
constexpr int kKinematicPGlobal = 8;

// 与 usv_params_B.yaml / HydroParams 默认值一致 (水动力 19 维)。
void FillDynamicPGlobal(Eigen::VectorXd & pg)
{
  pg.resize(kDynamicPGlobal);
  const double hydro[kDynamicPGlobal - 11] = {
    14.2, 2.13, 0.12, 0.25,
    -2.0, -8.0, 0.0, -0.363545, -3.41,
    -2.272063, -2.629019, 0.0, 0.0, -3.105,
    -11.571784, -0.05, 0.0, 0.0, -0.71,
  };
  for (int i = 0; i < 19; ++i) {
    pg(i) = hydro[i];
  }
  pg(19) = 20.0;   // Q[0]
  pg(20) = 20.0;   // Q[1]
  pg(21) = 50.0;   // Q[2]
  pg(22) = 8.0;    // Q[3]
  pg(23) = 1.0;    // Q[4]
  pg(24) = 8.0;    // Q[5]
  pg(25) = 0.05;   // R[0]
  pg(26) = 0.05;   // R[1]
  pg(27) = 0.2;    // Rd[0]
  pg(28) = 0.2;    // Rd[1]
  pg(29) = 8.0;    // Qf_scale
}

void FillKinematicPGlobal(Eigen::VectorXd & pg)
{
  pg.resize(kKinematicPGlobal);
  pg << 0.8, 1.78, 10.0, 10.0, 50.0, 1.0, 1.0, 10.0;
}

usv_acados::Problem DynamicProblem()
{
  usv_acados::Problem problem;
  problem.N = 20;
  problem.dt = 0.2;
  FillDynamicPGlobal(problem.p_global);
  problem.lower << -25.0, -25.0;
  problem.upper << 25.0, 25.0;
  problem.max_delta << 80.0 * 0.2, 80.0 * 0.2;
  return problem;
}

usv_acados::Problem KinematicProblem()
{
  usv_acados::Problem problem;
  problem.N = 20;
  problem.dt = 0.2;
  FillKinematicPGlobal(problem.p_global);
  problem.lower << 0.0, -1.25;
  problem.upper << 3.3, 1.25;
  problem.max_delta << 1.3 * 0.2, 1.25 * 0.2;
  return problem;
}

/// 直线参考: 位置按速度推进, 航向恒为 0。
Eigen::MatrixXd StraightReference(int rows, int N, double dt, double speed)
{
  Eigen::MatrixXd reference = Eigen::MatrixXd::Zero(rows, N + 1);
  for (int k = 0; k <= N; ++k) {
    reference(0, k) = speed * dt * k;
    if (rows >= 6) {
      reference(3, k) = speed;
    }
  }
  return reference;
}

}  // namespace

TEST(AcadosInstanceIsolation, DimensionsFollowModel)
{
  usv_acados::AcadosBackend kinematic(
    usv_acados::Model::Kinematic, KinematicProblem());
  usv_acados::AcadosBackend dynamic(usv_acados::Model::Dynamic, DynamicProblem());

  EXPECT_EQ(kinematic.n_phys(), 5);
  EXPECT_EQ(kinematic.n_aug(), 7);
  EXPECT_EQ(dynamic.n_phys(), 6);
  EXPECT_EQ(dynamic.n_aug(), 8);
  EXPECT_EQ(kinematic.nu(), 2);
  EXPECT_EQ(dynamic.nu(), 2);
}

// 重置一个实例不得影响另一个实例的 warm 链与锚点。
TEST(AcadosInstanceIsolation, ResetDoesNotLeakAcrossInstances)
{
  usv_acados::AcadosBackend kinematic(
    usv_acados::Model::Kinematic, KinematicProblem());
  usv_acados::AcadosBackend dynamic(usv_acados::Model::Dynamic, DynamicProblem());

  const Eigen::Vector2d kin_anchor(1.2, 0.1);
  const Eigen::Vector2d dyn_anchor(5.0, -5.0);

  Eigen::VectorXd kin_state(5);
  kin_state << 0.0, 0.0, 0.0, 0.8, 0.0;
  Eigen::VectorXd dyn_state(6);
  dyn_state << 0.0, 0.0, 0.0, 0.8, 0.0, 0.0;

  const Eigen::MatrixXd kin_ref = StraightReference(3, 20, 0.2, 0.8);
  const Eigen::MatrixXd dyn_ref = StraightReference(6, 20, 0.2, 0.8);

  // 交错两拍, 两个实例各自建立 warm 链。
  kinematic.set_anchor(kin_anchor);
  dynamic.set_anchor(dyn_anchor);
  for (int tick = 0; tick < 2; ++tick) {
    const auto & kin_candidate = kinematic.solve(kin_state, kin_ref);
    ASSERT_TRUE(kin_candidate.finite) << "kin status=" << kin_candidate.status;
    ASSERT_TRUE(kin_candidate.status == 0) << "kin status=" << kin_candidate.status;
    kinematic.accept_candidate();

    const auto & dyn_candidate = dynamic.solve(dyn_state, dyn_ref);
    ASSERT_TRUE(dyn_candidate.finite) << "dyn status=" << dyn_candidate.status;
    ASSERT_TRUE(dyn_candidate.status == 0) << "dyn status=" << dyn_candidate.status;
    dynamic.accept_candidate();
  }

  ASSERT_TRUE(kinematic.has_warmstart());
  ASSERT_TRUE(dynamic.has_warmstart());
  const Eigen::Vector2d dyn_anchor_after = dynamic.anchor();
  const Eigen::MatrixXd dyn_warm_before = dynamic.warm_states();

  // 只重置运动学实例。
  kinematic.reset_warmstart();
  EXPECT_FALSE(kinematic.has_warmstart());
  EXPECT_TRUE(kinematic.anchor().isZero());

  // 动态实例的锚点/热启动必须逐位不变。
  EXPECT_TRUE(dynamic.has_warmstart());
  EXPECT_TRUE(dynamic.anchor() == dyn_anchor_after);
  EXPECT_TRUE(dynamic.warm_states() == dyn_warm_before);

  // 动态实例继续求解仍成功, 且首拍速率约束仍锚定在 reset 之前的锚点。
  const auto & next = dynamic.solve(dyn_state, dyn_ref);
  ASSERT_TRUE(next.finite);
  ASSERT_EQ(next.status, 0);
  const Eigen::Vector2d first_control = next.U.col(0);
  EXPECT_LE((first_control - dyn_anchor_after).cwiseAbs().maxCoeff(),
            80.0 * 0.2 + 1e-6);
  EXPECT_TRUE(next.X_aug.col(0).head(6).isApprox(dyn_state, 1e-9));
  // 增广尾部 = 本拍锚点 (未被 reset 影响)
  EXPECT_LE((next.X_aug.col(0).tail(2) - dyn_anchor_after).cwiseAbs().maxCoeff(),
            1e-12);
  dynamic.accept_candidate();

  // 运动学实例重置后重新建立 warm 链也不受影响。
  const auto & kin_next = kinematic.solve(kin_state, kin_ref);
  ASSERT_TRUE(kin_next.finite);
  ASSERT_EQ(kin_next.status, 0);
  EXPECT_TRUE(kin_next.X_aug.col(0).head(5).isApprox(kin_state, 1e-9));
}

TEST(AcadosInstanceIsolation, InvalidDimensionsAreRejected)
{
  usv_acados::Problem problem = KinematicProblem();
  problem.p_global.resize(7);
  EXPECT_THROW(
    usv_acados::AcadosBackend(usv_acados::Model::Kinematic, problem),
    std::invalid_argument);

  usv_acados::Problem wrong_n = KinematicProblem();
  wrong_n.N = 21;
  EXPECT_THROW(
    usv_acados::AcadosBackend(usv_acados::Model::Kinematic, wrong_n),
    std::runtime_error);

  usv_acados::Problem wrong_dt = KinematicProblem();
  wrong_dt.dt = 0.25;
  EXPECT_THROW(
    usv_acados::AcadosBackend(usv_acados::Model::Kinematic, wrong_dt),
    std::runtime_error);

  EXPECT_THROW(
    usv_acados::AcadosBackend(usv_acados::Model::Dynamic, KinematicProblem()),
    std::invalid_argument);

  usv_acados::AcadosBackend kinematic(
    usv_acados::Model::Kinematic, KinematicProblem());
  Eigen::VectorXd state5(5);
  state5 << 0.0, 0.0, 0.0, 0.8, 0.0;
  Eigen::VectorXd state6(6);
  state6 << 0.0, 0.0, 0.0, 0.8, 0.0, 0.0;
  EXPECT_THROW(
    kinematic.solve(state6, StraightReference(3, 20, 0.2, 0.8)),
    std::invalid_argument);
  EXPECT_THROW(
    kinematic.solve(state5, StraightReference(6, 20, 0.2, 0.8)),
    std::invalid_argument);

  Eigen::VectorXd nan_state(5);
  nan_state << std::nan(""), 0.0, 0.0, 0.8, 0.0;
  EXPECT_THROW(
    kinematic.solve(nan_state, StraightReference(3, 20, 0.2, 0.8)),
    std::invalid_argument);
}

// accept_candidate 之前不得有可提交候选: 这是适配器门禁的前提。
TEST(AcadosInstanceIsolation, CandidateCostRequiresFiniteCandidate)
{
  usv_acados::AcadosBackend kinematic(
    usv_acados::Model::Kinematic, KinematicProblem());
  EXPECT_THROW(kinematic.candidate_cost(), std::logic_error);
  EXPECT_THROW(kinematic.accept_candidate(), std::logic_error);
}

TEST(AcadosInstanceIsolation, StageResidualAndFirstStepPreferenceSemantics)
{
  usv_acados::AcadosBackend nominal(usv_acados::Model::Dynamic, DynamicProblem());
  usv_acados::AcadosBackend zero_res(usv_acados::Model::Dynamic, DynamicProblem());
  usv_acados::AcadosBackend gp_bias(usv_acados::Model::Dynamic, DynamicProblem());
  usv_acados::AcadosBackend ppo_pref(usv_acados::Model::Dynamic, DynamicProblem());
  usv_acados::AcadosBackend zero_lam(usv_acados::Model::Dynamic, DynamicProblem());

  Eigen::VectorXd state6(6);
  state6 << 0.0, 0.0, 0.0, 0.6, 0.0, 0.0;
  Eigen::MatrixXd ref6 = StraightReference(6, 20, 0.2, 0.8);
  Eigen::MatrixXd res_zero = Eigen::MatrixXd::Zero(3, 21);

  const auto c_nom = nominal.solve(state6, ref6);
  const auto c_zero = zero_res.solve(state6, ref6, res_zero, Eigen::Vector2d(10.0, 10.0), 0.0);
  ASSERT_TRUE(c_nom.finite && c_zero.finite);
  EXPECT_LT((c_nom.U - c_zero.U).cwiseAbs().maxCoeff(), 1e-12);
  EXPECT_LT((c_nom.X_aug - c_zero.X_aug).cwiseAbs().maxCoeff(), 1e-12);

  // Known positive surge velocity residual -> lower thrust required to match target speed.
  Eigen::MatrixXd res_surge = Eigen::MatrixXd::Zero(3, 21);
  res_surge.row(0).setConstant(0.08);
  const auto c_gp = gp_bias.solve(state6, ref6, res_surge, Eigen::Vector2d::Zero(), 0.0);
  ASSERT_TRUE(c_gp.finite);
  EXPECT_LT(c_gp.U(0, 0), c_nom.U(0, 0) - 0.1);

  // lambda_pi == 0 ignores q_pi; lambda_pi > 0 pulls U(:,0) toward q_pi within bounds.
  const Eigen::Vector2d q_target(12.0, -4.0);
  const auto c_l0 = zero_lam.solve(state6, ref6, res_zero, q_target, 0.0);
  EXPECT_LT((c_l0.U - c_nom.U).cwiseAbs().maxCoeff(), 1e-12);

  const auto c_pref = ppo_pref.solve(state6, ref6, res_zero, q_target, 5.0);
  ASSERT_TRUE(c_pref.finite);
  EXPECT_LT((c_pref.U.col(0) - q_target).norm(), (c_nom.U.col(0) - q_target).norm());
  for (int k = 0; k < 20; ++k) {
    EXPECT_GE(c_pref.U(0, k), -25.0 - 1e-6);
    EXPECT_LE(c_pref.U(0, k), 25.0 + 1e-6);
    EXPECT_GE(c_pref.U(1, k), -25.0 - 1e-6);
    EXPECT_LE(c_pref.U(1, k), 25.0 + 1e-6);
  }
  const double du0_l = std::abs(c_pref.U(0, 0) - 0.0);
  const double du0_r = std::abs(c_pref.U(1, 0) - 0.0);
  EXPECT_LE(du0_l, 16.0 + 1e-4);
  EXPECT_LE(du0_r, 16.0 + 1e-4);
}
