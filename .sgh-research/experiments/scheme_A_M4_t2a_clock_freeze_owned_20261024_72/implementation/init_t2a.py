#!/usr/bin/env python3
"""Protect batch71 (pre-run), batch67 and dirty workspace files (T2-A inputs)."""
from pathlib import Path
import datetime, hashlib, json, subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]

def pin(path):
    h = hashlib.sha256()
    with path.open('rb') as s:
        for chunk in iter(lambda: s.read(1024*1024), b''):
            h.update(chunk)
    return {'bytes': path.stat().st_size, 'sha256': h.hexdigest()}

def population(root):
    return {str(p): pin(p) for p in sorted(root.rglob('*')) if p.is_file()}

prior71 = population(BASE / 'scheme_A_M4_t2_action_freeze_20261024_71')
prior67 = population(BASE / 'scheme_A_M4_fixture_gap_20261024_67')
status = subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=REPO,text=True)
dirty = {str(REPO/r[3:]): pin(REPO/r[3:]) for r in status.splitlines() if (REPO/r[3:]).is_file()}
data = {'schema':'M4-T2A-owned-inputs-v72',
        'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'batch71_complete_regular_files_pre_run': prior71, 'batch67_complete_regular_files': prior67,
        'workspace_files': dirty, 'git_status_porcelain': status,
        'scope':'71 captured BEFORE the registered T2A run creates runs/T2A_01; 67 full; dirty workspace files.'}
(ROOT/'evidence/inputs_before_v1.json').open('x').write(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'protected71_files':len(prior71),'protected67_files':len(prior67),'workspace_files':len(dirty)}))
