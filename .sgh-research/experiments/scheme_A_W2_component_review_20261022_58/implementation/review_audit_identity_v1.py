#!/usr/bin/env python3
"""Replay current v3 with private identity/config input edits; never edit old files."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
BASE = Path('/home/trevor/USV/.sgh-research/experiments')
ROOT = BASE / 'scheme_A_W2_component_review_20261022_58'
P57 = BASE / 'scheme_A_M4_diagnostic_review_20261022_57'
P56 = BASE / 'scheme_A_M4_diagnostic_worker_20261021_56'
AUDITOR = P57 / 'implementation/audit_v3/audit_diagnostic_v3.py'


def save(p, value):
    with p.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')


def pin(p):
    b = p.read_bytes()
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}


def replay(label):
    spec = importlib.util.spec_from_file_location('audit_v3_identity_probe', AUDITOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.D = ROOT / 'evidence' / label
    (mod.D / 'postrun').mkdir(parents=True)
    original = mod.read
    changes = []

    def edited(p):
        value = original(p)
        p = Path(p)
        if (label == 'peer_config_probe_final'
                and p.parent.name in ('worker', 'regulator', 'fixture')
                and p.name in ('manifest.json', 'owned_manifest.json')
                and 'contract_configuration' in value):
            value = copy.deepcopy(value)
            value['contract_configuration']['hold_ns'] += 1234
            changes.append(str(p))
        if label == 'driver_tool_probe' and p.name == 'driver_manifest.json':
            value = copy.deepcopy(value)
            value['tool_sha256'] = '0' * 64
            changes.append(str(p))
        return value

    mod.read = edited
    old_argv = sys.argv
    sys.argv = ['audit_diagnostic_v3.py', '--case', 'W4', '--registration',
                str(P56 / 'implementation/W4_registration_v1.json')]
    stream = io.StringIO()
    try:
        with contextlib.redirect_stdout(stream):
            mod.main()
        result = {'auditor_passed': True, 'stdout': stream.getvalue()}
    except Exception as exc:
        result = {'auditor_passed': False, 'exception': type(exc).__name__,
                  'message': str(exc)}
    finally:
        sys.argv = old_argv
    result.update(label=label, in_memory_input_edits=changes,
                  unique_edited_paths=sorted(set(changes)),
                  synthetic_input=True, runtime_evidence=False,
                  original_files_edited=False)
    assert changes, 'private probe did not edit an input'
    if label == 'peer_config_probe_final':
        assert len(set(changes)) == 3, 'three distinct peer manifests must be edited'
    save(mod.D / 'MUTATED_INPUT_NOT_RUNTIME_EVIDENCE.json', result)
    return result


def main():
    results = [replay('peer_config_probe_final'), replay('driver_tool_probe')]
    save(ROOT / 'evidence/additional_audit_identity_probes_v1.json', results)
    snapshot_path = P57 / 'evidence/review_inputs_before_v1.json'
    snapshot = json.loads(snapshot_path.read_bytes())
    delta = []
    for name, expected in snapshot['files'].items():
        actual = pin(Path(name))
        if actual != expected:
            delta.append({'path': name, 'previous': expected, 'current': actual})
    receipt = json.loads((P57 / 'evidence/delivery_to_MPC_v1.json').read_bytes())
    history = {
        'previous_snapshot_pin': pin(snapshot_path),
        'snapshot_matches_original_delivery_receipt':
            pin(snapshot_path) == receipt['compared_files']['evidence/review_inputs_before_v1.json'],
        'previous_review_inputs_checked': len(snapshot['files']),
        'changed_since_previous_review': delta,
        'attribution': 'Unknown; this review does not restore or edit any previous file.'}
    save(ROOT / 'evidence/prior_56_history_delta_v1.json', history)
    mirrored = []
    for sub in ('implementation/w2_gate', 'implementation/audit_v3'):
        for source in sorted((P57 / sub).iterdir()):
            if not source.is_file():
                continue
            dest = Path('/home/trevor/MPC') / P57.name / source.relative_to(P57)
            mirrored.append({'source': str(source), 'destination': str(dest),
                             'source_pin': pin(source),
                             'destination_pin': pin(dest) if dest.is_file() else None,
                             'matches': dest.is_file() and pin(source) == pin(dest)})
    source_doc = P57 / 'documents/W2步骤1_私有pipe_release_gate组件_2026-10-22.md'
    dest_doc = Path('/home/trevor/MPC') / P57.name / source_doc.relative_to(P57)
    mirrored.append({'source': str(source_doc), 'destination': str(dest_doc),
                     'source_pin': pin(source_doc),
                     'destination_pin': pin(dest_doc) if dest_doc.is_file() else None,
                     'matches': dest_doc.is_file() and pin(source_doc) == pin(dest_doc)})
    save(ROOT / 'evidence/current_eight_file_MPC_check_v1.json', mirrored)
    print(json.dumps({'additional_audit_probes': [
        {'label': x['label'], 'auditor_passed': x['auditor_passed']} for x in results],
        'historical_input_changes': len(delta),
        'MPC_files_checked': len(mirrored),
        'MPC_mismatches': sum(not x['matches'] for x in mirrored)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
