// Finite command observation component. It has no actuator or ROS publisher.
#pragma once
#include "p1_admission_N10.hpp"
#include <mutex>
#include <stdexcept>
#include <string_view>

namespace c36 {
enum class Life {preparing, open, faulted, closing, closed};
enum class Call {unattempted, started, succeeded, failed};
struct Owner {
  std::string run, boot, producer, config;
  uint64_t epoch=0;
  bool operator==(const Owner& o) const {
    return run==o.run && boot==o.boot && producer==o.producer && config==o.config && epoch==o.epoch;
  }
};
inline bool ascii_id(std::string_view s, size_t max) {
  if(s.empty() || s.size()>max) return false;
  for(unsigned char c:s) if(c<33 || c>126) return false;
  return true;
}
inline bool valid_owner(const Owner& o) {
  if(!ascii_id(o.run,128)||!ascii_id(o.boot,64)||!ascii_id(o.producer,64)||o.config.size()!=64) return false;
  for(char c:o.config) if(!((c>='0'&&c<='9')||(c>='a'&&c<='f'))) return false;
  return true;
}
struct PairFeedback {
  Owner owner;
  uint64_t sequence=0;
  p1::Command n{};
  std::array<Call,2> calls{Call::unattempted,Call::unattempted};
  std::array<int64_t,2> start{}, end{};
  int64_t receipt=0;
};
struct FrozenJob {
  Owner owner;
  p1::Ticket ticket;
  int64_t freeze=0;
};
struct Result {std::string reason; explicit operator bool() const {return reason.empty();}};
struct Facts {
  Life life;
  p1::Anchor anchor;
  bool whole_pair_observed;
  bool active_transaction;
  // All facts are local command observations. Plant feedback is unavailable.
  bool plant_acceptance_observed=false;
};

// Future adapters must authenticate the owner/endpoint and provide actual local
// call receipts. Identity matching here is not a live DDS ownership proof.
// All public operations serialize at the component mutex. A future controller
// must also coordinate other state/clock/admission guards at its decision lock.
class CommandAnchor {
 public:
  explicit CommandAnchor(Owner owner, p1::Limits limits={}) : owner_(std::move(owner)), limits_(limits) {
    if(!valid_owner(owner_) || !limits_.valid() || limits_.low!=-25 || limits_.high!=25 || limits_.rho!=80)
      throw std::invalid_argument("owner_or_limits");
    version_.epoch=owner_.epoch;
  }
  Facts facts() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return {life_,anchor_,whole_,active_.has_value(),false};
  }
  Result observe(const PairFeedback& f) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(life_!=Life::preparing && life_!=Life::open) return {"owner_not_open"};
    if(!(f.owner==owner_)) return {"foreign_owner"};
    if(active_) return fault("unexpected_feedback_during_transaction");
    if(auto r=feedback_shape(f);!r.empty()) return fault(r);
    if(f.sequence<=last_pair_sequence_) return {"replayed_feedback"};
    if(last_pair_sequence_ && (last_pair_sequence_==UINT64_MAX || f.sequence!=last_pair_sequence_+1)) return fault("feedback_gap");
    if(f.receipt<last_time_) return fault("feedback_time_reversal");
    for(int ch=0;ch<2;++ch) {
      if(f.calls[ch]!=Call::unattempted && f.start[ch]<=anchor_.time[ch]) return fault("publish_time_reversal");
    }
    last_pair_sequence_=f.sequence; last_time_=f.receipt;
    for(int ch=0;ch<2;++ch) apply_call(ch,f.calls[ch],f.n[ch],f.sequence,f.start[ch]);
    whole_=f.calls[0]==Call::succeeded && f.calls[1]==Call::succeeded;
    if(!whole_) {life_=Life::faulted; pending_.reset(); return {"incomplete_pair"};}
    return {};
  }
  Result open(int64_t now) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(life_!=Life::preparing || !whole_ || !anchor_.known[0] || !anchor_.known[1]) return {"not_prepared"};
    if(!time_ok(now)) return {"time_order"};
    life_=Life::open;last_time_=now;return {};
  }
  Result freeze(uint64_t id,uint64_t target,int64_t origin,int64_t now,FrozenJob& out) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(life_!=Life::open) return {"owner_not_open"};
    if(pending_ || active_) return {"slot_busy"};
    if(!id || id<=last_job_id_ || !target) return {"old_job_or_tick"};
    if(origin<=0 || origin>INT64_MAX-p1::T || now<origin || now>origin+p1::DEADLINE || !time_ok(now)) return {"freeze_time"};
    if(!anchor_.known[0] || !anchor_.known[1]) return {"unknown_anchor"};
    if(target<=last_target_) return {"old_job_or_tick"};
    FrozenJob j;j.owner=owner_;j.freeze=now;j.ticket.id=id;j.ticket.target=target;
    j.ticket.origin=origin;j.ticket.deadline=origin+p1::DEADLINE;j.ticket.target_ns=origin+p1::T;
    j.ticket.version=version_;j.ticket.anchor=anchor_;
    pending_=Pending{j,{},false,false};last_job_id_=id;last_target_=target;last_time_=now;out=j;return {};
  }
  Result ready(const FrozenJob& echo,const p1::Command& command,int64_t now) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(life_!=Life::open) return {"owner_not_open"};
    if(!pending_ || !same_job(echo,pending_->job)) return {"frozen_job_mismatch"};
    if(pending_->ready || pending_->cutoff) return {"duplicate_or_cutoff"};
    if(!time_ok(now) || now<echo.freeze || now>echo.ticket.deadline) return {"ready_time"};
    for(double n:command) if(!std::isfinite(n)||n<limits_.low||n>limits_.high) return {"command_domain"};
    pending_->command=command;pending_->ready=true;pending_->job.ticket.ready_ns=now;last_time_=now;return {};
  }
  Result cutoff(int64_t now) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(life_!=Life::open) return {"owner_not_open"};
    if(!pending_ || !pending_->ready || pending_->cutoff) return {"no_ready_or_duplicate_cutoff"};
    if(!time_ok(now)||now<=pending_->job.ticket.deadline) return {"cutoff_time"};
    pending_->cutoff=true;last_time_=now;return {};
  }
  Result activate(const FrozenJob& echo,uint64_t target,int64_t now,uint64_t& token) {
    std::lock_guard<std::mutex> lock(mutex_);
    token=0;
    if(life_!=Life::open) return {"owner_not_open"};
    if(!pending_ || !same_job(echo,pending_->job)) return {"frozen_job_mismatch"};
    if(!pending_->ready || !pending_->cutoff) return {"not_committed"};
    if(target!=pending_->job.ticket.target || !time_ok(now) || now<pending_->job.ticket.target_ns) return {"activation_time_or_tick"};
    auto r=p1::publication_history_check(pending_->job.ticket.anchor,anchor_,history_);
    if(r.empty()) r=p1::command_check(pending_->command,anchor_,now,limits_);
    if(!r.empty()) {pending_.reset();last_time_=now;return {r};}
    if(last_pair_sequence_==UINT64_MAX) return fault("sequence_overflow");
    token=pending_->job.ticket.id;
    active_=Active{token,last_pair_sequence_+1,pending_->command,now};
    pending_.reset();last_time_=now;whole_=false;return {};
  }
  // This permit represents a local call start, not plant acceptance. No call is
  // made here. Closing between left and right revokes the right start permit.
  Result start(uint64_t token,int channel,int64_t now,double& requested) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(life_!=Life::open) return {"owner_not_open"};
    if(!active_ || active_->token!=token || channel<0 || channel>1) return {"transaction_identity"};
    if(!time_ok(now)||active_->calls[channel]!=Call::unattempted) return {"start_time_or_duplicate"};
    if(channel==1 && active_->calls[0]!=Call::succeeded) return {"left_not_succeeded"};
    active_->calls[channel]=Call::started;active_->start[channel]=now;
    last_time_=now;requested=active_->command[channel];return {};
  }
  Result complete(uint64_t token,int channel,bool success,int64_t now) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(!active_ || active_->token!=token || channel<0 || channel>1) return {"transaction_identity"};
    if(active_->calls[channel]!=Call::started || !time_ok(now) || now<active_->start[channel]) return {"completion_order"};
    auto call=success?Call::succeeded:Call::failed;
    active_->calls[channel]=call;active_->end[channel]=now;
    apply_call(channel,call,active_->command[channel],active_->sequence,active_->start[channel]);
    last_time_=now;
    if(!success && life_==Life::open) life_=Life::faulted;
    return {};
  }
  Result settle(uint64_t token,int64_t now) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(!active_ || active_->token!=token) return {"transaction_identity"};
    if(!time_ok(now)) return {"time_order"};
    if(active_->calls[0]==Call::started || active_->calls[1]==Call::started) return {"completion_missing"};
    whole_=active_->calls[0]==Call::succeeded && active_->calls[1]==Call::succeeded;
    last_pair_sequence_=active_->sequence;active_.reset();last_time_=now;
    if(life_==Life::closing) life_=Life::closed;
    else if(!whole_) life_=Life::faulted;
    return whole_?Result{}:Result{"incomplete_pair"};
  }
  Result close(int64_t now) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(life_==Life::closed || life_==Life::closing) return {"already_closing"};
    if(!time_ok(now)) return {"time_order"};
    pending_.reset();life_=active_?Life::closing:Life::closed;last_time_=now;return {};
  }
  Result change_version(const p1::Version& version,int64_t now) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(life_!=Life::open || active_) return {"version_change_not_permitted"};
    if(!time_ok(now)||version.epoch!=owner_.epoch) return {"version_time_or_epoch"};
    if(!version.model || !version.config || !version.schedule || version.task<version_.task ||
       version.model<version_.model || version.config<version_.config || version.schedule<version_.schedule)
      return {"version_regression_or_zero"};
    version_=version;pending_.reset();last_time_=now;return {};
  }
 private:
  struct Pending {FrozenJob job;p1::Command command;bool ready,cutoff;};
  struct Active {
    uint64_t token,sequence;p1::Command command;int64_t activation;
    std::array<Call,2> calls{Call::unattempted,Call::unattempted};
    std::array<int64_t,2> start{},end{};
  };
  bool time_ok(int64_t now) const {return now>0 && now>=last_time_;}
  static bool same_job(const FrozenJob& a,const FrozenJob& b) {
    const auto& x=a.ticket;const auto& y=b.ticket;
    return a.owner==b.owner && a.freeze==b.freeze && x.id==y.id && x.target==y.target &&
      x.origin==y.origin && x.deadline==y.deadline && x.target_ns==y.target_ns && x.version==y.version &&
      x.anchor.n==y.anchor.n && x.anchor.seq==y.anchor.seq && x.anchor.time==y.anchor.time && x.anchor.known==y.anchor.known &&
      x.prediction==y.prediction;
    // ready_ns is assigned internally, never trusted from Candidate echo.
  }
  std::string feedback_shape(const PairFeedback& f) const {
    if(!f.sequence || f.receipt<=0) return "feedback_shape";
    for(int ch=0;ch<2;++ch) {
      if(!std::isfinite(f.n[ch])||f.n[ch]<limits_.low||f.n[ch]>limits_.high) return "feedback_command_domain";
      if(f.calls[ch]==Call::unattempted) {if(f.start[ch]!=0||f.end[ch]!=0)return "unattempted_has_call_times";}
      else if(f.calls[ch]==Call::succeeded || f.calls[ch]==Call::failed) {
        if(f.start[ch]<=0||f.end[ch]<f.start[ch]||f.end[ch]>f.receipt)return "feedback_call_times";
      } else return "unfinished_feedback_call";
    }
    if(f.calls[1]!=Call::unattempted && (f.calls[0]!=Call::succeeded || f.start[1]<f.end[0])) return "sequential_call_order";
    return {};
  }
  Result fault(const std::string& reason) {
    anchor_.known={false,false};whole_=false;pending_.reset();life_=Life::faulted;return {reason};
  }
  void apply_call(int channel,Call call,double n,uint64_t seq,int64_t start) {
    if(call==Call::unattempted) return; // retains the previous command fact.
    anchor_.known[channel]=call==Call::succeeded;
    if(call==Call::succeeded) anchor_.n[channel]=n;
    anchor_.seq[channel]=seq;anchor_.time[channel]=start;
    history_.push_back({channel,seq,start,anchor_.n[channel],anchor_.known[channel]});
    while(history_.size()>256) history_.pop_front();
  }
  Owner owner_;p1::Limits limits_;p1::Version version_;
  mutable std::mutex mutex_;
  Life life_=Life::preparing;p1::Anchor anchor_;bool whole_=false;
  std::deque<p1::PublicationEvent> history_;
  std::optional<Pending> pending_;std::optional<Active> active_;
  uint64_t last_pair_sequence_=0,last_job_id_=0,last_target_=0;
  int64_t last_time_=0;
};
} // namespace c36
