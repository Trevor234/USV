#!/usr/bin/env python3
"""Build one diagnostic Worker and its new pure policy test; no install/codegen/node."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
helper = D.parent / 'scheme_A_activation_alignment_20261019_28/build_activation_roles_v1.py'
spec = importlib.util.spec_from_file_location('frozen_worker_build_primitives', helper)
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
B.C = D / 'worker_author'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--attempt', type=int, required=True)
    args = ap.parse_args()
    B.require(args.attempt in [1, 2, 3], 'maximum_initial_plus_two_repairs')
    out = D / 'build' / ('v2_worker_attempt' + str(args.attempt).zfill(2))
    out.mkdir(exist_ok=False)
    build = out / 'cmake_build'
    (out / 'native_callback_output').mkdir()
    started = time.monotonic()
    result = {'schema': 'V2-explicit-diagnostic-worker-build/v1', 'role': 'worker',
              'author_directory': str(B.C), 'binary': str(build / 'p1_solver_worker_owned_v2'),
              'passed': False, 'attempt': args.attempt, 'install_performed': False,
              'codegen_performed': False, 'node_launch_performed': False,
              'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False,
              'recipe': B.pin(__file__), 'primitive_helper': B.pin(helper)}
    try:
        parent, previous, parents = B.parent_role('worker')
        files = B.source_files('worker')
        for name, row in files.items():
            B.snapshot(row['path'], out / 'source_snapshot' / name)
        descriptor = {'schema': 'V2-worker-source-bundle/v1', 'files': files,
                      'author_directory': str(B.C), 'parent_source_bundle': parent,
                      'projected_contract': B.pin(B.C / 'pair_wakeup_contract_v1.json'),
                      'frozen_before_configure': True, 'stage_qualified': False, 'execute_qualified': False}
        B.write(out / 'source_bundle_bootstrap.json', descriptor)
        def configure(bundle_hash, name):
            return B.command(out, name, ['cmake', '-S', str(B.C / 'worker'), '-B', str(build),
                '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
                '-DPython3_EXECUTABLE=/usr/bin/python3', '-DP1_OWNED_SOURCE_BUNDLE_SHA256=' + bundle_hash], 45, files)
        B.require(configure(B.sha(out / 'source_bundle_bootstrap.json'), 'bootstrap_configure') == 0, 'bootstrap_configure')
        static = B.static_link_inputs_before(build, out)
        descriptor['static_link_inputs_before'] = B.pin(out / 'static_link_inputs_before.json')
        B.write(out / 'source_bundle.json', descriptor)
        bundle_hash = B.sha(out / 'source_bundle.json')
        B.require(configure(bundle_hash, 'configure') == 0, 'configure')
        B.verify_static_link_inputs(static)
        rc = B.command(out, 'build', ['cmake', '--build', str(build), '-j2'], 120, files)
        B.require(rc == 0, 'build_failed')
        binary = build / 'p1_solver_worker_owned_v2'
        B.require(bundle_hash.encode() in binary.read_bytes(), 'ELF_exact_source_bundle_pin')
        B.require(B.command(out, 'native_policy', [str(build / 'test_v2_diagnostic_block')], 20, files) == 0,
                  'native_policy_failed')
        native = (out / 'native_policy.log').read_text().strip()
        B.require(native == 'checks=22 passed', 'all_22_policy_assertions')
        dependency_count = B.dependencies(build, out)
        loader_count = B.runtime_libraries(binary, out, files)
        B.verify_static_link_inputs(static)
        B.require(B.unchanged(files) and B.unchanged(parents), 'selected_new_or_parent_source_changed')
        result.update(passed=True, binary_sha256=B.sha(binary),
                      source_bundle={'path': str(out / 'source_bundle.json'), 'sha256': bundle_hash, 'files': len(files)},
                      Native_assertions=22, Native_cases=1, parent_binary_sha256=previous['binary_sha256'],
                      actual_compiler_dependencies=dependency_count, loader_libraries=loader_count,
                      copied_legacy_hooks_unmodified=True)
    except Exception as error:
        result.update(error=repr(error), traceback=traceback.format_exc())
    result['elapsed_seconds'] = time.monotonic() - started
    B.write(out / 'build_result_v1.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ['traceback', 'source_bundle', 'recipe', 'primitive_helper']}, ensure_ascii=False))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
