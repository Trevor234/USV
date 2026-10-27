// SPDX-License-Identifier: MIT
#pragma once
#include "owned_peer_c36_v1.hpp"

namespace business_start {
using Json=p1_owned::Json;
inline constexpr const char *policy="owned-prepare-before-business-v1";
inline constexpr int64_t timeout_ns=20000000000LL,request_ttl_ns=2000000000LL;
inline constexpr size_t max_bytes=8192;
inline void validate_policy(const std::string &selected,const std::string &path,int64_t timeout,
                            const std::string &mode,bool witnessed,bool fault_enabled){
  using c36_owned::detail::require;
  if(selected=="immediate"){
    require(path.empty()&&timeout==0,"business immediate must have no request/budget");return;
  }
  require(selected==policy&&mode=="shadow"&&witnessed&&fault_enabled&&timeout==timeout_ns,
          "business gate explicit witnessed diagnostic shadow scope");
  const std::filesystem::path p(path);
  require(!path.empty()&&path.size()<=4096&&path.find('\0')==std::string::npos&&p.is_absolute()&&
          p==p.lexically_normal()&&!p.filename().empty()&&p.filename()!="."&&p.filename()!="..","business gate path domain");
  const auto dir=p1_owned::open_directory(p.parent_path());struct stat st{};errno=0;
  require(::fstatat(dir.get(),p.filename().c_str(),&st,AT_SYMLINK_NOFOLLOW)==-1&&errno==ENOENT,
          "business request path must be fresh");
}
struct Identity {
  std::string run_id,boot_id,contract_sha256,driver_tool_sha256,observer_manifest_sha256,publisher_manifest_sha256;
  int64_t driver_pid=0;uint64_t driver_start_ticks=0;
};
struct Context {
  bool ready=false,worker_valid=false,worker_unusable=false,stopping=false,sink_failed=false;
  bool owner_alive=false,worker_alive=false,owner_open=false,source_eligible=false;
  std::array<bool,2> anchor_known{false,false};std::array<double,2> anchor_n{};
  std::array<uint64_t,2> anchor_sequence{};Json version;
};
struct Grant {std::string sha256;int64_t issued_ns=0,authorized_ns=0,publisher_bound_ns=0;uint64_t applied_sequence=0;};
enum class State { waiting,started,cancelled,expired,rejected };
class Gate {
 public:
  Gate(Identity id,int64_t created):id_(std::move(id)),created_(created){
    using c36_owned::detail::require;
    require(created>0&&created<=INT64_MAX-timeout_ns,"business start deadline domain");
    require(c36_owned::detail::visible_ascii(id_.run_id,128)&&c36_owned::detail::visible_ascii(id_.boot_id,64)
      &&id_.driver_pid>0&&id_.driver_pid<=INT_MAX&&id_.driver_start_ticks>0,"business start identity domain");
    for(const auto &s:{id_.contract_sha256,id_.driver_tool_sha256,id_.observer_manifest_sha256,id_.publisher_manifest_sha256})
      require(p1_owned::sha256_shape(s),"business start hash identity");
  }
  Grant open(const std::string &raw,int64_t now,const Context &c){
    using namespace c36_owned::detail;
    require(state_==State::waiting,"business start request already consumed/closed");
    require(now>=created_&&now<deadline(),"business start deadline");
    require(!raw.empty()&&raw.size()<=max_bytes,"business start request size");
    const auto j=strict_json(raw);
    const std::set<std::string> keys={"schema","run_id","boot_id","contract_sha256","driver_pid","driver_start_ticks",
      "driver_tool_sha256","observer_manifest_sha256","publisher_manifest_sha256","issued_ns","seq",
      "initial_applied_sequence","publisher_bound_ns","version","stage_qualified","execute_qualified"};
    require(j.size()==keys.size(),"business start exact request population");
    for(auto it=j.begin();it!=j.end();++it)require(keys.count(it.key())==1,"business start unknown field");
    for(const auto &kv:std::vector<std::pair<const char*,std::string>>{{"schema","p1-owned-business-start-v1"},
      {"run_id",id_.run_id},{"boot_id",id_.boot_id},{"contract_sha256",id_.contract_sha256},
      {"driver_tool_sha256",id_.driver_tool_sha256},{"observer_manifest_sha256",id_.observer_manifest_sha256},
      {"publisher_manifest_sha256",id_.publisher_manifest_sha256}})
      require(string_field(j,kv.first,128)==kv.second,std::string("business start binding:")+kv.first);
    require(uint_field(j,"driver_pid",INT_MAX)==uint64_t(id_.driver_pid)&&
      uint_field(j,"driver_start_ticks",UINT64_MAX)==id_.driver_start_ticks,"business start driver PID/start");
    require(uint_field(j,"seq",1)==1,"business start one-shot sequence");
    bool_field(j,"stage_qualified",false);bool_field(j,"execute_qualified",false);
    const auto issued=uint_field(j,"issued_ns",INT64_MAX),bound=uint_field(j,"publisher_bound_ns",INT64_MAX);
    require(issued>=uint64_t(created_)&&issued<=uint64_t(now)&&now-int64_t(issued)<=request_ttl_ns
      &&bound>0&&bound<=issued,"business start request freshness");
    const auto seq=uint_field(j,"initial_applied_sequence",UINT64_MAX);
    require(seq>0&&c.anchor_known[0]&&c.anchor_known[1]&&c.anchor_sequence[0]==seq&&c.anchor_sequence[1]==seq
      &&c.anchor_n[0]==0.&&c.anchor_n[1]==0.,"business start actual initial zero anchor");
    require(j.at("version").is_object()&&j.at("version").size()==5,"business start version fields");
    for(const auto &k:{"task","model","config","schedule","epoch"})
      require(uint_field(j.at("version"),k,UINT64_MAX)==uint_field(c.version,k,UINT64_MAX),"business start current version");
    require(c.ready&&c.worker_valid&&!c.worker_unusable&&!c.stopping&&!c.sink_failed&&c.owner_alive&&c.worker_alive
      &&c.owner_open&&c.source_eligible,"business start live original prerequisites");
    Grant grant{p1_owned::sha256_bytes(raw),int64_t(issued),now,int64_t(bound),seq};
    state_=State::started;started_ns_=now;return grant;
  }
  void close(int64_t now,State state){
    c36_owned::detail::require(state!=State::waiting&&state!=State::started&&now>=created_,"business close state");
    state_=state;closed_ns_=now;
  }
  bool expired(int64_t now)const{return state_==State::waiting&&now>=deadline();}
  bool started()const{return state_==State::started;}
  State state()const{return state_;}
  int64_t deadline()const{return created_+timeout_ns;}
  Json evidence()const{return {{"policy",policy},{"state",state_==State::waiting?"waiting":state_==State::started?"started":state_==State::cancelled?"cancelled":state_==State::expired?"expired":"rejected"},
    {"created_ns",created_},{"deadline_ns",deadline()},{"started_ns",started_ns_},{"closed_ns",closed_ns_},
    {"stage_qualified",false},{"execute_qualified",false}};}
 private:Identity id_;int64_t created_=0,started_ns_=0,closed_ns_=0;State state_=State::waiting;
};
}
