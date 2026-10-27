#!/usr/bin/env python3
"""Native entry-policy checks with independently declared expected facts.

All contexts and API outcomes here are synthetic deterministic component input.
No context in this test proves actual ROS graph ownership or actuator output.
"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

D = Path(__file__).resolve().parent.parent
G = 1000000000
MS = 1000000


def enc(v):
    return (json.dumps(v, separators=(',', ':'), sort_keys=True, allow_nan=False) + '\n').encode()


def pin(p):
    raw = p.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    spec = json.loads((D / 'implementation/current_contract_spec_v1.json').read_bytes())
    contract = D / 'verification/owned_frozen_shape_only.json'
    context = {'run_id': 'component_owned_run_47', 'boot_id': '96645bc1-f6e0-49ff-b66e-809611803ed5',
               'contract_sha256': pin(contract)['sha256'], 'freeze_evidence_sha256': 'e' * 64,
               'policy_sha256': spec['target_policy_sha256'], 'regulator_manifest_sha256': 'b' * 64,
               'producer_id': 'component_owned_regulator_47', 'role': 'p1_owned_execute_regulator',
               'pid': 12345, 'start_ticks': 123456, 'output_gids': ['1' * 48, '2' * 48],
               'old_outputs_absent': True, 'worker_output_count': 0, 'fixture_output_count': 0,
               'recorder_output_count': 0, 'worker_capability_live': True, 'recorder_ready': True,
               'inputs_ready': True, 'source_graph_verified': True}
    base = {'contract': str(contract), 'mode': 'no_output', 'expected': copy.deepcopy(context), 'actual': copy.deepcopy(context), 'prepare_ns': G}
    cases = []

    def add(name, request=None, accepted=True, checks=()):
        cases.append({'name': name, 'request': copy.deepcopy(base if request is None else request),
                      'expected_accepted': accepted, 'checks': list(checks)})

    def scenario(name, steps, checks=(), accepted=True):
        request = copy.deepcopy(base);request['steps'] = steps
        add(name, request, accepted, checks)

    def pair(t, command=(0, 0), reason='bootstrap', returned=(True, True), activation=None, span=300):
        start = G + t
        value = {'op': 'pair', 'starts': [start, start + 200], 'ends': [start + 100, start + span],
                 'command': list(command), 'reason': reason, 'returned': list(returned)}
        if activation is not None:value['activation_ns'] = G + activation
        return value

    def check(event, path, value):
        return {'event': event, 'path': path, 'value': value}

    add('exact_synthetic_context')
    for key in context:
        request = copy.deepcopy(base);request['actual'].pop(key)
        add('missing_context_' + key, request, False)
    for key in ['run_id', 'boot_id', 'contract_sha256', 'freeze_evidence_sha256', 'policy_sha256', 'regulator_manifest_sha256', 'producer_id', 'pid', 'start_ticks', 'output_gids']:
        request = copy.deepcopy(base)
        value = request['actual'][key]
        request['actual'][key] = (value + 1 if type(value) is int else ['3' * 48, '4' * 48] if type(value) is list else value[:-1] + ('c' if value[-1] != 'c' else 'd'))
        add('registry_mismatch_' + key, request, False)
    for key in ['old_outputs_absent', 'worker_capability_live', 'recorder_ready', 'inputs_ready', 'source_graph_verified']:
        for bad in [False, 1]:
            request = copy.deepcopy(base);request['actual'][key] = bad;request['expected'][key] = bad
            add('semantic_ready_' + key + '_' + str(bad), request, False)
    for key in ['worker_output_count', 'fixture_output_count', 'recorder_output_count']:
        for bad in [1, False, 0.0]:
            request = copy.deepcopy(base);request['actual'][key] = bad;request['expected'][key] = bad
            add('nonowner_output_or_type_' + key + '_' + repr(bad), request, False)
    for name, key, value in [('oldrole', 'role', 'p1_regulator_shadow_observer'), ('duplicate_gid', 'output_gids', ['1' * 48] * 2),
                             ('zero_pid', 'pid', 0), ('float_pid', 'pid', 12345.0), ('bool_start', 'start_ticks', True),
                             ('empty_run', 'run_id', ''), ('oversize_run', 'run_id', 'a' * 97)]:
        request = copy.deepcopy(base);request['actual'][key] = value;request['expected'][key] = value
        add(name, request, False)
    for mode in ['execute', 'shadow', 'NO_OUTPUT']:
        request = copy.deepcopy(base);request['mode'] = mode
        add('runtime_mode_' + mode, request, False)
    for name in ['current_pre_freeze_contract_v1.json', 'owned_pre_freeze_contract_v1.json', 'current_diag_contract_v1.json']:
        request = copy.deepcopy(base);request['contract'] = str(D / 'implementation' / name)
        add('wrong_entry_contract_' + name, request, False)
    scenario('initial_numeric_zero_is_unknown', [{'op': 'fallback', 'now': G}], [check(0, 'command', [0, 0]), check(0, 'state.known', [False, False]), check(0, 'state.business_permitted', False)])
    scenario('first_actual_zero_pair', [pair(0)], [check(0, 'initial_pair', True), check(0, 'rho_available', False), check(0, 'state.known', [True, True]), check(0, 'state.time', [G, G + 200]), check(0, 'state.seq', [1, 1]), check(0, 'state.business_permitted', True)])
    scenario('waiting_heartbeat_keeps_zero_no_accept_renewal', [pair(0), pair(200 * MS, reason='waiting')], [check(1, 'state.seq', [2, 2]), check(1, 'state.last_accepted_ns', 0), check(1, 'rho_available', True), check(1, 'gap_exceeded', False)])
    scenario('bootstrap_deadline_equal', [pair(200 * MS)], [check(0, 'bootstrap_late', False), check(0, 'state.terminal', False)])
    scenario('bootstrap_deadline_after', [pair(200 * MS + 1)], [check(0, 'bootstrap_late', True), check(0, 'state.terminal', True), check(0, 'state.known', [True, True])])
    scenario('full_gap_equal', [pair(0), pair(240 * MS, reason='waiting')], [check(1, 'gap_exceeded', False), check(1, 'state.terminal', False)])
    scenario('full_gap_after', [pair(0), pair(240 * MS + 1, reason='waiting')], [check(1, 'gap_exceeded', True), check(1, 'state.terminal', True), check(1, 'state.seq', [2, 2])])
    scenario('startup_legacy_1_54s_is_failure', [pair(0), pair(1540 * MS, reason='waiting')], [check(1, 'gap_exceeded', True), check(1, 'state.business_permitted', False)])
    scenario('span_equal', [pair(0, span=5 * MS)], [check(0, 'span_exceeded', False), check(0, 'state.terminal', False)])
    scenario('span_after_successes_irreversible', [pair(0, span=5 * MS + 1)], [check(0, 'span_exceeded', True), check(0, 'state.known', [True, True]), check(0, 'state.seq', [1, 1]), check(0, 'state.terminal', True)])
    accepted16 = pair(200 * MS, [16, 16], 'accepted', activation=200 * MS)
    accepted25 = pair(400 * MS, [25, 25], 'accepted', activation=400 * MS)
    scenario('per_side_rate_equal', [pair(0), accepted16], [check(1, 'rate_exceeded', False), check(1, 'state.n', [16, 16]), check(1, 'state.last_accepted_ns', G + 200 * MS)])
    scenario('rate_after_preserves_actual_success', [pair(0), pair(200 * MS, [16.000001, 16], 'accepted', activation=200 * MS)], [check(1, 'rate_exceeded', True), check(1, 'state.n', [16.000001, 16]), check(1, 'state.last_accepted_ns', 0)])
    scenario('magnitude_over_bound', [pair(0), pair(200 * MS, [26, 0], 'accepted', activation=200 * MS)], [check(1, 'command_invalid', True), check(1, 'state.terminal', True)])
    scenario('no_fake_nonzero_bootstrap', [pair(0, [1, 0])], [check(0, 'command_invalid', True), check(0, 'state.initialized', False), check(0, 'state.business_permitted', False)])
    scenario('partial_first_success_side_retained', [pair(0, returned=[False, True])], [check(0, 'both_returned', False), check(0, 'state.known', [False, True]), check(0, 'state.seq', [0, 1]), check(0, 'state.time', [0, G + 200]), check(0, 'state.terminal', True)])
    scenario('partial_business_no_false_accept', [pair(0), pair(200 * MS, [16, 16], 'accepted', [False, True], 200 * MS), {'op': 'fallback', 'now': G + 400 * MS}], [check(1, 'state.known', [False, True]), check(1, 'state.n', [0, 16]), check(1, 'state.last_accepted_ns', 0), check(2, 'command', [0, 0])])
    scenario('terminal_not_revived_by_fresh_zero', [pair(0, returned=[False, True]), pair(200 * MS)], [check(1, 'state.initialized', True), check(1, 'state.terminal', True), check(1, 'state.business_permitted', False)])
    hold = [pair(0), accepted16, accepted25]
    for t in [600, 800, 1000]:hold += [{'op': 'fallback', 'now': G + t * MS}, pair(t * MS, [25, 25], 'fallback')]
    hold += [{'op': 'fallback', 'now': G + 1200 * MS}]
    scenario('hold_equality_then_ramp_republish_does_not_renew', hold, [check(7, 'command', [25, 25]), check(8, 'state.last_accepted_ns', G + 400 * MS), check(9, 'command', [9, 9.000016])])
    # Right actual anchor is 200 ns later; its ramp interval is correspondingly shorter.
    scenario('invalid_bypasses_hold_each_side_elapsed', [pair(0), accepted16, accepted25, {'op': 'fallback', 'now': G + 600 * MS, 'invalid': True}], [check(3, 'command', [9, 9.000016])])
    for offset, good in [(20 * MS, True), (20 * MS + 1, False), (1000 * MS, False)]:
        scenario('tick_jitter_or_skip_' + str(offset), [{'op': 'tick', 'now': G + offset}], [check(0, 'tick_ok', good), check(0, 'state.terminal', not good)])
    scenario('repeated_tick_forbidden', [{'op': 'tick', 'now': G}, {'op': 'tick', 'now': G}], accepted=False)
    for label, command, returned, delta, expected in [
        ('zero_requested_API_failed', [0, 0], [False, True], 1, {'zero_requested': True, 'zero_target_published': False, 'exit_tick': True, 'grace_exceeded': False}),
        ('both_zero_APIs_returned', [0, 0], [True, True], 1, {'zero_requested': True, 'zero_target_published': True, 'exit_tick': True, 'grace_exceeded': False}),
        ('nonzero_before_grace', [9, 9], [True, True], 2499999999, {'zero_requested': False, 'zero_target_published': False, 'exit_tick': False, 'grace_exceeded': False}),
        ('nonzero_at_grace', [9, 9], [True, True], 2500000000, {'zero_requested': False, 'zero_target_published': False, 'exit_tick': True, 'grace_exceeded': True}),
    ]:
        scenario('shutdown_' + label, [{'op': 'shutdown', 'command': command, 'returned': returned, 'now': G + delta, 'stop_start': G}], [check(0, k, v) for k, v in expected.items()])
    binary = D / 'build/components_attempt01/entry_probe'
    paths = [contract, binary, Path(__file__).resolve()] + list((D / 'implementation/native').glob('*.hpp'))
    before = {str(p): pin(p) for p in paths}
    with (D / 'verification/entry_policy_requests_v1.jsonl').open('xb') as f:f.write(b''.join(enc(c['request']) for c in cases))
    result = subprocess.run([str(binary)], input=b''.join(enc(c['request']) for c in cases), capture_output=True, timeout=120)
    (D / 'verification/entry_policy_stdout_v1.jsonl').write_bytes(result.stdout)
    (D / 'verification/entry_policy_stderr_v1.log').write_bytes(result.stderr)
    outputs = [json.loads(s) for s in result.stdout.splitlines()]
    assert result.returncode == 0 and len(outputs) == len(cases)
    for c, output in zip(cases, outputs):
        passed = output['accepted'] == c['expected_accepted'] and output['physical_execute_release_enabled'] is False and output['physical_API_calls'] == 0
        for chk in c['checks']:
            try:
                actual = output['events'][chk['event']]
                for key in chk['path'].split('.'):actual = actual[key]
                expected = chk['value']
                if type(actual) is list and type(expected) is list and all(type(v) in (int, float) for v in expected):
                    good = len(actual) == len(expected) and all(abs(a - b) < 1e-8 for a, b in zip(actual, expected))
                else:good = type(actual) is type(expected) and actual == expected
            except (KeyError, IndexError, TypeError):good = False
            chk['passed'] = good;passed = passed and good
        c['output'] = output;c['passed'] = passed
    after = {p: pin(Path(p)) for p in before}
    record = {'schema': 'P1-owned-entry-policy-component/v1', 'passed': all(c['passed'] for c in cases) and before == after,
              'case_count': len(cases), 'failed_cases': [c['name'] for c in cases if not c['passed']], 'cases': cases,
              'input_sha256_before': before, 'input_sha256_after': after, 'synthetic_contexts_and_API_results_only': True,
              'actual_ROS_or_output_calls': 0, 'physical_execute_release_enabled': False, 'stage_qualified': False,
              'M4_qualified': False, 'research_conclusion': False}
    with (D / 'verification/entry_policy_cases_v1.json').open('xb') as f:f.write(enc(record))
    print(json.dumps({k: record[k] for k in ['passed', 'case_count', 'failed_cases']}))
    return 0 if record['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
