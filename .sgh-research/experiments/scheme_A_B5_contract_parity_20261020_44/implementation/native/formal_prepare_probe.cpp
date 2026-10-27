// SPDX-License-Identifier: MIT
// Seeded policy-core test process. No ROS endpoints or actual peer authenticity.
#include "formal_prepare_gate_v1.hpp"
#include <fstream>
#include <iostream>
#include <memory>
namespace f=p1::formal_prepare;
f::Context context(const f::Json &j){
  f::Context c;
  c.driver_live=j.at("driver_live");c.worker_live=j.at("worker_live");c.fixture_live=j.at("fixture_live");
  c.recorder_live=j.at("recorder_live");c.worker_capability_valid=j.at("worker_capability_valid");
  c.source_inputs_valid=j.at("source_inputs_valid");c.reference_pair_ready=j.at("reference_pair_ready");
  c.recording_ready=j.at("recording_ready");c.sink_ready=j.at("sink_ready");c.stopping=j.at("stopping");
  c.capability_receipt_ns=j.at("capability_receipt_ns");c.ready_generation=j.at("ready_generation");
  c.physical_publishers=j.at("physical_publishers");c.solve_job_publishers=j.at("solve_job_publishers");
  c.decision_publishers=j.at("decision_publishers");c.applied_publishers=j.at("applied_publishers");
  c.ready_snapshot_sha256=j.at("ready_snapshot_sha256");c.version=j.at("version");return c;
}
int main(){
  std::string line;
  while(std::getline(std::cin,line)){
    f::Json result;std::unique_ptr<f::Gate> gate;
    try{
      const auto r=f::Json::parse(line);std::ifstream file(r.at("contract_path").get<std::string>(),std::ios::binary);
      if(!file)throw std::runtime_error("test contract file unavailable");
      std::string raw(65537,'\0');file.read(raw.data(),raw.size());raw.resize(size_t(file.gcount()));
      const auto contract=p1::parse_unique_contract(raw);
      const auto mode=r.at("mode").get<std::string>();f::validate_entry(contract,mode);
      const auto &j=r.at("identity");
      f::Identity id{j.at("run_id"),j.at("boot_id"),j.at("contract_sha256"),j.at("preparer_manifest_sha256"),
        j.at("driver_pid"),j.at("driver_start_ticks"),j.at("driver_exe_sha256"),j.at("driver_argv_sha256"),
        j.at("driver_tool_sha256"),j.at("worker_manifest_sha256"),j.at("fixture_manifest_sha256"),j.at("recorder_manifest_sha256")};
      gate=std::make_unique<f::Gate>(contract,mode,id,r.at("created_ns"));
      const auto c=context(r.at("context"));const auto op=r.at("operation").get<std::string>();
      const auto now=r.at("now_ns").get<int64_t>();
      if(op=="close_before_open")gate->close(now);
      if(op=="expire_before_open")gate->poll(now,c);
      gate->open(r.at("raw_request"),now,c);
      if(op=="replay")gate->open(r.at("raw_request"),now,c);
      else if(op=="close"){gate->close(now+1);gate->close(now+2);}
      else if(op=="close_then_replay"){gate->close(now+1);gate->open(r.at("raw_request"),now+2,c);}
      else if(op=="poll"||op=="poll_then_replay"){
        gate->poll(r.at("post_ns"),context(r.at("post_context")));
        if(op=="poll_then_replay")gate->open(r.at("raw_request"),r.at("post_ns"),context(r.at("post_context")));
      }
      result={{"operation_completed",true}};
    }catch(const std::exception &e){result={{"operation_completed",false},{"reason",e.what()}};}
    result["state"]=gate?f::name(gate->state()):"not_created";
    if(gate)result["evidence"]=gate->evidence();
    result["seeded_component_only"]=true;
    std::cout<<result.dump(-1,' ',false,f::Json::error_handler_t::replace)<<std::endl;
  }
}
