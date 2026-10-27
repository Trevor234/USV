#!/usr/bin/env python3
"""Read-only declared-asset protection; new batch14 preflight outputs only."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
W = Path("/home/trevor/USV")
N = D.parent / "p1_execution_architecture_20261005_01/authored_D1_C3_8_20261014_v15"
P = D.parent / "scheme_A_C3_7_20261014_13"
M = Path("/home/trevor/MPC/scheme_A_C3_7_20261014_13")
HEAD = "78999cf380c0b0dd7f545e4dc8103b7c4c2f7b15"
BRANCH = "codex/scheme-c-rl"
BUSINESS_SHA256 = "d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5"
INVENTORY_SHA256 = "53fc95e30ccf0b29d84ed80e68ce516b5f2952dc14d996c125eb8552e8ad035f"
METADATA = {
    "archive_inventory_v2.json": INVENTORY_SHA256,
    "delivery_verification.json": "438dd20e440f936910e7929a16f13069893a5e88f371c8e1751dae818583bdc2",
    "batch_status_final.json": "b9820dedcffe28f5917fd906d5c258e831caf8ba028d9038fc1839557386bee0",
}
POST_FREEZE_PINS = {
    "方案A_C3_7后续实施计划_2026-10-14_v2.md": "8534fc4dc6f43e3a5c9365b15efe5f86c61d05dde0b14ec370330442646511cd",
    "documents/post_freeze_plan_clarification_v1.json": "29580fa538bb6eceb542c5ed4f8b30a24c962c02a40add1bd806ef50076890af",
    "archive_v2.py": "3c0b08be80d44d73377e09066d02f56dcc040cbcdd804df135cf366ac14868ad",
}
QA_SHA256 = "a63801ae605babf9a1112bea984b584f0f93d5a23be010fca4c017540fbaa8b4"
sys.path.insert(0, str(D.parent / "p1_execution_architecture_20261005_01/authored_D1_C3_5_20261013_v11"))
import acceptance_core_v1 as C


def git(args, allow_failure=False):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(["git", "--no-optional-locks", *args], cwd=W, env=env,
                            capture_output=True, timeout=30)
    C.require(len(result.stdout) + len(result.stderr) <= 8 * 1024 * 1024, "finite_git_output")
    if not allow_failure:
        C.require(result.returncode == 0, "git_read_failed:" + args[0])
    return result


def workspace():
    exclude = [".", ":(exclude).gitignore"]
    original_diff = git(["diff", "--binary", "--", *exclude]).stdout
    head_diff = git(["diff", "HEAD", "--binary", "--", *exclude]).stdout
    staged_business = git(["diff", "--cached", "--binary", "--", *exclude]).stdout
    names = [x.decode("utf-8") for x in git(["diff", "HEAD", "--name-only", "-z", "--", *exclude]).stdout.split(b"\0") if x]
    head = git(["rev-parse", "HEAD"]).stdout.decode().strip()
    branch = git(["branch", "--show-current"]).stdout.decode().strip()
    C.require(head == HEAD and branch == BRANCH, "original_git_identity_changed")
    C.require(len(names) == 24 and len(original_diff) == len(head_diff) == 151961
              and C.digest(original_diff) == C.digest(head_diff) == BUSINESS_SHA256,
              "original_24_business_dirty_changed")
    C.require(staged_business == b"", "original_business_staging_changed")
    status = git(["status", "--porcelain=v1", "--branch", "--untracked-files=all"]).stdout
    staged_all = git(["diff", "--cached", "--binary"]).stdout
    gitignore = (W / ".gitignore").read_bytes()
    submodules = git(["submodule", "status", "--recursive"], allow_failure=True)
    return {
        "HEAD": head, "branch": branch, "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "business_tracked_files": sorted(names), "business_tracked_count": len(names),
        "business_diff_bytes": len(original_diff), "business_diff_sha256": C.digest(original_diff),
        "business_HEAD_diff_sha256": C.digest(head_diff), "staged_business_diff_sha256": C.digest(staged_business),
        "staged_all_diff_bytes": len(staged_all), "staged_all_diff_sha256": C.digest(staged_all),
        "gitignore_bytes": len(gitignore), "gitignore_sha256": C.digest(gitignore),
        "status_porcelain": status.decode("utf-8"), "status_porcelain_sha256": C.digest(status),
        "submodule_status_returncode": submodules.returncode,
        "submodule_status": submodules.stdout.decode("utf-8", errors="replace"),
        "submodule_status_stderr": submodules.stderr.decode("utf-8", errors="replace"),
        "git_optional_locks_disabled": True,
        "scope": "original HEAD/branch and 24 business dirty files are required stable; other staged/metadata/untracked/submodule state is recorded without mutation",
    }


def regular_population(root):
    files, directories = set(), set()
    for base, dirs, names in os.walk(root, followlinks=False):
        for name in dirs:
            p = Path(base) / name
            C.require(stat.S_ISDIR(p.lstat().st_mode), "sealed_directory_link_or_special:" + str(p))
            directories.add(str(p.relative_to(root)))
        for name in names:
            p = Path(base) / name
            C.require(stat.S_ISREG(p.lstat().st_mode), "sealed_file_link_or_special:" + str(p))
            files.add(str(p.relative_to(root)))
    return files, directories


def previous_protection():
    spec = importlib.util.spec_from_file_location("c38_previous_protection", P / "archive_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.protect()


def collect():
    C.require(D.name == "scheme_A_C3_8_20261014_14", "fixed_new_batch_scope")
    before_workspace = workspace()
    reader = C.Reader(seconds=900, max_bytes=3 * 1024 * 1024 * 1024, max_files=18000)
    for name, digest in METADATA.items():
        original, archived = reader.raw(P / name), reader.raw(M / name)
        C.require(original == archived and C.digest(original) == digest, "sealed_metadata_pair:" + name)
    inventory = reader.json(P / "archive_inventory_v2.json")
    delivery = reader.json(P / "delivery_verification.json")
    status = reader.json(P / "batch_status_final.json")
    C.require(inventory["source"] == str(P) and inventory["destination"] == str(M)
              and len(inventory["files"]) == 2860, "sealed_inventory_scope")
    C.require(delivery.get("passed") is True and delivery.get("full_second_SHA_readback") is True
              and delivery["inventory_sha256"] == INVENTORY_SHA256
              and delivery["final_regular_files_per_root"] == 2863, "sealed_delivery_record")
    C.require(status.get("stage_qualified") is False and status.get("research_conclusion") is False,
              "sealed_status_qualification_scope")
    for rel, digest in POST_FREEZE_PINS.items():
        for root in (P, M):
            C.require(C.digest(reader.raw(root / rel)) == digest, "post_freeze_document_or_helper_changed:" + rel)
    C.require(C.digest(reader.raw(P / "postrun/final_QA_current.json")) == QA_SHA256, "sealed_QA_identity")
    qa = reader.json(P / "postrun/final_QA_current.json")
    C.require(qa.get("passed") is True and qa["new_frozen_pairs"] == 1927
              and len(qa["fixed_source_header_input_hashes"]) == 8311, "sealed_QA_declared_population")
    C.require(qa.get("actual_Witness_observation_complete") is True
              and qa.get("actual_Witness_business_ready_observed") is False
              and qa.get("actual_Witness_normal_business") is False
              and qa.get("normal_business_contract_qualified") is False, "sealed_Witness_facts")
    clarification = reader.json(P / "documents/post_freeze_plan_clarification_v1.json")
    C.require(clarification.get("original_QA_retained") is True
              and clarification.get("source_binary_configuration_or_predicates_changed") is False
              and clarification["current_plan_sha256"] == POST_FREEZE_PINS["方案A_C3_7后续实施计划_2026-10-14_v2.md"],
              "post_freeze_clarification_scope")
    before = previous_protection()
    C.require(before == inventory["protection"] == inventory["protection_after_prepare"]
              == delivery["protected_before"] == delivery["protected_after"], "sealed_previous_proof_changed")
    expected = set(METADATA)
    for pin in inventory["files"]:
        rel = Path(pin["relative_path"])
        C.require(not rel.is_absolute() and ".." not in rel.parts and str(rel) not in expected,
                  "unique_normalized_inventory_path")
        expected.add(str(rel))
        for root in (P, M):
            reader.verify({"path": str(root / rel), "sha256": pin["sha256"], "bytes": pin["bytes"]})
    C.require(len(expected) == 2863, "complete_sealed_file_population")
    for root in (P, M):
        files, dirs = regular_population(root)
        C.require(files == expected and dirs == set(inventory["directories"]), "sealed_root_population_changed:" + str(root))
    # Original failures are evidence, not candidates for reassessment or deletion.
    C.require(reader.json(P / "component/native_attempt01/result.json").get("passed") is False,
              "original_native_failure_retained")
    C.require(reader.json(P / "runs/positive01/check_result.json").get("passed") is False,
              "original_owned_checker_failure_retained")
    C.require(reader.unchanged(), "sealed_pairs_changed_during_preflight")
    after = previous_protection()
    C.require(before == after, "previous_protection_before_after")
    after_workspace = workspace()
    for field in ("HEAD", "branch", "boot_id", "business_tracked_files", "business_tracked_count",
                  "business_diff_bytes", "business_diff_sha256", "business_HEAD_diff_sha256", "staged_business_diff_sha256"):
        C.require(before_workspace[field] == after_workspace[field], "original_workspace_changed:" + field)
    proof = {
        "schema": "C3.8-declared-preservation-proof/v1", "passed": True,
        "previous_protection": after, "previous_QA_sha256": QA_SHA256,
        "previous_inventory_sha256": INVENTORY_SHA256,
        "previous_inventory_pairs_checked": 2860, "previous_metadata_pairs_checked": 3,
        "previous_regular_files_per_root": 2863, "previous_complete_root_populations_verified": True,
        "previous_fixed_QA_paths_checked": 8311, "previous_frozen_pairs_checked": 1927,
        "post_freeze_document_and_helper_pins": POST_FREEZE_PINS,
        "HEAD": after_workspace["HEAD"], "branch": after_workspace["branch"],
        "boot_id": after_workspace["boot_id"], "business_tracked_count": 24,
        "business_diff_bytes": 151961, "business_diff_sha256": BUSINESS_SHA256,
        "staged_business_diff_sha256": after_workspace["staged_business_diff_sha256"],
        "sealed_input_sha256": dict(reader.hashes),
        "old_expected_updated": False, "old_failure_deleted": False,
        "stage_qualified": False, "execute_qualified": False, "research_conclusion": False,
        "scope": "declared frozen and inventoried assets only; no complete OS, current endpoint, plant, WCET or research qualification",
    }
    return proof, before_workspace, after_workspace


def protect():
    """Stable read-only proof for later before/after comparisons."""
    return collect()[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=D / "preflight/workspace_initial.json")
    args = parser.parse_args()
    C.require(args.output.is_absolute() and args.output.parent == D / "preflight", "new_preflight_output_only")
    C.require(not args.output.exists() and not args.output.is_symlink(), "create_only_preflight")
    try:
        proof, before, after = collect()
        result = {
            "schema": "C3.8-preflight/v1", "passed": True, "client_date": "2026-10-14",
            "new_batch": str(D), "new_author": str(N), "protection": proof,
            "workspace_before": before, "workspace_after": after,
            "workspace_other_state_changed": before != after,
            "owned_endpoint_capability_checked": False,
            "controlled_owned_close_matrix_status": "not_run",
            "current_phase_status": {"B4": "unknown", "M0b": "unknown", "B5": "unknown", "M4": "unknown"},
            "stage_qualified": False, "execute_qualified": False, "research_conclusion": False,
        }
    except Exception as error:
        result = {"schema": "C3.8-preflight/v1", "passed": False, "client_date": "2026-10-14",
                  "new_batch": str(D), "new_author": str(N),
                  "error": type(error).__name__ + ": " + str(error),
                  "old_failure_deleted": False, "stage_qualified": False,
                  "execute_qualified": False, "research_conclusion": False}
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        f.write("\n")
    C.require(C.Reader().json(args.output) == result, "new_preflight_readback")
    print(json.dumps({"passed": result["passed"], "output": str(args.output),
                      "error": result.get("error"),
                      "scope": "declared asset/workspace preservation only; endpoints and diagnostic runs not_run"},
                     ensure_ascii=False))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
