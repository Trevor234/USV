#!/usr/bin/env python3
"""Actual scoped early Worker exit verifies driver failure-path cleanup only."""
from pathlib import Path
import hashlib,json,os,signal,subprocess,sys,time
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent;sys.path.insert(0,str(D));import build_and_verify_v2 as B
sys.path.insert(0,str(B.N));from owned_release import actual_process
N=B.N;CASE='worker_early_exit';R=N/'runs/owned_C39_worker_early_exit_01';O=D/'runs'/CASE

def main():
 O.mkdir(exist_ok=False);assert not R.exists()
 assert json.loads((D/'component/native_attempt01/result.json').read_text())['passed']
 for p,x in json.loads((D/'preregister/helper_pins_v2.json').read_text())['files'].items():assert B.sha(p)==x['sha256'],p
 B.verify(json.loads((N/'source_bundles_current.json').read_text())['observer'])
 script=O/'run_owned.sh';import shlex
 script.write_text('set -e\n'+B.SETUP+'export ROS_DOMAIN_ID=153\nexec timeout --signal=TERM --kill-after=5s 75s '+shlex.join(['/usr/bin/python3','-B',str(N/'prepare_fixture.py'),'--run-id',R.name,'--domain','153','--mode','positive','--c38-case','worker_post_exit'])+'\n')
 start=time.monotonic_ns();sent=False;process=None
 try:
  with (O/'run_owned.log').open('xb') as log:
   process=subprocess.Popen(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
   until=time.monotonic_ns()+35_000_000_000
   while time.monotonic_ns()<until:
    assert process.poll() is None,'driver exited before declared fault'
    sf=R/'observer/source.jsonl';mf=R/'worker/owned_manifest.json';pf=R/'preparation_evidence.json'
    if sf.is_file() and mf.is_file() and pf.is_file() and (R/'publisher/release_receipt.json').exists():
     rows=[json.loads(l) for l in sf.read_bytes().splitlines(keepends=True) if l.endswith(b'\n')]
     ready=[r for r in rows if r.get('type')=='legacy_ready']
     if ready:
      manifest=json.loads(mf.read_text());identity=actual_process(manifest['pid']);asset=json.loads((N/'build_manifest_current.json').read_text());asset=next(x for x in asset if x['role']=='worker')
      assert manifest['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
      assert identity['pid']==manifest['pid'] and identity['start_ticks']==manifest['process_start_ticks'] and identity['exe']==manifest['exe']==asset['binary'] and identity['exe_sha256']==manifest['binary_sha256']==asset['binary_sha256']
      before=time.monotonic_ns();os.kill(identity['pid'],signal.SIGINT);after=time.monotonic_ns();sent=True
      B.write(O/'controlled_signal.json',{'schema':'C3.9-actual-scoped-worker-SIGINT/v1','target':'worker','identity':identity,'worker_manifest_sha256':B.sha(mf),'native_legacy_ready_source':ready[-1],'signal':2,'call_start_ns':before,'call_return_ns':after,'domain':153,'no_other_process_signalled':True,'stage_qualified':False});break
    time.sleep(.01)
   assert sent,'native prepared Worker fault target never observed'
   rc=process.wait(timeout=45)
 except BaseException:
  # Only the harness-owned timeout/driver group can be terminated here. Driver
  # finally keeps registry cleanup; no existing external process is targeted.
  if process and process.poll() is None:
   process.send_signal(signal.SIGTERM)
   try:process.wait(timeout=20)
   except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
  raise
 result=json.loads((R/'result.json').read_text());roles={'publisher','worker','observer','synthetic_source','recorder'}
 ledger=[json.loads(l) for l in (R/'owned_process_ledger.jsonl').read_text().splitlines()]
 clean=[r for r in ledger if r['type']=='cleanup_result'];summaries=[r for r in ledger if r['type']=='supervisor_summary'];rows=[json.loads(l) for l in (R/'observer/source.jsonl').read_text().splitlines()]
 witness=json.loads((R/'observer/witness.json').read_text());before={str(p):B.sha(p) for p in R.rglob('*') if p.is_file()}
 issues=[]
 def need(ok,code):
  if not ok:issues.append(code)
 need(rc==2 and result['passed'] is False and result['diagnostic_case_completed'] is False,'actual_driver_failure_preserved')
 need(result.get('finite_prepare_and_measurement_passed') is not True and bool(result.get('error')),'measurement_failure_recorded')
 need(any(r.get('action')=='C3.8 owned close scenario' and 'actual Worker publications while paused absent' in r.get('error','') for r in result['close_errors']),'new_scenario_failure_before_Publisher_stop_exercised')
 need(result['cleanup_complete'] is True and result['cleanup_within_budget'] is True and set(result['cleanup'])==roles and all(r['cleanup_complete'] and r['remaining_members']==[] for r in result['cleanup'].values()),'entire_registered_cleanup_complete')
 need({r['name'] for r in clean}==roles and len(clean)==5 and all(r['cleanup_complete'] and r['remaining_members']==[] for r in clean),'five_actual_ledger_cleanup_results')
 need(len(summaries)==1 and summaries[0].get('cleanup_failed') is False,'supervisor_terminal_no_residual')
 need(all(v==0 for v in result['owned_role_returncodes'].values()),'all_actual_role_returncodes_zero')
 need(len([r for r in ledger if r['type']=='signal' and r.get('name')=='publisher'])==1,'fallback_actual_Publisher_signal')
 need(witness['closed'] is True and witness['observation_complete'] is True and witness['business_ready_observed'] is False and witness['counters']['accepted_activations']==0,'terminal_Witness_no_BusinessReady_Accepted')
 need(sum(r.get('type')=='diagnostic_c38_gate_paused' for r in rows)==1,'actual_gate_pause_before_failure')
 need(before=={str(p):B.sha(p) for p in R.rglob('*') if p.is_file()},'raw_inputs_unchanged')
 report={'schema':'C3.9-driver-failure-cleanup-check/v1','passed':not issues,'issues':issues,'driver_returncode':rc,'controlled_worker_signal_sent':sent,'component_scope':'Actual early Worker exit, actual native gate pause then publication precondition failure; complete registered fallback cleanup only. No normal or queued-interface/payload qualification.', 'raw_run':str(R),'cleanup':result['cleanup'],'error':result.get('error'),'close_errors':result['close_errors'],'Witness_observation_complete':witness['observation_complete'],'actual_Accepted':0,'input_sha256_before':before,'input_sha256_after':before,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 B.write(O/'check_result.json',report);B.write(O/'result.json',result);print(json.dumps({'passed':report['passed'],'issues':issues,'driver_returncode':rc,'roles_reaped':len(clean)}));return 0 if report['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
