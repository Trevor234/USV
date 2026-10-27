#!/usr/bin/env python3
"""Build only the new observer; verify and retain the four existing role pins.

Every evidence output is create-only. This tool never installs into an overlay,
launches a ROS node, or rewrites current bundle/build manifests.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

N = Path(__file__).resolve().parent
DEFAULT_OUTPUT = Path('/home/trevor/MPC/scheme_A_atomic_observation_20261011_06/validation/build01')
REUSED_ROLES = ('publisher', 'worker', 'fixture', 'recorder')
TARGET = 'p1_regulator_shadow_observer_owned_v2'


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def create_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def read_json(path):
    return json.loads(Path(path).read_text())


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def verify_bundle(pin, role):
    path = Path(pin['path'])
    require(path.is_absolute(), 'bundle path must be absolute: ' + role)
    require(file_sha(path) == pin['sha256'], 'bundle identity changed: ' + role)
    bundle = read_json(path)
    require(bundle['role'] == role, 'bundle role differs: ' + role)
    require(len(bundle['files']) == pin['files'], 'bundle file count differs: ' + role)
    for name, item in bundle['files'].items():
        source = Path(item['path'])
        require(source.is_absolute(), 'source path must be absolute: ' + name)
        require(file_sha(source) == item['sha256'], 'source identity changed: ' + str(source))
        if role == 'observer':
            require(source.is_relative_to(N), 'new observer source outside N7: ' + str(source))
    return bundle


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument('--build-dir', type=Path, default=N / 'observer' / 'build',
                    help='fresh directory under N7/observer; use a new path after a failed attempt')
    ap.add_argument('--domain', type=int, required=True)
    args = ap.parse_args()
    require(1 <= args.domain <= 200, 'domain outside [1,200]')
    require(args.output_dir.is_absolute(), 'evidence directory must be absolute')
    require(args.build_dir.is_absolute() and args.build_dir.is_relative_to(N / 'observer'),
            'build directory must be absolute and under the new observer directory')
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=False)
    with (out / 'build_atomic_observer_v7.py.snapshot').open('xb') as stream:
        stream.write(Path(__file__).read_bytes())
    result = {'schema': 'p1-atomic-observer-build-v7', 'role': 'observer',
              'author_directory': str(N), 'tool_sha256': file_sha(__file__),
              'node_launch_performed': False, 'install_performed': False,
              'passed': False, 'stage_qualified': False, 'execute_qualified': False}
    started = time.monotonic()
    try:
        pins_path = N / 'source_bundles_current.json'
        build_path = N / 'build_manifest_current.json'
        pins = read_json(pins_path)
        previous = {item['role']: item for item in read_json(build_path)}
        identities = {str(p): file_sha(p) for p in (pins_path, build_path)}
        for path in (pins_path, build_path):
            with (out / (path.name + '.snapshot')).open('xb') as stream:
                stream.write(path.read_bytes())
        pin = pins['observer']
        require(Path(pin['path']).is_relative_to(N), 'new observer bundle outside N7')
        bundle = verify_bundle(pin, 'observer')
        with (out / 'observer_source_bundle.json.snapshot').open('xb') as stream:
            stream.write(Path(pin['path']).read_bytes())
        reused = []
        for role in REUSED_ROLES:
            verify_bundle(pins[role], role)
            old = previous[role]
            require(old['passed'] is True, 'unqualified reused build: ' + role)
            require(old['source_bundle'] == pins[role], 'reused bundle/build binding differs: ' + role)
            require(file_sha(old['binary']) == old['binary_sha256'], 'reused binary changed: ' + role)
            reused.append(old)
        result['source_bundle'] = {**pin, 'files': len(bundle['files'])}
        result['reused_roles'] = reused
        result['input_manifest_sha256'] = identities
        create_json(out / 'build_inputs.json', result)
        build_dir = args.build_dir
        require(not build_dir.exists(), 'fresh observer build directory required; preserve previous attempts')
        setup = '''export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_DOMAIN_ID=''' + shlex.quote(str(args.domain)) + '''
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
'''
        commands = [
            ('configure', ['cmake', '-S', str(N / 'observer'), '-B', str(build_dir),
                           '-DCMAKE_BUILD_TYPE=Release', '-DPython3_EXECUTABLE=/usr/bin/python3',
                           '-DP1_OWNED_SOURCE_BUNDLE_SHA256=' + pin['sha256']], 60),
            ('build', ['cmake', '--build', str(build_dir), '--target', TARGET, '-j2'], 180),
        ]
        for label, command, budget in commands:
            script = out / (label + '.sh')
            with script.open('x') as stream:
                stream.write('set -e\n' + setup + 'exec timeout --signal=TERM --kill-after=10s '
                             + str(budget) + 's ' + shlex.join(command) + '\n')
            with (out / (label + '.log')).open('xb') as log:
                rc = subprocess.run(['bash', str(script)], stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=budget + 15).returncode
            result[label + '_rc'] = rc
            require(rc == 0, label + ' failed')
        for path, expected_sha in identities.items():
            require(file_sha(path) == expected_sha, 'input manifest changed during build: ' + path)
        verify_bundle(pin, 'observer')
        for old in reused:
            verify_bundle(pins[old['role']], old['role'])
            require(file_sha(old['binary']) == old['binary_sha256'], 'reused binary changed during build')
        binary = build_dir / TARGET
        result.update(binary=str(binary), binary_sha256=file_sha(binary), passed=True,
                      reused_roles_verified_unchanged=True)
    except Exception as error:
        result['error'] = repr(error)
    result['elapsed_seconds'] = time.monotonic() - started
    create_json(out / 'result.json', result)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
