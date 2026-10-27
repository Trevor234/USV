// SPDX-License-Identifier: MIT
// Real factory, AcadosBackend and (when enabled) CasadiBackend. Faults are at
// named C boundaries; they are not claims about an internal native failure.
#include "usv_mpc_cpp/mpc_solver.hpp"
#include "acados_solver_usv_dyn_nmpc.h"
#include <nlohmann/json.hpp>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <set>
#include <sstream>

using namespace usv_mpc;
using Json = nlohmann::json;
static bool setter_error = false, capsule_null = false;
static int allocated = 0, created = 0, graph_freed = 0, capsule_freed = 0;
static int native_solves = 0, reported_setter_failures = 0;
static Json setters = Json::array();
extern "C" usv_dyn_nmpc_solver_capsule *__real_usv_dyn_nmpc_acados_create_capsule();
extern "C" int __real_usv_dyn_nmpc_acados_free(usv_dyn_nmpc_solver_capsule *);
extern "C" int __real_usv_dyn_nmpc_acados_free_capsule(usv_dyn_nmpc_solver_capsule *);
extern "C" int __real_usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies(usv_dyn_nmpc_solver_capsule *, double *, int);
extern "C" int __real_usv_dyn_nmpc_acados_solve(usv_dyn_nmpc_solver_capsule *);
extern "C" usv_dyn_nmpc_solver_capsule *__wrap_usv_dyn_nmpc_acados_create_capsule()
{
  ++allocated;
  if (capsule_null) return nullptr;
  auto * c = __real_usv_dyn_nmpc_acados_create_capsule();
  if (c) ++created;
  return c;
}
extern "C" int __wrap_usv_dyn_nmpc_acados_free(usv_dyn_nmpc_solver_capsule * c)
{ ++graph_freed; return __real_usv_dyn_nmpc_acados_free(c); }
extern "C" int __wrap_usv_dyn_nmpc_acados_free_capsule(usv_dyn_nmpc_solver_capsule * c)
{ ++capsule_freed; return __real_usv_dyn_nmpc_acados_free_capsule(c); }
extern "C" int __wrap_usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies(
  usv_dyn_nmpc_solver_capsule * c, double * p, int n)
{
  bool finite = true;
  Json words = Json::array();
  for (int i=0; i<n; ++i) {
    std::uint64_t b; std::memcpy(&b, p+i, sizeof(b)); words.push_back(b);
    finite = finite && std::isfinite(p[i]);
  }
  setters.push_back({{"n",n},{"finite",finite},{"bits",words}});
  if (setter_error && n == 30 && p[0] != 30.0) {
    ++reported_setter_failures; return 17;
  }
  // Safety adapter for historical baseline characterization only. Nonfinite
  // data is never submitted to generated native precompute or solve.
  if (!finite) return 0;
  return __real_usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies(c,p,n);
}
extern "C" int __wrap_usv_dyn_nmpc_acados_solve(usv_dyn_nmpc_solver_capsule * c)
{ ++native_solves; return __real_usv_dyn_nmpc_acados_solve(c); }

Json matrix(const Eigen::MatrixXd & m)
{
  Json values = Json::array();
  for (int c=0; c<m.cols(); ++c) for (int r=0; r<m.rows(); ++r) values.push_back(m(r,c));
  return {{"rows",m.rows()},{"cols",m.cols()},{"values",values}};
}

int main(int argc, char ** argv)
{
  if (argc != 3 || std::filesystem::exists(argv[2])) return 3;
  const std::string id = argv[1];
  const std::set<std::string> known = {"NOMINAL","CUSTOM","SETTER_ERROR","CAPSULE_NULL",
    "BAD_N","BAD_DT","NAN_HYDRO","INF_HYDRO","NAN_WEIGHT","NEGATIVE_WEIGHT",
    "DIRECT_NOMINAL","DIRECT_NAN_HYDRO","DIRECT_INF_HYDRO"};
  if (!known.count(id)) return 4;
  MpcParams p;
  if (id=="CUSTOM") { p.hydro.mass=15; p.hydro.Xu=-2.4; p.hydro.Nr=-4.4; }
  if (id=="BAD_N") p.N=19;
  if (id=="BAD_DT") p.dt=.1;
  if (id.find("NAN_HYDRO")!=std::string::npos) p.hydro.mass=std::numeric_limits<double>::quiet_NaN();
  if (id.find("INF_HYDRO")!=std::string::npos) p.hydro.Xu=std::numeric_limits<double>::infinity();
  if (id=="NAN_WEIGHT") p.Q_diag[0]=std::numeric_limits<double>::quiet_NaN();
  if (id=="NEGATIVE_WEIGHT") p.Q_diag[0]=-1;
  setter_error = id=="SETTER_ERROR";
  capsule_null = id=="CAPSULE_NULL";
  const bool direct = id.rfind("DIRECT_",0)==0;
  Json rows=Json::array();
  bool constructed=false, available=true;
  std::string backend, exception, exception_type;
  try {
    std::unique_ptr<DynamicMpc> solver;
    if (direct) {
#ifdef USV_MPC_HAS_CASADI
      solver=make_casadi_dynamic_mpc(p);
#else
      available=false;
#endif
    } else solver=make_dynamic_mpc(p);
    if (solver) {
      constructed=true; backend=solver->backend();
      // Invalid-model observation is construction-only. Do not solve through
      // an invalid model even when the unchanged factory admits it.
      if (id.find("HYDRO")==std::string::npos && !(id=="SETTER_ERROR" && backend=="acados")) {
        for (int k=0; k<2; ++k) {
          Vector6d x; x<<.01*k+.02,0,.03,.045,0,0;
          Eigen::MatrixXd ref(6,p.N+1);
          for (int j=0; j<=p.N; ++j) ref.col(j)<<.05*p.dt*(k+j),0,0,.05,0,0;
          auto [u, info]=solver->solve(x,ref);
          rows.push_back({{"u",{u[0],u[1]}},{"success",info.success},{"backend",info.backend},
            {"error",info.error},{"X",matrix(info.X_pred)},{"U",matrix(info.U_pred)},
            {"trajectory",matrix(solver->get_predicted_trajectory())},
            {"finite",u.allFinite()&&info.X_pred.allFinite()&&info.U_pred.allFinite()},
            {"solve_time_ms_observation_only",info.solve_time_ms}});
          solver->set_applied_control({.5,.45});
        }
        solver->reset_warmstart();
      }
    }
  } catch (const std::invalid_argument & e) { exception=e.what(); exception_type="invalid_argument"; }
    catch (const std::exception & e) { exception=e.what(); exception_type="exception"; }
  std::set<std::string> mapped;
  std::ifstream maps("/proc/self/maps"); std::string line;
  while (std::getline(maps,line)) {
    auto pos=line.find('/');
    if (pos!=std::string::npos) { auto name=line.substr(pos); if(name.find(".so")!=std::string::npos) mapped.insert(name); }
  }
  Json result={{"case",id},{"available",available},{"constructed",constructed},{"backend",backend},
    {"exception",exception},{"exception_type",exception_type},{"rows",rows},
    {"allocation_attempts",allocated},{"created",created},{"graph_freed",graph_freed},{"capsule_freed",capsule_freed},
    {"setter_calls",setters},{"reported_setter_failures",reported_setter_failures},{"native_solves",native_solves},
    {"mapped_shared_objects",mapped},{"ROS_initialized",false},{"stage_qualified",false}};
  std::filesystem::create_directories(argv[2]);
  std::ofstream(std::filesystem::path(argv[2])/"result.json")<<result.dump(2)<<'\n';
  return 0;
}
