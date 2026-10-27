// SPDX-License-Identifier: MIT
#include "causal_start.hpp"
#include <openssl/evp.h>
#include <fcntl.h>
#include <unistd.h>
#include <filesystem>
#include <sstream>
#include <iomanip>
#include <iostream>
#ifndef P1_REPLAY_SOURCE_BUNDLE_SHA256
#error pinned source required
#endif
std::string file_sha(const std::string &path){std::ifstream f(path,std::ios::binary);bias_replay::require(bool(f),"hash input exists");std::string s((std::istreambuf_iterator<char>(f)),{});unsigned char h[32];unsigned n=0;bias_replay::require(EVP_Digest(s.data(),s.size(),h,&n,EVP_sha256(),nullptr)==1&&n==32,"SHA256");std::ostringstream o;o<<std::hex<<std::setfill('0');for(auto v:h)o<<std::setw(2)<<unsigned(v);return o.str();}
void append_bytes(int fd,const std::string &s){size_t i=0;while(i<s.size()){auto n=::write(fd,s.data()+i,s.size()-i);bias_replay::require(n>0,"write record");i+=n;}bias_replay::require(::fsync(fd)==0,"record fsync");}
struct Journal{int fd;explicit Journal(const std::string &p):fd(::open(p.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600)){bias_replay::require(fd>=0,"create-only journal");}~Journal(){if(fd>=0)::close(fd);}void put(const causal_start::Json &j){append_bytes(fd,j.dump()+"\n");}};
int main(int argc,char **argv){try{
 using causal_start::Json;bias_replay::require(argc==5&&std::string(argv[1])=="--input"&&std::string(argv[3])=="--output","only runtime --input and create-only --output accepted");std::string in=argv[2],out=argv[4];bias_replay::require(std::filesystem::path(in).is_absolute()&&std::filesystem::path(out).is_absolute(),"absolute paths");auto before=file_sha(in);auto runtime=bias_replay::read(in);Journal journal(out+".journal.jsonl");journal.put({{"phase","identity"},{"runtime_sha256",before},{"binary_sha256",file_sha("/proc/self/exe")},{"source_bundle_sha256",P1_REPLAY_SOURCE_BUNDLE_SHA256}});
 causal_start::Pipeline pipeline(bias_replay::parameters(runtime.at("contract")));auto candidate=pipeline.run(runtime,[&](const Json &r){journal.put(r);});auto probe=pipeline.restoration_probe_same_job(runtime.at("actual_job"));journal.put({{"phase","restoration_probe"},{"probe",probe}});
 Json result={{"schema","scheme-A-causal-cold-native-result/v1"},{"runtime_input_path",in},{"runtime_input_sha256",before},{"input_unchanged",before==file_sha(in)},{"binary_sha256",file_sha("/proc/self/exe")},{"source_bundle_sha256",P1_REPLAY_SOURCE_BUNDLE_SHA256},{"candidate",candidate},{"separate_restoration_probe",probe},{"candidate_RTI_calls",4},{"separate_restoration_probe_RTI_calls",1},{"validation_input_argument_supported",false},{"journal_path",out+".journal.jsonl"},{"journal_sha256",file_sha(out+".journal.jsonl")},{"ROS_nodes_started",false},{"runtime_controller_changed",false},{"stage_qualified",false},{"execute_qualified",false},{"research_conclusion",false}};bias_replay::require(result["input_unchanged"],"runtime input changed");int fd=::open(out.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);bias_replay::require(fd>=0,"create-only native result");append_bytes(fd,result.dump(2)+"\n");::close(fd);
 std::cout<<Json{{"output",out},{"candidate_RTI_calls",4},{"separate_probe_calls",1},{"final_first_control",candidate["candidate_final"]["first_control"]}}.dump()<<'\n';return 0;
 }catch(const std::exception &e){std::cerr<<"causal cold-start failed: "<<e.what()<<'\n';return 2;}}
