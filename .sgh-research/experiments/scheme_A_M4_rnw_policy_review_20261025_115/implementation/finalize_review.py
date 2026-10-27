#!/usr/bin/env python3
"""Close a design review, not an implementation or qualification."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]
B112 = BASE / 'scheme_A_M4_t2a_rnw2_impl_20261025_112'
AUTHOR = B112 / 'implementation/t2_author'
R = ROOT / 'evidence/replay01'


def read(p):
    return json.loads(Path(p).read_bytes())


def pin(p):
    p = Path(p)
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return {'bytes': p.stat().st_size, 'sha256': h.hexdigest()}


def create(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


clock = read(R / 'clock/clock_evidence_v1.json')
assert sum(v['clock_count'] for v in clock['runs'].values()) == 201
assert all(v['clock_count'] == v['cdr_clock_stamp_verified'] and not v['source_clock_backsteps']
           and set(v['clock_epochs']) == {'0'} for v in clock['runs'].values())
second = clock['runs']['T2A_RNW2']
assert second['source_sim_delta_ns'] == 797450244
assert second['source_receive_delta_ns'] == 1539221548
assert second['hold_actual_ns'] == 1527323783
assert second['projection_regressions'][0]['left_minus_prev_right_ns'] == -541809040
assert second['claimed_stamp_102619942560_matches'] == []
assert any(r['type'] == 'clock' and r['line'] == 567 and r['relation_to_resume'] == 'after'
           for r in clock['runs']['T2A_RNW2_attempt1']['claimed_stamp_102619942560_matches'])
assert read(R / 'clock/replay_verification_v1.json')['complete'] is True
assert 'known=[false,true]' in (R / 'clock/replay_stdout.txt').read_text()
assert 'actual OutputAuthority has_change_version=false' in (R / 'policy/authority_interface.stdout').read_text()
policy = (R / 'policy/probe.stdout').read_text()
assert 'version_time_or_epoch' in policy and 'version_change_not_permitted' in policy
assert 'preserves actual anchor: PASS' in policy
fixture = read(R / 'fixture/findings.json')
assert fixture['runner_probe']['all_runner_checks_pass'] is True
assert len(fixture['runner_probe']['checks']) == 9
assert all(x['outcome'] == 'ACCEPTED' for x in fixture['admission_probes'])
assert len(fixture['admission_probes']) == 3
mapping = read(ROOT / 'evidence/mapping_arithmetic_v1.json')
assert mapping['shorthand_error_ns'] == 6838410
identity = read(ROOT / 'evidence/identity_readback_v1.json')
assert all(identity[k] is True for k in ['registry_matches_registration', 'table_matches_registration',
                                        'audit_matches_registration', 'Driver_matches_registry', 'bundle_population_matches'])
assert all(identity['ELF_matches_registry'].values()) and identity['bundle_files'] == 106
for p in ['contract', 'topics']:
    reg = read(B112 / 'implementation/T2A_RNW2_registration.json')
    assert pin(reg[p])['sha256'] == reg[p + '_sha256']
registry = read(reg['registry'])
assert all(pin(role['source_bundle']['path'])['sha256'] == role['source_bundle']['sha256'] for role in registry['roles'].values())

plan = read(ROOT / 'postrun/next_plan_v1.json')
assert plan['mainline'] == ['S0', 'S1', 'S2', 'S4']
assert next(s for s in plan['steps'] if s['id'] == 'S3')['gates_B2_run'] is False
assert next(s for s in plan['steps'] if s['id'] == 'S4')['B0_completion_required'] is False
assert plan['current_state']['resume_NW'] == 'not_covered'
assert all(plan['current_state'][k] is False for k in ['M4', 'F6', 'P1', 'plant', 'hard_realtime'])
report = ROOT / 'documents/方案A_第115批_114设计独立复审与实施计划_2026-10-25.md'
text = report.read_text()
for token in ['797.450244', '541809040', '1527.323783', '6.838410', '201', '主线是S0→S1→S2→S4']:
    assert token in text, token

findings = [
    {'id': 'R115-01', 'priority': 1, 'title': 'cross-attempt and cross-domain comparison does not prove a raw clock backstep',
     'file': str(BASE / 'scheme_A_M4_rnw_policy_design_20261025_114/documents/方案A_第114批_resume过渡政策设计_2026-10-25.md'),
     'evidence': 'evidence/replay01/clock/clock_evidence_v1.json'},
    {'id': 'R115-02', 'priority': 1, 'title': 'synchronous engineering-history reset reproduces the signature; L630-only fix misses this path',
     'file': str(AUTHOR / 'observer/src/shadow/regulator_owned_execute.cpp'), 'lines': [844, 967, 968, 1248],
     'evidence': 'evidence/replay01/clock/replay_verification_v1.json'},
    {'id': 'R115-03', 'priority': 1, 'title': 'actual OutputAuthority has no change_version; shadow API preserves facts and rejects active/new epoch',
     'file': str(AUTHOR / 'observer/src/shadow/owned_execution_policy_native_v1.hpp'), 'lines': [60, 96, 143],
     'evidence': 'evidence/replay01/policy/probe.stdout'},
    {'id': 'R115-04', 'priority': 1, 'title': 'runner event-presence checks can accept failed Candidate and fallback as new-window acceptance',
     'file': str(B112 / 'implementation/run_t2a_rnw2.py'),
     'evidence': 'evidence/replay01/fixture/findings.json'},
    {'id': 'R115-05', 'priority': 1, 'title': 'distinct clock_epoch assertion conflicts with monotonic B2 recovery via schedule change',
     'file': str(B112 / 'implementation/run_t2a_rnw2.py'),
     'evidence': 'evidence/replay01/fixture/findings.json'},
    {'id': 'R115-06', 'priority': 2, 'title': 'B2 mapping must bind the actual last stamp to its writer target; hold command duration loses edge accounting',
     'file': str(AUTHOR / 'fixture/synthetic_source_m4.cpp'),
     'evidence': 'evidence/mapping_arithmetic_v1.json'},
    {'id': 'R115-07', 'priority': 2, 'title': 'admission accepts missing hold, reversed action order and false clauses; new Fixture needs new exact pins',
     'file': str(AUTHOR / 't2b_gen_admission.py'),
     'evidence': 'evidence/replay01/fixture/findings.json'},
    {'id': 'R115-08', 'priority': 2, 'title': 'combined B0/B2, time-window exemptions and old M0 reuse require separate bounded claims',
     'evidence': 'documents/' + report.name}
]
create(ROOT / 'postrun/review_findings_v1.json', {
    'schema': 'RNW-policy-design-review-v115', 'review_work_complete': True,
    'findings': findings, 'new_policy_implemented': False, 'owned_runs_this_batch': 0,
    'current_112_identity_matches': True, 'current_112_bundle_files': 106,
    'verified_raw_clock_rows': 201,
    'limits': ['exact-method replay with simplified collaborators is not a full runtime branch observation',
               'AST verdict replay never imported or executed the owned runner main/subprocess',
               'counterfactual mapping arithmetic is not an implemented writer policy'],
    'qualification': {k: False for k in ['M4', 'F6', 'P1', 'plant', 'hard_realtime']},
    'resume_NW': 'not_covered', 'production_B_mode': 'MANUAL+RC override'})

before = read(ROOT / 'evidence/inputs_before_v1.json')
missing = [p for p in before['files'] if not Path(p).is_file()]
changed = [p for p, value in before['files'].items() if Path(p).is_file() and pin(p) != value]
workspace_changed = [p for p, value in before['workspace_files'].items() if not Path(p).is_file() or pin(p) != value]
population = set()
for root in before['batches']:
    for parent, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith('build') and d not in ('cmake_build', 'CMakeFiles', '__pycache__')]
        population.update(str(Path(parent) / n) for n in names if (Path(parent) / n).is_file())
added = sorted(population - set(before['files']))
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
assert not missing and not changed and not workspace_changed and not added
assert status == before['git_porcelain']
create(ROOT / 'evidence/final_verification_v1.json', {
    'schema': 'RNW-policy-review-final-v115',
    'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
    'review_work_complete': True, 'new_policy_implemented': False,
    'protected_input_files': before['count'], 'protected_input_bytes': sum(v['bytes'] for v in before['files'].values()),
    'historical_missing': missing, 'historical_changed': changed, 'historical_population_added': added,
    'workspace_ordinary_files_preserved': len(before['workspace_files']), 'workspace_changed': workspace_changed,
    'git_porcelain_matches_before': True, 'protection_scope': before['scope'],
    'replays': {p: read(R / p / 'replay_result.json') for p in ['clock', 'policy', 'fixture']},
    'raw_CDR_clock_rows_verified': 201, 'attempt2_raw_clock_forward_ns': 797450244,
    'attempt2_projected_history_regression_ns': 541809040, 'runner_invalid_case_checks_passed': 9,
    'admission_invalid_tables_accepted': 3, 'current_identity_matches': True,
    'owned_runs_this_batch': 0, 'ROS_initialized': False, 'resume_NW': 'not_covered',
    'qualification': {k: False for k in ['M4', 'F6', 'P1', 'plant', 'hard_realtime']},
    'production_B_mode': 'MANUAL+RC override',
    'note': 'Review probes succeeded, including adverse findings; no candidate resume policy was implemented, run or qualified.'})
print(json.dumps({'review_work_complete': True, 'findings': len(findings), 'protected_inputs': before['count'],
                  'workspace_files_preserved': len(before['workspace_files']), 'owned_runs': 0}, ensure_ascii=False))
