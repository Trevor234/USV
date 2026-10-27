import hashlib,json,pathlib,subprocess,xml.etree.ElementTree as ET,zipfile
root=pathlib.Path('/home/trevor/USV')
exp=root/'.sgh-research/experiments/v5_scaling_fix_20261003'
before=json.loads((exp/'preflight.json').read_text())
applied=json.loads((exp/'apply.json').read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
changed={d['path'] for d in applied['changed']}
protected={r:dict(before=h,after=digest(root/r)) for r,h in before['sha256'].items() if r not in changed}
assert all(v['before']==v['after'] for v in protected.values()), 'protected baseline changed'
asset=json.loads((exp/'real_assets_validation.json').read_text())
vrx=json.loads((exp/'results/new_physical_n/metrics.json').read_text())
installed=json.loads((exp/'installed_node.json').read_text())
assert asset['passed'] and not asset.get('requires_scope_review',False)
assert vrx['passed_current_interface_checks']
assert installed['module_sha256']==digest(root/'usv_mpc_ws/src/usv_rl_ros/usv_rl_ros/rl_policy_node.py')
tests={}
for label,p in [('export_and_regression',exp/'export_tests.xml'),('ros_source',exp/'ros_tests.xml'),
                ('ros_colcon',root/'usv_mpc_ws/build/usv_rl_ros/pytest.xml')]:
    suites=ET.parse(p).getroot()
    suites=[suites] if suites.tag=='testsuite' else list(suites.iter('testsuite'))
    fields={n:sum(int(s.get(n,0)) for s in suites) for n in ['tests','failures','errors','skipped']}
    assert fields['errors']==0 and fields['failures']==0
    tests[label]=fields
status=subprocess.check_output(['git','status','--short'],cwd=root,text=True)
patch=subprocess.check_output(['git','diff','--','usv_rl/usv_rl/export_policy.py',
    'usv_mpc_ws/src/usv_rl_ros/usv_rl_ros/rl_policy_node.py'],cwd=root)
(exp/'unit_fix.patch').write_bytes(patch)
commands={
    'export': 'PYTHONPATH=/home/trevor/USV/usv_rl /home/trevor/USV/usv_rl/.venv/bin/python -m usv_rl.export_policy --model /home/trevor/USV/usv_rl/models/v5/s4_dr/model.zip --vecnorm /home/trevor/USV/usv_rl/models/v5/s4_dr/vecnormalize.pkl --thrust-scale-n 25.0 --out /home/trevor/USV/usv_rl/models/v5/s4_dr/policy_physical_n.onnx --verification-obs /home/trevor/USV/.sgh-research/experiments/v5_scaling_fix_20261003/raw_obs_cases.npy',
    'training_tests': 'PYTHONPATH=/home/trevor/USV/usv_rl usv_rl/.venv/bin/python -m pytest -q usv_rl/tests/test_export_scaling.py usv_rl/tests/test_obs_equivalence.py usv_rl/tests/test_env_api.py --junitxml=.sgh-research/experiments/v5_scaling_fix_20261003/export_tests.xml',
    'ros_tests': 'source /opt/ros/jazzy/setup.bash; PYTHONPATH=/home/trevor/USV/usv_mpc_ws/src/usv_rl_ros:/home/trevor/USV/usv_rl:$PYTHONPATH python3 -m pytest -q usv_mpc_ws/src/usv_rl_ros/test/test_policy_units.py --junitxml=.sgh-research/experiments/v5_scaling_fix_20261003/ros_tests.xml',
    'build': 'cd /home/trevor/USV/usv_mpc_ws; colcon build --packages-select usv_rl_ros --event-handlers console_direct+',
    'colcon_tests': 'cd /home/trevor/USV/usv_mpc_ws; PYTHONPATH=/home/trevor/USV/usv_rl:$PYTHONPATH colcon test --packages-select usv_rl_ros --event-handlers console_direct+',
}
(exp/'commands.json').write_text(json.dumps(commands,indent=2))
process=subprocess.run(['pgrep','-af','gz sim|ros2 launch|rl_policy_node|mpc_node'],capture_output=True,text=True)
assert process.returncode==1, 'runtime process remains'
summary=dict(completed=True,head=before['head']['out'],branch='codex/scheme-c-rl',backup=applied['backup'],
    changed=applied['changed'],protected=protected,tests=tests,installed_node=installed,
    original_assets_unchanged=asset['original_assets_unchanged'],
    max_reference_abs_error_n=asset['max_reference_abs_error_n'],
    max_new_vs_25_old_abs_error_n=asset['max_new_vs_25_old_abs_error_n'],
    new_onnx_sha256=asset['new_onnx_sha256'],runtime_processes_remaining=False,git_status=status,
    experiment=str(exp))
(exp/'final_summary.json').write_text(json.dumps(summary,indent=2))
files=[]
for p in exp.rglob('*'):
    if p.is_file() and p.suffix in ['.json','.log','.xml','.patch','.npy','.py','.exit','.yaml'] and 'model' not in p.relative_to(exp).parts:
        files.append((p,'experiment/'+str(p.relative_to(exp))))
for d in applied['changed']:
    files.append((root/d['path'],'source/'+d['path']))
for name in ['policy_physical_n.onnx','policy_physical_n.manifest.json','policy.onnx']:
    files.append((root/'usv_rl/models/v5/s4_dr'/name,'assets/v5/s4_dr/'+name))
for name in ['launch/vrx.launch.py','config/path_config.yaml']:
    p=root/'usv_mpc_ws/install/usv_bringup/share/usv_bringup'/name
    if p.exists(): files.append((p,'installed_bringup/'+name))
files.append((root/'usv_mpc_ws/build/usv_rl_ros/pytest.xml','colcon/pytest.xml'))
archive=exp/'v5_scaling_fix_evidence.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for p,n in files: z.write(p,n)
print(json.dumps(dict(completed=True,tests=tests,new_onnx_sha256=summary['new_onnx_sha256'],
    evidence_zip=str(archive),evidence_bytes=archive.stat().st_size,evidence_sha256=digest(archive))))
