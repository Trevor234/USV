"""Read provenance instrumentation only; enabled explicitly by C3.10 capture."""
import atexit
import builtins
import io
import hashlib
import json
import os
import stat
import subprocess
import sys

_trace = os.environ.get('C310_TRACE_DIRECTORY')
if _trace:
    _base = os.path.dirname(os.path.dirname(__file__))
    _open_fd = os.open
    _builtin_open = builtins.open
    _io_open = io.open
    _log = _open_fd(os.path.join(_trace, str(os.getpid()) + '.jsonl'),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    _seen = set()
    _busy = False

    def _emit(row):
        global _busy
        if _busy:
            return
        _busy = True
        try:
            row['pid'] = os.getpid()
            raw = (json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n').encode()
            n = os.write(_log, raw)
            if n != len(raw):
                raise RuntimeError('short provenance trace write')
        finally:
            _busy = False

    def _path(value):
        if isinstance(value, int):
            return os.readlink('/proc/self/fd/' + str(value))
        return os.fsdecode(value)

    def _file(value):
        if _busy:
            return
        try:
            path = os.path.abspath(_path(value))
            if path == _base or path.startswith(_base + '/') or path.startswith(('/proc/', '/sys/', '/dev/')):
                return
            key = ('file', path)
            if key not in _seen and stat.S_ISREG(os.stat(path, follow_symlinks=False).st_mode):
                _seen.add(key)
                _emit({'event': 'file', 'path': path})
        except (OSError, TypeError, ValueError):
            pass

    def _audit(event, args):
        if _busy:
            return
        if event == 'open':
            path = args[0]
            if isinstance(path, (str, bytes)) and os.path.isabs(path):
                flags = args[2]
                if flags is None or flags & os.O_ACCMODE != os.O_WRONLY:
                    _file(path)
        elif event == 'os.scandir':
            path = os.path.abspath(_path(args[0]))
            calibration = os.environ.get('C310_TRACE_CALIBRATION_ROOT', '')
            tracked = path.startswith(('/home/trevor/USV/.sgh-research/', '/home/trevor/MPC/')) or (calibration and (path == calibration or path.startswith(calibration + '/')))
            if tracked and not (path == _base or path.startswith(_base + '/')):
                key = ('directory', path)
                if key not in _seen:
                    _seen.add(key)
                    _emit({'event': 'directory', 'path': path})

    def _fd_open(*args, **kwargs):
        fd = _open_fd(*args, **kwargs)
        if len(args) > 1 and args[1] & os.O_ACCMODE != os.O_WRONLY:
            _file(fd)
        return fd

    def _high_open(real, *args, **kwargs):
        f = real(*args, **kwargs)
        mode = args[1] if len(args) > 1 else kwargs.get('mode', 'r')
        if 'r' in mode or '+' in mode:
            _file(f.fileno())
        return f

    def _bopen(*args, **kwargs):
        return _high_open(_builtin_open, *args, **kwargs)

    def _iopen(*args, **kwargs):
        return _high_open(_io_open, *args, **kwargs)

    _popen_init = subprocess.Popen.__init__

    def _init(self, args, *a, **kw):
        _popen_init(self, args, *a, **kw)
        argv = args if isinstance(args, (list, tuple)) else [args]
        executable = os.fsdecode(kw.get('executable') or argv[0])
        if os.path.basename(executable).startswith('python'):
            _emit({'event': 'python_child', 'child_pid': self.pid, 'argv': list(map(str, argv))})

    sys.addaudithook(_audit)
    os.open = _fd_open
    builtins.open = _bopen
    io.open = _iopen
    subprocess.Popen.__init__ = _init
    import acceptance_core_v1 as _core
    _reader_raw = _core.Reader.raw
    _verified = {}

    def _raw(self, path, *args, **kwargs):
        raw = _reader_raw(self, path, *args, **kwargs)
        path = str(path)
        digest = hashlib.sha256(raw).hexdigest()
        if path not in _verified:
            _verified[path] = digest
            _emit({'event': 'verified_read', 'path': path, 'sha256': digest, 'bytes': len(raw)})
        elif _verified[path] != digest:
            raise ValueError('traced input changed between exact Reader bytes: ' + path)
        return raw

    _core.Reader.raw = _raw
    _emit({'event': 'start', 'parent_pid': os.getppid(), 'argv': sys.argv,
           'mechanisms': ['CPython.open.audit', 'os.open.returned_fd', 'builtins.open.returned_fd',
                          'io.open.returned_fd', 'CPython.os.scandir.audit', 'Popen.python_pid',
                          'acceptance_core.Reader.raw.actual_returned_bytes']})
    atexit.register(lambda: (_emit({'event': 'end'}), os.fsync(_log), os.close(_log)))
