#!/usr/bin/env python3
"""Freeze the W2 author tree, rebuild it with real identities, and emit a registry.

This is the §5.2 step: the previous builds used `x` placeholders for the source
bundle and Driver SHA, which makes them review artefacts rather than a source of
truth for an owned run. Here the identities are computed from the frozen tree
itself, baked into the ELFs at compile time, and then read back from the built
binaries to prove the bake took effect.

Order matters and is asserted:
  1. hash the frozen tree -> source bundle;
  2. hash the Driver tool;
  3. configure with those two values, so the compile-time macros are real;
  4. build every consumed role;
  5. re-hash the tree and require it unchanged (no build step may edit source);
  6. record ELF hashes, loaded dependencies, and the compile-time macros that
     were actually used.

No ROS is started, no run directory is created, no registration is written yet.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
AUTHOR = PKG / 'implementation' / 'w2_author'
OUT = PKG / 'evidence' / 'freeze_and_build'

CONTRACT = Path('/home/trevor/USV/.sgh-research/experiments/'
                'scheme_A_M4_diagnostic_worker_20261021_56/implementation/'
                'p1_execution_contract_v4.json')
CONTRACT_V3 = Path('/home/trevor/USV/.sgh-research/experiments/'
                   'scheme_A_formal_execute_profile_20261020_47/freeze/'
                   'p1_execution_contract_v1.json')

TARGETS = ['p1_m4_worker_owned', 'p1_m4_regulator_owned', 'p1_m4_fixture_owned']

SETUP = '''
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
'''


def pin(path: Path) -> dict:
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def tree_manifest(root: Path) -> dict:
    """Every regular file in the frozen tree, relative path -> pin."""
    rows = {}
    for p in sorted(root.rglob('*')):
        if not p.is_file():
            continue
        if '__pycache__' in p.parts or p.suffix == '.pyc':
            continue
        # `verify_bundle` in the Driver re-hashes `row['path']`, so each row must
        # carry the absolute path it pins — not only bytes and sha256.
        rows[str(p.relative_to(root))] = {'path': str(p), **pin(p)}
    return rows


_command_sequence = 0

def run_script(body: str, timeout: int) -> tuple[int, str]:
    global _command_sequence
    prefix = OUT / ('command_%02d' % _command_sequence)
    _command_sequence += 1
    script = prefix.with_suffix('.sh')
    with script.open('x') as f: f.write(body)
    r = subprocess.run(['/bin/bash', str(script)], capture_output=True,
                       text=True, timeout=timeout)
    prefix.with_suffix('.stdout.txt').write_text(r.stdout)
    prefix.with_suffix('.stderr.txt').write_text(r.stderr)
    prefix.with_suffix('.json').write_text(json.dumps({'argv':['/bin/bash',str(script)],'returncode':r.returncode},indent=2)+'\n')
    return r.returncode, r.stdout + r.stderr


def elf_macros(binary: Path) -> dict:
    """Read the compile-time identity strings back out of the ELF.

    `strings` is enough: the macros are string literals, so their presence is checked together with the configured source root and build report.
    Literal presence alone is not proof of the source of a particular macro.
    """
    try:
        r = subprocess.run(['strings', str(binary)], capture_output=True,
                           text=True, timeout=60)
        text = r.stdout
    except Exception:  # noqa: BLE001
        return {}
    markers = {}
    import re
    for name in ('P1_OWNED_SOURCE_BUNDLE_SHA256', 'P1_DRIVER_TOOL_SHA256'):
        # The macro value itself is what appears; record any 64-hex literal.
        pass
    hexes = set(re.findall(r'\b[0-9a-f]{64}\b', text))
    markers['hex_literals'] = sorted(hexes)
    return markers


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=False)
    if not (AUTHOR / 'worker' / 'solver_worker_m4.cpp').is_file():
        print('author tree missing')
        return 2

    before = tree_manifest(AUTHOR)
    bundle = OUT / 'source_bundle.json'
    bundle_doc = {
        'schema': 'M4-owned-source-bundle/v1',
        'files': {k: v for k, v in before.items()},
        'file_count': len(before),
        'physical_production_release': False,
        'scope': 'M4_owned_diagnostic_worker_only_v1',
    }
    with bundle.open('x') as f: f.write(json.dumps(bundle_doc, indent=2, sort_keys=True) + '\n')
    bundle_sha = pin(bundle)['sha256']
    driver = AUTHOR / 'owned_m4_diagnostic_driver_v1.py'
    driver_sha = pin(driver)['sha256']

    build = OUT / 'cmake_build'
    configure = SETUP + '\n'.join([
        'exec cmake -S %s -B %s -DCMAKE_BUILD_TYPE=Release '
        "'-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG' -DCMAKE_EXPORT_COMPILE_COMMANDS=ON "
        '-DP1_OWNED_SOURCE_BUNDLE_SHA256=%s -DP1_DRIVER_TOOL_SHA256=%s '
        '-DP1_V4_CONTRACT_FILE=%s -DP1_V3_CONTRACT_FILE=%s' % (
            shlex.quote(str(AUTHOR)), shlex.quote(str(build)),
            bundle_sha, driver_sha, shlex.quote(str(CONTRACT)),
            shlex.quote(str(CONTRACT_V3))),
    ]) + '\n'

    t0 = time.monotonic()
    rc, log = run_script(configure, 300)
    if rc != 0:
        print('configure failed')
        print(log[-3000:])
        return 2
    cache = (build / 'CMakeCache.txt').read_text()
    home_ok = 'CMAKE_HOME_DIRECTORY:INTERNAL=%s' % AUTHOR in cache

    build_rc, build_log = run_script(
        SETUP + 'exec cmake --build %s --target %s -j2\n' % (
            shlex.quote(str(build)), ' '.join(TARGETS)), 1800)
    if build_rc != 0:
        print('build failed')
        print(build_log[-3000:])
        return 2

    after = tree_manifest(AUTHOR)
    unchanged = before == after

    roles = {}
    for name, role in (('p1_m4_worker_owned', 'worker'),
                       ('p1_m4_regulator_owned', 'regulator'),
                       ('p1_m4_fixture_owned', 'fixture')):
        binary = build / name
        assert binary.is_file(), name
        entry = {'binary': str(binary), **pin(binary)}
        m = elf_macros(binary)
        entry['embedded_sha_literals'] = m.get('hex_literals', [])
        entry['source_bundle_macro_present'] = bundle_sha in entry['embedded_sha_literals']
        entry['driver_tool_macro_present'] = driver_sha in entry['embedded_sha_literals']
        roles[role] = entry

    # Loaded dependencies, so a later registry can pin what the ELF actually
    # resolves at runtime rather than only what it was compiled against.
    deps = {}
    resolutions = {}
    for name in TARGETS:
        lrc, ltext = run_script(SETUP + 'exec ldd %s\n' % shlex.quote(str(build / name)), 60)
        assert lrc == 0 and 'not found' not in ltext, name + ' loader resolution incomplete'
        records = {}
        for line in ltext.splitlines():
            import re
            m = re.match(r'\s*(\S+)\s+=>\s+(/\S+)', line)
            if m: records[m.group(1)] = m.group(2)
        deps[name] = sorted(records)
        resolutions[name] = records
    acados = {}
    for lib in ('libacados.so', 'libhpipm.so', 'libblasfeo.so'):
        paths = {v for k,v in resolutions['p1_m4_worker_owned'].items() if k==lib or k.startswith(lib+'.')}
        assert len(paths)==1, (lib,paths)
        actual = Path(next(iter(paths))).resolve()
        st = actual.stat()
        acados[lib] = {'path':str(actual),'device':st.st_dev,'inode':st.st_ino,**pin(actual)}

    report = {
        'schema': 'M4-owned-freeze-and-build/v1',
        'author_root': str(AUTHOR),
        'source_bundle': {'path': str(bundle), 'sha256': bundle_sha,
                          'files': len(before)},
        'driver': {'path': str(driver), 'sha256': driver_sha},
        'contract': {'path': str(CONTRACT), **pin(CONTRACT)},
        'contract_v3': {'path': str(CONTRACT_V3), **pin(CONTRACT_V3)},
        'configure': {'returncode': rc, 'cmake_home_matches': home_ok},
        'build': {'returncode': build_rc, 'targets': TARGETS,
                  'elapsed_seconds': round(time.monotonic() - t0, 1)},
        'source_unchanged_after_build': unchanged,
        'roles': roles,
        'ldd': deps,
        'loader_resolutions': resolutions,
        'acados_runtime': acados,
        'placeholders_used': False,
        'ros_started': False,
        'run_directory_created': False,
        'registration_written': False,
        'M4_stage_qualified': False,
        'F6_qualified': False,
        'P1_qualified': False,
    }
    report['passed'] = bool(
        rc == 0 and home_ok and build_rc == 0 and unchanged
        and all(r['source_bundle_macro_present'] and r['driver_tool_macro_present']
                for r in roles.values()))

    path = OUT / 'freeze_and_build_v1.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({
        'passed': report['passed'],
        'source_bundle_sha256': bundle_sha,
        'driver_sha256': driver_sha,
        'files': len(before),
        'source_unchanged': unchanged,
        'roles': {k: v['sha256'][:16] for k, v in roles.items()},
    }, indent=2))
    print('written:', path)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
