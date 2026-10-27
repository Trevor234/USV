#!/usr/bin/env python3
"""Prepare an immutable payload for one explicit MPC directory copy."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
STAGE = Path('/tmp/codex_mpc_model127_stage') / ROOT.name
MANIFEST = 'evidence/delivery_population_v1.json'
LATE = {'evidence/delivery_to_MPC_v1.json', 'evidence/delivery_receipt_readback_v1.json'}


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


assert (ROOT / 'evidence/final_verification_v1.json').is_file()
STAGE.mkdir(parents=True)
files, excluded = {}, []
for path in sorted(ROOT.rglob('*')):
    if not path.is_file():
        continue
    relative = str(path.relative_to(ROOT))
    assert relative != MANIFEST and relative not in LATE, 'Delivery already prepared'
    raw = path.read_bytes()
    if raw.startswith(b'\x7fELF') or any(p in ('build', '__pycache__') for p in path.relative_to(ROOT).parts):
        excluded.append({'path': relative, 'reason': 'compiled offline replay or build/cache', **pin(raw)})
        continue
    files[relative] = pin(raw)
    dest = STAGE / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('xb') as stream:
        stream.write(raw)
    assert dest.read_bytes() == raw
population = {'schema': 'M4-model127-MPC-population-v1', 'source': str(ROOT),
              'stage': str(STAGE), 'mirror': '/home/trevor/MPC/' + ROOT.name,
              'files': files, 'payload_file_count': len(files), 'payload_bytes': sum(v['bytes'] for v in files.values()),
              'excluded_build_files': excluded, 'self_manifest': MANIFEST,
              'late_delivery_receipt': 'evidence/delivery_to_MPC_v1.json',
              'source_only_final_receipt_readback': 'evidence/delivery_receipt_readback_v1.json'}
raw = (json.dumps(population, ensure_ascii=False, indent=2) + '\n').encode()
for path in [ROOT / MANIFEST, STAGE / MANIFEST]:
    with path.open('xb') as stream:
        stream.write(raw)
print(json.dumps({'stage': str(STAGE), 'payload_files': len(files), 'payload_bytes': population['payload_bytes'],
                  'excluded_build_files': len(excluded)}, ensure_ascii=False))
