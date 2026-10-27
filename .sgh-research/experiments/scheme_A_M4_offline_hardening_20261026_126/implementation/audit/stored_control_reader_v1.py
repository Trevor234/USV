"""Read a closed SQLite rosbag using its full installed ROS types; no rclpy.init."""
from pathlib import Path
import hashlib
import json
import numbers
import sqlite3
import sys


def plain(value):
    if hasattr(value, 'get_fields_and_field_types'):
        return {name: plain(getattr(value, name)) for name in value.get_fields_and_field_types()}
    if hasattr(value, 'tolist'):
        return plain(value.tolist())
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value)
    raise TypeError(type(value).__name__)


def read_stored(run):
    from rclpy.serialization import deserialize_message, serialize_message
    from usv_research_interfaces.msg import SolveJob, SolveCandidate, ExecutionDecision, AppliedControl
    classes = {'SolveJob': SolveJob, 'SolveCandidate': SolveCandidate,
               'ExecutionDecision': ExecutionDecision, 'AppliedControl': AppliedControl}
    run = Path(run)
    databases = sorted((run / 'recorder/bag').glob('*.db3'))
    if not databases:
        raise FileNotFoundError('closed SQLite bag missing')
    records = {name: [] for name in classes}
    for db in databases:
        conn = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
        try:
            assert conn.execute('pragma integrity_check').fetchone()[0] == 'ok'
            for topic_id, topic, typename in conn.execute('select id,name,type from topics'):
                name = typename.rsplit('/', 1)[-1]
                if name not in classes:
                    continue
                for timestamp, data in conn.execute('select timestamp,data from messages where topic_id=? order by id', (topic_id,)):
                    msg = deserialize_message(data, classes[name])
                    typed = serialize_message(msg)
                    records[name].append({'topic': topic, 'timestamp': timestamp, 'data': plain(msg),
                                          'cdr_sha256': hashlib.sha256(data).hexdigest(), 'cdr_bytes': len(data),
                                          'typed_serialization_bytes': len(typed),
                                          'trailing_padding_bytes': len(data) - len(typed),
                                          'trailing_padding_zero': not any(data[len(typed):])})
        finally:
            conn.close()
    identities = {}
    for name, module in list(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        if filename and (name.startswith('usv_research_interfaces') or name in ('rclpy.serialization', 'rclpy._rclpy_pybind11')):
            path = Path(filename)
            if path.is_file():
                raw = path.read_bytes()
                identities[str(path)] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    package = Path('/home/trevor/USV/usv_mpc_ws/install/usv_research_interfaces')
    for path in sorted((package / 'lib').glob('*.so')):
        raw = path.read_bytes()
        identities[str(path)] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return {'records': records, 'full_fields': {n: list(c.get_fields_and_field_types()) for n, c in classes.items()},
            'type_support_identity': identities, 'ROS_initialized': False}


if __name__ == '__main__':
    result = read_stored(Path(sys.argv[1]).resolve())
    with Path(sys.argv[2]).open('x') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'populations': {n: len(v) for n, v in result['records'].items()},
                      'full_field_counts': {n: len(v) for n, v in result['full_fields'].items()},
                      'type_support_files': len(result['type_support_identity']), 'ROS_initialized': False}))
