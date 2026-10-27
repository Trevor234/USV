// SPDX-License-Identifier: MIT
// Known actual owner API-completion history drives a nominal model, no Plant claim.
#pragma once
#include "p1_owned_identity.hpp"
#include "usv_mpc_cpp/usv_model_dynamic.hpp"
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
 }
 p1_owned::Json state_at(int64_t origin,int64_t target,bool dynamic) const {
  p1_owned::require(origin>0&&target>=origin&&target-origin<=40000000000LL,"nominal_replay_time_domain");
  usv_mpc::Vector6d x=usv_mpc::Vector6d::Zero();Eigen::Vector2d u=Eigen::Vector2d::Zero();int64_t cursor=origin;size_t steps=0;
  p1_owned::Json history=p1_owned::Json::array();
  auto integrate=[&](int64_t end){while(cursor<end){auto ns=std::min<int64_t>(2000000,end-cursor);if(dynamic){usv_mpc::USVDynamicModel model(double(ns)*1e-9,4,params_);x=model.forward(x,u);}cursor+=ns;++steps;p1_owned::require(steps<=20000,"nominal_step_budget");}};
  for(const auto &event:events_) {
   if(event.ns>target)break;
   if(event.ns>origin)integrate(event.ns);
   u[event.channel]=event.n;
   history.push_back({{"publish_end_ns",event.ns},{"channel",event.channel},{"n",event.n},{"applied_sequence",event.sequence}});
  }
  integrate(target);p1_owned::require(x.allFinite(),"nominal_nonfinite_state");
  std::array<double,6> state{};for(size_t k=0;k<6;++k)state[k]=x[k];
  return {{"schema","p1-controlled-nominal-model-step-v1"},{"origin_ns",origin},{"target_ns",target},{"initial_state",{0.,0.,0.,0.,0.,0.}},
   {"state",state},{"integration_substep_max_ns",2000000},{"rk4_substeps",4},{"integration_steps",steps},{"held_events",history},
   {"contract_hydro",hydro_},{"model_contract_sha256",contract_sha_},{"diagnostic_nominal_model_connected",dynamic},{"plant_connected",false},{"input_time_semantics","actual successful owner per-channel DDS publish API completion; no Plant receipt inference"}};
 }
 private:std::vector<HeldEvent> events_;usv_mpc::HydroParams params_;p1_owned::Json hydro_;std::string contract_sha_;
};
} // namespace controlled
