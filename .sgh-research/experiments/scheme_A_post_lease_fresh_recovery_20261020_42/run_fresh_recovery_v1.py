"""Exactly one locked healthy fresh-identity run after actual lease41 closure."""
import hashlib,importlib.util,json,shlex,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def main():
    plan=json.loads((D/'preflight/fresh_preregistration_v1.json').read_bytes());lock=json.loads((D/'preflight/prerun_source_lock_v1.json').read_bytes());env=json.loads((D/'preflight/loader_environment_v2.json').read_bytes())
    assert plan['verdict']=='GO' and env['passed'] and plan['runner']==pin(__file__)
    assert plan['source_lock']==pin(D/'preflight/prerun_source_lock_v1.json') and plan['loader']==pin(D/'preflight/loader_environment_v2.json')
    assert plan['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    for p,f in lock['files'].items():assert pin(p)==f,'locked input changed:'+p
    run=plan['run_id'];assert not (D/'author/runs'/run).exists()
    spec=importlib.util.spec_from_file_location('setup',D/'author/build_c33_v9.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert hashlib.sha256(m.SETUP.encode()).hexdigest()==env['complete_setup_sha256']
    argv=['/usr/bin/python3',str(D/'author/prepare_pair_wakeup_v1.py'),'--run-id',run,'--reference-speed','0.05','--controlled-case','C','--domain','196','--v2-case','none','--close-profile','normal','--supervision-profile','none']
    script=m.SETUP+'export PYTHONDONTWRITEBYTECODE=1 ROS_DOMAIN_ID=196\nexec timeout --signal=INT --kill-after=20s 55s '+shlex.join(argv)
    start=time.monotonic_ns()
    with (D/'evidence'/('driver_'+run+'.log')).open('xb') as log:rc=subprocess.run(['bash','-c',script],stdout=log,stderr=subprocess.STDOUT,timeout=80).returncode
    finish=time.monotonic_ns()
    for p,f in lock['files'].items():assert pin(p)==f,'locked input changed during run:'+p
    report=dict(run_id=run,case='post lease41 fresh identity two healthy jobs and original normal resource close',returncode=rc,started_ns=start,finished_ns=finish,elapsed_ns=finish-start,
        external_timeout_triggered=rc in [124,137],inputs_unchanged=True,source_lock=plan['source_lock'],stage_qualified=False,execute_qualified=False,research_conclusion=False)
    with (D/'postrun'/('launch_'+run+'_v1.json')).open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(report));return rc
if __name__=='__main__':raise SystemExit(main())
