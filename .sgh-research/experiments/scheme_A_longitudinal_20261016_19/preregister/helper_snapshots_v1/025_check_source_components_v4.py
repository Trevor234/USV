#!/usr/bin/env python3
"""Independent scoped source/typed-input numerical checks. Never stage Go."""
import argparse
import array
import copy
from collections import Counter, defaultdict, deque
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
N = Path(__file__).resolve().parent
D = Path('/home/trevor/MPC/scheme_A_strict_source_20261011_03')
sys.path[:0] = [str(N), str(N / 'runtime')]
CAP_TOPIC = '/p1/worker_capability'
CONTRACT_SHA = '7570bc0005bccbd814ba66bc799e75e1c74887cc36ed508e6f4aa3256a71deb8'
SENSORS = {'clock': ('/clock','rosgraph_msgs/msg/Clock'),
    'odom_admission': ('/wamv/sensors/position/ground_truth_odometry','nav_msgs/msg/Odometry'),
    'imu_admission': ('/wamv/sensors/imu/imu/data','sensor_msgs/msg/Imu'),
    'path_version': ('/path/reference','nav_msgs/msg/Path'),
    'profile_version': ('/path/reference_profile','std_msgs/msg/Float64MultiArray')}


def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(x): return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
def plain(x):
    if isinstance(x, dict): return {k: plain(v) for k,v in x.items()}
    if hasattr(x, 'tolist'): return plain(x.tolist())
    if isinstance(x, (list, tuple, array.array)): return [plain(v) for v in x]
    return x
def angle(x): return math.atan2(math.sin(x), math.cos(x))
def yaw(q): return math.atan2(2*(q['w']*q['z']+q['x']*q['y']), 1-2*(q['y']**2+q['z']**2))
def stamp(x): return x['sec']*1_000_000_000+x['nanosec']
def fields(rows, typ): return [r for r in rows if r['type']==typ]
def typed_sha(x):
    y=copy.deepcopy(x);y['prediction_dt']={'ieee754_binary64_be':struct.pack('>d', y['prediction_dt']).hex()}
    return sha(canonical(y))


def imports():
    raw=(D/'preregister/input_numerics_contract_v4.json').read_bytes()
    if sha(raw)!=CONTRACT_SHA: raise ValueError('component source contract changed')
    c=json.loads(raw)
    for pin in c['source_identity']:
        if sha(Path(pin['path']).read_bytes())!=pin['sha256']: raise ValueError('source/helper identity changed: '+pin['path'])
    if sha(Path(c['source_observation_preregister']).read_bytes())!=c['source_observation_sha256']: raise ValueError('observation contract changed')
    import validate_readiness_v3 as safe
    import check_owned_fixture as storage
    return safe,storage,c


def load(root):
    safe, reader, contract=imports();root=Path(root)
    paths=['inputs.json','result.json','topics.json','worker/source.jsonl','observer/source.jsonl',
        'synthetic_source/transport_source.jsonl','synthetic_source/terminal.json','recorder/terminal.json']
    paths += [role+'/owned_manifest.json' for role in ('publisher','worker','observer','synthetic_source','recorder')]
    paths += ['recorder/bag/'+str(p.relative_to(root/'recorder/bag')) for p in sorted((root/'recorder/bag').rglob('*')) if p.is_file()]
    before={p:sha(safe.read_regular(root/p)) for p in paths}
    if sum((root/p).stat().st_size for p in paths)>134217728: raise ValueError('input total budget exceeded')
    records={p:safe.jsonl(safe.read_regular(root/p)) if p.endswith('.jsonl') else safe.strict_json(safe.read_regular(root/p)) for p in paths if not p.startswith('recorder/bag/')}
    inp=records['inputs.json'];config=safe.strict_json(safe.read_regular(inp['contract']))
    if sha(safe.read_regular(inp['contract']))!=inp['contract_sha256']: raise ValueError('contract pin changed')
    decoded,cdr,summary=reader.read_actual_storage(root/'recorder/bag',records['topics.json']['topics'])
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    def decode(raw,typ): return plain(dict(message_to_ordereddict(deserialize_message(raw,get_message(typ)))))
    return {'root':str(root),'safe':safe,'reader':reader,'contract':contract,'records':records,'decoded':decoded,
        'cdr':cdr,'storage':summary,'configuration':config,'hashes':before,'paths':paths,'decode':decode}


def rhs(s, held, p):
    _,_,psi,u,v,r=s;tl,tr=held
    m11=p['mass']-p['Xu_dot'];m22=p['mass']-p['Yv_dot'];m23=p['mass']*p['xg']-p['Yr_dot'];m32=p['mass']*p['xg']-p['Nv_dot'];m33=p['Iz']-p['Nr_dot']
    c13=-m22*v-m23*r;c23=m11*u
    b0=tl+tr-c13*r-(-p['Xu']-p['Xuu']*abs(u))*u
    b1=-c23*r-(-p['Yv']-p['Yvv']*abs(v))*v-(-p['Yr']-p['Yrr']*abs(r))*r
    b2=p['d_thruster']*(tr-tl)+c13*u+c23*v-(-p['Nv']-p['Nvv']*abs(v))*v-(-p['Nr']-p['Nrr']*abs(r))*r
    determinant=m22*m33-m23*m32
    return [math.cos(psi)*u-math.sin(psi)*v,math.sin(psi)*u+math.cos(psi)*v,r,b0/m11,(b1*m33-b2*m23)/determinant,(m22*b2-m32*b1)/determinant]


def advance(state, held, dt, p):
    s=list(state);h=dt/4
    for _ in range(4):
        k1=rhs(s,held,p);k2=rhs([x+h*.5*k for x,k in zip(s,k1)],held,p)
        k3=rhs([x+h*.5*k for x,k in zip(s,k2)],held,p);k4=rhs([x+h*k for x,k in zip(s,k3)],held,p)
        s=[x+h/6*(a+2*b+2*c+d) for x,a,b,c,d in zip(s,k1,k2,k3,k4)]
    s[2]=angle(s[2]);return s


def propagate(state, start, target, held, events, p):
    if target<start or target-start>1_000_000_000: raise ValueError('nominal target outside bound')
    s=list(state);cursor=start;held=list(held)
    for when,channel,value in events:
        if channel not in (0,1) or not math.isfinite(value): raise ValueError('history invalid')
        if when<=start: held[channel]=value;continue
        if when>target: break
        if when>cursor:s=advance(s,held,(when-cursor)/1e9,p);cursor=when
        held[channel]=value
    if target>cursor:s=advance(s,held,(target-cursor)/1e9,p)
    s[2]=angle(s[2]);return s


def reference(state,path,profile,ps,qs,c):
    count=20;dt=.2;nearest=min(range(len(path)),key=lambda i:math.hypot(path[i][0]-state[0],path[i][1]-state[1]))
    start=min(nearest+max(1,c['reference_start_offset']),len(path)-1)
    synced=len(profile)==len(path) and len(path)>=2 and ps==qs
    ref=[];t0=profile[start][3] if synced else 0.;j=start
    arc=[0.]
    for i in range(start,len(path)-1):arc.append(arc[-1]+math.hypot(path[i+1][0]-path[i][0],path[i+1][1]-path[i][1]))
    for k in range(count+1):
        if synced:
            tk=t0+k*dt
            while j<len(path)-1 and profile[j+1][3]<tk:j+=1
            if j==len(path)-1:point=[*path[j],profile[j][0],0.,profile[j][2]]
            else:
                seg=profile[j+1][3]-profile[j][3];a=max(0.,min(1.,(tk-profile[j][3])/seg)) if seg>1e-9 else 0.
                point=[path[j][0]+a*(path[j+1][0]-path[j][0]),path[j][1]+a*(path[j+1][1]-path[j][1]),angle(path[j][2]+a*angle(path[j+1][2]-path[j][2])),profile[j][0]+a*(profile[j+1][0]-profile[j][0]),0.,profile[j][2]+a*(profile[j+1][2]-profile[j][2])]
        else:
            distance=c['cruise_speed']*dt*k;idx=0
            while idx<len(arc)-1 and arc[idx+1]<distance:idx+=1
            ii=min(start+idx,len(path)-1)
            if ii<len(path)-1 and idx<len(arc)-1 and arc[idx+1]-arc[idx]>1e-6:
                a=max(0.,min(1.,(distance-arc[idx])/(arc[idx+1]-arc[idx])))
                point=[path[ii][0]+a*(path[ii+1][0]-path[ii][0]),path[ii][1]+a*(path[ii+1][1]-path[ii][1]),angle(path[ii][2]+a*angle(path[ii+1][2]-path[ii][2])),c['cruise_speed'],0.,0.]
            else:point=[*path[ii],c['cruise_speed'],0.,0.]
        point[2]=(state[2] if not ref else ref[-1][2])+angle(point[2]-(state[2] if not ref else ref[-1][2]));ref.append(point)
    return [v for col in ref for v in col],{'reference_mode':'profile_time' if synced else 'cruise_arc_fallback','profile_t0':t0,'nearest_index':nearest,'start_index':start}


def analyze(s):
    safe=s['safe'];rec=s['records'];cfg=s['configuration'];issues=[];groups={}
    def need(ok,code,**detail):
        if not ok:issues.append({'code':code,**detail})
        return bool(ok)
    def near(a,b,tol):return len(a)==len(b) and all(type(x) in (float,int) and math.isfinite(x) and abs(x-y)<=tol for x,y in zip(a,b))
    def once(rows,typ):
        chosen=fields(rows,typ)
        if len(chosen)!=1:raise ValueError('exactly one '+typ+' required')
        return chosen[0]
    worker=rec['worker/source.jsonl'];obs=rec['observer/source.jsonl'];inp=rec['inputs.json']
    owned={role:rec[role+'/owned_manifest.json'] for role in ('publisher','worker','observer','synthetic_source','recorder')}
    start=len(issues)
    allowed_worker=safe.WORKER_EVENTS|{'capability_source_header','capability_publish_attempt','capability_publish_result'}
    need(all(r['type'] in allowed_worker for r in worker),'unknown_positive_worker_source_event')
    need(all(r['type'] in safe.OBSERVER_EVENTS for r in obs),'unknown_positive_observer_source_event')
    # The actual reader scans all topics. Transport has exact original CDR identities.
    transport=s['reader'].transport_join(s['cdr'],rec['synthetic_source/transport_source.jsonl'],owned,rec['topics.json']['topics'])
    issues.extend(transport['issues'] if isinstance(transport,dict) else transport)
    groups['whole_transport_storage']={'passed':len(issues)==start,'storage':s['storage']}
    start=len(issues)
    source_join=s['reader'].source_typed_join(obs,worker,s['decoded'])
    issues.extend(source_join['issues'])
    anchors=fields(obs,'legacy_anchor')
    applied=[r['message'] for r in s['decoded'][safe.APPLIED_TOPIC]]
    need([r['sequence'] for r in anchors]==list(range(1,len(applied)+1)) and len(anchors)==len(applied),'complete_legacy_applied_population')
    need(all(safe.equal(a['applied'],b) for a,b in zip(anchors,applied)),'complete_legacy_applied_full_fields')
    groups['whole_source_typed_storage']={'passed':len(issues)==start,'streams':source_join.get('streams'),'Applied':len(applied)}
    start=len(issues)
    header=once(worker,'capability_source_header');terminal=once(worker,'worker_summary');wmanifest=owned['worker']
    need(worker[0] is header,'cap_header_first')
    need(worker[-1] is terminal,'worker_terminal_last')
    need(header['schema']=='p1-capability-source-header-v1' and header['run_id']==inp['run_id'] and header['boot_id']==wmanifest['boot_id'] and header['pid']==wmanifest['pid'] and header['process_start_ticks']==wmanifest['process_start_ticks'],'cap_header_identity')
    need(header['worker_instance']==wmanifest['worker_instance'] and header['binary_sha256']==inp['builds']['worker']['binary_sha256'] and header['source_bundle_sha256']==inp['source_bundles']['worker']['sha256'],'cap_header_author')
    need(header['owned_manifest_sha256']==s['hashes']['worker/owned_manifest.json'],'cap_header_manifest_sha')
    expected_endpoint=next(e for e in wmanifest['endpoints'] if e['kind']=='publisher' and e['topic']==CAP_TOPIC)
    need(safe.equal(header['endpoint'],expected_endpoint),'cap_header_GID')
    attempts=fields(worker,'capability_publish_attempt');results=fields(worker,'capability_publish_result');count=len(attempts)
    need(count>0 and [r['publish_seq'] for r in attempts]==list(range(1,count+1)) and [r['publish_seq'] for r in results]==list(range(1,count+1)),'cap_source_sequence')
    cap_fields=safe.CAP_FIELDS;previous_end=0
    for a,r in zip(attempts,results):
        need(worker.index(header)<worker.index(a)<worker.index(r)<worker.index(terminal),'cap_source_record_order')
        value=a['payload'];need(set(value)==cap_fields,'cap_payload_full_field_set',seq=a['publish_seq'])
        need(all(safe.integer(value[k],0,safe.U64) for k in ('horizon_steps','pid','startup_ns','completed_jobs','active_job','pending_count')) and all(type(value[k]) is bool for k in ('fault_injection_enabled','fatal')) and type(value['prediction_dt']) is float and math.isfinite(value['prediction_dt']),'cap_exact_scalar_types')
        need(all(type(value[k]) is str for k in cap_fields-{'horizon_steps','pid','startup_ns','completed_jobs','active_job','pending_count','fault_injection_enabled','fatal','prediction_dt'}),'cap_exact_string_types')
        need(all(safe.integer(a[k]) for k in ('publish_seq','snapshot_ns','attempt_record_ns')) and all(safe.integer(r[k]) for k in ('publish_seq','publish_start_ns','publish_end_ns')),'cap_exact_source_integer_types')
        need(a['schema']=='p1-capability-publish-attempt-v1' and r['schema']=='p1-capability-publish-result-v1','cap_schema')
        need(a['payload_sha256']==r['payload_sha256']==typed_sha(value),'cap_payload_SHA',seq=a['publish_seq'])
        need(previous_end<=a['snapshot_ns']<=a['attempt_record_ns']<=r['publish_start_ns']<=r['publish_end_ns'] and r['returned'] is True and r['threw'] is False,'cap_actual_call_order',seq=a['publish_seq']);previous_end=r['publish_end_ns']
        raw=bytes.fromhex(a['cdr']['hex'])
        need(len(raw)==a['cdr']['bytes'] and 0<len(raw)<=1048576 and sha(raw)==a['cdr']['sha256'] and a['cdr']['representation']=='typed_reserialization_cdr','cap_cdr_identity')
        need(safe.equal(s['decode'](raw,'usv_research_interfaces/msg/WorkerCapability'),value),'cap_cdr_full_fields')
        need(value['run_id']==inp['run_id'] and value['boot_id']==header['boot_id'] and value['worker_instance']==header['worker_instance'] and value['pid']==header['pid'] and value['startup_ns']==header['startup_ns'] and value['contract_hash']==inp['contract_sha256'] and value['nominal_hash']==cfg['nominal_hash'],'cap_frozen_identity')
    actual=[r['message'] for r in s['decoded'][CAP_TOPIC]]
    need(len(actual)==count and all(safe.equal(a['payload'],v) for a,v in zip(attempts,actual)),'cap_full_publisher_storage_population',source=count,storage=len(actual))
    expected={'schema':'p1-capability-source-terminal-v1','capability_generated':count,'capability_attempt_records':count,'capability_publish_calls':count,'capability_publish_returned':count,'capability_publish_threw':0,'capability_result_records':count,'capability_aborted_before_publish':0,'capability_source_io_failed':False,'capability_last_publish_seq':count,'capability_last_payload_sha256':attempts[-1]['payload_sha256'] if attempts else '', 'capability_last_publish_end_ns':results[-1]['publish_end_ns'] if results else 0,'capability_source_complete':True}
    need(safe.equal(terminal['capability_source'],expected),'cap_terminal_counters')
    need(safe.integer(terminal['finished_ns']) and terminal['finished_ns']>=previous_end,'cap_terminal_time')
    need(terminal['source_rows_before_terminal']==terminal['source_rows_emitted_before_terminal']==len(worker)-1 and terminal['source_io_failed'] is False and terminal['normal_source_complete'] is True,'worker_complete_source_rows')
    summaries=fields(obs,'source_summary');need(len(summaries)==1 and obs[-1] is summaries[0] and summaries[0]['generated']==summaries[0]['emitted']==len(obs)-1 and summaries[0]['dropped']==0 and summaries[0]['normal_source_complete'] is True,'observer_complete_source_rows')
    groups['capability_source_population']={'passed':len(issues)==start,'source':count,'storage':len(actual),'packet_unique_identity':False,'packet_freshness':False}
    start=len(issues);raws={};raw_counts={};msg_index={};state_by_odom={};imu_by_seq={};paths={};profiles={};clocks={};clock_window=deque();last_receive=last_sim=0
    state=[0.]*6
    for typ,(topic,ros_type) in SENSORS.items():
        rows=fields(obs,typ);raw_counts[typ]=len(rows);raws[typ]=[];cursor=0
        gid=next(e['gid'] for e in owned['synthetic_source']['endpoints'] if e['kind']=='publisher' and e['topic']==topic)
        previous_entry=0
        for seq,row in enumerate(rows,1):
            raw=row.get('raw_input');need(type(raw) is dict,'raw_input_missing',event=typ,seq=seq)
            if type(raw) is not dict:continue
            need(set(raw)==set('schema topic message_type callback_sequence entry_steady_ns publisher_gid rmw_implementation source_timestamp received_timestamp publication_sequence_number reception_sequence_number from_intra_process cdr_bytes cdr_sha256 cdr_hex'.split()),'raw_exact_field_set')
            need(all(safe.integer(raw[k],0,safe.U64) for k in ('callback_sequence','entry_steady_ns','source_timestamp','received_timestamp','publication_sequence_number','reception_sequence_number','cdr_bytes')),'raw_exact_integer_types')
            need(raw['schema']=='p1-input-callback-full-cdr-v1' and raw['topic']==topic and raw['message_type']==ros_type and raw['callback_sequence']==seq,'raw_schema_sequence',event=typ,seq=seq)
            need(safe.equal(raw['publisher_gid'],gid) and raw['rmw_implementation']=='rmw_fastrtps_cpp' and raw['from_intra_process'] is False,'raw_actual_GID',event=typ)
            semantic_ns=row.get('receive_ns',row.get('processed_ns'))
            need(previous_entry<raw['entry_steady_ns']<=semantic_ns,'raw_entry_order',event=typ,seq=seq);previous_entry=raw['entry_steady_ns']
            blob=bytes.fromhex(raw['cdr_hex']);need(0<len(blob)<=1048576 and len(blob)==raw['cdr_bytes'] and sha(blob)==raw['cdr_sha256'],'raw_cdr_identity',event=typ,seq=seq)
            message=s['decode'](blob,ros_type);raws[typ].append((row,message));candidates=s['decoded'][topic]
            while cursor<len(candidates) and not safe.equal(candidates[cursor]['message'],message):cursor+=1
            need(cursor<len(candidates),'raw_full_fields_storage_subset',event=typ,seq=seq)
            if cursor<len(candidates):cursor+=1
            raw_sequence=row.get('sequence',row.get('received_sequence',seq));need(raw_sequence==seq,'raw_semantic_sequence',event=typ)
            msg_index[(typ,seq)]=(row,message)
        need(bool(rows),'raw_empty_population',event=typ)
    groups['five_callback_full_typed_fields']={'passed':len(issues)==start,'counts':raw_counts,'sensor_full_delivery_proven':False,'wire_padding_proven':False}
    start=len(issues)
    for row in obs:
        typ=row['type']
        if typ not in SENSORS:continue
        seq=row.get('sequence',row.get('received_sequence',row.get('raw_input',{}).get('callback_sequence')))
        if (typ,seq) not in msg_index:continue
        _,m=msg_index[(typ,seq)]
        if typ=='odom_admission':
            pose=m['pose']['pose'];twist=m['twist']['twist'];p=pose['position'];q=pose['orientation']
            v=[p['x'],p['y'],yaw(q),twist['linear']['x'],twist['linear']['y'],twist['angular']['z']]
            valid=all(math.isfinite(x) for x in v) and sum(q[k]**2 for k in ('x','y','z','w'))>=1e-12 and m['header']['frame_id']==cfg['expected_pose_frame'] and m['child_frame_id']==cfg['expected_child_frame']
            need(valid and row['valid'] is True,'positive_odom_admission');state=v if valid else state
            need(near(row['state'],state,1e-9) and row['stamp_ns']==stamp(m['header']['stamp']),'odom_raw_state');state_by_odom[seq]=(list(state),row)
        elif typ=='imu_admission':
            rate=m['angular_velocity']['z'];valid=math.isfinite(rate) and m['header']['frame_id']==cfg['expected_imu_frame']
            need(valid and row['valid'] is True and abs(row['r_value']-rate)<=1e-9 and row['stamp_ns']==stamp(m['header']['stamp']),'imu_raw_state')
            if valid:state[5]=rate
            imu_by_seq[seq]=(rate,row)
        elif typ=='path_version':
            points=[[p['pose']['position']['x'],p['pose']['position']['y'],yaw(p['pose']['orientation'])] for p in m['poses']]
            digest=sha(canonical({'frame':m['header']['frame_id'],'path':points}))
            need(row['valid'] is True and row['resource_valid'] is True and row['fingerprint']==digest and row['points']==len(points),'path_raw_fingerprint',seq=seq)
            paths[seq]=(points,stamp(m['header']['stamp']),row)
        elif typ=='profile_version':
            labels=[d['label'] for d in m['layout']['dim']];ps=pn=-1
            for label in labels:
                if label.startswith('stamp_sec:'):ps=int(re.match(r'^[+-]?\d+',label[10:]).group())
                if label.startswith('stamp_nanosec:'):pn=int(re.match(r'^[+-]?\d+',label[14:]).group())
            profile=[m['data'][i:i+4] for i in range(0,len(m['data']),4)]
            need(row['valid'] is True and row['resource_valid'] is True and row['fingerprint']==sha(canonical(profile)) and len(profile)==row['rows'],'profile_raw_fingerprint',seq=seq)
            profiles[seq]=(profile,ps*1_000_000_000+pn,row)
        else:
            received=row['receive_ns'];sim=stamp(m['clock'])
            if last_receive and (received<=last_receive or sim<last_sim or sim-last_sim>5_000_000_000):clock_window.clear()
            last_receive,last_sim=received,sim
            while clock_window and received-clock_window[0][0]>600_000_000:clock_window.popleft()
            if not clock_window or received-clock_window[-1][0]>=10_000_000:clock_window.append((received,sim))
            while len(clock_window)>100:clock_window.popleft()
            span=received-clock_window[0][0];rtf=0. if span<400_000_000 else (sim-clock_window[0][1])/span
            valid=span>=400_000_000 and cfg['rtf_low']<=rtf<=cfg['rtf_high']
            need(row['sim_ns']==sim and row['rtf_window_span_ns']==span and row['rtf_stored_samples']==len(clock_window) and abs(row['rtf']-rtf)<=1e-12 and row['rtf_valid']==valid,'independent_clock_window',seq=seq)
            clocks[received]=row
    groups['callback_state_fingerprints_RTF']={'passed':len(issues)==start,'clocks':len(clocks),'paths':len(paths),'profiles':len(profiles),'general_float_formatter_qualified':False}
    start=len(issues);jobproof=[]
    for row in fields(obs,'job'):
        j=row['job'];p=row.get('input_provenance');need(type(p) is dict,'job_input_provenance_missing',job=j['job_id'])
        if type(p) is not dict:continue
        before=len(issues);frozen,odom=state_by_odom[p['odom_sequence']];frozen=list(frozen)
        if p['r_from_imu']:
            rate,imu=imu_by_seq[p['imu_sequence_raw']];frozen[5]=rate
            need(j['imu_sequence']==p['imu_sequence_raw'] and j['imu_stamp_ns']==imu['stamp_ns'] and j['imu_receive_ns']==imu['receive_ns'],'job_imu_selection')
        else:need(j['imu_sequence']==j['imu_stamp_ns']==j['imu_receive_ns']==0,'job_inactive_imu_mask')
        need(p['schema']=='p1-job-input-selection-v1' and j['odom_sequence']==p['odom_sequence'] and j['odom_stamp_ns']==odom['stamp_ns'] and j['odom_receive_ns']==odom['receive_ns'] and p['r_from_imu']==j['r_from_imu'] and near(j['frozen_state'],frozen,1e-9),'selected_raw_frozen_state',job=j['job_id'])
        clock=clocks[p['clock_receive_ns']]
        need(p['clock_sim_ns']==j['frozen_clock_sim_ns']==clock['sim_ns'] and p['clock_receive_ns']==j['frozen_clock_receive_ns'] and p['rtf_valid']==clock['rtf_valid'] and abs(p['rtf']-clock['rtf'])<=1e-12 and p['freeze_ns']==j['freeze_ns'],'selected_clock_rtf')
        path,ps,pathrow=paths[p['path_sequence']];profile,qs,profilerow=profiles[p['profile_sequence']]
        need(p['path_stamp_ns']==ps and p['profile_stamp_ns']==qs and pathrow['processed_ns']<=j['freeze_ns'] and profilerow['processed_ns']<=j['freeze_ns'],'immutable_reference_selection')
        expected_ref,meta=reference(frozen,path,profile,ps,qs,cfg)
        need(near(j['reference'],expected_ref,1e-9) and all(row[k]==v for k,v in meta.items()),'independent_frozen_reference126',job=j['job_id'])
        history=list(zip(j['history_sim_ns'],j['history_channel'],j['history_n']))
        need(len(history)==len(j['history_sim_ns'])==len(j['history_channel'])==len(j['history_n']) and all(a[0]<=b[0] for a,b in zip(history,history[1:])),'job_history_shape')
        authenticated=[]
        for anchor in fields(obs,'legacy_anchor'):
            if anchor['processed_ns']>j['freeze_ns']:continue
            a=anchor['applied']
            for channel in (0,1):
                side='left' if channel==0 else 'right'
                authenticated.append((a[side+'_sim_time_ns'],channel,a['final_n'][channel]))
        authenticated=authenticated[-cfg['history_capacity']:]
        need(safe.equal([list(x) for x in history],[list(x) for x in authenticated]),'job_history_authenticated_whole_prefix',job=j['job_id'])
        target=p['clock_sim_ns']+j['target_ns']-p['clock_receive_ns'];need(target==j['target_sim_ns'] and j['assumed_rtf']==1.0,'target_sim_mapping')
        expected_state=propagate(frozen,j['odom_stamp_ns'],target,j['anchor_n'],history,cfg['hydro'])
        error=max(abs(a-b) for a,b in zip(j['target_state'],expected_state))
        need(error<=1e-9,'independent_nominal_RK4',job=j['job_id'],max_error=error)
        jobproof.append({'job_id':j['job_id'],'max_nominal_error':error,'path_sequence':p['path_sequence'],'profile_sequence':p['profile_sequence'],'odom_sequence':p['odom_sequence'],'r_from_imu':p['r_from_imu'],'passed':before==len(issues)})
    need(bool(jobproof),'numerics_empty_job_population')
    groups['immutable_job_reference_and_nominal']={'passed':len(issues)==start,'jobs':len(jobproof),'proofs':jobproof,'nominal_hash_formula_rebuilt':False,'dynamic_plant_proven':False}
    return {'schema':'p1-source-components-v4','run_id':inp['run_id'],'passed':not issues,'groups':groups,'issues':issues,
        'input_sha256':s['hashes'],'strict_full_chain':False,'shared_v2_identity':False,'D1':False,'B4':False,'B5':False,'M0b':False,'M4':False,'F6':False,'P1':False,'execute':False,'true_master_clock':False,
        'limits':['fixed valid-callback positive scope','full sensor delivery and DDS packet freshness unproven','typed reserialization not original wire padding','nominal hash formula and general JSON float formatter unqualified','no old strict gate inheritance','no full dynamic/mixed/turn/pressure/recovery qualification']}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    try:
        s=load(a.run);report=analyze(s)
        after={p:sha(s['safe'].read_regular(Path(a.run)/p)) for p in s['paths']}
        if after!=s['hashes']:report['issues'].append({'code':'input_changed_during_read'});report['passed']=False
        report['inputs_unchanged']=after==s['hashes']
    except Exception as e:report={'schema':'p1-source-components-v4','passed':False,'issues':[{'code':'bounded_input_or_checker_error','detail':type(e).__name__+': '+str(e)}],'strict_full_chain':False,'D1':False,'execute':False}
    with Path(a.output).open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'passed':report['passed'],'issues':report['issues'][:15]}));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
