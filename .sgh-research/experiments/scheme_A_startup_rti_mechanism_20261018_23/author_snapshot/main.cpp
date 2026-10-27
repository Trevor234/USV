// SPDX-License-Identifier: MIT
#include "raw_backend_v1.hpp"
#include <openssl/evp.h>
#include <fcntl.h>
#include <unistd.h>
#include <filesystem>
#include <sstream>
#include <iomanip>
#include <iostream>
#ifndef P1_REPLAY_SOURCE_BUNDLE_SHA256
#error source identity required
#endif
std::string file_sha(const std::string &path){std::ifstream f(path,std::ios::binary);bias_replay::require(bool(f),"hash input exists");std::string s((std::istreambuf_iterator<char>(f)),{});unsigned char hash[32];unsigned count=0;bias_replay::require(EVP_Digest(s.data(),s.size(),hash,&count,EVP_sha256(),nullptr)==1&&count==32,"SHA256");std::ostringstream out;out<<std::hex<<std::setfill('0');for(auto c:hash)out<<std::setw(2)<<unsigned(c);return out.str();}
int main(int argc,char **argv){try{
 bias_replay::require(argc==5&&std::string(argv[1])=="--input"&&std::string(argv[3])=="--output","usage --input absolute.json --output create-only.json");const std::string input=argv[2],output=argv[4];bias_replay::require(std::filesystem::path(input).is_absolute()&&std::filesystem::path(output).is_absolute(),"absolute paths");auto before=file_sha(input);auto data=bias_replay::read(input);auto baseline=startup_replay::actual_baseline(data);
 for(const auto &kind:{"public_vs_actual","raw_shift_vs_actual","public_vs_raw_shift"}){bias_replay::require(baseline[kind]["control"].get<double>()<=1e-10,"baseline control equivalence");for(const auto &key:{"X","U"})bias_replay::require(baseline[kind][key].get<double>()<=1e-9,"baseline full prediction equivalence");}
 startup_replay::Json cases=startup_replay::Json::array();for(const auto &id:data.at("selected_job_ids")){auto c=startup_replay::repeated_selected(data,id.get<uint64_t>());for(const auto &key:{"control","X","U"})bias_replay::require(c["public_vs_raw_shift_max"][key].get<double>()<=1e-10,"public/raw shifted repeat equivalence");cases.push_back(c);}
 startup_replay::Json result={{"schema","scheme-A-startup-RTI-native-result/v1"},{"input_path",input},{"input_sha256",before},{"source_bundle_sha256",P1_REPLAY_SOURCE_BUNDLE_SHA256},{"binary_sha256",file_sha("/proc/self/exe")},{"baseline",baseline},{"cases",cases},{"all_numeric_OCP_parameters_unchanged",true},{"actual_ROS_nodes_started",false},{"runtime_code_or_endpoint_policy_changed",false},{"generated_code_changed",false},{"input_unchanged",before==file_sha(input)},{"stage_qualified",false},{"execute_qualified",false},{"research_conclusion",false}};bias_replay::require(result["input_unchanged"],"input changed during replay");
 auto bytes=result.dump(2)+"\n";int fd=::open(output.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);bias_replay::require(fd>=0,"create-only output");size_t done=0;while(done<bytes.size()){auto n=::write(fd,bytes.data()+done,bytes.size()-done);bias_replay::require(n>0,"result write");done+=n;}bias_replay::require(::fsync(fd)==0,"result fsync");::close(fd);
 std::cout<<startup_replay::Json{{"output",output},{"baseline",baseline},{"selected_cases",cases.size()}}.dump()<<'\n';return 0;
 }catch(const std::exception &e){std::cerr<<"startup replay failed: "<<e.what()<<'\n';return 2;}}
