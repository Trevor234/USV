#!/usr/bin/env python3
"""Create-only archive delivery; receipts stay in this batch, never in frozen parents."""
import argparse
import hashlib
import json
from pathlib import Path
import time

D=Path(__file__).resolve().parent
W=D.parent
NAMES=['scheme_A_startup_first_control_20261018_24','scheme_A_fixed_first_tail_optimization_20261018_25',
       'scheme_A_causal_cold_start_20261018_26','scheme_A_owned_cold_start_20261018_27',
       'scheme_A_activation_alignment_20261019_28','scheme_A_deferred_observation_20261019_29',
       'scheme_A_P1_scope_audit_20261019_30']


def pin(p):
    h=hashlib.sha256();size=0
    with p.open('rb') as f:
        while b:=f.read(1024*1024):h.update(b);size+=len(b)
    return dict(bytes=size,sha256=h.hexdigest())


def population(root):
    fs=set();ds=set()
    for p in root.rglob('*'):
        assert not p.is_symlink(),str(p)
        (ds if p.is_dir() else fs).add(str(p.relative_to(root)))
    return fs,ds


def deliver(name):
    source=W/name;dest=Path('/home/trevor/MPC')/name
    ib=(source/'archive_inventory_v1.json').read_bytes();inv=json.loads(ib)
    rows={r['relative_path']:dict(bytes=r['bytes'],sha256=r['sha256']) for r in inv['files']}
    rows['archive_inventory_v1.json']=dict(bytes=len(ib),sha256=hashlib.sha256(ib).hexdigest())
    dirs=set(inv['directories'])
    assert population(source)==(set(rows),dirs),'local population not sealed: '+name
    try:dest.mkdir()
    except FileExistsError:pass
    assert dest.is_dir() and not dest.is_symlink()
    ef,ed=population(dest)
    assert ef<=set(rows) and ed<=dirs,'unknown remote members: '+name
    for rel in sorted(dirs,key=lambda s:(len(Path(s).parts),s)):(dest/rel).mkdir(exist_ok=True)
    copied=0;reused=0
    for rel,expected in sorted(rows.items()):
        p=source/rel;q=dest/rel
        if q.exists():
            assert q.is_file() and pin(q)==expected,'remote conflict: '+str(q)
            reused+=1
        else:
            h=hashlib.sha256();size=0
            with p.open('rb') as fi,q.open('xb') as fo:
                while b:=fi.read(1024*1024):fo.write(b);h.update(b);size+=len(b)
            assert dict(bytes=size,sha256=h.hexdigest())==expected,'local changed during copy: '+str(p)
            copied+=1
        assert pin(q)==expected,'first remote readback failed: '+str(q)
    # Separate complete second readback after all members exist.
    assert population(source)==population(dest)==(set(rows),dirs)
    for rel,expected in rows.items():
        assert pin(source/rel)==pin(dest/rel)==expected,'second readback failed: '+rel
    return dict(name=name,passed=True,files=len(rows),bytes=sum(r['bytes'] for r in rows.values()),
                directories=len(dirs),copied=copied,existing_exact_files_reused=reused,
                inventory_sha256=rows['archive_inventory_v1.json']['sha256'],destination=str(dest),
                exact_population=True,full_second_SHA_readback=True,old_source_or_remote_members_overwritten=False,
                server_durable_storage_guarantee_claimed=False)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('scope',choices=['backlog','current']);a=ap.parse_args()
    out=D/'evidence'/('MPC_backlog_delivery_v1.json' if a.scope=='backlog' else 'MPC_current_delivery_v1.json')
    journal=D/'evidence'/('MPC_backlog_progress_v1.jsonl' if a.scope=='backlog' else 'MPC_current_progress_v1.jsonl')
    # Current delivery receipts are emitted to /tmp first; final publication is
    # handled separately so that the sealed current inventory remains immutable.
    if a.scope=='current':raise SystemExit('use explicit final current delivery after local seal')
    result=dict(schema='MPC-restored-backlog-delivery/v1',passed=False,started_ns=time.monotonic_ns(),batches=[],
                stage_qualified=False,execute_qualified=False,research_conclusion=False)
    try:
        with journal.open('x') as j:
            for name in NAMES:
                row=deliver(name);result['batches'].append(row)
                j.write(json.dumps(row,ensure_ascii=False)+'\n');j.flush()
                print(json.dumps(dict(batch=name,files=row['files'],passed=True)),flush=True)
        result['passed']=True
    except Exception as e:result.update(error=repr(e),traceback=__import__('traceback').format_exc())
    result['finished_ns']=time.monotonic_ns()
    with out.open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False);f.write('\n')
    print(json.dumps(dict(passed=result['passed'],batches=len(result['batches']),output=str(out),error=result.get('error')),ensure_ascii=False),flush=True)
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
