"""Full SDK imports for read-only decoding; creates no ROS context or publications."""
from pathlib import Path
import importlib.util,subprocess,sys,shlex
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('setup',D/'author/build_c33_v9.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
script=m.SETUP+'export PYTHONDONTWRITEBYTECODE=1\nexec /usr/bin/python3 '+shlex.quote(str(D/'audit_current_V1_v1.py'))
r=subprocess.run(['bash','-c',script],capture_output=True,text=True,timeout=40)
with (D/'evidence/closed_audit_stdout_v1.log').open('x') as f:f.write(r.stdout+'\nSTDERR\n'+r.stderr)
print(r.stdout);print(r.stderr,file=sys.stderr)
raise SystemExit(r.returncode)
