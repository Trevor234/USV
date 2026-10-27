#!/usr/bin/env python3
"""Real file-source entry checks; no mocked hashes or filesystem outcomes."""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(D/'implementation/python'))
from formal_prepare_contract import load_preparation_contract


def pin(p):
    b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def main():
    root=D/'verification/entry_files_v1';root.mkdir()
    pre=D/'implementation/current_pre_freeze_contract_v1.json'
    diag=D/'implementation/current_diag_contract_v1.json'
    frozen=D/'verification/frozen_shape_for_entry_cases_v1.json'
    bad=root/'bad_hash_contract.json';bad.write_bytes(pre.read_bytes()+b' ')
    duplicate=root/'duplicate.json';duplicate.write_bytes(pre.read_bytes().rstrip()[:-1]+b',"execution_contract_revision":1}')
    empty=root/'empty.json';empty.write_bytes(b'')
    oversized=root/'oversized.json';oversized.write_bytes(b' '*65537)
    link=root/'symlink.json';link.symlink_to(pre)
    parentlink=root/'linked_parent';parentlink.symlink_to(pre.parent,target_is_directory=True)
    fifo=root/'pipe.json';os.mkfifo(fifo)
    rows=[]
    sha=pin(pre)['sha256']
    cases=[('valid_pre_freeze',pre,sha,'no_output',True),
           ('changed_bytes',bad,sha,'no_output',False),
           ('diagnostic_not_formal',diag,pin(diag)['sha256'],'no_output',False),
           ('Frozen_cannot_promote_prepare',frozen,pin(frozen)['sha256'],'no_output',False),
           ('duplicate_raw',duplicate,pin(duplicate)['sha256'],'no_output',False),
           ('empty',empty,pin(empty)['sha256'],'no_output',False),
           ('oversized',oversized,pin(oversized)['sha256'],'no_output',False),
           ('symlink_leaf',link,sha,'no_output',False),
           ('symlink_parent',parentlink/pre.name,sha,'no_output',False),
           ('fifo_nonblocking_reject',fifo,sha,'no_output',False),
           ('directory',root,sha,'no_output',False),
           ('relative_path','local.json',sha,'no_output',False),
           ('parent_traversal',str(root)+'/../entry_files_v1/bad_hash_contract.json',sha,'no_output',False)]
    for mode in ['shadow','execute','',None,False]:cases.append(('mode_'+repr(mode),pre,sha,mode,False))
    for expected in [None,False,'A'*64,'g'*64,'f'*63,'f'*65,'f'*64]:cases.append(('expected_sha_'+repr(expected),pre,expected,'no_output',False))
    inputs=[pre,diag,frozen,Path(__file__).resolve(),D/'implementation/python/formal_prepare_contract.py',
            D/'implementation/python/p1_full_contract.py',D/'implementation/python/p1_contract_spec_v1.json']
    before={str(p):pin(p) for p in inputs}
    for label,path,expected,mode,accept in cases:
        try:
            value=load_preparation_contract(path,expected,mode=mode)
            outcome=True;reason=''
            assert value.sha256==sha and value.spec_sha256=='317ec56f9c1211b9d8adc5dc727e2a20c1f281afd2047efafecbac797c46d798'
            changed=value.configuration;changed['execute_qualified']=True
            assert value.configuration['execute_qualified'] is False
        except (ValueError,OSError) as e:outcome=False;reason=str(e)
        rows.append({'name':label,'expected_accept':accept,'accepted':outcome,'reason':reason,'passed':outcome==accept})
    after={p:pin(Path(p)) for p in before}
    report={'schema':'B5-formal-preparation-file-entry/v1','passed':all(r['passed'] for r in rows) and before==after,
            'case_count':len(rows),'cases':rows,'input_sha256_before':before,'input_sha256_after':after,
            'actual_file_operations':True,'owned_ROS_runtime':False,'stage_qualified':False,'execute_qualified':False}
    with (D/'verification/formal_contract_entry_v1.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    # Special test fixtures are removed after observed use, before archiving.
    # No historical artifact is touched; full regular input bytes remain.
    fifo.unlink();link.unlink();parentlink.unlink()
    print(json.dumps({'passed':report['passed'],'case_count':len(rows),'failures':[r['name'] for r in rows if not r['passed']]}))
    return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
