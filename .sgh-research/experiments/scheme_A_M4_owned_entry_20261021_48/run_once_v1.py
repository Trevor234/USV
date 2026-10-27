#!/usr/bin/env python3
"""Exactly one registered isolated run with owned orphan cleanup, no retry.

Linux subreaper lineage, recorded spawn identities, run argv, executable hash,
start ticks and process group are checked before emergency signals. A remaining
group is cleanup_failed and cannot be called a successful restart boundary.
"""
import ast
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent


def pin(p):
    b=Path(p).read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def read(p):return json.loads(Path(p).read_bytes())


def proc(pid):
    root=Path('/proc')/str(pid);s=(root/'stat').read_text();v=s[s.rfind(')')+1:].split()
    return {'pid':pid,'state':v[0],'ppid':int(v[1]),'pgid':int(v[2]),'start':int(v[19]),
            'exe':os.readlink(root/'exe'),'sha':pin(root/'exe')['sha256'],
            'argv':[x.decode() for x in (root/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')]}


def empty(group):
    try:os.killpg(group,0);return False
    except ProcessLookupError:return True


def main():
    assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0,'subreaper required'
    regfile=D/'implementation/normal_registration_v1.json';reg=read(regfile)
    assert reg['automatic_retries']==0 and reg['scope']=='M4_owned_local_nominal_only_v1' and reg['outer_timeout_seconds']==90
    assert read(D/'verification/component_verification_v3.json')['passed']
    assert read(D/'verification/native_entry_rejections_v1.json')['passed']
    lock=read(D/'preflight/prerun_source_lock_v1.json')
    for path,row in lock['files'].items():assert pin(path)==row,'registered input changed: '+path
    registry=read(reg['registry']);assert pin(reg['registry'])['sha256']==reg['registry_sha256']
    assert not Path(reg['output']).exists(),'registered run already exists; no automatic retry'
    # Keep a finite initial process census; never stop unrelated processes.
    existing=[]
    selected={r['binary']:r['binary_sha256'] for r in registry['roles'].values()}
    for root in Path('/proc').iterdir():
        if not root.name.isdigit():continue
        try:
            exe=os.readlink(root/'exe')
            if exe in selected:existing.append({'pid':int(root.name),'exe':exe})
        except (OSError,ValueError):pass
    assert not existing,'selected owned executable already running'
    setupfile=D.parent/'scheme_A_owned_business_start_20261020_39/author/build_c33_v9.py'
    tree=ast.parse(setupfile.read_bytes());setup=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SETUP' for t in n.targets))
    setup+='\nexport ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120 RMW_IMPLEMENTATION=rmw_fastrtps_cpp PYTHONDONTWRITEBYTECODE=1\n'
    script=D/'implementation/launch_registered_normal_v1.sh'
    with script.open('x') as f:f.write('set -e\n'+setup+'\nexec /usr/bin/python3 -B '+shlex.quote(registry['driver'])+' --registration '+shlex.quote(str(regfile))+'\n')
    out=D/'evidence/normal_outer_stdout_v1.log';err=D/'evidence/normal_outer_stderr_v1.log'
    started=time.monotonic();cleanup=[];timed_out=False
    with out.open('xb') as stdout,err.open('xb') as stderr:
        child=subprocess.Popen(['/bin/bash',str(script)],stdout=stdout,stderr=stderr,start_new_session=True)
        driver_start=int((Path('/proc')/str(child.pid)/'stat').read_text().split(')')[-1].split()[19])
        try:child.wait(timeout=90)
        except subprocess.TimeoutExpired:
            timed_out=True
            current=proc(child.pid);assert current['start']==driver_start and current['pgid']==child.pid
            os.killpg(child.pid,signal.SIGINT)
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                current=proc(child.pid);assert current['start']==driver_start;os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=1)
        # Driver should have closed/reaped every role; the fallback is also
        # needed if it dies between Popen and publishing its spawn receipt.
        candidates={}
        runroot=Path(reg['output'])
        if runroot.is_dir():
            for p in runroot.glob('*/spawn.json'):
                row=read(p);candidates[row['pid']]={'start':row['process_start_ticks'],'origin':'Driver recorded spawn'}
        for root in Path('/proc').iterdir():
            if not root.name.isdigit():continue
            try:
                p=proc(int(root.name))
                if p['ppid']==os.getpid() and p['exe'] in selected and p['sha']==selected[p['exe']] and any(reg['run_id'] in a for a in p['argv']):
                    candidates.setdefault(p['pid'],{'start':p['start'],'origin':'actual subreaper direct lineage and registered run argv'})
            except (OSError,ValueError,AssertionError):pass
        for pid,record in candidates.items():
            row={'pid':pid,**record,'signals':[]}
            try:
                p=proc(pid)
                assert p['start']==record['start'] and p['pgid']==pid and p['exe'] in selected and p['sha']==selected[p['exe']] and any(reg['run_id'] in a for a in p['argv']),'foreign process/group guard'
                fd=os.pidfd_open(pid)
                try:
                    for sig,budget in [(signal.SIGINT,2.5),(signal.SIGTERM,1),(signal.SIGKILL,1)]:
                        if empty(pid):break
                        try:
                            p=proc(pid);assert p['start']==record['start'] and p['pgid']==pid
                        except FileNotFoundError:break
                        os.killpg(pid,sig);row['signals'].append(sig.name)
                        until=time.monotonic()+budget
                        while time.monotonic()<until:
                            try:os.waitpid(pid,os.WNOHANG)
                            except ChildProcessError:pass
                            if empty(pid):break
                            time.sleep(.02)
                finally:os.close(fd)
            except FileNotFoundError:pass
            except (OSError,AssertionError) as error:row['error']=repr(error)
            row['group_empty']=empty(pid);cleanup.append(row)
    result_path=Path(reg['output'])/'driver_result.json'
    result=read(result_path) if result_path.exists() else {'passed':False,'error':'Driver result absent'}
    passed=child.returncode==0 and not timed_out and result.get('passed') is True and all(r['group_empty'] and not r.get('signals') for r in cleanup)
    report={'schema':'M4-one-registered-normal-launch/v1','passed':passed,'driver_returncode':child.returncode,
            'driver_timed_out':timed_out,'driver_result':result,'emergency_cleanup':cleanup,'selected_preexisting_processes':existing,
            'elapsed_seconds':time.monotonic()-started,'registration':str(regfile),'registration_sha256':pin(regfile)['sha256'],
            'ordinary_production_release_enabled':False,'isolated_nominal_only':True,'M4_stage_qualified':False,'P1_qualified':False,'research_conclusion':False}
    with (D/'evidence/normal_launch_v1.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({'passed':passed,'driver_returncode':child.returncode,'error':result.get('error'),'elapsed_seconds':report['elapsed_seconds'],'emergency_signals':[s for r in cleanup for s in r['signals']]}))
    return 0 if passed else 2


if __name__=='__main__':raise SystemExit(main())
