"""Closed raw SDK decoding only; no ROS context or publication."""
from pathlib import Path
import importlib.util,subprocess,sys,shlex
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('setup',D/'author/build_c33_v9.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
argv=['/usr/bin/python3',str(D/'audit_fresh_actual_v2.py'),'--run','fresh_after_lease_01','--output',str(D/'postrun/fresh_recovery_actual_audit_v2.json')]
r=subprocess.run(['bash','-c',m.SETUP+'export PYTHONDONTWRITEBYTECODE=1\nexec '+shlex.join(argv)],capture_output=True,text=True,timeout=45)
with (D/'evidence/closed_audit_stdout_v2.log').open('x') as f:f.write(r.stdout+'\nSTDERR\n'+r.stderr)
print(r.stdout);print(r.stderr,file=sys.stderr);raise SystemExit(r.returncode)
