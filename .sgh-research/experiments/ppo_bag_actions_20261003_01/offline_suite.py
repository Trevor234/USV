import json, pathlib, shlex, subprocess, time

root=pathlib.Path('/home/trevor/USV')
exp=root/'.sgh-research/experiments/ppo_bag_actions_20261003_01'
reports=exp/'results/offline'
reports.mkdir(parents=True,exist_ok=False)
checker=root/'usv_mpc_ws/scripts/check_ppo_bag.py'
historical=root/'data/sim_bags/rl_c_001'
physical=root/'.sgh-research/experiments/v5_scaling_fix_20261003/results/new_physical_n/new_physical_n'
results=[]
for label,bag,profile,expected in [
    ('historical_legacy',historical,'legacy-actions',2),
    ('historical_strict',historical,'ppo-actions-v1',2),
    ('physical_legacy',physical,'legacy-actions',0),
    ('physical_strict',physical,'ppo-actions-v1',2),
]:
    output=reports/(label+'.json')
    argv=['python3',str(checker),str(bag),'--profile',profile,
          '--thrust-limit-n','25.0','--report',str(output)]
    command='\n'.join(['set -e','source /opt/ros/jazzy/setup.bash',shlex.join(argv)])
    start=time.monotonic()
    process=subprocess.run(['bash','-c',command],cwd=root,text=True,capture_output=True,timeout=120)
    (reports/(label+'.log')).write_text(process.stdout+process.stderr)
    report=json.loads(output.read_text())
    codes=sorted({failure['code'] for failure in report.get('failures',[])})
    outcome=dict(label=label,bag=str(bag),profile=profile,returncode=process.returncode,
        expected=expected,matched_expectation=process.returncode==expected,
        wall_seconds=time.monotonic()-start,command=command,
        action_stream_consistent=report.get('recorded_action_stream_consistent'),
        failure_codes=codes,warning_codes=sorted({warning['code'] for warning in report.get('warnings',[])}),
        counts=report.get('actual_message_counts'),matching=report.get('matching'))
    if label=='physical_strict':
        outcome['matched_expectation'] &= report.get('recorded_action_stream_consistent') is True and codes==['missing_topic']
    results.append(outcome)
    print(json.dumps(outcome,ensure_ascii=False),flush=True)
passed=all(case['matched_expectation'] for case in results)
summary=dict(passed=passed,cases=results)
(reports/'suite_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
assert passed, 'offline profile expectations failed'
