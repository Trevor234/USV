from pathlib import Path
import hashlib,json,sys,os,time,traceback,signal
E=Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01');A=E/'authored_B2_C0_tools_20261008_v2';R=A/'runtime';G=E/'B1_complete_closed_assets_20261008.json';P=A/'C0_predeclared_policy.json'
sys.path.insert(0,str(R))
from run_worker_fault_matrix import verify_assets
from run_r5_diag_validation import host_preflight
from owned_process_supervisor import Supervisor
from check_C0_gates import combine
from cleanup_C0_inner import recover
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(P)=='73fcbd91591b10bd3dbbee541be637ffb407249b9716bba5fd130f7dfa7e1a43'
policy=json.loads(P.read_text());D=E/policy['run_id'];assert not D.exists()
tools=json.loads((A/'tool_tests_result.json').read_text());assert tools['passed'] is True and tools['tests_discovered']==88
assert tools['live_recovery_tests']['passed'] is True and tools['live_recovery_tests']['count']==2 and sha(A/'live_inner_recovery_results.json')==tools['live_recovery_report_sha256']
def verify_tools():
    assert len(tools['files'])==55
    for n,item in tools['files'].items():assert sha(R/n)==item['sha256'],n
    for n,item in policy['new_tool_files'].items():assert tools['files'][n]['sha256']==item['sha256'],n
    for n,item in tools['extra_files'].items():assert sha(A/n)==item['sha256'],n
def verify_previous_tools():
    old=E/'authored_B2_C0_tools_20261008';receipt=old/'tool_tests_result.json'
    assert sha(receipt)==policy['previous_tool_deployment']['result_sha256']
    previous=json.loads(receipt.read_text())
    for n,item in previous['files'].items():assert sha(old/'runtime'/n)==item['sha256'],('previous runtime',n)
    for n,item in previous['extra_files'].items():assert sha(old/n)==item['sha256'],('previous extra',n)
    assert sha(old/'new_tool_tests.log')==previous['log_sha256']
verify_previous_tools();verify_tools()
guard_before=verify_assets(G);host_before=host_preflight();assert host_before['boot_id']==policy['pins']['boot_id']
S=A/'C0_driver_supervision';assert not S.exists();S.mkdir();sup=Supervisor(S)
steps=[];failure=None;combined=None;rcs={};inputs={};asset_after=None;host_after=None;final_inner=[]
env={**os.environ,'PYTHONPATH':str(R)+':'+os.environ.get('PYTHONPATH','')}
def recover_inner(item):
    def durable_event(kind,**details):
        sup.event(kind,**details)
        return not sup.evidence_failed
    try:
        return recover(D/'owned_process_ledger.jsonl',policy['recovery_expected_roles'],policy['pins']['boot_id'],runner_pid=item.process.pid,event=durable_event)
    except BaseException as error:
        durable_event('inner_recovery_exception',runner_pid=item.process.pid,error=repr(error))
        return {'cleanup_complete':False,'error':repr(error),'remaining_members':'unknown'}
def call(name,args,timeout=120):
    py=Path('/usr/bin/python3').resolve();assert str(py)==policy['recovery_expected_roles']['fixture']['exe'] and sha(py)==policy['recovery_expected_roles']['fixture']['sha256'];item=sup.spawn(name,[str(py),'-B',*args],env,py,sha(py))
    deadline=time.monotonic()+timeout
    while item.process.poll() is None and time.monotonic()<deadline:time.sleep(.1)
    timed_out=item.process.poll() is None;inner=None
    if name=='runner':
        if timed_out:
            sup.send(item,signal.SIGINT)
            sup.wait_empty(item,20)  # finite allowance for the inner finally
        inner=recover_inner(item)
    cleanup=sup.stop(item,.5,1,1)
    if name=='runner' and inner.get('cleanup_complete') is not True:
        # Recheck after parent exit; an unreaped child remains a failure until its
        # authorized group has actually disappeared. Never mask the first result.
        inner_after=recover_inner(item)
        inner={'cleanup_complete':inner_after.get('cleanup_complete') is True,'first_attempt':inner,'after_runner_exit':inner_after}
    
    row={'name':name,'returncode':cleanup['returncode'],'timed_out':timed_out,'cleanup':cleanup,'inner_owned_cleanup':inner,'console_sha256':sha(S/(name+'.console.log'))};steps.append(row)
    if timed_out or not cleanup['cleanup_complete'] or (name=='runner' and inner.get('cleanup_complete') is not True):raise RuntimeError('owned driver timeout/inner/outer cleanup: '+name)
    return row['returncode']
try:
    pins=policy['pins'];paths=policy['paths']
    for key,path in (('regulator_binary_sha256',paths['diagnostic_bin']),('worker_binary_sha256',paths['worker_bin']),('diagnostic_source_sha256',paths['diagnostic_source']),('contract_sha256',paths['contract'])):assert sha(path)==pins[key],key
    args=[str(R/'run_r5_diag_validation.py'),'--contract',paths['contract'],'--contract-hash',pins['contract_sha256'],'--experiment-root',str(E),'--workspace','/home/trevor/USV/usv_mpc_ws','--run-id',policy['run_id'],'--duration','10','--worker-sha256',pins['worker_binary_sha256'],'--regulator-sha256',pins['regulator_binary_sha256'],'--diagnostic-bin',paths['diagnostic_bin'],'--diagnostic-source',paths['diagnostic_source'],'--diagnostic-source-sha256',pins['diagnostic_source_sha256'],'--witness-enabled','--witness-file','fixed_witness.json','--test-sink-pause-ms','0']
    rcs['runner']=call('runner',args)
    if not (D/'normal_source_check/contract_report.json').exists():raise RuntimeError('strict source report missing')
    base_path=D/'normal_source_check/contract_report.json';base=json.loads(base_path.read_text());rcs['base']=json.loads((D/'postrun_checks.json').read_text())['normal_source_check']['checker_returncode']
    rcs['delivery']=call('delivery',[str(R/'check_resource_delivery.py'),str(D),'--base-report',str(base_path),'--output',str(D/'verification_C0_resource_delivery')],30)
    rcs['comparison']=call('comparison',[str(R/'check_p1_C0_comparison.py'),'--context',str(D/'run_context.json'),'--source',str(D/'regulator_source.jsonl'),'--witness',str(D/'fixed_witness.json'),'--expected-header',str(D/'witness_expected_header.json'),'--output',str(D/'verification_C0_source_witness.json')],30)
    names={'context':D/'run_context.json','summary':D/'runner_summary.json','postrun':D/'postrun_checks.json','base':base_path,'delivery':D/'verification_C0_resource_delivery/resource_delivery_check.json','comparison':D/'verification_C0_source_witness.json'}
    inputs={k:{'path':str(p),'sha256':sha(p)} for k,p in names.items()};reports={k:json.loads(p.read_text()) for k,p in names.items()}
    hashes={path:sha(path) for path in reports['base']['input_sha256_before']}
    required=[str(Path(paths['contract']).resolve()),*[str(D/n) for n in ('run_context.json','regulator_source.jsonl','worker_source.jsonl','fixture_source.jsonl','owned_process_ledger.jsonl','runner_summary.json','regulator.console.log','worker.console.log','raw_bag/metadata.yaml')]]
    artifact_hashes={'base_report_sha256':inputs['base']['sha256'],'witness_report_sha256':sha(D/'witness_check.json'),'expected_header_sha256':sha(D/'witness_expected_header.json'),'witness_sha256':sha(D/'fixed_witness.json')}
    # Recheck each independently pinned artifact inventory after all readers.
    for k in ('delivery','comparison'):
        for path,h in reports[k].get('evidence_sha256',{}).items():assert sha(path)==h,(k,path)
    comp=reports['comparison'];assert comp['raw_inputs_unchanged'] is True and comp['input_sha256_before'] and comp['input_sha256_before']==comp['input_sha256_after']
    for path,h in comp['input_sha256_before'].items():assert sha(path)==h,('comparison raw',path)
    for path,h in reports['postrun']['fixed_witness_check'].get('evidence_sha256',{}).items():assert sha(path)==h,('audit',path)
    for k,p in names.items():assert sha(p)==inputs[k]['sha256']
    verify_previous_tools();verify_tools();asset_after=verify_assets(G);host_after=host_preflight()
    combined=combine(**reports,policy=policy,required_paths=required,actual_hashes=hashes,artifact_hashes=artifact_hashes,returncodes=rcs,assets_unchanged=not guard_before['drift'] and not asset_after['drift'],host_clean=host_after['existing_controller_gazebo_count']==0 and host_after['unreadable_cmdline_count']==0)
    combined['inputs']=inputs;combined['policy_sha256']=sha(P);combined['actual_returncodes']=rcs
    with (D/'verification_C0_combined_gates.json').open('x') as f:json.dump(combined,f,indent=2)
    if not combined['passed']:raise RuntimeError('C0 gate failed: '+','.join(combined['issues']))
except BaseException as e:failure=repr(e);traceback.print_exc(file=sys.stderr)
finally:
    for item in sup.owned.values():
        if item.cleanup is None:
            if item.name=='runner':final_inner.append(recover_inner(item))
            sup.stop(item,.5,1,1)
        if item.name=='runner':final_inner.append(recover_inner(item))
    if not final_inner or final_inner[-1].get('cleanup_complete') is not True:failure=failure or 'final inner owned cleanup unknown/incomplete'
    sup.close()
    try:verify_previous_tools();verify_tools();asset_after=verify_assets(G);host_after=host_preflight()
    except Exception as e:failure=failure or repr(e)
result={'schema':'p1-C0-run-result-v1','run_id':policy['run_id'],'run_directory':str(D),'policy_sha256':sha(P),'failure':failure,'steps':steps,'actual_returncodes':rcs,'combined':combined,'inputs':inputs,'guard_before':guard_before,'guard_after':asset_after,'host_before':host_before,'host_after':host_after,'outer_supervision_evidence_complete':not sup.evidence_failed,'outer_cleanup_complete':not sup.cleanup_failed,'final_inner_recovery':final_inner,'inner_owned_cleanup_complete':all(v.get('inner_owned_cleanup',{}).get('cleanup_complete') is True for v in steps if v['name']=='runner') and any(v['name']=='runner' for v in steps) and bool(final_inner) and final_inner[-1].get('cleanup_complete') is True,'C0_complete':failure is None and combined is not None and combined['passed'] and not sup.cleanup_failed and not sup.evidence_failed,'R5_run':False,'R5_complete':False,'M0b_formally_complete':False,'M4_complete':False,'F6_complete':False,'P1_complete':False,'execute_qualified':False,'physical_execute_release_enabled':False}
with (A/'C0_run_result.json').open('x') as f:json.dump(result,f,indent=2)
print(json.dumps(result))
