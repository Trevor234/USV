#!/usr/bin/env python3
"""Self-contained freeze for batch 108 (F6 model transaction): bundle of the
batch-local implementation -> native ELF (linked against the INSTALLED
production usv_mpc_cpp libs; no package file is modified) -> registry ->
registration with fixed assertion lists. Registration precedes any run."""
import hashlib, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPL = ROOT / 'implementation'
OUT = ROOT / 'evidence/freeze'
BUILD = ROOT / 'implementation/build_f6'
I = '/home/trevor/USV/usv_mpc_ws/install/usv_mpc_cpp/include'
LIB = '/home/trevor/USV/usv_mpc_ws/install/usv_mpc_cpp/lib'
ACADOS = '/home/trevor/acados'
BUDGET_S = 120
OUT.mkdir(parents=True, exist_ok=True); BUILD.mkdir(parents=True, exist_ok=True)

def pin(p):
    raw = Path(p).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

files = {p.name: {'path': str(p), **pin(p)} for p in sorted(IMPL.glob('*'))
         if p.is_file() and p.suffix in ('.hpp', '.cpp', '.py')}
bundle = OUT / 'source_bundle.json'
bundle.write_text(json.dumps({'schema': 'F6-transaction-source-bundle/v1',
    'scope': 'F6_model_transaction_component_v1', 'files': files,
    'file_count': len(files), 'physical_production_release': False,
    'linked_against': {'usv_mpc_cpp_install_lib': LIB, 'acados': ACADOS},
    'production_package_modified': False}, indent=2, sort_keys=True) + '\n')
bundle_sha = pin(bundle)['sha256']

binary = BUILD / 'test_f6_model_transaction'
cmd = ['g++', '-std=c++17', '-O2', '-DNDEBUG',
       '-I', str(IMPL), '-I', I, '-I', I + '/usv_mpc_cpp/acados_generated',
       '-I', ACADOS + '/include', '-I', ACADOS + '/include/blasfeo/include',
       '-I', ACADOS + '/include/hpipm/include', '-I', '/usr/include/eigen3',
       str(IMPL / 'test_f6_model_transaction.cpp'), '-o', str(binary),
       '-L', LIB, '-lmpc_solver_lib', '-lcodegen_lib', '-lmpc_core_lib',
       '-L', ACADOS + '/lib', '-lacados', '-lblasfeo', '-lhpipm', '-pthread']
build = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
if build.returncode != 0:
    print(build.stderr[-4000:]); raise SystemExit(f'build failed rc={build.returncode}')
cc = subprocess.run(['g++', '--version'], capture_output=True, text=True).stdout.splitlines()[0]
binary_sha = pin(binary)['sha256']
registry = {'schema': 'F6-transaction-registry/v1', 'scope': 'F6_model_transaction_component_v1',
    'test_binary': str(binary), 'test_binary_sha256': binary_sha,
    'wrapper_source': str(IMPL / 'model_transaction_v1.hpp'),
    'wrapper_source_sha256': pin(IMPL / 'model_transaction_v1.hpp')['sha256'],
    'harness_source': str(IMPL / 'test_f6_model_transaction.cpp'),
    'harness_source_sha256': pin(IMPL / 'test_f6_model_transaction.cpp')['sha256'],
    'source_bundle': {'path': str(bundle), 'sha256': bundle_sha},
    'comparator': 'production AcadosBackend via installed libmpc_solver_lib (unmodified)',
    'compiler': cc, 'ros_context': False, 'physical_production_release': False}
(IMPL / 'f6_registry.json').write_text(json.dumps(registry, indent=2, sort_keys=True) + '\n')

ASSERTS = {
 'F6-1': ['f6_1_setter_switch_equals_fresh_m1_instance', 'f6_1_warm_books_per_version'],
 'F6-2': ['f6_2_solve_rejected_during_prepare', 'f6_2_no_half_applied_solve',
          'f6_2_solve_after_commit_executes_exactly_once', 'f6_2_accounting'],
 'F6-3': ['f6_3_m0_phase_matches_pure_m0', 'f6_3_m1_phase_matches_pure_m1',
          'f6_3_clean_boundary_accounting'],
 'F6-4': ['f6_4_stale_stamp_rejected', 'f6_4_unknown_generation_rejected',
          'f6_4_version_content_immutable', 'f6_4_rejections_never_touch_solver',
          'f6_4_state_unchanged_by_rejections'],
 'F6-5': ['f6_5_phase1_lockstep', 'f6_5_back_on_m0', 'f6_5_m0_warm_restored_matches_paused_instance',
          'f6_5_both_versions_keep_warm_books'],
 'F6-6': ['f6_6_wrapper_matches_production_backend_tick_for_tick', 'f6_6_no_transaction_accounting'],
}
cases = [{'case_id': cid, 'family': 'F6_model_transaction_component',
          'design': 'batch 107 design table', 'harness': str(IMPL / 'test_f6_model_transaction.cpp'),
          'budget_seconds': BUDGET_S, 'assertions': names,
          'result_schema': 'F6-model-transaction/v1',
          'qualification_flags': {'ROS_context_created': False, 'stage_qualified': False,
                                  'execute_qualified': False, 'research_conclusion': False}}
         for cid, names in ASSERTS.items()]
registration = {'schema': 'T3-case-registration/v1', 'batch_registered': 108,
    'family_registered': 'F6-Stage1',
    'obligation_binding': {'n4': 'batch 67 next plan (N4)', 'design': 'batch 107',
        'f6': '首选A §5.2 有限模型/固定偏置阶段'},
    'tree_base': {'source': str(IMPL), 'bundle_sha256': bundle_sha, 'binary_sha256': binary_sha},
    'fixed_parameters': {'tolerance': 1e-8, 'ticks_phase1': 4, 'ticks_phase2': 4,
        'm1_perturbations': {'mass': [14.2, 15.0], 'Xu': [-2.272063, -2.4], 'Nr': [-4.286144, -4.4]},
        'dimensions': {'NX': 8, 'NU': 2, 'N': 20, 'NP': 6, 'NP_GLOBAL': 30},
        'codegen': False, 'gp_ppo': False},
    'cases': cases,
    'governance': {'pre_registration_required': True, 'single_finite_execution': True,
        'auto_retry': 0, 'failure_originals_preserved': True,
        'production_package_unmodified': True},
    'not_claimed': ['F6 stage qualification (GP phase etc. remain)', 'production default change',
                    'any stage qualification or research conclusion']}
(IMPL / 'F6_registration.json').write_text(json.dumps(registration, indent=2, sort_keys=True) + '\n')
print(f'bundle={bundle_sha[:16]}... binary={binary_sha[:16]}... files={len(files)} cc={cc}')
print('registry + registration written (pre-run)')
