// SPDX-License-Identifier: MIT
// Process-internal endpoint/config evidence; external supervisor authenticates authorship.
#pragma once
#include <rclcpp/rclcpp.hpp>
#include <rcl/subscription.h>
#include <rmw/rmw.h>
#include <rmw_fastrtps_shared_cpp/custom_subscriber_info.hpp>
#include <nlohmann/json.hpp>
#include <openssl/evp.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <algorithm>
#include <chrono>
#include <cerrno>
#include <cctype>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace p1_owned {
using Json=nlohmann::json;
inline void require(bool v,const std::string &why){if(!v)throw std::runtime_error(why);}
inline int64_t steady_ns(){return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
inline bool sha256_shape(const std::string &v){return v.size()==64&&v.find_first_not_of("0123456789abcdef")==std::string::npos;}
inline std::string hex(const unsigned char *p,size_t n){std::ostringstream o;o<<std::hex<<std::setfill('0');for(size_t i=0;i<n;++i)o<<std::setw(2)<<unsigned(p[i]);return o.str();}
inline std::string sha256_bytes(const std::string &s){unsigned char d[EVP_MAX_MD_SIZE];unsigned n=0;require(EVP_Digest(s.data(),s.size(),d,&n,EVP_sha256(),nullptr)==1&&n==32,"owned SHA256 failed");return hex(d,n);}
inline std::string file_sha256(const std::string &path){
  std::ifstream f(path,std::ios::binary);require(bool(f),"owned identity file unavailable");
  EVP_MD_CTX *ctx=EVP_MD_CTX_new();require(ctx!=nullptr,"owned digest allocation");
  unsigned char d[EVP_MAX_MD_SIZE];unsigned n=0;char buffer[16384];bool ok=EVP_DigestInit_ex(ctx,EVP_sha256(),nullptr)==1;
  while(f&&ok){f.read(buffer,sizeof(buffer));if(f.gcount())ok=EVP_DigestUpdate(ctx,buffer,size_t(f.gcount()))==1;}
  ok=ok&&f.eof()&&EVP_DigestFinal_ex(ctx,d,&n)==1;EVP_MD_CTX_free(ctx);require(ok&&n==32,"owned file digest failed");return hex(d,n);
}
class Fd {
 public:explicit Fd(int fd=-1):fd_(fd){}~Fd(){if(fd_>=0)::close(fd_);}Fd(const Fd&)=delete;Fd& operator=(const Fd&)=delete;Fd(Fd&&o)noexcept:fd_(o.fd_){o.fd_=-1;}int get()const{return fd_;}
 private:int fd_;
};
inline Fd open_directory(const std::filesystem::path &path){
  require(path.is_absolute(),"owned path must be absolute");int current=::open("/",O_RDONLY|O_DIRECTORY|O_CLOEXEC);require(current>=0,"owned root open failed");
  for(const auto &part:path.relative_path()){const auto name=part.string();if(name.empty()||name=="."||name==".."){::close(current);throw std::runtime_error("owned unsafe path");}
    int next=::openat(current,name.c_str(),O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);::close(current);require(next>=0,"owned directory missing or symlink");current=next;}
  return Fd(current);
}
class PublicationAmbiguousError:public std::runtime_error{
 public:explicit PublicationAmbiguousError(const std::string &path,const std::string &sha):std::runtime_error("owned target visible; durability unconfirmed: "+path),path(path),content_sha256(sha){}const std::string path,content_sha256;
};
inline void write_create_only(const std::string &path,const Json &value){
  const std::filesystem::path p(path);const auto dir=open_directory(p.parent_path());const auto name=p.filename().string();
  require(!name.empty()&&name!="."&&name!="..","owned unsafe output filename");const auto bytes=value.dump()+"\n";require(bytes.size()<=256*1024,"owned manifest budget exceeded");
  const auto temp="."+name+".tmp."+std::to_string(::getpid())+"."+std::to_string(steady_ns());Fd fd(::openat(dir.get(),temp.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600));require(fd.get()>=0,"owned temp create failed");bool linked=false;
  try{size_t done=0;while(done<bytes.size()){ssize_t n=::write(fd.get(),bytes.data()+done,bytes.size()-done);if(n<0&&errno==EINTR)continue;require(n>0,"owned output write failed");done+=size_t(n);}require(::fsync(fd.get())==0,"owned file fsync failed");
    require(::linkat(dir.get(),temp.c_str(),dir.get(),name.c_str(),0)==0,"owned destination exists or link failed");linked=true;
    if(::unlinkat(dir.get(),temp.c_str(),0)!=0||::fsync(dir.get())!=0)throw PublicationAmbiguousError(path,sha256_bytes(bytes));
  }catch(...){::unlinkat(dir.get(),temp.c_str(),0);if(linked){/* Visible evidence is deliberately retained. */}throw;}
}
inline std::string read_bounded(const std::string &path,size_t limit=65536){std::ifstream f(path,std::ios::binary);require(bool(f),"owned proc read failed");std::string s(limit+1,'\0');f.read(s.data(),s.size());s.resize(size_t(f.gcount()));require(!f.bad()&&s.size()<=limit,"owned proc input exceeds bound");return s;}
inline std::string boot_id(){auto s=read_bounded("/proc/sys/kernel/random/boot_id",128);while(!s.empty()&&std::isspace(static_cast<unsigned char>(s.back())))s.pop_back();require(!s.empty(),"owned boot empty");return s;}
inline uint64_t process_start_ticks(){auto s=read_bounded("/proc/self/stat",4096);auto close=s.rfind(')');require(close!=std::string::npos,"owned proc stat malformed");std::istringstream in(s.substr(close+1));std::string token;for(int i=0;i<=19;++i)require(bool(in>>token),"owned proc stat truncated");size_t consumed=0;auto result=std::stoull(token,&consumed);require(consumed==token.size()&&result>0,"owned start ticks invalid");return result;}
inline std::string actual_exe(){std::vector<char> b(4097);ssize_t n=::readlink("/proc/self/exe",b.data(),b.size()-1);require(n>0&&size_t(n)<b.size()-1,"owned executable path invalid");return std::string(b.data(),size_t(n));}
inline Json actual_argv(){const auto s=read_bounded("/proc/self/cmdline");Json rows=Json::array();size_t begin=0;for(size_t i=0;i<s.size();++i)if(s[i]=='\0'){rows.push_back(s.substr(begin,i-begin));begin=i+1;}require(begin==s.size()&&!rows.empty(),"owned cmdline malformed");return rows;}
inline std::string rmw_identifier(){const char *id=rmw_get_implementation_identifier();require(id&&std::string(id)=="rmw_fastrtps_cpp","owned endpoint collection requires pinned rmw_fastrtps_cpp");return id;}
inline Json gid_json(const rmw_gid_t &gid){
  const auto id=rmw_identifier();require(gid.implementation_identifier&&std::string(gid.implementation_identifier)==id,"owned GID implementation mismatch");
  Json value=Json::array();bool nonzero=false;for(auto c:gid.data){value.push_back(unsigned(c));nonzero=nonzero||c!=0;}require(value.size()==RMW_GID_STORAGE_SIZE&&nonzero,"owned missing/invalid GID");return value;
}
inline Json publisher_endpoint(const rclcpp::PublisherBase &pub,const std::string &type){return {{"kind","publisher"},{"topic",pub.get_topic_name()},{"type",type},{"gid",gid_json(pub.get_gid())}};}
inline Json subscription_endpoint(const rclcpp::SubscriptionBase &sub,const std::string &type){
  const auto id=rmw_identifier();const auto h=sub.get_subscription_handle();require(bool(h),"owned subscription handle missing");const auto *rmw=rcl_subscription_get_rmw_handle(h.get());
  require(rmw&&rmw->implementation_identifier&&std::string(rmw->implementation_identifier)==id&&rmw->data,"owned subscription RMW mismatch");
  const auto *info=static_cast<const CustomSubscriberInfo *>(rmw->data);require(info->data_reader_!=nullptr,"owned actual DDS reader missing");
  return {{"kind","subscription"},{"topic",sub.get_topic_name()},{"type",type},{"gid",gid_json(info->subscription_gid_)}};
}
inline std::string double_canonical(double v){require(std::isfinite(v),"owned nonfinite parameter");static_assert(sizeof(double)==8&&std::numeric_limits<double>::is_iec559,"IEEE754 double required");uint64_t bits=0;std::memcpy(&bits,&v,8);std::ostringstream out;out<<std::hex<<std::setw(16)<<std::setfill('0')<<bits;return out.str();}
inline Json parameter_json(const rclcpp::Parameter &p){
  const auto v=p.to_parameter_msg().value;Json value,canonical;
  switch(v.type){
    case 0:value=nullptr;canonical=nullptr;break;
    case 1:value=v.bool_value;canonical=value;break;
    case 2:value=v.integer_value;canonical=value;break;
    case 3:value=v.double_value;canonical=double_canonical(v.double_value);break;
    case 4:value=v.string_value;canonical=value;break;
    case 5:value=v.byte_array_value;canonical=value;break;
    case 6:value=Json::array();for(bool x:v.bool_array_value)value.push_back(x);canonical=value;break;
    case 7:value=v.integer_array_value;canonical=value;break;
    case 8:value=v.double_array_value;canonical=Json::array();for(double x:v.double_array_value)canonical.push_back(double_canonical(x));break;
    case 9:value=v.string_array_value;canonical=value;break;
    default:throw std::runtime_error("owned unknown parameter type");
  }
  return {{"type",int(v.type)},{"value",value},{"canonical_value",canonical}};
}
inline Json effective_parameters(const rclcpp::Node &node){auto names=node.list_parameters({},0).names;std::sort(names.begin(),names.end());require(names.size()<=512,"owned parameter count exceeds bound");Json rows=Json::object();for(const auto &p:node.get_parameters(names))rows[p.get_name()]=parameter_json(p);return rows;}
inline Json canonical_parameters(const Json &rows){Json out=Json::object();for(auto it=rows.begin();it!=rows.end();++it)out[it.key()]={{"type",it.value().at("type")},{"canonical_value",it.value().at("canonical_value")}};return out;}
inline rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr freeze_parameters(rclcpp::Node &node){
  return node.add_on_set_parameters_callback([](const std::vector<rclcpp::Parameter>&){rcl_interfaces::msg::SetParametersResult r;r.successful=false;r.reason="owned startup parameters are immutable";return r;});
}
inline Json source_fd_identity(const std::string &path){
  const std::filesystem::path p(path);const auto parent=open_directory(p.parent_path());(void)parent;require(p.filename()!="."&&p.filename()!="..","owned source path unsafe");
  Json rows=Json::array();for(const auto &entry:std::filesystem::directory_iterator("/proc/self/fd")){
    auto name=entry.path().filename().string();if(name.empty()||name.find_first_not_of("0123456789")!=std::string::npos)continue;int fd=std::stoi(name);std::vector<char> target(4097);ssize_t n=::readlink(entry.path().c_str(),target.data(),target.size()-1);
    if(n<0||size_t(n)>=target.size()-1||std::string(target.data(),size_t(n))!=path)continue;struct stat st{};int flags=::fcntl(fd,F_GETFL);
    require(::fstat(fd,&st)==0&&S_ISREG(st.st_mode)&&flags>=0,"owned source FD is not regular");
    rows.push_back({{"fd",fd},{"path",path},{"device",uint64_t(st.st_dev)},{"inode",uint64_t(st.st_ino)},{"mode",uint32_t(st.st_mode)},{"flags",flags},{"append",bool(flags&O_APPEND)},{"access_mode",flags&O_ACCMODE}});
  }
  require(rows.size()==1,"owned source FD missing/ambiguous");return rows[0];
}
inline Json role_manifest(rclcpp::Node &node,const std::string &role,const std::string &run,const std::string &contract_sha,const std::string &source_bundle_sha,const Json &endpoints,const Json &extra=Json::object()){
  require(!role.empty()&&!run.empty()&&sha256_shape(contract_sha)&&sha256_shape(source_bundle_sha),"owned role identity invalid");require(endpoints.is_array()&&!endpoints.empty()&&endpoints.size()<=128,"owned endpoint population invalid");
  std::set<std::string> unique;for(const auto &e:endpoints){require(e.at("topic").is_string()&&e.at("type").is_string()&&e.at("gid").is_array()&&e.at("gid").size()==RMW_GID_STORAGE_SIZE,"owned malformed endpoint");require(unique.insert(e.at("kind").get<std::string>()+":"+e.at("topic").get<std::string>()+":"+e.at("gid").dump()).second,"owned duplicate endpoint");}
  const auto params=effective_parameters(node);Json overrides=Json::object();for(const auto &item:node.get_node_parameters_interface()->get_parameter_overrides())overrides[item.first]=parameter_json(rclcpp::Parameter(item.first,item.second));
  Json m={{"schema_version","p1-owned-role-v1"},{"role",role},{"run_id",run},{"contract_sha256",contract_sha},{"boot_id",boot_id()},{"pid",::getpid()},{"process_start_ticks",process_start_ticks()},
    {"pgid",::getpgrp()},{"sid",::getsid(0)},{"exe",actual_exe()},{"binary_sha256",file_sha256("/proc/self/exe")},{"source_bundle_sha256",source_bundle_sha},{"created_steady_ns",steady_ns()},
    {"node",node.get_fully_qualified_name()},{"rmw_implementation",rmw_identifier()},{"gid_storage_size",RMW_GID_STORAGE_SIZE},{"endpoints",endpoints},{"effective_parameters",params},{"parameter_overrides",overrides},
    {"effective_parameters_digest_encoding","p1-typed-ieee754-v1"},{"effective_parameters_sha256",sha256_bytes(canonical_parameters(params).dump())},{"argv",actual_argv()},
    {"effective_parameters_immutable",true},{"execute_qualified",false},{"physical_release_qualified",false}};
  require(extra.is_object(),"owned extras must be object");for(auto it=extra.begin();it!=extra.end();++it){require(!m.contains(it.key()),"owned extra attempts identity overwrite");m[it.key()]=it.value();}return m;
}
} // namespace p1_owned
