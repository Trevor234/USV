#!/usr/bin/env python3
"""F4-hash-bound, single-function atomic solve-qualification patch.

The original source is read on the owner-provided workspace. Only the first
state lock immediately preceding current_state assignment is changed. No full
source payload is transported. Default dry-run; write needs all byte guards.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
MARKER = "P1_ATOMIC_DYNAMIC_FREEZE_V1"
CPP = "src/usv_mpc_cpp/src/mpc_node.cpp"
HEADER = "src/usv_mpc_cpp/include/usv_mpc_cpp/mpc_node.hpp"
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_][A-Za-z_0-9]*|\d+|[^\s]')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pattern(old):
    return r"\s*".join(re.escape(t) for t in TOKEN.findall(old))


def function_region(text, name):
    definitions = list(re.finditer(r"(?m)^\s*void\s+MpcControllerNode::" + re.escape(name) + r"\s*\(", text))
    if len(definitions) != 1:
        raise ValueError("expected one definition of " + name)
    start = definitions[0].start()
    next_definition = re.search(r"(?m)^.*MpcControllerNode::[A-Za-z_]\w*\s*\(", text[definitions[0].end():])
    end = definitions[0].end() + next_definition.start() if next_definition else len(text)
    return start, end


def prepare_cpp(raw):
    text = raw.decode("utf-8")
    if MARKER in text:
        raise ValueError("atomic gate already present")
    if "P0_REFERENCE_PREDICTION_V1" not in text:
        raise ValueError("required F4 telemetry marker missing")
    start, end = function_region(text, "run_dynamic_mpc_")
    region = text[start:end]
    old = "std::lock_guard<std::mutex> lk(state_lock_); current_state <<"
    matches = list(re.finditer(pattern(old), region))
    if len(matches) != 1:
        raise ValueError("expected exactly one state-lock/current-state freeze anchor")
    match = matches[0]
    for required in ("build_reference_", "enforce_solve_deadline_", "observe_reference", "mpc_->solve"):
        if required not in region:
            raise ValueError("F4 dynamic solve prerequisite missing: " + required)
    if "can_solve_" in region:
        raise ValueError("unexpected existing qualification check in dynamic entry")
    replacement = (HERE / "atomic_freeze_gate.cpp.txt").read_text(encoding="utf-8").rstrip("\n")
    # Keep the original indentation preceding the anchor; snippets are already
    # indented for the block and the owner's formatter can normalize afterward.
    replacement = replacement.lstrip(" ")
    updated_region = region[:match.start()] + replacement + region[match.end():]
    result = text[:start] + updated_region + text[end:]
    if result[:start] != text[:start] or result[start + len(updated_region):] != text[end:]:
        raise ValueError("unexpected modification outside dynamic solve entry")
    for expression in (r"\bmpc_\s*->\s*solve\s*\(", r"\bbuild_reference_\s*\("):
        if len(re.findall(expression, result)) != len(re.findall(expression, text)):
            raise ValueError("solve/reference invocation count changed")
    return result.encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-guard", type=Path, default=HERE / "source_guard.json")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    workspace = args.workspace.expanduser().resolve()
    guard = json.loads(args.source_guard.read_text(encoding="utf-8"))
    if guard.get("baseline_id") != "F4_20261005_config_reference_01":
        raise ValueError("F4 baseline identity guard required")
    cpp, header = workspace / CPP, workspace / HEADER
    for path in (cpp, header):
        if not path.resolve().is_relative_to(workspace):
            raise ValueError("source path resolves outside requested workspace")
    cpp_raw, header_raw = cpp.read_bytes(), header.read_bytes()
    if sha(cpp_raw) != guard["source_sha256"][CPP] or sha(header_raw) != guard["source_sha256"][HEADER]:
        raise ValueError("exact F4 cpp/header SHA256 guard failed")
    updated = prepare_cpp(cpp_raw)
    if sha(updated) == sha(cpp_raw):
        raise ValueError("no source edit")
    backup = cpp.with_name(cpp.name + ".pre_atomic_dynamic_freeze_v1")
    if args.write:
        if backup.exists():
            raise ValueError("refuse to overwrite existing source backup")
        if cpp.read_bytes() != cpp_raw or header.read_bytes() != header_raw:
            raise ValueError("source changed after validation")
        backup.write_bytes(cpp_raw)
        cpp.write_bytes(updated)
        if header.read_bytes() != header_raw:
            raise RuntimeError("untouched header changed externally during write")
    print(json.dumps({"written": args.write, "baseline_id": guard["baseline_id"],
        "cpp_before_sha256": sha(cpp_raw), "cpp_after_sha256_before_format": sha(updated),
        "header_sha256_unchanged": sha(header_raw), "marker": MARKER,
        "changed_scope": "run_dynamic_mpc_ first state-lock/current-state anchor only"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
