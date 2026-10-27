"""Bounded component tests; generated storage is explicitly synthetic."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from check_owned_fixture import read_actual_storage, transport_join


class ActualStorage(unittest.TestCase):
    def test_actual_sqlite_storage_decode_and_counts(self):
        import rosbag2_py
        from rclpy.serialization import serialize_message
        from std_msgs.msg import Float64
        with tempfile.TemporaryDirectory(prefix='p1-synthetic-reader-') as root:
            bag=Path(root)/'synthetic_component_bag'
            writer=rosbag2_py.SequentialWriter()
            writer.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='sqlite3'),
                        rosbag2_py.ConverterOptions(input_serialization_format='cdr',output_serialization_format='cdr'))
            writer.create_topic(rosbag2_py.TopicMetadata(id=0,name='/synthetic/component',type='std_msgs/msg/Float64',serialization_format='cdr'))
            expected=[]
            for index,value in enumerate([.0,-1.0,2.5]):
                blob=serialize_message(Float64(data=value))
                expected.append(hashlib.sha256(blob).hexdigest())
                writer.write('/synthetic/component',blob,1_000_000+index)
            writer.close()
            decoded,hashes,report=read_actual_storage(bag,{'/synthetic/component':'std_msgs/msg/Float64'})
            self.assertEqual(report['actual_counts'],{'/synthetic/component':3})
            self.assertEqual(hashes['/synthetic/component'],expected)
            self.assertEqual([r['message']['data'] for r in decoded['/synthetic/component']],[.0,-1.0,2.5])
            with self.assertRaises(ValueError):
                read_actual_storage(bag,{'/synthetic/component':'std_msgs/msg/Int32'})


class TransportSequence(unittest.TestCase):
    def setUp(self):
        self.topic='/synthetic/component'
        self.topics={self.topic:'std_msgs/msg/Float64'}
        self.gid=[1]+[0]*15
        self.manifests={'synthetic_component':{'endpoints':[{'kind':'publisher','topic':self.topic,'type':self.topics[self.topic],'gid':self.gid}]}}
        self.hashes={self.topic:['a'*64,'b'*64]}
        self.rows=[{'type':'transport_message','topic':self.topic,'ros_type':self.topics[self.topic],
                    'publisher_gid':self.gid,'payload_sha256':h} for h in self.hashes[self.topic]]

    def test_whole_sequence_matches(self):
        self.assertTrue(transport_join(self.hashes,self.rows,self.manifests,self.topics)['passed'])

    def test_same_count_reordered_payload_rejected(self):
        self.assertFalse(transport_join(self.hashes,self.rows[::-1],self.manifests,self.topics)['passed'])

    def test_same_name_foreign_publisher_gid_rejected(self):
        self.rows[0]['publisher_gid']=[2]+[0]*15
        self.assertFalse(transport_join(self.hashes,self.rows,self.manifests,self.topics)['passed'])

    def test_missing_prepare_or_terminal_message_rejected(self):
        for rows in [self.rows[:1],self.rows[1:]]:
            self.assertFalse(transport_join(self.hashes,rows,self.manifests,self.topics)['passed'])


if __name__=='__main__':
    unittest.main()
