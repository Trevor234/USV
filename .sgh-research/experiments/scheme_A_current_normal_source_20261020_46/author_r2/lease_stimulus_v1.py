"""Authenticated callback-gate stimulus; stop authority stays in ordinary_supervision."""
from pathlib import Path
import hashlib,json,time

def need(v,w):
    if not v:raise ValueError(w)

def validate_ack(command,row,digest):
    action=command['action'];gate=row['gate']
    need(action in ('pause','resume'),'known_gate_action')
    need(row['type']==('diagnostic_c38_gate_paused' if action=='pause' else 'diagnostic_c38_gate_resumed')
        and row['request_sha256']==digest and row['gate_interface']=='worker','actual_gate_ACK_binding')
    for key in ['run_id','boot_id','driver_pid','driver_start_ticks','driver_tool_sha256','owner_manifest_sha256']:
        need(type(gate[key]) is type(command[key]) and gate[key]==command[key],'gate_identity:'+key)
    need(gate['state']==('paused' if action=='pause' else 'resumed')
        and row['group_registered'] is (action=='resume') and gate['ttl_ns']==3500000000
        and gate['deadline_ns']==gate['paused_ns']+gate['ttl_ns'],'actual_gate_state_and_original_TTL')
    completed=gate['paused_ns'] if action=='pause' else gate['resumed_ns']
    need(command['issued_ns']<=completed<=row['checked_ns'] and row['checked_ns']<gate['deadline_ns'],'actual_gate_completion_bounds')
    need(command['seq']==(1 if action=='pause' else 2) and command['stage_qualified'] is False,'gate_sequence_and_scope')
    return row

def make_command(action,*,run,boot,identity,driver_sha,owner_manifest_sha,now_ns):
    need(action in ('pause','resume'),'known_gate_action')
    return dict(schema='p1-C3.8-applied-gate-v1',action=action,run_id=run,boot_id=boot,
        driver_pid=identity['pid'],driver_start_ticks=identity['start_ticks'],driver_tool_sha256=driver_sha,
        owner_manifest_sha256=owner_manifest_sha,issued_ns=now_ns,seq=1 if action=='pause' else 2,stage_qualified=False)

def accepted_prefix(source,publisher):
    accepted={r['sequence']:r for r in source if r.get('type')=='decision' and r['accepted']}
    for row in source:
        if row.get('type')!='controlled_phase_callback' or row.get('accepted') is not True:continue
        phase=row['phase'];decision=accepted.get(phase['decision_sequence'])
        if decision is None:continue
        emitted=[r for r in publisher if r.get('type')=='controlled_Applied_emitted' and r['applied_sequence']==phase['applied_sequence']]
        if emitted:
            need(len(emitted)==1 and row['authentication_reason']=='','unique_authenticated_accepted_prefix')
            return dict(decision=decision,phase_callback=row,Applied=emitted[0])
    return None

def gate(action,root,*,spin,bound,identity,boot,driver_sha,owner_manifest_sha,create_only_json,overall_deadline_ns):
    root=Path(root);run=json.loads((root/'expected_witness_header.json').read_bytes())['run_id']
    command=make_command(action,run=run,boot=boot,identity=identity,driver_sha=driver_sha,
        owner_manifest_sha=owner_manifest_sha,now_ns=time.monotonic_ns())
    path=root/('c38_'+action+'_request.json');create_only_json(path,command)
    digest=hashlib.sha256(path.read_bytes()).hexdigest();deadline=min(time.monotonic_ns()+1000000000,overall_deadline_ns-15000000000)
    target='diagnostic_c38_gate_paused' if action=='pause' else 'diagnostic_c38_gate_resumed'
    while time.monotonic_ns()<deadline:
        bound();source=[json.loads(x) for x in (root/'observer/source.jsonl').read_bytes().splitlines(keepends=True) if x.endswith(b'\n')]
        need(not any(r.get('type') in ['diagnostic_c38_gate_timeout','diagnostic_c38_gate_rejected'] for r in source),'gate_not_failed_or_timed_out')
        found=[r for r in source if r.get('type')==target]
        if found:
            need(len(found)==1,'unique_actual_gate_ACK')
            ack=validate_ack(command,found[0],digest)
            return dict(command=command,command_sha256=digest,ack=ack,driver_observed_ns=time.monotonic_ns())
        spin(.005)
    raise RuntimeError('lease stimulus gate ACK deadline:'+action)

def prepare(root,*,spin,bound,identity,boot,driver_sha,owner_manifest_sha,create_only_json,overall_deadline_ns):
    root=Path(root);started=time.monotonic_ns();deadline=min(started+4000000000,overall_deadline_ns-15000000000)
    def rows(p):return [json.loads(x) for x in p.read_bytes().splitlines(keepends=True) if x.endswith(b'\n')]
    prefix=None
    while time.monotonic_ns()<deadline:
        bound();source=rows(root/'observer/source.jsonl')
        need(not any(r.get('type')=='worker_unusable_transition' for r in source),'Worker_terminal_before_stimulus')
        prefix=accepted_prefix(source,rows(root/'publisher/controlled_source.jsonl'))
        if prefix:break
        spin(.005)
    need(prefix is not None,'lease_stimulus_healthy_prefix_deadline')
    create_only_json(root/'V2_prefix_observation.json',prefix)
    pause=gate('pause',root,spin=spin,bound=bound,identity=identity,boot=boot,driver_sha=driver_sha,
        owner_manifest_sha=owner_manifest_sha,create_only_json=create_only_json,overall_deadline_ns=overall_deadline_ns)
    source=rows(root/'observer/source.jsonl')
    need(not any(r.get('type')=='worker_unusable_transition' for r in source),'terminal_observed_before_monitor_entry')
    report=dict(schema='ordinary-lease-stimulus/v1',started_ns=started,ready_for_monitor_ns=time.monotonic_ns(),
        prefix_decision_sequence=prefix['decision']['sequence'],prefix_Applied_sequence=prefix['Applied']['applied_sequence'],pause=pause,
        delayed_900ms_observation_used=False,process_pause_used=False,ordinary_monitor_must_be_next=True,
        stage_qualified=False,execute_qualified=False,research_conclusion=False)
    create_only_json(root/'lease_stimulus.json',report)
    return report

def resume_after_stop(root,*,spin,bound,identity,boot,driver_sha,owner_manifest_sha,create_only_json,overall_deadline_ns):
    root=Path(root)
    resume=gate('resume',root,spin=spin,bound=bound,identity=identity,boot=boot,driver_sha=driver_sha,
        owner_manifest_sha=owner_manifest_sha,create_only_json=create_only_json,overall_deadline_ns=overall_deadline_ns)
    deadline=min(time.monotonic_ns()+1000000000,overall_deadline_ns-15000000000)
    while time.monotonic_ns()<deadline:
        bound();source=[json.loads(x) for x in (root/'observer/source.jsonl').read_bytes().splitlines(keepends=True) if x.endswith(b'\n')]
        callbacks=[r for r in source if r.get('type')=='adapter_worker_callback' and r['interface']=='capability'
            and r['entry_ns']>=resume['ack']['gate']['resumed_ns'] and r['authentication_reason']=='worker_process_exited']
        if callbacks:
            need(all(not r['semantic_callback_invoked'] and r['raw_input'] is None and r['before']==r['after']
                and r['after']['worker_unusable'] for r in callbacks),'post_exit_callback_must_not_change_business')
            proof=dict(schema='ordinary-lease-post-stop-resume/v1',resume=resume,
                post_exit_capability_callbacks_observed=len(callbacks),callback_sequences=[r['callback_sequence'] for r in callbacks],
                same_run_revival=False,finished_ns=time.monotonic_ns(),deadline_ns=deadline,
                full_old_payload_serialization_claimed=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
            create_only_json(root/'lease_resume_after_stop.json',proof);return proof
        spin(.005)
    raise RuntimeError('lease stimulus resumed post-exit callback deadline')
