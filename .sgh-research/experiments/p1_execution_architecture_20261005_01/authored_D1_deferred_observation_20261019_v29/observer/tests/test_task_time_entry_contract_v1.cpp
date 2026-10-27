// SPDX-License-Identifier: MIT
#include "task_time_entry_contract_v1.hpp"
#include <iostream>
#include <stdexcept>
int main(){unsigned checks=0;auto check=[&](bool b,const char *m){++checks;if(!b)throw std::runtime_error(m);};
 auto c=p1::candidate_baseline();auto accepted=[](const auto &value,const std::string &mode){try{p1::shadow::validate_task_time_entry(value,mode);return true;}catch(const std::exception&){return false;}};
 check(accepted(c,"shadow"),"actual diag9 task-time shadow entry accepted");
 for(const auto &mode:{"execute","no_output","","foreign"})check(!accepted(c,mode),"entry stays shadow only");
 auto old=c;old.erase("reference_epoch_policy");old["diagnostic_contract_revision"]=6;old["reference_sampling_policy"]="projected_profile_time_v1";check(!accepted(old,"shadow"),"old diag6 projected entry rejected");
 for(const auto &revision:{nlohmann::json(7),nlohmann::json(8),nlohmann::json(9.0),nlohmann::json(true)}){auto v=c;v["diagnostic_contract_revision"]=revision;check(!accepted(v,"shadow"),"revision type and value fixed");}
 for(const auto &key:{"reference_sampling_policy","reference_epoch_policy","preparation_retry_policy","cold_start_policy"}){auto v=c;v.erase(key);check(!accepted(v,"shadow"),"mandatory entry policy");v=c;v[key]="foreign";check(!accepted(v,"shadow"),"policy exact");}
 for(const auto &offset:{nlohmann::json(1),nlohmann::json(false),nlohmann::json(0.0)}){auto v=c;v["reference_start_offset"]=offset;check(!accepted(v,"shadow"),"integer zero offset only");}
 auto v=c;v["Q"][0]=21;check(!accepted(v,"shadow"),"full fixed cost validation retained");v=c;v["deadline_ns"]=160000000;check(!accepted(v,"shadow"),"deadline unchanged");v=c;v["execute_qualified"]=true;check(!accepted(v,"shadow"),"execute flag cannot be raised");
 std::cout<<"task-time actual entry checks="<<checks<<" passed; shared constructor validator; no ROS calls\n";
}
