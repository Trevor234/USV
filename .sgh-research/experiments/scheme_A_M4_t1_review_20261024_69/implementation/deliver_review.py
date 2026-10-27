#!/usr/bin/env python3
"""Deliver the declared review population, retaining build originals on USV."""
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
    return {str(path.relative_to(root)): pin(path) for path in sorted(root.rglob('*'))
            if path.is_file() and path.relative_to(root).parts[0] != 'build'}


def create(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def confirm(expected):
    attempts = []
    consecutive = 0
    for index in range(1, 6):
        actual = population(DEST)
        diff = {'source_only': sorted(expected.keys() - actual.keys()),
                'destination_only': sorted(actual.keys() - expected.keys()),
                'changed': sorted(key for key in expected.keys() & actual.keys() if expected[key] != actual[key])}
        matched = all(not value for value in diff.values())
        attempts.append({'read': index, 'matched': matched, 'differences': diff})
        consecutive = consecutive + 1 if matched else 0
        if consecutive == 2:
            assert population(ROOT) == expected, 'source changed during delivery'
            return attempts
        time.sleep(0.5)
    raise AssertionError(json.dumps({'bounded_readbacks': attempts}))


assert DEST.parent.is_dir() and not DEST.exists(), 'new destination required'
inventory = ROOT / 'evidence/package_inventory_v1.json'
receipt_path = ROOT / 'evidence/delivery_to_MPC_v1.json'
assert not inventory.exists() and not receipt_path.exists()
expected = population(ROOT)
create(inventory, {'schema': 'M4-T1-review-delivery-inventory-v69',
    'source_excludes': ['build/'], 'excludes_self_and_receipt': True,
    'retained_build_inventory': 'evidence/retained_build_inventory_v1.json',
    'files': expected, 'count': len(expected), 'bytes': sum(row['bytes'] for row in expected.values())})
expected = population(ROOT)
shutil.copytree(ROOT, DEST, ignore=lambda folder, names: ['build'] if Path(folder) == ROOT and 'build' in names else [])
reads = confirm(expected)
receipt = {'schema': 'M4-T1-review-MPC-delivery-v69',
    'written_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
    'source': str(ROOT), 'destination': str(DEST), 'excludes': ['build/'],
    'final_files_including_receipt': len(expected) + 1,
    'bytes_before_receipt': sum(row['bytes'] for row in expected.values()),
    'exact_declared_population': True, 'sha256_mismatches': [], 'readbacks_before_receipt': reads,
    'old_deliveries_overwritten': False, 'new_owned_runs': 0,
    'reviewed25_and3_mutations_passed': True, 'all23_semantic_coverage_signed_off': False,
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False}
create(receipt_path, receipt)
create(DEST / receipt_path.relative_to(ROOT), receipt)
final_reads = confirm(population(ROOT))
print(json.dumps({**receipt, 'receipt_also_verified': True, 'final_complete_readbacks': final_reads}, ensure_ascii=False))
