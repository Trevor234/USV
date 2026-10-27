// SPDX-License-Identifier: MIT
// Offline fixed-tail mechanism only. No optimizer, ROS node or runtime policy.
#pragma once
#include "common_replay.hpp"
#include <algorithm>
#include <limits>
namespace first_probe {
using Json=bias_replay::Json;
using bias_replay::require;
inline usv_mpc::Vector6d state(const Json &job){require(job.at("target_state").size()==6,"actual state shape");usv_mpc::Vector6d x;for(int i=0;i<6;++i)x[i]=job.at("target_state")[i].get<double>();require(x.allFinite(),"finite state");return x;}
inline Eigen::Vector2d anchor(const Json &job){require(job.at("anchor_n").size()==2,"actual anchor shape");Eigen::Vector2d a(job.at("anchor_n")[0].get<double>(),job.at("anchor_n")[1].get<double>());require(a.allFinite(),"finite anchor");return a;}
inline Eigen::MatrixXd reference(const Json &job){require(job.at("reference").size()==126,"actual reference shape");Eigen::MatrixXd r(6,21);for(int i=0;i<126;++i)r.data()[i]=job.at("reference")[i].get<double>();require(r.allFinite(),"finite reference");return r;}
inline Eigen::MatrixXd controls(const Json &values){require(values.size()==40,"exact fixed tail shape");Eigen::MatrixXd u(2,20);for(int i=0;i<40;++i)u.data()[i]=values[i].get<double>();require(u.allFinite(),"finite control sequence");return u;}
inline void validate(const Eigen::MatrixXd &u,const Eigen::Vector2d &a,const usv_mpc::MpcParams &p){
 require(u.rows()==2&&u.cols()==20&&u.allFinite()&&a.allFinite(),"finite exact controls");
 require(u.minCoeff()>=p.T_min&&u.maxCoeff()<=p.T_max,"input bound violated; no clamping");
 Eigen::Vector2d prior=a;for(int k=0;k<20;++k){require((u.col(k)-prior).cwiseAbs().maxCoeff()<=p.dT_max*p.dt,"initial or later rate bound violated; no clamping");prior=u.col(k);}
}
inline Json rollout(const Json &input,const Eigen::MatrixXd &u){
 const auto p=bias_replay::parameters(input.at("contract"));const auto &job=input.at("actual_job");const auto a=anchor(job);validate(u,a,p);
 usv_mpc::USVDynamicModel model(p.dt,4,p.hydro);usv_mpc::SolveInfo info;info.X_pred=Eigen::MatrixXd::Zero(6,21);info.U_pred=u;info.X_pred.col(0)=state(job);
 double largest=0;Eigen::Vector2d prior=a;
 for(int k=0;k<20;++k){info.X_pred.col(k+1)=model.forward(info.X_pred.col(k),u.col(k));require(info.X_pred.col(k+1).allFinite(),"finite nonlinear rollout");largest=std::max(largest,(u.col(k)-prior).cwiseAbs().maxCoeff());prior=u.col(k);}
 auto x=bias_replay::matrix_data(info.X_pred);return {{"X",x},{"U",bias_replay::matrix_data(u)},{"first_control_n",{u(0,0),u(1,0)}},{"first_interval_position_m",{info.X_pred(0,1),info.X_pred(1,1)}},{"first_interval_surge_m_s",info.X_pred(3,1)},{"objective",bias_replay::objective(info,reference(job),a,p)},{"largest_control_increment_n",largest},{"control_increment_limit_n",p.dT_max*p.dt},{"input_bound_violation_n",0.0},{"nonlinear_RK4_substeps",4},{"optimizer_invoked",false},{"tail_reoptimized",false},{"solver_NLP_cost_readback",false}};
}
inline Json baseline(const Json &input,const std::string &tail){
 const auto &expected=input.at("tail_sequences").at(tail);auto r=rollout(input,controls(expected.at("U")));
 double xerr=bias_replay::maximum_error(r.at("X").get<std::vector<double>>(),expected.at("expected_rollout_X"));double cerr=0;
 for(auto it=expected.at("expected_objective").begin();it!=expected.at("expected_objective").end();++it)if(it.key()!="solver_NLP_cost_readback")cerr=std::max(cerr,std::abs(it.value().get<double>()-r.at("objective").at(it.key()).get<double>()));
 require(xerr<=input.at("baseline_rollout_cost_abs_tolerance").get<double>()&&cerr<=input.at("baseline_rollout_cost_abs_tolerance").get<double>(),"sealed baseline rollout/cost does not reproduce");
 return {{"tail_id",tail},{"max_X_abs_error",xerr},{"max_cost_part_abs_error",cerr},{"expected_parent_iteration",expected.at("source_parent_iteration")},{"rollout",r}};
}
inline Json run(const Json &input){
 require(input.at("actual_job").at("job_id")==1&&input.at("tail_sequences").size()==2&&input.at("first_controls").size()==5&&input.at("ordered_cases").size()==10,"fixed preregistered scope");
 Json baselines={{"once",baseline(input,"once")},{"refined",baseline(input,"refined")}};Json cases=Json::array();
 for(const auto &c:input.at("ordered_cases")){
  const auto t=c.at("tail_id").get<std::string>();const auto k=c.at("first_control_id").get<std::string>();const auto &first=input.at("first_controls").at(k);require(first==c.at("first_control")&&first.size()==2,"fixed registered first pair");
  auto u=controls(input.at("tail_sequences").at(t).at("U"));for(int ch=0;ch<2;++ch)u(ch,0)=first[ch].get<double>();
  auto r=rollout(input,u);auto original=input.at("tail_sequences").at(t).at("U");for(int i=2;i<40;++i)require(r["U"][i]==original[i],"fixed tail changed");
  cases.push_back({{"case_id",c.at("case_id")},{"tail_id",t},{"first_control_id",k},{"baseline_case_id",c.at("baseline_case_id")},{"tail_nodes_1_to_19_exactly_unchanged",true},{"rollout",r}});
 }
 return {{"baselines",baselines},{"cases",cases},{"all_10_cases_complete",true},{"optimizer_calls",0},{"stage_qualified",false},{"execute_qualified",false},{"research_conclusion",false}};
}
} // namespace first_probe
