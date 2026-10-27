"""Independent source / actual CDR storage checks for the worker integration fixture.
This is not the normal P1 contract checker and does not validate the real regulator.
"""
from collections import Counter
import argparse
import hashlib
import json
import math
from pathlib import Path

from p1_payload_digest import payload_digest
from owned_process_supervisor import sha256_file
from run_worker_fault_matrix import TOPICS, BAD_CASES, EXPECTED_CONTRACT, EXPECTED_WORKER

def fail_if(issues, condition, reason):
    if condition: issues.append(reason)

def assess(context, summary, fixture, worker, ledger, jobs, candidates, caps):
    issues = []
    scenario = context["scenario"]
    fail_if(issues,context.get("payload_schema")!="ros-fields-ieee754-v1","canonical payload schema missing")
    attempts = [e for e in fixture if e["type"]=="job_publish_attempt"]
    acked = [e for e in fixture if e["type"]=="job_publish_acked"]
    declared = Counter((e["payload_sha256"],e["job_id"]) for e in attempts)
    actual = Counter((e["payload_sha256"],e["message"]["job_id"]) for e in jobs)
    fail_if(issues, declared!=actual, "fixture publication / actual job content differs")
    fail_if(issues, len(acked)!=len(attempts) or Counter((e["label"],e["job_id"]) for e in acked)!=Counter((e["label"],e["job_id"]) for e in attempts), "publication acknowledgements incomplete")
    fail_if(issues, summary.get("sent_jobs")!=len(attempts), "runner sent count mismatch")
    fail_if(issues, summary.get("failure") is not None, "runner failed")
    fail_if(issues, context.get("contract_hash")!=EXPECTED_CONTRACT or context.get("worker_sha256")!=EXPECTED_WORKER, "unqualified fixture identity")
    fail_if(issues, context.get("production_regulator_present") is not False or summary.get("production_regulator_present") is not False, "fixture role ambiguous")
    fail_if(issues, summary.get("physical_publisher_samples_all_zero") is not True or summary.get("graph_samples",0)<1, "zero physical endpoint observation missing")
    fail_if(issues, summary.get("asset_postcheck",{}).get("drift")!=[] or context.get("asset_precheck",{}).get("drift")!=[], "asset identity drift / missing guard")
    fail_if(issues, summary.get("cleanup_complete") is not True or summary.get("supervision_evidence_complete") is not True, "owned cleanup / evidence incomplete")
    clean = summary.get("cleanup",{})
    for name in ("worker","recorder"):
        item = clean.get(name,{})
        fail_if(issues, item.get("cleanup_complete") is not True or item.get("remaining_members")!=[], "owned residual: "+name)
    spawns = [e for e in ledger if e["type"]=="spawn" and e.get("name")=="worker"]
    fail_if(issues, len(spawns)!=1 or not spawns[0].get("executable_verified") or spawns[0].get("expected_sha256")!=EXPECTED_WORKER, "owned executable not verified")
    pid = summary.get("worker_pid")
    instance = summary.get("worker_instance")
    if spawns: fail_if(issues, spawns[0].get("identity",{}).get("pid")!=pid, "worker PID binding mismatch")
    fail_if(issues, not caps, "actual capabilities absent")
    for cap in caps:
        fail_if(issues, (cap["pid"],cap["worker_instance"],cap["run_id"],cap["boot_id"],cap["contract_hash"])!=(pid,instance,context["run_id"],context["boot_id"],EXPECTED_CONTRACT), "foreign actual capability")
        fail_if(issues, cap["pending_count"]>1 or cap["backend"]!="acados" or cap["matrix_layout"]!="column_major" or cap["horizon_steps"]!=20 or cap["prediction_dt"]!=.2, "actual capability capacity / layout")
    summaries = [e for e in worker if e["type"]=="worker_summary"]
    ready = [e for e in worker if e["type"]=="worker_recording_ready"]
    fail_if(issues,len(ready)!=1 or ready[0].get("worker_instance")!=instance or ready[0].get("candidate_matched",0)<2, "actual recorder-ready handshake absent")
    w_candidates = [e for e in worker if e["type"]=="candidate"]
    fail_if(issues,len(w_candidates)!=len(candidates), "worker source / actual candidate count differs")
    by_id = {}
    for e in w_candidates:
        key = e["job"]["job_id"]
        fail_if(issues,key in by_id,"worker generated duplicate candidate")
        by_id[key]=e
    msg_ids = Counter(e["message"]["job"]["job_id"] for e in candidates)
    fail_if(issues, any(v!=1 for v in msg_ids.values()), "duplicate actual candidate")
    for entry in candidates:
        m = entry["message"]; jid=m["job"]["job_id"]; source=by_id.get(jid,{})
        fail_if(issues, (entry["job_payload_sha256"],jid) not in declared, "candidate job does not echo an actual sent payload")
        fail_if(issues,m["worker_instance"]!=instance or m["job"]["worker_instance"]!=instance or m["backend"]!="acados" or not m["solver_invoked"],"candidate source / native invocation invalid")
        aliases={"schema_version":"schema", "horizon_steps":"N", "prediction_dt":"dt",
                 "tick_origin_steady_ns":"tick_origin_ns", "freeze_steady_ns":"freeze_ns",
                 "deadline_steady_ns":"deadline_ns", "target_steady_ns":"target_ns"}
        source_job={aliases.get(k,k):v for k,v in m["job"].items()}
        fail_if(issues,source.get("job")!=source_job,"candidate full frozen job differs from source")
        pairs={"receive_ns":"worker_receive_ns","solve_start_ns":"solve_start_ns","solve_end_ns":"solve_end_ns",
               "solver_invoked":"solver_invoked","success":"success","prediction_available":"prediction_available",
               "backend":"backend","backend_ms":"backend_ms","reason":"reason","first_control":"first_control","X":"x_prediction","U":"u_prediction"}
        fail_if(issues, any(source.get(k)!=m[v] for k,v in pairs.items()),"candidate full result differs from source")
        fail_if(issues, not (m["worker_receive_ns"]<=m["solve_start_ns"]<=m["solve_end_ns"]
                            and m["solve_start_ns"]<=m["job"]["deadline_steady_ns"]), "native started after original deadline")
    rejected = Counter((e["job_id"],e["reason"]) for e in worker if e["type"]=="job_rejected")
    unknown = []
    source_complete = False
    if scenario=="death":
        fail_if(issues,summaries!=[] or candidates!=[],"abrupt exit unexpectedly recorded terminal summary or candidate")
        signals=[e for e in ledger if e["type"]=="signal" and e.get("name")=="worker"]
        fail_if(issues,not any(e["signal"]==9 for e in signals) or clean.get("worker",{}).get("returncode")!=-9,"declared owned SIGKILL not proven")
        fail_if(issues,not any(m["active_job"]==100 for m in caps),"active worker not observed before kill")
        fail_if(issues, len(attempts)!=1 or attempts[0]["label"]!="valid_initial","death input declaration mismatch")
        unknown=["worker_terminal_summary_missing","worker_source_completeness_unknown","worker_flush_success_unproven"]
    else:
        fail_if(issues,len(summaries)!=1,"worker terminal summary missing / duplicated")
        if summaries:
            s=summaries[0]
            source_complete=(s.get("normal_source_complete") is True and s.get("fatal") is False
                             and s.get("generated_candidates")==len(candidates)==s.get("published_candidates")
                             and s.get("completed_jobs")==len(candidates))
            fail_if(issues,not source_complete,"worker normal terminal counts / completeness disagree")
        fail_if(issues,clean.get("worker",{}).get("returncode")!=0 or clean.get("recorder",{}).get("returncode")!=0,"normal fixture child exit not zero")
        expected = {100,300,400} if scenario=="invalid" else {100} if scenario=="queue" else {100,1000,300}
        fail_if(issues,set(msg_ids)!=expected,"unexpected native candidate IDs")
        if scenario=="invalid":
            reasons=Counter((e["job_id"],e["expected"]) for e in attempts if e["expected"]!="success")
            fail_if(issues,rejected!=reasons,"actual reject ledger differs from all declared malformed / old / late jobs")
            fail_if(issues,context.get("case_declaration")!=[list(x) for x in BAD_CASES],"case matrix declaration changed")
            fail_if(issues,len(attempts)!=len(BAD_CASES)+6,"negative matrix publication count differs")
        elif scenario=="queue":
            replacements=[(e["job_id"],e["replacement_job_id"]) for e in worker if e["type"]=="pending_replaced"]
            fail_if(issues,replacements!=[(i,i+1) for i in range(201,212)],"pending replacement chain incomplete or reordered")
            expired=[e for e in worker if e["type"]=="pending_expired_before_native"]
            fail_if(issues,len(expired)!=1 or expired[0].get("job_id")!=212 or expired[0].get("solver_invoked") is not False,"latest pending was not rejected before native")
            fail_if(issues,not any(m["active_job"]==100 and m["pending_count"]==1 for m in caps),"bounded active+pending state not actually observed")
            fail_if(issues,rejected!=Counter() or len(attempts)!=13,"queue inputs dropped into unexpected rejection path")
            order=[e["type"] for e in worker]
            fail_if(issues,order.index("candidate")<max((i for i,v in enumerate(order) if v=="pending_replaced"),default=-1),"replacement phase not before delayed candidate")
        elif scenario=="numerical":
            failed=[e["message"] for e in candidates if e["message"]["job"]["job_id"]==1000]
            fail_if(issues,len(failed)!=1 or failed[0]["success"] or failed[0]["prediction_available"] or not failed[0]["reason"],"real finite-overflow native failure not proven")
            stress=[e["message"] for e in jobs if e["message"]["job_id"]==1000]
            fail_if(issues,len(stress)!=1 or stress[0]["target_state"][3]!=1e200 or not all(math.isfinite(x) for x in stress[0]["target_state"]),"numerical stimulus not the declared finite value")
            fail_if(issues,rejected!=Counter(),"finite numerical stress rejected before native")
        else: issues.append("unsupported scenario")
        for entry in candidates:
            m=entry["message"]
            if m["job"]["job_id"]!=1000:
                fail_if(issues,not m["success"] or not m["prediction_available"],"normal / recovery native result unsuccessful")
    return {"schema":"p1-worker-matrix-check-v1","scenario":scenario,"run_id":context["run_id"],
            "fixture_mechanism_complete":not issues,"worker_source_contract_complete":source_complete,
            "issues":sorted(set(issues)),"unknown":unknown,
            "actual_jobs":len(jobs),"actual_candidates":len(candidates),
            "reject_events":sum(rejected.values()),"replacement_events":sum(e["type"]=="pending_replaced" for e in worker),
            "max_pending_actual":max((m["pending_count"] for m in caps),default=None),
            "production_regulator_validated":False,"candidate_consumption_validated":False,
            "normal_contract_complete":False,"execute_qualified":False}

def scan(bag):
    import yaml
    import rosbag2_py
    from rclpy.serialization import deserialize_message, serialize_message
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from check_p1_execution import plain
    meta=yaml.safe_load((bag/"metadata.yaml").read_text())["rosbag2_bagfile_information"]
    if meta["storage_identifier"]!="mcap": raise ValueError("expected actual mcap storage")
    declared={v["topic_metadata"]["name"]:(v["topic_metadata"]["type"],int(v["message_count"])) for v in meta["topics_with_message_count"]}
    if set(declared)!=set(TOPICS) or any(declared[k][0]!=v for k,v in TOPICS.items()): raise ValueError("actual metadata topics / types mismatch")
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id="mcap"),rosbag2_py.ConverterOptions("cdr","cdr"))
    if {v.name:v.type for v in reader.get_all_topics_and_types()}!=TOPICS: raise ValueError("storage / metadata type mismatch")
    classes={k:get_message(v) for k,v in TOPICS.items()};result={k:[] for k in TOPICS}
    while reader.has_next():
        topic,blob,t=reader.read_next();m=deserialize_message(blob,classes[topic])
        e={"message":plain(dict(message_to_ordereddict(m))),"cdr_sha256":hashlib.sha256(blob).hexdigest(),"payload_sha256":payload_digest(m)}
        if topic=="/p1/solve_candidate": e["job_cdr_sha256"]=hashlib.sha256(serialize_message(m.job)).hexdigest();e["job_payload_sha256"]=payload_digest(m.job)
        result[topic].append(e)
    if any(len(result[k])!=declared[k][1] for k in TOPICS) or sum(map(len,result.values()))!=meta["message_count"]: raise ValueError("actual storage counts differ from metadata")
    return result

def check(directory):
    def j(name): return json.loads((directory/name).read_text())
    def lines(name):
        raw=(directory/name).read_bytes()
        if not raw or not raw.endswith(b"\n"): raise ValueError("unclosed source "+name)
        return [json.loads(line,parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x))) for line in raw.decode().splitlines()]
    tracked=[p for p in directory.rglob("*") if p.is_file() and p.name!="worker_matrix_check.json"]
    before={str(p):sha256_file(p) for p in tracked}
    data=scan(directory/"raw_bag")
    report=assess(j("run_context.json"),j("runner_summary.json"),lines("fixture_source.jsonl"),
                  lines("worker_source.jsonl"),lines("owned_process_ledger.jsonl"),
                  data["/p1/solve_job"],data["/p1/solve_candidate"],[e["message"] for e in data["/p1/worker_capability"]])
    if any(sha256_file(Path(p))!=v for p,v in before.items()): raise RuntimeError("evidence changed during independent scan")
    console=(directory/"worker.console.log").read_text(errors="replace")
    if report["scenario"]!="death" and "WORKER_CLOSE_FLUSH_SUCCESS=true" not in console:
        report["issues"].append("worker actual flush success missing");report["fixture_mechanism_complete"]=False;report["worker_source_contract_complete"]=False
    report["evidence_sha256"]=before
    report["actual_topic_counts"]={k:len(v) for k,v in data.items()}
    with (directory/"worker_matrix_check.json").open("x") as f: json.dump(report,f,indent=2,sort_keys=True);f.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k!="evidence_sha256"}))
    return 0 if report["fixture_mechanism_complete"] and report["worker_source_contract_complete"] else 2

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("directory",type=Path)
    raise SystemExit(check(parser.parse_args().directory))
