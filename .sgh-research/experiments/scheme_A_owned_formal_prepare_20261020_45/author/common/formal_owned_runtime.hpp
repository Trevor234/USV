// SPDX-License-Identifier: MIT
#pragma once
#include "owned_peer_c36_v1.hpp"
#include "formal_prepare_gate_v1.hpp"
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
#include <usv_research_interfaces/msg/worker_capability.hpp>
#include <usv_research_interfaces/msg/solve_candidate.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <nav_msgs/msg/path.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <rosgraph_msgs/msg/clock.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <csignal>
#include <atomic>

namespace formal_owned {
using Json=p1_owned::Json;using p1_owned::require;
inline constexpr const char *cap_topic="/p1/worker_capability";
inline constexpr const char *candidate_topic="/p1/solve_candidate";
using Capability=usv_research_interfaces::msg::WorkerCapability;
using Candidate=usv_research_interfaces::msg::SolveCandidate;
inline rclcpp::NodeOptions node_options(){rclcpp::NodeOptions o;
  o.enable_rosout(false).start_parameter_services(false).start_parameter_event_publisher(false);return o;}
inline void entry_arguments(rclcpp::Node &node){
  for(const auto &a:p1_owned::actual_argv())require(a!="-r"&&a!="--remap"&&a.get<std::string>().find("--remap=")!=0,"formal remapping forbidden");
  require(!node.get_parameter("use_sim_time").as_bool(),"formal uses monotonic administrative time");
}
inline Json load_contract(const std::string &path,const std::string &hash,const std::string &mode){
  require(p1_owned::sha256_shape(hash),"formal contract SHA shape");
  const auto raw=c36_owned::detail::read_manifest(path);
  require(p1_owned::sha256_bytes(raw)==hash,"formal contract SHA mismatch");
  const auto c=p1::parse_unique_contract(raw);p1::formal_prepare::validate_entry(c,mode);return c;
}
inline void overrides(rclcpp::Node &node,const std::set<std::string> &names){
  for(const auto &kv:node.get_node_parameters_interface()->get_parameter_overrides())
    require(names.count(kv.first),"unknown formal startup override: "+kv.first);
}
class Source {
 public: explicit Source(const std::string &path):path_(path){
    const std::filesystem::path p(path);const auto parent=p1_owned::open_directory(p.parent_path());
    fd_.reset(::openat(parent.get(),p.filename().c_str(),O_WRONLY|O_CREAT|O_EXCL|O_APPEND|O_NOFOLLOW|O_CLOEXEC,0600));
    require(fd_.get()>=0,"formal create-only Source");
  }
  void add(Json row){
    row["source_sequence"]=++sequence_;row["source_written_ns"]=p1_owned::steady_ns();
    row["stage_qualified"]=false;row["execute_qualified"]=false;
    const auto raw=row.dump()+"\n";require(raw.size()<=262144,"formal Source row bound");size_t done=0;
    while(done<raw.size()){const auto n=::write(fd_.get(),raw.data()+done,raw.size()-done);
      if(n<0&&errno==EINTR)continue;
      if(n<=0){good_=false;throw std::runtime_error("formal Source write failed");}done+=size_t(n);}
  }
  bool good()const{return good_;}
  void finish(){require(::fsync(fd_.get())==0,"formal Source fsync");}
 private:std::string path_;c36_owned::detail::Fd fd_;uint64_t sequence_=0;bool good_=true;
};
template<class Message>inline Json cdr(const Message &m){
  rclcpp::Serialization<Message> serial;rclcpp::SerializedMessage data;serial.serialize_message(&m,&data);
  const auto &raw=data.get_rcl_serialized_message();require(raw.buffer_length<=262144,"formal CDR bound");
  return {{"bytes",raw.buffer_length},{"sha256",p1_owned::sha256_bytes(std::string(reinterpret_cast<const char*>(raw.buffer),raw.buffer_length))}};
}
inline Json read_pinned(const std::string &path,const std::string &sha){
  const auto raw=c36_owned::detail::read_manifest(path);require(p1_owned::sha256_shape(sha)&&p1_owned::sha256_bytes(raw)==sha,"formal pinned file SHA");
  return c36_owned::detail::strict_json(raw);
}
inline bool bounded(const rosgraph_msgs::msg::Clock &m){return m.clock.sec>=0&&m.clock.nanosec<1000000000;}
inline bool bounded(const nav_msgs::msg::Odometry &m){return m.header.frame_id.size()<=128&&m.child_frame_id.size()<=128&&m.header.stamp.sec>=0&&m.header.stamp.nanosec<1000000000;}
inline bool bounded(const sensor_msgs::msg::Imu &m){return m.header.frame_id.size()<=128&&m.header.stamp.sec>=0&&m.header.stamp.nanosec<1000000000;}
inline bool bounded(const nav_msgs::msg::Path &m){
  if(m.header.frame_id.size()>128||m.poses.size()>2048||m.header.stamp.sec<0||m.header.stamp.nanosec>=1000000000)return false;
  for(const auto &p:m.poses)if(p.header.frame_id.size()>128)return false;return true;
}
inline bool bounded(const std_msgs::msg::Float64MultiArray &m){
  if(m.layout.dim.size()>4||m.data.size()>8192)return false;
  for(const auto &d:m.layout.dim)if(d.label.size()>64)return false;return true;
}
inline bool bounded(const Capability &m){
  for(const auto *s:{&m.schema_version,&m.run_id,&m.boot_id,&m.contract_hash,&m.nominal_hash,&m.worker_instance,
    &m.clock_name,&m.backend,&m.matrix_layout,&m.reason})if(s->size()>128)return false;return true;
}
class Peer {
 public:
  Peer(const Json &pin,const std::string &role,const std::string &run,const std::string &contract):pin_(pin){
    path_=pin.at("manifest_path");const auto raw=c36_owned::detail::read_manifest(path_);
    require(p1_owned::sha256_bytes(raw)==pin.at("manifest_sha256"),"formal peer manifest SHA");manifest_=c36_owned::detail::strict_json(raw);
    for(const auto &kv:std::vector<std::pair<const char*,std::string>>{{"schema_version","p1-owned-role-v1"},{"role",role},
      {"run_id",run},{"boot_id",p1_owned::boot_id()},{"contract_sha256",contract}})
      require(manifest_.at(kv.first).is_string()&&manifest_.at(kv.first)==kv.second,"formal peer identity binding");
    for(const auto &key:{"pid","process_start_ticks","exe","binary_sha256","source_bundle_sha256","effective_parameters_sha256"})
      require(manifest_.at(key)==pin.at(key),"formal peer independently pinned field");
    c36_owned::detail::bool_field(manifest_,"effective_parameters_immutable",true);
    c36_owned::detail::bool_field(manifest_,"execute_qualified",false);
    c36_owned::detail::bool_field(manifest_,"physical_release_qualified",false);
    if(role!="driver"){
      c36_owned::detail::parameter_rows(manifest_.at("effective_parameters"));
      require(p1_owned::sha256_bytes(p1_owned::canonical_parameters(manifest_.at("effective_parameters")).dump())==manifest_.at("effective_parameters_sha256"),"formal effective parameter digest");
      require(manifest_.at("rmw_implementation")=="rmw_fastrtps_cpp","formal peer RMW");
    }
    process_pins_.pid=c36_owned::detail::uint_field(manifest_,"pid",INT_MAX);
    process_pins_.process_start_ticks=c36_owned::detail::uint_field(manifest_,"process_start_ticks",INT64_MAX);
    process_pins_.boot_id=p1_owned::boot_id();process_pins_.exe=manifest_.at("exe");process_pins_.binary_sha256=manifest_.at("binary_sha256");
    process_=c36_owned::detail::authenticate_process(process_pins_,manifest_);
    pidfd_.reset(int(::syscall(SYS_pidfd_open,process_pins_.pid,0)));require(pidfd_.get()>=0&&alive(),"formal peer pidfd");
    const auto again=c36_owned::detail::authenticate_process(process_pins_,manifest_);
    require(again.argv==process_.argv&&again.start==process_.start&&c36_owned::detail::read_manifest(path_)==raw,"formal peer pin changed");
  }
  bool alive()const{pollfd f{pidfd_.get(),POLLIN,0};return ::poll(&f,1,0)==0;}
  bool stable_manifest()const{return alive()&&p1_owned::file_sha256(path_)==pin_.at("manifest_sha256");}
  const Json &manifest()const{return manifest_;}
  const Json &pin()const{return pin_;}
  Json endpoint(const std::string &kind,const std::string &topic,const std::string &type)const{
    Json found;size_t count=0;
    for(const auto &e:manifest_.at("endpoints"))if(e.at("kind")==kind&&e.at("topic")==topic&&e.at("type")==type){found=e;++count;}
    require(count==1&&found.at("gid").size()==RMW_GID_STORAGE_SIZE,"formal peer exact endpoint");return found;
  }
  bool receipt(const rclcpp::MessageInfo &info,const std::string &topic,const std::string &type)const{
    const auto &m=info.get_rmw_message_info();
    return !m.from_intra_process&&m.publisher_gid.implementation_identifier&&std::string(m.publisher_gid.implementation_identifier)=="rmw_fastrtps_cpp"&&
      alive()&&endpoint("publisher",topic,type).at("gid")==p1_owned::gid_json(m.publisher_gid);
  }
  bool graph(rclcpp::Node &node,const std::string &topic,const std::string &type)const{
    const auto expected=endpoint("publisher",topic,type);const auto rows=node.get_publishers_info_by_topic(topic);
    if(rows.size()!=1||rows[0].topic_type()!=type)return false;
    Json gid=Json::array();for(auto b:rows[0].endpoint_gid())gid.push_back(unsigned(b));
    const auto full=(rows[0].node_namespace()=="/"?"/":rows[0].node_namespace()+"/")+rows[0].node_name();
    return alive()&&gid==expected.at("gid")&&full==manifest_.at("node");
  }
 private:Json pin_,manifest_;std::string path_;c36_owned::PeerPins process_pins_;
  c36_owned::detail::Process process_;c36_owned::detail::Fd pidfd_;
};
inline std::unique_ptr<Peer> driver_peer(const Json &pin,const std::string &run,const std::string &hash){
  auto peer=std::make_unique<Peer>(pin,"driver",run,hash);const auto &m=peer->manifest();
  require(m.at("tool_sha256")==P1_DRIVER_TOOL_SHA256&&p1_owned::file_sha256(m.at("tool_path"))==P1_DRIVER_TOOL_SHA256,"compiled Driver tool SHA");
  const auto argv=m.at("argv");require(argv.size()>=3&&argv[1]=="-B"&&argv[2]==m.at("tool_path"),"actual Driver script argv");
  return peer;
}
inline std::array<std::pair<std::string,std::string>,5> inputs(const Json &c){return {{{"/clock","rosgraph_msgs/msg/Clock"},
  {c.at("input_topics").at("odom"),"nav_msgs/msg/Odometry"},{c.at("input_topics").at("imu"),"sensor_msgs/msg/Imu"},
  {c.at("input_topics").at("path"),"nav_msgs/msg/Path"},{c.at("input_topics").at("profile"),"std_msgs/msg/Float64MultiArray"}}};}
inline bool forbidden_writers_absent(rclcpp::Node &node,const Json &c){
  for(const auto &topic:{std::string("/p1/solve_job"),std::string("/p1/execution_decision"),std::string("/research/control/applied"),
    c.at("output_topics").at("left").get<std::string>(),c.at("output_topics").at("right").get<std::string>()})
    if(!node.get_publishers_info_by_topic(topic).empty())return false;
  return true;
}
inline Json capability_json(const Capability &m){return {{"schema_version",m.schema_version},{"run_id",m.run_id},{"boot_id",m.boot_id},
  {"contract_hash",m.contract_hash},{"nominal_hash",m.nominal_hash},{"worker_instance",m.worker_instance},{"clock_name",m.clock_name},
  {"backend",m.backend},{"matrix_layout",m.matrix_layout},{"horizon_steps",m.horizon_steps},{"prediction_dt",m.prediction_dt},
  {"pid",m.pid},{"startup_ns",m.startup_ns},{"completed_jobs",m.completed_jobs},{"active_job",m.active_job},{"pending_count",m.pending_count},
  {"fault_injection_enabled",m.fault_injection_enabled},{"fatal",m.fatal},{"reason",m.reason}};}
} // namespace formal_owned
