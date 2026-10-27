#!/usr/bin/env python3
"""Derive owner shell; keep numerical/admission/activation core source-visible."""
from pathlib import Path
import hashlib
import json
import re

D=Path(__file__).resolve().parent
A=D/'author'
OLD=D.parent/'scheme_A_owned_business_start_20261020_39/author/observer/src/shadow/regulator_shadow_observer.cpp'


def masked(text):
    return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27',lambda m:' '*len(m.group()),text)


def replace_body(text,begin,new):
    at=text.index(begin);mask=masked(text);start=mask.index('{',at);depth=1;end=start+1
    while depth:
        if mask[end]=='{':depth+=1
        elif mask[end]=='}':depth-=1
        end+=1
    return text[:at]+new+text[end:]


def one(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new,1)


def main():
    s=OLD.read_text()
    s=one(s,'#include "c38_diagnostic_gate.hpp"','#include "c38_diagnostic_gate.hpp"\n#include "m4_owned_runtime.hpp"\n#include "owned_execution_policy_native_v1.hpp"')
    s=replace_body(s,'  explicit Regulator(', (D/'implementation/regulator_constructor_v1.cpp.part').read_text().rstrip())
    s=one(s,'bool business_start_failed()const{return business_start_failed_;}','bool business_start_failed()const{return own_start_failed_;}')
    s=replace_body(s,'  bool close_source(){', '''  bool close_source(){
    if(tick_.joinable())tick_.join();prep_stop_=true;prep_cv_.notify_all();if(prep_.joinable())prep_.join();
    sink_->add({{"type","owned_reception_closed"},{"executor_detached",executor_detached_},{"closed_ns",p1::monotonic_ns()},
      {"started",own_started_},{"decision_count",decision_seq_},{"job_count",job_id_},{"normal_contract_complete",normal_complete_.load()},
      {"worker_capability_received",worker_capability_received_},{"worker_candidate_received",worker_candidate_received_}});
    sink_->close();{std::lock_guard<std::mutex> lock(mutex_);phase_locked(p1::WitnessPhaseKind::Close,p1::WitnessObservation::Close,p1::monotonic_ns());}
    if(!audit_identity_ok_)witness_->mark_header_invalid();witness_->close_after_join();
    audit_closed_=witness_->write_terminal(witness_file_.c_str())&&witness_->summary().observation_complete;
    fprintf(stdout,"REGULATOR_CLOSE_FLUSH_SUCCESS=%s\\n",sink_->failed()?"false":"true");return !sink_->failed();
  }''')
    s=one(s,'std::string eligible(const Snapshot & s,int64_t now) {','std::string eligible(const Snapshot & s,int64_t now,bool require_anchor=true) {')
    s=one(s,'    if(!s.anchor.known[0]||!s.anchor.known[1])return "unknown_anchor";','    if(require_anchor&&(!s.anchor.known[0]||!s.anchor.known[1]))return "unknown_anchor";')
    s=replace_body(s,'  void retry_reference_pair_locked(','''  void retry_reference_pair_locked(const char *trigger,bool input_valid){
    if(input_valid&&sink_)sink_->add({{"type","owned_reference_pair_commit"},{"trigger",trigger},{"policy","owned_reference_pair_completion_before_business_v1"},{"task_generation",version_.task},{"processed_ns",p1::monotonic_ns()}});
  }''')
    s=replace_body(s,'  bool finish_tick(','''  bool finish_tick(const p1::Decision &d,int64_t now,int64_t planned,uint64_t tick,int64_t &stop_start,const p1::Json *observation=nullptr){
    auto row=decision_json(d);if(observation)row["d0_observation"]=*observation;
    if(!sink_->add(std::move(row),d)){std::lock_guard<std::mutex> lock(mutex_);normal_complete_=false;stopping_=true;if(!stop_start)stop_start=now;invalidate_locked();}
    {
      std::lock_guard<std::mutex> lock(mutex_);const auto current=p1::monotonic_ns();check_worker_locked(current);
      if(!stopping_&&!stop_requested&&!worker_unusable_&&worker_valid_&&!sink_->failed()&&own_authority_->business_permitted(current)){
        auto snapshot=snapshot_locked(current);
        if(eligible(snapshot,current).empty()){
          std::lock_guard<std::mutex> queue(prep_mutex_);
          if(pending_)sink_->add({{"type","owned_pending_replaced"},{"old_target_tick",pending_->tick+1},{"new_target_tick",tick+1}});
          pending_=Preparation{std::move(snapshot),tick,planned};prep_cv_.notify_one();
        }
      }
    }
    const auto close=p1::publication::shutdown_result(stopping_.load(),true,d.final_n,d.publish_success,now,stop_start,c_.at("shutdown_grace_ns"));
    if(close.exit_tick){sink_->add({{"type","regulator_shutdown"},{"zero_requested",close.zero_requested},{"zero_target_published",close.zero_target_published},{"shutdown_grace_exceeded",close.grace_exceeded},{"last_decision_sequence",d.sequence},{"normal_contract_complete",normal_complete_.load()&&!sink_->failed()},{"plant_hold_end_known",false},{"finished_ns",p1::monotonic_ns()}});return true;}
    return false;
  }''')
    s=one(s,'    int64_t origin=p1::monotonic_ns()+1000000000,stop_start=0;uint64_t tick=0,last_schedule=0;','    int64_t origin=own_origin_ns_,stop_start=0;uint64_t tick=0,last_schedule=0;')
    s=one(s,'      auto now=p1::monotonic_ns();p1::Decision d;','      auto now=p1::monotonic_ns();try{if(!own_authority_->tick(now)){normal_complete_=false;stop_requested=true;}}catch(const std::exception &e){normal_complete_=false;stop_requested=true;sink_->add({{"type","owned_tick_policy_failed"},{"reason",e.what()},{"checked_ns",now}});}p1::Decision d;')
    s=one(s,'d.publish_sim_ns[i]=sim_;d.publish_epoch[i]=version_.epoch;d.publish_clock_age_ns[i]=start-clock_receive_;','d.publish_sim_ns[i]=clock_receive_>0?sim_+(start-clock_receive_):0;d.publish_epoch[i]=version_.epoch;d.publish_clock_age_ns[i]=start-clock_receive_;')
    s=one(s,'    if(result.timing_failed()){normal_complete_=false;worker_unusable_=true;}','''    if(result.timing_failed()){normal_complete_=false;worker_unusable_=true;stop_requested=true;}
    try{owned_pair_record(d,old,result);}catch(const std::exception &e){normal_complete_=false;worker_unusable_=true;stop_requested=true;sink_->add({{"type","owned_pair_policy_failed"},{"sequence",d.sequence},{"reason",e.what()},{"starts",d.publish_start_ns},{"returned",d.publish_success}});}''')
    insert=(D/'implementation/regulator_owned_methods_v1.cpp.part').read_text()
    s=one(s,'  std::string business_start_policy_="immediate",',insert+'''
  std::unique_ptr<formal_owned::Peer> own_driver_,own_fixture_,own_worker_,own_recorder_;
  std::unique_ptr<p1::owned_execution::OutputAuthority> own_authority_;
  p1::Json own_peer_pins_,own_manifest_,own_ready_version_;
  std::string own_output_dir_,own_manifest_file_,own_manifest_sha_,own_ready_sha_,own_grant_sha_;
  int64_t own_prepare_begin_=0,own_origin_ns_=0;bool own_started_=false,own_start_failed_=false;
  rclcpp::Publisher<usv_research_interfaces::msg::AppliedControl>::SharedPtr own_applied_pub_;
  std::string business_start_policy_="immediate",''')
    start=s.index('int main(int argc,char **argv)')
    s=s[:start]+'''int main(int argc,char **argv){rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,stop_signal);std::signal(SIGTERM,stop_signal);
try{auto node=std::make_shared<Regulator>();rclcpp::executors::SingleThreadedExecutor exec;exec.add_node(node);
while(!node->finished()&&rclcpp::ok()){node->poll_owned_start();exec.spin_some(std::chrono::milliseconds(10));std::this_thread::sleep_for(std::chrono::milliseconds(1));}
exec.remove_node(node);node->mark_executor_detached();const bool closed=node->close_source(),audit=node->audit_closed(),start_failed=node->business_start_failed();node.reset();rclcpp::shutdown();return start_failed?5:(closed?(audit?0:3):2);
}catch(const std::exception &e){fprintf(stderr,"M4 regulator fatal: %s\\n",e.what());rclcpp::shutdown();return 1;}}
'''
    target=A/'observer/src/shadow/regulator_owned_execute.cpp'
    with target.open('x') as f:f.write(s)
    worker=A/'worker/solver_worker.cpp';w=worker.read_text()
    w=one(w,'#include "protocol.hpp"','#include "protocol.hpp"\n#include "m4_owned_runtime.hpp"')
    w=one(w,'Worker():Node("p1_solver_worker") {','Worker():Node("p1_solver_worker",formal_owned::node_options()) {\n    formal_owned::entry_arguments(*this);')
    w=one(w,'c_=p1::load_contract(file,hash_);resources_=p1::resource_limits_from_contract(c_);','c_=p1::load_contract(file,hash_);m4_owned::frozen(c_,hash_);p1_owned::require(declare_parameter<std::string>("m4_release_scope","")==m4_owned::scope,"M4 Worker isolated scope");resources_=p1::resource_limits_from_contract(c_);')
    with (A/'worker/solver_worker_m4.cpp').open('x') as f:f.write(w)
    record={'schema':'M4-owned-runtime-source-derivation/v1','parent':str(OLD),'parent_sha256':hashlib.sha256(OLD.read_bytes()).hexdigest(),
      'child':str(target),'child_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'control_numbers_changed':False,
      'scope':'new owned shell; existing prepare/activation/tick core derived with visible affected changes; no parent edits',
      'worker_deltas':['full frozen contract and isolated scope required','disable implicit ROS admin surfaces','solver/work loop unchanged'],
      'GID_ABI_delta':'native FastDDS16 bytes ->32hex in derived context; original47 48hex pure model preserved',
      'changes':['new constructor/actual registered roles and endpoint creation','native Driver grant+source/config authentication','owned input metadata','fixed grant tick origin','own after-publish preparation','actual output accounting and Applied','new bounded-close shell']}
    with (D/'evidence/runtime_source_derivation_v1.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    print(json.dumps({'regulator_lines':len(s.splitlines()),'worker_solver_loop_modified':False,'parents_edited':False}))


if __name__=='__main__':main()
