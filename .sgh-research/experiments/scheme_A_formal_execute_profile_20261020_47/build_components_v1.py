#!/usr/bin/env python3
"""Finite create-only build: two offline probes, dependency and loader pins."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import time

D = Path(__file__).resolve().parent


def pin(p):
    p = Path(p).resolve(strict=True)
    data = p.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    root = D / 'build/components_attempt01'
    root.mkdir(parents=True)
    compiler = Path(shutil.which('g++')).resolve(strict=True)
    rows = []
    for name in ['contract_probe', 'entry_probe']:
        out = root / name
        dep = root / (name + '.d')
        source = D / 'implementation/native' / (name + '_v1.cpp')
        command = [str(compiler), '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-MD', '-MF', str(dep), str(source), '-o', str(out)]
        started = time.monotonic()
        try:
            result = subprocess.run(command, capture_output=True, timeout=180)
            stdout, stderr, rc = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr, rc = error.stdout or b'', error.stderr or b'', 124
        (root / (name + '.stdout.log')).write_bytes(stdout)
        (root / (name + '.stderr.log')).write_bytes(stderr)
        row = {'target': name, 'command': command, 'returncode': rc, 'elapsed_seconds': time.monotonic() - started,
               'compiler': {str(compiler): pin(compiler)}, 'source': {str(source): pin(source)}, 'physical_API_calls': 0}
        if rc == 0:
            paths = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
            row['dependencies'] = {str(Path(p).resolve()): pin(p) for p in paths}
            row['binary'] = {str(out): pin(out)}
            linked = subprocess.run(['/usr/bin/ldd', str(out)], capture_output=True, timeout=10)
            (root / (name + '.ldd.log')).write_bytes(linked.stdout + linked.stderr)
            assert linked.returncode == 0 and b'not found' not in linked.stdout
            libs = [Path(w) for line in linked.stdout.decode().splitlines() for w in line.split() if w.startswith('/') and Path(w).is_file()]
            row['runtime_libraries'] = {str(p.resolve()): pin(p) for p in libs}
        rows.append(row)
        if rc:
            break
    record = {'schema': 'P1-owned-profile-offline-build/v1', 'passed': len(rows) == 2 and all(r['returncode'] == 0 for r in rows),
              'targets': rows, 'ROS_runs': 0, 'physical_publishers': 0, 'codegen_performed': False,
              'build_tool': {str(Path(__file__).resolve()): pin(Path(__file__))}}
    with (root / 'build_manifest_v1.json').open('x') as f:
        json.dump(record, f, indent=2, sort_keys=True)
        f.write('\n')
    print(json.dumps({'passed': record['passed'], 'targets': [{k:r[k] for k in ['target', 'returncode', 'elapsed_seconds']} for r in rows]}))
    return 0 if record['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
