// SPDX-License-Identifier: MIT
#include <gtest/gtest.h>
#include "owned_peer_c36_v1.hpp"
#include <usv_research_interfaces/msg/applied_control.hpp>
#include <rclcpp/serialization.hpp>
#include <thread>
#include <functional>

namespace {
using Json = c36_owned::Json;
using Applied = usv_research_interfaces::msg::AppliedControl;
namespace fs = std::filesystem;

class OwnedPeerTest : public ::testing::Test {
 protected:
  static void SetUpTestSuite() {
    if (!rclcpp::ok()) { int argc = 0; rclcpp::init(argc,nullptr); }
    ASSERT_EQ(p1_owned::rmw_identifier(),"rmw_fastrtps_cpp");
  }
  static void TearDownTestSuite() { if (rclcpp::ok()) rclcpp::shutdown(); }
  void SetUp() override {
    char directory[] = "/tmp/c36_owned_peer_XXXXXX";
    auto *name = ::mkdtemp(directory); ASSERT_NE(name,nullptr);
    dir_ = name; path_ = dir_ / "manifest.json";
    auto options = rclcpp::NodeOptions().enable_rosout(false).start_parameter_services(false)
      .start_parameter_event_publisher(false).use_intra_process_comms(false);
    owner_ = std::make_shared<rclcpp::Node>("c36_peer_owner",options);
    reader_ = std::make_shared<rclcpp::Node>("c36_peer_reader",options);
    owner_->declare_parameter<int64_t>("owner_test_integer",7);
    owner_->declare_parameter<std::vector<int64_t>>("owner_test_integers",{1,2});
    owner_->declare_parameter<bool>("owner_test_boolean",true);
    owner_->declare_parameter<double>("owner_test_double",0.2);
    owner_->declare_parameter<std::vector<double>>("owner_test_doubles",{0.2,0.3});
    topic_ = "/c36_owned_peer/applied_" + std::to_string(::getpid());
    pub_ = owner_->create_publisher<Applied>(topic_,rclcpp::QoS(10).reliable());
    frozen_ = p1_owned::freeze_parameters(*owner_);
    manifest_ = p1_owned::role_manifest(*owner_,"publisher","c36-peer-test",std::string(64,'a'),
      std::string(64,'b'),Json::array({p1_owned::publisher_endpoint(*pub_,
        "usv_research_interfaces/msg/AppliedControl")}),
      {{"producer_instance_id","c36-peer-producer"},{"config_hash",std::string(64,'c')}});
    pins_.manifest_path = path_.string();
    pins_.run_id = manifest_.at("run_id"); pins_.boot_id = manifest_.at("boot_id");
    pins_.contract_sha256 = manifest_.at("contract_sha256");
    pins_.producer_instance_id = manifest_.at("producer_instance_id");
    pins_.config_hash = manifest_.at("config_hash"); pins_.exe = manifest_.at("exe");
    pins_.binary_sha256 = manifest_.at("binary_sha256");
    pins_.source_bundle_sha256 = manifest_.at("source_bundle_sha256");
    pins_.effective_parameters_sha256 = manifest_.at("effective_parameters_sha256");
    pins_.pid = manifest_.at("pid").get<int64_t>();
    pins_.process_start_ticks = manifest_.at("process_start_ticks").get<uint64_t>();
    pins_.topic = topic_; pins_.type = "usv_research_interfaces/msg/AppliedControl";
    save_manifest();
  }
  void TearDown() override {
    pub_.reset(); frozen_.reset(); reader_.reset(); owner_.reset();
    if (!dir_.empty()) fs::remove_all(dir_);
  }
  void save_raw(const std::string &raw) {
    std::ofstream f(path_,std::ios::binary|std::ios::trunc); f << raw; f.close();
    pins_.manifest_sha256 = p1_owned::sha256_bytes(raw);
  }
  void save_manifest() { save_raw(manifest_.dump() + "\n"); }
  void rebind_parameters() {
    auto sha = p1_owned::sha256_bytes(p1_owned::canonical_parameters(manifest_.at("effective_parameters")).dump());
    manifest_["effective_parameters_sha256"] = sha; pins_.effective_parameters_sha256 = sha;
    save_manifest();
  }
  Json pins_json() const {
    return {{"manifest_path",pins_.manifest_path},{"manifest_sha256",pins_.manifest_sha256},
      {"run_id",pins_.run_id},{"boot_id",pins_.boot_id},{"contract_sha256",pins_.contract_sha256},
      {"producer_instance_id",pins_.producer_instance_id},{"config_hash",pins_.config_hash},
      {"exe",pins_.exe},{"binary_sha256",pins_.binary_sha256},
      {"source_bundle_sha256",pins_.source_bundle_sha256},
      {"effective_parameters_sha256",pins_.effective_parameters_sha256},{"pid",pins_.pid},
      {"process_start_ticks",pins_.process_start_ticks},{"topic",pins_.topic},{"type",pins_.type}};
  }
  rclcpp::MessageInfo info() const {
    rmw_message_info_t m{}; m.publisher_gid = pub_->get_gid();
    return rclcpp::MessageInfo(m);
  }
  bool wait_for(const std::function<bool()> &predicate,rclcpp::Executor &executor,double seconds=4) {
    const auto end = std::chrono::steady_clock::now() + std::chrono::duration<double>(seconds);
    while (std::chrono::steady_clock::now() < end) {
      executor.spin_some(); if (predicate()) return true;
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    return false;
  }
  fs::path dir_, path_;
  std::string topic_;
  rclcpp::Node::SharedPtr owner_,reader_;
  rclcpp::Publisher<Applied>::SharedPtr pub_;
  rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr frozen_;
  Json manifest_;
  c36_owned::PeerPins pins_;
};

TEST_F(OwnedPeerTest, ActualManifestProcessAndTypedParametersBind) {
  c36_owned::OwnedPeer peer(c36_owned::from_json(pins_json()));
  EXPECT_TRUE(peer.alive()); EXPECT_TRUE(peer.gid_matches(info()));
  EXPECT_TRUE(peer.callback_reason(info()).empty());
  const auto e = peer.evidence();
  EXPECT_EQ(e.at("gid"),manifest_.at("endpoints")[0].at("gid"));
  EXPECT_EQ(e.at("continuous_DDS_uniqueness"),"unknown");
  EXPECT_EQ(e.at("owner_close_intent"),"unknown");
  EXPECT_EQ(e.at("owner_endpoints_exited"),"unknown");
  EXPECT_EQ(e.at("post_pin_exec_continuity"),"unknown");
  EXPECT_EQ(e.at("plant_acceptance"),"unknown");
  EXPECT_FALSE(e.at("stage_qualified").get<bool>());
}

TEST_F(OwnedPeerTest, ActualDDSIdenticalPayloadForeignDataWriterRejected) {
  c36_owned::OwnedPeer peer(pins_);
  // A second actual DataWriter has the same node name and exactly the same
  // payload. This demonstrates why payload identity and graph names do not
  // authenticate callback ownership.
  auto other = std::make_shared<rclcpp::Node>("c36_peer_owner",
    rclcpp::NodeOptions().enable_rosout(false).start_parameter_services(false)
      .start_parameter_event_publisher(false).use_intra_process_comms(false));
  auto foreign = other->create_publisher<Applied>(topic_,rclcpp::QoS(10).reliable());
  std::vector<std::string> reasons; std::vector<std::string> payloads;
  rclcpp::Serialization<Applied> serializer;
  auto sub = reader_->create_subscription<Applied>(topic_,rclcpp::QoS(10).reliable(),
    [&](Applied::SharedPtr message,const rclcpp::MessageInfo &metadata) {
      reasons.push_back(peer.callback_reason(metadata));
      rclcpp::SerializedMessage serialized; serializer.serialize_message(message.get(),&serialized);
      const auto &cdr = serialized.get_rcl_serialized_message();
      payloads.emplace_back(reinterpret_cast<const char *>(cdr.buffer),cdr.buffer_length);
    });
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(owner_); executor.add_node(reader_); executor.add_node(other);
  ASSERT_TRUE(wait_for([&]{return pub_->get_subscription_count()==1 && foreign->get_subscription_count()==1;},executor));
  Applied message; message.schema_version="p0-contract-v1"; message.run_id=pins_.run_id;
  message.producer_instance_id=pins_.producer_instance_id; message.config_hash=pins_.config_hash;
  message.sequence=1; message.final_n={1.0,1.0};
  pub_->publish(message);
  ASSERT_TRUE(wait_for([&]{return reasons.size()==1;},executor));
  foreign->publish(message);
  ASSERT_TRUE(wait_for([&]{return reasons.size()==2;},executor));
  EXPECT_EQ(reasons[0],""); EXPECT_EQ(reasons[1],"callback_foreign_gid");
  ASSERT_EQ(payloads.size(),2U); EXPECT_EQ(payloads[0],payloads[1]);
  EXPECT_FALSE(peer.graph_matches_snapshot(*reader_));
}

TEST_F(OwnedPeerTest, ActualSingleGraphIsOnlyAnExplicitSnapshot) {
  c36_owned::OwnedPeer peer(pins_);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(owner_); executor.add_node(reader_);
  ASSERT_TRUE(wait_for([&]{return peer.graph_matches_snapshot(*reader_);},executor));
  EXPECT_EQ(peer.evidence().at("continuous_DDS_uniqueness"),"unknown");
}

TEST_F(OwnedPeerTest, CallbackForeignGidAndRmwRejected) {
  c36_owned::OwnedPeer peer(pins_);
  auto metadata=info(); metadata.get_rmw_message_info().publisher_gid.data[0]^=1;
  EXPECT_FALSE(peer.gid_matches(metadata)); EXPECT_EQ(peer.callback_reason(metadata),"callback_foreign_gid");
  metadata=info(); metadata.get_rmw_message_info().publisher_gid.implementation_identifier="other_rmw";
  EXPECT_FALSE(peer.gid_matches(metadata)); EXPECT_EQ(peer.callback_reason(metadata),"callback_rmw_implementation");
  metadata=info(); metadata.get_rmw_message_info().from_intra_process=true;
  EXPECT_FALSE(peer.gid_matches(metadata));
  EXPECT_EQ(peer.callback_reason(metadata),"callback_intra_process_outside_registered_domain");
}

TEST_F(OwnedPeerTest, PinJsonRejectsBoolFloatUnknownAndMissing) {
  auto p=pins_json(); p["pid"]=true; EXPECT_THROW(c36_owned::from_json(p),std::runtime_error);
  p=pins_json(); p["process_start_ticks"]=static_cast<double>(pins_.process_start_ticks);
  EXPECT_THROW(c36_owned::from_json(p),std::runtime_error);
  p=pins_json(); p["owner_endpoints_exited"]=true;
  EXPECT_THROW(c36_owned::from_json(p),std::runtime_error);
  p=pins_json(); p.erase("manifest_sha256"); EXPECT_THROW(c36_owned::from_json(p),std::runtime_error);
}

TEST_F(OwnedPeerTest, DuplicateJsonKeyRejectedAfterExactByteRepin) {
  auto raw=manifest_.dump(); raw.insert(1,"\"role\":\"publisher\","); save_raw(raw);
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ManifestLeafSymlinkRejected) {
  fs::rename(path_,dir_/"real.json"); fs::create_symlink(dir_/"real.json",path_);
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ManifestParentSymlinkRejected) {
  fs::create_directory_symlink(dir_,dir_/"alias"); pins_.manifest_path=(dir_/"alias"/"manifest.json").string();
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ManifestFifoRejectedWithoutBlocking) {
  fs::remove(path_); ASSERT_EQ(::mkfifo(path_.c_str(),0600),0);
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ManifestOversizeAndWrongByteShaRejected) {
  save_raw(std::string(262145,' ')); EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
  save_manifest(); pins_.manifest_sha256=std::string(64,'d');
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ProcessStartPinCannotBeReboundThroughManifestCopy) {
  ++pins_.process_start_ticks; manifest_["process_start_ticks"]=pins_.process_start_ticks; save_manifest();
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, BinaryPinCannotBeReboundThroughManifestCopy) {
  pins_.binary_sha256=std::string(64,'d'); manifest_["binary_sha256"]=pins_.binary_sha256; save_manifest();
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ExePinCannotBeReboundThroughManifestCopy) {
  pins_.exe="/tmp/c36_not_actual_exe"; manifest_["exe"]=pins_.exe; save_manifest();
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, BootPinCannotBeReboundThroughManifestCopy) {
  pins_.boot_id="other-boot"; manifest_["boot_id"]=pins_.boot_id; save_manifest();
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ManifestPidBooleanRejectedAfterByteRepin) {
  manifest_["pid"]=true; save_manifest(); EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ManifestStartFloatRejectedAfterByteRepin) {
  manifest_["process_start_ticks"]=static_cast<double>(pins_.process_start_ticks); save_manifest();
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ManifestFlagsIntegerRejectedAfterByteRepin) {
  manifest_["effective_parameters_immutable"]=1; save_manifest();
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ManifestEndpointGidBoolRejectedAfterByteRepin) {
  manifest_["endpoints"][0]["gid"][0]=true; save_manifest();
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ManifestWrongOrDuplicatedEndpointRejectedAfterByteRepin) {
  manifest_["endpoints"][0]["type"]="std_msgs/msg/Float64"; save_manifest();
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
  manifest_["endpoints"][0]["type"]=pins_.type;
  auto duplicate=manifest_["endpoints"][0]; duplicate["gid"][0]=255;
  manifest_["endpoints"].push_back(duplicate); save_manifest();
  EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ParameterBoolIntForgingRejectedAfterDigestAndByteRepin) {
  manifest_["effective_parameters"]["owner_test_boolean"]["value"]=1;
  manifest_["effective_parameters"]["owner_test_boolean"]["canonical_value"]=1;
  rebind_parameters(); EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ParameterIntegerFloatForgingRejectedAfterDigestAndByteRepin) {
  manifest_["effective_parameters"]["owner_test_integer"]["value"]=7.0;
  manifest_["effective_parameters"]["owner_test_integer"]["canonical_value"]=7.0;
  rebind_parameters(); EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, CanonicalArrayNumericTypeForgingRejectedAfterDigestAndByteRepin) {
  manifest_["effective_parameters"]["owner_test_integers"]["canonical_value"][0]=1.0;
  rebind_parameters(); EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ParameterDigestMismatchRejectedAfterByteRepin) {
  manifest_["effective_parameters"]["owner_test_integer"]["value"]=8;
  manifest_["effective_parameters"]["owner_test_integer"]["canonical_value"]=8;
  save_manifest(); EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedPeerTest, ProducerSupportDomainIsExplicitAndUntrimmed) {
  pins_.producer_instance_id=std::string(65,'p'); manifest_["producer_instance_id"]=pins_.producer_instance_id;
  save_manifest(); EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
  pins_.producer_instance_id="producer with space"; manifest_["producer_instance_id"]=pins_.producer_instance_id;
  save_manifest(); EXPECT_THROW(c36_owned::OwnedPeer peer(pins_),std::runtime_error);
}
}  // namespace
