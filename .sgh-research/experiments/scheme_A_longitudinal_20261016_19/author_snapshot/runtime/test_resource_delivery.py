import copy,unittest
from test_check_p1_execution import fixture
from check_resource_delivery import analyze

def prepared():
    reg,worker,bag,c,context,digest=fixture();j=reg[1]['job'];sc=worker[0]
    reg[2].update(worker_instance='worker',solve_start_ns=sc['solve_start_ns'],solve_end_ns=sc['solve_end_ns'],first_control=sc['first_control'])
    reg.insert(2,{'type':'job_publish_result','job_id':1,'publish_start_ns':1,'publish_end_ns':2,'success':True})
    worker.insert(0,{'type':'job_received','job':copy.deepcopy(j),'worker_instance':'worker','receive_ns':sc['receive_ns'],'commit_ns':sc['receive_ns']})
    worker.insert(2,{'type':'candidate_publish_result','job_id':1,'worker_instance':'worker','solve_start_ns':sc['solve_start_ns'],'solve_end_ns':sc['solve_end_ns'],'publish_start_ns':3,'publish_end_ns':4,'success':True})
    report={k:True for k in ('source_bag_contract_complete','logical_admission_contract_passed','lifecycle_verified','raw_input_recording_complete')};report.update(run_id='run',issues=[])
    return [reg,worker,bag,context,report]
class DeliveryRisks(unittest.TestCase):
    def check(self,f):return analyze(*f)
    def assertFails(self,f,code):r=self.check(f);self.assertFalse(r['passed']);self.assertIn(code,[i['code'] for i in r['issues']])
    def test_full_closed_chain(self):r=self.check(prepared());self.assertTrue(r['passed']);self.assertIsNone(r['dds_internal_loss_count'])
    def test_missing_rejected_registration_is_not_ignored(self):f=prepared();f[0]=[r for r in f[0] if r['type']!='candidate_registration'];self.assertFails(f,'candidate_registration_missing_or_duplicate')
    def test_duplicate_registration_fails(self):f=prepared();f[0].insert(0,copy.deepcopy(next(r for r in f[0] if r['type']=='candidate_registration')));self.assertFails(f,'candidate_registration_missing_or_duplicate')
    def test_receiver_missing_but_recorder_present(self):f=prepared();f[1]=[r for r in f[1] if r['type']!='job_received'];self.assertFails(f,'job_worker_delivery_missing_or_ambiguous')
    def test_publish_return_unknown_is_not_success(self):f=prepared();f[0]=[r for r in f[0] if r['type']!='job_publish_result'];self.assertFails(f,'job_publish_stage_unresolved')
    def test_candidate_publish_failed(self):f=prepared();next(r for r in f[1] if r['type']=='candidate_publish_result')['success']=False;self.assertFails(f,'candidate_publish_failed_or_identity')
    def test_same_id_different_payload_fails(self):f=prepared();f[2]['/p1/solve_job'][0]['message']['reference'][0]=7.;self.assertFails(f,'recorder_multiset_difference')
    def test_duplicate_same_identity_fails(self):f=prepared();f[2]['/p1/solve_job'].append(copy.deepcopy(f[2]['/p1/solve_job'][0]));self.assertFails(f,'ambiguous_job_identity')
    def test_foreign_same_id_receipt_fails(self):f=prepared();next(r for r in f[1] if r['type']=='job_received')['job']['run_id']='foreign';self.assertFails(f,'job_receipt_content_mismatch')
    def test_candidate_registration_payload_mismatch(self):f=prepared();next(r for r in f[0] if r['type']=='candidate_registration')['first_control']=[1.,0.];self.assertFails(f,'candidate_registration_content_mismatch')
    def test_worker_received_without_outcome(self):f=prepared();f[1]=[r for r in f[1] if r['type']!='candidate'];self.assertFails(f,'worker_job_outcome_unexplained_or_duplicate')
    def test_superseded_is_counted_separately(self):
        f=prepared();second=prepared()
        for source in (second[0],second[1]):
            for row in source:
                if row.get('job_id')==1:row['job_id']=2
                if row.get('job',{}).get('job_id')==1:row['job']['job_id']=2
        for topic in ('/p1/solve_job','/p1/solve_candidate'):
            for row in second[2][topic]:
                job=row['message'] if topic.endswith('solve_job') else row['message']['job'];job['job_id']=2
        f[0]=[r for r in f[0] if r['type']!='candidate_registration'];f[1]=[r for r in f[1] if r['type'] not in ('candidate','candidate_publish_result')];f[2]['/p1/solve_candidate']=[]
        f[0]+= [r for r in second[0] if r['type'] in ('job','job_publish_result','candidate_registration')]
        f[1]+= [r for r in second[1] if r['type'] in ('job_received','candidate','candidate_publish_result')]
        f[1].append({'type':'pending_replaced','job_id':1,'replacement_job_id':2})
        for topic in ('/p1/solve_job','/p1/solve_candidate'):f[2][topic]+=second[2][topic]
        r=self.check(f);self.assertTrue(r['passed']);self.assertEqual(r['counts']['worker_pending_superseded'],1);self.assertEqual(r['counts']['recorder_candidate_missing'],0)
    def test_weak_base_facts_cannot_complete_chain(self):f=prepared();f[4]['lifecycle_verified']=False;self.assertFails(f,'base_evidence_not_complete')
    def test_different_run_report_fails(self):f=prepared();f[4]['run_id']='other';self.assertFails(f,'base_report_identity')
if __name__=='__main__':unittest.main()
