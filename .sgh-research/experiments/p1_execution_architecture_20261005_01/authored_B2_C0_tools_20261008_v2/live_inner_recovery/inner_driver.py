from pathlib import Path
import sys,os,time,json,signal,hashlib
R=Path(sys.argv[1]);D=Path(sys.argv[2]);count=int(sys.argv[3]);sys.path.insert(0,str(R))
from owned_process_supervisor import Supervisor
py=Path('/usr/bin/python3').resolve();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
signal.signal(signal.SIGINT,lambda *_:None)
sup=Supervisor(D);deadline=time.monotonic()+25
try:
    for role in ('regulator','worker','fixture','recorder')[:count]:
        sup.spawn(role,[str(py),'-B','-c','import time; time.sleep(20)'],dict(os.environ),py,sha(py))
    with (D/'ready.json').open('x') as f:json.dump({'pid':os.getpid(),'count':count},f)
    # Reap these direct children without changing the frozen authorization ledger.
    while time.monotonic()<deadline:
        alive=any(v.process.poll() is None for v in sup.owned.values())
        if not alive and (D/'recovery_done').exists():break
        time.sleep(.02)
finally:
    for item in sup.owned.values():sup.stop(item,.5,1,1)
    sup.close()
