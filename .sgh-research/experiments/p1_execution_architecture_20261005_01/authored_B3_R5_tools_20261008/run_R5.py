from pathlib import Path
import hashlib,json,sys,os,time,traceback,signal
E=Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01');A=E/'authored_B3_R5_tools_20261008';R=A/'runtime';G=E/'C0_closed_assets_20261008.json';P=A/'R5_predeclared_policy.json'
sys.path.insert(0,str(R))
from run_worker_fault_matrix import verify_assets
from run_R5_pressure import host_preflight
from owned_process_supervisor import Supervisor
from cleanup_C0_inner import recover
from check_R5_independent import combine
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(P)=='33670f3475b6467b9211fb034942fe6f058f1e11e5abe699ba8e6860cfded31a'
policy=json.loads(P.read_text());D=E/policy['run_id'];assert policy['status']=='frozen-before-run' and not D.exists()
tools=json.loads((A/'tool_tests_result.json').read_text());assert tools['passed'] is True and tools['tests_discovered']==123
def verify_tools():
    assert len(tools['files'])==61
    for n,item in tools['files'].items():assert sha(R/n)==item['sha256'],n
    for n,item in policy['new_tool_files'].items():assert tools['files'][n]['sha256']==item['sha256'],n
    for n,item in tools['extra_files'].items():assert sha(A/n)==item['sha256'],n
    assert sha(A/'new_tool_tests.log')==tools['log_sha256']
verify_tools();assert sha(G)==policy['previous_closed_asset_sha256']
guard_before=verify_assets(G);host_before=host_preflight();assert host_before['boot_id']==policy['pins']['boot_id']
assert len(guard_before.get('drift',[]))==0 and guard_before['count']==2521
with (A/'R5_GO_before_launch.json').open('x') as f:
    json.dump({'schema':'p1-R5-prelaunch-go-v1','decision':'GO','policy_sha256':sha(P),'tools_result_sha256':sha(A/'tool_tests_result.json'),
        'driver_sha256':sha(Path(__file__)),'guard':guard_before,'host':host_before,'monotonic_ns':time.monotonic_ns(),'scope':'single_finite_no_output_pressure','physical_execute':False},f,indent=2)
S=A/'R5_driver_supervision';assert not S.exists();S.mkdir();sup=Supervisor(S)
steps=[];failure=None;combined=None;rcs={};inputs={};asset_after=None;host_after=None;final_inner=[]
env={**os.environ,'PYTHONPATH':str(R)+':'+os.environ.get('PYTHONPATH','')}
def recover_inner(item):
    def durable_event(kind,**details):
        sup.event(kind,**details);return not sup.evidence_failed
    try:return recover(D/'owned_process_ledger.jsonl',policy['recovery_expected_roles'],policy['pins']['boot_id'],runner_pid=item.process.pid,event=durable_event)
    except BaseException as error:
        durable_event('inner_recovery_exception',runner_pid=item.process.pid,error=repr(error));return {'cleanup_complete':False,'error':repr(error),'remaining_members':'unknown'}
def call(name,args,timeout=120):
    py=Path('/usr/bin/python3').resolve();assert str(py)==policy['recovery_expected_roles']['fixture']['exe'] and sha(py)==policy['recovery_expected_roles']['fixture']['sha256']
    item=sup.spawn(name,[str(py),'-B',*args],env,py,sha(py));deadline=time.monotonic()+timeout
    while item.process.poll() is None and time.monotonic()<deadline:time.sleep(.1)
    timed_out=item.process.poll() is None;inner=None
    if name=='runner':
        if timed_out:sup.send(item,signal.SIGINT);sup.wait_empty(item,20)
        inner=recover_inner(item)
    cleanup=sup.stop(item,.5,1,1)
    if name=='runner' and inner.get('cleanup_complete') is not True:
        after=recover_inner(item);inner={'cleanup_complete':after.get('cleanup_complete') is True,'first_attempt':inner,'after_runner_exit':after}
    row={'name':name,'returncode':cleanup['returncode'],'timed_out':timed_out,'cleanup':cleanup,'inner_owned_cleanup':inner,'console_sha256':sha(S/(name+'.console.log'))};steps.append(row)
    if timed_out or cleanup['cleanup_complete'] is not True or (name=='runner' and inner.get('cleanup_complete') is not True):raise RuntimeError('owned driver timeout/inner/outer cleanup: '+name)
    return row['returncode']
try:
    pins=policy['pins'];paths=policy['paths']
    for key,path in (('regulator_binary_sha256',paths['diagnostic_bin']),('worker_binary_sha256',paths['worker_bin']),('diagnostic_source_sha256',paths['diagnostic_source']),('contract_sha256',paths['contract'])):assert sha(path)==pins[key],key
    assert sha(Path(paths['diagnostic_source']).with_name('p1_diag_sink.hpp'))==policy['queue_overflow_proof']['sink_source_sha256']
    args=[str(R/'run_R5_pressure.py'),'--contract',paths['contract'],'--contract-hash',pins['contract_sha256'],'--experiment-root',str(E),'--workspace','/home/trevor/USV/usv_mpc_ws','--run-id',policy['run_id'],'--duration','15','--worker-sha256',pins['worker_binary_sha256'],'--regulator-sha256',pins['regulator_binary_sha256'],'--diagnostic-bin',paths['diagnostic_bin'],'--diagnostic-source',paths['diagnostic_source'],'--diagnostic-source-sha256',pins['diagnostic_source_sha256'],'--witness-enabled','--witness-file','fixed_witness.json','--test-sink-pause-ms','5000']
    rcs['runner']=call('runner',args)
    post=json.loads((D/'postrun_checks.json').read_text());rcs['base']=post['normal_source_check']['checker_returncode'];rcs['delivery']=post['strict_application_delivery']['checker_returncode']
    rcs['mechanism']=call('mechanism',[str(R/'check_R5_mechanism.py'),'--context',str(D/'run_context.json'),'--summary',str(D/'runner_summary.json'),'--witness',str(D/'fixed_witness.json'),'--expected-header',str(D/'witness_expected_header.json'),'--worker-source',str(D/'worker_source.jsonl'),'--regulator-source',str(D/'regulator_source.jsonl'),'--policy',str(P),'--output',str(D/'verification_R5_mechanism.json')],30)
    rcs['independent']=call('independent',[str(R/'check_R5_independent.py'),str(D),'--policy',str(P),'--output',str(D/'verification_R5_independent.json')],30)
    names={'summary':D/'runner_summary.json','postrun':D/'postrun_checks.json','mechanism':D/'verification_R5_mechanism.json','independent':D/'verification_R5_independent.json',
           'base_report':D/'normal_source_check/contract_report.json','delivery_report':D/'strict_application_delivery/resource_delivery_check.json'}
    reports={k:json.loads(p.read_text()) for k,p in names.items()};inputs={k:{'path':str(p),'sha256':sha(p)} for k,p in names.items()}
    stable=True
    for key in ('mechanism','independent'):
        r=reports[key];before=r.get('input_sha256_before');after=r.get('input_sha256_after')
        stable=stable and r.get('raw_inputs_unchanged') is True and type(before) is dict and bool(before) and before==after
        if type(before) is dict:
            for path,h in before.items():stable=stable and sha(path)==h
    for kind in ('normal_source_check','strict_application_delivery'):
        item=reports['postrun'][kind];p=D/item['report_relative_path'] if 'report_relative_path' in item else names['base_report']
        expected=item.get('report_sha256',item.get('contract_report_sha256'));stable=stable and expected==sha(p)
    for key in ('base_report','delivery_report'):
        r=reports[key]
        inventory=r.get('input_sha256_before',r.get('evidence_sha256',{}))
        if 'input_sha256_before' in r:stable=stable and inventory==r.get('input_sha256_after') and bool(inventory)
        for path,h in inventory.items():stable=stable and sha(path)==h
    for path,h in reports['postrun']['fixed_witness_check'].get('evidence_sha256',{}).items():stable=stable and sha(path)==h
    for k,p in names.items():stable=stable and sha(p)==inputs[k]['sha256']
    verify_tools();asset_after=verify_assets(G);host_after=host_preflight()
    combined=combine(**reports,policy=policy,returncodes=rcs,assets_unchanged=not guard_before['drift'] and not asset_after['drift'],inputs_unchanged=stable,
        host_clean=host_after['existing_controller_gazebo_count']==0 and host_after['unreadable_cmdline_count']==0,
        outer_clean=not sup.evidence_failed and not sup.cleanup_failed and all(not x['timed_out'] and x['cleanup']['cleanup_complete'] is True for x in steps)
            and any(x['name']=='runner' and x['inner_owned_cleanup']['cleanup_complete'] is True for x in steps))
    combined['inputs']=inputs;combined['policy_sha256']=sha(P);combined['actual_returncodes']=rcs
    with (D/'verification_R5_combined_gates.json').open('x') as f:json.dump(combined,f,indent=2)
    if not combined['passed']:failure='R5 gates failed: '+','.join(combined['issues'])
except BaseException as error:failure=repr(error);traceback.print_exc(file=sys.stderr)
finally:
    for item in sup.owned.values():
        if item.cleanup is None:
            if item.name=='runner':final_inner.append(recover_inner(item))
            sup.stop(item,.5,1,1)
        if item.name=='runner':final_inner.append(recover_inner(item))
    if not final_inner or final_inner[-1].get('cleanup_complete') is not True:failure=failure or 'final inner owned cleanup unknown/incomplete'
    sup.close()
    try:verify_tools();asset_after=verify_assets(G);host_after=host_preflight()
    except BaseException as error:failure=failure or repr(error)
complete=failure is None and combined is not None and combined['R5_complete'] is True and not sup.cleanup_failed and not sup.evidence_failed
result={'schema':'p1-R5-run-result-v1','run_id':policy['run_id'],'run_directory':str(D),'policy_sha256':sha(P),'failure':failure,'steps':steps,'actual_returncodes':rcs,'combined':combined,'inputs':inputs,
        'guard_before':guard_before,'guard_after':asset_after,'host_before':host_before,'host_after':host_after,'outer_supervision_evidence_complete':not sup.evidence_failed,'outer_cleanup_complete':not sup.cleanup_failed,'final_inner_recovery':final_inner,
        'inner_owned_cleanup_complete':any(x['name']=='runner' and x['inner_owned_cleanup']['cleanup_complete'] is True for x in steps) and bool(final_inner) and final_inner[-1].get('cleanup_complete') is True,
        'R5_run':D.exists(),'R5_complete':complete,'M0b_formally_complete':False,'M4_complete':False,'F6_complete':False,'P1_complete':False,'execute_qualified':False,'physical_execute_release_enabled':False}
with (A/'R5_run_result.json').open('x') as f:json.dump(result,f,indent=2)
print(json.dumps(result))
