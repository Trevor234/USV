"""Independent actual MCAP accounting and candidate rejection binding.
Transport injections are kept separate from original native worker results.
"""
from collections import Counter
from copy import deepcopy
import argparse
import json
import math
from pathlib import Path
from candidate_fault_spec import CASES
from check_regulator_fault_matrix import scan
from check_p1_execution import JOB_ALIASES, CANDIDATE_ALIASES, CANDIDATE_FIELDS, DECISION_ALIASES, DECISION_V2_FIELDS
from p1_payload_digest import canonical_payload_digest
from owned_process_supervisor import sha256_file

def null_invalid(v):
    if isinstance(v,float) and not math.isfinite(v):return None
    if isinstance(v,dict):return {k:null_invalid(x) for k,x in v.items()}
    if isinstance(v,list):return [null_invalid(x) for x in v]
    return v

def lookup(v,path):
    for part in path.split("."):v=v[int(part)] if part.isdecimal() else v[part]
    return v

def mutation_matches(base,actual,case):
    # Independent dictionary oracle; the driver operates on typed ROS objects.
    expected=deepcopy(base);_,field,op,value,_=case
    if field is not None:
        parts=field.split(".");p=expected
        for key in parts[:-1]:p=p[int(key)] if key.isdecimal() else p[key]
        key=int(parts[-1]) if parts[-1].isdecimal() else parts[-1]
        if op=="set":p[key]=value
        elif op=="add":p[key]=lookup(base,field)+value
        elif op=="special":p[key]=float(value)
        elif op=="relative":
            source,offset=value.split(":");p[key]=lookup(base,source)+int(offset)
        elif op=="append":p[key]=list(lookup(base,field))+[value]
        else:return False
    return canonical_payload_digest(expected)==canonical_payload_digest(actual)

def registration_matches(e,m):
    job={JOB_ALIASES.get(k,k):v for k,v in m["job"].items()}
    return (e["job"]==null_invalid(job) and e["worker_instance"]==m["worker_instance"]
            and e["solve_start_ns"]==m["solve_start_ns"] and e["solve_end_ns"]==m["solve_end_ns"]
            and e["first_control"]==null_invalid(m["first_control"]))

def audit(native,injections,registrations,decisions,actual,cases=CASES):
    issues=[];proof=[];used=set()
    def require(ok,why):
        if not ok:issues.append(why)
    require(len(injections)==len(cases),"declared case count not exercised")
    require([e["label"] for e in injections]==[c[0] for c in cases],"case order/identity differs")
    byid={m["job"]["job_id"]:m for m in native}
    require(len(byid)==len(native),"native duplicate job ID")
    bag_by_hash={canonical_payload_digest(m):m for m in actual}
    native_counts=Counter(canonical_payload_digest(m) for m in native)
    injected_counts=Counter(e["injected_payload_sha256"] for e in injections)
    require(Counter(canonical_payload_digest(m) for m in actual)==native_counts+injected_counts,"actual candidate multiset is not native plus declared injections")
    require(len(registrations)==len(actual),"actual candidate / registration count differs")
    for number,(event,case) in enumerate(zip(injections,cases),1):
        label=case[0];at=event["publish_start_ns"]
        require(event["case_number"]==number and event["descriptor"]==list(case),"declaration differs "+label)
        require(event["is_original_native_result"] is False,"injection mislabelled native "+label)
        base=byid.get(event["base_job_id"]);barrier=byid.get(event["barrier_job_id"])
        injected=bag_by_hash.get(event["injected_payload_sha256"])
        if base is None or barrier is None or injected is None:
            issues.append("actual base/barrier/injection missing "+label);continue
        require(canonical_payload_digest(base)==event["base_payload_sha256"],"base digest differs "+label)
        require(base["success"] and base["prediction_available"] and base["solver_invoked"],"base is not actual native success "+label)
        require(mutation_matches(base,injected,case),"undeclared candidate field/value changed "+label)
        require(event["expected_reason"]==case[4],"expected reason rewritten "+label)
        normal=[e for e in registrations if e["accepted_registration"] and registration_matches(e,barrier)]
        require(len(normal)==1 and normal[0]["ready_commit_ns"]<at and normal[0]["ready_commit_ns"]<=barrier["job"]["deadline_steady_ns"],"original barrier not registered before injection "+label)
        require(event["barrier_deadline_ns"]==barrier["job"]["deadline_steady_ns"] and event["barrier_target_ns"]==barrier["job"]["target_steady_ns"],"barrier original timing differs "+label)
        if case[2]=="late":require(barrier["job"]["deadline_steady_ns"]<at<barrier["job"]["target_steady_ns"]-20_000_000,"late injection timing absent")
        else:require(at<barrier["job"]["deadline_steady_ns"],"pre-deadline injection actually late "+label)
        if case[2]=="previous":require(base["job"]["target_tick"]<barrier["job"]["target_tick"],"reordered packet is not an earlier target")
        else:require(base["job"]["job_id"]==barrier["job"]["job_id"],"base identity is not current barrier "+label)
        matched=[(i,e) for i,e in enumerate(registrations) if i not in used and registration_matches(e,injected)
                 and at<=e["ready_commit_ns"]<=min(at+100_000_000,barrier["job"]["target_steady_ns"])]
        require(len(matched)==1,"registration not uniquely bound within original tick "+label)
        if matched:
            index,e=matched[0];used.add(index)
            require(not e["accepted_registration"] and e["reason"]==case[4],"actual registration not expected rejection "+label)
        activated=[d for d in decisions if d["accepted"] and d["job_id"]==barrier["job"]["job_id"]]
        require(len(activated)==1,"original legal candidate not activated exactly once "+label)
        if activated and len(normal)==1:
            require(activated[0]["ready_commit_ns"]==normal[0]["ready_commit_ns"] and activated[0]["requested_n"]==barrier["first_control"],"injection displaced original ready/command "+label)
        proof.append({"label":label,"base_job_id":event["base_job_id"],"barrier_job_id":event["barrier_job_id"],
                      "expected_reason":case[4],"actual_reason":matched[0][1]["reason"] if matched else None,
                      "source_ready_commit_ns":matched[0][1]["ready_commit_ns"] if matched else None,
                      "publish_start_ns":at,"is_original_native_result":False})
    if injections:
        first=injections[0]["publish_start_ns"];last=injections[-1]["publish_start_ns"]
        require(any(d["accepted"] and d["activation_commit_ns"]<first for d in decisions),"normal accepted prefix missing")
        require(any(d["accepted"] and d["activation_commit_ns"]>last for d in decisions),"normal accepted suffix missing")
    return {"issues":issues,"mechanism_complete":not issues,"case_proofs":proof,
            "declared_cases":len(cases),"injected_candidates":len(injections),"native_candidates":len(native),
            "actual_candidates":len(actual),"registrations":len(registrations),
            "injected_rejection_reason_counts":dict(Counter(e["actual_reason"] for e in proof)),
            "actual_native_failure_claimed":False,"illegal_cdr_verified":False}

def check(directory):
    output=directory/"verification_candidate_v1"
    if output.exists():raise FileExistsError("create-only verification")
    tracked={str(p):sha256_file(p) for p in directory.rglob("*") if p.is_file()}
    def j(name):return json.loads((directory/name).read_text())
    def lines(name):
        b=(directory/name).read_bytes()
        if not b.endswith(b"\n"):raise ValueError("unclosed source: "+name)
        return [json.loads(v) for v in b.decode().splitlines()]
    context=j("run_context.json");summary=j("runner_summary.json");c=json.loads(Path(context["contract_file"]).read_text())
    reg=lines("regulator_source.jsonl");worker=lines("worker_source.jsonl");fixture=lines("fixture_source.jsonl");ledger=lines("owned_process_ledger.jsonl")
    data=scan(directory/"raw_bag",context["topics"]);msgs=lambda t:[e["message"] for e in data[t]]
    issues=[]
    def require(ok,why):
        if not ok:issues.append(why)
    require(summary["failure"] is None and summary["cleanup_complete"] and summary["supervision_evidence_complete"],"runner/cleanup/evidence failure")
    require(context["production_regulator_present"] and summary["production_regulator_present"] and summary["zero_physical_endpoints"] and summary["graph_samples"]>0,"production/zero physical graph unproven")
    require(context["asset_precheck"]["drift"]==summary["asset_postcheck"]["drift"]==[],"asset drift")
    require(context["declared_cases"]==[list(v) for v in CASES],"context case declarations differ")
    for name in ("worker","regulator","recorder"):
        require(summary["cleanup"].get(name,{}).get("remaining_members")==[],"owned residual "+name)
        events=[e for e in ledger if e["type"]=="spawn" and e["name"]==name]
        require(len(events)==1 and events[0]["executable_verified"],"spawn identity missing "+name)
        if name!="recorder" and events:require(events[0]["expected_sha256"]==context["binaries"][name]["sha256"],"binary differs "+name)
    for topic in ("/p1/solve_job","/p1/solve_candidate","/p1/execution_decision"):
        obs=Counter(e["payload_sha256"] for e in fixture if e["type"]=="observed" and e["topic"]==topic)
        require(obs==Counter(e["payload_sha256"] for e in data[topic]),"observer/actual full fields differ "+topic)
    for kind in ("clock","odom","imu","path","profile"):
        topic="/clock" if kind=="clock" else c["input_topics"][kind]
        pubs=Counter(e["payload_sha256"] for e in fixture if e["type"] in ("input_publish","reference_publish") and e["kind"]==kind)
        require(pubs==Counter(e["payload_sha256"] for e in data[topic]),"input/actual content differs "+kind)
    sj=[e for e in reg if e["type"]=="job"];sd=[e for e in reg if e["type"]=="decision"];sc=[e for e in worker if e["type"]=="candidate"]
    jobs=msgs("/p1/solve_job");decisions=msgs("/p1/execution_decision");actual=msgs("/p1/solve_candidate")
    require((len(sj),len(sd))==(len(jobs),len(decisions)),"job/decision source count differs")
    for e,m in zip(sj,jobs):require(e["job"]=={JOB_ALIASES.get(k,k):v for k,v in m.items()},"full native job differs")
    for e,m in zip(sd,decisions):require(all(e.get(DECISION_ALIASES.get(k,k))==m[k] for k in DECISION_V2_FIELDS),"full decision differs")
    inverse={v:k for k,v in JOB_ALIASES.items()}
    native=[{"job":{inverse.get(k,k):v for k,v in e["job"].items()},**{k:e[CANDIDATE_ALIASES.get(k,k)] for k in CANDIDATE_FIELDS}} for e in sc]
    caps=msgs("/p1/worker_capability")
    require(bool(caps) and all(m["pid"]==summary["worker_pid"] and m["worker_instance"]==summary["worker_instance"] and not m["fatal"] for m in caps),"capability identity/fatal differs")
    for events,tag,console in ((reg,"source_summary","regulator"),(worker,"worker_summary","worker")):
        ends=[e for e in events if e["type"]==tag]
        require(len(ends)==1 and ends[0]["normal_source_complete"],"source incomplete "+console)
        require(console.upper()+"_CLOSE_FLUSH_SUCCESS=true" in (directory/(console+".console.log")).read_text(),"flush unproven "+console)
    require(any(e["type"]=="input_armed" and all(v>=2 for v in e["matches"].values()) for e in fixture),"DDS input arm absent")
    injections=[e for e in fixture if e["type"]=="candidate_injection"]
    require(summary["counts"].get("injected")==len(CASES),"runner injected count differs")
    result=audit(native,injections,[e for e in reg if e["type"]=="candidate_registration"],sd,actual)
    result["issues"]=issues+result["issues"]
    result.update(schema="p1-candidate-transport-check-v1",run_id=context["run_id"],
                  mechanism_complete=not result["issues"],evidence_accounting_complete=not issues,
                  actual_topic_counts={k:len(v) for k,v in data.items()},source_typed_counts={"job":len(sj),"native_candidate":len(sc),"decision":len(sd)},
                  evidence_sha256=tracked,production_changed=False,execute_qualified=False,
                  normal_contract_complete=False,plant_acceptance_observed=False)
    if any(sha256_file(Path(p))!=v for p,v in tracked.items()):raise RuntimeError("evidence changed during scan")
    output.mkdir()
    with (output/"candidate_check.json").open("x") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("evidence_sha256","case_proofs")}))
    return 0 if result["mechanism_complete"] else 2

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("directory",type=Path)
    raise SystemExit(check(p.parse_args().directory))
