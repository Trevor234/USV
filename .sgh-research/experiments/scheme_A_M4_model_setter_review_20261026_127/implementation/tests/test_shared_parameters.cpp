// SPDX-License-Identifier: MIT
#include "usv_mpc_cpp/p_global_apply.hpp"
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <nlohmann/json.hpp>
using namespace usv_mpc;
using Json = nlohmann::json;
Json checks = Json::array(); bool passed = true;
void check(bool ok, const char *name) { checks.push_back({{"name", name}, {"passed", ok}}); passed &= ok; }
uint64_t bits(double x) { uint64_t value; std::memcpy(&value, &x, sizeof(value)); return value; }
MpcParams sentinels() {
  MpcParams p; p.hydro = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19};
  for (int i=0;i<6;++i) p.Q_diag(i)=20+i;
  p.R_diag={26,27}; p.Rd_diag={28,29}; p.Qf_scale=30; return p;
}
int main(int argc,char **argv) {
  if(argc!=2 || std::filesystem::exists(argv[1])) return 3;
  std::filesystem::create_directories(argv[1]);
  auto params=sentinels(); auto pg=p_global::pack(params);
  bool layout=true; for(size_t i=0;i<pg.size();++i) layout &= pg[i]==double(i+1);
  check(layout,"pack_all_30_distinct_slots");
  params.hydro.mass=-0.0; params.hydro.Iz=std::numeric_limits<double>::infinity();
  params.hydro.xg=std::numeric_limits<double>::quiet_NaN(); auto special=p_global::pack(params);
  check(bits(special[0])==bits(params.hydro.mass)&&bits(special[1])==bits(params.hydro.Iz)&&bits(special[2])==bits(params.hydro.xg),"pack_preserves_IEEE_values_without_validation");
  p_global::Capsule dummy{}; int calls=0,observed_size=0; p_global::Packed observed{};
  auto capture=[&](auto*,double *data,int size){++calls;observed_size=size;
    for(int i=0;i<size && i<int(pg.size());++i) observed[i]=data[i];return 0;};
  auto applied=p_global::apply_with(&dummy,pg,capture);
  check(applied.ok()&&applied.native_called&&calls==1,"apply_calls_adapter_once");
  check(observed_size==30&&observed==pg,"apply_exact_native_count_and_values");
  calls=0; auto null=p_global::apply_with(nullptr,pg,capture);
  check(!null.ok()&&null.code==p_global::ApplyCode::null_capsule&&calls==0,"null_capsule_before_adapter");
  auto missing=p_global::apply(&dummy,pg,nullptr);
  check(!missing.ok()&&missing.code==p_global::ApplyCode::null_setter,"null_setter_rejected");
  auto bad=pg; bad[0]=std::numeric_limits<double>::quiet_NaN();
  auto nan=p_global::apply_with(&dummy,bad,capture);
  bad=pg;bad[29]=std::numeric_limits<double>::infinity();auto inf=p_global::apply_with(&dummy,bad,capture);
  check(nan.code==p_global::ApplyCode::nonfinite_parameters&&inf.code==p_global::ApplyCode::nonfinite_parameters&&calls==0,"nonfinite_before_adapter");
  auto failed=p_global::apply_with(&dummy,pg,[](auto*,double*,int){return 17;});
  check(!failed.ok()&&failed.native_called&&failed.code==p_global::ApplyCode::native_error&&failed.native_status==17,"native_status_propagated");
  const auto original=pg;
  auto clobber=p_global::apply_with(&dummy,pg,[](auto*,double*data,int){data[0]=999;return 0;});
  check(clobber.ok()&&pg==original,"apply_input_unchanged");
  bool threw=false;try{p_global::apply_with(&dummy,pg,[](auto*,double*,int)->int{throw std::runtime_error("adapter only");});}catch(const std::runtime_error&){threw=true;}
  check(threw&&pg==original,"adapter_exception_propagates_to_owner");
  Json result={{"passed",passed},{"assertions",checks},{"adapter_is_native_fault",false},{"stage_qualified",false},{"ROS_initialized",false}};
  std::ofstream f(std::filesystem::path(argv[1])/"result.json");f<<result.dump(2)<<'\n';return passed?0:2;
}
