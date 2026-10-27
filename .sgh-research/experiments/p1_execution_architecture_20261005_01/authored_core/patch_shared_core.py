#!/usr/bin/env python3
"""Guarded F5 extraction; no source copy leaves the ROS host."""
from pathlib import Path
import hashlib,json,re
ROOT=Path('/home/trevor/USV');PKG=ROOT/'usv_mpc_ws/src/usv_mpc_cpp'
EXP=ROOT/'.sgh-research/experiments/p1_execution_architecture_20261005_01'
cpp=PKG/'src/mpc_node.cpp';text=cpp.read_text()
assert hashlib.sha256(cpp.read_bytes()).hexdigest()=='2f1b457ce9644d6ceff722e4ce328fa6a5de23a2cb94f8470c022e0bd70f2dd8'
backup=EXP/'f5_pre_shared_core';backup.mkdir(exist_ok=False)
for p in [cpp,PKG/'CMakeLists.txt']: (backup/p.name).write_bytes(p.read_bytes())
start=text.index('Eigen::MatrixXd MpcControllerNode::build_reference_(')
end=text.index('\nvoid MpcControllerNode::safe_shutdown()',start)
original=text[start:end];body=original[original.index('{')+1:original.rfind('}')]
body=body.replace('  const int N = mpc_->N();\n  double dt = mpc_->dt();\n','')
replace={'reference_path_':'input.path','ref_profile_':'input.profile','reference_path_stamp_':'input.path_stamp','ref_profile_stamp_':'input.profile_stamp','path_received_sequence_':'input.path_sequence','profile_received_sequence_':'input.profile_sequence','reference_start_offset_':'offset','cruise_speed_':'cruise'}
for a in sorted(replace,key=len,reverse=True):body=body.replace(a,replace[a])
body=re.sub(r'^    profile_synced_ = .*?;\n','',body,flags=re.M)
body=re.sub(r'^    profile_sync_reason_ = .*?;\n','',body,flags=re.M)
core='#include "usv_mpc_cpp/p1_input_core.hpp"\nnamespace usv_mpc {\nEigen::MatrixXd build_frozen_reference(const Vector6d & current_state,const ReferenceInput & input,int N,double dt,int offset,double cruise,ReferenceMetadata * evidence)\n{'+body+'}\n}\n'
assert 'profile_synced_' not in core and 'mpc_' not in core.replace('usv_mpc_cpp','')
(PKG/'src/p1_input_core.cpp').write_text(core)
fields=re.findall(r'evidence->([a-zA-Z0-9_]+)',body)
wrapper='''Eigen::MatrixXd MpcControllerNode::build_reference_(
  const Vector6d & current_state, ResearchReference * evidence)
{
  ReferenceInput input;
  input.path=reference_path_;input.profile=ref_profile_;
  input.path_stamp=reference_path_stamp_;input.profile_stamp=ref_profile_stamp_;
  input.path_sequence=path_received_sequence_;input.profile_sequence=profile_received_sequence_;
  ReferenceMetadata metadata;
  auto ref=build_frozen_reference(current_state,input,mpc_->N(),mpc_->dt(),
    reference_start_offset_,cruise_speed_,&metadata);
  // Preserve F5 cached status, including its empty-path early return semantics.
  if (!input.path.empty()) {profile_synced_=metadata.profile_synced;profile_sync_reason_=metadata.profile_sync_reason;}
  if (evidence) {
'''+''.join('    evidence->'+f+'=metadata.'+f+';\n' for f in sorted(set(fields)))+'''  }
  return ref;
}
'''
text=text[:start]+wrapper+text[end:]
begin=text.index('std::pair<bool, std::string> MpcControllerNode::can_solve_() const')
finish=text.index('\nvoid MpcControllerNode::enter_standby_',begin)
text=text[:begin]+'''std::pair<bool, std::string> MpcControllerNode::can_solve_() const
{
  InputEligibility c;
  c.odom_received=odom_received_;c.path_received=path_received_;c.path_size=reference_path_.size();
  c.now_s=steady_now();c.last_odom_s=last_odom_time_;c.odom_timeout_s=odom_timeout_s_;
  c.require_fcu=require_fcu_state_;c.armed=armed_;c.last_state_s=last_state_time_;
  c.state_timeout_s=state_timeout_s_;c.mode=mode_;c.allowed_modes=allowed_fcu_modes_;
  return input_eligibility(c);
}
'''+text[finish:]
# Replace accepted state composition, after existing raw telemetry/diagnostic guards.
old='''  x_ = p.x;
  y_ = p.y;
  psi_ = psi;
  u_ = t.linear.x;
  v_ = t.linear.y;
  r_ = t.angular.z;'''
new='''  const auto composed=compose_odom({p.x,p.y,t.linear.x,t.linear.y,t.angular.z},
    {q.x,q.y,q.z,q.w});
  x_=composed[0];y_=composed[1];psi_=composed[2];u_=composed[3];v_=composed[4];r_=composed[5];'''
assert text.count(old)==1;text=text.replace(old,new)
assert text.count('if (!std::isfinite(r)) {')==1;text=text.replace('if (!std::isfinite(r)) {','if (!admit_imu(r)) {')
old='''  left.data = std::clamp(thrust(0) * vrx_thrust_scale_, lower, upper);
  right.data = std::clamp(thrust(1) * vrx_thrust_scale_, lower, upper);'''
new='''  const auto mapped=map_vrx(thrust,vrx_thrust_scale_,lower,upper,vrx_thrust_cmd_max_);
  left.data=mapped[0];right.data=mapped[1];'''
assert text.count(old)==1;text=text.replace(old,new)
text=text.replace('#include "usv_mpc_cpp/mpc_node.hpp"','#include "usv_mpc_cpp/mpc_node.hpp"\n#include "usv_mpc_cpp/p1_input_core.hpp"')
cpp.write_text(text)
cm=PKG/'CMakeLists.txt';s=cm.read_text();assert s.count('  src/utils.cpp\n')==1;s=s.replace('  src/utils.cpp\n','  src/utils.cpp\n  src/p1_input_core.cpp\n');cm.write_text(s)
r={'schema':'p1-shared-core-patch/1','f5_original_node_sha256':hashlib.sha256((backup/'mpc_node.cpp').read_bytes()).hexdigest(),'node_sha256':hashlib.sha256(cpp.read_bytes()).hexdigest(),'reference_core_sha256':hashlib.sha256((PKG/'src/p1_input_core.cpp').read_bytes()).hexdigest(),'extracted_metadata_fields':sorted(set(fields)),'legacy_reference_math':'F5 body extracted verbatim except member bindings and cached-status assignments','scope':'shared core; no new physical output ownership yet'}
(EXP/'shared_core_patch.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
