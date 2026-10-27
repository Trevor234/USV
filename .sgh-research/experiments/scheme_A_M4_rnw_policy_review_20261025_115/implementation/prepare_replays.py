#!/usr/bin/env python3
"""Copy private review materials and relocate outputs for independent replay."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/replay01'
OUT.mkdir(parents=True)
families = {'clock': Path('/tmp/review114_clock_evidence'),
            'policy': Path('/tmp/review114_authority_policy'),
            'fixture': Path('/tmp/review114_fixture_plan')}


def digest(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def create(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


materials = []
for family, source_root in families.items():
    for path in sorted(source_root.rglob('*')):
        if not path.is_file() or path.suffix not in ('.py', '.cpp', '.json', '.txt', '.md', '.sh', '.hpp'):
            continue
        raw = path.read_bytes()
        dest = ROOT / 'evidence/independent_reviews' / family / path.relative_to(source_root)
        create(dest, raw)
        materials.append({'source': str(path), 'saved': str(dest.relative_to(ROOT)), **digest(raw)})
selected = {'clock': ['analyze.py', 'replay_generate.py'],
            'policy': ['probe.cpp', 'authority_interface.cpp'],
            'fixture': ['probe.py']}
derivations = []
for family, names in selected.items():
    for name in names:
        source = families[family] / name
        raw = source.read_bytes()
        derived = raw.replace(str(families[family]).encode(), str(OUT / family).encode())
        target = OUT / family / name
        create(target, derived)
        derivations.append({'source': str(source), 'target': str(target.relative_to(ROOT)),
                            'original': digest(raw), 'derived': digest(derived),
                            'change': 'only private output directory relocated'})
for name, value in [('review_materials_v1.json', materials), ('replay_derivations_v1.json', derivations)]:
    create(ROOT / 'evidence' / name, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())
print(json.dumps({'material_count': len(materials), 'replay_sources': len(derivations), 'owned_runs': 0}))
