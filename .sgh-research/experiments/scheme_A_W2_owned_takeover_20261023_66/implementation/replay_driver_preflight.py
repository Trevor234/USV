#!/usr/bin/env python3
"""Execute the same read-only preflight the real Driver calls; no role starts."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
AUTHOR = ROOT / 'implementation/w2_author'
OUT = ROOT / 'evidence/preflight_replay'


def main():
    OUT.mkdir(exist_ok=False)
    path = AUTHOR / 'owned_m4_diagnostic_driver_v1.py'
    spec = importlib.util.spec_from_file_location('registered_driver_no_main', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    regpath = ROOT / 'implementation/W2_registration_v1.json'
    reg = json.loads(regpath.read_text())
    env = {'ROS_DOMAIN_ID': '120', 'ROS_LOCALHOST_ONLY': '1', 'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'}
    config, registry = module.registration_preflight(reg, path, env)
    rejected = {}
    for name, update in [
        ('nonce_zero', lambda r: r['w2_release'].update(nonce=0)),
        ('budget_zero', lambda r: r['w2_release'].update(wait_budget_ns=0)),
        ('different_Job_deadline', lambda r: r['two_deadlines'].update(job_deadline_ns_after_origin=150000001)),
        ('wrong_close_signal', lambda r: r['expected'].update(w2_worker_signals=['SIGTERM'])),
        ('wrong_registry_pin', lambda r: r.update(registry_sha256='0' * 64)),
    ]:
        candidate = copy.deepcopy(reg); update(candidate)
        try: module.registration_preflight(candidate, path, env)
        except AssertionError as exc: rejected[name] = str(exc)
        else: raise AssertionError('Preflight mutation survived: ' + name)
    report = {'schema': 'W2-shared-real-preflight-v1',
        'registration': str(regpath), 'registration_sha256': hashlib.sha256(regpath.read_bytes()).hexdigest(),
        'registry_sha256': reg['registry_sha256'], 'shared_function': 'w2_runtime_contract.registration_preflight',
        'driver_calls_same_function': 'config,registry=registration_preflight(' in path.read_text(),
        'positive_passed': True, 'negative_cases_assertion_rejected': rejected,
        'ROS_started': False, 'roles_spawned': False, 'registered_output_created': Path(reg['output']).exists()}
    assert not report['registered_output_created']
    (OUT / 'preflight_replay_v1.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__': raise SystemExit(main())
