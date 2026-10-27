from pathlib import Path
import datetime, hashlib, json, shutil, subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
PREVIOUS = ROOT.parent / 'scheme_A_M4_model_setter_review_20261026_127'
PKG = REPO / 'usv_mpc_ws/src/usv_mpc_cpp'

def pin(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')

for directory in ['documents', 'implementation', 'evidence/inputs', 'postrun', 'patches']:
    (ROOT / directory).mkdir(parents=True, exist_ok=True)
assert not (ROOT / 'evidence/inputs/manifest_v1.json').exists()
previous = {str(p): pin(p) for p in sorted(PREVIOUS.rglob('*')) if p.is_file()}
raw = subprocess.check_output(['git', '-c', 'core.quotepath=false', 'status', '--porcelain=v1', '-z', '-uall'], cwd=REPO)
entries = raw.decode().split('\0')
workspace = {}
i = 0
while i < len(entries):
    entry = entries[i]
    i += 1
    if not entry:
        continue
    name = entry[3:]
    p = REPO / name
    workspace[name] = {'kind': 'file', **pin(p)} if p.is_file() else {'kind': 'directory' if p.is_dir() else 'absent'}
    if entry[0] in 'RC' or entry[1] in 'RC':
        i += 1
inputs = {}
for variant in ['baseline', 'checked_init']:
    source = PREVIOUS / 'implementation' / variant
    dest = ROOT / 'implementation' / variant
    shutil.copytree(source, dest)
    for p in source.rglob('*'):
        if p.is_file():
            inputs[str(p)] = pin(p)
for name in ['src/casadi_backend.cpp', 'include/usv_mpc_cpp/casadi_backend.hpp', 'CMakeLists.txt', 'src/mpc_solver.cpp']:
    inputs[str(PKG/name)] = pin(PKG/name)
    dest = ROOT / 'implementation/current' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PKG/name, dest)
archive = PREVIOUS / 'build/attempt02/libgenerated_current.a'
shutil.copy2(archive, ROOT / 'implementation/libgenerated_current.a')
inputs[str(archive)] = pin(archive)
for name in ['implementation/cmake/CMakeLists.txt', 'evidence/current_build_identity_v1.json', 'postrun/next_plan_v1.json']:
    inputs[str(PREVIOUS/name)] = pin(PREVIOUS/name)
casadi_dir = Path(subprocess.check_output(['python3', '-c', 'import casadi,pathlib;print(pathlib.Path(casadi.__file__).parent)'], text=True).strip())
libraries = {str(p): pin(p) for p in [Path('/home/trevor/acados/lib')/n for n in ['libacados.so', 'libblasfeo.so', 'libhpipm.so']]}
for name in ['libcasadi.so', 'libcasadi_nlpsol_ipopt.so', 'libipopt.so']:
    libraries[str(casadi_dir/name)] = pin(casadi_dir/name)
save(ROOT/'evidence/inputs/manifest_v1.json', {
    'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
    'files': inputs, 'previous127_files': previous, 'runtime_libraries': libraries,
    'workspace_files': workspace, 'git_porcelain_z': raw.decode(),
    'casadi_dir': str(casadi_dir), 'generated_archive_origin': str(archive),
    'generated_archive_recipe': 'Batch127 current vendored generated C, GCC -O1; reused byte-for-byte, not an installed solver archive',
})
save(ROOT/'postrun/plan_v1.json', {
    'scope': 'Actual factory routing of batch127 checked constructor in two standalone build modes',
    'sequence': ['freeze input/protection population', 'real CasADi ABI link probes',
                 'unchanged factory baseline and checked constructor matrix',
                 'only if reproduced: isolated finite-p_global factory admission patch',
                 'behavior parity, targeted runtime assertion mutations, patch replay',
                 'protection and MPC exact-population readback'],
    'requirements': ['real current factory source compiled', 'actual CasADi constructor and finite solves, no fake backend',
                     'every capsule allocation/free counted', 'no timing qualification',
                     'timeout/crash/build failure never counted as mutation rejection'],
    'limits': {'production_edits': 0, 'ROS_initializations': 0, 'owned_runs': 0,
               'no_RawBackend_or_Worker_change': True, 'no_codegen': True,
               'no_fallback_policy_redesign': True},
    'qualification': {k: False for k in ['M4','F6','P1','plant','hard_realtime']},
})
print(json.dumps({'inputs':len(inputs), 'protected127':len(previous), 'workspace_entries':len(workspace), 'casadi_dir':str(casadi_dir)}))
