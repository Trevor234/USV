// SPDX-License-Identifier: MIT
// Pure policy/API-simulator tests. No ROS init, endpoints, or solver invocation.
#include "m4_owned_runtime.hpp"
#include "owned_execution_policy_native_v1.hpp"
#include "../../worker/v2_diagnostic_block.hpp"
#include <fstream>
#include <iostream>
using J=nlohmann::json;
int main(int argc,char **argv){
  if(argc!=2)return 2;
  const auto raw=c36_owned::detail::read_manifest(argv[1]);const auto c=p1::parse_unique_contract(raw);
  J rows=J::array();bool okay=true;
  auto test=[&](const std::string &name,bool expected,auto operation){
    bool accepted=false;std::string reason;
    try{operation();accepted=true;}catch(const std::exception &e){reason=e.what();}
    const bool passed=accepted==expected;okay&=passed;rows.push_back({{"name",name},{"expected_accepted",expected},{"accepted",accepted},{"passed",passed},{"reason",reason}});
  };
  auto gid=J::array();for(int i=0;i<16;++i)gid.push_back(i+1);
  test("native16_GID_is_32hex",true,[&]{p1_owned::require(m4_owned::gid_hex(gid).size()==32,"native width");});
  for(const auto &label:{"old24bytes","allzero","booleanbyte","overflowbyte","negativebyte"}){
    auto x=gid;if(std::string(label)=="old24bytes")for(int i=0;i<8;++i)x.push_back(1);
    if(std::string(label)=="allzero")for(auto &v:x)v=0;
    if(std::string(label)=="booleanbyte")x[0]=true;
    if(std::string(label)=="overflowbyte")x[0]=256;
    if(std::string(label)=="negativebyte")x[0]=-1;
    test(label,false,[&]{m4_owned::gid_hex(x);});
  }
  test("exact_frozen_contract",true,[&]{m4_owned::frozen(c,m4_owned::frozen_contract_sha);});
  test("ordinary_runtime_release_closed",false,[&]{p1::require_runtime_contract_mode(c,"execute");});
  test("explicit_isolated_entry_shape",true,[&]{m4_owned::contract(argv[1],m4_owned::frozen_contract_sha,"execute",m4_owned::scope);});
  for(const auto &mode:{"shadow","no_output","","Execute"})test(std::string("wrong_M4_mode_")+mode,false,[&]{m4_owned::contract(argv[1],m4_owned::frozen_contract_sha,mode,m4_owned::scope);});
  test("missing_isolation_scope",false,[&]{m4_owned::contract(argv[1],m4_owned::frozen_contract_sha,"execute","");});
  test("wrong_frozen_hash",false,[&]{m4_owned::frozen(c,std::string(64,'a'));});
  test("old_diagnostic_not_M4_contract",false,[&]{m4_owned::frozen(p1::candidate_baseline(),m4_owned::frozen_contract_sha);});
  test("disabled_V2_works_with_formal_frozen",true,[&]{v2_diagnostic::Block b("none",0,false,false,true);p1_owned::require(!b.take(1),"fault disabled");});
  test("V2_never_enabled_by_frozen_flag",false,[&]{v2_diagnostic::Block b(v2_diagnostic::policy,1700,true,true,true);});
  const J context={{"run_id","unit_m4_native"},{"boot_id",p1_owned::boot_id()},{"contract_sha256",m4_owned::frozen_contract_sha},
    {"freeze_evidence_sha256",m4_owned::frozen_index_sha},{"policy_sha256",p1::target_policy_sha256},{"regulator_manifest_sha256",std::string(64,'b')},
    {"producer_id",std::string(64,'c')},{"role",m4_owned::owner_role},{"pid",12345},{"start_ticks",67890},
    {"output_gids",J::array({std::string(32,'1'),std::string(32,'2')})},{"old_outputs_absent",true},
    {"worker_output_count",0},{"fixture_output_count",0},{"recorder_output_count",0},{"worker_capability_live",true},
    {"recorder_ready",true},{"inputs_ready",true},{"source_graph_verified",true}};
  test("native_context_accepted_offline",true,[&]{p1::owned_execution::context_gate(c,"no_output",context,context);});
  for(const auto &key:{"run_id","boot_id","contract_sha256","policy_sha256","regulator_manifest_sha256","producer_id","role"}){
    auto altered=context;altered[key]="foreign";
    test(std::string("context_foreign_")+key,false,[&]{p1::owned_execution::context_gate(c,"no_output",context,altered);});
  }
  for(const auto &key:{"worker_output_count","fixture_output_count","recorder_output_count"}){
    auto altered=context;altered[key]=1;
    test(std::string("nonowner_output_")+key,false,[&]{p1::owned_execution::context_gate(c,"no_output",altered,altered);});
  }
  for(const auto &key:{"old_outputs_absent","worker_capability_live","recorder_ready","inputs_ready","source_graph_verified"}){
    auto altered=context;altered[key]=false;
    test(std::string("missing_readiness_")+key,false,[&]{p1::owned_execution::context_gate(c,"no_output",altered,altered);});
  }
  auto old_gid_context=context;old_gid_context["output_gids"]=J::array({std::string(48,'1'),std::string(48,'2')});
  test("24byte_context_not_native_GID",false,[&]{p1::owned_execution::context_gate(c,"no_output",old_gid_context,old_gid_context);});
  const J version={{"task",2},{"model",1},{"config",1},{"schedule",1},{"epoch",0}},driver={{"manifest_sha256",std::string(64,'d')}};
  const J grant={{"schema","M4-owned-execute-grant-v1"},{"scope",m4_owned::scope},{"run_id",context.at("run_id")},
    {"boot_id",context.at("boot_id")},{"contract_sha256",m4_owned::frozen_contract_sha},{"index_sha256",m4_owned::frozen_index_sha},
    {"context",context},{"version",version},{"ready_sha256",std::string(64,'e')},{"driver_manifest_sha256",driver.at("manifest_sha256")},{"issued_ns",int64_t(2000000000)},{"sequence",1}};
  test("grant_age_equal_2s",true,[&]{m4_owned::grant_fields(grant,context,version,std::string(64,'e'),driver,4000000000LL);});
  test("grant_age_after_2s",false,[&]{m4_owned::grant_fields(grant,context,version,std::string(64,'e'),driver,4000000001LL);});
  test("grant_from_future",false,[&]{m4_owned::grant_fields(grant,context,version,std::string(64,'e'),driver,1999999999LL);});
  for(const auto &key:{"schema","scope","run_id","boot_id","contract_sha256","index_sha256","context","version","ready_sha256","driver_manifest_sha256","issued_ns","sequence"}){
    auto altered=grant;altered.erase(key);
    test(std::string("missing_grant_")+key,false,[&]{m4_owned::grant_fields(altered,context,version,std::string(64,'e'),driver,3000000000LL);});
  }
  auto badseq=grant;badseq["sequence"]=true;
  test("grant_sequence_bool_refused",false,[&]{m4_owned::grant_fields(badseq,context,version,std::string(64,'e'),driver,3000000000LL);});
  test("real_two_send_template_left_throws",true,[&]{
    p1::owned_execution::OutputAuthority a(c,context,context,1000000000);
    auto anchor=a.anchor();int count=0;int64_t ns=1000000000;
    const auto actual=p1::publication::publish_pair(p1::Command{0,0},anchor,p1::publication::Policy{},
      [&]{return ns++;},[](int,int64_t){},[&](int channel,double){++count;if(channel==0)throw std::runtime_error("intentional simulator left failure");},[](int,const p1::publication::CallResult&){});
    const auto result=a.record_pair({0,0},actual.calls,"bootstrap");
    p1_owned::require(count==2&&!result.both_returned&&a.anchor().known==std::array<bool,2>{false,true}&&a.terminal(),"both simulated sends and per-side irreversibility");
  });
  std::cout<<J{{"schema","M4-native-policy-component/v1"},{"passed",okay},{"case_count",rows.size()},{"cases",rows},
    {"ROS_initialized",false},{"physical_API_calls",0},{"input_contract_sha256",p1_owned::sha256_bytes(raw)},{"ordinary_production_release_enabled",false}}.dump()<<std::endl;
  return okay?0:2;
}
