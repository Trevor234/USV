// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <deque>
#include <optional>
#include <string>
#include <algorithm>
#include <limits>
namespace p1 {
constexpr int64_t T=200000000, DEADLINE=150000000;
using State=std::array<double,6>;using Command=std::array<double,2>;
// 五轴**不是**一个坐标系：model 是计划的目标代，schedule/epoch 是计划网格身份，
// task/config 是运行身份。把两组合并成一个 Version 会让"候选用自己覆盖
// admission_version"成为可能（3.3 的旁路）。
struct PlanIdentity {uint64_t model=1,schedule=1,epoch=0;
  bool operator==(const PlanIdentity & v)const{return model==v.model&&schedule==v.schedule&&epoch==v.epoch;}};
struct RunAxes {uint64_t task=0,config=1,schedule=1,epoch=0;
  bool operator==(const RunAxes & v)const{return task==v.task&&config==v.config&&schedule==v.schedule&&epoch==v.epoch;}};
struct Anchor {Command n{0,0};std::array<uint64_t,2> seq{0,0};std::array<int64_t,2> time{0,0};std::array<bool,2> known{false,false};};
struct Ticket {uint64_t id=0,target=0;int64_t origin=0,deadline=0,target_ns=0,ready_ns=0;
  PlanIdentity plan;RunAxes run;Anchor anchor;State prediction{};};

// P1_SOURCE_SIM_AGE_GATE_V2: receipt and physical sim-origin ages are independent.
struct SourceTime {int64_t stamp_ns=0,receive_ns=0;};
struct SourceAgeLimits {
  int64_t odom_receive_age_ns=100000000,imu_receive_age_ns=100000000;
  int64_t odom_sim_lag_ns=100000000,imu_sim_lag_ns=100000000,future_slack_ns=20000000;
};
inline std::string source_time_check(
  int64_t now,int64_t clock_sim,int64_t clock_receive,const SourceTime & source,
  int64_t receive_age,int64_t sim_lag,int64_t future_slack)
{
  if(receive_age<=0||sim_lag<=0||future_slack<0)return "limits_invalid";
  if(now<=0||source.receive_ns<=0||source.stamp_ns<0)return "time_invalid";
  if(source.receive_ns>now)return "receive_future";
  if(now-source.receive_ns>receive_age)return "receive_stale";
  if(clock_receive<=0||clock_receive>now||clock_sim<0)return "clock_anchor_invalid";
  const int64_t elapsed=now-clock_receive;
  if(clock_sim>std::numeric_limits<int64_t>::max()-elapsed)return "clock_extrapolation_overflow";
  const int64_t current_sim=clock_sim+elapsed;
  if(source.stamp_ns>current_sim){
    if(source.stamp_ns-current_sim>future_slack)return "sim_future";
  }else if(current_sim-source.stamp_ns>sim_lag)return "sim_lag";
  return "";
}
inline std::string state_source_check(
  int64_t now,int64_t clock_sim,int64_t clock_receive,
  const SourceTime & odom,const SourceTime & imu,bool mixed,const SourceAgeLimits & limits)
{
  auto reason=source_time_check(now,clock_sim,clock_receive,odom,
    limits.odom_receive_age_ns,limits.odom_sim_lag_ns,limits.future_slack_ns);
  if(!reason.empty())return "odom_"+reason;
  if(mixed){
    reason=source_time_check(now,clock_sim,clock_receive,imu,
      limits.imu_receive_age_ns,limits.imu_sim_lag_ns,limits.future_slack_ns);
    if(!reason.empty())return "imu_"+reason;
  }
  return "";
}

struct Limits {State tolerance{.25,.25,.15,.3,.2,.15};double low=-25,high=25,rho=80;int64_t hold_ns=600000000;
  bool valid()const{if(!std::isfinite(low)||!std::isfinite(high)||!std::isfinite(rho)||low>0||high<0||low>=high||rho<=0||hold_ns<=0)return false;for(double x:tolerance)if(!std::isfinite(x)||x<=0)return false;return true;}};
inline double wrap(double x){return std::atan2(std::sin(x),std::cos(x));}
inline std::string anchor_check(const Anchor & expected,const Anchor & actual) {
  for(int i=0;i<2;++i){if(!actual.known[i]||!expected.known[i])return "unknown_anchor";if(expected.seq[i]!=actual.seq[i]||expected.time[i]!=actual.time[i]||expected.n[i]!=actual.n[i])return "anchor_mismatch";}return "";
}
// Complete publisher history proves that identity changes did not change the
// input assumption. Per-channel gaps and change-then-return are never equivalent.
struct PublicationEvent {int channel=0;uint64_t sequence=0;int64_t publish_ns=0;double n=0;bool known=false;};
inline std::string publication_history_check(const Anchor & expected,const Anchor & actual,
                                             const std::deque<PublicationEvent> & history){
  for(int channel=0;channel<2;++channel){
    if(!expected.known[channel]||!actual.known[channel])return "unknown_anchor";
    if(!std::isfinite(expected.n[channel])||!std::isfinite(actual.n[channel]))return "unknown_anchor";
    if(actual.n[channel]!=expected.n[channel])return "anchor_mismatch";
    if(actual.seq[channel]<expected.seq[channel]||actual.time[channel]<expected.time[channel])return "anchor_history_incomplete";
    if(actual.seq[channel]==expected.seq[channel]){
      if(actual.time[channel]!=expected.time[channel])return "anchor_history_incomplete";
      continue;
    }
    bool found=false;uint64_t sequence=expected.seq[channel];int64_t time=expected.time[channel];
    for(const auto & e:history){
      if(e.channel!=channel||e.sequence<expected.seq[channel]||e.sequence>actual.seq[channel])continue;
      if(!e.known||!std::isfinite(e.n))return "unknown_anchor";
      if(e.n!=expected.n[channel])return "anchor_history_changed";
      if(!found){
        if(e.sequence!=sequence||e.publish_ns!=time)return "anchor_history_incomplete";
        found=true;
      }else{
        if(sequence==std::numeric_limits<uint64_t>::max()||e.sequence!=sequence+1||e.publish_ns<=time)return "anchor_history_incomplete";
        sequence=e.sequence;time=e.publish_ns;
      }
    }
    if(!found||sequence!=actual.seq[channel]||time!=actual.time[channel])return "anchor_history_incomplete";
  }
  return "";
}
inline std::string state_check(const State & predicted,const State & actual,const Limits & l,State * errors=nullptr) {
  for(int i=0;i<6;++i){double e=i==2?wrap(actual[i]-predicted[i]):actual[i]-predicted[i];if(errors)(*errors)[i]=e;if(!std::isfinite(e))return "nonfinite";if(std::abs(e)>l.tolerance[i])return "activation_state_mismatch";}return "";
}
/// 幅值/有限性只有一种判据；速率与时基无关的部分单独放到 command_check_held，
/// 因为"命令何时生效"必须由调用方按真实窗口声明。
// 受控仿真里锚点每拍都会被"刚执行的那条已声明命令"推进，因此不能要求
// 值不变；要证明的是**链条连续**：从票据锚点逐号走到当前锚点，序号严格 +1、
// 时间严格递增，且每一步都能在回执历史里找到对应的执行记录。
inline std::string receipt_chain_check(const Anchor & expected,const Anchor & actual,
                                       const std::deque<PublicationEvent> & history){
  for(int channel=0;channel<2;++channel){
    if(!expected.known[channel]||!actual.known[channel])return "unknown_anchor";
    if(!std::isfinite(expected.n[channel])||!std::isfinite(actual.n[channel]))return "unknown_anchor";
    if(actual.seq[channel]<expected.seq[channel]||actual.time[channel]<expected.time[channel])
      return "anchor_history_incomplete";
    if(actual.seq[channel]==expected.seq[channel])
      return actual.time[channel]==expected.time[channel]?"": "anchor_history_incomplete";
    std::uint64_t sequence=expected.seq[channel];int64_t time=expected.time[channel];
    bool found=false;
    for(const auto & e:history){
      if(e.channel!=channel||e.sequence<=expected.seq[channel]||e.sequence>actual.seq[channel])continue;
      if(!e.known||!std::isfinite(e.n))return "unknown_anchor";
      if(!found){if(e.sequence!=sequence+1||e.publish_ns<time)return "anchor_history_incomplete";found=true;}
      else if(e.sequence!=sequence+1||e.publish_ns<=time)return "anchor_history_incomplete";
      sequence=e.sequence;time=e.publish_ns;
    }
    if(!found||sequence!=actual.seq[channel])return "anchor_history_incomplete";
  }
  return "";
}
inline std::string command_bounds(const Command & u,const Limits & l) {
  for(int i=0;i<2;++i){if(!std::isfinite(u[i]))return "nonfinite";if(u[i]<l.low||u[i]>l.high)return "command_limit";}
  return "";
}
inline std::string command_check(const Command & u,const Anchor & a,int64_t now,const Limits & l) {
  for(int i=0;i<2;++i){if(!std::isfinite(u[i]))return "nonfinite";if(u[i]<l.low||u[i]>l.high)return "command_limit";if(!a.known[i])return "unknown_anchor";if(now<=a.time[i]||std::abs(u[i]-a.n[i])>l.rho*(now-a.time[i])/1e9+1e-9)return "command_rate";}return "";
}
// Call all methods under the regulator decision mutex. Registration, cutoff and
// activation have different linearization points; closing at equality is forbidden.
class Admission {
 public:
  // 顺序固定，且每一步只比较**同一坐标系**里的量：
  //   wrong_tick → plan_axes_do_not_match_plan → model_is_not_plan_target →
  //   run_task_config_changed → run_schedule_epoch_changed → 既有时间/迟到/重复。
  std::string register_ready(Ticket t,uint64_t current_tick,int64_t now,
                             const PlanIdentity & plan,const RunAxes & run) {
    if(t.target!=current_tick+1)return "wrong_tick";
    if(t.plan.schedule!=plan.schedule||t.plan.epoch!=plan.epoch)
      return "plan_axes_do_not_match_plan";
    if(t.plan.model!=plan.model)return "model_is_not_plan_target";
    if(t.run.task!=run.task||t.run.config!=run.config)return "run_task_config_changed";
    if(t.run.schedule!=run.schedule||t.run.epoch!=run.epoch)
      return "run_schedule_epoch_changed";
    if(t.deadline!=t.origin+DEADLINE || t.target_ns!=t.origin+T)return "time_contract";
    if(now>t.deadline)return "late";
    if(std::find(seen_.begin(),seen_.end(),t.id)!=seen_.end())return "duplicate";
    if(committed_ && committed_->target==t.target)return "cutoff_closed";
    if(ready_)return "ready_slot_full";
    t.ready_ns=now;ready_=t;seen_.push_back(t.id);if(seen_.size()>64)seen_.pop_front();return "";
  }
  bool finalize_ready(uint64_t id,int64_t completed_ns){if(!ready_||ready_->id!=id)return false;if(completed_ns>ready_->deadline){ready_.reset();return false;}ready_->ready_ns=completed_ns;return true;}
  bool cutoff(int64_t now) {
    if(!ready_ || now<=ready_->deadline)return false;
    committed_=ready_;ready_.reset();cutoff_ns_=now;return true;
  }
  std::optional<Ticket> take(uint64_t target,int64_t now) {
    cutoff(now);if(!committed_)return std::nullopt;
    if(committed_->target<target){committed_.reset();return std::nullopt;}
    if(committed_->target!=target || now<committed_->target_ns)return std::nullopt;
    auto x=committed_;committed_.reset();return x;
  }
  void invalidate(){ready_.reset();committed_.reset();}
  int64_t cutoff_ns()const{return cutoff_ns_;}
  size_t slots()const{return bool(ready_)+bool(committed_);}
 private:std::optional<Ticket> ready_,committed_;std::deque<uint64_t> seen_;int64_t cutoff_ns_=0;
};
// hold 只在**有效窗口**内成立：超过 validity_ns 后基准推力归零，
// rho 预算也用真实的零推力时长计算，而不是假装一直在保持旧值。
inline std::string command_check_held(const Command & u,const Anchor & a,int64_t apply_begin,
                                      int64_t /*now*/,const Limits & l,int64_t validity_ns) {
  for(int i=0;i<2;++i){
    if(!std::isfinite(u[i]))return "nonfinite";
    if(u[i]<l.low||u[i]>l.high)return "command_limit";
    if(!a.known[i])return "unknown_anchor";
    const int64_t since=apply_begin-a.time[i];
    const bool baseline=a.known[i] && since>=0 && since<=validity_ns;
    if(!baseline)continue;                      // 基准已失效：从零起算，无速率约束
    if(apply_begin<=a.time[i])return "command_rate";
    if(std::abs(u[i]-a.n[i])>l.rho*(apply_begin-a.time[i])/1e9+1e-9)return "command_rate";
  }
  return "";
}
inline Command fallback(const Anchor & a,int64_t now,int64_t last_accepted,const Limits & l,bool invalid) {
  Command out{};
  const int64_t hold_limit=std::min<int64_t>(l.hold_ns,T);
  const bool hold=!invalid && last_accepted>0 && now-last_accepted<=hold_limit;
  for(int i=0;i<2;++i){if(!a.known[i]){out[i]=0;continue;}if(hold){out[i]=a.n[i];continue;}double step=l.rho*std::max<int64_t>(0,now-a.time[i])/1e9;out[i]=std::copysign(std::max(0.0,std::abs(a.n[i])-step),a.n[i]);}
  return out;
}
inline uint64_t due_tick(int64_t anchor,int64_t now){return now<=anchor?0:static_cast<uint64_t>((now-anchor)/T);}
}  // namespace p1
