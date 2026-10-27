#!/usr/bin/env python3
"""Own one isolated simulation, freeze runtime provenance, retain all failures."""
from pathlib import Path
import argparse,hashlib,json,math,os,signal,subprocess,time,yaml

ROOT=Path('/home/trevor/USV')
IMPL=ROOT/'.sgh-research/experiments/p0_contract_implementation_20261004'
BASELINE='F2_20261004_publisher_contract_01'

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

def main():
    ap=argparse.ArgumentParser();ap.add_argument('kind',choices=['straight','left','right']);ap.add_argument('--attempt',default='01');ap.add_argument('--duration',type=float,default=60);args=ap.parse_args()
    run='p0_contract_'+args.kind+'_20261004_'+args.attempt
    exp=ROOT/'.sgh-research/experiments'/run;exp.mkdir(exist_ok=False)
    (exp/'logs').mkdir(); bag=ROOT/'data/sim_bags'/run
    if bag.exists():raise RuntimeError('bag exists')
    partition='usv_'+run;os.environ.update(ROS_DOMAIN_ID='94',ROS_LOCALHOST_ONLY='1',GZ_PARTITION=partition)
    refs=IMPL/'references';refs.mkdir(exist_ok=True)
    ref=refs/(args.kind+'.yaml')
    if args.kind=='straight':
        content=(ROOT/'.sgh-research/experiments/v5_scaling_fix_20261003/straight_waypoints.yaml').read_text()
    else:
        a=1.0;d=1 if args.kind=='left' else -1
        x=-532+15*math.cos(a);y=162+15*math.sin(a)
        content='waypoints:\n  - {x: -532.0, y: 162.0}\n  - {x: %.9f, y: %.9f}\n  - {x: %.9f, y: %.9f}\n'%(x,y,x+45*math.cos(a+d*math.pi/4),y+45*math.sin(a+d*math.pi/4))
    if ref.exists():assert ref.read_text()==content
    else:ref.write_text(content)
    config_inputs={str(p):sha(p) for p in [ROOT/'usv_mpc_ws/src/usv_bringup/config/usv_params_sim.yaml',ROOT/'usv_mpc_ws/src/usv_bringup/config/mpc_params.yaml',ROOT/'usv_mpc_ws/src/usv_bringup/config/mpc_params_vrx.yaml',ROOT/'usv_mpc_ws/src/usv_simulation/config/vrx_model.yaml',ref]}
    config_hash=hashlib.sha256(json.dumps(config_inputs,sort_keys=True).encode()).hexdigest()
    cmd=['ros2','launch','usv_bringup','p0_contract_recording.launch.py','headless:=true','visualize:=false',
         'waypoints_file:='+str(ref),'bag_path:='+str(bag),'model_output_dir:='+str(exp/'model'),
         'research_run_id:='+run,'research_baseline_id:='+BASELINE,'research_output_dir:='+str(exp/'source'),
         'research_config_hash:='+config_hash,'research_expected_pose_frame:=map',
         'research_expected_child_frame:=wamv/base_link','research_frame_contract_verified:=true']
    identity={'run_id':run,'baseline_id':BASELINE,'pilot_runner_sha256':sha(Path(__file__)),'launch_command':cmd,'config_inputs':config_inputs,'config_hash':config_hash,'ros_domain_id':94,'gazebo_partition':partition,'reference_sha256':sha(ref),'bag_time_domain':'system_receive','physical_match_window_ns':20000000,'nominal_dt_s':.2,'requested_wall_duration_s':args.duration}
    save(exp/'launch_context.json',identity)
    launch=None;reason=None;start=time.monotonic_ns();run_start=None;cpu_start=None
    try:
        launch=subprocess.Popen(cmd,stdout=(exp/'logs/launch.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
        time.sleep(12)
        graphcmd=['/usr/bin/python3',str(ROOT/'usv_mpc_ws/scripts/capture_p0_runtime_context.py'),'--run-id',run,'--baseline-id',BASELINE,'--bag-path',str(bag),'--output',str(exp/'topic_graph.json'),'--wait-timeout','55']
        graph=subprocess.run(graphcmd,capture_output=True,text=True,timeout=75);(exp/'logs/graph.log').write_text(graph.stdout+graph.stderr)
        if graph.returncode:raise RuntimeError('graph/runtime gate failed')
        g=json.loads((exp/'topic_graph.json').read_text());parameter_document=yaml.safe_load(g['effective_parameter_dump']['stdout']); parameter_node=parameter_document.get('/mpc_controller_node',parameter_document.get('mpc_controller_node')); assert parameter_node is not None, 'expected unique controller parameter namespace'; params=parameter_node['ros__parameters']
        assert params['enable_research_logging'] and params['research_run_id']==run and params['research_config_hash']==config_hash
        assert params['output_mode']=='vrx_thrust' and params['vrx_thrust_scale']==1.0 and params['use_sim_time']
        assert all(s['frame_id']=='map' and s['child_frame_id']=='wamv/base_link' for s in g['odom_samples'])
        import xml.etree.ElementTree as E
        plugins=E.parse(exp/'model/model.sdf').getroot().findall('.//plugin')
        odom=[p for p in plugins if p.get('name')=='gz::sim::systems::OdometryPublisher']
        assert len(odom)==1 and odom[0].findtext('dimensions')=='3' and odom[0].findtext('odom_frame')=='map' and odom[0].findtext('robot_base_frame')=='wamv/base_link'
        pids=owned_controller(partition);assert len(pids)==1
        pid=pids[0];cpu_start=Path('/proc')/str(pid)/'stat'
        stat_before=cpu_start.read_text().split();ticks_before=int(stat_before[13])+int(stat_before[14])
        arm=subprocess.run(['ros2','param','set','--no-daemon','--spin-time','2','--timeout','8','/mpc_controller_node','research_logging_armed','true'],capture_output=True,text=True,timeout=15)
        (exp/'logs/arm.log').write_text(arm.stdout+arm.stderr)
        if arm.returncode:raise RuntimeError('arm failed')
        run_start=time.monotonic_ns();time.sleep(args.duration)
        stat_after=cpu_start.read_text().split();ticks_after=int(stat_after[13])+int(stat_after[14])
        cpu_seconds=(ticks_after-ticks_before)/os.sysconf('SC_CLK_TCK')
        os.kill(pid,signal.SIGINT)
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
                 'frozen_baseline_status':'F2 pending; reconcile after static freeze',
                 'max_clock_receive_age_ns':500000000,'max_source_clock_lag_ns':500000000,'max_source_clock_future_ns':100000000,
                 'wall_start_steady_ns':run_start,'wall_end_steady_ns':time.monotonic_ns(),
                 'controller_cpu_seconds':cpu_seconds,'controller_cpu_one_core_percent':100*cpu_seconds/args.duration}
        runtime_assets={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'usv_mpc_ws/install/usv_mpc_cpp/lib/usv_mpc_cpp/mpc_node',ROOT/'usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp',ROOT/'usv_mpc_ws/src/usv_mpc_cpp/include/usv_mpc_cpp/mpc_node.hpp',ROOT/'usv_mpc_ws/src/usv_mpc_cpp/include/usv_mpc_cpp/research_logger.hpp',ROOT/'usv_mpc_ws/src/usv_bringup/launch/vrx.launch.py']}
        context['runtime_assets']=runtime_assets;save(exp/'run_context.json',context)
    except Exception as exc:
        reason=str(exc);save(exp/'run_failure.json',{'reason':reason,'elapsed_wall_s':(time.monotonic_ns()-start)/1e9})
    finally:
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
        save(exp/'pilot_result.json',{'run_id':run,'check_exit_code':check.returncode,'reason':reason,'launch_return_code':launch.returncode,'elapsed_wall_s':(time.monotonic_ns()-start)/1e9})
    print(json.dumps({'run_id':run,'experiment':str(exp),'reason':reason},ensure_ascii=False))
if __name__=='__main__':main()
