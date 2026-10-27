#!/usr/bin/env python3
"""Shared numeric admission is authoritative; preserve F5 diagnostic reasons."""
from pathlib import Path
import hashlib,json
root=Path('/home/trevor/USV');exp=root/'.sgh-research/experiments/p1_execution_architecture_20261005_01'
p=root/'usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp';s=p.read_text()
assert hashlib.sha256(p.read_bytes()).hexdigest()=='c15f83484e498f2a6a5d6ba672e89493cb575f7bc31282e2b80d9be5995ef011a'
backup=exp/'before_authoritative_odom.cpp';assert not backup.exists();backup.write_bytes(p.read_bytes())
begin=s.index('  if (!std::isfinite(p.x)',s.index('void MpcControllerNode::odom_callback_'))
end=s.index('  std::lock_guard<std::mutex> lk(state_lock_);',begin)
old=s[begin:end]
assert 'quaternion_norm2 < 1e-12' in old and 'double psi = quaternion_to_yaw' in old
new='''  // P1_SHARED_ODOM_ADMISSION_V1: the common gate owns acceptance.
  if (!admit_odom({p.x, p.y, t.linear.x, t.linear.y, t.angular.z},
    {q.x, q.y, q.z, q.w}))
  {
'''+''.join('  '+line+'\n' for line in old.splitlines())+'''    return;
  }
'''
s=s[:begin]+new+s[end:];p.write_text(s)
r={'schema':'p1-authoritative-odom-gate-patch/1','before_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'after_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'acceptance_owner':'shared admit_odom','f5_diagnostics_preserved':True}
(exp/'authoritative_odom_patch.json').write_text(json.dumps(r,indent=2));print('SHARED_ODOM_GATE_PATCHED')
