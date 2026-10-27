#!/usr/bin/env python3
"""Protect reviewed 110–114 populations before independent design adjudication."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]


def pin(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return {'bytes': path.stat().st_size, 'sha256': h.hexdigest()}


batches, files = [], {}
for number in range(110, 115):
    candidates = [p for p in BASE.glob('*_' + str(number)) if p.is_dir()]
    assert len(candidates) == 1, candidates
    root = candidates[0]
    batches.append(str(root))
    for parent, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith('build') and d not in ('cmake_build', 'CMakeFiles', '__pycache__')]
        for name in names:
            p = Path(parent) / name
            if p.is_file():
                files[str(p)] = pin(p)
    for registry_path in (root / 'implementation').glob('*registry*.json'):
        registry = json.loads(registry_path.read_bytes())
        for entry in registry.get('roles', {}).values():
            for p in [entry.get('binary'), (entry.get('source_bundle') or {}).get('path')]:
                if p and Path(p).is_file():
                    files[p] = pin(p)
    for registration_path in (root / 'implementation').glob('*registration*.json'):
        reg = json.loads(registration_path.read_bytes())
        for key in ('contract', 'topics', 'registry', 'action_table'):
            if reg.get(key) and Path(reg[key]).is_file():
                files[reg[key]] = pin(reg[key])
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
workspace = {str(REPO / row[3:]): pin(REPO / row[3:]) for row in status.splitlines() if (REPO / row[3:]).is_file()}
output = ROOT / 'evidence/inputs_before_v1.json'
output.parent.mkdir(parents=True)
with output.open('x') as stream:
    stream.write(json.dumps({'schema': 'RNW-policy-review-inputs-v115',
        'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'batches': batches, 'files': files, 'count': len(files), 'workspace_files': workspace,
        'git_porcelain': status,
        'scope': '110–114 non-build files including retained runs, registered ELF/bundle and external contract/topics; not every historical intermediate build or dirty submodule content'}, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'protected_files': len(files), 'protected_bytes': sum(v['bytes'] for v in files.values()),
                  'workspace_files': len(workspace), 'owned_runs': 0}))
