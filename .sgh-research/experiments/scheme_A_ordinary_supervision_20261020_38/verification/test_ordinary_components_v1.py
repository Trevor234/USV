"""Frozen Source cause tests and seeded-auth real Linux child dispatch; no ROS."""
from copy import deepcopy,copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(D/'author'),str(D/'author/runtime')]
from ordinary_supervision_v1 import validate_notice,DispatchOnce
from owned_process_supervisor import Supervisor,sha256_file
def need(v,w):
    if not v:raise AssertionError(w)
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def load(p):return json.loads(Path(p).read_bytes())
def main():
    C=load(D/'author/pair_wakeup_contract_v1.json');pure=[];negative=[];children=[];inputs={}
    def reject(name,fn):
        try:fn()
        except ValueError as e:negative.append(dict(case=name,reason=str(e)))
        else:raise AssertionError('invalid component accepted:'+name)
    for case,run in [('active_watchdog','v2_active_r3_05'),('worker_capability_expired','v2_lease_r3_04')]:
        P=D.parent/'scheme_A_V2_watchdog_lease_20261019_35/author_r3/runs'/run
        for leaf in ['observer/source.jsonl','observer/owned_manifest.json','worker/owned_manifest.json','result.json']:
            inputs[str(P/leaf)]=pin(P/leaf)
        source=[json.loads(x) for x in (P/'observer/source.jsonl').read_bytes().splitlines()]
        om,wm,result=[load(P/leaf) for leaf in ['observer/owned_manifest.json','worker/owned_manifest.json','result.json']]
        expected=dict(run_id=om['run_id'],boot_id=om['boot_id'],observer_pid=om['pid'],contract_sha256=om['contract_sha256'],
            worker_pid=wm['pid'],worker_instance=wm['worker_instance'],nominal_hash=wm['nominal_hash'],prepare_start_ns=result['prepare_start_ns'])
        notice=validate_notice(source,expected,C);need(notice['cause']==case,'frozen Source dispatch')
        pure.append(dict(case=case,actual_frozen_Source_cause=True,action=notice['action']))
        for key,value in [('run_id','wrong'),('boot_id','wrong'),('observer_pid',1),('worker_pid',True),
                          ('worker_instance','wrong'),('nominal_hash','0'*64),('prepare_start_ns',notice['terminal']['check_ns']+1)]:
            bad=dict(expected);bad[key]=value
            reject(case+':context_'+key,lambda:validate_notice(source,bad,C))
        for badcase in ['unknown_cause','duplicate_terminal','missing_link','pending_not_invalidated','capability_foreign_identity','wrong_causal_age','renewal_order','wrong_receipt_timeout']:
            bad=deepcopy(source);terminal=next(r for r in bad if r.get('type')=='worker_unusable_transition')
            if badcase=='unknown_cause':terminal['reason']='unexpected:active_watchdog'
            elif badcase=='duplicate_terminal':bad.append(deepcopy(terminal))
            elif badcase=='missing_link':bad=[r for r in bad if r.get('type')!='legacy_ready_invalidated']
            elif badcase=='pending_not_invalidated':terminal['pending_after']=True
            elif badcase=='capability_foreign_identity':next(r for r in bad if r.get('type')=='capability_admission' and r['renewed'])['capability']['worker_instance']='foreign'
            elif badcase=='wrong_causal_age':
                opposite='worker_capability_expired' if case=='active_watchdog' else 'active_watchdog'
                terminal['reason']='legacy_ready_invalidated:worker_unusable:'+opposite
                link=next(r for r in bad if r.get('type')=='legacy_ready_invalidated' and r['check_ns']==terminal['check_ns'])
                link['reason']='worker_unusable:'+opposite
            elif badcase=='renewal_order':
                indices=[i for i,r in enumerate(bad) if r.get('type')=='capability_admission' and r['renewed']]
                bad[indices[0]],bad[indices[1]]=bad[indices[1]],bad[indices[0]]
            else:terminal['capability_timeout_ns']+=1
            reject(case+':'+badcase,lambda:validate_notice(bad,expected,C))
    exe=Path('/usr/bin/python3').resolve()
    for cause in ['active_watchdog','worker_capability_expired']:
        root=D/'component_runs'/cause;root.mkdir();ready=root/'ready'
        code='import signal,time,pathlib,sys\ndef done(sig,frame):\n sys.exit(0)\n'
        code+='signal.signal(signal.SIGINT,done)\nsignal.signal(signal.SIGTERM,done)\n'
        code+='pathlib.Path('+repr(str(ready))+').write_text("ready")\ntime.sleep(20)\n'
        sup=Supervisor(root)
        try:
            item=sup.spawn('worker',[str(exe),'-c',code],dict(os.environ),exe,sha256_file(exe))
            until=time.monotonic()+2
            while not ready.exists() and time.monotonic()<until:time.sleep(.005)
            need(ready.exists(),'unit child ready')
            manifest=dict(role='worker',run_id='seeded-unit-'+cause,boot_id=sup.boot,contract_sha256='a'*64,
                worker_instance='unit-'+cause,pid=item.identity['pid'],process_start_ticks=item.identity['start_ticks'],
                pgid=item.identity['pgid'],sid=item.identity['sid'],exe=item.identity['exe'],binary_sha256=item.identity['exe_sha256'])
            current=dict(manifest=manifest,actual=dict(item.identity))
            notice=dict(cause=cause,action='stop_registered_Worker',terminal=dict(worker_pid=manifest['pid'],
                worker_instance=manifest['worker_instance'],check_ns=time.monotonic_ns()),
                binding={k:manifest[k] for k in ['run_id','boot_id','contract_sha256','worker_instance']})
            notice['binding']['worker_pid']=manifest['pid']
            for badcase in ['foreign_start_ticks','foreign_instance','foreign_run','foreign_boot','unregistered_object','unknown_action']:
                auth=deepcopy(current);n=deepcopy(notice);target=item
                if badcase=='foreign_start_ticks':auth['actual']['start_ticks']+=1
                elif badcase=='foreign_instance':n['terminal']['worker_instance']='foreign'
                elif badcase=='foreign_run':n['binding']['run_id']='foreign'
                elif badcase=='foreign_boot':auth['manifest']['boot_id']='foreign'
                elif badcase=='unregistered_object':target=copy(item)
                else:n['action']='signal_arbitrary_group'
                reject(cause+':dispatch_'+badcase,lambda:DispatchOnce().run(sup=sup,item=target,notice=n,current_worker=auth,contract=C))
                need(not any(r['type']=='signal_call_result' for r in sup.memory_tail),'rejected grant caused signal')
            once=DispatchOnce();cleanup=once.run(sup=sup,item=item,notice=notice,current_worker=current,contract=C)
            calls=[r for r in sup.memory_tail if r['type']=='signal_call_result']
            need([r['signal'] for r in calls]==[2] and cleanup['returncode']==0 and cleanup['cleanup_complete'],'ordinary real SIGINT exit')
            count=len(calls)
            reject(cause+':replayed_dispatch',lambda:once.run(sup=sup,item=item,notice=notice,current_worker=current,contract=C))
            need(len([r for r in sup.memory_tail if r['type']=='signal_call_result'])==count,'replay emitted signal')
            children.append(dict(cause=cause,real_Linux_child=True,ROS_node=False,Source_auth_context_seeded=True,
                actual_signals=[r['signal'] for r in calls],returncode=cleanup['returncode'],cleanup_complete=True,
                diagnostic_process_pause=False,dispatch_key=once.key))
        finally:
            for item in sup.owned.values():
                if item.cleanup is None:sup.stop(item,.5,1,1)
            sup.close()
    after={p:pin(p) for p in inputs};need(after==inputs,'historical component evidence changed')
    report=dict(passed=True,frozen_Source_positive_causes=pure,negative_cases=negative,real_owned_child_cases=children,
        negative_count=len(negative),input_sha256_before=inputs,input_sha256_after=after,
        SourceCursor_and_Supervisor_component_reused_from_batch36=True,new_ROS_experiments=0,
        script_sha256=pin(__file__)['sha256'],policy_pin=pin(D/'author/ordinary_supervision_v1.py'),
        stage_qualified=False,execute_qualified=False,research_conclusion=False)
    with (D/'verification/ordinary_components_v1.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True)
    print(json.dumps(dict(passed=True,negative_count=len(negative),real_owned_children=len(children),Source_causes=len(pure))))
if __name__=='__main__':
    try:main()
    except BaseException as e:
        with (D/'verification/ordinary_components_failure_v1.json').open('x') as f:json.dump(dict(passed=False,error=repr(e),traceback=traceback.format_exc()),f,indent=2)
        raise
