#!/usr/bin/env python3
"""Private, offline review. Reads historical artifacts; writes only alongside this file."""
import ast
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
BASE = Path('/home/trevor/USV/.sgh-research/experiments')
B70 = BASE / 'scheme_A_M4_t1_semantic_supp_20261024_70'
B71 = BASE / 'scheme_A_M4_t2_action_freeze_20261024_71'
B72 = BASE / 'scheme_A_M4_t2a_clock_freeze_owned_20261024_72'
AUTHOR = B72 / 'implementation/t2_author_rev8'
sys.path.insert(0, str(AUTHOR))
import t2_action_contract as t2
import audit_t2


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def all_bools(checks):
    return all(v is True for v in checks.values() if isinstance(v, bool))


table = read(B72 / 'implementation/t2_tables_v8/T2C_v8.json')
trigger = {'phase': 'ready_window', 'job': {'job_id': 2}, 'observed_ns': 1000,
           'source_role': 'regulator'}
command = {'schema': t2.COMMAND_SCHEMA, 'run_id': table['run_id'],
           'contract_sha256': table['contract_sha256'], 'action_id': 'a1',
           'sequence': 1, 'trigger': trigger}
bad_command = copy.deepcopy(command)
bad_command['trigger'] = {'observed_ns': 1000, 'job': {'job_id': 2}}
results = {'owned_started': False, 'ROS_initialized': False}
try:
    t2.validate_command(bad_command, table, [])
    results['actual_ready_cache_shape'] = 'UNEXPECTED ACCEPT'
except AssertionError as error:
    results['actual_ready_cache_shape'] = str(error)

receipt = {'type': t2.RECEIPT_TYPE, 'action_id': 'a1', 'executed_ns': 2000,
           'trigger': trigger, 'command_sha256': t2.digest(t2.encoded_json(command))}
probes = {}
wrong_sha = copy.deepcopy(receipt)
wrong_sha['command_sha256'] = '0' * 64
probes['wrong_command_sha256'] = [wrong_sha]
foreign = copy.deepcopy(receipt)
foreign.update(action_id='alien', executed_ns=2001)
probes['foreign_extra_action_id'] = [receipt, foreign]
wrong_job = copy.deepcopy(receipt)
wrong_job['trigger']['job']['job_id'] = 999
probes['wrong_bound_job'] = [wrong_job]
results['receipt_counterexamples'] = {
    name: t2.check_receipts(table, rows, []) for name, rows in probes.items()
}

driver_event = {'type': 't2_driver_action_executed', 'checked_ns': 2000,
                'action_id': 'a1', 'command': command, 'executed_ns': 2000}
sources = {
    'no_target_guard_or_decision': [{'type': 'owned_reception_closed', 'closed_ns': 2500}],
    'accepted_target_after_request': [
        {'type': 'owned_reception_closed', 'closed_ns': 2500},
        {'type': 'decision', 'job_id': 2, 'accepted': True, 'activation_commit_ns': 3000}],
    'rejected_target_guard_before_request': [
        {'type': 'owned_reception_closed', 'closed_ns': 2500},
        {'type': 'decision', 'job_id': 2, 'accepted': False,
         'ready_commit_ns': 1000, 'activation_commit_ns': 1600, 'reason': 'shutdown'}],
}
results['t2c_audit_counterexamples'] = {}
for name, source in sources.items():
    root = OUT / name
    (root / 'regulator').mkdir(parents=True, exist_ok=True)
    (root / 'driver_events.jsonl').write_text(json.dumps(driver_event) + '\n')
    (root / 'regulator/source.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in source))
    (root / 'action_table_copy.json').write_text(json.dumps(table) + '\n')
    checks = audit_t2.audit_run(root, table)
    results['t2c_audit_counterexamples'][name] = {'checks': checks, 'all_boolean_checks_pass': all_bools(checks)}

# Re-evaluate the retained GoogleTest JSON through the original strict verdict code.
spec = importlib.util.spec_from_file_location('private70verdict', B70 / 'implementation/runner_verdict_v2.py')
verdict = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verdict)
verification = read(B70 / 'evidence/supp_t1/attempt04/verification_v1.json')
expected = verification['expected_tests']
baseline_rows = verdict.baseline_verdict(read(verification['nominal']['doc']),
                                        verification['nominal']['returncode'], expected)
values = {}
for node in ast.parse((B70 / 'evidence/spec68/scripts/run_t1.py').read_text()).body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == 'MUTATIONS':
                values[target.id] = ast.literal_eval(node.value)
mutation_specs = {r['name']: r for r in values['MUTATIONS']}
mutations = []
for record in verification['mutations']:
    doc = B70 / 'evidence/supp_t1/attempt04' / (record['name'] + '_run01/gtest.json')
    caught = verdict.mutation_verdict(read(doc), record['returncode'], expected,
                                      mutation_specs[record['name']]['expect_caught_by'],
                                      record['prepared'], 0)
    mutations.append({'name': record['name'], 'returncode': record['returncode'],
                      'named_assertions': caught, 'prepared_source_matches_pin':
                      pin(record['source']['path']) == {k: record['source'][k] for k in ('bytes', 'sha256')},
                      'gtest': str(doc)})
source69 = BASE / 'scheme_A_M4_t1_review_20261024_69/implementation/reviewed_harness/tests/test_current_candidate_reference_clock.cpp'
harness = B70 / 'implementation/supp_harness'
anchor = b'   return {d.candidate_accepted,d.reason,d.control_source};\n }\n'
original = source69.read_bytes()
derived = original.replace(anchor, anchor + (harness / 's1_helpers_insert.cpp').read_bytes(), 1) + (harness / 's1_tests_append.cpp').read_bytes()
results['batch70'] = {
    'strict_baseline_pass': True, 'executed_tests': len(baseline_rows),
    'baseline_doc': verification['nominal']['doc'], 'mutations': mutations,
    'original_25_tests_preserved_exactly_by_derivation': derived == (harness / 'tests/test_current_candidate_reference_clock.cpp').read_bytes(),
    'retained_attempt_complete': verification['complete'],
    'retained_source_pins_match_current': all(pin(path) == value for path, value in verification['source_pins_before'].items()),
    'retained_before_after_pins_equal': verification['source_pins_before'] == verification['source_pins_after'],
    'regulator_sha256': pin(BASE / 'scheme_A_M4_fixture_gap_20261024_67/implementation/current_author/observer/src/shadow/regulator_owned_execute.cpp')['sha256'],
    'closed_69_scope_debts': [
        'success and solver_invoked isolated false gates; prediction_available was isolated in 69',
        'native X/U/control dimensions proved constructively by fixed wire type; metadata rejection kept distinct',
        'real prepare_loop emits committed Job and successful publish; real echo admits synthetic result without seed_echo',
        'real preparation submit rejects stopping/version change; logical pre-ready old version result rejects; new generation registers and activates',
        'ordinary fresh odom followed by real activate_candidate through admission.take; task/config/schedule rejection dimensions enumerated'],
    'scope_remaining': 'Component seam only; stale/new Candidate results are helper constructed. Five owned atoms remain T2; no real Worker solve or four-role closure is claimed.'
}
source_facts = {}
types = {'job', 'job_publish_result', 'reference_epoch_committed', 'job_not_submitted', 'candidate_registration', 'path_version'}
for name in ('RealPrepareLoopSubmitsJob', 'RealSubmitBlockedByShutdownBeforeSubmit',
             'RealSubmitBlockedByVersionChangeBeforeSubmit', 'ReferenceOrdinaryNewOdomActivation'):
    path = B70 / 'evidence/supp_t1/attempt04/nominal_run01/cases' / name / 'source.jsonl'
    source_facts[name] = {'path': str(path), 'events': [json.loads(line) for line in path.read_text().splitlines() if json.loads(line).get('type') in types]}
save('batch70_source_facts.json', source_facts)

bundle = read(B72 / 'evidence/freeze_rev8/source_bundle.json')
registry = read(B72 / 'implementation/t2_registry_v8.json')
results['rev8_identity_readback'] = {
    'bundle_file_count': len(bundle['files']),
    'bundle_files_match': all(pin(item['path']) == {k: item[k] for k in ('bytes', 'sha256')} for item in bundle['files'].values()),
    'driver_matches': pin(registry['driver'])['sha256'] == registry['driver_tool_sha256'],
    'ELFs_match': {role: pin(item['binary'])['sha256'] == item['binary_sha256'] for role, item in registry['roles'].items()},
    'registrations_match': {tag: all(pin(reg[key])['sha256'] == reg[key + '_sha256'] for key in ('action_table', 'registry'))
                            and pin(reg['audit_tool']['path'])['sha256'] == reg['audit_tool']['sha256']
                            for tag in ('T2A', 'T2B', 'T2C')
                            for reg in [read(B72 / ('implementation/t2_registrations_v8/' + tag + '_v8.json'))]}
}
save('counterexample_inputs.json', {'table': table, 'actual_ready_cache_command': bad_command,
                                  'receipt_probes': probes, 'driver_event': driver_event, 'regulator_sources': sources})
save('results.json', results)
print(json.dumps(results, ensure_ascii=False, indent=2))
