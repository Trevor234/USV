"""Freeze all current inputs plus current Observer native/build dependency lineage."""
import hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent;P=D.parent/'scheme_A_owned_business_start_20261020_39'
def load(p):return json.loads(Path(p).read_bytes())
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def dump(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')
files={}
def add(p,expected=None):
    p=Path(p);f=pin(p)
    if expected:assert f['sha256']==expected['sha256'] and f['bytes']==expected.get('bytes',f['bytes']),str(p)
    assert str(p) not in files or files[str(p)]==f
    files[str(p)]=f
assert load(D/'preflight/protection_initial_v1.json')['passed'] and load(D/'preflight/source_change_review_v1.json')['passed']
assert load(D/'preflight/theory_veto_V1_v1.json')['verdict']=='GO'
assert load(D/'verification/driver_CLI_v1.json')['passed'] and load(D/'preflight/loader_environment_v2.json')['passed']
assert not load(D/'preflight/runtime_process_scan_before_v1.json')['selected_research_processes']
assert load(P/'postrun/final_QA_v1.json')['passed']
build=load(P/'build/business_observer_attempt01/result.json');assert build['passed'] and build['Native_cases']==38 and build['Native_rc']==0
for n in ['build_manifest_current.json','source_bundles_current.json','fault_self_close_v1.py','business_start_v1.py','runtime/owned_process_supervisor.py']:
    assert (D/'author'/n).read_bytes()==(P/'author'/n).read_bytes()
for p,f in load(P/'preflight/prerun_source_lock_v1.json')['files'].items():add(p,f)
for p in sorted((D/'author').rglob('*')):
    if p.is_file():assert not p.is_symlink();add(p)
for p in D.glob('*.py'):add(p)
for p in (D/'preflight').iterdir():
    if p.is_file():add(p)
add(D/'verification/driver_CLI_v1.json')
for row in load(D/'author/build_manifest_current.json'):
    add(row['binary'],dict(sha256=row['binary_sha256']));add(row['source_bundle']['path'],row['source_bundle'])
    for f in load(row['source_bundle']['path'])['files'].values():add(f['path'],f)
for row in load(D/'preflight/loader_environment_v2.json')['roles'].values():
    for p,f in row['libraries'].items():add(p,f)
dump(D/'preflight/prerun_source_lock_v1.json',dict(files=files,count=len(files),CXX_builds=0,all_five_parent39_ELFs_reused=True,Native_cases_reused=38,stage_qualified=False,execute_qualified=False))
dump(D/'preflight/V1_preregistration_v1.json',dict(verdict='GO',selected_plan='A',run_id='final_V1_01',
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),runner=pin(D/'run_current_V1_v1.py'),
    source_lock=pin(D/'preflight/prerun_source_lock_v1.json'),loader=pin(D/'preflight/loader_environment_v2.json'),
    Observer_V1='decision_queue_saturation_after_authenticated_phase_v2',Observer_V3='none/0',Worker_V2='none/0',
    business_start='owned-prepare-before-business-v1/20s/2sTTL',close_profile='sink-fault-self-close-v1',
    close_order=['observer','publisher','worker','synthetic_source','recorder'],
    overall_budget_ns=45000000000,close_budget_ns=15000000000,raw_budget_bytes=134217728,
    strict_accepted_Applied_authenticated_ACK_before_arm_required=True,normal_Observer_Source_complete_expected=False,
    role_returncodes={'observer':2,'publisher':0,'worker':0,'synthetic_source':0,'recorder':0},
    actual_runs=1,CXX_builds=0,Native_cases_reused=38,actual_raw_copy_negatives=14,
    stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False))
print(json.dumps(dict(passed=True,locked_inputs=len(files),CXX_builds=0,run_id='final_V1_01')))
