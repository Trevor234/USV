#!/usr/bin/env python3
"""Execute selected original Driver AST branches; never execute main or spawn."""
from pathlib import Path
import ast
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'scheme_A_W2_hook_review_20261022_60/implementation/w2_author/owned_m4_diagnostic_driver_v1.py'
text = SOURCE.read_text()
tree = ast.parse(text, filename=str(SOURCE))
main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')


def original_branch(line):
    return next(node for node in ast.walk(main) if isinstance(node, ast.If) and node.lineno == line)


def execute(node, environment):
    unit = ast.Module(body=[node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(unit), str(SOURCE), 'exec'), environment)


observation = {'case': 'W2-native-boundary-hold', 'accepted_pairs': 1,
               'stall_entered': False, 'transition_ns': None, 'watchdog_ns': None,
               'transition_reason': None, 'result': {}}
try:
    execute(original_branch(514), observation)
    raised = None
except AssertionError as exc:
    raised = str(exc)
assert raised == 'W1 never observed the Worker entering its registered stall', raised

forged = {
    'case': 'W2-native-boundary-hold',
    'reg': {'expected': {'w2_exit_codes': {'worker': 2}}},
    'w2': {'job_id': 2, 'ordinal': 1, 'ticks_before_release': 2},
    'by_role': {'worker': {'returncode': 2, 'group_empty': False},
                'regulator': {'returncode': 99, 'group_empty': False},
                'fixture': {'returncode': 99, 'group_empty': False},
                'recorder': {'returncode': 99, 'group_empty': False}},
    'common_ok': False,
    'result': {'error': 'prior stimulus failure', 'w2_boundary_entered': True,
               'w2_release_sent': True, 'w2_ticks_after_enter': [10, 11],
               'w2_result': {'job_id': 999, 'ordinal': 99,
                             'disposition': 'expired', 'actual_native_invoked': False},
               'transition_ns': None, 'ramp_ok': True},
}
execute(original_branch(639), forged)
assert forged['result']['passed'] is True

with_transition = {
    'case': 'W2-native-boundary-hold', 'reg': forged['reg'], 'w2': forged['w2'],
    'by_role': {'worker': {'returncode': 2}}, 'common_ok': True,
    'result': {'w2_boundary_entered': True, 'w2_release_sent': True,
               'w2_ticks_after_enter': [10, 11],
               'w2_result': {'job_id': 2, 'ordinal': 1, 'disposition': 'expired',
                             'actual_native_invoked': False},
               'transition_ns': 1500000000, 'transition_reason': 'fatal_capability',
               'ramp_ok': True},
}
execute(original_branch(639), with_transition)
assert with_transition['result']['passed'] is False

summary_environment = {
    'case': 'W2-native-boundary-hold', 'result': {},
    'w2_entered_at': 1000000000, 'w2_entered_row': {'job_id': 2, 'ordinal': 1},
    'w2_release_sent': True, 'w2_release_frame': b'frame',
    'w2_ticks_after_enter': [10, 11],
    'w2_result': {'job_id': 2, 'ordinal': 1, 'disposition': 'expired',
                  'actual_native_invoked': False},
    'ramp_ok': True, 'transition_ns': 1500000000,
    'transition_reason': 'fatal_capability',
}
execute(original_branch(607), summary_environment)
assert 'ramp_ok' not in summary_environment['result']
assert 'transition_ns' not in summary_environment['result']

observed = []
wrong_entry = {
    'wt': 'w2_boundary_entered', 'w2': {'job_id': 2, 'ordinal': 1},
    'wrow': {'job_id': 999, 'ordinal': 99, 'entered_ns': 1000000000,
             'job_deadline_ns': 1150000000},
    'event': lambda *args, **values: observed.append({'args': args, 'values': values}),
}
execute(original_branch(365), wrong_entry)
assert wrong_entry['w2_entered_at'] == 1000000000

result = {
    'schema': 'W2-exact-original-driver-branch-probes-v2',
    'scope': 'AST-isolated submitted statements; no imports, main, ROS, processes, or owned run',
    'normal_W2_observation_rejected_by_W1_assertion': {
        'line': 514, 'assertion': raised},
    'final_predicate_false_positive': {
        'line': 639, 'actual_passed': forged['result']['passed'],
        'prior_error': forged['result']['error'], 'wrong_job': 999, 'wrong_ordinal': 99,
        'other_role_exit_codes': [99, 99, 99], 'group_empty': False,
        'common_ok': False,
        'reachability_note': 'Whole main currently hits the earlier W1 fallthrough; this independently probes the newly added W2 final predicate'},
    'terminal_fatal_transition_rejected': {
        'line': 639, 'transition_reason': 'fatal_capability',
        'actual_passed': with_transition['result']['passed']},
    'W2_summary_drops_observed_fields': {
        'ramp_ok_present': 'ramp_ok' in summary_environment['result'],
        'transition_ns_present': 'transition_ns' in summary_environment['result'],
        'scope': 'Existing final predicate requires ramp_ok=True, but the W2 summary never copies that local value'},
    'wrong_target_entry_consumed': {'registered_job_id': 2, 'event_job_id': 999,
                                    'registered_ordinal': 1, 'event_ordinal': 99,
                                    'accepted_entered_ns': wrong_entry['w2_entered_at']},
    'exact_channel_manifest_key_present_in_driver_AST': 'w2_release_channel' in {
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)},
}
out = ROOT / 'evidence/driver_branch_probes_v2.json'
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
