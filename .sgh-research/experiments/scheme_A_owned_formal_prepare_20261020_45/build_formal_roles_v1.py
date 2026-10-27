#!/usr/bin/env python3
"""Source-locked isolated two-role build and new typed-boundary component test."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

D=Path(__file__).resolve().parent;A=D/'author'


def pin(path):
    path=Path(path);raw=path.read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def create(path,value):
    with path.open('x') as f:json.dump(value,f,sort_keys=True,indent=2);f.write('\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);args=parser.parse_args()
    root=D/'build'/args.attempt;root.mkdir()
    prior=D.parent/'scheme_A_owned_business_start_20261020_39/author/build_c33_v9.py'
    tree=ast.parse(prior.read_text());setup=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SETUP' for t in node.targets))
    files={}
    for path in sorted(A.rglob('*')):
        assert not path.is_symlink()
        if not path.is_file():continue
        rel=path.relative_to(A);snapshot=root/'source_snapshot'/rel;snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes(path.read_bytes())
        files[str(rel)]={'path':str(path),'snapshot':str(snapshot),**pin(path)}
    bundle={'schema':'formal-prepare-source-bundle-v1','role':'formal_prepare_runtime','roles':['fixture','preparer'],
            'files':files,'driver_tool_sha256':pin(A/'owned_prepare_driver_v1.py')['sha256']}
    create(root/'source_bundle.json',bundle)
    bp={'path':str(root/'source_bundle.json'),'files':len(files),'sha256':pin(root/'source_bundle.json')['sha256']}
    result={'schema':'formal-owned-roles-build-v1','passed':False,'install_performed':False,'ROS_session_started':False,
            'source_bundle':bp,'driver_tool_sha256':bundle['driver_tool_sha256'],'SDK_setup_source':{'path':str(prior),**pin(prior)},
            'stage_qualified':False,'execute_qualified':False};started=time.monotonic()
    try:
        commands=[('configure',['cmake','-S',str(A),'-B',str(root/'cmake'),'-DCMAKE_BUILD_TYPE=Release',
                    '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DPython3_EXECUTABLE=/usr/bin/python3',
                    '-DP1_OWNED_SOURCE_BUNDLE_SHA256='+bp['sha256'],'-DP1_DRIVER_TOOL_SHA256='+bundle['driver_tool_sha256']],60),
                  ('build',['cmake','--build',str(root/'cmake'),'-j2'],180),
                  ('bounds_test',[str(root/'cmake/test_formal_input_bounds')],15)]
        for name,command,budget in commands:
            script=root/(name+'.sh');script.write_text('set -e\n'+setup+'exec timeout --signal=TERM --kill-after=5s '+str(budget)+'s '+shlex.join(command)+'\n')
            with (root/(name+'.log')).open('xb') as stream:
                rc=subprocess.run(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,timeout=budget+10).returncode
            result[name+'_returncode']=rc
            if rc:raise RuntimeError(name+' failed: '+str(rc))
        deps={}
        for path in (root/'cmake').rglob('*.o.d'):
            raw=path.read_text().replace('\\\n',' ')
            for token in shlex.split(raw.split(':',1)[1]):
                p=Path(token).resolve(strict=True);deps[str(p)]={'path':str(p),**pin(p)}
        result['compiler_dependencies']=deps
        for tool,command in [('compiler',['bash','-c',setup+'command -v c++']),
                             ('compiler_frontend',['/usr/bin/g++','-print-prog-name=cc1plus'])]:
            p=Path(subprocess.check_output(command,text=True).strip()).resolve();result[tool]={'path':str(p),**pin(p)}
        roles={}
        for role in ['fixture','preparer']:
            binary=root/'cmake'/('p1_formal_'+role+'_owned_v1');roles[role]={'binary':str(binary),'binary_sha256':pin(binary)['sha256'],'source_bundle':bp,'passed':True}
        reused=json.loads((D/'preflight/reused_roles_registry_v1.json').read_text());roles.update(reused)
        registry={'schema':'formal-prepare-runtime-registry-v1','roles':roles,'driver_tool_sha256':bundle['driver_tool_sha256']}
        create(root/'runtime_registry_v1.json',registry)
        libs={}
        for role in ['fixture','preparer']:
            binary=roles[role]['binary'];ldd=subprocess.run(['bash','-c',setup+'exec ldd '+shlex.quote(binary)],capture_output=True,timeout=15)
            (root/(role+'_ldd.log')).write_bytes(ldd.stdout+ldd.stderr);assert ldd.returncode==0 and b'not found' not in ldd.stdout
            for line in ldd.stdout.decode().splitlines():
                for word in line.split():
                    if word.startswith('/') and Path(word).is_file():
                        p=Path(word).resolve();libs[str(p)]={'path':str(p),**pin(p)}
        for row in files.values():assert all(pin(row['path'])[k]==row[k] for k in ['bytes','sha256'])
        result.update(passed=True,roles=roles,runtime_libraries=libs,registry={'path':str(root/'runtime_registry_v1.json'),**pin(root/'runtime_registry_v1.json')},
                      new_input_boundary_test=json.loads((root/'bounds_test.log').read_text()))
    except Exception as e:result.update(error=repr(e),traceback=__import__('traceback').format_exc())
    result['elapsed_seconds']=time.monotonic()-started;create(root/'build_result_v1.json',result)
    print(json.dumps({k:result[k] for k in ['passed','elapsed_seconds']}|{'error':result.get('error'),'output':str(root)}))
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
