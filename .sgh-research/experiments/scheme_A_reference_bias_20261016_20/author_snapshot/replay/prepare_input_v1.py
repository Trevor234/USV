#!/usr/bin/env python3
from pathlib import Path
import hashlib,json
N=Path(__file__).resolve().parent
R=N.parents[1]/'authored_D1_longitudinal_20261016_v19/runs/longitudinal_s010_01'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):return [json.loads(s) for s in Path(p).read_text().splitlines()]
def main():
 inputs=json.loads((R/'inputs.json').read_text());worker=rows(R/'worker/source.jsonl');observer=rows(R/'observer/source.jsonl')
 native=[r for r in worker if r.get('type')=='candidate' and r.get('solver_invoked') is True]
 assert [r['job']['job_id'] for r in native]==list(range(1,len(native)+1))
 selected=104;assert native[-1]['job']['job_id']==selected
 jobs={r['job']['job_id']:r for r in observer if r.get('type')=='job'}
 payload=[]
 for r in native:
  j=r['job'];assert j==jobs[j['job_id']]['job'] and r['success'] and r['prediction_available'] and r['backend']=='acados'
  payload.append({'job':j,'expected':{k:r[k] for k in ['first_control','X','U']},'reference_metadata':{k:jobs[j['job_id']][k] for k in ['nearest_index','start_index','profile_t0','reference_mode']}})
 contract=Path(inputs['contract']);libraries=[Path('/home/trevor/USV/usv_mpc_ws/install/usv_mpc_cpp/lib')/name for name in ['libmpc_solver_lib.a','libmpc_core_lib.a','libcodegen_lib.a']]
 b=inputs['builds']['worker'];link=Path(b['build_directory'])/'CMakeFiles/p1_solver_worker_owned_v2.dir/link.txt'
 assert all(str(p) in link.read_text() for p in libraries)
 value={'schema':'p1-actual-acados-reference-replay-input-v1','selected_job_id':selected,'source_run_dir':str(R),'reference_speed_m_s':.1,'contract':json.loads(contract.read_text()),'contract_sha256':sha(contract),'ordered_native_jobs':payload,'actual_worker':{'binary':b['binary'],'binary_sha256':b['binary_sha256'],'link_recipe':str(link),'link_recipe_sha256':sha(link)},'static_libraries':{str(p):sha(p) for p in libraries},'evidence':{str(p):sha(p) for p in [R/'inputs.json',R/'observer/source.jsonl',R/'worker/source.jsonl',R/'result.json',contract]},'warm_replay_policy':'exact complete native job order; reset only where actual Job.reset_warmstart; overwrite u_prev from each actual Job.anchor_n before every solve','qualifications':{'stage':False,'execute':False,'research_conclusion':False}}
 out=N/'actual_replay_input_v1.json'
 with out.open('x') as f:json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps({'path':str(out),'sha256':sha(out),'jobs':len(payload),'selected':selected}))
if __name__=='__main__':main()
