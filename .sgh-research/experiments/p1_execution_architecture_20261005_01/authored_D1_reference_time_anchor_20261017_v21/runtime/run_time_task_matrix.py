"""Real regulator time/task/activation matrix; synthetic inputs, no physical output.
Original worker native candidates only. Create-only runs and immutable raw evidence.
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
    context = {"schema":"p1-real-time-task-v1", "run_id":args.run_id,"scenario":args.scenario,
               "boot_id":boot_id(),"contract_hash":digest,"contract_file":str(args.contract.resolve()),
               "topics":topics,"binaries":binaries,"runner_sha256":sha256_file(Path(__file__)),
               "production_regulator_present":True,"mode":"no_output","execute_qualified":False,
               "asset_precheck":guard,"limits":{"total_s":60,"startup_s":12,"fault_observation_s":1.0,"recovery_s":4.0},
               "test_native_block_ms":0,"injection_policy":"after_original_deadline_before_target",
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
                latest[key] = m
                counts[key] += 1
                fields={"topic":topic,"payload_sha256":payload_digest(m)}
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
            if time.monotonic()-started>60: raise TimeoutError("total bounded run timeout")
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
        # Select an actual fresh native result with sufficient time remaining.
        wait(lambda: latest["candidate"] is not None and latest["candidate"].success
             and latest["candidate"].solver_invoked and latest["candidate"].job.job_id>first.job_id
             and latest["candidate"].job.target_steady_ns-time.monotonic_ns()>70_000_000)
        selected=deepcopy(latest["candidate"]);j=selected.job
        due=j.deadline_steady_ns+5_000_000
        while time.monotonic_ns()<due:spin()
        if time.monotonic_ns()>=j.target_steady_ns-20_000_000:
            raise RuntimeError("deadline-window injection missed its reserved margin")
        stage="fault"
        fault={"kind":args.scenario,"ns":time.monotonic_ns(),"job_id":j.job_id,
               "deadline_ns":j.deadline_steady_ns,"target_ns":j.target_steady_ns,
               "target_tick":j.target_tick,"task_generation":j.task_generation,
               "schedule_generation":j.schedule_generation,"epoch":j.clock_epoch,
               "candidate_payload_sha256":payload_digest(selected)}
        event("fault_declared",**fault)
        if args.scenario=="path_clear":path.poses=[]
        elif args.scenario=="path_replace":
            for pose in path.poses:pose.pose.position.y=.4
        elif args.scenario=="profile_change":
            for i in range(20):profile.data[4*i]=.5
        elif args.scenario in ("pair_incomplete","paired_refresh"):
            path.header.stamp.sec=2
            if args.scenario=="paired_refresh":profile.layout.dim[0].label="stamp_sec:2"
        elif args.scenario=="clock_pause":paused_sim=1_000_000_000+time.monotonic_ns()-input_origin+sim_offset
        elif args.scenario=="clock_rollback":sim_offset-=1_000_000_000
        elif args.scenario=="clock_jump":sim_offset+=6_000_000_000
        elif args.scenario=="odom_timeout":publish_odom=False
        elif args.scenario=="source_lag":source_shift=-300_000_000
        elif args.scenario=="source_future":source_shift=200_000_000
        elif args.scenario=="activation_deviation":position_x=.75
        else:raise ValueError("unrecognized scenario")
        publish_reference();next_ref=time.monotonic_ns()+1_000_000_000;next_input=time.monotonic_ns()
        settle(1.0)
        event("fault_observation_end",fault=fault,counts=dict(counts))
        if args.scenario not in ("clock_rollback","clock_jump"):
            stage="recovery"
            recovery_ns=time.monotonic_ns()
            if args.scenario=="clock_pause":
                sim_offset=paused_sim-(1_000_000_000+recovery_ns-input_origin);paused_sim=None
            publish_odom=True;source_shift=0;position_x=0.0
            if args.scenario=="pair_incomplete":profile.layout.dim[0].label="stamp_sec:2"
            elif args.scenario!="paired_refresh":path=deepcopy(original_path);profile=deepcopy(original_profile)
            event("recovery_declared",recovery_ns=recovery_ns)
            publish_reference();next_ref=time.monotonic_ns()+1_000_000_000;next_input=time.monotonic_ns()
            wait(lambda:latest["decision"] is not None and latest["decision"].candidate_accepted
                 and latest["decision"].activation_commit_ns>recovery_ns,4)
            event("recovery_acceptance_observed",sequence=latest["decision"].sequence,
                  activation_commit_ns=latest["decision"].activation_commit_ns,job_id=latest["decision"].job_id)
            settle(.25)
        else:event("reset_anchor_recovery_not_assumed",requires="new_run_or_actual_publisher_anchor")
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
        summary={"schema":"p1-real-time-task-summary-v1","run_id":args.run_id,"scenario":args.scenario,
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
    p.add_argument("--scenario",choices=("path_clear","path_replace","profile_change","pair_incomplete","paired_refresh","clock_pause","clock_rollback","clock_jump","odom_timeout","source_lag","source_future","activation_deviation"),required=True)
    p.add_argument("--run-id",required=True);p.add_argument("--contract",type=Path,required=True)
    p.add_argument("--experiment-root",type=Path,required=True);p.add_argument("--guard-manifest",type=Path,required=True)
    p.add_argument("--worker-sha256",required=True);p.add_argument("--regulator-sha256",required=True)
    p.add_argument("--workspace",type=Path,default=Path("/home/trevor/USV/usv_mpc_ws"))
    raise SystemExit(run(p.parse_args()))
