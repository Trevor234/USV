#include "p1_diag_sink.hpp"
#include <iostream>
#include <memory>
struct D{unsigned sequence;};
struct P{std::atomic<unsigned> picked{0},calls{0};std::atomic<bool> release{false};void publish(const D&){++picked;while(!release.load())std::this_thread::yield();++calls;}};
int main(){auto p=std::make_shared<P>();p1::Witness w(true);p1::DiagSink<D,std::shared_ptr<P>> s("/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_session_code_review_20261026_124/evidence/replay01/t3/sticky_source.jsonl",1,p,&w);bool seed=s.add({{"type","seed"}},D{0});while(!p->picked.load())std::this_thread::yield();bool queued=s.add({{"type","queued"}},D{1});bool overflow=s.add({{"type","overflow"}},D{2});bool failed=s.failed();p->release=true;while(p->calls.load()!=2)std::this_thread::yield();bool after=s.add({{"type","after_overflow_and_drain"}},D{3});s.close();w.close_after_join();std::cout<<nlohmann::json{{"seed",seed},{"queued",queued},{"overflow_add",overflow},{"failed_sticky",failed&&s.failed()},{"add_after_failed_and_drained",after}}.dump()<<'\n';return 0;}
