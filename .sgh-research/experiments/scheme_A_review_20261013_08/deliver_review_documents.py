"""Deliver this prepared review, preserving sealed history and original doc.

The only pre-existing document intentionally replaced is the user's unsealed
10/12 explanation. Its exact original is archived and checked before replacing.
Every other pre-existing destination must already match, otherwise stop.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import tempfile

SOURCE = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_review_20261013_08')
DEST = Path('/home/trevor/MPC/scheme_A_review_20261013_08')
PRIMARY = Path('/home/trevor/MPC/方案A_从基线修复到C3_3_逐步讲解_2026-10-12.md')
REVISION = SOURCE / 'documents/方案A_从基线修复到C3_3_逐步讲解_2026-10-12_修订准备稿.md'
ORIGINAL = SOURCE / 'documents/逐步讲解_20261012_修订前原件.md'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def atomic_replace(path, raw):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.review-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if Path(name).exists():
            Path(name).unlink()

def main():
    pin = json.loads((SOURCE / 'documents/original_document_pin.json').read_text())
    original = ORIGINAL.read_bytes(); revision = REVISION.read_bytes()
    if sha(original) != pin['sha256'] or PRIMARY.read_bytes() != original:
        raise RuntimeError('primary document changed since review; refusing overwrite')
    # Preserve the prepared status separately before marking actual delivery.
    status_path = SOURCE / 'batch_status_2026-10-13.json'
    prepared_status = status_path.read_bytes()
    prepared_path = SOURCE / 'batch_status_2026-10-13_prepared.json'
    if not prepared_path.exists():
        prepared_path.write_bytes(prepared_status)
    status = json.loads(prepared_status)
    status.update(status='review and document revision completed; delivered to MPC',
        MPC_delivery_completed=True,
        primary_document_original_sha256=sha(original),
        primary_document_updated_sha256=sha(revision))
    final_status = (json.dumps(status, ensure_ascii=False, indent=2) + '\n').encode()
    (SOURCE / 'current-status.md').write_text(
        (SOURCE / 'current-status.md').read_text().replace(
            '逐步讲解原件已备份，修订稿、当前实施状态、审查报告与下一计划已准备。',
            '逐步讲解原件已备份，原文件已修订；当前实施状态、审查报告与下一计划已归档MPC。'))
    files = []
    for p in sorted(SOURCE.rglob('*')):
        if p.is_symlink():
            raise RuntimeError('unexpected symlink in new review bundle')
        if p.is_file() and p.name not in ('delivery_manifest.json', 'MPC_document_QA.json'):
            files.append(p)
    for p in files:
        target = DEST / p.relative_to(SOURCE)
        raw = final_status if p == status_path else p.read_bytes()
        if target.exists() and target.read_bytes() != raw:
            raise RuntimeError('existing review destination differs: ' + str(target))
    copied = []
    for p in files:
        target = DEST / p.relative_to(SOURCE); target.parent.mkdir(parents=True, exist_ok=True)
        raw = final_status if p == status_path else p.read_bytes()
        if not target.exists():
            with target.open('xb') as stream:
                stream.write(raw)
        if target.read_bytes() != raw:
            raise RuntimeError('delivery verification differs: ' + str(target))
        copied.append({'source': str(p), 'destination': str(target),
            'bytes': len(raw), 'sha256': sha(raw)})
    if (DEST / ORIGINAL.relative_to(SOURCE)).read_bytes() != original:
        raise RuntimeError('original backup delivery differs')
    # Authorized update of the unsealed explanation, with verified prior backup.
    atomic_replace(PRIMARY, revision)
    if PRIMARY.read_bytes() != revision:
        raise RuntimeError('primary revision verification differs')
    status_path.write_bytes(final_status)
    docs = list(DEST.glob('*.md')) + [PRIMARY]
    missing = []; count = 0
    for doc in docs:
        for target in re.findall(r'\]\((/[^)]+)\)', doc.read_text()):
            count += 1
            if not Path(re.sub(r':\d+$', '', target)).exists():
                missing.append(target)
    qa = {'client_date': '2026-10-13', 'documents': len(docs),
        'absolute_local_links': count, 'missing_links': missing,
        'primary_revision_sha256': sha(revision),
        'backup_sha256': sha(original), 'passed': not missing}
    if missing:
        raise RuntimeError('delivered document links missing: ' + repr(missing))
    manifest = {'schema': 'scheme-A-review-delivery/v1', 'client_date': '2026-10-13',
        'files': copied, 'file_count': len(copied), 'primary_document': str(PRIMARY),
        'original_sha256': sha(original), 'updated_sha256': sha(revision),
        'sealed_history_modified': False, 'business_code_modified': False,
        'stage_qualification_changed': False, 'document_links_passed': True}
    for root in (SOURCE, DEST):
        (root / 'postrun/MPC_document_QA.json').write_text(json.dumps(qa, ensure_ascii=False, indent=2) + '\n')
        (root / 'postrun/delivery_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'delivered_files': len(copied), 'destination': str(DEST),
        'primary_document_updated': str(PRIMARY), 'links_checked': count,
        'missing_links': missing}, ensure_ascii=False))

if __name__ == '__main__':
    main()
