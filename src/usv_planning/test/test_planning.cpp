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
#include "usv_planning/waypoint_manager.hpp"

using usv_planning::Waypoint;
using usv_planning::WaypointManager;
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

// 首航点在未进入到达半径但沿首段前向越过时可正常推进至 idx=1，到末点准确触发完成
TEST(WaypointManager, FirstWaypointPassedWithoutEnteringRadius) {
  WaypointManager mgr;
  mgr.set_turn_radius(4.0);
  mgr.add_waypoint(Waypoint{0.0, 0.0, 2.0, 0.0, 0.0});
  mgr.add_waypoint(Waypoint{20.0, 0.0, 2.0, 0.0, 0.0});
  mgr.add_waypoint(Waypoint{20.0, 20.0, 2.0, 0.0, 0.0});

  // 船从距 wp[0] 5.0 m 处沿航段前进 (未进入 2.0 m 半径)
  EXPECT_TRUE(mgr.update_progress(5.0, 0.0));
  EXPECT_EQ(mgr.current_index(), 1);
  EXPECT_FALSE(mgr.mission_complete());

  // 经由倒角外切区越过中间拐点 wp[1]
  EXPECT_TRUE(mgr.update_progress(20.0, 3.0));
  EXPECT_EQ(mgr.current_index(), 2);
  EXPECT_FALSE(mgr.mission_complete());

  // 到达末点 2.0 m 半径内准确触发完成
  EXPECT_TRUE(mgr.update_progress(20.0, 18.5));
  EXPECT_TRUE(mgr.mission_complete());
}

// 长末段上船距终点 5.0 m（或越过 5.0 m）时不因 0.5*seg_len 放大圈误触发完成，仅在 < radius 时完成
TEST(WaypointManager, FinalWaypointRequiresStrictRadius) {
  WaypointManager mgr;
  mgr.set_turn_radius(4.0);
  mgr.add_waypoint(Waypoint{0.0, 0.0, 2.0, 0.0, 0.0});
  mgr.add_waypoint(Waypoint{30.0, 0.0, 2.0, 0.0, 0.0});

  // 先越过 wp[0]，进入末段 wp[1]
  EXPECT_TRUE(mgr.update_progress(2.0, 0.0));
  EXPECT_EQ(mgr.current_index(), 1);

  // 在 30 m 长末段上，距终点 5.0 m (不论前后) 均不应提前触发 mission_complete
  EXPECT_FALSE(mgr.update_progress(25.0, 0.0));
  EXPECT_FALSE(mgr.mission_complete());
  EXPECT_FALSE(mgr.update_progress(35.0, 0.0));
  EXPECT_FALSE(mgr.mission_complete());
  EXPECT_FALSE(mgr.update_progress(30.0, 2.1));
  EXPECT_FALSE(mgr.mission_complete());

  // 严格进入 2.0 m 到达半径内才触发完成
  EXPECT_TRUE(mgr.update_progress(28.5, 0.0));
  EXPECT_TRUE(mgr.mission_complete());
}

// 传入保底起步初速 v_start=0.4 m/s 时，起点及前 2 m 内参考速度保持 >= 0.4 m/s
TEST(SpeedProfile, NonZeroStartVelocityPreventsDeadlock) {
  Eigen::VectorXd s = Eigen::VectorXd::LinSpaced(21, 0.0, 10.0);
  Eigen::VectorXd kappas = Eigen::VectorXd::Zero(21);
  auto r = compute_profile(kappas, s, 0.8, 0.35, 0.35, 0.35, 0.25, 0.4, 0.0, 0.2);

  ASSERT_EQ(r.vs.size(), s.size());
  EXPECT_NEAR(r.vs(0), 0.4, 1e-9);
  for (int i = 0; i < r.vs.size(); ++i) {
    if (s(i) <= 2.0 + 1e-9) {
      EXPECT_GE(r.vs(i), 0.4 - 1e-9) << "i=" << i << " s=" << s(i);
    }
  }
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
