// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
// Gate tests and actual-node output tests. Physical output is redirected to
// unique test topics; no simulator, external Worker, or plant is used.
#include <gtest/gtest.h>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <future>
#include <condition_variable>
#include <memory>
#include <string>
#include <thread>
#include <vector>
#include "usv_mpc_cpp/mpc_node.hpp"

namespace usv_mpc {
class MpcControllerNodeTestAccess {
public:
  static std::shared_ptr<MpcControllerNode> make(std::unique_ptr<DynamicMpc> solver,
    const rclcpp::NodeOptions & options)
  {
    auto node = std::shared_ptr<MpcControllerNode>(new MpcControllerNode(std::move(solver), options));
    node->timer_->cancel(); return node;
  }
  static bool discovered(const MpcControllerNode & node)
  {
    return node.vrx_left_pub_->get_subscription_count() > 0 &&
      node.vrx_right_pub_->get_subscription_count() > 0 && node.rc_pub_->get_subscription_count() > 0;
  }
  static void tick(MpcControllerNode & node) {node.control_loop_();}
  static bool poll(MpcControllerNode & node) {return node.p1_poll_release_();}
  static bool armed(const MpcControllerNode & node) {return node.research_->armed();}
  static bool failed(const MpcControllerNode & node) {return node.p1_startup_gate_->failed();}
  static void standby(MpcControllerNode & node) {node.enter_standby_("startup_test");}
  static void all_output_helpers(MpcControllerNode & node)
  {
    const Eigen::Vector2d thrust(8, 12);
    node.publish_dynamic_output_(thrust); node.publish_vrx_thrust_(thrust);
    node.publish_rc_override_(thrust); node.publish_zero_dynamic_output_();
    node.release_vrx_thrust_(); node.release_rc_override_();
    std_msgs::msg::Float64 left, right; left.data = 8; right.data = 12;
    node.research_publish_(thrust, left, right);
  }
  static void publish(MpcControllerNode & node) {node.publish_dynamic_output_(Eigen::Vector2d(8, 12));}
  static void clock(MpcControllerNode & node)
  {
    auto value = std::make_shared<rosgraph_msgs::msg::Clock>(); value->clock.sec = 10;
    node.research_clock_(value);
  }
  static void close_logger(MpcControllerNode & node) {node.research_->stop(false);}
  static void gate_clock(PublisherStartupGate & gate, std::function<int64_t()> clock)
  {gate.p1_test_now_ = std::move(clock);}
  static void node_clock(MpcControllerNode & node, std::function<int64_t()> clock)
  {gate_clock(*node.p1_startup_gate_, std::move(clock));}
  static void release_latch(MpcControllerNode & node, std::function<void()> latch)
  {node.p1_test_release_arm_latch_ = std::move(latch);}
  static void shutdown_latch(MpcControllerNode & node, std::function<void()> latch)
  {node.p1_test_shutdown_latch_ = std::move(latch);}
  static bool shutting_down(const MpcControllerNode & node) {return node.shutting_down_.load();}
};
}  // namespace usv_mpc

namespace {
using Json = nlohmann::json;
using Gate = usv_mpc::PublisherStartupGate;
namespace fs = std::filesystem;
using namespace std::chrono_literals;
Json read_json(const fs::path & path) {std::ifstream file(path); Json result; file >> result; return result;}
std::string file_bytes(const fs::path & path)
{
  std::ifstream file(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}
void write_bytes(const fs::path & path, const std::string & bytes)
{
  std::ofstream file(path, std::ios::binary); file << bytes;
  if (!file.good()) {throw std::runtime_error("test input write failed");}
}
Json release_from(const Json & manifest, const std::string & manifest_hash)
{
  return {{"schema_version", "p1-D1-publisher-release-v1"},
    {"run_id", manifest.at("run_id")}, {"producer_instance_id", manifest.at("producer_instance_id")},
    {"startup_manifest_sha256", manifest_hash}, {"release_nonce", std::string(32, '1')},
    {"driver_evidence_sha256", std::string(64, '2')},
    {"valid_until_steady_ns", usv_mpc::p1_startup::steady_ns() + 10000000000LL},
    {"gates", {{"external_worker_zero_hooks", true}, {"subscriptions_verified", true},
      {"unique_dual_channel_owner", true}}}};
}
class StartupGate : public ::testing::Test {
protected:
  void SetUp() override
  {
    root_ = fs::temp_directory_path() / ("p1_startup_gate_" + std::to_string(::getpid()) +
      "_" + std::to_string(usv_mpc::p1_startup::steady_ns()));
    ASSERT_TRUE(fs::create_directory(root_)); ASSERT_TRUE(fs::create_directory(root_ / "output"));
    output_ = root_ / "output"; release_ = root_ / "release.json";
    std::ifstream boot("/proc/sys/kernel/random/boot_id"); std::string boot_id; std::getline(boot, boot_id);
    identity_ = {{"run_id", "startup_unit"}, {"producer_instance_id", "startup_unit:actual_logger"},
      {"baseline_id", "F5_20261005_atomic_freeze_01"}, {"config_hash", std::string(64, 'a')},
      {"nominal_config_hash", std::string(64, 'b')}, {"steady_clock_domain", boot_id + ":steady_clock"}};
  }
  void TearDown() override
  {
    // Only this exact freshly created test directory is eligible for cleanup.
    gate_.reset(); if (!root_.empty()) {fs::remove_all(root_);}
  }
  void make() {gate_ = std::make_unique<Gate>(output_, release_, identity_);}
  Json release_json() {return release_from(gate_->identity(), gate_->manifest_sha256());}
  void supply(Json value) {write_bytes(release_, value.dump());}
  void reject(Json value)
  {
    supply(value); EXPECT_FALSE(gate_->poll_release([this]() {++arm_calls_; return true;}));
    EXPECT_TRUE(gate_->failed()); EXPECT_EQ(arm_calls_, 0);
    EXPECT_FALSE(fs::exists(output_ / "release_receipt.json"));
    fs::remove(release_); supply(release_json());
    EXPECT_FALSE(gate_->poll_release([]() {return true;}));
  }
  fs::path root_, output_, release_; Json identity_; std::unique_ptr<Gate> gate_; int arm_calls_ = 0;
};
TEST_F(StartupGate, FreshManifestBindsExactIdentityAndExecutingBinary)
{
  make(); const auto manifest = read_json(output_ / "startup_manifest.json");
  EXPECT_EQ(manifest.at("producer_instance_id"), identity_.at("producer_instance_id"));
  EXPECT_EQ(manifest.at("binary_sha256"), usv_mpc::p1_startup::binary_sha256());
  EXPECT_EQ(manifest.at("pid"), ::getpid());
  EXPECT_EQ(manifest.at("process_start_ticks"), usv_mpc::p1_startup::process_start_ticks());
  EXPECT_EQ(manifest.at("source_bundle_sha256"), P1_D1_SOURCE_BUNDLE_SHA256);
  EXPECT_EQ(gate_->manifest_sha256(), usv_mpc::p1_startup::sha256_bytes(file_bytes(output_ / "startup_manifest.json")));
  EXPECT_EQ(manifest.at("physical_output_state"), "held");
  EXPECT_FALSE(manifest.at("driver_process_graph_worker_evidence_verified_by_publisher").get<bool>());
}
TEST_F(StartupGate, ExistingManifestIsNeverOverwritten)
{
  make(); const auto old = file_bytes(output_ / "startup_manifest.json");
  EXPECT_THROW(Gate(output_, release_, identity_), std::exception);
  EXPECT_EQ(file_bytes(output_ / "startup_manifest.json"), old);
}
TEST_F(StartupGate, MissingOutputDirectoryFailsBeforeRelease)
{fs::remove(output_); EXPECT_THROW(make(), std::exception); EXPECT_FALSE(fs::exists(release_));}
TEST_F(StartupGate, ManifestDestinationSymlinkIsRejected)
{
  write_bytes(root_ / "other", "original"); fs::create_symlink(root_ / "other", output_ / "startup_manifest.json");
  EXPECT_THROW(make(), std::exception); EXPECT_EQ(file_bytes(root_ / "other"), "original");
}
TEST_F(StartupGate, OutputDirectorySymlinkIsRejected)
{
  fs::remove(output_); fs::create_directory(root_ / "other"); fs::create_directory_symlink(root_ / "other", output_);
  EXPECT_THROW(make(), std::exception); EXPECT_FALSE(fs::exists(root_ / "other/startup_manifest.json"));
}
TEST_F(StartupGate, AbsentReleaseRemainsHeldWithoutArming)
{make(); EXPECT_FALSE(gate_->poll_release([this]() {++arm_calls_; return true;})); EXPECT_EQ(arm_calls_, 0); EXPECT_FALSE(gate_->failed());}
TEST_F(StartupGate, WrongRunIsTerminal) {make(); auto v = release_json(); v["run_id"] = "wrong"; reject(v);}
TEST_F(StartupGate, WrongProducerIsTerminal) {make(); auto v = release_json(); v["producer_instance_id"] = "wrong"; reject(v);}
TEST_F(StartupGate, WrongManifestHashIsTerminal) {make(); auto v = release_json(); v["startup_manifest_sha256"] = std::string(64, '9'); reject(v);}
TEST_F(StartupGate, FalsePreparationGateIsTerminal) {make(); auto v = release_json(); v["gates"]["external_worker_zero_hooks"] = false; reject(v);}
TEST_F(StartupGate, NonBooleanPreparationGateIsTerminal) {make(); auto v = release_json(); v["gates"]["subscriptions_verified"] = 1; reject(v);}
TEST_F(StartupGate, MissingPreparationGateIsTerminal) {make(); auto v = release_json(); v["gates"].erase("unique_dual_channel_owner"); reject(v);}
TEST_F(StartupGate, InvalidEvidenceHashIsTerminal) {make(); auto v = release_json(); v["driver_evidence_sha256"] = "missing"; reject(v);}
TEST_F(StartupGate, InvalidNonceIsTerminal) {make(); auto v = release_json(); v["release_nonce"] = "once"; reject(v);}
TEST_F(StartupGate, DuplicateJsonKeyIsTerminal)
{
  make(); auto bytes = release_json().dump(); bytes.insert(1, "\"run_id\":\"startup_unit\",");
  write_bytes(release_, bytes); EXPECT_FALSE(gate_->poll_release([]() {return true;})); EXPECT_TRUE(gate_->failed());
}
TEST_F(StartupGate, ReleaseSymlinkIsTerminal)
{make(); write_bytes(root_ / "other", release_json().dump()); fs::create_symlink(root_ / "other", release_); EXPECT_FALSE(gate_->poll_release([]() {return true;})); EXPECT_TRUE(gate_->failed());}
TEST_F(StartupGate, OversizedReleaseIsTerminal)
{make(); write_bytes(release_, std::string(16385, ' ')); EXPECT_FALSE(gate_->poll_release([]() {return true;})); EXPECT_TRUE(gate_->failed());}
TEST_F(StartupGate, DirectoryReleaseIsTerminal)
{make(); fs::create_directory(release_); EXPECT_FALSE(gate_->poll_release([]() {return true;})); EXPECT_TRUE(gate_->failed());}
TEST_F(StartupGate, HardLinkedReleaseIsTerminal)
{make(); supply(release_json()); fs::create_hard_link(release_, root_ / "alias"); EXPECT_FALSE(gate_->poll_release([]() {return true;})); EXPECT_TRUE(gate_->failed());}
TEST_F(StartupGate, FailedTelemetryArmDoesNotRelease)
{make(); supply(release_json()); EXPECT_FALSE(gate_->poll_release([]() {return false;})); EXPECT_TRUE(gate_->failed()); EXPECT_FALSE(fs::exists(output_ / "release_receipt.json"));}
TEST_F(StartupGate, ExistingReceiptCannotBeOverwrittenOrRelease)
{make(); supply(release_json()); write_bytes(output_ / "release_receipt.json", "old"); EXPECT_FALSE(gate_->poll_release([]() {return true;})); EXPECT_TRUE(gate_->failed()); EXPECT_EQ(file_bytes(output_ / "release_receipt.json"), "old");}
TEST_F(StartupGate, ValidReleaseArmsOnceAndReceiptBindsHashes)
{
  make(); supply(release_json());
  EXPECT_TRUE(gate_->poll_release([this]() {++arm_calls_; return true;}));
  const auto receipt_bytes = file_bytes(output_ / "release_receipt.json");
  EXPECT_TRUE(gate_->poll_release([this]() {++arm_calls_; return true;})); EXPECT_EQ(arm_calls_, 1);
  EXPECT_EQ(file_bytes(output_ / "release_receipt.json"), receipt_bytes);
  const auto receipt = read_json(output_ / "release_receipt.json");
  EXPECT_EQ(receipt.at("startup_manifest_sha256"), gate_->manifest_sha256());
  EXPECT_EQ(receipt.at("release_file_sha256"), usv_mpc::p1_startup::sha256_bytes(file_bytes(release_)));
  EXPECT_EQ(receipt.at("release_nonce"), std::string(32, '1'));
  EXPECT_TRUE(receipt.at("research_armed_before_release").get<bool>());
  EXPECT_EQ(receipt.at("status"), "prepared_acceptance");
  EXPECT_FALSE(receipt.at("receipt_qualifies_physical_release").get<bool>());
}
TEST_F(StartupGate, ChangedReleaseAfterAcceptanceInvalidatesPermanently)
{
  make(); const auto original = release_json(); supply(original); ASSERT_TRUE(gate_->poll_release([]() {return true;}));
  auto v = original; v["release_nonce"] = std::string(32, '3'); supply(v);
  EXPECT_FALSE(gate_->released_and_unchanged()); EXPECT_TRUE(gate_->failed());
  supply(original); EXPECT_FALSE(gate_->released_and_unchanged());
}
TEST_F(StartupGate, RemovedReleaseAfterAcceptanceInvalidatesPermanently)
{make(); supply(release_json()); ASSERT_TRUE(gate_->poll_release([]() {return true;})); fs::remove(release_); EXPECT_FALSE(gate_->released_and_unchanged()); EXPECT_TRUE(gate_->failed());}
TEST_F(StartupGate, ChangedManifestBeforeReleaseCannotArm)
{make(); supply(release_json()); write_bytes(output_ / "startup_manifest.json", "changed"); EXPECT_FALSE(gate_->poll_release([this]() {++arm_calls_; return true;})); EXPECT_EQ(arm_calls_, 0); EXPECT_TRUE(gate_->failed());}
TEST_F(StartupGate, RemovedManifestAfterReleaseInvalidatesOutput)
{make(); supply(release_json()); ASSERT_TRUE(gate_->poll_release([]() {return true;})); fs::remove(output_ / "startup_manifest.json"); EXPECT_FALSE(gate_->released_and_unchanged()); EXPECT_TRUE(gate_->failed());}
TEST_F(StartupGate, ExpiredReleaseCannotArm)
{make(); auto v = release_json(); v["valid_until_steady_ns"] = 1; reject(v);}
TEST_F(StartupGate, ReleaseValidityLongerThanSixtySecondsCannotArm)
{make(); auto v = release_json(); v["valid_until_steady_ns"] = usv_mpc::p1_startup::steady_ns() + 61000000000LL; reject(v);}
TEST_F(StartupGate, NonIntegerExpiryCannotArm)
{make(); auto v = release_json(); v["valid_until_steady_ns"] = "deadline"; reject(v);}
TEST_F(StartupGate, ExpiryDuringArmKeepsHeldWithoutReceipt)
{
  make(); auto v = release_json(); const int64_t until = v.at("valid_until_steady_ns"); supply(v);
  int calls = 0; usv_mpc::MpcControllerNodeTestAccess::gate_clock(*gate_, [&]() {return ++calls == 1 ? until - 100 : until;});
  EXPECT_FALSE(gate_->poll_release([]() {return true;})); EXPECT_TRUE(gate_->failed());
  EXPECT_FALSE(fs::exists(output_ / "release_receipt.json"));
}
TEST_F(StartupGate, ExpiryAfterReceiptIoLeavesPreparedEvidenceAndHeldState)
{
  make(); auto v = release_json(); const int64_t until = v.at("valid_until_steady_ns"); supply(v);
  int calls = 0; usv_mpc::MpcControllerNodeTestAccess::gate_clock(*gate_, [&]() {return ++calls <= 2 ? until - 100 : until;});
  EXPECT_FALSE(gate_->poll_release([]() {return true;})); EXPECT_TRUE(gate_->failed());
  EXPECT_TRUE(gate_->receipt_io_completed()); EXPECT_FALSE(gate_->released_and_unchanged());
  const auto receipt = read_json(output_ / "release_receipt.json");
  EXPECT_EQ(receipt.at("status"), "prepared_acceptance");
  EXPECT_FALSE(receipt.at("receipt_qualifies_physical_release").get<bool>());
}
TEST_F(StartupGate, ExpiryOnlyBoundsInitialAcceptance)
{
  make(); auto v = release_json(); const int64_t until = v.at("valid_until_steady_ns"); supply(v);
  usv_mpc::MpcControllerNodeTestAccess::gate_clock(*gate_, [until]() {return until - 100;});
  ASSERT_TRUE(gate_->poll_release([]() {return true;}));
  usv_mpc::MpcControllerNodeTestAccess::gate_clock(*gate_, [until]() {return until + 100;});
  EXPECT_TRUE(gate_->released_and_unchanged()); EXPECT_TRUE(gate_->poll_release([]() {return false;}));
}

class TestLatch {
public:
  void block()
  {
    std::unique_lock<std::mutex> lock(mutex_); entered_ = true; changed_.notify_all();
    // Root CTest also has an outer timeout; the latch itself is bounded.
    changed_.wait_for(lock, 6s, [this]() {return released_;});
  }
  bool wait_entered()
  {std::unique_lock<std::mutex> lock(mutex_); return changed_.wait_for(lock, 3s, [this]() {return entered_;});}
  void release() {std::lock_guard<std::mutex> lock(mutex_); released_ = true; changed_.notify_all();}
private:
  std::mutex mutex_; std::condition_variable changed_; bool entered_ = false, released_ = false;
};

class FakeSolver : public usv_mpc::DynamicMpc {
public:
  std::pair<Eigen::Vector2d, usv_mpc::SolveInfo> solve(const usv_mpc::Vector6d &, const Eigen::MatrixXd &) override
  {usv_mpc::SolveInfo info; info.success = true; info.solve_time_ms = 1; return {Eigen::Vector2d(8, 12), info};}
  void set_applied_control(const Eigen::Vector2d &) override {}
  void reset_warmstart() override {}
  Eigen::MatrixXd get_predicted_trajectory() const override {return {};}
  int N() const override {return 20;}
  double dt() const override {return 0.2;}
  const char * backend() const override {return "startup_test_fake";}
};
class PublisherNode : public ::testing::Test {
protected:
  static void SetUpTestSuite() {rclcpp::init(0, nullptr);}
  static void TearDownTestSuite() {rclcpp::shutdown();}
  void SetUp() override
  {
    static int sequence = 0; const auto suffix = std::to_string(++sequence);
    root_ = fs::temp_directory_path() / ("p1_startup_node_" + std::to_string(::getpid()) + "_" +
      std::to_string(usv_mpc::p1_startup::steady_ns())); ASSERT_TRUE(fs::create_directory(root_));
    output_ = root_ / "output"; release_ = root_ / "release.json";
    run_ = "p1_startup_test_" + suffix; const auto prefix = "/p1/startup_test/case_" + suffix;
    rclcpp::NodeOptions options; options.parameter_overrides({
      rclcpp::Parameter("output_mode", "vrx_thrust"), rclcpp::Parameter("enable_research_logging", true),
      rclcpp::Parameter("enable_reference_prediction_logging", true),
      rclcpp::Parameter("research_run_id", run_),
      rclcpp::Parameter("research_baseline_id", "F5_20261005_atomic_freeze_01"),
      rclcpp::Parameter("research_config_hash", std::string(64, 'a')),
      rclcpp::Parameter("research_nominal_config_hash", std::string(64, 'b')),
      rclcpp::Parameter("research_output_dir", output_.string()),
      rclcpp::Parameter("p1_release_file", release_.string()),
      rclcpp::Parameter("vrx_thrust_scale", 1.0),
      rclcpp::Parameter("vrx_left_thrust_topic", prefix + "/left"),
      rclcpp::Parameter("vrx_right_thrust_topic", prefix + "/right"),
      rclcpp::Parameter("rc_override_topic", prefix + "/rc")});
    node_ = usv_mpc::MpcControllerNodeTestAccess::make(std::make_unique<FakeSolver>(), options);
    observer_ = std::make_shared<rclcpp::Node>("startup_test_observer_" + suffix);
    left_sub_ = observer_->create_subscription<std_msgs::msg::Float64>(prefix + "/left", 100,
      [this](std_msgs::msg::Float64::ConstSharedPtr value) {left_.push_back(value->data);});
    right_sub_ = observer_->create_subscription<std_msgs::msg::Float64>(prefix + "/right", 100,
      [this](std_msgs::msg::Float64::ConstSharedPtr value) {right_.push_back(value->data);});
    rc_sub_ = observer_->create_subscription<mavros_msgs::msg::OverrideRCIn>(prefix + "/rc", 100,
      [this](mavros_msgs::msg::OverrideRCIn::ConstSharedPtr) {++rc_count_;});
    applied_sub_ = observer_->create_subscription<usv_mpc::ResearchApplied>("/research/control/applied", 100,
      [this](usv_mpc::ResearchApplied::ConstSharedPtr value) {if (value->run_id == run_) {applied_.push_back(*value);}});
    executor_.add_node(observer_);
    ASSERT_TRUE(spin_until([this]() {return usv_mpc::MpcControllerNodeTestAccess::discovered(*node_) && applied_sub_->get_publisher_count() > 0;}));
    drain();
  }
  void TearDown() override
  {
    if (node_) {usv_mpc::MpcControllerNodeTestAccess::close_logger(*node_);}
    executor_.remove_node(observer_); node_.reset(); observer_.reset(); fs::remove_all(root_);
  }
  template<class F> bool spin_until(F predicate)
  {
    const auto end = std::chrono::steady_clock::now() + 3s;
    while (!predicate() && std::chrono::steady_clock::now() < end) {executor_.spin_some(); std::this_thread::sleep_for(2ms);}
    executor_.spin_some(); return predicate();
  }
  void drain() {for (int i = 0; i < 20; ++i) {executor_.spin_some(); std::this_thread::sleep_for(2ms);}}
  Json release_json()
  {return release_from(read_json(output_ / "startup_manifest.json"), usv_mpc::p1_startup::sha256_bytes(file_bytes(output_ / "startup_manifest.json")));}
  void release()
  {write_bytes(release_, release_json().dump()); ASSERT_TRUE(usv_mpc::MpcControllerNodeTestAccess::poll(*node_)); usv_mpc::MpcControllerNodeTestAccess::clock(*node_);}
  void expect_no_physical()
  {drain(); EXPECT_TRUE(left_.empty()); EXPECT_TRUE(right_.empty()); EXPECT_EQ(rc_count_, 0); EXPECT_TRUE(applied_.empty());}
  fs::path root_, output_, release_; std::string run_;
  std::shared_ptr<usv_mpc::MpcControllerNode> node_; std::shared_ptr<rclcpp::Node> observer_;
  rclcpp::executors::SingleThreadedExecutor executor_;
  rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr left_sub_, right_sub_;
  rclcpp::Subscription<mavros_msgs::msg::OverrideRCIn>::SharedPtr rc_sub_;
  rclcpp::Subscription<usv_mpc::ResearchApplied>::SharedPtr applied_sub_;
  std::vector<double> left_, right_; std::vector<usv_mpc::ResearchApplied> applied_; int rc_count_ = 0;
};
TEST_F(PublisherNode, ConstructorManifestPrecedesAnyTimerOrPhysicalOutput)
{EXPECT_TRUE(fs::exists(output_ / "startup_manifest.json")); EXPECT_FALSE(usv_mpc::MpcControllerNodeTestAccess::armed(*node_)); expect_no_physical();}
TEST_F(PublisherNode, AllOutputHelpersRemainHeldWithoutRelease)
{usv_mpc::MpcControllerNodeTestAccess::all_output_helpers(*node_); expect_no_physical();}
TEST_F(PublisherNode, StandbyAndArmedParameterCannotBypassRelease)
{
  node_->set_parameter(rclcpp::Parameter("research_logging_armed", true));
  usv_mpc::MpcControllerNodeTestAccess::tick(*node_); usv_mpc::MpcControllerNodeTestAccess::standby(*node_);
  EXPECT_FALSE(usv_mpc::MpcControllerNodeTestAccess::armed(*node_)); expect_no_physical();
}
TEST_F(PublisherNode, ShutdownNeverAcceptsEvenAValidPendingRelease)
{write_bytes(release_, release_json().dump()); node_->safe_shutdown(); expect_no_physical(); EXPECT_FALSE(fs::exists(output_ / "release_receipt.json"));}
TEST_F(PublisherNode, WrongReleaseIsTerminalAndShutdownEmitsNoZero)
{
  auto v = release_json(); v["run_id"] = "wrong"; write_bytes(release_, v.dump());
  usv_mpc::MpcControllerNodeTestAccess::tick(*node_); EXPECT_TRUE(usv_mpc::MpcControllerNodeTestAccess::failed(*node_));
  node_->safe_shutdown(); expect_no_physical();
}
TEST_F(PublisherNode, FirstActualPhysicalPairHasSequenceOneAndManifestProducer)
{
  release(); EXPECT_TRUE(usv_mpc::MpcControllerNodeTestAccess::armed(*node_));
  usv_mpc::MpcControllerNodeTestAccess::publish(*node_);
  ASSERT_TRUE(spin_until([this]() {return left_.size() == 1 && right_.size() == 1 && applied_.size() == 1;}));
  EXPECT_EQ(applied_[0].sequence, 1u); EXPECT_EQ(applied_[0].producer_instance_id, read_json(output_ / "startup_manifest.json").at("producer_instance_id"));
  EXPECT_TRUE(applied_[0].left_publish_success); EXPECT_TRUE(applied_[0].right_publish_success);
  EXPECT_EQ(applied_[0].final_n[0], 8); EXPECT_EQ(applied_[0].final_n[1], 12);
  EXPECT_TRUE(fs::exists(output_ / "release_receipt.json"));
}
TEST_F(PublisherNode, ReleasedShutdownRecordsFinalZeroBeforeLoggerCloses)
{
  release(); usv_mpc::MpcControllerNodeTestAccess::publish(*node_); node_->safe_shutdown();
  ASSERT_TRUE(spin_until([this]() {return left_.size() == 2 && right_.size() == 2 && applied_.size() == 2;}));
  EXPECT_EQ(applied_.back().sequence, 2u); EXPECT_EQ(applied_.back().control_source, "shutdown_zero");
  EXPECT_EQ(applied_.back().final_n[0], 0); EXPECT_EQ(applied_.back().final_n[1], 0);
  const auto report = read_json(output_ / "session_summary.json");
  EXPECT_EQ(report.at("streams").at("applied").at("generated"), 2);
  EXPECT_EQ(report.at("streams").at("applied").at("emitted"), 2);
  usv_mpc::MpcControllerNodeTestAccess::all_output_helpers(*node_); drain(); EXPECT_EQ(left_.size(), 2u); EXPECT_EQ(right_.size(), 2u);
}
TEST_F(PublisherNode, RemovedReleaseBlocksLaterOutputAndShutdown)
{
  release(); fs::remove(release_); usv_mpc::MpcControllerNodeTestAccess::publish(*node_);
  node_->safe_shutdown(); expect_no_physical(); EXPECT_TRUE(usv_mpc::MpcControllerNodeTestAccess::failed(*node_));
}
TEST_F(PublisherNode, ShutdownLinearizedFirstPreventsConcurrentReleaseAcceptance)
{
  write_bytes(release_, release_json().dump()); TestLatch shutdown;
  usv_mpc::MpcControllerNodeTestAccess::shutdown_latch(*node_, [&]() {shutdown.block();});
  std::thread closing([&]() {node_->safe_shutdown();});
  const bool entered = shutdown.wait_entered(); EXPECT_TRUE(entered);
  EXPECT_TRUE(usv_mpc::MpcControllerNodeTestAccess::shutting_down(*node_));
  std::promise<void> poll_started; bool accepted = true;
  std::thread polling([&]() {poll_started.set_value(); accepted = usv_mpc::MpcControllerNodeTestAccess::poll(*node_);});
  poll_started.get_future().wait(); shutdown.release(); closing.join(); polling.join();
  EXPECT_FALSE(accepted); EXPECT_FALSE(fs::exists(output_ / "release_receipt.json"));
  expect_no_physical();
}
TEST_F(PublisherNode, ReleaseLinearizedFirstCommitsBeforeConcurrentRecordedShutdownZero)
{
  write_bytes(release_, release_json().dump()); usv_mpc::MpcControllerNodeTestAccess::clock(*node_);
  TestLatch release_arm; usv_mpc::MpcControllerNodeTestAccess::release_latch(*node_, [&]() {release_arm.block();});
  bool accepted = false; std::thread polling([&]() {accepted = usv_mpc::MpcControllerNodeTestAccess::poll(*node_);});
  const bool entered = release_arm.wait_entered(); EXPECT_TRUE(entered);
  EXPECT_FALSE(fs::exists(output_ / "release_receipt.json"));
  std::promise<void> shutdown_started;
  std::thread closing([&]() {shutdown_started.set_value(); node_->safe_shutdown();});
  shutdown_started.get_future().wait();
  EXPECT_FALSE(usv_mpc::MpcControllerNodeTestAccess::shutting_down(*node_));
  release_arm.release(); polling.join(); closing.join(); EXPECT_TRUE(accepted);
  ASSERT_TRUE(spin_until([this]() {return left_.size() == 1 && right_.size() == 1 && applied_.size() == 1;}));
  EXPECT_EQ(applied_.back().sequence, 1u); EXPECT_EQ(applied_.back().control_source, "shutdown_zero");
  EXPECT_TRUE(fs::exists(output_ / "release_receipt.json"));
  EXPECT_EQ(read_json(output_ / "session_summary.json").at("streams").at("applied").at("generated"), 1);
}
TEST_F(PublisherNode, ExpiredAfterPreparedReceiptNeverPublishesShutdownZero)
{
  auto v = release_json(); const int64_t until = v.at("valid_until_steady_ns");
  write_bytes(release_, v.dump()); int calls = 0;
  usv_mpc::MpcControllerNodeTestAccess::node_clock(*node_, [&]() {return ++calls <= 2 ? until - 100 : until;});
  EXPECT_FALSE(usv_mpc::MpcControllerNodeTestAccess::poll(*node_));
  EXPECT_TRUE(fs::exists(output_ / "release_receipt.json"));
  EXPECT_EQ(read_json(output_ / "release_receipt.json").at("status"), "prepared_acceptance");
  node_->safe_shutdown(); expect_no_physical();
}
}  // namespace
