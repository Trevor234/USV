"""Evidence mutation tests: a plausible report must fail when critical proof is removed."""
from copy import deepcopy
import unittest
from check_worker_fault_matrix import assess
from run_worker_fault_matrix import EXPECTED_CONTRACT, EXPECTED_WORKER

def fixture():
    c={"scenario":"queue","run_id":"T","boot_id":"B","contract_hash":EXPECTED_CONTRACT,
       "worker_sha256":EXPECTED_WORKER,"production_regulator_present":False,
       "asset_precheck":{"drift":[]}}
    cleanup={n:{"cleanup_complete":True,"remaining_members":[],"returncode":0} for n in ("worker","recorder")}
    s={"worker_pid":7,"worker_instance":"I","sent_jobs":13,"failure":None,
       "production_regulator_present":False,"physical_publisher_samples_all_zero":True,"graph_samples":20,
       "asset_postcheck":{"drift":[]},"cleanup_complete":True,"supervision_evidence_complete":True,"cleanup":cleanup}
    ids=[100,*range(201,213)];events=[];jobs=[]
    for i in ids:
        events.extend([{"type":"job_publish_attempt","label":str(i),"job_id":i,"cdr_sha256":str(i)},
                       {"type":"job_publish_acked","label":str(i),"job_id":i}])
        jobs.append({"cdr_sha256":str(i),"message":{"job_id":i}})
    job={"job_id":100,"worker_instance":"I","deadline_steady_ns":10}
    m={"job":job,"worker_instance":"I","backend":"acados","solver_invoked":True,
       "worker_receive_ns":1,"solve_start_ns":2,"solve_end_ns":3,"backend_ms":.1,"reason":"",
       "success":True,"prediction_available":True,"first_control":[0,0],"x_prediction":[0]*126,"u_prediction":[0]*40}
    w={"type":"candidate","job":{"job_id":100,"worker_instance":"I","deadline_ns":10},
       "worker_instance":"I","backend":"acados","solver_invoked":True,"receive_ns":1,"solve_start_ns":2,
       "solve_end_ns":3,"backend_ms":.1,"reason":"","success":True,"prediction_available":True,
       "first_control":[0,0],"X":[0]*126,"U":[0]*40}
    worker=[{"type":"worker_recording_ready","worker_instance":"I","candidate_matched":2},
            *[{"type":"pending_replaced","job_id":i,"replacement_job_id":i+1} for i in range(201,212)],
            w,{"type":"pending_expired_before_native","job_id":212,"solver_invoked":False},
            {"type":"worker_summary","normal_source_complete":True,"fatal":False,
             "generated_candidates":1,"published_candidates":1,"completed_jobs":1}]
    ledger=[{"type":"spawn","name":"worker","executable_verified":True,
             "expected_sha256":EXPECTED_WORKER,"identity":{"pid":7}}]
    cap={"pid":7,"worker_instance":"I","run_id":"T","boot_id":"B","contract_hash":EXPECTED_CONTRACT,
         "pending_count":1,"active_job":100,"backend":"acados","matrix_layout":"column_major",
         "horizon_steps":20,"prediction_dt":.2}
    return [c,s,events,worker,ledger,jobs,[{"message":m,"job_cdr_sha256":"100"}],[cap]]

class EvidenceTests(unittest.TestCase):
    def test_complete_queue_fixture(self):
        r=assess(*fixture());self.assertTrue(r["fixture_mechanism_complete"],r["issues"])
        self.assertFalse(r["normal_contract_complete"]);self.assertFalse(r["production_regulator_validated"])
    def check_bad(self,mutator,expected):
        data=deepcopy(fixture());mutator(data);r=assess(*data)
        self.assertFalse(r["fixture_mechanism_complete"]);self.assertIn(expected,r["issues"])
    def test_actual_message_loss(self):
        self.check_bad(lambda d:d[5].pop(),"fixture publication / actual job CDR differs")
    def test_cdr_payload_tamper(self):
        self.check_bad(lambda d:d[5][0].update(cdr_sha256="wrong"),"fixture publication / actual job CDR differs")
    def test_missing_ack(self):
        self.check_bad(lambda d:d[2].pop(),"publication acknowledgements incomplete")
    def test_foreign_pid(self):
        self.check_bad(lambda d:d[7][0].update(pid=8),"foreign actual capability")
    def test_pending_capacity(self):
        self.check_bad(lambda d:d[7][0].update(pending_count=2),"actual capability capacity / layout")
    def test_residual_process(self):
        self.check_bad(lambda d:d[1]["cleanup"]["worker"].update(remaining_members=[7]),"owned residual: worker")
    def test_missing_asset_post_guard(self):
        self.check_bad(lambda d:d[1].pop("asset_postcheck"),"asset identity drift / missing guard")
    def test_replacement_loss(self):
        self.check_bad(lambda d:d[3].pop(3),"pending replacement chain incomplete or reordered")
    def test_expired_task_invoked(self):
        self.check_bad(lambda d:d[3][-2].update(solver_invoked=True),"latest pending was not rejected before native")
    def test_source_job_content_changed(self):
        self.check_bad(lambda d:d[3][-3]["job"].update(deadline_ns=11),"candidate full frozen job differs from source")
    def test_full_prediction_tamper(self):
        self.check_bad(lambda d:d[6][0]["message"]["x_prediction"].__setitem__(125,1),"candidate full result differs from source")
    def test_native_after_deadline(self):
        self.check_bad(lambda d:d[6][0]["message"].update(solve_start_ns=11,solve_end_ns=12),"native started after original deadline")
    def test_terminal_counter_mismatch(self):
        self.check_bad(lambda d:d[3][-1].update(published_candidates=0),"worker normal terminal counts / completeness disagree")
    def test_bad_pid_identity(self):
        self.check_bad(lambda d:d[4][0]["identity"].update(pid=8),"worker PID binding mismatch")
    def test_unverified_executable(self):
        self.check_bad(lambda d:d[4][0].update(executable_verified=False),"owned executable not verified")
    def test_role_ambiguity(self):
        self.check_bad(lambda d:d[1].update(production_regulator_present=True),"fixture role ambiguous")

if __name__=="__main__": unittest.main()
