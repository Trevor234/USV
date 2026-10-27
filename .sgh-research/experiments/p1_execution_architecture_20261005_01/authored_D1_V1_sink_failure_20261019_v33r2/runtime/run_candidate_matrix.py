"""Real regulator candidate transport matrix, zero physical endpoints.
Injected copies are declared transport stimuli, distinct from original native output.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time

from owned_process_supervisor import Supervisor, boot_id, sha256_file
from run_no_output_calibration import host_preflight, load_contract, exclusive_json
from run_worker_fault_matrix import verify_assets
from p1_payload_digest import payload_digest
from candidate_fault_spec import CASES, mutate

def run(args):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,119}", args.run_id):
        raise ValueError("explicit bounded run ID required")
    c, digest = load_contract(args.contract)
    if not c.get("fault_injection_enabled") or c.get("execute_qualified"):
        raise ValueError("diagnostic fault contract required")
    preflight = host_preflight()
    guard = verify_assets(args.guard_manifest)
    directory = args.experiment_root.resolve() / args.run_id
    directory.mkdir(exist_ok=False)
    worker = (args.workspace / "install/usv_research_safety_cpp/lib/usv_research_safety_cpp/p1_solver_worker").resolve(strict=True)
    regulator = worker.with_name("p1_regulator").resolve(strict=True)
    python = Path(sys.executable).resolve(strict=True)
    ros2 = Path(shutil.which("ros2") or "").resolve(strict=True)
    binaries = {k:{"path":str(p), "sha256":sha256_file(p)} for k,p in
                (("worker",worker),("regulator",regulator),("python",python),("ros2",ros2))}
    if binaries["worker"]["sha256"] != args.worker_sha256 or binaries["regulator"]["sha256"] != args.regulator_sha256:
        raise ValueError("predeclared binary identity mismatch")
    topics = {"/clock":"rosgraph_msgs/msg/Clock",c["input_topics"]["odom"]:"nav_msgs/msg/Odometry",
              c["input_topics"]["imu"]:"sensor_msgs/msg/Imu",c["input_topics"]["path"]:"nav_msgs/msg/Path",
              c["input_topics"]["profile"]:"std_msgs/msg/Float64MultiArray",
              "/p1/solve_job":"usv_research_interfaces/msg/SolveJob",
              "/p1/solve_candidate":"usv_research_interfaces/msg/SolveCandidate",
              "/p1/worker_capability":"usv_research_interfaces/msg/WorkerCapability",
              "/p1/execution_decision":"usv_research_interfaces/msg/ExecutionDecision", "/p1/stop":"std_msgs/msg/Bool"}
    env = dict(os.environ, ROS_DOMAIN_ID="99", ROS_LOCALHOST_ONLY="1")
    os.environ.update(ROS_DOMAIN_ID="99", ROS_LOCALHOST_ONLY="1")
    context = {"schema":"p1-candidate-transport-v1", "run_id":args.run_id,"scenario":args.scenario,
               "boot_id":boot_id(),"contract_hash":digest,"contract_file":str(args.contract.resolve()),
               "topics":topics,"binaries":binaries,"runner_sha256":sha256_file(Path(__file__)),
               "production_regulator_present":True,"mode":"no_output","execute_qualified":False,
               "asset_precheck":guard,"limits":{"total_s":90,"startup_s":12,"fault_observation_s":1.0,"recovery_s":4.0},
               "test_native_block_ms":0,"injection_policy":"declared_copy_of_real_native_candidate","declared_cases":CASES,
               "created_ns":time.monotonic_ns()}
    exclusive_json(directory / "run_context.json", context)
    exclusive_json(directory / "host_preflight.json", preflight)
    supervisor = Supervisor(directory)
    log = (directory / "fixture_source.jsonl").open("x")
    node = rclpy = None
    started = time.monotonic()
    failure = fault = None
    cleanup = {}
    samples = 0
    counts = Counter()
    latest = {"cap":None,"job":None,"candidate":None,"decision":None}
    native_latest=None;native_history={};injected_hashes=set();observed_hashes=Counter()
    stage = "startup"
    def event(event_type, **fields):
        log.write(json.dumps({"type":event_type,"ns":time.monotonic_ns(),**fields},sort_keys=True,allow_nan=False)+"\n")
        log.flush()
    try:
        import rclpy
        from rclpy.signals import SignalHandlerOptions
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from rosgraph_msgs.msg import Clock
        from nav_msgs.msg import Odometry, Path as RosPath
        from sensor_msgs.msg import Imu
        from std_msgs.msg import Float64MultiArray, MultiArrayDimension, Bool
        from geometry_msgs.msg import PoseStamped
        from usv_research_interfaces.msg import SolveJob, SolveCandidate, WorkerCapability, ExecutionDecision
        rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
        def interrupted(_sig,_frame): raise KeyboardInterrupt("operator stop")
        signal.signal(signal.SIGINT,interrupted)
        signal.signal(signal.SIGTERM,interrupted)
        node = rclpy.create_node("p1_calibration_driver")
        qos = QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE)
        capq = QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        # Observer depth is finite; production endpoints remain depth 1.
        observeq = QoSProfile(depth=64,reliability=ReliabilityPolicy.RELIABLE)
        pubs = {"clock":node.create_publisher(Clock,"/clock",qos),
                "odom":node.create_publisher(Odometry,c["input_topics"]["odom"],qos),
                "imu":node.create_publisher(Imu,c["input_topics"]["imu"],qos),
                "path":node.create_publisher(RosPath,c["input_topics"]["path"],qos),
                "profile":node.create_publisher(Float64MultiArray,c["input_topics"]["profile"],qos)}
        stop_pub = node.create_publisher(Bool,"/p1/stop",qos)
        declarations = [node.create_publisher(SolveJob,"/p1/solve_job",qos),
                        node.create_publisher(SolveCandidate,"/p1/solve_candidate",qos),
                        node.create_publisher(WorkerCapability,"/p1/worker_capability",capq),
                        node.create_publisher(ExecutionDecision,"/p1/execution_decision",qos)]
        for key,kind,topic in (("cap",WorkerCapability,"/p1/worker_capability"),
                ("job",SolveJob,"/p1/solve_job"),("candidate",SolveCandidate,"/p1/solve_candidate"),
                ("decision",ExecutionDecision,"/p1/execution_decision")):
            def observe(m,key=key,topic=topic):
                nonlocal native_latest
                latest[key] = m
                counts[key] += 1
                fields={"topic":topic,"payload_sha256":payload_digest(m)}
                observed_hashes[fields["payload_sha256"]]+=1
                if key=="candidate" and fields["payload_sha256"] not in injected_hashes:
                    native_latest=deepcopy(m);native_history[m.job.job_id]=deepcopy(m)
                    if len(native_history)>64:del native_history[min(native_history)]
                if key=="cap": fields.update(pid=m.pid,instance=m.worker_instance,active_job=m.active_job,
                          pending_count=m.pending_count,fatal=m.fatal,completed_jobs=m.completed_jobs)
                elif key=="job": fields.update(job_id=m.job_id,target_tick=m.target_tick)
                elif key=="candidate": fields.update(job_id=m.job.job_id,success=m.success,
                          prediction_available=m.prediction_available,solver_invoked=m.solver_invoked)
                else: fields.update(sequence=m.sequence,reason=m.reason,accepted=m.candidate_accepted,
                          activation_commit_ns=m.activation_commit_ns,job_id=m.job_id)
                event("observed",**fields)
            node.create_subscription(kind,topic,observe,capq if key=="cap" else observeq)
        path = RosPath();path.header.frame_id=c["expected_pose_frame"];path.header.stamp.sec=1
        profile = Float64MultiArray()
        for label in ("stamp_sec:1","stamp_nanosec:0"):
            dim=MultiArrayDimension();dim.label=label;profile.layout.dim.append(dim)
        for i in range(20):
            pose=PoseStamped();pose.header=path.header;pose.pose.position.x=i*.5;pose.pose.orientation.w=1.
            path.poses.append(pose);profile.data.extend([.6,0.,0.,i*.5/.6])
        input_origin = next_input = next_ref = None
        sim_offset=0;paused_sim=None;publish_odom=True;source_shift=0;position_x=0.0
        original_path=deepcopy(path);original_profile=deepcopy(profile)
        def publish_reference():
            for key,m in (("path",path),("profile",profile)):
                pubs[key].publish(m);counts["input_"+key]+=1
                event("reference_publish",kind=key,payload_sha256=payload_digest(m),stage=stage)
        def spin():
            nonlocal samples,next_input,next_ref
            if time.monotonic()-started>90: raise TimeoutError("total bounded run timeout")
            now=time.monotonic_ns()
            if input_origin is not None and now>=next_input:
                next_input=now+20_000_000
                sim_ns=paused_sim if paused_sim is not None else 1_000_000_000+now-input_origin+sim_offset
                clock=Clock();clock.clock.sec,clock.clock.nanosec=divmod(sim_ns,1_000_000_000)
                odom=Odometry();odom.header.frame_id=c["expected_pose_frame"];odom.child_frame_id=c["expected_child_frame"]
                odom.header.stamp.sec,odom.header.stamp.nanosec=divmod(sim_ns+source_shift,1_000_000_000)
                odom.pose.pose.orientation.w=1.;odom.pose.pose.position.x=position_x
                imu=Imu();imu.header.stamp=odom.header.stamp;imu.header.frame_id=c["expected_imu_frame"]
                for key,m in (("clock",clock),("odom",odom),("imu",imu)):
                    if key=="odom" and not publish_odom:continue
                    pubs[key].publish(m);counts["input_"+key]+=1
                    event("input_publish",kind=key,payload_sha256=payload_digest(m),stage=stage)
                if now>=next_ref:
                    publish_reference()
                    next_ref=now+1_000_000_000
            rclpy.spin_once(node,timeout_sec=.005)
            samples+=1
            if any(node.count_publishers(t) for t in c["output_topics"].values()):
                raise RuntimeError("unexpected physical publisher")
            if supervisor.evidence_failed: raise RuntimeError("supervision IO failure")
        def wait(pred,seconds=12):
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                spin()
                if pred(): return
            raise TimeoutError("bounded condition not met: "+stage)
        def settle(seconds):
            end=time.monotonic()+seconds
            while time.monotonic()<end: spin()
        settle(1.)
        if any(n in {"p1_regulator","p1_solver_worker","mpc_controller_node"} for n,_ in node.get_node_names_and_namespaces()):
            raise RuntimeError("preexisting controller in diagnostic domain")
        recorder=supervisor.spawn("recorder",[str(python),str(ros2),"bag","record","--storage","mcap",
                "--output",str(directory/"raw_bag"),*topics],env,python,binaries["python"]["sha256"])
        wait(lambda: recorder.process.poll() is None and (directory/"raw_bag").is_dir()
            and all(any("recorder" in e.node_name for e in node.get_subscriptions_info_by_topic(t)) for t in topics))
        base=["--ros-args","-p","run_id:="+args.run_id,"-p","contract_file:="+str(args.contract.resolve()),"-p","contract_hash:="+digest]
        w=supervisor.spawn("worker",[str(worker),*base,"-p","source_file:="+str(directory/"worker_source.jsonl"),
                "-p","test_native_block_ms:="+str(context["test_native_block_ms"])],env,worker,args.worker_sha256)
        wait(lambda: latest["cap"] is not None)
        cap=latest["cap"]
        if (cap.pid!=w.process.pid or cap.fatal or cap.boot_id!=context["boot_id"] or cap.contract_hash!=digest
            or cap.run_id!=args.run_id or cap.backend!="acados"):
            raise RuntimeError("actual worker identity mismatch")
        context["worker_pid"]=cap.pid;context["worker_instance"]=cap.worker_instance
        event("worker_identity_verified",pid=cap.pid,instance=cap.worker_instance)
        r=supervisor.spawn("regulator",[str(regulator),*base,"-p","mode:=no_output","-p","worker_pid:="+str(w.process.pid),
                    "-p","source_file:="+str(directory/"regulator_source.jsonl")],env,regulator,args.regulator_sha256)
        wait(lambda: all(pub.get_subscription_count()>=2 for pub in pubs.values()))
        input_origin=next_input=next_ref=time.monotonic_ns()
        event("input_armed",required_subscribers=["recorder","p1_regulator"],
              matches={k:p.get_subscription_count() for k,p in pubs.items()})
        stage="normal_readiness"
        wait(lambda: latest["decision"] is not None and latest["decision"].candidate_accepted)
        first=latest["decision"]
        event("normal_acceptance_observed",sequence=first.sequence,activation_commit_ns=first.activation_commit_ns)
        last_base_id=first.job_id
        last_injection_ns=0
        for number,case in enumerate(CASES,1):
            stage="candidate_"+case[0]
            wait(lambda:native_latest is not None and native_latest.success and native_latest.solver_invoked
                 and native_latest.job.job_id>last_base_id
                 and native_latest.job.deadline_steady_ns-time.monotonic_ns()>70_000_000)
            barrier=deepcopy(native_latest);last_base_id=barrier.job.job_id
            base=barrier
            if case[2]=="previous":
                prior=[v for k,v in native_history.items() if k<barrier.job.job_id]
                if not prior:raise RuntimeError("actual earlier native candidate missing")
                base=deepcopy(max(prior,key=lambda v:v.job.job_id))
            settle(.020)
            if case[2]=="late":
                due=barrier.job.deadline_steady_ns+5_000_000
                while time.monotonic_ns()<due:spin()
            if time.monotonic_ns()>=barrier.job.target_steady_ns-20_000_000:
                raise RuntimeError("injection missed declared tick margin")
            injected=mutate(base,case);digest=payload_digest(injected)
            before=observed_hashes[digest]
            injected_hashes.add(digest)
            start_ns=time.monotonic_ns();last_injection_ns=start_ns
            event("candidate_injection",case_number=number,label=case[0],descriptor=case,
                  base_job_id=base.job.job_id,barrier_job_id=barrier.job.job_id,
                  injected_job_id=injected.job.job_id,base_payload_sha256=payload_digest(base),
                  injected_payload_sha256=digest,publish_start_ns=start_ns,
                  barrier_deadline_ns=barrier.job.deadline_steady_ns,barrier_target_ns=barrier.job.target_steady_ns,
                  expected_reason=case[4],is_original_native_result=False)
            declarations[1].publish(injected);counts["injected"]+=1
            event("candidate_injection_return",case_number=number,publish_end_ns=time.monotonic_ns())
            wait(lambda:observed_hashes[digest]>before,1.)
            settle(.025)
        fault={"kind":"candidate_matrix","ns":last_injection_ns,"injected_cases":len(CASES),"actual_native_failure_claimed":False}
        stage="post_matrix_normal"
        wait(lambda:latest["decision"] is not None and latest["decision"].candidate_accepted
             and latest["decision"].activation_commit_ns>last_injection_ns,2.)
        settle(.45)
        event("matrix_observation_end",counts=dict(counts),cases=len(CASES),last_injection_ns=last_injection_ns)
        stage="logical_stop"
        def stopped():
            msg=Bool();msg.data=True;stop_pub.publish(msg);return r.process.poll() is not None
        wait(stopped,c["shutdown_grace_ns"]/1e9+.5)
    except BaseException as error:
        failure=repr(error);event("run_exception",stage=stage,error=failure)
    finally:
        # Keep recorder through both production shutdown tails. Input publications
        # have a separately recorded prefix/suffix; no callback-loss claim is made.
        for name in ("regulator","worker","recorder"):
            child=supervisor.owned.get(name)
            if child:
                if name=="recorder": time.sleep(.25)
                cleanup[name]=supervisor.stop(child,c["worker_grace_ns"]/1e9,c["term_grace_ns"]/1e9,c["kill_postcheck_ns"]/1e9)
        event("fixture_summary",failure=failure,stage=stage,counts=dict(counts),physical_endpoints=0,samples=samples)
        log.close();supervisor.close()
        if node is not None: node.destroy_node()
        if rclpy is not None and rclpy.ok(): rclpy.shutdown()
        after=verify_assets(args.guard_manifest)
        summary={"schema":"p1-candidate-transport-summary-v1","run_id":args.run_id,"scenario":args.scenario,
                 "failure":failure,"fault":fault,"counts":dict(counts),"cleanup":cleanup,
                 "cleanup_complete":not supervisor.cleanup_failed,"supervision_evidence_complete":not supervisor.evidence_failed,
                 "asset_postcheck":after,"zero_physical_endpoints":samples>0,"graph_samples":samples,
                 "worker_pid":context.get("worker_pid"),"worker_instance":context.get("worker_instance"),
                 "fault_observation_s":1.0,"production_regulator_present":True,"execute_qualified":False,
                 "finished_ns":time.monotonic_ns()}
        exclusive_json(directory/"runner_summary.json",summary)
    print(json.dumps({"run_id":args.run_id,"failure":failure,"fault":fault,"cleanup_complete":summary["cleanup_complete"]}))
    return 1 if failure or not summary["cleanup_complete"] else 0

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenario",choices=("candidate_matrix",),required=True)
    p.add_argument("--run-id",required=True);p.add_argument("--contract",type=Path,required=True)
    p.add_argument("--experiment-root",type=Path,required=True);p.add_argument("--guard-manifest",type=Path,required=True)
    p.add_argument("--worker-sha256",required=True);p.add_argument("--regulator-sha256",required=True)
    p.add_argument("--workspace",type=Path,default=Path("/home/trevor/USV/usv_mpc_ws"))
    raise SystemExit(run(p.parse_args()))
