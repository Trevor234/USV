#!/usr/bin/env python3
"""Synthetic fact-layer audit checks; never count as an owned run."""
from pathlib import Path
import copy
import hashlib
import json
import struct
import sys
import zlib
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_w2 import w2_facts


def fixture():
    reg = {'w2_release': {'job_id': 2, 'ordinal': 1, 'nonce': 20261023, 'ticks_before_release': 2},
           'expected': {'w2_isolation_reason': 'fatal_capability',
                        'w2_terminal_reasons': ['w2_boundary_expired'], 'pending_discard_required': True}}
    config = {'deadline_ns': 150000000, 'active_watchdog_ns': 1000000000,
              'worker_capability_receipt_timeout_ns': 600000000}
    b = {'job_id': 2, 'ordinal': 1, 'released': True, 'gate_outcome': 'released',
         'disposition': 'expired', 'actual_native_invoked': False, 'ordinal_at_call': 0,
         'entered_ns': 1000000000, 'released_ns': 1500000050, 'guard_ns': 1500000060,
         'job_deadline_ns': 1150000000, 'past_deadline_ns': 350000060}
    jobs = [{'job_id': 1}, {'job_id': 2, 'tick_origin_ns': 1000000000, 'deadline_ns': 1150000000}, {'job_id': 3}]
    worker = [{'type': 'job_received', 'job': copy.deepcopy(j)} for j in jobs]
    worker += [
        {'type': 'candidate', 'job': copy.deepcopy(jobs[0])},
        {'type': 'candidate_publish_result', 'job_id': 1, 'success': True},
        {'type': 'cold_start_policy_result', 'job_id': 1, 'metadata': {'successful': True}},
        {'type': 'w2_boundary_entered', 'job_id': 2, 'ordinal': 1, 'entered_ns': 1000000100, 'job_deadline_ns': 1150000000},
        {'type': 'w2_boundary_result', 'job_id': 2, 'ordinal': 1, 'boundary': b,
         'disposition': 'expired', 'actual_native_invoked': False},
        {'type': 'cold_start_policy_failure', 'job_id': 2,
         'metadata': {'terminal': True, 'actual_C_solve_calls_this_job': 0, 'w2_boundary': copy.deepcopy(b)}},
        {'type': 'terminal_exception', 'job_id': 2, 'reason': 'w2_boundary_expired'},
        {'type': 'pending_discarded', 'job_id': 3, 'reason': 'worker_terminal_exception'},
        {'type': 'capability_publish_attempt', 'payload': {'fatal': False, 'active_job': 2, 'pending_count': 1}},
        {'type': 'capability_publish_attempt', 'payload': {'fatal': True, 'active_job': 0, 'pending_count': 0}},
        {'type': 'worker_summary', 'fatal': True, 'source_io_failed': False,
         'capability_source': {'capability_source_complete': True},
         'generated_candidates': 1, 'published_candidates': 1, 'dropped_candidates': 0, 'completed_jobs': 1},
    ]
    regulator = [{'type': 'job', 'job': copy.deepcopy(j)} for j in jobs]
    regulator.append({'type': 'candidate_registration', 'job': {'job_id': 1}, 'accepted_registration': True})
    for tick, start, kind in [(2, 800000000, 'accepted'), (3, 1100000000, 'fallback'), (4, 1300000000, 'fallback')]:
        regulator += [
            {'type': 'owned_API_pair', 'tick': tick, 'sequence': tick - 1, 'kind': kind,
             'starts': [start + 100, start + 500], 'ends': [start + 400, start + 1000], 'returned': [True, True]},
            {'type': 'decision', 'tick': tick, 'sequence': tick - 1, 'job_id': 1 if tick == 2 else 2,
             'reason': '' if tick == 2 else 'no_candidate', 'accepted': tick == 2,
             'start_ns': start, 'end_ns': start + 2000},
        ]
    for stamp in [990000000, 1100000000, 1300000000]:
        regulator.append({'type': 'capability_admission', 'renewed': True, 'lease_last_after_ns': stamp,
                          'capability': {'active_job': 2, 'fatal': False}})
    raw = struct.pack('<IHHQQIIQ', 0x4C523257, 1, 0, 1, 2, 1, 20261023, 1)
    raw += struct.pack('<I', zlib.crc32(raw) & 0xFFFFFFFF)
    driver = [{'type': 'w2_release_sent', 'write_start_ns': 1500000000, 'write_end_ns': 1500000100,
               'frame_hex': raw.hex(), 'frame_len': 44, 'written_bytes': 44,
               'frame_sha256': hashlib.sha256(raw).hexdigest()}]
    return reg, config, worker, regulator, driver


def run():
    positive = w2_facts(*fixture())
    results = {}
    def mutate(name, fn):
        data = fixture(); fn(*data)
        try:
            w2_facts(*data)
        except AssertionError as exc:
            results[name] = {'rejected_by_assertion': True, 'reason': str(exc)}
        else:
            raise AssertionError('Audit mutation survived: ' + name)
    def find(rows, kind): return next(x for x in rows if x['type'] == kind)
    mutate('not_released', lambda reg, cfg, w, r, d: find(w, 'w2_boundary_result')['boundary'].update(released=False))
    mutate('not_past_deadline', lambda reg, cfg, w, r, d: find(w, 'w2_boundary_result')['boundary'].update(guard_ns=1100000000))
    mutate('wrong_terminal_Job', lambda reg, cfg, w, r, d: find(w, 'terminal_exception').update(job_id=999))
    mutate('target_published', lambda reg, cfg, w, r, d: w.append({'type': 'candidate_publish_result', 'job_id': 2, 'success': True}))
    mutate('no_renewal_while_held', lambda reg, cfg, w, r, d: r.__setitem__(slice(None), [x for x in r if x['type'] != 'capability_admission' or x['lease_last_after_ns'] < 1000000000]))
    mutate('missing_pending_terminal', lambda reg, cfg, w, r, d: w.__setitem__(slice(None), [x for x in w if x['type'] != 'pending_discarded']))
    mutate('target_C_count', lambda reg, cfg, w, r, d: find(w, 'cold_start_policy_failure')['metadata'].update(actual_C_solve_calls_this_job=1))
    mutate('bad_frame_hash', lambda reg, cfg, w, r, d: d[0].update(frame_sha256='0' * 64))
    mutate('duplicate_received_Job', lambda reg, cfg, w, r, d: w.append(copy.deepcopy(find(w, 'job_received'))))
    return {'schema': 'W2-audit-fact-selfcheck-v1', 'synthetic_positive': positive,
            'mutations': results, 'all_rejected_by_assertion': True,
            'scope': 'Synthetic W2 fact layer only; no ROS, no actual owned qualification'}


if __name__ == '__main__':
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
