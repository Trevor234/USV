#include <fstream>
#include <iostream>
#include <memory>
#include <nlohmann/json.hpp>
#include "/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_r2_driver_20261025_78/implementation/t2_author_r3/observer/src/shadow/p1_witness.hpp"
using J=nlohmann::json;
template<class R>void ids(R&r,const J&v){
#define ID(k) r.k=v.at(#k).get<decltype(r.k)>();
ID(job_id) ID(tick) ID(target_tick) ID(task_generation) ID(model_generation) ID(config_generation) ID(schedule_generation) ID(clock_epoch)
#undef ID
}
int main(int argc,char**argv){std::ifstream f(argv[1]);J x;f>>x;
if(argc>2){x["tick"][9]["tick"]=0;x["tick"][10]["tick"]=1;}
p1::WitnessHeader h{};const auto z=x.at("header");
#define H(k) p1::witness_text(h.k,z.at(#k).get<std::string>());
H(run_id) H(boot_id) H(contract_sha256) H(source_sha256) H(binary_sha256) H(worker_binary_sha256) H(worker_instance)
#undef H
 auto w=std::make_unique<p1::Witness>(true,h);bool accepted=true;
 for(auto&v:x.at("tick")){p1::WitnessTick r{};ids(r,v);
#define F(k) r.k=v.at(#k).get<decltype(r.k)>();
 F(planned_ns) F(start_ns) F(end_ns) F(skipped_ticks) F(candidate_present) F(failed_start) F(stopping_start) F(failed_end) F(stopping_end)
#undef F
 accepted &=w->record_tick(r);}
 for(auto&v:x.at("submit")){p1::WitnessSubmit r{};ids(r,v);r.commit_ns=v.at("commit_ns");r.failed=v.at("failed");r.stopping=v.at("stopping");accepted &=w->record_submit(r);}
 for(auto&v:x.at("activation")){p1::WitnessActivation r{};ids(r,v);r.commit_ns=v.at("commit_ns");r.ready_commit_ns=v.at("ready_commit_ns");r.accepted=v.at("accepted");r.failed=v.at("failed");r.stopping=v.at("stopping");r.reason_code=static_cast<p1::WitnessActivationReason>(v.at("reason_code").get<unsigned>());accepted &=w->record_activation(r);}
 for(auto&v:x.at("phase")){p1::WitnessPhase r{};r.event_code=static_cast<p1::WitnessPhaseKind>(v.at("event_code").get<unsigned>());r.observation_code=static_cast<p1::WitnessObservation>(v.at("observation_code").get<unsigned>());r.ns=v.at("ns");r.tick=v.at("tick");r.job_id=v.at("job_id");r.admission_slots=v.at("admission_slots");
#define B(k) r.k=v.at(#k).is_null()?p1::WitnessState::Unknown:v.at(#k).get<bool>()?p1::WitnessState::True:p1::WitnessState::False;
 B(candidate_present) B(pending_present) B(failed) B(stopping) B(pause_active)
#undef B
 accepted &=w->record_phase(r);}
 w->close_after_join();auto s=w->summary();
 std::cout<<J{{"actual_current_witness_header",true},{"all_record_append_accepted",accepted},{"observation_complete",s.observation_complete},{"normal_contract_qualified",s.normal_contract_qualified},{"records_inconsistency",s.inconsistency},{"first_failure_code",unsigned(s.first_failure.code)},{"counterfactual_tick_fix",argc>2}}.dump(2)<<"\n";
}
