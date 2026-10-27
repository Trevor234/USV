"""Pure mutations for aligned, separately owned receiver proof; no simulated DDS claim."""
import copy
import unittest

from check_cdr_receive_aligned import validate, RAW_TOPICS, digest, raw_key
from test_cdr_receive import data_fixture, remove_case_observations


def aligned_fixture():
    d=data_fixture()
    remove_case_observations(d,1);remove_case_observations(d,6)
    oldcases=d['plan']['cases'];oldsends=d['sends']
    cases=[];sends=[];facts=[]
    for oldindex in (0,2,3,4,5,7,8,9):
        old=oldcases[oldindex];index=len(cases);case=copy.deepcopy(old)
        case.update(case_index=index,stage={'header3':'header4','tail_minus1':'tail_minus4'}.get(old['stage'],old['stage']))
        length=4 if case['stage']=='header4' else 16 if case['stage']=='tail_minus4' else 20
        blob=(bytes([index+1])*length);case.update(bytes=length,sha256=digest(blob),blob=f'{index:02d}_{case["stage"]}.cdr')
        for stream in ('raw','bag'):
            for row in d[stream]:
                if raw_key(row)==raw_key(old):row.update(bytes=length,sha256=digest(blob))
        send=copy.deepcopy(oldsends[oldindex]);send.update(case)
        cases.append(case);sends.append(send)
        facts.append(dict(blob=case['blob'],bytes=length,sha256=digest(blob),path_within_blob_directory=True))
    d['plan'].update(schema='p1-cdr-plan-aligned-v2',sample_count=8,cases=cases,external_observer_required=True)
    d.update(sends=sends,blob_facts=facts)
    d['context']['driver_pid']=50
    node='p1_cdr_raw_observer'
    subscriptions={topic:[dict(node_name=node,endpoint_gid=[20]*12+[i+1]*4,topic_type='typed')]
                   for i,topic in enumerate(RAW_TOPICS)}
    for send in sends:
        send['subscriber_endpoints']=copy.deepcopy(subscriptions[send['topic']])
        send['publisher_endpoints']=[dict(node_name='p1_calibration_driver',endpoint_gid=[10]*12+[1]*4),
                                     dict(node_name='p1_calibration_driver',endpoint_gid=[10]*12+[2]*4)]
    start=dict(type='startup',schema='p1-cdr-external-v1',pid=100,boot_id='boot',node_name=node,
               physical_publishers_created=0)
    rows=[];external_facts=[]
    for source in d['raw']:
        row=copy.deepcopy(source);row.update(type='raw',blob=f'{row["sequence"]:06d}.cdr')
        rows.append(row)
        external_facts.append(dict(sequence=row['sequence'],blob=row['blob'],bytes=row['bytes'],
                                   sha256=row['sha256'],path_within_blob_directory=True))
    end=dict(type='summary',schema='p1-cdr-external-v1',pid=100,received_count=len(rows),
             normal_source_complete=True,error=None)
    d['external']=[start,dict(type='endpoint_inventory',pid=100,subscriptions=subscriptions),*rows,end]
    d.update(external_blob_facts=external_facts,external_source_closed=True,external_blob_directory_complete=True)
    cleanup=dict(name='raw_observer',cleanup_complete=True,returncode=0,remaining_members=[])
    d['summary']['cleanup']['raw_observer']=cleanup
    d['ledger'].extend((dict(type='spawn',name='raw_observer',executable_verified=True,boot_id='boot',expected_sha256='e'*64,
                            identity=dict(pid=100,pgid=100,sid=100,start_ticks=999,exe_sha256='e'*64)),
                        dict(cleanup,type='cleanup_result')))
    return d


class AlignedReceiveProof(unittest.TestCase):
    def assert_bad(self,d):self.assertFalse(validate(d)['selected_observation_gate_passed'])

    def test_eight_cases_and_separate_process_pass_scoped_gate(self):
        result=validate(aligned_fixture());self.assertEqual(result['issues'],[])
        self.assertTrue(result['independent_reader_coverage_complete'])
        self.assertEqual(len(result['attempts']),8)
        self.assertEqual(result['external_observer_pid'],100)
        self.assertFalse(result['normal_contract_complete'])
        self.assertFalse(result['target_reader_fault_observation_complete'])

    def test_wrong_sample_scope_or_extra_empty_fails(self):
        d=aligned_fixture();d['plan']['sample_count']=10;self.assert_bad(d)
        d=aligned_fixture();d['plan']['cases'][1]['stage']='empty';self.assert_bad(d)
        d=aligned_fixture();d['plan']['external_observer_required']=False;self.assert_bad(d)

    def test_same_driver_pid_cannot_claim_independence(self):
        d=aligned_fixture();d['context']['driver_pid']=100;self.assert_bad(d)

    def test_same_participant_prefix_cannot_claim_independence(self):
        d=aligned_fixture();d['sends'][0]['publisher_endpoints'][0]['endpoint_gid'][:12]=[20]*12
        self.assert_bad(d)

    def test_inventory_gid_must_match_actual_send_endpoint(self):
        d=aligned_fixture();d['sends'][0]['subscriber_endpoints'][0]['endpoint_gid'][-1]=88
        self.assert_bad(d)

    def test_truncated_gid_prefix_is_not_sufficient_identity(self):
        d=aligned_fixture();d['external'][1]['subscriptions'][RAW_TOPICS[0]][0]['endpoint_gid']=[20]*8
        self.assert_bad(d)

    def test_external_blob_hash_and_path_must_match_source(self):
        d=aligned_fixture();d['external_blob_facts'][0]['sha256']='0'*64;self.assert_bad(d)
        d=aligned_fixture();d['external_blob_facts'][0]['path_within_blob_directory']=False;self.assert_bad(d)

    def test_external_lost_sample_fails_even_with_adjusted_close_count(self):
        d=aligned_fixture();d['external'].pop(2);d['external'][-1]['received_count']-=1
        self.assert_bad(d)

    def test_external_start_summary_or_close_must_be_complete(self):
        for kind in ('startup','summary','endpoint_inventory'):
            d=aligned_fixture();d['external']=[e for e in d['external'] if e['type']!=kind];self.assert_bad(d)
        d=aligned_fixture();d['external_source_closed']=False;self.assert_bad(d)
        d=aligned_fixture();d['external'][-1]['received_count']=999;self.assert_bad(d)

    def test_extra_unaccounted_blob_and_unverified_owned_cleanup_fail(self):
        d=aligned_fixture();d['external_blob_directory_complete']=False;self.assert_bad(d)
        d=aligned_fixture();d['ledger'][-2]['executable_verified']=False;self.assert_bad(d)
        d=aligned_fixture();d['summary']['cleanup']['raw_observer']['returncode']=1;self.assert_bad(d)

    def test_padding_change_cannot_be_accepted_by_equal_observer_bag_hashes(self):
        d=aligned_fixture();case=d['plan']['cases'][1];key=raw_key(case)
        for stream in ('raw','bag','external'):
            for row in d[stream]:
                if row.get('topic') is not None and raw_key(row)==key:
                    row.update(bytes=8,sha256='f'*64)
        for fact in d['external_blob_facts']:
            if fact['sha256']==case['sha256']:fact.update(bytes=8,sha256='f'*64)
        self.assert_bad(d)

    def test_decode_difference_is_recorded_but_byte_difference_is_not_relaxed(self):
        d=aligned_fixture();row=next(e for e in d['external'] if e.get('type')=='raw' and e.get('job_id')==900004)
        row.update(decoded=False,exception_type='RMWError',exception='external local decode differs')
        result=validate(d);self.assertEqual(result['issues'],[])
        self.assertEqual(len(result['external_decoder_discrepancies']),1)
        row['sha256']='0'*64;self.assert_bad(d)

    def test_external_decode_failure_requires_an_error_record(self):
        d=aligned_fixture();row=next(e for e in d['external'] if e.get('decoded') is False)
        row.pop('exception');self.assert_bad(d)

    def test_native_recovery_and_production_source_guards_retained(self):
        d=aligned_fixture()
        for e in d['reg']:
            if e['type']=='job':e['submit_commit_ns']=1
        self.assert_bad(d)
        d=aligned_fixture();d['reg'][-1]['emitted']=999;self.assert_bad(d)
        d=aligned_fixture();next(e for e in d['reg'] if e['type']=='decision')['publish_success']=[True,False]
        self.assert_bad(d)


if __name__=='__main__':unittest.main()
