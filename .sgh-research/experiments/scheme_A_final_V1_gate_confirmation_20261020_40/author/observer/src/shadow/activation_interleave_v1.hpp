// SPDX-License-Identifier: MIT
#pragma once
#include <atomic>
#include <chrono>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <thread>

namespace activation_interleave {
inline constexpr const char *policy="await_actual_odom_once_before_commit_v1";
inline constexpr int64_t wait_budget_ns=25000000;
inline void validate(const std::string &selected,int64_t budget,const std::string &mode,
                     bool witnessed,bool fault_enabled,bool other_fault){
  if(selected=="none"){
    if(budget!=0)throw std::runtime_error("disabled V3 must have zero wait budget");
    return;
  }
  if(selected!=policy||budget!=wait_budget_ns||mode!="shadow"||!witnessed||!fault_enabled||other_fault)
    throw std::runtime_error("V3 requires explicit isolated witnessed shadow policy and fixed bounded wait");
}
struct Record {
  bool used=false,changed=false,cancelled=false;
  int64_t begin_ns=0,deadline_ns=0,end_ns=0;
  uint64_t captured_sequence=0,observed_before=0,observed_after=0;
};
// Only the tick thread claims the one-shot. A callback advertises its actual
// completed odometry admission; this class never changes sensor/business data.
class Once {
 public:
  void observe_odom(uint64_t sequence){committed_.store(sequence,std::memory_order_release);}
  template<class Clock,class Cancel>
  Record wait(bool enabled,bool eligible,uint64_t captured,Clock now,Cancel cancel){
    Record r;
    if(!enabled||!eligible||claimed_)return r;
    claimed_=true;r.used=true;r.captured_sequence=captured;
    r.begin_ns=now();r.deadline_ns=r.begin_ns+wait_budget_ns;
    r.observed_before=committed_.load(std::memory_order_acquire);
    for(;;){
      r.observed_after=committed_.load(std::memory_order_acquire);
      r.cancelled=cancel();r.end_ns=now();
      r.changed=r.observed_after>captured;
      if(r.changed||r.cancelled||r.end_ns>=r.deadline_ns)break;
      std::this_thread::sleep_for(std::chrono::microseconds(100));
    }
    return r;
  }
 private:
  bool claimed_=false;
  std::atomic<uint64_t> committed_{0};
};
}
