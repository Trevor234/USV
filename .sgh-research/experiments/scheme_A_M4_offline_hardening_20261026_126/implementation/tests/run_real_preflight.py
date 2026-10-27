"""Exercise actual Driver.main -> complete preflight; no live role can be spawned."""
import copy,importlib.util,json,os,shutil,subprocess,sys
from pathlib import Path
from unittest.mock import patch
from offline_support import Evidence,ROOT,pin,save
sys.path[:0]=[str(ROOT/'implementation/author'),str(ROOT/'implementation/audit')]
import t2_rnw_admission_rules as rules
import rnw_admission_v2 as freeze
import t2b_gen_admission as entry
e=Evidence('E03',sys.argv[1]);old=ROOT.parent/'scheme_A_M4_rnw_s4_owned_20261025_119/implementation'
registrations=[]
for p in old.glob('*.json'):
 d=json.loads(p.read_text())
 if d.get('schema')==entry.REGISTRATION_SCHEMA and d.get('case')==rules.FAMILY:registrations.append((p,d))
assert len(registrations)==1,registrations
original_path,original=registrations[0];source_table=json.loads(Path(original['action_table']).read_text())
cases={
 'ENTRY2-LEGAL':(lambda t:None,None),
 'ENTRY2-CLAUSES-FALSE':(lambda t:t['clauses'].update({k:False for k in t['clauses']}),'clause_value:'),
 'ENTRY2-MISSING-HOLD':(lambda t:t['actions'].pop(0),'missing_hold'),
 'ENTRY2-RESUME-FIRST':(lambda t:t['actions'].reverse(),'resume_before_hold'),
 'ENTRY2-DUP-ID':(lambda t:t['actions'][1].__setitem__('id',t['actions'][0]['id']),'duplicate_action_id'),
 'ENTRY2-ID-TYPE':(lambda t:t['actions'][0].__setitem__('id',0),'action_id_domain'),
 'ENTRY2-FLOAT-DELAY':(lambda t:t['actions'][0]['trigger'].__setitem__('delay_ms',1200.0),'trigger_domain:'),
 'ENTRY2-TRIGGER-SHAPE':(lambda t:t['actions'][0].__setitem__('trigger',[]),'action_parameters_or_trigger_shape'),
 'ENTRY2-UNKNOWN':(lambda t:t['actions'][0].__setitem__('action','clock_warp'),'unregistered_action:'),
 'ENTRY2-CLAUSE-TYPE':(lambda t:t['clauses'].__setitem__('pause_confirm_ns',True),'clause_value:'),
 'ENTRY2-UNKNOWN-FIELD':(lambda t:t.__setitem__('extra',1),'table_exact_fields'),
}
save(e.out/'registration.json',{'cases':{k:v[1]for k,v in cases.items()},'valid_frozen_identity_source':str(original_path),
 'driver_main':str(ROOT/'implementation/author/t2b_gen_driver_v1.py'),'stop_point':'after real preflight returns, before Driver creates its run output',
 'fixture_registry_only':True,'live_owned_source_qualified':False,'automatic_retries':0})
e.check('freeze_and_Driver_same_physical_rule_function',freeze.validate_table is rules.validate_table and entry._hardened_rules() is rules)
class PreflightReturned(Exception):pass
proof=[]
for name,(mutate,expected)in cases.items():
 private=e.out/'fixtures'/name;author=private/'author';author.mkdir(parents=True);(private/'runs').mkdir()
 driver=author/'t2b_gen_driver_v1.py';shutil.copy2(ROOT/'implementation/author/t2b_gen_driver_v1.py',driver)
 table=copy.deepcopy(source_table);mutate(table);tp=private/'table.json';save(tp,table)
 registry=json.loads(Path(original['registry']).read_text());registry['driver']=str(driver);registry['driver_tool_sha256']=pin(driver)['sha256']
 rp=private/'registry.json';save(rp,registry)
 reg={**original,'action_table':str(tp),'action_table_sha256':pin(tp)['sha256'],
      'registry':str(rp),'registry_sha256':pin(rp)['sha256'],'output':str(private/'runs/never_started')}
 regpath=private/'registration.json';save(regpath,reg)
 calls={'Popen':0,'real_preflight':0,'returned':0};reason=None;parser_error=None
 spec=importlib.util.spec_from_file_location('test_driver_'+name.replace('-','_'),driver);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 real=entry.registration_preflight_t2bgen
 def observe(*args,**kwargs):
  calls['real_preflight']+=1
  real(*args,**kwargs);calls['returned']+=1;raise PreflightReturned()
 def no_spawn(*args,**kwargs):calls['Popen']+=1;raise AssertionError('unexpected spawn')
 env={'ROS_DOMAIN_ID':'120','ROS_LOCALHOST_ONLY':'1','RMW_IMPLEMENTATION':'rmw_fastrtps_cpp'}
 with patch.object(entry,'registration_preflight_t2bgen',observe),patch.object(subprocess,'Popen',no_spawn),patch.object(sys,'argv',[str(driver),'--registration',str(regpath)]),patch.dict(os.environ,env):
  try:module.main()
  except PreflightReturned:reason='legal_preflight_returned'
  except AssertionError as exc:reason=str(exc)
  except Exception as exc:parser_error=type(exc).__name__+':'+str(exc)
 pure=freeze.validate_table(table,{'run_id':reg['run_id'],'contract_sha256':reg['contract_sha256']})
 ok=calls['real_preflight']==1 and calls['Popen']==0 and parser_error is None and not Path(reg['output']).exists()
 entry_reason = 'table exact fields' if name == 'ENTRY2-UNKNOWN-FIELD' else expected
 ok=ok and ((calls['returned']==1 and reason=='legal_preflight_returned'and pure==[])if expected is None else(calls['returned']==0 and entry_reason in (reason or '')and any(x.startswith(expected)for x in pure)))
 row={'case':name,'calls':calls,'actual_main_rejection':reason,'unexpected_parser_error':parser_error,'freeze_rejections':pure}
 proof.append(row);e.check(name,ok,row)
save(e.out/'real_entry_proof.json',proof)
result=e.finish(rule_module_identity=rules.module_identity(),actual_Driver_main_calls=len(cases),max_Popen_calls=max(p['calls']['Popen']for p in proof),
 actual_full_preflight_positive='existing frozen assets as identity fixture only; no new executable identity registration or owned run')
sys.exit(0 if result['status']=='PASS'else 2)
