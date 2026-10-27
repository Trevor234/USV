#include <nlohmann/json.hpp>
#ifdef CONTROLLED_WORKER_CONTRACT
#include "worker/p1_full_contract.hpp"
#else
#include "observer/src/shadow/p1_full_contract.hpp"
#include "observer/src/shadow/p1_shadow_entry.hpp"
#endif
#include <iostream>
#include <stdexcept>
int main(){
 unsigned count=0;auto check=[&](bool good){++count;if(!good)throw std::runtime_error("contract check "+std::to_string(count));};
 auto c=p1::candidate_baseline();
 check(c.at("baseline_input")=="CONTROLLED_PHASE_20261015_DIAGNOSTIC_01");
 check(p1::validate_contract_fields(c)==p1::ContractProfile::Diagnostic);
 check(c.at("execute_qualified")==false);check(c.at("qualification")=="temporary_shadow_diagnostic");
 check(c.at("deadline_ns")==150000000);check(c.at("T_ns")==200000000);check(c.at("activation_tolerance")==nlohmann::json::array({.25,.25,.15,.3,.2,.15}));
 auto rejected=[&](const nlohmann::json &j){try{p1::validate_contract_fields(j);return false;}catch(const std::exception &){return true;}};
 for(const auto &id:{"F5_20261005_atomic_freeze_01","arbitrary",""}){auto j=c;j["baseline_input"]=id;check(rejected(j));}
 {auto j=c;j["deadline_ns"]=160000000;check(rejected(j));}
 {auto j=c;j["T_ns"]=210000000;check(rejected(j));}
 {auto j=c;j["execute_qualified"]=true;check(rejected(j));}
 {auto j=c;j["deadline_ns"]=150000000.0;check(rejected(j));}
 {auto j=c;j["phase_unknown_permission"]=true;check(rejected(j));}
 {auto j=c;j.erase("baseline_input");check(rejected(j));}
 {auto j=c;j["activation_tolerance"][3]=.31;check(rejected(j));}
 {bool threw=false;try{p1::require_runtime_contract_mode(c,"execute");}catch(const std::exception &){threw=true;}check(threw);}
#ifndef CONTROLLED_WORKER_CONTRACT
 p1::shadow::LegacyIdentity identity{"p0-contract-v1","run","producer","CONTROLLED_PHASE_20261015_DIAGNOSTIC_01",std::string(64,'a'),"boot:steady_clock"};
 identity.validate("boot");check(true);identity.baseline="F5_20261005_atomic_freeze_01";
 {bool threw=false;try{identity.validate("boot");}catch(const std::exception &){threw=true;}check(threw);}
#endif
 std::cout<<"controlled contract checks="<<count<<" passed; exact baseline and unchanged guards\n";
}
