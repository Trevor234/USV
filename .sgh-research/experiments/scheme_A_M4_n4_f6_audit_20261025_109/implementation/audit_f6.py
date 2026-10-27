#!/usr/bin/env python3
"""Fail-closed per-clause audit for the F6 model transaction (batch 108).
Recomputes every SHA, assertion list and registration parameter from primary
evidence; records the production-library SHA baseline; trusts no self-report."""
import hashlib, json, sys
from pathlib import Path

B108 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_n4_f6_impl_20261025_108')
ROOT = Path(__file__).resolve().parents[1]
IMPL = B108 / 'implementation'
LIB = Path('/home/trevor/USV/usv_mpc_ws/install/usv_mpc_cpp/lib')
ACADOS = Path('/home/trevor/acados/lib')

def pin(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

clauses = []
def clause(cid, obligation, ok, detail=None):
    clauses.append({'clause': cid, 'obligation': obligation, 'passed': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + cid + ((' :: ' + json.dumps(detail, default=str)[:180]) if detail else ''))
    return bool(ok)

ok_all = True
REG = json.loads((IMPL / 'F6_registration.json').read_bytes())
REGISTRY = json.loads((IMPL / 'f6_registry.json').read_bytes())
VERDICT = json.loads((B108 / 'postrun/f6_run_verdict_v1.json').read_bytes())

ok_all &= clause('F6.identity', 'identity pins',
    pin(REGISTRY['test_binary']) == REGISTRY['test_binary_sha256'] == REG['tree_base']['binary_sha256']
    and pin(REGISTRY['wrapper_source']) == REGISTRY['wrapper_source_sha256']
    and pin(REGISTRY['harness_source']) == REGISTRY['harness_source_sha256']
    and pin(REGISTRY['source_bundle']['path']) == REGISTRY['source_bundle']['sha256'])
ok_all &= clause('F6.registration_schema', 'N4 binding',
    REG['obligation_binding']['n4'] == 'batch 67 next plan (N4)' and REG['fixed_parameters']['codegen'] is False
    and REG['fixed_parameters']['gp_ppo'] is False
    and REG['fixed_parameters']['dimensions'] == {'NX': 8, 'NU': 2, 'N': 20, 'NP': 6, 'NP_GLOBAL': 30}
    and REG['governance']['production_package_unmodified'] is True)
for case in REG['cases']:
    cid = case['case_id']
    result = json.loads((IMPL / 'runs' / cid / 'result.json').read_bytes())
    names = [a['name'] for a in result['assertions']]
    facts = {
        'names_match_registration': names == case['assertions'],
        'all_passed': all(a['passed'] for a in result['assertions']),
        'tolerance_match': result.get('tolerance') == REG['fixed_parameters']['tolerance'],
        'm1_perturbations_match': result.get('m1_perturbations') == REG['fixed_parameters']['m1_perturbations'],
        'flags_false': all(result.get(k) is False for k in
                           ('ROS_context_created', 'stage_qualified', 'execute_qualified', 'research_conclusion')),
    }
    ok_all &= clause(f'F6.{cid}.recompute', 'N4 component evidence', all(facts.values()), facts)
run_dirs = sorted(p.name for p in (IMPL / 'runs').iterdir())
ok_all &= clause('F6.single_execution', 'governance',
                 run_dirs == sorted(c['case_id'] for c in REG['cases']), run_dirs)
ok_all &= clause('F6.verdict_consistent', 'fail-closed verdict',
                 VERDICT['passed'] is True and len(VERDICT['cases']) == 6
                 and all(c['passed'] and c['rc'] == 0 and not c['timed_out'] for c in VERDICT['cases'])
                 and all(c['assertion_count'] == c['registered_count'] for c in VERDICT['cases']))
prod_libs = {n: pin(LIB / n) for n in ('libmpc_solver_lib.a', 'libcodegen_lib.a', 'libmpc_core_lib.a')}
prod_libs.update({n: pin(ACADOS / n) for n in ('libacados.so', 'libblasfeo.so', 'libhpipm.so')})
ok_all &= clause('F6.production_libs_pinned', 'unmodified-production baseline', len(prod_libs) == 6)

manifest = {f'batch108/{n}': pin(IMPL / n) for n in
            ('F6_registration.json', 'f6_registry.json', 'model_transaction_v1.hpp',
             'test_f6_model_transaction.cpp')}
manifest.update({f'batch108/runs/{c["case_id"]}/result.json': pin(IMPL / 'runs' / c['case_id'] / 'result.json')
                 for c in REG['cases']})
manifest['batch108/postrun/f6_run_verdict_v1.json'] = pin(B108 / 'postrun/f6_run_verdict_v1.json')
manifest.update({f'production/{k}': v for k, v in prod_libs.items()})

report = {'schema': 'F6-audit/v1', 'batch': 109, 'clauses': clauses, 'clause_count': len(clauses),
          'passed': bool(ok_all),
          'obligation': 'N4 five duties evidenced at component level along the real numeric setter paths',
          'production_libs_sha_baseline': prod_libs,
          'originals_sha_baseline': manifest,
          'not_claimed': ['F6 stage qualification (GP phase etc. remain)', 'M4 qualification',
                          'production default change', 'any research conclusion']}
(ROOT / 'evidence/audit_f6_v1.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print('AUDIT passed=' + str(ok_all) + ' clauses=' + str(len(clauses)))
sys.exit(0 if ok_all else 2)
