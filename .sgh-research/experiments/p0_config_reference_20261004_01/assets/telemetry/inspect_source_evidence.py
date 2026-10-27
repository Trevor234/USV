#!/usr/bin/env python3
"""Write a narrow hash/semantic audit, without duplicating source payloads."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
META = WORK / "p0_model_consistency_2026-10-04/metadata_summary.json"
MIRROR = WORK / "p0_contract_impl_2026-10-03/source/usv_mpc_ws"
FILES = [
    "src/usv_mpc_cpp/src/mpc_node.cpp",
    "src/usv_mpc_cpp/include/usv_mpc_cpp/mpc_node.hpp",
    "src/usv_mpc_cpp/include/usv_mpc_cpp/research_logger.hpp",
    "src/usv_mpc_cpp/include/usv_mpc_cpp/mpc_solver.hpp",
    "src/usv_mpc_cpp/src/acados_backend.cpp",
    "src/usv_mpc_cpp/src/casadi_backend.cpp",
    "src/usv_research_interfaces/CMakeLists.txt",
    "src/usv_research_interfaces/msg/StateSnapshot.msg",
    "src/usv_research_interfaces/msg/AppliedControl.msg",
    "src/usv_research_interfaces/msg/CycleTiming.msg",
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    raw = META.read_bytes()
    metadata = json.loads(raw)
    baseline = metadata["baselines"]["F3_20261004_quaternion_gate_01"]
    source = baseline["source_hashes"]
    records = []
    for name in FILES:
        hits = [x for x in source if x["path"].endswith("/" + name)]
        if len(hits) != 1:
            raise ValueError("F3 hash entry missing or repeated: " + name)
        item = hits[0]
        local_sha = sha((MIRROR / name).read_bytes())
        records.append({"relative_path": name, "f3_sha256": item["sha256"],
            "local_mirror_sha256": local_sha, "byte_identical_to_f3": local_sha == item["sha256"]})
    result = {
        "schema": "p0-reference-telemetry-source-review-v1",
        "metadata_sha256": sha(raw), "baseline": "F3_20261004_quaternion_gate_01",
        "files": records,
        "interpretation": [
            "The local node/header/logger differ in formatting and the remote quaternion gate.",
            "Whole-file mirror replacement is forbidden; only guarded local anchors are supplied.",
            "SolveInfo exposes the current solve X_pred/U_pred; getters expose shifted warm-start matrices.",
            "Actual current_state/reference/source containers are read within the same state_lock_ region.",
            "The solve runs outside state_lock_; source callbacks can replace containers during solve.",
            "Both source counters count every received callback, including clearing invalid/empty containers.",
            "Prediction copy uses accepted success after the existing deadline gate; rejected candidates are omitted.",
        ],
        "local_validation": "10 guarded-patch Python checks pass; ROS build/GTests are parent deployment work",
    }
    target = HERE / "source_evidence.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(target), "files": len(records),
        "byte_identical": sum(x["byte_identical_to_f3"] for x in records)}, indent=2))


if __name__ == "__main__":
    main()
