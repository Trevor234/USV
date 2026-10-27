#!/usr/bin/env python3
"""Create-only copies of read-only reviewers' materials; no role processes."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/independent_replay01'
OUT.mkdir()
sources = {'contract': Path('/tmp/review70_71_contract'),
           'clock': Path('/tmp/review72_clock_audit'),
           'boundary': Path('/tmp/review73_boundary_plan')}
manifest = []
for name, origin in sources.items():
    target = ROOT / 'evidence/private_review_originals' / name
    target.mkdir(parents=True)
    for source in sorted(origin.rglob('*')):
        if not source.is_file() or source.suffix not in ('.py', '.cpp', '.sh', '.json', '.txt', '.md'):
            continue
        dest = target / source.relative_to(origin)
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        with dest.open('xb') as stream:
            stream.write(raw)
        assert dest.read_bytes() == raw
        manifest.append({'origin': str(source), 'saved': str(dest.relative_to(ROOT)),
                         'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})

derivations = []
for name, filename in [('contract', 'review.py'), ('clock', 'validate_t2a14.py'),
                       ('clock', 'replay_anchor.cpp'), ('boundary', 'measure.py'),
                       ('boundary', 'epoch_probe.cpp')]:
    source = sources[name] / filename
    dest = OUT / name / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = source.read_bytes()
    if filename == 'measure.py':
        old = b"out = Path('/tmp/review73_boundary_plan')"
        assert raw.count(old) == 1
        raw = raw.replace(old, b'out = Path(__file__).resolve().parent')
    with dest.open('xb') as stream:
        stream.write(raw)
    derivations.append({'source': str(source), 'target': str(dest),
                        'original_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'derived_sha256': hashlib.sha256(raw).hexdigest(),
                        'change': 'measurement output relocated to current script directory' if filename == 'measure.py' else 'byte-for-byte copy'})
for name, value in [('private_review_inputs_v1.json', manifest), ('review_derivations_v1.json', derivations)]:
    with (ROOT / 'evidence' / name).open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'copied_text_artifacts': len(manifest), 'replay_sources': len(derivations),
                  'owned_runs': 0, 'role_processes': 0}))
