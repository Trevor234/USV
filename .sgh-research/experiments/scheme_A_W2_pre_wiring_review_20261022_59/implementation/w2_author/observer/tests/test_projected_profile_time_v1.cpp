#include "projected_profile_time_v1.hpp"
#include <iostream>
#include <stdexcept>
using usv_mpc::ReferenceInput;using usv_mpc::Vector6d;
int main(){size_t checks=0;auto require=[&](bool value){++checks;if(!value)throw std::runtime_error("projection check "+std::to_string(checks));};
 auto straight=[](double speed){ReferenceInput r;r.path_stamp={100,123};r.profile_stamp=r.path_stamp;for(int k=0;k<=200;++k){r.path.push_back({speed*(.2*k),0.,0.});r.profile.push_back({speed,0.,0.,.2*k});}return r;};
 auto target=Vector6d::Zero().eval();auto input=straight(.1);target[0]=2.50254083761055;target[3]=.12541161761083622;
 auto result=reference_candidate::build(target,input);require(result.valid);require(result.reference_mode=="projected_profile_time_v1");require(result.segment==125);require(std::abs(result.reference(0,0)-target[0])<1e-15);require(std::abs(result.profile_t0-target[0]/.1)<1e-13);
 for(int k=0;k<=20;++k){require(result.reference(3,k)==.1);require(std::abs(result.reference(0,k)-(target[0]+.1*.2*k))<1e-14);}
 usv_mpc::ReferenceMetadata legacy;auto old=usv_mpc::build_frozen_reference(target,input,20,.2,2,.6,&legacy);require(old(0,0)>result.reference(0,0));require(std::abs(old(0,0)-2.54)<1e-14);require(legacy.start_index==127);
 usv_mpc::ReferenceMetadata clamp;auto zero_offset=usv_mpc::build_frozen_reference(target,input,20,.2,0,.6,&clamp);require(clamp.effective_start_offset==1);require(zero_offset(0,0)>result.reference(0,0));
 auto offgrid=target;offgrid[1]=.3;auto off=reference_candidate::build(offgrid,input);require(off.valid);require(off.reference(1,0)==0);require(std::abs(off.squared_distance-.09)<1e-15);require(std::abs(off.reference(0,0)-target[0])<1e-15);
 auto bad=input;bad.profile_stamp.second++;require(!reference_candidate::build(target,bad).valid);bad=input;bad.path_stamp={-1,0};require(!reference_candidate::build(target,bad).valid);bad=input;bad.path_stamp.second=1000000000;bad.profile_stamp=bad.path_stamp;require(!reference_candidate::build(target,bad).valid);
 bad=input;bad.profile.pop_back();require(!reference_candidate::build(target,bad).valid);bad=input;bad.profile[5][3]=bad.profile[4][3];require(!reference_candidate::build(target,bad).valid);bad=input;bad.profile[5][0]=std::numeric_limits<double>::quiet_NaN();require(!reference_candidate::build(target,bad).valid);
 bad=input;bad.path[5]=bad.path[4];require(!reference_candidate::build(target,bad).valid);bad=input;bad.path[5][0]=std::numeric_limits<double>::infinity();require(!reference_candidate::build(target,bad).valid);
 auto zero=straight(0);auto rest=reference_candidate::build(Vector6d::Zero(),zero);require(rest.valid&&rest.stationary);require(rest.reference.norm()==0);require(rest.profile_t0==0);bad=zero;bad.profile[7][0]=.1;require(!reference_candidate::build(Vector6d::Zero(),bad).valid);
 auto past=target;past[0]=4.;require(!reference_candidate::build(past,input).valid);require(!reference_candidate::build(target,input,21,.2).valid);require(!reference_candidate::build(target,input,20,.1).valid);
 auto curve=straight(.1);for(size_t k=0;k<curve.path.size();++k){double a=.01*k;curve.path[k]={std::sin(a),1-std::cos(a),3.1+.01*k};}
 auto turn=target;turn[0]=curve.path[20][0];turn[1]=curve.path[20][1];turn[2]=3.3;auto curved=reference_candidate::build(turn,curve);require(curved.valid);require(std::abs(curved.reference(0,0)-turn[0])<1e-14);require(std::abs(curved.reference(1,0)-turn[1])<1e-14);
 for(int k=1;k<=20;++k)require(std::abs(curved.reference(2,k)-curved.reference(2,k-1))<.1);
 require(std::abs(curved.reference(2,0)-turn[2])<1e-12);require(curved.reference(3,0)==.1);
 std::cout<<"projected reference native checks="<<checks<<" passed; actual legacy static archive linked; no ROS/solver/output calls\n";}
