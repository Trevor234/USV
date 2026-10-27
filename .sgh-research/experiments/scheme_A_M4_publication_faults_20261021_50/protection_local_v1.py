#!/usr/bin/env python3
"""Recheck pinned49 and its full historical local protection without recursive runs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
P = D.parent / 'scheme_A_M4_recorder_bootstrap_20261021_49'
PINS = {'archive_inventory_v1.json': '7ca703b906bc95e154816ef591b9df6a8b5cadcdd4e2842b42ad3b254dbc87fc',
        'postrun/final_QA_v1.json': 'eb2ef9d422b83d3bc0de0739b1b781acdafd4b5cb1adcfd66a496a2762f00ca7',
        'delivery_verification.json': 'df7a3cffd7e702b7544fa0a13d1c01209dfbcad56a5eaef2a296e0cc55ab8931'}


def pin(path):
    h = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        while b := stream.read(1024 * 1024):
            h.update(b)
            size += len(b)
    return {'bytes': size, 'sha256': h.hexdigest()}


def parent49():
    for name, sha in PINS.items():
        assert pin(P / name)['sha256'] == sha, name
    inv = json.loads((P / 'archive_inventory_v1.json').read_bytes())
    expected = {row['relative_path'] for row in inv['files']} | {'archive_inventory_v1.json', 'delivery_verification.json'}
    actual_files = set()
    actual_dirs = set()
    for path in P.rglob('*'):
        assert not path.is_symlink(), str(path)
        (actual_dirs if path.is_dir() else actual_files).add(str(path.relative_to(P)))
    assert actual_files == expected and actual_dirs == set(inv['directories']) and len(expected) == 533
    for row in inv['files']:
        assert pin(P / row['relative_path']) == {k: row[k] for k in ['bytes', 'sha256']}, row['relative_path']
    qa = json.loads((P / 'postrun/final_QA_v1.json').read_bytes())
    assert qa['passed'] and qa['normal_owned_outlet_component_qualified'] and qa['actual_control_API_calls'] == 210
    assert not qa['M4_stage_qualified'] and not qa['F6_qualified'] and not qa['P1_qualified']
    return {'files': 533, 'full_bytes_checked': True, 'metadata_pins': PINS,
            'normal_component_passed_retained': True, 'M4_F6_P1_unqualified_retained': True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    assert args.output.is_absolute() and args.output.parent == D / 'preflight' and not args.output.exists()
    helper = P / 'protection_local_v1.py'
    assert pin(helper)['sha256'] == '506394bebfebecdca24e6957e9f5c0a31b1a86e9336a2180e519034ad913ae9d'
    spec = importlib.util.spec_from_file_location('pinned49_local_protection', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.NEW_ROOTS += ('.sgh-research/experiments/' + D.name + '/',)
    start = time.monotonic()
    before = module.workspace()
    try:
        p49 = parent49()
        historical = module.protect()
        assert parent49() == p49
        after = module.workspace()
        assert before == after
        result = {'passed': True, 'workspace_before': before, 'workspace_after': after,
                  'parent49': p49, 'historical_full_local_protection': historical,
                  'all_historical_original_paths_unchanged': False,
                  'explicit49_preexisting_path_exceptions_retained': True}
    except Exception as e:
        result = {'passed': False, 'error': repr(e), 'traceback': __import__('traceback').format_exc(),
                  'workspace_before': before, 'workspace_after': module.workspace()}
    result.update(schema='M4-publication-component-local-preservation/v1', elapsed_seconds=time.monotonic() - start,
                  endpoints_checked=False, M4_stage_qualified=False, P1_qualified=False, research_conclusion=False)
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ['passed', 'elapsed_seconds']} | {'output': str(args.output), 'error': result.get('error')}))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
