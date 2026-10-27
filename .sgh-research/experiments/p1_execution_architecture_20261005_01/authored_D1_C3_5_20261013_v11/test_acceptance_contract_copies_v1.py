#!/usr/bin/env python3
"""Coherent re-pinned contract copies must not erase registered requirements."""
import copy,json,subprocess,sys
from pathlib import Path
import acceptance_core_v1 as C
import check_acceptance_v1 as A

def main():
    root=A.D/'negatives/contract_copies_v1';root.mkdir(exist_ok=False)
    original=A.D/'preregister/acceptance_contract_v3.json';raw=original.read_bytes();before=C.digest(raw)
    base=C.strict_json(raw);A.validate_contract(base)
    cases=[]
    def case(name,change,expected):
        altered=copy.deepcopy(base);change(altered);path=root/(name+'.json')
        A.write(path,altered);rebound_sha=C.digest(path.read_bytes());reason=None
        try:A.validate_contract(C.strict_json(path.read_bytes()))
        except (ValueError,TypeError,KeyError) as e:reason=type(e).__name__+': '+str(e)
        passed=reason is not None and expected in reason
        cases.append({'case':name,'copy':str(path),'recomputed_copy_sha256':rebound_sha,'expected_rejection':expected,'actual':reason,'passed':passed})
    case('empty_identity',lambda x:x.update(identity_pins=[]),'identity_population')
    case('empty_records',lambda x:x.update(record_pins=[]),'record_population')
    case('identity_omitted',lambda x:x['identity_pins'].pop(),'identity_population')
    case('record_SHA_rebound',lambda x:x['record_pins'][0].update(sha256='0'*64),'record_population')
    case('source_SHA_rebound',lambda x:x['identity_pins'][0].update(sha256='0'*64),'identity_population')
    case('required_components_weakened',lambda x:x.update(required_components=['identity_closure']),'component_dependency')
    case('phase_requires_weakened',lambda x:x.update(phase_requires={p:['identity_closure'] for p in C.PHASES}),'phase_dependency')
    case('adapter_removed',lambda x:x.update(job_rule_adapters={}),'rule_adapters')
    case('deferred_removed',lambda x:x.update(deferred_rules={}),'deferred_conditions')
    case('unknown_promoted',lambda x:x['deferred_rules']['engineering_execution_time_policy'].update(status='passed'),'deferred_conditions')
    case('preregister_rebound_to_other_valid_pin',lambda x:x.update(preregister=x['identity_pins'][0]),'execution_preregister')
    case('wire_case_and_requirement_removed',lambda x:(x['jobs'].pop(),x['required_components'].pop()),'component_dependency')
    case('wrong_registered_dataset',lambda x:x['jobs'][0]['args'].__setitem__(1,str(A.PARENT/'runs/owned_C3_4_expired_01/checker_inputs.json')),'dataset_arguments')
    case('job_identity_traversal',lambda x:x['jobs'][0].update(id='../escape'),'normalized_job_identity')
    case('profile_promoted',lambda x:x.update(profile='actual-execute'),'profile_author')
    case('stage_support_enabled',lambda x:x.update(stage_support=['M4']),'cannot_enable_stage')
    case('new_runtime_launch_flag',lambda x:x.update(new_runtime_launches=True),'runtime_scope')
    optimized=[sys.executable,'-O',str(A.N/'check_acceptance_v1.py'),'--contract',str(original),'--contract-sha',before,
               '--output-dir',str(root/'optimized_must_not_exist')]
    result=subprocess.run(optimized,capture_output=True,text=True,timeout=10)
    A.write(root/'optimized_actual_output.json',{'argv':optimized,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    cases.append({'case':'optimized_interpreter','passed':result.returncode!=0 and 'optimization_level_zero_required' in result.stderr and not (root/'optimized_must_not_exist').exists(),
                  'returncode':result.returncode,'no_job_or_output_directory_created':not (root/'optimized_must_not_exist').exists()})
    unchanged=C.digest(original.read_bytes())==before
    final={'schema':'p1-C3.5-coherent-contract-copy-negatives/v1','passed':unchanged and all(c['passed'] for c in cases),
           'cases':cases,'count':len(cases),'original_contract_sha256':before,'original_contract_unchanged':unchanged,
           'mode':'altered contract copies have coherent new SHA; rejection is registered semantic population/matrix, not old digest only',
           'no_original_raw_changed':True,'no_ROS_nodes_launched':True,'qualifications':{k:False for k in C.QUALIFICATIONS}}
    A.write(root/'result.json',final);print(json.dumps({'passed':final['passed'],'count':len(cases),'failed':[c['case'] for c in cases if not c['passed']]}))
    return 0 if final['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
