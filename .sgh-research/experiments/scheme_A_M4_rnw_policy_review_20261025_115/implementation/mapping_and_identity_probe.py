#!/usr/bin/env python3
"""Read-only time-domain arithmetic and present identity checks, not new policy."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
B112 = BASE / 'scheme_A_M4_t2a_rnw2_impl_20261025_112'
RUN = B112 / 'implementation/runs/T2A_RNW2'


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


fixture = [json.loads(s) for s in (RUN / 'fixture/nominal_steps.jsonl').read_text().splitlines() if s.strip()]
hold = next(r for r in fixture if r.get('action') == 'clock_hold')
resume = next(r for r in fixture if r.get('action') == 'clock_resume')
models = [r for r in fixture if r.get('schema') == 'p1-controlled-nominal-model-step-v1']
last = next(r for r in reversed(models) if r['target_ns'] < hold['executed_ns'] and not r['t2_hold_active'])
first = next(r for r in models if r['target_ns'] >= resume['executed_ns'] and not r['t2_hold_active'])
held_last = next(r for r in reversed(models) if r['target_ns'] < resume['executed_ns'] and r['t2_hold_active'])
paired_next = last['sim_stamp_ns'] + first['target_ns'] - last['target_ns']
shorthand_next = last['sim_stamp_ns'] + resume['executed_ns'] - hold['executed_ns'] + first['target_ns'] - held_last['target_ns']
assert last['sim_stamp_ns'] == 101782845634
assert hold['executed_ns'] - last['target_ns'] == 11439084
assert shorthand_next - paired_next == 6838410
arithmetic = {
    'scope': 'counterfactual arithmetic over retained Fixture observations; not an implemented or run B2 policy',
    'last_actual_clock_pair': {'stamp_ns': last['sim_stamp_ns'], 'target_ns': last['target_ns']},
    'hold_action_ns': hold['executed_ns'], 'resume_action_ns': resume['executed_ns'],
    'last_held_writer_target_ns': held_last['target_ns'], 'first_resumed_writer_target_ns': first['target_ns'],
    'first_resumed_stamp_observed': first['sim_stamp_ns'],
    'command_hold_duration_ns': resume['executed_ns'] - hold['executed_ns'],
    'last_publication_to_hold_edge_ns': hold['executed_ns'] - last['target_ns'],
    'paired_mapping_next_stamp_counterfactual': paired_next,
    'last_stamp_plus_command_hold_plus_current_increment_counterfactual': shorthand_next,
    'shorthand_error_ns': shorthand_next - paired_next,
    'requirements': ['bind stamp to its actual writer target', 'avoid double counting last_target increment',
                     'constrain initial implementation to registered silent profile',
                     'recompute raw clock, projected-history ordering and RTF separately']}
reg = read(B112 / 'implementation/T2A_RNW2_registration.json')
registry = read(reg['registry'])
bundle = read(B112 / 'evidence/freeze/source_bundle.json')
identity = {
    'scope': 'current registration and source population only; not historic ownership or a complete run audit',
    'registration_sha256': pin(B112 / 'implementation/T2A_RNW2_registration.json')['sha256'],
    'registry_matches_registration': pin(reg['registry'])['sha256'] == reg['registry_sha256'],
    'table_matches_registration': pin(reg['action_table'])['sha256'] == reg['action_table_sha256'],
    'audit_matches_registration': pin(reg['audit_tool']['path'])['sha256'] == reg['audit_tool']['sha256'],
    'Driver_matches_registry': pin(registry['driver'])['sha256'] == registry['driver_tool_sha256'],
    'ELF_matches_registry': {name: pin(entry['binary'])['sha256'] == entry['binary_sha256']
                             for name, entry in registry['roles'].items()},
    'bundle_files': len(bundle['files']),
    'bundle_population_matches': all(pin(entry['path']) == {k: entry[k] for k in ('bytes', 'sha256')}
                                     for entry in bundle['files'].values())}
for name, value in [('mapping_arithmetic_v1.json', arithmetic), ('identity_readback_v1.json', identity)]:
    with (ROOT / 'evidence' / name).open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'mapping_shorthand_error_ns': arithmetic['shorthand_error_ns'], 'current_identity': identity}, ensure_ascii=False))
