// SPDX-License-Identifier: MIT
// Calls the actual imported static core archive. No solver/ROS node/output API.
#include "usv_mpc_cpp/p1_input_core.hpp"
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <cmath>
using J=nlohmann::json;
int main(int argc,char **argv){try{
 if(argc!=2)throw std::runtime_error("input path required");std::ifstream in(argv[1]);J input;in>>input;J out=J::array();
 for(const auto &r:input.at("samples")){
  usv_mpc::ReferenceInput ref;
  ref.path=r.at("path").get<std::vector<std::array<double,3>>>();ref.profile=r.at("profile").get<std::vector<std::array<double,4>>>();
  ref.path_stamp=r.at("path_stamp").get<std::pair<int,int>>();ref.profile_stamp=r.at("profile_stamp").get<std::pair<int,int>>();ref.path_sequence=r.at("path_sequence");ref.profile_sequence=r.at("profile_sequence");
  usv_mpc::Vector6d target,frozen;for(int k=0;k<6;++k){target[k]=r.at("target_state").at(k);frozen[k]=r.at("frozen_state").at(k);}
  usv_mpc::ReferenceMetadata meta,oldmeta,zero_meta;
  auto actual=usv_mpc::build_frozen_reference(target,ref,20,.2,2,.6,&meta);
  auto from_frozen=usv_mpc::build_frozen_reference(frozen,ref,20,.2,2,.6,&oldmeta);
  auto offset_zero=usv_mpc::build_frozen_reference(target,ref,20,.2,0,.6,&zero_meta);
  double error=0,frozen_error=0;bool equal=true;
  for(int k=0;k<126;++k){double expected=r.at("reference").at(k);error=std::max(error,std::abs(actual.data()[k]-expected));equal=equal&&actual.data()[k]==expected;frozen_error=std::max(frozen_error,std::abs(from_frozen.data()[k]-expected));}
  out.push_back({{"case",r.at("case")},{"job_id",r.at("job_id")},{"actual_archive_full_reference_max_error",error},{"actual_archive_all_126_doubles_equal",equal},{"frozen_state_builder_max_error",frozen_error},
   {"nearest_target",meta.nearest_index},{"nearest_frozen",oldmeta.nearest_index},{"start_target",meta.start_index},{"start_frozen",oldmeta.start_index},{"configured_start_offset",meta.configured_start_offset},{"effective_start_offset",meta.effective_start_offset},{"profile_t0",meta.profile_t0},{"reference_mode",meta.reference_mode},
   {"target_x",target[0]},{"frozen_x",frozen[0]},{"reference_x0",actual(0,0)},{"reference_profile_u",actual(3,0)},{"reference_x_step_speed",(actual(0,1)-actual(0,0))/.2},
   {"configured_offset_zero_still_effective",zero_meta.effective_start_offset},{"configured_offset_zero_start",zero_meta.start_index},{"configured_offset_zero_x0",offset_zero(0,0)}});
 }
 std::cout<<J{{"schema","actual-static-reference-probe/v1"},{"samples",out},{"no_ROS_node_started",true},{"solver_invoked",false},{"stage_qualified",false},{"research_conclusion",false}}.dump(2)<<'\n';return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
