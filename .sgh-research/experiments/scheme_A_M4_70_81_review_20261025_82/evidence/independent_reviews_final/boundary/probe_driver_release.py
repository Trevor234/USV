#!/usr/bin/env python3
import pathlib,textwrap,json,types
p=pathlib.Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_r2_driver_20261025_78/implementation/t2_author_r3/t2_scenario_driver_v1.py')
lines=p.read_text().splitlines()
# Execute exact unedited production fragments. No process, ROS, file or real pipe.
read_fragment=textwrap.dedent('\n'.join(lines[329:344]))
release_fragment=textwrap.dedent('\n'.join(lines[381:402]))
class Cursor:
 def poll(self):return [{'type':'path_version','processed_ns':10,'task_generation':2}]
writes=[];events=[]
ctx=dict(cursor=Cursor(),regulator_rows_all=[],boundary_state={'awaiting_fixture_receipt':'a1','path_version_committed':False,'released':False},jobs_by_id={},ready_jobs={},event=lambda typ,**kw:events.append({'type':typ,**kw}),boundary_pipe_write=7,receipts=[{'action_id':'a1','executed_ns':20}],boundary_release_cfg={'job_id':2,'ordinal':1,'nonce':1749532001},os=types.SimpleNamespace(write=lambda fd,data:(writes.append((fd,len(data))) or len(data))))
exec(compile(read_fragment,str(p)+':330-344','exec'),ctx)
exec(compile(release_fragment,str(p)+':382-402','exec'),ctx)
out={'source_fragments_unchanged':True,'path_event_processed_ns':10,'fixture_receipt_executed_ns':20,'target_job_task_generation':2,'observed_path_task_generation':2,'released_despite_no_generation_advance_and_path_event_before_receipt':ctx['boundary_state']['released'],'writes':writes,'events':events}
pathlib.Path('/tmp/review81_boundary/driver_release_probe_results.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
