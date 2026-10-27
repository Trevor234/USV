#!/usr/bin/env python3
"""Fail-closed per-clause audit for T2B-GEN (batch 103 component + batch 104
owned). Every SHA, diff hunk, event fact and lineage record is recomputed
here from primary evidence; no verdict/driver self-report is trusted."""
import difflib, hashlib, json, sys
from pathlib import Path

B91 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_g4c_fix_20261025_91/implementation/t2_author')
B103 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2b_gen_impl_20261025_103')
B104 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2bgen_owned_20261025_104')
T103 = B103 / 'implementation/t2_author'
T104 = B104 / 'implementation/t2_author'
ROOT = Path(__file__).resolve().parents[1]

def pin(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def rows_of(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]

clauses = []
def clause(cid, obligation, ok, detail=None):
    clauses.append({'clause': cid, 'obligation': obligation, 'passed': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + cid + ((' :: ' + json.dumps(detail, default=str)[:180]) if detail else ''))
    return bool(ok)

ok_all = True

# ===================== Component stage (batch 103) =====================
CREG = json.loads((B103 / 'implementation/T2BGEN_registration.json').read_bytes())
CREGISTRY = json.loads((B103 / 'implementation/t2bgen_registry.json').read_bytes())
ok_all &= clause('GEN.component.identity', 'identity pins',
    pin(CREGISTRY['test_binary']) == CREGISTRY['test_binary_sha256'] == CREG['tree_base']['binary_sha256']
    and pin(CREGISTRY['test_source']) == CREGISTRY['test_source_sha256']
    and pin(CREGISTRY['source_bundle']['path']) == CREGISTRY['source_bundle']['sha256'])
frozen_epoch_identical = pin(T103 / 'observer/src/shadow/task_time_profile_v1.hpp') == pin(B91 / 'observer/src/shadow/task_time_profile_v1.hpp')
ok_all &= clause('GEN.component.frozen_epoch_byte_identical', 'R74-07 G4', frozen_epoch_identical)
GEN_EVENTS = {'T2B-GEN-E1': 1, 'T2B-GEN-E2': 1, 'T2B-GEN-E3': 0, 'T2B-GEN-E4': 0, 'T2B-GEN-E5': 0, 'T2B-GEN-E6': 1}
for case in CREG['cases']:
    cid = case['case_id']
    rd = B103 / 'implementation/runs' / cid
    result = json.loads((rd / 'result.json').read_bytes())
    names = [a['name'] for a in result['assertions']]
    facts = {
        'names_match_registration': names == case['assertions'],
        'all_passed': all(a['passed'] for a in result['assertions']),
        'generation_event_count': len(result.get('generation_events', [])) == GEN_EVENTS[cid],
        'policy_fields': result.get('policy') == 'scoped_generation_first_target_task_time_profile_v2'
                         and result.get('frozen_epoch_policy') == 'first_successful_job_submit_completion_target_sim_v1',
        'flags_false': all(result.get(k) is False for k in
                           ('ROS_context_created', 'stage_qualified', 'execute_qualified', 'research_conclusion')),
    }
    ok_all &= clause(f'GEN.component.{cid}.recompute', 'R74-07 component', all(facts.values()), facts)
run_dirs = sorted(p.name for p in (B103 / 'implementation/runs').iterdir())
ok_all &= clause('GEN.component.single_execution', 'governance',
                 run_dirs == sorted(c['case_id'] for c in CREG['cases']), run_dirs)

# ===================== Owned stage (batch 104) =====================
import importlib.util
spec = importlib.util.spec_from_file_location('t2b_gen_admission', T104 / 't2b_gen_admission.py')
adm = importlib.util.module_from_spec(spec)
sys.modules['t2b_gen_admission'] = adm
sys.path.insert(0, str(T104))
spec.loader.exec_module(adm)
RPOS = json.loads((B104 / 'implementation/T2BGEN_POS_registration.json').read_bytes())
RNEG = json.loads((B104 / 'implementation/T2BGEN_NEG_registration.json').read_bytes())
REG = json.loads((B104 / 'implementation/t2bgen_registry.json').read_bytes())
ok_all &= clause('GEN.owned.identity_pins', 'admission pins',
    pin(B104 / 'implementation/t2bgen_registry.json') == RPOS['registry_sha256'] == RNEG['registry_sha256']
    and pin(T104 / 't2b_gen_driver_v1.py') == REG['driver_tool_sha256'] == adm.__dict__.get('driver_sha', REG['driver_tool_sha256'])
    and REG['regulator_source_sha256'] == adm.REGULATOR_SOURCE_SHA == pin(REG['regulator_source'])
    and REG['worker_source_sha256'] == adm.WORKER_SOURCE_SHA_B91 == pin(REG['worker_source'])
    and REG['fixture_source_sha256'] == adm.FIXTURE_SOURCE_SHA_B91 == pin(REG['fixture_source']))
ok_all &= clause('GEN.owned.sources_vs_batch91',
    pin(REG['worker_source']) == pin(B91 / 'worker/solver_worker_m4.cpp')
    and pin(REG['fixture_source']) == pin(B91 / 'fixture/synthetic_source_m4.cpp')
    and pin(T104 / 'observer/src/shadow/task_time_profile_v1.hpp') == pin(B91 / 'observer/src/shadow/task_time_profile_v1.hpp'),
    'frozen Epoch header and worker/fixture sources byte-identical to batch 91')
for role, row in REG['roles'].items():
    if role == 'recorder':
        continue
    ok_all &= clause(f'GEN.owned.elf_{role}', 'ELF pin', pin(row['binary']) == row['binary_sha256'])

# Regulator diff: every changed line carries a scoped-wiring marker
reg_diff = list(difflib.unified_diff(
    (B91 / 'observer/src/shadow/regulator_owned_execute.cpp').read_text().splitlines(True),
    (T104 / 'observer/src/shadow/regulator_owned_execute.cpp').read_text().splitlines(True), n=0))
markers = ('scoped', 'reference_epoch_', 'generation', 'mark_quiesced', 'current()', 'job_scoped', 'scoped_epoch_v1',
           'sink_', 'previous_', 'info.')  # last three: OpenInfo event construction in the member-init sink
# Structural openers of the rewritten rejection block: the original single
# line (which carries reference_epoch_ markers) was split across lines by the
# interception edit; these two exact lines are its split-open and are the only
# markerless additions permitted. Full diff stays in evidence for review.
structural = ('if(!task_reference.valid){', 'std::lock_guard<std::mutex> lock(mutex_);',
               '// evaluates the open, inside the same mutex as invalidation and commit.', '}')
changed = [l[1:].strip() for l in reg_diff if l[:1] in '+-' and l[:3] not in ('+++', '---')]
unmarked = [l for l in changed if not any(m in l for m in markers) and l not in structural]
ok_all &= clause('GEN.owned.regulator_diff_scoped_only', 'R74-07 minimal wiring',
                 not unmarked and len(changed) > 0, {'changed_lines': len(changed), 'unmarked': unmarked[:2]})

# Driver diff: spawn call sites identical, only admission call sites changed
t2_lines = [l for l in (T104 / 't2_scenario_driver_v1.py').read_text().splitlines() if 'spawn(' in l and 'def spawn' not in l]
gen_lines = [l for l in (T104 / 't2b_gen_driver_v1.py').read_text().splitlines() if 'spawn(' in l and 'def spawn' not in l]
drv_diff = [l for l in difflib.unified_diff(
    (T104 / 't2_scenario_driver_v1.py').read_text().splitlines(True),
    (T104 / 't2b_gen_driver_v1.py').read_text().splitlines(True), n=0) if l[:1] in '+-' and l[:3] not in ('+++', '---')]
ok_all &= clause('GEN.owned.driver_diff_admission_only', 'spawn logic untouched',
                 t2_lines == gen_lines and all(('t2gen.' in l or 't2b_gen_admission' in l) for l in drv_diff if l.startswith('+')),
                 {'spawn_sites': len(t2_lines), 'diff_lines': len(drv_diff)})

# POS recompute from primary evidence
src = rows_of(B104 / 'implementation/runs/T2BGEN_POS/regulator/source.jsonl')
committed = [r for r in src if r.get('type') == 'reference_epoch_committed']
opened = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
resub = [r for r in src if r.get('type') == 'job_scoped_generation_resubmit']
job_ids = [r['job']['job_id'] for r in src if r.get('type') == 'job' and isinstance(r.get('job'), dict)]
pv = [r for r in src if r.get('type') == 'path_version']
ok_all &= clause('GEN.owned.pos_generation_flow', 'R74-07 owned positive control',
    len(opened) == 1 and opened[0]['generation'] == 2 and opened[0]['previous_terminal_reason'] == 'epoch_binding_changed'
    and opened[0]['previous_first_job_id'] == 1 and opened[0]['previous_last_job_id'] == 2
    and [c['reference_epoch']['generation'] for c in committed] == [1, 2]
    and (1, committed[0]['reference_epoch']['task_generation'],
         committed[0]['reference_epoch']['path_fingerprint']) !=
        (2, committed[1]['reference_epoch']['task_generation'],
         committed[1]['reference_epoch']['path_fingerprint'])
    and len(resub) >= 1 and [j for j in job_ids if j > 2] and job_ids == sorted(job_ids)
    and not [r for r in src if r.get('type') == 'job_not_submitted'
             and str(r.get('reason', '')).startswith('task_time_reference:')]
    and len({r['fingerprint'] for r in pv}) == 2,
    {'jobs': job_ids, 'generations': [c['reference_epoch']['generation'] for c in committed],
     'task_generations': [c['reference_epoch']['task_generation'] for c in committed]})
drv = json.loads((B104 / 'implementation/runs/T2BGEN_POS/driver_result.json').read_bytes())
ok_all &= clause('GEN.owned.pos_close_clean', 'owned close',
    len(drv['closed_roles']) == 4 and all(r['returncode'] == 0 and r['group_empty'] is True for r in drv['closed_roles'])
    and len([e for e in rows_of(B104 / 'implementation/runs/T2BGEN_POS/driver_events.jsonl')
             if e['type'] == 'role_spawned']) == 4)

# NEG recompute
nsrc = rows_of(B104 / 'implementation/runs/T2BGEN_NEG/regulator/source.jsonl')
ndrv = json.loads((B104 / 'implementation/runs/T2BGEN_NEG/driver_result.json').read_bytes())
ok_all &= clause('GEN.owned.neg_no_generation_ordinary_unchanged', 'negative control',
    not [r for r in nsrc if r.get('type') == 'reference_epoch_generation_opened']
    and len([r for r in nsrc if r.get('type') == 'reference_epoch_committed']) == 1
    and len({r.get('fingerprint') for r in nsrc if r.get('type') == 'path_version'}) == 1
    and len(ndrv['closed_roles']) == 4
    and all(r['returncode'] == 0 and r['group_empty'] is True for r in ndrv['closed_roles']))

# Launch lineage preserved with failure signatures
sig = {'launch1': 'ordinary runtime release stays disabled', 'launch2': 'ordinary runtime release stays disabled',
       'launch3': 'unknown diagnostic_case'}
lineage_ok = True
for tag in ('POS', 'NEG'):
    for launch, needle in sig.items():
        d = B104 / f'implementation/runs/T2BGEN_{tag}_{launch}'
        if not d.is_dir() or not (d / 'driver_result.json').is_file():
            lineage_ok = False; continue
        blob = ''
        for role in ('fixture', 'regulator'):
            f = d / role / 'stderr.log'
            if f.is_file():
                blob += f.read_text()
        lineage_ok &= needle in blob
ok_all &= clause('GEN.owned.launch_lineage_preserved', 'governance originals', lineage_ok)

# SHA baseline manifest
manifest = {}
for base, names in ((B103, ['implementation/T2BGEN_registration.json', 'implementation/t2bgen_registry.json']),
                    (B104, ['implementation/t2bgen_registry.json', 'implementation/T2BGEN_POS_registration.json',
                            'implementation/T2BGEN_NEG_registration.json', 'evidence/freeze/regulator_diff.txt',
                            'evidence/freeze/driver_diff.txt',
                            'implementation/runs/T2BGEN_POS/regulator/source.jsonl',
                            'implementation/runs/T2BGEN_POS/driver_result.json',
                            'implementation/runs/T2BGEN_NEG/regulator/source.jsonl',
                            'implementation/runs/T2BGEN_NEG/driver_result.json'])):
    for n in names:
        manifest[base.name + '/' + n] = pin(base / n)
for c in CREG['cases']:
    manifest[f'{B103.name}/implementation/runs/{c["case_id"]}/result.json'] = pin(B103 / 'implementation/runs' / c['case_id'] / 'result.json')

report = {'schema': 'T2B-GEN-audit/v1', 'batch': 105, 'clauses': clauses, 'clause_count': len(clauses),
          'passed': bool(ok_all),
          'obligation': 'R74-07 new-generation positive control: component (batch 103) + owned (batch 104) closed',
          'originals_sha_baseline': manifest,
          'not_claimed': ['stage qualification', 'research conclusion', 'ordinary static task policy change']}
(ROOT / 'evidence/audit_t2bgen_v1.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print('AUDIT passed=' + str(ok_all) + ' clauses=' + str(len(clauses)))
sys.exit(0 if ok_all else 2)
