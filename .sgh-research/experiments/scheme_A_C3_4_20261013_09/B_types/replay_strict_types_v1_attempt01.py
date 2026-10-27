"""Replay full analyze with controlled byte overlays of read-only N9 records.

No recorded file, author route, source/build pin, transport or SQLite data is
rewritten. This demonstrates parser/type rejection, not a new runtime case or
a coherent semantic tamper of authenticated original source payloads.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import check_release_observation_v1 as current


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical-author', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.historical_author.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    old_path = root / 'check_release_observation_v1.py'
    spec = importlib.util.spec_from_file_location('historical_release_checker_readonly', old_path)
    old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
    reports, original_hashes = {}, {}
    for mode in ('positive', 'expired'):
        run = root / 'runs' / ('owned_C3_3_' + mode + '_01')
        for label, checker in (('old', old), ('current', current)):
            value = checker.analyze(run)
            value['evidence_origin'] = 'read-only N9 capture; no new runtime'
            save(args.output / (mode + '_' + label + '_honest.json'), value)
            original_hashes.update(value['input_sha256_before'])
        reports[mode] = run

    expired = reports['expired']
    report_path = expired / 'publisher/release_observation.json'
    session_path = expired / 'publisher/session_summary.json'
    result_path = expired / 'result.json'
    original_report = json.loads(report_path.read_bytes())
    original_session = json.loads(session_path.read_bytes())
    original_result = json.loads(result_path.read_bytes())
    cases = []
    changed = copy.deepcopy(original_report)
    changed['gate']['original_freshness_read_count'] = True
    cases.append(('review_freshness_true', {report_path: changed}, True))
    changed = copy.deepcopy(original_session)
    for key in ('start_steady_ns', 'queue_dropped_total', 'publish_errors',
                'cycle_invocations_started', 'interrupted_cycle_sequence'):
        changed[key] = False
    for row in changed['streams'].values():
        for key in row:
            row[key] = False
    cases.append(('review_unarmed_and_four_stream_false', {session_path: changed}, True))
    for label, value in (('float', 1.0), ('string', '1'), ('null', None), ('negative', -1),
                         ('uint64_overflow', 1 << 64)):
        changed = copy.deepcopy(original_report)
        changed['gate']['original_freshness_read_count'] = value
        cases.append(('freshness_' + label, {report_path: changed}, False))
    for label, value in (('bool', False), ('float', 0.0), ('negative', -1),
                         ('int64_overflow', 1 << 63)):
        changed = copy.deepcopy(original_result)
        changed['close_elapsed_ns'] = value
        cases.append(('cleanup_time_' + label, {result_path: changed}, False))
    changed = copy.deepcopy(original_result)
    changed['owned_role_returncodes']['publisher'] = False
    changed['cleanup']['publisher']['returncode'] = False
    cases.append(('cleanup_returncode_false', {result_path: changed}, True))

    real_inputs = current.Inputs
    real_old_inputs = old.Inputs
    results = []
    for name, overlay, old_should_accept in cases:
        case_dir = args.output / name; case_dir.mkdir()
        byte_overlays = {path: json.dumps(value, sort_keys=True, indent=2,
            allow_nan=False).encode() + b'\n' for path, value in overlay.items()}
        for path, raw in byte_overlays.items():
            target = case_dir / path.relative_to(expired)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)

        def wrapped(base):
            class Overlaid(base):
                def raw(self, path, limit=current.MAX_FILE_BYTES, remember=True):
                    actual = super().raw(path, limit, remember)
                    p = Path(path)
                    if p not in byte_overlays:
                        return actual
                    raw = byte_overlays[p]
                    if len(raw) > limit:
                        raise ValueError('overlay_not_within_original_read_limit')
                    if remember:
                        self.before[str(p)] = hashlib.sha256(raw).hexdigest()
                    return raw
            return Overlaid

        def check_with(module, base):
            try:
                with patch.object(module, 'Inputs', wrapped(base)):
                    value = module.analyze(expired)
                return {'passed': value['passed'], 'representation_rejected': False}
            except Exception as error:
                return {'passed': False, 'error_type': type(error).__name__, 'error': str(error),
                    'representation_rejected': isinstance(error, ValueError) and (
                        str(error).startswith('field_domain:') or str(error) == 'nonfinite_json')}

        before = check_with(old, real_old_inputs)
        after = check_with(current, real_inputs)
        item = {'case': name, 'old': before, 'current': after, 'old_acceptance_expected': old_should_accept,
            'success': (not old_should_accept or before['passed']) and after['representation_rejected'],
            'overlay_paths': [str(p) for p in overlay],
            'input_boundary': 'full analyze decoded bytes overlay; original author path and authenticated pins unchanged',
            'runtime_wire_coverage': False, 'semantic_negative_pass': False}
        save(case_dir / 'result.json', item); results.append(item)

    unchanged = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in original_hashes}
    summary = {'schema': 'p1-C3.4-B-full-analyze-overlay/v1', 'passed': all(r['success'] for r in results),
        'honest_capture_compatibility': {'positive': True, 'expired': True}, 'cases': results,
        'historical_inputs_unchanged': unchanged == original_hashes,
        'historical_sha256_before': original_hashes, 'historical_sha256_after': unchanged,
        'new_runtime_coverage': False, 'phase_qualification': False,
        'qualification_changed': False, 'checker_sha256': hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest()}
    summary['passed'] = summary['passed'] and summary['historical_inputs_unchanged']
    save(args.output / 'summary.json', summary)
    print(json.dumps({'passed': summary['passed'], 'cases': len(results),
        'historical_inputs_unchanged': summary['historical_inputs_unchanged']}))
    return 0 if summary['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
