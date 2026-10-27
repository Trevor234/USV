#!/usr/bin/env python3
"""T2B-GEN audit v2 (batch 126 derivation; fixes F124-04).

Three defects in the batch-105 auditor, each verified against its source before
this rewrite:

1. `clause(cid, obligation, ok, detail)` took `ok` POSITIONALLY. At the two
   source-comparison call sites the boolean landed in the `obligation` slot and
   the explanation string landed in `ok`, so `bool("some text") == True` recorded
   `passed: true` even when the comparison was false. Here `clause()` is
   keyword-only and requires a real bool; anything else is a hard error, never a
   coercion.

2. The "two commits have different binding" check compared constants:
   `(1, task_generation_0, path_fp_0) != (2, task_generation_1, path_fp_1)` is
   true because 1 != 2 in the first tuple slot, i.e. it compared the generation
   NUMBER it was supposed to ignore. Here the generation number is excluded by
   construction and the comparison runs over the binding identity that can
   actually differ.

3. `pin(bundle_file)` proved the manifest bytes did not change, not that the
   files listed inside the manifest did. Here every bundle entry is recomputed.

Provenance is recorded per clause: `recomputed_from_primary_evidence` vs
`references_harness_result`, so the report never presents a referenced harness
claim as an independent recompute.
"""
import difflib
import hashlib
import json
import os
import shutil
from pathlib import Path

EXP = Path('/home/trevor/USV/.sgh-research/experiments')
B91 = EXP / 'scheme_A_M4_g4c_fix_20261025_91/implementation/t2_author'
B103 = EXP / 'scheme_A_M4_t2b_gen_impl_20261025_103'
B104 = EXP / 'scheme_A_M4_t2bgen_owned_20261025_104'

# Binding identity fields. The generation NUMBER is deliberately absent: it always
# changes between generations and comparing it is the batch-105 tautology.
BINDING_FIELDS = ('task_generation', 'model_generation', 'config_generation',
                  'schedule_generation', 'clock_epoch', 'path_fingerprint',
                  'profile_fingerprint', 'run_id', 'boot_id', 'contract_hash',
                  'nominal_hash')


def pin(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows_of(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


class ClauseLog:
    """Collects clauses. `passed` is a real bool or this raises."""

    def __init__(self):
        self.clauses = []

    def add(self, *, clause, obligation, passed, provenance, detail=None):
        if type(passed) is not bool:
            raise TypeError(
                f'clause {clause!r}: passed must be bool, got {type(passed).__name__} '
                f'({passed!r}); a non-bool here is exactly the batch-105 defect')
        if provenance not in ('recomputed_from_primary_evidence', 'references_harness_result'):
            raise ValueError(f'clause {clause!r}: provenance must be stated, got {provenance!r}')
        self.clauses.append({'clause': clause, 'obligation': obligation,
                             'passed': passed, 'provenance': provenance, 'detail': detail})
        return passed

    @property
    def all_passed(self):
        return all(c['passed'] for c in self.clauses)


def binding_of(epoch):
    """Extract the comparable binding identity, excluding the generation number."""
    return {k: epoch.get(k) for k in BINDING_FIELDS}


def bindings_differ(e1, e2):
    """True iff at least one real binding field differs (generation number excluded)."""
    b1, b2 = binding_of(e1), binding_of(e2)
    diffs = {k: (b1[k], b2[k]) for k in BINDING_FIELDS if b1[k] != b2[k]}
    return bool(diffs), diffs


def recompute_bundle(bundle_path, resolve_against=None):
    """Recompute every file listed INSIDE the bundle manifest.

    `resolve_against` redirects the recorded absolute paths onto a private MIRROR
    that preserves each entry's path relative to the common bundle root, so a tamper
    test never has to write a protected original and same-named files cannot collide.
    Returns (mismatches, count). The manifest's own sha proves nothing about its
    contents.
    """
    bundle = json.loads(Path(bundle_path).read_bytes())
    files = bundle.get('files', {})
    entries = list(files.values() if isinstance(files, dict) else files)
    base = Path(os.path.commonpath([str(Path(e['path']).parent) for e in entries if e.get('path')])) \
        if any(e.get('path') for e in entries) else None
    bad = []
    for entry in entries:
        path = entry.get('path')
        if not path:
            bad.append({'path': None, 'why': 'no_path_recorded'})
            continue
        target = Path(path)
        if resolve_against is not None:
            target = Path(resolve_against) / Path(path).relative_to(base)
        if not target.is_file():
            bad.append({'path': path, 'resolved': str(target), 'why': 'missing'})
            continue
        raw = target.read_bytes()
        rec_bytes, rec_sha = entry.get('bytes'), entry.get('sha256')
        if rec_bytes is not None and len(raw) != rec_bytes:
            bad.append({'path': path, 'resolved': str(target), 'why': 'bytes_changed',
                        'recorded': rec_bytes, 'observed': len(raw)})
        if rec_sha is not None and hashlib.sha256(raw).hexdigest() != rec_sha:
            bad.append({'path': path, 'resolved': str(target), 'why': 'sha_changed'})
    return bad, len(entries)


def mirror_bundle(bundle_path, dest):
    """Copy every entry of a bundle into `dest`, preserving relative paths."""
    bundle = json.loads(Path(bundle_path).read_bytes())
    files = bundle.get('files', {})
    entries = list(files.values() if isinstance(files, dict) else files)
    base = Path(os.path.commonpath([str(Path(e['path']).parent) for e in entries if e.get('path')]))
    for entry in entries:
        p = entry.get('path')
        if not p:
            continue
        src = Path(p)
        if not src.is_file():
            continue
        out = Path(dest) / Path(p).relative_to(base)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
    return base


def audit_component(log):
    """Batch-103 component stage, recomputed from primary run results."""
    creg = json.loads((B103 / 'implementation/T2BGEN_registration.json').read_bytes())
    cregistry = json.loads((B103 / 'implementation/t2bgen_registry.json').read_bytes())

    log.add(clause='GEN.component.identity_pins', obligation='R74-07 identity',
            passed=(pin(cregistry['test_binary']) == cregistry['test_binary_sha256']
                    == creg['tree_base']['binary_sha256']
                    and pin(cregistry['test_source']) == cregistry['test_source_sha256']),
            provenance='recomputed_from_primary_evidence')

    # per-file recompute of the frozen Epoch header against the batch-91 review state
    frozen_ok = pin(B103 / 'implementation/t2_author/observer/src/shadow/task_time_profile_v1.hpp') \
        == pin(B91 / 'observer/src/shadow/task_time_profile_v1.hpp')
    log.add(clause='GEN.component.frozen_epoch_byte_identical', obligation='R74-07 G4',
            passed=frozen_ok, provenance='recomputed_from_primary_evidence')

    gen_events = {'T2B-GEN-E1': 1, 'T2B-GEN-E2': 1, 'T2B-GEN-E3': 0,
                  'T2B-GEN-E4': 0, 'T2B-GEN-E5': 0, 'T2B-GEN-E6': 1}
    for case in creg['cases']:
        cid = case['case_id']
        result = json.loads((B103 / 'implementation/runs' / cid / 'result.json').read_bytes())
        names = [a['name'] for a in result['assertions']]
        facts = {
            'names_match_registration': names == case['assertions'],
            'all_passed': all(a['passed'] for a in result['assertions']),
            'generation_event_count': len(result.get('generation_events', [])) == gen_events[cid],
            'policy_fields': (result.get('policy') == 'scoped_generation_first_target_task_time_profile_v2'
                              and result.get('frozen_epoch_policy')
                              == 'first_successful_job_submit_completion_target_sim_v1'),
            'flags_false': all(result.get(k) is False for k in
                               ('ROS_context_created', 'stage_qualified',
                                'execute_qualified', 'research_conclusion')),
        }
        log.add(clause=f'GEN.component.{cid}.recompute', obligation='R74-07 component',
                passed=all(facts.values()), provenance='recomputed_from_primary_evidence',
                detail=facts)

    run_dirs = sorted(p.name for p in (B103 / 'implementation/runs').iterdir())
    log.add(clause='GEN.component.single_execution', obligation='governance',
            passed=run_dirs == sorted(c['case_id'] for c in creg['cases']),
            provenance='recomputed_from_primary_evidence', detail=run_dirs)


def audit_owned(log, t104):
    """Batch-104 owned stage: source identity recomputed per file from the bundle."""
    rpos = json.loads((B104 / 'implementation/T2BGEN_POS_registration.json').read_bytes())
    rneg = json.loads((B104 / 'implementation/T2BGEN_NEG_registration.json').read_bytes())
    reg = json.loads((B104 / 'implementation/t2bgen_registry.json').read_bytes())

    identity_ok = (
        pin(B104 / 'implementation/t2bgen_registry.json')
        == rpos['registry_sha256'] == rneg['registry_sha256']
        and pin(t104 / 't2b_gen_driver_v1.py') == reg['driver_tool_sha256']
        and reg['regulator_source_sha256'] == pin(reg['regulator_source'])
        and reg['worker_source_sha256'] == pin(reg['worker_source'])
        and reg['fixture_source_sha256'] == pin(reg['fixture_source']))
    log.add(clause='GEN.owned.identity_pins', obligation='admission pins',
            passed=identity_ok, provenance='recomputed_from_primary_evidence')

    # THE F124-04 SITE: this comparison used to be passed positionally so the
    # explanation string was coerced to `ok` and a false result looked green.
    sources_ok = (pin(reg['worker_source']) == pin(B91 / 'worker/solver_worker_m4.cpp')
                  and pin(reg['fixture_source']) == pin(B91 / 'fixture/synthetic_source_m4.cpp')
                  and pin(t104 / 'observer/src/shadow/task_time_profile_v1.hpp')
                  == pin(B91 / 'observer/src/shadow/task_time_profile_v1.hpp'))
    log.add(clause='GEN.owned.sources_vs_batch91',
            obligation='frozen Epoch header and worker/fixture sources byte-identical to batch 91',
            passed=sources_ok, provenance='recomputed_from_primary_evidence',
            detail={'worker': pin(reg['worker_source']) == pin(B91 / 'worker/solver_worker_m4.cpp'),
                    'fixture': pin(reg['fixture_source']) == pin(B91 / 'fixture/synthetic_source_m4.cpp'),
                    'epoch_header': pin(t104 / 'observer/src/shadow/task_time_profile_v1.hpp')
                                    == pin(B91 / 'observer/src/shadow/task_time_profile_v1.hpp')})

    for role, row in reg['roles'].items():
        if role == 'recorder':
            continue
        log.add(clause=f'GEN.owned.elf_{role}', obligation='ELF pin',
                passed=pin(row['binary']) == row['binary_sha256'],
                provenance='recomputed_from_primary_evidence')

    # POS generation flow, with the binding comparison done on real fields
    src = rows_of(B104 / 'implementation/runs/T2BGEN_POS/regulator/source.jsonl')
    committed = [r for r in src if r.get('type') == 'reference_epoch_committed']
    opened = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
    resub = [r for r in src if r.get('type') == 'job_scoped_generation_resubmit']
    job_ids = [r['job']['job_id'] for r in src if r.get('type') == 'job' and isinstance(r.get('job'), dict)]
    pv = [r for r in src if r.get('type') == 'path_version']

    flow_ok = len(opened) == 1 and opened[0].get('generation') == 2
    binding_diff = None
    if len(committed) == 2:
        e1, e2 = (c['reference_epoch'] for c in committed)
        differs, binding_diff = bindings_differ(e1, e2)
        flow_ok = (flow_ok and [e1.get('generation'), e2.get('generation')] == [1, 2]
                   and differs)
    else:
        flow_ok = False
    flow_ok = (flow_ok
               and opened[0].get('previous_terminal_reason') == 'epoch_binding_changed'
               and len(resub) >= 1 and [j for j in job_ids if j > 2]
               and job_ids == sorted(job_ids)
               and not [r for r in src if r.get('type') == 'job_not_submitted'
                        and str(r.get('reason', '')).startswith('task_time_reference:')]
               and len({r['fingerprint'] for r in pv}) == 2)
    log.add(clause='GEN.owned.pos_generation_flow', obligation='R74-07 owned positive control',
            passed=bool(flow_ok), provenance='recomputed_from_primary_evidence',
            detail={'jobs': job_ids,
                    'generations': [c['reference_epoch'].get('generation') for c in committed],
                    'task_generations': [c['reference_epoch'].get('task_generation') for c in committed],
                    'binding_differences': binding_diff,
                    'binding_compared_without_generation_number': True})

    drv = json.loads((B104 / 'implementation/runs/T2BGEN_POS/driver_result.json').read_bytes())
    close_ok = (len(drv['closed_roles']) == 4
                and all(r['returncode'] == 0 and r['group_empty'] is True for r in drv['closed_roles'])
                and len([e for e in rows_of(B104 / 'implementation/runs/T2BGEN_POS/driver_events.jsonl')
                         if e['type'] == 'role_spawned']) == 4)
    log.add(clause='GEN.owned.pos_close_clean', obligation='owned close',
            passed=close_ok, provenance='recomputed_from_primary_evidence')

    nsrc = rows_of(B104 / 'implementation/runs/T2BGEN_NEG/regulator/source.jsonl')
    ndrv = json.loads((B104 / 'implementation/runs/T2BGEN_NEG/driver_result.json').read_bytes())
    neg_ok = (not [r for r in nsrc if r.get('type') == 'reference_epoch_generation_opened']
              and len([r for r in nsrc if r.get('type') == 'reference_epoch_committed']) == 1
              and len({r.get('fingerprint') for r in nsrc if r.get('type') == 'path_version'}) == 1
              and len(ndrv['closed_roles']) == 4
              and all(r['returncode'] == 0 and r['group_empty'] is True for r in ndrv['closed_roles']))
    log.add(clause='GEN.owned.neg_no_generation_ordinary_unchanged',
            obligation='negative control', passed=neg_ok,
            provenance='recomputed_from_primary_evidence')

    sig = {'launch1': 'ordinary runtime release stays disabled',
           'launch2': 'ordinary runtime release stays disabled',
           'launch3': 'unknown diagnostic_case'}
    lineage_ok = True
    for tag in ('POS', 'NEG'):
        for launch, needle in sig.items():
            d = B104 / f'implementation/runs/T2BGEN_{tag}_{launch}'
            if not d.is_dir() or not (d / 'driver_result.json').is_file():
                lineage_ok = False
                continue
            blob = ''
            for role in ('fixture', 'regulator'):
                f = d / role / 'stderr.log'
                if f.is_file():
                    blob += f.read_text()
            lineage_ok = lineage_ok and needle in blob
    log.add(clause='GEN.owned.launch_lineage_preserved', obligation='governance originals',
            passed=lineage_ok, provenance='recomputed_from_primary_evidence')


def audit_bundles(log, t103, t104):
    """Recompute every file listed inside each source bundle (F124-04 defect 3)."""
    for tag, bundle in (('component', B103 / 'evidence/freeze/source_bundle.json'),
                        ('owned', B104 / 'evidence/freeze/source_bundle.json')):
        if not bundle.is_file():
            log.add(clause=f'GEN.{tag}.bundle_items_recomputed', obligation='bundle contents',
                    passed=False, provenance='recomputed_from_primary_evidence',
                    detail={'why': 'bundle manifest missing', 'path': str(bundle)})
            continue
        bad, total = recompute_bundle(bundle)
        log.add(clause=f'GEN.{tag}.bundle_items_recomputed', obligation='bundle contents',
                passed=not bad, provenance='recomputed_from_primary_evidence',
                detail={'entries': total, 'mismatches': bad[:5],
                        'note': 'the manifest sha alone would not have caught these'})


def audit_harness_claims(log):
    """Clauses that only REFERENCE the old harness, stated as such."""
    log.add(clause='GEN.owned.driver_diff_admission_only',
            obligation='spawn logic untouched (diff shape)',
            passed=True, provenance='references_harness_result',
            detail={'note': 'batch-105 computed this diff; not recomputed here, and it is not '
                            'independent evidence that spawn behaviour is unchanged'})
    log.add(clause='GEN.owned.regulator_diff_scoped_only',
            obligation='minimal scoped wiring (diff markers)',
            passed=True, provenance='references_harness_result',
            detail={'note': 'marker heuristic from batch 105; a marker match does not prove the '
                            'edit is behaviourally minimal'})


def run(emit_path=None):
    log = ClauseLog()
    t103 = B103 / 'implementation/t2_author'
    t104 = B104 / 'implementation/t2_author'
    audit_component(log)
    audit_owned(log, t104)
    audit_bundles(log, t103, t104)
    audit_harness_claims(log)
    report = {
        'schema': 'T2B-GEN-audit/v2',
        'batch': 126,
        'clauses': log.clauses,
        'clause_count': len(log.clauses),
        'passed': log.all_passed,
        'provenance_split': {
            'recomputed_from_primary_evidence': sum(
                1 for c in log.clauses if c['provenance'] == 'recomputed_from_primary_evidence'),
            'references_harness_result': sum(
                1 for c in log.clauses if c['provenance'] == 'references_harness_result'),
        },
        'not_claimed': ['stage qualification', 'research conclusion',
                        'ordinary static task policy change'],
        'supersedes': 'batch-105 evidence/audit_t2bgen_v1.json (kept as history, not rewritten)',
    }
    if emit_path:
        Path(emit_path).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    import sys
    r = run(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"AUDIT passed={r['passed']} clauses={r['clause_count']} "
          f"provenance={r['provenance_split']}")
    for c in r['clauses']:
        if not c['passed']:
            print('  FAIL', c['clause'], json.dumps(c['detail'], default=str)[:200])
    sys.exit(0 if r['passed'] else 2)
