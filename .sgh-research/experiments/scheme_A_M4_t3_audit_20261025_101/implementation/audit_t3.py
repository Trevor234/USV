#!/usr/bin/env python3
"""Fail-closed per-clause audit for T3-Q (batch 99) and T3-C (batch 100).

Consumes only primary evidence: registrations, registries, run directories,
event journals and result files. Every balance, count, ladder and SHA is
recomputed here; no runner/driver self-reported passed flag is trusted.
Output: evidence/audit_t3_v1.json (+ SHA baseline manifest). rc=0 only if
every clause passes."""
import hashlib, json, os, sys
from pathlib import Path

B99 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t3q_impl_20261025_99')
B100 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t3c_impl_20261025_100')
ROOT = Path(__file__).resolve().parents[1]

def pin(p):
    raw = Path(p).read_bytes()
    return hashlib.sha256(raw).hexdigest()

def rows_of(jsonl):
    out = []
    for line in Path(jsonl).read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out

clauses = []
def clause(cid, obligation, ok, detail=None):
    clauses.append({'clause': cid, 'obligation': obligation, 'passed': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + cid + ((' :: ' + json.dumps(detail, default=str)[:200]) if detail else ''))
    return bool(ok)

ok_all = True

# ============================ T3-Q (batch 99) ============================
QREG = json.loads((B99 / 'implementation/T3Q_registration.json').read_bytes())
QREGI = json.loads((B99 / 'implementation/t3q_registry.json').read_bytes())

q_binary = Path(QREGI['test_binary'])
q_source = Path(QREGI['test_source'])
ok_all &= clause('Q.identity.binary', 'actual_source_recording.03',
                 q_binary.is_file() and pin(q_binary) == QREGI['test_binary_sha256'] == QREG['tree_base']['binary_sha256'],
                 {'binary': str(q_binary), 'sha': QREGI['test_binary_sha256'][:16]})
ok_all &= clause('Q.identity.source_and_bundle', 'actual_source_recording.03',
                 pin(q_source) == QREGI['test_source_sha256']
                 and Path(QREGI['source_bundle']['path']).is_file()
                 and pin(QREGI['source_bundle']['path']) == QREGI['source_bundle']['sha256']
                 and json.loads(Path(QREGI['source_bundle']['path']).read_bytes())['file_count'] == 104)

EFFECTIVE = {'T3-Q1d': 'T3-Q1d', 'T3-Q4': 'T3-Q4',
             'T3-Q1r': 'T3-Q1r_r2', 'T3-Q2': 'T3-Q2_r2', 'T3-Q3': 'T3-Q3_r2'}
JSONL = {'T3-Q1d': 'q1d.jsonl', 'T3-Q1r': 'q1r.jsonl', 'T3-Q2': 'q2.jsonl', 'T3-Q3': 'q3.jsonl', 'T3-Q4': 'q4.jsonl'}
PRESSURE = {'T3-Q1d', 'T3-Q1r', 'T3-Q2', 'T3-Q3'}
ATTEMPTS = {'T3-Q1d': 2561, 'T3-Q1r': 2560, 'T3-Q2': 3072, 'T3-Q3': 2560, 'T3-Q4': 100}

for case in QREG['cases']:
    cid = case['case_id']
    rd = B99 / 'implementation/runs' / EFFECTIVE[cid]
    result = json.loads((rd / 'result.json').read_bytes())
    data = rows_of(rd / JSONL[cid])
    summary = data[-1]
    events = [r for r in data[:-1]]
    recomputes = {
        'schema': result.get('schema') == 'T3-queue-pressure/v1',
        'case_match': result.get('case') == cid,
        'row_count': len(data) == summary['emitted'] + 1,
        'balance': summary['generated'] == summary['emitted'] + summary['dropped'],
        'attempts': summary['generated'] == ATTEMPTS[cid],
        'dropped_zero_iff_negative_control': (summary['dropped'] == 0) == (cid == 'T3-Q4'),
        'pressure_applied': summary['dropped'] > 0 if cid in PRESSURE else True,
        'normal_complete': summary['normal_source_complete'] == (cid == 'T3-Q4'),
        'assertion_names_match_registration':
            sorted(a['name'] for a in result['assertions']) == sorted(case['assertions']),
        'all_assertions_passed': all(a['passed'] for a in result['assertions']),
        'assertion_count': result['assertion_count'] == len(case['assertions']),
        'qualification_flags_false': all(result.get(k) is False for k in
                                         ('ROS_context_created', 'stage_qualified', 'execute_qualified', 'research_conclusion')),
    }
    ok_all &= clause(f'Q.{cid}.recompute', 'actual_source_recording.03', all(recomputes.values()),
                     {k: v for k, v in recomputes.items()})

v1 = json.loads((B99 / 'postrun/t3q_run_verdict_v1.json').read_bytes())
v2 = json.loads((B99 / 'postrun/t3q_run_verdict_v2.json').read_bytes())
ok_all &= clause('Q.lineage.attempt1_originals_preserved', 'governance',
                 all((B99 / 'implementation/runs' / c / 'result.json').is_file() for c in ('T3-Q1r', 'T3-Q2', 'T3-Q3'))
                 and sum(1 for c in v1['cases'] if not c['passed']) == 3
                 and QREG.get('revision') == 2 and 'revision_note' in QREG)
ok_all &= clause('Q.lineage.verdict_v2_consistent', 'governance',
                 v2['passed'] is True and len(v2['cases']) == 5
                 and {c['case'] for c in v2['cases']} == set(EFFECTIVE)
                 and all(c['passed'] for c in v2['cases'])
                 and QREG['governance']['auto_retry'] == 0)

# ============================ T3-C (batch 100) ============================
R12 = json.loads((B100 / 'implementation/T3C12_registration.json').read_bytes())
R3 = json.loads((B100 / 'implementation/T3C3_registration.json').read_bytes())
G12 = json.loads((B100 / 'implementation/t3c_registry_c12.json').read_bytes())
G3 = json.loads((B100 / 'implementation/t3c_registry_c3.json').read_bytes())
T3D = B100 / 'implementation/t2_author/t3_cleanup_driver_v1.py'
T2D = B100 / 'implementation/t2_author/t2_scenario_driver_v1.py'

ok_all &= clause('C.identity.registries', 'publication_exit.09/.10',
                 pin(B100 / 'implementation/t3c_registry_c12.json') == R12['registry_sha256']
                 and pin(B100 / 'implementation/t3c_registry_c3.json') == R3['registry_sha256']
                 and pin(T3D) == G12['driver_tool_sha256'] == G3['driver_tool_sha256'])
roles_ok = True
for reg_, g_ in ((R12, G12), (R3, G3)):
    for role, row in g_['roles'].items():
        roles_ok &= Path(row['binary']).is_file() and pin(row['binary']) == row['binary_sha256']
    roles_ok &= pin(g_['roles']['regulator']['source_bundle']['path']) == g_['roles']['regulator']['source_bundle']['sha256']
ok_all &= clause('C.identity.role_binaries_and_bundle', 'publication_exit.09/.10', roles_ok)
ok_all &= clause('C.identity.fixtures_differ_as_registered', 'publication_exit.09/.10',
                 G12['roles']['fixture']['binary_sha256'] != G3['roles']['fixture']['binary_sha256']
                 and R12['t3_close_injection']['mechanism'] == 'role_side_survivor'
                 and R3['t3_close_injection']['mechanism'] == 'none')

t2_lines = [l for l in T2D.read_text().splitlines() if 'spawn(' in l and 'def spawn' not in l]
t3_lines = [l for l in T3D.read_text().splitlines() if 'spawn(' in l and 'def spawn' not in l]
ok_all &= clause('C.static.spawn_sites_identical', 'publication_exit.10',
                 t2_lines == t3_lines and 'cleanup_failed' in T3D.read_text() and 'cleanup_failed' not in T2D.read_text(),
                 {'spawn_lines': len(t2_lines)})

for tag, reg_path, expect_cleanup in (('C12', R12, True), ('C3', R3, False)):
    rd = Path(reg_path['output'])
    ev = rows_of(rd / 'driver_events.jsonl')
    result = json.loads((rd / 'driver_result.json').read_bytes())
    closed = result['closed_roles']
    by_role = {r['role']: r for r in closed}
    spawns = [e for e in ev if e['type'] == 'role_spawned']
    cleanup = [e for e in ev if e['type'] == 'cleanup_failed']
    facts = {
        'four_unique_spawns': len(spawns) == 4 and len({s['role'] for s in spawns}) == 4,
        'four_closed': len(closed) == 4,
        'no_restart_events': not [e['type'] for e in ev if 'restart' in e['type'] or 'respawn' in e['type'] or 'retry' in e['type']],
        'registration_output_binding': str(rd) == reg_path['output'] and reg_path['automatic_retries'] == 0,
    }
    if expect_cleanup:
        facts.update({
            'cleanup_failed_fixture_only': len(cleanup) == 1 and cleanup[0]['role'] == 'fixture'
                and cleanup[0]['group_empty'] is False and cleanup[0]['check_deadline_ns'] == 1000000000
                and cleanup[0]['returncode'] == 0,
            'cleanup_failed_roles_field': result.get('cleanup_failed_roles') == ['fixture'],
            'fixture_ladder_int_term': [s['signal'] for s in by_role['fixture']['signals']] == ['SIGINT', 'SIGTERM'],
            'others_healthy': all(by_role[r]['returncode'] == 0 and by_role[r]['group_empty'] is True
                                  for r in ('regulator', 'worker', 'recorder')),
            'run_failed': result.get('passed') is False,
        })
        sv = json.loads((rd / 'fixture/t3_survivor.json').read_bytes())
        pgid = json.loads((rd / 'fixture/spawn.json').read_bytes())['pid']
        alive = False
        try:
            os.killpg(pgid, 0); alive = True
        except ProcessLookupError:
            alive = False
        facts['survivor_bounded_dead'] = sv.get('policy') == 't3_close_survivor_v1' and sv.get('self_deadline_ms') == 3000 and not alive
    else:
        facts.update({
            'no_cleanup_failed': not cleanup and result.get('cleanup_failed_roles') == [],
            'all_healthy': all(r['returncode'] == 0 and r['group_empty'] is True for r in closed)
                and all([s['signal'] for s in by_role[r]['signals']] == ['SIGINT'] for r in ('fixture', 'worker', 'recorder')),
        })
    ok_all &= clause(f'C.{tag}.events_recompute', 'publication_exit.09/.10' if expect_cleanup else 'negative control',
                     all(facts.values()), {k: v for k, v in facts.items()})

# Originals preserved: SHA baseline manifest for future audits
manifest = {}
for base, names in ((B99, ['implementation/T3Q_registration.json', 'implementation/t3q_registry.json',
                           'postrun/t3q_run_verdict_v1.json', 'postrun/t3q_run_verdict_v2.json']),
                    (B100, ['implementation/T3C12_registration.json', 'implementation/T3C3_registration.json',
                            'implementation/t3c_registry_c12.json', 'implementation/t3c_registry_c3.json',
                            'evidence/freeze/driver_diff.txt',
                            'implementation/runs/T3C_C12/driver_events.jsonl',
                            'implementation/runs/T3C_C12/driver_result.json',
                            'implementation/runs/T3C_C12/fixture/t3_survivor.json',
                            'implementation/runs/T3C_C3/driver_events.jsonl',
                            'implementation/runs/T3C_C3/driver_result.json'])):
    for n in names:
        manifest[str(base.name) + '/' + n] = pin(base / n)
for d in EFFECTIVE.values():
    for f in ('result.json',):
        manifest['scheme_A_M4_t3q_impl_20261025_99/implementation/runs/' + d + '/' + f] = pin(B99 / 'implementation/runs' / d / f)

report = {'schema': 'T3-audit/v1', 'batch': 101, 'clauses': clauses,
          'clause_count': len(clauses), 'passed': bool(ok_all),
          'obligations': {'actual_source_recording.03': 'component-level evidenced (batch 99)',
                          'publication_exit.09': 'driver-level evidenced (batch 100 C12)',
                          'publication_exit.10': 'driver-level evidenced (batch 100 C12 no-respawn group)'},
          'not_claimed': ['four-role Stored reconciliation in Q-family',
                          'kernel-level absolutely bounded exit',
                          'any stage qualification or research conclusion'],
          'originals_sha_baseline': manifest}
(ROOT / 'evidence/audit_t3_v1.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print('AUDIT passed=' + str(ok_all) + ' clauses=' + str(len(clauses)))
sys.exit(0 if ok_all else 2)
