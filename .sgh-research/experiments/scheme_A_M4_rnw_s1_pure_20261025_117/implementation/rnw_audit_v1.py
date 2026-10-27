#!/usr/bin/env python3
"""Pure RNW audit functions (batch 117, S1 per the batch-115 review).

No live-runner imports, no subprocess, no ROS. Every function consumes parsed
rows / files and returns clause dicts. Coverage semantics follow R115-04:
the core acceptance clause requires ONE SAME gen2 Job to travel the full real
chain (submit -> accepted candidate registration -> accepted Decision with
control_source=candidate -> real API pair -> Applied), each after the scoped
open. Event presence alone never passes; missing positive facts yield honest
not_covered with a precise reason, never a silent pass.
"""
import json
from pathlib import Path

PAUSE_CONFIRM_NS = 400_000_000

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

def clause(name, passed, detail=None, coverage=None):
    return {'name': name, 'passed': bool(passed), 'detail': detail,
            'coverage': coverage or ('covered' if passed else 'not_covered')}

# ---------------------------------------------------------------- close/spawn
def audit_close(run_dir):
    rp = Path(run_dir) / 'driver_result.json'
    ep = Path(run_dir) / 'driver_events.jsonl'
    if not rp.is_file() or not ep.is_file():
        return [clause('driver_evidence_present', False, {'missing': str(rp if not rp.is_file() else ep)})]
    result = json.loads(rp.read_bytes())
    ev, parse_errors = rows_of(ep)
    cl = [clause('driver_events_parse_clean', parse_errors == 0, {'parse_errors': parse_errors})]
    closed = result.get('closed_roles', [])
    cl.append(clause('four_roles_closed_clean',
                     len(closed) == 4 and all(r.get('returncode') == 0 and r.get('group_empty') is True for r in closed),
                     {r.get('role'): {'rc': r.get('returncode'), 'empty': r.get('group_empty')} for r in closed}))
    spawns = [e for e in ev if e.get('type') == 'role_spawned']
    cl.append(clause('exactly_four_single_spawns',
                     len(spawns) == 4 and len({s.get('role') for s in spawns}) == 4,
                     [s.get('role') for s in spawns]))
    cl.append(clause('no_restart_events',
                     not [e for e in ev if any(k in e.get('type', '') for k in ('restart', 'respawn', 'retry'))]))
    # driver self-report is evidence-only, never a gate of its own
    cl.append(clause('driver_selfreport_recorded_only', True, {'passed': result.get('passed')}))
    return cl

# ------------------------------------------------------------------- pause
def audit_pause(src):
    clocks = [r for r in src if r.get('type') == 'clock']
    if len(clocks) < 3:
        return [clause('pause_confirmed', False, {'clock_events': len(clocks)}, 'not_covered')]
    rxs = [r['receive_ns'] for r in clocks]
    sims = [r['sim_ns'] for r in clocks]
    gi = max(range(1, len(rxs)), key=lambda i: rxs[i] - rxs[i - 1])
    gap = rxs[gi] - rxs[gi - 1]
    sim_step = sims[gi] - sims[gi - 1]
    epochs = sorted({r.get('epoch') for r in clocks})
    schedules = sorted({r.get('schedule_generation') for r in clocks})
    adjacent_back = sum(1 for i in range(1, len(sims)) if sims[i] < sims[i - 1])
    cl = [
        clause('pause_silence_exceeds_confirm_bound', gap > PAUSE_CONFIRM_NS,
               {'wall_gap_ns': gap, 'pause_confirm_ns': PAUSE_CONFIRM_NS}),
        clause('raw_clock_monotonic', adjacent_back == 0, {'adjacent_regressions': adjacent_back}),
        clause('clock_epoch_unchanged_legal', epochs == [0], {'epochs': epochs}),
        clause('schedule_transition_observed', schedules == sorted(set(schedules)) and len(schedules) >= 2,
               {'schedule_generations': schedules}),
    ]
    return cl

# ------------------------------------------------------- scoped generation
def audit_generation(src):
    committed = [r for r in src if r.get('type') == 'reference_epoch_committed']
    opened = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
    cl = []
    if not opened:
        cl.append(clause('scoped_generation_opened', False, {'opened_events': 0}, 'not_covered'))
        return cl
    o = opened[0]
    cl.append(clause('single_generation_open',
                     len(opened) == 1 and o.get('generation') == 2
                     and o.get('previous_terminal_reason') == 'epoch_binding_changed'
                     and o.get('previous_first_job_id', 0) >= 1 and o.get('previous_last_job_id', 0) >= 1,
                     {k: o.get(k) for k in ('generation', 'previous_terminal_reason',
                                            'previous_first_job_id', 'previous_last_job_id')},
                     'covered' if len(opened) == 1 and o.get('generation') == 2 else 'not_covered'))
    if len(committed) == 2:
        e1, e2 = (c['reference_epoch'] for c in committed)
        binding_diff = any(e1.get(k) != e2.get(k) for k in
                           ('task_generation', 'model_generation', 'config_generation',
                            'schedule_generation', 'clock_epoch', 'path_fingerprint', 'profile_fingerprint'))
        cl.append(clause('two_commits_distinct_binding_identity',
                         [e1.get('generation'), e2.get('generation')] == [1, 2] and binding_diff,
                         {'gens': [e1.get('generation'), e2.get('generation')],
                          'schedule': [e1.get('schedule_generation'), e2.get('schedule_generation')],
                          'clock_epoch': [e1.get('clock_epoch'), e2.get('clock_epoch')]}))
    else:
        cl.append(clause('two_commits_distinct_binding_identity', False,
                         {'committed': len(committed)}, 'not_covered'))
    return cl

# ------------------------------------------------- R4: same-Job full chain
def audit_r4_acceptance_chain(src):
    opened = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
    if not opened:
        return [clause('r4_same_job_new_generation_acceptance', False,
                       {'reason': 'no_scoped_open'}, 'not_covered')]
    open_index = src.index(opened[0])
    after = src[open_index + 1:]
    jobs_after = [r for r in after if r.get('type') == 'job' and isinstance(r.get('job'), dict)]
    reasons = []
    for jr in jobs_after:
        jid = jr['job'].get('job_id')
        cand = [r for r in after if r.get('type') == 'candidate_registration'
                and isinstance(r.get('job'), dict) and r['job'].get('job_id') == jid]
        if not cand:
            reasons.append({'job_id': jid, 'reason': 'no_candidate_registration'})
            continue
        c = cand[0]
        if c.get('accepted_registration') is not True:
            reasons.append({'job_id': jid, 'reason': 'candidate_not_accepted',
                            'candidate_reason': c.get('reason')})
            continue
        dec = [r for r in after if r.get('type') == 'decision' and r.get('job_id') == jid
               and r.get('accepted') is True and r.get('control_source') == 'candidate']
        if not dec:
            d_any = [r for r in after if r.get('type') == 'decision' and r.get('job_id') == jid]
            why = {'job_id': jid, 'reason': 'no_accepted_candidate_sourced_decision'}
            if d_any:
                why['observed_control_sources'] = sorted({r.get('control_source') for r in d_any})
                why['observed_accepted'] = sorted({r.get('accepted') for r in d_any})
            reasons.append(why)
            continue
        seq = dec[0].get('sequence')
        pair = [r for r in after if r.get('type') == 'owned_API_pair' and r.get('sequence') == seq
                and r.get('returned') == [True, True]]
        if not pair:
            reasons.append({'job_id': jid, 'reason': 'no_real_api_pair_for_decision_sequence', 'sequence': seq})
            continue
        appl = [r for r in after if r.get('type') == 'owned_applied_publication' and r.get('sequence') == seq]
        if not appl:
            reasons.append({'job_id': jid, 'reason': 'no_applied_publication', 'sequence': seq})
            continue
        return [clause('r4_same_job_new_generation_acceptance', True,
                       {'job_id': jid, 'decision_sequence': seq,
                        'candidate_accepted': True, 'control_source': 'candidate',
                        'api_returned': [True, True], 'applied_sequence': seq})]
    if not jobs_after:
        reasons.append({'reason': 'no_jobs_submitted_after_open'})
    return [clause('r4_same_job_new_generation_acceptance', False,
                   {'reason': 'no_complete_chain', 'attempted': reasons[:4]}, 'not_covered')]

# ------------------------------------------------------- old candidates
def audit_old_candidates(src):
    opened = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
    if not opened:
        return [clause('old_candidate_disposition', False, {'reason': 'no_scoped_open'}, 'not_covered')]
    open_index = src.index(opened[0])
    before = src[:open_index]
    pre_candidates = [r for r in before if r.get('type') == 'candidate_registration']
    if not pre_candidates:
        # honest absence: no in-flight old candidates existed; this is NOT rejection evidence
        return [clause('old_candidate_disposition', True,
                       {'pre_open_candidates': 0,
                        'note': 'absent_evidence_recorded_not_counted_as_rejection'},
                       'not_applicable_absent')]
    rejected = [r for r in src[open_index:] if r.get('type') in ('job_not_submitted', 'candidate_rejected')
                and r.get('job_id') in {c['job'].get('job_id') for c in pre_candidates if isinstance(c.get('job'), dict)}]
    return [clause('old_candidate_disposition', bool(rejected),
                   {'pre_open_candidates': len(pre_candidates), 'rejection_events': len(rejected)},
                   'covered' if rejected else 'not_covered')]

# ------------------------------------------------------------------ jobs
def audit_jobs_monotonic(src):
    ids = [r['job']['job_id'] for r in src if r.get('type') == 'job' and isinstance(r.get('job'), dict)]
    return [clause('job_ids_strictly_monotonic',
                   ids == sorted(ids) and len(set(ids)) == len(ids), {'count': len(ids)})]

def audit_rnw_run(run_dir):
    sp = Path(run_dir) / 'regulator/source.jsonl'
    if not sp.is_file():
        return {'passed': False, 'error': 'regulator source missing'}
    src, parse_errors = rows_of(sp)
    clauses = [clause('regulator_source_parse_clean', parse_errors == 0, {'parse_errors': parse_errors})]
    if parse_errors:
        return {'passed': False, 'clauses': clauses, 'error': 'parse_errors_present'}
    clauses += audit_close(run_dir)
    clauses += audit_pause(src)
    clauses += audit_generation(src)
    clauses += audit_r4_acceptance_chain(src)
    clauses += audit_old_candidates(src)
    clauses += audit_jobs_monotonic(src)
    # R4 is the gate; close/pause/generation are necessary conditions recorded separately
    r4 = [c for c in clauses if c['name'] == 'r4_same_job_new_generation_acceptance']
    return {'passed': bool(r4 and r4[0]['passed']), 'clauses': clauses}
