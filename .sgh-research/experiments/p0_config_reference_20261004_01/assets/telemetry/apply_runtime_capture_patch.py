#!/usr/bin/env python3
"""Add an optional 13th-topic graph gate; preserve old 12-topic default."""
import argparse
import hashlib
import json
from pathlib import Path

MARKER = "P0_REFERENCE_RUNTIME_CAPTURE_V1"


def prepare(raw):
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if MARKER in text:
        raise ValueError("runtime capture extension already present")
    replacements = [
        ('    parser.add_argument("--wait-timeout", type=float, default=45.0)',
         '    # ' + MARKER + '\n'
         '    parser.add_argument("--reference-prediction", action="store_true")\n'
         '    parser.add_argument("--wait-timeout", type=float, default=45.0)'),
        ('    topics = dict(DEFAULT_TYPES)',
         '    topics = dict(DEFAULT_TYPES)\n'
         '    if args.reference_prediction:\n'
         '        topics["/research/reference_prediction"] = "usv_research_interfaces/msg/ReferencePrediction"'),
    ]
    for old, new in replacements:
        if text.count(old) != 1:
            raise ValueError("runtime capture anchor missing or repeated: " + old)
        text = text.replace(old, new)
    return text.encode("utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=Path, required=True)
    p.add_argument("--expected-sha256")
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    if a.target.name != "capture_p0_runtime_context.py":
        raise ValueError("target must be the existing capture helper")
    raw = a.target.read_bytes()
    before = hashlib.sha256(raw).hexdigest()
    if a.expected_sha256 and before != a.expected_sha256:
        raise ValueError("source hash mismatch")
    new = prepare(raw)
    backup = a.target.with_name(a.target.name + ".pre_reference_prediction_v1")
    if a.write:
        if backup.exists() or a.target.read_bytes() != raw:
            raise ValueError("backup exists or source changed")
        backup.write_bytes(raw)
        a.target.write_bytes(new)
    print(json.dumps({"written": a.write, "before_sha256": before,
        "after_sha256": hashlib.sha256(new).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
