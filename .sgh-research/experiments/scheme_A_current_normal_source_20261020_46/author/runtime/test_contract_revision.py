import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from p1_contract_revision import (diagnostic_revision_supported, POLICY, CAPABILITY_POLICY,
                                  RESOURCE_POLICY, RESOURCE_BUDGET_SCOPE, RESOURCE_FIELDS)

class RevisionTests(unittest.TestCase):
    def test_preserved_revision_two(self):
        self.assertTrue(diagnostic_revision_supported({"diagnostic_contract_revision":2}))
    def test_revision_three_requires_declared_policy(self):
        self.assertTrue(diagnostic_revision_supported({"diagnostic_contract_revision":3,"worker_failure_policy":POLICY}))
    def test_missing_policy_is_rejected(self):
        self.assertFalse(diagnostic_revision_supported({"diagnostic_contract_revision":3}))
    def test_changed_policy_is_rejected(self):
        self.assertFalse(diagnostic_revision_supported({"diagnostic_contract_revision":3,"worker_failure_policy":"retry_same_capsule"}))
    def test_unknown_future_revision_is_rejected(self):
        self.assertFalse(diagnostic_revision_supported({"diagnostic_contract_revision":6,"worker_failure_policy":POLICY}))
    def test_revision_type_is_integral(self):
        for value in (True,2.0,3.0,"3",None):
            with self.subTest(value=value):
                self.assertFalse(diagnostic_revision_supported({"diagnostic_contract_revision":value,"worker_failure_policy":POLICY}))
    def test_new_policy_cannot_be_hidden_in_old_revision(self):
        self.assertFalse(diagnostic_revision_supported({"diagnostic_contract_revision":2,"worker_failure_policy":POLICY}))
    def new(self):
        return {"diagnostic_contract_revision":4,"worker_failure_policy":POLICY,"worker_capability_lease_policy":CAPABILITY_POLICY,
                "worker_capability_receipt_timeout_ns":600_000_000,"worker_capability_source_freshness_available":False,"parameters_are_diagnostic_only":True}
    def test_revision_four_complete(self):self.assertTrue(diagnostic_revision_supported(self.new()))
    def test_revision_four_missing_fields(self):
        for k in ('worker_capability_lease_policy','worker_capability_receipt_timeout_ns','worker_capability_source_freshness_available','parameters_are_diagnostic_only'):
            c=self.new();del c[k];self.assertFalse(diagnostic_revision_supported(c))
    def test_receipt_timeout_integral_and_finite(self):
        for age in (True,600_000_000.,0,-1,199_999_999,5_000_000_001,'600000000'):
            c=self.new();c['worker_capability_receipt_timeout_ns']=age;self.assertFalse(diagnostic_revision_supported(c))
    def test_receipt_lease_cannot_claim_source_freshness(self):
        c=self.new();c['worker_capability_source_freshness_available']=True;self.assertFalse(diagnostic_revision_supported(c))
    def test_lease_diagnostic_only(self):
        c=self.new();c['parameters_are_diagnostic_only']=False;self.assertFalse(diagnostic_revision_supported(c))
    def test_lease_policy_identity(self):
        c=self.new();c['worker_capability_lease_policy']='resume_same_run';self.assertFalse(diagnostic_revision_supported(c))
    def test_lease_cannot_hide_in_revision_three(self):
        c=self.new();c['diagnostic_contract_revision']=3;self.assertFalse(diagnostic_revision_supported(c))

    def resources(self):
        c=self.new()
        c.update(diagnostic_contract_revision=5,resource_policy=RESOURCE_POLICY,
                 resource_budget_scope=RESOURCE_BUDGET_SCOPE,max_profile_dims=4,
                 max_profile_label_bytes=64,max_path_frame_bytes=128,
                 job_cdr_max_bytes=6460,candidate_cdr_max_bytes=8204,
                 max_path_points=2048,max_profile_rows=2048,log_capacity=512,
                 history_capacity=256,dds_depth=1,max_job_bytes=8192,
                 max_candidate_bytes=16384)
        return c

    def test_revision_five_complete(self):
        self.assertTrue(diagnostic_revision_supported(self.resources()))

    def test_revision_five_requires_all_resource_fields(self):
        for key in (*RESOURCE_FIELDS,"max_path_points","max_profile_rows","log_capacity",
                    "history_capacity","dds_depth","max_job_bytes","max_candidate_bytes"):
            with self.subTest(key=key):
                c=self.resources();del c[key]
                self.assertFalse(diagnostic_revision_supported(c))

    def test_resource_policy_and_budget_scope_are_exact(self):
        for key in ("resource_policy","resource_budget_scope"):
            for value in (None,True,"","raw_dds_memory_safe","typed_domain_bounds_before_copy_v2"):
                with self.subTest(key=key,value=value):
                    c=self.resources();c[key]=value
                    self.assertFalse(diagnostic_revision_supported(c))

    def test_resource_fields_cannot_hide_in_preserved_revisions(self):
        old={2:{"diagnostic_contract_revision":2},
             3:{"diagnostic_contract_revision":3,"worker_failure_policy":POLICY},
             4:self.new()}
        for revision, baseline in old.items():
            self.assertTrue(diagnostic_revision_supported(baseline))
            for key in RESOURCE_FIELDS:
                with self.subTest(revision=revision,key=key):
                    c=dict(baseline);c[key]=self.resources()[key]
                    self.assertFalse(diagnostic_revision_supported(c))

    def test_fixed_resource_shape_must_match_declared_domain(self):
        for key in ("max_profile_dims","max_profile_label_bytes","max_path_frame_bytes",
                    "job_cdr_max_bytes","candidate_cdr_max_bytes","dds_depth"):
            correct=self.resources()[key]
            for value in (True,float(correct),str(correct),0,-1,correct-1,correct+1):
                with self.subTest(key=key,value=value):
                    c=self.resources();c[key]=value
                    self.assertFalse(diagnostic_revision_supported(c))

    def test_bounded_resource_limits_reject_nonintegral_or_over_domain(self):
        for key in ("max_path_points","max_profile_rows","log_capacity","history_capacity"):
            upper=self.resources()[key]
            for value in (True,float(upper),str(upper),0,-1,upper+1,float("nan"),float("inf")):
                with self.subTest(key=key,value=value):
                    c=self.resources();c[key]=value
                    self.assertFalse(diagnostic_revision_supported(c))

    def test_smaller_positive_resource_capacities_remain_supported(self):
        for key in ("max_path_points","max_profile_rows","log_capacity","history_capacity"):
            for value in (1,self.resources()[key]-1):
                with self.subTest(key=key,value=value):
                    c=self.resources();c[key]=value
                    self.assertTrue(diagnostic_revision_supported(c))

    def test_byte_budgets_cover_full_legal_type_and_stay_within_implementation_cap(self):
        for key,lower,upper in (("max_job_bytes",6460,8192),("max_candidate_bytes",8204,16384)):
            for value in (True,float(lower),str(lower),0,-1,lower-1,upper+1):
                with self.subTest(key=key,value=value):
                    c=self.resources();c[key]=value
                    self.assertFalse(diagnostic_revision_supported(c))
            for value in (lower,upper):
                with self.subTest(key=key,value=value):
                    c=self.resources();c[key]=value
                    self.assertTrue(diagnostic_revision_supported(c))

    def test_revision_five_retains_failure_and_lease_policy(self):
        for key,value in (("worker_failure_policy","retry_same_capsule"),
                          ("worker_capability_lease_policy","resume_same_run"),
                          ("worker_capability_receipt_timeout_ns",True),
                          ("worker_capability_source_freshness_available",True),
                          ("parameters_are_diagnostic_only",False)):
            with self.subTest(key=key):
                c=self.resources();c[key]=value
                self.assertFalse(diagnostic_revision_supported(c))

    def test_revision_five_without_resource_declaration_is_rejected(self):
        c=self.new();c['diagnostic_contract_revision']=5
        self.assertFalse(diagnostic_revision_supported(c))

    def runner_contract(self):
        c=self.resources()
        c.update(schema="p1-execution-contract-v2",execute_qualified=False,
                 clock="CLOCK_MONOTONIC",N=20,dt=.2,
                 worker_grace_ns=500_000_000,term_grace_ns=1_000_000_000,
                 kill_postcheck_ns=1_000_000_000,shutdown_grace_ns=2_500_000_000,
                 active_watchdog_ns=1_000_000_000)
        return c

    def test_runner_accepts_frozen_revision_five(self):
        from run_no_output_calibration import load_contract
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"contract.json"
            data=json.dumps(self.runner_contract()).encode();path.write_bytes(data)
            digest=hashlib.sha256(data).hexdigest()
            parsed,actual=load_contract(path,digest)
            self.assertEqual(parsed,self.runner_contract())
            self.assertEqual(actual,digest)
            with self.assertRaisesRegex(RuntimeError,"contract hash changed"):
                load_contract(path,"0"*64)

    def test_runner_rejects_unsupported_resources_before_creating_run(self):
        from run_no_output_calibration import run
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/"contract.json"
            c=self.runner_contract();c['max_job_bytes']=6459
            data=json.dumps(c).encode();path.write_bytes(data)
            args=SimpleNamespace(run_id="p1_resource_rejected",duration=10.,contract=path,
                                 contract_hash=hashlib.sha256(data).hexdigest(),experiment_root=root)
            with self.assertRaisesRegex(RuntimeError,"temporary diagnostic-only F5 contract required"):
                run(args)
            self.assertFalse((root/args.run_id).exists())

if __name__=="__main__": unittest.main()
