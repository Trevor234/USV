"""Loader and CLI checks with complete setup; no ROS context is created."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('complete_setup',D/'author_r2/build_c33_v9.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
for leaf in ['author_r2/prepare_pair_wakeup_v1.py','author_r2/ordinary_supervision_v1.py','audit_ordinary_core_v1.py','audit_ordinary_actual_v1.py']:
    ast.parse((D/leaf).read_text())
assert json.loads((D/'preflight/loader_environment_v2.json').read_bytes())['passed']
cmd=module.SETUP+'export PYTHONDONTWRITEBYTECODE=1\nexec /usr/bin/python3 '+shlex.quote(str(D/'author_r2/prepare_pair_wakeup_v1.py'))+' --help'
cli=subprocess.run(['bash','-c',cmd],capture_output=True,text=True,timeout=20)
report=dict(passed=cli.returncode==0 and 'source-terminal-owned-stop-v1' in cli.stdout,
    returncode=cli.returncode,stdout=cli.stdout,stderr=cli.stderr,driver_sha256=hashlib.sha256((D/'author_r2/prepare_pair_wakeup_v1.py').read_bytes()).hexdigest(),
    no_ROS_context_created=True,no_control_roles_launched=True,stage_qualified=False)
with (D/'verification/driver_CLI_r2_v1.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True)
print(json.dumps(dict(loader_passed=True,CLI_passed=report['passed'],ROS_context_created=False)))
assert report['passed']
