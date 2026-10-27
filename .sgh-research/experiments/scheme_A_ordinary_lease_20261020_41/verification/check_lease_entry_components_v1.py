"""Only new orchestration joins: frozen actual gates and in-memory negative ACKs; no ROS."""
import sys,json,hashlib
from pathlib import Path
from copy import deepcopy
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(D/'author'))
from lease_stimulus_v1 import validate_ack,make_command,accepted_prefix
P=D.parent/'scheme_A_V2_watchdog_lease_20261019_35/author_r3/runs/v2_lease_r3_04'
files=[P/'observer/source.jsonl',P/'publisher/controlled_source.jsonl',P/'c38_pause_request.json',P/'c38_resume_request.json']
def pin(p):
    b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
before={str(p):pin(p) for p in files};source=[json.loads(x) for x in files[0].read_bytes().splitlines()];pub=[json.loads(x) for x in files[1].read_bytes().splitlines()]
positive=[];negative=[]
for action in ['pause','resume']:
    command=json.loads((P/('c38_'+action+'_request.json')).read_bytes());ack=next(r for r in source if r.get('type')==('diagnostic_c38_gate_paused' if action=='pause' else 'diagnostic_c38_gate_resumed'))
    digest=pin(P/('c38_'+action+'_request.json'))['sha256'];validate_ack(command,ack,digest);positive.append(action)
    for label in ['different_driver_start','different_script_sha','wrong_state','wrong_group','wrong_digest','expired_ACK']:
        bad=deepcopy(ack)
        if label=='different_driver_start':bad['gate']['driver_start_ticks']+=1
        elif label=='different_script_sha':bad['gate']['driver_tool_sha256']='0'*64
        elif label=='wrong_state':bad['gate']['state']='timed_out'
        elif label=='wrong_group':bad['group_registered']=not bad['group_registered']
        elif label=='wrong_digest':bad['request_sha256']='0'*64
        else:bad['checked_ns']=bad['gate']['deadline_ns']
        try:validate_ack(command,bad,digest)
        except ValueError as e:negative.append(dict(case=action+':'+label,rejected=True,reason=str(e)))
        else:raise AssertionError('invalid ACK accepted')
prefix=accepted_prefix(source,pub);assert prefix and prefix['decision']['accepted']
assert accepted_prefix([r for r in source if r.get('type')!='decision'],pub) is None
assert accepted_prefix(source,[]) is None
try:make_command('unknown',run='x',boot='b',identity=dict(pid=1,start_ticks=2),driver_sha='a'*64,owner_manifest_sha='b'*64,now_ns=1)
except ValueError as e:negative.append(dict(case='unknown_action',rejected=True,reason=str(e)))
else:raise AssertionError('unknown action admitted')
assert {p:pin(Path(p)) for p in before}==before
r=dict(passed=True,frozen_actual_ACK_cases=positive,healthy_actual_prefix=True,missing_decision_or_Applied_produces_no_prefix=True,
    negative_cases=negative,negative_count=len(negative),new_ROS_runs=0,
    ordinary_policy_44_negatives_and_two_seeded_auth_real_children_reused_from_batch38=True,
    helper_pin=pin(D/'author/lease_stimulus_v1.py'),input_sha256_before=before,input_sha256_after=before,
    stage_qualified=False,execute_qualified=False,research_conclusion=False)
with (D/'verification/lease_entry_components_v1.json').open('x') as f:json.dump(r,f,indent=2)
print(json.dumps(dict(passed=True,frozen_actual_ACK_cases=2,negative_cases=len(negative),ROS_context_created=False)))
