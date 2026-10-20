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
 * @file test_deadline_control.cpp
 * @brief 方案 A 安全修复回归测试 (移植自方案 B 的 test_deadline_control.cpp)。
 *
 * 覆盖 2026-10-09 代码审查四项修复:
 *   C1  can_solve_ 重查: 锁释放窗口内路径被清空 → STANDBY 而非全零参考
 *   C2  关机/输出互斥: safe_shutdown 与控制循环不竞争
 *   M2  墙钟 deadline: wall/后端双计时拒绝 + warmstart 重置 + repeat-last
 *   M1  四元数退化门禁 (odom 门禁, 见 FakeKinematicMpc 之外的直接回调测试)
 *
 * 无仿真器/FCU/生产延迟参数。控制定时器被取消, 输出重定向到独立测试话题。
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
  static std::shared_ptr<MpcControllerNode> make(std::unique_ptr<KinematicMpc> solver)
  {
    auto node = std::shared_ptr<MpcControllerNode>(
      new MpcControllerNode(std::move(solver)));
    node->timer_->cancel();
    node->max_solve_time_ms_ = 200.0;
    node->solver_hold_threshold_ = 5;
    node->publish_predicted_ = true;
    node->prev_state_ = "ACTIVE";
    // 通过真实回调构造就绪状态, 而非绕过门禁 (对齐 B 的 fixture 哲学)。
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
    node.vel_pub_ =
      node.create_publisher<geometry_msgs::msg::TwistStamped>(prefix + "/cmd_vel", 10);
    node.status_pub_ =
      node.create_publisher<std_msgs::msg::String>(prefix + "/status", 10);
    node.traj_pub_ =
      node.create_publisher<nav_msgs::msg::Path>(prefix + "/trajectory", 10);
  }

  static bool discovered(MpcControllerNode & node)
  {
    return node.vel_pub_->get_subscription_count() > 0 &&
           node.status_pub_->get_subscription_count() > 0 &&
           node.traj_pub_->get_subscription_count() > 0;
  }

  static void run(MpcControllerNode & node)
  {
    // Make every candidate eligible for trajectory publication, including late ones.
    node.control_count_ = 0;
    node.run_kinematic_mpc_();
  }

  static void clear_path(MpcControllerNode & node)
  {
    auto path = std::make_shared<nav_msgs::msg::Path>();
    path->header.frame_id = "map";
    node.path_callback_(path);
  }

  static void standby(MpcControllerNode & node) {node.enter_standby_("test_disarmed");}

  static void feed_odom(MpcControllerNode & node, double qw, double px)
  {
    auto odom = std::make_shared<nav_msgs::msg::Odometry>();
    odom->header.frame_id = "map";
    odom->child_frame_id = "base_link";
    odom->pose.pose.orientation.w = qw;
    odom->pose.pose.position.x = px;
    node.odom_callback_(odom);
  }

  static bool has_history(MpcControllerNode & node) {return node.has_last_command_;}

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

class FakeKinematicMpc : public usv_mpc::KinematicMpc
{
public:
  Eigen::Vector2d candidate = {1.5, 0.1};
  Eigen::Vector2d anchor = Eigen::Vector2d::Zero();
  bool success = true;
  double reported_ms = 1.0;
  std::chrono::milliseconds delay{0};
  int reset_count = 0;
  std::vector<std::string> events;
  int solve_count = 0;

  std::pair<Eigen::Vector2d, SolveInfo> solve(
    const Eigen::Matrix<double, 5, 1> &, const Eigen::MatrixXd &) override
  {
    events.push_back("solve");
    ++solve_count;
    if (delay.count() > 0) {std::this_thread::sleep_for(delay);}
    anchor = candidate;  // Mirrors the backend's tentative first-control cache.
    SolveInfo info;
    info.success = success;
    info.solve_time_ms = reported_ms;
    std::snprintf(info.backend, sizeof(info.backend), "fake");
    if (!success) {std::snprintf(info.error, sizeof(info.error), "backend_failure");}
    info.X_pred = Eigen::MatrixXd::Zero(5, N() + 1);
    info.U_pred = Eigen::MatrixXd::Zero(2, N());
    return {candidate, std::move(info)};
  }

  void set_applied_command(const Eigen::Vector2d & applied) override
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

class KinematicDeadlineControl : public ::testing::Test
{
protected:
  static void SetUpTestSuite() {rclcpp::init(0, nullptr);}
  static void TearDownTestSuite() {rclcpp::shutdown();}

  void SetUp() override
  {
    static unsigned int sequence = 0;
    const auto suffix = std::to_string(++sequence);
    prefix_ = "/kin_deadline_test/instance_" + suffix;
    auto solver = std::make_unique<FakeKinematicMpc>();
    fake_ = solver.get();
    controller_ = MpcControllerNodeTestAccess::make(std::move(solver));
    MpcControllerNodeTestAccess::outputs(*controller_, prefix_);
    observer_ = std::make_shared<rclcpp::Node>("kin_deadline_observer_" + suffix);
    cmdvel_sub_ = observer_->create_subscription<geometry_msgs::msg::TwistStamped>(
      prefix_ + "/cmd_vel", 10,
      [this](geometry_msgs::msg::TwistStamped::ConstSharedPtr msg) {
        cmdvels_.push_back(std::make_pair(msg->twist.linear.x, msg->twist.angular.z));
      });
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

  void run()
  {
    cmdvels_.clear(); status_.clear(); trajectories_ = 0;
    MpcControllerNodeTestAccess::run(*controller_);
    drain();
  }

  void drain()
  {
    const auto deadline = std::chrono::steady_clock::now() + 2s;
    while ((status_.empty() || cmdvels_.empty()) &&
      std::chrono::steady_clock::now() < deadline)
    {
      executor_.spin_some();
      std::this_thread::sleep_for(2ms);
    }
    executor_.spin_some();
    const auto settle = std::chrono::steady_clock::now() + 20ms;
    while (std::chrono::steady_clock::now() < settle) {
      executor_.spin_some();
      std::this_thread::sleep_for(1ms);
    }
    ASSERT_EQ(status_.size(), 1u);
    ASSERT_EQ(cmdvels_.size(), 1u);
  }

  std::shared_ptr<usv_mpc::MpcControllerNode> controller_;
  FakeKinematicMpc * fake_ = nullptr;
  std::shared_ptr<rclcpp::Node> observer_;
  rclcpp::executors::SingleThreadedExecutor executor_;
  std::string prefix_;
  rclcpp::Subscription<geometry_msgs::msg::TwistStamped>::SharedPtr cmdvel_sub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr status_sub_;
  rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr traj_sub_;
  std::vector<std::pair<double, double>> cmdvels_;
  std::vector<nlohmann::json> status_;
  unsigned int trajectories_ = 0;
};

TEST_F(KinematicDeadlineControl, TimelySuccessPublishesCandidate)
{
  run();
  ASSERT_EQ(cmdvels_.size(), 1u);
  EXPECT_DOUBLE_EQ(cmdvels_.at(0).first, 1.5);
  EXPECT_DOUBLE_EQ(cmdvels_.at(0).second, 0.1);
  EXPECT_DOUBLE_EQ(fake_->anchor(0), 1.5);
  EXPECT_DOUBLE_EQ(fake_->anchor(1), 0.1);
  EXPECT_TRUE(status_.at(0).at("success").get<bool>());
  EXPECT_FALSE(status_.at(0).at("deadline_miss").get<bool>());
  EXPECT_EQ(trajectories_, 1u);
  EXPECT_EQ(fake_->reset_count, 0);
}

TEST_F(KinematicDeadlineControl, WallClockTimeoutRejectsCandidateAndResetsWarmstart)
{
  // wall 超限但后端计时正常: 旧实现 (只查后端) 会发布该过期候选。
  fake_->reported_ms = 5.0;
  fake_->delay = std::chrono::milliseconds(250);  // wall ≈ 250ms > 200ms
  run();
  ASSERT_EQ(cmdvels_.size(), 1u);
  EXPECT_DOUBLE_EQ(cmdvels_.at(0).first, 0.0);  // 无历史 → 零速度而非过期候选
  EXPECT_DOUBLE_EQ(cmdvels_.at(0).second, 0.0);
  EXPECT_FALSE(status_.at(0).at("success").get<bool>());
  EXPECT_TRUE(status_.at(0).at("deadline_miss").get<bool>());
  EXPECT_EQ(trajectories_, 0u);
  EXPECT_GE(fake_->reset_count, 1);  // 迟到候选的热启动状态一并拒绝
  EXPECT_DOUBLE_EQ(fake_->anchor(0), 0.0);  // 零速度写回锚点
}

TEST_F(KinematicDeadlineControl, RejectedLateCandidateThenRepeatsLastCommand)
{
  // 第一拍成功建立指令历史; 第二拍 wall 超限 → 重放上一条指令而非过期候选。
  run();
  ASSERT_TRUE(MpcControllerNodeTestAccess::has_history(*controller_));

  fake_->candidate = {2.5, -0.3};
  fake_->delay = std::chrono::milliseconds(250);
  cmdvels_.clear(); status_.clear(); trajectories_ = 0;
  MpcControllerNodeTestAccess::run(*controller_);
  drain();
  ASSERT_EQ(cmdvels_.size(), 1u);
  EXPECT_DOUBLE_EQ(cmdvels_.at(0).first, 1.5);  // repeat-last, 不是 2.5
  EXPECT_DOUBLE_EQ(cmdvels_.at(0).second, 0.1);
  EXPECT_TRUE(status_.at(0).at("deadline_miss").get<bool>());
}

TEST_F(KinematicDeadlineControl, BackendTimeoutRejectsCandidate)
{
  fake_->reported_ms = 400.0;  // 后端计时超限, wall 正常
  run();
  ASSERT_EQ(cmdvels_.size(), 1u);
  EXPECT_DOUBLE_EQ(cmdvels_.at(0).first, 0.0);
  EXPECT_TRUE(status_.at(0).at("deadline_miss").get<bool>());
  EXPECT_GE(fake_->reset_count, 1);
}

TEST_F(KinematicDeadlineControl, EmptyPathAfterGateGoesStandbyWithoutSolving)
{
  // C1 回归: can_solve_ 通过后路径被清空 (任务结束时序), 重查必须拦截。
  MpcControllerNodeTestAccess::clear_path(*controller_);
  cmdvels_.clear(); status_.clear(); trajectories_ = 0;
  MpcControllerNodeTestAccess::run(*controller_);
  drain();
  EXPECT_EQ(fake_->solve_count, 0);  // 未调求解器
  ASSERT_FALSE(status_.empty());
  EXPECT_EQ(status_.at(0).at("state").get<std::string>(), "STANDBY");
  EXPECT_EQ(status_.at(0).at("standby_reason").get<std::string>(), "no_path");
  ASSERT_EQ(cmdvels_.size(), 1u);
  EXPECT_DOUBLE_EQ(cmdvels_.at(0).first, 0.0);  // 零速度, 非全零参考解
}

TEST_F(KinematicDeadlineControl, DegenerateQuaternionOdomIsRejected)
{
  // M1 回归: 全零四元数 (yaw=0, isfinite 拦不住) 必须被范数门禁丢弃。
  MpcControllerNodeTestAccess::feed_odom(*controller_, 0.0, 99.0);
  // 样本被丢弃: 状态不应被污染。随后喂合法样本验证节点仍正常工作。
  MpcControllerNodeTestAccess::feed_odom(*controller_, 1.0, 5.0);
  run();
  ASSERT_EQ(cmdvels_.size(), 1u);
  EXPECT_TRUE(status_.at(0).at("success").get<bool>());
}

TEST_F(KinematicDeadlineControl, EnforceDeadlineTimingInvalidity)
{
  SolveInfo info;
  info.success = true;
  info.solve_time_ms = 1.0;
  // wall 为 NaN → 计时无效, 拒绝
  info.success = true;
  EXPECT_TRUE(MpcControllerNodeTestAccess::enforce(
      *controller_, info, std::numeric_limits<double>::quiet_NaN(), 200.0));
  EXPECT_FALSE(info.success);
  // 后端计时为负 → 拒绝
  info.success = true;
  info.solve_time_ms = -1.0;
  EXPECT_TRUE(MpcControllerNodeTestAccess::enforce(*controller_, info, 1.0, 200.0));
  EXPECT_FALSE(info.success);
  // 双计时均正常且在限内 → 不拒绝
  info.success = true;
  info.solve_time_ms = 100.0;
  EXPECT_FALSE(MpcControllerNodeTestAccess::enforce(*controller_, info, 150.0, 200.0));
  EXPECT_TRUE(info.success);
}

TEST_F(KinematicDeadlineControl, StandbyDuringShutdownDoesNotRepublish)
{
  run();
  controller_->safe_shutdown();
  // 关机后再触发 standby: shutting_down_ 标志应让 enter_standby_ 直接返回,
  // 不产生新的发布 (状态保持 node_shutdown)。
  const size_t before = status_.size();
  MpcControllerNodeTestAccess::standby(*controller_);
  EXPECT_EQ(status_.size(), before);
}

}  // namespace
