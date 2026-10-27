#!/usr/bin/env python3
"""Seeded state/permission core cases; no claim of real owned ROS readiness."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time

D=Path(__file__).resolve().parent.parent
I=D/'implementation'


def pin(path):
    data=path.read_bytes();return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def data(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def create(path,value):
    with path.open('xb') as f:f.write(data(value))


def main():
    profile=I/'current_pre_freeze_contract_v1.json'
    pre=json.loads(profile.read_bytes())
    frozen=dict(pre);frozen.update(qualification='execution_frozen',execute_qualified=True,
        parameters_are_diagnostic_only=False,pending_final_calibration=[],freeze_evidence_sha256='f'*64)
    frozen_path=D/'verification/frozen_shape_for_entry_cases_v1.json';create(frozen_path,frozen)
    identity={'run_id':'formal_prepare_seeded_44','boot_id':'seeded-boot-44',
        'contract_sha256':pin(profile)['sha256'],'preparer_manifest_sha256':'1'*64,
        'driver_pid':1234,'driver_start_ticks':500,'driver_exe_sha256':'2'*64,
        'driver_argv_sha256':'3'*64,'driver_tool_sha256':'4'*64,
        'worker_manifest_sha256':'5'*64,'fixture_manifest_sha256':'6'*64,'recorder_manifest_sha256':'7'*64}
    version={k:1 for k in ['task','model','config','schedule','epoch']}
    created=1_000_000_000;now=created+3_000_000_000
    context={k:True for k in ['driver_live','worker_live','fixture_live','recorder_live',
        'worker_capability_valid','source_inputs_valid','reference_pair_ready','recording_ready','sink_ready']}
    context.update(stopping=False,capability_receipt_ns=now-200_000_000,ready_generation=1,
        physical_publishers=0,solve_job_publishers=0,decision_publishers=0,applied_publishers=0,
        ready_snapshot_sha256='8'*64,version=version)
    grant={'schema':'p1-owned-formal-prepare-v1','policy':'owned-formal-no-output-prepare-close-v1',
        'scope':'bounded_prepare_close_only','run_id':identity['run_id'],'boot_id':identity['boot_id'],
        'contract_sha256':identity['contract_sha256'],
        'spec_sha256':'317ec56f9c1211b9d8adc5dc727e2a20c1f281afd2047efafecbac797c46d798',
        'preparer_manifest_sha256':identity['preparer_manifest_sha256'],
        'driver':{'pid':identity['driver_pid'],'start_ticks':identity['driver_start_ticks'],
                  'exe_sha256':identity['driver_exe_sha256'],'argv_sha256':identity['driver_argv_sha256'],
                  'tool_sha256':identity['driver_tool_sha256']},
        'roles':{k:identity[k] for k in ['worker_manifest_sha256','fixture_manifest_sha256','recorder_manifest_sha256']},
        'ready_snapshot_sha256':context['ready_snapshot_sha256'],'ready_generation':1,'version':version,
        'issued_ns':now-1_000_000_000,'sequence':1,'stage_qualified':False,'execute_qualified':False}
    base={'contract_path':str(profile),'mode':'no_output','identity':identity,
          'created_ns':created,'now_ns':now,'context':context,
          'operation':'open','raw_request':json.dumps(grant)}
    cases=[]

    def add(name,request,completed=False,state='rejected'):
        cases.append({'name':name,'request':request,'expected_completed':completed,'expected_state':state})

    add('valid_preparation_only',copy.deepcopy(base),True,'prepared')
    for mode in ['shadow','execute','','NO_OUTPUT']:
        r=copy.deepcopy(base);r['mode']=mode;add('entry_mode_'+repr(mode),r,False,'not_created')
    for label,path in [('diag',I/'current_diag_contract_v1.json'),('Frozen',frozen_path)]:
        r=copy.deepcopy(base);r['contract_path']=str(path);add('entry_profile_'+label,r,False,'not_created')
    for key in grant:
        bad=copy.deepcopy(grant);bad.pop(key);r=copy.deepcopy(base);r['raw_request']=json.dumps(bad)
        add('missing_'+key,r)
    wrong={'schema':'invented','policy':'owned-prepare-before-business-v1','scope':'execute',
        'run_id':'old_run','boot_id':'old_boot','contract_sha256':'a'*64,'spec_sha256':'b'*64,
        'preparer_manifest_sha256':'c'*64,'ready_snapshot_sha256':'d'*64,'ready_generation':2,
        'sequence':2,'stage_qualified':True,'execute_qualified':True}
    for key,value in wrong.items():
        bad=copy.deepcopy(grant);bad[key]=value;r=copy.deepcopy(base);r['raw_request']=json.dumps(bad)
        add('wrong_'+key,r)
    for key in ['sequence','ready_generation','issued_ns','stage_qualified','execute_qualified']:
        bad=copy.deepcopy(grant);bad[key]=int(grant[key]) if type(grant[key]) is bool else float(grant[key])
        r=copy.deepcopy(base);r['raw_request']=json.dumps(bad);add('strict_type_'+key,r)
    for group in ['driver','roles','version']:
        for key,value in grant[group].items():
            bad=copy.deepcopy(grant);bad[group][key]=value+1 if type(value) is int else 'e'*64
            r=copy.deepcopy(base);r['raw_request']=json.dumps(bad);add('binding_'+group+'_'+key,r)
    for key in ['driver_live','worker_live','fixture_live','recorder_live','worker_capability_valid',
                'source_inputs_valid','reference_pair_ready','recording_ready','sink_ready']:
        r=copy.deepcopy(base);r['context'][key]=False;add('missing_live_prerequisite_'+key,r)
    for key in ['physical_publishers','solve_job_publishers','decision_publishers','applied_publishers']:
        r=copy.deepcopy(base);r['context'][key]=1;add('prohibited_writer_'+key,r)
    for label,value in [('stale',now-600_000_001),('future',now+1),('zero',0)]:
        r=copy.deepcopy(base);r['context']['capability_receipt_ns']=value;add('capability_'+label,r)
    r=copy.deepcopy(base);r['context']['capability_receipt_ns']=now-600_000_000
    add('capability_at_600ms_inclusive',r,True,'prepared')
    for label,value in [('stale',now-2_000_000_001),('future',now+1),('pre_creation',created-1)]:
        bad=copy.deepcopy(grant);bad['issued_ns']=value;r=copy.deepcopy(base);r['raw_request']=json.dumps(bad)
        add('grant_'+label,r)
    bad=copy.deepcopy(grant);bad['issued_ns']=now-2_000_000_000;r=copy.deepcopy(base);r['raw_request']=json.dumps(bad)
    add('grant_at_2s_inclusive',r,True,'prepared')
    for label,value in [('empty',''),('too_large',' '*8193),('duplicate',json.dumps(grant)[:-1]+',"sequence":1}'),
                        ('legacy_anchor',json.dumps({**grant,'initial_applied_sequence':1})),
                        ('publisher_binding',json.dumps({**grant,'publisher_manifest_sha256':'a'*64}))]:
        r=copy.deepcopy(base);r['raw_request']=value;add('raw_'+label,r)
    r=copy.deepcopy(base);r['context']['stopping']=True;add('stop_before_open',r)
    r=copy.deepcopy(base);r['now_ns']=created-1;add('clock_before_creation',r)
    for value in [created+20_000_000_000,created+20_000_000_001]:
        r=copy.deepcopy(base);r['now_ns']=value;add('deadline_'+str(value),r,False,'expired')
    for op,completed,state in [('replay',False,'prepared'),('close',True,'closed'),
        ('close_then_replay',False,'closed'),('close_before_open',False,'closed')]:
        r=copy.deepcopy(base);r['operation']=op;add('lifecycle_'+op,r,completed,state)
    for label,changes,delta,state in [
        ('healthy',{},1_000_000,'prepared'),('capability_lost',{'worker_live':False},1_000_000,'rejected'),
        ('fixture_lost',{'fixture_live':False},1_000_000,'rejected'),
        ('recorder_lost',{'recorder_live':False},1_000_000,'rejected'),
        ('source_invalid',{'source_inputs_valid':False},1_000_000,'rejected'),
        ('reference_changed',{'ready_generation':2},1_000_000,'rejected'),
        ('snapshot_changed',{'ready_snapshot_sha256':'9'*64},1_000_000,'rejected'),
        ('version_changed',{'version':{**version,'model':2}},1_000_000,'rejected'),
        ('physical_writer_appeared',{'physical_publishers':1},1_000_000,'rejected'),
        ('lease_expired',{},400_000_001,'rejected'),('stopping',{'stopping':True},1_000_000,'closed'),
        ('deadline_expired',{},17_000_000_000,'expired')]:
        r=copy.deepcopy(base);r.update(operation='poll',post_ns=now+delta,post_context=copy.deepcopy(context))
        r['post_context'].update(changes);add('post_'+label,r,True,state)
    r=copy.deepcopy(base);r.update(operation='poll_then_replay',post_ns=now+400_000_001,post_context=context)
    add('terminal_lease_cannot_reopen',r,False,'rejected')
    binary=D/'build/formal_prepare_attempt01/formal_prepare_probe'
    inputs=[I/'native/formal_prepare_gate_v1.hpp',I/'native/formal_prepare_probe.cpp',
            I/'native/p1_full_contract.hpp',I/'native/p1_resources.hpp',profile,frozen_path,
            Path(__file__).resolve(),binary]
    before={str(p):pin(p) for p in inputs}
    create(D/'verification/formal_prepare_cases_manifest_v1.json',{'seeded_component_only':True,'cases':cases})
    started=time.monotonic()
    result=subprocess.run([str(binary)],input=b''.join(data(c['request']) for c in cases),capture_output=True,timeout=60)
    (D/'verification/formal_prepare_stdout_v1.jsonl').write_bytes(result.stdout)
    (D/'verification/formal_prepare_stderr_v1.log').write_bytes(result.stderr)
    outputs=[json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode==0 and len(outputs)==len(cases)
    for case,output in zip(cases,outputs):
        case['actual']=output
        case['passed']=(output['operation_completed']==case['expected_completed'] and output['state']==case['expected_state'])
        if 'evidence' in output:
            e=output['evidence'];case['passed'] &= all(e[k]==0 for k in ['physical_publishers_permitted','solve_jobs_permitted','decisions_permitted','applied_messages_permitted'])
            case['passed'] &= all(e[k] is False for k in ['stage_qualified','execute_qualified','formal_freeze_qualified'])
    after={p:pin(Path(p)) for p in before}
    report={'schema':'B5-formal-no-output-preparation-core-cases/v1',
        'passed':all(c['passed'] for c in cases) and before==after,'case_count':len(cases),'cases':cases,
        'failed_cases':[c['name'] for c in cases if not c['passed']],'elapsed_seconds':time.monotonic()-started,
        'input_sha256_before':before,'input_sha256_after':after,'seeded_component_only':True,
        'live_owned_endpoint_authentication_proven':False,'ROS_runs':0,'stage_qualified':False,
        'execute_qualified':False,'research_conclusion':False}
    create(D/'verification/formal_prepare_cases_v1.json',report)
    print(json.dumps({k:report[k] for k in ['passed','case_count','failed_cases','elapsed_seconds']}))
    return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
