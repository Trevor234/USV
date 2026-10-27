#!/usr/bin/env python3
"""Offline component replay of the Driver's W4 observation logic.

Reads one finished W4 run directory and re-applies exactly the assertions the
live Driver applies, so a Driver change can be validated against real Source
evidence BEFORE spending a rebuild (the Driver's SHA is compiled into every
owned binary, so a Driver edit always costs a new build attempt).

This is a component check, not run qualification: it reads files another
process produced and cannot prove anything the live run did not record.
"""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def lines(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--contract', type=Path, required=True)
    a = ap.parse_args()
    config = json.loads(a.contract.read_bytes())
    hold_ns = int(config['hold_ns'])

    dropped = 0
    dropped_job_id = None
    dropped_target_tick = None
    generated_at_drop = None
    jobs_after_drop = 0
    cap_window = []
    cap_frame = []
    jobs_by_id = {}
    registered_job_ids = set()
    decisions = {}
    transition_ns = None
    watchdog_ns = None

    for wrow in lines(a.run / 'worker/source.jsonl'):
        wt = wrow['type']
        if wt == 'diagnostic_candidate_dropped':
            dropped += 1
            dropped_job_id = wrow['job_id']
            generated_at_drop = wrow['generated_candidates']
            if dropped_job_id in jobs_by_id:
                dropped_target_tick = jobs_by_id[dropped_job_id]
        elif wt == 'job_received':
            if dropped:
                jobs_after_drop += 1
        elif wt == 'capability_publish_attempt':
            p = wrow['payload']
            if dropped and jobs_after_drop == 0:
                cap_window.append({'source': 'worker_capability_publish_attempt',
                                   'snapshot_ns': wrow['snapshot_ns'],
                                   'active_job': p['active_job'],
                                   'completed_jobs': p['completed_jobs'],
                                   'pending_count': p['pending_count']})

    for row in lines(a.run / 'regulator/source.jsonl'):
        t = row['type']
        if t == 'capability_admission':
            cap = row['capability']
            cap_frame.append({'source': 'regulator_capability_admission',
                              'callback_sequence': row['callback_sequence'],
                              'active_job': cap['active_job'],
                              'completed_jobs': cap['completed_jobs'],
                              'pending_count': cap['pending_count'],
                              'lease_last_after_ns': row.get('lease_last_after_ns')})
        elif t == 'decision':
            decisions[row['tick']] = {'reason': row.get('reason', ''),
                                      'accepted': row.get('accepted') is True,
                                      'control_source': row.get('control_source'),
                                      'final_n': row.get('final_n'),
                                      'previous_n': row.get('previous_n'),
                                      'job_id': row.get('job_id'),
                                      'tick': row.get('tick'),
                                      'activation_commit_ns': row.get('activation_commit_ns'),
                                      'anchor_known': row.get('anchor_known')}
        elif t == 'job':
            jid = row['job']['job_id']
            jobs_by_id[jid] = row['job']['target_tick']
            if dropped and dropped_job_id == jid:
                dropped_target_tick = row['job']['target_tick']
        elif t == 'candidate_registration':
            registered_job_ids.add(row['job']['job_id'])
        elif t == 'worker_unusable_transition' and transition_ns is None:
            transition_ns = row['processed_ns']
        elif t == 'active_watchdog':
            watchdog_ns = row['observed_ns']

    summary = {'dropped_candidates': dropped, 'dropped_job_id': dropped_job_id,
               'dropped_target_tick': dropped_target_tick,
               'generated_at_drop': generated_at_drop,
               'registered_job_ids': sorted(registered_job_ids),
               'capability_window_after_drop': cap_window}

    assert dropped >= 1, 'W4 never observed a generated-but-dropped candidate'
    assert dropped_target_tick is not None, 'W4 could not resolve the dropped Job target tick'
    assert transition_ns is None, 'W4 must not produce a worker_unusable_transition'
    assert watchdog_ns is None, 'W4 must not trip the active watchdog'
    d0 = decisions.get(dropped_target_tick)
    assert d0 is not None, 'W4 never observed a decision for the dropped Job target tick'
    assert d0['reason'] == 'no_candidate' and d0['accepted'] is False, \
        'W4 target tick %r was decided as %r (accepted=%r)' % (
            dropped_target_tick, d0['reason'], d0['accepted'])
    assert dropped_job_id not in registered_job_ids, 'W4 dropped candidate was registered anyway'
    prior = [(v['tick'], v['activation_commit_ns']) for v in decisions.values()
             if v['accepted'] and v['tick'] < dropped_target_tick]
    assert prior, 'W4 has no accepted tick before the dropped target tick'
    prior_tick, prior_commit = max(prior, key=lambda x: x[1])
    age_ns = d0['activation_commit_ns'] - prior_commit
    expected_source = 'hold' if age_ns <= hold_ns else 'ramp_zero'
    assert d0['control_source'] == expected_source, \
        'W4 fallback source %r but policy (age %d vs hold %d ns) requires %r' % (
            d0['control_source'], age_ns, hold_ns, expected_source)
    if expected_source == 'hold':
        assert d0['final_n'] == d0['previous_n'], 'W4 hold did not keep the applied command'
    later = sorted(k for k, v in decisions.items()
                   if k > dropped_target_tick and v['reason'] != 'shutdown')
    assert later, 'W4 never observed a business tick after the dropped target tick'
    assert any(decisions[k]['accepted'] for k in later), 'W4 never resumed delivery'
    cleared = [r for r in (cap_window + cap_frame)
               if r['active_job'] == 0 and r['pending_count'] == 0
               and r['completed_jobs'] >= generated_at_drop]
    assert cleared, 'W4 never cleared active_job after the drop with no later Job pending'

    summary.update({'target_tick_decision': d0,
                    'target_tick_age_since_prior_accept_ns': age_ns,
                    'hold_ns': hold_ns, 'prior_accepted_tick': prior_tick,
                    'expected_fallback_source': expected_source,
                    'later_business_ticks': {k: decisions[k] for k in later},
                    'cleared_frames': cleared,
                    'passed': True})
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
