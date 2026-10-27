import copy,json,os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import owned_release as m

class OwnedRelease(unittest.TestCase):
    def setUp(self):
        base=os.environ.get('P1_BRANCH_TEST_OUTPUT')
        if base:
            self.root=Path(base).absolute()/self._testMethodName
            self.root.mkdir(parents=True,exist_ok=False)  # retain case evidence
        else:
            self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
            self.root=Path(self.tmp.name).absolute()
        self.owned=dict(pid=100,start_ticks=20,pgid=100,sid=100,exe='/usr/bin/test',exe_sha256='a'*64)
        self.actual=dict(self.owned,boot_id='boot',argv=['/usr/bin/test'])
        self.params={'run_id':'test','contract_hash':'b'*64}
        self.argv=['/usr/bin/test','--ros-args','-p','run_id:=test','-p','contract_hash:='+'b'*64,
                   '-p','test_delay_ms:=0','-p','test_native_block_ms:=0']
        self.graph={'observed_ns':100,'topics':{topic:{'publishers':[{'node':'/pub','gid':[1],'type':'std_msgs/msg/Float64'}],
                     'subscriptions':[{'node':'/recorder','gid':[2],'type':'std_msgs/msg/Float64'}]} for topic in ('/left','/right')}}
    def test_explicit_worker_zero_hooks(self):
        self.assertEqual(m.explicit_parameters(self.argv,self.params,('test_delay_ms','test_native_block_ms'))['test_delay_ms'],'0')
    def test_implicit_hook_default_rejected(self):
        with self.assertRaisesRegex(ValueError,'explicitly integer zero'):
            m.explicit_parameters(self.argv[:-2],self.params,('test_delay_ms','test_native_block_ms'))
    def test_nonzero_negative_float_and_text_hooks_rejected(self):
        for value in ('1','-1','0.0','"0"','false'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                m.explicit_parameters(self.argv[:-1]+['test_native_block_ms:='+value],self.params,('test_delay_ms','test_native_block_ms'))
    def test_duplicate_override_and_parameter_file_rejected(self):
        for extra in (['-p','test_delay_ms:=0'],['--params-file','fake.yaml'],['-p','p1_solver_worker:test_delay_ms:=0']):
            with self.subTest(extra=extra),self.assertRaises(ValueError):
                m.explicit_parameters(self.argv+extra,self.params,('test_delay_ms','test_native_block_ms'))
    def test_wrongrun_rejected(self):
        values=self.argv.copy();values[3]='run_id:=foreign'
        with self.assertRaisesRegex(ValueError,'parameter mismatch'):
            m.explicit_parameters(values,self.params,('test_delay_ms','test_native_block_ms'))
    def test_owned_boot_pid_reuse_exe_and_group_rejected(self):
        for key,value in [('boot_id','other'),('start_ticks',21),('exe_sha256','b'*64),('pgid',99),('sid',99)]:
            actual=dict(self.actual,**{key:value})
            with self.subTest(key=key),patch.object(m,'actual_process',return_value=actual),self.assertRaises(ValueError):
                m.authenticate_owned(self.owned,'boot')
    def test_owned_expected_record_accepts(self):
        with patch.object(m,'actual_process',return_value=self.actual):
            self.assertEqual(m.authenticate_owned(self.owned,'boot'),self.actual)
    def test_unique_dual_publisher_and_subscriber_accept(self):
        self.assertTrue(m.verify_graph(self.graph,('/left','/right'),'/pub',{'/left':['/recorder']},110,100))
    def test_missing_or_duplicated_physical_owner_rejected(self):
        for rows in ([],[{'node':'/foreign','gid':[1]}],[{'node':'/pub','gid':[1]},{'node':'/pub','gid':[3]}]):
            graph=copy.deepcopy(self.graph);graph['topics']['/left']['publishers']=rows
            with self.subTest(rows=rows),self.assertRaises(ValueError):
                m.verify_graph(graph,('/left','/right'),'/pub',{},110,100)
    def test_missing_or_ambiguous_subscription_rejected(self):
        for rows in ([],[{'node':'/recorder','gid':[0]}],[{'node':'/recorder','gid':[2]}]*2):
            graph=copy.deepcopy(self.graph);graph['topics']['/right']['subscriptions']=rows
            with self.subTest(rows=rows),self.assertRaises(ValueError):
                m.verify_graph(graph,('/left','/right'),'/pub',{'/right':['/recorder']},110,100)
    def test_future_stale_graph_rejected(self):
        for now in (90,201):
            with self.subTest(now=now),self.assertRaises(ValueError):
                m.verify_graph(self.graph,('/left','/right'),'/pub',{},now,100)
    def test_empty_population_and_wrong_topic_type_rejected(self):
        with self.assertRaisesRegex(ValueError,'nonempty'):
            m.verify_graph(self.graph,('/left','/right'),'/pub',{},110,100)
        for kind in ('publishers','subscriptions'):
            graph=copy.deepcopy(self.graph);graph['topics']['/left'][kind][0]['type']='std_msgs/msg/String'
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'type mismatch'):
                m.verify_graph(graph,('/left','/right'),'/pub',{'/left':['/recorder']},110,100)
    def test_atomic_file_duplicate_no_overwrite(self):
        path=self.root/'fresh.json';h=m.create_only_json(path,{'a':1});before=path.read_bytes()
        self.assertEqual(h,m.digest(before))
        with self.assertRaises(FileExistsError):m.create_only_json(path,{'a':2})
        self.assertEqual(path.read_bytes(),before)
    def test_duplicate_json_nonfinite_and_budget_rejected(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b' '*65537):
            with self.subTest(raw=raw[:40]),self.assertRaises(ValueError):m.strict_json(raw)
    def test_no_release_on_preparation_expiry(self):
        release=self.root/'release.json'
        with self.assertRaisesRegex(ValueError,'prepare deadline'):
            m.authorize_release(manifest_path=self.root/'missing',publisher_owned={},worker_owned={},observer_owned={},recorder_owned={},
                boot='boot',startup_pins={},worker_parameters={},observer_parameters={},node=None,physical_topics=('/left','/right'),
                publisher_node='/pub',required_subscriptions={},evidence_path=self.root/'evidence',release_path=release,
                preparation_start_ns=time.monotonic_ns()-2_000_000_000,preparation_budget_ns=1)
        self.assertFalse(release.exists())
    def startup(self):
        return dict(schema_version='p1-D1-publisher-startup-v1',derived_publisher=True,
                    run_id='run',producer_instance_id='run:100',pid=100,process_start_ticks=20,
                    binary_sha256='a'*64,boot_id='boot',steady_clock_domain='boot:steady_clock',
                    created_steady_ns=time.monotonic_ns()-1000,config_hash='b'*64)
    def test_manifest_self_reported_pid_does_not_authenticate_author(self):
        for key,value in [('pid',101),('process_start_ticks',21),('binary_sha256','c'*64),
                          ('boot_id','other'),('steady_clock_domain','foreign:steady_clock'),
                          ('created_steady_ns',time.monotonic_ns()+10_000_000_000),('config_hash','c'*64),
                          ('producer_instance_id','foreign:100')]:
            data=self.startup();data[key]=value;path=self.root/(key+'.json');m.create_only_json(path,data)
            with self.subTest(key=key),patch.object(m,'actual_process',return_value=self.actual),self.assertRaises(ValueError):
                m.authenticate_startup(path,self.owned,'boot',{'run_id':'run','config_hash':'b'*64})
    def test_manifest_owned_author_and_registered_pins_accept(self):
        path=self.root/'startup.json';m.create_only_json(path,self.startup())
        with patch.object(m,'actual_process',return_value=self.actual):
            evidence=m.authenticate_startup(path,self.owned,'boot',{'run_id':'run','config_hash':'b'*64})
        self.assertEqual(evidence['manifest_sha256'],m.digest(path.read_bytes()))
        self.assertEqual(evidence['observed']['start_ticks'],self.owned['start_ticks'])
    def test_production_release_refused_despite_named_graph_and_alive_processes(self):
        graph=copy.deepcopy(self.graph);graph['observed_ns']=time.monotonic_ns()
        release=self.root/'release.json';evidence=self.root/'evidence.json'
        with patch.object(m,'authenticate_owned',return_value=self.actual),patch.object(m,'authenticate_startup',return_value={'manifest':self.startup()}),\
             patch.object(m,'explicit_parameters',return_value={}),patch.object(m,'live_graph',return_value=graph),\
             self.assertRaisesRegex(ValueError,'production release disabled'):
            m.authorize_release(manifest_path=self.root/'startup.json',publisher_owned=self.owned,worker_owned=self.owned,
                observer_owned=self.owned,recorder_owned=self.owned,boot='boot',startup_pins={},worker_parameters={},observer_parameters={},
                node=None,physical_topics=('/left','/right'),publisher_node='/pub',required_subscriptions={'/left':['/recorder']},
                evidence_path=evidence,release_path=release,preparation_start_ns=time.monotonic_ns(),preparation_budget_ns=1_000_000_000)
        self.assertFalse(release.exists());self.assertFalse(evidence.exists())
    @unittest.skipUnless(os.name=='posix','POSIX directory fsync boundary')
    def test_post_link_durability_error_is_ambiguous_visible_not_absent(self):
        path=self.root/'ambiguous.json'
        with patch.object(m.os,'fsync',side_effect=[None,OSError('injected directory fsync failure')]):
            with self.assertRaises(m.PublicationAmbiguousError) as error:m.create_only_json(path,{'a':1})
        self.assertTrue(path.is_file());self.assertTrue(error.exception.target_visible)
        self.assertEqual(error.exception.content_sha256,m.digest(path.read_bytes()))
    @unittest.skipUnless(os.name=='posix','POSIX FIFO boundary')
    def test_fifo_rejected_without_blocking_before_stat(self):
        path=self.root/'fifo';os.mkfifo(path)
        start=time.monotonic()
        with self.assertRaisesRegex(ValueError,'regular file'):m.read_regular(path)
        self.assertLess(time.monotonic()-start,.5)
    def test_symlink_root_rejected_before_resolution(self):
        target=self.root/'target';target.write_text('{}');link=self.root/'link'
        try:link.symlink_to(target)
        except OSError:self.skipTest('requires symlink privilege; actual Linux batch required')
        with self.assertRaisesRegex(ValueError,'symlink'):m.read_regular(link)

class LinuxOwnedActual(unittest.TestCase):
    @unittest.skipUnless(os.name=='posix','actual /proc test is Linux only')
    def test_actual_process_identity_and_pid_reuse_refusal(self):
        import subprocess
        p=subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(5)'],start_new_session=True)
        try:
            actual=m.actual_process(p.pid);owned={key:actual[key] for key in m.OWN_KEYS}
            self.assertEqual(m.authenticate_owned(owned,actual['boot_id'])['pid'],p.pid)
            wrong=dict(owned,start_ticks=owned['start_ticks']+1)
            with self.assertRaisesRegex(ValueError,'PID reused'):m.authenticate_owned(wrong,actual['boot_id'])
        finally:
            # Test owns this Popen child; do not search/kill other processes.
            p.terminate();p.wait(timeout=2)

    @unittest.skipUnless(os.name=='posix','actual isolated ROS graph test is Linux only')
    def test_actual_isolated_graph_collector_and_dual_owner_gate(self):
        import rclpy
        from rclpy.context import Context
        from rclpy.node import Node
        from std_msgs.msg import Float64
        context=Context();rclpy.init(context=context)
        publisher=Node('handshake_component_publisher',context=context)
        subscriber=Node('handshake_component_recorder',context=context)
        topics=('/p1_handshake_component/left','/p1_handshake_component/right')
        pubs=[publisher.create_publisher(Float64,topic,10) for topic in topics]
        subs=[subscriber.create_subscription(Float64,topic,lambda msg:None,10) for topic in topics]
        try:
            end=time.monotonic()+4
            while True:
                graph=m.live_graph(subscriber,topics,{t:['/handshake_component_recorder'] for t in topics})
                try:
                    m.verify_graph(graph,topics,'/handshake_component_publisher',
                        {t:['/handshake_component_recorder'] for t in topics},time.monotonic_ns(),1_000_000_000)
                    break
                except ValueError:
                    if time.monotonic()>end:raise
                    rclpy.spin_once(subscriber,timeout_sec=.05)
            self.assertTrue(all(len(graph['topics'][t]['publishers'])==1 for t in topics))
        finally:
            subscriber.destroy_node();publisher.destroy_node();rclpy.shutdown(context=context)

if __name__=='__main__':unittest.main()
