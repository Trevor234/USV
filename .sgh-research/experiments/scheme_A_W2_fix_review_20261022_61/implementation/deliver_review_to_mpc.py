#!/usr/bin/env python3
"""Create one new MPC review mirror; do not overwrite any existing package."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = Path('/home/trevor/MPC') / ROOT.name
INVENTORY = ROOT / 'evidence/package_inventory_v1.json'
RECEIPT = ROOT / 'evidence/delivery_to_MPC_v1.json'


def population(root):
    rows = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            data = path.read_bytes()
            rows[str(path.relative_to(root))] = {
                'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return rows


assert not DESTINATION.exists(), 'Refusing to overwrite an existing MPC package'
assert not INVENTORY.exists() and not RECEIPT.exists()
rows = population(ROOT)
INVENTORY.write_text(json.dumps({'schema': 'W2-fix-review-package-inventory-v1',
    'excludes_self_and_delivery_receipt': True, 'files': rows,
    'count': len(rows), 'bytes': sum(row['bytes'] for row in rows.values())},
    ensure_ascii=False, indent=2) + '\n')
source = population(ROOT)
shutil.copytree(ROOT, DESTINATION)
mirror = population(DESTINATION)
assert mirror == source, 'MPC readback population or SHA mismatch'
receipt = {
    'schema': 'W2-fix-review-MPC-delivery-v1',
    'written_at': datetime.datetime.now().astimezone().isoformat(),
    'source': str(ROOT), 'destination': str(DESTINATION),
    'files_before_receipt': len(source),
    'bytes_before_receipt': sum(row['bytes'] for row in source.values()),
    'exact_population': True, 'sha256_mismatches': [],
    'overwritten_existing_files': False,
    'receipt_excluded_from_initial_population': True,
}
raw = json.dumps(receipt, ensure_ascii=False, indent=2) + '\n'
RECEIPT.write_text(raw)
(DESTINATION / RECEIPT.relative_to(ROOT)).write_text(raw)
assert population(ROOT) == population(DESTINATION)
print(json.dumps({**receipt, 'final_files_including_receipt': len(source) + 1},
                 ensure_ascii=False))
