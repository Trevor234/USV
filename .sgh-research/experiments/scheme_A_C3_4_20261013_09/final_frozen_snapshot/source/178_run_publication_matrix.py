"""Test-only v10 writer/header matrix; no ROS or physical output."""
from pathlib import Path
import argparse, errno, hashlib, json, os, select, stat, subprocess, sys, threading, time
from unittest.mock import patch
AUTHOR=Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10')
sys.path.insert(0,str(AUTHOR))
import owned_release

def read_line(p):
 if not select.select([p.stdout],[],[],5)[0]:raise TimeoutError('native probe output deadline')
 line=p.stdout.readline()
 if not line:raise RuntimeError('native probe exited: '+p.stderr.read())
 return json.loads(line)
def run_case(binary,root,kind):
 root.mkdir();p=subprocess.Popen([str(binary),str(root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 reached,resume=threading.Event(),threading.Event();result={};thread=None
 native_fsync=os.fsync;native_write=os.write
 try:
  ready=read_line(p);path=root/'release.json'
  value=dict(schema_version='p1-D1-publisher-release-v1',run_id=ready['identity']['run_id'],producer_instance_id=ready['identity']['producer_instance_id'],startup_manifest_sha256=ready['startup_manifest_sha256'],release_nonce='1'*32,driver_evidence_sha256='2'*64,valid_until_steady_ns=time.monotonic_ns()+3_000_000_000,gates=dict(external_worker_zero_hooks=True,subscriptions_verified=True,unique_dual_channel_owner=True))
  def fsync(fd):
   directory=stat.S_ISDIR(os.fstat(fd).st_mode)
   if kind=='directory_pause' and directory:
    reached.set()
    if not resume.wait(5):raise TimeoutError('directory fsync barrier')
   if kind=='directory_failure' and directory:raise OSError(errno.EIO,'injected directory fsync failure')
   if kind=='file_fsync_failure' and not directory:raise OSError(errno.EIO,'injected file fsync failure')
   return native_fsync(fd)
  def write(fd,data):
   if kind=='write_pause':
    reached.set()
    if not resume.wait(5):raise TimeoutError('write barrier')
   if kind=='write_failure':raise OSError(errno.ENOSPC,'injected write failure')
   return native_write(fd,data)
  def writer():
   try:result.update(returned=True,sha256=owned_release.create_only_json(path,value))
   except BaseException as e:
    result.update(returned=False,error_type=type(e).__name__,error=str(e),errno=getattr(e,'errno',None),cause_type=type(e.__cause__).__name__ if e.__cause__ else None,cause_errno=getattr(e.__cause__,'errno',None),target_visible=getattr(e,'target_visible',None))
  if kind in ('symlink','hardlink','fifo'):
   if kind=='fifo':os.mkfifo(path)
   else:
    (root/'original.json').write_text(json.dumps(value))
    if kind=='symlink':path.symlink_to(root/'original.json')
    else:os.link(root/'original.json',path)
   result={'writer_not_called':True}
  elif kind=='duplicate':
   owned_release.create_only_json(path,value);before=path.read_bytes();before_inode=path.stat().st_ino
   value={**value,'release_nonce':'3'*32};writer();result['original_bytes_and_inode_retained']=path.read_bytes()==before and path.stat().st_ino==before_inode
  else:
   with patch.object(owned_release.os,'fsync',fsync),patch.object(owned_release.os,'write',write):
    thread=threading.Thread(target=writer);thread.start()
    if kind in ('directory_pause','write_pause'):
     if not reached.wait(5):raise TimeoutError('writer barrier not reached')
    else:
     thread.join(5)
     if thread.is_alive():raise TimeoutError('writer completion deadline')
    at_first={'target_exists':path.exists(),'target_lstat_exists':path.is_symlink() or path.exists(),'writer_inflight':thread.is_alive(),'temporary_count':len(list(root.glob('.release.json.*.tmp')))}
    if path.exists():at_first['nlink']=path.stat().st_nlink
    p.stdin.write('poll\n');p.stdin.flush();first=read_line(p)
    resume.set();thread.join(5)
    if thread.is_alive():raise TimeoutError('writer cleanup deadline')
   p.stdin.write('poll\n');p.stdin.flush();second=read_line(p)
  if kind in ('duplicate','symlink','hardlink','fifo'):
   at_first={'target_exists':path.exists(),'nlink':path.lstat().st_nlink,'writer_inflight':False}
   p.stdin.write('poll\n');p.stdin.flush();first=read_line(p)
   p.stdin.write('poll\n');p.stdin.flush();second=read_line(p)
  p.stdin.close();p.wait(timeout=5)
  ok=p.returncode==0
  if kind in ('normal','directory_pause','directory_failure','duplicate'):
   ok=ok and first['released'] and first['gate']['gate_state']=='Released' and second['released'] and at_first['nlink']==1
  elif kind=='write_pause':ok=ok and not first['released'] and first['gate']['gate_state']=='Held' and not at_first['target_exists'] and second['released']
  elif kind in ('file_fsync_failure','write_failure'):ok=ok and not first['released'] and first['gate']['gate_state']=='Held' and not path.exists() and not second['released']
  else:ok=ok and not first['released'] and first['gate']['gate_state']=='Fault' and not first['arm_called'] and not second['released']
  if kind=='directory_pause':ok=ok and at_first['writer_inflight'] and at_first['temporary_count']==0 and result.get('returned') is True
  if kind=='directory_failure':ok=ok and result.get('error_type')=='PublicationAmbiguousError' and result.get('cause_errno')==errno.EIO and result.get('target_visible') is True
  if kind=='duplicate':ok=ok and result.get('errno')==errno.EEXIST and result.get('original_bytes_and_inode_retained')
  if kind=='hardlink':ok=ok and at_first['nlink']==2 and first['gate']['failure_reason']=='gate input is not a bounded, single-link regular file'
  return {'case':kind,'passed':bool(ok),'ready':ready,'release':value,'writer':result,'at_first':at_first,'first_poll':first,'second_poll':second,'native_returncode':p.returncode,'native_stderr':p.stderr.read(),'target_exists_after':path.exists(),'temporary_count_after':len(list(root.glob('.release.json.*.tmp')))}
 finally:
  resume.set()
  if thread is not None:thread.join(5)
  if p.poll() is None:p.kill();p.wait(timeout=5)

def main():
 a=argparse.ArgumentParser();a.add_argument('--binary',required=True);a.add_argument('--root',required=True);a.add_argument('--report',required=True);args=a.parse_args();root=Path(args.root);root.mkdir()
 rows=[]
 for kind in ['normal','directory_pause','directory_failure','file_fsync_failure','write_pause','write_failure','duplicate','symlink','fifo','hardlink']:
  try:rows.append(run_case(Path(args.binary),root/kind,kind))
  except BaseException as e:rows.append({'case':kind,'passed':False,'error_type':type(e).__name__,'error':str(e)})
 report={'schema':'C3.4-A-publication-native-gate-matrix/v1','cases':rows,'passed':all(row['passed'] for row in rows),'native_case_count':len(rows),'author':str(AUTHOR),'writer_sha256':hashlib.sha256((AUTHOR/'owned_release.py').read_bytes()).hexdigest(),'native_header_sha256':hashlib.sha256((AUTHOR/'publisher/include/usv_mpc_cpp/p1_startup_gate.hpp').read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(),'scope':'same-host ext4, test-only injected IO, actual v10 gate; no ROS/plant; arm is always-success fixture','historical_timeout_cause_proven':False,'stage_qualified':False}
 with Path(args.report).open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
 print(json.dumps({'passed':report['passed'],'cases':[(x['case'],x['passed']) for x in rows]}));return 0 if report['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
