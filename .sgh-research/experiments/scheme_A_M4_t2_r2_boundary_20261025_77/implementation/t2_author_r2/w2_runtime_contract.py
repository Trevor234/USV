"""Shared registration and live-runtime checks. No ROS initialisation.

Batch 71 (S2): adds the T2 scenario-family entry preflight and the
normal-scope rejection of any action-table capability. The W1-W4
preflight below is byte-preserved apart from that guard."""
from pathlib import Path
import hashlib
import json
import os
import time
import t2_action_contract as t2

SCOPE = 'M4_owned_diagnostic_worker_only_v1'
CONTRACT_SHA = '3a8451d5172423adbef955d78c8550d67bbeec4582a80bd9ba69028b867b9f06'
INDEX_MARKER = 'd1a9f0e2b7c4a8536e0f2b9d4c7a1e5836b0d9f2c4a7e1b8369d0c5f2a8e4b71'


def require(value, message):
    if not value:
        raise AssertionError(message)


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path):
    return json.loads(Path(path).read_bytes())


def validate_w2(reg, config=None):
    w = reg.get('w2_release')
    require(isinstance(w, dict), 'W2 registration must declare w2_release')
    for name in ['job_id', 'ordinal', 'nonce', 'wait_budget_ns', 'ticks_before_release']:
        require(type(w.get(name)) is int, 'W2 integer required: ' + name)
    require(w['job_id'] == 2 and w['ordinal'] == 1, 'This W2 profile binds Job2/ordinal1')
    require(0 < w['nonce'] <= 2147483647, 'W2 nonce outside shared positive int32 domain')
    require(0 < w['wait_budget_ns'] <= 2000000000, 'W2 wait budget outside finite bound')
    require(w['ticks_before_release'] >= 2, 'W2 requires at least two complete ticks')
    e = reg.get('expected', {})
    require(type(e.get('w2_exit_codes', {}).get('worker')) is int, 'W2 worker exit code required')
    require(e.get('w2_worker_signals') == ['SIGINT'], 'W2 requires the registered single Worker SIGINT')
    require(e.get('w2_isolation_reason') == 'fatal_capability', 'Explicit W2 isolation reason required')
    require(e.get('w2_terminal_reasons') == ['w2_boundary_expired'], 'Explicit target terminal reason required')
    require(e.get('exit_codes') == {'worker': 2, 'regulator': 0, 'fixture': 0, 'recorder': 0},
            'W2 role exit codes differ from terminal-isolation profile')
    require(e['w2_exit_codes']['worker'] == e['exit_codes']['worker'], 'Duplicate worker exit codes differ')
    require(e.get('signals') == {'worker': ['SIGINT'], 'regulator': [], 'fixture': ['SIGINT'], 'recorder': ['SIGINT']},
            'W2 close-signal clauses disagree')
    for name, expected in [('target_job_native_calls', 0), ('target_job_candidate_published', False),
                           ('target_job_candidate_registered', False), ('backend_terminal', True),
                           ('active_job_cleared', True), ('pending_discard_required', True)]:
        require(type(e.get(name)) is type(expected) and e[name] == expected, 'W2 terminal clause: ' + name)
    if config is not None:
        d, p, c = reg.get('two_deadlines', {}), reg.get('release_preconditions', {}), reg.get('channel', {})
        require(d.get('gate_wait_budget_ns') == w['wait_budget_ns'], 'Gate budget policy differs from parameter')
        require(d.get('job_deadline_ns_after_origin') == config['deadline_ns'], 'Job deadline policy differs from contract')
        require(d.get('gate_window_extends_job_deadline') is False, 'Gate must not extend Job deadline')
        require(p.get('required_complete_ticks_after_entry') == w['ticks_before_release'], 'Tick policies disagree')
        require(p.get('capability_lease_ns') == config['worker_capability_receipt_timeout_ns'], 'Lease policies disagree')
        require(p.get('active_watchdog_ns') == config['active_watchdog_ns'], 'Watchdog policies disagree')
        require(p.get('release_must_precede_active_watchdog') is True, 'Release-before-watchdog clause required')
        require(c.get('kind') == 'private_pipe' and c.get('driver_holds') == 'write_end'
                and c.get('worker_inherits') == 'read_end' and c.get('siblings_inherit') == 'none', 'Private pipe roles disagree')
        require(c.get('static_registration_predicts_inode') is False, 'Pipe inode must be fixed at runtime')
    return w


def registration_preflight(reg, driver_path, environment=None):
    """The same read-only preflight is used by the real Driver and offline tool."""
    env = os.environ if environment is None else environment
    require(__debug__, 'Driver must run with Python assertions enabled')
    require(reg.get('schema') == 'M4-owned-diagnostic-run-v1' and reg.get('scope') == SCOPE, 'Registration schema/scope')
    require(reg.get('production_physical_release_enabled') is False, 'Ordinary physical release must stay off')
    require(reg.get('case') in ['W1-work-stall-watchdog', 'W3-result-delivery-delay', 'W4-result-delivery-drop', 'W2-native-boundary-hold'], 'Unknown diagnostic case')
    t2.require_normal_scope_unarmed(reg)
    require(reg.get('domain_id') == 120 and env.get('ROS_DOMAIN_ID') == '120'
            and env.get('ROS_LOCALHOST_ONLY') == '1' and env.get('RMW_IMPLEMENTATION') == 'rmw_fastrtps_cpp', 'Exact isolated DDS environment required')
    require(reg.get('max_seconds') == 45 and reg.get('automatic_retries') == 0, 'Finite one-attempt budget required')
    require(reg.get('fault_injection_enabled') is True, 'Diagnostic permission required')
    require(reg.get('contract_sha256') == CONTRACT_SHA and reg.get('index_sha256') == INDEX_MARKER, 'Contract/evidence marker mismatch')
    require(pin(reg['contract'])['sha256'] == CONTRACT_SHA, 'Actual contract bytes mismatch')
    config = read(reg['contract'])
    require(config['schema'] == 'p1-execution-contract-v4' and config['qualification'] == 'execution_diagnostic_only'
            and config['fault_injection_enabled'] is True and config['pending_final_calibration'] == [], 'Diagnostic contract shape')
    require(pin(reg['registry'])['sha256'] == reg['registry_sha256'], 'Registry pin mismatch')
    registry = read(reg['registry'])
    require(registry['scope'] == SCOPE and registry['driver_tool_sha256'] == pin(driver_path)['sha256'], 'Driver tool identity mismatch')
    require(Path(registry['driver']).resolve() == Path(driver_path).resolve(), 'Driver path mismatch')
    require(set(registry['roles']) == {'worker', 'regulator', 'fixture', 'recorder'}, 'Four exact roles required')
    for role, row in registry['roles'].items():
        bp = row['source_bundle']
        require(pin(bp['path'])['sha256'] == bp['sha256'], role + ' bundle mismatch')
        files = read(bp['path'])['files']
        for f in files.values() if isinstance(files, dict) else files:
            require(Path(f['path']).is_absolute(), role + ' source path must be absolute')
            require(pin(f['path']) == {'bytes': f['bytes'], 'sha256': f['sha256']}, role + ' source bytes mismatch: ' + f['path'])
        require(pin(row['binary'])['sha256'] == row['binary_sha256'], role + ' ELF mismatch')
        with Path(row['binary']).open('rb') as f:
            require(f.read(4) == b'\x7fELF', role + ' is not an ELF')
    require(pin(reg['topics'])['sha256'] == reg['topics_sha256'], 'Topics pin mismatch')
    output = Path(reg['output'])
    require(output.is_absolute() and output.parent == Path(driver_path).resolve().parent.parent / 'runs', 'Output outside registered runs directory')
    require(output.parent.is_dir() and not output.exists(), 'Output must be a new run under an existing parent')
    if reg['case'] == 'W2-native-boundary-hold':
        validate_w2(reg, config)
        require(set(registry.get('acados_runtime', {})) == {'libacados.so', 'libhpipm.so', 'libblasfeo.so'}, 'Three runtime library pins required')
        for name, row in registry['acados_runtime'].items():
            require(Path(row['path']).is_absolute(), name + ' resolved runtime path required')
            require(pin(row['path']) == {'bytes': row['bytes'], 'sha256': row['sha256']}, name + ' runtime file mismatch')
        ap = reg.get('audit_tool', {})
        require(pin(ap['path'])['sha256'] == ap['sha256'], 'W2 independent audit tool mismatch')
    return config, registry


def process_start(pid):
    raw = Path('/proc/%d/stat' % pid).read_text()
    fields = raw[raw.rfind(')') + 1:].split()
    require(fields[0] not in ['Z', 'X'], 'Runtime process is not live')
    return int(fields[19])


def verify_runtime_maps(pid, records, expected_start):
    """Authenticate mapped inodes and bytes before granting business execution."""
    require(process_start(pid) == expected_start, 'Runtime process identity changed')
    text = Path('/proc/%d/maps' % pid).read_text()
    checked = []
    for name, expected in records.items():
        candidates = {}
        for line in text.splitlines():
            fields = line.split(None, 5)
            if len(fields) != 6:
                continue
            path = fields[5]
            base = Path(path.removesuffix(' (deleted)')).name
            if base != name and not base.startswith(name + '.'):
                continue
            require(not path.endswith(' (deleted)'), name + ' mapping was deleted')
            candidates.setdefault(path, []).append(fields)
        require(len(candidates) == 1, name + ' must map one exact object')
        path, mappings = next(iter(candidates.items()))
        require(Path(path).resolve() == Path(expected['path']).resolve(), name + ' mapped path mismatch')
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            for fields in mappings:
                major, minor = [int(v, 16) for v in fields[3].split(':')]
                require(before.st_ino == int(fields[4]) and os.major(before.st_dev) == major
                        and os.minor(before.st_dev) == minor, name + ' mapped inode differs from current path')
            h = hashlib.sha256()
            while True:
                block = os.read(fd, 1024 * 1024)
                if not block: break
                h.update(block)
            after = os.fstat(fd)
            require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                    == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), name + ' changed while hashing')
            require(before.st_size == expected['bytes'] and h.hexdigest() == expected['sha256'], name + ' loaded bytes mismatch')
            checked.append({'library': name, 'path': path, 'device': before.st_dev,
                            'inode': before.st_ino, 'bytes': before.st_size,
                            'sha256': h.hexdigest(), 'maps_lines': [' '.join(f) for f in mappings]})
        finally:
            os.close(fd)
    require(process_start(pid) == expected_start, 'Runtime process replaced during map check')
    return {'checked': True, 'pid': pid, 'process_start_ticks': expected_start,
            'checked_ns': time.monotonic_ns(), 'maps_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'libraries': checked}


def complete_w2_ticks(entered_ns, decisions, pairs):
    if type(entered_ns) is not int:
        return []
    ticks = []
    for tick, d in decisions.items():
        pair = pairs.get(tick, {})
        start, end = d.get('start_ns'), d.get('end_ns')
        starts, ends = pair.get('starts', []), pair.get('ends', [])
        if (type(tick) is int and type(start) is int and type(end) is int
                and start >= entered_ns and end > start
                and d.get('reason') != 'shutdown' and pair.get('kind') != 'shutdown'
                and pair.get('sequence') == d.get('sequence')
                and pair.get('returned') == [True, True]
                and len(starts) == len(ends) == 2
                and all(type(v) is int for v in starts + ends)
                and min(starts) >= start and all(b >= a for a, b in zip(starts, ends))
                and not any(pair.get(k) for k in ['gap_exceeded', 'span_exceeded', 'rate_exceeded', 'command_invalid'])):
            ticks.append(tick)
    return sorted(ticks)


def w2_result_checks(reg, result, closed, observed):
    """Total function over incomplete observations; finalization never loses error."""
    w, e = reg.get('w2_release') or {}, reg.get('expected') or {}
    target, ordinal = w.get('job_id'), w.get('ordinal')
    r = result.get('w2_result') or {}
    r = r if isinstance(r, dict) else {}
    b = r.get('boundary') or {}
    b = b if isinstance(b, dict) else {}
    entry = result.get('w2_entered_row') or {}
    entry = entry if isinstance(entry, dict) else {}
    release = result.get('w2_release_record') or {}
    release = release if isinstance(release, dict) else {}
    job = result.get('w2_target_job') or {}
    job = job if isinstance(job, dict) else {}
    guard, deadline = b.get('guard_ns'), b.get('job_deadline_ns')
    began, received = b.get('entered_ns'), b.get('released_ns')
    ws, we = release.get('write_start_ns'), release.get('write_end_ns')
    times_valid = all(type(t) is int and t > 0 for t in [guard, deadline, began, received, ws, we, entry.get('entered_ns')])
    by_role = {row.get('role'): row for row in closed if isinstance(row, dict)}
    close_ok = len(closed) == 4 and set(by_role) == {'worker', 'regulator', 'fixture', 'recorder'}
    for role in ['worker', 'regulator', 'fixture', 'recorder']:
        row = by_role.get(role, {})
        signals = [s.get('signal') for s in row.get('signals', []) if isinstance(s, dict)]
        close_ok = close_ok and (row.get('returncode') == e.get('exit_codes', {}).get(role)
            and signals == e.get('signals', {}).get(role)
            and row.get('group_empty') is True and not row.get('error'))
    terminal = [row for row in observed.get('terminal_events', [])
                if row.get('job_id') == target and row.get('reason') in e.get('w2_terminal_reasons', ['w2_boundary_expired'])]
    transition = result.get('transition_ns')
    checks = {
        'no_driver_error': result.get('error') is None,
        'four_roles_closed_exactly': bool(close_ok),
        'observed_target': result.get('W2_observed') is True and result.get('w2_boundary_entered') is True
            and entry.get('job_id') == target and entry.get('ordinal') == ordinal,
        'one_written_release': result.get('w2_release_sent') is True and release.get('written_bytes') == 44
            and release.get('job_id') == target and release.get('ordinal') == ordinal
            and release.get('nonce') == w.get('nonce'),
        'verified_release': b.get('released') is True and b.get('gate_outcome') == 'released',
        'target_boundary_identity': r.get('job_id') == b.get('job_id') == target
            and r.get('ordinal') == b.get('ordinal') == ordinal,
        'expired_original_job': times_valid and guard > deadline and b.get('past_deadline_ns') == guard - deadline
            and deadline == entry.get('job_deadline_ns') == job.get('deadline_ns')
            and r.get('disposition') == b.get('disposition') == 'expired',
        'causal_release': times_valid and began <= entry.get('entered_ns', -1) <= ws <= received <= guard and we >= ws,
        'release_before_watchdog': times_valid and we - began < reg.get('release_preconditions', {}).get('active_watchdog_ns', 0),
        'no_target_C_call': r.get('actual_native_invoked') is False and b.get('actual_native_invoked') is False
            and b.get('ordinal_at_call') == 0,
        'target_policy_C_count': observed.get('target_policy', {}).get('actual_C_solve_calls_this_job') == 0
            and observed.get('target_policy', {}).get('terminal') is True,
        'two_complete_ticks': len(set(result.get('w2_ticks_after_enter') or [])) >= w.get('ticks_before_release', 2),
        'heartbeat_renewed_while_held': result.get('w2_live_renewals', 0) >= 1,
        'no_watchdog': result.get('watchdog_ns') is None,
        'isolation_after_expiry': transition is None or (type(transition) is int and type(guard) is int
            and transition >= guard and result.get('transition_reason') == e.get('w2_isolation_reason')),
        'target_not_generated': target not in observed.get('candidate_rows', []),
        'target_not_published': target not in observed.get('worker_published_job_ids', set()),
        'target_not_registered': target not in observed.get('registered_job_ids', set()),
        'target_terminal': bool(terminal),
        'active_cleared': observed.get('active_cleared') is True,
        'pending_discarded': not e.get('pending_discard_required') or bool(observed.get('pending_discarded_job_ids')),
        'normal_prefix': result.get('accepted_pairs', 0) >= 1,
        'live_libraries_authenticated': result.get('runtime_libraries_verified') is True,
        'ramp_integrity': result.get('ramp_ok') is True,
    }
    return checks


def registration_preflight_t2(reg, driver_path, environment=None):
    """Entry admission for the frozen T2 scenario families (S2, batch 71).

    Ordinary scope + frozen v3 contract + nonfault four roles; the T2
    capability is ONLY the registration-pinned action table executed by the
    existing Fixture writers (and the single Driver shutdown request)."""
    env = os.environ if environment is None else environment
    require(__debug__, 'Driver must run with Python assertions enabled')
    require(reg.get('schema') == t2.REGISTRATION_SCHEMA and reg.get('scope') in (t2.ORDINARY_SCOPE, t2.T2_BOUNDARY_SCOPE), 'T2 registration schema/scope')
    require(reg.get('case') in t2.FAMILIES, 'Unknown T2 scenario family')
    require(reg.get('production_physical_release_enabled') is False, 'Ordinary physical release must stay off')
    boundary = reg.get('scope') == t2.T2_BOUNDARY_SCOPE
    require(boundary or reg.get('fault_injection_enabled') is False,
            'ordinary T2 stays nonfault; boundary T2 declares fault (v4 contract)')
    if boundary:
        require(reg.get('fault_injection_enabled') is True, 'boundary T2 uses the v4 contract')
        require(reg.get('case') == 'T2B-inflight-clear-replace', 'boundary scope is for T2-B only')
        w = reg.get('boundary_release')
        require(isinstance(w, dict) and w.get('job_id') == 2 and w.get('ordinal') == 1,
                'boundary binds Job2/ordinal1 for the minimal timely case')
        require(0 < w.get('wait_budget_ns', 0) <= 2000000000, 'boundary wait budget bounded')
    require(reg.get('domain_id') == 120 and env.get('ROS_DOMAIN_ID') == '120'
            and env.get('ROS_LOCALHOST_ONLY') == '1' and env.get('RMW_IMPLEMENTATION') == 'rmw_fastrtps_cpp', 'Exact isolated DDS environment required')
    require(reg.get('max_seconds') == 45 and reg.get('automatic_retries') == 0, 'Finite one-attempt budget required')
    if boundary:
        V4_SHA = '3a8451d5172423adbef955d78c8550d67bbeec4582a80bd9ba69028b867b9f06'
        require(reg.get('contract_sha256') == V4_SHA, 'boundary T2 uses the frozen v4 contract')
    else:
        require(reg.get('contract_sha256') == t2.V3_CONTRACT_SHA, 'ordinary T2 stays on the frozen v3 contract')
    require(pin(reg['contract'])['sha256'] == t2.V3_CONTRACT_SHA, 'Actual contract bytes mismatch')
    config = read(reg['contract'])
    if boundary:
        require(config['schema'] == 'p1-execution-contract-v4' and config['qualification'] == 'execution_diagnostic_only'
                and config['fault_injection_enabled'] is True, 'boundary T2 uses the diagnostic contract shape')
    else:
        require(config['schema'] == 'p1-execution-contract-v3' and config['qualification'] == 'execution_frozen'
                and config['fault_injection_enabled'] is False, 'Ordinary frozen contract shape')
    t2.verify_budgets_unchanged(config)
    require(pin(reg['action_table'])['sha256'] == reg['action_table_sha256'], 'Action table pin mismatch')
    table = read(reg['action_table'])
    t2.validate_table(table, {'run_id': reg['run_id'], 'case': reg['case'],
                              'contract_sha256': reg['contract_sha256']})
    require(table['case'] == reg['case'], 'Action table case binding')
    require(pin(reg['registry'])['sha256'] == reg['registry_sha256'], 'Registry pin mismatch')
    registry = read(reg['registry'])
    require(registry['scope'] in (t2.ORDINARY_SCOPE, t2.T2_BOUNDARY_SCOPE) and registry['driver_tool_sha256'] == pin(driver_path)['sha256'], 'Driver tool identity mismatch')
    require(Path(registry['driver']).resolve() == Path(driver_path).resolve(), 'Driver path mismatch')
    require(set(registry['roles']) == {'worker', 'regulator', 'fixture', 'recorder'}, 'Four exact roles required')
    for role, row in registry['roles'].items():
        bp = row['source_bundle']
        require(pin(bp['path'])['sha256'] == bp['sha256'], role + ' bundle mismatch')
        files = read(bp['path'])['files']
        for f in files.values() if isinstance(files, dict) else files:
            require(Path(f['path']).is_absolute(), role + ' source path must be absolute')
            require(pin(f['path']) == {'bytes': f['bytes'], 'sha256': f['sha256']}, role + ' source bytes mismatch: ' + f['path'])
        require(pin(row['binary'])['sha256'] == row['binary_sha256'], role + ' ELF mismatch')
        with Path(row['binary']).open('rb') as f:
            require(f.read(4) == b'\x7fELF', role + ' is not an ELF')
    require(registry.get('regulator_source_sha256') == 'dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5',
            'T2 keeps the Regulator source byte-identical')
    require(pin(reg['topics'])['sha256'] == reg['topics_sha256'], 'Topics pin mismatch')
    output = Path(reg['output'])
    require(output.is_absolute() and output.parent == Path(driver_path).resolve().parent.parent / 'runs', 'Output outside registered runs directory')
    require(output.parent.is_dir() and not output.exists(), 'Output must be a new run under an existing parent')
    ap = reg.get('audit_tool', {})
    require(pin(ap['path'])['sha256'] == ap['sha256'], 'T2 audit tool mismatch')
    return config, registry, table
