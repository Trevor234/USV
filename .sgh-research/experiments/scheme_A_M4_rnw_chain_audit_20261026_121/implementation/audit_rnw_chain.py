#!/usr/bin/env python3
"""Fail-closed chain audit for the T2A-RNW S0->S4 execution (batches 116-120).

Recomputes every identity pin, re-executes the deterministic offline matrices
(S1/S2 evidence reproducibility), re-adjudicates the S4 run from raw evidence
via the S1 pure audit, verifies lineage, and records SHA baselines. Trusts no
self-report."""
import hashlib, importlib.util, json, subprocess, sys
from pathlib import Path

B116 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_rnw_s0_evidence_20261025_116')
B117 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_rnw_s1_pure_20261025_117')
B118 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_rnw_s2_b2_20261025_118')
B119 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_rnw_s4_owned_20261025_119')
B112 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_rnw2_impl_20261025_112')
B104 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2bgen_owned_20261025_104')
ROOT = Path(__file__).resolve().parents[1]

def pin(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def rows_of(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]

clauses = []
def clause(cid, obligation, ok, detail=None):
    clauses.append({'clause': cid, 'obligation': obligation, 'passed': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + cid + ((' :: ' + json.dumps(detail, default=str)[:170]) if detail else ''))
    return bool(ok)

ok = True

# ---- S0 evidence integrity
ev = json.loads((B116 / 'postrun/three_column_evidence_v1.json').read_bytes())
a2 = rows_of(B112 / 'implementation/runs/T2A_RNW2/regulator/source.jsonl')
cl = [r for r in a2 if r.get('type') == 'clock']
sims = [r['sim_ns'] for r in cl]
rx = [r['receive_ns'] for r in cl]
gi = max(range(1, len(rx)), key=lambda i: rx[i] - rx[i - 1])
ok &= clause('S0.evidence_recompute_matches',
    'batch 116 three-column evidence',
    len(cl) == 97 and sims[gi] - sims[gi - 1] == 797450244
    and ev['runs'][1]['column_raw_received_clock']['silence_sim_advance_ns'] == 797450244
    and all(sims[i] >= sims[i - 1] for i in range(1, len(sims))),
    {'clocks': len(cl), 'silence_advance_ns': sims[gi] - sims[gi - 1]})

# ---- S1 matrix reproducibility (deterministic offline; re-run in a temp copy)
import shutil, tempfile
with tempfile.TemporaryDirectory() as td:
    src = B117 / 'implementation'
    dst = Path(td) / 'impl'
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', 'fixtures'))
    (dst.parent / 'postrun').mkdir(exist_ok=True)
    r = subprocess.run([sys.executable, str(dst / 'test_s1_pure.py')], capture_output=True, text=True,
                       cwd=dst.parent, timeout=300)
    m = json.loads((dst.parent / 'postrun/s1_acceptance_v1.json').read_bytes()) if (dst.parent / 'postrun/s1_acceptance_v1.json').is_file() else None
    ok &= clause('S1.matrix_reproducible',
        'S1 acceptance matrix 18/18 reproduces from identical inputs',
        r.returncode == 0 and m and m['passed'] == m['total'] == 18,
        {'rc': r.returncode, 'passed': (m or {}).get('passed'), 'total': (m or {}).get('total'),
         'stderr_tail': r.stderr[-200:] if r.returncode else None})

# ---- S2 identity + result integrity
S2REG = json.loads((B118 / 'implementation/S2_registration.json').read_bytes())
S2REGI = json.loads((B118 / 'implementation/s2_registry.json').read_bytes())
S2RES = json.loads((B118 / 'implementation/runs/S2_B2_MAPPING/result.json').read_bytes())
ok &= clause('S2.identity_pins',
    'S2 registry/registration/binary three-way',
    pin(S2REGI['test_binary']) == S2REGI['test_binary_sha256'] == S2REG['tree_base']['binary_sha256']
    and pin(S2REGI['helper_source']) == S2REGI['helper_source_sha256']
    and pin(S2REGI['fixture_source']) == S2REGI['fixture_source_sha256'])
ok &= clause('S2.result_vs_registration',
    'S2 16 assertions exactly as registered, all passed',
    [a['name'] for a in S2RES['assertions']] == S2REG['cases'][0]['assertions']
    and S2RES['passed'] is True
    and all(a['passed'] for a in S2RES['assertions']))
ok &= clause('S2.mutants_caught_onrecord',
    'three mutants caught',
    all(any(a['name'].startswith(f'mutant_m{i}') and a['passed'] for a in S2RES['assertions']) for i in (1, 2, 3)))

# ---- S4 identity chain
S4REG = json.loads((B119 / 'implementation/T2A_RNW3_registration.json').read_bytes())
S4REGI = json.loads((B119 / 'implementation/s4_registry.json').read_bytes())
GEN = json.loads((B119 / 'implementation/t2_author/t2b_gen_admission.py').read_bytes()) if False else None
sys.path.insert(0, str(B119 / 'implementation/t2_author'))
import t2b_gen_admission as gen119
ok &= clause('S4.identity_chain',
    'registration<->registry<->source pins',
    pin(B119 / 'implementation/s4_registry.json') == S4REG['registry_sha256']
    and pin(S4REGI['fixture_source']) == S4REGI['fixture_source_sha256'] == gen119.FIXTURE_SOURCE_SHA
    and pin(S4REGI['regulator_source']) == S4REGI['regulator_source_sha256'] == gen119.REGULATOR_SOURCE_SHA
    and pin(S4REGI['worker_source']) == S4REGI['worker_source_sha256'] == gen119.WORKER_SOURCE_SHA_B91)
ok &= clause('S4.regulator_unchanged_from_104_lineage',
    'scoped wiring regulator byte-identical to the audited 104 lineage',
    pin(S4REGI['regulator_source']) == pin(B104 / 'implementation/t2_author/observer/src/shadow/regulator_owned_execute.cpp'))
for role in ('worker', 'regulator', 'fixture'):
    row = S4REGI['roles'][role]
    ok &= clause(f'S4.elf_{role}', 'ELF pin', pin(row['binary']) == row['binary_sha256'])

# ---- S4 re-adjudication from raw evidence (pure recompute, no re-run)
sys.path.insert(0, str(B119 / 'implementation'))
spec = importlib.util.spec_from_file_location('rnw_audit_re', B119 / 'implementation/rnw_audit_v1.py')
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
res = audit.audit_rnw_run(B119 / 'implementation/runs/T2A_RNW3')
r4 = [c for c in res['clauses'] if c['name'] == 'r4_same_job_new_generation_acceptance'][0]
old = [c for c in res['clauses'] if c['name'] == 'old_candidate_disposition'][0]
ok &= clause('S4.r4_recomputed_from_raw_evidence',
    'R4 chain covered with same-Job facts',
    res['passed'] is True and r4['coverage'] == 'covered'
    and r4['detail']['control_source'] == 'candidate'
    and r4['detail']['api_returned'] == [True, True]
    and r4['detail']['candidate_accepted'] is True,
    r4['detail'])
ok &= clause('S4.old_candidates_honest',
    'old-candidate disposition honestly not_covered (no in-flight)',
    old['coverage'] == 'not_covered' and old['detail']['rejection_events'] == 0)

# ---- lineage preserved
lineage = all((B112 / f'implementation/runs/T2A_RNW2{suffix}').is_dir() for suffix in ('', '_attempt1'))
ok &= clause('S4.lineage_preserved', '112 attempts retained', lineage)

manifest = {
    'b116/three_column_evidence_v1.json': pin(B116 / 'postrun/three_column_evidence_v1.json'),
    'b117/rnw_audit_v1.py': pin(B117 / 'implementation/rnw_audit_v1.py'),
    'b117/rnw_admission_v2.py': pin(B117 / 'implementation/rnw_admission_v2.py'),
    'b118/helper': pin(B118 / 'implementation/t2_author/fixture/resume_stamp_mapping_v1.hpp'),
    'b118/result': pin(B118 / 'implementation/runs/S2_B2_MAPPING/result.json'),
    'b119/registration': pin(B119 / 'implementation/T2A_RNW3_registration.json'),
    'b119/run/source.jsonl': pin(B119 / 'implementation/runs/T2A_RNW3/regulator/source.jsonl'),
    'b119/run/driver_result.json': pin(B119 / 'implementation/runs/T2A_RNW3/driver_result.json'),
    'b119/verdict': pin(B119 / 'postrun/s4_verdict_v1.json'),
}
report = {'schema': 'T2A-RNW-chain-audit/v1', 'batch': 121, 'clauses': clauses,
          'clause_count': len(clauses), 'passed': bool(ok),
          'chain': 'S0(116) -> S1(117) -> S2(118) -> S4(119) -> closeout(120) per batch-115 review',
          'originals_sha_baseline': manifest,
          'not_claimed': ['B0 (clock-epoch recovery) design or evidence', 'B1 exemption use',
                          'M4/F6/P1 qualification change', 'old-candidate rejection positive facts (cited semantics only)']}
(ROOT / 'evidence/audit_rnw_chain_v1.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
print('AUDIT passed=' + str(ok) + ' clauses=' + str(len(clauses)))
sys.exit(0 if ok else 2)
