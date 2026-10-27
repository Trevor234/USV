// SPDX-License-Identifier: MIT
#include "replay.hpp"
#include <iostream>
#include <openssl/evp.h>
#include <fcntl.h>
#include <unistd.h>
#include <filesystem>
#include <iomanip>
#include <sstream>
#ifndef P1_REPLAY_SOURCE_BUNDLE_SHA256
#error pinned source bundle required
#endif
static std::string file_sha(const std::string &path){std::ifstream in(path,std::ios::binary);bias_replay::require(bool(in),"SHA input missing");std::string bytes((std::istreambuf_iterator<char>(in)),{});unsigned char d[32];unsigned n=0;bias_replay::require(EVP_Digest(bytes.data(),bytes.size(),d,&n,EVP_sha256(),nullptr)==1&&n==32,"SHA failure");std::ostringstream o;o<<std::hex<<std::setfill('0');for(auto c:d)o<<std::setw(2)<<unsigned(c);return o.str();}
int main(int argc,char **argv){try {
 bias_replay::require(argc==5&&std::string(argv[1])=="--input"&&std::string(argv[3])=="--output","usage --input absolute.json --output create-only.json");std::string input=argv[2],output=argv[4];bias_replay::require(std::filesystem::path(input).is_absolute()&&std::filesystem::path(output).is_absolute(),"absolute paths required");
 const auto before=file_sha(input);auto data=bias_replay::read(input);bias_replay::Json cases=bias_replay::Json::array();
 for(const auto &id:data.at("selected_job_ids")){auto variant=data;variant["selected_job_id"]=id;auto g=bias_replay::prefix_replay(variant,false),t=bias_replay::prefix_replay(variant,true);cases.push_back({{"job_id",id},{"G",g},{"T_selected_only",t}});}
 const auto &first=data.at("ordered_native_jobs")[0]["job"];bias_replay::require(bias_replay::task_time_job(first,data)["reference"]==first["reference"],"first reference must be bit-identical");
 bias_replay::Json result={{"schema","p1-actual-Acados-task-time-replay-v1"},{"input_path",input},{"input_sha256",before},{"source_bundle_sha256",P1_REPLAY_SOURCE_BUNDLE_SHA256},{"binary_sha256",file_sha("/proc/self/exe")},{"cases",cases},{"first_job_G_T_reference_bit_identical",true},{"all_numeric_solver_parameters_unchanged",true},{"actual_ROS_nodes_started",false},{"codegen_performed",false},{"install_performed",false},{"stage_qualified",false},{"execute_qualified",false},{"research_conclusion",false}};
 bias_replay::require(before==file_sha(input),"input changed during read-only replay");result["input_unchanged"]=true;
 auto bytes=result.dump(2)+"\n";int fd=::open(output.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);bias_replay::require(fd>=0,"create-only result open");size_t n=0;while(n<bytes.size()){auto wrote=::write(fd,bytes.data()+n,bytes.size()-n);bias_replay::require(wrote>0,"result write failed");n+=wrote;}bias_replay::require(::fsync(fd)==0,"result fsync failed");::close(fd);
 std::cout<<bias_replay::Json{{"output",output},{"cases",cases.size()},{"first_job_G_T_reference_bit_identical",true}}.dump()<<'\n';return 0;
 }catch(const std::exception &e){std::cerr<<"offline replay failed: "<<e.what()<<'\n';return 2;}}
