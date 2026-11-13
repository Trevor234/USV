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
 * @file test_acados_kinematic.cpp
 * @brief 方案 A acados 后端的真实求解行为与候选门禁。
 *
 * 覆盖:
 *   - 标称求解成功、预测维度 5x(N+1)/2xN、四残差在 tol 内;
 *   - 实际下发锚点 clamp (超界值) 与首拍速率约束;
 *   - 全阶段两通道非对称幅值 + 两种不同变化率 (运行时参数生效);
 *   - 跨 ±π 连续 warm 链; 多拍 reset/重锚;
 *   - 非法 tau/权重/非有限数据不成为成功解;
 *   - generated cost 与解析目标一致 (抓 dt 缩放/p_global 顺序错误);
 *   - 状态码门禁纯函数 (0/2/7 + 有限 + 约束)。
 */

#include <gtest/gtest.h>

#include <cmath>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <utility>

#include "usv_mpc/acados_kinematic_backend.hpp"
#include "usv_mpc/kinematic_mpc_solver.hpp"
#include "usv_mpc/kinematic_solution_audit.hpp"
#include "usv_mpc/usv_model_kinematic.hpp"

namespace
{

constexpr double kDt = 0.2;
constexpr int kN = 20;  // 生成码固定时域

usv_mpc::KinematicMpcParams Params()
{
  usv_mpc::KinematicMpcParams p;
  p.N = kN;
  p.dt = kDt;
  return p;
}

/// 直线参考: x 以 speed 推进, psi=0。
Eigen::MatrixXd StraightRef(int n, double speed)
{
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(3, n + 1);
  for (int k = 0; k <= n; ++k) {
    ref(0, k) = speed * kDt * k;
  }
  return ref;
}

usv_mpc::Vector5d ZeroState(double u = 0.0, double r = 0.0)
{
  usv_mpc::Vector5d state;
  state << 0.0, 0.0, 0.0, u, r;
  return state;
}

double AnalyticObjective(
  const usv_mpc::KinematicMpcParams & params,
  const Eigen::MatrixXd & X,
  const Eigen::MatrixXd & U,
  const Eigen::MatrixXd & ref)
{
  const int n = params.N;
  const double qx = params.Q_diag(0), qy = params.Q_diag(1), qpsi = params.Q_diag(2);
  const double ru = params.R_diag(0), rr = params.R_diag(1);
  double cost = 0.0;
  for (int k = 0; k < n; ++k) {
    const double ex = X(0, k) - ref(0, k);
    const double ey = X(1, k) - ref(1, k);
    cost += qx * ex * ex + qy * ey * ey +
      2.0 * qpsi * (1.0 - std::cos(X(2, k) - ref(2, k)));
    cost += ru * U(0, k) * U(0, k) + rr * U(1, k) * U(1, k);
  }
  const double exN = X(0, n) - ref(0, n);
  const double eyN = X(1, n) - ref(1, n);
  cost += params.Qf_scale * (qx * exN * exN + qy * eyN * eyN +
    2.0 * qpsi * (1.0 - std::cos(X(2, n) - ref(2, n))));
  return cost;
}

}  // namespace

TEST(AcadosKinematic, NominalSolveSucceedsWithinDiagnostics)
{
  const usv_mpc::KinematicMpcParams p = Params();
  usv_mpc::AcadosKinematicBackend backend(p);
  EXPECT_STREQ(backend.backend(), "acados");
  EXPECT_EQ(backend.N(), kN);
  EXPECT_DOUBLE_EQ(backend.dt(), kDt);

  const auto [u, info] = backend.solve(ZeroState(), StraightRef(kN, 0.8));
  ASSERT_TRUE(info.success) << info.error;
  EXPECT_STREQ(info.backend, "acados");
  EXPECT_EQ(info.X_pred.rows(), 5);
  EXPECT_EQ(info.X_pred.cols(), kN + 1);
  EXPECT_EQ(info.U_pred.rows(), 2);
  EXPECT_EQ(info.U_pred.cols(), kN);
  EXPECT_LE(info.initial_state_residual, p.solution_constraint_tol);
  EXPECT_LE(info.max_dynamics_residual, p.solution_constraint_tol);
  EXPECT_LE(info.max_control_bound_violation, p.solution_constraint_tol);
  EXPECT_LE(info.max_control_rate_violation, p.solution_constraint_tol);
  EXPECT_LT(info.solve_time_ms, 200.0);
  EXPECT_GE(u(0), p.u_min - 1e-6);
  EXPECT_LE(u(0), p.u_max + 1e-6);
}

// 幅值边界两通道各不相同, 且必须对全部预测阶段生效。
TEST(AcadosKinematic, AsymmetricBoundsApplyToEveryStage)
{
  usv_mpc::KinematicMpcParams p = Params();
  p.u_min = 0.3;
  p.u_max = 0.9;
  p.r_max = 0.05;
  usv_mpc::AcadosKinematicBackend backend(p);

  // 参考要求 2 m/s, 但 u 上界只有 0.9。锚点必须对齐实测速度, 否则
  // u>=0.3 与首拍 |u-0| <= 0.26 无交集 (节点在 ACTIVE 重入时也是这样锚定)。
  backend.set_applied_command(Eigen::Vector2d(0.8, 0.0));
  const auto [u, info] = backend.solve(ZeroState(0.8, 0.0), StraightRef(kN, 2.0));
  ASSERT_TRUE(info.success) << info.error;
  for (int k = 0; k < info.U_pred.cols(); ++k) {
    EXPECT_GE(info.U_pred(0, k), p.u_min - 1e-6) << "stage " << k;
    EXPECT_LE(info.U_pred(0, k), p.u_max + 1e-6) << "stage " << k;
    EXPECT_GE(info.U_pred(1, k), -p.r_max - 1e-6) << "stage " << k;
    EXPECT_LE(info.U_pred(1, k), p.r_max + 1e-6) << "stage " << k;
  }
}

// 两通道变化率不同 (du_max != dr_max), 首拍相对 anchor、后续相对上一拍。
TEST(AcadosKinematic, DistinctRateLimitsApplyPerChannel)
{
  usv_mpc::KinematicMpcParams p = Params();
  p.du_max = 0.2;   // 每步 0.04
  p.dr_max = 1.0;   // 每步 0.20
  usv_mpc::AcadosKinematicBackend backend(p);

  const Eigen::Vector2d anchor(1.4, 0.0);
  backend.set_applied_command(anchor);
  const auto [u, info] = backend.solve(ZeroState(1.4, 0.0), StraightRef(kN, 1.4));
  ASSERT_TRUE(info.success) << info.error;
  (void)u;

  const double du_step = p.du_max * p.dt;
  const double dr_step = p.dr_max * p.dt;
  Eigen::Vector2d previous = anchor;
  for (int k = 0; k < info.U_pred.cols(); ++k) {
    EXPECT_LE(std::abs(info.U_pred(0, k) - previous(0)), du_step + 1e-4)
      << "stage " << k << " du";
    EXPECT_LE(std::abs(info.U_pred(1, k) - previous(1)), dr_step + 1e-4)
      << "stage " << k << " dr";
    previous = info.U_pred.col(k);
  }
  // 两个通道的实际窗口必须不同: u 被 0.04 卡住, r 允许更大步长。
  EXPECT_GT(dr_step, du_step);
}

// set_applied_command 按两通道各自 clamp; 非有限输入直接拒绝。
TEST(AcadosKinematic, AppliedCommandIsClampedPerChannel)
{
  const usv_mpc::KinematicMpcParams p = Params();
  usv_mpc::AcadosKinematicBackend backend(p);

  backend.set_applied_command(Eigen::Vector2d(99.0, -99.0));
  // clamp 后 u=u_max, r=-r_max; 首拍只能在锚点 ± 步长内。
  const double du_step = p.du_max * p.dt;
  const auto [u, info] = backend.solve(ZeroState(), StraightRef(kN, 0.5));
  ASSERT_TRUE(info.success) << info.error;
  EXPECT_GE(info.U_pred(0, 0), p.u_max - du_step - 5e-3);
  EXPECT_LE(info.U_pred(0, 0), p.u_max + 5e-3);
  EXPECT_GE(info.U_pred(1, 0), -p.r_max - 5e-3);
  EXPECT_LE(info.U_pred(1, 0), -p.r_max + p.dr_max * p.dt + 5e-3);
  (void)u;

  EXPECT_THROW(backend.set_applied_command(
      Eigen::Vector2d(std::numeric_limits<double>::quiet_NaN(), 0.0)),
    std::invalid_argument);
  EXPECT_THROW(backend.set_applied_command(
      Eigen::Vector2d(0.0, std::numeric_limits<double>::infinity())),
    std::invalid_argument);
}

// 运行时参数 (tau/权重/边界) 必须来自 YAML, 而不是 codegen 占位值。
TEST(AcadosKinematic, RuntimeParametersDriveSolutionNotCodegenPlaceholders)
{
  usv_mpc::KinematicMpcParams baseline = Params();
  usv_mpc::KinematicMpcParams altered = Params();
  altered.tau_u = 0.4;      // 生成占位值是 0.8
  altered.tau_r = 1.0;      // 生成占位值是 1.78
  altered.Q_diag << 2.0, 3.0, 7.0;   // 占位值 10/10/50
  altered.R_diag << 0.5, 0.25;       // 占位值 1/1
  altered.u_max = 1.1;               // 占位值 3.3
  altered.du_max = 0.5;              // 占位值 1.3

  usv_mpc::AcadosKinematicBackend baseline_backend(baseline);
  usv_mpc::AcadosKinematicBackend altered_backend(altered);
  const Eigen::MatrixXd ref = StraightRef(kN, 1.6);

  const auto [u_base, info_base] = baseline_backend.solve(ZeroState(), ref);
  const auto [u_alt, info_alt] = altered_backend.solve(ZeroState(), ref);
  ASSERT_TRUE(info_base.success) << info_base.error;
  ASSERT_TRUE(info_alt.success) << info_alt.error;
  (void)u_base;
  (void)u_alt;
  // tau 更短 -> 首拍速度响应更快; 上界 1.1 也必须生效。
  EXPECT_GT(info_alt.X_pred(3, 1), info_base.X_pred(3, 1));
  EXPECT_LE(info_alt.U_pred(0, 0), 1.1 + 1e-6);
}

// 跨 ±π 的连续 warm 链不应出现推力跳变。
TEST(AcadosKinematic, HeadingWrapAroundPiStaysContinuous)
{
  const usv_mpc::KinematicMpcParams p = Params();
  usv_mpc::AcadosKinematicBackend backend(p);

  usv_mpc::Vector5d x1;
  x1 << 0.0, 0.0, 3.12, 0.8, 0.05;
  Eigen::MatrixXd ref1 = Eigen::MatrixXd::Zero(3, kN + 1);
  for (int k = 0; k <= kN; ++k) {
    ref1(0, k) = 0.8 * kDt * k;
    ref1(2, k) = std::atan2(std::sin(3.12 + 0.05 * kDt * k),
        std::cos(3.12 + 0.05 * kDt * k));
  }
  backend.set_applied_command(Eigen::Vector2d(0.8, 0.05));
  const auto [u1, info1] = backend.solve(x1, ref1);
  ASSERT_TRUE(info1.success) << info1.error;

  usv_mpc::Vector5d x2;
  x2 << 0.8 * kDt, 0.0, -3.14, 0.8, 0.05;
  Eigen::MatrixXd ref2 = Eigen::MatrixXd::Zero(3, kN + 1);
  for (int k = 0; k <= kN; ++k) {
    ref2(0, k) = 0.8 * kDt * (k + 1);
    ref2(2, k) = std::atan2(std::sin(-3.14 + 0.05 * kDt * k),
        std::cos(-3.14 + 0.05 * kDt * k));
  }
  const auto [u2, info2] = backend.solve(x2, ref2);
  ASSERT_TRUE(info2.success) << info2.error;

  EXPECT_LT(std::abs(u2(0) - u1(0)), 0.5) << "u2=" << u2(0) << " u1=" << u1(0);
  EXPECT_LT(std::abs(u2(1) - u1(1)), 0.5) << "r2=" << u2(1) << " r1=" << u1(1);
}

// reset 清 anchor/warm: 重置后首拍回到 0 ± 步长, 预测轨迹为空。
TEST(AcadosKinematic, ResetClearsAnchorAndWarmstart)
{
  const usv_mpc::KinematicMpcParams p = Params();
  usv_mpc::AcadosKinematicBackend backend(p);

  backend.set_applied_command(Eigen::Vector2d(1.5, 0.4));
  const auto [u1, info1] = backend.solve(ZeroState(0.5, 0.0), StraightRef(kN, 1.5));
  ASSERT_TRUE(info1.success) << info1.error;
  (void)u1;
  EXPECT_GT(backend.get_predicted_trajectory().size(), 0);

  backend.reset_warmstart();
  EXPECT_EQ(backend.get_predicted_trajectory().size(), 0);

  const auto [u2, info2] = backend.solve(ZeroState(0.5, 0.0), StraightRef(kN, 1.5));
  ASSERT_TRUE(info2.success) << info2.error;
  (void)u2;
  EXPECT_GE(info2.U_pred(0, 0), -5e-3);
  EXPECT_LE(info2.U_pred(0, 0), p.du_max * p.dt + 5e-3);
}

// 多拍重锚 (ACTIVE 重入语义): 每拍锚点对齐实测值, 不得出现突变。
TEST(AcadosKinematic, RepeatedReanchorAfterResetStaysFeasible)
{
  const usv_mpc::KinematicMpcParams p = Params();
  usv_mpc::AcadosKinematicBackend backend(p);
  const Eigen::MatrixXd ref = StraightRef(kN, 1.0);

  for (int cycle = 0; cycle < 3; ++cycle) {
    backend.reset_warmstart();
    const double measured_u = 0.4 + 0.2 * cycle;
    backend.set_applied_command(Eigen::Vector2d(measured_u, 0.0));
    const auto [u, info] = backend.solve(ZeroState(measured_u, 0.0), ref);
    ASSERT_TRUE(info.success) << "cycle " << cycle << " err=" << info.error;
    EXPECT_LE(std::abs(u(0) - measured_u), p.du_max * p.dt + 5e-3);
  }
}

// generated cost 与解析目标一致: 抓 dt 缩放错误和 p_global 顺序错误。
TEST(AcadosKinematic, GeneratedCostMatchesAnalyticObjective)
{
  // 覆盖含终端误差、非零控制、航向跨界和非常规 tau/权重。
  usv_mpc::KinematicMpcParams p = Params();
  p.tau_u = 0.55;
  p.tau_r = 1.2;
  p.Q_diag << 4.0, 6.0, 12.0;
  p.R_diag << 0.7, 0.3;
  p.Qf_scale = 3.0;

  usv_mpc::AcadosKinematicBackend backend(p);
  usv_mpc::Vector5d state;
  state << 0.3, -0.2, 3.05, 0.7, -0.1;

  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(3, kN + 1);
  for (int k = 0; k <= kN; ++k) {
    ref(0, k) = 0.3 + 0.15 * k;
    ref(1, k) = -0.2 + 0.05 * k;
    // 参考航向跨 +pi: 展开后由求解器自己解卷绕。
    const double psi = 3.05 + 0.02 * k;
    ref(2, k) = std::atan2(std::sin(psi), std::cos(psi));
  }

  const auto [u, info] = backend.solve(state, ref);
  ASSERT_TRUE(info.success) << info.error;
  (void)u;

  const double analytic = AnalyticObjective(p, info.X_pred, info.U_pred, ref);
  const double acados = backend.diagnostic_cost();
  ASSERT_TRUE(std::isfinite(acados));
  EXPECT_GT(std::abs(analytic), 1e-3) << "目标值过小, 该用例无鉴别力";
  EXPECT_LE(std::abs(acados - analytic), 1e-8 * std::max(1.0, std::abs(analytic)))
    << "analytic=" << analytic << " acados=" << acados;
}

// 没有候选时 cost getter 必须失败, 不能返回陈旧值。
TEST(AcadosKinematic, DiagnosticCostRequiresFiniteCandidate)
{
  usv_mpc::AcadosKinematicBackend backend(Params());
  EXPECT_THROW(backend.diagnostic_cost(), std::logic_error);
}

// 非法 tau/权重/时域: 构造即失败, 不留下半初始化对象。
TEST(AcadosKinematic, InvalidParametersAreRejected)
{
  usv_mpc::KinematicMpcParams bad_tau = Params();
  bad_tau.tau_u = 0.0;
  EXPECT_THROW(
    {usv_mpc::AcadosKinematicBackend backend(bad_tau); (void)backend;},
    std::invalid_argument);

  usv_mpc::KinematicMpcParams bad_tau_r = Params();
  bad_tau_r.tau_r = -1.0;
  EXPECT_THROW(
    {usv_mpc::AcadosKinematicBackend backend(bad_tau_r); (void)backend;},
    std::invalid_argument);

  usv_mpc::KinematicMpcParams bad_q = Params();
  bad_q.Q_diag(1) = -2.0;
  EXPECT_THROW(
    {usv_mpc::AcadosKinematicBackend backend(bad_q); (void)backend;},
    std::invalid_argument);
  EXPECT_THROW(usv_mpc::make_kinematic_mpc(bad_q), std::invalid_argument);

  usv_mpc::KinematicMpcParams bad_n = Params();
  bad_n.N = kN + 1;
  EXPECT_THROW(
    {usv_mpc::AcadosKinematicBackend backend(bad_n); (void)backend;},
    std::runtime_error);
  EXPECT_THROW(usv_mpc::make_kinematic_mpc(bad_n), std::runtime_error);

  usv_mpc::KinematicMpcParams bad_dt = Params();
  bad_dt.dt = 0.25;
  EXPECT_THROW(
    {usv_mpc::AcadosKinematicBackend backend(bad_dt); (void)backend;},
    std::runtime_error);

  usv_mpc::KinematicMpcParams bad_bound = Params();
  bad_bound.u_min = 2.0;
  bad_bound.u_max = 1.0;
  EXPECT_THROW(
    {usv_mpc::AcadosKinematicBackend backend(bad_bound); (void)backend;},
    std::invalid_argument);
}

// 非有限测量/参考不得成为成功解。
TEST(AcadosKinematic, NonFiniteInputsNeverSucceed)
{
  usv_mpc::AcadosKinematicBackend backend(Params());
  usv_mpc::Vector5d state = ZeroState(0.5, 0.0);
  state(0) = std::numeric_limits<double>::quiet_NaN();
  const auto [u, info] = backend.solve(state, StraightRef(kN, 0.5));
  EXPECT_FALSE(info.success);
  EXPECT_EQ(info.X_pred.size(), 0);
  EXPECT_EQ(info.U_pred.size(), 0);
  EXPECT_TRUE(u.allFinite());

  Eigen::MatrixXd ref = StraightRef(kN, 0.5);
  ref(0, 3) = std::numeric_limits<double>::infinity();
  const auto [u2, info2] = backend.solve(ZeroState(), ref);
  EXPECT_FALSE(info2.success);
  EXPECT_TRUE(u2.allFinite());
}

// audit 纯函数: 同一条可行轨迹, 逐项破坏必须指出正确残差。
TEST(KinematicSolutionAudit, DetectsEachViolationWithCorrectResidual)
{
  usv_mpc::KinematicMpcParams p = Params();
  const usv_mpc::Vector5d measured = ZeroState(0.6, 0.0);
  const Eigen::Vector2d anchor(0.6, 0.0);

  // 构造一条物理可行的 rollout (逐步 RK4, 控制落在边界内)。
  usv_mpc::USVKinematicModel model(p.dt, 4);
  Eigen::MatrixXd X(5, kN + 1);
  Eigen::MatrixXd U(2, kN);
  X.col(0) = measured;
  for (int k = 0; k < kN; ++k) {
    U.col(k) << 0.6 + 0.01 * k, 0.02 * std::sin(0.1 * k);
    X.col(k + 1) = model.forward_unwrapped(
      X.col(k), U.col(k), p.tau_u, p.tau_r);
  }

  usv_mpc::SolveInfo info;
  EXPECT_TRUE(usv_mpc::audit_kinematic_solution(p, measured, anchor, X, U, info))
    << info.error;

  // 1) 初值残差
  {
    Eigen::MatrixXd broken = X;
    broken(0, 0) += 0.05;
    usv_mpc::SolveInfo diag;
    EXPECT_FALSE(usv_mpc::audit_kinematic_solution(p, measured, anchor, broken,
      U, diag));
    EXPECT_NEAR(diag.initial_state_residual, 0.05, 1e-9);
    EXPECT_GE(diag.max_dynamics_residual, 0.04);
  }
  // 2) 动力学残差 (末阶段状态被篡改)
  {
    Eigen::MatrixXd broken = X;
    broken(3, kN) += 0.2;
    usv_mpc::SolveInfo diag;
    EXPECT_FALSE(usv_mpc::audit_kinematic_solution(p, measured, anchor, broken,
      U, diag));
    EXPECT_NEAR(diag.max_dynamics_residual, 0.2, 1e-9);
  }
  // 3) 末阶段幅值越界
  {
    Eigen::MatrixXd broken_u = U;
    broken_u(0, kN - 1) = p.u_max + 0.5;
    usv_mpc::SolveInfo diag;
    EXPECT_FALSE(usv_mpc::audit_kinematic_solution(p, measured, anchor, X,
      broken_u, diag));
    EXPECT_NEAR(diag.max_control_bound_violation, 0.5, 1e-9);
  }
  // 4) 首拍速率越界 (相对 anchor)
  {
    Eigen::MatrixXd broken_u = U;
    broken_u(0, 0) = anchor(0) + p.du_max * p.dt + 0.1;
    usv_mpc::SolveInfo diag;
    EXPECT_FALSE(usv_mpc::audit_kinematic_solution(p, measured, anchor, X,
      broken_u, diag));
    EXPECT_NEAR(diag.max_control_rate_violation, 0.1, 1e-9);
  }
  // 5) 后续相邻变化率越界
  {
    Eigen::MatrixXd broken_u = U;
    broken_u(1, 7) = broken_u(1, 6) + p.dr_max * p.dt + 0.2;
    usv_mpc::SolveInfo diag;
    EXPECT_FALSE(usv_mpc::audit_kinematic_solution(p, measured, anchor, X,
      broken_u, diag));
    EXPECT_NEAR(diag.max_control_rate_violation, 0.2, 1e-9);
  }
  // 6) 维度错误
  {
    usv_mpc::SolveInfo diag;
    EXPECT_FALSE(usv_mpc::audit_kinematic_solution(p, measured, anchor,
      X.leftCols(kN), U, diag));
    EXPECT_EQ(std::strncmp(diag.error, "invalid_solution_dimensions", 26), 0);
  }
  // 7) 非有限
  {
    Eigen::MatrixXd broken = X;
    broken(1, 2) = std::numeric_limits<double>::quiet_NaN();
    usv_mpc::SolveInfo diag;
    EXPECT_FALSE(usv_mpc::audit_kinematic_solution(p, measured, anchor, broken,
      U, diag));
    EXPECT_EQ(std::strncmp(diag.error, "non_finite_solution", 19), 0);
  }
}

// 状态码门禁: 只有 0/2/7 + 有限 + 约束通过才接受。
TEST(KinematicSolutionAudit, StatusGateAcceptsOnlyFeasibleCodes)
{
  EXPECT_TRUE(usv_mpc::accept_kinematic_candidate(0, true, true));
  EXPECT_TRUE(usv_mpc::accept_kinematic_candidate(2, true, true));
  EXPECT_TRUE(usv_mpc::accept_kinematic_candidate(7, true, true));
  EXPECT_FALSE(usv_mpc::accept_kinematic_candidate(0, false, true));
  EXPECT_FALSE(usv_mpc::accept_kinematic_candidate(0, true, false));
  EXPECT_FALSE(usv_mpc::accept_kinematic_candidate(2, true, false));
  EXPECT_FALSE(usv_mpc::accept_kinematic_candidate(7, true, false));
  for (int status : {1, 3, 4, 5, 6, 8, 9, -1}) {
    EXPECT_FALSE(usv_mpc::accept_kinematic_candidate(status, true, true))
      << "status=" << status;
  }
}
