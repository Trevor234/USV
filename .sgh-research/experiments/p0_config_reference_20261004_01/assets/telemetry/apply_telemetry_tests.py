#!/usr/bin/env python3
"""Append five telemetry GTests and friend helpers; dry-run by default."""
from pathlib import Path
import argparse
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent


def prepare(raw: bytes) -> bytes:
    text = raw.decode("utf-8")
    if "P0_REFERENCE_PREDICTION_TEST_" in text:
        raise ValueError("telemetry test patch already present")
    access = list(re.finditer(
        r"(?m)^\s*class\s+MpcControllerNodeTestAccess\s*\{\s*public\s*:", text))
    ends = list(re.finditer(r"(?m)^\}\s*//\s*namespace\s*$", text))
    if len(access) != 1 or len(ends) != 1 or "class ResearchContract" not in text:
        raise ValueError("expected one friend class, existing fixture, and namespace end")
    for required in ("observer_added_", "case_", "sys/resource.h", "ContractSolver"):
        if required not in text:
            raise ValueError("existing verified fixture prerequisite missing: " + required)
    edits = [(access[0].end(), "\n" + (HERE / "test_access.inc").read_text(encoding="utf-8")),
             (ends[0].start(), "\n" + (HERE / "test_cases.inc").read_text(encoding="utf-8") + "\n")]
    for position, content in sorted(edits, reverse=True):
        text = text[:position] + content + text[position:]
    return text.replace("\r\n", "\n").encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.target.name != "test_research_contract.cpp":
        raise ValueError("target must be existing test_research_contract.cpp")
    raw = args.target.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if args.expected_sha256 and args.expected_sha256 != sha:
        raise ValueError("current test file hash mismatch")
    new = prepare(raw)
    backup = args.target.with_name(args.target.name + ".pre_reference_prediction_v1")
    if args.write:
        if backup.exists():
            raise ValueError("backup already exists")
        if args.target.read_bytes() != raw:
            raise ValueError("test file changed during validation")
        backup.write_bytes(raw)
        args.target.write_bytes(new)
    print(json.dumps({"written": args.write, "before_sha256": sha,
        "after_sha256": hashlib.sha256(new).hexdigest(),
        "appended_tests": re.findall(r"TEST_F\(ReferencePredictionContract,\s*(\w+)\)",
            (HERE / "test_cases.inc").read_text(encoding="utf-8"))}, indent=2))


if __name__ == "__main__":
    main()
