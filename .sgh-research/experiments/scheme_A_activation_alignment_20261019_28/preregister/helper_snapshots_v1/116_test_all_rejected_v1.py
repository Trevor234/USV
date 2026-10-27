#!/usr/bin/env python3
"""Semantic all-rejected negatives on fresh copies; original normal gate unchanged."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
N=Path(__file__).resolve().parent
sys.path.insert(0,str(N))
import audit_all_rejected_v1 as a


def hashes(root):return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}
def event(rs,typ):return next(r for r in rs if r['type']==typ and (typ!='decision' or r['job_id']))
def reason(rs):
    event(rs,'decision')['reason']='no_candidate';event(rs,'anchor_validation')['decision_reason']='no_candidate'
def fake_ready(w):w['phase'][0]['event_code']=9
def remove_close(w):w['phase']=[p for p in w['phase'] if p['event_code']!=7]


CASES=[
 ('coherent_wrong_rejection_reason','observer/source.jsonl',reason,'first_rejection_order'),
 ('wrong_actual_anchor_sequence','observer/source.jsonl',lambda rs:event(rs,'anchor_validation')['actual_sequence'].__setitem__(0,999),'final_anchor_actual_applied_join'),
 ('wrong_expected_anchor_value','observer/source.jsonl',lambda rs:event(rs,'anchor_validation')['expected_n'].__setitem__(0,0.),'expected_anchor_actual_applied_join'),
 ('wrong_publication_entry_time','observer/source.jsonl',lambda rs:event(rs,'anchor_validation')['entries'][0].__setitem__('publish_ns',0),'complete_publication_entry_join'),
 ('missing_anchor_proof','observer/source.jsonl',lambda rs:rs.remove(event(rs,'anchor_validation')),'activation_attempt_sets'),
 ('job_nominal_identity','observer/source.jsonl',lambda rs:event(rs,'job')['job'].__setitem__('nominal_hash','0'*64),'job_configuration_identity'),
 ('late_registration','observer/source.jsonl',lambda rs:event(rs,'candidate_registration').__setitem__('ready_commit_ns',event(rs,'job')['job']['deadline_ns']+1),'native_deadline_activation_order'),
 ('witness_ready_time','observer/witness.json',lambda w:w['activation'][0].__setitem__('ready_commit_ns',0),'witness_time_identity_join'),
 ('fake_BusinessReady','observer/witness.json',fake_ready,'all_rejected_business_ready_must_be_absent'),
 ('missing_Close','observer/witness.json',remove_close,'fixed_ring_integrity_residual'),
 ('false_integrity_complete','observer/witness.json',lambda w:w.__setitem__('audit_complete',False),'fixed_storage_integrity_flags'),
]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);ap.add_argument('--output',required=True);args=ap.parse_args()
    root=Path(args.run);out=Path(args.output);out.mkdir();copies=N/'validation_copies'/out.name;copies.mkdir(parents=True)
    contract,lock=a.load_contract();entry=next(v for v in lock['cases'].values() if v['root']==str(root))
    for rel,pin in entry['files'].items():assert a.digest((root/rel).read_bytes())==pin['sha256']
    before=hashes(root);tools={p.name:a.digest(p.read_bytes()) for p in (N/'audit_all_rejected_v1.py',Path(__file__))}
    (out/'prerun_identity.json').open('x').write(json.dumps({'tools':tools,'original_files':before,'cases':[{'name':n,'file':f,'expected_code':e} for n,f,_,e in CASES],'qualification':False},indent=2)+'\n')
    results=[]
    for name,rel,mutate,expected in CASES:
        copyroot=copies/name;shutil.copytree(root,copyroot);p=copyroot/rel
        value=[json.loads(x) for x in p.read_text().splitlines()] if rel.endswith('.jsonl') else json.loads(p.read_text())
        mutate(value)
        p.write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in value) if rel.endswith('.jsonl') else json.dumps(value,indent=2)+'\n')
        try:report=a.analyze(a.load_run(copyroot,contract,original=False),contract)
        except Exception as error:report={'protocol_component_passed':False,'issues':[{'code':'audit_input_or_join_error','detail':type(error).__name__+': '+str(error)}]}
        codes=[r['code'] for r in report['issues']];matched=report['protocol_component_passed'] is False and expected in codes
        report.update(expected_negative_matched=matched,expected_code=expected,copy_root=str(copyroot),copy_sha256=hashes(copyroot))
        (out/(name+'.json')).open('x').write(json.dumps(report,indent=2,allow_nan=False)+'\n')
        results.append({'name':name,'expected_negative_matched':matched,'expected_code':expected,'observed_codes':sorted(set(codes))});print(name,matched,flush=True)
    summary={'schema':'p1-all-rejected-fresh-copy-negatives-v1','passed':all(r['expected_negative_matched'] for r in results),'count':len(results),'cases':results,'originals_unchanged':before==hashes(root),'tools_unchanged':tools=={p.name:a.digest(p.read_bytes()) for p in (N/'audit_all_rejected_v1.py',Path(__file__))},'normal_Witness_gate_qualified':False,'D1':False,'execute':False}
    summary['passed']=summary['passed'] and summary['originals_unchanged'] and summary['tools_unchanged']
    (out/'summary.json').open('x').write(json.dumps(summary,indent=2)+'\n');return 0 if summary['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
