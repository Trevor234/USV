#!/usr/bin/env python3
"""Post-observation consistency check of a pinned all-rejected shadow fixture.

The old normal Witness gate and its failure remain authoritative and unchanged.
This separate offline profile only checks the declared closed observation
population. Coherent in-memory negatives are not DDS execution evidence.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE/'runtime')]
import check_c36_adapter_run as original
import check_p1_witness as normal

FLAGS = original.QUALIFICATIONS
T = 200000000
DEADLINE = 150000000
ROOT_CAPACITIES = {'tick':256,'submit':128,'activation':128,'phase':32}
EXPECTED_COUNTS = {'tick':30,'submit':21,'activation':20,'phase':3}
VERSIONS = ('task_generation','model_generation','config_generation','schedule_generation')


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def population(observer,witness,expected_header,close,request,ack,ledger):
    c = original.Checks()
    def need(ok,code,**ctx):c.need(ok,code,**ctx)
    need(type(witness) is dict and set(witness)==normal.ROOT_FIELDS,'strict_Witness_root_fields')
    need(witness.get('schema')==normal.SCHEMA and witness.get('clock_name')=='CLOCK_MONOTONIC','strict_Witness_schema_clock')
    need(all(type(witness.get(k)) is bool for k in ('enabled','closed','audit_complete','overflow','incomplete')),
         'strict_Witness_root_flags_typed')
    need(witness.get('enabled') is True and witness.get('closed') is True
        and witness.get('overflow') is False and witness.get('incomplete') is False,'raw_Witness_closed_without_overflow')
    # audit_complete is explicitly not used as a population or normal pass bit.
    need(normal._header_valid(witness.get('header')) and normal._header_valid(expected_header)
        and original.exact(witness.get('header'),expected_header),'strict_full_expected_Witness_header')
    need(type(witness.get('capacities')) is dict and witness.get('capacities')==ROOT_CAPACITIES
        and all(type(v) is int for v in witness['capacities'].values()),'fixed_Witness_capacities')
    counters = witness.get('counters',{})
    need(type(counters) is dict and set(counters)==set(ROOT_CAPACITIES)|{'ticks_without_candidate','accepted_activations'},
         'strict_counter_root_fields')
    for stream,capacity in ROOT_CAPACITIES.items():
        rows=witness.get(stream); counts=counters.get(stream,{})
        need(type(rows) is list and len(rows)==EXPECTED_COUNTS[stream] and len(rows)<=capacity,
             'registered_closed_population_count',stream=stream)
        need(type(counts) is dict and set(counts)==normal.COUNTER_FIELDS
            and all(normal._uint(v) for v in counts.values()),'strict_stream_counter_types',stream=stream)
        if not isinstance(rows,list):continue
        need(counts.get('attempts')==counts.get('reserved')==counts.get('published')==len(rows)
            and counts.get('overflow')==0 and counts.get('rejected')==0,'whole_stream_counter_conservation',stream=stream)
        need([r.get('sequence') for r in rows if isinstance(r,dict)]==list(range(1,len(rows)+1)),
             'whole_Witness_stream_sequence',stream=stream)
        for index,row in enumerate(rows):
            need(type(row) is dict and set(row)==normal.ROW_FIELDS[stream], 'strict_Witness_row_fields',stream=stream,index=index)
            if not isinstance(row,dict):continue
            need(normal._uint(row.get('sequence')) and all(normal._uint(row.get(k)) for k in
                (normal.IDENTITY_FIELDS if stream!='phase' else ('tick','job_id'))),'strict_Witness_row_uints',stream=stream,index=index)
            bools=normal.BOOL_FIELDS[stream] if stream!='phase' else normal.PHASE_STATE_FIELDS
            need(all(type(row.get(k)) is bool for k in bools),'strict_Witness_row_boolean_facts',stream=stream,index=index)
            times={'tick':('planned_ns','start_ns','end_ns'),'submit':('commit_ns',),
                   'activation':('commit_ns','ready_commit_ns'),'phase':('ns',)}[stream]
            need(all(normal._time(row.get(k)) for k in times),'strict_Witness_row_times',stream=stream,index=index)
            if stream=='tick':
                need(row.get('planned_ns',0)<=row.get('start_ns',0)<=row.get('end_ns',0)
                    and normal._uint(row.get('skipped_ticks')) and row.get('skipped_ticks')==0,
                    'tick_time_and_no_skip_scope',index=index)
                need(row.get('failed_start') is False and row.get('failed_end') is False,'tick_no_observed_source_failure',index=index)
            elif stream=='submit':
                need(row.get('failed') is False and row.get('stopping') is False,'submit_live_business_observation',index=index)
            elif stream=='activation':
                need(type(row.get('reason_code')) is int and row.get('reason_code')==3
                    and row.get('accepted') is False and row.get('failed') is False
                    and row.get('stopping') is False
                    and row.get('ready_commit_ns',0)<=row.get('commit_ns',0),
                    'registered_all_rejected_activation_scope',index=index)
            else:
                need(type(row.get('event_code')) is int and type(row.get('observation_code')) is int
                    and normal._uint(row.get('admission_slots')) and row.get('admission_slots')==0
                    and row.get('candidate_present') is False and row.get('pending_present') is False
                    and row.get('failed') is False and row.get('stopping') is True and row.get('pause_active') is False,
                    'strict_terminal_phase_facts',index=index)
    need(normal._uint(counters.get('ticks_without_candidate')) and normal._uint(counters.get('accepted_activations')),
         'strict_aux_counter_types')
    need(counters.get('accepted_activations')==0
        and counters.get('ticks_without_candidate')==sum(r['candidate_present'] is False for r in witness['tick']),
        'aux_counter_conservation')
    failure=witness.get('first_failure',{})
    need(type(failure) is dict and set(failure)=={'code','stream','ns','ticket'}
        and all(type(v) is int and v==0 for v in failure.values()),'no_raw_fixed_Witness_first_failure')
    need([r['event_code'] for r in witness['phase']]==[5,8,7]
        and [r['observation_code'] for r in witness['phase']]==[1,1,6], 'registered_Stop_Invalidate_Close_phase_population')
    # The original normal gate is re-run without changing any input or policy.
    old=normal.analyze(witness,expected_header)
    need(old.get('passed') is False and [r['code'] for r in old.get('issues',[])]==
        ['business_ready_count','complete_flag_disagrees'],'unchanged_normal_gate_exact_failure_retained')
    get=lambda kind:[r for r in observer if r.get('type')==kind]
    decisions=get('decision');jobs=get('job');registrations=get('candidate_registration')
    need(len(observer)>0 and observer[-1].get('type')=='source_summary','closed_Source_terminal_summary')
    summary=observer[-1]
    need(summary.get('generated')==summary.get('emitted')==len(observer)-1
        and summary.get('dropped')==0 and summary.get('normal_source_complete') is True,'whole_Source_population_conservation')
    dmap=c.index(decisions,lambda r:r['tick'],'Source_tick')
    jmap=c.index(jobs,lambda r:r['job']['job_id'],'Source_job')
    rmap=c.index(registrations,lambda r:r['job']['job_id'],'Source_registration')
    tmap=c.index(witness['tick'],lambda r:r['tick'],'Witness_tick')
    smap=c.index(witness['submit'],lambda r:r['job_id'],'Witness_submit')
    amap=c.index(witness['activation'],lambda r:r['job_id'],'Witness_activation')
    attempts={r['job_id']:r for r in decisions if r['job_id']}
    need(len(dmap)==30 and len(jmap)==21 and len(rmap)==21 and len(attempts)==20
        and set(dmap)==set(tmap) and set(jmap)==set(smap) and set(attempts)==set(amap),
        'registered_full_Source_Witness_identity_sets')
    need([r['sequence'] for r in decisions]==list(range(1,len(decisions)+1)),'full_Source_decision_sequence')
    need(set(jmap)==set(rmap) and set(jmap)==set(range(1,22)) and set(attempts)==set(range(1,21)),
         'closed_cancellation_population_identity')
    for tick,d in dmap.items():
        r=tmap.get(tick)
        need(r is not None,'Source_tick_has_Witness',tick=tick)
        if r is None:continue
        wanted={'sequence':d['sequence'],'job_id':d['job_id'],'tick':d['tick'],
            'target_tick':d['tick'] if d['job_id'] else 0,'clock_epoch':d['epoch'],
            'planned_ns':d['planned_ns'],'start_ns':d['start_ns'],'skipped_ticks':d['skipped_ticks'],
            'candidate_present':d['job_id']>0,**{k:d[k] for k in VERSIONS}}
        need(all(original.exact(r.get(k),v) for k,v in wanted.items()) and d['end_ns']<=r['end_ns'],
             'entire_tick_full_Source_Witness_binding',tick=tick)
        need(d.get('accepted') is False and d.get('mode')=='shadow' and d.get('diagnostic_only') is True
            and d.get('publish_success')==[False,False] and d.get('publish_start_ns')==[0,0]
            and d.get('publish_end_ns')==[0,0] and d.get('plant_acceptance_observed') is False,
            'every_decision_rejected_shadow_no_publication',tick=tick)
    for jid,e in jmap.items():
        j=e['job'];r=smap.get(jid)
        need(r is not None,'Source_job_has_Witness',job_id=jid)
        if r is None:continue
        need(all(original.exact(r.get(k),j[k]) for k in ('job_id','target_tick','clock_epoch',*VERSIONS))
            and r.get('tick')==j['target_tick']-1 and e['submit_commit_ns']==r['commit_ns']<=e['publish_start_ns'],
            'entire_submit_full_Source_Witness_binding',job_id=jid)
        need(j['tick_origin_ns']+DEADLINE==j['deadline_ns'] and j['tick_origin_ns']+T==j['target_ns']
            and j['freeze_ns']<=e['submit_commit_ns']<=j['deadline_ns']
            and e['submit_commit_ns']<close['observed_ns'],'submit_final_business_time_contract',job_id=jid)
    for jid,d in attempts.items():
        r=amap.get(jid);reg=rmap.get(jid);j=jmap.get(jid,{}).get('job')
        need(r is not None and reg is not None and j is not None,'activation_complete_referents',job_id=jid)
        if r is None or reg is None or j is None:continue
        wanted={'job_id':jid,'tick':d['tick'],'target_tick':d['tick'],'clock_epoch':d['epoch'],
            'commit_ns':d['activation_commit_ns'],'ready_commit_ns':d['ready_commit_ns'],
            'accepted':False,**{k:d[k] for k in VERSIONS}}
        need(all(original.exact(r.get(k),v) for k,v in wanted.items()),'entire_activation_full_Source_Witness_binding',job_id=jid)
        need(reg['accepted_registration'] is True and reg['ready_commit_ns']==d['ready_commit_ns']
            and j['freeze_ns']<=reg['ready_commit_ns']<=j['deadline_ns']
            and d['activation_commit_ns']>=j['target_ns'] and d['tick']==j['target_tick']
            and original.exact(d['target_state'],j['target_state'])
            and d['reason']=='anchor_mismatch', 'activation_payload_and_final_ready_binding',job_id=jid)
    phaseclose=witness['phase'][-1]
    endtimes=[summary['finished_ns'],*[r['end_ns'] for r in witness['tick']],
        *[r['commit_ns'] for r in witness['submit']],*[r['commit_ns'] for r in witness['activation']],
        *[r['ns'] for r in witness['phase']]]
    need(phaseclose['ns']>=max(endtimes),'terminal_Witness_close_after_every_producer_and_Source_flush')
    needsignal=[r for r in ledger if r.get('type')=='signal' and r.get('name')=='publisher']
    need(len(needsignal)==1 and needsignal[0].get('signal')==2,'actual_owned_Publisher_SIGINT_once')
    need(request['request_ns']==close['requested_ns'] and request['request_ns']<=close['read_completed_ns']
        <=close['observed_ns']<=ack['driver_checked_ns']<=needsignal[0]['monotonic_ns']
        and ack['publisher_still_alive'] is True,'actual_driver_request_observation_ack_SIGINT_order')
    job21=jmap.get(21,{}).get('job',{});reg21=rmap.get(21,{})
    need(reg21.get('accepted_registration') is True
        and reg21.get('ready_commit_ns',0)<close['observed_ns']<job21.get('target_ns',0)
        and close['evidence']['closing_requested'] is True and close['evidence']['job_pending'] is False
        and 21 not in amap,'actual_job21_pending_cancelled_before_target')
    need(all(d['job_id']==0 and d['accepted'] is False for d in decisions
        if d['activation_commit_ns']>=close['observed_ns']),'whole_population_no_post_close_job_or_accept')
    closed=get('adapter_closed_after_join')
    need(len(closed)==1 and closed[0].get('reason')==''
        and closed[0]['evidence']['component_lifecycle']==4
        and closed[0]['evidence']['job_pending'] is False
        and closed[0]['evidence']['active_publish_transaction'] is False
        and closed[0].get('owner_endpoints_exited')=='unknown','adapter_closed_after_producer_join')
    return c.result(counts={'tick':len(decisions),'submit':len(jobs),'activation':len(attempts),
        'phase':len(witness['phase'])},normal_witness={'qualified':False,'passed':False,
        'original_gate_reexecuted':old,'raw_audit_complete_flag':witness.get('audit_complete'),
        'raw_audit_complete_flag_used_as_new_pass':False},
        profile='post-observation registered closed all-rejected shadow population only')


def negatives(context):
    reports=[]
    for name in ('coherent_submit_completion_after_deadline','coherent_activation_ready_rebinding',
                 'coherent_last_tick_population_deletion'):
        data=deepcopy(context);o,w=data['observer'],data['witness']
        if name=='coherent_submit_completion_after_deadline':
            e=next(r for r in o if r.get('type')=='job');jid=e['job']['job_id'];point=e['job']['deadline_ns']+1
            e['submit_commit_ns']=point;e['publish_start_ns']=point+1
            next(r for r in w['submit'] if r['job_id']==jid)['commit_ns']=point
        elif name=='coherent_activation_ready_rebinding':
            d=next(r for r in o if r.get('type')=='decision' and r.get('job_id'))
            d['ready_commit_ns']+=1
            next(r for r in w['activation'] if r['job_id']==d['job_id'])['ready_commit_ns']=d['ready_commit_ns']
        else:
            d=[r for r in o if r.get('type')=='decision'][-1];o.remove(d);w['tick'].pop()
            for k in ('attempts','reserved','published'):w['counters']['tick'][k]=len(w['tick'])
            w['counters']['ticks_without_candidate']-=1
            o[-1]['generated']=o[-1]['emitted']=len(o)-1
        rehashed={'Source_canonical_sha256':canonical_sha(o),'Witness_canonical_sha256':canonical_sha(w)}
        result=population(**data)
        reports.append({'case':name,'scope':'coherent in-memory Source and Witness modifications; no raw run mutation or DDS execution',
            'copy_sha256':rehashed,'rejected':result['passed'] is False,'issues':result['issues']})
    return {'passed':all(r['rejected'] for r in reports),'cases':reports,'actual_DDS_runs':0,'raw_run_modified':False}


def analyze(run,original_report_path,scope_path):
    run=Path(run).resolve();scope=original.load(scope_path)
    if (scope.get('schema')!='p1-C3.6-post-observation-population-scope-v1'
        or scope.get('post_observation_registration') is not True):
        raise ValueError('scope registration absent/invalid')
    if scope.get('helper_sha256')!=original.sha(__file__) or scope.get('run_dir')!=str(run):
        raise ValueError('new helper or actual run scope pin differs')
    if scope.get('expected_Witness_population')!=EXPECTED_COUNTS:
        raise ValueError('registered population differs')
    for path,value in scope['input_pins'].items():
        if original.sha(path)!=value:raise ValueError('registered raw input changed: '+path)
    oldreport=original.load(original_report_path)
    if original.sha(original_report_path)!=scope['original_report_sha256']:
        raise ValueError('original failed checker report changed')
    if oldreport.get('passed') is not False or [r['code'] for r in oldreport['issues']]!=['source_fixed_witness_passed']:
        raise ValueError('original checker failure profile differs')
    if any(oldreport[k].get('passed') is not True for k in ('transport_storage','source_typed_storage','publisher_session')):
        raise ValueError('original storage/typed/Publisher population group failed')
    if (oldreport.get('checker_sha256')!=scope['original_helper_sha256']
        or original.sha(HERE/'check_c36_adapter_run.py')!=scope['original_helper_sha256']):
        raise ValueError('original helper changed')
    for path,value in oldreport['input_sha256_before'].items():
        if original.sha(path)!=value:raise ValueError('original run input pin changed: '+path)
    if oldreport['input_sha256_before']!=oldreport['input_sha256_after']:
        raise ValueError('original check input immutability failed')
    observer=original.lines(run/'observer/source.jsonl');witness=original.load(run/'observer/witness.json')
    closes=[r for r in observer if r.get('type')=='adapter_driver_close_observed']
    if len(closes)!=1:raise ValueError('observed close population differs')
    context={'observer':observer,'witness':witness,'expected_header':original.load(run/'expected_witness_header.json'),
        'close':closes[0],'request':original.load(run/'adapter_driver_close_request.json'),
        'ack':original.load(run/'adapter_driver_close_ack.json'),'ledger':original.lines(run/'owned_process_ledger.jsonl')}
    result=population(**context);negative=negatives(context)
    for path,value in scope['input_pins'].items():
        if original.sha(path)!=value:raise ValueError('registered input changed during new check: '+path)
    return {'schema':'p1-C3.6-all-rejected-observation-population-check-v1',
        'component_observation_passed':result['passed'] and negative['passed'],
        'normal_witness_qualified':False,'normal_witness_passed':False,
        'original_checker_passed':False,'original_checker_report_sha256':scope['original_report_sha256'],
        'post_observation_registration':True,'qualifications':FLAGS,'unknowns':original.UNKNOWNS,
        'run_dir':str(run),'population':result,'coherent_semantic_negatives':negative,
        'original_non_Witness_population_groups_reused':True,
        'original_full_input_pins_recomputed':True,'registration_sha256':original.sha(scope_path),
        'helper_sha256':original.sha(__file__),'component_observation_is_phase_qualification':False,
        'original_Witness_failure_preserved':True,'input_pins':scope['input_pins']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',required=True,type=Path)
    p.add_argument('--original-report',required=True,type=Path)
    p.add_argument('--scope',required=True,type=Path)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    try:report=analyze(args.run_dir,args.original_report,args.scope)
    except Exception as error:report={'schema':'p1-C3.6-all-rejected-observation-population-check-v1',
        'component_observation_passed':False,'normal_witness_qualified':False,'normal_witness_passed':False,
        'qualifications':FLAGS,'reader_error':type(error).__name__+': '+str(error)}
    if args.output:original.create_only_json(args.output,report)
    print(json.dumps(report,sort_keys=True,indent=2,allow_nan=False))
    return 0 if report['component_observation_passed'] else 2


if __name__=='__main__':raise SystemExit(main())
