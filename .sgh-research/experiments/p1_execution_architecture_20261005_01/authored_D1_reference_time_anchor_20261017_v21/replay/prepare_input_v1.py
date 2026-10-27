#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,math
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
N=Path(__file__).resolve().parent
R=N.parents[1]/'authored_D1_reference_bias_20261016_v20/runs/projected_s005_01'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):return [json.loads(s) for s in Path(p).read_text().splitlines()]
def main():
 inputs=json.loads((R/'inputs.json').read_text());worker=rows(R/'worker/source.jsonl');observer=rows(R/'observer/source.jsonl')
 native=[r for r in worker if r.get('type')=='candidate' and r.get('solver_invoked') is True][:40]
 assert [r['job']['job_id'] for r in native]==list(range(1,41))
 jobs={r['job']['job_id']:r for r in observer if r.get('type')=='job'};payload=[]
 for r in native:
  j=r['job'];assert j==jobs[j['job_id']]['job'] and r['success'] and r['prediction_available'] and r['backend']=='acados'
  payload.append({'job':j,'expected':{k:r[k] for k in ['first_control','X','U']},'reference_metadata':{k:jobs[j['job_id']][k] for k in ['nearest_index','start_index','profile_t0','reference_mode','reference_projection','input_provenance']}})
 first=jobs[1];decoded={}
 for kind in ['path','profile']:
  seq=first['input_provenance'][kind+'_sequence'];ev=next(r for r in observer if r.get('type')==kind+'_version' and r['received_sequence']==seq);raw=ev['raw_input'];cdr=bytes.fromhex(raw['cdr_hex']);assert hashlib.sha256(cdr).hexdigest()==raw['cdr_sha256'] and len(cdr)==raw['cdr_bytes'];decoded[kind]=deserialize_message(cdr,get_message(raw['message_type']))
 path=[]
 for pose in decoded['path'].poses:
  p=pose.pose.position;q=pose.pose.orientation;path.append([p.x,p.y,math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))])
 data=list(decoded['profile'].data);profile=[data[k:k+4] for k in range(0,len(data),4)]
 contract=Path(inputs['contract']);libraries=[Path('/home/trevor/USV/usv_mpc_ws/install/usv_mpc_cpp/lib')/name for name in ['libmpc_solver_lib.a','libmpc_core_lib.a','libcodegen_lib.a']]
 b=inputs['builds']['worker'];link=Path(b['build_directory'])/'CMakeFiles/p1_solver_worker_owned_v2.dir/link.txt';assert all(str(p) in link.read_text() for p in libraries)
 value={'schema':'p1-actual-acados-task-time-replay-input-v1','selected_job_ids':[2,5,10,40],'source_run_dir':str(R),'reference_speed_m_s':.05,'contract':json.loads(contract.read_text()),'contract_sha256':sha(contract),'ordered_native_jobs':payload,'epoch':{'first_job_id':1,'first_target_sim_ns':first['job']['target_sim_ns'],'initial_profile_t0':first['profile_t0']},'actual_reference_input':{'path':path,'profile':profile,'path_stamp':[decoded['path'].header.stamp.sec,decoded['path'].header.stamp.nanosec]},'actual_worker':{'binary':b['binary'],'binary_sha256':b['binary_sha256'],'link_recipe':str(link),'link_recipe_sha256':sha(link)},'static_libraries':{str(p):sha(p) for p in libraries},'evidence':{str(p):sha(p) for p in [R/'inputs.json',R/'observer/source.jsonl',R/'worker/source.jsonl',R/'result.json',contract]},'warm_replay_policy':'exact actual G prefix; change selected Job only for T; actual reset/anchor retained','qualifications':{'stage':False,'execute':False,'research_conclusion':False}}
 out=N/'actual_replay_input_v1.json'
 with out.open('x') as f:json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps({'path':str(out),'sha256':sha(out),'jobs':len(payload),'selected':value['selected_job_ids']}))
if __name__=='__main__':main()
