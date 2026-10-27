#define main archived_component_main
#include "/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2b_gen_impl_20261025_103/implementation/t2_author/observer/tests/test_scoped_epoch_v1.cpp"
#undef main
int main(){
 Json result;
 {
  ScopedEpoch w; Binding A=make_binding('A'),B=make_binding('B');
  auto stale=w.propose(A,TS1,target(),make_input());
  const bool first=w.commit(stale,1,1);
  w.invalidate_if_changed(B);w.mark_quiesced();
  auto fresh=w.propose(B,TS2,target(),make_input());
  const bool stale_commit=w.commit(stale,2,2);
  result["retired_proposal_replayed_into_uncommitted_generation"]={{"initial_commit",first},{"fresh_B_valid",fresh.valid},{"generation",w.generation()},{"stale_A_commit_accepted",stale_commit},{"anchor_is_A",w.anchor()&&w.anchor()->binding==A},{"ledger_A_retired",w.ledger().size()==1&&w.ledger()[0].binding==A}};
 }
 {
  ScopedEpoch w; Binding A=make_binding('A'),B=A; B.version[3]++;
  const bool first=w.commit(w.propose(A,TS1,target(),make_input()),1,1);
  w.invalidate_if_changed(B);w.mark_quiesced();
  auto p=w.propose(B,TS2,target(),make_input());
  result["same_fingerprints_new_schedule"]={{"initial_commit",first},{"proposal_valid",p.valid},{"opened_generation",w.generation()},{"same_path",A.path==B.path},{"same_profile",A.profile==B.profile}};
 }
 std::cout<<result.dump(2)<<'\n';
}
