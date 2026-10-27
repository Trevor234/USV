import datetime, hashlib, json, os, pathlib, shutil, subprocess, tempfile, zipfile

root=pathlib.Path('/home/trevor/USV').resolve()
exp=root/'.sgh-research/experiments/ppo_bag_actions_20261003_01'
before=json.loads((exp/'preflight.json').read_text())
assert not (exp/'apply.json').exists(), 'already applied'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==before['head']['out']
for rel,sha in before['sha256'].items():
    assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==sha, 'preflight changed: '+rel
assert subprocess.run(['pgrep','-af','gz sim|ros2 launch|rl_policy_node|mpc_node|ros2 bag record'],capture_output=True).returncode==1

allowed=set(before['modified']+before['new_files'])
with zipfile.ZipFile(exp/'upload.zip') as z:
    manifest=json.loads(z.read('bundle_manifest.json'))
    assert set(manifest['source'])==allowed, 'unexpected source scope'
    payload={rel:z.read('source/'+rel) for rel in allowed}
    for rel,data in payload.items():
        assert hashlib.sha256(data).hexdigest()==manifest['source'][rel]['sha256']
        path=(root/rel).resolve()
        assert path.is_relative_to(root)
        if rel in before['new_files']:
            assert not path.exists(), 'new filename occupied: '+rel
    for name,item in manifest['helpers'].items():
        assert pathlib.PurePosixPath(name).name==name
        body=z.read('helpers/'+name)
        assert hashlib.sha256(body).hexdigest()==item['sha256']
        (exp/name).write_bytes(body)

stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=root/'.local-backups'/('ppo-bag-actions-'+stamp)
backup.mkdir(parents=True,exist_ok=False)
for rel in before['modified']:
    target=backup/rel
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/rel,target)
shutil.copy2(exp/'preflight.json',backup/'preflight.json')
(backup/'git_diff_before.patch').write_bytes(subprocess.check_output(['git','diff'],cwd=root))
changed=[]
for rel in sorted(allowed):
    path=root/rel
    path.parent.mkdir(parents=True,exist_ok=True)
    mode=path.stat().st_mode&0o777 if path.exists() else (0o755 if rel.endswith('/check_ppo_bag.py') else 0o644)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        temporary=pathlib.Path(f.name)
        f.write(payload[rel])
    temporary.chmod(mode)
    os.replace(temporary,path)
    changed.append(dict(path=rel,sha256=hashlib.sha256(payload[rel]).hexdigest(),bytes=len(payload[rel])))
report=dict(backup=str(backup),utc_stamp=stamp,changed=changed)
(exp/'apply.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
