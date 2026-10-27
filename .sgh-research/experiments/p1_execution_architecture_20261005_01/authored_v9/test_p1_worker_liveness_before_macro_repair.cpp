// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include <gtest/gtest.h>
#include <csignal>
#include <sys/wait.h>
#include "p1_worker_liveness.hpp"
namespace {
class Child {
 public:
  Child(){int pipefd[2];if(pipe(pipefd))throw std::runtime_error("pipe");pid=fork();
    if(pid<0){close(pipefd[0]);close(pipefd[1]);throw std::runtime_error("fork");}
    if(pid==0){close(pipefd[1]);char b;while(read(pipefd[0],&b,1)<0&&errno==EINTR){}close(pipefd[0]);_exit(0);}
    close(pipefd[0]);writer=pipefd[1];}
  ~Child(){if(writer>=0)close(writer);if(!reaped){kill(pid,SIGKILL);while(waitpid(pid,nullptr,0)<0&&errno==EINTR){}}}
  void exit(){if(writer>=0){close(writer);writer=-1;}}
  void reap(){while(waitpid(pid,nullptr,0)<0&&errno==EINTR){}reaped=true;}
  pid_t pid;int writer=-1;bool reaped=false;
};
TEST(WorkerLiveness,RejectsNonpositive){EXPECT_THROW(p1::WorkerLiveness(0),std::runtime_error);EXPECT_THROW(p1::WorkerLiveness(-1),std::runtime_error);}
TEST(WorkerLiveness,RejectsOverflow){EXPECT_THROW(p1::WorkerLiveness(int64_t(std::numeric_limits<pid_t>::max())+1),std::runtime_error);}
TEST(WorkerLiveness,RejectsMissingProcess){EXPECT_THROW(p1::WorkerLiveness(std::numeric_limits<pid_t>::max()),std::runtime_error);}
TEST(WorkerLiveness,AliveThenExited){Child c;p1::WorkerLiveness monitor(c.pid);EXPECT_EQ(monitor.reason(),"");c.exit();c.reap();EXPECT_EQ(monitor.reason(),"worker_process_exited");}
TEST(WorkerLiveness,KilledBeforeReaping){Child c;p1::WorkerLiveness monitor(c.pid);ASSERT_EQ(kill(c.pid,SIGKILL),0);siginfo_t info{};ASSERT_EQ(waitid(P_PID,c.pid,&info,WEXITED|WNOWAIT),0);EXPECT_EQ(monitor.reason(),"worker_process_exited");c.reap();}
TEST(WorkerLiveness,OldIdentityRemainsDead){Child old;p1::WorkerLiveness original(old.pid);old.exit();old.reap();Child next;p1::WorkerLiveness replacement(next.pid);EXPECT_EQ(original.reason(),"worker_process_exited");EXPECT_EQ(replacement.reason(),"");}
}  // namespace
