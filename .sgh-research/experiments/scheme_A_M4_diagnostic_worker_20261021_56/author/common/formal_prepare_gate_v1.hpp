// SPDX-License-Identifier: MIT
#pragma once
#include "p1_full_contract.hpp"
#include <algorithm>
#include <climits>

// Pure policy core for a NEW formal no_output preparation role. The future
// owned adapter must derive Context from actual authenticated receipts and
// endpoints. Context supplied by a test is not live endpoint authentication.
// This gate never submits a job, produces a Decision, or supplies a command
// anchor. "prepared" only permits a bounded preparation/close proof.
namespace p1::formal_prepare {
using Json=nlohmann::json;
inline constexpr const char *policy="owned-formal-no-output-prepare-close-v1";
inline constexpr const char *scope="bounded_prepare_close_only";
inline constexpr int64_t prepare_timeout_ns=20000000000LL;
inline constexpr int64_t request_ttl_ns=2000000000LL;
inline constexpr size_t request_max_bytes=8192;

inline void require(bool value,const std::string &why){contract_require(value,"formal prepare: "+why);}
inline bool text(const std::string &s,size_t limit){
  return !s.empty()&&s.size()<=limit&&std::all_of(s.begin(),s.end(),[](unsigned char c){return c>=33&&c<=126;});
}
inline bool sha(const std::string &s){return s.size()==64&&s.find_first_not_of("0123456789abcdef")==std::string::npos;}
inline void exact(const Json &j,const std::set<std::string> &keys,const char *what){
  require(j.is_object()&&j.size()==keys.size(),std::string(what)+" exact field count");
  for(const auto &k:keys)require(j.contains(k),std::string(what)+" missing field "+k);
}
inline int64_t integer(const Json &j,const char *key,int64_t lower,int64_t upper=INT64_MAX){
  require(j.contains(key)&&strict_i64(j.at(key)),std::string("int64 required: ")+key);
  const auto value=j.at(key).get<int64_t>();
  require(value>=lower&&value<=upper,std::string("integer range: ")+key);return value;
}
inline void same_text(const Json &j,const char *key,const std::string &expected){
  require(j.contains(key)&&j.at(key).is_string()&&j.at(key)==expected,std::string("binding: ")+key);
}
inline void false_flag(const Json &j,const char *key){
  require(j.at(key).is_boolean()&&!j.at(key).get<bool>(),std::string("false boolean required: ")+key);
}
inline void validate_entry(const Json &contract,const std::string &mode){
  require(mode=="no_output","only no_output entry permitted");
  require_runtime_contract_mode(contract,mode);
  require(validate_contract_fields(contract)==ContractProfile::PreFreeze,"pre-freeze only; no diagnostic or Frozen promotion");
}

struct Identity {
  std::string run_id,boot_id,contract_sha256,preparer_manifest_sha256;
  int64_t driver_pid=0,driver_start_ticks=0;
  std::string driver_exe_sha256,driver_argv_sha256,driver_tool_sha256;
  std::string worker_manifest_sha256,fixture_manifest_sha256,recorder_manifest_sha256;
};
struct Context {
  // These booleans are adapter facts, NEVER trusted request fields. The adapter
  // must check pidfd/process identity, effective-config/manifests, writer GIDs,
  // raw source selection, native capability, and actual recording readiness.
  bool driver_live=false,worker_live=false,fixture_live=false,recorder_live=false;
  bool worker_capability_valid=false,source_inputs_valid=false,reference_pair_ready=false;
  bool recording_ready=false,sink_ready=false,stopping=false;
  int64_t capability_receipt_ns=0,ready_generation=0;
  size_t physical_publishers=0,solve_job_publishers=0,decision_publishers=0,applied_publishers=0;
  std::string ready_snapshot_sha256;
  Json version;
};
enum class State { waiting,prepared,closed,rejected,expired };
inline const char *name(State value){switch(value){
  case State::waiting:return "waiting";case State::prepared:return "prepared";
  case State::closed:return "closed";case State::rejected:return "rejected";
  case State::expired:return "expired";}return "unknown";
}

class Gate {
 public:
  Gate(const Json &contract,const std::string &mode,Identity id,int64_t created)
    :id_(std::move(id)),created_(created){
    validate_entry(contract,mode);
    lease_ns_=contract.at("worker_capability_receipt_timeout_ns").get<int64_t>();
    require(created_>0&&created_<=INT64_MAX-prepare_timeout_ns,"creation/deadline range");
    require(text(id_.run_id,128)&&text(id_.boot_id,64),"run/boot domain");
    require(id_.driver_pid>0&&id_.driver_pid<=INT_MAX&&id_.driver_start_ticks>0,"driver PID/start domain");
    for(const auto &h:{id_.contract_sha256,id_.preparer_manifest_sha256,id_.driver_exe_sha256,
      id_.driver_argv_sha256,id_.driver_tool_sha256,id_.worker_manifest_sha256,
      id_.fixture_manifest_sha256,id_.recorder_manifest_sha256})require(sha(h),"identity SHA domain");
    require(std::set<std::string>{id_.preparer_manifest_sha256,id_.worker_manifest_sha256,
      id_.fixture_manifest_sha256,id_.recorder_manifest_sha256}.size()==4,"distinct role manifests");
  }

  // Any consumed malformed/stale/mismatched grant is terminal. A caller cannot
  // retry corrected data in the same run after rejection or after close.
  void open(const std::string &raw,int64_t now,const Context &context){
    require(state_==State::waiting,"grant already consumed or terminal");
    if(now>=deadline()){state_=State::expired;throw std::runtime_error("formal prepare deadline expired");}
    try{
      require(now>=created_,"clock ordering");
      require(!raw.empty()&&raw.size()<=request_max_bytes,"bounded request bytes");
      const auto j=parse_unique_contract(raw);
      exact(j,{"schema","policy","scope","run_id","boot_id","contract_sha256","spec_sha256",
        "preparer_manifest_sha256","driver","roles","ready_snapshot_sha256","ready_generation",
        "version","issued_ns","sequence","stage_qualified","execute_qualified"},"request");
      for(const auto &kv:std::vector<std::pair<const char*,std::string>>{
        {"schema","p1-owned-formal-prepare-v1"},{"policy",policy},{"scope",scope},
        {"run_id",id_.run_id},{"boot_id",id_.boot_id},{"contract_sha256",id_.contract_sha256},
        {"spec_sha256",full_contract_spec_sha256},{"preparer_manifest_sha256",id_.preparer_manifest_sha256}})
        same_text(j,kv.first,kv.second);
      exact(j.at("driver"),{"pid","start_ticks","exe_sha256","argv_sha256","tool_sha256"},"driver");
      const auto &driver=j.at("driver");
      require(integer(driver,"pid",1,INT_MAX)==id_.driver_pid&&
        integer(driver,"start_ticks",1)==id_.driver_start_ticks,"driver PID/start mismatch");
      same_text(driver,"exe_sha256",id_.driver_exe_sha256);
      same_text(driver,"argv_sha256",id_.driver_argv_sha256);
      same_text(driver,"tool_sha256",id_.driver_tool_sha256);
      exact(j.at("roles"),{"worker_manifest_sha256","fixture_manifest_sha256","recorder_manifest_sha256"},"roles");
      same_text(j.at("roles"),"worker_manifest_sha256",id_.worker_manifest_sha256);
      same_text(j.at("roles"),"fixture_manifest_sha256",id_.fixture_manifest_sha256);
      same_text(j.at("roles"),"recorder_manifest_sha256",id_.recorder_manifest_sha256);
      require(integer(j,"sequence",1,1)==1,"one shot sequence");
      false_flag(j,"stage_qualified");false_flag(j,"execute_qualified");
      const auto issued=integer(j,"issued_ns",created_);
      require(issued<=now&&now-issued<=request_ttl_ns,"grant TTL/order");
      require(integer(j,"ready_generation",1)==context.ready_generation,"ready generation mismatch");
      require(sha(context.ready_snapshot_sha256),"ready snapshot SHA domain");
      same_text(j,"ready_snapshot_sha256",context.ready_snapshot_sha256);
      exact(j.at("version"),{"task","model","config","schedule","epoch"},"request version");
      exact(context.version,{"task","model","config","schedule","epoch"},"context version");
      for(const auto &k:{"task","model","config","schedule","epoch"})
        require(integer(j.at("version"),k,1)==integer(context.version,k,1),"current version mismatch");
      require(live(context,now),"current owned preparation prerequisites");
      authorized_ready_sha_=context.ready_snapshot_sha256;
      authorized_generation_=context.ready_generation;authorized_version_=context.version;
      state_=State::prepared;prepared_ns_=now;last_checked_ns_=now;
    }catch(...){state_=State::rejected;throw;}
  }
  bool live(const Context &c,int64_t now)const{
    return now>=created_&&now<deadline()&&c.driver_live&&c.worker_live&&c.fixture_live&&c.recorder_live&&
      c.worker_capability_valid&&c.source_inputs_valid&&c.reference_pair_ready&&c.recording_ready&&
      c.sink_ready&&!c.stopping&&c.capability_receipt_ns>0&&c.capability_receipt_ns<=now&&
      now-c.capability_receipt_ns<=lease_ns_&&c.ready_generation>0&&sha(c.ready_snapshot_sha256)&&
      c.physical_publishers==0&&c.solve_job_publishers==0&&c.decision_publishers==0&&c.applied_publishers==0;
  }
  void poll(int64_t now,const Context &c){
    if(state_==State::waiting||state_==State::prepared){
      require(now>=created_&&now>=last_checked_ns_,"poll monotonic ordering");
      last_checked_ns_=now;
      if(now>=deadline()){state_=State::expired;closed_ns_=now;}
      else if(c.stopping){state_=State::closed;closed_ns_=now;}
      else if(state_==State::prepared&&(!live(c,now)||c.ready_snapshot_sha256!=authorized_ready_sha_||
        c.ready_generation!=authorized_generation_||c.version!=authorized_version_)){
        state_=State::rejected;closed_ns_=now;
      }
    }
  }
  void close(int64_t now){
    require(now>=created_&&now>=last_checked_ns_,"close monotonic ordering");
    if(state_==State::waiting||state_==State::prepared){state_=State::closed;closed_ns_=now;}
  }
  State state()const{return state_;}
  int64_t deadline()const{return created_+prepare_timeout_ns;}
  Json evidence()const{return {{"policy",policy},{"scope",scope},{"state",name(state_)},
    {"created_ns",created_},{"prepared_ns",prepared_ns_},{"closed_ns",closed_ns_},{"deadline_ns",deadline()},
    {"physical_publishers_permitted",0},{"solve_jobs_permitted",0},{"decisions_permitted",0},
    {"applied_messages_permitted",0},{"command_anchor_authority","none"},
    {"stage_qualified",false},{"execute_qualified",false},{"formal_freeze_qualified",false}};}
 private:
  Identity id_;int64_t created_=0,lease_ns_=0,prepared_ns_=0,closed_ns_=0,last_checked_ns_=0;
  std::string authorized_ready_sha_;int64_t authorized_generation_=0;Json authorized_version_;
  State state_=State::waiting;
};
} // namespace p1::formal_prepare
