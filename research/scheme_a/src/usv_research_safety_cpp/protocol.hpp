// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#pragma once
#include <fstream>
#include "p1_resources.hpp"
#include "p1_full_contract.hpp"
#include <limits>
#include <sstream>
#include <iomanip>
#include <stdexcept>
#include <time.h>
#include <cerrno>
#include <unistd.h>
#include <openssl/sha.h>
#include <nlohmann/json.hpp>
#include "usv_nmpc/mpc_solver.hpp"
#include "p1_model_reference.hpp"
#include "p1_model_transaction.hpp"
#include "p1_gp_snapshot.hpp"
#include "usv_research_interfaces/msg/solve_job.hpp"
#include "usv_research_interfaces/msg/solve_candidate.hpp"
#include "usv_research_interfaces/msg/worker_capability.hpp"
#include "usv_research_interfaces/msg/execution_decision.hpp"
#include "usv_research_interfaces/msg/control_proposal.hpp"
namespace p1 {
using Json=nlohmann::json;
using Job=usv_research_interfaces::msg::SolveJob;
using Candidate=usv_research_interfaces::msg::SolveCandidate;
using Capability=usv_research_interfaces::msg::WorkerCapability;
using Decision=usv_research_interfaces::msg::ExecutionDecision;
using Proposal=usv_research_interfaces::msg::ControlProposal;
inline int64_t monotonic_ns(){timespec t{};if(clock_gettime(CLOCK_MONOTONIC,&t))throw std::runtime_error("CLOCK_MONOTONIC failed");return int64_t(t.tv_sec)*1000000000+t.tv_nsec;}
inline void sleep_until_monotonic(int64_t ns){timespec t{ns/1000000000,ns%1000000000};int rc;do{rc=clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&t,nullptr);}while(rc==EINTR);if(rc)throw std::runtime_error("absolute monotonic sleep failed");}
inline std::string read_text(const std::string & p){std::ifstream f(p);if(!f)throw std::runtime_error("read failed: "+p);return {std::istreambuf_iterator<char>(f),{}};}
inline std::string digest(const std::string & s){unsigned char d[SHA256_DIGEST_LENGTH];SHA256(reinterpret_cast<const unsigned char*>(s.data()),s.size(),d);std::ostringstream o;for(auto c:d)o<<std::hex<<std::setw(2)<<std::setfill('0')<<int(c);return o.str();}
inline std::string boot_id(){auto s=read_text("/proc/sys/kernel/random/boot_id");while(!s.empty()&&isspace(s.back()))s.pop_back();return s;}
inline Json load_contract(const std::string & file,const std::string & hash,std::string * verified_text=nullptr){
  contract_require(std::regex_match(hash,std::regex("[0-9a-f]{64}")),"SHA256 identity required");
  std::ifstream input(file,std::ios::binary);if(!input)throw std::runtime_error("contract read failed");
  std::string text(65537,'\0');input.read(text.data(),text.size());text.resize(static_cast<size_t>(input.gcount()));
  contract_require(!text.empty()&&text.size()<=65536,"bounded contract file required");
  if(digest(text)!=hash)throw std::runtime_error("contract hash mismatch");
  auto c=parse_unique_contract(text);validate_contract_fields(c);
  if(verified_text)*verified_text=std::move(text);
  return c;
}
inline usv_mpc::MpcParams solver_params(const Json & c){usv_mpc::MpcParams p;p.N=c.at("N");p.dt=c.at("dt");auto q=c.at("Q").get<std::array<double,6>>();for(int i=0;i<6;++i)p.Q_diag[i]=q[i];p.R_diag=Eigen::Vector2d(c.at("R")[0],c.at("R")[1]);p.Rd_diag=Eigen::Vector2d(c.at("Rd")[0],c.at("Rd")[1]);p.Qf_scale=c.at("Qf_scale");p.T_min=c.at("command_min_n");p.T_max=c.at("command_max_n");p.dT_max=c.at("backend_rate_n_s");
const auto & h=!c.contains("hydro") && c.at("schema")=="p1-execution-contract-v2-sim" &&
  c.at("qualification")=="controlled_sim" ? candidate_baseline().at("hydro") : c.at("hydro");
#define P1_H(x) p.hydro.x=h.at(#x).get<double>()
P1_H(mass);P1_H(Iz);P1_H(xg);P1_H(d_thruster);P1_H(Xu_dot);P1_H(Yv_dot);P1_H(Yr_dot);P1_H(Nv_dot);P1_H(Nr_dot);P1_H(Xu);P1_H(Yv);P1_H(Yr);P1_H(Nv);P1_H(Nr);P1_H(Xuu);P1_H(Yvv);P1_H(Yrr);P1_H(Nvv);P1_H(Nrr);
#undef P1_H
return p;}
inline Json job_json(const Job & j){return {{"schema",j.schema_version},{"run_id",j.run_id},{"boot_id",j.boot_id},{"contract_hash",j.contract_hash},{"nominal_hash",j.nominal_hash},{"worker_instance",j.worker_instance},{"job_id",j.job_id},{"target_tick",j.target_tick},{"task_generation",j.task_generation},{"model_generation",j.model_generation},{"config_generation",j.config_generation},{"schedule_generation",j.schedule_generation},{"clock_epoch",j.clock_epoch},{"tick_origin_ns",j.tick_origin_steady_ns},{"freeze_ns",j.freeze_steady_ns},{"deadline_ns",j.deadline_steady_ns},{"target_ns",j.target_steady_ns},{"target_sim_ns",j.target_sim_ns},{"odom_stamp_ns",j.odom_stamp_ns},{"imu_stamp_ns",j.imu_stamp_ns},{"odom_receive_ns",j.odom_receive_ns},{"imu_receive_ns",j.imu_receive_ns},{"odom_sequence",j.odom_sequence},{"imu_sequence",j.imu_sequence},{"r_from_imu",j.r_from_imu},{"N",j.horizon_steps},{"dt",j.prediction_dt},{"frozen_state",j.frozen_state},{"target_state",j.target_state},{"reference",j.reference},{"anchor_n",j.anchor_n},{"anchor_sequence",j.anchor_sequence},{"anchor_publish_ns",j.anchor_publish_ns},{"anchor_known",j.anchor_known},{"reset_warmstart",j.reset_warmstart},{"frozen_clock_sim_ns",j.frozen_clock_sim_ns},{"frozen_clock_receive_ns",j.frozen_clock_receive_ns},{"assumed_rtf",j.assumed_rtf},{"anchor_source",j.anchor_source},{"anchor_producer",j.anchor_producer},{"anchor_run_id",j.anchor_run_id},{"history_sim_ns",j.history_sim_ns},{"history_channel",j.history_channel},{"history_n",j.history_n},{"gp_snapshot_id",j.gp_snapshot_id},{"gp_snapshot_sha256",j.gp_snapshot_sha256},{"gp_generation",j.gp_generation},{"stage_residuals",j.stage_residuals},{"stage_residuals_digest",j.stage_residuals_digest},{"ppo_proposal_used",j.ppo_proposal_used},{"ppo_policy_sha256",j.ppo_policy_sha256},{"ppo_obs_seq",j.ppo_obs_seq},{"ppo_q_pi",j.ppo_q_pi},{"ppo_lambda_pi",j.ppo_lambda_pi},{"ppo_reject_reason",j.ppo_reject_reason}};}

// ---- 方案 A 执行封签：Job -> 事务身份/网格/轴的唯一映射 ----
// 这些转换集中在一处，Regulator 与 Worker 必须得到同一结果；任何一处自己
// 拼装都会让"同一 Job 在两侧身份不同"变成静默的运行时差异。
inline model_reference::Axes axes_of(const Job & j){
  model_reference::Axes a;
  a.task=j.task_generation;a.model=j.model_generation;a.config=j.config_generation;
  a.schedule=j.schedule_generation;a.epoch=j.clock_epoch;return a;
}
// grid 身份**只来自计划**：schedule_generation/clock_epoch 是计划的表起点，
// tick_period/deadline 必须与合同逐位一致。合同不携带 grid —— 让合同再拼一份
// 就会有两个"同一网格"的定义。
inline model_reference::Grid grid_of_plan(const std::string & plan_text,const Json & c){
  const Json plan=Json::parse(plan_text);
  const auto & g=plan.at("grid");
  model_reference::Grid out;
  out.schedule_generation=g.at("schedule_generation_at_table_start").get<std::uint64_t>();
  out.clock_epoch=g.at("clock_epoch_at_table_start").get<std::uint64_t>();
  out.tick_period_ns=g.at("tick_period_ns").get<std::int64_t>();
  out.deadline_ns=g.at("deadline_ns").get<std::int64_t>();
  contract_require(out.tick_period_ns==c.at("T_ns").get<std::int64_t>(),"plan grid tick differs from the contract");
  contract_require(out.deadline_ns==c.at("deadline_ns").get<std::int64_t>(),"plan grid deadline differs from the contract");
  return out;
}
inline model_txn::RegisteredModelTransaction::JobIdentity identity_of(const Job & j){
  return {j.run_id,j.boot_id,j.contract_hash,j.nominal_hash,j.worker_instance};
}
template<class A> inline bool finite_array(const A & a){for(double v:a)if(!std::isfinite(v))return false;return true;}
inline std::string valid_job(const Job & j,const std::string & run,const std::string & boot,const std::string & hash,const std::string & nominal,const std::string & worker) {
if(j.schema_version!="p1-solve-job-v1"||j.run_id!=run||j.boot_id!=boot||j.contract_hash!=hash||j.nominal_hash!=nominal||j.worker_instance!=worker)return "foreign";
if(j.tick_origin_steady_ns<0||j.tick_origin_steady_ns>std::numeric_limits<int64_t>::max()-200000000||j.freeze_steady_ns<j.tick_origin_steady_ns||j.freeze_steady_ns>monotonic_ns()||j.target_sim_ns<j.odom_stamp_ns||j.odom_receive_ns>j.freeze_steady_ns||j.imu_receive_ns>j.freeze_steady_ns)return "invalid_time_order";
if(j.horizon_steps!=20||j.prediction_dt!=.2||j.deadline_steady_ns!=j.tick_origin_steady_ns+150000000||j.target_steady_ns!=j.tick_origin_steady_ns+200000000||j.freeze_steady_ns>j.deadline_steady_ns||!j.job_id)return "shape_or_time_contract";
if(!finite_array(j.target_state)||!finite_array(j.frozen_state)||!finite_array(j.reference)||!finite_array(j.anchor_n)||!finite_array(j.stage_residuals)||!finite_array(j.ppo_q_pi)||!std::isfinite(j.ppo_lambda_pi)||j.ppo_lambda_pi<0.0)return "nonfinite";
if(j.gp_generation==0||j.gp_snapshot_id.empty()||j.gp_snapshot_sha256.size()!=64||j.stage_residuals_digest.size()!=64||j.stage_residuals[60]!=0.0||j.stage_residuals[61]!=0.0||j.stage_residuals[62]!=0.0||(!j.ppo_proposal_used&&j.ppo_lambda_pi!=0.0))return "gp_or_ppo_contract";
for(int i=0;i<2;++i)if(!j.anchor_known[i]||j.anchor_n[i]<-25||j.anchor_n[i]>25||j.anchor_publish_ns[i]<=0||j.anchor_publish_ns[i]>j.freeze_steady_ns)return "unknown_or_invalid_anchor";
if(j.history_sim_ns.size()>256||j.history_channel.size()!=j.history_sim_ns.size()||j.history_n.size()!=j.history_sim_ns.size()||!finite_array(j.history_n)||j.assumed_rtf!=1.0||j.frozen_clock_receive_ns>j.freeze_steady_ns)return "history_shape_or_time";
for(size_t i=0;i<j.history_sim_ns.size();++i)if(j.history_channel[i]>1||(i&&j.history_sim_ns[i]<j.history_sim_ns[i-1])||j.history_n[i]<-25||j.history_n[i]>25)return "invalid_history";
return "";}
}  // namespace p1
