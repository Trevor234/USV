"""Decoded proof mutations; these fixtures make no claim to be real DDS traffic."""
import copy
import json
import unittest

from check_cdr_receive import (validate, digest, JOB, CANDIDATE, DECISION,
                               STAGES, BASE_KEYS)
from check_p1_execution import JOB_ALIASES, CANDIDATE_ALIASES, DECISION_ALIASES
from test_check_p1_execution import fixture as native_fixture


def sample(topic, blob, message=None):
    row = {'topic': topic, 'bytes': len(blob), 'sha256': digest(blob), 'bag_receive_ns': 123}
    if message is None:
        row.update(decoded=False, exception_type='RMWError', exception='finite decode failure')
    else:
        row.update(decoded=True, message=copy.deepcopy(message))
    return row


def data_fixture():
    oldreg, oldworker, oldbag, _contract, _context, contract_sha = native_fixture()
    reg = [copy.deepcopy(oldreg[0])]
    worker = []
    bag = []
    raw = []
    base_job = copy.deepcopy(oldbag[JOB][0]['message'])
    base_candidate = copy.deepcopy(oldbag[CANDIDATE][0]['message'])
    base_decision = copy.deepcopy(oldbag[DECISION][0]['message'])
    for i, delta in enumerate((0, 6_000_000_000, 7_000_000_000, 8_000_000_000), 1):
        job = copy.deepcopy(base_job); job.update(job_id=i, target_tick=i)
        for k in ('tick_origin_steady_ns', 'freeze_steady_ns', 'deadline_steady_ns', 'target_steady_ns'):
            job[k] += delta
        source_job = {JOB_ALIASES.get(k,k):v for k,v in job.items()}
        reg.append({'type':'job','job':source_job,'submit_commit_ns':job['freeze_steady_ns']})
        candidate = copy.deepcopy(base_candidate); candidate['job'] = job
        for k in ('worker_receive_ns','solve_start_ns','solve_end_ns'):
            candidate[k] += delta
        source_candidate = {CANDIDATE_ALIASES.get(k,k):v for k,v in candidate.items() if k != 'job'}
        worker.append(dict(source_candidate,type='candidate',job=copy.deepcopy(source_job)))
        reg.append({'type':'candidate_registration','job':copy.deepcopy(source_job),
                    'accepted_registration':True,'ready_commit_ns':1_100_000_000+delta,'reason':''})
        decision = copy.deepcopy(base_decision); decision.update(job_id=i,tick=i,sequence=i)
        for k in ('activation_commit_ns','tick_start_ns','tick_planned_ns'):
            decision[k] += delta
        reg.append(dict({DECISION_ALIASES.get(k,k):v for k,v in decision.items()},type='decision'))
        bag.extend((sample(JOB,('native-job-'+str(i)).encode(),job),
                    sample(CANDIDATE,('native-candidate-'+str(i)).encode(),candidate),
                    sample(DECISION,('native-decision-'+str(i)).encode(),decision)))
    cases = []; sends = []; facts = []
    for topic in (JOB,CANDIDATE):
        for stage in STAGES:
            i=len(cases); ident=900001+i
            job = copy.deepcopy(base_job); job.update(run_id='foreign_cdr_run',job_id=ident)
            message = job if topic == JOB else dict(copy.deepcopy(base_candidate),job=job)
            full = json.dumps(message,sort_keys=True).encode()
            blob = {'empty':b'','header3':b'\0\1\0','tail_minus1':full[:-1]}.get(stage,full)
            case = dict(case_index=i,topic=topic,stage=stage,job_id=ident,blob=f'{i:02d}_{stage}.cdr',
                        bytes=len(blob),sha256=digest(blob),valid_control=stage in ('before','after'),
                        offset_ns=1_000_000_000+i*400_000_000)
            cases.append(case)
            target='p1_solver_worker' if topic==JOB else 'p1_regulator'
            sends.append(dict(case,attempt_ns=2_000_000_000+i*400_000_000,
                              return_ns=2_000_000_100+i*400_000_000,matched_count=3,
                              subscriber_names=[target,'p1_calibration_driver','rosbag2_recorder'],api_returned=True))
            facts.append({k:case[k] for k in ('blob','bytes','sha256')})
            facts[-1]['path_within_blob_directory']=True
            decoded = stage in ('before','after') or (stage=='tail_minus1' and topic==JOB)
            bag.append(sample(topic,blob,message if decoded else None))
            if stage in ('before','tail_minus1','after'):
                if topic==JOB:
                    worker.append({'type':'job_rejected','job_id':ident,'reason':'foreign',
                                   'receive_ns':sends[-1]['return_ns']+1})
                else:
                    reg.append({'type':'candidate_registration','job':{JOB_ALIASES.get(k,k):v for k,v in job.items()},
                                'accepted_registration':False,'reason':'foreign',
                                'ready_commit_ns':sends[-1]['return_ns']+1})
    for row in bag:
        if row['topic'] not in (JOB,CANDIDATE):continue
        obs={k:row[k] for k in ('topic','bytes','sha256','decoded')}
        obs.update(sequence=len(raw)+1,receive_ns=10_000_000_000+len(raw))
        if row['decoded']:
            job=row['message'] if row['topic']==JOB else row['message']['job']
            obs.update(job_id=job['job_id'],run_id=job['run_id'])
        else:obs.update(exception_type=row['exception_type'],exception=row['exception'])
        raw.append(obs)
    reg.append({'type':'source_summary','generated':len(reg),'emitted':len(reg),
                'dropped':0,'normal_source_complete':True})
    worker.append({'type':'worker_summary','generated_candidates':4,'published_candidates':4,
                   'fatal':False,'normal_source_complete':True})
    cleanup={name:dict(name=name,cleanup_complete=True,returncode=0,remaining_members=[])
             for name in ('worker','regulator','fixture','recorder')}
    ledger=[]
    for name,result in cleanup.items():
        ledger.extend((dict(type='spawn',name=name,executable_verified=True),
                       dict(result,type='cleanup_result')))
    return dict(plan=dict(schema='p1-cdr-plan-v1',run_id='run',sample_count=10,cases=cases,
                          observer_depth=64,production_reader_depth=1,actual_plant=False,physical_endpoints=0),
                sends=sends,raw=raw,bag=bag,blob_facts=facts,reg=reg,worker=worker,ledger=ledger,
                context=dict(run_id='run',boot_id='boot',contract_sha256=contract_sha,mode='no_output',
                             declaration=dict(cdr_injection=True,test_delay_ms=0,test_native_block_ms=0,
                                              test_prepare_block_ms=0,test_tick_block_ms=0)),
                summary=dict(failure=None,cleanup_complete=True,cleanup_failed=False,
                             supervision_evidence_complete=True,graph_no_physical_publishers=True,cleanup=cleanup),
                all_sources_closed=True,consoles={n:n.upper()+'_CLOSE_FLUSH_SUCCESS=true\n' for n in ('worker','regulator')},
                native_view_contract=dict(issues=[],**{k:True for k in BASE_KEYS}))


def remove_case_observations(data,index):
    case=data['plan']['cases'][index]
    key=lambda r:(r['topic'],r['bytes'],r['sha256'])
    casekey=key(case)
    data['bag']=[r for r in data['bag'] if key(r)!=casekey]
    data['raw']=[r for r in data['raw'] if key(r)!=casekey]
    for i,row in enumerate(data['raw'],1):row['sequence']=i


class CdrReceiveProof(unittest.TestCase):
    def assert_bad(self,data):
        result=validate(data);self.assertFalse(result['selected_observation_gate_passed'],result)

    def test_observed_decode_disagreement_with_business_rejection_is_preserved(self):
        result=validate(data_fixture());self.assertEqual(result['issues'],[])
        tail=result['attempts'][8]
        self.assertFalse(tail['observer_decoded'])
        self.assertTrue(tail['production_business_rejection_observed'])
        self.assertEqual(tail['classification'],'local_decoder_failed_but_production_business_rejected')
        self.assertFalse(result['target_reader_fault_observation_complete'])
        self.assertFalse(result['normal_contract_complete'])
        self.assertFalse(result['execute_qualified'])

    def test_missing_control_business_source_fails(self):
        d=data_fixture();d['worker']=[e for e in d['worker'] if e.get('job_id')!=900001]
        self.assert_bad(d)

    def test_wrong_blob_hash_fails(self):
        d=data_fixture();d['blob_facts'][0]['sha256']='0'*64;self.assert_bad(d)

    def test_raw_bag_byte_difference_fails(self):
        d=data_fixture();d['raw'][0]['sha256']='0'*64;self.assert_bad(d)

    def test_duplicate_raw_sample_fails(self):
        d=data_fixture();d['raw'].append(copy.deepcopy(d['raw'][0]));self.assert_bad(d)

    def test_injection_id_in_native_source_fails(self):
        d=data_fixture();next(e for e in d['reg'] if e['type']=='job')['job']['job_id']=900001
        self.assert_bad(d)

    def test_physical_output_fails(self):
        d=data_fixture();next(e for e in d['reg'] if e['type']=='decision')['publish_success']=[True,False]
        self.assert_bad(d)

    def test_no_fresh_native_recovery_fails(self):
        d=data_fixture()
        for e in d['reg']:
            if e['type']=='job':e['submit_commit_ns']=1
        self.assert_bad(d)

    def test_old_prefix_not_counted_as_post_fault_recovery(self):
        d=data_fixture()
        for e in d['reg']:
            if e['type']=='decision':e['activation_commit_ns']=1
        self.assert_bad(d)

    def test_decode_error_must_be_recorded_in_both_paths(self):
        for stream in ('raw','bag'):
            d=data_fixture();next(r for r in d[stream] if not r['decoded']).pop('exception')
            self.assert_bad(d)

    def test_forged_source_completeness_fails(self):
        for key in ('generated','emitted','dropped'):
            d=data_fixture();d['reg'][-1][key]=999;self.assert_bad(d)
        d=data_fixture();d['worker'][-1]['normal_source_complete']=False;self.assert_bad(d)

    def test_console_flush_claim_requires_exact_token(self):
        d=data_fixture();d['consoles']['worker']='';self.assert_bad(d)

    def test_owned_cleanup_or_graph_failure_fails(self):
        d=data_fixture();d['summary']['cleanup']['worker']['remaining_members']=[{'pid':42}];self.assert_bad(d)
        d=data_fixture();d['summary']['graph_no_physical_publishers']=False;self.assert_bad(d)

    def test_api_rejection_accounted_without_claiming_receiver_coverage(self):
        d=data_fixture();remove_case_observations(d,1)
        d['sends'][1].update(api_returned=False,exception_type='RuntimeError',exception='publisher rejected empty')
        result=validate(d);self.assertEqual(result['issues'],[])
        self.assertTrue(result['attempt_accounting_complete'])
        self.assertFalse(result['independent_reader_coverage_complete'])
        self.assertEqual(result['attempts'][1]['classification'],'publisher_api_rejected')

    def test_unobserved_raw_delivery_accounted_as_unknown(self):
        d=data_fixture();remove_case_observations(d,1)
        result=validate(d);self.assertEqual(result['issues'],[])
        self.assertEqual(result['attempts'][1]['classification'],'raw_delivery_not_observed')
        self.assertFalse(result['independent_reader_coverage_complete'])

    def test_observer_and_bag_decoder_difference_recorded(self):
        d=data_fixture();case=d['plan']['cases'][3]
        r=next(v for v in d['raw'] if v['sha256']==case['sha256'] and v['topic']==JOB)
        r.update(decoded=False,exception_type='RMWError',exception='different local decode result')
        result=validate(d);self.assertEqual(result['issues'],[])
        self.assertEqual(len(result['decoder_discrepancies']),1)

    def test_control_decode_failure_cannot_be_relabeled_as_unknown(self):
        d=data_fixture();case=d['plan']['cases'][0]
        r=next(v for v in d['raw'] if v['sha256']==case['sha256'] and v['topic']==JOB)
        r.update(decoded=False,exception_type='RMWError',exception='failed valid control');self.assert_bad(d)

    def test_empty_header_labels_cannot_attribute_business_id(self):
        d=data_fixture();d['worker'].insert(-1,dict(type='job_rejected',job_id=900002,reason='foreign',receive_ns=4_000_000_000))
        self.assert_bad(d)

    def test_candidate_tail_job_stencil_corruption_fails(self):
        d=data_fixture();next(e for e in d['reg'] if e.get('job',{}).get('job_id')==900009)['job']['config_generation']=55
        self.assert_bad(d)

    def test_native_payload_or_normal_view_contract_failure_fails(self):
        d=data_fixture();next(r for r in d['bag'] if r['topic']==CANDIDATE)['message']['backend']='ppo';self.assert_bad(d)
        d=data_fixture();d['native_view_contract']['source_bag_contract_complete']=False;self.assert_bad(d)

    def test_normal_flag_terminal_skip_and_source_close_fail(self):
        for mode in ('normal','terminal','skip','unclosed'):
            d=data_fixture()
            if mode=='normal':next(e for e in d['reg'] if e['type']=='decision')['normal_contract_complete']=True
            elif mode=='terminal':d['reg'].insert(-1,dict(type='worker_unusable_transition'))
            elif mode=='skip':d['reg'].insert(-1,dict(type='scheduler_skipped_ticks'))
            else:d['all_sources_closed']=False
            self.assert_bad(d)


if __name__=='__main__':unittest.main()
