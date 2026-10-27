import copy,unittest,tempfile,json,contextlib,io
from pathlib import Path
from unittest.mock import patch
import check_R5_independent as checker
import check_p1_execution as base

def fixture():
    h='a'*64;boot='boot';run='run';inst='owned'
    policy={'run_id':run,'mode':'no_output','pins':{'boot_id':boot,'contract_sha256':h},'recovery_expected_roles':{}}
    context={'run_id':run,'mode':'no_output','boot_id':boot,'contract_sha256':h,'_binding_issues':[],
        'normal_contract_complete':False,'plant_acceptance_observed':False,'declaration':{'execute_qualified':False},
        '_worker_verified_instance':inst,'_worker_owned_pid':11,'_regulator_owned_pid':12,'_fixture_owned_pid':13}
    summary={'run_id':run,'failure':None,'cleanup_complete':True,'cleanup_failed':False,'supervision_evidence_complete':True,
             'graph_no_physical_publishers':True,'physical_execute_release_enabled':False,'cleanup':{}}
    contract={'nominal_hash':h,'input_topics':{'odom':'/odom','imu':'/imu','path':'/path','profile':'/profile'}}
    reg=[{'type':'startup','run_id':run,'boot':boot,'mode':'no_output','clock':'CLOCK_MONOTONIC','contract_hash':h,'pid':12,'physical_publisher_endpoints':0}]
    worker=[{'type':'worker_recording_ready'}];bag={x:[] for x in base.TOPICS}
    ledger=[]
    for n,pid in (('worker',11),('regulator',12),('fixture',13),('recorder',14)):
        expected={'exe':'/bin/'+n,'sha256':h};policy['recovery_expected_roles'][n]=expected
        ident={'pid':pid,'pgid':pid,'sid':pid,'start_ticks':50,'exe':expected['exe'],'exe_sha256':h}
        ledger.append({'type':'spawn','name':n,'boot_id':boot,'identity':ident,'expected_sha256':h,'executable_verified':True})
        clean={'name':n,'cleanup_complete':True,'returncode':2 if n=='regulator' else 0,'remaining_members':[]}
        summary['cleanup'][n]=clean;ledger.append({'type':'cleanup_result','boot_id':boot,**clean})
    ledger.append({'type':'supervisor_summary','boot_id':boot,'cleanup_failed':False,'unverified_children':[]})
    for jid in (1,2):
        j={k:0 for k in base.JOB_FIELDS}
        j.update(schema_version='p1-solve-job-v1',run_id=run,boot_id=boot,contract_hash=h,nominal_hash=h,worker_instance=inst,job_id=jid,
                 target_tick=jid+1,horizon_steps=20,prediction_dt=.2,frozen_state=[0.]*6,target_state=[0.]*6,reference=[0.]*126,
                 tick_origin_steady_ns=1000000000*jid,freeze_steady_ns=1000000000*jid+100,deadline_steady_ns=1000000000*jid+150000000,target_steady_ns=1000000000*jid+200000000)
        sourcej={base.JOB_ALIASES.get(k,k):v for k,v in j.items()};reg.append({'type':'job','job':sourcej})
        worker.append({'type':'job_received','job':sourcej,'worker_instance':inst,'receive_ns':j['freeze_steady_ns']+1,'commit_ns':j['freeze_steady_ns']+1})
        c={'job':j,'worker_instance':inst,'worker_receive_ns':j['freeze_steady_ns']+1,'solve_start_ns':j['freeze_steady_ns']+2,
           'solve_end_ns':j['freeze_steady_ns']+3,'solver_invoked':True,'success':True,'prediction_available':True,'reason':'native_result',
           'backend':'acados','backend_ms':.1,'first_control':[0.,0.],'x_prediction':[0.]*126,'u_prediction':[0.]*40}
        sourcec={base.CANDIDATE_ALIASES.get(k,k):v for k,v in c.items()};sourcec['job']=sourcej;sourcec['publish_start_ns']=c['solve_end_ns']+1
        worker.append({'type':'candidate',**sourcec})
        worker.append({'type':'candidate_publish_result','job_id':jid,'worker_instance':inst,'solve_start_ns':c['solve_start_ns'],'solve_end_ns':c['solve_end_ns'],
                       'publish_start_ns':c['solve_end_ns']+1,'publish_end_ns':c['solve_end_ns']+2,'success':True})
        d={k:0 for k in base.DECISION_V2_FIELDS};d.update(run_id=run,boot_id=boot,contract_hash=h,mode='no_output',sequence=jid,plant_acceptance_observed=False,normal_contract_complete=False)
        reg.append({'type':'decision',**{base.DECISION_ALIASES.get(k,k):v for k,v in d.items()}})
        for topic,msg in (('/p1/solve_job',j),('/p1/solve_candidate',c),('/p1/execution_decision',d)):bag[topic].append({'message':msg,'bag_receive_ns':3})
    worker.append({'type':'worker_summary','generated_candidates':2,'published_candidates':2,'fatal':False,'terminal_numerical_failure':False,'normal_source_complete':True})
    counts={t:len(v) for t,v in bag.items()};counts.update({'/clock':10,'/odom':10,'/imu':10,'/path':2,'/profile':2})
    storage={'actual_topic_counts':counts}
    fx={'type':'fixture_summary','schema':'p1-synthetic-fixture-v1','contract_sha256':h,'boot_id':boot,'pid':13,'error':None,'physical_endpoints':0,
        'actual_plant':False,'publisher_side_counts_only':True,'counts':{'clock':10,'odom':10,'imu':10,'path':2,'profile':2}}
    consoles={'worker':'WORKER_CLOSE_FLUSH_SUCCESS=true\n','regulator':'REGULATOR_CLOSE_FLUSH_SUCCESS=false\nDIAGNOSTIC_WITNESS_COMPLETE=true\n'}
    return dict(reg=reg,worker=worker,bag=bag,storage=storage,context=context,summary=summary,ledger=ledger,fixture=fx,contract=contract,policy=policy,consoles=consoles)

class IndependentTests(unittest.TestCase):
    def setUp(self):self.f=fixture()
    def check(self):return checker.analyze(**self.f)
    def bad(self,code):
        r=self.check();self.assertFalse(r['passed']);self.assertIn(code,[x['code'] for x in r['issues']])
    def test_full_finite_pressure_evidence(self):
        r=self.check();self.assertTrue(r['passed'],r['issues']);self.assertFalse(r['R5_complete']);self.assertFalse(r['execute_qualified'])
    def test_bag_only_candidate_is_failure(self):self.f['worker'].pop(2);self.bad('source_bag_full_payload_multiset')
    def test_same_count_modified_payload(self):self.f['bag']['/p1/solve_candidate'][0]['message']=copy.deepcopy(self.f['bag']['/p1/solve_candidate'][0]['message']);self.f['bag']['/p1/solve_candidate'][0]['message']['first_control']=[1.,0.];self.bad('source_bag_full_payload_multiset')
    def test_duplicate_receipt(self):self.f['worker'].insert(2,copy.deepcopy(self.f['worker'][1]));self.bad('worker_receipt_full_job_echo')
    def test_missing_native_outcome(self):self.f['worker']=[x for x in self.f['worker'] if x.get('type')!='candidate'];self.bad('closed_worker_outcome_unique')
    def test_native_fatal_not_excused_by_sink(self):self.f['worker'][-1]['fatal']=True;self.bad('closed_worker_counts')
    def test_bool_worker_counter(self):self.f['worker'][-1]['generated_candidates']=True;self.bad('closed_worker_counts')
    def test_nonfinite_prediction(self):self.f['worker'][2]['X']=[float('nan')]*126;self.bad('native_candidate_shape')
    def test_wrong_worker_instance(self):self.f['worker'][1]['worker_instance']='foreign';self.bad('worker_receipt_full_job_echo')
    def test_candidate_publish_failure(self):self.f['worker'][3]['success']=False;self.bad('candidate_publish_complete')
    def test_raw_recorder_count_loss(self):self.f['storage']['actual_topic_counts']['/imu']-=1;self.bad('raw_fixture_actual_bag_count')
    def test_fixture_wrong_owned_pid(self):self.f['fixture']['pid']=99;self.bad('raw_fixture_identity')
    def test_missing_fixture_cleanup(self):self.f['ledger']=[x for x in self.f['ledger'] if not(x.get('type')=='cleanup_result' and x.get('name')=='fixture')];self.bad('exact_owned_roles')
    def test_regulator_rc_zero_not_expected_pressure(self):self.f['ledger'][3]['returncode']=0;self.bad('owned_actual_exit')
    def test_remaining_zombie_not_clean(self):self.f['ledger'][1]['remaining_members']=[{'state':'Z'}];self.bad('owned_actual_exit')
    def test_spawn_identity_changed(self):self.f['ledger'][0]['identity']['start_ticks']=0;self.bad('owned_spawn_identity')
    def test_binding_unknown(self):self.f['context']['_binding_issues']=[{'code':'unknown'}];self.bad('owned_binding_issues')
    def test_physical_publishers_present(self):self.f['summary']['graph_no_physical_publishers']=False;self.bad('summary_owned_cleanup_and_zero_endpoints')
    def test_worker_flush_missing(self):self.f['consoles']['worker']='';self.bad('source_console_terminal')
    def test_source_false_preserved(self):self.f['consoles']['regulator']='REGULATOR_CLOSE_FLUSH_SUCCESS=true\nDIAGNOSTIC_WITNESS_COMPLETE=true\n';self.bad('source_console_terminal')
    def test_unclosed_ledger(self):self.f['ledger'].append({'type':'event','boot_id':'boot'});self.bad('owned_terminal_complete')
    def test_publication_before_native_end(self):self.f['worker'][3]['publish_start_ns']=1;self.f['worker'][3]['publish_end_ns']=2;self.bad('candidate_publish_complete')
    def test_negative_receipt_time(self):self.f['worker'][1]['receive_ns']=-1;self.f['worker'][1]['commit_ns']=-1;self.bad('worker_receipt_chronology')
    def test_unknown_signal_role(self):self.f['ledger'].insert(-1,{'type':'signal','name':'foreign','boot_id':'boot','members':[{'pid':99,'pgid':99,'sid':99,'start_ticks':1}]});self.bad('unknown_role_signal_or_descendant')
    def test_float_horizon(self):self.f['bag']['/p1/solve_job'][0]['message']['horizon_steps']=20.;self.f['reg'][1]['job']['N']=20.;self.bad('native_job_shape')
    def test_int_float_echo_not_equal(self):self.f['worker'][1]['job']=copy.deepcopy(self.f['worker'][1]['job']);self.f['worker'][1]['job']['N']=20.;self.bad('worker_receipt_full_job_echo')
    def test_receipt_candidate_time_mismatch(self):self.f['worker'][1]['receive_ns']-=1;self.bad('candidate_receipt_time_echo')
class CliTests(unittest.TestCase):
    def test_missing_input_still_saves_false_report(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);out=d/'report.json'
            with contextlib.redirect_stdout(io.StringIO()):rc=checker.main([str(d),'--policy',str(d/'missing.json'),'--output',str(out)])
            r=json.loads(out.read_text());self.assertEqual(rc,2);self.assertFalse(r['passed']);self.assertFalse(r['raw_inputs_unchanged'])
    def test_actual_cli_reader_api_and_closed_files(self):
        f=fixture()
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);bag=d/'raw_bag';bag.mkdir();(bag/'dummy.mcap').write_bytes(b'dummy');(bag/'metadata.yaml').write_text('{}')
            contract=d/'contract.json';policy=d/'policy.json';raw={**f['context'],'contract_file':str(contract)}
            for p,obj in ((contract,f['contract']),(policy,f['policy']),(d/'run_context.json',raw),(d/'runner_summary.json',f['summary'])):p.write_text(json.dumps(obj))
            for name,rows in (('regulator_source.jsonl',f['reg']),('worker_source.jsonl',f['worker']),('owned_process_ledger.jsonl',f['ledger']),('fixture_source.jsonl',[f['fixture']])):(d/name).write_text(''.join(json.dumps(x)+'\n' for x in rows))
            for name,txt in f['consoles'].items():(d/(name+'.console.log')).write_text(txt)
            out=d/'report.json'
            with patch.object(base,'runtime_context',return_value=(f['context'],[])),patch.object(base,'read_bag',return_value=(f['bag'],f['storage'])),contextlib.redirect_stdout(io.StringIO()):
                rc=checker.main([str(d),'--policy',str(policy),'--output',str(out)])
            r=json.loads(out.read_text());self.assertEqual(rc,0,r['issues']);self.assertTrue(r['passed']);self.assertTrue(r['raw_inputs_unchanged']);self.assertEqual(r['input_sha256_before'],r['input_sha256_after'])

class CombinedTests(unittest.TestCase):
    def setUp(self):
        common={'run_id':'run','execute_qualified':False,'normal_contract_complete':False}
        self.f={'policy':{'run_id':'run','status':'frozen-before-run','mode':'no_output'},'summary':{**common,'failure':None,'cleanup_complete':True,'cleanup_failed':False,'supervision_evidence_complete':True,'graph_no_physical_publishers':True},
            'postrun':{**common,'pressure_collection_complete':True,'normal_source_check':{'checker_returncode':2,'passed':False},'strict_application_delivery':{'checker_returncode':2,'passed':False}},
            'mechanism':{**common,'mechanism_passed':True,'expected_log_overflow_mechanism_passed':True,'issues':[]},
            'independent':{**common,'passed':True,'issues':[],'raw_inputs_unchanged':True},'base_report':{**common,'passed':False},'delivery_report':{**common,'passed':False},
            'returncodes':{'runner':0,'base':2,'delivery':2,'mechanism':0,'independent':0},'assets_unchanged':True,'inputs_unchanged':True,'host_clean':True,'outer_clean':True}
    def bad(self):self.assertFalse(checker.combine(**self.f)['R5_complete'])
    def test_all_independent_gates(self):r=checker.combine(**self.f);self.assertTrue(r['R5_complete']);self.assertFalse(r['M0b_formally_complete']);self.assertFalse(r['execute_qualified'])
    def test_mechanism_only_not_total(self):self.f['independent']['passed']=False;self.bad()
    def test_expected_RC2_alone_not_pass(self):self.f['mechanism']['mechanism_passed']=False;self.bad()
    def test_draft_not_launchable(self):self.f['policy']['status']='draft-not-authorized-for-launch';self.bad()
    def test_input_changed(self):self.f['inputs_unchanged']=False;self.bad()
    def test_outer_cleanup_unknown(self):self.f['outer_clean']=None;self.bad()
    def test_normal_result_rewritten_to_pass(self):self.f['base_report']['passed']=True;self.bad()
    def test_execute_overclaim(self):self.f['summary']['execute_qualified']=True;self.bad()
    def test_bool_rc_not_valid(self):self.f['returncodes']['base']=False;self.bad()
if __name__=='__main__':unittest.main()
