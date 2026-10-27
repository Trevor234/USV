"""Two real, controlled Python process-group tests; no ROS or USV launch."""
from pathlib import Path
import os,sys,time,json,hashlib

CHILD='''from pathlib import Path
import sys,os,time,json,signal,hashlib
R=Path(sys.argv[1]);D=Path(sys.argv[2]);count=int(sys.argv[3]);sys.path.insert(0,str(R))
from owned_process_supervisor import Supervisor
py=Path('/usr/bin/python3').resolve();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
signal.signal(signal.SIGINT,lambda *_:None)
sup=Supervisor(D);deadline=time.monotonic()+25
try:
    for role in ('regulator','worker','fixture','recorder')[:count]:
        sup.spawn(role,[str(py),'-B','-c','import time; time.sleep(20)'],dict(os.environ),py,sha(py))
    with (D/'ready.json').open('x') as f:json.dump({'pid':os.getpid(),'count':count},f)
    # Reap these direct children without changing the frozen authorization ledger.
    while time.monotonic()<deadline:
        alive=any(v.process.poll() is None for v in sup.owned.values())
        if not alive and (D/'recovery_done').exists():break
        time.sleep(.02)
finally:
    for item in sup.owned.values():sup.stop(item,.5,1,1)
    sup.close()
'''

def run(A,R):
    sys.path.insert(0,str(R))
    from owned_process_supervisor import Supervisor,boot_id
    from cleanup_C0_inner import recover
    from run_r5_diag_validation import host_preflight
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    py=Path('/usr/bin/python3').resolve();root=A/'live_inner_recovery';root.mkdir()
    driver=root/'inner_driver.py'
    with driver.open('x') as f:f.write(CHILD)
    S=root/'outer';S.mkdir();sup=Supervisor(S)
    expected={r:{'exe':str(py),'sha256':sha(py)} for r in ('regulator','worker','fixture','recorder')}
    cases=[];failure=None;host_before=host_preflight()
    def event(kind,**details):
        sup.event(kind,**details)
        return not sup.evidence_failed
    try:
        for name,count in (('all_four_groups',4),('missing_role_known_subset',3)):
            D=root/name;D.mkdir();item=None;report=None
            try:
                item=sup.spawn(name,[str(py),'-B',str(driver),str(R),str(D),str(count)],dict(os.environ),py,sha(py))
                deadline=time.monotonic()+5
                while not (D/'ready.json').exists() and time.monotonic()<deadline:
                    assert item.process.poll() is None
                    time.sleep(.02)
                assert json.loads((D/'ready.json').read_text())=={'pid':item.process.pid,'count':count}
                report=recover(D/'owned_process_ledger.jsonl',expected,boot_id(),runner_pid=item.process.pid,event=event)
                assert report['group_cleanup_complete'] is True,report
                assert report['cleanup_complete'] is (count==4) and report['evidence_complete'] is (count==4),report
                assert len(report['signals'])==count and all(v['signal']==2 for v in report['signals']),report
                assert set(report['roles'])==set(tuple(expected)[:count]),report
                with (D/'recovery_done').open('x') as f:f.write('done')
                deadline=time.monotonic()+5
                while item.process.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                cleanup=sup.stop(item,.5,1,1)
                assert cleanup['cleanup_complete'] and cleanup['returncode']==0,cleanup
                cases.append({'name':name,'real_spawned_inner_groups':count,'report':report,'outer_cleanup':cleanup,'passed':True})
            finally:
                if item is not None and item.cleanup is None:
                    recovery=recover(D/'owned_process_ledger.jsonl',expected,boot_id(),runner_pid=item.process.pid,event=event)
                    event('live_test_exception_recovery',report=recovery)
                    if not (D/'recovery_done').exists():
                        with (D/'recovery_done').open('x') as f:f.write('finally')
                    sup.stop(item,2,1,1)
    except BaseException as error:failure=repr(error)
    finally:
        for item in sup.owned.values():
            if item.cleanup is None:sup.stop(item,2,1,1)
        sup.close()
    result={'schema':'p1-C0-inner-recovery-live-tests-v1','cases':cases,'count':len(cases),'failure':failure,
            'passed':failure is None and len(cases)==2 and not sup.evidence_failed and not sup.cleanup_failed,
            'host_before':host_before,'host_after':host_preflight(),'supervision_evidence_complete':not sup.evidence_failed,
            'cleanup_complete':not sup.cleanup_failed,'actual_inner_group_count':7,'ros_nodes_started':False,
            'C0_run':False,'R5_run':False,'physical_execute':False}
    with (A/'live_inner_recovery_results.json').open('x') as f:json.dump(result,f,indent=2)
    return result
