import unittest
from p1_contract_revision import diagnostic_revision_supported, POLICY, CAPABILITY_POLICY

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
        self.assertFalse(diagnostic_revision_supported({"diagnostic_contract_revision":5,"worker_failure_policy":POLICY}))
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

if __name__=="__main__": unittest.main()
