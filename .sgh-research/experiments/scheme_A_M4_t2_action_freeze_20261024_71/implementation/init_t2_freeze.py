#!/usr/bin/env python3
"""Protect batch70, batch67 and current dirty ordinary workspace files (S2 inputs)."""
from pathlib import Path
import datetime, hashlib, json, subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]
B70 = BASE / 'scheme_A_M4_t1_semantic_supp_20261024_70'
B67 = BASE / 'scheme_A_M4_fixture_gap_20261024_67'

def pin(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return {'bytes': path.stat().st_size, 'sha256': h.hexdigest()}

def population(root):
    return {str(p): pin(p) for p in sorted(root.rglob('*')) if p.is_file()}

prior70 = population(B70)
prior67 = population(B67)
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
dirty = {str(REPO / row[3:]): pin(REPO / row[3:]) for row in status.splitlines() if (REPO / row[3:]).is_file()}
data = {'schema': 'M4-T2-action-freeze-inputs-v71',
        'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'batch70_complete_regular_files': prior70, 'batch67_complete_regular_files': prior67,
        'workspace_files': dirty, 'git_status_porcelain': status,
        'scope': 'Full ordinary-file populations of 70 and 67; current dirty ordinary files; no claim about unscanned submodule contents.'}
with (ROOT / 'evidence/inputs_before_v1.json').open('x') as stream:
    stream.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'protected70_files': len(prior70), 'protected67_files': len(prior67), 'workspace_files': len(dirty)}))
