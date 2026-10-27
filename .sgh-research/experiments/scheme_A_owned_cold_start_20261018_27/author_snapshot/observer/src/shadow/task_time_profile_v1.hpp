// SPDX-License-Identifier: MIT
#pragma once
#include "projected_profile_time_v1.hpp"
#include <array>
#include <optional>
namespace task_time_reference {
constexpr const char *policy="first_target_task_time_profile_v1";
constexpr const char *epoch_policy="first_successful_job_submit_completion_target_sim_v1";
struct Binding {
 std::array<uint64_t,5> version{}; // task, model, config, schedule, clock epoch
 std::string run,boot,contract,nominal,path,profile;
 bool operator==(const Binding &b)const{return version==b.version&&run==b.run&&boot==b.boot&&contract==b.contract&&nominal==b.nominal&&path==b.path&&profile==b.profile;}
};
struct Anchor {Binding binding;uint64_t first_job_id=0;int64_t first_target_sim_ns=0,commit_ns=0;double initial_profile_t0=0;};
struct Proposal {
 bool valid=false,first=false;std::string reason;Binding binding;Anchor anchor;
 int64_t target_sim_ns=0;double profile_t0=0;int start_index=-1;
 reference_candidate::Result geometric;Eigen::MatrixXd reference;
};
class Epoch {
 public:
 bool active()const{return bool(anchor_);}
 bool terminal()const{return !invalid_.empty();}
 const std::string &invalid_reason()const{return invalid_;}
 const std::optional<Anchor> &anchor()const{return anchor_;}
 void invalidate(const std::string &reason){if(active()&&invalid_.empty())invalid_=reason;}
 void invalidate_if_changed(const Binding &binding){if(anchor_&&!(anchor_->binding==binding))invalidate("epoch_binding_changed");}
 Proposal propose(const Binding &binding,int64_t target_sim,const usv_mpc::Vector6d &target,const usv_mpc::ReferenceInput &input)const {
  Proposal p;p.binding=binding;p.target_sim_ns=target_sim;
  const auto fail=[&](const char *why){p.reason=why;return p;};
  if(terminal())return fail("epoch_terminal");
  if(target_sim<=0||binding.run.empty()||binding.boot.empty()||binding.contract.size()!=64||binding.nominal.size()!=64||binding.path.size()!=64||binding.profile.size()!=64)return fail("epoch_identity_domain");
  if(anchor_&&!(anchor_->binding==binding))return fail("epoch_binding_changed");
  if(anchor_&&target_sim<=last_target_sim_ns_)return fail("target_sim_not_strictly_advancing");
  // The comparison is deliberately bounded to the parent's actual static
  // straight, 201 point, 0.2 second reference domain. No tiny-interval fix to G.
  if(input.path.size()!=201||input.profile.size()!=201)return fail("static_reference_population");
  const double speed=input.profile[0][0];
  if(!(speed==.05||speed==.1||speed==.3||speed==.6))return fail("static_reference_speed_domain");
  for(size_t i=0;i<201;++i){
   if(input.path[i][0]!=speed*(.2*i)||input.path[i][1]!=0||input.path[i][2]!=0||input.profile[i][0]!=speed||input.profile[i][1]!=0||input.profile[i][2]!=0||input.profile[i][3]!=.2*i)return fail("static_reference_content_domain");
  }
  p.geometric=reference_candidate::build(target,input,20,.2);
  if(!p.geometric.valid){p.reason="reference_input:"+p.geometric.reason;return p;}
  p.first=!anchor_;
  if(anchor_)p.anchor=*anchor_;
  else {p.anchor.binding=binding;p.anchor.first_target_sim_ns=target_sim;p.anchor.initial_profile_t0=p.geometric.profile_t0;}
  p.profile_t0=p.anchor.initial_profile_t0+double(target_sim-p.anchor.first_target_sim_ns)/1e9;
  if(!std::isfinite(p.profile_t0)||p.profile_t0<input.profile.front()[3]||p.profile_t0+4>input.profile.back()[3])return fail("task_time_horizon_exceeds_profile");
  if(p.first){p.reference=p.geometric.reference;p.start_index=p.geometric.segment;}
  else {
   std::vector<double> times,vs,rs;for(const auto &r:input.profile){times.push_back(r[3]);vs.push_back(r[0]);rs.push_back(r[2]);}
   p.reference=Eigen::MatrixXd::Zero(6,21);int hint=0;
   for(int k=0;k<=20;++k){auto sample=usv_mpc::sample_path_profile_at_time(input.path,times,vs,rs,p.profile_t0+k*.2,hint);hint=sample.j;if(!k)p.start_index=hint;p.reference.col(k)<<sample.x,sample.y,sample.psi,sample.v,0.,sample.r;}
   p.reference(2,0)=target[2]+usv_mpc::normalize_angle(p.reference(2,0)-target[2]);
   for(int k=1;k<=20;++k)p.reference(2,k)=p.reference(2,k-1)+usv_mpc::normalize_angle(p.reference(2,k)-p.reference(2,k-1));
  }
  if(!p.reference.allFinite())return fail("task_time_reference_nonfinite");
  p.valid=true;return p;
 }
 // The caller holds the same invalidation mutex as the final Job submit
 // completion. A proposal, adapter import, or failed guard cannot bind epoch.
 bool commit(const Proposal &p,uint64_t job_id,int64_t submit_commit_ns){
  if(!p.valid||terminal()||!job_id||submit_commit_ns<=0||p.first==active())return false;
  if(anchor_){if(!(p.binding==anchor_->binding)||p.anchor.first_job_id!=anchor_->first_job_id||p.anchor.first_target_sim_ns!=anchor_->first_target_sim_ns||p.anchor.initial_profile_t0!=anchor_->initial_profile_t0||p.target_sim_ns<=last_target_sim_ns_||job_id<=last_job_id_)return false;}
  else {anchor_=p.anchor;anchor_->first_job_id=job_id;anchor_->commit_ns=submit_commit_ns;}
  last_target_sim_ns_=p.target_sim_ns;last_job_id_=job_id;return true;
 }
 private:
 std::optional<Anchor> anchor_;std::string invalid_;int64_t last_target_sim_ns_=0;uint64_t last_job_id_=0;
};
} // namespace task_time_reference
