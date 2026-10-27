from pathlib import Path
import hashlib,json,sys,traceback
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.convert import message_to_ordereddict
from rosidl_runtime_py.utilities import get_message

E=Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01')
b=json.loads((E/'resource_v13_build_result_20261007.json').read_text())
R=Path(b['runtime']);sys.path.insert(0,str(R))
from run_worker_fault_matrix import verify_assets
from run_no_output_calibration import host_preflight
import check_p1_execution as base
D=E/'p1_resource_metadata_20261007_02';C=Path(b['contract_file']);c=json.loads(C.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
P=D/'verification_metadata_base_v13/contract_report.json';L=D/'verification_metadata_delivery_v1/resource_delivery_check.json'
files=sorted([p for p in (D/'raw_bag').rglob('*') if p.is_file()])+[D/'regulator_source.jsonl',D/'worker_source.jsonl',D/'run_context.json',D/'runner_summary.json',D/'owned_process_ledger.jsonl',D/'fixture_source.jsonl',C,P,L]
before={str(p):sha(p) for p in files};result=None;failure=None
try:
    verify_assets(Path(b['guard_manifest']));host_preflight()
    report=json.loads(P.read_text());ledger=json.loads(L.read_text())
    assert report['passed'] and report['diagnostic_complete'] and not report['issues']
    assert ledger['passed'] and not ledger['issues']
    bag,storage=base.read_bag(D/'raw_bag')
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(D/'raw_bag'),storage_id=storage['storage']),rosbag2_py.ConverterOptions(input_serialization_format='cdr',output_serialization_format='cdr'))
    types=storage['topic_types'];topics=[c['input_topics']['profile'],c['input_topics']['path']]
    classes={t:get_message(types[t]) for t in topics};decoded={t:[] for t in topics}
    while reader.has_next():
        topic,blob,timestamp=reader.read_next()
        if topic in classes:decoded[topic].append(base.plain(dict(message_to_ordereddict(deserialize_message(blob,classes[topic])))))
    assert all(len(decoded[t])==storage['actual_topic_counts'][t] for t in topics)
    profiles=decoded[topics[0]];paths=decoded[topics[1]]
    raw_cases={'profile_dims5':sum(len(p['layout']['dim'])==5 for p in profiles),'profile_label65':sum(any(len(d['label'].encode())==65 for d in p['layout']['dim']) for p in profiles),'path_frame129':sum(len(p['header']['frame_id'].encode())==129 for p in paths),'legal_profile_boundary':sum(len(p['layout']['dim'])==4 and any(len(d['label'].encode())==64 for d in p['layout']['dim']) for p in profiles)}
    assert all(v>=1 for v in raw_cases.values()),raw_cases
    reg=base.read_jsonl(D/'regulator_source.jsonl');pv=[r for r in reg if r['type']=='profile_version'];pathv=[r for r in reg if r['type']=='path_version']
    source_cases={'profile_dims5':[r for r in pv if r.get('received_dims')==5 and r.get('resource_valid') is False and r.get('valid') is False],'profile_label65':[r for r in pv if r.get('received_dims')==4 and r.get('received_data_elements')==80 and r.get('resource_valid') is False and r.get('valid') is False],'path_frame129':[r for r in pathv if r.get('frame_bytes')==129 and r.get('resource_valid') is False and r.get('valid') is False]}
    assert all(len(rows)==raw_cases[key] for key,rows in source_cases.items()),source_cases
    assert any(r.get('valid') is True and r.get('received_dims')==4 for r in pv)
    decisions=[r for r in reg if r['type']=='decision'];invalid=sorted([r for rows in source_cases.values() for r in rows],key=lambda r:r['processed_ns'])
    for r in invalid:
        assert not any(d.get('accepted') and d['activation_commit_ns']>=r['processed_ns'] and d['task_generation']<r['task_generation'] for d in decisions),'old task accepted after metadata rejection'
    last_invalid=invalid[-1]['processed_ns'];jobs={r['job']['job_id']:r['job'] for r in reg if r['type']=='job'}
    recovered=[d for d in decisions if d.get('accepted') and jobs[d['job_id']]['freeze_ns']>last_invalid]
    assert recovered,'no fresh native recovery'
    result={'schema':'p1-resource-metadata-proof-v2','run_id':D.name,'selected_gate_passed':True,'original_wrapper_failed_record':str(E/'resource_metadata_v3_batch_20261007.json'),'analysis_only_no_new_ros':True,'base_report_sha256':sha(P),'delivery_ledger_sha256':sha(L),'base_report':report,'delivery_ledger':ledger,'raw_case_counts':raw_cases,'raw_decoded_topic_counts':{t:len(decoded[t]) for t in topics},'source_rejections':source_cases,'last_invalid_processed_ns':last_invalid,'fresh_native_recovery_accepted':len(recovered),'storage':storage,'fixture_summary':json.loads((D/'fixture_source.jsonl').read_text()),'issues':[],'physical_publishers':0,'execute_qualified':False}
except BaseException as e:failure=repr(e);traceback.print_exc()
after={str(p):sha(p) for p in files};assert before==after
record={'schema':'p1-resource-metadata-analysis-record-v1','failure':failure,'result':result,'input_sha256_before':before,'input_sha256_after':after,'inputs_unchanged':True,'asset_final':verify_assets(Path(b['guard_manifest'])),'host_final':host_preflight(),'analysis_sha256':sha(Path(__file__)),'no_new_ros_nodes':True,'execute_qualified':False}
with (D/'resource_metadata_check_v2.json').open('x') as f:json.dump(record,f,indent=2)
print(json.dumps({'failure':failure,'selected_gate_passed':bool(result),'raw_case_counts':result['raw_case_counts'] if result else None,'recovery':result['fresh_native_recovery_accepted'] if result else None,'inputs_unchanged':True,'host_final':record['host_final']}))
raise SystemExit(1 if failure else 0)
