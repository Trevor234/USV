#!/usr/bin/env python3
"""Admission for the T2B-GEN scenario family (batch 102 design, Stage 2).

This is a NEW family admission module: the frozen T2 contract modules
(t2_action_contract.py, w2_runtime_contract.py) stay byte-identical, and the
frozen T2 preflight (which pins the Regulator source at the batch-91 review
state) continues to govern ordinary T2 runs. The T2B-GEN family alone admits
the scoped-generation Regulator wiring under these pins:

- Regulator source: the scoped wiring below (sha pinned here)
- Worker and Fixture SOURCES: byte-identical to the batch-91 review state
- Contract: the frozen v4 diagnostic contract (fault declared), as T2-B boundary
- Vocabulary: exactly one path_replace at 201 points / 0.1 m/s for the
  positive control (inside the frozen Epoch's own static speed domain
  {.05,.1,.3,.6}), or one driver_shutdown_request for the negative control

Everything else follows the T2 discipline: isolated DDS env, 45s one-attempt
budget, registry/bundle/ELF per-file pins, output-under-runs, audit tool pin.
"""
import json
import os
from pathlib import Path

import t2_action_contract as t2
from w2_runtime_contract import require, pin, read

REGISTRATION_SCHEMA = 'M4-owned-t2bgen-scenario-run-v1'
SCOPE = 'M4_owned_local_nominal_only_v1'  # ordinary frozen runtime scope: scoped generation is a policy capability, not a fault hook  # frozen admitted runtime scope; family identity lives in schema/case
CONTRACT_SHA = '19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a'  # frozen v3 contract
REGULATOR_SOURCE_SHA = '2a3fc697bee865e0d1ead1fa27b286f3bfa7cfb7a19228c3c00dbc8bbb1a62ff'
WORKER_SOURCE_SHA_B91 = 'd4e2cd2cc2db7c68fa928dcc2012130e890e3370f88ffba796eb2cfc894468a8'
FIXTURE_SOURCE_SHA = '20e11a758a95d085e8bfa1d97992ee52661c955dd8f69a3b8633fcabc2789e53'  # B2' pairing-mapping fixture variant (batch 118 S2; declared, not batch-91)
TABLE_SCHEMA = 'M4-t2-action-table-v1'
TABLE_KEYS = {'schema', 'run_id', 'case', 'contract_sha256', 'actions', 'clauses'}
FAMILY_ACTIONS = {
    'T2B-gen-positive-control': {'path_replace'},
    'T2B-gen-negative-control': {'driver_shutdown_request'},
    # batch 111 design: resume->new-window acceptance under the scoped Epoch
    # wiring, driven by the existing T2-A fixture clock writers.
    'T2A-gen-resume-new-window': {'clock_hold', 'clock_resume', 'driver_shutdown_request'},
}
TRIGGER_PHASES = {'solve_active', 'ready_window', 'job_received'}
CLAUSES = {
    'T2B-gen-positive-control': {'deadline_must_not_extend', 'stale_result_reject_reasons',
                                 'old_generation_must_not_revive', 'new_generation_first_job_must_commit'},
    'T2B-gen-negative-control': {'no_generation_without_binding_change'},
    'T2A-gen-resume-new-window': {'resume_requires_new_window', 'old_candidate_must_not_revive', 'pause_confirm_ns'},
}


_HARDENED = None


def _hardened_rules():
    """Import the single physical rule module for the RNW family.

    Path resolution is explicit and cached; the module identity (path + sha) is
    recorded so a caller can prove both the freeze helper and this Driver preflight
    are judging with the same bytes (F124-03: previously they were not).

    A file imported twice becomes two module objects with separate module state, so
    an already-loaded module for the SAME resolved path is reused instead of being
    loaded a second time. "One rule source" must hold at the object level too.
    """
    global _HARDENED
    if _HARDENED is not None:
        return _HARDENED
    import importlib.util
    import sys as _sys
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / 'audit/t2_rnw_admission_rules.py',   # implementation/audit/
        here.parent / 'audit/t2_rnw_admission_rules.py',
    ]
    for cand in candidates:
        if not cand.is_file():
            continue
        target = cand.resolve()
        for name, mod in list(_sys.modules.items()):
            f = getattr(mod, '__file__', None)
            if f and Path(f).resolve() == target:
                _HARDENED = mod                       # reuse: same bytes, same object
                return mod
        spec = importlib.util.spec_from_file_location('t2_rnw_admission_rules', target)
        mod = importlib.util.module_from_spec(spec)
        _sys.modules['t2_rnw_admission_rules'] = mod
        spec.loader.exec_module(mod)
        _HARDENED = mod
        return mod
    raise RuntimeError('hardened admission rules module not found; the RNW family '
                       'must be judged by exactly one physical module')


def validate_table(table, context):
    require(table.get('schema') == TABLE_SCHEMA, 'T2B-GEN table schema')
    require(set(table) == TABLE_KEYS, 'T2B-GEN table exact fields')
    family = table.get('case')
    require(family in FAMILY_ACTIONS, 'unknown T2B-GEN case')
    require(table['run_id'] == context['run_id'] and table['contract_sha256'] == context['contract_sha256'],
            'T2B-GEN table identity binding')
    require(table['case'] == context['case'], 'case binding')

    # ---- RNW family: delegate. No second copy of the rules may live here.
    hard = _hardened_rules()
    if hard.judges(family):
        rejections = hard.validate_table(table, {'run_id': context['run_id'],
                                                 'contract_sha256': context['contract_sha256']})
        require(not rejections,
                'hardened RNW admission rejected: ' + ', '.join(rejections))
        return

    # ---- other families keep their existing rules, unchanged.
    actions = table['actions']
    require(isinstance(actions, list) and 1 <= len(actions) <= 3, 'finite action population')
    ids = set()
    for row in actions:
        require(isinstance(row, dict) and set(row) == {'id', 'action', 'parameters', 'trigger'}, 'action shape')
        require(row['action'] in FAMILY_ACTIONS[family], 'action not admitted for this case')
        require(row['id'] not in ids, 'duplicate action id')
        ids.add(row['id'])
        trigger = row['trigger']
        require(isinstance(trigger, dict) and set(trigger) == {'delay_ms', 'job_id', 'phase'}, 'trigger shape')
        if family == 'T2A-gen-resume-new-window':
            require(trigger['phase'] == 'after_grant_ms' and trigger['job_id'] == 0
                    and isinstance(trigger['delay_ms'], int) and trigger['delay_ms'] >= 0,
                    'T2A-GEN trigger is the registered after-grant timing form')
        else:
            require(trigger['phase'] in TRIGGER_PHASES and isinstance(trigger['job_id'], int)
                    and trigger['job_id'] >= 1 and trigger['delay_ms'] == 0, 'trigger domain')
        if row['action'] == 'path_replace':
            require(row['parameters'] == {'points': 201, 'speed_m_s': 0.1},
                    'T2B-GEN path_replace is exactly 201 points at 0.1 m/s (frozen Epoch static speed domain)')
        elif row['action'] == 'clock_hold':
            require(row['parameters'] == {'mode': 'silent', 'duration_ms': 1200},
                    'T2A-GEN clock_hold is exactly silent/1200ms (beyond the 400ms pause confirm)')
        elif row['action'] == 'clock_resume':
            require(row['parameters'] == {},
                    'T2A-GEN clock_resume takes no parameters under the B2 pairing mapping (batch 118)')
        elif row['action'] == 'driver_shutdown_request' and family == 'T2A-gen-resume-new-window':
            require(row['parameters'] == {} and trigger['delay_ms'] == 9000,
                    'T2A-GEN termination action is exactly after_grant+9000ms (post-resume observation window)')
        else:
            require(row['parameters'] == {}, 'driver_shutdown_request takes no parameters')
    require(isinstance(table['clauses'], dict) and set(table['clauses']) == CLAUSES[family], 'clause set')


def fixture_action_parameters(registration, command_dir, table_path):
    table = json.loads(Path(table_path).read_bytes())
    validate_table(table, {'run_id': registration['run_id'], 'case': registration['case'],
                           'contract_sha256': registration['contract_sha256']})
    require(pin(table_path)['sha256'] == registration['action_table_sha256'], 'action table pin mismatch')
    return {'t2_case': registration['case'],
            't2_action_table_file': str(table_path),
            't2_action_table_sha256': registration['action_table_sha256'],
            't2_command_dir': str(command_dir)}


def registration_preflight_t2bgen(reg, driver_path, environment=None):
    env = os.environ if environment is None else environment
    require(__debug__, 'Driver must run with Python assertions enabled')
    require(reg.get('schema') == REGISTRATION_SCHEMA and reg.get('scope') == SCOPE, 'T2B-GEN schema/scope')
    require(reg.get('case') in FAMILY_ACTIONS, 'Unknown T2B-GEN case')
    require(reg.get('production_physical_release_enabled') is False, 'physical release must stay off')
    require(reg.get('fault_injection_enabled') is False, 'T2B-GEN is a policy positive control on the frozen ordinary contract, not a fault injection')
    require(reg.get('domain_id') == 120 and env.get('ROS_DOMAIN_ID') == '120'
            and env.get('ROS_LOCALHOST_ONLY') == '1' and env.get('RMW_IMPLEMENTATION') == 'rmw_fastrtps_cpp',
            'Exact isolated DDS environment required')
    require(reg.get('max_seconds') == 45 and reg.get('automatic_retries') == 0, 'Finite one-attempt budget required')
    require(reg.get('contract_sha256') == CONTRACT_SHA, 'T2B-GEN stays on the frozen v3 contract')
    require(pin(reg['contract'])['sha256'] == CONTRACT_SHA, 'Actual contract bytes mismatch')
    config = read(reg['contract'])
    require(config['schema'] == 'p1-execution-contract-v3' and config['qualification'] == 'execution_frozen'
            and config['fault_injection_enabled'] is False, 'ordinary frozen contract shape')
    t2.verify_budgets_unchanged(config)
    require(pin(reg['action_table'])['sha256'] == reg['action_table_sha256'], 'Action table pin mismatch')
    table = read(reg['action_table'])
    validate_table(table, {'run_id': reg['run_id'], 'case': reg['case'],
                           'contract_sha256': reg['contract_sha256']})
    require(table['case'] == reg['case'], 'Action table case binding')
    require(pin(reg['registry'])['sha256'] == reg['registry_sha256'], 'Registry pin mismatch')
    registry = read(reg['registry'])
    require(registry['scope'] == SCOPE and registry['driver_tool_sha256'] == pin(driver_path)['sha256'],
            'Driver tool identity mismatch')
    require(Path(registry['driver']).resolve() == Path(driver_path).resolve(), 'Driver path mismatch')
    require(set(registry['roles']) == {'worker', 'regulator', 'fixture', 'recorder'}, 'Four exact roles required')
    for role, row in registry['roles'].items():
        bp = row['source_bundle']
        require(pin(bp['path'])['sha256'] == bp['sha256'], role + ' bundle mismatch')
        files = read(bp['path'])['files']
        for f in files.values() if isinstance(files, dict) else files:
            require(Path(f['path']).is_absolute(), role + ' source path must be absolute')
            require(pin(f['path']) == {'bytes': f['bytes'], 'sha256': f['sha256']},
                    role + ' source bytes mismatch: ' + f['path'])
        require(pin(row['binary'])['sha256'] == row['binary_sha256'], role + ' ELF mismatch')
        with Path(row['binary']).open('rb') as f:
            require(f.read(4) == b'\x7fELF', role + ' is not an ELF')
    require(registry.get('regulator_source_sha256') == REGULATOR_SOURCE_SHA == pin(registry['regulator_source'])['sha256'],
            'T2B-GEN pins the scoped-wiring Regulator source')
    require(registry.get('worker_source_sha256') == WORKER_SOURCE_SHA_B91 == pin(registry['worker_source'])['sha256'],
            'Worker source must stay byte-identical to the batch-91 review state')
    require(registry.get('fixture_source_sha256') == FIXTURE_SOURCE_SHA == pin(registry['fixture_source'])['sha256'],
            'Fixture source is the declared B2 pairing-mapping variant (pinned)')
    require(pin(reg['topics'])['sha256'] == reg['topics_sha256'], 'Topics pin mismatch')
    output = Path(reg['output'])
    require(output.is_absolute() and output.parent == Path(driver_path).resolve().parent.parent / 'runs',
            'Output outside registered runs directory')
    require(output.parent.is_dir() and not output.exists(), 'Output must be a new run under an existing parent')
    ap = reg.get('audit_tool', {})
    require(pin(ap['path'])['sha256'] == ap['sha256'], 'audit tool pin mismatch')
    return config, registry, table
