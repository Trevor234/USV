#!/usr/bin/env python3
"""Bounded create-only C++ validator build, compiler/header/runtime pins."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import time

D=Path(__file__).resolve().parent


def pin(path):
    path=Path(path).resolve(strict=True)
    data=path.read_bytes()
    return {'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def run():
    root=D/'build/contract_probe_attempt01';root.mkdir()
    compiler=Path(shutil.which('g++')).resolve(strict=True)
    source=D/'implementation/native/contract_probe.cpp'
    command=[str(compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-MD','-MF',str(root/'dependencies.d'),
             str(source),'-o',str(root/'contract_probe')]
    started=time.monotonic()
    result=subprocess.run(command,capture_output=True,timeout=180)
    (root/'stdout.log').write_bytes(result.stdout);(root/'stderr.log').write_bytes(result.stderr)
    record={'schema':'B5-native-component-build/v1','command':command,'returncode':result.returncode,
            'elapsed_seconds':time.monotonic()-started,'compiler':pin(compiler),'source':pin(source),
            'ROS':False,'physical_publishers':0}
    if result.returncode==0:
        deps=(root/'dependencies.d').read_text().replace('\\\n',' ')
        paths=shlex.split(deps.split(':',1)[1])
        record['dependencies']={str(Path(p).resolve()):pin(p) for p in paths}
        record['binary']=pin(root/'contract_probe')
        linked=subprocess.run(['/usr/bin/ldd',str(root/'contract_probe')],capture_output=True,timeout=10)
        (root/'ldd.log').write_bytes(linked.stdout+linked.stderr)
        assert linked.returncode==0 and b'not found' not in linked.stdout
        libs=[]
        for line in linked.stdout.decode().splitlines():
            for word in line.split():
                if word.startswith('/') and Path(word).is_file():libs.append(Path(word))
        record['runtime_libraries']={str(p.resolve()):pin(p) for p in libs}
    with (root/'build_manifest_v1.json').open('x') as f:json.dump(record,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({k:record[k] for k in ['returncode','elapsed_seconds']}))
    if result.returncode:raise SystemExit(result.returncode)


if __name__=='__main__':run()
