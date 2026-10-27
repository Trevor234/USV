#!/usr/bin/env python3
"""RNW pure audit v2 (batch 126 derivation; fixes F124-02 / R-RNW-01 / R-RNW-02).

Four INDEPENDENT outputs, never merged into one `passed`:
    r4_observed      -- did one same-Job full real chain actually occur?
    run_accepted     -- do ALL registered mandatory gates hold for the run?
    coverage         -- per gate: covered / not_covered / not_applicable_absent
    stage_qualified  -- always False here; stage qualification is never granted
                       by an offline audit.

Batch-117 defects this fixes:
  * `audit_rnw_run` returned `passed = r4 clause only`, so deleting driver close
    evidence, all clock rows or a bad generation value still passed.
  * R4 matched on job_id / sequence alone: a foreign-run candidate with an old
    schedule and a reversed chain both passed. Identity is now the full echo plus
    the generation binding, and causality uses the real logical commit fields,
    not the order of lines in the file (the true RNW3 Source writes API/Applied
    BEFORE the final Decision line, which is legal).

No ROS, no subprocess, no writes. Pure functions over parsed rows.
"""
import json
from pathlib import Path

PAUSE_CONFIRM_NS = 400_000_000

REQUIRED_CLOSED_ROLES = {'regulator', 'fixture', 'worker', 'recorder'}

# Identity echo fields, DECLARED PER COMPARISON rather than intersected. An
# intersection would silently stop checking a field the moment one source drops
# it from its schema; a declared field that is missing is a coverage gap.
# Confirmed against the real T3-T2A-RNW3 regulator Source schema:
#   job / candidate_registration carry both `clock_epoch` and `nominal_hash`;
#   decision carries `epoch` (not `clock_epoch`) and no `nominal_hash`/`target_tick`.
ECHO_JOB_CANDIDATE = ('job_id', 'run_id', 'boot_id', 'task_generation', 'model_generation',
                      'config_generation', 'schedule_generation', 'clock_epoch',
                      'contract_hash', 'nominal_hash', 'target_tick', 'worker_instance')
ECHO_JOB_DECISION = (('job_id', 'job_id'), ('run_id', 'run_id'), ('boot_id', 'boot_id'),
                     ('task_generation', 'task_generation'), ('model_generation', 'model_generation'),
                     ('config_generation', 'config_generation'),
                     ('schedule_generation', 'schedule_generation'),
                     ('clock_epoch', 'epoch'), ('contract_hash', 'contract_hash'),
                     ('worker_instance', 'worker_instance'))


# ------------------------------------------------------------------ utilities
def rows_of(path):
    out, parse_errors = [], 0
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            parse_errors += 1
    return out, parse_errors


def gate(name, passed, coverage, detail=None):
    """One gate. `passed` must be a real bool; coverage states evidence scope."""
    if type(passed) is not bool:
        raise TypeError(f'gate {name}: passed must be bool, got {type(passed).__name__}')
    return {'gate': name, 'passed': passed, 'coverage': coverage, 'detail': detail}


def _job_of(row):
    j = row.get('job')
    return j if isinstance(j, dict) else {}


def _echo(row):
    """Flatten the identity echo of one row (job dict if present, else top level)."""
    j = _job_of(row)
    return j if j else row


def echo_mismatches(left, right, pairs):
    """Compare declared (left_key, right_key) pairs. A missing field is a gap, not a pass."""
    diffs, missing = {}, []
    for lk, rk in pairs:
        lv, rv = left.get(lk), right.get(rk)
        if lv is None or rv is None:
            missing.append({'field': f'{lk}->{rk}', 'left': lv, 'right': rv})
        elif lv != rv:
            diffs[f'{lk}->{rk}'] = (lv, rv)
    return diffs, missing


# --------------------------------------------------------------- run-level gates
def audit_close(run_dir):
    """Four roles spawned once, closed cleanly, groups empty."""
    rp = Path(run_dir) / 'driver_result.json'
    ep = Path(run_dir) / 'driver_events.jsonl'
    if not rp.is_file() or not ep.is_file():
        missing = [str(p) for p in (rp, ep) if not p.is_file()]
        return [gate('close.evidence_present', False, 'not_covered', {'missing': missing})]
    result = json.loads(rp.read_bytes())
    events, parse_errors = rows_of(ep)
    closed = result.get('closed_roles', [])
    roles = [r.get('role') for r in closed]
    spawns = [e.get('role') for e in events if e.get('type') == 'role_spawned']
    gates = [
        # Emitted on success too: a failure-only gate leaves an "absent" hole that
        # would be indistinguishable from a deleted check.
        gate('close.evidence_present', True, 'covered',
             {'driver_result': str(rp), 'driver_events': str(ep)}),
        gate('close.events_parse_clean', parse_errors == 0,
             'covered' if parse_errors == 0 else 'not_covered', {'parse_errors': parse_errors}),
        gate('close.four_exact_roles_closed',
             len(closed) == 4 and set(roles) == REQUIRED_CLOSED_ROLES
             and all(r.get('returncode') == 0 and r.get('group_empty') is True for r in closed),
             'covered',
             {r.get('role'): {'rc': r.get('returncode'), 'empty': r.get('group_empty')} for r in closed}),
        gate('close.exactly_one_spawn_per_role',
             len(spawns) == 4 and set(spawns) == REQUIRED_CLOSED_ROLES, 'covered', spawns),
        gate('close.no_restart_events',
             not [e for e in events if any(k in str(e.get('type', '')) for k in ('restart', 'respawn', 'retry'))],
             'covered'),
    ]
    # Driver self-report is recorded, never a gate of its own.
    gates.append(gate('close.driver_selfreport_recorded_only', True, 'covered',
                      {'driver_passed': result.get('passed')}))
    return gates


def audit_pause(src):
    """Clock silence beyond the confirm bound, with a schedule transition."""
    clocks = [r for r in src if r.get('type') == 'clock']
    if len(clocks) < 3:
        return [gate('pause.confirmed', False, 'not_covered', {'clock_events': len(clocks)})]
    rxs = [r['receive_ns'] for r in clocks]
    sims = [r['sim_ns'] for r in clocks]
    gi = max(range(1, len(rxs)), key=lambda i: rxs[i] - rxs[i - 1])
    gap = rxs[gi] - rxs[gi - 1]
    epochs = sorted({r.get('epoch') for r in clocks})
    schedules = sorted({r.get('schedule_generation') for r in clocks})
    regressions = sum(1 for i in range(1, len(sims)) if sims[i] < sims[i - 1])
    return [
        gate('pause.confirmed', gap > PAUSE_CONFIRM_NS, 'covered',
             {'wall_gap_ns': gap, 'pause_confirm_ns': PAUSE_CONFIRM_NS, 'clock_events': len(clocks)}),
        gate('pause.silence_exceeds_confirm_bound', gap > PAUSE_CONFIRM_NS, 'covered',
             {'wall_gap_ns': gap, 'pause_confirm_ns': PAUSE_CONFIRM_NS}),
        gate('pause.raw_clock_monotonic', regressions == 0, 'covered',
             {'adjacent_regressions': regressions}),
        gate('pause.clock_epoch_unchanged_is_legal', epochs == [0], 'covered', {'epochs': epochs}),
        gate('pause.schedule_transition_observed', len(schedules) >= 2, 'covered',
             {'schedule_generations': schedules}),
    ]


def audit_generation(src):
    """One scoped generation open, and two commits with genuinely different binding."""
    committed = [r for r in src if r.get('type') == 'reference_epoch_committed']
    opened = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
    gates = []
    if not opened:
        gates.append(gate('generation.scoped_open', False, 'not_covered', {'opened_events': 0}))
    else:
        o = opened[0]
        gates.append(gate('generation.scoped_open', True, 'covered',
                          {'opened_events': len(opened), 'generation': o.get('generation'),
                           'opened_ns': o.get('opened_ns')}))
        gates.append(gate(
            'generation.single_open_from_terminal',
            len(opened) == 1 and o.get('generation') == 2
            and o.get('previous_terminal_reason') == 'epoch_binding_changed'
            and o.get('previous_first_job_id', 0) >= 1 and o.get('previous_last_job_id', 0) >= 1,
            'covered' if len(opened) == 1 else 'not_covered',
            {k: o.get(k) for k in ('generation', 'previous_generation', 'previous_terminal_reason',
                                   'previous_first_job_id', 'previous_last_job_id')}))
    if len(committed) == 2:
        e1, e2 = (c.get('reference_epoch') or {} for c in committed)
        # The generation NUMBER always differs and must never be the compared field
        # (batch 105's tautology). Compare the binding identity that can actually
        # differ between two generations, and require at least one real difference.
        binding_keys = ('task_generation', 'model_generation', 'config_generation',
                        'schedule_generation', 'clock_epoch', 'path_fingerprint',
                        'profile_fingerprint', 'run_id', 'boot_id', 'nominal_hash')
        diffs = {k: (e1.get(k), e2.get(k)) for k in binding_keys if e1.get(k) != e2.get(k)}
        same_generation_numbers = [e1.get('generation'), e2.get('generation')]
        gates.append(gate(
            'generation.two_commits_distinct_binding',
            same_generation_numbers == [1, 2] and bool(diffs),
            'covered',
            {'generations': same_generation_numbers, 'binding_differences': diffs,
             'compared_fields_exclude_generation_number': True}))
    else:
        gates.append(gate('generation.two_commits_distinct_binding', False, 'not_covered',
                          {'committed': len(committed)}))
    return gates


# ---------------------------------------------------------------- R4 (positive)
def audit_r4(src, target_job=None):
    """One same-Job chain: submit -> accepted candidate -> accepted candidate-sourced
    Decision -> real API pair -> Applied, bound by full identity AND logical time.

    `target_job` pins the question to ONE registered job (the doc requires the
    comparison to be made for the same target Job). With target_job=None the
    question is "does any job in the opened generation complete the chain".

    Population selection uses the OPEN's logical timestamp, never list position:
    a legal Source may write the final Decision line after the API/Applied lines,
    and a private copy may be reordered for testing. Position-based slicing made
    both of those produce false verdicts.
    """
    opened = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
    if not opened:
        return gate('r4.same_job_full_chain', False, 'not_covered',
                    {'reason': 'no_scoped_open'}), None
    open_ns = opened[0].get('opened_ns')
    if not isinstance(open_ns, int):
        return gate('r4.same_job_full_chain', False, 'not_covered',
                    {'reason': 'open_event_has_no_logical_timestamp'}), None
    open_gen = opened[0].get('generation')

    # Candidates: jobs whose submit completion is strictly after the open.
    jobs_after = [r for r in src if r.get('type') == 'job' and isinstance(r.get('job'), dict)
                  and isinstance(r.get('submit_commit_ns'), int) and r['submit_commit_ns'] > open_ns]
    if target_job is not None:
        jobs_after = [r for r in jobs_after if r['job'].get('job_id') == target_job]
    jobs_after.sort(key=lambda r: r['submit_commit_ns'])
    # Same-identity duplication is a named rejection: two `job` rows for one job_id,
    # or two candidate/decision events for it, mean the stream is mixed or doubled
    # and cannot be read as one real chain.
    submit_ids = [r['job'].get('job_id') for r in jobs_after]
    duplicate_submits = sorted({i for i in submit_ids if submit_ids.count(i) > 1})
    if duplicate_submits:
        return gate('r4.same_job_full_chain', False, 'covered',
                    {'reason': 'duplicate_job_events_for_same_id',
                     'job_ids': duplicate_submits}), None
    attempts = []
    for jr in jobs_after:
        jid = jr['job'].get('job_id')
        job_echo = _echo(jr)
        # the Job must carry the NEW generation binding opened above
        epoch_of_job = jr.get('reference_epoch') or {}
        if epoch_of_job.get('generation') != open_gen:
            attempts.append({'job_id': jid, 'reason': 'job_not_in_opened_generation',
                             'observed': epoch_of_job.get('generation'), 'expected': open_gen})
            continue
        submit_ns = jr['submit_commit_ns']

        cands = [r for r in src if r.get('type') == 'candidate_registration'
                 and _job_of(r).get('job_id') == jid]
        if not cands:
            attempts.append({'job_id': jid, 'reason': 'no_candidate_registration'})
            continue
        cand = cands[0]
        cand_echo = _echo(cand)
        if len(cands) > 1:
            attempts.append({'job_id': jid, 'reason': 'duplicate_candidate_registrations',
                             'count': len(cands)})
            continue
        echo_diffs, echo_missing = echo_mismatches(
            job_echo, cand_echo, [(k, k) for k in ECHO_JOB_CANDIDATE])
        if echo_missing:
            attempts.append({'job_id': jid, 'reason': 'candidate_echo_field_missing',
                             'missing': echo_missing})
            continue
        if echo_diffs:
            attempts.append({'job_id': jid, 'reason': 'candidate_echo_mismatch', 'diffs': echo_diffs})
            continue
        if cand.get('accepted_registration') is not True:
            attempts.append({'job_id': jid, 'reason': 'candidate_not_accepted',
                             'candidate_reason': cand.get('reason')})
            continue
        ready_ns = cand.get('ready_commit_ns')

        decs = [r for r in src if r.get('type') == 'decision' and r.get('job_id') == jid
                and r.get('accepted') is True and r.get('control_source') == 'candidate']
        if not decs:
            observed = [{'accepted': r.get('accepted'), 'control_source': r.get('control_source')}
                        for r in src if r.get('type') == 'decision' and r.get('job_id') == jid]
            attempts.append({'job_id': jid, 'reason': 'no_accepted_candidate_sourced_decision',
                             'observed_decisions': observed[:4]})
            continue
        dec = decs[0]
        dec_echo = _echo(dec)
        dec_diffs, dec_missing = echo_mismatches(job_echo, dec_echo, ECHO_JOB_DECISION)
        if dec_missing:
            attempts.append({'job_id': jid, 'reason': 'decision_echo_field_missing',
                             'missing': dec_missing})
            continue
        if dec_diffs:
            attempts.append({'job_id': jid, 'reason': 'decision_echo_mismatch', 'diffs': dec_diffs})
            continue
        seq = dec.get('sequence')
        activation_ns = dec.get('activation_commit_ns')

        pairs = [r for r in src if r.get('type') == 'owned_API_pair'
                 and r.get('sequence') == seq and r.get('returned') == [True, True]]
        if not pairs:
            attempts.append({'job_id': jid, 'reason': 'no_real_api_pair_for_decision_sequence',
                             'sequence': seq})
            continue
        pair = pairs[0]
        applieds = [r for r in src if r.get('type') == 'owned_applied_publication'
                    and r.get('sequence') == seq]
        if not applieds:
            attempts.append({'job_id': jid, 'reason': 'no_applied_for_sequence', 'sequence': seq})
            continue
        applied = applieds[0]

        # ---- logical-time causality from fields, never from line order
        starts = pair.get('starts') or []
        api_left_ns = starts[0] if starts else None
        applied_left_ns = applied.get('left_start')
        times = {'submit': submit_ns, 'ready': ready_ns, 'activation': activation_ns,
                 'api_left_start': api_left_ns, 'applied_left_start': applied_left_ns}
        missing = [k for k, v in times.items() if not isinstance(v, int)]
        if missing:
            attempts.append({'job_id': jid, 'reason': 'logical_time_field_missing',
                             'missing': missing})
            continue
        ordered = (times['submit'] < times['ready'] < times['activation']
                   and times['activation'] <= times['api_left_start'])
        same_left = api_left_ns == applied_left_ns
        if not ordered:
            attempts.append({'job_id': jid, 'reason': 'logical_time_order_violated', 'times': times})
            continue
        if not same_left:
            attempts.append({'job_id': jid, 'reason': 'api_and_applied_left_start_disagree',
                             'api_left': api_left_ns, 'applied_left': applied_left_ns})
            continue
        if applied.get('control_source') != 'candidate':
            attempts.append({'job_id': jid, 'reason': 'applied_control_source_not_candidate',
                             'observed': applied.get('control_source')})
            continue

        g = gate('r4.same_job_full_chain', True, 'covered', {
            'job_id': jid, 'decision_sequence': seq, 'opened_generation': open_gen,
            'identity_echo_job_candidate': {k: job_echo.get(k) for k in ECHO_JOB_CANDIDATE},
            'identity_echo_decision': {lk: dec_echo.get(rk) for lk, rk in ECHO_JOB_DECISION},
            'candidate_accepted': True, 'control_source': 'candidate',
            'api_returned': [True, True], 'applied_sequence': seq,
            'logical_times': times,
            'ordered_submit_ready_activation_api': ordered,
            'api_equals_applied_left_start': same_left,
            'population_selected_by': 'open logical timestamp (opened_ns), not list position',
        })
        return g, {'job_id': jid, 'sequence': seq, 'times': times}
    if not jobs_after:
        attempts.append({'reason': 'no_jobs_submitted_after_open'})
    return gate('r4.same_job_full_chain', False, 'not_covered',
                {'reason': 'no_complete_chain', 'attempted': attempts[:6]}), None


def audit_r4_negative_variants(src):
    """Run the R4 function over private mutated copies of the same stream.

    Each counterexample MUST fail R4. Mutations are anchored on the chain the
    baseline R4 actually accepts (the first accepted chain after the open), so a
    mutation cannot silently miss its target.  In-memory copies only.
    """
    import copy
    results = {}
    g, fact = audit_r4(src)
    if not fact:
        return {'baseline': {'r4_passed': g['passed'], 'reason': 'no_baseline_chain',
                             'note': 'variants are meaningless without an accepted baseline chain'}}
    target_jid, target_seq = fact['job_id'], fact['sequence']

    def run_variant(name, mutate):
        rows = copy.deepcopy(src)
        applied = mutate(rows)
        gv, _ = audit_r4(rows, target_job=target_jid)
        results[name] = {'r4_passed': gv['passed'],
                         'reason': (gv.get('detail') or {}).get('reason'),
                         'coverage': gv['coverage'],
                         'mutation_applied': applied}

    def pick(rows, typ, match=None):
        """Return the first row of `typ` matching the predicate, else mutate reports False."""
        for r in rows:
            if r.get('type') == typ and (match is None or match(r)):
                return r
        return None

    def by_job(jid):
        return lambda r: _job_of(r).get('job_id') == jid

    def by_seq(seq):
        return lambda r: r.get('sequence') == seq

    run_variant('baseline_identity', lambda rows: True)

    def foreign_run(rows):
        r = pick(rows, 'candidate_registration', by_job(target_jid))
        if not r:
            return False
        r['job']['run_id'] = 'FOREIGN-RUN'
        return True
    run_variant('foreign_run_echo', foreign_run)

    def old_schedule(rows):
        r = pick(rows, 'candidate_registration', by_job(target_jid))
        if not r:
            return False
        r['job']['schedule_generation'] = 1
        return True
    run_variant('old_schedule_echo', old_schedule)

    def wrong_generation(rows):
        r = pick(rows, 'reference_epoch_generation_opened')
        if not r:
            return False
        r['generation'] = 99
        return True
    run_variant('wrong_generation', wrong_generation)

    def ready_before_submit(rows):
        c = pick(rows, 'candidate_registration', by_job(target_jid))
        j = pick(rows, 'job', by_job(target_jid))
        if not c or not j:
            return False
        c['ready_commit_ns'] = j['submit_commit_ns'] - 1
        return True
    run_variant('ready_before_submit', ready_before_submit)

    def activation_before_ready(rows):
        c = pick(rows, 'candidate_registration', by_job(target_jid))
        d = pick(rows, 'decision', lambda r: r.get('job_id') == target_jid)
        if not c or not d:
            return False
        d['activation_commit_ns'] = c['ready_commit_ns'] - 1
        return True
    run_variant('activation_before_ready', activation_before_ready)

    def api_before_activation(rows):
        d = pick(rows, 'decision', lambda r: r.get('job_id') == target_jid)
        if not d:
            return False
        early = d['activation_commit_ns'] - 2
        changed = False
        for r in rows:
            if r.get('type') == 'owned_API_pair' and r.get('sequence') == target_seq:
                r['starts'][0] = early
                changed = True
            if r.get('type') == 'owned_applied_publication' and r.get('sequence') == target_seq:
                r['left_start'] = early
                changed = True
        return changed
    run_variant('api_before_activation', api_before_activation)

    def reversed_chain(rows):
        rows.reverse()
        return True
    run_variant('file_order_reversed_still_legal', reversed_chain)

    def rejected_candidate(rows):
        r = pick(rows, 'candidate_registration', by_job(target_jid))
        if not r:
            return False
        r['accepted_registration'] = False
        return True
    run_variant('rejected_candidate', rejected_candidate)

    def fallback_only(rows):
        r = pick(rows, 'decision', lambda r: r.get('job_id') == target_jid)
        if not r:
            return False
        r['control_source'] = 'fallback'
        return True
    run_variant('fallback_only', fallback_only)

    def partial_api(rows):
        r = pick(rows, 'owned_API_pair', by_seq(target_seq))
        if not r:
            return False
        r['returned'] = [True, False]
        return True
    run_variant('partial_api', partial_api)

    def no_applied(rows):
        r = pick(rows, 'owned_applied_publication', by_seq(target_seq))
        if not r:
            return False
        r['type'] = 'owned_applied_publication_renamed'
        return True
    run_variant('missing_applied', no_applied)

    def wrong_applied_source(rows):
        r = pick(rows, 'owned_applied_publication', by_seq(target_seq))
        if not r:
            return False
        r['control_source'] = 'ramp_zero'
        return True
    run_variant('applied_source_not_candidate', wrong_applied_source)
    return results


# ------------------------------------------------------- old-candidate coverage
def audit_old_candidates(src):
    """Old in-flight candidates must not silently revive. Absence is NOT rejection."""
    opened = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
    if not opened:
        return gate('old_candidates.disposition', False, 'not_covered', {'reason': 'no_scoped_open'})
    open_index = src.index(opened[0])
    before, after = src[:open_index], src[open_index:]
    pre = [r for r in before if r.get('type') == 'candidate_registration']
    if not pre:
        return gate('old_candidates.disposition', True, 'not_applicable_absent',
                    {'pre_open_candidates': 0,
                     'note': 'absent evidence is recorded, never counted as rejection'})
    pre_ids = {_job_of(r).get('job_id') for r in pre}
    rejected = [r for r in after if r.get('type') in ('job_not_submitted', 'candidate_rejected')
                and r.get('job_id') in pre_ids]
    return gate('old_candidates.disposition', bool(rejected),
                'covered' if rejected else 'not_covered',
                {'pre_open_candidates': len(pre), 'rejection_events': len(rejected)})


def audit_jobs_monotonic(src):
    ids = [r['job']['job_id'] for r in src if r.get('type') == 'job' and isinstance(r.get('job'), dict)]
    return gate('jobs.strictly_monotonic', ids == sorted(ids) and len(set(ids)) == len(ids),
                'covered', {'count': len(ids)})


# ------------------------------------------------------------------ public API
# Gates that must hold for run acceptance. Kept as names for reporting only; the
# acceptance decision is computed from actual gate state (fail OR not_covered
# blocks), so a renamed or newly added gate can never silently drop out of the gate.
ACCEPTANCE_GATES = (
    'source.parse_clean',
    'close.evidence_present',
    'close.events_parse_clean',
    'close.four_exact_roles_closed',
    'close.exactly_one_spawn_per_role',
    'close.no_restart_events',
    'pause.confirmed',
    'pause.silence_exceeds_confirm_bound',
    'pause.raw_clock_monotonic',
    'pause.clock_epoch_unchanged_is_legal',
    'pause.schedule_transition_observed',
    'generation.scoped_open',
    'generation.single_open_from_terminal',
    'generation.two_commits_distinct_binding',
    'jobs.strictly_monotonic',
    'r4.same_job_full_chain',
)
# Conditional gates: recorded, never blocking. Absence must not become evidence.
CONDITIONAL = ('old_candidates.disposition',)


def audit_rnw_run(run_dir, with_variants=False, target_job=None):
    """Audit one run. Returns the four dimensions separately.

    Acceptance is computed from ACTUAL gate state over ACCEPTANCE_GATES: a gate
    that is absent is a not_covered gap and also blocks. That makes a deleted or
    renamed gate fail closed instead of silently leaving the acceptance set.
    """
    run_dir = Path(run_dir)
    sp = run_dir / 'regulator/source.jsonl'
    if not sp.is_file():
        return {'run_dir': str(run_dir),
                'r4_observed': {'passed': False, 'coverage': 'not_covered',
                                'detail': {'reason': 'regulator_source_missing'}},
                'run_accepted': {'accepted': False, 'reason': 'regulator_source_missing',
                                 'blockers': ['regulator_source_missing']},
                'coverage': {'gates': {}, 'not_covered': list(ACCEPTANCE_GATES)},
                'stage_qualified': False}
    src, parse_errors = rows_of(sp)
    gates = [gate('source.parse_clean', parse_errors == 0,
                  'covered' if parse_errors == 0 else 'not_covered',
                  {'parse_errors': parse_errors, 'rows': len(src)})]
    if parse_errors == 0:
        gates += audit_close(run_dir)
        gates += audit_pause(src)
        gates += audit_generation(src)
        gates += [audit_old_candidates(src)]
        gates += [audit_jobs_monotonic(src)]

    r4_gate, r4_fact = audit_r4(src, target_job=target_job)
    gates.append(r4_gate)

    by_name = {g['gate']: g for g in gates}

    def state(name):
        g = by_name.get(name)
        if g is None:
            return 'absent'
        if g['coverage'] == 'not_covered':
            return 'not_covered'
        return 'pass' if g['passed'] else 'fail'

    gate_states = {n: state(n) for n in ACCEPTANCE_GATES}
    blockers = [n for n, s in gate_states.items()
                if s in ('absent', 'not_covered', 'fail')]
    conditional_states = {n: state(n) for n in CONDITIONAL}

    coverage = {g['gate']: g['coverage'] for g in gates}
    run_accepted = {
        'accepted': not blockers,
        'acceptance_gates': len(ACCEPTANCE_GATES),
        'gate_states': gate_states,
        'blockers': blockers,
        'conditional_states_recorded_not_blocking': conditional_states,
        'distinct_from_r4_observation': True,
        'rule': 'acceptance requires EVERY acceptance gate in state pass; R4 alone is not acceptance',
    }
    out = {
        'run_dir': str(run_dir),
        'rows': len(src),
        'r4_observed': {'passed': r4_gate['passed'], 'coverage': r4_gate['coverage'],
                        'detail': r4_gate['detail'], 'fact': r4_fact},
        'run_accepted': run_accepted,
        'coverage': {'gates': coverage,
                     'required_gates_present': [n for n, s in gate_states.items() if s != 'absent'],
                     'required_gates_absent': [n for n, s in gate_states.items() if s == 'absent']},
        'gates': gates,
        'stage_qualified': False,
    }
    if with_variants:
        out['negative_variants'] = audit_r4_negative_variants(src)
    return out


def summarise(result):
    return {
        'r4_observed': result['r4_observed']['passed'],
        'run_accepted': result['run_accepted']['accepted'],
        'blockers': result['run_accepted'].get('failed_required', [])
                    + result['run_accepted'].get('not_covered_required', []),
        'stage_qualified': result['stage_qualified'],
    }
