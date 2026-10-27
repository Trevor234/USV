"""Guard small F3 additions for optional fourth-stream runtime gate and freeze."""
import argparse
import ast
import hashlib
import json
from pathlib import Path


def patch(raw, edits):
    text = raw.decode('utf-8')
    for before, after in edits:
        if text.count(before) != 1:
            raise ValueError('Anchor absent or ambiguous: ' + repr(before))
        text = text.replace(before, after, 1)
    ast.parse(text)
    return text.encode('utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', type=Path, required=True)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    root = args.workspace.resolve(strict=True)
    baseline = root / '.sgh-research/baselines/F3_20261004_quaternion_gate_01'
    hashes = {x['path']: x['sha256'] for x in json.loads((baseline / 'source_hashes.json').read_text())}
    plans = {
        'usv_mpc_ws/scripts/capture_p0_runtime_context.py': [
            ('    parser.add_argument("--wait-timeout", type=float, default=45.0)\n',
             '    parser.add_argument("--wait-timeout", type=float, default=45.0)\n'
             '    parser.add_argument("--reference-prediction", action="store_true",\n'
             '                        help="Require the optional fourth research publisher/recorder")\n'),
            ('    topics = dict(DEFAULT_TYPES)\n',
             '    topics = dict(DEFAULT_TYPES)\n'
             '    if args.reference_prediction:\n'
             '        topics["/research/reference_prediction"] = "usv_research_interfaces/msg/ReferencePrediction"\n'),
        ],
        'usv_mpc_ws/scripts/collect_repair_baseline.py': [
            ('    "usv_mpc_ws/scripts/check_p0_contract.py",\n',
             '    "usv_mpc_ws/scripts/check_p0_contract.py",\n'
             '    "usv_mpc_ws/scripts/check_reference_prediction.py",\n'
             '    "usv_mpc_ws/scripts/tests/test_check_reference_prediction.py",\n'),
            ('RESEARCH_MESSAGES = ("StateSnapshot", "AppliedControl", "CycleTiming")\n',
             'RESEARCH_MESSAGES = ("StateSnapshot", "AppliedControl", "CycleTiming", "ReferencePrediction")\n'),
        ],
    }
    prepared = []
    for relative, edits in plans.items():
        target = root / relative
        raw = target.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if sha != hashes[relative]:
            raise ValueError('Current file differs from frozen F3: ' + relative)
        changed = patch(raw, edits)
        prepared.append((target, raw, changed))
    result = []
    for target, raw, changed in prepared:
        if args.apply:
            if target.read_bytes() != raw:
                raise ValueError('Changed while preparing patch')
            target.write_bytes(changed)
        result.append({'path': str(target.relative_to(root)), 'before_sha256': hashlib.sha256(raw).hexdigest(),
                       'after_sha256': hashlib.sha256(changed).hexdigest(), 'applied': args.apply})
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
