#!/usr/bin/env python3
from pathlib import Path
import datetime, hashlib, json, shutil
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'scheme_A_M4_t2_r0_protocol_20261024_75/implementation/t2_author_r0'
TARGET = ROOT / 'implementation/t2_author_r1'
def pin(p):
    raw = p.read_bytes(); return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
assert not TARGET.exists()
shutil.copytree(SOURCE, TARGET, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
files = {str(p.relative_to(TARGET)): pin(p) for p in sorted(TARGET.rglob('*')) if p.is_file()}
record = {'schema':'M4-T2-R1-author-derivation-v76',
          'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
          'source': str(SOURCE), 'target': str(TARGET), 'files': len(files),
          'regulator_source_sha256_before_r1': files['observer/src/shadow/regulator_owned_execute.cpp']['sha256'],
          'claim':'byte-identical copy of R0 rev9 tree; R1 edits (regulator schedule transition, pair ledger, witness localization, fixture counters) land after this record; the Regulator source SHA changes HERE by design (74 review R1)'}
(ROOT/'evidence/r1_author_derivation_v1.json').open('x').write(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'files': len(files), 'regulator_before': record['regulator_source_sha256_before_r1'][:16]}))
