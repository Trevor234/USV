"""Evidence mutation tests: a plausible report must fail when critical proof is removed."""
from copy import deepcopy
import unittest
from p1_payload_digest import canonical_payload_digest
from check_worker_fault_matrix import assess
from run_worker_fault_matrix import EXPECTED_CONTRACT, EXPECTED_WORKER

def fixture():
    c={"payload_schema":"ros-fields-ieee754-v1","scenario":"queue","run_id":"T","boot_id":"B","contract_hash":EXPECTED_CONTRACT,
       "worker_sha256":EXPECTED_WORKER,"production_regulator_present":False,
       "asset_precheck":{"drift":[]}}
    cleanup={n:{"cleanup_complete":True,"remaining_members":[],"returncode":0} for n in ("worker","recorder")}
    s={"worker_pid":7,"worker_instance":"I","sent_jobs":13,"failure":None,
       "production_regulator_present":False,"physical_publisher_samples_all_zero":True,"graph_samples":20,
       "asset_postcheck":{"drift":[]},"cleanup_complete":True,"supervision_evidence_complete":True,"cleanup":cleanup}
    ids=[100,*range(201,213)];events=[];jobs=[]
    for i in ids:
        events.extend([{"type":"job_publish_attempt","label":str(i),"job_id":i,"payload_sha256":str(i)},
                       {"type":"job_publish_acked","label":str(i),"job_id":i}])
        jobs.append({"payload_sha256":str(i),"message":{"job_id":i}})
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
    return [c,s,events,worker,ledger,jobs,[{"message":m,"job_payload_sha256":"100"}],[cap]]

class EvidenceTests(unittest.TestCase):
    def test_canonical_order_does_not_change_identity(self):
        self.assertEqual(canonical_payload_digest({"x":1.0,"a":2}),canonical_payload_digest({"a":2,"x":1.0}))
    def test_float_bits_preserve_signed_zero(self):
        self.assertNotEqual(canonical_payload_digest([0.0]),canonical_payload_digest([-0.0]))
    def test_nonfinite_stimulus_is_stable(self):
        self.assertEqual(canonical_payload_digest([float("nan")]),canonical_payload_digest([float("nan")]))
        self.assertNotEqual(canonical_payload_digest([float("nan")]),canonical_payload_digest([float("inf")]))
    def test_one_last_history_value_changes_content(self):
        self.assertNotEqual(canonical_payload_digest([0.0]*256),canonical_payload_digest([0.0]*255+[1.0]))
    def test_complete_queue_fixture(self):
        r=assess(*fixture());self.assertTrue(r["fixture_mechanism_complete"],r["issues"])
        self.assertFalse(r["normal_contract_complete"]);self.assertFalse(r["production_regulator_validated"])
    def check_bad(self,mutator,expected):
        data=deepcopy(fixture());mutator(data);r=assess(*data)
        self.assertFalse(r["fixture_mechanism_complete"]);self.assertIn(expected,r["issues"])
    def test_actual_message_loss(self):
        self.check_bad(lambda d:d[5].pop(),"fixture publication / actual job content differs")
    def test_semantic_payload_tamper(self):
        self.check_bad(lambda d:d[5][0].update(payload_sha256="wrong"),"fixture publication / actual job content differs")
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

def numerical_fixture():
    d=fixture();d[0]["scenario"]="numerical";d[0]["worker_failure_policy"]="terminal_on_failed_or_invalid_native_result";d[1]["sent_jobs"]=3;d[1]["cleanup"]["worker"]["returncode"]=2;d[2]=[];d[3]=[d[3][0]];d[5]=[];d[6]=[]
    initial=fixture()[6][0]["message"]
    for jid in (100,1000,2000):
        label="finite_overflow_stress" if jid==1000 else "valid_initial" if jid==100 else "valid_recovery"
        d[2].extend([{"type":"job_publish_attempt","label":label,"job_id":jid,"payload_sha256":str(jid)},
                     {"type":"job_publish_acked","label":label,"job_id":jid}])
        j={"job_id":jid,"worker_instance":"I","deadline_steady_ns":10,"target_state":[0.0]*6}
        if jid==1000:j["target_state"][3]=1e200
        d[5].append({"payload_sha256":str(jid),"message":deepcopy(j)})
        if jid==2000:continue
        m=deepcopy(initial);m["job"]=j
        if jid==1000:m.update(success=False,prediction_available=False,reason="declared QP failure")
        w={"type":"candidate","job":{"job_id":jid,"worker_instance":"I","deadline_ns":10,"target_state":j["target_state"]},
           "receive_ns":1,"solve_start_ns":2,"solve_end_ns":3,"backend":"acados","backend_ms":.1,
           "solver_invoked":True,"success":m["success"],"prediction_available":m["prediction_available"],"reason":m["reason"],
           "first_control":m["first_control"],"X":m["x_prediction"],"U":m["u_prediction"]}
        d[3].append(w);d[6].append({"message":m,"job_payload_sha256":str(jid)})
    d[3].append({"type":"terminal_numerical_failure","job_id":1000,"result_published":True,"policy":"quarantine_this_run_no_restart"})
    d[3].append({"type":"job_rejected","job_id":2000,"reason":"worker_terminal"})
    d[3].append({"type":"worker_summary","normal_source_complete":False,"fatal":True,"terminal_numerical_failure":True,"generated_candidates":2,"published_candidates":2,"completed_jobs":2})
    d[7][0]["pending_count"]=0;d[7][0]["fatal"]=True
    return d

def death_fixture():
    d=fixture();d[0]["scenario"]="death";d[1]["sent_jobs"]=1
    d[1]["cleanup"]["worker"]["returncode"]=-9
    d[2]=d[2][:2];d[2][0]["label"]=d[2][1]["label"]="valid_initial"
    d[3]=d[3][:1];d[5]=d[5][:1];d[6]=[]
    d[4].append({"type":"signal","name":"worker","signal":9})
    d[7][0]["pending_count"]=0
    return d

class NumericalAndDeathEvidenceTests(unittest.TestCase):
    def test_numerical_failure_is_quarantined(self):
        r=assess(*numerical_fixture());self.assertTrue(r["fixture_mechanism_complete"],r["issues"])
    def test_native_success_cannot_be_claimed_numerical_failure(self):
        d=numerical_fixture();d[6][1]["message"].update(success=True,prediction_available=True)
        d[3][2].update(success=True,prediction_available=True)
        r=assess(*d);self.assertIn("real finite-overflow native failure not proven",r["issues"])
    def test_post_terminal_job_cannot_be_silently_dropped(self):
        d=numerical_fixture();d[3].pop(-2)
        r=assess(*d);self.assertFalse(r["fixture_mechanism_complete"])
        self.assertIn("after-terminal job was not rejected without native",r["issues"])
    def test_death_has_unknown_source_even_if_cleanup_passes(self):
        r=assess(*death_fixture());self.assertTrue(r["fixture_mechanism_complete"],r["issues"])
        self.assertFalse(r["worker_source_contract_complete"]);self.assertEqual(len(r["unknown"]),3)
    def test_death_without_owned_signal_is_not_proven(self):
        d=death_fixture();d[4].pop();r=assess(*d)
        self.assertIn("declared owned SIGKILL not proven",r["issues"])
    def test_endpoint_observation_and_test_failure_are_independent(self):
        d=fixture();d[1]["failure"]="other fixture timeout";r=assess(*d)
        self.assertIn("runner failed",r["issues"]);self.assertNotIn("zero physical endpoint observation missing",r["issues"])


if __name__=="__main__": unittest.main()
