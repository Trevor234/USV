#include <iostream>
#include <deque>
#include <string>
#include <vector>
#include <cassert>
#include <nlohmann/json.hpp>
#include "publication_result_v1.hpp"
namespace p1 { inline int64_t monotonic_ns(){return 1;} }
namespace usv_mpc { struct HeldInputEvent {int64_t sim_ns; int channel; double n;}; }
struct Replay {
 p1::Anchor anchor_;
 std::deque<usv_mpc::HeldInputEvent> history_,ready_history_,publication_history_;
 nlohmann::json c_={{"history_capacity",128}};
 std::vector<std::string> reset_reasons;unsigned invalidations=0;
 void invalidate_legacy_ready_locked(const std::string&r,int64_t){reset_reasons.push_back(r);}
 void invalidate_locked(){++invalidations;}
  void push_history_locked(const usv_mpc::HeldInputEvent & e){if(!history_.empty()&&e.sim_ns<history_.back().sim_ns){invalidate_legacy_ready_locked("held_history_time_regression",p1::monotonic_ns());history_.clear();ready_history_.clear();publication_history_.clear();anchor_.known={false,false};invalidate_locked();return;}history_.push_back(e);while(history_.size()>c_.at("history_capacity").get<size_t>())history_.pop_front();}
};
int main(){
 const std::array<int64_t,2> times={900492349656360LL,900492349741648LL};
 const std::array<int64_t,2> sims={102588031850LL,102588117138LL};
 Replay r;r.anchor_.known={true,true};r.anchor_.seq={14,14};r.history_.push_back({103129840890LL,1,0});
 for(int ch=0;ch<2;++ch){
 p1::publication::CallResult call{times[ch],times[ch]+1,true};
 p1::publication::apply_channel_result(r.anchor_,ch,0,call);
 r.push_history_locked({sims[ch],ch,0});
 }
 assert(!r.anchor_.known[0]&&r.anchor_.known[1]);assert(r.anchor_.seq[0]==15&&r.anchor_.seq[1]==15);assert(r.anchor_.time==times);
 assert(r.reset_reasons==std::vector<std::string>{"held_history_time_regression"});assert(r.invalidations==1);
 Replay control;control.anchor_.known={true,true};control.anchor_.seq={14,14};control.history_.push_back({102500000000LL,1,0});
 for(int ch=0;ch<2;++ch){p1::publication::CallResult call{times[ch],times[ch]+1,true};p1::publication::apply_channel_result(control.anchor_,ch,0,call);control.push_history_locked({sims[ch],ch,0});}
 assert(control.anchor_.known[0]&&control.anchor_.known[1]);assert(control.reset_reasons.empty());
 std::cout<<"regression replay: known=[false,true], seq=[15,15], matched_time=true, reset=held_history_time_regression\nnonregression control: known=[true,true], resets=0\n";
}
