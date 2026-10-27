// SPDX-License-Identifier: MIT
// Isolated candidate component. No ROS/owner/admission/contract/output change.
#pragma once
#include "usv_mpc_cpp/p1_input_core.hpp"
#include <limits>
namespace reference_candidate {
constexpr const char *policy="projected_profile_time_v1";
struct Result {
 bool valid=false,stationary=false;
 std::string reason,reference_mode=policy;
 int segment=-1;double fraction=0,profile_t0=0,projection_x=0,projection_y=0,squared_distance=0;
 Eigen::MatrixXd reference;
};
inline Result build(const usv_mpc::Vector6d &target,const usv_mpc::ReferenceInput &input,int N=20,double dt=.2) {
 Result out;auto fail=[&](const char *why){out.reason=why;return out;};
 if(N!=20||dt!=.2||!target.allFinite())return fail("fixed_horizon_or_target_domain");
 const auto &path=input.path;const auto &profile=input.profile;
 if(path.size()<2||path.size()>2048||profile.size()!=path.size())return fail("path_profile_population");
 auto valid_stamp=[](const std::pair<int,int> &s){return s.first>=0&&s.second>=0&&s.second<1000000000;};
 if(!valid_stamp(input.path_stamp)||!valid_stamp(input.profile_stamp)||input.path_stamp!=input.profile_stamp)return fail("profile_not_synchronized");
 std::vector<double> times,vs,rs;bool stationary=true,any_degenerate=false;
 for(size_t i=0;i<path.size();++i){
  for(double v:path[i])if(!std::isfinite(v))return fail("path_nonfinite");
  for(double v:profile[i])if(!std::isfinite(v))return fail("profile_nonfinite");
  if(i&&profile[i][3]<=profile[i-1][3])return fail("profile_time_not_strictly_increasing");
  times.push_back(profile[i][3]);vs.push_back(profile[i][0]);rs.push_back(profile[i][2]);
  stationary=stationary&&path[i][0]==path[0][0]&&path[i][1]==path[0][1]&&path[i][2]==path[0][2]&&profile[i][0]==0&&profile[i][2]==0;
  if(i&&path[i][0]==path[i-1][0]&&path[i][1]==path[i-1][1])any_degenerate=true;
 }
 if(stationary){
  out.stationary=true;out.profile_t0=times.front();out.projection_x=path[0][0];out.projection_y=path[0][1];
  out.squared_distance=std::pow(target[0]-path[0][0],2)+std::pow(target[1]-path[0][1],2);
 }else{
  if(any_degenerate)return fail("degenerate_segment_requires_explicit_policy");
  double best=std::numeric_limits<double>::infinity();
  for(size_t i=0;i+1<path.size();++i){
   const double dx=path[i+1][0]-path[i][0],dy=path[i+1][1]-path[i][1],length2=dx*dx+dy*dy;
   if(!std::isfinite(length2)||length2<=0)return fail("segment_numeric_domain");
   const double fraction=std::clamp(((target[0]-path[i][0])*dx+(target[1]-path[i][1])*dy)/length2,0.,1.);
   const double px=path[i][0]+fraction*dx,py=path[i][1]+fraction*dy;
   const double distance=std::pow(target[0]-px,2)+std::pow(target[1]-py,2);
   if(distance<best){best=distance;out.segment=int(i);out.fraction=fraction;out.projection_x=px;out.projection_y=py;out.squared_distance=distance;out.profile_t0=times[i]+fraction*(times[i+1]-times[i]);}
  }
  if(out.segment<0||!std::isfinite(best))return fail("projection_not_finite");
  if(out.profile_t0+N*dt>times.back())return fail("horizon_exceeds_profile");
 }
 if(!std::isfinite(out.squared_distance))return fail("projection_not_finite");
 out.reference=Eigen::MatrixXd::Zero(6,N+1);int hint=std::max(0,out.segment);
 for(int k=0;k<=N;++k){
  auto sample=usv_mpc::sample_path_profile_at_time(path,times,vs,rs,out.profile_t0+k*dt,hint);hint=sample.j;
  out.reference.col(k)<<sample.x,sample.y,sample.psi,sample.v,0.,sample.r;
 }
 out.reference(2,0)=target[2]+usv_mpc::normalize_angle(out.reference(2,0)-target[2]);
 for(int k=1;k<=N;++k)out.reference(2,k)=out.reference(2,k-1)+usv_mpc::normalize_angle(out.reference(2,k)-out.reference(2,k-1));
 if(!out.reference.allFinite())return fail("reference_nonfinite");
 out.valid=true;return out;
}
} // namespace reference_candidate
