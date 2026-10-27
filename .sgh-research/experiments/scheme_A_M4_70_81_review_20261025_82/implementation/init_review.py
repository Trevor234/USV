#!/usr/bin/env python3
"""Read-only protection population and create-only review material intake."""
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


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


batches, files, registered = [], {}, []
for number in range(70, 82):
    matches = [p for p in BASE.glob('*_' + str(number)) if p.is_dir()]
    assert len(matches) == 1, matches
    root = matches[0]
    batches.append(str(root))
    for parent, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith('build') and d not in ('cmake_build', 'CMakeFiles', '__pycache__')]
        for name in names:
            path = Path(parent) / name
            if path.is_file():
                files[str(path)] = pin(path)
    for path in (root / 'implementation').glob('*registry*.json'):
        registry = json.loads(path.read_bytes())
        for role in registry.get('roles', {}).values():
            for name in [role.get('binary'), (role.get('source_bundle') or {}).get('path')]:
                if name and Path(name).is_file():
                    files[name] = pin(name)
                    registered.append(name)

status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
workspace = {str(REPO / line[3:]): pin(REPO / line[3:]) for line in status.splitlines()
             if (REPO / line[3:]).is_file()}
instructions = {}
for parent in [Path('/home'), Path('/home/trevor'), REPO, REPO / '.sgh-research', BASE, ROOT]:
    path = parent / 'AGENTS.md'
    if path.is_file():
        instructions[str(path)] = path.read_text()
create(ROOT / 'evidence/inputs_before_v1.json', {
    'schema': 'M4-70-81-independent-review-inputs-v82',
    'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
    'batches': batches, 'files': files, 'count': len(files), 'registered_artifacts': sorted(set(registered)),
    'workspace_files': workspace, 'git_porcelain': status,
    'scope': '70–81 non-build ordinary files including retained runs, plus registered ELF/bundle; does not claim all historical intermediate builds or dirty submodule contents',
    'ancestor_instructions': instructions})

copied = []
for label, origin in [('boundary', Path('/tmp/review81_boundary')),
                      ('protocol', Path('/tmp/review75_protocol')),
                      ('runtime', Path('/tmp/review76_runtime'))]:
    for source in sorted(origin.rglob('*')):
        if not source.is_file() or source.suffix not in ('.py', '.cpp', '.sh', '.json', '.md', '.txt', '.stdout', '.stderr'):
            continue
        raw = source.read_bytes()
        dest = ROOT / 'evidence/independent_reviews' / label / source.relative_to(origin)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream:
            stream.write(raw)
        assert dest.read_bytes() == raw
        copied.append({'original': str(source), 'saved': str(dest.relative_to(ROOT)), **pin(dest)})
create(ROOT / 'evidence/review_materials_v1.json', copied)
print(json.dumps({'protected_inputs': len(files), 'protected_bytes': sum(v['bytes'] for v in files.values()),
                  'workspace_files': len(workspace), 'review_materials': len(copied),
                  'ancestor_instructions': list(instructions), 'owned_runs': 0}, ensure_ascii=False))
