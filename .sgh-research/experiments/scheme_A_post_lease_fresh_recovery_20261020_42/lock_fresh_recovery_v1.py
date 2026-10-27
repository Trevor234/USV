"""Freeze same current roles and exact prior-lease closure for one healthy recovery."""
import hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent;P=D.parent/'scheme_A_ordinary_lease_20261020_41';G=D.parent/'scheme_A_owned_business_start_20261020_39'
def load(p):return json.loads(Path(p).read_bytes())
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def dump(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')
files={}
def add(p,expected=None):
    p=Path(p);v=pin(p)
    if expected:assert v['sha256']==expected['sha256'] and v['bytes']==expected.get('bytes',v['bytes']),str(p)
    assert str(p) not in files or files[str(p)]==v;files[str(p)]=v
assert load(D/'preflight/protection_initial_v1.json')['passed'] and load(D/'preflight/source_change_review_v1.json')['original_normal_close_branch_byte_equal']
assert load(D/'preflight/theory_veto_recovery_v1.json')['verdict']=='GO'
assert load(D/'verification/fresh_entry_components_v1.json')['passed'] and load(D/'verification/fresh_entry_components_v1.json')['negative_count']==8
assert load(D/'verification/driver_CLI_v1.json')['passed'] and load(D/'preflight/loader_environment_v2.json')['passed']
assert not load(D/'preflight/runtime_process_scan_before_v1.json')['selected_research_processes']
assert load(P/'postrun/final_QA_v1.json')['current_selected_ordinary_lease_case_passed']
assert load(G/'build/business_observer_attempt01/result.json')['Native_cases']==38
for n in ['build_manifest_current.json','source_bundles_current.json','business_start_v1.py','owned_auth.py','owned_release.py','runtime/owned_process_supervisor.py']:
    assert (D/'author'/n).read_bytes()==(P/'author'/n).read_bytes()
for p,f in load(P/'preflight/prerun_source_lock_v1.json')['files'].items():add(p,f)
for p in sorted((D/'author').rglob('*')):
    if p.is_file():assert not p.is_symlink();add(p)
for p in D.glob('*.py'):add(p)
for root in [D/'preflight',D/'verification']:
    for p in root.iterdir():
        if p.is_file():add(p)
for p,f in load(D/'author/previous_lease_close_proof_v1.json')['source_input_pins'].items():add(p,f)
for p,f in load(D/'verification/fresh_entry_components_v1.json')['input_sha256_before'].items():add(p,f)
for r in load(D/'preflight/loader_environment_v2.json')['roles'].values():
    for p,f in r['libraries'].items():add(p,f)
registry={r['role']:r for r in load(D/'author/build_manifest_current.json')}
dump(D/'preflight/prerun_source_lock_v1.json',dict(files=files,count=len(files),worker_binary_sha256=registry['worker']['binary_sha256'],
    CXX_builds=0,all_five_current_registered_ELFs_reused=True,Native_cases_reused=38,stage_qualified=False,execute_qualified=False))
dump(D/'preflight/fresh_preregistration_v1.json',dict(verdict='GO',selected_plan='A',run_id='fresh_after_lease_01',
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),runner=pin(D/'run_fresh_recovery_v1.py'),
    source_lock=pin(D/'preflight/prerun_source_lock_v1.json'),loader=pin(D/'preflight/loader_environment_v2.json'),
    previous_closed_run='ordinary_lease_01',previous_close_proof=pin(D/'author/previous_lease_close_proof_v1.json'),
    business_start='owned-prepare-before-business-v1/20s/2sTTL',Observer_V1='none',Observer_V3='none/0',Observer_callback_gate='none/empty paths',Worker_V2='none/0',
    close_profile='normal',close_order=['publisher','observer','worker','synthetic_source','recorder'],minimum_distinct_healthy_jobs=2,
    original_normal_tail_required=True,Worker_terminal_diagnostic_tail_substitute_forbidden=True,
    overall_budget_ns=45000000000,close_budget_ns=15000000000,raw_budget_bytes=134217728,
    selected_actual_runs=1,CXX_builds=0,Native_cases_reused=38,new_seeded_identity_negatives=8,
    actual_raw_negative_cases=['old_Worker_instance','old_Worker_run','old_Observer_PID_start','old_group_not_closed','new_prepare_before_old_close',
        'duplicate_job_as_two_cycles','ready_after_absolute_deadline','missing_actual_healthy_Applied','Worker_unusable_during_recovery','normal_tail_anchor_missing',
        'normal_tail_not_zero','submit_after_normal_close_ACK','accepted_after_normal_close_ACK','normal_close_ACK_wrong_request'],
    source_packet_freshness_claimed=False,stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False))
print(json.dumps(dict(passed=True,locked_inputs=len(files),run_id='fresh_after_lease_01',CXX_builds=0)))
