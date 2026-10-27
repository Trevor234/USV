#!/usr/bin/python3
"""No-ROS semantic regressions and fresh native-copy C3.2 negatives.

Unit fixtures exercise the actual checker functions without claiming an owned
run. With --run and --output-dir, every case copies the complete native run,
registers its resulting source/storage/transport hashes, then requires the
named semantic failure (parser/loading failure never counts as a negative).
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import unittest
sys.dont_write_bytecode=True
import check_atomic_observation_v2 as C


def prefix(ordinal=1):
    return dict(input_commit_ordinal=ordinal,state=[0.]*6,version={'task':2,'model':1,'config':1,'schedule':1,'epoch':0},
        odom_sequence=1,odom_stamp_ns=1_000_000_000,odom_receive_ns=1_000_000_000,
        imu_sequence=1,imu_stamp_ns=1_000_000_000,imu_receive_ns=1_000_000_000,r_from_imu=False,
        clock_sim_ns=1_000_000_000,clock_receive_ns=1_000_000_000,rtf=1.,rtf_valid=True,paused=False,
        path=[[0.,0.,0.],[1.,0.,0.]],profile=[[0.,0.,0.,0.],[0.,0.,0.,1.]],
        path_sequence=1,profile_sequence=1,path_stamp=(1,0),profile_stamp=(1,0),
        path_fingerprint='a'*64,profile_fingerprint='b'*64,
        held_history=[{'sim_ns':900_000_000,'channel':0,'value':0.},{'sim_ns':900_000_000,'channel':1,'value':0.}],
        publication_history=[{'channel':0,'sequence':1,'publish_ns':900_000_000,'n':0.,'known':True},
            {'channel':1,'sequence':1,'publish_ns':900_000_000,'n':0.,'known':True}],
        anchor={'n':[0.,0.],'sequence':[1,1],'publish_ns':[900_000_000]*2,'known':[True,True]},
        anchor_producer='producer',anchor_run_id='run-publisher',anchor_source='legacy_publisher')


def snapshot(p):
    keys=('input_commit_ordinal state version odom_sequence odom_stamp_ns odom_receive_ns imu_sequence imu_stamp_ns '
        'imu_receive_ns r_from_imu clock_sim_ns clock_receive_ns rtf rtf_valid paused anchor held_history '
        'publication_history anchor_producer anchor_run_id anchor_source').split()
    out={k:copy.deepcopy(p[k]) for k in keys};out.update(ref_selection=C.ref_selection(p),history_count=len(p['held_history']),
        publication_history_count=len(p['publication_history']),sample_ns=1_000_000_001,copy_capture_ns=1_000_000_002,commit_ns=1_000_000_003)
    return out


def config():
    return dict(odom_age_ns=100_000_000,imu_age_ns=100_000_000,mixed_skew_ns=100_000_000,clock_age_ns=100_000_000,
        odom_sim_lag_ns=100_000_000,imu_sim_lag_ns=100_000_000,source_future_slack_ns=20_000_000,
        tick_jitter_ns=20_000_000,command_min_n=-1.,command_max_n=1.,publisher_max_n=1.,map_scale=1.,rho_n_s=1.,hold_ns=100_000_000,
        target_sim_slack_ns=100_000_000,activation_tolerance=[1.]*6,
        hydro={'mass':180.,'Xu_dot':-100.,'Yv_dot':-200.,'xg':0.,'Yr_dot':0.,'Nv_dot':0.,'Iz':200.,'Nr_dot':-100.,
            'Xu':-10.,'Xuu':-10.,'Yv':-10.,'Yvv':-10.,'Yr':0.,'Yrr':0.,'Nv':0.,'Nvv':0.,'Nr':-10.,'Nrr':-10.,'d_thruster':1.})


def no_pair():
    p=prefix();v=snapshot(p);f=snapshot(p)
    reads={k:None for k in C.GATE_KEYS};reads.update(early_legacy_enabled=True,early_legacy_measurement=True,
        early_stopping=False,early_worker_unusable=False,final_stopping=False,final_stop_requested=False,
        fallback_invalid_stopping=False,fallback_invalid_worker_unusable=False)
    ob=dict(candidate_pair_available=False,candidate_job_id=None,candidate_target_tick=None,prediction_target_sim_ns=None,
        predict_invoked=False,predict_success=False,predict_status='not_attempted',predicted_state=None,full_error=None,
        input_change_gate_ran=False,input_change_gate_unchanged=None,gate_reads=reads)
    d=dict(sequence=1,start_ns=v['sample_ns'],planned_ns=1_000_000_000,accepted=False,reason='no_candidate',
        requested_n=[0.,0.],final_n=[0.,0.],control_source='ramp_zero',d0_observation=ob)
    return d,v,f,p,copy.deepcopy(p)


class AtomicSemanticTests(unittest.TestCase):
    def codes(self,ev):return {x['code'] for x in ev.issues}
    def test_six_callback_types_contiguous(self):
        ev=C.Evidence();rows=[{'type':typ,'input_commit_ordinal':i} for i,typ in enumerate(
            ['odom_admission','imu_admission','path_version','profile_version','clock','legacy_anchor'],1)]
        self.assertEqual(len(C.input_transactions(rows,ev)),6);self.assertFalse(ev.issues)
    def test_Applied_reset_and_anchor_same_transaction(self):
        ev=C.Evidence();rows=[{'type':'legacy_history_reset','sequence':4,'input_commit_ordinal':1},
            {'type':'legacy_anchor','sequence':4,'input_commit_ordinal':1}]
        self.assertEqual(len(C.input_transactions(rows,ev)),1);self.assertFalse(ev.issues)
    def test_ordinal_gap_rejected(self):
        ev=C.Evidence();C.input_transactions([{'type':'clock','input_commit_ordinal':2}],ev)
        self.assertIn('callback_ordinal_not_strict_contiguous',self.codes(ev))
    def test_ordinal_decrease_rejected(self):
        ev=C.Evidence();C.input_transactions([{'type':'clock','input_commit_ordinal':1},
            {'type':'clock','input_commit_ordinal':2},{'type':'clock','input_commit_ordinal':1}],ev)
        self.assertIn('callback_ordinal_reappeared',self.codes(ev))
    def test_duplicate_non_Applied_rejected(self):
        ev=C.Evidence();C.input_transactions([{'type':'clock','input_commit_ordinal':1},
            {'type':'odom_admission','input_commit_ordinal':1}],ev)
        self.assertIn('callback_ordinal_duplicate_not_Applied_projection',self.codes(ev))
    def test_bool_ordinal_is_not_integer(self):
        ev=C.Evidence();C.input_transactions([{'type':'clock','input_commit_ordinal':True}],ev)
        self.assertIn('callback_ordinal_missing_or_invalid',self.codes(ev))
    def test_prelock_receive_order_does_not_select_prefix(self):
        ev=C.Evidence();rows=[{'type':'clock','input_commit_ordinal':1,'receive_ns':20},
            {'type':'odom_admission','input_commit_ordinal':2,'receive_ns':10}]
        self.assertEqual(list(C.input_transactions(rows,ev)),[1,2]);self.assertFalse(ev.issues)
    def test_full_snapshot_positive(self):
        p=prefix();ev=C.Evidence();self.assertEqual(C.check_snapshot(snapshot(p),{1:p},ev,'final',1),p);self.assertFalse(ev.issues)
    def test_full_final_state_failure(self):
        p=prefix();x=snapshot(p);x['state'][5]=.1;ev=C.Evidence();C.check_snapshot(x,{1:p},ev,'final',1)
        self.assertIn('snapshot_full_state_from_last_ordinal',self.codes(ev))
    def test_reference_stamp_pair_alias_not_sum_equivalence(self):
        p=prefix();x=snapshot(p);x['ref_selection']['profile_stamp']={'sec':0,'nanosec':1_000_000_000}
        ev=C.Evidence();C.check_snapshot(x,{1:p},ev,'validation',1)
        self.assertIn('snapshot_reference_sequence_stamp_pair_fingerprint_size',self.codes(ev))
    def test_selected_old_reference_identity_failure(self):
        p=prefix();x=snapshot(p);x['ref_selection']['path_sequence']=0;ev=C.Evidence();C.check_snapshot(x,{1:p},ev,'final',1)
        self.assertIn('snapshot_reference_sequence_stamp_pair_fingerprint_size',self.codes(ev))
    def test_full_publication_omission_failure(self):
        p=prefix();x=snapshot(p);x['publication_history'].pop();x['publication_history_count']-=1
        ev=C.Evidence();C.check_snapshot(x,{1:p},ev,'final',1)
        self.assertIn('snapshot_full_prefix_history_anchor_identity',self.codes(ev))
    def test_full_anchor_producer_identity_failure(self):
        p=prefix();x=snapshot(p);x['anchor_producer']='foreign';ev=C.Evidence();C.check_snapshot(x,{1:p},ev,'final',1)
        self.assertIn('snapshot_full_prefix_history_anchor_identity',self.codes(ev))
    def test_no_candidate_original_gate_shape(self):
        d,v,f,vp,fp=no_pair();ev=C.Evidence();C.replay_gates(d,v,f,vp,fp,None,None,config(),0,ev);self.assertFalse(ev.issues)
    def test_unread_commit_operand_not_false(self):
        d,v,f,vp,fp=no_pair();d['d0_observation']['gate_reads']['commit_sink_failed']=False
        ev=C.Evidence();C.replay_gates(d,v,f,vp,fp,None,None,config(),0,ev)
        self.assertIn('gate_operand_short_circuit_shape',self.codes(ev))
    def test_shutdown_override_and_short_circuit(self):
        d,v,f,vp,fp=no_pair();reads=d['d0_observation']['gate_reads'];reads['early_legacy_measurement']=False
        reads['final_stopping']=True;reads['final_stop_requested']=None;reads['fallback_invalid_stopping']=True;reads['fallback_invalid_worker_unusable']=None
        d['reason']='shutdown';ev=C.Evidence();C.replay_gates(d,v,f,vp,fp,None,None,config(),0,ev);self.assertFalse(ev.issues)
    def test_final_shutdown_override_cannot_be_removed(self):
        d,v,f,vp,fp=no_pair();reads=d['d0_observation']['gate_reads'];reads['final_stop_requested']=True
        ev=C.Evidence();C.replay_gates(d,v,f,vp,fp,None,None,config(),0,ev)
        self.assertIn('independent_original_reason_overrides',self.codes(ev))
    def test_unread_final_stop_request_is_null(self):
        d,v,f,vp,fp=no_pair();reads=d['d0_observation']['gate_reads'];reads['final_stopping']=True
        d['reason']='shutdown';ev=C.Evidence();C.replay_gates(d,v,f,vp,fp,None,None,config(),0,ev)
        self.assertIn('gate_operand_short_circuit_shape',self.codes(ev))
    def test_readiness_event_window_without_Decision_reason(self):
        rows=[{'type':'legacy_ready','readiness':{'legacy_ready_ns':10}}]
        self.assertEqual(C.flag_possible(rows,False,{'legacy_ready'},set(),1,9),{False})
        self.assertEqual(C.flag_possible(rows,False,{'legacy_ready'},set(),9,11),{False,True})
        self.assertEqual(C.flag_possible(rows,False,{'legacy_ready'},set(),11,20),{True})
    def test_stopping_true_to_false_rejected_same_Decision(self):
        d,*_=no_pair();reads=d['d0_observation']['gate_reads'];reads['early_stopping']=True;reads['final_stopping']=False
        ev=C.Evidence();C.irreversible_flag_reads([d],ev)
        self.assertIn('irreversible_original_flag_true_to_false',self.codes(ev))
    def test_worker_true_to_false_rejected_across_Decisions(self):
        a,*_=no_pair();b=copy.deepcopy(a);b['sequence']=2;a['d0_observation']['gate_reads']['early_worker_unusable']=True
        a['d0_observation']['gate_reads']['fallback_invalid_worker_unusable']=True
        ev=C.Evidence();C.irreversible_flag_reads([a,b],ev)
        self.assertIn('irreversible_original_flag_true_to_false',self.codes(ev))
    def test_unread_flag_does_not_reset_irreversibility(self):
        a,*_=no_pair();b=copy.deepcopy(a);b['sequence']=2
        for d in (a,b):
            for k in ('early_stopping','final_stopping','fallback_invalid_stopping','fallback_source_stopping'):d['d0_observation']['gate_reads'][k]=None
        a['d0_observation']['gate_reads']['early_stopping']=True;b['d0_observation']['gate_reads']['final_stopping']=True
        ev=C.Evidence();C.irreversible_flag_reads([a,b],ev);self.assertFalse(ev.issues)


NATIVE_CASES={
    'ordinal_gap':'callback_ordinal_not_strict_contiguous',
    'validation_selected_old_reference':'snapshot_reference_sequence_stamp_pair_fingerprint_size',
    'coherent_reference_stamp_pair_alias':'snapshot_reference_sequence_stamp_pair_fingerprint_size',
    'full_final_state':'snapshot_full_state_from_last_ordinal',
    'full_final_publication_omission':'snapshot_full_prefix_history_anchor_identity',
    'full_final_anchor_identity':'snapshot_full_prefix_history_anchor_identity',
    'candidate_actual_pointer_other_job':'actual_candidate_ticket_echoed_Job_binding',
    'gate_unread_commit_value':'gate_operand_short_circuit_shape',
    'coherent_shutdown_reason_removed':'independent_original_reason_overrides',
    'coherent_full_echoed_Job':'actual_candidate_full_echoed_Job_original_binding',
    'prediction_target_sim_claim':'actual_candidate_prediction_target_sim_binding',
    'coherent_Decision_target_state':'actual_candidate_canonical_Decision_target_state_binding',
    'coherent_stopping_true_to_false':'irreversible_original_flag_true_to_false',
    'capability_admission_full19_corruption':'capability_admission_no_ordered_typed_payload',
    'coherent_capability_attempt_payload':'capability_publisher_source_actual_full19_population',
    'capability_lease_replay_corruption':'capability_lease_replay',
}


def create_json(path,value):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write('\n')


def rewrite_decision_cdr(root, sequence, changes):
    """Coherently change canonical source/CDR/transport on a fresh copy only."""
    from rclpy.serialization import deserialize_message,serialize_message
    from rosidl_runtime_py.utilities import get_message
    transport_path=root/'synthetic_source/transport_source.jsonl'
    transport=[json.loads(line) for line in transport_path.read_text().splitlines()]
    old_new={}
    connection=__import__('sqlite3').connect(root/'recorder/bag/bag_0.db3')
    try:
        rows=connection.execute('SELECT messages.id,topics.type,messages.data FROM messages JOIN topics ON messages.topic_id=topics.id WHERE topics.name=?',('/p1/execution_decision',)).fetchall()
        for mid,typ,data in rows:
            message=deserialize_message(data,get_message(typ))
            if message.sequence!=sequence:continue
            for key,value in changes.items():setattr(message,key,value)
            blob=serialize_message(message);connection.execute('UPDATE messages SET data=? WHERE id=?',(blob,mid));old_new[C.sha(data)]=(C.sha(blob),len(blob))
        connection.commit()
    finally:connection.close()
    if len(old_new)!=1:raise ValueError('coherent negative did not select exactly one stored Decision')
    for row in transport:
        if row.get('topic')=='/p1/execution_decision' and row.get('payload_sha256') in old_new:
            digest,size=old_new[row['payload_sha256']];row['payload_sha256']=digest
            row['serialized_bytes']=size
    transport_path.write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in transport))


def rewrite_candidate_echo(root,job_id,source_rows):
    from rclpy.serialization import deserialize_message,serialize_message
    from rosidl_runtime_py.utilities import get_message
    wp=root/'worker/source.jsonl';worker=[json.loads(x) for x in wp.read_text().splitlines()]
    selected=[r for r in worker if r['type']=='candidate' and r['job']['job_id']==job_id]
    if len(selected)!=1:raise ValueError('coherent echoed Job source selection not unique')
    selected[0]['job']['reference'][0]+=.125
    wp.write_text(''.join(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n' for r in worker))
    connection=__import__('sqlite3').connect(root/'recorder/bag/bag_0.db3');changed={}
    try:
        records=connection.execute('SELECT messages.id,topics.type,messages.data FROM messages JOIN topics ON messages.topic_id=topics.id WHERE topics.name=?',('/p1/solve_candidate',)).fetchall()
        for mid,typ,data in records:
            message=deserialize_message(data,get_message(typ))
            if message.job.job_id!=job_id:continue
            reference=list(message.job.reference);reference[0]+=.125;message.job.reference=reference
            blob=serialize_message(message);connection.execute('UPDATE messages SET data=? WHERE id=?',(blob,mid));changed[C.sha(data)]=(C.sha(blob),len(blob))
        connection.commit()
    finally:connection.close()
    if len(changed)!=1:raise ValueError('coherent echoed Job stored Candidate selection not unique')
    tp=root/'synthetic_source/transport_source.jsonl';transport=[json.loads(x) for x in tp.read_text().splitlines()]
    for r in transport:
        if r.get('topic')=='/p1/solve_candidate' and r.get('payload_sha256') in changed:
            r['payload_sha256'],r['serialized_bytes']=changed[r['payload_sha256']]
    tp.write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in transport))
    digest,size=next(iter(changed.values()))
    for r in source_rows:
        if r['type']!='decision':continue
        cap=r['d0_observation']['candidate_capture']
        if cap['candidate_present'] and cap['job_id']==job_id:cap['cdr_sha256']=digest;cap['cdr_bytes']=size


def rewrite_capability_attempt(root):
    from rclpy.serialization import deserialize_message,serialize_message
    from rosidl_runtime_py.utilities import get_message
    path=root/'worker/source.jsonl';rows=[json.loads(x) for x in path.read_text().splitlines()]
    attempt=next(r for r in rows if r['type']=='capability_publish_attempt')
    result=next(r for r in rows if r['type']=='capability_publish_result' and r['publish_seq']==attempt['publish_seq'])
    value=attempt['payload'];value['prediction_dt']+=.125
    message=deserialize_message(bytes.fromhex(attempt['cdr']['hex']),get_message('usv_research_interfaces/msg/WorkerCapability'))
    message.prediction_dt=value['prediction_dt'];blob=serialize_message(message)
    attempt['cdr'].update(hex=blob.hex(),bytes=len(blob),sha256=C.sha(blob))
    attempt['payload_sha256']=result['payload_sha256']=C.numerical.typed_sha(value)
    terminal=next(r for r in rows if r['type']=='worker_summary')
    if terminal['capability_source']['capability_last_publish_seq']==attempt['publish_seq']:
        terminal['capability_source']['capability_last_payload_sha256']=attempt['payload_sha256']
    path.write_text(''.join(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n' for r in rows))


def mutate(root,name):
    path=root/'observer/source.jsonl';rows=[json.loads(x) for x in path.read_text().splitlines()]
    decisions=[r for r in rows if r['type']=='decision'];d=next((r for r in decisions if r['d0_observation']['candidate_pair_available']),decisions[0])
    ob=d['d0_observation'];v=ob['validation_snapshot'];f=ob['final_snapshot']
    if name=='ordinal_gap':
        r=next(r for r in rows if r['type'] in C.CALLBACK_TYPES);r['input_commit_ordinal']+=1
    elif name=='validation_selected_old_reference':v['ref_selection']['path_sequence']-=1
    elif name=='coherent_reference_stamp_pair_alias':
        # Same ns sum, different immutable stamp pair; change both observations
        # and every Job provenance claim, while raw full inputs stay immutable.
        for r in rows:
            selections=[]
            if r['type']=='decision':selections=[r['d0_observation'][k]['ref_selection'] for k in ('validation_snapshot','final_snapshot')]
            elif r['type']=='job':selections=[r['input_provenance']['ref_selection']]
            for selection in selections:
                stamp=selection['profile_stamp']
                if selection['profile_sequence']:stamp['sec']-=1;stamp['nanosec']+=1_000_000_000
    elif name=='full_final_state':f['state'][5]+=.1
    elif name=='full_final_publication_omission':
        if not f['publication_history']:raise ValueError('run has no selected final publication history')
        f['publication_history'].pop(0);f['publication_history_count']-=1
    elif name=='full_final_anchor_identity':f['anchor_producer']+='-foreign'
    elif name=='candidate_actual_pointer_other_job':
        other=next(r['d0_observation']['candidate_capture'] for r in decisions if r['d0_observation']['candidate_capture']['candidate_present'] and r['d0_observation']['candidate_capture']['job_id']!=ob['candidate_capture']['job_id'])
        for key in ('cdr_bytes','cdr_sha256','job_id','worker_instance','first_control'):ob['candidate_capture'][key]=copy.deepcopy(other[key])
    elif name=='coherent_full_echoed_Job':rewrite_candidate_echo(root,ob['candidate_capture']['job_id'],rows)
    elif name=='prediction_target_sim_claim':ob['prediction_target_sim_ns']+=1
    elif name=='coherent_Decision_target_state':
        d['target_state'][5]+=.125;rewrite_decision_cdr(root,d['sequence'],{'target_state':d['target_state']})
    elif name=='coherent_stopping_true_to_false':
        d=next(r for r in reversed(decisions) if r['d0_observation']['gate_reads']['early_stopping'] is True and r['d0_observation']['gate_reads']['final_stopping'] is True)
        reads=d['d0_observation']['gate_reads'];reads['final_stopping']=False;reads['final_stop_requested']=True
    elif name=='capability_admission_full19_corruption':
        admission=next(r for r in rows if r['type']=='capability_admission');admission['capability']['prediction_dt']+=.125
    elif name=='coherent_capability_attempt_payload':rewrite_capability_attempt(root)
    elif name=='capability_lease_replay_corruption':
        admission=next(r for r in rows if r['type']=='capability_admission');admission['lease_last_before_ns']+=1
    elif name=='gate_unread_commit_value':
        d=next(r for r in decisions if r['d0_observation']['gate_reads']['commit_sink_failed'] is None)
        d['d0_observation']['gate_reads']['commit_sink_failed']=False
    elif name=='coherent_shutdown_reason_removed':
        d=next(r for r in reversed(decisions) if r['d0_observation']['gate_reads']['final_stopping'] or r['d0_observation']['gate_reads']['final_stop_requested'])
        d['reason']='no_candidate';rewrite_decision_cdr(root,d['sequence'],{'reason':'no_candidate'})
        for r in rows:
            if r['type']=='anchor_validation' and r['sequence']==d['sequence']:r['decision_reason']='no_candidate'
        wp=root/'observer/witness.json';w=json.loads(wp.read_text())
        for r in w['activation']:
            if r['job_id']==d['job_id']:r['reason_code']=3
        wp.write_text(json.dumps(w,separators=(',',':'))+'\n')
    else:raise ValueError('unknown registered native case')
    path.write_text(''.join(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n' for r in rows))


def native_cases(run,out):
    run=Path(run).absolute();out=Path(out).absolute();out.mkdir(exist_ok=False)
    before=C.load(run);positive=C.analyze(before)
    create_json(out/'preregister.json',{'schema':'p1-C3.2-native-copy-negative-plan-v1','original_run':str(run),
        'original_input_sha256':before['hashes'],'cases':NATIVE_CASES,'test_sha256':C.sha(C.safe.read_regular(Path(__file__).absolute())),
        'qualification_flags':False,'component_only':True})
    create_json(out/'original_component_baseline.json',positive)
    if not positive['passed']:raise ValueError('original component baseline failed; semantic negative qualification blocked')
    results=[]
    for name,expected in NATIVE_CASES.items():
        case=out/name;shutil.copytree(run,case,symlinks=True)
        mutate(case,name);state=C.load(case)
        # The changed native copy is re-locked, preserving original and changed
        # CDR/source pins. No stale-original digest is accepted as a semantic hit.
        create_json(out/(name+'_input_lock.json'),{'native_copy':str(case),'input_sha256':state['hashes'],
            'original_input_sha256':before['hashes'],'lock_semantics':'retrospective altered native-copy identity; not original authenticity'})
        report=C.analyze(state);codes={r['code'] for r in report['issues']}
        transport_and_typed=report['groups']['whole_raw_CDR_GID_callback_sequences_and_transport']['passed']
        passed=not report['passed'] and expected in codes and 'bounded_input_or_checker_error' not in codes and transport_and_typed and C.unchanged(state)
        create_json(out/(name+'_result.json'),report)
        results.append({'case':name,'expected_semantic_code':expected,'passed':passed,'whole_CDR_transport_source_typed_passed':transport_and_typed,'observed_codes':sorted(codes)})
    result={'schema':'p1-C3.2-native-copy-negatives-v1','passed':all(r['passed'] for r in results),
        'cases':results,'original_inputs_unchanged':C.unchanged(before),'component_verification_only':True,**C.FLAGS}
    result['passed']=result['passed'] and result['original_inputs_unchanged'];create_json(out/'summary.json',result)
    print(json.dumps(result,ensure_ascii=False));return 0 if result['passed'] else 1


def main():
    if '--run' in sys.argv:
        p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
        a=p.parse_args();return native_cases(a.run,a.output_dir)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(AtomicSemanticTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite);return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
