#!/usr/bin/python3
"""Create-only new batch and read-only protection audit, prior ledger append recognized."""
from pathlib import Path
import hashlib,json,subprocess
D=Path('/home/trevor/MPC/scheme_A_config_identity_20261011_04')
P=Path('/home/trevor/MPC/scheme_A_strict_source_20261011_03')
sha=lambda b:hashlib.sha256(b).hexdigest()
D.mkdir(exist_ok=False)
for name in ['preflight','preregister','validation','postrun','audits']:(D/name).mkdir()
with (D/'prepare_batch.snapshot.py').open('xb') as f:f.write(Path(__file__).read_bytes())
for name in ['audit_assets_20261011.py','audit_protection_20261011.py','audit_followup_20261011.py']:
    source=(P/'preflight'/name).read_text().replace(str(P/'preflight'),str(D/'preflight'))
    if name=='audit_protection_20261011.py':
        source=source.replace("proof = load(D / 'postrun/research_ledger_append.json')",
                            "proof = load(Path('/home/trevor/MPC/scheme_A_strict_source_20261011_03/postrun/research_ledger_append.json'))")
        source=source.replace("'ledger_original_final': ledger['passed']","'ledger_authorized_v4_final': ledger['passed']")
    path=D/'preflight'/name
    with path.open('x') as f:f.write(source)
    with (path.with_suffix('.log')).open('xb') as f:
        p=subprocess.run(['/usr/bin/python3','-I','-S',str(path)],stdout=f,stderr=subprocess.STDOUT,timeout=180)
    assert p.returncode==0,name
print(json.dumps({'protection':json.loads((D/'preflight/protection_completion.json').read_bytes()),'new_batch':str(D)},indent=2))
