"""Independent process raw receive/storage witness. No publisher is constructed."""
from pathlib import Path
import argparse,hashlib,json,os,signal,time
import rclpy
from rclpy.qos import QoSProfile,ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from rclpy.serialization import deserialize_message
from usv_research_interfaces.msg import SolveJob,SolveCandidate

stop=False
def stopping(_s,_f):
    global stop
    stop=True

def main(directory):
    rclpy.init(args=[],signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGINT,stopping);signal.signal(signal.SIGTERM,stopping)
    node=rclpy.create_node('p1_cdr_raw_observer');blobs=directory/'cdr_external_blobs';blobs.mkdir(exist_ok=False)
    source=(directory/'cdr_external_observer.jsonl').open('x');count=0;error=None
    def emit(item):source.write(json.dumps(item,sort_keys=True)+'\n');source.flush()
    emit({'type':'startup','schema':'p1-cdr-external-v1','pid':os.getpid(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'node_name':'p1_cdr_raw_observer','monotonic_ns':time.monotonic_ns(),'physical_publishers_created':0})
    def callback(topic,kind):
        def receive(raw):
            nonlocal count
            count+=1;blob=bytes(raw);name=f'{count:06d}.cdr'
            with (blobs/name).open('xb') as f:f.write(blob)
            row={'type':'raw','sequence':count,'topic':topic,'receive_ns':time.monotonic_ns(),'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),'blob':name}
            try:
                m=deserialize_message(blob,kind);j=m if topic.endswith('solve_job') else m.job;row.update(decoded=True,job_id=j.job_id,run_id=j.run_id)
            except Exception as e:row.update(decoded=False,exception_type=type(e).__name__,exception=str(e)[:1024])
            emit(row)
        return receive
    qos=QoSProfile(depth=64,reliability=ReliabilityPolicy.RELIABLE)
    node.create_subscription(SolveJob,'/p1/solve_job',callback('/p1/solve_job',SolveJob),qos,raw=True)
    node.create_subscription(SolveCandidate,'/p1/solve_candidate',callback('/p1/solve_candidate',SolveCandidate),qos,raw=True)
    try:
        graph_deadline=time.monotonic()+5
        infos={}
        while time.monotonic()<graph_deadline and not stop:
            rclpy.spin_once(node,timeout_sec=.02)
            infos={topic:[{'node_name':v.node_name,'endpoint_gid':[int(x) for x in v.endpoint_gid],'topic_type':v.topic_type} for v in node.get_subscriptions_info_by_topic(topic) if v.node_name=='p1_cdr_raw_observer'] for topic in ('/p1/solve_job','/p1/solve_candidate')}
            if all(infos.values()):break
        if not all(infos.values()):raise RuntimeError('external raw subscriptions did not discover self')
        emit({'type':'endpoint_inventory','pid':os.getpid(),'subscriptions':infos,'monotonic_ns':time.monotonic_ns()})
        while not stop:rclpy.spin_once(node,timeout_sec=.02)
        end=time.monotonic()+.3
        while time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.01)
    except BaseException as e:error=repr(e)
    finally:
        emit({'type':'summary','schema':'p1-cdr-external-v1','pid':os.getpid(),'received_count':count,'normal_source_complete':error is None,'error':error,'finished_ns':time.monotonic_ns()});source.close();node.destroy_node();rclpy.shutdown()
    return 1 if error else 0

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);raise SystemExit(main(p.parse_args().directory))
