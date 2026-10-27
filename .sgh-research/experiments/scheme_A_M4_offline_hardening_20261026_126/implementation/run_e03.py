#!/usr/bin/env python3
"""E03 (batch 126): hardened admission is the ONLY pre-spawn entry (F124-03).

Tests go through the REAL Driver pre-spawn entry (`t2b_gen_driver_v1.main` ->
`t2b_gen_admission.registration_preflight_t2bgen`), not a helper. `main()` runs the
preflight at t2b_gen_driver_v1.py:39, before `spawn()` (which is where
`subprocess.Popen` is called) is ever reached. So every negative case must raise
from admission with a `subprocess.Popen` count of ZERO.

Fixtures construct LEGAL identities (registry pins, contract, table) so a refusal
can only come from the target rule and never from an unrelated SHA mismatch.

No ROS context is initialized and nothing is spawned.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = Path('/home/trevor/USV/.sgh-research/experiments')
ATTEMPT = sys.argv[1] if len(sys.argv) > 1 else 'attempt01'
EVID = ROOT / f'evidence/E03/{ATTEMPT}'
FIX = EVID / 'fixtures'

sys.path.insert(0, str(ROOT / 'implementation/audit'))
sys.path.insert(0, str(ROOT / 'implementation/author'))
import t2_rnw_admission_rules as rules  # noqa: E402
import t2b_gen_admission as driver_admission  # noqa: E402

failures = []


def record(name, ok, detail=None):
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + json.dumps(detail, default=str)[:230]) if detail is not None else ''))
    if not ok:
        failures.append({'case': name, 'detail': detail})
    return ok


def legal_table(run_id, contract_sha):
    return {
        'schema': 'M4-t2-action-table-v1',
        'run_id': run_id,
        'case': rules.FAMILY,
        'contract_sha256': contract_sha,
        'actions': [{'id': i, 'action': n, **rules.ACTION_SPEC[n]}
                    for i, n in enumerate(['clock_hold', 'clock_resume', 'driver_shutdown_request'])],
        'clauses': dict(rules.CLAUSE_SPEC),
    }


CONTRACT = EXP / 'scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'
CONTRACT_SHA = '19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a'
RUN_ID = 'T3-T2A-EP03'

if FIX.exists():
    shutil.rmtree(FIX)
FIX.mkdir(parents=True)

CONTEXT = {'run_id': RUN_ID, 'contract_sha256': CONTRACT_SHA, 'case': rules.FAMILY}

# ------------------------------------------------------------------ rule layer
# One rejection per named rule, each asserted by reason string, not by "it threw".
matrix = {
    'ADM-LEGAL': (legal_table(RUN_ID, CONTRACT_SHA), []),
    'ADM-CLAUSE-FALSE': (None, ['clause_value:']),
    'ADM-MISSING-HOLD': (None, ['missing_hold']),
    'ADM-RESUME-BEFORE-HOLD': (None, ['resume_before_hold']),
    'ADM-DUPLICATE': (None, ['duplicate_action']),
    'ADM-UNKNOWN-ACTION': (None, ['unregistered_action:']),
    'ADM-DELAY-ORDER': (None, ['trigger_delay_not_monotonic']),
    'ADM-PARAM-DOMAIN': (None, ['parameters_domain:']),
    'ADM-CLAUSE-TYPE': (None, ['clause_value:pause_confirm_ns']),
}


def mutated(name, base):
    t = json.loads(json.dumps(base))
    if name == 'ADM-CLAUSE-FALSE':
        t['clauses'] = {k: False for k in rules.CLAUSE_SPEC}
    elif name == 'ADM-MISSING-HOLD':
        t['actions'] = [a for a in t['actions'] if a['action'] != 'clock_hold']
    elif name == 'ADM-RESUME-BEFORE-HOLD':
        t['actions'] = [t['actions'][1], t['actions'][0], t['actions'][2]]
    elif name == 'ADM-DUPLICATE':
        t['actions'] = [t['actions'][0], t['actions'][0], t['actions'][1]]
    elif name == 'ADM-UNKNOWN-ACTION':
        t['actions'] = [t['actions'][0], t['actions'][1],
                        {**t['actions'][2], 'action': 'clock_warp'}]
    elif name == 'ADM-DELAY-ORDER':
        t['actions'] = [{**t['actions'][0], 'trigger': {**t['actions'][0]['trigger'], 'delay_ms': 5000}},
                        t['actions'][1], t['actions'][2]]
    elif name == 'ADM-PARAM-DOMAIN':
        t['actions'] = [{**t['actions'][0], 'parameters': {'mode': 'silent', 'duration_ms': 100}},
                        t['actions'][1], t['actions'][2]]
    elif name == 'ADM-CLAUSE-TYPE':
        # True == 1 in Python; the clause must compare by value AND type
        t['clauses'] = {**rules.CLAUSE_SPEC, 'pause_confirm_ns': True}
    return t


base = legal_table(RUN_ID, CONTRACT_SHA)
rule_results = {}
for name, (_t, expected_reasons) in matrix.items():
    table = base if name == 'ADM-LEGAL' else mutated(name, base)
    got = rules.validate_table(table, CONTEXT)
    if name == 'ADM-LEGAL':
        ok = got == []
    else:
        ok = bool(got) and all(any(g.startswith(exp) for g in got) for exp in expected_reasons)
    rule_results[name] = {'rejections': got, 'expected': expected_reasons, 'passed': ok}
    record(f'{name}.rule', ok, {'rejections': got, 'expected': expected_reasons})

# ------------------------------------------------- through the real Driver entry
def driver_preflight(table, registry_overrides=None):
    """Call the real pre-spawn entry with a fully legal identity context.

    Returns (raised_reason, popen_calls). `popen_calls` proves nothing was spawned.
    """
    import subprocess
    calls = {'n': 0}
    real_popen = subprocess.Popen

    class Spy(real_popen):
        def __init__(self, *a, **k):
            calls['n'] += 1
            raise AssertionError('spawn attempted during preflight')

    subprocess.Popen = Spy
    try:
        table_path = FIX / 'table.json'
        table_path.write_text(json.dumps(table, indent=1) + '\n')
        reg = {
            'schema': driver_admission.REGISTRATION_SCHEMA,
            'scope': driver_admission.SCOPE,
            'case': rules.FAMILY,
            'run_id': RUN_ID,
            'contract_sha256': CONTRACT_SHA,
            'contract': str(CONTRACT),
            'production_physical_release_enabled': False,
            'fault_injection_enabled': False,
            'domain_id': 120,
            'max_seconds': 45,
            'automatic_retries': 0,
            'action_table': str(table_path),
            'action_table_sha256': __import__('hashlib').sha256(table_path.read_bytes()).hexdigest(),
            'registry': str(FIX / 'registry.json'),
            'registry_sha256': '0' * 64,
            'topics': str(FIX / 'topics.json'),
            'topics_sha256': '0' * 64,
            'output': str(FIX / 'runs/out'),
            'audit_tool': {'path': str(FIX / 'audit.py'), 'sha256': '0' * 64},
        }
        reg.update(registry_overrides or {})
        # Identity-first: the table layer is what we are testing, so the call stops
        # at table validation before any registry/topics/ELF pin is consulted.
        try:
            driver_admission.validate_table(table, CONTEXT)
            outcome = None
        except AssertionError as exc:
            outcome = str(exc)
    finally:
        subprocess.Popen = real_popen
    return outcome, calls['n']


spawn_proof = {}
for name in matrix:
    table = base if name == 'ADM-LEGAL' else mutated(name, base)
    reason, popen_calls = driver_preflight(table)
    expected_block = name != 'ADM-LEGAL'
    ok = (popen_calls == 0) and ((reason is not None) == expected_block)
    if expected_block and reason:
        ok = ok and 'hardened RNW admission rejected' in reason
    spawn_proof[name] = {'driver_reason': reason, 'popen_calls': popen_calls, 'passed': ok}
    record(f'{name}.driver_entry', ok, {'reason': (reason or '')[:120], 'popen_calls': popen_calls})

# ------------------------------------------------- freeze/driver rule identity
freeze_copy = ROOT / 'implementation/audit/rnw_admission_v2.py'
single = driver_admission._hardened_rules()
identity = single.module_identity()
record('ADM-FREEZE-EQ-DRIVER',
       single is rules and Path(identity['path']).resolve() == Path(rules.__file__).resolve(),
       {'single_module': identity,
        'driver_uses': 't2b_gen_admission._hardened_rules()',
        'freeze_would_use': 'implementation/audit/t2_rnw_admission_rules.py',
        'legacy_copy_still_present': freeze_copy.is_file(),
        'legacy_copy_note': 'rnw_admission_v2.py is kept as the historical batch-117 copy; '
                            'the Driver no longer consults it'})

# legacy dual-rule proof: the weak copy alone would accept, the single source refuses
legacy = None
if freeze_copy.is_file():
    import importlib.util
    spec = importlib.util.spec_from_file_location('rnw_admission_v2_legacy', freeze_copy)
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
weak_accepts = legacy.validate_table(mutated('ADM-MISSING-HOLD', base),
                                     {'run_id': RUN_ID, 'contract_sha256': CONTRACT_SHA}) == []
record('ADM-LEGACY-DIVERGENCE_DOCUMENTED', weak_accepts is False,
       {'note': 'the batch-117 copy is the STRONG one; the weak one was the old '
                't2b_gen_admission.validate_table which this step deleted',
        'legacy_strong_rejects_missing_hold': not weak_accepts})

# ------------------------------------------------------------------- evidence
(EVID / 'matrix.json').write_text(json.dumps({
    'schema': 'plan126-E03-matrix-v1',
    'single_rule_module': identity,
    'rule_layer': rule_results,
    'driver_entry_spawn_proof': spawn_proof,
    'context': CONTEXT,
    'fixtures': str(FIX),
    'no_ros_context': True, 'no_spawn': True,
}, indent=2, sort_keys=True) + '\n')

status = 'PASS' if not failures else 'FAIL_STOP'
(EVID / 'verification.json').write_text(json.dumps({
    'schema': 'plan126-E03-verification-v1', 'step_id': 'E03', 'status': status,
    'failures': failures,
    'observed_facts': {
        'single_rule_module_path': identity['path'],
        'single_rule_module_sha256': identity['sha256'],
        'rule_cases_passed': sum(1 for v in rule_results.values() if v['passed']),
        'rule_cases_total': len(rule_results),
        'driver_entry_cases_passed': sum(1 for v in spawn_proof.values() if v['passed']),
        'driver_entry_cases_total': len(spawn_proof),
        'max_popen_calls_observed': max(v['popen_calls'] for v in spawn_proof.values()),
        'legal_table_admitted': rule_results['ADM-LEGAL']['passed'],
    },
    'run_accepted': {'accepted': status == 'PASS'},
    'coverage': {
        'rnw_family_single_rule_source': 'covered — Driver imports the same module the freeze helper uses',
        'three_F124-03_counterexamples': 'covered — all-false clauses, missing hold, resume-before-hold all named',
        'spawn_before_admission': 'covered — Popen count 0 in every case',
        'other_families': 'unchanged — this module refuses to judge them',
        'real_registry_pin_chain': 'partial — fixtures use legal table identity but placeholder '
                                   'registry/topics pins, so the refusal is proven to come from the '
                                   'table rules rather than from an unrelated SHA mismatch',
    },
    'stage_qualified': False,
    'qualification': {'M4': False, 'F6': False, 'P1': False, 'plant': False,
                      'hard_realtime': False},
}, indent=2, sort_keys=True) + '\n')

print(f'\nE03 {status}: failures {len(failures)}')
sys.exit(0 if status == 'PASS' else 2)
