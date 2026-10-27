#!/usr/bin/env python3
"""One finite T2 scenario run orchestrator (S2 freeze, batch 71).

Ordinary scope + frozen v3 contract + NONFAULT four roles: no diagnostic hook
exists anywhere in this run. The only T2 capability is the registration-pinned
action table. This Driver observes the frozen trigger phases in the role
Sources, writes create-only commands into the registered directory, and the
existing Fixture writers execute them. Executed receipts stay in the Fixture's
own Source stream; the single driver_shutdown_request is executed by this
Driver itself and recorded in driver_events, never in the Fixture-polled
directory. Receipts are accounted separately from Regulator state rows and are
correlated by action id, Job binding and monotonic time — the test flush pad
is never an acknowledgement.

Batch 71 freezes this interface; no owned run is executed by that batch."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
A = Path(__file__).resolve().parent
sys.path.insert(0, str(A))
import t2_action_contract as t2
from w2_runtime_contract import registration_preflight_t2
from owned_m4_diagnostic_driver_v1 import encoded, digest, pin, read, publish, process, peer_pin, SourceCursor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--registration', type=Path, required=True)
    args = parser.parse_args()
    reg = read(args.registration)
    config, registry, table = registration_preflight_t2(reg, Path(__file__).resolve())
    case = reg['case']
    run = reg['run_id']
    out = Path(reg['output'])
    out.mkdir()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    begin = time.monotonic()
    deadline = begin + reg['max_seconds']
    children = {}
    streams = []
    journal = (out / 'driver_events.jsonl').open('xb')

    def event(kind, **values):
        journal.write(encoded({'type': kind, 'checked_ns': time.monotonic_ns(), **values}))
        journal.flush()

    manifest = {**process(os.getpid()), 'schema_version': 'p1-owned-role-v1', 'role': 'driver', 'run_id': run,
                'boot_id': boot, 'contract_sha256': t2.V3_CONTRACT_SHA,
                'tool_path': str(Path(__file__).resolve()), 'tool_sha256': pin(__file__)['sha256'],
                'source_bundle_sha256': registry['driver_tool_sha256'],
                'effective_parameters_sha256': digest(encoded(reg)),
                'effective_parameters_immutable': True, 'execute_qualified': False,
                'physical_release_qualified': False, 'created_steady_ns': time.monotonic_ns(),
                'registry_sha256': reg['registry_sha256'],
                'registration_sha256': pin(args.registration)['sha256'],
                'm4_release_scope': t2.ORDINARY_SCOPE}
    publish(out / 'driver_manifest.json', manifest)
    dpin = peer_pin(out / 'driver_manifest.json', manifest)
    publish(out / 'driver_pins.json', dpin)

    def check_time():
        assert time.monotonic() < deadline, 'registered Driver budget expired'

    def spawn(role, argv):
        check_time()
        root = out / role
        root.mkdir(exist_ok=True)
        stdout = (root / 'stdout.log').open('xb')
        stderr = (root / 'stderr.log').open('xb')
        streams.extend([stdout, stderr])
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                 start_new_session=True, env=os.environ.copy(), close_fds=True)
        pidfd = os.pidfd_open(child.pid)
        actual = process(child.pid)
        assert actual['pgid'] == actual['sid'] == child.pid
        children[role] = {'process': child, 'pidfd': pidfd, 'start_ticks': actual['process_start_ticks'], 'argv': argv}
        publish(root / 'spawn.json', {'role': role, 'pid': child.pid,
                                      'process_start_ticks': actual['process_start_ticks'], 'argv': argv,
                                      'boot_id': boot, 'inherited_fds': []})
        event('role_spawned', role=role, **actual)

    def native(binary, parameters):
        argv = [binary, '--ros-args']
        for key, value in parameters.items():
            argv += ['-p', key + ':=' + str(value)]
        return argv

    def wait_file(path, seconds=10):
        until = min(deadline, time.monotonic() + seconds)
        while time.monotonic() < until:
            for role, c in children.items():
                if c['process'].poll() is not None:
                    raise RuntimeError(role + ' exited early: ' + str(c['process'].returncode))
            if path.is_file():
                return read(path)
            time.sleep(.01)
        raise TimeoutError('waiting for ' + str(path))

    def authenticate(role, path, parameters=None):
        m = wait_file(path)
        actual = process(children[role]['process'].pid)
        record = registry['roles'][role]
        assert m['schema_version'] == 'p1-owned-role-v1' and m['run_id'] == run and m['boot_id'] == boot \
            and m['contract_sha256'] == t2.V3_CONTRACT_SHA
        for key in ['pid', 'process_start_ticks', 'exe', 'binary_sha256', 'argv', 'pgid', 'sid']:
            assert m[key] == actual[key], (role, key)
        assert actual['binary_sha256'] == record['binary_sha256'] \
            and m['source_bundle_sha256'] == record['source_bundle']['sha256']
        assert m['effective_parameters_immutable'] is True and m['execute_qualified'] is False \
            and m['physical_release_qualified'] is False
        canonical = {k: {'type': v['type'], 'canonical_value': v['canonical_value']}
                     for k, v in m['effective_parameters'].items()}
        assert digest(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()) \
            == m['effective_parameters_sha256']
        assert m['effective_parameters']['use_sim_time']['value'] is False
        for key, value in (parameters or {}).items():
            row = m['effective_parameters'][key]
            assert row['value'] == value and type(row['value']) is type(value), (role, key, row, value)
        if role != 'recorder':
            assert m['contract_configuration'] == config
        if 'source_fd' in m:
            sf = m['source_fd']
            st = os.stat('/proc/' + str(actual['pid']) + '/fd/' + str(sf['fd']))
            assert st.st_ino == sf['inode'] and st.st_dev == sf['device'] and sf['append'] is True
            assert os.readlink('/proc/' + str(actual['pid']) + '/fd/' + str(sf['fd'])) == sf['path']
        for ep in m['endpoints']:
            assert len(ep['gid']) == 16 and any(ep['gid']) \
                and all(type(n) is int and 0 <= n <= 255 for n in ep['gid'])
        event('actual_role_authenticated', role=role, manifest=peer_pin(path, m),
              parameters=m['effective_parameters'], endpoints=m['endpoints'])
        return m, peer_pin(path, m)

    def stop(role):
        child = children[role]['process']
        rows = []
        first = config['worker_grace_ns'] / 1e9 if role == 'worker' else config['shutdown_grace_ns'] / 1e9
        for sig, budget in [(signal.SIGINT, first), (signal.SIGTERM, config['term_grace_ns'] / 1e9),
                            (signal.SIGKILL, config['kill_postcheck_ns'] / 1e9)]:
            if child.poll() is not None:
                break
            actual = process(child.pid)
            assert actual['process_start_ticks'] == children[role]['start_ticks'] and actual['pgid'] == child.pid
            os.killpg(child.pid, sig)
            rows.append({'signal': sig.name, 'sent_ns': time.monotonic_ns(), 'wait_seconds': budget})
            try:
                child.wait(timeout=budget)
            except subprocess.TimeoutExpired:
                pass
        rc = child.poll()
        try:
            os.killpg(child.pid, 0)
            empty = False
        except ProcessLookupError:
            empty = True
        row = {'role': role, 'pid': child.pid, 'returncode': rc, 'signals': rows,
               'group_empty': empty, 'finished_ns': time.monotonic_ns()}
        event('owned_role_closed', **row)
        return row

    command_dir = out / 't2_commands'
    command_dir.mkdir()
    result = {'schema': 'M4-t2-scenario-driver-result-v1', 'run_id': run, 'case': case, 'passed': False,
              'M4_qualified': False, 'P1_qualified': False, 'production_physical_release_enabled': False,
              'isolated_scope': t2.ORDINARY_SCOPE, 'research_conclusion': False,
              'executed_owned_run_in_batch71': False}
    commands_sent = []
    receipts = []
    regulator_rows_all = []
    try:
        for role in ['fixture', 'worker', 'recorder', 'regulator']:
            (out / role).mkdir()
        common = {'run_id': run, 'contract_hash': t2.V3_CONTRACT_SHA, 'contract_file': str(reg['contract']),
                  'm4_release_scope': t2.ORDINARY_SCOPE}
        fixture_params = t2.fixture_action_parameters(reg, command_dir, reg['action_table'])
        fp = {**common, 'output_dir': str(out / 'fixture'), 'start_file': str(out / 'fixture_start.json'),
              'topics_file': str(reg['topics']), 'topics_sha256': reg['topics_sha256'],
              'controlled_phase_mode': 'C', 'reference_speed_m_s': .05,
              'driver_pins_file': str(out / 'driver_pins.json'),
              'driver_pins_sha256': pin(out / 'driver_pins.json')['sha256'], **fixture_params}
        spawn('fixture', native(registry['roles']['fixture']['binary'], fp))
        fm, fpin = authenticate('fixture', out / 'fixture/owned_manifest.json', fp)
        assert fm['t2_armed'] is True and fm['t2_case'] == case \
            and fm['t2_action_table_sha256'] == reg['action_table_sha256'], 'Fixture action channel not armed'
        wp = {**common, 'driver_pins_file': str(out / 'driver_pins.json'),
              'driver_pins_sha256': pin(out / 'driver_pins.json')['sha256'],
              'source_file': str(out / 'worker/source.jsonl'),
              'owned_manifest_file': str(out / 'worker/manifest.json'),
              'test_delay_ms': 0, 'test_native_block_ms': 0, 'diagnostic_v2_policy': 'none',
              'diagnostic_v2_block_ms': 0, 'diagnostic_drop_after_candidates': -1}
        spawn('worker', native(registry['roles']['worker']['binary'], wp))
        wm, wpin = authenticate('worker', out / 'worker/manifest.json', wp)
        rp = out / 'recorder'
        rv = [registry['roles']['recorder']['binary'], '--run-id', run, '--contract', str(reg['contract']),
              '--contract-sha256', t2.V3_CONTRACT_SHA, '--topics', str(reg['topics']),
              '--topics-sha256', reg['topics_sha256'], '--manifest', str(rp / 'manifest.json'),
              '--terminal', str(rp / 'terminal.json'), '--bag', str(rp / 'bag'),
              '--storage-id', 'sqlite3', '--prepare-budget-ms', '10000']
        spawn('recorder', rv)
        actual_recorder = process(children['recorder']['process'].pid)
        assert actual_recorder['binary_sha256'] == registry['roles']['recorder']['binary_sha256']
        rprocess = {**actual_recorder, 'schema': 'M4-recorder-owned-process-only/v1', 'role': 'recorder',
                    'run_id': run, 'boot_id': boot, 'contract_sha256': t2.V3_CONTRACT_SHA,
                    'source_bundle_sha256': registry['roles']['recorder']['source_bundle']['sha256'],
                    'manifest_path': str(rp / 'manifest.json'), 'topics_sha256': reg['topics_sha256'],
                    'process_only': True, 'recording_ready': False}
        publish(out / 'recorder_process_pin.json', rprocess)
        publish(out / 'peer_pins.json', {'schema': 'M4-owned-role-bootstrap-pins-v1', 'driver': dpin,
                                         'worker': wpin, 'fixture': fpin, 'recorder_process': rprocess,
                                         'topics_sha256': reg['topics_sha256']})
        cp = {**common, 'mode': 'execute', 'output_dir': str(out / 'regulator'),
              'peer_pins_file': str(out / 'peer_pins.json'),
              'peer_pins_sha256': pin(out / 'peer_pins.json')['sha256'],
              'diagnostic_source_file': registry['regulator_source'],
              'diagnostic_source_sha256': registry['regulator_source_sha256'],
              'diagnostic_binary_sha256': registry['roles']['regulator']['binary_sha256'],
              'worker_binary_sha256': registry['roles']['worker']['binary_sha256'],
              'witness_worker_instance': wm['worker_instance'],
              'source_file': str(out / 'regulator/source.jsonl'),
              'witness_file': str(out / 'regulator/witness.json'), 'witness_enabled': True,
              }
        spawn('regulator', native(registry['roles']['regulator']['binary'], cp))
        cm, cpin = authenticate('regulator', out / 'regulator/manifest.json', cp)
        rm, rpin = authenticate('recorder', rp / 'manifest.json')
        publish(out / 'fixture_start.json',
                {'schema': 'M4-owned-inputs-start-v2', 'run_id': run, 'boot_id': boot,
                 'contract_sha256': t2.V3_CONTRACT_SHA, 'scope': t2.ORDINARY_SCOPE,
                 'driver_manifest_sha256': dpin['manifest_sha256'], 'owner': cpin,
                 'issued_ns': time.monotonic_ns(), 'sequence': 1, 't2_case': case,
                 't2_action_table_sha256': reg['action_table_sha256'],
                 't2_command_dir': str(command_dir)})
        ready = wait_file(out / 'regulator/ready.json')
        ctx = ready['context']
        assert ctx['regulator_manifest_sha256'] == cpin['manifest_sha256'] \
            and ctx['freeze_evidence_sha256'] == config['freeze_evidence_sha256']
        grant_file = out / 'regulator/grant.json'
        publish(grant_file, {'schema': 'M4-owned-execute-grant-v1', 'scope': t2.ORDINARY_SCOPE, 'run_id': run,
                             'boot_id': boot, 'contract_sha256': t2.V3_CONTRACT_SHA,
                             'index_sha256': config['freeze_evidence_sha256'], 'context': ctx,
                             'version': ready['version'],
                             'ready_sha256': pin(out / 'regulator/ready.json')['sha256'],
                             'driver_manifest_sha256': dpin['manifest_sha256'],
                             'issued_ns': time.monotonic_ns(), 'sequence': 1})
        prepared = wait_file(out / 'regulator/prepared.json')
        assert prepared['grant_sha256'] == pin(grant_file)['sha256']
        event('t2_actual_output_authorized', prepared=prepared)
        # ── frozen trigger observation → create-only commands → receipts ──
        cursor = SourceCursor(out / 'regulator/source.jsonl')
        worker_cursor = SourceCursor(out / 'worker/source.jsonl')
        fixture_cursor = SourceCursor(out / 'fixture/nominal_steps.jsonl')
        grant_ns = time.monotonic_ns()
        drain_deadline = None  # post-receipt healthy-business drain window
        jobs_by_id = {}
        received_jobs = {}
        ready_jobs = {}
        active_jobs = {}
        generated_jobs = set()
        next_action = 0
        actions = table['actions']
        shutdown_fired = False
        while time.monotonic() < deadline and not shutdown_fired:
            check_time()
            for role, c in children.items():
                if c['process'].poll() is not None:
                    raise RuntimeError(role + ' exited early: ' + str(c['process'].returncode))
            for row in worker_cursor.poll():
                wt = row.get('type')
                if wt == 'job_received':
                    received_jobs[row.get('job_id')] = {'observed_ns': time.monotonic_ns(),
                                                        'job': jobs_by_id.get(row.get('job_id'))}
                elif wt in ('capability_publish_attempt', 'capability_publish_result'):
                    payload = row.get('payload') or {}
                    active = payload.get('active_job')
                    if type(active) is int and active > 0 and active not in generated_jobs:
                        active_jobs[active] = {'observed_ns': time.monotonic_ns(),
                                               'job': jobs_by_id.get(active)}
                elif wt == 'candidate':
                    jid = (row.get('job') or {}).get('job_id')
                    if jid is not None:
                        generated_jobs.add(jid)
                        active_jobs.pop(jid, None)
            for row in cursor.poll():
                regulator_rows_all.append(row)
                rt = row.get('type')
                if rt == 'job':
                    jid = (row.get('job') or {}).get('job_id')
                    if jid is not None:
                        jobs_by_id[jid] = row.get('job')
                elif rt == 'candidate_registration' and row.get('accepted_registration') is True:
                    jid = (row.get('job') or {}).get('job_id')
                    if jid is not None:
                        ready_jobs[jid] = {'observed_ns': row.get('ready_commit_ns') or time.monotonic_ns(),
                                           'job': row.get('job')}
            for row in fixture_cursor.poll():
                if row.get('type') == t2.RECEIPT_TYPE:
                    receipts.append(row)
            if next_action >= len(actions):
                if shutdown_fired:
                    break
                if all(r.get('action_id') in {a['id'] for a in actions} for r in receipts):
                    global drain_deadline
                    if drain_deadline is None:
                        drain_deadline = time.monotonic() + 5.0
                    if time.monotonic() >= drain_deadline:
                        break
                    continue
                if time.monotonic() - grant_ns > 20:
                    break
                continue
            entry = actions[next_action]
            trig = entry['trigger']
            phase, delay_ns = trig['phase'], trig['delay_ms'] * 1000000
            evidence = None
            if phase == 'after_grant_ms':
                evidence = {'phase': phase, 'job': None, 'observed_ns': grant_ns, 'source_role': 'driver'}
            elif phase == 'job_received':
                evidence = received_jobs.get(trig['job_id'])
            elif phase == 'solve_active':
                evidence = active_jobs.get(trig['job_id'])
            elif phase == 'ready_window':
                evidence = ready_jobs.get(trig['job_id'])
            if evidence is None or time.monotonic_ns() < evidence['observed_ns'] + delay_ns:
                continue
            command = {'schema': t2.COMMAND_SCHEMA, 'run_id': run,
                       'contract_sha256': t2.V3_CONTRACT_SHA, 'action_id': entry['id'],
                       'sequence': len(commands_sent) + 1, 'trigger': evidence}
            t2.validate_command(command, table, [c['action_id'] for c in commands_sent])
            if entry['action'] == 'driver_shutdown_request':
                shutdown_fired = True
                receipts.append({'type': t2.RECEIPT_TYPE, 'action_id': entry['id'],
                                 'command_sha256': digest(encoded(command)), 'trigger': evidence,
                                 'executed_ns': time.monotonic_ns(), 'executor': 'driver'})
                event('t2_driver_action_executed', action_id=entry['id'], command=command)
            else:
                path = command_dir / ('%03d_%s.json' % (command['sequence'], entry['id']))
                publish(path, command)
                commands_sent.append(command)
                event('t2_action_commanded', action_id=entry['id'], command=command, path=str(path))
            next_action += 1
        result['t2_commands_sent'] = [c['action_id'] for c in commands_sent]
        result['t2_shutdown_fired'] = shutdown_fired
    except Exception as error:
        result.update(error=repr(error), traceback=__import__('traceback').format_exc())
        event('driver_failure', error=repr(error))
    finally:
        closed = []
        for role in ['regulator', 'fixture', 'worker', 'recorder']:
            if role in children:
                if role == 'recorder':
                    time.sleep(.2)
                try:
                    closed.append(stop(role))
                except Exception as error:
                    closed.append({'role': role, 'error': repr(error), 'group_empty': False})
                    event('close_failure', role=role, error=repr(error))
        for c in children.values():
            os.close(c['pidfd'])
        result['closed_roles'] = closed
        result['elapsed_seconds'] = time.monotonic() - begin
        by_role = {r['role']: r for r in closed}

        def rc_is(role, value):
            return by_role.get(role, {}).get('returncode') == value
        # Ordinary T2 close: every role exits 0 through the registered SIGINT
        # ladder (a scenario may also stop the regulator itself via the
        # shutdown request, leaving its signal list empty).
        common_ok = bool(rc_is('regulator', 0) and rc_is('worker', 0) and rc_is('fixture', 0)
                         and rc_is('recorder', 0) and len(closed) == 4
                         and all(r.get('group_empty') for r in closed)
                         and [s['signal'] for s in by_role.get('regulator', {}).get('signals', [])] in ([], ['SIGINT']))
        try:
            accounting = t2.check_receipts(table, receipts, regulator_rows_all)
            result['t2_receipt_checks'] = accounting
            receipts_ok = accounting['receipts_complete'] is True \
                and accounting['regulator_rows_separate_stream'] is True
        except Exception as error:
            result['t2_receipt_checks'] = {'error': repr(error)}
            receipts_ok = False
        result['passed'] = bool(result.get('error') is None and common_ok and receipts_ok
                                and result.get('t2_shutdown_fired') is (table['actions'][-1]['action'] == 'driver_shutdown_request'))
        publish(out / 'driver_result.json', result)
        journal.close()
        for f in streams:
            f.close()
    print(json.dumps({'passed': result['passed'], 'error': result.get('error'),
                      'elapsed_seconds': result['elapsed_seconds'], 'output': str(out)}))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
