#include "/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_rnw2_impl_20261025_112/implementation/t2_author/common/command_anchor_v2.hpp"
#include "/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_rnw2_impl_20261025_112/implementation/t2_author/observer/src/shadow/publication_result_v1.hpp"
#include <cassert>
#include <iostream>
int main(){
 c36::Owner owner{"run","boot","producer",std::string(64,'a'),1}; c36::CommandAnchor book(owner);
 c36::PairFeedback f{owner,1,{4,6},{c36::Call::succeeded,c36::Call::succeeded},{10,12},{11,13},14};
 assert(bool(book.observe(f))); assert(bool(book.open(15)));
 auto before=book.facts().anchor; p1::Version v{1,1,1,2,1}; assert(bool(book.change_version(v,16))); auto after=book.facts().anchor;
 assert(after.known==before.known&&after.n==before.n&&after.time==before.time&&after.seq==before.seq);
 std::cout << "change_version preserves actual anchor: PASS\n";
 auto newer_epoch=v;newer_epoch.epoch=2;auto bad=book.change_version(newer_epoch,17);assert(bad.reason=="version_time_or_epoch");std::cout<<"new epoch rejected: "<<bad.reason<<"\n";
 c36::FrozenJob job; const int64_t origin=1000000000;assert(bool(book.freeze(1,1,origin,origin+1,job)));assert(bool(book.ready(job,{4,6},origin+2)));assert(bool(book.cutoff(origin+p1::DEADLINE+1)));uint64_t token=0;assert(bool(book.activate(job,1,origin+p1::T,token)));auto newer_schedule=v;newer_schedule.schedule=3;auto active_reject=book.change_version(newer_schedule,origin+p1::T+1);assert(active_reject.reason=="version_change_not_permitted");std::cout<<"active transaction rejected: "<<active_reject.reason<<"\n";
 p1::Anchor history=before,authority=before;std::array<p1::publication::CallResult,2> calls{{{20,21,true},{22,23,true}}};
 p1::publication::apply_channel_result(history,0,4,calls[0]);history.known={false,false};p1::publication::apply_channel_result(history,1,6,calls[1]);for(int i=0;i<2;++i)p1::publication::apply_channel_result(authority,i,i?6:4,calls[i]);assert((history.known==std::array<bool,2>{false,true}));assert((authority.known==std::array<bool,2>{true,true}));assert(history.n==authority.n&&history.time==authority.time&&history.seq==authority.seq);std::cout<<"reset-between-real-channel-commits yields exact F/T known-only divergence: PASS\n";
 p1::Anchor early=before;early.known={false,false};for(int i=0;i<2;++i)p1::publication::apply_channel_result(early,i,i?6:4,calls[i]);assert(early.known==authority.known&&early.n==authority.n&&early.time==authority.time&&early.seq==authority.seq);std::cout<<"same epoch reset before both commits does not necessarily diverge: PASS\n";
}
