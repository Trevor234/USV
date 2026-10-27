import base64, datetime, hashlib, json, os, pathlib, shutil, subprocess, tempfile
root=pathlib.Path('/home/trevor/USV').resolve()
exp=root/'.sgh-research/experiments/v5_scaling_fix_20261003'
preflight=json.loads((exp/'preflight.json').read_text())
assert (exp/'results/old_diagnostic/complete.json').exists(), 'old diagnostic baseline must precede new unit gate'
assert subprocess.run(['pgrep','-af','gz sim|ros2 launch|rl_policy_node|mpc_node'],capture_output=True).returncode==1, 'controller/simulator still running'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==preflight['head']['out']
for rel,digest in preflight['sha256'].items():
    assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==digest, 'live preflight changed: '+rel
expected={
    'usv_rl/usv_rl/export_policy.py',
    'usv_rl/tests/test_export_scaling.py',
    'usv_mpc_ws/src/usv_rl_ros/usv_rl_ros/rl_policy_node.py',
    'usv_mpc_ws/src/usv_rl_ros/test/test_policy_units.py',
}
bundle=json.loads((exp/'source_bundle.json').read_text())
assert set(bundle)==expected, 'unexpected patch scope'
for rel in expected:
    path=(root/rel).resolve()
    assert path.is_relative_to(root)
    if rel not in preflight['sha256']:
        assert not path.exists(), 'new test already exists: '+rel
for name in ['policy_physical_n.onnx','policy_physical_n.manifest.json']:
    assert not (root/'usv_rl/models/v5/s4_dr'/name).exists(), 'new asset name occupied'
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=root/'.local-backups'/('v5-scaling-fix-'+stamp)
backup.mkdir(parents=True,exist_ok=False)
backup_files=[s for s in preflight['sha256'] if s in expected or s.startswith('usv_rl/models/v5/s4_dr/')]
for rel in backup_files:
    target=backup/rel
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/rel,target)
shutil.copy2(exp/'preflight.json',backup/'preflight.json')
(backup/'git_diff_before.patch').write_bytes(subprocess.check_output(['git','diff'],cwd=root))
changed=[]
for rel,item in bundle.items():
    path=root/rel
    body=item['text'].encode('utf-8')
    assert hashlib.sha256(body).hexdigest()==item['sha256']
    path.parent.mkdir(parents=True,exist_ok=True)
    mode=path.stat().st_mode & 0o777 if path.exists() else 0o644
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        temp=pathlib.Path(f.name)
        f.write(body)
    temp.chmod(mode)
    os.replace(temp,path)
    changed.append(dict(path=rel,sha256=item['sha256'],bytes=len(body)))
report=dict(backup=str(backup),changed=changed,utc_stamp=stamp)
(exp/'apply.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
