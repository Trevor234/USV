#!/usr/bin/env python3
"""Protect batch74 (post-delivery), batch72 rev8 tree and dirty workspace files (R0 inputs)."""
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

prior74 = population(BASE / 'scheme_A_M4_t2_review_20261024_74')
prior72 = population(BASE / 'scheme_A_M4_t2a_clock_freeze_owned_20261024_72')
status = subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=REPO,text=True)
dirty = {str(REPO/r[3:]): pin(REPO/r[3:]) for r in status.splitlines() if (REPO/r[3:]).is_file()}
data = {'schema':'M4-T2-R0-protocol-inputs-v75',
        'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'batch74_complete_regular_files': prior74, 'batch72_complete_regular_files': prior72,
        'workspace_files': dirty, 'git_status_porcelain': status,
        'scope':'74 (post-delivery) and 72 full ordinary populations before R0 edits; dirty workspace files.'}
(ROOT/'evidence/inputs_before_v1.json').open('x').write(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'protected74':len(prior74),'protected72':len(prior72),'workspace':len(dirty)}))
