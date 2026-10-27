"""B0 contract rejection, compatibility and no-side-effect tests; no ROS."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import p1_full_contract as full


def diagnostic():
    return copy.deepcopy(full.SPEC["legacy_baseline"])


def pre_freeze():
    c = diagnostic()
    c.pop("diagnostic_contract_revision")
    c.update(schema=full.FORMAL_SCHEMA, qualification="execution_pre_freeze",
             fault_injection_enabled=False, execution_contract_revision=1,
             resource_contract_revision=1,
             supported_parameter_profile=full.SPEC["profile_id"], freeze_evidence_sha256="")
    return c


def frozen():
    c = pre_freeze()
    c.update(qualification="execution_frozen", execute_qualified=True,
             parameters_are_diagnostic_only=False, pending_final_calibration=[],
             freeze_evidence_sha256="a" * 64)
    return c


def formal_fixture():
    from test_check_p1_execution import fixture_v2
    f = list(fixture_v2(mixed=False))
    c = pre_freeze()
    f[3] = c
    jobs = [e["job"] for e in f[0] if e.get("type") in ("job", "candidate_registration")]
    jobs += [e["job"] for e in f[1] if e.get("type") == "candidate"]
    jobs += [f[2]["/p1/solve_job"][0]["message"],
             f[2]["/p1/solve_candidate"][0]["message"]["job"]]
    for job in jobs:
        job["nominal_hash"] = c["nominal_hash"]
    f[2]["/p1/worker_capability"][0]["message"]["nominal_hash"] = c["nominal_hash"]
    for e in f[0]:
        if e.get("type") == "odom_admission":
            e["child_frame"] = c["expected_child_frame"]
    counts = f[4]["_actual_topic_counts"]
    for role, topic in c["input_topics"].items():
        counts[topic] = counts.pop("/" + role)
    return f


class FullContractTests(unittest.TestCase):
    def test_full_current_diagnostic_and_formal_profiles(self):
        self.assertEqual(len(diagnostic()), 74)
        self.assertEqual(len(pre_freeze()), 77)
        for c in (diagnostic(), pre_freeze(), frozen()):
            self.assertIs(full.validate_fields(c), c)

    def test_pure_mode_matrix(self):
        for factory, allowed in ((diagnostic, {"no_output", "shadow"}),
                                 (pre_freeze, {"no_output"}),
                                 (frozen, {"no_output", "execute"})):
            for mode in ("no_output", "shadow", "execute", "foreign", None):
                with self.subTest(profile=factory.__name__, mode=mode):
                    if mode in allowed:
                        c = factory()
                        self.assertIs(full.validate_mode(c, mode), c)
                    else:
                        with self.assertRaises(full.ContractError):
                            full.validate_mode(factory(), mode)

    def test_frozen_execute_release_remains_closed(self):
        full.validate_mode(frozen(), "execute")
        with self.assertRaisesRegex(full.ContractError, "B5/M4 release not enabled"):
            full.require_runtime_mode(frozen(), "execute")
        full.require_runtime_mode(frozen(), "no_output")

    def test_every_required_field_missing_is_rejected(self):
        for original in (diagnostic(), pre_freeze(), frozen()):
            for key in original:
                with self.subTest(schema=original["schema"], key=key):
                    c = copy.deepcopy(original); c.pop(key)
                    with self.assertRaises(full.ContractError): full.validate_fields(c)

    def test_unknown_and_mixed_revision_fields_rejected(self):
        for original, key in ((diagnostic(), "execution_contract_revision"),
                              (pre_freeze(), "diagnostic_contract_revision"),
                              (pre_freeze(), "decision_schema_version")):
            c = copy.deepcopy(original); c[key] = 1
            with self.assertRaisesRegex(full.ContractError, "field set mismatch"):
                full.validate_fields(c)

    def test_integer_keys_reject_bool_float_string_and_null(self):
        for key in full.SPEC["integer_keys"]:
            for value in (True, float(diagnostic()[key]), str(diagnostic()[key]), None):
                with self.subTest(key=key, value=value):
                    c = diagnostic(); c[key] = value
                    with self.assertRaises(full.ContractError): full.validate_fields(c)

    def test_formal_revisions_require_true_integer_one(self):
        for key in ("execution_contract_revision", "resource_contract_revision"):
            for value in (True, 1., "1", None, 0, 2):
                c = pre_freeze(); c[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(full.ContractError):
                    full.validate_fields(c)

    def test_int64_domain_is_checked_before_conversion(self):
        for value in (1 << 63, -(1 << 63)-1):
            c = pre_freeze(); c["T_ns"] = value
            with self.assertRaisesRegex(full.ContractError, "outside int64"): full.validate_fields(c)
            with self.assertRaisesRegex(full.ContractError, "outside int64"):
                full.parse_contract_bytes(json.dumps(c).encode())

    def test_nonfinite_nested_numbers_and_bool_real_values_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf"), True):
            for key in ("mass", "Iz", "Xu_dot"):
                c = pre_freeze(); c["hydro"][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(full.ContractError):
                    full.validate_fields(c)

    def test_arrays_exact_length_and_numeric_element_types(self):
        for key in ("Q", "R", "Rd", "activation_tolerance"):
            for mutate in (lambda a: a[:-1], lambda a: a + [0],
                           lambda a: [True] + a[1:], lambda a: [None] + a[1:]):
                c = pre_freeze(); c[key] = mutate(c[key])
                with self.subTest(key=key), self.assertRaises(full.ContractError): full.validate_fields(c)

    def test_equivalent_real_numeric_representation_allowed(self):
        c = pre_freeze(); c["Q"] = [float(v) for v in c["Q"]]
        c["hydro"]["Xu_dot"] = -2.; c["map_scale"] = 1.
        full.validate_fields(c)

    def test_fixed_model_mapping_topics_and_semantics_drift_rejected(self):
        for key, value in (("N", 21), ("dt", .2 + 1e-12), ("deadline_ns", 200000000),
                           ("map_scale", .5), ("publisher_max_n", 24), ("command_max_n", 30),
                           ("nominal_hash", "0"*64), ("propagation_semantics", "plant_ack"),
                           ("worker_failure_policy", "retry")):
            c = pre_freeze(); c[key] = value
            with self.subTest(key=key), self.assertRaises(full.ContractError): full.validate_fields(c)
        c = pre_freeze(); c["hydro"]["mass"] += .1
        with self.assertRaises(full.ContractError): full.validate_fields(c)
        c = pre_freeze(); c["output_topics"]["right"] = c["output_topics"]["left"]
        with self.assertRaises(full.ContractError): full.validate_fields(c)

    def test_hydro_and_topic_nested_field_sets_exact(self):
        for key in ("hydro", "input_topics", "output_topics"):
            c = pre_freeze(); c[key]["unknown"] = 0
            with self.assertRaisesRegex(full.ContractError, "object shape mismatch"):
                full.validate_fields(c)

    def test_resource_original_bounded_domain_preserved(self):
        for factory in (diagnostic, pre_freeze):
            c = factory()
            c.update(max_path_points=1, max_profile_rows=1, log_capacity=1,
                     history_capacity=1, max_job_bytes=6460, max_candidate_bytes=8204)
            full.validate_fields(c)
        for key, value in (("max_job_bytes", 6459), ("max_candidate_bytes", 8203),
                           ("history_capacity", 257), ("log_capacity", 513),
                           ("dds_depth", 2), ("max_profile_dims", 5)):
            c = pre_freeze(); c[key] = value
            with self.subTest(key=key), self.assertRaises(full.ContractError): full.validate_fields(c)

    def test_flag_types_and_qualification_combinations(self):
        for factory in (diagnostic, pre_freeze, frozen):
            for key in ("execute_qualified", "parameters_are_diagnostic_only", "fault_injection_enabled"):
                for value in (1, "true", not factory()[key]):
                    c = factory(); c[key] = value
                    with self.subTest(profile=factory.__name__, key=key, value=value), self.assertRaises(full.ContractError):
                        full.validate_fields(c)

    def test_pre_freeze_pending_and_empty_marker_are_exact(self):
        for key, value in (("pending_final_calibration", []),
                           ("pending_final_calibration", ["invented"]),
                           ("freeze_evidence_sha256", "a"*64),
                           ("qualification", "unrecognized")):
            c = pre_freeze(); c[key] = value
            with self.subTest(key=key), self.assertRaises(full.ContractError): full.validate_fields(c)

    def test_frozen_marker_and_pending_required(self):
        for value in ("", "A"*64, "g"*64, "a"*63, 1, True):
            c = frozen(); c["freeze_evidence_sha256"] = value
            with self.subTest(value=value), self.assertRaises(full.ContractError): full.validate_fields(c)
        c = frozen(); c["pending_final_calibration"] = ["rho_n_s"]
        with self.assertRaises(full.ContractError): full.validate_fields(c)

    def test_raw_duplicates_top_level_and_nested_rejected(self):
        for data in (b'{"schema":1,"schema":2}', b'{"hydro":{"mass":1,"mass":2}}'):
            with self.assertRaisesRegex(full.ContractError, "duplicate JSON key"):
                full.parse_contract_bytes(data)

    def test_raw_nonstandard_constants_and_numeric_overflow_rejected(self):
        for token in ("NaN", "Infinity", "-Infinity", "1e309"):
            with self.subTest(token=token), self.assertRaises(full.ContractError):
                full.parse_contract_bytes(('{"dt":' + token + '}').encode())

    def test_raw_invalid_json_utf8_and_size_rejected(self):
        for data in (b'{', b'\xff', b' '*(65536+1)):
            with self.assertRaises(full.ContractError): full.parse_contract_bytes(data)
        with self.assertRaises(full.ContractError): full.validate_fields([])

    def test_loading_hash_and_bound_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/"contract.json"; data = json.dumps(pre_freeze()).encode(); p.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            c, actual = full.load_contract(p, digest, mode="no_output", runtime=True)
            self.assertEqual((c, actual), (pre_freeze(), digest))
            with self.assertRaisesRegex(full.ContractError, "hash changed"): full.load_contract(p, "0"*64)
            with self.assertRaisesRegex(full.ContractError, "runtime mode required"): full.load_contract(p, digest, runtime=True)
            p.write_bytes(data + b' ' * 65536)
            with self.assertRaisesRegex(full.ContractError, "64 KiB"): full.load_contract(p)

    def test_new_runner_loading_is_formal_only_and_hash_bound(self):
        import run_formal_no_output_validation as runner
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/"contract.json"
            for factory in (pre_freeze, frozen):
                data = json.dumps(factory()).encode(); p.write_bytes(data)
                self.assertEqual(runner.load_contract(p, hashlib.sha256(data).hexdigest())[0], factory())
            data = json.dumps(diagnostic()).encode(); p.write_bytes(data)
            with self.assertRaisesRegex(full.ContractError, "formal v3 contract required"):
                runner.load_contract(p, hashlib.sha256(data).hexdigest())

    def test_new_runner_bad_contract_does_not_create_directory(self):
        import run_formal_no_output_validation as runner
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); p = root/"contract.json"; c = pre_freeze(); c["dt"] = .1
            data = json.dumps(c).encode(); p.write_bytes(data)
            args = SimpleNamespace(run_id="formal_rejected", duration=1., contract=p,
                                   contract_hash=hashlib.sha256(data).hexdigest(), experiment_root=root)
            with self.assertRaises(full.ContractError): runner.run(args)
            self.assertFalse((root/args.run_id).exists())

    def test_new_runner_hooks_rejected_before_creating_directory(self):
        import run_formal_no_output_validation as runner
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); p = root/"contract.json"; data = json.dumps(pre_freeze()).encode(); p.write_bytes(data)
            for hook in ("test_delay_ms", "test_native_block_ms", "test_prepare_block_ms", "test_tick_block_ms"):
                args = SimpleNamespace(run_id="formal_hook_rejected", duration=1., contract=p,
                    contract_hash=hashlib.sha256(data).hexdigest(), experiment_root=root,
                    test_delay_ms=0, test_native_block_ms=0, test_prepare_block_ms=0, test_tick_block_ms=0)
                setattr(args, hook, 1)
                with self.subTest(hook=hook), self.assertRaisesRegex(RuntimeError, "fault injection disabled"):
                    runner.run(args)
                self.assertFalse((root/args.run_id).exists())

    def test_new_runner_host_preflight_recognizes_both_fixture_names(self):
        import run_formal_no_output_validation as runner
        row = {"pid": 999999, "state": "S", "exe": "/usr/bin/python3", "start_ticks": 1}
        for name in ("run_formal_no_output_validation.py", "run_no_output_calibration.py"):
            cmdline = ("python3\0/path/" + name + "\0--fixture-child\0").encode()
            with self.subTest(name=name), patch.object(runner.sys, "platform", "linux"), \
                    patch.object(runner, "proc_table", return_value=[row]), \
                    patch.object(Path, "read_bytes", return_value=cmdline), \
                    self.assertRaisesRegex(RuntimeError, "prevents startup"):
                runner.host_preflight()

    def test_new_fixture_child_entry_uses_its_own_file(self):
        import run_formal_no_output_validation as runner
        source = Path(runner.__file__).read_text(encoding="utf-8")
        self.assertIn('str(Path(__file__).resolve()),', source)
        self.assertIn('"--fixture-child", "--contract"', source)
        self.assertNotIn('from run_no_output_calibration import', source)

    def test_legacy_sparse_recognition_and_runner_remain_unchanged(self):
        from p1_contract_revision import diagnostic_revision_supported
        from run_no_output_calibration import load_contract as old_load
        self.assertTrue(diagnostic_revision_supported({"diagnostic_contract_revision": 2}))
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/"contract.json"; data = json.dumps(pre_freeze()).encode(); p.write_bytes(data)
            with self.assertRaisesRegex(RuntimeError, "temporary diagnostic-only"):
                old_load(p, hashlib.sha256(data).hexdigest())

    def test_formal_checker_accepts_complete_v2_source_metadata(self):
        import check_p1_execution as checker
        result = checker.validate_decoded(*formal_fixture())
        self.assertTrue(result["passed"], result["issues"])
        self.assertTrue(result["activation_source_contract_complete"])
        self.assertFalse(result["normal_contract_complete"])

    def test_formal_checker_rejects_profile_drift_and_physical_release(self):
        import check_p1_execution as checker
        f = formal_fixture(); f[3]["map_scale"] = 2
        result = checker.validate_decoded(*f)
        self.assertFalse(result["passed"])
        self.assertIn("formal_contract_or_runtime_mode_invalid", [v["code"] for v in result["issues"]])
        f = formal_fixture(); f[3] = frozen()
        f[0][0]["mode"] = f[4]["mode"] = "execute"
        result = checker.validate_decoded(*f)
        self.assertFalse(result["passed"])
        self.assertTrue(any("B5/M4 release not enabled" in v.get("error", "") for v in result["issues"]))


if __name__ == "__main__":
    unittest.main()
