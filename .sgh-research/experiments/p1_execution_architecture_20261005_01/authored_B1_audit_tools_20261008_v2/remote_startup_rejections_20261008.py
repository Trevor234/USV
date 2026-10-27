from pathlib import Path
import os,hashlib,json,sys,time
E=Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01');R=E/'authored_runtime_v30_contract_20261007';A=E/'authored_B1_diag_20261008_v3';G=E/'contract_B0_closed_assets_20261007.json';D=A/'startup_rejections_v2'
sys.path.insert(0,str(R))
from run_worker_fault_matrix import verify_assets
from run_formal_no_output_validation import host_preflight
from owned_process_supervisor import Supervisor,sha256_file
import rclpy
build=json.loads((A/'build_result.json').read_text());assert all(next(c for c in build['commands'] if c['name']==n)['returncode']==0 for n in ('configure','build','test_p1_witness','test_p1_diag_sink'));host=host_preflight();guard=verify_assets(G);assert not D.exists();D.mkdir()
binary=A/'build/p1_regulator_r5_diag';contract=E/'authored_v13_resource_20261007/p1_shadow_contract_v5.json';source=A/'diag/regulator_r5_diag.cpp'
assert sha256_file(contract)=='0e3eb70e74e922059ff17014ab1971b8a9fe20be0171964fc26410b7d769a933'
env=os.environ.copy();rclpy.init();node=rclpy.create_node('p1_B1_rejection_observer');sup=Supervisor(D);rows=[];failure=None;max_endpoints=0
def check_endpoints():
    global max_endpoints
    count=sum(len(node.get_publishers_info_by_topic(t)) for t in ('/wamv/thrusters/left/thrust','/wamv/thrusters/right/thrust'));max_endpoints=max(max_endpoints,count)
    if count:raise RuntimeError('physical publishers appeared in rejected startup')
def cli_params(values):
    result=[]
    for k,v in values.items():result+=['-p',k+':='+str(v).lower() if isinstance(v,bool) else k+':='+str(v)]
    return result
common={'mode':'no_output','run_id':'p1_B1_reject_20261008','contract_file':str(contract),'contract_hash':sha256_file(contract),'worker_pid':os.getpid()}
identity={'witness_enabled':True,'diagnostic_source_file':str(source),'diagnostic_source_sha256':sha256_file(source),'diagnostic_binary_sha256':sha256_file(binary),'worker_binary_sha256':sha256_file(Path('/proc/self/exe')),'witness_worker_instance':'a'*64}
cases=[('execute_mode',{'mode':'execute'},'mode'),('shadow_mode',{'mode':'shadow'},'no_output diag5'),
       ('pause_without_witness',{'test_sink_pause_ms':1},'pause requires'),('pause_above_limit',{'test_sink_pause_ms':5001},'finite'),
       ('pause_negative',{'test_sink_pause_ms':-1},'finite'),('disabled_output_path',{'witness_enabled':False},'disabled witness'),
       ('enabled_empty_path',{'witness_enabled':True},'output path'),
       ('identity_mismatch',{**identity,'diagnostic_source_sha256':'b'*64},'digest mismatch'),
       ('malformed_worker_instance',{**identity,'witness_worker_instance':'not-a-hash'},'header invalid')]
try:
    for name,values,error in cases:
        check_endpoints();source_file=D/(name+'.source.jsonl');witness_file=D/(name+'.witness.json');params={**common,'source_file':str(source_file),**values}
        if name!='enabled_empty_path' and (params.get('witness_enabled') or name=='disabled_output_path'):params['witness_file']=str(witness_file)
        item=sup.spawn(name,[str(binary),'--ros-args',*cli_params(params)],env,binary,sha256_file(binary))
        end=time.monotonic()+3
        while item.process.poll() is None and time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.01);check_endpoints()
        timed_out=item.process.poll() is None
        cleanup=sup.stop(item,.5,1,1);check_endpoints();console=(D/(name+'.console.log')).read_text()
        passed=not timed_out and cleanup['cleanup_complete'] and cleanup['returncode']==1 and error in console and not source_file.exists() and not witness_file.exists()
        rows.append({'name':name,'returncode':cleanup['returncode'],'timeout':timed_out,'expected_error_fragment':error,'matched':error in console,'source_created':source_file.exists(),'witness_created':witness_file.exists(),'cleanup':cleanup,'passed':passed})
        if not passed:raise RuntimeError('startup rejection failed: '+name)
except BaseException as e:failure=repr(e)
finally:
    for item in sup.owned.values():
        if item.cleanup is None:sup.stop(item,.5,1,1)
    sup.close();node.destroy_node();rclpy.shutdown()
result={'schema':'p1-B1-startup-rejections-v1','rows':rows,'count':len(rows),'failure':failure,'passed':failure is None and len(rows)==len(cases),'max_physical_publisher_endpoints':max_endpoints,'host_before':host,'host_after':host_preflight(),'guard_before':guard,'guard_after':verify_assets(G),'supervisor_evidence_failed':sup.evidence_failed,'cleanup_failed':sup.cleanup_failed,'C0_run':False,'R5_run':False,'physical_release':False}
with (D/'result.json').open('x') as f:json.dump(result,f,indent=2)
print(json.dumps(result))
