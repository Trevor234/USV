#!/usr/bin/env python3
"""Create-only batch13 freeze/QA; exact bounded evidence, never phase qualification."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import shlex
import stat
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True

D = Path(__file__).resolve().parent
N = D.parent / "p1_execution_architecture_20261005_01/authored_D1_C3_7_20261014_v14"
P = D.parent / "scheme_A_C3_6_adapter_20261013_12"
PM = Path("/home/trevor/MPC/scheme_A_C3_6_adapter_20261013_12")
M = Path("/home/trevor/MPC/scheme_A_C3_7_20261014_13")
PARENT_INVENTORY_SHA256 = "d91f54e72f5fadb546030b85097d626d93b6af1e603c4ddc4f7cdca81ccbc1d5"
PARENT_METADATA = {
    "archive_inventory_v1.json": PARENT_INVENTORY_SHA256,
    "delivery_verification.json": "555c7e72d8925837f434da584ae6eaafcb765b0e6af4776925f1519b42f3d606",
    "batch_status_final.json": "edc29fe1612dc26e3e0b1273b763d90bfd0fa908701ebb6136e0291e12d2e78c",
}
DOCUMENTS = (
    "方案A_C3_7实施记录与当前状态_2026-10-14.md",
    "方案A_C3_7后续实施计划_2026-10-14.md",
)
sys.path.insert(0, str(N.parent / "authored_D1_C3_5_20261013_v11"))
import acceptance_core_v1 as C


def write(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parent():
    # Parent module only performs its declared read-only preservation checks.
    return load_module("c37_parent_protection", P / "archive_v1.py").protect()


def verify_parent_pairs(reader):
    inventory_path = P / "archive_inventory_v1.json"
    C.require(C.digest(reader.raw(inventory_path)) == PARENT_INVENTORY_SHA256, "parent_inventory_identity")
    inventory = reader.json(inventory_path)
    C.require(len(inventory["files"]) == 2194, "pinned_parent_inventory_population")
    for row in inventory["files"]:
        rel = Path(row["relative_path"])
        C.require(not rel.is_absolute() and ".." not in rel.parts, "parent_relative_path")
        for root in (P, PM):
            reader.verify({"path": str(root / rel), "sha256": row["sha256"], "bytes": row["bytes"]})
    for name, digest in PARENT_METADATA.items():
        a, b = reader.raw(P / name), reader.raw(PM / name)
        C.require(a == b and C.digest(a) == digest, "parent_metadata_pair:" + name)
    return inventory


def binary_pins(build):
    out = {"runtime": {"path": build["binary"], "sha256": build["binary_sha256"]}}
    for category in ("native_binaries", "auxiliary_binaries"):
        for name, pin in build.get(category, {}).items():
            C.require(name not in out, "duplicate_build_target")
            out[name] = pin
    return out


def source_revision(reader, revision):
    result_path = D / ("build/observer_attempt0" + str(revision) + "/result.json")
    build = reader.json(result_path)
    C.require(build.get("passed") is True, "build_not_completed:" + str(revision))
    pin = build["source_bundle"]
    reader.verify(pin)
    bundle = reader.json(Path(pin["path"]))
    snapshot = result_path.parent / "source_snapshot"
    mappings = {}
    for relative, row in bundle["files"].items():
        rel = Path(relative)
        C.require(not rel.is_absolute() and ".." not in rel.parts, "relative_source")
        C.require(Path(row["path"]) == N / rel, "declared_source_path")
        saved = snapshot / rel
        reader.verify({"path": str(saved), "sha256": row["sha256"], "bytes": row["bytes"]})
        mappings[row["path"]] = str(saved)
        if revision == 2:
            reader.verify(row)
    binaries = binary_pins(build)
    for row in binaries.values():
        reader.verify(row)
        C.require(Path(row["path"]).is_relative_to(N / ("observer/build0" + str(revision))), "build_binary_scope")
    deps_path = result_path.parent / "compiler_dependency_pins.json"
    deps = reader.json(deps_path)
    reader.verify({"path": deps["compiler"], "sha256": deps["compiler_sha256"]})
    C.require(C.digest(reader.raw(result_path.parent / "compile_commands.json")) == deps["compile_commands_sha256"],
              "compile_commands_identity")
    dependency_mappings = []
    for original, digest in deps["files"].items():
        actual = Path(original)
        raw = reader.raw(actual)
        if C.digest(raw) != digest:
            # A superseded source path is expected to differ after repairs.
            # Its immutable saved source is the historical compiler input.
            C.require(revision == 1 and original in mappings, "unmapped_compiler_dependency_changed:" + original)
            actual = Path(mappings[original])
            C.require(C.digest(reader.raw(actual)) == digest, "historical_compiler_source_snapshot_changed")
        dependency_mappings.append({"declared_original": original, "verified_path": str(actual),
                                    "sha256": digest, "historical_source_snapshot": str(actual) != original})
    C.require(deps.get("dependency_count") == len(deps["files"]), "compiler_dependency_population")
    return {"revision": revision, "result_path": str(result_path), "build": build, "source_bundle": pin,
            "source_mappings": mappings, "dependency_file": str(deps_path), "dependencies": dependency_mappings,
            "compiler": deps["compiler"], "binaries": binaries}


def helpers(reader):
    results = []
    for version in (1, 2, 3):
        path = D / ("preregister/helper_pins_v" + str(version) + ".json")
        declared = reader.json(path)
        if version == 1:
            C.require(len(declared["files"]) == 103, "pinned_v1_helper_population")
        rows = []
        for original, pin in declared["files"].items():
            actual = Path(original)
            C.require(actual.is_absolute() and (actual.is_relative_to(N) or actual.is_relative_to(D)),
                      "helper_declared_scope")
            raw = reader.raw(actual)
            if C.digest(raw) != pin["sha256"]:
                C.require(version in (1, 2) and actual.is_relative_to(N), "current_helper_changed")
                actual = D / "preregister/helper_snapshot_v1" / actual.relative_to(N)
                raw = reader.raw(actual)
            C.require(C.digest(raw) == pin["sha256"] and len(raw) == pin["bytes"], "helper_pin_mismatch")
            rows.append({"declared_original": original, "verified_path": str(actual), **pin})
        results.append({"version": version, "pin_file": str(path), "count": len(rows), "files": rows})
    return results


def selected_evidence(reader, current_build):
    registry = reader.json(N / "build_manifest_current.json")
    C.require(type(registry) is list and {b["role"] for b in registry} ==
              {"publisher", "worker", "fixture", "recorder", "observer"} and len(registry) == 5, "current_role_registry")
    selected = [b for b in registry if b["role"] == "observer"][0]
    C.require(selected == current_build, "selected_build02_result_differs")
    source_registry = reader.json(N / "source_bundles_current.json")
    C.require(source_registry["observer"] == current_build["source_bundle"], "selected_source_registry")
    for build in registry:
        reader.verify({"path": build["binary"], "sha256": build["binary_sha256"]})
        reader.verify(build["source_bundle"])
        bundle = reader.json(Path(build["source_bundle"]["path"]))
        for row in bundle["files"].values():
            reader.verify(row)
    native = reader.json(D / "component/native_current_assessment.json")
    actual_native = reader.json(D / "component/native_attempt02/result.json")
    C.require(native.get("passed") is True and actual_native.get("passed") is True, "native_current_not_passed")
    rows = actual_native["tests"]
    C.require(set(rows) == set(current_build["native_binaries"]), "current_native_target_population")
    for name, row in rows.items():
        C.require(row.get("passed") is True and row["returncode"] == 0 and type(row["count"]) is int
                  and row["count"] > 0 and row["failed"] == row["errors"] == 0, "current_native_target_failed:" + name)
        C.require(row["binary_sha256"] == current_build["native_binaries"][name]["sha256"], "current_native_binary_identity")
        xml_path = D / "component/native_attempt02" / name / "gtest.xml"
        root = ET.fromstring(reader.raw(xml_path))
        C.require(int(root.attrib["tests"]) == row["count"] and int(root.attrib["failures"]) == 0
                  and int(root.attrib.get("errors", 0)) == 0, "native_XML_population")
    actual_count = sum(row["count"] for row in rows.values())
    C.require(actual_native["count"] == native["count"] == actual_count, "current_native_population_count")
    original_run = reader.json(D / "runs/positive01/result.json")
    original_check = reader.json(D / "runs/positive01/check_result.json")
    C.require(original_run.get("passed") is True and original_check.get("passed") is False,
              "original_driver_success_and_checker_failure_must_remain")
    original_run_dir = Path(original_check["run_dir"])
    C.require(original_run_dir.is_relative_to(N / "runs") and original_run_dir.is_dir(), "original_failed_run_raw_retained")
    original_native = reader.json(D / "component/native_attempt01/result.json")
    C.require(original_native.get("passed") is False, "original_native_failure_must_remain")
    reader.raw(D / "component/native_attempt01/test_c34_lease_matrix/run.log")
    run = reader.json(D / "runs/positive02/result.json")
    check = reader.json(D / "runs/positive02/check_result.json")
    C.require(run.get("passed") is True and check.get("passed") is True, "owned_run_not_passed")
    C.require(check["profile"] == "closed_shadow_observation", "actual_checker_profile")
    witness = check["witness_v2"]
    basis = witness["basis"]
    C.require(witness.get("passed") is True and basis.get("passed") is True
              and basis.get("observation_complete") is True, "actual_Witness_v2_observation")
    C.require(type(basis.get("normal_business")) is bool, "actual_normal_business_type")
    C.require(check.get("normal_business_contract_qualified") is False
              and all(v is False for v in check["qualifications"].values()), "architectural_qualification_must_remain_false")
    C.require(check["input_sha256_before"] == check["input_sha256_after"], "checked_run_population_mutated")
    for field in ("input_sha256_before", "author_asset_sha256", "checker_dependencies"):
        for path, digest in check[field].items():
            C.require(C.digest(reader.raw(Path(path))) == digest, "actual_checked_input_changed:" + path)
    C.require(C.digest(reader.raw(N / "check_c37_owned_run_v2.py")) == check["checker_sha256"], "actual_checker_identity")
    # Check the complete author run tree, including failures and raw CDR/SQLite;
    # the checker separately attests its closed entire-population comparisons.
    actual_run = Path(check["run_dir"])
    C.require(actual_run.is_relative_to(N / "runs") and actual_run.is_dir(), "actual_author_run_scope")
    return native, actual_native, run, check


def executable_elf(path):
    # Classify only owned build files; ET_REL object files are not run binaries.
    C.require(stat.S_ISREG(path.lstat().st_mode), "build_regular_only")
    with path.open("rb") as f:
        header = f.read(20)
    if len(header) < 20 or header[:4] != b"\x7fELF" or header[5] not in (1, 2):
        return False
    return struct.unpack("<H" if header[5] == 1 else ">H", header[16:18])[0] in (2, 3)


def runtime_libraries(reader, binaries):
    helper = D / "build_and_verify_v2.py"
    if not helper.exists():
        helper = D / "build_and_verify_v1.py"
    reader.raw(helper)
    build_helper = load_module("c37_runtime_environment", helper)
    C.require(type(build_helper.SETUP) is str and bool(build_helper.SETUP), "explicit_build_runtime_setup")
    logs = D / "postrun/runtime_ldd_v1"
    logs.mkdir(exist_ok=False)
    files, records = {}, []
    for index, binary in enumerate(sorted(binaries)):
        reader.raw(binary)
        script = "set -e\n" + build_helper.SETUP + "\nexec " + shlex.join(["ldd", binary]) + "\n"
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=20)
        log = logs / (f"{index + 1:03d}_" + Path(binary).name + ".log")
        with log.open("x", encoding="utf-8") as f:
            f.write(result.stdout + result.stderr)
        C.require(result.returncode == 0 and "not found" not in result.stdout + result.stderr,
                  "runtime_library_missing_within_setup:" + binary)
        resolved = []
        for item in re.findall(r"(?:=>\s+)?(/[^\s()]+)", result.stdout):
            path = Path(item).resolve(strict=True)
            files[str(path)] = C.digest(reader.raw(path))
            resolved.append(str(path))
        C.require(bool(resolved), "runtime_library_population_empty:" + binary)
        records.append({"binary": binary, "binary_sha256": C.digest(reader.raw(Path(binary))),
                        "returncode": result.returncode, "log": str(log), "resolved_paths": sorted(set(resolved))})
    result = {"schema": "C3.7-runtime-link-pins/v1", "passed": True, "within_build_SETUP": True,
              "build_helper": str(helper), "build_helper_sha256": C.digest(reader.raw(helper)),
              "SETUP_sha256": hashlib.sha256(build_helper.SETUP.encode()).hexdigest(), "files": files,
              "binaries": records, "scope": "ldd within actual ROS build SETUP and linked-file bytes at finalization; no runtime continuity, complete OS or WCET qualification"}
    write(D / "postrun/runtime_shared_library_pins.json", result)
    return result


def document_links(reader):
    result = []
    for name in DOCUMENTS:
        path = D / name
        raw = reader.raw(path)
        for target in re.findall(r"\]\((/[^)]+)\)", raw.decode("utf-8")):
            actual = Path(re.sub(r":\d+$", "", target))
            projected = actual.is_relative_to(M)
            if projected:
                actual = D / actual.relative_to(M)
            C.require(actual.exists(), "document_target_missing:" + target)
            result.append({"document": str(path), "target": target, "verified_local_target": str(actual),
                           "fresh_archive_projection": projected})
    return result


def main():
    C.require(D.name == "scheme_A_C3_7_20261014_13", "fixed_batch13_scope")
    C.require(not (D / "final_frozen_snapshot").exists() and not (D / "postrun/final_QA_current.json").exists(),
              "fresh_finalization_required")
    before = parent()
    reader = C.Reader(seconds=900, max_bytes=3 * 1024 * 1024 * 1024, max_files=24000)
    parent_inventory = verify_parent_pairs(reader)
    revisions = [source_revision(reader, version) for version in (1, 2)]
    helper_versions = helpers(reader)
    native, actual_native, run, check = selected_evidence(reader, revisions[1]["build"])
    temp = reader.json(D / "review/c34_existing_temporary_evidence_v1.json")
    C.require(temp.get("touched") is False, "historical_C34_temp_must_remain_untouched")
    for path, pin in temp["files"].items():
        reader.verify({"path": path, **pin})
    # Gather every executable/shared-library build output, including initial
    # failed native attempt and CMake compiler probes; do not erase old evidence.
    binaries = {}
    for revision in revisions:
        for row in revision["binaries"].values():
            binaries[row["path"]] = row["sha256"]
        build_dir = N / ("observer/build0" + str(revision["revision"]))
        for path in sorted(build_dir.rglob("*")):
            if path.is_file() and executable_elf(path):
                binaries[str(path)] = C.digest(reader.raw(path))
    runtime = runtime_libraries(reader, binaries)
    # The frozen v2 predicate CLI failed only its 64KiB report writer. Preserve it,
    # verify the separate analysis report writer/receipt and its exact v2 identity.
    receipt=reader.json(D/'runs/positive02/analysis_writer_receipt_v1.json')
    writerpins=reader.json(D/'postrun/analysis_writer_pins_v1.json')
    C.require(receipt['passed'] is True and receipt['predicate_modified'] is False and
              receipt['release_writer_or_budget_changed'] is False and
              receipt['report_sha256']==C.digest(reader.raw(D/'runs/positive02/check_result.json')) and
              receipt['report_bytes']==len(reader.raw(D/'runs/positive02/check_result.json')) and
              receipt['writer_sha256']==writerpins['writer_sha256']==C.digest(reader.raw(D/'analyze_current_owned_v1.py')) and
              receipt['checker_sha256']==writerpins['checker_sha256']==check['checker_sha256'], 'analysis_writer_receipt')
    reader.raw(D/'runs/positive02/check_owned_v2.log')
    C.require(b'output exceeds budget' in reader.raw(D/'runs/positive02/check_owned_v2.log'),'original_CLI_report_failure_retained')
    pure=reader.json(D/'component/checker_v2_peer_attempt01/result.json')
    C.require(pure['passed'] is True,'checker_v2_component_tests')
    links = document_links(reader)
    root = D / "final_frozen_snapshot"
    root.mkdir(exist_ok=False)
    candidates = []
    for path in sorted(N.rglob("*")):
        if path.is_file() and not any(p.startswith("build") or p == "__pycache__" for p in path.relative_to(N).parts[:-1]):
            C.require(stat.S_ISREG(path.lstat().st_mode), "author_regular_only")
            candidates.append(("author_and_entire_raw_runs", path, str(path)))
    for revision in revisions:
        for original, saved in revision["source_mappings"].items():
            candidates.append(("build_source_snapshot_v" + str(revision["revision"]), Path(saved), original))
        for row in revision["dependencies"]:
            candidates.append(("compiler_dependency_v" + str(revision["revision"]), Path(row["verified_path"]), row["declared_original"]))
        candidates.append(("compiler_v" + str(revision["revision"]), Path(revision["compiler"]), revision["compiler"]))
    for version in helper_versions:
        for row in version["files"]:
            candidates.append(("helper_v" + str(version["version"]), Path(row["verified_path"]), row["declared_original"]))
    for path in binaries:
        candidates.append(("all_build_binaries", Path(path), path))
    for path in runtime["files"]:
        candidates.append(("runtime_link_within_SETUP", Path(path), path))
    for path in temp["files"]:
        candidates.append(("preexisting_C34_temporary_evidence", Path(path), path))
    for path in [Path(__file__).resolve(), D / "archive_v1.py", D / "postrun/runtime_shared_library_pins.json",
                 D/'analyze_current_owned_v1.py',D/'postrun/analysis_writer_pins_v1.json',D/'runs/positive02/analysis_writer_receipt_v1.json',D/'component/checker_v2_peer_attempt01/result.json',D/'runs/positive02/check_owned_v2.log',*[D / name for name in DOCUMENTS]]:
        candidates.append(("finalization_tools_and_documents", path, str(path)))
    for path in [D / "runs/positive01/result.json", D / "runs/positive01/check_result.json",
                 D / "component/native_attempt01/result.json",
                 D / "component/native_attempt01/test_c34_lease_matrix/run.log"]:
        candidates.append(("original_current_batch_failure_evidence", path, str(path)))
    pairs, seen = [], {}
    for kind, path, logical in candidates:
        physical = str(path)
        if physical in seen:
            seen[physical]["declarations"].append({"kind": kind, "declared_original": logical})
            continue
        raw = reader.raw(path)
        copied = root / (f"{len(pairs) + 1:04d}_" + path.name)
        with copied.open("xb") as f:
            f.write(raw)
        C.require(reader.raw(copied) == raw, "new_frozen_pair")
        row = {"kind": kind, "original": physical, "copy": str(copied), "sha256": C.digest(raw), "bytes": len(raw),
               "declarations": [{"kind": kind, "declared_original": logical}]}
        pairs.append(row)
        seen[physical] = row
    manifest = {"schema": "C3.7-final-freeze/v1", "files": pairs, "new_frozen_pairs": len(pairs),
                "all_pairs_verified": True, "historical_source_rebinding_performed": False,
                "compiler_dependency_mappings": {str(r["revision"]): r["dependencies"] for r in revisions},
                "stage_qualified": False, "research_conclusion": False,
                "scope": "declared current/historical sources, all raw author runs, all build01/build02 ELF binaries, helpers, actual compiler dependencies, ldd-within-SETUP and finite old C34 temp files; no full machine/runtime continuity/plant/WCET claim"}
    write(root / "manifest.json", manifest)
    reader.raw(root / "manifest.json")
    runtime_env = {"schema": "C3.7-runtime-environment-link-verification/v1", "passed": True,
                   "within_build_SETUP": True, "runtime_env_missing_libraries": False,
                   "runtime_link_metadata": str(D / "postrun/runtime_shared_library_pins.json"),
                   "pins": {path: {"sha256": digest, "copy": seen[path]["copy"]} for path, digest in runtime["files"].items()},
                   "scope": runtime["scope"]}
    write(D / "postrun/runtime_env_link_verification_v1.json", runtime_env)
    reader.raw(D / "postrun/runtime_env_link_verification_v1.json")
    C.require(reader.unchanged(), "inputs_changed_during_finalization")
    after = parent()
    C.require(before == after, "parent_protection_changed")
    qa = {"schema": "C3.7-final-QA/v1", "passed": True, "parent_before": before, "parent_after": after,
          "parent_batch12_inventory_sha256": PARENT_INVENTORY_SHA256,
          "parent_batch12_inventory_pairs_checked": len(parent_inventory["files"]),
          "parent_batch12_metadata_pairs_checked": len(PARENT_METADATA),
          "selected_build_result": revisions[1]["result_path"],
          "selected_owned_run_result": str(D / "runs/positive02/result.json"),
          "selected_owned_run_check": str(D / "runs/positive02/check_result.json"),
          "source_bundle_sha256": revisions[1]["source_bundle"]["sha256"],
          "historical_build01_source_snapshot_verified": True, "historical_failure_evidence_retained": True,
          "original_positive01_checker_failure_sha256": C.digest(reader.raw(D / "runs/positive01/check_result.json")),
          "original_native_attempt01_failure_sha256": C.digest(reader.raw(D / "component/native_attempt01/result.json")),
          "compiler_dependency_counts": {str(r["revision"]): len(r["dependencies"]) for r in revisions},
          "helper_pin_counts": {str(v["version"]): v["count"] for v in helper_versions},
          "all_build_binaries_frozen": len(binaries), "runtime_shared_library_count": len(runtime["files"]),
          "runtime_link_verification_within_SETUP": True, "new_frozen_pairs": len(pairs),
          "native_count": actual_native["count"], "original_CLI_report_failure_retained": True, "analysis_writer_predicate_changed": False, "analysis_report_bytes": receipt["report_bytes"], "owned_driver_complete": True,
          "owned_closed_shadow_observation_consistency_passed": True,
          "actual_Witness_observation_complete": check["witness_v2"]["basis"]["observation_complete"],
          "actual_Witness_business_ready_observed": check["witness_v2"]["basis"]["business_ready_observed"],
          "actual_Witness_normal_business": check["witness_v2"]["basis"]["normal_business"],
          "normal_business_contract_qualified": False, "actual_checker_sha256": check["checker_sha256"],
          "selected_actual_check_sha256": C.digest(reader.raw(D / "runs/positive02/check_result.json")),
          "old_C34_temp_content_pins_checked": len(temp["files"]), "local_document_links_checked": len(links),
          "document_links": links, "fixed_source_header_input_hashes": dict(reader.hashes),
          "old_expected_updated": False, "old_failure_deleted": False, "stage_qualified": False,
          "execute_qualified": False, "research_conclusion": False, "unknowns": check["unknowns"]}
    write(D / "postrun/final_QA_current.json", qa)
    print(json.dumps({k: v for k, v in qa.items() if k not in ("fixed_source_header_input_hashes", "document_links")},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
