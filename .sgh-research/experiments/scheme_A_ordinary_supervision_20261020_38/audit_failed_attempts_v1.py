"""Independent read-only audit of three attempts; never promotes ordinary supervision."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
PINS={}
def raw(p):
    p=Path(p);b=p.read_bytes();v=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
    assert str(p) not in PINS or PINS[str(p)]==v,'changed input:'+str(p)
    PINS[str(p)]=v;return b
def load(p):return json.loads(raw(p))
def rows(p):
    b=raw(p);assert b.endswith(b'\n');return [json.loads(v) for v in b.splitlines()]
def main():
    scopes=[('author','ordinary_active_01','ordinary_terminal_notification_deadline'),
            ('author_r2','ordinary_active_r2_02','deadline: Recorder ready before Observer'),
            ('author_r3','ordinary_active_r3_03','parameter service absent /mpc_controller_node')]
    attempts=[]
    for author,run,error in scopes:
        R=D/author/'runs'/run;population=sorted(str(p.relative_to(R)) for p in R.rglob('*') if p.is_file())
        for name in population:raw(R/name)
        result=load(R/'result.json');ledger=rows(R/'owned_process_ledger.jsonl')
        assert result['error']==error and result['passed'] is False and not result['ordinary_supervision_case_completed']
        assert result['cleanup_complete'] and result['cleanup_within_budget']
        assert not any(e['type'] in ['ordinary_notice_authenticated','ordinary_worker_stop_dispatched'] for e in ledger)
        assert not any(e.get('signal')==19 for e in ledger)
        spawns=[r for r in ledger if r['type']=='spawn'];closes=[r for r in ledger if r['type']=='cleanup_result']
        assert len(spawns)==len(closes) and all(e['cleanup_complete'] and not e['remaining_members'] for e in closes)
        assert not ledger[-1]['unverified_children'] and not ledger[-1]['unexpected_descendants'] and not ledger[-1]['cleanup_failed']
        worker=rows(R/'worker/source.jsonl');job_rows=[r for r in worker if r.get('type') in ['job','candidate','diagnostic_v2_pre_native_enter']]
        assert not job_rows,'ordinary stimulus unexpectedly entered'
        pub=rows(R/'publisher/controlled_source.jsonl');applied=[r for r in pub if r['type']=='controlled_Applied_emitted']
        assert all(r['final_n']==[0.0,0.0] for r in applied),'unexplained nonzero controlled output'
        dbs=list((R/'recorder/bag').glob('*.db3'));assert len(dbs)==1
        db=sqlite3.connect(dbs[0].resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
            count=db.execute('select count(*) from messages').fetchone()[0]
            by={n:c for n,c in db.execute('select t.name,count(*) from messages m join topics t on t.id=m.topic_id group by t.id')}
        finally:db.close()
        note=dict(run_id=run,error=error,ordinary_dispatch_executed=False,Worker_stimulus_entered=False,
            Worker_job_rows=0,released=result['released'],role_returncodes=result['owned_role_returncodes'],
            all_owned_groups_empty=True,close_errors_preserved=result['close_errors'],Stored_messages=count,
            SQL_integrity='ok',SQL_topic_counts=by,normal_Worker_Source_claim=result['Worker_normal_Source_qualified'],
            positive_ordinary_supervision_qualified=False)
        if author=='author':
            source=rows(R/'observer/source.jsonl');assert not any(r.get('type') in ['job','worker_unusable_transition','controlled_phase_callback'] for r in source)
            assert all(r['capability']['active_job']==r['capability']['completed_jobs']==0 for r in source if r['type']=='capability_admission')
            refused=[r for r in pub if r['type']=='controlled_phase_refused'];assert len(refused)==1 and refused[0]['reason']=='late_for_unchanged_150ms_freeze_budget'
            d=next(r for r in source if r.get('type')=='decision' and r['sequence']==refused[0]['decision_sequence'])
            release=load(R/'release_publication_observation.json')['events'][-1]
            bind=next(r for r in pub if r['type']=='controlled_observer_peer_bound')
            assert refused[0]['applied_publish_end_ns']-d['planned_ns']>=150000000
            note.update(first_phase_applied_delay_ns=refused[0]['applied_publish_end_ns']-d['planned_ns'],
                release_call_ns=release['call_end_steady_ns']-release['call_start_steady_ns'],
                release_call_to_native_bind_ns=bind['source_written_ns']-release['call_start_steady_ns'],
                queued_decision_bound_rejections=sum(r.get('reason')=='decision_queue_bound' for r in pub),
                pending_latch_is_inference_from_pinned_code_and_queue_evidence=True)
        else:assert not result['released'] and not applied and not any(e['name']=='observer' for e in spawns)
        attempts.append(note)
        assert population==sorted(str(p.relative_to(R)) for p in R.rglob('*') if p.is_file())
    for freeze in ['first_run_failure_freeze_v1.json','second_run_failure_freeze_v1.json']:
        data=load(D/'postrun'/freeze);root=Path(data.get('first_run',data.get('run')))
        for r in data['files']:
            b=raw(root/r['relative_path']);assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
    for suffix in ['', '_r2', '_r3']:
        lock=load(D/'preflight'/('prerun_source_lock'+suffix+'_v1.json'))
        for p,item in lock['files'].items():
            b=raw(p);assert dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())==item
        launch=load(D/'postrun'/('launch_'+scopes[['','_r2','_r3'].index(suffix)][1]+'_v1.json'))
        assert launch['returncode']==2 and launch['inputs_unchanged'] and not launch['external_timeout_triggered']
    before=dict(PINS)
    for p in before:raw(p)
    assert PINS==before
    report=dict(schema='ordinary-supervision-failed-attempts-audit/v1',audit_passed=True,
        passed_scope='failure explanation, original evidence/source stability and owned resource closure only',
        ordinary_supervision_actual_passed=False,positive_ordinary_audit_executed=False,
        actual_raw_success_auditor_negative_checks_executed=0,attempts=attempts,
        input_sha256_before=before,input_sha256_after=PINS,stage_qualified=False,execute_qualified=False,research_conclusion=False)
    with (D/'postrun/failed_attempts_audit_v1.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True)
    print(json.dumps(dict(audit_passed=True,ordinary_supervision_actual_passed=False,attempts=len(attempts),inputs=len(PINS))))
if __name__=='__main__':main()
