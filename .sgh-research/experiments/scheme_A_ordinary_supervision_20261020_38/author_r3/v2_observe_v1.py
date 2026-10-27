"""Bounded V2 stimulus and observations; no failure reason is synthesized."""
from pathlib import Path
import hashlib
import json
import time


def need(value, reason):
    if not value:
        raise ValueError(reason)



def actual_cause(transition, source):
    reason = transition['reason']
    if reason in ['active_watchdog', 'worker_capability_expired']:
        return reason
    table = {'legacy_ready_invalidated:worker_unusable:active_watchdog': 'active_watchdog',
             'legacy_ready_invalidated:worker_unusable:worker_capability_expired': 'worker_capability_expired'}
    need(reason in table, 'unexpected V2 terminal causal chain')
    cause = table[reason]
    linked = [r for r in source if r.get('type') == 'legacy_ready_invalidated'
              and r.get('reason') == 'worker_unusable:' + cause and r.get('check_ns') == transition['check_ns']]
    need(len(linked) == 1 and linked[0]['terminal'] is True and linked[0]['measurement_eligible'] is False,
         'V2 causal readiness invalidation link missing')
    return cause


def observe(case, root, *, spin, bound, identity, boot, driver_sha, owner_manifest_sha,
            create_only_json, overall_deadline_ns):
    root = Path(root)
    start = time.monotonic_ns()
    deadline = min(start + 8_000_000_000, overall_deadline_ns - 15_000_000_000)
    def rows(relative):
        data = (root / relative).read_bytes()
        return [json.loads(line) for line in data.splitlines(keepends=True) if line.endswith(b'\n')]
    def wait(predicate, label):
        while time.monotonic_ns() < deadline:
            bound()
            result = predicate()
            if result:
                return result
            spin(.01)
        raise RuntimeError('V2 finite observation deadline: ' + label)
    def first_unusable():
        found = [r for r in rows('observer/source.jsonl') if r.get('type') == 'worker_unusable_transition']
        return found[0] if found else None
    def prefix():
        source = rows('observer/source.jsonl')
        accepted = {r['sequence']: r for r in source if r.get('type') == 'decision' and r['accepted']}
        for callback in source:
            if callback.get('type') == 'controlled_phase_callback' and callback.get('accepted') is True:
                phase = callback['phase']
                if phase['decision_sequence'] not in accepted:
                    continue
                emitted = [r for r in rows('publisher/controlled_source.jsonl')
                           if r.get('type') == 'controlled_Applied_emitted' and r['applied_sequence'] == phase['applied_sequence']]
                if emitted:
                    return {'decision': accepted[phase['decision_sequence']], 'phase_callback': callback, 'Applied': emitted[0]}
        return None
    def gate(action):
        path = root / ('c38_' + action + '_request.json')
        command = {'schema': 'p1-C3.8-applied-gate-v1', 'action': action,
                   'run_id': json.loads((root / 'expected_witness_header.json').read_bytes())['run_id'],
                   'boot_id': boot, 'driver_pid': identity['pid'], 'driver_start_ticks': identity['start_ticks'],
                   'driver_tool_sha256': driver_sha, 'owner_manifest_sha256': owner_manifest_sha,
                   'issued_ns': time.monotonic_ns(), 'seq': 1 if action == 'pause' else 2, 'stage_qualified': False}
        create_only_json(path, command)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        target = 'diagnostic_c38_gate_paused' if action == 'pause' else 'diagnostic_c38_gate_resumed'
        def received():
            found = [r for r in rows('observer/source.jsonl') if r.get('type') == target]
            if not found:
                return None
            row = found[-1]
            need(row['request_sha256'] == digest and row['gate_interface'] == 'worker', 'V2 gate actual ACK binding')
            need(row['gate']['run_id'] == command['run_id'] and row['gate']['boot_id'] == boot
                 and row['gate']['driver_pid'] == identity['pid']
                 and row['gate']['driver_start_ticks'] == identity['start_ticks']
                 and row['group_registered'] is (action == 'resume'), 'V2 gate actual state')
            return row
        return wait(received, target)
    paused = resumed = barrier = prefix_observed = None
    if case == 'lease':
        prefix_observed = wait(prefix, 'authenticated accepted prefix')
        create_only_json(root / 'V2_prefix_observation.json', prefix_observed)
        paused = gate('pause')
        wait(lambda: time.monotonic_ns() >= paused['gate']['paused_ns'] + 900_000_000, '900ms callback pause')
        transition = wait(first_unusable, 'receipt lease expiration')
        try:
            need(actual_cause(transition, rows('observer/source.jsonl')) == 'worker_capability_expired', 'V2 first cause differs from receipt lease')
        finally:
            resumed = gate('resume')
        wait(lambda: len([r for r in rows('observer/source.jsonl') if r.get('type') == 'capability_admission'
                          and r['validation_commit_ns'] >= resumed['gate']['resumed_ns'] and r['identity_valid']
                          and r['valid'] and not r['renewed'] and r['terminal_run']]) >= 2,
             'real valid-identity callbacks cannot revive terminal run')
    elif case == 'active':
        barrier = wait(lambda: next((r for r in rows('worker/source.jsonl')
                                    if r.get('type') == 'diagnostic_v2_pre_native_enter'), None), 'one-shot work barrier')
        transition = wait(first_unusable, 'active watchdog')
        need(actual_cause(transition, rows('observer/source.jsonl')) == 'active_watchdog', 'V2 first cause differs from active watchdog')
        released = wait(lambda: next((r for r in rows('worker/source.jsonl')
                                     if r.get('type') == 'diagnostic_v2_pre_native_release'), None), 'work barrier release')
        wait(lambda: len([r for r in rows('observer/source.jsonl') if r.get('type') == 'capability_admission'
                          and r['validation_commit_ns'] > released['released_ns'] and r['valid']
                          and not r['renewed'] and r['terminal_run']]) >= 2, 'post-barrier same-run terminal capability')
        prefix_observed = prefix()
    else:
        raise ValueError('V2 unknown case')
    source = rows('observer/source.jsonl')
    need(not any(r.get('type') == 'diagnostic_c38_gate_timeout' for r in source), 'unexpected gate timeout')
    need(all(not r['renewed'] for r in source if r.get('type') == 'capability_admission'
             and r['validation_commit_ns'] > transition['check_ns']), 'capability revival after terminal')
    report = {'schema': 'V2-actual-stimulus-observation/v1', 'case': case, 'started_ns': start,
              'finished_ns': time.monotonic_ns(), 'deadline_ns': deadline, 'first_transition': transition,
              'first_cause': actual_cause(transition,source), 'raw_terminal_reason':transition['reason'],
              'paused': paused, 'resumed': resumed, 'barrier_enter': barrier,
              'prefix_observed': prefix_observed is not None, 'native_C_hang_proven': False,
              'source_packet_freshness_proven': False, 'normal_business_qualified': False,
              'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False}
    create_only_json(root / 'V2_observation.json', report)
    return report
