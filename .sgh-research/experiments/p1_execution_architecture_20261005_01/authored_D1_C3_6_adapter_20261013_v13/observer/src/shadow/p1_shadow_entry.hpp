// SPDX-License-Identifier: MIT
#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <limits>
#include <stdexcept>
#include <string>
#include <nlohmann/json.hpp>

namespace p1::shadow {
inline constexpr size_t identity_text_limit=128;
inline constexpr const char *entry_policy="D1_shadow_startup_handshake_v1";
inline constexpr const char *legacy_schema="p0-contract-v1";
inline constexpr const char *legacy_baseline="F5_20261005_atomic_freeze_01";
inline void require(bool okay,const char *reason){if(!okay)throw std::runtime_error(std::string("shadow entry: ")+reason);}
inline bool text(const std::string &s){return !s.empty()&&s.size()<=identity_text_limit&&s.find('\0')==std::string::npos;}
inline bool sha256(const std::string &s){if(s.size()!=64)return false;for(char c:s)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;return true;}
inline void require_shadow_mode(const std::string &mode){require(mode=="shadow","only explicitly declared shadow mode is supported");}

struct LegacyIdentity {
  std::string schema,run,producer,baseline,config,domain;
  void validate(const std::string &boot)const {
    require(text(schema)&&schema==legacy_schema,"unsupported legacy schema");
    require(text(run)&&text(producer),"nonempty bounded legacy run/producer required");
    require(text(baseline)&&baseline==legacy_baseline,"frozen F5 legacy baseline required");
    require(sha256(config),"legacy config SHA256 required");
    require(text(domain)&&text(boot)&&domain==boot+":steady_clock","legacy clock domain must equal this boot steady_clock domain");
  }
  nlohmann::json json()const{return {{"schema",schema},{"run_id",run},{"producer_instance_id",producer},{"baseline_id",baseline},{"config_hash",config},{"steady_clock_domain",domain}};}
};
struct EntryPolicy {
  std::string mode,run,boot,source_file,witness_file,identity_source_file,source_sha,binary_sha,worker_sha,worker_instance;
  int64_t worker_pid=0;
  bool witness_enabled=false;
  // These are this entry's declarations. Another process's effective worker
  // arguments must additionally be verified by the independently owned driver.
  std::array<int64_t,5> hooks{};
  LegacyIdentity legacy;
  void validate()const {
    require_shadow_mode(mode);
    require(text(run)&&text(boot),"nonempty bounded run/boot required");
    require(witness_enabled,"Witness is mandatory");
    for(auto value:hooks)require(value==0,"every delay/native/prepare/tick/logger hook must be exactly zero");
    require(worker_pid>0&&worker_pid<=std::numeric_limits<int32_t>::max(),"worker PID required");
    require(sha256(source_sha)&&sha256(binary_sha)&&sha256(worker_sha)&&text(worker_instance),"complete bounded source/binary/worker Witness identity required");
    legacy.validate(boot);
    const std::array<std::string,3> paths{source_file,witness_file,identity_source_file};
    std::array<std::filesystem::path,3> normalized;
    for(size_t i=0;i<paths.size();++i){
      require(!paths[i].empty()&&paths[i].size()<=4096&&paths[i].find('\0')==std::string::npos,"bounded explicit source/Witness/identity path required");
      const std::filesystem::path p(paths[i]);require(p.is_absolute(),"source/Witness/identity paths must be absolute");
      normalized[i]=std::filesystem::weakly_canonical(p);
    }
    require(normalized[0]!=normalized[1]&&normalized[0]!=normalized[2]&&normalized[1]!=normalized[2],"source/Witness/identity paths must be distinct");
    require(std::filesystem::is_regular_file(normalized[2]),"identity source must exist as a regular file");
    for(size_t i=0;i<2;++i){require(std::filesystem::is_directory(normalized[i].parent_path()),"owned output parent must already exist");require(!std::filesystem::exists(normalized[i])&&!std::filesystem::is_symlink(std::filesystem::symlink_status(normalized[i])),"source/Witness output must be fresh create-only paths");}
  }
};

struct LegacyAdmission {
  const char *reason="";
  bool invalidate=false,terminal=false;
  explicit operator bool()const{return reason[0]=='\0';}
};
// Whole-pair validation runs under the existing business mutex before any
// anchor/history merge. It never changes command/propagation/acceptance formulas.
template<class Applied,class Anchor>
LegacyAdmission assess(const Applied &m,const LegacyIdentity &expected,const std::string &admitted_producer,
                       uint64_t epoch,uint64_t previous_sequence,const Anchor &anchor,
                       bool history_present,int64_t last_history_sim,int64_t now,double low,double high){
  const bool owned_run=m.run_id==expected.run;
  const bool owned_producer=m.producer_instance_id==expected.producer;
  if(!text(m.run_id)||!owned_run)return {"legacy_run_mismatch",false,false};
  if(!text(m.producer_instance_id))return {"legacy_producer_missing_or_unbounded",false,false};
  if(!owned_producer)return {"legacy_producer_mismatch",false,!admitted_producer.empty()};
  if(!text(m.schema_version)||m.schema_version!=expected.schema)return {"legacy_schema_mismatch",true,false};
  if(!text(m.baseline_id)||m.baseline_id!=expected.baseline)return {"legacy_baseline_mismatch",true,false};
  if(!sha256(m.config_hash)||m.config_hash!=expected.config)return {"legacy_config_mismatch",true,false};
  if(!text(m.steady_clock_domain)||m.steady_clock_domain!=expected.domain)return {"legacy_clock_domain_mismatch",true,false};
  if(!text(m.event_semantics)||m.event_semantics!="publisher_command")return {"legacy_semantics_mismatch",true,false};
  if(m.map_scale!=1)return {"legacy_map_scale_mismatch",true,false};
  if(m.clock_epoch!=epoch||m.left_clock_epoch!=epoch||m.right_clock_epoch!=epoch)return {"epoch_mismatch",true,false};
  if(!m.sequence||m.sequence<=previous_sequence)return {"duplicate_or_old_sequence",false,false};
  if(!m.left_publish_success||!m.right_publish_success)return {"legacy_partial_or_failed_publication",true,false};
  for(size_t i=0;i<2;++i){
    const auto start=i?m.right_publish_start_steady_ns:m.left_publish_start_steady_ns;
    const auto end=i?m.right_publish_end_steady_ns:m.left_publish_end_steady_ns;
    if(start<=0||end<start||end>now||(previous_sequence&&start<=anchor.time[i]))return {"legacy_publish_time_order",true,false};
    if(!std::isfinite(m.final_n[i])||m.final_n[i]<low||m.final_n[i]>high)return {"legacy_command_invalid",true,false};
  }
  if(m.left_publish_end_steady_ns>m.right_publish_start_steady_ns)return {"legacy_dual_publish_order",true,false};
  if(m.sim_time_ns<0||m.left_sim_time_ns<m.sim_time_ns||m.right_sim_time_ns<m.left_sim_time_ns||
     (history_present&&m.left_sim_time_ns<last_history_sim))return {"legacy_sim_time_order",true,false};
  if(m.clock_receive_steady_ns<=0||m.clock_receive_steady_ns>m.left_publish_start_steady_ns||
     m.clock_age_ns<0||m.left_clock_age_ns<0||m.right_clock_age_ns<0)return {"legacy_clock_receipt_invalid",true,false};
  return {};
}
inline nlohmann::json bounded_text(const std::string &s){return {{"value",s.substr(0,identity_text_limit)},{"observed_bytes",s.size()},{"truncated",s.size()>identity_text_limit}};}
template<class Applied>nlohmann::json observed_identity(const Applied &m){return {
  {"schema_version",bounded_text(m.schema_version)},{"run_id",bounded_text(m.run_id)},
  {"producer_instance_id",bounded_text(m.producer_instance_id)},{"baseline_id",bounded_text(m.baseline_id)},
  {"config_hash",bounded_text(m.config_hash)},{"steady_clock_domain",bounded_text(m.steady_clock_domain)},
  {"event_semantics",bounded_text(m.event_semantics)}};}
} // namespace p1::shadow
