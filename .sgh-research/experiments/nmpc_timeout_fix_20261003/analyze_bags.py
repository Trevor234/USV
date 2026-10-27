import pathlib,json,math,collections
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

ROOT=pathlib.Path('/home/trevor/USV/.sgh-research/experiments/nmpc_timeout_fix_20261003/results')
def describe(v):
    if not v:return None
    s=sorted(v)
    return dict(n=len(v),mean=sum(v)/len(v),min=min(v),max=max(v),p95=s[min(len(s)-1,int(.95*(len(s)-1)))])
def distance(x,y,pts):
    out=[]
    for a,b in zip(pts,pts[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1];q=dx*dx+dy*dy
        t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/q)) if q else 0
        out.append(math.hypot(x-a[0]-t*dx,y-a[1]-t*dy))
    return min(out) if out else None
def analyze(name):
    bag=ROOT/name/name
    reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
    types={t.name:get_message(t.type) for t in reader.get_all_topics_and_types()}
    counts=collections.Counter();states=collections.Counter();sources=collections.Counter();path=[];odom=[];cte=[];backend=[];wall=[];fail=[];deadline=0;outputs={'left':[],'right':[]};stamp=[];interval=[];status_time=[];success=0
    while reader.has_next():
        topic,data,t=reader.read_next();counts[topic]+=1
        if topic not in ['/mpc/status','/path/reference','/wamv/sensors/position/ground_truth_odometry','/wamv/thrusters/left/thrust','/wamv/thrusters/right/thrust']:continue
        m=deserialize_message(data,types[topic])
        if topic=='/path/reference':path=[(q.pose.position.x,q.pose.position.y) for q in m.poses]
        elif topic.endswith('ground_truth_odometry'):
            x,y=m.pose.pose.position.x,m.pose.pose.position.y;odom.append((x,y));stamp.append(m.header.stamp.sec+m.header.stamp.nanosec*1e-9)
            d=distance(x,y,path)
            if d is not None:cte.append(d)
        elif topic=='/mpc/status':
            s=json.loads(m.data);states[s.get('state')]+=1
            if s.get('state')=='ACTIVE':
                success+=bool(s.get('success'));deadline+=bool(s.get('deadline_miss'));fail.append(s.get('fail_count',0));status_time.append(t*1e-9)
                for key,v in [('solve_time_ms',backend),('solve_wall_time_ms',wall)]:
                    if isinstance(s.get(key),(int,float)):v.append(s[key])
                sources[s.get('control_source','not_recorded')]+=1
        else:outputs['left' if '/left/' in topic else 'right'].append(m.data)
    interval=[b-a for a,b in zip(status_time,status_time[1:])]
    d={'case':name,'launch':json.loads((ROOT/name/'complete.json').read_text()),'topic_counts':dict(counts),'states':dict(states),'sources':dict(sources),'success_active':success,'deadline_miss':deadline,'fail_count_max':max(fail) if fail else None,'backend_ms':describe(backend),'wall_ms':describe(wall),'status_interval_seconds':describe(interval),'odom_sim_seconds':stamp[-1]-stamp[0] if stamp else None,'odom_first':odom[0] if odom else None,'odom_last':odom[-1] if odom else None,'cte_m':describe(cte),'left_N':describe(outputs['left']),'right_N':describe(outputs['right'])}
    (ROOT/name/'metrics.json').write_text(json.dumps(d,indent=2));return d
if __name__=='__main__':
    import sys
    for name in sys.argv[1:]:analyze(name)
