#!/usr/bin/env python3
"""Preserve the initial readback failure and confirm the complete MPC mirror."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = Path('/home/trevor/MPC') / ROOT.name
ERROR = ROOT / 'evidence/delivery_initial_failure_v1.json'
INVENTORY = ROOT / 'evidence/package_inventory_v2.json'
RECEIPT = ROOT / 'evidence/delivery_readback_v2.json'


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def population(root):
    return {str(p.relative_to(root)): pin(p)
            for p in sorted(root.rglob('*')) if p.is_file()}


def create(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def differences(source, mirror):
    return {'source_only': sorted(source.keys() - mirror.keys()),
            'mirror_only': sorted(mirror.keys() - source.keys()),
            'changed': sorted(k for k in source.keys() & mirror.keys()
                              if source[k] != mirror[k])}


def confirm(expected, passes=2):
    readings = []
    consecutive = 0
    for attempt in range(1, 6):
        mirror = population(DESTINATION)
        diff = differences(expected, mirror)
        matched = all(not values for values in diff.values())
        readings.append({'read': attempt, 'matched': matched, 'differences': diff})
        consecutive = consecutive + 1 if matched else 0
        if consecutive == passes:
            assert population(ROOT) == expected, 'Source changed during delivery verification'
            return readings
        time.sleep(0.5)
    raise AssertionError(json.dumps({'bounded_readback_failed': readings}))


assert not any(p.exists() for p in (ERROR, INVENTORY, RECEIPT))
initial_source = population(ROOT)
initial_mirror = population(DESTINATION)
initial_diff = differences(initial_source, initial_mirror)
# Only this newly authored follow-up script may be absent in the old mirror.
assert initial_diff == {'source_only': [str(Path(__file__).relative_to(ROOT))],
                        'mirror_only': [], 'changed': []}, initial_diff
create(ERROR, {
    'schema': 'W2-MPC-initial-final-readback-failure-v1',
    'initial_command': 'implementation/deliver_to_mpc.py',
    'initial_returncode': 1,
    'initial_assertion': 'Final receipt readback differs',
    'initial_difference_details_captured': False,
    'subsequent_independent_readback': {
        'files_at_that_time': 882, 'source_only': [], 'mirror_only': [],
        'changed': [], 'source_and_mirror_identical': True,
        'files_rewritten_to_obtain_this_match': False,
    },
    'cause': 'undetermined; immediate read failed and later reads matched',
    'owned_run_repeated': False,
    'original_inventory_and_receipt_preserved': True,
})
rows = population(ROOT)
create(INVENTORY, {
    'schema': 'W2-owned-takeover-package-inventory-v66-recheck',
    'excludes_self_and_delivery_readback_v2_receipt': True,
    'includes_original_inventory_receipt_and_failure_record': True,
    'count': len(rows), 'bytes': sum(row['bytes'] for row in rows.values()),
    'files': rows,
})
expected = population(ROOT)
for relative, row in expected.items():
    source_path = ROOT / relative
    mirror_path = DESTINATION / relative
    if mirror_path.exists():
        assert pin(mirror_path) == row, ('Refuse to overwrite', relative)
    else:
        assert mirror_path.parent.is_dir()
        shutil.copy2(source_path, mirror_path)
before_receipt = confirm(expected)
receipt = {
    'schema': 'W2-owned-takeover-MPC-readback-v2',
    'written_at': datetime.datetime.now().astimezone().isoformat(),
    'source': str(ROOT), 'destination': str(DESTINATION),
    'final_files_including_receipt': len(expected) + 1,
    'bytes_before_receipt': sum(row['bytes'] for row in expected.values()),
    'exact_population': True, 'sha256_mismatches': [],
    'consecutive_complete_readbacks_before_receipt': 2,
    'readbacks': before_receipt,
    'old_files_overwritten': False,
    'initial_readback_failure_preserved': str(ERROR.relative_to(ROOT)),
    'original_inventory_and_receipt_preserved': True,
    'inventory': str(INVENTORY.relative_to(ROOT)),
    'owned_W2_qualified': True,
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
}
create(RECEIPT, receipt)
create(DESTINATION / RECEIPT.relative_to(ROOT), receipt)
final_reads = confirm(population(ROOT))
print(json.dumps({**receipt, 'final_receipt_also_matched': True,
                  'complete_final_readbacks': final_reads}, ensure_ascii=False))
