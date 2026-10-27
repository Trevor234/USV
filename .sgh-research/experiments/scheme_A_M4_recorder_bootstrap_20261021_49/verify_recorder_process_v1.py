#!/usr/bin/env python3
"""Authenticate a real waiting Recorder; never treat process-only as full-ready."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent


def enc(v):return (json.dumps(v,sort_keys=True,separators=(',',':'))+'\n').encode()
def put(p,v):
    b=enc(v)
    with p.open('xb') as f:f.write(b)
    return hashlib.sha256(b).hexdigest()


def main():
    root=D/'verification/recorder_process_v1';root.mkdir()
    spec=importlib.util.spec_from_file_location('current_m4_driver_helpers',D/'author/owned_m4_driver_v1.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    setupfile=D.parent/'scheme_A_owned_business_start_20261020_39/author/build_c33_v9.py'
    tree=ast.parse(setupfile.read_bytes());setup=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SETUP' for t in n.targets))
    setup+='\nexport ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120 RMW_IMPLEMENTATION=rmw_fastrtps_cpp\n'
    recorder=D.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10/recorder/build01/p1_owned_recorder'
    contract=D.parent/'scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'
    topics={'schema':'p1-owned-recorder-topics/v1','topics':{'/unit_m4_bootstrap_absent_writer':'std_msgs/msg/Float64'}}
    th=put(root/'topics.json',topics);run='M4_recorder_process_component_49'
    argv=[str(recorder),'--run-id',run,'--contract',str(contract),'--contract-sha256',module.CONTRACT_SHA,
          '--topics',str(root/'topics.json'),'--topics-sha256',th,'--manifest',str(root/'manifest.json'),
          '--terminal',str(root/'terminal.json'),'--bag',str(root/'bag'),'--storage-id','sqlite3','--prepare-budget-ms','10000']
    script=root/'recorder.sh';script.write_text('set -e\n'+setup+'\nexec '+shlex.join(argv)+'\n')
    stdout=(root/'recorder_stdout.log').open('xb');stderr=(root/'recorder_stderr.log').open('xb')
    child=subprocess.Popen(['/bin/bash',str(script)],stdout=stdout,stderr=stderr,start_new_session=True)
    rows=[];signals=[]
    try:
        # Popen returns after the shell exec, so wait for the actual registered
        # Recorder binary before recording its independently observed identity.
        import time
        until=time.monotonic()+3
        while True:
            actual=module.process(child.pid)
            if actual['binary_sha256']=='d1b91109081c84d4427510d752e926249a0779c44e84b36509bbfa1dac800002':break
            assert child.poll() is None and time.monotonic()<until;time.sleep(.01)
        pin={**actual,'schema':'M4-recorder-owned-process-only/v1','role':'recorder','run_id':run,
             'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'contract_sha256':module.CONTRACT_SHA,
             'source_bundle_sha256':'61da30907164a3e55ba3aa41e5609d9b80562982133c52cc6135d8283bb99c08',
             'manifest_path':str(root/'manifest.json'),'topics_sha256':th,'process_only':True,'recording_ready':False}
        cases=[('actual_waiting_process',pin,True)]
        for key,value in [('role','worker'),('recording_ready',True),('process_only',False),('pid',os.getpid()),
                          ('process_start_ticks',pin['process_start_ticks']+1),('binary_sha256','a'*64),('source_bundle_sha256','b'*64),
                          ('boot_id','foreign'),('topics_sha256','c'*64),('pgid',pin['pgid']+1),('contract_sha256','d'*64)]:
            bad=copy.deepcopy(pin);bad[key]=value;cases.append((key,bad,False))
        bad=copy.deepcopy(pin);bad['argv'][2]='foreign';cases.append(('actual_argv_mismatch',bad,False))
        bad=copy.deepcopy(pin);bad['invented_ready']=True;cases.append(('unknown_field',bad,False))
        probe=D/'build/m4_attempt01/cmake_build/test_m4_recorder_process'
        for i,(name,value,expected) in enumerate(cases):
            path=root/f'case{i:02d}.json';sha=put(path,value)
            cmd=[str(probe),str(path),sha]
            script=root/f'case{i:02d}.sh';script.write_text('set -e\n'+setup+'\nexec '+shlex.join(cmd)+'\n')
            result=subprocess.run(['/bin/bash',str(script)],capture_output=True,timeout=10)
            (root/f'case{i:02d}.stdout.json').write_bytes(result.stdout);(root/f'case{i:02d}.stderr.log').write_bytes(result.stderr)
            parsed=json.loads(result.stdout);accepted=parsed['accepted'];passed=result.returncode==0 and accepted==expected
            if expected:passed=passed and parsed['recording_ready'] is False and parsed['full_manifest_exists'] is False
            rows.append({'name':name,'expected_accepted':expected,'passed':passed,'result':parsed})
    finally:
        for sig,budget in [(signal.SIGINT,2.5),(signal.SIGTERM,1),(signal.SIGKILL,1)]:
            if child.poll() is not None:break
            actual=module.process(child.pid);assert actual['pgid']==child.pid
            os.killpg(child.pid,sig);signals.append(sig.name)
            try:child.wait(timeout=budget)
            except subprocess.TimeoutExpired:pass
        stdout.close();stderr.close()
    try:os.killpg(child.pid,0);group_empty=False
    except ProcessLookupError:group_empty=True
    # SIGINT before preparation is deliberately an incomplete Recorder session;
    # its real RC/terminal are retained rather than called normal recording.
    report={'schema':'M4-real-Recorder-process-only-component/v1','passed':all(r['passed'] for r in rows) and len(rows)==14 and group_empty,
       'cases':rows,'case_count':len(rows),'actual_Recorder_executable_used':True,'full_recording_ready_proven':False,
       'control_API_calls':0,'Recorder_returncode':child.returncode,'Recorder_signals':signals,'group_empty':group_empty,
       'M4_stage_qualified':False,'P1_qualified':False}
    put(D/'verification/recorder_process_verification_v1.json',report)
    print(json.dumps({'passed':report['passed'],'cases':len(rows),'Recorder_RC':child.returncode,'group_empty':group_empty,'failed':[r['name'] for r in rows if not r['passed']]}))
    return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
