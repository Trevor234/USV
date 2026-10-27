// SPDX-License-Identifier: MIT
// Offline C API transcription from the frozen readable backend. The complete
// actual Worker replay and public-vs-raw checks must pass before interpretation.
#pragma once
#include "common_replay.hpp"
#include <usv_mpc_cpp/utils.hpp>
#include <acados_c/ocp_nlp_interface.h>
#include <chrono>
#include <cstdio>
#include <functional>
#include <vector>

namespace startup_replay {
using Json=bias_replay::Json;
using Clock=std::chrono::steady_clock;
struct Answer {Eigen::Vector2d control;usv_mpc::SolveInfo info;Eigen::MatrixXd augmented;double wall_ms=0;};
inline usv_mpc::Vector6d state_of(const Json &job){usv_mpc::Vector6d x;for(int i=0;i<6;++i)x[i]=job.at("target_state")[i];return x;}
inline Eigen::Vector2d anchor_of(const Json &job){return Eigen::Vector2d(job.at("anchor_n")[0].get<double>(),job.at("anchor_n")[1].get<double>());}
inline Eigen::MatrixXd reference_of(const Json &job){bias_replay::require(job.at("reference").size()==126,"fixed actual reference shape");Eigen::MatrixXd r(6,21);for(int i=0;i<126;++i)r.data()[i]=job["reference"][i];return r;}
inline Answer public_step(usv_mpc::AcadosBackend &solver,const Json &job,bool reset){
 const auto start=Clock::now();if(reset)solver.reset_warmstart();solver.set_applied_control(anchor_of(job));auto r=solver.solve(state_of(job),reference_of(job));
 bias_replay::require(r.second.success&&r.first.allFinite(),"actual public backend solve failed");return {r.first,r.second,{},std::chrono::duration<double,std::milli>(Clock::now()-start).count()};
}
class RawBackend {
 public:
 explicit RawBackend(const usv_mpc::MpcParams &p,bool fixed_first=false):p_(p),fixed_first_(fixed_first){
  bias_replay::require(!fixed_first_||(.5>=p.T_min&&.5<=p.T_max),"fixed first inside original box");
  c_=usv_dyn_nmpc_acados_create_capsule();bias_replay::require(c_!=nullptr,"capsule allocation");
  bias_replay::require(usv_dyn_nmpc_acados_create(c_)==0,"capsule create");cfg_=usv_dyn_nmpc_acados_get_nlp_config(c_);dim_=usv_dyn_nmpc_acados_get_nlp_dims(c_);in_=usv_dyn_nmpc_acados_get_nlp_in(c_);out_=usv_dyn_nmpc_acados_get_nlp_out(c_);
  bias_replay::require(dim_->N==p.N&&in_->Ts&&std::abs(in_->Ts[0]-p.dt)<1e-9,"same baked horizon and dt");
  const auto &h=p.hydro;double pg[30]={h.mass,h.Iz,h.xg,h.d_thruster,h.Xu_dot,h.Yv_dot,h.Yr_dot,h.Nv_dot,h.Nr_dot,h.Xu,h.Yv,h.Yr,h.Nv,h.Nr,h.Xuu,h.Yvv,h.Yrr,h.Nvv,h.Nrr,p.Q_diag[0],p.Q_diag[1],p.Q_diag[2],p.Q_diag[3],p.Q_diag[4],p.Q_diag[5],p.R_diag[0],p.R_diag[1],p.Rd_diag[0],p.Rd_diag[1],p.Qf_scale};
  usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies(c_,pg,30);xw_=Eigen::MatrixXd::Zero(8,p.N+1);uw_=Eigen::MatrixXd::Zero(2,p.N);
 }
 ~RawBackend(){if(c_){usv_dyn_nmpc_acados_free(c_);usv_dyn_nmpc_acados_free_capsule(c_);}}
 RawBackend(const RawBackend&)=delete;RawBackend &operator=(const RawBackend&)=delete;
 void set_first_control_mode(bool fixed){
  bias_replay::require(!fixed||(.5>=p_.T_min&&.5<=p_.T_max),"added equality inside original box");fixed_first_=fixed;
  double lo[2]={fixed?.5:p_.T_min,fixed?.5:p_.T_min},hi[2]={fixed?.5:p_.T_max,fixed?.5:p_.T_max};
  ocp_nlp_constraints_model_set(cfg_,dim_,in_,out_,0,"lbu",lo);ocp_nlp_constraints_model_set(cfg_,dim_,in_,out_,0,"ubu",hi);
 }
 Json first_control_bounds() const {
  double lo[2],hi[2];ocp_nlp_constraints_model_get(cfg_,dim_,in_,0,"lbu",lo);ocp_nlp_constraints_model_get(cfg_,dim_,in_,0,"ubu",hi);
  return {{"lbu",{lo[0],lo[1]}},{"ubu",{hi[0],hi[1]}},{"additional_first_equality",fixed_first_},{"read_from_actual_C_API",true}};
 }
 Json warm_state() const {return {{"warm",warm_},{"X_aug",bias_replay::matrix_data(xw_)},{"U",bias_replay::matrix_data(uw_)}};}
 /// Observe the actual C entry. Called immediately before
 /// usv_dyn_nmpc_acados_solve, i.e. after all preparation that can still throw,
 /// so "wrapper entered" and "C function entered" remain distinct facts.
 using NativeCallObserver=std::function<void(unsigned)>;
 void begin_native_call(unsigned ordinal){if(native_observer_)native_observer_(ordinal);}
 /// Final guard: runs after every preparation step that can throw and
 /// immediately before the actual C solve. Returning false refuses the call.
 using FinalGuard=std::function<bool(unsigned)>;
 void set_final_guard(FinalGuard fn){final_guard_=std::move(fn);}
 void set_native_call_observer(NativeCallObserver fn){native_observer_=std::move(fn);}
 unsigned native_call_count() const {return unsigned(native_calls_.size());}
 void note_native_call(unsigned ordinal){native_calls_.push_back(ordinal);if(native_observer_)native_observer_(ordinal);}
 const std::vector<unsigned> &native_ordinals() const {return native_calls_;}
 Json seed_feasible(const Json &job,const std::vector<double> &values){
  bias_replay::require(values.size()==40,"complete seed controls");Eigen::MatrixXd seed_u(2,20);for(int i=0;i<40;++i)seed_u.data()[i]=values[i];
  bias_replay::require(seed_u.allFinite()&&seed_u.minCoeff()>=p_.T_min&&seed_u.maxCoeff()<=p_.T_max,"finite seed inside original input box");
  auto prior=anchor_of(job);for(int k=0;k<20;++k){bias_replay::require((seed_u.col(k)-prior).cwiseAbs().maxCoeff()<=p_.dT_max*p_.dt,"seed original rate bound");prior=seed_u.col(k);}
  if(fixed_first_)bias_replay::require(seed_u(0,0)==.5&&seed_u(1,0)==.5,"seed obeys added first equality");
  usv_mpc::USVDynamicModel model(p_.dt,4,p_.hydro);xw_.setZero();xw_.block<6,1>(0,0)=state_of(job);xw_.block<2,1>(6,0)=anchor_of(job);
  for(int k=0;k<20;++k){xw_.block<6,1>(0,k+1)=model.forward(xw_.block<6,1>(0,k),seed_u.col(k));xw_.block<2,1>(6,k+1)=seed_u.col(k);}
  bias_replay::require(xw_.allFinite(),"finite feasible augmented seed");uw_=seed_u;bias_replay::require(usv_dyn_nmpc_acados_reset(c_,1)==0,"QP reset before prescribed seed");warm_=true;
  return {{"X_aug",bias_replay::matrix_data(xw_)},{"U",bias_replay::matrix_data(uw_)},{"initial_state_exact",true},{"original_RK4_substeps",4},{"previous_control_memory_from_anchor_and_U",true},{"QP_reset_before_primal_seed",true},{"tail_nodes_1_to_19_from_refined",true}};
 }
 Answer step(const Json &job,bool reset,bool shift_after){
  const auto start=Clock::now();if(reset){warm_=false;xw_.setZero();uw_.setZero();usv_dyn_nmpc_acados_reset(c_,1);}
  const auto state=state_of(job);const auto anchor=anchor_of(job);const auto reference=reference_of(job);
  // This is exactly what the actual set_applied_control performs before solve.
  if(warm_)xw_.block<2,1>(6,0)=anchor;
  Eigen::Matrix<double,8,1> x0;x0<<state,anchor;
  if(warm_){const double shift=std::round((state[2]-xw_(2,0))/(2*M_PI))*2*M_PI;if(std::abs(shift)>1e-3)xw_.row(2).array()+=shift;}
  ocp_nlp_constraints_model_set(cfg_,dim_,in_,out_,0,"lbx",x0.data());ocp_nlp_constraints_model_set(cfg_,dim_,in_,out_,0,"ubx",x0.data());
  double lo[2]={p_.T_min,p_.T_min},hi[2]={p_.T_max,p_.T_max},lh[2]={-p_.dT_max*p_.dt,-p_.dT_max*p_.dt},uh[2]={p_.dT_max*p_.dt,p_.dT_max*p_.dt};
  double fixed[2]={.5,.5};if(fixed_first_)bias_replay::require((Eigen::Vector2d(.5,.5)-anchor).cwiseAbs().maxCoeff()<=p_.dT_max*p_.dt,"added equality respects original first rate");
  for(int k=0;k<p_.N;++k){double *lower=k==0&&fixed_first_?fixed:lo;double *upper=k==0&&fixed_first_?fixed:hi;ocp_nlp_constraints_model_set(cfg_,dim_,in_,out_,k,"lbu",lower);ocp_nlp_constraints_model_set(cfg_,dim_,in_,out_,k,"ubu",upper);ocp_nlp_constraints_model_set(cfg_,dim_,in_,out_,k,"lh",lh);ocp_nlp_constraints_model_set(cfg_,dim_,in_,out_,k,"uh",uh);}
  double previous_yaw=state[2];for(int k=0;k<=p_.N;++k){double ref[6];for(int i=0;i<6;++i)ref[i]=reference(i,k);ref[2]=previous_yaw+usv_mpc::normalize_angle(ref[2]-previous_yaw);previous_yaw=ref[2];usv_dyn_nmpc_acados_update_params(c_,k,ref,6);}
  if(warm_){for(int k=0;k<=p_.N;++k)ocp_nlp_out_set(cfg_,dim_,out_,in_,k,"x",xw_.col(k).data());for(int k=0;k<p_.N;++k)ocp_nlp_out_set(cfg_,dim_,out_,in_,k,"u",uw_.col(k).data());}
  else {Eigen::Matrix<double,8,1> guess;guess<<state,Eigen::Vector2d::Zero();Eigen::Vector2d zero=Eigen::Vector2d::Zero();for(int k=0;k<=p_.N;++k)ocp_nlp_out_set(cfg_,dim_,out_,in_,k,"x",guess.data());for(int k=0;k<p_.N;++k)ocp_nlp_out_set(cfg_,dim_,out_,in_,k,"u",zero.data());}
  Answer answer;const auto solve_start=Clock::now();
  // Everything above (constraints, references, warm start) has completed. This
  // is the last point at which a stop or an expired Job deadline can still keep
  // the C solve from starting; a guard placed earlier would miss a stop that
  // arrived during preparation.
  if(final_guard_&&!final_guard_(ordinal_))bias_replay::require(false,"blocked_at_final_guard");
  // The genuine entry point. Nothing below has run yet, so this is the first
  // instant at which the C solve is really entered.
  note_native_call(ordinal_);
  const int status=usv_dyn_nmpc_acados_solve(c_);answer.info.solve_time_ms=std::chrono::duration<double,std::milli>(Clock::now()-solve_start).count();bias_replay::require(status==0,"raw actual codegen solve failed");
  answer.augmented=Eigen::MatrixXd::Zero(8,p_.N+1);answer.info.U_pred=Eigen::MatrixXd::Zero(2,p_.N);
  for(int k=0;k<=p_.N;++k){double x[8];ocp_nlp_out_get(cfg_,dim_,out_,k,"x",x);answer.augmented.col(k)=Eigen::Map<Eigen::Matrix<double,8,1>>(x);}
  for(int k=0;k<p_.N;++k){double u[2];ocp_nlp_out_get(cfg_,dim_,out_,k,"u",u);answer.info.U_pred.col(k)=Eigen::Map<Eigen::Vector2d>(u);}
  answer.info.X_pred=answer.augmented.topRows(6);answer.control=answer.info.U_pred.col(0);answer.info.success=true;snprintf(answer.info.backend,sizeof(answer.info.backend),"acados");
  bias_replay::require(answer.augmented.allFinite()&&answer.info.U_pred.allFinite(),"raw finite output");
  if(shift_after){xw_.leftCols(p_.N)=answer.augmented.rightCols(p_.N);xw_.col(p_.N)=answer.augmented.col(p_.N);uw_.leftCols(p_.N-1)=answer.info.U_pred.rightCols(p_.N-1);uw_.col(p_.N-1)=answer.info.U_pred.col(p_.N-1);}
  else {xw_=answer.augmented;uw_=answer.info.U_pred;}
  warm_=true;answer.wall_ms=std::chrono::duration<double,std::milli>(Clock::now()-start).count();return answer;
 }
 void set_call_ordinal(unsigned o){ordinal_=o;}
 private:
 unsigned ordinal_=0;std::vector<unsigned> native_calls_;NativeCallObserver native_observer_;FinalGuard final_guard_;
 usv_mpc::MpcParams p_;usv_dyn_nmpc_solver_capsule *c_=nullptr;ocp_nlp_config *cfg_=nullptr;ocp_nlp_dims *dim_=nullptr;ocp_nlp_in *in_=nullptr;ocp_nlp_out *out_=nullptr;bool warm_=false;bool fixed_first_=false;Eigen::MatrixXd xw_,uw_;
};
inline double control_error(const Answer &a,const Json &expected){return bias_replay::maximum_error({a.control[0],a.control[1]},expected);}
inline Json answer_json(const Answer &a,const Json &job,const usv_mpc::MpcParams &p){
 const auto reference=reference_of(job);const auto anchor=anchor_of(job);const auto state=state_of(job);usv_mpc::USVDynamicModel model(p.dt,4,p.hydro);usv_mpc::SolveInfo rollout;rollout.X_pred=Eigen::MatrixXd::Zero(6,p.N+1);rollout.U_pred=a.info.U_pred;rollout.X_pred.col(0)=state;
 double defect=0,initial=(a.info.X_pred.col(0)-state).cwiseAbs().maxCoeff(),rate=0,bound=0;
 for(int k=0;k<p.N;++k){rollout.X_pred.col(k+1)=model.forward(rollout.X_pred.col(k),a.info.U_pred.col(k));auto next=model.forward(a.info.X_pred.col(k),a.info.U_pred.col(k));defect=std::max(defect,(next-a.info.X_pred.col(k+1)).cwiseAbs().maxCoeff());Eigen::Vector2d previous=k?Eigen::Vector2d(a.info.U_pred.col(k-1)):anchor;rate=std::max(rate,(a.info.U_pred.col(k)-previous).cwiseAbs().maxCoeff());for(int ch=0;ch<2;++ch)bound=std::max(bound,std::max(p.T_min-a.info.U_pred(ch,k),a.info.U_pred(ch,k)-p.T_max));}
 return {{"first_control",{a.control[0],a.control[1]}},{"X",bias_replay::matrix_data(a.info.X_pred)},{"U",bias_replay::matrix_data(a.info.U_pred)},{"kernel_solve_ms",a.info.solve_time_ms},{"wall_ms",a.wall_ms},{"objective_self_computed",bias_replay::objective(a.info,reference,anchor,p)},{"feasible_rollout_objective_self_computed",bias_replay::objective(rollout,reference,anchor,p)},{"nonlinear_RK4_state_defect_max_abs",defect},{"initial_state_max_abs_error",initial},{"largest_control_increment_n",rate},{"increment_limit_n",p.dT_max*p.dt},{"input_bound_violation_n",std::max(0.,bound)},{"feasible_rollout_X",bias_replay::matrix_data(rollout.X_pred)},{"actual_OCP_input_changed",false},{"solver_NLP_cost_readback",false},{"KKT_convergence_proven",false}};
}
inline Json actual_baseline(const Json &input){
 auto p=bias_replay::parameters(input.at("contract"));usv_mpc::AcadosBackend pub(p);RawBackend raw(p);double ec=0,ex=0,eu=0,rc=0,rx=0,ru=0,pc=0,px=0,pu=0;uint64_t count=0;
 for(const auto &r:input.at("ordered_native_jobs")){const auto &j=r.at("job");bias_replay::require(j.at("job_id").get<uint64_t>()==++count,"complete actual native order");bool reset=j.at("reset_warmstart");auto a=public_step(pub,j,reset),b=raw.step(j,reset,true);auto expected=r.at("expected");ec=std::max(ec,control_error(a,expected["first_control"]));ex=std::max(ex,bias_replay::maximum_error(bias_replay::matrix_data(a.info.X_pred),expected["X"]));eu=std::max(eu,bias_replay::maximum_error(bias_replay::matrix_data(a.info.U_pred),expected["U"]));rc=std::max(rc,control_error(b,expected["first_control"]));rx=std::max(rx,bias_replay::maximum_error(bias_replay::matrix_data(b.info.X_pred),expected["X"]));ru=std::max(ru,bias_replay::maximum_error(bias_replay::matrix_data(b.info.U_pred),expected["U"]));pc=std::max(pc,(a.control-b.control).cwiseAbs().maxCoeff());px=std::max(px,(a.info.X_pred-b.info.X_pred).cwiseAbs().maxCoeff());pu=std::max(pu,(a.info.U_pred-b.info.U_pred).cwiseAbs().maxCoeff());}
 return {{"jobs",count},{"public_vs_actual",{{"control",ec},{"X",ex},{"U",eu}}},{"raw_shift_vs_actual",{{"control",rc},{"X",rx},{"U",ru}}},{"public_vs_raw_shift",{{"control",pc},{"X",px},{"U",pu}}}};
}
inline Json repeated_selected(const Json &input,uint64_t selected){
 auto p=bias_replay::parameters(input.at("contract"));usv_mpc::AcadosBackend pub(p);RawBackend shifted(p),unshifted(p);Json iterations=Json::array(),selected_job;double ec=0,ex=0,eu=0;
 for(const auto &r:input.at("ordered_native_jobs")){const auto &j=r.at("job");uint64_t id=j.at("job_id");if(id>selected)break;if(id<selected){public_step(pub,j,j.at("reset_warmstart"));shifted.step(j,j.at("reset_warmstart"),true);unshifted.step(j,j.at("reset_warmstart"),true);continue;}selected_job=j;int count=input.at("repeat_count");bias_replay::require(count==12,"predeclared finite repeat count");
  for(int k=0;k<count;++k){bool reset=k==0&&j.at("reset_warmstart").get<bool>();auto a=public_step(pub,j,reset),b=shifted.step(j,reset,true),c=unshifted.step(j,reset,false);ec=std::max(ec,(a.control-b.control).cwiseAbs().maxCoeff());ex=std::max(ex,(a.info.X_pred-b.info.X_pred).cwiseAbs().maxCoeff());eu=std::max(eu,(a.info.U_pred-b.info.U_pred).cwiseAbs().maxCoeff());iterations.push_back({{"iteration",k+1},{"public_shift",answer_json(a,j,p)},{"raw_shift",answer_json(b,j,p)},{"raw_unshifted",answer_json(c,j,p)}});}
 }
 bias_replay::require(!selected_job.is_null(),"selected actual Job exists");return {{"job_id",selected},{"warm_prefix_jobs",selected-1},{"fixed_Job",selected_job},{"iterations",iterations},{"public_vs_raw_shift_max",{{"control",ec},{"X",ex},{"U",eu}}},{"same_state_anchor_reference_params_every_repeat",true},{"repeated_closed_loop_claimed",false}};
}
} // namespace startup_replay
