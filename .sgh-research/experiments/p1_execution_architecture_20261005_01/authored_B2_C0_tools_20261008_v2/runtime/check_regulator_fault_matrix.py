"""Independent actual bag/source verification of real regulator fault linkage."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
from owned_process_supervisor import sha256_file
from p1_payload_digest import payload_digest

def linkage(scenario, fault, jobs, registrations, candidates, decisions, transitions, end_ns):
    issues=[]
    if not fault or not isinstance(fault.get("ns"),int):
        return {"issues":["actual fault missing"],"mechanism_complete":False}
    at=fault["ns"]
    fail=lambda cond,msg: issues.append(msg) if cond else None
    fail(end_ns-at<1_200_000_000,"post-fault observation shorter than 1.2 s")
    fail(scenario=="idle_exit" and fault.get("active_job")!=0,"idle state not observed")
    fail(scenario=="active_exit" and fault.get("active_job",0)<=0,"active state not observed")
    after=[d for d in decisions if d["activation_commit_ns"]>=at]
    fail(not after,"no actual decisions after fault")
    unusable=[d for d in after if d["reason"]=="worker_unusable"]
    fail(not unusable,"regulator never observed worker unusable")
    event=next((e for e in transitions if e["processed_ns"]>=at-250_000_000),None)
    terminal=event["processed_ns"] if event else (unusable[0]["activation_commit_ns"] if unusable else None)
    budget=450_000_000 if scenario=="numerical" else 220_000_000
    if terminal is not None:
        fail(terminal-at>budget,"fault observation exceeded declared tick boundary")
        fail(any(j.get("submit_commit_ns",j["publish_start_ns"])>terminal for j in jobs),"new job commit after terminal observation")
        fail(any(d["accepted"] and d["activation_commit_ns"]>=terminal for d in decisions),"candidate activated after terminal observation")
    if event:
        fail(event.get("candidate_after") is not False or event.get("pending_after") is not False,"terminal invalidation not proven")
        if scenario.endswith("exit"):
            fail(event.get("reason")!="worker_process_exited","exit source cause mismatch")
    failed=[]
    if scenario=="numerical":
        failed=[m for m in candidates if m["job"]["job_id"]==fault.get("job_id") and m["solver_invoked"] and not m["success"]]
        fail(len(failed)!=1,"actual native failed candidate missing")
        reg=[r for r in registrations if r["job"]["job_id"]==fault.get("job_id")]
        fail(len(reg)!=1 or reg[0]["accepted_registration"] or reg[0]["reason"]!="solver_failed","failed candidate not rejected as solver_failed")
    else:
        fail(any(d["accepted"] and d["activation_commit_ns"]>=at+budget for d in decisions),"candidate activated beyond death observation bound")
    return {"issues":issues,"mechanism_complete":not issues,"terminal_observed_ns":terminal,
            "terminal_source_invalidation_proven":event is not None and event.get("candidate_after") is False and event.get("pending_after") is False,
            "detection_budget_ns":budget,"post_fault_decisions":len(after),
            "precommitted_publication_tail":sum(j.get("submit_commit_ns",j["publish_start_ns"])<=terminal<j["publish_start_ns"] for j in jobs) if terminal else None}

def scan(bag,topics):
    import yaml
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from check_p1_execution import plain
    meta=yaml.safe_load((bag/"metadata.yaml").read_text())["rosbag2_bagfile_information"]
    if meta["storage_identifier"]!="mcap": raise ValueError("unexpected storage")
    rows={r["topic_metadata"]["name"]:(r["topic_metadata"]["type"],r["message_count"]) for r in meta["topics_with_message_count"]}
    if {k:v[0] for k,v in rows.items()}!=topics: raise ValueError("metadata topic identity mismatch")
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id="mcap"),rosbag2_py.ConverterOptions("cdr","cdr"))
    if {v.name:v.type for v in reader.get_all_topics_and_types()}!=topics: raise ValueError("storage type identity mismatch")
    result={k:[] for k in topics};classes={k:get_message(v) for k,v in topics.items()}
    while reader.has_next():
        topic,blob,_=reader.read_next();m=deserialize_message(blob,classes[topic])
        result[topic].append({"message":plain(dict(message_to_ordereddict(m))),"payload_sha256":payload_digest(m),"cdr_sha256":hashlib.sha256(blob).hexdigest()})
    if any(len(result[k])!=rows[k][1] for k in topics) or sum(map(len,result.values()))!=meta["message_count"]:
        raise ValueError("storage counts do not equal metadata")
    return result

def check(directory):
    output=directory/"verification_linkage_v2"
    if output.exists(): raise FileExistsError("create-only verification already exists")
    def j(name): return json.loads((directory/name).read_text())
    def lines(name):
        b=(directory/name).read_bytes()
        if not b.endswith(b"\n"): raise ValueError("unclosed source: "+name)
        return [json.loads(v) for v in b.decode().splitlines()]
    tracked={str(p):sha256_file(p) for p in directory.rglob("*") if p.is_file() and p.name!="regulator_fault_check.json"}
    context=j("run_context.json");summary=j("runner_summary.json")
    fixture=lines("fixture_source.jsonl");reg=lines("regulator_source.jsonl");ledger=lines("owned_process_ledger.jsonl")
    is_exit=context["scenario"].endswith("exit")
    worker_bytes=(directory/"worker_source.jsonl").read_bytes()
    worker_tail_unclosed=not worker_bytes.endswith(b"\n")
    if is_exit:
        # SIGKILL may interrupt a buffered line. Preserve its bytes and classify
        # the missing suffix as unknown; never repair the original source file.
        prefix=worker_bytes[:worker_bytes.rfind(b"\n")+1]
        worker=[json.loads(v) for v in prefix.decode().splitlines()]
    else: worker=lines("worker_source.jsonl")
    data=scan(directory/"raw_bag",context["topics"])
    msgs=lambda topic:[e["message"] for e in data[topic]]
    issues=[]
    def require(ok,why):
        if not ok: issues.append(why)
    require(summary["failure"] is None,"runner exception")
    require(summary["cleanup_complete"] and summary["supervision_evidence_complete"],"cleanup or supervisor evidence failed")
    require(summary["zero_physical_endpoints"] and summary["graph_samples"]>0,"zero physical endpoint evidence missing")
    require(context["production_regulator_present"] and summary["production_regulator_present"],"real regulator role missing")
    require(context["asset_precheck"]["drift"]==summary["asset_postcheck"]["drift"]==[],"asset drift")
    for name in ("regulator","worker","recorder"):
        require(summary["cleanup"].get(name,{}).get("remaining_members")==[],"owned residual: "+name)
        sp=[e for e in ledger if e["type"]=="spawn" and e["name"]==name]
        require(len(sp)==1 and sp[0]["executable_verified"],"actual executable binding missing: "+name)
        if name!="recorder" and sp: require(sp[0]["expected_sha256"]==context["binaries"][name]["sha256"],"binary hash differs: "+name)
    typed=("/p1/solve_job","/p1/solve_candidate","/p1/execution_decision")
    for topic in typed:
        observed=Counter(e["payload_sha256"] for e in fixture if e["type"]=="observed" and e["topic"]==topic)
        actual=Counter(e["payload_sha256"] for e in data[topic])
        require(observed==actual,"observer / actual full field content differs: "+topic)
    sj=[e for e in reg if e["type"]=="job"];sc=[e for e in worker if e["type"]=="candidate"];sd=[e for e in reg if e["type"]=="decision"]
    jobs=msgs("/p1/solve_job");candidates=msgs("/p1/solve_candidate");decisions=msgs("/p1/execution_decision")
    require((len(sj),len(sd))==(len(jobs),len(decisions)),"regulator source / storage count mismatch")
    if not is_exit: require(len(sc)==len(candidates),"worker source / storage count mismatch")
    aliases={"schema_version":"schema","horizon_steps":"N","prediction_dt":"dt","tick_origin_steady_ns":"tick_origin_ns",
             "freeze_steady_ns":"freeze_ns","deadline_steady_ns":"deadline_ns","target_steady_ns":"target_ns"}
    byid={m["job_id"]:m for m in jobs}
    require(len(byid)==len(jobs),"actual duplicate job ID")
    for e in sj:
        actual=byid.get(e["job"]["job_id"],{})
        require({aliases.get(k,k):v for k,v in actual.items()}==e["job"],"full submitted job echo mismatch")
    for e,m in zip(sc,candidates):
        require({aliases.get(k,k):v for k,v in m["job"].items()}==e["job"],"worker source frozen job differs")
        pairs={"receive_ns":"worker_receive_ns","solve_start_ns":"solve_start_ns","solve_end_ns":"solve_end_ns",
               "solver_invoked":"solver_invoked","success":"success","prediction_available":"prediction_available",
               "backend":"backend","backend_ms":"backend_ms","reason":"reason","first_control":"first_control","X":"x_prediction","U":"u_prediction"}
        require(all(e.get(k)==m[v] for k,v in pairs.items()),"full native result differs from source")
    for e,m in zip(sd,decisions):
        require(all(e[k]==m[v] for k,v in {"sequence":"sequence","job_id":"job_id","accepted":"candidate_accepted",
                    "reason":"reason","activation_commit_ns":"activation_commit_ns","final_n":"final_n"}.items()),"decision commit/source differs")
    require(all(m["pid"]==summary["worker_pid"] and m["worker_instance"]==summary["worker_instance"]
             and m["boot_id"]==context["boot_id"] and m["contract_hash"]==context["contract_hash"] for m in msgs("/p1/worker_capability")),"foreign actual capability")
    require(any(e["type"]=="input_armed" and all(v>=2 for v in e["matches"].values()) for e in fixture),"input DDS arm absent")
    for key in ("clock","odom","imu","path","profile"):
        topic="/clock" if key=="clock" else json.loads(Path(context["contract_file"]).read_text())["input_topics"][key]
        require(summary["counts"].get("input_"+key)==len(data[topic]),"fixture input / bag count differs: "+key)
    rs=[e for e in reg if e["type"]=="source_summary"]
    require(len(rs)==1 and rs[0]["normal_source_complete"] and rs[0]["dropped"]==0 and rs[0]["generated"]==rs[0]["emitted"],"regulator source not complete")
    require("REGULATOR_CLOSE_FLUSH_SUCCESS=true" in (directory/"regulator.console.log").read_text(),"regulator flush unproven")
    unknown=[]
    if is_exit:
        require(summary["cleanup"]["worker"]["returncode"]==-9,"actual worker SIGKILL not proven")
        require(any(e["type"]=="signal" and e["name"]=="worker" and e["signal"]==9 for e in ledger),"owned signal missing")
        unknown=["worker_terminal_summary_missing","worker_source_completeness_unknown","worker_flush_success_unproven"]
        if worker_tail_unclosed: unknown.append("worker_source_partial_last_line_preserved")
    else:
        require(any(m["fatal"] for m in msgs("/p1/worker_capability")),"actual fatal capability missing")
        require(any(e["type"]=="terminal_numerical_failure" for e in worker),"native quarantine source missing")
        require("WORKER_CLOSE_FLUSH_SUCCESS=true" in (directory/"worker.console.log").read_text(),"numerical worker flush unproven")
    transitions=[e for e in reg if e["type"]=="worker_unusable_transition"]
    end=next((e["ns"] for e in fixture if e["type"]=="post_fault_observation_end"),0)
    result=linkage(context["scenario"],summary["fault"],sj,[e for e in reg if e["type"]=="candidate_registration"],candidates,sd,transitions,end)
    result["issues"] = issues+result["issues"]
    result.update(schema="p1-real-regulator-fault-check-v1",scenario=context["scenario"],run_id=context["run_id"],
                  actual_topic_counts={k:len(v) for k,v in data.items()},source_typed_counts={"job":len(sj),"candidate":len(sc),"decision":len(sd)},
                  evidence_accounting_complete=not issues,worker_source_accounting_complete=not is_exit and len(sc)==len(candidates),
                  mechanism_complete=not result["issues"],unknown=unknown,
                  normal_contract_complete=False,execute_qualified=False,evidence_sha256=tracked)
    if any(sha256_file(Path(p))!=v for p,v in tracked.items()): raise RuntimeError("evidence changed during scan")
    output.mkdir()
    with (output/"regulator_fault_check.json").open("x") as f: json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k!="evidence_sha256"}))
    return 0 if result["mechanism_complete"] else 2

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("directory",type=Path)
    raise SystemExit(check(p.parse_args().directory))
