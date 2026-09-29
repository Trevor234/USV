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
 * @file test_safety_monitor.cpp
 * @brief SafetyMonitor 纯逻辑层 gtest 单测 (对拍 Python test_safety_monitor.py)。
 */

#include <gtest/gtest.h>

#include "usv_safety_cpp/safety_monitor.hpp"

using usv_safety::SafetyConfig;
using usv_safety::SafetyLevel;
using usv_safety::SafetyMonitor;

// 辅助: flags 中是否有以 prefix 开头的
static bool has_flag(
  const std::vector<std::string> & flags,
  const std::string & prefix)
{
  for (const auto & f : flags) {
    if (f.rfind(prefix, 0) == 0) {return true;}
  }
  return false;
}

// 对应 Python: test_safety_domains_do_not_clear_each_other
TEST(SafetyMonitor, DomainsDoNotClearEachOther) {
  SafetyMonitor m(SafetyConfig{
      /*max_solver_failures*/ 2, /*max_odom_timeout_s*/ 1.0,
      /*max_path_timeout_s*/ 1.0, /*max_solve_time_ms*/ 500.0,
      /*geofence_radius_m*/ 10.0, /*geofence_center_x*/ 0.0,
      /*geofence_center_y*/ 0.0, /*max_crosstrack_error_m*/ 10.0,
      /*low_battery_v*/ 10.5, /*critical_battery_v*/ 10.0,
      /*max_speed_mps*/ 3.0, /*mpc_status_timeout_s*/ 1.0});

  m.update_odom(11.0, 0.0, 0.0, 0.0, 100.0);
  m.update_battery(12.0, 100.0);
  m.update_solver(false, 10.0, 101.0);
  m.update_solver(false, 10.0, 102.0);
  m.update_path(true, 103.0);
  m.update_path(false, 105.0);

  auto flags = m.active_flags();
  EXPECT_TRUE(has_flag(flags, "GEOFENCE VIOLATION"));
  EXPECT_TRUE(has_flag(flags, "Solver failed"));
  EXPECT_TRUE(has_flag(flags, "No path update"));
  EXPECT_EQ(m.level(), SafetyLevel::FAILSAFE);

  // 新 odom 清除 geofence, 但不清除 solver/path failsafe
  m.update_odom(0.0, 0.0, 0.0, 0.0, 106.0);
  flags = m.active_flags();
  EXPECT_FALSE(has_flag(flags, "GEOFENCE VIOLATION"));
  EXPECT_TRUE(has_flag(flags, "Solver failed"));
  EXPECT_TRUE(has_flag(flags, "No path update"));
}

// 对应 Python: test_state_returns_defensive_copy
TEST(SafetyMonitor, StateReturnsDefensiveCopy) {
  SafetyMonitor m(SafetyConfig{5, 1.0, 5.0, 500.0, 10.0, 0.0, 0.0, 10.0, 10.5, 10.0, 3.0});
  m.update_odom(11.0, 0.0, 0.0, 0.0, 100.0);

  auto st = m.state();
  st.active_flags.clear();  // 修改拷贝, 不应影响内部
  EXPECT_TRUE(has_flag(m.active_flags(), "GEOFENCE VIOLATION"));
}

// 对应 Python: test_battery_severity_and_action
TEST(SafetyMonitor, BatterySeverityAndAction) {
  SafetyMonitor m(SafetyConfig{5, 1.0, 5.0, 500.0, 200.0, 0.0, 0.0, 10.0, 10.5, 10.0, 3.0});

  m.update_battery(10.2, 100.0);  // 低电量
  EXPECT_EQ(m.level(), SafetyLevel::WARNING);
  EXPECT_EQ(m.recommended_action(), "REDUCE_SPEED");
  EXPECT_TRUE(has_flag(m.active_flags(), "Low battery"));

  m.update_battery(9.8, 101.0);  // 临界电量
  EXPECT_EQ(m.level(), SafetyLevel::FAILSAFE);
  EXPECT_EQ(m.recommended_action(), "RTL");
  EXPECT_TRUE(has_flag(m.active_flags(), "CRITICAL battery"));
}

// 对应 Python: test_battery_update_does_not_refresh_odom_watchdog
// 电池遥测不得喂活 odom 看门狗 (P0-1)
TEST(SafetyMonitor, BatteryUpdateDoesNotRefreshOdomWatchdog) {
  SafetyMonitor m(SafetyConfig{5, 1.0, 5.0, 500.0, 200.0, 0.0, 0.0, 10.0, 10.5, 10.0, 3.0});

  m.update_odom(0.0, 0.0, 0.0, 0.0, 100.0);
  // odom 断流后电池持续到达
  m.update_battery(12.0, 101.0);
  m.update_battery(12.0, 102.0);
  m.update_battery(12.0, 103.0);

  EXPECT_TRUE(m.check_odom_timeout(103.0));
  m.set_odom_watchdog("Odometry timeout: 3.0s", 103.0);
  EXPECT_EQ(m.level(), SafetyLevel::FAILSAFE);
}

// 对应 Python: test_mpc_status_timeout_triggers_failsafe
// ACTIVE/HOLD 期间 /mpc/status 停发必须触发 failsafe (P0-2)
TEST(SafetyMonitor, MpcStatusTimeoutTriggersFailsafe) {
  SafetyMonitor m(SafetyConfig{5, 1.0, 5.0, 500.0, 200.0, 0.0, 0.0, 10.0,
      10.5, 10.0, 3.0, /*mpc_status_timeout_s*/ 1.0});

  m.mark_mpc_status(100.0);
  EXPECT_FALSE(m.check_mpc_status_timeout(100.5));
  m.set_mpc_status_watchdog("", 100.5);
  EXPECT_EQ(m.level(), SafetyLevel::NOMINAL);

  // MPC 死亡: status 停发, 超时后看门狗升级为 FAILSAFE
  EXPECT_TRUE(m.check_mpc_status_timeout(101.5));
  m.set_mpc_status_watchdog("MPC status timeout: 1.5s", 101.5);
  EXPECT_EQ(m.level(), SafetyLevel::FAILSAFE);
  EXPECT_EQ(m.recommended_action(), "RTL");
  EXPECT_TRUE(has_flag(m.active_flags(), "MPC status timeout"));

  // 恢复新鲜的 status 后看门狗清除
  m.mark_mpc_status(102.0);
  m.set_mpc_status_watchdog("", 102.0);
  EXPECT_EQ(m.level(), SafetyLevel::NOMINAL);
}

// 额外: set_solver_fail_count / clear_solver_flags 同步行为
TEST(SafetyMonitor, SolverFailCountSyncAndClear) {
  SafetyMonitor m(SafetyConfig{5, 1.0, 5.0, 500.0, 200.0, 0.0, 0.0, 10.0, 10.5, 10.0, 3.0});
  m.set_solver_fail_count(3);
  EXPECT_EQ(m.solver_fail_count(), 3);
  m.clear_solver_flags(200.0);
  EXPECT_FALSE(has_flag(m.active_flags(), "Solver failures"));
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
