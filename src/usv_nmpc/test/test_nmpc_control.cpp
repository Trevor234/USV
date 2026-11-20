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
 * @file test_nmpc_control.cpp
 * @brief 方案 B 节点级控制逻辑回归测试 (终点 STANDBY 门禁、防倒吸、起步前向辅助)。
 */

#include <gtest/gtest.h>

#include <chrono>
#include <cmath>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "usv_nmpc/mpc_node.hpp"

namespace usv_mpc {

class DynamicMpcNodeTestAccess {
 public:
  static std::shared_ptr<MpcControllerNode> make(std::unique_ptr<DynamicMpc> solver) {
    auto node = std::shared_ptr<MpcControllerNode>(
        new MpcControllerNode(std::move(solver)));
    node->timer_->cancel();
    node->max_solve_time_ms_ = 200.0;
    node->solver_hold_threshold_ = 5;
    node->publish_predicted_ = true;
    node->prev_state_ = "ACTIVE";
    node->require_fcu_state_ = false;
    node->odom_timeout_s_ = 0.0;
    node->dyn_T_max_ = 30.0;
    node->dyn_T_min_ = -30.0;
    auto state = std::make_shared<nav_msgs::msg::Odometry>();
    state->header.frame_id = "map";
    state->child_frame_id = "base_link";
    state->pose.pose.orientation.w = 1.0;
    node->odom_callback_(state);
    feed_path(*node, 15, 1.0);
    return node;
  }

  static void outputs(MpcControllerNode& node, const std::string& prefix) {
    node.rc_pub_ =
        node.create_publisher<mavros_msgs::msg::OverrideRCIn>(prefix + "/rc_override", 10);
    node.status_pub_ =
        node.create_publisher<std_msgs::msg::String>(prefix + "/status", 10);
    node.traj_pub_ =
        node.create_publisher<nav_msgs::msg::Path>(prefix + "/trajectory", 10);
  }

  static bool discovered(MpcControllerNode& node) {
    return node.rc_pub_->get_subscription_count() > 0 &&
           node.status_pub_->get_subscription_count() > 0 &&
           node.traj_pub_->get_subscription_count() > 0;
  }

  static void run(MpcControllerNode& node) {
    node.control_count_ = 0;
    node.run_dynamic_mpc_();
  }

  static void feed_odom(MpcControllerNode& node, double px, double py, double yaw, double u = 0.0) {
    auto odom = std::make_shared<nav_msgs::msg::Odometry>();
    odom->header.frame_id = "map";
    odom->child_frame_id = "base_link";
    odom->pose.pose.position.x = px;
    odom->pose.pose.position.y = py;
    odom->pose.pose.orientation.z = std::sin(0.5 * yaw);
    odom->pose.pose.orientation.w = std::cos(0.5 * yaw);
    odom->twist.twist.linear.x = u;
    node.odom_callback_(odom);
  }

  static void feed_path(MpcControllerNode& node, int count, double step = 1.0) {
    auto path = std::make_shared<nav_msgs::msg::Path>();
    path->header.frame_id = "map";
    for (int i = 0; i < count; ++i) {
      geometry_msgs::msg::PoseStamped pose;
      pose.pose.position.x = static_cast<double>(i) * step;
      pose.pose.orientation.w = 1.0;
      path->poses.push_back(pose);
    }
    node.path_callback_(path);
  }

  static int progress_index(const MpcControllerNode& node) { return node.progress_index_; }
  static bool mission_completed(const MpcControllerNode& node) { return node.mission_completed_; }
};

}  // namespace usv_mpc

namespace {

using usv_mpc::DynamicMpcNodeTestAccess;
using usv_mpc::SolveInfo;
using namespace std::chrono_literals;

class FakeDynamicMpc : public usv_mpc::DynamicMpc {
 public:
  Eigen::Vector2d candidate = {22.0, -25.0};
  Eigen::Vector2d anchor = Eigen::Vector2d::Zero();
  Eigen::MatrixXd last_ref;
  int solve_count = 0;

  std::pair<Eigen::Vector2d, SolveInfo> solve(
      const usv_mpc::Vector6d&, const Eigen::MatrixXd& reference) override {
    ++solve_count;
    last_ref = reference;
    SolveInfo info;
    info.success = true;
    info.solve_time_ms = 1.0;
    std::snprintf(info.backend, sizeof(info.backend), "fake");
    info.X_pred = Eigen::MatrixXd::Zero(6, N() + 1);
    info.U_pred = Eigen::MatrixXd::Zero(2, N());
    return {candidate, std::move(info)};
  }

  void set_applied_control(const Eigen::Vector2d& applied) override { anchor = applied; }
  void reset_warmstart() override { anchor.setZero(); }
  Eigen::MatrixXd get_predicted_trajectory() const override { return {}; }
  int N() const override { return 4; }
  double dt() const override { return 0.2; }
  const char* backend() const override { return "fake"; }
};

class DynamicNmpcNodeTest : public ::testing::Test {
 protected:
  static void SetUpTestSuite() { rclcpp::init(0, nullptr); }
  static void TearDownTestSuite() { rclcpp::shutdown(); }

  void SetUp() override {
    static unsigned int seq = 0;
    const auto suffix = std::to_string(++seq);
    prefix_ = "/nmpc_node_test/instance_" + suffix;
    auto solver = std::make_unique<FakeDynamicMpc>();
    fake_ = solver.get();
    controller_ = DynamicMpcNodeTestAccess::make(std::move(solver));
    DynamicMpcNodeTestAccess::outputs(*controller_, prefix_);
    observer_ = std::make_shared<rclcpp::Node>("nmpc_observer_" + suffix);
    rc_sub_ = observer_->create_subscription<mavros_msgs::msg::OverrideRCIn>(
        prefix_ + "/rc_override", 10,
        [this](mavros_msgs::msg::OverrideRCIn::ConstSharedPtr msg) {
          rcs_.push_back({msg->channels[0], msg->channels[2]});
        });
    status_sub_ = observer_->create_subscription<std_msgs::msg::String>(
        prefix_ + "/status", 10,
        [this](std_msgs::msg::String::ConstSharedPtr msg) {
          status_.push_back(nlohmann::json::parse(msg->data));
        });
    traj_sub_ = observer_->create_subscription<nav_msgs::msg::Path>(
        prefix_ + "/trajectory", 10,
        [this](nav_msgs::msg::Path::ConstSharedPtr) { ++trajectories_; });
    executor_.add_node(observer_);
    const auto deadline = std::chrono::steady_clock::now() + 3s;
    while (!DynamicMpcNodeTestAccess::discovered(*controller_) &&
           std::chrono::steady_clock::now() < deadline) {
      executor_.spin_some();
      std::this_thread::sleep_for(5ms);
    }
    ASSERT_TRUE(DynamicMpcNodeTestAccess::discovered(*controller_));
  }

  void TearDown() override {
    executor_.remove_node(observer_);
    controller_.reset();
    observer_.reset();
  }

  void run() {
    rcs_.clear();
    status_.clear();
    trajectories_ = 0;
    DynamicMpcNodeTestAccess::run(*controller_);
    const auto deadline = std::chrono::steady_clock::now() + 2s;
    while ((status_.empty() || rcs_.empty()) &&
           std::chrono::steady_clock::now() < deadline) {
      executor_.spin_some();
      std::this_thread::sleep_for(2ms);
    }
    executor_.spin_some();
    ASSERT_EQ(status_.size(), 1u);
    ASSERT_EQ(rcs_.size(), 1u);
  }

  std::shared_ptr<usv_mpc::MpcControllerNode> controller_;
  FakeDynamicMpc* fake_ = nullptr;
  std::shared_ptr<rclcpp::Node> observer_;
  rclcpp::executors::SingleThreadedExecutor executor_;
  std::string prefix_;
  rclcpp::Subscription<mavros_msgs::msg::OverrideRCIn>::SharedPtr rc_sub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr status_sub_;
  rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr traj_sub_;
  std::vector<std::pair<int, int>> rcs_;
  std::vector<nlohmann::json> status_;
  unsigned int trajectories_ = 0;
};

TEST_F(DynamicNmpcNodeTest, TransitionsToStandbyOnMissionComplete) {
  DynamicMpcNodeTestAccess::feed_odom(*controller_, 3.0, 0.0, 0.0, 0.5);
  run();
  EXPECT_FALSE(DynamicMpcNodeTestAccess::mission_completed(*controller_));
  const int prog_mid = DynamicMpcNodeTestAccess::progress_index(*controller_);
  EXPECT_GT(prog_mid, 0);

  // 同几何路径 1 Hz 重发不应重置 progress_index_
  DynamicMpcNodeTestAccess::feed_path(*controller_, 15, 1.0);
  EXPECT_EQ(DynamicMpcNodeTestAccess::progress_index(*controller_), prog_mid);

  // 推进到末段且距终点 < 2.0 m (path[14]=(14,0), x=12.5 => d_goal=1.5 < 2.0)
  DynamicMpcNodeTestAccess::feed_odom(*controller_, 8.5, 0.0, 0.0, 0.5);
  run();
  DynamicMpcNodeTestAccess::feed_odom(*controller_, 12.5, 0.0, 0.0, 0.5);
  const int solves_before = fake_->solve_count;
  run();
  EXPECT_EQ(fake_->solve_count, solves_before);
  EXPECT_TRUE(DynamicMpcNodeTestAccess::mission_completed(*controller_));
  EXPECT_EQ(status_.at(0).at("state").get<std::string>(), "STANDBY");
  EXPECT_EQ(status_.at(0).at("standby_reason").get<std::string>(), "mission_complete");
  EXPECT_EQ(rcs_.at(0).first, 1500);
  EXPECT_EQ(rcs_.at(0).second, 1500);
}

TEST_F(DynamicNmpcNodeTest, LargeHeadingStartupProducesPositiveNetThrust) {
  // 船处于起步位置但航向偏离路径 100° (path yaw=0, boat yaw=-1.75 rad)
  DynamicMpcNodeTestAccess::feed_odom(*controller_, 0.0, 0.0, -1.75, 0.0);
  fake_->candidate = {22.0, -25.0};
  run();
  EXPECT_EQ(status_.at(0).at("state").get<std::string>(), "ACTIVE");
  // 执行层大偏角前向辅助生效: throttle_pwm 跳过 1600 死区, tl_cmd_n + tr_cmd_n >= 8 N
  EXPECT_GE(rcs_.at(0).second, 1600);
  const double tl_cmd = status_.at(0).at("tl_cmd_n").get<double>();
  const double tr_cmd = status_.at(0).at("tr_cmd_n").get<double>();
  EXPECT_GE(tl_cmd + tr_cmd, 8.0 - 1e-9);
  EXPECT_GE(tr_cmd, -5.0 - 1e-9);
  // 参考层航向渐进引导 + 参考速度 >= 0.4 m/s
  EXPECT_GE(fake_->last_ref(3, 0), 0.4 - 1e-9);
}

}  // namespace
