// Isolated out-of-preregister-domain counterexample; no existing source changes.
#include "/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_reference_bias_20261016_v20/reference_probe/projected_profile_time_v1.hpp"
#include <nlohmann/json.hpp>
#include <iostream>
int main(){
 usv_mpc::ReferenceInput input;input.path_stamp={100,0};input.profile_stamp=input.path_stamp;
 for(int k=0;k<=200;++k){input.path.push_back({.05*(.2*k),0.,0.});input.profile.push_back({.05,0.,0.,.2*k});}
 input.profile[1][3]=1e-12; // finite and strictly increasing, but outside fixed .2 s fixture domain
 usv_mpc::Vector6d target=usv_mpc::Vector6d::Zero();target[0]=.005;target[3]=.05;
 auto r=reference_candidate::build(target,input);
 const bool demonstrated=r.valid&&r.segment==0&&std::abs(r.fraction-.5)<1e-12&&r.projection_x==.005&&r.reference(0,0)==0.;
 std::cout<<nlohmann::json{{"schema","small-profile-interval-counterexample/v1"},{"demonstrated",demonstrated},{"candidate_valid",r.valid},{"segment",r.segment},{"fraction",r.fraction},{"profile_t0",r.profile_t0},{"projection_x",r.projection_x},{"reference_x0",r.valid?r.reference(0,0):0.},{"first_profile_interval_s",1e-12},{"current_preregistered_201point_dt02_fixture_domain",false},{"actual_velocity_bias_root_cause",false},{"stage_qualified",false}}.dump(2)<<'\n';return demonstrated?0:2;
}
