#!/usr/bin/env python3
"""Protect batch69, batch67 and current dirty ordinary workspace files (S1 inputs)."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]
B69 = BASE / 'scheme_A_M4_t1_review_20261024_69'
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


(ROOT / 'evidence').mkdir(parents=True, exist_ok=True)
prior69 = population(B69)
prior67 = population(B67)
prior68_evidence = {rel: pin(B68 / rel) for rel in [
    'evidence/init_inputs_v1.json', 'evidence/final_verification_v1.json',
    'evidence/t1_wiring/verification_v1.json']}
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
dirty = {str(REPO / row[3:]): pin(REPO / row[3:]) for row in status.splitlines()
         if (REPO / row[3:]).is_file()}
data = {'schema': 'M4-T1-S1-semantic-supplication-inputs-v70',
        'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'batch69_complete_regular_files_including_build': prior69,
        'batch67_complete_regular_files': prior67,
        'batch68_reference_evidence_files': prior68_evidence,
        'workspace_files': dirty, 'git_status_porcelain': status,
        'scope': 'Full ordinary-file populations of 69 (incl. retained build) and 67; three 68 evidence JSONs for continuity; current dirty ordinary files. No claim about unscanned submodule contents or pre-existing history.'}
with (ROOT / 'evidence/inputs_before_v1.json').open('x') as stream:
    stream.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
# Self-contained spec source for the runner: the 68 ATOM_MAP/COMPANIONS/MUTATIONS
# exactly as reviewed (and re-verified) by batch 69.
for directory in ('scripts',):
    shutil.copytree(B69 / 'evidence/reviewed68' / directory, ROOT / 'evidence/spec68' / directory,
                    dirs_exist_ok=True)
print(json.dumps({'protected69_files': len(prior69),
                  'protected69_bytes': sum(row['bytes'] for row in prior69.values()),
                  'protected67_files': len(prior67), 'workspace_files': len(dirty)}))
