// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#pragma once
#include <cerrno>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <poll.h>
#include <sys/syscall.h>
#include <unistd.h>
namespace p1 {
// Pin the process identity once. No /proc scan, wait, signal or restart occurs
// in either control commit. A dead pidfd stays dead even if numeric PIDs recycle.
class WorkerLiveness {
 public:
  explicit WorkerLiveness(int64_t pid) {
    if(pid<=0||pid>std::numeric_limits<pid_t>::max())throw std::runtime_error("invalid worker PID");
    fd_=static_cast<int>(syscall(SYS_pidfd_open,static_cast<pid_t>(pid),0));
    if(fd_<0)throw std::runtime_error("cannot pin worker process identity");
  }
  ~WorkerLiveness(){if(fd_>=0)close(fd_);}
  WorkerLiveness(const WorkerLiveness &)=delete;
  WorkerLiveness & operator=(const WorkerLiveness &)=delete;
  std::string reason()const {
    pollfd p{fd_,POLLIN,0};const int rc=poll(&p,1,0);
    if(rc==0)return "";
    if(rc<0||p.revents&(POLLERR|POLLNVAL))return "worker_liveness_check_failed";
    return p.revents&(POLLIN|POLLHUP)?"worker_process_exited":"worker_liveness_check_failed";
  }
 private:int fd_=-1;
};
}  // namespace p1
