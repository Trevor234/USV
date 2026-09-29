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
 * @file test_planning.cpp
 * @brief 规划纯逻辑层 gtest 单测 (对拍 Python test_speed_profile_and_fillet.py)。
 */

#include <cmath>
#include <fstream>
#include <vector>

#include <Eigen/Dense>
#include <gtest/gtest.h>

#include "usv_planning_cpp/speed_profile.hpp"
#include "usv_planning_cpp/trajectory_optimizer.hpp"
#include "usv_planning_cpp/waypoint_manager.hpp"

using usv_planning::compute_profile;
using usv_planning::fillet_path;

// 对应 Python: test_speed_profile_respects_limits_and_time_monotonicity
TEST(SpeedProfile, RespectsLimitsAndTimeMonotonicity) {
  Eigen::VectorXd s = Eigen::VectorXd::LinSpaced(21, 0.0, 10.0);
  Eigen::VectorXd kappas = Eigen::VectorXd::Constant(21, 0.2);
  auto r = compute_profile(kappas, s, 1.0, 0.3, 1.0, 0.5, 0.5, 0.0, 0.0, 0.1);

  EXPECT_EQ(r.vs.size(), s.size());
  EXPECT_EQ(r.rs.size(), s.size());
  EXPECT_EQ(r.ts.size(), s.size());
  // v <= u_max
  for (int i = 0; i < r.vs.size(); ++i) {
    EXPECT_LE(r.vs(i), 1.0 + 1e-9);
}
  // |r| <= r_max
  for (int i = 0; i < r.rs.size(); ++i) {
    EXPECT_LE(std::fabs(r.rs(i)), 0.3 + 1e-9);
}
  // ts 单调不减
  for (int i = 1; i < r.ts.size(); ++i) {
    EXPECT_GE(r.ts(i) - r.ts(i - 1), -1e-9);
}
}

// 对应 Python: test_fillet_path_outputs_finite_geometry
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
  for (int i = 1; i < r.s.size(); ++i) {
    EXPECT_GE(r.s(i) - r.s(i - 1), -1e-9);
}
  EXPECT_TRUE(r.warnings.empty());
}

TEST(WaypointManager, LoadFromYamlFile) {
  const std::string test_yaml = "/tmp/test_wps.yaml";
  std::ofstream ofs(test_yaml);
  ofs << "waypoints:\n"
      << "  - {x: 1.0, y: 2.0, radius: 1.5, heading_deg: 90.0, stay_time: 2.0}\n"
      << "  - {x: 3.0, y: 4.0}\n";
  ofs.close();

  usv_planning::WaypointManager wm;
  EXPECT_TRUE(wm.load_from_yaml_file(test_yaml, 2.5));
  EXPECT_EQ(wm.waypoints().size(), 2u);
  EXPECT_DOUBLE_EQ(wm.waypoints()[0].x, 1.0);
  EXPECT_DOUBLE_EQ(wm.waypoints()[0].y, 2.0);
  EXPECT_DOUBLE_EQ(wm.waypoints()[0].radius, 1.5);
  EXPECT_NEAR(wm.waypoints()[0].heading, M_PI / 2.0, 1e-6);
  EXPECT_DOUBLE_EQ(wm.waypoints()[0].stay_time, 2.0);

  EXPECT_DOUBLE_EQ(wm.waypoints()[1].x, 3.0);
  EXPECT_DOUBLE_EQ(wm.waypoints()[1].y, 4.0);
  EXPECT_DOUBLE_EQ(wm.waypoints()[1].radius, 2.5);
  EXPECT_DOUBLE_EQ(wm.waypoints()[1].heading, 0.0);
  EXPECT_DOUBLE_EQ(wm.waypoints()[1].stay_time, 0.0);

  std::remove(test_yaml.c_str());

  EXPECT_FALSE(wm.load_from_yaml_file("/tmp/nonexistent_file_12345.yaml"));
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
