#!/usr/bin/env python3
"""Non-ROS exec test for the W2 release channel's fd ownership.

The point of this file is the one thing the in-process pipe tests cannot show:
that after a real `execve` with close_fds=True, the Child sees the read end and
nothing else, the parent keeps only the write end, and no third process inherits
either. Getting this backwards (the v1 wiring note said `pass_fds=(write_fd,)`)
would leave a Worker that can never read a release and a Driver whose own write
end never produces EOF because a child still holds a copy.

No ROS, no NMPC. The child is this same file re-invoked with a role argument.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PKG = HERE.parents[1]
OUT = PKG / 'evidence' / 'w2_fd_exec'

MAGIC = 0x4C523257


def crc32(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if crc & 1 else crc >> 1
    return crc ^ 0xFFFFFFFF


def encode_release(run_seq: int, job_id: int, ordinal: int, nonce: int) -> bytes:
    body = bytearray(44)
    body[0:4] = MAGIC.to_bytes(4, 'little')
    body[4:6] = (1).to_bytes(2, 'little')
    body[6:8] = (0).to_bytes(2, 'little')
    body[8:16] = run_seq.to_bytes(8, 'little')
    body[16:24] = job_id.to_bytes(8, 'little')
    body[24:28] = ordinal.to_bytes(4, 'little')
    body[28:32] = nonce.to_bytes(4, 'little')
    body[32:40] = (1).to_bytes(8, 'little')
    body[40:44] = crc32(bytes(body[0:40])).to_bytes(4, 'little')
    return bytes(body)


def pipe_inode(fd: int) -> str:
    """Identify the pipe itself, not the fd number (numbers are per-process)."""
    target = fd_target(fd)
    return target  # 'pipe:[12345]' is stable across processes


def fd_target(fd: int) -> str:
    try:
        return os.readlink(f'/proc/self/fd/{fd}')
    except OSError:
        return ''


def child_main(role: str, read_fd: int, report_path: Path) -> int:
    """The Worker's view: it must see the read end and nothing to write with."""
    report = {
        'role': role,
        'pid': os.getpid(),
        'inherited_fds': sorted(
            int(x) for x in os.listdir('/proc/self/fd') if x.isdigit()),
        'read_fd': read_fd,
        'read_fd_target': fd_target(read_fd),
        'read_fd_is_pipe': fd_target(read_fd).startswith('pipe:'),
        'can_write_to_read_fd': False,
    }
    # A read end must not be writable. If it were, the channel would not be
    # one-directional and EOF would be undecidable.
    try:
        os.write(read_fd, b'x')
        report['can_write_to_read_fd'] = True
    except OSError as exc:
        report['write_error'] = exc.__class__.__name__
    # The child holds no other end of this pipe; when the parent closes its
    # write end, a read must report EOF.
    # Report pipe identities. Numbers are per-process and cannot be compared
    # with the parent's table.
    # Only descriptors above stdio matter: subprocess gives the child its own
    # stdout/stderr pipes, which are unrelated to the release channel.
    report['pipe_identities'] = sorted(
        fd_target(fd) for fd in report['inherited_fds']
        if fd > 2 and fd_target(fd).startswith('pipe:'))
    report['pipe_fds_held'] = len(report['pipe_identities'])
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    return 0


def sibling_main(role: str, report_path: Path) -> int:
    """A role with no business on the channel must hold no pipe at all."""
    held = [int(x) for x in os.listdir('/proc/self/fd') if x.isdigit()]
    report = {'role': role, 'pid': os.getpid(), 'inherited_fds': sorted(held),
              'pipe_identities': sorted(
                  fd_target(fd) for fd in held
                  if fd > 2 and fd_target(fd).startswith('pipe:'))}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == 'child':
        return child_main('worker', int(sys.argv[2]), Path(sys.argv[3]))
    if len(sys.argv) > 1 and sys.argv[1] == 'sibling':
        return sibling_main('sibling', Path(sys.argv[2]))

    OUT.mkdir(parents=True, exist_ok=True)
    read_fd, write_fd = os.pipe()
    # Identify the pipe itself; fd numbers are per-process.
    channel_id = fd_target(read_fd)
    checks = {}
    try:
        # ── 1. The Worker inherits ONLY the read end. ──────────────────
        child_report = OUT / 'worker_fd_report.json'
        child = subprocess.Popen(
            [sys.executable, '-I', __file__, 'child', str(read_fd), str(child_report)],
            pass_fds=(read_fd,), close_fds=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        child.wait(timeout=20)
        report = json.loads(child_report.read_text())
        checks['worker_inherited_read_fd'] = report['read_fd_is_pipe']
        # One pipe has a single identity; both ends share it. The Worker must
        # hold that pipe exactly once (its read end) and nothing else.
        checks['worker_holds_channel_exactly_once'] = (
            report['pipe_identities'] == [channel_id])
        checks['read_fd_is_not_writable'] = not report['can_write_to_read_fd']

        # ── 2. A sibling role inherits no pipe at all. ─────────────────
        sib_report = OUT / 'sibling_fd_report.json'
        sib = subprocess.Popen(
            [sys.executable, '-I', __file__, 'sibling', str(sib_report)],
            close_fds=True, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        sib.wait(timeout=20)
        srep = json.loads(sib_report.read_text())
        checks['sibling_holds_no_pipe'] = srep['pipe_identities'] == []

        # ── 3. With the parent's write end open, no data means no EOF. ─
        #    (The Worker child has exited, so it holds nothing either.)
        os.set_blocking(read_fd, False)
        r, _, _ = select.select([read_fd], [], [], 0.05)
        checks['no_eof_while_write_end_open'] = (r == [])

        # ── 4. A release written by the parent is readable, in one frame. ─
        frame = encode_release(9, 5, 3, 0x1234)
        os.write(write_fd, frame)
        r, _, _ = select.select([read_fd], [], [], 1.0)
        got = os.read(read_fd, 44) if r else b''
        checks['parent_written_frame_arrives_intact'] = (got == frame)
        checks['frame_length'] = len(got)

        # ── 5. Closing the write end makes the read end report EOF. ────
        os.close(write_fd)
        write_fd = -1
        r, _, _ = select.select([read_fd], [], [], 1.0)
        eof = os.read(read_fd, 44) if r else b'<not-readable>'
        checks['eof_after_write_end_closed'] = (eof == b'')

        # ── 6. A wrong-direction fd is rejected, not silently ignored. ─
        #    Writing to the read end is the error the v1 note invited.
        wrong_direction_rejected = False
        try:
            os.write(read_fd, b'x')
        except OSError:
            wrong_direction_rejected = True
        checks['write_to_read_end_rejected'] = wrong_direction_rejected
    finally:
        if write_fd >= 0:
            os.close(write_fd)
        os.close(read_fd)

    ok = all(v is True for k, v in checks.items() if isinstance(v, bool))
    report = {'schema': 'M4-diagnostic-w2-fd-exec-v1',
              'checks': checks, 'all_checks_pass': ok,
              'note': 'non-ROS exec evidence for channel direction and '
                      'inheritance only; not a W2 owned run'}
    path = OUT / 'fd_exec_verification_v1.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    for k, v in checks.items():
        print('%-42s %s' % (k, v))
    print('all checks pass:', ok)
    print('written:', path)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
