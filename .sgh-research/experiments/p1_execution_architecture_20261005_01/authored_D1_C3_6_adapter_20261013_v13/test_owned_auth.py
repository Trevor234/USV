"""Targeted negative checks for typed parameters and actual source FD identity."""
import math
import os
from pathlib import Path
import struct
import tempfile
import unittest
import time
from copy import deepcopy
from owned_auth import canonical_parameters, parameter_digest, source_fd_matches, verify_owned_graph


def row(kind, value):
    if kind == 3 and type(value) in (float, int):
        canonical = struct.pack('>d', value).hex()
    elif kind == 8 and type(value) is list:
        canonical = [struct.pack('>d', x).hex() for x in value]
    else:
        canonical = value
    return {'type': kind, 'value': value, 'canonical_value': canonical}


class ParameterTypes(unittest.TestCase):
    def test_all_supported_types(self):
        values = [None, False, 0, -0.0, '参数', [0, 255], [False, True], [-4, 5], [.2, -1e-8], ['x', '参数']]
        data = {str(i): row(i, value) for i, value in enumerate(values)}
        self.assertEqual(len(canonical_parameters(data)), 10)
        self.assertEqual(len(parameter_digest(data)), 64)

    def test_signed_zero_is_bound(self):
        self.assertNotEqual(parameter_digest({'x': row(3, -0.0)}), parameter_digest({'x': row(3, 0.0)}))

    def test_double_value_cannot_disagree_with_bits(self):
        data = {'x': row(3, 0.2)}
        data['x']['canonical_value'] = struct.pack('>d', 0.3).hex()
        with self.assertRaises(ValueError):
            canonical_parameters(data)

    def test_scalar_type_confusion_rejected(self):
        for kind, value in [(0, False), (1, 0), (2, False), (2, .0), (3, False), (4, 8)]:
            with self.subTest(kind=kind, value=value), self.assertRaises(ValueError):
                canonical_parameters({'x': row(kind, value)})

    def test_array_element_type_confusion_rejected(self):
        for kind, value in [(5, [True]), (5, [-1]), (5, [256]), (6, [0]), (7, [False]), (7, [1.0]), (8, [True]), (9, [5])]:
            with self.subTest(kind=kind, value=value), self.assertRaises(ValueError):
                canonical_parameters({'x': row(kind, value)})

    def test_nonfinite_double_rejected(self):
        for value in [math.inf, -math.inf, math.nan]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_parameters({'x': row(3, value)})


class SourceFd(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p1-owned-auth-')
        self.path = Path(self.temp.name) / 'source.jsonl'
        self.fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
        self.addCleanup(os.close, self.fd)
        self.addCleanup(self.temp.cleanup)
        s = os.fstat(self.fd)
        import fcntl
        flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        self.record = {'fd': self.fd, 'path': str(self.path), 'device': s.st_dev, 'inode': s.st_ino,
                       'mode': s.st_mode, 'flags': flags, 'append': bool(flags & os.O_APPEND),
                       'access_mode': flags & os.O_ACCMODE}
        self.role = {'actual': {'pid': os.getpid()}, 'manifest': {'source_fd': self.record}}

    def test_real_open_regular_source(self):
        self.assertTrue(source_fd_matches(self.role, self.path))

    def test_source_inode_mismatch_rejected(self):
        self.record['inode'] += 1
        with self.assertRaises(ValueError):
            source_fd_matches(self.role, self.path)

    def test_source_flags_mismatch_rejected(self):
        self.record['flags'] ^= os.O_APPEND
        with self.assertRaises(ValueError):
            source_fd_matches(self.role, self.path)

    def test_source_self_reported_path_mismatch_rejected(self):
        self.record['path'] += '.foreign'
        with self.assertRaises(ValueError):
            source_fd_matches(self.role, self.path)

    def test_source_fifo_rejected(self):
        fifo = Path(self.temp.name) / 'source.fifo'
        os.mkfifo(fifo, 0o600)
        fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
        self.addCleanup(os.close, fd)
        s = os.fstat(fd)
        import fcntl
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        self.role['manifest']['source_fd'] = {'fd': fd, 'path': str(fifo), 'device': s.st_dev,
            'inode': s.st_ino, 'mode': s.st_mode, 'flags': flags, 'append': False,
            'access_mode': os.O_RDWR}
        with self.assertRaises(ValueError):
            source_fd_matches(self.role, fifo)



class OwnedGraph(unittest.TestCase):
    def setUp(self):
        def e(kind, topic, typ, number):return {'kind':kind,'topic':topic,'type':typ,'gid':[number]+[0]*15}
        self.roles={'publisher':{'manifest':{'node':'/owned','endpoints':[e('publisher','/left','std_msgs/msg/Float64',1),e('publisher','/right','std_msgs/msg/Float64',2),e('subscription','/clock','rosgraph_msgs/msg/Clock',3),e('subscription','/clock','rosgraph_msgs/msg/Clock',4)]}}}
        self.graph={'observed_ns':time.monotonic_ns(),'topics':{'/left':{'publishers':[{'node':'/owned','type':'std_msgs/msg/Float64','gid':[1]+[0]*15}],'subscriptions':[]},'/right':{'publishers':[{'node':'/owned','type':'std_msgs/msg/Float64','gid':[2]+[0]*15}],'subscriptions':[]},'/clock':{'publishers':[],'subscriptions':[{'node':'/owned','type':'rosgraph_msgs/msg/Clock','gid':[v]+[0]*15} for v in [3,4]]}}}
    def test_two_actual_same_owner_clock_readers_are_distinct(self):
        self.assertTrue(verify_owned_graph(self.graph,self.roles,['/left','/right']))
    def test_name_never_authorizes_foreign_gid_or_type(self):
        for topic,kind,typ in [('/left','publishers','std_msgs/msg/Float64'),('/left','publishers','std_msgs/msg/String'),('/clock','subscriptions','rosgraph_msgs/msg/Clock')]:
            g=deepcopy(self.graph);g['topics'][topic][kind].append({'node':'/owned','type':typ,'gid':[99]+[0]*15})
            with self.subTest(topic=topic,typ=typ),self.assertRaises(ValueError):verify_owned_graph(g,self.roles,['/left','/right'])
    def test_mutated_endpoint_gid_and_stale_graph_rejected(self):
        r=deepcopy(self.roles);r['publisher']['manifest']['endpoints'][0]['gid'][0]=9
        with self.assertRaises(ValueError):verify_owned_graph(self.graph,r,['/left','/right'])
        self.graph['observed_ns']-=2_000_000_000
        with self.assertRaises(ValueError):verify_owned_graph(self.graph,self.roles,['/left','/right'])

if __name__ == '__main__':
    unittest.main()
