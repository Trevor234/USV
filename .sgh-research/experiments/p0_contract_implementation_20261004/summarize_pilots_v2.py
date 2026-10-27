from pathlib import Path
import json,sys,math,hashlib
ROOT=Path('/home/trevor/USV');sys.path.insert(0,str(ROOT/'usv_mpc_ws/scripts'))
import check_p0_contract as c
runs=['p0_contract_straight_20261004_03','p0_contract_left_20261004_01','p0_contract_right_20261004_01']
result=[]
for run in runs:
    exp=ROOT/'.sgh-research/experiments'/run;bag=ROOT/'data/sim_bags'/run
    if not (exp/'reports_final/contract_report.json').exists():raise RuntimeError('final reports not ready:'+run)
    before=c.hash_bag(bag);cfg=c.Config();records,_,_=c.read_bag(bag,cfg)
    states=[r.payload for r in records if r.topic==c.DEFAULT_TOPICS['state']]
    actions=[r.payload for r in records if r.topic==c.DEFAULT_TOPICS['applied']]
    cycles=[r.payload for r in records if r.topic==c.DEFAULT_TOPICS['cycle']]
    paths=[r.payload for r in records if r.topic==c.DEFAULT_TOPICS['path']]
    valid_paths=[p for p in paths if len(p['poses'])>=2]
    if not valid_paths:raise RuntimeError('no path with segments:'+run)
    path=[(p['pose']['position']['x'],p['pose']['position']['y']) for p in valid_paths[-1]['poses']]
    if not all([(p['pose']['position']['x'],p['pose']['position']['y']) for p in v['poses']]==path for v in valid_paths):raise RuntimeError('static reference changed:'+run)
    def distance(x,y):
        best=float('inf')
        for (a,b),(u,v) in zip(path,path[1:]):
            dx=u-a;dy=v-b;norm=dx*dx+dy*dy
            t=max(0,min(1,((x-a)*dx+(y-b)*dy)/norm)) if norm else 0
            best=min(best,math.hypot(x-a-t*dx,y-b-t*dy))
        return best
    ctes=[distance(s['state_6'][0],s['state_6'][1]) for s in states if s['valid']]
    speeds=[math.hypot(s['state_6'][3],s['state_6'][4]) for s in states if s['valid']]
    intervals=[(b['left_publish_start_steady_ns']-a['left_publish_start_steady_ns'])/1e6 for a,b in zip(actions,actions[1:])]
    context=json.loads((exp/'run_context_f2_reconciled.json').read_text());session=json.loads((exp/'source/session_summary.json').read_text())
    metrics={'run_id':run,'source_record_window_wall_s':(session['end_steady_ns']-session['start_steady_ns'])/1e9,
        'state_odom_sim_coverage_s':(states[-1]['odom_stamp_ns']-states[0]['odom_stamp_ns'])/1e9,
        'state_count':len(states),'applied_count':len(actions),'cycle_count':len(cycles),
        'cte_m':c.distribution(ctes),'cte_rmse_m':math.sqrt(sum(v*v for v in ctes)/len(ctes)),
        'body_speed_m_s':c.distribution(speeds),'publisher_wall_interval_ms':c.distribution(intervals),
        'controller_cpu_seconds':context['controller_cpu_seconds'],'controller_cpu_one_core_percent':context['controller_cpu_one_core_percent'],
        'controller_mixed_cycles':sum(p['state_kind']=='controller_mixed' for p in cycles),
        'odom_atomic_cycles':sum(p['state_kind']=='odom_atomic' for p in cycles),
        'queue_dropped_total':session['queue_dropped_total'],'source_sensor_precallback_loss_fraction':None,
        'raw_bag_bytes':sum(p.stat().st_size for p in bag.iterdir() if p.is_file()),
        'bag_sha256':before,'original_bag_unchanged':before==c.hash_bag(bag),
        'trajectory_scope':'descriptive single pilot; distance to actual last path with >=2 poses; all nonempty static paths checked equal',
        'path_message_count':len(paths),'path_with_segments_count':len(valid_paths),'empty_or_single_point_path_count':len(paths)-len(valid_paths),
        'control_source_counts':{p['control_source']:sum(q['control_source']==p['control_source'] for q in actions) for p in actions},
        'cpu_scope':'one process, all threads / one-core equivalent; 60wallsecond recording'}
    if not metrics['original_bag_unchanged']:raise RuntimeError('raw bag changed')
    if not all(math.isfinite(v) for v in ctes+speeds):raise RuntimeError('nonfinite metrics')
    target=exp/'trajectory_metrics.json';assert not target.exists();target.write_text(json.dumps(metrics,indent=2)+'\n')
    result.append({**metrics,'timing':json.loads((exp/'reports_final/timing_report.json').read_text())})
out=ROOT/'.sgh-research/experiments/p0_contract_implementation_20261004/pilots_summary.json';assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
print('PILOT_METRICS_COMPLETE')
