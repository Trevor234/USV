#!/usr/bin/env python3
"""Read-only LOCAL full-byte preservation for owned cold-start integration batch27. Remote MPC mirrors are explicitly deferred, not revalidated.

The historical semantic capture stays frozen. One explicitly pinned live-path
delta observed before the resumed turn is preserved; its historical bytes are
verified separately against the immutable Git HEAD and a new recovery snapshot. All captured input bytes and
directory populations, both complete later archives, and analysis inputs are
reread without running historical ROS processes or importing endpoint authority.
The sealed eight-file analysis archive is projected out only while its exact
population and bytes remain required. This batch's two new untracked roots are
additionally excluded from the existing workspace projection; old source, staging, submodules and failures stay
fixed. No recursive protection helper is invoked.
"""
import argparse
import importlib.util
import json
import os
import subprocess
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
H = D.parent / 'scheme_A_positive_chain_20261015_18'
J = D.parent / 'scheme_A_longitudinal_20261016_19'
N19 = D.parent / 'p1_execution_architecture_20261005_01/authored_D1_longitudinal_20261016_v19'
N18 = D.parent / 'p1_execution_architecture_20261005_01/authored_D1_positive_chain_20261015_v18'
P = D.parent / 'scheme_A_C3_10_20261015_16'
A = D.parent / 'scheme_A_rejection_analysis_20261015_17'
M = Path('/home/trevor/MPC')
DEFERRED_MPC_PINS = {}
DEFERRED_MPC_DIRECTORIES = {}
PARENT_ROOTS = (
    '.sgh-research/experiments/scheme_A_positive_chain_20261015_18/',
    '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_positive_chain_20261015_v18/',
    '.sgh-research/experiments/scheme_A_longitudinal_20261016_19/',
    '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_longitudinal_20261016_v19/',
)
PARENT_ROOTS += (
    '.sgh-research/experiments/scheme_A_reference_bias_20261016_20/',
    '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_reference_bias_20261016_v20/',
)
PARENT_ROOTS += ('.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_reference_time_anchor_20261017_v21/',)
PARENT_ROOTS += (
 '.sgh-research/experiments/scheme_A_reference_time_anchor_20261017_21/',
 '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_reference_time_anchor_20261018_v21r2/',
)
PARENT_ROOTS += (
 '.sgh-research/experiments/scheme_A_reference_pair_wakeup_20261018_22/',
 '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_reference_pair_wakeup_20261018_v22/',
)
PARENT_ROOTS += (
 '.sgh-research/experiments/scheme_A_startup_rti_mechanism_20261018_23/',
 '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_startup_rti_mechanism_20261018_v23/',
)
PARENT_ROOTS += (
 '.sgh-research/experiments/scheme_A_startup_first_control_20261018_24/',
 '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_startup_first_control_20261018_v24/',
)
PARENT_ROOTS += (
 '.sgh-research/experiments/scheme_A_fixed_first_tail_optimization_20261018_25/',
 '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_fixed_first_tail_optimization_20261018_v25/',
)
PARENT_ROOTS += (
 '.sgh-research/experiments/scheme_A_causal_cold_start_20261018_26/',
 '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_causal_cold_start_20261018_v26/',
)
NEW_ROOTS = (
 '.sgh-research/experiments/scheme_A_owned_cold_start_20261018_27/',
 '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_owned_cold_start_20261018_v27/',
)
SEALED_LATER_ROOTS = ('.sgh-research/experiments/scheme_A_rejection_analysis_20261015_17/',)
OLD_ROOTS = (
    '.sgh-research/experiments/scheme_A_C3_10_20261015_16/',
    '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_10_20261015_v17/',
)
PIN16 = {
    'archive_inventory_v1.json': '8385def2158a9346ab38243ddb70f161a557d636c446b130a2b3a3f8b7886729',
    'postrun/final_QA_current.json': 'c55ebe389318e9d24941e0a6702dc40c2c8a36d4978b22d04d9e1cdd842bffe0',
    'delivery_verification.json': 'd761180125c2dd175eca57e76a30f7da236d0533589307158907f7daba2df761',
    'batch_status_final.json': '4d89572d606d016ae4c7383ba40498c5511c13957a9a4a891dd6efd1f8165b0d',
    'protection_v1.py': '7ea34af54149cd30ae455acbfffcbc5bbca9d5674989374a113e3ce91bd4c4c4',
    'protection_v3.py': '22c95d6512fccf2a83d1301882e621e382fe1cba1dade5dd845e5be335bd0b9c',
    'protection_v4.py': '2846776572d8237124c73c3c5469b0a22d95ca288b51d3efc76316e406d07f86',
    'preflight/preservation_anchor_v3.json': '770dcf7f3ffd12944a1117c1145a6e13ace825623b34fef8ee77e4539dd1aadb',
    'preflight/preservation_roster_v3.json': '4c9062d9033e2bd89ba34e3bf2c9490251b8bb0679a06018860fc74bc163583d',
    'preflight/boot_transition_v4.json': '0f188c835aff8c1070cb421406085fbce3dbb779bbbad3c9d6ccf5ce69c6e279',
}
REAL = '/home/trevor/USV/usv_mpc_ws/src/usv_bringup/launch/real.launch.py'
REAL_REL = 'usv_mpc_ws/src/usv_bringup/launch/real.launch.py'
OLD_REAL = {'bytes': 15682, 'mode': 436, 'sha256': 'a4d0dd480bbcd3518c0d9ad40c34db86123fb7a772135dd44ac03d04e7a2420e'}
NEW_REAL = {'bytes': 15602, 'mode': 436, 'sha256': 'f7d6f8a66ef834148da1a17aa71a93b86fca4f2a0ef5e0029f6aa4d039549b43'}
DELTA_DIFF_SHA = '96cdf76e50289c687c36de0afcd159969de7b9c4ce624ab98a78eabf6a452d16'
RESUMED_PINS = {
 'resumed_20261016_workspace_delta_v1.json': 'd31c2e1a4aa67b35cde641cc5e33a68599f671e8b06dbc1f0496c63266d04ae6',
 'resumed_20261016_real_launch.diff': DELTA_DIFF_SHA,
 'resumed_20261016_real_launch.py.snapshot': NEW_REAL['sha256'],
 'resumed_20261016_real_launch_HEAD_historical.py.snapshot': OLD_REAL['sha256'],
 'resumed_20261016_real_launch_historical_recovery_v1.json': '14a56bac7ba4cb364d32ff73cce584bed1dfdb9646302ba0e29d53cee49cb94c',
}
PIN17 = {
    'archive_inventory_v1.json': '59ef7f3df168720079f1394536fec169b241b18bab818b6d2f6679a6a16f8ce2',
    'delivery_verification.json': '0864ec5b6d3879d99d405f32df6a6a22edad3ab21b31213e0412aeeb299d7a29',
    'evidence/analysis_QA_v1.json': 'b3918f644955d0921238f3d308daae9c7ed1e32c284e1e28d5e65102272fafed',
    'evidence/rejection_audit_v1.json': '3a0e9a95ceee10b2bc122a2a4f4282d07eb4d52822f41475a7f6d9896fc7d30a',
}

# Import only stable-stream/workspace utilities from the pinned original helper.
# Its protect/capture/parent-semantic subprocess functions are never invoked.
spec = importlib.util.spec_from_file_location('ordered_parent_preservation_utilities', P / 'protection_v1.py')
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)
C = V.C


def git(args, allow_failure=False):
    result = subprocess.run(['git', '--no-optional-locks', *args], cwd='/home/trevor/USV',
                            env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'), capture_output=True, timeout=30)
    C.require(len(result.stdout) + len(result.stderr) <= 8 * 1024**2, 'finite_git_output')
    if not allow_failure:
        C.require(result.returncode == 0, 'git_read_failed:' + args[0])
    return result


def verify_resumed_delta():
    for name, sha in RESUMED_PINS.items():
        C.require(V.stable_sha(H / 'preflight' / name)['sha256'] == sha, 'explicit_resume_record_changed:' + name)
    current = V.stable_sha(REAL)
    C.require(current == NEW_REAL, 'explicit_one_live_path_current_bytes_or_mode_changed')
    delta = git(['diff', '--binary', '--', REAL_REL]).stdout
    from_head = git(['diff', 'HEAD', '--binary', '--', REAL_REL]).stdout
    staged = git(['diff', '--cached', '--binary', '--', REAL_REL]).stdout
    C.require(delta == from_head == (H / 'preflight/resumed_20261016_real_launch.diff').read_bytes()
              and len(delta) == 515 and C.digest(delta) == DELTA_DIFF_SHA and staged == b'',
              'explicit_live_delta_or_staging_changed')
    old_blob = git(['show', '78999cf380c0b0dd7f545e4dc8103b7c4c2f7b15:' + REAL_REL]).stdout
    C.require(len(old_blob) == OLD_REAL['bytes'] and C.digest(old_blob) == OLD_REAL['sha256']
              and old_blob == (H / 'preflight/resumed_20261016_real_launch_HEAD_historical.py.snapshot').read_bytes(),
              'historical_HEAD_blob_no_longer_matches_original_roster')
    return current


def workspace():
    # Scope the original 24 changes exactly, while separately pinning one fully
    # declared later live-path delta. No restoration or broad dirty exclusion.
    verify_resumed_delta()
    exclude = ['.', ':(exclude).gitignore', ':(exclude)' + REAL_REL]
    original_diff = git(['diff', '--binary', '--', *exclude]).stdout
    head_diff = git(['diff', 'HEAD', '--binary', '--', *exclude]).stdout
    staged_business = git(['diff', '--cached', '--binary', '--', *exclude]).stdout
    names = [x.decode('utf-8') for x in git(['diff', 'HEAD', '--name-only', '-z', '--', *exclude]).stdout.split(b'\0') if x]
    head = git(['rev-parse', 'HEAD']).stdout.decode().strip()
    branch = git(['branch', '--show-current']).stdout.decode().strip()
    C.require(head == '78999cf380c0b0dd7f545e4dc8103b7c4c2f7b15' and branch == 'codex/scheme-c-rl', 'original_git_identity_changed')
    C.require(len(names) == 24 and len(original_diff) == len(head_diff) == 151961
              and C.digest(original_diff) == C.digest(head_diff) == 'd901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5'
              and staged_business == b'', 'original_24_business_changes_or_staging_changed')
    status = git(['status', '--porcelain=v1', '--branch', '--untracked-files=all']).stdout
    C.require(status.decode().splitlines().count(' M ' + REAL_REL) == 1, 'explicit_live_delta_status_shape_changed')
    staged_all = git(['diff', '--cached', '--binary']).stdout
    gitignore = Path('/home/trevor/USV/.gitignore').read_bytes()
    submodules = git(['submodule', 'status', '--recursive'], allow_failure=True)
    return {'HEAD': head, 'branch': branch, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'business_tracked_files': sorted(names), 'business_tracked_count': len(names),
        'business_diff_bytes': len(original_diff), 'business_diff_sha256': C.digest(original_diff),
        'business_HEAD_diff_sha256': C.digest(head_diff), 'staged_business_diff_sha256': C.digest(staged_business),
        'staged_all_diff_bytes': len(staged_all), 'staged_all_diff_sha256': C.digest(staged_all),
        'gitignore_bytes': len(gitignore), 'gitignore_sha256': C.digest(gitignore),
        'status_porcelain': status.decode('utf-8'), 'status_porcelain_sha256': C.digest(status),
        'submodule_status_returncode': submodules.returncode,
        'submodule_status': submodules.stdout.decode('utf-8', errors='replace'),
        'submodule_status_stderr': submodules.stderr.decode('utf-8', errors='replace'),
        'git_optional_locks_disabled': True,
        'scope': 'original HEAD/branch and 24 business dirty files are required stable; other staged/metadata/untracked/submodule state is recorded without mutation'}


def projection(value):
    result = dict(value)
    rows = []
    for line in value['status_porcelain'].splitlines(keepends=True):
        if line.rstrip('\n') == ' M ' + REAL_REL:
            continue
        path = line[3:]
        if path.startswith('"'):
            path = path[1:]
        if line.startswith('?? ') and any(path.startswith(prefix) for prefix in OLD_ROOTS + SEALED_LATER_ROOTS + PARENT_ROOTS + NEW_ROOTS):
            continue
        rows.append(line)
    result['status_porcelain'] = ''.join(rows)
    result['status_porcelain_sha256'] = C.digest(result['status_porcelain'].encode())
    return result


def without_boot(value):
    result = projection(value)
    result.pop('boot_id')
    return result


def add_pin(pins, path, sha, size=None, mode=None):
    if Path(path).is_relative_to(M):pins=DEFERRED_MPC_PINS
    path = str(path)
    row = {'sha256': sha}
    if size is not None:
        row['bytes'] = size
    if mode is not None:
        row['mode'] = mode
    if path in pins:
        for key in row.keys() & pins[path].keys():
            C.require(row[key] == pins[path][key], 'inconsistent_sealed_pin:' + path)
        pins[path].update(row)
    else:
        pins[path] = row


def add_archive(pins, root, inv, extra_pins, metadata_names):
    expected = set(metadata_names)
    directories = set(inv.get('directories', []))
    for row in inv['files']:
        rel = Path(row['relative_path'])
        C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in expected,
                  'unique_normalized_archive_member')
        expected.add(str(rel))
        for parent in rel.parents:
            if str(parent) != '.':
                directories.add(str(parent))
        for archive in (root, M / root.name):
            # Archive copying historically selected its own output mode. The
            # sealed archive byte/size identity, not original source mode, binds it.
            add_pin(pins, archive / rel, row['sha256'], row['bytes'])
    for archive in (root,):
        C.require(V.population(archive) == (expected, directories), 'sealed_complete_population:' + str(archive))
        for name in metadata_names:
            add_pin(pins, archive / name, extra_pins[name])
    return (expected, directories)


PIN18 = {
    'archive_inventory_v1.json': 'f643aa0a7b4ef77280d033277a5771aaa8ede5d771eab277d60f2ccf2927e0b0',
    'delivery_verification.json': '8e7f89c15994afd0b537ee7566abf4d7568b59fe1a8279995b599781b3e7d460',
    'postrun/final_QA_v1.json': 'e1e9e11908157afd4538196d14af5302219cdb104f7a969737b0f33dd5da7933',
    'postrun/author_freeze_v1.json': '05bc2b2694e67cfb314e2024f0f1372a426a300371f26f200687b3e84527f97c',
    'preflight/workspace_final_v4.json': 'e85d3300e41cd22560745572ea65df4889d0b0606e9bed8c0500f9c2733c3a2f',
    'protection_v4.py': '27a72de6bfe655769a5f0a529424990f33d218587c6cb9d5dc3c7f063d0acf9d',
    'finalize_positive_chain_v1.py': 'e2ac34d872ab6f3f20fd2f78174f1f2cd3993efc7bb6bd7fda39092fba5c2fa2',
    'postrun/independent_sequence_review_v1.json': 'dbbf0a1d862ad916458feea76daebd8d012ec4900ce3f4d29b5a9af84476f771',
}
EMPTY_PARENT_BUILD_DIRS = {
    'fixture/build01/CMakeFiles/3.28.3/CompilerIdC/tmp',
    'fixture/build01/CMakeFiles/3.28.3/CompilerIdCXX/tmp',
    'fixture/build01/CMakeFiles/CMakeScratch',
    'fixture/build01/CMakeFiles/pkgRedirects',
    'fixture/build02/CMakeFiles/3.28.3/CompilerIdC/tmp',
    'fixture/build02/CMakeFiles/3.28.3/CompilerIdCXX/tmp',
    'fixture/build02/CMakeFiles/CMakeScratch',
    'fixture/build02/CMakeFiles/pkgRedirects',
}


DEPENDENCY_LOGICAL_ALIASES = {}


def add_recorded_dependency(pins, row):
    logical = Path(row['path'])
    target = Path(row['resolved_path'])
    C.require(logical.is_absolute() and target.is_absolute() and '..' not in logical.parts
              and '..' not in target.parts, 'absolute_recorded_dependency_paths')
    C.require(str(logical.resolve(strict=True)) == str(target), 'sealed_dependency_alias_resolution_changed:' + str(logical))
    if logical != target:
        key = str(logical)
        C.require(key not in DEPENDENCY_LOGICAL_ALIASES or DEPENDENCY_LOGICAL_ALIASES[key] == str(target),
                  'inconsistent_sealed_dependency_alias')
        DEPENDENCY_LOGICAL_ALIASES[key] = str(target)
    add_pin(pins, str(target), row['sha256'], row['bytes'])


def check_dependency_aliases():
    for path, target in DEPENDENCY_LOGICAL_ALIASES.items():
        C.require(str(Path(path).resolve(strict=True)) == target, 'sealed_dependency_alias_resolution_changed:' + path)


def collect_parent18(pins, reader):
    for rel, sha in PIN18.items():
        C.require(C.digest(reader.raw(H / rel)) == sha, 'sealed_D18_metadata_changed:' + rel)
        add_pin(pins, H / rel, sha)
    inv = reader.json(H / 'archive_inventory_v1.json')
    delivery = reader.json(H / 'delivery_verification.json')
    qa = reader.json(H / 'postrun/final_QA_v1.json')
    freeze = reader.json(H / 'postrun/author_freeze_v1.json')
    old = reader.json(H / 'preflight/workspace_final_v4.json')
    C.require(len(inv['files']) == 2501 and delivery['passed'] is True
              and delivery['full_byte_readback'] is True and delivery['complete_population_equal'] is True
              and delivery['files_before_delivery_receipt'] == 2502
              and delivery['archive_inventory_sha256'] == PIN18['archive_inventory_v1.json']
              and delivery['final_QA_sha256'] == PIN18['postrun/final_QA_v1.json']
              and delivery['source'] == str(H) and delivery['destination'] == str(M / H.name), 'complete_D18_archive_scope')
    C.require(qa['passed'] is True and qa['fixed_file_count'] == len(qa['fixed_files']) == 2499
              and qa['author_frozen_files'] == 957 and qa['component_sequence_completed'] == ['A','A2','B','C']
              and qa['stage_qualified'] is False and qa['research_conclusion'] is False
              and qa['final_old_protection_sha256'] == PIN18['preflight/workspace_final_v4.json'], 'complete_D18_QA_scope')
    C.require(old['passed'] is True and old['protection']['schema'] == 'SchemeA-ordered-positive-preservation/v4'
              and old['protection']['unique_raw_files_reread'] == 39781
              and old['protection']['raw_paths_equal_recorded_old_bytes'] == 39780
              and old['protection']['all_historical_original_path_bytes_unchanged'] is False
              and old['protection']['explicit_live_original_path_exceptions'] == [{
                'path': REAL, 'old_pin': OLD_REAL, 'current_pin': NEW_REAL, 'diff_bytes':515,
                'diff_sha256':DELTA_DIFF_SHA, 'origin':'unknown; present before resumed turn',
                'current_live_file_edited_or_restored_by_this_batch':False,
                'old_bytes_retained_in_original_Git_HEAD':True,
                'historical_recovery_snapshot_written_at_resume':True}], 'archived_V4_explicit_scope_preserved')
    archive_population = add_archive(pins, H, inv, PIN18, ('archive_inventory_v1.json','delivery_verification.json'))
    for path, row in qa['fixed_files'].items():
        C.require(Path(path).is_relative_to(H), 'D18_QA_fixed_scope')
        add_pin(pins, path, row['sha256'], row['bytes'])
    C.require(freeze['count'] == len(freeze['files']) == 957 and freeze['all_source_and_failed_attempts_preserved'] is True,
              'entire_N18_author_snapshot_scope')
    names, dirs = set(), set()
    for row in freeze['files']:
        rel = Path(row['relative_path'])
        C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in names, 'unique_N18_freeze_relative_path')
        names.add(str(rel))
        for parent in rel.parents:
            if str(parent) != '.': dirs.add(str(parent))
        C.require(row['original'] == str(N18 / rel) and row['snapshot'] == str(H / 'author_snapshot' / rel), 'exact_N18_freeze_original_copy_paths')
        for field in ('original','snapshot'):
            add_pin(pins, row[field], row['sha256'], row['bytes'])
    C.require(len(dirs) == 95 and V.population(H / 'author_snapshot') == (names, dirs), 'exact_N18_snapshot_population')
    author_population = (names, dirs | EMPTY_PARENT_BUILD_DIRS)
    C.require(V.population(N18) == author_population, 'exact_N18_original_population_with_named_empty_build_dirs')
    for rel in EMPTY_PARENT_BUILD_DIRS:
        C.require(V.directory_entries(N18 / rel) == [], 'named_parent_build_directory_no_longer_empty')
    for path, sha in qa['selected_assets'].items(): add_pin(pins, path, sha)
    for role, selected in qa['selected_builds'].items():
        directory = Path(selected['source_bundle']['path']).parent
        C.require(directory.is_relative_to(H / 'build'), 'selected_parent_build_scope')
        result_path = directory / 'result.json'
        C.require(C.digest(reader.raw(result_path)) == selected['result_sha256'], 'selected_parent_build_result_identity')
        result = reader.json(result_path)
        C.require(result['passed'] is True and result['role'] == role
                  and result['source_bundle'] == selected['source_bundle']
                  and result['binary_sha256'] == selected['binary_sha256'], 'selected_parent_build_tuple')
        add_pin(pins, result['binary'], result['binary_sha256'])
        descriptor_path = Path(selected['source_bundle']['path'])
        C.require(C.digest(reader.raw(descriptor_path)) == selected['source_bundle']['sha256'], 'selected_parent_source_bundle_identity')
        descriptor = reader.json(descriptor_path)
        for row in descriptor['files'].values(): add_pin(pins,row['path'],row['sha256'],row['bytes'])
        for name in ('compiler_dependency_pins.json','runtime_library_pins.json'):
            dependency = reader.json(directory / name)
            for row in dependency['files'].values(): add_recorded_dependency(pins,row)
    for name in ('A_preregistration_v1.json','controlled_preregistration_v1.json','controlled_preregistration_v2.json'):
        pre = reader.json(H / 'preregister' / name)
        for path, row in pre['helper_files'].items():
            add_pin(pins,path,row['sha256']);add_pin(pins,row['snapshot'],row['sha256'])
        for path, sha in pre['asset_sha256'].items(): add_pin(pins,path,sha)
    for case, row in qa['cases'].items():
        path = Path(row['path'])
        C.require(path.is_relative_to(H / 'runs') and C.digest(reader.raw(path)) == row['sha256'], 'selected_parent_case_identity')
        case_result = reader.json(path)
        C.require(case_result['passed'] is True and case_result['issues'] == [], 'selected_parent_case_passed_record')
        for path, sha in case_result['input_sha256_after'].items(): add_pin(pins,path,sha)
    return archive_population, author_population, old['protection']


PIN19 = {
    'archive_inventory_v1.json': 'de2c4a78a05529be49d75ae0e00995459d939d2beae4061929f3dfb7a7c663a2',
    'delivery_verification.json': 'bf621c6693ca15abe77b738005702545c6487fdba9d0fe64233d9f85d95142d7',
    'postrun/final_QA_v1.json': 'fc7314451ca2ba5ee294b59de615696625853ffced4d7177cfc3208fab5c131d',
    'postrun/author_freeze_v1.json': '9c76e4abe67837815ec89ecbcbadc19429d65e233efb7bf4384bb186b6189c98',
    'preflight/workspace_final_v2.json': 'e80025daf55abd314105cbc768bd25e862ea27ad05c053c8ab5ad3b4248e7268',
    'protection_v2.py': '585deadbb4043d7390f4c884b37c2caf040e61f90a199c712f7441acdf5eb27e',
    'finalize_longitudinal_v1.py': 'e6d63e4f15f96287986e77b95fc6f291a67a218634669ddd6426dfa47c6c455d',
}
ADDITIONAL_COMPILER_ALIASES = {}


def add_recorded_compiler_input(pins, row):
    logical = Path(row['path'])
    target = Path(row['resolved_path'])
    C.require(logical.is_absolute() and target.is_absolute()
              and str(logical.resolve(strict=True)) == str(target), 'recorded_compiler_alias_changed')
    if logical != target:
        key = str(logical)
        C.require(key not in ADDITIONAL_COMPILER_ALIASES or ADDITIONAL_COMPILER_ALIASES[key] == str(target),
                  'inconsistent_recorded_compiler_alias')
        ADDITIONAL_COMPILER_ALIASES[key] = str(target)
    add_pin(pins, str(target), row['sha256'], row['bytes'])


def check_compiler_aliases():
    for path, target in ADDITIONAL_COMPILER_ALIASES.items():
        C.require(str(Path(path).resolve(strict=True)) == target, 'recorded_compiler_alias_changed:' + path)


def collect_parent19(pins, reader):
    for rel, sha in PIN19.items():
        C.require(C.digest(reader.raw(J / rel)) == sha, 'sealed_D19_metadata_changed:' + rel)
        add_pin(pins, J / rel, sha)
    inv = reader.json(J / 'archive_inventory_v1.json')
    delivery = reader.json(J / 'delivery_verification.json')
    qa = reader.json(J / 'postrun/final_QA_v1.json')
    freeze = reader.json(J / 'postrun/author_freeze_v1.json')
    old = reader.json(J / 'preflight/workspace_final_v2.json')
    C.require(len(inv['files']) == 851 and delivery['passed'] is True
              and delivery['full_byte_readback'] is True and delivery['full_second_SHA_readback'] is True
              and delivery['complete_population_equal'] is True and delivery['final_regular_files_per_root'] == 853
              and delivery['files_before_delivery_receipt'] == 852
              and delivery['archive_inventory_sha256'] == PIN19['archive_inventory_v1.json']
              and delivery['final_QA_sha256'] == PIN19['postrun/final_QA_v1.json']
              and delivery['author_freeze_sha256'] == PIN19['postrun/author_freeze_v1.json']
              and delivery['source'] == str(J) and delivery['destination'] == str(M / J.name), 'complete_D19_archive_scope')
    C.require(qa['passed'] is True and qa['archive_integrity_passed'] is True
              and qa['passed_semantics'] == 'archive integrity only; actual ordered component outcomes remain separate'
              and qa['fixed_file_count'] == len(qa['fixed_files']) == 850 and qa['author_frozen_files'] == 528
              and qa['cases_complete'] is True and qa['all_planned_cases_passed'] is True
              and qa['ordered_execution_valid'] is True and len(qa['cases']) == 4
              and qa['stage_qualified'] is False and qa['execute_qualified'] is False and qa['research_conclusion'] is False
              and qa['final_protection_v2_sha256'] == PIN19['preflight/workspace_final_v2.json']
              and qa['author_freeze_sha256'] == PIN19['postrun/author_freeze_v1.json'], 'complete_D19_QA_scope')
    C.require(old['passed'] is True and old['protection']['schema'] == 'SchemeA-longitudinal-preservation/v2'
              and old['protection']['unique_raw_files_reread'] == 45776
              and old['protection']['raw_paths_equal_recorded_old_bytes'] == 45775
              and old['protection']['parent_D18_archive_pairs'] == 2503
              and old['protection']['parent_N18_author_pairs'] == 957
              and old['protection']['parent_D18_recorded_dependency_logical_aliases_rechecked'] == 20
              and old['protection']['all_historical_original_path_bytes_unchanged'] is False
              and len(old['protection']['explicit_live_original_path_exceptions']) == 1
              and old['protection']['explicit_live_original_path_exceptions'][0]['path'] == REAL
              and old['protection']['explicit_live_original_path_exceptions'][0]['current_pin'] == NEW_REAL,
              'archived_D19_full_protection_scope_preserved')
    archive_population = add_archive(pins,J,inv,PIN19,('archive_inventory_v1.json','delivery_verification.json'))
    for path,row in qa['fixed_files'].items():
        C.require(Path(path).is_relative_to(J),'D19_fixed_QA_scope')
        add_pin(pins,path,row['sha256'],row['bytes'])
    C.require(freeze['count'] == len(freeze['files']) == 528
              and freeze['all_sources_runs_failed_attempts_and_raw_Storage_preserved'] is True
              and len(freeze['directories']) == 33,'complete_N19_author_freeze_scope')
    names,dirs = set(),set(freeze['directories'])
    C.require(len(dirs)==33 and all(not Path(p).is_absolute() and '..' not in Path(p).parts for p in dirs),'N19_directory_declarations')
    for row in freeze['files']:
        rel=Path(row['relative_path'])
        C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in names,'unique_N19_freeze_relative')
        names.add(str(rel))
        C.require(row['original']==str(N19/rel) and row['snapshot']==str(J/'author_snapshot'/rel),'N19_exact_original_snapshot_paths')
        for field in ('original','snapshot'):add_pin(pins,row[field],row['sha256'],row['bytes'])
    author_population=(names,dirs)
    C.require(V.population(N19)==author_population and V.population(J/'author_snapshot')==author_population,'N19_complete_original_snapshot_population')
    for path,sha in qa['selected_assets'].items():add_pin(pins,path,sha)
    C.require(set(qa['selected_builds'])=={'publisher','worker','observer','fixture','recorder'},'D19_selected_five_role_scope')
    for role,selected in qa['selected_builds'].items():
        add_recorded_dependency(pins,selected['runtime'])
        descriptor_path=Path(selected['source_bundle']['path'])
        C.require(C.digest(reader.raw(descriptor_path))==selected['source_bundle']['sha256'],'D19_selected_bundle_identity')
        descriptor=reader.json(descriptor_path)
        for row in descriptor['files'].values():add_pin(pins,row['path'],row['sha256'],row['bytes'])
        if 'result_path' in selected:
            result_path=Path(selected['result_path'])
            C.require(C.digest(reader.raw(result_path))==selected['result_sha256'],'D19_selected_build_result_identity')
            result=reader.json(result_path)
            C.require(result['passed'] is True and result['role']==role and result['source_bundle']==selected['source_bundle']
                      and result['binary_sha256']==selected['runtime']['sha256'],'D19_selected_build_tuple')
        else:C.require(role=='recorder' and selected['reused_from_parent'] is True,'D19_reused_Recorder_scope')
        for name,row in selected['compiler_and_loader_manifests'].items():
            path=Path(row['path']);C.require(C.digest(reader.raw(path))==row['sha256'],'D19_dependency_manifest_identity')
            manifest=reader.json(path);C.require(len(manifest['files'])==row['verified_files'],'D19_dependency_manifest_population')
            for value in manifest['files'].values():add_recorded_dependency(pins,value)
            for key in ('compiler','compile_commands'):
                if isinstance(manifest.get(key),dict) and 'path' in manifest[key]:add_recorded_compiler_input(pins,manifest[key])
            for value in manifest.get('compiler_dependency_files',{}).values():add_recorded_compiler_input(pins,value)
        for row in (selected.get('finite_native') or {}).get('GTest_XML',[]):add_pin(pins,row['path'],row['sha256'])
    pre_path=J/'preregister/longitudinal_v1.json'
    C.require(C.digest(reader.raw(pre_path))==qa['preregistration_sha256'],'D19_preregistration_identity')
    pre=reader.json(pre_path)
    C.require(pre['measurement_seconds']==20,'D19_recorded_measurement_scope')
    for path,row in pre['helper_files'].items():add_pin(pins,path,row['sha256']);add_pin(pins,row['snapshot'],row['sha256'])
    for path,sha in pre['asset_sha256'].items():add_pin(pins,path,sha)
    for case,row in qa['cases'].items():
        path=Path(row['path'])
        C.require(path.is_relative_to(J/'runs') and row['status']=='passed' and row['driver_passed'] is True
                  and C.digest(reader.raw(path))==row['sha256'],'D19_selected_actual_case_identity')
        value=reader.json(path)
        C.require(value['passed'] is True and value['issues']==[] and value['input_sha256_before']==value['input_sha256_after'],'D19_actual_case_readonly_record')
        for path,sha in value['input_sha256_after'].items():add_pin(pins,path,sha)
    return archive_population,author_population,old['protection']



K=D.parent/'scheme_A_reference_bias_20261016_20'
N20=D.parent/'p1_execution_architecture_20261005_01/authored_D1_reference_bias_20261016_v20'
PIN20={'archive_inventory_v1.json': '9de68deca6254a9cc6211af8541d65fffcb2b2beacbce30c0bdc3dcb89065c6c', 'delivery_verification.json': '783afde630236564c57653dbac00b9b60a3b9dfb9e13f261e6cc7df99a423ea5', 'postrun/final_QA_v1.json': '635035ecd65547529ac4ce335ad882f5610f270bc1340bb0d9d2cb078e7985c7', 'postrun/author_freeze_v1.json': 'e022ab8758e8daa93de68c876c298396e3d4da52f3b6cffe2b1ce74e5c1f29dc', 'preflight/workspace_final_v1.json': '85be44b415ed3c75fddee133dc38f2eb64c256e5d34857b815c5533d89b91aff', 'protection_v1.py': 'c2dd72f8cee9abc4c6be2a5057701e0cd50d4a461bbd13ca1630272f4ab34d00', 'finalize_reference_bias_v1.py': '278c847c543196963d4671b189fa7b71c27dd1d887ee3145b59608d6d4218347'}

def collect_parent20(pins,reader):
    for rel,sha in PIN20.items():
        C.require(C.digest(reader.raw(K/rel))==sha,'sealed_D20_metadata_changed:'+rel)
        add_pin(pins,K/rel,sha)
    inv=reader.json(K/'archive_inventory_v1.json');delivery=reader.json(K/'delivery_verification.json')
    qa=reader.json(K/'postrun/final_QA_v1.json');freeze=reader.json(K/'postrun/author_freeze_v1.json')
    old=reader.json(K/'preflight/workspace_final_v1.json')
    C.require(len(inv['files'])==926 and delivery['passed'] is True and delivery['final_regular_files_per_root']==928
        and delivery['full_byte_readback'] and delivery['full_second_SHA_readback'] and delivery['complete_population_equal']
        and delivery['archive_inventory_sha256']==PIN20['archive_inventory_v1.json']
        and delivery['final_QA_sha256']==PIN20['postrun/final_QA_v1.json']
        and delivery['author_freeze_sha256']==PIN20['postrun/author_freeze_v1.json']
        and delivery['source']==str(K) and delivery['destination']==str(M/K.name),'complete_D20_archive_scope')
    C.require(qa['passed'] is True and qa['archive_integrity_passed'] is True
        and qa['fixed_file_count']==len(qa['fixed_files'])==925 and qa['author_frozen_files']==291
        and qa['cases_complete'] is False and qa['all_planned_cases_passed'] is False
        and qa['batch_status']=='blocked_gate' and qa['blocked_gate']=='s005'
        and qa['cases']['s005']['status']=='failed'
        and len(qa['cases']['s005']['issues'])==1
        and qa['cases']['s005']['issues'][0]['code']=='projected_preregistered_whole_measurement_RMSE_halved_parent'
        and all(qa['cases'][k]['status']=='not_run' for k in ['s010','s030','s060'])
        and qa['ordered_execution_valid'] and qa['stage_qualified'] is False
        and qa['execute_qualified'] is False and qa['research_conclusion'] is False
        and qa['final_protection_v1_sha256']==PIN20['preflight/workspace_final_v1.json'],'honest_D20_failed_performance_scope')
    C.require(old['passed'] is True and old['protection']['unique_raw_files_reread']==48010
        and old['protection']['raw_paths_equal_recorded_old_bytes']==48009
        and old['protection']['all_historical_original_path_bytes_unchanged'] is False
        and len(old['protection']['explicit_live_original_path_exceptions'])==1,'archived_D20_protection_scope')
    archive_population=add_archive(pins,K,inv,PIN20,('archive_inventory_v1.json','delivery_verification.json'))
    for path,row in qa['fixed_files'].items():
        C.require(Path(path).is_relative_to(K),'D20_fixed_QA_scope');add_pin(pins,path,row['sha256'],row['bytes'])
    C.require(freeze['count']==len(freeze['files'])==291 and freeze['bytes']==63903967
        and len(freeze['directories'])==17 and freeze['all_sources_runs_failed_attempts_and_raw_Storage_preserved'],'complete_N20_freeze')
    names=set();dirs=set(freeze['directories'])
    for row in freeze['files']:
        rel=Path(row['relative_path']);C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in names,'N20_unique_relative_path')
        names.add(str(rel));C.require(row['original']==str(N20/rel) and row['snapshot']==str(K/'author_snapshot'/rel),'N20_exact_original_snapshot')
        for key in ['original','snapshot']:add_pin(pins,row[key],row['sha256'],row['bytes'])
    author_population=(names,dirs)
    C.require(V.population(N20)==author_population==V.population(K/'author_snapshot'),'N20_exact_population')
    for path,sha in qa['selected_assets'].items():add_pin(pins,path,sha)
    for role,selected in qa['selected_builds'].items():
        add_recorded_dependency(pins,selected['runtime'])
        path=Path(selected['source_bundle']['path']);C.require(C.digest(reader.raw(path))==selected['source_bundle']['sha256'],'D20_selected_bundle')
        descriptor=reader.json(path)
        for row in descriptor['files'].values():add_pin(pins,row['path'],row['sha256'],row['bytes'])
        if 'result_path' in selected:
            path=Path(selected['result_path']);C.require(C.digest(reader.raw(path))==selected['result_sha256'],'D20_selected_result')
            result=reader.json(path);C.require(result['passed'] is True and result['source_bundle']==selected['source_bundle'] and result['binary_sha256']==selected['runtime']['sha256'],'D20_build_tuple')
        for row in selected['compiler_and_loader_manifests'].values():
            path=Path(row['path']);C.require(C.digest(reader.raw(path))==row['sha256'],'D20_dependency_manifest')
            manifest=reader.json(path);C.require(len(manifest['files'])==row['verified_files'],'D20_dependency_population')
            for item in manifest['files'].values():add_recorded_dependency(pins,item)
            for key in ['compiler','compile_commands']:
                if isinstance(manifest.get(key),dict):add_recorded_compiler_input(pins,manifest[key])
            for item in manifest.get('compiler_dependency_files',{}).values():add_recorded_compiler_input(pins,item)
        if 'static_link_inputs_before' in selected:
            row=selected['static_link_inputs_before'];path=Path(row['path']);C.require(C.digest(reader.raw(path))==row['sha256'],'D20_explicit_static_input_leaf')
            manifest=reader.json(path);C.require(len(manifest['files'])==row['archives'],'D20_actual_archive_count')
            for item in manifest['files'].values():
                add_recorded_compiler_input(pins,item);add_pin(pins,item['snapshot']['path'],item['sha256'],item['bytes'])
            for item in manifest['link_command_files'].values():add_pin(pins,item['path'],item['sha256'],item['bytes'])
    pre=reader.json(K/'preregister/projected_v1.json')
    C.require(C.digest(reader.raw(K/'preregister/projected_v1.json'))==qa['preregistration_sha256'],'D20_preregistration')
    for path,row in pre['helper_files'].items():add_pin(pins,path,row['sha256']);add_pin(pins,row['snapshot'],row['sha256'])
    for path,sha in pre['asset_sha256'].items():add_pin(pins,path,sha)
    case=qa['cases']['s005'];value=reader.json(case['path'])
    C.require(C.digest(reader.raw(case['path']))==case['sha256'] and value['passed'] is False and value['input_sha256_before']==value['input_sha256_after'],'D20_failed_case_exact_readonly')
    for path,sha in value['input_sha256_after'].items():add_pin(pins,path,sha)
    return archive_population,author_population



K21=D.parent/'scheme_A_reference_time_anchor_20261017_21'
N21=D.parent/'p1_execution_architecture_20261005_01/authored_D1_reference_time_anchor_20261018_v21r2'
PIN21={'archive_inventory_v1.json': 'eb71e64d2f1b5201c14bc2dba2085e59c69abe7c58b4e56582e86794b25f47fc', 'delivery_verification.json': '9d7fe808d5680cf7cf27c54681d91c87ac2155d96b9fb18303628e121e6c238b', 'postrun/final_QA_v1.json': '315d829488a564ae39e50a2906ffb947c5e53b0c47e760c2ad2079ddf33829d3', 'postrun/author_freeze_v1.json': '18009522b2ce1515f6327b961f64afc76d320082da2b50ac3d269e6e96b34cb1', 'preflight/workspace_final_v2.json': '3f21c6695bd9c64137f2d82d124aeac0e1214144ebbd2d246779efbe6bd857a2', 'protection_v2.py': '660752ea54b74a9de0be5a126d36620fbd2527d8707cf77aa8fe49b0991ecdb9', 'finalize_reference_time_anchor_v2.py': '32eb838290d64381c33ec3f05b97c3854b39c6071ae428a8af8f95cd78579960', 'postrun/revision01_author_freeze_v1.json': '93c285567872ef4602175f3cad4105f6d9c14ae6a2bc1dfe95e6b9c80757534c'}

def collect_parent21(pins,reader):
    for rel,sha in PIN21.items():
        C.require(C.digest(reader.raw(K21/rel))==sha,'sealed_D21_metadata_changed:'+rel);add_pin(pins,K21/rel,sha)
    inv=reader.json(K21/'archive_inventory_v1.json');delivery=reader.json(K21/'delivery_verification.json');qa=reader.json(K21/'postrun/final_QA_v1.json');freeze=reader.json(K21/'postrun/author_freeze_v1.json');old=reader.json(K21/'preflight/workspace_final_v2.json')
    C.require(len(inv['files'])==1674 and delivery['passed'] is True and delivery['final_regular_files_per_root']==1676 and delivery['full_byte_readback'] and delivery['full_second_SHA_readback'] and delivery['complete_population_equal'] and delivery['archive_inventory_sha256']==PIN21['archive_inventory_v1.json'] and delivery['final_QA_sha256']==PIN21['postrun/final_QA_v1.json'] and delivery['author_freeze_sha256']==PIN21['postrun/author_freeze_v1.json'],'D21_complete_archive_scope')
    C.require(qa['passed'] is True and qa['archive_integrity_passed'] is True and qa['fixed_file_count']==len(qa['fixed_files'])==1673 and qa['author_frozen_files']==291 and qa['cases_complete'] is False and qa['all_planned_cases_passed'] is False and qa['batch_status']=='blocked_gate' and qa['blocked_gate']=='s005' and qa['cases']['s005']['status']=='failed' and {r['code'] for r in qa['cases']['s005']['issues']}=={'longitudinal_20s_all_candidates_accepted_90_consecutive_18s_coverage','projected_preregistered_whole_measurement_RMSE_halved_parent'} and all(qa['cases'][k]['status']=='not_run' for k in ['s010','s030','s060']) and qa['revision01_unreleased_startup_failure_preserved'] is True and qa['ordered_execution_valid'] and qa['stage_qualified'] is False and qa['execute_qualified'] is False and qa['research_conclusion'] is False,'D21_two_failed_gates_and_startup_failure_preserved')
    C.require(old['passed'] and old['protection']['unique_raw_files_reread']==50703 and old['protection']['raw_paths_equal_recorded_old_bytes']==50702 and old['protection']['all_historical_original_path_bytes_unchanged'] is False,'D21_final_protection_preserved')
    archive_population=add_archive(pins,K21,inv,PIN21,('archive_inventory_v1.json','delivery_verification.json'))
    for path,row in qa['fixed_files'].items():C.require(Path(path).is_relative_to(K21),'D21_fixed_QA_scope');add_pin(pins,path,row['sha256'],row['bytes'])
    C.require(freeze['count']==len(freeze['files'])==291 and freeze['bytes']==49042326 and len(freeze['directories'])==15,'N21_full_author_freeze_scope')
    names=set();dirs=set(freeze['directories'])
    for row in freeze['files']:
        rel=Path(row['relative_path']);C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in names and row['original']==str(N21/rel) and row['snapshot']==str(K21/'author_snapshot'/rel),'N21_exact_frozen_paths');names.add(str(rel))
        for key in ['original','snapshot']:add_pin(pins,row[key],row['sha256'],row['bytes'])
    author_population=(names,dirs);C.require(V.population(N21)==author_population==V.population(K21/'author_snapshot'),'N21_frozen_population')
    for path,sha in qa['selected_assets'].items():add_pin(pins,path,sha)
    for selected in list(qa['selected_builds'].values())+list(qa['revision01_selected_builds'].values()):
        add_recorded_dependency(pins,selected['runtime']);path=Path(selected['source_bundle']['path']);C.require(C.digest(reader.raw(path))==selected['source_bundle']['sha256'],'D21_source_bundle_identity');descriptor=reader.json(path)
        for row in descriptor['files'].values():add_pin(pins,row['path'],row['sha256'],row['bytes'])
        if 'result_path' in selected:
            path=Path(selected['result_path']);C.require(C.digest(reader.raw(path))==selected['result_sha256'],'D21_selected_build_identity');result=reader.json(path);C.require(result['passed'] and result['source_bundle']==selected['source_bundle'] and result['binary_sha256']==selected['runtime']['sha256'],'D21_selected_build_tuple')
        for row in selected['compiler_and_loader_manifests'].values():
            path=Path(row['path']);C.require(C.digest(reader.raw(path))==row['sha256'],'D21_dependency_manifest');manifest=reader.json(path);C.require(len(manifest['files'])==row['verified_files'],'D21_dependency_count')
            for item in manifest['files'].values():add_recorded_dependency(pins,item)
            for key in ['compiler','compile_commands']:
                if isinstance(manifest.get(key),dict):add_recorded_compiler_input(pins,manifest[key])
            for item in manifest.get('compiler_dependency_files',{}).values():add_recorded_compiler_input(pins,item)
        leaf=selected.get('static_link_inputs_before')
        if leaf:
            path=Path(leaf['path']);C.require(C.digest(reader.raw(path))==leaf['sha256'],'D21_static_leaf');manifest=reader.json(path)
            for item in manifest['files'].values():add_recorded_compiler_input(pins,item);add_pin(pins,item['snapshot']['path'],item['sha256'],item['bytes'])
            for item in manifest['link_command_files'].values():add_pin(pins,item['path'],item['sha256'],item['bytes'])
    pre=reader.json(K21/'preregister/task_time_v2.json');C.require(C.digest(reader.raw(K21/'preregister/task_time_v2.json'))==qa['preregistration_sha256'],'D21_current_preregistration')
    for path,row in pre['helper_files'].items():add_pin(pins,path,row['sha256']);add_pin(pins,row['snapshot'],row['sha256'])
    case=qa['cases']['s005'];r=reader.json(case['path']);C.require(C.digest(reader.raw(case['path']))==case['sha256'] and r['passed'] is False and r['input_sha256_before']==r['input_sha256_after'],'D21_failed_readonly_case')
    for path,sha in r['input_sha256_after'].items():add_pin(pins,path,sha)
    return archive_population,author_population



K22=D.parent/'scheme_A_reference_pair_wakeup_20261018_22'
N22=D.parent/'p1_execution_architecture_20261005_01/authored_D1_reference_pair_wakeup_20261018_v22'
PIN22={'archive_inventory_v1.json': '327998bd79e667ebec5e65fba91393586aacba67175bf282767bc0d3ecee91e8', 'delivery_verification.json': '730467a26b8b42a40106e2e4eae326a8ee28eef1f2a0c10e6128d151fe181525', 'postrun/final_QA_v1.json': '5b0dfc789b80a8249b2606f3f0cc604a91e8a85f40eab4147826b753049b2b56', 'postrun/author_freeze_v1.json': 'f7010d7d2f5146ff7a3a48b70164010cf97d4c4ee5e7adc25046b0204b13ddd0', 'preflight/workspace_final_v1.json': '08a9caf3871c5c13050d5f458bc5369390e5fb1091cb193102f11d00402e8ea3', 'protection_v1.py': 'd74ca524d7f430ae864f7a5e22c537bacf3f32ee9994aeaca973f47334a27fd6', 'finalize_pair_wakeup_v1.py': '003f3ebd25c1366f0fa81b4029245b58499a0705f5775fb719026e4b23bec107'}

def collect_parent22(pins,reader):
    for rel,sha in PIN22.items():C.require(C.digest(reader.raw(K22/rel))==sha,'D22_sealed_metadata_changed:'+rel);add_pin(pins,K22/rel,sha)
    inv=reader.json(K22/'archive_inventory_v1.json');delivery=reader.json(K22/'delivery_verification.json');qa=reader.json(K22/'postrun/final_QA_v1.json');freeze=reader.json(K22/'postrun/author_freeze_v1.json');old=reader.json(K22/'preflight/workspace_final_v1.json')
    C.require(len(inv['files'])==1883 and delivery['passed'] and delivery['full_byte_readback'] and delivery['full_second_SHA_readback'] and delivery['complete_population_equal'] and delivery['final_regular_files_per_root']==1885 and delivery['archive_inventory_sha256']==PIN22['archive_inventory_v1.json'] and delivery['final_QA_sha256']==PIN22['postrun/final_QA_v1.json'] and delivery['author_freeze_sha256']==PIN22['postrun/author_freeze_v1.json'],'D22_complete_archive')
    C.require(qa['passed'] and qa['archive_integrity_passed'] and qa['fixed_file_count']==len(qa['fixed_files'])==1882 and qa['author_frozen_files']==301 and qa['cases_complete'] is False and qa['all_planned_cases_passed'] is False and qa['batch_status']=='blocked_gate' and qa['blocked_gate']=='s005' and qa['cases']['s005']['status']=='failed' and len(qa['cases']['s005']['issues'])==1 and qa['cases']['s005']['issues'][0]['code']=='projected_preregistered_whole_measurement_RMSE_halved_parent' and all(qa['cases'][k]['status']=='not_run' for k in ['s010','s030','s060']) and qa['source_callback_GTest_cases']==19 and qa['actual_DDS_wire_component_cases']==1 and qa['stage_qualified'] is False and qa['execute_qualified'] is False and qa['research_conclusion'] is False,'D22_component_scope_and_performance_failure_preserved')
    C.require(old['passed'] and old['protection']['unique_raw_files_reread']==54073 and old['protection']['raw_paths_equal_recorded_old_bytes']==54072,'D22_final_full_protection')
    archive_population=add_archive(pins,K22,inv,PIN22,('archive_inventory_v1.json','delivery_verification.json'))
    for path,row in qa['fixed_files'].items():C.require(Path(path).is_relative_to(K22),'D22_fixed_QA_scope');add_pin(pins,path,row['sha256'],row['bytes'])
    C.require(freeze['count']==len(freeze['files'])==301 and freeze['bytes']==47834749 and len(freeze['directories'])==15,'N22_full_author_freeze')
    names=set();dirs=set(freeze['directories'])
    for row in freeze['files']:
        rel=Path(row['relative_path']);C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in names and row['original']==str(N22/rel) and row['snapshot']==str(K22/'author_snapshot'/rel),'N22_exact_frozen_paths');names.add(str(rel))
        for key in ['original','snapshot']:add_pin(pins,row[key],row['sha256'],row['bytes'])
    author_population=(names,dirs);C.require(V.population(N22)==author_population==V.population(K22/'author_snapshot'),'N22_frozen_population')
    for path,sha in qa['selected_assets'].items():add_pin(pins,path,sha)
    for selected in qa['selected_builds'].values():
        add_recorded_dependency(pins,selected['runtime']);path=Path(selected['source_bundle']['path']);C.require(C.digest(reader.raw(path))==selected['source_bundle']['sha256'],'D22_source_bundle');bundle=reader.json(path)
        for row in bundle['files'].values():
            if 'resolved_path' in row:add_recorded_compiler_input(pins,row)
            else:add_pin(pins,row['path'],row['sha256'],row['bytes'])
        if 'result_path' in selected:
            path=Path(selected['result_path']);C.require(C.digest(reader.raw(path))==selected['result_sha256'],'D22_selected_build');result=reader.json(path);C.require(result['passed'] and result['source_bundle']==selected['source_bundle'] and result['binary_sha256']==selected['runtime']['sha256'],'D22_selected_build_tuple')
        for row in selected['compiler_and_loader_manifests'].values():
            path=Path(row['path']);C.require(C.digest(reader.raw(path))==row['sha256'],'D22_dependency_manifest');data=reader.json(path)
            for item in data['files'].values():add_recorded_dependency(pins,item)
            for key in ['compiler','compile_commands']:
                if isinstance(data.get(key),dict):add_recorded_compiler_input(pins,data[key])
            for item in data.get('compiler_dependency_files',{}).values():add_recorded_compiler_input(pins,item)
        leaf=selected.get('static_link_inputs_before')
        if leaf:
            path=Path(leaf['path']);C.require(C.digest(reader.raw(path))==leaf['sha256'],'D22_static_leaf');data=reader.json(path)
            for item in data['files'].values():add_recorded_compiler_input(pins,item);add_pin(pins,item['snapshot']['path'],item['sha256'],item['bytes'])
            for item in data['link_command_files'].values():add_pin(pins,item['path'],item['sha256'],item['bytes'])
            for key in ['generated_vendor_sources_before_build','generated_archive_tools_before_build']:
                for item in data.get(key,{}).values():add_recorded_compiler_input(pins,item)
        for item in selected.get('generated_test_archives_after_build',{}).values():add_recorded_compiler_input(pins,item)
    pre=reader.json(K22/'preregister/pair_wakeup_v1.json');C.require(C.digest(reader.raw(K22/'preregister/pair_wakeup_v1.json'))==qa['preregistration_sha256'],'D22_preregistration')
    for path,row in pre['helper_files'].items():add_pin(pins,path,row['sha256']);add_pin(pins,row['snapshot'],row['sha256'])
    case=qa['cases']['s005'];r=reader.json(case['path']);C.require(C.digest(reader.raw(case['path']))==case['sha256'] and r['passed'] is False and r['input_sha256_before']==r['input_sha256_after'] and r['window']['consecutive_accepted']==r['window']['accepted']==r['window']['attempts']==100,'D22_failed_performance_accepted_chain_record')
    for path,sha in r['input_sha256_after'].items():add_pin(pins,path,sha)
    wire=reader.json(K22/'build/wire_component_attempt01/result.json');C.require(wire['passed'] and wire['tests']['tests']==1,'D22_wire_positive_scope')
    desc=reader.json(wire['source_bundle']['path']);C.require(C.digest(reader.raw(wire['source_bundle']['path']))==wire['source_bundle']['sha256'],'D22_wire_bundle')
    for row in desc['files'].values():add_recorded_compiler_input(pins,row)
    dep=reader.json(K22/'build/wire_component_attempt01/compiler_dependency_pins.json')
    for row in dep['files'].values():add_recorded_compiler_input(pins,row)
    return archive_population,author_population



K23=D.parent/'scheme_A_startup_rti_mechanism_20261018_23'
N23=D.parent/'p1_execution_architecture_20261005_01/authored_D1_startup_rti_mechanism_20261018_v23'
PIN23={'archive_inventory_v1.json':'e3fe64aa3c5aa4868ba9724f71ef99ffe719affb61df5ecac113b6f5b3e0ce45','delivery_verification.json':'6a634b922a6bed6cc8f32047d4eaec9d428f59836b14c21ce30ae1bcaf5030fc','postrun/final_QA_v1.json':'b7218e596383b16b8a2dfcaca5b631d5bfe7844d6989c8f4f83f8f1f28a56c41','postrun/author_freeze_v1.json':'bfde4121ee4ba8883293f1963b9eb7e7662f53f3ee919026b2f4692665cdacca','preflight/workspace_final_v3.json':'25924d036627c9690c250ffc8c4035d129bcb164651763d05d5baf7372e0b2e6'}
def collect_parent23(pins,reader):
    for rel,h in PIN23.items():C.require(C.digest(reader.raw(K23/rel))==h,'D23_sealed_metadata:'+rel);add_pin(pins,K23/rel,h)
    inv=reader.json(K23/'archive_inventory_v1.json');qa=reader.json(K23/'postrun/final_QA_v1.json');delivery=reader.json(K23/'delivery_verification.json');freeze=reader.json(K23/'postrun/author_freeze_v1.json')
    C.require(len(inv['files'])==411 and delivery['passed'] and delivery['final_regular_files_per_root']==413 and delivery['archive_inventory_sha256']==PIN23['archive_inventory_v1.json'] and delivery['final_QA_sha256']==PIN23['postrun/final_QA_v1.json'],'D23_historical_delivery_identity_only')
    C.require(qa['passed'] and qa['offline_mechanism_complete'] and qa['primary_mechanism_nearly_unchanged'] is False and qa['new_closed_loop_performance_qualified'] is False and qa['parent_first_RMSE_gate_failure_preserved'] and qa['native_GTest_cases']==10 and qa['independent_checked_answers']==144 and qa['fixed_file_count']==410,'D23_mechanism_and_qualification_scope')
    population=add_archive(pins,K23,inv,PIN23,('archive_inventory_v1.json','delivery_verification.json'))
    for path,row in qa['fixed_files'].items():C.require(Path(path).is_relative_to(K23),'D23_fixed_scope');add_pin(pins,path,row['sha256'],row['bytes'])
    C.require(freeze['count']==len(freeze['files'])==6 and freeze['bytes']==1790179 and freeze['directories']==[],'N23_frozen_scope')
    names=set()
    for row in freeze['files']:
        rel=Path(row['relative_path']);C.require(not rel.is_absolute() and '..' not in rel.parts and row['original']==str(N23/rel) and row['snapshot']==str(K23/'author_snapshot'/rel),'N23_frozen_paths');names.add(str(rel))
        for key in ['original','snapshot']:add_pin(pins,row[key],row['sha256'],row['bytes'])
    author=(names,set());C.require(V.population(N23)==author==V.population(K23/'author_snapshot'),'N23_frozen_population')
    lock=reader.json(K23/'preregister/offline_invocation_lock_v1.json');C.require(len(lock['files'])==828,'D23_complete_actual_closure')
    for path,h in lock['files'].items():add_pin(pins,path,h)
    for logical,target in lock['aliases'].items():
        C.require(str(Path(logical).resolve(strict=True))==target,'D23_sealed_alias')
        if logical!=target:ADDITIONAL_COMPILER_ALIASES[logical]=target
    return population,author



K24=D.parent/'scheme_A_startup_first_control_20261018_24'
N24=D.parent/'p1_execution_architecture_20261005_01/authored_D1_startup_first_control_20261018_v24'
PIN24={'archive_inventory_v1.json':'64b528df3ad20ae12cfdc431f8d825c47975d66425daf754df00f4282f6d2c9a','postrun/final_QA_v1.json':'0938e9fc9397680502e606cd181745d1b72f13f2d2b6ffe4a6be0686b059403f','postrun/author_freeze_v1.json':'3e35d1fe5a9ee2fe5197c68b90564d683cad50be6f8453b4fd9d43982e3f8c71','preflight/workspace_final_local_v1.json':'49f734a68c18e794a9f47b3ba4ceadff3e9b5df39b40c4d168a4e5f66da2f254','postrun/first_control_audit_v1.json':'d4519ae492e00ccdb45496bfa5bc153e2336db3d15571c6cd4b338163d64313b'}
def collect_parent24(pins,reader):
    for rel,h in PIN24.items():C.require(C.digest(reader.raw(K24/rel))==h,'D24_sealed_metadata:'+rel);add_pin(pins,K24/rel,h)
    inv=reader.json(K24/'archive_inventory_v1.json');qa=reader.json(K24/'postrun/final_QA_v1.json');freeze=reader.json(K24/'postrun/author_freeze_v1.json');audit=reader.json(K24/'postrun/first_control_audit_v1.json')
    C.require(len(inv['files'])==401 and qa['passed'] and qa['all_ten_registered_probes_complete'] and qa['native_GTest_cases']==4 and qa['MPC_delivery_verified_at_QA'] is False and qa['remote_MPC_mirrors_currently_verified'] is False and qa['original_RMSE_failure_preserved'] and audit['all_material_pulses_faster_and_cost_worse'] is False,'D24_local_only_scope_and_counterexample')
    names={'archive_inventory_v1.json'};dirs=set(inv['directories'])
    for row in inv['files']:
        rel=Path(row['relative_path']);C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in names,'D24_local_archive_member');names.add(str(rel));add_pin(pins,K24/rel,row['sha256'],row['bytes'])
    population=(names,dirs);C.require(V.population(K24)==population,'D24_complete_LOCAL_archive_no_remote_copy_claim')
    C.require(freeze['count']==len(freeze['files'])==6 and freeze['bytes']==37936,'N24_frozen_source_scope');author_names=set()
    for row in freeze['files']:
        rel=Path(row['relative_path']);C.require(row['original']==str(N24/rel) and row['snapshot']==str(K24/'author_snapshot'/rel),'N24_frozen_paths');author_names.add(str(rel))
        for key in ['original','snapshot']:add_pin(pins,row[key],row['sha256'],row['bytes'])
    author=(author_names,set(freeze['directories']));C.require(V.population(N24)==author==V.population(K24/'author_snapshot'),'N24_complete_local_source')
    lock=reader.json(K24/'preregister/offline_invocation_lock_v1.json');C.require(len(lock['files'])==826,'D24_actual_dependency_closure')
    for path,h in lock['files'].items():add_pin(pins,path,h)
    for logical,target in lock['aliases'].items():
        C.require(str(Path(logical).resolve(strict=True))==target,'D24_sealed_alias')
        if logical!=target:ADDITIONAL_COMPILER_ALIASES[logical]=target
    return population,author



K25=D.parent/'scheme_A_fixed_first_tail_optimization_20261018_25'
N25=D.parent/'p1_execution_architecture_20261005_01/authored_D1_fixed_first_tail_optimization_20261018_v25'
PIN25={'archive_inventory_v1.json':'51d1aca04b4bc343051a187a6a3d65811c38c40a0265fe24aa450e9af08f9137','postrun/final_QA_v1.json':'8decd30227c9b0ab63fd60e9a999bd063800c4e1d0dcfa4cdc525175fe2523c4','postrun/author_freeze_v1.json':'f50e93e05876b2eedabe339ffb95d434ed9dba0f5ec464d44f375acb14b10976','preflight/workspace_final_local_v1.json':'1ffb8650893a47e68058b3b4c487db32d538aa5b73bf0b36cac4eff6b0fc1160','postrun/fixed_first_audit_v2.json':'076c664cd1f1d7504ec50d37d6078bc859eb5e638c5b4d52957f1d76237e0ea2'}
def collect_parent25(pins,reader):
    for rel,h in PIN25.items():C.require(C.digest(reader.raw(K25/rel))==h,'D25_sealed_metadata:'+rel);add_pin(pins,K25/rel,h)
    inv=reader.json(K25/'archive_inventory_v1.json');qa=reader.json(K25/'postrun/final_QA_v1.json');freeze=reader.json(K25/'postrun/author_freeze_v1.json');C.require(len(inv['files'])==419 and qa['passed'] and qa['all_24_iterations_checked'] and qa['native_GTest_cases']==3 and qa['source_rebuild_numerically_identical'] and qa['MPC_delivery_verified_at_QA'] is False and qa['original_RMSE_failure_preserved'],'D25_local_mechanism_scope')
    names={'archive_inventory_v1.json'};dirs=set(inv['directories'])
    for row in inv['files']:
        rel=Path(row['relative_path']);C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in names,'D25_local_member');names.add(str(rel));add_pin(pins,K25/rel,row['sha256'],row['bytes'])
    population=(names,dirs);C.require(V.population(K25)==population,'D25_complete_local_archive')
    C.require(freeze['count']==len(freeze['files'])==7 and freeze['bytes']==47042,'N25_frozen_scope');anames=set()
    for row in freeze['files']:
        rel=Path(row['relative_path']);C.require(row['original']==str(N25/rel) and row['snapshot']==str(K25/'author_snapshot'/rel),'N25_frozen_paths');anames.add(str(rel))
        for key in ['original','snapshot']:add_pin(pins,row[key],row['sha256'],row['bytes'])
    author=(anames,set(freeze['directories']));C.require(V.population(N25)==author==V.population(K25/'author_snapshot'),'N25_frozen_population')
    lock=reader.json(K25/'preregister/offline_invocation_lock_v2.json');C.require(len(lock['files'])==831,'D25_final_selected_closure')
    for path,h in lock['files'].items():add_pin(pins,path,h)
    for logical,target in lock['aliases'].items():
        C.require(str(Path(logical).resolve(strict=True))==target,'D25_selected_alias')
        if logical!=target:ADDITIONAL_COMPILER_ALIASES[logical]=target
    return population,author



K26=D.parent/'scheme_A_causal_cold_start_20261018_26'
N26=D.parent/'p1_execution_architecture_20261005_01/authored_D1_causal_cold_start_20261018_v26'
PIN26={'archive_inventory_v1.json':'f6f0c633e5311d3e88295b038be23d5b3ab5997a58b9f8cdf8c6ed8e1d945b0c','postrun/final_QA_v1.json':'f359f903c58973681329de9f4ddb7037d4f344172474f57de872a290d0048eb2','postrun/author_freeze_v1.json':'2708d8bb8d25ce4b028c10e9d6576095a90f4bb3dc945514226cf00142892b2f','preflight/workspace_final_local_v1.json':'d8299630a5776fe4206f471292a99e07995a6dac474cf518810b82f6543bb4ce','postrun/causal_cold_audit_v1.json':'a011f0db0dda944e9fab23e20433eb0d2f695e9d0280818805a07febb761e847'}
def collect_parent26(pins,reader):
    for rel,h in PIN26.items():C.require(C.digest(reader.raw(K26/rel))==h,'D26_sealed_metadata:'+rel);add_pin(pins,K26/rel,h)
    inv=reader.json(K26/'archive_inventory_v1.json');qa=reader.json(K26/'postrun/final_QA_v1.json');freeze=reader.json(K26/'postrun/author_freeze_v1.json');C.require(len(inv['files'])==229 and qa['passed'] and qa['candidate_component_gates_passed'] and qa['candidate_RTI_calls']==4 and qa['separate_restoration_probe_RTI_calls']==1 and qa['actual_oracle_open_attempts']==0 and qa['MPC_delivery_verified_at_QA'] is False and qa['original_RMSE_failure_preserved'],'D26_offline_component_scope')
    names={'archive_inventory_v1.json'};dirs=set(inv['directories'])
    for row in inv['files']:
        rel=Path(row['relative_path']);C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in names,'D26_archive_member');names.add(str(rel));add_pin(pins,K26/rel,row['sha256'],row['bytes'])
    population=(names,dirs);C.require(V.population(K26)==population,'D26_complete_local_archive')
    C.require(freeze['count']==len(freeze['files'])==8 and freeze['bytes']==77831,'N26_frozen_scope');anames=set()
    for row in freeze['files']:
        rel=Path(row['relative_path']);C.require(row['original']==str(N26/rel) and row['snapshot']==str(K26/'author_snapshot'/rel),'N26_frozen_paths');anames.add(str(rel))
        for key in ['original','snapshot']:add_pin(pins,row[key],row['sha256'],row['bytes'])
    author=(anames,set(freeze['directories']));C.require(V.population(N26)==author==V.population(K26/'author_snapshot'),'N26_frozen_population')
    lock=reader.json(K26/'preregister/offline_invocation_lock_v1.json');C.require(len(lock['files'])==832,'D26_selected_closure')
    for path,h in lock['files'].items():add_pin(pins,path,h)
    for logical,target in lock['aliases'].items():
        C.require(str(Path(logical).resolve(strict=True))==target,'D26_selected_alias')
        if logical!=target:ADDITIONAL_COMPILER_ALIASES[logical]=target
    return population,author


def protect():
    before = workspace()
    reader = C.Reader(seconds=1200, max_bytes=512 * 1024**2, max_files=1000)
    for root, meta in ((P, PIN16), (A, PIN17)):
        for rel, sha in meta.items():
            C.require(C.digest(reader.raw(root / rel)) == sha, 'sealed_metadata_changed:' + str(root / rel))
    anchor = reader.json(P / 'preflight/preservation_anchor_v3.json')
    roster = reader.json(P / 'preflight/preservation_roster_v3.json')
    transition = reader.json(P / 'preflight/boot_transition_v4.json')
    C.require(anchor['roster_sha256'] == PIN16['preflight/preservation_roster_v3.json']
              and transition['original_anchor_sha256'] == PIN16['preflight/preservation_anchor_v3.json']
              and transition['original_roster_sha256'] == anchor['roster_sha256']
              and transition['helper_sha256'] == PIN16['protection_v4.py'], 'original_capture_transition_identity')
    C.require(roster['parent_inventory_sha256'] == V.PIN['archive_inventory_v1.json']
              and roster['parent_QA_sha256'] == V.PIN['postrun/final_QA_current.json']
              and roster['parent_proof_sha256'] == anchor['parent_proof_sha256'], 'historical_semantic_anchor_identity')
    C.require(len(roster['files']) == 34296 and len(roster['directories']) == 1344, 'historical_complete_capture_scope')
    C.require(before['boot_id'] == transition['resumed_boot_id'], 'new_boot_requires_explicit_transition')
    C.require(without_boot(before) == transition['preserved_workspace_projection_without_boot']
              == without_boot(roster['initial_workspace_projection']), 'old_workspace_projection_changed')
    C.require(before['business_tracked_count'] == 24 and before['business_diff_bytes'] == 151961
              and before['business_diff_sha256'] == 'd901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5',
              'original_24_business_changes_changed')
    C.require(roster['files'].get(REAL) == OLD_REAL, 'declared_live_exception_original_roster_identity')
    pins = {path: dict(pin) for path,pin in roster['files'].items() if not Path(path).is_relative_to(M)}
    DEFERRED_MPC_PINS.update({path:dict(pin) for path,pin in roster['files'].items() if Path(path).is_relative_to(M)})
    for path, sha in anchor['provenance_file_sha256'].items():
        add_pin(pins, path, sha)
    for root, meta in ((P, PIN16), (A, PIN17)):
        for rel, sha in meta.items():
            add_pin(pins, root / rel, sha)
    inv16 = reader.json(P / 'archive_inventory_v1.json')
    delivery16 = reader.json(P / 'delivery_verification.json')
    qa16 = reader.json(P / 'postrun/final_QA_current.json')
    C.require(len(inv16['files']) == 2432 and delivery16['passed']
              and delivery16['full_second_SHA_readback'] and delivery16['final_regular_files_per_root'] == 2435,
              'C310_complete_archive_scope')
    C.require(qa16['passed'] and qa16['stage_qualified'] is False and qa16['new_frozen_pairs'] == 2151
              and len(qa16['fixed_source_header_input_hashes']) == 4303, 'C310_current_QA_scope')
    C.require(qa16['parent_before'] == qa16['parent_after'] == inv16['protection']['parent']
              == inv16['protection_after_prepare']['parent'] == delivery16['protected_before']['parent']
              == delivery16['protected_after']['parent'], 'C310_archived_parent_proof_identity')
    C.require(inv16['protection'] == inv16['protection_after_prepare'] == delivery16['protected_before']
              == delivery16['protected_after'] and inv16['protection']['passed']
              and inv16['protection']['current_fixed_paths'] == 4303
              and inv16['protection']['new_frozen_pairs'] == 2151
              and inv16['protection']['current_QA_sha256'] == PIN16['postrun/final_QA_current.json'],
              'C310_current_archive_protection_identity')
    old_proof = qa16['parent_after']
    C.require(old_proof['flat_roster_sha256'] == anchor['roster_sha256']
              and old_proof['parent_chain_proof_sha256'] == roster['parent_proof_sha256']
              and old_proof['boot_transition_record_sha256'] == PIN16['preflight/boot_transition_v4.json']
              and old_proof['old_run_or_endpoint_qualification_transferred'] is False
              and old_proof['current_asset_recheck_boot_id'] == before['boot_id'], 'C310_archived_proof_scope')
    archives16 = add_archive(pins, P, inv16, PIN16,
                             ('archive_inventory_v1.json', 'delivery_verification.json', 'batch_status_final.json'))
    for path, sha in qa16['fixed_source_header_input_hashes'].items():
        add_pin(pins, path, sha)
    frozen = reader.json(P / 'final_frozen_snapshot/manifest.json')
    C.require(len(frozen['files']) == 2151, 'C310_frozen_population')
    for row in frozen['files']:
        for field in ('original', 'copy'):
            add_pin(pins, row[field], row['sha256'], row['bytes'])
    inv17 = reader.json(A / 'archive_inventory_v1.json')
    delivery17 = reader.json(A / 'delivery_verification.json')
    qa17 = reader.json(A / 'evidence/analysis_QA_v1.json')
    audit17 = reader.json(A / 'evidence/rejection_audit_v1.json')
    C.require(len(inv17['files']) == 6 and delivery17['passed']
              and delivery17['full_second_SHA_readback'] and delivery17['final_files_per_root'] == 8
              and qa17['passed'] and qa17['raw_inputs_before_after_equal']
              and qa17['new_ROS_run'] is False and audit17['passed']
              and audit17['source_inputs_before_sha256'] == audit17['source_inputs_after_sha256'], 'analysis_preserved_scope')
    archives17 = add_archive(pins, A, inv17, PIN17, ('archive_inventory_v1.json', 'delivery_verification.json'))
    analysis_inputs = {**audit17['source_inputs_before_sha256'], **qa17['source_code_document_pins']}
    C.require(len(analysis_inputs) == 42, 'analysis_complete_input_scope')
    for path, sha in analysis_inputs.items():
        add_pin(pins, path, sha)
    for path, target in roster['legacy_symlink_targets'].items():
        if Path(path).is_relative_to(M):continue
        C.require(Path(path).is_symlink() and os.readlink(path) == target, 'historical_symlink_changed:' + path)
    for path, target in roster['legacy_symlink_logical_aliases'].items():
        if Path(path).is_relative_to(M):continue
        C.require(str(Path(path).resolve(strict=True)) == target, 'historical_alias_changed:' + path)
    archive18_population, author18_population, archived_parent18_proof = collect_parent18(pins, reader)
    archive19_population,author19_population,archived_parent19_proof=collect_parent19(pins,reader)
    archive20_population,author20_population=collect_parent20(pins,reader)
    revision_path=K21/'postrun/revision01_author_freeze_v1.json'
    C.require(C.digest(reader.raw(revision_path))=='93c285567872ef4602175f3cad4105f6d9c14ae6a2bc1dfe95e6b9c80757534c','revision01_frozen_manifest_changed')
    revision=reader.json(revision_path);revision_names=set();revision_dirs=set(revision['directories'])
    add_pin(pins,revision_path,'93c285567872ef4602175f3cad4105f6d9c14ae6a2bc1dfe95e6b9c80757534c')
    for row in revision['files']:
        revision_names.add(row['relative_path'])
        for key in ['original','snapshot']:add_pin(pins,row[key],row['sha256'],row['bytes'])
    revision_root=D.parent/'p1_execution_architecture_20261005_01/authored_D1_reference_time_anchor_20261017_v21'
    C.require(V.population(revision_root)==(revision_names,revision_dirs)==V.population(K21/'revision01_author_snapshot'),'revision01_exact_frozen_population')
    archive21_population,author21_population=collect_parent21(pins,reader)
    archive22_population,author22_population=collect_parent22(pins,reader)
    archive23_population,author23_population=collect_parent23(pins,reader)
    archive24_population,author24_population=collect_parent24(pins,reader)
    archive25_population,author25_population=collect_parent25(pins,reader)
    archive26_population,author26_population=collect_parent26(pins,reader)
    check_dependency_aliases()
    check_compiler_aliases()
    # Flattened selected_assets can also name a previously recorded tool alias.
    # Only aliases already bound by sealed dependency records may be normalized.
    for logical,target in {**DEPENDENCY_LOGICAL_ALIASES,**ADDITIONAL_COMPILER_ALIASES}.items():
        if logical in pins:
            pin=pins.pop(logical)
            add_pin(pins,target,pin['sha256'],pin.get('bytes'),pin.get('mode'))
    for path in pins:
        C.require(not Path(path).is_symlink(),'unrecorded_symlink_pin:'+path)
    total_bytes = 0
    for path, pin in sorted(pins.items()):
        actual = V.stable_sha(path)
        if path == REAL:
            C.require(pin == OLD_REAL and actual == NEW_REAL, 'exactly_declared_live_original_path_exception')
        else:
            C.require(all(actual[key] == value for key, value in pin.items()), 'sealed_raw_file_changed:' + path)
        total_bytes += actual['bytes']
    verify_resumed_delta()
    check_dependency_aliases()
    check_compiler_aliases()
    for path, entries in roster['directories'].items():
        if Path(path).is_relative_to(M):DEFERRED_MPC_DIRECTORIES[path]=entries;continue
        C.require(V.directory_entries(path) == entries, 'historical_population_changed:' + path)
    for root, expected in ((P, archives16), (A, archives17)):
        C.require(V.population(root) == expected, 'sealed_population_changed_during_read:' + str(root))
    for root in (H,):
        C.require(V.population(root) == archive18_population, 'D18_sealed_population_changed_during_stream')
    C.require(V.population(N18) == author18_population, 'N18_sealed_population_changed_during_stream')
    for root in (J,):C.require(V.population(root)==archive19_population,'D19_archive_population_changed_during_stream')
    C.require(V.population(N19)==author19_population,'N19_original_population_changed_during_stream')
    for root in (K,):C.require(V.population(root)==archive20_population,'D20_archive_population_changed')
    C.require(V.population(N20)==author20_population,'N20_population_changed')
    C.require(V.population(revision_root)==(revision_names,revision_dirs),'revision01_population_changed_during_stream')
    for root in (K21,):C.require(V.population(root)==archive21_population,'D21_population_changed')
    C.require(V.population(N21)==author21_population,'N21_population_changed')
    for root in (K22,):C.require(V.population(root)==archive22_population,'D22_archive_population_changed')
    C.require(V.population(N22)==author22_population,'N22_population_changed')
    C.require(V.population(K23)==archive23_population and V.population(N23)==author23_population,'D23_N23_local_population_changed')
    C.require(V.population(K24)==archive24_population and V.population(N24)==author24_population,'D24_N24_local_population_changed')
    C.require(V.population(K25)==archive25_population and V.population(N25)==author25_population,'D25_N25_local_population_changed')
    C.require(V.population(K26)==archive26_population and V.population(N26)==author26_population,'D26_N26_local_population_changed')
    C.require(reader.unchanged(), 'metadata_changed_during_stream_recheck')
    after = workspace()
    C.require(projection(before) == projection(after), 'old_workspace_changed_during_recheck')
    return {'schema': 'SchemeA-first-control-local-preservation/v1', 'passed': True,
            'parent_D22_archive_pairs':1885,'parent_N22_author_pairs':301,'parent_D22_RMSE_failure_preserved':True,'parent_D22_inventory_sha256':PIN22['archive_inventory_v1.json'],
            'parent_D21_archive_pairs':1676,'parent_N21r2_author_pairs':291,'parent_D21_first_revision_pairs':272,'parent_D21_failed_gates_preserved':True,'parent_D21_inventory_sha256':PIN21['archive_inventory_v1.json'],
            'parent_D20_archive_pairs':928,'parent_N20_author_pairs':291,
            'parent_D20_performance_failure_preserved':True,
            'parent_D20_inventory_sha256':PIN20['archive_inventory_v1.json'],
            'parent_D20_QA_sha256':PIN20['postrun/final_QA_v1.json'],
            'parent_D19_archive_pairs':853,
            'parent_D19_fixed_QA_files':850,
            'parent_N19_author_pairs':528,
            'parent_N19_original_and_snapshot_directories':33,
            'parent_D19_closed_twenty_second_component_records':4,
            'parent_D19_inventory_sha256':PIN19['archive_inventory_v1.json'],
            'parent_D19_QA_sha256':PIN19['postrun/final_QA_v1.json'],
            'parent_D19_final_protection_sha256':PIN19['preflight/workspace_final_v2.json'],
            'parent_D19_recorded_compiler_aliases_rechecked':len(ADDITIONAL_COMPILER_ALIASES),
            'parent_D19_recorded_compiler_alias_mapping':dict(sorted(ADDITIONAL_COMPILER_ALIASES.items())),
            'parent_D19_cases_requalified_for_new_research_or_endpoints':False,
            'parent_D18_archive_pairs': 2503,
            'parent_D18_fixed_QA_files': 2499,
            'parent_N18_author_pairs': 957,
            'parent_N18_original_directories': 103,
            'parent_N18_snapshot_directories': 95,
            'parent_N18_named_empty_build_directories': 8,
            'parent_D18_inventory_sha256': PIN18['archive_inventory_v1.json'],
            'parent_D18_QA_sha256': PIN18['postrun/final_QA_v1.json'],
            'parent_D18_final_protection_sha256': PIN18['preflight/workspace_final_v4.json'],
            'parent_D18_semantic_and_raw_proof_preserved': True,
            'recursive_parent_protect_called': False,
            'parent_D18_recorded_dependency_logical_aliases_rechecked': len(DEPENDENCY_LOGICAL_ALIASES),
            'parent_D18_recorded_dependency_alias_mapping': dict(sorted(DEPENDENCY_LOGICAL_ALIASES.items())),
            'initial_logical_alias_adapter_failure_retained': True,
            'parent_D18_component_results_requalified': False,
            'historical_flat_roster_sha256': anchor['roster_sha256'],
            'historical_raw_paths_checked': sum(not Path(p).is_relative_to(M) for p in roster['files']),
            'historical_raw_paths_equal_original_bytes': sum(not Path(p).is_relative_to(M) for p in roster['files']) - 1,
            'all_historical_original_path_bytes_unchanged': False,
            'raw_paths_equal_recorded_old_bytes': len(pins) - 1,
            'explicit_live_original_path_exceptions': [{'path': REAL, 'old_pin': OLD_REAL, 'current_pin': NEW_REAL,
                'diff_bytes': 515, 'diff_sha256': DELTA_DIFF_SHA, 'origin': 'unknown; present before resumed turn',
                'current_live_file_edited_or_restored_by_this_batch': False,
                'old_bytes_retained_in_original_Git_HEAD': True,
                'historical_recovery_snapshot_written_at_resume': True}],
            'resume_record_sha256': RESUMED_PINS,
            'historical_directory_populations_rechecked': sum(not Path(p).is_relative_to(M) for p in roster['directories']),
            'historical_capture_provenance_files_rechecked': len(anchor['provenance_file_sha256']),
            'historical_logical_aliases_rechecked': len(roster['legacy_symlink_logical_aliases']),
            'parent_C310_archive_pairs': 2435, 'parent_C310_fixed_QA_paths': 4303,
            'parent_C310_frozen_pairs': 2151, 'analysis_archive_pairs': 8,
            'analysis_inputs_reread': len(analysis_inputs), 'unique_raw_files_reread': len(pins),
            'logical_bytes_streamed': total_bytes, 'full_declared_current_byte_sha_recheck': False, 'full_local_current_byte_sha_recheck':True, 'MPC_mirror_current_bytes_verified':False, 'MPC_unavailable_expected_file_count':len(DEFERRED_MPC_PINS), 'local_D23_archive_files':413, 'local_N23_source_files':6, 'local_D24_archive_files':402, 'local_N24_source_files':6, 'D24_MPC_delivery_pending_preserved':True, 'local_D25_archive_files':420, 'local_N25_source_files':7, 'D25_MPC_delivery_pending_preserved':True, 'local_D26_archive_files':230, 'local_N26_source_files':8, 'D26_MPC_delivery_pending_preserved':True,
            'parent_D18_capture_scope': 'archived component records and exact bytes; no current endpoint or stage qualification inherited',
            'parent_inventory_sha256': PIN16['archive_inventory_v1.json'],
            'parent_QA_sha256': PIN16['postrun/final_QA_current.json'],
            'analysis_inventory_sha256': PIN17['archive_inventory_v1.json'],
            'archived_parent_proof_sha256': C.digest(V.canon(old_proof)),
            'historical_semantics_recomputed': False,
            'historical_semantic_capture_retained': True,
            'semantic_capture_boot_id': transition['original_capture_boot_id'],
            'current_asset_recheck_boot_id': before['boot_id'],
            'old_run_or_endpoint_qualification_transferred': False,
            'new_current_endpoints_verified': False,
            'workspace_status_excluded_untracked_roots_only': list(OLD_ROOTS + SEALED_LATER_ROOTS + PARENT_ROOTS + NEW_ROOTS),
            'sealed_later_roots_exact_population_required': list(SEALED_LATER_ROOTS + PARENT_ROOTS),
            'new_mutable_untracked_roots_only': list(NEW_ROOTS),
            'first_projection_failure_evidence_retained': True,
            'only_one_explicit_current_live_path_delta_permitted': True,
            'parent_proof_wrapper_shape_failure_evidence_retained': True,
            'initial_full_untracked_snapshot_unavailable': True,
            'initial_full_untracked_list_before_original_capture_retrospectively_proven': False,
            'HEAD': after['HEAD'], 'branch': after['branch'], 'boot_id': after['boot_id'],
            'business_tracked_count': 24, 'business_diff_bytes': 151961,
            'business_diff_sha256': after['business_diff_sha256'],
            'actual_Witness_normal_business': False, 'normal_business_contract_qualified': False,
            'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    C.require(args.output.is_absolute() and args.output.parent == D / 'preflight', 'new_preflight_output_only')
    started = time.monotonic()
    before = workspace()
    try:
        proof = protect()
        for key in list(proof):
            if key.endswith('archive_pairs'):proof[key.replace('archive_pairs','local_archive_files')]=proof.pop(key)
        proof['remote_mirror_expectations_preserved_not_read']=DEFERRED_MPC_PINS
        proof['remote_directory_expectations_not_read']=DEFERRED_MPC_DIRECTORIES
        result = {'passed': True, 'protection': proof, 'workspace_before': before,
                  'workspace_after': workspace(), 'endpoints_checked': False,
                  'stage_qualified': False, 'research_conclusion': False}
    except Exception as error:
        result = {'passed': False, 'error': repr(error), 'traceback': __import__('traceback').format_exc(), 'workspace_before': before,
                  'workspace_after': workspace(), 'stage_qualified': False, 'research_conclusion': False}
    result['elapsed_seconds'] = time.monotonic() - started
    V.write_new(args.output, result)
    print(json.dumps({'passed': result['passed'], 'error': result.get('error'),
                      'elapsed_seconds': result['elapsed_seconds'], 'output': str(args.output)}, sort_keys=True))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
