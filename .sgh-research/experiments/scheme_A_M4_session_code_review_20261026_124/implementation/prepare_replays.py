#!/usr/bin/env python3
"""Archive independent review material and prepare create-only private replays."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]
OUT = ROOT / 'evidence/replay01'
OUT.mkdir(parents=True)
origins = {'rnw': Path('/tmp/review123_rnw'),
           'epoch_model': Path('/tmp/review123_epoch_model'),
           't3': Path('/tmp/review123_t3_register')}


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def create(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


materials = []
for family, origin in origins.items():
    for source in sorted(origin.rglob('*')):
        if not source.is_file():
            continue
        raw = source.read_bytes()
        if raw.startswith(b'\x7fELF'):
            continue
        dest = ROOT / 'evidence/independent_reviews' / family / source.relative_to(origin)
        create(dest, raw)
        materials.append({'source': str(source), 'saved': str(dest.relative_to(ROOT)), **pin(raw)})
selected = {'rnw': ['replay_checks.py', 'probe_audit.py', 'probe_admission.py',
                    'probe_mapping.cpp', 'probe_receive_skew.cpp'],
            'epoch_model': ['epoch_probe.cpp', 'model_probe.cpp'],
            't3': ['run_asan_probe.py', 'sticky_probe.cpp']}
derivations = []
for family, names in selected.items():
    for name in names:
        raw = (origins[family] / name).read_bytes()
        derived = raw.replace(str(origins[family]).encode(), str(OUT / family).encode())
        if name == 'run_asan_probe.py':
            derived = derived.replace(b'timeout=180', b'timeout=60')
        dest = OUT / family / name
        create(dest, derived)
        derivations.append({'source': str(origins[family] / name), 'target': str(dest.relative_to(ROOT)),
                            'original': pin(raw), 'derived': pin(derived),
                            'change': 'private output relocation; ASAN compiler timeout capped at 60s when applicable'})

# Some component registries have test_binary rather than roles. Protect these
# additional executable/library inputs before this thread's own replays.
before = json.loads((ROOT / 'evidence/inputs_before_v1.json').read_bytes())
extras = {}
for folder in before['batches']:
    for path in (Path(folder) / 'implementation').glob('*registry*.json'):
        registry = json.loads(path.read_bytes())
        names = [registry.get(k) for k in ('test_binary', 'test_source', 'binary', 'source')]
        if isinstance(registry.get('source_bundle'), dict):
            names.append(registry['source_bundle'].get('path'))
        for entry in registry.get('acados_runtime', {}).values():
            if isinstance(entry, dict):
                names.append(entry.get('path'))
        for name in names:
            if isinstance(name, str) and Path(name).is_file() and name not in before['files']:
                extras[name] = pin(Path(name).read_bytes())
for name in [
    REPO / 'usv_mpc_ws/install/usv_mpc_cpp/lib/libmpc_solver_lib.so',
    REPO / 'usv_mpc_ws/install/usv_mpc_cpp/lib/libcodegen_lib.so',
    REPO / 'usv_mpc_ws/install/usv_mpc_cpp/lib/libmpc_core_lib.so',
    REPO / 'usv_mpc_ws/src/usv_mpc_cpp/src/utils.cpp',
    REPO / 'usv_mpc_ws/src/usv_mpc_cpp/src/acados_backend.cpp',
    REPO / 'usv_mpc_ws/src/usv_mpc_cpp/acados_generated/acados_solver_usv_dyn_nmpc.c']:
    if name.is_file() and str(name) not in before['files']:
        extras[str(name)] = pin(name.read_bytes())
for name, data in [('review_materials_v1.json', materials), ('replay_derivations_v1.json', derivations),
                   ('supplemental_inputs_before_v1.json', {'files': extras, 'count': len(extras),
                     'scope': 'selected registered component test binaries, native libraries and production solver sources used by this review'})]:
    create(ROOT / 'evidence' / name, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode())
print(json.dumps({'review_artifacts': len(materials), 'replay_sources': len(derivations),
                  'supplemental_protected_inputs': len(extras), 'owned_runs': 0}))
