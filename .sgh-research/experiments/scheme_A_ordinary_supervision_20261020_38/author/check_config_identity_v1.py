#!/usr/bin/python3
"""Independent bounded byte-preimage and recorded nominal/fingerprint component checks."""
import argparse,copy,hashlib,importlib,math,struct,sys
from decimal import Decimal
from pathlib import Path
import json
sys.dont_write_bytecode=True
N=Path(__file__).resolve().parent
D=Path('/home/trevor/MPC/scheme_A_config_identity_20261011_04')
CONTRACT_SHA='1e10fc45fbed4c339a95b20542ab12138648d31fc926a625f06cd54d58583cf1'
sha=lambda b:hashlib.sha256(b).hexdigest()
bits=lambda x:struct.pack('>d',x).hex()
def imports():
    raw=(D/'preregister/config_identity_contract_v1.json').read_bytes()
    if sha(raw)!=CONTRACT_SHA:raise ValueError('identity contract changed')
    c=json.loads(raw)
    for pin in list(c['sealed_helpers'].values())+list(c['source_pins'].values()):
        if sha(Path(pin['path']).read_bytes())!=pin['sha256']:raise ValueError('helper/source pin changed: '+pin['path'])
    sys.path[:0]=[str(N),str(N/'runtime')]
    import check_source_components_v4 as source
    import validate_readiness_v3 as safe
    for mod,key in [(source,'check_source_components_v4.py'),(safe,'validate_readiness_v3.py')]:
        if Path(mod.__file__).resolve()!=Path(c['sealed_helpers'][key]['path']).resolve():raise ValueError('wrong helper path')
    return c,source,safe

def load_data(negative_copy=None):
    c,source,safe=imports();root=Path(negative_copy or c['original_run']);base=Path(c['original_run'])
    records={};paths={};hashes={}
    for key,pin in c['record_files'].items():
        original=Path(pin['path'])
        path=root/original.relative_to(base) if negative_copy and original.is_relative_to(base) else root/'external'/key if negative_copy else original
        raw=safe.read_regular(path)
        if not negative_copy and sha(raw)!=pin['sha256']:raise ValueError('record pin changed: '+key)
        paths[key]=path;hashes[key]=sha(raw)
        records[key]=safe.jsonl(raw) if original.suffix=='.jsonl' else safe.strict_json(raw)
    if sum(p.stat().st_size for p in paths.values())>128*1024*1024:raise ValueError('record budget')
    s=source.load(root)
    return {'contract':c,'source':source,'safe':safe,'records':records,'paths':paths,'hashes':hashes,'typed':s,
            'negative_copy':str(negative_copy) if negative_copy else None}

class IdentityError(ValueError):pass
def exact_number(x):
    if type(x) not in (int,float) or not math.isfinite(x):raise IdentityError('nominal_source_numeric_type')
    return float(x)
def nominal_preimage(document,contract):
    if set(document)!={'/**'} or set(document['/**'])!={'ros__parameters'}:raise IdentityError('nominal_source_mapping')
    params=document['/**']['ros__parameters']
    if set(params)!={'vehicle','thruster'}:raise IdentityError('nominal_source_mapping')
    expected=set(contract['preimage']['vehicle_keys']);v=params['vehicle'];t=params['thruster']
    if type(v) is not dict or set(v)!=expected:raise IdentityError('nominal_vehicle_field_set')
    if type(t) is not dict or set(t)!=set(contract['preimage']['thruster_keys']):raise IdentityError('nominal_thruster_field_set')
    v={k:exact_number(x) for k,x in v.items()};t={k:exact_number(x) for k,x in t.items()}
    a=v['mass']-v['Xu_dot'];b=v['mass']-v['Yv_dot'];e=v['Iz']-v['Nr_dot']
    cross1=v['mass']*v['xg']-v['Yr_dot'];cross2=v['mass']*v['xg']-v['Nv_dot']
    if any(v[k]<=0 for k in ('mass','Iz','d_thruster')) or min(a,b,e,b*e-cross1*cross2)<=0 or min(t.values())<=0:
        raise IdentityError('nominal_inertia_or_limits')
    q={'/**':{'ros__parameters':{'vehicle':v,'thruster':t}}}
    raw=(json.dumps(q,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    return raw,v,t

def parameter_digest(parameters):
    out={}
    def scalar(kind,value):
        if kind==0:return value is None
        if kind==1:return type(value) is bool
        if kind==2:return type(value) is int and -(1<<63)<=value<(1<<63)
        if kind==3:return type(value) is float and math.isfinite(value)
        if kind==4:return type(value) is str
        return False
    for name,row in parameters.items():
        if type(row) is not dict or set(row)!={'type','value','canonical_value'}:raise IdentityError('actual_parameter_row_shape')
        kind=row['type'];value=row['value']
        if type(kind) is not int or not 0<=kind<=9:raise IdentityError('actual_parameter_exact_type')
        if kind<5:
            valid=scalar(kind,value)
        else:
            valid=type(value) is list and all((type(x) is int and 0<=x<=255) if kind==5 else scalar({6:1,7:2,8:3,9:4}[kind],x) for x in value)
        if not valid:raise IdentityError('actual_parameter_exact_type')
        canonical=bits(value) if kind==3 else [bits(x) for x in value] if kind==8 else value
        if row['canonical_value']!=canonical:raise IdentityError('actual_parameter_canonical')
        out[name]={'type':kind,'canonical_value':canonical}
    return sha(json.dumps(out,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode())

def native_number(x):
    """Independent digit generation; qualified only for frozen differential-tested IEEE corpus."""
    if type(x) is not float or not math.isfinite(x):raise IdentityError('fingerprint_float_type')
    sign='-' if math.copysign(1.0,x)<0 else ''
    if x==0:return sign+'0.0'
    decimal=Decimal(repr(abs(x))).as_tuple();digits=''.join(str(x) for x in decimal.digits);exp=decimal.exponent
    while len(digits)>1 and digits.endswith('0'):digits=digits[:-1];exp+=1
    k=len(digits);n=k+exp
    if k<=n<=15:body=digits+'0'*(n-k)+'.0'
    elif 0<n<=15:body=digits[:n]+'.'+digits[n:]
    elif -4<n<=0:body='0.'+'0'*(-n)+digits
    else:
        exponent=n-1;body=digits[0]+('.'+digits[1:] if k>1 else '')+'e'+('+' if exponent>=0 else '-')+str(abs(exponent)).zfill(2)
    return sign+body
def cpp_json(x,allowed):
    if type(x) is float:
        if bits(x) not in allowed:raise IdentityError('unqualified_float_bits')
        return native_number(x)
    if type(x) is list:return '['+','.join(cpp_json(v,allowed) for v in x)+']'
    if type(x) is dict:return '{'+','.join(json.dumps(k,ensure_ascii=False)+':'+cpp_json(x[k],allowed) for k in sorted(x))+'}'
    if type(x) is str:
        if not x.isascii():raise IdentityError('unqualified_string_domain')
        return json.dumps(x,ensure_ascii=False,separators=(',',':'))
    if type(x) in (bool,int) or x is None:return json.dumps(x,separators=(',',':'))
    raise IdentityError('fingerprint_unknown_type')
def reference_payloads(s):
    result=[]
    for row in s['records']['observer_source']:
        if row['type'] not in ('path_version','profile_version'):continue
        raw=row['raw_input'];blob=bytes.fromhex(raw['cdr_hex'])
        if sha(blob)!=raw['cdr_sha256'] or len(blob)!=raw['cdr_bytes']:raise IdentityError('fingerprint_raw_cdr_identity')
        msg=s['typed']['decode'](blob,raw['message_type'])
        if row['type']=='path_version':
            if msg['header']['frame_id']!='map':raise IdentityError('unqualified_string_domain')
            points=[]
            for pose in msg['poses']:
                q=pose['pose']['orientation'];yaw=math.atan2(2*(q['w']*q['z']+q['x']*q['y']),1-2*(q['y']**2+q['z']**2))
                points.append([float(pose['pose']['position']['x']),float(pose['pose']['position']['y']),yaw])
            value={'frame':msg['header']['frame_id'],'path':points}
        else:
            value=[[float(x) for x in msg['data'][i:i+4]] for i in range(0,len(msg['data']),4)]
        result.append({'source_type':row['type'],'sequence':row['received_sequence'],'payload':value,'source_fingerprint':row['fingerprint']})
    return result

def analyze(s,formatter_contract=None):
    c=s['contract'];r=s['records'];components={}
    def group(name,fn):
        issues=[]
        def need(ok,code,**detail):
            if not ok:issues.append({'code':code,**detail})
        try:detail=fn(need)
        except (ValueError,KeyError,TypeError,OverflowError,IndexError) as error:
            issues.append({'code':str(error) if isinstance(error,IdentityError) else 'identity_schema_error','error_class':type(error).__name__});detail={}
        components[name]={'passed':not issues,'issues':issues,**(detail or {})}
    reconstructed={}
    def preimage(need):
        raw,v,t=nominal_preimage(r['nominal_source'],c);fraw,fv,ft=nominal_preimage(r['nominal_f5_source'],c)
        digest=sha(raw);reconstructed.update(raw=raw,vehicle=v,thruster=t,hash=digest)
        need(raw==fraw,'nominal_current_F5_preimage_differs')
        need(digest==r['contract']['nominal_hash'],'nominal_byte_identity')
        need(digest==r['f5_parameters']['f5_actual_parameters']['research_nominal_config_hash'],'F5_effective_nominal_identity')
        return {'canonical_bytes':len(raw),'canonical_sha256':digest,'nominal_projection':'none','hash_covers_weights_or_reference':False,
                'raw_source_sha256':s['hashes']['nominal_source'],'raw_source_equals_canonical':s['paths']['nominal_source'].read_bytes()==raw}
    group('independent_nominal_byte_preimage',preimage)
    def actual(need):
        v=reconstructed['vehicle'];t=reconstructed['thruster'];cfg=r['contract'];pub=r['owned_publisher']['effective_parameters'];live=r['live_publisher']
        for role in ('publisher','worker','observer','synthetic_source'):
            owned=r['owned_'+role]
            need(parameter_digest(owned['effective_parameters'])==parameter_digest(r['live_'+role])==owned['effective_parameters_sha256'],'whole_actual_parameter_digest_binding',role=role)
        for key,value in v.items():
            name='vehicle.'+key
            for label,p in [('owned',pub),('live',live)]:
                actual=p[name];need(actual['type']==3 and type(actual['value']) is float and bits(actual['value'])==bits(value),'actual_vehicle_nominal_differs',surface=label,field=name)
                need(actual['canonical_value']==bits(float(actual['value'])),'actual_live_IEEE_canonical_differs',surface=label,field=name)
            need(bits(float(cfg['hydro'][key]))==bits(value),'contract_hydro_nominal_differs',field=key)
        wanted={'dynamic.T_max':t['T_max_forward'],'dynamic.T_min':-t['T_max_reverse'],'horizon':cfg['N'],'dynamic.dt':cfg['dt'],
                'mpc_dt':cfg['dt'],'dynamic.Q':cfg['Q'],'dynamic.R':cfg['R'],'dynamic.Rd':cfg['Rd'],'dynamic.Qf_scale':cfg['Qf_scale']}
        for key,value in wanted.items():
            for label,p in [('owned',pub),('live',live)]:need(s['safe'].equal(p[key]['value'],value),'solver_effective_contract_differs',surface=label,field=key)
        need(cfg['command_max_n']==t['T_max_forward'] and cfg['command_min_n']==-t['T_max_reverse'],'contract_nominal_bounds_differs')
        for role in ('worker','observer'):need(s['safe'].equal(r['owned_'+role]['contract_configuration'],cfg),'whole_effective_contract_differs',role=role)
        return {'vehicle_fields':19,'thruster_fields':2,'separate_solver_fields':len(wanted),'runtime_model_is_loaded_parameter_evidence':True,'plant_response_qualified':False}
    group('actual_nominal_model_and_separate_solver_binding',actual)
    def fanout(need):
        count={};digest=reconstructed['hash']
        def visit(q,label):
            if type(q) is dict:
                for k,v in q.items():
                    if k in ('nominal_hash','nominal_config_hash'):
                        count[label]=count.get(label,0)+1;need(type(v) is str and v==digest,'whole_nominal_fanout_differs',surface=label,field=k)
                    else:visit(v,label)
            elif type(q) is list:
                for v in q:visit(v,label)
        for key in ('contract','startup_manifest','owned_worker','owned_observer','worker_source','observer_source'):visit(r[key],key)
        for topic in ('/p1/solve_job','/p1/solve_candidate','/p1/worker_capability','/research/reference_prediction'):
            visit([x['message'] for x in s['typed']['decoded'][topic]],topic)
        for key in ('owned_publisher','live_publisher'):
            params=r[key]['effective_parameters'] if key.startswith('owned') else r[key]
            need(params['research_nominal_config_hash']['value']==digest,'publisher_nominal_hash_parameter_differs',surface=key)
        need(all(count.get(k,0)>0 for k in ('worker_source','observer_source','/p1/solve_job','/p1/solve_candidate','/p1/worker_capability','/research/reference_prediction')),'nominal_fanout_population_missing')
        return {'observed_claim_counts':count,'whole_stored_message_populations':True}
    group('whole_nominal_identity_fanout',fanout)
    if formatter_contract:
        def fingerprint(need):
            allowed=set(formatter_contract['allowed_ieee_bits']);values=reference_payloads(s);proofs=[]
            for item in values:
                text=cpp_json(item['payload'],allowed);digest=sha(text.encode())
                need(digest==item['source_fingerprint'],'independent_cpp_reference_fingerprint',source_type=item['source_type'],sequence=item['sequence'])
                proofs.append({'source_type':item['source_type'],'sequence':item['sequence'],'sha256':digest,'bytes':len(text.encode())})
            need(len(values)==26,'reference_callback_population_differs')
            return {'rows':len(values),'proofs':proofs,'qualified_IEEE_corpus':len(allowed),'general_formatter_qualified':False}
        group('bounded_cpp_reference_fingerprints',fingerprint)
    report={'schema':'p1-config-identity-components-v1','passed':all(g['passed'] for g in components.values()),'components':components,
       'scope':'Pinned original full v4 run, exact JSON nominal preimage and closed recorded fingerprint domain only',
       'negative_copy':s['negative_copy'],'original_authenticity_qualified':s['negative_copy'] is None,'input_sha256':s['hashes'],
       'nominal_hash_identity_formula_rebuilt':components['independent_nominal_byte_preimage']['passed'],
       'general_float_formatter_qualified':False,'general_JSON_YAML_config_qualified':False,
       'strict_full_chain':False,'D1':False,'B4':False,'B5':False,'M0b':False,'M4':False,'F6':False,'P1':False,'execute':False,'true_master_clock':False}
    if s['negative_copy'] is not None:report['nominal_hash_identity_formula_rebuilt']=False
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--formatter-contract',type=Path);p.add_argument('--formatter-sha');a=p.parse_args()
    s=load_data();fc=None
    if a.formatter_contract:
        raw=s['safe'].read_regular(a.formatter_contract)
        if not a.formatter_sha or sha(raw)!=a.formatter_sha:raise ValueError('formatter contract pin differs')
        fc=s['safe'].strict_json(raw)
    report=analyze(s,fc);after={k:sha(s['safe'].read_regular(p)) for k,p in s['paths'].items()}
    report['original_inputs_unchanged']=after==s['hashes'];report['passed']&=report['original_inputs_unchanged']
    s['safe'].create_only(a.output,report)
    print(json.dumps({'passed':report['passed'],'issues':[i for g in report['components'].values() for i in g['issues']][:15]}))
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
