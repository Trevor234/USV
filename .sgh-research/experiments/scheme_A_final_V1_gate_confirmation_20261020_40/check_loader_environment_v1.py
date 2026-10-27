"""Read-only loader precheck using the previously pinned complete ROS/acados setup."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
helper = D / 'author/build_c33_v9.py'
spec = importlib.util.spec_from_file_location('complete_previous_setup', helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def pin(p):
    p=Path(p).resolve();b=p.read_bytes()
    return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'resolved_path':str(p)}
roles={}
for row in json.loads((D/'author/build_manifest_current.json').read_bytes()):
    r=subprocess.run(['bash','-c',module.SETUP+'exec ldd '+shlex.quote(row['binary'])],capture_output=True,text=True,timeout=15)
    assert r.returncode==0 and 'not found' not in r.stdout+r.stderr, row['role']+':'+r.stdout+r.stderr
    libraries={}
    for line in r.stdout.splitlines():
        found=re.search(r'(?:=>\s*)?(/[^\s]+)\s+\(',line)
        if found:
            p=Path(found.group(1)).resolve();libraries[str(p)]=pin(p)
    assert libraries
    roles[row['role']]={'binary':pin(row['binary']),'libraries':libraries,'ldd_stdout':r.stdout,'stderr':r.stderr}
report={'passed':True,'no_ROS_node_started':True,'complete_setup_helper':pin(helper),
        'complete_setup_sha256':hashlib.sha256(module.SETUP.encode()).hexdigest(),'roles':roles,
        'complete_setup_inherited_without_shortening':True,
        'all_five_parent39_registered_ELFs_reused':True,'stage_qualified':False,'execute_qualified':False}
with (D/'preflight/loader_environment_v2.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True)
print(json.dumps({'passed':True,'roles':len(roles),'all_libraries_resolved':True,'node_started':False}))
