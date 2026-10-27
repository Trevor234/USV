#!/usr/bin/env python3
"""Post-run report serializer only; frozen v2 predicates and run inputs unchanged."""
import argparse,hashlib,json,os,secrets,sys
from pathlib import Path
sys.dont_write_bytecode=True
N=Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_7_20261014_v14')
sys.path[:0]=[str(N),str(N/'runtime')]
import check_c37_owned_run_v2 as frozen
import owned_release as publication
MAX_REPORT_BYTES=8*1024*1024
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
a=p.parse_args();helper=N/'check_c37_owned_run_v2.py';helper_before=sha(helper)
report=frozen.analyze(a.run_dir)
assert helper_before==sha(helper),'frozen v2 helper changed during analysis'
raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
assert 0<len(raw)<=MAX_REPORT_BYTES,'bounded report overflow'
# Same create-only atomic rename primitives as existing publisher; new bound
# applies only to this diagnostic report, never to any input/predicate reader.
output=publication.checked_path(a.output);directory=publication.open_directory(output.parent)
temporary='.'+output.name+'.peer.'+secrets.token_hex(16)+'.tmp'
fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
try:
 position=0
 while position<len(raw):position+=os.write(fd,raw[position:])
 os.fsync(fd)
finally:os.close(fd)
publication.rename_noreplace(directory,temporary,output.name)
os.fsync(directory);os.close(directory)
assert output.read_bytes()==raw,'report readback differs'
print(json.dumps({'passed':report['passed'],'reader_error':report.get('reader_error'),
 'issues':report['issues'],'report_bytes':len(raw),'report_sha256':sha(output),
 'frozen_helper_sha256':helper_before,'report_writer_sha256':sha(__file__),
 'analysis_policy_modified':False,'postrun_report_writer_only':True,
 'phase_qualified':False,'research_conclusion':False,'output':str(output)},sort_keys=True,indent=2))
