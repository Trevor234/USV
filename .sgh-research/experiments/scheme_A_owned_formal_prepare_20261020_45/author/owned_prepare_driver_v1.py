#!/usr/bin/env python3
"""Bounded owned four-role no_output preparation; no ROS participant in driver."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode=True
A=Path(__file__).resolve().parent
sys.path.insert(0,str(A/'python'))
from formal_prepare_contract import load_preparation_contract


def encoded(value):return (json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def pin(path):
    path=Path(path);raw=path.read_bytes();return {'bytes':len(raw),'sha256':digest(raw)}
def read(path):return json.loads(Path(path).read_bytes())


def publish(path,value):
    """Same Linux no-replace primitive as the inspected native create-only helper."""
    path=Path(path);assert path.is_absolute() and not path.exists() and not path.is_symlink()
    parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    temp='.'+path.name+'.tmp.'+str(os.getpid())+'.'+str(time.monotonic_ns())
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
    visible=False
    try:
        raw=encoded(value);done=0
        while done<len(raw):done+=os.write(fd,raw[done:])
        os.fsync(fd)
        libc=ctypes.CDLL(None,use_errno=True)
        fn=libc.renameat2;fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
        if fn(parent,os.fsencode(temp),parent,os.fsencode(path.name),1)!=0:raise OSError(ctypes.get_errno(),'create-only renameat2')
        visible=True;os.fsync(parent)
    finally:
        os.close(fd)
        if not visible:
            try:os.unlink(temp,dir_fd=parent)
            except FileNotFoundError:pass
        os.close(parent)


def process(pid):
    root=Path('/proc')/str(pid);raw=(root/'stat').read_text();fields=raw[raw.rfind(')')+1:].split()
    assert fields[0] not in ['Z','X']
    return {'pid':pid,'process_start_ticks':int(fields[19]),'pgid':int(fields[2]),'sid':int(fields[3]),
            'exe':os.readlink(root/'exe'),'binary_sha256':pin(root/'exe')['sha256'],
            'argv':[v.decode() for v in (root/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')]}


def verify_bundle(record):
    bpin=record['source_bundle'];assert pin(bpin['path'])['sha256']==bpin['sha256']
    bundle=read(bpin['path']);rows=bundle['files'];rows=rows.values() if type(rows) is dict else rows
    for row in rows:
        assert all(pin(row['path'])[k]==row[k] for k in ['bytes','sha256'])
    assert pin(record['binary'])['sha256']==record['binary_sha256']


def peer_pin(manifest_path,m):
    keys=['pid','process_start_ticks','exe','binary_sha256','source_bundle_sha256','effective_parameters_sha256']
    return {**{k:m[k] for k in keys},'manifest_path':str(manifest_path),'manifest_sha256':pin(manifest_path)['sha256']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--registration',type=Path,required=True);args=parser.parse_args()
    reg=read(args.registration)
    assert reg['schema']=='formal-owned-prepare-run-v1' and reg['physical_execute_release_enabled'] is False
    assert os.environ['ROS_DOMAIN_ID']==str(reg['domain_id']) and os.environ['RMW_IMPLEMENTATION']=='rmw_fastrtps_cpp'
    assert pin(reg['registry'])['sha256']==reg['registry_sha256']
    registry=read(reg['registry']);assert registry['driver_tool_sha256']==pin(__file__)['sha256']
    for row in registry['roles'].values():verify_bundle(row)
    config=load_preparation_contract(reg['contract'],reg['contract_sha256'],mode='no_output')
    assert pin(reg['topics'])['sha256']==reg['topics_sha256']
    assert reg['max_seconds']==35 and reg['prepared_hold_seconds']==1
    out=Path(reg['output']);assert out.is_absolute() and out.parent==A.parent/'runs';out.mkdir()
    run=reg['run_id'];boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    now=time.monotonic();deadline=now+reg['max_seconds'];children={};streams=[];events=[]
    journal=(out/'driver_events.jsonl').open('xb')
    def event(kind,**values):
        row={'type':kind,'checked_ns':time.monotonic_ns(),**values};events.append(row);journal.write(encoded(row));journal.flush()
    manifest={**process(os.getpid()),'schema_version':'p1-owned-role-v1','role':'driver','run_id':run,'boot_id':boot,
        'contract_sha256':config.sha256,'spec_sha256':config.spec_sha256,'tool_path':str(Path(__file__).resolve()),
        'tool_sha256':pin(__file__)['sha256'],'source_bundle_sha256':registry['driver_tool_sha256'],
        'effective_parameters_sha256':digest(encoded(reg)),'effective_parameters_immutable':True,
        'execute_qualified':False,'physical_release_qualified':False,'created_steady_ns':time.monotonic_ns(),
        'registry_sha256':reg['registry_sha256'],'registration_sha256':pin(args.registration)['sha256']}
    publish(out/'driver_manifest.json',manifest)
    driver_pin=peer_pin(out/'driver_manifest.json',manifest);publish(out/'driver_pins.json',driver_pin)
    def check_time():assert time.monotonic()<deadline,'registered run budget expired'
    def wait_file(path,seconds=10):
        until=min(deadline,time.monotonic()+seconds)
        while time.monotonic()<until:
            for role,c in children.items():
                if c['process'].poll() is not None:raise RuntimeError(role+' exited early: '+str(c['process'].returncode))
            if path.is_file():return read(path)
            time.sleep(.01)
        raise TimeoutError('waiting for '+str(path))
    def spawn(role,argv):
        check_time();root=out/role;root.mkdir(exist_ok=True)
        stdout=(root/'stdout.log').open('xb');stderr=(root/'stderr.log').open('xb');streams.extend([stdout,stderr])
        child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True,env=os.environ.copy())
        pidfd=os.pidfd_open(child.pid);p=process(child.pid)
        assert p['pgid']==p['sid']==child.pid
        children[role]={'process':child,'pidfd':pidfd,'start_ticks':p['process_start_ticks'],'argv':argv}
        event('role_spawned',role=role,pid=child.pid,process_start_ticks=p['process_start_ticks'],argv=argv)
        return root
    def native_argv(binary,parameters):
        argv=[binary,'--ros-args']
        for key,value in parameters.items():argv+=['-p',key+':='+str(value)]
        return argv
    def authenticate(role,path,expected_parameters=None):
        m=wait_file(path);child=children[role]['process'];actual=process(child.pid);record=registry['roles'][role]
        assert m['schema_version']=='p1-owned-role-v1' and m['run_id']==run and m['boot_id']==boot and m['contract_sha256']==config.sha256
        for key in ['pid','process_start_ticks','exe','binary_sha256','argv','pgid','sid']:assert m[key]==actual[key],(role,key)
        assert actual['binary_sha256']==record['binary_sha256'] and m['source_bundle_sha256']==record['source_bundle']['sha256']
        assert m['effective_parameters_immutable'] is True and m['execute_qualified'] is False and m['physical_release_qualified'] is False
        canonical={k:{'type':v['type'],'canonical_value':v['canonical_value']} for k,v in m['effective_parameters'].items()}
        assert digest(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode())==m['effective_parameters_sha256']
        assert m['effective_parameters']['use_sim_time']['value'] is False
        for key,value in (expected_parameters or {}).items():
            row=m['effective_parameters'][key];assert row['value']==value and type(row['value']) is type(value),(role,key,row,value)
        if role in ['worker','fixture','preparer']:assert m['contract_configuration']==config.configuration
        if 'source_fd' in m:
            sf=m['source_fd'];st=os.stat('/proc/'+str(child.pid)+'/fd/'+str(sf['fd']))
            assert st.st_ino==sf['inode'] and st.st_dev==sf['device'] and sf['append'] is True
            assert os.readlink('/proc/'+str(child.pid)+'/fd/'+str(sf['fd']))==sf['path']
        for ep in m['endpoints']:
            assert len(ep['gid'])==16 and any(ep['gid']) and all(type(n) is int and 0<=n<=255 for n in ep['gid'])
        event('actual_role_authenticated',role=role,pin=peer_pin(path,m),effective_parameters=m['effective_parameters'],endpoints=m['endpoints'])
        return m,peer_pin(path,m)
    def stop(role):
        c=children[role];child=c['process'];signal_rows=[]
        for sig,budget in [(signal.SIGINT,1.8),(signal.SIGTERM,.3),(signal.SIGKILL,.2)]:
            if child.poll() is not None:break
            current=process(child.pid)
            assert current['process_start_ticks']==c['start_ticks'] and current['pgid']==child.pid,'foreign process group guard'
            sent=time.monotonic_ns();os.killpg(child.pid,sig);signal_rows.append({'signal':sig.name,'sent_ns':sent})
            try:child.wait(timeout=budget)
            except subprocess.TimeoutExpired:continue
        rc=child.poll();assert rc is not None,'owned child not stopped'
        try:os.killpg(child.pid,0);empty=False
        except ProcessLookupError:empty=True
        row={'role':role,'pid':child.pid,'returncode':rc,'signals':signal_rows,'group_empty':empty,'finished_ns':time.monotonic_ns()}
        event('owned_role_closed',**row);return row
    outcome={'schema':'formal-owned-prepare-driver-result-v1','run_id':run,'passed':False,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
    try:
        common={'run_id':run,'contract_hash':config.sha256,'contract_file':str(reg['contract']),'mode':'no_output'}
        (out/'fixture').mkdir();fp={**common,'output_dir':str(out/'fixture'),'start_file':str(out/'fixture_start.json'),
            'driver_pins_file':str(out/'driver_pins.json'),'driver_pins_sha256':pin(out/'driver_pins.json')['sha256']}
        spawn('fixture',native_argv(registry['roles']['fixture']['binary'],fp))
        fm,fpin=authenticate('fixture',out/'fixture/manifest.json',fp)
        assert fm['role']=='synthetic_source' and fm['Applied_subscribers']==fm['Applied_publishers']==0
        (out/'worker').mkdir();wp={'run_id':run,'contract_hash':config.sha256,'contract_file':str(reg['contract']),
            'source_file':str(out/'worker/source.jsonl'),'owned_manifest_file':str(out/'worker/manifest.json'),
            'test_delay_ms':0,'test_native_block_ms':0,'diagnostic_v2_policy':'none','diagnostic_v2_block_ms':0}
        spawn('worker',native_argv(registry['roles']['worker']['binary'],wp))
        wm,wpin=authenticate('worker',out/'worker/manifest.json',wp)
        assert wm['role']=='worker' and wm['fault_injection_permission'] is False
        (out/'recorder').mkdir();rp=out/'recorder'
        recorder_argv=[registry['roles']['recorder']['binary'],'--run-id',run,'--contract',str(reg['contract']),
            '--contract-sha256',config.sha256,'--topics',str(reg['topics']),'--topics-sha256',reg['topics_sha256'],
            '--manifest',str(rp/'manifest.json'),'--terminal',str(rp/'terminal.json'),'--bag',str(rp/'bag'),
            '--storage-id','sqlite3','--prepare-budget-ms','10000']
        spawn('recorder',recorder_argv);rm,rpin=authenticate('recorder',rp/'manifest.json')
        assert rm['role']=='recorder' and rm['true_recorder_storage'] is True and rm['discovery_stopped'] is True
        assert rm['topic_declaration_sha256']==reg['topics_sha256'] and rm['record_options']['topics']==read(reg['topics'])['topics']
        peers={'schema':'formal-prepare-owned-peer-pins-v1','driver':driver_pin,'worker':wpin,'fixture':fpin,'recorder':rpin,'topics_sha256':reg['topics_sha256']}
        publish(out/'peer_pins.json',peers);(out/'preparer').mkdir()
        pp={**common,'output_dir':str(out/'preparer'),'peer_pins_file':str(out/'peer_pins.json'),
            'peer_pins_sha256':pin(out/'peer_pins.json')['sha256']}
        spawn('preparer',native_argv(registry['roles']['preparer']['binary'],pp))
        pm,ppin=authenticate('preparer',out/'preparer/manifest.json',pp)
        assert pm['role']=='formal_preparer' and all(e['kind']=='subscription' for e in pm['endpoints'])
        readers=wait_file(out/'preparer/reader_ready.json');assert readers['manifest_sha256']==ppin['manifest_sha256'] and readers['forbidden_Writers']==0
        publish(out/'fixture_start.json',{'schema':'formal-fixture-start-v1','run_id':run,'boot_id':boot,'contract_sha256':config.sha256,
            'fixture_manifest_sha256':fpin['manifest_sha256'],'driver_manifest_sha256':driver_pin['manifest_sha256'],
            'sequence':1,'issued_ns':time.monotonic_ns()})
        ready=wait_file(out/'preparer/ready.json');assert ready['run_id']==run and ready['contract_sha256']==config.sha256 and ready['spec_sha256']==config.spec_sha256
        grant={'schema':'p1-owned-formal-prepare-v1','policy':'owned-formal-no-output-prepare-close-v1','scope':'bounded_prepare_close_only',
            'run_id':run,'boot_id':boot,'contract_sha256':config.sha256,'spec_sha256':config.spec_sha256,
            'preparer_manifest_sha256':ppin['manifest_sha256'],
            'driver':{'pid':os.getpid(),'start_ticks':manifest['process_start_ticks'],'exe_sha256':manifest['binary_sha256'],
                'argv_sha256':digest(json.dumps(manifest['argv'],separators=(',',':')).encode()),'tool_sha256':manifest['tool_sha256']},
            'roles':{'worker_manifest_sha256':wpin['manifest_sha256'],'fixture_manifest_sha256':fpin['manifest_sha256'],'recorder_manifest_sha256':rpin['manifest_sha256']},
            'ready_snapshot_sha256':pin(out/'preparer/ready.json')['sha256'],'ready_generation':ready['ready_generation'],
            'version':ready['version'],'issued_ns':time.monotonic_ns(),'sequence':1,'stage_qualified':False,'execute_qualified':False}
        publish(out/'preparer/grant.json',grant);prepared=wait_file(out/'preparer/prepared.json')
        assert prepared['grant_sha256']==pin(out/'preparer/grant.json')['sha256'] and prepared['gate']['state']=='prepared'
        event('real_preparation_observed',prepared=prepared)
        until=time.monotonic()+reg['prepared_hold_seconds']
        while time.monotonic()<until:
            check_time()
            for c in children.values():assert c['process'].poll() is None,'role exited during prepared observation'
            time.sleep(.01)
        outcome.update(preparation_observed=True,ready_snapshot_sha256=grant['ready_snapshot_sha256'],grant_sha256=prepared['grant_sha256'])
    except Exception as e:
        outcome.update(error=repr(e),traceback=__import__('traceback').format_exc());event('driver_failure',error=repr(e))
    finally:
        closed=[]
        for role in ['preparer','fixture','worker','recorder']:
            if role in children:
                if role=='recorder':time.sleep(.2)
                try:closed.append(stop(role))
                except Exception as e:closed.append({'role':role,'error':repr(e),'group_empty':False});event('close_failure',role=role,error=repr(e))
        for c in children.values():os.close(c['pidfd'])
        outcome['closed_roles']=closed;outcome['elapsed_seconds']=time.monotonic()-now
        outcome['passed']=bool(outcome.get('preparation_observed')) and len(closed)==4 and all(r.get('returncode')==0 and r['group_empty'] and [s['signal'] for s in r['signals']]==['SIGINT'] for r in closed)
        publish(out/'driver_result.json',outcome);journal.close()
        for f in streams:f.close()
    print(json.dumps({'passed':outcome['passed'],'elapsed_seconds':outcome['elapsed_seconds'],'error':outcome.get('error'),'output':str(out)},sort_keys=True))
    return 0 if outcome['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
