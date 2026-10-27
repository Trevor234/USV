"""Finite immutable suite runner; creates result/console, never retries."""
from pathlib import Path
import argparse,hashlib,importlib,io,json,sys,time,unittest
sys.dont_write_bytecode=True
p=argparse.ArgumentParser();p.add_argument('module');p.add_argument('--result',type=Path,required=True)
p.add_argument('--expected-count',type=int,required=True);a=p.parse_args()
suite=unittest.defaultTestLoader.loadTestsFromName(a.module)
stream=io.StringIO();start=time.monotonic()
result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
raw=stream.getvalue().encode('utf-8');console=a.result.with_suffix('.console.log')
with console.open('xb') as f:f.write(raw)
data=dict(schema='p1-finite-python-suite-result-v1',module=a.module,tests_run=result.testsRun,
          skipped=[dict(test=str(t),reason=r) for t,r in result.skipped],
          failures=[dict(test=str(t),trace=r) for t,r in result.failures],
          errors=[dict(test=str(t),trace=r) for t,r in result.errors],elapsed_seconds=time.monotonic()-start,
          expected_count=a.expected_count,passed=result.wasSuccessful() and result.testsRun==a.expected_count,
          console_sha256=hashlib.sha256(raw).hexdigest(),platform=sys.platform)
with a.result.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2)
print(json.dumps(data))
sys.exit(0 if data['passed'] else 2)
