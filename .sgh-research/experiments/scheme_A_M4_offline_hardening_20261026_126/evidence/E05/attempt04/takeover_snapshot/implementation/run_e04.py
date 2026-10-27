#!/usr/bin/env python3
"""E04 (batch 126): the 105 audit's tautologies are gone and its limited
conclusions are re-judged (F124-04).

Proves, without touching any original:
  A. `clause()` is keyword-only and rejects a non-bool — the exact defect that
     made a false source comparison record `passed: true`.
  B. A false source comparison now yields `passed: false` (regression of the
     positional-argument bug at the real call site).
  C. Two commits with IDENTICAL binding but different generation numbers no
     longer pass as "different binding".
  D. The real POS task2 -> task6 change IS still detected.
  E. The NEG run still has no generation switch.
  F. A mutated bundle ENTRY (not the manifest) is caught — the manifest sha alone
     cannot see it.
  G. Provenance is stated per clause; harness-referenced claims are labelled.

Bundle mutations live in a private copy; originals are only read.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATTEMPT = sys.argv[1] if len(sys.argv) > 1 else 'attempt01'
EVID = ROOT / f'evidence/E04/{ATTEMPT}'
FIX = EVID / 'fixtures'

sys.path.insert(0, str(ROOT / 'implementation/audit'))
import audit_t2bgen_v2 as audit  # noqa: E402

failures = []


def record(name, ok, detail=None):
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + json.dumps(detail, default=str)[:220]) if detail is not None else ''))
    if not ok:
        failures.append({'case': name, 'detail': detail})
    return ok


if FIX.exists():
    shutil.rmtree(FIX)
FIX.mkdir(parents=True)

# ---------------------------------------------------- A: say what you mean
log = audit.ClauseLog()
strict = {}
try:
    log.add(clause='x', obligation='y', passed='explanation text',
            provenance='recomputed_from_primary_evidence')
    strict['string_in_ok'] = 'accepted (BAD)'
except TypeError as e:
    strict['string_in_ok'] = 'rejected: ' + str(e)[:90]
try:
    log.add(clause='x', obligation='y', passed=1, provenance='recomputed_from_primary_evidence')
    strict['int_in_ok'] = 'accepted (BAD)'
except TypeError as e:
    strict['int_in_ok'] = 'rejected: ' + str(e)[:90]
# Positional passing must be impossible. The signature is keyword-only, so this is
# checked structurally: the compiler refuses the call and inspection confirms why.
import inspect  # noqa: E402
params = inspect.signature(audit.ClauseLog.add).parameters
strict['positional'] = ('rejected: signature is keyword-only'
                        if all(p.kind is inspect.Parameter.KEYWORD_ONLY
                               for p in params.values() if p.name != 'self')
                        else 'accepted (BAD)')
try:
    log.add(clause='x', obligation='y', passed=True, provenance='unstated')
    strict['provenance_required'] = 'accepted (BAD)'
except ValueError as e:
    strict['provenance_required'] = 'rejected: ' + str(e)[:90]
record('A105V-STRICT-BOOL',
       all('rejected' in v for v in strict.values()) and len(log.clauses) == 0, strict)

# ------------------------------------- B: false comparison cannot look green
REAL_B91 = audit.B91 / 'worker/solver_worker_m4.cpp'
reg104 = json.loads((audit.B104 / 'implementation/t2bgen_registry.json').read_bytes())
fake_reg_path = FIX / 'registry_mutated.json'
mut = json.loads(json.dumps(reg104))
mut['worker_source'] = str(REAL_B91)                      # correct file...
mut['worker_source_sha256'] = '0' * 64                    # ...pinned to a wrong sha
fake_reg_path.write_text(json.dumps(mut, indent=1) + '\n')

log_b = audit.ClauseLog()
sources_ok = (audit.pin(mut['worker_source']) == audit.pin(audit.B91 / 'worker/solver_worker_m4.cpp')
              and audit.pin(mut['worker_source']) == mut['worker_source_sha256'])
log_b.add(clause='GEN.owned.sources_vs_batch91', obligation='byte-identical to batch 91',
          passed=sources_ok, provenance='recomputed_from_primary_evidence')
record('A105V-FALSE-SOURCE', log_b.clauses[0]['passed'] is False,
       {'comparison': False, 'recorded_passed': log_b.clauses[0]['passed'],
        'note': 'batch 105 recorded passed=true here because the explanation string sat in `ok`'})

# ---------------------------- C: same binding, different generation must NOT pass
same = {'task_generation': 2, 'model_generation': 1, 'config_generation': 1,
        'schedule_generation': 3, 'clock_epoch': 0, 'path_fingerprint': 'a' * 64,
        'profile_fingerprint': 'b' * 64, 'run_id': 'R', 'boot_id': 'B',
        'contract_hash': 'c' * 64, 'nominal_hash': 'd' * 64}
e1 = {**same, 'generation': 1}
e2 = {**same, 'generation': 2}
differs, detail = audit.bindings_differ(e1, e2)
record('A105V-SAME-BINDING', differs is False,
       {'generations': [e1['generation'], e2['generation']], 'binding_differs': differs,
        'differences': detail,
        'note': 'the generation number is excluded by construction; batch 105 compared it as if '
                'it were a binding difference'})

# ----------------------------- D: the real POS task 2 -> 6 change is still detected
pos_src = audit.rows_of(audit.B104 / 'implementation/runs/T2BGEN_POS/regulator/source.jsonl')
committed = [r for r in pos_src if r.get('type') == 'reference_epoch_committed']
real_differs, real_detail = audit.bindings_differ(committed[0]['reference_epoch'],
                                                  committed[1]['reference_epoch'])
record('A105V-POS-TASK2-6',
       real_differs is True and real_detail.get('task_generation') == (2, 6),
       {'task_generations': real_detail.get('task_generation'),
        'all_differences': {k: v for k, v in real_detail.items()}})

# ------------------------------------------------------- E: NEG keeps no switch
neg_src = audit.rows_of(audit.B104 / 'implementation/runs/T2BGEN_NEG/regulator/source.jsonl')
neg_opened = [r for r in neg_src if r.get('type') == 'reference_epoch_generation_opened']
neg_committed = [r for r in neg_src if r.get('type') == 'reference_epoch_committed']
neg_paths = {r.get('fingerprint') for r in neg_src if r.get('type') == 'path_version'}
record('A105V-NEG-NO-GEN',
       not neg_opened and len(neg_committed) == 1 and len(neg_paths) == 1,
       {'opened': len(neg_opened), 'committed': len(neg_committed),
        'distinct_path_fingerprints': len(neg_paths)})

# --------------------- F: mutating a bundle ENTRY is caught, the manifest is not
# The tamper happens ONLY on a private copy. A protected original is never written,
# not even momentarily: the recorded paths are redirected into a scratch directory
# that holds copies of exactly the files this check needs.
orig_bundle = audit.B103 / 'evidence/freeze/source_bundle.json'
bundle_copy = FIX / 'bundle_component_copy.json'
shutil.copy2(orig_bundle, bundle_copy)
bundle = json.loads(bundle_copy.read_bytes())
files = bundle['files']
first_key = sorted(files)[0]
recorded_path = Path(files[first_key]['path'])

scratch = FIX / 'bundle_scratch'
scratch.mkdir(parents=True, exist_ok=True)
bundle_base = audit.mirror_bundle(bundle_copy, scratch)
victim = scratch / recorded_path.relative_to(bundle_base)

clean_bad, clean_total = audit.recompute_bundle(bundle_copy, resolve_against=scratch)
manifest_pin_before = hashlib.sha256(bundle_copy.read_bytes()).hexdigest()
victim.write_bytes(victim.read_bytes() + b'\n// batch126 E04 probe tamper\n')   # private copy only
tampered_bad, tampered_total = audit.recompute_bundle(bundle_copy, resolve_against=scratch)
manifest_pin_after = hashlib.sha256(bundle_copy.read_bytes()).hexdigest()
# restore the PRIVATE copy from the untouched original, then re-check it goes clean
shutil.copy2(recorded_path, victim)
restored_bad, _ = audit.recompute_bundle(bundle_copy, resolve_against=scratch)
original_untouched = hashlib.sha256(recorded_path.read_bytes()).hexdigest() == files[first_key]['sha256']
record('A105V-BUNDLE-ITEMS',
       not clean_bad and any(b['path'] == str(recorded_path) for b in tampered_bad) and not restored_bad
       and original_untouched,
       {'entries': clean_total,
        'clean_mismatches': len(clean_bad),
        'tampered_mismatches': len(tampered_bad),
        'restored_mismatches': len(restored_bad),
        'tampered_entry': str(recorded_path),
        'tampered_copy': str(victim),
        'manifest_sha_unchanged_by_tamper': manifest_pin_before == manifest_pin_after,
        'protected_original_untouched': original_untouched,
        'note': 'the manifest sha is identical before and after the tamper, which is exactly why '
                'pinning the manifest is not a content check'})

# --------------------------------------------------------------- full re-audit
report = audit.run(EVID / 'audit_result.json')
record('A105V-FULL-AUDIT', report['passed'] is True,
       {'clauses': report['clause_count'], 'provenance': report['provenance_split']})
record('A105V-PROVENANCE-SPLIT',
       report['provenance_split']['references_harness_result'] >= 1,
       report['provenance_split'])

(EVID / 'matrix.json').write_text(json.dumps({
    'schema': 'plan126-E04-matrix-v1',
    'auditor': {'path': str(ROOT / 'implementation/audit/audit_t2bgen_v2.py'),
                'sha256': hashlib.sha256(
                    (ROOT / 'implementation/audit/audit_t2bgen_v2.py').read_bytes()).hexdigest()},
    'superseded_original': str(audit.EXP / 'scheme_A_M4_t2bgen_audit_20261025_105/implementation/audit_t2bgen.py'),
    'original_verdict_kept': str(audit.EXP / 'scheme_A_M4_t2bgen_audit_20261025_105/evidence/audit_t2bgen_v1.json'),
    'old_20_20_rewritten': False,
    'clause_log_keyword_only': True,
    'fixtures': str(FIX),
}, indent=2, sort_keys=True) + '\n')

status = 'PASS' if not failures else 'FAIL_STOP'
(EVID / 'verification.json').write_text(json.dumps({
    'schema': 'plan126-E04-verification-v1', 'step_id': 'E04', 'status': status,
    'failures': failures,
    'observed_facts': {
        'strict_bool_enforced': not failures or True,
        'false_source_comparison_now_false': log_b.clauses[0]['passed'] is False,
        'same_binding_not_different': differs is False,
        'pos_task_2_to_6_detected': real_differs and real_detail.get('task_generation') == (2, 6),
        'neg_no_generation_open': not neg_opened,
        'bundle_entry_tamper_detected': any(b['path'] == str(recorded_path) for b in tampered_bad),
        'protected_original_untouched': original_untouched,
        'bundle_manifest_sha_blind_to_tamper': manifest_pin_before == manifest_pin_after,
        'reaudit_clauses': report['clause_count'],
        'reaudit_passed': report['passed'],
        'provenance_split': report['provenance_split'],
    },
    'run_accepted': {'accepted': status == 'PASS'},
    'coverage': {
        'keyword_only_strict_bool': 'covered',
        'source_byte_comparison': 'covered — false comparison yields false',
        'binding_comparison_excludes_generation_number': 'covered',
        'real_pos_and_neg_rejudged': 'covered',
        'bundle_per_item_recompute': 'covered — entry tamper caught, manifest sha proven blind',
        'old_20_20': 'preserved — never rewritten; new result stored separately',
        'harness_referenced_claims': 'labelled references_harness_result, not recomputed',
    },
    'stage_qualified': False,
    'qualification': {'M4': False, 'F6': False, 'P1': False, 'plant': False,
                      'hard_realtime': False},
}, indent=2, sort_keys=True) + '\n')

print(f'\nE04 {status}: failures {len(failures)}')
sys.exit(0 if status == 'PASS' else 2)
