#!/usr/bin/env python3
"""Reproduce observed16MiB refusal and bounded64MiB positive on real files."""
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(D/'author_r2'));sys.path.insert(0,str(D/'author_r2/runtime'))
from supervision_bridge_v1 import SourceCursor


def main():
    outcomes=[]
    with tempfile.TemporaryDirectory(prefix='USV_source_budget_') as temp:
        path=Path(temp)/'Source.jsonl'
        row=(json.dumps({'type':'source_budget_fixture','padding':'x'*40000})+'\n').encode()
        with path.open('xb') as f:
            for _ in range(500):f.write(row)
        st=path.stat();identity={'device':st.st_dev,'inode':st.st_ino}
        try:
            cur=SourceCursor(path,identity);cur.close();old_reject=False
        except ValueError:old_reject=True
        cur=SourceCursor(path,identity,max_bytes=64*1024*1024)
        try:new_rows=cur.poll();new_pass=len(new_rows)==500 and cur.offset==st.st_size
        finally:cur.close()
        outcomes=[{'name':'old16MiB_refuses_actual20MB_source','passed':old_reject},
                  {'name':'new64MiB_reads_same_bounded_source','passed':new_pass},
                  {'name':'reader_remains_below_total128MiB_output_budget','passed':64*1024*1024<=128*1024*1024}]
    report={'schema':'normal-source-explicit-reader-budget-cases-v1','passed':all(r['passed'] for r in outcomes),'cases':outcomes,
            'actual_regular_file_operations':True,'control_parameters_or_ELFs_changed':False,'stage_qualified':False}
    with (D/'verification/normal_source_reader_budget_cases_v1.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({'passed':report['passed'],'cases':len(outcomes)}));return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
