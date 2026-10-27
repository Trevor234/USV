#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent;sys.path.insert(0,str(D));import build_and_verify_v2 as B
N=B.N
CASES=['normal','worker_post_exit']
def main():
 p=argparse.ArgumentParser();p.add_argument('--case',choices=CASES,required=True);a=p.parse_args();case=a.case
 out=D/'runs'/case;out.mkdir(exist_ok=False)
 assert json.loads((D/'preflight/workspace_initial.json').read_text())['passed']
 assert json.loads((D/'component/native_attempt01/result.json').read_text())['passed']
 assert json.loads((D/'component/checker_finite_v1.json').read_text())['passed']
 for path,row in json.loads((D/'preregister/helper_pins_v1.json').read_text())['files'].items():assert B.sha(path)==row['sha256'],path
 B.verify(json.loads((N/'source_bundles_current.json').read_text())['observer'])
 domain=151+CASES.index(case);run=N/'runs'/('owned_C39_'+case+'_01')
 rc=B.command(out,'run_owned',['/usr/bin/python3','-B',str(N/'prepare_fixture.py'),'--run-id',run.name,'--domain',str(domain),'--mode','positive','--c38-case',case],75,domain)
 B.write(out/'invocation.json',{'case':case,'driver_returncode':rc,'domain':domain,'run_dir':str(run),'source_bundle':json.loads((N/'source_bundles_current.json').read_text())['observer'],'stage_qualified':False})
 if (run/'result.json').exists():
  with (out/'result.json').open('xb') as f:f.write((run/'result.json').read_bytes())
 checker='check_c38_owned_close.py' if case=='normal' else 'check_c39_worker_close.py'
 checkrc=B.command(out,'check_owned',['/usr/bin/python3','-B',str(N/checker),'--run-dir',str(run),'--output',str(out/'check_result.json')],45,domain)
 x=json.loads((out/'check_result.json').read_text());print(json.dumps({'case':case,'driver_returncode':rc,'check_returncode':checkrc,'passed':x['passed'],'reader_error':x.get('reader_error'),'issues':x.get('issues')},ensure_ascii=False));return checkrc
if __name__=='__main__':raise SystemExit(main())
