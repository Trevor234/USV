"""Independent strict causal joins on closed current raw data; no driver imports."""
import hashlib

def need(v,w):
    if not v:raise ValueError(w)

def check(b):
    w,f,source,pub=b['witness'],b['fault'],b['observer_source'],b['publisher_source']
    def phase(e,o=None):
        a=[r for r in w['phase'] if r['event_code']==e and (o is None or r['observation_code']==o)]
        need(len(a)==1,'unique_phase:'+str(e));return a[0]
    arm,begin,overflow,fail,end,stop,invalid=[phase(e,o) for e,o in [(1,None),(2,None),(3,None),(4,None),(6,None),(5,3),(8,3)]]
    need(arm['ns']<=begin['ns']<=f['sink']['rejection_ns']<=overflow['ns']<=fail['ns']<=end['ns']<=stop['ns']<=invalid['ns']<=f['observation_ns'],'strict_first_failure_causal_order')
    roles=b['manifests'];transport=b['transport']
    def gid(role,topic):
        found=[e['gid'] for e in roles[role]['endpoints'] if e['topic']==topic and e['kind']=='publisher']
        need(len(found)==1,'unique_GID:'+topic);return found[0]
    for topic,role,rows in [('/p1/execution_decision','observer',b['stored_decision_wire']),('/p1/controlled_owner_phase','publisher',b['stored_phase'])]:
        g=gid(role,topic)
        for r in rows:
            matches=[t for t in transport if t.get('topic')==topic and t['payload_sha256']==r['wire_sha256'] and t['publisher_gid']==g]
            need(len(matches)==1,'Stored_exact_wire_owner_GID:'+topic)
    accepted=[d for d in b['stored_decisions'] if d['candidate_accepted'] and d['sequence']<f['decision_sequence']]
    need(accepted,'accepted_prefix_missing');joins=[]
    for d in accepted:
        need(d['run_id']==f['run_id'] and d['contract_hash']==f['contract_hash'],'Stored_Decision_identity')
        src=[r for r in source if r.get('type')=='decision' and r['accepted'] and r['sequence']==d['sequence']]
        physical=[r for r in pub if r.get('type')=='controlled_decision_physical_return' and r['decision_sequence']==d['sequence']]
        need(len(src)==len(physical)==1,'accepted_Source_owner_join')
        emissions=[r for r in pub if r.get('type')=='controlled_Applied_emitted' and r['applied_sequence']==physical[0]['applied_sequence']]
        need(len(emissions)==1,'accepted_Applied_emission');e=emissions[0]
        stored=[r for r in b['stored_applied'] if r['decoded']['sequence']==e['applied_sequence']]
        need(len(stored)==1 and stored[0]['decoded']==b['publisher_applied'][str(e['applied_sequence'])],'accepted_full_Stored_Applied')
        need(stored[0]['decoded']['final_n']==e['final_n'] and e['applied_publish_end_ns']<arm['ns'],'strict_Applied_before_arm')
        joins.append(dict(decision=d['sequence'],job=d['job_id'],command=d['final_n'],applied_sequence=e['applied_sequence'],Applied_before_arm_ns=arm['ns']-e['applied_publish_end_ns']))
    armed=[r for r in source if r.get('type')=='diagnostic_v1_armed_after_ack']
    need(len(armed)==1 and armed[0]['armed'],'unique_authenticated_arm')
    ar=armed[0]
    need(any(j['decision']==ar['decision_sequence'] and j['applied_sequence']==ar['applied_sequence'] for j in joins),'arm_accepted_prefix_join')
    phases=[p for p in b['stored_phase'] if p['decoded']['decision_sequence']==ar['decision_sequence'] and p['decoded']['applied_sequence']==ar['applied_sequence']]
    callbacks=[r for r in source if r.get('type')=='controlled_phase_callback' and r.get('accepted') and r.get('phase',{}).get('decision_sequence')==ar['decision_sequence']]
    need(len(phases)==len(callbacks)==1,'unique_Stored_phase_and_callback')
    p,c=phases[0],callbacks[0]
    need(c['authentication_reason']=='','actual_phase_authentication')
    rec=c['raw_input'];typed=bytes.fromhex(rec['cdr_hex']);wire=bytes.fromhex(p['wire_hex'])
    need(len(typed)==rec['cdr_bytes'] and hashlib.sha256(typed).hexdigest()==rec['cdr_sha256'],'callback_CDR_integrity')
    need(hashlib.sha256(wire).hexdigest()==p['wire_sha256'],'Stored_phase_wire_integrity')
    need(rec['publisher_gid']==gid('publisher','/p1/controlled_owner_phase') and rec['topic']=='/p1/controlled_owner_phase','callback_owner_GID')
    need(typed[:4]==wire[:4]==b'\x00\x01\x00\x00','CDR1_String_header')
    size=8+int.from_bytes(typed[4:8],'little')
    need(size>8 and size<=len(typed) and typed[size-1]==0 and 0<=len(typed)-size<=3 and 0<=len(wire)-size<=3,'bounded_String_extent')
    need(typed[:size]==wire[:size] and c['phase']==p['decoded'],'full_declared_String_payload')
    need(p['decoded']['emitted_ns']==ar['phase_emitted_ns']<=arm['ns'],'authenticated_phase_before_arm')
    return dict(passed=True,actual_accepted_prefix_joins=joins,authenticated_arm=ar,
        phase_CDR_binding=dict(callback_sha256=rec['cdr_sha256'],Stored_wire_sha256=p['wire_sha256'],
            callback_bytes=len(typed),Stored_wire_bytes=len(wire),declared_extent=size,trailing_bytes_preserved=True),
        first_failure=dict(decision=f['decision_sequence'],tick=f['tick'],job=f['job_id'],
            filler_events=f['sink']['filler_events'],depth_at_rejection=f['sink']['depth_at_rejection']),
        stopping_after_overflow_ns=stop['ns']-overflow['ns'],invalidation_after_overflow_ns=invalid['ns']-overflow['ns'],
        timing_is_observation_not_WCET=True,nonempty_pre_failure_slot_interleaving_proven=False,
        Source_extra_dropped_payload_identity='not reconstructed',stage_qualified=False,execute_qualified=False,research_conclusion=False)
