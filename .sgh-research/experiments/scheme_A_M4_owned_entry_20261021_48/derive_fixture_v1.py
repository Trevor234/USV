#!/usr/bin/env python3
"""Keep the calibrated nominal model/reference; bind its Applied source to M4 owner."""
from pathlib import Path
import hashlib
import json
import shutil

D=Path(__file__).resolve().parent
A=D/'author'
P=D.parent/'scheme_A_longitudinal_20261016_19/author_snapshot'


def one(s,old,new):
    assert s.count(old)==1,old
    return s.replace(old,new,1)


def main():
    for name in ['exact_peer.hpp','controlled_protocol.hpp','nominal_history.hpp']:
        shutil.copy2(P/'owner_common'/name,A/'common'/name)
    shutil.copy2(P/'fixture/controlled_reference.hpp',A/'fixture/controlled_reference.hpp')
    s=(P/'fixture/synthetic_source.cpp').read_text()
    s=one(s,'#include "p1_owned_identity.hpp"','#include "p1_owned_identity.hpp"\n#include "m4_owned_runtime.hpp"')
    s=one(s,'Synthetic():Node("p1_synthetic_source") {','Synthetic():Node("p1_synthetic_source",formal_owned::node_options()) {\n  formal_owned::entry_arguments(*this);')
    s=one(s,'declare_parameter<std::string>("controlled_phase_mode","A2")','declare_parameter<std::string>("controlled_phase_mode","C")')
    s=one(s,'p1_owned::require(std::isfinite(reference_speed_)&&(mode_=="C"?(reference_speed_==.05||reference_speed_==.1||reference_speed_==.3||reference_speed_==.6):reference_speed_==0.),"controlled fixture reference speed domain");','p1_owned::require(mode_=="C"&&reference_speed_==.05,"M4 fixed calibrated nominal/reference domain");')
    lo=s.index('  owner_manifest_=declare_parameter')
    hi=s.index('  applied_=create_subscription',lo)
    s=s[:lo]+'''  contract_file_=declare_parameter<std::string>("contract_file","");owner_run_=run_;
  const auto scope=declare_parameter<std::string>("m4_release_scope","");
  contract_configuration_=m4_owned::contract(contract_file_,contract_,"execute",scope);
  const auto driver_file=declare_parameter<std::string>("driver_pins_file","");
  const auto driver_hash=declare_parameter<std::string>("driver_pins_sha256","");
  driver_pin_=formal_owned::read_pinned(driver_file,driver_hash);driver_=formal_owned::driver_peer(driver_pin_,run_,contract_);
  formal_owned::overrides(*this,{"run_id","contract_hash","output_dir","start_file","topics_file","topics_sha256","controlled_phase_mode","reference_speed_m_s","contract_file","m4_release_scope","driver_pins_file","driver_pins_sha256","use_sim_time"});
  hydro_=contract_configuration_.at("hydro");model_=std::make_unique<controlled::NominalHistory>(hydro_,contract_);
  nominal_.open(output_+"/nominal_steps.jsonl",std::ios::out|std::ios::app);p1_owned::require(bool(nominal_),"M4 nominal Source unavailable");
''' +s[hi:]
    s=one(s,'{"source_state",mode_=="C"?"actual_Applied_nominal_RK4":"stationary_zero"}',
      '{"source_state","actual_owned_Applied_nominal_RK4"},{"physical_publishers",0},{"contract_configuration",contract_configuration_},{"m4_release_scope",m4_owned::scope},{"Applied_subscribers",1},{"Applied_publishers",0}')
    s=one(s,'  auto reason=owner_peer_->reason(info);const auto &owner=owner_peer_->manifest();',
      '  p1_owned::require(bool(owner_peer_),"M4 Applied before owner authentication");auto reason=owner_peer_->reason(info);const auto &owner=owner_peer_->manifest();')
    s=one(s,'m.baseline_id!=controlled::baseline','m.baseline_id!=contract_configuration_.at("baseline_input")')
    old='void publish(){if(!start_){if(!std::filesystem::exists(start_file_))return;auto command=p1_owned::Json::parse(p1_owned::read_bounded(start_file_));p1_owned::require(command.at("run_id")==run_&&command.at("boot_id")==p1_owned::boot_id()&&command.at("schema")=="p1-synthetic-start-v1","synthetic start identity differs");start_=p1_owned::steady_ns();}'
    new='''void publish(){if(!start_){if(!std::filesystem::exists(start_file_))return;
    auto command=c36_owned::detail::strict_json(c36_owned::detail::read_manifest(start_file_));
    const std::set<std::string> keys={"schema","run_id","boot_id","contract_sha256","scope","driver_manifest_sha256","owner","issued_ns","sequence"};
    p1_owned::require(command.size()==keys.size(),"M4 Fixture start exact fields");for(const auto &k:keys)p1_owned::require(command.contains(k),"M4 Fixture start missing field");
    p1_owned::require(command.at("run_id")==run_&&command.at("boot_id")==p1_owned::boot_id()&&command.at("schema")=="M4-owned-inputs-start-v1"&&command.at("contract_sha256")==contract_&&command.at("scope")==m4_owned::scope&&command.at("driver_manifest_sha256")==driver_pin_.at("manifest_sha256")&&c36_owned::detail::uint_field(command,"sequence",1)==1,"M4 Fixture start actual identity");
    const auto issued=c36_owned::detail::uint_field(command,"issued_ns",INT64_MAX),checked=p1_owned::steady_ns();
    p1_owned::require(issued>0&&issued<=uint64_t(checked)&&uint64_t(checked)-issued<=2000000000ULL&&driver_->stable_manifest(),"M4 Fixture start time/Driver");
    const auto &p=command.at("owner");formal_owned::Peer checked_owner(p,m4_owned::owner_role,run_,contract_);
    p1_owned::require(checked_owner.manifest().at("contract_configuration")==contract_configuration_&&checked_owner.manifest().at("m4_release_scope")==m4_owned::scope,"M4 Fixture exact owner contract/scope");
    for(const auto &key:{"left","right"})p1_owned::require(m4_owned::graph_publisher(*this,checked_owner.manifest(),contract_configuration_.at("output_topics").at(key),"std_msgs/msg/Float64"),"M4 Fixture sole actual owner outputs");
    owner_peer_=std::make_unique<controlled::ExactPeer>(controlled::ExpectedPeer{p.at("manifest_path"),m4_owned::owner_role,run_,contract_,p.at("binary_sha256"),p.at("source_bundle_sha256"),"/research/control/applied","usv_research_interfaces/msg/AppliedControl"});
    source({{"type","nominal_owner_peer_bound"},{"peer",owner_peer_->evidence()},{"start_request",command},{"contract_hydro",hydro_},{"model_contract_sha256",contract_},{"initial_zero_force_is_nominal_fixture_assumption_not_command_authority",true}});
    start_=p1_owned::steady_ns();}
'''
    s=one(s,old,new)
    s=one(s,' double reference_speed_=0.;',' p1_owned::Json contract_configuration_,driver_pin_;std::unique_ptr<formal_owned::Peer> driver_;\n double reference_speed_=0.;')
    target=A/'fixture/synthetic_source_m4.cpp'
    with target.open('x') as f:f.write(s)
    record={'schema':'M4-nominal-fixture-derivation/v1','parent':str(P/'fixture/synthetic_source.cpp'),'child':str(target),
      'parent_sha256':hashlib.sha256((P/'fixture/synthetic_source.cpp').read_bytes()).hexdigest(),'child_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
      'fixed_19_hydro_and_reference_generator_unchanged':True,'same_cached_RK4_algorithm':True,'actual_new_owner_bound_at_start':True,
      'plant_connected':False,'reference_speed_m_s':.05,'source_scope':'calibrated isolated nominal subset; original F5 plant/reference trajectory identity not claimed'}
    with (D/'evidence/fixture_derivation_v1.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    print(json.dumps({'fixture_lines':len(s.splitlines()),'model_and_reference_tuned':False}))


if __name__=='__main__':main()
