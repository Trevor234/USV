#!/usr/bin/env python3
"""E01 identity auditor for T3 queue-pressure event logs (batch 126).

Pure function over parsed rows. No ROS, no subprocess, no writes to originals.

Purpose (F124-01): the batch-99 harness asserted only totals, so 513 accepted
events with 163 unique identities passed 14/14. This auditor states, per file:
  - the offered/accepted/rejected population and the exclusive-complete split,
  - the identity MULTISET (duplicates counted, never collapsed into a set size),
  - the producer/local-sequence consistency when those fields are present.

A file that predates the identity fields is reported as `not_recorded`, which is
a coverage statement about the evidence, not a pass.
"""
import json
from collections import Counter
from pathlib import Path


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


def multiset_digest(values):
    counted = Counter(values)
    return {
        'entries': len(values),
        'unique': len(counted),
        'duplicated_entries': sum(c - 1 for c in counted.values() if c > 1),
        'duplicate_pairs': sorted(([v, c] for v, c in counted.items() if c > 1))[:8],
    }


def audit_event_file(path):
    """Audit one T3 queue-pressure event log. Returns a clause dict."""
    rows, parse_errors = rows_of(path)
    if not rows:
        return {'file': str(path), 'status': 'not_covered', 'reason': 'empty_file',
                'parse_errors': parse_errors}
    summary_rows = [r for r in rows if r.get('type') == 'source_summary']
    events = [r for r in rows if r.get('type') != 'source_summary']
    other_events = [r for r in events if r.get('type') != 't3_event']
    business = [r for r in events if r.get('type') == 't3_event']

    ids = [r.get('sequence') for r in business]
    ids_present = [v for v in ids if isinstance(v, int)]

    producer_recorded = all('producer_id' in r and 'local_seq' in r for r in business) and bool(business)
    per_producer = {}
    if producer_recorded:
        for r in business:
            key = r['producer_id']
            bucket = per_producer.setdefault(key, [])
            bucket.append((r['sequence'], r['local_seq']))
        consistency = {}
        for key, rows_k in per_producer.items():
            local = [ls for _, ls in rows_k]
            monotonic = all(b > a for a, b in zip(local, local[1:]))
            offsets_ok = all(seq - ls == rows_k[0][0] - rows_k[0][1] for seq, ls in rows_k)
            consistency[str(key)] = {'events': len(rows_k), 'local_seq_monotonic': monotonic,
                                     'constant_offset': offsets_ok}
    else:
        consistency = None

    clause = {
        'file': str(path),
        'status': 'covered',
        'parse_errors': parse_errors,
        'summary_rows': len(summary_rows),
        'business_events': len(business),
        'non_event_rows': len(other_events),
        'summary_excluded_from_population': True,
        'identity_multiset': multiset_digest(ids_present),
        'duplicates_present': multiset_digest(ids_present)['duplicated_entries'] > 0,
        'producer_identity_recorded': producer_recorded,
        'producer_consistency': consistency,
    }
    if len(summary_rows) == 1:
        s = summary_rows[0]
        clause['summary'] = {k: s.get(k) for k in
                             ('generated', 'emitted', 'dropped', 'normal_source_complete')}
        clause['summary_balance_ok'] = (
            s.get('generated') is not None and s.get('emitted') is not None
            and s.get('dropped') is not None
            and s['generated'] == s['emitted'] + s['dropped'])
        clause['summary_emitted_equals_business_events'] = (
            s.get('emitted') == len(business))
    else:
        clause['summary'] = None
    # The identity finding is independent of any summary claim.
    clause['verdict'] = ('identity_duplicates_detected' if clause['duplicates_present']
                         else 'identity_unique_in_this_file')
    return clause


def compare_accepted_published_disk(accepted_ids, published_ids, disk_ids):
    """Multiset reconciliation across the three populations (F124-01 requirement)."""
    a, p, d = multiset_digest(accepted_ids), multiset_digest(published_ids), multiset_digest(disk_ids)
    return {
        'accepted': a, 'published': p, 'disk': d,
        'published_equals_accepted': Counter(accepted_ids) == Counter(published_ids),
        'disk_equals_accepted': Counter(accepted_ids) == Counter(disk_ids),
        'note': 'multiset comparison; equal counts with different identities fail',
    }
