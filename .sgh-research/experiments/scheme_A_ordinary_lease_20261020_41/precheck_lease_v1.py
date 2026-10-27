"""Full SDK loader and CLI without ROS initialization."""
import ast,hashlib,importlib.util,json,shlex,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
files=list(D.glob('*.py'))+list((D/'author').rglob('*.py'))+list((D/'verification').glob('*.py'))
for p in files:ast.parse(p.read_bytes())
spec=importlib.util.spec_from_file_location('setup',D/'author/build_c33_v9.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
r=subprocess.run([sys.executable,str(D/'check_loader_environment_v1.py')],capture_output=True,text=True,timeout=35);assert r.returncode==0,r.stdout+r.stderr
cli=subprocess.run(['bash','-c',m.SETUP+'export PYTHONDONTWRITEBYTECODE=1\nexec /usr/bin/python3 '+shlex.quote(str(D/'author/prepare_pair_wakeup_v1.py'))+' --help'],capture_output=True,text=True,timeout=20)
report=dict(passed=cli.returncode==0 and '--v2-case {lease}' in cli.stdout and 'source-terminal-owned-stop-v1' in cli.stdout,returncode=cli.returncode,stdout=cli.stdout,stderr=cli.stderr,
    syntax_files_checked=len(files),driver_sha256=hashlib.sha256((D/'author/prepare_pair_wakeup_v1.py').read_bytes()).hexdigest(),no_ROS_context_created=True,stage_qualified=False)
with (D/'verification/driver_CLI_v1.json').open('x') as f:json.dump(report,f,indent=2)
print(json.dumps(dict(passed=report['passed'],loader_passed=True,ROS_context_created=False)));assert report['passed']
