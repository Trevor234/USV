from pathlib import Path
import hashlib,json,subprocess
root=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_70_81_review_20261025_82/evidence/replay01/protocol')
src=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_r2_driver_20261025_78/implementation/t2_author_r3/fixture/synthetic_source_m4.cpp').read_text()
block=src[src.index(' void poll_commands(){'):src.index(' void execute_action(')]
(root/'poll_commands_extracted.hpp').write_text(block)
prefix=r'''#include <nlohmann/json.hpp>
#include <filesystem>
#include <fstream>
#include <set>
#include <stdexcept>
#include <iostream>
using Json=nlohmann::json;
namespace p1_owned {using Json=nlohmann::json; void require(bool b,const char*m){if(!b)throw std::runtime_error(m);} std::string read_bounded(const std::filesystem::path&p){std::ifstream in(p);return std::string(std::istreambuf_iterator<char>(in),{});} std::string file_sha256(const std::filesystem::path&){return "unused";}}
namespace c36_owned {namespace detail { Json strict_json(const std::string&s){return Json::parse(s);} }}
struct Gate {bool t2_armed_=true,start_=true;std::string t2_command_dir_,run_="R0",contract_="C";std::set<std::string>t2_seen_commands_;Json t2_table_,t2_executed_=Json::array();
void execute_action(const Json&e,const Json&t,const std::string&){t2_executed_.push_back(e.at("id"));}
'''
suffix=r'''};
int main(int argc,char**argv){Gate g;g.t2_command_dir_=argv[1];g.t2_table_=Json::parse(argv[2]);try{g.poll_commands();std::cout<<Json{{"executed",g.t2_executed_},{"rejected",false}}.dump();}catch(const std::exception&e){std::cout<<Json{{"executed",g.t2_executed_},{"rejected",true},{"reason",e.what()}}.dump();}}
'''
(root/'fixture_gate_probe.cpp').write_text(prefix+block+suffix)
subprocess.run(['g++','-std=c++17','-O0',str(root/'fixture_gate_probe.cpp'),'-o',str(root/'fixture_gate_probe')],check=True)
table={'actions':[{'id':'a1','action':'path_replace','parameters':{'points':101,'speed_m_s':.05},'trigger':{'phase':'solve_active','job_id':2,'delay_ms':0}}]}
command={'schema':'M4-t2-action-command-v1','run_id':'R0','contract_sha256':'C','action_id':'a1','sequence':1,'trigger':{'phase':'solve_active','job':{'job_id':999},'observed_ns':-100,'source_role':'driver','extra':'accepted'}}
d=root/'fixture_commands';d.mkdir(exist_ok=True);(d/'001_a1.json').write_text(json.dumps(command))
r=subprocess.run([str(root/'fixture_gate_probe'),str(d),json.dumps(table)],text=True,capture_output=True,check=True)
result={'scope':'actual poll_commands block extracted unchanged; execute_action stub only records execution; no ROS','source_block_sha256':hashlib.sha256(block.encode()).hexdigest(),'input':command,'result':json.loads(r.stdout)}
(root/'fixture_gate_probe_result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
