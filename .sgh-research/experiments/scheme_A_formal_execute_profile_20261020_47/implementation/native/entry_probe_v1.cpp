// SPDX-License-Identifier: MIT
// Offline process, no ROS/solver/thread/physical output API.
#include "owned_execution_entry_v1.hpp"
#include <fstream>
#include <iostream>

using json=nlohmann::json;
static json load(const std::string & path){
  std::ifstream in(path,std::ios::binary);
  if(!in)throw std::runtime_error("contract unavailable");
  std::string text(65537,'\0');in.read(text.data(),text.size());text.resize(size_t(in.gcount()));
  return p1::parse_unique_contract(text);
}
static json state(const p1::owned_execution::OutputAuthority & a,int64_t now){
  const auto & anchor=a.anchor();
  return {{"initialized",a.initialized()},{"terminal",a.terminal()},{"business_permitted",a.business_permitted(now)},
    {"known",anchor.known},{"n",anchor.n},{"time",anchor.time},{"seq",anchor.seq},{"last_accepted_ns",a.last_accepted_ns()}};
}
int main(){
  std::string line;
  while(std::getline(std::cin,line)){
    json result;
    try{
      if(line.size()>65536)throw std::runtime_error("bounded request required");
      const auto r=p1::parse_unique_contract(line);const auto c=load(r.at("contract"));
      p1::owned_execution::context_gate(c,r.at("mode"),r.at("expected"),r.at("actual"));
      result={{"accepted",true},{"events",json::array()}};
      if(r.contains("steps")){
        p1::owned_execution::OutputAuthority authority(c,r.at("expected"),r.at("actual"),r.at("prepare_ns"));
        for(const auto & step:r.at("steps")){
          const std::string op=step.at("op");json event;
          if(op=="pair"){
            std::array<p1::publication::CallResult,2> calls;
            for(int i=0;i<2;++i){calls[i].start_ns=step.at("starts").at(i);calls[i].end_ns=step.at("ends").at(i);calls[i].returned=step.at("returned").at(i);}
            const auto observation=authority.record_pair(step.at("command").get<p1::Command>(),calls,step.at("reason"),step.value("activation_ns",int64_t(0)));
            event={{"initial_pair",observation.initial_pair},{"rho_available",observation.rho_available},{"both_returned",observation.both_returned},
              {"gap_exceeded",observation.gap_exceeded},{"span_exceeded",observation.span_exceeded},{"rate_exceeded",observation.rate_exceeded},
              {"command_invalid",observation.command_invalid},{"bootstrap_late",observation.bootstrap_late},
              {"state",state(authority,calls[1].end_ns+1)}};
          }else if(op=="tick"){
            const int64_t now=step.at("now");event={{"tick_ok",authority.tick(now)},{"state",state(authority,now)}};
          }else if(op=="fallback"){
            const int64_t now=step.at("now");event={{"command",authority.fallback_request(now,step.value("invalid",false))},{"state",state(authority,now)}};
          }else if(op=="shutdown"){
            const auto x=authority.shutdown(step.at("command").get<p1::Command>(),step.at("returned").get<std::array<bool,2>>(),step.at("now"),step.at("stop_start"));
            event={{"zero_requested",x.zero_requested},{"zero_target_published",x.zero_target_published},{"exit_tick",x.exit_tick},{"grace_exceeded",x.grace_exceeded}};
          }else throw std::runtime_error("unsupported step");
          result["events"].push_back(event);
        }
      }
    }catch(const std::exception & e){result={{"accepted",false},{"reason",e.what()}};}
    result["physical_execute_release_enabled"]=p1::physical_execute_release_enabled;
    result["physical_API_calls"]=0;
    std::cout<<result.dump(-1,' ',false,json::error_handler_t::replace)<<std::endl;
  }
}
