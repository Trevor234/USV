import pathlib,subprocess,shlex,json,time,os,signal,hashlib
root=pathlib.Path('/home/trevor/USV');exp=root/'.sgh-research/experiments/nmpc_timeout_fix_20261003';build=root/'usv_mpc_ws/build/usv_mpc_cpp';out=exp/'baseline_binary';out.mkdir(exist_ok=True)
backup=pathlib.Path(json.loads((exp/'apply.json').read_text())['backup'])
flags={}
for s in (build/'CMakeFiles/mpc_node.dir/flags.make').read_text().splitlines():
    if ' = ' in s:
        k,v=s.split(' = ',1);flags[k]=shlex.split(v)
base=['/usr/bin/c++','-I'+str(backup/'usv_mpc_ws/src/usv_mpc_cpp/include')]+flags['CXX_DEFINES']+flags['CXX_INCLUDES']+flags['CXX_FLAGS']
with (out/'build.log').open('w') as f:
    for name in ['mpc_node','mpc_node_main']:
        source=backup/'usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp' if name=='mpc_node' else root/'usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node_main.cpp'
        subprocess.run(base+['-c',str(source),'-o',str(out/(name+'.o'))],stdout=f,stderr=subprocess.STDOUT,check=True)
    link=shlex.split((build/'CMakeFiles/mpc_node.dir/link.txt').read_text());link=[str(out/'mpc_node.o') if s=='CMakeFiles/mpc_node.dir/src/mpc_node.cpp.o' else str(out/'mpc_node_main.o') if s=='CMakeFiles/mpc_node.dir/src/mpc_node_main.cpp.o' else s for s in link];link[link.index('-o')+1]=str(out/'mpc_node')
    subprocess.run(link,cwd=build,stdout=f,stderr=subprocess.STDOUT,check=True)
launch=(root/'usv_mpc_ws/src/usv_bringup/launch/vrx.launch.py').read_text().replace('executable="mpc_node"','executable="'+str(out/'mpc_node')+'"')
(exp/'vrx_baseline.launch.py').write_text(launch)
wp=exp/'straight_waypoints.yaml';wp.write_text('waypoints:\n  - {x: -532.0, y: 162.0}\n  - {x: -513.0894, y: 191.4515}\n  - {x: -494.1788, y: 220.9030}\n')
for name in ['baseline_active','postpatch_active']:
    case=exp/'results'/name;case.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env.update(ROS_DOMAIN_ID='89',ROS_LOCALHOST_ONLY='1',GZ_PARTITION='nmpc_timeout_'+name+'_20261003')
    target=str(exp/'vrx_baseline.launch.py') if name=='baseline_active' else 'usv_bringup vrx.launch.py'
    cmd='source /opt/ros/jazzy/setup.bash && source /home/trevor/USV/vrx_ws/install/setup.bash && source /home/trevor/USV/usv_mpc_ws/install/setup.bash && exec ros2 launch '+target+' scheme:=B headless:=True record_bag:=True bag_dir:='+str(case)+' run_id:='+name+' model_output_dir:='+str(case/'model')+' waypoints_file:='+str(wp)
    start=time.time()
    with (case/'launch.log').open('w') as f:
        p=subprocess.Popen(['bash','-c',cmd],env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        (case/'process.json').write_text(json.dumps({'pid':p.pid,'start_wall':start,'command':cmd,'env':{k:env[k] for k in ['ROS_DOMAIN_ID','ROS_LOCALHOST_ONLY','GZ_PARTITION']}}))
        bounded=False
        try:rc=p.wait(timeout=60)
        except subprocess.TimeoutExpired:
            bounded=True;os.killpg(p.pid,signal.SIGINT)
            try:rc=p.wait(timeout=20)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);rc=p.wait(timeout=15)
    (case/'complete.json').write_text(json.dumps({'returncode':rc,'wall_elapsed':time.time()-start,'bounded_stop':bounded}))
    cmd='source /opt/ros/jazzy/setup.bash && source /home/trevor/USV/usv_mpc_ws/install/setup.bash && python3 '+str(exp/'analyze_bags.py')+' '+name
    with (case/'analysis.log').open('w') as f:subprocess.run(['bash','-c',cmd],stdout=f,stderr=subprocess.STDOUT,check=True)
(exp/'active_comparison_complete.json').write_text(json.dumps({'complete':True}))
