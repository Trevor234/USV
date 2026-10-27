#!/usr/bin/env python3
"""One finite owned local-nominal M4 run, no ROS participant in the Driver.

Parent frozen values are immutable. The separate native entry scope permits
only this isolated nominal ownership confirmation; ordinary release stays off.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode=True
A=Path(__file__).resolve().parent
sys.path.insert(0,str(A/'python'))
import freeze_binding_v1 as freeze

SCOPE='M4_owned_local_nominal_only_v1'
INDEX_SHA='1d750a7eeb32f379f2be5dd516533f6f785e091c6b30082dda68e51b3f100081'
CONTRACT_SHA='19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a'


def encoded(value):return (json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def pin(path):
    path=Path(path);raw=path.read_bytes();return {'bytes':len(raw),'sha256':digest(raw)}
def read(path):return json.loads(Path(path).read_bytes())


def publish(path,value):
    path=Path(path);assert path.is_absolute() and not path.exists() and not path.is_symlink()
    parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    temp='.'+path.name+'.tmp.'+str(os.getpid())+'.'+str(time.monotonic_ns())
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent);visible=False
    try:
        raw=encoded(value);done=0
        while done<len(raw):done+=os.write(fd,raw[done:])
        os.fsync(fd);libc=ctypes.CDLL(None,use_errno=True);fn=libc.renameat2
        fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
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
    for row in rows:assert all(pin(row['path'])[k]==row[k] for k in ['bytes','sha256'])
    assert pin(record['binary'])['sha256']==record['binary_sha256']


def peer_pin(path,m):
    keys=['pid','process_start_ticks','exe','binary_sha256','source_bundle_sha256','effective_parameters_sha256']
    return {**{k:m[k] for k in keys},'manifest_path':str(path),'manifest_sha256':pin(path)['sha256']}


class SourceCursor:
    def __init__(self,path):
        self.path=Path(path);self.offset=0;self.tail=b'';self.total=0;self.rows=0;self.identity=None
    def poll(self):
        fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            st=os.fstat(fd);identity=(st.st_dev,st.st_ino)
            if self.identity is None:self.identity=identity
            assert identity==self.identity and st.st_size>=self.offset,'Source identity/truncation'
            os.lseek(fd,self.offset,os.SEEK_SET);chunks=[]
            while True:
                data=os.read(fd,512*1024)
                if not data:break
                self.total+=len(data);self.offset+=len(data)
                assert self.total<=64*1024**2,'explicit Source observer64MiB budget'
                chunks.append(data)
            data=self.tail+b''.join(chunks);parts=data.split(b'\n');self.tail=parts.pop()
            assert len(self.tail)<=262144
            out=[]
            for line in parts:
                assert len(line)<=262144
                self.rows+=1;assert self.rows<=1000000
                out.append(json.loads(line))
            return out
        finally:os.close(fd)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--registration',type=Path,required=True);args=parser.parse_args()
    reg=read(args.registration)
    assert reg['schema']=='M4-owned-normal-run-v1' and reg['scope']==SCOPE and reg['production_physical_release_enabled'] is False
    assert reg['domain_id']==120 and os.environ.get('ROS_DOMAIN_ID')=='120' and os.environ.get('ROS_LOCALHOST_ONLY')=='1' and os.environ.get('RMW_IMPLEMENTATION')=='rmw_fastrtps_cpp'
    assert reg['max_seconds']==45 and reg['source_window_ns']==20000000000 and reg['automatic_retries']==0
    assert reg['contract_sha256']==CONTRACT_SHA and reg['index_sha256']==INDEX_SHA
    parent=freeze.verify(Path(reg['contract']),Path(reg['index']),INDEX_SHA,CONTRACT_SHA)
    assert parent['passed'] and parent['M4_qualified'] is False
    config=read(reg['contract']);assert config['pending_final_calibration']==[]
    assert pin(reg['registry'])['sha256']==reg['registry_sha256'];registry=read(reg['registry'])
    assert registry['driver_tool_sha256']==pin(__file__)['sha256'] and registry['scope']==SCOPE
    for row in registry['roles'].values():verify_bundle(row)
    assert pin(reg['topics'])['sha256']==reg['topics_sha256']
    out=Path(reg['output']);assert out.is_absolute() and out.parent==A.parent/'runs';out.mkdir()
    run=reg['run_id'];boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    begin=time.monotonic();deadline=begin+45;children={};streams=[]
    journal=(out/'driver_events.jsonl').open('xb')
    def event(kind,**values):
        journal.write(encoded({'type':kind,'checked_ns':time.monotonic_ns(),**values}));journal.flush()
    manifest={**process(os.getpid()),'schema_version':'p1-owned-role-v1','role':'driver','run_id':run,'boot_id':boot,
        'contract_sha256':CONTRACT_SHA,'spec_sha256':parent.get('spec_sha256',freeze.full.SPEC_SHA256),
        'tool_path':str(Path(__file__).resolve()),'tool_sha256':pin(__file__)['sha256'],
        'source_bundle_sha256':registry['driver_tool_sha256'],'effective_parameters_sha256':digest(encoded(reg)),
        'effective_parameters_immutable':True,'execute_qualified':False,'physical_release_qualified':False,
        'created_steady_ns':time.monotonic_ns(),'registry_sha256':reg['registry_sha256'],
        'registration_sha256':pin(args.registration)['sha256'],'m4_release_scope':SCOPE}
    publish(out/'driver_manifest.json',manifest);dpin=peer_pin(out/'driver_manifest.json',manifest);publish(out/'driver_pins.json',dpin)
    def check_time():assert time.monotonic()<deadline,'registered45s Driver budget expired'
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
        pidfd=os.pidfd_open(child.pid);actual=process(child.pid);assert actual['pgid']==actual['sid']==child.pid
        children[role]={'process':child,'pidfd':pidfd,'start_ticks':actual['process_start_ticks'],'argv':argv}
        publish(root/'spawn.json',{'role':role,'pid':child.pid,'process_start_ticks':actual['process_start_ticks'],'argv':argv,'boot_id':boot})
        event('role_spawned',role=role,**actual)
    def native(binary,parameters):
        argv=[binary,'--ros-args']
        for key,value in parameters.items():argv+=['-p',key+':='+str(value)]
        return argv
    def authenticate(role,path,parameters=None):
        m=wait_file(path);actual=process(children[role]['process'].pid);record=registry['roles'][role]
        assert m['schema_version']=='p1-owned-role-v1' and m['run_id']==run and m['boot_id']==boot and m['contract_sha256']==CONTRACT_SHA
        for key in ['pid','process_start_ticks','exe','binary_sha256','argv','pgid','sid']:assert m[key]==actual[key],(role,key)
        assert actual['binary_sha256']==record['binary_sha256'] and m['source_bundle_sha256']==record['source_bundle']['sha256']
        assert m['effective_parameters_immutable'] is True and m['execute_qualified'] is False and m['physical_release_qualified'] is False
        canonical={k:{'type':v['type'],'canonical_value':v['canonical_value']} for k,v in m['effective_parameters'].items()}
        assert digest(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode())==m['effective_parameters_sha256']
        assert m['effective_parameters']['use_sim_time']['value'] is False
        for key,value in (parameters or {}).items():
            row=m['effective_parameters'][key];assert row['value']==value and type(row['value']) is type(value),(role,key,row,value)
        if role!='recorder':assert m['contract_configuration']==config
        if 'source_fd' in m:
            sf=m['source_fd'];st=os.stat('/proc/'+str(actual['pid'])+'/fd/'+str(sf['fd']))
            assert st.st_ino==sf['inode'] and st.st_dev==sf['device'] and sf['append'] is True
            assert os.readlink('/proc/'+str(actual['pid'])+'/fd/'+str(sf['fd']))==sf['path']
        for ep in m['endpoints']:assert len(ep['gid'])==16 and any(ep['gid']) and all(type(n) is int and 0<=n<=255 for n in ep['gid'])
        event('actual_role_authenticated',role=role,manifest=peer_pin(path,m),parameters=m['effective_parameters'],endpoints=m['endpoints'])
        return m,peer_pin(path,m)
    def stop(role):
        child=children[role]['process'];rows=[]
        first=config['worker_grace_ns']/1e9 if role=='worker' else config['shutdown_grace_ns']/1e9
        for sig,budget in [(signal.SIGINT,first),(signal.SIGTERM,config['term_grace_ns']/1e9),(signal.SIGKILL,config['kill_postcheck_ns']/1e9)]:
            if child.poll() is not None:break
            actual=process(child.pid);assert actual['process_start_ticks']==children[role]['start_ticks'] and actual['pgid']==child.pid
            os.killpg(child.pid,sig);rows.append({'signal':sig.name,'sent_ns':time.monotonic_ns(),'wait_seconds':budget})
            try:child.wait(timeout=budget)
            except subprocess.TimeoutExpired:pass
        rc=child.poll()
        try:os.killpg(child.pid,0);empty=False
        except ProcessLookupError:empty=True
        row={'role':role,'pid':child.pid,'returncode':rc,'signals':rows,'group_empty':empty,'finished_ns':time.monotonic_ns()}
        event('owned_role_closed',**row);return row
    result={'schema':'M4-owned-normal-driver-result-v1','run_id':run,'passed':False,'M4_qualified':False,'P1_qualified':False,
            'production_physical_release_enabled':False,'isolated_scope':SCOPE,'research_conclusion':False}
    try:
        for role in ['fixture','worker','recorder','regulator']:(out/role).mkdir()
        common={'run_id':run,'contract_hash':CONTRACT_SHA,'contract_file':str(reg['contract']),'m4_release_scope':SCOPE}
        fp={**common,'output_dir':str(out/'fixture'),'start_file':str(out/'fixture_start.json'),
            'topics_file':str(reg['topics']),'topics_sha256':reg['topics_sha256'],'controlled_phase_mode':'C','reference_speed_m_s':.05,
            'driver_pins_file':str(out/'driver_pins.json'),'driver_pins_sha256':pin(out/'driver_pins.json')['sha256']}
        spawn('fixture',native(registry['roles']['fixture']['binary'],fp));fm,fpin=authenticate('fixture',out/'fixture/owned_manifest.json',fp)
        assert fm['physical_publishers']==0 and fm['plant_connected'] is False and fm['reference_speed_m_s']==.05
        wp={**common,'driver_pins_file':str(out/'driver_pins.json'),'driver_pins_sha256':pin(out/'driver_pins.json')['sha256'],'source_file':str(out/'worker/source.jsonl'),'owned_manifest_file':str(out/'worker/manifest.json'),
            'test_delay_ms':0,'test_native_block_ms':0,'diagnostic_v2_policy':'none','diagnostic_v2_block_ms':0}
        spawn('worker',native(registry['roles']['worker']['binary'],wp));wm,wpin=authenticate('worker',out/'worker/manifest.json',wp)
        rp=out/'recorder';rv=[registry['roles']['recorder']['binary'],'--run-id',run,'--contract',str(reg['contract']),
            '--contract-sha256',CONTRACT_SHA,'--topics',str(reg['topics']),'--topics-sha256',reg['topics_sha256'],
            '--manifest',str(rp/'manifest.json'),'--terminal',str(rp/'terminal.json'),'--bag',str(rp/'bag'),'--storage-id','sqlite3','--prepare-budget-ms','10000']
        spawn('recorder',rv);rm,rpin=authenticate('recorder',rp/'manifest.json')
        assert rm['true_recorder_storage'] is True and rm['discovery_stopped'] is True and rm['topic_declaration_sha256']==reg['topics_sha256']
        publish(out/'peer_pins.json',{'schema':'M4-owned-role-pins-v1','driver':dpin,'worker':wpin,'fixture':fpin,'recorder':rpin,'topics_sha256':reg['topics_sha256']})
        cp={**common,'mode':'execute','output_dir':str(out/'regulator'),'peer_pins_file':str(out/'peer_pins.json'),
            'peer_pins_sha256':pin(out/'peer_pins.json')['sha256'],'diagnostic_source_file':registry['regulator_source'],
            'diagnostic_source_sha256':registry['regulator_source_sha256'],'diagnostic_binary_sha256':registry['roles']['regulator']['binary_sha256'],
            'worker_binary_sha256':registry['roles']['worker']['binary_sha256'],'witness_worker_instance':wm['worker_instance'],
            'source_file':str(out/'regulator/source.jsonl'),'witness_file':str(out/'regulator/witness.json'),'witness_enabled':True}
        spawn('regulator',native(registry['roles']['regulator']['binary'],cp));cm,cpin=authenticate('regulator',out/'regulator/manifest.json',cp)
        assert cm['role']=='p1_owned_execute_regulator' and cm['physical_publishers']==2 and cm['physical_API_calls_before_grant']==0
        publish(out/'fixture_start.json',{'schema':'M4-owned-inputs-start-v1','run_id':run,'boot_id':boot,'contract_sha256':CONTRACT_SHA,
            'scope':SCOPE,'driver_manifest_sha256':dpin['manifest_sha256'],'owner':cpin,'issued_ns':time.monotonic_ns(),'sequence':1})
        ready=wait_file(out/'regulator/ready.json');ctx=ready['context']
        assert ctx['regulator_manifest_sha256']==cpin['manifest_sha256'] and ctx['freeze_evidence_sha256']==INDEX_SHA
        gids=[bytes(next(e for e in cm['endpoints'] if e['kind']=='publisher' and e['topic']==config['output_topics'][side])['gid']).hex() for side in ['left','right']]
        assert ctx['output_gids']==gids and all(len(g)==32 for g in gids) and len(set(gids))==2
        assert ready['physical_API_calls']==0 and ready['anchor_known']==[False,False]
        publish(out/'regulator/grant.json',{'schema':'M4-owned-execute-grant-v1','scope':SCOPE,'run_id':run,'boot_id':boot,
            'contract_sha256':CONTRACT_SHA,'index_sha256':INDEX_SHA,'context':ctx,'version':ready['version'],
            'ready_sha256':pin(out/'regulator/ready.json')['sha256'],'driver_manifest_sha256':dpin['manifest_sha256'],'issued_ns':time.monotonic_ns(),'sequence':1})
        prepared=wait_file(out/'regulator/prepared.json');assert prepared['grant_sha256']==pin(out/'regulator/grant.json')['sha256']
        event('isolated_actual_output_authorized',prepared=prepared)
        cursor=SourceCursor(out/'regulator/source.jsonl');first=None;last=None;dynamic_jobs=0;observed_pairs=0
        while True:
            check_time()
            for role,c in children.items():assert c['process'].poll() is None,role+' early exit'
            for row in cursor.poll():
                if row['type'] in ['owned_tick_policy_failed','owned_pair_policy_failed','owned_applied_publication_failed','worker_unusable_transition']:raise RuntimeError('normal Source terminal: '+row['type'])
                if row['type']=='owned_API_pair':
                    observed_pairs+=1;assert not row['terminal'],'owned API policy terminal'
                if row['type']=='job':
                    job=row['job'];state=job['frozen_state'];dynamic=(state[3]**2+state[4]**2)>1e-12
                    if dynamic and all(job['anchor_known']) and any(abs(v)>1e-9 for v in job['anchor_n']):
                        if first is None:first={'freeze_ns':job['freeze_ns'],'odom_ns':job['odom_stamp_ns'],'job_id':job['job_id']}
                        last={'freeze_ns':job['freeze_ns'],'odom_ns':job['odom_stamp_ns'],'job_id':job['job_id']};dynamic_jobs+=1
            if first and last and last['freeze_ns']-first['freeze_ns']>=20000000000 and last['odom_ns']-first['odom_ns']>=20000000000:break
            time.sleep(.02)
        result.update(normal_window_observed=True,first=first,last=last,dynamic_jobs=dynamic_jobs,observed_API_pairs=observed_pairs,
                      Source_observer_bytes=cursor.total,Source_observer_rows=cursor.rows)
    except Exception as error:
        result.update(error=repr(error),traceback=__import__('traceback').format_exc());event('driver_failure',error=repr(error))
    finally:
        closed=[]
        for role in ['regulator','fixture','worker','recorder']:
            if role in children:
                if role=='recorder':time.sleep(.2)
                try:closed.append(stop(role))
                except Exception as error:closed.append({'role':role,'error':repr(error),'group_empty':False});event('close_failure',role=role,error=repr(error))
        for c in children.values():os.close(c['pidfd'])
        result['closed_roles']=closed;result['elapsed_seconds']=time.monotonic()-begin
        result['passed']=bool(result.get('normal_window_observed')) and len(closed)==4 and all(r.get('returncode')==0 and r['group_empty'] and [s['signal'] for s in r['signals']]==['SIGINT'] for r in closed)
        publish(out/'driver_result.json',result);journal.close()
        for f in streams:f.close()
    print(json.dumps({'passed':result['passed'],'error':result.get('error'),'elapsed_seconds':result['elapsed_seconds'],'output':str(out)}))
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
