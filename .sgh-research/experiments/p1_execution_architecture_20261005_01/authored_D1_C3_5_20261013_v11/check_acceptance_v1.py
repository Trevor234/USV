#!/usr/bin/env python3
"""Execute a pinned bounded-component dependency contract, never launch ROS nodes."""
from __future__ import annotations
import argparse,json,os,re,subprocess,sys,time
from pathlib import Path
import acceptance_core_v1 as C

N=Path(__file__).resolve().parent
PARENT=N.parent/'authored_D1_C3_4_20261013_v10'
D=N.parent.parent/'scheme_A_C3_5_20261013_10'
SCHEMA='p1-C3.5-component-acceptance-result/v1'
REGISTRY=D/'preregister/external_input_registry_v1.json'
REGISTRY_SHA='4756038b43dd3fc318d5b6a7092d2f68e12cb191a541ebc9c6029abeeef3b181'
PREREGISTER={'path':str(D/'preregister/execution_scope_v1.json'),
             'sha256':'dceab65bb91725d0d1d8050db45c626b19b9342713df9142d57b235c003b391d','bytes':1937}
ROOT_TOOLS=('acceptance_core_v1.py','check_acceptance_v1.py','check_preparation_io_v2.py','generate_acceptance_contract_v1.py','test_acceptance_v1.py')
ADAPTERS={'budget_scope':['observed_runtime_budgets','observed_ready_gate','anchor_guard_observed','anchor_execution_contract',
                       'master_clock_hard_bound','plant_hold_interval','worker_io_schedule_wcet','current_dynamic20s',
                       'current_turn_mixed','current_stress_recovery_failed_close']}

def registered_phase_requires():
    return {'B4':['identity_closure','record_identity','normal_owned','normal_atomic','config_domain','current_readiness','budget_scope',
                 'budget_scope__observed_runtime_budgets','budget_scope__observed_ready_gate','budget_scope__anchor_guard_observed',
                 'budget_scope__anchor_execution_contract','budget_scope__current_stress_recovery_failed_close'],
            'M0b':['B4','engineering_execution_time_policy','budget_scope__current_dynamic20s','budget_scope__current_turn_mixed'],
            'B5':['M0b','normal_release','expired_release','preparation_io','immutable_execute_policy_contract'],
            'M4':['B5','new_execute_source_bin','continuous_unique_publisher_handoff','actual_nonzero_and_partial_publish','rho_gap_budget_execution_evidence']}

def registered_deferred_rules():
    return {'engineering_execution_time_policy':{'status':'not_run','evidence':'current finite observations and failclosed gates exist; engineering guarantee assumptions/domain and out-of-domain policy must be selected before execute','scope':'does not require claiming unknown physical WCET or true Master Clock as zero'},
            'immutable_execute_policy_contract':{'status':'not_run','evidence':'this is a bounded evidence acceptance contract; actual unified execute/close/recovery policy remains separate'},
            'new_execute_source_bin':{'status':'not_run','evidence':'no M4 execution version built or launched'},
            'continuous_unique_publisher_handoff':{'status':'not_run','evidence':'no transition from F5 owner to regulator actuator owner performed'},
            'actual_nonzero_and_partial_publish':{'status':'not_run','evidence':'accepted shadow proposal with publish_success=false is not an actuator event'},
            'rho_gap_budget_execution_evidence':{'status':'not_run','evidence':'new execution-level rho/gap/hold policy and actual publish evidence absent'}}

def registered_inputs():
    reader=C.Reader();raw=reader.raw(REGISTRY);C.require(C.digest(raw)==REGISTRY_SHA,'fixed_external_registry_SHA_differs')
    registry=C.strict_json(raw);identities=list(registry['identity_pins'])
    identities.append({'path':str(REGISTRY),'sha256':REGISTRY_SHA,'bytes':len(raw)})
    for name in ROOT_TOOLS:
        p=N/name;data=reader.raw(p);identities.append({'path':str(p),'sha256':C.digest(data),'bytes':len(data)})
    return identities,registry['record_pins']

def same_pin_population(actual,expected,code):
    C.require(type(actual) is list and len(actual)==len(expected),code)
    C.require(all(type(p) is dict and set(p)=={'path','sha256','bytes'} for p in actual),code)
    C.require(len({p['path'] for p in actual})==len(actual),code)
    C.require(sorted(actual,key=lambda p:p['path'])==sorted(expected,key=lambda p:p['path']),code)

def registered_jobs():
    positive=PARENT/'runs/owned_C3_4_positive_01';expired=PARENT/'runs/owned_C3_4_expired_01'
    ambiguous=PARENT/'runs/owned_C3_4_ambiguous_preparation_01';parent_batch=D.parent/'scheme_A_C3_4_20261013_09'
    specs={
      'normal_owned':(PARENT/'check_owned_fixture.py',['--inputs',str(positive/'checker_inputs.json'),'--output','{output}'],'passed'),
      'normal_atomic':(PARENT/'check_atomic_observation_v2.py',['--run',str(positive),'--output','{output}'],'passed'),
      'normal_release':(PARENT/'check_release_observation_v1.py',['--run',str(positive),'--output','{output}'],'passed'),
      'expired_release':(PARENT/'check_release_observation_v1.py',['--run',str(expired),'--output','{output}'],'passed'),
      'config_domain':(PARENT/'config_scope_v1.py',['--run',str(positive),'--output','{output}'],'passed'),
      'preparation_io':(N/'check_preparation_io_v2.py',['--run',str(ambiguous),'--output','{output}'],'passed'),
      'current_readiness':(N/'validate_readiness_c35_v1.py',['--contract',str(D/'readiness/readiness_c35_contract_v1.json'),'--output','{output}'],'component_suite_passed'),
      'budget_scope':(N/'budget_scope_v1.py',['--output','{output}'],'passed')}
    for case in ('invalid_foreign','fatal','instance','expired','duplicate','no_valid'):
        specs['wire_'+case]=(PARENT/'check_lease_wire_v1.py',['--run',str(parent_batch/'C_lease/wire_matrix01'/case),'--output','{output}'],'passed')
    return specs

def write(path,value):
    path=Path(path)
    with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')

def validate_contract(contract):
    C.require(contract['schema']=='p1-C3.5-bounded-acceptance-contract/v1','contract_schema')
    C.require(contract['profile']==C.PROFILE and contract['author_directory']==str(N),'contract_profile_author')
    C.require(contract['runtime_source_root']==str(PARENT) and contract['new_runtime_launches'] is False,'contract_runtime_scope')
    C.require(contract['stage_support']==[],'bounded_component_contract_cannot_enable_stage')
    C.require(contract['record_lock_semantics']=='retrospective frozen N10 raw records; not independent pre-run qualification','record_semantics')
    C.require(contract['preregister']==PREREGISTER,'registered_execution_preregister_required')
    identities,records=registered_inputs()
    same_pin_population(contract['identity_pins'],identities,'complete_registered_identity_population_required')
    same_pin_population(contract['record_pins'],records,'complete_registered_record_population_required')
    C.require(contract['required_components']==['identity_closure','record_identity',*registered_jobs()], 'complete_component_dependency_set_required')
    C.require(contract['phase_requires']==registered_phase_requires(),'registered_phase_dependency_matrix_required')
    C.require(contract['job_rule_adapters']==ADAPTERS,'registered_rule_adapters_required')
    C.require(contract['deferred_rules']==registered_deferred_rules(),'registered_deferred_conditions_required')
    ids=[j['id'] for j in contract['jobs']]
    C.require(all(type(x) is str and re.fullmatch(r'[a-z0-9_]{1,64}',x) for x in ids),'normalized_job_identity')
    C.require(len(ids)==len(set(ids)) and 1<=len(ids)<=24,'job_population')
    registered=registered_jobs();C.require(set(ids)==set(registered),'complete_registered_component_population_required')
    allowed_names={'check_owned_fixture.py','check_release_observation_v1.py','check_atomic_observation_v2.py',
                   'config_scope_v1.py','check_lease_wire_v1.py','check_preparation_io_v2.py',
                   'validate_readiness_c35_v1.py','budget_scope_v1.py'}
    for job in contract['jobs']:
        tool=Path(job['tool']['path'])
        C.require(tool.parent in (N,PARENT) and tool.name in allowed_names,'unregistered_job_tool')
        C.require(type(job['args']) is list and all(type(x) is str for x in job['args']),'job_args_shape')
        C.require(job['args'].count('{output}')==1 and job['result_key'] in ('passed','component_suite_passed'),'job_output_shape')
        expected_tool,expected_args,expected_key=registered[job['id']]
        C.require(tool==expected_tool and job['args']==expected_args and job['result_key']==expected_key,'registered_job_dataset_arguments_differ')
        C.require(type(job['budget_seconds']) is int and 1<=job['budget_seconds']<=60,'job_offline_budget')
    C.require(all(row['status'] in ('unknown','not_run') and type(row['status']) is str for row in contract['deferred_rules'].values()),'deferred_cannot_self_declare_pass')

def evaluate(contract_path,contract_sha,output_dir):
    C.require(sys.flags.optimize==0,'optimization_level_zero_required')
    reader=C.Reader(seconds=300,max_bytes=768*1024*1024)
    raw=reader.raw(contract_path);C.require(C.digest(raw)==contract_sha,'acceptance_contract_SHA_differs')
    contract=C.strict_json(raw);validate_contract(contract)
    out=Path(output_dir);C.require(out.is_absolute() and '..' not in out.parts and out.is_relative_to(D),'fresh_batch_output_required')
    C.require(not any(p.is_symlink() for p in out.parents),'output_symlink_parent_forbidden')
    out.mkdir(parents=True,exist_ok=False);start=time.monotonic_ns();rules={};execution=[]
    try:
        reader.verify(contract['preregister'])
        for pin in contract['identity_pins']:reader.verify(pin)
        for pin in contract['record_pins']:reader.verify(pin)
        rules['identity_closure']={'status':'passed','evidence':'fixed current tool/source/bin pins verified by nofollow stable read'}
        rules['record_identity']={'status':'passed','evidence':'all declared original closed records match retrospective fixed SHA'}
        for job in contract['jobs']:
            reader.verify(job['tool']);report_path=out/(job['id']+'.json')
            args=[str(report_path) if a=='{output}' else a for a in job['args']]
            command=[sys.executable,'-B',job['tool']['path'],*args]
            with (out/(job['id']+'.log')).open('xb') as log:
                child_env=dict(os.environ);child_env.pop('PYTHONOPTIMIZE',None)
                try:rc=subprocess.run(command,env=child_env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=job['budget_seconds']).returncode
                except subprocess.TimeoutExpired:rc=124
            if report_path.exists():
                report=reader.json(report_path);status=C.report_result(report,job['result_key'],rc)
            else:report=None;status='failed'
            rules[job['id']]={'status':status,'report':str(report_path),'returncode':rc,'scope':job['scope']}
            for field in contract.get('job_rule_adapters',{}).get(job['id'],[]):
                name=job['id']+'__'+field
                if status=='passed':
                    row=report['rules'][field];C.exact_status(row['status']);rules[name]={**row,'derived_from':job['id']}
                else:rules[name]={'status':'not_run','derived_from':job['id'],'evidence':'parent checker failed; rule not accepted'}
            execution.append({'id':job['id'],'argv':command,'returncode':rc,'status':status})
        # Deferred conditions are distinct from results of executed jobs.
        for name,row in contract['deferred_rules'].items():
            C.require(name not in rules,'deferred_rule_collision');rules[name]=row
        assessment=C.assess(rules,contract['required_components'],contract['phase_requires'],contract['profile'])
        unchanged=reader.unchanged();C.require(unchanged,'fixed_inputs_or_tools_changed_during_acceptance')
        result={'schema':SCHEMA,'passed':assessment['component_acceptance_passed'],'contract':str(contract_path),
                'contract_sha256':contract_sha,'rules':rules,'assessment':assessment,'jobs':execution,
                'input_SHA_before':reader.hashes,'fixed_inputs_unchanged':True,'elapsed_ns':time.monotonic_ns()-start,
                'new_ROS_nodes_launched':False,'runtime_qualification_claimed':False,
                'qualifications':assessment['qualifications']}
    except Exception as error:
        result={'schema':SCHEMA,'passed':False,'contract':str(contract_path),'contract_sha256':contract_sha,
                'error':type(error).__name__+': '+str(error),'rules':rules,'jobs':execution,
                'qualifications':{k:False for k in C.QUALIFICATIONS},'new_ROS_nodes_launched':False}
    write(out/'result.json',result);return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--contract',type=Path,required=True)
    p.add_argument('--contract-sha',required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    result=evaluate(a.contract,a.contract_sha,a.output_dir)
    print(json.dumps({k:result.get(k) for k in ('passed','error','assessment')},sort_keys=True));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
