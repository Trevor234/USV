"""Bounded, create-only integration fixtures for the unchanged real P1 worker.
The node named p1_regulator is a test sender/observer, not the production regulator.
No physical command publisher is constructed. This suite does not qualify execute.
"""
from __future__ import annotations
import argparse
from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time

from owned_process_supervisor import Supervisor, boot_id, sha256_file
from run_no_output_calibration import host_preflight, load_contract, exclusive_json

TOPICS = {"/p1/solve_job": "usv_research_interfaces/msg/SolveJob",
          "/p1/solve_candidate": "usv_research_interfaces/msg/SolveCandidate",
          "/p1/worker_capability": "usv_research_interfaces/msg/WorkerCapability"}
EXPECTED_WORKER = "2abb6819e8d99b466bd371d7ae28fabf8e265644331045dfc47c2cb890e0c886"
EXPECTED_CONTRACT = "27ac689a712e35cec4af5dcf43eb085ae54a41857a3d992fd56fff5dffcb7dab"

# Declarative malformed payloads; expected reasons are checked after process close.
BAD_CASES = [
 ("schema", "foreign"), ("run", "foreign"), ("boot", "foreign"),
 ("contract", "foreign"), ("nominal", "foreign"), ("instance", "foreign"),
 ("negative_origin", "invalid_time_order"), ("future_freeze", "invalid_time_order"),
 ("future_odom_receive", "invalid_time_order"),
 ("N", "shape_or_time_contract"), ("dt", "shape_or_time_contract"),
 ("deadline", "shape_or_time_contract"), ("target_time", "shape_or_time_contract"),
 ("target_nan", "nonfinite"), ("frozen_inf", "nonfinite"),
 ("reference_nan", "nonfinite"), ("anchor_nan", "nonfinite"),
 ("anchor_unknown", "unknown_or_invalid_anchor"),
 ("anchor_limit", "unknown_or_invalid_anchor"), ("anchor_future", "unknown_or_invalid_anchor"),
 ("history_lengths", "history_shape_or_time"), ("history_nan", "history_shape_or_time"),
 ("rtf", "history_shape_or_time"), ("clock_future", "history_shape_or_time"),
 ("history_channel", "invalid_history"), ("history_order", "invalid_history"),
 ("history_limit", "invalid_history")]

def verify_assets(path):
    data = json.loads(path.read_text())
    rows = data if isinstance(data, list) else data.get("files", data.get("assets", data))
    if isinstance(rows, dict):
        rows = [dict(v, path=k) for k, v in rows.items()]
    drift = []
    for row in rows:
        p = Path(row["path"])
        actual = sha256_file(p) if p.is_file() else "missing"
        if actual != row["sha256"]:
            drift.append({"path": str(p), "actual": actual})
    if drift:
        raise RuntimeError("declared assets changed: " + json.dumps(drift))
    return {"manifest": str(path), "manifest_sha256": sha256_file(path),
            "count": len(rows), "drift": []}

def mutate(j, label):
    if label in ("schema", "run", "boot", "contract", "nominal", "instance"):
        field = {"schema":"schema_version", "run":"run_id", "boot":"boot_id",
                 "contract":"contract_hash", "nominal":"nominal_hash", "instance":"worker_instance"}[label]
        setattr(j, field, "foreign_fixture")
    elif label == "negative_origin": j.tick_origin_steady_ns = -1
    elif label == "future_freeze": j.freeze_steady_ns += 1000000000
    elif label == "future_odom_receive": j.odom_receive_ns += 1
    elif label == "N": j.horizon_steps = 19
    elif label == "dt": j.prediction_dt = .1
    elif label == "deadline": j.deadline_steady_ns += 1
    elif label == "target_time": j.target_steady_ns += 1
    elif label == "target_nan": j.target_state[0] = math.nan
    elif label == "frozen_inf": j.frozen_state[0] = math.inf
    elif label == "reference_nan": j.reference[125] = math.nan
    elif label == "anchor_nan": j.anchor_n[0] = math.nan
    elif label == "anchor_unknown": j.anchor_known[1] = False
    elif label == "anchor_limit": j.anchor_n[1] = 25.001
    elif label == "anchor_future": j.anchor_publish_ns[0] = j.freeze_steady_ns + 1
    elif label == "history_lengths": j.history_n = [0.0]
    elif label == "history_nan": j.history_n = [math.nan, 0.0]
    elif label == "rtf": j.assumed_rtf = .999
    elif label == "clock_future": j.frozen_clock_receive_ns += 1
    elif label == "history_channel": j.history_channel = [0, 2]
    elif label == "history_order": j.history_sim_ns = [1000000001, 1000000000]
    elif label == "history_limit": j.history_n = [25.001, 0.0]
    else: raise ValueError(label)

def run(args):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,119}", args.run_id):
        raise ValueError("invalid run id")
    c, digest = load_contract(args.contract, EXPECTED_CONTRACT)
    if not c["fault_injection_enabled"]: raise RuntimeError("diagnostic fault contract required")
    preflight = host_preflight()
    before = verify_assets(args.guard_manifest)
    worker = (args.workspace / "install/usv_research_safety_cpp/lib/usv_research_safety_cpp/p1_solver_worker").resolve(strict=True)
    if sha256_file(worker) != EXPECTED_WORKER: raise RuntimeError("production worker identity changed")
    python = Path(sys.executable).resolve(strict=True)
    ros2 = Path(shutil.which("ros2") or "").resolve(strict=True)
    if not ros2.is_file() or ros2.name != "ros2": raise RuntimeError("ROS environment missing")
    directory = args.experiment_root.resolve() / args.run_id
    directory.mkdir(exist_ok=False)
    delay = 1000 if args.scenario in ("queue", "death") else 0
    context = {"schema":"p1-worker-matrix-context-v1", "run_id":args.run_id,
        "scenario":args.scenario, "boot_id":boot_id(), "contract_hash":digest,
        "nominal_hash":c["nominal_hash"], "worker_sha256":EXPECTED_WORKER,
        "runner_sha256":sha256_file(Path(__file__)), "supervisor_sha256":sha256_file(Path(__file__).with_name("owned_process_supervisor.py")),
        "driver_role":"synthetic_job_sender_and_candidate_observer",
        "production_regulator_present":False, "domain":98, "test_delay_ms":delay,
        "case_declaration":BAD_CASES if args.scenario=="invalid" else [],
        "limits":{"startup_s":10, "candidate_s":2, "total_s":35, "driver_cache":256,
                  "active":1,"pending":1,"dds_depth":1},
        "asset_precheck":before, "execute_qualified":False, "normal_contract_complete":False}
    exclusive_json(directory/"run_context.json", context)
    exclusive_json(directory/"host_preflight.json", preflight)
    supervisor = Supervisor(directory)
    fixture = (directory/"fixture_source.jsonl").open("x")
    node = None
    failure = None
    cleanup = {}
    caps = deque(maxlen=256)
    candidates = deque(maxlen=64)
    latest = {"cap":None, "owned_pid":None, "instance":None}
    sent = 0
    graph_samples = 0
    max_pending = 0
    started = time.monotonic()

    def event(kind, **data):
        fixture.write(json.dumps({"type":kind, "monotonic_ns":time.monotonic_ns(), **data}, allow_nan=False)+"\n")
        fixture.flush()
    try:
        os.environ.update(ROS_DOMAIN_ID="98", ROS_LOCALHOST_ONLY="1")
        env = dict(os.environ)
        import rclpy
        from rclpy.signals import SignalHandlerOptions
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from rclpy.duration import Duration
        from rclpy.serialization import serialize_message
        from usv_research_interfaces.msg import SolveJob, SolveCandidate, WorkerCapability
        rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
        def interrupted(_signal, _frame): raise KeyboardInterrupt("operator stop")
        signal.signal(signal.SIGINT, interrupted)
        signal.signal(signal.SIGTERM, interrupted)
        node = rclpy.create_node("p1_regulator")
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)
        capq = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                          durability=DurabilityPolicy.TRANSIENT_LOCAL)
        jobpub = node.create_publisher(SolveJob, "/p1/solve_job", qos)
        # Type declarations have no data publications.
        decl = [node.create_publisher(SolveCandidate, "/p1/solve_candidate", qos),
                node.create_publisher(WorkerCapability, "/p1/worker_capability", capq)]

        def capability(m):
            nonlocal max_pending
            if m.run_id != args.run_id or m.boot_id != context["boot_id"] or m.contract_hash != digest:
                raise RuntimeError("foreign capability in isolated domain")
            if latest["owned_pid"] is not None and m.pid != latest["owned_pid"]:
                raise RuntimeError("capability PID is not owned worker")
            if latest["instance"] is not None and m.worker_instance != latest["instance"]:
                raise RuntimeError("worker instance changed")
            latest["cap"] = m
            max_pending = max(max_pending, m.pending_count)
            caps.append({"receive_ns":time.monotonic_ns(), "pid":m.pid, "instance":m.worker_instance,
                         "active_job":m.active_job,"pending_count":m.pending_count,"completed":m.completed_jobs,
                         "fatal":m.fatal})
            if m.pending_count>1: raise RuntimeError("pending capacity exceeded")

        def candidate(m):
            if m.worker_instance != latest["instance"] or m.job.run_id != args.run_id:
                raise RuntimeError("foreign candidate")
            candidates.append({"job_id":m.job.job_id,"success":m.success,
                "prediction_available":m.prediction_available,"solver_invoked":m.solver_invoked,
                "backend":m.backend,"reason":m.reason,"receive_ns":time.monotonic_ns()})
        node.create_subscription(WorkerCapability,"/p1/worker_capability",capability,capq)
        node.create_subscription(SolveCandidate,"/p1/solve_candidate",candidate,qos)

        def spin():
            nonlocal graph_samples
            rclpy.spin_once(node,timeout_sec=.005)
            graph_samples += 1
            endpoints = {k:node.count_publishers(t) for k,t in c["output_topics"].items()}
            if any(endpoints.values()): raise RuntimeError("physical publisher detected")
            if time.monotonic()-started > 35: raise TimeoutError("finite fixture total budget exceeded")
            child = supervisor.owned.get("worker")
            if child and child.process.poll() is not None and args.scenario!="death":
                raise RuntimeError("unexpected worker process exit")
        def wait(predicate, seconds):
            end = time.monotonic()+seconds
            while time.monotonic()<end:
                spin()
                if predicate(): return
            raise TimeoutError("fixture condition timeout")
        def settle(seconds):
            end = time.monotonic()+seconds
            while time.monotonic()<end: spin()

        settle(1)
        names = node.get_node_names_and_namespaces()
        if sum(n=="p1_regulator" for n,_ in names)!=1 or any(n in {"p1_solver_worker","mpc_node"} for n,_ in names):
            raise RuntimeError("existing controller in fixture domain")
        recorder = supervisor.spawn("recorder",[str(python),str(ros2),"bag","record","--storage","mcap",
                 "--output",str(directory/"raw_bag"),*TOPICS],env,python,sha256_file(python))
        wait(lambda: recorder.process.poll() is None and (directory/"raw_bag").is_dir()
             and all(any("recorder" in v.node_name for v in node.get_subscriptions_info_by_topic(t)) for t in TOPICS),10)
        child = supervisor.spawn("worker",[str(worker),"--ros-args","-p","run_id:="+args.run_id,
            "-p","contract_file:="+str(args.contract.resolve()),"-p","contract_hash:="+digest,
            "-p","source_file:="+str(directory/"worker_source.jsonl"),"-p","test_delay_ms:="+str(delay)],
            env,worker,EXPECTED_WORKER)
        latest["owned_pid"] = child.process.pid
        wait(lambda: latest["cap"] is not None,10)
        cap = latest["cap"]
        if (cap.schema_version!="p1-worker-capability-v1" or cap.pid!=child.process.pid
            or cap.backend!="acados" or cap.fatal or cap.matrix_layout!="column_major"
            or cap.horizon_steps!=20 or cap.prediction_dt!=.2 or cap.clock_name!="CLOCK_MONOTONIC"
            or cap.nominal_hash!=c["nominal_hash"]):
            raise RuntimeError("actual capability invalid")
        latest["instance"] = cap.worker_instance
        def armed():
            p = directory/"worker_source.jsonl"
            return p.is_file() and any(json.loads(line).get("type")=="worker_recording_ready"
                                     for line in p.read_text().splitlines())
        wait(lambda: armed() and jobpub.get_subscription_count()>=2,10)
        event("fixture_armed",pid=cap.pid,worker_instance=cap.worker_instance,physical_publishers=0)

        def make(jobid, late=False):
            now = time.monotonic_ns()
            origin = now-200000000 if late else now
            freeze = origin if late else time.monotonic_ns()
            j = SolveJob()
            j.schema_version="p1-solve-job-v1";j.run_id=args.run_id;j.boot_id=context["boot_id"]
            j.contract_hash=digest;j.nominal_hash=c["nominal_hash"];j.worker_instance=latest["instance"]
            j.job_id=jobid;j.target_tick=jobid+1
            j.task_generation=1;j.model_generation=1;j.config_generation=1;j.schedule_generation=1;j.clock_epoch=1
            j.tick_origin_steady_ns=origin;j.freeze_steady_ns=freeze
            j.deadline_steady_ns=origin+150000000;j.target_steady_ns=origin+200000000
            j.target_sim_ns=1200000000;j.odom_stamp_ns=1000000000;j.imu_stamp_ns=1000000000
            j.odom_receive_ns=freeze;j.imu_receive_ns=freeze;j.odom_sequence=1;j.imu_sequence=1;j.r_from_imu=True
            j.horizon_steps=20;j.prediction_dt=.2;j.reset_warmstart=True
            j.anchor_n=[0.0,0.0];j.anchor_sequence=[1,1];j.anchor_publish_ns=[freeze-1,freeze-1];j.anchor_known=[True,True]
            j.frozen_clock_sim_ns=1000000000;j.frozen_clock_receive_ns=freeze;j.assumed_rtf=1.0
            j.anchor_source="synthetic_fixture";j.anchor_producer="p1_worker_fixture";j.anchor_run_id=args.run_id
            j.history_sim_ns=[1000000000,1000000000];j.history_channel=[0,1];j.history_n=[0.0,0.0]
            return j
        def send(j,label,expected):
            nonlocal sent
            raw = serialize_message(j)
            event("job_publish_attempt",label=label,job_id=j.job_id,expected=expected,
                  cdr_sha256=hashlib.sha256(raw).hexdigest(),cdr_bytes=len(raw))
            jobpub.publish(j)
            if not jobpub.wait_for_all_acked(Duration(seconds=.1)): raise TimeoutError("job DDS acknowledgement timeout")
            sent+=1
            event("job_publish_acked",label=label,job_id=j.job_id)
            settle(.01)
        def got(jobid): return any(v["job_id"]==jobid for v in candidates)
        send(make(100),"valid_initial","success")
        if args.scenario=="death":
            wait(lambda: latest["cap"].active_job==100,1)
            event("declared_abrupt_worker_kill",pid=child.process.pid,worker_instance=latest["instance"])
            supervisor.send(child,signal.SIGKILL)
            wait(lambda: child.process.poll() is not None,1)
            settle(.6)
        elif args.scenario=="queue":
            wait(lambda: latest["cap"].active_job==100,1)
            for i in range(201,213): send(make(i),"pending_"+str(i),"superseded" if i<212 else "pending_expired")
            settle(.25)
            wait(lambda: got(100),2)
            wait(lambda: latest["cap"].active_job==0 and latest["cap"].pending_count==0,1)
            settle(.2)
        else:
            wait(lambda: got(100),2)
            if not any(v["job_id"]==100 and v["success"] and v["prediction_available"] for v in candidates):
                raise RuntimeError("initial real native solve did not succeed")
            if args.scenario=="invalid":
                for i,(label,reason) in enumerate(BAD_CASES,1001):
                    j=make(i);mutate(j,label);send(j,label,reason)
                send(make(100),"duplicate","duplicate_or_reordered")
                send(make(99),"old_id","duplicate_or_reordered")
                send(make(200,late=True),"expired_original_deadline","late_before_native")
            else:
                j=make(1000);j.frozen_state[3]=1e200;j.target_state[3]=1e200
                send(j,"finite_overflow_stress","native_failure")
                wait(lambda: got(1000),2)
            send(make(300),"valid_recovery","success")
            wait(lambda: got(300),2)
            if args.scenario=="invalid":
                j=make(400);j.history_sim_ns=[1000000000]*256
                j.history_channel=[i%2 for i in range(256)];j.history_n=[0.0]*256
                send(j,"maximum_bounded_history","success")
                wait(lambda: got(400),2)
            settle(.25)
        event("fixture_window_complete",scenario=args.scenario)
    except BaseException as error:
        failure=repr(error)
        event("fixture_exception",error=failure)
    finally:
        for name in ("worker","recorder"):
            child=supervisor.owned.get(name)
            if child:
                if name=="recorder": time.sleep(.3)
                cleanup[name]=supervisor.stop(child,c["worker_grace_ns"]/1e9,c["term_grace_ns"]/1e9,c["kill_postcheck_ns"]/1e9)
        if node is not None: node.destroy_node()
        if "rclpy" in locals() and rclpy.ok(): rclpy.shutdown()
        event("fixture_summary",sent_jobs=sent,cache_capabilities=len(caps),
              graph_samples=graph_samples,max_pending=max_pending,failure=failure,fixture_source_complete=True)
        fixture.close()
        supervisor.close()
        try: after=verify_assets(args.guard_manifest)
        except BaseException as error: after={"drift_unknown":repr(error)};failure=failure or repr(error)
        summary={"schema":"p1-worker-matrix-runner-summary-v1","run_id":args.run_id,"scenario":args.scenario,
            "failure":failure,"cleanup":cleanup,"cleanup_complete":not supervisor.cleanup_failed,
            "supervision_evidence_complete":not supervisor.evidence_failed,
            "capability_observations":list(caps),"candidate_observations":list(candidates),
            "sent_jobs":sent,"graph_samples":graph_samples,"max_pending":max_pending,
            "physical_publisher_samples_all_zero":graph_samples>0 and failure is None,
            "asset_postcheck":after,"worker_instance":latest["instance"],"worker_pid":latest["owned_pid"],
            "production_regulator_present":False,"normal_contract_complete":False,"execute_qualified":False}
        exclusive_json(directory/"runner_summary.json",summary)
    print(json.dumps({"run_id":args.run_id,"scenario":args.scenario,"failure":failure,
                      "cleanup_complete":summary["cleanup_complete"],"sent_jobs":sent}))
    return 1 if failure or supervisor.cleanup_failed else 0

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--contract",type=Path,required=True);p.add_argument("--guard-manifest",type=Path,required=True)
    p.add_argument("--experiment-root",type=Path,required=True);p.add_argument("--workspace",type=Path,default=Path("/home/trevor/USV/usv_mpc_ws"))
    p.add_argument("--run-id",required=True);p.add_argument("--scenario",choices=("invalid","queue","numerical","death"),required=True)
    return run(p.parse_args())
if __name__=="__main__": raise SystemExit(main())
