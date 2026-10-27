#pragma once
#include <array>
#include <cmath>
#include <optional>
#include <nlohmann/json.hpp>
#include "p1_admission.hpp"

namespace p1::d0 {
using Json=nlohmann::json;
inline bool finite_state(const std::array<double,6> &a){return std::all_of(a.begin(),a.end(),[](double v){return std::isfinite(v);});}
struct Observation {
  bool predict_invoked=false,predict_success=false,predicted_state_available=false,full_error_available=false;
  std::array<double,6> predicted_state{},full_error{};
  bool input_change_gate_ran=false;
  std::optional<bool> input_change_gate_unchanged;
};
inline void observe_prediction(Observation &o,bool success,const std::array<double,6> &actual,const std::array<double,6> &target){
  o.predict_invoked=true;o.predict_success=success;
  o.predicted_state_available=success&&finite_state(actual);
  o.full_error_available=o.predicted_state_available&&finite_state(target);
  if(o.predicted_state_available)o.predicted_state=actual;
  if(o.full_error_available){
    for(size_t i=0;i<6;++i)o.full_error[i]=i==2?p1::wrap(actual[i]-target[i]):actual[i]-target[i];
    o.full_error_available=finite_state(o.full_error);
  }
}
inline Json version_json(const p1::Version &v){return {{"task",v.task},{"model",v.model},{"config",v.config},{"schedule",v.schedule},{"epoch",v.epoch}};}
template<class Snapshot> Json source_json(const Snapshot &s){return {{"version",version_json(s.version)},{"odom_sequence",s.odom_seq},{"odom_stamp_ns",s.odom_stamp},{"odom_receive_ns",s.odom_receive},{"imu_sequence",s.imu_seq},{"imu_stamp_ns",s.imu_stamp},{"imu_receive_ns",s.imu_receive},{"r_from_imu",s.mixed},{"clock_sim_ns",s.sim},{"clock_receive_ns",s.clock_receive},{"rtf",s.rtf},{"rtf_valid",s.rtf_valid},{"paused",s.paused}};}
template<class Snapshot> Json json(const Snapshot &validation,const Snapshot &final_source,int64_t copy_capture_ns,const Observation &o,bool pair,uint64_t job,uint64_t target_tick,int64_t target_sim){
  Json v=source_json(validation),f=source_json(final_source);std::array<double,6> state{};
  std::copy(validation.state.data(),validation.state.data()+6,state.begin());
  v["state"]=state;v["sample_ns"]=validation.freeze;v["copy_capture_ns"]=copy_capture_ns;v["capture_semantics"]="mutex_copy_end";
  v["anchor"]={{"n",validation.anchor.n},{"sequence",validation.anchor.seq},{"publish_ns",validation.anchor.time},{"known",validation.anchor.known}};
  v["held_history"]=Json::array();for(const auto &e:validation.history)v["held_history"].push_back({{"sim_ns",e.sim_ns},{"channel",e.channel},{"value",e.value}});
  v["history_count"]=validation.history.size();f["commit_ns"]=final_source.freeze;
  return {{"schema","p1-d0-observation-v1"},{"candidate_pair_available",pair},{"candidate_job_id",pair?Json(job):Json(nullptr)},{"candidate_target_tick",pair?Json(target_tick):Json(nullptr)},{"prediction_target_sim_ns",pair?Json(target_sim):Json(nullptr)},
    {"predict_invoked",o.predict_invoked},{"predict_success",o.predict_success},{"predict_status",!o.predict_invoked?"not_attempted":o.predict_success?"success":"history_or_time_failed"},
    {"predicted_state_available",o.predicted_state_available},{"predicted_state",o.predicted_state_available?Json(o.predicted_state):Json(nullptr)},
    {"full_error_available",o.full_error_available},{"full_error",o.full_error_available?Json(o.full_error):Json(nullptr)},
    {"validation_snapshot",v},{"input_change_gate_ran",o.input_change_gate_ran},{"input_change_gate_unchanged",o.input_change_gate_unchanged?Json(*o.input_change_gate_unchanged):Json(nullptr)},{"final_snapshot",f}};
}
} // namespace p1::d0
