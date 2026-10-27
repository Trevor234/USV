#!/usr/bin/env python3
"""Offline evidence corruption and actual adapter-branch tests; no ROS processes."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace
import traceback

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
sys.path[:0] = [str(D / 'author'), str(D / 'implementation')]
from fault_self_close_v1 import ROLES, perform_driver_branch, validate_entry, validate_observer_terminal, final_fault_case_completed
from check_fault_self_close_v1 import check


def need(value, reason):
    if not value:
        raise AssertionError(reason)


def load(path):
    return json.loads(Path(path).read_bytes())


def setpath(data, path, value):
    for key in path[:-1]:
        data = data[key]
    data[path[-1]] = value


def context_for(bundle):
    return {'profile': 'sink-fault-self-close-v1', 'run_id': bundle['run_id'], 'boot_id': bundle['boot_id'],
            'contract_sha256': bundle['inputs']['contract_sha256'], 'released': True,
            'diagnostic_shadow_only': True, 'expected_header': bundle['expected_header'],
            'roles': {r: {'manifest': bundle['manifests'][r],
                         'registered_identity': next(x['identity'] for x in bundle['ledger'] if x['type'] == 'spawn' and x['name'] == r),
                         'manifest_sha256': bundle['manifest_hashes'][r],
                         'prepared_manifest_sha256': bundle['preparation']['roles'][r]['manifest_sha256'],
                         'prepared_source_bundle_sha256': bundle['preparation']['roles'][r]['source_bundle_sha256'],
                         'prepared_parameter_digest': bundle['preparation']['roles'][r]['effective_parameters_sha256']}
                      for r in ROLES}}


class OfflineSupervisor:
    """Test double only: does not inspect or signal a process."""
    def __init__(self, bundle, case):
        self.boot = bundle['boot_id']
        self.case = case
        self.stopped = set()
        self.calls = []
        self.unexpected_descendants = []
        self.unverified_children = []
        self.cleanup_failed = False
        self.evidence_failed = case == 'ledger_failure'
        self.memory_tail = []
        self.owned = {}
        for role in ROLES:
            identity = deepcopy(next(r['identity'] for r in bundle['ledger'] if r['type'] == 'spawn' and r['name'] == role))
            process = SimpleNamespace(poll=lambda role=role: (2 if role == 'observer' else 0) if role in self.stopped else None)
            self.owned[role] = SimpleNamespace(name=role, identity=identity, process=process)
        if case == 'PID_start_mismatch':
            self.owned['observer'].identity['start_ticks'] += 1
    def members(self, item):
        return [] if item.name in self.stopped else [item.identity]
    def stop(self, item, grace, term, kill, *, natural_grace):
        self.calls.append({'role': item.name, 'grace': grace, 'term': term, 'kill': kill, 'natural_grace': natural_grace})
        if self.case == 'stop_raises' and item.name == 'observer':
            raise RuntimeError('declared offline supervisor stop failure')
        self.stopped.add(item.name)
        if self.case == 'forced_cleanup' and item.name == 'worker':
            self.memory_tail.append({'type': 'signal', 'signal': 15, 'name': 'worker'})
        return {'name': item.name, 'returncode': 2 if item.name == 'observer' else 0,
                'cleanup_complete': True, 'remaining_members': [], 'unexpected_descendants': [],
                'qualification_clean': item.name != 'observer'}


def adapter_case(bundle, case):
    origin = Path(bundle['original_run_root'])
    with tempfile.TemporaryDirectory(prefix='scheme_A_batch34_component_', dir='/tmp') as tmp:
        root = Path(tmp)
        names = ['preparation_evidence.json', 'observer/v1_fault.json', 'observer/witness.json', 'observer/source.jsonl']
        names += [r + '/owned_manifest.json' for r in ROLES]
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin / name, target)
        if case == 'Witness_missing':
            (root / 'observer/witness.json').unlink()
        if case == 'report_IO_collision':
            (root / 'fault_self_close_driver.json').write_text('{}\n')
        sup = OfflineSupervisor(bundle, case)
        cleanup = {}
        roles = {r: {'manifest': bundle['manifests'][r], 'sha256': bundle['manifest_hashes'][r]} for r in ROLES}
        def proof():
            need('publisher' in sup.stopped, 'exit proof before Publisher stop')
            return {'offline_test_double': True, 'actual_exit_proven': False}
        start = time.monotonic_ns() - (16_000_000_000 if case == 'expired_budget' else 0)
        report = perform_driver_branch(root, sup, sup.owned, roles, expected_header=bundle['expected_header'],
            contract_sha256=bundle['inputs']['contract_sha256'], released=True, close_start_ns=start,
            overall_deadline_ns=time.monotonic_ns() + 20_000_000_000, cleanup=cleanup, owner_exit_proof=proof)
        need([r['role'] for r in sup.calls] == list(ROLES), 'all owned stops must continue in declared order')
        need(report['driver_sequence_completed'] is (case == 'positive'), 'wrong component outcome:' + case)
        need(not (root / 'adapter_driver_close_request.json').exists()
             and not (root / 'adapter_driver_close_ack.json').exists(), 'fault branch emitted normal ACK traffic')
        if case == 'positive':
            need(sup.calls[0]['natural_grace'] > 0 and all(r['natural_grace'] == 0 for r in sup.calls[1:]), 'bounded natural Observer wait')
            need(load(root / 'fault_self_close_driver.json') == report, 'driver report write mismatch')
        return {'case': case, 'passed': True, 'driver_sequence_completed': report['driver_sequence_completed'],
                'stop_calls': sup.calls, 'errors': report['errors'], 'offline_test_double': True,
                'actual_processes_or_ROS_started': False}


def main():
    cases, negative = [], []
    bundles = [load(D / 'evidence' / (run + '_normalized_v1.json')) for run in ['v1_sink_01', 'v1_sink_ack_02']]
    for bundle in bundles:
        report = check(bundle)
        need(report == load(D / 'verification' / (bundle['run_id'] + '_fault_closure_v1.json')), 'independent checker report changed')
        context = context_for(bundle)
        validate_entry(context, bundle['fault'])
        validate_observer_terminal(context, bundle['fault'], bundle['observer_source'], bundle['witness'])
        cases.append({'case': bundle['run_id'] + '_positive_existing_raw', 'passed': True,
                      'original_V1_strict_order_passed': report['original_V1_strict_order_passed']})
        cases.append({'case': bundle['run_id'] + '_driver_adapter_positive', **adapter_case(bundle, 'positive')})
    basis = bundles[1]
    zero_index = next(i for i, r in enumerate(basis['publisher_source'])
                      if r.get('type') == 'controlled_Applied_emitted' and r['control_source'] == 'shutdown_zero')
    zero_sequence = str(basis['publisher_source'][zero_index]['applied_sequence'])
    stored_index = next(i for i, r in enumerate(basis['stored_applied']) if str(r['decoded']['sequence']) == zero_sequence)
    receipt_index = next(i for i, r in enumerate(basis['transport'])
                         if r['payload_sha256'] == basis['stored_applied'][stored_index]['wire_sha256'])
    source_terminal_index = len(basis['observer_source']) - 1
    signal_index = next(i for i, r in enumerate(basis['ledger']) if r['type'] == 'signal')
    tests = [
        ('normal_profile_cannot_consume_fault', ['requested_profile'], 'normal', 'explicit_checker_profile'),
        ('wrong_fault_run', ['fault', 'run_id'], 'different_run', 'fault_identity'),
        ('wrong_boot', ['fault', 'boot_id'], 'different_boot', 'fault_identity'),
        ('PID_reuse', ['manifests', 'observer', 'process_start_ticks'], 1, 'spawn_prepared_identity'),
        ('ELF_mismatch', ['binary_hashes', 'observer'], '0' * 64, 'selected_binary'),
        ('source_bundle_mismatch', ['manifests', 'observer', 'source_bundle_sha256'], '0' * 64, 'prepared_source_bundle'),
        ('typed_config_change', ['manifests', 'publisher', 'effective_parameters', 'dynamic.dt', 'value'], .25, 'parameter_canonical'),
        ('exit2_without_Sink_failure', ['fault', 'sink', 'failed'], False, 'actual_Sink_rejection'),
        ('Witness_incomplete', ['witness', 'incomplete'], True, 'Witness_terminal_complete'),
        ('Witness_wrong_source', ['witness', 'header', 'source_sha256'], '0' * 64, 'Witness_header'),
        ('Source_claims_normal', ['observer_source', source_terminal_index, 'normal_source_complete'], True, 'Source_fault_accounting'),
        ('Source_bad_counts', ['observer_source', source_terminal_index, 'dropped'], 0, 'Source_fault_accounting'),
        ('group_remaining', ['original_result', 'cleanup', 'worker', 'remaining_members'], [{'pid': 42}], 'cleanup_record_binding'),
        ('SIGTERM_escalation', ['ledger', signal_index, 'signal'], 15, 'escalated_cleanup_signal'),
        ('nonzero_shutdown_command', ['publisher_source', zero_index, 'final_n'], [.5, .5], 'zero_command_value'),
        ('one_API_failure', ['publisher_applied', zero_sequence, 'left_publish_success'], False, 'successful_both_API_zero'),
        ('boolean_coercion', ['publisher_applied', zero_sequence, 'left_publish_success'], 1, 'successful_both_API_zero'),
        ('Applied_wrong_clock', ['publisher_applied', zero_sequence, 'steady_clock_domain'], 'wrong_clock', 'zero_Applied_identity'),
        ('Stored_value_changed', ['stored_applied', stored_index, 'decoded', 'right_publish_success'], False, 'Stored_full_Applied_value_binding'),
        ('foreign_GID', ['transport', receipt_index, 'publisher_gid'], [0] * 16, 'Fixture_exact_wire_owner_GID'),
        ('Fixture_closed_early', ['fixture_terminal', 'closed_steady_ns'], 0, 'Fixture_closed_after_receipt'),
        ('Recorder_no_clean_stop', ['recorder_terminal', 'Recorder_stop_completed'], False, 'Recorder_actual_clean_stop'),
        ('Recorder_wrong_metadata', ['recorder_terminal', 'metadata_sha256'], '0' * 64, 'Recorder_actual_clean_stop'),
        ('SQL_count_mismatch', ['storage_counts', '/research/control/applied'], 123, 'SQL_metadata_full_counts'),
        ('historical_normal_false_must_stay_false', ['original_result', 'passed'], True, 'historical_normal_status'),
    ]
    for name, path, value, reason in tests:
        bundle = deepcopy(basis)
        setpath(bundle, path, value)
        try:
            check(bundle)
        except ValueError as error:
            need(reason in str(error), 'unexpected rejection:' + name + ':' + str(error))
            negative.append({'case': name, 'rejected': True, 'reason': str(error)})
        else:
            raise AssertionError('accepted malformed evidence:' + name)
    for case in ['PID_start_mismatch', 'Witness_missing', 'report_IO_collision', 'stop_raises',
                 'expired_budget', 'ledger_failure', 'forced_cleanup']:
        cases.append(adapter_case(basis, case))
    parent = (D.parent / 'p1_execution_architecture_20261005_01/authored_D1_V1_sink_failure_20261019_v33r2/prepare_pair_wakeup_v1.py').read_text()
    finalization_cases = []
    valid_result = {'close_policy': 'sink-fault-self-close-v1', 'run_id': 'offline_final', 'V1_fault_observed': True,
                    'cleanup_complete': True, 'cleanup_within_budget': True, 'ledger_failed': False,
                    'close_errors': [], 'fault_self_close_driver': {'profile': 'sink-fault-self-close-v1',
                    'run_id': 'offline_final', 'driver_sequence_completed': True}}
    for name, mutation in [('positive', None), ('ledger_close_failure', ('ledger_failed', True)),
                           ('unexpected_driver_error', ('error', 'unexpected')), ('close_error', ('close_errors', ['error'])),
                           ('cleanup_incomplete', ('cleanup_complete', False)), ('budget_overrun', ('cleanup_within_budget', False)),
                           ('normal_profile', ('close_policy', 'normal')), ('foreign_run_report', ('run_id', 'foreign'))]:
        current = deepcopy(valid_result)
        if mutation:
            current[mutation[0]] = mutation[1]
        supervisor = OfflineSupervisor(basis, 'positive')
        need(final_fault_case_completed(current, supervisor) is (name == 'positive'), 'final outcome:' + name)
        finalization_cases.append({'case': name, 'passed': True, 'fault_case_completed': name == 'positive'})
    derived = (D / 'author/prepare_pair_wakeup_v1.py').read_text()
    start = "  if released and a.close_order=='publisher-first' and 'observer' in owned:\n"
    end = "  for name in ['foreign','publisher','observer','worker','synthetic_source','recorder']:stop(name)\n"
    normal_parent = parent[parent.index(start):parent.index(end)]
    normal_derived_start = start.replace('  if ', '  elif ', 1)
    normal_derived = derived[derived.index(normal_derived_start):derived.index(end)].replace(normal_derived_start, start, 1)
    need(normal_parent == normal_derived, 'old normal close branch changed')
    need("inputs['close_order']=['observer','publisher','worker','synthetic_source','recorder']" in derived
         and "inputs['close_policy']=FAULT_CLOSE_PROFILE" in derived
         and "result['close_policy']=FAULT_CLOSE_PROFILE" in derived, 'effective fault close policy must match actual order')
    tree = ast.parse(derived)
    need(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'perform_driver_branch'
             for n in ast.walk(tree)), 'derived driver does not invoke implemented adapter')
    for path in [D / 'author/prepare_pair_wakeup_v1.py', D / 'author/fault_self_close_v1.py',
                 D / 'implementation/check_fault_self_close_v1.py', Path(__file__), D / 'audit_existing_runs_v1.py']:
        compile(path.read_text(), str(path), 'exec')
    unchanged = []
    origin = D.parent / 'p1_execution_architecture_20261005_01/authored_D1_V1_sink_failure_20261019_v33r2'
    for path in sorted((D / 'author').rglob('*')):
        if not path.is_file() or path.name in ['prepare_pair_wakeup_v1.py', 'fault_self_close_v1.py']:
            continue
        relative = path.relative_to(D / 'author')
        need(path.read_bytes() == (origin / relative).read_bytes(), 'unrelated author source changed:' + str(relative))
        unchanged.append(str(relative))
    out = {'passed': True, 'offline_cases': cases, 'targeted_negative_cases': negative, 'finalization_cases': finalization_cases,
           'targeted_rejected': len(negative), 'adapter_cases': 9,
           'old_normal_close_branch_byte_identical': True, 'unchanged_copied_parent_files': unchanged,
           'actual_new_control_runs': 0, 'new_driver_executed_live': False,
           'normal_close_qualified': False, 'stage_qualified': False, 'execute_qualified': False,
           'true_plant_qualified': False, 'research_conclusion': False}
    with (D / 'verification/targeted_offline_checks_v3.json').open('x') as stream:
        json.dump(out, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': True, 'targeted_rejected': len(negative), 'adapter_cases': 9,
                      'copied_parent_files_unchanged': len(unchanged), 'finalization_cases': len(finalization_cases), 'actual_new_control_runs': 0}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        with (D / 'verification/targeted_offline_checks_failure_v3.json').open('x') as stream:
            json.dump({'passed': False, 'error': repr(error), 'traceback': traceback.format_exc()}, stream, indent=2)
        print(traceback.format_exc())
        raise SystemExit(2)
