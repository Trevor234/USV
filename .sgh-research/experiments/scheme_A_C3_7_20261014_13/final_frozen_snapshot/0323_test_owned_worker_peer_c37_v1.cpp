// SPDX-License-Identifier: MIT
#include <gtest/gtest.h>
#include "owned_worker_peer_c37_v1.hpp"
#include <usv_research_interfaces/msg/worker_capability.hpp>
#include <usv_research_interfaces/msg/solve_candidate.hpp>
#include <rclcpp/serialization.hpp>
#include <thread>
#include <functional>

namespace {
using Json = c37_owned::Json;
using Interface = c37_owned::Interface;
using Capability = usv_research_interfaces::msg::WorkerCapability;
using Candidate = usv_research_interfaces::msg::SolveCandidate;
namespace fs = std::filesystem;

class OwnedWorkerPeerTest : public ::testing::Test {
 protected:
  static void SetUpTestSuite() {
    if (!rclcpp::ok()) { int argc = 0; rclcpp::init(argc,nullptr); }
    ASSERT_EQ(p1_owned::rmw_identifier(),"rmw_fastrtps_cpp");
  }
  static void TearDownTestSuite() { if (rclcpp::ok()) rclcpp::shutdown(); }
  static rclcpp::NodeOptions options() {
    return rclcpp::NodeOptions().enable_rosout(false).start_parameter_services(false)
      .start_parameter_event_publisher(false).use_intra_process_comms(false);
  }
  void SetUp() override {
    char directory[] = "/tmp/c37_owned_worker_XXXXXX";
    auto *name = ::mkdtemp(directory); ASSERT_NE(name,nullptr);
    dir_ = name; path_ = dir_ / "manifest.json";
    owner_ = std::make_shared<rclcpp::Node>("c37_worker_owner",options());
    reader_ = std::make_shared<rclcpp::Node>("c37_worker_reader",options());
    owner_->declare_parameter<std::string>("run_id","c37-worker-test");
    owner_->declare_parameter<std::string>("contract_hash",std::string(64,'a'));
    owner_->declare_parameter<std::string>("owned_manifest_file",path_.string());
    owner_->declare_parameter<int64_t>("test_integer",7);
    owner_->declare_parameter<std::vector<int64_t>>("test_integers",{1,2});
    owner_->declare_parameter<bool>("test_boolean",true);
    owner_->declare_parameter<double>("test_double",0.2);
    owner_->declare_parameter<std::vector<double>>("test_doubles",{0.2,0.3});
    const auto suffix = std::to_string(::getpid());
    capability_topic_ = "/c37_owned_worker/capability_" + suffix;
    candidate_topic_ = "/c37_owned_worker/candidate_" + suffix;
    capability_pub_ = owner_->create_publisher<Capability>(capability_topic_,rclcpp::QoS(10).reliable());
    candidate_pub_ = owner_->create_publisher<Candidate>(candidate_topic_,rclcpp::QoS(10).reliable());
    frozen_ = p1_owned::freeze_parameters(*owner_);
    manifest_ = p1_owned::role_manifest(*owner_,"worker","c37-worker-test",std::string(64,'a'),
      std::string(64,'b'),Json::array({
        p1_owned::publisher_endpoint(*capability_pub_,"usv_research_interfaces/msg/WorkerCapability"),
        p1_owned::publisher_endpoint(*candidate_pub_,"usv_research_interfaces/msg/SolveCandidate")}),
      {{"worker_instance",std::string(64,'c')},{"nominal_hash",std::string(64,'d')},
       {"contract_configuration",{{"nominal_hash",std::string(64,'d')},{"execute_qualified",false}}}});
    pins_.manifest_path = path_.string();
    pins_.run_id = manifest_.at("run_id"); pins_.boot_id = manifest_.at("boot_id");
    pins_.contract_sha256 = manifest_.at("contract_sha256");
    pins_.worker_instance = manifest_.at("worker_instance"); pins_.nominal_hash = manifest_.at("nominal_hash");
    pins_.exe = manifest_.at("exe"); pins_.binary_sha256 = manifest_.at("binary_sha256");
    pins_.source_bundle_sha256 = manifest_.at("source_bundle_sha256");
    pins_.effective_parameters_sha256 = manifest_.at("effective_parameters_sha256");
    pins_.pid = manifest_.at("pid").get<int64_t>();
    pins_.process_start_ticks = manifest_.at("process_start_ticks").get<uint64_t>();
    pins_.capability_topic = capability_topic_; pins_.candidate_topic = candidate_topic_;
    save_manifest();
  }
  void TearDown() override {
    capability_pub_.reset(); candidate_pub_.reset(); frozen_.reset(); reader_.reset(); owner_.reset();
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
      {"worker_instance",pins_.worker_instance},{"nominal_hash",pins_.nominal_hash},
      {"exe",pins_.exe},{"binary_sha256",pins_.binary_sha256},
      {"source_bundle_sha256",pins_.source_bundle_sha256},
      {"effective_parameters_sha256",pins_.effective_parameters_sha256},{"pid",pins_.pid},
      {"process_start_ticks",pins_.process_start_ticks},
      {"capability_topic",pins_.capability_topic},{"capability_type",pins_.capability_type},
      {"candidate_topic",pins_.candidate_topic},{"candidate_type",pins_.candidate_type}};
  }
  rclcpp::MessageInfo info(Interface interface) const {
    rmw_message_info_t m{};
    m.publisher_gid = interface == Interface::Capability ? capability_pub_->get_gid() : candidate_pub_->get_gid();
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
  std::string capability_topic_,candidate_topic_;
  rclcpp::Node::SharedPtr owner_,reader_;
  rclcpp::Publisher<Capability>::SharedPtr capability_pub_;
  rclcpp::Publisher<Candidate>::SharedPtr candidate_pub_;
  rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr frozen_;
  Json manifest_;
  c37_owned::WorkerPins pins_;
};

TEST_F(OwnedWorkerPeerTest, WorkerRoleManifestProcessAndBothTypedEndpointsBind) {
  c37_owned::OwnedWorkerPeer peer(c37_owned::WorkerPins::from_json(pins_json()));
  EXPECT_TRUE(peer.alive());
  EXPECT_TRUE(peer.gid_matches(info(Interface::Capability),Interface::Capability));
  EXPECT_TRUE(peer.gid_matches(info(Interface::Candidate),Interface::Candidate));
  EXPECT_TRUE(peer.callback_reason(info(Interface::Capability),Interface::Capability).empty());
  EXPECT_TRUE(peer.callback_reason(info(Interface::Candidate),Interface::Candidate).empty());
  const auto e = peer.evidence();
  EXPECT_EQ(e.at("worker_instance"),pins_.worker_instance);
  EXPECT_EQ(e.at("nominal_hash"),pins_.nominal_hash);
  EXPECT_EQ(e.at("endpoints").at("capability").at("gid"),manifest_.at("endpoints")[0].at("gid"));
  EXPECT_EQ(e.at("endpoints").at("candidate").at("gid"),manifest_.at("endpoints")[1].at("gid"));
  EXPECT_EQ(e.at("continuous_DDS_uniqueness"),"unknown");
  EXPECT_EQ(e.at("worker_close_intent"),"unknown"); EXPECT_EQ(e.at("worker_endpoints_exited"),"unknown");
  EXPECT_EQ(e.at("post_pin_exec_continuity"),"unknown"); EXPECT_EQ(e.at("plant_acceptance"),"unknown");
  EXPECT_FALSE(e.at("stage_qualified").get<bool>());
  EXPECT_FALSE(e.at("execute_qualified").get<bool>());
  EXPECT_FALSE(e.at("physical_release_qualified").get<bool>());
}

TEST_F(OwnedWorkerPeerTest, ActualDDSBothInterfacesIdenticalPayloadForeignDataWritersRejected) {
  c37_owned::OwnedWorkerPeer peer(pins_);
  // The second participant deliberately has the same node name. Each pair
  // publishes identical typed payload/CDR through different actual DataWriters.
  auto other = std::make_shared<rclcpp::Node>("c37_worker_owner",options());
  auto foreign_cap = other->create_publisher<Capability>(capability_topic_,rclcpp::QoS(10).reliable());
  auto foreign_cand = other->create_publisher<Candidate>(candidate_topic_,rclcpp::QoS(10).reliable());
  std::vector<std::string> cap_reasons,cand_reasons,cap_payloads,cand_payloads,swapped_reasons;
  rclcpp::Serialization<Capability> cap_serializer;
  rclcpp::Serialization<Candidate> cand_serializer;
  auto cap_sub = reader_->create_subscription<Capability>(capability_topic_,rclcpp::QoS(10).reliable(),
    [&](Capability::SharedPtr message,const rclcpp::MessageInfo &metadata) {
      cap_reasons.push_back(peer.callback_reason(metadata,Interface::Capability));
      swapped_reasons.push_back(peer.callback_reason(metadata,Interface::Candidate));
      rclcpp::SerializedMessage serialized; cap_serializer.serialize_message(message.get(),&serialized);
      const auto &cdr = serialized.get_rcl_serialized_message();
      cap_payloads.emplace_back(reinterpret_cast<const char *>(cdr.buffer),cdr.buffer_length);
    });
  auto cand_sub = reader_->create_subscription<Candidate>(candidate_topic_,rclcpp::QoS(10).reliable(),
    [&](Candidate::SharedPtr message,const rclcpp::MessageInfo &metadata) {
      cand_reasons.push_back(peer.callback_reason(metadata,Interface::Candidate));
      swapped_reasons.push_back(peer.callback_reason(metadata,Interface::Capability));
      rclcpp::SerializedMessage serialized; cand_serializer.serialize_message(message.get(),&serialized);
      const auto &cdr = serialized.get_rcl_serialized_message();
      cand_payloads.emplace_back(reinterpret_cast<const char *>(cdr.buffer),cdr.buffer_length);
    });
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(owner_); executor.add_node(reader_); executor.add_node(other);
  ASSERT_TRUE(wait_for([&]{return capability_pub_->get_subscription_count()==1 &&
    candidate_pub_->get_subscription_count()==1 && foreign_cap->get_subscription_count()==1 &&
    foreign_cand->get_subscription_count()==1;},executor));
  Capability cap; cap.schema_version="p1-worker-capability-v1"; cap.run_id=pins_.run_id;
  cap.worker_instance=pins_.worker_instance; cap.nominal_hash=pins_.nominal_hash; cap.pid=pins_.pid;
  Candidate cand; cand.worker_instance=pins_.worker_instance; cand.first_control={1.0,1.0};
  capability_pub_->publish(cap); candidate_pub_->publish(cand);
  ASSERT_TRUE(wait_for([&]{return cap_reasons.size()==1 && cand_reasons.size()==1;},executor));
  foreign_cap->publish(cap); foreign_cand->publish(cand);
  ASSERT_TRUE(wait_for([&]{return cap_reasons.size()==2 && cand_reasons.size()==2;},executor));
  EXPECT_EQ(cap_reasons[0],""); EXPECT_EQ(cap_reasons[1],"callback_foreign_gid");
  EXPECT_EQ(cand_reasons[0],""); EXPECT_EQ(cand_reasons[1],"callback_foreign_gid");
  EXPECT_EQ(cap_payloads[0],cap_payloads[1]); EXPECT_EQ(cand_payloads[0],cand_payloads[1]);
  for (const auto &reason : swapped_reasons) EXPECT_EQ(reason,"callback_foreign_gid");
  EXPECT_FALSE(peer.graph_matches_snapshot(*reader_));
}

TEST_F(OwnedWorkerPeerTest, ActualUniqueGraphChecksBothInterfacesAtOneExplicitSnapshot) {
  c37_owned::OwnedWorkerPeer peer(pins_);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(owner_); executor.add_node(reader_);
  ASSERT_TRUE(wait_for([&]{return peer.graph_matches_snapshot(*reader_);},executor));
  EXPECT_EQ(peer.evidence().at("continuous_DDS_uniqueness"),"unknown");
}
TEST_F(OwnedWorkerPeerTest, CallbackSwappedInterfaceForeignGidAndRmwRejected) {
  c37_owned::OwnedWorkerPeer peer(pins_);
  EXPECT_EQ(peer.callback_reason(info(Interface::Capability),Interface::Candidate),"callback_foreign_gid");
  EXPECT_EQ(peer.callback_reason(info(Interface::Candidate),Interface::Capability),"callback_foreign_gid");
  for (const auto interface : {Interface::Capability,Interface::Candidate}) {
    auto metadata=info(interface); metadata.get_rmw_message_info().publisher_gid.data[0]^=1;
    EXPECT_FALSE(peer.gid_matches(metadata,interface));
    EXPECT_EQ(peer.callback_reason(metadata,interface),"callback_foreign_gid");
    metadata=info(interface); metadata.get_rmw_message_info().publisher_gid.implementation_identifier="other_rmw";
    EXPECT_EQ(peer.callback_reason(metadata,interface),"callback_rmw_implementation");
    metadata=info(interface); metadata.get_rmw_message_info().from_intra_process=true;
    EXPECT_EQ(peer.callback_reason(metadata,interface),"callback_intra_process_outside_registered_domain");
  }
  EXPECT_EQ(peer.callback_reason(info(Interface::Capability),static_cast<Interface>(17)),"callback_interface_domain");
}
TEST_F(OwnedWorkerPeerTest, PinJsonRejectsBoolFloatPublisherFieldsUnknownAndMissing) {
  auto p=pins_json(); p["pid"]=true; EXPECT_THROW(c37_owned::from_json(p),std::runtime_error);
  p=pins_json(); p["process_start_ticks"]=static_cast<double>(pins_.process_start_ticks);
  EXPECT_THROW(c37_owned::from_json(p),std::runtime_error);
  p=pins_json(); p["producer_instance_id"]="borrowed"; EXPECT_THROW(c37_owned::from_json(p),std::runtime_error);
  p=pins_json(); p["worker_endpoints_exited"]=true; EXPECT_THROW(c37_owned::from_json(p),std::runtime_error);
  p=pins_json(); p.erase("manifest_sha256"); EXPECT_THROW(c37_owned::from_json(p),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, FixedInterfaceTypesCannotBorrowPublisherApplied) {
  pins_.capability_type="usv_research_interfaces/msg/AppliedControl";
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
  pins_.capability_type="usv_research_interfaces/msg/WorkerCapability";
  pins_.candidate_type=pins_.capability_type;
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, DuplicateJsonKeyRejectedAfterExactByteRepin) {
  auto raw=manifest_.dump(); raw.insert(1,"\"role\":\"worker\","); save_raw(raw);
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, ManifestLeafSymlinkRejected) {
  fs::rename(path_,dir_/"real.json"); fs::create_symlink(dir_/"real.json",path_);
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, ManifestParentSymlinkRejected) {
  fs::create_directory_symlink(dir_,dir_/"alias"); pins_.manifest_path=(dir_/"alias"/"manifest.json").string();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, ManifestFifoRejectedWithoutBlocking) {
  fs::remove(path_); ASSERT_EQ(::mkfifo(path_.c_str(),0600),0);
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, ManifestOversizeAndWrongByteShaRejected) {
  save_raw(std::string(262145,' ')); EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
  save_manifest(); pins_.manifest_sha256=std::string(64,'e');
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, WrongRoleRejectedAfterCoherentByteRepin) {
  manifest_["role"]="publisher"; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, BorrowedPublisherIdentityRejectedEvenInWorkerRole) {
  manifest_["producer_instance_id"]="borrowed-publisher"; manifest_["config_hash"]=std::string(64,'e');
  save_manifest(); EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, WrongWorkerInstanceAndNominalPinsRejected) {
  auto actual=manifest_; manifest_["worker_instance"]=std::string(64,'e'); save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
  manifest_=actual; manifest_["nominal_hash"]=std::string(64,'e'); save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, CoherentTopNominalRebindCannotLeaveWrongContractNominal) {
  pins_.nominal_hash=std::string(64,'e'); manifest_["nominal_hash"]=pins_.nominal_hash; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, CoherentParameterDigestRebindCannotLeaveWrongRun) {
  manifest_["effective_parameters"]["run_id"]["value"]="wrong-run";
  manifest_["effective_parameters"]["run_id"]["canonical_value"]="wrong-run";
  rebind_parameters(); EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, CoherentParameterDigestRebindCannotLeaveWrongContract) {
  manifest_["effective_parameters"]["contract_hash"]["value"]=std::string(64,'e');
  manifest_["effective_parameters"]["contract_hash"]["canonical_value"]=std::string(64,'e');
  rebind_parameters(); EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, CoherentParameterDigestRebindCannotLeaveWrongManifestPath) {
  manifest_["effective_parameters"]["owned_manifest_file"]["value"]="/tmp/wrong-worker.json";
  manifest_["effective_parameters"]["owned_manifest_file"]["canonical_value"]="/tmp/wrong-worker.json";
  rebind_parameters(); EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, ProcessStartPinCannotBeReboundThroughManifestCopy) {
  ++pins_.process_start_ticks; manifest_["process_start_ticks"]=pins_.process_start_ticks; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, BinaryPinCannotBeReboundThroughManifestCopy) {
  pins_.binary_sha256=std::string(64,'e'); manifest_["binary_sha256"]=pins_.binary_sha256; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, ExePinCannotBeReboundThroughManifestCopy) {
  pins_.exe="/tmp/c37_not_actual_exe"; manifest_["exe"]=pins_.exe; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, BootPinCannotBeReboundThroughManifestCopy) {
  pins_.boot_id="other-boot"; manifest_["boot_id"]=pins_.boot_id; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, ManifestPidBooleanAndStartFloatRejectedAfterByteRepin) {
  auto actual=manifest_; manifest_["pid"]=true; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
  manifest_=actual; manifest_["process_start_ticks"]=static_cast<double>(pins_.process_start_ticks); save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, ManifestFlagsAndContractFlagsIntegerRejectedAfterByteRepin) {
  auto actual=manifest_; manifest_["effective_parameters_immutable"]=1; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
  manifest_=actual; manifest_["contract_configuration"]["execute_qualified"]=0; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, EndpointGidBoolAndMissingInterfaceRejectedAfterByteRepin) {
  auto actual=manifest_; manifest_["endpoints"][0]["gid"][0]=true; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
  manifest_=actual; manifest_["endpoints"].erase(1); save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, EndpointWrongTypeAndDuplicateInterfaceRejectedAfterByteRepin) {
  auto actual=manifest_; manifest_["endpoints"][0]["type"]=pins_.candidate_type; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
  manifest_=actual; auto duplicate=manifest_["endpoints"][0]; duplicate["gid"][0]=255;
  manifest_["endpoints"].push_back(duplicate); save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, BothInterfacesCannotShareSameDataWriterGid) {
  manifest_["endpoints"][1]["gid"]=manifest_["endpoints"][0]["gid"]; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, ParameterBoolIntForgingRejectedAfterDigestAndByteRepin) {
  manifest_["effective_parameters"]["test_boolean"]["value"]=1;
  manifest_["effective_parameters"]["test_boolean"]["canonical_value"]=1;
  rebind_parameters(); EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, ParameterIntegerFloatForgingRejectedAfterDigestAndByteRepin) {
  manifest_["effective_parameters"]["test_integer"]["value"]=7.0;
  manifest_["effective_parameters"]["test_integer"]["canonical_value"]=7.0;
  rebind_parameters(); EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, CanonicalArrayNumericTypeForgingRejectedAfterDigestAndByteRepin) {
  manifest_["effective_parameters"]["test_integers"]["canonical_value"][0]=1.0;
  rebind_parameters(); EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, ParameterDigestMismatchRejectedAfterByteRepin) {
  manifest_["effective_parameters"]["test_integer"]["value"]=8;
  manifest_["effective_parameters"]["test_integer"]["canonical_value"]=8;
  save_manifest(); EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
TEST_F(OwnedWorkerPeerTest, WorkerSupportDomainIsExplicitAndUntrimmed) {
  pins_.worker_instance=std::string(65,'p'); manifest_["worker_instance"]=pins_.worker_instance; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
  pins_.worker_instance="worker with space"; manifest_["worker_instance"]=pins_.worker_instance; save_manifest();
  EXPECT_THROW(c37_owned::OwnedWorkerPeer peer(pins_),std::runtime_error);
}
}  // namespace
