// SPDX-License-Identifier: MIT
// Driver-declared code/run/contract pins plus actual manifest, /proc and pidfd.
#pragma once
#include "owned_peer_c36_v1.hpp"
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
namespace controlled {
using Json=p1_owned::Json;
struct ExpectedPeer {
 std::string manifest_path,role,run,contract,binary_sha,source_sha,topic,type;
};
class ExactPeer {
 public:
 explicit ExactPeer(ExpectedPeer expected):expected_(std::move(expected)) {
  using namespace c36_owned::detail;
  require(p1_owned::sha256_shape(expected_.contract)&&p1_owned::sha256_shape(expected_.binary_sha)&&p1_owned::sha256_shape(expected_.source_sha),"controlled_expected_sha");
  const auto bytes=read_manifest(expected_.manifest_path);manifest_=strict_json(bytes);manifest_sha_=p1_owned::sha256_bytes(bytes);
  for(const auto &binding:std::vector<std::pair<const char*,std::string>>{
   {"schema_version","p1-owned-role-v1"},{"role",expected_.role},{"run_id",expected_.run},
   {"boot_id",p1_owned::boot_id()},{"contract_sha256",expected_.contract},{"binary_sha256",expected_.binary_sha},
   {"source_bundle_sha256",expected_.source_sha},{"rmw_implementation","rmw_fastrtps_cpp"},
   {"effective_parameters_digest_encoding","p1-typed-ieee754-v1"}})
    require(string_field(manifest_,binding.first,256)==binding.second,std::string("controlled_manifest_")+binding.first);
  bool_field(manifest_,"effective_parameters_immutable",true);bool_field(manifest_,"execute_qualified",false);bool_field(manifest_,"physical_release_qualified",false);
  parameter_rows(manifest_.at("effective_parameters"));parameter_rows(manifest_.at("parameter_overrides"));
  require(p1_owned::sha256_bytes(p1_owned::canonical_parameters(manifest_.at("effective_parameters")).dump())==manifest_.at("effective_parameters_sha256"),"controlled_manifest_parameter_digest");
  pins_.manifest_path=expected_.manifest_path;pins_.manifest_sha256=manifest_sha_;pins_.run_id=expected_.run;
  pins_.boot_id=p1_owned::boot_id();pins_.contract_sha256=expected_.contract;pins_.binary_sha256=expected_.binary_sha;pins_.source_bundle_sha256=expected_.source_sha;
  pins_.pid=int64_t(uint_field(manifest_,"pid",INT_MAX));pins_.process_start_ticks=uint_field(manifest_,"process_start_ticks",UINT64_MAX);
  pins_.exe=string_field(manifest_,"exe",4096);pins_.effective_parameters_sha256=string_field(manifest_,"effective_parameters_sha256",64);
  require(pins_.pid>0&&pins_.process_start_ticks>0,"controlled_manifest_process_domain");
  const auto created=uint_field(manifest_,"created_steady_ns",INT64_MAX);require(created>0&&created<=uint64_t(p1_owned::steady_ns()),"controlled_manifest_creation_time");
  size_t matches=0;
  for(const auto &e:manifest_.at("endpoints"))if(e.at("kind")=="publisher"&&e.at("topic")==expected_.topic) {
   require(e.at("type")==expected_.type&&e.at("gid").is_array()&&e.at("gid").size()==gid_.size(),"controlled_endpoint_type_gid");
   bool nonzero=false;for(size_t i=0;i<gid_.size();++i){const auto v=uint_field(Json{{"b",e["gid"][i]}},"b",255);gid_[i]=uint8_t(v);nonzero=nonzero||v;}
   require(nonzero,"controlled_zero_gid");endpoint_=e;++matches;
  }
  require(matches==1,"controlled_endpoint_unique");
  process_=authenticate_process(pins_,manifest_);
  pidfd_.reset(int(::syscall(SYS_pidfd_open,pid_t(pins_.pid),0)));require(pidfd_.get()>=0,"controlled_pidfd_open");
  auto after=authenticate_process(pins_,manifest_);
  require(after.start==process_.start&&after.exe==process_.exe&&after.sha==process_.sha&&after.argv==process_.argv&&alive(),"controlled_process_changed_during_pin");
  require(read_manifest(expected_.manifest_path)==bytes,"controlled_manifest_changed_during_pin");pinned_ns_=p1_owned::steady_ns();
 }
 bool alive() const {pollfd fd{pidfd_.get(),POLLIN,0};return ::poll(&fd,1,0)==0;}
 std::string reason(const rclcpp::MessageInfo &info) const {
  const auto &m=info.get_rmw_message_info();
  if(m.from_intra_process)return "callback_intra_process";
  if(!m.publisher_gid.implementation_identifier||std::strcmp(m.publisher_gid.implementation_identifier,"rmw_fastrtps_cpp"))return "callback_rmw_implementation";
  for(size_t i=0;i<gid_.size();++i)if(m.publisher_gid.data[i]!=gid_[i])return "callback_foreign_gid";
  return alive()?"":"peer_process_exited";
 }
 Json evidence() const {return {{"schema","p1-controlled-exact-peer-v1"},{"manifest_path",expected_.manifest_path},{"manifest_sha256",manifest_sha_},{"role",expected_.role},{"run_id",expected_.run},{"contract_sha256",expected_.contract},{"binary_sha256",expected_.binary_sha},{"source_bundle_sha256",expected_.source_sha},{"pid",pins_.pid},{"process_start_ticks",pins_.process_start_ticks},{"endpoint",endpoint_},{"pinned_ns",pinned_ns_},{"pidfd_alive",alive()},{"post_pin_exec_continuity","unknown"},{"continuous_DDS_uniqueness","unknown"},{"stage_qualified",false},{"execute_qualified",false}};}
 const Json &manifest() const{return manifest_;}
 private:
 ExpectedPeer expected_;c36_owned::PeerPins pins_;Json manifest_,endpoint_;std::string manifest_sha_;std::array<uint8_t,RMW_GID_STORAGE_SIZE> gid_{};
 c36_owned::detail::Process process_;c36_owned::detail::Fd pidfd_;int64_t pinned_ns_=0;
};
template<class Message>Json receipt(const Message &message,const rclcpp::MessageInfo &info,uint64_t sequence,int64_t entry,const std::string &topic,const std::string &type) {
 rclcpp::Serialization<Message> codec;rclcpp::SerializedMessage bytes;codec.serialize_message(&message,&bytes);
 const auto &raw=bytes.get_rcl_serialized_message();const auto &meta=info.get_rmw_message_info();
 return {{"schema","p1-controlled-full-cdr-receipt-v1"},{"topic",topic},{"message_type",type},{"callback_sequence",sequence},{"entry_steady_ns",entry},
  {"publisher_gid",p1_owned::gid_json(meta.publisher_gid)},{"rmw_implementation",meta.publisher_gid.implementation_identifier?meta.publisher_gid.implementation_identifier:""},
  {"from_intra_process",meta.from_intra_process},{"source_timestamp",meta.source_timestamp},{"received_timestamp",meta.received_timestamp},
  {"publication_sequence_number",meta.publication_sequence_number},{"reception_sequence_number",meta.reception_sequence_number},
  {"cdr_bytes",raw.buffer_length},{"cdr_sha256",p1_owned::sha256_bytes(std::string(reinterpret_cast<const char*>(raw.buffer),raw.buffer_length))},
  {"cdr_hex",p1_owned::hex(raw.buffer,raw.buffer_length)}};
}
} // namespace controlled
