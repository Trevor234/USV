#!/usr/bin/env python3
"""Pin selected role versions, actual loader closure, core reuse, and one run."""
import ast
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
A=D/'author'
sys.path.insert(0,str(D))
from source_reader_helpers_v1 import masked


def pin(p):
    p=Path(p).resolve(strict=True);b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def emit(p,obj):
    # Create-only by default; an identical pre-existing artifact from an aborted
    # attempt of the SAME run is accepted verbatim instead of being overwritten.
    if p.exists():
        import json as _j
        assert _j.loads(p.read_bytes())==obj,'refusing to overwrite a different artifact: '+str(p)
        return
    with p.open('x') as f:json.dump(obj,f,indent=2,sort_keys=True);f.write('\n')


def body(text,name):
    match=__import__('re').search(r'\n  (?:static )?[\w:<>*&]+\s+'+name+r'\(',text);assert match,name
    mask=masked(text);begin=mask.index('{',match.start());depth=1;end=begin+1
    while depth:
        if mask[end]=='{':depth+=1
        elif mask[end]=='}':depth-=1
        end+=1
    return text[begin:end]


def main():
    b2=D/'build/fault_attempt05';b3=b2
    j2=json.loads((b2/'build_manifest_v1.json').read_bytes());j3=json.loads((b3/'build_manifest_v1.json').read_bytes());assert j2['passed'] and j3['passed']
    components=json.loads((D/'verification/component_verification_v5.json').read_bytes());assert components['passed']
    assert json.loads((D/'verification/recorder_process_verification_v5.json').read_bytes())['passed']
    assert json.loads((D/'verification/native_entry_rejections_v5.json').read_bytes())['passed']
    parent=D.parent/'scheme_A_owned_business_start_20261020_39/author/observer/src/shadow/regulator_shadow_observer.cpp'
    child=A/'observer/src/shadow/regulator_owned_execute.cpp';old=parent.read_text();new=child.read_text()
    same={}
    for name in ['prepare_loop','candidate','activate_candidate','predict','odom','imu','path','profile','clock','snapshot_locked','snapshot_source_locked','capture_final_source_locked','materialize_activation_trace']:
        x,y=body(old,name),body(new,name);assert x==y,name;same[name]={'bytes':len(x),'sha256':hashlib.sha256(x.encode()).hexdigest()}
    wp=D.parent/'scheme_A_V2_watchdog_lease_20261019_35/worker_author/worker/solver_worker.cpp'
    # Work loop source contains the numerical backend ownership and cannot drift.
    assert body(wp.read_text(),'work')==body((D/'author/worker/solver_worker_m4.cpp').read_text(),'work')
    old_model=D.parent/'scheme_A_longitudinal_20261016_19/author_snapshot/owner_common/nominal_history.hpp'
    old_ref=D.parent/'scheme_A_longitudinal_20261016_19/author_snapshot/fixture/controlled_reference.hpp'
    assert (A/'common/nominal_history.hpp').read_bytes()==old_model.read_bytes()
    assert (A/'fixture/controlled_reference.hpp').read_bytes()==old_ref.read_bytes()
    proof={'schema':'M4-selected-source-core-reuse-audit/v1','passed':True,'unchanged_Regulator_method_bodies':same,
       'unchanged_Worker_work_loop_sha256':hashlib.sha256(body(wp.read_text(),'work').encode()).hexdigest(),
       'nominal_model_and_reference_byte_identical_to_calibration':True,'selected_Regulator_source':{str(child):pin(child)},
       'parent_Regulator_source':{str(parent):pin(parent)},'profile_numbers_tuned':False,
       'qualification_scope':'source reuse and explicit shell differences; no new actual output proof yet'}
    emit(D/'verification/source_core_reuse_v1.json',proof)
    roles={}
    for role,target,build in [('regulator','p1_m4_regulator_owned',j3),('worker','p1_m4_worker_owned',j2),('fixture','p1_m4_fixture_owned',j2)]:
        row=build['targets'][target];roles[role]={'binary':row['path'],'binary_sha256':row['sha256'],'source_bundle':build['source_bundle']}
    recorder=D.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10'
    rec=recorder/'recorder/build01/p1_owned_recorder';bundle=recorder/'recorder_source_bundle_C3_4_v1.json'
    assert pin(rec)['sha256']=='d1b91109081c84d4427510d752e926249a0779c44e84b36509bbfa1dac800002'
    assert pin(bundle)['sha256']=='61da30907164a3e55ba3aa41e5609d9b80562982133c52cc6135d8283bb99c08'
    roles['recorder']={'binary':str(rec),'binary_sha256':pin(rec)['sha256'],'source_bundle':{'path':str(bundle),'sha256':pin(bundle)['sha256']}}
    setupfile=D.parent/'scheme_A_owned_business_start_20261020_39/author/build_c33_v9.py'
    tree=ast.parse(setupfile.read_bytes());setup=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SETUP' for t in n.targets))
    loader={}
    for role,row in roles.items():
        script=D/'verification'/('loader_'+role+'_v1.sh');script.write_text('set -e\n'+setup+'\nexec /usr/bin/ldd '+shlex.quote(row['binary'])+'\n')
        result=subprocess.run(['/bin/bash',str(script)],capture_output=True,timeout=20)
        (D/'verification'/('loader_'+role+'_v1.log')).write_bytes(result.stdout+result.stderr)
        assert result.returncode==0 and b'not found' not in result.stdout
        libs={}
        for word in result.stdout.decode().split():
            if word.startswith('/') and Path(word).is_file():
                p=Path(word).resolve(strict=True);libs[str(p)]=pin(p)
        loader[role]={'binary':{row['binary']:pin(Path(row['binary']))},'runtime_libraries':libs}
    emit(D/'verification/actual_loader_closure_v1.json',{'schema':'M4-selected-actual-loader-closure/v1','passed':True,'roles':loader})
    driver=A/'owned_m4_fault_driver_v1.py';assert pin(driver)['sha256']==j2['driver_tool_sha256']==j3['driver_tool_sha256']
    registry={'schema':'M4-owned-runtime-registry-v1','scope':'M4_owned_local_nominal_only_v1','roles':roles,
       'driver_tool_sha256':pin(driver)['sha256'],'driver':str(driver),'regulator_source':str(child),
       'regulator_source_sha256':pin(child)['sha256'],'production_physical_release_enabled':False,
       'source_scope':'owned local nominal .05 m/s component; not original F5 plant/reference identity qualification'}
    emit(D/'implementation/selected_runtime_registry_v1.json',registry)
    c=json.loads((D.parent/'scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json').read_bytes())
    topics={'schema':'p1-owned-recorder-topics/v1','topics':{
      '/clock':'rosgraph_msgs/msg/Clock',c['input_topics']['odom']:'nav_msgs/msg/Odometry',c['input_topics']['imu']:'sensor_msgs/msg/Imu',
      c['input_topics']['path']:'nav_msgs/msg/Path',c['input_topics']['profile']:'std_msgs/msg/Float64MultiArray',
      '/p1/worker_capability':'usv_research_interfaces/msg/WorkerCapability','/p1/solve_job':'usv_research_interfaces/msg/SolveJob',
      '/p1/solve_candidate':'usv_research_interfaces/msg/SolveCandidate','/p1/execution_decision':'usv_research_interfaces/msg/ExecutionDecision',
      '/research/control/applied':'usv_research_interfaces/msg/AppliedControl',c['output_topics']['left']:'std_msgs/msg/Float64',c['output_topics']['right']:'std_msgs/msg/Float64'}}
    emit(D/'implementation/m4_topics_v1.json',topics)
    (D/'runs').mkdir(exist_ok=True)
    parentfreeze=D.parent/'scheme_A_formal_execute_profile_20261020_47/freeze'
    base={'scope':registry['scope'],'domain_id':120,'production_physical_release_enabled':False,
       'registry':str(D/'implementation/selected_runtime_registry_v1.json'),'registry_sha256':pin(D/'implementation/selected_runtime_registry_v1.json')['sha256'],
       'contract':str(parentfreeze/'p1_execution_contract_v1.json'),'contract_sha256':'19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a',
       'index':str(parentfreeze/'freeze_index_v1.json'),'index_sha256':'1d750a7eeb32f379f2be5dd516533f6f785e091c6b30082dda68e51b3f100081',
       'topics':str(D/'implementation/m4_topics_v1.json'),'topics_sha256':pin(D/'implementation/m4_topics_v1.json')['sha256'],
       'max_seconds':45,'automatic_retries':0,'outer_timeout_seconds':90,
       'fault_injection_enabled':False,
       'old_normal_or_fault_qualifications_transferred':False,'M4_stage_qualified':False,'P1_qualified':False}
    r1={**base,'schema':'M4-owned-fault-run-v1','case':'R1-owned-pre-grant-cancel',
        'run_id':'M4_owned_fault_20261021_53_R1','output':str(D/'runs/owned_fault_R1_01'),
        'boundary':'four roles authenticated; full Recorder manifest bound in ready.json; Regulator ready.json written; grant.json absent',
        'stimulus':{'target':'regulator','signal':'SIGINT','count':1,'sent_by':'driver',
                    'authenticated_before_send':['pid','process_start_ticks','exe','binary_sha256','argv','pgid','sid']},
        'expected_exit':{'regulator':3,'fixture':0,'worker':0,'recorder':0},
        'expected_signals':{'regulator':[],'fixture':['SIGINT'],'worker':['SIGINT'],'recorder':['SIGINT']},
        'required_source_rows':['owned_execute_waiting','owned_prepare_ready','owned_prepare_closed_before_API','owned_reception_closed'],
        'forbidden_source_rows':['job','owned_API_pair','regulator_shutdown','owned_execute_grant_accepted','candidate_registration'],
        'declared_exceptions':['witness observation_complete=false is expected with zero ticks',
                               'regulator exit 3 is the documented audit-close code for zero ticks'],
        'minimum_assertions':['no grant before stimulus','no API/Job/Decision','four groups empty','exact pre-registered exits']}
    emit(D/'implementation/R1_registration_v1.json',r1)
    r2={**base,'schema':'M4-owned-fault-run-v1','case':'R2-owned-worker-exit',
        'run_id':'M4_owned_fault_20261021_53_R2','output':str(D/'runs/owned_fault_R2_01'),
        'boundary':'first owned_API_pair with kind=accepted, returned=[true,true], command_invalid=false',
        'stimulus':{'target':'worker','signal':'SIGKILL','count':1,'sent_by':'driver',
                    'authenticated_before_send':['pid','process_start_ticks','exe','binary_sha256','argv','pgid','sid']},
        'expected_exit':{'worker':-9,'regulator':0,'fixture':0,'recorder':0},
        'expected_signals':{'worker':[],'regulator':['SIGINT'],'fixture':['SIGINT'],'recorder':['SIGINT']},
        'observation_window':{'min_fallback_pairs':5,'max_after_stimulus_ns':3000000000},
        'required_source_rows':['worker_unusable_transition','regulator_shutdown'],
        'declared_exceptions':['worker_summary absent','capability_source terminal absent',
                               'one unterminated trailing line in worker/source.jsonl',
                               'at most two stored candidates without a worker Source row',
                               'at most one committed job with no candidate',
                               'witness normal_contract_qualified is not fault-aware'],
        'minimum_assertions':['no accepted registration after transition','no job committed after transition',
                              'fallback ramp within rho/gap/span','worker rc -9 with no driver signal',
                              'shutdown normal_contract_complete=false','four groups empty']}
    emit(D/'implementation/R2_registration_v1.json',r2)
    r3={**base,'schema':'M4-owned-fault-run-v1','case':'R3-owned-capability-lease-expiry',
        'run_id':'M4_owned_fault_20261021_53_R3','output':str(D/'runs/owned_fault_R3_01'),
        'boundary':'first owned_API_pair with kind=accepted, returned=[true,true], command_invalid=false',
        'stimulus':{'target':'worker','signal':'SIGSTOP','count':1,'sent_by':'driver',
                    'resume':'SIGCONT after the Regulator goes terminal',
                    'authenticated_before_send':['pid','process_start_ticks','exe','binary_sha256','argv','pgid','sid']},
        'expected_exit':{'worker':0,'regulator':0,'fixture':0,'recorder':0},
        'expected_signals':{'worker':['SIGINT'],'regulator':[],'fixture':['SIGINT'],'recorder':['SIGINT']},
        'expected_transition_reason':'worker_capability_expired',
        'observation_window':{'min_post_transition_pairs':1,'max_after_stimulus_ns':5000000000},
        'required_source_rows':['worker_unusable_transition','regulator_shutdown'],
        'rationale':('SIGSTOP cannot satisfy the pidfd exit poll, so this isolates the 600 ms '
                     'capability receipt lease from worker death. The 1 s active watchdog cannot '
                     'fire first because unusable_locked() is idempotent and the lease check '
                     'precedes it inside check_worker_locked().'),
        'declared_exceptions':['witness normal_contract_qualified is not fault-aware'],
        'minimum_assertions':['transition reason is worker_capability_expired',
                              'candidate and pending cleared at transition',
                              'post-expiry fallback ramp within rho/gap/span',
                              'worker resumed and exits 0','four groups empty']}
    emit(D/'implementation/R3_registration_v1.json',r3)
    emit(D/'implementation/W1_watchdog_not_isolable_v1.json',{
        'schema':'M4-owned-fault-watchdog-feasibility/v1',
        'case':'W1-owned-active-watchdog',
        'status':'not_isolable_by_external_signal',
        'reason':('The 1 s active watchdog requires worker_active_!=0 for >1 s while the Worker '
                  'keeps publishing capability. Any external signal that freezes the Worker '
                  'also stops capability publication, so the 600 ms receipt lease expires first; '
                  'unusable_locked() is idempotent, so the watchdog branch can never run after '
                  'that. Isolating it requires a code path where capability keeps arriving while '
                  'the active job stalls, i.e. a fault-capable Worker, which the frozen contract '
                  'forbids (fault_injection_enabled=false) and the Regulator explicitly refuses '
                  '(regulator_owned_execute.cpp:99-100).'),
        'closed_by_this_batch':False,
        'requires':['fault-capable Worker variant with an approved contract',
                    'or a Driver-managed native stall that leaves capability publishing intact'],
        'M4_stage_qualified':False,'F6_qualified':False,'P1_qualified':False})
    emit(D/'evidence/F5_and_calibrated_nominal_scope_v1.json',{'schema':'M4-current-source-asset-applicability/v1',
       'nominal_hydro19_equals_frozen_parent':c['hydro']==json.loads((D.parent/'scheme_A_current_normal_source_20261020_46/author_r2/pair_wakeup_contract_v1.json').read_bytes())['hydro'],
       'same_calibrated_source_model_and_reference_files':{str(old_model):pin(old_model),str(old_ref):pin(old_ref)},
       'calibrated_reference_speed_m_s':.05,'original_F5_plant_reference_identity_qualified':False,
       'component_scope':'first owned outlet confirmation against calibrated local nominal .05 source; no plant/Gazebo/hardware or F5 full normal-case claim',
       'general_1_2_turn_mixed_WCET_or_GP_data_qualification':False})
    paths={}
    for build in [j2,j3]:
        for key,row in build['compiler_dependencies'].items():paths[key]=row
    for role in roles.values():
        paths[role['binary']]=pin(Path(role['binary']));paths[role['source_bundle']['path']]=pin(Path(role['source_bundle']['path']))
        r=json.loads(Path(role['source_bundle']['path']).read_bytes())['files'];r=r.values() if type(r) is dict else r
        for row in r:paths[str(Path(row['path']).resolve(strict=True))]=pin(Path(row['path']))
    for group in loader.values():paths.update(group['runtime_libraries'])
    for root in ['implementation','verification']:
        for f in (D/root).rglob('*'):
            if f.is_file():paths[str(f)]=pin(f)
    paths[str(driver)]=pin(driver)
    emit(D/'preflight/prerun_source_lock_v1.json',{'schema':'M4-owned-fault-source-lock/v1','files':paths,'file_count':len(paths),
       'selected_roles':roles,'run_registrations':[str(D/'implementation/R1_registration_v1.json'),str(D/'implementation/R2_registration_v1.json'),str(D/'implementation/R3_registration_v1.json')],'automatic_retries':0})
    print(json.dumps({'passed':True,'core_methods_identical':len(same),'locked_paths':len(paths),'roles':list(roles),'normal_run_registered_not_started':True}))


if __name__=='__main__':main()
