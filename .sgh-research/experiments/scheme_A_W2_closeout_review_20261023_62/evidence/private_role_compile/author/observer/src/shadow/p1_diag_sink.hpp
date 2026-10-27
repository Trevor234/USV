// SPDX-License-Identifier: MIT
#pragma once
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <fstream>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <thread>
#include <nlohmann/json.hpp>
#include <time.h>
#include "p1_witness.hpp"
namespace p1 {
inline int64_t diag_now() noexcept { timespec t{}; clock_gettime(CLOCK_MONOTONIC,&t); return int64_t(t.tv_sec)*1000000000+t.tv_nsec; }
struct DiagPausePolicy {
  int64_t milliseconds=0;
  void validate(const std::string &mode, bool diag5, bool faults, bool witness) const {
    if(milliseconds<0||milliseconds>5000)throw std::runtime_error("diagnostic pause outside finite 0..5000 ms");
    if(milliseconds && (mode!="no_output"||!diag5||!faults||!witness))throw std::runtime_error("pause requires no_output diag5 faults and witness");
  }
};
// A clone of B0's Sink. Only this dedicated executable may pause its logger.
// Sink observations never acquire business/preparation locks or mutate slots.
template<class Decision, class Publisher>
class DiagSink {
 public:
  struct Item {nlohmann::json event;std::optional<Decision> decision;};
  DiagSink(const std::string &path,size_t capacity,Publisher publisher,
           Witness *witness=nullptr,DiagPausePolicy pause={},bool v1_saturation=false):v1_enabled_(v1_saturation),capacity_(capacity),publisher_(publisher),witness_(witness),pause_(pause) {
    if(v1_enabled_&&(!witness_||!witness_->enabled()||capacity_>512))throw std::runtime_error("V1 requires witnessed bounded queue");
    if(!capacity_)throw std::runtime_error("zero log capacity");
    if(pause_.milliseconds<0||pause_.milliseconds>5000)throw std::runtime_error("invalid finite pause");
    file_.open(path,std::ios::out|std::ios::app);if(!file_)throw std::runtime_error("source log unavailable");
    thread_=std::thread([this]{loop();});
  }
  ~DiagSink(){close();}
  bool add(nlohmann::json e,std::optional<Decision> d=std::nullopt){
    std::lock_guard<std::mutex> l(mutex_);generated_++;
    const bool v1_reject=v1_enabled_&&v1_state_==2&&d.has_value()&&!closing_;
    if(v1_reject){
      v1_first_failure_=!failed_.load();v1_depth_before_=q_.size();v1_sequence_=e.value("sequence",uint64_t{0});v1_reject_ns_=diag_now();
      while(q_.size()<capacity_){++generated_;++v1_fill_;q_.push_back({nlohmann::json{{"type","diagnostic_v1_queue_fill"},{"ordinal",v1_fill_},{"policy","decision_queue_saturation_v1"}},std::nullopt});}
      if(q_.size()>peak_)peak_=q_.size();v1_depth_rejected_=q_.size();
    }
    if(closing_||q_.size()>=capacity_){dropped_++;failed_=true;
      if(q_.size()>=capacity_&&!overflow_recorded_.exchange(true))phase(WitnessPhaseKind::QueueOverflow);
      first_failure();if(v1_reject){v1_state_=3;phase(WitnessPhaseKind::PauseEnd);cv_.notify_all();}return false;}
    q_.push_back({std::move(e),std::move(d)});if(q_.size()>peak_)peak_=q_.size();cv_.notify_one();return true;
  }
  bool failed()const{return failed_.load();}
  bool arm_v1_saturation(){
    std::lock_guard<std::mutex> lock(mutex_);
    if(!v1_enabled_||closing_||failed_||v1_state_!=0)return false;
    v1_state_=1;phase(WitnessPhaseKind::PauseArmed);cv_.notify_all();return true;
  }
  bool v1_triggered()const{return v1_state_.load()==3;}
  nlohmann::json v1_snapshot()const{
    std::lock_guard<std::mutex> lock(mutex_);
    return {{"policy","decision_queue_saturation_v1"},{"enabled",v1_enabled_},{"state",v1_state_.load()},
      {"capacity",capacity_},{"depth_before_fill",v1_depth_before_},{"depth_at_rejection",v1_depth_rejected_},
      {"filler_events",v1_fill_},{"decision_sequence",v1_sequence_},{"rejection_ns",v1_reject_ns_},
      {"first_failure_at_this_decision",v1_first_failure_},{"failed",failed_.load()},
      {"generated",generated_.load()},{"dropped",dropped_.load()},{"closing",closing_}};
  }
  bool arm_pause(){
    if(!pause_.milliseconds||!witness_||!witness_->enabled())return false;
    std::lock_guard<std::mutex> l(mutex_);if(closing_)return false;
    unsigned expected=0;if(!pause_state_.compare_exchange_strong(expected,1))return false;
    phase(WitnessPhaseKind::PauseArmed);cv_.notify_one();return true;
  }
  bool pause_active()const{return pause_state_.load()==2||v1_state_.load()==2;}
  uint64_t generated()const{return generated_;} uint64_t dropped()const{return dropped_;}
  size_t peak_depth()const{std::lock_guard<std::mutex> l(mutex_);return peak_;}
  void close(){if(!thread_.joinable())return;{std::lock_guard<std::mutex> l(mutex_);closing_=true;if(v1_enabled_&&(v1_state_==1||v1_state_==2)){const bool active=v1_state_==2;v1_state_=4;if(active)phase(WitnessPhaseKind::PauseEnd);}}
    {std::lock_guard<std::mutex> p(pause_mutex_);pause_cancel_=true;}pause_cv_.notify_all();cv_.notify_all();thread_.join();}
 private:
  void phase(WitnessPhaseKind kind,int64_t ns=0){if(!witness_)return;WitnessPhase r{};
    r.event_code=kind;r.observation_code=WitnessObservation::SinkThread;r.ns=ns?ns:diag_now();r.admission_slots=-1;
    r.failed=failed_?WitnessState::True:WitnessState::False;
    r.pause_active=pause_active()?WitnessState::True:WitnessState::False;witness_->record_phase(r);
  }
  void first_failure(){if(!failure_recorded_.exchange(true))phase(WitnessPhaseKind::SourceFailure);}
  void loop(){for(;;){Item i;
      {std::unique_lock<std::mutex> l(mutex_);cv_.wait(l,[this]{return closing_||!q_.empty()||pause_state_==1||v1_state_==1;});
        if(v1_state_==1&&q_.empty()&&!closing_){v1_state_=2;phase(WitnessPhaseKind::PauseBegin);}
        if(v1_state_==2&&!closing_)cv_.wait(l,[this]{return closing_||v1_state_!=2;});
        if(closing_&&v1_state_==2)v1_state_=4;
        if(pause_state_==1&&!closing_){pause_state_=2;l.unlock();const auto entered=diag_now();phase(WitnessPhaseKind::PauseBegin,entered);
          const auto deadline=entered+pause_.milliseconds*1000000;
          // No queue mutex is acquired during the pause. Close cancels it.
          {std::unique_lock<std::mutex> p(pause_mutex_);while(!pause_cancel_&&diag_now()<deadline)pause_cv_.wait_for(p,std::chrono::nanoseconds(deadline-diag_now()),[this]{return pause_cancel_.load();});}
          pause_state_=3;phase(WitnessPhaseKind::PauseEnd);l.lock();
        }
        if(q_.empty()&&closing_)break;if(q_.empty())continue;i=std::move(q_.front());q_.pop_front();}
      try{if(i.decision)publisher_->publish(*i.decision);file_<<i.event.dump()<<'\n';if(!file_){failed_=true;first_failure();}else emitted_++;}
      catch(...){failed_=true;first_failure();}
    }
    file_<<nlohmann::json{{"type","source_summary"},{"generated",generated_.load()},{"emitted",emitted_.load()},{"dropped",dropped_.load()},{"normal_source_complete",!failed_.load()&&generated_==emitted_},{"finished_ns",diag_now()}}.dump()<<'\n';
    file_.flush();if(!file_){failed_=true;first_failure();}
  }
  const bool v1_enabled_;std::atomic<unsigned> v1_state_{0};
  size_t v1_depth_before_=0,v1_depth_rejected_=0;uint64_t v1_fill_=0,v1_sequence_=0;int64_t v1_reject_ns_=0;bool v1_first_failure_=false;
  size_t capacity_,peak_=0;std::ofstream file_;mutable std::mutex mutex_;std::condition_variable cv_;std::deque<Item> q_;bool closing_=false;std::thread thread_;
  std::atomic<uint64_t> generated_{0},emitted_{0},dropped_{0};std::atomic<bool> failed_{false},overflow_recorded_{false},failure_recorded_{false};
  Publisher publisher_;Witness *witness_;DiagPausePolicy pause_;std::atomic<unsigned> pause_state_{0};
  std::mutex pause_mutex_;std::condition_variable pause_cv_;std::atomic<bool> pause_cancel_{false};
};
}
