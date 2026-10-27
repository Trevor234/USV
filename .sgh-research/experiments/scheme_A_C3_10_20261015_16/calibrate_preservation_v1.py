"""Exercise each read interception, relative dir_fd resolution, and child propagation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
sys.path.insert(0, str(D))
import protection_v1 as P

root = Path(tempfile.mkdtemp(prefix='c310_preservation_calibration_'))
trace = D / 'preflight/calibration_trace_v1'
trace.mkdir(exist_ok=False)
files = {name: root / (name + '.txt') for name in ['path', 'builtins', 'io', 'dirfd', 'Reader', 'child']}
for name, path in files.items():
    path.write_bytes(name.encode())
code = '''import io,os,sys,subprocess,json
from pathlib import Path
import acceptance_core_v1 as C
root=Path(sys.argv[1]); assert (root/'path.txt').read_bytes()==b'path'
assert open(root/'builtins.txt','rb').read()==b'builtins'
assert io.open(root/'io.txt','rb').read()==b'io'
fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
child=os.open('dirfd.txt',os.O_RDONLY,dir_fd=fd); assert os.read(child,99)==b'dirfd'
os.close(child);os.close(fd)
assert C.Reader().raw(root/'Reader.txt')==b'Reader'
assert len(list(os.scandir(root)))==6
subprocess.run([sys.executable,'-B','-c',"from pathlib import Path;import sys;assert Path(sys.argv[1]).read_bytes()==b'child'",str(root/'child.txt')],check=True)
'''
env = dict(os.environ, PYTHONPATH=str(D / 'preservation_trace') + os.pathsep + str(Path(P.C.__file__).parent),
           PYTHONDONTWRITEBYTECODE='1', C310_TRACE_DIRECTORY=str(trace), C310_TRACE_CALIBRATION_ROOT=str(root))
run = subprocess.run([sys.executable, '-B', '-c', code, str(root)], env=env, capture_output=True, timeout=30)
rows = [json.loads(line) for path in trace.glob('*.jsonl') for line in path.read_bytes().splitlines()]
assert run.returncode == 0, run.stderr.decode()
paths = {r['path'] for r in rows if r['event'] == 'file'}
assert set(map(str, files.values())) <= paths
assert any(r['event'] == 'verified_read' and r['path'] == str(files['Reader']) for r in rows)
assert any(r['event'] == 'directory' and r['path'] == str(root) for r in rows)
starts = {r['pid'] for r in rows if r['event'] == 'start'}
ends = {r['pid'] for r in rows if r['event'] == 'end'}
children = {r['child_pid'] for r in rows if r['event'] == 'python_child'}
assert len(starts) == 2 and starts == ends and children < starts and len(children) == 1
P.write_new(D / 'preflight/calibration_preservation_v1.json', {
    'passed': True, 'six_distinct_read_paths_captured': True, 'relative_dir_fd_resolved': True,
    'Reader_exact_returned_bytes_captured': True, 'directory_population_interception': True,
    'python_descendants_traced_to_exit': True, 'processes': len(starts),
    'fixture': str(root), 'stderr': run.stderr.decode(),
    'trace_sha256': {str(path): P.stable_sha(path)['sha256'] for path in trace.glob('*.jsonl')},
    'helper_sha256': P.stable_sha(D / 'protection_v1.py')['sha256'],
    'tracer_sha256': P.stable_sha(D / 'preservation_trace/sitecustomize.py')['sha256'],
    'stage_qualified': False, 'research_conclusion': False})
print(json.dumps({'passed': True, 'calibration_read_paths': 6, 'processes': 2}))
