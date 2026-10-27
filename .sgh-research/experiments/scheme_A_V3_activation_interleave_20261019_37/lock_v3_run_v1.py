"""Create-only run prerequisite and source lock after selected build/loader checks."""
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def load(p):return json.loads(Path(p).read_bytes())
def write(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')
files={}
def add(p,expected=None):
    p=Path(p);row=pin(p)
    if expected:
        assert row['sha256']==expected['sha256'] and row['bytes']==expected.get('bytes',row['bytes']),str(p)
    assert str(p) not in files or files[str(p)]==row
    files[str(p)]=row
build=load(D/'build/v3_observer_attempt02/result.json')
assert build['passed'] and build['Native_rc']==0 and build['source_unchanged']
assert load(D/'preflight/protection_initial_v1.json')['passed']
assert load(D/'preflight/theory_veto_v3_v1.json')['verdict']=='GO'
environment=load(D/'preflight/loader_environment_v2.json');assert environment['passed']
scan=load(D/'preflight/runtime_process_scan_before_v1.json');assert scan['selected_research_processes']==[]
for p in sorted((D/'author').rglob('*')):
    if p.is_file() and 'runs' not in p.relative_to(D/'author').parts:
        assert not p.is_symlink();add(p)
for row in load(D/'author/build_manifest_current.json'):
    add(row['binary'],dict(sha256=row['binary_sha256']))
    bundle=load(row['source_bundle']['path']);add(row['source_bundle']['path'],row['source_bundle'])
    for item in bundle['files'].values():add(item['path'],item)
for role in environment['roles'].values():
    for p,item in role['libraries'].items():add(p,item)
for p,item in load(D/'build/v3_observer_attempt02/compiler_dependency_pins.json')['files'].items():add(p,item)
for p in ['activation_interleave_audit_v1.py','audit_v3_actual_v1.py','run_v3_v1.py','build_v3_observer_v1.py','lock_v3_run_v1.py',
          'preflight/preflight_reflection_v3_v1.md','preflight/theory_veto_v3_v1.json','build/v3_observer_attempt02/result.json']:
    add(D/p)
registry={r['role']:r for r in load(D/'author/build_manifest_current.json')}
write(D/'preflight/prerun_source_lock_v1.json',dict(files=files,worker_binary_sha256=registry['worker']['binary_sha256'],
    new_Observer_binary_sha256=registry['observer']['binary_sha256'],stage_qualified=False))
write(D/'preflight/v3_preregistration_v1.json',dict(verdict='GO',selected_plan='A',run_id='v3_odom_01',
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),runner=pin(D/'run_v3_v1.py'),
    source_lock=pin(D/'preflight/prerun_source_lock_v1.json'),loader=pin(D/'preflight/loader_environment_v2.json'),
    policy='await_actual_odom_once_before_commit_v1',source_wait_budget_ns=25000000,
    diagnostic_wait_scheduling_observation_slack_ns=5000000,original_tick_jitter_ns=20000000,
    measurement_seconds=5,driver_budget_seconds=45,max_raw_bytes=134217728,
    actual_input_race_required=True,actual_clock_epoch_interleave_claimed=False,
    source_changes_are_actual_owned_callbacks=True,no_patched_Source_evidence=True,
    selected_checker_negative_cases=['unchanged_observed_sequence','false_input_guard','third_attempt','capacity33',
        'wrong_owned_GID','input_commit_before_snapshot','wait_budget_changed','false_prior_healthy_activation'],
    stage_qualified=False,execute_qualified=False,research_conclusion=False))
print(json.dumps(dict(passed=True,source_inputs=len(files),run_id='v3_odom_01')))
