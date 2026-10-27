"""Independent actual tick-skip / preparation-release proof, after full typed bag check."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from owned_process_supervisor import sha256_file

T=200_000_000
def proof(rows,scenario):
    issues=[]
    def need(ok,text):
        if not ok:issues.append(text)
    select=lambda tag:[r for r in rows if r['type']==tag]
    jobs=select('job');ds=select('decision');regs=select('candidate_registration')
    need(bool(jobs) and bool(ds),'empty actual job/decision premise')
    need(not select('worker_unusable_transition'),'unexpected terminal worker')
    need(not select('active_watchdog'),'unexpected active watchdog')
    need([d['sequence'] for d in ds]==list(range(1,len(ds)+1)),'nonconsecutive emitted decisions')
    need(all(d['publish_success']==[False,False] and not d['normal_contract_complete'] for d in ds),'physical output or normal overclaim')
    result={'scenario':scenario,'issues':issues}
    if scenario=='tick_skip':
        en=select('diagnostic_tick_barrier_enter');out=select('diagnostic_tick_barrier_release');sk=select('scheduler_skipped_ticks')
        need(len(en)==len(out)==len(sk)==1,'single actual tick barrier/skip lifecycle absent')
        if len(en)!=1 or len(out)!=1 or len(sk)!=1:return result
        en,out,sk=en[0],out[0],sk[0]
        need(en['maximum_ms']==610 and en['physical_output'] is False and out['cancelled'] is False,'diagnostic tick declaration or cancellation differs')
        need(en['start_ns']<=out['released_ns']<=sk['observed_ns'],'tick wait/skip chronology')
        need(610_000_000<=out['released_ns']-en['start_ns']<=830_000_000,'finite tick wait outside declared diagnostic observation bound')
        need(sk['expected_tick']==en['expected_tick']==out['expected_tick'],'expected tick identity differs')
        need(sk['due_tick']==(sk['observed_ns']-sk['origin_ns'])//T,'independent integer due tick differs')
        need(sk['skipped_ticks']==sk['due_tick']-sk['expected_tick']>=2,'actual multi-tick skip absent')
        need(sk['planned_ns']==sk['origin_ns']+sk['due_tick']*T,'absolute schedule was shifted')
        jid=sk['invalidated_candidate_job_id'];target=sk['invalidated_candidate_target_tick']
        old=[j for j in jobs if j['job']['job_id']==jid]
        ready=[r for r in regs if r['job']['job_id']==jid and r['accepted_registration'] and r['ready_commit_ns']<=en['start_ns']]
        need(jid>0 and target==en['expected_tick'] and len(old)==len(ready)==1,'actual ready stale candidate premise absent')
        need(sk['candidate_after'] is False and sk['admission_slots_after']==0,'stale admission slots not cleared')
        need(not any(d['accepted'] and d['job_id']==jid for d in ds),'skipped target candidate activated')
        before=[d for d in ds if d['start_ns']<en['start_ns']];after=[d for d in ds if d['start_ns']>=sk['observed_ns']]
        need(bool(before) and any(d['accepted'] for d in before),'normal native admitted prefix absent')
        need(bool(after) and after[0]['tick']==sk['due_tick'] and after[0]['skipped_ticks']==sk['skipped_ticks'] and not after[0]['accepted'] and after[0]['job_id']==0,'actual resumed skip decision absent')
        need(not any(en['start_ns']<=d['start_ns']<out['released_ns'] for d in ds),'decisions were emitted during tick stall')
        need(not any(sk['expected_tick']<=d['tick']<sk['due_tick'] for d in ds),'missed ticks were replayed')
        need(all(d['planned_ns']==sk['origin_ns']+d['tick']*T and d['schedule_generation']==sk['schedule_generation'] for d in ds),'absolute plan or generation changed')
        for left,right in zip(ds,ds[1:]):need(right['tick']==left['tick']+1+right['skipped_ticks'],'unexplained tick gap')
        renew=[r for r in select('capability_admission') if r['renewed'] and en['start_ns']<=r['validation_commit_ns']<=out['released_ns']]
        accepted=[d for d in after if d['accepted']]
        need(len(renew)>=2,'callbacks did not continue valid lease renewal during tick stall')
        need(len(accepted)>=3,'native successor admission did not recover')
        result.update(skipped_ticks=sk['skipped_ticks'],expected_tick=sk['expected_tick'],due_tick=sk['due_tick'],discarded_candidate_job_id=jid,discarded_candidate_target_tick=target,wait_ms=(out['released_ns']-en['start_ns'])/1e6,lease_renewals_during_wait=len(renew),resumed_native_accepted=len(accepted),resumed_decision_sequence=after[0]['sequence'] if after else None)
    elif scenario=='prepare_release':
        en=select('diagnostic_preparation_barrier_enter');out=select('diagnostic_preparation_barrier_release');q=select('diagnostic_preparation_pending_enqueued');replaced=select('prepare_pending_replaced')
        need(len(en)==len(out)==1,'single preparation barrier lifecycle absent')
        if len(en)!=1 or len(out)!=1:return result
        en,out=en[0],out[0];at=out['released_ns'];target=en['target_tick']
        need(en['maximum_ms']==2810 and en['physical_output'] is False and out['cancelled'] is False and out['worker_unusable'] is False and out['pending_after'] is True,'natural finite release premise differs')
        need(2_810_000_000<=at-en['start_ns']<=3_030_000_000,'finite preparation wait observation bound exceeded')
        need(len(q)>=3 and len(replaced)>=2 and all(e['pending_count']==1 for e in q),'bounded nonempty replace queue premise absent')
        need(all(en['start_ns']<=e['enqueued_ns']<at for e in q),'pending enqueue outside active barrier')
        need(len(replaced)==max(0,len(q)-1),'replacement event accounting differs')
        for old,new,r in zip(q,q[1:],replaced):need(r['old_target_tick']==old['target_tick'] and r['replacement_target_tick']==new['target_tick'],'replacement identity chain differs')
        dropped=select('job_not_submitted');old=[r for r in dropped if r['target_tick']==target and r['reason'] in ('tick_changed_before_submit','deadline_expired_before_submit')]
        need(len(old)==1 and old[0]['processed_ns']>=at and old[0]['processed_ns']>old[0]['deadline_ns'],'active old preparation not explicitly rejected after original deadline')
        need(not any(j['job']['target_tick']==target for j in jobs),'active old preparation submitted')
        latest=q[-1]['target_tick'] if q else None
        successors=[j for j in jobs if j['submit_commit_ns']>=at]
        need(bool(successors) and successors[0]['job']['target_tick']==latest,'latest pending item did not become next actual job')
        if successors:
            j=successors[0];need(j['job']['freeze_ns']==q[-1]['enqueued_ns'],'latest pending snapshot provenance differs')
            need(j['submit_commit_ns']<=j['job']['deadline_ns'] and j['job']['deadline_ns']==j['job']['tick_origin_ns']+150_000_000,'pending successor deadline was shifted or expired')
        superseded={e['target_tick'] for e in q[:-1]}
        need(not any(j['job']['target_tick'] in superseded for j in jobs),'superseded preparation was submitted')
        need(not select('scheduler_skipped_ticks'),'preparation wait also stalled scheduler')
        during=[d for d in ds if en['start_ns']<=d['start_ns']<at]
        need(len(during)>=10 and all(right['tick']==left['tick']+1 for left,right in zip(ds,ds[1:])),'tick did not independently continue')
        need(any(d['accepted'] and d['activation_commit_ns']<en['start_ns'] for d in ds),'normal native prefix absent')
        accepted=[d for d in ds if d['accepted'] and d['activation_commit_ns']>=at]
        need(len(accepted)>=3,'native successor admission did not recover')
        result.update(active_target_tick=target,latest_pending_target_tick=latest,pending_enqueues=len(q),pending_replacements=len(replaced),wait_ms=(at-en['start_ns'])/1e6,independent_decisions_during_wait=len(during),active_discard_reason=old[0]['reason'] if old else None,resumed_native_accepted=len(accepted),first_successor_target_tick=successors[0]['job']['target_tick'] if successors else None)
    else:need(False,'unknown scenario')
    return result

def check(directory,scenario):
    raw=[directory/n for n in ('run_context.json','runner_summary.json','owned_process_ledger.jsonl','regulator_source.jsonl','worker_source.jsonl','fixture_source.jsonl')]
    raw.extend(p for p in (directory/'raw_bag').rglob('*') if p.is_file())
    locked={str(p):sha256_file(p) for p in raw}
    context=json.loads((directory/'run_context.json').read_text());summary=json.loads((directory/'runner_summary.json').read_text())
    base=json.loads((directory/'verification_scheduler_base_v12/contract_report.json').read_text())
    b=(directory/'regulator_source.jsonl').read_bytes()
    if not b.endswith(b'\n'):raise ValueError('unclosed regulator source')
    rows=[json.loads(v) for v in b.decode().splitlines()]
    result=proof(rows,scenario);issues=result['issues']
    def need(ok,text):
        if not ok:issues.append(text)
    need(context['mode']=='no_output' and summary['graph_no_physical_publishers'] is True,'actual no-output premise absent')
    expected='diagnostic_tick_stall' if scenario=='tick_skip' else 'diagnostic_preparation_wait'
    need(context['declaration']['expected_fault']==summary['expected_fault']==expected,'fault declaration binding differs')
    parameter='test_tick_block_ms' if scenario=='tick_skip' else 'test_prepare_block_ms';value=610 if scenario=='tick_skip' else 2810
    ledger=[json.loads(v) for v in (directory/'owned_process_ledger.jsonl').read_text().splitlines()]
    spawns=[v for v in ledger if v['type']=='spawn' and v['name']=='regulator']
    need(len(spawns)==1 and [v for v in spawns[0]['argv'] if v.startswith(parameter+':=')]==[parameter+':='+str(value)],'actual owned regulator argv differs')
    need(context['declaration'][parameter]==value,'declared finite parameter differs')
    need(summary['failure'] is None and summary['cleanup_complete'] is True and summary['supervision_evidence_complete'] is True,'runner/cleanup/evidence failure')
    need(not base['issues'] and all(base[k] is True for k in ('source_bag_contract_complete','logical_admission_contract_passed','lifecycle_verified','raw_input_recording_complete','activation_source_contract_complete','fault_mechanism_evidence_complete')),'full base typed/source/input/lifecycle contract incomplete')
    need(base['normal_contract_complete'] is False and base['fault_run'] is True and base['passed'] is False,'fault run promoted to normal')
    need(len([v for v in rows if v['type']=='source_summary' and v['normal_source_complete']])==1,'source close summary incomplete')
    need(not any(sha256_file(Path(p))!=h for p,h in locked.items()),'raw evidence mutated during proof')
    result.update(schema='p1-scheduler-preparation-proof-v1',run_id=context['run_id'],selected_gate_passed=not issues,mechanism_complete=not issues,evidence_accounting_complete=not issues,normal_contract_complete=False,execute_qualified=False,zero_physical_endpoints=summary['graph_no_physical_publishers'],actual_topic_counts=base['storage']['actual_topic_counts'],streams=base['streams'],observed_metrics=base['observed_metrics'],contract_hash=context['contract_sha256'],raw_evidence_sha256=locked)
    output=directory/'verification_scheduler_v1';output.mkdir(exist_ok=False)
    with (output/'scheduler_preparation_check.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True)
    print(json.dumps({k:v for k,v in result.items() if k!='raw_evidence_sha256'}))
    return 0 if not issues else 2

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--scenario',choices=('tick_skip','prepare_release'),required=True)
    a=p.parse_args();raise SystemExit(check(a.directory,a.scenario))
