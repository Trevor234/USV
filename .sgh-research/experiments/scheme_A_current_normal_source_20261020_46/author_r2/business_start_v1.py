"""Owned Source prerequisites -> create-only business start -> actual Observer ACK."""
from pathlib import Path
import hashlib
import time
from supervision_bridge_v1 import SourceCursor
POLICY='owned-prepare-before-business-v1'
def need(v,w):
    if not v:raise ValueError(w)
def start(root,*,roles,authenticate,source_fd_matches,create_only_json,spin,bound,driver_identity,
          driver_sha,parameter_queries_completed_ns,overall_deadline_ns):
    root=Path(root);om,pm=roles['observer']['manifest'],roles['publisher']['manifest']
    source=root/'observer/source.jsonl';owner_source=root/'publisher/controlled_source.jsonl'
    pub_view={**roles['publisher'],'manifest':{**pm,'source_fd':pm['controlled_source_fd']}}
    source_fd_matches(roles['observer'],source);source_fd_matches(pub_view,owner_source)
    observer=SourceCursor(source,om['source_fd']);publisher=SourceCursor(owner_source,pm['controlled_source_fd'])
    deadline=min(time.monotonic_ns()+4_000_000_000,overall_deadline_ns-15_000_000_000)
    try:
        ready=initial=binding=None
        while time.monotonic_ns()<deadline:
            bound();o=observer.poll();p=publisher.poll()
            need(not any(r.get('type') in ['decision','job','business_start_authorized','business_threads_started'] for r in o),'business observed before owned start')
            starts=[r for r in o if r.get('type')=='startup'];need(len(starts)==1,'unique gated Observer startup')
            need(starts[0]['pid']==om['pid'] and starts[0]['run_id']==om['run_id'] and starts[0]['boot']==om['boot_id'],'actual gated Source identity')
            candidates=[r for r in p if r.get('type')=='controlled_observer_peer_bound']
            zeros=[r for r in p if r.get('type')=='controlled_Applied_emitted' and r['control_source']=='controlled_initial_zero']
            readings=[r for r in o if r.get('type')=='legacy_ready']
            if candidates and zeros and readings:
                need(len(candidates)==len(zeros)==len(readings)==1,'unique actual initial prerequisites')
                binding,initial,ready=candidates[0],zeros[0],readings[0]['readiness'];break
            spin(.005)
        need(binding is not None and ready is not None,'owned business start prerequisite deadline')
        for key,topic in [('decision','/p1/execution_decision'),('job','/p1/solve_job')]:
            pin=binding[key]
            need(pin['manifest_sha256']==roles['observer']['sha256'] and pin['pid']==om['pid']
                 and pin['process_start_ticks']==om['process_start_ticks'] and pin['run_id']==om['run_id']
                 and pin['binary_sha256']==om['binary_sha256'] and pin['source_bundle_sha256']==om['source_bundle_sha256']
                 and pin['pidfd_alive'] is True and pin['endpoint']['topic']==topic,'actual Publisher binding:'+key)
        seq=initial['applied_sequence'];need(initial['final_n']==[0.0,0.0] and seq>0 and ready['measurement_eligible'] is True
            and ready['anchor_sequence']==[seq,seq] and ready['anchor_n']==[0.0,0.0] and all(ready['anchor_known']), 'actual initial zero joined readiness')
        for name in ['publisher','worker','observer']:
            current=authenticate(name);need(current['sha256']==roles[name]['sha256'],'business current manifest changed:'+name)
        source_fd_matches(roles['observer'],source);source_fd_matches(pub_view,owner_source);observer.verify();publisher.verify()
        issued=time.monotonic_ns()
        need(parameter_queries_completed_ns<=issued,'live parameters completed before start')
        command=dict(schema='p1-owned-business-start-v1',run_id=om['run_id'],boot_id=om['boot_id'],contract_sha256=om['contract_sha256'],
            driver_pid=driver_identity['pid'],driver_start_ticks=driver_identity['start_ticks'],driver_tool_sha256=driver_sha,
            observer_manifest_sha256=roles['observer']['sha256'],publisher_manifest_sha256=roles['publisher']['sha256'],
            issued_ns=issued,seq=1,initial_applied_sequence=seq,publisher_bound_ns=binding['source_written_ns'],
            version=ready['version'],stage_qualified=False,execute_qualified=False)
        path=root/'business_start_request.json';before=time.monotonic_ns();create_only_json(path,command);after=time.monotonic_ns()
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        # The only writer is create-only. A duplicate cannot replace the request.
        refused=False
        try:create_only_json(path,command)
        except FileExistsError:refused=True
        need(refused and hashlib.sha256(path.read_bytes()).hexdigest()==digest,'business duplicate create-only request')
        while time.monotonic_ns()<deadline:
            bound();o=observer.poll()
            accepted=[r for r in o if r.get('type')=='business_start_authorized']
            threads=[r for r in o if r.get('type')=='business_threads_started']
            failed=[r for r in o if r.get('type')=='business_start_closed_before_tick']
            need(not failed,'Observer rejected business request')
            if accepted and threads:
                need(len(accepted)==len(threads)==1 and accepted[0]['request_sha256']==digest
                    and accepted[0]['decision_sequence_before']==accepted[0]['job_id_before']==0
                    and accepted[0]['physical_publisher_endpoints']==0,'actual business authorization ACK')
                proof=dict(schema='owned-business-start-observation/v1',policy=POLICY,run_id=om['run_id'],
                    Publisher_bound_event=binding,initial_zero_Applied=initial,LegacyReady=ready,
                    command_sha256=digest,create_call_start_ns=before,create_call_end_ns=after,
                    duplicate_create_rejected=True,Observer_authorized=accepted[0],business_threads_started=threads[0],
                    preparation_complete_before_start=True,driver_live_parameters_completed_ns=parameter_queries_completed_ns,original_job_deadline_unchanged=True,
                    stage_qualified=False,execute_qualified=False,research_conclusion=False)
                create_only_json(root/'business_start_observation.json',proof);return proof
            spin(.005)
        raise ValueError('business start actual ACK deadline')
    finally:observer.close();publisher.close()
