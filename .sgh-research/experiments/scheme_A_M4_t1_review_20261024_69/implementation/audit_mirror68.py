#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'scheme_A_M4_t1_component_wiring_20261024_68'
MIRROR = Path('/home/trevor/MPC') / SOURCE.name


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


expected = {str(p.relative_to(SOURCE)): pin(p) for p in SOURCE.rglob('*')
            if p.is_file() and p.relative_to(SOURCE).parts[0] != 'build'}
actual = {str(p.relative_to(MIRROR)): pin(p) for p in MIRROR.rglob('*') if p.is_file()}
missing = sorted(expected.keys() - actual.keys())
extra = sorted(actual.keys() - expected.keys())
changed = sorted(key for key in expected.keys() & actual.keys() if expected[key] != actual[key])
documents = {
    'documents/final_verification_v1.json': 'evidence/final_verification_v1.json',
    'documents/implementation_plan_v1.md': 'postrun/implementation_plan_v1.md',
    'documents/t1_handoff_to_t2_v1.json': 'postrun/t1_handoff_to_t2_v1.json',
    'documents/verification_v1.json': 'evidence/t1_wiring/verification_v1.json',
    'documents/方案A_第68批_T1组件接线_执行报告_2026-10-24.md': 'postrun/方案A_第68批_T1组件接线_执行报告_2026-10-24.md',
}
derived = {key: {'source': value, 'matches': actual.get(key) == expected.get(value)}
           for key, value in documents.items()}
report = {'schema': 'T1-old-mirror-independent-two-way-population-review-v69',
    'source_excludes': ['build/'], 'source_expected_files': len(expected),
    'mirror_actual_files': len(actual), 'missing': missing, 'changed': changed,
    'extra': extra, 'derived_documents': derived,
    'only_declared_document_copies_extra': set(extra) == set(documents),
    'originals_currently_match': not missing and not changed,
    'snapshot_scope': 'Read-only current Linux MPC mirror; Windows Documents folder was not accessed',
    'original_final_receipt_file_count': json.loads((SOURCE / 'evidence/final_verification_v1.json').read_text())['mirror']['files']}
with (ROOT / 'evidence/mirror68_review_v1.json').open('x') as stream:
    stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False))
