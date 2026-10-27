// C3.4-A link-time IO injection. The actual production header has no hooks.
#include "p1_create_only_atomic.hpp"
#include <nlohmann/json.hpp>
#include <sys/stat.h>
#include <cstdarg>
#include <filesystem>
#include <fstream>
#include <iostream>
static std::string mode;
static int writes=0;
extern "C" int __real_fsync(int);
extern "C" ssize_t __real_write(int,const void*,size_t);
extern "C" long __real_syscall(long,...);
extern "C" int __wrap_fsync(int fd) {
  struct stat st{};
  if (::fstat(fd,&st)!=0) return -1;
  if ((mode=="file_fsync_failure"&&!S_ISDIR(st.st_mode)) ||
      (mode=="directory_fsync_failure"&&S_ISDIR(st.st_mode))) {errno=EIO;return -1;}
  return __real_fsync(fd);
}
extern "C" ssize_t __wrap_write(int fd,const void*data,size_t n) {
  ++writes;
  if (mode=="write_failure") {errno=ENOSPC;return -1;}
  if (mode=="eintr_short_write"&&writes==1) {errno=EINTR;return -1;}
  return __real_write(fd,data,mode=="eintr_short_write"?std::min(n,size_t(2)):n);
}
extern "C" long __wrap_syscall(long number,...) {
  if (number!=SYS_renameat2) {errno=ENOSYS;return -1;}
  va_list args;va_start(args,number);int oldfd=va_arg(args,int);const char*oldname=va_arg(args,const char*);int newfd=va_arg(args,int);const char*newname=va_arg(args,const char*);unsigned flags=va_arg(args,unsigned);va_end(args);
  if (mode=="rename_unsupported") {errno=ENOSYS;return -1;}
  return __real_syscall(number,oldfd,oldname,newfd,newname,flags);
}
std::string bytes(const std::filesystem::path&p) {std::ifstream f(p,std::ios::binary);return {std::istreambuf_iterator<char>(f),std::istreambuf_iterator<char>()};}
int main(int argc,char**argv) {
 using Json=nlohmann::json;namespace fs=std::filesystem;
 if (argc!=3)return 2;
 const fs::path root(argv[1]);fs::create_directory(root);const auto target=root/"target";const std::string input="written fully before publication\n";
 std::string requested=argv[2];
 if(requested=="eexist") {std::ofstream f(target);f<<"original target\n";}
 struct stat original{};if(fs::exists(target))::stat(target.c_str(),&original);
 int directory=::open(root.c_str(),O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(directory<0)return 3;
 mode=requested;Json result={{"case",mode},{"returned",false},{"error_errno",nullptr},{"ambiguous",false}};
 try {p1_create_only::write_create_only_at(directory,"target","owned-temporary",input,target.string());result["returned"]=true;}
 catch(const p1_create_only::PublicationAmbiguousError&e) {result["ambiguous"]=e.target_visible;result["error_errno"]=e.code().value();result["error"]=e.what();}
 catch(const std::system_error&e) {result["error_errno"]=e.code().value();result["error"]=e.what();}
 catch(const std::exception&e) {result["error"]=e.what();}
 ::close(directory);result["target_exists"]=fs::exists(target);result["temporary_exists"]=fs::exists(root/"owned-temporary");result["writes"]=writes;
 if(fs::exists(target)) {struct stat st{};::stat(target.c_str(),&st);result["nlink"]=st.st_nlink;result["bytes"]=bytes(target);result["original_inode_retained"]=original.st_ino==st.st_ino;}
 bool pass=!result["temporary_exists"].get<bool>();
 if(mode=="normal"||mode=="eintr_short_write") pass=pass&&result["returned"]==true&&result["bytes"]==input&&result["nlink"]==1;
 else if(mode=="directory_fsync_failure")pass=pass&&result["ambiguous"]==true&&result["target_exists"]==true&&result["bytes"]==input&&result["nlink"]==1&&result["error_errno"]==EIO;
 else if(mode=="eexist")pass=pass&&result["error_errno"]==EEXIST&&result["bytes"]=="original target\n"&&result["original_inode_retained"]==true;
 else pass=pass&&result["target_exists"]==false&&result["error_errno"]==(mode=="write_failure"?ENOSPC:mode=="rename_unsupported"?ENOSYS:EIO);
 result["passed"]=pass;result["scope"]="actual shared v10 header, test-only link wrappers; no ROS";std::cout<<result.dump()<<std::endl;return pass?0:4;
}
