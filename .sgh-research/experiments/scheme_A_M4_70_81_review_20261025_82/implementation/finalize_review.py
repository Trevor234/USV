#!/usr/bin/env python3
"""Create-only closeout. Expected negative results never count as family passes."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]
AUTHOR = BASE / 'scheme_A_M4_t2_r2_driver_20261025_78/implementation/t2_author_r3'
REPLAY = ROOT / 'evidence/replay01'


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return {'bytes': path.stat().st_size, 'sha256': h.hexdigest()}


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


timeline = read(REPLAY / 'boundary/timeline_evidence.json')
assert len(timeline['positive_observation_checks']) == 7
assert all(v is True for v in timeline['positive_observation_checks'].values())
old = read(REPLAY / 'boundary/pinned_audit_cli.stdout')
new = read(REPLAY / 'boundary/current_audit_cli.stdout')
assert old['passed'] is False and new['passed'] is True
assert len(old['checks']) == len(new['checks']) == 13
assert sum(v is True for v in old['checks'].values()) == 12
assert old['checks']['trigger_phase_is_inflight_or_ready'] is False
assert all(v is True for v in new['checks'].values())
expected_pin = timeline['audit_identity']['registered_sha256']
assert pin(ROOT / 'evidence/recovered_P01_registered_sources/audit_t2.py')['sha256'] == expected_pin
assert pin(AUTHOR / 'audit_t2.py')['sha256'] == timeline['audit_identity']['current_sha256'] != expected_pin
bad_b = read(REPLAY / 'boundary/audit_probe_results.json')
assert len(bad_b) == 6 and all(row['passed'] is True for row in bad_b.values())
assert read(REPLAY / 'boundary/driver_release_probe_results.json')['released_despite_no_generation_advance_and_path_event_before_receipt'] is True
assert read(REPLAY / 'boundary/failed_applied_counted_as_success.json')['publication_failure_counted_as_Applied_row'] is True

protocol = read(REPLAY / 'protocol/probe_result.json')
assert len(protocol) == 6 and all(r['passed'] is True for r in protocol[:5])
assert protocol[5]['passed'] is False
assert read(REPLAY / 'protocol/fixture_gate_probe_result.json')['result']['rejected'] is False
a = read(REPLAY / 'protocol/probe_t2a_predicates_result.json')['cases']
assert [r['passed'] for r in a] == [True, False, False, True]
log = (REPLAY / 'protocol/r0_19_tests.stderr').read_text()
assert 'Ran 19 tests' in log and log.rstrip().endswith('OK')

storage = read(ROOT / 'evidence/replay02/storage/validate_t2b_p01_result.json')
env = read(ROOT / 'evidence/replay02/storage/environment_provenance.json')
assert env['full_workspace_decode_and_selected_checks_passed'] is True
assert env['ExecutionDecision_has_activation_odom_stamp_ns'] is True
assert len(env['native_type_support']) == 5
assert storage['Stored']['CDR_decoded'] is True
assert storage['protected_run_files_unchanged'] is True and storage['protected_run_files'] == 38
for name in ['API_full_stream', 'typed_Source_Stored', 'capability_Source_Stored',
             'wire_GID_Stored', 'recorder_fixture_counts', 'Source_flush_witness_close',
             'bounded_shutdown', 'observed_four_role_rc0_group_empty_no_errors']:
    assert storage['common_checks'][name]['passed'] is True, name
for name in ['role_source_ELF_identity', 'regulator_source_ELF_identity',
             'worker_source_ELF_identity', 'fixture_source_ELF_identity']:
    assert storage['common_checks'][name]['passed'] is False
    assert storage['common_checks'][name]['error_type'] == 'AssertionError'
assert storage['common_checks']['recorder_source_ELF_identity']['passed'] is True
assert storage['common_checks']['fallback_policy']['passed'] is False
assert storage['check_applicability']['fallback_policy']
assert all(row == list(range(1, 30)) for row in storage['Source_sequences'].values())
assert storage['Stored']['Applied_sequences'] == storage['Stored']['Decision_sequences'] == list(range(1, 30))
assert read(REPLAY / 'runtime/witness_original.stdout')['records_inconsistency'] == 'same-generation tick not strictly advancing'
assert read(REPLAY / 'runtime/witness_counterfactual.stdout')['observation_complete'] is True
pair = read(REPLAY / 'runtime/pair_controlflow_probe.json')
assert any(r['type'] == 'owned_applied_publication_failed' for r in pair)
assert any(r['type'] == 'owned_pair_consistency_failed' and r['applied_emitted'] is True for r in pair)
gtest = read(BASE / 'scheme_A_M4_t2_r1_runtime_20261024_76/evidence/harness_gtest.json')
assert gtest['tests'] == 34 and gtest['failures'] == 0
assert not any(t.get('failures') for suite in gtest['testsuites'] for t in suite['testsuite'])

report_path = ROOT / 'documents/方案A_第82批_70至81批代码复审与下一步实施计划_2026-10-25.md'
report = report_path.read_text()
for time in timeline['timepoints_from_origin_ms'].values():
    if time:
        assert f'{time:.6f}' in report or time == timeline['timepoints_from_origin_ms']['tick_origin'], time
assert '正控以及此前被误拒的合法案例必须通过' in report
plan = read(ROOT / 'postrun/next_plan_v14.json')
assert plan['current_status']['P01_timely_replace_observation'] is True
assert plan['current_status']['P01_original_registered_audit_pass'] is False
assert all(plan['current_status'][k] is False for k in ['M4', 'F6', 'P1', 'plant', 'hard_realtime'])

findings = [
    ('R82-01', 1, 'audit identity and reused freeze paths', 'audit_t2.py', [219], 'boundary/pinned_audit_cli.stdout'),
    ('R82-02', 1, 'boundary/deadline/native and full-stream evidence omitted from audit', 'audit_t2.py', [60, 79, 113, 208], 'boundary/audit_probe_results.json'),
    ('R82-03', 1, 'arbitrary path_version accepted as release ACK', 't2_scenario_driver_v1.py', [333, 382], 'boundary/driver_release_probe_results.json'),
    ('R82-04', 1, 'C activation and stopping timestamps incorrect, target guard not yet proven observable', 'audit_t2.py', [247, 249, 258, 265], 'protocol/probe_result.json'),
    ('R82-05', 2, 'command bytes, complete receipt trigger and independent Fixture gate not fully bound', 't2_action_contract.py', [253, 258], 'protocol/fixture_gate_probe_result.json'),
    ('R82-06', 2, 'applied_emitted hardcoded despite caught publication failure', 'observer/src/shadow/regulator_owned_execute.cpp', [1235, 1245, 1272], 'runtime/pair_controlflow_probe.json'),
    ('R82-07', 2, 'target seq2 ledger regression assertions select first Applied/divergence', str(BASE / 'scheme_A_M4_t2_r1_runtime_20261024_76/implementation/r1_harness/tests/test_current_candidate_reference_clock.cpp'), [837, 875], None),
    ('R82-08', 2, 'queued trigger scope and inflight/family/latency claims need narrower semantics', 't2_action_contract.py', [53], 'boundary/timeline_evidence.json'),
    ('R82-09', 2, 'claimed new Worker flush not supported by identical retained sources; clock attempt scope misleading', 'worker/solver_worker_m4.cpp', [134, 181], None),
    ('R82-10', 2, 'A legal silent/new-schedule cases rejected and missing positive evidence accepted', 'audit_t2.py', [169, 205], 'protocol/probe_t2a_predicates_result.json'),
]
create(ROOT / 'postrun/review_findings_v1.json', {
    'schema': 'M4-70-81-independent-review-v82',
    'review_work_complete': True, 'production_fixes_implemented': False, 'owned_runs_this_batch': 0,
    'findings': [{'id': i, 'priority': p, 'title': title,
                  'file': source if source.startswith('/') else str(AUTHOR / source),
                  'lines': lines, 'evidence': 'evidence/replay01/' + evidence if evidence else 'documents/' + report_path.name}
                 for i, p, title, source, lines, evidence in findings],
    'positive_progress': {'P01_seven_timeline_checks': timeline['positive_observation_checks'],
                          'P01_API_Source_Stored_complete': True,
                          'R0_offline_tests_rerun': 19, 'R1_retained_component_tests': 34,
                          'P01_exact_source_population_recovered': 103},
    'formal_audit': {'registered_tool_pin_matches_current': False, 'registered_tool_checks_passed': 12,
                     'registered_tool_checks_total': 13, 'registered_tool_passed': False,
                     'modified_unregistered_tool_passed': True},
    'qualification': {k: False for k in ['T2B_full_family', 'M4', 'F6', 'P1', 'plant', 'hard_realtime']},
    'production_B_mode': 'MANUAL+RC override'})

before = read(ROOT / 'evidence/inputs_before_v1.json')
missing = [p for p in before['files'] if not Path(p).is_file()]
changed = [p for p, value in before['files'].items() if Path(p).is_file() and pin(p) != value]
workspace_changed = [p for p, value in before['workspace_files'].items() if not Path(p).is_file() or pin(p) != value]
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
    'schema': 'M4-70-81-review-final-verification-v82',
    'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
    'review_work_complete': True, 'production_fixes_implemented': False,
    'protected_input_files': before['count'], 'protected_input_bytes': sum(x['bytes'] for x in before['files'].values()),
    'historical_missing': missing, 'historical_changed': changed, 'historical_population_added': added,
    'workspace_ordinary_files_preserved': len(before['workspace_files']), 'workspace_changed': workspace_changed,
    'git_porcelain_matches_before': True, 'protection_scope': before['scope'],
    'owned_runs_this_batch': 0, 'ROS_graph_started': False,
    'review_replays': {part: read(REPLAY / ('protocol' if part == 'storage' else part) / (part + '_replay_result.json'))
                       for part in ['boundary', 'protocol', 'runtime', 'storage']},
    'storage_replay01': 'mixed snapshot Python/workspace native environment failed; preserved, not data failure or pass',
    'storage_replay02_full_workspace_schema': {'passed': True, 'native_type_support_libraries': 5,
                                             'original_P01_files_preserved': 38},
    'unadapted_W_fallback_failure': 'preserved and applicability-limited; T2 worker_unusable invalid branch requires ramp',
    'report_timeline_matches_raw': True, 'findings_count': len(findings),
    'P01_timely_replace_observation': True, 'P01_original_registered_audit_pass': False,
    'qualification': {k: False for k in ['T2B_full_family', 'M4', 'F6', 'P1', 'plant', 'hard_realtime']},
    'production_B_mode': 'MANUAL+RC override',
    'note': 'Review completion includes expected negative findings. It is not a new owned run, production fix, family qualification or delivery readback.'})
print(json.dumps({'review_work_complete': True, 'protected_inputs': before['count'],
                  'workspace_files_preserved': len(before['workspace_files']),
                  'findings': len(findings), 'owned_runs': 0}, ensure_ascii=False))
