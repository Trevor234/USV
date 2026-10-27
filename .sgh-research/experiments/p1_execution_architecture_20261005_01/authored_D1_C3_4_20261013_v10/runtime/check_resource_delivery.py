"""Independent application transport ledger; no inference of internal DDS drop causes."""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,hashlib,json
import check_p1_execution as base

def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False)
def events(rows,kind):return [r for r in rows if r.get('type')==kind]
def group(rows,key):
    g=defaultdict(list)
    for r in rows:g[key(r)].append(r)
    return g
def cp(m,source):
    return {'job':base.job_projection(m.get('job',{}),source),**base.projection(m,base.CANDIDATE_FIELDS,base.CANDIDATE_ALIASES if source else {})}
def registration_key(m,source):
    j=base.job_projection(m.get('job',{}),source)
    return canonical({'job':j,**{k:m.get(k) for k in ('worker_instance','solve_start_ns','solve_end_ns','first_control')}})

def analyze(reg,worker,bag,context,base_report):
    issues=[];counts=Counter();rows=[]
    def fail(code,**detail):issues.append({'code':code,**detail})
    if base_report.get('run_id')!=context.get('run_id'):fail('base_report_identity')
    for key in ('source_bag_contract_complete','logical_admission_contract_passed','lifecycle_verified','raw_input_recording_complete'):
        if base_report.get(key) is not True:fail('base_evidence_not_complete',field=key)
    if base_report.get('issues'):fail('base_issues_present')
    starts=events(reg,'startup')
    if len(starts)!=1 or any(starts[0].get(a)!=context.get(b) for a,b in [('run_id','run_id'),('boot','boot_id'),('contract_hash','contract_hash')]):fail('source_startup_identity')
    sj=events(reg,'job');sc=events(worker,'candidate');sd=events(reg,'decision')
    bj=[r['message'] for r in bag.get('/p1/solve_job',[])];bc=[r['message'] for r in bag.get('/p1/solve_candidate',[])];bd=[r['message'] for r in bag.get('/p1/execution_decision',[])]
    def equality(label,left,right):
        missing=Counter(left)-Counter(right);extra=Counter(right)-Counter(left)
        counts['recorder_'+label+'_missing']=sum(missing.values());counts['recorder_'+label+'_extra']=sum(extra.values())
        if missing or extra:fail('recorder_multiset_difference',stream=label,missing=sum(missing.values()),extra=sum(extra.values()))
    equality('job',[canonical(base.job_projection(r['job'],True)) for r in sj],[canonical(base.job_projection(r)) for r in bj])
    equality('candidate',[canonical(cp(r,True)) for r in sc],[canonical(cp(r,False)) for r in bc])
    fields=base.DECISION_V2_FIELDS if any('activation_odom_stamp_ns' in r for r in sd) else base.DECISION_FIELDS
    equality('decision',[canonical(base.projection(r,fields,base.DECISION_ALIASES)) for r in sd],[canonical(base.projection(r,fields,{})) for r in bd])
    groups={
      'submit':group(sj,lambda r:r['job']['job_id']),
      'bag_job':group(bj,lambda r:r['job_id']),
      'receipt':group(events(worker,'job_received'),lambda r:r['job']['job_id']),
      'candidate':group(sc,lambda r:r['job']['job_id']),
      'bag_candidate':group(bc,lambda r:r['job']['job_id']),
      'job_publish':group(events(reg,'job_publish_result'),lambda r:r.get('job_id')),
      'candidate_publish':group(events(worker,'candidate_publish_result'),lambda r:r.get('job_id')),
      'registration':group(events(reg,'candidate_registration'),lambda r:r['job']['job_id']),
      'outcome':group([r for r in worker if r.get('type') in ('pending_replaced','pending_expired_before_native','terminal_pending_discarded','pending_discarded','job_rejected')],lambda r:r.get('job_id')),
    }
    native_ids=set(groups['submit'])
    for name,g in groups.items():
        extras=set(g)-native_ids
        if extras:counts['unmatched_'+name]=sum(len(g[k]) for k in extras);fail('unmatched_events',stream=name,job_ids=sorted(extras,key=str))
    for jid in sorted(native_ids):
        g={k:v.get(jid,[]) for k,v in groups.items()};row={'job_id':jid,**{k+'_count':len(v) for k,v in g.items()},'unexplained_steps':[]}
        def bad(code):row['unexplained_steps'].append(code);counts[code]+=1;fail(code,job_id=jid)
        if len(g['submit'])!=1 or len(g['bag_job'])!=1:bad('ambiguous_job_identity');rows.append(row);continue
        expected=base.job_projection(g['submit'][0]['job'],True)
        if any(expected.get(k)!=context.get(k) for k in ('run_id','boot_id','contract_hash')):bad('job_run_identity')
        if len(expected)!=len(base.JOB_FIELDS):bad('job_fields_missing')
        if len(g['job_publish'])!=1:bad('job_publish_stage_unresolved')
        elif g['job_publish'][0].get('success') is not True:bad('job_publish_failed')
        else:
            e=g['job_publish'][0]
            if not all(type(e.get(k)) is int and e[k]>0 for k in ('publish_start_ns','publish_end_ns')) or e['publish_end_ns']<e['publish_start_ns']:bad('job_publish_timing_invalid')
        rejection=[r for r in g['outcome'] if r.get('type')=='job_rejected']
        if len(g['receipt'])==1:
            receipt=g['receipt'][0]
            if not base.exact(base.job_projection(receipt['job'],True),expected) or receipt.get('worker_instance')!=expected['worker_instance']:bad('job_receipt_content_mismatch')
            row['receipt_proof']='full_job_echo'
        elif not g['receipt'] and len(rejection)==1:
            row['receipt_proof']='unique_rejection_id_in_closed_native_stream'
        else:bad('job_worker_delivery_missing_or_ambiguous')
        outcomes=[r for r in g['outcome'] if r.get('type')!='job_rejected']
        if len(g['candidate'])+len(g['outcome'])!=1:bad('worker_job_outcome_unexplained_or_duplicate')
        for outcome in outcomes:
            if outcome.get('type')=='pending_replaced' and outcome.get('replacement_job_id') not in native_ids:bad('replacement_job_not_submitted')
        counts['worker_pending_superseded']+=sum(r.get('type')=='pending_replaced' for r in outcomes)
        counts['worker_pending_expired']+=sum(r.get('type')=='pending_expired_before_native' for r in outcomes)
        counts['worker_pending_discarded']+=sum(r.get('type') in ('terminal_pending_discarded','pending_discarded') for r in outcomes)
        counts['worker_job_rejected']+=len(rejection)
        if g['candidate']:
            if len(g['candidate'])!=1 or len(g['bag_candidate'])!=1:bad('ambiguous_candidate_identity')
            if len(g['candidate_publish'])!=1:bad('candidate_publish_stage_unresolved')
            else:
                e=g['candidate_publish'][0];c=g['candidate'][0]
                if e.get('success') is not True or any(e.get(k)!=c.get(k) for k in ('worker_instance','solve_start_ns','solve_end_ns')):bad('candidate_publish_failed_or_identity')
                if not all(type(e.get(k)) is int and e[k]>0 for k in ('publish_start_ns','publish_end_ns')) or e['publish_end_ns']<e['publish_start_ns']:bad('candidate_publish_timing_invalid')
            if len(g['registration'])!=1:bad('candidate_registration_missing_or_duplicate')
            else:
                c=g['candidate'][0];r=g['registration'][0]
                if registration_key(c,True)!=registration_key(r,True):bad('candidate_registration_content_mismatch')
                if type(r.get('accepted_registration')) is not bool:bad('registration_disposition_unknown')
                counts['candidate_registration_accepted' if r.get('accepted_registration') else 'candidate_registration_rejected']+=1
        elif g['candidate_publish'] or g['bag_candidate'] or g['registration']:bad('candidate_without_source_outcome')
        rows.append(row)
    counts['jobs']=len(sj);counts['candidates']=len(sc);counts['decisions']=len(sd)
    return {'schema':'p1-resource-delivery-ledger-v1','run_id':context.get('run_id'),'application_delivery_accounting_complete':not issues,'passed':not issues,'scope':'closed_native_application_edges_with_source_and_actual_recorder','dds_internal_loss_count':None,'dds_internal_loss_cause':'unknown_not_inferred_from_application_gaps','counts':dict(counts),'jobs':rows,'issues':issues,'execute_qualified':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('experiment',type=Path);p.add_argument('--base-report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    ex=a.experiment.resolve();reg=base.read_jsonl(ex/'regulator_source.jsonl');worker=base.read_jsonl(ex/'worker_source.jsonl');context=base.read_json(ex/'run_context.json');context['contract_hash']=context.get('contract_hash',context.get('contract_sha256'));report=base.read_json(a.base_report)
    bag,storage=base.read_bag(ex/'raw_bag');result=analyze(reg,worker,bag,context,report);result['storage']=storage
    result['evidence_sha256']={str(path):base.sha(path) for path in [ex/'regulator_source.jsonl',ex/'worker_source.jsonl',ex/'run_context.json',a.base_report,*sorted((ex/'raw_bag').glob('*.mcap'))]}
    a.output.mkdir(exist_ok=False)
    with (a.output/'resource_delivery_check.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'passed':result['passed'],'counts':result['counts'],'issues':result['issues']}));return 0 if result['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
