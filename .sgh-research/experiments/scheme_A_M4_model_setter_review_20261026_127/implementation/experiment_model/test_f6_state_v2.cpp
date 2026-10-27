// Serial wrapper state tests plus the unchanged finite M0/M1 numeric controls.
#define main original_f6_main
#include "test_f6_model_transaction.cpp"
#undef main
#include <atomic>
#include <limits>
#include <thread>

std::atomic<uint64_t> c_entries{0};
extern "C" int __real_usv_dyn_nmpc_acados_solve(usv_dyn_nmpc_solver_capsule *);
extern "C" int __wrap_usv_dyn_nmpc_acados_solve(usv_dyn_nmpc_solver_capsule *c) {
  ++c_entries;
  return __real_usv_dyn_nmpc_acados_solve(c);
}
using State = f6::TransactionState;
auto pg0() { return make_p_global(params_m0()); }
void denied(f6::ModelTransactionSolver &w, uint64_t g, const std::string &reason) {
  const auto n=c_entries.load();auto result=w.solve(g,state_tick(0),ref_tick(0));
  check(!result.executed&&result.reject==reason,"reject_"+reason,result.reject);
  check(c_entries.load()==n,"real_C_entry_count_unchanged_"+reason);
}
void state_case(const std::string &id) {
  if(id=="F6V-01-UNCOMMITTED"){
    f6::ModelTransactionSolver w({});require(w.register_version(1,pg0()),"register");
    denied(w,1,"model_not_committed");
    check(!w.has_committed()&&w.state()==State::UNCOMMITTED&&w.stats().setter_calls==0,"uncommitted_state_no_setter");
  }else if(id=="F6V-02-GEN-ZERO"){
    f6::ModelTransactionSolver w({});check(!w.register_version(0,pg0()),"zero_generation_rejected");
    check(!w.prepare(0),"zero_cannot_prepare");denied(w,0,"model_not_committed");
  }else if(id=="F6V-03-STALE"){
    f6::ModelTransactionSolver w({});init_m0(w);require(w.register_version(2,make_p_global(params_m1()))&&w.prepare(2)&&w.commit(),"M1");
    denied(w,1,"stale_stamp");denied(w,999,"unknown_generation");
  }else if(id=="F6V-04-NAN"){
    f6::ModelTransactionSolver w({});auto p=pg0();p[0]=std::numeric_limits<double>::quiet_NaN();
    check(!w.register_version(1,p),"nan_model_refused");p=pg0();p[29]=std::numeric_limits<double>::infinity();
    check(!w.register_version(2,p),"inf_model_refused");
    check(!w.prepare(1)&&!w.prepare(2)&&w.stats().setter_calls==0,"invalid_models_never_applied");
  }else if(id=="F6V-05-IMMUTABLE"){
    f6::ModelTransactionSolver w({});auto p=pg0();require(w.register_version(1,p),"register");
    check(w.register_version(1,p),"identical_registration_idempotent");p[0]+=1;
    check(!w.register_version(1,p),"same_generation_content_rewrite_refused");
  }else if(id=="F6V-06-PREPARING"){
    f6::ModelTransactionSolver w({});init_m0(w);require(w.prepare(1),"prepare");
    denied(w,1,"solve_during_prepare");check(w.abort()&&w.state()==State::READY,"abort_restores_ready");
  }else if(id=="F6V-07-LEGAL"){
    run_f6_1();run_f6_5(); // bounded fixed inputs and 1e-8 tolerance, installed-library comparison
  }else if(id=="F6V-08-WRONG-THREAD"){
    f6::ModelTransactionSolver w({});const auto n=c_entries.load();bool refused=false,query_refused=false;
    std::thread other([&]{
      bool a=!w.register_version(1,pg0()),b=!w.prepare(1),c=!w.commit(),d=!w.abort();
      auto result=w.solve(1,state_tick(0),ref_tick(0));
      refused=a&&b&&c&&d&&!result.executed&&result.reject=="wrong_owner_thread";
      try{(void)w.state();}catch(const std::logic_error&){query_refused=true;}
    });other.join();
    check(refused&&query_refused,"wrong_thread_all_operations_refused_before_state");
    check(w.stats().offered==0&&w.stats().setter_calls==0&&c_entries.load()==n&&w.state()==State::UNCOMMITTED,"wrong_thread_zero_mutable_state_and_C_entry");
  }else if(id=="F6V-09-FAULTED-SET"||id=="F6V-10-FAULTED-RESET"){
    bool fail=false;f6::TransactionApi api;
    if(id=="F6V-09-FAULTED-SET")api.set_global=[&](auto*c,double*p,int n){
      const int real=usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies(c,p,n);return fail?77:real;};
    else api.reset=[&](auto*c,int reset){const int real=usv_dyn_nmpc_acados_reset(c,reset);return fail?78:real;};
    f6::ModelTransactionSolver w({},api);init_m0(w);fail=true;
    require(w.register_version(2,make_p_global(params_m1()))&&w.prepare(2),"prepare M1");
    check(!w.commit(),"injected_api_failure_refuses_commit");
    check(w.state()==State::FAULTED&&!w.has_committed()&&w.current_generation()==1&&w.stats().commits==1,"new_identity_not_published_after_failure");
    check(!w.abort()&&!w.prepare(1)&&!w.commit()&&!w.register_version(3,pg0()),"faulted_instance_has_no_recovery_bypass");
    denied(w,1,"transaction_faulted");denied(w,2,"transaction_faulted");
  }else if(id=="F6V-11-ABORT-PREPARED"){
    f6::ModelTransactionSolver w({});require(w.register_version(1,pg0())&&w.prepare(1),"prepare uncommitted");
    check(w.abort()&&w.state()==State::UNCOMMITTED&&w.stats().setter_calls==0,"abort_uncommitted_before_capsule");
    require(w.prepare(1)&&w.commit(),"commit");require(w.register_version(2,make_p_global(params_m1()))&&w.prepare(2),"prepare M1");
    auto n=w.stats().setter_calls;
    check(w.abort()&&w.state()==State::READY&&w.current_generation()==1&&w.stats().setter_calls==n,"abort_ready_preserves_current_and_setter_count");
    check(w.solve(1,state_tick(0),ref_tick(0)).executed,"old_committed_model_still_solves_after_cancel");
  }else if(id=="F6V-12-INPUT"){
    f6::ModelTransactionSolver w({});init_m0(w);auto n=c_entries.load();auto x=state_tick(0);auto ref=ref_tick(0);
    check(w.solve(1,x,ref.leftCols(20)).reject=="reference_shape","reference_shape_refused");
    x(0)=std::numeric_limits<double>::quiet_NaN();check(w.solve(1,x,ref).reject=="nonfinite_state_or_reference","nan_state_refused");
    x=state_tick(0);ref(0,0)=std::numeric_limits<double>::infinity();check(w.solve(1,x,ref).reject=="nonfinite_state_or_reference","inf_reference_refused");
    check(c_entries.load()==n,"bad_inputs_no_real_C_solve");
  }else if(id=="F6V-13-API-EXCEPTION"){
    f6::TransactionApi api;api.set_global=[](auto*,double*,int)->int{throw std::runtime_error("adapter only");};
    f6::ModelTransactionSolver w({},api);require(w.register_version(1,pg0())&&w.prepare(1),"prepare");
    check(!w.commit()&&w.state()==State::FAULTED,"adapter_exception_faults_conservatively");denied(w,1,"transaction_faulted");
  }else require(false,"unknown state case");
}
int main(int argc,char**argv){
  if(argc==3&&std::string(argv[1]).rfind("F6-",0)==0)return original_f6_main(argc,argv);
  try{
    require(argc==3,"case + create-only output required");std::filesystem::path out(argv[2]);
    require(!std::filesystem::exists(out),"fresh output");std::filesystem::create_directories(out);
    state_case(argv[1]);Json result={{"case",argv[1]},{"passed",all_ok},{"assertions",asserts},
      {"real_C_entries",c_entries.load()},{"adapter_failure_is_native_failure",false},
      {"comparison_scope","fixed inputs vs freshly compiled checked_init source snapshot; generated C O1, C++ O2; no production landing"},
      {"stage_qualified",false},{"ROS_context_created",false}};
    std::ofstream f(out/"result.json");f<<result.dump(2)<<'\n';return all_ok?0:2;
  }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 3;}
}
