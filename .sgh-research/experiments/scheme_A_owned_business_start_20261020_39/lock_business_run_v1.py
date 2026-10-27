"""Freeze Python policy plus unchanged role lineage for one ordinary stop run."""
import hashlib
import json
from pathlib import Path
D=Path(__file__).resolve().parent
P=D.parent/'scheme_A_V3_activation_interleave_20261019_37'
def load(p):return json.loads(Path(p).read_bytes())
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def write(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')
files={}
def add(p,expected=None):
    p=Path(p);r=pin(p)
    if expected:assert r['sha256']==expected['sha256'] and r['bytes']==expected.get('bytes',r['bytes']),str(p)
    assert str(p) not in files or files[str(p)]==r
    files[str(p)]=r
assert load(D/'preflight/protection_initial_v1.json')['passed']
assert load(D/'preflight/theory_veto_business_start_v1.json')['verdict']=='GO'
build=load(D/'build/business_observer_attempt01/result.json')
assert build['passed'] and build['Native_cases']==38 and build['Native_rc']==0
assert load(D/'preflight/source_change_review_v1.json')['passed']
assert (D/'author/ordinary_supervision_v1.py').read_bytes()==(D.parent/'scheme_A_ordinary_supervision_20261020_38/author/ordinary_supervision_v1.py').read_bytes()
assert load(D/'verification/driver_CLI_v2.json')['passed']
assert load(D/'preflight/loader_environment_v2.json')['passed']
assert not load(D/'preflight/runtime_process_scan_before_v1.json')['selected_research_processes']
for name in ['owned_auth.py','owned_release.py','runtime/owned_process_supervisor.py','pair_wakeup_contract_v1.json']:
    assert (D/'author'/name).read_bytes()==(P/'author'/name).read_bytes()
for p in sorted((D/'author').rglob('*')):
    if p.is_file() and 'runs' not in p.relative_to(D/'author').parts:
        assert not p.is_symlink();add(p)
for r in load(D/'author/build_manifest_current.json'):
    add(r['binary'],dict(sha256=r['binary_sha256']));add(r['source_bundle']['path'],r['source_bundle'])
    for f in load(r['source_bundle']['path'])['files'].values():add(f['path'],f)
env=load(D/'preflight/loader_environment_v2.json')
for r in env['roles'].values():
    for p,f in r['libraries'].items():add(p,f)
for p,f in load(D/'build/business_observer_attempt01/compiler_dependency_pins.json')['files'].items():add(p,f)
for leaf in ['run_business_v1.py','lock_business_run_v1.py','audit_ordinary_core_v1.py','audit_v2_core_base_v1.py',
             'audit_ordinary_actual_v1.py','audit_business_start_v1.py','build_business_observer_v1.py','preflight/source_change_review_v1.json',
             'verification/driver_CLI_v2.json','preflight/preflight_reflection_business_start_v1.md','preflight/theory_veto_business_start_v1.json']:
    add(D/leaf)
registry={r['role']:r for r in load(D/'author/build_manifest_current.json')}
write(D/'preflight/prerun_source_lock_v1.json',dict(files=files,count=len(files),
    worker_binary_sha256=registry['worker']['binary_sha256'],new_Observer_and_four_reused_ELFs=True,
    CXX_builds=1,stage_qualified=False,execute_qualified=False))
write(D/'preflight/business_preregistration_v1.json',dict(verdict='GO',selected_plan='A',run_id='business_active_01',
    case='active',profile='source-terminal-owned-stop-v1',expected_terminal_cause='active_watchdog',
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    runner=pin(D/'run_business_v1.py'),source_lock=pin(D/'preflight/prerun_source_lock_v1.json'),
    loader=pin(D/'preflight/loader_environment_v2.json'),new_Observer_and_four_reused_ELFs=True,CXX_builds=1,
    Observer_V1='none',Observer_V3='none/0',Observer_business_start='owned-prepare-before-business-v1/20s/2sTTL',diagnostic_Worker_stimulus='pre_native_once_after_completed_v1/1700ms',
    ordinary_healthy_Worker_profile='none/0; fault enabled only for this selected stimulus',
    diagnostic_SIGSTOP_allowed=False,notification_observation_budget_ns=250000000,
    authenticated_to_INT_budget_ns=100000000,wait_observation_slack_ns=100000000,
    stop_waits_ns=dict(worker_grace=500000000,term_grace=1000000000,kill_postcheck=1000000000),
    driver_budget_seconds=45,max_raw_bytes=134217728,actual_ROS_run_limit=1,
    expected_selected_Worker_returncode=0,normal_Worker_Source_required=True,kill_signal_not_required=True,
    business_gate_negative_cases=['pre_gate_decision','driver_start_mismatch','early_first_tick','stale_gate_request','wrong_initial_anchor','first_phase_late'],
    checker_negative_cases=['unknown_cause','duplicate_dispatch','foreign_signal_group','injected_SIGSTOP',
        'notification_budget_exceeded','inconsistent_wait_budget','Worker_summary_missing','new_submit_after_terminal',
        'accepted_after_terminal','Source_inode_mismatch'],
    actual_lease_ordinary_stop_claimed=False,native_C_hang_claimed=False,
    stage_qualified=False,execute_qualified=False,research_conclusion=False))
print(json.dumps(dict(passed=True,locked_inputs=len(files),run_id='business_active_01',CXX_builds=1)))
