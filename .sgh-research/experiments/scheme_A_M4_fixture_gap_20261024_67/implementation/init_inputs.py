#!/usr/bin/env python3
"""Lock the current batch and untouched workspace before the applicability audit."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
PREVIOUS = ROOT.parent / 'scheme_A_W2_owned_takeover_20261023_66'
AUTHOR = PREVIOUS / 'implementation/w2_author'


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


assert PREVIOUS.is_dir()
previous = {str(p): pin(p) for p in sorted(PREVIOUS.rglob('*')) if p.is_file()}
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'],
                                 cwd=REPO, text=True)
workspace = {}
for row in status.splitlines():
    path = REPO / row[3:]
    if path.is_file():
        workspace[str(path)] = pin(path)
create(ROOT / 'evidence/inputs_before_v1.json', {
    'schema': 'M4-case-applicability-input-protection-v67',
    'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
    'previous_batch_full_regular_file_population': previous,
    'previous_batch_files': len(previous),
    'workspace_files': workspace, 'status_porcelain': status,
    'scope': 'Full ordinary-file population of batch66; current dirty ordinary files and git status; no submodule-content scan',
})
bundle = json.loads((PREVIOUS / 'evidence/freeze_and_build/source_bundle.json').read_text())
assert set(bundle['files']) == {str(p.relative_to(AUTHOR)) for p in AUTHOR.rglob('*') if p.is_file()}
for relative, row in bundle['files'].items():
    assert pin(AUTHOR / relative) == {k: row[k] for k in ('bytes', 'sha256')}
shutil.copytree(AUTHOR, ROOT / 'implementation/current_author')
create(ROOT / 'evidence/current_source_copy_v1.json', {
    'schema': 'M4-applicability-current-source-copy-v1', 'source': str(AUTHOR),
    'private_copy': str(ROOT / 'implementation/current_author'),
    'file_count': len(bundle['files']),
    'bundle': {'path': str(PREVIOUS / 'evidence/freeze_and_build/source_bundle.json'),
               **pin(PREVIOUS / 'evidence/freeze_and_build/source_bundle.json')},
    'source_exact': True, 'registered_owned_execution_source': False,
})
(ROOT / 'documents').mkdir(exist_ok=True)
(ROOT / 'postrun').mkdir(exist_ok=True)
with (ROOT / 'CURRENT.md').open('x') as stream:
    stream.write('# 第67批：M4逐case适用性与Fixture差集\n\n日期：2026-10-24。\n\n'
                 '第66批W2子项通过，原件完整保护。本批正在逐项绑定原47要求、历史证据、源码及合同，'
                 '随后只验证确切差集。当前未新增owned运行，未修改生产源码。\n\n'
                 '完整M4/F6/P1/plant/硬实时/研究结论仍为false。生产B保持MANUAL＋RC覆写。\n')
print(json.dumps({'previous_files_protected': len(previous), 'workspace_files': len(workspace),
                  'current_source_files': len(bundle['files'])}))
