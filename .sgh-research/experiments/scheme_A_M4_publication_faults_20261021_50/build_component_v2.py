#!/usr/bin/env python3
"""Bounded single-target test build; no runtime rewrite/install or control codegen."""
import ast
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

D = Path(__file__).resolve().parent
P = D.parent / 'scheme_A_M4_recorder_bootstrap_20261021_49'


def pin(p):
    p = Path(p).resolve(strict=True)
    data = p.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def emit(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


def main():
    assert 'verdict=GO' in (D / 'preflight/preflight_reflection_v1.md').read_text()
    source = P / 'author/observer/src/shadow/regulator_owned_execute.cpp'
    assert pin(source)['sha256'] == '94bbcb25c356c992111c1779d685bdb3da7dca2f5a0bf301d1f745ea4c2f9bf0'
    root = D / 'build/component_attempt02'
    root.mkdir()
    import shutil
    shutil.copytree(D / 'author_v2', root / 'author_snapshot')
    paths = [p for p in (D / 'author_v2').rglob('*') if p.is_file()] + [source, Path(__file__).resolve()]
    before = {str(p): pin(p) for p in paths}
    helper = D.parent / 'scheme_A_owned_business_start_20261020_39/author/build_c33_v9.py'
    tree = ast.parse(helper.read_bytes())
    setup = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SETUP' for t in n.targets))
    setup += '\nexport ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120 RMW_IMPLEMENTATION=rmw_fastrtps_cpp\n'
    commands = []
    def run(name, argv, budget):
        script = root / (name + '.sh')
        with script.open('x') as f:
            f.write('set -e\n' + setup + '\nexec timeout --signal=TERM --kill-after=5s ' + str(budget) + 's ' + shlex.join(argv) + '\n')
        start = time.monotonic()
        with (root / (name + '.stdout.log')).open('xb') as out, (root / (name + '.stderr.log')).open('xb') as err:
            result = subprocess.run(['/bin/bash', str(script)], stdout=out, stderr=err, timeout=budget + 10)
        row = {'name': name, 'argv': argv, 'returncode': result.returncode, 'elapsed_seconds': time.monotonic() - start, 'script': str(script), **pin(script)}
        commands.append(row)
        print(json.dumps(row), flush=True)
        return result.returncode
    build = root / 'cmake_build'
    rc = run('configure', ['cmake', '-S', str(D / 'author_v2'), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'], 120)
    if rc == 0:
        rc = run('build_test', ['cmake', '--build', str(build), '--target', 'test_m4_publication_faults', '-j1'], 180)
    dependencies = {}
    for dep in build.rglob('*.o.d'):
        for path in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
            p = Path(path).resolve(strict=True)
            dependencies[str(p)] = pin(p)
    after = {str(p): pin(p) for p in paths}
    target = build / 'test_m4_publication_faults'
    symbols = ''
    if rc == 0:
        result = subprocess.run(['nm', '-D', str(target)], capture_output=True, check=True, text=True, timeout=15)
        symbols = '\n'.join(line for line in result.stdout.splitlines() if line.endswith(' rcl_publish'))
        with (root / 'interposer_export.txt').open('x') as f:
            f.write(symbols + '\n')
    passed = rc == 0 and before == after and ' T rcl_publish' in symbols
    emit(root / 'build_manifest_v1.json', {
        'schema': 'M4-source-linked-publication-fault-build/v1', 'passed': passed,
        'commands': commands, 'input_before': before, 'input_after': after,
        'compiler_dependencies': dependencies, 'test_only_rcl_publish_export': symbols,
        'target': {'path': str(target), **pin(target)} if target.exists() else None,
        'setup_helper': {'path': str(helper), **pin(helper)},
        'new_runtime_source_changes': 0, 'new_production_runtime_builds': 0,
        'control_codegen': False, 'install': False, 'ROS_runs': 0,
        'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False, 'research_conclusion': False})
    print(json.dumps({'passed': passed, 'manifest': str(root / 'build_manifest_v1.json')}), flush=True)
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
