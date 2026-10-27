#!/usr/bin/env python3
"""Append tests through the existing friend/fixture, guarded by the actual F4 SHA.

Dry-run by default. No SSH, source download, source replacement, or production
test hook. All unmodified target bytes, including newline style, are retained.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
F4_TEST_SHA256 = "99dd8bb798d2771c6c64e8cdbf8a635f41e5c5a6c1545f228be9028edd45918b"
MARKER = "P1_ATOMIC_FREEZE_TEST_"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(raw: bytes) -> bytes:
    text = raw.decode("utf-8")
    if MARKER in text:
        raise ValueError("atomic-freeze test markers already present")
    for required in ("class ResearchContract", "class ReferencePredictionContract",
                     "class ReferenceEvidenceSolver", "reference_solver(",
                     "reference_path_version(", "reference_profile_version(",
                     "P0_REFERENCE_PREDICTION_TEST_CASES_V1", "condition_variable"):
        if required not in text:
            raise ValueError("F4 fixture prerequisite missing: " + required)
    access = list(re.finditer(
        r"(?m)^\s*class\s+MpcControllerNodeTestAccess\s*\{\s*public\s*:", text))
    ends = list(re.finditer(r"(?m)^\}\s*//\s*namespace\s*$", text))
    if len(access) != 1 or len(ends) != 1:
        raise ValueError("expected one existing friend public anchor and namespace end")
    newline = "\r\n" if b"\r\n" in raw else "\n"
    fragments = []
    for path in (HERE / "atomic_access.inc", HERE / "atomic_tests.inc"):
        fragments.append(path.read_text(encoding="utf-8").replace("\r\n", "\n")
                         .replace("\n", newline))
    edits = [(access[0].end(), newline + fragments[0]),
             (ends[0].start(), newline + fragments[1] + newline)]
    for position, content in sorted(edits, reverse=True):
        text = text[:position] + content + text[position:]
    return text.encode("utf-8")


def apply(target: Path, expected_sha256: str, write: bool = False) -> dict:
    if target.name != "test_research_contract.cpp":
        raise ValueError("only the existing test_research_contract.cpp may be patched")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("expected SHA256 must contain 64 lowercase hex digits")
    raw = target.read_bytes()
    before = digest(raw)
    if before != expected_sha256:
        raise ValueError("actual target does not match expected verified SHA256")
    new = prepare(raw)
    backup = target.with_name(target.name + ".pre_p1_atomic_freeze_tests_v1")
    if write:
        if backup.exists():
            raise ValueError("create-only backup already exists")
        if target.read_bytes() != raw:
            raise ValueError("target changed during validation")
        with backup.open("xb") as file:
            file.write(raw)
        # All guards passed before this single existing-test mutation.
        target.write_bytes(new)
        if target.read_bytes() != new:
            raise RuntimeError("post-write byte verification failed")
    return {"written": write, "before_sha256": before, "after_sha256": digest(new),
            "backup": str(backup) if write else None,
            "new_tests": re.findall(r"TEST_F\(AtomicFreezeContract,\s*(\w+)\)",
                                    (HERE / "atomic_tests.inc").read_text(encoding="utf-8")),
            "scope": "actual node/actual callbacks/fake solver; no production test hook"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--expected-sha256", default=F4_TEST_SHA256)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(apply(args.target, args.expected_sha256, args.write), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
