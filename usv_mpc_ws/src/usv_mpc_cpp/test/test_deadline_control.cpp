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
 * @file test_deadline_control.cpp
 * @brief Deadline rejection regressions observing the actual ROS publications.
 *
 * No simulator, FCU, or production delay parameter is used. The controller timer
 * is cancelled and every output is redirected to a unique test-only topic.
 */

#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdio>
#include <limits>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <gtest/gtest.h>
#include <nlohmann/json.hpp>

#include "usv_mpc_cpp/mpc_node.hpp"

namespace usv_mpc
{

// The only private access seam; it injects a solver without changing ROS params.
class MpcControllerNodeTestAccess
{
public:
  static std::shared_ptr<MpcControllerNode> make(std::unique_ptr<DynamicMpc> solver)
  {
    auto node = std::shared_ptr<MpcControllerNode>(
      new MpcControllerNode(std::move(solver)));
    node->timer_->cancel();
    node->dyn_T_min_ = -25.0;
    node->dyn_T_max_ = 25.0;
    node->max_solve_time_ms_ = 200.0;
    node->solver_hold_threshold_ = 5;
    node->publish_predicted_ = true;
    node->prev_state_ = "ACTIVE";
    // P1_ATOMIC_DEADLINE_FIXTURE_V1
    // These tests exercise deadline/output behavior on an eligible controller.
    // Build eligibility through actual callbacks instead of bypassing the gate.
    node->require_fcu_state_ = false;
    node->odom_timeout_s_ = 0.0;
    auto state = std::make_shared<nav_msgs::msg::Odometry>();
    state->header.frame_id = "map";
    state->child_frame_id = "base_link";
    state->pose.pose.orientation.w = 1.0;
    node->odom_callback_(state);
    auto path = std::make_shared<nav_msgs::msg::Path>();
    path->header.frame_id = "map";
    for (int i = 0; i < 4; ++i) {
      geometry_msgs::msg::PoseStamped pose;
      pose.pose.position.x = static_cast<double>(i);
      pose.pose.orientation.w = 1.0;
      path->poses.push_back(pose);
    }
    node->path_callback_(path);
    return node;
  }

  static void outputs(MpcControllerNode & node, const std::string & prefix)
  {
    node.rc_pub_ = node.create_publisher<mavros_msgs::msg::OverrideRCIn>(prefix + "/rc", 10);
    node.vrx_left_pub_ = node.create_publisher<std_msgs::msg::Float64>(prefix + "/left", 10);
    node.vrx_right_pub_ = node.create_publisher<std_msgs::msg::Float64>(prefix + "/right", 10);
    node.status_pub_ = node.create_publisher<std_msgs::msg::String>(prefix + "/status", 10);
    node.traj_pub_ = node.create_publisher<nav_msgs::msg::Path>(prefix + "/trajectory", 10);
  }

  static bool discovered(const MpcControllerNode & node)
  {
    return node.rc_pub_->get_subscription_count() > 0 &&
           node.vrx_left_pub_->get_subscription_count() > 0 &&
           node.vrx_right_pub_->get_subscription_count() > 0 &&
           node.status_pub_->get_subscription_count() > 0 &&
           node.traj_pub_->get_subscription_count() > 0;
  }

  static void vrx(MpcControllerNode & node, double scale = 1.0, double limit = 25.0)
  {
    node.output_mode_ = "vrx_thrust";
    node.vrx_thrust_scale_ = scale;
    node.vrx_thrust_cmd_max_ = limit;
  }

  static void rc(MpcControllerNode & node)
  {
    node.output_mode_ = "rc_override";
    node.steering_gain_ = 1.0;
    node.throttle_gain_ = 0.5;
    node.steering_sign_ = -1.0;
  }

  static void run(MpcControllerNode & node)
  {
    // Make every candidate eligible for trajectory publication, including late ones.
    node.control_count_ = 0;
    node.run_dynamic_mpc_();
  }

  static void standby(MpcControllerNode & node) {node.enter_standby_("test_disarmed");}

  static bool has_history(const MpcControllerNode & node) {return node.has_last_command_;}

  static void heading(MpcControllerNode & node, double yaw) {node.psi_ = yaw;}

  static bool enforce(MpcControllerNode & node, SolveInfo & info, double wall, double max)
  {
    node.max_solve_time_ms_ = max;
    return node.enforce_solve_deadline_(info, wall);
  }
};

}  // namespace usv_mpc

namespace
{

using usv_mpc::MpcControllerNodeTestAccess;
using usv_mpc::SolveInfo;
using namespace std::chrono_literals;

class FakeDynamicMpc : public usv_mpc::DynamicMpc
{
public:
  Eigen::Vector2d candidate = {8.0, 12.0};
  Eigen::Vector2d anchor = Eigen::Vector2d::Zero();
  Eigen::Vector2d solve_entry_anchor = Eigen::Vector2d::Zero();
  bool success = true;
  double reported_ms = 1.0;
  std::chrono::milliseconds delay{0};
  int reset_count = 0;
  std::vector<std::string> events;
  bool block = false;
  bool entered = false;
  bool released = false;
  std::mutex gate_mutex;
  std::condition_variable gate;

  std::pair<Eigen::Vector2d, SolveInfo> solve(
    const usv_mpc::Vector6d &, const Eigen::MatrixXd &) override
  {
    solve_entry_anchor = anchor;
    events.push_back("solve");
    if (block) {
      std::unique_lock<std::mutex> lock(gate_mutex);
      entered = true;
      gate.notify_all();
      gate.wait(lock, [this]() {return released;});
    }
    std::this_thread::sleep_for(delay);
    anchor = candidate;  // Mirrors the backend's tentative first-control cache.
    SolveInfo info;
    info.success = success;
    info.solve_time_ms = reported_ms;
    std::snprintf(info.backend, sizeof(info.backend), "fake");
    if (!success) {std::snprintf(info.error, sizeof(info.error), "backend_failure");}
    info.X_pred = Eigen::MatrixXd::Zero(6, N() + 1);
    info.U_pred = Eigen::MatrixXd::Zero(2, N());
    return {candidate, std::move(info)};
  }

  void set_applied_control(const Eigen::Vector2d & applied) override
  {
    events.push_back("set_applied");
    anchor = applied;
  }

  void reset_warmstart() override
  {
    events.push_back("reset");
    ++reset_count;
    anchor.setZero();
  }

  Eigen::MatrixXd get_predicted_trajectory() const override {return {};}
  int N() const override {return 2;}
  double dt() const override {return 0.2;}
  const char * backend() const override {return "fake";}
};

class DeadlineControl : public ::testing::Test
{
protected:
  static void SetUpTestSuite() {rclcpp::init(0, nullptr);}
  static void TearDownTestSuite() {rclcpp::shutdown();}

  void SetUp() override
  {
    static unsigned int sequence = 0;
    const auto suffix = std::to_string(++sequence);
    prefix_ = "/deadline_test/instance_" + suffix;
    auto solver = std::make_unique<FakeDynamicMpc>();
    fake_ = solver.get();
    controller_ = MpcControllerNodeTestAccess::make(std::move(solver));
    MpcControllerNodeTestAccess::outputs(*controller_, prefix_);
    MpcControllerNodeTestAccess::vrx(*controller_);
    observer_ = std::make_shared<rclcpp::Node>("deadline_observer_" + suffix);
    left_sub_ = observer_->create_subscription<std_msgs::msg::Float64>(
      prefix_ + "/left", 10,
      [this](std_msgs::msg::Float64::ConstSharedPtr msg) {left_.push_back(msg->data);});
    right_sub_ = observer_->create_subscription<std_msgs::msg::Float64>(
      prefix_ + "/right", 10,
      [this](std_msgs::msg::Float64::ConstSharedPtr msg) {right_.push_back(msg->data);});
    rc_sub_ = observer_->create_subscription<mavros_msgs::msg::OverrideRCIn>(
      prefix_ + "/rc", 10,
      [this](mavros_msgs::msg::OverrideRCIn::ConstSharedPtr msg) {rc_.push_back(*msg);});
    status_sub_ = observer_->create_subscription<std_msgs::msg::String>(
      prefix_ + "/status", 10,
      [this](std_msgs::msg::String::ConstSharedPtr msg) {
        status_.push_back(nlohmann::json::parse(msg->data));
      });
    traj_sub_ = observer_->create_subscription<nav_msgs::msg::Path>(
      prefix_ + "/trajectory", 10,
      [this](nav_msgs::msg::Path::ConstSharedPtr) {++trajectories_;});
    executor_.add_node(observer_);
    const auto deadline = std::chrono::steady_clock::now() + 3s;
    while (!MpcControllerNodeTestAccess::discovered(*controller_) &&
      std::chrono::steady_clock::now() < deadline)
    {
      executor_.spin_some();
      std::this_thread::sleep_for(5ms);
    }
    ASSERT_TRUE(MpcControllerNodeTestAccess::discovered(*controller_));
  }

  void TearDown() override
  {
    executor_.remove_node(observer_);
    controller_.reset();
    observer_.reset();
  }

  void run(bool use_rc = false)
  {
    left_.clear(); right_.clear(); rc_.clear(); status_.clear(); trajectories_ = 0;
    MpcControllerNodeTestAccess::run(*controller_);
    drain(use_rc);
  }

  void drain(bool use_rc = false)
  {
    const auto deadline = std::chrono::steady_clock::now() + 2s;
    while ((status_.empty() || (use_rc ? rc_.empty() : (left_.empty() || right_.empty()))) &&
      std::chrono::steady_clock::now() < deadline)
    {
      executor_.spin_some();
      std::this_thread::sleep_for(2ms);
    }
    executor_.spin_some();
    // Drain the trajectory topic too before clearing observations for the next run.
    const auto settle = std::chrono::steady_clock::now() + 20ms;
    while (std::chrono::steady_clock::now() < settle) {
      executor_.spin_some();
      std::this_thread::sleep_for(1ms);
    }
    ASSERT_EQ(status_.size(), 1u);
    if (use_rc) {
      ASSERT_EQ(rc_.size(), 1u);
    } else {
      ASSERT_EQ(left_.size(), 1u);
      ASSERT_EQ(right_.size(), 1u);
    }
  }

  void expect_vrx(double left, double right)
  {
    ASSERT_EQ(left_.size(), 1u);
    ASSERT_EQ(right_.size(), 1u);
    EXPECT_DOUBLE_EQ(left_.at(0), left);
    EXPECT_DOUBLE_EQ(right_.at(0), right);
    EXPECT_DOUBLE_EQ(fake_->anchor(0), left);
    EXPECT_DOUBLE_EQ(fake_->anchor(1), right);
  }

  std::shared_ptr<usv_mpc::MpcControllerNode> controller_;
  FakeDynamicMpc * fake_ = nullptr;
  std::shared_ptr<rclcpp::Node> observer_;
  rclcpp::executors::SingleThreadedExecutor executor_;
  std::string prefix_;
  rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr left_sub_, right_sub_;
  rclcpp::Subscription<mavros_msgs::msg::OverrideRCIn>::SharedPtr rc_sub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr status_sub_;
  rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr traj_sub_;
  std::vector<double> left_, right_;
  std::vector<mavros_msgs::msg::OverrideRCIn> rc_;
  std::vector<nlohmann::json> status_;
  unsigned int trajectories_ = 0;
};

TEST_F(DeadlineControl, TimelySuccessPublishesCandidateAndActualAnchor)
{
  run();
  expect_vrx(8.0, 12.0);
  EXPECT_TRUE(status_.at(0).at("success").get<bool>());
  EXPECT_FALSE(status_.at(0).at("deadline_miss").get<bool>());
  EXPECT_TRUE(status_.at(0).contains("solve_wall_time_ms"));
  EXPECT_TRUE(status_.at(0).contains("control_source"));
  EXPECT_EQ(status_.at(0).at("control_source").get<std::string>(), "solver");
  EXPECT_EQ(trajectories_, 1u);
  EXPECT_EQ(fake_->reset_count, 0);
}

TEST_F(DeadlineControl, BlockingSolveWithShortBackendTimingCannotPublishItsCandidate)
{
  run();
  fake_->candidate = {22.0, -18.0};
  fake_->reported_ms = 1.0;
  int rejected_count = 0;
  for (const auto delay : {250ms, 400ms}) {
    SCOPED_TRACE(delay.count());
    fake_->delay = delay;
    const auto start = std::chrono::steady_clock::now();
    run();
    EXPECT_GE(std::chrono::steady_clock::now() - start, delay);
    expect_vrx(8.0, 12.0);
    EXPECT_FALSE(status_.at(0).at("success").get<bool>());
    EXPECT_TRUE(status_.at(0).at("deadline_miss").get<bool>());
    EXPECT_DOUBLE_EQ(status_.at(0).at("solve_time_ms").get<double>(), 1.0);
    const double wall_ms = status_.at(0).at("solve_wall_time_ms").get<double>();
    EXPECT_GE(wall_ms, static_cast<double>(delay.count()));
    EXPECT_EQ(status_.at(0).at("control_source").get<std::string>(), "repeat_last_command");
    EXPECT_EQ(trajectories_, 0u);
    ASSERT_GE(fake_->events.size(), 3u);
    EXPECT_EQ(fake_->events[fake_->events.size() - 2], "reset");
    EXPECT_EQ(fake_->events.back(), "set_applied");
    ++rejected_count;
    EXPECT_EQ(fake_->reset_count, rejected_count);
    std::printf(
      "DEADLINE_OBSERVED injected_ms=%d backend_ms=%.3f wall_ms=%.3f "
      "left=%.3f right=%.3f source=%s\n",
      static_cast<int>(delay.count()),
      status_.at(0).at("solve_time_ms").get<double>(), wall_ms,
      left_.at(0), right_.at(0),
      status_.at(0).at("control_source").get<std::string>().c_str());
  }
}

TEST_F(DeadlineControl, BackendReportedTimeoutIsAlsoRejectedAndRecoveryUsesActualAnchor)
{
  run();
  fake_->candidate = {22.0, -18.0};
  fake_->reported_ms = 250.0;
  run();
  expect_vrx(8.0, 12.0);
  EXPECT_TRUE(status_.at(0).at("deadline_miss").get<bool>());
  EXPECT_EQ(trajectories_, 0u);
  fake_->candidate = {9.0, 11.0};
  fake_->reported_ms = 1.0;
  run();
  EXPECT_DOUBLE_EQ(fake_->solve_entry_anchor(0), 8.0);
  EXPECT_DOUBLE_EQ(fake_->solve_entry_anchor(1), 12.0);
  expect_vrx(9.0, 11.0);
  EXPECT_TRUE(status_.at(0).at("success").get<bool>());
  EXPECT_EQ(status_.at(0).at("fail_count").get<int>(), 0);
}

TEST_F(DeadlineControl, FirstTimeoutCommandsNeutralRcInsteadOfReleasingChannels)
{
  MpcControllerNodeTestAccess::rc(*controller_);
  fake_->reported_ms = 250.0;
  run(true);
  ASSERT_EQ(rc_.size(), 1u);
  EXPECT_EQ(rc_.at(0).channels[0], 1500u);
  EXPECT_EQ(rc_.at(0).channels[2], 1500u);
  EXPECT_TRUE(fake_->anchor.isZero());
  EXPECT_FALSE(status_.at(0).at("hold").get<bool>());
  EXPECT_EQ(status_.at(0).at("fail_count").get<int>(), 1);
  EXPECT_EQ(status_.at(0).at("control_source").get<std::string>(), "zero_no_history");
}

TEST_F(DeadlineControl, FirstTimeoutWithoutCachePublishesZeroVrx)
{
  fake_->reported_ms = 250.0;
  run();
  expect_vrx(0.0, 0.0);
}

TEST_F(DeadlineControl, FourTimeoutsHoldLastCommandAndFifthEntersHold)
{
  run();
  fake_->candidate = {22.0, -18.0};
  fake_->reported_ms = 250.0;
  for (int failure = 1; failure <= 6; ++failure) {
    SCOPED_TRACE(failure);
    run();
    expect_vrx(failure < 5 ? 8.0 : 0.0, failure < 5 ? 12.0 : 0.0);
    EXPECT_EQ(status_.at(0).at("fail_count").get<int>(), failure);
    EXPECT_EQ(status_.at(0).at("hold").get<bool>(), failure >= 5);
    EXPECT_EQ(status_.at(0).at("control_source").get<std::string>(),
      failure >= 5 ? "hold_zero" : "repeat_last_command");
    EXPECT_EQ(trajectories_, 0u);
  }
}

TEST_F(DeadlineControl, NonunitVrxScaleAndClampAreNotAppliedTwiceOnTimeout)
{
  for (const double scale : {0.5, 2.0}) {
    SCOPED_TRACE(scale);
    MpcControllerNodeTestAccess::vrx(*controller_, scale, 20.0);
    fake_->candidate = {12.0, -18.0};
    fake_->reported_ms = 1.0;
    run();
    const double expected_left = scale == 0.5 ? 6.0 : 20.0;
    const double expected_right = scale == 0.5 ? -9.0 : -20.0;
    expect_vrx(expected_left, expected_right);
    fake_->candidate = {-22.0, 22.0};
    fake_->reported_ms = 250.0;
    run();
    expect_vrx(expected_left, expected_right);
    EXPECT_DOUBLE_EQ(status_.at(0).at("tl_cmd_n").get<double>(), 12.0);
    EXPECT_DOUBLE_EQ(status_.at(0).at("tr_cmd_n").get<double>(), -18.0);
    fake_->reported_ms = 1.0;
    run();
    EXPECT_DOUBLE_EQ(fake_->solve_entry_anchor(0), expected_left);
    EXPECT_DOUBLE_EQ(fake_->solve_entry_anchor(1), expected_right);
  }
}

TEST_F(DeadlineControl, RcTimeoutRepeatsTheSamePwmAndKeepsMappedAnchor)
{
  MpcControllerNodeTestAccess::rc(*controller_);
  fake_->candidate = {8.0, 20.0};
  run(true);
  ASSERT_EQ(rc_.size(), 1u);
  const auto original = rc_.at(0);
  EXPECT_EQ(original.channels[0], 1404u);
  EXPECT_EQ(original.channels[2], 1612u);
  const Eigen::Vector2d anchor = fake_->anchor;
  EXPECT_DOUBLE_EQ(anchor(0), 1.0);
  EXPECT_DOUBLE_EQ(anchor(1), 13.0);
  fake_->candidate = {22.0, -18.0};
  fake_->reported_ms = 250.0;
  run(true);
  ASSERT_EQ(rc_.size(), 1u);
  EXPECT_EQ(rc_.at(0).channels, original.channels);
  EXPECT_TRUE(fake_->anchor.isApprox(anchor));
  EXPECT_DOUBLE_EQ(status_.at(0).at("tl_cmd_n").get<double>(), 8.0);
  EXPECT_DOUBLE_EQ(status_.at(0).at("tr_cmd_n").get<double>(), 20.0);
}

TEST_F(DeadlineControl, HeadingWarmstartResetRestoresThePublishedAnchorBeforeSolve)
{
  MpcControllerNodeTestAccess::vrx(*controller_, 0.5);
  run();
  expect_vrx(4.0, 6.0);
  const auto event_start = fake_->events.size();
  MpcControllerNodeTestAccess::heading(*controller_, std::acos(-1.0));
  fake_->candidate = {10.0, 14.0};
  run();
  EXPECT_EQ(fake_->reset_count, 1);
  EXPECT_DOUBLE_EQ(fake_->solve_entry_anchor(0), 4.0);
  EXPECT_DOUBLE_EQ(fake_->solve_entry_anchor(1), 6.0);
  ASSERT_GE(fake_->events.size(), event_start + 3);
  EXPECT_EQ(fake_->events[event_start], "reset");
  EXPECT_EQ(fake_->events[event_start + 1], "set_applied");
  EXPECT_EQ(fake_->events[event_start + 2], "solve");
  expect_vrx(5.0, 7.0);
  EXPECT_TRUE(status_.at(0).at("success").get<bool>());
}

TEST_F(DeadlineControl, StandbyInvalidatesCachedCommandBeforeNextTimeout)
{
  run();
  left_.clear(); right_.clear(); status_.clear();
  MpcControllerNodeTestAccess::standby(*controller_);
  drain();
  EXPECT_DOUBLE_EQ(left_.at(0), 0.0);
  EXPECT_DOUBLE_EQ(right_.at(0), 0.0);
  EXPECT_EQ(status_.at(0).at("state").get<std::string>(), "STANDBY");
  fake_->candidate = {22.0, -18.0};
  fake_->reported_ms = 250.0;
  run();
  expect_vrx(0.0, 0.0);
  EXPECT_EQ(status_.at(0).at("fail_count").get<int>(), 1);
}

TEST_F(DeadlineControl, OrdinaryTimelyBackendFailureRetainsExistingFallbackBehavior)
{
  run();
  fake_->success = false;
  fake_->candidate = {6.0, 7.0};
  run();
  expect_vrx(6.0, 7.0);
  EXPECT_FALSE(status_.at(0).at("success").get<bool>());
  EXPECT_FALSE(status_.at(0).at("deadline_miss").get<bool>());
  EXPECT_EQ(fake_->reset_count, 0);
  EXPECT_EQ(status_.at(0).at("error").get<std::string>(), "backend_failure");
  EXPECT_EQ(status_.at(0).at("control_source").get<std::string>(), "backend_fallback");
}

TEST_F(DeadlineControl, BackendFailureWithLateTimingStillRejectsItsReturnedControl)
{
  run();
  fake_->success = false;
  fake_->reported_ms = 250.0;
  fake_->candidate = {22.0, -18.0};
  run();
  expect_vrx(8.0, 12.0);
  EXPECT_TRUE(status_.at(0).at("deadline_miss").get<bool>());
  EXPECT_EQ(status_.at(0).at("control_source").get<std::string>(), "repeat_last_command");
  EXPECT_EQ(fake_->reset_count, 1);
}

TEST_F(DeadlineControl, ShutdownDuringSolveCannotRepublishOrReviveCachedControl)
{
  run();
  left_.clear(); right_.clear(); status_.clear(); trajectories_ = 0;
  fake_->candidate = {22.0, -18.0};
  fake_->block = true;
  std::thread solving([this]() {MpcControllerNodeTestAccess::run(*controller_);});
  bool entered = false;
  {
    std::unique_lock<std::mutex> lock(fake_->gate_mutex);
    entered = fake_->gate.wait_for(lock, 2s, [this]() {return fake_->entered;});
  }
  EXPECT_TRUE(entered);
  controller_->safe_shutdown();
  {
    std::lock_guard<std::mutex> lock(fake_->gate_mutex);
    fake_->released = true;
  }
  fake_->gate.notify_all();
  solving.join();
  drain();
  EXPECT_DOUBLE_EQ(left_.at(0), 0.0);
  EXPECT_DOUBLE_EQ(right_.at(0), 0.0);
  EXPECT_EQ(status_.at(0).at("state").get<std::string>(), "STANDBY");
  EXPECT_EQ(status_.at(0).at("standby_reason").get<std::string>(), "node_shutdown");
  EXPECT_EQ(trajectories_, 0u);
  EXPECT_FALSE(MpcControllerNodeTestAccess::has_history(*controller_));
  const auto event_count = fake_->events.size();
  MpcControllerNodeTestAccess::run(*controller_);
  executor_.spin_some();
  EXPECT_EQ(fake_->events.size(), event_count);
  EXPECT_EQ(left_.size(), 1u);
  EXPECT_EQ(right_.size(), 1u);
}

TEST_F(DeadlineControl, InvalidBackendTimingCannotPublishItsCandidate)
{
  for (const double invalid : {std::numeric_limits<double>::quiet_NaN(),
      std::numeric_limits<double>::infinity(), -1.0})
  {
    fake_->candidate = {8.0, 12.0};
    fake_->reported_ms = 1.0;
    run();
    fake_->candidate = {22.0, -18.0};
    fake_->reported_ms = invalid;
    run();
    expect_vrx(8.0, 12.0);
    EXPECT_FALSE(status_.at(0).at("success").get<bool>());
    EXPECT_EQ(status_.at(0).at("control_source").get<std::string>(), "repeat_last_command");
    EXPECT_EQ(trajectories_, 0u);
  }
}

TEST_F(DeadlineControl, DeadlineBoundaryAndDisabledBudgetRemainCompatible)
{
  SolveInfo info;
  info.success = true;
  info.solve_time_ms = 200.0;
  EXPECT_FALSE(MpcControllerNodeTestAccess::enforce(*controller_, info, 200.0, 200.0));
  EXPECT_TRUE(info.success);
  EXPECT_TRUE(MpcControllerNodeTestAccess::enforce(*controller_, info, 200.001, 200.0));
  EXPECT_FALSE(info.success);
  for (const double budget : {0.0, -1.0}) {
    SCOPED_TRACE(budget);
    info = SolveInfo{};
    info.success = true;
    info.solve_time_ms = 300.0;
    EXPECT_FALSE(MpcControllerNodeTestAccess::enforce(*controller_, info, 300.0, budget));
    EXPECT_TRUE(info.success);
  }
}

TEST_F(DeadlineControl, InvalidTimingFailsClosedEvenWhenBudgetIsDisabled)
{
  const double nan = std::numeric_limits<double>::quiet_NaN();
  const double inf = std::numeric_limits<double>::infinity();
  for (const double invalid : {nan, inf, -1.0}) {
    for (const double budget : {0.0, 200.0}) {
      SolveInfo info;
      info.success = true;
      info.solve_time_ms = invalid;
      EXPECT_TRUE(MpcControllerNodeTestAccess::enforce(*controller_, info, 1.0, budget));
      EXPECT_FALSE(info.success);
      info = SolveInfo{};
      info.success = true;
      info.solve_time_ms = 1.0;
      EXPECT_TRUE(MpcControllerNodeTestAccess::enforce(*controller_, info, invalid, budget));
      EXPECT_FALSE(info.success);
    }
  }
  for (const double invalid_budget : {nan, inf}) {
    SolveInfo info;
    info.success = true;
    info.solve_time_ms = 1.0;
    EXPECT_TRUE(MpcControllerNodeTestAccess::enforce(*controller_, info, 1.0, invalid_budget));
    EXPECT_FALSE(info.success);
  }
}

}  // namespace
