#!/usr/bin/env python3
"""Create-only mainline documentation delivery with two full SHA readbacks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
helper = D.parent / 'scheme_A_B4_applicability_20261019_31/sync_MPC_v1.py'
assert hashlib.sha256(helper.read_bytes()).hexdigest() == 'a1d01de6003d040209a385124524d4fdcb25895d6b95575ea6d4b8ddff7ffbe3'
qa = json.loads((D / 'postrun/final_QA_v1.json').read_bytes())
assert qa['passed'] and not qa['M4_stage_qualified'] and qa['new_ROS_runs'] == 0
spec = importlib.util.spec_from_file_location('mainline_checkpoint_create_only_delivery', helper)
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
result = m.deliver(D.name)
result.update(schema='SchemeA-batch52-mainline-document-MPC-delivery/v1',
              final_regular_files_per_root=result['files'] + 1, document_checkpoint=True,
              user_confirmed_parallel_changes_preserved=True, new_ROS_runs=0,
              M4_stage_qualified=False, F6_qualified=False, P1_qualified=False)
raw = (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
dest = Path(result['destination'])
for root in [D, dest]:
    with (root / 'delivery_verification.json').open('xb') as f:f.write(raw)
assert (D / 'delivery_verification.json').read_bytes() == (dest / 'delivery_verification.json').read_bytes() == raw
assert m.population(D) == m.population(dest)
print(json.dumps({'passed': True, 'files_each': result['final_regular_files_per_root'], 'full_second_SHA_readback': True,
                  'destination': str(dest), 'receipt_sha256': hashlib.sha256(raw).hexdigest()}))
