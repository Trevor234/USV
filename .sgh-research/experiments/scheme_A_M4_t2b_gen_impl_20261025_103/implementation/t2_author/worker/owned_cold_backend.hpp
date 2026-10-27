// SPDX-License-Identifier: MIT
#pragma once
#include "raw_backend_v1.hpp"
#include "w2_native_boundary.hpp"
#include <functional>
#include <chrono>
namespace owned_cold {
using Json=nlohmann::json;
inline constexpr const char *policy="current_job_free_once_then_fixed050_three_rti_v1";
class Backend {
 public:
 using Clock=std::function<int64_t()>;
 using BeforeCall=std::function<void(unsigned)>; // C++ component injection only; no ROS parameter.
 Backend(const usv_mpc::MpcParams &p,Json binding,bool enabled=true,Clock clock={},BeforeCall hook={}):p_(p),solver_(p),binding_(std::move(binding)),enabled_(enabled),clock_(std::move(clock)),hook_(std::move(hook)){
  if(!clock_)clock_=[](){return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();};
 }
 /// Attach the W2 boundary. When unset the ordinary path is unchanged, which
 /// is what the normal profile requires.
 void attach_boundary(w2_wire::Boundary *boundary,w2_gate::StopPredicate stop){
  boundary_=boundary;stop_=std::move(stop);
  if(boundary_&&clock_)boundary_->set_clock(clock_);
  if(boundary_){
    // The gate's wait window decides whether a release was valid. This guard
    // decides whether the Job may still enter C, and it runs after all
    // preparation so a stop or expiry during preparation is still caught.
    //
    // `matches` gates only the *extra* release wait and the target Boundary
    // facts. Every internal call — including a non-target Job and the restored
    // BeforeCall path — still has to obey the current Job's stop state and its
    // original 150 ms deadline. Exempting non-matching calls from those
    // constraints would let a stopped or expired run keep solving.
    solver_.set_final_guard([this](unsigned ordinal)->bool{
      // The registered target goes through the Boundary's own final check, so
      // the record is refreshed in the same step as the decision. The earlier
      // generic check would return before that update and leave a stale
      // `allowed` record behind a refused call.
      if(boundary_->armed()&&boundary_->matches(ordinal,current_job_)){
        return boundary_->permit_native_entry(stop_);
      }
      // Non-target internal calls keep the same constraints — they merely do not
      // own the Boundary's release wait or facts.
      if(stop_&&stop_())return false;
      if(clock_()>current_deadline_ns_)return false;
      return true;
    });
  }
 }
 /// Report the last boundary record for manifest/ledger purposes.
 Json w2_boundary_event()const{return boundary_?w2_boundary_json(boundary_->record()):Json();}
 int N()const{return p_.N;}double dt()const{return p_.dt;}std::string backend()const{return "acados";}
 void reset_warmstart(){reset_pending_=true;}
 void set_applied_control(const Eigen::Vector2d &a){anchor_=a;anchor_set_=true;}
 const Json &last_policy_event()const{return last_;}
 bool terminal()const{return terminal_;}
 Json debug_warm()const{return solver_.warm_state();}
 Json actual_first_bounds()const{return solver_.first_control_bounds();}
 std::pair<Eigen::Vector2d,usv_mpc::SolveInfo> solve_owned(const Json &j){
  if(terminal_)throw std::runtime_error("cold_backend_terminal");
  for(auto it=binding_.begin();it!=binding_.end();++it)bias_replay::require(j.contains(it.key())&&j.at(it.key())==it.value(),"owned native context identity mismatch");
  bias_replay::require(j.at("job_id").is_number_unsigned()||j.at("job_id").is_number_integer(),"integer Job id");auto id=j.at("job_id").get<uint64_t>();
  bias_replay::require(id>last_job_&&j.at("N")==p_.N&&j.at("dt")==p_.dt,"duplicate/reordered Job or horizon mismatch");
  bias_replay::require(j.at("target_state").size()==6&&j.at("anchor_n").size()==2&&j.at("reference").size()==126,"owned native input shape");
  for(auto key:{"target_state","anchor_n","reference"})for(const auto &v:j.at(key))bias_replay::require(v.is_number()&&std::isfinite(v.get<double>()),"finite owned native input");
  const auto actual_anchor=startup_replay::anchor_of(j);bias_replay::require(anchor_set_&&(actual_anchor-anchor_).isZero(0.),"actual Job anchor must be set before solve");
  const int64_t deadline=j.at("deadline_ns");bias_replay::require(clock_()<=deadline,"expired_before_owned_native");
  Json context;for(auto key:{"run_id","boot_id","contract_hash","config_generation","model_generation","task_generation","schedule_generation","clock_epoch"})context[key]=j.at(key);
  bool first=last_job_==0;bool eligible=first&&id==1&&startup_replay::state_of(j).isZero(0.)&&actual_anchor.isZero(0.);
  if(eligible)for(int k=0;k<=20;++k){const auto &r=j.at("reference");eligible=eligible&&std::abs(r[6*k].get<double>()-.05*.2*k)<=1e-9&&r[6*k+1]==0&&r[6*k+2]==0&&r[6*k+3]==.05&&r[6*k+4]==0&&r[6*k+5]==0;}
  bool apply=enabled_&&!consumed_&&eligible;last_job_=id;current_job_=int64_t(id);
  current_job_C_calls_=0;
  current_deadline_ns_=deadline;
  if(boundary_)boundary_->set_current_job(current_job_);anchor_set_=false;
  last_={{"schema","owned-cold-start-native-policy-v1"},{"policy",policy},{"job_id",id},{"context",context},{"candidate_applied",apply},{"eligibility",eligible},{"reason",apply?"applied":!enabled_?"disabled":!first?"not_first_native_job":"outside_registered_cold_domain"},{"backend_entries_started",0},{"backend_entries_completed",0},{"subcalls",Json::array()},{"terminal",false},{"successful",false}};
  double kernel_sum=0;unsigned ordinal=0;const auto entry=clock_();
  auto invoke=[&](bool reset,bool shift,bool fixed){
   bias_replay::require(clock_()<=deadline,"expired_before_internal_native_entry");++ordinal;
   // The original component seam. It must keep running: callers inject a hook
   // here and a silent drop is a regression, not a refactor. It runs before any
   // waiting, so a hook that throws still prevents the solve.
   if(hook_)hook_(ordinal);
   // W2: hold at this boundary if it is the registered one. The gate's wait
   // window and the Job deadline are separate authorities: `enter` returns true
   // only when the release arrived AND the Job is still inside its deadline.
   if(boundary_&&boundary_->armed()&&boundary_->matches(ordinal,id)){
     const bool permitted=boundary_->enter(ordinal,id,stop_);
     if(!permitted){
       // Snapshot AFTER the boundary has finished updating its record, so the
       // policy JSON and the Boundary cannot disagree about the call fact.
       last_["w2_boundary"]=w2_boundary_json(boundary_->record());
       last_["w2_actual_C_call_started"]=false;
       throw std::runtime_error(std::string("w2_boundary_")+
         w2_wire::disposition_name(boundary_->record().disposition));
     }
   }
   last_["backend_entries_started"]=ordinal;const auto start=clock_();
   // Tell the raw backend which ordinal this is, then let it report the actual
   // C entry from its own solve site. The marker therefore lands after all
   // preparation that can still throw, not before it.
   solver_.set_call_ordinal(ordinal);
   // The fact is committed from the call site, before the call, so an
   // exception inside the solve cannot leave the record claiming "never called".
   const unsigned calls_before=solver_.native_call_count();
   solver_.set_native_call_observer([this,ordinal,id](unsigned o){
     ++current_job_C_calls_;
     if(!boundary_||!boundary_->armed()||!boundary_->matches(o,id))return;
     boundary_->mark_native_entered(o);
     last_["w2_boundary"]=w2_boundary_json(boundary_->record());
     last_["w2_actual_C_call_started"]=true;
   });
   auto a=solver_.step(j,reset,shift);const auto end=clock_();kernel_sum+=a.info.solve_time_ms;
   if(boundary_&&boundary_->armed()&&boundary_->matches(ordinal,id)){
     // The observer already recorded the call; this only refreshes the count so
     // the snapshot is complete on the success path too.
     last_["w2_native_call_count"]=solver_.native_call_count();
     last_["w2_native_calls_this_entry"]=solver_.native_call_count()-calls_before;
     last_["w2_boundary"]=w2_boundary_json(boundary_->record());
   }
   Json r={{"ordinal",ordinal},{"start_ns",start},{"end_ns",end},{"native_returned_success",a.info.success},{"first_control",{a.control[0],a.control[1]}},{"kernel_ms",a.info.solve_time_ms},{"additional_first_equality",fixed},{"warm_shift_after",shift}};
   if(apply){r["X"]=bias_replay::matrix_data(a.info.X_pred);r["U"]=bias_replay::matrix_data(a.info.U_pred);r["augmented_X"]=bias_replay::matrix_data(a.augmented);}
   last_["subcalls"].push_back(r);last_["backend_entries_completed"]=ordinal;return a;
  };
  try{
   startup_replay::Answer result;
   const bool reset=reset_pending_||j.at("reset_warmstart").get<bool>();reset_pending_=false;
   if(apply){
    consumed_=true;last_["applied_context"]=context;auto cold=invoke(reset,false,false);
    auto u=bias_replay::matrix_data(cold.info.U_pred);u[0]=.5;u[1]=.5;solver_.set_first_control_mode(true);last_["enabled_first_bounds"]=solver_.first_control_bounds();last_["causal_seed"]=solver_.seed_feasible(j,u);
    for(int k=1;k<=3;++k)result=invoke(false,k==3,true);
    last_["warm_after_last_shift"]=solver_.warm_state();solver_.set_first_control_mode(false);last_["warm_after_withdrawal"]=solver_.warm_state();
    bias_replay::require(last_["warm_after_last_shift"]==last_["warm_after_withdrawal"],"withdrawal changed final warm cache");last_["restored_first_bounds"]=solver_.first_control_bounds();
   }else result=invoke(reset,true,false);
   last_["successful"]=true;last_["kernel_sum_ms"]=kernel_sum;last_["native_entry_elapsed_ms"]=(clock_()-entry)/1e6;last_["policy_consumed_for_run"]=consumed_;last_["final_first_control"]={result.control[0],result.control[1]};
   last_["actual_C_solve_calls_this_job"]=current_job_C_calls_;
   result.info.solve_time_ms=kernel_sum;return {result.control,result.info};
  }catch(...){
   terminal_=true;last_["terminal"]=true;last_["successful"]=false;last_["policy_consumed_for_run"]=consumed_;
   last_["actual_C_solve_calls_this_job"]=current_job_C_calls_;
   // The final guard may have refused after preparation, in which case the
   // observer never ran and step never returned. The Boundary still holds the
   // authoritative disposition, so copy it here: a refusal must be visible in
   // the policy, and `actual_native_invoked` must keep whatever the call site
   // already committed rather than being reset to false.
   if(boundary_&&boundary_->matches(boundary_->config().ordinal,id)){
     const auto &rec=boundary_->record();
     last_["w2_boundary"]=w2_boundary_json(rec);
     last_["w2_actual_C_call_started"]=rec.actual_native_invoked;
     last_["w2_native_call_count"]=solver_.native_call_count();
   }
   try{solver_.set_first_control_mode(false);last_["restored_first_bounds"]=solver_.first_control_bounds();}catch(...){}throw;}
 }
 private:
 usv_mpc::MpcParams p_;startup_replay::RawBackend solver_;Json binding_,last_;bool enabled_=true,reset_pending_=false,anchor_set_=false,consumed_=false,terminal_=false;uint64_t last_job_=0;Eigen::Vector2d anchor_=Eigen::Vector2d::Zero();Clock clock_;BeforeCall hook_;
 w2_wire::Boundary *boundary_=nullptr;w2_gate::StopPredicate stop_;int64_t current_job_=0;
 int64_t current_deadline_ns_=0;
 uint64_t current_job_C_calls_=0;
};
} // namespace owned_cold
