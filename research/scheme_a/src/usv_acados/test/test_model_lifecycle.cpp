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
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

/**
 * @file test_model_lifecycle.cpp
 * @brief 受检模型事务原语与最后一道 native guard 的生命周期测试。
 *
 * 覆盖计划步骤 3 的合同:
 *   - update_p_global/reset_native/clear_cpp_state 的分离语义;
 *   - reset_warmstart 先受检原生重置, 成功才清 warm;
 *   - PreparationLedger 在 N=20 dynamic 上的精确计数
 *     (constraints 82 / update 21 / out_set 41);
 *   - 完整准备后 final guard 拒绝: 零 C solve、同代下一拍真实求解;
 *   - 参数错长/非有限在进入 setter 前被拒;
 *   - g3 事务后与 fresh M0 的全轨迹数值对拍 (≤1e-8)。
 *
 * 准备失败 (constraints/update_params 非零) 无法用真实 SDK 自然触发,
 * 属于受控 adapter 报告注入, 不在本测试中冒充 SDK 失败。
 */

// 手写测试头按 ament_cpplint 顺序: 对应头 -> C system -> C++ system -> other。
#include <gtest/gtest.h>

#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

#include "usv_acados/acados_backend.hpp"

namespace
{

constexpr int kDynamicPGlobal = 30;

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

/// M1 计划参数: mass=15.0, Xu=-2.4, Nr=-4.4, 其余与 M0 相同。
usv_acados::Problem M1Problem()
{
  usv_acados::Problem problem = DynamicProblem();
  problem.p_global(0) = 15.0;   // mass
  problem.p_global(4) = -2.4;   // Xu
  problem.p_global(12) = -4.4;  // Nr
  return problem;
}

Eigen::VectorXd State6(double x, double y, double psi, double u, double v, double r)
{
  Eigen::VectorXd state(6);
  state << x, y, psi, u, v, r;
  return state;
}

/// 直线参考: 位置按速度推进, 航向恒为 0。
Eigen::MatrixXd StraightReference6(int N, double dt, double speed)
{
  Eigen::MatrixXd reference = Eigen::MatrixXd::Zero(6, N + 1);
  for (int k = 0; k <= N; ++k) {
    reference(0, k) = speed * dt * k;
    reference(3, k) = speed;
  }
  return reference;
}

/// 拒绝事实 (guard 抛出的类型化异常)。
struct GuardRefusal
  : public std::runtime_error
{
  explicit GuardRefusal(const std::string & what)
  : std::runtime_error(what) {}
};

}  // namespace

TEST(ModelLifecycle, PreparationLedgerCountsExactNativeCalls)
{
  usv_acados::AcadosBackend backend(usv_acados::Model::Dynamic, DynamicProblem());
  const auto reference = StraightReference6(20, 0.2, 0.6);
  const auto state = State6(0.0, 0.0, 0.0, 0.0, 0.0, 0.0);

  const auto & candidate = backend.solve(state, reference);
  ASSERT_TRUE(candidate.finite);
  const auto & ledger = backend.preparation();

  // N=20 一轮完整准备: constraints 2 + 4*20 = 82, update 21, out_set 41。
  EXPECT_EQ(ledger.ordinals, 1u);
  EXPECT_EQ(ledger.constraint_set_calls, 82u);
  EXPECT_EQ(ledger.constraint_set_failed, 0u);
  EXPECT_EQ(ledger.update_params_calls, 21u);
  EXPECT_EQ(ledger.update_params_failed, 0u);
  EXPECT_EQ(ledger.out_set_calls, 41u);
  EXPECT_TRUE(ledger.complete);
  EXPECT_EQ(backend.native_solve_entries(), 1u);

  // 第二拍: 账本清零重来, native 累计 +1。
  const auto & second = backend.solve(state, reference);
  ASSERT_TRUE(second.finite);
  EXPECT_EQ(backend.preparation().ordinals, 1u);
  EXPECT_EQ(backend.preparation().constraint_set_calls, 82u);
  EXPECT_EQ(backend.native_solve_entries(), 2u);
}

TEST(ModelLifecycle, FinalGuardRejectionKeepsZeroNativeEntriesThenNextSolveIsReal)
{
  usv_acados::AcadosBackend backend(usv_acados::Model::Dynamic, DynamicProblem());
  const auto reference = StraightReference6(20, 0.2, 0.6);
  const auto state = State6(0.0, 0.0, 0.0, 0.0, 0.0, 0.0);

  // 正常一拍, 建立事实。
  const auto & first = backend.solve(state, reference);
  ASSERT_TRUE(first.finite);
  ASSERT_EQ(backend.native_solve_entries(), 1u);

  // 完整准备后的 final guard 拒绝: hook 抛出的类型化拒绝原样上抛。
  usv_acados::SolveHooks hooks;
  hooks.context = nullptr;
  hooks.before_native = [](void *, const usv_acados::PreparationLedger & ledger) {
      // guard 看到的准备账必须是完整的一轮。
      if (!ledger.complete || ledger.constraint_set_calls != 82u ||
        ledger.update_params_calls != 21u || ledger.out_set_calls != 41u)
      {
        throw std::logic_error("guard: preparation incomplete");
      }
      throw GuardRefusal("guard: rejected before native solve");
    };
  ASSERT_THROW(backend.solve(state, reference, hooks), GuardRefusal);

  // 拒绝拍零 C solve; 准备账仍完整 (准备已发生, native 未进入)。
  EXPECT_EQ(backend.native_solve_entries(), 1u);
  EXPECT_TRUE(backend.preparation().complete);

  // 同代下一拍真实求解: 计数恢复递增, 结果有限。
  const auto & next = backend.solve(state, reference);
  EXPECT_TRUE(next.finite);
  EXPECT_EQ(backend.native_solve_entries(), 2u);
}

TEST(ModelLifecycle, UpdatePGlobalRejectsBadInputBeforeAnySetter)
{
  usv_acados::AcadosBackend backend(usv_acados::Model::Dynamic, DynamicProblem());

  Eigen::VectorXd wrong_length(29);
  wrong_length.setZero();
  EXPECT_THROW(backend.update_p_global(wrong_length), std::invalid_argument);

  Eigen::VectorXd non_finite(30);
  non_finite.setZero();
  non_finite(7) = std::nan("");
  EXPECT_THROW(backend.update_p_global(non_finite), std::invalid_argument);

  // 非法输入零 setter: native solve 计数不受影响, 引擎仍可正常求解。
  EXPECT_EQ(backend.native_solve_entries(), 0u);
  const auto reference = StraightReference6(20, 0.2, 0.6);
  const auto state = State6(0.0, 0.0, 0.0, 0.0, 0.0, 0.0);
  const auto & candidate = backend.solve(state, reference);
  EXPECT_TRUE(candidate.finite);
}

TEST(ModelLifecycle, TransactionSequenceAppliesM1AndReturnsToFreshM0)
{
  // 同一引擎: M0 求解 -> 事务换入 M1 参数 -> 回到 M0 (g3 语义, 重新换入
  // M0 参数并 clear) 与全新构造的 M0 引擎在全 X/U 上对拍。
  usv_acados::Problem m0_problem = DynamicProblem();
  usv_acados::Problem m1_problem = M1Problem();

  usv_acados::AcadosBackend engine(usv_acados::Model::Dynamic, m0_problem);
  usv_acados::AcadosBackend fresh_m0(usv_acados::Model::Dynamic, m0_problem);

  const auto reference = StraightReference6(20, 0.2, 0.6);
  const auto state = State6(0.0, 0.0, 0.0, 0.0, 0.0, 0.0);

  // g1: M0 首拍 (候选引用会被下一次 solve 覆盖, 先复制首控制)。
  const auto & m0_first = engine.solve(state, reference);
  ASSERT_TRUE(m0_first.finite);
  const Eigen::Vector2d m0_u0 = m0_first.U.col(0);
  engine.accept_candidate();

  // g2: 换入 M1 (update_p_global + reset_native(1) + clear_cpp_state)。
  ASSERT_EQ(engine.update_p_global(m1_problem.p_global), 0);
  ASSERT_EQ(engine.reset_native(1), 0);
  engine.clear_cpp_state();
  const auto & m1_first = engine.solve(state, reference);
  ASSERT_TRUE(m1_first.finite);
  const Eigen::Vector2d m1_u0 = m1_first.U.col(0);
  EXPECT_EQ(engine.native_solve_entries(), 2u);
  // M1 参数确实改变了动力学: 同一状态下首控制不同。
  EXPECT_GT((m1_u0 - m0_u0).norm(), 1e-9);

  // g3: 回到 M0。事务换参数 + 受检 reset + 清 warm, 不得复用旧 warm 链。
  ASSERT_EQ(engine.update_p_global(m0_problem.p_global), 0);
  ASSERT_EQ(engine.reset_native(1), 0);
  engine.clear_cpp_state();
  const auto & m0_again = engine.solve(state, reference);
  ASSERT_TRUE(m0_again.finite);

  // fresh M0 同状态/同参考的首拍 (无 warm)。
  const auto & m0_fresh = fresh_m0.solve(state, reference);
  ASSERT_TRUE(m0_fresh.finite);

  // 全轨迹 X/U 与新构造 M0 一致 (≤1e-8): 换回 M0 后不再残留 M1/旧 warm。
  ASSERT_EQ(m0_again.X_aug.rows(), m0_fresh.X_aug.rows());
  ASSERT_EQ(m0_again.U.cols(), m0_fresh.U.cols());
  EXPECT_LE((m0_again.X_aug - m0_fresh.X_aug).cwiseAbs().maxCoeff(), 1e-8);
  EXPECT_LE((m0_again.U - m0_fresh.U).cwiseAbs().maxCoeff(), 1e-8);
}

TEST(ModelLifecycle, ResetWarmstartClearsWarmAfterCheckedNativeReset)
{
  usv_acados::AcadosBackend backend(usv_acados::Model::Dynamic, DynamicProblem());
  const auto reference = StraightReference6(20, 0.2, 0.6);
  const auto state = State6(0.0, 0.0, 0.0, 0.0, 0.0, 0.0);

  const auto & candidate = backend.solve(state, reference);
  ASSERT_TRUE(candidate.finite);
  backend.accept_candidate();
  ASSERT_TRUE(backend.has_warmstart());

  // 受检 reset 成功后才清 warm: 结果是无 warm 的干净状态。
  backend.reset_warmstart();
  EXPECT_FALSE(backend.has_warmstart());
  EXPECT_TRUE(backend.warm_states().isZero(0.0));
  EXPECT_TRUE(backend.anchor().isZero());

  // reset 后同代下一拍仍是真实求解 (零 warm 初猜路径)。
  const auto & next = backend.solve(state, reference);
  EXPECT_TRUE(next.finite);
  EXPECT_EQ(backend.native_solve_entries(), 2u);
  EXPECT_TRUE(backend.preparation().complete);
}

TEST(ModelLifecycle, ResetNativeAndClearCppStateAreSeparatePrimitives)
{
  usv_acados::AcadosBackend backend(usv_acados::Model::Dynamic, DynamicProblem());
  const auto reference = StraightReference6(20, 0.2, 0.6);
  const auto state = State6(0.0, 0.0, 0.0, 0.0, 0.0, 0.0);

  const auto & candidate = backend.solve(state, reference);
  ASSERT_TRUE(candidate.finite);
  backend.accept_candidate();

  // reset_native 单独调用: 返回真实状态, 不清 warm。
  ASSERT_EQ(backend.reset_native(1), 0);
  EXPECT_TRUE(backend.has_warmstart());

  // clear_cpp_state 单独调用: 清 warm/anchor/candidate, 零 native 调用,
  // native 累计计数不变。
  const uint64_t before = backend.native_solve_entries();
  backend.clear_cpp_state();
  EXPECT_FALSE(backend.has_warmstart());
  EXPECT_TRUE(backend.anchor().isZero());
  EXPECT_EQ(backend.native_solve_entries(), before);
}
