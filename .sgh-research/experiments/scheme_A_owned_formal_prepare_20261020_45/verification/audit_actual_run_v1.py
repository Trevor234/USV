#!/usr/bin/env python3
"""Independent actual owned identity, grant, typed-payload and closure audit.

Source cdr hashes describe typed reserialization, not original DDS wire bytes.
The bag is kept raw; all fields are decoded and compared independently. Worker
raw CDR is additionally parsed field-by-field to locate alignment differences.
"""
import copy
from collections import Counter,defaultdict
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys

import yaml
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from rosidl_runtime_py.convert import message_to_ordereddict
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import MultiArrayDimension

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent
R=D/'runs/formal_prepare_01'


def pin(path):
    b=Path(path).read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(p):return json.loads(Path(p).read_bytes())
def rows(path):return [json.loads(line) for line in Path(path).read_text().splitlines()]
def create(p,value):
    with Path(p).open('x') as f:json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')


def cap_layout(raw):
    assert raw[:4]==b'\x00\x01\x00\x00','registered CDR1 little endian encapsulation'
    pos=4;padding=[];value={}
    def scalar(fmt,width):
        nonlocal pos
        n=(-(pos-4))%width;padding.extend(range(pos,pos+n));pos+=n
        v=struct.unpack_from('<'+fmt,raw,pos)[0];pos+=width;return v
    def text():
        nonlocal pos
        n=scalar('I',4);assert 0<n<=1024 and raw[pos+n-1]==0
        s=raw[pos:pos+n-1].decode();pos+=n;return s
    for k in ['schema_version','run_id','boot_id','contract_hash','nominal_hash','worker_instance','clock_name','backend','matrix_layout']:value[k]=text()
    for k,fmt,width in [('horizon_steps','I',4),('prediction_dt','d',8),('pid','q',8),('startup_ns','q',8),
        ('completed_jobs','Q',8),('active_job','Q',8),('pending_count','I',4),('fault_injection_enabled','?',1),('fatal','?',1)]:value[k]=scalar(fmt,width)
    value['reason']=text();suffix=len(raw)-pos;assert suffix in {0,(-pos)%4},'no unexplained CDR suffix'
    normalized=bytearray(raw[:pos])
    for index in padding:normalized[index]=0
    return value,bytes(normalized),padding,suffix


def expected_input(ros_type,stamp,contract):
    message=get_message(ros_type)();sec,nano=divmod(stamp,1_000_000_000)
    if ros_type=='rosgraph_msgs/msg/Clock':message.clock.sec=sec;message.clock.nanosec=nano
    elif ros_type=='std_msgs/msg/Float64MultiArray':
        a=MultiArrayDimension(label='stamp_sec:'+str(sec),size=21,stride=84)
        b=MultiArrayDimension(label='stamp_nanosec:'+str(nano),size=4,stride=4)
        message.layout.dim=[a,b];message.data=[v for k in range(21) for v in [0.,0.,0.,.2*k]]
    else:
        message.header.stamp.sec=sec;message.header.stamp.nanosec=nano
        if ros_type=='nav_msgs/msg/Odometry':
            message.header.frame_id=contract['expected_pose_frame'];message.child_frame_id=contract['expected_child_frame'];message.pose.pose.orientation.w=1.
        elif ros_type=='sensor_msgs/msg/Imu':message.header.frame_id=contract['expected_imu_frame'];message.orientation.w=1.
        elif ros_type=='nav_msgs/msg/Path':
            message.header.frame_id=contract['expected_pose_frame']
            for _ in range(21):
                p=PoseStamped();p.header=copy.deepcopy(message.header);p.pose.orientation.w=1.;message.poses.append(p)
        else:raise AssertionError('unregistered input type')
    return message_to_ordereddict(message)


def stamp_of(value,ros_type):
    if ros_type=='std_msgs/msg/Float64MultiArray':
        dims=value['layout']['dim'];return int(dims[0]['label'].split(':')[1])*1_000_000_000+int(dims[1]['label'].split(':')[1])
    t=value['clock'] if ros_type=='rosgraph_msgs/msg/Clock' else value['header']['stamp']
    return t['sec']*1_000_000_000+t['nanosec']


def verify(data):
    reg=data['registration'];contract=data['contract'];manifests=data['manifests'];result=data['result']
    assert result['passed'] and result['preparation_observed'] and not result['stage_qualified']
    assert contract['qualification']=='execution_pre_freeze' and contract['fault_injection_enabled'] is False and contract['execute_qualified'] is False and len(contract)==84
    assert len(contract['pending_final_calibration'])==8
    allowed_topics=data['topics'];assert len(allowed_topics)==7
    for role,m in manifests.items():
        assert m['run_id']==reg['run_id'] and m['contract_sha256']==reg['contract_sha256'] and m['boot_id']==data['boot']
        assert m['execute_qualified'] is False and m['physical_release_qualified'] is False and m['effective_parameters_immutable'] is True
        assert m['source_bundle_sha256']==data['registry']['roles'][role]['source_bundle']['sha256']
        assert m['binary_sha256']==data['registry']['roles'][role]['binary_sha256']
        if role!='recorder':assert m['contract_configuration']==contract
        eps=m['endpoints'];assert len({tuple(e['gid']) for e in eps})==len(eps)
        assert all(len(e['gid'])==16 and any(e['gid']) for e in eps)
    assert manifests['preparer']['mode']=='no_output' and all(e['kind']=='subscription' for e in manifests['preparer']['endpoints'])
    assert len(manifests['preparer']['endpoints'])==7
    assert sum(e['kind']=='publisher' for e in manifests['fixture']['endpoints'])==5
    assert len(manifests['fixture']['endpoints'])==6 and manifests['fixture']['Applied_subscribers']==0
    assert len(manifests['worker']['endpoints'])==3 and manifests['worker']['fault_injection_permission'] is False
    assert len(manifests['recorder']['endpoints'])==7 and manifests['recorder']['record_options']['topics']==allowed_topics
    forbidden={'/p1/solve_job','/p1/execution_decision','/research/control/applied',*contract['output_topics'].values()}
    for role,m in manifests.items():
        assert not any(e['kind']=='publisher' and e['topic'] in forbidden for e in m['endpoints'])
    pref=data['sources']['preparer'];fix=data['sources']['fixture'];worker=data['sources']['worker']
    for source in [pref,fix]:assert [r['source_sequence'] for r in source]==list(range(1,len(source)+1)),'Source row continuity'
    assert not any(r['type'] in ['prepare_terminal_failure','prepare_grant_rejected','typed_resource_rejected','unexpected_candidate'] for r in pref)
    accepted=[r for r in pref if r['type']=='prepare_grant_accepted'];replay=[r for r in pref if r['type']=='actual_grant_replay_rejected']
    assert len(accepted)==len(replay)==1 and replay[0]['gate']['state']=='prepared'
    grant=data['grant'];ready=data['ready'];a=accepted[0];g=a['gate'];c=a['context']
    assert a['request']==grant and g['state']=='prepared' and grant['run_id']==reg['run_id']
    assert grant['contract_sha256']==reg['contract_sha256'] and grant['spec_sha256']=='317ec56f9c1211b9d8adc5dc727e2a20c1f281afd2047efafecbac797c46d798'
    assert grant['ready_generation']==ready['ready_generation']==c['ready_generation']==1 and grant['version']==ready['version']==c['version']
    assert grant['ready_snapshot_sha256']==c['ready_snapshot_sha256']==data['ready_sha256']
    for k in ['driver_live','worker_live','fixture_live','recorder_live','worker_capability_valid','source_inputs_valid','reference_pair_ready','recording_ready','sink_ready']:assert c[k] is True
    assert c['stopping'] is False and all(c[k]==0 for k in ['physical_publishers','solve_job_publishers','decision_publishers','applied_publishers'])
    assert g['created_ns']<=grant['issued_ns']<=g['prepared_ns']<g['deadline_ns']
    assert g['prepared_ns']-grant['issued_ns']<=2_000_000_000 and 0<=g['prepared_ns']-c['capability_receipt_ns']<=600_000_000
    before=[r for r in pref if r['source_sequence']<a['source_sequence']]
    inputs=[r for r in pref if r['type']=='input_receipt'];assert all(r['owned_admitted'] and r['value_valid'] for r in inputs)
    expected_gid={e['topic']:e['gid'] for e in manifests['fixture']['endpoints'] if e['kind']=='publisher'}
    assert all(r['publisher_gid']==expected_gid[r['topic']] for r in inputs)
    latest={r['topic']:r for r in before if r['type']=='input_receipt'}
    input_names=[k for k in allowed_topics if k not in ['/p1/worker_capability','/p1/solve_candidate']]
    assert set(latest)==set(input_names)
    for r in latest.values():assert 0<=g['prepared_ns']-r['receive_ns']<=100_000_000
    clock=latest['/clock'];current=clock['sim_stamp_ns']+g['prepared_ns']-clock['receive_ns']
    for k in ['odom','imu']:
        stamp=latest[contract['input_topics'][k]]['sim_stamp_ns'];assert -20_000_000<=current-stamp<=100_000_000
    paths={r['sim_stamp_ns']:r for r in before if r['type']=='input_receipt' and r['topic']==contract['input_topics']['path']}
    profiles={r['sim_stamp_ns']:r for r in before if r['type']=='input_receipt' and r['topic']==contract['input_topics']['profile']}
    paired=set(paths)&set(profiles);assert paired and ready['paired_reference_stamp_ns'] in paired
    pair_commit=max(max(paths[k]['receive_ns'],profiles[k]['receive_ns']) for k in paired)
    assert 0<=g['prepared_ns']-pair_commit<=100_000_000
    graphs=[r for r in pref if r['type']=='actual_graph_check'];assert graphs and all(r['forbidden_Writers_absent'] for r in graphs)
    terminal=data['terminals']['preparer'];assert terminal['was_prepared'] and not terminal['failed'] and terminal['normal_source_complete']
    assert terminal['gate']['state']=='closed' and all(terminal[k]==0 for k in ['solve_jobs','Decisions','Applied','physical_calls'])
    assert terminal['validated_input_counts']==[sum(r['topic']==k for r in inputs) for k in ['/clock',contract['input_topics']['odom'],contract['input_topics']['imu'],contract['input_topics']['path'],contract['input_topics']['profile']]]
    assert terminal['rejected_input_counts']==[0]*5
    publications=[r for r in fix if r['type']=='input_publish_result'];assert publications and all(r['returned'] for r in publications)
    expected_keys=Counter((r['topic'],r['sim_ns']) for r in publications)
    assert all(v==1 for v in expected_keys.values()) and all(r['publisher_gid']==expected_gid[r['topic']] for r in publications)
    topic_counts=Counter(r['topic'] for r in publications)
    assert dict(topic_counts)==data['terminals']['fixture']['published_counts']
    bag_inputs=[r for r in data['bag'] if r['topic'] in topic_counts]
    bag_keys=Counter((r['topic'],stamp_of(r['value'],r['ros_type'])) for r in bag_inputs)
    assert bag_keys==expected_keys,'Source-to-Stored input key accounting'
    for row in bag_inputs:assert row['value']==expected_input(row['ros_type'],stamp_of(row['value'],row['ros_type']),contract),'all typed input fields'
    assert Counter((r['topic'],r['sim_stamp_ns']) for r in inputs)<=bag_keys,'actual admitted receipt subset'
    caps=[r for r in worker if r['type']=='capability_publish_attempt'];cap_returns=[r for r in worker if r['type']=='capability_publish_result']
    assert len(caps)==len(cap_returns)>0 and all(r['returned'] and not r['threw'] for r in cap_returns)
    assert [r['publish_seq'] for r in caps]==list(range(1,len(caps)+1))
    bag_caps=[r for r in data['bag'] if r['topic']=='/p1/worker_capability']
    canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'))
    assert Counter(canonical(r['payload']) for r in caps)==Counter(canonical(r['value']) for r in bag_caps),'all19 capability fields and counts'
    normalized_source=[];normalized_bag=[];suffixes=Counter()
    for r in caps:
        value,norm,padding,suffix=cap_layout(bytes.fromhex(r['cdr']['hex']));assert value==r['payload']
        normalized_source.append(norm);suffixes['Source_suffix_'+str(suffix)]+=1
    for r in bag_caps:
        value,norm,padding,suffix=cap_layout(bytes.fromhex(r['raw_hex']));assert value==r['value']
        normalized_bag.append(norm);suffixes['bag_suffix_'+str(suffix)]+=1
    assert Counter(normalized_source)==Counter(normalized_bag),'Worker CDR field bytes after explicit padding mask'
    for r in bag_caps:
        v=r['value'];assert v['run_id']==reg['run_id'] and v['contract_hash']==reg['contract_sha256'] and v['worker_instance']==manifests['worker']['worker_instance']
        assert not v['fault_injection_enabled'] and not v['fatal'] and v['completed_jobs']==v['active_job']==v['pending_count']==0
    summary=worker[-1];assert summary['type']=='worker_summary' and summary['normal_source_complete'] and not summary['fatal']
    assert summary['completed_jobs']==summary['generated_candidates']==summary['published_candidates']==0
    assert summary['source_rows_before_terminal']==summary['source_rows_emitted_before_terminal']==len(worker)-1
    assert summary['capability_source']['capability_source_complete'] and summary['capability_source']['capability_generated']==len(caps)
    assert not any(r['topic']=='/p1/solve_candidate' for r in data['bag'])
    assert len(data['bag'])==len(publications)+len(caps)==data['metadata']['rosbag2_bagfile_information']['message_count']
    rec=data['terminals']['recorder'];assert rec['clean'] and rec['Recorder_stop_completed'] and rec['prepared'] and rec['stop_signal']==2
    assert len(result['closed_roles'])==4
    for role in result['closed_roles']:
        assert role['returncode']==0 and role['group_empty'] and [s['signal'] for s in role['signals']]==['SIGINT']
    return {'stored_messages':len(data['bag']),'typed_input_messages':len(publications),'capability_messages':len(caps),
            'candidate_messages':0,'actual_grant_count':1,'actual_replay_rejections':1,'periodic_graph_checks_recorded':len(graphs),
            'native_graph_poll_count':terminal['graph_checks'],'admitted_input_receipts':len(inputs),
            'Worker_CDR_normalized_multiset_equal':True,'Worker_CDR_suffix_observations':dict(suffixes)}


def main():
    lock=read(D/'preflight/actual_source_lock_v1.json');pins=dict(lock['input_sha256'])
    for p in R.rglob('*'):
        assert not p.is_symlink()
        if p.is_file():pins[str(p)]=pin(p)
    extra=[D/'preflight/actual_run_registration_v1.json',D/'preflight/actual_source_lock_v1.json',Path(__file__).resolve(),
      D.parent.parent.parent/'usv_mpc_ws/src/usv_research_interfaces/msg/WorkerCapability.msg']
    # The workspace IDL is an explicit primary input; resolve it independently.
    extra[-1]=Path('/home/trevor/USV/usv_mpc_ws/src/usv_research_interfaces/msg/WorkerCapability.msg')
    for p in extra:pins[str(p)]=pin(p)
    for path,p in pins.items():assert pin(path)==p,path
    data={'registration':read(D/'preflight/actual_run_registration_v1.json'),
          'contract':read(D/'author/formal_pre_freeze_contract_v1.json'),'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'registry':read(D/'build/native_formal_attempt03/runtime_registry_v1.json'),
          'topics':read(D/'preflight/formal_topics_v1.json')['topics'],'result':read(R/'driver_result.json'),
          'manifests':{r:read(R/r/'manifest.json') for r in ['fixture','worker','recorder','preparer']},
          'terminals':{r:read(R/r/'terminal.json') for r in ['fixture','recorder','preparer']},
          'sources':{r:rows(R/r/'source.jsonl') for r in ['fixture','worker','preparer']},
          'ready':read(R/'preparer/ready.json'),'grant':read(R/'preparer/grant.json'),
          'ready_sha256':pin(R/'preparer/ready.json')['sha256'],
          'metadata':yaml.safe_load((R/'recorder/bag/metadata.yaml').read_text()),'bag':[]}
    db=next((R/'recorder/bag').glob('*.db3'));connection=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
    assert connection.execute('pragma integrity_check').fetchone()==('ok',)
    for topic,ros_type,timestamp,raw in connection.execute('select t.name,t.type,m.timestamp,m.data from messages m join topics t on t.id=m.topic_id order by m.id'):
        value=message_to_ordereddict(deserialize_message(raw,get_message(ros_type)))
        data['bag'].append({'topic':topic,'ros_type':ros_type,'timestamp':timestamp,'raw_sha256':hashlib.sha256(raw).hexdigest(),
                            'raw_hex':raw.hex() if topic=='/p1/worker_capability' else '', 'value':value})
    connection.close()
    output={'schema':'formal-owned-actual-independent-audit-v1','passed':False,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
    try:
        metrics=verify(data);negative=[]
        def reject(name,mutate):
            changed=copy.deepcopy(data);mutate(changed)
            try:verify(changed);rejected=False;why='incorrect acceptance'
            except (AssertionError,ValueError,KeyError,struct.error) as error:rejected=True;why=str(error)
            negative.append({'name':name,'rejected':rejected,'reason':why})
        reject('wrong_run_grant',lambda x:x['grant'].__setitem__('run_id','foreign'))
        reject('formal_fault_true',lambda x:x['contract'].__setitem__('fault_injection_enabled',True))
        reject('missing_replay_evidence',lambda x:x['sources'].__setitem__('preparer',[r for r in x['sources']['preparer'] if r['type']!='actual_grant_replay_rejected']))
        reject('Source_row_gap',lambda x:x['sources']['fixture'].pop(2))
        reject('one_stored_message_missing',lambda x:x['bag'].pop())
        reject('Worker_job_count_nonzero',lambda x:x['sources']['worker'][-1].__setitem__('completed_jobs',1))
        reject('bad_close_returncode',lambda x:x['result']['closed_roles'][0].__setitem__('returncode',2))
        reject('Recorder_stop_incomplete',lambda x:x['terminals']['recorder'].__setitem__('Recorder_stop_completed',False))
        reject('ready_generation_mismatch',lambda x:x['ready'].__setitem__('ready_generation',2))
        reject('group_not_empty',lambda x:x['result']['closed_roles'][0].__setitem__('group_empty',False))
        def bad_input(x):
            row=next(r for r in x['bag'] if r['ros_type']=='nav_msgs/msg/Odometry');row['value']['pose']['pose']['position']['x']=.1
        reject('stored_input_value_changed',bad_input)
        def bad_cap(x):
            row=next(r for r in x['bag'] if r['topic']=='/p1/worker_capability');row['value']['fault_injection_enabled']=True
        reject('stored_capability_changed',bad_cap)
        assert all(r['rejected'] for r in negative)
        after={p:pin(p) for p in pins};assert pins==after
        # Empty process groups are read-only rechecked after the owned wait/reap.
        for role in data['result']['closed_roles']:
            try:os.killpg(role['pid'],0);raise AssertionError('owned group unexpectedly present')
            except ProcessLookupError:pass
        output.update(passed=True,metrics=metrics,altered_actual_evidence_cases=negative,
          source_evidence_inputs=len(pins),input_sha256_before=pins,input_sha256_after=after,
          actual_owned_prepare_close_component_qualified=True,full_Regulator_no_output_qualified=False,
          B5_formal_freeze_qualified=False,M0b_qualified=False,M4_qualified=False,P1_qualified=False,
          recording_accounting='external Source-to-Stored exact counts, unique input timestamps, all typed fields, Worker field-byte normalization; original Recorder flag remains false',
          raw_reserialization_SHA_equals_wire_SHA_claimed=False,capability_packet_sequence_freshness_claimed=False)
    except Exception as e:output.update(error=repr(e),traceback=__import__('traceback').format_exc())
    create(D/'postrun/actual_prepare_audit_v1.json',output)
    print(json.dumps({'passed':output['passed'],'error':output.get('error'),'metrics':output.get('metrics'),'input_pins':output.get('source_evidence_inputs')}))
    return 0 if output['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
