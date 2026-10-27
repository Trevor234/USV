#pragma once
#include <algorithm>
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
  // One slot per original read occurrence. Unread short-circuit operands stay
  // null; these values are neither a later policy snapshot nor a global order.
  std::optional<bool> early_legacy_enabled,early_legacy_measurement;
  std::optional<bool> early_stopping,early_worker_unusable;
  std::optional<bool> commit_legacy_enabled,commit_legacy_measurement;
  std::optional<bool> commit_worker_unusable,commit_worker_valid,commit_sink_failed;
  std::optional<bool> final_stopping,final_stop_requested;
  std::optional<bool> fallback_invalid_stopping,fallback_invalid_worker_unusable;
  std::optional<bool> fallback_source_stopping,fallback_source_worker_unusable;
  std::optional<bool> input_version_equal,input_odom_equal,input_imu_equal;
};
// The caller supplies the once-evaluated original operand. C++ &&/|| still
// decides whether this function and that operand are evaluated at all.
inline bool tap(std::optional<bool> &slot,bool value) noexcept {slot=value;return value;}
inline Json nullable_bool(const std::optional<bool> &value){return value?Json(*value):Json(nullptr);}
inline Json gate_reads_json(const Observation &o){return {
  {"early_legacy_enabled",nullable_bool(o.early_legacy_enabled)},
  {"early_legacy_measurement",nullable_bool(o.early_legacy_measurement)},
  {"early_stopping",nullable_bool(o.early_stopping)},
  {"early_worker_unusable",nullable_bool(o.early_worker_unusable)},
  {"commit_legacy_enabled",nullable_bool(o.commit_legacy_enabled)},
  {"commit_legacy_measurement",nullable_bool(o.commit_legacy_measurement)},
  {"commit_worker_unusable",nullable_bool(o.commit_worker_unusable)},
  {"commit_worker_valid",nullable_bool(o.commit_worker_valid)},
  {"commit_sink_failed",nullable_bool(o.commit_sink_failed)},
  {"final_stopping",nullable_bool(o.final_stopping)},
  {"final_stop_requested",nullable_bool(o.final_stop_requested)},
  {"fallback_invalid_stopping",nullable_bool(o.fallback_invalid_stopping)},
  {"fallback_invalid_worker_unusable",nullable_bool(o.fallback_invalid_worker_unusable)},
  {"fallback_source_stopping",nullable_bool(o.fallback_source_stopping)},
  {"fallback_source_worker_unusable",nullable_bool(o.fallback_source_worker_unusable)},
  {"input_version_equal",nullable_bool(o.input_version_equal)},
  {"input_odom_equal",nullable_bool(o.input_odom_equal)},
  {"input_imu_equal",nullable_bool(o.input_imu_equal)}};}
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
template<class Snapshot> Json reference_selection_json(const Snapshot &s){
  Json out={{"ref_present",bool(s.ref)},{"path_sequence",nullptr},{"profile_sequence",nullptr},
    {"path_stamp",nullptr},{"profile_stamp",nullptr},{"path_fingerprint",nullptr},
    {"profile_fingerprint",nullptr},{"path_size",nullptr},{"profile_size",nullptr}};
  if(!s.ref)return out;
  out["path_sequence"]=s.ref->path_sequence;out["profile_sequence"]=s.ref->profile_sequence;
  out["path_stamp"]={{"sec",s.ref->path_stamp.first},{"nanosec",s.ref->path_stamp.second}};
  out["profile_stamp"]={{"sec",s.ref->profile_stamp.first},{"nanosec",s.ref->profile_stamp.second}};
  if(s.ref->path_sequence)out["path_fingerprint"]=s.path_fingerprint;
  if(s.ref->profile_sequence)out["profile_fingerprint"]=s.profile_fingerprint;
  out["path_size"]=s.ref->path.size();out["profile_size"]=s.ref->profile.size();return out;
}
template<class Snapshot> Json source_json(const Snapshot &s){return {{"version",version_json(s.version)},{"odom_sequence",s.odom_seq},{"odom_stamp_ns",s.odom_stamp},{"odom_receive_ns",s.odom_receive},{"imu_sequence",s.imu_seq},{"imu_stamp_ns",s.imu_stamp},{"imu_receive_ns",s.imu_receive},{"r_from_imu",s.mixed},{"clock_sim_ns",s.sim},{"clock_receive_ns",s.clock_receive},{"rtf",s.rtf},{"rtf_valid",s.rtf_valid},{"paused",s.paused},
  {"input_commit_ordinal",s.input_commit_ordinal},{"ref_selection",reference_selection_json(s)}};}
template<class Snapshot> Json full_snapshot_json(const Snapshot &s){
  Json out=source_json(s);std::array<double,6> state{};
  std::copy(s.state.data(),s.state.data()+6,state.begin());out["state"]=state;
  // Keep the old anchor fields and shape; add its copied identity separately.
  out["anchor"]={{"n",s.anchor.n},{"sequence",s.anchor.seq},{"publish_ns",s.anchor.time},{"known",s.anchor.known}};
  out["anchor_producer"]=s.anchor_producer;out["anchor_run_id"]=s.anchor_run;out["anchor_source"]=s.anchor_source;
  out["held_history"]=Json::array();for(const auto &e:s.history)out["held_history"].push_back({{"sim_ns",e.sim_ns},{"channel",e.channel},{"value",e.value}});
  out["history_count"]=s.history.size();out["publication_history"]=Json::array();
  for(const auto &e:s.publication_history)out["publication_history"].push_back({{"channel",e.channel},{"sequence",e.sequence},{"publish_ns",e.publish_ns},{"n",e.n},{"known",e.known}});
  out["publication_history_count"]=s.publication_history.size();return out;
}
template<class Snapshot> Json json(const Snapshot &validation,const Snapshot &final_source,int64_t copy_capture_ns,const Observation &o,bool pair,uint64_t job,uint64_t target_tick,int64_t target_sim){
  Json v=full_snapshot_json(validation),f=full_snapshot_json(final_source);
  v["sample_ns"]=validation.freeze;v["copy_capture_ns"]=copy_capture_ns;v["capture_semantics"]="mutex_copy_end";
  f["commit_ns"]=final_source.freeze;
  return {{"schema","p1-d0-observation-v2"},{"candidate_pair_available",pair},{"candidate_job_id",pair?Json(job):Json(nullptr)},{"candidate_target_tick",pair?Json(target_tick):Json(nullptr)},{"prediction_target_sim_ns",pair?Json(target_sim):Json(nullptr)},
    {"predict_invoked",o.predict_invoked},{"predict_success",o.predict_success},{"predict_status",!o.predict_invoked?"not_attempted":o.predict_success?"success":"history_or_time_failed"},
    {"predicted_state_available",o.predicted_state_available},{"predicted_state",o.predicted_state_available?Json(o.predicted_state):Json(nullptr)},
    {"full_error_available",o.full_error_available},{"full_error",o.full_error_available?Json(o.full_error):Json(nullptr)},
    {"validation_snapshot",v},{"input_change_gate_ran",o.input_change_gate_ran},{"input_change_gate_unchanged",nullable_bool(o.input_change_gate_unchanged)},{"final_snapshot",f},{"gate_reads",gate_reads_json(o)}};
}
} // namespace p1::d0
