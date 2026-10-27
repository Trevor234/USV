#!/usr/bin/env python3
"""Source-bound classification of the one failed M4 startup; never pass the run."""
import hashlib
import json
from pathlib import Path

D=Path(__file__).resolve().parent
R=D/'runs/owned_normal20s_01'


def pin(p):
    b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def main():
    launch=json.loads((D/'evidence/normal_launch_v1.json').read_bytes())
    result=json.loads((R/'driver_result.json').read_bytes())
    events=[json.loads(x) for x in (R/'driver_events.jsonl').read_bytes().splitlines()]
    spawned=[x['role'] for x in events if x['type']=='role_spawned']
    assert spawned==['fixture','worker','recorder'] and result['passed'] is False and launch['passed'] is False
    assert not (R/'regulator/manifest.json').exists() and not (R/'regulator/grant.json').exists()
    assert all(r['group_empty'] for r in result['closed_roles']) and all(r['group_empty'] for r in launch['emergency_cleanup'])
    assert all(not r['signals'] for r in launch['emergency_cleanup'])
    recorder=D.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10/recorder/src/owned_recorder.cpp'
    driver=D/'author_r3/owned_m4_driver_v1.py';regulator=D/'author_r3/observer/src/shadow/regulator_owned_execute.cpp'
    rt=recorder.read_text();dt=driver.read_text();gt=regulator.read_text()
    assert 'recorder->subscriptions().size()==topics.size()' in rt
    assert rt.index('if(!prepared)throw')<rt.index('write_create_only(args.manifest')
    assert dt.index("spawn('recorder',rv);rm,rpin=authenticate")<dt.index("spawn('regulator'")
    assert gt.index('own_recorder_=std::make_unique<formal_owned::Peer>')<gt.index('job_pub_=create_publisher')
    inputs={str(p):pin(p) for p in [D/'evidence/normal_launch_v1.json',R/'driver_result.json',R/'driver_events.jsonl',recorder,driver,regulator]}
    lock=json.loads((D/'preflight/prerun_source_lock_v1.json').read_bytes());pins=dict(lock['files'])
    for p,row in json.loads((D/'preflight/execution_tool_input_lock_v1.json').read_bytes())['files'].items():
        assert p not in pins or pins[p]==row;pins[p]=row
    for path,row in pins.items():assert pin(Path(path))==row,path
    worker=[json.loads(x) for x in (R/'worker/source.jsonl').read_bytes().splitlines()]
    assert not any(x.get('type') in ['job_received','candidate','cold_start_policy_result'] for x in worker)
    report={'schema':'M4-first-startup-cycle-evidence-audit/v1','passed':True,'audit_scope':'failure classification and input preservation, not experiment pass',
      'actual_run_passed':False,'actual_roles_spawned':spawned,'Regulator_started':False,'SolveJobs':0,'Candidates':0,'control_API_calls':0,
      'expected_normal_source20s_observed':False,'causal_cycle':['Driver waits full Recorder manifest','Recorder waits subscriptions for all declared topics including future Regulator outputs','Regulator constructor requires full Recorder pin before creating those outputs'],
      'root_cause':'preparation lifecycle policy mismatch; not NMPC numerical rejection or a threshold failure',
      'owned_groups_empty':True,'emergency_signals':0,'closed_role_returncodes':{r['role']:r['returncode'] for r in result['closed_roles']},
      'unchanged_prerun_paths':len(pins),'input_sha256':inputs,'prerun_inputs':pins,
      'M4_normal_component_qualified':False,'M4_stage_qualified':False,'P1_qualified':False,'research_conclusion':False,
      'next_minimal_fix':'authenticate Recorder owned process/binary/argv before its manifest; create new-owner endpoints with zero APIs; require actual complete Recorder manifest/Reader GIDs before grant and every first output',
      'retry_same_registration':False,'next_experiment_requires_new_source_version_and_separate_registration':True}
    with (D/'postrun/failed_start_audit_v1.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({k:report[k] for k in ['passed','actual_run_passed','actual_roles_spawned','control_API_calls','owned_groups_empty','unchanged_prerun_paths']}))


if __name__=='__main__':main()
