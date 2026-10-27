#!/usr/bin/env python3
"""Create-only batch13 archive, scoped protection and complete SHA readback."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True

D = Path(__file__).resolve().parent
M = Path("/home/trevor/MPC/scheme_A_C3_7_20261014_13")
P = D.parent / "scheme_A_C3_6_adapter_20261013_12"
sys.path.insert(0, str(D.parent / "p1_execution_architecture_20261005_01/authored_D1_C3_5_20261013_v11"))
import acceptance_core_v1 as C


def write_new(path, raw, mode=0o644):
    C.require(not any(p.is_symlink() for p in path.parents), "archive_symlink_parent")
    with path.open("xb") as f:
        f.write(raw)
        os.fchmod(f.fileno(), mode & 0o777)
        f.flush()
        os.fsync(f.fileno())
    C.require(C.Reader().raw(path) == raw, "create_only_readback")


def write_json(path, value):
    write_new(path, (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode())


def protect():
    q = C.Reader().json(D / "postrun/final_QA_current.json")
    C.require(q.get("passed") is True and q.get("stage_qualified") is False
              and q.get("execute_qualified") is False and q.get("research_conclusion") is False, "scoped_final_QA")
    reader = C.Reader(seconds=600, max_bytes=3 * 1024 * 1024 * 1024, max_files=26000)
    for path, digest in q["fixed_source_header_input_hashes"].items():
        C.require(C.digest(reader.raw(Path(path))) == digest, "protected_input_changed:" + path)
    manifest = reader.json(D / "final_frozen_snapshot/manifest.json")
    C.require(manifest.get("all_pairs_verified") is True and len(manifest["files"]) == q["new_frozen_pairs"],
              "new_freeze_population")
    for pin in manifest["files"]:
        for key in ("original", "copy"):
            reader.verify({"path": pin[key], "sha256": pin["sha256"], "bytes": pin["bytes"]})
    env = reader.json(D / "postrun/runtime_env_link_verification_v1.json")
    C.require(env.get("passed") is True and env.get("within_build_SETUP") is True
              and env.get("runtime_env_missing_libraries") is False, "runtime_environment_link_scope")
    for path, pin in env["pins"].items():
        C.require(C.digest(reader.raw(Path(path))) == pin["sha256"]
                  and C.digest(reader.raw(Path(pin["copy"]))) == pin["sha256"], "runtime_file_or_copy_changed")
    spec = importlib.util.spec_from_file_location("c37_parent_protection", P / "archive_v1.py")
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    proof = parent.protect()
    C.require(proof == q["parent_after"], "parent_protection_changed")
    C.require(reader.unchanged(), "protected_inputs_changed_during_check")
    return {"passed": True, "parent": proof, "current_fixed_paths": len(q["fixed_source_header_input_hashes"]),
            "new_frozen_pairs": q["new_frozen_pairs"], "runtime_env_link_file_pairs": len(env["pins"]),
            "runtime_env_within_BUILD_SETUP": True,
            "runtime_env_link_verification_sha256": C.digest(reader.raw(D / "postrun/runtime_env_link_verification_v1.json")),
            "current_QA_sha256": C.digest(reader.raw(D / "postrun/final_QA_current.json")),
            "protected_old_C34_temporary_evidence_count": q["old_C34_temp_content_pins_checked"],
            "actual_Witness_normal_business": q["actual_Witness_normal_business"],
            "normal_business_contract_qualified": False, "stage_qualified": False, "research_conclusion": False}


def population():
    files, directories = [], []
    for root, dirs, names in os.walk(D, followlinks=False):
        for name in dirs:
            path = Path(root) / name
            C.require(stat.S_ISDIR(path.lstat().st_mode), "archive_directory_link_or_special")
            directories.append(str(path.relative_to(D)))
        for name in names:
            path = Path(root) / name
            C.require(stat.S_ISREG(path.lstat().st_mode), "archive_regular_only")
            files.append(path)
    return sorted(files), sorted(directories, key=lambda x: (len(Path(x).parts), x))


def prepare():
    C.require(D.name == "scheme_A_C3_7_20261014_13" and not M.exists() and not M.is_symlink(), "fresh_MPC_batch_required")
    C.require(not (D / "archive_inventory_v2.json").exists() and not (D / "delivery_verification.json").exists()
              and not (D / "batch_status_final.json").exists(), "fresh_archive_prepare_required")
    before = protect()
    status = C.Reader().json(D / "batch_status_prepared.json")
    C.require(status.get("stage_qualified") is False and status.get("research_conclusion") is False, "prepared_status_scope")
    files, directories = population()
    reader = C.Reader(seconds=300, max_bytes=3 * 1024 * 1024 * 1024, max_files=26000)
    pins = []
    for path in files:
        raw = reader.raw(path)
        pins.append({"relative_path": str(path.relative_to(D)), "sha256": C.digest(raw), "bytes": len(raw),
                     "mode": stat.S_IMODE(path.lstat().st_mode)})
    C.require(reader.unchanged(), "prepare_source_population_changed")
    after = protect()
    C.require(before == after, "prepare_protection_before_after")
    inventory = {"schema": "p1-C3.7-owned-worker-Witness-archive-inventory/v2", "source": str(D), "destination": str(M),
                 "files": pins, "directories": directories, "inventory_self_excluded": True,
                 "protection": before, "protection_after_prepare": after, "old_batches_overwritten": False,
                 "stage_qualified": False, "research_conclusion": False}
    write_json(D / "archive_inventory_v2.json", inventory)
    print(json.dumps({"prepared": True, "files_excluding_inventory": len(pins),
                      "bytes": sum(p["bytes"] for p in pins),
                      "inventory_sha256": C.digest(C.Reader().raw(D / "archive_inventory_v2.json"))}))


def deliver(digest):
    C.require(D.name == "scheme_A_C3_7_20261014_13" and not M.exists() and not M.is_symlink()
              and M.parent.is_dir(), "fixed_fresh_destination")
    C.require(not any(p.is_symlink() for p in M.parents), "MPC_parent_link")
    raw = C.Reader().raw(D / "archive_inventory_v2.json")
    C.require(C.digest(raw) == digest, "archive_inventory_identity")
    inventory = C.strict_json(raw)
    C.require(inventory["source"] == str(D) and inventory["destination"] == str(M), "fixed_archive_scope")
    before = protect()
    C.require(before == inventory["protection"] == inventory["protection_after_prepare"], "prepared_protection_identity")
    files, _ = population()
    C.require({str(p.relative_to(D)) for p in files} ==
              {p["relative_path"] for p in inventory["files"]} | {"archive_inventory_v2.json"}, "source_population_changed")
    M.mkdir(exist_ok=False)
    for directory in inventory["directories"]:
        relative = Path(directory)
        C.require(not relative.is_absolute() and ".." not in relative.parts, "relative_directory")
        (M / relative).mkdir(exist_ok=False)
    reader = C.Reader(seconds=600, max_bytes=3 * 1024 * 1024 * 1024, max_files=26000)
    for pin in inventory["files"]:
        relative = Path(pin["relative_path"])
        C.require(not relative.is_absolute() and ".." not in relative.parts, "relative_file")
        content = reader.verify({"path": str(D / relative), "sha256": pin["sha256"], "bytes": pin["bytes"]})
        write_new(M / relative, content, pin["mode"])
    write_new(M / "archive_inventory_v2.json", raw)
    for pin in inventory["files"]:
        for root in (D, M):
            reader.verify({"path": str(root / pin["relative_path"]), "sha256": pin["sha256"], "bytes": pin["bytes"]})
    C.require(C.Reader().raw(D / "archive_inventory_v2.json") == C.Reader().raw(M / "archive_inventory_v2.json") == raw,
              "inventory_pair_readback")
    C.require(reader.unchanged(), "delivery_inputs_changed_during_readback")
    after = protect()
    C.require(before == after, "delivery_protection_before_after")
    verification = {"schema": "p1-C3.7-owned-worker-Witness-delivery-verification/v1", "passed": True,
                    "source": str(D), "destination": str(M), "inventory_sha256": digest,
                    "copied_regular_files": len(inventory["files"]) + 1,
                    "copied_bytes": sum(p["bytes"] for p in inventory["files"]) + len(raw),
                    "full_second_SHA_readback": True, "protected_before": before, "protected_after": after,
                    "metadata_supplements": ["delivery_verification.json", "batch_status_final.json"],
                    "final_regular_files_per_root": len(inventory["files"]) + 3,
                    "actual_Witness_normal_business": before["actual_Witness_normal_business"],
                    "normal_business_contract_qualified": False, "old_batches_overwritten": False,
                    "old_expected_updated": False, "old_failure_deleted": False, "stage_qualified": False,
                    "execute_qualified": False, "research_conclusion": False}
    status = C.Reader().json(D / "batch_status_prepared.json")
    C.require(status.get("stage_qualified") is False and status.get("research_conclusion") is False, "final_status_scope")
    status.update(delivery_verified=True, state="owned_worker_callback_and_Witness_v2_components_complete_archive_verified",
                  delivery_verification=str(M / "delivery_verification.json"), next_plan_current=str(M / "方案A_C3_7后续实施计划_2026-10-14_v2.md"), document_clarification=str(M / "documents/post_freeze_plan_clarification_v1.json"),
                  actual_Witness_normal_business=before["actual_Witness_normal_business"],
                  normal_business_contract_qualified=False, execute_qualified=False)
    for root in (D, M):
        write_json(root / "delivery_verification.json", verification)
        write_json(root / "batch_status_final.json", status)
    for name in verification["metadata_supplements"]:
        C.require(C.Reader().raw(D / name) == C.Reader().raw(M / name), "metadata_pair_readback")
    C.require(len(population()[0]) == verification["final_regular_files_per_root"]
              and sum(p.is_file() for p in M.rglob("*")) == verification["final_regular_files_per_root"], "final_population")
    print(json.dumps(verification, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "deliver"))
    parser.add_argument("--sha")
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare()
    else:
        C.require(type(args.sha) is str and len(args.sha) == 64, "inventory_SHA_required")
        deliver(args.sha)
