#!/usr/bin/env python3
"""Deploy only authored files and guarded incremental library exports."""
from pathlib import Path
import hashlib,json
R=Path('/home/trevor/USV');E=R/'.sgh-research/experiments/p1_execution_architecture_20261005_01';A=E/'authored';W=R/'usv_mpc_ws/src'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
backup=E/'pre_m2_exports';backup.mkdir(exist_ok=False)
interfaces=W/'usv_research_interfaces';cm=interfaces/'CMakeLists.txt';(backup/'interfaces_CMakeLists.txt').write_bytes(cm.read_bytes());s=cm.read_text();assert s.count('"msg/ReferencePrediction.msg")')==1
names=['SolveJob','SolveCandidate','WorkerCapability','ExecutionDecision']
for n in names:assert not (interfaces/'msg'/f'{n}.msg').exists();(interfaces/'msg'/f'{n}.msg').write_bytes((A/'messages'/f'{n}.msg').read_bytes())
s=s.replace('"msg/ReferencePrediction.msg")','"msg/ReferencePrediction.msg"\n  '+ ' '.join('"msg/'+n+'.msg"' for n in names)+')');cm.write_text(s)
mpc=W/'usv_mpc_cpp';cm=mpc/'CMakeLists.txt';(backup/'mpc_CMakeLists.txt').write_bytes(cm.read_bytes());s=cm.read_text()
assert 'ament_export_targets(p1_core_targets' not in s
s=s.replace('  ${ACADOS_GEN_DIR}', '  $<BUILD_INTERFACE:${ACADOS_GEN_DIR}>\n  $<INSTALL_INTERFACE:include/usv_mpc_cpp/acados_generated>')
extra='''
# P1_EXPORT_CORE_V1: backend has one owner in the independent solver process.
install(TARGETS mpc_core_lib mpc_solver_lib codegen_lib
 EXPORT p1_core_targets ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
install(DIRECTORY acados_generated/ DESTINATION include/usv_mpc_cpp/acados_generated FILES_MATCHING PATTERN "*.h")
ament_export_targets(p1_core_targets HAS_LIBRARY_TARGET NAMESPACE usv_mpc_cpp::)
ament_export_dependencies(Eigen3 nlohmann_json)
'''
s=s.replace('\nament_package()',extra+'\nament_package()');cm.write_text(s)
pkg=W/'usv_research_safety_cpp';pkg.mkdir(exist_ok=False)
for p in (A/'safety').iterdir():
 if p.is_file():(pkg/p.name).write_bytes(p.read_bytes())
r={'schema':'p1-m2-authored-deployment/1','files':{str(p.relative_to(R)):sha(p) for p in list(pkg.iterdir())+[cm,interfaces/'CMakeLists.txt']+[interfaces/'msg'/f'{n}.msg' for n in names] if p.is_file()}}
(E/'m2_deployment.json').write_text(json.dumps(r,indent=2));print('M2_AUTHORED_DEPLOYED',len(r['files']))
