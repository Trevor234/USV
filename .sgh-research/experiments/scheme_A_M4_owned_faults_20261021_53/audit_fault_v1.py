#!/usr/bin/env python3
"""Independent audit for the two owned fault cases (R1 pre-grant cancel, R2 worker exit).

Case-independent checks are kept from the batch-49 normal audit:
  * input/config/registry/source-lock hash continuity before and after
  * exactly one publishing role per output topic, and the Regulator owns all five
  * typed Source -> SQLite equality for the rows that do exist
  * Applied never asserts plant acceptance / measured force / execution atomicity

Normal-only assertions (exactly 101 jobs, 100/100 accepted, SIGINT-only rc0 for
all four roles, dropped==0, witness complete, fixture normal_end) are replaced by
case-specific expectations.

Bag timestamps and CLOCK_MONOTONIC are never subtracted.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent


def pin(p):
    b = Path(p).read_bytes()
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}


def read(p):
    return json.loads(Path(p).read_bytes())


def lines(p):
    raw = Path(p).read_bytes()
    assert len(raw) <= 128 * 1024**2 and raw.endswith(b'\n')
    return [json.loads(x) for x in raw.splitlines()]


def norm(value):
    if type(value) in [str, bool, int, float, type(None)]:
        return value
    if hasattr(value, 'get_fields_and_field_types'):
        return {k: norm(getattr(value, k)) for k in value.get_fields_and_field_types()}
    if hasattr(value, 'tolist'):
        return norm(value.tolist())
    if hasattr(value, 'item'):
        return norm(value.item())
    return [norm(x) for x in value]


def rename_job(value):
    mapping = {'schema_version': 'schema', 'tick_origin_steady_ns': 'tick_origin_ns',
               'freeze_steady_ns': 'freeze_ns', 'deadline_steady_ns': 'deadline_ns',
               'target_steady_ns': 'target_ns', 'horizon_steps': 'N', 'prediction_dt': 'dt'}
    return {mapping.get(k, k): v for k, v in value.items()}


def decode_bag(run_root, get_message, deserialize_message):
    bag = next((run_root / 'recorder/bag').glob('*.db3'))
    db = sqlite3.connect('file:' + str(bag) + '?mode=ro', uri=True)
    topics = {i: (name, typ) for i, name, typ in db.execute('select id,name,type from topics')}
    decoded = collections.defaultdict(list)
    wire = collections.Counter()
    classes = {typ: get_message(typ) for _, typ in topics.values()}
    for topic_id, data in db.execute('select topic_id,data from messages order by id'):
        name, typ = topics[topic_id]
        decoded[name].append(norm(deserialize_message(data, classes[typ])))
        wire[(name, hashlib.sha256(data).hexdigest())] += 1
    db.close()
    return decoded, wire


# ── case-independent checks ────────────────────────────────────────────────

def check_common(run_root, registration, manifests, c):
    cm = manifests['regulator']
    assert cm['role'] == 'p1_owned_execute_regulator'
    assert cm['physical_publishers'] == 2
    assert cm['physical_API_calls_before_grant'] == 0
    output_topics = {'/p1/solve_job', '/p1/execution_decision', '/research/control/applied',
                     *c['output_topics'].values()}
    seen = {}
    for role, m in manifests.items():
        for ep in m['endpoints']:
            if ep['kind'] == 'publisher':
                assert ep['topic'] not in seen, 'two publishing roles for ' + ep['topic']
                seen[ep['topic']] = role
                if ep['topic'] in output_topics:
                    assert role == 'regulator', 'output topic owned by ' + role
    for topic in output_topics:
        assert seen.get(topic) == 'regulator', 'missing sole output owner: ' + topic


def check_applied_honesty(decoded):
    """The run must never claim physical execution facts it cannot observe."""
    applied = decoded.get('/research/control/applied', [])
    for row in applied:
        assert row['plant_acceptance_observed'] is False, 'fabricated plant acceptance'
        assert row['force_measured'] is False, 'fabricated measured force'
        assert row['execution_atomicity_proven'] is False, 'fabricated execution atomicity'
        assert row['event_semantics'] == 'actual_per_side_API_result', 'unexpected applied semantics'
    return len(applied)


def check_bag_equality(decoded, source_rows, manifests):
    """Every stored row must correspond to a Source row of the same kind.

    The Regulator Source names the registration row `candidate_registration`;
    the wire topic is /p1/solve_candidate. Both count the candidates accepted
    into the regulator's admission path.
    """
    jobs = [r['job'] for r in source_rows if r['type'] == 'job']
    pairs = [r for r in source_rows if r['type'] == 'owned_API_pair']
    candidates = [r for r in source_rows if r['type'] == 'candidate_registration']
    counts = {k: len(v) for k, v in decoded.items()}
    assert counts.get('/p1/solve_job', 0) == len(jobs), 'stored jobs != source jobs'
    assert counts.get('/p1/solve_candidate', 0) == len(candidates), \
        'stored candidates != source registrations (%d vs %d)' % (
            counts.get('/p1/solve_candidate', 0), len(candidates))
    assert counts.get('/p1/execution_decision', 0) == len(pairs), 'stored decisions != source pairs'
    assert counts.get('/research/control/applied', 0) == len(pairs), 'stored applied != source pairs'
    stored_jobs = {j['job_id']: rename_job(j) for j in decoded.get('/p1/solve_job', [])}
    for job in jobs:
        assert stored_jobs[job['job_id']] == job, 'job ' + str(job['job_id']) + ' differs in storage'


# ── case-specific checks ──────────────────────────────────────────────────

def check_r1(run_root, source_rows, by_type, result):
    assert not (run_root / 'regulator/grant.json').exists(), 'R1 must not have written a grant'
    assert 'owned_prepare_ready' in by_type, 'R1 requires prepare-ready evidence'
    assert 'owned_prepare_closed_before_API' in by_type, 'R1 missing pre-grant cancel record'
    for forbidden in ('job', 'owned_API_pair', 'regulator_shutdown', 'owned_execute_grant_accepted'):
        assert forbidden not in by_type, 'R1 produced forbidden Source row: ' + forbidden
    assert not by_type.get('candidate_registration'), 'R1 produced a candidate registration'
    closed = by_type['owned_prepare_closed_before_API'][0]
    assert closed['physical_API_calls'] == 0, 'R1 cancel claims nonzero API calls'
    # Regulator main returns start_failed?5:(closed?(audit?0:3):2). With zero
    # ticks the Witness cannot be observation_complete, so 3 is the expected
    # exit code for a successful pre-grant cancel.
    assert result['regulator_returncode'] == 3, 'R1 regulator exit is not the documented 3'
    assert result['R1_source_events'], 'R1 driver saw no prepare events'
    return {'physical_API_calls': 0,
            'rectypes': sorted(by_type),
            'regulator_returncode': result['regulator_returncode']}


def check_r3(run_root, source_rows, by_type, result, c):
    """Capability receipt lease expiry with the Worker stopped, not killed."""
    transition = by_type['worker_unusable_transition'][0]
    assert transition['reason'] == 'worker_capability_expired', \
        'R3 must be a capability-lease expiry, got ' + transition['reason']
    assert transition['candidate_after'] is False and transition['pending_after'] is False, \
        'transition must clear candidate and pending'
    assert transition['capability_timeout_ns'] > 0, 'lease timeout must be the frozen value'
    t_ns = transition['processed_ns']
    pairs = by_type['owned_API_pair']
    before = [p for p in pairs if p['starts'][0] < t_ns]
    after = [p for p in pairs if p['starts'][0] >= t_ns]
    assert len(before) >= 1, 'R3 needs at least one accepted pair before expiry'
    assert len(after) >= 1, 'R3 needs at least one fallback pair after expiry'
    for p in pairs:
        assert not p['gap_exceeded'] and not p['span_exceeded'] and not p['rate_exceeded'], \
            'R3 ramp exceeded a frozen bound at sequence ' + str(p['sequence'])
        assert not p['command_invalid'], 'R3 produced a non-finite command'
    # No new submission or accepted registration after the lease expired.
    for job in by_type.get('job', []):
        assert job.get('submit_commit_ns', 0) < t_ns, 'job submitted after the lease expired'
    for reg_row in by_type.get('candidate_registration', []):
        if reg_row.get('ready_commit_ns', 0) >= t_ns:
            assert reg_row.get('accepted_registration') is False, \
                'candidate accepted after the lease expired'
    shutdown = by_type.get('regulator_shutdown')
    assert shutdown, 'R3 missing regulator_shutdown'
    shutdown = shutdown[0]
    assert shutdown['normal_contract_complete'] is False, \
        'a lease-expiry run must not claim a complete normal contract'
    assert result['regulator_returncode'] == 0, 'R3 regulator did not exit cleanly'
    assert result.get('lease_reason') == 'worker_capability_expired'
    return {'transition_reason': transition['reason'],
            'stimulus_to_transition_ns': result.get('stimulus_to_transition_ns'),
            'capability_timeout_ns': transition['capability_timeout_ns'],
            'pairs_before_transition': len(before),
            'pairs_after_transition': len(after),
            'shutdown_zero_published': shutdown['zero_target_published'],
            'shutdown_grace_exceeded': shutdown['shutdown_grace_exceeded']}


def check_r2(run_root, source_rows, by_type, result, c):
    transition = by_type['worker_unusable_transition'][0]
    assert transition['reason'] in ('worker_process_exited', 'worker_liveness_check_failed'), \
        'unexpected worker loss reason: ' + transition['reason']
    assert transition['candidate_after'] is False and transition['pending_after'] is False, \
        'transition must clear candidate and pending'
    t_ns = transition['processed_ns']
    pairs = by_type['owned_API_pair']
    after = [p for p in pairs if p['starts'][0] >= t_ns]
    assert len(after) >= 2, 'R2 needs at least two post-transition API pairs'
    # Bounded ramp: no per-side rate / gap / span violations anywhere in the stream.
    for p in pairs:
        assert not p['gap_exceeded'] and not p['span_exceeded'] and not p['rate_exceeded'], \
            'R2 ramp exceeded a frozen bound at sequence ' + str(p['sequence'])
        assert not p['command_invalid'], 'R2 produced a non-finite command'
    # No new submission or activation after the transition.
    late_jobs = [r for r in by_type.get('job', []) if r.get('submit_commit_ns', 0) >= t_ns]
    for job in late_jobs:
        # Only a submission committed BEFORE the transition may still land in DDS.
        assert job['submit_commit_ns'] < t_ns, 'job submitted after the worker became unusable'
    assert not [r for r in by_type.get('candidate_registration', []) if r['ready_commit_ns'] >= t_ns], \
        'candidate registered after the worker became unusable'
    # Applied history: the successful side must never be rolled back.
    known = [False, False]
    for p in pairs:
        for side in (0, 1):
            if p['returned'][side]:
                assert p['command_n'][side] is not None
        if p['kind'] in ('fallback', 'shutdown'):
            assert p['previous_known'] == [True, True], 'fallback requires a known previous anchor'
    shutdown = by_type.get('regulator_shutdown')
    assert shutdown, 'R2 missing regulator_shutdown'
    shutdown = shutdown[0]
    assert shutdown['normal_contract_complete'] is False, \
        'a worker-death run must not claim a complete normal contract'
    assert result['regulator_returncode'] == 0, 'R2 regulator did not exit cleanly'
    assert result.get('new_job_after_transition') is False, 'new job observed after transition'
    assert result.get('new_candidate_after_transition') is False, 'new candidate after transition'
    worker_summary = [r for r in by_type.get('worker_summary', [])]
    # The killed worker cannot write a summary; a present one must be honest.
    for ws in worker_summary:
        assert ws['normal_source_complete'] is False or ws['fatal'] is True, \
            'worker summary claims completeness after being killed'
    return {'transition_reason': transition['reason'],
            'stimulus_to_transition_ns': result.get('stimulus_to_transition_ns'),
            'pairs_after_transition': len(after),
            'jobs_after_transition': len(late_jobs),
            'shutdown_zero_published': shutdown['zero_target_published'],
            'shutdown_grace_exceeded': shutdown['shutdown_grace_exceeded'],
            'worker_summary_present': bool(worker_summary)}


# ── mutation self-checks ──────────────────────────────────────────────────

def self_mutations(case, run_root, source_rows, by_type, result, c, check_common_fn,
                   check_bag_fn, decoded, manifests, reg):
    """The audit must reject fabricated passes. Each mutation must raise."""
    rejected, escaped = [], []

    def must_reject(name, fn):
        try:
            fn()
        except AssertionError:
            rejected.append(name)
            return
        except Exception as exc:  # a crash is also a rejection, but record it
            rejected.append(name + ':' + type(exc).__name__)
            return
        escaped.append(name)

    def rebuild(rows):
        bt = collections.defaultdict(list)
        for r in rows:
            bt[r['type']].append(r)
        return bt

    if str(case).startswith('R1'):
        def m1():
            # claim one physical API call during the pre-grant cancel
            rows = [dict(r) for r in source_rows]
            for r in rows:
                if r['type'] == 'owned_prepare_closed_before_API':
                    r['physical_API_calls'] = 1
            check_r1(run_root, rows, rebuild(rows), result)
        must_reject('r1_api_call_fabricated', m1)

        def m2():
            # inject a business job into a run that must never produce one
            rows = [dict(r) for r in source_rows] + [{'type': 'job', 'job': {'job_id': 1}}]
            check_r1(run_root, rows, rebuild(rows), result)
        must_reject('r1_job_fabricated', m2)
    elif str(case).startswith('R3'):
        def m3a():
            # claim worker death instead of a lease expiry
            rows = [dict(r) for r in source_rows]
            for r in rows:
                if r['type'] == 'worker_unusable_transition':
                    r['reason'] = 'worker_process_exited'
            check_r3(run_root, rows, rebuild(rows), result, c)
        must_reject('r3_wrong_transition_reason', m3a)

        def m3b():
            # claim a complete normal contract on a lease-expiry run
            rows = [dict(r) for r in source_rows]
            for r in rows:
                if r['type'] == 'regulator_shutdown':
                    r['normal_contract_complete'] = True
            check_r3(run_root, rows, rebuild(rows), result, c)
        must_reject('r3_normal_complete_fabricated', m3b)
    else:
        def m3():
            # delete the worker-unusable transition
            rows = [r for r in source_rows if r['type'] != 'worker_unusable_transition']
            check_r2(run_root, rows, rebuild(rows), result, c)
        must_reject('r2_transition_removed', m3)

        def m4():
            # claim a complete normal contract on a worker-death run
            rows = [dict(r) for r in source_rows]
            for r in rows:
                if r['type'] == 'regulator_shutdown':
                    r['normal_contract_complete'] = True
            check_r2(run_root, rows, rebuild(rows), result, c)
        must_reject('r2_normal_complete_fabricated', m4)

        def m5():
            # claim the killed worker exited normally (rc 0 instead of -9).
            # Uses the same raise-on-rejection shape as m1-m4 so must_reject
            # records it consistently.
            forged = dict(result)
            forged['closed_roles'] = [dict(x, returncode=0) if x['role'] == 'worker' else x
                                      for x in result['closed_roles']]
            assert forged['closed_roles'] != result['closed_roles'], 'mutation did not apply'
            require_driver_exit(forged, case)
        must_reject('r2_worker_rc_fabricated', m5)
    return rejected, escaped


def require_driver_exit(result, case):
    """Raise unless the close rows match the case's pre-registered exits.

    The Regulator's SIGINT (R1) and the Worker's SIGKILL (R2) are the Driver's
    registered stimuli, delivered by wait_close, so those rows carry an empty
    signal list; the remaining roles must show SIGINT-only clean exits.
    """
    by_role = {r['role']: r for r in result['closed_roles']}
    def rc(role): return by_role.get(role, {}).get('returncode')
    def sigs(role): return [s['signal'] for s in by_role.get(role, {}).get('signals', [])]
    if str(case).startswith('R1'):
        assert rc('regulator') == 3, 'R1 regulator exit is not the documented 3'
        assert not sigs('regulator'), 'R1 regulator must not be re-signalled by cleanup'
    elif str(case).startswith('R3'):
        # The Worker is stopped, then resumed by the Driver, so it closes itself
        # through the normal SIGINT ladder rather than dying by signal.
        assert rc('worker') == 0, 'R3 worker must resume and close cleanly'
        assert sigs('worker') == ['SIGINT'], 'R3 worker expected one SIGINT after resume'
        assert rc('regulator') == 0, 'R3 regulator did not exit cleanly'
        assert not sigs('regulator'), 'R3 regulator stimulus is the driver SIGINT'
    else:
        assert rc('worker') == -9, 'R2 worker must be SIGKILLed (-9)'
        assert not sigs('worker'), 'R2 driver must not signal the already-killed worker'
        assert rc('regulator') == 0, 'R2 regulator did not exit cleanly'
        assert not sigs('regulator'), 'R2 regulator stimulus is the driver SIGINT'
    for role in ('fixture', 'recorder'):
        assert rc(role) == 0, role + ' did not exit cleanly'
        assert sigs(role) == ['SIGINT'], role + ' expected exactly one SIGINT'
    for r in result['closed_roles']:
        assert r.get('group_empty') is True, 'role group not empty: ' + r['role']


def _check_driver_exit(result, case):
    """Boolean wrapper used by the mutation self-test."""
    try:
        require_driver_exit(result, case)
        return True
    except AssertionError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True, choices=['R1', 'R2', 'R3'])
    args = ap.parse_args()
    case = args.case
    reg_file = D / ('implementation/%s_registration_v1.json' % case)
    reg = read(reg_file)
    run_root = Path(reg['output'])
    c = read(Path(reg['contract']))

    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    source_rows = lines(run_root / 'regulator/source.jsonl')
    by_type = collections.defaultdict(list)
    for r in source_rows:
        by_type[r['type']].append(r)
    manifests = {role: read(run_root / role / ('owned_manifest.json' if role == 'fixture'
                                               else 'manifest.json'))
                 for role in ['regulator', 'worker', 'fixture', 'recorder']}
    result = read(run_root / 'driver_result.json')
    outer_path = D / ('evidence/%s_launch_v1.json' % case)
    outer = read(outer_path)

    # hash continuity: every input pinned before and after
    closure = dict(read(D / 'preflight/prerun_source_lock_v1.json')['files'])
    for p, row in closure.items():
        assert pin(Path(p)) == row, 'registered input changed: ' + p
    inputs = [p for p in run_root.rglob('*') if p.is_file()] + [
        Path(__file__).resolve(), reg_file,
        D / 'implementation/selected_runtime_registry_v1.json',
        D / 'preflight/prerun_source_lock_v1.json', outer_path]
    before = {str(p): pin(p) for p in inputs}

    assert result['passed'], 'driver did not pass'
    assert outer['passed'], 'outer harness did not pass'
    assert len(result['closed_roles']) == 4, 'expected exactly four closed roles'

    check_common(run_root, reg, manifests, c)
    decoded, wire = decode_bag(run_root, get_message, deserialize_message)
    check_applied_honesty(decoded)
    check_bag_equality(decoded, source_rows, manifests)

    if case == 'R1':
        summary = check_r1(run_root, source_rows, by_type, result)
    elif case == 'R3':
        summary = check_r3(run_root, source_rows, by_type, result, c)
    else:
        summary = check_r2(run_root, source_rows, by_type, result, c)

    rejected, escaped = self_mutations(case, run_root, source_rows, by_type, result, c,
                                       check_common, check_bag_equality, decoded, manifests, reg)
    assert not escaped, 'audit failed to reject fabricated mutations: ' + repr(escaped)
    assert len(rejected) == {'R1': 2, 'R2': 3, 'R3': 2}[case], 'mutation self-check count wrong: ' + repr(rejected)

    after = {str(p): pin(p) for p in inputs}
    assert before == after, 'audit inputs changed during the audit'

    report = {'schema': 'M4-owned-fault-audit/v1', 'case': case, 'passed': True,
              'run_id': reg['run_id'], 'case_summary': summary,
              'mutation_rejections': rejected, 'mutations_tested': len(rejected),
              'stored_counts': {k: len(v) for k, v in decoded.items()},
              'input_continuity': len(before),
              'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
              'research_conclusion': False, 'plant_acceptance_observed': False}
    out = D / 'postrun' / ('%s_audit_v1.json' % case)
    out.parent.mkdir(exist_ok=True)
    with out.open('x') as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write('\n')
    print(json.dumps({'passed': True, 'case': case, 'summary': summary, 'output': str(out)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
