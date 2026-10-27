#pragma once
#include <cstdint>
#include <stdexcept>
#include <string>
namespace p1 {
// Trusted callback receipt lease only. WorkerCapability v1 has no packet
// sequence/send time: this is neither source freshness nor solve progress.
class CapabilityLease {
 public:
  explicit CapabilityLease(int64_t timeout):timeout_(timeout) {
    if(timeout<200000000LL||timeout>5000000000LL)
      throw std::runtime_error("capability receipt lease outside finite diagnostic bounds");
  }
  std::string check(int64_t now) {
    if(!reason_.empty())return reason_;
    if(now<=0||(armed_&&now<last_))reason_="worker_capability_clock_invalid";
    else if(armed_&&now-last_>timeout_)reason_="worker_capability_expired";
    return reason_;
  }
  bool renew(int64_t now) {
    if(!check(now).empty())return false;
    last_=now;armed_=true;return true;
  }
  int64_t last_valid_ns() const{return last_;}
  int64_t timeout_ns() const{return timeout_;}
 private:
  int64_t timeout_,last_=0;bool armed_=false;std::string reason_;
};
}
