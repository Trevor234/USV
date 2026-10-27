#!/usr/bin/env python3
"""Compile submitted roles and isolated native probes, without ROS execution."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'evidence/reviewed_input_snapshot/implementation/w2_author'
OUT = ROOT / 'evidence/application_compile_and_edges'
OUT.mkdir(exist_ok=False)
PRIVATE = OUT / 'author'
BUILD = OUT / 'build'
shutil.copytree(SOURCE, PRIVATE, ignore=shutil.ignore_patterns('__pycache__'))
scope = {'__file__': str(SOURCE / 'worker/run_wiring_verification.py'), '__name__': 'submitted_runner'}
exec(compile((SOURCE / 'worker/run_wiring_verification.py').read_text(), scope['__file__'], 'exec'), scope)
extra = ROOT / 'implementation/backend_edge_probes.cpp'
combined = PRIVATE / 'worker/review_backend_edges.cpp'
combined.write_text((PRIVATE / 'worker/test_w2_backend_wiring.cpp').read_text() + '\n' + extra.read_text())
with (PRIVATE / 'CMakeLists.txt').open('a') as stream:
    stream.write('''
ament_add_gtest(review_backend_edges worker/review_backend_edges.cpp TIMEOUT 60)
target_include_directories(review_backend_edges PRIVATE worker)
target_link_libraries(review_backend_edges usv_mpc_cpp::mpc_solver_lib nlohmann_json::nlohmann_json)
link_owned(review_backend_edges)
target_link_options(review_backend_edges PRIVATE
  "-Wl,--wrap=usv_dyn_nmpc_acados_solve" "-Wl,--wrap=usv_dyn_nmpc_acados_update_params")
set_target_properties(review_backend_edges PROPERTIES BUILD_RPATH "/home/trevor/acados/lib")
''')


def shell(name, body):
    script = OUT / (name + '.sh')
    script.write_text(body)
    result = subprocess.run(['/bin/bash', str(script)], capture_output=True, text=True, timeout=600)
    (OUT / (name + '.stdout.txt')).write_text(result.stdout)
    (OUT / (name + '.stderr.txt')).write_text(result.stderr)
    (OUT / (name + '.json')).write_text(json.dumps({
        'argv': ['/bin/bash', str(script)], 'returncode': result.returncode}, indent=2) + '\n')
    print(name, result.returncode, flush=True)
    return result


assert shell('configure', scope['CONFIGURE'].format(src=PRIVATE, build=BUILD)).returncode == 0
targets = ['p1_m4_worker_owned', 'p1_m4_regulator_owned', 'review_backend_edges', 'test_w2_entry_contract']
build_body = scope['BUILD'].format(build=BUILD, targets=' '.join(targets)).replace('-j2', '-j1')
built = shell('build', build_body)
if built.returncode:
    print(built.stderr[-4000:])
    raise SystemExit(built.returncode)
env = {'PATH': '/usr/local/bin:/usr/bin:/bin',
       'LD_LIBRARY_PATH': '/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi'}
argv = [str(BUILD / 'review_backend_edges'), '--gtest_filter=W2Review.*']
result = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=60)
(OUT / 'review_backend_edges.stdout.txt').write_text(result.stdout)
(OUT / 'review_backend_edges.stderr.txt').write_text(result.stderr)
report = {'schema': 'W2-private-application-compile-and-native-edge-probes-v1',
          'roles_compiled': targets[:2], 'role_execution': False,
          'formal_identity': False, 'compile_identity_values': 'x placeholders; not a registered owned source',
          'link_interposition': 'real acados solve runs; forced nonzero return or preparation-time stop/clock change for controlled regression checks',
          'probe_argv': argv, 'probe_env': env, 'probe_exit_code': result.returncode,
          'binaries': {name: hashlib.sha256((BUILD / name).read_bytes()).hexdigest() for name in targets}}
(OUT / 'verification_v1.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False), flush=True)
