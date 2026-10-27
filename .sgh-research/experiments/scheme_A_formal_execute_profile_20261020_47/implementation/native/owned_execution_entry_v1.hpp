// SPDX-License-Identifier: MIT
#pragma once
#include "p1_full_contract.hpp"
#include "publication_result_v1.hpp"

namespace p1::owned_execution {
// This is the pre-execution policy core. It creates no ROS endpoints and makes
// no API calls. M4 must obtain the facts below from its owned process/graph gate,
// verify the freeze package, and serialize this core on the sole output thread.
// A synthetic context in a component test is never live ownership evidence.
inline void context_gate(const nlohmann::json & contract, const std::string & mode,
                         const nlohmann::json & expected, const nlohmann::json & actual) {
  contract_require(validate_contract_fields(contract)==ContractProfile::Frozen,"frozen contract required");
  contract_require(contract.at("supported_parameter_profile")==target_parameter_profile,"owned profile required");
  require_runtime_contract_mode(contract,mode);  // execute remains disabled
  contract_require(mode=="no_output","only policy preflight is released");
  const std::set<std::string> fields={"run_id","boot_id","contract_sha256","freeze_evidence_sha256",
    "policy_sha256","regulator_manifest_sha256","producer_id","role","pid","start_ticks","output_gids",
    "old_outputs_absent","worker_output_count","fixture_output_count","recorder_output_count",
    "worker_capability_live","recorder_ready","inputs_ready","source_graph_verified"};
  contract_require(actual.is_object() && actual.size()==fields.size(),"exact owned context fields");
  for(const auto & field:fields)contract_require(actual.contains(field),"owned context field missing");
  for(const auto & key:{"run_id","producer_id"})
    contract_require(actual.at(key).is_string() && std::regex_match(actual.at(key).get<std::string>(),std::regex("[A-Za-z0-9_-]{1,96}")),"owned identity string");
  contract_require(actual.at("boot_id").is_string() && std::regex_match(actual.at("boot_id").get<std::string>(),std::regex("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")),"boot identity");
  for(const auto & key:{"contract_sha256","freeze_evidence_sha256","policy_sha256","regulator_manifest_sha256"})
    contract_require(actual.at(key).is_string() && std::regex_match(actual.at(key).get<std::string>(),std::regex("[0-9a-f]{64}")),"context SHA-256");
  contract_require(actual.at("freeze_evidence_sha256")==contract.at("freeze_evidence_sha256"),"freeze binding");
  contract_require(actual.at("policy_sha256")==target_policy_sha256,"policy binding");
  contract_require(actual.at("role")=="p1_owned_execute_regulator","sole owner role");
  for(const auto & key:{"pid","start_ticks"})contract_require(strict_i64(actual.at(key)) && actual.at(key).get<int64_t>()>0,"positive process identity");
  for(const auto & key:{"worker_output_count","fixture_output_count","recorder_output_count"})
    contract_require(strict_i64(actual.at(key)) && actual.at(key).get<int64_t>()==0,"non-owner output forbidden");
  for(const auto & key:{"old_outputs_absent","worker_capability_live","recorder_ready","inputs_ready","source_graph_verified"})
    contract_require(actual.at(key).is_boolean() && actual.at(key).get<bool>(),"owned readiness required");
  const auto & gids=actual.at("output_gids");
  contract_require(gids.is_array() && gids.size()==2 && gids[0]!=gids[1],"two unique output GIDs");
  for(const auto & gid:gids)contract_require(gid.is_string() && std::regex_match(gid.get<std::string>(),std::regex("[0-9a-f]{48}")),"output GID shape");
  contract_require(actual==expected,"owned registry/context changed");
}

struct PairObservation {
  bool both_returned=false,initial_pair=false,rho_available=false;
  bool gap_exceeded=false,span_exceeded=false,rate_exceeded=false;
  bool command_invalid=false,bootstrap_late=false;
};

class OutputAuthority {
 public:
  OutputAuthority(const nlohmann::json & c,const nlohmann::json & expected,
                  const nlohmann::json & actual,int64_t prepare_ns):grant_ns_(prepare_ns) {
    context_gate(c,"no_output",expected,actual);
    contract_require(prepare_ns>0,"positive prepare grant time");
    limits_.low=c.at("command_min_n");limits_.high=c.at("command_max_n");
    limits_.rho=c.at("rho_n_s");limits_.hold_ns=c.at("hold_ns");
    period_ns_=c.at("T_ns");gap_ns_=c.at("publish_gap_ns");
    span_ns_=c.at("publish_budget_ns");jitter_ns_=c.at("tick_jitter_ns");
    shutdown_ns_=c.at("shutdown_grace_ns");
  }
  const Anchor & anchor()const{return anchor_;}
  int64_t last_accepted_ns()const{return last_accepted_ns_;}
  bool initialized()const{return initialized_;}
  bool terminal()const{return terminal_;}
  bool business_permitted(int64_t now)const {
    if(!initialized_||terminal_||!anchor_.known[0]||!anchor_.known[1])return false;
    for(int i=0;i<2;++i)if(now<=anchor_.time[i]||now-anchor_.time[i]>gap_ns_)return false;
    return true;
  }
  // Fixed absolute schedule. A missed tick never creates catch-up bursts.
  bool tick(int64_t now) {
    contract_require(now>=grant_ns_,"tick before prepare grant");
    const auto elapsed=now-grant_ns_;
    const auto due=elapsed/period_ns_;
    contract_require(due>=next_tick_,"early or repeated absolute tick");
    if(due!=next_tick_ || elapsed%period_ns_>jitter_ns_)terminal_=true;
    next_tick_=due+1;
    return !terminal_;
  }
  Command fallback_request(int64_t now,bool invalid=false)const {
    contract_require(now>=grant_ns_,"fallback time precedes prepare");
    for(int i=0;i<2;++i)contract_require(!anchor_.known[i]||now>=anchor_.time[i],"fallback time precedes anchor");
    return fallback(anchor_,now,last_accepted_ns_,limits_,invalid||terminal_);
  }
  // Record actual API facts even if they violate the policy. Successful sides
  // remain irreversible after partial failure, rate/gap/span failure, or stop.
  PairObservation record_pair(const Command & command,
      const std::array<publication::CallResult,2> & calls,
      const std::string & reason,int64_t activation_ns=0) {
    contract_require(reason=="bootstrap"||reason=="waiting"||reason=="accepted"||reason=="fallback"||reason=="shutdown","publication reason");
    for(const auto & call:calls)contract_require(call.start_ns>=grant_ns_ && call.end_ns>=call.start_ns,"ordered API times required");
    contract_require(calls[1].start_ns>=calls[0].end_ns,"serial pair required");
    for(int i=0;i<2;++i)contract_require(last_attempt_ns_[i]==0||calls[i].start_ns>last_attempt_ns_[i],"actual API start must advance");
    PairObservation result;
    result.initial_pair=!initialized_;
    result.both_returned=calls[0].returned&&calls[1].returned;
    result.span_exceeded=calls[1].end_ns-calls[0].start_ns>span_ns_;
    result.bootstrap_late=last_attempt_ns_[0]==0 && calls[0].start_ns-grant_ns_>period_ns_;
    result.rho_available=anchor_.known[0]&&anchor_.known[1]&&result.both_returned;
    if(reason=="accepted" && (!business_permitted(calls[0].start_ns)||activation_ns<grant_ns_||activation_ns>calls[0].start_ns||activation_ns<=last_accepted_ns_))result.command_invalid=true;
    if(!initialized_ && reason!="bootstrap" && reason!="shutdown")result.command_invalid=true;
    for(int i=0;i<2;++i){
      if(!std::isfinite(command[i])||command[i]<limits_.low||command[i]>limits_.high)result.command_invalid=true;
      if((!initialized_||!anchor_.known[i]) && command[i]!=0)result.command_invalid=true;
      if(last_attempt_ns_[i] && calls[i].start_ns-last_attempt_ns_[i]>gap_ns_)result.gap_exceeded=true;
      if(anchor_.known[i] && calls[i].returned){
        const auto elapsed=calls[i].start_ns-anchor_.time[i];
        if(elapsed<=0 || std::abs(command[i]-anchor_.n[i])>limits_.rho*elapsed/1e9+1e-9)result.rate_exceeded=true;
      }
      last_attempt_ns_[i]=calls[i].start_ns;
      publication::apply_channel_result(anchor_,i,command[i],calls[i]);
    }
    if(!result.both_returned||result.gap_exceeded||result.span_exceeded||result.rate_exceeded||result.command_invalid||result.bootstrap_late)terminal_=true;
    result.rho_available=result.rho_available&&!result.gap_exceeded&&!result.rate_exceeded;
    if(!initialized_ && result.both_returned && command[0]==0 && command[1]==0)initialized_=true;
    if(reason=="accepted" && !terminal_)last_accepted_ns_=activation_ns;
    return result;
  }
  publication::ShutdownResult shutdown(const Command & target,const std::array<bool,2> & returned,
                                      int64_t now,int64_t stop_start)const {
    contract_require(stop_start>=grant_ns_ && now>=stop_start,"ordered shutdown time");
    return publication::shutdown_result(true,true,target,returned,now,stop_start,shutdown_ns_);
  }
 private:
  Anchor anchor_{};Limits limits_{};
  std::array<int64_t,2> last_attempt_ns_{0,0};
  int64_t grant_ns_=0,last_accepted_ns_=0,next_tick_=0;
  int64_t period_ns_=0,gap_ns_=0,span_ns_=0,jitter_ns_=0,shutdown_ns_=0;
  bool initialized_=false,terminal_=false;
};
}  // namespace p1::owned_execution
