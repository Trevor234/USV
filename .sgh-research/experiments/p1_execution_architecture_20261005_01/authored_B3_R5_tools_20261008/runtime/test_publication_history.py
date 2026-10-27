"""Risk fixtures for consecutive history and real shadow rejection evidence."""
import copy
import unittest
import check_p1_execution as c
from test_check_p1_execution import shadow_fixture, decision_update

def history():
    expected={"n":[10.,10.],"sequence":[3,3],"publish_ns":[1000000000,1000000000],"known":[True,True]}
    actual={"n":[10.,10.],"sequence":[5,5],"publish_ns":[1400000000,1400000000],"known":[True,True]}
    entries=[{"channel":channel,"sequence":seq,"publish_ns":1000000000+(seq-3)*200000000,"n":10.,"known":True}
             for seq in range(3,6) for channel in (0,1)]
    return expected,actual,entries

class HistoryRisks(unittest.TestCase):
    def test_same_value_requires_complete_consecutive_history(self):
        self.assertEqual(c.publication_history_reason(*history()),"")
    def test_changed_then_returned_never_equals_static_history(self):
        a,b,e=history();e[2]["n"]=9
        self.assertEqual(c.publication_history_reason(a,b,e),"anchor_history_changed")
    def test_missing_channel_sequence_and_evicted_anchor_fail(self):
        for index in (0,2,3,5):
            a,b,e=history();del e[index]
            self.assertEqual(c.publication_history_reason(a,b,e),"anchor_history_incomplete")
    def test_out_of_order_time_and_sequence_fail(self):
        a,b,e=history();e[2],e[4]=e[4],e[2]
        self.assertEqual(c.publication_history_reason(a,b,e),"anchor_history_incomplete")
    def test_unknown_nan_and_large_history_cannot_authorize(self):
        a,b,e=history();e[2]["known"]=False
        self.assertEqual(c.publication_history_reason(a,b,e),"unknown_anchor")
        a,b,e=history();e[2]["n"]=float("nan")
        self.assertEqual(c.publication_history_reason(a,b,e),"anchor_history_invalid")
        self.assertEqual(c.publication_history_reason(a,b,e*50),"anchor_history_invalid")
    def test_shadow_accepted_candidate_requires_raw_applied_proof(self):
        f=shadow_fixture();f[2][c.APPLIED_TOPIC]=[]
        report=c.validate_decoded(*f)
        self.assertFalse(report["passed"])
        self.assertIn("shadow_anchor_raw_event_missing_or_duplicate",[e["code"] for e in report["issues"]])
    def test_shadow_raw_command_corruption_cannot_match_source(self):
        f=shadow_fixture();f[2][c.APPLIED_TOPIC][0]["message"]["final_n"][0]=.5
        report=c.validate_decoded(*f)
        self.assertIn("shadow_anchor_applied_payload_mismatch",[e["code"] for e in report["issues"]])
    def test_missing_history_proof_is_unknown(self):
        f=shadow_fixture();f[0][:]=[e for e in f[0] if e.get("type")!="anchor_validation"]
        f[0][-1].update(generated=len(f[0])-1,emitted=len(f[0])-1)
        self.assertIn("shadow_anchor_proof_missing_or_duplicate",[e["code"] for e in c.validate_decoded(*f)["issues"]])
    def test_real_changed_anchor_rejection_completes_shadow_chain(self):
        f=shadow_fixture();proof=next(e for e in f[0] if e.get("type")=="anchor_validation")
        decision_update(f,candidate_accepted=False,reason="anchor_mismatch",control_source="ramp_zero")
        proof.update(actual_n=[.5,0.],actual_sequence=[2,2],actual_publish_ns=[1100000000,1100000000],
                     history_reason="anchor_mismatch",decision_reason="anchor_mismatch",accepted=False)
        proof["entries"] += [{"channel":ch,"sequence":2,"publish_ns":1100000000,"n":.5 if ch==0 else 0.,"known":True} for ch in (0,1)]
        m=copy.deepcopy(f[2][c.APPLIED_TOPIC][0]["message"]);m.update(sequence=2,final_n=[.5,0.],left_publish_start_steady_ns=1100000000,right_publish_start_steady_ns=1100000000)
        f[2][c.APPLIED_TOPIC].append({"message":m})
        report=c.validate_decoded(*f)
        self.assertEqual(report["issues"],[])
        self.assertTrue(report["diagnostic_complete"])
        self.assertFalse(report["normal_contract_complete"])
    def test_false_rejection_of_unchanged_anchor_is_detected(self):
        f=shadow_fixture();proof=next(e for e in f[0] if e.get("type")=="anchor_validation")
        decision_update(f,candidate_accepted=False,reason="anchor_mismatch",control_source="ramp_zero")
        proof.update(accepted=False,decision_reason="anchor_mismatch")
        self.assertIn("shadow_anchor_rejection_without_basis",[e["code"] for e in c.validate_decoded(*f)["issues"]])

    def test_fault_shadow_still_requires_proof_for_checked_candidate(self):
        f=shadow_fixture();f[4]["scenario"]="controlled_shadow_fault"
        f[0][:]=[e for e in f[0] if e.get("type")!="anchor_validation"]
        f[0][-1].update(generated=len(f[0])-1,emitted=len(f[0])-1)
        self.assertIn("shadow_anchor_proof_missing_or_duplicate",[e["code"] for e in c.validate_decoded(*f)["issues"]])

if __name__=="__main__":unittest.main()
