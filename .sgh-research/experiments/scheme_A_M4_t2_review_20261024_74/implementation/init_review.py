#!/usr/bin/env python3
"""Protect selected review populations and all prior raw runs without editing them."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]
NAMES = ['scheme_A_M4_t1_semantic_supp_20261024_70',
         'scheme_A_M4_t2_action_freeze_20261024_71',
         'scheme_A_M4_t2a_clock_freeze_owned_20261024_72',
         'scheme_A_M4_t2b_feasibility_20261024_73']


def pin(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return {'bytes': path.stat().st_size, 'sha256': h.hexdigest()}


files = {}
for name in NAMES:
    for parent, directories, filenames in os.walk(BASE / name):
        directories[:] = [part for part in directories
                          if part not in ('build', 'cmake_build', 'CMakeFiles', '__pycache__')
                          and not part.startswith('build_')]
        for filename in filenames:
            path = Path(parent) / filename
            if path.is_file():
                files[str(path)] = pin(path)
# Include registered executable/bundle identity, even when stored in build dirs.
for name in NAMES:
    for registry_file in (BASE / name / 'implementation').glob('*registry*.json'):
        registry = json.loads(registry_file.read_text())
        for role in registry.get('roles', {}).values():
            for path in [role.get('binary'), (role.get('source_bundle') or {}).get('path')]:
                if path and Path(path).is_file():
                    files[path] = pin(path)
for relative in ['scheme_A_W2_owned_takeover_20261023_66/evidence/owned_audit_v1.json',
                 'scheme_A_M4_t1_review_20261024_69/evidence/final_verification_v1.json',
                 'scheme_A_formal_execute_profile_20261020_47/freeze/M4_fault_matrix_v1.json']:
    path = BASE / relative
    files[str(path)] = pin(path)
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
workspace = {str(REPO / line[3:]): pin(REPO / line[3:]) for line in status.splitlines()
             if (REPO / line[3:]).is_file()}
(ROOT / 'evidence').mkdir(parents=True)
(ROOT / 'documents').mkdir()
(ROOT / 'postrun').mkdir()
data = {'schema': 'M4-T2-independent-review-inputs-v74',
        'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'files': files, 'count': len(files), 'workspace_files': workspace,
        'status_porcelain': status,
        'scope': '70–73 non-build ordinary files including raw runs, plus registered ELF/bundle and selected earlier gates; no claim of all historic build files or submodule content'}
with (ROOT / 'evidence/inputs_before_v1.json').open('x') as stream:
    stream.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
rev8 = BASE / NAMES[2] / 'implementation/t2_author_rev8'
for relative in ['t2_action_contract.py', 't2_scenario_driver_v1.py', 'audit_t2.py',
                 'fixture/t2_fixture_actions.hpp', 'fixture/synthetic_source_m4.cpp']:
    source = rev8 / relative
    if source.is_file():
        target = ROOT / 'evidence/reviewed_rev8' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
print(json.dumps({'protected_files': len(files), 'bytes': sum(row['bytes'] for row in files.values()),
                  'workspace_files': len(workspace)}))
