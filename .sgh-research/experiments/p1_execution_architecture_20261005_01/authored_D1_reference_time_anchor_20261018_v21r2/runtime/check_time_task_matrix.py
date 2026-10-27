"""Independent time/task matrix verification from immutable MCAP and source.
Expected failures qualify only the exercised diagnostic mechanism, never execute.
"""
from collections import Counter
import argparse
import json
from pathlib import Path
from owned_process_supervisor import sha256_file
from check_regulator_fault_matrix import scan
from check_p1_execution import JOB_ALIASES, CANDIDATE_ALIASES, CANDIDATE_FIELDS, DECISION_ALIASES, DECISION_V2_FIELDS
from p1_payload_digest import canonical_payload_digest

RESET = {"clock_rollback", "clock_jump"}
TASK = {"path_clear", "path_replace", "profile_change"}
EXPECTED = {"path_clear":"no_path", "pair_incomplete":"profile_pair_incomplete",
            "odom_timeout":"odom_timeout", "source_lag":"odom_sim_lag",
            "source_future":"odom_sim_future", "activation_deviation":"activation_state_mismatch"}

def mechanism(scenario, fault, reg, decisions, jobs, candidates, fixture, c):
    issues=[]
    def require(ok, why):
        if not ok: issues.append(why)
    if not fault or not isinstance(fault.get("ns"),int):
        return {"mechanism_complete":False,"issues":["fault missing"]}
    at=fault["ns"];jid=fault["job_id"];target=fault["target_ns"]
    end=next((e["ns"] for e in fixture if e["type"]=="fault_observation_end"),0)
    require(fault["deadline_ns"]<at<target-20_000_000,"injection outside reserved deadline window")
    require(end-at>=800_000_000,"fault observation shorter than 0.8 s")
    selected=[m for m in candidates if m["job"]["job_id"]==jid]
    ready=[e for e in reg if e["type"]=="candidate_registration" and e["job"]["job_id"]==jid]
    require(len(selected)==1 and selected[0]["success"] and selected[0]["solver_invoked"],"selected native success absent")
    if len(selected)==1:require(canonical_payload_digest(selected[0])==fault.get("candidate_payload_sha256"),"selected candidate digest differs from actual storage")
    require(len(ready)==1 and ready[0]["accepted_registration"] and ready[0]["ready_commit_ns"]<=fault["deadline_ns"],"selected candidate was not ready by original deadline")
    post=[d for d in decisions if at<=d["activation_commit_ns"]<end and d["reason"]!="shutdown"]
    require(len(post)>=4,"insufficient independent post-fault decisions")
    old=[d for d in post if d["job_id"]==jid and d["accepted"]]
    callback_ns=None
    if scenario in TASK or scenario in {"pair_incomplete","paired_refresh"}:
        typ="profile_version" if scenario=="profile_change" else "path_version"
        events=[e for e in reg if e["type"]==typ and at<=e["processed_ns"]<target]
        require(bool(events),"fault reference was not processed before original activation")
        if events:
            callback_ns=events[0]["processed_ns"]
            require(fault["deadline_ns"]<callback_ns<target,"callback outside cutoff-to-activation interval")
            changed=events[0]["task_generation"]!=fault["task_generation"]
            require(changed if scenario in TASK else not changed,"task generation does not match reference semantics")
            if scenario in TASK:
                require(not any(d["accepted"] and d["task_generation"]==fault["task_generation"] and d["activation_commit_ns"]>=callback_ns for d in post),"old task activated after processed invalidation")
        if scenario!="paired_refresh":require(not old,"selected old candidate activated after task/pair fault")
        else:
            require(len(old)==1,"same-semantic paired refresh lost the selected eligible candidate")
            require(all(d["task_generation"]==fault["task_generation"] for d in post),"same-semantic refresh unexpectedly changed task")
    if scenario in EXPECTED:
        stable=post
        if scenario=="odom_timeout":stable=[d for d in post if d["activation_commit_ns"]>=at+150_000_000]
        if scenario=="activation_deviation":stable=[d for d in post if d["job_id"]==jid]
        require(any(d["reason"]==EXPECTED[scenario] and not d["accepted"] for d in stable),"expected concrete rejection absent: "+EXPECTED[scenario])
        if scenario!="activation_deviation":require(not any(d["accepted"] for d in stable),"candidate accepted in persistent ineligible interval")
        if scenario in {"source_lag","source_future","activation_deviation"}:
            require(not old,"selected candidate activated after source/state fault")
        if scenario in {"source_lag","source_future"}:
            rows=[d for d in stable if d["reason"]==EXPECTED[scenario]]
            for d in rows:
                current=d["activation_clock_sim_ns"]+d["activation_commit_ns"]-d["activation_clock_receive_ns"]
                delta=current-d["activation_odom_stamp_ns"]
                require(d["odom_age_ns"]<=c["odom_age_ns"],"physical-time rejection actually has stale receipt")
                require(delta>c["odom_sim_lag_ns"] if scenario=="source_lag" else -delta>c["source_future_slack_ns"],"source time rejection lacks measured age")
        if scenario=="activation_deviation":
            rows=[d for d in stable if d["reason"]==EXPECTED[scenario]]
            require(bool(rows) and abs(rows[0]["state_error"][0])>c["activation_tolerance"][0],"activation x deviation is not beyond frozen component threshold")
    if scenario=="clock_pause":
        clocks=[e for e in reg if e["type"]=="clock" and at<=e["receive_ns"]<end]
        require(any(e["paused"] for e in clocks),"pause never confirmed")
        require(any(e["schedule_generation"]>fault["schedule_generation"] for e in clocks),"pause did not invalidate schedule")
        require(not old,"old candidate activated during clock pause")
        late=[d for d in post if d["activation_commit_ns"]>=at+c["clock_pause_confirm_ns"]+200_000_000]
        require(bool(late) and all(not d["accepted"] and d["reason"]=="clock_missing_stale_paused" for d in late),"confirmed pause did not block activation")
    if scenario in RESET:
        clocks=[e for e in reg if e["type"]=="clock" and at<=e["receive_ns"]<end]
        require(any(e["epoch"]==fault["epoch"]+1 and e["schedule_generation"]>fault["schedule_generation"] for e in clocks),"reset did not change epoch/schedule")
        require(not old and not any(d["accepted"] for d in post),"candidate activated after clock reset")
        require(any(d["reason"]=="unknown_anchor" for d in post),"reset anchor loss not exposed after RTF recovery")
        require(all(not any(d["anchor_known"]) for d in post),"reset synthetic anchor was silently restored")
        require(not any(e.get("submit_commit_ns",e["publish_start_ns"])>=at+50_000_000 for e in jobs),"new job after reset anchor loss")
    recovery=next((e["recovery_ns"] for e in fixture if e["type"]=="recovery_declared"),None)
    recovered=[d for d in decisions if recovery is not None and d["accepted"] and d["activation_commit_ns"]>recovery]
    if scenario not in RESET:require(bool(recovered),"independent later recovery acceptance absent")
    if scenario=="clock_pause" and recovered:
        require(recovered[0]["epoch"]==fault["epoch"] and recovered[0]["schedule_generation"]>=fault["schedule_generation"]+2,"resume did not reanchor schedule without raw epoch change")
    return {"mechanism_complete":not issues,"issues":issues,"selected_job_id":jid,
            "reference_processed_ns":callback_ns,"post_fault_decisions":len(post),
            "post_fault_reason_counts":dict(Counter(d["reason"] for d in post)),
            "selected_old_candidate_accepted":bool(old),"recovery_accepted_decisions":len(recovered),
            "reset_anchor_recovery_assumed":False,"execute_qualified":False}

def check(directory):
    output=directory/"verification_time_task_v1"
    if output.exists():raise FileExistsError("create-only verification")
    tracked={str(p):sha256_file(p) for p in directory.rglob("*") if p.is_file()}
    def j(name):return json.loads((directory/name).read_text())
    def lines(name):
        b=(directory/name).read_bytes()
        if not b.endswith(b"\n"):raise ValueError("source tail unclosed: "+name)
        return [json.loads(v) for v in b.decode().splitlines()]
    context=j("run_context.json");summary=j("runner_summary.json");c=json.loads(Path(context["contract_file"]).read_text())
    reg=lines("regulator_source.jsonl");worker=lines("worker_source.jsonl");fixture=lines("fixture_source.jsonl");ledger=lines("owned_process_ledger.jsonl")
    data=scan(directory/"raw_bag",context["topics"])
    msgs=lambda topic:[v["message"] for v in data[topic]]
    issues=[]
    def require(ok,why):
        if not ok:issues.append(why)
    require(summary["failure"] is None,"runner exception")
    require(summary["cleanup_complete"] and summary["supervision_evidence_complete"],"cleanup/supervision failed")
    require(summary["zero_physical_endpoints"] and summary["graph_samples"]>0,"zero physical graph unproven")
    require(context["production_regulator_present"] and summary["production_regulator_present"],"production regulator absent")
    require(context["asset_precheck"]["drift"]==summary["asset_postcheck"]["drift"]==[],"asset drift")
    for name in ("worker","regulator","recorder"):
        require(summary["cleanup"].get(name,{}).get("remaining_members")==[],"owned residual "+name)
        events=[e for e in ledger if e["type"]=="spawn" and e["name"]==name]
        require(len(events)==1 and events[0]["executable_verified"],"spawn identity missing "+name)
        if name!="recorder" and events:require(events[0]["expected_sha256"]==context["binaries"][name]["sha256"],"binary identity differs "+name)
    for topic in ("/p1/solve_job","/p1/solve_candidate","/p1/execution_decision"):
        observed=Counter(e["payload_sha256"] for e in fixture if e["type"]=="observed" and e["topic"]==topic)
        require(observed==Counter(e["payload_sha256"] for e in data[topic]),"actual full-field observer differs "+topic)
    for kind in ("clock","odom","imu","path","profile"):
        topic="/clock" if kind=="clock" else c["input_topics"][kind]
        published=Counter(e["payload_sha256"] for e in fixture if e["type"] in ("input_publish","reference_publish") and e["kind"]==kind)
        require(published==Counter(e["payload_sha256"] for e in data[topic]),"actual input payload/count differs "+kind)
    sj=[e for e in reg if e["type"]=="job"];sc=[e for e in worker if e["type"]=="candidate"];sd=[e for e in reg if e["type"]=="decision"]
    jobs=msgs("/p1/solve_job");candidates=msgs("/p1/solve_candidate");decisions=msgs("/p1/execution_decision")
    require((len(sj),len(sc),len(sd))==(len(jobs),len(candidates),len(decisions)),"source/bag typed count differs")
    for e,m in zip(sj,jobs):require({JOB_ALIASES.get(k,k):v for k,v in m.items()}==e["job"],"frozen job differs")
    for e,m in zip(sc,candidates):
        require({JOB_ALIASES.get(k,k):v for k,v in m["job"].items()}==e["job"],"candidate job differs")
        require(all(e.get(CANDIDATE_ALIASES.get(k,k))==m[k] for k in CANDIDATE_FIELDS),"full native candidate differs")
    for e,m in zip(sd,decisions):require(all(e.get(DECISION_ALIASES.get(k,k))==m[k] for k in DECISION_V2_FIELDS),"full decision differs")
    caps=msgs("/p1/worker_capability")
    require(bool(caps) and all(m["pid"]==summary["worker_pid"] and m["worker_instance"]==summary["worker_instance"] and not m["fatal"] for m in caps),"worker fatal/identity mismatch")
    for events,tag,console in ((reg,"source_summary","regulator"),(worker,"worker_summary","worker")):
        ends=[e for e in events if e["type"]==tag]
        require(len(ends)==1 and ends[0]["normal_source_complete"],"source incomplete "+console)
        require(console.upper()+"_CLOSE_FLUSH_SUCCESS=true" in (directory/(console+".console.log")).read_text(),"flush unproven "+console)
    require(any(e["type"]=="input_armed" and all(v>=2 for v in e["matches"].values()) for e in fixture),"DDS input arm absent")
    result=mechanism(context["scenario"],summary["fault"],reg,sd,sj,candidates,fixture,c)
    result["issues"]=issues+result["issues"]
    result.update(schema="p1-time-task-check-v1",run_id=context["run_id"],scenario=context["scenario"],
                  mechanism_complete=not result["issues"],evidence_accounting_complete=not issues,
                  source_typed_counts={"job":len(sj),"candidate":len(sc),"decision":len(sd)},
                  actual_topic_counts={k:len(v) for k,v in data.items()},evidence_sha256=tracked,
                  normal_contract_complete=False,plant_acceptance_observed=False)
    if any(sha256_file(Path(p))!=v for p,v in tracked.items()):raise RuntimeError("evidence changed during scan")
    output.mkdir()
    with (output/"time_task_check.json").open("x") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k!="evidence_sha256"}))
    return 0 if result["mechanism_complete"] else 2

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("directory",type=Path)
    raise SystemExit(check(p.parse_args().directory))
