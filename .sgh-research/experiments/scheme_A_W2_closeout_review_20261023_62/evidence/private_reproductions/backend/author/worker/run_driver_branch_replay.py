#!/usr/bin/env python3
"""Replay the Driver's W2 branch against a scripted event stream.

61's D1 showed the observation loop's post-conditions fell through to the W1
branch, so a perfectly good W2 stimulus died on
`W1 never observed the Worker entering its registered stall`. That is a
deterministic property of the source, not a guess about a future owned run, so
it can be replayed without ROS: build the same locals the loop would have, then
execute the *submitted* branch statements.

The extraction is by line range from the real file, so an edit that moves or
changes the branch is noticed here rather than silently drifting.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
TREE = HERE.parent
PKG = TREE.parents[1]
OUT = PKG / 'evidence' / 'w2_driver_replay'

DRIVER = TREE / 'owned_m4_diagnostic_driver_v1.py'


def branch_block(source: str, start_marker: str, end_marker: str) -> str:
    """Extract a dedented statement block between two markers.

    The Driver's branches are indented inside `try:`; dedenting lets the block
    run at module scope with the locals supplied explicitly.
    """
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    block = source[start:end]
    lines = block.splitlines()
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    trim = min(indents)
    body = '\n'.join(l[trim:] if l.strip() else l for l in lines)
    # The block starts with `elif ...:`; turn it into a plain `if` so the
    # statements can run at module scope.
    return body.replace('elif ', 'if ', 1)


def run_block(block: str, scope: dict) -> str:
    """Execute the block; return 'ok' or the assertion message."""
    try:
        exec(compile(block, '<driver-branch>', 'exec'), scope)  # noqa: S102
        return 'ok'
    except AssertionError as exc:
        return 'assertion: %s' % exc


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source = DRIVER.read_text()
    w2_block = branch_block(source, "        elif case=='W2-native-boundary-hold':",
                            "        else:\n            assert accepted_pairs>=1")
    report = {'schema': 'W2-driver-branch-replay-v1', 'cases': {}}

    base = {
        'case': 'W2-native-boundary-hold',
        'w2': {'job_id': 2, 'ordinal': 1, 'nonce': 5,
               'wait_budget_ns': 1000000000, 'ticks_before_release': 2},
        'w2_required_ticks': 2,
        'accepted_pairs': 1, 'ramp_ok': True,
        'pairs_before': 1, 'pairs_after': 3,
        'w2_entered_at': 1000000000,
        'w2_entered_row': {'job_id': 2, 'ordinal': 1, 'entered_ns': 1000000000},
        'w2_release_sent': True,
        'w2_release_frame': b'\x00' * 44,
        'w2_result': {'disposition': 'expired', 'actual_native_invoked': False,
                      'job_id': 2, 'ordinal': 1},
        'w2_ticks_after_enter': [3, 4],
        'transition_ns': None, 'transition_reason': None, 'watchdog_ns': None,
        'result': {}, 'event': lambda *a, **k: None,
        'hashlib': __import__('hashlib'),
    }

    # 1. A well-formed W2 stream must pass the observation post-conditions.
    scope = dict(base); scope = dict(scope)
    report['cases']['well_formed_stream'] = {'outcome': run_block(w2_block, scope)}

    # 2. Too few ticks after entry must be refused.
    scope = dict(base, w2_ticks_after_enter=[3])
    report['cases']['too_few_ticks'] = {'outcome': run_block(w2_block, scope),
                                        'expected': 'assertion'}

    # 3. A result attributed to another Job must be refused.
    scope = dict(base, w2_result={'disposition': 'expired',
                                  'actual_native_invoked': False,
                                  'job_id': 999, 'ordinal': 99})
    report['cases']['wrong_result_job'] = {'outcome': run_block(w2_block, scope),
                                           'expected': 'assertion'}

    # 4. Entry at another ordinal must be refused.
    scope = dict(base, w2_entered_row={'job_id': 2, 'ordinal': 99,
                                       'entered_ns': 1000000000})
    report['cases']['wrong_entry_ordinal'] = {'outcome': run_block(w2_block, scope),
                                              'expected': 'assertion'}

    # 5. No release written must be refused.
    scope = dict(base, w2_release_sent=False)
    report['cases']['no_release'] = {'outcome': run_block(w2_block, scope),
                                     'expected': 'assertion'}

    for name, case in report['cases'].items():
        expect = case.get('expected', 'ok')
        ok = case['outcome'].startswith('assertion') if expect == 'assertion' \
            else case['outcome'] == 'ok'
        case['passed'] = ok

    report['all_passed'] = all(c['passed'] for c in report['cases'].values())
    report['w2_branch_lines'] = [source[:source.index(
        "        elif case=='W2-native-boundary-hold':")].count('\n') + 1,
                                 source[:source.index(
        "        else:\n            assert accepted_pairs>=1")].count('\n') + 1]
    report['note'] = ('Source-statement replay of the submitted W2 branch with '
                      'scripted locals. No ROS, no spawn, no owned run.')
    path = OUT / 'driver_branch_replay_v1.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    for k, v in report['cases'].items():
        print('%-24s %s  %s' % (k, 'PASS' if v['passed'] else 'FAIL', v['outcome']))
    print('all passed:', report['all_passed'])
    print('written:', path)
    return 0 if report['all_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
