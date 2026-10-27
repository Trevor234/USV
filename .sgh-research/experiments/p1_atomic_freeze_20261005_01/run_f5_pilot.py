#!/usr/bin/env python3
"""Own one isolated simulation, freeze runtime provenance, retain all failures."""
from pathlib import Path
import argparse,hashlib,json,math,os,signal,subprocess,time,yaml

ROOT=Path('/home/trevor/USV')
IMPL=ROOT/'.sgh-research/experiments/p1_atomic_freeze_20261005_01'
BASELINE='F5_20261005_atomic_freeze_01'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')

def owned_controller(partition):
    out=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            if (p/'comm').read_text().strip()!='mpc_node':continue
            env=(p/'environ').read_bytes().split(b'\0')
            if b'ROS_DOMAIN_ID=94' in env and ('GZ_PARTITION='+partition).encode() in env:out.append(int(p.name))
        except (OSError,ProcessLookupError):pass
    return out

def baseline_gate():
    base=ROOT/'.sgh-research/baselines'/BASELINE
    manifest=json.loads((base/'baseline_manifest.json').read_text())
    assert manifest['baseline_id']==BASELINE
    assert manifest['integrity']['frozen_baseline_verified'] is True
    errors=[];count=0
    for name in ['source_hashes.json','installed_hashes.json','model_assets.json']:
        doc=json.loads((base/name).read_text());assets=doc if isinstance(doc,list) else doc['files']
        for asset in assets:
            if asset.get('sha256'):
                count+=1
                if sha(ROOT/asset['path'])!=asset['sha256']:errors.append(asset['path'])
    if errors:raise RuntimeError('F4 live asset mismatch:'+str(errors))
    return {'baseline_id':BASELINE,'manifest_sha256':sha(base/'baseline_manifest.json'),
            'verified_assets':count,'errors':errors}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('kind',choices=['baseline']);ap.add_argument('--attempt',default='01');ap.add_argument('--duration',type=float,default=60);args=ap.parse_args()
    run='p1_f5_atomic_'+args.kind+'_20261005_'+args.attempt
    exp=ROOT/'.sgh-research/experiments'/run;exp.mkdir(exist_ok=False)
    (exp/'logs').mkdir(); bag=ROOT/'data/sim_bags'/run
    if os.path.lexists(bag):raise RuntimeError('bag exists')
    partition='usv_'+run;os.environ.update(ROS_DOMAIN_ID='94',ROS_LOCALHOST_ONLY='1',GZ_PARTITION=partition)
    refs=IMPL/'references';refs.mkdir(exist_ok=True)
    ref=refs/'straight.yaml'
    content=(ROOT/'.sgh-research/experiments/v5_scaling_fix_20261003/straight_waypoints.yaml').read_text()
    if ref.exists():assert ref.read_text()==content
    else:ref.write_text(content)
    nominal=ROOT/'usv_mpc_ws/src/usv_bringup/config/p0_nominal_f3.yaml'
    plant=ROOT/'usv_mpc_ws/src/usv_bringup/config/p0_plant_f3.yaml'
    if args.kind!='baseline':
        changed=nominal if args.kind=='nominal_mass' else plant
        doc=yaml.safe_load(changed.read_text())
        doc['/**']['ros__parameters']['vehicle']['mass']=17.04
        cloned=exp/(args.kind+'_input.yaml')
        cloned.write_text(yaml.safe_dump(doc,sort_keys=False))
        if args.kind=='nominal_mass':nominal=cloned
        else:plant=cloned
    config_inputs={str(p):sha(p) for p in [nominal,plant,ROOT/'usv_mpc_ws/src/usv_bringup/config/mpc_params.yaml',ROOT/'usv_mpc_ws/src/usv_bringup/config/mpc_params_vrx.yaml',ROOT/'usv_mpc_ws/src/usv_simulation/config/vrx_model.yaml',ref]}
    config_hash=hashlib.sha256(json.dumps(config_inputs,sort_keys=True).encode()).hexdigest()
    cmd=['ros2','launch','usv_bringup','p0_config_reference_recording.launch.py','headless:=true','visualize:=false',
         'waypoints_file:='+str(ref),'bag_path:='+str(bag),'model_output_dir:='+str(exp/'model'),
         'nominal_vehicle_config:='+str(nominal),'plant_vehicle_config:='+str(plant),'config_output_dir:='+str(exp/'config'),
         'research_run_id:='+run,'research_baseline_id:='+BASELINE,'research_output_dir:='+str(exp/'source'),
         'research_config_hash:='+config_hash,'research_expected_pose_frame:=map',
         'research_expected_child_frame:=wamv/base_link','research_frame_contract_verified:=true']
    identity={'run_id':run,'baseline_id':BASELINE,'launch_command':cmd,'config_inputs':config_inputs,'config_hash':config_hash,'ros_domain_id':94,'gazebo_partition':partition,'reference_sha256':sha(ref),'bag_time_domain':'system_receive','physical_match_window_ns':20000000,'nominal_dt_s':.2,'requested_wall_duration_s':args.duration}
    save(exp/'launch_context.json',identity)
    observer=None;launch=None;reason=None;start=time.monotonic_ns();run_start=None;cpu_start=None
    try:
        save(exp/'baseline_start_gate.json',baseline_gate())
        launch=subprocess.Popen(cmd,stdout=(exp/'logs/launch.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
        time.sleep(12)
        graphcmd=['/usr/bin/python3',str(ROOT/'usv_mpc_ws/scripts/capture_p0_runtime_context.py'),'--run-id',run,'--baseline-id',BASELINE,'--bag-path',str(bag),'--output',str(exp/'topic_graph.json'),'--wait-timeout','55','--reference-prediction']
        graph=subprocess.run(graphcmd,capture_output=True,text=True,timeout=75);(exp/'logs/graph.log').write_text(graph.stdout+graph.stderr)
        if graph.returncode:raise RuntimeError('graph/runtime gate failed')
        g=json.loads((exp/'topic_graph.json').read_text());pd=yaml.safe_load(g['effective_parameter_dump']['stdout']);pn=pd.get('/mpc_controller_node',pd.get('mpc_controller_node'));assert pn is not None;params=pn['ros__parameters']
        assert params['enable_research_logging'] and params['research_run_id']==run and params['research_config_hash']==config_hash
        assert params['output_mode']=='vrx_thrust' and params['vrx_thrust_scale']==1.0 and params['use_sim_time']
        from usv_bringup.research_config_sources import verify_runtime_sources
        config_runtime=verify_runtime_sources(exp/'config',exp/'model',pd)
        save(exp/'config_runtime.json',config_runtime)
        assert params['enable_reference_prediction_logging']
        assert params['research_nominal_config_hash']==config_runtime['nominal_effective_yaml_sha256']
        assert params['horizon']==20 and params['mpc_dt']==.2
        actual_dt=params.get('dynamic',{}).get('dt',params.get('dynamic.dt'))
        assert actual_dt==.2, 'actual dynamic prediction dt differs'
        actual_N=max(1,int(math.floor(params['horizon']*params['mpc_dt']/actual_dt+.5)))
        assert actual_N==20
        import re
        runtime_backend=re.findall(r'\| backend=([A-Za-z0-9_]+) \| output=vrx_thrust',(exp/'logs/launch.log').read_text())
        assert len(set(runtime_backend))==1, 'unique runtime backend startup evidence required'
        runtime_backend=runtime_backend[0]
        assert all(s['frame_id']=='map' and s['child_frame_id']=='wamv/base_link' for s in g['odom_samples'])
        import xml.etree.ElementTree as E
        plugins=E.parse(exp/'model/model.sdf').getroot().findall('.//plugin')
        odom=[p for p in plugins if p.get('name')=='gz::sim::systems::OdometryPublisher']
        assert len(odom)==1 and odom[0].findtext('dimensions')=='3' and odom[0].findtext('odom_frame')=='map' and odom[0].findtext('robot_base_frame')=='wamv/base_link'
        pids=owned_controller(partition);assert len(pids)==1
        pid=pids[0]
        assert hashlib.sha256(g['effective_parameter_dump']['stdout'].encode()).hexdigest()==g['effective_parameter_dump']['stdout_sha256']
        install_doc=json.loads((ROOT/'.sgh-research/baselines'/BASELINE/'installed_hashes.json').read_text())
        for package,actual in g['installed_package_prefixes'].items():
            assert actual['returncode']==0
            assert Path(actual['stdout'].strip()).resolve()==Path(install_doc['packages'][package]['prefix']).resolve()
        executable=(Path('/proc')/str(pid)/'exe').resolve(strict=True)
        expected_executable=ROOT/'usv_mpc_ws/install/usv_mpc_cpp/lib/usv_mpc_cpp/mpc_node'
        assert executable==expected_executable.resolve(strict=True)
        assert sha(executable)==sha(expected_executable)
        save(exp/'process_executable.json',{'pid':pid,'resolved_path':str(executable),'sha256':sha(executable)})
        cpu_start=Path('/proc')/str(pid)/'stat'
        cpu_sample_start=time.monotonic_ns()
        stat_before=cpu_start.read_text().split();ticks_before=int(stat_before[13])+int(stat_before[14])
        observer=subprocess.Popen(['/usr/bin/python3',str(IMPL/'stop_after_publish_gap.py'),
            '--experiment',str(exp),'--run-id',run,'--partition',partition,'--pid',str(pid)],
            stdout=(exp/'logs/shutdown_gate.log').open('w'),stderr=subprocess.STDOUT)
        ready_deadline=time.monotonic()+10
        while not (exp/'shutdown_observer_ready.json').exists() and time.monotonic()<ready_deadline:
            if observer.poll() is not None:raise RuntimeError('shutdown observer exited before ready')
            time.sleep(.02)
        if not (exp/'shutdown_observer_ready.json').exists():raise RuntimeError('shutdown observer not ready')
        arm=subprocess.run(['ros2','param','set','/mpc_controller_node','research_logging_armed','true'],capture_output=True,text=True,timeout=15)
        (exp/'logs/arm.log').write_text(arm.stdout+arm.stderr)
        if arm.returncode:raise RuntimeError('arm failed')
        run_start=time.monotonic_ns();time.sleep(args.duration)
        stat_after=cpu_start.read_text().split();ticks_after=int(stat_after[13])+int(stat_after[14])
        cpu_sample_wall_s=(time.monotonic_ns()-cpu_sample_start)/1e9
        cpu_seconds=(ticks_after-ticks_before)/os.sysconf('SC_CLK_TCK')
        save(exp/'shutdown_requested.json',{'requested_steady_ns':time.monotonic_ns()})
        if observer.wait(timeout=15)!=0:raise RuntimeError('owned shutdown gap gate failed')
        deadline=time.monotonic()+15
        while not (exp/'source/session_summary.json').exists() and time.monotonic()<deadline:time.sleep(.1)
        if not (exp/'source/session_summary.json').exists():raise RuntimeError('source summary missing after stop')
        session=json.loads((exp/'source/session_summary.json').read_text())
        time.sleep(2)
        context={**identity,**{k:session[k] for k in ['producer_instance_id','steady_clock_domain']},
                 'frame_contract_verified':True,'expected_pose_frame':'map','expected_child_frame':'wamv/base_link','twist_frame':'body',
                 'frame_evidence':{'model_sdf_sha256':sha(exp/'model/model.sdf'),'gazebo_plugin':'OdometryPublisher dimensions=3, inverse rotation to body','gazebo_source_url':'https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/odometry_publisher/OdometryPublisher.cc','bridge_source_url':'https://github.com/gazebosim/ros_gz/blob/jazzy/ros_gz_bridge/src/convert/nav_msgs.cpp'},
                 'physical_publisher_counts':{'left':1,'right':1},'runtime_effective_verified':True,
                 'effective_parameter_dump_sha256':g['effective_parameter_dump']['stdout_sha256'],
                 'runtime_effective_parameters':params,'frozen_baseline_verified':False,
                 'frozen_baseline_status':'F5 pending; reconcile after static freeze',
                 'max_clock_receive_age_ns':500000000,'max_source_clock_lag_ns':500000000,'max_source_clock_future_ns':100000000,
                 'wall_start_steady_ns':run_start,'wall_end_steady_ns':time.monotonic_ns(),
                 'controller_cpu_seconds':cpu_seconds,'controller_cpu_sample_wall_s':cpu_sample_wall_s,'controller_cpu_one_core_percent':100*cpu_seconds/cpu_sample_wall_s}
        runtime_assets={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'usv_mpc_ws/install/usv_mpc_cpp/lib/usv_mpc_cpp/mpc_node',ROOT/'usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp',ROOT/'usv_mpc_ws/src/usv_mpc_cpp/include/usv_mpc_cpp/mpc_node.hpp',ROOT/'usv_mpc_ws/src/usv_mpc_cpp/include/usv_mpc_cpp/research_logger.hpp',ROOT/'usv_mpc_ws/src/usv_bringup/launch/vrx.launch.py']}
        context['runtime_assets']=runtime_assets
        context['source_node_sha256']=runtime_assets['usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp']
        base=ROOT/'.sgh-research/baselines'/BASELINE
        errors=[]
        for name in ['source_hashes.json','installed_hashes.json','model_assets.json']:
            document=json.loads((base/name).read_text());assets=document if isinstance(document,list) else document['files']
            for asset in assets:
                if asset.get('sha256') and sha(ROOT/asset['path'])!=asset['sha256']:errors.append(asset['path'])
        if errors:raise RuntimeError('F5 live assets mismatch:'+str(errors))
        context.update(frozen_baseline_verified=True,frozen_baseline_status='F5 full live source/install/model hash gate passed',
                       frozen_baseline_manifest_sha256=sha(base/'baseline_manifest.json'),
                       independent_config_runtime=config_runtime,independent_config_runtime_sha256=sha(exp/'config_runtime.json'),
                       source_runner_sha256=sha(Path(__file__)))
        evidence=IMPL/'solver_test_evidence.json'
        assert evidence.is_file()
        context['reference_prediction_contract']={
            'enabled':True,'schema_version':'p0-reference-prediction-v1',
            'record_policy':'solve_invoked_only','matrix_layout':'k_major',
            'prediction_policy':'accepted_post_deadline_only',
            'nominal_config_hash':params['research_nominal_config_hash'],
            'horizon_steps':actual_N,'prediction_dt':actual_dt,
            'backend':runtime_backend,
            'source_node_sha256':context['source_node_sha256'],
            'solver_test_evidence':{'path':str(evidence),'file_sha256':sha(evidence)}}
        atomic_path=IMPL/'atomic_freeze_test_evidence.json'
        atomic=json.loads(atomic_path.read_text())
        assert atomic['schema']=='p1-atomic-freeze-compiled-test-evidence/1'
        assert atomic['baseline_id']==BASELINE
        assert atomic['source_node_sha256']==context['source_node_sha256']
        assert atomic['exit_code']==0 and atomic['all_required_passed'] is True
        assert len(atomic['required_cases'])>=5
        assert all(name.startswith('AtomicFreezeContract.') for name in atomic['required_cases'])
        assert set(atomic['required_cases']).issubset(set(atomic['tested_cases']))
        assert sha(Path(atomic['test_binary_path']))==atomic['compiled_test_binary_sha256']
        assert sha(Path(atomic['gtest_report_path']))==atomic['gtest_report_sha256']
        context['atomic_freeze_contract']={
            'scope':'dynamic B eligibility and actual state/reference freeze under one state lock',
            'compiled_test_evidence_path':str(atomic_path),'compiled_test_evidence_sha256':sha(atomic_path),
            'compiled_test_evidence_verified':True,
            'frozen_clear_cancels_inflight_solve':False,
            'independent_worker_implemented':False,'fixed_execution_tick_implemented':False,
            'P1_complete':False}
        save(exp/'run_context.json',context)
    except Exception as exc:
        reason=str(exc);save(exp/'run_failure.json',{'reason':reason,'elapsed_wall_s':(time.monotonic_ns()-start)/1e9})
    finally:
        if observer and observer.poll() is None:
            observer.terminate()
            try:observer.wait(timeout=5)
            except subprocess.TimeoutExpired:observer.kill();observer.wait()
        if launch and launch.poll() is None:
            os.killpg(launch.pid,signal.SIGINT)
            try:launch.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(launch.pid,signal.SIGTERM)
                try:launch.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(launch.pid,signal.SIGKILL);launch.wait()
    if (exp/'run_context.json').exists():
        check=subprocess.run(['/usr/bin/python3',str(ROOT/'usv_mpc_ws/scripts/check_p0_contract.py'),str(bag),'--session-summary',str(exp/'source/session_summary.json'),'--run-context',str(exp/'run_context.json'),'--output-dir',str(exp/'reports_initial')],capture_output=True,text=True,timeout=120)
        (exp/'logs/check.log').write_text(check.stdout+check.stderr)
        extra=subprocess.run(['/usr/bin/python3',str(ROOT/'usv_mpc_ws/scripts/check_reference_prediction.py'),str(bag),
            '--session-summary',str(exp/'source/session_summary.json'),'--run-context',str(exp/'run_context.json'),
            '--publisher-contract-report',str(exp/'reports_initial/contract_report.json'),
            '--output-dir',str(exp/'reference_reports')],capture_output=True,text=True,timeout=120)
        (exp/'logs/reference_check.log').write_text(extra.stdout+extra.stderr)
        accepted_gates=False
        rp=exp/'reference_reports/reference_prediction_report.json'
        if rp.exists():
            report=json.loads(rp.read_text())
            accepted_gates=all(report.get(key) is True for key in ['passed','combined_recording_contract_verified',
                'frozen_solver_test_evidence_verified','actual_solve_input_verified'])
        save(exp/'pilot_result.json',{'run_id':run,'check_exit_code':check.returncode,'reference_check_exit_code':extra.returncode,
            'all_required_acceptance_flags':accepted_gates,'reason':reason if accepted_gates and not check.returncode and not extra.returncode else 'checker or required acceptance flag failed', 'launch_return_code':launch.returncode,
            'elapsed_wall_s':(time.monotonic_ns()-start)/1e9})
        if check.returncode or extra.returncode or not accepted_gates:reason='checker or required acceptance flag failed; retained original data and reports' 
    print(json.dumps({'run_id':run,'experiment':str(exp),'reason':reason},ensure_ascii=False))
    return 1 if reason else 0
if __name__=='__main__':raise SystemExit(main())
