#!/usr/bin/env python3
"""Replay the Driver's registration preflight and record it as evidence.

The delivery document claims the Driver's startup assertion chain was replayed
and passed. A claim without a stored artifact cannot be checked, so this script
is that artifact's producer: it executes the same assertions, over the same
registration, and writes pass/fail per step.

This runs no role and starts no ROS graph. It stops exactly where the Driver's
main() stops before its first spawn.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
IMPL = PKG / 'implementation'
AUTHOR = IMPL / 'w2_author'
OUT = PKG / 'evidence' / 'preflight_replay'

# The Driver's own constants, read from its source so a drift is visible here.
DRIVER = AUTHOR / 'owned_m4_diagnostic_driver_v1.py'

SCOPE = 'M4_owned_diagnostic_worker_only_v1'


def pin(p: Path) -> dict:
    data = Path(p).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def read(p: Path):
    return json.loads(Path(p).read_bytes())


def driver_constants() -> dict:
    """Extract the Driver's pinned constants without importing it."""
    import re
    src = DRIVER.read_text()
    out = {}
    for name in ('INDEX_SHA', 'CONTRACT_SHA', 'SCOPE'):
        m = re.search(r"^%s\s*=\s*'([^']*)'" % name, src, re.M)
        if m:
            out[name] = m.group(1)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    reg = read(IMPL / 'W2_registration_v1.json')
    registry = read(IMPL / 'selected_runtime_registry_w2_v1.json')
    const = driver_constants()
    os.environ.update({'ROS_DOMAIN_ID': str(reg.get('domain_id', 120)),
                       'ROS_LOCALHOST_ONLY': '1',
                       'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'})
    steps = []

    def step(name: str, fn):
        try:
            detail = fn()
            steps.append({'step': name, 'passed': True, 'detail': detail})
        except AssertionError as exc:
            steps.append({'step': name, 'passed': False, 'detail': str(exc)[:300]})
        except Exception as exc:  # noqa: BLE001 - any failure is a finding
            steps.append({'step': name, 'passed': False,
                          'detail': '%s: %s' % (type(exc).__name__, exc)})

    step('schema_scope_case', lambda: (
        _assert(reg['schema'] == 'M4-owned-diagnostic-run-v1', 'schema'),
        _assert(reg['scope'] == SCOPE, 'scope'),
        _assert(reg['case'] == 'W2-native-boundary-hold', 'case'),
        _assert(reg['production_physical_release_enabled'] is False, 'physical release'),
        f"case={reg['case']}"))

    step('domain_and_budget', lambda: (
        _assert(reg['domain_id'] == 120, 'domain'),
        _assert(os.environ['ROS_DOMAIN_ID'] == '120', 'env domain'),
        _assert(reg['max_seconds'] == 45, 'max_seconds'),
        _assert(reg['automatic_retries'] == 0, 'retries'),
        _assert(reg['fault_injection_enabled'] is True, 'fault injection'),
        'budget ok'))

    step('contract_identity', lambda: (
        _assert(reg['contract_sha256'] == const['CONTRACT_SHA'], 'contract sha'),
        _assert(reg['index_sha256'] == const['INDEX_SHA'], 'index sha'),
        f"index_sha={reg['index_sha256'][:12]}"))

    step('contract_shape', lambda: (
        _assert(read(reg['contract'])['schema'] == 'p1-execution-contract-v4', 'v4'),
        _assert(read(reg['contract'])['qualification'] == 'execution_diagnostic_only', 'diag'),
        _assert(read(reg['contract'])['pending_final_calibration'] == [], 'no pending'),
        'contract ok'))

    step('registry_pins', lambda: (
        _assert(pin(reg['registry'])['sha256'] == reg['registry_sha256'], 'registry sha'),
        _assert(registry['driver_tool_sha256'] == pin(registry['driver'])['sha256'], 'driver sha'),
        _assert(registry['scope'] == SCOPE, 'scope'),
        f"driver={registry['driver_tool_sha256'][:12]}"))

    def bundle_check():
        for role, record in registry['roles'].items():
            b = record['source_bundle']
            _assert(pin(b['path'])['sha256'] == b['sha256'], role + ' bundle sha')
            rows = read(b['path'])['files']
            rows = rows.values() if isinstance(rows, dict) else rows
            for row in rows:
                _assert('path' in row, role + ' row missing path')
                for key in ('bytes', 'sha256'):
                    _assert(pin(row['path'])[key] == row[key], role + ' row ' + key)
            _assert(pin(record['binary'])['sha256'] == record['binary_sha256'], role + ' elf')
        return 'all roles verified'
    step('bundle_and_elf_chain', bundle_check)

    step('topics_pin', lambda: (
        _assert(pin(reg['topics'])['sha256'] == reg['topics_sha256'], 'topics sha'),
        'topics ok'))

    def output_path():
        out = Path(reg['output'])
        _assert(out.is_absolute(), 'absolute')
        _assert(out.parent == AUTHOR.parent / 'runs', 'parent is runs')
        _assert(out.parent.is_dir(), 'runs parent exists')
        _assert(not out.exists(), 'output absent')
        return str(out)
    step('output_path', output_path)

    def w2_clauses():
        # Execute the Driver's own preflight function rather than a copy, so a
        # clause added there cannot be missed here.
        namespace = {}
        src = DRIVER.read_text()
        start = src.index('def w2_preflight(reg):')
        end = src.index('def _w2r_terminal(', start)
        exec(compile(src[start:end], str(DRIVER), 'exec'), namespace)
        w2 = namespace['w2_preflight'](reg)
        _assert(reg['expected']['w2_exit_codes']['worker'] == 2, 'worker rc')
        _assert(reg['expected']['w2_worker_signals'] == ['SIGINT'], 'worker signal')
        return 'target=%d/%d' % (w2['job_id'], w2['ordinal'])
    step('w2_clauses', w2_clauses)

    ok = all(s['passed'] for s in steps)
    report = {
        'schema': 'W2-driver-preflight-replay-v1',
        'registration': str(IMPL / 'W2_registration_v1.json'),
        'registration_sha256': pin(IMPL / 'W2_registration_v1.json')['sha256'],
        'registry_sha256': pin(IMPL / 'selected_runtime_registry_w2_v1.json')['sha256'],
        'driver_constants_used': const,
        'steps': steps,
        'all_passed': ok,
        'scope_note': ('Replays the Driver main() assertions up to the first spawn. '
                       'No role starts, no ROS graph, no owned run.'),
        'ros_started': False,
        'owned_run_performed': False,
    }
    path = OUT / 'preflight_replay_v1.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    for s in steps:
        print('%-26s %s  %s' % (s['step'], 'PASS' if s['passed'] else 'FAIL',
                                str(s['detail'])[:80]))
    print('\nall passed:', ok)
    print('written:', path)
    return 0 if ok else 1


def _assert(cond, what):
    assert cond, what
    return True


if __name__ == '__main__':
    sys.exit(main())
