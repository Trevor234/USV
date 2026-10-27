#!/usr/bin/env python3
"""One finite owned M4 DIAGNOSTIC run (W1 / W3 / W4).

Derived from batch-49 owned_m4_driver_v1.py. Every helper (pin/read/publish/
process/verify_bundle/peer_pin/SourceCursor/spawn/native/authenticate/stop) is
kept byte-identical; only the observation window and exit classification are
case-specific.

Unlike the batch-53 fault driver, these cases run under the v4 diagnostic
contract, which is the ONLY profile that carries fault_injection_enabled=true
and parameters_are_diagnostic_only=true. The stimulus is an in-process,
registered, one-shot hook inside the Worker (a pre-native stall, a post-native
delivery delay, or a single generated-but-unpublished Candidate). The v3 frozen
profile still refuses every one of those hooks, and the Regulator's ordinary
path still rejects a Worker whose runtime hooks are nonzero. The diagnostic
path binds the hook value to the registered case and accepts nothing else.

Parent frozen values are immutable. Ordinary release stays off.
"""
import argparse
import ctypes
import hashlib
import json
import os
import zlib
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode=True
A=Path(__file__).resolve().parent
sys.path.insert(0,str(A/'python'))
import freeze_binding_v1 as freeze

SCOPE='M4_owned_diagnostic_worker_only_v1'
INDEX_SHA='d1a9f0e2b7c4a8536e0f2b9d4c7a1e5836b0d9f2c4a7e1b8369d0c5f2a8e4b71'
CONTRACT_SHA='3a8451d5172423adbef955d78c8550d67bbeec4582a80bd9ba69028b867b9f06'


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


def _w2r_terminal(result):
    """Terminal flag carried by the Worker's terminal rows, if any."""
    return bool(result.get('w2_backend_terminal',False))


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


W2_MAGIC = 0x4C523257


def w2_crc32(data):
    return zlib.crc32(data) & 0xFFFFFFFF


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--registration',type=Path,required=True);args=parser.parse_args()
    reg=read(args.registration)
    assert reg['schema']=='M4-owned-diagnostic-run-v1' and reg['scope']==SCOPE and reg['production_physical_release_enabled'] is False
    case=reg['case'];assert case in ('W1-work-stall-watchdog','W3-result-delivery-delay','W4-result-delivery-drop','W2-native-boundary-hold'),case
    assert reg['domain_id']==120 and os.environ.get('ROS_DOMAIN_ID')=='120' and os.environ.get('ROS_LOCALHOST_ONLY')=='1' and os.environ.get('RMW_IMPLEMENTATION')=='rmw_fastrtps_cpp'
    assert reg['max_seconds']==45 and reg['automatic_retries']==0
    # W1 is an IN-PROCESS diagnostic run: the contract itself carries
    # fault_injection_enabled=true, which is precisely what v3 forbids and v4
    # permits. There is no freeze.verify() here because that helper only knows
    # the v3 frozen parent.
    assert reg['fault_injection_enabled'] is True,'diagnostic case requires a fault-capable contract'
    assert reg['contract_sha256']==CONTRACT_SHA and reg['index_sha256']==INDEX_SHA
    config=read(reg['contract'])
    assert config['schema']=='p1-execution-contract-v4'
    assert config['fault_injection_enabled'] is True
    assert config['qualification']=='execution_diagnostic_only'
    assert config['pending_final_calibration']==[]
    parent={'spec_sha256':config['freeze_evidence_sha256'],'M4_qualified':False}
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
    expect_dead=set();expect_stopped=set()
    def wait_file(path,seconds=10):
        until=min(deadline,time.monotonic()+seconds)
        while time.monotonic()<until:
            for role,c in children.items():
                if role in expect_dead:continue
                if c['process'].poll() is not None:raise RuntimeError(role+' exited early: '+str(c['process'].returncode))
            if path.is_file():return read(path)
            time.sleep(.01)
        raise TimeoutError('waiting for '+str(path))
    def spawn(role,argv,pass_fds=()):
        check_time();root=out/role;root.mkdir(exist_ok=True)
        stdout=(root/'stdout.log').open('xb');stderr=(root/'stderr.log').open('xb');streams.extend([stdout,stderr])
        child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True,env=os.environ.copy(),pass_fds=tuple(pass_fds),close_fds=True)
        pidfd=os.pidfd_open(child.pid);actual=process(child.pid);assert actual['pgid']==actual['sid']==child.pid
        children[role]={'process':child,'pidfd':pidfd,'start_ticks':actual['process_start_ticks'],'argv':argv}
        publish(root/'spawn.json',{'role':role,'pid':child.pid,'process_start_ticks':actual['process_start_ticks'],'argv':argv,'boot_id':boot,'inherited_fds':list(pass_fds)})
        event('role_spawned',role=role,**actual)

    # ── W2 private release channel ───────────────────────────────────────
    # Only the Worker inherits the read end. The Driver keeps the write end and
    # closes its own copy of the read end right after spawn, so EOF is decidable
    # by the child alone. A sibling role is handed nothing.
    def w2_channel_open():
        read_fd,write_fd=os.pipe()
        return read_fd,write_fd

    def w2_release(write_fd,job_id,ordinal,nonce):
        frame=bytearray(44)
        frame[0:4]=W2_MAGIC.to_bytes(4,'little')
        frame[4:6]=(1).to_bytes(2,'little')
        frame[6:8]=(0).to_bytes(2,'little')
        frame[8:16]=(1).to_bytes(8,'little')      # run sequence
        frame[16:24]=job_id.to_bytes(8,'little')
        frame[24:28]=ordinal.to_bytes(4,'little')
        frame[28:32]=nonce.to_bytes(4,'little')
        frame[32:40]=(1).to_bytes(8,'little')     # single use
        frame[40:44]=w2_crc32(bytes(frame[0:40])).to_bytes(4,'little')
        written=os.write(write_fd,bytes(frame))
        assert written==len(frame),'short release write: %d of %d'%(written,len(frame))
        return bytes(frame)

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
    closed_by_wait={}
    def wait_close(role,seconds=15):
        if role in closed_by_wait:return closed_by_wait[role]
        child=children[role]['process']
        try:child.wait(timeout=min(seconds,max(0.0,deadline-time.monotonic())))
        except subprocess.TimeoutExpired:pass
        rc=child.poll()
        try:os.killpg(child.pid,0);empty=False
        except ProcessLookupError:empty=True
        row={'role':role,'pid':child.pid,'returncode':rc,'signals':[],'group_empty':empty,
             'finished_ns':time.monotonic_ns(),'signalled_by':'driver-registered-stimulus'}
        closed_by_wait[role]=row;event('owned_role_closed',**row);return row
    result={'schema':'M4-owned-fault-driver-result-v1','run_id':run,'case':case,'passed':False,'M4_qualified':False,'P1_qualified':False,
            'production_physical_release_enabled':False,'isolated_scope':SCOPE,'research_conclusion':False}
    # W2 context is hoisted above the try: `finally` closes these fds, and an
    # early failure (for example Fixture authentication) must not make cleanup
    # itself raise UnboundLocalError over the original error.
    w2 = reg.get('w2_release')
    w2_read = w2_write = -1
    w2_binding = None
    w2_release_sent = False
    w2_release_frame = None
    w2_result = None
    w2_entered_at = None
    w2_entered_row = {}
    w2_ticks_after_enter = []
    # Registration clauses the final predicate depends on are checked BEFORE any
    # role starts, so a malformed registration fails fast rather than after a run.
    if case=='W2-native-boundary-hold':
        assert isinstance(w2,dict),'W2 registration must declare w2_release'
        for key in ('job_id','ordinal','nonce','wait_budget_ns'):
            assert isinstance(w2.get(key),int),'w2_release.%s must be an integer'%key
        assert w2['job_id']>0 and w2['ordinal']>0 and w2['nonce']!=0, \
            'w2_release job/ordinal/nonce must be positive'
        assert 0<w2['wait_budget_ns']<=2000000000,'w2_release wait budget out of bounds'
        _w2_exp=reg.get('expected',{}).get('w2_exit_codes')
        assert isinstance(_w2_exp,dict) and isinstance(_w2_exp.get('worker'),int), \
            'W2 registration must declare expected.w2_exit_codes.worker'
        assert reg.get('expected',{}).get('w2_worker_signals'), \
            'W2 registration must declare expected.w2_worker_signals'
    try:
        for role in ['fixture','worker','recorder','regulator']:(out/role).mkdir()
        common={'run_id':run,'contract_hash':CONTRACT_SHA,'contract_file':str(reg['contract']),'m4_release_scope':SCOPE}
        fp={**common,'output_dir':str(out/'fixture'),'start_file':str(out/'fixture_start.json'),
            'topics_file':str(reg['topics']),'topics_sha256':reg['topics_sha256'],'controlled_phase_mode':'C','reference_speed_m_s':.05,
            'driver_pins_file':str(out/'driver_pins.json'),'driver_pins_sha256':pin(out/'driver_pins.json')['sha256']}
        spawn('fixture',native(registry['roles']['fixture']['binary'],fp));fm,fpin=authenticate('fixture',out/'fixture/owned_manifest.json',fp)
        assert fm['physical_publishers']==0 and fm['plant_connected'] is False and fm['reference_speed_m_s']==.05
        # W1: the Worker carries its own registered stall. It blocks the
        # COMPUTATION thread only (pre-native, holding no mutex), so the executor
        # thread keeps publishing capability every 200 ms while active_job stays
        # pinned. That is what separates this case from R3's whole-process
        # SIGSTOP, where the heartbeat stopped and the receipt lease expired first.
        wp={**common,'driver_pins_file':str(out/'driver_pins.json'),'driver_pins_sha256':pin(out/'driver_pins.json')['sha256'],'source_file':str(out/'worker/source.jsonl'),'owned_manifest_file':str(out/'worker/manifest.json'),
            'test_delay_ms':(reg.get('worker_delay_ms',0) if case=='W3-result-delivery-delay' else 0),
            'test_native_block_ms':0,
            'diagnostic_v2_policy':('pre_native_once_after_completed_v1'
                                    if case=='W1-work-stall-watchdog' else 'none'),
            'diagnostic_v2_block_ms':(1700 if case=='W1-work-stall-watchdog' else 0),
            'diagnostic_drop_after_candidates':(reg.get('drop_after_candidates',-1)
                                                if case=='W4-result-delivery-drop' else -1)}
        # W2: a private release channel for one registered Job and internal
        # ordinal. The Worker inherits ONLY the read end; this process keeps the
        # write end and closes its own read end immediately after spawn so EOF
        # stays decidable by the Worker alone.
        if w2:
            w2_read, w2_write = w2_channel_open()
            # Pin the channel's real identity now that the pipe exists. A static
            # registration cannot know an inode that has not been created yet, so
            # the binding is fixed here and compared against the Worker manifest.
            _st = os.fstat(w2_write)
            w2_binding = {'device': int(_st.st_dev), 'inode': int(_st.st_ino),
                          'job_id': int(w2['job_id']), 'ordinal': int(w2['ordinal']),
                          'nonce': int(w2['nonce']),
                          'wait_budget_ns': int(w2['wait_budget_ns'])}
            event('w2_channel_bound', **w2_binding)
            wp.update({'w2_release_fd': w2_read,
                       'w2_release_job_id': int(w2['job_id']),
                       'w2_release_ordinal': int(w2['ordinal']),
                       'w2_release_nonce': int(w2['nonce']),
                       'w2_release_wait_ns': int(w2['wait_budget_ns'])})
        spawn('worker',native(registry['roles']['worker']['binary'],wp),
              pass_fds=(w2_read,) if w2 else ())
        if w2:
            os.close(w2_read)  # the parent keeps only the write end
            w2_read = -1
        wm,wpin=authenticate('worker',out/'worker/manifest.json',wp)
        if w2_binding is not None:
            # The Worker reports what it actually inherited, not what it was told.
            # Device+inode must match the pipe this Driver created, and the
            # binding fields must match the registration.
            ch=wm.get('w2_release_channel')
            assert isinstance(ch,dict),'W2 Worker did not report its release channel'
            assert ch.get('device')==w2_binding['device'] and \
                   ch.get('inode')==w2_binding['inode'], \
                'W2 Worker channel (%r,%r) is not the pipe this Driver created (%r,%r)'%(
                    ch.get('device'),ch.get('inode'),
                    w2_binding['device'],w2_binding['inode'])
            for key in ('job_id','ordinal','nonce','wait_budget_ns'):
                assert ch.get(key)==w2_binding[key], \
                    'W2 Worker channel %s=%r, registered %r'%(key,ch.get(key),w2_binding[key])
            assert ch.get('read_only') is True and ch.get('gate_armed') is True, \
                'W2 Worker channel must be an armed read-only pipe'
            event('w2_channel_verified',**w2_binding)
        rp=out/'recorder';rv=[registry['roles']['recorder']['binary'],'--run-id',run,'--contract',str(reg['contract']),
            '--contract-sha256',CONTRACT_SHA,'--topics',str(reg['topics']),'--topics-sha256',reg['topics_sha256'],
            '--manifest',str(rp/'manifest.json'),'--terminal',str(rp/'terminal.json'),'--bag',str(rp/'bag'),'--storage-id','sqlite3','--prepare-budget-ms','10000']
        spawn('recorder',rv)
        actual_recorder=process(children['recorder']['process'].pid)
        assert actual_recorder['binary_sha256']==registry['roles']['recorder']['binary_sha256']
        rprocess={**actual_recorder,'schema':'M4-recorder-owned-process-only/v1','role':'recorder','run_id':run,'boot_id':boot,
            'contract_sha256':CONTRACT_SHA,'source_bundle_sha256':registry['roles']['recorder']['source_bundle']['sha256'],
            'manifest_path':str(rp/'manifest.json'),'topics_sha256':reg['topics_sha256'],'process_only':True,'recording_ready':False}
        publish(out/'recorder_process_pin.json',rprocess)
        event('actual_recorder_process_only_authenticated',pin=rprocess,full_recording_ready=False)
        publish(out/'peer_pins.json',{'schema':'M4-owned-role-bootstrap-pins-v1','driver':dpin,'worker':wpin,'fixture':fpin,'recorder_process':rprocess,'topics_sha256':reg['topics_sha256']})
        cp={**common,'mode':'execute','output_dir':str(out/'regulator'),'peer_pins_file':str(out/'peer_pins.json'),
            'peer_pins_sha256':pin(out/'peer_pins.json')['sha256'],'diagnostic_source_file':registry['regulator_source'],
            'diagnostic_source_sha256':registry['regulator_source_sha256'],'diagnostic_binary_sha256':registry['roles']['regulator']['binary_sha256'],
            'worker_binary_sha256':registry['roles']['worker']['binary_sha256'],'witness_worker_instance':wm['worker_instance'],
            'source_file':str(out/'regulator/source.jsonl'),'witness_file':str(out/'regulator/witness.json'),'witness_enabled':True,'diagnostic_case':case}
        if w2:
            # The Regulator pins the reported channel against these values.
            cp.update({'w2_release_job_id':int(w2['job_id']),
                       'w2_release_ordinal':int(w2['ordinal']),
                       'w2_release_nonce':int(w2['nonce']),
                       'w2_release_wait_ns':int(w2['wait_budget_ns'])})
        spawn('regulator',native(registry['roles']['regulator']['binary'],cp));cm,cpin=authenticate('regulator',out/'regulator/manifest.json',cp)
        assert cm['role']=='p1_owned_execute_regulator' and cm['physical_publishers']==2 and cm['physical_API_calls_before_grant']==0
        rm,rpin=authenticate('recorder',rp/'manifest.json')
        assert rm['true_recorder_storage'] is True and rm['discovery_stopped'] is True and rm['topic_declaration_sha256']==reg['topics_sha256']
        event('actual_full_recorder_authenticated',pin=rpin)
        publish(out/'fixture_start.json',{'schema':'M4-owned-inputs-start-v1','run_id':run,'boot_id':boot,'contract_sha256':CONTRACT_SHA,
            'scope':SCOPE,'driver_manifest_sha256':dpin['manifest_sha256'],'owner':cpin,'issued_ns':time.monotonic_ns(),'sequence':1})
        ready=wait_file(out/'regulator/ready.json');ctx=ready['context']
        assert ctx['regulator_manifest_sha256']==cpin['manifest_sha256'] and ctx['freeze_evidence_sha256']==INDEX_SHA
        assert ready['complete_recorder_pin']==rpin,'actual complete Recorder pin bound in ready evidence'
        gids=[bytes(next(e for e in cm['endpoints'] if e['kind']=='publisher' and e['topic']==config['output_topics'][side])['gid']).hex() for side in ['left','right']]
        assert ctx['output_gids']==gids and all(len(g)==32 for g in gids) and len(set(gids))==2
        assert ready['physical_API_calls']==0 and ready['anchor_known']==[False,False]
        grant_file=out/'regulator/grant.json'
        publish(grant_file,{'schema':'M4-owned-execute-grant-v1','scope':SCOPE,'run_id':run,'boot_id':boot,
            'contract_sha256':CONTRACT_SHA,'index_sha256':INDEX_SHA,'context':ctx,'version':ready['version'],
            'ready_sha256':pin(out/'regulator/ready.json')['sha256'],'driver_manifest_sha256':dpin['manifest_sha256'],'issued_ns':time.monotonic_ns(),'sequence':1})
        prepared=wait_file(out/'regulator/prepared.json');assert prepared['grant_sha256']==pin(grant_file)['sha256']
        event('diagnostic_actual_output_authorized',prepared=prepared)
        # W1: no external signal. The Worker blocks its own computation thread on
        # the SECOND completed job (after_completed_jobs=1 means it fires once
        # one job has finished). We watch the Regulator Source for the watchdog.
        cursor=SourceCursor(out/'regulator/source.jsonl')
        # The stall is a WORKER-side event (diagnostic_v2_pre_native_*), so it
        # must be read from the Worker Source. The Regulator Source only carries
        # the consequence (active_watchdog / worker_unusable_transition).
        worker_cursor=SourceCursor(out/'worker/source.jsonl')
        accepted_pairs=0;stall_entered=False;stall_released=False
        stall_enter_ns=None;stall_release_ns=None
        watchdog_ns=None;transition_ns=None;transition_reason=None
        pairs_before=0;pairs_after=0;ramp_ok=True;new_job_after=False;new_candidate_after=False
        max_cap_age_while_stalled=0;cap_before_stall=None;cap_after_stall=None
        renewals_during_stall=0;last_renewal_ns=None;late_candidates=0;dropped=0
        dropped_job_id=None;dropped_target_tick=None;decision_ticks={};decisions={}
        jobs_by_id={};registered_job_ids=set();published_job_ids=set();jobs_after_drop=0
        # Terminal evidence for the W2 end-state clauses, filled from the Worker.
        w2_terminal_evidence={'active_cleared':False,'pending_discarded':False,
                              'backend_terminal':False,'terminal_events':[]}
        generated_at_drop=None;cap_window=[];cap_frame=[]
        # W2 release state was hoisted above the try; only the run-specific
        # counter is set here.
        w2_required_ticks=int(w2.get('ticks_before_release',2)) if w2 else 0
        deadline_obs=min(deadline,time.monotonic()+(8 if case=='W3-result-delivery-delay' else 60))
        while time.monotonic()<deadline_obs:
            check_time()
            for role,c in children.items():
                if role in expect_dead:continue
                assert c['process'].poll() is None,role+' early exit'
            for wrow in worker_cursor.poll():
                wt=wrow['type']
                if wt=='w2_release_channel_armed':
                    w2_armed=wrow
                    event('w2_channel_armed_by_worker',**{k:v for k,v in wrow.items()
                                                         if k not in ('type',)})
                elif wt=='w2_boundary_entered':
                    # The Driver times its release against this event. A thread
                    # that merely sleeps is not evidence of anything.
                    w2_entered_at=wrow.get('entered_ns')
                    w2_entered_row=wrow
                    event('w2_boundary_entered_observed',
                          job_id=wrow.get('job_id'),ordinal=wrow.get('ordinal'),
                          entered_ns=w2_entered_at,
                          job_deadline_ns=wrow.get('job_deadline_ns'))
                elif wt in ('terminal_exception','terminal_numerical_failure'):
                    # BOTH terminal rows mean the Backend is unusable for this
                    # run. Only `terminal_numerical_failure` carries an explicit
                    # `policy` string; `terminal_exception` does not, so keying the
                    # flag on `policy` would leave the W2 expiry path unflagged.
                    w2_terminal_evidence['terminal_events'].append(
                        {'type':wt,'job_id':wrow.get('job_id'),
                         'reason':wrow.get('reason'),'policy':wrow.get('policy','')})
                    w2_terminal_evidence['backend_terminal']=True
                elif wt=='pending_discarded':
                    w2_terminal_evidence['pending_discarded']=True
                elif wt=='worker_summary':
                    # The summary reports `fatal`, which is the terminal flag; the
                    # capability stream then reports active_job=0.
                    if wrow.get('fatal') is True:
                        w2_terminal_evidence['backend_terminal']=True
                elif wt=='w2_boundary_result':
                    w2_result=wrow
                    event('w2_boundary_result_observed',
                          disposition=wrow.get('disposition'),
                          actual_native_invoked=wrow.get('actual_native_invoked'),
                          job_id=wrow.get('job_id'),ordinal=wrow.get('ordinal'))
                elif wt=='diagnostic_candidate_dropped':
                    dropped+=1;dropped_job_id=wrow['job_id']
                    generated_at_drop=wrow['generated_candidates']
                    # The Regulator Source row for this Job may have been read
                    # before or after the drop, so resolve in both places.
                    if dropped_job_id in jobs_by_id:dropped_target_tick=jobs_by_id[dropped_job_id]
                elif wt=='job_received':
                    if dropped:jobs_after_drop+=1
                elif wt=='capability_publish_attempt':
                    p=wrow['payload']
                    # Terminal evidence: the Worker reports `fatal` and clears
                    # `active_job` on the isolation path. Both are read from the
                    # same payload, in the same branch the W4 accounting uses.
                    if p.get('fatal') is True and p.get('active_job')==0:
                        w2_terminal_evidence['active_cleared']=True
                    if dropped and jobs_after_drop==0:
                        # Capability rows emitted after the drop but BEFORE any
                        # later Job arrived: this is the "no subsequent Job"
                        # accounting window.
                        cap_window.append({'source':'worker_capability_publish_attempt',
                            'snapshot_ns':wrow['snapshot_ns'],
                            'active_job':p['active_job'],'completed_jobs':p['completed_jobs'],
                            'pending_count':p['pending_count']})
                elif wt=='diagnostic_v2_pre_native_enter':
                    stall_entered=True;stall_enter_ns=wrow['start_ns']
                elif wt=='diagnostic_v2_pre_native_release':
                    stall_released=True;stall_release_ns=wrow['released_ns']
            for row in cursor.poll():
                t=row['type']
                if t=='owned_API_pair':
                    if transition_ns is None:
                        pairs_before+=1
                        if row['kind']=='accepted' and row['returned']==[True,True]:accepted_pairs+=1
                    else:
                        pairs_after+=1
                        if row.get('gap_exceeded') or row.get('span_exceeded') or row.get('rate_exceeded'):ramp_ok=False
                elif t=='capability_admission':
                    # A renewal proves the heartbeat was alive at that instant.
                    if (stall_entered and not stall_released and row.get('renewed') and
                            stall_enter_ns is not None and stall_release_ns is None):
                        lease_ns=row.get('lease_last_after_ns') or 0
                        if stall_enter_ns<=lease_ns:
                            renewals_during_stall+=1
                            if last_renewal_ns:
                                max_cap_age_while_stalled=max(
                                    max_cap_age_while_stalled,lease_ns-last_renewal_ns)
                            last_renewal_ns=lease_ns
                            cap_after_stall=row
                elif t=='active_watchdog':
                    watchdog_ns=row['observed_ns']
                elif t=='worker_unusable_transition' and transition_ns is None:
                    transition_ns=row['processed_ns'];transition_reason=row['reason']
                    event('fault_observed',reason=row['reason'],transition_ns=transition_ns)
                elif t=='capability_admission':
                    cap=row['capability']
                    cap_frame.append({'source':'regulator_capability_admission',
                        'callback_sequence':row['callback_sequence'],
                        'active_job':cap['active_job'],'completed_jobs':cap['completed_jobs'],
                        'pending_count':cap['pending_count'],
                        'lease_last_after_ns':row.get('lease_last_after_ns')})
                elif t=='decision':
                    decision_ticks[row['tick']]=row.get('reason','')
                    decisions[row['tick']]={'reason':row.get('reason',''),'accepted':row.get('accepted') is True,
                        'control_source':row.get('control_source'),'final_n':row.get('final_n'),
                        'previous_n':row.get('previous_n'),'job_id':row.get('job_id'),
                        'tick':row.get('tick'),'activation_commit_ns':row.get('activation_commit_ns'),
                        'start_ns':row.get('start_ns'),'end_ns':row.get('end_ns'),
                        'anchor_known':row.get('anchor_known')}
                    # W2: count complete business ticks observed *after* the
                    # Worker reported entering the boundary, and release once the
                    # registered number has gone by. This is the "observe real
                    # ticks, then release" rule; a thread that merely sleeps is
                    # not evidence of anything.
                    if w2 and w2_entered_at is not None and not w2_release_sent:
                        # Screen by real event time, not by the order rows
                        # happened to be read: a tick that completed before the
                        # boundary was entered is not "a tick after entry", even
                        # if its log line is read later.
                        start_ns=row.get('start_ns')
                        end_ns=row.get('end_ns')
                        if (str(row.get('reason',''))!='shutdown'
                                and isinstance(start_ns,int) and isinstance(end_ns,int)
                                and start_ns>=w2_entered_at
                                and end_ns>start_ns
                                and row.get('tick') not in w2_ticks_after_enter):
                            w2_ticks_after_enter.append(row.get('tick'))
                        if len(w2_ticks_after_enter)>=w2_required_ticks:
                            _before=time.monotonic_ns()
                            w2_release_frame=w2_release(w2_write,int(w2['job_id']),
                                                        int(w2['ordinal']),int(w2['nonce']))
                            _after=time.monotonic_ns()
                            w2_write_ns=_after-_before
                            w2_release_sent=True
                            event('w2_release_sent',job_id=int(w2['job_id']),
                                  ordinal=int(w2['ordinal']),nonce=int(w2['nonce']),
                                  ticks_observed=len(w2_ticks_after_enter),
                                  ticks=list(w2_ticks_after_enter),
                                  frame_len=len(w2_release_frame),
                                  write_start_ns=_before,write_end_ns=_after,
                                  write_elapsed_ns=w2_write_ns,
                                  frame_sha256=__import__('hashlib').sha256(
                                      w2_release_frame).hexdigest())
                elif t=='job':
                    jid=row['job']['job_id'];jobs_by_id[jid]=row['job']['target_tick']
                    if dropped and dropped_job_id==jid:dropped_target_tick=row['job']['target_tick']
                    if transition_ns is not None:new_job_after=True
                elif t=='candidate_registration':
                    registered_job_ids.add(row['job']['job_id'])
                    if row.get('accepted_registration'):
                        published_job_ids.add(row['job']['job_id'])
                    if not row.get('accepted_registration'):
                        lr=str(row.get('reason',''))
                        if lr in ('late','wrong_tick','cutoff_closed'):late_candidates+=1
                    elif transition_ns is not None:new_candidate_after=True
            if case=='W2-native-boundary-hold':
                # W2 is complete when the release was written AND the Worker
                # reported the resulting disposition. Either without the other
                # is an unfinished stimulus, not a result.
                # The boundary result arrives BEFORE the terminal rows on this
                # path (the Worker records the refusal, then goes fatal). Breaking
                # here would skip the terminal evidence the predicate requires.
                if (w2_release_sent and w2_result is not None
                        and w2_terminal_evidence['terminal_events']
                        and w2_terminal_evidence['active_cleared']):
                    break
            elif case=='W4-result-delivery-drop':
                # W4: the Worker generates a Candidate and never publishes it.
                # The report must show WHAT the Regulator did with the missing
                # delivery: the dropped Job's own target tick, at least one later
                # business tick (delivery resumed), and the capability accounting
                # emitted between the drop and the next Job.
                if dropped_target_tick is not None and cap_window:
                    d0=decisions.get(dropped_target_tick)
                    later=[k for k,v in decisions.items()
                           if k>dropped_target_tick and v['reason']!='shutdown']
                    if d0 is not None and d0['reason']!='shutdown' and later:break
                if dropped>=1 and time.monotonic()-begin>40:break
            elif case=='W3-result-delivery-delay':
                # W3 has no stall and no watchdog: it must run normally while the
                # Worker's post-native delay pushes candidate delivery past the
                # job deadline. Stop once enough pairs have been seen.
                if late_candidates>=1:break
            elif transition_ns is not None and pairs_after>=2 and stall_released:
                # Keep draining until the Worker's release row is observed, so the
                # stall duration is measured rather than assumed.
                break
            time.sleep(.02)
        if case=='W4-result-delivery-drop':
            # W4: a Candidate was generated and never delivered. The Regulator
            # must see no candidate for that tick, never a solver failure, and
            # the Worker must still close the tick normally.
            assert dropped>=1,'W4 never observed a generated-but-dropped candidate'
            assert dropped_target_tick is not None,'W4 could not resolve the dropped Job target tick'
            assert transition_ns is None,'W4 must not produce a worker_unusable_transition'
            assert watchdog_ns is None,'W4 must not trip the active watchdog'
            d0=decisions.get(dropped_target_tick)
            assert d0 is not None,'W4 never observed a decision for the dropped Job target tick'
            assert d0['reason']=='no_candidate' and d0['accepted'] is False, \
                'W4 target tick %r was decided as %r (accepted=%r)'%(dropped_target_tick,d0['reason'],d0['accepted'])
            assert dropped_job_id not in registered_job_ids,'W4 dropped candidate was registered anyway'
            # The frozen fallback policy (p1_admission.hpp:131) holds the last
            # applied command while commit-last_accepted<=hold_ns, else ramps to
            # zero. Recompute that predicate independently from the decision rows
            # instead of trusting the reported control_source.
            hold_ns=int(config['hold_ns'])
            prior=[(v['tick'],v['activation_commit_ns']) for v in decisions.values()
                   if v['accepted'] and v['tick']<dropped_target_tick]
            assert prior,'W4 has no accepted tick before the dropped target tick'
            prior_tick,prior_commit=max(prior,key=lambda x:x[1])
            age_ns=d0['activation_commit_ns']-prior_commit
            expected_source='hold' if age_ns<=hold_ns else 'ramp_zero'
            assert d0['control_source']==expected_source, \
                'W4 fallback source %r but policy (age %d vs hold %d ns) requires %r'%(
                    d0['control_source'],age_ns,hold_ns,expected_source)
            if expected_source=='hold':
                assert d0['final_n']==d0['previous_n'],'W4 hold did not keep the applied command'
            later=sorted(k for k,v in decisions.items()
                         if k>dropped_target_tick and v['reason']!='shutdown')
            assert later,'W4 never observed a business tick after the dropped target tick'
            assert any(decisions[k]['accepted'] for k in later),'W4 never resumed delivery'
            cleared=[r for r in (cap_window+cap_frame)
                     if r['active_job']==0 and r['pending_count']==0
                     and r['completed_jobs']>=generated_at_drop]
            assert cleared,'W4 never cleared active_job after the drop with no later Job pending'
            result.update(W4_observed=True,dropped_candidates=dropped,
                          dropped_job_id=dropped_job_id,dropped_target_tick=dropped_target_tick,
                          generated_at_drop=generated_at_drop,
                          target_tick_decision=d0,
                          target_tick_age_since_prior_accept_ns=age_ns,
                          hold_ns=hold_ns,prior_accepted_tick=prior_tick,
                          expected_fallback_source=expected_source,
                          later_business_ticks={k:decisions[k] for k in later},
                          candidate_job_ids=sorted(registered_job_ids),
                          capability_window_after_drop=cap_window,
                          capability_frame_after_drop=cap_frame,
                          active_cleared_without_subsequent_job=True,
                          delivery_resumed_after_drop=True,
                          pairs_before_transition=pairs_before,ramp_ok=ramp_ok)
        elif case=='W3-result-delivery-delay':
            # W3 must NOT trip the watchdog: the Worker keeps heartbeating and the
            # only effect is that candidates arrive after their deadline.
            # W3 proves a delayed candidate is REFUSED, not that the run dies.
            # A 260 ms delay pushes delivery past both the 150 ms deadline and the
            # 200 ms tick boundary, so the admission gate rejects it as wrong_tick
            # (that check precedes the late check). Both reasons are valid
            # refusals; what must NOT happen is the run going terminal for it.
            assert late_candidates>=1,'W3 never observed a refused late candidate'
            result.update(late_refused=late_candidates)
            result.update(W3_observed=True,accepted_pairs=accepted_pairs,
                          late_candidates=late_candidates,
                          pairs_before_transition=pairs_before,
                          ramp_ok=ramp_ok,
                          worker_delay_ms=reg.get('worker_delay_ms',0))
        elif case=='W2-native-boundary-hold':
            # W2 is not a stall case and must not be judged by W1's criteria.
            # Its evidence is: the boundary was entered at the registered target,
            # at least the registered number of complete business ticks followed,
            # one release frame was written, and the Worker reported the
            # resulting disposition.
            reg_job=int(w2['job_id'])
            reg_ord=int(w2['ordinal'])
            assert w2_entered_at is not None, \
                'W2 never observed the Worker entering its registered boundary'
            assert w2_entered_row.get('job_id')==reg_job, \
                'W2 boundary entered for job %r, registered %r'%(
                    w2_entered_row.get('job_id'),reg_job)
            assert w2_entered_row.get('ordinal')==reg_ord, \
                'W2 boundary entered at ordinal %r, registered %r'%(
                    w2_entered_row.get('ordinal'),reg_ord)
            assert w2_release_sent, 'W2 never wrote its release frame'
            assert w2_result is not None, 'W2 never observed a boundary result'
            assert w2_result.get('job_id')==reg_job, \
                'W2 result attributed to job %r, registered %r'%(
                    w2_result.get('job_id'),reg_job)
            assert w2_result.get('ordinal')==reg_ord, \
                'W2 result attributed to ordinal %r, registered %r'%(
                    w2_result.get('ordinal'),reg_ord)
            assert len(w2_ticks_after_enter)>=w2_required_ticks, \
                'W2 observed %d complete ticks after entry, registered %d'%(
                    len(w2_ticks_after_enter),w2_required_ticks)
            result.update(W2_observed=True,
                          accepted_pairs=accepted_pairs,
                          ramp_ok=ramp_ok,
                          pairs_before_transition=pairs_before,
                          pairs_after_transition=pairs_after,
                          w2_boundary_entered=True,
                          w2_entered_row=w2_entered_row,
                          w2_release_sent=True,
                          w2_release_frame_sha256=__import__('hashlib').sha256(
                              w2_release_frame).hexdigest(),
                          w2_ticks_after_enter=list(w2_ticks_after_enter),
                          w2_result=w2_result,
                          transition_ns=transition_ns,
                          transition_reason=transition_reason,
                          watchdog_ns=watchdog_ns)
        else:
            assert accepted_pairs>=1,'W1 needs at least one accepted dual API pair before the stall'
            assert stall_entered,'W1 never observed the Worker entering its registered stall'
            assert transition_ns is not None,'W1 never observed a worker_unusable_transition'
            assert transition_reason=='active_watchdog','W1 transition reason is %r, not active_watchdog'%transition_reason
            assert watchdog_ns is not None,'W1 missing the active_watchdog Source row'
            result.update(W1_observed=True,accepted_pairs=accepted_pairs,
                      stall_entered=stall_entered,stall_released=stall_released,
                      stall_enter_ns=stall_enter_ns,stall_release_ns=stall_release_ns,
                      stall_duration_ns=(stall_release_ns-stall_enter_ns) if (stall_enter_ns and stall_release_ns) else None,
                      transition_ns=transition_ns,transition_reason=transition_reason,
                      watchdog_ns=watchdog_ns,pairs_before_transition=pairs_before,
                      pairs_after_transition=pairs_after,ramp_ok=ramp_ok,
                      new_job_after_transition=new_job_after,
                      new_candidate_after_transition=new_candidate_after,
                      max_capability_age_while_stalled_ns=max_cap_age_while_stalled,
                      capability_stayed_live=cap_after_stall is not None,
                      renewals_during_stall=renewals_during_stall,
                      last_renewal_ns=last_renewal_ns)
        event('w1_observation_window_closed',pairs_after=pairs_after,
              ramp_ok=ramp_ok,new_job=new_job_after,new_candidate=new_candidate_after,
              capability_live=cap_after_stall is not None)
        os.killpg(children['regulator']['process'].pid,signal.SIGINT)
        closed=wait_close('regulator',seconds=20)
        result.update(regulator_returncode=closed['returncode'],
                      regulator_signals=[s['signal'] for s in closed['signals']])

        if case=='W2-native-boundary-hold':
            result.update(w2_boundary_entered=w2_entered_at is not None,
                          w2_entered_row=w2_entered_row,
                          w2_release_sent=w2_release_sent,
                          w2_release_frame_sha256=(__import__('hashlib').sha256(
                              w2_release_frame).hexdigest() if w2_release_frame else None),
                          w2_ticks_after_enter=list(w2_ticks_after_enter),
                          w2_result=w2_result)
        result.update(Source_observer_bytes=cursor.total,Source_observer_rows=cursor.rows)
    except Exception as error:
        result.update(error=repr(error),traceback=__import__('traceback').format_exc());event('driver_failure',error=repr(error))
    finally:
        closed=[]
        for role in ['regulator','fixture','worker','recorder']:
            if role in children:
                if role in closed_by_wait:closed.append(closed_by_wait[role]);continue
                if role=='recorder':time.sleep(.2)
                try:closed.append(stop(role))
                except Exception as error:closed.append({'role':role,'error':repr(error),'group_empty':False});event('close_failure',role=role,error=repr(error))
        for c in children.values():os.close(c['pidfd'])
        # Close this run's release channel on every path, including a failed or
        # partially-completed spawn. Leaving the write end open would make the
        # Worker's EOF depend on when the Driver process exits as a whole.
        for _fd in (w2_read, w2_write):
            if _fd is not None and _fd >= 0:
                try: os.close(_fd)
                except OSError: pass
        w2_read = w2_write = -1
        result['closed_roles']=closed;result['elapsed_seconds']=time.monotonic()-begin
        by_role={r['role']:r for r in closed}
        def rc_is(role,value):return by_role.get(role,{}).get('returncode')==value
        def only_int(role):return [s['signal'] for s in by_role.get(role,{}).get('signals',[])]==['SIGINT']
        # Every role shuts down through the normal SIGINT ladder: the fault is a
        # deliberate in-process hook, never a kill or a freeze.
        common_ok = bool(
            rc_is('regulator',0) and not by_role.get('regulator',{}).get('signals')
            and rc_is('worker',0) and only_int('worker')
            and rc_is('fixture',0) and only_int('fixture')
            and rc_is('recorder',0) and only_int('recorder')
            and len(closed)==4 and all(r.get('group_empty') for r in closed))
        if case=='W2-native-boundary-hold':
            # W2's expected end state is a deliberate isolation, not a clean
            # solve: the Job's 150 ms deadline has passed by the time the release
            # arrives, so the target Job must not enter the C solve. The Worker's
            # own close path then reports fatal and exits non-zero, which is
            # registered here rather than forced to 0.
            #
            # Everything else about shutdown is NOT relaxed: the other roles, the
            # close signals, the empty process groups and any recorded error are
            # still checked. Only the Worker's exit code is registration-specific.
            w2_exp=reg.get('expected',{}).get('w2_exit_codes')
            assert isinstance(w2_exp,dict) and 'worker' in w2_exp, \
                'W2 registration must declare expected.w2_exit_codes.worker'
            worker_rc=by_role.get('worker',{}).get('returncode')
            # The Worker's close signal is checked exactly like the other roles:
            # only its exit *code* is registration-specific (terminal isolation
            # exits non-zero). A SIGTERM escalation or a missing signal must fail.
            w2_worker_signals=[sg['signal'] for sg in by_role.get('worker',{}).get('signals',[])]
            w2_expected_signals=list(reg['expected']['w2_worker_signals'])
            w2_common_ok=bool(
                rc_is('regulator',0) and not by_role.get('regulator',{}).get('signals')
                and w2_worker_signals==w2_expected_signals
                and rc_is('fixture',0) and only_int('fixture')
                and rc_is('recorder',0) and only_int('recorder')
                and len(closed)==4 and all(r.get('group_empty') for r in closed)
                and result.get('error') is None)
            # The isolation transition is a *registered* consequence, not a
            # failure: after a verified expired, the Worker goes fatal and the
            # Regulator marks it unusable. A matching reason is not enough — if a
            # transition happened it must not predate the Worker's own verified
            # expired fact, otherwise the run was unusable for a different reason.
            iso_reason=reg.get('expected',{}).get('w2_isolation_reason','fatal_capability')
            _w2r=result.get('w2_result') or {}
            # The Worker publishes the full boundary record under 'boundary'; the
            # top level only repeats job_id/ordinal/disposition.
            expired_verified_ns=((_w2r.get('boundary') or {}).get('guard_ns')
                                 if isinstance(_w2r.get('boundary'),dict)
                                 else _w2r.get('guard_ns'))
            if result.get('transition_ns') is None:
                tr_ok=True
            else:
                tr_ok=bool(
                    str(result.get('transition_reason'))==iso_reason
                    and isinstance(expired_verified_ns,int)
                    and result['transition_ns']>=expired_verified_ns)
            # No watchdog may have fired while the boundary was held: the release
            # has to arrive before the original 1 s active watchdog.
            w2_no_watchdog=result.get('watchdog_ns') is None
            w2r=result.get('w2_result') or {}
            reg_job=int(w2['job_id']);reg_ord=int(w2['ordinal'])
            # The remaining registration clauses are checked here rather than
            # left as prose. Each reads evidence the run actually produced:
            #   target_job_candidate_registered/published — the Regulator's
            #     candidate_registration rows and the stored candidate set;
            #   target_job_native_calls — the Worker's own boundary record;
            #   active_job_cleared / pending_discard_required — the terminal
            #     Source rows the Worker writes on the fatal path;
            #   backend_terminal — the Backend's terminal flag on the Worker.
            exp=reg.get('expected',{})
            w2_target_registered=reg_job in registered_job_ids
            w2_target_published=reg_job in published_job_ids
            w2_native_calls=int((w2r.get('boundary') or {}).get('ordinal_at_call') or 0) \
                if w2r.get('actual_native_invoked') else 0
            # The Worker never writes `backend_terminal` on the boundary row; the
            # terminal flag lives in the terminal rows and the Worker summary.
            w2_backend_terminal=bool(w2_terminal_evidence.get('backend_terminal'))
            result['w2_backend_terminal']=w2_backend_terminal
            w2_active_cleared=bool(w2_terminal_evidence.get('active_cleared'))
            w2_pending_discarded=bool(w2_terminal_evidence.get('pending_discarded'))
            result['passed']=bool(
                result.get('W2_observed') is True
                and result.get('w2_boundary_entered') is True
                and result.get('w2_release_sent') is True
                and w2r.get('disposition')=='expired'
                and w2r.get('actual_native_invoked') is False
                and w2r.get('job_id')==reg_job and w2r.get('ordinal')==reg_ord
                and result.get('w2_entered_row',{}).get('job_id')==reg_job
                and result.get('w2_entered_row',{}).get('ordinal')==reg_ord
                and len(result.get('w2_ticks_after_enter') or [])>=int(
                    w2.get('ticks_before_release',2))
                and worker_rc==w2_exp['worker']
                and tr_ok
                and w2_no_watchdog
                and w2_target_registered==bool(exp.get('target_job_candidate_registered',False))
                and w2_target_published==bool(exp.get('target_job_candidate_published',False))
                and w2_native_calls==int(exp.get('target_job_native_calls',0))
                and w2_backend_terminal==bool(exp.get('backend_terminal',True))
                and w2_active_cleared==bool(exp.get('active_job_cleared',True))
                and (not exp.get('pending_discard_required') or w2_pending_discarded)
                and result.get('ramp_ok') is True
                and w2_common_ok)
        elif case=='W4-result-delivery-drop':
            result['passed']=bool(result.get('W4_observed')
                                  and result.get('transition_ns') is None
                                  and result.get('watchdog_ns') is None
                                  and result.get('dropped_candidates',0)>=1
                                  and result.get('dropped_target_tick') is not None
                                  and result.get('active_cleared_without_subsequent_job') is True
                                  and result.get('delivery_resumed_after_drop') is True
                                  and result.get('ramp_ok') is True and common_ok)
        elif case=='W3-result-delivery-delay':
            result['passed']=bool(result.get('W3_observed') and
                                  result.get('transition_ns') is None and
                                  result.get('ramp_ok') is True and common_ok)
        else:
            result['passed']=bool(
            result.get('W1_observed')
            and result.get('transition_reason')=='active_watchdog'
            and result.get('stall_entered') is True
            and result.get('capability_stayed_live') is True
            and result.get('max_capability_age_while_stalled_ns',0)<=600000000
            and result.get('pairs_after_transition',0)>=1
            and result.get('ramp_ok') is True
            and result.get('new_job_after_transition') is False
            and result.get('new_candidate_after_transition') is False
            and common_ok)
        publish(out/'driver_result.json',result);journal.close()
        for f in streams:f.close()
    print(json.dumps({'passed':result['passed'],'error':result.get('error'),'elapsed_seconds':result['elapsed_seconds'],'output':str(out)}))
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
