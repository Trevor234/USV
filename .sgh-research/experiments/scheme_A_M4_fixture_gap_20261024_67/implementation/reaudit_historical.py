#!/usr/bin/env python3
"""Run the hardened historical auditor with all writes redirected to batch67."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'scheme_A_M4_diagnostic_worker_20261021_56'
TOOL = ROOT / 'implementation/current_author/w2_audit_common.py'
OUT = ROOT / 'evidence/historical_reaudit'


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def create(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


OUT.mkdir()
inputs = {str(TOOL): pin(TOOL)}
for case in ('W1', 'W3', 'W4'):
    registration = OLD / 'implementation' / f'{case}_registration_v1.json'
    inputs[str(registration)] = pin(registration)
    reg = json.loads(registration.read_text())
    for path in Path(reg['output']).rglob('*'):
        if path.is_file():
            inputs[str(path)] = pin(path)
    inputs[str(OLD / 'evidence' / f'{case}_launch_v1.json')] = pin(OLD / 'evidence' / f'{case}_launch_v1.json')
create(OUT / 'inputs_before_v1.json', {'files': inputs, 'count': len(inputs)})
cases = {}
for case in ('W1', 'W3', 'W4'):
    destination = OUT / case
    (destination / 'postrun').mkdir(parents=True)
    spec = importlib.util.spec_from_file_location('historical_audit_' + case, TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.D = destination
    sys.argv = [str(TOOL), '--case', case, '--registration',
                str(OLD / 'implementation' / f'{case}_registration_v1.json')]
    try:
        module.main()
        report = json.loads((destination / 'postrun' / f'{case}_audit_v1.json').read_text())
        assert report['passed'] is True
        cases[case] = {'passed': True, 'report': str(destination / 'postrun' / f'{case}_audit_v1.json'),
                      'report_pin': pin(destination / 'postrun' / f'{case}_audit_v1.json'),
                      'run_id': report['run_id'], 'mutations_rejected': report['mutations_rejected']}
    except Exception as error:
        (destination / 'error.log').write_text(traceback.format_exc())
        cases[case] = {'passed': False, 'error_type': type(error).__name__, 'error': str(error)}
after = {filename: pin(Path(filename)) for filename in inputs}
create(OUT / 'verification_v1.json', {
    'schema': 'M4-historical-three-diagnostic-raw-reaudit-v67', 'cases': cases,
    'auditor': {'path': str(TOOL), **pin(TOOL)},
    'ROS_initialized': False, 'new_owned_runs': 0,
    'original_files_unchanged': inputs == after,
    'input_files': len(inputs),
    'complete': all(row['passed'] for row in cases.values()) and inputs == after,
    'qualification_scope': 'Original registered case population only; source-range applicability is assessed separately',
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
})
print(json.dumps({'cases': cases, 'original_files_unchanged': inputs == after}, ensure_ascii=False))
raise SystemExit(0 if all(row['passed'] for row in cases.values()) and inputs == after else 2)
