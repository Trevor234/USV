// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
// Observe the actual mode-manager request on a private mock service; no FCU.

#include <unistd.h>

#include <chrono>
#include <memory>
#include <string>
#include <thread>
#include <vector>

#include <gtest/gtest.h>

#include "usv_safety_cpp/mode_manager_node.hpp"

namespace usv_safety
{
class ModeManagerNodeTestAccess
{
public:
  static void prepare(ModeManagerNode & node, const std::string & service)
  {
    node.timer_->cancel();
    node.set_mode_cli_ = node.create_client<mavros_msgs::srv::SetMode>(service);
    node.armed_ = true;
    node.current_mavros_mode_ = "GUIDED";
    node.mpc_state_ = "STANDBY";
    node.mpc_ok_ = false;
    node.mpc_standby_reason_ = "wrong_mode(GUIDED)";
    node.last_mode_change_ = 0.0;
    node.odom_callback_(std::make_shared<nav_msgs::msg::Odometry>());
    node.path_callback_(std::make_shared<nav_msgs::msg::Path>());
  }
  static void current(ModeManagerNode & node, const std::string & mode)
  {node.current_mavros_mode_ = mode;}
  static void recent_takeover(ModeManagerNode & node)
  {
    node.last_mode_change_ = std::chrono::duration<double>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
  }
  static void reload(ModeManagerNode & node) {node.load_config_();}
  static void monitor(ModeManagerNode & node) {node.monitor_loop_();}
  static bool service_ready(ModeManagerNode & node)
  {return node.set_mode_cli_->service_is_ready();}
};
}  // namespace usv_safety

class ModeContract : public ::testing::Test
{
protected:
  static void SetUpTestSuite()
  {rclcpp::init(0, nullptr, rclcpp::InitOptions(), rclcpp::SignalHandlerOptions::None);}
  static void TearDownTestSuite() {rclcpp::shutdown();}
  void SetUp() override
  {
    node = std::make_shared<usv_safety::ModeManagerNode>();
    peer = std::make_shared<rclcpp::Node>("mode_contract_mock");
    const auto name = std::string("/mode_contract_") + std::to_string(getpid()) + "/" +
      ::testing::UnitTest::GetInstance()->current_test_info()->name();
    server = peer->create_service<mavros_msgs::srv::SetMode>(name,
      [this](const std::shared_ptr<mavros_msgs::srv::SetMode::Request> request,
        std::shared_ptr<mavros_msgs::srv::SetMode::Response> response) {
        requests.push_back(request->custom_mode);
        response->mode_sent = true;
      });
    usv_safety::ModeManagerNodeTestAccess::prepare(*node, name);
    executor.add_node(node);
    executor.add_node(peer);
    const auto end = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (!usv_safety::ModeManagerNodeTestAccess::service_ready(*node) &&
      std::chrono::steady_clock::now() < end)
    {
      executor.spin_some();
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    ASSERT_TRUE(usv_safety::ModeManagerNodeTestAccess::service_ready(*node));
  }
  void TearDown() override
  {
    executor.remove_node(node);
    executor.remove_node(peer);
    node.reset();
    server.reset();
    peer.reset();
  }
  void check(const std::vector<std::string> & expected)
  {
    usv_safety::ModeManagerNodeTestAccess::monitor(*node);
    const auto end = std::chrono::steady_clock::now() + std::chrono::milliseconds(100);
    while (std::chrono::steady_clock::now() < end) {
      executor.spin_some();
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    EXPECT_EQ(requests, expected);
  }
  std::shared_ptr<usv_safety::ModeManagerNode> node;
  std::shared_ptr<rclcpp::Node> peer;
  rclcpp::Service<mavros_msgs::srv::SetMode>::SharedPtr server;
  rclcpp::executors::SingleThreadedExecutor executor;
  std::vector<std::string> requests;
};

TEST_F(ModeContract, DefaultManualContractDoesNotAutomaticallyRequestAnyMode)
{
  EXPECT_EQ(node->get_parameter("mpc_fcu_mode").as_string(), "MANUAL");
  EXPECT_FALSE(node->get_parameter("auto_mode_switch").as_bool());
  check({});
}
TEST_F(ModeContract, EnabledSchemeBRequestsManualFromGuided)
{
  node->set_parameter(rclcpp::Parameter("auto_mode_switch", true));
  check({"MANUAL"});
}
TEST_F(ModeContract, SchemeBAlreadyManualNeverRequestsGuided)
{
  node->set_parameter(rclcpp::Parameter("auto_mode_switch", true));
  usv_safety::ModeManagerNodeTestAccess::current(*node, "MANUAL");
  check({});
}
TEST_F(ModeContract, ExplicitKinematicTargetRetainsGuided)
{
  node->set_parameter(rclcpp::Parameter("mpc_fcu_mode", "GUIDED"));
  node->set_parameter(rclcpp::Parameter("auto_mode_switch", true));
  usv_safety::ModeManagerNodeTestAccess::reload(*node);
  usv_safety::ModeManagerNodeTestAccess::current(*node, "MANUAL");
  check({"GUIDED"});
}
TEST_F(ModeContract, OperatorTakeoverCooldownStillBlocksAutomaticReturn)
{
  node->set_parameter(rclcpp::Parameter("auto_mode_switch", true));
  usv_safety::ModeManagerNodeTestAccess::recent_takeover(*node);
  check({});
}
TEST_F(ModeContract, InvalidControlModeIsRejected)
{
  node->set_parameter(rclcpp::Parameter("mpc_fcu_mode", "AUTO"));
  EXPECT_THROW(usv_safety::ModeManagerNodeTestAccess::reload(*node), std::invalid_argument);
}
