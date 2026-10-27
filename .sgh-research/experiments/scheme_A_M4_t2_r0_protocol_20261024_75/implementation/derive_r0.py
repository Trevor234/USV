#!/usr/bin/env python3
"""Derive the R0 author tree from batch-72 rev8 (byte copy; R0 edits land after this record)."""
from pathlib import Path
import datetime, hashlib, json, shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation/t2_author_rev8'
TARGET = ROOT / 'implementation/t2_author_r0'

def pin(p):
    raw = p.read_bytes(); return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

assert not TARGET.exists()
shutil.copytree(SOURCE, TARGET)
files = {str(p.relative_to(TARGET)): pin(p) for p in sorted(TARGET.rglob('*')) if p.is_file()}
record = {'schema':'M4-T2-R0-author-derivation-v75',
          'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
          'source': str(SOURCE), 'target': str(TARGET), 'files': len(files),
          'regulator_source_sha256': files['observer/src/shadow/regulator_owned_execute.cpp']['sha256'],
          'claim':'byte-identical copy of batch-72 rev8; R0 edits (driver/contract/fixture/audit) land after this record'}
assert record['regulator_source_sha256'] == 'dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5'
(ROOT/'evidence/r0_author_derivation_v1.json').open('x').write(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'files': len(files)}))
