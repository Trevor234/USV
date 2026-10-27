from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET
D=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
v1=D/'independent_ladder_review_v1.json';original_sha=sha(v1);data=json.loads(v1.read_text())
assert data['issues']==[{'code':'native_late_and_cap_component_tests_preserved'}]
assert all(c['passed'] is True for c in data['cases'])
assert data['actual_accepted']==data['actual_candidate_activations']==408 and data['actual_SQLite_bound_sensor_states']==4865
verified=0
for case in data['cases']:
 report_path=Path(case['locked_report']['path']);assert sha(report_path)==case['locked_report']['sha256']
 report=json.loads(report_path.read_text());assert report['input_sha256_before']==report['input_sha256_after']
 for p,digest in report['input_sha256_before'].items():assert sha(p)==digest;verified+=1
xml=Path(data['native_late_tests']['evidence']['path']);assert sha(xml)==data['native_late_tests']['evidence']['sha256']
root=ET.parse(xml).getroot();assert int(root.attrib['tests'])==16 and int(root.attrib['failures'])==0 and int(root.attrib['errors'])==0 and int(root.attrib['disabled'])==0
names={'LateActualInputRollsBackCheckpointAndCorrectsFutureWithoutRewritingPast','EventExactlyAtCheckpointIsReplayedFromStrictlyEarlierCheckpoint','QueryWorkCapIsTerminalAndDoesNotPretendToProduceAState','LateInputBeyondReplayWorkBudgetIsExplicitFailure'}
selected=[r for r in root.findall('.//testcase') if r.attrib['name'] in names]
assert {r.attrib['name'] for r in selected}==names and all(not r.findall('failure') for r in selected)
data['schema']='p1-longitudinal-independent-ladder-review-v2';data['passed']=True;data['issues']=[]
data['native_late_tests']['cases']=[dict(name=r.attrib['name'],status=r.attrib.get('status'),failures=len(r.findall('failure'))) for r in selected]
data['correction_of_v1']={'path':str(v1),'sha256':original_sha,'reason':'Review v1 selected Native names by Late/Checkpoint/Budget and omitted the actual QueryWorkCap test, causing a false negative count threshold. All v1 actual Source/SQLite/checker evidence checks passed. V2 selects four exact names and rechecks all locked run input SHA values; no run or preregistered source was changed.','original_review_issue':{'code':'native_late_and_cap_component_tests_preserved'}}
data['locked_raw_files_SHA_reverified_in_correction']=verified
data['review_recipe']={'path':str(Path(__file__)),'sha256':sha(__file__),'bytes':Path(__file__).stat().st_size}
data['initial_independent_primary_review_recipe']=json.loads(v1.read_text())['review_recipe']
assert sha(v1)==original_sha
out=D/'independent_ladder_review_v2.json'
with out.open('x') as f:json.dump(data,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
print(json.dumps(dict(path=str(out),sha256=sha(out),passed=True,accepted=408,states=4865,native_tests=16,selected_late_cap_tests=4,locked_raw_files=verified,native_rewinds=[c['native_work']['actual_rewound_samples'] for c in data['cases']],canonical_rollbacks=[c['independent_timestamp_geometry']['rollback_count'] for c in data['cases']]),sort_keys=True))
