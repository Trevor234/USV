#include "p1_diag_sink.hpp"
#include <memory>
#include <filesystem>
#include <iostream>
struct Decision{unsigned sequence;};
struct Publisher{
 std::atomic<unsigned> picked{0},done{0};std::atomic<bool> release{false};
 void publish(const Decision&){++picked;auto deadline=p1::diag_now()+2000000000LL;
  while(!release&&p1::diag_now()<deadline)std::this_thread::yield();++done;}
};
template<class F>bool until(F predicate){auto deadline=p1::diag_now()+1000000000LL;
 while(!predicate()&&p1::diag_now()<deadline)std::this_thread::yield();return predicate();}
int main(int argc,char**argv){
 if(argc!=2)return 3;std::filesystem::path out(argv[1]);if(std::filesystem::exists(out))return 3;
 std::filesystem::create_directories(out);auto p=std::make_shared<Publisher>();p1::Witness witness(true);
 p1::DiagSink<Decision,std::shared_ptr<Publisher>> sink((out/"source.jsonl").string(),1,p,&witness);
 bool seed=sink.add({{"type","seed"}},Decision{0});bool entered=until([&]{return p->picked.load()==1;});
 bool queued=sink.add({{"type","queued"}},Decision{1});bool rejected=!sink.add({{"type","overflow"}},Decision{2});
 p->release=true;bool drained=until([&]{return p->done.load()==2;});
 bool after=sink.add({{"type","after_drain"}},Decision{3});sink.close();witness.close_after_join();
 bool sticky=sink.failed();bool ok=seed&&entered&&queued&&rejected&&drained&&after&&sticky;
 nlohmann::json result={{"passed",ok},{"seed",seed},{"entered",entered},{"queued",queued},{"overflow_rejected",rejected},
  {"drained",drained},{"post_drain_add",after},{"failed_sticky",sticky},{"ROS_initialized",false}};
 std::ofstream f(out/"result.json");f<<result.dump(2)<<'\n';return ok?0:2;
}
