#!/usr/bin/env python3
"""Self-contained freeze for batch 103 (T2B-GEN Stage 1): bundle -> native
ELF -> registry -> registration. Component-level by design: no ROS context;
links only the installed mpc_core_lib math library. Registration precedes any
run; assertion lists and counts are fixed here (verified against smoke)."""
import hashlib, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / 'implementation/t2_author'
OUT = ROOT / 'evidence/freeze'
BUILD = ROOT / 'implementation/build_t2bgen'
TEST_SRC = TREE / 'observer/tests/test_scoped_epoch_v1.cpp'
WRAP_SRC = TREE / 'observer/src/shadow/scoped_epoch_v1.hpp'
EPOCH_SRC = TREE / 'observer/src/shadow/task_time_profile_v1.hpp'
USV_INC = '/home/trevor/USV/usv_mpc_ws/install/usv_mpc_cpp/include'
USV_LIB = '/home/trevor/USV/usv_mpc_ws/install/usv_mpc_cpp/lib'
BUDGET_S = 60

for d in (OUT, BUILD):
    d.mkdir(parents=True, exist_ok=True)

def pin(p):
    raw = Path(p).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

# 1. Bundle
files = {str(p.relative_to(TREE)): {'path': str(p), **pin(p)}
         for p in sorted(TREE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
bundle = OUT / 'source_bundle.json'
bundle.write_text(json.dumps({'schema': 'T2B-GEN-source-bundle/v1', 'scope': 'T2B_GEN_component_v1',
    'files': files, 'file_count': len(files), 'physical_production_release': False,
    'ros_context': False}, indent=2, sort_keys=True) + '\n')
bundle_sha = pin(bundle)['sha256']

# 2. Native build (frozen Epoch header + scoped wrapper + installed math lib)
binary = BUILD / 'test_scoped_epoch_v1'
cmd = ['g++', '-std=c++17', '-O2', '-DNDEBUG',
       '-I', str(TREE / 'observer/src/shadow'), '-I', str(TREE / 'common'),
       '-I', USV_INC, '-I', '/usr/include/eigen3',
       str(TEST_SRC), '-o', str(binary), '-L', USV_LIB, '-lmpc_core_lib', '-pthread']
build = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
if build.returncode != 0:
    print(build.stderr[-4000:]); raise SystemExit(f'native build failed rc={build.returncode}')
cc = subprocess.run(['g++', '--version'], capture_output=True, text=True).stdout.splitlines()[0]
binary_sha = pin(binary)['sha256']

# 3. Registry
registry = {'schema': 'T2B-GEN-native-registry/v1', 'scope': 'T2B_GEN_component_v1',
    'test_binary': str(binary), 'test_binary_sha256': binary_sha,
    'test_source': str(TEST_SRC), 'test_source_sha256': pin(TEST_SRC)['sha256'],
    'scoped_wrapper_source': str(WRAP_SRC), 'scoped_wrapper_source_sha256': pin(WRAP_SRC)['sha256'],
    'frozen_epoch_source': str(EPOCH_SRC), 'frozen_epoch_source_sha256': pin(EPOCH_SRC)['sha256'],
    'source_bundle': {'path': str(bundle), 'sha256': bundle_sha},
    'math_library': 'libmpc_core_lib.a from usv_mpc_ws install (headers+lib pinned by include/lib path)',
    'compiler': cc, 'ros_context': False, 'physical_production_release': False,
    'frozen_epoch_unchanged': pin(EPOCH_SRC)['sha256'] == pin(
        Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_g4c_fix_20261025_91/implementation/t2_author/observer/src/shadow/task_time_profile_v1.hpp'))['sha256']}
assert registry['frozen_epoch_unchanged'], 'frozen Epoch header must stay byte-identical'
(ROOT / 'implementation/t2bgen_registry.json').write_text(json.dumps(registry, indent=2, sort_keys=True) + '\n')

# 4. Registration (pre-run; assertion lists fixed from the compiled binary)
ASSERTS = {
 'T2B-GEN-E1': ['frozen_epoch_terminal_after_binding_change', 'gen1_first_proposal_valid',
   'gen1_first_commit', 'gen1_second_proposal_successive', 'gen1_second_commit',
   'gen1_no_generation_events', 'terminal_after_binding_change_quiesce_cleared',
   'gen2_first_proposal_valid_after_scoped_open', 'gen2_opened_single_event',
   'gen2_proposal_anchor_binding_B', 'g5_cross_generation_job_monotonicity_enforced',
   'gen2_first_commit_job5', 'gen2_anchor_after_commit',
   'ledger_generation1_record_complete', 'gen2_active_not_terminal'],
 'T2B-GEN-E2': ['retired_binding_proposal_rejected', 'no_extra_generation_or_ledger_growth',
   'anchor_never_rolled_back', 'current_generation_still_advances'],
 'T2B-GEN-E3': ['same_binding_republish_is_successive', 'same_binding_never_opens_generation',
   'successive_commit_normal'],
 'T2B-GEN-E4': ['domain_rejected_with_frozen_reason', 'no_open_completed_on_domain_failure',
   'terminal_generation_unchanged_after_domain_failure'],
 'T2B-GEN-E5': ['own_binding_reblocked_by_g3', 'no_open_for_own_binding', 'old_anchor_kept_terminal'],
 'T2B-GEN-E6': ['g2_blocks_without_quiesce', 'no_open_before_quiesce',
   'quiesce_marker_authorizes_open', 'gen2_commit_after_g2_satisfied'],
}
DESIGN_DOCS = {
 'E1': 'positive control: gen2 scoped open + ledger + G5',
 'E2': 'revival negative: retired binding never re-anchors',
 'E3': 'same-content republish never opens a generation',
 'E4': 'G4: frozen static domain rejects 101-point binding, no open',
 'E5': 'G3: own binding re-blocked, old anchor kept terminal',
 'E6': 'G2: no quiesce -> no submission; marker authorizes open',
}
cases = []
for cid, names in ASSERTS.items():
    cases.append({'case_id': cid, 'family': 'T2B_GEN_component', 'design': DESIGN_DOCS[cid[-2:]],
        'harness': str(TEST_SRC), 'budget_seconds': BUDGET_S, 'assertions': names,
        'result_schema': 'T2B-GEN-component/v1',
        'qualification_flags': {'ROS_context_created': False, 'stage_qualified': False,
                                'execute_qualified': False, 'research_conclusion': False}})
registration = {
    'schema': 'T3-case-registration/v1', 'batch_registered': 103, 'family_registered': 'T2B-GEN-Stage1',
    'obligation_binding': {'review': 'R74-07 (batch 74 independent review)',
        'design': 'experiments/scheme_A_M4_t2b_epoch_design_20261025_102/documents/方案A_第102批_T2B新代际scoped_Epoch生命周期设计_2026-10-25.md',
        'status_source': 'experiments/scheme_A_M4_g3_t2b_20261025_86/documents/方案A_第86批_G3_T2B回顾性复核_2026-10-25.md (新代际正控未覆盖)'},
    'tree_base': {'source': str(TREE), 'bundle_sha256': bundle_sha, 'binary_sha256': binary_sha},
    'fixed_parameters': {'speed': .05, 'points': 201, 'ts_ns': [1000000000, 2000000000, 3000000000],
        'jobs': [1, 2, 5], 'max_generations_cap': 8,
        'policy': 'scoped_generation_first_target_task_time_profile_v2',
        'frozen_epoch_policy': 'first_successful_job_submit_completion_target_sim_v1'},
    'cases': cases,
    'governance': {'pre_registration_required': True, 'single_finite_execution': True,
        'auto_retry': 0, 'failure_originals_preserved': True,
        'component_not_owned': 'R74-07: component verification does not borrow owned qualification'},
    'not_claimed': ['owned qualification (Stage 2 is batch 104)', 'ordinary-scope behavior change',
                    'any stage qualification or research conclusion'],
}
(ROOT / 'implementation/T2BGEN_registration.json').write_text(json.dumps(registration, indent=2, sort_keys=True) + '\n')
print(f'bundle={bundle_sha[:16]}... binary={binary_sha[:16]}... files={len(files)} cc={cc}')
print('registry + registration written (pre-run); frozen Epoch header byte-identical')
