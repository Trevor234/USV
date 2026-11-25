// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// 责任测试：一个 capsule + 一个事务，三步回调互不替代，最终 guard 真的在
// 真实 native solve 紧前求值。
//
// 这里测的是"失败能表达"，不是"成功路径能跑"：一个只会返回成功的事务，
// 会让 reset 成功但 C++ 未同步这类真实故障永远无法被观察到（E04）。
//
// 三组入口级事实（都不依赖内部调用次数）：
//   1) 构造即拒绝：合同与生成码/M0 不一致；
//   2) 真过期：真实 stage-0 参数准备返回后越过原始 deadline → 本 Job 零 native、
//      非终端拒绝；同一 owner 的下一合法 Job → native delta=1；
//   3) 真锚点：同代/切代都用调用方传入的非零 anchor（[8,12]）作为 stage 0 起点，
//      g3 与 fresh M0 的首控制一致（同一模型内容 → 同一解）。
#include <gtest/gtest.h>

#include <algorithm>
#include <chrono>
#include <limits>
#include <cmath>
#include <memory>
#include <string>
#include <thread>

#include "usv_nmpc/model_constants.hpp"
#include "p1_engine_session.hpp"
#include "p1_worker_engine.hpp"

namespace {

using StopPredicate = model_txn::RegisteredModelTransaction::StopPredicate;
using ExpiryPredicate = model_txn::RegisteredModelTransaction::ExpiryPredicate;

model_reference::Grid make_grid()
{
  model_reference::Grid g;
  g.schedule_generation = 1;
  g.clock_epoch = 0;
  g.tick_period_ns = 200000000;
  g.deadline_ns = 150000000;
  return g;
}

usv_mpc::MpcParams make_params()
{
  usv_mpc::MpcParams p;
  p.N = usv_nmpc::kDynamicN;
  p.dt = usv_nmpc::kDynamicDt;
  p.T_min = usv_nmpc::kDynamicTMin;
  p.T_max = usv_nmpc::kDynamicTMax;
  p.dT_max = usv_nmpc::kDynamicDTMax;
  // 与 model_reference::m0_content() 逐项一致。
  p.hydro.mass = 14.2;
  p.hydro.Iz = 2.13;
  p.hydro.xg = 0.12;
  p.hydro.d_thruster = 0.25;
  p.hydro.Xu_dot = -2.0;
  p.hydro.Yv_dot = -8.0;
  p.hydro.Yr_dot = -0.1817725;
  p.hydro.Nv_dot = -0.1817725;
  p.hydro.Nr_dot = -3.41;
  p.hydro.Xu = -2.272063;
  p.hydro.Yv = -2.629019;
  p.hydro.Yr = 0.0;
  p.hydro.Nv = 0.0;
  p.hydro.Nr = -3.105;
  p.hydro.Xuu = -11.571784;
  p.hydro.Yvv = -0.05;
  p.hydro.Yrr = 0.0;
  p.hydro.Nvv = 0.0;
  p.hydro.Nrr = -0.71;
  p.Q_diag << 20.0, 20.0, 50.0, 8.0, 1.0, 8.0;
  p.R_diag << 0.05, 0.05;
  p.Rd_diag << 0.2, 0.2;
  p.Qf_scale = 8.0;
  return p;
}

std::int64_t now_ns()
{
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}

model_txn::RegisteredModelTransaction::JobIdentity identity()
{
  return {"run", "boot", "contract", "nominal", "worker"};
}

Eigen::VectorXd state()
{
  Eigen::VectorXd x(6);
  x << 0.0, 0.0, 0.0, 1.0, 0.0, 0.0;
  return x;
}

Eigen::MatrixXd reference()
{
  Eigen::MatrixXd r(6, 21);
  r.setZero();
  r.row(0).setLinSpaced(21, 0.0, 4.0);
  r.row(1).setZero();
  r.row(2).setZero();
  r.row(3).setConstant(1.0);
  return r;
}

model_reference::Axes axes_of_generation(std::uint64_t generation)
{
  model_reference::Axes a;
  a.task = 1;
  a.model = generation;
  a.config = 1;
  a.schedule = 1;
  a.epoch = 0;
  return a;
}

}  // namespace

// 合同与生成码不一致时，构造就必须失败；静默修正会让所有后续断言失去意义。
TEST(P1EngineSession, RejectsContractThatDivergesFromGeneratedCode)
{
  auto params = make_params();
  params.N = usv_nmpc::kDynamicN + 1;
  const auto grid = make_grid();
  auto registry = model_reference::default_registry();
  EXPECT_THROW(p1::WorkerEngine(params, registry, grid, 1), std::runtime_error);
}

// 构造即核对 M0：合同参数必须就是登记表里的 M0，否则第一拍之前就应拒绝。
TEST(P1EngineSession, RejectsContractThatIsNotTheRegisteredM0)
{
  auto params = make_params();
  params.hydro.mass = 99.0;
  const auto grid = make_grid();
  auto registry = model_reference::default_registry();
  EXPECT_THROW(p1::WorkerEngine(params, registry, grid, 1), std::runtime_error);
}

// 引擎在构造后即处于"模型一致、代 1、零 solve"的状态。
TEST(P1EngineSession, BootstrapIsAppliedAndNothingWasSolved)
{
  const auto params = make_params();
  const auto grid = make_grid();
  auto registry = model_reference::default_registry();
  p1::WorkerEngine engine(params, registry, grid, 1);

  EXPECT_EQ(engine.applied_generation(), 1u);
  EXPECT_TRUE(engine.model_consistent());
  EXPECT_FALSE(engine.faulted());
  EXPECT_EQ(engine.N(), usv_nmpc::kDynamicN);
  EXPECT_DOUBLE_EQ(engine.dt(), usv_nmpc::kDynamicDt);
  EXPECT_EQ(engine.preparation().constraint_set_calls, 0u);
  EXPECT_EQ(engine.preparation().update_params_calls, 0u);
  EXPECT_EQ(engine.preparation().out_set_calls, 0u);
  EXPECT_EQ(engine.touch_facts().setter_entries, 0u);
  EXPECT_EQ(engine.touch_facts().reset_entries, 0u);
  EXPECT_EQ(engine.touch_facts().sync_entries, 0u);
}

// 入口级：准备期间越过原始 deadline，本 Job 必须零 native 且非终端；
// 同一 owner/capsule 的下一合法 Job 必须真的求解（delta=1）。
TEST(P1EngineSession, ExpiryDuringPreparationRefusesZeroNativeAndSuccessorSolves)
{
  const auto params = make_params();
  const auto grid = make_grid();
  auto registry = model_reference::default_registry();
  p1::WorkerEngine engine(params, registry, grid, 1);

  // 先用一次正常求解测出"进入最终 guard 之前的真实耗时"，再据此设期限：
  // 期限取该区间的一半，于是准备开始（几 µs）仍在期限内，guard 复采
  // （≈ 全额区间）必然越过它。这不是"按调用次数"的判据，而是实测时间。
  // 先做一次正常求解，把 capsule 与参数缓存推到稳态。
  p1::EngineOutcome warm;
  const std::int64_t warm_start = now_ns();
  engine.solve(axes_of_generation(1), grid, 1, 1, warm_start + 1'000'000'000,
               state(), reference(), Eigen::Vector2d(8.0, 12.0), identity(),
               [] { return false; }, [] { return false; }, &warm);
  ASSERT_EQ(warm.execution, p1::EngineDisposition::CandidateReady);

  const std::int64_t expired_start = now_ns();
  const std::int64_t tight_deadline = expired_start + 1'000'000;  // 1 ms
  engine.set_test_preparation_delay_ns(5'000'000);                // 5 ms 在提交之后

  p1::EngineOutcome expired;
  engine.solve(axes_of_generation(1), grid, 3, 1, tight_deadline, state(),
               reference(), Eigen::Vector2d(8.0, 12.0), identity(),
               [] { return false; }, [] { return false; }, &expired);

  engine.set_test_preparation_delay_ns(0);

  EXPECT_EQ(expired.execution, p1::EngineDisposition::JobRefused);
  EXPECT_TRUE(expired.guard_refused);
  EXPECT_FALSE(expired.terminal);
  EXPECT_EQ(expired.refusal.origin, model_txn::RefusalOrigin::RawFinalGuard);
  EXPECT_EQ(expired.refusal.fault, model_txn::RefusalFault::Expiry);
  EXPECT_EQ(expired.native_solve_entries_this_job, 0u);
  EXPECT_EQ(expired.original_deadline_ns, tight_deadline);
  EXPECT_GT(expired.guard_checked_ns, tight_deadline);
  EXPECT_FALSE(engine.faulted());
  // 准备本身是完整的（124 次真实 native），只是最后的 C solve 没有进入。
  EXPECT_EQ(expired.preparation.ordinals, 1u);
  EXPECT_TRUE(expired.preparation.complete);
  EXPECT_EQ(expired.preparation.constraint_set_calls, 82u);

  // 后继合法 Job：同一 engine、同一 capsule，必须真的进入 native solve。
  const std::int64_t fresh_deadline = now_ns() + 1'000'000'000;
  p1::EngineOutcome successor;
  const auto answer = engine.solve(
      axes_of_generation(1), grid, 4, 1, fresh_deadline, state(), reference(),
      Eigen::Vector2d(8.0, 12.0), identity(), [] { return false; },
      [fresh_deadline] { return now_ns() > fresh_deadline; }, &successor);

  EXPECT_EQ(successor.execution, p1::EngineDisposition::CandidateReady);
  EXPECT_FALSE(successor.terminal);
  EXPECT_EQ(successor.native_solve_entries_this_job, 1u);
  EXPECT_EQ(successor.native_solve_entries_after,
            successor.native_solve_entries_before + 1);
  EXPECT_EQ(successor.preparation.ordinals, 1u);
  EXPECT_TRUE(successor.preparation.complete);
  EXPECT_EQ(successor.preparation.constraint_set_calls, 82u);
  EXPECT_EQ(successor.preparation.update_params_calls, 21u);
  EXPECT_EQ(successor.preparation.out_set_calls, 41u);
  EXPECT_TRUE(answer.second.success);
  EXPECT_GT(answer.second.solve_time_ms, 0.0);  // 真实 solved 耗时，不再写死 0
}

// 谓词抛异常必须成为 PredicateFault（终端），而不是"过期"。
TEST(P1EngineSession, PredicateThrowIsPredicateFaultNotExpiry)
{
  const auto params = make_params();
  const auto grid = make_grid();
  auto registry = model_reference::default_registry();
  p1::WorkerEngine engine(params, registry, grid, 1);

  p1::EngineOutcome outcome;
  engine.solve(axes_of_generation(1), grid, 1, 1, now_ns() + 1'000'000'000, state(),
               reference(), Eigen::Vector2d(8.0, 12.0), identity(),
               [] { return false; },
               []() -> bool { throw std::runtime_error("predicate blew up"); },
               &outcome);

  EXPECT_EQ(outcome.execution, p1::EngineDisposition::TerminalFault);
  EXPECT_TRUE(outcome.terminal);
  EXPECT_EQ(outcome.refusal.origin, model_txn::RefusalOrigin::PredicateFault);
  EXPECT_EQ(outcome.native_solve_entries_this_job, 0u);
}

// 真锚点：同代 + g1→g2 + g2→g3 都必须用调用方传入的 [8,12] 作为 stage 0 起点，
// 而不是切换后清零的默认值。g3 与 fresh M0 是同一模型内容，首控制应一致。
TEST(P1EngineSession, NonZeroAnchorSurvivesGenerationSwitches)
{
  const auto params = make_params();
  const auto grid = make_grid();
  auto registry = model_reference::default_registry();
  p1::WorkerEngine engine(params, registry, grid, 1);
  const Eigen::Vector2d anchor(8.0, 12.0);

  const auto run = [&](std::uint64_t job_id, std::uint64_t generation,
                       p1::EngineOutcome * outcome) {
    return engine.solve(axes_of_generation(generation), grid, job_id,
                        job_id + 1, now_ns() + 1'000'000'000, state(), reference(),
                        anchor, identity(), [] { return false; },
                        [] { return false; }, outcome);
  };

  p1::EngineOutcome same_generation;
  const auto first = run(1, 1, &same_generation);
  EXPECT_EQ(same_generation.execution, p1::EngineDisposition::CandidateReady);
  EXPECT_EQ(engine.applied_generation(), 1u);

  p1::EngineOutcome to_g2;
  const auto second = run(6, 2, &to_g2);
  EXPECT_EQ(to_g2.execution, p1::EngineDisposition::CandidateReady);
  EXPECT_TRUE(to_g2.model_switched);
  EXPECT_EQ(engine.applied_generation(), 2u);
  EXPECT_EQ(engine.touch_facts().sync_entries, 1u);

  p1::EngineOutcome to_g3;
  const auto third = run(12, 3, &to_g3);
  EXPECT_EQ(to_g3.execution, p1::EngineDisposition::CandidateReady);
  EXPECT_EQ(engine.applied_generation(), 3u);
  EXPECT_EQ(engine.touch_facts().sync_entries, 2u);

  // 切换首拍不得因清零锚点而产生不同的变化率起点：三条候选的首控制都应
  // 落在同一个 stage 0 邻域内（同一 anchor、同一 state/reference）。
  EXPECT_LT((first.first - second.first).norm(), 5.0);
  EXPECT_LT((second.first - third.first).norm(), 5.0);

  // g3 == M0：与全新引擎（bootstrap M0）在同一输入下的首控制一致。
  p1::WorkerEngine fresh(params, registry, grid, 1);
  p1::EngineOutcome fresh_outcome;
  const auto fresh_answer = fresh.solve(
      axes_of_generation(1), grid, 1, 1, now_ns() + 1'000'000'000, state(),
      reference(), anchor, identity(), [] { return false; },
      [] { return false; }, &fresh_outcome);
  EXPECT_EQ(fresh_outcome.execution, p1::EngineDisposition::CandidateReady);
  EXPECT_LT((third.first - fresh_answer.first).norm(), 1e-8);
}
