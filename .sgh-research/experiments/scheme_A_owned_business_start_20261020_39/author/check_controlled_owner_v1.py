"""Read-only complete controlled-owner publication and received-input evidence."""
from pathlib import Path
import json,sys
sys.dont_write_bytecode=True
import check_c37_owned_run_v2 as p
c36=p.c36
def ordered_phase(row,applied):
 try:
  ph=row['phase']
  return (applied['applied_publish_start_ns']<=applied['applied_publish_end_ns']
   <=ph['emitted_ns']<=row['phase_publish_start_ns']<=row['phase_publish_end_ns']
   and row['applied_publish_start_ns']==applied['applied_publish_start_ns']
   and row['applied_publish_end_ns']==applied['applied_publish_end_ns']
   and ph['applied_sequence']==applied['applied_sequence']
   and ph['command_n']==applied['final_n']
   and ph['end_ns'][1]<=applied['applied_publish_start_ns'])
 except (KeyError,TypeError):return False
def pulse_matches(row,j,a):
 try:
  return (row['job_id']==j['job_id'] and row['freeze_ns']==j['freeze_ns']
   and row['origin_ns']==j['tick_origin_ns'] and row['due_ns']==j['tick_origin_ns']+100000000
   and j['freeze_ns']<a['left_publish_start_steady_ns'] and row['due_ns']<=a['left_publish_start_steady_ns']
   <=a['right_publish_end_steady_ns']<=row['physical_return_ns']<j['deadline_ns']
   and row['actual_command_n']==a['final_n']==[0.1,0.1] and row['applied_sequence']==a['sequence'])
 except (KeyError,TypeError):return False
def analyze(run,decoded,c):
 run=Path(run);start=len(c.issues);rows=c36.lines(run/'publisher/controlled_source.jsonl')
 get=lambda kind:[r for r in rows if r.get('type')==kind]
 closed=get('controlled_owner_source_closed');created=get('controlled_owner_created')
 c.need(len(created)==len(closed)==1 and rows[0] is created[0] and rows[-1] is closed[0] and closed[0]['executor_detached'] is True,'owner_Source_closed_after_actual_executor_detach')
 terminal=closed[0];inputs=c36.load(run/'inputs.json');om=c36.load(run/'observer/owned_manifest.json');pm=c36.load(run/'publisher/owned_manifest.json')
 applied={r['message']['sequence']:r['message'] for r in decoded[c36.APPLIED]};emitted=get('controlled_Applied_emitted')
 em=c.index(emitted,lambda r:r['applied_sequence'],'owner_emitted_Applied')
 c.need(set(em)==set(applied) and terminal['Applied_emitted']==len(emitted),'whole_owner_Applied_emitted_Storage_population')
 for row in emitted:
  a=p.decode_callback({**row,'message_type':c36.APPLIED_TYPE},c,{'owner_emitted_Applied':row['applied_sequence']})
  c.need(a==applied.get(row['applied_sequence']) and row['right_end_ns']<=row['applied_publish_start_ns']<=row['applied_publish_end_ns']<=row['source_written_ns'],'owner_full_typed_Applied_and_actual_DDS_call_binding')
 phases=get('controlled_phase_emitted');stored=[c36.strict(r['message']['data']) for r in decoded['/p1/controlled_owner_phase']]
 c.need([r['phase'] for r in phases]==stored and terminal['phases_emitted']==len(phases),'whole_owner_phase_emitted_Storage_population')
 for row in phases:
  a=em.get(row['phase']['applied_sequence']);c.need(a is not None and ordered_phase(row,a),'phase_after_actual_Applied_DDS_return')
 binding=get('controlled_observer_peer_bound');c.need(len(binding)==1,'owner_actual_Observer_peer_pin')
 if len(binding)==1:
  for key,topic in [('decision','/p1/execution_decision'),('job','/p1/solve_job')]:
   e=binding[0][key];expected=[x for x in om['endpoints'] if x['kind']=='publisher' and x['topic']==topic]
   c.need(len(expected)==1 and e['endpoint']==expected[0] and e['manifest_sha256']==c36.sha(run/'observer/owned_manifest.json') and e['pid']==om['pid'] and e['process_start_ticks']==om['process_start_ticks'] and e['binary_sha256']==inputs['builds']['observer']['binary_sha256'] and e['source_bundle_sha256']==inputs['source_bundles']['observer']['sha256'] and e['pidfd_alive'] is True,'owner_actual_Observer_PID_code_GID_binding',interface=key)
 for kind,topic,countkey in [('controlled_decision_receipt','/p1/execution_decision','decision_receipts'),('controlled_job_receipt','/p1/solve_job','job_receipts')]:
  receipts=get(kind);c.need(terminal[countkey]==len(receipts),'owner_entire_received_counter_closure',topic=topic)
  expected_gid=[e['gid'] for e in om['endpoints'] if e['kind']=='publisher' and e['topic']==topic][0]
  messages=[r['message'] for r in decoded[topic]]
  for index,row in enumerate(receipts,1):
   raw=row['raw_input'];message=p.decode_callback(raw,c,{'owner_receipt':kind,'ordinal':index})
   c.need(message in messages and raw['publisher_gid']==expected_gid and raw['callback_sequence']==index and raw['topic']==topic and raw['schema']=='p1-controlled-full-cdr-receipt-v1' and raw['rmw_implementation']=='rmw_fastrtps_cpp' and raw['from_intra_process'] is False and raw['entry_steady_ns']<=row['source_written_ns']<=terminal['closed_ns'],'owner_actual_received_CDR_GID_Storage_subset',topic=topic,ordinal=index)
 pulse=get('controlled_B_pulse_physical_return');case=inputs['ordered_stage']
 c.need(len(pulse)==(1 if case=='B' else 0),'one_B_only_pulse')
 if case=='B' and len(pulse)==1:
  row=pulse[0];job=next((r['message'] for r in decoded['/p1/solve_job'] if r['message']['job_id']==row['job_id']),None)
  # Typed Job field spellings differ from the Source aliases used by the pure predicate.
  j={**job,'freeze_ns':job['freeze_steady_ns'],'tick_origin_ns':job['tick_origin_steady_ns'],'deadline_ns':job['deadline_steady_ns']} if job else None
  c.need(j is not None and row['applied_sequence'] in applied and pulse_matches(row,j,applied[row['applied_sequence']]),'B_actual_single_pulse_matches_frozen_Job_and_unchanged_deadline')
  c.need(terminal['pulse_fired'] is True and terminal['pulse_restored'] is True,'B_pulse_and_after_decision_restore_completed')
 return {'passed':len(c.issues)==start,'Applied_emitted':len(emitted),'phases_emitted':len(phases),'decision_received':len(get('controlled_decision_receipt')),'Job_received':len(get('controlled_job_receipt')),'all_subscriber_delivery_claimed':False,'stage_qualified':False}
