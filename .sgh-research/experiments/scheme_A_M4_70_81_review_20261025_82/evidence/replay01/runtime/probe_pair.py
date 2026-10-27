from pathlib import Path
import subprocess,json,hashlib
src=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_r2_driver_20261025_78/implementation/t2_author_r3/observer/src/shadow/regulator_owned_execute.cpp')
s=src.read_text();a=s.index('  void owned_pair_record(');b=s.index('  void emit_owned_applied(',a);body=s[a:b]
pre=r'''
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
'''
post=r'''
};int main(){Regulator r;r.own_authority_->value.known={true,true};p1::Decision d;p1::Anchor before;p1::publication::PairResult actual;r.owned_pair_record(d,before,actual);std::cout<<r.sink_->rows.dump(2)<<"\n";}
'''
base=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_70_81_review_20261025_82/evidence/replay01/runtime');(base/'pair_controlflow_probe.cpp').write_text(pre+body+post)
subprocess.run(['c++','-std=c++17','-O2',str(base/'pair_controlflow_probe.cpp'),'-o',str(base/'pair_controlflow_probe')],check=True)
p=subprocess.run([str(base/'pair_controlflow_probe')],text=True,capture_output=True,check=True);(base/'pair_controlflow_probe.json').write_text(p.stdout)
rows=json.loads(p.stdout);assert any(x['type']=='owned_applied_publication_failed' for x in rows);assert any(x['type']=='owned_pair_consistency_failed' and x['applied_emitted'] is True for x in rows)
print(json.dumps({'probe':'actual owned_pair_record body with dependencies stubbed; not ROS or owned evidence','copied_body_sha256':hashlib.sha256(body.encode()).hexdigest(),'failure_and_emitted_both_reported':True,'output':str(base/'pair_controlflow_probe.json')},indent=2))
