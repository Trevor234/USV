#!/usr/bin/env python3
"""Insert only test helpers and GTests into the current research fixture.

No production file is read or written. Guards allow independent quaternion
test insertion before/after this patch without replacing the whole fixture.
"""

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import sys


HELPER_START = "P0_REFERENCE_TEST_ACCESS_V1_BEGIN"
HELPER_END = "P0_REFERENCE_TEST_ACCESS_V1_END"
TEST_START = "P0_REFERENCE_REAL_FUNCTION_TESTS_V1_BEGIN"
TEST_END = "P0_REFERENCE_REAL_FUNCTION_TESTS_V1_END"
HELPER_ANCHOR = "  static std::shared_ptr<MpcControllerNode> make("
TEST_ANCHOR = "\n}  // namespace\n"
TARGET = "usv_mpc_ws/src/usv_mpc_cpp/test/test_research_contract.cpp"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def checked_text(data):
    return data.decode("utf-8").replace("\r\n", "\n")


def inside(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def render(original, helper, tests):
    markers = [HELPER_START, HELPER_END, TEST_START, TEST_END]
    counts = [original.count(marker) for marker in markers]
    if counts == [1, 1, 1, 1]:
        return original, False
    if counts != [0, 0, 0, 0]:
        raise ValueError("partial or duplicate reference patch markers; inspect without overwriting")
    if original.count(HELPER_ANCHOR) != 1 or original.count(TEST_ANCHOR) != 1:
        raise ValueError("fixture anchors are not unique")
    if "class MpcControllerNodeTestAccess" not in original or "class ResearchContract" not in original:
        raise ValueError("expected friend access class and fixture are missing")
    if any(marker not in (helper + tests) for marker in markers):
        raise ValueError("required markers absent from fragment inputs")
    updated = original.replace(HELPER_ANCHOR, helper + HELPER_ANCHOR, 1)
    updated = updated.replace(TEST_ANCHOR, "\n" + tests + TEST_ANCHOR, 1)
    return updated, True


def apply(workspace, backup_dir, expected_sha256=None, check=False):
    workspace = workspace.resolve()
    backup_dir = backup_dir.resolve()
    target = workspace / TARGET
    if not inside(target, workspace) or not inside(backup_dir, workspace):
        raise ValueError("target and new backup directory must stay within workspace")
    original_bytes = target.read_bytes()
    original_sha = sha256(original_bytes)
    if expected_sha256 is not None and original_sha != expected_sha256.lower():
        raise ValueError("current fixture SHA differs from explicit expected SHA")
    folder = Path(__file__).resolve().parent
    helper = checked_text((folder / "reference_access.inc").read_bytes())
    tests = checked_text((folder / "reference_tests.inc").read_bytes())
    updated, changed = render(checked_text(original_bytes), helper, tests)
    report = {"target": str(target), "fixture_before_sha256": original_sha,
              "helper_fragment_sha256": sha256(helper.encode()),
              "tests_fragment_sha256": sha256(tests.encode()),
              "changed": changed, "check_only": check,
              "production_modified": False}
    if not changed or check:
        return report
    backup_dir.mkdir(parents=True, exist_ok=False)
    (backup_dir / "test_research_contract.cpp.before").write_bytes(original_bytes)
    newline = "\r\n" if b"\r\n" in original_bytes else "\n"
    updated_bytes = updated.replace("\n", newline).encode("utf-8")
    # Keep concurrent independent patches: fail instead of writing over a change.
    if target.read_bytes() != original_bytes:
        raise RuntimeError("fixture changed after guard; no target write performed")
    target.write_bytes(updated_bytes)
    report["fixture_after_sha256"] = sha256(target.read_bytes())
    report["backup_directory"] = str(backup_dir)
    patch = "".join(difflib.unified_diff(checked_text(original_bytes).splitlines(True),
                                       updated.splitlines(True),
                                       fromfile=TARGET, tofile=TARGET))
    (backup_dir / "reference_tests.patch").write_text(patch, encoding="utf-8")
    (backup_dir / "apply.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = apply(args.workspace, args.backup_dir, args.expected_sha256, args.check)
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"applied": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
