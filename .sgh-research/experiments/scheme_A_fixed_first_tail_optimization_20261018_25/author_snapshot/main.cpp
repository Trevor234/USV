// SPDX-License-Identifier: MIT
#include "fixed_first.hpp"
#include <openssl/evp.h>
#include <fcntl.h>
#include <unistd.h>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>
#ifndef P1_REPLAY_SOURCE_BUNDLE_SHA256
#error pinned source required
#endif
std::string file_sha(const std::string &path){std::ifstream f(path,std::ios::binary);bias_replay::require(bool(f),"hash input exists");std::string s((std::istreambuf_iterator<char>(f)),{});unsigned char h[32];unsigned n=0;bias_replay::require(EVP_Digest(s.data(),s.size(),h,&n,EVP_sha256(),nullptr)==1&&n==32,"SHA256");std::ostringstream o;o<<std::hex<<std::setfill('0');for(auto v:h)o<<std::setw(2)<<unsigned(v);return o.str();}
void write_all(int fd,const std::string &raw){size_t i=0;while(i<raw.size()){auto n=::write(fd,raw.data()+i,raw.size()-i);bias_replay::require(n>0,"record write");i+=n;}bias_replay::require(::fsync(fd)==0,"record fsync");}
struct Journal{int fd;explicit Journal(const std::string &p):fd(::open(p.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600)){bias_replay::require(fd>=0,"create-only journal");}~Journal(){if(fd>=0)::close(fd);}void append(const fixed_first::Json &j){write_all(fd,j.dump()+"\n");}};
int main(int argc,char **argv){try{
 using fixed_first::Json;bias_replay::require(argc==5&&std::string(argv[1])=="--input"&&std::string(argv[3])=="--output","usage --input absolute --output create-only");std::string in=argv[2],out=argv[4];bias_replay::require(std::filesystem::path(in).is_absolute()&&std::filesystem::path(out).is_absolute(),"absolute paths");auto before=file_sha(in);auto d=bias_replay::read(in);bias_replay::require(d.at("repeat_count")==12&&d.at("ordered_arms")==Json::array({"free_first","fixed_first_050"})&&d.at("fixed_first_control_n")==Json::array({.5,.5}),"two registered arms and finite repetitions");
 Journal journal(out+".journal.jsonl");journal.append({{"type","identity"},{"input_sha256",before},{"source_bundle_sha256",P1_REPLAY_SOURCE_BUNDLE_SHA256},{"binary_sha256",file_sha("/proc/self/exe")}});
 bias_replay::require(file_sha(d.at("actual_baseline_input_path"))==d.at("actual_baseline_input_sha256"),"actual 102 Job input binding");auto legacy=startup_replay::actual_baseline(bias_replay::read(d.at("actual_baseline_input_path")));
 for(auto kind:{"public_vs_actual","raw_shift_vs_actual","public_vs_raw_shift"}){bias_replay::require(legacy[kind]["control"].get<double>()<=1e-10,"actual control baseline");for(auto key:{"X","U"})bias_replay::require(legacy[kind][key].get<double>()<=1e-9,"actual complete prediction baseline");}
 auto free_baseline=fixed_first::seeded_free_baseline(d);journal.append({{"type","baselines_passed"},{"legacy",legacy},{"seeded_free",free_baseline}});
 auto p=bias_replay::parameters(d.at("contract"));const auto &job=d.at("actual_job");Json arms=Json::array();
 for(auto id:{"free_first","fixed_first_050"}){
  bool fixed=std::string(id)=="fixed_first_050";startup_replay::RawBackend s(p,fixed);auto u=d.at("refined_U").get<std::vector<double>>();if(fixed){u[0]=.5;u[1]=.5;}auto seed=s.seed_feasible(job,u);journal.append({{"type","arm_seed"},{"arm_id",id},{"seed",seed},{"additional_first_equality",fixed}});Json iterations=Json::array();
  for(int k=1;k<=12;++k){auto answer=s.step(job,false,false);auto r=startup_replay::answer_json(answer,job,p);r["actual_OCP_input_changed"]=fixed;r["additional_first_control_equality"]=fixed;r["tail_reoptimized"]=true;r["native_status"]=0;r["first_control_equality_error_n"]=fixed?std::max(std::abs(answer.control[0]-.5),std::abs(answer.control[1]-.5)):0.;r["augmented_X"]=bias_replay::matrix_data(answer.augmented);Json row={{"iteration",k},{"answer",r}};iterations.push_back(row);journal.append({{"type","iteration"},{"arm_id",id},{"record",row}});}
  arms.push_back({{"arm_id",id},{"fixed_Job",job},{"seed",seed},{"iterations",iterations},{"additional_first_equality",fixed},{"warm_cache_shifted",false},{"original_model_cost_reference_unchanged",true}});
 }
 Json result={{"schema","scheme-A-fixed-first-tail-native-result/v1"},{"input_path",in},{"input_sha256",before},{"source_bundle_sha256",P1_REPLAY_SOURCE_BUNDLE_SHA256},{"binary_sha256",file_sha("/proc/self/exe")},{"legacy_baseline",legacy},{"seeded_free_baseline",free_baseline},{"arms",arms},{"mechanism_RTI_calls",24},{"all_24_iterations_complete",true},{"input_unchanged",before==file_sha(in)},{"journal_path",out+".journal.jsonl"},{"journal_sha256",file_sha(out+".journal.jsonl")},{"ROS_nodes_started",false},{"runtime_code_changed",false},{"original_objective_changed",false},{"constrained_arm_has_changed_feasible_set",true},{"stage_qualified",false},{"execute_qualified",false},{"research_conclusion",false}};bias_replay::require(result["input_unchanged"],"input mutation");int fd=::open(out.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);bias_replay::require(fd>=0,"create-only result");write_all(fd,result.dump(2)+"\n");::close(fd);std::cout<<Json{{"output",out},{"legacy_baseline",legacy},{"free_seeded_X_error",free_baseline["X_max_abs_error"]},{"mechanism_RTI_calls",24}}.dump()<<'\n';return 0;
 }catch(const std::exception &e){std::cerr<<"fixed-first tail replay failed: "<<e.what()<<'\n';return 2;}}
