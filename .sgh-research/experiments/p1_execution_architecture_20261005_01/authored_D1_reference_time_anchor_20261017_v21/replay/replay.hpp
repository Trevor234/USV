// SPDX-License-Identifier: MIT
#pragma once
#include <usv_mpc_cpp/acados_backend.hpp>
#include <usv_mpc_cpp/p1_input_core.hpp>
#include <usv_mpc_cpp/usv_model_dynamic.hpp>
#include <nlohmann/json.hpp>
#include <array>
#include <cmath>
#include <fstream>
#include <stdexcept>
#include <vector>
namespace bias_replay {
using Json=nlohmann::json;
inline void require(bool b,const char *m){if(!b)throw std::runtime_error(m);}
inline Json read(const std::string &path){std::ifstream f(path);require(bool(f),"input unavailable");Json j;f>>j;return j;}
inline usv_mpc::MpcParams parameters(const Json &c){
 usv_mpc::MpcParams p;p.N=c.at("N");p.dt=c.at("dt");auto q=c.at("Q").get<std::array<double,6>>();for(int i=0;i<6;++i)p.Q_diag[i]=q[i];
 p.R_diag=Eigen::Vector2d(c.at("R")[0],c.at("R")[1]);p.Rd_diag=Eigen::Vector2d(c.at("Rd")[0],c.at("Rd")[1]);p.Qf_scale=c.at("Qf_scale");p.T_min=c.at("command_min_n");p.T_max=c.at("command_max_n");p.dT_max=c.at("backend_rate_n_s");auto h=c.at("hydro");
#define REPLAY_H(x) p.hydro.x=h.at(#x).get<double>()
 REPLAY_H(mass);REPLAY_H(Iz);REPLAY_H(xg);REPLAY_H(d_thruster);REPLAY_H(Xu_dot);REPLAY_H(Yv_dot);REPLAY_H(Yr_dot);REPLAY_H(Nv_dot);REPLAY_H(Nr_dot);REPLAY_H(Xu);REPLAY_H(Yv);REPLAY_H(Yr);REPLAY_H(Nv);REPLAY_H(Nr);REPLAY_H(Xuu);REPLAY_H(Yvv);REPLAY_H(Yrr);REPLAY_H(Nvv);REPLAY_H(Nrr);
#undef REPLAY_H
 require(p.N==20&&p.dt==.2&&p.Q_diag.allFinite()&&p.R_diag.allFinite()&&p.Rd_diag.allFinite(),"actual frozen backend shape/finite parameters");return p;
}
inline Json task_time_job(const Json &job,const Json &input){
 Json out=job;const auto epoch=input.at("epoch");const double t0=epoch.at("initial_profile_t0").get<double>()+(job.at("target_sim_ns").get<int64_t>()-epoch.at("first_target_sim_ns").get<int64_t>())/1e9;
 const auto &raw=input.at("actual_reference_input");usv_mpc::ReferenceInput ref;
 ref.path=raw.at("path").get<std::vector<std::array<double,3>>>();ref.profile=raw.at("profile").get<std::vector<std::array<double,4>>>();
 std::vector<double> times,vs,rs;for(const auto &row:ref.profile){times.push_back(row[3]);vs.push_back(row[0]);rs.push_back(row[2]);}
 require(ref.path.size()==201&&times.size()==201&&std::isfinite(t0)&&t0>=times.front()&&t0+4<=times.back(),"actual static task-time reference domain");
 Eigen::MatrixXd reference=Eigen::MatrixXd::Zero(6,21);int hint=0;
 for(int k=0;k<=20;++k){auto sample=usv_mpc::sample_path_profile_at_time(ref.path,times,vs,rs,t0+k*.2,hint);hint=sample.j;reference.col(k)<<sample.x,sample.y,sample.psi,sample.v,0.,sample.r;}
 const double yaw=job.at("target_state")[2];reference(2,0)=yaw+usv_mpc::normalize_angle(reference(2,0)-yaw);
 for(int k=1;k<=20;++k)reference(2,k)=reference(2,k-1)+usv_mpc::normalize_angle(reference(2,k)-reference(2,k-1));
 out["reference"]=std::vector<double>(reference.data(),reference.data()+126);return out;
}
inline std::vector<double> matrix_data(const Eigen::MatrixXd &a){return {a.data(),a.data()+a.size()};}
inline double maximum_error(const std::vector<double> &a,const Json &b){require(a.size()==b.size(),"expected prediction shape");double e=0;for(size_t k=0;k<a.size();++k)e=std::max(e,std::abs(a[k]-b[k].get<double>()));return e;}
inline Json objective(const usv_mpc::SolveInfo &info,const Eigen::MatrixXd &reference,const Eigen::Vector2d &previous,const usv_mpc::MpcParams &p){
 double position=0,velocity=0,heading=0,effort=0,increment=0,terminal=0;Eigen::Vector2d prior=previous;
 for(int k=0;k<p.N;++k){
  for(int i:{0,1})position+=p.dt*p.Q_diag[i]*std::pow(info.X_pred(i,k)-reference(i,k),2);
  for(int i:{3,4,5})velocity+=p.dt*p.Q_diag[i]*std::pow(info.X_pred(i,k)-reference(i,k),2);
  heading+=p.dt*2*p.Q_diag[2]*(1-std::cos(info.X_pred(2,k)-reference(2,k)));
  for(int i=0;i<2;++i){effort+=p.dt*p.R_diag[i]*std::pow(info.U_pred(i,k),2);increment+=p.dt*p.Rd_diag[i]*std::pow(info.U_pred(i,k)-prior[i],2);}prior=info.U_pred.col(k);
 }
 for(int i:{0,1,3,4,5})terminal+=p.Qf_scale*p.Q_diag[i]*std::pow(info.X_pred(i,p.N)-reference(i,p.N),2);
 terminal+=p.Qf_scale*2*p.Q_diag[2]*(1-std::cos(info.X_pred(2,p.N)-reference(2,p.N)));
 return {{"stage_position_dt_scaled",position},{"stage_velocity_dt_scaled",velocity},{"stage_heading_dt_scaled",heading},{"stage_absolute_control_dt_scaled",effort},{"stage_control_increment_dt_scaled",increment},{"terminal_state_not_dt_scaled",terminal},{"total",position+velocity+heading+effort+increment+terminal},{"solver_NLP_cost_readback",false}};
}
inline Json prefix_replay(const Json &input,bool shift_selected){
 auto p=parameters(input.at("contract"));usv_mpc::AcadosBackend solver(p);const uint64_t selected=input.at("selected_job_id");
 double max_control=0,max_x=0,max_u=0;size_t count=0;Json last;uint64_t previous_id=0;
 for(const auto &record:input.at("ordered_native_jobs")) {
  const auto &actual=record.at("job");const uint64_t id=actual.at("job_id");require(id==previous_id+1,"complete native warm prefix required");previous_id=id;
  if(id>selected)break;
  auto job=shift_selected&&id==selected?task_time_job(actual,input):actual;
  if(job.at("reset_warmstart").get<bool>())solver.reset_warmstart();
  Eigen::Vector2d anchor(job["anchor_n"][0],job["anchor_n"][1]);solver.set_applied_control(anchor);
  usv_mpc::Vector6d state;for(size_t k=0;k<6;++k)state[k]=job["target_state"][k];
  Eigen::MatrixXd reference(6,21);for(size_t k=0;k<126;++k)reference.data()[k]=job["reference"][k];
  auto answer=solver.solve(state,reference);require(answer.second.success&&answer.first.allFinite()&&answer.second.X_pred.rows()==6&&answer.second.X_pred.cols()==21&&answer.second.U_pred.rows()==2&&answer.second.U_pred.cols()==20,"actual Acados solve/prediction failed");++count;
  const Json &expected=record.at("expected");const double e_control=maximum_error({answer.first[0],answer.first[1]},expected["first_control"]),e_x=maximum_error(matrix_data(answer.second.X_pred),expected["X"]),e_u=maximum_error(matrix_data(answer.second.U_pred),expected["U"]);
  if(!shift_selected||id<selected){max_control=std::max(max_control,e_control);max_x=std::max(max_x,e_x);max_u=std::max(max_u,e_u);}
  if(id==selected)last={{"job_id",id},{"first_control",{answer.first[0],answer.first[1]}},{"expected_actual_first_control",expected["first_control"]},{"selected_absolute_control_difference_from_actual",e_control},{"X",matrix_data(answer.second.X_pred)},{"U",matrix_data(answer.second.U_pred)},{"reference",job["reference"]},{"target_state",job["target_state"]},{"anchor_n",job["anchor_n"]},{"reference_x_translation_m",job["reference"][0].get<double>()-actual["reference"][0].get<double>()},{"target_initial_state_changed",false},{"contract_parameters_changed",false},{"solve_time_ms",answer.second.solve_time_ms},{"objective_decomposition",objective(answer.second,reference,anchor,p)}};
 }
 require(!last.is_null()&&count==selected,"selected actual Job absent");
 return {{"variant",shift_selected?"selected_reference_first_target_task_time":"actual_exact_complete_warm_prefix"},{"jobs_replayed",count},{"warm_prefix_jobs",selected-1},{"warm_reset_policy","actual Job.reset_warmstart only; set_applied_control(actual anchor) for every solve"},{"maximum_absolute_baseline_first_control_error",max_control},{"maximum_absolute_baseline_X_error",max_x},{"maximum_absolute_baseline_U_error",max_u},{"baseline_error_excludes_counterfactual_selected_job",shift_selected},{"selected",last}};
}
inline double equilibrium_thrust(double speed,const usv_mpc::HydroParams &p){require(std::isfinite(speed),"finite equilibrium speed");return .5*(-p.Xu*speed-p.Xuu*std::abs(speed)*speed);}
inline Json fixed_state_case(const usv_mpc::MpcParams &p,double speed,double reference_speed,double lead){
 usv_mpc::Vector6d x=usv_mpc::Vector6d::Zero();x[3]=speed;const double eq=equilibrium_thrust(speed,p.hydro);Eigen::Vector2d held=Eigen::Vector2d::Constant(eq);
 auto rhs=usv_mpc::USVDynamicModel::continuous_ode(x,held,p.hydro);usv_mpc::USVDynamicModel physical(p.dt,4,p.hydro);auto advanced=physical.forward(x,held);
 Eigen::MatrixXd reference=Eigen::MatrixXd::Zero(6,21);for(int k=0;k<=p.N;++k){reference(0,k)=lead+reference_speed*p.dt*k;reference(3,k)=reference_speed;}
 usv_mpc::AcadosBackend solver(p);Json iterations=Json::array();usv_mpc::SolveInfo final;Eigen::Vector2d control;
 for(int k=0;k<12;++k){solver.set_applied_control(held);auto answer=solver.solve(x,reference);require(answer.second.success,"fixed-state native solve failed");control=answer.first;final=answer.second;iterations.push_back({control[0],control[1]});}
 return {{"state_speed_m_s",speed},{"reference_speed_m_s",reference_speed},{"reference_origin_lead_m",lead},{"analytic_equilibrium_per_channel_n",eq},{"analytic_body_acceleration",{rhs[3],rhs[4],rhs[5]}},{"nominal_discrete_state_after_dt",std::vector<double>(advanced.data(),advanced.data()+6)},{"fixed_state_repeated_RTI_iterations",12},{"fixed_state_policy","state/reference/actual anchor held fixed; not a simulated closed loop"},{"iteration_first_controls",iterations},{"final_first_control",{control[0],control[1]}},{"final_control_minus_equilibrium_n",{control[0]-eq,control[1]-eq}},{"predicted_first_body_acceleration_m_s2",(final.X_pred(3,1)-speed)/p.dt},{"objective_decomposition",objective(final,reference,held,p)}};
}
} // namespace bias_replay
