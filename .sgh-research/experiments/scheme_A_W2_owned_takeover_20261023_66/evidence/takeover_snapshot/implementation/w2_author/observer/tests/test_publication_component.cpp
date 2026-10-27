// SPDX-License-Identifier: MIT
#include "publication_result_v1.hpp"
#include <nlohmann/json.hpp>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using Json=nlohmann::json;
using namespace p1::publication;
int assertions=0;
Json cases=Json::array();
void check(bool ok,const char *why){++assertions;if(!ok)throw std::runtime_error(why);}
void close(double actual,double expected){check(std::abs(actual-expected)<1e-8,"numeric expectation");}
p1::Anchor initial(){p1::Anchor a;a.known={true,true};a.n={0,0};a.time={1000000000,1000000000};a.seq={3,7};return a;}
struct Probe {
  p1::Anchor anchor=initial();
  std::array<int64_t,4> times{1200000000,1200001000,1200002000,1200003000};
  std::array<bool,2> throws{};
  size_t clock_index=0;
  int invalidations=0;
  std::vector<std::string> events;
  Json history=Json::array();
  PairResult run(p1::Command command={8,8},Policy policy={}){
    const auto old=anchor;
    return publish_pair(command,old,policy,[&]{return times.at(clock_index++);},
      [&](int ch,int64_t start){events.push_back("begin"+std::to_string(ch));check(start==times[ch*2],"captured actual start");},
      [&](int ch,double n){events.push_back("send"+std::to_string(ch));check(n==command[ch],"exact requested value");if(throws[ch])throw std::runtime_error("injected local send failure");},
      [&](int ch,const CallResult &r){
        events.push_back("commit"+std::to_string(ch));apply_channel_result(anchor,ch,command[ch],r);
        if(r.returned)history.push_back({{"channel",ch},{"n",anchor.n[ch]},{"sequence",anchor.seq[ch]},{"start_ns",anchor.time[ch]}});
        else ++invalidations;
      });
  }
};
void save(const char *name,const Probe &p,const PairResult &r){
  cases.push_back({{"case",name},{"passed",true},{"events",p.events},{"anchor_n",p.anchor.n},
    {"anchor_known",p.anchor.known},{"anchor_sequence",p.anchor.seq},{"anchor_start_ns",p.anchor.time},
    {"history",p.history},{"injected_failure_invalidations",p.invalidations},{"rho_available",r.rho_available},
    {"span_exceeded",r.span_exceeded},{"gap_exceeded",r.gap_exceeded},{"rate_exceeded",r.rate_exceeded},
    {"local_results",Json::array({{{"returned",r.calls[0].returned},{"start",r.calls[0].start_ns},{"end",r.calls[0].end_ns}},
                                {{"returned",r.calls[1].returned},{"start",r.calls[1].start_ns},{"end",r.calls[1].end_ns}}})}});
}

void success(){
  Probe p;auto r=p.run();
  check(p.events==std::vector<std::string>({"begin0","send0","commit0","begin1","send1","commit1"}),"left commit before right start");
  check(p.anchor.known==std::array<bool,2>{true,true}&&p.anchor.n==p1::Command{8,8},"both calls update their own values");
  check(p.anchor.seq==std::array<uint64_t,2>{4,8},"independent per-side sequence");
  check(p.anchor.time==std::array<int64_t,2>{1200000000,1200002000},"start, not end/planned tick, is anchor");
  check(r.rho_available&&!r.timing_failed()&&p.history.size()==2,"normal pair facts");save("both_returned_per_side_actual_starts",p,r);
}
void partial(){
  for(int failed=0;failed<2;++failed){
    Probe p;p.anchor.n={25,-25};p.throws[failed]=true;auto r=p.run({9,-9});int ok=1-failed;
    check(p.events.size()==6,"right attempted even after left fails");
    check(!p.anchor.known[failed]&&p.anchor.known[ok],"only failed side loses authority");
    check(p.anchor.n[failed]==(failed?-25:25)&&p.anchor.time[failed]==1000000000,"failed side retains numeric receipt as non-authoritative");
    check(p.anchor.seq[failed]==(failed?7u:3u),"failed call does not increment successful sequence");
    check(p.anchor.n[ok]==(ok?-9:9)&&p.anchor.time[ok]==p.times[ok*2],"successful side cannot be rolled back");
    check(p.invalidations==1&&!r.rho_available&&r.calls[failed].end_ns>r.calls[failed].start_ns,"failure has actual end receipt");
    auto u=p1::fallback(p.anchor,1250000000,1100000000,p1::Limits{},true);
    check(u[failed]==0,"unknown side fallback does not use its stale numeric force");
    check(std::abs(u[ok])<9&&std::abs(u[ok])>4.99,"known side slopes from successful API start");
    save(failed?"left_success_right_failed":"left_failed_right_still_attempted",p,r);
  }
  Probe p;p.throws={true,true};auto r=p.run();check(!p.anchor.known[0]&&!p.anchor.known[1]&&p.history.empty(),"both failed no successful history");
  check(p.anchor.seq==std::array<uint64_t,2>{3,7}&&p.invalidations==2,"both failed do not fabricate successes");save("both_failed",p,r);
}
void actual_time_rate(){
  Probe p;p.anchor.time[1]=1100000000;auto r=p.run({16,16});
  check(!r.rate_exceeded[0]&&r.rate_exceeded[1]&&!r.rho_available,"right actual interval is 100ms, not nominal 200ms");
  check(p.anchor.known[1]&&p.anchor.n[1]==16,"post-call rate violation cannot undo successful call");save("per_side_actual_spacing_rate",p,r);
  Probe q;auto s=q.run({16.000001,16});check(s.rate_exceeded[0]&&!s.rate_exceeded[1],"amplitude increment boundary");save("rate_boundary_exceeded",q,s);
}
void timing(){
  for(int extra=0;extra<2;++extra){
    Probe p;p.times={1200000000,1200001000,1200002000,1205000000+extra};auto r=p.run();
    check(r.span_exceeded==bool(extra),"5ms span equality remains inclusive");
    check(p.anchor.known[0]&&p.anchor.known[1]&&r.rho_available,"span diagnostic separate from successful anchors/rate availability");
    save(extra?"span_one_ns_over":"span_exact_5ms",p,r);
    Probe q;q.anchor.time[1]=1000002000;q.times={1240000000+extra,1240001000+extra,1240002000+extra,1240003000+extra};auto s=q.run();
    check(s.gap_exceeded[0]==bool(extra)&&s.gap_exceeded[1]==bool(extra),"240ms actual gap boundary");
    check(s.rho_available==!bool(extra),"gap diagnostic invalidates rate availability");save(extra?"gap_one_ns_over":"gap_exact_240ms",q,s);
  }
  Probe p;p.anchor.known[0]=false;auto r=p.run();check(p.anchor.known[0]&&!r.rho_available,"new success does not prove prior unknown interval");save("unknown_previous_anchor",p,r);
}
void holds(){
  p1::Limits limits;p1::Anchor a=initial();a.n={25,-25};const int64_t accepted=1000000000;
  Json trace=Json::array();
  for(int miss=1;miss<=5;++miss){
    int64_t now=accepted+miss*200000000LL;
    auto command=p1::fallback(a,now,accepted,limits,false);
    close(command[0],miss<=3?25:miss==4?9:0);
    check(p1::command_check(command,a,now,limits).empty(),"every miss follows actual-anchor slope");
    Probe p;p.anchor=a;p.times={now,now+100,now+200,now+300};auto r=p.run(command);a=p.anchor;
    trace.push_back({{"miss",miss},{"command",command},{"accepted_time_still",accepted},{"anchor_time",a.time},{"rho_available",r.rho_available}});
  }
  cases.push_back({{"case","five_misses_hold_boundary_and_no_lifetime_refresh"},{"passed",true},{"trace",trace}});
  a=initial();a.n={25,-25};auto invalid=p1::fallback(a,1200000000,1100000000,limits,true);
  check(invalid==p1::Command{9,-9},"source failure bypasses hold immediately");
  cases.push_back({{"case","invalid_source_bypasses_hold_with_rate_limited_ramp"},{"passed",true},{"command",invalid}});
}
void shutdown(){
  auto partial=shutdown_result(true,true,{0,0},{true,false},1500000000,1000000000,2500000000);
  check(partial.exit_tick&&partial.zero_requested&&!partial.zero_target_published&&!partial.grace_exceeded,"requested zero exit is not successful zero-pair publication");
  auto good=shutdown_result(true,true,{0,0},{true,true},1500000000,1000000000,2500000000);
  check(good.exit_tick&&good.zero_target_published,"both returned zero calls have separate publication fact");
  auto shadow=shutdown_result(true,false,{0,0},{true,true},1500000000,1000000000,2500000000);
  check(shadow.exit_tick&&!shadow.zero_target_published,"shadow/no-output cannot assert zero publication");
  auto before=shutdown_result(true,true,{1,-1},{true,true},3499999999,1000000000,2500000000);
  auto at=shutdown_result(true,true,{1,-1},{true,true},3500000000,1000000000,2500000000);
  check(!before.exit_tick&&at.exit_tick&&at.grace_exceeded&&!at.zero_target_published,"finite close grace boundary");
  check(!shutdown_result(false,true,{0,0},{true,true},3500000000,1000000000,2500000000).exit_tick,"non-stopping zero does not exit");
  cases.push_back({{"case","shutdown_zero_request_success_and_grace_are_separate"},{"passed",true},
                   {"partial_zero_exit",partial.exit_tick},{"partial_zero_published",partial.zero_target_published},
                   {"both_zero_published",good.zero_target_published},{"grace_exit_with_nonzero",at.exit_tick},
                   {"plant_hold_end_known",false}});
}
} // namespace

int main(int argc,char **argv){
  try{
    check(argc==2,"one fresh output file required");check(!std::filesystem::exists(argv[1]),"do not overwrite Native evidence");
    success();partial();actual_time_rate();timing();holds();shutdown();
    Json output={{"schema","publication-component-native/v1"},{"passed",true},{"cases",cases},{"case_count",cases.size()},
      {"assertions",assertions},{"ROS_context_created",false},{"actuator_endpoints_created",false},
      {"send_results_are_injected_component_events",true},{"plant_acceptance_observed",false},
      {"stage_qualified",false},{"execute_qualified",false},{"research_conclusion",false}};
    std::ofstream file(argv[1]);file<<output.dump(2)<<'\n';check(bool(file),"Native evidence stream");
    std::cout<<"checks="<<output.at("assertions").get<int>()<<" passed cases="<<cases.size()<<'\n';return 0;
  }catch(const std::exception &e){std::cerr<<"Native failure: "<<e.what()<<'\n';return 2;}
}
