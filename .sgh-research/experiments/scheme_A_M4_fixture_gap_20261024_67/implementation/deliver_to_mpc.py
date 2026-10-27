#!/usr/bin/env python3
"""Deliver a new evidence directory and confirm bounded consecutive readbacks."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
DEST = Path('/home/trevor/MPC') / ROOT.name


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def population(root):
    return {str(path.relative_to(root)): pin(path)
            for path in sorted(root.rglob('*')) if path.is_file()}


def create(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def confirm(expected):
    reads = []
    consecutive = 0
    for attempt in range(1, 6):
        actual = population(DEST)
        diff = {'source_only': sorted(expected.keys() - actual.keys()),
                'destination_only': sorted(actual.keys() - expected.keys()),
                'changed': sorted(key for key in expected.keys() & actual.keys()
                                   if expected[key] != actual[key])}
        matched = all(not value for value in diff.values())
        reads.append({'read': attempt, 'matched': matched, 'differences': diff})
        consecutive = consecutive + 1 if matched else 0
        if consecutive == 2:
            assert population(ROOT) == expected, 'source changed during readback'
            return reads
        time.sleep(0.5)
    raise AssertionError(json.dumps({'readback_attempts': reads}, ensure_ascii=False))


assert DEST.parent.is_dir() and not DEST.exists(), 'Require a new MPC directory'
assert not any(path.is_symlink() for path in ROOT.rglob('*')), 'Inspect links first'
inventory = ROOT / 'evidence/package_inventory_v1.json'
receipt_path = ROOT / 'evidence/delivery_to_MPC_v1.json'
assert not inventory.exists() and not receipt_path.exists()
rows = population(ROOT)
create(inventory, {'schema': 'M4-Fixture-gap-package-inventory-v67',
    'excludes_self_and_delivery_receipt': True, 'files': rows,
    'count': len(rows), 'bytes': sum(row['bytes'] for row in rows.values())})
expected = population(ROOT)
shutil.copytree(ROOT, DEST)
reads = confirm(expected)
receipt = {'schema': 'M4-Fixture-gap-MPC-delivery-v67',
    'written_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
    'source': str(ROOT), 'destination': str(DEST),
    'final_files_including_receipt': len(expected) + 1,
    'bytes_before_receipt': sum(row['bytes'] for row in expected.values()),
    'exact_population': True, 'sha256_mismatches': [],
    'consecutive_full_readbacks_before_receipt': 2, 'readbacks': reads,
    'overwritten_existing_files': False, 'new_owned_runs': 0,
    'N1_inventory_complete': True,
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
    'plant_acceptance': False, 'hard_realtime': False}
create(receipt_path, receipt)
create(DEST / receipt_path.relative_to(ROOT), receipt)
final_reads = confirm(population(ROOT))
print(json.dumps({**receipt, 'final_receipt_also_verified': True,
                  'complete_final_reads': final_reads}, ensure_ascii=False))
