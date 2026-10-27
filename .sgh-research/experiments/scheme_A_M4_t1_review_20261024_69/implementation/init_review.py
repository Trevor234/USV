#!/usr/bin/env python3
"""Protect batch68, batch67, and current dirty ordinary workspace files."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]
B68 = BASE / 'scheme_A_M4_t1_component_wiring_20261024_68'
B67 = BASE / 'scheme_A_M4_fixture_gap_20261024_67'


def pin(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return {'bytes': path.stat().st_size, 'sha256': h.hexdigest()}


def population(root):
    return {str(p): pin(p) for p in sorted(root.rglob('*')) if p.is_file()}


(ROOT / 'evidence').mkdir(parents=True)
(ROOT / 'documents').mkdir()
(ROOT / 'postrun').mkdir()
prior68 = population(B68)
prior67 = population(B67)
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
dirty = {str(REPO / row[3:]): pin(REPO / row[3:]) for row in status.splitlines()
         if (REPO / row[3:]).is_file()}
data = {'schema': 'M4-T1-independent-review-inputs-v69',
        'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'batch68_complete_regular_files_including_build': prior68,
        'batch67_complete_regular_files': prior67,
        'workspace_files': dirty, 'git_status_porcelain': status,
        'scope': 'Full ordinary-file populations of 68/67; current dirty ordinary files; no claim about unscanned submodule contents or changes before this review'}
with (ROOT / 'evidence/inputs_before_v1.json').open('x') as stream:
    stream.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
for directory in ('scripts', 'implementation', 'postrun'):
    shutil.copytree(B68 / directory, ROOT / 'evidence/reviewed68' / directory)
for rel in ['evidence/init_inputs_v1.json', 'evidence/final_verification_v1.json',
            'evidence/t1_wiring/verification_v1.json']:
    target = ROOT / 'evidence/reviewed68' / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(B68 / rel, target)
print(json.dumps({'protected68_files': len(prior68),
                  'protected68_bytes': sum(row['bytes'] for row in prior68.values()),
                  'protected67_files': len(prior67), 'workspace_files': len(dirty)}))
