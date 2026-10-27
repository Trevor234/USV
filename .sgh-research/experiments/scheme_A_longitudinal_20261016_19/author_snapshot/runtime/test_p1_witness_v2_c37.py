"""Decoder-only strict input tests; native producer replay is a separate tool."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import check_p1_witness_v2 as checker


def expected_header():
    return {"run_id": "C37_native_finite_witness", "boot_id": "5a417cdc-1c7f-4c5c-8186-6d7e9a85ddcb",
            "contract_sha256": "1" * 64, "source_sha256": "2" * 64, "binary_sha256": "3" * 64,
            "worker_binary_sha256": "4" * 64, "worker_instance": "5" * 64}


def identity(job, tick, target):
    return dict(job_id=job, tick=tick, target_tick=target, task_generation=1, model_generation=1,
                config_generation=1, schedule_generation=1, clock_epoch=1)


def sample(accepted=True):
    flags = dict(failed_start=False, stopping_start=False, failed_end=False, stopping_end=False)
    w = dict(schema=checker.SCHEMA, profile=checker.PRODUCTION_PROFILE,
             normal_contract_scope=checker.NORMAL_CONTRACT_SCOPE, enabled=True, closed=True,
             observation_complete=True, business_ready_observed=accepted, normal_contract_qualified=accepted,
             overflow=False, incomplete=False, clock_name="CLOCK_MONOTONIC", header=expected_header(),
             capacities=dict(checker.CAPACITIES), counters={},
             tick=[dict(identity(0, 0, 0), sequence=1, planned_ns=100, start_ns=101, end_ns=140,
                        skipped_ticks=0, candidate_present=False, **flags),
                   dict(identity(1, 1, 1), sequence=2, planned_ns=200, start_ns=201, end_ns=240,
                        skipped_ticks=0, candidate_present=True, **flags)],
             submit=[dict(identity(1, 0, 1), sequence=1, commit_ns=150, failed=False, stopping=False)],
             activation=[dict(identity(1, 1, 1), sequence=1, commit_ns=220, ready_commit_ns=180,
                              accepted=accepted, reason_code=0 if accepted else 3, failed=False, stopping=False)],
             phase=[], first_failure=dict(code=0, stream=0, ns=0, ticket=0))
    def phase(seq, event, ns, job=0, tick=0):
        return dict(sequence=seq, event_code=event, observation_code=2 if event == 9 else 6,
                    ns=ns, tick=tick, job_id=job, admission_slots=0, candidate_present=False,
                    pending_present=False, failed=False, stopping=False, pause_active=False)
    if accepted:
        w["phase"].append(phase(1, 9, 220, 1, 1))
    w["phase"].append(phase(len(w["phase"]) + 1, 7, 250))
    recount(w)
    return w


def recount(w):
    for stream in checker.STREAMS:
        n = len(w[stream])
        w["counters"][stream] = dict(attempts=n, reserved=n, published=n, overflow=0, rejected=0)
    w["counters"]["ticks_without_candidate"] = sum(not r["candidate_present"] for r in w["tick"])
    w["counters"]["accepted_activations"] = sum(r["accepted"] for r in w["activation"])


class WitnessV2DecoderC37(unittest.TestCase):
    def check(self, w=None, profile="closed_shadow_observation"):
        return checker.analyze(sample() if w is None else w, expected_header(), profile=profile)

    def test_profiles_distinguish_closed_rejected_and_normal(self):
        self.assertTrue(self.check(profile="normal_business")["passed"])
        w = sample(False)
        self.assertTrue(self.check(w)["passed"])
        r = self.check(w, "normal_business")
        self.assertFalse(r["passed"])
        self.assertTrue(r["observation_complete"])
        self.assertFalse(r["business_ready_observed"])
        self.assertFalse(r["normal_business"])

    def test_no_profile_default_and_invalid_profile(self):
        with self.assertRaises(TypeError):
            checker.analyze(sample(), expected_header())
        for p in (None, True, [], "startup_ready"):
            self.assertFalse(self.check(profile=p)["passed"])

    def test_old_v1_and_ambiguous_audit_field_rejected(self):
        w = sample();w["schema"] = "p1-fixed-witness-v1";w["audit_complete"] = True
        r = self.check(w)
        self.assertFalse(r["passed"])
        self.assertIn("root_fields", {i["code"] for i in r["issues"]})

    def test_raw_normal_claim_cannot_substitute_real_accepted(self):
        w = sample(False);w["normal_contract_qualified"] = w["business_ready_observed"] = True
        self.assertFalse(self.check(w)["passed"])

    def test_each_header_pin_checked_independently(self):
        for field in checker.HEADER_FIELDS:
            h = expected_header()
            h[field] = "6" * 64 if field in checker.HASH_FIELDS else (
                "another_run" if field == "run_id" else "6a417cdc-1c7f-4c5c-8186-6d7e9a85ddcb")
            self.assertFalse(checker.analyze(sample(), h, profile="closed_shadow_observation")["passed"])

    def test_root_flags_are_booleans_not_numbers(self):
        for field in ("enabled", "closed", "observation_complete", "business_ready_observed",
                      "normal_contract_qualified", "overflow", "incomplete"):
            for v in (0, 1, None, "true"):
                w = sample();w[field] = v
                self.assertFalse(self.check(w)["passed"], (field, v))

    def test_identity_malformed_types_never_raise(self):
        for stream in ("tick", "submit", "activation"):
            for field in checker.IDENTITY_FIELDS:
                for v in (True, None, -1, 1.0, "1", checker.U64_MAX + 1):
                    w = sample();w[stream][0][field] = v
                    self.assertFalse(self.check(w)["passed"], (stream, field, v))

    def test_fixed_capacities_and_counter_accounting(self):
        for stream in checker.STREAMS:
            w = sample();w["capacities"][stream] = True
            self.assertFalse(self.check(w)["passed"])
            w = sample();w["counters"][stream]["attempts"] += 1
            self.assertFalse(self.check(w)["passed"])

    def test_duplicate_population_and_accepted_identity_mismatch(self):
        w = sample();w["submit"].append(dict(w["submit"][0], sequence=2));recount(w)
        w["normal_contract_qualified"] = w["observation_complete"] = False
        self.assertFalse(self.check(w)["passed"])
        w = sample();w["activation"][0]["model_generation"] = 2;w["normal_contract_qualified"] = w["observation_complete"] = False
        self.assertFalse(self.check(w)["passed"])

    def test_ready_binding_must_be_first_and_final_activation(self):
        for field, value in (("job_id", 2), ("tick", 2), ("ns", 221), ("observation_code", 1)):
            w = sample();w["phase"][0][field] = value
            w["business_ready_observed"] = w["normal_contract_qualified"] = False
            self.assertFalse(self.check(w)["passed"])

    def test_missing_close_and_close_before_producers(self):
        w = sample();w["phase"].pop();recount(w);w["normal_contract_qualified"] = w["observation_complete"] = False
        self.assertFalse(self.check(w)["passed"])
        w = sample();w["phase"][-1]["ns"] = 210;w["normal_contract_qualified"] = w["observation_complete"] = False
        self.assertFalse(self.check(w)["passed"])

    def test_failed_record_population_remains_observation_only(self):
        w = sample();w["tick"][1]["failed_end"] = True;w["normal_contract_qualified"] = False
        self.assertTrue(self.check(w)["passed"])
        self.assertFalse(self.check(w, "normal_business")["passed"])

    def test_complete_source_failure_never_qualifies_normal(self):
        w = sample();w["phase"].insert(1, dict(w["phase"][-1], sequence=2, event_code=4, observation_code=0, ns=245))
        w["phase"][-1]["sequence"] = 3;recount(w);w["normal_contract_qualified"] = False
        self.assertTrue(self.check(w)["passed"])
        self.assertFalse(self.check(w, "normal_business")["passed"])

    def test_missing_ready_does_not_invent_business_qualification(self):
        w = sample();w["phase"].pop(0);w["phase"][0]["sequence"] = 1;recount(w)
        w["business_ready_observed"] = w["normal_contract_qualified"] = False
        self.assertTrue(self.check(w)["passed"])
        self.assertFalse(self.check(w, "normal_business")["passed"])

    def test_parser_rejects_duplicate_nonfinite_depth_and_bytes(self):
        values = [b'{"schema":1,"schema":2}', b'{"number":NaN}', b'{"number":1e999}',
                  b'[' * 10 + b'0' + b']' * 10, b'x' * (checker.MAX_BYTES + 1)]
        with tempfile.TemporaryDirectory() as d:
            for i, raw in enumerate(values):
                p = Path(d) / str(i);p.write_bytes(raw)
                with self.assertRaises(ValueError):
                    checker.load_json(p)

    def test_all_results_deny_stage_and_research_qualification(self):
        r = self.check(profile="normal_business")
        for field in ("phase_qualified", "execute_qualified", "research_conclusion",
                      "source_join_verified", "normal_contract_complete"):
            self.assertIs(r[field], False)


if __name__ == "__main__":
    unittest.main()
