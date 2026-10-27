
#include <nlohmann/json.hpp>
#include <array>
#include <atomic>
#include <mutex>
#include <memory>
#include <iostream>
using J=nlohmann::json;
namespace p1 {struct Anchor{std::array<bool,2> known{};std::array<double,2> n{};std::array<long,2> time{};std::array<unsigned long,2> seq{};};struct Decision{bool candidate_accepted=false;long activation_commit_ns=0;unsigned long sequence=2,tick=2;std::array<double,2> final_n{};std::array<long,2> publish_start_ns{},publish_end_ns{},publish_sim_ns{};std::array<bool,2> publish_success{true,true};};namespace publication{struct PairResult{std::array<int,2> calls{};};}}
struct Observed{bool initial_pair=false,rho_available=true,gap_exceeded=false,span_exceeded=false,rate_exceeded=false,bootstrap_late=false,command_invalid=false;};
struct Authority{p1::Anchor value;bool initialized(){return true;}bool terminal(){return false;}auto &anchor(){return value;}Observed record_pair(const std::array<double,2>&,const std::array<int,2>&,const std::string&,long){return {};}};
struct Sink {J rows=J::array();void add(const J&x){rows.push_back(x);}};
struct Regulator{std::atomic<bool>stopping_{false};bool worker_unusable_=false,normal_complete_=true,stop_requested=false;long last_accepted_=1;std::string scope_="test",own_grant_sha_="test";std::mutex mutex_;p1::Anchor anchor_;std::unique_ptr<Authority>own_authority_=std::make_unique<Authority>();std::unique_ptr<Sink>sink_=std::make_unique<Sink>();
// Only this dependency is stubbed: reproduce the production void return and caught publish exception.
void emit_owned_applied(const p1::Decision&d,const p1::Anchor&){try{throw 1;}catch(...){normal_complete_=false;worker_unusable_=true;stop_requested=true;sink_->add({{"type","owned_applied_publication_failed"},{"sequence",d.sequence}});}}
  void owned_pair_record(p1::Decision &d,const p1::Anchor &before,const p1::publication::PairResult &actual){
    std::string kind=d.candidate_accepted?"accepted":stopping_.load()?"shutdown":!own_authority_->initialized()?"bootstrap":
      last_accepted_==0&&!worker_unusable_?"waiting":"fallback";
    const auto observed=own_authority_->record_pair(d.final_n,actual.calls,kind,d.candidate_accepted?d.activation_commit_ns:0);
    // R1 (74 review R74-01): the real per-side API facts and the Applied
    // record are written BEFORE any consistency acceptance that may fail. A
    // failed acceptance records the divergence and re-anchors the command
    // history to the independent physical output facts; it can never erase
    // the already-achieved API/Applied ledger.
    sink_->add({{"type","owned_API_pair"},{"sequence",d.sequence},{"tick",d.tick},{"kind",kind},{"scope",scope_},{"command_n",d.final_n},
      {"previous_known",before.known},{"previous_n",before.n},{"previous_start_ns",before.time},
      {"starts",d.publish_start_ns},{"ends",d.publish_end_ns},{"returned",d.publish_success},{"sim_ns",d.publish_sim_ns},
      {"initial_pair",observed.initial_pair},{"rho_available",observed.rho_available},{"gap_exceeded",observed.gap_exceeded},
      {"span_exceeded",observed.span_exceeded},{"rate_exceeded",observed.rate_exceeded},{"bootstrap_late",observed.bootstrap_late},
      {"command_invalid",observed.command_invalid},{"terminal",own_authority_->terminal()},{"grant_sha256",own_grant_sha_},
      {"consistency_pending",true}});
    emit_owned_applied(d,before);
    {
      std::lock_guard<std::mutex> lock(mutex_);const auto &a=own_authority_->anchor();
      const bool agrees=a.known==anchor_.known&&a.n==anchor_.n&&a.time==anchor_.time&&a.seq==anchor_.seq;
      if(!agrees){
        normal_complete_=false;worker_unusable_=true;stop_requested=true;
        sink_->add({{"type","owned_pair_consistency_failed"},{"sequence",d.sequence},{"tick",d.tick},
          {"authority_anchor",{{"known",a.known},{"n",a.n},{"time",a.time},{"seq",a.seq}}},
          {"history_anchor_before_reanchor",{{"known",anchor_.known},{"n",anchor_.n},{"time",anchor_.time},{"seq",anchor_.seq}}},
          {"resolution","history re-anchored to independent physical output facts"},
          {"api_facts_recorded",true},{"applied_emitted",true},{"terminal",own_authority_->terminal()}});
        anchor_=a;
      }
      if(own_authority_->terminal()){normal_complete_=false;worker_unusable_=true;stop_requested=true;}
    }
  }

};int main(){Regulator r;r.own_authority_->value.known={true,true};p1::Decision d;p1::Anchor before;p1::publication::PairResult actual;r.owned_pair_record(d,before,actual);std::cout<<r.sink_->rows.dump(2)<<"\n";}
