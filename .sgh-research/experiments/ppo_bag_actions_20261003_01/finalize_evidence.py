import bisect, collections, difflib, hashlib, importlib.util, json, math, pathlib, subprocess, sys, xml.etree.ElementTree as ET, zipfile

root=pathlib.Path('/home/trevor/USV').resolve()
exp=root/'.sgh-research/experiments/ppo_bag_actions_20261003_01'
before=json.loads((exp/'preflight.json').read_text())
applied=json.loads((exp/'apply.json').read_text())
case=exp/'results/new_actions'
bag=root/'data/sim_bags/rl_c_actions_20261003_01'

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

spec=importlib.util.spec_from_file_location('ppo_checker_final',root/'usv_mpc_ws/scripts/check_ppo_bag.py')
checker=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=checker
spec.loader.exec_module(checker)
acceptance=json.loads((case/'acceptance.json').read_text())
offline=json.loads((exp/'results/offline/suite_summary.json').read_text())
completion=json.loads((case/'complete.json').read_text())
context=json.loads((case/'run_context.json').read_text())
assert acceptance['passed'] and acceptance['exit_code']==0
assert acceptance['recorded_action_stream_consistent'] and acceptance['active_count']>=10
assert acceptance['simulation_clock_recorded'] and acceptance['nonzero_active_count']>0
assert offline['passed']
assert completion['stop_signals']==['SIGINT'] and completion['returncode']==0
assert completion['metadata_exists']
assert not acceptance['failures']
protected={rel:dict(before=before['sha256'][rel],after=digest(root/rel)) for rel in before['protected']}
assert all(pair['before']==pair['after'] for pair in protected.values()), 'protected file changed'
old_bags={}
for name,item in before['bags'].items():
    path=pathlib.Path(item['path'])
    now={str(p.relative_to(path)):dict(bytes=p.stat().st_size,sha256=digest(p))
         for p in path.rglob('*') if p.is_file()}
    old_bags[name]=dict(path=str(path),unchanged=now==item['files'],files=now)
assert all(item['unchanged'] for item in old_bags.values()), 'baseline bag modified'
changed=[]
for item in applied['changed']:
    now=digest(root/item['path'])
    assert now==item['sha256'], 'deployed source changed: '+item['path']
    changed.append(dict(item,after_sha256=now))
installed=root/'usv_mpc_ws/install/usv_bringup/share/usv_bringup/launch/vrx.launch.py'
assert digest(installed)==digest(root/'usv_mpc_ws/src/usv_bringup/launch/vrx.launch.py')
tests_root=ET.parse(exp/'unit_tests.xml').getroot()
suites=[tests_root] if tests_root.tag=='testsuite' else list(tests_root.iter('testsuite'))
tests={name:sum(int(s.get(name,0)) for s in suites) for name in ['tests','errors','failures','skipped']}
assert tests['tests']>=40 and all(tests[key]==0 for key in ['errors','failures','skipped'])
remaining=subprocess.run(['pgrep','-af','gz sim|ros2 launch|rl_policy_node|mpc_node|ros2 bag record'],capture_output=True,text=True)
assert remaining.returncode==1, 'runtime process remains: '+remaining.stdout

cfg=checker.Config(profile='ppo-actions-v1',min_active=10,require_nonzero_active=True)
records,types,reading=checker.read_bag(bag,cfg)
statuses=[(r.bag_ns,json.loads(r.payload['data'])) for r in records if r.topic==cfg.topics['status']]
clocks=[(r.bag_ns,checker._stamp_ns(r.payload['clock'])) for r in records if r.topic==cfg.topics['clock']]
clocks.sort()
clock_bag_times=[t for t,s in clocks]
mapped=[clocks[bisect.bisect_right(clock_bag_times,t)-1][1] for t,s in statuses]
raw=[abs(s[k]) for t,s in statuses for k in ['tl_cmd_n','tr_cmd_n']]
published=[abs(s[k]) for t,s in statuses for k in ['tl_n','tr_n']]
case_files={str(p.relative_to(bag)):dict(bytes=p.stat().st_size,sha256=digest(p))
            for p in bag.rglob('*') if p.is_file()}
clock_wall_span=(clocks[-1][0]-clocks[0][0])/1e9
sim_span=(clocks[-1][1]-clocks[0][1])/1e9
run_metrics=dict(bag_files=case_files,bag_bytes=sum(item['bytes'] for item in case_files.values()),
    status_count=len(statuses),status_states=dict(collections.Counter(s['state'] for t,s in statuses)),
    status_receive_span_seconds=(statuses[-1][0]-statuses[0][0])/1e9,
    status_clock_mapped_sim_span_seconds=(mapped[-1]-mapped[0])/1e9,
    max_request_abs_n=max(raw),max_published_abs_n=max(published),
    clock_count=len(clocks),clock_receive_span_seconds=clock_wall_span,
    clock_sim_span_seconds=sim_span,
    clock_receive_rate_hz=(len(clocks)-1)/clock_wall_span,
    clock_sim_rate_hz=(len(clocks)-1)/sim_span)
patch=[]
for rel in before['modified']+before['new_files']:
    old=before['sources'].get(rel,'').splitlines(keepends=True)
    new=(root/rel).read_text().splitlines(keepends=True)
    patch.extend(difflib.unified_diff(old,new,fromfile='a/'+rel if old else '/dev/null',tofile='b/'+rel))
(exp/'ppo_bag_fix.patch').write_text(''.join(patch))
historical=json.loads((exp/'results/offline/historical_strict.json').read_text())
import rosbag2_py, yaml
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
old_storage=yaml.safe_load(before['bags']['historical']['metadata'])['rosbag2_bagfile_information']['storage_identifier']
old_reader=rosbag2_py.SequentialReader()
old_reader.open(rosbag2_py.StorageOptions(uri=before['bags']['historical']['path'],storage_id=old_storage),
    rosbag2_py.ConverterOptions('',''))
profile_lengths=collections.Counter()
nonfinite_profile_messages=0
profile_class=get_message('std_msgs/msg/Float64MultiArray')
while old_reader.has_next():
    topic,payload,stamp=old_reader.read_next()
    if topic!='/path/reference_profile': continue
    profile_msg=deserialize_message(payload,profile_class)
    profile_lengths[len(profile_msg.data)]+=1
    nonfinite_profile_messages+=int(any(not math.isfinite(value) for value in profile_msg.data))
profile_inspection=dict(message_count=sum(profile_lengths.values()),length_counts=dict(profile_lengths),
    empty_count=profile_lengths[0],nonfinite_message_count=nonfinite_profile_messages)
(exp/'historical_profile_inspection.json').write_text(json.dumps(profile_inspection,indent=2))
classification=dict(historical=dict(path=before['bags']['historical']['path'],action_recording_complete=False,
        recorded_action_stream_consistent=False,gp_labels_ready=False,
        reasons=['missing_left_right_thrust_and_control_status','missing_clock','invalid_reference_profile_records'],
        failure_counts=dict(collections.Counter(x['code'] for x in historical['failures'])),
        reference_profile_inspection=profile_inspection,
        allowed_use=['trajectory_and_observation_analysis_with_limits'],original_files_unchanged=True),
    v5_physical_previous=dict(path=before['bags']['new_physical_n']['path'],
        recorded_action_stream_consistent=True,simulation_clock_recorded=False,
        strict_profile_passed=False,gp_labels_ready=False),
    new_actions=dict(path=str(bag),recorded_action_stream_consistent=True,strict_profile_passed=True,
        common_drop_identifiable=False,exact_execution_timing_available=False,gp_labels_ready=False))
(exp/'dataset_classification.json').write_text(json.dumps(classification,indent=2))
log=(case/'launch.log').read_text(errors='replace')
subscriptions=[line for line in log.splitlines() if 'Subscribed to topic' in line]
shutdown_known_exception='rcl_shutdown already called' in log
summary=dict(completed=True,experiment=str(exp),bag=str(bag),backup=applied['backup'],
    head=before['head']['out'],branch=before['branch']['out'],changed=changed,protected=protected,
    existing_bags=old_bags,tests=tests,installed_launch_sha256=digest(installed),
    unit_model_sha256=context['model_sha256'],offline=offline,acceptance=acceptance,
    run_completion=completion,run_metrics=run_metrics,recorder_subscriptions=subscriptions,
    known_shutdown_rclpy_exception=shutdown_known_exception,runtime_processes_remaining=False,
    dataset_classification=classification,git_status=subprocess.check_output(['git','status','--short'],cwd=root,text=True),
    patch_sha256=digest(exp/'ppo_bag_fix.patch'))
(exp/'final_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
archive=exp/'ppo_bag_fix_evidence.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in exp.rglob('*'):
        if p.is_file() and p.suffix in ['.json','.log','.xml','.patch','.yaml','.py','.txt']:
            z.write(p,'experiment/'+str(p.relative_to(exp)))
    for item in changed: z.write(root/item['path'],'source/'+item['path'])
    z.write(installed,'installed_bringup/launch/vrx.launch.py')
    for p in bag.rglob('*'):
        if p.is_file(): z.write(p,'new_bag/'+str(p.relative_to(bag)))
    for name,item in before['bags'].items():
        z.write(pathlib.Path(item['path'])/'metadata.yaml','baseline_metadata/'+name+'.yaml')
print(json.dumps(dict(completed=True,tests=tests,run_metrics=run_metrics,
    evidence_zip=str(archive),evidence_bytes=archive.stat().st_size,evidence_sha256=digest(archive)),indent=2))
