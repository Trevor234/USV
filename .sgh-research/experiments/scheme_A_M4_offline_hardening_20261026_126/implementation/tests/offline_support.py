"""Create-only evidence utilities for batch 126 offline checks; starts no ROS graph."""
from pathlib import Path
import hashlib
import json
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
QUALIFICATION = {key: False for key in ('M4', 'F6', 'P1', 'plant', 'hard_realtime')}


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


class Evidence:
    def __init__(self, step, output):
        self.step = step
        self.out = Path(output).resolve()
        self.out.relative_to(ROOT / 'evidence')
        self.out.mkdir(parents=True, exist_ok=False)
        self.checks, self.commands = [], []

    def check(self, name, ok, detail=None):
        if type(ok) is not bool:
            raise TypeError('check result must be a bool')
        self.checks.append({'name': name, 'passed': ok, 'detail': detail})
        print(('PASS ' if ok else 'FAIL ') + name, flush=True)
        return ok

    def command(self, name, argv, timeout=300, env=None):
        before = time.monotonic()
        result = subprocess.run([str(x) for x in argv], capture_output=True, text=True,
                                cwd=ROOT, timeout=timeout, env=env)
        number = len(self.commands)
        stdout = self.out / f'{number:02d}_{name}.stdout'
        stderr = self.out / f'{number:02d}_{name}.stderr'
        stdout.write_text(result.stdout)
        stderr.write_text(result.stderr)
        self.commands.append({'name': name, 'argv': [str(x) for x in argv], 'cwd': str(ROOT),
                              'returncode': result.returncode, 'seconds': time.monotonic() - before,
                              'timeout_seconds': timeout, 'stdout': str(stdout), 'stderr': str(stderr)})
        return result

    def finish(self, **facts):
        failures = [check for check in self.checks if not check['passed']]
        result = {'schema': 'batch126-offline-verification-v2', 'step': self.step,
                  'status': 'FAIL_STOP' if failures else 'PASS', 'checks': self.checks,
                  'failures': failures, 'observed_facts': facts,
                  'run_accepted': {'accepted': not failures, 'scope': 'this offline suite only'},
                  'qualification': QUALIFICATION, 'ROS_initialized': False, 'owned_runs': 0}
        save(self.out / 'commands.json', self.commands)
        save(self.out / 'verification.json', result)
        print(json.dumps({'step': self.step, 'status': result['status'],
                          'checks': len(self.checks), 'failures': len(failures)}, ensure_ascii=False), flush=True)
        return result
