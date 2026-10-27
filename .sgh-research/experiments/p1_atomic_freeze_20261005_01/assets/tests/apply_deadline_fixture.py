#!/usr/bin/env python3
"""Guarded single fixture edit: prepare genuine odom/path eligibility for old tests.

Production eligibility remains strict. Fake deadline candidates, mappings,
failure thresholds and all existing deadline test cases remain unchanged.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
F4_DEADLINE_SHA256 = "7f720eb55ad8416df826d3866cba0617310cfee044bb69b9fa2b8c4c20ae807c"
MARKER = "P1_ATOMIC_DEADLINE_FIXTURE_V1"
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[A-Za-z_]\w*|\d+(?:\.\d+)?|[^\s]')
OLD = """node->reference_path_ = {{{0.0, 0.0, 0.0}}, {{1.0, 0.0, 0.0}},
      {{2.0, 0.0, 0.0}}, {{3.0, 0.0, 0.0}}};"""


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def prepare(raw: bytes) -> bytes:
    text = raw.decode("utf-8")
    if MARKER in text:
        raise ValueError("deadline fixture patch already present")
    for required in ("class MpcControllerNodeTestAccess", "class DeadlineControl",
                     "node->max_solve_time_ms_", "node.run_dynamic_mpc_();"):
        if required not in text:
            raise ValueError("existing deadline fixture prerequisite missing: " + required)
    pattern = r"\s*".join(re.escape(token) for token in TOKEN.findall(OLD))
    hits = list(re.finditer(pattern, text))
    if len(hits) != 1:
        raise ValueError("expected one unchanged four-point fixture assignment")
    hit = hits[0]
    newline = "\r\n" if b"\r\n" in raw else "\n"
    fragment = (HERE / "deadline_fixture.inc").read_text(encoding="utf-8")
    fragment = fragment.replace("\r\n", "\n").replace("\n", newline)
    # The four existing indentation spaces precede the anchor. Remove four
    # spaces from the fragment's first line to preserve surrounding bytes.
    fragment = fragment[4:] if fragment.startswith("    ") else fragment
    return (text[:hit.start()] + fragment.rstrip("\r\n") + text[hit.end():]).encode("utf-8")


def apply(target: Path, expected_sha256: str, write: bool = False) -> dict:
    if target.name != "test_deadline_control.cpp":
        raise ValueError("only existing test_deadline_control.cpp may be patched")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("expected SHA256 must contain 64 lowercase hex digits")
    raw = target.read_bytes()
    before = digest(raw)
    if before != expected_sha256:
        raise ValueError("actual target does not match expected verified SHA256")
    new = prepare(raw)
    backup = target.with_name(target.name + ".pre_p1_atomic_deadline_fixture_v1")
    if write:
        if backup.exists():
            raise ValueError("create-only backup already exists")
        if target.read_bytes() != raw:
            raise ValueError("target changed during validation")
        with backup.open("xb") as file:
            file.write(raw)
        target.write_bytes(new)
        if target.read_bytes() != new:
            raise RuntimeError("post-write byte verification failed")
    return {"written": write, "before_sha256": before, "after_sha256": digest(new),
            "backup": str(backup) if write else None,
            "existing_test_cases_changed": False,
            "scope": "one test-only eligibility setup; actual odom and path callbacks"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--expected-sha256", default=F4_DEADLINE_SHA256)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(apply(args.target, args.expected_sha256, args.write), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
