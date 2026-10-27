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
} // namespace bias_replay
