#!/usr/bin/env python3
"""Derive the batch-71 T2 owned author tree from frozen66 (= 67 current_author).

Byte copy of all 100 files; the frozen provenance chain (66 w2_author -> 67
current_author -> 71 t2_author) is recorded before any S2 edit lands."""
from pathlib import Path
import datetime, hashlib, json, shutil

ROOT = Path(__file__).resolve().parents[1]
B67 = ROOT.parent / 'scheme_A_M4_fixture_gap_20261024_67'
SOURCE = B67 / 'implementation/current_author'
TARGET = ROOT / 'implementation/t2_author'

def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

assert not TARGET.exists(), 't2_author already derived'
shutil.copytree(SOURCE, TARGET)
files = {str(p.relative_to(TARGET)): pin(p) for p in sorted(TARGET.rglob('*')) if p.is_file()}
record = {'schema': 'M4-T2-author-derivation-v71',
          'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
          'source': {'path': str(SOURCE), 'files': len(files)},
          'target': {'path': str(TARGET), 'files': len(files)},
          'regulator_source_sha256': files['observer/src/shadow/regulator_owned_execute.cpp']['sha256'],
          'claim': 'byte-identical copy of the 67th-batch current_author (frozen66 lineage); S2 edits land only after this record'}
assert record['regulator_source_sha256'] == 'dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5'
with (ROOT / 'evidence/t2_author_derivation_v1.json').open('x') as stream:
    stream.write(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'files': len(files)}))
