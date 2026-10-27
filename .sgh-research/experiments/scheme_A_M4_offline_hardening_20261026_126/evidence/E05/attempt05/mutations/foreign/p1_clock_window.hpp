// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#pragma once
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <utility>
namespace p1 {
struct RtfEstimate {
  double value=0;
  bool valid=false;
  int64_t span_ns=0;
  size_t stored_samples=0;
};
// Keep a time window independent of incoming clock frequency. Every observation
// is checked; only stored anchors are decimated. No valid estimate survives a
// short window, receive gap, invalid chronology, or clock epoch change.
class ClockWindow {
 public:
  static constexpr int64_t min_span_ns=400000000;
  static constexpr int64_t max_span_ns=600000000;
  static constexpr int64_t sample_spacing_ns=10000000;
  static constexpr size_t capacity=100;
  void reset(){samples_.clear();last_receive_=0;last_sim_=0;}
  RtfEstimate observe(int64_t receive,int64_t sim,double low,double high){
    if(receive<=0||sim<0||!std::isfinite(low)||!std::isfinite(high)||low<=0||low>high){reset();return {};}
    if(last_receive_&&(receive<=last_receive_||sim<last_sim_||sim-last_sim_>5000000000LL))reset();
    last_receive_=receive;last_sim_=sim;
    while(!samples_.empty()&&receive-samples_.front().first>max_span_ns)samples_.pop_front();
    if(samples_.empty()||receive-samples_.back().first>=sample_spacing_ns)samples_.push_back({receive,sim});
    while(samples_.size()>capacity)samples_.pop_front();
    RtfEstimate result;result.stored_samples=samples_.size();
    if(samples_.empty())return result;
    result.span_ns=receive-samples_.front().first;
    if(result.span_ns<min_span_ns)return result;
    result.value=double(sim-samples_.front().second)/double(result.span_ns);
    result.valid=std::isfinite(result.value)&&result.value>=low&&result.value<=high;
    return result;
  }
 private:
  std::deque<std::pair<int64_t,int64_t>> samples_;
  int64_t last_receive_=0,last_sim_=0;
};
}  // namespace p1
