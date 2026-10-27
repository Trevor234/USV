#!/usr/bin/env python3
from pathlib import Path
import datetime, hashlib, json, subprocess
ROOT = Path(__file__).resolve().parents[1]; BASE = ROOT.parent; REPO = ROOT.parents[2]
def pin(path):
    h = hashlib.sha256()
    with path.open('rb') as s:
        for chunk in iter(lambda: s.read(1024*1024), b''): h.update(chunk)
    return {'bytes': path.stat().st_size, 'sha256': h.hexdigest()}
def population(root):
    return {str(p): pin(p) for p in sorted(root.rglob('*')) if p.is_file()}
prior76 = population(BASE / 'scheme_A_M4_t2_r1_runtime_20261024_76')
prior72runs = population(BASE / 'scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation/runs')
status = subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=REPO,text=True)
dirty = {str(REPO/r[3:]): pin(REPO/r[3:]) for r in status.splitlines() if (REPO/r[3:]).is_file()}
data = {'schema':'M4-T2-R2-boundary-inputs-v77',
        'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'batch76_complete_regular_files': prior76, 'batch72_runs': prior72runs,
        'workspace_files': dirty, 'git_status_porcelain': status,
        'scope':'76 full and 72 preserved runs before R2; dirty workspace files.'}
(ROOT/'evidence/inputs_before_v1.json').open('x').write(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'protected76':len(prior76),'protected72runs':len(prior72runs),'workspace':len(dirty)}))
