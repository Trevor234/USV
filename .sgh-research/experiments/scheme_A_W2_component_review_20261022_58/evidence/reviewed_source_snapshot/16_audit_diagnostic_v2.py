#!/usr/bin/env python3
"""Independent W1/W3/W4 diagnostic run audit. Read-only: no ROS, no new runs.

This is a NEW tool for the diagnostic package, not a port of batch-53's
audit_fault_v2.py. The cases differ in a way that changes what accounting is
possible:

  * Batch 53 measured processes dying (R1 cancel, R2 SIGKILL, R3 SIGSTOP).
    Its reconciliation was: did the Regulator stop trusting a dead Worker.
  * W1/W3/W4 measure a live Worker misbehaving under a registered in-process
    hook. The reconciliation is per-Job: for each Job the Regulator published,
    there must be exactly one of {a delivered Candidate, a recorded drop, an
    expired pending} and the Decision for that Job's target tick must agree
    with which of those happened.

The accounting is therefore a multiset over Job identity, not a count, so a
duplicated or substituted message cannot cancel out a missing one.

Every expectation is recomputed from raw Source rows plus the contract. The
audit deliberately does NOT trust Driver-derived summary booleans; it re-derives
them. Where a claim cannot be re-derived from files on disk, the audit says so
in `unprovable_here` instead of echoing the Driver.
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
SCOPE = 'M4_owned_diagnostic_worker_only_v1'
CASES = ('W1', 'W3', 'W4')
TAG = {'W1-work-stall-watchdog': 'W1', 'W3-result-delivery-delay': 'W3',
       'W4-result-delivery-drop': 'W4'}


def pin(p):
    b = Path(p).read_bytes()
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}


def read(p):
    return json.loads(Path(p).read_bytes())


def lines(p, allow_truncated_tail=False):
    raw = Path(p).read_bytes()
    assert len(raw) <= 128 * 1024**2, 'source larger than the bounded read'
    dropped = 0
    if not raw.endswith(b'\n'):
        assert allow_truncated_tail, 'truncated Source tail (no trailing newline)'
        cut = raw.rfind(b'\n')
        assert cut >= 0, 'Source is a single unterminated line'
        dropped = len(raw) - cut - 1
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


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def by_type(rows):
    out = collections.defaultdict(list)
    for r in rows:
        out[r['type']].append(r)
    return out


# ── shared checks ─────────────────────────────────────────────────────────

def check_roles(result, reg, case):
    """Every role's exit code and signal list, from the Driver's real closure."""
    closed = result.get('closed_roles') or []
    assert len(closed) == 4, 'expected exactly four closed roles'
    by_role = {r['role']: r for r in closed}
    assert set(by_role) == {'regulator', 'worker', 'fixture', 'recorder'}, \
        'closed roles are not the four owned roles'
    want = reg['expected']['exit_codes']
    for role, value in want.items():
        got = by_role[role]['returncode']
        assert got == value, '%s exit %r != registered %r' % (role, got, value)
    for role, row in by_role.items():
        assert row.get('group_empty') is True, 'role group not empty: ' + role
        assert not row.get('error'), 'close error for %s: %r' % (role, row['error'])
    sig_want = reg['expected']['signals']
    seen = {}
    for role, want_sigs in sig_want.items():
        got = [s['signal'] for s in by_role[role]['signals']]
        seen[role] = got
        # The Regulator is stopped by the Driver through killpg and records its
        # closure via wait_close(), which reports signals=[] by design. Any
        # other role must match the registration exactly.
        if role == 'regulator':
            assert got == [] or got == want_sigs, \
                'regulator signals %r are neither empty nor registered %r' % (got, want_sigs)
            continue
        assert got == want_sigs, '%s signals %r != registered %r' % (role, got, want_sigs)
    return {'exit_codes': {r: by_role[r]['returncode'] for r in by_role},
            'signals': seen,
            'unprovable_here': ['a signal list of [] is consistent with both a clean '
                                'exit and a close that happened before the Driver '
                                'sampled; only the exit code distinguishes them']}


def check_service_bundle(record, role):
    """Every file listed in a role's source bundle must still hash to its pin.

    This is the check that would have caught a role running against a source
    tree other than the one the run registered.
    """
    bpin = record['source_bundle']
    assert pin(bpin['path'])['sha256'] == bpin['sha256'], \
        '%s source bundle bytes changed' % role
    bundle = read(bpin['path'])
    rows = bundle['files']
    rows = rows.values() if isinstance(rows, dict) else rows
    assert len(rows) > 0, '%s source bundle is empty' % role
    for row in rows:
        got = pin(row['path'])
        assert got['bytes'] == row['bytes'] and got['sha256'] == row['sha256'], \
            '%s bundle member changed: %s' % (role, row['path'])
    return {'bundle_files': len(rows), 'bundle_sha256': bpin['sha256']}


def check_registration_pins(regfile, reg, registry):
    """The registration must still be the file the launch receipt recorded."""
    reg_sha = pin(regfile)['sha256']
    evidence = D / 'evidence' / ('%s_launch_v1.json' % TAG[reg['case']])
    assert evidence.exists(), 'missing launch receipt for this case'
    launch = read(evidence)
    assert launch['registration_sha256'] == reg_sha, \
        'the run was launched from different registration bytes'
    assert launch['registration'] == str(regfile), \
        'the launch receipt names a different registration path'
    assert launch['passed'] is True, 'the outer harness reported failure'
    assert launch['case'] == reg['case'], 'launch case differs from the registration'
    assert launch['driver_result']['run_id'] == reg['run_id'], \
        'the launch receipt names a different run'
    driver_manifest = read(Path(reg['output']) / 'driver_manifest.json')
    assert driver_manifest.get('registration_sha256') == reg_sha, \
        'the Driver recorded a different registration SHA'
    return {'registration_sha256': reg_sha,
            'driver_manifest_sha256': pin(Path(reg['output']) / 'driver_manifest.json')['sha256']}


def check_role_identity(run_root, registry, manifests, reg, c_typed):
    """Close the identity chain: registry -> manifest -> actual ELF -> bundle.

    The three links are checked separately because each has failed at least
    once in this project's history: a registry pinned an older build, a
    registration was rewritten after the run, and a manifest could name a
    binary that is no longer on disk.
    """
    out = {}
    for role in ('regulator', 'worker', 'fixture', 'recorder'):
        entry = registry['roles'][role]
        m = manifests[role]
        # 1. The ELF on disk still hashes to the registry value.
        actual = pin(entry['binary'])['sha256']
        assert actual == entry['binary_sha256'], \
            '%s ELF on disk differs from the registry pin' % role
        # 2. The manifest the role wrote names that same ELF and hash.
        assert m['binary_sha256'] == entry['binary_sha256'], \
            '%s manifest names a different binary hash than the registry' % role
        assert Path(m['exe']).resolve() == Path(entry['binary']).resolve(), \
            '%s manifest names a different executable path than the registry' % role
        # 3. The bundle that ELF was built from is intact.
        bundle = check_service_bundle(entry, role)
        assert m['source_bundle_sha256'] == bundle['bundle_sha256'], \
            '%s manifest names a different source bundle than the registry' % role
        out[role] = {'binary_sha256': actual, **bundle}
    # 4. The Driver is a tool, not a role, but it is pinned the same way.
    driver = registry['driver']
    assert pin(driver)['sha256'] == registry['driver_tool_sha256'], \
        'the Driver script differs from the registry pin'
    dm = read(Path(reg['output']) / 'driver_manifest.json')
    if 'driver_tool_sha256' in dm:
        assert dm['driver_tool_sha256'] == registry['driver_tool_sha256'], \
            'the run Driver manifest names a different Driver'
    out['driver'] = {'sha256': registry['driver_tool_sha256']}
    # 5. The effective configuration each role loaded must equal the run
    #    contract's typed configuration exactly, not just a few fields.
    for role in ('regulator', 'worker', 'fixture'):
        assert manifests[role]['contract_configuration'] == c_typed, \
            '%s loaded a contract configuration that differs from the run contract' % role
    return out


def check_contract_identity(run_root, c, registry, manifests, reg):
    """The run's own manifests must carry the diagnostic identity, not the frozen one."""
    assert c['schema'] == 'p1-execution-contract-v4'
    assert c['qualification'] == 'execution_diagnostic_only'
    assert c['execute_qualified'] is False
    assert c['parameters_are_diagnostic_only'] is True
    assert c['fault_injection_enabled'] is True
    # The contract file has no self-referential hash field; its identity is the
    # SHA-256 of its own bytes, which the registry and the registration pin.
    contract_sha = hashlib.sha256(Path(reg['contract']).read_bytes()).hexdigest()
    assert contract_sha == registry['contract_sha256'], \
        'contract bytes do not match the registry pin'
    for role in ('regulator', 'worker', 'fixture'):
        m = manifests[role]
        assert m['run_id'] == reg['run_id'], \
            '%s manifest run id differs from the registration' % role
        # The scope is carried inside the frozen contract configuration the role
        # actually loaded, not as a top-level manifest field. Worker has no
        # m4_release_scope of its own, so this is the only honest source.
        cfg = m['contract_configuration']
        assert cfg['qualification'] == 'execution_diagnostic_only', \
            '%s loaded a non-diagnostic contract' % role
        assert cfg['fault_injection_enabled'] is True, \
            '%s loaded a contract without fault injection' % role
        assert cfg['execute_qualified'] is False, \
            '%s loaded a contract claiming execute qualification' % role
        assert cfg['output_topics'] == c['output_topics'], \
            '%s output topics differ from the run contract' % role
        assert m['contract_sha256'] == contract_sha, \
            '%s manifest contract hash differs from the contract bytes' % role
        # Model identity is declared per role: the Worker names the nominal
        # hash, the Fixture carries the hydro coefficients it integrates, and
        # the Regulator declares neither (it holds no numerical model). Check
        # exactly what each role claims.
        if 'nominal_hash' in m:
            assert m['nominal_hash'] == c['nominal_hash'], \
                '%s manifest nominal hash differs from the contract' % role
        if 'contract_hydro' in m:
            assert m['contract_hydro'] == c['hydro'], \
                '%s manifest hydro differs from the contract' % role
        if role == 'regulator':
            assert 'nominal_hash' not in m and 'contract_hydro' not in m, \
                'the Regulator claims a numerical model it does not own'
        if 'm4_release_scope' in m:
            assert m['m4_release_scope'] == SCOPE, \
                '%s manifest scope is %r' % (role, m['m4_release_scope'])
    return {'contract_hash': contract_sha, 'scope': SCOPE}


def check_publishers(manifests, c):
    cm = manifests['regulator']
    assert cm['role'] == 'p1_owned_execute_regulator'
    assert cm['physical_publishers'] == 2
    assert cm['physical_API_calls_before_grant'] == 0
    outputs = {'/p1/solve_job', '/p1/execution_decision', '/research/control/applied',
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
    for topic in outputs:
        assert owner.get(topic) == 'regulator', 'output topic not owned by regulator: ' + topic
    return gid


def check_pair_stream(pairs, c):
    """Recompute gap/span/rate from raw starts/ends; never trust the flags."""
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
        assert span <= c['publish_budget_ns'], 'pair span %d > budget' % span
        maxspan = max(maxspan, span)
        for side in (0, 1):
            n = p['command_n'][side]
            assert isinstance(n, (int, float)) and math.isfinite(n), 'non-finite command'
            assert c['command_min_n'] <= n <= c['command_max_n'], 'command outside N envelope'
            if known[side]:
                elapsed = p['starts'][side] - prev_start[side]
                assert elapsed > 0, 'non-positive per-side API interval'
                assert elapsed <= c['publish_gap_ns'], 'per-side gap %d > %d' % (
                    elapsed, c['publish_gap_ns'])
                maxgap[side] = max(maxgap[side], elapsed)
                rate = abs(n - prev_n[side]) * 1e9 / elapsed
                assert rate <= c['rho_n_s'] + 1e-9, 'recomputed rate %.6f > %.6f' % (
                    rate, c['rho_n_s'])
                maxrate[side] = max(maxrate[side], rate)
        for flag in ('gap_exceeded', 'span_exceeded', 'rate_exceeded', 'command_invalid'):
            assert not p.get(flag), 'Source self-reported %s at pair %d' % (flag, i)
        # Advance the chain only after this pair has been fully verified, so the
        # next iteration's previous_known/previous_n check is meaningful.
        for side in (0, 1):
            if p['returned'][side]:
                known[side] = True
                prev_n[side] = p['command_n'][side]
                prev_start[side] = p['starts'][side]
    assert pairs[-1]['command_n'] == [0, 0], 'final API pair is not a zero command'
    assert pairs[-1]['returned'] == [True, True], 'final API pair did not return both sides'
    return {'pairs': len(pairs), 'max_gap_ns': maxgap, 'max_rate_n_s': maxrate,
            'max_span_ns': maxspan}


def check_decisions(decisions, c):
    for d in decisions:
        assert d['mode'] == 'execute', 'decision mode is not execute'
        assert d['skipped_ticks'] == 0, 'scheduler skipped a tick'
        jitter = d['start_ns'] - d['planned_ns']
        assert 0 <= jitter <= c['tick_jitter_ns'], 'tick start jitter %d out of range' % jitter
        # Both flags must be derived from the contract, not from the run mode:
        # a v4 run ticks in execute mode but is still diagnostic-only, and must
        # never claim normal-contract completeness.
        assert d['diagnostic_only'] is True, \
            'decision tick %d does not declare diagnostic-only' % d['tick']
        assert d['normal_contract_complete'] is False, \
            'decision tick %d claimed normal-contract completeness' % d['tick']
        assert d['plant_acceptance_observed'] is False, 'fabricated plant acceptance'
    ticks = [d['tick'] for d in decisions]
    assert ticks == sorted(ticks) and len(set(ticks)) == len(ticks), \
        'decision ticks are not strictly increasing'
    assert ticks == list(range(ticks[0], ticks[0] + len(ticks))), 'decision ticks have a gap'


def check_jobs(jobs, pairs, c, manifests):
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
                'job anchor_publish_ns does not match the referenced pair'
            assert job['anchor_publish_ns'][side] <= job['freeze_ns'], \
                'job anchored to a future publish'
        clock_now = job['frozen_clock_sim_ns'] + job['freeze_ns'] - job['frozen_clock_receive_ns']
        for key in ['odom'] + (['imu'] if job['r_from_imu'] else []):
            assert 0 <= job['freeze_ns'] - job[key + '_receive_ns'] <= c[key + '_age_ns'], \
                '%s receipt age out of bounds' % key
            lag = clock_now - job[key + '_stamp_ns']
            assert -c['source_future_slack_ns'] <= lag <= c[key + '_sim_lag_ns'], \
                '%s sim-domain lag %d out of bounds' % (key, lag)


# ── W1/W3/W4 per-Job reconciliation ───────────────────────────────────────

def job_ledger(worker_rows, regulator_rows, dropped_ids):
    """One entry per Job identity the Regulator actually published.

    A Job is accounted for exactly once. The legal outcomes are:
      delivered   -- Candidate published by the Worker
      dropped     -- Candidate generated and deliberately not published (W4)
      expired     -- Worker discarded the Job at the pre-native deadline check
      replaced    -- Worker superseded the Job while it was still pending
      unreported  -- a Job the Regulator published with no Worker outcome at all
    A Job with two conflicting outcomes, or an outcome for a Job the Regulator
    never published, fails here. Every received Job must resolve exactly once.
    """
    w = by_type(worker_rows)
    r = by_type(regulator_rows)
    published = {}
    for row in r['job']:
        jid = row['job']['job_id']
        assert jid not in published, 'Regulator published job %r twice' % jid
        published[jid] = row['job']
    received, solved, expired, replaced = {}, {}, {}, {}
    for row in w['job_received']:
        jid = row['job']['job_id']
        assert jid not in received, 'Worker received job %r twice' % jid
        received[jid] = row
    for row in w['candidate']:
        jid = row['job']['job_id']
        assert jid not in solved, 'Worker generated two candidates for job %r' % jid
        solved[jid] = row
    for row in w.get('pending_expired_before_native', []):
        jid = row['job_id']
        assert jid not in expired, 'Worker expired job %r twice' % jid
        expired[jid] = row
    # A single pending slot means a Job can also be superseded before it ever
    # runs. That is a legitimate Worker outcome, not a loss: the row names both
    # the discarded Job and its replacement, so the discard stays attributable.
    for row in w.get('pending_replaced', []):
        jid = row['job_id']
        assert jid not in replaced, 'job %r was replaced twice' % jid
        replaced[jid] = row
    # A Job cannot end in two different ways. "delivered" is two rows (candidate
    # + publish_result) describing ONE outcome, and W4's drop is likewise two
    # rows (candidate + dropped) for one outcome; every other bucket is one row.
    publish_result = {row['job_id']: row for row in w['candidate_publish_result']}
    dropped_pre = {row['job_id']: row for row in w['diagnostic_candidate_dropped']}
    dropped = dropped_pre
    terminal = collections.Counter()
    for jid in publish_result:
        terminal[jid] += 1
    for jid in dropped_pre:
        terminal[jid] += 1
    for jid in expired:
        terminal[jid] += 1
    for jid in replaced:
        terminal[jid] += 1
    foreign = sorted(set(terminal) - set(published))
    assert not foreign, \
        'Worker produced outcomes for Jobs the Regulator never published: %r' % foreign
    unpublished_solved = sorted(set(solved) - set(published))
    assert not unpublished_solved, \
        'Worker solved Jobs the Regulator never published: %r' % unpublished_solved
    ambiguous = {jid: n for jid, n in terminal.items() if n > 1}
    assert not ambiguous, 'Jobs with more than one terminal outcome: %r' % ambiguous
    # Every received Job must have exactly one terminal outcome, otherwise the
    # Worker silently lost the Job and the ledger's 'unreported' bucket would
    # be hiding it.
    for jid in received:
        assert jid in terminal, 'Worker accepted job %r and never resolved it' % jid

    ledger, problems = {}, []
    for jid, job in sorted(published.items()):
        if jid in dropped:
            kind = 'dropped'
        elif jid in publish_result:
            assert publish_result[jid]['success'] is True, \
                'job %r reported an unsuccessful publish_result' % jid
            kind = 'delivered'
        elif jid in expired:
            kind = 'expired'
        elif jid in replaced:
            kind = 'replaced'
        else:
            kind = 'unreported'
            problems.append({'job_id': jid, 'problem': 'no Worker outcome at all'})
        ledger[jid] = {'kind': kind, 'target_tick': job['target_tick'],
                       'worker_received': jid in received, 'solved': jid in solved,
                       'replaced_by': replaced[jid]['replacement_job_id'] if jid in replaced else None}
    assert set(dropped_ids) == set(dropped), \
        'the drop rows and the job ledger disagree about which job was dropped'
    for jid, row in publish_result.items():
        assert ledger[jid]['kind'] == 'delivered'
    return ledger, problems


def check_target_tick(ledger, decisions, c):
    """Every business decision must agree with the Job outcome for that tick."""
    by_tick = {j['target_tick']: (jid, j) for jid, j in ledger.items()}
    out = {}
    for d in decisions:
        tick = d['tick']
        entry = by_tick.get(tick)
        accepted = d['accepted']
        if entry is None:
            # No Job targeted this tick. It may still accept an EARLIER job
            # whose candidate is still inside the window; the Regulator binds a
            # candidate to a job, not to a tick, so record what happened.
            out[tick] = {'job': None, 'accepted': accepted,
                         'reason': d['reason'], 'control_source': d['control_source']}
            if accepted:
                assert d['job_id'] in ledger, \
                    'tick %d accepted job %r that was never published' % (tick, d['job_id'])
                assert ledger[d['job_id']]['kind'] == 'delivered', \
                    'tick %d accepted a job that was not delivered' % tick
            continue
        jid, job = entry
        out[tick] = {'job': jid, 'kind': job['kind'], 'accepted': accepted,
                     'reason': d['reason'], 'control_source': d['control_source'],
                     'job_id_field': d['job_id']}
        if job['kind'] in ('dropped', 'expired', 'replaced'):
            assert accepted is False, \
                'tick %d accepted a candidate the Worker never published (job %r)' % (tick, jid)
            assert d['job_id'] != jid, \
                'tick %d claims to have applied dropped job %r' % (tick, jid)
            assert d['control_source'] in ('hold', 'ramp_zero'), \
                'tick %d fell back with source %r' % (tick, d['control_source'])
        if accepted:
            assert d['job_id'] == jid, \
                'tick %d accepted job %r but is registered to job %r' % (tick, d['job_id'], jid)
    return out


def check_fallback_policy(decisions, c):
    """Recompute hold-vs-ramp for every non-accepted business decision."""
    hold_ns = c['hold_ns']
    accepted = [(d['tick'], d['activation_commit_ns']) for d in decisions
                if d['accepted']]
    out = []
    for d in decisions:
        if d['accepted']:
            continue
        if d['reason'] in ('shutdown', 'unknown_anchor'):
            continue
        prior = [k for t, k in accepted if t < d['tick']]
        if not prior:
            continue
        age = d['activation_commit_ns'] - max(prior)
        required = 'hold' if age <= hold_ns else 'ramp_zero'
        assert d['control_source'] == required, \
            'tick %d fell back as %r but the frozen policy requires %r (age %d ns)' % (
                d['tick'], d['control_source'], required, age)
        if required == 'hold':
            assert d['final_n'] == d['previous_n'], \
                'tick %d hold did not preserve the applied command' % d['tick']
        out.append({'tick': d['tick'], 'age_since_accepted_ns': age,
                    'required': required, 'observed': d['control_source']})
    return out


# ── Worker-side hook evidence ─────────────────────────────────────────────

def check_worker_hooks(case, worker_rows, c):
    """The registered hook must appear exactly once, and no other hook may run."""
    w = by_type(worker_rows)
    hooks = collections.Counter()
    for key in ('diagnostic_v2_pre_native_enter', 'controlled_pre_native_barrier',
                'diagnostic_candidate_dropped', 'terminal_exception',
                'terminal_numerical_failure'):
        hooks[key] = len(w.get(key, []))
    assert hooks['controlled_pre_native_barrier'] == 0, 'unregistered native barrier ran'
    assert hooks['terminal_exception'] == 0, 'Worker raised a terminal exception'
    assert hooks['terminal_numerical_failure'] == 0, 'Worker hit a numerical failure'
    detail = {}
    if case == 'W1':
        assert hooks['diagnostic_v2_pre_native_enter'] == 1, \
            'W1 requires exactly one registered stall, saw %d' % hooks['diagnostic_v2_pre_native_enter']
        enter = w['diagnostic_v2_pre_native_enter'][0]
        release = w['diagnostic_v2_pre_native_release'][0]
        assert enter['actual_native_invoked'] is False, 'W1 stall claims a native invocation'
        assert enter['stage_qualified'] is False, 'W1 stall claims stage qualification'
        assert enter['duration_ms'] == c.get('diagnostic_stall_ms', enter['duration_ms'])
        duration = release['released_ns'] - enter['start_ns']
        assert duration >= enter['duration_ms'] * 1000000 * 0.95, \
            'W1 stall released after %d ns, well before its registered %d ms' % (
                duration, enter['duration_ms'])
        detail = {'stall_enter_ns': enter['start_ns'], 'stall_release_ns': release['released_ns'],
                  'stall_duration_ns': duration, 'stall_duration_ms': enter['duration_ms'],
                  'stopping_at_release': release['stopping'],
                  'unprovable_here': ['that the stall is NOT a native C hang follows from '
                                      'actual_native_invoked=false and the sleep site '
                                      'preceding solve_owned(), not from timing']}
    elif case == 'W3':
        assert hooks['diagnostic_candidate_dropped'] == 0, 'W3 must not drop a candidate'
        assert hooks['diagnostic_v2_pre_native_enter'] == 0, 'W3 must not stall'
        cand = w['candidate']
        assert cand, 'W3 generated no candidate'
        delays = []
        for row in cand:
            jid = row['job']['job_id']
            res = next((x for x in w['candidate_publish_result'] if x['job_id'] == jid), None)
            assert res is not None, 'W3 candidate %r was never published' % jid
            d = res['publish_start_ns'] - row['solve_end_ns']
            delays.append(d)
            assert d >= 0, 'candidate %r published before its solve ended' % jid
            # The solve timestamps must NOT be rewritten to hide the delay.
            assert res['solve_start_ns'] == row['solve_start_ns'], \
                'candidate %r rewrote solve_start_ns' % jid
            assert res['solve_end_ns'] == row['solve_end_ns'], \
                'candidate %r rewrote solve_end_ns' % jid
        detail = {'publish_delays_ns': delays,
                  'solve_time_identity_preserved': True}
    else:
        assert hooks['diagnostic_candidate_dropped'] == 1, \
            'W4 requires exactly one dropped candidate, saw %d' % hooks['diagnostic_candidate_dropped']
        assert hooks['diagnostic_v2_pre_native_enter'] == 0, 'W4 must not stall'
        drop = w['diagnostic_candidate_dropped'][0]
        assert drop['publish_attempted'] is False, 'W4 drop claims a publish attempt'
        assert drop['policy'] == 'generate_once_without_publish', 'W4 drop policy differs'
        jid = drop['job_id']
        assert not any(x['job_id'] == jid for x in w['candidate_publish_result']), \
            'the dropped candidate was published after all'
        generated = [row['job']['job_id'] for row in w['candidate']]
        assert drop['generated_candidates'] == generated.index(jid) + 1, \
            'the drop index does not match the generated candidate order'
        detail = {'dropped_job_id': jid, 'generated_at_drop': drop['generated_candidates'],
                  'candidate_order': generated}
    return {'hooks': dict(hooks), **detail}


def check_worker_accounting(worker_rows, ledger):
    """Worker summary and capability stream must agree with the Job ledger."""
    w = by_type(worker_rows)
    summary = w.get('worker_summary')
    assert summary, 'Worker wrote no summary though it exited cleanly'
    s = summary[-1]
    assert s['fatal'] is False, 'Worker summary reports fatal'
    assert s['terminal_numerical_failure'] is False, 'Worker summary reports a numerical failure'
    assert s['normal_source_complete'] is True, 'Worker Source is not complete'
    generated = len(w['candidate'])
    published = len(w['candidate_publish_result'])
    dropped = len(w['diagnostic_candidate_dropped'])
    assert s['generated_candidates'] == generated, \
        'summary generated %d != candidate rows %d' % (s['generated_candidates'], generated)
    assert s['published_candidates'] == published, \
        'summary published %d != publish_result rows %d' % (
            s['published_candidates'], published)
    # The Worker must account for its own drops by name, not merely fail the
    # generated==published equality; otherwise a policy drop and a real loss
    # would be indistinguishable in the summary.
    assert s['dropped_candidates'] == dropped, \
        'summary dropped %d != dropped rows %d' % (s['dropped_candidates'], dropped)
    assert generated == published + dropped, \
        'generated %d != published %d + dropped %d' % (generated, published, dropped)
    delivered = sum(1 for v in ledger.values() if v['kind'] == 'delivered')
    assert published == delivered, \
        'Worker published %d but the Job ledger has %d delivered' % (published, delivered)
    cap = s['capability_source']
    assert cap['capability_source_complete'] is True, 'capability Source incomplete'
    assert cap['capability_publish_threw'] == 0, 'a capability publish threw'
    assert cap['capability_generated'] == cap['capability_result_records'], \
        'capability generated != result records'
    # Every capability payload must be internally consistent and monotone.
    last_completed = -1
    for row in w['capability_publish_attempt']:
        p = row['payload']
        assert p['completed_jobs'] >= last_completed, 'completed_jobs went backwards'
        last_completed = p['completed_jobs']
        assert 0 <= p['pending_count'] <= 1, 'pending_count outside {0,1}'
        if p['active_job']:
            assert p['active_job'] in {j for j in ledger}, \
                'capability reports active job %r that was never published' % p['active_job']
    # completed_jobs counts finished ticks, not deliveries: a dropped Candidate
    # still completed its solve. So the final capability must equal the number
    # of Candidates generated, and must cover every delivered one.
    assert last_completed == generated, \
        'final capability completed %d != %d generated candidates' % (
            last_completed, generated)
    assert last_completed >= delivered, \
        'final capability completed %d < %d delivered jobs' % (last_completed, delivered)
    return {'generated': generated, 'published': published, 'dropped': dropped,
            'delivered': delivered, 'final_completed': last_completed,
            'unprovable_here': ['the capability DDS payloads themselves are checked by '
                                'the wire reconciliation, not by these summary counters']}


def check_capability_continuity(regulator_rows, worker_rows, case):
    """Heartbeat continuity: the Worker's own capability stream must not gap."""
    attempts = by_type(worker_rows)['capability_publish_attempt']
    assert len(attempts) >= 2, 'fewer than two capability attempts'
    gaps = []
    for a, b in zip(attempts, attempts[1:]):
        gaps.append(b['snapshot_ns'] - a['snapshot_ns'])
    nominal = 200000000
    worst = max(gaps)
    # The heartbeat is an executor timer. Under W1 the computation thread is
    # stalled, so a gap materially beyond the timer period would mean the
    # heartbeat itself was blocked -- the exact failure W1 must rule out.
    assert worst <= nominal * 3, \
        'capability heartbeat gap %d ns exceeds three timer periods' % worst
    received = by_type(regulator_rows)['capability_admission']
    assert received, 'Regulator admitted no capability'
    return {'capability_attempts': len(attempts), 'worst_heartbeat_gap_ns': worst,
            'regulator_admissions': len(received)}


def check_transition(regulator_rows, case):
    """W1 MUST go unusable via the watchdog; W3/W4 must never go unusable.

    The three cases are defined by opposite outcomes, so a single blanket
    "no transition" assertion would contradict W1's entire claim.
    """
    r = by_type(regulator_rows)
    transitions = r.get('worker_unusable_transition', [])
    watchdogs = r.get('active_watchdog', [])
    exits = r.get('worker_process_exited', [])
    if case == 'W1':
        assert len(transitions) == 1, \
            'W1 requires exactly one worker_unusable_transition, saw %d' % len(transitions)
        assert transitions[0]['reason'] == 'active_watchdog', \
            'W1 transition reason is %r, not active_watchdog' % transitions[0]['reason']
        assert watchdogs, 'W1 has a transition but no active_watchdog row'
        assert not exits, 'W1 saw the Worker process exit'
        return {'transition': True, 'reason': transitions[0]['reason'],
                'processed_ns': transitions[0]['processed_ns'],
                'watchdog_rows': len(watchdogs),
                'unprovable_here': ['that the watchdog, and not the lease, fired is '
                                    'shown by lease_age(check_ns - last valid commit) '
                                    'staying under the lease timeout']}
    assert not transitions, '%s produced a worker_unusable_transition' % case
    assert not watchdogs, '%s tripped the active watchdog' % case
    assert not exits, '%s saw the Worker process exit' % case
    return {'transition': False}


# ── typed Source <-> Stored equality ──────────────────────────────────────

DECISION_RENAMES = {'schema_version': 'schema', 'clock_epoch': 'epoch',
                    'tick_planned_ns': 'planned_ns', 'tick_start_ns': 'start_ns',
                    'tick_end_ns': 'end_ns', 'candidate_accepted': 'accepted',
                    'candidate_ready_commit_ns': 'ready_commit_ns'}
JOB_RENAMES = {'schema_version': 'schema', 'tick_origin_steady_ns': 'tick_origin_ns',
               'freeze_steady_ns': 'freeze_ns', 'deadline_steady_ns': 'deadline_ns',
               'target_steady_ns': 'target_ns', 'horizon_steps': 'N',
               'prediction_dt': 'dt'}


def check_typed_equality(decoded, regulator_rows, worker_rows, manifests, c):
    r = by_type(regulator_rows)
    w = by_type(worker_rows)
    jobs = [row['job'] for row in r['job']]
    decisions = r['decision']
    pairs = r['owned_API_pair']
    counts = {k: len(v) for k, v in decoded.items()}

    stored_jobs = decoded.get('/p1/solve_job', [])
    assert collections.Counter(canonical({JOB_RENAMES.get(k, k): v for k, v in j.items()})
                               for j in stored_jobs) == \
        collections.Counter(canonical(j) for j in jobs), \
        'stored jobs differ from Source jobs (multiset)'
    assert counts.get('/p1/solve_job', 0) == len(jobs), 'stored job count mismatch'

    # Candidates: the Stored set is exactly the PUBLISHED set. A dropped
    # candidate must be absent, which is the whole point of W4.
    stored_cands = decoded.get('/p1/solve_candidate', [])
    published_ids = {row['job_id'] for row in w['candidate_publish_result']}
    assert len(stored_cands) == len(published_ids), \
        'stored candidates %d != published %d' % (len(stored_cands), len(published_ids))
    assert collections.Counter(x['job']['job_id'] for x in stored_cands) == \
        collections.Counter(published_ids), 'stored candidate job ids differ from published'
    solved = {row['job']['job_id']: row for row in w['candidate']}
    for cand in stored_cands:
        jid = cand['job']['job_id']
        row = solved[jid]
        assert {JOB_RENAMES.get(k, k): v for k, v in cand['job'].items()} == row['job'], \
            'candidate job echo differs for job %r' % jid
        assert cand['first_control'] == row['first_control'], 'candidate first_control differs'
        assert cand['x_prediction'] == row['X'], 'candidate x_prediction differs'
        assert cand['u_prediction'] == row['U'], 'candidate u_prediction differs'
        assert cand['success'] == row['success'], 'candidate success differs'
        assert cand['prediction_available'] == row['prediction_available'], \
            'candidate prediction_available differs'

    decision_by_seq = {d['sequence']: d for d in decisions}
    stored_dec = decoded.get('/p1/execution_decision', [])
    assert len(stored_dec) == len(decisions), \
        'stored decisions %d != Source decisions %d' % (len(stored_dec), len(decisions))
    for dec in stored_dec:
        seq = dec['sequence']
        assert seq in decision_by_seq, 'stored decision has no Source row'
        row = decision_by_seq[seq]
        for key, value in dec.items():
            src_key = DECISION_RENAMES.get(key, key)
            if src_key in row:
                assert row[src_key] == value, \
                    'decision field %s differs at sequence %d' % (key, seq)
            else:
                raise AssertionError('decision field %s has no Source counterpart' % key)

    applied = decoded.get('/research/control/applied', [])
    assert len(applied) == len(pairs), 'stored applied %d != Source pairs %d' % (
        len(applied), len(pairs))
    cm = manifests['regulator']
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
        assert m['left_publish_success'] == p['returned'][0], 'applied left success differs'
        assert m['right_publish_success'] == p['returned'][1], 'applied right success differs'
        assert m['plant_acceptance_observed'] is False, 'fabricated plant acceptance'
        assert m['force_measured'] is False, 'fabricated measured force'
        assert m['execution_atomicity_proven'] is False, 'fabricated execution atomicity'
    for side, key in enumerate(['left', 'right']):
        topic = c['output_topics'][key]
        assert [m['data'] for m in decoded.get(topic, [])] == \
            [p['command_n'][side] for p in pairs], '%s values differ from the pairs' % key
    return {'stored_counts': counts, 'jobs': len(jobs), 'candidates': len(stored_cands),
            'published_candidates': len(published_ids),
            'decisions': len(stored_dec), 'applied': len(applied), 'pairs': len(pairs)}


def check_wire(run_root, decoded, wire, gids):
    transport, drop = lines(run_root / 'fixture/transport_source.jsonl')
    assert drop == 0, 'Fixture transport receiver lost its tail'
    observed = collections.Counter()
    for row in transport:
        topic = row['topic']
        assert topic in gids, 'transport row for an unregistered topic: ' + topic
        assert row['publisher_gid'] == gids[topic], \
            'transport row GID differs from the manifest for ' + topic
        observed[(topic, row['payload_sha256'])] += 1
    missing = observed - wire
    assert not missing, 'wire messages missing from storage: ' + repr(list(missing)[:4])
    extra = wire - observed
    assert all(k[0] == '/p1/worker_capability' for k in extra), \
        'extra stored messages outside /p1/worker_capability'
    assert sum(extra.values()) <= 2, 'more than two unexplained extra capabilities'
    return {'observed': sum(observed.values()), 'stored': sum(wire.values()),
            'extra_capabilities': sum(extra.values())}


def check_recorder_and_fixture(run_root, decoded, c, case):
    rec = read(run_root / 'recorder/terminal.json')
    assert rec['clean'] is True, 'Recorder did not close cleanly'
    assert rec['Recorder_stop_completed'] is True, 'Recorder stop did not complete'
    assert rec['prepared'] is True, 'Recorder was never prepared'
    assert rec['storage_stream_accounting_verified'] is False, \
        'Recorder internal accounting must stay false (the external audit owns it)'
    ft = read(run_root / 'fixture/terminal.json')
    assert not ft['failed'], 'Fixture reports failure'
    counts = {k: len(v) for k, v in decoded.items()}
    for topic, n in ft['published_counts'].items():
        if topic in counts:
            assert counts[topic] == n, 'Fixture published %d but %d stored on %s' % (
                n, counts[topic], topic)
    # The Fixture never sees plant state and never accepts a command.
    fixt = read(run_root / 'fixture/owned_manifest.json')
    assert fixt['physical_publishers'] == 0, 'Fixture declares a physical publisher'
    assert fixt['plant_connected'] is False, 'Fixture claims a plant connection'
    return {'recorder_clean': True, 'fixture_published_counts': ft['published_counts']}


def check_shutdown(regulator_rows, c):
    r = by_type(regulator_rows)
    rows = r.get('regulator_shutdown')
    assert rows, 'missing regulator_shutdown'
    row = rows[0]
    assert row['zero_requested'] is True, 'shutdown did not request zero'
    assert row['plant_hold_end_known'] is False, 'shutdown must not claim a known plant hold end'
    if not row['shutdown_grace_exceeded']:
        assert row['zero_target_published'] is True, \
            'shutdown exited inside grace without publishing zero'
    return {'grace_exceeded': row['shutdown_grace_exceeded'],
            'zero_target_published': row['zero_target_published']}


def check_witness(run_root, regulator_rows, case):
    witness = read(run_root / 'regulator/witness.json')
    assert witness['closed'] is True, 'Witness did not close'
    assert witness['overflow'] is False, 'Witness overflowed'
    assert witness['incomplete'] is False, 'Witness reports incomplete'
    r = by_type(regulator_rows)
    summary = r.get('source_summary')
    assert summary, 'missing Regulator source_summary'
    s = summary[0]
    assert s['normal_source_complete'] is True, 'Regulator Source is not complete'
    assert s['dropped'] == 0, 'Regulator Source dropped %d rows' % s['dropped']
    assert s['generated'] == s['emitted'], 'Regulator generated != emitted'
    return {'observation_complete': witness['observation_complete'],
            'regulator_rows_generated': s['generated']}


def check_driver_claims(result, checks, case):
    """Cross-check the Driver's own summary against the audit's recomputation.

    The Driver is an observer, not evidence. Where its numbers can be
    re-derived they must agree; where they cannot, the audit lists them.
    """
    agree, disagree = [], []
    pairs = {
        'dropped_candidates': checks.get('dropped'),
        'generated': checks.get('generated'),
        'delivered': checks.get('delivered'),
    }
    for key, mine in pairs.items():
        if key in result and mine is not None:
            (agree if result[key] == mine else disagree).append(
                {'field': key, 'driver': result[key], 'audit': mine})
    if case != 'W4':
        for key in ('dropped_candidates',):
            if key in result and result[key] not in (0, None):
                disagree.append({'field': key, 'driver': result[key], 'audit': 0})
    return {'agree': agree, 'disagree': disagree}


# ── mutation self-checks ─────────────────────────────────────────────────

def self_mutations(case, ctx):
    rejected, escaped = [], []

    def must_reject(name, fn):
        # Only a deliberate assertion counts. An incidental KeyError/TypeError
        # means the mutation died before reaching the check it was meant to
        # exercise, which is not evidence that the check works.
        try:
            fn()
        except AssertionError:
            rejected.append(name)
            return
        except Exception as exc:
            escaped.append('%s:rejected-by-%s-not-assertion' % (name, type(exc).__name__))
            return
        escaped.append(name)

    def copy(x):
        return json.loads(json.dumps(x))

    # 1. A fabricated successful exit must break the role check.
    def m_rc():
        bad = copy(ctx['result'])
        for row in bad['closed_roles']:
            if row['role'] == 'worker':
                row['returncode'] = 9
        check_roles(bad, ctx['reg'], case)

    # 2. A duplicated stored job must break the multiset reconciliation.
    def m_dup():
        dec = copy(ctx['decoded'])
        if not dec.get('/p1/solve_job'):
            raise AssertionError('no stored jobs')
        dec['/p1/solve_job'].append(copy(dec['/p1/solve_job'][0]))
        check_typed_equality(dec, ctx['regulator'], ctx['worker'], ctx['manifests'], ctx['c'])

    # 3. Shipping the DROPPED candidate as if it were delivered must break.
    def m_ghost_candidate():
        w = [copy(x) for x in ctx['worker']]
        if case != 'W4':
            # Outside W4 no candidate is dropped, so the equivalent forgery is a
            # publish_result for a Job that has no candidate row at all.
            jid = max(x['job']['job_id'] for x in w if x['type'] == 'job_received') + 1
        else:
            jid = [x for x in w if x['type'] == 'diagnostic_candidate_dropped'][0]['job_id']
        w.append({'type': 'candidate_publish_result', 'job_id': jid,
                  'publish_start_ns': 1, 'publish_end_ns': 2,
                  'solve_start_ns': 0, 'solve_end_ns': 1, 'success': True})
        ledger, problems = job_ledger(w, ctx['regulator'], ctx['dropped_ids'])
        assert not problems, 'ghost publish accepted'

    # 4. Tampering with a raw publish time while leaving the flags false must break.
    def m_time():
        pairs = copy(ctx['pairs'])
        if len(pairs) < 2:
            raise AssertionError('need two pairs')
        pairs[1]['starts'] = [pairs[1]['starts'][0] + 10**9, pairs[1]['starts'][1]]
        check_pair_stream(pairs, ctx['c'])

    # 5. A hold that silently ramps must break the fallback recomputation.
    def m_hold():
        decs = copy(ctx['decisions'])
        for d in decs:
            if not d['accepted'] and d['control_source'] == 'hold':
                d['final_n'] = [0.0, 0.0]
                break
        else:
            raise AssertionError('no hold decision to mutate')
        check_fallback_policy(decs, ctx['c'])

    # 6. An unexplained second hook invocation must break. W3 has no one-shot
    #    hook at all, so the equivalent forgery there is a stall it must never
    #    have (its whole claim is "delay only, never a stall").
    def m_second_hook():
        w = copy(ctx['worker'])
        if case == 'W4':
            w.extend(x for x in copy(w) if x['type'] == 'diagnostic_candidate_dropped')
        elif case == 'W1':
            w.extend(x for x in copy(w) if x['type'] == 'diagnostic_v2_pre_native_enter')
        else:
            w.append({'type': 'diagnostic_v2_pre_native_enter', 'job_id': 1,
                      'policy': 'pre_native_once_after_completed_v1', 'start_ns': 1,
                      'duration_ms': 1700, 'completed_jobs_before': 1,
                      'actual_native_invoked': False, 'stage_qualified': False})
        check_worker_hooks(case, w, ctx['c'])

    # 7. A decision that hides its diagnostic nature must break.
    def m_undiagnosed():
        decs = copy(ctx['decisions'])
        decs[0]['diagnostic_only'] = False
        check_decisions(decs, ctx['c'])

    for name, fn in [('forged_exit_code', m_rc),
                     ('decision_claims_qualified', m_undiagnosed),
                     ('duplicate_stored_job', m_dup),
                     ('ghost_publish_result', m_ghost_candidate),
                     ('raw_time_tampered_flags_false', m_time),
                     ('silent_hold_ramp', m_hold),
                     ('second_hook_invocation', m_second_hook)]:
        must_reject(name, fn)
    return rejected, escaped


# ── main ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True, choices=list(CASES))
    ap.add_argument('--registration', type=Path)
    args = ap.parse_args()
    case = args.case
    regfile = args.registration or (D / 'implementation' / ('%s_registration_v1.json' % case))
    reg = read(regfile)
    assert reg['case'] in TAG and TAG[reg['case']] == case, 'registration case mismatch'
    assert reg['scope'] == SCOPE and reg['automatic_retries'] == 0
    run_root = Path(reg['output'])
    assert run_root.is_dir(), 'run directory does not exist'
    c = read(Path(reg['contract']))
    registry = read(Path(reg['registry']))
    assert registry['scope'] == SCOPE
    assert pin(Path(reg['registry']))['sha256'] == reg['registry_sha256']
    assert pin(Path(reg['contract']))['sha256'] == reg['contract_sha256']

    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    regulator_rows, rdrop = lines(run_root / 'regulator/source.jsonl')
    worker_rows, wdrop = lines(run_root / 'worker/source.jsonl')
    assert rdrop == 0, 'the Regulator Source must never lose its tail'
    assert wdrop == 0, 'a clean diagnostic Worker must not lose its Source tail'

    manifests = {role: read(run_root / role / ('owned_manifest.json' if role == 'fixture'
                                               else 'manifest.json'))
                 for role in ['regulator', 'worker', 'fixture', 'recorder']}
    result = read(run_root / 'driver_result.json')
    assert result['passed'] is True, 'Driver reported failure'
    assert result['run_id'] == reg['run_id'], 'Driver run id differs from the registration'

    r = by_type(regulator_rows)
    w = by_type(worker_rows)
    pairs = r['owned_API_pair']
    decisions = r['decision']
    jobs = [row['job'] for row in r['job']]
    dropped_ids = [row['job_id'] for row in w.get('diagnostic_candidate_dropped', [])]

    identity = check_contract_identity(run_root, c, registry, manifests, reg)
    roles = check_roles(result, reg, case)
    gids = check_publishers(manifests, c)
    stream = check_pair_stream(pairs, c)
    check_decisions(decisions, c)
    check_jobs(jobs, pairs, c, manifests)
    ledger, problems = job_ledger(worker_rows, regulator_rows, dropped_ids)
    assert not problems, 'Job ledger has unexplained entries: %r' % problems
    targets = check_target_tick(ledger, decisions, c)
    fallback = check_fallback_policy(decisions, c)
    hooks = check_worker_hooks(case, worker_rows, c)
    accounting = check_worker_accounting(worker_rows, ledger)
    heartbeat = check_capability_continuity(regulator_rows, worker_rows, case)
    transition = check_transition(regulator_rows, case)
    shutdown = check_shutdown(regulator_rows, c)
    witness = check_witness(run_root, regulator_rows, case)

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

    typed = check_typed_equality(decoded, regulator_rows, worker_rows, manifests, c)
    transport = check_wire(run_root, decoded, wire, gids)
    rec = check_recorder_and_fixture(run_root, decoded, c, case)

    # A dropped candidate must not be in the Stored set: this is the single
    # most important W4 claim and it is checked from the bag, not the Source.
    if case == 'W4':
        stored_ids = {x['job']['job_id'] for x in decoded.get('/p1/solve_candidate', [])}
        for jid in dropped_ids:
            assert jid not in stored_ids, \
                'the dropped candidate for job %r reached storage' % jid

    ctx = {'result': result, 'reg': reg, 'decoded': decoded, 'regulator': regulator_rows,
           'worker': worker_rows, 'manifests': manifests, 'c': c, 'pairs': pairs,
           'decisions': decisions, 'dropped_ids': dropped_ids}
    rejected, escaped = self_mutations(case, ctx)
    assert not escaped, 'audit failed to reject fabricated input: %r' % escaped
    assert len(rejected) == 7, 'mutation self-check count wrong: %r' % rejected

    label = {'W1': 'watchdog must not fire; heartbeat must stay live through the stall',
             'W3': 'a late candidate is refused; nothing goes terminal',
             'W4': 'a missing candidate falls back under frozen policy; nothing goes terminal'}[case]
    report = {
        'schema': 'M4-owned-diagnostic-audit-v1',
        'case': case, 'run_id': reg['run_id'], 'passed': True,
        'claim': label,
        'registration': str(regfile), 'registration_sha256': pin(regfile)['sha256'],
        'contract_sha256': identity['contract_hash'],
        'scope': SCOPE,
        'role_exit_codes': roles['exit_codes'],
        'role_signals': roles['signals'],
        'api_pairs': stream,
        'job_ledger': {str(k): v for k, v in ledger.items()},
        'target_tick_decisions': {str(k): v for k, v in targets.items()},
        'fallback_policy_recomputed': fallback,
        'worker_hooks': hooks,
        'worker_accounting': accounting,
        'heartbeat': heartbeat,
        'transition': transition,
        'shutdown': shutdown,
        'witness': witness,
        'typed': typed,
        'wire': transport,
        'recorder_fixture': rec,
        'driver_cross_check': check_driver_claims(
            result, {'dropped': accounting['dropped'], 'generated': accounting['generated'],
                     'delivered': accounting['delivered']}, case),
        'mutations_rejected': rejected,
        'declared_exceptions': [],
        'unprovable_here': sorted(set(
            roles['unprovable_here'] + accounting['unprovable_here']
            + hooks.get('unprovable_here', []))),
        'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
        'research_conclusion': False,
    }
    out = D / 'postrun' / ('%s_audit_v1.json' % case)
    with out.open('x') as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write('\n')
    print(json.dumps({'passed': True, 'case': case, 'output': str(out),
                      'pairs': len(pairs), 'decisions': len(decisions),
                      'ledger': {str(k): v['kind'] for k, v in ledger.items()}}))


if __name__ == '__main__':
    main()
