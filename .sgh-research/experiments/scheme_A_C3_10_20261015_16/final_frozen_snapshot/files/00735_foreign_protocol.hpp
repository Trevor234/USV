// SPDX-License-Identifier: MIT
// Bounded independent diagnostic producer; this contract confers no owner role.
#pragma once
#include "p1_owned_identity.hpp"
#include <rclcpp/serialization.hpp>
#include <usv_research_interfaces/msg/applied_control.hpp>
#include <set>
namespace c310 {
using Json=p1_owned::Json;
using Applied=usv_research_interfaces::msg::AppliedControl;
inline Json strict_json(const std::string &s){
  p1_owned::require(!s.empty()&&s.size()<=65536,"JSON input bound");
  std::vector<std::set<std::string>> keys;
  return Json::parse(s,[&](int,Json::parse_event_t e,Json &v){
    if(e==Json::parse_event_t::object_start)keys.emplace_back();
    if(e==Json::parse_event_t::key)p1_owned::require(!keys.empty()&&keys.back().insert(v.get<std::string>()).second,"duplicate JSON key");
    if(e==Json::parse_event_t::object_end){p1_owned::require(!keys.empty(),"JSON object scope");keys.pop_back();}
    return true;
  });
}
inline void keyset(const Json &j,std::initializer_list<const char*> names){
  p1_owned::require(j.is_object()&&j.size()==names.size(),"exact object field count");
  for(auto s:names)p1_owned::require(j.contains(s),std::string("missing field ")+s);
}
inline uint64_t uint(const Json &j,const char *k){
  const auto &v=j.at(k);p1_owned::require(v.is_number_integer()&&!(v.is_number_integer()&&!v.is_number_unsigned()&&v.get<int64_t>()<0),std::string("unsigned integer ")+k);
  const auto n=v.get<uint64_t>();p1_owned::require(n>0&&n<=uint64_t(INT64_MAX),std::string("positive finite integer ")+k);return n;
}
inline std::string text(const Json &j,const char *k,size_t limit=128){
  p1_owned::require(j.at(k).is_string(),std::string("text ")+k);auto s=j.at(k).get<std::string>();
  p1_owned::require(!s.empty()&&s.size()<=limit&&std::all_of(s.begin(),s.end(),[](unsigned char c){return c>=33&&c<=126;}),std::string("visible bounded text ")+k);return s;
}
inline std::string hash(const Json &j,const char *k){auto s=text(j,k,64);p1_owned::require(p1_owned::sha256_shape(s),std::string("SHA256 ")+k);return s;}
inline std::string unhex(const std::string &hex){
  p1_owned::require(!hex.empty()&&hex.size()%2==0&&hex.size()<=16384&&hex.find_first_not_of("0123456789abcdef")==std::string::npos,"bounded lowercase CDR hex");
  std::string out;out.reserve(hex.size()/2);for(size_t i=0;i<hex.size();i+=2)out.push_back(char(std::stoul(hex.substr(i,2),nullptr,16)));return out;
}
inline rclcpp::SerializedMessage serialized(const std::string &bytes){
  rclcpp::SerializedMessage out(bytes.size());auto &r=out.get_rcl_serialized_message();std::memcpy(r.buffer,bytes.data(),bytes.size());r.buffer_length=bytes.size();return out;
}
inline Applied decode(const std::string &bytes){auto raw=serialized(bytes);Applied m;rclcpp::Serialization<Applied> s;s.deserialize_message(&raw,&m);return m;}
inline std::string encode(const Applied &m){rclcpp::SerializedMessage raw;rclcpp::Serialization<Applied> s;s.serialize_message(&m,&raw);const auto &r=raw.get_rcl_serialized_message();return std::string(reinterpret_cast<const char*>(r.buffer),r.buffer_length);}
inline std::string submitted_cdr(const std::string &application){
  p1_owned::require(!application.empty()&&application.size()<=8192,"bounded application CDR before submission");
  const size_t padding=(4-application.size()%4)%4;
  p1_owned::require(application.size()+padding<=8192,"bounded aligned submission CDR");
  return application+std::string(padding,'\0');
}
inline void contract(const Json &j){
  keyset(j,{"schema","topic","ros_type","packet_labels","max_packets","max_cdr_bytes","nonzero_final_n","physical_publisher_endpoints","stage_qualified","execute_qualified","submission_alignment_bytes","submission_padding_policy"});
  p1_owned::require(j.at("schema")=="p1-C3.10-foreign-Applied-contract-v2"&&j.at("topic")=="/research/control/applied"&&j.at("ros_type")=="usv_research_interfaces/msg/AppliedControl","independent diagnostic contract identity");
  p1_owned::require(j.at("packet_labels")==Json::array({"clone_zero_first","clone_nonzero","clone_zero_repeat"})&&j.at("max_packets").is_number_integer()&&j.at("max_packets")==3&&j.at("max_cdr_bytes").is_number_integer()&&j.at("max_cdr_bytes")==8192,"fixed finite producer population");
  p1_owned::require(j.at("submission_alignment_bytes").is_number_integer()&&j.at("submission_alignment_bytes")==4&&j.at("submission_padding_policy").is_string()&&j.at("submission_padding_policy")=="explicit-zero-fill-before-native-publish","explicit finite submission alignment policy");
  const auto &n=j.at("nonzero_final_n");p1_owned::require(n.is_array()&&n.size()==2&&n[0].is_number_float()&&n[1].is_number_float()&&n[0].get<double>()==1.0&&n[1].get<double>()==-1.0,"fixed diagnostic nonzero final_n");
  p1_owned::require(j.at("physical_publisher_endpoints").is_number_integer()&&j.at("physical_publisher_endpoints")==0&&j.at("stage_qualified").is_boolean()&&j.at("stage_qualified")==false&&j.at("execute_qualified").is_boolean()&&j.at("execute_qualified")==false,"no execution authority");
}
inline std::string command(const Json &j,const std::string &run,const std::string &boot){
  keyset(j,{"schema","run_id","boot_id","original_owner_manifest_sha256","original_applied_cdr_hex","original_applied_cdr_sha256","driver_pid","driver_start_ticks","driver_tool_sha256","close_request_sha256","close_observed_ns","owner_exit_proof_sha256"});
  p1_owned::require(j.at("schema")=="p1-C3.10-foreign-Applied-command-v1"&&text(j,"run_id")==run&&text(j,"boot_id")==boot,"foreign command identity");
  for(auto k:{"original_owner_manifest_sha256","original_applied_cdr_sha256","driver_tool_sha256","close_request_sha256","owner_exit_proof_sha256"})hash(j,k);
  p1_owned::require(uint(j,"driver_pid")<=INT_MAX,"driver PID bound");uint(j,"driver_start_ticks");uint(j,"close_observed_ns");
  p1_owned::require(j.at("original_applied_cdr_hex").is_string(),"CDR text type");auto bytes=unhex(j.at("original_applied_cdr_hex").get<std::string>());
  p1_owned::require(p1_owned::sha256_bytes(bytes)==j.at("original_applied_cdr_sha256"),"original CDR SHA differs");
  auto m=decode(bytes);p1_owned::require(m.sequence>0&&m.control_source=="shutdown_zero"&&std::isfinite(m.final_n[0])&&std::isfinite(m.final_n[1])&&m.final_n[0]==0.0&&m.final_n[1]==0.0&&m.left_publish_success&&m.right_publish_success,"original observed terminal zero domain");return bytes;
}
inline void emit(const Json &j,const Json &command,const std::string &command_sha,const std::string &manifest_sha,uint64_t now){
  keyset(j,{"schema","run_id","boot_id","driver_pid","driver_start_ticks","driver_tool_sha256","command_sha256","foreign_manifest_sha256","issued_ns"});
  p1_owned::require(j.at("schema")=="p1-C3.10-foreign-Applied-emit-v1","emit schema");
  for(auto k:{"run_id","boot_id","driver_tool_sha256"})p1_owned::require(text(j,k)==text(command,k),std::string("emit text identity ")+k);
  for(auto k:{"driver_pid","driver_start_ticks"})p1_owned::require(uint(j,k)==uint(command,k),std::string("emit integer identity ")+k);
  p1_owned::require(hash(j,"command_sha256")==command_sha&&hash(j,"foreign_manifest_sha256")==manifest_sha,"emit immutable file binding");
  const auto issued=uint(j,"issued_ns");p1_owned::require(issued<=now&&now-issued<=3500000000ULL&&issued>=uint(command,"close_observed_ns"),"finite post-close emit time");
}
} // namespace c310
