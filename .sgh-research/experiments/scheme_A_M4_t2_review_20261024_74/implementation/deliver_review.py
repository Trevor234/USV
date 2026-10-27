#!/usr/bin/env python3
"""Create-only MPC mirror of batch74, excluding compiled replay build dirs."""
from pathlib import Path
import datetime
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parents[1]
MIRROR = Path('/home/trevor/MPC') / ROOT.name
MANIFEST = 'postrun/delivery_population_v1.json'
RECEIPT = 'postrun/delivery_receipt_v1.json'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def create(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


assert not MIRROR.exists(), 'Refuse to replace an existing delivery directory'
assert (ROOT / 'evidence/final_verification_v1.json').is_file()
files, excluded = {}, []
for path in sorted(ROOT.rglob('*')):
    if not path.is_file():
        continue
    relative = path.relative_to(ROOT)
    if any(p in ('build', '__pycache__') for p in relative.parts):
        excluded.append(str(relative))
        continue
    assert str(relative) not in (MANIFEST, RECEIPT), 'Delivery already finalized'
    files[str(relative)] = pin(path.read_bytes())
population = {'schema': 'M4-T2-review-delivery-population-v74',
              'scope': 'all batch74 files except named compiled replay builds, self manifest and self receipt',
              'files': files, 'count': len(files), 'bytes': sum(v['bytes'] for v in files.values()),
              'excluded_build_files': excluded,
              'self_records': [MANIFEST, RECEIPT]}
create(ROOT / MANIFEST, (json.dumps(population, ensure_ascii=False, indent=2) + '\n').encode())
MIRROR.mkdir()
for name in [*files, MANIFEST]:
    create(MIRROR / name, (ROOT / name).read_bytes())
expected = {**files, MANIFEST: pin((ROOT / MANIFEST).read_bytes())}
rounds = []
for i in range(2):
    names = {str(p.relative_to(MIRROR)) for p in MIRROR.rglob('*') if p.is_file()}
    mismatch = [name for name, value in expected.items() if pin((MIRROR / name).read_bytes()) != value]
    assert names == set(expected) and not mismatch, (names ^ set(expected), mismatch)
    rounds.append({'round': i + 1, 'population_exact': True, 'mismatches': mismatch,
                   'files_read': len(expected)})
receipt = {'schema': 'M4-T2-review-delivery-receipt-v74',
           'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
           'source': str(ROOT), 'mirror': str(MIRROR),
           'payload_files': len(files), 'payload_bytes': population['bytes'],
           'population_manifest': pin((ROOT / MANIFEST).read_bytes()),
           'excluded_build_files': excluded, 'readback_rounds': rounds,
           'exact_population': True, 'delivered_files_including_manifest_and_receipt': len(files) + 2,
           'qualification_unchanged': {'M4': False, 'F6': False, 'P1': False, 'plant': False, 'hard_realtime': False}}
raw = (json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode()
create(ROOT / RECEIPT, raw)
create(MIRROR / RECEIPT, raw)
assert (MIRROR / RECEIPT).read_bytes() == raw
names = {str(p.relative_to(MIRROR)) for p in MIRROR.rglob('*') if p.is_file()}
assert names == set(expected) | {RECEIPT}
print(json.dumps({'mirror': str(MIRROR), 'delivered_files': len(names),
                  'payload_bytes': population['bytes'], 'build_files_excluded': len(excluded),
                  'exact_population': True, 'readback_rounds': 2}, ensure_ascii=False))
