// SPDX-License-Identifier: MIT
#include "p1_diag_sink.hpp"
#include <filesystem>
#include <iostream>
#include <memory>
#include <vector>
struct Decision {uint64_t sequence;};
struct Publisher {std::atomic<unsigned> calls{0};void publish(const Decision &){++calls;}};
using Sink=p1::DiagSink<Decision,std::shared_ptr<Publisher>>;
using Json=nlohmann::json;
int checks=0;
void require(bool v,const char *why){++checks;if(!v)throw std::runtime_error(why);}
std::vector<Json> rows(const std::filesystem::path &p){std::ifstream f(p);std::vector<Json> r;std::string line;while(std::getline(f,line))r.push_back(Json::parse(line));return r;}
void paused(Sink &s){const auto until=p1::diag_now()+1000000000;while(s.v1_snapshot().at("state")!=2&&p1::diag_now()<until)std::this_thread::sleep_for(std::chrono::milliseconds(1));require(s.v1_snapshot().at("state")==2,"bounded empty-queue gate acknowledged");}
int main(int argc,char **argv){try{
  require(argc==2,"fresh output directory required");std::filesystem::path out(argv[1]);require(!std::filesystem::exists(out),"do not overwrite Native evidence");std::filesystem::create_directory(out);
  Json cases=Json::array();
  {auto pub=std::make_shared<Publisher>();p1::Witness w(true);Sink s((out/"disabled.jsonl").string(),512,pub,&w);
   require(!s.arm_v1_saturation(),"disabled cannot arm");require(s.add({{"type","decision"},{"sequence",1}},Decision{1}),"disabled normal enqueue");s.close();w.close_after_join();
   require(pub->calls==1&&!s.failed(),"disabled retains normal publication");auto data=rows(out/"disabled.jsonl");require(data.back()["normal_source_complete"]==true,"disabled complete accounting");cases.push_back({{"case","disabled_profile_preserves_normal_sink"},{"passed",true}});}
  {auto pub=std::make_shared<Publisher>();p1::Witness w(true);Sink s((out/"overflow.jsonl").string(),512,pub,&w,{},true);
   require(s.add({{"type","decision"},{"sequence",1}},Decision{1}),"first decision real enqueue");require(s.arm_v1_saturation(),"single arm");require(!s.arm_v1_saturation(),"second arm rejected");paused(s);
   require(pub->calls==1,"first decision actually emitted before gate");require(!s.add({{"type","decision"},{"sequence",2}},Decision{2}),"second real enqueue rejected at actual capacity");auto snapshot=s.v1_snapshot();
   require(snapshot["depth_at_rejection"]==512&&snapshot["filler_events"].get<int>()>0&&snapshot["filler_events"].get<int>()<=512,"bounded real queue population");
   require(snapshot["first_failure_at_this_decision"]==true&&snapshot["decision_sequence"]==2&&snapshot["state"]==3,"first failure identity recorded");
   require(s.failed()&&!s.arm_v1_saturation(),"terminal failure cannot rearm");s.close();w.close_after_join();auto data=rows(out/"overflow.jsonl");auto summary=data.back();
   require(pub->calls==1,"rejected decision not delivered to publisher");require(summary["dropped"]==1&&!summary["normal_source_complete"].get<bool>(),"failed normal accounting retained");
   require(summary["generated"].get<uint64_t>()==summary["emitted"].get<uint64_t>()+summary["dropped"].get<uint64_t>(),"generated emitted dropped balance");
   unsigned fills=0;for(const auto &r:data)if(r.value("type",std::string{})=="diagnostic_v1_queue_fill")++fills;
   require(fills==snapshot["filler_events"],"fill events really drained into Source");cases.push_back({{"case","real_bounded_queue_rejects_second_decision"},{"passed",true},{"snapshot",snapshot},{"summary",summary},{"injected_event_scope",true}});}
  {auto pub=std::make_shared<Publisher>();p1::Witness w(true);Sink s((out/"cancel.jsonl").string(),512,pub,&w,{},true);require(s.arm_v1_saturation(),"cancel case arm");paused(s);const auto begin=p1::diag_now();s.close();w.close_after_join();
   require(p1::diag_now()-begin<1000000000,"close cancels paused gate without hanging");require(s.v1_snapshot()["state"]==4&&!s.failed()&&pub->calls==0,"cancel does not fabricate failure or publish");cases.push_back({{"case","close_cancels_untriggered_gate"},{"passed",true}});}
  Json report={{"schema","V1-sink-native/v1"},{"passed",true},{"cases",cases},{"case_count",cases.size()},{"assertions",checks},{"ROS_context_created",false},{"actuator_endpoints_created",false},{"stage_qualified",false},{"execute_qualified",false},{"research_conclusion",false}};
  std::ofstream f(out/"result.json");f<<report.dump(2)<<'\n';require(bool(f),"evidence stream");std::cout<<"checks="<<report["assertions"]<<" passed cases="<<cases.size()<<'\n';return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
