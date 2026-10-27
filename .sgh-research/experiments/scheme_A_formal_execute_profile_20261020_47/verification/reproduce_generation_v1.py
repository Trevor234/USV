#!/usr/bin/env python3
"""Regenerate all five artifacts into a new directory and compare exact bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

D = Path(__file__).resolve().parent.parent


def pin(p):
    data = p.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    source = D / 'implementation'
    root = D / 'verification/generation_reproduction_v1'
    target = root / 'implementation'
    for q in ['templates', 'python', 'native']:(target / q).mkdir(parents=True)
    (root / 'evidence').mkdir()
    files = [source / 'generate_contract_v1.py', source / 'current_contract_spec_v1.json'] + list((source / 'templates').iterdir())
    before = {str(p): pin(p) for p in files}
    for p in files:
        out = target / p.relative_to(source)
        with out.open('xb') as f:f.write(p.read_bytes())
    run = subprocess.run([sys.executable, '-B', str(target / 'generate_contract_v1.py')], capture_output=True, timeout=30)
    (root / 'stdout.log').write_bytes(run.stdout);(root / 'stderr.log').write_bytes(run.stderr)
    names = ['native/p1_full_contract.hpp', 'native/p1_resources.hpp', 'python/p1_full_contract.py', 'python/p1_resource_contract.py', 'python/p1_contract_spec_v1.json']
    pairs = {rel: {'selected': pin(source / rel), 'regenerated': pin(target / rel), 'equal': (source / rel).read_bytes() == (target / rel).read_bytes()} for rel in names}
    after = {p: pin(Path(p)) for p in before}
    result = {'schema': 'P1-profile-exact-generation-reproduction/v1', 'passed': run.returncode == 0 and all(v['equal'] for v in pairs.values()) and before == after,
              'outputs': pairs, 'input_sha256_before': before, 'input_sha256_after': after,
              'physical_execute_release_enabled': False, 'stage_qualified': False}
    with (D / 'verification/reproduce_generation_v1.json').open('x') as f:json.dump(result, f, indent=2, sort_keys=True);f.write('\n')
    print(json.dumps({'passed': result['passed'], 'exact_outputs': len(pairs)}))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
