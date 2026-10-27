// SPDX-License-Identifier: MIT
// Known actual owner API-completion history drives a nominal model, no Plant claim.
#pragma once
#include "p1_owned_identity.hpp"
#include "usv_mpc_cpp/usv_model_dynamic.hpp"
#include <optional>
namespace controlled {
struct HeldEvent {int64_t ns;int channel;double n;uint64_t sequence;};
class NominalHistory {
 public:
 explicit NominalHistory(const p1_owned::Json &hydro,const std::string &contract_sha):hydro_(hydro),contract_sha_(contract_sha) {
  p1_owned::require(p1_owned::sha256_shape(contract_sha)&&hydro.is_object()&&hydro.size()==19,"nominal_explicit_contract_hydro");
  for(const char *key:{"mass","Iz","xg","d_thruster","Xu_dot","Yv_dot","Yr_dot","Nv_dot","Nr_dot","Xu","Yv","Yr","Nv","Nr","Xuu","Yvv","Yrr","Nvv","Nrr"})
   p1_owned::require(hydro.contains(key)&&hydro[key].is_number()&&!hydro[key].is_boolean()&&std::isfinite(hydro[key].get<double>()),"nominal_hydro_field_domain");
  params_.mass=hydro["mass"];params_.Iz=hydro["Iz"];params_.xg=hydro["xg"];params_.d_thruster=hydro["d_thruster"];
  params_.Xu_dot=hydro["Xu_dot"];params_.Yv_dot=hydro["Yv_dot"];params_.Yr_dot=hydro["Yr_dot"];params_.Nv_dot=hydro["Nv_dot"];params_.Nr_dot=hydro["Nr_dot"];
  params_.Xu=hydro["Xu"];params_.Yv=hydro["Yv"];params_.Yr=hydro["Yr"];params_.Nv=hydro["Nv"];params_.Nr=hydro["Nr"];
  params_.Xuu=hydro["Xuu"];params_.Yvv=hydro["Yvv"];params_.Yrr=hydro["Yrr"];params_.Nvv=hydro["Nvv"];params_.Nrr=hydro["Nrr"];
  p1_owned::require(params_.mass>0&&params_.Iz>0&&params_.d_thruster>0,"nominal_hydro_physical_domain");
 }
 void add(int64_t ns,int channel,double n,uint64_t sequence) {
  p1_owned::require(ns>0&&(channel==0||channel==1)&&std::isfinite(n)&&std::abs(n)<=25&&sequence>0&&events_.size()<1024,"nominal_held_event_domain");
  p1_owned::require(std::none_of(events_.begin(),events_.end(),[&](const HeldEvent &e){return e.sequence==sequence&&e.channel==channel;}),"nominal_duplicate_held_event");
  events_.push_back({ns,channel,n,sequence});std::stable_sort(events_.begin(),events_.end(),[](const HeldEvent&a,const HeldEvent&b){return a.ns<b.ns;});
  if(initialized_&&ns<=cache_ns_){dirty_ns_=dirty_ns_?std::min(*dirty_ns_,ns):ns;++late_events_;}
 }
 p1_owned::Json state_at(int64_t origin,int64_t target,bool dynamic) {
  p1_owned::require(!unusable_,"nominal_cache_terminal_after_failed_query");
  p1_owned::require(origin>0&&target>=origin&&target-origin<=40000000000LL,"nominal_replay_time_domain");
  struct QueryFailureGuard {bool &fatal;bool completed=false;~QueryFailureGuard(){if(!completed)fatal=true;}} guard{unusable_};
  if(!initialized_) {
   initialized_=true;origin_ns_=origin;cache_ns_=origin;last_requested_ns_=origin;dynamic_=dynamic;state_.setZero();
   checkpoints_.push_back({origin,state_});
  }
  p1_owned::require(origin==origin_ns_&&dynamic==dynamic_&&target>=last_requested_ns_,"nominal_cached_run_origin_mode_or_time_changed");
  const auto cache_before=cache_ns_,last_requested=last_requested_ns_;const auto checkpoint_count_before=checkpoints_.size();
  const auto dirty=dirty_ns_;const auto late_events=late_events_;bool rewound=false;size_t invalidated=0;
  if(dirty&&*dirty<=cache_ns_) {
   size_t chosen=0;
   for(size_t k=0;k<checkpoints_.size();++k)if(checkpoints_[k].ns<*dirty)chosen=k;else break;
   cache_ns_=checkpoints_[chosen].ns;state_=checkpoints_[chosen].state;
   invalidated=checkpoints_.size()-chosen-1;checkpoints_.resize(chosen+1);rewound=true;++correction_count_;
  }
  const int64_t replay_start=cache_ns_;size_t steps=0,event_visits=0;
  Eigen::Vector2d held=Eigen::Vector2d::Zero();size_t next=0;
  while(next<events_.size()&&events_[next].ns<=cache_ns_){held[events_[next].channel]=events_[next].n;++next;++event_visits;}
  auto advance=[&](int64_t end){
   while(cache_ns_<end) {
    const auto ns=std::min<int64_t>(2000000,end-cache_ns_);
    p1_owned::require(steps<512,"nominal_per_sensor_integration_step_budget_512");
    if(dynamic_){usv_mpc::USVDynamicModel model(double(ns)*1e-9,4,params_);state_=model.forward(state_,held);}
    cache_ns_+=ns;++steps;
   }
  };
  while(next<events_.size()&&events_[next].ns<=target){const auto &e=events_[next];advance(e.ns);held[e.channel]=e.n;++next;++event_visits;}
  advance(target);p1_owned::require(state_.allFinite(),"nominal_nonfinite_state");
  if(checkpoints_.back().ns<target){p1_owned::require(checkpoints_.size()<2048,"nominal_checkpoint_budget");checkpoints_.push_back({target,state_});}
  else checkpoints_.back().state=state_;
  p1_owned::Json history=p1_owned::Json::array();
  for(const auto &e:events_)if(e.ns<=target){history.push_back({{"publish_end_ns",e.ns},{"channel",e.channel},{"n",e.n},{"applied_sequence",e.sequence}});++event_visits;}else break;
  p1_owned::require(event_visits<=2048,"nominal_per_sensor_event_visit_budget");
  std::array<double,6> state{};for(size_t k=0;k<6;++k)state[k]=state_[k];
  p1_owned::Json work={{"schema","p1-nominal-checkpoint-work-v1"},{"algorithm","checkpoint_cached_RK4_replay_v1"},
   {"cache_before_ns",cache_before},{"cache_after_ns",cache_ns_},{"last_requested_ns",last_requested},{"requested_delta_ns",target-last_requested},
   {"integration_start_ns",replay_start},{"integration_target_ns",target},{"integrated_ns",target-replay_start},{"rollback_ns",cache_before-replay_start},
   {"cache_rewound",rewound},{"ordinary_incremental",!rewound},{"late_event_earliest_ns",dirty?p1_owned::Json(*dirty):p1_owned::Json(nullptr)},
   {"late_channel_events_since_last_sensor",late_events},{"state_correction_count",correction_count_},{"integration_steps",steps},{"ODE_evaluations",dynamic_?16*steps:0},
   {"checkpoint_count_before",checkpoint_count_before},{"checkpoint_count_after",checkpoints_.size()},{"invalidated_checkpoint_count",invalidated},
   {"event_element_visits",event_visits},{"retained_channel_events",events_.size()},{"maximum_channel_events",1024},{"maximum_event_element_visits",2048},
   {"maximum_checkpoints",2048},{"maximum_integration_steps",512},{"maximum_full_run_2ms_steps",20000},{"maximum_run_duration_ns",40000000000LL},
   {"event_retention_policy","retain every authenticated channel event; no clipping or eviction"},{"WCET_qualified",false}};
  dirty_ns_.reset();late_events_=0;last_requested_ns_=target;
  auto result=p1_owned::Json{{"schema","p1-controlled-nominal-model-step-v1"},{"origin_ns",origin},{"target_ns",target},{"initial_state",{0.,0.,0.,0.,0.,0.}},
   {"state",state},{"integration_substep_max_ns",2000000},{"rk4_substeps",4},{"integration_steps",steps},{"held_events",history},{"work",work},
   {"contract_hydro",hydro_},{"model_contract_sha256",contract_sha_},{"diagnostic_nominal_model_connected",dynamic},{"plant_connected",false},
   {"input_time_semantics","actual successful owner per-channel DDS publish API completion; no Plant receipt inference"}};
  guard.completed=true;return result;
 }
 private:
 struct Checkpoint {int64_t ns;usv_mpc::Vector6d state;};
 std::vector<HeldEvent> events_;usv_mpc::HydroParams params_;p1_owned::Json hydro_;std::string contract_sha_;
 bool initialized_=false,dynamic_=false,unusable_=false;int64_t origin_ns_=0,cache_ns_=0,last_requested_ns_=0;
 usv_mpc::Vector6d state_=usv_mpc::Vector6d::Zero();std::vector<Checkpoint> checkpoints_;std::optional<int64_t> dirty_ns_;
 size_t late_events_=0;uint64_t correction_count_=0;
};
} // namespace controlled
