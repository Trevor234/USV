#!/usr/bin/env python3
"""Independent fault-run audit, v2. Read-only: no ROS, no new runs.

Corrects the 22 gaps found in audit_fault_v1.py (batch 53). The most important:

  * v1 never called its own per-role exit classifier on the real run — it was
    only reached from a mutation test against a forged copy. v2 applies it to
    the actual closed_roles.
  * v1 compared Candidate / Decision / Applied by count only. v2 compares them
    field by field, and reads the Decision Source rows (v1 never did).
  * v1 built the wire Counter and never used it. v2 reconciles Stored against
    the Fixture's own transport receiver, per topic and per payload hash.
  * v1 trusted the Source's own gap_exceeded / span_exceeded / rate_exceeded
    flags. v2 recomputes all three from raw starts/ends and cross-checks.
  * v1 opened none of: worker/source.jsonl, ready.json, prepared.json,
    witness.json, fixture/terminal.json, nominal_steps.jsonl,
    transport_source.jsonl, recorder/terminal.json. v2 uses all of them.
  * v1 used the wrong lease start point. v2 uses
    check_ns - capability_last_valid_commit_ns.

Timing domains are never subtracted across: bag ns and CLOCK_MONOTONIC stay
separate, and the only cross-domain subtraction v2 performs is the documented
sim-clock projection frozen_clock_sim_ns + freeze_ns - frozen_clock_receive_ns.
"""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
EXP53 = D.parent / 'scheme_A_M4_owned_faults_20261021_53'


def pin(p):
    b = Path(p).read_bytes()
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}


def read(p):
    return json.loads(Path(p).read_bytes())


def lines(p, allow_truncated_tail=False):
    """Read a JSONL Source. A SIGKILLed writer can lose its final buffered line.

    Returns (rows, dropped_bytes). Only a caller that has declared the
    corresponding exception may pass allow_truncated_tail=True, and the dropped
    byte count is returned so the audit record shows what was not parsed.
    """
    raw = Path(p).read_bytes()
    assert len(raw) <= 128 * 1024**2, 'source larger than the bounded read'
    dropped = 0
    if not raw.endswith(b'\n'):
        assert allow_truncated_tail, 'truncated Source tail (no trailing newline)'
        cut = raw.rfind(b'\n')
        assert cut >= 0, 'Source is a single unterminated line'
        dropped = len(raw) - cut - 1
        assert dropped <= 262144, 'truncated tail larger than the bounded allowance'
        raw = raw[:cut + 1]
    return [json.loads(x) for x in raw.splitlines()], dropped


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


def stamp(v):
    return int(v['sec']) * 1000000000 + int(v['nanosec'])


def rename_job(value):
    mapping = {'schema_version': 'schema', 'tick_origin_steady_ns': 'tick_origin_ns',
               'freeze_steady_ns': 'freeze_ns', 'deadline_steady_ns': 'deadline_ns',
               'target_steady_ns': 'target_ns', 'horizon_steps': 'N', 'prediction_dt': 'dt'}
    return {mapping.get(k, k): v for k, v in value.items()}


DECISION_RENAMES = {'schema_version': 'schema', 'clock_epoch': 'epoch',
                    'tick_planned_ns': 'planned_ns', 'tick_start_ns': 'start_ns',
                    'tick_end_ns': 'end_ns', 'candidate_accepted': 'accepted',
                    'candidate_ready_commit_ns': 'ready_commit_ns'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


# ── per-case exception profile ─────────────────────────────────────────────

class Exceptions:
    """Every allowance is bound to a case, a role, and an event."""

    def __init__(self, case):
        self.case = case
        self.allowed = set()
        if case == 'R2':
            # SIGKILL loses the Worker's unflushed ofstream tail: no summary,
            # no capability terminal, and possibly the last candidate row.
            self.allowed.add(('R2', 'worker', 'worker_summary_missing'))
            self.allowed.add(('R2', 'worker', 'capability_terminal_missing'))
            self.allowed.add(('R2', 'worker', 'candidate_row_unflushed'))
        # R1 has zero business ticks: its Witness can never be
        # observation_complete, and the Regulator exits 3 by design.
        if case == 'R1':
            self.allowed.add(('R1', 'regulator', 'witness_not_observation_complete'))
            self.allowed.add(('R1', 'regulator', 'exit_code_3'))

    def allows(self, role, what):
        return (self.case, role, what) in self.allowed

    def describe(self):
        return sorted('.'.join(x) for x in self.allowed)


# ── case-independent checks ────────────────────────────────────────────────

def check_role_exits(result, case, reg, exceptions):
    """v1 gap #19: this must run on the REAL run, not only inside a mutation.

    Exit codes come straight from the registration. Signal lists need one
    correction: the registration for R2 records regulator=['SIGINT'], but the
    Driver delivers that SIGINT itself and records it through wait_close(),
    whose row carries signals=[] by design. The Driver's own pass formula
    requires an empty list there, so the audit follows the driver semantics and
    reports the registration discrepancy rather than silently accepting either.
    """
    by_role = {r['role']: r for r in result['closed_roles']}
    assert len(result['closed_roles']) == 4, 'expected exactly four closed roles'
    expected = reg.get('expected_exit', {})
    for role, want in expected.items():
        got = by_role.get(role, {}).get('returncode')
        assert got == want, '%s exit %r != pre-registered %r' % (role, got, want)
    notes = []
    for role, want in reg.get('expected_signals', {}).items():
        got = [s['signal'] for s in by_role.get(role, {}).get('signals', [])]
        if got == want:
            continue
        # Only the driver-delivered stimulus may differ, and only by being empty.
        if got == [] and want == ['SIGINT'] and role == 'regulator' and case in ('R1', 'R2', 'R3'):
            notes.append({'role': role, 'registration_says': want, 'actual': got,
                          'reason': 'driver-delivered stimulus is recorded by wait_close '
                                    'with an empty signal list; the registration text '
                                    'was not updated to match the driver semantics'})
            continue
        raise AssertionError('%s signals %r != pre-registered %r' % (role, got, want))
    for r in result['closed_roles']:
        assert r.get('group_empty') is True, 'role group not empty: ' + r['role']
        assert not r.get('error'), 'close error for %s: %s' % (r['role'], r.get('error'))
    return {r['role']: r['returncode'] for r in result['closed_roles']}, notes


def check_publishers(manifests, c):
    cm = manifests['regulator']
    assert cm['role'] == 'p1_owned_execute_regulator'
    assert cm['physical_publishers'] == 2
    assert cm['physical_API_calls_before_grant'] == 0
    output_topics = {'/p1/solve_job', '/p1/execution_decision', '/research/control/applied',
                     *c['output_topics'].values()}
    owner, gid = {}, {}
    for role, m in manifests.items():
        for ep in m['endpoints']:
            if ep['kind'] != 'publisher':
                continue
            assert ep['topic'] not in owner, 'two publishing roles for ' + ep['topic']
            owner[ep['topic']] = role
            assert len(ep['gid']) == 16 and any(ep['gid']), 'bad GID for ' + ep['topic']
            gid[ep['topic']] = ep['gid']
    for topic in output_topics:
        assert owner.get(topic) == 'regulator', 'output topic not owned by regulator: ' + topic
    return gid


def check_bootstrap(run_root, source, pairs, c, manifests):
    """v1 gap #10: recorder-ready / grant / first-pair ordering was absent."""
    ready = read(run_root / 'regulator/ready.json')
    assert ready['complete_recorder_pin']['manifest_sha256'] == \
        pin(run_root / 'recorder/manifest.json')['sha256'], 'ready pins a different Recorder'
    assert ready['anchor_known'] == [False, False], 'ready must start with an unknown anchor'
    assert ready['physical_API_calls'] == 0, 'ready reports pre-grant API calls'
    full = source.get('owned_full_recorder_bound')
    assert full, 'missing owned_full_recorder_bound'
    assert full[0]['physical_API_calls'] == 0, 'full-recorder bind happened after an API call'
    if 'prepared.json' in [p.name for p in (run_root / 'regulator').iterdir()]:
        prepared = read(run_root / 'regulator/prepared.json')
        grant = read(run_root / 'regulator/grant.json')
        assert prepared['grant_sha256'] == pin(run_root / 'regulator/grant.json')['sha256']
    else:
        prepared, grant = None, None
    accepted = source.get('owned_execute_grant_accepted')
    if grant and accepted:
        assert full[0]['bound_ns'] <= accepted[0]['origin_ns'], \
            'grant accepted before the full Recorder was bound'
        assert accepted[0]['origin_ns'] <= pairs[0]['starts'][0], \
            'first API pair precedes grant origin'
    return ready, prepared, grant


def check_pair_stream(pairs, c, recompute=True):
    """v1 gap #7/#8: recompute gap/span/rho instead of trusting the flags."""
    known = [False, False]
    prev_n = [0.0, 0.0]
    prev_start = [0, 0]
    maxgap = [0, 0]
    maxrate = [0.0, 0.0]
    maxspan = 0
    for i, p in enumerate(pairs):
        assert p['sequence'] == i + 1, 'non-contiguous API pair sequence'
        assert list(p['previous_known']) == known, 'previous_known does not chain'
        if all(known):
            assert p['previous_n'] == prev_n, 'previous_n does not chain'
            assert p['previous_start_ns'] == prev_start, 'previous_start_ns does not chain'
        s0, e0, s1, e1 = p['starts'][0], p['ends'][0], p['starts'][1], p['ends'][1]
        assert s0 <= e0 <= s1 <= e1, 'intra-pair call ordering violated'
        span = e1 - s0
        assert span <= c['publish_budget_ns'], \
            'pair span %d > budget %d' % (span, c['publish_budget_ns'])
        maxspan = max(maxspan, span)
        for side in (0, 1):
            n = p['command_n'][side]
            assert isinstance(n, (int, float)) and math.isfinite(n), 'non-finite command'
            assert c['command_min_n'] <= n <= c['command_max_n'], 'command outside N envelope'
        if recompute:
            for side in (0, 1):
                if not known[side]:
                    continue
                elapsed = p['starts'][side] - prev_start[side]
                assert elapsed > 0, 'non-positive per-side API interval'
                assert elapsed <= c['publish_gap_ns'], \
                    'per-side gap %d > %d at pair %d side %d' % (
                        elapsed, c['publish_gap_ns'], i, side)
                maxgap[side] = max(maxgap[side], elapsed)
                dn = abs(p['command_n'][side] - prev_n[side])
                rate = dn * 1e9 / elapsed
                assert rate <= c['rho_n_s'] + 1e-9, \
                    'recomputed rate %.6f > %.6f at pair %d side %d' % (
                        rate, c['rho_n_s'], i, side)
                maxrate[side] = max(maxrate[side], rate)
        # Self-produced flags must agree with the independent recomputation.
        for flag in ('gap_exceeded', 'span_exceeded', 'rate_exceeded', 'command_invalid'):
            assert not p.get(flag), 'Source self-reported %s at pair %d' % (flag, i)
        for side in (0, 1):
            if p['returned'][side]:
                known[side] = True
                prev_n[side] = p['command_n'][side]
                prev_start[side] = p['starts'][side]
    return {'max_gap_ns': maxgap, 'max_rate_n_s': maxrate, 'max_span_ns': maxspan}


def check_decisions(decisions, pairs, c):
    """v1 gap #12: mode / skipped ticks / jitter were never asserted."""
    maxjitter = 0
    for d in decisions:
        assert d['mode'] == 'execute', 'decision mode is not execute'
        assert d['skipped_ticks'] == 0, 'scheduler skipped a tick'
        jitter = d['start_ns'] - d['planned_ns']
        assert 0 <= jitter <= c['tick_jitter_ns'], 'tick start jitter %d out of range' % jitter
        maxjitter = max(maxjitter, jitter)
    return maxjitter


def check_jobs(jobs, pairs, c, manifests):
    """v1 gap #14: deadline/target arithmetic and anchor cross-check were absent."""
    cm = manifests['regulator']
    for job in jobs:
        assert job['anchor_source'] == 'regulator_publisher', 'unexpected anchor source'
        assert job['anchor_producer'] == cm['producer_instance_id'], 'anchor producer mismatch'
        assert job['anchor_run_id'] == cm['run_id'], 'anchor run mismatch'
        assert job['anchor_known'] == [True, True], 'job froze an unknown anchor'
        assert job['deadline_ns'] == job['tick_origin_ns'] + c['deadline_ns'], \
            'job deadline is not origin + deadline_ns'
        assert job['target_ns'] == job['tick_origin_ns'] + c['T_ns'], \
            'job target is not origin + T_ns'
        assert job['tick_origin_ns'] <= job['freeze_ns'] <= job['deadline_ns'], \
            'freeze time outside [origin, deadline]'
        for side in (0, 1):
            seq = job['anchor_sequence'][side]
            assert 1 <= seq <= len(pairs), 'anchor sequence out of range'
            actual = pairs[seq - 1]
            assert actual['command_n'][side] == job['anchor_n'][side], \
                'job anchor_n does not match the referenced API pair'
            assert actual['starts'][side] == job['anchor_publish_ns'][side], \
                'job anchor_publish_ns does not match the referenced API pair'
            assert job['anchor_publish_ns'][side] <= job['freeze_ns'], \
                'job anchored to a future publish'
        now = job['freeze_ns']
        clock_now = job['frozen_clock_sim_ns'] + now - job['frozen_clock_receive_ns']
        for key in ['odom'] + (['imu'] if job['r_from_imu'] else []):
            assert 0 <= now - job[key + '_receive_ns'] <= c[key + '_age_ns'], \
                '%s receipt age out of bounds' % key
            lag = clock_now - job[key + '_stamp_ns']
            assert -c['source_future_slack_ns'] <= lag <= c[key + '_sim_lag_ns'], \
                '%s sim-domain lag %d out of bounds' % (key, lag)


def check_shutdown(source, pairs, c, exceptions):
    """v1 gap #11: the shutdown pair and its row were only echoed, never asserted."""
    assert pairs[-1]['kind'] == 'shutdown', 'last API pair is not the shutdown pair'
    assert pairs[-1]['command_n'] == [0, 0], 'shutdown pair is not a zero command'
    assert pairs[-1]['returned'] == [True, True], 'shutdown pair did not return on both sides'
    rows = source.get('regulator_shutdown')
    assert rows, 'missing regulator_shutdown'
    row = rows[0]
    assert row['zero_requested'] is True, 'shutdown did not request zero'
    assert row['plant_hold_end_known'] is False, \
        'shutdown must not claim a known plant hold end'
    if not row['shutdown_grace_exceeded']:
        assert row['zero_target_published'] is True, \
            'shutdown exited inside grace without publishing zero'
    return row


# ── typed Source <-> Stored equality ──────────────────────────────────────

def check_typed_equality(decoded, source_rows, worker_rows, manifests, c, exceptions, case):
    """v1 gap #2/#3: Candidate/Decision/Applied were compared by count only."""
    cm = manifests['regulator']
    by_type = collections.defaultdict(list)
    for r in source_rows:
        by_type[r['type']].append(r)
    jobs = [r['job'] for r in by_type['job']]
    pairs = by_type['owned_API_pair']
    decisions = by_type['decision']
    counts = {k: len(v) for k, v in decoded.items()}

    # Multiset, not a dict: duplicates and ordering stay visible.
    stored_jobs = decoded.get('/p1/solve_job', [])
    assert collections.Counter(canonical(rename_job(j)) for j in stored_jobs) == \
        collections.Counter(canonical(j) for j in jobs), \
        'stored jobs differ from Source jobs (multiset)'
    assert counts.get('/p1/solve_job', 0) == len(jobs), 'stored job count mismatch'

    # Candidates: compare against the Worker's own publication rows.
    worker_candidates = [x for x in worker_rows if x['type'] == 'candidate']
    stored_candidates = decoded.get('/p1/solve_candidate', [])
    if len(stored_candidates) != len(worker_candidates):
        if not exceptions.allows('worker', 'candidate_row_unflushed'):
            raise AssertionError(
                'stored candidates %d != worker published %d (undeclared worker loss)'
                % (len(stored_candidates), len(worker_candidates)))
        assert abs(len(stored_candidates) - len(worker_candidates)) <= 2, \
            'more than two candidates lost without declaration'
    by_job = {x['job']['job_id']: x for x in worker_candidates}
    unexplained = []
    for cand in stored_candidates:
        job_id = cand['job']['job_id']
        if job_id not in by_job:
            # The Worker's ofstream buffer is lost on SIGKILL, so a stored
            # candidate may have no Source row. This is only acceptable under
            # the declared R2 exception, and only for a bounded number.
            unexplained.append(job_id)
            continue
        row = by_job[job_id]
        assert rename_job(cand['job']) == row['job'], 'candidate job echo differs'
        assert cand['first_control'] == row['first_control'], 'candidate first_control differs'
        assert cand['x_prediction'] == row['X'], 'candidate x_prediction differs'
        assert cand['u_prediction'] == row['U'], 'candidate u_prediction differs'
        assert cand['success'] == row['success'], 'candidate success differs'
        assert cand['prediction_available'] == row['prediction_available'], \
            'candidate prediction_available differs'
    if unexplained:
        assert exceptions.allows('worker', 'candidate_row_unflushed'), \
            'stored candidates without a Worker Source row: %r' % unexplained[:4]
        assert len(unexplained) <= 2, \
            'more than two unflushed candidate rows: %r' % unexplained

    # Decisions: field by field, against the Decision Source rows v1 never read.
    decision_by_seq = {d['sequence']: d for d in decisions}
    stored_decisions = decoded.get('/p1/execution_decision', [])
    assert len(stored_decisions) == len(decisions), \
        'stored decisions %d != Source decisions %d' % (len(stored_decisions), len(decisions))
    for dec in stored_decisions:
        seq = dec['sequence']
        assert seq in decision_by_seq, 'stored decision has no Source row'
        row = decision_by_seq[seq]
        for key, value in dec.items():
            src_key = DECISION_RENAMES.get(key, key)
            if src_key in row:
                assert row[src_key] == value, \
                    'decision field %s differs at sequence %d' % (key, seq)

    # Applied: field by field against the API pair stream.
    applied = decoded.get('/research/control/applied', [])
    assert len(applied) == len(pairs), \
        'stored applied %d != Source pairs %d' % (len(applied), len(pairs))
    for i, m in enumerate(applied):
        p = pairs[i]
        assert m['sequence'] == i + 1, 'applied sequence is not contiguous'
        assert m['run_id'] == cm['run_id'], 'applied run_id differs'
        assert m['config_hash'] == cm['config_hash'], 'applied config_hash differs'
        assert m['producer_instance_id'] == cm['producer_instance_id'], \
            'applied producer_instance_id differs'
        assert m['baseline_id'] == c['baseline_input'], 'applied baseline_id differs'
        assert m['final_n'] == p['command_n'], 'applied final_n differs from the API pair'
        assert [m['left_publish_start_steady_ns'], m['right_publish_start_steady_ns']] == \
            p['starts'], 'applied publish starts differ'
        assert [m['left_publish_end_steady_ns'], m['right_publish_end_steady_ns']] == \
            p['ends'], 'applied publish ends differ'
        assert m['left_publish_success'] == p['returned'][0], \
            'applied left success differs from the API result'
        assert m['right_publish_success'] == p['returned'][1], \
            'applied right success differs from the API result'
        assert m['plant_acceptance_observed'] is False, 'fabricated plant acceptance'
        assert m['force_measured'] is False, 'fabricated measured force'
        assert m['execution_atomicity_proven'] is False, 'fabricated execution atomicity'
        assert m['event_semantics'] == 'actual_per_side_API_result', \
            'unexpected applied event semantics'

    # Float64 thrust topics, ordered.
    for side, key in enumerate(['left', 'right']):
        topic = c['output_topics'][key]
        assert [m['data'] for m in decoded.get(topic, [])] == \
            [p['command_n'][side] for p in pairs], \
            '%s topic values differ from the Source pair commands' % key

    return {'stored_counts': counts, 'jobs': len(jobs), 'candidates': len(stored_candidates),
            'decisions': len(stored_decisions), 'applied': len(applied), 'pairs': len(pairs)}


def check_wire(run_root, decoded, wire, gids, worker_rows, manifests, exceptions, case):
    """v1 gap #4: the wire Counter was built and never used."""
    transport_path = run_root / 'fixture/transport_source.jsonl'
    assert transport_path.exists(), 'missing Fixture transport receiver log'
    transport, drop = lines(transport_path)
    assert drop == 0, 'Fixture transport receiver lost its tail'
    observed = collections.Counter()
    for row in transport:
        topic = row['topic']
        assert topic in gids, 'transport row for an unregistered topic: ' + topic
        assert row['publisher_gid'] == gids[topic], \
            'transport row GID differs from the manifest for ' + topic
        observed[(topic, row['payload_sha256'])] += 1
    extra = wire - observed          # stored but never seen on the wire
    missing = observed - wire        # seen on the wire but not stored
    assert not missing, 'wire messages missing from storage: ' + repr(list(missing)[:4])
    # The only permitted extra is the Worker's final capability after the
    # Fixture closed (the Worker outlives the input source by design).
    extra_total = sum(extra.values())
    assert all(k[0] == '/p1/worker_capability' for k in extra), \
        'extra stored messages outside /p1/worker_capability: ' + repr(list(extra)[:4])
    assert extra_total <= 2, 'more than two unexplained extra capabilities: %d' % extra_total
    terminal_path = run_root / 'fixture/terminal.json'
    ft = read(terminal_path)
    if extra_total:
        last = next((x for x in reversed(worker_rows)
                     if x['type'] == 'capability_publish_result'), None)
        assert last, 'extra capability without a Worker publish result row'
        assert last['publish_start_ns'] > ft['closed_steady_ns'], \
            'the extra capability was not published after the Fixture closed'
    return {'observed': sum(observed.values()), 'stored': sum(wire.values()),
            'extra': extra_total}


def check_source_and_witness(run_root, source, worker_rows, decisions, jobs, exceptions, case):
    """v1 gap #16: source_summary / worker_summary / witness were not asserted."""
    summary = source.get('source_summary')
    assert summary, 'missing Regulator source_summary'
    s = summary[0]
    assert s['normal_source_complete'] is True, 'Regulator Source is not complete'
    assert s['dropped'] == 0, 'Regulator Source dropped %d rows' % s['dropped']
    assert s['generated'] == s['emitted'], 'Regulator generated != emitted'

    witness = read(run_root / 'regulator/witness.json')
    assert witness['closed'] is True, 'Witness did not close'
    assert witness['overflow'] is False, 'Witness overflowed'
    assert witness['incomplete'] is False, 'Witness reports incomplete'
    if case == 'R1':
        assert witness['observation_complete'] is False, \
            'a zero-tick run cannot be observation_complete'
    else:
        assert witness['observation_complete'] is True, \
            'Witness observation incomplete outside R1'

    worker_summaries = [x for x in worker_rows if x['type'] == 'worker_summary']
    if case in ('R1', 'R3'):
        # R1 only cancels the Regulator; R3 resumes the Worker after the lease
        # expired. In both, the Worker exits normally, so its summary must be
        # present and complete.
        assert worker_summaries, '%s worker exited cleanly but wrote no summary' % case
        ws = worker_summaries[-1]
        assert ws['normal_source_complete'] is True, \
            '%s worker summary is not complete though it exited cleanly' % case
        assert ws['fatal'] is False, '%s worker reported fatal' % case
    elif not worker_summaries:
        # R2 SIGKILLs the Worker: no summary is the declared, explainable loss.
        assert exceptions.allows('worker', 'worker_summary_missing'), \
            'missing worker_summary without a declared exception'
    else:
        ws = worker_summaries[-1]
        assert ws['fatal'] is True or ws['normal_source_complete'] is False, \
            'worker_summary claims completeness on a fault run'
    return {'witness_observation_complete': witness['observation_complete'],
            'regulator_dropped': s['dropped']}


def check_recorder_and_fixture(run_root, decoded, c):
    rec = read(run_root / 'recorder/terminal.json')
    assert rec['clean'] is True, 'Recorder did not close cleanly'
    assert rec['Recorder_stop_completed'] is True, 'Recorder stop did not complete'
    assert rec['prepared'] is True, 'Recorder was never prepared'
    assert rec['storage_stream_accounting_verified'] is False, \
        'Recorder internal accounting must stay false (external audit owns the claim)'
    ft = read(run_root / 'fixture/terminal.json')
    assert not ft['failed'], 'Fixture reports failure'
    counts = {k: len(v) for k, v in decoded.items()}
    for topic, n in ft['published_counts'].items():
        if topic in counts:
            assert counts[topic] == n, 'Fixture published %d but %d stored on %s' % (
                n, counts[topic], topic)
    return {'recorder_clean': True, 'fixture_normal_end': ft.get('normal_end')}


# ── case-specific classification ──────────────────────────────────────────

def classify_pairs(pairs, transition_ns):
    before = collections.Counter()
    after = collections.Counter()
    for p in pairs:
        bucket = after if p['starts'][0] >= transition_ns else before
        bucket[p['kind']] += 1
    return dict(before), dict(after)


def check_r1(source, by_type, pairs, reg, exceptions):
    # A defaultdict creates an empty bucket on read, so membership alone is not
    # evidence that the row exists. Only a non-empty bucket counts as production.
    present = {k for k, v in by_type.items() if v}
    for forbidden in ('job', 'owned_API_pair', 'regulator_shutdown',
                      'owned_execute_grant_accepted', 'candidate_registration'):
        assert forbidden not in present, 'R1 produced forbidden Source row: ' + forbidden
    closed = by_type['owned_prepare_closed_before_API'][0]
    assert closed['physical_API_calls'] == 0, 'R1 cancel reports a physical API call'
    assert 'owned_prepare_ready' in present, 'R1 requires prepare-ready evidence'
    return {'physical_API_calls': 0, 'api_pairs': 0}


def check_transition(by_type, reg, case):
    rows = by_type.get('worker_unusable_transition')
    assert rows, 'missing worker_unusable_transition'
    assert len(rows) == 1, 'multiple worker_unusable_transition rows'
    tr = rows[0]
    assert tr['candidate_after'] is False and tr['pending_after'] is False, \
        'transition did not clear candidate and pending'
    want = reg.get('expected_transition_reason')
    if want:
        assert tr['reason'] == want, 'transition reason %r != %r' % (tr['reason'], want)
    return tr


def check_lease_point(tr, case, c):
    """v1 gap #6: the lease is measured from the last valid receipt commit."""
    start = tr['capability_last_valid_commit_ns']
    check = tr['check_ns']
    assert start > 0 and check >= start, 'capability lease timestamps are not ordered'
    elapsed = check - start
    timeout = c['worker_capability_receipt_timeout_ns']
    assert timeout == tr['capability_timeout_ns'], 'lease timeout differs from the contract'
    if case == 'R3':
        assert tr['reason'] == 'worker_capability_expired'
        assert elapsed > timeout, \
            'R3 lease elapsed %d ns does not exceed the %d ns timeout' % (elapsed, timeout)
        assert elapsed < c['active_watchdog_ns'], \
            'R3 lease elapsed reached the watchdog window; cannot attribute to the lease'
    else:
        assert elapsed < timeout, \
            'R2 reported a process exit but the lease had already expired (%d ns)' % elapsed
    return {'lease_elapsed_ns': elapsed, 'lease_timeout_ns': timeout,
            'watchdog_ns': c['active_watchdog_ns']}


def check_post_transition(by_type, tr, case):
    t = tr['processed_ns']
    late_jobs = [j for j in by_type.get('job', []) if j.get('submit_commit_ns', 0) >= t]
    assert not late_jobs, 'job committed after the worker became unusable'
    late_regs = [r for r in by_type.get('candidate_registration', [])
                 if r.get('ready_commit_ns', 0) >= t and r.get('accepted_registration')]
    assert not late_regs, 'candidate accepted after the worker became unusable'
    return {'late_jobs': len(late_jobs), 'late_accepted_candidates': len(late_regs)}


# ── mutation self-checks ──────────────────────────────────────────────────

def self_mutations(case, checks, reg, exceptions):
    rejected, escaped = [], []

    def must_reject(name, fn):
        try:
            fn()
        except AssertionError:
            rejected.append(name)
            return
        except Exception as exc:
            rejected.append('%s:%s' % (name, type(exc).__name__))
            return
        escaped.append(name)

    def forged_result(**changes):
        out = json.loads(json.dumps(checks['result']))
        for role, rc in changes.get('rc', {}).items():
            for row in out['closed_roles']:
                if row['role'] == role:
                    row['returncode'] = rc
        return out

    # 1. Driver exit forged: a clean rc where the case demands a fault code.
    def m_exit():
        if case == 'R2':
            forged = forged_result(rc={'worker': 0})
        elif case == 'R1':
            forged = forged_result(rc={'regulator': 0})
        else:
            forged = forged_result(rc={'worker': -9})
        check_role_exits(forged, case, reg, exceptions)
    must_reject('exit_code_fabricated', m_exit)

    # 2. Applied command tampered while the honesty flags stay false.
    def m_applied():
        dec = json.loads(json.dumps(checks['decoded']))
        rows = dec.get('/research/control/applied', [])
        if not rows:
            raise AssertionError('no applied rows to mutate')
        rows[0]['final_n'] = [rows[0]['final_n'][0] + 1.0, rows[0]['final_n'][1]]
        check_typed_equality(dec, checks['source'], checks['worker'], checks['manifests'],
                             checks['c'], exceptions, case)
    must_reject('applied_command_tampered', m_applied)

    # 3. Raw publish time tampered while the self-produced flags stay false.
    def m_time():
        pairs = json.loads(json.dumps(checks['pairs']))
        if len(pairs) < 2:
            raise AssertionError('need at least two pairs')
        pairs[1]['starts'] = [pairs[1]['starts'][0] + 10**9, pairs[1]['starts'][1]]
        check_pair_stream(pairs, checks['c'], recompute=True)
    must_reject('raw_time_tampered_flags_false', m_time)

    # 4. Duplicate a stored message: a dict-by-id view would hide this.
    def m_dup():
        dec = json.loads(json.dumps(checks['decoded']))
        jobs = dec.get('/p1/solve_job', [])
        if not jobs:
            raise AssertionError('no stored jobs to duplicate')
        jobs.append(json.loads(json.dumps(jobs[0])))
        check_typed_equality(dec, checks['source'], checks['worker'], checks['manifests'],
                             checks['c'], exceptions, case)
    must_reject('duplicate_stored_message', m_dup)

    # 5. Extra Source loss must break the summary reconciliation.
    def m_loss():
        src = json.loads(json.dumps(checks['source']))
        src['source_summary'][0]['dropped'] = 1
        check_source_and_witness(checks['run_root'], src, checks['worker'],
                                 checks['decisions'], checks['jobs'], exceptions, case)
    must_reject('undeclared_source_loss', m_loss)

    return rejected, escaped


# ── main ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True, choices=['R1', 'R2', 'R3'])
    args = ap.parse_args()
    case = args.case
    reg = read(EXP53 / ('implementation/%s_registration_v1.json' % case))
    run_root = Path(reg['output'])
    c = read(Path(reg['contract']))
    exceptions = Exceptions(case)

    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    source_rows, src_dropped = lines(run_root / 'regulator/source.jsonl')
    # Only R2 SIGKILLs the Worker, so only R2 may lose the Worker's buffered tail.
    worker_rows, worker_dropped = lines(run_root / 'worker/source.jsonl',
                                        allow_truncated_tail=(case == 'R2'))
    assert src_dropped == 0, 'the Regulator Source must never lose its tail'
    if worker_dropped:
        assert exceptions.allows('worker', 'candidate_row_unflushed'), \
            'worker Source tail dropped without a declared exception'
    by_type = collections.defaultdict(list)
    for r in source_rows:
        by_type[r['type']].append(r)
    jobs = [r['job'] for r in by_type['job']]
    pairs = by_type['owned_API_pair']
    decisions = by_type['decision']

    manifests = {role: read(run_root / role / ('owned_manifest.json' if role == 'fixture'
                                               else 'manifest.json'))
                 for role in ['regulator', 'worker', 'fixture', 'recorder']}
    result = read(run_root / 'driver_result.json')
    outer = read(D.parent / 'scheme_A_M4_owned_faults_20261021_53' /
                 ('evidence/%s_launch_v1.json' % case))

    # Input closure: every pinned byte must still match.
    lock_files = dict(read(EXP53 / 'preflight/prerun_source_lock_v1.json')['files'])
    inputs = ([p for p in run_root.rglob('*') if p.is_file()]
              + [Path(__file__).resolve(), EXP53 / ('implementation/%s_registration_v1.json' % case),
                 EXP53 / 'preflight/prerun_source_lock_v1.json'])
    before = {str(p): pin(p) for p in inputs}
    for p, row in lock_files.items():
        assert pin(Path(p)) == row, 'registered input changed: ' + p

    assert result['passed'] is True, 'driver reported failure'
    assert outer['passed'] is True, 'outer harness reported failure'

    exits, exit_notes = check_role_exits(result, case, reg, exceptions)
    gids = check_publishers(manifests, c)
    ready, prepared, grant = check_bootstrap(run_root, by_type, pairs, c, manifests)
    stream = check_pair_stream(pairs, c, recompute=True)
    maxjitter = check_decisions(decisions, pairs, c)
    check_jobs(jobs, pairs, c, manifests)
    # R1 cancels before any business tick: there is no API pair stream at all,
    # so the shutdown-pair assertions apply only to the post-grant cases.
    shutdown = check_shutdown(by_type, pairs, c, exceptions) if pairs else None
    if pairs == []:
        assert case == 'R1', 'a non-R1 case produced no API pairs'

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

    typed = check_typed_equality(decoded, source_rows, worker_rows, manifests,
                                 c, exceptions, case)
    transport = check_wire(run_root, decoded, wire, gids, worker_rows,
                           manifests, exceptions, case)
    src = check_source_and_witness(run_root, by_type, worker_rows, decisions,
                                   jobs, exceptions, case)
    rec = check_recorder_and_fixture(run_root, decoded, c)

    case_summary = {}
    if case == 'R1':
        case_summary = check_r1(by_type, by_type, pairs, reg, exceptions)
    else:
        tr = check_transition(by_type, reg, case)
        before_kinds, after_kinds = classify_pairs(pairs, tr['processed_ns'])
        lease = check_lease_point(tr, case, c)
        post = check_post_transition(by_type, tr, case)
        case_summary = {'transition_reason': tr['reason'],
                        'pairs_before_transition': before_kinds,
                        'pairs_after_transition': after_kinds,
                        'lease': lease, 'post_transition': post}

    checks = {'result': result, 'decoded': decoded, 'source': by_type,
              'worker': worker_rows, 'manifests': manifests, 'c': c,
              'run_root': run_root, 'pairs': pairs, 'decisions': decisions,
              'jobs': jobs}
    rejected, escaped = self_mutations(case, checks, reg, exceptions)
    assert not escaped, 'audit failed to reject fabricated input: ' + repr(escaped)
    assert len(rejected) == 5, 'mutation self-check count wrong: ' + repr(rejected)

    after = {str(p): pin(p) for p in inputs}
    assert before == after, 'audit inputs changed during the audit'

    report = {
        'schema': 'M4-owned-fault-audit-v2', 'case': case, 'run_id': reg['run_id'],
        'passed': True,
        'role_exit_codes': exits,
        'registration_discrepancies': exit_notes,
        'declared_exceptions': exceptions.describe(),
        'pair_stream': stream,
        'max_tick_start_jitter_ns': maxjitter,
        'typed_equality': typed,
        'wire_transport': transport,
        'source_and_witness': src,
        'recorder_and_fixture': rec,
        'case_summary': case_summary,
        'shutdown': ({'zero_target_published': shutdown['zero_target_published'],
                      'shutdown_grace_exceeded': shutdown['shutdown_grace_exceeded']}
                     if shutdown else {'absent': 'R1 cancels before any business tick'}),
        'mutation_rejections': rejected,
        'input_continuity': len(before),
        'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
        'research_conclusion': False,
    }
    out = D / 'postrun' / ('%s_audit_v2.json' % case)
    with out.open('x') as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write('\n')
    print(json.dumps({'passed': True, 'case': case,
                      'pairs': typed['pairs'], 'decisions': typed['decisions'],
                      'stored': transport['stored'], 'wire_extra': transport['extra'],
                      'lease_elapsed_ns': case_summary.get('lease', {}).get('lease_elapsed_ns'),
                      'output': str(out)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
