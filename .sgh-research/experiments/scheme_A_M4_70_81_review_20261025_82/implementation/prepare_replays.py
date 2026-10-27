#!/usr/bin/env python3
"""Create-only replays and exact recovered P01 source population, not a new freeze."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
OUT = ROOT / 'evidence/replay01'
OUT.mkdir(parents=True)


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def create(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


materials = []
families = {'boundary': Path('/tmp/review81_boundary'),
            'protocol': Path('/tmp/review75_protocol'),
            'runtime': Path('/tmp/review76_runtime')}
for family, origin in families.items():
    for source in sorted(origin.rglob('*')):
        if not source.is_file() or source.suffix not in ('.py', '.cpp', '.hpp', '.sh', '.json', '.md', '.txt', '.stdout', '.stderr'):
            continue
        raw = source.read_bytes()
        dest = ROOT / 'evidence/independent_reviews_final' / family / source.relative_to(origin)
        create(dest, raw)
        materials.append({'source': str(source), 'saved': str(dest.relative_to(ROOT)), **pin(raw)})

scripts = {'boundary': ['extract_timeline.py', 'probe_audit.py', 'probe_driver_release.py'],
           'protocol': ['probe.py', 'fixture_gate_probe.py', 'probe_t2a_predicates.py', 'validate_t2b_p01.py'],
           'runtime': ['probe_pair.py', 'replay_witness.cpp']}
derivations = []
for family, names in scripts.items():
    for name in names:
        source = families[family] / name
        raw = source.read_bytes()
        derived = raw.replace(str(families[family]).encode(), str(OUT / family).encode())
        dest = OUT / family / name
        create(dest, derived)
        derivations.append({'source': str(source), 'destination': str(dest.relative_to(ROOT)),
                            'original': pin(raw), 'derived': pin(derived),
                            'change': 'only private output directory relocation'})

bundle = json.loads((BASE / 'scheme_A_M4_t2_r2_driver_20261025_78/evidence/freeze_rev11/source_bundle.json').read_bytes())
old_tree = BASE / 'scheme_A_M4_t2b_flush_20261025_80/implementation/t2_author_r4'
recovered = ROOT / 'evidence/recovered_P01_registered_sources'
population = {}
for relative, record in bundle['files'].items():
    source = old_tree / relative
    raw = source.read_bytes()
    assert pin(raw) == {k: record[k] for k in ('bytes', 'sha256')}, relative
    dest = recovered / relative
    create(dest, raw)
    population[relative] = {'original_registered_path': record['path'], 'matching_copy': str(source),
                            'recovered': str(dest.relative_to(ROOT)), **pin(raw)}
assert len(population) == 103
for name, value in [
    ('review_materials_final_v1.json', materials),
    ('replay_derivations_v1.json', derivations),
    ('recovered_source_population_v1.json', {'files': population, 'count': len(population),
        'scope': 'exact bytes matching the P01 recorded bundle population, recovered from retained 80/r4; no old paths restored, no old registration changed, no missing ELF inferred'})]:
    create(ROOT / 'evidence' / name, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())
print(json.dumps({'review_materials': len(materials), 'replay_sources': len(derivations),
                  'exact_recovered_source_files': len(population), 'owned_runs': 0}))
