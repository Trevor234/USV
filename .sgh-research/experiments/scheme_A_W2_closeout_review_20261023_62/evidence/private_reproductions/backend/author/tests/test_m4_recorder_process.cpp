// SPDX-License-Identifier: MIT
// Actual owned Recorder process authentication; no ROS init or output API here.
#include "recorder_process_pin_v1.hpp"
#include <iostream>
int main(int argc,char **argv){
  nlohmann::json result;
  try{
    if(argc!=3)throw std::runtime_error("pin path and expected SHA required");
    const auto pin=formal_owned::read_pinned(argv[1],argv[2]);
    m4_owned::RecorderProcessPin recorder(pin,pin.at("run_id"),pin.at("contract_sha256"));
    result={{"accepted",true},{"process_evidence",recorder.process_evidence()},
      {"full_manifest_exists",std::filesystem::exists(recorder.path())},{"recording_ready",false}};
  }catch(const std::exception &e){result={{"accepted",false},{"reason",e.what()}};}
  result["control_API_calls"]=0;result["ROS_initialized"]=false;std::cout<<result.dump()<<std::endl;
}
