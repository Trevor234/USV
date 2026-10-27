#!/usr/bin/env python3
"""Read-only MPC verification; verification receipts write only in USV."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
MIRROR = Path('/home/trevor/MPC') / ROOT.name
MANIFEST = 'evidence/delivery_population_v1.json'
RECEIPT = 'evidence/delivery_to_MPC_v1.json'


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


parser = argparse.ArgumentParser()
parser.add_argument('--receipt', action='store_true')
args = parser.parse_args()
population = json.loads((ROOT / MANIFEST).read_bytes())
expected = {**population['files'], MANIFEST: pin(ROOT / MANIFEST)}
if args.receipt:
    expected[RECEIPT] = pin(ROOT / RECEIPT)
rounds = []
for number in range(2):
    actual = {str(p.relative_to(MIRROR)) for p in MIRROR.rglob('*') if p.is_file()}
    mismatches = [p for p, record in expected.items() if not (MIRROR / p).is_file() or pin(MIRROR / p) != record]
    assert actual == set(expected) and not mismatches, (actual ^ set(expected), mismatches)
    rounds.append({'round': number + 1, 'files_read': len(expected), 'exact_population': True, 'mismatches': []})
out = {'schema': 'M4-plan125-MPC-readback-v1',
       'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
       'source': str(ROOT), 'mirror': str(MIRROR), 'exact_population': True,
       'files_verified': len(expected), 'payload_bytes': population['payload_bytes'],
       'rounds': rounds, 'receipt_included': args.receipt,
       'excluded_build_files': population['excluded_build_files'],
       'owned_runs_this_batch': 0,
       'qualification': {k: False for k in ['M4', 'F6', 'P1', 'plant', 'hard_realtime']}}
target = ROOT / ('evidence/delivery_receipt_readback_v1.json' if args.receipt else RECEIPT)
with target.open('x') as stream:
    stream.write(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'files_verified': len(expected), 'exact_population': True,
                  'receipt_included': args.receipt, 'rounds': 2}, ensure_ascii=False))
