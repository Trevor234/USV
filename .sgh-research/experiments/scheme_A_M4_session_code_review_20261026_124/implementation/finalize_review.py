#!/usr/bin/env python3
"""Validate review evidence and protected inputs; do not promote stage qualification."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]
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


rnw = read(R / 'rnw/replay_results.json')
assert rnw['all_selected_pins_match'] is True and len(rnw['pins']) == 15
assert rnw['S1']['rc'] == 0 and rnw['S1']['passed'] == rnw['S1']['total'] == 18
assert rnw['S2']['rc'] == 0 and rnw['S2']['result']['passed'] is True
assert rnw['S2']['result']['assertion_count'] == 16
assert all(v['passed'] is True for v in read(R / 'rnw/audit_probe_results.json')['results'])
admission = read(R / 'rnw/admission_probe_results.json')
assert len(admission) == 4
assert all(v['actual_owned_admission'] == 'accepted' for v in admission)
assert all(v['pure_S1_rejections'] for v in admission[1:])
logical = read(R / 'rnw/logical_time_probe.json')['results']
assert len(logical) == 4 and all(v['passed_by_current_R4'] is True for v in logical)
assert 'backwards_ns=4000000' in (R / 'rnw/receive_skew.stdout').read_text()
assert 'projected_backstep=1100000000' in (R / 'rnw/mapping_cap.stdout').read_text()
assert 'signed integer overflow' in (R / 'rnw/mapping_overflow.stderr').read_text()

epoch = read(R / 'epoch_model/epoch_result.json')['retired_proposal_replayed_into_uncommitted_generation']
assert epoch['initial_commit'] and epoch['fresh_B_valid'] and epoch['generation'] == 2
assert epoch['stale_A_commit_accepted'] and epoch['anchor_is_A'] and epoch['ledger_A_retired']
mutation = read(R / 'epoch_model/mutation_ledger_result.json')
assert mutation['all_original_six_pass'] is True and mutation['assertions'] == 32
model = read(R / 'epoch_model/model_result.json')
m = model['generation_zero_without_commit']
assert m['registered'] and m['executed'] and m['finite'] and m['commits'] == 0
assert m['u_diff_vs_declared_m1'] > .1
assert model['nonfinite_registration_accepted'] is True
false_pass = read(R / 'epoch_model/audit_false_pass_result.json')
assert false_pass['false_source_comparison_recorded_as_pass'] is True
assert false_pass['same_binding_declared_different_due_generation_constants'] is True
q2 = read(R / 't3/q2_actual_id_probe.json')
assert (q2['accepted_rows'], q2['unique_ids'], q2['duplicate_count']) == (513, 163, 350)
asan = read(R / 't3/asan_probe.json')
assert asan['compile_rc'] == 0 and asan['run_rc'] == 1 and asan['asan_stack_use_after_scope'] is True
assert 'stack-use-after-scope' in (R / 't3/asan_stderr.log').read_text()
sticky = read(R / 't3/sticky_probe.json')
assert sticky['failed_sticky'] is True and sticky['add_after_failed_and_drained'] is True
positive = read(ROOT / 'evidence/positive_progress_v1.json')
assert all(positive['RNW3']['checks'].values()) and positive['RNW3']['bundle_files'] == 108
assert positive['ScopedEpoch_POS']['jobs'] == list(range(1, 28))
assert positive['ModelTransaction_F6_1']['observed'] == {'X_diff': 0.0, 'u_diff': 0.0}
plan = read(ROOT / 'postrun/next_plan_v1.json')
assert plan['autonomous_resource_free_work_remains'] is True
assert all(v is False for v in plan['qualification'].values())
report = ROOT / 'documents/方案A_第124批_近期修改详解_代码质量复审与后续计划_2026-10-26.md'
assert report.read_text().index('按最近的推进顺序') < report.read_text().index('代码质量评价') < report.read_text().index('我建议接下来的固定顺序')

P99 = BASE / 'scheme_A_M4_t3q_impl_20261025_99/implementation/t2_author'
P103 = BASE / 'scheme_A_M4_t2b_gen_impl_20261025_103/implementation/t2_author'
P105 = BASE / 'scheme_A_M4_t2bgen_audit_20261025_105/implementation'
P108 = BASE / 'scheme_A_M4_n4_f6_impl_20261025_108/implementation'
P119 = BASE / 'scheme_A_M4_rnw_s4_owned_20261025_119/implementation'
findings = [
    ('F124-01', 1, 'Q2 dangling base capture and duplicated accepted event identities', P99 / 'observer/tests/test_t3_queue_pressure.cpp', [99, 101], 't3/asan_probe.json'),
    ('F124-02', 1, 'R4-only top pass and incomplete full-identity/logical-time audit', P119 / 'rnw_audit_v1.py', [115, 154, 194, 202], 'rnw/logical_time_probe.json'),
    ('F124-03', 1, 'hardened admission at freeze differs from real Driver pre-spawn entry', P119 / 't2_author/t2b_gen_admission.py', [51, 90], 'rnw/admission_probe_results.json'),
    ('F124-04', 1, 'audit clause argument inversion and tautological generation-based binding comparison', P105 / 'audit_t2bgen.py', [74, 78, 122, 125], 'epoch_model/audit_false_pass_result.json'),
    ('F124-05', 2, 'ScopedEpoch stale Proposal commit and uncovered inner retired-ledger guard', P103 / 'observer/src/shadow/scoped_epoch_v1.hpp', [86, 92, 113, 116], 'epoch_model/epoch_result.json'),
    ('F124-06', 2, 'model generation0 executes before commit; nonfinite registration accepted', P108 / 'model_transaction_v1.hpp', [68, 102, 171], 'epoch_model/model_result.json'),
    ('F124-07', 2, 'serial finite transaction tests do not prove concurrent atomicity, mixed refs, fixed tick or full behavioral equivalence', P108 / 'model_transaction_v1.hpp', [80, 93, 95, 154], None),
    ('F124-08', 2, 'B2 receive-latency and cap domain limits; unchecked signed arithmetic', P119 / 't2_author/fixture/resume_stamp_mapping_v1.hpp', [13, 18, 38, 42], 'rnw/mapping_overflow.stderr'),
    ('F124-09', 2, 'T3 sticky qualification, survivor and audit independence need bounded claims', P99 / 'observer/src/shadow/p1_diag_sink.hpp', [37, 50], 't3/sticky_probe.json'),
    ('F124-10', 2, 'innovation register mixes mechanisms and overstates reusable/novel properties', REPO / '.sgh-research/research-innovations.md', [], None)
]
create(ROOT / 'postrun/review_findings_v1.json', {
    'schema': 'schemeA-session-code-quality-review-v124', 'review_work_complete': True,
    'production_fixes_implemented': False, 'owned_runs_this_review': 0,
    'findings': [{'id': i, 'priority': p, 'title': title, 'file': str(file), 'lines': lines,
                  'evidence': 'evidence/replay01/' + evidence if evidence else 'documents/' + report.name}
                 for i, p, title, file, lines, evidence in findings],
    'severity_scope': 'priorities apply to verification/reuse readiness; no claim that these probes demonstrate an existing boat fault',
    'positive_progress_retained': 'evidence/positive_progress_v1.json',
    'current_stage_qualification': plan['qualification'],
    'single_innovation_register_edited': False, 'academic_novelty_checked': False,
    'production_B_mode': 'MANUAL+RC override'})

before = read(ROOT / 'evidence/inputs_before_v1.json')
supp = read(ROOT / 'evidence/supplemental_inputs_before_v1.json')
all_inputs = {**before['files'], **supp['files']}
missing = [p for p in all_inputs if not Path(p).is_file()]
changed = [p for p, record in all_inputs.items() if Path(p).is_file() and pin(p) != record]
workspace_changed = [p for p, record in before['workspace_files'].items() if not Path(p).is_file() or pin(p) != record]
selected = set()
for root in before['batches']:
    for parent, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith('build') and d not in ('cmake_build', 'CMakeFiles', '__pycache__')]
        selected.update(str(Path(parent) / n) for n in names if (Path(parent) / n).is_file())
added = sorted(selected - set(before['files']))
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
assert not missing and not changed and not workspace_changed and not added
assert status == before['git_porcelain']
create(ROOT / 'evidence/final_verification_v1.json', {
    'schema': 'schemeA-session-review-final-v124',
    'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
    'review_work_complete': True, 'production_fixes_implemented': False,
    'primary_protected_files': before['count'], 'supplemental_protected_files': supp['count'],
    'all_protected_files': len(all_inputs), 'all_protected_bytes': sum(v['bytes'] for v in all_inputs.values()),
    'historical_missing': missing, 'historical_changed': changed, 'historical_population_added': added,
    'workspace_ordinary_files_preserved': len(before['workspace_files']), 'workspace_changed': workspace_changed,
    'git_porcelain_matches_before': True,
    'protection_scope': [before['scope'], supp['scope']],
    'replays': {p: read(R / p / 'replay_result.json') for p in ['rnw', 'epoch_model', 't3']},
    'existing_positive_progress': {'RNW3_key_checks': 10, 'RNW3_bundle_files': 108, 'Scoped_POS_jobs': 27,
                                  'S1_private_replay': '18/18', 'S2_private_replay': '16/16',
                                  'F6_retained_finite_observation': 'u_diff=0.0, X6_diff=0.0, tolerance=1e-8'},
    'adverse_review_results': {'Q2_duplicate_IDs': 350, 'Q2_ASAN_stack_use_after_scope': True,
                               'old_Proposal_commit_accepted': True, 'zero_model_before_commit_executed': True,
                               'deleted_ledger_guard_old_assertions_still_pass': 32,
                               'RNW_invalid_logical_time_cases_accepted': 3,
                               'B2_receive_delay_counterexample_backwards_ns': 4000000},
    'findings_count': len(findings), 'single_innovation_register_edited': False,
    'owned_runs_this_review': 0, 'ROS_initialized': False, 'survivor_role_started': False,
    'qualification': plan['qualification'], 'production_B_mode': 'MANUAL+RC override',
    'note': 'Review completion includes confirmed flaws and bounded positive evidence; it is not a new integration, universal correctness proof or stage qualification.'})
print(json.dumps({'review_work_complete': True, 'protected_files': len(all_inputs),
                  'workspace_files_preserved': len(before['workspace_files']), 'findings': len(findings), 'owned_runs': 0}))
