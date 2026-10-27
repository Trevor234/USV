#!/usr/bin/env python3
"""Self-contained freeze for batch 118 (S2, B2' mapping helper): bundle ->
native test ELF + production fixture target build (proves the production call
site compiles) -> registry -> registration with the fixed 16-assertion list.
Registration precedes the single run."""
import hashlib, json, shlex, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / 'implementation/t2_author'
OUT = ROOT / 'evidence/freeze'
BUILD = ROOT / 'implementation/build_s2'
CBUILD = ROOT / 'build/cmake'
SETUP_SH = ROOT / 'implementation/setup_env.sh'
TEST_SRC = TREE / 'tests/test_resume_mapping_v1.cpp'
HELPER = TREE / 'fixture/resume_stamp_mapping_v1.hpp'
FIXTURE_SRC = TREE / 'fixture/synthetic_source_m4.cpp'
V3 = '/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'
V4 = '/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json'
for d in (OUT, BUILD, CBUILD):
    d.mkdir(parents=True, exist_ok=True)

def pin(p):
    raw = Path(p).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def run(cmd, timeout=300):
    r = subprocess.run(['/bin/bash', str(SETUP_SH), 'bash', '-c', ' '.join(shlex.quote(c) for c in cmd)],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        print('STDERR:', r.stderr[-3000:])
        raise AssertionError(f'command failed rc={r.returncode}: {cmd[0]}')
    return r

files = {str(p.relative_to(TREE)): {'path': str(p), **pin(p)}
         for p in sorted(TREE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
bundle = OUT / 'source_bundle.json'
bundle.write_text(json.dumps({'schema': 'S2-B2-mapping-source-bundle/v1',
    'scope': 'B2_pairing_mapping_component_v1', 'files': files, 'file_count': len(files),
    'physical_production_release': False,
    'fixture_changed_vs_batch112': ['resume_stamp_mapping_v1.hpp added (helper)',
        'synthetic_source_m4.cpp: include/member/clock_resume branch (advance removed, arm_resume)/publish_step advance via step_stamp + note_published at actual publish'],
    'regulator_unchanged_from_batch112_scoped': True}, indent=2, sort_keys=True) + '\n')
bundle_sha = pin(bundle)['sha256']

binary = BUILD / 'test_resume_mapping_v1'
build = subprocess.run(['g++', '-std=c++17', '-O2', '-DNDEBUG', '-I', str(TREE / 'fixture'),
                        str(TEST_SRC), '-o', str(binary), '-lpthread'],
                       capture_output=True, text=True, timeout=300)
if build.returncode != 0:
    print(build.stderr[-4000:]); raise SystemExit('native build failed')
binary_sha = pin(binary)['sha256']
cc = subprocess.run(['g++', '--version'], capture_output=True, text=True).stdout.splitlines()[0]

# production call-site compile proof: build the fixture target with the helper wired in
run(['cmake', '-S', str(TREE), '-B', str(CBUILD), '-DCMAKE_BUILD_TYPE=Release',
     '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG',
     f'-DP1_OWNED_SOURCE_BUNDLE_SHA256={bundle_sha}',
     '-DP1_DRIVER_TOOL_SHA256=' + pin(TREE / 't2b_gen_driver_v1.py')['sha256'],
     f'-DP1_V4_CONTRACT_FILE={V4}', f'-DP1_V3_CONTRACT_FILE={V3}'], timeout=300)
run(['cmake', '--build', str(CBUILD), '--target', 'p1_m4_fixture_owned', '-j2'], timeout=1800)
fixture_elf_sha = pin(CBUILD / 'p1_m4_fixture_owned')['sha256']
print(f'bundle={bundle_sha[:16]}... binary={binary_sha[:16]}... fixture_elf={fixture_elf_sha[:16]}... files={len(files)}')

registry = {'schema': 'S2-B2-mapping-registry/v1', 'scope': 'B2_pairing_mapping_component_v1',
    'test_binary': str(binary), 'test_binary_sha256': binary_sha,
    'helper_source': str(HELPER), 'helper_source_sha256': pin(HELPER)['sha256'],
    'fixture_source': str(FIXTURE_SRC), 'fixture_source_sha256': pin(FIXTURE_SRC)['sha256'],
    'fixture_elf_compiled': str(CBUILD / 'p1_m4_fixture_owned'), 'fixture_elf_sha256': fixture_elf_sha,
    'source_bundle': {'path': str(bundle), 'sha256': bundle_sha},
    'compiler': cc, 'ros_context_for_suite': False, 'physical_production_release': False}
(ROOT / 'implementation/s2_registry.json').write_text(json.dumps(registry, indent=2, sort_keys=True) + '\n')

ASSERTIONS = ['t1_raw_stamps_monotonic', 't1_first_resumed_stamp_is_published_pair_mapping',
    't1_projection_history_no_regression', 't2_resume_stamp_independent_of_action_instant',
    't3_long_hold_maps_capped_and_monotonic', 't4_duplicate_resume_single_application',
    't5_missing_resume_frozen_no_crash', 't6_no_double_accumulation',
    't7_rtf_window_rebuild_in_band', 't8_no_hold_path_bitwise_identical',
    't9_same_stamp_smooth_resume', 't10_catch_up_capped_below_epoch_threshold',
    't11_large_stamp_no_overflow', 'mutant_m1_no_catchup_is_caught',
    'mutant_m2_command_time_source_is_caught', 'mutant_m3_double_accumulation_is_caught']
registration = {'schema': 'T3-case-registration/v1', 'batch_registered': 118,
    'family_registered': 'B2-pairing-mapping-S2',
    'obligation_binding': {'review': 'batch 115 S2/R115-06', 's0': 'batch 116', 's1': 'batch 117'},
    'tree_base': {'source': str(TREE), 'bundle_sha256': bundle_sha, 'binary_sha256': binary_sha},
    'fixed_parameters': {'writer_step_ns': 20000000, 'catch_up_cap_ns': 4900000000,
        'mapping': 'S_next = S_last_published + min(T_next - T_last_published_target, cap)',
        'mutants_required_caught': 3, 'production_call_site': 'fixture publish_step + clock_resume'},
    'cases': [{'case_id': 'S2-B2-MAPPING', 'family': 'B2_pairing_mapping_component',
               'budget_seconds': 60, 'assertions': ASSERTIONS,
               'result_schema': 'S2-resume-mapping/v1',
               'qualification_flags': {'ROS_context_created': False, 'stage_qualified': False,
                                       'execute_qualified': False, 'research_conclusion': False}}],
    'governance': {'pre_registration_required': True, 'single_finite_execution': True,
        'auto_retry': 0, 'failure_originals_preserved': True,
        'no_L630_or_OutputAuthority_change': True, 'consistency_fail_closed_preserved': True},
    'not_claimed': ['owned run (S4 is batch 119)', 'B0 design', 'healthy-recovery proven (S4 decides)']}
(ROOT / 'implementation/S2_registration.json').write_text(json.dumps(registration, indent=2, sort_keys=True) + '\n')
print('registry + registration written (pre-run)')
