// 版权所有 2026 USV Developer
//
// 特此免费授予任何获得本软件及相关文档文件（下称“软件”）副本的人不受限制地处置该软件的权利，
// 包括但不限于使用、复制、修改、合并、发布、分发、再许可和/或出售软件副本的权利，
// 以及允许获得本软件的人这样做，但须满足以下条件：
//
// 上述版权声明和本许可声明应包含在软件的所有副本或主要部分中。
//
// 本软件按“原样”提供，不附带任何明示或暗示的担保，包括但不限于对适销性、
// 特定用途适用性和非侵权性的担保。在任何情况下，作者或版权持有人均不对因软件、
// 软件的使用或与软件相关的其他交易而产生的任何索赔、损害赔偿或其他责任承担责任，
// 无论该等责任是基于合同诉讼、侵权行为还是其他原因。

/**
 * @file test_planning.cpp
 * @brief 规划纯逻辑层 gtest 单测。
 */

#include <gtest/gtest.h>

#include <Eigen/Dense>
#include <cmath>
#include <vector>

#include "usv_planning/speed_profile.hpp"
#include "usv_planning/trajectory_optimizer.hpp"

using usv_planning::compute_profile;
using usv_planning::fillet_path;

// 速度剖面满足动力学约束与时间单调性
TEST(SpeedProfile, RespectsLimitsAndTimeMonotonicity) {
  Eigen::VectorXd s = Eigen::VectorXd::LinSpaced(21, 0.0, 10.0);
  Eigen::VectorXd kappas = Eigen::VectorXd::Constant(21, 0.2);
  auto r = compute_profile(kappas, s, 1.0, 0.3, 1.0, 0.5, 0.5, 0.0, 0.0, 0.1);

  EXPECT_EQ(r.vs.size(), s.size());
  EXPECT_EQ(r.rs.size(), s.size());
  EXPECT_EQ(r.ts.size(), s.size());
  // 速度不超过最大巡航速度 u_max
  for (int i = 0; i < r.vs.size(); ++i) EXPECT_LE(r.vs(i), 1.0 + 1e-9);
  // 转艏角速度幅值不超过 r_max
  for (int i = 0; i < r.rs.size(); ++i) EXPECT_LE(std::fabs(r.rs(i)), 0.3 + 1e-9);
  // ts 单调不减
  for (int i = 1; i < r.ts.size(); ++i) EXPECT_GE(r.ts(i) - r.ts(i - 1), -1e-9);
}

// 圆弧倒角路径输出有限几何量
TEST(FilletPath, OutputsFiniteGeometry) {
  std::vector<std::pair<double, double>> wps = {{0, 0}, {10, 0}, {10, 10}};
  auto r = fillet_path(wps, 2.0, 0.5);

  EXPECT_GE(r.xs.size(), 2);
  EXPECT_EQ(r.xs.size(), r.ys.size());
  EXPECT_EQ(r.xs.size(), r.psis.size());
  EXPECT_EQ(r.xs.size(), r.kappas.size());
  EXPECT_EQ(r.xs.size(), r.s.size());
  for (int i = 0; i < r.xs.size(); ++i) {
    EXPECT_TRUE(std::isfinite(r.xs(i)));
    EXPECT_TRUE(std::isfinite(r.ys(i)));
    EXPECT_TRUE(std::isfinite(r.psis(i)));
    EXPECT_TRUE(std::isfinite(r.kappas(i)));
  }
  // s 单调不减
  for (int i = 1; i < r.s.size(); ++i) EXPECT_GE(r.s(i) - r.s(i - 1), -1e-9);
  EXPECT_TRUE(r.warnings.empty());
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
