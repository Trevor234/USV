"""Pure seeded-context identity rejection and frozen actual prefix distinctness; no ROS."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(D/'author'))
from fresh_recovery_v1 import validate_fresh,healthy_pairs
old=json.loads((D/'author/previous_lease_close_proof_v1.json').read_bytes());run='unit_fresh_context';start=old['old_all_groups_cleanup_observed_ns']+1
manifests=deepcopy(old['old_role_manifests'])
for role,m in manifests.items():
    m['run_id']=run+('-publisher' if role=='publisher' else '');m['pid']+=1000000;m['process_start_ticks']+=1000000
manifests['worker']['worker_instance']=hashlib.sha256(b'unit fresh identity context only').hexdigest()
manifests['observer']['effective_parameters']['diagnostic_c38_mode']['value']='none'
assert validate_fresh(old,manifests,run,start)['fresh_owned_identities_verified'];cases=[]
for name in ['old_run','early_prepare','old_group_open','old_PID_start','old_Worker_instance','changed_ELF','callback_gate_on','Worker_stimulus_on']:
    previous=deepcopy(old);new=deepcopy(manifests);which_run=run;when=start
    if name=='old_run':which_run=old['run_id']
    elif name=='early_prepare':when=old['old_all_groups_cleanup_observed_ns']
    elif name=='old_group_open':previous['old_cleanup']['worker']['remaining_members']=[dict(pid=1)]
    elif name=='old_PID_start':new['worker']['pid']=old['old_role_manifests']['worker']['pid'];new['worker']['process_start_ticks']=old['old_role_manifests']['worker']['process_start_ticks']
    elif name=='old_Worker_instance':new['worker']['worker_instance']=old['old_role_manifests']['worker']['worker_instance']
    elif name=='changed_ELF':new['observer']['binary_sha256']='0'*64
    elif name=='callback_gate_on':new['observer']['effective_parameters']['diagnostic_c38_mode']['value']='worker-gate'
    else:new['worker']['effective_parameters']['diagnostic_v2_policy']['value']='pre_native_once_after_completed_v1'
    try:validate_fresh(previous,new,which_run,when)
    except ValueError as e:cases.append(dict(case=name,rejected=True,reason=str(e)))
    else:raise AssertionError('invalid entry admitted:'+name)
R=Path(old['run_root']);paths=[R/'observer/source.jsonl',R/'publisher/controlled_source.jsonl']
def pin(p):
    b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
before={str(p):pin(p) for p in paths};source,pub=[[json.loads(x) for x in p.read_bytes().splitlines()] for p in paths]
pairs=healthy_pairs(source,pub);assert pairs
accepted=next(r for r in source if r.get('type')=='decision' and r.get('accepted'))
duplicate=healthy_pairs(source+[deepcopy(accepted)],pub);assert len(duplicate)==len(pairs)
assert healthy_pairs([r for r in source if r.get('type')!='controlled_phase_callback'],pub)==[]
assert {p:pin(Path(p)) for p in before}==before
r=dict(passed=True,seeded_identity_context_only=True,no_new_manifest_authentication_claimed=True,
    identity_negative_cases=cases,negative_count=len(cases),duplicate_same_job_does_not_count_twice=True,
    missing_authenticated_phase_has_no_healthy_pair=True,frozen_actual_healthy_pairs=len(pairs),
    input_sha256_before=before,input_sha256_after=before,helper_pin=pin(D/'author/fresh_recovery_v1.py'),
    new_ROS_runs=0,stage_qualified=False,execute_qualified=False,research_conclusion=False)
with (D/'verification/fresh_entry_components_v1.json').open('x') as f:json.dump(r,f,indent=2)
print(json.dumps(dict(passed=True,seeded_identity_negative_cases=8,frozen_actual_pairs=len(pairs),ROS_context_created=False)))
