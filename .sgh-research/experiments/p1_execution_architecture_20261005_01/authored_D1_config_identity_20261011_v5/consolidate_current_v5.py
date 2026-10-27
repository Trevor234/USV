#!/usr/bin/python3
"""One offline current component report; enumerated missing strict gates remain false."""
from pathlib import Path
import argparse,hashlib,importlib,json,sys
sys.dont_write_bytecode=True
N=Path(__file__).resolve().parent
D=Path('/home/trevor/MPC/scheme_A_config_identity_20261011_04')
sys.path[:0]=[str(N),str(N/'runtime')]
if hashlib.sha256((N/'check_config_identity_v1.py').read_bytes()).hexdigest()!='d981ba6a2cc4ad3ac85376d59f684e88fc57523b24a814d2c292328f192ae8d3':
    raise ValueError('config identity implementation pin differs')
import check_config_identity_v1 as identity
CURRENT_SHA='9fb79aa88282e111894af1b50c658f33a76b9816865a5014ccb5ab0afbb288c9'
FORMATTER_SHA='cfa8a09a5b1c638aefa9b3acb11c10eb4233d711b386cf9769d5068875b3442c'
RULE_MAP_SHA='6c47463c0413ce1a78f42bc00f12d024ef5d5e77c0c623f9c561aee28605c96a'

def imports():
    c,_,safe=identity.imports()
    raw=safe.read_regular(D/'preregister/current_components_contract_v5.json')
    if identity.sha(raw)!=CURRENT_SHA:raise ValueError('current contract pin differs')
    current=safe.strict_json(raw)
    raw=safe.read_regular(D/'preregister/current_rule_map_v1.json')
    if identity.sha(raw)!=RULE_MAP_SHA:raise ValueError('current rule map pin differs')
    rule=safe.strict_json(raw)
    pin=rule['current_legacy_adapter']
    if identity.sha(safe.read_regular(pin['path']))!=pin['sha256']:raise ValueError('legacy adapter changed')
    import validate_current_legacy_rules_v5 as legacy
    if Path(legacy.__file__).resolve()!=Path(pin['path']).resolve():raise ValueError('wrong adapter path')
    raw=safe.read_regular(D/'preregister/formatter_corpus_contract_v1.json')
    if identity.sha(raw)!=FORMATTER_SHA:raise ValueError('formatter corpus pin differs')
    return current,rule,safe,legacy,safe.strict_json(raw)

def analyze(negative_copy=None):
    contract,rule,safe,legacy,fc=imports()
    snapshot=legacy.load_snapshot(contract,negative_copy=negative_copy)
    historical=legacy.validate_snapshot(snapshot,contract)
    source_data=identity.load_data(negative_copy)
    source=source_data['source'].analyze(source_data['typed'])
    config=identity.analyze(source_data,fc)
    components={}
    for prefix,report,key in [('legacy',historical,'components'),('source',source,'groups'),('identity',config,'components')]:
        for name,g in report[key].items():components[prefix+'/'+name]=g
    r=snapshot['records'];ack=source_data['records']['close_tail_ack'];issues=[]
    def need(ok,code,**detail):
        if not ok:issues.append({'code':code,**detail})
    terminal=r['publisher_session'];n=terminal['streams']['applied']['last_sequence'];graph=r['preparation']
    need(ack['schema']=='p1-owned-terminal-tail-ack-v1','tail_ack_schema')
    need(ack['run_id']==contract['expected']['run_id'] and ack['stage_qualified'] is False,'tail_ack_identity_or_qualification')
    need(ack['publisher_session_sha256']==snapshot['hashes']['publisher_session'],'tail_ack_publisher_session_identity')
    need(ack['publisher_last_applied_sequence']==ack['observer_last_applied_sequence']==ack['complete_observer_anchor_count']==n,'tail_ack_entire_Applied_population')
    topics=['/research/control/applied',*contract['expected']['physical_topics']]
    need(set(ack['expected_counts'])==set(topics) and safe.equal(ack['expected_counts'],ack['transport_counts']) and all(ack['transport_counts'][t]==snapshot['storage']['actual_counts'][t]==n for t in topics),'tail_ack_entire_declared_output_population')
    need(ack['receiver_roles_alive'] is True,'tail_ack_receiver_alive_population')
    try:
        driver=ack['driver_identity'];spawns=legacy.rows_of(r['ledger'],'spawn')
        need(all(driver['pid']==x['identity']['ppid'] and driver['boot_id']==x['boot_id'] and 0<driver['start_ticks']<=x['identity']['start_ticks'] for x in spawns),'tail_ack_driver_identity')
        need(driver['argv']==['/usr/bin/python3',r['run_inputs']['contract'].rsplit('/authored_v13_resource_20261007/',1)[0]+'/authored_D1_strict_source_20261011_v4/prepare_fixture.py','--run-id',contract['expected']['run_id'],'--domain',str(r['run_inputs']['domain']),'--mode','positive'],'tail_ack_driver_argv_binding')
        need(ack['driver_sha256']==r['run_inputs']['tool_sha256']['prepare_fixture.py'],'tail_ack_driver_binary_source_identity')
        close_signals=legacy.rows_of(r['ledger'],'signal')
        pub_stop=next(x['monotonic_ns'] for x in close_signals if x['name']=='publisher')
        observer_stop=next(x['monotonic_ns'] for x in close_signals if x['name']=='observer')
        need(pub_stop<=ack['checked_ns']<=observer_stop,'tail_ack_actual_close_order')
    except (KeyError,StopIteration,TypeError) as e:need(False,'tail_ack_schema_error',error=type(e).__name__)
    components['current/native_tail_delivery']={'passed':not issues,'issues':issues,'Applied':n,'whole_run_population':True,'ack_topic_scope':topics,'all18_topics_acknowledged':False}
    unchanged=legacy.rehash_snapshot(snapshot)==snapshot['hashes'] and all(identity.sha(safe.read_regular(path))==source_data['hashes'][key] for key,path in source_data['paths'].items())
    passed=all(g['passed'] for g in components.values()) and historical['component_suite_passed'] and source['passed'] and config['passed'] and unchanged
    return {'schema':'p1-current-consolidated-components-v5','run_id':contract['expected']['run_id'],'component_suite_passed':passed,
        'original_inputs_unchanged':unchanged,'original_authenticity_qualified':negative_copy is None,'negative_copy':str(negative_copy) if negative_copy else None,
        'components':components,'component_count':len(components),'storage':snapshot['storage'],
        'source_component_issues':source['issues'],
        'source_report_qualification_flags_preserved':{k:source[k] for k in ['strict_full_chain','D1','execute']},
        'nominal_hash_identity_formula_component_passed':config['components']['independent_nominal_byte_preimage']['passed'],
        'missing_strict_gates':rule['unclosed_strict_gates'],
        'strict_readiness_passed':False,'all_original_execution_rules_qualified':False,'shared_v2_identity_recovered':False,
        'strict_full_chain':False,'D1':False,'B4':False,'B5':False,'M0b':False,'M4':False,'F6':False,'P1':False,'execute':False,'true_master_clock':False,
        'general_float_formatter_qualified':False,'live_process_reauthentication':False,'DDS_graph_empty_proven':False,
        'scope':'One complete original v4 whole-run offline component report; no subwindow, no inherited stage or unavailable tool identity',
        'historical_input_sha256':snapshot['hashes'],'identity_input_sha256':source_data['hashes']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    _,_,safe,_,_=imports()
    try:report=analyze()
    except Exception as e:report={'schema':'p1-current-consolidated-components-v5','component_suite_passed':False,'load_error':type(e).__name__+': '+str(e),'strict_readiness_passed':False,'D1':False,'execute':False}
    safe.create_only(a.output,report)
    print(json.dumps({'component_suite_passed':report['component_suite_passed'],'strict_readiness_passed':False,
        'load_error':report.get('load_error'),'issues':[{**i,'component':name} for name,g in report.get('components',{}).items() for i in g.get('issues',[])][:20]}))
    return 0 if report['component_suite_passed'] else 1
if __name__=='__main__':raise SystemExit(main())
