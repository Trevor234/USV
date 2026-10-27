#!/usr/bin/env python3
"""Insert quaternion admission test helpers and cases into an existing fixture.

Requires unique class/namespace markers. Other independently inserted test
helpers/cases remain untouched. A repeated patch, mixed newline file, hash
mismatch or unexpected fixture refuses to write. Default mode is dry-run.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


HERE = Path(__file__).resolve().parent
HELPER_MARKER = "P0_QUATERNION_TEST_ACCESS_V1_BEGIN"
TEST_MARKER = "P0_QUATERNION_TEST_CASES_V1_BEGIN"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def prepare_patch(raw):
    text = raw.decode("utf-8")
    if HELPER_MARKER in text or TEST_MARKER in text:
        raise ValueError("Quaternion patch marker already present; refusing duplicate application")
    if "\r\n" in text and "\n" in text.replace("\r\n", ""):
        raise ValueError("Mixed newline input; normalize separately before patching")
    newline = "\r\n" if "\r\n" in text else "\n"
    access = list(re.finditer(
        r"(?m)^\s*class\s+MpcControllerNodeTestAccess\s*\{\s*public\s*:", text))
    fixture = list(re.finditer(r"(?m)^\s*class\s+ResearchContract\s*:\s*public\s+::testing::Test\b", text))
    namespace_end = list(re.finditer(r"(?m)^\}\s*//\s*namespace\s*$", text))
    if len(access) != 1 or len(fixture) != 1 or len(namespace_end) != 1:
        raise ValueError("Expected one access class, ResearchContract fixture, and anonymous namespace end")
    for required in ("quaternion_to_yaw",):
        # The node function is not expected in this test file; no replacement
        # or inspection of production code is performed by this helper.
        if re.search(r"\b" + required + r"\s*\([^)]*\)\s*\{", text):
            raise ValueError("Unexpected production helper definition in target")
    for required in ("ContractSolver", "spin_until", "void enable", "void run", "summary"):
        if required not in text:
            raise ValueError("Fixture prerequisite missing: " + required)
    helpers_raw = (HERE / "helper_methods.cpp.txt").read_bytes()
    tests_raw = (HERE / "appended_tests.cpp.txt").read_bytes()
    helpers = helpers_raw.decode("utf-8").replace("\r\n", "\n").replace("\n", newline)
    tests = tests_raw.decode("utf-8").replace("\r\n", "\n").replace("\n", newline)
    names = re.findall(r"TEST_F\(ResearchContract,\s*(\w+)\)", tests)
    if len(names) != 4 or len(set(names)) != 4:
        raise ValueError("Appended test payload must contain four unique cases")
    for name in names:
        if name in text:
            raise ValueError("New test name already exists: " + name)
    edits = [(access[0].end(), newline + helpers),
             (namespace_end[0].start(), newline + tests + newline)]
    patched = text
    for position, content in sorted(edits, reverse=True):
        patched = patched[:position] + content + patched[position:]
    original_cases = re.findall(r"TEST_F\(ResearchContract,\s*(\w+)\)", text)
    patched_cases = re.findall(r"TEST_F\(ResearchContract,\s*(\w+)\)", patched)
    if len(patched_cases) != len(original_cases) + 4:
        raise ValueError("Unexpected case count change")
    return patched.encode("utf-8"), {
        "original_test_count": len(original_cases), "new_test_count": len(patched_cases),
        "appended_tests": names, "helper_payload_sha256": sha256(helpers_raw),
        "test_payload_sha256": sha256(tests_raw),
        "newline": "CRLF" if newline == "\r\n" else "LF",
        "guards": "unique access class/fixture/namespace; own markers absent; prerequisites present",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup-directory", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    target = args.target.resolve()
    if target.name != "test_research_contract.cpp" or not target.is_file():
        parser.error("Target must be an existing test_research_contract.cpp")
    if args.report and args.report.exists():
        parser.error("Report already exists; refusing overwrite")
    raw = target.read_bytes()
    before = sha256(raw)
    if args.expected_sha256 and args.expected_sha256.lower() != before:
        parser.error("Target SHA256 differs from supplied current-source hash")
    try:
        patched, details = prepare_patch(raw)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    result = {
        "schema_version": "p0-quaternion-test-patch-v1", "target": str(target),
        "utc": datetime.now(timezone.utc).isoformat(), "written": False,
        "before_sha256": before, "after_sha256": sha256(patched), **details,
    }
    if args.write:
        if not args.backup_directory or not args.backup_directory.is_dir():
            parser.error("Write requires an existing backup-directory")
        backup = args.backup_directory / (target.name + ".pre_quaternion_" + before[:16] + ".bak")
        with backup.open("xb") as handle:
            handle.write(raw)
        result["backup"] = str(backup.resolve())
        if target.read_bytes() != raw:
            parser.error("Target changed after preparation; retained backup, no patch applied")
        descriptor, temp_name = tempfile.mkstemp(prefix=".quaternion_test_patch_", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(patched)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, target.stat().st_mode)
            if target.read_bytes() != raw:
                parser.error("Target changed before replacement; no patch applied")
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        if target.read_bytes() != patched:
            raise RuntimeError("Patched target integrity check failed")
        result["written"] = True
    if args.report:
        with args.report.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
