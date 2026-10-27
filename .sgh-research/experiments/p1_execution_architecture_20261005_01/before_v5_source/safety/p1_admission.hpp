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
namespace p1 {
constexpr int64_t T=200000000, DEADLINE=150000000;
using State=std::array<double,6>;using Command=std::array<double,2>;
struct Version {uint64_t task=0,model=1,config=1,schedule=1,epoch=0;
  bool operator==(const Version & v)const{return task==v.task&&model==v.model&&config==v.config&&schedule==v.schedule&&epoch==v.epoch;}};
struct Anchor {Command n{0,0};std::array<uint64_t,2> seq{0,0};std::array<int64_t,2> time{0,0};std::array<bool,2> known{false,false};};
struct Ticket {uint64_t id=0,target=0;int64_t origin=0,deadline=0,target_ns=0,ready_ns=0;Version version;Anchor anchor;State prediction{};};
struct Limits {State tolerance{.25,.25,.15,.3,.2,.15};double low=-25,high=25,rho=80;int64_t hold_ns=600000000;
  bool valid()const{if(!std::isfinite(low)||!std::isfinite(high)||!std::isfinite(rho)||low>0||high<0||low>=high||rho<=0||hold_ns<=0)return false;for(double x:tolerance)if(!std::isfinite(x)||x<=0)return false;return true;}};
inline double wrap(double x){return std::atan2(std::sin(x),std::cos(x));}
inline std::string anchor_check(const Anchor & expected,const Anchor & actual) {
  for(int i=0;i<2;++i){if(!actual.known[i]||!expected.known[i])return "unknown_anchor";if(expected.seq[i]!=actual.seq[i]||expected.time[i]!=actual.time[i]||expected.n[i]!=actual.n[i])return "anchor_mismatch";}return "";
}
inline std::string state_check(const State & predicted,const State & actual,const Limits & l,State * errors=nullptr) {
  for(int i=0;i<6;++i){double e=i==2?wrap(actual[i]-predicted[i]):actual[i]-predicted[i];if(errors)(*errors)[i]=e;if(!std::isfinite(e))return "nonfinite";if(std::abs(e)>l.tolerance[i])return "activation_state_mismatch";}return "";
}
inline std::string command_check(const Command & u,const Anchor & a,int64_t now,const Limits & l) {
  for(int i=0;i<2;++i){if(!std::isfinite(u[i]))return "nonfinite";if(u[i]<l.low||u[i]>l.high)return "command_limit";if(!a.known[i])return "unknown_anchor";if(now<=a.time[i]||std::abs(u[i]-a.n[i])>l.rho*(now-a.time[i])/1e9+1e-9)return "command_rate";}return "";
}
// Call all methods under the regulator decision mutex. Registration, cutoff and
// activation have different linearization points; closing at equality is forbidden.
class Admission {
 public:
  std::string register_ready(Ticket t,uint64_t current_tick,int64_t now,const Version & v) {
    if(t.target!=current_tick+1)return "wrong_tick";
    if(!(t.version==v))return "version_mismatch";
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
inline Command fallback(const Anchor & a,int64_t now,int64_t last_accepted,const Limits & l,bool invalid) {
  Command out{};
  const bool hold=!invalid && last_accepted>0 && now-last_accepted<=l.hold_ns;
  for(int i=0;i<2;++i){if(!a.known[i]){out[i]=0;continue;}if(hold){out[i]=a.n[i];continue;}double step=l.rho*std::max<int64_t>(0,now-a.time[i])/1e9;out[i]=std::copysign(std::max(0.0,std::abs(a.n[i])-step),a.n[i]);}
  return out;
}
inline uint64_t due_tick(int64_t anchor,int64_t now){return now<=anchor?0:static_cast<uint64_t>((now-anchor)/T);}
}  // namespace p1
