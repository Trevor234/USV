"""Independent nonempty preparation pending proof; raw evidence stays immutable."""
from collections import Counter
import argparse
import json
from pathlib import Path
from owned_process_supervisor import sha256_file
from check_regulator_fault_matrix import check as base_check, scan
from check_p1_execution import JOB_ALIASES, DECISION_ALIASES, DECISION_V2_FIELDS

def pending_proof(reg, fixture, fault, jobs, decisions):
    issues=[]
    def require(ok,why):
        if not ok: issues.append(why)
    select=lambda tag:[e for e in reg if e['type']==tag]
    enters=select('diagnostic_preparation_barrier_enter')
    releases=select('diagnostic_preparation_barrier_release')
    queues=select('diagnostic_preparation_pending_enqueued')
    transitions=select('worker_unusable_transition')
    require(len(enters)==len(releases)==len(transitions)==1,'single barrier/terminal lifecycle absent')
    if not fault or len(enters)!=1 or len(releases)!=1 or len(transitions)!=1:
        return {'issues':issues+['incomplete pending premise'],'mechanism_complete':False}
    enter,release,terminal=enters[0],releases[0],transitions[0]
    at=fault['ns'];check=terminal['check_ns'];processed=terminal['processed_ns']
    require(enter['maximum_ms']==3000 and enter['physical_output'] is False,'bounded diagnostic declaration differs')
    require(enter['start_ns']<at<=check<=processed<=release['released_ns'],'actual lifecycle time order differs')
    require(release['released_ns']-enter['start_ns']<=3_100_000_000,'preparation cancellation exceeded finite barrier')
    before=[e for e in queues if e['enqueued_ns']<=check]
    require(bool(before) and all(e['pending_count']==1 for e in queues),'actual nonempty bounded queue absent')
    require(all(enter['start_ns']<=e['enqueued_ns']<release['released_ns'] for e in queues),'enqueue outside active barrier')
    require(not any(e['enqueued_ns']>check for e in queues),'preparation queue refilled after terminal observation')
    require(terminal['pending_before'] is True and terminal['pending_after'] is False,'nonempty pending invalidation absent')
    require(terminal['candidate_after'] is False and terminal['reason']=='worker_process_exited','terminal cause or candidate clearing differs')
    require(release['cancelled'] is True and release['worker_unusable'] is True and release['pending_after'] is False,'active preparation did not cancel with empty queue')
    if before:
        require(terminal['cleared_pending_target_tick']==before[-1]['target_tick'],'cleared identity is not last actual queued target')
        require(before[-1]['target_tick']>enter['target_tick'],'active and pending identities conflated')
        observed=[e for e in before if e['target_tick']==fault['observed_preparation_pending_target_tick']
                  and e['enqueued_ns']==fault['observed_preparation_pending_enqueue_ns']]
        require(len(observed)==1 and observed[0]['enqueued_ns']<at,'driver kill lacked actual nonempty source premise')
    require(fault['barrier_active_target_tick']==enter['target_tick'],'driver active preparation identity differs')
    require(fault['active_job']==0 and fault['pending_count']==0,'worker idle premise differs')
    discarded=[e for e in select('job_not_submitted') if e['target_tick']==enter['target_tick']
               and e['reason']=='worker_unusable_after_preparation_barrier' and e['processed_ns']>=processed]
    require(len(discarded)==1,'active preparation terminal discard missing')
    blocked={enter['target_tick']}|{e['target_tick'] for e in queues}
    require(not any(e['job']['target_tick'] in blocked for e in jobs),'active/pending target was submitted')
    require(not any(e['submit_commit_ns']>check for e in jobs),'new submission after terminal observation')
    require(any(d['accepted'] and d['activation_commit_ns']<enter['start_ns'] for d in decisions),'normal native accepted prefix absent')
    require(not any(d['accepted'] and d['activation_commit_ns']>=check for d in decisions),'activation after terminal observation')
    end=next((e['ns'] for e in fixture if e['type']=='post_fault_observation_end'),0)
    require(end-at>=1_200_000_000,'post-fault observation too short')
    post=[d for d in decisions if processed<=d['activation_commit_ns']<=end and d['reason']!='shutdown']
    require(len(post)>=5 and all(d['reason']=='worker_unusable' and not d['accepted'] for d in post),'post-terminal ticks absent or accepted')
    return {'issues':issues,'mechanism_complete':not issues,'barrier_active_target_tick':enter['target_tick'],
            'pending_queue_events':len(queues),'cleared_pending_target_tick':terminal['cleared_pending_target_tick'],
            'pending_before':terminal['pending_before'],'pending_after':terminal['pending_after'],
            'active_preparation_cancelled':release['cancelled'],'post_terminal_decisions':len(post),
            'detection_ms':(processed-at)/1e6,'barrier_duration_ms':(release['released_ns']-enter['start_ns'])/1e6}

def check(directory):
    output=directory/'verification_preparation_v1'
    if output.exists():raise FileExistsError('create-only verification already exists')
    base_output=directory/'verification_linkage_v2/regulator_fault_check.json'
    if base_output.exists():raise FileExistsError('base verification already exists')
    base_rc=base_check(directory)
    base=json.loads(base_output.read_text())
    tracked={str(p):sha256_file(p) for p in directory.rglob('*') if p.is_file()}
    def j(name):return json.loads((directory/name).read_text())
    def lines(name):
        b=(directory/name).read_bytes()
        if not b.endswith(b'\n'):raise ValueError('unclosed source '+name)
        return [json.loads(v) for v in b.decode().splitlines()]
    context=j('run_context.json');summary=j('runner_summary.json')
    c=json.loads(Path(context['contract_file']).read_text())
    reg=lines('regulator_source.jsonl');fixture=lines('fixture_source.jsonl')
    data=scan(directory/'raw_bag',context['topics'])
    issues=list(base['issues'])
    def require(ok,why):
        if not ok:issues.append(why)
    require(base_rc==0 and base['mechanism_complete'],'base actual linkage verification failed')
    require(context['test_prepare_block_ms']==3000 and context['mode']=='no_output','context diagnostic barrier declaration differs')
    for kind in ('clock','odom','imu','path','profile'):
        topic='/clock' if kind=='clock' else c['input_topics'][kind]
        publications=Counter(e['payload_sha256'] for e in fixture if e['type'] in ('input_publish','reference_publish') and e['kind']==kind)
        require(publications==Counter(e['payload_sha256'] for e in data[topic]),'input publication/actual full content differs '+kind)
    sj=[e for e in reg if e['type']=='job'];sd=[e for e in reg if e['type']=='decision']
    actual_jobs=[e['message'] for e in data['/p1/solve_job']]
    actual_decisions=[e['message'] for e in data['/p1/execution_decision']]
    for e,m in zip(sj,actual_jobs):require(e['job']=={JOB_ALIASES.get(k,k):v for k,v in m.items()},'full job differs')
    for e,m in zip(sd,actual_decisions):require(all(e.get(DECISION_ALIASES.get(k,k))==m[k] for k in DECISION_V2_FIELDS),'full decision differs')
    result=pending_proof(reg,fixture,summary['fault'],sj,sd)
    result['issues']=issues+result['issues']
    result.update(schema='p1-preparation-pending-check-v1',run_id=context['run_id'],
                  mechanism_complete=not result['issues'],evidence_accounting_complete=not issues,
                  actual_topic_counts=base['actual_topic_counts'],source_typed_counts=base['source_typed_counts'],
                  unknown=base['unknown'],zero_physical_endpoints=True,production_regulator_present=True,
                  contract_hash=context['contract_hash'],normal_contract_complete=False,execute_qualified=False,
                  evidence_sha256=tracked)
    if any(sha256_file(Path(p))!=v for p,v in tracked.items()):raise RuntimeError('evidence changed during scan')
    output.mkdir()
    with (output/'preparation_pending_check.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='evidence_sha256'}))
    return 0 if result['mechanism_complete'] else 2

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    raise SystemExit(check(p.parse_args().directory))
