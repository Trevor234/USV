"""Replay create-only real native Witness outputs through both independent v2 profiles."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import check_p1_witness_v2 as checker
from test_p1_witness_v2_c37 import expected_header

EXPECTATIONS = {
    "accepted": (True, True), "all_rejected": (True, False), "accepted_then_rejected": (True, True),
    "append_rejected": (False, False), "overflow": (False, False), "duplicate_submit": (False, False),
    "mismatched_ready": (False, False), "missing_ready": (True, False), "missing_close": (False, False),
    "failed_tick": (True, False), "source_failure": (True, False), "duplicate_ready": (False, False),
    "startup_ready": (False, False), "wrong_ready_observation": (False, False), "header_invalid": (False, False),
    "after_close": (False, False), "reversed_ticks": (False, False), "different_first_accepted": (False, False),
}


def write(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, allow_nan=False);f.write("\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--producer", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    a = p.parse_args()
    a.output_dir.mkdir()
    write(a.output_dir / "expected_fixture_header.json", expected_header())
    records = []
    for mode, expected in EXPECTATIONS.items():
        directory = a.output_dir / mode;directory.mkdir()
        witness_path = directory / "native_witness_v2.json"
        r = subprocess.run([str(a.producer.resolve()), mode, str(witness_path)], capture_output=True, timeout=5)
        (directory / "producer.stdout").write_bytes(r.stdout)
        (directory / "producer.stderr").write_bytes(r.stderr)
        witness, digest = checker.load_json(witness_path)
        outcomes = []
        for profile, wanted in zip(checker.EVALUATION_PROFILES, expected):
            report = checker.analyze(witness, expected_header(), profile=profile)
            report["evidence_sha256"] = {str(witness_path): digest}
            report["fixture_scope"] = "finite_native_Witness_producer_API; no solver/DDS/plant assertion"
            write(directory / (profile + ".json"), report)
            outcomes.append(report["passed"])
        records.append(dict(case=mode, producer_exit_code=r.returncode, observed=outcomes,
                            expected=list(expected), passed=r.returncode == 0 and outcomes == list(expected),
                            witness_sha256=digest))
    disabled = a.output_dir / "disabled";disabled.mkdir()
    disabled_path = disabled / "native_witness_v2.json"
    r = subprocess.run([str(a.producer.resolve()), "disabled", str(disabled_path)], capture_output=True, timeout=5)
    (disabled / "producer.stdout").write_bytes(r.stdout);(disabled / "producer.stderr").write_bytes(r.stderr)
    records.append(dict(case="disabled", producer_exit_code=r.returncode,
                        output_created=disabled_path.exists(), passed=r.returncode == 0 and not disabled_path.exists()))
    summary = dict(schema="c37-witness-v2-native-replay-v1", passed=all(r["passed"] for r in records),
                   native_fixture_cases=len(records), evaluations=2 * len(EXPECTATIONS), records=records,
                   producer_sha256=hashlib.sha256(a.producer.read_bytes()).hexdigest(),
                   phase_qualified=False, execute_qualified=False, research_conclusion=False)
    write(a.output_dir / "summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("passed", "native_fixture_cases", "evaluations")}))
    return 0 if summary["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
