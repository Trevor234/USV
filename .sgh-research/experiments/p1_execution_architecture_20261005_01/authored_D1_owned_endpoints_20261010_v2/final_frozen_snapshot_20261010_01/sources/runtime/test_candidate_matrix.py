from copy import deepcopy
import unittest
from candidate_fault_spec import CASES
from check_candidate_matrix import audit, mutation_matches, null_invalid
from p1_payload_digest import canonical_payload_digest

class CandidateEvidence(unittest.TestCase):
    def setUp(self):
        self.case=next(c for c in CASES if c[0]=="duplicate")
        self.base={"job":{"job_id":2,"target_tick":2,"deadline_steady_ns":150_000_000,"target_steady_ns":200_000_000},
                   "worker_instance":"native","solve_start_ns":5_000_000,"solve_end_ns":6_000_000,"first_control":[9.,9.],
                   "success":True,"prediction_available":True,"solver_invoked":True,"backend":"acados"}
        digest=canonical_payload_digest(self.base)
        self.native=[deepcopy(self.base)];self.actual=[deepcopy(self.base),deepcopy(self.base)]
        self.inject=[{"case_number":1,"label":"duplicate","descriptor":list(self.case),"base_job_id":2,"barrier_job_id":2,
                      "is_original_native_result":False,"base_payload_sha256":digest,"injected_payload_sha256":digest,
                      "publish_start_ns":40_000_000,"barrier_deadline_ns":150_000_000,"barrier_target_ns":200_000_000,"expected_reason":"duplicate"}]
        job={"job_id":2,"target_tick":2,"deadline_ns":150_000_000,"target_ns":200_000_000}
        self.reg=[{"job":job,"worker_instance":"native","solve_start_ns":5_000_000,"solve_end_ns":6_000_000,
                   "first_control":[9.,9.],"accepted_registration":True,"reason":"","ready_commit_ns":15_000_000}]
        self.reg.append({**deepcopy(self.reg[0]),"accepted_registration":False,"reason":"duplicate","ready_commit_ns":45_000_000})
        self.dec=[{"accepted":True,"job_id":1,"activation_commit_ns":20_000_000,"ready_commit_ns":0,"requested_n":[9.,9.]},
                  {"accepted":True,"job_id":2,"activation_commit_ns":200_000_000,"ready_commit_ns":15_000_000,"requested_n":[9.,9.]}]
    def assess(self):return audit(self.native,self.inject,self.reg,self.dec,self.actual,[self.case])
    def test_complete_binding(self):self.assertTrue(self.assess()["mechanism_complete"])
    def test_missing_injection(self):self.inject=[];self.assertFalse(self.assess()["mechanism_complete"])
    def test_case_relabel(self):self.inject[0]["label"]="N";self.assertFalse(self.assess()["mechanism_complete"])
    def test_descriptor_rewritten(self):self.inject[0]["descriptor"][4]="late";self.assertFalse(self.assess()["mechanism_complete"])
    def test_not_native_origin(self):self.native=[];self.assertFalse(self.assess()["mechanism_complete"])
    def test_native_failure_not_success_baseline(self):self.native[0]["success"]=False;self.assertFalse(self.assess()["mechanism_complete"])
    def test_origin_digest_mismatch(self):self.inject[0]["base_payload_sha256"]="other";self.assertFalse(self.assess()["mechanism_complete"])
    def test_actual_dropped_packet(self):self.actual.pop();self.assertFalse(self.assess()["mechanism_complete"])
    def test_actual_extra_packet(self):self.actual.append(deepcopy(self.base));self.assertFalse(self.assess()["mechanism_complete"])
    def test_undeclared_field_change(self):self.actual[1]["backend"]="other";self.assertFalse(self.assess()["mechanism_complete"])
    def test_injection_claimed_native(self):self.inject[0]["is_original_native_result"]=True;self.assertFalse(self.assess()["mechanism_complete"])
    def test_original_not_ready(self):self.reg[0]["accepted_registration"]=False;self.assertFalse(self.assess()["mechanism_complete"])
    def test_original_ready_after_injection(self):self.reg[0]["ready_commit_ns"]=42_000_000;self.assertFalse(self.assess()["mechanism_complete"])
    def test_original_deadline_rewritten(self):self.inject[0]["barrier_deadline_ns"]+=1;self.assertFalse(self.assess()["mechanism_complete"])
    def test_registration_missing(self):self.reg.pop();self.assertFalse(self.assess()["mechanism_complete"])
    def test_registration_timing_unbound(self):self.reg[1]["ready_commit_ns"]=150_000_000;self.assertFalse(self.assess()["mechanism_complete"])
    def test_injected_accepted(self):self.reg[1]["accepted_registration"]=True;self.assertFalse(self.assess()["mechanism_complete"])
    def test_wrong_reason(self):self.reg[1]["reason"]="late";self.assertFalse(self.assess()["mechanism_complete"])
    def test_ready_displaced(self):self.dec[1]["ready_commit_ns"]=45_000_000;self.assertFalse(self.assess()["mechanism_complete"])
    def test_command_displaced(self):self.dec[1]["requested_n"][0]=10.;self.assertFalse(self.assess()["mechanism_complete"])
    def test_original_not_activated(self):self.dec[1]["accepted"]=False;self.assertFalse(self.assess()["mechanism_complete"])
    def test_original_double_activated(self):self.dec.append(deepcopy(self.dec[1]));self.assertFalse(self.assess()["mechanism_complete"])
    def test_prefix_missing(self):self.dec.pop(0);self.assertFalse(self.assess()["mechanism_complete"])
    def test_exact_duplicate_content_required(self):
        actual=deepcopy(self.base);actual["first_control"][0]+=.1
        self.assertFalse(mutation_matches(self.base,actual,self.case))
    def test_json_null_does_not_make_nonfinite_finite(self):
        self.assertEqual(null_invalid([float("nan"),float("inf"),9.]),[None,None,9.])
        self.assertNotEqual(canonical_payload_digest([float("nan")]),canonical_payload_digest([None]))
    def test_late_bound_to_original_deadline(self):
        self.case=next(c for c in CASES if c[0]=="late")
        self.inject[0].update(label="late",descriptor=list(self.case),expected_reason="late",publish_start_ns=160_000_000)
        self.reg[1].update(reason="late",ready_commit_ns=165_000_000)
        self.assertTrue(self.assess()["mechanism_complete"])
    def test_false_late_claim(self):
        self.case=next(c for c in CASES if c[0]=="late")
        self.inject[0].update(label="late",descriptor=list(self.case),expected_reason="late")
        self.reg[1]["reason"]="late"
        self.assertFalse(self.assess()["mechanism_complete"])

if __name__=="__main__":unittest.main()
