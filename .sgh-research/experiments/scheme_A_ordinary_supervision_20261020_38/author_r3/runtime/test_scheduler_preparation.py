import copy,unittest
from check_scheduler_preparation import proof,T

def decision(tick,sequence,accepted=True,job_id=None,skipped=0):
    return dict(type='decision',tick=tick,sequence=sequence,start_ns=1_000_000_000+tick*T,planned_ns=1_000_000_000+tick*T,activation_commit_ns=1_000_001_000+tick*T,accepted=accepted,job_id=tick if job_id is None else job_id,skipped_ticks=skipped,schedule_generation=1,publish_success=[False,False],normal_contract_complete=False)
def tick_rows():
    rows=[decision(0,1,False,0),decision(1,2)]
    rows.extend([dict(type='job',job={'job_id':2,'target_tick':2}),dict(type='candidate_registration',job={'job_id':2},accepted_registration=True,ready_commit_ns=1_210_000_000),
      dict(type='diagnostic_tick_barrier_enter',expected_tick=2,planned_ns=1_400_000_000,start_ns=1_400_000_000,maximum_ms=610,physical_output=False),
      dict(type='diagnostic_tick_barrier_release',expected_tick=2,released_ns=2_010_000_000,cancelled=False),
      dict(type='scheduler_skipped_ticks',expected_tick=2,due_tick=5,skipped_ticks=3,origin_ns=1_000_000_000,observed_ns=2_010_000_000,planned_ns=2_000_000_000,schedule_generation=1,invalidated_candidate_job_id=2,invalidated_candidate_target_tick=2,candidate_after=False,admission_slots_after=0)])
    rows.extend(decision(t,i+3,t!=5,0 if t==5 else t,3 if t==5 else 0) for i,t in enumerate(range(5,9)))
    resumed=next(r for r in rows if r['type']=='decision' and r['tick']==5);resumed['start_ns']=2_010_000_000;resumed['activation_commit_ns']=2_010_001_000
    rows.extend(dict(type='capability_admission',renewed=True,validation_commit_ns=n) for n in (1_600_000_000,1_800_000_000,2_000_000_000))
    return rows
def prepare_rows():
    rows=[decision(t,t+1,t in (1,2) or t>=17,0 if 3<=t<17 else t) for t in range(21)]
    en=1_400_100_000;end=en+2_810_000_000
    rows.extend([dict(type='diagnostic_preparation_barrier_enter',target_tick=3,start_ns=en,maximum_ms=2810,physical_output=False),dict(type='diagnostic_preparation_barrier_release',target_tick=3,released_ns=end,cancelled=False,worker_unusable=False,pending_after=True)])
    for target in range(4,18):
        rows.append(dict(type='diagnostic_preparation_pending_enqueued',target_tick=target,enqueued_ns=1_000_001_000+(target-1)*T,pending_count=1))
        if target>4:rows.append(dict(type='prepare_pending_replaced',old_target_tick=target-1,replacement_target_tick=target))
    rows.append(dict(type='job_not_submitted',target_tick=3,reason='tick_changed_before_submit',processed_ns=end+1,deadline_ns=1_550_000_000))
    rows.append(dict(type='job',submit_commit_ns=end+2,job={'target_tick':17,'freeze_ns':4_200_001_000,'tick_origin_ns':4_200_000_000,'deadline_ns':4_350_000_000}))
    return rows
def tagged(rows,tag):return next(r for r in rows if r['type']==tag)

class SchedulerProof(unittest.TestCase):
    def test_actual_ready_skip_and_recovery(self):self.assertEqual(proof(tick_rows(),'tick_skip')['issues'],[])
    def test_requires_ready_candidate_premise(self):
        rows=[r for r in tick_rows() if r['type']!='candidate_registration'];self.assertTrue(proof(rows,'tick_skip')['issues'])
    def test_wrong_due_and_absolute_plan_rejected(self):
        for key,value in (('due_tick',4),('origin_ns',900_000_000),('planned_ns',2_010_000_000),('skipped_ticks',1)):
            rows=tick_rows();tagged(rows,'scheduler_skipped_ticks')[key]=value;self.assertTrue(proof(rows,'tick_skip')['issues'])
    def test_stale_activation_or_replay_rejected(self):
        rows=tick_rows();d=[r for r in rows if r['type']=='decision'][2];d.update(accepted=True,job_id=2,tick=2);self.assertTrue(proof(rows,'tick_skip')['issues'])
    def test_callbacks_and_native_recovery_required(self):
        for tag in ('capability_admission','decision'):
            rows=tick_rows()
            if tag=='capability_admission':rows=[r for r in rows if r['type']!=tag]
            else:
                for r in rows:
                    if r['type']=='decision' and r['tick']>=6:r['accepted']=False
            self.assertTrue(proof(rows,'tick_skip')['issues'])
    def test_terminal_or_cancelled_or_uncleared_rejected(self):
        for variant in ('terminal','cancelled','slot'):
            rows=tick_rows()
            if variant=='terminal':rows.append(dict(type='worker_unusable_transition'))
            elif variant=='cancelled':tagged(rows,'diagnostic_tick_barrier_release')['cancelled']=True
            else:tagged(rows,'scheduler_skipped_ticks')['admission_slots_after']=1
            self.assertTrue(proof(rows,'tick_skip')['issues'])
class PreparationProof(unittest.TestCase):
    def test_natural_latest_pending_release(self):self.assertEqual(proof(prepare_rows(),'prepare_release')['issues'],[])
    def test_cancelled_or_nonempty_premise_missing_rejected(self):
        for key,value in (('cancelled',True),('pending_after',False),('worker_unusable',True)):
            rows=prepare_rows();tagged(rows,'diagnostic_preparation_barrier_release')[key]=value;self.assertTrue(proof(rows,'prepare_release')['issues'])
    def test_wrong_replacement_chain_and_capacity_rejected(self):
        for tag,key in (('prepare_pending_replaced','old_target_tick'),('diagnostic_preparation_pending_enqueued','pending_count')):
            rows=prepare_rows();tagged(rows,tag)[key]=99;self.assertTrue(proof(rows,'prepare_release')['issues'])
    def test_old_item_submission_or_missing_reject_rejected(self):
        rows=prepare_rows();rows=[r for r in rows if r['type']!='job_not_submitted'];self.assertTrue(proof(rows,'prepare_release')['issues'])
        rows=prepare_rows();tagged(rows,'job')['job']['target_tick']=3;self.assertTrue(proof(rows,'prepare_release')['issues'])
    def test_latest_snapshot_and_original_deadline_required(self):
        for key,value in (('target_tick',16),('freeze_ns',4_200_001_001),('deadline_ns',4_550_000_000)):
            rows=prepare_rows();tagged(rows,'job')['job'][key]=value;self.assertTrue(proof(rows,'prepare_release')['issues'])
        rows=prepare_rows();tagged(rows,'job')['submit_commit_ns']=4_350_000_001;self.assertTrue(proof(rows,'prepare_release')['issues'])
    def test_tick_independence_and_recovery_required(self):
        rows=prepare_rows();rows.append(dict(type='scheduler_skipped_ticks'));self.assertTrue(proof(rows,'prepare_release')['issues'])
        rows=prepare_rows()
        for r in rows:
            if r['type']=='decision' and r['tick']>=17:r['accepted']=False
        self.assertTrue(proof(rows,'prepare_release')['issues'])

if __name__=='__main__':unittest.main()
