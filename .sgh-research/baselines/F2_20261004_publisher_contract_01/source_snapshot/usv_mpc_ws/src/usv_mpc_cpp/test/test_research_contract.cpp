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

// Exercise the node's real observation/publication paths with test-only topics.

#include <sys/resource.h>

#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <rcl/publisher.h>
#include <gtest/gtest.h>
#include <nlohmann/json.hpp>

#include "usv_mpc_cpp/mpc_node.hpp"

namespace usv_mpc
{
class MpcControllerNodeTestAccess
{
public:
  static std::shared_ptr<MpcControllerNode> make(std::unique_ptr<DynamicMpc> solver)
  {
    auto node = std::shared_ptr<MpcControllerNode>(new MpcControllerNode(std::move(solver)));
    node->timer_->cancel();
    node->output_mode_ = "vrx_thrust";
    node->vrx_thrust_scale_ = 1.0;
    node->vrx_thrust_cmd_max_ = 25.0;
    node->dyn_T_min_ = -25.0;
    node->dyn_T_max_ = 25.0;
    node->max_solve_time_ms_ = 200.0;
    node->require_fcu_state_ = false;
    node->odom_timeout_s_ = 0.0;
    node->publish_predicted_ = false;
    node->prev_state_ = "ACTIVE";
    node->path_received_ = true;
    node->reference_path_ = {{{0.0, 0.0, 0.0}}, {{5.0, 0.0, 0.0}}, {{10.0, 0.0, 0.0}}};
    return node;
  }

  static void outputs(MpcControllerNode & node, const std::string & prefix)
  {
    node.vrx_left_pub_ = node.create_publisher<std_msgs::msg::Float64>(prefix + "/left", 100);
    node.vrx_right_pub_ = node.create_publisher<std_msgs::msg::Float64>(prefix + "/right", 100);
    node.status_pub_ = node.create_publisher<std_msgs::msg::String>(prefix + "/status", 100);
  }

  static bool discovered(const MpcControllerNode & node)
  {
    return node.vrx_left_pub_->get_subscription_count() > 0 &&
           node.vrx_right_pub_->get_subscription_count() > 0;
  }

  static void logging(MpcControllerNode & node, const std::string & dir, const std::string & run)
  {
    node.set_parameter(rclcpp::Parameter("research_expected_pose_frame", "map"));
    node.set_parameter(rclcpp::Parameter("research_expected_child_frame", "base_link"));
    node.set_parameter(rclcpp::Parameter("research_frame_contract_verified", true));
    node.research_ = std::make_unique<ResearchLogger>(node, dir, run, "F1_test",
        std::string(64, 'a'));
    node.research_->arm();
  }

  static void stop(MpcControllerNode & node, bool normal = true)
  {
    if (node.research_) {node.research_->stop(normal);}
  }

  static void clock(MpcControllerNode & node, int sec)
  {
    auto msg = std::make_shared<rosgraph_msgs::msg::Clock>();
    msg->clock.sec = sec;
    node.research_clock_(msg);
  }

  static void odom(MpcControllerNode & node, const nav_msgs::msg::Odometry & msg)
  {
    node.odom_callback_(std::make_shared<nav_msgs::msg::Odometry>(msg));
  }

  static void imu(MpcControllerNode & node, int sec, double r)
  {
    auto msg = std::make_shared<sensor_msgs::msg::Imu>();
    msg->header.stamp.sec = sec;
    msg->angular_velocity.z = r;
    node.imu_callback_(msg);
  }

  static void run(MpcControllerNode & node) {node.control_loop_();}

  static void reset_history(MpcControllerNode & node)
  {
    node.has_last_command_ = false;
    node.solver_fail_count_ = 0;
    node.last_commanded_thrust_.setZero();
    node.last_applied_thrust_.setZero();
    node.mpc_->reset_warmstart();
    node.prev_state_ = "ACTIVE";
    node.control_count_ = 0;
  }

  static void standby(MpcControllerNode & node) {node.enter_standby_("test_standby");}

  static void invalidate_right_publisher(MpcControllerNode & node)
  {
    const auto result = rcl_publisher_fini(node.vrx_right_pub_->get_publisher_handle().get(),
      node.get_node_base_interface()->get_rcl_node_handle());
    if (result != RCL_RET_OK) {throw std::runtime_error("test failed to invalidate publisher");}
  }

  static void publish(MpcControllerNode & node)
  {
    node.publish_dynamic_output_(Eigen::Vector2d(8.0, 12.0));
  }

  static uint64_t enqueue_state(MpcControllerNode & node, const ResearchState & state)
  {
    return node.research_->enqueue(state, "state");
  }
};
}  // namespace usv_mpc

namespace
{
using usv_mpc::MpcControllerNodeTestAccess;
using namespace std::chrono_literals;

class ContractSolver : public usv_mpc::DynamicMpc
{
public:
  Eigen::Vector2d candidate{8.0, 12.0};
  usv_mpc::Vector6d input = usv_mpc::Vector6d::Zero();
  double backend_ms = 1.0;
  std::chrono::milliseconds delay{0};
  bool block = false, entered = false, released = false;
  std::mutex gate_mutex;
  std::condition_variable gate;

  std::pair<Eigen::Vector2d, usv_mpc::SolveInfo> solve(
    const usv_mpc::Vector6d & state, const Eigen::MatrixXd &) override
  {
    input = state;
    if (block) {
      std::unique_lock<std::mutex> lock(gate_mutex);
      entered = true;
      gate.notify_all();
      gate.wait(lock, [this]() {return released;});
    }
    std::this_thread::sleep_for(delay);
    usv_mpc::SolveInfo info;
    info.success = true;
    info.solve_time_ms = backend_ms;
    std::snprintf(info.backend, sizeof(info.backend), "contract_fake");
    return {candidate, info};
  }
  void set_applied_control(const Eigen::Vector2d &) override {}
  void reset_warmstart() override {}
  Eigen::MatrixXd get_predicted_trajectory() const override {return {};}
  int N() const override {return 2;}
  double dt() const override {return 0.2;}
  const char * backend() const override {return "contract_fake";}
};

nav_msgs::msg::Odometry odom(int sec = 10, double yaw = 0.0, double r = 0.3)
{
  nav_msgs::msg::Odometry msg;
  msg.header.frame_id = "map";
  msg.child_frame_id = "base_link";
  msg.header.stamp.sec = sec;
  msg.pose.pose.position.x = 2.0;
  msg.pose.pose.position.y = 3.0;
  msg.pose.pose.orientation.z = std::sin(yaw / 2.0);
  msg.pose.pose.orientation.w = std::cos(yaw / 2.0);
  msg.twist.twist.linear.x = 4.0;
  msg.twist.twist.linear.y = 0.5;
  msg.twist.twist.angular.z = r;
  return msg;
}

class ResearchContract : public ::testing::Test
{
protected:
  static void SetUpTestSuite() {rclcpp::init(0, nullptr);}
  static void TearDownTestSuite() {rclcpp::shutdown();}
  void SetUp() override
  {
    static unsigned sequence = 0;
    const std::string suffix = std::to_string(++sequence);
    run_id_ = "contract_test_" + suffix;
    prefix_ = "/research_contract_test/case_" + suffix;
    output_ = std::filesystem::temp_directory_path() /
      (run_id_ + "_" + std::to_string(usv_mpc::research_steady_ns()));
    auto solver = std::make_unique<ContractSolver>();
    fake_ = solver.get();
    node_ = MpcControllerNodeTestAccess::make(std::move(solver));
    MpcControllerNodeTestAccess::outputs(*node_, prefix_);
    observer_ = std::make_shared<rclcpp::Node>("research_contract_observer_" + suffix);
    left_sub_ = observer_->create_subscription<std_msgs::msg::Float64>(prefix_ + "/left", 100,
        [this](std_msgs::msg::Float64::ConstSharedPtr m) {left_.push_back(m->data);});
    right_sub_ = observer_->create_subscription<std_msgs::msg::Float64>(prefix_ + "/right", 100,
        [this](std_msgs::msg::Float64::ConstSharedPtr m) {right_.push_back(m->data);});
    state_sub_ = observer_->create_subscription<usv_mpc::ResearchState>("/research/state_snapshot",
        100,
        [this](usv_mpc::ResearchState::ConstSharedPtr m) {
          if (m->run_id == run_id_) {states_.push_back(*m);}
      });
    applied_sub_ =
      observer_->create_subscription<usv_mpc::ResearchApplied>("/research/control/applied", 100,
        [this](usv_mpc::ResearchApplied::ConstSharedPtr m) {
          if (m->run_id == run_id_) {applied_.push_back(*m);}
      });
    cycle_sub_ = observer_->create_subscription<usv_mpc::ResearchCycle>("/research/cycle_timing",
        100,
        [this](usv_mpc::ResearchCycle::ConstSharedPtr m) {
          if (m->run_id == run_id_) {cycles_.push_back(*m);}
      });
    executor_.add_node(observer_);
    observer_added_ = true;
    ASSERT_TRUE(spin_until([this]() {return MpcControllerNodeTestAccess::discovered(*node_);}));
    MpcControllerNodeTestAccess::odom(*node_, odom());
  }
  void TearDown() override
  {
    if (node_) {MpcControllerNodeTestAccess::stop(*node_, false);}
    if (observer_ && observer_added_) {executor_.remove_node(observer_);}
    node_.reset();
    observer_.reset();
    if (std::filesystem::exists(output_)) {std::filesystem::remove_all(output_);}
  }
  template<class Predicate> bool spin_until(Predicate predicate)
  {
    const auto end = std::chrono::steady_clock::now() + 3s;
    while (!predicate() && std::chrono::steady_clock::now() < end) {
      executor_.spin_some();
      std::this_thread::sleep_for(2ms);
    }
    executor_.spin_some();
    return predicate();
  }
  void enable()
  {
    MpcControllerNodeTestAccess::logging(*node_, output_.string(), run_id_);
    ASSERT_TRUE(spin_until([this]() {
        return state_sub_->get_publisher_count() > 0 &&
               applied_sub_->get_publisher_count() > 0 &&
               cycle_sub_->get_publisher_count() > 0;
    }));
    // Publisher discovery can precede reciprocal subscription discovery.
    for (int i = 0; i < 25; ++i) {executor_.spin_some(); std::this_thread::sleep_for(2ms);}
    MpcControllerNodeTestAccess::clock(*node_, 10);
    MpcControllerNodeTestAccess::odom(*node_, odom());
    ASSERT_TRUE(spin_until([this]() {return states_.size() == 1;}));
  }
  void run()
  {
    const auto expected_left = left_.size() + 1;
    const auto expected_right = right_.size() + 1;
    const auto expected_cycle = cycles_.size() + 1;
    MpcControllerNodeTestAccess::run(*node_);
    ASSERT_TRUE(spin_until([&]() {
        return left_.size() == expected_left && right_.size() == expected_right;
    }));
    if (logging_) {ASSERT_TRUE(spin_until([&]() {return cycles_.size() == expected_cycle;}));}
  }
  nlohmann::json summary()
  {
    std::ifstream stream(output_ / "session_summary.json");
    nlohmann::json result;
    stream >> result;
    return result;
  }

  std::shared_ptr<usv_mpc::MpcControllerNode> node_;
  ContractSolver * fake_ = nullptr;
  std::shared_ptr<rclcpp::Node> observer_;
  rclcpp::executors::SingleThreadedExecutor executor_;
  std::string run_id_, prefix_;
  std::filesystem::path output_;
  bool logging_ = false;
  bool observer_added_ = false;
  rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr left_sub_, right_sub_;
  rclcpp::Subscription<usv_mpc::ResearchState>::SharedPtr state_sub_;
  rclcpp::Subscription<usv_mpc::ResearchApplied>::SharedPtr applied_sub_;
  rclcpp::Subscription<usv_mpc::ResearchCycle>::SharedPtr cycle_sub_;
  std::vector<double> left_, right_;
  std::vector<usv_mpc::ResearchState> states_;
  std::vector<usv_mpc::ResearchApplied> applied_;
  std::vector<usv_mpc::ResearchCycle> cycles_;
};

TEST_F(ResearchContract, LoggingOffAndOnPreserveIdenticalCommandSelection)
{
  auto sequence = [this]() {
      MpcControllerNodeTestAccess::reset_history(*node_);
      std::vector<std::array<double, 2>> output;
      for (int i = 0; i < 8; ++i) {
        fake_->candidate = i == 0 ? Eigen::Vector2d(8.0, 12.0) : Eigen::Vector2d(-18.0, 22.0);
        fake_->backend_ms = i < 2 ? 1.0 : 250.0;
        run();
        output.push_back({left_.back(), right_.back()});
      }
      return output;
    };
  const auto disabled = sequence();
  enable(); logging_ = true;
  const auto enabled = sequence();
  ASSERT_EQ(disabled.size(), enabled.size());
  for (size_t i = 0; i < disabled.size(); ++i) {
    EXPECT_EQ(disabled[i], enabled[i]);
                                                                                   }
  EXPECT_DOUBLE_EQ(enabled.back()[0], 0.0);
  EXPECT_DOUBLE_EQ(enabled.back()[1], 0.0);
  ASSERT_TRUE(spin_until([this]() {return applied_.size() == 8;}));
  EXPECT_EQ(applied_.at(2).control_source, "repeat_last_command");
  EXPECT_EQ(applied_.at(6).control_source, "hold_zero");
}

TEST_F(ResearchContract, YawNinetyDegreesPreservesBodyTwistWithoutSecondRotation)
{
  enable(); logging_ = true;
  const auto msg = odom(10, std::acos(-1.0) / 2.0);
  MpcControllerNodeTestAccess::odom(*node_, msg);
  run();
  ASSERT_TRUE(spin_until([this]() {return states_.size() == 2;}));
  EXPECT_TRUE(states_.back().valid);
  EXPECT_NEAR(states_.back().state_6[2], std::acos(-1.0) / 2.0, 1e-12);
  EXPECT_DOUBLE_EQ(states_.back().state_6[3], 4.0);
  EXPECT_DOUBLE_EQ(states_.back().state_6[4], 0.5);
  EXPECT_DOUBLE_EQ(fake_->input(3), 4.0);
  EXPECT_DOUBLE_EQ(fake_->input(4), 0.5);
}

TEST_F(ResearchContract, ImuOverwriteIsMixedAndNextOdomRestoresAtomicSource)
{
  enable(); logging_ = true;
  MpcControllerNodeTestAccess::imu(*node_, 9, 0.9);
  run();
  ASSERT_EQ(cycles_.size(), 1u);
  EXPECT_EQ(cycles_.back().state_kind, "controller_mixed");
  EXPECT_DOUBLE_EQ(cycles_.back().controller_state_6[5], 0.9);
  EXPECT_EQ(cycles_.back().received_imu_sequence, 1u);
  EXPECT_EQ(cycles_.back().imu_stamp_ns, 9000000000LL);
  EXPECT_DOUBLE_EQ(states_.back().state_6[5], 0.3);
  MpcControllerNodeTestAccess::odom(*node_, odom(10, 0.0, 0.4));
  run();
  EXPECT_EQ(cycles_.back().state_kind, "odom_atomic");
  EXPECT_EQ(cycles_.back().received_imu_sequence, 0u);
  EXPECT_EQ(cycles_.back().imu_stamp_ns, 0);
  EXPECT_DOUBLE_EQ(cycles_.back().controller_state_6[5], 0.4);
}

TEST_F(ResearchContract, NewOdomDuringSolveCannotRewriteFrozenInputOrIdentity)
{
  enable(); logging_ = true;
  MpcControllerNodeTestAccess::imu(*node_, 9, 0.9);
  fake_->block = true;
  std::thread solving([this]() {MpcControllerNodeTestAccess::run(*node_);});
  bool entered = false;
  {
    std::unique_lock<std::mutex> lock(fake_->gate_mutex);
    entered = fake_->gate.wait_for(lock, 2s, [this]() {return fake_->entered;});
  }
  EXPECT_TRUE(entered);
  auto newer = odom(11, 0.0, 0.7);
  newer.pose.pose.position.x = 99.0;
  MpcControllerNodeTestAccess::odom(*node_, newer);
  {
    std::lock_guard<std::mutex> lock(fake_->gate_mutex); fake_->released = true;
  }
  fake_->gate.notify_all();
  solving.join();
  ASSERT_TRUE(spin_until([this]() {return cycles_.size() == 1 && states_.size() == 2;}));
  EXPECT_DOUBLE_EQ(fake_->input(0), 2.0);
  EXPECT_DOUBLE_EQ(fake_->input(5), 0.9);
  EXPECT_DOUBLE_EQ(cycles_.back().controller_state_6[0], 2.0);
  EXPECT_EQ(cycles_.back().odom_stamp_ns, 10000000000LL);
  EXPECT_EQ(cycles_.back().imu_stamp_ns, 9000000000LL);
  EXPECT_EQ(cycles_.back().received_odom_sequence, 1u);
  EXPECT_DOUBLE_EQ(states_.back().state_6[0], 99.0);
  EXPECT_EQ(states_.back().odom_stamp_ns, 11000000000LL);
}

TEST_F(ResearchContract, Real250And400MillisecondBlockingIntervalsAreRecorded)
{
  enable(); logging_ = true;
  run();
  for (const auto delay : {250ms, 400ms}) {
    fake_->delay = delay;
    fake_->candidate = {22.0, -18.0};
    run();
    const auto & cycle = cycles_.back();
    EXPECT_TRUE(cycle.deadline_miss);
    EXPECT_FALSE(cycle.success);
    EXPECT_GE(cycle.solve_end_steady_ns - cycle.solve_start_steady_ns,
      std::chrono::duration_cast<std::chrono::nanoseconds>(delay).count());
    EXPECT_DOUBLE_EQ(cycle.backend_time_ms, 1.0);
    EXPECT_DOUBLE_EQ(left_.back(), 8.0);
    EXPECT_DOUBLE_EQ(right_.back(), 12.0);
    EXPECT_GT(cycle.publish_end_steady_ns, cycle.solve_end_steady_ns);
  }
}

TEST_F(ResearchContract, RepeatedIdenticalCommandsAlwaysHaveNewJointSequence)
{
  enable(); logging_ = true;
  for (int i = 0; i < 4; ++i) {
    run();
                                     }
  ASSERT_TRUE(spin_until([this]() {return applied_.size() == 4;}));
  for (size_t i = 0; i < applied_.size(); ++i) {
    const auto & event = applied_[i];
    EXPECT_EQ(event.sequence, i + 1);
    EXPECT_DOUBLE_EQ(event.final_n[0], 8.0);
    EXPECT_DOUBLE_EQ(event.final_n[1], 12.0);
    EXPECT_EQ(event.event_semantics, "publisher_command");
    EXPECT_FALSE(event.plant_acceptance_observed);
    EXPECT_FALSE(event.force_measured);
    EXPECT_FALSE(event.execution_atomicity_proven);
    EXPECT_EQ(event.previous_anchor_known, i > 0);
  }
}

TEST_F(ResearchContract, InvalidNumericQuaternionAndFrameSnapshotsAreFlagged)
{
  enable(); logging_ = true;
  auto invalid = odom();
  invalid.pose.pose.position.x = std::numeric_limits<double>::quiet_NaN();
  MpcControllerNodeTestAccess::odom(*node_, invalid);
  invalid = odom(); invalid.pose.pose.orientation.w = 0.0;
  MpcControllerNodeTestAccess::odom(*node_, invalid);
  invalid = odom(); invalid.child_frame_id = "unknown";
  MpcControllerNodeTestAccess::odom(*node_, invalid);
  ASSERT_TRUE(spin_until([this]() {return states_.size() == 4;}));
  for (size_t i = 1; i < states_.size(); ++i) {
    EXPECT_FALSE(states_[i].valid);
                                                                              }
  for (double value : states_.at(1).state_6) {
    EXPECT_TRUE(std::isfinite(value));
                                                                                }
  EXPECT_NE(states_.back().quality_reason.find("frame_unverified_or_mismatch"), std::string::npos);
}

TEST_F(ResearchContract, ClockPauseResetAndJumpRemainDistinctEpochs)
{
  enable(); logging_ = true;
  MpcControllerNodeTestAccess::clock(*node_, 10); run();
  EXPECT_EQ(cycles_.back().clock_status, "paused");
  EXPECT_EQ(cycles_.back().clock_epoch, 0u);
  MpcControllerNodeTestAccess::clock(*node_, 1); run();
  EXPECT_EQ(cycles_.back().clock_status, "reset");
  EXPECT_EQ(cycles_.back().clock_epoch, 1u);
  MpcControllerNodeTestAccess::clock(*node_, 10); run();
  EXPECT_EQ(cycles_.back().clock_status, "jump");
  EXPECT_EQ(cycles_.back().clock_epoch, 2u);
}

TEST_F(ResearchContract, RightPublisherExceptionRecordsActualPartialPublication)
{
  enable();
  MpcControllerNodeTestAccess::invalidate_right_publisher(*node_);
  EXPECT_THROW(MpcControllerNodeTestAccess::publish(*node_), std::exception);
  ASSERT_TRUE(spin_until([this]() {return applied_.size() == 1 && left_.size() == 1;}));
  EXPECT_TRUE(right_.empty());
  EXPECT_TRUE(applied_.back().left_publish_success);
  EXPECT_FALSE(applied_.back().right_publish_success);
  EXPECT_FALSE(applied_.back().publish_error.empty());
  EXPECT_EQ(applied_.back().sequence, 1u);
}

TEST_F(ResearchContract, ShutdownPublishesActualZeroAndDrainsBeforeContextEnds)
{
  enable(); logging_ = true;
  run();
  node_->safe_shutdown();
  ASSERT_TRUE(spin_until([this]() {return applied_.size() == 2 && left_.size() == 2;}));
  EXPECT_EQ(applied_.back().control_source, "shutdown_zero");
  EXPECT_DOUBLE_EQ(applied_.back().final_n[0], 0.0);
  EXPECT_DOUBLE_EQ(applied_.back().final_n[1], 0.0);
  EXPECT_TRUE(rclcpp::ok());
  const auto report = summary();
  EXPECT_TRUE(report.at("normal_end").get<bool>());
  EXPECT_TRUE(report.at("flushed").get<bool>());
  EXPECT_EQ(report.at("streams").at("applied").at("generated"), 2);
  EXPECT_EQ(report.at("streams").at("applied").at("emitted"), 2);
  EXPECT_EQ(report.at("queue_dropped_total"), 0);
}

TEST_F(ResearchContract, BoundedQueueOverflowIsCountedByTheActualEnqueuePath)
{
  enable();
  usv_mpc::ResearchState state;
  state.quality_reason = std::string(1024, 'q');
  state.valid = true;
  constexpr uint64_t generated = 50000;
  for (uint64_t i = 0; i < generated; ++i) {
    EXPECT_EQ(MpcControllerNodeTestAccess::enqueue_state(*node_, state), i + 2);
  }
  MpcControllerNodeTestAccess::stop(*node_);
  const auto report = summary();
  const auto & counts = report.at("streams").at("state");
  EXPECT_EQ(counts.at("generated"), generated + 1);
  EXPECT_EQ(counts.at("last_sequence"), generated + 1);
  const auto dropped = counts.at("dropped").get<uint64_t>();
  const auto emitted = counts.at("emitted").get<uint64_t>();
  EXPECT_GT(dropped, 0u);
  EXPECT_EQ(dropped + emitted, generated + 1);
  EXPECT_EQ(report.at("queue_dropped_total"), dropped);
}
TEST_F(ResearchContract, ObservationalLoggingOverheadUsesIdenticalFixedWorkload)
{
  constexpr int iterations = 100;
  auto cpu_ms = []() {
      struct rusage usage;
      if (getrusage(RUSAGE_SELF, &usage) != 0) {
        throw std::runtime_error("getrusage failed");
      }
      return 1000.0 * static_cast<double>(usage.ru_utime.tv_sec + usage.ru_stime.tv_sec) +
             static_cast<double>(usage.ru_utime.tv_usec + usage.ru_stime.tv_usec) / 1000.0;
    };
  auto wall_ms = [](int64_t start, int64_t end) {
      return static_cast<double>(end - start) / 1000000.0;
    };
  MpcControllerNodeTestAccess::reset_history(*node_);
  const double off_cpu_start = cpu_ms();
  const int64_t off_start = usv_mpc::research_steady_ns();
  for (int i = 0; i < iterations; ++i) {
    MpcControllerNodeTestAccess::run(*node_);
                                                                                 }
  const int64_t off_end = usv_mpc::research_steady_ns();
  const double off_cpu_end = cpu_ms();
  ASSERT_TRUE(spin_until([this]() {return left_.size() == 100 && right_.size() == 100;}));
  for (int i = 0; i < iterations; ++i) {
    EXPECT_DOUBLE_EQ(left_.at(i), 8.0);
    EXPECT_DOUBLE_EQ(right_.at(i), 12.0);
  }
  left_.clear(); right_.clear();
  enable();
  MpcControllerNodeTestAccess::reset_history(*node_);
  const double on_cpu_start = cpu_ms();
  const int64_t on_start = usv_mpc::research_steady_ns();
  for (int i = 0; i < iterations; ++i) {
    MpcControllerNodeTestAccess::run(*node_);
                                                                                 }
  const int64_t on_end = usv_mpc::research_steady_ns();
  const double on_cpu_control_end = cpu_ms();
  MpcControllerNodeTestAccess::stop(*node_);
  const int64_t flush_end = usv_mpc::research_steady_ns();
  const double on_cpu_flushed = cpu_ms();
  ASSERT_TRUE(spin_until([this]() {
      return left_.size() == 100 && right_.size() == 100 &&
             applied_.size() == 100 && cycles_.size() == 100;
  }));
  for (int i = 0; i < iterations; ++i) {
    EXPECT_DOUBLE_EQ(left_.at(i), 8.0);
    EXPECT_DOUBLE_EQ(right_.at(i), 12.0);
  }
  const auto report = summary();
  EXPECT_EQ(report.at("queue_dropped_total"), 0);
  EXPECT_EQ(report.at("streams").at("applied").at("emitted"), iterations);
  EXPECT_EQ(report.at("streams").at("cycle").at("emitted"), iterations);
  nlohmann::json observed = {
    {"iterations", iterations}, {"workload", "fixed_state_fake_solver_no_delay"},
    {"setup_discovery_observer_drain_excluded", true},
    {"off_control_wall_ms", wall_ms(off_start, off_end)},
    {"off_process_cpu_ms", off_cpu_end - off_cpu_start},
    {"on_control_wall_ms", wall_ms(on_start, on_end)},
    {"on_process_cpu_to_control_end_ms", on_cpu_control_end - on_cpu_start},
    {"on_async_flush_wall_ms", wall_ms(on_end, flush_end)},
    {"on_process_cpu_including_flush_ms", on_cpu_flushed - on_cpu_start},
    {"queue_dropped_total", report.at("queue_dropped_total")},
    {"single_pair_observation_hard_realtime_bound", false}
  };
  std::printf("RESEARCH_OVERHEAD_OBSERVED %s\n", observed.dump().c_str());
}

}  // namespace
