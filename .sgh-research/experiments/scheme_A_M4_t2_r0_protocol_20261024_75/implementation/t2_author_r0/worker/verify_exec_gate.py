#!/usr/bin/env python3
"""Live exec pipe receiver verification. No ROS, native solver, or old writes."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]          # the 59 package
HEADERS = Path(__file__).resolve().parent            # worker/, holds the v2 headers
BIN = Path('/tmp/w2_exec_gate_receiver')
OUT = ROOT / 'evidence' / 'live_exec_gate'


def handles(device, inode):
    result = []
    for name in os.listdir('/proc/self/fd'):
        try:
            fd = int(name)
            st = os.fstat(fd)
            if (st.st_dev, st.st_ino) == (device, inode):
                result.append({'fd': fd, 'mode': fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE})
        except (ValueError, OSError):
            pass
    return result


def read_row(child):
    ready, _, _ = select.select([child.stdout], [], [], 4)
    assert ready, 'receiver output timeout'
    raw = child.stdout.readline()
    assert raw, 'receiver exited without a report'
    return json.loads(raw)


def case(mode, frame):
    r, w = os.pipe()
    st = os.fstat(r)
    child = None
    try:
        child = subprocess.Popen(
            [str(BIN), str(r), mode, str(st.st_dev), str(st.st_ino)],
            pass_fds=(r,), close_fds=True, start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True)
        os.close(r)
        r = -1
        parent_handles = handles(st.st_dev, st.st_ino)
        assert len(parent_handles) == 1 and parent_handles[0]['mode'] == os.O_WRONLY
        ready = read_row(child)
        assert ready['event'] == 'ready' and ready['read_only'] is True
        assert ready['channel_handles'] == 1
        assert (ready['device'], ready['inode']) == (st.st_dev, st.st_ino)
        assert child.poll() is None, 'child must be alive before transport checks'
        late_write_failed = False
        if mode == 'release':
            time.sleep(.1)
            assert os.write(w, frame) == 44
        elif mode == 'eof':
            time.sleep(.1)
            os.close(w)
            w = -1
        elif mode == 'partial_eof':
            assert os.write(w, frame[:17]) == 17
            os.close(w)
            w = -1
        elif mode == 'budget':
            time.sleep(.2)
            os.kill(child.pid, signal.SIGUSR1)
            time.sleep(.2)
            assert os.write(w, frame[:22]) == 22
            time.sleep(.35)
            try:
                os.write(w, frame[22:])
            except BrokenPipeError:
                late_write_failed = True
        elif mode != 'stop':
            raise AssertionError('unknown component case')
        result = read_row(child)
        rc = child.wait(timeout=3)
        stderr = child.stderr.read()
        assert rc == 0 and not stderr, (rc, stderr)
        expected = {'release': 'released', 'eof': 'eof',
                    'partial_eof': 'partial_frame', 'stop': 'stop_requested',
                    'budget': 'partial_frame'}[mode]
        assert result['outcome'] == expected, (mode, result)
        assert result['actual_native_invoked'] is False
        if mode == 'release':
            assert result['frame_equal'] is True
        if mode == 'stop':
            assert result['stop'] is True and result['elapsed_ns'] < 500000000
        if mode == 'budget':
            assert result['elapsed_ns'] >= result['budget_ns']
            assert result['frame_equal'] is False
        return {'case': mode, 'parent_channel_handles_after_spawn': parent_handles,
                'ready': ready, 'result': result, 'exit_code': rc,
                'late_write_rejected_by_closed_receiver': late_write_failed,
                'passed': True}
    finally:
        if r >= 0:
            os.close(r)
        if w >= 0:
            os.close(w)
        if child is not None and child.poll() is None:
            child.kill()
            child.wait(timeout=3)


MAGIC = 0x4C523257


def encode_release(run_seq, job_id, ordinal, nonce):
    """Encoder kept here rather than imported, so this tool has no dependency on
    an older package's layout."""
    import zlib
    body = bytearray(44)
    body[0:4] = MAGIC.to_bytes(4, 'little')
    body[4:6] = (1).to_bytes(2, 'little')
    body[6:8] = (0).to_bytes(2, 'little')
    body[8:16] = run_seq.to_bytes(8, 'little')
    body[16:24] = job_id.to_bytes(8, 'little')
    body[24:28] = ordinal.to_bytes(4, 'little')
    body[28:32] = nonce.to_bytes(4, 'little')
    body[32:40] = (1).to_bytes(8, 'little')
    body[40:44] = (zlib.crc32(bytes(body[0:40])) & 0xFFFFFFFF).to_bytes(4, 'little')
    return bytes(body)


def build_receiver():
    """Build the receiver against the v2 headers in this tree.

    The receiver is a plain C++ program: it links the reviewed Gate/PipeReader
    and nothing else, so a failure here is about the component, not about ROS.
    """
    src = Path(__file__).resolve().parent / 'exec_gate_receiver.cpp'
    cmd = ['g++', '-std=c++17', '-O1', '-I', str(HEADERS), str(src), '-o', str(BIN)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('receiver build failed:\n' + r.stderr[-2000:])


def main():
    build_receiver()
    frame = encode_release(9, 5, 3, 0x1234)
    results = [case(mode, frame) for mode in
               ('release', 'eof', 'partial_eof', 'stop', 'budget')]
    out = {'schema': 'W2-live-exec-component-receiver-review/v1',
           'cases': results, 'all_passed': all(x['passed'] for x in results),
           'real_cpp_receiver_after_exec': True,
           'parent_read_end_closed_before_transport': True,
           'original_sources_modified': False, 'ROS_started': False,
           'owned_W2_qualified': False, 'M4_stage_qualified': False,
           'F6_qualified': False, 'P1_qualified': False}
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'live_exec_gate_verification_v1.json').open('x') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')
    print(json.dumps({'all_passed': out['all_passed'],
                      'cases': [(r['case'], r['result']['outcome'],
                                 r['result']['elapsed_ns']) for r in results]}))


if __name__ == '__main__':
    main()
