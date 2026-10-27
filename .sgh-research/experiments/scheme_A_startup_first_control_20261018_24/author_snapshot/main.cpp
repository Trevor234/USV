// SPDX-License-Identifier: MIT
#include "probe.hpp"
#include <openssl/evp.h>
#include <fcntl.h>
#include <unistd.h>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>
#ifndef P1_REPLAY_SOURCE_BUNDLE_SHA256
#error source identity required
#endif
std::string file_sha(const std::string &path){std::ifstream f(path,std::ios::binary);first_probe::require(bool(f),"hash input exists");std::string s((std::istreambuf_iterator<char>(f)),{});unsigned char hash[32];unsigned n=0;first_probe::require(EVP_Digest(s.data(),s.size(),hash,&n,EVP_sha256(),nullptr)==1&&n==32,"SHA256");std::ostringstream o;o<<std::hex<<std::setfill('0');for(auto c:hash)o<<std::setw(2)<<unsigned(c);return o.str();}
int main(int argc,char **argv){try{
 first_probe::require(argc==5&&std::string(argv[1])=="--input"&&std::string(argv[3])=="--output","usage --input absolute.json --output create-only.json");std::string input=argv[2],output=argv[4];first_probe::require(std::filesystem::path(input).is_absolute()&&std::filesystem::path(output).is_absolute(),"absolute paths required");auto before=file_sha(input);auto data=bias_replay::read(input);auto result=first_probe::run(data);
 result["schema"]="scheme-A-first-control-native-result/v1";result["input_sha256"]=before;result["input_path"]=input;result["source_bundle_sha256"]=P1_REPLAY_SOURCE_BUNDLE_SHA256;result["binary_sha256"]=file_sha("/proc/self/exe");result["input_unchanged"]=before==file_sha(input);result["ROS_nodes_started"]=false;result["runtime_code_changed"]=false;result["new_closed_loop_performance_qualified"]=false;first_probe::require(result["input_unchanged"],"input mutation");
 auto bytes=result.dump(2)+"\n";int fd=::open(output.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);first_probe::require(fd>=0,"create-only output");size_t n=0;while(n<bytes.size()){auto wrote=::write(fd,bytes.data()+n,bytes.size()-n);first_probe::require(wrote>0,"output write");n+=wrote;}first_probe::require(::fsync(fd)==0,"output fsync");::close(fd);
 std::cout<<first_probe::Json{{"output",output},{"cases",result["cases"].size()},{"baselines",result["baselines"]},{"optimizer_calls",0}}.dump()<<'\n';return 0;
 }catch(const std::exception &e){std::cerr<<"fixed-tail probe failed: "<<e.what()<<'\n';return 2;}}
