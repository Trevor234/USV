#!/usr/bin/env python3
"""E00 (batch 126): freeze inputs, component lineage and execution constraints.

Read-only over every original batch. Writes only inside this package.
Registers:
  evidence/inputs/input_manifest_v1.json      full source pin population
  evidence/inputs/component_lineage_v1.json   derived-from table, one lineage per component
  evidence/inputs/git_porcelain_v1.txt        exact workspace porcelain
  evidence/inputs/workspace_files_v1.json     ordinary uncommitted file pins
  evidence/inputs/contract_pin_v1.json        v3 budget/dimension pin
  evidence/inputs/allowed_changes.json        per-step write whitelist
  evidence/inputs/expected_cases.json         locked case population + expected outcome
  postrun/step_status_v1.json                 all steps NOT_STARTED
No file outside ROOT is modified. Fail-closed: any missing input aborts.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = Path('/home/trevor/USV/.sgh-research/experiments')
OUT = ROOT / 'evidence/inputs'
WORKSPACE = Path('/home/trevor/USV')
CONTRACT = EXP / 'scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'
CONTRACT_SHA = '19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a'

# ---------------------------------------------------------------- batch aliases
BATCHES = {
    'B99':  'scheme_A_M4_t3q_impl_20261025_99',
    'B100': 'scheme_A_M4_t3c_impl_20261025_100',
    'B101': 'scheme_A_M4_t3_audit_20261025_101',
    'B103': 'scheme_A_M4_t2b_gen_impl_20261025_103',
    'B104': 'scheme_A_M4_t2bgen_owned_20261025_104',
    'B105': 'scheme_A_M4_t2bgen_audit_20261025_105',
    'B108': 'scheme_A_M4_n4_f6_impl_20261025_108',
    'B112': 'scheme_A_M4_t2a_rnw2_impl_20261025_112',
    'B117': 'scheme_A_M4_rnw_s1_pure_20261025_117',
    'B118': 'scheme_A_M4_rnw_s2_b2_20261025_118',
    'B119': 'scheme_A_M4_rnw_s4_owned_20261025_119',
    'B124': 'scheme_A_M4_session_code_review_20261026_124',
    'PLAN125': 'scheme_A_M4_controlled_plan_20261026_125',
}


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def fail(msg):
    print('E00 FAIL: ' + msg, file=sys.stderr)
    raise SystemExit(2)


OUT.mkdir(parents=True, exist_ok=True)

# Absolute paths must be resolved before use; never take a file via an elided path.
aliases = {}
for alias, name in BATCHES.items():
    p = (EXP / name).resolve()
    if not p.is_dir():
        fail(f'{alias} missing: {p}')
    aliases[alias] = str(p)

# ------------------------------------------------- contract pin (full bytes + sha)
if not CONTRACT.is_file():
    fail(f'contract missing: {CONTRACT}')
cpin = pin(CONTRACT)
if cpin['sha256'] != CONTRACT_SHA:
    fail(f'contract sha drift: {cpin["sha256"]} != {CONTRACT_SHA}')
contract = json.loads(CONTRACT.read_bytes())
BUDGET_KEYS = ['T_ns', 'deadline_ns', 'hold_ns', 'active_watchdog_ns',
               'worker_capability_receipt_timeout_ns', 'publish_budget_ns',
               'publish_gap_ns', 'tick_jitter_ns', 'shutdown_grace_ns', 'worker_grace_ns']
budgets = {k: contract[k] for k in BUDGET_KEYS}
EXPECTED_BUDGETS = {
    'T_ns': 200000000, 'deadline_ns': 150000000, 'hold_ns': 600000000,
    'active_watchdog_ns': 1000000000, 'worker_capability_receipt_timeout_ns': 600000000,
    'publish_budget_ns': 5000000, 'publish_gap_ns': 240000000,
    'tick_jitter_ns': 20000000, 'shutdown_grace_ns': 2500000000, 'worker_grace_ns': 500000000,
}
if budgets != EXPECTED_BUDGETS:
    fail(f'budget drift: {budgets}')
(OUT / 'contract_pin_v1.json').write_text(json.dumps({
    'schema': 'plan126-contract-pin-v1',
    'path': str(CONTRACT.resolve()),
    'expected_sha256': CONTRACT_SHA,
    'observed_sha256': cpin['sha256'],
    'bytes': cpin['bytes'],
    'bytes_match': True,
    'budgets_ns': budgets,
    'budgets_match_plan': True,
    'model_dimensions': {'NX': 8, 'NU': 2, 'N': 20, 'NP': 6, 'NPG': 30},
    'finite_F6_existing_tolerance': 1e-8,
    'other_profiles_keep_own_pins': True,
}, indent=2, sort_keys=True) + '\n')

print(f'contract OK {cpin["sha256"][:16]}…')

# ------------------------------------------------------- component lineage table
# One lineage per component. B119 is the single main author tree; the Q2 test,
# the model transaction layer and the two auditors each have their own origin.
LINEAGE = {
    'author_tree': {
        'source': str(EXP / BATCHES['B119'] / 'implementation/t2_author'),
        'dest': str(ROOT / 'implementation/author'),
        'reason': 'B119 is the only main author tree; Q2 diag sink, Worker/Fixture, '
                  'scoped Epoch wrapper and Regulator wiring all live here.',
    },
    'setup_env': {
        'source': str(EXP / BATCHES['B119'] / 'implementation/setup_env.sh'),
        'dest': str(ROOT / 'implementation/setup_env.sh'),
        'reason': 'batch-local environment wrapper, unchanged.',
    },
    'q2_test': {
        'source': str(EXP / BATCHES['B99'] / 'implementation/t2_author/observer/tests/test_t3_queue_pressure.cpp'),
        'dest': str(ROOT / 'implementation/tests/test_t3_queue_pressure.cpp'),
        'reason': 'the Q2 harness exists only in B99; B119 tree has no such file.',
    },
    'rnw_audit': {
        'source': str(EXP / BATCHES['B117'] / 'implementation/rnw_audit_v1.py'),
        'dest': str(ROOT / 'implementation/audit/rnw_audit_v1.py'),
        'reason': 'F124-02 names B119, but 117 and 119 copies are byte-identical; '
                  '117 is the declared origin of the pure audit.',
    },
    'rnw_admission': {
        'source': str(EXP / BATCHES['B117'] / 'implementation/rnw_admission_v2.py'),
        'dest': str(ROOT / 'implementation/audit/rnw_admission_v2.py'),
        'reason': 'B117 holds the hardened rule set; B119 duplicates only a weaker '
                  'variant inside t2b_gen_admission.py (F124-03).',
    },
    't2bgen_audit': {
        'source': str(EXP / BATCHES['B105'] / 'implementation/audit_t2bgen.py'),
        'dest': str(ROOT / 'implementation/audit/audit_t2bgen.py'),
        'reason': 'F124-04 target; B105 is the only copy.',
    },
    's1_pure_test': {
        'source': str(EXP / BATCHES['B117'] / 'implementation/test_s1_pure.py'),
        'dest': str(ROOT / 'implementation/tests/test_s1_pure.py'),
        'reason': 'reference style for private-fixture pure matrices.',
    },
    'model_transaction': {
        'source': str(EXP / BATCHES['B108'] / 'implementation/model_transaction_v1.hpp'),
        'dest': str(ROOT / 'implementation/standalone/model/model_transaction_v1.hpp'),
        'reason': 'F124-06/F124-07 target; B108 is the only copy.',
    },
    'model_harness': {
        'source': str(EXP / BATCHES['B108'] / 'implementation/test_f6_model_transaction.cpp'),
        'dest': str(ROOT / 'implementation/standalone/model/test_f6_model_transaction.cpp'),
        'reason': 'F6 6-case harness, derived so the original stays frozen.',
    },
}

# The identical-header claim must be proven, not assumed.
IDENTICAL_HEADERS = ['observer/src/shadow/p1_diag_sink.hpp', 'observer/src/shadow/p1_witness.hpp']
identical = {}
for rel in IDENTICAL_HEADERS:
    a = EXP / BATCHES['B99'] / 'implementation/t2_author' / rel
    b = EXP / BATCHES['B119'] / 'implementation/t2_author' / rel
    if not a.is_file() or not b.is_file():
        fail(f'header missing for equivalence check: {rel}')
    pa, pb = pin(a), pin(b)
    identical[rel] = {'B99': pa, 'B119': pb, 'byte_identical': pa == pb,
                      'in_derived_author_tree': pin(ROOT / 'implementation/author' / rel)}
    if pa != pb:
        fail(f'header differs between B99 and B119, Q2 test cannot be moved as-is: {rel}')

lineage = {'schema': 'plan126-component-lineage-v1', 'components': LINEAGE,
           'identical_headers_proof': identical}
(OUT / 'component_lineage_v1.json').write_text(json.dumps(lineage, indent=2, sort_keys=True) + '\n')
print('component lineage OK')

# ------------------------------------------------------- input pin population
# Every file the plan reads as evidence, pinned by content.
PIN_TARGETS = {
    'B99': [
        'implementation/t2_author/observer/tests/test_t3_queue_pressure.cpp',
        'implementation/t2_author/observer/src/shadow/p1_diag_sink.hpp',
        'implementation/t2_author/observer/src/shadow/p1_witness.hpp',
        'implementation/t3q_registry.json',
        'implementation/T3Q_registration.json',
        'implementation/runs/T3-Q1d/q1d.jsonl', 'implementation/runs/T3-Q1d/result.json',
        'implementation/runs/T3-Q2/q2.jsonl', 'implementation/runs/T3-Q2/result.json',
        'implementation/runs/T3-Q2_r2/q2.jsonl', 'implementation/runs/T3-Q2_r2/result.json',
        'implementation/runs/T3-Q3_r2/result.json', 'implementation/runs/T3-Q1r_r2/result.json',
        'implementation/runs/T3-Q4/result.json',
    ],
    'B100': [
        'implementation/t2_author/fixture/synthetic_source_m4_t3_survivor.cpp',
        'implementation/runs/T3C_C12/driver_result.json',
        'implementation/runs/T3C_C3/driver_result.json',
    ],
    'B101': ['implementation/audit_t3.py', 'evidence/audit_t3_v1.json'],
    'B103': [
        'implementation/t2_author/observer/src/shadow/scoped_epoch_v1.hpp',
        'implementation/t2_author/observer/tests/test_scoped_epoch_v1.cpp',
        'implementation/t2bgen_registry.json', 'implementation/T2BGEN_registration.json',
    ] + [f'implementation/runs/T2B-GEN-E{i}/result.json' for i in range(1, 7)],
    'B104': [
        'implementation/t2_author/t2b_gen_admission.py',
        'implementation/runs/T2BGEN_POS/regulator/source.jsonl',
        'implementation/runs/T2BGEN_POS/driver_result.json',
        'implementation/runs/T2BGEN_NEG/regulator/source.jsonl',
        'implementation/runs/T2BGEN_NEG/driver_result.json',
        'implementation/t2bgen_registry.json',
    ],
    'B105': ['implementation/audit_t2bgen.py', 'evidence/audit_t2bgen_v1.json'],
    'B108': [
        'implementation/model_transaction_v1.hpp',
        'implementation/test_f6_model_transaction.cpp',
        'implementation/f6_registry.json', 'implementation/F6_registration.json',
    ] + [f'implementation/runs/F6-{i}/result.json' for i in range(1, 7)],
    'B112': [
        'implementation/t2_author/t2b_gen_admission.py',
        'implementation/runs/T2A_RNW2/regulator/source.jsonl',
        'implementation/runs/T2A_RNW2/driver_result.json',
        'implementation/runs/T2A_RNW2_attempt1/regulator/source.jsonl',
        'implementation/runs/T2A_RNW2_attempt1/driver_result.json',
    ],
    'B117': [
        'implementation/rnw_audit_v1.py', 'implementation/rnw_admission_v2.py',
        'implementation/test_s1_pure.py', 'postrun/s1_acceptance_v1.json',
    ],
    'B118': [
        'implementation/t2_author/fixture/resume_stamp_mapping_v1.hpp',
        'implementation/t2_author/tests/test_resume_mapping_v1.cpp',
        'implementation/runs/S2_B2_MAPPING/result.json',
        'implementation/S2_registration.json', 'implementation/s2_registry.json',
    ],
    'B119': [
        'implementation/rnw_audit_v1.py', 'implementation/rnw_admission_v2.py',
        'implementation/t2_author/t2b_gen_admission.py',
        'implementation/t2_author/t2b_gen_driver_v1.py',
        'implementation/t2_author/fixture/resume_stamp_mapping_v1.hpp',
        'implementation/t2_author/observer/src/shadow/scoped_epoch_v1.hpp',
        'implementation/t2_author/observer/src/shadow/task_time_profile_v1.hpp',
        'implementation/t2_author/observer/src/shadow/regulator_owned_execute.cpp',
        'implementation/runs/T2A_RNW3/regulator/source.jsonl',
        'implementation/runs/T2A_RNW3/driver_result.json',
        'implementation/s4_registry.json', 'implementation/T2A_RNW3_registration.json',
        'postrun/s4_verdict_v1.json',
    ],
    'B124': [
        'postrun/review_findings_v1.json', 'postrun/innovation_register_revisions_v1.json',
        'evidence/positive_progress_v1.json', 'evidence/final_verification_v1.json',
        'evidence/inputs_before_v1.json', 'evidence/replay01/t3/asan_probe.json',
        'evidence/replay01/t3/q2_actual_id_probe.json', 'evidence/replay01/t3/sticky_probe.json',
        'evidence/replay01/rnw/audit_probe_results.json',
        'evidence/replay01/rnw/logical_time_probe.json',
        'evidence/replay01/rnw/admission_probe_results.json',
        'evidence/replay01/rnw/mapping_overflow.stderr',
        'evidence/replay01/rnw/mapping_cap.stdout',
        'evidence/replay01/rnw/receive_skew.stdout',
        'evidence/replay01/epoch_model/epoch_result.json',
        'evidence/replay01/epoch_model/model_result.json',
        'evidence/replay01/epoch_model/audit_false_pass_result.json',
        'evidence/replay01/epoch_model/mutation_ledger_result.json',
    ],
    'PLAN125': [
        'CURRENT.md',
        'documents/方案A_第125批_严格执行顺序与逐步验收计划_2026-10-26.md',
        'postrun/execution_plan_v1.json', 'postrun/execution_checklist_v1.tsv',
        'postrun/next_step_v1.json', 'evidence/final_verification_v1.json',
        'evidence/planning_inputs_v1.json',
    ],
}

manifest, missing = {}, []
for alias, rels in PIN_TARGETS.items():
    base = EXP / BATCHES[alias]
    for rel in rels:
        p = base / rel
        if not p.is_file():
            missing.append(str(p))
            continue
        manifest[str(p.resolve())] = pin(p)
if missing:
    fail('missing pinned inputs:\n  ' + '\n  '.join(missing))

# Innovation register is a project-level file read (and later the only write exception).
register = Path('/home/trevor/USV/.sgh-research/research-innovations.md')
if not register.is_file():
    fail(f'innovation register missing: {register}')
manifest[str(register.resolve())] = pin(register)

(OUT / 'input_manifest_v1.json').write_text(json.dumps({
    'schema': 'plan126-input-manifest-v1',
    'batch_aliases': aliases,
    'content_from': 'direct reads of primary batch sources',
    'files': manifest,
    'count': len(manifest),
    'scope': 'source files, registrations/registries, run evidence quoted by the plan, '
             'the three replay parts, the plan batch and the innovation register; '
             'not all intermediate builds and not dirty submodule contents.',
}, indent=2, sort_keys=True) + '\n')
print(f'input manifest OK: {len(manifest)} files')

# --------------------------------------------------------- workspace state
porcelain = subprocess.run(['git', '-C', str(WORKSPACE), 'status', '--porcelain'],
                           capture_output=True, text=True, check=True).stdout
(OUT / 'git_porcelain_v1.txt').write_text(porcelain)

ws_files, ws_missing = {}, []
for line in porcelain.splitlines():
    if len(line) < 4:
        continue
    status, rel = line[:2], line[3:]
    p = WORKSPACE / rel
    if not p.is_file():
        ws_missing.append(rel)          # submodule / directory entries
        continue
    ws_files[rel] = {'status': status, **pin(p)}

submodule = subprocess.run(['git', '-C', str(WORKSPACE), 'status', '--porcelain'],
                           capture_output=True, text=True, check=True).stdout
ws = subprocess.run(['git', '-C', str(WORKSPACE), 'submodule', 'status'],
                    capture_output=True, text=True).stdout

(OUT / 'workspace_files_v1.json').write_text(json.dumps({
    'schema': 'plan126-workspace-files-v1',
    'git_porcelain': porcelain,
    'porcelain_line_count': len([l for l in porcelain.splitlines() if l.strip()]),
    'ordinary_file_count': len(ws_files),
    'files': ws_files,
    'non_file_entries': ws_missing,
    'submodules': submodule,
    'excluded_from_pin': 'dirty submodule working-tree contents are recorded by state only '
                         'and are NOT claimed to be content-frozen',
}, indent=2, sort_keys=True) + '\n')
print(f'workspace files OK: {len(ws_files)} ordinary + {len(ws_missing)} non-file entries')

# ------------------------------------------------------------ write whitelist
WHITELIST = {
    'E00': ['evidence/inputs/', 'evidence/E00/', 'postrun/', 'CURRENT.md', 'implementation/'],
    'E01': ['implementation/tests/test_t3_queue_pressure.cpp', 'implementation/tests/',
            'evidence/E01/', 'postrun/', 'CURRENT.md'],
    'E02': ['implementation/audit/rnw_audit_v1.py', 'implementation/audit/', 'implementation/tests/',
            'evidence/E02/', 'postrun/', 'CURRENT.md'],
    'E03': ['implementation/audit/rnw_admission_v2.py', 'implementation/audit/',
            'implementation/author/t2b_gen_admission.py', 'implementation/tests/',
            'evidence/E03/', 'postrun/', 'CURRENT.md'],
    'E04': ['implementation/audit/audit_t2bgen.py', 'implementation/audit/', 'implementation/tests/',
            'evidence/E04/', 'postrun/', 'CURRENT.md'],
    'E05': ['implementation/author/observer/src/shadow/scoped_epoch_v1.hpp',
            'implementation/author/observer/tests/', 'implementation/author/observer/src/shadow/regulator_owned_execute.cpp',
            'implementation/tests/', 'evidence/E05/', 'postrun/', 'CURRENT.md'],
    'E06': ['implementation/standalone/model/', 'implementation/tests/', 'evidence/E06/',
            'postrun/', 'CURRENT.md'],
    'E07': ['implementation/author/fixture/resume_stamp_mapping_v1.hpp',
            'implementation/author/fixture/', 'implementation/tests/', 'evidence/E07/',
            'postrun/', 'CURRENT.md'],
    'E08': ['implementation/audit/', 'implementation/tests/', 'documents/', 'evidence/E08/',
            'postrun/', 'CURRENT.md'],
    'E09': ['implementation/tests/', 'evidence/E09/', 'postrun/', 'CURRENT.md'],
    'E10': ['documents/', 'evidence/E10/', 'postrun/', 'CURRENT.md',
            '/home/trevor/USV/.sgh-research/research-innovations.md'],
    'E11': ['documents/', 'evidence/E11/', 'postrun/', 'CURRENT.md'],
    'E12': ['documents/', 'evidence/E12/', 'postrun/', 'CURRENT.md'],
}
FORBIDDEN = [
    'usv_mpc_ws/', 'ardurover-argus/', '.git/',
    'scheme_A_M4_t3q_impl_20261025_99/', 'scheme_A_M4_t3c_impl_20261025_100/',
    'scheme_A_M4_t3_audit_20261025_101/', 'scheme_A_M4_t2b_gen_impl_20261025_103/',
    'scheme_A_M4_t2bgen_owned_20261025_104/', 'scheme_A_M4_t2bgen_audit_20261025_105/',
    'scheme_A_M4_n4_f6_impl_20261025_108/', 'scheme_A_M4_t2a_rnw2_impl_20261025_112/',
    'scheme_A_M4_rnw_s1_pure_20261025_117/', 'scheme_A_M4_rnw_s2_b2_20261025_118/',
    'scheme_A_M4_rnw_s4_owned_20261025_119/', 'scheme_A_M4_session_code_review_20261026_124/',
    'scheme_A_M4_controlled_plan_20261026_125/',
]
(OUT / 'allowed_changes.json').write_text(json.dumps({
    'schema': 'plan126-allowed-changes-v1',
    'root': str(ROOT),
    'per_step': WHITELIST,
    'forbidden_prefixes': FORBIDDEN,
    'rule': 'relative paths resolve under root unless absolute; any write outside the '
            'current step whitelist is FAIL_STOP. Frozen originals and production trees '
            'are read-only for the whole batch.',
    'only_project_level_write_exception': {
        'step': 'E10',
        'path': '/home/trevor/USV/.sgh-research/research-innovations.md',
        'mode': 'append-only corrective review, preimage + sha + diff kept',
        'requires_user_confirmation': True,
    },
}, indent=2, sort_keys=True) + '\n')
print('allowed changes OK')

# ---------------------------------------------------------- expected cases
def case(cid, kind, expectation, reason):
    return {'case_id': cid, 'kind': kind, 'expected': expectation, 'reason': reason}

EXPECTED = {
    'E01': [
        case('Q2V-LIFETIME', 'positive', 'asan_clean', 'fixed capture has no stack-use-after-scope'),
        case('Q2V-IDENTITY', 'positive', 'all_ids_unique', 'per-producer monotonic local sequence'),
        case('Q2V-BALANCE', 'positive', 'offered_eq_accepted_union_rejected', 'exclusive complete partition'),
        case('Q2V-MULTISET', 'positive', 'publish_and_file_eq_accepted_multiset', 'multiset, not count'),
        case('Q2V-RAW-OLD', 'negative', 'duplicates_detected=350', 'old T3-Q2_r2 has 350 duplicate ids'),
        case('Q2V-RAW-OLD2', 'negative', 'duplicates_detected=303', 'old T3-Q2 has 303 duplicate ids'),
        case('Q2V-MUT-CAPTURE', 'mutation', 'asan_reports_uaf', 'restore reference capture; must be caught by ASAN'),
        case('Q2V-REGRESSION', 'positive', 'q1d_accepted_eq_capacity_plus_one', 'Q1d property preserved (513)'),
    ],
    'E02': [
        case('RNWV-POS-119', 'positive', 'r4_observed_true_run_accepted_true', 'RNW3 Job7/seq18 chain'),
        case('RNWV-OLD-112', 'negative', 'r4_not_covered_no_scoped_open', 'no generation open in either run'),
        case('RNWV-MISSING-CLOSE', 'negative', 'run_accepted_false_r4_observed_true', 'close evidence missing'),
        case('RNWV-MISSING-CLOCK', 'negative', 'run_accepted_false', 'clock evidence missing'),
        case('RNWV-MISSING-WORKER', 'negative', 'run_accepted_false', 'worker evidence missing'),
        case('RNWV-IDENTITY-FOREIGN', 'negative', 'named_reject', 'foreign run echo'),
        case('RNWV-IDENTITY-SCHEDULE', 'negative', 'named_reject', 'old schedule echo'),
        case('RNWV-IDENTITY-GEN', 'negative', 'named_reject', 'wrong generation binding'),
        case('RNWV-IDENTITY-DUP', 'negative', 'named_reject', 'duplicate/mixed same-id events'),
        case('RNWV-TIME-READY', 'negative', 'named_reject', 'ready before submit'),
        case('RNWV-TIME-ACTIVATION', 'negative', 'named_reject', 'activation before ready'),
        case('RNWV-TIME-API', 'negative', 'named_reject', 'API left_start before activation'),
        case('RNWV-FACT-REJECTED', 'negative', 'r4_false', 'rejected candidate'),
        case('RNWV-FACT-FALLBACK', 'negative', 'r4_false', 'fallback only'),
        case('RNWV-FACT-PARTIAL', 'negative', 'r4_false', 'partial API pair'),
        case('RNWV-FACT-NOAPPLIED', 'negative', 'r4_false', 'missing Applied'),
        case('RNWV-LEGAL-EPOCH0', 'positive', 'no_false_reject', 'clock_epoch 0 with schedule change is legal'),
    ],
    'E03': [
        case('ADM-LEGAL', 'positive', 'admitted', 'real registered table'),
        case('ADM-CLAUSE-FALSE', 'negative', 'named_reject:clause_value', 'all-false clauses'),
        case('ADM-MISSING-HOLD', 'negative', 'named_reject:missing_hold', 'hold absent'),
        case('ADM-RESUME-BEFORE-HOLD', 'negative', 'named_reject:resume_before_hold', 'order violated'),
        case('ADM-DUPLICATE', 'negative', 'named_reject:duplicate_action', 'duplicate action'),
        case('ADM-UNKNOWN-ACTION', 'negative', 'named_reject:unregistered_action', 'unknown action'),
        case('ADM-IDENTITY', 'negative', 'named_reject:table_identity_binding', 'run/contract identity mismatch'),
        case('ADM-SPAWN-COUNT', 'negative', 'spawn_count_zero', 'no spawn before admission'),
        case('ADM-FREEZE-EQ-DRIVER', 'positive', 'identical_verdict', 'single rule source'),
    ],
    'E04': [
        case('A105V-FALSE-SOURCE', 'negative', 'clause_rejected', 'boolean must not land in obligation'),
        case('A105V-SAME-BINDING', 'negative', 'clause_rejected', 'generation constants cannot fake a difference'),
        case('A105V-POS-TASK2-6', 'positive', 'different_binding_detected', '104 POS really changes'),
        case('A105V-NEG-NO-GEN', 'positive', 'no_generation_open_detected', 'NEG has no generation switch'),
        case('A105V-STRICT-BOOL', 'negative', 'reject_non_bool', 'keyword-only strict bool'),
        case('A105V-BUNDLE-ITEMS', 'negative', 'reject_when_bundle_item_changed', 'per-file recompute, not bundle sha'),
    ],
    'E05': [
        case('EPV-E1', 'positive', 'existing_semantics_preserved', 'original 6 component cases'),
        case('EPV-E2', 'positive', 'existing_semantics_preserved', ''),
        case('EPV-E3', 'positive', 'existing_semantics_preserved', ''),
        case('EPV-E4', 'positive', 'existing_semantics_preserved', ''),
        case('EPV-E5', 'positive', 'existing_semantics_preserved', ''),
        case('EPV-E6', 'positive', 'existing_semantics_preserved', ''),
        case('EPV-REPLAY-A', 'negative', 'reject_stale_generation', 'retired A commit into uncommitted B'),
        case('EPV-DUP-COMMIT', 'negative', 'reject_consumed_proposal', 'same proposal, larger job id'),
        case('EPV-RETIRED-BINDING', 'negative', 'reject_by_retired_ledger', 'full old A binding after B'),
        case('EPV-NO-QUIESCE', 'negative', 'reject_scoped_open_requires_quiesce', 'existing guard kept'),
        case('EPV-SAME-BINDING', 'negative', 'reject_scoped_open_binding_not_new', 'existing guard kept'),
        case('EPV-DOMAIN-FAIL', 'negative', 'reject_static_domain', 'existing guard kept'),
        case('EPV-GEN-CAP', 'negative', 'reject_scoped_open_generation_cap', 'existing guard kept'),
        case('EPV-LEGAL-NEW-SCHEDULE', 'positive', 'opened_and_job_monotonic', 'same fingerprints, new schedule'),
        case('EPV-MUT-TOKEN', 'mutation', 'caught_by_named_assertion', 'delete token gate'),
        case('EPV-MUT-LEDGER', 'mutation', 'caught_by_named_assertion', 'delete ledger loop'),
    ],
    'E06': [
        case('F6V-01-UNCOMMITTED', 'negative', 'solve_rejected_c_solve_zero', 'registered but never committed'),
        case('F6V-02-GEN-ZERO', 'negative', 'register_rejected', 'generation 0 refused'),
        case('F6V-03-STALE', 'negative', 'solve_rejected_c_solve_zero', 'stale stamp'),
        case('F6V-04-NAN', 'negative', 'register_rejected', 'non-finite p_global'),
        case('F6V-05-IMMUTABLE', 'negative', 'register_rejected', 'same generation rewritten'),
        case('F6V-06-PREPARING', 'negative', 'solve_rejected_c_solve_zero', 'solve during prepare'),
        case('F6V-07-LEGAL', 'positive', 'matches_installed_lib_within_1e-8', 'M0/M1 numeric parity'),
        case('F6V-08-WRONG-THREAD', 'negative', 'rejected_before_state_touch', 'owner thread contract'),
        case('F6V-09-FAULTED-SET', 'negative', 'faulted_then_all_rejected', 'adapter setter failure'),
        case('F6V-10-FAULTED-RESET', 'negative', 'faulted_then_all_rejected', 'adapter reset failure'),
        case('F6V-11-ABORT-PREPARED', 'positive', 'back_to_previous_state', 'cancel before capsule touch'),
    ],
    'E07': [
        case('B2V-01-LEGAL', 'positive', 'legal_mapping_preserved', 'existing legal pairing'),
        case('B2V-16-NO-HOLD', 'positive', 'bitwise_identical', 'no-hold path unchanged'),
        case('B2V-17a-MAX', 'negative', 'named_reject_int64', 'published_stamp near INT64_MAX'),
        case('B2V-17b-MIN', 'negative', 'named_reject_int64', 'elapsed subtraction underflow'),
        case('B2V-17c-CAP-EDGE', 'positive', 'capped_true', 'cap boundary explicit'),
        case('B2V-17d-PLUS', 'negative', 'named_reject_int64', 'addition overflow'),
        case('B2V-18-UBSAN', 'positive', 'no_runtime_error', 'UBSan clean on the fixed domain'),
        case('B2V-19-CAP', 'positive', 'cap_applied_true', 'cap flag explicit'),
        case('B2V-20a-LONG-HOLD', 'limitation', 'backstep_recorded_1100000000', 'scope limit evidence kept'),
        case('B2V-20b-RX-SKEW', 'limitation', 'backstep_recorded_4000000', 'scope limit evidence kept'),
    ],
    'E08': [
        case('T3V-STICKY-01', 'positive', 'failed_sticky_add_after_drain_succeeds', 'qualification sticky only'),
        case('T3V-STICKY-02', 'positive', 'normal_source_complete_false', 'counts reconcile'),
        case('T3V-SURVIVOR-DOC', 'document', 'claim_matches_code', 'main-loop fork, fd3..255, fork unchecked'),
        case('T3V-C12-REJUDGE', 'rejudge', 'limited_facts_preserved', 'C12 failure not rewritten'),
        case('T3V-A101-PROVENANCE', 'document', 'recompute_vs_harness_split', 'no overclaim'),
    ],
    'E09': [
        case('REG-Q', 'regression', 'all_expected', 'Q family on fixed tree'),
        case('REG-RNW', 'regression', 'all_expected', 'audit + admission'),
        case('REG-A105', 'regression', 'all_expected', '105 audit re-judge'),
        case('REG-EPOCH', 'regression', 'all_expected', 'Epoch component'),
        case('REG-F6', 'regression', 'all_expected', 'model transaction'),
        case('REG-B2', 'regression', 'all_expected', 'B2 helper'),
        case('REG-HISTORY', 'rejudge', 'all_expected', '104 POS/NEG, 119 RNW3, 112 failures'),
    ],
}

(OUT / 'expected_cases.json').write_text(json.dumps({
    'schema': 'plan126-expected-cases-v1',
    'locked_at': 'E00 before any run',
    'policy': 'case ids and outcomes are fixed before execution; after a run a required case '
              'may not be re-labelled out of scope, and assertion-list changes require a new case id.',
    'qualification_flags_for_every_result': {
        'ROS_context_created': False, 'stage_qualified': False,
        'execute_qualified': False, 'research_conclusion': False,
    },
    'cases': EXPECTED,
    'count': sum(len(v) for v in EXPECTED.values()),
}, indent=2, sort_keys=True) + '\n')
print(f'expected cases OK: {sum(len(v) for v in EXPECTED.values())}')

# ---------------------------------------------------------- step status table
STEPS = ['E00', 'E01', 'E02', 'E03', 'E04', 'E05', 'E06', 'E07',
         'E08', 'E09', 'E10', 'E11', 'E12']
(ROOT / 'postrun/step_status_v1.json').write_text(json.dumps({
    'schema': 'plan126-step-status-v1',
    'batch': 126,
    'steps': {s: {'status': 'NOT_STARTED', 'attempts': []} for s in STEPS},
    'statuses_allowed': ['NOT_STARTED', 'RUNNING', 'PASS', 'FAIL_STOP',
                         'BLOCKED_SPEC', 'NOT_COVERED', 'N/A'],
    'outcome_dimensions': ['observed_facts', 'run_accepted', 'coverage', 'stage_qualified'],
    'qualification': {'M4': False, 'F6': False, 'P1': False,
                      'plant': False, 'hard_realtime': False},
    'production_B_mode': 'MANUAL+RC override',
    'automatic_owned_runs': 0,
}, indent=2, sort_keys=True) + '\n')
print('step status OK')

# ------------------------------------------------------------ self-verification
summary = {
    'schema': 'plan126-E00-verification-v1',
    'inputs_pinned': len(manifest),
    'component_lineage_count': len(LINEAGE),
    'identical_headers_proven': all(v['byte_identical'] for v in identical.values()),
    'contract_sha_ok': cpin['sha256'] == CONTRACT_SHA,
    'budgets_ok': budgets == EXPECTED_BUDGETS,
    'expected_case_count': sum(len(v) for v in EXPECTED.values()),
    'workspace_ordinary_files': len(ws_files),
    'porcelain_lines': len([l for l in porcelain.splitlines() if l.strip()]),
    'files_written': sorted(str(p.relative_to(ROOT)) for p in OUT.rglob('*') if p.is_file())
                     + ['postrun/step_status_v1.json'],
}
(ROOT / 'evidence/E00/attempt01/verification.json').write_text(
    json.dumps(summary, indent=2, sort_keys=True) + '\n')
print(json.dumps({k: v for k, v in summary.items() if k != 'files_written'},
                 indent=2, ensure_ascii=False))
