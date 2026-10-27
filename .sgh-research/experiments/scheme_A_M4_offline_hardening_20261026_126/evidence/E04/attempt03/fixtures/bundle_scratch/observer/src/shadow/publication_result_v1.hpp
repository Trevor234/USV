// SPDX-License-Identifier: MIT
#pragma once
#include "p1_admission.hpp"
#include <array>
#include <cmath>
#include <cstdint>

namespace p1::publication {
// These are local API results. A returned publish never proves plant receipt.
struct CallResult {int64_t start_ns=0,end_ns=0;bool returned=false;};
struct Policy {int64_t span_budget_ns=5000000,gap_ns=240000000;double rho=80;};
struct PairResult {
  std::array<CallResult,2> calls{};
  std::array<bool,2> gap_exceeded{},rate_exceeded{};
  bool span_exceeded=false,rho_available=false;
  bool timing_failed()const{return span_exceeded||gap_exceeded[0]||gap_exceeded[1]||rate_exceeded[0]||rate_exceeded[1];}
};

// Caller serializes this with its state/clock invalidation lock. Failed calls
// retain the last numeric receipt but invalidate its authority, per channel.
inline void apply_channel_result(Anchor &anchor,int channel,double command,const CallResult &r){
  if(r.returned){anchor.n[channel]=command;anchor.time[channel]=r.start_ns;++anchor.seq[channel];anchor.known[channel]=true;}
  else anchor.known[channel]=false;
}

// One control-thread owner; neither ROS nor a shared mutex is held here.
// before_call and commit perform the caller's short protected snapshots/updates.
// Both send calls are attempted in order, including after a failure on the left.
// A commit exception propagates: it is not relabeled a failed send.
template<class Clock,class Before,class Send,class Commit>
PairResult publish_pair(const Command &command,const Anchor &previous,const Policy &policy,
                        Clock &&clock,Before &&before_call,Send &&send,Commit &&commit){
  PairResult result;
  for(int channel=0;channel<2;++channel){
    auto &r=result.calls[channel];r.start_ns=clock();before_call(channel,r.start_ns);
    try{send(channel,command[channel]);r.returned=true;}catch(...){r.returned=false;}
    r.end_ns=clock();commit(channel,r);
  }
  result.span_exceeded=result.calls[1].end_ns-result.calls[0].start_ns>policy.span_budget_ns;
  result.rho_available=previous.known[0]&&previous.known[1];
  for(int channel=0;channel<2;++channel){
    const auto &r=result.calls[channel];
    if(!previous.known[channel]||!r.returned){result.rho_available=false;continue;}
    const auto elapsed=r.start_ns-previous.time[channel];
    result.gap_exceeded[channel]=elapsed>policy.gap_ns;
    result.rate_exceeded[channel]=std::abs(command[channel]-previous.n[channel])>policy.rho*elapsed/1e9+1e-9;
    if(result.gap_exceeded[channel]||result.rate_exceeded[channel])result.rho_available=false;
  }
  return result;
}

struct ShutdownResult {bool zero_requested=false,exit_tick=false,zero_target_published=false,grace_exceeded=false;};
// Keep the original finite-close policy: requesting zero can permit exit even
// when a send fails. Successful zero-pair publication is a separate fact.
inline ShutdownResult shutdown_result(bool stopping,bool execute,const Command &target,
                                      const std::array<bool,2> &returned,int64_t now,
                                      int64_t stop_start,int64_t grace_ns){
  ShutdownResult r;
  r.zero_requested=std::abs(target[0])<1e-9&&std::abs(target[1])<1e-9;
  r.exit_tick=stopping&&(r.zero_requested||now-stop_start>=grace_ns);
  r.zero_target_published=execute&&r.zero_requested&&returned[0]&&returned[1];
  r.grace_exceeded=r.exit_tick&&!r.zero_requested;
  return r;
}
} // namespace p1::publication
