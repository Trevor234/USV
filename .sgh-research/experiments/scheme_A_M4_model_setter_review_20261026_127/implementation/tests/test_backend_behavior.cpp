// SPDX-License-Identifier: MIT
// Same harness, separately linked against the three freshly compiled backends.
#include "usv_mpc_cpp/acados_backend.hpp"
#include <acados_c/ocp_nlp_interface.h>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <nlohmann/json.hpp>
using namespace usv_mpc;
using Json=nlohmann::json;
enum class Hook {normal,solve_error,solve_throw,solve_nonfinite,setter_error,observe_nonfinite};
Hook hook=Hook::normal;
int capsule_created=0,graph_freed=0,capsule_freed=0,solve_boundaries=0,real_solves=0;
Json setters=Json::array();
extern "C" usv_dyn_nmpc_solver_capsule *__real_usv_dyn_nmpc_acados_create_capsule();
extern "C" int __real_usv_dyn_nmpc_acados_free(usv_dyn_nmpc_solver_capsule*);
extern "C" int __real_usv_dyn_nmpc_acados_free_capsule(usv_dyn_nmpc_solver_capsule*);
extern "C" int __real_usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies(usv_dyn_nmpc_solver_capsule*,double*,int);
extern "C" int __real_usv_dyn_nmpc_acados_solve(usv_dyn_nmpc_solver_capsule*);
uint64_t bits(double x){uint64_t v;std::memcpy(&v,&x,sizeof(v));return v;}
extern "C" usv_dyn_nmpc_solver_capsule *__wrap_usv_dyn_nmpc_acados_create_capsule(){++capsule_created;return __real_usv_dyn_nmpc_acados_create_capsule();}
extern "C" int __wrap_usv_dyn_nmpc_acados_free(usv_dyn_nmpc_solver_capsule*c){++graph_freed;return __real_usv_dyn_nmpc_acados_free(c);}
extern "C" int __wrap_usv_dyn_nmpc_acados_free_capsule(usv_dyn_nmpc_solver_capsule*c){++capsule_freed;return __real_usv_dyn_nmpc_acados_free_capsule(c);}
extern "C" int __wrap_usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies(usv_dyn_nmpc_solver_capsule*c,double*p,int n){
 Json words=Json::array();bool finite=true;for(int i=0;i<n;++i){words.push_back(bits(p[i]));finite &= std::isfinite(p[i]);}
 setters.push_back({{"count",n},{"bits",words},{"finite",finite}});
 // Generated create bootstraps mass=30 before the reviewed constructor applies
 // its registered mass=14.2. Fault only that latter boundary, never bootstrap.
 if(hook==Hook::setter_error&&n==30&&p[0]!=30.0)return 17;
 if(hook==Hook::observe_nonfinite&&!finite)return 0; // never feed the observation probe to native precompute
 return __real_usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies(c,p,n);
}
extern "C" int __wrap_usv_dyn_nmpc_acados_solve(usv_dyn_nmpc_solver_capsule*c){
 ++solve_boundaries;if(hook==Hook::solve_error)return 7;
 if(hook==Hook::solve_throw)throw std::runtime_error("controlled_boundary_exception");
 ++real_solves;int status=__real_usv_dyn_nmpc_acados_solve(c);
 if(hook==Hook::solve_nonfinite){double u[2]={std::numeric_limits<double>::quiet_NaN(),0};
  ocp_nlp_out_set(usv_dyn_nmpc_acados_get_nlp_config(c),usv_dyn_nmpc_acados_get_nlp_dims(c),usv_dyn_nmpc_acados_get_nlp_out(c),usv_dyn_nmpc_acados_get_nlp_in(c),0,"u",u);}
 return status;
}
Json matrix(const Eigen::MatrixXd&m){Json a=Json::array();for(int c=0;c<m.cols();++c)for(int r=0;r<m.rows();++r)a.push_back(m(r,c));return {{"rows",m.rows()},{"cols",m.cols()},{"values",a}};}
Eigen::MatrixXd reference(int k){Eigen::MatrixXd ref(6,21);for(int j=0;j<21;++j)ref.col(j)<<.05*.2*(k+j),0,0,.05,0,0;return ref;}
Vector6d state(int k){Vector6d x;x<<.05*.2*k+.02,0,.03,.045,0,0;return x;}
Json row(AcadosBackend&w,int k){auto[u,info]=w.solve(state(k),reference(k));
 return {{"k",k},{"u",std::vector<double>{u[0],u[1]}},{"success",info.success},{"backend",info.backend},{"error",info.error},
 {"X",matrix(info.X_pred)},{"U",matrix(info.U_pred)},{"trajectory",matrix(w.get_predicted_trajectory())}};}
int main(int argc,char**argv){
 if(argc!=3||std::filesystem::exists(argv[2]))return 3;std::filesystem::create_directories(argv[2]);
 std::string id=argv[1];MpcParams p;Json rows=Json::array();bool constructed=false;std::string exception,exception_type;
 if(id=="CUSTOM_MODEL"){p.hydro.mass=15;p.hydro.Xu=-2.4;p.hydro.Nr=-4.4;}
 if(id=="BAD_N")p.N=19;if(id=="BAD_DT")p.dt=.1;
 if(id=="NEGATIVE_WEIGHT")p.Q_diag[0]=-1;
 if(id=="NAN_WEIGHT")p.Q_diag[0]=std::numeric_limits<double>::quiet_NaN();
 if(id=="SETTER_ERROR")hook=Hook::setter_error;
 if(id=="NONFINITE_HYDRO"){p.hydro.mass=std::numeric_limits<double>::quiet_NaN();hook=Hook::observe_nonfinite;}
 try{
  AcadosBackend w(p);constructed=true;
  if(id=="COLD"||id=="CUSTOM_MODEL")rows.push_back(row(w,0));
  else if(id=="WARM"||id=="APPLIED_ANCHOR"){for(int k=0;k<8;++k){rows.push_back(row(w,k));if(id=="APPLIED_ANCHOR")w.set_applied_control({.5,.45});}}
  else if(id=="RESET"){for(int k=0;k<4;++k)rows.push_back(row(w,k));w.reset_warmstart();rows.push_back(row(w,4));}
  else if(id=="FAIL_COLD"){hook=Hook::solve_error;rows.push_back(row(w,0));}
  else if(id=="FAIL_WARM_EXHAUST"){for(int k=0;k<3;++k)rows.push_back(row(w,k));hook=Hook::solve_error;for(int k=3;k<25;++k)rows.push_back(row(w,k));hook=Hook::normal;rows.push_back(row(w,25));hook=Hook::solve_error;rows.push_back(row(w,26));}
  else if(id=="NONFINITE_SOLUTION"){rows.push_back(row(w,0));hook=Hook::solve_nonfinite;rows.push_back(row(w,1));hook=Hook::normal;rows.push_back(row(w,2));}
  else if(id=="SOLVE_EXCEPTION"){rows.push_back(row(w,0));hook=Hook::solve_throw;rows.push_back(row(w,1));hook=Hook::normal;rows.push_back(row(w,2));}
  else if(id=="APPLIED_INVALID"){rows.push_back(row(w,0));try{w.set_applied_control({100,0});}catch(const std::out_of_range&e){exception=e.what();exception_type="out_of_range";}rows.push_back(row(w,1));}
 }catch(const std::invalid_argument&e){exception=e.what();exception_type="invalid_argument";}
 catch(const std::runtime_error&e){exception=e.what();exception_type="runtime_error";}
 Json result={{"case",id},{"constructed",constructed},{"exception",exception},{"exception_type",exception_type},{"rows",rows},
 {"setter_calls",setters},{"capsule_created",capsule_created},{"graph_freed",graph_freed},{"capsule_freed",capsule_freed},
 {"solve_boundaries",solve_boundaries},{"real_solves",real_solves},{"controlled_boundary_injection",id=="FAIL_COLD"||id=="FAIL_WARM_EXHAUST"||id=="SOLVE_EXCEPTION"||id=="NONFINITE_SOLUTION"||id=="SETTER_ERROR"||id=="NONFINITE_HYDRO"},
 {"stage_qualified",false},{"ROS_initialized",false}};
 std::ofstream f(std::filesystem::path(argv[2])/"result.json");f<<result.dump(2)<<'\n';return 0;
}
