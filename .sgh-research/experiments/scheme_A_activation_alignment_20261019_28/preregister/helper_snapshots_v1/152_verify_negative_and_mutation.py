"""Read-only negative bag accounting plus fresh-copy detector mutations."""
from pathlib import Path
import hashlib,json,shutil
import yaml,rosbag2_py
from check_owned_fixture import analyze_inputs
from owned_release import create_only_json
N=Path(__file__).resolve().parent
D=N/'verification_negative_and_mutation_v1';D.mkdir()
def load(p):return json.loads(Path(p).read_text())
def dump(p,d):Path(p).open('x').write(json.dumps(d,sort_keys=True,indent=2)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
neg=[]
for name in ['owned_foreign_same_name_01','owned_foreign_wrong_type_02','owned_wrong_config_01','owned_wrong_hook_01']:
 r=N/'runs'/name;result=load(r/'result.json');session=load(r/'publisher/session_summary.json')
 reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(r/'recorder/bag'),storage_id='sqlite3'),rosbag2_py.ConverterOptions(input_serialization_format='cdr',output_serialization_format='cdr'))
 counts={x.name:0 for x in reader.get_all_topics_and_types()};total=0
 while reader.has_next():
  topic,blob,stamp=reader.read_next();counts[topic]+=1;total+=1
 fields=['/wamv/thrusters/left/thrust','/wamv/thrusters/right/thrust','/research/control/applied']
 allzero=all(counts.get(k,0)==0 for k in fields) and all(v['generated']==v['emitted']==v['dropped']==0 for v in session['streams'].values())
 row={'run_id':name,'expected_negative_rejection':result['held_negative_passed'],'rejection':result['error'],'release_absent':not (r/'release.json').exists(),'release_receipt_absent':not (r/'publisher/release_receipt.json').exists(),'sensor_start_absent':not (r/'synthetic_start.json').exists(),'entire_storage_counts':counts,'total_stored_messages':total,'entire_physical_and_applied_zero':allzero,'cleanup_complete':result['cleanup_complete'],'run_result_sha256':sha(r/'result.json'),'session_sha256':sha(r/'publisher/session_summary.json')}
 row['passed']=row['expected_negative_rejection'] and row['release_absent'] and row['release_receipt_absent'] and row['sensor_start_absent'] and allzero and row['cleanup_complete'];neg.append(row)
base=load(N/'runs/owned_positive_07/checker_inputs.json');originals={str(p):sha(p) for p in [Path(base[k]) for k in ['observer_source','expected_witness_header','topics_file']]+[Path(x) for x in base['owned_manifests'].values()]+list(Path(base['bag']).rglob('*.yaml'))+list(Path(base['bag']).rglob('*.db3'))}
mutations=[]
for kind in ['source_decision_payload','worker_actual_gid','storage_metadata_count','witness_expected_identity']:
 d=D/kind;d.mkdir();inputs=json.loads(json.dumps(base))
 if kind=='source_decision_payload':
  rows=[json.loads(x) for x in Path(base['observer_source']).read_text().splitlines()];changed=next(x for x in rows if x['type']=='decision' and x['job_id']);changed['accepted']=not changed['accepted'];p=d/'source.jsonl';p.open('x').write(''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows));inputs['observer_source']=str(p)
 elif kind=='worker_actual_gid':
  m=load(base['owned_manifests']['worker']);e=next(e for e in m['endpoints'] if e['topic']=='/p1/worker_capability' and e['kind']=='publisher');e['gid'][0]^=1;p=d/'worker_owned_manifest.json';dump(p,m);inputs['owned_manifests']['worker']=str(p)
 elif kind=='storage_metadata_count':
  p=d/'bag';shutil.copytree(base['bag'],p);mp=p/'metadata.yaml';m=yaml.safe_load(mp.read_text());m['rosbag2_bagfile_information']['message_count']+=1;mp.write_text(yaml.safe_dump(m));inputs['bag']=str(p)
 else:
  m=load(base['expected_witness_header']);m['worker_instance']='f'*64;p=d/'expected_header.json';dump(p,m);inputs['expected_witness_header']=str(p)
 dump(d/'inputs.json',inputs)
 try:report=analyze_inputs(inputs);detected=not report['passed']
 except Exception as e:report={'passed':False,'reader_error':str(e)};detected=True
 report['deliberate_detector_mutation']=kind;report['D1_dynamic_qualified']=False;report['execute_qualified']=False;create_only_json(d/'report.json',report)
 mutations.append({'mutation':kind,'detected':detected,'report':str(d/'report.json'),'report_sha256':sha(d/'report.json'),'reader_error':report.get('reader_error')})
unchanged=all(sha(p)==h for p,h in originals.items())
report={'schema':'p1-owned-negative-verification-v1','held_negative_runs':neg,'detector_mutations':mutations,'original_positive_inputs_unchanged':unchanged,'original_sha256':originals,'passed':all(x['passed'] for x in neg) and all(x['detected'] for x in mutations) and unchanged,'scope':'bounded localhost fixture components only','D1_dynamic_qualified':False,'execute_qualified':False}
create_only_json(D/'report.json',report);print(json.dumps({'passed':report['passed'],'negative_runs':len(neg),'mutations':len(mutations),'report':str(D/'report.json')},indent=2))
