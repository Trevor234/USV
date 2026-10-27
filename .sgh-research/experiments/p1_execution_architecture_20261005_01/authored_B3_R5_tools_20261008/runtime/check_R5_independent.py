"""Independent full typed bag, closed worker, raw fixture and owned lifecycle gates.

Regulator Sink loss never grants a missing worker, bag or process fact. The normal
checker remains unchanged and its real failure is preserved separately.
"""
from pathlib import Path
from collections import Counter, defaultdict
import argparse, hashlib, json
import check_p1_execution as base
from check_p1_C0_comparison import load_source

OUTCOMES={'pending_replaced','pending_expired_before_native','terminal_pending_discarded','pending_discarded','job_rejected'}
WORKER_TYPES=OUTCOMES|{'worker_recording_ready','job_received','candidate','candidate_publish_result','worker_summary'}
ROLES={'worker','regulator','fixture','recorder'}
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def events(rows,t):return [x for x in rows if x.get('type')==t]
def grouped(rows,key):
    result=defaultdict(list)
    for x in rows:result[key(x)].append(x)
    return result
def cp(x,source):return {'job':base.job_projection(x.get('job',{}),source),**base.projection(x,base.CANDIDATE_FIELDS,base.CANDIDATE_ALIASES if source else {})}
def counted(v):return type(v) is int and 0<=v<(1<<64)
def strict_equal(a,b):
    if type(a) is not type(b):return False
    if type(a) is dict:return set(a)==set(b) and all(strict_equal(a[k],b[k]) for k in a)
    if type(a) is list:return len(a)==len(b) and all(strict_equal(x,y) for x,y in zip(a,b))
    return a==b

def analyze(reg,worker,bag,storage,context,summary,ledger,fixture,contract,policy,consoles):
    issues=[];counts={};raw={}
    def require(ok,code,**detail):
        if not ok:issues.append({'code':code,**detail})
    require(all(type(x) is dict for x in (bag,storage,context,summary,fixture,contract,policy,consoles)),'object_inputs')
    if issues:return {'passed':False,'issues':issues,'R5_complete':False,'execute_qualified':False}
    run=policy.get('run_id');pins=policy.get('pins',{})
    require(context.get('run_id')==summary.get('run_id')==run and context.get('mode')==policy.get('mode')=='no_output','run_mode')
    require(context.get('_binding_issues')==[],'owned_binding_issues',binding=context.get('_binding_issues'))
    require(context.get('boot_id')==pins.get('boot_id') and context.get('contract_sha256')==pins.get('contract_sha256'),'boot_contract')
    require(context.get('normal_contract_complete') is False and context.get('plant_acceptance_observed') is False
            and context.get('declaration',{}).get('execute_qualified') is False and summary.get('physical_execute_release_enabled') is False,'context_no_execute_release')
    require(summary.get('failure') is None and summary.get('cleanup_complete') is True and summary.get('cleanup_failed') is False
            and summary.get('supervision_evidence_complete') is True and summary.get('graph_no_physical_publishers') is True,'summary_owned_cleanup_and_zero_endpoints')
    startup=events(reg,'startup')
    require(len(startup)==1,'startup_unique')
    if len(startup)==1:
        s=startup[0]
        require(s.get('run_id')==run and s.get('boot')==pins.get('boot_id') and s.get('mode')=='no_output'
                and s.get('clock')=='CLOCK_MONOTONIC' and s.get('contract_hash')==pins.get('contract_sha256')
                and s.get('pid')==context.get('_regulator_owned_pid') and s.get('physical_publisher_endpoints')==0,'source_owned_startup')
    # The recorder scans every message and checks metadata counts/types itself.
    actual=storage.get('actual_topic_counts',{})
    require(type(actual) is dict and bool(actual),'actual_bag_scan')
    for topic,items in bag.items():require(actual.get(topic)==len(items),'typed_actual_count',topic=topic)
    sj=events(reg,'job');sc=events(worker,'candidate');sd=events(reg,'decision')
    bj=[x['message'] for x in bag.get('/p1/solve_job',[])];bc=[x['message'] for x in bag.get('/p1/solve_candidate',[])];bd=[x['message'] for x in bag.get('/p1/execution_decision',[])]
    fields=base.DECISION_V2_FIELDS
    def equal(label,left,right):
        try:lc=Counter(map(canonical,left));rc=Counter(map(canonical,right))
        except (ValueError,TypeError):
            require(False,'source_bag_invalid_numeric_payload',stream=label);return
        missing=lc-rc;extra=rc-lc
        counts[label]={'source':len(left),'bag':len(right),'missing':sum(missing.values()),'extra':sum(extra.values())}
        require(not missing and not extra,'source_bag_full_payload_multiset',stream=label,counts=counts[label])
    equal('job',[base.job_projection(x.get('job',{}),True) for x in sj],[base.job_projection(x) for x in bj])
    equal('candidate',[cp(x,True) for x in sc],[cp(x,False) for x in bc])
    equal('decision',[base.projection(x,fields,base.DECISION_ALIASES) for x in sd],[base.projection(x,fields,{}) for x in bd])
    for stream,items,fs,aliases in (('job',sj,base.JOB_FIELDS,base.JOB_ALIASES),('candidate',sc,base.CANDIDATE_FIELDS,base.CANDIDATE_ALIASES),('decision',sd,fields,base.DECISION_ALIASES)):
        for x in items:require(len(base.projection(x.get('job',{}) if stream=='job' else x,fs,aliases))==len(fs),'source_full_fields',stream=stream)
    for stream,items,fs in (('job',bj,base.JOB_FIELDS),('candidate',bc,base.CANDIDATE_FIELDS),('decision',bd,fields)):
        for x in items:require(set(fs)<=set(x),'bag_full_fields',stream=stream)
    for d in bd:require(d.get('run_id')==run and d.get('boot_id')==pins.get('boot_id') and d.get('contract_hash')==pins.get('contract_sha256')
                        and d.get('mode')=='no_output' and d.get('plant_acceptance_observed') is False and d.get('normal_contract_complete') is False,'surviving_decision_identity')
    ws=events(worker,'worker_summary')
    require(len(ws)==1 and bool(worker) and worker[-1] is ws[0],'closed_worker_terminal')
    if len(ws)==1:
        s=ws[0]
        require(counted(s.get('generated_candidates')) and counted(s.get('published_candidates'))
                and s['generated_candidates']==s['published_candidates']==len(sc) and s.get('fatal') is False
                and s.get('terminal_numerical_failure') is False and s.get('normal_source_complete') is True,'closed_worker_counts')
    require(not any(x.get('type') not in WORKER_TYPES for x in worker),'unknown_worker_event')
    ready=events(worker,'worker_recording_ready')
    require(len(ready)==1,'worker_recording_ready_unique')
    # No normal regulator registration/publication line is synthesized here.
    jobs=grouped(bj,lambda x:x.get('job_id'));receipts=grouped(events(worker,'job_received'),lambda x:x.get('job',{}).get('job_id'))
    candidates=grouped(sc,lambda x:x.get('job',{}).get('job_id'));pubs=grouped(events(worker,'candidate_publish_result'),lambda x:x.get('job_id'))
    outcomes=grouped([x for x in worker if x.get('type') in OUTCOMES],lambda x:x.get('job_id'))
    instance=context.get('_worker_verified_instance')
    require(type(instance) is str and bool(instance) and context.get('_worker_owned_pid') is not None,'worker_owned_capability')
    require(len(jobs)>=2 and len(sc)>=2 and len(bd)>=2,'nonempty_native_and_decision_evidence')
    for label,g in (('receipt',receipts),('candidate',candidates),('publish',pubs),('outcome',outcomes)):
        require(set(g)<=set(jobs),'worker_unknown_job',stream=label)
    for jid,items in jobs.items():
        require(type(jid) is int and jid>0 and len(items)==1,'job_unique_identity')
        j=items[0]
        require(j.get('schema_version')=='p1-solve-job-v1' and j.get('run_id')==run and j.get('boot_id')==pins.get('boot_id')
                and j.get('contract_hash')==pins.get('contract_sha256') and j.get('worker_instance')==instance
                and j.get('nominal_hash')==contract.get('nominal_hash'),'job_identity')
        require(base.vector(j.get('frozen_state'),6) and base.vector(j.get('target_state'),6) and base.vector(j.get('reference'),126)
                and type(j.get('horizon_steps')) is int and j['horizon_steps']==20 and type(j.get('prediction_dt')) is float and j['prediction_dt']==.2,'native_job_shape')
        times=[j.get(k) for k in ('tick_origin_steady_ns','freeze_steady_ns','deadline_steady_ns','target_steady_ns')]
        require(all(counted(x) for x in times) and times==sorted(times) and times[2]==times[0]+150000000 and times[3]==times[0]+200000000,'native_job_absolute_time')
        rr=receipts.get(jid,[]);cc=candidates.get(jid,[]);oo=outcomes.get(jid,[]);pp=pubs.get(jid,[])
        reject=[x for x in oo if x.get('type')=='job_rejected']
        require((len(rr)==1 and strict_equal(base.job_projection(rr[0].get('job',{}),True),base.job_projection(j)) and rr[0].get('worker_instance')==instance)
                or (not rr and len(reject)==1),'worker_receipt_full_job_echo',job_id=jid)
        if len(rr)==1:
            receipt=rr[0];ts=[j.get('freeze_steady_ns'),receipt.get('receive_ns'),receipt.get('commit_ns')]
            require(all(counted(x) and x>0 for x in ts) and ts==sorted(ts),'worker_receipt_chronology',job_id=jid)
        require(len(cc)+len(oo)==1,'closed_worker_outcome_unique',job_id=jid)
        for o in oo:
            require(o.get('type')!='pending_replaced' or o.get('replacement_job_id') in jobs,'replacement_target_exists')
        if cc:
            c=cc[0]
            require(strict_equal(base.job_projection(c.get('job',{}),True),base.job_projection(j)) and c.get('worker_instance')==instance,'candidate_job_echo',job_id=jid)
            require(c.get('backend')=='acados' and c.get('solver_invoked') is True and c.get('success') is True and c.get('prediction_available') is True,'native_success',job_id=jid)
            require(base.vector(c.get('first_control'),2) and base.vector(c.get('X'),126) and base.vector(c.get('U'),40)
                    and base.finite(c.get('backend_ms')) and c['backend_ms']>=0,'native_candidate_shape',job_id=jid)
            ts=[j.get('freeze_steady_ns'),c.get('receive_ns'),c.get('solve_start_ns'),c.get('solve_end_ns')]
            require(all(counted(x) for x in ts) and ts==sorted(ts),'native_candidate_time',job_id=jid)
            require(len(rr)==1 and c.get('receive_ns')==rr[0].get('receive_ns') and counted(rr[0].get('commit_ns'))
                    and counted(c.get('solve_start_ns')) and rr[0]['commit_ns']<=c['solve_start_ns'],'candidate_receipt_time_echo',job_id=jid)
            if base.vector(c.get('U'),40) and base.vector(c.get('first_control'),2):require(all(abs(c['first_control'][i]-c['U'][i])<=1e-8 for i in range(2)),'native_first_control')
            if base.vector(c.get('X'),126) and base.vector(j.get('target_state'),6):require(all(abs(c['X'][i]-j['target_state'][i])<=1e-7 for i in range(6)),'native_initial_prediction')
            require(len(pp)==1,'candidate_publish_unique',job_id=jid)
            if len(pp)==1:
                p=pp[0];ts=[c.get('solve_end_ns'),c.get('publish_start_ns'),p.get('publish_start_ns'),p.get('publish_end_ns')]
                require(p.get('success') is True and all(p.get(k)==c.get(k) for k in ('worker_instance','solve_start_ns','solve_end_ns'))
                        and all(counted(x) and x>0 for x in ts) and ts==sorted(ts),'candidate_publish_complete',job_id=jid)
        else:require(not pp,'publish_without_candidate')
    require(fixture.get('type')=='fixture_summary' and fixture.get('schema')=='p1-synthetic-fixture-v1'
            and fixture.get('contract_sha256')==pins.get('contract_sha256') and fixture.get('boot_id')==pins.get('boot_id')
            and fixture.get('pid')==context.get('_fixture_owned_pid') and fixture.get('error') in (None,'')
            and fixture.get('physical_endpoints')==0 and fixture.get('actual_plant') is False
            and fixture.get('publisher_side_counts_only') is True,'raw_fixture_identity')
    topics={**contract.get('input_topics',{}),'clock':'/clock'}
    require(set(topics)=={'clock','odom','imu','path','profile'} and len(set(topics.values()))==5,'raw_topic_scope')
    for name,topic in topics.items():
        p=fixture.get('counts',{}).get(name);r=actual.get(topic);raw[name]={'published':p,'recorded':r,'topic':topic}
        require(counted(p) and p>0 and counted(r) and p==r,'raw_fixture_actual_bag_count',input=name)
    # Check all four minted groups; base binding alone omits fixture cleanup.
    spawns=grouped(events(ledger,'spawn'),lambda x:x.get('name'));clean=grouped(events(ledger,'cleanup_result'),lambda x:x.get('name'))
    require(set(spawns)==ROLES and set(clean)==ROLES,'exact_owned_roles')
    require(all(x.get('name') in ROLES for x in events(ledger,'signal')+events(ledger,'owned_descendant_observed')),'unknown_role_signal_or_descendant')
    terminal=events(ledger,'supervisor_summary')
    require(len(terminal)==1 and bool(ledger) and ledger[-1] is terminal[0] and terminal[0].get('cleanup_failed') is False
            and terminal[0].get('unverified_children')==[],'owned_terminal_complete')
    for x in ledger:require(x.get('boot_id')==pins.get('boot_id'),'ledger_boot')
    for name in ROLES:
        ss=spawns.get(name,[]);cs=clean.get(name,[]);require(len(ss)==len(cs)==1,'owned_role_unique',role=name)
        if len(ss)!=1 or len(cs)!=1:continue
        s=ss[0];c=cs[0];ident=s.get('identity',{});expected=policy.get('recovery_expected_roles',{}).get(name,{})
        require(s.get('executable_verified') is True and ident.get('pid')==ident.get('pgid')==ident.get('sid') and counted(ident.get('pid')) and ident['pid']>0
                and counted(ident.get('start_ticks')) and ident['start_ticks']>0 and ident.get('exe')==expected.get('exe')
                and ident.get('exe_sha256')==s.get('expected_sha256')==expected.get('sha256'),'owned_spawn_identity',role=name)
        require(c.get('cleanup_complete') is True and c.get('remaining_members')==[] and type(c.get('returncode')) is int
                and c['returncode']==(2 if name=='regulator' else 0),'owned_actual_exit',role=name)
        report=summary.get('cleanup',{}).get(name,{})
        require(all(strict_equal(report.get(k),v) for k,v in c.items() if k not in ('type','monotonic_ns','boot_id')),'summary_ledger_cleanup_pair',role=name)
        for sig in [x for x in events(ledger,'signal') if x.get('name')==name]:
            require(type(sig.get('members')) is list and bool(sig['members']) and all(m.get('pgid')==ident['pid'] and m.get('sid')==ident['pid']
                    and counted(m.get('start_ticks')) and m['start_ticks']>0 for m in sig['members']),'signal_owned_members',role=name)
            for m in sig.get('members',[]):
                if m.get('pid')==ident.get('pid'):require(m.get('start_ticks')==ident.get('start_ticks'),'signal_leader_not_reused')
    for name,true_token,false_token in (('worker','WORKER_CLOSE_FLUSH_SUCCESS=true','WORKER_CLOSE_FLUSH_SUCCESS=false'),
                                         ('regulator','REGULATOR_CLOSE_FLUSH_SUCCESS=false','REGULATOR_CLOSE_FLUSH_SUCCESS=true')):
        lines=consoles.get(name,'').splitlines();require(lines.count(true_token)==1 and false_token not in lines,'source_console_terminal',role=name)
    require(consoles.get('regulator','').splitlines().count('DIAGNOSTIC_WITNESS_COMPLETE=true')==1
            and 'DIAGNOSTIC_WITNESS_COMPLETE=false' not in consoles.get('regulator',''),'witness_console_terminal')
    return {'schema':'p1-R5-independent-evidence-v1','run_id':run,'passed':not issues,'issues':issues,
            'counts':counts,'raw_fixture_comparison':raw,'worker_terminal':ws[0] if len(ws)==1 else None,
            'scope':'full_native_worker_and_surviving_regulator_source_to_actual_typed_bag_raw_fixture_owned_cleanup',
            'regulator_loss_reconstructed':False,'normal_contract_complete':False,'R5_complete':False,
            'M0b_formally_complete':False,'M4_complete':False,'execute_qualified':False}

def combine(*,policy,summary,postrun,mechanism,independent,base_report,delivery_report,returncodes,assets_unchanged,inputs_unchanged,host_clean,outer_clean):
    issues=[]
    def require(ok,code):
        if not ok:issues.append(code)
    run=policy.get('run_id')
    for n,r in (('summary',summary),('postrun',postrun),('mechanism',mechanism),('independent',independent),('base',base_report),('delivery',delivery_report)):
        require(r.get('run_id')==run,'run_id:'+n)
    require(policy.get('status')=='frozen-before-run' and policy.get('mode')=='no_output','predeclared_policy_frozen')
    require(summary.get('failure') is None and summary.get('cleanup_complete') is True and summary.get('cleanup_failed') is False
            and summary.get('supervision_evidence_complete') is True and summary.get('graph_no_physical_publishers') is True,'runner_owned_and_zero_physical')
    require(postrun.get('pressure_collection_complete') is True,'finite_pressure_collection')
    require(mechanism.get('mechanism_passed') is True and mechanism.get('expected_log_overflow_mechanism_passed') is True and mechanism.get('issues')==[],'independent_mechanism')
    require(independent.get('passed') is True and independent.get('issues')==[] and independent.get('raw_inputs_unchanged') is True,'independent_worker_bag_fixture_owned')
    require(base_report.get('passed') is False and delivery_report.get('passed') is False,'original_normal_failures_preserved')
    normal=postrun.get('normal_source_check',{});delivery=postrun.get('strict_application_delivery',{})
    require(type(normal.get('checker_returncode')) is int and normal['checker_returncode']==2 and normal.get('passed') is False
            and type(delivery.get('checker_returncode')) is int and delivery['checker_returncode']==2 and delivery.get('passed') is False,'actual_normal_checker_failures')
    require(set(returncodes)=={'runner','base','delivery','mechanism','independent'} and all(type(x) is int for x in returncodes.values())
            and returncodes=={'runner':0,'base':2,'delivery':2,'mechanism':0,'independent':0},'actual_returncodes')
    require(assets_unchanged is True and inputs_unchanged is True,'unmodified_assets_and_inputs')
    require(host_clean is True and outer_clean is True,'postrun_host_and_outer_owned_cleanup')
    for n,r in (('summary',summary),('postrun',postrun),('mechanism',mechanism),('independent',independent)):
        require(r.get('execute_qualified') is False and r.get('normal_contract_complete') is False,'qualification_scope:'+n)
    return {'schema':'p1-R5-combined-gates-v1','run_id':run,'passed':not issues,'R5_complete':not issues,'issues':issues,
            'scope':'single_finite_no_output_sink_pressure_all_independent_gates',
            'expected_log_overflow_mechanism_passed':mechanism.get('expected_log_overflow_mechanism_passed') is True,
            'independent_worker_raw_bag_owned_passed':independent.get('passed') is True,
            'original_normal_failures_preserved':base_report.get('passed') is False and delivery_report.get('passed') is False,
            'M0b_formally_complete':False,'M4_complete':False,'F6_complete':False,'P1_complete':False,
            'normal_contract_complete':False,'plant_acceptance_observed':False,'execute_qualified':False,'physical_execute_release_enabled':False}

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('experiment',type=Path);p.add_argument('--policy',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    ex=a.experiment.resolve();before={};policy={};result=None
    try:
        from check_p1_witness import load_json
        policy,_=load_json(a.policy);raw,_=load_json(ex/'run_context.json');contract_path=Path(raw['contract_file'])
        paths=[a.policy,contract_path,*[ex/x for x in ('run_context.json','runner_summary.json','owned_process_ledger.jsonl','regulator_source.jsonl','worker_source.jsonl','fixture_source.jsonl','regulator.console.log','worker.console.log','raw_bag/metadata.yaml')],*sorted((ex/'raw_bag').glob('*.mcap'))]
        if not list((ex/'raw_bag').glob('*.mcap')):raise ValueError('actual MCAP storage missing')
        before={str(x):base.sha(x) for x in paths}
        reg,_=load_source(ex/'regulator_source.jsonl');worker,_=load_source(ex/'worker_source.jsonl');ledger,_=load_source(ex/'owned_process_ledger.jsonl');fixtures,_=load_source(ex/'fixture_source.jsonl')
        if len(fixtures)!=1:raise ValueError('fixture requires exactly one terminal summary')
        context,extra=base.runtime_context(ex,raw)
        for x in extra:before.setdefault(str(x),base.sha(x))
        bag,storage=base.read_bag(ex/'raw_bag')
        summary,_=load_json(ex/'runner_summary.json');contract,_=load_json(contract_path)
        result=analyze(reg,worker,bag,storage,context,summary,ledger,fixtures[0],contract,policy,{n:(ex/(n+'.console.log')).read_text() for n in ('regulator','worker')})
        result['storage']=storage
    except BaseException as error:result={'schema':'p1-R5-independent-evidence-v1','run_id':policy.get('run_id'),'passed':False,'issues':[{'code':'reader_or_analysis_exception','error':repr(error)}],'R5_complete':False,'execute_qualified':False}
    try:after={x:base.sha(Path(x)) for x in before}
    except BaseException as error:
        after=None;result['passed']=False;result['issues'].append({'code':'postread_hash_exception','error':repr(error)})
    result['input_sha256_before']=before;result['input_sha256_after']=after;result['raw_inputs_unchanged']=bool(before) and before==after
    if before!=after:result['passed']=False;result['issues'].append({'code':'input_changed'})
    result['checker_sha256']=base.sha(Path(__file__))
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'passed':result['passed'],'issues':result['issues'],'counts':result.get('counts')}));return 0 if result['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
