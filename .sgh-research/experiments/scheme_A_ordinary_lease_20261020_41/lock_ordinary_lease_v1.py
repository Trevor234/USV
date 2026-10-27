"""Lock current orchestration plus unchanged policy, role, SDK and native dependency lineage."""
import hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent;P=D.parent/'scheme_A_owned_business_start_20261020_39';Q=D.parent/'scheme_A_final_V1_gate_confirmation_20261020_40'
def load(p):return json.loads(Path(p).read_bytes())
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def dump(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')
files={}
def add(p,expected=None):
    p=Path(p);v=pin(p)
    if expected:assert v['sha256']==expected['sha256'] and v['bytes']==expected.get('bytes',v['bytes']),str(p)
    assert str(p) not in files or files[str(p)]==v
    files[str(p)]=v
assert load(D/'preflight/protection_initial_v1.json')['passed'] and load(D/'preflight/source_change_review_v1.json')['passed']
assert load(D/'preflight/theory_veto_lease_v1.json')['verdict']=='GO'
assert load(D/'verification/driver_CLI_v1.json')['passed'] and load(D/'preflight/loader_environment_v2.json')['passed']
assert load(D/'verification/lease_entry_components_v1.json')['passed'] and load(D/'verification/lease_entry_components_v1.json')['negative_count']==13
assert not load(D/'preflight/runtime_process_scan_before_v1.json')['selected_research_processes']
assert load(Q/'postrun/final_QA_v1.json')['current_selected_V1_case_passed']
assert load(P/'postrun/final_QA_v1.json')['ordinary_active_stop_actual_case_passed']
assert load(P/'build/business_observer_attempt01/result.json')['Native_cases']==38
assert load(D.parent/'scheme_A_ordinary_supervision_20261020_38/verification/ordinary_components_v1.json')['negative_count']==44
for n in ['build_manifest_current.json','source_bundles_current.json','ordinary_supervision_v1.py','supervision_bridge_v1.py','business_start_v1.py','worker_terminal_close_v1.py','runtime/owned_process_supervisor.py']:
    assert (D/'author'/n).read_bytes()==(P/'author'/n).read_bytes()
for p,f in load(P/'preflight/prerun_source_lock_v1.json')['files'].items():add(p,f)
for p in sorted((D/'author').rglob('*')):
    if p.is_file():assert not p.is_symlink();add(p)
for p in D.glob('*.py'):add(p)
for p in (D/'preflight').iterdir():
    if p.is_file():add(p)
for p in (D/'verification').iterdir():
    if p.is_file():add(p)
for p,f in load(D/'verification/lease_entry_components_v1.json')['input_sha256_before'].items():add(p,f)
for n in ['postrun/final_QA_v1.json','archive_inventory_v1.json','delivery_verification.json']:add(Q/n)
for n in ['verification/ordinary_components_v1.json']:add(D.parent/'scheme_A_ordinary_supervision_20261020_38'/n)
for row in load(D/'preflight/loader_environment_v2.json')['roles'].values():
    for p,f in row['libraries'].items():add(p,f)
registry={r['role']:r for r in load(D/'author/build_manifest_current.json')}
dump(D/'preflight/prerun_source_lock_v1.json',dict(files=files,count=len(files),worker_binary_sha256=registry['worker']['binary_sha256'],
    CXX_builds=0,all_five_current_registered_ELFs_reused=True,Native_cases_reused=38,ordinary_policy_unchanged=True,stage_qualified=False,execute_qualified=False))
dump(D/'preflight/lease_preregistration_v1.json',dict(verdict='GO',selected_plan='A',run_id='ordinary_lease_01',
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),runner=pin(D/'run_ordinary_lease_v1.py'),
    source_lock=pin(D/'preflight/prerun_source_lock_v1.json'),loader=pin(D/'preflight/loader_environment_v2.json'),
    profile='source-terminal-owned-stop-v1',expected_terminal_cause='worker_capability_expired',
    Observer_V1='none',Observer_V3='none/0',Worker_V2='none/0',Observer_callback_gate='worker-gate',
    business_start='owned-prepare-before-business-v1/20s/2sTTL',close_profile='worker-terminal-reception-v1',
    gate_TTL_ns=3500000000,receipt_lease_ns=600000000,notice_budget_ns=250000000,authenticated_to_INT_budget_ns=100000000,
    monitor_before_terminal_required=True,resume_only_after_owned_Worker_stop=True,post_exit_queue_guard_required=True,
    overall_budget_ns=45000000000,close_budget_ns=15000000000,raw_budget_bytes=134217728,
    role_returncodes={r:0 for r in ['observer','worker','publisher','synthetic_source','recorder']},
    selected_actual_runs=1,CXX_builds=0,Native_cases_reused=38,ordinary_policy_components_reused=44,new_orchestration_negative_cases=13,
    actual_raw_negative_cases=['unknown_cause','duplicate_dispatch','foreign_signal_group','injected_SIGSTOP','notification_budget_exceeded','inconsistent_wait_budget','Worker_summary_missing','new_submit_after_terminal','accepted_after_terminal','Source_inode_mismatch','monitor_after_terminal','resume_before_owned_cleanup','post_exit_semantic_callback','lease_not_expired'],
    source_packet_freshness_claimed=False,native_C_hang_claimed=False,stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False))
print(json.dumps(dict(passed=True,locked_inputs=len(files),run_id='ordinary_lease_01',CXX_builds=0)))
