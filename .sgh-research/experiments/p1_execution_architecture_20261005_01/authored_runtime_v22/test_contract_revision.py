import unittest
from p1_contract_revision import diagnostic_revision_supported, POLICY

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
        self.assertFalse(diagnostic_revision_supported({"diagnostic_contract_revision":4,"worker_failure_policy":POLICY}))
    def test_revision_type_is_integral(self):
        for value in (True,2.0,3.0,"3",None):
            with self.subTest(value=value):
                self.assertFalse(diagnostic_revision_supported({"diagnostic_contract_revision":value,"worker_failure_policy":POLICY}))
    def test_new_policy_cannot_be_hidden_in_old_revision(self):
        self.assertFalse(diagnostic_revision_supported({"diagnostic_contract_revision":2,"worker_failure_policy":POLICY}))

if __name__=="__main__": unittest.main()
