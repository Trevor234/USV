#!/usr/bin/env python3
"""Drive audit_diagnostic_v3 against the three `_05` runs and the private probes.

Three things must hold, and they are reported separately because conflating
them is what the previous audit did:

  1. the three recorded runs still pass (the tool did not become stricter than
     the data it is meant to accept);
  2. each private error input is rejected *by an assertion*, and the mutation
     that produced it really was applied;
  3. no preparation failure is counted as a rejection.

Read-only with respect to the 56 package: the auditor module is imported from
this package's own copy, and every write is redirected under
`evidence/audit_v3_replays/`.
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent          # implementation/audit_v3
PKG = HERE.parents[1]                           # the 57 review package root
BATCH56 = Path('/home/trevor/USV/.sgh-research/experiments/'
               'scheme_A_M4_diagnostic_worker_20261021_56')
OUT = PKG / 'evidence' / 'audit_v3_replays'


def load_auditor():
    spec = importlib.util.spec_from_file_location(
        'audit_v3', HERE / 'audit_diagnostic_v3.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_case(case, label='baseline', probe=None):
    """Run one audit case, optionally with an input rewritten in memory.

    The probe rewrites only what the named Source/manifest reader returns; the
    files on disk are never touched. `input_changes` records what was actually
    altered so a probe that silently did nothing cannot be read as a pass.
    """
    mod = load_auditor()
    out = OUT / label
    (out / 'postrun').mkdir(parents=True, exist_ok=True)
    mod.D = out
    original_lines, original_read = mod.lines, mod.read
    changes = []

    def lines(p, *args, **kwargs):
        rows, dropped = original_lines(p, *args, **kwargs)
        rows = copy.deepcopy(rows)
        parent = Path(p).parent.name
        if probe == 'W1_expired_lease' and parent == 'regulator':
            for row in rows:
                if row['type'] == 'worker_unusable_transition':
                    row['capability_last_valid_commit_ns'] = (
                        row['check_ns'] - row['capability_timeout_ns'] - 1)
                    changes.append('transition lease age set to timeout + 1 ns')
        if probe == 'W3_zero_delivery_delay' and parent == 'worker':
            for row in rows:
                if row['type'] == 'candidate_publish_result':
                    row['publish_start_ns'] = row['solve_end_ns']
                    row['publish_end_ns'] = row['solve_end_ns']
                    changes.append('delivery delay set to 0 ns')
        if probe == 'W4_active_not_cleared' and parent == 'worker':
            import collections
            w = collections.defaultdict(list)
            for r in rows:
                w[r['type']].append(r)
            jid = w['diagnostic_candidate_dropped'][0]['job_id']
            cand = next(r for r in w['candidate'] if r['job']['job_id'] == jid)
            later = min(r['receive_ns'] for r in w['job_received']
                        if r['job']['job_id'] > jid)
            for row in w['capability_publish_attempt']:
                if cand['publish_start_ns'] <= row['snapshot_ns'] < later:
                    row['payload']['active_job'] = jid
                    changes.append('idle-window capability active_job set to dropped Job')
        return rows, dropped

    def read_for_probe(p):
        value = original_read(p)
        if (probe == 'W4_wrong_manifest_binary'
                and Path(p).parent.name == 'worker'
                and Path(p).name == 'manifest.json'):
            value = copy.deepcopy(value)
            value['binary_sha256'] = '0' * 64
            changes.append('Worker manifest binary_sha256 set to all zeros')
        return value

    mod.lines = lines
    mod.read = read_for_probe
    old_argv = sys.argv
    sys.argv = ['audit_diagnostic_v3.py', '--case', case, '--registration',
                str(BATCH56 / 'implementation' / (case + '_registration_v1.json'))]
    stream = io.StringIO()
    try:
        with contextlib.redirect_stdout(stream):
            mod.main()
        result = {'case': case, 'probe': probe, 'auditor_passed': True,
                  'stdout': stream.getvalue()[-800:]}
    except AssertionError as exc:
        result = {'case': case, 'probe': probe, 'auditor_passed': False,
                  'rejected_by': 'AssertionError', 'message': str(exc)[:600]}
    except Exception as exc:  # noqa: BLE001 - any other type is a finding
        result = {'case': case, 'probe': probe, 'auditor_passed': False,
                  'rejected_by': type(exc).__name__, 'message': str(exc)[:600]}
    finally:
        sys.argv = old_argv
        mod.lines = original_lines
        mod.read = original_read
    result['input_changes'] = changes
    if probe:
        result['mutation_applied'] = bool(changes)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for label in ('baseline', 'probe_lease', 'probe_delay', 'probe_idle',
                  'probe_identity'):
        (OUT / label / 'postrun').mkdir(parents=True, exist_ok=True)

    report = {'schema': 'M4-diagnostic-audit-v3-verification-v1',
              'auditor': str(HERE / 'audit_diagnostic_v3.py'),
              'baselines': [], 'probes': []}

    for case in ('W1', 'W3', 'W4'):
        r = run_case(case, 'baseline')
        report['baselines'].append(r)
        print('baseline', case, 'passed' if r['auditor_passed'] else 'FAILED',
              r.get('message', '')[:160])

    probes = [('W1', 'W1_expired_lease', 'probe_lease'),
              ('W3', 'W3_zero_delivery_delay', 'probe_delay'),
              ('W4', 'W4_active_not_cleared', 'probe_idle'),
              ('W4', 'W4_wrong_manifest_binary', 'probe_identity')]
    for case, probe, label in probes:
        r = run_case(case, label, probe)
        report['probes'].append(r)
        print('probe', probe, '->',
              'PASSED (blind spot!)' if r['auditor_passed'] else
              'rejected by %s' % r.get('rejected_by'),
              '| mutation applied:', r.get('mutation_applied'))

    base_ok = all(r['auditor_passed'] for r in report['baselines'])
    probes_ok = all((not r['auditor_passed'])
                    and r.get('rejected_by') == 'AssertionError'
                    and r.get('mutation_applied')
                    for r in report['probes'])
    report['baselines_all_pass'] = base_ok
    report['all_probes_rejected_by_assertion'] = probes_ok
    report['complete'] = base_ok and probes_ok

    path = OUT / 'verification_v1.json'
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n',
                    encoding='utf-8')
    print()
    print('baselines pass:', base_ok)
    print('probes all rejected by assertion with mutation applied:', probes_ok)
    print('written:', path)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
