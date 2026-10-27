#!/usr/bin/python3
"""Fresh native-copy C3 causal negatives, preserving originals and every failure."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
sys.dont_write_bytecode = True
import check_activation_provenance_v1 as C3


def write_new(path, value):
    with Path(path).open('x') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False); f.write('\n')


def mutate_native(root, name):
    obs_path = root/'observer/source.jsonl'; worker_path = root/'worker/source.jsonl'; wp = root/'observer/witness.json'
    obs = [json.loads(x) for x in obs_path.read_text().splitlines()]
    worker = [json.loads(x) for x in worker_path.read_text().splitlines()]
    witness = json.loads(wp.read_text())
    d = next(x for x in obs if x['type'] == 'decision' and x['sequence'] == 9)
    if name in ('coherent_state_error_tail',): d = next(x for x in obs if x['type'] == 'decision' and x['sequence'] == 10)
    if name in ('input_change_gate_skipped_accepted','coherent_final_command','coherent_registered_command'): d = next(x for x in obs if x['type'] == 'decision' and x['sequence'] == 30)
    if name == 'shutdown_override_removed': d = next(x for x in obs if x['type'] == 'decision' and x['sequence'] == 31)
    ob = d['d0_observation']; v = ob['validation_snapshot']; f = ob['final_snapshot']
    ar = next((x for x in obs if x['type'] == 'anchor_validation' and x['sequence'] == d['sequence']),None)
    bag_changes = {}; job_change = None; candidate_change = None
    if name == 'validation_odom_sequence': v['odom_sequence'] -= 10
    elif name == 'final_odom_receive': f['odom_receive_ns'] += 1
    elif name == 'inactive_imu_mask':
        d['activation_imu_sequence'] = f['imu_sequence']; bag_changes['activation_imu_sequence'] = d['activation_imu_sequence']
    elif name == 'raw_imu_r_used_when_inactive': v['state'][5] = 1.0
    elif name == 'validation_state': v['state'][0] += 1.0
    elif name == 'validation_clock_selection': v['clock_sim_ns'] += 1
    elif name == 'validation_rtf': v['rtf'] += .01
    elif name == 'validation_rtf_valid': v['rtf_valid'] = not v['rtf_valid']
    elif name == 'copy_end_before_selected': v['copy_capture_ns'] = v['odom_receive_ns']-1
    elif name == 'final_version': f['version']['config'] += 1
    elif name == 'held_omission': v['held_history'].pop(0); v['history_count'] -= 1
    elif name == 'held_channel_change': v['held_history'][0]['channel'] = 1
    elif name == 'anchor_claim': v['anchor']['n'][0] += 1
    elif name == 'commit_anchor_claim': ar['actual_n'][0] += 1
    elif name == 'publication_entry_omission': ar['entries'].pop(0)
    elif name == 'publication_change_return': ar['entries'][0]['n'] += 1
    elif name == 'coherent_nominal_prediction':
        d['activation_state'][0] += .1; ob['predicted_state'] = d['activation_state'][:]
        ob['full_error'][0] += .1
        _, errors = C3.state_gate(d['target_state'],d['activation_state'],json.loads(Path(C3.imports()[0]['record_pins']['contract']['path']).read_text()),lambda x:__import__('math').atan2(__import__('math').sin(x),__import__('math').cos(x)))
        d['state_error'] = errors; bag_changes.update(activation_state=d['activation_state'],state_error=errors)
    elif name == 'full_error': ob['full_error'][0] += 1.0
    elif name == 'coherent_state_error_tail': d['state_error'][5] += 1.0; bag_changes['state_error'] = d['state_error']
    elif name == 'predict_invocation_skipped': ob['predict_invoked'] = False
    elif name == 'wrong_target_sim': ob['prediction_target_sim_ns'] += 1
    elif name == 'coherent_job_reference': job_change = ('reference', .1)
    elif name == 'candidate_pointer_job': ob['candidate_job_id'] += 1
    elif name == 'input_change_gate_skipped_accepted': ob['input_change_gate_ran'] = False; ob['input_change_gate_unchanged'] = None
    elif name == 'input_change_gate_claimed_rejected': ob['input_change_gate_ran'] = True; ob['input_change_gate_unchanged'] = True
    elif name == 'coherent_rejection_reason': d['reason'] = 'no_candidate'; ar['decision_reason'] = d['reason']; bag_changes['reason'] = d['reason']
    elif name == 'coherent_final_command':
        d['final_n'][0] += .1; d['requested_n'][0] += .1; bag_changes.update(final_n=d['final_n'],requested_n=d['requested_n'])
    elif name == 'witness_activation_missing': witness['activation'].pop(0)
    elif name == 'witness_activation_extra':
        extra = copy.deepcopy(witness['activation'][-1]); extra['sequence'] += 1; witness['activation'].append(extra)
    elif name == 'registration_deadline': job_change = ('deadline_ns',1)
    elif name == 'cutoff_equality':
        job = next(x['job'] for x in obs if x['type'] == 'job' and x['job']['job_id'] == d['job_id'])
        d['cutoff_commit_ns'] = job['deadline_ns']; bag_changes['cutoff_commit_ns'] = d['cutoff_commit_ns']
    elif name == 'shutdown_override_removed': d['reason'] = 'no_candidate'; bag_changes['reason'] = d['reason']
    elif name == 'activation_version': witness['activation'][0]['task_generation'] = 99
    elif name == 'tick_version': witness['tick'][0]['model_generation'] = 99
    elif name == 'submit_version': witness['submit'][0]['config_generation'] = 99
    elif name == 'coherent_registered_command':
        reg = next(x for x in obs if x['type'] == 'candidate_registration' and x['job']['job_id'] == 22)
        reg['first_control'][0] += .1; d['requested_n'][0] += .1; d['final_n'][0] += .1
        bag_changes.update(requested_n=d['requested_n'],final_n=d['final_n'])
    elif name == 'real_worker_transition':
        obs.insert(-1,{'type':'worker_unusable_transition','reason':'worker_pidfd_readable','check_ns':d['start_ns']-1,'processed_ns':d['start_ns']-1,'worker_instance':d['worker_instance'],'candidate_before':False,'pending_before':False,'candidate_after':False,'pending_after':False,'policy':'stop_new_submit_commits_and_activation; already_committed_DDS_tail_may_finish'})
        obs[-1]['generated'] += 1; obs[-1]['emitted'] += 1
    elif name == 'source_terminal_counter': obs[-1]['generated'] -= 1
    elif name == 'witness_header': witness['header']['run_id'] += '-wrong'
    elif name == 'coherent_profile_stamp_alias': pass
    elif name.startswith('coherent_') and name in ('coherent_solver_not_invoked','coherent_worker_receive_before_freeze','coherent_negative_backend_ms','coherent_foreign_backend','coherent_foreign_worker'):
        candidate = next(x for x in worker if x['type'] == 'candidate' and x['job']['job_id'] == 1)
        if name == 'coherent_solver_not_invoked': candidate_change = ('solver_invoked',False)
        elif name == 'coherent_worker_receive_before_freeze': candidate_change = ('receive_ns',candidate['job']['freeze_ns']-1)
        elif name == 'coherent_negative_backend_ms': candidate_change = ('backend_ms',-1.0)
        elif name == 'coherent_foreign_backend': candidate_change = ('backend','foreign-backend')
        else: candidate_change = ('worker_instance','foreign-worker')
        field,value = candidate_change; candidate[field] = value
        if field == 'receive_ns':
            for receipt in worker:
                if receipt['type'] == 'job_received' and receipt['job']['job_id'] == 1: receipt['receive_ns'] = value
        if field == 'worker_instance':
            for reg in obs:
                if reg['type'] == 'candidate_registration' and reg['job']['job_id'] == 1: reg['worker_instance'] = value
    else: raise ValueError('unknown preregistered negative '+name)

    if job_change:
        field, delta = job_change
        def walk(x):
            if type(x) is dict:
                if x.get('schema') == 'p1-solve-job-v1' and x.get('job_id') == 1:
                    if field == 'reference': x[field][0] += delta
                    else: x[field] += delta
                    return
                for value in x.values(): walk(value)
            elif type(x) is list:
                for value in x: walk(value)
        walk(obs); walk(worker)

    if bag_changes or job_change or candidate_change or name == 'coherent_profile_stamp_alias':
        from rclpy.serialization import deserialize_message, serialize_message
        from rosidl_runtime_py.utilities import get_message
        db = root/'recorder/bag/bag_0.db3'
        connection = sqlite3.connect(db)
        changed = []; transport_map = {}
        def alias(message):
            for dim in message.layout.dim:
                if dim.label.startswith('stamp_sec:'): dim.label = 'stamp_sec:'+str(int(dim.label[10:])-1)
                elif dim.label.startswith('stamp_nanosec:'): dim.label = 'stamp_nanosec:'+str(int(dim.label[14:])+1_000_000_000)
        if name == 'coherent_profile_stamp_alias':
            for row in obs:
                if row['type'] != 'profile_version': continue
                raw = row['raw_input']; blob = bytes.fromhex(raw['cdr_hex']); message = deserialize_message(blob,get_message(raw['message_type'])); alias(message); new = serialize_message(message)
                raw.update(cdr_hex=new.hex(),cdr_sha256=C3.sha(new),cdr_bytes=len(new))
        for mid,typ,topic,data in connection.execute('SELECT messages.id, topics.type, topics.name, messages.data FROM messages JOIN topics ON messages.topic_id=topics.id').fetchall():
            if topic not in ('/p1/execution_decision','/p1/solve_job','/p1/solve_candidate','/path/reference_profile'): continue
            message = deserialize_message(data,get_message(typ)); altered = False
            if topic == '/p1/execution_decision' and message.sequence == d['sequence']:
                for key,value in bag_changes.items(): setattr(message,key,value)
                altered = bool(bag_changes)
            if job_change and topic in ('/p1/solve_job','/p1/solve_candidate'):
                job = message if topic == '/p1/solve_job' else message.job
                if job.job_id == 1:
                    field,delta = job_change
                    if field == 'reference':
                        values = list(job.reference); values[0] += delta; job.reference = values
                    else: setattr(job, 'deadline_steady_ns' if field == 'deadline_ns' else field, getattr(job,'deadline_steady_ns' if field == 'deadline_ns' else field)+delta)
                    altered = True
            if name == 'coherent_profile_stamp_alias' and topic == '/path/reference_profile': alias(message); altered = True
            if candidate_change and topic == '/p1/solve_candidate' and message.job.job_id == 1:
                field,value = candidate_change; setattr(message,'worker_receive_ns' if field == 'receive_ns' else field,value); altered = True
            if altered:
                new = serialize_message(message); connection.execute('UPDATE messages SET data=? WHERE id=?',(new,mid)); changed.append({'id':mid,'topic':topic}); transport_map[C3.sha(data)] = (C3.sha(new),len(new))
        connection.commit(); connection.close()
        if bag_changes and not any(x['topic'] == '/p1/execution_decision' for x in changed): raise ValueError('coherent Decision CDR update did not occur')
        if job_change and {x['topic'] for x in changed} != {'/p1/solve_job','/p1/solve_candidate'}: raise ValueError('coherent Job/Candidate CDR update did not occur')
        if candidate_change and {x['topic'] for x in changed} != {'/p1/solve_candidate'}: raise ValueError('coherent actual Candidate CDR update did not occur')
        tp = root/'synthetic_source/transport_source.jsonl'; transport = [json.loads(x) for x in tp.read_text().splitlines()]; fanout = 0
        for row in transport:
            if row.get('payload_sha256') in transport_map:
                row['payload_sha256'],row['serialized_bytes'] = transport_map[row['payload_sha256']]; fanout += 1
        tp.write_text(''.join(json.dumps(x,ensure_ascii=False,allow_nan=False)+'\n' for x in transport))
        if fanout != len(changed): raise ValueError('complete coherent transport SHA fanout update did not occur')
    else: changed = []
    # Writes affect this new native-copy directory only.
    obs_path.write_text(''.join(json.dumps(x,ensure_ascii=False,allow_nan=False)+'\n' for x in obs))
    worker_path.write_text(''.join(json.dumps(x,ensure_ascii=False,allow_nan=False)+'\n' for x in worker))
    wp.write_text(json.dumps(witness,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return {'coherent_stored_CDR_updates':changed,'source_files':['observer/source.jsonl','worker/source.jsonl','observer/witness.json']}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); p.add_argument('--copies',type=Path,required=True); a = p.parse_args()
    c,identity = C3.imports(); base = Path(c['original_run']); originals = {k:C3.sha(Path(v['path']).read_bytes()) for k,v in c['record_pins'].items()}
    a.copies.mkdir(); results = []
    for case in c['negative_cases']:
        name = case['name']; root = a.copies/name; root.mkdir()
        copy_pins = {}
        for key,pin in c['record_pins'].items():
            original = Path(pin['path']); target = root/original.relative_to(base) if original.is_relative_to(base) else root/'external'/key
            target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(original,target)
            copy_pins[str(target.relative_to(root))] = {'sha256':C3.sha(target.read_bytes()),'bytes':target.stat().st_size}
        write_new(root/'native_original_copy_manifest.json',copy_pins)
        try:
            mutation = mutate_native(root,name)
            s = C3.load(root); report = C3.analyze(s)
            codes = {x['code'] for x in report['issues']}
            result = {'case':name,'expected_code':case['expected_code'],'passed':not report['passed'] and case['expected_code'] in codes and 'bounded_input_or_checker_error' not in codes,'observed_codes':sorted(codes),'mutation':mutation,'report':str(root/'C3_report.json'),'original_authenticity_qualified':False}
            write_new(root/'C3_report.json',report)
        except Exception as e:
            result = {'case':name,'expected_code':case['expected_code'],'passed':False,'harness_or_parser_failure':type(e).__name__+': '+str(e)}
        write_new(root/'case_result.json',result); results.append(result)
        print(json.dumps({'case':name,'passed':result['passed'],'failure':result.get('harness_or_parser_failure'),'codes':result.get('observed_codes')},ensure_ascii=False),flush=True)
        if not result['passed']: break
    after = {k:C3.sha(Path(v['path']).read_bytes()) for k,v in c['record_pins'].items()}
    out = {'schema':'p1-C3-native-copy-negatives-v1','passed':len(results) == len(c['negative_cases']) and all(x['passed'] for x in results) and after == originals,'cases':results,'planned':len(c['negative_cases']),'completed':len(results),'original_inputs_unchanged':after == originals,'original_sha256':originals,'copies':str(a.copies),'checker_sha256':C3.sha(Path(C3.__file__).read_bytes()),**C3.FLAGS}
    write_new(a.output,out)
    return 0 if out['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
