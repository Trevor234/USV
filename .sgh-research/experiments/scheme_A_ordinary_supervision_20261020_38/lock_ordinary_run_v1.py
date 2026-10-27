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
assert load(D/'preflight/theory_veto_ordinary_v1.json')['verdict']=='GO'
component=load(D/'verification/ordinary_components_v1.json')
assert component['passed'] and component['negative_count']==44 and len(component['real_owned_child_cases'])==2
assert component['policy_pin']==pin(D/'author/ordinary_supervision_v1.py')
assert load(D/'verification/driver_CLI_v1.json')['passed']
assert load(D/'preflight/loader_environment_v2.json')['passed']
assert not load(D/'preflight/runtime_process_scan_before_v1.json')['selected_research_processes']
for registry in ['build_manifest_current.json','source_bundles_current.json']:
    assert (D/'author'/registry).read_bytes()==(P/'author'/registry).read_bytes()
for name in ['owned_auth.py','owned_release.py','runtime/owned_process_supervisor.py','pair_wakeup_contract_v1.json']:
    assert pin(D/'author'/name)==pin(P/'author'/name)
for root in ['observer','common']:
    parent={str(p.relative_to(P/'author')):pin(p) for p in (P/'author'/root).rglob('*') if p.is_file()}
    current={str(p.relative_to(D/'author')):pin(p) for p in (D/'author'/root).rglob('*') if p.is_file()}
    assert parent==current,'unchanged selected C++ source copy'
for p in sorted((D/'author').rglob('*')):
    if p.is_file() and 'runs' not in p.relative_to(D/'author').parts:
        assert not p.is_symlink();add(p)
for r in load(D/'author/build_manifest_current.json'):
    add(r['binary'],dict(sha256=r['binary_sha256']));add(r['source_bundle']['path'],r['source_bundle'])
    for f in load(r['source_bundle']['path'])['files'].values():add(f['path'],f)
env=load(D/'preflight/loader_environment_v2.json')
for r in env['roles'].values():
    for p,f in r['libraries'].items():add(p,f)
for p,f in load(P/'build/v3_observer_attempt02/compiler_dependency_pins.json')['files'].items():add(p,f)
for leaf in ['run_ordinary_v1.py','lock_ordinary_run_v1.py','audit_ordinary_core_v1.py','audit_v2_core_base_v1.py',
             'audit_ordinary_actual_v1.py','verification/test_ordinary_components_v1.py','verification/ordinary_components_v1.json',
             'verification/driver_CLI_v1.json','preflight/preflight_reflection_ordinary_v1.md','preflight/theory_veto_ordinary_v1.json']:
    add(D/leaf)
registry={r['role']:r for r in load(D/'author/build_manifest_current.json')}
write(D/'preflight/prerun_source_lock_v1.json',dict(files=files,count=len(files),
    worker_binary_sha256=registry['worker']['binary_sha256'],all_five_role_ELFs_reused=True,
    CXX_builds=0,stage_qualified=False,execute_qualified=False))
write(D/'preflight/ordinary_preregistration_v1.json',dict(verdict='GO',selected_plan='A',run_id='ordinary_active_01',
    case='active',profile='source-terminal-owned-stop-v1',expected_terminal_cause='active_watchdog',
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    runner=pin(D/'run_ordinary_v1.py'),source_lock=pin(D/'preflight/prerun_source_lock_v1.json'),
    loader=pin(D/'preflight/loader_environment_v2.json'),all_five_role_ELFs_reused=True,CXX_builds=0,
    Observer_V1='none',Observer_V3='none/0',diagnostic_Worker_stimulus='pre_native_once_after_completed_v1/1700ms',
    ordinary_healthy_Worker_profile='none/0; fault enabled only for this selected stimulus',
    diagnostic_SIGSTOP_allowed=False,notification_observation_budget_ns=250000000,
    authenticated_to_INT_budget_ns=100000000,wait_observation_slack_ns=100000000,
    stop_waits_ns=dict(worker_grace=500000000,term_grace=1000000000,kill_postcheck=1000000000),
    driver_budget_seconds=45,max_raw_bytes=134217728,actual_ROS_run_limit=1,
    expected_selected_Worker_returncode=0,normal_Worker_Source_required=True,kill_signal_not_required=True,
    checker_negative_cases=['unknown_cause','duplicate_dispatch','foreign_signal_group','injected_SIGSTOP',
        'notification_budget_exceeded','inconsistent_wait_budget','Worker_summary_missing','new_submit_after_terminal',
        'accepted_after_terminal','Source_inode_mismatch'],
    actual_lease_ordinary_stop_claimed=False,native_C_hang_claimed=False,
    stage_qualified=False,execute_qualified=False,research_conclusion=False))
print(json.dumps(dict(passed=True,locked_inputs=len(files),run_id='ordinary_active_01',CXX_builds=0)))
