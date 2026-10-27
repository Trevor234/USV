"""Fresh saved-observation v10 receipt fsync failure; test-only wrapper."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,time
D=Path(__file__).parent
N=Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10');sys.path.insert(0,str(N));import owned_release
sys.path.insert(0,str(D.parent/'A_publication/reproductions'));from run_publication_matrix import read_line
ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);a=ap.parse_args()
root=D/a.name;root.mkdir();binary=D/'probe_receipt_fsync_fault';p=subprocess.Popen([str(binary),str(root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
try:
 ready=read_line(p)
 with (root/'native_ready.json').open('x') as f:json.dump(ready,f,indent=2);f.write('\n')
 release=dict(schema_version='p1-D1-publisher-release-v1',run_id=ready['identity']['run_id'],producer_instance_id=ready['identity']['producer_instance_id'],startup_manifest_sha256=ready['startup_manifest_sha256'],release_nonce='1'*32,driver_evidence_sha256='2'*64,valid_until_steady_ns=time.monotonic_ns()+3_000_000_000,gates=dict(external_worker_zero_hooks=True,subscriptions_verified=True,unique_dual_channel_owner=True))
 driver_digest=owned_release.create_only_json(root/'release.json',release)
 polls=[]
 for i in range(2):
  p.stdin.write('poll\n');p.stdin.flush();row=read_line(p);polls.append(row)
  with (root/('native_poll_'+str(i+1)+'.json')).open('x') as f:json.dump(row,f,indent=2);f.write('\n')
 p.stdin.close();p.wait(timeout=5);stderr=p.stderr.read()
 with (root/'native_stderr.log').open('x') as f:f.write(stderr)
 first,second=polls;receipt=root/'publisher/release_receipt.json'
 passed=(p.returncode==0 and first['receipt_visible'] and first['receipt_nlink']==1 and not first['released'] and first['arm_called'] and first['gate']['gate_state']=='Fault' and first['gate']['failure_phase']=='receipt_io' and first['gate']['receipt_io_completed'] is False and first['gate']['final_freshness_now_ns'] is None and first['gate']['commit_steady_ns'] is None and first['gate']['original_freshness_read_count']==2 and not second['released'] and second['gate']['gate_state']=='Fault')
 report={'schema':'C3.4-D-receipt-directory-fsync-fault/v1','passed':passed,'ready':ready,'release':release,'driver_release_returned':True,'driver_release_digest':driver_digest,'first_poll':first,'second_poll':second,'native_returncode':p.returncode,'native_stderr':stderr,'receipt_sha256':hashlib.sha256(receipt.read_bytes()).hexdigest(),'receipt_content':json.loads(receipt.read_bytes()),'probe_source_sha256':hashlib.sha256((D/'probe_receipt_fsync_fault.cpp').read_bytes()).hexdigest(),'probe_binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'production_hook_added':False,'ROS_or_physical_output':False,'historical_timeout_cause_proven':False,'stage_qualified':False}
 with (D/(a.name+'.json')).open('x') as f:json.dump(report,f,indent=2);f.write('\n')
 print(json.dumps({'passed':passed,'gate':first['gate']['gate_state'],'phase':first['gate']['failure_phase'],'receipt_visible':first['receipt_visible'],'receipt_io_completed':first['gate']['receipt_io_completed']}));assert passed
finally:
 if p.poll() is None:p.kill();p.wait(timeout=5)
