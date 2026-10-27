"""One explicit pre-run C10 contract identity; never learn expected from a run."""
from pathlib import Path
import ast
import hashlib
import json
import re

EXPECTED_CONTRACT_SHA='89caaaf36783463a1e1d789bda41f7f90dc398981ddb4b3b8cd6037114333f72'
EXPECTED_SPEC_SHA='317ec56f9c1211b9d8adc5dc727e2a20c1f281afd2047efafecbac797c46d798'


def declared_hash(path, name):
    tree=ast.parse(Path(path).read_text())
    imports=[n for n in tree.body if isinstance(n,ast.ImportFrom) and n.module=='contract_identity_v1'
             and any(x.name=='EXPECTED_CONTRACT_SHA' and x.asname is None for x in n.names)]
    assignments=[n.value for n in tree.body if isinstance(n,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
    if len(assignments)!=1:raise ValueError('one declared consumer identity required: '+str(path))
    value=assignments[0]
    if isinstance(value,ast.Constant) and type(value.value) is str:return value.value
    if isinstance(value,ast.Name) and value.id=='EXPECTED_CONTRACT_SHA' and len(imports)==1:return EXPECTED_CONTRACT_SHA
    raise ValueError('unsupported identity declaration: '+str(path))


def verify_consumers(root, driver, overrides=None):
    root=Path(root);driver=Path(driver)
    paths=dict(producer=(root/'prepare_pair_wakeup_v1.py','PRODUCER_CONTRACT_SHA'),
               checker=(root/'check_pair_wakeup_v1.py','PROJECTED_CONTRACT_SHA'),
               driver=(driver,'PREREG_CONTRACT_SHA'))
    if overrides:paths.update(overrides)
    values={role:declared_hash(path,variable) for role,(path,variable) in paths.items()}
    if any(value!=EXPECTED_CONTRACT_SHA for value in values.values()):raise ValueError('contract identity consumer mismatch: '+str(values))
    raw=(root/'pair_wakeup_contract_v1.json').read_bytes()
    spec=(root/'cold_start_contract_spec_v1.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_CONTRACT_SHA:raise ValueError('explicit current contract identity')
    if hashlib.sha256(spec).hexdigest()!=EXPECTED_SPEC_SHA:raise ValueError('explicit current specification identity')
    c=json.loads(raw);norm=json.loads(spec)
    if c!=norm['legacy_baseline'] or norm['source_contract_sha256']!=EXPECTED_CONTRACT_SHA:raise ValueError('normative source relationship')
    for role in ['worker','observer/src/shadow']:
        text=(root/role/'p1_full_contract.hpp').read_text()
        baked=re.search(r'R"P1BASE\((.*?)\)P1BASE"',text,re.S)
        if not baked or json.loads(baked.group(1))!=c or EXPECTED_SPEC_SHA not in text:raise ValueError('baked native identity/profile differs: '+role)
    return dict(schema='contract-consumers-preflight/v1',passed=True,expected_contract_sha256=EXPECTED_CONTRACT_SHA,
                expected_spec_sha256=EXPECTED_SPEC_SHA,consumers=values,diagnostic_revision=c['diagnostic_contract_revision'],
                contract_semantics_unchanged_from_batch28=True,stage_qualified=False,execute_qualified=False)
