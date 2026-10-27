"""Review-only byte-overlay checks against the original frozen release checker.

The original run/files stay unchanged. Overlay bytes model changed JSON inputs
at the original reader boundary; this is no native/wire or new-run evidence.
"""
from pathlib import Path
import copy
import hashlib
import json
import math
import sys

AUTHOR = Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9')
REVIEW = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_review_20261013_08')
sys.dont_write_bytecode = True
sys.path.insert(0, str(AUTHOR))
import check_release_observation_v1 as check

RUN = AUTHOR / 'runs/owned_C3_3_expired_01'
BaseInputs = check.Inputs

def scenario(name, replacements):
    class OverlayInputs(BaseInputs):
        def raw(self, path, limit=check.MAX_FILE_BYTES, remember=True):
            original = super().raw(path, limit, remember)
            key = str(Path(path))
            if key not in replacements:
                return original
            raw = replacements[key]
            check.require(len(raw) <= limit, 'review_overlay_exceeds_original_limit')
            if remember:
                self.total += len(raw) - len(original)
                self.before[key] = check.digest(raw)
            return raw
    check.Inputs = OverlayInputs
    try:
        report = check.analyze(RUN)
        return {'name': name, 'accepted_by_original_analyze': report['passed'],
            'gate_read_count': report['components']['actual_gate_observation']['original_freshness_read_count'],
            'gate_read_count_type': type(report['components']['actual_gate_observation']['original_freshness_read_count']).__name__,
            'whole_transport_SQLite_passed': report['components']['whole_transport_actual_SQLite']['passed'],
            'source_session_passed': report['components']['source_session']['passed'],
            'qualifications': report['qualifications'],
            'overlay_sha256': {k: hashlib.sha256(v).hexdigest() for k, v in replacements.items()}}
    except Exception as error:
        return {'name': name, 'accepted_by_original_analyze': False,
            'error_type': type(error).__name__, 'error': str(error)}
    finally:
        check.Inputs = BaseInputs

def encoded(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()

def main():
    gate_path = RUN / 'publisher/release_observation.json'
    session_path = RUN / 'publisher/session_summary.json'
    gate = json.loads(gate_path.read_bytes())
    session = json.loads(session_path.read_bytes())
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (gate_path, session_path)}
    cases = [scenario('original_expired_control', {})]
    altered_gate = copy.deepcopy(gate)
    altered_gate['gate']['original_freshness_read_count'] = True
    cases.append(scenario('boolean_true_instead_of_unsigned_count1', {str(gate_path): encoded(altered_gate)}))
    altered_session = copy.deepcopy(session)
    fields = ['queue_dropped_total', 'publish_errors', 'start_steady_ns',
        'cycle_invocations_started', 'interrupted_cycle_sequence']
    for field in fields:
        altered_session[field] = False
    for row in altered_session['streams'].values():
        for field in ['generated', 'emitted', 'dropped', 'first_sequence', 'last_sequence']:
            row[field] = False
    cases.append(scenario('boolean_false_instead_of_unarmed_integer0_counters', {str(session_path): encoded(altered_session)}))
    wrong_count = copy.deepcopy(gate)
    wrong_count['gate']['original_freshness_read_count'] = 2
    cases.append(scenario('wrong_integer_read_count2_negative_control', {str(gate_path): encoded(wrong_count)}))
    overflow = check.strict_json(b'{"value":1e309}')
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (gate_path, session_path)}
    report = {'schema': 'scheme-A-review-release-types/v1', 'client_date': '2026-10-13',
        'scope': 'original whole analyze with in-memory JSON byte overlays; all actual native inputs read-only',
        'cases': cases, 'parser_only_exponent_overflow_yields_infinity': math.isinf(overflow['value']),
        'original_files_unchanged': before == after, 'original_sha256_before': before,
        'original_sha256_after': after, 'checker_sha256': hashlib.sha256((AUTHOR / 'check_release_observation_v1.py').read_bytes()).hexdigest(),
        'not_native_or_wire_evidence': True, 'stage_qualified': False}
    with (REVIEW / 'release_checker_type_reproduction.json').open('x') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'cases': cases, 'original_files_unchanged': before == after,
        'parser_overflow_inf': report['parser_only_exponent_overflow_yields_infinity']}, ensure_ascii=False))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
