#!/usr/bin/env python3
"""Read-only replay and private in-memory probes of the batch-56 auditor.

No ROS context, processes, control publications, or original output writes.
Only the auditor's report directory and explicit registration argv are routed
to this review. Mutation probes replace selected input values in memory.
"""
import collections
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
P = HERE.parent / 'scheme_A_M4_diagnostic_worker_20261021_56'


def read(p):
    return json.loads(Path(p).read_bytes())


def pin(p):
    p = Path(p)
    h = hashlib.sha256()
    n = 0
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''):
            h.update(chunk)
            n += len(chunk)
    return {'bytes': n, 'sha256': h.hexdigest()}


def save(name, value):
    with (HERE / 'evidence' / name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')


def identity_review():
    lock = read(P / 'preflight/prerun_source_lock_v1.json')
    mismatches = []
    for name, expected in lock['files'].items():
        try:
            actual = pin(name)
        except Exception as exc:
            mismatches.append({'path': name, 'error': str(exc)})
            continue
        if actual != expected:
            mismatches.append({'path': name, 'expected': expected, 'actual': actual})
    regpath = P / 'implementation/selected_runtime_registry_v1.json'
    registry = read(regpath)
    role_checks = {}
    for role, entry in registry['roles'].items():
        actual = pin(entry['binary'])
        assert actual['sha256'] == entry['binary_sha256'], role + ' ELF pin'
        bundle = entry['source_bundle']
        assert pin(bundle['path'])['sha256'] == bundle['sha256'], role + ' bundle pin'
        role_checks[role] = {'binary': entry['binary'], **actual,
                            'source_bundle_sha256': bundle['sha256']}
    bundle = read(registry['roles']['worker']['source_bundle']['path'])
    for name, row in bundle['files'].items():
        assert pin(row['path']) == {k: row[k] for k in ('bytes', 'sha256')}, name
    assert pin(registry['driver'])['sha256'] == registry['driver_tool_sha256']
    cases = {}
    for case in ('W1', 'W3', 'W4'):
        regfile = P / 'implementation' / (case + '_registration_v1.json')
        reg = read(regfile)
        run = Path(reg['output'])
        assert run.name == case + '_05'
        assert pin(regpath)['sha256'] == reg['registry_sha256']
        assert pin(reg['contract'])['sha256'] == reg['contract_sha256']
        sha = pin(regfile)['sha256']
        launch = read(P / 'evidence' / (case + '_launch_v1.json'))
        dm = read(run / 'driver_manifest.json')
        audit = read(P / 'postrun' / (case + '_audit_v1.json'))
        assert sha == launch['registration_sha256'] == dm['registration_sha256'] == audit['registration_sha256']
        assert dm['tool_sha256'] == registry['driver_tool_sha256']
        assert dm['registry_sha256'] == reg['registry_sha256']
        for role in registry['roles']:
            mp = run / role / ('owned_manifest.json' if role == 'fixture' else 'manifest.json')
            m = read(mp)
            assert m['binary_sha256'] == role_checks[role]['sha256'], case + '/' + role + ' manifest ELF'
            assert m['source_bundle_sha256'] == role_checks[role]['source_bundle_sha256'], case + '/' + role + ' bundle'
        cases[case] = {'run_id': reg['run_id'], 'registration_sha256': sha,
                       'launch_manifest_audit_registration_pins_match': True,
                       'all_role_manifests_match_actual_registry_binaries': True}
    return {'locked_inputs': len(lock['files']), 'locked_input_mismatches': mismatches,
            'source_bundle_entries_checked': len(bundle['files']), 'roles': role_checks,
            'driver_tool_sha256': registry['driver_tool_sha256'], 'cases': cases}


def load_auditor():
    spec = importlib.util.spec_from_file_location('batch56_audit_review', P / 'audit_diagnostic_v2.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def replay(case, label='baseline', probe=None):
    mod = load_auditor()
    out = HERE / 'evidence' / 'auditor_replays' / label
    (out / 'postrun').mkdir(parents=True, exist_ok=True)
    mod.D = out
    original_lines, original_read = mod.lines, mod.read
    changes = []

    def lines(p, *args, **kwargs):
        rows, dropped = original_lines(p, *args, **kwargs)
        rows = copy.deepcopy(rows)
        p = Path(p)
        if probe == 'W1_expired_lease' and p.parent.name == 'regulator':
            for row in rows:
                if row['type'] == 'worker_unusable_transition':
                    row['capability_last_valid_commit_ns'] = row['check_ns'] - row['capability_timeout_ns'] - 1
                    changes.append('lease age changed to timeout + 1 ns')
        if probe == 'W3_zero_delivery_delay' and p.parent.name == 'worker':
            for row in rows:
                if row['type'] == 'candidate_publish_result':
                    row['publish_start_ns'] = row['solve_end_ns']
                    row['publish_end_ns'] = row['solve_end_ns']
                    changes.append('delivery delay changed to 0 ns')
        if probe == 'W4_active_not_cleared' and p.parent.name == 'worker':
            w = mod.by_type(rows)
            jid = w['diagnostic_candidate_dropped'][0]['job_id']
            candidate = next(r for r in w['candidate'] if r['job']['job_id'] == jid)
            later = min(r['receive_ns'] for r in w['job_received'] if r['job']['job_id'] > jid)
            for row in w['capability_publish_attempt']:
                if candidate['publish_start_ns'] <= row['snapshot_ns'] < later:
                    row['payload']['active_job'] = jid
                    changes.append('idle-window capability active_job changed to dropped Job')
        return rows, dropped

    def read_for_probe(p):
        value = original_read(p)
        if probe == 'W4_wrong_manifest_binary' and Path(p).parent.name == 'worker' and Path(p).name == 'manifest.json':
            value = copy.deepcopy(value)
            value['binary_sha256'] = '0' * 64
            changes.append('Worker manifest binary SHA changed to all zeros')
        return value

    mod.lines = lines
    mod.read = read_for_probe
    old_argv = sys.argv
    sys.argv = ['audit_diagnostic_v2.py', '--case', case, '--registration',
                str(P / 'implementation' / (case + '_registration_v1.json'))]
    stream = io.StringIO()
    try:
        with contextlib.redirect_stdout(stream):
            mod.main()
        result = {'case': case, 'probe': probe, 'auditor_passed': True, 'stdout': stream.getvalue()}
    except Exception as exc:
        result = {'case': case, 'probe': probe, 'auditor_passed': False,
                  'exception': type(exc).__name__, 'message': str(exc)}
    finally:
        sys.argv = old_argv
    result['input_changes'] = changes
    if probe:
        assert changes, 'probe did not mutate its intended input'
    return result


def actual_case_review():
    mod = load_auditor()
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    results = {}
    for case in ('W1', 'W3', 'W4'):
        run = P / 'runs' / (case + '_05')
        worker, _ = mod.lines(run / 'worker/source.jsonl')
        regulator, _ = mod.lines(run / 'regulator/source.jsonl')
        w, r = mod.by_type(worker), mod.by_type(regulator)
        value = {'run': str(run), 'candidate_count': len(w['candidate']),
                 'published_count': len(w['candidate_publish_result']),
                 'dropped_count': len(w['diagnostic_candidate_dropped']),
                 'transitions': [x['reason'] for x in r['worker_unusable_transition']]}
        c = read(P / 'implementation/p1_execution_contract_v4.json')
        if case == 'W1':
            t = r['worker_unusable_transition'][0]
            age = t['check_ns'] - t['capability_last_valid_commit_ns']
            assert 0 <= age < c['worker_capability_receipt_timeout_ns']
            assert t['reason'] == 'active_watchdog'
            entered = w['diagnostic_v2_pre_native_enter'][0]['start_ns']
            released = w['diagnostic_v2_pre_native_release'][0]['released_ns']
            within = [x for x in w['capability_publish_attempt'] if entered <= x['snapshot_ns'] <= released]
            value.update(lease_age_at_watchdog_ns=age,
                         total_capability_attempts=len(w['capability_publish_attempt']),
                         capability_attempts_inside_stall=len(within),
                         stall_duration_ns=released - entered)
        if case == 'W3':
            pub = {x['job_id']: x for x in w['candidate_publish_result']}
            delays = [pub[x['job']['job_id']]['publish_start_ns'] - x['solve_end_ns'] for x in w['candidate']]
            assert all(x >= 170000000 for x in delays)
            refused = [x for x in r['candidate_registration'] if not x['accepted_registration']]
            assert any(x['reason'] == 'late' for x in refused)
            value.update(delivery_delays_ns=delays,
                         refused_reasons=[x['reason'] for x in refused],
                         hold_decisions_available_for_mutation=sum(x['control_source'] == 'hold' and not x['accepted'] for x in r['decision']))
        if case == 'W4':
            jid = w['diagnostic_candidate_dropped'][0]['job_id']
            job = next(x['job'] for x in r['job'] if x['job']['job_id'] == jid)
            target = next(x for x in r['decision'] if x['tick'] == job['target_tick'])
            assert target['reason'] == 'no_candidate' and not target['accepted']
            assert all(x['job']['job_id'] != jid for x in r['candidate_registration'])
            recovery = [x for x in r['decision'] if x['tick'] > job['target_tick'] and x['reason'] != 'shutdown' and x['accepted']]
            assert recovery
            generated = next(x for x in w['candidate'] if x['job']['job_id'] == jid)
            next_receive = min(x['receive_ns'] for x in w['job_received'] if x['job']['job_id'] > jid)
            idle = [x['payload'] for x in w['capability_publish_attempt'] if generated['publish_start_ns'] <= x['snapshot_ns'] < next_receive]
            assert idle and all(x['active_job'] == 0 and x['completed_jobs'] >= 3 for x in idle)
            prior = max(x['activation_commit_ns'] for x in r['decision'] if x['tick'] < target['tick'] and x['accepted'])
            age = target['activation_commit_ns'] - prior
            assert 0 <= age <= c['hold_ns'] and target['control_source'] == 'hold'
            assert target['final_n'] == target['previous_n']
            value.update(dropped_job=jid, target_tick=target['tick'],
                         target_reason=target['reason'], hold_age_ns=age,
                         recovery_ticks=[x['tick'] for x in recovery],
                         idle_capability_frames=idle)
        dbpath = next((run / 'recorder/bag').glob('*.db3'))
        db = sqlite3.connect('file:' + str(dbpath) + '?mode=ro', uri=True)
        capid, typ = db.execute("select id,type from topics where name='/p1/worker_capability'").fetchone()
        cls = get_message(typ)
        stored = [mod.norm(deserialize_message(data, cls)) for (data,) in db.execute('select data from messages where topic_id=? order by id', (capid,))]
        db.close()
        assert collections.Counter(mod.canonical(x) for x in stored) == collections.Counter(mod.canonical(x['payload']) for x in w['capability_publish_attempt'])
        value['typed_capability_Source_Stored_equal'] = True
        results[case] = value
    return results


def main():
    identities = read(HERE / 'evidence/identity_review_v1.json')
    baseline = read(HERE / 'evidence/auditor_baseline_replays_v1.json')
    assert all(x['auditor_passed'] for x in baseline), baseline
    actual = actual_case_review()
    save('actual_case_recheck_v1.json', actual)
    probes = [replay('W1', 'probe_lease', 'W1_expired_lease'),
              replay('W3', 'probe_delay', 'W3_zero_delivery_delay'),
              replay('W4', 'probe_idle', 'W4_active_not_cleared'),
              replay('W4', 'probe_identity', 'W4_wrong_manifest_binary')]
    save('auditor_private_input_probes_v1.json', {
        'method': 'same auditor logic; only selected input values altered in memory; original files unchanged',
        'probes': probes})
    print(json.dumps({'locked_inputs': identities['locked_inputs'],
                      'locked_mismatches': len(identities['locked_input_mismatches']),
                      'baseline_auditor_replays_passed': sum(x['auditor_passed'] for x in baseline),
                      'actual_cases_rechecked': list(actual),
                      'probes_accepted_by_original_auditor': [x['probe'] for x in probes if x['auditor_passed']],
                      'original_runtime_started': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
