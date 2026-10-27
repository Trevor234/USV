#!/usr/bin/env python3
"""Altered actual evidence checks; no new runtime fault injection."""
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(D))
from audit_normal_source_core_v1 import check_window
R=D/'author_r2/runs/normal_source20s_03'
def read(p):return json.loads(p.read_bytes())
def lines(p):return [json.loads(s) for s in p.read_text().splitlines()]
def pin(p):
    b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def main():
    paths=[R/'observer/source.jsonl',R/'worker/source.jsonl',R/'publisher/controlled_source.jsonl',R/'normal_source_observation.json',R/'inputs.json',R/'result.json',D/'audit_normal_source_core_v1.py',Path(__file__).resolve()]
    before={str(p):pin(p) for p in paths}
    data={'source':[r for r in lines(paths[0]) if r.get('type') in ['job','decision','worker_unusable_transition','diagnostic_v1_armed_after_ack','diagnostic_v3_wait_started','diagnostic_c38_gate_paused']],
          'worker':[r for r in lines(paths[1]) if r.get('type')=='candidate'],
          'publisher':[r for r in lines(paths[2]) if r.get('type')=='controlled_Applied_emitted'],
          'proof':read(paths[3]),'inputs':read(paths[4]),'result':read(paths[5])}
    actual=check_window(**data);assert actual['passed'];out=[]
    def case(name,alter):
        v=copy.deepcopy(data);alter(v)
        try:check_window(**v);rejected=False;reason='wrong acceptance'
        except (ValueError,KeyError,TypeError) as e:rejected=True;reason=str(e)
        out.append({'name':name,'rejected':rejected,'reason':reason})
    def job(v):return next(r['job'] for r in v['source'] if r.get('type')=='job' and r['job']['job_id']==v['proof']['first_job_id']+10)
    case('reselected_origin',lambda v:v['proof'].__setitem__('first_job_id',v['proof']['first_job_id']+1))
    case('short_span',lambda v:v['proof'].__setitem__('source_span_ns',19_000_000_000))
    case('planar_v_outside_domain',lambda v:job(v)['frozen_state'].__setitem__(4,1.21))
    case('foreign_Worker',lambda v:job(v).__setitem__('worker_instance','foreign'))
    case('late_receipt',lambda v:job(v).__setitem__('odom_receive_ns',0))
    case('wrong_absolute_deadline',lambda v:job(v).__setitem__('deadline_ns',job(v)['deadline_ns']+1))
    case('zero_anchor_tail',lambda v:job(v).__setitem__('anchor_n',[0.,0.]))
    case('unknown_anchor',lambda v:job(v).__setitem__('anchor_known',[False,False]))
    case('actual_window_population_mismatch',lambda v:v['proof'].__setitem__('jobs_in_window',v['proof']['jobs_in_window']-1))
    case('no_successful_Driver',lambda v:v['result'].__setitem__('normal20_source_case_completed',False))
    case('hidden_fault_transition',lambda v:v['source'].append({'type':'worker_unusable_transition'}))
    case('changed_recipe',lambda v:v['inputs'].__setitem__('reference_speed_m_s',.6))
    after={str(p):pin(p) for p in paths};assert before==after
    report={'schema':'current-normal20s-altered-actual-evidence-v1','passed':all(r['rejected'] for r in out),'cases':out,
      'actual_positive_checked':True,'case_count':len(out),'input_sha256_before':before,'input_sha256_after':after,
      'runtime_fault_injections':0,'stage_qualified':False,'research_conclusion':False}
    with (D/'verification/actual_normal_evidence_negatives_v1.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({'passed':report['passed'],'cases':len(out),'failed':[r['name'] for r in out if not r['rejected']]}))
    return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
