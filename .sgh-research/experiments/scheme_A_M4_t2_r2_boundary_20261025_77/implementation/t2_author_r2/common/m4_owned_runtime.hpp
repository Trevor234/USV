// SPDX-License-Identifier: MIT
#pragma once
#include "formal_owned_runtime.hpp"
#include <cstdlib>
namespace m4_owned {
using Json=p1_owned::Json;
inline constexpr const char * scope="M4_owned_local_nominal_only_v1";
inline constexpr const char * frozen_index_sha="1d750a7eeb32f379f2be5dd516533f6f785e091c6b30082dda68e51b3f100081";
inline constexpr const char * frozen_contract_sha="19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a";
inline constexpr const char * owner_role="p1_owned_execute_regulator";
inline void environment(){
  for(const auto &kv:std::vector<std::pair<const char*,std::string>>{{"ROS_DOMAIN_ID","120"},{"ROS_LOCALHOST_ONLY","1"},{"RMW_IMPLEMENTATION","rmw_fastrtps_cpp"}}){
    const auto actual=std::getenv(kv.first);p1_owned::require(actual&&actual==kv.second,"M4 exact local environment");
  }
  static_assert(RMW_GID_STORAGE_SIZE==16,"M4 registered FastDDS native GID ABI changed");
}
inline void frozen(const Json &c,const std::string &hash){
  environment();
  p1_owned::require(hash==frozen_contract_sha&&p1::validate_contract_fields(c)==p1::ContractProfile::Frozen&&
    c.at("supported_parameter_profile")==p1::target_parameter_profile&&c.at("freeze_evidence_sha256")==frozen_index_sha,
    "M4 exact frozen parent contract");
}
// W1 diagnostic profile. It is a SEPARATE identity from the frozen one: its own
// contract hash, its own parameter profile and its own evidence marker. Nothing
// here relaxes frozen(); the ordinary run keeps rejecting the v4 contract and the
// diagnostic run keeps rejecting the v3 one.
inline constexpr const char * diagnostic_scope="M4_owned_diagnostic_worker_only_v1";
// R2 (batch 77): T2 boundary diagnostic scope. It uses the SAME v4 diagnostic
// contract as the W-series (the boundary mechanism requires fault injection
// permission), but registers as a separate scope so a T2-B boundary run can
// never borrow the ordinary identity and vice versa. The ordinary profile
// stays unarmed: contract() only routes this scope to the diagnostic
// validation; it does not change what the frozen scope accepts.
inline constexpr const char * t2_boundary_scope="M4_owned_t2_boundary_diagnostic_v1";
inline constexpr const char * diagnostic_parameter_profile="P1_owned_diagnostic_worker_20261021_01";
inline constexpr const char * diagnostic_policy_sha256="475d093f034165b94a09dde577a4462dc3c575752e25a99364d4ac699955918b";
inline constexpr const char * diagnostic_index_sha="d1a9f0e2b7c4a8536e0f2b9d4c7a1e5836b0d9f2c4a7e1b8369d0c5f2a8e4b71";
inline void diagnostic(const Json &c,const std::string &hash){
  environment();
  p1_owned::require(p1::validate_contract_fields(c)==p1::ContractProfile::DiagnosticExecute,
    "diagnostic run requires the v4 diagnostic profile");
  p1_owned::require(c.at("supported_parameter_profile")==diagnostic_parameter_profile,
    "diagnostic run requires the diagnostic parameter profile");
  p1_owned::require(hash.size()==64,"diagnostic contract hash must be a SHA256");
  p1_owned::require(c.at("freeze_evidence_sha256")==diagnostic_index_sha,
    "diagnostic run requires the diagnostic evidence marker");
}
inline bool diagnostic_profile(const Json &c){
  return p1::validate_contract_fields(c)==p1::ContractProfile::DiagnosticExecute;
}
inline Json contract(const std::string &path,const std::string &hash,const std::string &mode,const std::string &release_scope){
  const auto text=c36_owned::detail::read_manifest(path);
  p1_owned::require(p1_owned::sha256_bytes(text)==hash,"M4 actual contract bytes");
  const auto c=p1::parse_unique_contract(text);
  if(release_scope==diagnostic_scope||release_scope==t2_boundary_scope){
    p1_owned::require(mode=="execute","diagnostic scope requires execute mode");
    diagnostic(c,hash);p1::validate_contract_mode(c,mode);return c;
  }
  p1_owned::require(mode=="execute"&&release_scope==scope,"M4 explicit isolated nominal entry required; ordinary runtime release stays disabled");
  frozen(c,hash);p1::validate_contract_mode(c,mode);return c;
}
inline std::string gid_hex(const Json &gid){
  p1_owned::require(gid.is_array()&&gid.size()==RMW_GID_STORAGE_SIZE,"M4 actual native GID size");
  std::array<uint8_t,RMW_GID_STORAGE_SIZE> data{};bool nonzero=false;
  for(size_t i=0;i<data.size();++i){data[i]=uint8_t(c36_owned::detail::uint_field(Json{{"b",gid[i]}},"b",255));nonzero|=data[i]!=0;}
  p1_owned::require(nonzero,"M4 nonzero actual GID");return p1_owned::hex(data.data(),data.size());
}
inline Json endpoint(const Json &manifest,const std::string &kind,const std::string &topic,const std::string &type){
  Json found;size_t matches=0;
  for(const auto &ep:manifest.at("endpoints"))if(ep.at("kind")==kind&&ep.at("topic")==topic&&ep.at("type")==type){found=ep;++matches;}
  p1_owned::require(matches==1,"M4 exact manifest endpoint");gid_hex(found.at("gid"));return found;
}
inline bool graph_publisher(rclcpp::Node &node,const Json &manifest,const std::string &topic,const std::string &type){
  const auto expected=endpoint(manifest,"publisher",topic,type);const auto rows=node.get_publishers_info_by_topic(topic);
  if(rows.size()!=1||rows[0].topic_type()!=type)return false;
  Json gid=Json::array();for(auto b:rows[0].endpoint_gid())gid.push_back(unsigned(b));
  const auto full=(rows[0].node_namespace()=="/"?"/":rows[0].node_namespace()+"/")+rows[0].node_name();
  return gid==expected.at("gid")&&full==manifest.at("node");
}
inline std::array<std::pair<std::string,std::string>,5> outputs(const Json &c){return {{{"/p1/solve_job","usv_research_interfaces/msg/SolveJob"},
  {"/p1/execution_decision","usv_research_interfaces/msg/ExecutionDecision"},{"/research/control/applied","usv_research_interfaces/msg/AppliedControl"},
  {c.at("output_topics").at("left"),"std_msgs/msg/Float64"},{c.at("output_topics").at("right"),"std_msgs/msg/Float64"}}};}
inline bool graph_readers(rclcpp::Node &node,const std::string &topic,const std::string &type,const std::vector<Json> &manifests){
  std::vector<std::pair<std::string,Json>> expected;
  for(const auto &m:manifests)for(const auto &ep:m.at("endpoints"))
    if(ep.at("kind")=="subscription"&&ep.at("topic")==topic&&ep.at("type")==type)expected.push_back({m.at("node"),ep.at("gid")});
  const auto actual=node.get_subscriptions_info_by_topic(topic);if(expected.empty()||actual.size()!=expected.size())return false;
  std::vector<bool> seen(expected.size(),false);
  for(const auto &ep:actual){
    if(ep.topic_type()!=type)return false;
    Json gid=Json::array();for(auto byte:ep.endpoint_gid())gid.push_back(unsigned(byte));
    const auto full=(ep.node_namespace()=="/"?"/":ep.node_namespace()+"/")+ep.node_name();bool found=false;
    for(size_t i=0;i<expected.size();++i)if(!seen[i]&&expected[i].first==full&&expected[i].second==gid){seen[i]=true;found=true;break;}
    if(!found)return false;
  }
  return true;
}
inline Json context(const Json &own,const std::string &own_sha,const Json &c){
  // W1: the owner may declare either the ordinary scope or the diagnostic one,
  // and the diagnostic scope is only valid with the v4 profile. The role and the
  // two physical publishers are required in both cases.
  const auto declared_scope = own.at("m4_release_scope").get<std::string>();
  const bool ordinary = declared_scope == scope;
  const bool diagnostic_ok = declared_scope == diagnostic_scope && diagnostic_profile(c);
  p1_owned::require(own.at("role")==owner_role&&(ordinary||diagnostic_ok)&&
    own.at("physical_publishers")==2,"M4 actual owner role/scope");
  const auto left=endpoint(own,"publisher",c.at("output_topics").at("left"),"std_msgs/msg/Float64");
  const auto right=endpoint(own,"publisher",c.at("output_topics").at("right"),"std_msgs/msg/Float64");
  return {{"run_id",own.at("run_id")},{"boot_id",own.at("boot_id")},{"contract_sha256",own.at("contract_sha256")},
    {"freeze_evidence_sha256",diagnostic_ok?std::string(diagnostic_index_sha):std::string(frozen_index_sha)},{"policy_sha256",diagnostic_ok?std::string(diagnostic_policy_sha256):std::string(p1::target_policy_sha256)},{"regulator_manifest_sha256",own_sha},
    {"producer_id",own.at("producer_instance_id")},{"role",own.at("role")},{"pid",own.at("pid")},{"start_ticks",own.at("process_start_ticks")},
    {"output_gids",Json::array({gid_hex(left.at("gid")),gid_hex(right.at("gid"))})},
    {"old_outputs_absent",true},{"worker_output_count",0},{"fixture_output_count",0},{"recorder_output_count",0},
    {"worker_capability_live",true},{"recorder_ready",true},{"inputs_ready",true},{"source_graph_verified",true}};
}
// Context readiness booleans above are emitted only after live graph/process,
// typed source and valid callback-lease checks in the actual owner gate. They
// are not accepted as a substitute for those observations.
inline void grant_fields(const Json &g,const Json &expected_context,const Json &version,const std::string &ready_sha,
                         const Json &driver,int64_t now){
  const std::set<std::string> keys={"schema","scope","run_id","boot_id","contract_sha256","index_sha256","context",
    "version","ready_sha256","driver_manifest_sha256","issued_ns","sequence"};
  p1_owned::require(g.is_object()&&g.size()==keys.size(),"M4 grant exact population");
  for(const auto &k:keys)p1_owned::require(g.contains(k),"M4 grant missing field");
  // W1: the grant must name the scope it was issued under, and the contract and
  // evidence marker must match that scope. A diagnostic grant cannot borrow the
  // frozen identity and vice versa.
  const auto granted_scope = g.at("scope").get<std::string>();
  const bool ordinary_grant = granted_scope == scope &&
    g.at("contract_sha256") == frozen_contract_sha && g.at("index_sha256") == frozen_index_sha;
  const bool diagnostic_grant = granted_scope == diagnostic_scope &&
    g.at("index_sha256") == diagnostic_index_sha;
  p1_owned::require(g.at("schema")=="M4-owned-execute-grant-v1"&&(ordinary_grant||diagnostic_grant),
    "M4 grant scope/contract/evidence binding");
  p1_owned::require(g.at("run_id")==expected_context.at("run_id")&&g.at("boot_id")==expected_context.at("boot_id")&&
    g.at("context")==expected_context&&g.at("version")==version&&g.at("ready_sha256")==ready_sha&&
    g.at("driver_manifest_sha256")==driver.at("manifest_sha256"),"M4 grant actual identity/version/ready binding");
  p1_owned::require(c36_owned::detail::uint_field(g,"sequence",1)==1,"M4 grant one-shot sequence");
  const auto issued=c36_owned::detail::uint_field(g,"issued_ns",INT64_MAX);
  p1_owned::require(issued>0&&issued<=uint64_t(now)&&uint64_t(now)-issued<=2000000000ULL,"M4 grant issued/future/TTL");
}
} // namespace m4_owned
