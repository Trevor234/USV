"""One locked current normal-source window; reuse exact SDK and five roles."""
import ast,hashlib,json,shlex,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def main():
    plan=json.loads((D/'preflight/normal_source_preregistration_v2.json').read_bytes())
    lock=json.loads((D/'preflight/prerun_source_lock_v2.json').read_bytes())
    assert plan['verdict']=='GO' and plan['runner']==pin(__file__) and plan['source_lock']==pin(D/'preflight/prerun_source_lock_v2.json')
    assert plan['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    for p,f in lock['files'].items():assert pin(p)==f,'locked input changed:'+p
    assert not (D/'author/runs'/plan['run_id']).exists()
    t=ast.parse((D/'author/build_c33_v9.py').read_text())
    setup=next(ast.literal_eval(n.value) for n in t.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='SETUP' for x in n.targets))
    argv=['/usr/bin/python3',str(D/'author/prepare_pair_wakeup_v1.py'),'--run-id',plan['run_id'],'--reference-speed','0.05',
          '--controlled-case','C','--domain','199','--v2-case','none','--close-profile','normal','--supervision-profile','none']
    script=setup+'export PYTHONDONTWRITEBYTECODE=1 ROS_DOMAIN_ID=199\nexec timeout --signal=INT --kill-after=15s 70s '+shlex.join(argv)
    started=time.monotonic_ns()
    with (D/'evidence/driver_normal_source20s_02.log').open('xb') as f:
        rc=subprocess.run(['bash','-c',script],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=90).returncode
    for p,row in lock['files'].items():assert pin(p)==row,'input changed during run:'+p
    report={'schema':'current-normal-source20s-launch-v1','run_id':plan['run_id'],'returncode':rc,
      'started_ns':started,'finished_ns':time.monotonic_ns(),'elapsed_ns':time.monotonic_ns()-started,
      'inputs_unchanged':True,'source_lock':plan['source_lock'],'external_timeout_triggered':rc in [124,137],
      'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
    with (D/'postrun/launch_normal_source20s_02_v1.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report));return rc
if __name__=='__main__':raise SystemExit(main())
