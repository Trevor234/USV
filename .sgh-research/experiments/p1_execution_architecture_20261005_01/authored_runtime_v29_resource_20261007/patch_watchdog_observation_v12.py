from pathlib import Path
import sys,hashlib
root=Path(sys.argv[1])
def change(name,expected,mutate):
 p=root/name;s=p.read_text();assert hashlib.sha256(p.read_bytes()).hexdigest()==expected,name
 p.write_text(mutate(s),encoding="utf-8",newline="\n")
helper='''
def watchdog_observation(active_since, now, decision_reason, decision_ns, watchdog_ns, grace_ns, pending_since=None):
    """External expiry and regulator observation have distinct linearization points."""
    if active_since is None or now-active_since<=watchdog_ns:
        return "idle",None
    pending_since=now if pending_since is None else pending_since
    if now-pending_since>grace_ns:
        return "timeout",pending_since
    if decision_reason=="worker_unusable" and active_since+watchdog_ns<=decision_ns<=now:
        return "confirmed",pending_since
    return "pending",pending_since

'''
def nooutput(s):
 s=s.replace("def run(args",helper+"def run(args",1)
 s=s.replace('"active_job": 0, "owned_identity": None}', '"active_job": 0, "owned_identity": None, "watchdog_pending": None}')
 old='''            if active_since is not None and time.monotonic_ns() - active_since > c["active_watchdog_ns"]:
                observations["watchdog_seen"] = True
                stop_reason = "owned_worker_active_watchdog"
                if expected_fault == "none":
                    raise RuntimeError("unexpected worker watchdog in baseline calibration")
                break'''
 new='''            observed_now=time.monotonic_ns()
            if active_since is not None and observed_now-active_since>c["active_watchdog_ns"] and expected_fault=="none":
                raise RuntimeError("unexpected worker watchdog in baseline calibration")
            decision=business["decision"]
            status,latest["watchdog_pending"]=watchdog_observation(active_since,observed_now,
                decision.reason if decision else "",decision.activation_commit_ns if decision else 0,
                c["active_watchdog_ns"],c["T_ns"]+c["tick_jitter_ns"],latest["watchdog_pending"])
            if status in ("confirmed","timeout"):
                observations["watchdog_seen"]=status=="confirmed"
                stop_reason="owned_worker_active_watchdog" if status=="confirmed" else "owned_worker_watchdog_observation_timeout"
                supervisor.event("watchdog_observation_result",status=status,active_job=latest["active_job"],
                    external_active_since_ns=active_since,pending_since_ns=latest["watchdog_pending"],
                    original_watchdog_ns=c["active_watchdog_ns"],observation_grace_ns=c["T_ns"]+c["tick_jitter_ns"])
                break'''
 assert s.count(old)==1;s=s.replace(old,new);return s
def vrx(s):
 s=s.replace('source_observation','source_observation, watchdog_observation',1)
 s=s.replace('"imu": None, "path": None, "clock": None, "applied": None}', '"imu": None, "path": None, "clock": None, "applied": None, "decision": None, "watchdog_pending": None}')
 s=s.replace('observations["decision_count"] += 1','observations["decision_count"] += 1\n                latest["decision"] = msg',1)
 old='''            if latest["active_since"] is not None and now - latest["active_since"] > c["active_watchdog_ns"]:
                observations["watchdog_seen"] = True
                stop_reason = "owned_worker_active_watchdog"
                if fault == "none":
                    raise RuntimeError("unexpected native-owned worker watchdog")
                break'''
 new='''            observed_now=time.monotonic_ns()
            if latest["active_since"] is not None and observed_now-latest["active_since"]>c["active_watchdog_ns"] and fault=="none":
                raise RuntimeError("unexpected native-owned worker watchdog")
            decision=latest["decision"]
            status,latest["watchdog_pending"]=watchdog_observation(latest["active_since"],observed_now,
                decision.reason if decision else "",decision.activation_commit_ns if decision else 0,
                c["active_watchdog_ns"],c["T_ns"]+c["tick_jitter_ns"],latest["watchdog_pending"])
            if status in ("confirmed","timeout"):
                observations["watchdog_seen"]=status=="confirmed"
                stop_reason="owned_worker_active_watchdog" if status=="confirmed" else "owned_worker_watchdog_observation_timeout"
                supervisor.event("watchdog_observation_result",status=status,active_job=latest["active_job"],
                    external_active_since_ns=latest["active_since"],pending_since_ns=latest["watchdog_pending"],
                    original_watchdog_ns=c["active_watchdog_ns"],observation_grace_ns=c["T_ns"]+c["tick_jitter_ns"])
                break'''
 assert s.count(old)==1;s=s.replace(old,new);return s
change("run_no_output_calibration.py","9a06623342c133f3f59225171b28808607aaaf7e402dff1a0193483da831b177",nooutput)
change("run_p1_vrx_validation.py","0a88b159b803a8b52378fb194985efbc2d46ea674504b6812b011791bab0c0dd",vrx)
test=root/"test_watchdog_observation.py";assert not test.exists()
test.write_text('''import unittest
from run_no_output_calibration import watchdog_observation as observe
class WatchdogObservationRisks(unittest.TestCase):
    def test_equality_is_not_expiry_and_external_expiry_needs_regulator(self):
        self.assertEqual(observe(100,1100,"",0,1000,220),("idle",None))
        self.assertEqual(observe(100,1101,"",0,1000,220),("pending",1101))
    def test_delayed_regulator_confirmation_is_in_finite_observation_window(self):
        self.assertEqual(observe(100,1121,"worker_unusable",1120,1000,220,1101),("confirmed",1101))
    def test_stale_or_future_decision_cannot_confirm_watchdog(self):
        for stamp in (1099,1122):self.assertEqual(observe(100,1121,"worker_unusable",stamp,1000,220,1101),("pending",1101))
    def test_confirmation_deadline_is_inclusive_and_overdue_fails(self):
        self.assertEqual(observe(100,1321,"worker_unusable",1321,1000,220,1101),("confirmed",1101))
        self.assertEqual(observe(100,1322,"worker_unusable",1322,1000,220,1101),("timeout",1101))
if __name__=="__main__":unittest.main()
''',encoding="utf-8",newline="\n")
