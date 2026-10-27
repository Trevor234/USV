// SPDX-License-Identifier: MIT
#pragma once
#include <deque>
#include <optional>
#include <vector>
#include "p1_admission.hpp"

namespace activation_alignment {
inline constexpr const char *policy="latest_causal_sensor_frame_then_one_revalidation_v1";
inline constexpr size_t capacity=32, attempts=2;
struct Frame {
  p1::State state{};p1::Version version;
  uint64_t history_generation=0,input_commit_ordinal=0,origin_sequence=0,odom_sequence=0,imu_sequence=0;
  int64_t odom_stamp_ns=0,imu_stamp_ns=0,odom_receive_ns=0,imu_receive_ns=0;
  bool r_from_imu=false;std::string origin_kind;
};
inline nlohmann::json json(const Frame &f){return {
  {"state",f.state},{"version",{{"task",f.version.task},{"model",f.version.model},{"config",f.version.config},{"schedule",f.version.schedule},{"epoch",f.version.epoch}}},
  {"history_generation",f.history_generation},{"input_commit_ordinal",f.input_commit_ordinal},
  {"origin_kind",f.origin_kind},{"origin_sequence",f.origin_sequence},{"odom_sequence",f.odom_sequence},
  {"imu_sequence",f.imu_sequence},{"odom_stamp_ns",f.odom_stamp_ns},{"imu_stamp_ns",f.imu_stamp_ns},
  {"odom_receive_ns",f.odom_receive_ns},{"imu_receive_ns",f.imu_receive_ns},{"r_from_imu",f.r_from_imu}};}
class History {
 public:
  void clear(){if(generation_==UINT64_MAX)throw std::runtime_error("sensor history generation exhausted");++generation_;frames_.clear();}
  void append(Frame f){f.history_generation=generation_;frames_.push_back(std::move(f));if(frames_.size()>capacity)frames_.pop_front();}
  uint64_t generation()const{return generation_;}
  std::vector<Frame> copy()const{return {frames_.begin(),frames_.end()};}
 private:uint64_t generation_=1;std::deque<Frame> frames_;
};
struct Selection {std::optional<Frame> frame;size_t scanned=0;};
// Snapshot remains the raw current capture. Only the returned immutable sensor
// frame replaces state/provenance in a separate prediction snapshot.
template<class Snapshot>
Selection select(const Snapshot &s,int64_t target,const p1::SourceAgeLimits &limits,int64_t skew){
  Selection out;
  if(s.activation_frames.size()>capacity)return out;
  for(auto it=s.activation_frames.rbegin();it!=s.activation_frames.rend();++it){
    ++out.scanned;const auto &f=*it;
    if(f.history_generation!=s.activation_history_generation||!(f.version==s.version)||f.input_commit_ordinal>s.input_commit_ordinal||
       !f.odom_sequence||f.odom_stamp_ns<0||f.odom_stamp_ns>target||target-f.odom_stamp_ns>1000000000LL||
       (f.r_from_imu&&(!f.imu_sequence||f.imu_stamp_ns<0||f.imu_stamp_ns>target||std::abs(f.imu_stamp_ns-f.odom_stamp_ns)>skew)))continue;
    if(!std::all_of(f.state.begin(),f.state.end(),[](double v){return std::isfinite(v);}))continue;
    if(!p1::state_source_check(s.freeze,s.sim,s.clock_receive,{f.odom_stamp_ns,f.odom_receive_ns},
         {f.imu_stamp_ns,f.imu_receive_ns},f.r_from_imu,limits).empty())continue;
    std::array<bool,2> found{false,false};
    for(const auto &e:s.history)if(e.sim_ns<=f.odom_stamp_ns&&(e.channel==0||e.channel==1))found[e.channel]=true;
    if(!found[0]||!found[1])continue;
    out.frame=f;return out;
  }
  return out;
}
template<class Snapshot>void apply(Snapshot &s,const Frame &f){
  std::copy(f.state.begin(),f.state.end(),s.state.data());
  s.odom_seq=f.odom_sequence;s.imu_seq=f.imu_sequence;s.odom_stamp=f.odom_stamp_ns;s.imu_stamp=f.imu_stamp_ns;
  s.odom_receive=f.odom_receive_ns;s.imu_receive=f.imu_receive_ns;s.mixed=f.r_from_imu;
}
}
