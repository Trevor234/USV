#!/usr/bin/env python3
"""Create one complete new MPC mirror and verify every byte by readback."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = Path('/home/trevor/MPC') / ROOT.name
INVENTORY = ROOT / 'evidence/package_inventory_v1.json'
RECEIPT = ROOT / 'evidence/delivery_to_MPC_v1.json'


def pin(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def population(root):
    return {str(p.relative_to(root)): pin(p)
            for p in sorted(root.rglob('*')) if p.is_file()}


def create(path, data):
    with path.open('x') as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


assert DESTINATION.parent.is_dir(), 'MPC mount/directory unavailable'
assert not DESTINATION.exists(), 'Refusing to overwrite an existing MPC package'
assert not INVENTORY.exists() and not RECEIPT.exists(), 'Delivery is create-only'
assert not any(p.is_symlink() for p in ROOT.rglob('*')), 'Inspect links before packaging'
verification = json.loads((ROOT / 'evidence/final_verification_v1.json').read_text())
for record in verification['identity_pins'].values():
    assert pin(record['path']) == {k: record[k] for k in ('bytes', 'sha256')}
run_inventory = json.loads((ROOT / 'evidence/owned_run_inventory_v1.json').read_text())
assert population(ROOT / 'implementation/runs/W2_01') == run_inventory['files']
rows = population(ROOT)
create(INVENTORY, {
    'schema': 'W2-owned-takeover-package-inventory-v66',
    'excludes_self_and_delivery_receipt': True,
    'count': len(rows), 'bytes': sum(row['bytes'] for row in rows.values()),
    'files': rows,
})
source = population(ROOT)
shutil.copytree(ROOT, DESTINATION)
assert population(DESTINATION) == source, 'MPC population/SHA readback differs'
receipt = {
    'schema': 'W2-owned-takeover-MPC-delivery-v66',
    'written_at': datetime.datetime.now().astimezone().isoformat(),
    'source': str(ROOT), 'destination': str(DESTINATION),
    'files_before_receipt': len(source),
    'final_files_including_receipt': len(source) + 1,
    'bytes_before_receipt': sum(row['bytes'] for row in source.values()),
    'exact_population': True, 'sha256_mismatches': [],
    'overwritten_existing_files': False,
    'receipt_excluded_from_initial_population': True,
    'run_id': run_inventory['run_id'],
    'owned_W2_qualified': True,
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
    'plant_acceptance': False, 'hard_realtime': False,
    'mirror_is_evidence_copy_not_new_registered_execution_source': True,
}
create(RECEIPT, receipt)
create(DESTINATION / RECEIPT.relative_to(ROOT), receipt)
assert population(ROOT) == population(DESTINATION), 'Final receipt readback differs'
print(json.dumps(receipt, ensure_ascii=False))
