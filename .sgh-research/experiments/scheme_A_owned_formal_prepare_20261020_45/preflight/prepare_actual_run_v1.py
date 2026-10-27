#!/usr/bin/env python3
"""Lock current affected sources and preregister exactly one no_output session."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shlex
import time

D=Path(__file__).resolve().parent.parent


def pin(path):
    p=Path(path);b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def create(path,value):
    with path.open('x') as f:json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')


def main():
    build_dir=D/'build/native_formal_attempt03';build=json.loads((build_dir/'build_result_v1.json').read_text())
    tests=json.loads((D/'verification/constructor_checks_v2.json').read_text())
    assert build['passed'] and tests['passed'] and tests['case_count']==22
    assert build['new_input_boundary_test']['passed'] and build['new_input_boundary_test']['checks']==17
    protection=json.loads((D/'preflight/protection_initial_v1.json').read_text());assert protection['passed']
    rows=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            values=(p/'environ').read_bytes().split(b'\0')
            if b'ROS_DOMAIN_ID=197' in values:rows.append({'pid':int(p.name),'exe':os.readlink(p/'exe')})
        except OSError:pass
    assert not rows,'DDS197 already has a visible process'
    topics={'/clock':'rosgraph_msgs/msg/Clock','/wamv/sensors/position/ground_truth_odometry':'nav_msgs/msg/Odometry',
      '/wamv/sensors/imu/imu/data':'sensor_msgs/msg/Imu','/path/reference':'nav_msgs/msg/Path',
      '/path/reference_profile':'std_msgs/msg/Float64MultiArray','/p1/worker_capability':'usv_research_interfaces/msg/WorkerCapability',
      '/p1/solve_candidate':'usv_research_interfaces/msg/SolveCandidate'}
    topic_file=D/'preflight/formal_topics_v1.json';create(topic_file,{'schema':'p1-owned-recorder-topics/v1','topics':topics})
    sdk=D.parent/'scheme_A_owned_business_start_20261020_39/author/build_c33_v9.py'
    tree=ast.parse(sdk.read_text());setup=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SETUP' for t in n.targets))
    wrapper=D/'preflight/run_actual_prepare_v1.sh';registration=D/'preflight/actual_run_registration_v1.json'
    command=['/usr/bin/python3','-B',str(D/'author/owned_prepare_driver_v1.py'),'--registration',str(registration)]
    wrapper.write_text('set -e\n'+setup.replace('ROS_DOMAIN_ID=120','ROS_DOMAIN_ID=197')+'exec '+shlex.join(command)+'\n')
    inputs={}
    def capture(path,expected=None):
        p=Path(path);actual=pin(p)
        if expected is not None:assert all(actual[k]==expected[k] for k in ['bytes','sha256'] if k in expected),str(p)
        if str(p) in inputs:assert inputs[str(p)]==actual
        inputs[str(p)]=actual
    bundle=json.loads(Path(build['source_bundle']['path']).read_text())
    capture(build['source_bundle']['path'],build['source_bundle'])
    for r in bundle['files'].values():capture(r['path'],r);capture(r['snapshot'],r)
    for r in build['compiler_dependencies'].values():capture(r['path'],r)
    for r in build['runtime_libraries'].values():capture(r['path'],r)
    for field in ['compiler','compiler_frontend']:capture(build[field]['path'],build[field])
    for role,r in build['roles'].items():
        capture(r['binary'],{'sha256':r['binary_sha256']});capture(r['source_bundle']['path'],r['source_bundle'])
        b=json.loads(Path(r['source_bundle']['path']).read_text());files=b['files'];files=files.values() if type(files)is dict else files
        for f in files:capture(f['path'],f)
    for p in [build_dir/'build_result_v1.json',build_dir/'runtime_registry_v1.json',D/'verification/constructor_checks_v2.json',
              Path(__file__).resolve(),wrapper,topic_file,sdk]:capture(p)
    lock={'schema':'formal-owned-prepare-source-lock-v1','registered_ns':time.monotonic_ns(),'input_sha256':inputs,
          'visible_DDS197_processes_before_launch':rows,'scope':'four role actual preparation-close only','stage_qualified':False,'execute_qualified':False}
    lock_file=D/'preflight/actual_source_lock_v1.json';create(lock_file,lock)
    reg={'schema':'formal-owned-prepare-run-v1','registered_ns':time.monotonic_ns(),'run_id':'formal_prepare_01',
         'domain_id':197,'output':str(D/'runs/formal_prepare_01'),'registry':str(build_dir/'runtime_registry_v1.json'),
         'registry_sha256':pin(build_dir/'runtime_registry_v1.json')['sha256'],'contract':str(D/'author/formal_pre_freeze_contract_v1.json'),
         'contract_sha256':pin(D/'author/formal_pre_freeze_contract_v1.json')['sha256'],
         'topics':str(topic_file),'topics_sha256':pin(topic_file)['sha256'],'source_lock':str(lock_file),
         'source_lock_sha256':pin(lock_file)['sha256'],'max_seconds':35,'close_budget_seconds':10,'prepared_hold_seconds':1,
         'physical_execute_release_enabled':False,'fault_injection_enabled':False,'solver_jobs_permitted':0,
         'Decisions_permitted':0,'Applied_permitted':0,'physical_publishers_permitted':0,
         'stop_order':['preparer','fixture','worker','recorder'],'acceptance':['actual4role config/proc/GID binding',
             'actual native grant and replay rejection','zero forbiddenWriters/jobs','allSource+bag closed,INTonly,groupsEmpty',
             'external source/bag/raw-input accounting and source-lock recheck'],
         'not_qualified':['fullRegulatorNoOutput','B5freeze','M0b','M4','modelTransaction','P1'],
         'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
    create(registration,reg)
    print(json.dumps({'passed':True,'source_pins':len(inputs),'registration':str(registration),'source_lock_sha256':reg['source_lock_sha256']}))


if __name__=='__main__':main()
