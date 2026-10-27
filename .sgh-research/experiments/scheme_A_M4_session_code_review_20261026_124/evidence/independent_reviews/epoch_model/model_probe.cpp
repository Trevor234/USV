#define main archived_component_main
#include "/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_n4_f6_impl_20261025_108/implementation/test_f6_model_transaction.cpp"
#undef main
int main(){
 Json result;
 {
  f6::ModelTransactionSolver w(f6::Bounds{});
  bool reg=w.register_version(0,make_p_global(params_m1()));
  auto out=w.solve(0,state_tick(0),ref_tick(0));
  AcadosBackend fresh(params_m1());
  auto [u,info]=fresh.solve(state_tick(0),ref_tick(0));
  result["generation_zero_without_commit"]={{"registered",reg},{"commits",w.stats().commits},{"executed",out.executed},{"finite",out.finite},{"fresh_m1_success",info.success},{"u_diff_vs_declared_m1",(out.u-u).cwiseAbs().maxCoeff()}};
 }
 {
  f6::ModelTransactionSolver w(f6::Bounds{}); auto pg=make_p_global(params_m0());pg[0]=std::numeric_limits<double>::quiet_NaN();
  result["nonfinite_registration_accepted"]=w.register_version(9,pg);
 }
 std::cout<<result.dump(2)<<'\n';
}
