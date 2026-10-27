#!/usr/bin/env python3
"""Protect the reviewed session and innovation register without altering them."""
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
    p = Path(path)
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return {'bytes': p.stat().st_size, 'sha256': h.hexdigest()}


files, batches = {}, []
for number in range(98, 124):
    matches = [p for p in BASE.glob('*_' + str(number)) if p.is_dir()]
    assert len(matches) == 1, matches
    root = matches[0]
    batches.append(str(root))
    for parent, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith('build') and d not in ('cmake_build', 'CMakeFiles', '__pycache__')]
        for name in names:
            p = Path(parent) / name
            if p.is_file():
                files[str(p)] = pin(p)
    for p in (root / 'implementation').glob('*registry*.json'):
        registry = json.loads(p.read_bytes())
        for entry in registry.get('roles', {}).values():
            for name in [entry.get('binary'), (entry.get('source_bundle') or {}).get('path')]:
                if name and Path(name).is_file():
                    files[name] = pin(name)
    for p in (root / 'implementation').glob('*registration*.json'):
        registration = json.loads(p.read_bytes())
        for key in ('contract', 'registry', 'topics', 'action_table'):
            name = registration.get(key)
            if isinstance(name, str) and Path(name).is_file():
                files[name] = pin(name)
register = REPO / '.sgh-research/research-innovations.md'
files[str(register)] = pin(register)
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
workspace = {str(REPO / row[3:]): pin(REPO / row[3:]) for row in status.splitlines() if (REPO / row[3:]).is_file()}
output = ROOT / 'evidence/inputs_before_v1.json'
output.parent.mkdir(parents=True)
with output.open('x') as stream:
    stream.write(json.dumps({'schema': 'schemeA-session-code-review-inputs-v124',
        'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'batches': batches, 'files': files, 'count': len(files), 'workspace_files': workspace,
        'git_porcelain': status,
        'scope': '98–123 non-build files, innovation register, registered ELF/bundle and referenced contract/topics; not all old intermediate builds or dirty submodule contents'}, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'protected_files': len(files), 'protected_bytes': sum(v['bytes'] for v in files.values()),
                  'workspace_files': len(workspace), 'owned_runs': 0}))
