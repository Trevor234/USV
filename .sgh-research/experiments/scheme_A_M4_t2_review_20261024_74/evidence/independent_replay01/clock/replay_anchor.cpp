// Offline replay of original per-side API facts through the frozen policy.
// No ROS headers, endpoints, initialization, clocks, syscalls, or live process access.
#include "/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation/t2_author_rev8/observer/src/shadow/owned_execution_policy_native_v1.hpp"
#include <fstream>
#include <iostream>
#include <vector>

int main() {
  using nlohmann::json;
  const std::string root="/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation/runs/T2A_14/";
  auto read=[](const std::string &path){json v;std::ifstream(path)>>v;return v;};
  const auto reg=read(root+"registration_copy.json"),contract=read(reg.at("contract")),grant=read(root+"regulator/grant.json");
  std::vector<json> decisions;int64_t origin=0;std::ifstream input(root+"regulator/source.jsonl");std::string line;
  while(std::getline(input,line)){auto r=json::parse(line);if(r.at("type")=="decision")decisions.push_back(r);if(r.at("type")=="owned_execute_grant_accepted")origin=r.at("origin_ns");}
  p1::owned_execution::OutputAuthority authority(contract,grant.at("context"),grant.at("context"),origin);
  p1::Anchor history_anchor{};
  std::vector<int64_t> history_sim;
  json output=json::array();
  for(const auto &d:decisions){
    const auto command=d.at("final_n").get<p1::Command>();
    std::array<p1::publication::CallResult,2> calls;
    json regressions=json::array();
    for(int side=0;side<2;++side){
      calls[side]={d.at("publish_start_ns")[side],d.at("publish_end_ns")[side],d.at("publish_success")[side]};
      // Same apply_channel_result() used by the real publish completion path.
      p1::publication::apply_channel_result(history_anchor,side,command[side],calls[side]);
      if(calls[side].returned){
        int64_t sim=d.at("publish_sim_ns")[side];
        // Exact history/anchor branch at regulator_owned_execute.cpp:843.
        if(!history_sim.empty()&&sim<history_sim.back()){
          regressions.push_back({{"side",side},{"previous_sim_ns",history_sim.back()},{"new_sim_ns",sim},{"regression_ns",history_sim.back()-sim}});
          history_sim.clear();history_anchor.known={false,false};
        }else history_sim.push_back(sim);
      }
    }
    const bool tick_ok=authority.tick(d.at("start_ns"));
    const std::string kind=d.at("accepted").get<bool>()?"accepted":d.at("reason")=="shutdown"?"shutdown":!authority.initialized()?"bootstrap":authority.last_accepted_ns()==0?"waiting":"fallback";
    const auto observation=authority.record_pair(command,calls,kind,d.at("accepted").get<bool>()?d.at("activation_commit_ns").get<int64_t>():0);
    const auto &actual=authority.anchor();
    output.push_back({{"sequence",d.at("sequence")},{"kind",kind},{"tick_ok",tick_ok},{"authority_terminal",authority.terminal()},
      {"record_pair_command_invalid",observation.command_invalid},{"history_regressions",regressions},
      {"replayed_history_known",history_anchor.known},{"Source_history_known",d.at("anchor_known")},
      {"replayed_history_seq",history_anchor.seq},{"Source_history_seq",d.at("anchor_sequence")},
      {"authority_known",actual.known},{"authority_seq",actual.seq},{"authority_n",actual.n},{"authority_time",actual.time},
      {"authority_equals_history",actual.known==history_anchor.known&&actual.n==history_anchor.n&&actual.time==history_anchor.time&&actual.seq==history_anchor.seq}});
  }
  std::cout<<output.dump(2)<<"\n";
}
