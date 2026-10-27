"""Finite diagnostic raw observers and send ledger; never a physical publisher."""
from pathlib import Path
import hashlib,json,time

def sha(blob): return hashlib.sha256(blob).hexdigest()

class CdrIngress:
    def __init__(self,node,directory,run_id):
        from rclpy.qos import QoSProfile,ReliabilityPolicy
        from rclpy.serialization import serialize_message
        from usv_research_interfaces.msg import SolveJob,SolveCandidate
        self.node=node;self.directory=directory;self.run_id=run_id
        self.raw=(directory/'cdr_raw_observer.jsonl').open('x')
        self.sent=(directory/'cdr_send_ledger.jsonl').open('x')
        self.sequence=0;self.index=0;self.plan=[];self.closed=False
        self.blobs=directory/'cdr_injected_blobs';self.blobs.mkdir(exist_ok=False)
        self.publishers={};qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE)
        for topic,kind in (('/p1/solve_job',SolveJob),('/p1/solve_candidate',SolveCandidate)):
            self.publishers[topic]=node.create_publisher(kind,topic,qos)
            for stage in ('before','empty','header3','tail_minus1','after'):
                i=len(self.plan);m=kind();j=m if kind is SolveJob else m.job
                j.schema_version='p1-solve-job-v1';j.run_id='foreign_cdr_'+run_id
                j.job_id=900001+i
                if kind is SolveCandidate:m.backend='acados';m.worker_instance='foreign_cdr'
                valid=serialize_message(m)
                blob={'before':valid,'after':valid,'empty':b'','header3':valid[:3],'tail_minus1':valid[:-1]}[stage]
                name=f'{i:02d}_{stage}.cdr';(self.blobs/name).write_bytes(blob)
                self.plan.append({'case_index':i,'topic':topic,'stage':stage,'job_id':j.job_id,'blob':name,'bytes':len(blob),'sha256':sha(blob),'valid_control':stage in ('before','after'),'offset_ns':1_000_000_000+i*400_000_000})
        (directory/'cdr_injection_plan.json').write_text(json.dumps({'schema':'p1-cdr-plan-v1','run_id':run_id,'cases':self.plan,'sample_count':10,'observer_depth':64,'production_reader_depth':1,'actual_plant':False,'physical_endpoints':0},indent=2)+'\n')

    def callback(self,topic,kind,handler):
        from rclpy.serialization import deserialize_message
        def receive(blob):
            self.sequence+=1;blob=bytes(blob);item={'sequence':self.sequence,'topic':topic,'receive_ns':time.monotonic_ns(),'bytes':len(blob),'sha256':sha(blob)}
            message=None
            try:
                message=deserialize_message(blob,kind);j=message if topic.endswith('solve_job') else message.job
                item.update(decoded=True,job_id=j.job_id,run_id=j.run_id)
            except Exception as e:item.update(decoded=False,exception_type=type(e).__name__,exception=str(e)[:1024])
            self.raw.write(json.dumps(item,sort_keys=True)+'\n');self.raw.flush()
            if message is not None:handler(message)
        return receive

    def advance(self,now,started):
        if self.index>=len(self.plan):return
        item=self.plan[self.index]
        if now-started<item['offset_ns']:return
        blob=(self.blobs/item['blob']).read_bytes()
        if len(blob)!=item['bytes'] or sha(blob)!=item['sha256']:raise RuntimeError('fixed CDR blob changed')
        info=self.node.get_subscriptions_info_by_topic(item['topic'])
        record={**item,'attempt_ns':time.monotonic_ns(),'matched_count':self.publishers[item['topic']].get_subscription_count(),'subscriber_names':[e.node_name for e in info]}
        target='p1_solver_worker' if item['topic'].endswith('solve_job') else 'p1_regulator'
        if record['matched_count']<3 or not {target,'p1_calibration_driver'}.issubset(record['subscriber_names']) or not any('recorder' in v for v in record['subscriber_names']):raise RuntimeError('raw test writer has not matched declared observers and target')
        try:self.publishers[item['topic']].publish(blob);record.update(api_returned=True)
        except Exception as e:record.update(api_returned=False,exception_type=type(e).__name__,exception=str(e)[:1024])
        record['return_ns']=time.monotonic_ns();self.sent.write(json.dumps(record,sort_keys=True)+'\n');self.sent.flush();self.index+=1

    def close(self):
        if self.closed:return
        self.raw.flush();self.sent.flush();self.raw.close();self.sent.close();self.closed=True
