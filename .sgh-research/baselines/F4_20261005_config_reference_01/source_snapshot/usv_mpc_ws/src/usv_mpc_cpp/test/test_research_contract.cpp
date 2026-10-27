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
  // P0_REFERENCE_PREDICTION_TEST_ACCESS_V1
  static void reference_logging(
    MpcControllerNode & node, const std::string & dir,
    const std::string & run)
  {
    node.set_parameter(rclcpp::Parameter("research_expected_pose_frame", "map"));
    node.set_parameter(rclcpp::Parameter("research_expected_child_frame", "base_link"));
    node.set_parameter(rclcpp::Parameter("research_frame_contract_verified", true));
    node.reference_logging_enabled_ = true;
    node.research_nominal_config_hash_ = std::string(64, 'b');
    node.research_ = std::make_unique<ResearchLogger>(node, dir, run, "F1_test",
      std::string(64, 'a'), true, node.research_nominal_config_hash_);
    node.research_->arm();
  }

  static void reference_solver(MpcControllerNode & node, std::unique_ptr<DynamicMpc> solver)
  {
    node.mpc_ = std::move(solver);
  }

  static void reference_path(
    MpcControllerNode & node, int sec, double dx = 0.0,
    bool empty = false)
  {
    {
      std::lock_guard<std::mutex> lock(node.state_lock_);
      node.reference_start_offset_ = 2;
    }
    auto msg = std::make_shared<nav_msgs::msg::Path>();
    msg->header.stamp.sec = sec;
    msg->header.frame_id = "map";
    if (!empty) {
      for (int i = 0; i < 5; ++i) {
        geometry_msgs::msg::PoseStamped pose;
        pose.pose.position.x = dx + 2.0 * i;
        pose.pose.position.y = 3.0;
        pose.pose.orientation.w = 1.0;
        msg->poses.push_back(pose);
      }
    }
    node.path_callback_(msg);
  }

  static void reference_profile(MpcControllerNode & node, int sec)
  {
    auto msg = std::make_shared<std_msgs::msg::Float64MultiArray>();
    msg->layout.dim.resize(2);
    msg->layout.dim[0].label = "stamp_sec:" + std::to_string(sec);
    msg->layout.dim[1].label = "stamp_nanosec:0";
    for (int i = 0; i < 5; ++i) {
      msg->data.insert(msg->data.end(), {1.0 + 0.1 * i, 9.0, 0.3 + 0.05 * i, 10.0 * i});
    }
    node.profile_callback_(msg);
  }

  static void reference_bad_profile(MpcControllerNode & node)
  {
    auto msg = std::make_shared<std_msgs::msg::Float64MultiArray>();
    msg->data = {9.0, 8.0, 7.0};
    node.profile_callback_(msg);
  }

  static uint64_t reference_profile_version(const MpcControllerNode & node)
  {
    return node.profile_received_sequence_;
  }

  static uint64_t reference_path_version(const MpcControllerNode & node)
  {
    return node.path_received_sequence_;
  }

  // P0_QUATERNION_TEST_ACCESS_V1_BEGIN
  static nlohmann::json quaternion_admission(MpcControllerNode & node)
  {
    std::lock_guard<std::mutex> lock(node.state_lock_);
    return {
      {"state", {node.x_, node.y_, node.psi_, node.u_, node.v_, node.r_}},
      {"odom_received", node.odom_received_}, {"imu_received", node.imu_received_},
      {"last_odom_time", node.last_odom_time_},
      {"received_odom", node.received_odom_count_}, {"received_imu", node.received_imu_count_},
      {"accepted_odom", node.accepted_odom_sequence_},
      {"accepted_imu", node.accepted_imu_sequence_},
      {"odom_stamp", node.accepted_odom_stamp_ns_}, {"imu_stamp", node.accepted_imu_stamp_ns_},
      {"r_from_imu", node.r_from_imu_}
    };
  }

  static void quaternion_stale_odom(MpcControllerNode & node)
  {
    std::lock_guard<std::mutex> lock(node.state_lock_);
    node.odom_timeout_s_ = 1.0;
    node.last_odom_time_ = std::chrono::duration<double>(
      std::chrono::steady_clock::now().time_since_epoch()).count() - 2.0;
  }

  static void quaternion_imu_message(MpcControllerNode & node, const sensor_msgs::msg::Imu & msg)
  {
    node.imu_callback_(std::make_shared<sensor_msgs::msg::Imu>(msg));
  }
  // P0_QUATERNION_TEST_ACCESS_V1_END

  // P0_REFERENCE_TEST_ACCESS_V1_BEGIN
  static void reference_inputs(
    MpcControllerNode & node,
    const std::vector<std::array<double, 3>> & path,
    const std::vector<std::array<double, 4>> & profile,
    std::pair<int, int> path_stamp = {100, 0},
    std::pair<int, int> profile_stamp = {100, 0}, int offset = 2)
  {
    std::lock_guard<std::mutex> lock(node.state_lock_);
    node.reference_path_ = path;
    node.ref_profile_ = profile;
    node.reference_path_stamp_ = path_stamp;
    node.ref_profile_stamp_ = profile_stamp;
    node.reference_start_offset_ = offset;
    node.cruise_speed_ = 0.6;
    node.path_received_ = !path.empty();
  }

  static Eigen::MatrixXd reference_matrix(
    MpcControllerNode & node, const Vector6d & state)
  {
    std::lock_guard<std::mutex> lock(node.state_lock_);
    return node.build_reference_(state);
  }

  static bool reference_profile_synced(const MpcControllerNode & node)
  {
    return node.profile_synced_;
  }
  // P0_REFERENCE_TEST_ACCESS_V1_END

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

// P0_REFERENCE_REAL_FUNCTION_TESTS_V1_BEGIN
// These fixtures call the node's actual private build_reference_ function.
// They do not reconstruct or claim the unlogged reference used by an old bag.
TEST_F(ResearchContract, ReferenceProfileUsesNearestOffsetAndReanchorsProfileTime)
{
  std::vector<std::array<double, 3>> path;
  std::vector<std::array<double, 4>> profile;
  for (int i = 0; i < 41; ++i) {
    const double position = 0.5 * static_cast<double>(i);
    path.push_back({position, 0.0, 0.0});
    profile.push_back({0.8, 0.0, 0.0, 100.0 + position / 0.8});
  }
  MpcControllerNodeTestAccess::reference_inputs(*node_, path, profile);
  usv_mpc::Vector6d state = usv_mpc::Vector6d::Zero();
  // At x=0 and x=0.1 the nearest point is index 0; at x=0.3 it is index 1.
  // With offset 2, output anchors move from path[2] to path[3]. Profile times
  // are 101.25 and 101.875, so k=1 remains anchor + 0.8 * solver dt (0.2).
  for (const auto & sample : std::vector<std::array<double, 2>>{
      {0.0, 1.0}, {0.1, 1.0}, {0.3, 1.5}})
  {
    SCOPED_TRACE(sample[0]);
    state(0) = sample[0];
    const auto reference = MpcControllerNodeTestAccess::reference_matrix(*node_, state);
    ASSERT_EQ(reference.rows(), 6);
    ASSERT_EQ(reference.cols(), 3);  // ContractSolver N=2, dt=0.2.
    EXPECT_TRUE(MpcControllerNodeTestAccess::reference_profile_synced(*node_));
    for (int k = 0; k < reference.cols(); ++k) {
      EXPECT_NEAR(reference(0, k), sample[1] + 0.16 * k, 1e-9);
      EXPECT_DOUBLE_EQ(reference(1, k), 0.0);
      EXPECT_DOUBLE_EQ(reference(3, k), 0.8);
      EXPECT_DOUBLE_EQ(reference(4, k), 0.0);
      EXPECT_DOUBLE_EQ(reference(5, k), 0.0);
    }
  }
}

TEST_F(ResearchContract, ReferenceStampOrLengthMismatchUsesCruiseFallback)
{
  std::vector<std::array<double, 3>> path;
  std::vector<std::array<double, 4>> profile;
  for (int i = 0; i < 41; ++i) {
    const double position = 0.5 * static_cast<double>(i);
    path.push_back({position, 0.0, 0.0});
    profile.push_back({0.8, 0.0, 0.0, position / 0.8});
  }
  const usv_mpc::Vector6d state = usv_mpc::Vector6d::Zero();
  for (int mismatch = 0; mismatch < 2; ++mismatch) {
    SCOPED_TRACE(mismatch);
    auto selected_profile = profile;
    if (mismatch == 1) {selected_profile.pop_back();}
    MpcControllerNodeTestAccess::reference_inputs(
      *node_, path, selected_profile, {100, 0}, mismatch == 0 ?
      std::pair<int, int>{101, 0} : std::pair<int, int>{100, 0});
    const auto reference = MpcControllerNodeTestAccess::reference_matrix(*node_, state);
    EXPECT_FALSE(MpcControllerNodeTestAccess::reference_profile_synced(*node_));
    for (int k = 0; k < reference.cols(); ++k) {
      EXPECT_NEAR(reference(0, k), 1.0 + 0.12 * k, 1e-9);
      EXPECT_DOUBLE_EQ(reference(3, k), 0.6);
      EXPECT_DOUBLE_EQ(reference(4, k), 0.0);
    }
  }
}

TEST_F(ResearchContract, ReferenceOffsetZeroStillAdvancesAtLeastOnePathPoint)
{
  std::vector<std::array<double, 3>> path;
  std::vector<std::array<double, 4>> profile;
  for (int i = 0; i < 41; ++i) {
    const double position = 0.5 * static_cast<double>(i);
    path.push_back({position, 0.0, 0.0});
    profile.push_back({0.8, 0.0, 0.0, position / 0.8});
  }
  MpcControllerNodeTestAccess::reference_inputs(*node_, path, profile, {100, 0}, {100, 0}, 0);
  const auto reference = MpcControllerNodeTestAccess::reference_matrix(
    *node_, usv_mpc::Vector6d::Zero());
  EXPECT_TRUE(MpcControllerNodeTestAccess::reference_profile_synced(*node_));
  for (int k = 0; k < reference.cols(); ++k) {
    EXPECT_NEAR(reference(0, k), 0.5 + 0.16 * k, 1e-9);
    EXPECT_DOUBLE_EQ(reference(3, k), 0.8);
  }
}

TEST_F(ResearchContract, ReferenceYawUnwrapRemainsContinuousAcrossPi)
{
  const double pi = std::acos(-1.0);
  std::vector<std::array<double, 3>> path;
  std::vector<std::array<double, 4>> profile;
  for (int i = 0; i < 41; ++i) {
    const double position = 0.5 * static_cast<double>(i);
    path.push_back({position, 0.0, i <= 2 ? pi - 0.04 : -pi + 0.04});
    profile.push_back({0.8, 0.0, 0.0, position / 0.8});
  }
  MpcControllerNodeTestAccess::reference_inputs(*node_, path, profile);
  usv_mpc::Vector6d state = usv_mpc::Vector6d::Zero();
  state(2) = -pi + 0.02;
  const auto reference = MpcControllerNodeTestAccess::reference_matrix(*node_, state);
  EXPECT_TRUE(MpcControllerNodeTestAccess::reference_profile_synced(*node_));
  EXPECT_NEAR(reference(2, 0), -pi - 0.04, 1e-9);
  for (int k = 1; k < reference.cols(); ++k) {
    EXPECT_TRUE(std::isfinite(reference(2, k)));
    EXPECT_LT(std::abs(reference(2, k) - reference(2, k - 1)), 0.2);
    EXPECT_LT(std::abs(reference(2, k) - state(2)), 0.2);
  }
}
// P0_REFERENCE_REAL_FUNCTION_TESTS_V1_END


// P0_QUATERNION_TEST_CASES_V1_BEGIN
struct QuaternionRejectedCaseV1
{
  const char * name;
  std::array<double, 4> xyzw;
};

std::vector<QuaternionRejectedCaseV1> quaternion_rejected_cases_v1()
{
  const double nan = std::numeric_limits<double>::quiet_NaN();
  const double inf = std::numeric_limits<double>::infinity();
  return {
    {"zero", {0.0, 0.0, 0.0, 0.0}},
    {"near_zero", {0.0, 0.0, 0.0, 1e-7}},
    {"norm_square_overflow", {1e200, 0.0, 0.0, 1e200}},
    {"nan_component", {nan, 0.0, 0.0, 1.0}},
    {"positive_inf_component", {0.0, inf, 0.0, 1.0}},
    {"negative_inf_component", {0.0, 0.0, -inf, 1.0}}
  };
}

nav_msgs::msg::Odometry quaternion_rejected_odom_v1(
  const QuaternionRejectedCaseV1 & value)
{
  auto msg = odom(10);
  msg.pose.pose.position.x = 99.0;
  msg.pose.pose.position.y = -99.0;
  msg.twist.twist.linear.x = 88.0;
  msg.twist.twist.linear.y = -88.0;
  msg.twist.twist.angular.z = 77.0;
  auto & q = msg.pose.pose.orientation;
  q.x = value.xyzw[0]; q.y = value.xyzw[1];
  q.z = value.xyzw[2]; q.w = value.xyzw[3];
  return msg;
}

class QuaternionCountingSolverV1 : public ContractSolver
{
public:
  unsigned calls = 0;
  std::pair<Eigen::Vector2d, usv_mpc::SolveInfo> solve(
    const usv_mpc::Vector6d & state, const Eigen::MatrixXd & reference) override
  {
    ++calls;
    return ContractSolver::solve(state, reference);
  }
};

TEST_F(ResearchContract, FirstBadQuaternionNeverEnablesControllerWithLoggingOffOrOn)
{
  for (bool enabled : {false, true}) {
    SCOPED_TRACE(enabled ? "logging_on" : "logging_off");
    // SetUp supplies a good odom to its initial node. Replace that entire node,
    // without calling enable(), so this case has genuinely never accepted odom.
    auto solver = std::make_unique<QuaternionCountingSolverV1>();
    auto * counted = solver.get();
    fake_ = counted;
    node_ = MpcControllerNodeTestAccess::make(std::move(solver));
    MpcControllerNodeTestAccess::outputs(*node_, prefix_);
    ASSERT_TRUE(spin_until([this]() {return MpcControllerNodeTestAccess::discovered(*node_);}));
    left_.clear(); right_.clear();
    logging_ = enabled;
    if (enabled) {
      MpcControllerNodeTestAccess::logging(*node_, output_.string(), run_id_);
      ASSERT_TRUE(spin_until([this]() {
          return state_sub_->get_publisher_count() > 0 &&
                 applied_sub_->get_publisher_count() > 0 && cycle_sub_->get_publisher_count() > 0;
      }));
      for (int i = 0; i < 25; ++i) {
        executor_.spin_some(); std::this_thread::sleep_for(2ms);
      }
      MpcControllerNodeTestAccess::clock(*node_, 10);
    }
    const auto initial = MpcControllerNodeTestAccess::quaternion_admission(*node_);
    ASSERT_FALSE(initial.at("odom_received").get<bool>());
    ASSERT_EQ(initial.at("accepted_odom").get<uint64_t>(), 0u);
    const auto cases = quaternion_rejected_cases_v1();
    for (size_t i = 0; i < cases.size(); ++i) {
      SCOPED_TRACE(cases.at(i).name);
      MpcControllerNodeTestAccess::odom(*node_, quaternion_rejected_odom_v1(cases.at(i)));
      auto after = MpcControllerNodeTestAccess::quaternion_admission(*node_);
      EXPECT_EQ(after.at("received_odom").get<uint64_t>(), enabled ? i + 1 : 0u);
      auto unchanged = initial;
      after.erase("received_odom"); unchanged.erase("received_odom");
      EXPECT_EQ(after, unchanged);
      run();
      ASSERT_FALSE(left_.empty());
      ASSERT_FALSE(right_.empty());
      EXPECT_EQ(counted->calls, 0u);
      EXPECT_DOUBLE_EQ(left_.back(), 0.0);
      EXPECT_DOUBLE_EQ(right_.back(), 0.0);
      if (enabled) {
        ASSERT_EQ(cycles_.size(), i + 1);
        EXPECT_FALSE(cycles_.back().solve_invoked);
        EXPECT_EQ(cycles_.back().rejection_reason, "no_odom");
      }
    }
    if (enabled) {
      ASSERT_TRUE(spin_until([&]() {return states_.size() == cases.size();}));
      for (size_t i = 0; i < states_.size(); ++i) {
        EXPECT_FALSE(states_.at(i).valid);
        EXPECT_EQ(states_.at(i).received_odom_sequence, i + 1);
      }
      MpcControllerNodeTestAccess::stop(*node_);
      const auto source = summary();
      EXPECT_EQ(source.at("streams").at("state").at("generated").get<uint64_t>(), cases.size());
      EXPECT_EQ(source.at("streams").at("state").at("emitted").get<uint64_t>(), cases.size());
      EXPECT_EQ(source.at("queue_dropped_total").get<uint64_t>(), 0u);
    }
  }
}

TEST_F(ResearchContract, BadQuaternionPreservesMixedAcceptedInputAndDoesNotRefreshFreshness)
{
  enable(); logging_ = true;
  MpcControllerNodeTestAccess::imu(*node_, 9, 0.9);
  const auto before = MpcControllerNodeTestAccess::quaternion_admission(*node_);
  const auto cases = quaternion_rejected_cases_v1();
  for (size_t i = 0; i < cases.size(); ++i) {
    SCOPED_TRACE(cases.at(i).name);
    MpcControllerNodeTestAccess::odom(*node_, quaternion_rejected_odom_v1(cases.at(i)));
    auto after = MpcControllerNodeTestAccess::quaternion_admission(*node_);
    EXPECT_EQ(after.at("received_odom").get<uint64_t>(),
      before.at("received_odom").get<uint64_t>() + i + 1);
    auto unchanged = before;
    after.erase("received_odom"); unchanged.erase("received_odom");
    EXPECT_EQ(after, unchanged);
  }
  ASSERT_TRUE(spin_until([&]() {return states_.size() == cases.size() + 1;}));
  for (size_t i = 1; i < states_.size(); ++i) {
    EXPECT_FALSE(states_.at(i).valid);
    EXPECT_EQ(states_.at(i).received_odom_sequence,
      before.at("received_odom").get<uint64_t>() + i);
  }
  run();
  ASSERT_EQ(cycles_.size(), 1u);
  EXPECT_EQ(cycles_.back().state_kind, "controller_mixed");
  EXPECT_EQ(cycles_.back().received_odom_sequence, before.at("accepted_odom").get<uint64_t>());
  EXPECT_EQ(cycles_.back().received_imu_sequence, before.at("accepted_imu").get<uint64_t>());
  EXPECT_EQ(cycles_.back().odom_stamp_ns, before.at("odom_stamp").get<int64_t>());
  EXPECT_EQ(cycles_.back().imu_stamp_ns, before.at("imu_stamp").get<int64_t>());
  EXPECT_DOUBLE_EQ(fake_->input(0), 2.0);
  EXPECT_DOUBLE_EQ(fake_->input(5), 0.9);

  // Force the existing watchdog to consider the last good odom stale. A new
  // receive timestamp from a bad quaternion must not extend that freshness.
  MpcControllerNodeTestAccess::quaternion_stale_odom(*node_);
  const auto stale = MpcControllerNodeTestAccess::quaternion_admission(*node_);
  MpcControllerNodeTestAccess::odom(*node_, quaternion_rejected_odom_v1(cases.front()));
  EXPECT_EQ(MpcControllerNodeTestAccess::quaternion_admission(*node_).at("last_odom_time"),
    stale.at("last_odom_time"));
  run();
  ASSERT_EQ(cycles_.size(), 2u);
  ASSERT_FALSE(left_.empty());
  ASSERT_FALSE(right_.empty());
  EXPECT_FALSE(cycles_.back().solve_invoked);
  EXPECT_EQ(cycles_.back().rejection_reason, "odom_timeout");
  EXPECT_DOUBLE_EQ(left_.back(), 0.0);
  EXPECT_DOUBLE_EQ(right_.back(), 0.0);
}

TEST_F(ResearchContract, ValidUnitQuaternionAndItsSignKeepOriginalBodyState)
{
  enable(); logging_ = true;
  const double pi = std::acos(-1.0);
  size_t expected_snapshots = states_.size();
  for (double yaw : {-pi, -pi / 2.0, -0.7, 0.0, 0.7, pi / 2.0, pi}) {
    for (double sign : {-1.0, 1.0}) {
      SCOPED_TRACE(yaw);
      SCOPED_TRACE(sign);
      auto msg = odom(10, yaw);
      msg.pose.pose.orientation.z *= sign;
      msg.pose.pose.orientation.w *= sign;
      MpcControllerNodeTestAccess::odom(*node_, msg);
      ++expected_snapshots;
      run();
      ASSERT_EQ(cycles_.size(), expected_snapshots - 1);
      ASSERT_TRUE(spin_until([&]() {return states_.size() == expected_snapshots;}));
      EXPECT_TRUE(states_.back().valid);
      EXPECT_NEAR(usv_mpc::normalize_angle(fake_->input(2) - yaw), 0.0, 1e-12);
      EXPECT_DOUBLE_EQ(fake_->input(3), 4.0);
      EXPECT_DOUBLE_EQ(fake_->input(4), 0.5);
      EXPECT_DOUBLE_EQ(fake_->input(5), 0.3);
      EXPECT_EQ(cycles_.back().state_kind, "odom_atomic");
      EXPECT_EQ(cycles_.back().received_imu_sequence, 0u);
    }
  }
}

TEST_F(ResearchContract, ImuZeroUnusedOrientationAcceptsValidRateAndRejectsInvalidRates)
{
  enable(); logging_ = true;
  sensor_msgs::msg::Imu good;
  good.header.stamp.sec = 9;
  good.orientation.w = 0.0;  // The controller consumes gyro z, not this orientation.
  good.angular_velocity.z = 0.7;
  MpcControllerNodeTestAccess::quaternion_imu_message(*node_, good);
  const auto before = MpcControllerNodeTestAccess::quaternion_admission(*node_);
  EXPECT_TRUE(before.at("imu_received").get<bool>());
  EXPECT_TRUE(before.at("r_from_imu").get<bool>());
  EXPECT_DOUBLE_EQ(before.at("state").at(5).get<double>(), 0.7);
  EXPECT_EQ(before.at("accepted_imu").get<uint64_t>(), 1u);
  const double nan = std::numeric_limits<double>::quiet_NaN();
  const double inf = std::numeric_limits<double>::infinity();
  const std::array<double, 3> invalid_rates = {nan, inf, -inf};
  for (size_t i = 0; i < invalid_rates.size(); ++i) {
    auto bad = good;
    bad.header.stamp.sec = 11;
    bad.angular_velocity.z = invalid_rates.at(i);
    MpcControllerNodeTestAccess::quaternion_imu_message(*node_, bad);
    auto after = MpcControllerNodeTestAccess::quaternion_admission(*node_);
    EXPECT_EQ(after.at("received_imu").get<uint64_t>(),
      before.at("received_imu").get<uint64_t>() + i + 1);
    auto unchanged = before;
    after.erase("received_imu"); unchanged.erase("received_imu");
    EXPECT_EQ(after, unchanged);
  }
  run();
  ASSERT_EQ(cycles_.size(), 1u);
  EXPECT_DOUBLE_EQ(fake_->input(5), 0.7);
  EXPECT_EQ(cycles_.back().state_kind, "controller_mixed");
  EXPECT_EQ(cycles_.back().received_imu_sequence, 1u);
  EXPECT_EQ(cycles_.back().imu_stamp_ns, 9000000000LL);
}
// P0_QUATERNION_TEST_CASES_V1_END


// P0_REFERENCE_PREDICTION_TEST_CASES_V1
class ReferenceEvidenceSolver : public usv_mpc::DynamicMpc
{
public:
  Eigen::Vector2d command{8.0, 12.0};
  std::vector<Eigen::MatrixXd> references;
  std::vector<usv_mpc::Vector6d> states;
  Eigen::MatrixXd returned_x, returned_u;
  bool success = true, invalid_shape = false, nonfinite = false;
  int horizon_steps = 2;
  double backend_ms = 1.0;
  mutable unsigned getter_calls = 0;
  bool block = false, entered = false, released = false;
  std::mutex mutex;
  std::condition_variable gate;

  std::pair<Eigen::Vector2d, usv_mpc::SolveInfo> solve(
    const usv_mpc::Vector6d & state, const Eigen::MatrixXd & reference) override
  {
    states.push_back(state);
    references.push_back(reference);
    if (block) {
      std::unique_lock<std::mutex> lock(mutex);
      entered = true; gate.notify_all();
      gate.wait(lock, [this]() {return released;});
    }
    usv_mpc::SolveInfo info;
    info.success = success;
    info.solve_time_ms = backend_ms;
    std::snprintf(info.backend, sizeof(info.backend), "reference_fake");
    if (!success) {std::snprintf(info.error, sizeof(info.error), "fake_failure");}
    info.X_pred.resize(invalid_shape ? 5 : 6, horizon_steps + 1);
    info.U_pred.resize(2, horizon_steps);
    for (int k = 0; k < info.X_pred.cols(); ++k) {
      for (int i = 0; i < info.X_pred.rows(); ++i) {info.X_pred(i, k) = 1000.0 + 10.0 * k + i;}
    }
    info.U_pred.col(0) = command;
    for (int k = 1; k < info.U_pred.cols(); ++k) {info.U_pred.col(k) << -3.0, 7.0;}
    if (nonfinite) {info.X_pred(0, 0) = std::numeric_limits<double>::quiet_NaN();}
    returned_x = info.X_pred; returned_u = info.U_pred;
    return {command, info};
  }
  void set_applied_control(const Eigen::Vector2d &) override {}
  void reset_warmstart() override {}
  Eigen::MatrixXd get_predicted_trajectory() const override
  {
    ++getter_calls;
    // Shifted warm state is deliberately different.
    return Eigen::MatrixXd::Constant(6, horizon_steps + 1, -999.0);
  }
  int N() const override {return horizon_steps;}
  double dt() const override {return 0.2;}
  const char * backend() const override {return "reference_fake";}
};

class ReferencePredictionContract : public ResearchContract
{
protected:
  void SetUp() override
  {
    ResearchContract::SetUp();
    if (::testing::Test::HasFatalFailure()) {return;}
    auto solver = std::make_unique<ReferenceEvidenceSolver>();
    evidence_ = solver.get();
    MpcControllerNodeTestAccess::reference_solver(*node_, std::move(solver));
    reference_sub_ = observer_->create_subscription<usv_mpc::ResearchReference>(
      "/research/reference_prediction", 100,
      [this](usv_mpc::ResearchReference::ConstSharedPtr msg) {
        if (msg->run_id == run_id_) {references_.push_back(*msg);}
      });
  }
  void enable_reference()
  {
    MpcControllerNodeTestAccess::reference_logging(*node_, output_.string(), run_id_);
    logging_ = true;
    ASSERT_TRUE(spin_until([this]() {
        return reference_sub_->get_publisher_count() > 0 && cycle_sub_->get_publisher_count() > 0;
    }));
    for (int i = 0; i < 25; ++i) {executor_.spin_some(); std::this_thread::sleep_for(2ms);}
    MpcControllerNodeTestAccess::clock(*node_, 10);
    MpcControllerNodeTestAccess::odom(*node_, odom());
  }
  void reference_run()
  {
    const auto count = references_.size();
    run();
    ASSERT_TRUE(spin_until([&]() {return references_.size() == count + 1;}));
  }
  static std::vector<double> flat(const Eigen::MatrixXd & matrix)
  {
    return {matrix.data(), matrix.data() + matrix.size()};
  }
  ReferenceEvidenceSolver * evidence_ = nullptr;
  rclcpp::Subscription<usv_mpc::ResearchReference>::SharedPtr reference_sub_;
  std::vector<usv_mpc::ResearchReference> references_;
};

TEST_F(ReferencePredictionContract, ExactFrozenReferenceSuppliedToSolver)
{
  enable_reference();
  ASSERT_FALSE(::testing::Test::HasFatalFailure());
  MpcControllerNodeTestAccess::reference_path(*node_, 100);
  MpcControllerNodeTestAccess::reference_bad_profile(*node_);
  evidence_->block = true;
  std::thread worker([this]() {MpcControllerNodeTestAccess::run(*node_);});
  bool entered;
  {
    std::unique_lock<std::mutex> lock(evidence_->mutex);
    entered = evidence_->gate.wait_for(lock, 2s, [this]() {return evidence_->entered;});
  }
  if (entered) {
    MpcControllerNodeTestAccess::reference_path(*node_, 101, 100.0);
    MpcControllerNodeTestAccess::reference_bad_profile(*node_);
  }
  {
    std::lock_guard<std::mutex> lock(evidence_->mutex);
    evidence_->released = true; evidence_->gate.notify_all();
  }
  worker.join();
  ASSERT_TRUE(entered);
  ASSERT_TRUE(spin_until([this]() {return references_.size() == 1 && cycles_.size() == 1;}));
  ASSERT_EQ(evidence_->references.size(), 1u);
  const auto & event = references_.front();
  EXPECT_EQ(event.reference_data, flat(evidence_->references.front()));
  EXPECT_EQ(event.controller_state_6, cycles_.front().controller_state_6);
  EXPECT_EQ(event.received_odom_sequence, cycles_.front().received_odom_sequence);
  EXPECT_EQ(event.state_copy_steady_ns, cycles_.front().state_copy_steady_ns);
  EXPECT_EQ(event.reference_ready_steady_ns, cycles_.front().reference_ready_steady_ns);
  EXPECT_EQ(event.solve_start_steady_ns, cycles_.front().solve_start_steady_ns);
  EXPECT_EQ(event.solve_end_steady_ns, cycles_.front().solve_end_steady_ns);
  EXPECT_EQ(event.cycle_sequence, cycles_.front().sequence);
  EXPECT_EQ(event.applied_sequence, cycles_.front().applied_sequence);
  EXPECT_EQ(event.path_received_sequence, 1u);
  EXPECT_EQ(event.profile_received_sequence, 1u);
  EXPECT_EQ(event.path_stamp_ns, 100000000000LL);
  EXPECT_EQ(MpcControllerNodeTestAccess::reference_path_version(*node_), 2u);
  EXPECT_EQ(MpcControllerNodeTestAccess::reference_profile_version(*node_), 2u);
  EXPECT_EQ(event.nearest_index, 1);
  EXPECT_EQ(event.start_index, 3);
  EXPECT_EQ(event.reference_mode, "cruise_arc_fallback");
  EXPECT_FALSE(event.profile_t0_known);
  EXPECT_EQ(evidence_->getter_calls, 0u);
  MpcControllerNodeTestAccess::reference_path(*node_, 102, 0.0, true);
  const auto before = references_.size();
  run();
  MpcControllerNodeTestAccess::stop(*node_);
  executor_.spin_some();
  EXPECT_EQ(references_.size(), before);
  EXPECT_EQ(MpcControllerNodeTestAccess::reference_path_version(*node_), 3u);
}

TEST_F(ReferencePredictionContract, AcceptedPredictionCopiedFromSameSolveInfo)
{
  enable_reference();
  ASSERT_FALSE(::testing::Test::HasFatalFailure());
  MpcControllerNodeTestAccess::reference_path(*node_, 100);
  MpcControllerNodeTestAccess::reference_profile(*node_, 100);
  reference_run();
  ASSERT_EQ(references_.size(), 1u);
  const auto & event = references_.back();
  EXPECT_EQ(event.schema_version, "p0-reference-prediction-v1");
  EXPECT_EQ(event.nominal_config_hash, std::string(64, 'b'));
  EXPECT_EQ(event.matrix_layout, "k_major");
  EXPECT_TRUE(event.profile_synced);
  EXPECT_EQ(event.reference_mode, "profile_time");
  EXPECT_TRUE(event.profile_t0_known);
  EXPECT_DOUBLE_EQ(event.profile_t0, 30.0);
  EXPECT_EQ(event.profile_received_sequence, 1u);
  EXPECT_EQ(event.profile_stamp_ns, 100000000000LL);
  EXPECT_TRUE(event.prediction_available);
  EXPECT_EQ(event.prediction_reason, "accepted_solution");
  EXPECT_EQ(event.x_pred_data, flat(evidence_->returned_x));
  EXPECT_EQ(event.u_pred_data, flat(evidence_->returned_u));
  EXPECT_EQ(event.x_pred_rows, 6u); EXPECT_EQ(event.x_pred_cols, 3u);
  EXPECT_EQ(event.u_pred_rows, 2u); EXPECT_EQ(event.u_pred_cols, 2u);
  EXPECT_GE(event.freeze_steady_ns, event.solve_end_steady_ns);
  EXPECT_EQ(event.sim_time_ns, cycles_.back().sim_time_ns);
  EXPECT_EQ(event.clock_epoch, cycles_.back().clock_epoch);
  EXPECT_EQ(event.clock_age_ns, cycles_.back().clock_age_ns);
  EXPECT_EQ(evidence_->getter_calls, 0u);
  MpcControllerNodeTestAccess::stop(*node_);
  const auto j = summary();
  EXPECT_TRUE(j.at("reference_prediction").at("enabled").get<bool>());
  EXPECT_EQ(j.at("streams").at("reference_prediction").at("generated"), 1);
  EXPECT_EQ(j.at("streams").at("reference_prediction").at("emitted"), 1);
  EXPECT_EQ(j.at("streams").at("reference_prediction").at("dropped"), 0);
}

TEST_F(ReferencePredictionContract, FailedLateAndStandbyNoFabrication)
{
  enable_reference();
  ASSERT_FALSE(::testing::Test::HasFatalFailure());
  MpcControllerNodeTestAccess::reference_path(*node_, 100);
  evidence_->success = false;
  reference_run();
  evidence_->success = true; evidence_->backend_ms = 250.0;
  reference_run();
  evidence_->backend_ms = 1.0; evidence_->invalid_shape = true;
  reference_run();
  evidence_->invalid_shape = false; evidence_->nonfinite = true;
  reference_run();
  ASSERT_EQ(references_.size(), 4u);
  for (const auto & event : references_) {
    EXPECT_FALSE(event.prediction_available);
    EXPECT_EQ(event.x_pred_rows, 0u); EXPECT_EQ(event.x_pred_cols, 0u);
    EXPECT_EQ(event.u_pred_rows, 0u); EXPECT_EQ(event.u_pred_cols, 0u);
    EXPECT_TRUE(event.x_pred_data.empty()); EXPECT_TRUE(event.u_pred_data.empty());
    EXPECT_FALSE(event.reference_data.empty());
  }
  EXPECT_EQ(references_[0].prediction_reason, "solve_rejected");
  EXPECT_EQ(references_[1].prediction_reason, "solve_rejected");
  EXPECT_TRUE(references_[1].deadline_miss);
  EXPECT_EQ(references_[2].prediction_reason, "prediction_missing_or_invalid");
  EXPECT_EQ(references_[3].prediction_reason, "prediction_missing_or_invalid");
  MpcControllerNodeTestAccess::reference_path(*node_, 101, 0.0, true);
  run();
  MpcControllerNodeTestAccess::stop(*node_);
  executor_.spin_some();
  EXPECT_EQ(references_.size(), 4u);
  ASSERT_EQ(cycles_.size(), 5u);
  EXPECT_FALSE(cycles_.back().solve_invoked);
  EXPECT_EQ(evidence_->getter_calls, 0u);
  const auto j = summary();
  EXPECT_EQ(j.at("streams").at("reference_prediction").at("generated"), 4);
  EXPECT_EQ(j.at("streams").at("reference_prediction").at("emitted"), 4);
}

TEST_F(ReferencePredictionContract, LoggingOffAndOnPreserveSameReferenceAndCommands)
{
  EXPECT_FALSE(node_->get_parameter("enable_reference_prediction_logging").as_bool());
  MpcControllerNodeTestAccess::reference_path(*node_, 100);
  run();
  ASSERT_EQ(evidence_->references.size(), 1u);
  ASSERT_FALSE(left_.empty()); ASSERT_FALSE(right_.empty());
  const auto original_reference = evidence_->references.front();
  const auto original_state = evidence_->states.front();
  const double original_left = left_.back(), original_right = right_.back();
  EXPECT_TRUE(references_.empty());
  MpcControllerNodeTestAccess::reset_history(*node_);
  enable_reference();
  ASSERT_FALSE(::testing::Test::HasFatalFailure());
  MpcControllerNodeTestAccess::reference_path(*node_, 100);
  reference_run();
  ASSERT_EQ(evidence_->references.size(), 2u);
  EXPECT_TRUE(evidence_->references.back().isApprox(original_reference, 0.0));
  EXPECT_TRUE(evidence_->states.back().isApprox(original_state, 0.0));
  EXPECT_DOUBLE_EQ(left_.back(), original_left);
  EXPECT_DOUBLE_EQ(right_.back(), original_right);
  ASSERT_EQ(references_.size(), 1u);
  EXPECT_EQ(references_.back().reference_data, flat(original_reference));
  EXPECT_EQ(evidence_->getter_calls, 0u);
}

TEST_F(ReferencePredictionContract, ObservationalOverheadSameFakeWorkload)
{
  // No ROS setup/discovery/spinning in the measured regions. The process CPU
  // includes concurrent logger work; deferred flush is measured separately.
  // This is an observation on this host, with no invented performance limit.
  constexpr unsigned calls = 100;
  evidence_->horizon_steps = 20;
  auto cpu_ms = []() {
      rusage usage{};
      if (getrusage(RUSAGE_SELF, &usage) != 0) {throw std::runtime_error("getrusage failed");}
      return 1000.0 * (usage.ru_utime.tv_sec + usage.ru_stime.tv_sec) +
             0.001 * (usage.ru_utime.tv_usec + usage.ru_stime.tv_usec);
    };
  auto clock_ms = []() {
      return std::chrono::duration<double, std::milli>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
    };
  MpcControllerNodeTestAccess::reference_path(*node_, 100);
  nlohmann::json benchmark = {{"benchmark", "reference_telemetry_observational_v1"},
    {"calls_per_mode", calls}, {"horizon_steps", evidence_->N()},
    {"reference_prediction_total_doubles", 6 * (evidence_->N() + 1) * 2 + 2 * evidence_->N()},
    {"workload", "same_fixed_fake_solver_and_actual_reference"}};
  Eigen::MatrixXd original_reference;
  usv_mpc::Vector6d original_state;
  for (int mode = 0; mode < 3; ++mode) {
    MpcControllerNodeTestAccess::reset_history(*node_);
    const auto first = evidence_->references.size();
    if (mode == 1) {
      MpcControllerNodeTestAccess::logging(*node_, output_.string(), run_id_);
      MpcControllerNodeTestAccess::clock(*node_, 10);
    } else if (mode == 2) {
      MpcControllerNodeTestAccess::reference_logging(*node_,
        (output_ / "reference_benchmark").string(), run_id_);
      MpcControllerNodeTestAccess::clock(*node_, 10);
      MpcControllerNodeTestAccess::reference_path(*node_, 100);
    }
    const double wall_begin = clock_ms(), cpu_begin = cpu_ms();
    for (unsigned i = 0; i < calls; ++i) {
      MpcControllerNodeTestAccess::run(*node_);
    }
    const double wall_elapsed = clock_ms() - wall_begin, cpu_elapsed = cpu_ms() - cpu_begin;
    ASSERT_EQ(evidence_->references.size(), first + calls);
    if (mode == 0) {
      original_reference = evidence_->references[first];
      original_state = evidence_->states[first];
    }
    for (unsigned i = 0; i < calls; ++i) {
      EXPECT_TRUE(evidence_->references[first + i].isApprox(original_reference, 0.0));
      EXPECT_TRUE(evidence_->states[first + i].isApprox(original_state, 0.0));
    }
    double flush_wall = 0.0, flush_cpu = 0.0;
    nlohmann::json drops = nullptr;
    if (mode > 0) {
      const double flush_wall_begin = clock_ms(), flush_cpu_begin = cpu_ms();
      MpcControllerNodeTestAccess::stop(*node_);
      flush_wall = clock_ms() - flush_wall_begin; flush_cpu = cpu_ms() - flush_cpu_begin;
      const auto path = mode == 1 ? output_ : output_ / "reference_benchmark";
      std::ifstream file(path / "session_summary.json");
      nlohmann::json session; file >> session;
      drops = session.at("queue_dropped_total");
      EXPECT_EQ(drops, 0);
    }
    benchmark["modes"].push_back({{"mode",
        mode == 0 ? "off" : (mode == 1 ? "base_three" : "base_plus_reference")},
        {"loop_wall_ms", wall_elapsed}, {"loop_process_cpu_ms", cpu_elapsed},
        {"flush_wall_ms", flush_wall}, {"flush_process_cpu_ms", flush_cpu},
        {"queue_dropped_total", drops}});
  }
  EXPECT_EQ(evidence_->getter_calls, 0u);
  std::printf("%s\n", benchmark.dump().c_str());
}

}  // namespace
