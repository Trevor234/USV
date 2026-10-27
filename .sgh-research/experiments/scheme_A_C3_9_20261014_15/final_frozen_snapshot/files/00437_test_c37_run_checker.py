#!/usr/bin/env python3
"""Finite coherent-copy checks of C3.7 checker predicates; no DDS/phase claims."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
import check_c37_owned_run as checker


def fixture():
    boot='b'*36;contract='c'*64;nominal='n'*64;instance='w'*64
    wm={'worker_instance':instance,'run_id':'test-run','boot_id':boot,
        'contract_sha256':contract,'nominal_hash':nominal,'pid':123,
        'endpoints':[{'kind':'publisher','topic':topic,'type':typ,'gid':[1]*(15)+[i+1]}
            for i,(topic,typ) in enumerate(checker.WORKER.values())]}
    cap=dict(schema_version='p1-worker-capability-v1',run_id='test-run',boot_id=boot,
        contract_hash=contract,nominal_hash=nominal,worker_instance=instance,
        clock_name='CLOCK_MONOTONIC',backend='acados',matrix_layout='column_major',
        horizon_steps=20,prediction_dt=.2,pid=123,startup_ns=10,completed_jobs=0,
        active_job=0,pending_count=0,fault_injection_enabled=True,fatal=False,reason='')
    job={field:0 for field in checker.JOB_FIELDS}
    job.update(job_id=1,worker_instance=instance)
    cand={field:0 for field in checker.CANDIDATE_FIELDS}
    cand.update(worker_instance=instance,job=job,first_control=[1.,1.])
    messages={'capability':cap,'candidate':cand};obs=[];decoded={}
    state=dict(worker_instance=instance,worker_valid=True,worker_unusable=False,
        lease_last_valid_ns=15,candidate_present=False,admission_slots=0)
    for i,(kind,(topic,typ)) in enumerate(checker.WORKER.items()):
        ep=wm['endpoints'][i];raw=dict(schema='p1-input-callback-full-cdr-v1',topic=topic,
            message_type=typ,callback_sequence=1,entry_steady_ns=40,publisher_gid=ep['gid'],
            rmw_implementation='rmw_fastrtps_cpp',source_timestamp=1,received_timestamp=2,
            publication_sequence_number=1,reception_sequence_number=1,from_intra_process=False,
            cdr_bytes=1,cdr_sha256='a'*64,cdr_hex='00')
        obs.append(dict(type='adapter_worker_callback',interface=kind,callback_sequence=1,
            received_count=1,entry_ns=20,authentication_checked_ns=30,processed_ns=50,
            resource_valid=True,resource_reason='',authentication_reason='',actual_gid=ep['gid'],
            expected_gid=ep['gid'],worker_process_alive_at_guard=True,later_worker_process_alive=True,
            full_cdr_serialized=True,raw_input=raw,semantic_callback_invoked=True,
            callback_completed_ns=50,before=deepcopy(state),after=deepcopy(state)))
        if kind=='capability':
            obs.append(dict(type='capability_admission',callback_sequence=1,received_count=1,raw_input=deepcopy(raw),capability=cap))
        else:
            source_job={checker.JOB_ALIASES.get(k,k):v for k,v in job.items()}
            obs.append(dict(type='candidate_registration',callback_sequence=1,received_count=1,
                raw_input=deepcopy(raw),job=source_job,first_control=[1.,1.]))
        decoded[topic]=[{'message':deepcopy(messages[kind])}]
    # Actual Worker/Recorder may outlive Observer. Missing later receives remain
    # reported observations, never silently equated to complete delivery.
    late=deepcopy(cap);late['completed_jobs']=1
    decoded[checker.WORKER['capability'][0]].append({'message':late})
    obs.append(dict(type='adapter_worker_reception_closed',schema='p1-C3.7-worker-reception-close-v1',
        closed_ns=90,executor_detached=True,tick_joined=True,prep_joined=True,
        capability_received=1,candidate_received=1,capability_callback_sequence=1,candidate_callback_sequence=1,
        worker_process_alive=False,all_Worker_publications_received=None,worker_endpoints_exited='unknown',business=state))
    obs.append(dict(type='source_summary',finished_ns=100))
    return obs,decoded,wm,messages


class WorkerPopulation(unittest.TestCase):
    def run_case(self,mutation=None):
        o,d,w,m=fixture()
        if mutation:mutation(o,d,w,m)
        c=checker.c36.Checks()
        report,_=checker.worker_population(o,d,w,{},c,decode=lambda raw,label:deepcopy(m[label['interface']]))
        return c,report

    def test_received_subset_keeps_terminal_unreceived_explicit(self):
        c,r=self.run_case();self.assertEqual(c.issues,[])
        self.assertEqual(r['capability']['recorded'],2);self.assertEqual(r['capability']['received'],1)
        self.assertFalse(r['capability']['all_recorded_received'])
        self.assertEqual(r['capability']['recorded_not_observed'][0]['storage_ordinal'],2)

    def test_foreign_gid_same_payload_rejected(self):
        c,_=self.run_case(lambda o,d,w,m:o[0].update(actual_gid=[9]*16))
        self.assertIn('Worker_callback_actual_owned_GID',{x['code'] for x in c.issues})

    def test_boolean_gid_byte_rejected(self):
        def edit(o,d,w,m):
            o[0]['actual_gid']=deepcopy(o[0]['actual_gid']);o[0]['actual_gid'][0]=True
        c,_=self.run_case(edit)
        self.assertIn('Worker_callback_actual_owned_GID',{x['code'] for x in c.issues})

    def test_callback_sequence_gap_rejected(self):
        c,_=self.run_case(lambda o,d,w,m:o[0].update(callback_sequence=2,received_count=2))
        self.assertIn('entire_Worker_callback_sequence_and_count',{x['code'] for x in c.issues})

    def test_decoded_full_capability_and_semantic_coherent_forgery_rejected_by_storage(self):
        def edit(o,d,w,m):m['capability']['nominal_hash']='x'*64
        c,_=self.run_case(edit)
        self.assertIn('every_received_Worker_full_typed_occurrence_in_Storage',{x['code'] for x in c.issues})

    def test_semantic_receipt_missing_rejected(self):
        def edit(o,d,w,m):o.pop(1)
        c,_=self.run_case(edit)
        self.assertIn('entire_Worker_received_semantic_receipt_population',{x['code'] for x in c.issues})

    def test_candidate_job_echo_complete_field_forgery_rejected(self):
        def edit(o,d,w,m):o[3]['job']['target_state']=[99.]*6
        c,_=self.run_case(edit)
        self.assertIn('Worker_semantic_full_candidate_Job_and_control_binding',{x['code'] for x in c.issues})

    def test_missing_candidate_typed_field_rejected(self):
        def edit(o,d,w,m):m['candidate'].pop('backend')
        c,_=self.run_case(edit)
        self.assertIn('Worker_callback_complete_typed_payload_field_domain',{x['code'] for x in c.issues})

    def test_cdr_point_after_source_close_rejected(self):
        def edit(o,d,w,m):o[0]['processed_ns']=101
        c,_=self.run_case(edit)
        self.assertIn('Worker_callback_finite_observation_time_order',{x['code'] for x in c.issues})

    def test_auth_point_after_typed_cdr_rejected(self):
        def edit(o,d,w,m):o[0]['authentication_checked_ns']=41
        c,_=self.run_case(edit)
        self.assertIn('Worker_callback_actual_typed_interface',{x['code'] for x in c.issues})

    def test_full_cdr_missing_without_resource_rejection_rejected(self):
        def edit(o,d,w,m):o[0]['raw_input']=None;o[0]['full_cdr_serialized']=False
        c,_=self.run_case(edit)
        self.assertIn('normal_Worker_callback_raw_present',{x['code'] for x in c.issues})

    def test_unknown_interface_rejected(self):
        def edit(o,d,w,m):o[0]['interface']='unregistered'
        c,_=self.run_case(edit)
        self.assertIn('Worker_callback_known_interfaces',{x['code'] for x in c.issues})

    def test_receiver_terminal_counter_mismatch_rejected(self):
        def edit(o,d,w,m):o[-2]['candidate_received']=2
        c,_=self.run_case(edit)
        self.assertIn('Worker_native_receiver_terminal_counter_conservation',{x['code'] for x in c.issues})

    def test_source_close_without_native_receiver_close_rejected(self):
        def edit(o,d,w,m):o.pop(-2)
        c,_=self.run_case(edit)
        self.assertIn('Worker_reception_terminal_event_once',{x['code'] for x in c.issues})

    def test_detached_flag_cannot_be_false(self):
        def edit(o,d,w,m):o[-2]['executor_detached']=False
        c,_=self.run_case(edit)
        self.assertIn('Worker_actual_receiver_lifecycle_close_facts',{x['code'] for x in c.issues})


class WitnessSourcePopulation(unittest.TestCase):
    def data(self,accepted=True):
        from test_p1_witness_v2_c37 import sample,expected_header
        w=sample(accepted);versions=('task_generation','model_generation','config_generation','schedule_generation')
        job={k:w['submit'][0][k] for k in ('job_id','target_tick','clock_epoch',*versions)}
        o=[]
        for r in w['tick']:
            d={k:r[k] for k in ('sequence','job_id','tick','planned_ns','start_ns','skipped_ticks',*versions)}
            d.update(type='decision',epoch=r['clock_epoch'],end_ns=r['end_ns']-1,
                     accepted=accepted if r['job_id'] else False,reason='' if accepted else 'anchor_mismatch',
                     activation_commit_ns=220 if r['job_id'] else 120,ready_commit_ns=180 if r['job_id'] else 0)
            o.append(d)
        o.append(dict(type='job',job=job,submit_commit_ns=150,publish_start_ns=151))
        o.append(dict(type='candidate_registration',job=job,accepted_registration=True,ready_commit_ns=180))
        o.append(dict(type='source_summary',finished_ns=245))
        return w,expected_header(),o

    def run_case(self,accepted=True,mutation=None):
        w,h,o=self.data(accepted)
        if mutation:mutation(w,o)
        c=checker.c36.Checks();r=checker.witness_source_population(w,h,o,c)
        return c,r

    def test_source_accepted_first_ready_exactly_bound(self):
        c,r=self.run_case();self.assertEqual(c.issues,[]);self.assertTrue(r['business_ready_source_bound'])

    def test_source_all_rejected_is_observation_complete(self):
        c,r=self.run_case(False);self.assertEqual(c.issues,[]);self.assertTrue(r['passed'])
        self.assertFalse(r['business_ready_source_bound']);self.assertFalse(r['basis']['normal_business'])

    def test_source_tick_removed_even_if_its_summary_recounted(self):
        c,r=self.run_case(mutation=lambda w,o:o.pop(0))
        self.assertFalse(r['whole_population_source_join'])
        self.assertIn('entire_Source_Witness_tick_identity_sets',{x['code'] for x in c.issues})

    def test_source_completion_cannot_use_earlier_witness_commit(self):
        def edit(w,o):next(x for x in o if x['type']=='job')['submit_commit_ns']=149
        c,r=self.run_case(mutation=edit)
        self.assertIn('entire_Source_Witness_submit_exact_completion_binding',{x['code'] for x in c.issues})

    def test_source_final_ready_rebind_without_registration_rejected(self):
        def edit(w,o):next(x for x in o if x['type']=='decision' and x['job_id'])['ready_commit_ns']=181
        c,r=self.run_case(mutation=edit)
        self.assertIn('entire_Source_Witness_activation_exact_final_ready_binding',{x['code'] for x in c.issues})

    def test_false_source_accepted_without_producer_accepted_rejected(self):
        def edit(w,o):next(x for x in o if x['type']=='decision' and x['job_id'])['accepted']=True
        c,r=self.run_case(False,edit)
        self.assertIn('Source_first_real_accepted_BusinessReady_exact_binding',{x['code'] for x in c.issues})

    def test_source_flush_cannot_be_later_than_witness_close(self):
        c,r=self.run_case(mutation=lambda w,o:o[-1].update(finished_ns=251))
        self.assertIn('Witness_close_after_all_Source_flush',{x['code'] for x in c.issues})


if __name__=='__main__':unittest.main()
