#!/usr/bin/env python3
"""Read-only preregistered v2 predicates; separate bounded analysis report writer."""
from pathlib import Path
import hashlib,json,os,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_7_20261014_v14'
sys.path[:0]=[str(N),str(N/'runtime')]
import check_c37_owned_run_v2 as checker
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 pin=json.loads((D/'postrun/analysis_writer_pins_v1.json').read_text())
 assert pin['writer_sha256']==sha(__file__) and pin['checker_sha256']==sha(checker.__file__)
 R=N/'runs/owned_C37_positive_02'
 report=checker.analyze(R);report['checker_sha256']=sha(checker.__file__)
 raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
 assert 0<len(raw)<=8*1024*1024,'bounded analysis report'
 p=D/'runs/positive02/check_result.json'
 assert not any(x.is_symlink() for x in p.parents)
 with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 assert p.read_bytes()==raw
 receipt={'schema':'C3.7-analysis-report-writer/v1','passed':True,'report_path':str(p),'report_sha256':sha(p),'report_bytes':len(raw),'writer_sha256':sha(__file__),'checker_sha256':sha(checker.__file__),'report_bound_bytes':8*1024*1024,'predicate_modified':False,'original_CLI_failure_retained':True,'release_writer_or_budget_changed':False,'prerun_checker_snapshot_verified':True,'stage_qualified':False,'research_conclusion':False}
 with (D/'runs/positive02/analysis_writer_receipt_v1.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
 print(json.dumps({'passed':report['passed'],'issues':report.get('issues'),'report_bytes':len(raw),'worker_callbacks':report.get('worker_callbacks'),'worker_publications':report.get('worker_publications'),'witness_v2':report.get('witness_v2')},ensure_ascii=False))
 return 0 if report['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
